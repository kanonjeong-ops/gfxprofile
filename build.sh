#!/usr/bin/env bash
# gfxprofile v2 빌드·검사·패키징 — 시스템에 node를 설치하지 않고, 폴더 안에 가둔 툴체인만 쓴다.
#
# 툴체인 실물: ~/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/  (U1에서 확보, 470M)
#   - node는 PATH에 없다(사용자 결정). 여기서만 절대경로로 얹는다.
#   - npm/pnpm 캐시·store·HOME을 전부 그 폴더 안으로 돌려 **홈을 오염시키지 않는다.**
# 툴체인을 다른 경로로 옮겼다면 아래 U1_ROOT만 고치고,
#   pnpm install --offline --force --frozen-lockfile 을 한 번 돌려 .bin 래퍼를 다시 만든다.
#
# 단계: install | check | build | grep | package | test | all
set -euo pipefail

U1_ROOT="${U1_ROOT:-/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle}"
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -d "$U1_ROOT/toolchain" ] || { echo "toolchain 없음: $U1_ROOT" >&2; exit 1; }

# ★ 실사용자 홈을 격리 **전에** 붙잡아 둔다. 아래 HOME 격리는 node·pnpm 캐시를 폴더 안에
#   가두기 위한 것인데, 그것을 모르고 실사용자 홈을 기대하는 코드가 이 프로젝트에서 이미
#   세 번 걸렸다((C) 고아화 경고 · qa 테스트 · 그 전의 사례). 필요한 쪽은 REAL_HOME을 쓴다.
REAL_HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"
export REAL_HOME
export HOME="$U1_ROOT/.u1-home"
export XDG_CACHE_HOME="$U1_ROOT/.u1-cache"
export XDG_DATA_HOME="$U1_ROOT/.u1-data"
export XDG_CONFIG_HOME="$U1_ROOT/.u1-config"
export npm_config_cache="$U1_ROOT/.u1-npm-cache"
export npm_config_prefix="$U1_ROOT/.u1-npm-prefix"
export npm_config_userconfig="$U1_ROOT/.u1-config/npmrc"
export PNPM_HOME="$U1_ROOT/.u1-pnpm"
export COREPACK_HOME="$U1_ROOT/.u1-corepack"
export NODE_REPL_HISTORY="$U1_ROOT/.u1-data/node_repl_history"
export PATH="$U1_ROOT/toolchain/node-v22.23.2-linux-x64/bin:$U1_ROOT/.u1-npm-prefix/bin:$PATH"

cd "$PROJ"

step="${1:-all}"

# ★ 모르는 단계명은 **실패**로 끝낸다.
#   예전엔 아무것도 안 하고 마지막 OK를 찍어 종료 코드 0을 냈다 — `build.sh chek` 같은 오타 하나가
#   "검증 성공"으로 기록된다. 검사가 거짓말을 하면 없느니만 못하다.
case "$step" in
  install|check|build|grep|package|test|all) ;;
  *) echo "알 수 없는 단계: $step (install|check|build|grep|package|test|all)" >&2; exit 2 ;;
esac

run() { [ "$step" = "$1" ] || [ "$step" = "all" ]; }

if run install; then
  echo "== pnpm install =="
  pnpm install
fi

if run check; then
  echo "== tsc --noEmit (추가 플래그 0개로 통과해야 한다) =="
  pnpm exec tsc --noEmit
  echo "tsc EXIT=0"
fi

if run build; then
  echo "== rollup build =="
  pnpm run build
  test -s dist/index.js
  echo "dist/index.js $(stat -c '%s' dist/index.js) bytes"
fi

