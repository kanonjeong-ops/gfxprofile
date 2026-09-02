#!/usr/bin/env python3
"""일괄 적용의 2단계 계약 — 1차 호출은 무쓰기 미리보기, 2차 호출이 실행.

`qa/test_apply_all.py`는 엔진을 직접 불러 "하나가 실패해도 나머지는 계속"을 잠근다
(route 계약과 무관하다). 이 파일은 그 위에 얹힌 route 계약을 잰다.

이 파일이 잠그는 것:
  ① 무토큰 1차 호출이 파일을 1바이트도 안 바꾼다 — 합성 세계 전 파일의 sha1을 전수 대조한다.
     (registry·프로필·게임 설정 파일·백업 전부. "미리보기"라는 이름이 아니라 효과로 잰다.)
  ② 토큰 계약 — 무토큰·위조·재사용·만료·scope 혼동(저장/삭제/복원 토큰으로 일괄 적용).
  ③ 방향 바인딩 — dock 미리보기에서 받은 토큰을 `apply_all("internal", token)`에 제출하면
     거부된다. 슬롯 4번 칸의 profile이 그 방어다.
  ④ 지문 무효화 — 확인창을 띄운 사이 프로필을 저장하면 낡은 토큰이 거부된다
     (`reset_fingerprint` 재사용: registry sha1만 보면 `save_profile`이 reg를 안 바꿔 안 걸린다).
  ⑤ 디스크 sha1은 지문에 없다(의도적 배제) — 게임이 설정 파일을 다시 써도 토큰은 유효하다.
     넣으면 확인→재확인 루프가 생겨 방지 장치가 사용 불능이 된다. 배제의 범위는 링이 포화가
     아닌 보통 상태다: 재기록이 지워질 백업을 바꾸면 토큰이 무효가 되는 것이 옳고, 그 갈래는
     `qa/test_evict_notice.py`가 잰다.
  ⑥ 2차 route가 엔진 직접 호출과 같은 행·파일계를 만드는가를 `dock` 세계에서 대조하고,
     별도 `internal` 실행에서 applied 2·no_profile 1과 `ok:true`를 잰다.
     ⑥′ route가 실행 중 집합을 미리보기에 배선하는가 — /proc 대신 합성 집합을 꽂아 잰다.
     ⑥″ 행 수·counts만 보면 순서 뒤집기·이름 변조·무관한 파일 쓰기가 전부 통과하므로,
       결과 행 전량(순서 포함)과 파일계 전체 바이트를 대조한다.
  ⑦ 미리보기 params가 5버킷 + profile + total + 토큰을 싣는다. 같은 params의 축출 고지
     (`evicted`·`evict_games`)는 이 파일이 재지 않는다 — `qa/test_evict_notice.py`의 몫이다.

거짓 검사 방지: 대조군을 세운 절은 ①·③·⑥′·⑥″ 넷이다. ①은 정상 2차 실행에서 sha가 실제로
  바뀐다는 것을 같은 계측기로 보이고, ③은 같은 토큰이 원래 방향에서는 통과하는지를 함께 재서
  "아무 토큰이나 거부"가 아님을 보인다. ②·④·⑤·⑦에는 대조군이 없다 — 그만큼 약한 검사다.
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
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
EDITED = b"quality=edit\nshadows=mid_\nsource=USER-EDITED-\n"


def boot(tmp):
    fake = types.ModuleType("decky")
    noop = lambda *a, **k: None                                  # noqa: E731
    fake.logger = types.SimpleNamespace(info=noop, warning=noop, error=noop, debug=noop, log=noop)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def mkgame(tmp, engine, store, appid, name, internal=True):
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


class _FrozenClock:
    """`store`가 쓰는 시계를 얼린다 — 백업 파일명(`%Y%m%d-%H%M%S`)과 `saved_at`이 실행 시각에
    좌우되면 두 번의 실행이 초 경계만 달라도 다른 바이트를 낸다. 재려는 것은 시간이 아니라
    "route 경유와 엔진 직접 호출이 같은 것을 쓰는가"이므로, 시간을 상수로 만들어 그 축을 없앤다.
    (테스트가 시간을 흉내 내는 것이 아니라 비교에서 시간을 제거하는 것이다.)"""

    def __init__(self, real):
        self._real = real

    def strftime(self, fmt, *args):
        if fmt == "%Y%m%d-%H%M%S":
            return "20260101-000000"
        if fmt == "%Y-%m-%dT%H:%M:%S%z":
            return "2026-01-01T00:00:00+0900"
        return self._real.strftime(fmt, *args)

    def __getattr__(self, name):
        return getattr(self._real, name)


def snapshot_world(tmp, keep):
    """합성 세계 전체를 `keep`으로 복사해 둔다(데이터 루트 + 게임 설정 파일 전부)."""
    if keep.exists():
        shutil.rmtree(keep)
    shutil.copytree(tmp, keep, symlinks=True)


def restore_world(tmp, keep):
    """스냅샷을 제자리로 되돌린다. 경로가 그대로여야 registry의 `config_path`가 유효하다 —
    다른 루트로 복사해 비교하면 registry가 원본을 가리켜 격리가 깨진다."""
    for child in tmp.iterdir():
        if child == keep:
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in keep.iterdir():
        target = tmp / child.name
        shutil.copytree(child, target, symlinks=True) if child.is_dir() else shutil.copy2(child, target)


def world_sha(tmp):
    """합성 세계 전 파일의 (상대경로 → sha1). 미리보기가 무쓰기인지를 효과로 잰다."""
    import hashlib
    out = {}
    for root, _dirs, files in os.walk(tmp):
        if os.sep + ".snapshot" in root + os.sep:
            continue                       # 비교용 사본은 세계의 일부가 아니다
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, tmp)] = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                out[os.path.relpath(path, tmp)] = "unreadable"
    return out


def main_test():                                                # noqa: C901
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-applyall-token-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []

        def P(msg):
            problems.append(msg)

        def finish():
            print("일괄 적용 토큰 계약 — 무쓰기 미리보기 · 토큰 6종 · 방향 바인딩 · 지문 "
                  "(데이터: %s)" % tmp)
            if problems:
                print("\nFAIL")
                for p in problems:
                    print("  " + p)
                return 1
            print("PASS")
            return 0

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        # 합성 세계: 적용 대상 2개 + internal 프로필이 없는 1개
        cfg1 = mkgame(tmp, engine, store, "100", "Alpha")
        cfg2 = mkgame(tmp, engine, store, "200", "Beta")
        mkgame(tmp, engine, store, "300", "NoInternal", internal=False)

        # ═══════════════════════════════════════════════════════════════════
        # ① 무토큰 1차 호출 = 파일을 1바이트도 안 바꾼다
        # ═══════════════════════════════════════════════════════════════════
        before = world_sha(tmp)
        env = rpc(main, "apply_all", "internal")
        if not is_confirm(env):
            P("★① 토큰 없이 일괄 적용이 실행됐다 — %s" % env)
            return finish()
        after = world_sha(tmp)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        if changed:
            P("★① 미리보기가 파일을 바꿨다 — %s" % sorted(changed)[:5])

        # ⑦ 5버킷·profile·total·토큰이 다 오는가
        p = params_of(env)
        for key in ("confirm_token", "profile", "would_apply", "already", "no_profile",
                    "running_refused", "cannot_apply", "total"):
            if key not in p:
                P("⑦ 미리보기 params에 %s가 없다 — 화면이 그릴 수 없다" % key)
        # `total`은 토큰 발급 시점의 등록 수 스냅샷이고, 확인창 본문은 `params.total`을 그린다.
        #   `get_overview`의 total은 다른 시점의 조회라 토큰이 지문 낸 대상과 어긋날 수 있다.
        if p.get("total") != 3:
            P("⑦ 미리보기 total이 등록 수(3)와 다르다 — %s" % p.get("total"))
        if p.get("profile") != "internal":
            P("⑦ params.profile이 요청 방향과 다르다 — %s" % p.get("profile"))
        if (p.get("would_apply"), p.get("no_profile")) != (2, 1):
            P("⑦ 미리보기 개수가 실물과 다르다 — would_apply=%s no_profile=%s (기대 2·1)"
              % (p.get("would_apply"), p.get("no_profile")))
        token = p.get("confirm_token")

        # ═══════════════════════════════════════════════════════════════════
        # ⑥″ 2차 실행 = 엔진 직접 호출과 바이트 동일
        #
        #   아무 실행도 지나지 않은 세계에서 잰다. 앞에서 한 번이라도 실행하면 그때 route가
        #     남긴 것이 기준 스냅샷에 들어가 두 경로 모두에 존재하게 되고, '무관한 파일을 더
        #     쓰는' 변이를 검사가 눈감는다.
        #
        #   행 수와 counts만 보면 route가 행 순서를 바꾸거나 name·note·code를 갈아 끼우거나
        #   무관한 파일을 더 써도 통과한다 — 그런데 이 불변식은 "route 층에서 미리 걸러내지
        #   않는다"는 재제안 금지의 근거로 쓰이는 계약이다. 근거가 약하면 그 금지도 약해진다.
        #   그래서 같은 초기 세계에서 두 경로를 각각 돌려 결과 행 전량(순서 포함)과 파일계
        #   전체를 대조한다.
        #
        #   두 실행이 시간에 좌우되지 않도록 시계를 얼린다(백업 파일명·saved_at).
        # ═══════════════════════════════════════════════════════════════════
        keep = tmp / ".snapshot"
        real_clock, store.time = store.time, _FrozenClock(store.time)
        try:
            snapshot_world(tmp, keep)

            # (A) route 경유 2차 실행
            env_a = rpc(main, "apply_all", "dock")
            tok_a = params_of(env_a).get("confirm_token")
            env_a = rpc(main, "apply_all", "dock", confirm_token=tok_a)
            rows_a = data_of(env_a).get("results")
            world_a = world_sha(tmp)

            restore_world(tmp, keep)

            # (B) 엔진 직접 호출 — route가 하는 나머지(저장)는 그대로 흉내 낸다
            reg_b = store.load_registry()
            rows_b = engine.apply_all(reg_b, "dock")
            store.save_registry(reg_b)
            world_b = world_sha(tmp)

            if not env_a.get("ok"):
                P("⑥″ 사전 조건 실패 — route 2차 실행이 성공하지 않았다 (%s)" % env_a)
            if rows_a != rows_b:
                P("★⑥″ route의 결과 행이 엔진 직접 호출과 다르다 — 순서·이름·사유가 갈렸다\n"
                  "      route=%s\n      engine=%s" % (rows_a, rows_b))
            diff = sorted(k for k in set(world_a) | set(world_b) if world_a.get(k) != world_b.get(k))
            if diff:
                P("★⑥″ 두 경로가 만든 **파일계가 다르다** — %s" % diff[:6])
            # 계측기 반증: 이 비교가 실제로 무언가를 재는가(두 실행이 세계를 바꾸긴 했는가)
            base = world_sha(keep)
            if not [k for k in set(base) | set(world_b) if base.get(k) != world_b.get(k)]:
                P("⑥″ 계측기 무효 — 적용이 세계를 하나도 안 바꿨다(대조가 항진식이다)")
            if not rows_b:
                P("⑥″ 계측기 무효 — 엔진 기준 결과 행이 비었다")
        finally:
            store.time = real_clock
            # 뒤 절들이 보던 세계를 그대로 돌려준다. 이 절이 세계를 바꿔 놓으면 다음 단언들이
            #   자기가 만들지 않은 상태 위에서 돌아 거짓 FAIL을 낸다 — 이 복원을 지우면 그
            #   상태가 그대로 돌아온다.
            if keep.exists():
                restore_world(tmp, keep)
                shutil.rmtree(keep, ignore_errors=True)


        # 계측기 반증: 정상 2차 실행에서는 세계가 실제로 바뀐다.
        # (안 바뀌면 위 ①은 "항상 안 바뀜"을 본 것이므로 무의미하다.)
        env = rpc(main, "apply_all", "internal", confirm_token=token)
        if not env.get("ok"):
            P("⑥ 정상 토큰인데 실행이 안 됐다 — %s" % env)
        after2 = world_sha(tmp)
        if not {k for k in set(after) | set(after2) if after.get(k) != after2.get(k)}:
            P("★① 계측기 무효 — 실제 실행에서도 세계가 안 바뀌었다(무쓰기 단언이 항진식이다)")
        if cfg1.read_bytes() != INTERNAL or cfg2.read_bytes() != INTERNAL:
            P("⑥ 2차 실행이 설정 파일을 바꾸지 않았다")
        counts = data_of(env).get("counts") or {}
        rows = data_of(env).get("results") or []
        if len(rows) != 3 or counts.get("applied") != 2 or counts.get("no_profile") != 1:
            P("⑥ 2차 실행 결과가 현행 apply_all과 다르다 — counts=%s rows=%d" % (counts, len(rows)))
        # 체크인은 엔진에 없다 — 그 관측 필드도 봉투에 없어야 한다. 여기서 부재를 단언하는
        #   이유는, 없는 사건의 계측기가 되살아나면 화면이 언젠가 그 오탐을 그리기 때문이다.
        if "checkin" in data_of(env):
            P("★⑥ 봉투에 checkin이 아직 있다 — 체크인은 13판에서 제거됐다 (%s)"
              % data_of(env).get("checkin"))
        for row in rows:
            if set(row) != {"appid", "name", "outcome", "code", "note"}:
                P("★⑥ 결과 행이 엔진 반환 모양과 다르다 — 관측이 행을 변형했다 (%s)" % sorted(row))

        # ═══════════════════════════════════════════════════════════════════
        # ② 토큰 우회 전종
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "apply_all", "dock", confirm_token=token)      # 재사용(이미 소각)
        if not is_confirm(env):
            P("②-a 소각된 토큰이 다시 통과했다 ★1회용이 아니다 — %s" % env)
        env = rpc(main, "apply_all", "dock", confirm_token="지어낸-토큰")
        if not is_confirm(env):
            P("②-b 지어낸 토큰이 통과했다 ★계약 위반 — %s" % env)
        if cfg1.read_bytes() != INTERNAL:
            P("②-b 거부인데 설정 파일이 바뀌었다")

        # ②-c 만료
        tok = params_of(rpc(main, "apply_all", "dock")).get("confirm_token")
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0
        try:
            env = rpc(main, "apply_all", "dock", confirm_token=tok)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env):
            P("②-c 만료된 토큰이 통과했다 ★계약 위반 — %s" % env)

        # ②-d scope 혼동 — 저장·삭제·복원 토큰으로 일괄 적용
        cfg1.write_bytes(EDITED)                       # 덮어쓰기 상황을 만든다(저장 토큰 발급용)
        save_tok = params_of(rpc(main, "save_profile", "100", "dock")).get("confirm_token")
        del_tok = params_of(rpc(main, "delete_game", "100")).get("confirm_token")
        # 복원 토큰을 얻으려면 되돌릴 곳과 내용이 다른 백업 행이 하나 필요하다.
        #   적용은 디스크가 어느 슬롯과 같으면 대피본을 안 만들므로 이 세계에는 백업이 0건일
        #   수 있다 — 여기서 하나를 직접 만든다. 이 절이 재는 것은 scope 격리뿐이고, 백업이
        #   어떻게 생겼는지는 그 측정과 무관하다.
        store.make_backup("100", b"quality=bkup\nshadows=old_\nsource=FOREIGN-TOKEN\n",
                          "disk", "video.ini")
        bk = store.list_backups("100")
        restore_tok = None
        if bk:
            restore_env = rpc(main, "restore_backup", "100", os.path.basename(bk[0]))
            restore_tok = params_of(restore_env).get("confirm_token")
        for label, foreign in (("저장", save_tok), ("삭제", del_tok), ("복원", restore_tok)):
            if not foreign:
                P("②-d %s 토큰을 못 얻었다 — scope 혼동을 시험할 수 없다" % label)
                continue
            env = rpc(main, "apply_all", "dock", confirm_token=foreign)
            if not is_confirm(env):
                P("★②-d %s 토큰으로 일괄 적용이 통과했다 — scope가 안 갈린다 (%s)" % (label, env))
        cfg1.write_bytes(INTERNAL)

        # ═══════════════════════════════════════════════════════════════════
        # ③ 방향 바인딩 — dock 토큰은 internal에 소비되지 않는다
        # ═══════════════════════════════════════════════════════════════════
        dock_tok = params_of(rpc(main, "apply_all", "dock")).get("confirm_token")
        env = rpc(main, "apply_all", "internal", confirm_token=dock_tok)
        if not is_confirm(env):
            P("★③ dock 미리보기 토큰이 internal 일괄 적용에 소비됐다 — 사용자가 확인한 것과 "
              "**다른 방향**의 쓰기가 확인 없이 실행된다 (%s)" % env)
        if cfg1.read_bytes() != INTERNAL:
            P("★③ 방향이 뒤바뀐 토큰으로 파일이 실제로 바뀌었다")
        # 반증: 같은 토큰이 원래 방향에서는 통과해야 한다(아무 토큰이나 거부하는 것이 아니다)
        dock_tok2 = params_of(rpc(main, "apply_all", "dock")).get("confirm_token")
        env = rpc(main, "apply_all", "dock", confirm_token=dock_tok2)
        if not env.get("ok"):
            P("★③ 음성 대조군 실패 — 같은 방향의 정상 토큰도 거부됐다(방어가 과하다) — %s" % env)
        if cfg1.read_bytes() != DOCK:
            P("③ 음성 대조군: dock 적용이 실제로 일어나지 않았다")

        # ═══════════════════════════════════════════════════════════════════
        # ④ 지문 무효화 — 확인창 사이 프로필 저장 → 낡은 토큰 거부
        #    (registry sha1만 보면 `save_profile`이 reg를 안 바꿔 통과한다)
        # ═══════════════════════════════════════════════════════════════════
        tok = params_of(rpc(main, "apply_all", "internal")).get("confirm_token")
        cfg2.write_bytes(EDITED)
        env = rpc(main, "save_profile", "200", "internal")
        if is_confirm(env):
            env = rpc(main, "save_profile", "200", "internal",
                      confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok"):
            P("④ 사전 조건 실패 — 확인창 사이 저장이 안 됐다 (%s)" % env)
        env = rpc(main, "apply_all", "internal", confirm_token=tok)
        if not is_confirm(env):
            P("★④ 확인창 사이 프로필이 저장됐는데 낡은 토큰이 통과했다 — 사용자가 본 미리보기가 "
              "이미 낡았다 (%s)" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⑥′ route가 실행 중 집합을 미리보기에 실제로 배선하는가
        #    `apply_all` route는 `_running_appids()`를 미리보기에 넘긴다. 그 배선을 지우면
        #    화면이 "실행 중 N개 거부 예상"을 영영 0으로 말하는데, 엔진은 그대로 거부한다 —
        #    미리보기와 결과가 갈린다. 여기서 /proc 대신 합성 집합을 꽂아 그 배선을 잰다.
        # ═══════════════════════════════════════════════════════════════════
        cfg1.write_bytes(EDITED)                      # 디스크≠dock 프로필 → 거부 대상이 된다
        real_running = main._running_appids
        main._running_appids = lambda: {"100"}
        try:
            env = rpc(main, "apply_all", "dock")
        finally:
            main._running_appids = real_running
        p = params_of(env)
        if p.get("running_refused") != 1:
            P("★⑥′ 실행 중 게임이 미리보기에 반영되지 않았다(running_refused=%s, 기대 1) — "
              "route가 실행 중 집합을 넘기지 않으면 화면이 영영 0을 말한다" % p.get("running_refused"))
        # 음성 대조군: 실행 중이 아니면 같은 세계에서 0이어야 한다(항진식이 아님을 보인다)
        env = rpc(main, "apply_all", "dock")
        if params_of(env).get("running_refused") != 0:
            P("⑥′ 음성 대조군 실패 — 아무도 실행 중이 아닌데 running_refused가 %s다"
              % params_of(env).get("running_refused"))
        cfg1.write_bytes(DOCK)

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ 디스크 sha1은 지문에 없다(의도적) — 게임이 설정을 다시 써도 토큰은 유효
        #
        #   이 배제의 범위는 좁다: 토큰은 축출 대상의 지문에도 묶인다. 그래서 설정 파일
        #     재기록이 지워질 백업을 바꾸는 때(=그 게임의 링이 이미 가득 찬 때)는 토큰이
        #     무효가 되는 것이 옳다 — 그때는 확인창이 말한 "축출 N건"이 이미 거짓이기
        #     때문이다. 그 포화 갈래는 `qa/test_evict_notice.py`가 잰다. 여기서 재는 것은
        #     링이 포화가 아닌 보통 상태에서 재기록이 확인→재확인 루프를 만들지 않는다는 것이다.
        # ═══════════════════════════════════════════════════════════════════
        tok = params_of(rpc(main, "apply_all", "dock")).get("confirm_token")
        cfg2.write_bytes(EDITED + b"game-rewrote=1\n")     # 게임이 종료하며 다시 쓴 상황
        env = rpc(main, "apply_all", "dock", confirm_token=tok)
        if not env.get("ok"):
            P("★⑤ 디스크가 바뀌었다고 토큰이 무효가 됐다 — 확인→재확인 루프가 생긴다 "
              "(설계 §3-C가 디스크 sha1을 지문에서 **일부러 뺀** 이유) (%s)" % env)

        return finish()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
