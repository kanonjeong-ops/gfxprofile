#!/usr/bin/env python3
"""설계 E13의 **자체 ErrorBoundary**를 실행형으로 잠근다.

잠그는 것:
    T1 `src/ui/ErrorBoundary.tsx`가 **React 클래스 컴포넌트**다
       (`getDerivedStateFromError` + `componentDidCatch`)
    T2 자식이 throw하면 **폴백이 실제로 렌더**된다 — grep이 아니라 던져 보고 본다
    T3 폴백이 **영어 고정**이다(한글 0자, `RENDER_FAILED` 표지) — i18n 자체가 못 뜨는
       상황이 여기로 오므로 `t()`를 거치면 폴백이 다시 던진다
    T4 폴백이 **intrinsic 요소만** 쓴다 — `@decky/ui`를 그리면 그것이 `undefined`일 때
       안전장치가 곧 크래시 원인이 된다(설계 E13이 `DFL.ErrorBoundary`를 버린 바로 그 이유)
    T5 경계가 **react 말고 아무것도 import하지 않는다** — 의존이 늘면 폴백의 전제가 무너진다
    T6 `componentDidCatch`가 `[gfxprofile] boundary where=…` 진단을 남긴다(cef_log 유일 레벨)
    T7 **정상 자식은 그대로 통과**한다 — 경계가 정상 렌더를 가로채지 않는다
    T8 **두 진입점이 모두 감싸여 있다** — QAM `content`와 route 컴포넌트(설계 E13)

★ 반증(§B): 경계를 깨뜨린 사본에서 실제로 FAIL하는지 대조군으로 확인한다.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "errorboundary_probe.cjs"
BOUNDARY = ROOT / "src" / "ui" / "ErrorBoundary.tsx"
INDEX = ROOT / "src" / "index.tsx"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)


def run_probe(boundary=None):
    args = [str(U1), str(PROBE)] + ([str(boundary)] if boundary else [])
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def check_behaviour(r):
    """프로브 결과 판정. §B가 변이 사본에도 같은 함수를 쓴다."""
    bad = []
    if not r["isClassComponent"]:
        bad.append("ErrorBoundary가 React 클래스 컴포넌트가 아니다 ★E13 위반")
    if not r["hasDerived"]:
        bad.append("getDerivedStateFromError가 없다 — 렌더 실패가 상태로 바뀌지 않는다")
    if not r["hasDidCatch"]:
        bad.append("componentDidCatch가 없다 — 진단을 남길 자리가 없다")
    # T5: react 말고 아무것도 안 쓴다
    extra = [m for m in r["imports"] if m != "react"]
    if extra:
        bad.append(f"경계가 react 밖 모듈을 import한다: {extra} ★그것이 못 뜨면 폴백도 못 뜬다")
    # T7: 정상 자식 통과
    if r["normalTexts"] != ["QA_NORMAL_CHILD"]:
        bad.append(f"정상 자식이 그대로 통과하지 않는다 — {r['normalTexts']}")
    if r["normalLogs"] != 0:
        bad.append(f"정상 렌더인데 진단이 {r['normalLogs']}건 나갔다")
    # T2·T3: 폴백
    if not r["fallbackShown"]:
        bad.append(f"자식이 throw했는데 폴백이 안 떴다 — 화면이 통째로 무너진다: {r['fallbackText']!r}")
    if r["fallbackHasHangul"]:
        bad.append("폴백에 한글이 있다 ★영어 고정이어야 한다 — i18n이 못 뜨는 상황이 여기로 온다")
    # T4: intrinsic 요소만
    decky = [t for t in r["fallbackTags"] if t.startswith("DECKY:")]
    if decky:
        bad.append(f"폴백이 @decky/ui 컴포넌트를 그린다: {decky} "
                   "★안전장치가 자기가 감시하는 실패에 걸린다")
    # T6: 진단
    if not r["diagTagged"]:
        bad.append(f"[gfxprofile] boundary where=… 진단이 없다 — 로그가 유일한 단서다: {r['diagLogs']}")
    if not r["diagHasError"]:
        bad.append("진단에 원 예외가 실리지 않았다 — 무엇이 터졌는지 알 수 없다")
    return bad


# ── T8. 두 진입점 래핑 (의미 기반 정적 판정) ─────────────────────────────────
def _balanced(text, start, opener, closer):
    """`start` 위치의 여는 기호부터 짝이 맞는 닫는 기호까지."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def check_entrypoints(source):
    """QAM `content`와 route가 **둘 다** 경계 안에 있는가.

    ★ `<ErrorBoundary`가 파일 어딘가에 있는지 세지 않는다 — 그러면 한 곳만 감싸도 통과한다.
      각 진입점의 **값 표현식**을 따로 떼어 그 안에 경계가 있는지 본다.
    """
    bad = []

    # (1) QAM 패널 — `content:` 뒤의 값 표현식
    match = re.search(r"\bcontent:\s*", source)
    if not match:
        return ["definePlugin의 content: 항목을 못 찾았다 — 검사가 대상에 닿지 못했다"]
    rest = source[match.end():]
    value = _balanced(rest, 0, "(", ")") if rest.startswith("(") else rest.split(",\n", 1)[0]
    if "<ErrorBoundary" not in value:
        bad.append(f"QAM content가 ErrorBoundary로 감싸이지 않았다 ★E13 위반 — {value.strip()[:80]!r}")

    # (2) route — `addRoute(ROUTE, <컴포넌트>)`의 그 컴포넌트가 경계를 그리는가
    match = re.search(r"routerHook\.addRoute\(\s*[A-Za-z_$][\w$]*\s*,\s*([A-Za-z_$][\w$]*)", source)
    if not match:
        return bad + ["routerHook.addRoute 호출을 못 찾았다 — 검사가 대상에 닿지 못했다"]
    component = match.group(1)
    decl = re.search(r"function\s+%s\s*\([^)]*\)\s*\{" % re.escape(component), source)
    if not decl:
        bad.append(f"route에 넘긴 {component}가 이 파일에 정의돼 있지 않다 — "
                   "경계 적용 여부를 판정할 수 없다(정적으로 추적 가능해야 한다)")
    else:
        body = _balanced(source, decl.end() - 1, "{", "}")
        if "<ErrorBoundary" not in body:
            bad.append(f"route 컴포넌트 {component}가 ErrorBoundary로 감싸이지 않았다 ★E13 위반")
    return bad


