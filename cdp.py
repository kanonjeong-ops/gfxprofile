#!/usr/bin/env python3
"""Steam CEF 원격 디버깅(CDP) 헬퍼 — 사람 눈 없이 프론트엔드를 검사한다.

사용자가 원격이라 화면을 직접 못 보는 상황에서, "QAM에 항목이 보이는가" 같은 완료 기준을
자동으로 판정하기 위한 도구다. 읽기 전용 조회가 기본이고, JS 평가는 인자로 명시할 때만 한다.

  python3 cdp.py targets                 # 타겟 목록
  python3 cdp.py eval '<js>' [타깃]      # JS 평가. 타깃 생략 시 SharedJSContext
                                         # 예: eval '<js>' QuickAccess  ← QAM 창의 실제 DOM을 읽는다
                                         #     (제목 부분 일치. targets로 목록 확인)
  python3 cdp.py logs [n]                # 콘솔 로그 수집(n초, 기본 8)
  python3 cdp.py install                 # pkg/install.js 실행 + 고아 모달 정리 (권장)
"""
import asyncio
import json
import pathlib
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


async def cmd_install():
    """설치 + **고아 모달 정리**를 한 번에.

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
    return rc


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
