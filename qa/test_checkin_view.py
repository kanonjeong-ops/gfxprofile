#!/usr/bin/env python3
"""체크인 관측(F6)의 정확성 — 설계 정본 DESIGN-UX §5-E·§14-A·§15-B ④.

엔진의 체크인(G3)은 *"적용 전에 현재 디스크를 직전 프로필에 되쓰는"* **조용한 덮어쓰기**다
(engine.py:494-519). 화면이 그것을 말하려면 구조 신호가 필요한데 엔진의 신호는 한국어 자유문
`notes[]`뿐이고 프론트의 note 파싱은 금지다 — 그래서 **접착층이 직전 프로필 슬롯의 전후
복합 지문을 대조해 관측한다.** 이 파일은 그 관측이 **실제로 정확한지**를 잠근다.

잠그는 것:
  ⓐ 체크인 발생 → `checked_in`/`checkin[]`이 채워진다 (+ 슬롯이 실제로 바뀌었다)
  ⓑ 건너뜀·불필요 → `null` / 빈 배열
  ⓒ **엔진 note의 "체크인:" 접두와 관측 결과가 동등**하다(엔진은 fence라 문구가 안정적이다 —
     테스트 전용 앵커다. 이 동등성이 관측과 실물 사이의 간극을 감시한다)
  ⓓ `apply_all` 봉투가 **엔진 반환 행을 변형하지 않는다** — `checkin`은 별도 필드다
  ⓔ ★ **실패 주입 3종**(D-02): 체크인이 **일어난 뒤**의 (i) disk 백업 실패 (ii) 설정 파일 쓰기
     실패 (iii) `save_registry` 실패 — 셋 다 **실패 봉투에 `checked_in`이 실린다.**
     성공 경로에만 관측을 두면 *"적용은 실패했는데 프로필은 이미 바뀐"* 상태를 화면이 침묵한다.
     + 체크인 **자체의 대피가 실패**하면(쓰기 미도달) `null`이 정답이다
  ⓔ′★ **부분 쓰기 주입**(N-01): 본체는 바뀌고 **meta 쓰기만 실패**한 상태 —
     meta 단독 지문이었다면 놓쳤을 갈래다. **음성 대조군 2종**(숨김명 `.graphics.ini`류 ·
     일시 파일 접두 실명 `.gfxprofile-tmp-*.ini`류)도 같이 주입한다: 지문에서 그 이름들을
     예외로 빼는 최적화가 되살아나면 이 두 케이스가 FAIL로 잡는다
  ⓕ ★ **손상 `last_applied` 4종**(N-02·D-03 — §14-A 엔진 가드): 절대경로·`../x`·숫자·빈 문자열
     → 체크인 건너뜀 + `checked_in: null` + **표적 경로에 읽기·쓰기 0**
  ⓖ 미리보기 `total` = 발급 시점 games 수, 그리고 **5버킷의 합과 항등**(D-06)

★ 합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`이 tmp라 실사용 데이터에 닿을 수 없다.
"""
import asyncio
import builtins
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
#: 세 벌 다 **줄 수가 같고 크기가 비슷하다** — G4(크기 25~400%, 줄 수 ±20%)에 걸리면
#: 체크인이 일어나지 않아 이 파일의 시나리오 자체가 성립하지 않는다.
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"


def boot(tmp):
    fake = types.ModuleType("decky")
    noop = lambda *a, **k: None                                  # noqa: E731
    fake.logger = types.SimpleNamespace(info=noop, warning=noop, error=noop,
                                        debug=noop, log=noop)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # ← 격리는 이 한 줄이 한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def apply_all(main, profile):
    """2단계 계약을 밟아 실제로 실행한다(미리보기 → 토큰 → 실행)."""
    env = rpc(main, "apply_all", profile)
    return rpc(main, "apply_all", profile,
               confirm_token=(env.get("params") or {}).get("confirm_token"))


#: §14-A 가드 원문. **테스트 전용 앵커**다 — 사라지면 아래 대조가 크래시가 아니라 FAIL이 된다.
GUARD_LINE = '    if previous not in ("dock", "internal"): previous = None'


def load_mutant_engine(tmp):
    """§14-A 가드 **한 줄만 뺀** 엔진 사본을 별도 패키지로 올린다.

    *"정상 값에서는 가드 전후 동작이 바이트 동일"*(설계 §14-A 테스트 명세)은 비교 대상이
    실물로 있어야 잴 수 있다 — 없으면 그 문장은 검사가 아니라 주장이다.
    """
    dst = tmp / "mutant"
    target = dst / "gfxp_mut"
    shutil.copytree(ROOT / "py_modules" / "gfxp", target,
                    ignore=shutil.ignore_patterns("__pycache__"))
    path = target / "engine.py"
    text = path.read_text()
    hit = [line for line in text.splitlines() if line.startswith(GUARD_LINE)]
    if len(hit) != 1:
        return None                       # 앵커 소실 — 호출부가 FAIL로 보고한다
    path.write_text(text.replace(hit[0] + "\n", ""))
    sys.path.insert(0, str(dst))
    import importlib
    return importlib.import_module("gfxp_mut.engine")


