#!/usr/bin/env python3
"""표시명(F11 ①)과 마지막 저장일자(F5) — **표시 계층만 바뀌고 식별자는 불변이다.**

### ★★ 이 파일의 핵심 단언 하나
**표시명을 바꿔도 `dock`/`internal`은 아무 데서도 움직이지 않는다.**
그 식별자는 경로 조각(`profiles/<appid>/dock/`)이자 RPC 인자(`_VALIDATORS["profile"]`)이자
registry 값(`last_applied`)이자 백업 파일명의 tag(`profile_dock`)다. 하나라도 표시명을 따라가면
**저장해 둔 프로필이 통째로 길을 잃는다** — 사용자가 이름 한 번 바꿨다고 프로필이 사라지는 것이
이 기능의 유일한 치명 실패 모드다. 그래서 이름을 바꾼 **뒤에** 실제로 적용·저장·복원 경로를
태워 본다("경로가 있다"와 "동작한다"는 다르다).

### 잠그는 것
  ① **식별자 불변** — 이름 변경 후: 디렉터리·meta 경로 그대로 · **프로필/백업 트리의 파일
     바이트 지문 전량 불변**(2026-08-10 최종 QA 결함 2 — 경로만 보면 본문을 덮는 변이가 통과한다) ·
     registry games/entry 불변 ·
     `apply_all("dock")`·`save_profile(appid,"dock")`이 그대로 동작 · 백업 tag 불변 ·
     바뀐 것은 `settings.profile_names` **하나뿐**(registry 전후 차이를 실제로 대조한다).
  ② 저장·조회 왕복(`set_profile_name` → `get_overview.profile_names`).
  ③ **빈 값·공백만 = 기본값 복귀**(거부가 아니다 — 그것이 "이름 지우기"다).
  ④ 정규화 — 길이 상한 자르기 · 제어문자/개행 제거 · 연속 공백 접기.
     ★ 항진 방지: 입력이 **실제로 상한을 넘었는지**부터 단언한다(안 넘는 입력으로 "잘렸다"를
       재면 아무것도 못 잰다 — 이 프로젝트에서 세 번 난 사고의 형태).
  ⑤ 화면 상수 대조 — `src/limits.ts`의 `PROFILE_NAME_MAX` == `labels.MAX_LEN`.
     (2026-08-07 QA 반려 ①: 화면이 실측과 다른 수를 약속했고 그 약속이 거짓이었다.)
  ⑥ 잘못된 profile 값 → `BAD_IDENTIFIER`(표시명 route도 기존 검증기를 그대로 지난다).
  ⑦ **전체 초기화가 표시명을 되돌린다** + 확인창이 그 사실을 미리 말한다(`named` 개수).
  ⑧ **F5** — `get_overview.saved_at`이 슬롯별로 오고, 저장 후 값이 채워지며, 프로필 없는 슬롯은
     빈 문자열이고, **손상 meta에도 현황이 죽지 않는다**. 표시값은 `YYYY-MM-DD HH:MM` 꼴이다.
  ⑨ i18n 덮어쓰기(프로브) — 이름 하나로 **모든 라벨**이 따라오고, 무관한 키는 안 변한다.
"""
import asyncio
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "i18n_names_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
SAVED_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def tree_sha(root):
    """디렉터리 전체의 `상대경로 → sha1`. **경로 존재가 아니라 내용까지** 잰다.

    ⚠️ 2026-08-10 최종 QA 결함 2: 예전에는 경로 존재·basename 집합만 봤다. 그러면 표시명 변경이
      **기존 백업·프로필의 본문만 덮는** 변이가 통과한다 — "식별자 불변"이라는 이 파일의 핵심
      주장이 실제 측정보다 강했던 것이다. 지금은 바이트까지 대조한다.
    """
    import hashlib
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, root)] = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                out[os.path.relpath(path, root)] = "unreadable"
    return out