if run grep; then
  echo "== 불변식 검사 =="
  # ① @decky/ui는 src/deckyui.ts 한 곳에서만 import한다.
  #    ★ 모듈명 문자열이 아니라 **import 구문**을 찾는다. 단순 문자열 검색은 패키지명을 언급한
  #      주석까지 잡아 오탐한다(실제로 오탐했다).
  files=$(grep -rlE '(from|import)[[:space:]]*\(?[[:space:]]*["'"'"']@decky/ui["'"'"']' src | sort | tr '\n' ' ')
  echo "@decky/ui를 import하는 파일: ${files:-<없음>} (src/deckyui.ts 하나여야 한다)"
  [ "${files% }" = "src/deckyui.ts" ] || { echo "불변식 위반" >&2; exit 1; }

  # ③ 일괄 적용 버튼의 활성 조건에 running이 들어가면 안 된다(설계 E1).
  #    들어가는 순간 게임 하나가 켜져 있다는 이유로 **아무것도 적용되지 않고**, 그건
  #    "하나만 거부하고 나머지는 적용"이라는 M1 불변식의 정면 위반이다.
  #    ⚠️ **이 grep이 방어선이라고 믿지 마라.** 파생 변수·헬퍼 함수·다중 중괄호 식을 못 잡는다
  #      (설계 E1 파급 4에서 [미확정]으로 명시). 진짜 방어선은 P2 실기 관찰과
  #      qa/test_apply_all.py다. 이건 **가장 흔한 형태의 실수만** 거른다.
  #    ★ 2026-08-05 QA R6로 **방식을 바꿨다**: 예전의 `disabled={...running}` 정규식은
  #      파생 변수 한 줄로 우회된다(`const blocked = (counts?.running ?? 0) > 0`
  #      → `disabled={... || blocked}`). **금지어를 찾는 대신 허용된 것만 통과시킨다** —
  #      새 식별자를 쓰려면 아래 ALLOWED에 적어야 하므로 몰래 들어올 수 없다.
  python3 - <<'PY3'
import re, pathlib, sys
ALLOWED = {'ready', 'busy'}            # 활성 조건에 들어와도 되는 것. 늘리려면 근거와 함께 여기에.
KEYWORDS = {'true', 'false', 'null', 'undefined'}
bad = []
# ★ 2026-08-06: `disabled` 식별자 허용 목록은 **일괄 적용 버튼**에 대한 규칙이다(E1).
#   게임별 적용 버튼은 "그 프로필이 없으면 비활성"이 정당하므로 같은 잣대를 대면 안 된다 —
#   실제로 P3에서 그렇게 오탐했다. **오탐도 거짓 검사다.**
#   반면 `running` 참조 위치 규칙(아래)은 **전 파일**에 그대로 건다 — 그게 진짜 방어선이다.
BULK = pathlib.Path('src/BulkApplyButton.tsx')
for path in sorted(list(pathlib.Path('src').rglob('*.tsx')) + list(pathlib.Path('src').rglob('*.ts'))):
    text = orig = path.read_text()
    # ⚠️ 마커(`e1-display-only`)는 **주석에 있으므로 원본 줄에서 찾는다.**
    #   주석을 지운 텍스트에서 마커를 찾으면 항상 없다 — 실제로 그렇게 짰다가 정당한 줄이 걸렸다.
    #   아래 치환은 행 수를 보존하므로 두 텍스트의 줄 번호는 그대로 대응된다.
    orig_lines = orig.splitlines()
    text = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)
    text = re.sub(r'//[^\n]*', '', text)
    for m in (re.finditer(r'disabled=\{([^}]*)\}', text) if path == BULK else []):
        expr = m.group(1)
        line = text[:m.start()].count('\n') + 1
        names = {n for n in re.findall(r'[A-Za-z_$][\w$]*', expr) if n not in KEYWORDS}
        extra = names - ALLOWED
        if extra:
            bad.append(f"{path}:{line} disabled={{{expr.strip()}}} — 허용 목록 밖: {sorted(extra)}")
    # ★ 2026-08-05 QA 재인증 R6: 식별자 이름만 보면 **값을 오염**시켜 우회할 수 있다
    #   (`const ready = counts.running ? 0 : counts.dock_ready` → 이름은 그대로 `ready`).
    #   그래서 `running`이 **프론트에 등장할 수 있는 자리 자체를 하나로 묶는다** — 표시 전용이라고
    #   명시한 줄에서만 허용한다. 값 오염을 하려면 어딘가에서 running을 읽어야 하므로 여기서 걸린다.
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        # ★ **값을 읽는 곳만** 잡는다 — 속성 접근(`.running`)과 구조분해(`{ running }`).
        #   타입 선언(`running: boolean;`)까지 잡으면 rpc.ts의 정당한 계약이 위반이 된다
        #   (실제로 그렇게 오탐했다). 오탐도 거짓 검사다 — 다음 사람이 검사를 꺼 버린다.
        #   `runningNote` 같은 파생 이름은 단어 경계로 걸러진다.
        if not (re.search(r'\.running\b', line) or re.search(r'\{[^}]*\brunning\b[^}]*\}\s*=', line)):
            continue
        if "e1-display-only" in orig_lines[i - 1] or "e1-display-only" in orig_lines[max(0, i - 2)]:
            continue
        bad.append(f"{path}:{i} running 참조가 표시 전용 표시 밖에 있다 — {line.strip()[:70]}")