class FrozenClock:
    """`store.time`을 감싸 **시각을 얼린다.** 두 경로를 대조할 때 백업 파일명·`saved_at`이
    실행 시각으로 갈리면 "달라졌다"가 아무 의미도 없어진다."""

    def __init__(self, real):
        self._real = real

    def strftime(self, fmt, *a):
        return self._real.strftime(fmt, self._real.localtime(1786000000))

    def __getattr__(self, name):
        return getattr(self._real, name)


def tree_sha(root):
    """디렉터리 하나의 (상대경로 → sha1) 지도. 파일계 대조용."""
    out = {}
    for base, _dirs, files in os.walk(str(root)):
        for name in files:
            full = os.path.join(base, name)
            out[os.path.relpath(full, str(root))] = _sha_of(full)
    return out


def _sha_of(path):
    import hashlib
    digest = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            digest.update(fh.read())
    except OSError:
        return "unreadable"
    return digest.hexdigest()


def mkgame(main, tmp, appid, name, filename="video.ini"):
    """두 프로필을 다 가진 게임 하나. 디스크는 dock 내용으로 끝난다."""
    from gfxp import store
    cfg = tmp / ("game%s" % appid) / filename
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(DOCK)
    reg = store.load_registry()
    main.engine.add_game(reg, appid, str(cfg), name=name)
    main.engine.save_profile(reg, appid, "dock")
    cfg.write_bytes(INTL)
    main.engine.save_profile(reg, appid, "internal")
    cfg.write_bytes(DOCK)
    store.save_registry(reg)
    return cfg


class Patch:
    """`store`의 함수 하나를 갈아끼운다 — **원복을 보장한다**(다음 시나리오가 오염되지 않게)."""

    def __init__(self, store, name, fn):
        self.store, self.name, self.fn = store, name, fn

    def __enter__(self):
        self.real = getattr(self.store, self.name)
        setattr(self.store, self.name, self.fn(self.real))
        return self

    def __exit__(self, *exc):
        setattr(self.store, self.name, self.real)
        return False


