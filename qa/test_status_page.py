#!/usr/bin/env python3
"""P3 「현황」 탭의 완료 기준을 **실행형으로** 잠근다.

지키는 것(설계 §9-E ② — 200게임 상한이 생기면서 재정의된 P3 기준):
    ① **미완성 게임이 위로** 정렬된다 — 스크롤 없이 "무엇이 덜 됐나"가 먼저 보인다
    ② **「미완성만 보기」 토글**이 실제로 걸러 낸다
    ③ **200게임에서도** ①②가 유지된다

왜 이 테스트가 필요한가:
    원래 P3 기준은 *"9게임 한 화면 · 스크롤 없이 구분"*이었다. 그 숫자는 **개발 기기에 우연히
    등록돼 있던 게임 수**였고, 200게임 상한이 생기면서 무효가 됐다(설계 §0-A).
    새 기준은 "한 화면"이 아니라 **"미완성이 먼저 보인다"**이므로, 그건 화면 크기가 아니라
    **정렬·필터 로직**의 문제다 — 그러니 로직으로 재는 것이 맞다.

⚠️ 한계: 이 테스트는 컴포넌트를 node에서 렌더한다. **실기 관찰을 대체하지 않는다** —
    Steam의 `ToggleField`는 커스텀 컴포넌트라 실제 조작감·D-패드 도달성은 빅픽처에서만 확인된다.
    (실제로 DOM `.click()`으로는 그 토글이 안 눌린다.)
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "status_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)


def run(n):
    proc = subprocess.run([str(U1), str(PROBE), str(n)], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-1:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")     # 판정 불가는 통과가 아니라 거부다
        return 1

    problems = []
    for n in (9, 200):                                # 이 기기 규모 / 설계 상한
        r, err = run(n)
        if r is None:
            print(f"FAIL — 프로브 실행 실패(N={n}): {err}")
            return 1

        # 측정 경로에 닿았는지부터 — 행이 안 나오면 아무것도 못 잰 것이다
        if r["rowsWithoutFilter"] != n:
            problems.append(f"N={n}: 행이 {r['rowsWithoutFilter']}개만 렌더됐다(기대 {n})")
        if not r["toggleWired"]:
            problems.append(f"N={n}: 토글에 onChange가 안 걸렸다 — 필터를 켤 수단이 없다")
        # ★ 2026-08-06 QA 지적 ⑤: "함수가 걸려 있다"만 보면 `onChange={() => {}}`도 통과한다.
        #   프로브가 **실제로 눌러** 상태가 바뀌었는지를 본다.
        # ★ QA R2 ⑫: 배선이 살아 있어도 **포커스가 못 가면 못 누른다.** P3 완료 기준
        #   "D-패드만으로 모든 버튼 도달"이 걸린 자리다(2026-08-06 실기에서 실제로 위반이었다).
        # ★ [2026-08-07 P4-3] 이름 하나가 아니라 **상호작용 컴포넌트 전부**를 본다
        #   (QA가 P4로 넘긴 조건 ①). P4의 저장·확인 버튼은 만들어지는 순간 자동으로 여기 걸린다 —
        #   *"핸드헬드에서 못 누르는 확인 버튼은 확인창이 아니라 잠금이다."*
        if r["unreachable"]:
            problems.append(
                f"N={n}: {r['unreachable']}가 Focusable 밖이라 D-패드로 도달할 수 없다 ★기준 위반")
        # ★ **0개를 훑고 「전부 도달 가능」이라 말하는 것**을 막는다. 컴포넌트 이름이 바뀌면
        #   집합이 조용히 아무것도 안 잡고, 그 상태의 "위반 0건"은 안전의 근거가 아니다.
        if r["interactiveSeen"] < 2:
            problems.append(
                f"N={n}: 상호작용 컴포넌트를 {r['interactiveSeen']}개만 봤다 — "
                f"검사가 재려던 대상에 닿지 못했다(INTERACTIVE 집합이 낡았을 수 있다)")
        if not r["toggleDrivesState"]:
            problems.append(
                f"N={n}: 토글을 눌러도 상태가 안 바뀐다 — 배선이 죽었다(onChange가 아무것도 안 함)")

        if not r["incompleteFirst"]:
            problems.append(f"N={n}: 미완성 게임이 위로 정렬되지 않았다 ★P3 기준 위반")
        if r["rowsWithFilter"] != r["incompleteCount"]:
            problems.append(
                f"N={n}: 필터를 켜니 {r['rowsWithFilter']}개 남았다(기대 {r['incompleteCount']})")
        if not r["filterKeepsOnlyIncomplete"]:
            problems.append(f"N={n}: 필터가 완성된 게임까지 남겼다")

        print(f"N={n:3d}: 전체 {r['rowsWithoutFilter']}행 / 미완성 {r['incompleteCount']}개 "
              f"→ 필터 시 {r['rowsWithFilter']}행 · 미완성 우선={r['incompleteFirst']}")

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
