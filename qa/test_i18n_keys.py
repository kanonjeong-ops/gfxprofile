#!/usr/bin/env python3
"""ko/en **키 집합 항등**과 빈 값 부재만 본다 — 데이터 계약 검사다(화면을 재지 않는다).

키가 한쪽에만 있으면 그 언어에서 `t()`가 **키 문자열 자체**를 그리고(i18n.ts:141), 빈 값이면
그 자리가 **아무 말도 없이** 비어 버린다. 둘 다 실물 데이터로만 판정된다.
⚠️ 그 이상(참조 0 키·JSX 스캔·문구 고정)은 **만들지 않는다** — 삭제된 UI 검사 계열이다(사용자 지정).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "i18n"


def main():
    tables = {name: json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))
              for name in ("ko", "en")}
    problems = []
    only_ko = sorted(set(tables["ko"]) - set(tables["en"]))
    only_en = sorted(set(tables["en"]) - set(tables["ko"]))
    if only_ko or only_en:
        problems.append(f"키 집합이 다르다 — ko에만 {only_ko} / en에만 {only_en}")
    for name, table in tables.items():
        empty = sorted(k for k, v in table.items() if not isinstance(v, str) or not v.strip())
        if empty:
            problems.append(f"{name}에 빈 값 {len(empty)}건 — {empty[:8]}")
    print(f"i18n 키 {len(tables['ko'])}종 (ko·en 항등 · 빈 값 0)")
    for p in problems:
        print("  " + p)
    print("FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
