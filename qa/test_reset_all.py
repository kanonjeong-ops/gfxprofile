#!/usr/bin/env python3
"""전체 초기화의 계약.

이 파일이 잠그는 것:
  ① challenge 튜플 바인딩 — type-to-confirm의 판정이 백엔드에 있는가(프론트가 틀려도 막히는가).
     그중 핵심은 registry가 안 변하는 변경이다: `engine.save_profile`은 `reg`를 바꾸지
       않으므로 확인창을 띄운 사이 다른 슬롯에 저장해도 registry.json의 sha1이 그대로다.
       registry sha1 단독 지문은 그 구멍으로 낡은 토큰을 통과시킨다. 그 구멍이 열려 있는지를
       registry sha1이 실제로 안 변했음을 같이 단언하며 잰다.
  ② 하나가 실패해도 나머지는 계속 — `apply_all`의 불변식 그대로. 실패한 게임의 registry
     항목은 남는다(registry ≡ 디스크 실물). 봉투는 `ok:true`.
  ③ 초기화가 `backups/`를 통째로 없애지 않는다 — 안전망을 같이 지우지 않는다. 「하나도 안
     지운다」는 아니다: 포화 링에서는 삭제 전 대피가 `store.prune_backups`를 돌려 가장 오래된
     백업을 밀어낸다. 이 파일의 세계는 포화가 아니라(대피 뒤에도 게임당 최대 3/10) 그 갈래를
     재지 않는다 — `qa/test_evict_notice.py`가 잰다.
  ④ 0게임 엣지 — 지울 것이 없어도 계약이 같은 모양이어야 한다.
  ⑤ 경로 탈출 봉쇄 — `reset_all`은 appid 파라미터가 없어 route의 `_VALIDATORS`를 지나지
     않는다. registry의 games 키가 그대로 경로가 되므로 `"../../X"`·절대경로 키는 데이터
     루트 밖을 rmtree 할 수 있다. 봉쇄는 문 안 한 곳(`remove.delete_game_data`)이고,
     여기서는 제품 경로로 그 문을 지난다.
  ⑥ 레지스트리 버전 가드(U5) — 더 새 버전이 만든 데이터에서 바꾸는 동작만 막히고 읽기와
     탈출로(전체 초기화)는 열려 있는가. 초기화는 `default_registry()`로 통째 교체하므로
     미지 필드를 보존하는 경로가 아니라 새 registry로 빠져나가는 경로다.
  ⑦ 결과 봉투가 「실제로 지운 범주」를 말한다 — `counts.deleted`는 게임만 센다. 초기화는
     registry를 통째로 갈아 끼우므로 표시 이름·감지 제외도 같이 사라지는데, 그 둘을 아무도
     말하지 않으면 등록 0 · 제외 N인 상태에서 화면이 "0개 삭제"라고 말하는 사이 N건이 조용히
     사라진다. 봉투의 `cleared`가 「지우려 했던 것」이 아니라 지운 것인지를 부분 실패까지
     포함해 잰다.
그리고 관통 단언: registry는 통째로 공장초기화(settings·gpu_map 포함) · 게임 설정 파일
원본은 1바이트도 안 바뀐다.

실데이터에 닿을 수 없다 — `boot()`가 `DECKY_PLUGIN_RUNTIME_DIR`을 tmp로 못박고 `main.py`가
  그것을 데이터 루트(`GFXPROFILE_DATA_DIR`)로 대입한다. 전체 초기화 실기는 격리 합성
  데이터로만 한다.
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
APPIDS = ("111", "222", "333")


def boot(tmp):
    fake = types.ModuleType("decky")
    noop = lambda *a, **k: None                                  # noqa: E731
    fake.logger = types.SimpleNamespace(info=noop, warning=noop, error=noop,
                                        debug=noop, log=noop)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # ← 데이터 루트 격리는 이 한 줄이 한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():                                                # noqa: C901  (시나리오 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-reset-"))
    locked = []
    try:
        main = boot(tmp)
        from gfxp import codes, engine, exclude, labels, store
        problems = []

        state = {"by_id": {}, "left": [], "cleared": None}

        def P(msg):
            problems.append(msg)

        def finish():
            """사전 조건이 무너지면 여기로 빠져나온다. 그냥 진행하면 뒤 절이 traceback으로
            죽어 정작 무엇이 깨졌는지가 화면에서 사라진다(진단이 사라지는 실패)."""
            print("전체 초기화 계약 — challenge 바인딩 6종(★registry 불변 변경 포함) · "
                  "실패 격리 · backups 불가침 · 0게임 · ★레지스트리 버전 가드(U5) · "
                  "★결과 봉투 cleared(DEFECT-05)  (데이터: %s)" % tmp)
            print("  결과: %s / registry 잔존=%s / cleared=%s"
                  % (state["by_id"], state["left"], state["cleared"]))
            if problems:
                print("\nFAIL")
                for p in problems:
                    print("  " + p)
                return 1
            print("PASS")
            return 0

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def ask():
            """확인 단계를 밟아 (토큰, params)를 얻는다."""
            env = rpc(main, "reset_all")
            if not is_confirm(env):
                P("확인 단계가 CONFIRM_REQUIRED가 아니다 — %s" % env)
                return None, {}
            params = env.get("params") or {}
            return params.get("confirm_token"), params

        # ═══════════════════════════════════════════════════════════════════
        # ④ 0게임 엣지 — 지울 것이 없어도 계약의 모양은 같다
        # ═══════════════════════════════════════════════════════════════════
        tok, params = ask()
        if params.get("games") != 0 or params.get("profiles") != 0:
            P("④ 0게임인데 파괴 내역이 0/0이 아니다 — %s" % params)
        if params.get("challenge") != "delete":
            P("④ challenge가 고정 단어 'delete'가 아니다 — %s" % params.get("challenge"))
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        if not env.get("ok") or (env.get("data") or {}).get("results") != []:
            P("④ 0게임 초기화가 정상 종료하지 않았다 — %s" % env)
        # ⑦ 봉투의 모양은 지울 것이 없어도 같다. 없으면 화면이 `undefined`를 읽는다.
        if (env.get("data") or {}).get("cleared") != {"named": 0, "excluded": 0}:
            P("⑦ 0게임 봉투에 cleared가 없거나 0/0이 아니다 — %s"
              % (env.get("data") or {}).get("cleared"))

        # ═══════════════════════════════════════════════════════════════════
        # 합성 세계 — 게임 3개, settings·gpu_map을 일부러 더럽혀 둔다
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        cfgs = {}
        for appid in APPIDS:
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(DOCK)
            engine.add_game(reg, appid, str(cfg), name="Game%s" % appid)
            engine.save_profile(reg, appid, "dock")
            cfg.write_bytes(INTERNAL)
            engine.save_profile(reg, appid, "internal")
            cfg.write_bytes(DOCK)
            cfgs[appid] = cfg
        reg["settings"].update(auto_apply=True, mode_override="dock", last_appid="222")
        reg["gpu_map"] = {"0000:03:00.0": "dock"}
        # 표시 이름 2개·감지 제외 2건도 같이 심는다. 이 둘은 `counts.deleted`가 세지 않는
        #   범주라, 봉투가 따로 말하지 않으면 사라진 사실이 화면 어디에도 안 남는다.
        #   제외 appid는 등록 게임과 겹치지 않게 고른다 — 겹치면 무엇이 무엇을 지웠는지
        #   구분이 안 돼 이 절이 아무것도 증명하지 못한다.
        labels.set_name(reg, "dock", "내 독 프로필")
        labels.set_name(reg, "internal", "내 내장 프로필")
        exclude.add(reg, "8801", "제외한 게임 A")
        exclude.add(reg, "8802", "제외한 게임 B")
        store.save_registry(reg)
        cfg_bytes = {a: cfgs[a].read_bytes() for a in APPIDS}

        # ═══════════════════════════════════════════════════════════════════
        # ① challenge 튜플 바인딩
        # ═══════════════════════════════════════════════════════════════════
        tok, params = ask()
        if params.get("games") != 3 or params.get("profiles") != 6:
            P("① 파괴 내역이 3게임/6프로필이 아니다 — %s" % params)

        env = rpc(main, "reset_all", confirm_token=tok)                     # 입력 없음
        if not is_confirm(env):
            P("①-a confirm_text 없이 초기화가 통과했다 ★계약 위반 (%s)" % env)
        tok, _ = ask()
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="Delete")
        if not is_confirm(env):
            P("①-b 대소문자가 다른 입력이 통과했다 ★튜플 비교가 아니다 (%s)" % env)
        tok, _ = ask()
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="지워")
        if not is_confirm(env):
            P("①-c 엉뚱한 입력이 통과했다 ★계약 위반 (%s)" % env)
        env = rpc(main, "reset_all", confirm_text="delete")                 # 토큰 없음
        if not is_confirm(env):
            P("①-d 토큰 없이 초기화가 통과했다 ★계약 위반 (%s)" % env)
        env = rpc(main, "reset_all", confirm_token="지어낸-토큰", confirm_text="delete")
        if not is_confirm(env):
            P("①-e 지어낸 토큰이 통과했다 ★계약 위반 (%s)" % env)
        if len(store.load_registry()["games"]) != 3:
            P("① 거부인데 게임이 지워졌다 — 「거부 시 아무것도 안 지운다」가 거짓이다")

        # ①-f registry가 안 변하는 변경에도 토큰이 무효인가
        tok, _ = ask()
        reg_sha_before = store.sha1_file(store.registry_path())
        cfgs["333"].write_bytes(b"quality=late\nshadows=mid_\nsource=USER-RESAVED\n")
        env = rpc(main, "save_profile", "333", "internal")
        if is_confirm(env):
            env = rpc(main, "save_profile", "333", "internal",
                      confirm_token=(env.get("params") or {}).get("confirm_token"))
        cfgs["333"].write_bytes(DOCK)
        if not env.get("ok"):
            P("①-f 사전 조건 실패 — 확인창 사이 저장이 안 됐다 (%s)" % env)
        if store.sha1_file(store.registry_path()) != reg_sha_before:
            P("①-f 재현 실패 — registry.json이 바뀌어 버렸다. 'registry가 안 변하는 변경'을 "
              "재지 못했으니 이 절은 구멍을 증명하지 않는다")
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        if not is_confirm(env):
            P("★①-f registry가 안 변하는 저장 뒤에도 낡은 토큰이 통과했다 — "
              "지문이 registry sha1 단독으로 돌아갔다(반증 채택 3의 구멍 재개방) (%s)" % env)
        if set(store.load_registry()["games"]) != set(APPIDS):
            P("★① 단계에서 이미 게임이 지워졌다 — ②③ 절을 잴 수 없다(위 실패를 먼저 고쳐라)")
            return finish()

        # ═══════════════════════════════════════════════════════════════════
        # ②③ 하나가 실패해도 계속 · backups 무삭제(비포화 링)
        # ═══════════════════════════════════════════════════════════════════
        before_backups = {a: set(store.list_backups(a)) for a in APPIDS}
        proot = store.profiles_root("222")
        os.chmod(proot, 0o500)                       # rmtree가 하위 폴더를 못 지운다
        locked.append(proot)
        tok, _ = ask()
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        os.chmod(proot, 0o700)

        if not env.get("ok"):
            P("② 게임별 실패가 봉투를 실패로 만들었다 ★불변식이 봉투 층에서 뒤집혔다 (%s)" % env)
        data = env.get("data") or {}
        by_id = {r["appid"]: r["outcome"] for r in data.get("results", [])}
        state["by_id"] = by_id
        if len(data.get("results", [])) != 3:
            P("② 결과 행이 3개가 아니다(%s) — 무엇이 안 됐는지 알 수 없다" % len(data.get("results", [])))
        if by_id.get("222") == "deleted":
            P("② 실패해야 할 게임이 삭제됐다 — 주입이 안 먹었다")
        if by_id.get("111") != "deleted" or by_id.get("333") != "deleted":
            P("★② 하나가 실패하자 나머지가 멈췄다 — %s (불변식 위반)" % by_id)
        row222 = next((r for r in data.get("results", []) if r["appid"] == "222"), {})
        if row222.get("code") != codes.DELETE_FAILED:
            P("② 실패 행의 code가 DELETE_FAILED가 아니다 — 화면이 사유를 구분할 수 없다 (%s)" % row222)
        for rid in ("111", "333"):
            row = next((r for r in data.get("results", []) if r["appid"] == rid), {})
            if row.get("code"):
                P("② %s는 성공인데 code가 실렸다(%s) — 화면이 정상을 문제로 센다" % (rid, row["code"]))

        # ⑦ 게임별 실패가 있어도 cleared는 「지운 것」과 일치한다.
        #   222가 남았다고 표시 이름·제외가 되살아나지는 않는다 — 되심는 것은 `games`뿐이다.
        #   즉 여기서 기대값은 「지우려 했던 것」과 같은 2/2이고, 그 근거는 바로 아래 절의
        #   "settings가 공장초기화됐다" 단언이다. 둘을 같은 자리에서 재야 한 쪽만 무너진
        #   상태(예: 실패분과 함께 settings까지 되살림)를 볼 수 있다.
        state["cleared"] = data.get("cleared")
        if data.get("cleared") != {"named": 2, "excluded": 2}:
            P("★⑦ 부분 실패에서 cleared가 「지운 것」과 어긋난다 — 표시 이름 2·제외 2를 "
              "지워 놓고 봉투는 %s라고 말한다" % data.get("cleared"))

        after = store.load_registry()
        state["left"] = sorted(after["games"])
        if set(after["games"]) != {"222"}:
            P("★② registry가 디스크 실물과 어긋난다 — 남아야 할 것은 실패분 222뿐인데 %s"
              % sorted(after["games"]))
        if after["settings"] != store.default_registry()["settings"] or after["gpu_map"] != {}:
            P("② settings·gpu_map이 공장초기화되지 않았다 — %s / %s"
              % (after["settings"], after["gpu_map"]))
        for appid in ("111", "333"):
            if os.path.exists(store.profiles_root(appid)):
                P("② %s의 profiles/가 남았다" % appid)
        if not os.path.exists(store.profiles_root("222")):
            P("② 실패한 222의 profiles/가 사라졌다 — 실패 판정이 거짓이다")

        # ③ 이 세계에서는 backups/가 하나도 안 지워진다 — 링이 포화가 아니라서다(대피 뒤에도
        #   게임당 최대 3/10). 포화 링에서는 초기화의 대피가 `prune_backups`를 돌려 가장
        #   오래된 백업을 밀어내므로 「불가침」이 무한정 참인 것은 아니다 — 그 갈래는
        #   `qa/test_evict_notice.py`가 잰다. 111·222는 이 시점에 링이 비어 있어 아래 `gone`이
        #   공집합끼리의 비교다; 실제로 무언가를 재는 것은 뒤의 「대피본이 늘었는가」다.
        for appid in APPIDS:
            gone = before_backups[appid] - set(store.list_backups(appid))
            if gone:
                P("★③ 초기화가 backups/를 지웠다 — %s에서 %d건 (마지막 안전망이 사라진다)"
                  % (appid, len(gone)))
            if len(store.list_backups(appid)) <= len(before_backups[appid]):
                P("③ %s의 대피본이 안 늘었다 — 삭제 전 대피가 일어나지 않았다" % appid)

        # 관통: 게임 설정 파일 원본 무접근
        for appid in APPIDS:
            if not cfgs[appid].exists() or cfgs[appid].read_bytes() != cfg_bytes[appid]:
                P("★게임 설정 파일 원본이 바뀌었다(%s) — 초기화는 툴 데이터만 지워야 한다" % appid)

        # 감지 제외 목록도 같이 지워진다. 지우는 코드는 없다 — 초기화가 `default_registry()`를
        #   통째로 갈아 끼우므로 구조적으로 사라진다. 그 구조가 깨지면(예: 제외를 games 밖
        #   어딘가에 따로 보존하면) 여기서 걸린다.
        reg = store.load_registry()
        reg["settings"]["discover_excluded"] = {
            "888": {"name": "제외한 게임", "excluded_at": "2026-08-11T09:00:00+0900"}}
        store.save_registry(reg)

        # 재시도로 완결된다
        tok, params = ask()
        if params.get("games") != 1:
            P("재시도 확인창의 파괴 내역이 갱신되지 않았다 — %s" % params)
        if params.get("excluded") != 1:
            P("초기화 확인창이 제외 건수를 안 말한다 — 모르고 잃는다 (%s)" % params.get("excluded"))
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        if not env.get("ok") or store.load_registry()["games"]:
            P("재시도가 완결되지 않았다 — %s" % env)
        if ((env.get("data") or {}).get("cleared") or {}).get("excluded") != 1:
            P("⑦ 제외 1건을 지웠는데 봉투의 cleared.excluded가 1이 아니다 — %s"
              % (env.get("data") or {}).get("cleared"))
        if store.load_registry()["settings"].get("discover_excluded"):
            P("★ 전체 초기화가 감지 제외 목록을 안 지웠다 — A9 ④ (%s)"
              % store.load_registry()["settings"].get("discover_excluded"))

        # ═══════════════════════════════════════════════════════════════════
        # ⑦ 등록 0 · 제외 N — 봉투가 없으면 조용히 잃는 자리
        #
        #   지울 게임이 하나도 없으므로 `counts.deleted`는 0이다. 그런데 감지 제외 N건과
        #   표시 이름은 실제로 사라진다. 봉투가 `cleared`로 말하지 않으면 화면이 가진 수는
        #   0뿐이고, 사용자는 무엇을 잃었는지 알 방법이 없다.
        # ═══════════════════════════════════════════════════════════════════
        reg = store.load_registry()
        if reg["games"]:
            P("⑦ 사전 조건 실패 — 등록 0 상태가 아니다(%s). 이 절은 「deleted=0인데 지워진 것이 "
              "있다」를 재는 자리다" % sorted(reg["games"]))
        for appid, label in (("9001", "제외 A"), ("9002", "제외 B"), ("9003", "제외 C")):
            exclude.add(reg, appid, label)
        labels.set_name(reg, "dock", "독 이름만 바꿔 둔다")
        store.save_registry(reg)

        tok, params = ask()
        if params.get("games") != 0 or params.get("excluded") != 3 or params.get("named") != 1:
            P("⑦ 사전 조건 실패 — 확인창이 0게임/제외3/이름1을 말하지 않는다 (%s)" % params)
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        data = env.get("data") or {}
        if not env.get("ok"):
            P("⑦ 등록 0·제외 3 초기화가 실패했다 — %s" % env)
        if (data.get("counts") or {}).get("deleted"):
            P("⑦ 등록 0인데 counts.deleted가 실렸다(%s) — 이 절의 전제가 무너졌다"
              % (data.get("counts") or {}).get("deleted"))
        state["cleared"] = data.get("cleared")
        if data.get("cleared") != {"named": 1, "excluded": 3}:
            P("★⑦ 등록 0·제외 3·표시이름 1인데 봉투가 cleared=%s라고 말한다 — 화면이 셀 수 있는 "
              "수가 deleted=0뿐이라 「0개 삭제」라고 말하며 4건을 조용히 잃는다(DEFECT-05)"
              % data.get("cleared"))
        left_settings = store.load_registry()["settings"]
        if left_settings != store.default_registry()["settings"]:
            P("★⑦ 초기화 뒤 settings가 공장 기본이 아니다(%s) — cleared가 「지운 것」이라는 "
              "근거 자체가 무너진다" % left_settings)

        # ⑦-b 지울 것이 하나도 없으면 cleared는 0/0이다 — 없던 일을 사건처럼 말하지 않는다.
        tok, _ = ask()
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        if ((env.get("data") or {}).get("cleared")) != {"named": 0, "excluded": 0}:
            P("⑦-b 지울 것이 없는데 cleared가 0/0이 아니다 — %s"
              % (env.get("data") or {}).get("cleared"))

        # ═══════════════════════════════════════════════════════════════════
        # ⑤ 경로 탈출 봉쇄
        #
        #   `reset_all`은 appid 파라미터가 없어 route의 `_VALIDATORS`를 한 번도 지나지
        #   않는다. registry의 games 키가 그대로 `delete_game_data`로 들어가므로,
        #   손상·수동 편집된 registry의 `"../../X"`·절대경로 키가 그대로 경로가 된다
        #   (`os.path.join`은 절대경로 조각을 만나면 앞의 데이터 루트를 통째로 버린다).
        #   → 봉쇄는 문 안 한 곳(`remove.delete_game_data`)에 있어야 한다.
        #     여기서는 그 문을 제품 경로(reset_all)로 지난다 — 합성 호출이 아니다.
        # ═══════════════════════════════════════════════════════════════════
        targets = {}
        for label in ("REL", "ABS"):
            d = tmp / ("ESCAPE-표적-%s" % label)
            d.mkdir(parents=True, exist_ok=True)
            (d / "victim.txt").write_bytes(b"outside-the-data-root\n")
            targets[label] = d
        # `..`를 몇 번 올라가야 표적에 닿는지는 실제 경로로 계산한다 — 상수로 박으면
        # 데이터 루트 구조가 바뀌는 순간 검사가 아무것도 안 재면서 통과한다.
        rel_key = os.path.relpath(str(targets["REL"]),
                                  os.path.join(store.data_dir(), "profiles"))
        abs_key = str(targets["ABS"])
        if not rel_key.startswith(".."):
            P("⑤ 사전 조건 실패 — 상대 탈출 키가 `..`로 시작하지 않는다(%s)" % rel_key)

        good = tmp / "game999" / "video.ini"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_bytes(DOCK)
        reg = store.default_registry()
        engine.add_game(reg, "999", str(good), name="Survivor")
        engine.save_profile(reg, "999", "dock")
        for key in (rel_key, abs_key):
            reg["games"][key] = {"name": "evil", "config_path": str(good)}
        store.save_registry(reg)

        tok, params = ask()
        if params.get("games") != 3:
            P("⑤ 사전 조건 실패 — 주입한 3키가 확인창에 안 잡혔다(%s)" % params)
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        rows = {r["appid"]: r for r in (env.get("data") or {}).get("results", [])}

        for label, key in (("REL", rel_key), ("ABS", abs_key)):
            d = targets[label]
            if not d.is_dir() or not (d / "victim.txt").exists():
                P("★⑤ 데이터 루트 **밖**이 지워졌다(%s: %s) — 경로 봉쇄가 뚫렸다" % (label, d))
            row = rows.get(key) or {}
            if row.get("outcome") != "refused" or row.get("code") != codes.DELETE_FAILED:
                P("⑤ 탈출 키(%s)의 outcome이 refused/DELETE_FAILED가 아니다 — %s" % (label, row))
            # E59(19판): 비-숫자 appid 키는 되심기에서 제외한다 — 개별 삭제로도 초기화로도
            #   청소할 수 없어 영구히 남던 항목이라, 거부(DELETE_FAILED)됐어도 registry에서
            #   빠진다. 탈출 키(REL·ABS)는 둘 다 비-숫자다.
            if key in store.load_registry()["games"]:
                P("⑤ 거부된 비-숫자 탈출 키(%s)가 registry에 남았다 — E59: 되심기에서 제외돼야 한다" % label)
        # 불변식은 여기서도 그대로다: 하나가 막혀도 정상 게임은 지워진다.
        if (rows.get("999") or {}).get("outcome") != "deleted":
            P("★⑤ 탈출 키가 막히자 정상 게임까지 안 지워졌다 — %s" % rows.get("999"))
        if good.read_bytes() != DOCK:
            P("★⑤ 게임 설정 파일 원본이 바뀌었다")
        state["by_id"] = {k: v["outcome"] for k, v in rows.items()}
        state["left"] = sorted(store.load_registry()["games"])

        # ═══════════════════════════════════════════════════════════════════
        # ⑥ 레지스트리 버전 가드 (U5) — 더 새 버전이 만든 데이터를 만났을 때
        #
        #   미지 키 자체는 `load_registry`의 setdefault와 전체 재직렬화가 보존한다 — 「통째로
        #   사라진다」가 근거가 아니다. 낡은 플러그인이 모르는 스키마의 의미를 지킬 수 없으므로
        #   바꾸는 동작만 막고, 읽기와 탈출로(전체 초기화)는 열어 둔다.
        #   그 셋에 「거부하고도 안 쓴다」를 더해 넷을 한자리에서 잰다 — 하나만 보면 나머지가
        #   무너진 것을 못 본다(막기만 하면 화면이 안 뜨고, 열기만 하면 데이터가 뭉개지고,
        #   탈출로가 막히면 영영 못 벗어나고, 거부하면서 쓰면 「바뀌지 않았습니다」가 거짓이 된다).
        # ═══════════════════════════════════════════════════════════════════
        future = tmp / "game777" / "video.ini"
        future.parent.mkdir(parents=True, exist_ok=True)
        future.write_bytes(DOCK)
        reg = store.default_registry()
        engine.add_game(reg, "777", str(future), name="FromFuture")
        engine.save_profile(reg, "777", "dock")
        reg["version"] = store.REGISTRY_VERSION + 1          # ← 미래 버전이 만든 데이터
        store.save_registry(reg)
        before = pathlib.Path(store.registry_path()).read_bytes()

        env = rpc(main, "set_profile_name", "dock", "새 이름")
        if env.get("ok") or env.get("code") != codes.REGISTRY_NEWER:
            P("⑥-① 변이 RPC가 REGISTRY_NEWER로 막히지 않았다 — %s" % env)
        env = rpc(main, "get_overview")
        if not env.get("ok") or len((env.get("data") or {}).get("games", [])) != 1:
            P("⑥-② 읽기까지 막혔다 — 화면이 아무것도 못 그린다 (%s)" % env)
        if pathlib.Path(store.registry_path()).read_bytes() != before:
            P("★⑥-④ 거부인데 registry.json이 바뀌었다 — 「바뀌지 않았습니다」가 거짓이다")

        tok, _ = ask()
        env = rpc(main, "reset_all", confirm_token=tok, confirm_text="delete")
        if not env.get("ok"):
            P("★⑥-③ 탈출로(전체 초기화)까지 막혔다 — 이 버전으로 새로 시작할 방법이 사라진다 (%s)"
              % env)
        if store.load_registry().get("version") != store.REGISTRY_VERSION:
            P("⑥-③ 초기화가 version을 이 버전으로 되돌리지 않았다 — %s"
              % store.load_registry().get("version"))

        return finish()
    finally:
        for path in locked:
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
