#!/usr/bin/env python3
"""에러 코드 불변식 — 모든 거부에 `code=codes.X`가 붙어 있고, 쓰인 코드가 전부 codes.py에
정의돼 있는가(부분 집합 검사다).

주장의 범위: 이 파일은 양방향 집합 항등을 강제하지 않는다. `codes.py`에 있지만 아무도 안 쓰는
  코드는 아래에서 참고 출력으로 끝난다(실패가 아니다). 그것이 맞다 — `BACKUP_ID_INVALID` 같은
  예비 코드를 남긴다는 결정이 먼저 있고, 미사용을 실패로 만들면 그 결정과 정면으로 부딪친다.
  번역 키(en/ko json)와 맞대는 검사는 저장소에 없다 — `qa/test_i18n_keys.py`가 보는 것은
  en과 ko 사이의 키 집합 항등뿐이고 `codes`를 import조차 하지 않는다. 네 집합이 어딘가에서
  맞춰진다고 읽지 마라.

왜 개수가 아니라 집합인가: 개수를 완료 기준으로 삼으면 가드를 하나 늘릴 때마다 기준이 통째로
깨진다. 집합 기준은 코드가 늘거나 줄어도 안 깨진다.

이 테스트가 있어야 raise에 code를 다는 작업을 기계적으로 해도 안전하다.
검사 대상: `py_modules/gfxp/*.py` 전량(아래 `SKIP` 명시 제외분만 뺀다) + 접착층 `main.py`의
`raise Refused(...)` / `raise RegistryError(...)`
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes  # noqa: E402

TARGETS = {"Refused", "RegistryError"}

#: 스캔에서 뺄 파일 — 근거 주석 없이 늘리지 말 것. 지금은 비어 있다(전 파일 통과 확인).
#: 여기에 이름을 올리는 것은 "이 파일의 `code=` 규율은 검사 밖"이라는 선언이다.
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

    # 스캔 대상은 glob + 명시 제외다.
    #   손으로 유지하는 파일 목록이면 새 정책 파일(`exclude.py` 같은)을 만들 때마다 등재를
    #   기억해야 하고, 잊은 파일이 조용히 검사를 우회한다. 등재를 잊는 예외를 처리하는 대신,
    #   그 예외가 생기지 않는 구조로 간다: 폴더 전량을 훑고, 빠지는 것만 근거와 함께 아래에 적는다.
    #   `labels.py`·`exclude.py`처럼 오늘 `raise`가 0건인 파일도 대상이다. 그래야 그중 하나에
    #     첫 `raise`가 생기는 날 자동으로 걸린다 — `confirm.py`가 그 경우다(지금은 한 건 있다).
    #   접착층 `main.py`도 대상이다. 거부를 던지는 곳이 엔진뿐이라는 전제는 이미 깨져 있고
    #     (`BAD_IDENTIFIER`·`UNEXPECTED`), `REGISTRY_NEWER`는 아예 `main.py`에만 산다 —
    #     여기가 안 보면 그 코드는 어떤 검사도 지나지 않는다.
    targets = sorted((ROOT / "py_modules" / "gfxp").glob("*.py")) + [ROOT / "main.py"]
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
    # (en/ko json 대조는 `qa/test_i18n_keys.py`가 en과 ko 사이에서만 한다. 여기서 또 만들면
    #  같은 불변식이 두 곳에서 갈라진다.)
    # 이 집합은 지금 합격/불합격에 관여하지 않는다 — 늘리기 전에 읽을 것:
    #   ① 쓰임은 바로 아래 `unused` 한 줄뿐이고 그 결과는 `problems`에 안 들어간다 — print만 한다.
    #   ② `targets`가 `main.py`를 포함하므로 접착층 전용 코드도 어차피 `used`에 잡힌다.
    #      → 그래서 `PROFILE_META_CORRUPT`·`PROFILE_WRITE_FAILED`·`UNEXPECTED` 셋은 이미
    #        무효항이다(있으나 없으나 출력이 같다). 목록을 실제로 지탱하는 것은 나머지 넷뿐이다.
    #   목록의 선언적 의도("엔진에서 안 쓰는 것이 정상인 코드")는 살아 있어 유지하되,
    #   무효한 목록을 말없이 키우면 다음 사람이 그것을 유효한 가드로 읽는다.
    #   가드로 만들려면 `unused`를 실패로 올려야 하는데, 그건 "예비 코드를 남긴다"는 기존 결정과
    #   정면으로 부딪친다 — 위 독스트링이 그 범위를 이미 적어 두었다.
    glue_only = {codes.BACKUP_ID_INVALID, codes.PROFILE_META_CORRUPT,
                 codes.PROFILE_WRITE_FAILED,
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
