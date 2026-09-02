#!/usr/bin/env python3
"""저장이 무엇을 잃는가는 슬롯의 기록(meta)이 아니라 본체가 정한다.

기록으로 판정하면 `meta.json`이 없거나 `{}`·`null`처럼 비어 있을 때, 정상 본체가 바로 옆에
있어도 「빈 슬롯이라 잃을 것이 없다」로 접혀 확인 없이·대피 없이 덮인다 — 그 프로필은
슬롯에도 백업 링에도 남지 않는다.

정책층(`confirm.needs_confirm`)과 엔진(`engine.save_profile`)이 각각 판정하므로 한 층만
재는 검사로는 이 계약이 안 잠긴다. 그래서 route로 확인을 받고, 토큰으로 승인하고,
링에 그 내용이 실제로 들어갔는지까지 한 왕복으로 잰다.

이 파일이 재는 것:
  ⓐ `EMPTY_METAS`의 기록마다 — 본체가 있으면 저장은 묻고, 승인 뒤 그 본체가 링에 남는다.
     확인창이 대는 크기·해시도 본체 실측이고, 기록이 없으면 저장 시각은 대지 않는다
     (없는 값을 mtime으로 메우면 「무엇을 잃는가」를 대는 자리에서의 거짓이다)
  ⓑ 진짜 빈 슬롯(부산물만 있는 슬롯)은 안 묻고 안 대피한다
  ⓒ 본체가 여럿이면 크기는 합이고 해시는 비며, 축출 예고와 실제로 지워진 이름이 같다
  ⓓ 링크뿐인 슬롯은 빈 슬롯이다 — 안 묻고, 링크가 가리키는 바깥 파일은 안 바뀐다
     (`store.atomic_write`가 tmp→rename이라 링크를 대체할 뿐이다)
  ⓔ 읽을 수 없는 meta(잘린 JSON)는 안 묻고, 아무것도 쓰지 않고 `PROFILE_META_CORRUPT`로
     실패한다. 경계는 「JSON을 읽을 수 있느냐」이지 「읽은 결과가 참이냐」가 아니다
  ⓕ 점으로 시작하는 본체(`.gamerc`)도 본체다 — 등록 게이트는 점파일을 막지 않으므로
     대피에서만 빼면 정상 등록된 프로필이 확인도 대피도 없이 사라진다
  ⓖ 비-UTF8 meta도 ⓔ와 같은 갈래다 — `json.load`가 내는 `UnicodeDecodeError`는
     `ValueError`의 하위형이라 같은 핸들러에 걸린다. 예외 목록을 JSON 구문 오류로 좁히면
     이 갈래가 빠져나가 사용자는 원인과 다른 `UNEXPECTED`를 받는다

합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp라 실사용 데이터에
닿을 수 없다.
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
SECOND = b"quality=2nd__\nshadows=mid_\nsource=SLOT-BODY-2-\n"    # 두 번째 본체
EDITED = b"quality=edit\nshadows=low_\nsource=USER-EDITED--\n"    # 지금 게임 설정 파일
OUTSIDE = b"quality=outs\nshadows=none\nsource=OUTSIDE-FILE-\n"   # 슬롯 바깥의 파일(링크 대상)

#: 「기록을 못 믿는다」의 전 형태 — 없음까지 포함한다.
#: 마지막 것은 비지 않았는데 크기·해시가 없는 기록이다: 판정이 「기록이 통째로 비었나」면
#:   이 갈래는 실측을 못 받아 확인창이 "지금 저장돼 있는 것: 0 B"라 말한다. 기준은 필드 단위다.
EMPTY_METAS = [("없음", None), ("{}", "{}"), ("[]", "[]"), ("null", "null"),
               ("false", "false"), ("0", "0"), ('""', '""'),
               ("무관한 키만", '{"foo": 1}')]


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
            """링에 실제로 담긴 내용들. "대피했다"는 경로가 아니라 이것으로 증명한다."""
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
            """지금 목록의 정렬 꼬리 n건(= 다음 n건이 쌓이면 잘릴 자리)."""
            return [os.path.basename(p) for p in store.list_backups(appid)[-n:]] if n else []

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ 기록이 비어도 본체가 있으면 묻고, 그 본체가 링에 남는다
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
            # 확인창이 말하는 숫자는 기록이 아니라 본체에서 나와야 한다. meta를 못 믿는 것이
            #   이 갈래의 전제인데 그 meta로 재료를 채우면, 화면은 멀쩡한 본체를 옆에 두고
            #   "지금 저장돼 있는 것: 0 B"라 말한다 — 무엇을 잃는지 대는 자리에서의 거짓이다.
            got = params_of(env)
            if got.get("size") != len(SAVED):
                P("★ⓐ[meta=%s] 확인창의 크기가 사실이 아니다 — 화면=%r B / 실제 본체=%d B"
                  % (label, got.get("size"), len(SAVED)))
            if got.get("sha1_short") != store.sha1_bytes(SAVED)[:10]:
                P("★ⓐ[meta=%s] 본체가 하나인데 해시를 못 대거나 틀리게 댔다 — 화면=%r / 실측=%r"
                  % (label, got.get("sha1_short"), store.sha1_bytes(SAVED)[:10]))
            # 크기·해시는 본체에서 재지만 저장 시각은 재지 않는다. 기록이 없으면 저장 시각은
            #   모르는 것이 사실이고, 파일 mtime은 저장 시각이 아니다(복사·복원·터치로도 바뀐다).
            #   없는 값을 그럴듯한 값으로 메우는 것은 실측이 아니라 지어내기이고, 이 확인창은
            #   「무엇을 잃는가」를 대는 자리라 지어낸 한 줄이 곧 거짓말이다.
            if got.get("saved_at"):
                P("★ⓐ[meta=%s] 기록이 없는데 저장 시각을 댔다 — 화면=%r (mtime을 끌어다 쓰면 "
                  "복사·복원·터치가 만든 시각을 '저장한 시각'이라 말하게 된다)"
                  % (label, got.get("saved_at")))
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
        # ⓑ 진짜 빈 슬롯 — 부산물만 있으면 안 묻고 안 대피한다
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
        # ⓒ 본체가 여럿이면 대피도 그 수만큼이고, 예고와 실제가 이름까지 같다
        #    앱이 그 상태를 만들지는 않는다: 같은 appid 재등록은 등록 route가
        #      `ALREADY_REGISTERED`로 거부하고, 슬롯 복원은 그 슬롯이 쓰던 이름을 유지한다.
        #      그래도 재는 이유는 밖에서 들어온 파일·중단된 삭제 잔재로 본체가 둘이 될 수 있고,
        #      그때 한 개만 대피시키면 나머지가 고지 없이 사라지기 때문이다.
        #      아래는 그 상태를 직접 놓아 만든다.
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
            # 본체가 둘이면 크기는 합이고 해시는 비운다: 둘 중 하나를 골라 대면
            #   화면이 어느 것의 해시인지 말할 수 없는 값을 사실처럼 내놓는다.
            two = params_of(env)
            if two.get("size") != len(SAVED) + len(SECOND):
                P("★ⓒ 본체가 2개인데 화면의 크기가 합이 아니다 — 화면=%r B / 실제=%d B"
                  % (two.get("size"), len(SAVED) + len(SECOND)))
            if two.get("sha1_short"):
                P("★ⓒ 본체가 2개인데 해시 하나를 댔다 — %r (어느 본체의 것인지 말할 수 없다)"
                  % two.get("sha1_short"))
            foretold = [row["backup_id"] for row in params_of(env).get("evicted") or []]
            expected = tail("810", 2)          # 백업 2건이 들어오면 잘릴 정렬 꼬리 2건
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
        # ⓓ 링크뿐인 슬롯은 빈 슬롯이다
        #    앱이 만들지 않은 상태까지 앱이 책임지지 않는다 → 조용히 덮는다. 안전한 이유는
        #    `atomic_write`가 tmp→rename이라 링크를 대체할 뿐 대상 파일에 안 쓰기 때문이다.
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
        # 술어 두 개가 같은 답을 내야 한다: 갈리면 묻고도 대피할 것이 없는 갈래가 생긴다
        #   (대피 목록이 비어 있으므로). 판정의 문이 하나라는 것은 이 두 답이 갈리지 않는다는 뜻이다.
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
        # ⓔ 읽을 수 없는 meta는 예외로 접힌다 — 안 묻고, 아무것도 안 쓰고 실패한다
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

        # ═══════════════════════════════════════════════════════════════════
        # ⓕ 점으로 시작하는 본체(`.gamerc`)도 본체다 — 저장 왕복
        #    등록 게이트(G14)에는 점파일을 막는 규칙이 없다(`.gamerc`는 리눅스 게임의 정상
        #    설정 파일이다). 그러니 대피에서만 점파일을 빼면 정상 등록된 프로필이
        #    확인도 대피도 없이 소멸한다 — 그 교집합이 이 갈래가 지키는 것이다.
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        cfg840 = tmp / "game840" / ".gamerc"
        cfg840.parent.mkdir(parents=True, exist_ok=True)
        cfg840.write_bytes(SAVED)
        engine.add_game(reg, "840", str(cfg840), name="DotfileBody")   # G14를 정상 통과한다
        engine.save_profile(reg, "840", "dock")                        # 빈 슬롯 → 그냥 저장
        store.save_registry(reg)
        if store.evacuable_names("840", "dock") != [".gamerc"]:
            P("★ⓕ 점파일 본체가 **빈 슬롯**으로 읽힌다 — evacuable_names=%s "
              "(앱이 자기가 저장한 프로필을 못 본다)" % store.evacuable_names("840", "dock"))
        cfg840.write_bytes(EDITED)                                     # 내용이 달라졌다
        main._CONFIRM_TOKENS.clear()
        before840 = names("840")
        env = rpc(main, "save_profile", "840", "dock")
        if env.get("code") != codes.CONFIRM_REQUIRED:
            P("★ⓕ 점파일 프로필을 **확인 없이** 덮었다 — 사용자가 저장해 둔 `.gamerc`가 "
              "고지 없이 사라진다 (%s)" % (env.get("code") or env))
        else:
            if names("840") != before840:
                P("★ⓕ 확인을 요구하면서 링이 이미 움직였다 — 묻기 전에 쓴 것이다")
            env = rpc(main, "save_profile", "840", "dock",
                      confirm_token=params_of(env).get("confirm_token"))
            if not env.get("ok"):
                P("ⓕ 승인 후 저장이 실패했다 — %s" % env)
        if SAVED not in backup_bodies("840"):
            P("★ⓕ 점파일 본체가 **대피되지 않았다** — 옛 내용이 링에 없다(되찾을 길이 없다)")
        body840 = pathlib.Path(store.profile_dir("840", "dock")) / ".gamerc"
        if body840.read_bytes() != EDITED:
            P("ⓕ 저장이 새 내용을 슬롯에 안 썼다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓖ 읽을 수 없는 meta는 잘린 JSON만이 아니다 — 비-UTF8 바이트도 같은 갈래다
        #    `json.load`는 이때 `UnicodeDecodeError`를 낸다(= `ValueError`의 하위형).
        #    예외 목록을 `json.JSONDecodeError`로 좁히면 이 갈래가 핸들러를 빠져나가
        #    사용자는 원인과 다른 `UNEXPECTED`를 받는다(복구 안내가 통째로 어긋난다).
        #    ⓔ와 같은 결과를 요구한다: 안 묻고, 아무것도 안 쓰고, 사유를 밝히며 실패.
        # ═══════════════════════════════════════════════════════════════════
        mkgame("850", "NonUtf8Meta")
        with open(store.profile_meta_path("850", "dock"), "wb") as fh:
            fh.write(b'{"filename": "video.ini", "sha1": "\xff\xfe not utf-8"}')
        main._CONFIRM_TOKENS.clear()
        before850 = names("850")
        env = rpc(main, "save_profile", "850", "dock")
        if env.get("code") == codes.CONFIRM_REQUIRED:
            P("★ⓖ 비-UTF8 meta에서 확인창이 떴다 — 예외 갈래가 「본체 실측」으로 넓어졌다")
        elif env.get("code") != codes.PROFILE_META_CORRUPT:
            P("★ⓖ 비-UTF8 meta 저장의 실패 코드가 %r다 — %r여야 복구 안내가 맞는다 "
              "(예외 목록을 JSON 구문 오류로 좁히면 여기가 UNEXPECTED로 샌다)"
              % (env.get("code"), codes.PROFILE_META_CORRUPT))
        body850 = pathlib.Path(store.profile_dir("850", "dock")) / "video.ini"
        if body850.read_bytes() != SAVED or names("850") != before850:
            P("★ⓖ 비-UTF8 meta 저장이 **무언가 썼다** — 본체 또는 링이 움직였다")

        print("저장의 본체 실측 — 빈 기록 %d종 · 빈 슬롯 · 본체 2개 · 링크 · 잘린 JSON · "
              "점파일 본체 · 비-UTF8 meta (데이터: %s)" % (len(EMPTY_METAS), tmp))
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