print(f"일괄 버튼 disabled 식별자: 허용={sorted(ALLOWED)} / 위반 {len(bad)}건 (0이어야 한다)")
for b in bad:
    print("  " + b)
sys.exit(1 if bad else 0)
PY3

  # ④ U19 — deckyui.ts의 **import 목록과 self-check(REQUIRED) 목록이 같은가.**
  #    P2에서 컴포넌트가 하나 늘었고(ButtonItem), 설계가 "컴포넌트가 늘 때 판정한다"고 한 자리다.
  #    지금까지는 주석에 "손으로 맞춘다"고 적혀 있었는데, 손으로 맞추는 목록은 언젠가 어긋나고
  #    **어긋나면 self-check가 조용히 그 컴포넌트를 안 본다** — 검사가 있는데 안 보는 상태가 된다.
  #    파일이 하나이고 형식이 고정이라 두 목록을 그대로 뽑아 비교할 수 있다.
  python3 - <<'PY'
import re, pathlib, sys
raw = pathlib.Path('src/deckyui.ts').read_text()

# ★ 주석을 먼저 지운다 (2026-08-05 QA R6). 예전엔 raw 텍스트에 정규식을 걸어 **첫 매치**를
#   집었는데, 그러면 가짜 import를 주석으로 위에 써 두는 것만으로 검사가 엉뚱한 목록을 본다.
#   이 프로젝트에서 grep이 주석을 잡아 오탐한 사고가 이미 두 번 있었다 — 같은 뿌리다.
src = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
src = re.sub(r'//[^\n]*', '', src)

# ★ 2026-08-05 QA 재인증 R6: **첫 import 하나만 보면 안 된다.** 같은 파일에 두 번째
#   `from "@decky/ui"` 를 두면 그 컴포넌트가 self-check 밖으로 빠지는데 검사는 통과했다.
#   전부 모아서 합집합으로 본다.
imports = re.findall(r'(?:import|export)\s*\{([^}]*)\}\s*from\s*["\']@decky/ui["\']', src)   # 재수출도 바인딩을 만든다
m_req = re.search(r'\bconst\s+REQUIRED\b[^=]*=\s*\{([^}]*)\}', src)   # \b앵커: REQUIRED_SNAPSHOT 같은 미끼에 안 걸린다
# ★ P15-E R7: **로컬 재수출 목록도 본다.** 이 파일은 `import {…} from "@decky/ui"` 로 받아
#   `export {…};` 로 내보내는데, 예전 검사는 앞의 둘(import·REQUIRED)만 대조했다.
#   그래서 **재수출에서 한 종을 빼도 EXIT=0**이었다 — 그러면 그 컴포넌트를 쓰는 화면이
#   빌드 단계에서 죽거나(다행) 다른 것으로 갈아치워지는데(불행) 검사는 초록불이다.
#   세 목록을 **동시에** 강제하면 "검사가 있는데 보지 않는" 자리가 남지 않는다.
reexports = re.findall(r'\bexport\s*\{([^}]*)\}\s*;', src)      # `… } from "…"` 는 `;`가 아니라 from이 온다
if not (imports and m_req and reexports):
    sys.exit('U19 검사 불가 — import·REQUIRED·재수출 블록 중 하나를 찾지 못했다 (형식이 바뀌었나?)')

