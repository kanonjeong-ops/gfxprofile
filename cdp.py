#!/usr/bin/env python3
"""Steam CEF 원격 디버깅(CDP) 헬퍼 — 사람 눈 없이 프론트엔드를 검사한다.

사용자가 원격이라 화면을 직접 못 보는 상황에서, "QAM에 항목이 보이는가" 같은 완료 기준을
자동으로 판정하기 위한 도구다. 읽기 전용 조회가 기본이고, JS 평가는 인자로 명시할 때만 한다.

  python3 cdp.py targets                 # 타겟 목록
  python3 cdp.py eval '<js>' [타깃]      # JS 평가. 타깃 생략 시 SharedJSContext
                                         # 예: eval '<js>' QuickAccess  ← QAM 창의 실제 DOM을 읽는다
                                         #     (제목 부분 일치. targets로 목록 확인)
  python3 cdp.py logs [n]                # 콘솔 로그 수집(n초, 기본 8)
  python3 cdp.py install                 # 설치 → JS 컨텍스트 재시작 → **새 프론트 확인**까지 한 동작
"""
import asyncio
import datetime
import json
import os
import pathlib
import pwd
import re
import sys

import aiohttp

CDP = "http://127.0.0.1:8080"
TARGET_TITLE = "SharedJSContext"


async def _targets(sess):
    async with sess.get(f"{CDP}/json/list") as r:
        return await r.json()


async def _pick(sess, title=TARGET_TITLE):
    targets = await _targets(sess)
    for t in targets:
        if t.get("title") == title:
            return t
    # 부분 일치 폴백 — 'QuickAccess_uid60'처럼 uid가 붙는 창을 짧은 이름으로 부르기 위한 것.
    # ★ 두 개 이상 걸리면 **고르지 않고 실패**한다. 어느 창을 봤는지 모르는 검사는 근거가 못 된다.
    hits = [t for t in targets if title.lower() in (t.get("title") or "").lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(f"target ambiguous: {title} → {[h.get('title') for h in hits]}")
    for t in targets:
        if t.get("title") == title:
            return t
    raise SystemExit(f"target not found: {title}")


async def cmd_targets():
    async with aiohttp.ClientSession() as sess:
        for t in await _targets(sess):
            print("%-8s %-28s %s" % (t.get("type"), (t.get("title") or "")[:28], t.get("id")))


EVAL_TIMEOUT = 60  # 초. awaitPromise를 쓰므로 영영 안 끝나는 Promise를 만나면 여기서 끊는다.


async def cmd_eval(expr, timeout=EVAL_TIMEOUT, title=None):
    try:
        async with asyncio.timeout(timeout):
            return await _eval(expr, title)
    except (asyncio.TimeoutError, TimeoutError):
        print(f"TIMEOUT: {timeout}초 안에 응답이 없었다 (resolve되지 않는 Promise일 수 있다)")
        return 1


async def _eval(expr, title=None):
    async with aiohttp.ClientSession() as sess:
        t = await _pick(sess, title or TARGET_TITLE)
        async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            await ws.send_json({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True,
                           "awaitPromise": True, "allowUnsafeEvalBlockedByCSP": True},
            })
            async for msg in ws:
                d = json.loads(msg.data)
                if d.get("id") == 1:
                    res = d.get("result", {})
                    if "exceptionDetails" in res:
                        print("EXCEPTION:", json.dumps(res["exceptionDetails"], ensure_ascii=False)[:800])
                        return 1
                    print(json.dumps(res.get("result", {}).get("value"), ensure_ascii=False, indent=1))
                    return 0
    return 1


