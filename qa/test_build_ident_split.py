#!/usr/bin/env python3
"""식별자(IDENT) ↔ 표시명(NAME) 분리 검사 — 설계 E19.

왜 필요한가:
    2026-08-06 전까지 이 둘은 **우연히 같은 문자열**이었고, 그래서 `build.sh`가 ZIP 최상위
    폴더명을 `plugin.json`의 name에서 파생시키고 있어도 아무도 이상하게 보지 않았다.
    D8이 표시명을 `eGPU Game Config Swap`으로 바꾸면서 둘이 처음으로 갈렸다 — 그 상태에서
    옛 코드로 패키징하면 런타임 경로가 표시명이 되어 **사용자 데이터(registry·profiles·backups)가
    고아가 된다.**

    기존 QA 8종은 이 결합을 하나도 감지하지 못했다(E19 § QA 공백).

검사 4종 — 전부 반증 케이스가 정의돼 있다:
    1. pkg/install.js에 미치환 자리표시자가 없다
       ↳ 반증: install.tmpl.js에 새 __XXX__를 넣고 치환 코드를 그대로 두면 FAIL
    2. pkg/install.js의 NAME == plugin.json의 name (**표시명**이지 IDENT가 아니다)
       ↳ 반증: install.tmpl.js의 NAME을 옛 식별자로 되돌리면 FAIL
    3. ZIP 안 dist/index.js에 박힌 manifest.name == ZIP 안 plugin.json의 name (RPC 생존)
       ↳ 반증: **이 테스트가 매 실행마다 직접 한다** — 옛 이름을 박은 ZIP 사본을 만들어
         qa/check_zip_manifest.py가 거부하는지 확인한다.
         ⚠️ 예전 독스트링은 "낡은 dist로 덮어쓰고 package하면 FAIL"이라고 적었는데 **거짓이었다** —
         package가 항상 rollup을 선행해 dist를 새로 구우므로 그 케이스는 만들 수조차 없었다
         (2026-08-06 QA 지적 ①·⑥). 반증은 문서가 아니라 실행으로 증명한다.
    4. package.json의 name == IDENT
       ↳ 반증: package.json의 name을 바꾸면 FAIL

이 파일은 `build.sh package`가 이미 돌아 pkg/가 만들어져 있다고 전제한다.
"""
import json
import pathlib
import re
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDENT = "gfxprofile"          # build.sh의 정본과 같아야 한다(아래 5번이 그것을 검사한다)

fail = []


def check(cond, msg):
    if not cond:
        fail.append(msg)


zip_path = ROOT / "pkg" / f"{IDENT}.zip"
install_js = ROOT / "pkg" / "install.js"

if not zip_path.is_file() or not install_js.is_file():
    sys.exit(f"SKIP 아님 — 먼저 `build.sh package`를 실행해야 한다 (없음: {zip_path.name}/{install_js.name})")

manifest_name = json.loads((ROOT / "plugin.json").read_text())["name"]
pkg_json = json.loads((ROOT / "package.json").read_text())

# 1. 미치환 자리표시자
gen = install_js.read_text()
left = sorted(set(re.findall(r'__[A-Z][A-Z0-9_]*__', gen)))   # 따옴표 종류에 의존하지 않는다(QA 지적 ②)
check(not left, f"pkg/install.js에 미치환 자리표시자: {left}")

# 2. install.js의 NAME == 표시명
m = re.search(r'const\s+NAME\s*=\s*"([^"]*)"', gen)
check(m is not None, "pkg/install.js에서 NAME 리터럴을 찾지 못했다 (fail-closed)")
if m:
    check(m.group(1) == manifest_name,
          f"install.js의 NAME({m.group(1)!r})이 plugin.json의 name({manifest_name!r})과 다르다 — "
          f"로더가 설치 프롬프트를 매칭하지 못해 설치가 죽는다")

