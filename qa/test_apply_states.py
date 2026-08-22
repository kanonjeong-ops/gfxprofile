#!/usr/bin/env python3
"""**적용 상태표 4-A 전수** — 갈래마다 무엇이 일어나고 무엇이 안 일어나는가 (설계 §5-E-1 · §14-B).

갈래별로 넷을 **같은 계측기**로 잰다:
  ⓐ 엔진 `apply_profile`이 실제로 호출됐는가(결과가 아니라 **호출 자체**)
  ⓑ 백업 링 증분 — 특히 **4행 0건**과 **4′행 1건**
  ⓒ 봉투의 `outcome`/`code`
  ⓓ 게임 설정 파일의 sha1 변화

### 4′행이 이 파일의 핵심이다 (반증 A2)
「디스크가 다른 슬롯과 같으면 대피본을 만들지 않는다」는 **판정 시점의 사실**에 기댄다.
판정(`engine.py`의 `disk_state`)과 쓰기 사이에 게임·클라우드가 파일을 **고유값**으로 바꾸면,
그 값은 어느 슬롯에도 백업에도 없이 사라진다. 13판은 그 자리에 **쓰기 직전 재검증**을 넣었다.
재현은 `store.read_bytes`가 **그 파일에 대해 한 번만** 다른 내용을 돌려주게 해서 만든다 —
엔진이 판정 뒤에 다시 읽는 바로 그 지점이다. 재검증이 없으면 백업이 **안 생긴다**(=FAIL).

### 3′·3″행 — `already`는 **기록이 아니라 본체**를 본다 (2026-08-22 · QA R2 N-1)
슬롯 **본체만** 깨지고 meta는 멀쩡한 상태에서 게임 설정 파일이 마침 그 내용과 같으면, 기록
기반 판정은 *"이미 적용됨"*이라 답한다 — 화면은 성공인데 프로필은 적용되지 않았다. 판정을
`profile in matches`(본체 실측)로 하면 **묻고**, 승인하면 엔진이 `PROFILE_CORRUPT`로 거부한다
(조기 거부는 하지 않는다 — 설계 §15-D E10). 3″행은 **본체 온전성 하나만** 되돌린 음성
대조군이라, `already`를 통째로 없애는 변이가 3′행을 초록으로 통과하지 못한다.

### 거짓 검사 방지
`already`(+0)와 `applied`(+1)를 같은 계측기로 재므로, 계측기가 고장 나(항상 0 또는 항상 1)
있으면 둘 중 하나가 반드시 FAIL한다.

### 못 재는 것(정직)
`store.read_bytes`(백업 조건) 이후 `store.atomic_write`(교체) 사이의 잔여 창은 재지 않는다 —
**12판과 동일한 창**이고(설계 §14-B), 완전 봉쇄는 파일 잠금이 필요해 이 툴의 위협 모델 밖이다.
★ 합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`이 tmp라 실사용 데이터에 닿을 수 없다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPID = "888"
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"
EXTERNAL = b"quality=extn\nshadows=race\nsource=OUTSIDE-RACE\n"
CORRUPT = b"quality=????\nshadows=????\nsource=CORRUPTED-BODY\n"


def boot(tmp):
    def sink(fmt="", *args, **kwargs):
        return None

    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(info=sink, warning=sink, error=sink, debug=sink,
                                        log=lambda level, fmt="", *a, **k: None)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():                                                # noqa: C901  (갈래 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-apply-states-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []
        calls = []

        def P(msg):
            problems.append(msg)

        real_apply = engine.apply_profile

        def counted_apply(reg, appid, profile):
            """엔진 호출을 **직접 센다** — "already면 엔진을 안 부른다"를 결과가 아니라 호출로 잰다."""
            calls.append((str(appid), profile))
            return real_apply(reg, appid, profile)

        engine.apply_profile = counted_apply

        reg = store.load_registry()
        cfg = tmp / "game" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(DOCK)
        engine.add_game(reg, APPID, str(cfg), name="ApplyStates")
        engine.save_profile(reg, APPID, "dock")
        cfg.write_bytes(INTERNAL)
        engine.save_profile(reg, APPID, "internal")
        store.save_registry(reg)

        def backup_n():
            return len(store.list_backups(APPID))

        rows = []                     # 갈래 수는 **세지 않고 잰다** — 손으로 적으면 어긋난다

        def measure(label, call, engine_called, backup_delta, outcome=None, code=None,
                    file_changes=None):
            rows.append(label)
            before_n, before_sha = backup_n(), store.sha1_file(str(cfg))
            calls.clear()
            env = call()
            after_n, after_sha = backup_n(), store.sha1_file(str(cfg))
            if bool(calls) != engine_called:
                P("[%s] 엔진 호출 여부가 %s다(기대 %s) — %s"
                  % (label, bool(calls), engine_called, calls))
            if after_n - before_n != backup_delta:
                P("★[%s] 백업 증분이 %d건이다(기대 %d) — 링 소모 계약이 어긋난다"
                  % (label, after_n - before_n, backup_delta))
            if outcome is not None:
                got = (env.get("data") or {}).get("outcome")
                if not env.get("ok") or got != outcome:
                    P("[%s] 기대 outcome=%s인데 봉투가 %s다" % (label, outcome, env))
            if code is not None and env.get("code") != code:
                P("[%s] 기대 code=%s인데 봉투가 %s다" % (label, code, env))
            if file_changes is not None and (before_sha != after_sha) != file_changes:
                P("★[%s] 설정 파일 변화가 %s다(기대 %s)"
                  % (label, before_sha != after_sha, file_changes))
            return env

        # ── 1행 미등록 ───────────────────────────────────────────────────────
        measure("1행 미등록", lambda: rpc(main, "apply_profile", "9999999", "dock"),
                engine_called=False, backup_delta=0, code=codes.GAME_NOT_REGISTERED)

        # ── 2행 실행 중 → 조기 거부 ──────────────────────────────────────────
        cfg.write_bytes(EDITED)
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == APPID
        try:
            measure("2행 실행 중", lambda: rpc(main, "apply_profile", APPID, "dock"),
                    engine_called=False, backup_delta=0, code=codes.GAME_RUNNING,
                    file_changes=False)
        finally:
            engine.running_game = real_running

        # ── 3행 디스크 == 목표 슬롯 → 무쓰기 성공 ────────────────────────────
        cfg.write_bytes(DOCK)
        measure("3행 already", lambda: rpc(main, "apply_profile", APPID, "dock"),
                engine_called=False, backup_delta=0, outcome="already", file_changes=False)

        # ── 3′행 ★ 슬롯 **본체만** 깨졌다(meta는 멀쩡) → **`already`가 아니다** ─────
        #
        # 판정을 기록(`meta.sha1 == 디스크 sha1`)으로 하면 여기서 "이미 적용됨"이 나온다 —
        # 화면은 성공이라 말하는데 dock 프로필은 **적용되지 않았다**(QA R2 N-1). 판정이 본체
        # 실측(`profile in matches`)이면 「두 슬롯 모두와 다름」으로 떨어져 **묻고**, 승인하면
        # 엔진이 `PROFILE_CORRUPT`로 정직하게 거부한다 — 조기 거부는 하지 않는다(설계 §15-D E10).
        # ★ 이 갈래가 중요한 이유는 **타이밍**이다: 디스크에 그 내용이 그대로 있는 지금이
        #   [저장] 한 번으로 슬롯을 되살릴 수 있는 유일하게 쉬운 순간인데, 거짓 성공이
        #   그 사실을 가린다.
        cfg.write_bytes(DOCK)
        dock_body = pathlib.Path(store.profile_file_path(APPID, "dock"))
        dock_meta = pathlib.Path(store.profile_meta_path(APPID, "dock"))
        intact_body, intact_meta = dock_body.read_bytes(), dock_meta.read_bytes()
        dock_body.write_bytes(CORRUPT)                    # meta는 손대지 않는다 — 본체만 깬다
        main._CONFIRM_TOKENS.clear()
        env = measure("3′행 본체 손상 → 묻는다", lambda: rpc(main, "apply_profile", APPID, "dock"),
                      engine_called=False, backup_delta=0, code=codes.CONFIRM_REQUIRED,
                      file_changes=False)
        if env.get("ok") or (env.get("data") or {}).get("outcome") == "already":
            P("★3′행 본체가 깨진 슬롯에 대고 봉투가 성공(`already`)이라 답한다 — 판정이 "
              "본체가 아니라 **기록**을 보고 있다(QA R2 N-1)")
        measure("3′행 승인 → 엔진이 거부",
                lambda: rpc(main, "apply_profile", APPID, "dock",
                            confirm_token=(env.get("params") or {}).get("confirm_token")),
                engine_called=True, backup_delta=0, code=codes.PROFILE_CORRUPT,
                file_changes=False)
        if dock_body.read_bytes() != CORRUPT or dock_meta.read_bytes() != intact_meta:
            P("3′행: 거부 갈래가 슬롯을 건드렸다")

        # ── 3″행 음성 대조군 — 본체를 되살리면 **다시 `already`**이고 아무것도 안 바뀐다 ──
        #
        # 3′행과 **딱 하나(본체 온전성)만** 다르다. 이 대조가 없으면 `already`를 통째로
        # 없애는 변이가 3′행을 초록으로 통과시킨다.
        dock_body.write_bytes(intact_body)
        ring_before = sorted(store.list_backups(APPID))
        slots_before = {p: store.sha1_file(store.profile_file_path(APPID, p))
                        for p in ("dock", "internal")}
        main._CONFIRM_TOKENS.clear()
        measure("3″행 정상 → 여전히 already", lambda: rpc(main, "apply_profile", APPID, "dock"),
                engine_called=False, backup_delta=0, outcome="already", file_changes=False)
        if sorted(store.list_backups(APPID)) != ring_before:
            P("★3″행 무쓰기 갈래가 링을 건드렸다")
        if {p: store.sha1_file(store.profile_file_path(APPID, p))
                for p in ("dock", "internal")} != slots_before:
            P("★3″행 무쓰기 갈래가 슬롯 본체를 건드렸다")
        if dock_meta.read_bytes() != intact_meta:
            P("★3″행 무쓰기 갈래가 meta를 건드렸다")

        # ── 4행 디스크 == 다른 슬롯 → 즉시 적용, **백업 없음** ───────────────
        cfg.write_bytes(INTERNAL)
        measure("4행 다른 슬롯과 같음", lambda: rpc(main, "apply_profile", APPID, "dock"),
                engine_called=True, backup_delta=0, outcome="applied", file_changes=True)
        if cfg.read_bytes() != DOCK:
            P("4행: 적용 결과가 dock 내용이 아니다")

        # ── 4′행 ★ 판정 뒤·쓰기 전에 외부가 파일을 바꿨다 → **백업이 생겨야 한다** ──
        cfg.write_bytes(INTERNAL)
        real_read = store.read_bytes
        armed = {"on": True}

        def racing_read(path):
            data = real_read(path)
            if armed["on"] and os.path.abspath(path) == os.path.abspath(str(cfg)):
                armed["on"] = False          # 딱 한 번 — 판정 이후의 외부 변경을 재현한다
                return EXTERNAL
            return data

        store.read_bytes = racing_read
        try:
            measure("4′행 쓰기 직전 변경", lambda: rpc(main, "apply_profile", APPID, "dock"),
                    engine_called=True, backup_delta=1, outcome="applied", file_changes=True)
        finally:
            store.read_bytes = real_read
        if armed["on"]:
            P("★4′행 계측기 무효 — 주입이 발동하지 않았다(엔진이 그 자리에서 파일을 다시 읽지 않는다)")
        saved = {store.sha1_file(p) for p in store.list_backups(APPID)}
        if store.sha1_bytes(EXTERNAL) not in saved:
            P("★4′행 외부가 쓴 내용이 백업에 없다 — **어느 슬롯에도 백업에도 없는 내용이 사라졌다**"
              "(§14-B 재검증이 없거나 무력하다)")

        # ── 5행 파일 없음 → 재생, 백업 없음 ──────────────────────────────────
        os.unlink(str(cfg))
        measure("5행 파일 없음", lambda: rpc(main, "apply_profile", APPID, "internal"),
                engine_called=True, backup_delta=0, outcome="applied")
        if not cfg.exists() or cfg.read_bytes() != INTERNAL:
            P("5행: 적용이 파일을 재생하지 못했다")

        # ── 6행 두 슬롯 모두와 다름(무토큰) → 무쓰기 확인 요구 ───────────────
        cfg.write_bytes(EDITED)
        main._CONFIRM_TOKENS.clear()
        env = measure("6행 확인 요구", lambda: rpc(main, "apply_profile", APPID, "dock"),
                      engine_called=False, backup_delta=0, code=codes.CONFIRM_REQUIRED,
                      file_changes=False)
        tok = (env.get("params") or {}).get("confirm_token")

        # ── 6′행 토큰 실행 → 적용 + **disk 백업 1건** ────────────────────────
        measure("6′행 토큰 실행",
                lambda: rpc(main, "apply_profile", APPID, "dock", confirm_token=tok),
                engine_called=True, backup_delta=1, outcome="applied", file_changes=True)
        if store.sha1_bytes(EDITED) not in {store.sha1_file(p) for p in store.list_backups(APPID)}:
            P("★6′행 덮어쓰기 직전 내용이 백업에 없다 — 되돌릴 지점이 없다")

        # ── 9행 백업 실패 → 거부 + **원본 무변경** ───────────────────────────
        cfg.write_bytes(EDITED)
        real_backup = store.make_backup

        def failing_backup(*args, **kwargs):
            raise OSError("합성 실패: 백업 디렉터리에 쓸 수 없다")

        store.make_backup = failing_backup
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", APPID, "dock")
        tok = (env.get("params") or {}).get("confirm_token")
        try:
            measure("9행 백업 실패",
                    lambda: rpc(main, "apply_profile", APPID, "dock", confirm_token=tok),
                    engine_called=True, backup_delta=0, code=codes.BACKUP_FAILED,
                    file_changes=False)
        finally:
            store.make_backup = real_backup

        print("적용 상태표 4-A — 갈래 %d종(4′ 재검증 · 3′ 본체 손상 포함) (데이터: %s)"
              % (len(rows), tmp))
        if problems:
            print("\nFAIL")
            for p in problems:
                print("  " + p)
            return 1
        print("PASS")
        return 0
    finally:
        # 계측기를 되돌린다 — 대상을 바꿔 놓은 채 남는 계측 장치가 가장 나쁘다.
        try:
            from gfxp import engine as engine_mod
            if "real_apply" in locals():
                engine_mod.apply_profile = locals()["real_apply"]
        except Exception:                                       # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