async def cmd_logs(seconds):
    """콘솔 이벤트를 수집한다. 이미 찍힌 과거 로그는 안 나온다 — 붙은 뒤부터다."""
    async with aiohttp.ClientSession() as sess:
        t = await _pick(sess)
        async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            await ws.send_json({"id": 1, "method": "Runtime.enable"})
            await ws.send_json({"id": 2, "method": "Log.enable"})
            try:
                async with asyncio.timeout(seconds):
                    async for msg in ws:
                        d = json.loads(msg.data)
                        m = d.get("method")
                        if m == "Runtime.consoleAPICalled":
                            args = " ".join(
                                str(a.get("value", a.get("description", "")))
                                for a in d["params"].get("args", [])
                            )
                            print("[console.%s] %s" % (d["params"].get("type"), args[:400]))
                        elif m == "Log.entryAdded":
                            e = d["params"]["entry"]
                            print("[log.%s] %s" % (e.get("level"), str(e.get("text"))[:400]))
            except (asyncio.TimeoutError, TimeoutError):
                pass
    return 0


# ── 설치 뒤 「새 프론트가 떴는가」 확인 (D3) ──────────────────────────────────
#
# ★★ 왜 확인이 설치에 붙어 있는가: `install_plugin`은 **파일만 갈아 끼운다.** 이미 평가된
#   프론트 번들은 그대로 살아 있어서, 그 뒤에 보는 화면은 **방금 만든 코드가 아니다.**
#   이 프로젝트는 그 함정에 두 번 빠졌고(옛 화면을 보고 "고쳤다"·"안 고쳐졌다"를 둘 다 오판),
#   그때마다 "다음엔 리로드를 잊지 말자"로 끝났다 — 기억에 맡기는 규칙은 반드시 다시 깨진다.
#   그래서 **리로드와 확인을 명령 안으로 넣는다.** 건너뛰는 플래그는 두지 않는다: 예외를
#   만들면 그 예외가 다음 사고다(「구조로 예외를 없애라」).
# ★ 실측(2026-08-15): `unloadPlugin`+`importPlugin`·캐시버스트·QAM 재개방·UI 모드 왕복은
#   전부 실패했고 **`SteamClient.Browser.RestartJSContext()`(≈35초)만** 새 번들을 평가시킨다.
# ★ 확인의 표지는 `ui hello`의 **`fn`**이다 — 프론트 모듈이 **평가될 때마다** 새로 뽑히는
#   난수라(`src/index.tsx`의 `FN`), 값이 바뀌었다는 것이 곧 "번들이 다시 평가됐다"이다.

# ★ IDENT(=ZIP 최상위 폴더명)가 곧 로그 폴더다 — `build.sh package`의 IDENT와 같은 값이다.
_IDENT = "gfxprofile"
# ★ `Path.home()`이 아니라 passwd를 본다: HOME이 격리된 환경에서 조용히 빈 폴더를 보게 된다
#   (build.sh가 실제로 그 사고를 겪었다).
LOG_DIR = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir) / "homebrew" / "logs" / _IDENT
_HELLO = re.compile(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+\].*ui hello .*\bfn=(\S+)")


def _last_hello():
    """백엔드 로그 전체에서 **가장 최근** `ui hello`의 (시각, fn). 없으면 None."""
    best = None
    for path in sorted(LOG_DIR.glob("*.log")):
        for line in path.read_text(errors="replace").splitlines():
            m = _HELLO.search(line)
            if not m:
                continue
            ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if best is None or ts >= best[0]:
                best = (ts, m.group(2))
    return best


async def _wait_context(deadline):
    """JS 컨텍스트가 다시 응답할 때까지 기다린다. 살아나면 True."""
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with aiohttp.ClientSession() as sess:
                t = await _pick(sess)
                async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                    await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                                        "params": {"expression": "1+1", "returnByValue": True}})
                    async with asyncio.timeout(5):
                        async for msg in ws:
                            if json.loads(msg.data).get("id") == 1:
                                return True
        except Exception:                           # noqa: BLE001 — 재시작 중엔 전부 정상적인 실패다
            pass
        await asyncio.sleep(2)
    return False


