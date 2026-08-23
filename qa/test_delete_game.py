#!/usr/bin/env python3
"""개별 삭제의 계약 — **순서 · 중간 상태 합법성 · 토큰 우회 · 부수 처리.**
설계 정본 DESIGN-DELETE §5-A·§6-B.

이 파일이 잠그는 것 6가지:
  ① **실행 순서**(대피→meta unlink→rmtree→registry)를 **단계별 크래시 주입**으로 잠근다.
     순서가 바뀌면 주입 지점의 잔존 상태가 달라져 반드시 걸린다.
  ② 중단 상태의 **소비자 전수 합법성** — 특히 *"본체 없음 · meta 잔존"*이 한 번도 생기지
     않는지. 그 상태는 `_profile_ready`(빈 슬롯)와 `apply_all`(already + registry 기록)의
     판정이 **정면으로 어긋나는** 자리다(설계 개정 1판의 최심각 결함).
     ★ 검사가 항진식이 아님을 **합성 주입**으로 증명한다 — 그 상태를 손으로 만들어
       판정기가 실제로 FAIL을 내는지 먼저 보인다(거짓 검사 방지 체크리스트).
  ③ 토큰 우회 전종 — 무토큰·위조·재사용·만료·타 게임·**scope 혼동**(저장 토큰으로 삭제).
  ④ 비숫자 appid 거부 · 미등록 거부 · **경로 봉쇄 4종** — 루트 밖 링크 / 루트 안 남의
     게임 링크 / 이름만 같은 루트 밖 링크(dirname 절반) / **슬롯 레벨 링크**(반려 ①′).
  ⑤ `last_appid` 정리(그리고 남의 last_appid는 안 건드린다).
  ⑥ TOCTOU — 확인창을 띄운 사이 프로필이 저장되면 삭제 토큰이 무효.
  ⑦ **meta가 손상돼도 본체는 대피한다**(QA 반려 ② — 본체 탐색을 meta에서 뗀 선택의 잠금).
     설계 원문대로 meta의 `filename`을 거쳐 찾으면 그 슬롯은 대피 없이 rmtree된다.
그리고 관통 단언: **게임 설정 파일 원본은 1바이트도 안 바뀐다 · `backups/`는 줄지 않는다.**

⑧ **`DELETE_FAILED`가 덮는 두 종류를 갈라 두는 사실 필드**(2026-08-23 QA DEFECT-06).
   이 코드 하나가 *"삭제 도중 실패 — 일부 지워졌을 수 있다"*와 *"시작 전 거부 — 아무것도 안
   지웠다"*를 함께 덮는다. 화면은 두 문장으로 갈리고, 그 근거는 `stage`가 **아니라**
   봉투의 `profile_delete_started`다(같은 `"escape"`를 `restore.py`가 **다른 코드**
   `BACKUP_OUT_OF_ROOT`에도 쓴다). 그래서 여기서 넷을 잠근다 —
   ⓐ `meta`·`rmtree` 주입에서 `is True` · ⓑ escape 거부마다 `is False` ·
   ⓒ escape **전후로** 대상 게임의 registry 항목·프로필 트리 지문이 같음(**백업 링은 제외** —
   삭제 전 대피가 먼저라 링은 이미 바뀌어 있을 수 있고, `False`는 링까지 부정하지 않는다) ·
   ⓓ `codes.DELETE_FAILED`의 생성점이 **공통 helper 하나뿐**인지 AST 소스 계약(⑨절).

★ 실데이터에 닿을 수 없다 — `main.py`는 `DECKY_PLUGIN_RUNTIME_DIR`이 없으면 뜨지도 않고,
  있으면 그것을 `GFXPROFILE_DATA_DIR`에 **무조건 대입**한다. 여기서는 그것이 tmp다.
"""
import ast
import asyncio
import copy
import inspect
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"

LOG = []          # decky.logger로 실제로 흘러간 줄. gfxp 로거 배선을 여기서 잰다.


