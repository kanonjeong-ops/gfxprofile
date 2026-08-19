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
# 릴리스 명령(단계가 아니다 — `all`에 섞이지 않는다): bump <버전> | release   → 절차는 RELEASE.md
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
  install|check|build|grep|package|test|all|bump|release) ;;
  *) echo "알 수 없는 단계: $step (install|check|build|grep|package|test|all|bump <버전>|release)" >&2; exit 2 ;;
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

  # ⑤ DialogButton JSX의 직접 사용은 src/popup.tsx 한 파일만 허용한다(설계 §4-G 2항, 10판).
  #    ★ 왜: Steam 본체 CSS가 `button.DialogButton { width:100% }`를 전역으로 걸고, 그 오염은
  #      블록 부모만이 아니라 **flex 자식에도** 발현한다(실측 — 행 버튼 584.7px, 게임 이름 0px
  #      붕괴). 각 버튼이 인라인 width로 눌러 막는 방식은 **다음에 추가되는 버튼**을 못 지킨다.
  #      그래서 폭을 아는 자리를 `PopupButton` 래퍼 하나로 모으고, 그 문 밖으로 나가는 길을
  #      여기서 닫는다 — 검사로 막던 것을 구조로 없앤 E1과 같은 문법이다.
  #    ★ 파일 단위로 잠근다(위 ① @decky/ui 단일 관문과 동형). **파일 밖 예외 목록은 두지
  #      않는다** — 목록을 두는 순간 그 목록이 다음 라운드의 구멍이 된다.
  #      popup.tsx 안의 두 자리(래퍼 정의 · 폴백 오버레이 푸터 2버튼)는 그 파일 주석이 사유를 진다.
  #    ⚠️ **주석을 먼저 지우고** 여는 JSX 태그만 본다(게이트 ①과 같은 문법). 단순 문자열 검색은
  #      `// … <DialogButton …` 같은 설명 주석까지 잡아 위반으로 오판한다 — 이 프로젝트는
  #      같은 오탐을 이미 두 번 겪었고(①의 주석), **오탐도 거짓 검사다**: 다음 사람이 검사를 끈다.
  #    ★ 문 하나의 범위 = **직접 여는 태그**다. `import { DialogButton as X }` 같은 별칭 우회는
  #      막지 않는다 — 그건 실수로 넘을 수 있는 문턱이 아니라 **고의**이고, 고의는 코드리뷰의
  #      몫이다(E1 grep의 "가장 흔한 형태의 실수만 거른다"와 같은 처분).
  btnfiles=$(python3 - <<'PY'
import pathlib, re
hits = []
for p in sorted(list(pathlib.Path('src').rglob('*.tsx')) + list(pathlib.Path('src').rglob('*.ts'))):
    src = p.read_text()
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)   # 블록 주석
    src = re.sub(r'//[^\n]*', '', src)                # 줄 주석
    if re.search(r'<DialogButton[\s/>]', src):
        hits.append(str(p))
print(' '.join(hits))
PY
)
  echo "DialogButton을 직접 그리는 파일: ${btnfiles:-<없음>} (src/popup.tsx 하나여야 한다)"
  [ "$btnfiles" = "src/popup.tsx" ] || { echo "불변식 위반 — 팝업 버튼은 PopupButton 래퍼로만 그린다(§4-G)" >&2; exit 1; }

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

  # ⑥ U5 — `store.save_registry(`를 **직접** 부르는 곳은 `main.py`의 래퍼 정의 1곳뿐이다.
  #    ★ 왜 검사가 필요한가: 레지스트리 버전 가드(문 ②)는 래퍼 `_save_registry` 안에 있다.
  #      교체를 한 곳이라도 빠뜨리면 그 route만 가드 밖으로 새는데, **정상 데이터에서는 아무
  #      증상이 없다** — 더 새 버전이 만든 데이터를 만나야 드러나고, 그때는 이미 뭉갠 뒤다.
  #      10곳 중 하나만 빠져도 아래 카운트가 2 이상이 되어 그 자리에서 잡힌다.
  #    ★ 문자열이 아니라 **AST의 Call 노드**를 센다. 주석·독스트링은 Call을 만들 수 없으므로
  #      이 프로젝트가 두 번 겪은 "주석에 오탐" 계열이 원리적으로 생기지 않는다(게이트 ②와 같은 문법).
  python3 - <<'PY'
