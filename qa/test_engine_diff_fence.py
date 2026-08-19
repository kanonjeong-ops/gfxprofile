#!/usr/bin/env python3
"""diff fence — 엔진(`engine.py`·`store.py`)의 변경을 **감지해 사람 승인 앞에 세운다**.

★ [2026-08-19 기준선 교체] 목적을 「M1 불변 증명」에서 **「릴리스 단위 변경 감지 + 명시 승인」**
  으로 재정의했다. 전제가 소멸했기 때문이다 — v2는 "이식만 하고 엔진은 손대지 않는다"로 출발했으나
  엔진은 실제로 승인을 거쳐 여러 차례 갈라졌고 앞으로도 고친다. 기준선이 얼어 있으면 허용 diff가
  **한 방향으로 자라기만 해서**(교체 직전 742행) 언젠가 "엔진을 통째로 다시 썼고 여기 그 기록이
  있다"가 된다. 그 순간 신호는 사라진다.

  → 기준선을 **직전 릴리스 태그**로 옮긴다. 릴리스마다 리셋되므로 허용 diff는 언제나
    *"이번 릴리스에서 엔진이 뭐가 바뀌었나"*만 담고, 그 diff가 CHANGELOG의 재료가 된다.
    · **첫 릴리스 태그부터 자립적이다** — 리포만 있으면 돈다(외부 경로 의존 0).
      **그 전까지는 M1 원본이 필요하고 그것은 이 기기의 절대경로다** — 최초 릴리스 전에
      포크한 사람은 PATCHED 두 파일의 기준선이 없다(공개는 첫 릴리스와 함께 이뤄지므로
      실사용에서는 이 구간이 노출되지 않는다).
    · **최초 태그가 찍히기 전까지는 M1 원본을 기준선으로 쓴다**(부트스트랩). 태그가 생기면
      자동으로 전환되므로 이행 공백이 없다.
    · IDENTICAL 3파일은 기준선을 쓰지 않는다 — 아래 고정 지문과 대조한다.
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
import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
V2 = ROOT / "py_modules" / "gfxp"
#: 부트스트랩 전용. 최초 릴리스 태그가 찍히면 더 쓰지 않는다.
M1 = pathlib.Path("/home/deck/scripts/gfxprofile/gfxp")
ALLOWED = ROOT / "qa" / "engine_allowed.diff"

PATCHED = ("engine.py", "store.py")      # 기록된 diff만 허용

#: 손대지 않기로 한 파일들(설계 §11-4). ★ **기준선에서 떼어내 지문으로 고정한다** —
#: 기준선을 릴리스 태그로 옮기면 이 파일들이 「직전 릴리스의 자기 자신」과 비교돼, 한 번 들어간
#: 변경이 다음 릴리스부터 영구히 안 보이게 된다(2026-08-19 QA A-1). 요구는 "릴리스 이후 불변"이
#: 아니라 **불변**이다. 이 상수를 고치는 것 자체가 리뷰에 보이는 행위다.
IDENTICAL_SHA256 = {
    "discover.py": "154eec93fde72dde574de58612c6cf7593e078b30f2cb77f1f88189542af3b3c",
    "detect.py": "4b9c42e4886734e0647f298166be4f3b59b598574c0c9aa9acd05058173dce8f",
    "__init__.py": "5f04bed7d2990f1cf2759fe74f86301997fda788c56bcb4a00680187be575b73",
}

#: 릴리스 태그만 기준선이 된다. `v0.0.0-fencecheck` 같은 시험용 태그가 기준선이 되면 그 시점의
#: 엔진이 조용히 정본이 된다(2026-08-19 QA A-2). glob은 접미사를 못 막으므로 정규식으로 거른다.
TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def latest_release_tag():
    """('tag', 이름) / ('none', None) / ('error', 사유) 중 하나.

    ★ git이 죽은 것과 「태그가 아직 없다」를 같은 것으로 취급하면 판정 불가가 조용히
      부트스트랩으로 바뀐다(2026-08-19 QA A-4). `git tag --list`는 태그가 없어도 rc 0에
      빈 목록을 준다 — 그래서 **rc가 두 상태를 갈라 준다**(describe는 둘 다 rc 128이다).
    """
    r = _git("tag", "--list", "v*", "--merged", "HEAD")
    if r.returncode != 0:
        return "error", f"git 태그 목록을 읽을 수 없다: {ROOT}"
    tags = [t for t in r.stdout.decode().split() if TAG_RE.fullmatch(t)]
    if not tags:
        return "none", None
    return "tag", max(tags, key=lambda t: tuple(int(x) for x in t[1:].split(".")))


def baseline():
    """((라벨, 이름→bytes 읽기), None) 또는 (None, 사유)."""
    kind, value = latest_release_tag()
    if kind == "error":
        return None, value
    if kind == "tag":
        def read(name):
            r = _git("show", f"{value}:py_modules/gfxp/{name}")
            return r.stdout if r.returncode == 0 else None
        return (f"직전 릴리스 태그 {value}", read), None
    if M1.is_dir():
        def read(name):
            p = M1 / name
            return p.read_bytes() if p.is_file() else None
        return (f"M1 원본 {M1} (부트스트랩 — 최초 릴리스 태그 전까지)", read), None
    return None, f"릴리스 태그도 없고 부트스트랩용 M1 원본도 없다: {M1}"


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
    base, reason = baseline()
    if base is None:
        # ★ 기준이 없으면 **실패다** (2026-08-05 QA R7). 예전엔 SKIP 후 0을 돌려줬는데,
        #   그러면 기준선이 사라진 순간 **엔진을 한 줄도 대조하지 않고 전체 테스트 루프가 성공**한다.
        #   검사는 판정할 수 없을 때 통과가 아니라 **거부**해야 한다.
        print(f"FAIL — 기준선을 잡을 수 없다: {reason}")
        return 1

    label, read = base
    problems = []

    # PATCHED만 기준선을 탄다. IDENTICAL은 고정 지문이 기준이라 기준선과 무관하다.
    for name in PATCHED:
        if read(name) is None:
            problems.append(f"{name}: 기준선에 이 파일이 없다 — 대조할 수 없으므로 거부한다")

    for name, want in IDENTICAL_SHA256.items():
        got = hashlib.sha256((V2 / name).read_bytes()).hexdigest()
        if got != want:
            problems.append(f"{name}: 고정 지문과 다르다 (이 파일은 손대지 않기로 했다)\n"
                            f"      기록 {want}\n      실물 {got}")

    diff = current_diff(read)

    # ★ 판정을 `--update`보다 **앞에** 둔다 (2026-08-19 QA A-3/B-11). 예전에는 여기서 발견한
    #   문제를 들고도 `--update`가 먼저 빠져나가 0을 돌려줬다 — 갱신 갈래만 "판정할 수 없으면
    #   거부한다"는 이 검사 자신의 규칙 밖에 있었다.
    if problems:
        print(f"기준선: {label}")
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        if "--update" in sys.argv:
            print("  ↑ 위 문제를 먼저 해소해야 기록본을 갱신할 수 있다 (갱신하지 않았다)")
        return 1

    if "--update" in sys.argv:
        ALLOWED.write_text(diff)
        print(f"기준선: {label}")
        print(f"기록본 갱신: {ALLOWED} ({len(diff.splitlines())}행)")
        # ★ 승인할 것을 그 자리에서 읽게 한다 — 갱신이 통과 의식이 되는 것을 막는 절반이다
        #   (나머지 절반 = 릴리스 시 CHANGELOG 반영 확인. `release` 명령과 한 묶음).
        print("--- 아래 diff를 사람이 읽고 승인해야 한다. 허용 목록은 이 파일이 전부다 ---")
        print(diff if diff else "(비어 있음 — 기준선과 완전히 같다)")
        print("--- diff 끝 ---")
        return 0

    if not ALLOWED.exists():
        print(f"FAIL — 허용 diff 기록본이 없다: {ALLOWED}\n  최초 1회 `--update`로 만들고 리뷰받아라")
        return 1

    recorded = ALLOWED.read_text()
    if diff != recorded:
        d = list(difflib.unified_diff(recorded.splitlines(), diff.splitlines(),
                                      fromfile="기록된 허용 diff", tofile="지금의 diff", n=1))
        print(f"기준선: {label}")
        print("\nFAIL")
        print("  engine/store의 diff가 기록본과 다르다 — 아래가 그 차이다:")
        for x in d[:40]:
            print("    " + x)
        return 1

    print(f"기준선: {label}")
    print(f"고정 지문 대조: {', '.join(IDENTICAL_SHA256)}")
    print(f"허용 diff 기록본: {ALLOWED.name} ({len(recorded.splitlines())}행)")
    print("PASS — 기록된 diff 말고는 기준선과 동일하다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
