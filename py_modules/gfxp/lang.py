"""Steam UI 언어 판정.

**신호는 `LANG` 환경변수가 아니라 Steam UI 언어다.** 이 기기가 반례다 —
Steam은 `koreana`인데 `LANG=en_US.UTF-8`이다. `LANG`을 보면 한국어 사용자에게 영어가 뜬다.

★ 참조 구현(SimpleDeckyTDP)을 베끼지 말 것. 그쪽은 `steamglobal`을 부분문자열로 지우려 하는데
  실물 키는 `Steamsteamglobal`이라 **이 기기에서 무동작**이다. 지금 두 값이 다 `koreana`라
  결과만 우연히 맞는다.

이 모듈은 `decky`를 import하지 않는다 — 엔진 계층은 Decky 없이도 import되고 테스트돼야 한다.
로그는 호출자(main.py)가 남긴다.
"""

import locale
import os
import re

#: 토크나이저: 따옴표 문자열 / { / } 세 종류뿐. VDF에 필요한 전부다.
_TOK = re.compile(r'"((?:[^"\\]|\\.)*)"|(\{)|(\})')

#: 경로 튜플 — 실물 최상위 키 `Registry`를 포함한다.
#: 1판은 `HKCU`부터 시작해 실물에서 None을 냈고, 폴백이 영어를 띄워 **버그가 조용히 숨었다.**
_VDF_PATHS = (
    ("Registry", "HKCU", "Software", "Valve", "Steam", "language"),
    ("HKCU", "Software", "Valve", "Steam", "language"),      # 래퍼 없는 변형 대비
)

_STEAM_TO_UI = {"koreana": "ko", "korean": "ko", "english": "en"}
SUPPORTED = ("en", "ko")


def _walk(text, path):
    """path 튜플을 **키 정확 일치**로 따라간다.

    '정확 일치'가 이 함수의 존재 이유다 — `Steamsteamglobal`은 `Steam`이 아니다.
    비교는 casefold로 하되 **부분문자열 비교는 절대 하지 않는다.**
    """
    want = [p.casefold() for p in path]
    depth, cursor, pending = 0, 0, None
    for m in _TOK.finditer(text):
        s, ob, cb = m.group(1), m.group(2), m.group(3)
        if s is not None:
            if depth == cursor and s.casefold() == want[cursor]:
                if cursor == len(want) - 1:
                    nxt = _TOK.search(text, m.end())          # 값은 바로 다음 토큰
                    return nxt.group(1) if (nxt and nxt.group(1) is not None) else None
                pending = True                                # 다음 '{' 를 열면 한 칸 전진
            else:
                pending = False
        elif ob:
            depth += 1
            if pending and depth == cursor + 1:
                cursor += 1
            pending = False
        else:
            depth -= 1
            if depth < cursor:
                # ★ 0으로 바닥을 친다. 짝이 안 맞는 닫는 중괄호가 오면 depth가 음수가 되고,
                #   그대로 cursor에 넣으면 다음 루프의 want[cursor]가 IndexError를 낸다
                #   (여분 중괄호 8개로 실제 재현했다). 설계는 이걸 "호출부 try/except"로 덮으라
                #   했지만, **불변식(cursor ≥ 0)을 대입 지점에서 지키면 예외 자체가 안 생긴다.**
                cursor = max(0, depth)                        # 형제 섹션으로 나왔다 — 되감기
            pending = False
    return None


def steam_language(text):
    """(값, 출처경로) 또는 (None, None)."""
    for p in _VDF_PATHS:
        value = _walk(text, p)
        if value:
            return value, "/".join(p)
    return None, None


def registry_candidates(home=None):
    """읽어 볼 registry.vdf 후보. 순서대로 처음 성공한 것을 쓴다."""
    home = home or os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~")
    return (
        os.path.join(home, ".steam", "registry.vdf"),
        # flatpak Steam(Bazzite 후보). 이 기기엔 부재함을 실측했다 — U13으로 열려 있다.
        os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".steam", "registry.vdf"),
    )


def _to_ui(value):
    """Steam 언어명 → UI 언어 코드. 모르면 앞 2글자, 그래도 모르면 en."""
    low = (value or "").strip().lower()
    return _STEAM_TO_UI.get(low) or (low[:2] if low[:2] in SUPPORTED else "en")


def detect(home=None):
    """(lang, source)를 돌려준다. **예외를 밖으로 내보내지 않는다.**

    언어 판정 실패로 플러그인이 안 뜨는 것이 훨씬 나쁘므로 마지막에는 반드시 "en"으로 떨어진다
    (fail-open). 대신 **어느 단계가 이겼는지를 source로 반드시 남긴다** — 그것이 이 결함의
    재발 방지 장치다. `source`가 `steam-registry:*`가 아니면 판정이 실패한 것이고,
    완료 기준은 그것을 불합격으로 본다.
    """
    for path in registry_candidates(home):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        value, where = steam_language(text)
        if value:
            return _to_ui(value), "steam-registry:%s" % where

    for env in ("LANGUAGE", "LANG"):
        raw = os.environ.get(env)
        if raw:
            return _to_ui(raw.split(":")[0].split(".")[0].split("_")[0]), env

    try:
        loc = locale.getdefaultlocale()[0]
    except (ValueError, TypeError):
        loc = None
    if loc:
        return _to_ui(loc.split("_")[0]), "locale"

    return "en", "default"
