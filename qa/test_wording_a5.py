#!/usr/bin/env python3
"""A5·A6 금칙 문자열 게이트 — **번역표 전량**을 본다. 명세 §15-B ⑨ · §10 잔존어 전수 검사.

### 왜 이 검사가 필요한가 (A5·A6, 사용자 확정 공리)
이 툴에는 이름이 비슷한 세 가지가 있다: **게임의 설정 파일**(원본) · **프로필**(우리가 저장한
사본) · **메뉴 「설정」**(플러그인 전역 설정). 셋을 뭉뚱그리면 사용자는 *"무엇이 덮어써지는지"*를
틀리게 읽는다.
→ A5: **"설정"은 메뉴명과 게임 원본 파일에만 쓴다.** 프로필 내용은 "프로필"·"내용"이라 부른다.
→ A6: **"미완/미완성"은 전면 금지**(프로필 없음은 정상 상태다 — 재촉하지 않는다).

### 2026-08-12 P16 게이트 C7 — **접두군 5개 → 전역 231키**
전까지 이 검사는 확인창 키군(`APPLY_ALL_`·`SAVE_`·`RESTORE_`·`DELETE_`·`RESET_`)만 훑었다.
그런데 `test_wording_10a`의 머리말은 §10-A의 「어휘 규칙 행」(*"`MANAGE_NAMES_HINT` 등 '설정'
충돌 문구"*)의 기계 판정을 **이 파일에 위임**하고 있었다 — 그 키는 접두군 밖이라 **아무도 안
보고 있었다.** 실증: `MANAGE_NAMES_HINT`에 "미완성 설정"을 주입해도 EXIT=0이었다.
설계 §10의 문면도 *"`ko.json` **전량**에 대해 grep"*이고 확인창 키군은 그 안의 **포함 관계**다.
→ **범위를 전역으로 올린다.** 접두 목록이 사라지면 "새 키가 어느 군에 들어가는가"라는 질문
자체가 없어진다(구조로 예외를 없앤다).

### 어떻게 오탐 없이 전역으로 가나 — 키 예외가 아니라 **용법**으로 판별한다
전역으로 올리면 정당한 "설정"이 11키(ko)·13키(en)에서 걸린다. 전부 *"게임의/그래픽/Decky의
설정"*이거나 메뉴명이다 — 즉 **소유자가 문장에 적혀 있는** 용법이다. A5가 금지하는 것은
*소유자 없는 "설정"이 프로필을 가리키는 것*이므로, **소유자를 명시한 어구를 지운 뒤 남는
"설정"**만 본다. 그래서 아래는 키 예외 목록이 아니라 **어구 목록**이다 — 새 키가 같은 어법을
쓰면 자동으로 통과하고, 프로필을 "설정"이라 부르면 새 키여도 걸린다.

`EXEMPT`(키 예외)는 **비어 있고, 비어 있는 것이 정상이다.** 예외가 필요해 보이면 문구를 고쳐
규칙으로 흡수하는 것이 이 게이트의 정상 처분이다(P13 선례: `RESTORE_CONFIRM_BACKUP`을
"복원 전에 지금의 **게임 설정 파일**도 …"로 고쳐 마지막 키 예외를 소거했다.
C7 선례: `DISCOVER_TIER3`(en)의 "looks like settings" → "looks like **a settings file**" —
ko "이름만 **설정 파일**처럼 보임"과 어긋나 있던 번역을 맞추면서 예외도 함께 사라졌다).

### 왜 JSON 값을 보는가
프로브의 `t()` 목은 **키를 그대로 돌려준다**(그래야 렌더 대조가 언어에 안 묶인다) — 그래서
프로브로는 값에 무엇이 적혀 있는지 **원리적으로 못 본다.** 값의 규율은 값이 사는 곳에서 잰다.
§10-A 확정값의 **바이트 고정**은 `test_wording_10a.py` 소관이다 — 여기는 금칙어만 본다.

★ 이 검사도 **자기 자신을 반증한다**: 아래 대조군을 매 실행마다 돌린다.
  · 음성(주입 → 반드시 FAIL): **접두군 밖 키**에 A5·A6 위반을 넣는다. 이것이 C7의 실증이다.
  · 양성(허용 용법 주입 → 통과 유지): 오탐도 거짓 검사다 — 다음 사람이 검사를 꺼 버린다.
"""
import copy
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
I18N = ROOT / "src" / "i18n"