# 3. ZIP 안 번들의 baked manifest.name == plugin.json의 name  (RPC 생존)
#    ★ 로직은 qa/check_zip_manifest.py 하나에만 있다. 여기서 그 함수를 부르고,
#      **변조한 ZIP 사본으로 실제 반증**까지 돌린다(2026-08-06 QA 지적 ①).
sys.path.insert(0, str(ROOT / "qa"))
from check_zip_manifest import verify as verify_zip   # noqa: E402

with zipfile.ZipFile(zip_path) as z:
    tops = {n.split("/")[0] for n in z.namelist()}
    check(tops == {IDENT}, f"ZIP 최상위 폴더가 {tops} — {IDENT} 하나여야 한다 (런타임 경로가 여기서 정해진다)")
    inner_name = json.loads(z.read(f"{IDENT}/plugin.json"))["name"]
    check(inner_name == manifest_name, "ZIP 안 plugin.json이 원본과 다르다")

try:
    verify_zip(zip_path, IDENT)
except ValueError as e:
    fail.append(f"RPC 생존 검사 실패: {e}")

# ★ 자기 반증 — 이 검사가 **지금도 잡는지** 매 실행마다 확인한다.
#   낡은 번들(옛 이름이 박힌 dist)을 넣은 ZIP 사본을 만들어 verify_zip이 거부해야 한다.
#   예전 판(인라인 검사)은 package가 항상 dist를 새로 구워 **이 케이스를 만들 수조차 없었다** —
#   그런데 독스트링에는 반증이 되는 것처럼 적혀 있었다. 문서가 아니라 실행으로 증명한다.
def _mutated_copy(dst, replace_name):
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(dst, "w") as out:
        for item in src.namelist():
            data = src.read(item)
            if item == f"{IDENT}/dist/index.js":
                text = data.decode("utf-8", "replace")
                data = text.replace(f'manifest = {{"name":"{manifest_name}"}}',
                                    f'manifest = {{"name":"{replace_name}"}}').encode()
            out.writestr(item, data)

with tempfile.TemporaryDirectory() as td:
    proofs = []
    for wrong, label in (('gfxprofile', "옛 이름이 박힌 낡은 번들"),
                         ('전혀 다른 이름', "무관한 이름")):
        mut = pathlib.Path(td) / f"mut-{abs(hash(wrong))}.zip"
        _mutated_copy(mut, wrong)
        try:
            verify_zip(mut, IDENT)
            proofs.append(f"{label}을 통과시켰다")
        except ValueError:
            pass
    check(not proofs, "이 검사는 무효다 — 다음을 검출하지 못했다: " + "; ".join(proofs))

# 4-a. src/version.ts의 PLUGIN_VERSION == package.json의 version (정본 하나에서 파생되는지)
vt = (ROOT / "src" / "version.ts").read_text()
vm = re.search(r'PLUGIN_VERSION\s*=\s*"([^"]+)"', vt)
check(vm is not None, "src/version.ts에서 PLUGIN_VERSION을 찾지 못했다 (fail-closed)")
if vm:
    check(vm.group(1) == pkg_json["version"],
          f"src/version.ts의 버전({vm.group(1)!r})이 package.json({pkg_json['version']!r})과 다르다")

# 4. package.json의 name == IDENT
check(pkg_json["name"] == IDENT,
      f"package.json의 name({pkg_json['name']!r})이 IDENT({IDENT!r})와 다르다")

# 5. build.sh의 IDENT 리터럴이 이 파일의 상수와 같은지 (두 곳에 사는 값이라 어긋날 수 있다)
bs = (ROOT / "build.sh").read_text()
bm2 = re.search(r"^IDENT\s*=\s*'([^']+)'", bs, re.M)
check(bm2 is not None, "build.sh에서 IDENT 상수를 찾지 못했다 (fail-closed)")
if bm2:
    check(bm2.group(1) == IDENT, f"build.sh의 IDENT({bm2.group(1)!r})가 이 테스트의 상수({IDENT!r})와 다르다")

if fail:
    print("FAIL")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print(f"PASS 식별자/표시명 분리 5종 — IDENT={IDENT!r} / 표시명={manifest_name!r}")
