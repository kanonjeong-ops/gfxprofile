#!/usr/bin/env python3
"""복원 토큰이 **목적지와 백업 파일에 결박되는가** — 설계 §5-F-1 (반증 A4 잠금).

### 무엇이 문제였나 (실물 재현)
12판 토큰의 슬롯은 `(appid, "restore_backup", 디스크 지문, 백업 지문)` 네 칸이고
**어느 백업 행인지도, 어디로 되돌리는지도 안 묶였다.** 그래서 두 슬롯의 내용이 같고 두
프로필 대피본의 내용도 같으면, dock 확인창에서 받은 토큰으로 **internal 슬롯을 덮어쓸 수 있다** —
사용자가 확인한 곳과 다른 곳에 쓰기가 일어난다.

### 이 테스트가 세우는 세계 (그 재현을 그대로 만든다)
    dock 슬롯 = internal 슬롯 = `C`          → 대상 지문이 **바이트 동일**
    profile_dock 백업 = profile_internal 백업 = `R`   → 백업 지문도 **바이트 동일**
즉 **토큰의 네 칸 중 세 칸이 같고, 갈리는 것은 슬롯 2의 합성 문자열뿐**이다.
결박이 없으면 토큰이 그대로 넘어간다 — 이 테스트가 재는 것이 정확히 그 한 칸이다.

잠그는 것:
  ⓐ dock 확인 토큰으로 **internal 백업** 호출 → 거부
  ⓑ 같은 조합에서는 **통과**한다 (= "아무 토큰이나 거부"가 아님을 증명하는 음성 대조군)
  ⓒ 같은 목적지·같은 지문의 **다른 backup_id**로 재사용 → 거부
  ⓓ 위조 토큰 → 거부
  ⓔ 거부된 모든 호출에서 **파일계 전수 sha1이 한 바이트도 안 바뀐다**

못 재는 것(정직):
  · TTL 만료의 실시간 경과는 재지 않는다 — `_CONFIRM_TTL`을 0으로 낮춰 대신 잰다(기존 문법 승계).
  · 토큰을 **사람이 실제로 봤는지**는 신뢰 경계 밖이다(main.py 토큰 절 주석).
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
APPID = "555"
#: 두 슬롯이 공유할 내용(C)과 두 대피본이 공유할 내용(R). 길이를 맞춘다 — G4가 크기 25~400%를 본다.
C = b"quality=comm\nshadows=same\nsource=BOTH-SLOTS-C\n"
R = b"quality=roll\nshadows=back\nsource=BOTH-BACKUPS\n"


def boot(tmp):
    """`main.py`를 샌드박스에서 띄운다. `decky`는 로더가 주는 모듈이라 여기서 흉내 낸다."""
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
    """합성 세계 **전 파일**의 (상대경로 → sha1). 거부가 정말 무쓰기인지를 **효과로** 잰다."""
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


def build_world(tmp, engine, store):
    """재현 세계를 **실제 저장 경로만 태워** 만든다(백업을 손으로 밀지 않는다).

    끝난 상태:
        dock 슬롯 = C · internal 슬롯 = C
        백업 = profile_dock(R) · profile_dock(C) · profile_dock(R) · profile_internal(R)
    `profile_dock` R 백업이 **두 건**인 것이 ⓒ(다른 backup_id 재사용)를 재는 재료다 —
    둘은 내용도 목적지도 같고 **이름만 다르다.**

    ⚠️⚠️ **그 두 번째 건만은 손으로 놓는다**(2026-08-22, 설계 §14-G ⓔ). 이제 앱은 같은 태그에
      같은 내용이 있으면 백업을 **안 만들므로** 정상 경로로는 그런 쌍이 생기지 않는다. 그런데
      ⓒ가 재는 계약은 여전히 살아 있다 — 규칙은 **앞으로 만들 백업에만** 걸리고 소급 정리를 하지
      않으므로, ⓔ 이전에 쌓인 링에는 그 쌍이 그대로 남아 있다(실물 링 81칸이 그 상태다).
      그래서 픽스처만 *그 시절의 링*을 재현한다. 놓는 방식은 정상 명명 규칙(`<stamp>-<tag>-
      <filename>`)을 그대로 따르는 파일 하나이고, 그 밖의 모든 상태는 실제 저장 경로가 만든다.
    """
    reg = store.load_registry()
    cfg = tmp / "game" / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(R)
    engine.add_game(reg, APPID, str(cfg), name="TokenBinding")
    engine.save_profile(reg, APPID, "dock")        # dock = R (첫 저장 — 대피 없음)
    cfg.write_bytes(C)
    engine.save_profile(reg, APPID, "dock")        # 대피 profile_dock(R) · dock = C
    cfg.write_bytes(R)
    engine.save_profile(reg, APPID, "dock")        # 대피 profile_dock(C) · dock = R
    cfg.write_bytes(C)
    engine.save_profile(reg, APPID, "dock")        # 대피 profile_dock(R) ★2건째 · dock = C
    cfg.write_bytes(R)
    engine.save_profile(reg, APPID, "internal")    # internal = R (첫 저장 — 대피 없음)
    cfg.write_bytes(C)
    engine.save_profile(reg, APPID, "internal")    # 대피 profile_internal(R) · internal = C
    store.save_registry(reg)
    # ★ 위 독스트링의 ⚠️⚠️ — `profile_dock(R)` 두 번째 건(=ⓔ 이전 링의 잔재)을 재현한다.
    #   stamp를 아주 예전으로 두어 목록 맨 끝에 놓는다(링은 4칸이라 prune에 안 걸린다).
    seed = [p for p in store.list_backups(APPID)
            if store.parse_backup_id(os.path.basename(p))["kind"] == "profile_dock"
            and store.sha1_file(p) == store.sha1_bytes(R)][0]
    store.atomic_write(
        os.path.join(store.backups_dir(APPID), "20200101-000000-profile_dock-video.ini"),
        store.read_bytes(seed))
    return cfg


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-restore-token-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, restore, store
        problems = []

        def P(msg):
            problems.append(msg)

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        cfg = build_world(tmp, engine, store)

        # ── 재현 세계가 실제로 「모든 칸이 같은」 상태인가 (여기가 무너지면 아래는 아무것도 못 잰다)
        names = [os.path.basename(p) for p in store.list_backups(APPID)]
        dock_r = [n for n in names
                  if store.parse_backup_id(n)["kind"] == "profile_dock"
                  and store.sha1_file(os.path.join(store.backups_dir(APPID), n))
                  == store.sha1_bytes(R)]
        intl_r = [n for n in names
                  if store.parse_backup_id(n)["kind"] == "profile_internal"
                  and store.sha1_file(os.path.join(store.backups_dir(APPID), n))
                  == store.sha1_bytes(R)]
        if len(dock_r) < 2 or len(intl_r) < 1:
            P("★사전 조건 실패 — 같은 내용의 profile_dock 백업 %d건 / profile_internal %d건 "
              "(2건·1건이 필요하다). 재현 세계가 안 섰다: %s" % (len(dock_r), len(intl_r), names))
            return finish(problems, tmp)
        reg = store.load_registry()
        fp_dock = restore.fingerprint(reg, APPID, dock_r[0])
        fp_intl = restore.fingerprint(reg, APPID, intl_r[0])
        if fp_dock != fp_intl:
            P("★사전 조건 실패 — 두 조합의 지문이 다르다(%s vs %s). 그러면 토큰이 지문 때문에 "
              "거부되는 것이라 **결박을 잰 것이 아니다**" % (fp_dock, fp_intl))
            return finish(problems, tmp)
        fp_dock2 = restore.fingerprint(reg, APPID, dock_r[1])
        if fp_dock2 != fp_dock:
            P("★사전 조건 실패 — 같은 목적지·같은 내용의 두 백업 지문이 다르다(%s vs %s)"
              % (fp_dock, fp_dock2))
            return finish(problems, tmp)

        before = world_sha(tmp)

        # ═══════════════════════════════════════════════════════════════════
        # ⓐ dock 확인 토큰 → **internal 백업** 호출 (반증 A4의 재현 그 자체)
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", APPID, dock_r[0])
        if not is_confirm(env):
            P("사전 조건 실패 — dock 백업에 CONFIRM_REQUIRED가 안 왔다 (%s)" % env)
            return finish(problems, tmp)
        if params_of(env).get("target") != "dock":
            P("사전 조건 실패 — dock 백업의 목적지가 %s다" % params_of(env).get("target"))
        tok_dock = params_of(env).get("confirm_token")

        env = rpc(main, "restore_backup", APPID, intl_r[0], confirm_token=tok_dock)
        if not is_confirm(env):
            P("★ⓐ dock 확인창에서 받은 토큰으로 **internal 슬롯 복원이 통과했다** — 사용자가 "
              "확인한 곳과 다른 곳에 쓰기가 일어난다 (%s)" % env)
        if store.sha1_file(store.profile_file_path(APPID, "internal")) != store.sha1_bytes(C):
            P("★ⓐ internal 슬롯이 실제로 덮어써졌다 — 남의 확인으로 일어난 쓰기다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓒ 같은 목적지·같은 지문의 **다른 backup_id**로 재사용
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", APPID, dock_r[0])
        tok_dock = params_of(env).get("confirm_token")
        env = rpc(main, "restore_backup", APPID, dock_r[1], confirm_token=tok_dock)
        if not is_confirm(env):
            P("★ⓒ 다른 백업 행의 토큰이 통과했다 — 확인한 백업과 다른 파일이 쓰인다 (%s)" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⓓ 위조 · 만료
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "restore_backup", APPID, dock_r[0], confirm_token="지어낸-토큰")
        if not is_confirm(env):
            P("★ⓓ 지어낸 토큰이 통과했다 (%s)" % env)
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", APPID, dock_r[0])
        tok = params_of(env).get("confirm_token")
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0
        try:
            env = rpc(main, "restore_backup", APPID, dock_r[0], confirm_token=tok)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env):
            P("★ⓓ 만료된 토큰이 통과했다 (%s)" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⓔ 여기까지 **거부만** 있었다 → 세계가 한 바이트도 안 바뀌었어야 한다
        # ═══════════════════════════════════════════════════════════════════
        after = world_sha(tmp)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if changed:
            P("★ⓔ 거부된 호출들이 파일을 바꿨다 — %s" % changed[:6])

        # ═══════════════════════════════════════════════════════════════════
        # ⓑ 음성 대조군 — **같은 조합**에서는 통과한다 (아무 토큰이나 거부하는 것이 아니다)
        #    통과가 확인되지 않으면 위의 모든 거부는 "언제나 거부"일 뿐이라 무의미하다.
        # ═══════════════════════════════════════════════════════════════════
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", APPID, dock_r[0])
        tok = params_of(env).get("confirm_token")
        env = rpc(main, "restore_backup", APPID, dock_r[0], confirm_token=tok)
        if not env.get("ok") or data_of(env).get("outcome") != "restored":
            P("★ⓑ 음성 대조군 실패 — 같은 조합의 정상 토큰도 거부됐다(방어가 과하다) (%s)" % env)
        elif store.sha1_file(store.profile_file_path(APPID, "dock")) != store.sha1_bytes(R):
            P("★ⓑ 복원됐다는데 dock 슬롯이 백업 내용이 아니다")
        if cfg.read_bytes() != C:
            P("★ⓑ 슬롯 복원이 게임 설정 파일을 바꿨다")

        print("복원 토큰 결박 — 목적지·백업 id (데이터: %s)" % tmp)
        print("  재현 세계: 두 슬롯 %s / 두 대피본 %s / 지문 %s (세 칸이 같다)"
              % (store.sha1_bytes(C)[:8], store.sha1_bytes(R)[:8], fp_dock[0][:8]))
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
