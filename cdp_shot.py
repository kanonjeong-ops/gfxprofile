#!/usr/bin/env python3
"""CDP로 화면을 캡처한다 — `Page.captureScreenshot`.

왜 이게 필요한가: `spectacle`은 이 환경에서 간헐적으로 파일을 안 남긴다(2026-08-06 실기 중 발생).
브라우저 엔진에 직접 물어보면 그 변덕을 안 탄다. 게다가 **캡처 대상이 창이 아니라 페이지**라
빅픽처가 뒤에 있어도 그 페이지를 그대로 뜬다.

  python3 cdp_shot.py <출력경로> [타깃제목]      # 기본 타깃: Steam Big Picture
"""
import asyncio
import base64
import json
import sys

import aiohttp

CDP = "http://127.0.0.1:8080"


async def shot(path, title):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{CDP}/json/list") as r:
            targets = await r.json()
        cand = [t for t in targets if title.lower() in (t.get("title") or "").lower()]
        if not cand:
            sys.exit(f"타깃 없음: {title!r} — 가진 것: {[t.get('title') for t in targets][:8]}")
        ws_url = cand[0]["webSocketDebuggerUrl"]
        async with sess.ws_connect(ws_url, max_msg_size=0) as ws:
            await ws.send_str(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send_str(json.dumps({
                "id": 2, "method": "Page.captureScreenshot",
                "params": {"format": "png", "captureBeyondViewport": False},
            }))
            while True:
                msg = json.loads(await ws.receive_str())
                if msg.get("id") == 2:
                    data = msg.get("result", {}).get("data")
                    if not data:
                        sys.exit(f"캡처 실패: {msg}")
                    open(path, "wb").write(base64.b64decode(data))
                    print(f"{path} {len(base64.b64decode(data))} bytes  (타깃: {cand[0]['title']})")
                    return


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(shot(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Big Picture"))
