#!/usr/bin/env python3
"""언어 판정 — VDF 워커의 정확 일치를 잠근다.

경로 튜플이 실물 최상위 키(`Registry`)를 빠뜨리면 워커는 늘 None을 내고, 그러면 폴백이 영어를
띄워 고장이 조용히 숨는다. 값만 보는 완료 기준("영어면 통과")으로는 그 상태를 잡을 수 없다.
그래서 이 테스트는 값뿐 아니라 어느 단계가 이겼는지(source)를 함께 본다.

폴백은 사슬 전체가 아니라 한 성질만 잰다 — registry가 없으면 source가 `steam-registry`가
아니어야 하고 값이 `lang.SUPPORTED` 안이어야 한다. `LANGUAGE`→`LANG`→locale→`("en","default")`
라는 순서 자체를 잠그는 검사는 여기 없다.

픽스처 (a)는 실물 `registry.vdf`를 직접 읽는다. 설계는 "실물을 복사해 픽스처로 만들라"고
  했으나, 그 파일에는 계정 정보가 섞여 있고 이 프로젝트는 배포물이다. 직접 읽으면 "발췌를
  손으로 재작성해 버그가 통과하는" 위험은 똑같이 막으면서 개인 데이터를 넣지 않는다.
  실물이 없으면 건너뛰는 것은 (a)뿐이다 — 파일 끝의 실환경 `detect()` 절은 그대로 돌아
  FAIL한다. 즉 이 파일은 HOME의 registry.vdf 후보에서 유효한 언어 값을 읽을 수 있는
  환경에서만 통과한다.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import lang  # noqa: E402

# 참조 구현이 틀리는 케이스: 형제 키 Steamsteamglobal이 먼저 나오고 값도 다르다
FIX_B = '''
"Registry" { "HKCU" { "Software" { "Valve" {
  "Steamsteamglobal" { "language" "english" }
  "Steam" { "language" "koreana" }
} } }
"HKLM" { "Software" { "Valve" { "Steam" { "language" "tchinese" } } } } }
'''
FIX_C = '"Registry" { "HKCU" { "Software" { "Valve" { "Other" { "x" "1" } } } } }'
FIX_D = '"Registry" { "HKCU" { "Software" { "Valve" { "Steam" { "language" "koreana"'
FIX_E = '"Registry" { "HKLM" { "Software" { "Valve" { "Steam" { "language" "koreana" } } } } }'
FIX_G = '} } } } } } } }' + '"Registry" { "HKCU" { "Software" { "Valve" { "Steam" { "language" "koreana" } } } } }'
ANY = object()

FIX_F = '"HKCU" { "Software" { "Valve" { "Steam" { "language" "koreana" } } } }'

CASES = [
    ("(b) 형제 Steamsteamglobal + HKLM 경쟁값", FIX_B, "koreana",
     "Registry/HKCU/Software/Valve/Steam/language"),
    ("(c) Steam 섹션 없음", FIX_C, None, None),
    # (d)(g) malformed — 값이 무엇이든 예외가 밖으로 나오지 않는 것이 요건이다.
    #   "malformed면 언제나 폴백한다"까지는 요구하지 않는다: 깨진 지점보다 앞에 값이 있으면
    #   정상적으로 찾는 것이 맞다. expect를 ANY로 두고 예외만 잡는다.
    ("(d) 닫는 중괄호 부족", FIX_D, ANY, ANY),
    ("(g) 여분의 닫는 중괄호 — IndexError가 났던 케이스", FIX_G, ANY, ANY),
    ("(e) HKLM에만 language — 집지 않는다", FIX_E, None, None),
    ("(f) Registry 래퍼 없음 — 둘째 경로가 받는다", FIX_F, "koreana",
     "HKCU/Software/Valve/Steam/language"),
]


def main():
    problems = []

    # (a) 실물
    real = pathlib.Path.home() / ".steam" / "registry.vdf"
    if real.exists():
        text = real.read_text(encoding="utf-8", errors="replace")
        value, where = lang.steam_language(text)
        print(f"  (a) 실물 registry.vdf → {value!r} @ {where}")
        if not value:
            problems.append("(a) 실물에서 언어 값을 못 읽었다 — 실물 경로 판정 실패(손상·스키마 변화·파서 회귀 포함)")
        elif not where.startswith("Registry/"):
            problems.append(f"(a) 실물 최상위 키가 Registry가 아니다: {where}")
        # 래퍼 없는 경로는 실물에서 None이어야 한다 — 값이 나오면 이 대조의 전제가 무너진다
        if lang._walk(text, ("HKCU", "Software", "Valve", "Steam", "language")):
            problems.append("(a) 래퍼 없는 경로가 실물에서 값을 냈다 — 이 테스트의 전제가 틀렸다")
    else:
        print("  (a) 실물 registry.vdf 없음 — 건너뜀 (이 환경에서는 미검증)")

    for label, text, expect_v, expect_w in CASES:
        try:
            value, where = lang.steam_language(text)
        except Exception as exc:                      # noqa: BLE001 — 예외 자체가 실패다
            problems.append(f"{label}: 예외가 밖으로 나왔다 — {exc!r}")
            continue
        if expect_v is ANY:
            continue
        if value != expect_v or (expect_w and where != expect_w):
            problems.append(f"{label}: 기대 ({expect_v}, {expect_w}) / 실제 ({value}, {where})")

    # 폴백 — registry가 없으면 source가 steam-registry 밖으로 내려가고 값이 지원 언어인지 본다
    l1, s1 = lang.detect(home="/nonexistent-home-for-test")
    if s1 == "steam-registry" or s1.startswith("steam-registry:"):
        problems.append(f"폴백: registry가 없는데 source가 steam-registry다 ({s1})")
    if l1 not in lang.SUPPORTED:
        problems.append(f"폴백: 지원하지 않는 언어를 냈다 ({l1})")
    print(f"  폴백 사슬(registry 없음) → {l1!r} @ {s1}")

    # 실환경 detect — 폴백이 아니라 registry가 이겨야 한다(폴백이 이기면 고장이 여기서 숨는다)
    l2, s2 = lang.detect()
    print(f"  실환경 detect() → {l2!r} @ {s2}")
    if not s2.startswith("steam-registry:"):
        problems.append(f"실환경에서 source가 steam-registry가 아니다 ({s2}) — 판정 실패로 본다")

    print(f"케이스 {len(CASES)}종 + 실물 + 폴백")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
