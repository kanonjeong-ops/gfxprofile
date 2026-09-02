#!/usr/bin/env python3
"""대피 실패는 어느 경로에서든 같은 사유로 보고된다 — `BACKUP_FAILED`.

백업(대피)이 실패하면 이 툴은 쓰기를 멈춘다(G13). 코드가 곧 화면 문구라, 같은 실패가 경로마다
다른 코드로 도착하면 사용자는 원인과 다른 복구 안내를 받는다 — `PROFILE_META_CORRUPT`는 화면에
"프로필 정보를 읽지 못했습니다"로 나오는데 실제 원인은 백업 폴더 쓰기 실패다.

이 파일이 잠그는 것:
  ⓐ 저장 · ⓑ 슬롯 복원 · ⓒ 설정 파일 복원 · ⓓ 등록 해제 · ⓔ 적용 — 전부 `BACKUP_FAILED`
  ⓕ 그때 아무것도 안 바뀐다(슬롯 meta·본체 sha1 · 게임 설정 파일 바이트 · registry 항목)
  ⓖ 음성 대조군 — 계측기를 떼면 같은 호출이 성공한다(항진식이 아님을 보인다)

계측기는 `store.make_backup`을 실패시키는 것 하나다. 좁게 잡는가를 재려면 그래야 한다 —
  대피 호출만 실패하고 나머지 경로는 멀쩡한 상태에서 코드가 무엇인지 보는 것이 이 검사다.
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
A = b"quality=aaaa\nshadows=high\nsource=SLOT-A-DOCK\n"
B = b"quality=bbbb\nshadows=low_\nsource=SLOT-B-INTL\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"
THIRD = b"quality=thrd\nshadows=mid_\nsource=THIRD-STATE-\n"
OTHER = b"quality=othr\nshadows=mid_\nsource=OTHER-STATE-\n"


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


def main_test():                                                # noqa: C901  (경로 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-backup-failed-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, restore, store
        problems = []

        def P(msg):
            problems.append(msg)

        def code_of(env):
            return env.get("code")

        def token(env):
            return (env.get("params") or {}).get("confirm_token")

        def mkgame(appid, name):
            """두 슬롯 + 두 종류의 백업 행을 정상 API로 만든다.

            빈 슬롯 첫 저장은 대피본을 만들지 않으므로(잃을 것이 없다), 행을 만들려면
            ① 덮어쓰기 저장 → `profile_dock` 행 ② 고유 내용 적용 → `disk` 행이 필요하다.
            """
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(A)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")
            cfg.write_bytes(B)
            engine.save_profile(reg, appid, "internal")
            cfg.write_bytes(EDITED)
            engine.save_profile(reg, appid, "dock")              # dock = EDITED · 대피본 = A
            cfg.write_bytes(THIRD)
            engine.apply_profile(reg, appid, "dock")             # 대피본 = THIRD(disk) · 디스크 = EDITED
            store.save_registry(reg)
            return cfg

        real_backup = store.make_backup

        def failing(*args, **kwargs):
            raise OSError("합성 실패: 백업 디렉터리에 쓸 수 없다")

        def with_failing_backup(fn):
            store.make_backup = failing
            try:
                return fn()
            finally:
                store.make_backup = real_backup

        def slot_state(appid, profile):
            body = store.profile_file_path(appid, profile)
            return (store.sha1_file(store.profile_meta_path(appid, profile)),
                    store.sha1_file(body) if body else None)

        # ── ⓐ 저장 ───────────────────────────────────────────────────────────
        cfg = mkgame("700", "BackupFail")
        cfg.write_bytes(OTHER)                                   # dock(EDITED)을 덮어쓰는 저장 → 확인 필요
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "save_profile", "700", "dock")
        if code_of(env) != codes.CONFIRM_REQUIRED:
            P("ⓐ 사전 조건 실패 — 덮어쓰기 저장이 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        before = slot_state("700", "dock")
        env = with_failing_backup(
            lambda: rpc(main, "save_profile", "700", "dock", confirm_token=token(env)))
        if code_of(env) != codes.BACKUP_FAILED:
            P("★ⓐ 저장의 대피 실패가 %s로 보고됐다 — 사용자가 원인과 다른 복구 안내를 받는다"
              % code_of(env))
        if slot_state("700", "dock") != before:
            P("★ⓕ 대피가 실패했는데 슬롯이 바뀌었다 — %s → %s" % (before, slot_state("700", "dock")))

        # ── ⓑ 슬롯 복원 ──────────────────────────────────────────────────────
        row = next((r for r in restore.backup_rows(store.load_registry(), "700")
                    if r["target"] == "dock"), None)
        if row is None:
            P("ⓑ 사전 조건 실패 — dock으로 되돌아가는 대피본이 없다")
        else:
            main._CONFIRM_TOKENS.clear()
            env = rpc(main, "restore_backup", "700", row["backup_id"])
            if code_of(env) != codes.CONFIRM_REQUIRED:
                P("ⓑ 사전 조건 실패 — 슬롯 복원이 확인을 요구하지 않았다 (%s)" % env)
            else:
                before = slot_state("700", "dock")
                env = with_failing_backup(lambda: rpc(main, "restore_backup", "700",
                                                      row["backup_id"], confirm_token=token(env)))
                if code_of(env) != codes.BACKUP_FAILED:
                    P("★ⓑ 슬롯 복원의 대피 실패가 %s로 보고됐다" % code_of(env))
                if slot_state("700", "dock") != before:
                    P("★ⓕ 슬롯 복원 대피 실패인데 슬롯이 바뀌었다")

        # ── ⓒ 설정 파일 복원 ─────────────────────────────────────────────────
        row = next((r for r in restore.backup_rows(store.load_registry(), "700")
                    if r["target"] == "config" and not r["same_as_target"]), None)
        if row is None:
            P("ⓒ 사전 조건 실패 — 되돌릴 곳과 다른 disk 행이 없다")
        else:
            main._CONFIRM_TOKENS.clear()
            env = rpc(main, "restore_backup", "700", row["backup_id"])
            if code_of(env) != codes.CONFIRM_REQUIRED:
                P("ⓒ 사전 조건 실패 — 설정 파일 복원이 확인을 요구하지 않았다 (%s)" % env)
            else:
                env = with_failing_backup(lambda: rpc(main, "restore_backup", "700",
                                                      row["backup_id"], confirm_token=token(env)))
                if code_of(env) != codes.BACKUP_FAILED:
                    P("★ⓒ 설정 파일 복원의 대피 실패가 %s로 보고됐다" % code_of(env))
                if cfg.read_bytes() != OTHER:
                    P("★ⓕ 복원 대피 실패인데 게임 설정 파일이 바뀌었다")

        # ── ⓓ 등록 해제 · ⓔ 적용 (기준선으로 같이 잰다) ──────────────────────
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "delete_game", "700")
        env = with_failing_backup(lambda: rpc(main, "delete_game", "700", confirm_token=token(env)))
        if code_of(env) != codes.BACKUP_FAILED:
            P("★ⓓ 등록 해제의 대피 실패가 %s로 보고됐다" % code_of(env))
        if "700" not in store.load_registry()["games"]:
            P("★ⓕ 대피 실패인데 등록이 지워졌다")

        cfg.write_bytes(OTHER)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", "700", "dock")
        env = with_failing_backup(
            lambda: rpc(main, "apply_profile", "700", "dock", confirm_token=token(env)))
        if code_of(env) != codes.BACKUP_FAILED:
            P("★ⓔ 적용의 대피 실패가 %s로 보고됐다" % code_of(env))
        if cfg.read_bytes() != OTHER:
            P("★ⓕ 적용 대피 실패인데 게임 설정 파일이 바뀌었다")

        # ── ⓖ 음성 대조군 — 계측기를 떼면 같은 호출이 성공한다 ────────────────
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", "700", "dock")
        env = rpc(main, "apply_profile", "700", "dock", confirm_token=token(env))
        if not env.get("ok"):
            P("★ⓖ 음성 대조군 실패 — 계측기를 뗐는데도 적용이 실패한다 (%s)" % env)

        print("대피 실패 코드 통일 — 저장·복원2·해제·적용 5경로 (데이터: %s)" % tmp)
        return finish(problems, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish(problems, tmp):
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