import ast, pathlib, sys
tree = ast.parse(pathlib.Path('main.py').read_text(), filename='main.py')
wrapper = next((n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == '_save_registry'), None)
if wrapper is None:
    sys.exit("불변식 위반 — main.py에 `_save_registry` 래퍼가 없다(문 ②가 통째로 사라졌다)")
hits = [n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == 'save_registry'
        and isinstance(n.func.value, ast.Name) and n.func.value.id == 'store']
inside = [ln for ln in hits if wrapper.lineno <= ln <= (wrapper.end_lineno or wrapper.lineno)]
print(f"main.py의 store.save_registry() 직접 호출 = {len(hits)}곳 "
      f"(래퍼 정의 안 {len(inside)}곳 — 1/1이어야 한다)")
for ln in hits:
    print(f"  main.py:{ln}")
if len(hits) != 1 or len(inside) != 1:
    sys.exit("불변식 위반 — 영속화는 `_save_registry` 래퍼 하나만 지나야 한다 (U5 문 ②)")
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
import hashlib, json, os, pathlib, pwd, re, subprocess, sys, zipfile

proj = pathlib.Path('.').resolve()
# ★ LICENSE는 **배포물의 법적 필수 파일**이다(2026-08-07 마일스톤 R2).
#   package.json이 `license: Unlicense`를 선언하는데 원문이 배포 ZIP에 없으면
#   그 선언이 근거 없는 주장이 된다. 아래 `missing` 검사가 fail-closed로 막는다 —
#   ship 목록에 넣는 것만으로는 부족하고, 없으면 **패키징 자체가 실패해야** 한다.
ship = ['plugin.json', 'package.json', 'LICENSE', 'THIRD-PARTY-NOTICES.md',
        'licenses/LGPL-2.1.txt', 'main.py', 'dist/index.js']
ship += [str(p) for p in sorted(pathlib.Path('py_modules').rglob('*.py'))] if pathlib.Path('py_modules').is_dir() else []

# ★ 존재만 보면 **0바이트 파일이 그대로 실린다**(2026-08-19 QA 재심 신규). ZIP의 testzip()은
#   CRC만 보고, RPC 검사는 plugin.json·dist/index.js만 읽는다 — 빈 main.py를 아무도 못 잡았다.
bad = [f for f in ship if not (proj / f).is_file() or (proj / f).stat().st_size == 0]
if bad:
    sys.exit(f"패키지에 넣을 파일이 없거나 비어 있다: {bad}")

# ★ `py_modules`는 고정 목록이 아니라 rglob 열거다 — **파일이 삭제되면 목록에서 조용히 빠지고**
#   위 검사는 그 사실을 알 길이 없다(빠진 것은 검사 대상도 아니다). 손으로 쓰는 목록을 따로
#   만들면 같은 수를 두 곳에 적는 드리프트가 생기므로 **git 인덱스를 명세로 쓴다**:
#   삭제하면 추적 목록과 어긋나 즉사하고, `git rm`으로 지운 의도적 제거는 둘이 함께 움직여
#   자연 통과하며 그 변경은 diff에 보인다. 추적 안 된 새 .py가 배포물에 실리는 경로도 함께 닫힌다.
r = subprocess.run(['git', '-C', str(proj), 'ls-files', '--', 'py_modules'], capture_output=True)
if r.returncode != 0:
    sys.exit("git 추적 목록을 읽을 수 없다 — py_modules 명세를 대조할 수 없으므로 거부한다")