imported = {n.strip() for block in imports for n in block.replace('\n', ' ').split(',') if n.strip()}
exported = {n.strip() for block in reexports for n in block.replace('\n', ' ').split(',') if n.strip()}

# ★ 키만 보지 않는다 (QA R6). `ButtonItem: 딴것` 처럼 값이 어긋나면 self-check가 **엉뚱한 것을**
#   감시하게 되는데 이름만 비교하면 통과한다. 축약 표기(`{ButtonItem}`)만 허용하고,
#   `키: 값` 형태는 키와 값이 같을 때만 인정한다.
required = set()
for item in m_req.group(1).replace('\n', ' ').split(','):
    item = item.strip()
    if not item:
        continue
    if ':' in item:
        key, value = (x.strip() for x in item.split(':', 1))
        if key != value:
            sys.exit(f'U19 위반 — REQUIRED의 {key}가 {value}를 감시한다(이름과 값이 달라 오감시)')
        required.add(key)
    else:
        required.add(item)
print(f"U19 self-check 목록 항등: import {len(imported)}종 / REQUIRED {len(required)}종 / "
      f"재수출 {len(exported)}종")
if imported != required:
    print(f"  import에만: {sorted(imported - required)}")
    print(f"  REQUIRED에만: {sorted(required - imported)}")
    sys.exit("불변식 위반 — @decky/ui import와 self-check 목록이 다르다")
if imported != exported:
    print(f"  import에만: {sorted(imported - exported)}")
    print(f"  재수출에만: {sorted(exported - imported)}")
    sys.exit("불변식 위반 — @decky/ui import와 재수출 목록이 다르다 "
             "(빠진 것은 화면이 못 얻고, 남는 것은 감시 밖이다)")
PY

  # ② decky.migrate_* 는 원본을 rm -rf 한다. 호출도, decky에서 그 이름을 가져오는 것도 금지.
  #    ★ AST로 **decky에 매인 것만** 본다. 이름만 보면 별칭 import를 놓치고(from decky import
  #      migrate_runtime as mv), 무관한 obj.migrate_profile()은 잘못 막는다.
  python3 - <<'PY'
import ast, pathlib, sys
hits = []
for p in list(pathlib.Path('.').glob('main.py')) + list(pathlib.Path('py_modules').rglob('*.py')):
    tree = ast.parse(p.read_text(), filename=str(p))
    aliased = set()
    mod_aliases = {'decky', 'decky_plugin'}
    for node in ast.walk(tree):
        # from decky import migrate_x [as y]  → 별칭까지 추적한다
        if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] == 'decky':
            for a in node.names:
                if a.name.startswith('migrate_'):
                    aliased.add(a.asname or a.name)
                    hits.append(f"{p}:{node.lineno} from decky import {a.name}")
        # `import decky as d` 도 추적한다 — 이름만 보면 이 별칭을 놓친다(리뷰 2-1)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split('.')[0] in ('decky', 'decky_plugin'):
                    mod_aliases.add(a.asname or a.name.split('.')[0])
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
               and f.value.id in mod_aliases and f.attr.startswith('migrate_'):
                hits.append(f"{p}:{node.lineno} {f.value.id}.{f.attr}()")
            elif isinstance(f, ast.Name) and f.id in aliased:
                hits.append(f"{p}:{node.lineno} {f.id}()  # decky.migrate_* 별칭")
print(f"decky migrate_* 사용 = {len(hits)}건 (0이어야 한다)")
for h in hits:
    print("  " + h)
sys.exit(1 if hits else 0)
PY
fi

