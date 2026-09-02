#!/usr/bin/env python3
"""감지 제외 목록의 계약 — 「삭제 = 등록 해제 + 감지 제외」.

이 파일이 잠그는 것:
  ① 삭제가 제외에 올린다 + 감사 로그가 `save_registry`보다 먼저 나간다
  ② 탐지 목록에서 사라진다 + `discover_games` 봉투의 `excluded`가 그 사실을 말한다
  ③ 일괄 등록(`register_confident`)도 같은 것을 본다 — 필터가 `_discover_entries` 한 곳이라
     화면에 안 뜬 게임이 일괄 등록에 섞이지 않는다(두 곳에서 거르면 언젠가 갈라진다)
  ④ 제외돼 있지 않은 appid의 재포함도 성공하고, 제외를 풀면 탐지 목록에 다시 뜬다
  ⑤ 등록하면 제외가 자동으로 풀린다 + 봉투에 `backups`(재등록 직후 대피본 안내)
  ⑤′ 그 `backups`를 커밋보다 먼저 확보한다 — 조회가 실패해도 등록만 영구화되지 않는다
  ⑥ 전체 초기화가 제외를 지운다 — `default_registry()` 통째 교체의 구조적 결과다
  ⑦ 손상 값에서 죽지 않는다: 전체가 dict가 아니면 빈 목록, 개별 항목이 dict가 아니면
     그 항목만 격리, 필드 타입이 이상하면 폴백. 그래도 필터는 계속 듣는다
  ⑧ 두 route의 `excluded` 봉투 결과가 같다 — 공통 헬퍼를 쓰는지 자체는 검사하지 않는다
  ⑨ 「게임 0 · 제외 1」: 그 상태에서 `counts.excluded`가 1로 오고(=화면이 초기화 버튼을 켤
     재료가 있고), 초기화하면 제외가 0이 된다. 마지막 게임을 등록 해제하면 `total=0`이라,
     이 재료가 없으면 남은 제외 목록을 지울 방법이 UI에서 사라진다.
     활성 조건식 자체는 여기서 재지 않는다(같은 식을 다시 써서 자평하면 항진식이다) —
       프론트 판정은 설정 팝업 프로브의 몫으로 이월한다

손상 값은 예외가 아니라 빈 목록으로 접는다 — ⑦이 그 접기를 잠근다.
  맨 끝 검사는 `exclude.py` 소스에 `raise `·`code=` 두 문자열이 없는지만 본다.
실데이터에 닿을 수 없다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp로 못박힌다.
"""
import asyncio
import json
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
BODY_A = b"quality=dock\nshadows=high\nsource=A\n"
BODY_B = b"quality=intl\nshadows=low_\nsource=B\n"

#: 로그를 순서까지 붙잡는다 — ①이 「감사 로그가 save보다 먼저」를 잰다.
LOG = []


def boot(tmp):
    fake = types.ModuleType("decky")

    class _Logger:
        def _add(self, msg, *args):
            LOG.append(("log", (msg % args) if args else msg))

        def info(self, msg, *a):
            self._add(msg, *a)

        def warning(self, msg, *a):
            self._add(msg, *a)

        def error(self, msg, *a):
            self._add(msg, *a)

        def debug(self, msg, *a):
            self._add(msg, *a)

        def log(self, level, msg, *a):
            self._add(msg, *a)

    fake.logger = _Logger()
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # 데이터 격리 — main.py가 이 값을 GFXPROFILE_DATA_DIR로 대입한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    # save_registry 호출을 로그 흐름에 끼워 넣는다(순서만 본다 — 동작은 진짜 그대로).
    real_save = main.store.save_registry
    main.store.save_registry = lambda reg: (LOG.append(("save", "")) or real_save(reg))
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def confirmed(main, name, *args, **kwargs):
    """확인 토큰을 요구하면 그대로 되돌려 한 번 더 부른다(2단계 계약을 밟는다)."""
    env = rpc(main, name, *args, **kwargs)
    from gfxp import codes
    if env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED:
        token = (env.get("params") or {}).get("confirm_token")
        env = rpc(main, name, *args, confirm_token=token, **kwargs)
    return env


