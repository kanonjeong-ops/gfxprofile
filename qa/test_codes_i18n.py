#!/usr/bin/env python3
"""codes ↔ 번역 전수 대조 — 백엔드 상수가 en/ko 양쪽에 등재됐는가 (F7-1).

데이터·계약 검사다(화면을 재지 않는다). `i18n.tCode`는 `code in en`이면 그 값을 그대로 그리고,
아니면 폴백(`{code}`)으로 내려간다. 그래서 `codes.py`가 던지는 코드가 en/ko에 없으면 화면에
코드 이름이 그대로 뜬다 — 그 등재를 이 검사가 잠근다(F1-c·F2a 신설 2코드 포함).

잰다: `codes.all_codes()` ⊆ en.json 키 ∧ ⊆ ko.json 키 ∧ en 키 == ko 키.
못 잰다: 문구가 옳은지(이 문서·리뷰 몫) · 화면 전용 i18n 키의 존재(TypeScript `StringKey`와
  `qa/test_i18n_keys.py`의 결합 몫) · `confirm`의 disk_state 분류값(codes 상수가 아니라 범위 밖).
왜 `qa/test_i18n_keys.py`에 안 얹나: 그 본은 ko↔en 항등·빈 값 부재만 보는 i18n 내부 검사이고,
  이쪽은 파이썬 상수와 프론트 자원의 대조다 — 재는 대상이 다르면 본을 가른다(R14 처분).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes  # noqa: E402

I18N = ROOT / "src" / "i18n"


def main():
    tables = {name: json.loads((I18N / f"{name}.json").read_text(encoding="utf-8"))
              for name in ("en", "ko")}
    all_codes = codes.all_codes()
    problems = []

    for name in ("en", "ko"):
        missing = sorted(c for c in all_codes if c not in tables[name])
        if missing:
            problems.append(f"{name}.json에 없는 codes 상수 {len(missing)}종 — {missing}")

    only_en = sorted(set(tables["en"]) - set(tables["ko"]))
    only_ko = sorted(set(tables["ko"]) - set(tables["en"]))
    if only_en or only_ko:
        problems.append(f"en·ko 키 집합이 다르다 — en에만 {only_en} / ko에만 {only_ko}")

    print(f"codes↔번역 대조 — codes 상수 {len(all_codes)}종 ⊆ en ∧ ⊆ ko · en·ko 항등")
    for p in problems:
        print("  " + p)
    print("FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
