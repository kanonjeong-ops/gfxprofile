#!/usr/bin/env python3
"""§10-E 치환자 조사 게이트 — `{치환자}` 뒤에 이형태 조사의 단독형을 못 붙이게 한다 (10판 신설).

### 왜 이 검사가 생겼나 — 화면이 "내장로"라고 말했다
실기에서 `APPLY_SUMMARY`가 **"내장로 전환"**을 그렸다(D5). 원문은 `"{profile}로 전환"`이고,
`{profile}`에는 표시명이 들어간다 — "eGPU"면 "eGPU로"가 맞지만 "내장"이면 "내장으로"라야 한다.
한국어의 이/가·을/를·은/는·와/과·로/으로는 **앞 글자의 받침에 따라 형태가 갈리는데**,
치환자 자리의 값은 실행 시에야 정해진다. 그래서 어느 쪽을 골라 적어도 **언젠가는 틀린다.**

이건 오타가 아니라 **구조 결함**이다: 표시명은 사용자가 바꿀 수 있고(F11) 게임 이름은 임의
문자열이다. 그 자리를 사람 눈으로 지키는 한 다음 문구에서 또 샌다 — 실제로 개정 초안 1판의
**손 전수 점검이 `RESET_CONFIRM_TYPE`을 놓쳤고**, 그 사실이 이 기계 게이트가 필요한 이유다.

### 왜 받침 판정 코드를 넣지 않았나
"마지막 글자의 종성을 보고 조사를 고르는" 함수는 기각됐다(§10-E). 표시명은 라틴 문자·숫자·
기호로 끝날 수 있고 그때는 판정 자체가 성립하지 않는다. 그건 *"그 예외가 생기지 않는 구조"*가
아니라 **예외 처리의 증식**이다. 문형을 바꿔 조사를 안 쓰는 쪽이 싸고 확실하다.

### 판정 — §10-E 허용 3형
치환자 `}` **바로 뒤**만 본다.
- ⓐ **불변 조사**(에·의·도·만·까지·부터·마다 …) — 이형태가 없어 어떤 이름에도 안 틀린다.
  아래 `VARIANTS`에 없으므로 **자동 허용**이다(허용 목록을 따로 두지 않는다).
- ⓑ **병기형**(`을(를)`류) — `{name}` 계열의 기존 관례라 유지한다. `PAIRED`가 인정한다.
- ⓒ **불변 명사 경유**(`{profile} 프로필을 …` — 조사가 '프로필'에 붙는다) — 권장 정본 문형.
  `}` 뒤가 공백이라 애초에 매치되지 않는다.
괄호·홑낫표가 치환자를 격리한 자리(`「{name}」의`·`({dock}/{internal})을`)는 조사가 치환자에
붙은 것이 아니므로 대상 밖이고, `}`가 인접하지 않아 구조적으로도 안 걸린다.

★ **판정 순서가 구조다**: 허용형(ⓑ)을 **먼저** 인정하고 **남은 것만** 이형태 단독형으로 본다.
  거꾸로 짜면 `(으)로`처럼 여는 괄호가 앞에 오는 병기형이 이형태 검사에 먼저 걸려 오탐이 된다
  (초안 2판 지적 3 — 홑낫표 없는 `{x}(으)로`가 생기는 날 터질 명세 구멍이었다). **오탐도 거짓
  검사다** — 다음 사람이 검사를 꺼 버린다.

### 예외 목록을 두지 않는다
기대 위반 수는 **0**이다. 걸리는 문구가 생기면 예외로 등록하지 말고 §10-E 3형 중 하나로 고친다
(§15-B ⑨ "키 예외 0"의 문법). `RESET_CONFIRM_TYPE`도 예외가 아니라 **개정**으로 처분했다 —
`{word}`가 비번역 고정 상수("delete")라 오독 위험이 실질적으로 없었지만, 게이트에 무예외
원칙을 세운 이상 그 자신이 예외가 되면 원칙이 자기모순에 빠진다.

### 음성 대조군 (이 검사가 살아 있는지 확인하는 법)
`src/i18n/ko.json`의 `APPLY_SUMMARY`를 옛 값 **`"{profile}로 전환 — 전체 {total}개 중
{applied}개 변경"`** 으로 되돌리면 이 검사는 **반드시 FAIL**한다(`}로`). 신설 시점에 현행
4건(`APPLY_SUMMARY` 1 · `SAVE_GUIDE` 2 · `RESET_CONFIRM_TYPE` 1)을 실제로 잡는 것을 확인한 뒤
값을 반영했다 — 잡히지 않는 검사를 먼저 통과시켜 두면 그 초록불은 아무 뜻이 없다.

**12판 — 표본이 옮겨졌다**: `SAVE_GUIDE`가 `SAVE_GUIDE_DOCK`/`SAVE_GUIDE_INTERNAL` 2키로
갈라지면서 위 스모크 기록의 "`SAVE_GUIDE` 2"는 **`SAVE_GUIDE_DOCK` 1 · `SAVE_GUIDE_INTERNAL` 1**이
된다(잡던 자리의 수는 같다). 대체 음성 대조군: **`SAVE_GUIDE_DOCK`의 `{dock}용`을 `{dock}를`로
되돌리면 이 검사는 반드시 FAIL한다**(`}를`). 신 문형이 쓰는 "용"은 이형태가 없는 불변 접미라
§10-E ⓐ로 자동 허용되고, 되돌린 "를"은 표시명 받침에 따라 갈리는 이형태 단독형이다 —
기본 표시명("eGPU"·"내장")에서는 우연히 맞아 실기에서 안 드러나고 사용자가 이름을 바꾸는 날
틀리는, 이 게이트가 존재하는 바로 그 형태의 잠복 결함이다.

### 언어
**ko만 본다.** en에는 이 문법 문제가 없고, 없는 문제를 검사하면 다음에 en 문구를 고칠 때
검사가 이유 없이 길을 막는다.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KO = ROOT / "src" / "i18n" / "ko.json"

SPEC = "DESIGN-UX-2026-08-11.md §10-E"

#: ⓑ 병기형 — 이형태 둘을 함께 적어 어느 이름에도 거짓이 아닌 형태. **먼저** 인정한다.
#:   `(으)로`는 여는 괄호가 앞에 오므로 다른 넷과 모양이 다르다 — 그래서 순서가 중요하다.
PAIRED = ("을(를)", "이(가)", "은(는)", "와(과)", "(으)로")

#: 금지 대상 — 앞 글자의 받침으로 형태가 갈리는 조사의 **단독형**.
#:   긴 것을 먼저 둔다("으로"를 "로"보다 앞에): 짧은 쪽이 먼저 맞으면 보고 문구가 어긋난다.
VARIANTS = ("으로", "로", "이", "가", "을", "를", "은", "는", "와", "과")


def violations(text):
    """한 문구에서 `}` 직후의 이형태 단독 조사를 전부 찾는다. 반환 = [(위치, 조사, 발췌)]."""
    out = []
    start = 0
    while True:
        i = text.find("}", start)
        if i < 0:
            return out
        start = i + 1
        tail = text[start:]
        # ★ 허용형이 먼저다 — 병기형이면 이형태 검사에 넘기지 않는다(위 "판정 순서가 구조다").
        if any(tail.startswith(p) for p in PAIRED):
            continue
        for particle in VARIANTS:
            if tail.startswith(particle):
                out.append((i, particle, text[max(0, i - 14):start + len(particle) + 6]))
                break


#: **탐지기 자가 시험 표본** — (문구, 위반이어야 하는가).
#:
#: ★★ 왜 필요한가(이종 QA 적발): 이 파일의 음성 대조군은 **주석 설명뿐**이었다. 그래서
#:   `violations()`가 어떤 이유로든 빈 배열만 돌려주게 망가지면 — 정규식 오타든, 허용 검사가
#:   전부를 삼키든 — ko.json 위반 0건과 **구별되지 않는다.** 둘 다 "PASS"로 보인다.
#:   실물 데이터가 깨끗한 검사일수록 이 함정이 크다: 잡을 것이 없으니 잡는 능력이 죽어도 모른다.
#: ★ 그래서 매 실행마다 **알려진 답이 있는 표본**에 탐지기를 걸어 본다. 하나라도 어긋나면
#:   ko.json 판정으로 넘어가지 않고 *"탐지기가 무효다"*로 죽는다 — 판정 불가는 통과가 아니다.
SELF_TEST = [
    # 금지형(ⓐ 밖) — 이형태 단독 조사가 치환자에 바로 붙었다
    ("{x}로 전환", True),
    ("{x}으로 간다", True),
    ("{x}을 적용", True),
    ("{x}를 적용", True),
    ("{x}이 있다", True),
    ("{x}가 있다", True),
    ("{x}은 그렇다", True),
    ("{x}는 그렇다", True),
    ("{x}와 함께", True),
    ("{x}과 함께", True),
    # ⓑ 병기형 — 허용(다섯 쌍 전부, `(으)로`는 여는 괄호가 앞에 오는 모양이라 특히 중요하다)
    ("{x}을(를) 적용", False),
    ("{x}이(가) 있다", False),
    ("{x}은(는) 그렇다", False),
    ("{x}와(과) 함께", False),
    ("{x}(으)로 간다", False),
    # ⓐ 불변 조사 — 이형태가 없어 어떤 이름에도 안 틀린다
    ("{x}에 저장", False),
    ("{x}의 이름", False),
    ("{x}도 같다", False),
    ("{x}만 남는다", False),
    # ⓒ 불변 명사 경유(권장 정본 문형) · 격리된 자리
    ("{x} 프로필을 적용", False),
    ("「{x}」의 등록", False),
    ("프로필({a}/{b})을 고른다", False),
]


def self_test():
    """탐지기가 살아 있는지 먼저 잰다. 문제 목록을 돌려준다(비어 있어야 한다)."""
    bad = []
    for text, want_hit in SELF_TEST:
        hit = bool(violations(text))
        if hit != want_hit:
            bad.append(f"{text!r} — {'잡아야 하는데 놓쳤다' if want_hit else '허용형인데 잡았다'}")
    return bad


def main():
    if not KO.is_file():
        print(f"FAIL: {KO} 없음")
        return 1

    broken = self_test()
    if broken:
        print(f"§10-E 치환자 조사 게이트 — 자가 시험 {len(SELF_TEST)}표본")
        print(f"\nFAIL — **탐지기가 무효다**({len(broken)}건). ko.json 판정으로 넘어가지 않는다: "
              f"잡는 능력이 죽은 검사의 '위반 0건'은 아무 뜻이 없다")
        for b in broken:
            print("  ★" + b)
        return 1

    table = json.loads(KO.read_text(encoding="utf-8"))

    problems = []
    scanned = 0
    for key, value in table.items():
        if not isinstance(value, str):
            continue
        scanned += 1
        for _, particle, excerpt in violations(value):
            problems.append(
                f"★{key} — 치환자 바로 뒤에 이형태 조사 {particle!r}가 단독으로 붙었다\n"
                f"      …{excerpt}…\n"
                f"      고치는 법({SPEC}): ⓐ 불변 조사(에·의·도·만…)로 바꾸거나 "
                f"ⓑ 병기형({'·'.join(PAIRED)})으로 적거나 "
                f"ⓒ 불변 명사를 경유한다(\"{{x}} 프로필을 …\" ← 권장)")

    # ★ 훑은 문구가 0개면 그건 통과가 아니라 **판정 불가**다(파일 형식이 바뀌었나?).
    #   0건을 초록불로 돌려주는 검사는 그 순간부터 거짓말을 시작한다.
    if scanned == 0:
        print("FAIL: ko.json에서 문자열 문구를 하나도 읽지 못했다 — 판정 불가는 통과가 아니다")
        return 1

    print(f"§10-E 치환자 조사 게이트 — 자가 시험 {len(SELF_TEST)}표본 통과 · "
          f"ko {scanned}개 문구 검사 · "
          f"금지 {len(VARIANTS)}종 / 병기 허용 {len(PAIRED)}종 (위반 0이어야 한다)")
    if problems:
        print(f"\nFAIL — 위반 {len(problems)}건")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
