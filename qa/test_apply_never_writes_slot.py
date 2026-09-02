#!/usr/bin/env python3
"""적용 경로가 슬롯의 정규 파일을 바꾸지 않는지 잰다 — 공리 A11.

되쓰기(체크인)가 있으면 현재 게임 설정이 직전 프로필 슬롯에 기록된다. 이 파일은 적용의
여러 갈래 전후에 두 슬롯의 정규 파일 스냅샷을 비교하고, 되쓰기를 넣은 음성 대조군으로
계측기가 실제 변경을 잡는지 확인한다.

스냅샷 값은 `(name, inode, mtime_ns, sha1)`이다. 같은 바이트 재기록도 inode·mtime_ns로
잡는다. 디렉터리와 깨진 링크, 링크 자체의 메타데이터는 이 스냅샷의 단언 범위가 아니다.

제품의 적용 경로에는 슬롯 쓰기가 없다. `.applied`는 제품이 만들지 않고 부산물 판정에만
쓰지만, 테스트 픽스처는 옛 잔재를 만들기 위해 그 이름을 직접 쓸 수 있다.

합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`이 tmp라 실사용 데이터에 닿을 수 없다.
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


def slot_snapshot(store, appid):
    """두 슬롯 디렉터리에서 `isfile`인 항목의 `(name, inode, mtime_ns, sha1)` 스냅샷."""
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

        def P(msg):
            problems.append(msg)

        cfg = build_world(tmp, engine, store)

        def run(label, call, expect_outcome=None, expect_code=None):
            """한 갈래를 돌리고 위 정규 파일 스냅샷의 불변을 잰다. 반환은 봉투."""
            before = slot_snapshot(store, APPID)
            env = call()
            after = slot_snapshot(store, APPID)
            if before != after:
                P("★[%s] 적용이 프로필 슬롯을 바꿨다(A11 위반)\n      전=%s\n      후=%s"
                  % (label, before, after))
            if expect_outcome is not None:
                got = (env.get("data") or {}).get("outcome")
                if not env.get("ok") or got != expect_outcome:
                    P("[%s] 기대 outcome=%s인데 봉투가 %s다" % (label, expect_outcome, env))
            if expect_code is not None and env.get("code") != expect_code:
                P("[%s] 기대 code=%s인데 봉투가 %s다" % (label, expect_code, env))
            return env

        # ── 3행: 디스크 == 목표 슬롯 → 무쓰기 성공 ────────────────────────
        cfg.write_bytes(DOCK)
        run("3행 already", lambda: rpc(main, "apply_profile", APPID, "dock"),
            expect_outcome="already")

        # ── 4행: 디스크 == 다른 슬롯 → 묻지 않고 적용 ─────────────────────
        cfg.write_bytes(INTERNAL)
        run("4행 다른 슬롯과 같음", lambda: rpc(main, "apply_profile", APPID, "dock"),
            expect_outcome="applied")
        if cfg.read_bytes() != DOCK:
            P("4행: 적용됐다는데 설정 파일이 dock 내용이 아니다")

        # ── 5행: 파일 없음 → 재생 ────────────────────────────────────────
        os.unlink(str(cfg))
        run("5행 파일 없음", lambda: rpc(main, "apply_profile", APPID, "internal"),
            expect_outcome="applied")
        if not cfg.exists() or cfg.read_bytes() != INTERNAL:
            P("5행: 적용이 파일을 재생하지 못했다")

        # ── 6행: 두 슬롯 모두와 다름 → 확인 요구(무쓰기) → 토큰으로 실행 ──
        cfg.write_bytes(EDITED)
        env = run("6행 확인 요구", lambda: rpc(main, "apply_profile", APPID, "dock"),
                  expect_code=codes.CONFIRM_REQUIRED)
        if cfg.read_bytes() != EDITED:
            P("★6행: 확인 요구인데 설정 파일이 이미 바뀌었다")
        tok = (env.get("params") or {}).get("confirm_token")
        run("6′행 토큰 실행", lambda: rpc(main, "apply_profile", APPID, "dock", confirm_token=tok),
            expect_outcome="applied")

        # ── 2행: 실행 중 → 조기 거부 ─────────────────────────────────────
        cfg.write_bytes(EDITED)
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == APPID
        try:
            run("2행 실행 중", lambda: rpc(main, "apply_profile", APPID, "dock"),
                expect_code=codes.GAME_RUNNING)
        finally:
            engine.running_game = real_running

        # ── 8행: 슬롯 손상(본체가 meta와 어긋남) → 엔진 거부 ─────────────
        body = store.profile_file_path(APPID, "internal")
        with open(body, "wb") as fh:
            fh.write(b"quality=brok\nshadows=brok\nsource=CORRUPTED--\n")   # meta와 어긋난다
        cfg.write_bytes(EDITED)
        env = rpc(main, "apply_profile", APPID, "internal")     # 확인 요구 단계
        tok = (env.get("params") or {}).get("confirm_token")
        run("8행 슬롯 손상", lambda: rpc(main, "apply_profile", APPID, "internal",
                                     confirm_token=tok),
            expect_code=codes.PROFILE_CORRUPT)

        # ── 음성 대조군 ⓐ: 체크인을 되살린 엔진을 꽂으면 이 검사가 반드시 FAIL해야 한다
        #    (실패하지 않으면 이 파일은 아무것도 안 재고 있는 것이다)
        cfg.write_bytes(EDITED)
        real_apply = engine.apply_profile

        def checkin_apply(reg, appid, profile):
            """체크인의 재현 — 적용 전에 현재 디스크를 직전 프로필 슬롯으로 되쓴다."""
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

        print("적용의 슬롯 불변 — 4-A 갈래 6종 · 음성 대조군 1 (데이터: %s)" % tmp)
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
