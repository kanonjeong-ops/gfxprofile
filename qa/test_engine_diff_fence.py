#!/usr/bin/env python3
"""diff fence — 엔진(`engine.py`·`store.py`)의 변경을 **감지해 사람 승인 앞에 세운다**.

★ [2026-08-19 기준선 교체] 목적을 「M1 불변 증명」에서 **「릴리스 단위 변경 감지 + 명시 승인」**
  으로 재정의했다. 전제가 소멸했기 때문이다 — v2는 "이식만 하고 엔진은 손대지 않는다"로 출발했으나
  엔진은 실제로 승인을 거쳐 여러 차례 갈라졌고 앞으로도 고친다. 기준선이 얼어 있으면 허용 diff가
  **한 방향으로 자라기만 해서**(교체 직전 742행) 언젠가 "엔진을 통째로 다시 썼고 여기 그 기록이
  있다"가 된다. 그 순간 신호는 사라진다.

  → 기준선을 **직전 릴리스 태그**로 옮긴다. 릴리스마다 리셋되므로 허용 diff는 언제나
    *"이번 릴리스에서 엔진이 뭐가 바뀌었나"*만 담고, 그 diff가 CHANGELOG의 재료가 된다.
    · **자립적이다** — 리포만 있으면 돈다(외부 경로 의존 0). 포크한 사람 기기에서도 같다.
    · **최초 태그가 찍히기 전까지는 M1 원본을 기준선으로 쓴다**(부트스트랩). 태그가 생기면
      자동으로 전환되므로 이행 공백이 없다.
  ⚠️ 이 방식의 위험은 `--update`가 반사적으로 눌리는 것이다. 대책은 검사를 하나 더 만드는 것이
  아니라 **사람이 이미 읽는 것에 묶는 것** — `build.sh release`가 누적 엔진 diff를 찍고 그것이
  CHANGELOG에 반영됐는지 확인한다(release 명령 신설과 한 묶음).

★ [2026-08-05 전면 교체] 이전 구현(AST 비교)은 **거짓 통과했다.**
  리뷰가 무단 변경 5개를 동시에 넣고도 PASS를 받아냈다:
    · `discover._MAX_DEPTH 6→999` (fence 대상 파일이 아니었다)
    · `store.BACKUP_KEEP 10→0`    (모듈 상수를 비교하지 않았다)
    · G14/G15 **호출 삭제**        (호출문을 "허용된 추가"로 벗겨내서, 지워도 티가 안 났다)
    · 거부 코드 `GAME_RUNNING→FILE_EMPTY` (code=를 통째로 벗겨냈다)
  구조가 틀렸다. 허용 목록을 코드로 표현하려 할수록 벗겨낼 것이 늘고, 벗겨낸 만큼 눈이 먼다.

  그래서 **허용 diff를 파일 하나로 고정한다**(`qa/engine_allowed.diff`).
  테스트는 기준선→작업본의 실제 diff를 그 자리에서 만들어 기록본과 **한 글자까지 대조**한다.
    · 무단 변경은 diff를 바꾸므로 무조건 걸린다. 벗겨내는 것이 없으니 사각지대도 없다.
    · 의도한 변경은 `--update`로 기록본을 갱신하고 **그 diff를 리뷰받는다** —
      허용 목록이 곧 사람이 읽는 문서가 된다.
  `discover.py`·`detect.py`는 애초에 손대지 않기로 했으므로 **바이트 동일**을 요구한다.
"""
import difflib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
V2 = ROOT / "py_modules" / "gfxp"
#: 부트스트랩 전용. 최초 릴리스 태그가 찍히면 더 쓰지 않는다.
M1 = pathlib.Path("/home/deck/scripts/gfxprofile/gfxp")
ALLOWED = ROOT / "qa" / "engine_allowed.diff"

PATCHED = ("engine.py", "store.py")      # 기록된 diff만 허용
IDENTICAL = ("discover.py", "detect.py", "__init__.py")   # 바이트 동일이어야 함
TAG_MATCH = "v[0-9]*"


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def latest_release_tag():
    r = _git("describe", "--tags", "--abbrev=0", "--match", TAG_MATCH)
    tag = r.stdout.decode().strip()
    return tag if r.returncode == 0 and tag else None


def baseline():
    """(라벨, 이름→bytes 읽기) 를 돌려준다. 기준선을 못 잡으면 None."""
    tag = latest_release_tag()
    if tag:
        def read(name):
            r = _git("show", f"{tag}:py_modules/gfxp/{name}")
            return r.stdout if r.returncode == 0 else None
        return f"직전 릴리스 태그 {tag}", read
    if M1.is_dir():
        def read(name):
            p = M1 / name
            return p.read_bytes() if p.is_file() else None
        return f"M1 원본 {M1} (부트스트랩 — 최초 릴리스 태그 전까지)", read
    return None


def current_diff(read):
    out = []
    for name in PATCHED:
        base = read(name)
        if base is None:
            continue
        a = base.decode().splitlines(keepends=True)
        b = (V2 / name).read_text().splitlines(keepends=True)
        out.extend(difflib.unified_diff(a, b, fromfile=f"기준선/{name}", tofile=f"작업본/{name}", n=3))
    return "".join(out)


def main():
    base = baseline()
    if base is None:
        # ★ 기준이 없으면 **실패다** (2026-08-05 QA R7). 예전엔 SKIP 후 0을 돌려줬는데,
        #   그러면 기준선이 사라진 순간 **엔진을 한 줄도 대조하지 않고 전체 테스트 루프가 성공**한다.
        #   검사는 판정할 수 없을 때 통과가 아니라 **거부**해야 한다.
        print("FAIL — 기준선을 잡을 수 없다: 릴리스 태그도 없고 부트스트랩용 M1 원본도 없다")
        print(f"       (태그: `git tag -l '{TAG_MATCH}'` · 부트스트랩: {M1})")
        return 1

    label, read = base
    problems = []

    for name in PATCHED + IDENTICAL:
        if read(name) is None:
            problems.append(f"{name}: 기준선에 이 파일이 없다 — 대조할 수 없으므로 거부한다")

    for name in IDENTICAL:
        b = read(name)
        if b is not None and b != (V2 / name).read_bytes():
            problems.append(f"{name}: 기준선과 바이트가 다르다 (이 파일은 손대지 않기로 했다)")

    diff = current_diff(read)
    if "--update" in sys.argv:
        ALLOWED.write_text(diff)
        print(f"기준선: {label}")
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

    print(f"기준선: {label}")
    print(f"바이트 동일 요구: {', '.join(IDENTICAL)}")
    print(f"허용 diff 기록본: {ALLOWED.name} ({len(recorded.splitlines())}행)")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS — 기록된 diff 말고는 기준선과 동일하다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