# ★ 패널이 **떠야** `ui hello`가 나간다(프론트는 QAM 패널 mount에서 부른다). 그래서 확인은
#   QAM을 여는 것까지 포함한다 — 사람이 다음에 할 일과 정확히 같은 동작이라 추가 비용이 없다.
# ⚠️ 여는 문은 **`GamepadUIMainWindowInstance.MenuStore`**다. `DFL.Navigation.OpenQuickAccessMenu`
#   에도 같은 이름이 있는데 그쪽은 **탭 번호를 듣지 않았다**(2026-08-15 실측: 999를 줘도 알림
#   탭이 열렸고 패널이 안 떠 `ui hello`가 오지 않았다). 이름이 같다고 같은 문이 아니다.
# ★ 순서: **활성 플러그인을 먼저** 정하고 연다 — 반대로 하면 Decky 탭의 목록이 뜬 채로 멈춘다.
_OPEN_QAM = """(() => {
  const w = window.SteamUIStore && window.SteamUIStore.WindowStore;
  const inst = w && w.GamepadUIMainWindowInstance;
  const st = window.DeckyPluginLoader && window.DeckyPluginLoader.deckyState;
  if (!inst || !inst.MenuStore || !st) return "gamepad-ui-not-ready";
  try {
    st.setActivePlugin(%s);
    inst.MenuStore.OpenQuickAccessMenu(999);
    return "opened";
  } catch (e) { return "open-failed: " + (e && e.message ? e.message : String(e)); }
})()"""


async def _eval_value(expr):
    """`_eval`과 달리 **값을 돌려준다**(출력만으로는 판정할 수 없는 자리에서 쓴다)."""
    async with aiohttp.ClientSession() as sess:
        t = await _pick(sess)
        async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            await ws.send_json({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True,
                           "awaitPromise": True, "allowUnsafeEvalBlockedByCSP": True},
            })
            async with asyncio.timeout(20):
                async for msg in ws:
                    d = json.loads(msg.data)
                    if d.get("id") == 1:
                        res = d.get("result", {})
                        if "exceptionDetails" in res:
                            return "exception"
                        return res.get("result", {}).get("value")
    return None


async def _reload_and_verify(before):
    """JS 컨텍스트를 재시작하고 **새 `fn`이 찍힐 때까지** 확인한다. 확인되면 0.

    ⚠️ 실패를 0으로 돌려주지 않는다: "설치는 됐지만 화면은 옛 코드"가 이 명령이 막으려는
       바로 그 상태다. 확인 못 한 것을 성공으로 부르면 검사가 있는데 보지 않는 것이 된다.
    """
    name = json.loads((pathlib.Path(__file__).resolve().parent / "plugin.json").read_text())["name"]
    print(f"프론트 리로드: RestartJSContext() … (≈35초, 이전 fn={before[1] if before else '<없음>'})")

    # ★ 응답을 기다리지 않는다 — 이 호출은 **자기가 붙어 있는 컨텍스트를 죽인다.**
    try:
        async with aiohttp.ClientSession() as sess:
            t = await _pick(sess)
            async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                                    "params": {"expression": "SteamClient.Browser.RestartJSContext()"}})
                await asyncio.sleep(2)
    except Exception as e:                          # noqa: BLE001
        print(f"  (재시작 요청 중 연결이 끊겼다 — 재시작에서는 정상이다: {type(e).__name__})")

    loop = asyncio.get_running_loop()
    if not await _wait_context(loop.time() + 150):
        print("확인 실패: JS 컨텍스트가 150초 안에 돌아오지 않았다")
        return 1
    print("  JS 컨텍스트 복귀")

    # 로더가 플러그인을 다시 주입할 때까지, 그리고 프론트가 실제로 **mount될 때까지** QAM
    # 열기를 되풀이한다.
    # ★ 실측(2026-08-15): 최초 1회만 열고 그 뒤로는 수동으로 `ui hello`를 기다리기만 하면,
    #   신판이 이미 잘 떴는데도 패널이 그 1회 시도에서 mount되지 않아 60초 뒤 exit 1로
    #   **오보**했다(사람이 QAM을 한 번 더 여니 곧바로 `ui hello`가 왔다). 그래서 `opened`가
    #   찍혀도 거기서 멈추지 않고, `fn`이 바뀔 때까지 매 시도마다 QAM을 다시 연다.
    opened = None
    attempts = 0
    deadline = loop.time() + 150                # 이전(90초+60초)과 같은 전체 예산
    while loop.time() < deadline:
        attempts += 1
        try:
            opened = await _eval_value(_OPEN_QAM % json.dumps(name))
        except Exception as e:                  # noqa: BLE001 — 재주입 중엔 왕복이 끊길 수 있다
            opened = f"eval-failed: {type(e).__name__}"
        after = _last_hello()
        if after and (before is None or after[1] != before[1]):
            print(f"리로드 확인: fn {before[1] if before else '<없음>'} → {after[1]} "
                  f"(ui hello {after[0]:%Y-%m-%d %H:%M:%S}, QAM 열기 {attempts}회 시도)")
            return 0
        await asyncio.sleep(3)

    after = _last_hello()
    print(f"확인 실패: QAM을 {attempts}회 다시 열었지만 새 `ui hello`가 오지 않았다 "
          f"(마지막 QAM 열기 결과: {opened} · 마지막으로 본 fn: "
          f"{after[1] if after else '<없음>'} · 기준 fn: {before[1] if before else '<없음>'}). "
          f"화면은 **옛 프론트일 수 있다** — 데스크톱 모드에는 QAM 자체가 없으니 빅픽처"
          f"(`SteamClient.UI.SetUIMode(4)`)나 Game Mode에서 QAM을 손으로 열고 {LOG_DIR}의 fn을 확인하라.")
    return 1