if run package; then
  # ★ package는 build를 **반드시** 거친다. 예전엔 안 거쳐서, 프론트를 고치고
  #   package만 부르면 옛 dist가 그대로 포장됐다(리뷰 1-3에서 sentinel로 재현됨).
  if [ "$step" = "package" ]; then
    echo "== rollup build (package 선행) =="
    pnpm run build
    test -s dist/index.js
  fi
  echo "== 패키지 =="
  # ★ 빌드와 ZIP을 한 단계로 묶는다. 예전엔 따로였고, 빌드 후 ZIP 갱신을 잊으면
  #   "설치 성공"처럼 보이면서 옛 코드가 설치됐다.
  python3 - <<'PY'
import hashlib, json, os, pathlib, pwd, re, sys, zipfile

proj = pathlib.Path('.').resolve()
# ★ LICENSE는 **배포물의 법적 필수 파일**이다(2026-08-07 마일스톤 R2).
#   package.json이 `license: BSD-3-Clause`를 선언하는데 원문이 배포 ZIP에 없으면
#   그 선언이 근거 없는 주장이 된다. 아래 `missing` 검사가 fail-closed로 막는다 —
#   ship 목록에 넣는 것만으로는 부족하고, 없으면 **패키징 자체가 실패해야** 한다.
ship = ['plugin.json', 'package.json', 'LICENSE', 'main.py', 'dist/index.js']
ship += [str(p) for p in sorted(pathlib.Path('py_modules').rglob('*.py'))] if pathlib.Path('py_modules').is_dir() else []

missing = [f for f in ship if not (proj / f).is_file()]
if missing:
    sys.exit(f"패키지에 넣을 파일이 없다: {missing}")

# (E) 라이선스 정합 — 선언과 원문이 같은 것을 가리켜야 한다
declared = json.loads((proj / 'package.json').read_text()).get('license', '')
license_text = (proj / 'LICENSE').read_text(encoding='utf-8')
if declared != 'BSD-3-Clause':
    sys.exit(f"package.json의 license가 BSD-3-Clause가 아니다: {declared!r}")
if 'BSD 3-Clause License' not in license_text or 'Redistribution and use' not in license_text:
    sys.exit("LICENSE 원문이 BSD-3-Clause 본문으로 보이지 않는다 — 선언과 실물이 어긋난다")

# (F) store metadata — 제출 가능한 구조인가 (2026-08-07 마일스톤 R3)
#   공식 database workflow는 `publish.image`를 그대로 제출값으로 쓰고, 빈 값·잘못된 scheme을
#   실패 처리한다. 우리는 **제출 전에** 그것을 잡는다.
publish = json.loads((proj / 'plugin.json').read_text()).get('publish', {})
image = publish.get('image', '')
if not image:
    sys.exit("plugin.json publish.image가 비어 있다 — 공식 workflow가 제출을 거부한다")
if not image.startswith('https://'):
    sys.exit(f"publish.image가 https:// URL이 아니다: {image!r}")
if not (proj / 'assets' / 'store-image.png').is_file():
    sys.exit("assets/store-image.png가 없다 — publish.image가 가리킬 실물이 리포에 있어야 한다")
# ★ 아직 확정되지 않은 값은 **지어낸 최종값처럼 두지 않는다.** 이 프로젝트의 자리표시자
#   규약(`__NAME__`)을 그대로 써서 *검사 가능한 형태로* 미확정임을 표시한다.
store_placeholders = sorted(set(re.findall(r'__[A-Z][A-Z0-9_]*__', image)))
if store_placeholders:
    if os.environ.get('GFXP_STORE_READY') == '1':
        sys.exit(f"publish.image에 미확정 자리표시자가 남았다: {store_placeholders} "
                 "— 공개 저장소 URL을 확정한 뒤 다시 패키징하라(스토어 제출 게이트)")
    print(f"⚠️  STORE_SUBMISSION_BLOCKED=1 publish.image 자리표시자 {store_placeholders} — "
          "로컬 설치에는 지장이 없다. 스토어 제출 전에 공개 저장소 URL을 확정하고 "
          "`GFXP_STORE_READY=1 bash build.sh package`로 잠금을 확인하라")