def boot(tmp):
    """`main.py`를 샌드박스에서 띄운다. `decky`는 로더가 주는 모듈이라 여기서 흉내 낸다."""
    def rec(kind):
        def fn(fmt="", *args, **kwargs):
            try:
                LOG.append((kind, (str(fmt) % args) if args else str(fmt)))
            except Exception:                                   # noqa: BLE001
                LOG.append((kind, "%s %r" % (fmt, args)))
        return fn

    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(
        info=rec("info"), warning=rec("warning"), error=rec("error"), debug=rec("debug"),
        # `_DeckyBridge`가 쓰는 자리 — 이게 없으면 gfxp 로거 배선이 조용히 죽는다.
        log=lambda level, fmt="", *args, **kwargs: rec("log")(fmt, *args),
    )
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # ← 격리는 이 한 줄이 한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    """route는 async다(Decky가 반환값을 await한다). 봉투를 그대로 돌려준다."""
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def mkgame(tmp, engine, store, appid, name, dock=True, internal=True):
    """합성 게임 하나. 디스크는 dock 프로필과 같은 내용으로 끝난다."""
    reg = store.load_registry()
    cfg = tmp / ("game%s" % appid) / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(DOCK)
    engine.add_game(reg, appid, str(cfg), name=name)
    if dock:
        engine.save_profile(reg, appid, "dock")
    if internal:
        cfg.write_bytes(INTERNAL)
        engine.save_profile(reg, appid, "internal")
        cfg.write_bytes(DOCK)
    store.save_registry(reg)
    return cfg


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-delete-"))
    unchmod = []
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []
        #: `delete_escape`를 실제로 지난 escape 거부의 라벨. **세지 말고 재라** — 아래 finish()가
        #: 이 목록을 그대로 찍어, 절이 통째로 빠져도 출력에서 드러난다.
        escape_seen = []

        def P(msg):
            problems.append(msg)

        def finish():
            """★ 사전 조건이 무너지면 **여기로 빠져나온다.** 그냥 진행하면 뒤 절이
            traceback으로 죽어 정작 무엇이 깨졌는지가 화면에서 사라진다(진단이 사라지는 실패)."""
            print("개별 삭제 계약 — 순서 3단계 주입 · 중간 상태 소비자 전수 · 토큰 6종 · "
                  "가드 6종(경로 봉쇄 4) · last_appid 2종 · 손상 meta 대피  (데이터: %s)" % tmp)
            print("  음성 대조군: 「본체 없음·meta 잔존」 합성 주입 → hazardous 검출 + "
                  "apply_all=already 확인 · 무변조 세계에서 삭제 토큰 통과(⑧-d-4)")
            print("  토큰 지문 축 4종(⑧-d): meta 파일 · 백업 개수 · 링 이름 순서 · 축출 대상")
            print("  로그 배선: decky.logger로 흘러간 줄 %d개" % len(LOG))
            print("  DELETE_FAILED 사실 필드(DEFECT-06): escape %d자리 — %s "
                  "· meta/rmtree 주입 2자리 True · 생성점 단일 AST 계약(⑨)"
                  % (len(escape_seen), " ".join(escape_seen) or "없음"))
            if problems:
                print("\nFAIL")
                for p in problems:
                    print("  " + p)
                return 1
            print("PASS")
            return 0

        # ── 판정기들 ─────────────────────────────────────────────────────────
        def registered(appid):
            return str(appid) in store.load_registry()["games"]

        def meta_exists(appid, profile):
            return os.path.exists(store.profile_meta_path(appid, profile))

        def body_exists(appid, profile):
            directory = store.profile_dir(appid, profile)
            if not os.path.isdir(directory):
                return False
            # 부산물 판정은 **코드와 같은 문**을 지난다 — 검사가 규칙을 복제해 두면
            # "목록이 하나"라는 전제가 검사 쪽에서 먼저 깨진다(설계 §14-G ⓑ).
            return any(not store.is_byproduct(n) for n in os.listdir(directory))

        def hazardous(appid):
            """★ "meta 잔존 · 본체 없음" 슬롯. 이 상태가 생기면 소비자 판정이 갈린다."""
            return [p for p in ("dock", "internal")
                    if meta_exists(appid, p) and not body_exists(appid, p)]

        def bulk_outcome(appid, profile):
            """`apply_all`이 그 게임을 뭐라고 판정하는가. **사본에** 돌려 registry를 안 더럽힌다."""
            reg = copy.deepcopy(store.load_registry())
            rows = engine.apply_all(reg, profile)
            return next((r["outcome"] for r in rows if r["appid"] == str(appid)), None)

        def nbackups(appid):
            return len(store.list_backups(appid))

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def code_of(env):
            return env.get("code")

        def _fp_walk(path, rel, seen, rows):
            """lstat·내용 지문을 `rows`에 쌓는다. **링크는 따라간다** — 슬롯 링크 너머의 남의
            트리가 지워지는 변이도 같은 지문에 걸리게 하려는 것이다. 같은 실경로는 한 번만
            본다(순환 방지). 링크 자체는 **대상 문자열**로 남으니 링크가 바뀌어도 걸린다."""
            try:
                st = os.lstat(path)
            except OSError as exc:
                rows.append("%s|없음(%s)" % (rel, type(exc).__name__))
                return
            if os.path.islink(path):
                rows.append("%s|link|%s" % (rel, os.readlink(path)))
                real = os.path.realpath(path)
                if real in seen or not os.path.isdir(path):
                    return
                seen.add(real)
            elif os.path.isdir(path):
                rows.append("%s|dir|%o" % (rel, st.st_mode))
            else:
                rows.append("%s|file|%o|%d|%s"
                            % (rel, st.st_mode, st.st_size, store.sha1_file(path) or "?"))
                return
            try:
                names = sorted(os.listdir(path))
            except OSError as exc:
                rows.append("%s|열람불가(%s)" % (rel, type(exc).__name__))
                return
            for n in names:
                _fp_walk(os.path.join(path, n), rel + "/" + n, seen, rows)

        def escape_fp(appid):
            """**escape 거부가 안 건드렸어야 하는 것**의 지문 — 그 게임의 registry 항목과
            프로필 트리(lstat·내용).

            ⚠️ **백업 링은 일부러 뺀다.** 삭제는 *대피 → 삭제* 순서라, 한 슬롯을 대피시킨 뒤
              다음 슬롯에서 거부되면 링은 **이미 바뀌어 있다.** `profile_delete_started=False`가
              부정하는 것은 「등록 정보와 프로필 데이터의 삭제 단계」뿐이고, 링까지 비교하면
              이 검사가 **참인 구현을 FAIL로** 만든다(그리고 그 단언은 원래 거짓이다)."""
            entry = store.load_registry()["games"].get(str(appid))
            rows = ["registry|" + json.dumps(entry, sort_keys=True, ensure_ascii=False)]
            _fp_walk(store.profiles_root(appid), "profiles", set(), rows)
            return rows

        def drop_link(path):
            """정리용 — **뒷정리가 진단을 가리지 않게** 한다. 변이를 넣으면 삭제가 성공해
            링크가 이미 사라져 있는데, 그때 unlink가 터지면 traceback이 FAIL 문구를 덮는다."""
            try:
                os.unlink(path)
            except OSError:
                pass

        # ═══════════════════════════════════════════════════════════════════
        # ② 먼저 **판정기가 항진식이 아님을 증명**한다 (거짓 검사 방지).
        #    "본체 없음 · meta 잔존"을 손으로 만들어, hazardous()가 잡고 apply_all이
        #    실제로 already를 보고하는지 본다. 못 잡으면 아래 단언들은 전부 무의미하다.
        # ═══════════════════════════════════════════════════════════════════
        mkgame(tmp, engine, store, "600", "HazardControl")
        if hazardous("600"):
            P("음성 대조군: 정상 게임인데 hazardous()가 잡았다 — 판정기가 과검출한다")
        if bulk_outcome("600", "dock") != "already":
            P("음성 대조군: 디스크=dock인데 apply_all이 already가 아니다 — 전제가 안 섰다")
        body = os.path.join(store.profile_dir("600", "dock"), "video.ini")
        os.unlink(body)                                   # 본체만 지운다(meta는 남긴다)
        if hazardous("600") != ["dock"]:
            P("★판정기가 「본체 없음·meta 잔존」을 못 잡는다 — 이 파일의 ② 단언이 전부 항진식이다")
        if bulk_outcome("600", "dock") != "already":
            P("합성 위험 상태에서 apply_all이 already를 안 냈다 — 재려던 어긋남에 닿지 못했다")
        if main._profile_ready("600", "dock"):
            P("합성 위험 상태인데 _profile_ready가 참이다 — 두 소비자의 어긋남이 재현되지 않았다")

        # ═══════════════════════════════════════════════════════════════════
        # ① 실행 순서를 **단계별 크래시 주입**으로 잠근다 (게임 100)
        # ═══════════════════════════════════════════════════════════════════
        cfg100 = mkgame(tmp, engine, store, "100", "OrderTarget")
        cfg_bytes = cfg100.read_bytes()

        def token(appid):
            env = rpc(main, "delete_game", str(appid))
            if not is_confirm(env):
                P("토큰 발급 실패 — %s에 CONFIRM_REQUIRED가 안 왔다 (%s)" % (appid, env))
                return None
            return (env.get("params") or {}).get("confirm_token")

        # ── 1단계 주입: 대피(백업)가 실패한다 → 원본 무손실이어야 한다 ─────────
        bdir = store.backups_dir("100")
        os.makedirs(bdir, exist_ok=True)
        base_backups = nbackups("100")
        os.chmod(bdir, 0o500)
        unchmod.append(bdir)
        env = rpc(main, "delete_game", "100", confirm_token=token("100"))
        os.chmod(bdir, 0o700)
        if code_of(env) != codes.BACKUP_FAILED:
            P("1단계 주입: 대피 실패인데 BACKUP_FAILED가 아니다 — %s" % env)
        if not registered("100") or not meta_exists("100", "dock") or not body_exists("100", "dock"):
            P("★1단계 실패인데 원본이 손상됐다 — 「대피 실패 시 아무것도 지우지 않는다」가 거짓이다")
        if hazardous("100"):
            P("1단계 중단 상태가 위험 상태다 — %s" % hazardous("100"))
        if not registered("100"):
            P("★1단계 주입이 안 먹었다(삭제가 그냥 성공했다) — ①의 나머지 단계를 잴 수 없다")
            return finish()

        # ── 2단계 주입: dock meta unlink가 실패한다 ────────────────────────────
        #    여기서 **대피가 이미 끝나 있어야** 한다 = 순서 1→2의 증거.
        dockdir = store.profile_dir("100", "dock")
        os.chmod(dockdir, 0o500)
        unchmod.append(dockdir)
        env = rpc(main, "delete_game", "100", confirm_token=token("100"))
        os.chmod(dockdir, 0o700)
        if code_of(env) != codes.DELETE_FAILED:
            P("2단계 주입: meta unlink 실패인데 DELETE_FAILED가 아니다 — %s" % env)
        if (env.get("params") or {}).get("stage") != "meta":
            P("2단계 주입: stage가 meta가 아니다 — 부분 삭제 상태를 진단할 수 없다 (%s)" % env)
        # ★ (DEFECT-06) 여기는 **삭제 단계 안**이다 — 화면은 "일부 지워졌을 수 있다"를 말해야
        #   한다. False가 실리면 화면이 **안전을 거짓 단언**한다(실제로는 meta가 하나 지워졌을
        #   수 있는 상태다). 이 한 줄이 그 뒤집힘을 잠근다.
        if (env.get("params") or {}).get("profile_delete_started") is not True:
            P("★2단계 주입: profile_delete_started가 True가 아니다 (%r) — 삭제 단계에서 멈췄는데 "
              "화면이 「등록 정보와 프로필 데이터는 지우지 않았습니다」라고 말한다"
              % (env.get("params") or {}).get("profile_delete_started"))
        if nbackups("100") <= base_backups:
            P("★순서 위반 — meta unlink 단계에 닿았는데 대피본이 없다 (대피가 선행하지 않았다)")
        if not registered("100"):
            P("★순서 위반 — 2단계에서 멈췄는데 registry 항목이 이미 사라졌다")
        if hazardous("100"):
            P("2단계 중단 상태가 위험 상태다 — %s" % hazardous("100"))
        if bulk_outcome("100", "dock") not in ("already", "no_profile"):
            P("2단계 중단 상태에서 apply_all이 예상 밖 판정을 냈다 — %s" % bulk_outcome("100", "dock"))
        if not registered("100") or not os.path.isdir(store.profiles_root("100")):
            P("★2단계 주입이 안 먹었다 — 3단계 주입을 잴 수 없다")
            return finish()

        # ── 3단계 주입: rmtree가 실패한다 ─────────────────────────────────────
        #    meta는 **이미 지워져 있어야** 한다 = 순서 2→3의 증거이자 중단 상태 합법성의 근거.
        proot = store.profiles_root("100")
        os.chmod(proot, 0o500)
        unchmod.append(proot)
        env = rpc(main, "delete_game", "100", confirm_token=token("100"))
        os.chmod(proot, 0o700)
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "rmtree":
            P("3단계 주입: rmtree 실패가 DELETE_FAILED/stage=rmtree로 안 왔다 — %s" % env)
        # ★ (DEFECT-06) meta는 이미 지워졌고 본체는 남았다 = **부분 삭제 상태**다.
        if (env.get("params") or {}).get("profile_delete_started") is not True:
            P("★3단계 주입: profile_delete_started가 True가 아니다 (%r) — 프로필 기록이 이미 "
              "지워진 상태인데 화면이 「지우지 않았습니다」라고 말한다"
              % (env.get("params") or {}).get("profile_delete_started"))
        if meta_exists("100", "dock") or meta_exists("100", "internal"):
            P("★순서 위반 — rmtree 단계에서 멈췄는데 meta.json이 남아 있다 (meta 선행 unlink 아님)")
        if not registered("100"):
            P("★순서 위반 — 3단계에서 멈췄는데 registry 항목이 이미 사라졌다")
        if hazardous("100"):
            P("★3단계 중단 상태가 위험 상태다 — %s (초판 결함의 재현)" % hazardous("100"))
        if bulk_outcome("100", "dock") != "no_profile":
            P("3단계 중단 상태에서 apply_all이 no_profile이 아니다 — %s ★소비자 판정이 갈린다"
              % bulk_outcome("100", "dock"))
        if main._profile_ready("100", "dock"):
            P("3단계 중단 상태인데 _profile_ready가 참이다")

        # ★ 로거 배선 — DELETE_FAILED가 실제로 decky 로그로 흘렀는가 (설계 §5-A)
        if not any("gfxp.remove" in line and "stage=rmtree" in line and "appid=100" in line
                   for _, line in LOG):
            P("★gfxp 로거 배선이 안 됐다 — remove.py의 진단 로그가 decky 로그에 안 실린다")

        # ── 재시도로 완결된다 (신규 복구 코드 0줄) ────────────────────────────
        env = rpc(main, "delete_game", "100", confirm_token=token("100"))
        if not env.get("ok"):
            P("중단 뒤 재시도가 완결되지 않았다 — %s" % env)
        if registered("100") or os.path.exists(store.profiles_root("100")):
            P("삭제 성공인데 registry 항목이나 profiles/가 남았다")
        if nbackups("100") <= base_backups:
            P("삭제됐는데 대피본이 없다 — 마지막 안전망이 사라졌다")
        if cfg100.read_bytes() != cfg_bytes or not cfg100.exists():
            P("★게임 설정 파일 원본이 바뀌었다 — 삭제는 툴 데이터만 지워야 한다")

        # ═══════════════════════════════════════════════════════════════════
        # ③ 토큰 우회 전종 (게임 200 · 이웃 500)
        # ═══════════════════════════════════════════════════════════════════
        mkgame(tmp, engine, store, "200", "TokenTarget")
        mkgame(tmp, engine, store, "500", "Neighbour")

        env = rpc(main, "delete_game", "200")                       # ③-a 무토큰
        if not is_confirm(env):
            P("③-a 토큰 없이 삭제가 통과했다 ★계약 위반 (%s)" % env)
        if not registered("200"):
            P("③-a 거부인데 게임이 사라졌다")
        tok200 = (env.get("params") or {}).get("confirm_token")
        if not tok200:
            P("③-a CONFIRM_REQUIRED에 confirm_token이 없다 — 프론트가 확정할 방법이 없다")
        for key in ("name", "has_dock", "has_internal", "saved_at", "backups"):
            if key not in (env.get("params") or {}):
                P("③-a 확인창이 쓸 %s가 params에 없다" % key)

        env = rpc(main, "delete_game", "200", confirm_token="지어낸-토큰")   # ③-b 위조
        if not is_confirm(env) or not registered("200"):
            P("③-b 지어낸 토큰으로 삭제가 통과했다 ★계약 위반 (%s)" % env)

        env = rpc(main, "delete_game", "500", confirm_token=tok200)         # ③-c 타 게임
        if not is_confirm(env) or not registered("500"):
            P("③-c 다른 게임의 토큰으로 삭제가 통과했다 ★계약 위반 (%s)" % env)

        # ③-d scope 혼동 — **저장 토큰으로 삭제**를 시도한다.
        cfg200 = tmp / "game200" / "video.ini"
        cfg200.write_bytes(b"quality=xxxx\nshadows=mid_\nsource=DISK-CHANGED\n")
        env = rpc(main, "save_profile", "200", "dock")              # 덮어쓰기 → 저장 토큰 발급
        save_tok = (env.get("params") or {}).get("confirm_token")
        cfg200.write_bytes(DOCK)
        if not save_tok:
            P("③-d 저장 토큰을 못 얻었다 — scope 혼동을 시험할 수 없다")
        else:
            env = rpc(main, "delete_game", "200", confirm_token=save_tok)
            if not is_confirm(env) or not registered("200"):
                P("③-d 저장 토큰으로 삭제가 통과했다 ★scope 네임스페이스가 안 갈린다 (%s)" % env)
        # 반대 방향도 본다 — 삭제 토큰으로 저장.
        del_tok = token("200")
        cfg200.write_bytes(b"quality=yyyy\nshadows=mid_\nsource=DISK-CHANGED\n")
        env = rpc(main, "save_profile", "200", "dock", confirm_token=del_tok)
        if not is_confirm(env):
            P("③-d′ 삭제 토큰으로 저장이 통과했다 ★scope 네임스페이스가 안 갈린다 (%s)" % env)
        cfg200.write_bytes(DOCK)

        # ③-e 만료
        tok = token("200")
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0
        try:
            env = rpc(main, "delete_game", "200", confirm_token=tok)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env) or not registered("200"):
            P("③-e 만료된 토큰이 통과했다 ★계약 위반 (%s)" % env)

        # ③-f 재사용 — 낡은 토큰은 다시 통과하지 못한다.
        #    삭제→같은 내용 재등록을 해도 지문이 **완전히 같지는 않다**: 삭제가 프로필을
        #    백업으로 대피시켜 백업 개수가 늘고, 그 개수가 delete_fingerprint에 반영된다
        #    (Codex #4 — 동일 재저장이 토큰을 무효화하지 않던 구멍을 백업 개수로 메웠다).
        #    그래서 두 번째 제출의 거부 사유는 「소각 또는 지문 변경」 둘 다로 정당하다 —
        #    route 수준에서는 "낡은 토큰이 통과하지 않는다"만 잰다. **순수 1회용 소각**의
        #    사유 격리는 바로 아래 유닛 검사(_issue/_consume 직접)가 담당한다.
        tok = token("200")
        env = rpc(main, "delete_game", "200", confirm_token=tok)
        if not env.get("ok"):
            P("③-f 정상 토큰인데 삭제가 안 됐다 (%s)" % env)
        mkgame(tmp, engine, store, "200", "TokenTarget")            # 같은 내용으로 재등록
        env = rpc(main, "delete_game", "200", confirm_token=tok)
        if not is_confirm(env) or not registered("200"):
            P("③-f 낡은 토큰이 재등록 뒤에도 통과했다 ★소각/지문 무효화 실패 (%s)" % env)
        # 인자 고정 소각도 직접 잰다(행위 수준만 재면 사유가 갈리지 않는다 — 저장 토큰과 같은 판단)
        t = main._issue("999", main._DELETE_SCOPE, "fp", "")
        if not main._consume(t, "999", main._DELETE_SCOPE, "fp", ""):
            P("③-f 방금 발급한 삭제 토큰이 첫 소비에서 거부됐다")
        if main._consume(t, "999", main._DELETE_SCOPE, "fp", ""):
            P("③-f 삭제 토큰이 두 번 소비됐다 ★1회용이 아니다")

        # ═══════════════════════════════════════════════════════════════════
        # ⑥ TOCTOU — 확인창을 띄운 사이 프로필이 저장되면 토큰 무효 (게임 800)
        # ═══════════════════════════════════════════════════════════════════
        cfg800 = mkgame(tmp, engine, store, "800", "ToctouTarget")
        tok = token("800")
        cfg800.write_bytes(b"quality=zzzz\nshadows=mid_\nsource=USER-RESAVED\n")
        env = rpc(main, "save_profile", "800", "internal")           # 다른 슬롯에 저장
        if is_confirm(env):
            env = rpc(main, "save_profile", "800", "internal",
                      confirm_token=(env.get("params") or {}).get("confirm_token"))
        if not env.get("ok"):
            P("⑥ 사전 조건 실패 — 확인창 사이 저장이 안 됐다 (%s)" % env)
        env = rpc(main, "delete_game", "800", confirm_token=tok)
        if not is_confirm(env) or not registered("800"):
            P("⑥ 확인창 사이 프로필이 저장됐는데 낡은 토큰이 통과했다 ★TOCTOU가 안 닫혔다 (%s)" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ④ 형태·존재 가드
        # ═══════════════════════════════════════════════════════════════════
        #
        # ★★ (2026-08-23 DEFECT-06) 아래 escape 거부들은 **아무것도 지우지 않은 거부**다.
        #   화면은 그때 *"등록 정보와 프로필 데이터는 지우지 않았습니다"*라고 말한다 —
        #   그 문장이 참이라는 근거를 **사람 기억이 아니라 이 함수에** 붙들어 둔다.
        #   ⓐ 봉투에 `profile_delete_started is False`가 실렸는가
        #   ⓑ 실제로 대상 게임의 registry 항목·프로필 트리가 **한 바이트도 안 바뀌었는가**
        #   둘 중 하나만 어긋나도 화면이 거짓을 말하게 된다. escape가 unlink/rmtree나
        #   registry pop **뒤로 밀리는** 변이는 ⓑ에서, 값을 반대로 싣는 변이는 ⓐ에서 걸린다.
        #   ⚠️ 지문에 **백업 링은 없다** — `escape_fp` 독스트링의 이유(대피가 삭제보다 먼저다).
        #   ⚠️ 토큰은 **거부 조건을 걸어 둔 상태에서** 받는다(④′ 주석의 이유 그대로) —
        #     지문 불일치로 거부되면 가드가 아니라 TOCTOU를 한 번 더 시험한 것이 된다.
        def delete_escape(appid, label):
            escape_seen.append(label)
            tok = token(appid)
            before = escape_fp(appid)
            env_ = rpc(main, "delete_game", str(appid), confirm_token=tok)
            started = (env_.get("params") or {}).get("profile_delete_started")
            if started is not False:
                P("★%s escape 거부인데 profile_delete_started가 False가 아니다 (%r) — "
                  "아무것도 안 지웠는데 화면이 「이미 일부 또는 전부 지워졌을 수 있습니다」라고 "
                  "말한다 (%s)" % (label, started, env_))

            # ★★ registry 축은 **route 밖에서 한 번 더** 잰다.
            #   `delete_game` route는 거부가 나가면 `_save_registry`에 닿지 못한다 — 그래서
            #   escape가 `reg["games"].pop()` **뒤로 밀려도 디스크 registry는 그대로다.**
            #   위 지문만으로는 그 변이를 못 본다(잠근다고 적어 두고 못 잠그는 자리가 된다).
            #   파괴의 문을 직접 불러 **제자리에서 고치는 그 dict**를 보면 잡힌다.
            #   덤: 거부가 route가 아니라 **문 안**에 있다는 것도 여기서 함께 잠긴다
            #   (`reset_all`은 route 검증을 한 번도 지나지 않고 이 문으로 들어온다).
            reg_probe = store.load_registry()
            had = str(appid) in reg_probe["games"]
            try:
                main.remove.delete_game_data(reg_probe, appid)
            except engine.Refused as exc:
                if exc.code != codes.DELETE_FAILED:
                    P("★%s 파괴의 문을 직접 불렀더니 DELETE_FAILED가 아닌 %s로 거부됐다"
                      % (label, exc.code))
                if exc.params.get("profile_delete_started") is not False:
                    P("★%s 직접 호출의 봉투에도 profile_delete_started=False가 없다 (%r)"
                      % (label, exc.params.get("profile_delete_started")))
            else:
                P("★%s 파괴의 문(`delete_game_data`)을 직접 부르니 거부되지 않았다 — 가드가 "
                  "route에만 있다. `reset_all`은 그 route를 지나지 않는다" % label)
            if had and str(appid) not in reg_probe["games"]:
                P("★%s escape 거부인데 registry 항목이 이미 pop됐다 — 거부가 registry 제거 "
                  "**뒤로** 밀렸다. 「등록 정보는 지우지 않았습니다」가 거짓이 된다" % label)

            after = escape_fp(appid)
            if before != after:
                lost = [r for r in before if r not in after]
                born = [r for r in after if r not in before]
                P("★%s escape 거부인데 대상 게임의 등록 항목·프로필 트리가 바뀌었다 — "
                  "「지우지 않았습니다」가 거짓이다 (사라짐 %s / 생김 %s)"
                  % (label, lost[:5], born[:5]))
            return env_

        env = rpc(main, "delete_game", "../../etc")
        if code_of(env) != codes.BAD_IDENTIFIER:
            P("④ 비숫자 appid가 BAD_IDENTIFIER로 거부되지 않았다 — %s" % env)
        env = rpc(main, "delete_game", "9999999")
        if code_of(env) != codes.GAME_NOT_REGISTERED:
            P("④ 미등록 appid가 GAME_NOT_REGISTERED로 거부되지 않았다 — %s" % env)

        # ④′ 심볼릭 링크 — profiles/<appid>가 링크면 **링크 밖을 지우면 안 된다**
        mkgame(tmp, engine, store, "700", "SymlinkTarget")
        shutil.rmtree(store.profiles_root("700"))
        outside = tmp / "outside-treasure"
        (outside / "dock").mkdir(parents=True, exist_ok=True)
        (outside / "dock" / "meta.json").write_text('{"filename":"video.ini","sha1":"x"}')
        (outside / "dock" / "video.ini").write_bytes(DOCK)
        os.symlink(str(outside), store.profiles_root("700"))
        # ★ 토큰은 **링크를 걸어 둔 상태**에서 받는다 — 지문 불일치로 거부되면 링크 가드를
        #   시험한 것이 아니라 TOCTOU를 한 번 더 시험한 것이 된다(재려던 것에 안 닿는다).
        env = delete_escape("700", "④′")
        if code_of(env) != codes.DELETE_FAILED:
            P("④′ 심볼릭 링크 프로필 루트를 거부하지 않았다 ★루트 밖을 지운다 — %s" % env)
        if (env.get("params") or {}).get("stage") != "escape":
            P("④′ stage가 escape가 아니다 — 경로 봉쇄 검사가 아닌 다른 이유로 걸렸다 (%s)" % env)
        if not (outside / "dock" / "meta.json").exists() or not (outside / "dock" / "video.ini").exists():
            P("★④′ 링크 너머의 파일이 지워졌다 — 데이터 루트 밖 삭제가 일어났다")
        if not registered("700"):
            P("④′ 거부인데 registry 항목이 사라졌다")
        drop_link(store.profiles_root("700"))

        # ④″ 데이터 루트 **안**을 가리키는 링크 — prefix 비교만으로는 통과하는 자리다.
        #    통과하면 2단계 meta unlink가 **남의 게임 meta**를 지운다(교차 피해).
        #    (이전 `islink` 분기가 잡던 것을 새 검사가 약화시키지 않았는지 보는 절이다.)
        mkgame(tmp, engine, store, "710", "InsideLinkSource")
        mkgame(tmp, engine, store, "720", "InsideLinkVictim")
        shutil.rmtree(store.profiles_root("710"))
        os.symlink(store.profiles_root("720"), store.profiles_root("710"))
        env = delete_escape("710", "④″")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("④″ 데이터 루트 안을 가리키는 링크를 거부하지 않았다 — %s" % env)
        if not meta_exists("720", "dock") or not meta_exists("720", "internal"):
            P("★④″ 남의 게임(720)의 meta가 지워졌다 — 링크를 따라간 교차 피해")
        drop_link(store.profiles_root("710"))

        # ④⁗ 루트 링크인데 **대상의 이름이 appid와 같은** 경우 — `basename`만 비교하는
        #    구현이면 그대로 통과해 루트 밖을 지운다. 검사의 `dirname` 절반을 잠그는 절이다
        #    (이 케이스가 없으면 "basename만 비교" 변이가 살아남는다).
        mkgame(tmp, engine, store, "760", "SameNameDecoy")
        decoy = tmp / "decoy-root" / "760"
        (decoy / "dock").mkdir(parents=True, exist_ok=True)
        (decoy / "dock" / "meta.json").write_text('{"filename":"video.ini","sha1":"y"}')
        (decoy / "dock" / "video.ini").write_bytes(DOCK)
        shutil.rmtree(store.profiles_root("760"))
        os.symlink(str(decoy), store.profiles_root("760"))
        env = delete_escape("760", "④⁗")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("④⁗ 이름이 같은 루트 밖 링크를 거부하지 않았다 — %s" % env)
        if not (decoy / "dock" / "meta.json").exists() or not (decoy / "dock" / "video.ini").exists():
            P("★④⁗ 루트 밖(이름만 같은 곳)의 파일이 지워졌다 — dirname 비교가 없다")
        drop_link(store.profiles_root("760"))

        # ④‴ **슬롯 레벨** 링크 (QA 반려 ①′) — 루트는 실디렉터리인데 그 안의 dock/internal만
        #    링크인 경우. 루트 검사만으로는 통과하고, 2단계 meta unlink가 **링크를 따라가**
        #    남의 meta.json을 지운다(rmtree는 링크를 안 따라가므로 본체는 고아로 남는다).
        #    (a) dock 슬롯 → 같은 데이터 루트의 다른 게임
        mkgame(tmp, engine, store, "730", "SlotLinkSource")
        mkgame(tmp, engine, store, "740", "SlotLinkVictim")
        shutil.rmtree(store.profile_dir("730", "dock"))
        os.symlink(store.profile_dir("740", "dock"), store.profile_dir("730", "dock"))
        env = delete_escape("730", "④‴-a")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("④‴-a 슬롯 링크를 거부하지 않았다 — %s" % env)
        if not meta_exists("740", "dock"):
            P("★④‴-a 남의 게임(740)의 dock meta가 지워졌다 — 슬롯 링크를 따라간 실피해")
        if not body_exists("740", "dock"):
            P("★④‴-a 남의 게임(740)의 dock 본체가 사라졌다")
        drop_link(store.profile_dir("730", "dock"))

        #    (b) internal 슬롯 → **데이터 루트 밖** (대칭 확인)
        mkgame(tmp, engine, store, "750", "SlotLinkOutside")
        out_slot = tmp / "outside-slot"
        out_slot.mkdir(parents=True, exist_ok=True)
        (out_slot / "meta.json").write_text('{"filename":"video.ini","sha1":"z"}')
        (out_slot / "video.ini").write_bytes(DOCK)
        (out_slot / "unrelated.txt").write_bytes(b"unrelated\n")
        shutil.rmtree(store.profile_dir("750", "internal"))
        os.symlink(str(out_slot), store.profile_dir("750", "internal"))
        env = delete_escape("750", "④‴-b")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("④‴-b internal 슬롯 링크를 거부하지 않았다 — %s" % env)
        left = sorted(os.listdir(out_slot)) if out_slot.is_dir() else "디렉터리 자체가 사라짐"
        if left != ["meta.json", "unrelated.txt", "video.ini"]:
            P("★④‴-b 데이터 루트 **밖** 파일이 지워졌다 — %s" % (left,))
        drop_link(store.profile_dir("750", "internal"))

        # ═══════════════════════════════════════════════════════════════════
        # ⑦ meta가 손상돼도 **본체는 대피한다** (QA 반려 ② — 이탈 #4의 잠금)
        #    설계 원문대로 meta의 `filename`을 거쳐 본체를 찾으면, meta가 안 읽히는 슬롯은
        #    대피 없이 rmtree된다. 그래서 본체 탐색을 meta에서 뗐다 — 그 선택을 여기서 잠근다.
        # ═══════════════════════════════════════════════════════════════════
        mkgame(tmp, engine, store, "900", "CorruptMetaTarget")
        body900 = os.path.join(store.profile_dir("900", "dock"), "video.ini")
        body_sha = store.sha1_file(body900)
        if not body_sha:
            P("⑦ 사전 조건 실패 — dock 본체 파일을 못 찾았다")
        # meta.json을 **읽을 수 없게** 만든다(비JSON 바이트). load_meta가 ValueError를 던진다.
        with open(store.profile_meta_path("900", "dock"), "wb") as fh:
            fh.write(b"\x00\xff not json at all \x00")
        env = rpc(main, "delete_game", "900", confirm_token=token("900"))
        if not env.get("ok"):
            P("⑦ meta가 손상됐다고 삭제가 실패했다 — 손상 슬롯도 지울 수 있어야 한다 (%s)" % env)
        backed = {store.sha1_file(b) for b in store.list_backups("900")}
        if body_sha not in backed:
            P("★⑦ meta가 손상된 슬롯의 본체가 대피 없이 사라졌다 — 복구 수단이 0이다 "
              "(본체 sha1 %s / 백업 %d건)" % ((body_sha or "")[:10], len(backed)))
        if os.path.exists(store.profiles_root("900")):
            P("⑦ 삭제 성공이라는데 profiles/900이 남았다")

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ last_appid 정리 (그리고 남의 것은 안 건드린다)
        # ═══════════════════════════════════════════════════════════════════
        mkgame(tmp, engine, store, "400", "LastAppidTarget")
        reg = store.load_registry()
        reg["settings"]["last_appid"] = "500"                 # 음성 대조군: 다른 게임을 가리킨다
        store.save_registry(reg)
        env = rpc(main, "delete_game", "400", confirm_token=token("400"))
        if not env.get("ok"):
            P("⑤ 사전 조건 실패 — 400 삭제가 안 됐다 (%s)" % env)
        if store.load_registry()["settings"]["last_appid"] != "500":
            P("⑤ 남의 last_appid를 지웠다 — 삭제 대상과 같을 때만 되돌려야 한다")
        reg = store.load_registry()
        reg["settings"]["last_appid"] = "500"
        store.save_registry(reg)
        env = rpc(main, "delete_game", "500", confirm_token=token("500"))
        if not env.get("ok"):
            P("⑤ 사전 조건 실패 — 500 삭제가 안 됐다 (%s)" % env)
        if store.load_registry()["settings"]["last_appid"] is not None:
            P("★⑤ 삭제한 게임을 last_appid가 계속 가리킨다 — 등록 목록에 없는 appid를 가리키는 상태")

        # ═══════════════════════════════════════════════════════════════════
        # ⑧ Codex sol high 독립 QA가 잡은 4건 (2026-08-09) — 고친 것을 잠근다
        #    (반려 ②의 교훈: 방어 코드만 있고 잠그는 테스트가 없으면 되돌려도 안 잡힌다)
        # ═══════════════════════════════════════════════════════════════════
        # ⑧-a (#1 치명) backups/<appid>가 외부 디렉터리 링크 → 대피(make_backup→prune)가
        #    링크 너머를 열거해 초과분을 unlink. 0단계 _paths_in_position이 backups까지 봐야 막힌다.
        mkgame(tmp, engine, store, "810", "BkLinkTarget")
        bk_victim = tmp / "bk-victim-810"
        bk_victim.mkdir()
        for i in range(12):                                    # BACKUP_KEEP(10) 초과 → prune 대상
            (bk_victim / ("outside-%02d.txt" % i)).write_text("사용자 파일 %d" % i)
        os.makedirs(os.path.dirname(store.backups_dir("810")), exist_ok=True)
        os.symlink(str(bk_victim), store.backups_dir("810"))
        env = delete_escape("810", "⑧-a")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("⑧-a backups 디렉터리 링크를 거부하지 않았다 — %s" % env)
        if len(os.listdir(bk_victim)) != 12:
            P("★⑧-a backups 링크로 데이터 루트 밖 파일이 지워졌다 (남은 %d/12)"
              % len(os.listdir(bk_victim)))
        drop_link(store.backups_dir("810"))

        # ⑧-b (#3 높음) 슬롯 **안의 비점 파일**이 외부 파일 링크 → isfile→read_bytes가 링크를
        #    따라가 외부 파일을 백업에 복사. ".sav를 열지도 않는다" 경계가 깨진다.
        mkgame(tmp, engine, store, "820", "SlotSubFileLink")
        secret = tmp / "SECRET-820.sav"
        secret.write_bytes(b"USER-SAVE-SECRET\n" * 200)
        os.symlink(str(secret), os.path.join(store.profile_dir("820", "dock"), "leak.bin"))
        env = delete_escape("820", "⑧-b")
        if code_of(env) != codes.DELETE_FAILED or (env.get("params") or {}).get("stage") != "escape":
            P("⑧-b 슬롯 하위 파일 링크를 거부하지 않았다 — %s" % env)
        secret_sha = store.sha1_bytes(secret.read_bytes())
        if any(store.sha1_file(b) == secret_sha for b in store.list_backups("820")):
            P("★⑧-b 슬롯 하위 파일 링크로 외부 파일(SECRET)이 백업에 복사됐다 — 경계 붕괴")
        drop_link(os.path.join(store.profile_dir("820", "dock"), "leak.bin"))

        # ⑧-c (#5 중간) 유효 JSON이지만 비객체(`"text"`)인 meta → `.get()` AttributeError가
        #    토큰 발급 전 UNEXPECTED로 새어 게임 하나가 삭제 불가 + 그 하나 때문에 reset도 봉쇄.
        #    비객체 meta를 손상(부재)으로 접으면 정상 흐름(CONFIRM_REQUIRED)이 된다.
        mkgame(tmp, engine, store, "830", "NonDictMeta")
        mkgame(tmp, engine, store, "840", "ResetBystander")    # reset 봉쇄 확인용 방관자
        with open(store.profile_meta_path("830", "dock"), "w", encoding="utf-8") as fh:
            fh.write('"just a string, valid json but not an object"')
        env = rpc(main, "delete_game", "830")                  # 무토큰 → CONFIRM_REQUIRED가 정상
        if code_of(env) != codes.CONFIRM_REQUIRED:
            P("★⑧-c 비객체 JSON meta가 개별 삭제를 봉쇄했다 (기대 CONFIRM_REQUIRED, 실제 %s)"
              % code_of(env))
        env = rpc(main, "reset_all")                           # 무토큰 → CONFIRM_REQUIRED가 정상
        if code_of(env) != codes.CONFIRM_REQUIRED:
            P("★⑧-c 비객체 JSON meta 하나가 전체 초기화 확인창을 봉쇄했다 (실제 %s)" % code_of(env))

        # ⑧-d 확인창을 연 사이 상태가 바뀌면 **낡은 삭제 토큰이 거부돼야 한다.**
        #
        #    ★★ [2026-08-15 R14 #8 재작성] 예전 픽스처는 **재저장 한 번으로 두 신호(meta 파일
        #      sha · 백업 개수)를 동시에** 움직였다. 그러면 구현에서 meta sha 신호를 빼고 개수만
        #      남겨도 이 절이 통과한다 — *두 신호를 함께 재는 검사는 어느 쪽도 잠그지 못한다.*
        #      게다가 그 픽스처는 슬롯 본체를 손으로 깨뜨려 만들었다(정상 API 밖).
        #    ★ 지금은 **신호를 하나씩만 움직이는 세 갈래**를 정상 API로 만든다. 각 갈래는 다른
        #      신호에 눈감은 구현에서 **혼자 FAIL한다**(변이 검증 완료 — 아래 주석):
        #        -1 슬롯 meta 신호  : 빈 슬롯에 저장 → 링·개수 불변, meta만 바뀜
        #        -2 백업 개수 신호  : 포화 전 링에서 적용 → meta 불변, 개수 +1
        #        -3 **링 순서 신호** : 포화 링에서 적용 → 개수 10 불변·meta 불변, **대상만 교체**
        #      -3이 R14 #2가 잡은 자리다: 확인창은 *"이 백업이 지워집니다"*라고 이름을 대는데
        #      개수·meta는 하나도 안 움직여 예전 지문으로는 **낡은 토큰이 그대로 통과**했다.
        cfg850 = mkgame(tmp, engine, store, "850", "TokenSignals", internal=False)

        def metas850():
            return [store.sha1_file(store.profile_meta_path("850", p)) for p in ("dock", "internal")]

        def ring850():
            return [os.path.basename(p) for p in store.list_backups("850")]

        def resave(data):
            """정상 저장 한 번 — 직전 본체가 대피본으로 링에 들어간다(백업 +1)."""
            cfg850.write_bytes(data)
            reg_ = store.load_registry()
            engine.save_profile(reg_, "850", "dock")
            store.save_registry(reg_)

        def reapply(data):
            """정상 적용 한 번 — 디스크가 두 슬롯 어느 것과도 달라 **대피본 1건**이 생긴다.
            슬롯 meta는 한 바이트도 안 바뀐다(적용은 슬롯을 쓰지 않는다 — A11)."""
            cfg850.write_bytes(data)
            reg_ = store.load_registry()
            engine.apply_profile(reg_, "850", "dock")
            store.save_registry(reg_)

        for i in range(3):                                     # 링을 3건까지 채운다(포화 전)
            resave(b"quality=r%02d\nshadows=high\nsource=RESAVE-%02d\n" % (i, i))

        # -1 **슬롯 meta 신호만** 움직인다: 빈 슬롯(internal) 첫 저장은 대피가 없다(링 불변).
        tok = token("850")
        fp_before, ring_before = main.remove.delete_fingerprint("850"), ring850()
        reg = store.load_registry()
        engine.save_profile(reg, "850", "internal")            # 빈 슬롯 → 백업 0건
        store.save_registry(reg)
        if ring850() != ring_before:
            P("⑧-d-1 계측기 무효 — 빈 슬롯 저장이 백업 링을 움직였다(%s → %s). 그러면 이 갈래가 "
              "meta 신호를 혼자 재지 못한다" % (ring_before, ring850()))
        if main.remove.delete_fingerprint("850") == fp_before:
            P("★⑧-d-1 슬롯이 새로 저장됐는데 지문이 그대로다 — 낡은 토큰이 통과한다(meta 신호 부재)")
        env = rpc(main, "delete_game", "850", confirm_token=tok)
        if not is_confirm(env) or not registered("850"):
            P("★⑧-d-1 빈 슬롯 저장 뒤 낡은 삭제 토큰이 통과했다 (%s)" % env)
        if not registered("850"):
            return finish()          # 토큰이 통과해 게임이 사라졌다 — 다음 갈래는 잴 대상이 없다

        # -2 **백업 개수 신호만** 움직인다: 포화 전 링에서 적용 → +1, 슬롯 meta는 불변.
        tok = token("850")
        fp_before, metas_before, n_before = main.remove.delete_fingerprint("850"), metas850(), nbackups("850")
        reapply(b"quality=t1__\nshadows=mid_\nsource=THIRD-STATE-1\n")
        if metas850() != metas_before:
            P("⑧-d-2 계측기 무효 — 적용이 슬롯 meta를 바꿨다. 그러면 이 갈래가 개수 신호를 "
              "혼자 재지 못한다")
        if nbackups("850") != n_before + 1:
            P("⑧-d-2 계측기 무효 — 적용이 백업을 1건 늘리지 않았다 (%d → %d)"
              % (n_before, nbackups("850")))
        if main.remove.delete_fingerprint("850") == fp_before:
            P("★⑧-d-2 백업이 1건 늘었는데 지문이 그대로다 — 낡은 토큰이 통과한다(개수 신호 부재)")
        env = rpc(main, "delete_game", "850", confirm_token=tok)
        if not is_confirm(env) or not registered("850"):
            P("★⑧-d-2 백업이 늘어난 뒤 낡은 삭제 토큰이 통과했다 (%s)" % env)
        if not registered("850"):
            return finish()          # 토큰이 통과해 게임이 사라졌다 — 다음 갈래는 잴 대상이 없다

        # -3 **링 순서 신호만** 움직인다: 포화 링에서 적용 → 개수도 meta도 그대로, 대상만 교체.
        while nbackups("850") < store.BACKUP_KEEP:
            reapply(b"quality=f%02d\nshadows=mid_\nsource=RING-FILL-%02d\n"
                    % (nbackups("850"), nbackups("850")))
        tok = token("850")
        fp_before, metas_before, ring_before = (main.remove.delete_fingerprint("850"),
                                                metas850(), ring850())
        reapply(b"quality=t2__\nshadows=mid_\nsource=THIRD-STATE-2\n")
        if nbackups("850") != store.BACKUP_KEEP or metas850() != metas_before:
            P("⑧-d-3 계측기 무효 — 개수(%d)나 meta가 함께 움직였다. 그러면 이 갈래가 링 신호를 "
              "혼자 재지 못한다" % nbackups("850"))
        if ring850() == ring_before:
            P("⑧-d-3 계측기 무효 — 포화 링이 돌지 않았다(%s). 축출이 없으면 잴 것이 없다" % ring_before)
        if main.remove.delete_fingerprint("850") != fp_before:
            P("⑧-d-3 계측기 무효 — 개수·meta 지문이 움직였다. 이 갈래는 **그 둘이 눈감는** 자리를 "
              "재는 것이라, 움직이면 링 신호가 없어도 통과해 버린다")
        if main.restore.ring_fingerprint("850") == main.store.sha1_bytes(
                "\n".join(ring_before).encode("utf-8")):
            P("★⑧-d-3 링이 돌았는데 링 지문이 그대로다 — 승인 대상이 바뀐 것을 잴 방법이 없다")
        env = rpc(main, "delete_game", "850", confirm_token=tok)
        if not is_confirm(env) or not registered("850"):
            P("★⑧-d-3 포화 링이 한 칸 돈 뒤 낡은 삭제 토큰이 통과했다 — 확인창이 이름을 댄 "
              "백업과 **다른 백업**이 지워진다 (%s)" % env)
        if not registered("850"):
            return finish()          # 토큰이 통과해 게임이 사라졌다 — 다음 갈래는 잴 대상이 없다

        # -4 **축출 대상 축만** 움직인다: 슬롯에 본체가 하나 늘면 대피 개수가 커져 **링에서
        #    잘리는 깊이**가 달라진다. meta 파일도, 백업 개수(10)도, 링의 이름 순서도 하나도
        #    안 움직이므로 -1·-2·-3이 잠근 세 신호는 전부 눈감는다 — 여기가 §14-G ⓓ가 말한
        #    자리이고, 승인 목록에 **없던 백업이 지워지는** 방향이다.
        #    (앱 자기 경로로는 본체를 쓰면 meta도 같이 쓰므로 도달하지 않는다 = 외부 쓰기 전제.
        #     그래도 잠그는 이유는 `apply_all`·`reset_all`이 이미 같은 것을 묶고 있어서다.)
        tok = token("850")
        fp_before, metas_before, ring_before = (main.remove.delete_fingerprint("850"),
                                                metas850(), ring850())
        ids_before = [row["backup_id"] for row in main.remove.evict_on_delete("850")]
        extra_body = os.path.join(store.profile_dir("850", "dock"), "extra.ini")
        with open(extra_body, "wb") as fh:                     # 외부가 슬롯에 본체를 하나 넣는다
            fh.write(b"source=EXTRA-BODY\nquality=x___\n")
        ids_after = [row["backup_id"] for row in main.remove.evict_on_delete("850")]
        if metas850() != metas_before or nbackups("850") != store.BACKUP_KEEP:
            P("⑧-d-4 계측기 무효 — 본체 추가가 meta나 백업 개수(%d)를 움직였다. 그러면 이 갈래가 "
              "축출 대상 축을 혼자 재지 못한다" % nbackups("850"))
        if ring850() != ring_before or main.remove.delete_fingerprint("850") != fp_before:
            P("⑧-d-4 계측기 무효 — 링 이름이나 meta·개수 지문이 함께 움직였다. 이 갈래는 **그 셋이 "
              "눈감는** 자리를 재는 것이라, 움직이면 축출 대상 신호가 없어도 통과해 버린다")
        if ids_after == ids_before:
            P("⑧-d-4 계측기 무효 — 본체가 하나 늘었는데 축출 대상이 그대로다(%s). 대피가 링을 더 "
              "깊이 밀어내지 않으면 잴 것이 없다" % ids_before)
        env = rpc(main, "delete_game", "850", confirm_token=tok)
        if not is_confirm(env) or not registered("850"):
            P("★⑧-d-4 축출 대상이 바뀐 뒤 낡은 삭제 토큰이 통과했다 — 확인창이 이름을 대며 "
              "승인받은 목록에 **없던 백업**(%s)이 지워진다 (%s)"
              % ([i for i in ids_after if i not in ids_before], env))
        if not registered("850"):
            return finish()          # 토큰이 통과해 게임이 사라졌다 — 음성 대조군은 잴 대상이 없다

        # -4 **음성 대조군** — 없으면 "항상 거부"도 초록이 된다. 아무것도 안 바꾼 세계에서는
        #    방금 발급한 토큰이 **통과해야** 하고(같은 상태를 두 번 관측해도 지문이 같아야 한다),
        #    그때 삭제는 끝까지 간다. 이 게임은 여기서 사라진다 — 마지막 갈래인 이유다.
        env = rpc(main, "delete_game", "850", confirm_token=token("850"))
        if env.get("ok") is not True or registered("850"):
            P("★⑧-d-4 음성 대조군 실패 — 아무 변조도 없는데 삭제 토큰이 거부됐다. 지문이 관측마다 "
              "달라지면 삭제는 영영 못 하고, 위 단언들은 「항상 거부」로 통과하는 항진식이 된다 (%s)"
              % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⑨ **소스 계약** — `DELETE_FAILED`의 생성점이 공통 helper 하나뿐인가 (DEFECT-06)
        #    위 ①·④·⑧의 사실 필드 단언은 **지금 실행되는 경로만** 잠근다. 새 거부 자리가
        #    helper를 우회해 `raise Refused(code=codes.DELETE_FAILED)`를 직접 쓰면 그 자리는
        #    `profile_delete_started`를 **안 싣고**, 화면은 보수적 폴백으로 부분 삭제 경고를
        #    낸다 — 아무것도 안 지웠는데도. 그 우회는 **동적 검사로는 안 보인다**(그 경로를
        #    아무도 부르지 않으니까). 그래서 소스를 읽어 잠근다.
        #    문법·대상은 `qa/test_codes.py`의 AST 스캔을 따른다(gfxp/*.py 전량 + 접착층 main.py).
        # ═══════════════════════════════════════════════════════════════════
        def delete_failed_raises(path):
            """`code=codes.DELETE_FAILED`를 **직접 던지는** 자리 — (파일, 행, 감싼 함수)."""
            found = []
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            def visit(node, fname):
                for child in ast.iter_child_nodes(node):
                    inner = (child.name
                             if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                             else fname)
                    if isinstance(child, ast.Raise) and isinstance(child.exc, ast.Call):
                        f = child.exc.func
                        nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                        for kw in (child.exc.keywords if nm == "Refused" else []):
                            if (kw.arg == "code"
                                    and isinstance(kw.value, ast.Attribute)
                                    and isinstance(kw.value.value, ast.Name)
                                    and kw.value.value.id == "codes"
                                    and kw.value.attr == "DELETE_FAILED"):
                                found.append((path.name, child.lineno, fname))
                    visit(child, inner)

            visit(tree, "<module>")
            return found

        scanned = sorted((ROOT / "py_modules" / "gfxp").glob("*.py")) + [ROOT / "main.py"]
        sites = [row for path in scanned for row in delete_failed_raises(path)]
        outside = [row for row in sites
                   if row[0] != "remove.py" or row[2] != "_delete_failed"]
        # ★ 음성 대조군 — 스캐너가 아무것도 못 찾으면 아래 단언은 항진식이다.
        if not sites:
            P("★⑨ 계측기 무효 — %d개 파일에서 `codes.DELETE_FAILED` raise를 한 건도 못 찾았다. "
              "스캐너가 죽었으면 이 절은 무엇도 잠그지 못한다" % len(scanned))
        if outside:
            P("★⑨ `DELETE_FAILED`를 공통 helper(`remove._delete_failed`) 밖에서 직접 던진다 — "
              "%s · 그 자리는 profile_delete_started를 안 실어, 아무것도 안 지웠어도 화면이 "
              "부분 삭제 경고를 낸다" % (outside,))

        # ⑨-b helper의 **필수 키워드 인자**가 유지되는가 — 기본값이 생기는 순간 「싣는 것을
        #    잊을 수 있는 자리」가 되살아난다(구조가 아니라 사람 기억에 다시 매달린다).
        sig = inspect.signature(main.remove._delete_failed)
        prm = sig.parameters.get("profile_delete_started")
        if (prm is None or prm.kind is not inspect.Parameter.KEYWORD_ONLY
                or prm.default is not inspect.Parameter.empty):
            P("★⑨-b `_delete_failed`의 profile_delete_started가 **기본값 없는 키워드 전용**이 "
              "아니다 %s — 안 실어도 조용히 통과하는 자리가 생긴다" % (sig,))

        # ⑨-c 화면 쪽 계약 — 사실 필드를 읽는가, 그리고 **`stage`로 갈리지 않는가.**
        #    `stage`는 진단용이다. 같은 `"escape"`를 `restore.py`가 다른 코드
        #    (`BACKUP_OUT_OF_ROOT`)에도 쓰므로, stage 화이트리스트는 **그 코드까지 안전이라**
        #    말하게 된다. 백엔드만 고치고 화면이 안 읽으면 결함은 그대로 남는다.
        #    ⚠️ 주석은 먼저 지운다 — 이 절이 잠그려는 것은 **코드가 무엇을 읽는가**이지 주석이
        #      무엇을 말하는가가 아니다. *"`stage`로 갈리지 않는다"*고 적은 주석이 그 검사에
        #      걸리면, 검사를 통과시키려고 **설명을 지우게** 된다(고칠 곳이 뒤바뀐다).
        #      거친 스트리퍼라 문자열 안의 `//`까지 지울 수 있지만, 여기서는 과삭제가 안전한
        #      방향이다 — 잘못 지우면 「못 찾음」(=FAIL)이 되지 「있는데 통과」가 되지 않는다.
        games_src = (ROOT / "src" / "GamesPopup.tsx").read_text(encoding="utf-8")
        games_src = re.sub(r"/\*.*?\*/", " ", games_src, flags=re.S)
        games_src = re.sub(r"//[^\n]*", " ", games_src)
        for needle in ("profile_delete_started", "DELETE_FAILED_BEFORE_DELETE"):
            if needle not in games_src:
                P("★⑨-c GamesPopup.tsx에 %s가 없다 — 백엔드가 사실을 실어도 화면은 여전히 "
                  "한 문장으로 두 경우를 덮는다" % needle)
        if re.search(r"params\s*\.\s*stage\b", games_src) or 'params["stage"]' in games_src:
            P("★⑨-c GamesPopup.tsx가 `params.stage`로 갈린다 — 진단용 값이 화면 분기 근거가 됐다")

        return finish()
    finally:
        for path in unchmod:
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
