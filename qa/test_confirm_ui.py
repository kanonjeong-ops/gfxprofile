#!/usr/bin/env python3
"""**`[적용]`엔 확인창 금지 / `[저장]`에만 확인창** — 주석이 아니라 **검사로** 잠근다.

P4-5 · QA가 P4로 넘긴 조건 ④. 지금까지 이 규칙은 소스의 주석으로만 지켜졌다.
이 프로젝트에서 **주석은 증거가 아니고**(누적 교훈 ②), 고친 것을 안 잠그면 다음 라운드에 돌아온다.

### 왜 grep이 아닌가
- 이 프로젝트에서 **거짓 검사가 다섯 번** 나왔고 그중 둘이 *"grep이 규칙을 설명한 주석을 잡았다"*였다
- 규칙을 소스 패턴으로 강제하려던 시도(`confirmed:\\s*true`)는 **positional 호출을 못 잡아 무효**였다
  (반증자 실측: 그 패턴 0건 / 실제 호출 1건)
→ **렌더하고 실제로 눌러서** 무슨 일이 나는지 본다. 별칭·헬퍼·파생 변수·주석 마커를 **가리지 않는다.**

### 잠그는 것
1. `[적용]`을 눌러도 **확인창이 안 뜬다** — 가장 자주 누르는 버튼이라 확인은 순수 마찰이다
   (사용자 판정, 재제안 금지). 그리고 적용은 **실제로 일어난다**(아무 일도 안 하는 것과 구분)
2. `[저장]`을 누르면 **확인창이 뜬다** — 저장은 덮어쓰기다
3. **첫 저장 호출은 토큰 없이** 나간다 — 프론트가 토큰을 지어내 붙이면 계약이 무너진다
4. 확정 시 **백엔드가 준 토큰을 그대로** 되돌린다
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "confirm_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)
TOKEN = "TOKEN-FROM-BACKEND"      # 프로브가 백엔드 대신 돌려주는 값


def main():
    if not U1.is_file():
        # ★ 판정할 수 없을 때는 통과가 아니라 **거부**다 (QA R7 · R2 재발 방지).
        #   SKIP 후 exit 0으로 두면 툴체인이 옮겨진 순간 이 계약을 **한 줄도 안 재고** 초록이 된다.
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    proc = subprocess.run([str(U1), str(PROBE)], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print("FAIL — 프로브가 죽었다")
        print("  " + (proc.stderr or proc.stdout).strip().splitlines()[-1])
        return 1
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    problems = []

    # 측정 경로에 닿았는지부터 — 버튼이 안 잡히면 **아무것도 못 잰 채 통과**한다.
    if r["applyButtons"] < 1:
        problems.append("적용 버튼을 하나도 못 찾았다 — 검사가 재려던 대상에 닿지 못했다")
    if r["saveButtons"] < 1:
        problems.append("저장 버튼을 하나도 못 찾았다 — 검사가 재려던 대상에 닿지 못했다")

    # ① 적용에는 확인창이 없다
    if r["modalsAfterApply"] != 0:
        problems.append(
            f"[적용]이 확인창을 {r['modalsAfterApply']}번 띄웠다 ★사용자 판정 위반 "
            f"— 가장 자주 누르는 버튼이라 확인은 순수 마찰이다(재제안 금지 항목)")
    if r["appliedCount"] < 1:
        problems.append("[적용]을 눌렀는데 apply RPC가 안 나갔다 — "
                        "'확인창이 없다'가 '아무 일도 안 한다'로 성립한 것이면 위 판정은 무의미하다")

    # ② 저장에는 확인창이 있다
    if r["modalsAfterSave"] != 1:
        problems.append(
            f"[저장]이 확인창을 {r['modalsAfterSave']}번 띄웠다(1이어야 한다) "
            f"★덮어쓰기가 확인 없이 일어날 수 있다")
    if not r["modalIsConfirmModal"]:
        problems.append("띄운 것이 ConfirmModal이 아니다 — 취소 경로가 없는 창일 수 있다")

    # ③④ 토큰은 지어내지 않고, 받은 것을 그대로 되돌린다
    if r["firstSaveCallHadToken"]:
        problems.append("첫 저장 호출에 토큰이 실려 있다 — 프론트가 토큰을 지어냈다 ★계약 위반")
    if r["tokenSentBack"] != TOKEN:
        problems.append(
            f"확정 시 되돌린 토큰이 백엔드가 준 것과 다르다({r['tokenSentBack']!r}) ★계약 위반")

    # 파괴적 표시 — `preferredFocus`가 `ConfirmModalProps`에 없어(실측) 쓸 수 있는 방어가 이것뿐이다.
    if not r["destructiveFlagged"]:
        problems.append("확인창에 bDestructiveWarning이 없다 — 되돌리기 어려운 동작임을 화면이 안 말한다")

    # ⑤ [QA 반려 ②] 확인창을 **못 띄웠을 때**: 안전한 것과 진단 가능한 것은 다른 요건이다.
    #    `showModal`은 런타임에 얻어지는 값이라 undefined일 수 있고, 그때 나는 `TypeError`는
    #    `.then(fn, errFn)`의 두 번째 인자가 **못 잡는다** → 아무 흔적 없이 버튼이 죽는다.
    if r["savedDespiteModalFailure"]:
        problems.append("확인창을 못 띄웠는데 저장이 일어났다 ★fail-closed가 깨졌다")
    if not r["noteOnModalFailure"]:
        problems.append(
            "확인창을 못 띄웠는데 화면에 아무 안내가 없다 — 저장 버튼이 흔적 없이 죽는다. "
            "안전한 것(=아무것도 안 씀)과 진단 가능한 것은 다른 요건이다(설계 §2-E-0)")

    print("확인창 규칙 (렌더+클릭으로 측정)")
    print(f"  적용 {r['applyButtons']}개 → 확인창 {r['modalsAfterApply']}회 · 실제 적용 {r['appliedCount']}회")
    print(f"  저장 {r['saveButtons']}개 → 확인창 {r['modalsAfterSave']}회 · "
          f"첫 호출 토큰없음={not r['firstSaveCallHadToken']} · 토큰 반환={r['tokenSentBack'] == TOKEN}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