class Watch:
    """표적 경로에 **읽기·쓰기가 한 번이라도 닿는지** 본다.

    ⚠️ 재는 범위를 정직하게: 전역 IO를 세지 않는다(`/proc`·`pwd`처럼 정상적으로 루트 밖을 읽는
      경로가 있다). **주입한 표적 디렉터리에 닿는 호출만** 기록한다 — 가드가 없으면 엔진이
      정확히 그곳을 읽고 쓰기 때문에(N-02) 이 좁힌 관측으로 충분하고, 대신 항진식이 되지 않게
      "표적이 실제로 그 경로로 계산되는가"를 시나리오에서 함께 단언한다.
    """

    def __init__(self, targets):
        self.targets = [os.path.realpath(str(t)) for t in targets]
        self.hits = []

    def _note(self, how, path):
        try:
            real = os.path.realpath(str(path))
        except (TypeError, ValueError, OSError):
            return
        for target in self.targets:
            if real == target or real.startswith(target + os.sep):
                self.hits.append((how, real))

    def __enter__(self):
        self._real = (builtins.open, os.makedirs, tempfile.mkstemp, os.listdir)
        builtins.open = lambda path, *a, **k: (self._note("open", path)
                                               or self._real[0](path, *a, **k))
        os.makedirs = lambda path, *a, **k: (self._note("makedirs", path)
                                             or self._real[1](path, *a, **k))
        tempfile.mkstemp = lambda *a, **k: (self._note("mkstemp", k.get("dir", ""))
                                            or self._real[2](*a, **k))
        os.listdir = lambda path=".": (self._note("listdir", path)
                                       or self._real[3](path))
        return self

    def __exit__(self, *exc):
        builtins.open, os.makedirs, tempfile.mkstemp, os.listdir = self._real
        return False


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-checkin-"))
    try:
        main = boot(tmp)
        from gfxp import codes, store
        problems = []

        def P(msg):
            problems.append(msg)

        def meta_sha(appid, profile):
            return store.sha1_file(store.profile_meta_path(appid, profile)) or "absent"

        def body_sha(appid, profile, filename="video.ini"):
            return store.sha1_file(os.path.join(store.profile_dir(appid, profile),
                                                filename)) or "absent"

        seq = [0]

        def prime(appid, cfg, previous="dock"):
            """**체크인이 일어날 조건**을 만든다: 직전 프로필이 있고, 디스크가 어느 프로필과도
            다르다. 여기서 `apply_profile(internal)`을 부르면 엔진이 디스크를 dock에 되쓴다.

            ⚠️ 디스크 내용은 **호출마다 새로** 만든다. 고정 내용을 쓰면 두 번째 시나리오에서
              디스크가 직전 체크인으로 갱신된 dock와 같아져 *"체크인 불필요"*로 빠지고,
              그 순간 이 파일의 주입들이 **아무것도 재지 않으면서 통과**한다(실제로 그랬다).
            """
            seq[0] += 1
            body = b"quality=edit\nshadows=e%03d\nsource=USER-EDITED-\n" % seq[0]
            reg = store.load_registry()
            reg["games"][appid]["last_applied"] = previous
            store.save_registry(reg)
            cfg.write_bytes(body)
            return body

        def note_says_checkin(env):
            notes = ((env.get("data") or {}).get("notes")) or []
            return any(n.startswith("체크인:") for n in notes)

        def equivalence(label, env):
            """ⓒ — 엔진 note와 관측 결과가 같은 것을 말하는가."""
            observed = (env.get("data") or {}).get("checked_in")
            if note_says_checkin(env) != (observed is not None):
                P("★ⓒ %s: 엔진 note와 관측이 어긋난다 — notes=%s checked_in=%r"
                  % (label, (env.get("data") or {}).get("notes"), observed))

        cfg100 = mkgame(main, tmp, "100", "Alpha")

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 건너뜀 — 직전 프로필 기록이 없다
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "apply_profile", "100", "dock")
        if not env.get("ok"):
            P("ⓑ 사전 조건 실패 — 첫 적용이 실패했다 (%s)" % env)
            return finish(tmp, problems)
        if (env.get("data") or {}).get("checked_in") is not None:
            P("★ⓑ 직전 기록이 없는데 체크인이 보고됐다 — %s" % (env.get("data") or {}))
        equivalence("건너뜀", env)

        # ⓑ 불필요 — 디스크가 직전 프로필과 같다
        env = rpc(main, "apply_profile", "100", "internal")
        if (env.get("data") or {}).get("checked_in") is not None:
            P("★ⓑ 디스크가 직전 프로필과 같은데 체크인이 보고됐다 — %s" % (env.get("data") or {}))
        equivalence("불필요", env)

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 체크인 발생 — 관측이 그 사실을 말하고, 슬롯이 실제로 바뀐다
        # ═══════════════════════════════════════════════════════════════════
        edited = prime("100", cfg100)
        before = (meta_sha("100", "dock"), body_sha("100", "dock"))
        env = rpc(main, "apply_profile", "100", "internal")
        if (env.get("data") or {}).get("checked_in") != "dock":
            P("★ⓐ 체크인이 일어났는데 checked_in이 'dock'이 아니다 — %s" % (env.get("data") or {}))
        equivalence("발생", env)
        if before == (meta_sha("100", "dock"), body_sha("100", "dock")):
            P("★ⓐ 계측기 무효 — 체크인이 슬롯을 하나도 안 바꿨다(시나리오가 성립하지 않았다)")
        if store.load_meta("100", "dock").get("sha1") != store.sha1_bytes(edited):
            P("★ⓐ dock 슬롯에 들어간 내용이 디스크의 편집본이 아니다 — 시나리오 오작동")

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ′ ★ 낡은 `.applied` + already → **null** (2026-08-11 P11 게이트 R1 회귀)
        #
        #   엔진은 `.applied` 그림자 사본을 **체크인과 무관하게** 갱신한다(적용 말미
        #   engine.py:545 · already 경로 `_record_already` engine.py:643). 그 파일을 슬롯
        #   지문에 넣으면 「적용 → 같은 슬롯 재저장 → 재적용」이라는 **일상 흐름**에서
        #   note는 "체크인 불필요"인데 관측은 프로필명을 실어 §5-E ⓒ가 깨진다.
        #   ⚠️ 낡히는 것이 핵심이다 — 내용이 같으면 재작성돼도 지문이 안 변해 아무것도 안 잰다.
        # ═══════════════════════════════════════════════════════════════════
        cfg800 = mkgame(main, tmp, "800", "Stale")
        for label, run_apply in (("개별 적용", lambda: rpc(main, "apply_profile", "800", "dock")),
                                 ("일괄 적용", lambda: apply_all(main, "dock"))):
            env = rpc(main, "apply_profile", "800", "dock")          # .applied 생성
            if not env.get("ok"):
                P("ⓐ′ %s 사전 조건 실패 — 첫 적용 (%s)" % (label, env))
                continue
            shadow = os.path.join(store.profile_dir("800", "dock"), ".applied")
            before_shadow = _sha_of(shadow)
            cfg800.write_bytes(b"quality=dock\nshadows=m%03d\nsource=DOCK-PROFILE\n" % seq[0])
            seq[0] += 1
            reg = store.load_registry()
            main.engine.save_profile(reg, "800", "dock")             # 본체·meta만 갱신 = .applied 낡음
            store.save_registry(reg)
            if _sha_of(shadow) != before_shadow:
                P("ⓐ′ %s 사전 조건 실패 — 재저장이 .applied를 건드렸다" % label)
            env = run_apply()
            data = env.get("data") or {}
            observed = data.get("checked_in") if label == "개별 적용" else data.get("checkin")
            if observed not in (None, []):
                P("★ⓐ′ %s: 체크인이 없는데 관측이 보고했다(%r) — `.applied` 갱신을 체크인으로 "
                  "오인한다(§5-E ⓒ 위반, 일상 흐름에서 상시 발생)" % (label, observed))
            if _sha_of(shadow) == before_shadow:
                P("ⓐ′ %s: 계측기 무효 — .applied가 갱신되지 않아 아무것도 재지 않았다" % label)
            if label == "개별 적용":
                equivalence("낡은 .applied + already", env)

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ″ ★ `backups/`만 링크인 **정상 게임**의 체크인은 보고돼야 한다
        #      (P11 게이트 R2 — 넓은 술어로 접으면 실제 체크인이 **침묵**한다)
        # ═══════════════════════════════════════════════════════════════════
        cfg900 = mkgame(main, tmp, "900", "LinkedBackups")
        outside_bk = tmp / "backups-elsewhere"
        outside_bk.mkdir(parents=True, exist_ok=True)
        bk_dir = pathlib.Path(store.backups_dir("900"))
        shutil.rmtree(bk_dir, ignore_errors=True)
        bk_dir.symlink_to(outside_bk, target_is_directory=True)
        if main.remove._paths_in_position("900") or not main.remove.slot_in_position("900", "dock"):
            P("ⓐ″ 사전 조건 실패 — 넓은 술어는 거짓, 좁은 술어는 참이어야 한다(주입 실패)")
        prime("900", cfg900)
        env = rpc(main, "apply_profile", "900", "internal")
        if (env.get("data") or {}).get("checked_in") != "dock":
            P("★ⓐ″ backups만 링크인 정상 게임의 체크인이 **침묵했다**(%r) — 술어가 관측이 읽지도 "
              "않는 경로까지 요구한다(§5-E '잔여 한계는 과보고 방향뿐' 위반)"
              % (env.get("data") or {}).get("checked_in"))
        equivalence("backups 링크", env)

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ apply_all — 엔진 반환 행 무변형 + checkin은 별도 필드
        # ═══════════════════════════════════════════════════════════════════
        cfg200 = mkgame(main, tmp, "200", "Beta")
        prime("100", cfg100)
        prime("200", cfg200)
        env = rpc(main, "apply_all", "internal")
        token = (env.get("params") or {}).get("confirm_token")
        env = rpc(main, "apply_all", "internal", confirm_token=token)
        data = env.get("data") or {}
        if not env.get("ok"):
            P("ⓓ 사전 조건 실패 — 일괄 적용 2차 호출이 실패했다 (%s)" % env)
        rows = data.get("results") or []
        for row in rows:
            if set(row) != {"appid", "name", "outcome", "code", "note"}:
                P("★ⓓ 결과 행이 엔진 반환 모양과 다르다 — 접착층이 행을 변형했다 (%s)" % sorted(row))
        checkin = data.get("checkin")
        if [r["appid"] for r in checkin or []] != ["100", "200"]:
            P("★ⓓ 일괄 적용의 checkin이 체크인된 두 게임을 안 싣는다 — %s" % checkin)
        for row in checkin or []:
            if set(row) != {"appid", "name", "profile"} or row["profile"] != "dock":
                P("ⓓ checkin 행의 모양이 계약과 다르다 — %s" % row)
        # 체크인이 없을 때는 빈 배열이다(없는 사실을 만들지 않는다)
        env = apply_all(main, "internal")
        if (env.get("data") or {}).get("checkin") != []:
            P("★ⓓ 체크인이 없는 일괄 적용에 checkin이 실렸다 — %s" % (env.get("data") or {}))

        # ⓓ″ ★ `checkin[].name`은 **항상 str**이다(D-08). 손상·수동 편집된 registry의 `name`은
        #      숫자일 수 있고, 그대로 실으면 봉투 계약(`name: string`)이 조용히 깨진다.
        reg = store.load_registry()
        reg["games"]["100"]["name"] = 12345
        store.save_registry(reg)
        prime("100", cfg100)
        env = apply_all(main, "internal")
        row = next((r for r in (env.get("data") or {}).get("checkin") or []
                    if r["appid"] == "100"), None)
        if row is None:
            P("ⓓ″ 사전 조건 실패 — 체크인이 안 일어나 이름을 잴 수 없다 (%s)" % (env.get("data") or {}))
        elif not isinstance(row.get("name"), str):
            P("★ⓓ″ checkin[].name이 str이 아니다(%r) — 봉투 계약(name: string) 위반" % row.get("name"))
        reg = store.load_registry()
        reg["games"]["100"]["name"] = "Alpha"
        store.save_registry(reg)

        # ⓓ′ ★ 일괄 적용의 **실패 봉투**에도 checkin이 실린다(개별 적용과 같은 계약)
        prime("100", cfg100)
        env = rpc(main, "apply_all", "internal")
        token = (env.get("params") or {}).get("confirm_token")
        with Patch(store, "save_registry",
                   lambda real: (lambda reg: (_ for _ in ()).throw(OSError("주입: 저장 실패")))):
            env = rpc(main, "apply_all", "internal", confirm_token=token)
        if env.get("ok") is not False or env.get("code") != codes.UNEXPECTED:
            P("★ⓓ′ save_registry 실패를 주입했는데 봉투가 실패가 아니다 — %s" % env)
        rows = (env.get("params") or {}).get("checkin")
        if [r["appid"] for r in rows or []] != ["100"]:
            P("★ⓓ′ 일괄 적용 실패 봉투에 checkin이 없다(%s) — 「적용은 실패했는데 프로필은 "
              "이미 바뀐」 상태를 화면이 침묵한다" % rows)

        # ═══════════════════════════════════════════════════════════════════
        # ⓖ 미리보기 total — 발급 시점 스냅샷 + 5버킷 합과 항등 (D-06)
        # ═══════════════════════════════════════════════════════════════════
        from gfxp import confirm as confirm_mod
        for step in (0, 1):
            if step:
                mkgame(main, tmp, "300", "Gamma")      # 등록이 늘면 스냅샷도 따라간다
            # ★ 기대값은 **실물 registry에서 센다** — 상수로 박으면 앞 절이 게임을 하나 더
            #   만드는 순간 이 절이 아무것도 안 재면서 FAIL/PASS가 뒤집힌다(실제로 겪었다).
            expected = len(store.load_registry()["games"])
            params = (rpc(main, "apply_all", "dock").get("params") or {})
            if params.get("total") != expected:
                P("★ⓖ 미리보기 total이 등록 수와 다르다 — %s (기대 %d)"
                  % (params.get("total"), expected))
            bucket_sum = sum(params.get(b, 0) for b in confirm_mod.APPLY_BUCKETS)
            if bucket_sum != params.get("total"):
                P("★ⓖ 5버킷의 합(%s)이 total(%s)과 다르다 — 확인창 본문이 거짓을 말한다"
                  % (bucket_sum, params.get("total")))

        # ═══════════════════════════════════════════════════════════════════
        # ⓔ 실패 주입 — 체크인이 **일어난 뒤**의 실패 3종 + 대피 실패 1종
        # ═══════════════════════════════════════════════════════════════════
        def inject(label, patch_name, patch_factory, expect_code, expect_checked_in):
            prime("100", cfg100)
            before_meta = meta_sha("100", "dock")
            with Patch(store, patch_name, patch_factory):
                env = rpc(main, "apply_profile", "100", "internal")
            if env.get("ok") is not False:
                P("★ⓔ %s: 주입했는데 성공했다 — 주입이 안 먹었다 (%s)" % (label, env))
                return
            if expect_code and env.get("code") != expect_code:
                P("ⓔ %s: code가 %s가 아니다 — %s" % (label, expect_code, env.get("code")))
            got = (env.get("params") or {}).get("checked_in")
            if got != expect_checked_in:
                P("★ⓔ %s: 실패 봉투의 checked_in이 %r이어야 하는데 %r다 — "
                  "「적용은 실패했는데 프로필은 이미 바뀐」 상태를 화면이 침묵한다"
                  % (label, expect_checked_in, got))
            changed = meta_sha("100", "dock") != before_meta
            if changed != (expect_checked_in is not None):
                P("ⓔ %s: 슬롯 변화(%s)와 기대(%s)가 어긋난다 — 주입 지점이 설계와 다르다"
                  % (label, changed, expect_checked_in is not None))

        def fail_backup(tag_prefix):
            def factory(real):
                def fake(appid, data, tag, filename):
                    if tag.startswith(tag_prefix):
                        raise OSError("주입: 백업 실패 (%s)" % tag)
                    return real(appid, data, tag, filename)
                return fake
            return factory

        def fail_write(match):
            def factory(real):
                def fake(path, data, mode=None, owner=None):
                    if match(str(path)):
                        raise OSError("주입: 쓰기 실패 (%s)" % path)
                    return real(path, data, mode, owner)
                return fake
            return factory

        # (i) 체크인 뒤 disk 백업 실패 → BACKUP_FAILED인데 프로필은 이미 바뀌었다
        inject("(i) disk 백업 실패", "make_backup", fail_backup("disk"),
               codes.BACKUP_FAILED, "dock")
        # (ii) 체크인 뒤 설정 파일 쓰기 실패
        inject("(ii) 설정 파일 쓰기 실패", "atomic_write",
               fail_write(lambda p: p == str(cfg100)), codes.UNEXPECTED, "dock")
        # (iii) 체크인 뒤 save_registry 실패
        inject("(iii) save_registry 실패", "save_registry",
               lambda real: (lambda reg: (_ for _ in ()).throw(OSError("주입: 저장 실패"))),
               codes.UNEXPECTED, "dock")
        # 체크인 **자체의 대피** 실패 → 쓰기 미도달 → null이 정답이다
        inject("(iv) 체크인 대피 실패", "make_backup", fail_backup("profile_"),
               codes.UNEXPECTED, None)

        # ═══════════════════════════════════════════════════════════════════
        # ⓔ′ 부분 쓰기 — 본체는 바뀌고 meta 쓰기만 실패 (+ 음성 대조군 2종)
        #
        #   meta 단독 지문이었다면 **놓쳤을** 갈래다. 그리고 파일명으로 거르는 최적화가
        #   되살아나면 아래 두 대조군이 잡는다(숨김명 · 일시 파일 접두 실명).
        # ═══════════════════════════════════════════════════════════════════
        partials = (("400", "video.ini", "보통 이름"),
                    ("500", ".graphics.ini", "숨김명"),
                    ("600", ".gfxprofile-tmp-settings.ini", "일시 파일 접두 실명"))
        for appid, filename, label in partials:
            cfg = mkgame(main, tmp, appid, "Part-%s" % appid, filename=filename)
            prime(appid, cfg)
            before_meta = meta_sha(appid, "dock")
            before_body = body_sha(appid, "dock", filename)
            with Patch(store, "atomic_write",
                       fail_write(lambda p, a=appid: p.endswith("meta.json") and
                                  os.path.join("profiles", a, "dock") in p)):
                env = rpc(main, appid and "apply_profile", appid, "internal")
            if env.get("ok") is not False:
                P("ⓔ′ %s: 주입했는데 성공했다 — 주입이 안 먹었다 (%s)" % (label, env))
                continue
            if meta_sha(appid, "dock") != before_meta:
                P("ⓔ′ %s: meta가 바뀌었다 — 부분 쓰기 상태가 재현되지 않았다" % label)
            if body_sha(appid, "dock", filename) == before_body:
                P("ⓔ′ %s: 본체도 안 바뀌었다 — 부분 쓰기 상태가 재현되지 않았다" % label)
            got = (env.get("params") or {}).get("checked_in")
            if got != "dock":
                P("★ⓔ′ %s: 본체만 바뀐 부분 쓰기를 관측하지 못했다(checked_in=%r) — "
                  "meta 단독 지문·파일명 예외가 되살아났다" % (label, got))

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ 손상 `last_applied` — 엔진 가드(§14-A)로 건너뛰고, 표적에 IO가 0이다
        # ═══════════════════════════════════════════════════════════════════
        cfg700 = mkgame(main, tmp, "700", "Delta")
        victim_abs = tmp / "ESCAPE-표적-ABS"
        victim_rel = pathlib.Path(store.data_dir()) / "ESCAPE-표적-REL"
        for victim in (victim_abs, victim_rel):
            victim.mkdir(parents=True, exist_ok=True)
            (victim / "meta.json").write_text(
                '{"filename": "victim.ini", "sha1": "x", "size": %d, "lines": 3}' % len(DOCK))
            (victim / "victim.ini").write_bytes(b"outside-the-slot\n")
        victim_bytes = {p: p.read_bytes() for v in (victim_abs, victim_rel)
                        for p in v.iterdir()}

        # 상대 탈출 값은 **실제 경로로 계산한다** — 상수로 박으면 구조가 바뀌는 순간
        # 검사가 아무것도 안 재면서 통과한다.
        rel_value = os.path.relpath(str(victim_rel), store.profiles_root("700"))
        if not rel_value.startswith(".."):
            P("ⓕ 사전 조건 실패 — 상대 탈출 값이 `..`로 시작하지 않는다(%s)" % rel_value)
        for label, value in (("절대경로", str(victim_abs)), ("상대경로", rel_value),
                             ("숫자", 5), ("빈 문자열", "")):
            # 표적이 실제로 그 경로로 계산되는가(항진식 방지) — 가드가 없으면 엔진이 여기를 읽고 쓴다
            if isinstance(value, str) and value:
                landing = os.path.realpath(os.path.join(store.profiles_root("700"), value))
                if landing not in (os.path.realpath(str(victim_abs)),
                                   os.path.realpath(str(victim_rel))):
                    P("ⓕ %s: 주입 값이 표적을 안 가리킨다(%s) — 이 케이스는 아무것도 안 잰다"
                      % (label, landing))
            # ★ **개별 적용과 일괄 적용 두 경로 모두**에 주입한다(§15-B ④-ⓕ). 일괄 경로는
            #   게임별 예외를 내부 격리하므로, 가드가 없으면 조용히 `error` 행이 되거나
            #   (숫자) 루트 밖에 쓰고도 `applied`로 보고된다(문자열) — 둘 다 화면이 못 본다.
            for path_label, run_apply in (
                    ("개별", lambda: rpc(main, "apply_profile", "700", "internal")),
                    ("일괄", lambda: apply_all(main, "internal"))):
                prime("700", cfg700, previous=None)
                reg = store.load_registry()
                reg["games"]["700"]["last_applied"] = value
                store.save_registry(reg)
                with Watch((victim_abs, victim_rel)) as watch:
                    env = run_apply()
                tag = "%s/%s" % (label, path_label)
                if not env.get("ok"):
                    P("★ⓕ %s: 손상 값 때문에 적용이 실패했다 — 가드는 건너뛰게만 해야 한다 (%s)"
                      % (tag, env))
                    continue
                data = env.get("data") or {}
                if path_label == "개별":
                    observed, notes = data.get("checked_in"), data.get("notes") or []
                    empty = observed is None
                else:
                    row = next((r for r in data.get("results") or []
                                if r["appid"] == "700"), {})
                    # ★ 일괄은 **다른 게임의 정상 체크인도** 함께 싣는다 — 이 절이 잴 것은
                    #   700이 그 안에 없다는 것뿐이다(전체가 비었는지 보면 다른 게임 때문에
                    #   항상 FAIL 나는 거짓 검사가 된다).
                    observed = [r for r in data.get("checkin") or [] if r["appid"] == "700"]
                    notes = [row.get("note") or ""]
                    empty = observed == []
                    if row.get("outcome") != "applied":
                        P("★ⓕ %s: 일괄 행이 applied가 아니다(%s) — 손상 값이 그 게임을 죽였다"
                          % (tag, row))
                if not empty:
                    P("★ⓕ %s: 손상 값인데 체크인이 보고됐다 — %r" % (tag, observed))
                if not any("체크인 건너뜀" in n for n in notes):
                    P("★ⓕ %s: 체크인 건너뜀 note가 없다 — 엔진 가드가 기존 분기로 합류하지 "
                      "않았다 (%s)" % (tag, notes))
                if watch.hits:
                    P("★ⓕ %s: 데이터 루트/슬롯 **밖 표적에 IO가 일어났다** — %s"
                      % (tag, watch.hits[:4]))
        for path, raw in victim_bytes.items():
            if not path.exists() or path.read_bytes() != raw:
                P("★ⓕ 표적 파일이 바뀌었다(%s) — 손상 값이 경로 조각으로 재소비됐다" % path)

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ″ ★ **정상 값에서는 가드 전후 동작이 동일하다**(설계 §14-A 테스트 명세)
        #
        #   가드가 손상 값만 접는다는 주장은, 정상 값에서 **가드 없는 엔진과 같은 결과를
        #   내는지**를 실제로 대조해야 검사가 된다. 그래서 §14-A 한 줄만 뺀 엔진 사본을
        #   만들어 **같은 초기 세계**에서 두 번 돌리고 봉투와 파일계 전체를 대조한다.
        #   ⚠️ 시각을 얼린다 — 백업 파일명·`saved_at`이 실행 시각으로 갈리면 대조가 무의미하다.
        # ═══════════════════════════════════════════════════════════════════
        mutant = load_mutant_engine(tmp)
        if mutant is None:
            P("★ⓕ″ 변이 앵커 소실 — engine.py에서 §14-A 가드 한 줄을 찾지 못했다"
              "(가드가 사라졌거나 형태가 바뀌었다)")
        else:
            keep = tmp / ".world-keep"
            real_clock, store.time = store.time, FrozenClock(store.time)
            mut_clock, mutant.store.time = mutant.store.time, store.time
            real_engine = main.engine
            try:
                prime("700", cfg700)                       # 정상 값(dock)에서 체크인이 일어난다
                # ⚠️ `symlinks=True` — 앞 절이 만든 링크(`backups/900`)를 실디렉터리로 펴면
                #   두 실행의 트리 **모양**이 달라져 대조가 무의미한 차이를 낸다(실제로 냈다).
                shutil.copytree(store.data_dir(), keep, symlinks=True)
                base_cfg = cfg700.read_bytes()

                env_a = rpc(main, "apply_profile", "700", "internal")
                world_a, cfg_a = tree_sha(store.data_dir()), cfg700.read_bytes()

                shutil.rmtree(store.data_dir())
                shutil.copytree(keep, store.data_dir(), symlinks=True)
                cfg700.write_bytes(base_cfg)

                main.engine = mutant                       # 가드 없는 엔진
                env_b = rpc(main, "apply_profile", "700", "internal")
                world_b, cfg_b = tree_sha(store.data_dir()), cfg700.read_bytes()
            finally:
                main.engine = real_engine
                store.time, mutant.store.time = real_clock, mut_clock
                shutil.rmtree(keep, ignore_errors=True)

            if env_a != env_b:
                P("★ⓕ″ 정상 값인데 가드 전후 봉투가 다르다 — 가드가 정상 경로를 건드린다\n"
                  "      가드있음=%s\n      가드없음=%s" % (env_a, env_b))
            diff = sorted(k for k in set(world_a) | set(world_b)
                          if world_a.get(k) != world_b.get(k))
            if diff or cfg_a != cfg_b:
                P("★ⓕ″ 정상 값인데 가드 전후 **파일계가 다르다** — %s" % (diff[:6] or "설정 파일"))
            if (env_a.get("data") or {}).get("checked_in") != "dock":
                P("ⓕ″ 계측기 무효 — 대조에 쓴 시나리오에서 체크인이 안 일어났다(%s)" % env_a)
            if not world_a:
                P("ⓕ″ 계측기 무효 — 파일계 지도가 비었다")

        # ⓕ′ 손상된 **키**도 같은 문법이다: `apply_all`의 관측기는 registry의 games 키를 그대로
        #    도는데 그 키는 `_VALIDATORS`를 지나지 않는다. 지문을 뜨겠다고 루트 밖을 읽지 않는다
        #    (`restore.backup_count`·`remove.delete_preview`와 같은 센티널 문법).
        escape_key = os.path.relpath(str(victim_abs), store.profiles_root(""))
        # 표적을 **읽을 것이 있는 상태**로 만든다 — 비어 있으면 조회가 실패해 검사가 항진식이 된다
        (victim_abs / "dock").mkdir(parents=True, exist_ok=True)
        (victim_abs / "dock" / "meta.json").write_text('{"filename": "victim.ini"}')
        (victim_abs / "dock" / "victim.ini").write_bytes(b"outside-the-slot\n")
        if not os.path.isdir(os.path.join(store.profiles_root(escape_key), "dock")):
            P("ⓕ′ 사전 조건 실패 — 탈출 키가 표적 슬롯을 안 가리킨다(%s)" % escape_key)
        with Watch((victim_abs,)) as watch:
            first = main._slot_fp(escape_key, "dock")
            second = main._slot_fp(escape_key, "dock")
        if watch.hits:
            P("★ⓕ′ 안전하지 않은 키의 지문을 뜨느라 루트 밖을 읽었다 — %s" % watch.hits[:4])
        if first != second:
            P("ⓕ′ 안전하지 않은 키의 지문이 호출마다 다르다 — 관측이 없는 변화를 만든다")

        # ⓕ‴ ★ 같은 문법이 **조회 경로 전체**에 걸린다(P11 게이트 경-ⓐ·ⓒ):
        #     `get_overview`도 손상 키에서 루트 밖 meta를 읽지 않고, `config_path`는
        #     `delete_preview`와 **같은 결론**을 말한다(두 화면이 같은 게임을 두고 다르게
        #     말하면 어느 쪽이 참인지 사용자가 가릴 방법이 없다).
        reg = store.load_registry()
        reg["games"][escape_key] = {"name": "탈출게임", "config_path": "/etc/passwd",
                                    "last_applied": "dock"}
        store.save_registry(reg)
        with Watch((victim_abs,)) as watch:
            env = rpc(main, "get_overview", True)
        row = next((g for g in (env.get("data") or {}).get("games") or []
                    if g["appid"] == escape_key), {})
        if watch.hits:
            P("★ⓕ‴ get_overview가 손상 키에서 데이터 루트 밖을 읽었다 — %s" % watch.hits[:4])
        if row.get("has_dock") or row.get("has_internal") or row.get("profiles_identical"):
            P("★ⓕ‴ 읽지도 않은 슬롯을 화면이 '있다'고 말한다 — %s" % row)
        preview = main.remove.delete_preview(store.load_registry(), escape_key)
        if row.get("config_path") != preview.get("config_path"):
            P("★ⓕ‴ 같은 게임의 config_path를 두 화면이 다르게 말한다 — overview=%r preview=%r"
              % (row.get("config_path"), preview.get("config_path")))
        reg = store.load_registry()
        reg["games"].pop(escape_key, None)
        store.save_registry(reg)

        return finish(tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish(tmp, problems):
    print("체크인 관측 — 발생/건너뜀 · note 동등성 · apply_all 무변형 · 실패 주입 4종 · "
          "부분 쓰기 3종(숨김명·tmp 실명 포함) · 손상 last_applied 4종 · preview total  "
          "(데이터: %s)" % tmp)
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
