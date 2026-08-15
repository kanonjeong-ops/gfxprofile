#!/usr/bin/env python3
"""**적용은 프로필 슬롯을 건드리지 않는다** — 공리 A11 잠금 (설계 §14-A · §15-B ①).

12판까지 `engine.apply_profile`은 적용 **직전에** 현재 게임 설정 파일을 `last_applied` 슬롯으로
되썼다(체크인, G3). 그래서 사용자가 게임에서 설정을 바꾼 뒤 같은 프로필을 다시 적용하면
「방금 바꾼 값 → 그 슬롯 → 다시 디스크」가 되어 **파일이 한 바이트도 안 바뀌었다.**
실기에서 여섯 번 눌러 여섯 번 다 성공 로그가 찍히고 파일은 그대로였다.

13판은 그 블록을 삭제했고, 이 파일은 **삭제된 상태가 유지되는지**를 잰다.
`qa/test_checkin_view.py`(684줄, 관측기 검사)를 대체한다 — 없는 사건의 계측기 대신 **불변식**을 잰다.

### 재는 방법 — 슬롯 디렉터리의 (이름, inode, mtime_ns, sha1)
sha1만 보면 **같은 바이트를 다시 쓴 경우**를 통과시킨다(체크인의 흔한 형태가 정확히 그것이다:
직전 적용 프로필과 디스크가 같으면 같은 내용을 되쓴다). `store.atomic_write`은 tmp→rename이라
**inode가 바뀌므로**, inode·mtime_ns를 같이 재면 그 재기록이 잡힌다.

### `.applied` 하나만 제외한다 — **그 제외가 계약의 일부다**
엔진은 적용 말미(`engine.py:545`)와 already 경로(`_record_already`)에서 그림자 사본 `.applied`를
**의도적으로** 갱신한다. 그래서 조문은 이렇게 읽는다:
    *"적용은 `.applied` 외에 슬롯의 어떤 파일도 만들거나 바꾸거나 지우지 않는다."*

### 못 재는 것(정직)
파일시스템이 ns 해상도를 안 주면(fat32 등) 동일 바이트 재기록은 **inode 변화로만** 잡힌다.
테스트는 tmp(ext4/tmpfs)에서 도므로 둘 다 유효하다.
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
APPID = "666"
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"
APPLIED_MARKER = ".applied"


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


def slot_snapshot(store, appid, with_marker=False):
    """두 슬롯 디렉터리의 파일 상태. `with_marker=False`면 `.applied`를 뺀다(계약).

    값은 `(name, inode, mtime_ns, sha1)`이다 — **같은 바이트 재기록**까지 잡기 위해서다.
    """
    out = {}
    for profile in ("dock", "internal"):
        directory = store.profile_dir(appid, profile)
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            out[profile] = None                   # 슬롯 없음도 상태의 일부다
            continue
        rows = []
        for name in names:
            if name == APPLIED_MARKER and not with_marker:
                continue
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            info = os.stat(path)
            rows.append((name, info.st_ino, info.st_mtime_ns, store.sha1_file(path)))
        out[profile] = rows
    return out


def build_world(tmp, engine, store):
    reg = store.load_registry()
    cfg = tmp / "game" / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(DOCK)
    engine.add_game(reg, APPID, str(cfg), name="SlotImmutable")
    engine.save_profile(reg, APPID, "dock")
    cfg.write_bytes(INTERNAL)
    engine.save_profile(reg, APPID, "internal")
    store.save_registry(reg)
    return cfg


def main_test():                                                # noqa: C901  (갈래 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-slot-immutable-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []
        marker_moved = []            # `.applied` 제외가 **실제로 필요한가**의 증거(음성 대조군 ⓑ)

        def P(msg):
            problems.append(msg)

        cfg = build_world(tmp, engine, store)

        def run(label, call, expect_outcome=None, expect_code=None):
            """한 갈래를 돌리고 **슬롯 불변**을 잰다. 반환은 봉투."""
            before = slot_snapshot(store, APPID)
            before_all = slot_snapshot(store, APPID, with_marker=True)
            env = call()
            after = slot_snapshot(store, APPID)
            after_all = slot_snapshot(store, APPID, with_marker=True)
            if before != after:
                P("★[%s] 적용이 프로필 슬롯을 바꿨다(A11 위반)\n      전=%s\n      후=%s"
                  % (label, before, after))
            if before_all != after_all:
                marker_moved.append(label)
            if expect_outcome is not None:
                got = (env.get("data") or {}).get("outcome")
                if not env.get("ok") or got != expect_outcome:
                    P("[%s] 기대 outcome=%s인데 봉투가 %s다" % (label, expect_outcome, env))
            if expect_code is not None and env.get("code") != expect_code:
                P("[%s] 기대 code=%s인데 봉투가 %s다" % (label, expect_code, env))
            return env

        # ── 4-A 3행: 디스크 == 목표 슬롯 → 무쓰기 성공 ────────────────────────
        cfg.write_bytes(DOCK)
        run("3행 already", lambda: rpc(main, "apply_profile", APPID, "dock"),
            expect_outcome="already")

        # ── 4-A 4행: 디스크 == 다른 슬롯 → 묻지 않고 적용 ─────────────────────
        cfg.write_bytes(INTERNAL)
        run("4행 다른 슬롯과 같음", lambda: rpc(main, "apply_profile", APPID, "dock"),
            expect_outcome="applied")
        if cfg.read_bytes() != DOCK:
            P("4행: 적용됐다는데 설정 파일이 dock 내용이 아니다")

        # ── 4-A 5행: 파일 없음 → 재생 ────────────────────────────────────────
        os.unlink(str(cfg))
        run("5행 파일 없음", lambda: rpc(main, "apply_profile", APPID, "internal"),
            expect_outcome="applied")
        if not cfg.exists() or cfg.read_bytes() != INTERNAL:
            P("5행: 적용이 파일을 재생하지 못했다")

        # ── 4-A 6행: 두 슬롯 모두와 다름 → 확인 요구(무쓰기) → 토큰으로 실행 ──
        cfg.write_bytes(EDITED)
        env = run("6행 확인 요구", lambda: rpc(main, "apply_profile", APPID, "dock"),
                  expect_code=codes.CONFIRM_REQUIRED)
        if cfg.read_bytes() != EDITED:
            P("★6행: 확인 요구인데 설정 파일이 이미 바뀌었다")
        tok = (env.get("params") or {}).get("confirm_token")
        run("6′행 토큰 실행", lambda: rpc(main, "apply_profile", APPID, "dock", confirm_token=tok),
            expect_outcome="applied")

        # ── 4-A 2행: 실행 중 → 조기 거부 ─────────────────────────────────────
        cfg.write_bytes(EDITED)
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == APPID
        try:
            run("2행 실행 중", lambda: rpc(main, "apply_profile", APPID, "dock"),
                expect_code=codes.GAME_RUNNING)
        finally:
            engine.running_game = real_running

        # ── 4-A 8행: 슬롯 손상(본체가 meta와 어긋남) → 엔진 거부 ─────────────
        body = store.profile_file_path(APPID, "internal")
        with open(body, "wb") as fh:
            fh.write(b"quality=brok\nshadows=brok\nsource=CORRUPTED--\n")   # meta와 어긋난다
        cfg.write_bytes(EDITED)
        env = rpc(main, "apply_profile", APPID, "internal")     # 확인 요구 단계
        tok = (env.get("params") or {}).get("confirm_token")
        run("8행 슬롯 손상", lambda: rpc(main, "apply_profile", APPID, "internal",
                                     confirm_token=tok),
            expect_code=codes.PROFILE_CORRUPT)

        # ── 음성 대조군 ⓐ: **체크인을 되살린 엔진**을 꽂으면 이 검사가 반드시 FAIL해야 한다
        #    (실패하지 않으면 이 파일은 아무것도 안 재고 있는 것이다)
        cfg.write_bytes(EDITED)
        real_apply = engine.apply_profile

        def checkin_apply(reg, appid, profile):
            """12판 체크인의 재현 — 적용 전에 현재 디스크를 직전 프로필 슬롯으로 되쓴다."""
            entry = (reg.get("games") or {}).get(str(appid)) or {}
            previous = entry.get("last_applied")
            path = entry.get("config_path")
            if previous in ("dock", "internal") and path and os.path.exists(path):
                store.write_profile(appid, previous, os.path.basename(path),
                                    store.read_bytes(path), src=path)
            return real_apply(reg, appid, profile)

        engine.apply_profile = checkin_apply
        try:
            probe_before = slot_snapshot(store, APPID)
            env = rpc(main, "apply_profile", APPID, "dock")
            if env.get("code") == codes.CONFIRM_REQUIRED:
                env = rpc(main, "apply_profile", APPID, "dock",
                          confirm_token=(env.get("params") or {}).get("confirm_token"))
            probe_after = slot_snapshot(store, APPID)
        finally:
            engine.apply_profile = real_apply
        if probe_before == probe_after:
            P("★음성 대조군 ⓐ 무효 — 체크인을 되살린 엔진에서도 슬롯이 그대로로 보였다. "
              "이 검사는 아무것도 재지 않는다")

        # ── 음성 대조군 ⓑ: `.applied` 제외가 **필요했는가**
        #    (제외 없이 재면 정상 구현도 달라 보인다 = 제외가 장식이 아니라 계약이다)
        if not marker_moved:
            P("★음성 대조군 ⓑ 무효 — 어느 갈래에서도 `.applied`가 안 움직였다. 그러면 제외 규칙이 "
              "아무 일도 안 하는 것이고, 규칙이 지워져도 이 검사는 안 걸린다")

        print("적용의 슬롯 불변 — 4-A 갈래 6종 · 음성 대조군 2 (데이터: %s)" % tmp)
        print("  `.applied`가 움직인 갈래: %s (제외 규칙이 실재하는 증거)" % marker_moved)
        if problems:
            print("\nFAIL")
            for p in problems:
                print("  " + p)
            return 1
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