async def cmd_install():
    """설치 + **고아 모달 정리** + **프론트 리로드 확인**을 한 동작으로.

    ★ 왜 정리가 필요한가: 우리는 `utilities/install_plugin` 뒤에 백엔드로 직접
      `confirm_plugin_install`을 보낸다. 그런데 Decky **프론트엔드도 같은 이벤트를 받아**
      별도 창(`Decky Dialog`)에 확인 모달을 띄운다. 백엔드에서 이미 확정했으므로 그 모달은
      **답이 필요 없는 고아**로 화면에 남는다(사용자가 실제로 발견했다).
      요청 기록은 이미 소진돼 눌러도 설치되지 않지만, **화면에 남는 것 자체가 사고다.**
      `취소`를 누르면 로더가 `KeyError`를 내므로, 백엔드를 건드리지 않는 **창 닫기**로 정리한다.
    """
    script = pathlib.Path(__file__).resolve().parent / "pkg" / "install.js"
    if not script.exists():
        print(f"{script} 가 없다 — 먼저 `build.sh package`를 돌려라")
        return 1
    # ★ 리로드 판정의 기준선은 **설치 전에** 잡는다 — 설치 뒤에 잡으면 그 사이에 뜬 화면의
    #   fn을 기준으로 삼아 "안 바뀌었다"를 못 가른다.
    before = _last_hello()
    rc = await cmd_eval(script.read_text())

    async with aiohttp.ClientSession() as sess:
        closed = 0
        for t in await _targets(sess):
            if t.get("title") != "Decky Dialog":
                continue
            try:
                async with sess.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                    await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                                        "params": {"expression": "window.close()"}})
                    async with asyncio.timeout(3):
                        async for _ in ws:
                            break
            except Exception:                       # noqa: BLE001 — 닫히면 응답이 없는 게 정상
                pass
            closed += 1
        print(f"고아 설치 모달 정리: {closed}개")
    if rc:
        print("설치가 실패했으므로 리로드하지 않는다 — 위 메시지를 보라")
        return rc
    return await _reload_and_verify(before)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "install":
        return asyncio.run(cmd_install())
    if cmd == "targets":
        return asyncio.run(cmd_targets()) or 0
    if cmd == "eval":
        return asyncio.run(cmd_eval(sys.argv[2], title=sys.argv[3] if len(sys.argv) > 3 else None))
    if cmd == "logs":
        return asyncio.run(cmd_logs(int(sys.argv[2]) if len(sys.argv) > 2 else 8))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
