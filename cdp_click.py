#!/usr/bin/env python3
"""CDP로 **좌표 지정 마우스 클릭**을 특정 타깃에 주입한다 — `Input.dispatchMouseEvent`.

`cdp.py`(조회·평가)·`cdp_key.py`(키)와 같은 계열의 셋째 도구다. 원격에서 화면을 못 보는 채로
프론트를 조작해야 할 때 쓴다.

  python3 cdp_click.py <타깃제목> '<엘리먼트를 돌려주는 IIFE>'

  예) python3 cdp_click.py QuickAccess \\
        '(() => [...document.querySelectorAll("button")].find(e => e.innerText.trim() === "게임 감지"))()'

## 왜 키보드가 아니라 마우스인가

방향키 탐색은 **포커스가 어디 있는지에 결과가 달린다.** 이 앱은 「eGPU 적용」 같은 **쓰기 버튼**이
목록에 섞여 있어, 한 칸 어긋난 Enter가 의도치 않은 적용을 부른다(`codex-cli-field-guide`가
같은 사고를 실측으로 적어 두었다). 좌표 클릭은 그 자리 하나만 누른다.

## 왜 `element.click()`이 아닌가 `[실측 2026-08-26]`

**Steam의 `Panel Focusable` div는 동기 `.click()`에 반응하지 않는다.** 진짜 `<button>`(QAM의
플러그인 홈 버튼 등)은 `.click()`으로도 열리지만, 게임 목록 행처럼 Steam이 자기 포커스 체계로
그리는 자리는 **실제 포인터 이벤트**를 받아야 움직인다.

## ★함정 — 뷰포트 밖 요소는 **조용히** 안 눌린다 `[실측 2026-08-26]`

`Input.dispatchMouseEvent`는 좌표를 그대로 보내므로, 요소가 스크롤 아래에 있으면
**"클릭 전송"만 찍히고 아무 일도 안 일어난다.** 침묵 실패다 — QA 실기에서 「이 게임 등록 해제」
(y≈620, 뷰포트 575)가 이 자리에서 한 번 죽었다. 그래서 이 도구는 **누르기 전에 항상
`scrollIntoView({block:"center"})`를 돌리고**, 스크롤 뒤의 좌표를 다시 읽는다.
그리고 좌표가 여전히 뷰포트 밖이면 **누르지 않고 실패로 끝낸다** — 예외를 두면 그 예외가
다음 사고다(「구조로 예외를 없애라」).
"""
import asyncio
import json
import sys

import aiohttp

CDP = "http://127.0.0.1:8080"


async def _rpc(ws, mid, method, params):
    await ws.send_json({"id": mid, "method": method, "params": params})
    async with asyncio.timeout(15):
        async for msg in ws:
            d = json.loads(msg.data)
            if d.get("id") == mid:
                return d
    return None


# ★ 사전 판독 + 스크롤을 **한 번의 평가**로 한다 — 둘로 나누면 그 사이에 목록이 다시 그려져
#   읽은 좌표와 누르는 좌표가 갈린다.
_PROBE = """(() => {
  const e = (%s);
  if (!e) return "NOTFOUND";
  e.scrollIntoView({block: "center", inline: "center"});
  const r = e.getBoundingClientRect();
  return JSON.stringify({
    x: r.left + r.width / 2, y: r.top + r.height / 2,
    w: Math.round(r.width), h: Math.round(r.height),
    vw: window.innerWidth, vh: window.innerHeight,
    text: (e.innerText || "").replace(/\\n/g, " ").slice(0, 60),
  });
})()"""


async def click(title, finder):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{CDP}/json/list") as r:
            targets = await r.json()
        cand = [t for t in targets if title.lower() in (t.get("title") or "").lower()]
        if not cand:
            sys.exit(f"타깃 없음: {title!r}")
        async with sess.ws_connect(cand[0]["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            d = await _rpc(ws, 1, "Runtime.evaluate",
                           {"expression": _PROBE % finder, "returnByValue": True})
            val = (d or {}).get("result", {}).get("result", {}).get("value")
            if not val or val == "NOTFOUND":
                print("대상을 못 찾았다")
                return 1
            i = json.loads(val)
            print(f"판독: {i['text']!r} {i['w']}x{i['h']} @ ({i['x']:.0f},{i['y']:.0f}) "
                  f"뷰포트 {i['vw']}x{i['vh']}")
            # ★ 스크롤 뒤에도 밖이면 **누르지 않는다** — 침묵 실패보다 시끄러운 실패가 낫다.
            if not (0 <= i["x"] <= i["vw"] and 0 <= i["y"] <= i["vh"]):
                print("★ 뷰포트 밖이라 누르지 않았다 — 스크롤 컨테이너가 따로 있거나 가려져 있다")
                return 2
            for n, ev in enumerate(("mouseMoved", "mousePressed", "mouseReleased")):
                p = {"type": ev, "x": i["x"], "y": i["y"], "clickCount": 1,
                     "button": "none" if ev == "mouseMoved" else "left",
                     "buttons": 1 if ev == "mousePressed" else 0}
                await _rpc(ws, 10 + n, "Input.dispatchMouseEvent", p)
                await asyncio.sleep(0.08)
            print("클릭 전송")
            return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    return asyncio.run(click(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