#: **소유자를 명시한 용법**은 A5가 허용한다 — 지운 뒤 남는 "설정"만 프로필을 가리키는 것으로 본다.
#:   ko: 설정 파일(원본 파일) · 게임 설정/게임의 설정/게임에서 설정(게임 소유) ·
#:       그래픽 설정(게임 화면 옵션) · Decky 설정(Decky의 메뉴) · 「설정」(우리 메뉴명 인용)
#:   en: settings file(s)/config file(s) · graphics|game|their|your settings(소유자 명시) ·
#:       settings of …(of-소유격) · Decky settings · “Settings”(메뉴명 인용)
#: ⚠️ **바깥으로 넓히지 말 것.** 여기에 소유자 없는 어구("saved settings" 류)를 넣는 순간
#:   A5는 판정을 멈춘다 — 그것이 정확히 A5가 금지하는 표현이다.
ALLOWED_PHRASES = {
    "ko": ("설정 파일", "게임 설정", "게임의 설정", "게임에서 설정", "그래픽 설정",
           "Decky 설정", "「설정」"),
    "en": ("settings file", "config file", "graphics settings", "game settings",
           "their settings", "your settings", "settings of", "Decky settings", "“Settings”"),
}

#: 메뉴명 그 자체(값 전체가 메뉴 이름인 키)는 A5가 허용하는 유일한 단독 사용이다.
MENU_VALUES = {"설정", "Settings"}

#: ★ 키별 예외 — **근거 없이 늘리지 말 것.** 여기 이름을 올리는 것은 "이 문구의 A5 판정은
#:   검사 밖"이라는 선언이다. **지금은 비어 있고, 비어 있는 것이 이 게이트의 정상 상태다.**
EXEMPT: set = set()

#: 금칙 — A6("미완/미완성" 전면 제거). 영어는 그 대응어.
FORBIDDEN = {"ko": ("미완",), "en": ("incomplete",)}

LANGS = ("ko", "en")


def scrub(value, lang):
    """허용 용법을 지운 잔여 문자열. 남은 자리의 "설정"이 곧 프로필을 가리키는 용법이다."""
    out = value
    for phrase in ALLOWED_PHRASES[lang]:
        out = re.sub(re.escape(phrase) + r"s?", " ", out, flags=re.IGNORECASE)
    return out


def scan(tables):
    """번역표 두 벌을 받아 위반 목록을 돌려준다.

    ★ **대조군이 이 함수를 그대로 다시 돌린다** — 판정과 대조군이 같은 코드를 보아야
      "검사가 죽은 채 초록"이 생기지 않는다(`test_popup_shell`의 `data_contract`와 같은 구조).
    """
    problems = []
    checked = 0
    for lang in LANGS:
        for key, value in tables[lang].items():
            checked += 1
            if key in EXEMPT or value in MENU_VALUES:
                continue
            for word in FORBIDDEN[lang]:
                hit = word in value.lower() if lang == "en" else word in value
                if hit:
                    problems.append(
                        f"★{key}({lang})에 금칙어 '{word}' — A6: 프로필 없음은 정상 상태이고 "
                        f"재촉하지 않는다\n      {value}")
            rest = scrub(value, lang)
            if lang == "ko" and "설정" in rest:
                problems.append(
                    f"★{key}(ko)의 '설정'이 소유자를 밝히지 않는다 — 프로필을 '설정'이라 부르면 "
                    f"화면이 무엇을 덮어쓰는지 흐려진다(A5). 게임/파일/메뉴를 가리키는 것이면 "
                    f"그렇게 적어라(\"게임 설정 파일\"·\"그래픽 설정\")\n      {value}")
            if lang == "en" and re.search(r"\bsettings\b", rest, re.IGNORECASE):
                problems.append(
                    f"★{key}(en)의 'settings'가 소유자를 밝히지 않는다 (A5)\n      {value}")

    # 범위가 조용히 줄어드는 경로를 막는다 — 표가 231키인데 몇 개만 재고 통과하면 검사가 아니다.
    want = sum(len(tables[lang]) for lang in LANGS)
    if checked != want:
        problems.append(f"검사 대상이 {checked}건이다(전량 {want}건이어야 한다) — 범위가 줄었다")
    if checked < 400:
        problems.append(f"검사 대상이 {checked}건뿐이다 — 번역표를 못 읽었거나 범위가 무너졌다")
    return problems


