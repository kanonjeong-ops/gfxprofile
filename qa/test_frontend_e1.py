#!/usr/bin/env python3
"""E1 불변식을 **의미로** 잠근다 — 정규식이 아니라 실제 렌더·클릭 결과로.

지키는 것(설계 E1):
    실행 중인 게임이 있어도 **일괄 적용은 실행할 수 있어야 한다.**
    (막으면 게임 하나가 켜져 있다는 이유로 아무것도 적용되지 않는다 = M1 불변식 정면 위반)

왜 이렇게까지 하나 — 뚫린 이력이 그대로 설계다:
    1차 정규식(`disabled={…running}`)  → 파생 변수로 우회
    2차 허용 목록(식별자 이름)         → `ready` 값 오염으로 우회
    3차 `running` 등장 위치 통제        → `.ts` helper·예외 마커 스푸핑으로 우회
    4차 런타임 `disabled` 관찰          → **onClick 무력화·pointerEvents·env 분기로 우회**
    → **`disabled`는 대리 지표였다.** 지금은 **눌러 보고 `applyAll`이 실제로 불렸는지**를 잰다.
    5차(P10, F8) 확인창이 생기면서 **뒤집힐 자리가 모달 층으로 늘었다** — OK 비활성·확정 무력화.
      같은 불변식이므로 같은 판정기(`violations`)가 덮는다.

이 파일은 **반대 방향 계약도 함께** 잰다(3절): 확인 없이 실행되지 않는가 —
    1차 호출은 토큰 없이 나가고, 확정 시에는 백엔드가 준 토큰이 **그대로** 되돌아가며,
    확인창을 못 띄우면 실행이 아예 없다. E1만 재면 이쪽이 조용히 깨진다.

★ 이 테스트는 매 실행마다 **자기 자신을 반증한다.**
    알려진 우회 6종을 그때그때 주입해 **전부 검출되는지** 확인하고, 하나라도 안 잡히면
    *"이 테스트는 무효다"* 라며 스스로 실패한다. 통과했다는 사실이 안전의 근거가 되려면
    그 검사가 **지금도 잡을 수 있다는 증거**가 같이 있어야 한다.

⚠️ 원리적 한계(문서에 남긴다): 프로브는 node에서 컴포넌트를 직접 렌더한다 —
    실제 Steam CEF·React·@decky/ui가 아니다. 브라우저에서만 나타나는 차이(CSS 상속, 실제
    포커스·입력 처리)는 못 본다. 그래서 **빅픽처 실기 관찰을 대체하지 않는다.**
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "frontend_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

# 알려진 우회 6종(P10에서 모달 층 2종 추가). (설명, **대상 파일**, 정규식, 치환) — 전부 실행 중 게임을 이유로 일괄 적용을 막는다.
# ★ 2026-08-06: 버튼이 `BulkApplyButton.tsx`로 분리되면서 주입 대상이 옮겨갔다(설계 §9-F A-4).
#   이 목록이 낡으면 주입이 실패하고 테스트가 **스스로 무효를 선언한다** — fail-closed다.
BYPASSES = [
    (
        # 호출부에서 `ready`를 오염시킨다 — 컴포넌트는 `running`을 못 보지만 호출부는 본다.
        # **분리 후 남는 가장 현실적인 위반 형태**다(값을 넣어 주는 쪽에서 막는 것).
        "ready 값 오염(호출부)",
        "index.tsx",
        r"ready=\{\(profile === \"dock\" \? counts\?\.dock_ready : counts\?\.internal_ready\) \?\? 0\}",
        'ready={(counts?.running ?? 0) > 0 ? 0 : ((profile === "dock" ? counts?.dock_ready : counts?.internal_ready) ?? 0)}',
    ),
    (
        "onClick 무력화(버튼은 활성인데 아무 일도 안 함)",
        "index.tsx",
        r"onApply=\{runApplyAll\}",
        'onApply={(p) => { if (!(counts?.running ?? 0)) runApplyAll(p); }}',
    ),
    (
        # 여는 태그만 넣으면 JSX가 어긋나 주입이 무효가 된다 — **감싸는 형태로** 넣는다.
        "조상 pointerEvents:none(호출부에서 감싸기)",
        "index.tsx",
        r"(<BulkApplyButton\n)([\s\S]*?)(/>\n)",
        r'<div style={{ pointerEvents: counts?.running ? "none" : "auto" }}><BulkApplyButton\n\2/></div>\n',
    ),
    (
        # ★ P10: 확인창의 OK를 실행 중 수로 죽인다 — E1이 모달 층에서 뒤집히는 형태.
        "확인창 OK 비활성(실행 중 수를 활성 조건으로)",
        "index.tsx",
        r'strOKButtonText=\{t\("APPLY_ALL_CONFIRM_OK"\)\}',
        'bOKDisabled={params.running_refused > 0} strOKButtonText={t("APPLY_ALL_CONFIRM_OK")}',
    ),
    (
        # ★ P10: OK는 활성인데 확정이 아무 일도 안 한다 — "눌리지 않는 것과 같다"의 모달 판.
        "확인창 확정 무력화(실행 중이면 2차 호출 안 함)",
        "index.tsx",
        r"onConfirm=\{\(\) => runApplyAll\(profile, p\.confirm_token\)\}",
        "onConfirm={() => { if (!p.running_refused) runApplyAll(profile, p.confirm_token); }}",
    ),
    (
        # ⚠️ 스프레드는 **`disabled=` 뒤에** 놓아야 이긴다. 앞에 두면 뒤의 disabled가 덮어써
        #   "주입은 됐는데 효과가 없는" 무효한 대조군이 된다(실제로 그렇게 짰다가 걸렸다).
        #   컴포넌트는 `running`을 못 보므로 전역을 통해 새어 들어오는 형태로 시험한다.
        "env 분기(브라우저에서만 비활성)",
        "BulkApplyButton.tsx",
        r"onClick=\{\(\) => onApply\(profile\)\}",
        '{...(typeof window !== "undefined" ? ({ disabled: true } as {}) : {})}'
        " onClick={() => onApply(profile)}",
    ),
]


def run_probe(src_dir):
    proc = subprocess.run(
        [str(U1), str(PROBE), str(src_dir)], capture_output=True, text=True, cwd=str(ROOT)
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-1:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def violations(result):
    """E1 위반의 관찰 가능한 형태 — 하나라도 있으면 '일괄 적용을 막았다'는 뜻이다."""
    out = []
    if any(b["disabled"] for b in result["buttons"]):
        out.append("버튼이 비활성")
    if result.get("styleBlocked"):
        out.append("조상 스타일로 클릭 차단")
    for want in ("dock", "internal"):
        if want not in result.get("applyCalls", []):
            out.append(f"눌러도 {want} 적용이 호출되지 않음")
    # ★ P10(F8): 확인창이 생기면서 **E1이 뒤집힐 자리가 모달 층으로 하나 더 늘었다.**
    #   설계 §3-A: "확인창의 OK는 항상 활성이다 — running_refused는 표시 전용이며 OK 활성
    #   조건에 절대 들어가지 않는다. 확인창은 마찰이지 조건이 아니다."
    #   그래서 ① OK 비활성 ② 확정해도 실행이 안 나감 — 둘 다 같은 위반으로 센다.
    if result.get("modalOkDisabled"):
        out.append("확인창 OK가 비활성(실행 중 수를 활성 조건으로 썼다)")
    for want in ("dock", "internal"):
        if want not in result.get("executed", []):
            out.append(f"확인창을 확정했는데 {want} 실행(2차 호출)이 나가지 않음")
    if not result["sawCounts"]:
        # ready가 0으로 오염됐거나(=위반) 프로브 가정이 깨졌거나(=검사 무효) 둘 중 하나다.
        out.append("주입한 현황이 라벨에 닿지 않음(ready 오염 또는 프로브 가정 붕괴)")
    return out


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")   # 판정 불가는 통과가 아니라 거부다(QA R7)
        return 1

    # ── (1) 정상 소스: 실행 중 1개여도 두 버튼이 눌리고 실제로 호출돼야 한다 ──
    result, err = run_probe(ROOT / "src")
    if result is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1
    if len(result["buttons"]) != 2:
        print(f"FAIL — 일괄 버튼이 2개가 아니다: {result['buttons']}")
        return 1

    bad = violations(result)
    print(f"실행 중 1개 + 대상 보유: 버튼 {len(result['buttons'])}개 / 클릭 호출 {result['applyCalls']}")
    if bad:
        print("FAIL — 실행 중인 게임을 이유로 일괄 적용이 막혔다(E1 위반)")
        for b in bad:
            print(f"  {b}")
        return 1

    # ── (2) 음성 대조군: 알려진 우회 6종이 지금도 잡히는가 ────────────────────
    for label, target, pattern, replacement in BYPASSES:
        source = (ROOT / "src" / target).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            injected, n = re.subn(pattern, replacement, source, count=1)
            if n != 1:
                # 주입이 안 됐는데 "통과"로 읽는 것이 이 프로젝트에서 세 번 난 사고다.
                print(f"FAIL — 음성 대조군 주입 실패({label}): 대상 식을 못 찾았다. 검사가 무효다.")
                return 1
            (case / target).write_text(injected, encoding="utf-8")

            control, err = run_probe(case)
            if control is None:
                print(f"FAIL — 음성 대조군 프로브 실행 실패({label}): {err}")
                return 1
            caught = violations(control)
            if not caught:
                print(f"FAIL — 우회를 주입했는데 통과했다: {label}")
                print("       **이 테스트는 그 우회에 대해 무효다.**")
                return 1
            print(f"  음성 대조군 검출: {label} → {caught[0]}")

    # ── (3) P10(F8) 2단계 계약 정합 — 프론트가 계약을 지키는가 ─────────────
    #    ★ E1과 **다른 것**을 잰다: E1은 "막히지 않는가", 여기는 "확인 없이 실행되지 않는가".
    #      둘은 반대 방향이라 한쪽만 재면 다른 쪽이 조용히 깨진다.
    contract = []
    if result.get("firstCallsHadToken"):
        contract.append("1차 호출에 토큰이 실려 있다 — 프론트가 토큰을 지어냈다 ★계약 위반")
    kinds = result.get("confirmModals") or []
    if kinds != ["ConfirmModal", "ConfirmModal"]:
        contract.append(f"버튼 2개를 눌렀는데 확인창이 {kinds}다(각 1회 ConfirmModal이어야 한다)")
    if result.get("replayedForeignToken"):
        contract.append("다른 프로필의 토큰을 되돌려 보냈다 ★방향 바인딩이 깨진다")
    if result.get("executedAfterModalFailure"):
        contract.append("확인창을 못 띄웠는데 실행이 나갔다 ★fail-closed가 깨졌다")
    if contract:
        print("FAIL — F8 2단계 계약 위반")
        for c in contract:
            print(f"  {c}")
        return 1
    print(f"F8 2단계: 1차 무토큰 → 확인창 {len(kinds)}회 → 확정 시 실행 {result.get('executed')} · "
          f"모달 실패 시 실행 0")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