tracked = {x for x in r.stdout.decode().split() if x.endswith('.py')}
found = {str(x) for x in pathlib.Path('py_modules').rglob('*.py')}
if tracked != found:
    sys.exit("py_modules 실물과 git 추적 목록이 다르다\n"
             f"  추적에만 있다(삭제됨?): {sorted(tracked - found)}\n"
             f"  실물에만 있다(미추적): {sorted(found - tracked)}")

# (E) 라이선스 정합 — 선언과 원문이 같은 것을 가리켜야 한다
#   ★ 존재 검사만으로는 부족하다(2026-08-19 QA A-5·A-6): `missing`은 경로가 일반 파일인지만
#     보므로 **0바이트 파일도, 부분 문자열만 든 가짜 본문도 통과**했다. 표준 문안은 고칠 일이
#     없으므로 **전문 지문**으로 못박는다 — 이것이 "표준 문안 수정 금지"라는 결정에 맞는 도구다.
LICENSE_SHA256 = 'cdaa0d66b48ff2687d17784d18e7f21683153f6020b990f167cf2154d907674d'   # Unlicense 전문
LGPL_SHA256 = '38965778962143b687faff3a5b69ef22dd228e0ca4f5a3752893e016ede87c6a'      # LGPL-2.1 전문 504줄

declared = json.loads((proj / 'package.json').read_text()).get('license', '')
if declared != 'Unlicense':
    sys.exit(f"package.json의 license가 Unlicense가 아니다: {declared!r}")
for path, want, what in ((proj / 'LICENSE', LICENSE_SHA256, 'LICENSE(Unlicense 전문)'),
                         (proj / 'licenses/LGPL-2.1.txt', LGPL_SHA256, 'licenses/LGPL-2.1.txt(LGPL-2.1 전문)')):
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != want:
        sys.exit(f"{what}이 정본과 다르다 — 선언과 실물이 어긋난다\n  기록 {want}\n  실물 {got}")

# 고지 파일은 앞으로도 고칠 파일이라 지문을 고정하지 않는다 — 대신 **약속이 살아 있는지** 본다.
#   THIRD-PARTY-NOTICES.md는 "사본이 licenses/LGPL-2.1.txt에 있다"고 약속하는 문서이므로,
#   비어 있거나 대상을 잃으면 그 약속이 거짓이 된다.
notices = (proj / 'THIRD-PARTY-NOTICES.md').read_text(encoding='utf-8')
missing_terms = [t for t in ('@decky/api', 'LGPL', 'licenses/LGPL-2.1.txt') if t not in notices]
if missing_terms:
    sys.exit(f"THIRD-PARTY-NOTICES.md가 고지해야 할 것을 담고 있지 않다: {missing_terms}")

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

# ★★ **검사는 엔진 같은 핵심 기능에만 만든다**(사용자 결정 2026-08-15). UI는 검사로 잡지 않고
#   **실기에서 직접 눌러 확인한다.**
#   근거: 실기에서 나온 결함 5건 중 이 검사들이 잡을 수 있었던 것이 0건이었다 — 패드 좌우 이동·
#   목록 잘림·경로 넘침은 실물 Steam에서만 드러나고, 적용·복원 두 건은 코드가 아니라 **설계**가
#   틀린 것이라 어떤 검사를 짜도 초록불이 나온다. 화면 프로브(`*_probe.cjs`)와 UI·문구 테스트는
#   그래서 전량 삭제했다. 남은 것은 **데이터를 실제로 쓰는 경로**(적용·복원·삭제·초기화·토큰·
#   코드 계약)와 패키징 무결성뿐이다 — 여기는 틀리면 사용자 파일이 조용히 사라진다.
if run test; then
  echo "== 엔진 검사 =="
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
  [ "$fails" -eq 0 ] || { echo "엔진 검사 $fails종 실패" >&2; exit 1; }
fi

