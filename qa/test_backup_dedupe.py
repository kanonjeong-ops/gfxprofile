#!/usr/bin/env python3
"""**백업 링은 태그마다 같은 내용을 하나만 담는다** — 설계 §14-G ⓔ.

### 무엇이 틀렸었나
`store.make_backup`은 내용을 보지 않고 매번 새 파일을 만들었다. 그런데 디스크 설정은
dock ↔ internal **두 내용 사이를 왕복**하므로 같은 내용이 계속 다시 쌓인다 — 실측 81칸 중
*지금 어디에도 없어 백업이 있어야만 되찾을 수 있는* 내용은 **7종**뿐이었고, **세 게임은 10칸
전부가 사본**이었다. 링을 마모시킨 주범은 실패가 아니라 **정상 동작**이다.

### 이 파일이 잠그는 것 다섯
  ⓐ 같은 태그에 같은 내용이 있으면 **아무것도 쓰지 않는다** — 그리고 안 쓰므로 **안 지운다**.
    (음성 대조군: 내용이 새것이면 정확히 1건 쌓이고 1건 잘린다. 둘이 같이 서야 잰 것이 「중복」이다.)
  ⓑ **태그가 다르면 같은 내용도 담긴다.** 되돌릴 곳이 다른 두 행은 서로를 대신하지 못한다
    (§5-C ⓐ) — 전역으로 걸렀다면 한쪽 태그의 행이 통째로 사라지고 화면은 그것을
    *"이쪽은 백업이 없다"*로 읽는다.
  ⓒ **형식 불명(`unknown`)은 판정에 끼지 않는다.** 앱이 만들지 않는 이름 = 바깥에서 들어온
    파일이라, 그것과 같다는 이유로 대피를 건너뛰지 않고 그것을 지우지도 않는다.
  ⓓ **고지한 개수 == 실제로 지워진 개수.** 본체가 둘인데 내용이 같으면 실제로 쌓이는 것은
    한 건이므로, 확인창도 한 건만 예고해야 한다(둘을 예고하면 *일어나지 않을 삭제*를 말한다).
  ⓔ **무쓰기여도 `evacuated` 봉투는 본체 이름을 그대로 싣는다.** 안 만들었다고 빼면 화면이
    `evacuated: {}`가 되어 **대피 없이 사라진 진짜 소멸과 구별되지 않는다.**

★ 합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp라 실사용 데이터에 닿을 수 없다.
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
INTL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
E1 = b"quality=e1__\nshadows=mid_\nsource=USER-EDIT-1-\n"
E2 = b"quality=e2__\nshadows=mid_\nsource=USER-EDIT-2-\n"
E3 = b"quality=e3__\nshadows=mid_\nsource=USER-EDIT-3-\n"

#: 앱이 만들지 않는 이름 = `parse_backup_id`가 `unknown`으로 접는 이름.
STRANGE = "strange-name.ini"


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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-backup-dedupe-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []

        def P(msg):
            problems.append(msg)

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def names(appid):
            return {os.path.basename(p) for p in store.list_backups(appid)}

        def holding(appid, kind, data):
            """그 태그의 링에 그 내용을 담은 백업 **이름들**."""
            want = store.sha1_bytes(data)
            out = []
            for path in store.list_backups(appid):
                info = store.parse_backup_id(os.path.basename(path))
                if info["kind"] == kind and store.sha1_file(path) == want:
                    out.append(os.path.basename(path))
            return out

        def build(appid, name):
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(DOCK)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")               # 빈 슬롯 첫 저장 — 대피 없음
            cfg.write_bytes(INTL)
            engine.save_profile(reg, appid, "internal")           # 빈 슬롯 첫 저장 — 대피 없음
            store.save_registry(reg)
            return cfg

        def saturate(appid):
            i = 0
            while len(names(appid)) < store.BACKUP_KEEP:
                store.make_backup(appid, b"filler-%02d\n" % i, store.KIND_DISK,
                                  "fill%02d.ini" % i)
                i += 1

        def apply_once(appid, profile, tag):
            """적용 한 번을 확인창까지 거쳐 끝낸다 — `(확인창 params, 링 변화)`."""
            main._CONFIRM_TOKENS.clear()
            ask = rpc(main, "apply_profile", appid, profile)
            if not is_confirm(ask):
                P("%s 사전 조건 실패 — 적용이 확인을 요구하지 않았다 (%s)" % (tag, ask))
                return None, (set(), set())
            before = names(appid)
            env = rpc(main, "apply_profile", appid, profile,
                      confirm_token=params_of(ask).get("confirm_token"))
            if not env.get("ok"):
                P("%s 적용이 실패했다 — %s" % (tag, env))
            after = names(appid)
            return params_of(ask), (after - before, before - after)

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 같은 태그·같은 내용은 다시 담기지 않는다 (+ 새 내용은 담긴다 = 음성 대조군)
        # ═══════════════════════════════════════════════════════════════════
        cfg = build("860", "Dedupe")
        cfg.write_bytes(E1)
        apply_once("860", "dock", "ⓐ-준비")                        # → disk(E1) 1건
        if len(holding("860", store.KIND_DISK, E1)) != 1:
            P("★ⓐ 준비 실패 — 첫 적용이 disk(E1)을 %d건 만들었다(1건이어야 한다)"
              % len(holding("860", store.KIND_DISK, E1)))
            return finish(problems, tmp)
        saturate("860")                                           # 포화 = 축출이 실재하는 상태

        # ⓐ-1 **중복**: 같은 내용을 다시 대피시키려 해도 아무 일도 없다
        cfg.write_bytes(E1)
        ask, (added, gone) = apply_once("860", "internal", "ⓐ-1")
        if ask is not None:
            if ask.get("evicted"):
                P("★ⓐ-1 대피본이 안 만들어지는 갈래인데 확인창이 축출을 예고했다 — %s"
                  % ask.get("evicted"))
            if added or gone:
                P("★ⓐ-1 같은 태그·같은 내용인데 링이 움직였다 — 추가=%s 축출=%s"
                  % (sorted(added), sorted(gone)))
        if len(holding("860", store.KIND_DISK, E1)) != 1:
            P("★ⓐ-1 disk(E1)이 %d건이 됐다 — 같은 내용이 다시 쌓였다"
              % len(holding("860", store.KIND_DISK, E1)))

        # ⓐ-2 **음성 대조군**: 내용이 새것이면 정확히 1건 쌓이고 1건 잘린다.
        #     (이것이 없으면 위 ⓐ-1은 "적용이 원래 아무것도 안 한다"로도 초록이다.)
        cfg.write_bytes(E2)
        ask, (added, gone) = apply_once("860", "dock", "ⓐ-2")
        if ask is not None:
            if len(ask.get("evicted") or []) != 1:
                P("★ⓐ-2 음성 대조군 무효 — 새 내용인데 축출 예고가 %d건이다(1건이어야 한다)"
                  % len(ask.get("evicted") or []))
            if len(added) != 1 or len(gone) != 1:
                P("★ⓐ-2 음성 대조군 무효 — 새 내용의 적용이 %d건 추가·%d건 축출했다(1·1이어야 한다)"
                  % (len(added), len(gone)))
            elif {row["backup_id"] for row in (ask.get("evicted") or [])} != gone:
                P("★ⓐ-2 예고한 파일과 실제로 지워진 파일이 다르다 — 예고=%s 실제=%s"
                  % (sorted(row["backup_id"] for row in ask.get("evicted") or []), sorted(gone)))

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ **태그가 다르면 같은 내용도 담긴다** (중복 제거는 전역이 아니라 태그별이다)
        # ═══════════════════════════════════════════════════════════════════
        cfg2 = build("861", "PerTag")
        cfg2.write_bytes(E1)
        apply_once("861", "dock", "ⓑ-준비")                        # → disk(E1)
        if not holding("861", store.KIND_DISK, E1):
            P("★ⓑ 준비 실패 — disk(E1)이 링에 없다")
        reg = store.load_registry()
        cfg2.write_bytes(E1)
        engine.save_profile(reg, "861", "dock")                   # dock 슬롯 = E1
        cfg2.write_bytes(E2)
        engine.save_profile(reg, "861", "dock")                   # 덮어쓰기 → profile_dock(E1)
        store.save_registry(reg)
        made = holding("861", store.profile_tag("dock"), E1)
        if len(made) != 1:
            P("★ⓑ `disk`에 같은 내용이 있다고 `profile_dock` 대피본을 %d건 만들었다(1건이어야 "
              "한다) — 되돌릴 곳이 다른 두 행은 서로를 대신하지 못한다(§5-C ⓐ)" % len(made))
        if len(holding("861", store.KIND_DISK, E1)) != 1:
            P("★ⓑ `disk` 쪽 행이 사라졌거나 늘었다 — 태그별 판정이 아니다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓒ 형식 불명(`unknown`)은 판정에 끼지 않는다
        #    — 그것과 같다고 **대피를 건너뛰지 않고**, 그것을 **지우지도 않는다**
        # ═══════════════════════════════════════════════════════════════════
        cfg3 = build("862", "Unknown")
        os.makedirs(store.backups_dir("862"), exist_ok=True)
        store.atomic_write(os.path.join(store.backups_dir("862"), STRANGE), E3)
        if store.parse_backup_id(STRANGE)["kind"] != store.KIND_UNKNOWN:
            P("ⓒ 계측기 무효 — %r가 형식 불명으로 안 읽힌다(잴 것이 없다)" % STRANGE)
        cfg3.write_bytes(E3)
        apply_once("862", "dock", "ⓒ")
        if len(holding("862", store.KIND_DISK, E3)) != 1:
            P("★ⓒ 형식 불명 파일과 내용이 같다는 이유로 대피를 건너뛰었다 — 그 파일은 앱이 만든 "
              "것이 아니고 되돌릴 곳도 다르다(그것으로는 못 되돌린다)")
        if STRANGE not in names("862"):
            P("★ⓒ 형식 불명 파일이 사라졌다 — 중복 정리는 아무것도 지우지 않는다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ·ⓔ 본체가 둘인데 내용이 같다 — **고지도 실제도 1건**, 그러나 봉투는 **둘 다** 싣는다
        # ═══════════════════════════════════════════════════════════════════
        # ★ 슬롯은 **dock 하나만** 둔다: internal 대피본은 태그가 달라 따로 한 건 쌓이므로,
        #   섞어 두면 이 절이 재려는 *"본체 둘 → 대피본 하나"*가 숫자에 묻힌다.
        reg = store.load_registry()
        cfg4 = tmp / "game863" / "video.ini"
        cfg4.parent.mkdir(parents=True, exist_ok=True)
        cfg4.write_bytes(DOCK)
        engine.add_game(reg, "863", str(cfg4), name="TwoBodies")
        engine.save_profile(reg, "863", "dock")
        store.save_registry(reg)
        slot = store.profile_dir("863", "dock")
        # ★ 본체 둘은 **파일명이 바뀐 저장**이 실제로 만드는 상태다(옛 본체가 슬롯에 남는다).
        #   여기서는 그 상태만 필요하므로 파일 하나를 슬롯에 그대로 놓는다 — 내용은 기존 본체와
        #   **같게** 둔다. 그러면 대피 대상은 둘인데 링에 쌓일 것은 한 건이다.
        body = store.profile_file_path("863", "dock")
        store.atomic_write(os.path.join(slot, "video2.ini"), store.read_bytes(body))
        if len(store.evacuable_names("863", "dock")) != 2:
            P("ⓓ 사전 조건 실패 — 본체가 %d개다(2개여야 한다)"
              % len(store.evacuable_names("863", "dock")))
        saturate("863")
        main._CONFIRM_TOKENS.clear()
        ask = rpc(main, "delete_game", "863")
        if not is_confirm(ask):
            P("ⓓ 사전 조건 실패 — 등록 해제가 확인을 요구하지 않았다 (%s)" % ask)
        else:
            preview = params_of(ask).get("evicted") or []
            if len(preview) != 1:
                P("★ⓓ 본체 둘의 내용이 같아 링에는 한 건만 쌓이는데 축출을 %d건 예고했다 — "
                  "확인창이 *일어나지 않을 삭제*를 이름으로 약속한다" % len(preview))
            before = names("863")
            env = rpc(main, "delete_game", "863",
                      confirm_token=params_of(ask).get("confirm_token"))
            if not env.get("ok"):
                P("ⓓ 등록 해제가 실패했다 — %s" % env)
            added, gone = names("863") - before, before - names("863")
            if len(added) != 1 or len(gone) != 1:
                P("★ⓓ 등록 해제가 %d건 추가·%d건 축출했다(1·1이어야 한다)"
                  % (len(added), len(gone)))
            elif {row["backup_id"] for row in preview} != gone:
                P("★ⓓ 예고한 파일과 실제로 지워진 파일이 다르다 — 예고=%s 실제=%s"
                  % (sorted(row["backup_id"] for row in preview), sorted(gone)))
            # ⓔ 봉투는 **본체 이름 전부**를 싣는다 — 한 건만 만들어졌어도.
            saved = (data_of(env).get("evacuated") or {}).get("dock") or []
            if sorted(saved) != ["video.ini", "video2.ini"]:
                P("★ⓔ `evacuated` 봉투가 %s다(본체 이름 둘 다여야 한다) — 「안 만들었으니 뺀다」로 "
                  "고치면 화면이 대피 없이 사라진 진짜 소멸과 구별되지 않는다" % sorted(saved))

        print("백업 링 태그별 중복 제거 — ⓐ 무쓰기·음성 대조군 / ⓑ 태그별 / ⓒ 형식 불명 / "
              "ⓓ 고지==실제 / ⓔ 봉투 (데이터: %s)" % tmp)
        return finish(problems, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish(problems, tmp):
    if problems:
        print("\nFAIL")
        for x in problems:
            print("  " + x)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