#: 음성 대조군 — (설명, 언어, 키, 주입 문장, **기대 판정 조각**).
#: ★ 전부 **접두군 밖 키**다: C7 이전이라면 한 건도 안 잡혔다(그것이 이 확장의 이유다).
NEGATIVE = [
    ("접두군 밖 키에 A6 금칙어(관리 안내)", "ko", "MANAGE_NAMES_HINT",
     "미완성 프로필이 있습니다.", "MANAGE_NAMES_HINT(ko)에 금칙어 '미완'"),
    ("접두군 밖 키에서 프로필을 '설정'이라 부름", "ko", "MANAGE_NAMES_HINT",
     "저장해 둔 설정을 덮어씁니다.", "MANAGE_NAMES_HINT(ko)의 '설정'이"),
    ("접두군 밖 키(en)에 A6 금칙어", "en", "QAM_ABOUT",
     "This profile is incomplete.", "QAM_ABOUT(en)에 금칙어 'incomplete'"),
    ("접두군 밖 키(en)에서 프로필을 'settings'라 부름", "en", "QAM_ABOUT",
     "This overwrites the saved settings.", "QAM_ABOUT(en)의 'settings'가"),
    # 접두군 **안쪽**도 여전히 살아 있는가 — 범위를 넓히다 원래 보던 곳을 잃지 않았음을 잰다.
    ("확인창 키군(기존 범위)에서 프로필을 '설정'이라 부름", "ko", "SAVE_CONFIRM_BODY",
     "저장돼 있던 설정을 덮어씁니다.", "SAVE_CONFIRM_BODY(ko)의 '설정'이"),
]

#: 양성 대조군 — 허용 용법을 **접두군 밖 키**에 넣어도 통과해야 한다(오탐도 거짓 검사다).
POSITIVE = [
    ("게임 설정 파일 지칭", "ko", "NAME_EDIT_HINT", " 게임 설정 파일은 건드리지 않습니다."),
    ("그래픽 설정 지칭", "ko", "QAM_ABOUT", " 그래픽 설정은 게임이 들고 있습니다."),
    ("소유자 명시(en)", "en", "NAME_EDIT_HINT", " The game's settings file is untouched."),
    ("메뉴명 인용", "ko", "OPEN_SETTINGS_DESC", " 「설정」에서 바꿉니다."),
]


def main():
    tables = {}
    for lang in LANGS:
        path = I18N / f"{lang}.json"
        if not path.is_file():
            print(f"FAIL: {path} 없음")
            return 1
        tables[lang] = json.loads(path.read_text(encoding="utf-8"))

    problems = scan(tables)
    total = sum(len(tables[lang]) for lang in LANGS)
    print(f"A5·A6 문구 게이트 — **번역표 전역** {total}건(ko {len(tables['ko'])} + "
          f"en {len(tables['en'])}) · 키 예외 {sorted(EXEMPT) or '없음'}")
    print(f"  허용 어구(소유자 명시) ko {len(ALLOWED_PHRASES['ko'])} · "
          f"en {len(ALLOWED_PHRASES['en'])} — 키가 아니라 **용법**으로 판별한다")
    print("  값 고정(§10-A)은 test_wording_10a.py 소관 — 여기는 금칙어만 본다")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1

    # ── 음성 대조군: 접두군 **밖** 위반을 그 판정이 잡는가 ─────────────────────
    for label, lang, key, injected, expect in NEGATIVE:
        if key not in tables[lang]:
            print(f"FAIL — 음성 대조군 주입 실패({label}): {key}가 {lang}.json에 없다. 검사가 무효다.")
            return 1
        mutated = copy.deepcopy(tables)
        mutated[lang][key] = injected
        caught = [c for c in scan(mutated) if expect in c]
        if not caught:
            print(f"FAIL — 위반을 주입했는데 **그 판정이** 안 잡았다: {label}")
            print(f"       기대 조각 {expect!r} / 잡힌 것: {scan(mutated)}")
            return 1
        print(f"  음성 대조군 검출: {label} → {caught[0].splitlines()[0][:100]}")

    # ── 양성 대조군: 허용 용법은 통과한다(오탐 0) ──────────────────────────────
    for label, lang, key, suffix in POSITIVE:
        if key not in tables[lang]:
            print(f"FAIL — 양성 대조군 대상이 없다({label}): {key}/{lang}. 검사가 무효다.")
            return 1
        mutated = copy.deepcopy(tables)
        mutated[lang][key] = tables[lang][key] + suffix
        noise = scan(mutated)
        if noise:
            print(f"FAIL — **허용된 용법**을 오탐했다: {label}")
            for n in noise:
                print("  " + n)
            return 1
        print(f"  양성 대조군 통과(오탐 없음): {label}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