# ══ 릴리스 명령 (`bump` / `release`) ═════════════════════════════════════════
# ★ `run()`을 쓰지 않고 **직접 비교**한다. 그래서 이 둘은 구조적으로 `all`에 섞이지 않는다 —
#   `bash build.sh all`이 커밋하거나 게시하는 일은 일어날 수 없다.
# ★ 절차 전문은 RELEASE.md. 여기 있는 것은 그 절차의 기계 부분뿐이다.
if [ "$step" = "bump" ] || [ "$step" = "release" ]; then
  # ★★ git·gh는 **실사용자 홈으로** 돌린다. 이 스크립트는 node·pnpm 캐시를 폴더 안에 가두려고
  #   HOME·XDG_*를 통째로 격리하는데, 그 격리 안에는 **커밋 신원(~/.gitconfig)도 gh 인증
  #   (~/.config/gh)도 SSH 키도 없다.** 그대로 두면 bump는 "당신이 누구인지 모르겠다"로 죽고,
  #   release는 로그인해 두고도 인증이 없다고 하며, push는 키를 못 찾는다.
  #   격리를 모르고 실사용자 홈을 기대하는 코드에 이 프로젝트가 이미 세 번 걸렸다(위 REAL_HOME 주석).
  #   **한 곳에서만 감싸 두면 호출부가 이것을 기억할 필요가 없다** — 잊을 수 있는 자리를 없앤다.
  #   ⚠️ `env`는 **외부 프로세스**라 PATH에서 진짜 실행 파일을 찾는다 — 함수 재귀가 아니다.
  git() { env HOME="$REAL_HOME" XDG_CONFIG_HOME="$REAL_HOME/.config" git "$@"; }
  gh()  { env HOME="$REAL_HOME" XDG_CONFIG_HOME="$REAL_HOME/.config" gh  "$@"; }
fi

if [ "$step" = "bump" ]; then
  # ★ 버전 두 사본(package.json·src/version.ts) 갱신을 **python 한 트랜잭션**으로 한다.
  #   셸 `sed`로 하면 미적중이 조용히 성공으로 지나가고(0건 치환도 종료 코드 0이다),
  #   둘 중 하나만 바뀐 **반쪽 상태**가 남는다. 여기서는 그 둘이 구조적으로 불가능하다:
  #   적중 횟수 1을 단언하고, **둘 다 성공한 뒤에야** 파일을 쓴다.
  python3 - "${2:-}" <<'PY'
import json
import pathlib
import re
import subprocess
import sys

ver = sys.argv[1] if len(sys.argv) > 1 else ""
if not ver:
    print("사용법: bash build.sh bump <버전>   (예: bash build.sh bump 0.2.0)", file=sys.stderr)
    raise SystemExit(2)
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", ver):
    print(f"버전 형식이 아니다: {ver!r} — MAJOR.MINOR.PATCH", file=sys.stderr)
    raise SystemExit(1)


def key(v):
    return tuple(int(x) for x in v.split("."))


# ★ 태그 **삼분법** — 조회 실패와 「아직 없다」는 다른 상태다(fence A4와 같은 원칙).
#   둘을 뭉치면 git이 죽은 날 하향 검사가 조용히 생략된다.
r = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True)
if r.returncode != 0:
    print("태그 조회 실패 — git 상태를 확인하라", file=sys.stderr)
    raise SystemExit(1)
