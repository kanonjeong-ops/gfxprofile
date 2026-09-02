"""Steam UI 언어 판정.

Steam UI 언어를 우선한다. OS locale과 Steam UI 언어는 서로 다른 신호다.

VDF 키는 부분문자열이 아니라 정확 일치로 따라간다. `qa/test_lang_detect.py`는 형제 키
`Steamsteamglobal`이 먼저 나와도 `Steam` 경로만 선택하는지 검사한다.

이 모듈은 `decky`를 import하지 않는다. 로그는 호출자가 남긴다.
"""

import locale
import os
import re

#: 토크나이저: 따옴표 문자열 / { / } 세 종류뿐. VDF에 필요한 전부다.
_TOK = re.compile(r'"((?:[^"\\]|\\.)*)"|(\{)|(\})')

#: 경로 튜플. `Registry`로 감싼 VDF와 `HKCU`부터 시작하는 변형을 차례로 지원한다.
_VDF_PATHS = (
    ("Registry", "HKCU", "Software", "Valve", "Steam", "language"),
    ("HKCU", "Software", "Valve", "Steam", "language"),      # 래퍼 없는 변형 대비
)

_STEAM_TO_UI = {"koreana": "ko", "korean": "ko", "english": "en"}
SUPPORTED = ("en", "ko")


def _walk(text, path):
    """path 튜플을 키 정확 일치로 따라간다.

    '정확 일치'가 이 함수의 존재 이유다 — `Steamsteamglobal`은 `Steam`이 아니다.
    비교는 casefold로 하되 부분문자열 비교는 절대 하지 않는다.
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
                # 0으로 바닥을 친다. 짝이 안 맞는 닫는 중괄호가 오면 depth가 음수가 되고,
                #   그대로 cursor에 넣으면 다음 루프의 want[cursor]가 IndexError를 낸다
                #   (`qa/test_lang_detect.py`의 여분 닫는 중괄호 케이스가 그 입력이다).
                #   불변식(cursor ≥ 0)을 대입 지점에서 지키면 예외 자체가 안 생긴다.
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
        # flatpak Steam 설치의 registry.vdf 자리. 없으면 `detect`가 다음 후보로 넘어간다.
        os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".steam", "registry.vdf"),
    )


def _to_ui(value):
    """Steam 언어명 → UI 언어 코드. 모르면 앞 2글자, 그래도 모르면 en."""
    low = (value or "").strip().lower()
    return _STEAM_TO_UI.get(low) or (low[:2] if low[:2] in SUPPORTED else "en")


def detect(home=None):
    """(lang, source)를 돌려준다.

    registry 파일 열기 실패와 locale 판정의 예상 오류는 폴백한다. Steam registry에서 값을
    얻지 못하면 `LANGUAGE`·`LANG`·locale 순으로 내리고, 마지막에는 `("en", "default")`를
    돌려준다. `source`는 어느 단계가 값을 냈는지 밝힌다.
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
