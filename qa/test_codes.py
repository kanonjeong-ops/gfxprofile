#!/usr/bin/env python3
"""에러 코드 불변식 — 모든 거부에 code가 붙어 있고, 그 집합이 codes.py와 일치하는가.

왜 개수가 아니라 집합인가: M1 설계가 "18개"라는 **개수**를 완료 기준으로 삼았다가,
가드를 둘 늘리자 기준이 통째로 깨졌다(설계 E2). 집합 항등은 코드가 늘거나 줄어도 안 깨진다.

이 테스트가 있어야 raise에 code를 다는 작업을 기계적으로 해도 안전하다.
검사 대상: py_modules/gfxp/{engine,store,remove,restore,confirm,labels}.py 의 `raise Refused(...)` / `raise RegistryError(...)`
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes  # noqa: E402

TARGETS = {"Refused", "RegistryError"}


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

    # ★ `remove.py`를 여기 넣지 않으면 그 파일의 `code=` 규율은 **검사 밖**이다
    #   (DESIGN-DELETE 반증 채택 2 — "test_codes가 자동으로 잠근다"는 허구였다).
    #   스캔 대상은 손으로 유지하는 목록이라 새 정책 파일을 만들 때마다 여기에 등재해야 한다.
    #   ⚠️ `confirm.py`·`labels.py`는 **오늘은 `raise`가 0건이라 아무것도 안 잠근다**(2026-08-10
    #     qa-lead 지적). 그래도 등재하는 이유는 대칭이다 — fence 밖 정책 파일 다섯이 같은 규율
    #     아래 있어야, 그중 하나에 첫 `raise`가 생기는 날 **자동으로** 검사에 걸린다.
    for fname in ("engine.py", "store.py", "remove.py", "restore.py",
                  "confirm.py", "labels.py"):
        path = ROOT / "py_modules" / "gfxp" / fname
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

    print(f"검사한 raise: {total}개 / 사용된 코드: {len(used)}종 / codes.py 정의: {len(known)}종")

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