def boot(tmp):
    fake = types.ModuleType("decky")
    noop = lambda *a, **k: None                                  # noqa: E731
    fake.logger = types.SimpleNamespace(info=noop, warning=noop, error=noop, debug=noop, log=noop)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():                                                # noqa: C901
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-names-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, labels, store
        problems = []

        def P(msg):
            problems.append(msg)

        def data_of(env):
            return env.get("data") or {}

        def params_of(env):
            return env.get("params") or {}

        def overview():
            env = rpc(main, "get_overview", True)
            if not env.get("ok"):
                P("get_overview가 실패했다 — %s" % env)
                return {}, {}
            payload = data_of(env)
            return {g["appid"]: g for g in payload.get("games", [])}, payload.get("profile_names", {})

        # 합성 게임 — 실제 저장 경로를 태운다
        reg = store.load_registry()
        cfg = tmp / "game100" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(DOCK)
        engine.add_game(reg, "100", str(cfg), name="Alpha")
        engine.save_profile(reg, "100", "dock")
        cfg.write_bytes(INTERNAL)
        engine.save_profile(reg, "100", "internal")
        cfg.write_bytes(DOCK)
        engine.apply_profile(reg, "100", "dock")       # last_applied="dock" 기록
        # internal 프로필이 없는 게임(F5의 빈 슬롯 표시 확인용 — 실물: ACE 3058630은 dock만)
        cfg2 = tmp / "game200" / "video.ini"
        cfg2.parent.mkdir(parents=True, exist_ok=True)
        cfg2.write_bytes(DOCK)
        engine.add_game(reg, "200", str(cfg2), name="Beta")
        engine.save_profile(reg, "200", "dock")
        store.save_registry(reg)

        # ═══════════════════════════════════════════════════════════════════
        # ⑧ F5 — 마지막 저장일자
        # ═══════════════════════════════════════════════════════════════════
        games, _names = overview()
        if not games:
            return finish_early(tmp, problems)
        g100 = games.get("100") or {}
        if "saved_at" not in g100:
            P("★⑧ get_overview에 saved_at이 없다 — F5를 그릴 수 없다")
        else:
            for slot in ("dock", "internal"):
                value = g100["saved_at"].get(slot)
                if not value:
                    P("⑧ 저장한 슬롯(%s)의 saved_at이 비어 있다" % slot)
                elif not SAVED_RE.match(value):
                    P("⑧ saved_at 표시값 형식이 다르다(%r) — 화면이 원문 ISO를 그대로 보인다" % value)
        g200 = games.get("200") or {}
        if (g200.get("saved_at") or {}).get("internal"):
            P("⑧ 저장한 적 없는 슬롯에 saved_at이 있다 — 없는 사실을 말한다")
        if g200.get("has_internal"):
            P("⑧ 사전 조건 실패 — 200의 internal이 없다고 나와야 한다")
        # 손상 meta에도 현황이 죽지 않는다(비객체 JSON — 2026-08-09 조사와 같은 버그 클래스)
        with open(store.profile_meta_path("200", "dock"), "w", encoding="utf-8") as fh:
            fh.write('"valid json but not an object"')
        games2, _ = overview()
        if not games2:
            P("★⑧ 손상 meta 하나로 현황이 통째로 죽었다")
        elif (games2.get("200") or {}).get("has_dock"):
            P("⑧ 손상 meta 슬롯이 적용 가능으로 집계됐다 — 라벨이 거짓말을 한다")
        # 되돌린다(뒤 절이 이 게임을 정상 상태로 쓴다).
        # ⚠️ 손상 meta 위에 그대로 저장하면 **엔진이 터진다**(fence 동작 — `old.get`).
        #   meta를 지우고 "빈 슬롯 첫 저장"으로 되돌린다.
        os.unlink(store.profile_meta_path("200", "dock"))
        reg = store.load_registry()
        engine.save_profile(reg, "200", "dock")
        store.save_registry(reg)

        # ═══════════════════════════════════════════════════════════════════
        # ① 식별자 불변 — **이 파일의 핵심**
        # ═══════════════════════════════════════════════════════════════════
        before_reg = copy.deepcopy(store.load_registry())
        dock_dir = store.profile_dir("100", "dock")
        dock_meta = store.profile_meta_path("100", "dock")
        backups_before = {os.path.basename(p) for p in store.list_backups("100")}
        # ★ 경로가 아니라 **내용**을 떠 둔다(결함 2). 프로필 본체·meta·백업 전량이 대상이다.
        profiles_root = os.path.join(store.data_dir(), "profiles")
        backups_root = os.path.join(store.data_dir(), "backups")
        profiles_sha_before = tree_sha(profiles_root)
        backups_sha_before = tree_sha(backups_root)
        if not profiles_sha_before or not backups_sha_before:
            P("★① 사전 조건 실패 — 지문을 뜰 프로필/백업이 없다(아무것도 못 잰다)")
        if not os.path.isdir(dock_dir) or not os.path.exists(dock_meta):
            P("★① 사전 조건 실패 — 이름 변경 전에 이미 dock 경로가 없다")

        env = rpc(main, "set_profile_name", "dock", "거실 TV")
        if not env.get("ok"):
            P("★① 표시명 변경이 실패했다 — %s" % env)
        if data_of(env).get("profile_names", {}).get("dock") != "거실 TV":
            P("① 변경 결과가 되돌아오지 않았다 — %s" % env)

        if not os.path.isdir(dock_dir) or not os.path.exists(dock_meta):
            P("★★① 표시명을 바꿨더니 **프로필 디렉터리/메타가 사라졌다** — 식별자가 표시명을 따라갔다")
        if {os.path.basename(p) for p in store.list_backups("100")} != backups_before:
            P("★★① 표시명 변경이 백업 파일명을 건드렸다 — tag(`profile_dock`)는 식별자다")
        # ★ 파일 **내용**까지 그대로인가(결함 2) — 이름만 남기고 본문을 덮는 변이를 잡는다.
        prof_diff = sorted(k for k in set(profiles_sha_before) | set(tree_sha(profiles_root))
                           if profiles_sha_before.get(k) != tree_sha(profiles_root).get(k))
        bk_diff = sorted(k for k in set(backups_sha_before) | set(tree_sha(backups_root))
                         if backups_sha_before.get(k) != tree_sha(backups_root).get(k))
        if prof_diff:
            P("★★① 표시명 변경이 **프로필 파일 내용**을 바꿨다 — %s" % prof_diff[:5])
        if bk_diff:
            P("★★① 표시명 변경이 **백업 파일 내용**을 바꿨다 — %s" % bk_diff[:5])
        after_reg = store.load_registry()
        if after_reg["games"] != before_reg["games"]:
            P("★★① 표시명 변경이 registry의 games를 건드렸다")
        if (after_reg["games"].get("100") or {}).get("last_applied") != "dock":
            P("★★① last_applied가 표시명으로 바뀌었다 — 그 값은 식별자다")
        # 바뀐 것이 **settings.profile_names 하나뿐**인지 실제로 대조한다
        diff_a, diff_b = copy.deepcopy(before_reg), copy.deepcopy(after_reg)
        diff_a.get("settings", {}).pop(labels.SETTINGS_KEY, None)
        diff_b.get("settings", {}).pop(labels.SETTINGS_KEY, None)
        if diff_a != diff_b:
            P("★① registry에서 표시명 말고 다른 것도 바뀌었다")

        # 이름을 바꾼 **뒤에** 실제 경로를 태운다 — "있다"와 "동작한다"는 다르다
        env = rpc(main, "apply_all", "dock")                    # 1차 = 미리보기(토큰)
        token = params_of(env).get("confirm_token")
        env = rpc(main, "apply_all", "dock", confirm_token=token)
        if not env.get("ok"):
            P("★① 이름을 바꾼 뒤 일괄 적용이 실패했다 — %s" % env)
        outcomes = {r["appid"]: r["outcome"] for r in data_of(env).get("results", [])}
        if outcomes.get("100") not in ("applied", "already"):
            P("★① 이름을 바꾼 뒤 dock 적용이 안 됐다 — %s" % outcomes)
        cfg.write_bytes(INTERNAL)                              # 덮어쓰기 상황을 만든다
        env = rpc(main, "save_profile", "100", "dock")
        if env.get("code") == codes.CONFIRM_REQUIRED:
            env = rpc(main, "save_profile", "100", "dock",
                      confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("★① 이름을 바꾼 뒤 dock 저장이 실패했다 — %s" % env)
        if not os.path.exists(dock_meta):
            P("★★① 저장 뒤 dock meta 경로가 다른 곳으로 갔다")

        # ② 조회 왕복
        _games, names = overview()
        if names.get("dock") != "거실 TV" or names.get("internal") != "":
            P("② get_overview의 profile_names가 다르다 — %s" % names)

        # ═══════════════════════════════════════════════════════════════════
        # ④ 정규화 (항진 방지: 입력이 실제로 상한을 넘는지부터 단언)
        # ═══════════════════════════════════════════════════════════════════
        long_name = "가" * (labels.MAX_LEN + 7)
        if len(long_name) <= labels.MAX_LEN:
            P("④ 음성 대조군 무효 — 시험 입력이 상한을 넘지 않는다(아무것도 못 잰다)")
        env = rpc(main, "set_profile_name", "internal", long_name)
        stored_name = data_of(env).get("profile_names", {}).get("internal", "")
        if len(stored_name) != labels.MAX_LEN:
            P("★④ 상한(%d)을 넘긴 이름이 %d자로 저장됐다 — 화면이 깨진다"
              % (labels.MAX_LEN, len(stored_name)))
        env = rpc(main, "set_profile_name", "internal", "  내장\n\tGPU   화면  ")
        stored_name = data_of(env).get("profile_names", {}).get("internal", "")
        if stored_name != "내장 GPU 화면":
            P("★④ 제어문자·연속 공백이 정리되지 않았다 — %r" % stored_name)

        # ③ 빈 값·공백만 = 기본값 복귀
        env = rpc(main, "set_profile_name", "internal", "   ")
        if data_of(env).get("profile_names", {}).get("internal") != "":
            P("★③ 공백만 입력이 기본값으로 되돌아가지 않았다 — %s" % env)
        env = rpc(main, "set_profile_name", "internal")          # 인자 생략도 같다
        if data_of(env).get("profile_names", {}).get("internal") != "":
            P("③ 이름 없이 부른 호출이 기본값 복귀가 아니다 — %s" % env)
        settings = store.load_registry().get("settings", {})
        if labels.SETTINGS_KEY in settings and settings[labels.SETTINGS_KEY].get("internal"):
            P("③ 기본값 복귀인데 설정이 남아 있다 — %s" % settings.get(labels.SETTINGS_KEY))

        # ⑥ 잘못된 profile 값은 기존 검증기가 막는다
        env = rpc(main, "set_profile_name", "../../etc", "x")
        if env.get("code") != codes.BAD_IDENTIFIER:
            P("⑥ 잘못된 profile 값이 BAD_IDENTIFIER로 거부되지 않았다 — %s" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⑦ 전체 초기화가 표시명을 되돌린다 + 확인창이 미리 말한다
        # ═══════════════════════════════════════════════════════════════════
        rpc(main, "set_profile_name", "dock", "거실 TV")
        rpc(main, "set_profile_name", "internal", "손안에")
        env = rpc(main, "reset_all")                             # 무토큰 → 확인창 params
        if params_of(env).get("named") != 2:
            P("★⑦ 확인창이 표시명 초기화를 말하지 않는다(named=%s) — 모르고 잃는다"
              % params_of(env).get("named"))
        env = rpc(main, "reset_all", confirm_token=params_of(env).get("confirm_token"),
                  confirm_text=main._RESET_CHALLENGE)
        if not env.get("ok"):
            P("⑦ 전체 초기화가 실패했다 — %s" % env)
        if labels.stored(store.load_registry()) != {"dock": "", "internal": ""}:
            P("★⑦ 전체 초기화 뒤에도 표시명이 남았다 — 확인창이 말한 것과 실제가 다르다")

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ 화면 상수 대조 — 문구가 약속하는 수 == 백엔드가 강제하는 수
        # ═══════════════════════════════════════════════════════════════════
        limits = (ROOT / "src" / "limits.ts").read_text(encoding="utf-8")
        m = re.search(r"PROFILE_NAME_MAX\s*=\s*(\d+)", limits)
        if not m:
            P("⑤ src/limits.ts에서 PROFILE_NAME_MAX를 못 찾았다 — 화면 문구의 근거가 없다")
        elif int(m.group(1)) != labels.MAX_LEN:
            P("★⑤ 화면 상수(%s)와 백엔드 상한(%d)이 다르다 — 화면이 지키지 못할 약속을 한다"
              % (m.group(1), labels.MAX_LEN))

        # ═══════════════════════════════════════════════════════════════════
        # ⑨ i18n 덮어쓰기 — 이름 하나로 모든 라벨이 따라오는가
        # ═══════════════════════════════════════════════════════════════════
        if not U1.is_file():
            P("⑨ 툴체인 node가 없어 i18n 덮어쓰기를 재지 못했다 — 판정 불가는 통과가 아니다")
        else:
            proc = subprocess.run([str(U1), str(PROBE)], capture_output=True, text=True, cwd=str(ROOT))
            if proc.returncode != 0:
                P("⑨ i18n 프로브가 죽었다 — %s" % (proc.stderr or proc.stdout).strip()[-200:])
            else:
                r = json.loads(proc.stdout.strip().splitlines()[-1])
                if not r["defaultMatchesTable"]:
                    P("⑨ 기본 이름이 번역표와 다르다 — %r" % r["defaultDock"])
                if r["afterDock"] != "거실 TV":
                    P("★⑨ 표시명을 넣었는데 t()가 기본 이름을 돌려준다 — %r" % r["afterDock"])
                if r["afterInternal"] != r["defaultInternal"]:
                    P("⑨ 빈 값을 준 슬롯의 이름까지 바뀌었다 — %r" % r["afterInternal"])
                if r["tDefaultDock"] != r["defaultDock"]:
                    P("⑨ tDefault가 덮어쓰기를 무시하지 않는다 — 편집창이 기본 이름을 못 보여준다")
                for field in ("bulkLabel", "applyShort", "saveShort"):
                    if "거실 TV" not in r[field]:
                        P("★⑨ %s가 옛 이름을 말한다(%r) — 라벨에 이름이 박혀 있다" % (field, r[field]))
                if not r["unrelatedMatchesTable"]:
                    P("★⑨ 무관한 키까지 바뀌었다 — 덮어쓰기의 사정거리가 넓다")
                if r["blankResetsDock"] != r["defaultDock"] or r["nullResetsDock"] != r["defaultDock"]:
                    P("★⑨ 빈 값/누락이 기본 이름으로 되돌아가지 않는다 — 빈 라벨이 화면에 남는다")

        print("표시명·저장일자 — 식별자 불변 · 정규화 4종 · 초기화 · 화면 상수 · i18n 덮어쓰기 "
              "(데이터: %s)" % tmp)
        if problems:
            print("\nFAIL")
            for p in problems:
                print("  " + p)
            return 1
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish_early(tmp, problems):
    print("표시명·저장일자 (데이터: %s)" % tmp)
    print("\nFAIL")
    for p in problems:
        print("  " + p)
    return 1


if __name__ == "__main__":
    sys.exit(main_test())
