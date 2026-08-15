#!/usr/bin/env python3
"""**축출 고지가 실제로 지워지는 파일과 같은가** — 설계 §5-E-3 (반증 A7 잠금).

확인창은 *"진행하면 오래된 백업 N건이 지워집니다: {목록}"*이라고 **이름을 대며** 약속한다.
그 목록이 실제 `store.prune_backups`가 지우는 것과 다르면, 화면이 **지워지지 않을 파일 이름을
대고** 정작 지워지는 것은 말하지 않는다 — 고지가 오정보가 되는 자리다.

### 이 파일의 핵심은 **정렬 기준**이다
2026-08-15(R14 #3) 이전에는 순서가 **두 개**였다: `prune`은 `store.list_backups`의 역**사전**순을
그대로 잘랐고, 화면 목록은 같은 초 충돌 접미사를 바로잡느라 `(stamp, seq)`로 다시 정렬했다.
두 순서가 갈리는 동안 **화면이 지워지지 않을 파일 이름을 댈 수 있었고**, 사전순이 `-10-`을
`-2-`보다 앞에 놓아 **방금 만든 백업이 먼저 잘려 나가기까지** 했다.
지금 순서의 정본은 `store.backup_order_key` **하나**이고, 이 파일은 그것을 두 축으로 잰다 —
① 예고 == 실제 삭제 ② **사전순으로 고른 답은 이 픽스처에서 다른 파일을 가리킨다**(음성 대조군).

잠그는 것:
  ⓐ 적용 확인창의 `evicted`가 **실제 지워진 파일과 일치**한다
  ⓑ 복원 확인창의 `evicted`도 **같은 산출 함수**로 같은 답을 낸다
  ⓒ 링이 안 찼으면 `evicted`는 **빈 배열**이다(없는 손실을 고지하지 않는다)
  ⓓ 축출이 없는 갈래(already·proceed)에는 고지가 실리지 않는다
  ⓔ **prune 순서 == 화면 순서**이고, 둘 다 *사전순이 내는 답과 다르다*(R14 #3)
  ⓕ **같은 초·같은 파일명 두 백업이 표기에서 갈린다**(2026-08-15 QA 재심 A) — 아래.

### ⓕ가 메우는 사각 (이 파일이 **일부러 피하고 있던** 자리다)
2026-08-15 재심 전까지 이 파일은 위 ⓐ~ⓔ 픽스처의 **파일명을 갈라 두어** 같은 표기가 겹치는
세계를 만들지 않았다("못 재는 것"에 그렇게 적혀 있었다). 그런데 그 세계는 정상 API로 쉽게 생긴다 —
같은 초에 같은 설정 파일이 두 번 대피하면 `…-disk-video.ini` / `…-disk-1-video.ini`가 되고,
표기 조각 `(stamp_label, filename)`이 **글자 하나까지 같다.** 확인창은 그 이름으로 승인을 받으므로
사용자는 **무엇을 승인했는지 모른 채** 승인한다. ⓕ는 그 세계를 실제로 만들어 잰다.

### 못 재는 것(정직)
  · 확인창이 그 목록을 **실제로 그리는지**는 UI라 여기서 재지 않는다(사용자 지정 — 실기 몫).
    ⓕ가 잠그는 것은 **봉투가 구별 가능한 값을 싣는가**까지이고, 화면이 `dup`을 실제로 덧붙여
    그리는지는 실기 확인 항목이다.
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
APPID = "850"
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"

#: 같은 초에 충돌한 두 백업. **파일명을 갈라 둔다** — 표기 3칸으로 구별되게 하기 위해서다.
#: 역사전순에서는 `-1-zebra`가 `-video`보다 작아 **뒤에** 오고(=사전순 prune이 먼저 지운다),
#: 생성 순서(`stamp`, `seq`)에서는 seq 0인 `-video`가 더 오래된 것이라 뒤에 온다.
#: **두 답이 갈린다** — 그래서 이 픽스처가 정렬 결함을 실제로 가른다.
OLDEST_STAMP = "20260101-000000"
COLLIDE_A = "%s-disk-video.ini" % OLDEST_STAMP          # seq 0
COLLIDE_B = "%s-disk-1-zebra.ini" % OLDEST_STAMP        # seq 1


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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-evict-preview-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, restore, store
        problems = []

        def P(msg):
            problems.append(msg)

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        def names():
            return {os.path.basename(p) for p in store.list_backups(APPID)}

        def as_item(backup_id, dup=0):
            """실제 파일 하나를 봉투 표기(`EvictedRow`)로 — 예고와 같은 모양으로 맞춘다."""
            info = restore.parse_backup_id(backup_id)
            return {"backup_id": backup_id, "kind": info["kind"],
                    "stamp_label": info["stamp_label"], "filename": info["filename"],
                    "dup": dup}

        # ── 세계 ─────────────────────────────────────────────────────────────
        reg = store.load_registry()
        cfg = tmp / "game" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(DOCK)
        engine.add_game(reg, APPID, str(cfg), name="EvictPreview")
        engine.save_profile(reg, APPID, "dock")
        cfg.write_bytes(INTERNAL)
        engine.save_profile(reg, APPID, "internal")
        store.save_registry(reg)

        # ── ⓒ 링이 안 찼으면 고지가 없다 ─────────────────────────────────────
        cfg.write_bytes(EDITED)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", APPID, "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("사전 조건 실패 — 두 슬롯과 다른데 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        if params_of(env).get("evicted") != []:
            P("★ⓒ 링이 비었는데 축출 고지가 실렸다 — 없는 손실을 말한다 (%s)"
              % params_of(env).get("evicted"))

        # ── 링을 정확히 BACKUP_KEEP까지 채운다 (꼬리 두 건이 충돌 픽스처다) ──
        bdir = store.backups_dir(APPID)
        os.makedirs(bdir, exist_ok=True)
        for name in (COLLIDE_A, COLLIDE_B):
            with open(os.path.join(bdir, name), "wb") as fh:
                fh.write(b"quality=fill\nshadows=fill\nsource=RING-FILLER\n")
        n = 0
        while len(names()) < store.BACKUP_KEEP:
            n += 1
            with open(os.path.join(bdir, "20260202-0000%02d-disk-video.ini" % n), "wb") as fh:
                fh.write(b"quality=fill\nshadows=fill\nsource=RING-FILLER\n")
        if len(names()) != store.BACKUP_KEEP:
            P("사전 조건 실패 — 링이 %d건이다(기대 %d)" % (len(names()), store.BACKUP_KEEP))
            return finish(problems, tmp)

        # ── ⓔ 순서는 **하나**이고, 사전순은 다른 답을 낸다 ───────────────────
        #    ★ 이 절이 음성 대조군이다: 사전순 구현으로 되돌리면 아래 ⓐ·ⓑ가 다른 파일을
        #      가리키게 되고, 그 사실을 여기서 먼저 숫자로 보인다.
        prune_order_last = os.path.basename(store.list_backups(APPID)[-1])
        display_order_last = restore.backup_rows(store.load_registry(), APPID)[-1]["backup_id"]
        if prune_order_last != display_order_last:
            P("★ⓔ prune 순서와 화면 순서가 다르다(%s vs %s) — 화면이 지워지지 않을 파일을 댄다"
              % (prune_order_last, display_order_last))
            return finish(problems, tmp)
        lex_last = sorted(names(), reverse=True)[-1]
        if lex_last == prune_order_last:
            P("★ⓔ 음성 대조군 무효 — 사전 역순이 우연히 같은 답을 냈다(정렬 결함을 못 잡는 픽스처)")
            return finish(problems, tmp)
        # 생성 순서상 가장 오래된 것은 seq 0인 COLLIDE_A다 — 사전순은 COLLIDE_B를 가리킨다.
        if prune_order_last != COLLIDE_A or lex_last != COLLIDE_B:
            P("★ⓔ 최고령 판정이 생성 순서와 다르다 — 실제=%s / 사전순=%s (기대 %s / %s)"
              % (prune_order_last, lex_last, COLLIDE_A, COLLIDE_B))
        expected = [as_item(prune_order_last)]
        naive = [as_item(lex_last)]
        if expected == naive:
            P("★ⓔ 음성 대조군 무효 — 두 답의 표기가 같아 구별되지 않는다 (%s)" % expected)
            return finish(problems, tmp)

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 적용 확인창의 예고 == 실제로 지워진 파일
        # ═══════════════════════════════════════════════════════════════════
        cfg.write_bytes(EDITED)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", APPID, "dock")
        preview = params_of(env).get("evicted")
        if preview != expected:
            P("★ⓐ 적용 확인창의 축출 예고가 실제 prune 대상과 다르다\n"
              "      예고=%s\n      실제=%s\n      (표시 순서로 고른 답=%s)"
              % (preview, expected, naive))
        before = names()
        env = rpc(main, "apply_profile", APPID, "dock",
                  confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("ⓐ 적용이 실패했다 — %s" % env)
        gone = before - names()
        if gone != {prune_order_last}:
            P("★ⓐ 실제로 지워진 파일이 %s다(예고는 %s를 가리켰다)" % (gone, prune_order_last))
        if len(names()) != store.BACKUP_KEEP:
            P("ⓐ 링 크기가 %d다(BACKUP_KEEP=%d)" % (len(names()), store.BACKUP_KEEP))

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 복원 확인창도 **같은 함수**로 같은 답을 낸다
        # ═══════════════════════════════════════════════════════════════════
        prune_next = os.path.basename(store.list_backups(APPID)[-1])
        expected_next = [as_item(prune_next)]
        # ⚠️ 행을 고르기 **전에** 게임 설정 파일 상태를 확정한다 — `same_as_target`은 그 시점의
        #   사실이라, 고른 뒤에 파일을 바꾸면 고를 때 본 근거가 무효가 된다(실제로 한 번 그랬다).
        cfg.write_bytes(EDITED)
        target_row = None
        for row in restore.backup_rows(store.load_registry(), APPID):
            if row["target"] == "config" and not row["same_as_target"]:
                target_row = row
                break
        if target_row is None:
            P("ⓑ 사전 조건 실패 — 되돌릴 곳과 내용이 다른 disk 행이 없다")
        else:
            main._CONFIRM_TOKENS.clear()
            env = rpc(main, "restore_backup", APPID, target_row["backup_id"])
            if env.get("code") != codes.CONFIRM_REQUIRED:
                P("ⓑ 복원이 확인을 요구하지 않았다 — %s" % env)
            elif params_of(env).get("evicted") != expected_next:
                P("★ⓑ 복원 확인창의 축출 예고가 실제 prune 대상과 다르다\n"
                  "      예고=%s\n      실제=%s" % (params_of(env).get("evicted"), expected_next))
            before = names()
            env = rpc(main, "restore_backup", APPID, target_row["backup_id"],
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓑ 복원이 실패했다 — %s" % env)
            gone = before - names()
            if gone != {prune_next}:
                P("★ⓑ 복원에서 실제로 지워진 파일이 %s다(예고는 %s)" % (gone, prune_next))

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ 축출이 없는 갈래에는 고지가 실리지 않는다
        # ═══════════════════════════════════════════════════════════════════
        cfg.write_bytes(store.read_bytes(store.profile_file_path(APPID, "dock")))
        env = rpc(main, "apply_profile", APPID, "dock")
        if data_of(env).get("outcome") != "already":
            P("ⓓ 사전 조건 실패 — already 갈래에 닿지 못했다 (%s)" % env)
        elif data_of(env).get("evicted"):
            P("★ⓓ 무쓰기(already)인데 축출 고지가 실렸다 — 일어나지 않을 삭제를 말한다 (%s)"
              % data_of(env).get("evicted"))

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ 같은 초·같은 파일명 두 백업이 **표기에서 갈린다** (QA 재심 A)
        #
        #   확인창은 *"이것이 지워집니다"*라고 이름을 대며 승인을 받는다. 그 이름이 둘을
        #   가리키면 사용자는 무엇을 승인했는지 모른 채 승인한다 — 손실 고지가 성립하지 않는다.
        #   ★ 픽스처는 **정상 API로만** 만든다(`store.make_backup` 두 번). 같은 초에 같은 설정
        #     파일이 두 번 대피하는 것은 실제로 일어나는 일이고, 여기서는 시계를 얼려 그것을
        #     우연이 아니라 결정론으로 만든다.
        # ═══════════════════════════════════════════════════════════════════
        TWIN_APPID = "851"
        TWIN_STAMP = "20250101-000000"
        TWINS = ["%s-disk-video.ini" % TWIN_STAMP,        # seq 0 — 먼저 만들어진 것
                 "%s-disk-1-video.ini" % TWIN_STAMP]      # seq 1 — 같은 초의 두 번째

        class _Stamp:
            """`store`의 시계를 특정 초로 **얼린다**. 파일을 만드는 것은 정상 경로 그대로다."""

            def __init__(self, real, stamp):
                self._real, self._stamp = real, stamp

            def strftime(self, fmt, *args):
                return self._stamp if fmt == "%Y%m%d-%H%M%S" else self._real.strftime(fmt, *args)

            def __getattr__(self, name):
                return getattr(self._real, name)

        def twin_names():
            return {os.path.basename(p) for p in store.list_backups(TWIN_APPID)}

        reg = store.load_registry()
        twin_cfg = tmp / "game851" / "video.ini"
        twin_cfg.parent.mkdir(parents=True, exist_ok=True)
        twin_cfg.write_bytes(DOCK)
        engine.add_game(reg, TWIN_APPID, str(twin_cfg), name="EvictTwins")
        engine.save_profile(reg, TWIN_APPID, "dock")
        twin_cfg.write_bytes(INTERNAL)
        engine.save_profile(reg, TWIN_APPID, "internal")     # 슬롯 본체 2개 = 해제 시 대피 2건
        store.save_registry(reg)

        real_clock = store.time
        try:
            store.time = _Stamp(real_clock, TWIN_STAMP)
            for _ in range(2):                               # ★ 같은 초·같은 파일명 두 건
                store.make_backup(TWIN_APPID, b"twin\n", "disk", "video.ini")
            for i in range(store.BACKUP_KEEP - 2):           # 링을 정확히 채운다(쌍둥이가 최고령)
                store.time = _Stamp(real_clock, "20250102-0000%02d" % i)
                store.make_backup(TWIN_APPID, b"filler-%02d\n" % i, "disk", "fill%02d.ini" % i)
        finally:
            store.time = real_clock

        if not set(TWINS) <= twin_names() or len(twin_names()) != store.BACKUP_KEEP:
            P("ⓕ 사전 조건 실패 — 쌍둥이 픽스처가 안 섰다 (%s)" % sorted(twin_names()))
            return finish(problems, tmp)

        # ⓕ-0 **음성 대조군**: 표기 조각만으로는 두 파일이 실제로 구별되지 않는다.
        #     (이 단언이 깨지면 명명 규칙이 바뀐 것이고, 그때는 ⓕ가 아무것도 안 재는 절이 된다.)
        seen = {(restore.parse_backup_id(n)["stamp_label"], restore.parse_backup_id(n)["filename"])
                for n in TWINS}
        if len(seen) != 1:
            P("ⓕ-0 계측기 무효 — 쌍둥이의 표기가 애초에 다르다(%s). 이 절이 재려는 모호성이 없다"
              % sorted(seen))

        # ⓕ-1 **한쪽만 지워지는 경우에도** 번호가 붙는다(남는 쌍둥이와 갈려야 한다).
        twin_cfg.write_bytes(EDITED)                         # 두 슬롯과 달라 적용이 물어본다
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", TWIN_APPID, "dock")
        rows = params_of(env).get("evicted") or []
        if env.get("code") != codes.CONFIRM_REQUIRED or len(rows) != 1:
            P("ⓕ-1 사전 조건 실패 — 적용 확인창이 축출 1건을 예고하지 않았다 (%s)" % env)
        else:
            if rows[0].get("backup_id") != TWINS[0]:
                P("★ⓕ-1 예고가 최고령(%s)이 아닌 %s를 가리킨다" % (TWINS[0], rows[0].get("backup_id")))
            if not rows[0].get("dup"):
                P("★ⓕ-1 쌍둥이 중 **한쪽만** 지워지는데 구분 번호가 없다 — 화면이 대는 이름이 "
                  "남는 쪽까지 가리킨다 (%s)" % rows[0])

        # ⓕ-2 **둘 다 지워지는 경우**(등록 해제 = 대피 2건) — 두 항목의 표기가 갈린다.
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "delete_game", TWIN_APPID)
        rows = params_of(env).get("evicted") or []
        if env.get("code") != codes.CONFIRM_REQUIRED or len(rows) != 2:
            P("ⓕ-2 사전 조건 실패 — 등록 해제 확인창이 축출 2건을 예고하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        if {r["backup_id"] for r in rows} != set(TWINS):
            P("★ⓕ-2 예고가 쌍둥이 두 건이 아니다 — %s" % [r["backup_id"] for r in rows])
        shown = [(r["stamp_label"], r["filename"], r["dup"]) for r in rows]
        if len(set(shown)) != len(shown):
            P("★ⓕ-2 **화면 표기가 두 항목에서 같다** — 사용자는 무엇을 승인하는지 알 수 없다 (%s)"
              % shown)
        # 번호의 뜻: 같은 표기를 공유하는 것 중 **먼저 만들어진 것이 1번**이다.
        numbers = {r["backup_id"]: r["dup"] for r in rows}
        if (numbers.get(TWINS[0]), numbers.get(TWINS[1])) != (1, 2):
            P("★ⓕ-2 구분 번호가 생성 순서를 따르지 않는다 — %s (기대: %s=1 · %s=2)"
              % (numbers, TWINS[0], TWINS[1]))

        # ⓕ-3 예고한 그 두 개가 **실제로** 사라진다.
        before = twin_names()
        env = rpc(main, "delete_game", TWIN_APPID, confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("ⓕ-3 등록 해제가 실패했다 — %s" % env)
        gone = before - twin_names()
        if gone != set(TWINS):
            P("★ⓕ-3 실제로 지워진 것이 %s다(예고는 %s)" % (sorted(gone), sorted(TWINS)))

        print("축출 예고 == 실제 prune — 적용·복원 공용 산출 (데이터: %s)" % tmp)
        print("  쌍둥이 픽스처: %s / %s — 표기 조각은 같고 구분 번호로 갈린다" % (TWINS[0], TWINS[1]))
        print("  픽스처: 실제 최고령=%s / 사전순이 고르는 답=%s (두 답이 갈린다)"
              % (prune_order_last, lex_last))
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
