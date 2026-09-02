#!/usr/bin/env python3
"""복원 route의 계약 — 3-상태 · 토큰 · 조기 거부 · 파일명 파싱/정렬 · 링 소모.

`qa/test_restore_path.py`는 엔진의 2단계 복원 절차를 잰다. 이 파일은 그 위의 route 계약을 잰다.

이 파일이 잠그는 것:
  ⓞ 목록 행은 봉투의 `target`과 `same_as_target`으로 되돌릴 곳과 현재 동일성을 싣는다.
  ① 무토큰·위조·재사용·만료·타 게임·scope 혼동·되돌릴 곳 내용 변경 뒤 토큰을 거부한다.
  ② `already`는 엔진을 부르지 않고 백업 ID 집합·설정 파일을 바꾸지 않으며 토큰을 내지 않는다.
     설정 파일이 없으면 `proceed`로 묻지 않고 복원한다.
  ③ 설정 파일 복원은 게임 실행 중 토큰 발급 전에 `GAME_RUNNING`으로 거부된다.
  ④ 식별자·등록·백업 경로를 검사하고, 링크 밖 파일을 설정 파일로 복사하지 않는다.
  ⑤ 파일명의 stamp·충돌 번호·하이픈 든 이름·미지 형식을 파싱하고
     `(stamp, seq, name)` 키의 내림차순을 잰다.
  ⑥ 새 내용의 설정 파일 대피는 비포화 링에 1건을 더하고, 포화 링에서는 1건을 더해 1건을
     지운다. 같은 태그·같은 내용이면 성공해도 백업 ID 집합은 그대로다. `get_overview.backups`도
     목록 행 수와 대조한다.
  ⑦ 이웃 슬롯 meta가 비-dict여도 설정 파일 복원의 확인과 실행이 성공한다.
  ⑧ 지문이 같은 두 게임 사이에서도 토큰의 appid가 다른 게임 사용을 막는다.
  ⑨ `profile_*` 행은 봉투의 `target` 슬롯으로 복원한다. 설정 파일은 그대로이고, 슬롯 대피는
     같은 태그·같은 내용의 존재에 따라 백업 ID가 1건 늘거나 그대로다. 게임 실행 중에도 막지 않는다.

파싱·정렬과 경로 봉쇄에는 순진한 구현이 실패하는 음성 대조군을 둔다.
합성 데이터만 쓰고 데이터 루트와 홈 경계는 tmp를 가리킨다.
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
#: 어느 슬롯과도 다른 제3의 상태. 적용이 대피본을 만드는 조건이 이것이다
#: (디스크가 어느 슬롯과 같으면 그 내용은 이미 슬롯에 있으므로 링을 태우지 않는다).
THIRD = b"quality=thrd\nshadows=mid_\nsource=THIRD-STATE-\n"
#: 아직 어느 태그의 링에도 담긴 적이 없는 내용. 대피는 그 태그에 같은 내용이 없을 때만
#: 링을 태우므로, "대피본이 1건 생긴다"를 재는 절은 이 내용을 써야 잴 것이 생긴다.
#: (중복이라 안 생기는 갈래는 같은 절의 뒤쪽에서 따로 잰다 — 단언을 넓히지 않고 갈래를 가른다.)
UNSEEN = b"quality=unsn\nshadows=off_\nsource=NEVER-IN-RING\n"

LOG = []


def boot(tmp):
    """`main.py`를 샌드박스에서 띄운다. `decky`는 로더가 주는 모듈이라 여기서 흉내 낸다."""
    def rec(kind):
        def fn(fmt="", *args, **kwargs):
            try:
                LOG.append((kind, (str(fmt) % args) if args else str(fmt)))
            except Exception:                                   # noqa: BLE001
                LOG.append((kind, "%s %r" % (fmt, args)))
        return fn

    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(
        info=rec("info"), warning=rec("warning"), error=rec("error"), debug=rec("debug"),
        log=lambda level, fmt="", *args, **kwargs: rec("log")(fmt, *args),
    )
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # ← 격리는 이 한 줄이 한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def mkgame(tmp, engine, store, appid, name):
    """합성 게임 하나 — 실제 저장·적용 경로를 태워 백업 링을 채운다(손으로 밀지 않는다).

    끝난 상태: 슬롯 dock=DOCK · internal=INTERNAL / 디스크 = DOCK / 백업 5건 —
    `profile_internal`(INTERNAL) · `profile_internal`(THIRD) ·
    `profile_dock`(DOCK) · `profile_dock`(THIRD) · `disk`(THIRD).
    대피본은 덮어쓰기가 만든다(빈 슬롯 첫 저장은 대피할 것이 없다) — 실사용의 그 경로를 탄다.

    마지막 적용 직전에 어느 슬롯과도 다른 THIRD를 쓴다. 디스크가 어느 슬롯과 같으면 적용이
      대피본을 만들지 않아, 그대로 두면 이 픽스처에 `disk` 행이 아예 없어 아래 단언들이 잴
      대상을 잃는다.
    내용이 같은 재저장은 한 바이트도 쓰지 않는다(`engine.save_profile`의 무쓰기 분기). 그래서
      "같은 내용으로 다시 저장"으로는 대피본이 아예 안 생긴다 — 대피는 내용이 달라지는
      덮어쓰기에서만 일어난다.
    그런데 아래 ⓞ·②는 슬롯과 내용이 같은 프로필 대피본을 필요로 한다. 대피본은 덮이기 전
      슬롯 내용이고 새 슬롯 내용은 그때의 디스크 내용이라, 한 번의 저장으로는 둘이 같아질 수
      없다(같으면 애초에 안 쓴다). 실사용에서 그 상태가 생기는 길은 하나뿐이다 — 갔다가
      돌아오는 것(A → B → A): 첫 덮어쓰기가 A를 대피시키고, 두 번째가 슬롯을 다시 A로
      되돌린다. 그래서 슬롯마다 대피본이 2건씩 쌓인다.
    그 결과 같은 kind의 행이 둘이 되므로, 아래 단언들은 「그 kind의 첫 행」이 아니라
      `same_as_target`이라는 성질로 행을 고른다(`pick_same`) — 픽스처 순서에 기대면 이 파일이
      재는 것이 무엇인지 다음 사람이 알 수 없다.
    """
    reg = store.load_registry()
    cfg = tmp / ("game%s" % appid) / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(DOCK)
    engine.add_game(reg, appid, str(cfg), name=name)
    engine.save_profile(reg, appid, "dock")           # 첫 저장 — 대피 없음
    cfg.write_bytes(INTERNAL)
    engine.save_profile(reg, appid, "internal")       # 첫 저장 — 대피 없음
    cfg.write_bytes(THIRD)
    engine.save_profile(reg, appid, "internal")       # 덮어쓰기 → profile_internal(INTERNAL)
    cfg.write_bytes(INTERNAL)
    engine.save_profile(reg, appid, "internal")       # 되돌아옴 → 슬롯 == 위 대피본
    cfg.write_bytes(THIRD)
    engine.save_profile(reg, appid, "dock")           # 덮어쓰기 → profile_dock(DOCK)
    cfg.write_bytes(DOCK)
    engine.save_profile(reg, appid, "dock")           # 되돌아옴 → 슬롯 == 위 대피본
    cfg.write_bytes(THIRD)                            # 어느 슬롯과도 다르다(적용의 대피 조건)
    engine.apply_profile(reg, appid, "dock")          # → disk 대피본(THIRD), 디스크는 DOCK이 된다
    store.save_registry(reg)
    return cfg


def naive_parse(name):
    """순진한 구현 — 첫 `-`로 자른다. 음성 대조군이다(이것이 틀리는 것을 테스트가 보인다)."""
    parts = name.split("-")
    return {"stamp": parts[0], "tag": parts[1] if len(parts) > 1 else ""}


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-restore-route-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, restore, store
        problems = []
        real_engine_restore = engine.restore_backup
        engine_calls = []

        def counted_restore(reg, appid, path, *args, **kwargs):
            """엔진 호출을 직접 센다 — "already면 엔진을 안 부른다"는 결과가 아니라
            호출 자체로 잰다(파일이 우연히 안 바뀌는 것과 구분된다).

            가변 인자로 받는다: 엔진이 `target`을 인자로 받으므로 고정 3인자 래퍼는 그 순간
              TypeError를 낸다 — 계측기가 대상을 깨는 자리다."""
            engine_calls.append((str(appid), path) + tuple(args))
            return real_engine_restore(reg, appid, path, *args, **kwargs)

        engine.restore_backup = counted_restore

        def P(msg):
            problems.append(msg)

        def finish():
            print("복원 route 계약 — 토큰 7종 · 3-상태 · 조기 거부 · 파싱 5종 · 정렬 · 링 소모 "
                  "(데이터: %s)" % tmp)
            print("  엔진 restore_backup 실호출 %d회 · decky 로그 %d줄" % (len(engine_calls), len(LOG)))
            if problems:
                print("\nFAIL")
                for p in problems:
                    print("  " + p)
                return 1
            print("PASS")
            return 0

        # ── 판정기 ───────────────────────────────────────────────────────────
        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def code_of(env):
            return env.get("code")

        def params_of(env):
            return env.get("params") or {}

        def data_of(env):
            return env.get("data") or {}

        def backup_ids(appid):
            return {os.path.basename(p) for p in store.list_backups(appid)}

        def rows(appid):
            env = rpc(main, "list_backups", str(appid))
            if not env.get("ok"):
                P("list_backups가 실패했다(appid=%s) — %s" % (appid, env))
                return []
            return data_of(env).get("backups") or []

        def token_for(appid, backup_id):
            env = rpc(main, "restore_backup", str(appid), backup_id)
            if not is_confirm(env):
                P("토큰 발급 실패 — %s/%s에 CONFIRM_REQUIRED가 안 왔다 (%s)"
                  % (appid, backup_id, env))
                return None
            return params_of(env).get("confirm_token")

        def pick(appid, kind):
            for row in rows(appid):
                if row["kind"] == kind:
                    return row
            P("사전 조건 실패 — appid %s에 kind=%s 백업이 없다 (%s)"
              % (appid, kind, [r["kind"] for r in rows(appid)]))
            return None

        def pick_same(appid, kind):
            """그 kind 중 되돌릴 곳과 내용이 같은 행. 픽스처 순서가 아니라 성질로 고른다.

            무쓰기 이후 이 상태는 갔다가 돌아온 슬롯에서만 생기고(mkgame 주석), 그때 같은
              kind의 행이 둘이라 「첫 행」으로는 엉뚱한 것을 집는다.
            """
            for row in rows(appid):
                if row["kind"] == kind and row["same_as_target"]:
                    return row
            P("사전 조건 실패 — appid %s에 슬롯과 내용이 같은 kind=%s 행이 없다 (%s)"
              % (appid, kind, [(r["kind"], r["same_as_target"]) for r in rows(appid)]))
            return None

        # ═══════════════════════════════════════════════════════════════════
        # 사전: 목록 route가 실제 흐름으로 쌓인 백업을 보는가 (측정 경로 도달 확인)
        # ═══════════════════════════════════════════════════════════════════
        cfg100 = mkgame(tmp, engine, store, "100", "RestoreTarget")
        rows100 = rows("100")
        if len(rows100) < 2:
            P("★사전 조건 실패 — 저장·적용을 태웠는데 백업이 %d건뿐이다. 아래 단언을 잴 수 없다"
              % len(rows100))
            return finish()
        if {r["kind"] for r in rows100} - {"disk", "profile_dock", "profile_internal", "unknown"}:
            P("목록에 알 수 없는 kind가 있다 — %s" % [r["kind"] for r in rows100])
        for key in ("backup_id", "kind", "stamp", "stamp_label", "filename", "size"):
            if key not in rows100[0]:
                P("행에 %s가 없다 — 화면이 그릴 값이 백엔드에서 안 온다" % key)
        if any(r["size"] <= 0 for r in rows100):
            P("백업 크기가 0으로 왔다 — 표시가 거짓말을 한다 (%s)" % [r["size"] for r in rows100])

        # get_overview의 backups 필드가 목록 길이와 같은가 (두 곳에서 세면 언젠가 어긋난다)
        env = rpc(main, "get_overview", True)
        ov = {g["appid"]: g for g in data_of(env).get("games", [])}
        if "backups" not in (ov.get("100") or {}):
            P("★get_overview에 backups 필드가 없다 — [백업 N] 라벨을 그릴 수 없다")
        elif ov["100"]["backups"] != len(rows100):
            P("get_overview.backups(%s) ≠ list_backups 행 수(%d) — 두 곳의 셈이 어긋난다"
              % (ov["100"]["backups"], len(rows100)))
        env_f = rpc(main, "get_overview")          # 관리 탭은 detail=false로 부른다
        ov_f = {g["appid"]: g for g in data_of(env_f).get("games", [])}
        if (ov_f.get("100") or {}).get("backups") != len(rows100):
            P("★detail=false에서 backups가 안 온다 — 관리 탭(detail=false 호출)이 N을 못 그린다")

        # ═══════════════════════════════════════════════════════════════════
        # ⓞ 되돌릴 곳이 행마다 실려 오는가 — 화면이 누르기 전에 말한다
        # ═══════════════════════════════════════════════════════════════════
        want_target = {"disk": "config", "profile_dock": "dock", "profile_internal": "internal"}
        for row in rows100:
            if "target" not in row or "same_as_target" not in row:
                P("★ⓞ 행에 target/same_as_target이 없다 — 「되돌릴 곳」을 화면이 그릴 수 없다 (%s)"
                  % sorted(row))
                break
            if row["target"] != want_target.get(row["kind"], "config"):
                P("★ⓞ kind=%s의 되돌릴 곳이 %s다(기대 %s) — 확인한 곳과 다른 곳에 쓰게 된다"
                  % (row["kind"], row["target"], want_target.get(row["kind"])))
        # `profile_internal` 대피본 하나는 지금 internal 슬롯과 같은 내용이다(mkgame가 그렇게
        # 만든다 — 갔다가 돌아온 슬롯). 그 사실이 배지로 나와야 하고, 같은 시각 `disk` 행은
        # 다르다(둘 다 맞아야 계측이 유효하다).
        # kind로 뭉뚱그리지 않는다 — 같은 kind에 True·False가 함께 있는 것이 정상 상태다.
        same_kinds = {r["kind"] for r in rows100 if r["same_as_target"]}
        if "profile_internal" not in same_kinds:
            P("★ⓞ 슬롯과 내용이 같은 프로필 백업에 same_as_target이 안 섰다 — %s"
              % [(r["kind"], r["same_as_target"]) for r in rows100])
        if "disk" in same_kinds:
            P("ⓞ 계측기 무효 — 내용이 다른 disk 행까지 same_as_target이 참이다 (%s)"
              % [(r["kind"], r["same_as_target"]) for r in rows100])

        # ═══════════════════════════════════════════════════════════════════
        # ② 3-상태 ①  `already` — 엔진 미호출 · 쓰기 0 · 링 소모 0
        #    기준은 되돌릴 곳이다. 지금 internal 슬롯과 `profile_internal` 대피본의 내용이
        #      같으므로 already다. 게임 설정 파일만 보는 판정이었다면 이 행은 confirm이다 —
        #      디스크는 DOCK이라 백업과 다르기 때문이다. 즉 이 단언은 기준이 목적지로
        #      옮겨졌는지를 직접 가른다.
        # ═══════════════════════════════════════════════════════════════════
        same_row = pick_same("100", "profile_internal")
        if same_row is None:
            return finish()
        before_ids = backup_ids("100")
        before_bytes = cfg100.read_bytes()
        engine_calls.clear()
        env = rpc(main, "restore_backup", "100", same_row["backup_id"])
        if not env.get("ok") or data_of(env).get("outcome") != "already":
            P("②-a 되돌릴 곳이 백업과 같은데 already가 아니다 — %s" % env)
        if engine_calls:
            P("★②-a already인데 엔진 restore_backup이 호출됐다 — 조기 반환이 안 된다 (%s)"
              % engine_calls)
        # 같은 행을 한 번 더 누른다 — 링이 1칸도 밀리면 안 된다.
        env = rpc(main, "restore_backup", "100", same_row["backup_id"])
        if data_of(env).get("outcome") != "already":
            P("②-a 두 번째 탭에서 already가 아니다 — %s" % env)
        if backup_ids("100") != before_ids:
            P("★②-a already 2탭에 백업 링이 움직였다 — 되돌릴 지점이 밀려 사라진다 "
              "(전 %d건 → 후 %d건)" % (len(before_ids), len(backup_ids("100"))))
        if cfg100.read_bytes() != before_bytes:
            P("★②-a already인데 설정 파일이 바뀌었다")
        if main._CONFIRM_TOKENS:
            P("②-a already 경로에서 토큰이 발급됐다 — 묻지 않는 경로다 (%d개)"
              % len(main._CONFIRM_TOKENS))

        # ═══════════════════════════════════════════════════════════════════
        # ① 토큰 계약 + ⑥ 링 소모 (디스크를 손으로 바꿔 「덮어쓰기」 상황을 만든다)
        #    대상은 `disk` 행 = 게임 설정 파일이다.
        # ═══════════════════════════════════════════════════════════════════
        cfg100.write_bytes(EDITED)
        prof_row = pick("100", "disk")
        if prof_row is None:
            return finish()

        env = rpc(main, "restore_backup", "100", prof_row["backup_id"])      # ①-a 무토큰
        if not is_confirm(env):
            P("①-a 토큰 없이 복원이 통과했다 ★계약 위반 (%s)" % env)
        if cfg100.read_bytes() != EDITED:
            P("★①-a 거부인데 설정 파일이 이미 바뀌었다")
        tok = params_of(env).get("confirm_token")
        for key in ("kind", "stamp_label", "size", "disk_state", "backup_id"):
            if key not in params_of(env):
                P("①-a 확인창이 쓸 %s가 params에 없다" % key)
        if params_of(env).get("disk_state") != "unknown":
            P("①-a 손으로 고친 디스크의 4분류가 unknown이 아니다 — %s"
              % params_of(env).get("disk_state"))

        env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token="지어낸-토큰")
        if not is_confirm(env) or cfg100.read_bytes() != EDITED:
            P("①-b 지어낸 토큰으로 복원이 통과했다 ★계약 위반 (%s)" % env)

        # ①-c scope 혼동 — 삭제 토큰으로 복원
        del_env = rpc(main, "delete_game", "100")
        del_tok = params_of(del_env).get("confirm_token")
        if not del_tok:
            P("①-c 삭제 토큰을 못 얻었다 — scope 혼동을 시험할 수 없다")
        else:
            env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=del_tok)
            if not is_confirm(env) or cfg100.read_bytes() != EDITED:
                P("★①-c 삭제 토큰으로 복원이 통과했다 — scope 네임스페이스가 안 갈린다 (%s)" % env)

        # ①-c′ 반대 방향 — 복원 토큰으로 저장
        tok = token_for("100", prof_row["backup_id"])
        env = rpc(main, "save_profile", "100", "dock", confirm_token=tok)
        if not is_confirm(env):
            P("★①-c′ 복원 토큰으로 저장이 통과했다 — scope 네임스페이스가 안 갈린다 (%s)" % env)

        # ①-d TOCTOU — 토큰을 받은 뒤 디스크가 바뀌면 낡은 토큰은 거부된다
        tok = token_for("100", prof_row["backup_id"])
        cfg100.write_bytes(EDITED + b"more=1\n")
        env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=tok)
        if not is_confirm(env):
            P("★①-d 확인창 사이 디스크가 바뀌었는데 낡은 토큰이 통과했다 (%s)" % env)
        cfg100.write_bytes(EDITED)

        # ①-e 만료
        tok = token_for("100", prof_row["backup_id"])
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0
        try:
            env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=tok)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env) or cfg100.read_bytes() != EDITED:
            P("①-e 만료된 토큰이 통과했다 ★계약 위반 (%s)" % env)

        # ①-f 타 게임의 토큰
        mkgame(tmp, engine, store, "200", "Neighbour")
        other = pick("200", "disk")               # 내용이 달라야 confirm 갈래를 탄다
        tok200 = token_for("200", other["backup_id"]) if other else None
        if tok200:
            env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=tok200)
            if not is_confirm(env) or cfg100.read_bytes() != EDITED:
                P("①-f 다른 게임의 토큰으로 복원이 통과했다 ★계약 위반 (%s)" % env)

        # ── ⑥ 정상 복원 1회 = 링 정확히 1칸 (already의 +0과 같은 계측기로 잰다) ──
        tok = token_for("100", prof_row["backup_id"])
        before_ids = backup_ids("100")
        engine_calls.clear()
        env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=tok)
        if not env.get("ok") or data_of(env).get("outcome") != "restored":
            P("⑥ 정상 토큰인데 복원이 안 됐다 — %s" % env)
        if len(engine_calls) != 1:
            P("⑥ 엔진 restore_backup 호출이 %d회다(1회여야 한다)" % len(engine_calls))
        if cfg100.read_bytes() != THIRD:
            P("★⑥ 복원됐다는데 설정 파일이 백업 내용이 아니다 — %r" % cfg100.read_bytes()[:40])
        after_ids = backup_ids("100")
        added, removed = after_ids - before_ids, before_ids - after_ids
        if len(added) != 1 or removed:
            P("★⑥ 복원 1회가 링에 %d건 추가·%d건 축출했다(1·0이어야 한다) — 대피 계약이 어긋난다"
              % (len(added), len(removed)))
        if store.sha1_bytes(EDITED) not in {store.sha1_file(p) for p in store.list_backups("100")}:
            P("★⑥ 복원 직전 디스크 내용이 백업에 없다 — 되돌릴 지점이 없다")

        # ①-g 재사용 — 방금 쓴 토큰은 다시 통과하지 못한다
        env = rpc(main, "restore_backup", "100", prof_row["backup_id"], confirm_token=tok)
        if not (is_confirm(env) or data_of(env).get("outcome") == "already"):
            P("①-g 소각된 토큰이 다시 통과했다 ★1회용이 아니다 (%s)" % env)
        t = main._issue("999", main._RESTORE_SCOPE, "fp-a", "fp-b")
        if not main._consume(t, "999", main._RESTORE_SCOPE, "fp-a", "fp-b"):
            P("①-g 방금 발급한 복원 토큰이 첫 소비에서 거부됐다")
        if main._consume(t, "999", main._RESTORE_SCOPE, "fp-a", "fp-b"):
            P("①-g 복원 토큰이 두 번 소비됐다 ★1회용이 아니다")

        # ── ⑥′ 포화 링에서 복원 1회 = 정확히 1건 축출 ─────────────────────────
        #   디스크 내용은 링에 없는 것이어야 한다: 방금 ⑥이 `EDITED`를 `disk` 대피본으로
        #     담아 뒀으므로 그대로 두면 중복 무쓰기 갈래가 되어 이 절이 잴 것을 잃는다.
        #     그 갈래는 바로 아래 ⑥″가 잰다.
        cfg100.write_bytes(UNSEEN)
        while len(backup_ids("100")) < store.BACKUP_KEEP:
            store.make_backup("100", b"filler=%d\n" % len(backup_ids("100")), "disk", "video.ini")
        saturated = backup_ids("100")
        target = pick("100", "disk")          # 게임 설정 파일로 되돌리는 행(내용이 다르다 → confirm)
        if target is None:
            return finish()
        tok = token_for("100", target["backup_id"])
        env = rpc(main, "restore_backup", "100", target["backup_id"], confirm_token=tok)
        if not env.get("ok"):
            P("⑥′ 포화 링에서 복원이 실패했다 — %s" % env)
        after = backup_ids("100")
        if len(after - saturated) != 1 or len(saturated - after) != 1:
            P("★⑥′ 포화 링 복원이 %d건 추가·%d건 축출했다(1·1이어야 한다)"
              % (len(after - saturated), len(saturated - after)))
        if len(after) != store.BACKUP_KEEP:
            P("⑥′ 포화 링 크기가 %d다(BACKUP_KEEP=%d)" % (len(after), store.BACKUP_KEEP))

        # ── ⑥″ 같은 내용은 다시 담기지 않는다 → 포화 링에서도 축출 0건 ──
        #   ⑥′이 되돌린 내용은 곧 그 백업 파일의 내용이라, 지금 디스크 내용은 이미 `disk` 링에
        #   있다. 그러면 대피가 아무것도 쓰지 않고, 쓰지 않으므로 지우지도 않는다.
        #   ⑥′와 갈래를 갈라서 잰다 — "1건 또는 0건"으로 넓히면 둘 다 못 잰다.
        disk_shas = {store.sha1_file(q) for q in store.list_backups("100")}
        if store.sha1_file(str(cfg100)) not in disk_shas:
            P("⑥″ 사전 조건 실패 — 지금 디스크 내용이 링에 없다(중복 갈래가 안 선다)")
        else:
            target2 = pick("100", "disk")
            if target2 is not None:
                main._CONFIRM_TOKENS.clear()
                ask = rpc(main, "restore_backup", "100", target2["backup_id"])
                if not is_confirm(ask):
                    P("⑥″ 사전 조건 실패 — 되돌릴 곳과 내용이 달라야 하는데 확인을 안 물었다 (%s)"
                      % ask)
                else:
                    if params_of(ask).get("evicted"):
                        P("★⑥″ 대피본이 안 만들어지는 갈래인데 축출을 예고했다 — %s"
                          % params_of(ask).get("evicted"))
                    if params_of(ask).get("evacuates"):
                        P("★⑥″ 링을 한 칸도 안 쓰는데 「백업 한 칸을 씁니다」가 참이라 한다")
                    before2 = backup_ids("100")
                    env = rpc(main, "restore_backup", "100", target2["backup_id"],
                              confirm_token=params_of(ask).get("confirm_token"))
                    if not env.get("ok"):
                        P("⑥″ 복원이 실패했다 — %s" % env)
                    now2 = backup_ids("100")
                    if now2 != before2:
                        P("★⑥″ 같은 내용을 다시 대피시켰다 — 추가=%s 축출=%s"
                          % (sorted(now2 - before2), sorted(before2 - now2)))

        # ═══════════════════════════════════════════════════════════════════
        # ② 3-상태 ②  `proceed` — 설정 파일이 없으면 묻지 않고 재생한다
        # ═══════════════════════════════════════════════════════════════════
        cfg300 = mkgame(tmp, engine, store, "300", "MissingConfig")
        row300 = pick("300", "disk")              # 되돌릴 곳 = 게임 설정 파일(지금 없다)
        if row300 is None:
            return finish()
        os.unlink(str(cfg300))
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", "300", row300["backup_id"])       # 토큰 없이
        if not env.get("ok") or data_of(env).get("outcome") != "restored":
            P("★② proceed(설정 파일 없음)인데 확인을 요구했다 — 잃을 것이 없는 복원이다 (%s)" % env)
        if not cfg300.exists() or cfg300.read_bytes() != THIRD:
            P("★② proceed 복원이 파일을 재생하지 못했다")
        if main._CONFIRM_TOKENS:
            P("② proceed 경로에서 토큰이 발급됐다 — 묻지 않는 경로다")

        # ═══════════════════════════════════════════════════════════════════
        # ③ 실행 중 게임 — 토큰 발급 전에 거부
        # ═══════════════════════════════════════════════════════════════════
        cfg400 = mkgame(tmp, engine, store, "400", "RunningGame")
        cfg400.write_bytes(EDITED)
        row400 = pick("400", "disk")              # 조기 거부는 게임 설정 파일 대상에만 건다
        if row400 is None:
            return finish()
        main._CONFIRM_TOKENS.clear()
        # 음성 대조군 — 실행 중이 아니면 같은 호출이 CONFIRM_REQUIRED다(그래야 ③이 유효하다)
        env = rpc(main, "restore_backup", "400", row400["backup_id"])
        if not is_confirm(env):
            P("③ 음성 대조군 실패 — 미실행 상태에서 CONFIRM_REQUIRED가 아니다 (%s)" % env)
        main._CONFIRM_TOKENS.clear()
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == "400"
        try:
            env = rpc(main, "restore_backup", "400", row400["backup_id"])
        finally:
            engine.running_game = real_running
        if code_of(env) != codes.GAME_RUNNING:
            P("★③ 실행 중 게임의 복원이 GAME_RUNNING으로 거부되지 않았다 — %s" % env)
        if main._CONFIRM_TOKENS:
            P("★③ 확실히 거부될 상황인데 토큰이 발급됐다 — 조기 거부가 아니다")
        if cfg400.read_bytes() != EDITED:
            P("★③ 거부인데 설정 파일이 바뀌었다")

        # ═══════════════════════════════════════════════════════════════════
        # ④ 형태·존재 가드 + 경로 봉쇄
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "restore_backup", "100", "../../etc/passwd")
        if code_of(env) != codes.BAD_IDENTIFIER:
            P("④ 경로가 든 backup_id가 BAD_IDENTIFIER로 거부되지 않았다 — %s" % env)
        env = rpc(main, "restore_backup", "100", ".hidden")
        if code_of(env) != codes.BAD_IDENTIFIER:
            P("④ 점으로 시작하는 backup_id가 거부되지 않았다 — %s" % env)
        env = rpc(main, "restore_backup", "../../etc", "x")
        if code_of(env) != codes.BAD_IDENTIFIER:
            P("④ 비숫자 appid가 거부되지 않았다 — %s" % env)
        env = rpc(main, "list_backups", "9999999")
        if code_of(env) != codes.GAME_NOT_REGISTERED:
            P("④ 미등록 게임의 목록 조회가 GAME_NOT_REGISTERED가 아니다 — %s" % env)
        env = rpc(main, "restore_backup", "100", "20260101-000000-disk-nonexistent.ini")
        if code_of(env) not in (codes.BACKUP_FILE_MISSING, codes.CONFIRM_REQUIRED):
            P("④ 없는 백업 id의 응답이 예상 밖이다 — %s" % env)

        # ④′ backups/<appid>가 외부 디렉터리 링크 — 루트 밖 파일이 설정 파일로 복사되면 안 된다
        cfg500 = mkgame(tmp, engine, store, "500", "BackupsLinked")
        cfg500.write_bytes(EDITED)
        outside = tmp / "outside-backups-500"
        outside.mkdir()
        bait_name = "20260101-000000-disk-video.ini"
        (outside / bait_name).write_bytes(b"quality=BAIT\nshadows=BAIT\nsource=OUTSIDE-ROOT\n")
        shutil.rmtree(store.backups_dir("500"), ignore_errors=True)
        os.symlink(str(outside), store.backups_dir("500"))
        if rows("500"):
            P("★④′ backups가 링크인데 목록이 채워졌다 — 루트 밖을 조회한다 (%s)" % rows("500"))
        env = rpc(main, "get_overview")
        ov500 = {g["appid"]: g for g in data_of(env).get("games", [])}.get("500") or {}
        if ov500.get("backups") != 0:
            P("④′ 링크된 backups의 개수가 0이 아니다 — %s" % ov500.get("backups"))
        main._CONFIRM_TOKENS.clear()
        env = rpc(main, "restore_backup", "500", bait_name)
        if code_of(env) != codes.BACKUP_OUT_OF_ROOT:
            P("★④′ backups 디렉터리 링크를 거부하지 않았다 — %s" % env)
        if cfg500.read_bytes() != EDITED:
            P("★④′ 데이터 루트 밖 파일이 게임 설정 파일로 복사됐다 — 경계 붕괴")
        if main._CONFIRM_TOKENS:
            P("④′ 봉쇄된 경로에서 토큰이 발급됐다")
        os.unlink(store.backups_dir("500"))

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ 파일명 파싱·정렬 — 순진한 구현이 틀리는 픽스처로 잰다
        # ═══════════════════════════════════════════════════════════════════
        cfg600 = mkgame(tmp, engine, store, "600", "ParseTarget")
        bdir = store.backups_dir("600")
        shutil.rmtree(bdir, ignore_errors=True)
        os.makedirs(bdir, exist_ok=True)
        fixtures = [
            # (파일명, 기대 kind, 기대 filename)
            ("20260809-221530-disk-video.ini", "disk", "video.ini"),
            ("20260809-221530-disk-1-video.ini", "disk", "video.ini"),        # 충돌 접미사
            ("20260809-221531-profile_dock-my-game-settings.ini",
             "profile_dock", "my-game-settings.ini"),                          # 하이픈 든 파일명
            ("20260809-221532-profile_internal-video.ini", "profile_internal", "video.ini"),
            ("garbage.ini", "unknown", "garbage.ini"),                         # 미지 형식
            ("20260809-221533-mystery_tag-video.ini", "unknown",
             "20260809-221533-mystery_tag-video.ini"),                         # 미지 tag
        ]
        for name, _, _ in fixtures:
            (pathlib.Path(bdir) / name).write_bytes(DOCK)
        # 링크 항목 1개 — 목록에 뜨면 안 된다. 엔진 G15가 링크를 무조건 거부하므로
        #   목록에 실으면 "누를 수는 있는데 항상 거부되는 행"이 생긴다(없는 조작을 권하지 않는다).
        #   이 픽스처가 없으면 `restore._entries`의 islink 스킵을 지워도 안 걸린다.
        link_bait = tmp / "outside-link-target.ini"
        link_bait.write_bytes(DOCK)
        link_name = "20260809-221534-disk-linked.ini"
        os.symlink(str(link_bait), os.path.join(bdir, link_name))
        got = {r["backup_id"]: r for r in rows("600")}
        if len(got) != len(fixtures):
            P("⑤ 픽스처 %d건 중 %d건만 목록에 왔다" % (len(fixtures), len(got)))
        for name, kind, filename in fixtures:
            row = got.get(name)
            if row is None:
                P("⑤ 픽스처 %s가 목록에 없다" % name)
                continue
            if row["kind"] != kind:
                P("⑤ %s의 kind가 %s다(기대 %s)" % (name, row["kind"], kind))
            if row["filename"] != filename:
                P("★⑤ %s의 파일명이 %r다(기대 %r) — stamp의 하이픈을 고정폭으로 안 뗐다"
                  % (name, row["filename"], filename))
        # 음성 대조군 — 첫 `-` split 구현이면 이 픽스처에서 틀린다(그래야 ⑤가 유효하다)
        naive = naive_parse("20260809-221530-disk-video.ini")
        if naive["stamp"] == "20260809-221530":
            P("⑤ 음성 대조군 무효 — 순진한 파서가 우연히 맞았다(픽스처가 이 결함을 못 잡는다)")
        ours = store.parse_backup_id("20260809-221530-disk-video.ini")
        if ours["stamp"] != "20260809-221530" or ours["stamp_label"] != "2026-08-09 22:15:30":
            P("★⑤ stamp를 15자 고정폭으로 떼지 않았다 — %r / %r"
              % (ours["stamp"], ours["stamp_label"]))

        # ⑤′ 같은 초 충돌 2건의 표시 순서 — 충돌 번호가 큰 쪽이 위다(정렬 키의 둘째 칸)
        order = [r["backup_id"] for r in rows("600")]
        try:
            i_plain = order.index("20260809-221530-disk-video.ini")
            i_suffix = order.index("20260809-221530-disk-1-video.ini")
        except ValueError:
            P("⑤′ 정렬 대상 두 건이 목록에 없다 — %s" % order)
        else:
            if i_suffix >= i_plain:
                P("★⑤′ 같은 초 충돌 접미사가 시간순이 아니다(최신이 위여야 한다) — %s" % order)
        # 음성 대조군 — 사전 역순은 이 픽스처에서 틀린 순서를 낸다(`-1-` < `-video`).
        #   `store.list_backups`는 사전순이 아니라 `backup_order_key`(stamp·충돌 번호·이름)
        #     순서다. 그래서 대조군을 그 함수가 아니라 사전순 자체로 잡는다 — 두 순서가
        #     하나로 합쳐졌다는 사실 자체는 아래 ⑤″가 잰다.
        lex = sorted((os.path.basename(p) for p in store.list_backups("600")), reverse=True)
        li_plain = lex.index("20260809-221530-disk-video.ini")
        li_suffix = lex.index("20260809-221530-disk-1-video.ini")
        if li_suffix < li_plain:
            P("⑤′ 음성 대조군 무효 — 사전 역순이 우연히 맞았다(정렬 결함을 못 잡는 픽스처다)")
        # ⑤″ 순서는 하나다 — prune이 자르는 목록과 화면 목록이 같은 순서여야
        #    축출 예고가 실제로 지워질 파일을 가리킨다(`test_backup_evict_preview` ⓔ와 같은 계약).
        prune_order = [os.path.basename(p) for p in store.list_backups("600")
                       if os.path.basename(p) != link_name]
        if prune_order != order:
            P("★⑤″ prune 순서와 화면 순서가 다르다 — 화면이 지워지지 않을 파일을 댄다\n"
              "      prune=%s\n      화면 =%s" % (prune_order, order))
        # unknown 행도 목록에 살아 있어야 한다(형식을 모른다고 백업을 숨기면 복구 수단이 사라진다)
        if "garbage.ini" not in order:
            P("⑤ 미지 형식 백업이 목록에서 사라졌다 — 복구 수단을 숨기면 안 된다")
        # 링크는 목록에서 빠진다. 음성 대조군: 같은 디렉터리의 실파일은 떠 있다.
        if link_name in order:
            P("★⑤ 링크된 백업이 목록에 떴다 — 눌러도 항상 거부되는 행이다(G15)")
        if not link_bait.exists():
            P("⑤ 음성 대조군 무효 — 링크 대상 파일이 사라졌다(픽스처가 안 섰다)")
        if "20260809-221530-disk-video.ini" not in order:
            P("⑤ 음성 대조군 무효 — 실파일까지 목록에서 빠졌다(스킵이 과하다)")

        # ═══════════════════════════════════════════════════════════════════
        # ⑦ 이웃 슬롯 meta가 비-dict여도 설정 파일 복원은 된다.
        #    `engine.disk_state`가 부르는 `store.slot_holds`가 비-dict meta를 불일치로 접는다.
        #    이 절은 `restore._slot_meta`나 `restore._disk_state`의 예외 포획을 실행하지 않는다.
        # ═══════════════════════════════════════════════════════════════════
        cfg700 = mkgame(tmp, engine, store, "700", "CorruptNeighbourSlot")
        row700 = pick("700", "disk")
        if row700 is not None:
            with open(store.profile_meta_path("700", "internal"), "w", encoding="utf-8") as fh:
                fh.write('"valid json but not an object"')       # 다른 슬롯이 손상됐다
            cfg700.write_bytes(EDITED)
            main._CONFIRM_TOKENS.clear()
            env = rpc(main, "restore_backup", "700", row700["backup_id"])
            if not is_confirm(env):
                P("★⑦ 손상 meta 하나로 복원이 막혔다(기대 CONFIRM_REQUIRED, 실제 %s) — "
                  "복구 경로가 손상 때문에 닫히면 안 된다" % code_of(env))
            else:
                env = rpc(main, "restore_backup", "700", row700["backup_id"],
                          confirm_token=params_of(env).get("confirm_token"))
                if not env.get("ok"):
                    P("★⑦ 손상 meta가 섞인 게임의 복원이 실패했다 — %s" % env)
                elif cfg700.read_bytes() != THIRD:
                    P("⑦ 복원됐다는데 설정 파일이 백업 내용이 아니다")

        # ═══════════════════════════════════════════════════════════════════
        # ⑨ 되돌릴 곳이 프로필 슬롯인 행
        #    잠그는 것: ⓐ 슬롯이 백업 내용이 된다 ⓑ 게임 설정 파일은 안 바뀐다
        #    ⓒ 대피본이 슬롯의 옛 내용으로 1건 생긴다 ⓓ 실행 중이어도 거부되지 않는다
        #    목적지를 뒤바꾼 구현에서는 ⓐ·ⓑ가 동시에 뒤집힌다(음성 대조군을 겸한다).
        # ═══════════════════════════════════════════════════════════════════
        cfg800 = mkgame(tmp, engine, store, "800", "SlotRestore")
        reg800 = store.load_registry()
        cfg800.write_bytes(UNSEEN)
        # 슬롯을 링에 없는 내용으로 만든다: mkgame은 슬롯이 갔다 돌아오게 만들어 두 상태를
        #   모두 대피본으로 담아 두므로, 그 두 상태 중 하나를 슬롯에 두면 이 절의 대피가 중복
        #   무쓰기가 되어 "대피본 1건"을 잴 수 없다. 중복 갈래는 아래 ⑨-e가 잰다.
        engine.save_profile(reg800, "800", "internal")   # 슬롯 = UNSEEN (아직 어디에도 없는 내용)
        store.save_registry(reg800)
        cfg800.write_bytes(EDITED)                       # 게임 설정 파일은 여기서 안 움직여야 한다
        slot_row = None
        for row in rows("800"):
            # 행을 성질로 고른다(mkgame 주석의 규칙): 같은 kind의 행이 둘이라 순서에 기대면
            #   무엇을 재는지 알 수 없다. 여기서 필요한 것은 *슬롯을 INTERNAL로 되돌릴 행*이다.
            if row["kind"] != "profile_internal" or row["same_as_target"]:
                continue
            if store.sha1_file(os.path.join(store.backups_dir("800"), row["backup_id"])) \
                    == store.sha1_bytes(INTERNAL):
                slot_row = row
                break
        if slot_row is None:
            P("⑨ 사전 조건 실패 — 슬롯과 내용이 다른 profile_internal(INTERNAL) 행이 없다 (%s)"
              % [(r["kind"], r["same_as_target"]) for r in rows("800")])
            return finish()
        before_ids = backup_ids("800")
        main._CONFIRM_TOKENS.clear()
        # ⓓ 실행 중에도 슬롯 복원은 묻고 진행한다(게임이 읽지도 쓰지도 않는 데이터다).
        #    같은 세계의 `disk` 행은 ③에서 이미 GAME_RUNNING으로 거부되는 것을 봤다 — 두 대상의
        #    처분이 갈린다는 것이 계약이다.
        real_running = engine.running_game
        engine.running_game = lambda appid: str(appid) == "800"
        try:
            env = rpc(main, "restore_backup", "800", slot_row["backup_id"])
        finally:
            engine.running_game = real_running
        if not is_confirm(env):
            P("★⑨-d 실행 중이라고 슬롯 복원이 막혔다 — 프로필 슬롯은 게임이 읽지도 쓰지도 않는다 "
              "(%s)" % env)
            return finish()
        if params_of(env).get("target") != "internal":
            P("★⑨ 확인창에 실린 되돌릴 곳이 %s다(기대 internal)" % params_of(env).get("target"))
        env = rpc(main, "restore_backup", "800", slot_row["backup_id"],
                  confirm_token=params_of(env).get("confirm_token"))
        if not env.get("ok") or data_of(env).get("outcome") != "restored":
            P("⑨ 정상 토큰인데 슬롯 복원이 안 됐다 — %s" % env)
        if cfg800.read_bytes() != EDITED:
            P("★⑨-b 슬롯 복원이 **게임 설정 파일을 바꿨다** — 사용자가 확인한 곳과 다른 곳에 썼다")
        body = store.profile_file_path("800", "internal")
        if not body or store.sha1_file(body) != store.sha1_bytes(INTERNAL):
            P("★⑨-a 슬롯 본체가 백업 내용이 아니다 — 되돌리기가 목적지에 닿지 않았다")
        meta800 = store.load_meta("800", "internal") or {}
        if meta800.get("sha1") != store.sha1_bytes(INTERNAL):
            P("★⑨ 슬롯 meta가 본체와 어긋난다 — 다음 적용이 PROFILE_CORRUPT로 거부된다 (%s)"
              % meta800.get("sha1"))
        added800 = backup_ids("800") - before_ids
        if len(added800) != 1:
            P("★⑨-c 슬롯 복원이 대피본을 %d건 만들었다(1건이어야 한다)" % len(added800))
        if store.sha1_bytes(UNSEEN) not in {store.sha1_file(q) for q in store.list_backups("800")}:
            P("★⑨-c 덮어쓰기 직전 슬롯 내용이 백업에 없다 — 되돌릴 지점이 없다")
        # 같은 행을 한 번 더: 이제 슬롯 == 백업이므로 already(링 소모 0)
        env = rpc(main, "restore_backup", "800", slot_row["backup_id"])
        if data_of(env).get("outcome") != "already":
            P("⑨ 되돌린 직후 같은 행이 already가 아니다 — 기준이 목적지가 아니다 (%s)" % env)

        # ── ⑨-e 슬롯 대피도 중복이면 한 칸도 안 쓴다 ─────────────────
        #   슬롯은 지금 INTERNAL이고, `profile_internal`(INTERNAL)은 이미 링에 있다(mkgame).
        #   그러니 다른 `profile_internal` 행으로 되돌려도 대피가 새 파일을 만들지 않는다 —
        #   태그가 같고 내용이 같기 때문이다. 태그가 다르면 얘기가 다르다(⑨-f).
        other_row = None
        for row in rows("800"):
            if row["kind"] == "profile_internal" and not row["same_as_target"]:
                other_row = row
                break
        if other_row is None:
            P("⑨-e 사전 조건 실패 — 슬롯과 내용이 다른 profile_internal 행이 없다")
        else:
            main._CONFIRM_TOKENS.clear()
            ask = rpc(main, "restore_backup", "800", other_row["backup_id"])
            if not is_confirm(ask):
                P("⑨-e 사전 조건 실패 — 확인을 안 물었다 (%s)" % ask)
            else:
                if params_of(ask).get("evacuates") or params_of(ask).get("evicted"):
                    P("★⑨-e 슬롯 내용이 이미 같은 태그의 백업에 있는데 확인창이 대피·축출을 "
                      "약속했다 — evacuates=%s evicted=%s"
                      % (params_of(ask).get("evacuates"), params_of(ask).get("evicted")))
                before_e = backup_ids("800")
                env = rpc(main, "restore_backup", "800", other_row["backup_id"],
                          confirm_token=params_of(ask).get("confirm_token"))
                if not env.get("ok"):
                    P("⑨-e 복원이 실패했다 — %s" % env)
                if backup_ids("800") != before_e:
                    P("★⑨-e 같은 태그·같은 내용인데 대피본이 생겼다 — 추가=%s"
                      % sorted(backup_ids("800") - before_e))

        # ── ⑨-f 태그가 다르면 내용이 같아도 쌓인다 — 중복 제거는 태그별이다 ────────
        #   `profile_internal`에 있는 내용이라도 `disk` 대피본을 대신하지 못한다:
        #   되돌릴 곳이 다른 두 행은 서로를 대신할 수 없다. 전역으로 걸렀다면 여기서
        #   대피본이 안 생기고, 화면은 그 상태를 *"디스크 쪽에는 백업이 없다"*로 읽는다.
        slot_now = store.profile_file_path("800", "internal")
        same_as_slot = store.read_bytes(slot_now) if slot_now else b""
        cfg800.write_bytes(same_as_slot)                 # 디스크 = 슬롯 내용(= 링의 profile_* 사본)
        disk_row = pick("800", "disk")
        if disk_row is not None and same_as_slot:
            main._CONFIRM_TOKENS.clear()
            ask = rpc(main, "restore_backup", "800", disk_row["backup_id"])
            if not is_confirm(ask):
                P("⑨-f 사전 조건 실패 — 확인을 안 물었다 (%s)" % ask)
            elif not params_of(ask).get("evacuates"):
                P("★⑨-f 태그가 다른데(그 내용은 `profile_internal`에만 있다) 대피를 안 한다고 "
                  "한다 — 중복 제거가 전역으로 걸리고 있다(태그별이어야 한다)")
            else:
                before_f = backup_ids("800")
                env = rpc(main, "restore_backup", "800", disk_row["backup_id"],
                          confirm_token=params_of(ask).get("confirm_token"))
                if not env.get("ok"):
                    P("⑨-f 복원이 실패했다 — %s" % env)
                added_f = backup_ids("800") - before_f
                if len(added_f) != 1:
                    P("★⑨-f 태그가 다른 같은 내용이 %d건 쌓였다(1건이어야 한다) — 중복 제거가 "
                      "태그를 안 보고 있다" % len(added_f))

        # ═══════════════════════════════════════════════════════════════════
        # ⑧ 토큰의 appid 칸이 실제로 게임을 가른다
        #    지문이 바이트 동일한 두 게임을 만든다 — 그래야 appid 칸만이 유일한 차이가 되고,
        #    그 칸을 `"*"`로 바꾸는 변이가 검출된다(①-f는 지문이 달라 그 변이를 못 잡았다).
        # ═══════════════════════════════════════════════════════════════════
        twin_name = "20260101-010101-disk-video.ini"
        for appid in ("910", "920"):
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(EDITED)                       # 두 게임의 디스크 내용이 같다
            reg = store.load_registry()
            engine.add_game(reg, appid, str(cfg), name="Twin%s" % appid)
            store.save_registry(reg)
            os.makedirs(store.backups_dir(appid), exist_ok=True)
            with open(os.path.join(store.backups_dir(appid), twin_name), "wb") as fh:
                fh.write(DOCK)                            # 백업 내용·이름도 같다
        fp_a = restore.fingerprint(store.load_registry(), "910", twin_name)
        fp_b = restore.fingerprint(store.load_registry(), "920", twin_name)
        if fp_a != fp_b:
            P("⑧ 음성 대조군 무효 — 두 게임의 지문이 다르다(%s vs %s). appid 칸을 잴 수 없다"
              % (fp_a, fp_b))
        tok910 = token_for("910", twin_name)
        env = rpc(main, "restore_backup", "920", twin_name, confirm_token=tok910)
        if not is_confirm(env):
            P("★⑧ 지문이 같은 다른 게임의 토큰이 통과했다 — 토큰의 appid 칸이 게임을 안 가른다 (%s)"
              % env)
        if (tmp / "game920" / "video.ini").read_bytes() != EDITED:
            P("★⑧ 남의 토큰으로 다른 게임의 설정 파일이 바뀌었다")

        return finish()
    finally:
        # 프로세스가 곧 끝나지만 패치를 되돌린다 — 되돌리지 않는 계측기는 다음 사람이
        # 이 파일을 import했을 때 조용히 남는다(계측 장치가 대상을 바꾼 채로 남는 것이 가장 나쁘다).
        try:
            from gfxp import engine as engine_mod
            if "real_engine_restore" in locals():
                engine_mod.restore_backup = locals()["real_engine_restore"]
        except Exception:                                       # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