else:
    print("STORE_SUBMISSION_BLOCKED=0 publish.image 확정됨")

# ── 식별자와 표시명은 다른 것이다 (설계 E19) ────────────────────────────────
# IDENT : 배포 ZIP 최상위 폴더명 = 런타임 경로(~/homebrew/{data,settings,logs}/<IDENT>).
#         **정본이 여기다.** 절대 plugin.json에서 파생시키지 않는다 — 반대 방향(검사)만 있다.
# name  : 표시명. plugin.json의 name이 정본이고 로더·스토어가 읽는 프로토콜 값이다.
# 둘이 우연히 같았던 시절이 있었고, 그때 build.sh가 폴더명을 name에서 파생시키고 있었다.
# 표시명을 바꾸는 순간 런타임 경로가 따라 바뀌어 **사용자 데이터가 고아가 된다.**
IDENT = 'gfxprofile'
name = json.loads((proj / 'plugin.json').read_text())['name']
pkg_name = json.loads((proj / 'package.json').read_text())['name']
version = json.loads((proj / 'package.json').read_text())['version']

# (D) package.json 정합 — IDENT의 또 다른 사본이라 손으로 맞아야 하는 자리다.
if pkg_name != IDENT:
    sys.exit(f"package.json의 name({pkg_name})이 IDENT({IDENT})와 다르다")

out = proj / 'pkg' / f'{IDENT}.zip'
out.parent.mkdir(exist_ok=True)

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in ship:
        z.write(proj / f, f'{IDENT}/{f}')   # ★ name이 아니라 IDENT. 이 한 줄이 고아화를 막는다

# 검증: 아카이브 무결성 + RPC 생존
#   ※ 예전의 "최상위 폴더 == name" 검사는 제거했다(E19 (A)). tops는 위 z.write가 만드는
#     f'{IDENT}/{f}'의 첫 세그먼트라 구조적으로 다른 값을 가질 수 없었다 — FAIL하는 입력을
#     만들 수 없는 검사는 검사가 아니라 장식이고, 이 프로젝트는 그 인상 때문에 QA를 네 번 뚫렸다.
with zipfile.ZipFile(out) as z:
    bad = z.testzip()
    if bad:
        sys.exit(f"ZIP 손상: {bad}")
    pass

# (B) RPC 생존 검사 — 로직 정본은 qa/check_zip_manifest.py 하나다(설계 E19).
#     ★ 여기 인라인으로 두면 **FAIL 입력을 만들 수 없는 검사**가 된다(2026-08-06 QA 지적 ①):
#       package는 항상 rollup을 선행하므로 zip 안 dist가 늘 갓 구운 것이라 두 값이 구조적으로 같다.
#       임의 ZIP을 받는 함수로 빼야 테스트가 **변조 ZIP으로 실제 반증**할 수 있다.
sys.path.insert(0, str(proj / 'qa'))
from check_zip_manifest import verify as _verify_zip   # noqa: E402
try:
    _verify_zip(out, IDENT)
except ValueError as e:
    sys.exit(str(e))

# (C) 고아화 사전 경고 — 차단하지 않는다(다른 기기에서 빌드할 수 있다)
# ★ Path.home()을 쓰면 안 된다 — 이 스크립트는 HOME을 툴체인 폴더로 격리한다(위 export HOME).
#   실제로 그 때문에 이 경고가 **조용히 건너뛰어졌다**(2026-08-06 구현 중 발견).
#   pwd는 환경변수가 아니라 passwd 항목을 보므로 격리의 영향을 받지 않는다.
real_home = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)
installed = real_home / 'homebrew' / 'plugins' / IDENT / 'plugin.json'
if installed.is_file():
    try:
        old = json.loads(installed.read_text()).get('name')
        if old != name:
            print(f"⚠️  설치본의 표시명({old})이 이번 표시명({name})과 다르다 — "
                  f"설치 전에 Decky UI에서 기존 {IDENT}를 **먼저 제거**하라. "
                  f"그러지 않으면 같은 데이터 폴더를 공유하는 두 번째 백엔드가 뜬다 (E19 S2)")
    except Exception as e:
        # 조용히 넘기지 않는다 — 검사가 안 돌았다는 사실 자체가 정보다
        print(f"(고아화 경고 검사를 못 돌렸다: {type(e).__name__} {e})")

