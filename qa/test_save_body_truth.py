#!/usr/bin/env python3
"""**저장이 무엇을 잃는가는 기록이 아니라 본체가 정한다** (설계 §14-G ⓐ).

`engine.save_profile`은 `if old:`로, `confirm.needs_confirm`은 `if not meta:`로 갈렸다.
슬롯의 `meta.json`이 없거나 `{}`·`[]`·`null`·`false`·`0`·`""`이면 둘 다 *"빈 슬롯이라 잃을 것이
없다"*로 접어 **정상 본체가 바로 옆에 있어도 확인 없이·대피 없이** 덮었다 — 그 프로필은 슬롯에도
백업 링에도 안 남는다. 앱이 스스로 그 상태를 만드는 경로가 둘이고(새 슬롯 저장 중 meta 쓰기 실패 /
삭제의 `rmtree` 중단), 그 상태에서 화면은 「프로필 없음」이라 **사용자의 자연스러운 재저장이 곧
파괴 트리거**였다.

### 왜 새 파일인가 — **이 동작을 지키던 검사가 없었다**
설계 §15 머리말의 실측이다: 판정 지점을 바꿔도 회귀가 반응하지 않았다. 정책층(`confirm`)과
엔진 중 **하나만** 고쳐도 회귀는 초록이었고, 그 반쪽은 각각 *"묻기는 하는데 승인하면 여전히
무백업 삭제"* 와 *"안 물어보고 대피만"* 이다. 그래서 여기서는 **두 층을 한 왕복으로** 잰다 —
route로 확인을 받고, 토큰으로 승인하고, **링에 그 내용이 실제로 들어갔는지**까지 본다.

이 파일이 잠그는 것:
  ⓐ 기록이 비어도(7종) **본체가 있으면** 저장은 묻고, 승인 후 그 본체가 **링에 남는다**
     — 그때 확인창이 대는 **숫자도 본체 실측**이다: 기록이 비었다고 *"지금 저장돼 있는 것: 0 B"*라 말하면
     바로 옆에 멀쩡한 본체가 있는데 **거짓을 보이는** 것이다
  ⓑ **진짜 빈 슬롯**(본체 0 · 부산물만)은 안 묻고 안 대피한다 — 정상 사용이 확인창을 만나면 안 된다
  ⓒ **본체가 여럿**이면 대피도 그 수만큼이고, **축출 예고와 실제 축출이 이름까지 같다**
  ⓓ **링크뿐인 슬롯은 빈 슬롯**이다(2026-08-22 사용자 결정) — 안 묻고, 링크가 가리키는
     바깥 파일은 한 바이트도 안 바뀐다(`atomic_write`가 링크를 **대체**할 뿐이다)
  ⓔ **읽을 수 없는 meta**(잘린 JSON)는 예전처럼 **예외로 접힌다** — 안 묻고, 아무것도 쓰지 않고
     `PROFILE_META_CORRUPT`로 실패한다. 경계는 *"JSON을 읽을 수 있느냐"*이지 *"읽은 결과가
     참이냐"*가 아니다(전자를 넓히면 잘린 JSON에서 손상 슬롯에 덧쓰게 된다)

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
SAVED = b"quality=saved\nshadows=high\nsource=SLOT-BODY---\n"     # 슬롯에 들어 있는 본체
SECOND = b"quality=2nd__\nshadows=mid_\nsource=SLOT-BODY-2-\n"    # 두 번째 본체(이름이 바뀐 저장의 잔존)
EDITED = b"quality=edit\nshadows=low_\nsource=USER-EDITED--\n"    # 지금 게임 설정 파일
OUTSIDE = b"quality=outs\nshadows=none\nsource=OUTSIDE-FILE-\n"   # 슬롯 **바깥**의 파일(링크 대상)

#: 「기록이 비었다」의 전 형태. **없음**까지 포함한다 — 실물에서 가장 흔한 모양이다.
EMPTY_METAS = [("없음", None), ("{}", "{}"), ("[]", "[]"), ("null", "null"),
               ("false", "false"), ("0", "0"), ('""', '""')]


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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-save-body-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []

        def P(msg):
            problems.append(msg)

        def params_of(env):
            return env.get("params") or {}

        def names(appid):
            return {os.path.basename(p) for p in store.list_backups(appid)}

        def backup_bodies(appid):
            """링에 실제로 담긴 **내용**들. "대피했다"는 경로가 아니라 이것으로 증명한다."""
            out = []
            for path in store.list_backups(appid):
                try:
                    with open(path, "rb") as fh:
                        out.append(fh.read())
                except OSError:
                    pass
            return out

        def mkgame(appid, name):
            """dock 슬롯에 본체+기록이 정상으로 들어 있는 게임 하나."""
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(SAVED)
            engine.add_game(reg, appid, str(cfg), name=name)
            engine.save_profile(reg, appid, "dock")               # 슬롯 = SAVED
            store.save_registry(reg)
            cfg.write_bytes(EDITED)                               # 디스크는 달라진다 = 덮어쓰기 저장
            return cfg

        def break_meta(appid, content):
            path = store.profile_meta_path(appid, "dock")
            if content is None:
                os.unlink(path)
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)

        def fill_ring(appid):
            """링을 가득 채운다 — 이름을 갈라 둬야 축출 대상을 이름으로 대조할 수 있다."""
            while len(names(appid)) < store.BACKUP_KEEP:
                i = len(names(appid))
                store.make_backup(appid, b"filler-%02d\n" % i, "disk", "fill%02d.ini" % i)

        def tail(appid, n):
            """지금 목록의 **가장 오래된 n건**(= 다음 n건이 쌓이면 잘릴 것)."""
            return [os.path.basename(p) for p in store.list_backups(appid)[-n:]] if n else []

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 기록이 비어도 **본체가 있으면** 묻고, 그 본체가 링에 남는다
        # ═══════════════════════════════════════════════════════════════════
        for i, (label, content) in enumerate(EMPTY_METAS):
            appid = "70%d" % i
            mkgame(appid, "EmptyMeta-%s" % label)
            break_meta(appid, content)
            main._CONFIRM_TOKENS.clear()

            env = rpc(main, "save_profile", appid, "dock")
            if env.get("code") != codes.CONFIRM_REQUIRED:
                P("★ⓐ[meta=%s] 본체가 있는데 확인 없이 저장했다 — 그 프로필은 슬롯에도 링에도 "
                  "안 남는다 (%s)" % (label, env.get("code") or env))
                continue
            # ★ 확인창이 말하는 숫자는 **기록이 아니라 본체**에서 나와야 한다. meta를 못 믿는 것이
            #   이 갈래의 전제인데 그 meta로 재료를 채우면, 화면은 멀쩡한 본체를 옆에 두고
            #   *"지금 저장돼 있는 것: 0 B"*라 말한다 — 무엇을 잃는지 대는 자리에서의 거짓이다.
            got = params_of(env)
            if got.get("size") != len(SAVED):
                P("★ⓐ[meta=%s] 확인창의 크기가 사실이 아니다 — 화면=%r B / 실제 본체=%d B"
                  % (label, got.get("size"), len(SAVED)))
            if got.get("sha1_short") != store.sha1_bytes(SAVED)[:10]:
                P("★ⓐ[meta=%s] 본체가 하나인데 해시를 못 대거나 틀리게 댔다 — 화면=%r / 실측=%r"
                  % (label, got.get("sha1_short"), store.sha1_bytes(SAVED)[:10]))
            env = rpc(main, "save_profile", appid, "dock",
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓐ[meta=%s] 승인 후 저장이 실패했다 — %s" % (label, env))
                continue
            if SAVED not in backup_bodies(appid):
                P("★ⓐ[meta=%s] 묻기는 했는데 **대피가 없다** — 승인 뒤 옛 본체가 링에 없다 "
                  "(링=%d칸)" % (label, len(names(appid))))
            body = tmp / "data" / "profiles" / appid / "dock" / "video.ini"
            if body.read_bytes() != EDITED:
                P("ⓐ[meta=%s] 저장이 새 내용을 슬롯에 안 썼다" % label)

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 진짜 빈 슬롯 — 부산물만 있으면 **안 묻고 안 대피한다**
        #    (뒤집히면 초기 세팅의 정상 저장이 매번 확인창을 만난다)
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        cfg800 = tmp / "game800" / "video.ini"
        cfg800.parent.mkdir(parents=True, exist_ok=True)
        cfg800.write_bytes(EDITED)
        engine.add_game(reg, "800", str(cfg800), name="ReallyEmpty")
        store.save_registry(reg)
        slot800 = pathlib.Path(store.profile_dir("800", "dock"))
        slot800.mkdir(parents=True, exist_ok=True)
        (slot800 / store.APPLIED_NAME).write_text("dock\n")          # 옛 버전이 남긴 마커
        (slot800 / (store.TMP_PREFIX + "crash")).write_bytes(b"half written\n")   # 크래시 잔재
        main._CONFIRM_TOKENS.clear()
        before800 = names("800")
        env = rpc(main, "save_profile", "800", "dock")
        if env.get("code") == codes.CONFIRM_REQUIRED:
            P("★ⓑ 부산물뿐인 빈 슬롯인데 확인을 요구했다 — 정상 세팅이 매번 확인창을 만난다 (%s)"
              % params_of(env))
        elif not env.get("ok"):
            P("ⓑ 빈 슬롯 저장이 실패했다 — %s" % env)
        if names("800") != before800:
            P("★ⓑ 잃을 것이 없는 저장이 링을 움직였다 — %s" % (names("800") ^ before800))

        # ═══════════════════════════════════════════════════════════════════
        # ⓒ 본체가 **여럿**이면 대피도 그 수만큼이고, 예고와 실제가 이름까지 같다
        #    (파일명이 바뀐 저장은 옛 본체를 슬롯에 남긴다 = 실제로 도달하는 상태)
        # ═══════════════════════════════════════════════════════════════════
        cfg810 = mkgame("810", "TwoBodies")
        slot810 = pathlib.Path(store.profile_dir("810", "dock"))
        (slot810 / "legacy.cfg").write_bytes(SECOND)                 # 두 번째 본체
        break_meta("810", "{}")
        fill_ring("810")
        main._CONFIRM_TOKENS.clear()

        env = rpc(main, "save_profile", "810", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("★ⓒ 사전 조건 실패 — 본체 2개인데 묻지 않았다 (%s)" % env)
        else:
            # ★ 본체가 둘이면 크기는 **합**이고 해시는 **비운다**: 둘 중 하나를 골라 대면
            #   화면이 *어느 것의 해시인지 말할 수 없는 값*을 사실처럼 내놓는다.
            two = params_of(env)
            if two.get("size") != len(SAVED) + len(SECOND):
                P("★ⓒ 본체가 2개인데 화면의 크기가 합이 아니다 — 화면=%r B / 실제=%d B"
                  % (two.get("size"), len(SAVED) + len(SECOND)))
            if two.get("sha1_short"):
                P("★ⓒ 본체가 2개인데 해시 하나를 댔다 — %r (어느 본체의 것인지 말할 수 없다)"
                  % two.get("sha1_short"))
            foretold = [row["backup_id"] for row in params_of(env).get("evicted") or []]
            expected = tail("810", 2)          # 백업 2건이 들어오면 잘릴 것 = 가장 오래된 2건
            if foretold != expected:
                P("★ⓒ 축출 **예고**가 실제 대피 건수와 안 맞는다(adding=1 하드코딩) — "
                  "예고=%s / 실제로 잘릴 것=%s" % (foretold, expected))
            before810 = names("810")
            env = rpc(main, "save_profile", "810", "dock",
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓒ 승인 후 저장이 실패했다 — %s" % env)
            gone = before810 - names("810")
            if gone != set(expected):
                P("★ⓒ 예고한 이름과 **실제로 지워진 이름**이 다르다 — 지워진 것=%s / 예고=%s"
                  % (gone, set(expected)))
            bodies = backup_bodies("810")
            missing = [tag for tag, data in (("본체1", SAVED), ("본체2", SECOND))
                       if data not in bodies]
            if missing:
                P("★ⓒ 본체가 2개인데 대피가 빠졌다 — 링에 없는 것: %s" % ", ".join(missing))

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ 링크뿐인 슬롯은 **빈 슬롯**이다 (2026-08-22 사용자 결정)
        #    앱이 만들지 않은 상태까지 앱이 책임지지 않는다 → 조용히 덮는다. 안전한 이유는
        #    `atomic_write`가 tmp→rename이라 **링크를 대체**할 뿐 대상 파일에 안 쓰기 때문이다.
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        cfg820 = tmp / "game820" / "video.ini"
        cfg820.parent.mkdir(parents=True, exist_ok=True)
        cfg820.write_bytes(EDITED)
        engine.add_game(reg, "820", str(cfg820), name="LinkOnly")
        store.save_registry(reg)
        outside = tmp / "outside.ini"
        outside.write_bytes(OUTSIDE)
        slot820 = pathlib.Path(store.profile_dir("820", "dock"))
        slot820.mkdir(parents=True, exist_ok=True)
        os.symlink(str(outside), str(slot820 / "video.ini"))         # 슬롯 안에는 링크뿐
        # ★ 술어 **두 개가 같은 답**을 내야 한다: 예전에는 `slot_body_exists`만 `os.path.isfile`로
        #   링크를 따라가 「본체 있음」이라 답했고 `evacuable_names`는 링크를 뺐다. 그 상태로
        #   저장 갈래를 판정하면 **묻고도 대피할 것이 없다**(대피 목록이 비어 있으므로).
        #   판정의 문이 하나라는 것은 이 두 답이 갈리지 않는다는 뜻이다.
        if store.slot_body_exists("820", "dock") or store.evacuable_names("820", "dock"):
            P("★ⓓ 링크뿐인 슬롯이 「본체 있음」으로 읽힌다 — slot_body_exists=%s / evacuable_names=%s "
              "(둘이 갈리면 묻고도 대피할 것이 없는 갈래가 생긴다)"
              % (store.slot_body_exists("820", "dock"), store.evacuable_names("820", "dock")))
        main._CONFIRM_TOKENS.clear()
        before820 = names("820")
        env = rpc(main, "save_profile", "820", "dock")
        if env.get("code") == codes.CONFIRM_REQUIRED:
            P("★ⓓ 링크뿐인 슬롯인데 확인을 요구했다 — 사용자 결정은 「빈 슬롯으로 보고 조용히 덮는다」다")
        elif not env.get("ok"):
            P("ⓓ 링크뿐인 슬롯 저장이 실패했다 — %s" % env)
        if names("820") != before820:
            P("★ⓓ 링크를 대피시켰다 — 슬롯 바깥 파일이 백업 링에 복사됐다(`.sav` 경계) %s"
              % (names("820") ^ before820))
        if outside.read_bytes() != OUTSIDE:
            P("★★ⓓ 링크가 **가리키던 바깥 파일**이 덮였다 — 저장이 링크를 따라갔다")
        if (slot820 / "video.ini").is_symlink():
            P("ⓓ 저장 뒤에도 슬롯이 링크다 — atomic_write가 대체하지 않았다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓔ 읽을 수 없는 meta는 **예외로 접힌다** — 안 묻고, 아무것도 안 쓰고 실패한다
        #    (여기를 「참이냐」 쪽으로 넓히면 손상 슬롯에 덧쓰게 된다)
        # ═══════════════════════════════════════════════════════════════════
        mkgame("830", "UnreadableMeta")
        break_meta("830", "{ not json at all")
        main._CONFIRM_TOKENS.clear()
        before830 = names("830")
        env = rpc(main, "save_profile", "830", "dock")
        if env.get("code") == codes.CONFIRM_REQUIRED:
            P("★ⓔ 잘린 JSON에서 확인창이 떴다 — 예외 갈래가 「본체 실측」으로 넓어졌다")
        elif env.get("code") != codes.PROFILE_META_CORRUPT:
            P("★ⓔ 손상 meta 저장의 실패 코드가 %r다 — %r여야 복구 안내가 맞는다"
              % (env.get("code"), codes.PROFILE_META_CORRUPT))
        body830 = pathlib.Path(store.profile_dir("830", "dock")) / "video.ini"
        if body830.read_bytes() != SAVED or names("830") != before830:
            P("★ⓔ 손상 meta 저장이 **무언가 썼다** — 본체 또는 링이 움직였다")

        print("저장의 본체 실측 — 빈 기록 %d종 · 빈 슬롯 · 본체 2개 · 링크 · 잘린 JSON "
              "(데이터: %s)" % (len(EMPTY_METAS), tmp))
        if problems:
            print("\nFAIL")
            for x in problems:
                print("  " + x)
            return 1
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