def synth_entries(games):
    """`discover.discover`를 갈아끼울 합성 결과. 후보 경로는 실재하는 파일이다 —
    `register_confident`가 진짜 `engine.add_game`을 지나야 ③이 실물을 재는 검사가 된다."""
    def fake(known_appids=()):
        out = []
        for appid, name, path in games:
            out.append({"appid": appid, "name": name, "library": str(path.parent.parent),
                        "candidates": [{"path": str(path), "tier": 1, "reason": "x",
                                        "size": path.stat().st_size, "mtime": 1.0}],
                        "confident": True, "registered": appid in set(known_appids)})
        return out
    return fake


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-exclude-"))
    try:
        main = boot(tmp)
        from gfxp import exclude, store
        problems = []

        def P(msg):
            problems.append(msg)

        def excluded_now():
            return store.load_registry().get("settings", {}).get("discover_excluded")

        def overview():
            return (rpc(main, "get_overview").get("data") or {})

        # 합성 세계: 게임 3개(전부 실파일)
        cfgs = {}
        for appid, name in (("111", "Alpha"), ("222", "Beta"), ("333", "Gamma")):
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(BODY_A)
            cfgs[appid] = cfg
        entries = [(a, n, cfgs[a]) for a, n in (("111", "Alpha"), ("222", "Beta"),
                                                ("333", "Gamma"))]
        main.discover.discover = synth_entries(entries)

        env = rpc(main, "register_confident")
        if not env.get("ok") or len(store.load_registry()["games"]) != 3:
            P("사전 조건 실패 — 합성 게임 3개가 등록되지 않았다 (%s)" % env)
            return finish(tmp, problems)
        # 프로필을 하나 만들어 둔다(삭제 시 대피본이 생겨 ⑤의 `backups`가 0이 아니게 된다)
        reg = store.load_registry()
        main.engine.save_profile(reg, "111", "dock")
        store.save_registry(reg)

        # ═══════════════════════════════════════════════════════════════════
        # ① 삭제 → 제외 기록 + 로그가 save보다 먼저
        # ═══════════════════════════════════════════════════════════════════
        del LOG[:]
        env = confirmed(main, "delete_game", "111")
        if not env.get("ok"):
            P("① 삭제가 실패했다 — %s" % env)
        record = (excluded_now() or {}).get("111")
        if not isinstance(record, dict):
            P("★① 삭제했는데 제외 목록에 안 올랐다 — A9가 성립하지 않는다 (%s)" % excluded_now())
        else:
            if record.get("name") != "Alpha":
                P("① 제외 기록의 이름이 캡처되지 않았다(%s) — 지운 뒤엔 이름을 알 방법이 없다"
                  % record.get("name"))
            if not str(record.get("excluded_at", "")).startswith("20"):
                P("① 제외 시각이 ISO 문자열이 아니다 — %s" % record.get("excluded_at"))
        kinds = [kind for kind, _ in LOG]
        texts = [text for kind, text in LOG if kind == "log"]
        if "save" not in kinds:
            P("① 사전 조건 실패 — save_registry 호출이 안 잡혔다")
        elif kinds.index("log") > kinds.index("save"):
            P("★① 감사 로그가 save_registry보다 뒤다 — 저장이 실패하면 지운 기록이 안 남는다(QA R4)")
        if not any("excluded=True" in t for t in texts if "delete_game" in t):
            P("① 삭제 로그에 excluded=True 표기가 없다 — 로그만으로 제외 사실을 못 가린다")

        # ═══════════════════════════════════════════════════════════════════
        # ② 탐지 목록에서 사라지고, 봉투가 그 사실을 말한다
        # ═══════════════════════════════════════════════════════════════════
        data = (rpc(main, "discover_games").get("data") or {})
        seen = {e["appid"] for e in data.get("entries", [])}
        if "111" in seen:
            P("★② 제외한 게임이 탐지 목록에 그대로 있다 — 필터가 안 듣는다 (%s)" % sorted(seen))
        rows = data.get("excluded")
        if not isinstance(rows, list) or [r["appid"] for r in rows] != ["111"]:
            P("② discover_games 봉투의 excluded가 제외분을 안 싣는다 — %s" % rows)
        elif rows[0].get("excluded_at_label", "")[:2] != "20" or \
                len(rows[0].get("excluded_at_label", "")) != 16:
            P("② excluded_at_label이 화면용 표기(YYYY-MM-DD HH:MM)가 아니다 — %r"
              % rows[0].get("excluded_at_label"))

        # ═══════════════════════════════════════════════════════════════════
        # ③ 일괄 등록도 같은 것을 본다
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "register_confident")
        added = [r["appid"] for r in (env.get("data") or {}).get("results", [])]
        if "111" in added:
            P("★③ 제외한 게임이 일괄 등록에 섞였다 — 화면에 안 뜬 것이 등록됐다 (%s)" % added)
        if "111" in store.load_registry()["games"]:
            P("★③ 제외한 게임이 다시 등록됐다")

        # ═══════════════════════════════════════════════════════════════════
        # ④ 재포함 — 없는 항목도 성공 + 다시 탐지된다
        # ═══════════════════════════════════════════════════════════════════
        env = rpc(main, "include_game", "111")
        if not env.get("ok") or (env.get("data") or {}).get("excluded") != []:
            P("④ 재포함 봉투가 비어 있지 않다 — %s" % env)
        if excluded_now():
            P("④ 재포함했는데 registry에 제외 기록이 남았다 — %s" % excluded_now())
        env = rpc(main, "include_game", "111")                   # 두 번째 — 이미 제외가 풀린 항목도 성공하는지 확인
        if not env.get("ok"):
            P("★④ 제외돼 있지 않은 appid의 재포함이 실패했다 — 멱등이 아니다 (%s)" % env)
        seen = {e["appid"] for e in (rpc(main, "discover_games").get("data") or {}).get("entries", [])}
        if "111" not in seen:
            P("★④ 제외를 풀었는데 탐지 목록에 다시 안 뜬다 — %s" % sorted(seen))

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ 등록하면 제외가 자동으로 풀린다 + `backups`
        # ═══════════════════════════════════════════════════════════════════
        env = confirmed(main, "delete_game", "222")              # 다시 제외 상태를 만든다
        if not env.get("ok") or "222" not in (excluded_now() or {}):
            P("⑤ 사전 조건 실패 — 222가 제외되지 않았다 (%s)" % env)
        del LOG[:]
        env = confirmed(main, "add_game", "222", str(cfgs["222"]), "Beta")
        if not env.get("ok"):
            P("⑤ 재등록이 실패했다 — %s" % env)
        if "222" in (excluded_now() or {}):
            P("★⑤ 재등록했는데 제외가 안 풀렸다 — 등록된 게임이 감지에서 숨은 채로 남는다")
        if "backups" not in (env.get("data") or {}):
            P("⑤ add_game 봉투에 backups가 없다 — 재등록 직후 대피본 안내(§9-③)를 그릴 수 없다")
        if not any("was_excluded=True" in t for k, t in LOG if k == "log" and "add_game" in t):
            P("⑤ add_game 로그에 was_excluded= 표기가 없다")
        # 대피본이 실제로 있는 게임(111)에서 backups가 0이 아닌 것도 함께 본다
        env2 = confirmed(main, "add_game", "111", str(cfgs["111"]), "Alpha")
        if (env2.get("data") or {}).get("backups", 0) <= 0:
            P("⑤ 프로필을 지웠던 게임의 backups가 0이다 — 대피본 안내가 항상 거짓이 된다(%s)"
              % (env2.get("data") or {}).get("backups"))

        # ⑤′ 봉투 재료는 커밋보다 먼저 확보한다. 대피본 조회가 실패해도
        #     등록이 영구화된 채로 실패 봉투가 나가면, 사용자가 다시 눌러도 `ALREADY_REGISTERED`라
        #     화면이 영영 성공을 말하지 못한다(되돌릴 UI도 없다).
        confirmed(main, "delete_game", "333")
        real_count = main.restore.backup_count
        main.restore.backup_count = lambda appid: (_ for _ in ()).throw(OSError("주입: 조회 실패"))
        try:
            env = confirmed(main, "add_game", "333", str(cfgs["333"]), "Gamma")
        finally:
            main.restore.backup_count = real_count
        if env.get("ok") is not False:
            P("⑤′ 주입했는데 성공했다 — 주입이 안 먹었다 (%s)" % env)
        elif "333" in store.load_registry()["games"]:
            P("★⑤′ 봉투는 실패인데 등록이 영구화됐다 — 재시도는 ALREADY_REGISTERED로 막힌다"
              "(봉투 재료를 save_registry보다 먼저 확보해야 한다)")
        env = confirmed(main, "add_game", "333", str(cfgs["333"]), "Gamma")   # 재시도로 완결
        if not env.get("ok"):
            P("★⑤′ 실패 뒤 재등록이 안 된다 — %s" % env)

        # ═══════════════════════════════════════════════════════════════════
        # ⑧ 두 route의 excluded 봉투 결과가 같다
        # ═══════════════════════════════════════════════════════════════════
        confirmed(main, "delete_game", "333")
        confirmed(main, "delete_game", "222")
        from_discover = (rpc(main, "discover_games").get("data") or {}).get("excluded")
        from_include = (rpc(main, "include_game", "999").get("data") or {}).get("excluded")
        if from_discover != from_include:
            P("★⑧ 두 route의 excluded 봉투가 다르다 — 화면이 route별 분기를 갖게 된다\n"
              "      discover=%s\n      include =%s" % (from_discover, from_include))
        for row in from_discover or []:
            if set(row) != {"appid", "name", "excluded_at_label"}:
                P("⑧ excluded 행의 키 집합이 계약과 다르다 — %s" % sorted(row))
        if [r["name"] for r in from_discover or []] != sorted(r["name"] for r in from_discover or []):
            P("⑧ excluded 목록이 이름순이 아니다 — %s" % [r["name"] for r in from_discover or []])

        # ═══════════════════════════════════════════════════════════════════
        # ⑦ 손상 값 폴백 — 죽지 않고, 그래도 필터는 듣는다
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        reg["settings"]["discover_excluded"] = "쓰레기"          # 전체가 dict가 아니다
        store.save_registry(reg)
        data = (rpc(main, "discover_games").get("data") or {})
        if not data or data.get("excluded") != []:
            P("★⑦ 전체가 손상된 값에서 discover_games가 빈 목록으로 접히지 않았다 — %s"
              % data.get("excluded"))
        if (overview().get("counts") or {}).get("excluded") != 0:
            P("⑦ 손상 값에서 counts.excluded가 0이 아니다 — %s" % overview().get("counts"))

        reg = store.load_registry()
        reg["settings"]["discover_excluded"] = {
            "111": "이건 dict가 아니다",                          # 격리 대상
            "222": {"name": 5, "excluded_at": 9},                # 필드 타입 폴백
            "333": {},                                          # 필드 자체가 없음
        }
        store.save_registry(reg)
        data = (rpc(main, "discover_games").get("data") or {})
        rows = {r["appid"]: r for r in data.get("excluded") or []}
        if "111" in rows:
            P("★⑦ dict가 아닌 항목이 격리되지 않았다 — 화면이 그릴 수 없는 행이 올라간다")
        if set(rows) != {"222", "333"}:
            P("⑦ 격리 후 남아야 할 항목이 다르다 — %s" % sorted(rows))
        for appid in ("222", "333"):
            row = rows.get(appid) or {}
            if row.get("name") != "appid %s" % appid:
                P("⑦ 이름 폴백이 `appid %s`가 아니다 — %r" % (appid, row.get("name")))
            if row.get("excluded_at_label") != "":
                P("⑦ 시각 폴백이 빈 문자열이 아니다 — %r" % row.get("excluded_at_label"))
        seen = {e["appid"] for e in data.get("entries", [])}
        if seen & {"111", "222", "333"}:
            P("★⑦ 손상 항목이 섞였다고 필터가 풀렸다 — 격리는 표시 문제이고 필터는 계속 들어야 한다"
              " (%s)" % sorted(seen))
        if (overview().get("counts") or {}).get("excluded") != 3:
            P("★⑦ counts.excluded가 원본 키 수(3)가 아니다 — 격리분을 빼면 '지울 것이 없다'는 "
              "거짓말이 되어 초기화로 못 지운다 (%s)" % (overview().get("counts") or {}).get("excluded"))

        # ═══════════════════════════════════════════════════════════════════
        # ⑨ 「게임 0 · 제외 1」 계수 재료 → ⑥ 초기화가 제외를 지운다
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        for appid in list(reg["games"]):
            main.remove.delete_game_data(reg, appid)
        reg["settings"]["discover_excluded"] = {
            "444": {"name": "Delta", "excluded_at": "2026-08-11T10:00:00+0900"}}
        store.save_registry(reg)
        counts = overview().get("counts") or {}
        # 이 절이 잠그는 것은 화면이 그 판정을 내릴 재료가 봉투에 있는가다:
        #   마지막 게임을 등록 해제하면 `total=0`이라, `excluded`가 없으면 화면은 「지울 것이
        #   없다」고 판정할 수밖에 없고 남은 제외 목록을 지울 방법이 사라진다.
        # 활성 조건식(`total>0 || excluded>0`) 자체의 검사는 여기서 하지 않는다 —
        #   같은 식을 테스트가 다시 써서 자평하면 항진식이라 아무것도 안 잰다.
        #   그 판정은 프론트 코드에 붙는 것이므로 설정 팝업 프로브로 이월한다.
        if counts.get("total") != 0:
            P("⑨ 게임을 다 지웠는데 counts.total이 0이 아니다 — %s" % counts)
        if counts.get("excluded") != 1:
            P("★⑨ '게임 0·제외 1' 상태인데 counts.excluded가 1이 아니다(%s) — 화면이 "
              "초기화 버튼을 켤 재료가 없다(D-01)" % counts.get("excluded"))
        env = rpc(main, "reset_all")
        params = env.get("params") or {}
        if params.get("excluded") != 1:
            P("⑨ 초기화 확인창이 제외 건수를 안 말한다 — %s" % params)
        env = rpc(main, "reset_all", confirm_token=params.get("confirm_token"),
                  confirm_text="delete")
        if not env.get("ok"):
            P("⑥ 초기화가 실패했다 — %s" % env)
        if excluded_now():
            P("★⑥ 전체 초기화가 제외 목록을 안 지웠다 — A9 ④ (%s)" % excluded_now())
        if (overview().get("counts") or {}).get("excluded") != 0:
            P("⑥ 초기화 뒤 counts.excluded가 0이 아니다")

        # 관통 종료 상태: 합성 게임 설정 파일 내용이 최초 `BODY_A`와 같다
        for appid, cfg in cfgs.items():
            if cfg.read_bytes() != BODY_A:
                P("★게임 설정 파일 원본이 바뀌었다(%s) — 제외는 registry 한 칸의 일이다" % appid)

        # 관통: `exclude.py` 소스에 `raise ` 또는 `code=` 문자열이 없는지 검사한다
        source = (ROOT / "py_modules" / "gfxp" / "exclude.py").read_text()
        if "raise " in source or "code=" in source:
            P("★exclude.py가 예외·거부 코드를 만든다 — 손상 값은 접기로 했다(설계 §8-B)")

        return finish(tmp, problems)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish(tmp, problems):
    print("감지 제외 계약 — 삭제→제외 · 필터 2route · 재포함 멱등 · 등록 자동 해제 · "
          "손상 폴백 · 초기화 소거 · 게임0/제외1  (데이터: %s)" % tmp)
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