digest = hashlib.sha256(out.read_bytes()).hexdigest()
(proj / 'pkg' / f'{IDENT}.zip.sha256').write_text(digest + '\n')

# 설치 스크립트를 해시를 박아 생성한다. 로더가 이 해시를 검증하므로,
# 손상되거나 낡은 ZIP이 기존 설치를 지운 뒤 실패하는 경로가 닫힌다.
# ★ NAME·VERSION도 코드젠한다 — 로더는 **표시명**으로 설치 프롬프트를 매칭하므로(E19),
#   손으로 맞추면 표시명을 바꿀 때마다 어긋나 설치가 죽는다. 드리프트를 구조로 없앤다.
tmpl = (proj / 'install.tmpl.js').read_text()
generated = (tmpl.replace('__ZIP_PATH__', str(out))
                 .replace('__ZIP_SHA256__', digest)
                 .replace('__PLUGIN_NAME__', name)
                 .replace('__PLUGIN_VERSION__', version))
# ★ QA 지적 ②: 예전엔 큰따옴표만 봤다. JS에서 따옴표 선택은 취향이라
#   홑따옴표·백틱으로 넣은 자리표시자가 그대로 새어 나갔다. 따옴표를 보지 않는다.
left = sorted(set(re.findall(r'__[A-Z][A-Z0-9_]*__', generated)))
if left:      # 템플릿에 자리표시자가 늘었는데 치환 코드를 안 늘린 사고를 잡는다
    sys.exit(f"pkg/install.js에 치환되지 않은 자리표시자가 남았다: {left}")
(proj / 'pkg' / 'install.js').write_text(generated)
print(f"pkg/{IDENT}.zip {out.stat().st_size} bytes")
print(f"sha256 {digest}")
print(f"수록 {len(ship)}개: {', '.join(ship)}")
print("pkg/install.js 생성됨 (해시 박힘)")
PY
fi

# ★ 2026-08-06 QA 지적 ⑧으로 신설. 그전까지 `build.sh all`은 **qa 테스트를 한 개도 안 돌리면서**
#   OK를 찍었다. 다른 방어선이 전부 "테스트가 돈다"를 전제하는데 그걸 부르는 건 사람의 기억뿐이었고,
#   이 프로젝트는 같은 구조(오타 단계명이 성공으로 기록되던 것)를 이미 한 번 고친 적이 있다.
#   ⚠️ test는 package 뒤에 온다 — test_build_ident_split.py가 pkg/ 산출물을 검사한다.
if run test; then
  echo "== qa 테스트 =="
  fails=0
  for t in qa/test_*.py; do
    # ⚠️ 실사용자 홈으로 돌린다 — 테스트는 실제 Steam registry·M1 경로 같은 **시스템 실물**을
    #   본다. 격리된 HOME에서 돌리면 test_lang_detect가 폴백으로 떨어져 거짓 FAIL이 난다.
    if env HOME="$REAL_HOME" python3 "$t" >/tmp/gfxp-test.log 2>&1; then
      printf '  PASS %s\n' "$(basename "$t")"
    else
      printf '  FAIL %s\n' "$(basename "$t")"
      sed 's/^/       /' /tmp/gfxp-test.log | head -12
      fails=$((fails + 1))
    fi
  done
  rm -f /tmp/gfxp-test.log
  [ "$fails" -eq 0 ] || { echo "qa 테스트 $fails종 실패" >&2; exit 1; }
fi

echo "OK"
