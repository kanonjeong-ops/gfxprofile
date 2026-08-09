#!/usr/bin/env python3
"""프론트의 표시명이 `plugin.json`의 name과 같은지 검사한다 — 설계 E19 § QA 공백 2번.

무엇을 막는가 (S5):
    표시명의 정본은 `plugin.json`의 `name`인데, 화면에 뜨는 문자열은 `src/*.tsx`에
    **하드코딩**돼 있다. 정본만 바꾸고 소스를 안 바꾸면 **이름을 바꿨는데 화면은 그대로**다.
    기존 QA 8종은 이 어긋남을 하나도 감지하지 못한다(E19 § QA 공백에서 8개 파일 직접 대조).

자기참조가 아닌 이유:
    비교하는 두 값이 **다른 파일**에서 온다 — `plugin.json`(정본)과 `src/*.tsx`(하드코딩).
    같은 파일을 두 번 읽어 비교하던 옛 `build.sh` 검사(E19 (A), 제거됨)와는 다르다.

★ 이 테스트도 매 실행마다 **자기 자신을 반증한다.**
    ⚠️ 정확히 말하면 **소스를 변조하는 것이 아니라 기준 문자열(기대 표시명)을 흔든다** —
    같은 검사 로직에 틀린 기대값을 넣어 위반이 검출되는지 본다(QA R2 지적 ⑥: 예전 독스트링은
    "소스를 변조한다"고 적었는데 구현은 그렇지 않았다. 문서와 구현이 다르면 문서가 거짓말이다).
    하나라도 안 잡히면 *"이 검사는 무효다"* 라며 스스로 실패한다 — 통과 사실이 안전의 근거가
    되려면 그 검사가 **지금도 잡는다는 증거**가 같이 있어야 한다.

한계(문서에 남긴다):
    검사 범위: `src/**/*.tsx` 전체(rglob). ① `i18n-exempt … 플러그인 이름` 표시가 붙은 다음 줄이
    표시명과 같은가 ② `definePlugin`의 `name:`이 표시명과 같은가 ③ **옛 식별자 문자열이 화면
    문자열 자리에 남아 있지 않은가**(마커를 어떻게 달았든 잡는다 — 2026-08-06 QA 지적 ③ 보완).

    정적 검사다. `@decky/manifest` 주입(E19 "채택 보류")이 스파이크로 채택되면 하드코딩 자체가
    사라져 이 검사는 구조적으로 항상 PASS가 되고 실질 은퇴한다. 그전까지는 회귀를 잠그는 유일한
    장치다. 렌더 결과가 아니라 소스를 보므로 CSS·조건부 렌더로 화면에 안 뜨는 경우는 못 본다.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ QA 지적 ③(G2): 하드코딩 목록이면 **새로 생긴 컴포넌트를 아예 안 본다.**
#   i18n 검사는 src를 rglob하는데 이쪽만 2개 파일이라 그 틈으로 옛 이름이 새어 나갔다.
FILES = sorted(str(q.relative_to(ROOT)) for q in (ROOT / "src").rglob("*.tsx"))
MARKER = "i18n-exempt"
MARKER_KIND = "플러그인 이름"          # 이 표시가 붙은 자리 = 표시명이 박히는 자리


def sites(text):
    """(행번호, 그 줄) 목록 — '플러그인 이름' i18n-exempt 표시 **다음 줄**들."""
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        if MARKER in ln and MARKER_KIND in ln and i + 1 < len(lines):
            out.append((i + 2, lines[i + 1]))
    return out


def violations(name):
    """표시명 `name`을 기준으로 어긋난 자리를 찾는다."""
    bad = []
    total = 0
    for f in FILES:
        text = (ROOT / f).read_text()
        found = sites(text)
        total += len(found)
        for lineno, ln in found:
            if name not in ln:
                bad.append(f"{f}:{lineno} 표시명이 없다 → {ln.strip()[:70]}")
        # definePlugin의 name:은 표시 표시자가 앞줄에 없어 따로 본다
        for m in re.finditer(r'^\s*name:\s*"([^"]*)"', text, re.M):
            total += 1
            if m.group(1) != name:
                bad.append(f"{f} definePlugin의 name({m.group(1)!r})이 plugin.json과 다르다")
    return bad, total


STALE = "gfxprofile"          # 옛 표시명 = 내부 식별자. 화면 문자열로 남으면 안 된다

# ★ QA R2 지적 ⑨: 예전엔 `console.log`가 **줄 어딘가에만 있어도** 그 줄 전체를 면제했다.
#   `<div onClick={() => console.log(1)}>gfxprofile</div>` 한 줄로 우회된다(실증됨).
#   면제는 **그 토큰이 놓인 자리**에만 준다 — 정당한 자리를 지운 뒤 남아 있으면 위반이다.
import re as _re
LEGIT = (
    _re.compile(r'const\s+ROUTE\s*=\s*["\'][^"\']*["\']'),     # route 문자열
    _re.compile(r'console\.\w+\([^)]*\)'),                       # 로그 인자
    _re.compile(r'`\[[^`\]]*\][^`]*`'),                            # 로그 접두어 템플릿(보간 포함)
)


def _strip_legit(line):
    for pat in LEGIT:
        line = pat.sub("", line)
    return line


def stale_on_screen():
    """식별자 문자열이 **화면에 그려지는 자리**에 남아 있는가 (QA 지적 ③ G1 보완).

    마커를 어떻게 달았든(다른 종류의 i18n-exempt를 붙여 두 검사를 동시에 통과시키는 우회 포함)
    옛 이름이 화면 문자열로 남으면 잡는다. 식별자로 정당하게 쓰는 자리(ROUTE·로그 접두어)는 제외.
    """
    bad = []
    for f in FILES:
        for i, ln in enumerate((ROOT / f).read_text().splitlines(), 1):
            if STALE not in _strip_legit(ln):
                continue
            bad.append(f"{f}:{i} 옛 이름이 화면 문자열로 남아 있다 → {ln.strip()[:70]}")
    return bad


manifest_name = json.loads((ROOT / "plugin.json").read_text())["name"]
bad, total = violations(manifest_name)
bad += stale_on_screen()

# ★ QA R2 지적 ⑩: `total == 0`만 보면 **마커를 하나씩 지울 때 조용히 줄어든다**(5자리→4자리 PASS).
#   지금 실물이 몇 자리인지를 하한으로 박는다 — 줄어들면 그 자체가 신호다.
MIN_SITES = 5
if total < MIN_SITES:
    sys.exit(f"FAIL 검사 대상이 {total}자리뿐이다(하한 {MIN_SITES}) — "
             f"표시 마커가 지워졌거나 규칙이 바뀌었다 (fail-closed)")

# ── 자기 반증: 이 검사가 지금도 잡는지 ──────────────────────────────────────
#   실제 소스를 건드리지 않고, 기준 문자열을 흔들어 검출되는지만 본다.
proofs = []
for wrong in ("gfxprofile", "eGPU Game Config Swapx", "완전히 다른 이름"):
    b, _ = violations(wrong)
    proofs.append((wrong, len(b)))
undetected = [w for w, n in proofs if n == 0]
if undetected:
    print("FAIL 이 검사는 무효다 — 다음 어긋남을 검출하지 못했다:", undetected)
    sys.exit(1)

if bad:
    print("FAIL 표시명이 plugin.json과 어긋난 자리:")
    for b in bad:
        print("  -", b)
    print(f"  (정본 plugin.json name = {manifest_name!r})")
    sys.exit(1)

print(f"PASS 표시명 정합 {total}자리 — 전부 {manifest_name!r} "
      f"· 자기 반증 3종 검출 확인 {[n for _, n in proofs]}")
