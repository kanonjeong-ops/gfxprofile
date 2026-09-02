#!/usr/bin/env python3
"""슬롯이 실제로 무엇을 들고 있는가 — 기록(meta)이 아니라 본체로 판정한다.

기록만 믿으면 두 자리가 거짓 위에서 돈다:
  · 적용의 "이 내용은 다른 슬롯에 보존돼 있다" → 묻지 않고 진행 + 대피 생략이다.
    기록이 거짓이면 게임 설정 파일의 마지막 온전한 사본이 사라진다.
  · 슬롯 복원의 "이미 같습니다"(`already`) → 아무것도 안 한다.
    기록이 거짓이면 복구 버튼이 손상된 슬롯을 못 고친다 — 복원은 그 손상을 되돌리는 경로다.

### 이 상태는 정상 동작으로 도달한다(합성이 아니다)
`store.write_profile`은 본체를 먼저 쓰고 meta를 나중에 쓴다(두 번의 `atomic_write`).
그 사이에 전원이 나가면 본체는 새 내용, meta는 옛 기록이 된다 — 아래 픽스처가 그 상태다.

이 파일이 재는 것:
  ⓐ 다른 슬롯 본체가 없으면 적용은 묻고, 대피본을 만든다(그 내용이 백업에 남는다)
  ⓑ 다른 슬롯 본체가 다르면(meta만 일치) 역시 묻고 대피한다
  ⓒ 음성 대조군 — 슬롯이 멀쩡하면 묻지 않고 대피도 안 한다(과잉 대피 방지)
  ⓓ 슬롯 복원의 `already`가 본문으로 판정된다 — 손상된 슬롯을 복원이 고친다
  ⓔ 목록의 `same_as_target` 배지도 슬롯 본체 파일을 읽어 정한다(화면과 동작이 같은 근거)
  ⓕ 음성 대조군 — 멀쩡한 슬롯에 같은 내용을 복원하면 여전히 `already`(링 소모 0)

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
C = b"quality=cccc\nshadows=mid_\nsource=HALF-WRITTEN\n"


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


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-slot-truth-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, restore, store
        problems = []

        def P(msg):
            problems.append(msg)

        def data_of(env):
            return env.get("data") or {}

        def params_of(env):
            return env.get("params") or {}

        def shas(appid):
            return {store.sha1_file(p) for p in store.list_backups(appid)}

        def mkgame(appid, name):
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(A)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")
            cfg.write_bytes(B)
            engine.save_profile(reg, appid, "internal")
            store.save_registry(reg)
            return cfg

        def half_write(appid, profile, data):
            """`write_profile`의 앞 절반만 실행된 상태 — 본체는 새 내용, meta는 옛 기록.
            쓰기 도중 전원이 나가면 실제로 이렇게 남는다(두 번의 `atomic_write`)."""
            store.atomic_write(store.profile_file_path(appid, profile), data)

        # ═══════════════════════════════════════════════════════════════════
        # ⓒ 음성 대조군 먼저 — 멀쩡한 슬롯에서는 묻지 않고 대피도 안 한다
        # ═══════════════════════════════════════════════════════════════════
        cfg = mkgame("800", "SlotTruth")
        cfg.write_bytes(B)                              # 디스크 = internal 슬롯 내용
        before = len(store.list_backups("800"))
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", "800", "dock")
        if not env.get("ok") or data_of(env).get("outcome") != "applied":
            P("★ⓒ 멀쩡한 슬롯인데 적용이 조용히 진행되지 않았다 — %s" % env)
        if len(store.list_backups("800")) != before:
            P("★ⓒ 다른 슬롯에 보존된 내용인데 대피본이 생겼다 — 링을 헛되이 태운다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 다른 슬롯의 본체가 없다 → 묻고, 그 내용을 대피시킨다
        # ═══════════════════════════════════════════════════════════════════
        cfg2 = mkgame("810", "MissingBody")
        os.unlink(store.profile_file_path("810", "internal"))    # meta는 남고 본체만 사라졌다
        cfg2.write_bytes(B)                             # 디스크 = internal meta와 같은 내용
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", "810", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("★ⓐ 다른 슬롯 본체가 없는데 묻지 않고 진행했다 — 그 내용은 **어디에도 없다** (%s)" % env)
        else:
            if params_of(env).get("matches"):
                P("★ⓐ 본체가 없는 슬롯을 「일치」로 보고했다 — 화면이 거짓 근거를 그린다 (%s)"
                  % params_of(env).get("matches"))
            env = rpc(main, "apply_profile", "810", "dock",
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓐ 확인 뒤 적용이 실패했다 — %s" % env)
        if store.sha1_bytes(B) not in shas("810"):
            P("★ⓐ 덮어쓰기 직전 내용이 백업에 없다 — 되돌릴 지점이 사라졌다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 다른 슬롯의 본체가 다르다(meta만 일치) → 역시 묻고 대피한다
        # ═══════════════════════════════════════════════════════════════════
        cfg3 = mkgame("820", "DivergedBody")
        half_write("820", "internal", C)                # meta는 B라는데 본문은 C다
        cfg3.write_bytes(B)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", "820", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("★ⓑ 슬롯 본문이 다른데 「보존됐다」며 묻지 않고 진행했다 (%s)" % env)
        else:
            env = rpc(main, "apply_profile", "820", "dock",
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓑ 확인 뒤 적용이 실패했다 — %s" % env)
        if store.sha1_bytes(B) not in shas("820"):
            P("★ⓑ 덮어쓰기 직전 내용이 백업에 없다 — 되돌릴 지점이 사라졌다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓓⓔⓕ 슬롯 복원 — `already`와 배지가 본문으로 판정된다
        # ═══════════════════════════════════════════════════════════════════
        cfg4 = mkgame("830", "RestoreRepair")
        reg = store.load_registry()
        cfg4.write_bytes(B)
        engine.save_profile(reg, "830", "dock")         # dock: A → B (대피본 = A)
        cfg4.write_bytes(A)
        engine.save_profile(reg, "830", "dock")         # dock: B → A (대피본 = B) · 지금 meta=A
        store.save_registry(reg)
        row = next((r for r in restore.backup_rows(store.load_registry(), "830")
                    if r["target"] == "dock" and store.sha1_file(
                        os.path.join(store.backups_dir("830"), r["backup_id"])) == store.sha1_bytes(A)),
                   None)
        if row is None:
            P("사전 조건 실패 — dock으로 되돌아가는 대피본(A)이 없다")
            return finish(problems, tmp)

        # ⓕ 음성 대조군 — 슬롯이 멀쩡하면 그 대피본은 「이미 같음」이다(링 소모 0)
        before = len(store.list_backups("830"))
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", "830", row["backup_id"])
        if data_of(env).get("outcome") != "already":
            P("★ⓕ 슬롯이 이미 같은데 already가 아니다 — 누를 때마다 링이 1칸씩 준다 (%s)" % env)
        if len(store.list_backups("830")) != before:
            P("★ⓕ already 갈래인데 링이 움직였다")
        if not row["same_as_target"]:
            P("★ⓕ 멀쩡한 슬롯인데 「지금과 같음」 배지가 안 붙었다 — 화면과 동작이 갈린다")

        # ⓓⓔ 본문만 깨뜨린다(meta는 A 그대로) → 복원이 그것을 고쳐야 한다
        half_write("830", "dock", C)
        rows = restore.backup_rows(store.load_registry(), "830")
        row2 = next((r for r in rows if r["backup_id"] == row["backup_id"]), None)
        if row2 is None:
            P("사전 조건 실패 — 대상 백업 행이 목록에서 사라졌다")
            return finish(problems, tmp)
        if row2["same_as_target"]:
            P("★ⓔ 본문이 C인데 배지가 「지금과 같음」이다 — 화면이 meta의 기록만 보고 말한다")
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", "830", row["backup_id"])
        if data_of(env).get("outcome") == "already":
            P("★ⓓ 손상된 슬롯에 복원을 눌렀는데 「이미 같습니다」로 끝났다 — **복구 경로가 그 자리에서 "
              "막힌다**(복원은 바로 이 손상을 되돌리는 경로다)")
        elif env.get("code") != codes.CONFIRM_REQUIRED:
            P("★ⓓ 손상된 슬롯 복원이 확인을 요구하지 않았다 — %s" % env)
        else:
            env = rpc(main, "restore_backup", "830", row["backup_id"],
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓓ 확인 뒤 복원이 실패했다 — %s" % env)
        body = store.sha1_file(store.profile_file_path("830", "dock"))
        if body != store.sha1_bytes(A):
            P("★ⓓ 복원 뒤에도 슬롯 본문이 A가 아니다 — 손상이 그대로다 (%s)" % body)

        print("슬롯 본문 진실성 — 적용 3갈래 · 복원 3갈래 (데이터: %s)" % tmp)
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
