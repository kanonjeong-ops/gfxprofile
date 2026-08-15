#!/usr/bin/env python3
"""**복원은 그 행의 「되돌릴 곳」으로 간다** — 설계 §5-C · 상태표 4-B (2·3·4·9·10행).

12판의 [복원]은 행 종류와 무관하게 **게임 설정 파일**만 되돌렸다. 그래서 *"프로필을 덮어쓰기
직전에 대피시킨 사본"*을 되돌려도 정작 그 프로필은 그대로였다 — 사용자가 실기에서 보고한
결함이다. 13판은 `profile_*` 행을 **그 슬롯**으로 보낸다.

잠그는 것:
  ⓐ `profile_*` 복원이 **슬롯**을 백업 내용으로 바꾼다 (meta·본체 둘 다)
  ⓑ 그때 **게임 설정 파일은 안 바뀐다**  ← 목적지를 뒤바꾼 구현에서 ⓐ와 **동시에** 뒤집힌다
  ⓒ 슬롯의 옛 내용이 대피본으로 **1건** 남는다
  ⓓ 슬롯 == 백업이면 `already`(쓰기 0 · 링 소모 0)
  ⓔ **실행 중이어도 거부되지 않는다**(프로필 슬롯은 게임이 읽지도 쓰지도 않는다)
  ⓕ **4-B 9행** — meta 없음/손상 ∧ 본체 있음 → 확인 요구 + `slot_unreadable` + **대피 0건**,
     확정하면 슬롯이 백업 내용이 된다
  ⓖ **4-B 10행** — meta 있음 ∧ 본체 없음 → *meta가 「같다」고 말해도* `already`가 아니다
     (already로 접으면 슬롯이 깨진 채로 남고 사용자에겐 되돌릴 방법이 사라진다) · **대피 0건**
  ⓗ `disk` 행은 **반대** — 게임 설정 파일만 바뀌고 슬롯은 그대로다
  ⓘ **확인창이 대는 두 사실이 실제와 같은가**(2026-08-15 QA R2) — `evacuates`·`saved_at`

### ⓘ가 메우는 사각 — 「대피 0건」은 재고 있었는데 **화면이 대피를 약속하는지**는 안 쟀다
ⓕ·ⓖ는 링이 안 움직이는 것까지만 봤다. 그런데 확인창은 같은 봉투를 읽고 *"복원 전에 지금의
내용도 백업으로 보관합니다 — 백업 한 칸을 씁니다"*와 *"덮어쓸 대상(현재 …): {saved_at}에
저장됨"*을 그린다. 10행에서는 **둘 다 거짓**인데(대피할 파일이 없고 그 자리에 내용도 없다)
봉투가 그 둘을 그대로 실어 보내고 있었다 — 사용자는 **없는 프로필을 덮어쓴다고 믿고**,
**쓰지도 않을 백업 한 칸을 지불한다고 믿는다.** 잠그는 것은 봉투의 두 값이고, 화면이 그 값으로
줄을 그리는지는 실기 몫이다(UI는 여기서 재지 않는다 — 사용자 지정).

★ 음성 대조군은 ⓑ·ⓗ 자체다: 목적지 판정을 지우거나 뒤바꾼 구현에서 이 둘이 반드시 깨진다.
★ ⓘ의 음성 대조군은 **4행**이다(아래 ⓐ 구간): 같은 두 값이 거기서는 **참·비어 있지 않음**이라야
  한다. 한쪽만 재면 *"항상 False로 실어 보내는"* 구현이 통과한다.
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
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"
THIRD = b"quality=thrd\nshadows=mid_\nsource=THIRD-STATE-\n"


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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-restore-target-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []

        def P(msg):
            problems.append(msg)

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        def rows(appid):
            env = rpc(main, "list_backups", str(appid))
            return (env.get("data") or {}).get("backups") or []

        def find(appid, kind, content):
            """그 종류이면서 **내용이 정확히 그것인** 백업 행. 없으면 None."""
            want = store.sha1_bytes(content)
            for row in rows(appid):
                if row["kind"] != kind:
                    continue
                path = os.path.join(store.backups_dir(appid), row["backup_id"])
                if store.sha1_file(path) == want:
                    return row
            return None

        def confirm_and_run(appid, backup_id):
            env = rpc(main, "restore_backup", str(appid), backup_id)
            if not is_confirm(env):
                return env, None
            tok = params_of(env).get("confirm_token")
            return env, rpc(main, "restore_backup", str(appid), backup_id, confirm_token=tok)

        def mkgame(appid, name):
            """슬롯 둘 + 프로필 대피본 둘 + disk 대피본 하나."""
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(DOCK)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")
            cfg.write_bytes(INTERNAL)
            engine.save_profile(reg, appid, "internal")
            cfg.write_bytes(THIRD)
            engine.save_profile(reg, appid, "dock")        # 대피 profile_dock(DOCK) · dock=THIRD
            engine.save_profile(reg, appid, "internal")    # 대피 profile_internal(INTERNAL) · intl=THIRD
            engine.apply_profile(reg, appid, "dock")       # 디스크가 두 슬롯과 같아 대피 없음
            store.save_registry(reg)
            return cfg

        # ═══════════════════════════════════════════════════════════════════
        # ⓐⓑⓒⓔ 프로필 슬롯으로 되돌린다 (4-B 4행)
        # ═══════════════════════════════════════════════════════════════════
        cfg = mkgame("810", "SlotTarget")
        cfg.write_bytes(EDITED)                            # 게임 설정 파일은 여기서 안 움직여야 한다
        row = find("810", "profile_internal", INTERNAL)
        if row is None:
            P("사전 조건 실패 — 내용이 INTERNAL인 profile_internal 대피본이 없다")
            return finish(problems, tmp)
        if row["target"] != "internal":
            P("★ⓐ 행의 되돌릴 곳이 %s다(기대 internal)" % row["target"])
        n_before = len(store.list_backups("810"))
        dock_before = store.sha1_file(store.profile_file_path("810", "dock"))

        # ⓔ 실행 중에도 슬롯 복원은 막지 않는다 — 토큰 발급까지 그대로 간다
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == "810"
        try:
            ask, done = confirm_and_run("810", row["backup_id"])
        finally:
            engine.running_game = real_running
        if not is_confirm(ask):
            P("★ⓔ 실행 중이라고 슬롯 복원이 막혔다 — %s" % ask)
            return finish(problems, tmp)
        # ── ⓘ 음성 대조군: **4행에서는** 두 사실이 참이다(대피가 실제로 일어나고 그 자리에
        #    내용이 있다). 이걸 같이 재지 않으면 두 값을 늘 False로 싣는 구현도 ⓘ를 통과한다.
        if params_of(ask).get("evacuates") is not True:
            P("★ⓘ 4행 확인창에 `evacuates`가 참이 아니다 — 실제로는 대피본이 1건 생기는데"
              " 화면이 **백업 한 칸이 소모된다는 사실을 말하지 못한다** (%s)"
              % params_of(ask).get("evacuates"))
        if not params_of(ask).get("saved_at"):
            P("★ⓘ 4행 확인창에 `saved_at`이 없다 — 덮어쓸 대상이 언제 저장된 것인지 못 말한다")
        if not (done or {}).get("ok") or data_of(done).get("outcome") != "restored":
            P("ⓐ 슬롯 복원이 실행되지 않았다 — %s" % done)
        body = store.profile_file_path("810", "internal")
        if not body or store.sha1_file(body) != store.sha1_bytes(INTERNAL):
            P("★ⓐ 슬롯 본체가 백업 내용이 아니다")
        meta = store.load_meta("810", "internal") or {}
        if meta.get("sha1") != store.sha1_bytes(INTERNAL):
            P("★ⓐ 슬롯 meta가 본체와 어긋난다 — 다음 적용이 PROFILE_CORRUPT로 거부된다")
        if cfg.read_bytes() != EDITED:
            P("★ⓑ 슬롯 복원이 **게임 설정 파일을 바꿨다** — 확인한 곳과 다른 곳에 썼다")
        if store.sha1_file(store.profile_file_path("810", "dock")) != dock_before:
            P("★ⓑ 슬롯 복원이 **다른 슬롯**까지 바꿨다")
        if len(store.list_backups("810")) - n_before != 1:
            P("★ⓒ 슬롯 복원의 대피본이 %d건이다(1건이어야 한다)"
              % (len(store.list_backups("810")) - n_before))
        if store.sha1_bytes(THIRD) not in {store.sha1_file(p) for p in store.list_backups("810")}:
            P("★ⓒ 덮어쓰기 직전 슬롯 내용(THIRD)이 백업에 없다 — 되돌릴 지점이 없다")

        # ── ⓓ 되돌린 직후 같은 행 = already(링 소모 0) ───────────────────────
        n_before = len(store.list_backups("810"))
        env = rpc(main, "restore_backup", "810", row["backup_id"])
        if data_of(env).get("outcome") != "already":
            P("★ⓓ 슬롯 == 백업인데 already가 아니다 — %s" % env)
        if len(store.list_backups("810")) != n_before:
            P("★ⓓ already에서 링이 움직였다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓗ `disk` 행은 반대 — 게임 설정 파일만 바뀐다
        # ═══════════════════════════════════════════════════════════════════
        cfg2 = mkgame("820", "DiskTarget")
        cfg2.write_bytes(EDITED)
        engine_reg = store.load_registry()
        engine.apply_profile(engine_reg, "820", "internal")   # EDITED가 대피본으로 남는다
        store.save_registry(engine_reg)
        disk_row = find("820", "disk", EDITED)
        if disk_row is None:
            P("사전 조건 실패 — 내용이 EDITED인 disk 대피본이 없다 (%s)"
              % [(r["kind"], r["size"]) for r in rows("820")])
        else:
            if disk_row["target"] != "config":
                P("★ⓗ disk 행의 되돌릴 곳이 %s다(기대 config)" % disk_row["target"])
            slots_before = {p: store.sha1_file(store.profile_file_path("820", p))
                            for p in ("dock", "internal")}
            _, done = confirm_and_run("820", disk_row["backup_id"])
            if not (done or {}).get("ok"):
                P("ⓗ disk 행 복원이 실패했다 — %s" % done)
            if cfg2.read_bytes() != EDITED:
                P("★ⓗ disk 행 복원이 게임 설정 파일을 되돌리지 못했다")
            slots_after = {p: store.sha1_file(store.profile_file_path("820", p))
                           for p in ("dock", "internal")}
            if slots_before != slots_after:
                P("★ⓗ disk 행 복원이 프로필 슬롯을 바꿨다 — %s → %s" % (slots_before, slots_after))

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ 4-B 9행 — meta가 손상됐고 본체는 남아 있다 (대피 불가를 고지하고 진행)
        # ═══════════════════════════════════════════════════════════════════
        cfg3 = mkgame("830", "SlotMetaBroken")
        cfg3.write_bytes(EDITED)
        row9 = find("830", "profile_internal", INTERNAL)
        with open(store.profile_meta_path("830", "internal"), "w", encoding="utf-8") as fh:
            fh.write('"valid json but not an object"')     # 기록은 깨졌고 본체는 그대로다
        n_before = len(store.list_backups("830"))
        ask, done = confirm_and_run("830", row9["backup_id"])
        if not is_confirm(ask):
            P("★ⓕ 9행에서 확인을 요구하지 않았다 — 되돌릴 수 없는 손실을 묻지 않고 진행한다 (%s)"
              % ask)
        elif not params_of(ask).get("slot_unreadable"):
            P("★ⓕ 9행 확인창에 `slot_unreadable`이 없다 — **대피가 불가능하다는 사실**을 "
              "사용자에게 말하지 못한다 (%s)" % sorted(params_of(ask)))
        if params_of(ask).get("evicted"):
            P("ⓕ 9행은 링을 쓰지 않는데 축출 고지가 실렸다 — %s" % params_of(ask).get("evicted"))
        if params_of(ask).get("evacuates"):
            P("★ⓘ 9행 확인창이 `evacuates`를 참이라 한다 — 대피할 대상을 특정할 수 없는 상태인데"
              " 화면은 **「백업 한 칸을 씁니다」**라고 약속한다")
        if not (done or {}).get("ok"):
            P("★ⓕ 9행 복원이 실패했다 — 손상된 슬롯을 되돌릴 방법이 사라진다 (%s)" % done)
        if len(store.list_backups("830")) != n_before:
            P("★ⓕ 9행에서 대피본이 생겼다(%d→%d) — 대피할 대상을 특정할 수 없는 상태였다"
              % (n_before, len(store.list_backups("830"))))
        body = store.profile_file_path("830", "internal")
        if not body or store.sha1_file(body) != store.sha1_bytes(INTERNAL):
            P("★ⓕ 9행 복원 뒤에도 슬롯이 백업 내용이 아니다")
        if cfg3.read_bytes() != EDITED:
            P("★ⓕ 9행 복원이 게임 설정 파일을 바꿨다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓖ 4-B 10행 — meta는 「같다」고 말하는데 본체가 없다
        #    already로 접으면 **슬롯이 깨진 채로 남는다**(무쓰기라 아무것도 고쳐지지 않는다).
        # ═══════════════════════════════════════════════════════════════════
        cfg4 = mkgame("840", "SlotBodyMissing")
        reg4 = store.load_registry()
        cfg4.write_bytes(INTERNAL)
        engine.save_profile(reg4, "840", "internal")   # 대피 profile_internal(THIRD) · slot=INTERNAL
        store.save_registry(reg4)
        row10 = find("840", "profile_internal", INTERNAL)
        meta10 = store.load_meta("840", "internal")
        if row10 is None or meta10.get("sha1") != store.sha1_bytes(INTERNAL):
            P("사전 조건 실패 — 10행을 만들 재료가 없다(meta가 백업과 같다고 말해야 한다)")
        else:
            os.unlink(store.profile_file_path("840", "internal"))     # 본체만 사라졌다
            n_before = len(store.list_backups("840"))
            ask, done = confirm_and_run("840", row10["backup_id"])
            if not is_confirm(ask):
                P("★ⓖ 10행이 already로 접혔다 — 무쓰기로 끝나면 슬롯이 깨진 채로 남고 "
                  "사용자에겐 되돌릴 방법이 없다 (%s)" % ask)
            elif not (done or {}).get("ok"):
                P("★ⓖ 10행 복원이 실패했다 — %s" % done)
            elif store.sha1_file(store.profile_file_path("840", "internal")) \
                    != store.sha1_bytes(INTERNAL):
                P("★ⓖ 10행 복원 뒤에도 슬롯 본체가 복구되지 않았다")
            if len(store.list_backups("840")) != n_before:
                P("★ⓖ 10행에서 대피본이 생겼다 — 대피할 본체가 없던 상태다")
            # ── ⓘ 10행: 위에서 링이 안 움직인 것을 쟀다. **화면이 그 사실과 같은 말을 하는가.**
            if is_confirm(ask):
                if params_of(ask).get("evacuates"):
                    P("★ⓘ 10행 확인창이 `evacuates`를 참이라 한다 — 링은 한 칸도 안 쓰는데"
                      " 화면은 **「백업 한 칸을 씁니다」**라고 말한다(쓰지도 않을 대가를 승인시킨다)")
                if params_of(ask).get("saved_at"):
                    P("★ⓘ 10행 확인창이 `saved_at`(%r)을 실었다 — 그 기록이 가리키는 본체는 없다."
                      " 화면은 **없는 프로필을 「…에 저장됨」**이라 말하고, 사용자는 지금 있지도"
                      " 않은 내용을 덮어쓴다고 믿는다" % params_of(ask).get("saved_at"))

        print("복원 목적지 — 4-B 2·4·9·10행 + disk 대칭 (데이터: %s)" % tmp)
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
