#!/usr/bin/env python3
"""CDP로 키 이벤트를 특정 타깃에 주입한다 — `Input.dispatchKeyEvent`.

왜: `xdotool`은 X 창에 보내므로 어느 CEF 페이지가 그 키를 받을지 우리가 못 정한다(실제로
QAM을 열어 둔 채 방향키를 보냈더니 뒤쪽 라이브러리가 받았다). 페이지를 지정해 넣으면 그 페이지가 받는다.

  python3 cdp_key.py <타깃제목> <키...>      # 키: Down Up Left Right Enter Escape
"""
import asyncio
import json
import sys

import aiohttp

CDP = "http://127.0.0.1:8080"
KEYS = {
    "Down": ("ArrowDown", 40), "Up": ("ArrowUp", 38),
    "Left": ("ArrowLeft", 37), "Right": ("ArrowRight", 39),
    "Enter": ("Enter", 13), "Escape": ("Escape", 27),
}


async def send(title, keys):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{CDP}/json/list") as r:
            targets = await r.json()
        cand = [t for t in targets if title.lower() in (t.get("title") or "").lower()]
        if not cand:
            sys.exit(f"타깃 없음: {title!r}")
        async with sess.ws_connect(cand[0]["webSocketDebuggerUrl"], max_msg_size=0) as ws:
            i = 0
            for k in keys:
                if k not in KEYS:
                    sys.exit(f"모르는 키: {k} (가능: {', '.join(KEYS)})")
                code, vk = KEYS[k]
                for typ in ("rawKeyDown", "keyUp"):
                    i += 1
                    await ws.send_str(json.dumps({
                        "id": i, "method": "Input.dispatchKeyEvent",
                        "params": {"type": typ, "key": code, "code": code,
                                   "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk},
                    }))
                await asyncio.sleep(0.35)
            await asyncio.sleep(0.4)
            print(f"보냄: {' '.join(keys)} → {cand[0]['title']}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    asyncio.run(send(sys.argv[1], sys.argv[2:]))
