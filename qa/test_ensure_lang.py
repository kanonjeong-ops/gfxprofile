#!/usr/bin/env python3
"""언어 확정(`ensureLang`)이 **모든 실패 모드에서 정착**하는지 — QA R2 지적 ⑬의 회귀 잠금.

정착하지 않으면 `StatusPage`가 `langReady`를 영원히 못 받아 **화면이 영구히 빈다.**
"안 끝난다"는 예외를 안 던져서 보통 테스트로는 안 잡힌다 — 그래서 시간 제한을 두고 잰다.

★ 이 파일이 존재하는 이유: 같은 결함을 실기로 찾아 고쳐 놓고 **검사를 안 붙여** QA에 다시 지적당한
  전례가 바로 앞 라운드에 있다(토글 도달성 ⑫). 고친 것은 잠근다.
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ 경로는 build.sh의 U1_ROOT 규약을 따른다(상대 계산은 사본·이동에서 조용히 깨진다).
#   ⚠️ **없으면 SKIP이 아니라 실패다.** 첫 판은 SKIP(exit 0)이었는데, 사본에서 돌리자
#   "조용히 통과"해 버렸다 — 이 프로젝트가 반복해 당한 「검사가 안 도는데 통과」 그 자체다.
U1_ROOT = pathlib.Path(
    os.environ.get("U1_ROOT", "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle"))
NODE = U1_ROOT / "toolchain/node-v22.23.2-linux-x64/bin/node"

if not NODE.is_file():
    sys.exit(f"FAIL — 툴체인 node를 찾지 못했다: {NODE}\n"
             f"  (U1_ROOT 환경변수로 지정할 수 있다. 검사를 건너뛰지 않는다 — fail-closed)")

r = subprocess.run([str(NODE), "qa/ensure_lang_probe.cjs"], cwd=ROOT,
                   capture_output=True, text=True, timeout=60)
if r.returncode != 0:
    print("FAIL — 프로브 실행 실패\n" + (r.stderr or "")[-600:])
    sys.exit(1)

res = json.loads(r.stdout.strip().splitlines()[-1])

# ★ QA R3 지적 ⑮: 아래 `bad`는 **전칭 조건**이라 시나리오가 0개여도 통과한다.
#   가장 중요한 「행(응답 없음)」 하나만 조용히 빠져도 `PASS … 4종`으로 넘어간다 —
#   그건 이 테스트가 존재하는 이유 그 자체다. 형제 테스트엔 하한을 넣어 놓고
#   새 파일엔 같은 잣대를 안 댔다. **개수가 아니라 집합으로 못박는다.**
EXPECTED = {"행(응답 없음)", "거부", "ok:false", "ok:true인데 data 없음", "정상"}
if set(res) != EXPECTED:
    sys.exit(f"FAIL 시나리오 집합이 다르다 — 빠짐 {sorted(EXPECTED - set(res))} / "
             f"추가 {sorted(set(res) - EXPECTED)} (fail-closed)")

bad = [f"{k}: {v}" for k, v in res.items() if not v.startswith("RESOLVE")]
if bad:
    print("FAIL — 정착하지 않는 경로가 있다 (화면이 영구히 빈다):")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print(f"PASS ensureLang 정착 {len(res)}종 — " + " · ".join(f"{k}={v.split()[0]}" for k, v in res.items()))
