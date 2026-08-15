#!/usr/bin/env python3
"""**무엇이 지워지는지 말하고 묻는가** — 축출 고지의 전 경로 + 토큰 결박 (R14 #1·#2).

사용자 지정 최상위 원칙: *"손실 발생 가능성이 있는 행동은 명확하게 인지시키고 그래도 수행할지
물어야 함."* 백업 링은 10칸 공유라, **백업을 만드는 모든 동작이 곧 가장 오래된 백업을 지우는
동작**이다. 그런데 2026-08-15 이전에는 적용·복원만 그 사실을 이름으로 말했고, 저장·일괄 적용·
등록 해제·전체 초기화는 **말없이 지웠다.**

이 파일이 잠그는 것:
  ⓐ **저장** 확인창의 `evicted`가 실제로 지워지는 파일과 같다(이름까지)
  ⓑ **등록 해제** 확인창의 `evicted`가 실제와 같다 — 대피 파일 수만큼 링이 밀린다
  ⓒ **일괄 적용** 미리보기의 `evicted`(수)가 실제 삭제 건수와 같다
  ⓓ **전체 초기화** 확인창의 `evicted`(수)가 실제 삭제 건수와 같다
  ⓔ **토큰이 링에 묶인다**(#2) — 확인창을 띄운 사이 링이 돌면 낡은 토큰은 거부되고
     **새 목록으로 다시 묻는다.** 적용·저장·복원 세 경로 전부.
  ⓕ **다게임 토큰도 축출 대상에 묶인다**(2026-08-15 QA 재심 B) — 일괄 적용·전체 초기화.
     그 둘은 이름 대신 **수**를 말하지만(세션 확정), 그 수가 정확하려면 토큰이 개수가 아니라
     **대상**에 묶여야 한다: 확인 시점에 "0건"이던 게임이 실행 시점에 1건을 지우면
     *"수가 정확하다"*는 약속 자체가 깨진다.

★ ⓔ·ⓕ의 계측기 설계: 링·대상만 움직이고 **다른 지문 조각은 건드리지 않는** 조작을 쓴다
  (ⓔ = 다른 슬롯에 저장 / ⓕ = 설정 파일 재기록·포화 링 회전). 그러지 않으면 결박이 없는
  구현도 통과해 이 절이 아무것도 못 가른다 — ⓕ는 옛 지문이 **실제로 안 움직였는지**까지 잰다.
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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-evict-notice-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, remove, restore, store
        problems = []

        def P(msg):
            problems.append(msg)

        def params_of(env):
            return env.get("params") or {}

        def names(appid):
            return {os.path.basename(p) for p in store.list_backups(appid)}

        def as_items(appid, filenames):
            """실제 파일 이름들을 봉투 표기(`EvictedRow`)로 — 예고와 같은 모양으로 맞춘다.

            ⚠️ `dup`(같은 표기 구분 번호)은 **0**으로 둔다: 이 파일의 픽스처는 파일명을 전부
              갈라 두므로 표기가 유일하다. 같은 표기가 겹치는 세계는
              `qa/test_backup_evict_preview.py` ⓕ가 따로 잰다.
            """
            out = []
            for name in filenames:
                info = restore.parse_backup_id(name)
                out.append({"backup_id": name, "kind": info["kind"],
                            "stamp_label": info["stamp_label"], "filename": info["filename"],
                            "dup": 0})
            return out

        def mkgame(appid, name, internal=True):
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(DOCK)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")
            if internal:
                cfg.write_bytes(INTERNAL)
                engine.save_profile(reg, appid, "internal")
            cfg.write_bytes(DOCK)
            store.save_registry(reg)
            return cfg

        def fill_ring(appid):
            """링을 가득 채운다. **이름을 갈라 둔다** — 표기 3칸으로 구별되게 하기 위해서다."""
            while len(names(appid)) < store.BACKUP_KEEP:
                i = len(names(appid))
                store.make_backup(appid, b"filler-%02d\n" % i, "disk", "fill%02d.ini" % i)

        def tail(appid, n):
            """지금 목록의 **가장 오래된 n건**(=다음 n건이 쌓이면 잘릴 것)."""
            return [os.path.basename(p) for p in store.list_backups(appid)[-n:]] if n else []

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 저장 — 확인창이 지워질 백업을 **이름으로** 말한다
        # ═══════════════════════════════════════════════════════════════════
        cfg900 = mkgame("900", "SaveEvict")
        fill_ring("900")
        cfg900.write_bytes(EDITED)                       # dock 슬롯과 달라 저장이 물어본다
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "save_profile", "900", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓐ 사전 조건 실패 — 덮어쓰기 저장이 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        expected = as_items("900", tail("900", 1))
        if params_of(env).get("evicted") != expected:
            P("★ⓐ 저장 확인창의 축출 예고가 실제 prune 대상과 다르다\n      예고=%s\n      실제=%s"
              % (params_of(env).get("evicted"), expected))
        before = names("900")
        gone_expected = set(tail("900", 1))
        env = rpc(main, "save_profile", "900", "dock",
                  confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("ⓐ 저장이 실패했다 — %s" % env)
        if before - names("900") != gone_expected:
            P("★ⓐ 저장에서 실제로 지워진 파일이 %s다(예고는 %s)"
              % (before - names("900"), gone_expected))

        # ⓐ′ 대피가 없는 갈래에는 고지가 없다 — 슬롯 본체가 없으면 저장은 백업을 안 만든다.
        cfg950 = mkgame("950", "NoEvacuate")
        fill_ring("950")
        os.unlink(store.profile_file_path("950", "dock"))   # 본체만 사라진 슬롯(부분 rmtree 잔재)
        cfg950.write_bytes(EDITED)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "save_profile", "950", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓐ′ 사전 조건 실패 — 확인을 요구하지 않았다 (%s)" % env)
        elif params_of(env).get("evicted"):
            P("★ⓐ′ 대피가 없는 저장인데 축출 고지가 실렸다 — 일어나지 않을 삭제를 말한다 (%s)"
              % params_of(env).get("evicted"))
        else:
            before = names("950")
            rpc(main, "save_profile", "950", "dock",
                confirm_token=params_of(env).get("confirm_token"))
            if before - names("950"):
                P("★ⓐ′ 고지가 없었는데 백업이 지워졌다 — %s" % (before - names("950")))

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 등록 해제 — 대피 파일 **수만큼** 링이 밀린다
        # ═══════════════════════════════════════════════════════════════════
        mkgame("910", "DeleteEvict")                     # 슬롯 2개 = 대피 2건
        fill_ring("910")
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "delete_game", "910")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓑ 사전 조건 실패 — 삭제가 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        expected = as_items("910", tail("910", 2))
        if params_of(env).get("evicted") != expected:
            P("★ⓑ 등록 해제 확인창의 축출 예고가 실제와 다르다\n      예고=%s\n      실제=%s"
              % (params_of(env).get("evicted"), expected))
        before = names("910")
        gone_expected = set(tail("910", 2))
        env = rpc(main, "delete_game", "910", confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("ⓑ 등록 해제가 실패했다 — %s" % env)
        if before - names("910") != gone_expected:
            P("★ⓑ 등록 해제에서 실제로 지워진 파일이 %s다(예고는 %s)"
              % (before - names("910"), gone_expected))

        # ═══════════════════════════════════════════════════════════════════
        # ⓒ 일괄 적용 — 예고한 **건수**가 실제 삭제 건수와 같다
        # ═══════════════════════════════════════════════════════════════════
        cfgs = {}
        for appid in ("920", "930"):
            cfgs[appid] = mkgame(appid, "BulkEvict%s" % appid)
            fill_ring(appid)
            cfgs[appid].write_bytes(EDITED)              # 두 슬롯 어느 것과도 다르다 → 대피가 생긴다
        # 940은 **대피가 없는 게임**이다(디스크 = dock) — 예고에 들어가면 안 된다.
        mkgame("940", "BulkAlready")
        fill_ring("940")
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_all", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓒ 사전 조건 실패 — 일괄 적용이 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        said_n = params_of(env).get("evicted")
        said_games = params_of(env).get("evict_games")
        before = {a: names(a) for a in ("900", "920", "930", "940", "950")}
        env = rpc(main, "apply_all", "dock", confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("ⓒ 일괄 적용이 실패했다 — %s" % env)
        gone = {a: before[a] - names(a) for a in before}
        real_n = sum(len(v) for v in gone.values())
        real_games = sum(1 for v in gone.values() if v)
        if (said_n, said_games) != (real_n, real_games):
            P("★ⓒ 일괄 적용 예고(%s건/%s게임)와 실제(%s건/%s게임)가 다르다 — 지워진 것=%s"
              % (said_n, said_games, real_n, real_games, gone))
        if said_n == 0:
            P("ⓒ 계측기 무효 — 예고가 0이면 어떤 구현도 통과한다(픽스처가 안 섰다)")
        if gone.get("940"):
            P("★ⓒ 대피가 없어야 할 게임(디스크=dock)에서 백업이 지워졌다 — %s" % gone["940"])

        # ═══════════════════════════════════════════════════════════════════
        # ⓔ 토큰 결박 — 확인창을 띄운 사이 **링만** 돌면 낡은 토큰은 거부된다
        #    ★ 계측기: 링을 돌리는 조작으로 **다른 슬롯 저장**을 쓴다. 그러면
        #      대상 슬롯 meta도 게임 설정 파일도 안 움직여, 링을 안 묶은 구현은 통과해 버린다.
        # ═══════════════════════════════════════════════════════════════════
        cfg960 = mkgame("960", "TokenRing")
        fill_ring("960")

        rotations = [0]

        def rotate_ring(appid):
            """링만 한 칸 돌린다 — 다른 슬롯(internal)에 **매번 새로운** 내용을 저장한다.

            ⚠️ 내용이 같으면 `save_profile`이 무쓰기로 끝나 링이 안 돈다(R13 분기). 그러면 낡은
              토큰이 통과하는 것이 **옳은 동작**이 되어 이 절이 거짓 FAIL을 낸다 — 실제로 한 번
              그렇게 짰다. 그래서 회차 번호로 내용을 갈라 두고, **돌았는지 여기서 확인**한다.
            """
            rotations[0] += 1
            path = (tmp / ("game%s" % appid) / "video.ini")
            keep = path.read_bytes()
            before_ring = names(appid)
            path.write_bytes(b"quality=rot_\nshadows=rot_\nsource=RING-ROTATE-%02d\n" % rotations[0])
            reg_ = store.load_registry()
            engine.save_profile(reg_, appid, "internal")
            store.save_registry(reg_)
            path.write_bytes(keep)                       # 디스크는 원래대로 — 지문의 다른 조각 불변
            if names(appid) == before_ring:
                P("계측기 무효 — %d회차 회전에서 링이 안 돌았다(무쓰기 분기?) %s"
                  % (rotations[0], sorted(before_ring)))

        def ring_bound(label, call, appid):
            """1차 호출로 토큰을 받고, 링을 돌린 뒤 **그 토큰이 거부되는지** 본다."""
            main._CONFIRM_TOKENS.clear()
            first = call(None)
            if first.get("code") != codes.CONFIRM_REQUIRED:
                P("ⓔ-%s 사전 조건 실패 — 확인을 요구하지 않았다 (%s)" % (label, first))
                return
            said = params_of(first).get("evicted")
            if not said:
                P("ⓔ-%s 계측기 무효 — 축출 예고가 비어 있다(포화 링이 아니다)" % label)
                return
            rotate_ring(appid)
            after = call(params_of(first).get("confirm_token"))
            if after.get("code") != codes.CONFIRM_REQUIRED:
                P("★ⓔ-%s 링이 돈 뒤에도 낡은 토큰이 통과했다 — 사용자가 승인한 것과 **다른 백업**이 "
                  "지워진다 (%s)" % (label, after))
                return
            if params_of(after).get("evicted") == said:
                P("★ⓔ-%s 다시 물었는데 목록이 그대로다 — 새 대상을 말하지 않는다 (%s)"
                  % (label, said))

        cfg960.write_bytes(EDITED)                       # 두 슬롯과 달라 적용이 물어본다
        ring_bound("적용", lambda tok: rpc(main, "apply_profile", "960", "dock", confirm_token=tok), "960")
        cfg960.write_bytes(EDITED)
        ring_bound("저장", lambda tok: rpc(main, "save_profile", "960", "dock", confirm_token=tok), "960")

        # 복원 — **가장 오래된 행은 고르지 않는다**(링을 돌리면 그 행 자체가 사라져 다른 조각이
        # 같이 움직인다. 그러면 링 신호를 혼자 재지 못한다).
        cfg960.write_bytes(EDITED)
        row = next((r for r in restore.backup_rows(store.load_registry(), "960")
                    if r["target"] == "config" and not r["same_as_target"]), None)
        if row is None:
            P("ⓔ-복원 사전 조건 실패 — 되돌릴 곳과 다른 disk 행이 없다")
        else:
            ring_bound("복원",
                       lambda tok: rpc(main, "restore_backup", "960", row["backup_id"], confirm_token=tok),
                       "960")

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ **다게임 토큰도 축출 대상에 묶인다** (2026-08-15 QA 재심 B)
        #
        #   일괄 적용·전체 초기화 토큰은 `remove.reset_fingerprint` 하나에만 묶여 있었다.
        #   그 지문의 링 신호는 게임별 **개수**뿐이고 설정 파일 sha는 §3-C가 **일부러 뺐다** —
        #   그래서 두 갈래로 뚫렸다:
        #     ⓕ-1 확인 시점에 "축출 0건"이던 게임의 설정 파일을 게임·클라우드가 고유 내용으로
        #         바꾸면, **낡은 토큰이 통과**하고 실행이 대피본을 만들며 고지에 없던 백업이 지워진다.
        #     ⓕ-2 **포화 링이 한 칸 돌면** 개수는 10으로 불변이라 대상이 바뀌어도 안 걸린다.
        #
        #   ★ 계측기 설계: 두 절 모두 **`reset_fingerprint`가 변하지 않는 조작**만 쓴다. 그리고
        #     그 사실을 숫자로 확인한 뒤에 판정한다 — 확인하지 않으면 "옛 지문이 잡은 것"과
        #     "새 결박이 잡은 것"을 구별할 수 없어 이 절이 아무것도 못 가른다.
        # ═══════════════════════════════════════════════════════════════════
        cfg970 = mkgame("970", "BulkToken")              # 디스크 = dock 프로필 → 축출 0건에서 시작
        fill_ring("970")

        main._CONFIRM_TOKENS.clear()
        first = rpc(main, "apply_all", "dock")
        if first.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓕ-1 사전 조건 실패 — 일괄 적용이 확인을 요구하지 않았다 (%s)" % first)
        else:
            said_n = params_of(first).get("evicted")
            fp_before = remove.reset_fingerprint(store.load_registry())
            # 게임(또는 클라우드)이 확인창을 띄운 사이 설정 파일을 **고유 내용**으로 다시 썼다.
            cfg970.write_bytes(b"quality=cld_\nshadows=cld_\nsource=CLOUD-REWROTE-970\n")
            if remove.reset_fingerprint(store.load_registry()) != fp_before:
                P("ⓕ-1 계측기 무효 — 설정 파일만 바꿨는데 옛 지문이 움직였다(무엇이 잡았는지 "
                  "구별할 수 없다)")
            after = rpc(main, "apply_all", "dock", confirm_token=params_of(first).get("confirm_token"))
            if after.get("code") != codes.CONFIRM_REQUIRED:
                P("★ⓕ-1 확인창을 띄운 사이 지워질 백업이 늘었는데 낡은 토큰이 통과했다 — "
                  "고지에 없던 백업이 사라진다 (%s)" % after)
            else:
                now_n = params_of(after).get("evicted")
                if not (isinstance(now_n, int) and isinstance(said_n, int) and now_n > said_n):
                    P("ⓕ-1 계측기 무효 — 축출 예고가 %s→%s로 늘지 않았다(픽스처가 안 섰다)"
                      % (said_n, now_n))
                # 음성 대조군: 아무것도 안 바뀐 상태의 새 토큰은 **통과해야** 한다(방어가 과하지 않다)
                fresh = rpc(main, "apply_all", "dock")
                done = rpc(main, "apply_all", "dock", confirm_token=params_of(fresh).get("confirm_token"))
                if not done.get("ok"):
                    P("★ⓕ-1 음성 대조군 실패 — 상태가 그대로인데 정상 토큰도 거부됐다 (%s)" % done)

        # ── ⓕ-2 전체 초기화: **개수는 그대로인데 대상만 바뀐다**(포화 링 회전) ─────
        #    ★ 여기서는 2차 호출을 **성공시키지 않는다**(세계가 사라진다). 음성 대조군은 바로
        #      아래 ⓓ가 겸한다 — 거기서 새 토큰이 정상적으로 통과해 초기화가 실행된다.
        main._CONFIRM_TOKENS.clear()
        first = rpc(main, "reset_all")
        if first.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓕ-2 사전 조건 실패 — 초기화가 확인을 요구하지 않았다 (%s)" % first)
        else:
            said_n = params_of(first).get("evicted")
            ring_before = names("970")
            fp_before = remove.reset_fingerprint(store.load_registry())
            # 링을 한 칸 돌린다 — **포화 상태라 개수는 10 그대로**이고 이름만 바뀐다.
            store.make_backup("970", b"quality=rot_\nshadows=rot_\nsource=RESET-RING-ROTATE\n",
                              "disk", "rotate.ini")
            if len(names("970")) != store.BACKUP_KEEP or names("970") == ring_before:
                P("ⓕ-2 계측기 무효 — 링이 %d건이고 회전 여부=%s (기대: %d건·회전함)"
                  % (len(names("970")), names("970") != ring_before, store.BACKUP_KEEP))
            if remove.reset_fingerprint(store.load_registry()) != fp_before:
                P("ⓕ-2 계측기 무효 — 링만 돌렸는데 옛 지문이 움직였다(개수 신호가 안 걸리는 "
                  "회전이라야 새 결박을 혼자 잰다)")
            after = rpc(main, "reset_all", confirm_token=params_of(first).get("confirm_token"),
                        confirm_text=main._RESET_CHALLENGE)
            if after.get("code") != codes.CONFIRM_REQUIRED:
                P("★ⓕ-2 포화 링이 돈 뒤에도 낡은 초기화 토큰이 통과했다 — 사용자가 승인한 것과 "
                  "**다른 백업**이 지워진다 (%s)" % after)
            elif params_of(after).get("evicted") != said_n:
                # 개수가 같아야 이 절이 "개수가 아니라 대상"을 잰 것이 된다(같은 수·다른 대상).
                P("ⓕ-2 계측기 주의 — 회전으로 축출 **건수**까지 바뀌었다(%s→%s). 이 절은 개수가 "
                  "불변인 회전을 재려던 것이다" % (said_n, params_of(after).get("evicted")))

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ 전체 초기화 — 예고한 **건수**가 실제 삭제 건수와 같다 (맨 마지막: 세계를 지운다)
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "reset_all")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("ⓓ 사전 조건 실패 — 초기화가 확인을 요구하지 않았다 (%s)" % env)
            return finish(problems, tmp)
        said_n = params_of(env).get("evicted")
        said_games = params_of(env).get("evict_games")
        appids = sorted(store.load_registry()["games"])
        before = {a: names(a) for a in appids}
        env = rpc(main, "reset_all", confirm_token=params_of(env).get("confirm_token"),
                  confirm_text=main._RESET_CHALLENGE)
        if not env.get("ok"):
            P("ⓓ 초기화가 실패했다 — %s" % env)
        gone = {a: before[a] - names(a) for a in appids}
        real_n = sum(len(v) for v in gone.values())
        real_games = sum(1 for v in gone.values() if v)
        if (said_n, said_games) != (real_n, real_games):
            P("★ⓓ 초기화 예고(%s건/%s게임)와 실제(%s건/%s게임)가 다르다 — 지워진 것=%s"
              % (said_n, said_games, real_n, real_games, gone))
        if said_n == 0:
            P("ⓓ 계측기 무효 — 예고가 0이면 어떤 구현도 통과한다(픽스처가 안 섰다)")

        print("축출 고지 전 경로 — 저장·해제·일괄·초기화 + 토큰 링 결박 3종 (데이터: %s)" % tmp)
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