tags = [t for t in r.stdout.decode().split() if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", t)]
if not tags:
    print(f"직전 릴리스 태그 없음 — 첫 릴리스로 간주, 버전 하향 검사 생략 "
          f"(v{ver}이 최초 태그가 된다)")
else:
    latest = max(tags, key=lambda t: key(t[1:]))
    if key(ver) <= key(latest[1:]):
        print(f"버전이 직전 릴리스 태그보다 크지 않다: {ver} <= {latest[1:]}", file=sys.stderr)
        raise SystemExit(1)

# ★ CHANGELOG 절을 **여기서** 본다. 잊음을 가장 싼 시점에 잡는 것이고, release는 이 절을
#   그대로 릴리스 노트로 오려 쓴다 — 없으면 release가 게시 직전에 멈춘다.
changelog = pathlib.Path("CHANGELOG.md")
if not changelog.is_file():
    print("CHANGELOG.md가 없다", file=sys.stderr)
    raise SystemExit(1)
if not re.search(r"^## %s( |$)" % re.escape(ver), changelog.read_text(encoding="utf-8"),
                 flags=re.M):
    print(f"CHANGELOG.md에 `## {ver}` 절이 없다 — 먼저 쓰고 다시 부르라", file=sys.stderr)
    raise SystemExit(1)

pkg_path = pathlib.Path("package.json")
vts_path = pathlib.Path("src/version.ts")
pkg_text = pkg_path.read_text(encoding="utf-8")
vts_text = vts_path.read_text(encoding="utf-8")

pkg_new, n_pkg = re.subn(r'("version"\s*:\s*")[0-9]+\.[0-9]+\.[0-9]+(")',
                         lambda m: m.group(1) + ver + m.group(2), pkg_text)
vts_new, n_vts = re.subn(r'(PLUGIN_VERSION\s*=\s*")[0-9]+\.[0-9]+\.[0-9]+(")',
                         lambda m: m.group(1) + ver + m.group(2), vts_text)
for name, n in (("package.json", n_pkg), ("src/version.ts", n_vts)):
    if n != 1:
        print(f"{name}의 버전 자리를 정확히 1곳 찾지 못했다(찾은 곳 {n}) — "
              f"아무것도 쓰지 않았다", file=sys.stderr)
        raise SystemExit(1)
# ★ 치환 횟수만 보면 **엉뚱한 값이 들어가도** 통과한다. 새 값을 그 자리에서 되읽어 단언한다.
if json.loads(pkg_new).get("version") != ver:
    print("package.json의 새 version이 기대값과 다르다 — 아무것도 쓰지 않았다", file=sys.stderr)
    raise SystemExit(1)
if not re.search(r'PLUGIN_VERSION\s*=\s*"%s"' % re.escape(ver), vts_new):
    print("src/version.ts의 새 값이 기대와 다르다 — 아무것도 쓰지 않았다", file=sys.stderr)
    raise SystemExit(1)

pkg_path.write_text(pkg_new, encoding="utf-8")
vts_path.write_text(vts_new, encoding="utf-8")
print(f"버전 갱신: package.json · src/version.ts → {ver}")
PY
  ver="$2"
  git add package.json src/version.ts CHANGELOG.md
  git commit -q -m "release: v$ver"
  echo "커밋했다: release: v$ver   (push는 하지 않았다 — 다음은 bash build.sh release)"
fi

if [ "$step" = "release" ]; then
  ver=$(python3 -c 'import json; print(json.load(open("package.json"))["version"])')
  [ -n "$ver" ] || { echo "package.json에서 버전을 읽지 못했다" >&2; exit 1; }

  # ① 재료 확인 — 게시 **전에** 다 있는지부터 본다.
  if [ -n "$(git status --porcelain)" ]; then
    echo "작업트리가 깨끗하지 않다 — 먼저 커밋하라 (bash build.sh bump <버전>)" >&2
    git status --short >&2
    exit 1
  fi
  # CHANGELOG의 `## <버전>` 절 본문 = 릴리스 노트의 재료. 절 머리글은 싣지 않는다.
  #   `sed '/./,$!d'`는 절 머리글 바로 아래의 **빈 줄을 떨어낸다**(뒤쪽 빈 줄은 $( )가 이미 먹는다).
  notes_body=$(awk -v v="$ver" 'BEGIN{gsub(/\./,"\\.",v)} $0 ~ ("^## " v "( |$)"){f=1;next} /^## /{f=0} f' CHANGELOG.md | sed -e '/./,$!d')
  [ -n "${notes_body//[[:space:]]/}" ] || { echo "CHANGELOG.md에 ## $ver 절이 없다" >&2; exit 1; }

  # ★ 노트 조립은 **함수 하나**다 — DRY와 실제 게시가 같은 코드를 지난다.
  #   두 벌로 두면 DRY에서 본 것과 다른 것이 게시된다.
  assemble_notes() {
    local digest ai
    digest=$(cat pkg/gfxprofile.zip.sha256)
    # ★ AI 고지의 **정본은 README.md 하나**다. 여기에 문구를 복제하면 두 곳이 갈라진다.
    #   ⚠️ `### About AI use`가 **README의 맨 끝 절**이라는 사실에 기댄다(그 아래를 전부 싣는다) —
    #     뒤에 절을 더하면 그것까지 노트에 실린다. 절을 추가할 때 이 자리를 같이 본다.
    ai=$(awk '/^### About AI use$/{f=1} f' README.md)
    [ -n "$ai" ] || { echo "README.md에 '### About AI use' 절이 없다 — 배포 고지가 빠진다" >&2; exit 1; }
    { printf '%s\n\n' "$notes_body"
      printf 'SHA-256 (gfxprofile.zip): %s\n\n' "$digest"
      printf '%s\n' "$ai"
    } > pkg/release-notes.md
  }

  # ② DRY — **지금 브랜치에서** 검사와 노트 조립까지만. checkout·merge·tag·push·gh 전부 안 한다.
  if [ "${GFXP_RELEASE_DRY:-}" = "1" ]; then
    echo "== DRY RUN — 게시·태그·push·checkout 없이 검사와 노트 조립까지만 한다 =="
    bash "$0" all
    assemble_notes
    echo "== pkg/release-notes.md =="
    cat pkg/release-notes.md
    echo "== 실제 release가 이어서 할 일 (DRY라 하지 않았다) =="
    echo "  git checkout main && git merge --ff-only dev"
    echo "  git tag v$ver && git push origin main v$ver"
    echo "  gh release create v$ver pkg/gfxprofile.zip --verify-tag --title v$ver --notes-file pkg/release-notes.md"
    exit 0
  fi

  # ③ 게시 준비 — 각 실패는 **복구 가능한 자리**에 멈춘다.
  gh auth status >/dev/null 2>&1 || {
    echo "gh 인증이 없다 — 먼저 gh auth login (대화형이라 사람이 직접 한다)" >&2; exit 1; }
  git fetch -q origin
  git checkout -q main || { echo "main으로 이동하지 못했다" >&2; exit 1; }
  git merge --ff-only dev || {
    echo "main을 dev로 ff-only 전진시키지 못했다 — 지금 main 위에 서 있다(작업 복귀: git checkout dev)" >&2
    exit 1; }
  if git rev-parse -q --verify "refs/tags/v$ver" >/dev/null; then
    echo "태그 v$ver가 이미 있다 — 버전을 올렸는지 확인하라(지금 main 위에 서 있다)" >&2
    exit 1
  fi

  # ④ 릴리스당 **유일한** 파이프라인 실행
  bash "$0" all

  # ⑤ 노트 조립 — 게시 전에 사람이 읽는다
  assemble_notes
  echo "== pkg/release-notes.md =="
  cat pkg/release-notes.md

  # ⑥ 태그·push — 여기까지도 아직 **게시 전**이다
  git tag "v$ver"
  git push origin main "v$ver" || {
    echo "push가 실패했다 — 아직 게시되지 않았다. 로컬 태그를 지우고 다시 하라: git tag -d v$ver" >&2
    exit 1; }

  # ⑦ 게시 — **마지막 줄**이다. 이 뒤에 자동으로 하는 일은 없다.
  gh release create "v$ver" pkg/gfxprofile.zip --verify-tag --title "v$ver" \
     --notes-file pkg/release-notes.md
  echo "게시했다: v$ver   작업 복귀: git checkout dev"
fi

echo "OK"
