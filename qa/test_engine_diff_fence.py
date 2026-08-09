#!/usr/bin/env python3
"""diff fence — v2 엔진이 M1에서 **기록된 diff 말고는 아무것도** 바뀌지 않았음을 강제한다.

M1 엔진은 QA 9라운드를 통과하고 실사용 중인 물건이다. v2는 이식만 하고 정책·가드 로직은
손대지 않는다. 목록 밖의 diff가 생기면 그건 회귀다.

★ [2026-08-05 전면 교체] 이전 구현(AST 비교)은 **거짓 통과했다.**
  리뷰가 무단 변경 5개를 동시에 넣고도 PASS를 받아냈다:
    · `discover._MAX_DEPTH 6→999` (fence 대상 파일이 아니었다)
    · `store.BACKUP_KEEP 10→0`    (모듈 상수를 비교하지 않았다)
    · G14/G15 **호출 삭제**        (호출문을 "허용된 추가"로 벗겨내서, 지워도 티가 안 났다)
    · 거부 코드 `GAME_RUNNING→FILE_EMPTY` (code=를 통째로 벗겨냈다)
  구조가 틀렸다. 허용 목록을 코드로 표현하려 할수록 벗겨낼 것이 늘고, 벗겨낸 만큼 눈이 먼다.

  그래서 **허용 diff를 파일 하나로 고정한다**(`qa/engine_allowed.diff`).
  테스트는 M1→v2의 실제 diff를 그 자리에서 만들어 기록본과 **한 글자까지 대조**한다.
    · 무단 변경은 diff를 바꾸므로 무조건 걸린다. 벗겨내는 것이 없으니 사각지대도 없다.
    · 의도한 변경은 `--update`로 기록본을 갱신하고 **그 diff를 리뷰받는다** —
      허용 목록이 곧 사람이 읽는 문서가 된다.
  `discover.py`·`detect.py`는 애초에 손대지 않기로 했으므로 **바이트 동일**을 요구한다.
"""
import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
V2 = ROOT / "py_modules" / "gfxp"
M1 = pathlib.Path("/home/deck/scripts/gfxprofile/gfxp")
ALLOWED = ROOT / "qa" / "engine_allowed.diff"

PATCHED = ("engine.py", "store.py")      # 기록된 diff만 허용
IDENTICAL = ("discover.py", "detect.py", "__init__.py")   # 바이트 동일이어야 함


def current_diff():
    out = []
    for name in PATCHED:
        a = (M1 / name).read_text().splitlines(keepends=True)
        b = (V2 / name).read_text().splitlines(keepends=True)
        out.extend(difflib.unified_diff(a, b, fromfile=f"M1/{name}", tofile=f"v2/{name}", n=3))
    return "".join(out)


def main():
    if not M1.is_dir():
        # ★ 기준이 없으면 **실패다** (2026-08-05 QA R7). 예전엔 SKIP 후 0을 돌려줬는데,
        #   그러면 M1 경로가 옮겨지거나 마운트가 빠진 순간 **엔진을 한 줄도 대조하지 않고
        #   전체 테스트 루프가 성공**한다. fence가 지키는 것이 "엔진이 안 바뀌었다"인데,
        #   비교를 못 한 것과 비교해서 같은 것은 정반대의 결론이다.
        #   검사는 판정할 수 없을 때 통과가 아니라 **거부**해야 한다.
        print(f"FAIL — 기준이 되는 M1 원본이 없다: {M1}")
        print("       (경로가 바뀌었으면 이 테스트의 M1 상수를 고칠 것. 건너뛰면 안 된다)")
        return 1

    problems = []
    for name in IDENTICAL:
        if (M1 / name).read_bytes() != (V2 / name).read_bytes():
            problems.append(f"{name}: M1과 바이트가 다르다 (이 파일은 손대지 않기로 했다)")

    diff = current_diff()
    if "--update" in sys.argv:
        ALLOWED.write_text(diff)
        print(f"기록본 갱신: {ALLOWED} ({len(diff.splitlines())}행)")
        print("★ 이 diff를 사람이 읽고 승인해야 한다. 허용 목록은 이 파일이 전부다.")
        return 0

    if not ALLOWED.exists():
        print(f"FAIL — 허용 diff 기록본이 없다: {ALLOWED}\n  최초 1회 `--update`로 만들고 리뷰받아라")
        return 1

    recorded = ALLOWED.read_text()
    if diff != recorded:
        d = list(difflib.unified_diff(recorded.splitlines(), diff.splitlines(),
                                      fromfile="기록된 허용 diff", tofile="지금의 diff", n=1))
        problems.append("engine/store의 diff가 기록본과 다르다 — 아래가 그 차이다:\n"
                        + "\n".join("    " + x for x in d[:40]))

    print(f"바이트 동일 요구: {', '.join(IDENTICAL)}")
    print(f"허용 diff 기록본: {ALLOWED.name} ({len(recorded.splitlines()) if ALLOWED.exists() else 0}행)")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS — 기록된 diff 말고는 M1과 동일하다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
