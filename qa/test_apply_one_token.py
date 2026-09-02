#!/usr/bin/env python3
"""개별 적용의 확인 토큰을 행위 수준에서 검사한다.

잠그는 것:
  ① 무토큰 1차 호출 뒤 tmp 전 파일의 sha1이 같다
  ② 위조·재사용·만료 토큰은 거부된다
  ③ 저장·일괄 적용·복원 토큰으로 개별 적용이 통과하지 않는다
  ④ dock 토큰은 internal 적용에서 거부되고, 같은 dock 적용에서는 통과한다
  ⑤ 확인 뒤 게임 설정이 바뀌면 낡은 토큰은 거부된다

④의 픽스처는 두 슬롯 내용을 같게 만든다. 다만 이 파일은 두 방향의 전체 지문 동일성을
단언하지 않으므로, ④의 거부가 scope 차이만으로 났다고 독립적으로 증명하지는 않는다.

합성 데이터만 쓴다. `DECKY_PLUGIN_RUNTIME_DIR`과 `GFXPROFILE_HOME`은 tmp를 가리킨다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPID = "777"
SAME = b"quality=same\nshadows=same\nsource=BOTH-SLOTS-X\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"
OTHER = b"quality=othr\nshadows=var_\nsource=GAME-REWROTE\n"


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


def world_sha(tmp):
    import hashlib
    out = {}
    for base, _, names in os.walk(tmp):
        for name in names:
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, tmp)] = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                out[os.path.relpath(path, tmp)] = "unreadable"
    return out


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-apply-token-"))
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

        # ── 세계: 두 슬롯의 내용이 같다 — 그래야 ④가 지문이 아닌 방향을 잰다 ───
        reg = store.load_registry()
        cfg = tmp / "game" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(SAME)
        engine.add_game(reg, APPID, str(cfg), name="ApplyToken")
        engine.save_profile(reg, APPID, "dock")
        engine.save_profile(reg, APPID, "internal")
        store.save_registry(reg)
        if store.load_meta(APPID, "dock")["sha1"] != store.load_meta(APPID, "internal")["sha1"]:
            P("사전 조건 실패 — 두 슬롯의 내용이 다르다. 방향 결박을 잴 수 없다")

        # ═══════════════════════════════════════════════════════════════════
        # ① 무토큰 1차 = 무쓰기
        # ═══════════════════════════════════════════════════════════════════
        cfg.write_bytes(EDITED)
        main._CONFIRM_TOKENS.clear()
        before = world_sha(tmp)
        env = rpc(main, "apply_profile", APPID, "dock")
        if not is_confirm(env):
            P("★① 두 슬롯 모두와 다른데 확인을 요구하지 않았다 — %s" % env)
            return finish(problems, tmp)
        after = world_sha(tmp)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if changed:
            P("★① 확인 요구 단계가 파일을 바꿨다 — %s" % changed[:6])
        for key in ("confirm_token", "appid", "profile", "disk_state", "matches", "evicted"):
            if key not in params_of(env):
                P("① 확인창이 쓸 %s가 params에 없다" % key)
        if params_of(env).get("disk_state") != "unknown":
            P("① 손으로 고친 파일의 4분류가 unknown이 아니다 — %s" % params_of(env).get("disk_state"))
        if params_of(env).get("matches"):
            P("① 어느 슬롯과도 다른데 matches가 비어 있지 않다 — %s" % params_of(env).get("matches"))
        tok_dock = params_of(env).get("confirm_token")

        # ═══════════════════════════════════════════════════════════════════
        # ④ 방향 바인딩 — dock 토큰은 internal 적용에 소비되지 않는다
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "apply_profile", APPID, "internal", confirm_token=tok_dock)
        if not is_confirm(env):
            P("★④ dock 확인 토큰이 internal 적용에 소비됐다 — 사용자가 확인한 것과 **다른 방향**의 "
              "쓰기가 확인 없이 실행된다 (%s)" % env)
        if cfg.read_bytes() != EDITED:
            P("★④ 방향이 뒤바뀐 토큰으로 설정 파일이 실제로 바뀌었다")

        # 음성 대조군 — 원래 방향에서는 통과한다(아무 토큰이나 거부하는 것이 아니다)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "apply_profile", APPID, "dock")
        tok_dock = params_of(env).get("confirm_token")
        env = rpc(main, "apply_profile", APPID, "dock", confirm_token=tok_dock)
        if not env.get("ok") or data_of(env).get("outcome") != "applied":
            P("★④ 음성 대조군 실패 — 같은 방향의 정상 토큰도 거부됐다(방어가 과하다) (%s)" % env)
        if cfg.read_bytes() != SAME:
            P("④ 음성 대조군: 적용이 실제로 일어나지 않았다")

        # ② 재사용 — 방금 쓴 토큰은 다시 통과하지 못한다
        cfg.write_bytes(EDITED)
        env = rpc(main, "apply_profile", APPID, "dock", confirm_token=tok_dock)
        if not is_confirm(env):
            P("★② 소각된 토큰이 다시 통과했다 (%s)" % env)
        # ② 위조
        env = rpc(main, "apply_profile", APPID, "dock", confirm_token="지어낸-토큰")
        if not is_confirm(env):
            P("★② 지어낸 토큰이 통과했다 (%s)" % env)
        if cfg.read_bytes() != EDITED:
            P("★② 거부인데 설정 파일이 바뀌었다")
        # ② 만료
        main._CONFIRM_TOKENS.clear()
        tok = params_of(rpc(main, "apply_profile", APPID, "dock")).get("confirm_token")
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0
        try:
            env = rpc(main, "apply_profile", APPID, "dock", confirm_token=tok)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env):
            P("★② 만료된 토큰이 통과했다 (%s)" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ TOCTOU — 확인창 사이에 게임이 설정을 다시 쓰면 낡은 토큰은 무효다
        #    (사용자가 본 "무엇을 덮어쓰는가"가 이미 낡았다)
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        tok = params_of(rpc(main, "apply_profile", APPID, "dock")).get("confirm_token")
        cfg.write_bytes(OTHER)                       # 게임이 종료하며 다시 썼다
        env = rpc(main, "apply_profile", APPID, "dock", confirm_token=tok)
        if not is_confirm(env):
            P("★⑤ 확인창 사이 설정 파일이 바뀌었는데 낡은 토큰이 통과했다 (%s)" % env)
        if cfg.read_bytes() != OTHER:
            P("★⑤ 거부인데 설정 파일이 바뀌었다")

        # ═══════════════════════════════════════════════════════════════════
        # ③ scope 혼동 — 저장·복원·일괄 토큰으로 개별 적용
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        save_tok = params_of(rpc(main, "save_profile", APPID, "dock")).get("confirm_token")
        bulk_tok = params_of(rpc(main, "apply_all", "dock")).get("confirm_token")
        store.make_backup(APPID, b"quality=bkup\nshadows=old_\nsource=FOREIGN-TOKEN\n",
                          "disk", "video.ini")
        newest = os.path.basename(store.list_backups(APPID)[0])
        restore_tok = params_of(rpc(main, "restore_backup", APPID, newest)).get("confirm_token")
        for label, foreign in (("저장", save_tok), ("일괄", bulk_tok), ("복원", restore_tok)):
            if not foreign:
                P("③ %s 토큰을 못 얻었다 — scope 혼동을 시험할 수 없다" % label)
                continue
            env = rpc(main, "apply_profile", APPID, "dock", confirm_token=foreign)
            if not is_confirm(env):
                P("★③ %s 토큰으로 개별 적용이 통과했다 — scope가 안 갈린다 (%s)" % (label, env))
        if cfg.read_bytes() != OTHER:
            P("★③ 남의 토큰으로 설정 파일이 바뀌었다")

        print("개별 적용 토큰 — 무쓰기 1차 · 방향 결박 · scope 3종 · TOCTOU (데이터: %s)" % tmp)
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
