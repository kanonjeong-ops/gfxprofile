#!/usr/bin/env python3
"""A5 금칙 문자열 게이트 — 확인창 문구가 **프로필을 "설정"이라 부르지 않는다**. 명세 §15-B ⑨.

### 왜 이 검사가 필요한가 (A5, 사용자 확정 공리)
이 툴에는 이름이 비슷한 세 가지가 있다: **게임의 설정 파일**(원본) · **프로필**(우리가 저장한
사본) · **메뉴 「설정」**(플러그인 전역 설정). 확인창은 되돌리기 어려운 동작 직전에 뜨는 화면이라,
여기서 셋을 뭉뜽그리면 사용자는 *"무엇이 덮어써지는지"*를 틀리게 읽는다.
→ A5: **"설정"은 메뉴명과 게임 원본 파일에만 쓴다.** 프로필 내용은 "프로필"·"내용"이라 부른다.
→ A6: **"미완/미완성"은 전면 금지**(프로필 없음은 정상 상태다 — 재촉하지 않는다).

### 왜 JSON 값을 보는가
프로브의 `t()` 목은 **키를 그대로 돌려준다**(그래야 렌더 대조가 언어에 안 묶인다) — 그래서
프로브로는 값에 무엇이 적혀 있는지 **원리적으로 못 본다.** 값의 규율은 값이 사는 곳에서 잰다.

### 검사 대상 — 확인창 키군을 **고정**한다
`APPLY_ALL_*` · `SAVE_*` · `RESTORE_*` · `DELETE_*` · `RESET_*`. 접두 고정이라 P13에서 이 군에
문구를 **새로 추가해도 자동으로 검사에 들어온다**(등재를 잊어 검사를 우회하는 구조를 만들지 않는다).
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
I18N = ROOT / "src" / "i18n"

#: 확인창 키군(접두). 새 키는 자동 포섭된다.
GROUPS = ("APPLY_ALL_", "SAVE_", "RESTORE_", "DELETE_", "RESET_")

#: §10-A가 **최종값으로 고정**한 문구(Codex D-09). 이 게이트의 기준점이라 값까지 잠근다 —
#: 여기가 흔들리면 "무엇을 기준으로 금칙을 재는가"가 같이 흔들린다.
FIXED_VALUES = {
    "SAVE_CONFIRM_BODY": {
        "ko": "이 프로필에 저장돼 있던 이전 내용을 덮어씁니다.",
        "en": "This overwrites what was previously saved in this profile.",
    },
}

#: **파일을 가리키는 용법은 허용**된다(A5가 명시한 예외). 이 조각을 지운 뒤 남는 "설정"만 본다.
ALLOWED_PHRASES = {
    "ko": ("설정 파일",),
    # 영어는 단수·복수 둘 다 실사용 중이다("settings file" / "settings files").
    "en": ("settings file", "config file"),
}

#: 메뉴명 그 자체(값 전체가 메뉴 이름인 키)는 A5가 허용하는 유일한 단독 사용이다.
MENU_VALUES = {"설정", "Settings"}

#: ★ 키별 예외 — **근거 없이 늘리지 말 것.** 여기 이름을 올리는 것은 "이 문구의 A5 판정은
#:   검사 밖"이라는 선언이다.
EXEMPT = {
    # "복원 전 현재 설정도 백업으로 보관합니다" — 여기서 '설정'은 **게임 원본 파일의 현재 내용**
    # 이고(프로필이 아니다) A5가 허용하는 용법이다. 다만 뒤에 "파일"이 붙지 않아 기계적으로는
    # 구별되지 않는다. 문구 자체를 "게임 설정 파일"로 바꾸는 것은 §5-C 개정(P13)의 몫이라,
    # 그때 이 예외를 지우고 규칙으로 흡수한다.
    "RESTORE_CONFIRM_BACKUP",
}

#: 금칙 — A6("미완/미완성" 전면 제거). 영어는 그 대응어.
FORBIDDEN = {"ko": ("미완",), "en": ("incomplete",)}


def scrub(value, lang):
    """허용 용법을 지운 잔여 문자열. 남은 자리의 "설정"이 곧 프로필을 가리키는 용법이다."""
    out = value
    for phrase in ALLOWED_PHRASES[lang]:
        out = re.sub(re.escape(phrase) + r"s?", " ", out, flags=re.IGNORECASE)
    return out


def main():
    problems = []
    tables = {}
    for lang in ("ko", "en"):
        path = I18N / f"{lang}.json"
        if not path.is_file():
            print(f"FAIL: {path} 없음")
            return 1
        tables[lang] = json.loads(path.read_text(encoding="utf-8"))

    # ── 고정값 대조 ──────────────────────────────────────────────────────────
    for key, values in FIXED_VALUES.items():
        for lang, expected in values.items():
            actual = tables[lang].get(key)
            if actual != expected:
                problems.append(
                    f"★{key}({lang})가 §10-A 확정값이 아니다\n"
                    f"      기대: {expected}\n      실제: {actual}")

    # ── 금칙 검사 ────────────────────────────────────────────────────────────
    checked = 0
    for lang in ("ko", "en"):
        for key, value in tables[lang].items():
            if not key.startswith(GROUPS):
                continue
            checked += 1
            if key in EXEMPT or value in MENU_VALUES:
                continue
            for word in FORBIDDEN[lang]:
                if word in value.lower() if lang == "en" else word in value:
                    problems.append(
                        f"★{key}({lang})에 금칙어 '{word}' — A6: 프로필 없음은 정상 상태이고 "
                        f"재촉하지 않는다\n      {value}")
            rest = scrub(value, lang)
            if lang == "ko" and "설정" in rest:
                problems.append(
                    f"★{key}(ko)의 '설정'이 파일을 가리키지 않는다 — 프로필을 '설정'이라 부르면 "
                    f"확인창이 무엇을 덮어쓰는지 흐려진다(A5)\n      {value}")
            if lang == "en" and re.search(r"\bsettings\b", rest, re.IGNORECASE):
                problems.append(
                    f"★{key}(en)의 'settings'가 파일을 가리키지 않는다 (A5)\n      {value}")

    if checked < 2 * len(GROUPS):
        problems.append(f"검사 대상이 {checked}개뿐이다 — 키군 접두가 실물과 어긋나 "
                        f"**아무것도 안 재고** 통과할 뻔했다")

    print(f"A5·A6 문구 게이트 — 확인창 키군 {GROUPS} · 검사 {checked}건(ko+en) · "
          f"예외 {sorted(EXEMPT) or '없음'}")
    print(f"  고정값 대조: {sorted(FIXED_VALUES)}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