# ── §B. 반증 — 깨뜨렸을 때 실제로 FAIL하는가 ─────────────────────────────────
def falsify():
    report, bad = [], []
    original = BOUNDARY.read_text(encoding="utf-8")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-boundary-mutants-"))
    try:
        mutants = {
            "getDerivedStateFromError 제거 → 폴백이 안 뜬다": [
                ("  static getDerivedStateFromError(error: unknown): State {",
                 "  static qaRemoved_getDerivedStateFromError(error: unknown): State {")],
            "componentDidCatch 제거 → 진단이 안 남는다": [
                ("  componentDidCatch(error: unknown, info: ErrorInfo) {",
                 "  qaRemoved_componentDidCatch(error: unknown, info: ErrorInfo) {")],
            "폴백을 한국어로 → 영어 고정이 깨진다": [
                ("        RENDER_FAILED ({this.state.detail}) — this part of the UI could not be drawn.",
                 "        RENDER_FAILED ({this.state.detail}) — 이 부분을 그리지 못했습니다.")],
            "폴백이 자식을 그대로 반환 → 실패를 삼킨다": [
                ("    if (!this.state.failed) return this.props.children;",
                 "    if (true) return this.props.children;")],
        }
        for i, (label, reps) in enumerate(mutants.items()):
            source = original
            ok = True
            for old, new in reps:
                if source.count(old) != 1:
                    bad.append(f"§B 변이 앵커가 {source.count(old)}개다({label}) — 주입되지 않았다")
                    ok = False
                    break
                source = source.replace(old, new)
            if not ok:
                continue
            path = tmp / f"Mutant{i}.tsx"
            path.write_text(source, encoding="utf-8")
            print(f"     [주입] ErrorBoundary.tsx  {label}")
            r, err = run_probe(path)
            caught = bool(err) or bool(check_behaviour(r))
            report.append((f"B{i + 1} {label}", caught))
            if caught and r is not None:
                print(f"            → 검출: {check_behaviour(r)[0]}")
            elif caught:
                print(f"            → 검출: 프로브가 실패 종료({err})")
            else:
                bad.append(f"§B 반증 실패 — {label}를 넣어도 검사가 못 잡는다")

        # 음성 대조군: 손대지 않은 사본은 통과한다(변이 판정이 무엇이든 잡는 것은 아니다)
        clean = tmp / "Clean.tsx"
        clean.write_text(original, encoding="utf-8")
        r, err = run_probe(clean)
        clean_bad = [f"프로브 실패: {err}"] if r is None else check_behaviour(r)
        report.append(("B′ 손대지 않은 사본은 통과(음성 대조군)", not clean_bad))
        if clean_bad:
            bad.append(f"B′ 음성 대조군 실패 — 원본이 위반으로 잡혔다: {clean_bad}")

        # 진입점 래핑 반증 — 한쪽만 감싼 사본은 FAIL해야 한다
        index_src = INDEX.read_text(encoding="utf-8")
        for label, old, new in (
            ("QAM content 래핑 제거", "      <ErrorBoundary where=\"qam\">", "      <>"),
            ("route 래핑 제거", "    <ErrorBoundary where=\"route\">", "    <>"),
        ):
            if index_src.count(old) != 1:
                bad.append(f"§B 진입점 변이 앵커가 없다({label})")
                continue
            print(f"     [주입] index.tsx  {label}")
            mutated = index_src.replace(old, new, 1)
            caught = bool(check_entrypoints(mutated))
            report.append((f"B-entry {label}", caught))
            if caught:
                print(f"            → 검출: {check_entrypoints(mutated)[0]}")
            else:
                bad.append(f"§B 반증 실패 — {label}인데 T8이 못 잡는다")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert BOUNDARY.read_text(encoding="utf-8") == original      # 원본은 손대지 않았다
    return report, bad


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")       # 판정 불가는 통과가 아니라 거부다
        return 1
    if not BOUNDARY.is_file():
        print(f"FAIL — 자체 ErrorBoundary가 없다: {BOUNDARY} ★설계 E13 필수 항목")
        return 1

    problems = []
    r, err = run_probe()
    if r is None:
        print(f"FAIL — 프로브 실행 실패: {err}")
        return 1
    problems += check_behaviour(r)
    print(f"T1~T7 경계 실동작 — 폴백 {r['fallbackText'][:52]!r}… · "
          f"태그 {r['fallbackTags']} · import {r['imports']} · 진단 {len(r['diagLogs'])}건")

    problems += check_entrypoints(INDEX.read_text(encoding="utf-8"))
    print("T8 두 진입점(QAM content · route 컴포넌트) 래핑")

    report, fals_bad = falsify()
    print("\n§B 반증 (깨뜨렸을 때 FAIL이 나는가)")
    for label, caught in report:
        print(f"  {'✓' if caught else '✗'} {label} → {'검출됨' if caught else '못 잡음'}")
    problems += fals_bad

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
