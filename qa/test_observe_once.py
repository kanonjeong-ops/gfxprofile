#!/usr/bin/env python3
"""단일 게임 route도 확인 단계에서 백업 링을 한 번만 관측한다.

### 무엇이 틀렸었나
`apply_profile`·`save_profile`·`delete_game`·`restore_backup`은 고지를 만들 때 한 번, 지문을
낼 때 또 한 번 링을 나열했다. 그 두 관측 사이에 링이 돌면 화면은 옛 목록의 이름을 대고 토큰은
새 목록에 묶인다 — 그 토큰은 2차 호출에서 그대로 통과하고, 사용자는 자기가 본 적 없는 상태를
승인한 것이 된다. 다게임 경로(`apply_all`·`reset_all`)는 처음부터 한 번의 산출에서 예고와
지문을 같이 냈다. 이 파일은 그 비대칭이 사라졌는지를 잰다.

### 어떻게 재는가 — 창은 주입해야만 열린다
창이 좁아 자연 발생을 기다릴 수 없다. 그래서 `store.list_backups`를 감싸 첫 호출이 값을 돌려준
직후 링을 한 칸 민다(아주 오래된 stamp의 백업 파일 하나를 넣는다 — 포화 링에서 축출 대상이
바뀌는 자리다).
    · 관측이 둘이면 → 고지는 옛 링, 지문은 새 링. 토큰이 새 상태에 묶여 2차 호출에서 통과한다.
    · 관측이 하나면 → 고지도 지문도 옛 링. 2차 호출에서 링이 달라 토큰이 거부된다.
그래서 이 파일의 합격 조건은 "주입 뒤 그 토큰이 거부되는가"다.

### 음성 대조군이 없으면 아무것도 못 잰다
"거부되면 합격"은 토큰이 언제나 거부돼도 초록이다. 그래서 route마다 주입 없는 세계를 하나 더
세워 "그때는 통과한다"를 같이 잰다. 둘이 같이 서야 잰 것이 「주입」이다.

### 부수로 잠그는 것 셋
  · 관측 횟수 자체 — 확인 단계의 `list_backups` 호출이 route당 1회인가(정면 계측).
  · meta·대상 파일의 관측 예산 — 위 계측기는 링만 센다. 그래서 "링은 한 번만 나열하되 meta와
    대상 파일만 확인 뒤에 다시 읽는다"는 변이가 그대로 살아남는다: 지문의 첫 칸이 슬롯 meta가
    기록한 sha1, 둘째 칸이 대상 파일의 sha1과 링 지문이므로 앞의 둘만 재관측해도 고지와 지문이
    다른 시점을 보는 상태가 똑같이 만들어진다. 이 둘은 한 확인 단계에서 여러 번 읽히는 것이
    정상이라 "1회"로는 못 잰다 — 그래서 route별 예산 표(`BUDGET`)로 잠근다.
  · 지문이 봉투로 새지 않는가 — 판정 함수가 지문을 함께 돌려주므로, 접착층이 통째로 splat하는
    순간 화면 계약에 없는 필드가 화면까지 샌다(다게임 경로의 `apply_all`이 같은 규칙을 이미
    못박아 두었다). 프론트가 `fingerprint`를 읽는 곳은 0건이라 봉투에 있으면 그 자체가 결함이다.

합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp라 실사용 데이터에 닿을 수 없다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

SLOT = b"quality=slot\nshadows=high\nsource=SAVED-IN-SLOT\n"     # dock 슬롯에 들어 있는 내용
DISK = b"quality=disk\nshadows=low_\nsource=ONLY-ON-DISK-\n"     # 어느 슬롯에도 없는 내용

#: 주입할 백업 — stamp가 아주 오래라 목록의 맨 끝(= 포화 링에서 가장 먼저 잘릴 자리)에 들어간다.
#: 그래야 주입 뒤에 확인창이 이름을 댄 백업과 실제로 지워질 백업이 갈린다.
INJECT = "20200101-010101-disk-injected.ini"

ROUTES = ("apply_profile", "save_profile", "delete_game", "restore_backup")

#: 확인 단계 한 번이 슬롯 기록(`store.load_meta`)과 대상 파일(`store.sha1_file`)을 읽는 수.
#: 아래 세계(게임 1개 · 슬롯 dock 1개 · 링이 `store.BACKUP_KEEP`칸으로 포화)에서 잰 값이다.
#: 이 표가 있는 이유: 위 주입 계측기는 `list_backups`만 센다. "링은 한 번만 나열하되 meta와
#:   대상 파일만 확인 뒤에 다시 읽는다"는 변이는 그래서 안 걸린다 — 지문의 두 칸이 그 둘에서
#:   나오므로 그것만 재관측해도 같은 창이 다시 열린다.
#: 계약이 아니라 예산이다. 숫자가 움직이면 그 자체가 결함이라는 뜻이 아니라, 무엇이 하나 더
#:   읽혔는지 말하고 지나가라는 뜻이다.
BUDGET = {
    "apply_profile":  (4, 11),
    # 이 route의 예산에는 `confirm._slot_materials`가 부르는 `store.slot_holds` 한 건이 들어
    #   있다(그 안에서 `load_meta` 1 + 슬롯 본체 `sha1_file` 1).
    #   창을 다시 열지는 않는다: 이 관측은 확인창의 표시값(`size`·`sha1_short`)만 정하고 지문에
    #     안 들어간다. 지문 첫 칸은 슬롯 meta가 기록한 sha1이고 둘째 칸은 게임 설정 파일의
    #     sha1이라, 둘 다 이 호출 전에 이미 읽은 값이다. 여기서 읽는 것은 슬롯 본체다.
    #   왜 재는가: 기록이 본체와 어긋난 반쪽 상태에서 확인창이 잃지 않을 것의 크기·해시를 댔다.
    #     그래서 저장 쪽 크기 가드가 이미 쓰던 술어를 그 화면에도 걸었다.
    "save_profile":   (4, 3),
    "delete_game":    (0, 1),
    "restore_backup": (1, 13),
}


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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-observe-once-"))
    main = boot(tmp)
    from gfxp import codes, engine, store
    problems = []
    real_list = store.list_backups
    try:
        def P(msg):
            problems.append(msg)

        def params_of(env):
            return env.get("params") or {}

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        def ring(appid):
            return [os.path.basename(p) for p in real_list(appid)]

        budgets = []

        # ── 세계 하나: 네 route가 전부 `confirm` 갈래에 서 있고 링은 포화다 ────────────
        def build(appid, label):
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(SLOT)
            engine.add_game(reg, appid, str(cfg), name=label)
            engine.save_profile(reg, appid, "dock")               # dock = SLOT (빈 슬롯이라 대피 0)
            store.save_registry(reg)
            cfg.write_bytes(DISK)                                 # 디스크는 어느 슬롯과도 다르다
            while len(ring(appid)) < store.BACKUP_KEEP:           # 링을 채운다 = 축출이 실재한다
                i = len(ring(appid))
                store.make_backup(appid, b"filler-%02d\n" % i, "disk", "fill%02d.ini" % i)
            return cfg

        def newest_backup(appid):
            return ring(appid)[0]

        def call(route, appid, token=None):
            if route == "restore_backup":
                return rpc(main, route, appid, newest_backup(appid), confirm_token=token)
            if route == "delete_game":
                return rpc(main, route, appid, confirm_token=token)
            return rpc(main, route, appid, "dock", confirm_token=token)

        # ── 계측기 ②: meta·대상 파일을 몇 번 읽는가 ─────────────────────────────────
        #
        # 재는 방식은 주입이 아니라 예산이다: 이 둘은 한 확인 단계에서 여러 번 읽히는 것이
        #   정상이라(디스크 sha1 + 슬롯마다 `slot_holds` + 링 중복 판정 …) "1회"로는 못 잰다.
        #   그래서 그 route가 지금 쓰는 수를 위 `BUDGET`에 못박는다 — 관측이 하나라도 늘면
        #   여기서 걸리고, 그것이 고지와 지문 사이에 끼는지는 사람이 판정한다.
        # 표를 갱신할 때는 무엇이 늘었는지 아래 실패 메시지의 내역으로 확인하고 갱신하라.
        watch = {"on": False, "meta": {}, "file": {}}
        real_meta, real_sha = store.load_meta, store.sha1_file

        def watched_meta(appid, profile):
            if watch["on"]:
                key = (str(appid), profile)
                watch["meta"][key] = watch["meta"].get(key, 0) + 1
            return real_meta(appid, profile)

        def watched_sha(path):
            if watch["on"]:
                watch["file"][path] = watch["file"].get(path, 0) + 1
            return real_sha(path)

        def budget_report():
            # 파일은 끝 두 칸으로 적는다 — basename만 쓰면 게임 설정 파일과 슬롯 본체가 둘 다
            #   `video.ini`라 어느 쪽이 늘었는지 못 읽는다.
            metas = sorted(("meta[%s/%s]" % k, v) for k, v in watch["meta"].items())
            files = sorted(("/".join(k.split(os.sep)[-2:]), v) for k, v in watch["file"].items())
            return "meta=%s / file=%s" % (metas, files)

        # ── 계측기: 첫 호출이 값을 돌려준 직후 링을 한 칸 민다 ────────────────────────
        state = {"armed": None, "calls": 0}

        def patched(appid):
            state["calls"] += 1
            result = real_list(appid)
            target = state["armed"]
            if target is not None and str(appid) == str(target):
                state["armed"] = None
                # 고지와 지문 사이에 상태를 밀어 넣는 자리다. 파일을 직접 쓴다 —
                #   `make_backup`을 쓰면 prune이 다시 `list_backups`를 불러 계측기가 자기
                #   자신을 센다(계측기가 대상을 바꾸면 잰 값이 자기 그림자다).
                with open(os.path.join(store.backups_dir(appid), INJECT), "wb") as fh:
                    fh.write(b"injected between notice and fingerprint\n")
            return result

        store.list_backups = patched
        try:
            for i, route in enumerate(ROUTES):
                hit = "9%02d" % (i * 2)          # 주입하는 세계
                ctl = "9%02d" % (i * 2 + 1)      # 음성 대조군(주입 없음)
                build(hit, "Inject-%s" % route)
                build(ctl, "Control-%s" % route)
                main._CONFIRM_TOKENS.clear()

                # ── 음성 대조군: 주입이 없으면 그 토큰은 통과해야 한다 ──────────────────
                #    (같은 호출에서 meta·대상 파일의 관측 수도 잰다 — 주입이 없는 세계라야
                #     예산이 route 자체의 것이다)
                store.load_meta, store.sha1_file = watched_meta, watched_sha
                watch["on"], watch["meta"], watch["file"] = True, {}, {}
                try:
                    env = call(route, ctl)
                finally:
                    watch["on"] = False
                    store.load_meta, store.sha1_file = real_meta, real_sha
                seen = (sum(watch["meta"].values()), sum(watch["file"].values()))
                budgets.append((route, seen))
                if seen != BUDGET[route]:
                    P("★[%s] meta·대상 파일의 관측 수가 예산과 다르다 — 지금=(load_meta=%d, "
                      "sha1_file=%d) / 예산=(load_meta=%d, sha1_file=%d)\n"
                      "      내역: %s\n"
                      "      ★늘었다면 **그 관측이 고지와 지문 사이에 끼는지** 먼저 보라(§14-G ⓕ) — "
                      "지문의 첫 칸은 슬롯 meta의 sha1이고 둘째 칸은 대상 파일의 sha1이라, 링을 한 번만 "
                      "나열해도 이 둘만 다시 읽으면 같은 창이 열린다. 정당한 증감이면 표를 갱신하라"
                      % ((route,) + seen + BUDGET[route] + (budget_report(),)))
                if not is_confirm(env):
                    P("[%s] 사전 조건 실패 — 대조군 1차 호출이 확인을 요구하지 않았다 (%s)"
                      % (route, env))
                    continue
                env = call(route, ctl, params_of(env).get("confirm_token"))
                if is_confirm(env) or not env.get("ok"):
                    P("★[%s] **음성 대조군이 무효다** — 아무것도 주입하지 않았는데 토큰이 거부됐다 "
                      "(%s). 그러면 아래 「거부」가 주입 때문인지 알 수 없다" % (route, env))
                    continue

                # ── 주입: 첫 호출과 다음 호출 사이에 링이 한 칸 돈다 ───────────────────
                before = ring(hit)
                state["armed"], state["calls"] = hit, 0
                env = call(route, hit)
                observed = state["calls"]
                state["armed"] = None
                if not is_confirm(env):
                    P("[%s] 사전 조건 실패 — 주입 세계 1차 호출이 확인을 요구하지 않았다 (%s)"
                      % (route, env))
                    continue
                if INJECT not in ring(hit):
                    P("[%s] 계측기 무효 — 주입이 링에 안 들어갔다(%s). 잴 것이 없다"
                      % (route, ring(hit)))
                    continue
                if ring(hit) == before:
                    P("[%s] 계측기 무효 — 링이 안 움직였다" % route)
                    continue

                # 정면 계측: 확인 단계의 백업 나열이 몇 번인가. 둘 이상이면 그 사이에 낄 창이
                #   있다는 뜻이고, 아래 거부는 우연히 성립한 것일 수 있다.
                if observed != 1:
                    P("★[%s] 확인 단계가 백업 링을 %d번 나열했다 — 고지와 지문이 **다른 관측**을 "
                      "본다(1회여야 한다)" % (route, observed))
                # 지문은 토큰의 재료이지 화면 값이 아니다 — 봉투에 있으면 그 자체가 결함이다.
                for leak in ("fingerprint", "ring", "fp"):
                    if leak in params_of(env):
                        P("★[%s] 지문이 화면 봉투로 샜다 — params에 %r가 있다 (판정 함수가 준 "
                          "지문을 통째로 splat했다)" % (route, leak))

                token = params_of(env).get("confirm_token")
                mark = world_sha(tmp)
                env = call(route, hit, token)
                if not is_confirm(env):
                    P("★★[%s] 고지와 지문 사이에 링이 돈 뒤에도 **낡은 토큰이 통과했다** — "
                      "확인창이 이름을 댄 백업과 실제로 지워지는 백업이 다르다. 사용자는 자기가 "
                      "본 적 없는 상태를 승인한 것이 된다 (%s)" % (route, env))
                after = world_sha(tmp)
                changed = sorted(k for k in set(mark) | set(after) if mark.get(k) != after.get(k))
                if changed:
                    P("★[%s] 거부된 2차 호출이 파일을 바꿨다 — %s" % (route, changed[:6]))
        finally:
            store.list_backups = real_list

        print("관측 1회화 — route %d종 × (주입 · 음성 대조군) (데이터: %s)" % (len(ROUTES), tmp))
        print("  meta·대상 관측 예산: "
              + " / ".join("%s=(%d,%d)" % (r, m, f) for r, (m, f) in budgets))
        if problems:
            print("\nFAIL")
            for x in problems:
                print("  " + x)
            return 1
        print("PASS")
        return 0
    finally:
        store.list_backups = real_list
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
