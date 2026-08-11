#!/usr/bin/env python3
"""에러 코드 불변식 — 모든 거부에 `code=codes.X`가 붙어 있고, **쓰인 코드가 전부 codes.py에
정의돼 있는가**(부분 집합 검사다).

⚠️ 주장의 범위(2026-08-10 최종 QA 표류 4): 이 파일은 **양방향 집합 항등을 강제하지 않는다.**
  `codes.py`에 있지만 아무도 안 쓰는 코드는 아래에서 **참고 출력으로 끝난다**(실패가 아니다).
  그것이 맞다 — `BACKUP_ID_INVALID` 같은 **예비 코드를 남긴다**는 기존 결정이 있고
  (DESIGN-F6-F8 §5-2 세션 확정), 미사용을 실패로 만들면 그 결정과 정면으로 부딪친다.
  나머지 두 집합(en/ko json)과의 대조는 `test_i18n_sets.py` 5항의 소관이다.

왜 개수가 아니라 집합인가: M1 설계가 "18개"라는 **개수**를 완료 기준으로 삼았다가,
가드를 둘 늘리자 기준이 통째로 깨졌다(설계 E2). 집합 기준은 코드가 늘거나 줄어도 안 깨진다.

이 테스트가 있어야 raise에 code를 다는 작업을 기계적으로 해도 안전하다.
검사 대상: **`py_modules/gfxp/*.py` 전량**(아래 `SKIP` 명시 제외분만 뺀다)의
`raise Refused(...)` / `raise RegistryError(...)`
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes  # noqa: E402

TARGETS = {"Refused", "RegistryError"}

#: 스캔에서 뺄 파일 — **근거 주석 없이 늘리지 말 것.** 지금은 비어 있다(전 파일 통과 확인,
#: 2026-08-11 P11). 여기에 이름을 올리는 것은 "이 파일의 `code=` 규율은 검사 밖"이라는 선언이다.
SKIP = frozenset()


def raises_in(path):
    """(행번호, 예외이름, code상수이름 or None) 목록."""
    out = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        f = node.exc.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if name not in TARGETS:
            continue
        const = None
        for kw in node.exc.keywords:
            if kw.arg == "code":
                # code=codes.FOO 만 허용한다. 리터럴 문자열은 단일 소스를 깨뜨린다.
                if isinstance(kw.value, ast.Attribute) and \
                   isinstance(kw.value.value, ast.Name) and kw.value.value.id == "codes":
                    const = kw.value.attr
                else:
                    const = "<非codes 상수>"
        out.append((node.lineno, name, const))
    return out


def main():
    known = codes.all_codes()
    problems = []
    used = set()
    total = 0

    # ★★ 스캔 대상은 **glob + 명시 제외**다 (2026-08-11 P11, Codex D-10).
    #   예전에는 손으로 유지하는 파일 목록이었다. 그 방식은 새 정책 파일(`exclude.py` 같은)을
    #   만들 때마다 등재를 기억해야 하고, **잊은 파일이 조용히 검사를 우회한다** —
    #   `remove.py`가 실제로 그렇게 빠져 있었다(DESIGN-DELETE 반증 채택 2). 등재를 잊는 예외를
    #   처리하는 대신, **그 예외가 생기지 않는 구조**로 바꾼다: 폴더 전량을 훑고, 빠지는 것만
    #   근거와 함께 아래에 적는다.
    #   ⚠️ `confirm.py`·`labels.py`·`exclude.py`처럼 **오늘은 `raise`가 0건인 파일도 대상이다**
    #     (2026-08-10 qa-lead 지적). 그래야 그중 하나에 첫 `raise`가 생기는 날 자동으로 걸린다.
    targets = sorted((ROOT / "py_modules" / "gfxp").glob("*.py"))
    skipped = [p.name for p in targets if p.name in SKIP]
    for path in targets:
        if path.name in SKIP:
            continue
        fname = path.name
        for lineno, exc, const in raises_in(path):
            total += 1
            if const is None:
                problems.append(f"{fname}:{lineno} {exc} — code= 없음")
            elif const == "<非codes 상수>":
                problems.append(f"{fname}:{lineno} {exc} — code가 codes.X 형태가 아님")
            elif not hasattr(codes, const):
                problems.append(f"{fname}:{lineno} {exc} — codes.{const} 가 존재하지 않음")
            else:
                used.add(getattr(codes, const))

    print(f"검사 대상 {len(targets) - len(skipped)}파일(glob, 제외 {skipped or '없음'}) / "
          f"검사한 raise: {total}개 / 사용된 코드: {len(used)}종 / codes.py 정의: {len(known)}종")

    unknown = used - known
    if unknown:
        problems.append(f"codes.py에 없는 코드가 쓰임: {sorted(unknown)}")

    # 접착층 전용·경고 코드는 엔진에서 안 쓰는 것이 정상이므로 미사용을 실패로 보지 않는다.
    # (4집합 항등 중 **en/ko json 대조는 `test_i18n_sets.py` 5항의 소관**이다 — P5에서 그리로
    #  일원화했다. 여기서 또 만들면 같은 불변식이 두 곳에서 갈라진다.)
    glue_only = {codes.BACKUP_ID_INVALID, codes.PROFILE_META_CORRUPT,
                 codes.CONFIRM_REQUIRED, codes.UNEXPECTED,
                 codes.WARN_OUTSIDE_SCAN_ROOTS, codes.WARN_NOT_DISCOVER_CANDIDATE}
    unused = known - used - glue_only
    if unused:
        print(f"  참고: 엔진에서 아직 안 쓰는 코드 {len(unused)}종 — {sorted(unused)}")

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
