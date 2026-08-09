#!/usr/bin/env python3
"""i18n 키 집합 검사 — **개수를 세지 않고 집합 관계로 본다** (설계 E18).

왜 P5가 아니라 지금부터 도는가:
    문자열은 P2~P4에서 태어나고 P5에서 번역된다. 그 사이에 키가 한쪽 JSON에만 들어가면
    P5의 "영어로 바꿔 보기"에서야 드러나는데, 그때는 어느 단계에서 새어 들어온 것인지
    알기 어렵다. **키가 생기는 순간에 잡는 것이 싸다.**

지금 검사하는 것:
    1. en.json 키 집합 == ko.json 키 집합 (양방향)
    2. src/에서 t("…")로 참조하는 키 ⊆ 양쪽 키 집합
    3. 값의 {placeholder} 집합이 두 언어에서 같다
       — 번역하면서 자리표시자를 빠뜨리면 화면에 "{n}"이 그대로 남거나 숫자가 사라진다.
    4. ★ src/에 `t()` 밖의 사용자 가시 문자열이 없다 (설계 E18 4항 — 2026-08-05 QA R6로 추가).
       1~3만 있으면 **JSON은 완벽한데 화면에 영어 리터럴이 박혀 있는 상태**를 통과시킨다.
       실제로 그랬다: self-check 실패 문구가 `t()` 밖 영어였고 이 검사는 PASS했다.
       판정 대상은 **JSX 텍스트 노드와 사용자에게 보이는 prop**(title/label/strTitle/
       strOKButtonText/toast의 title·body)이다. `console.*`의 진단 태그는 대상이 아니다
       (로그는 개발자용이고, 번역되면 로그 대조가 언어에 따라 깨진다 — E18이 명시한 예외).
       의도적 예외는 같은 줄이나 바로 윗줄에 `i18n-exempt`를 적어 **눈에 보이게** 남긴다.
    4′. ★ 같은 것을 **구문 구조로** 다시 본다 (2026-08-07 QA R4 — `qa/i18n_jsx_scan.cjs`).
       4번은 정규식이라 *"중괄호 안의 홑 리터럴"* 하나만 봤고, `{"A" + "B"}`·`join()`·변수
       경유는 그대로 통과했다(Codex가 연결식으로 재현). 패턴을 늘리는 대신 TypeScript AST로
       *"JSX 자식 자리인가 + t()를 거쳤는가"*를 본다. 두 검사는 덮는 범위가 달라 **같이** 돈다.
    5. ★ codes.py의 에러 코드 집합 ⊆ 양쪽 키 집합 (P5에서 SKIP을 걷어내고 실제로 구현).
       화면은 **code로 문구를 고른다**(설계 D4·E18 2항). 코드가 등재돼 있지 않으면
       `tCode`가 fallback으로 흘러 **원시 식별자**(= "GAME_RUNNING")가 사용자에게 뜬다.
       ⚠️ **부분 등재를 허용하지 않는다.** "이건 화면에 안 뜨니 빼도 된다"는 판단이
       곧 다음 라운드의 누락이 된다(설계 E2가 개수 기준을 버린 것과 같은 이유).
       ⚠️ `CONFIRM_REQUIRED`(FLOW_CODES)도 예외로 빼지 않는다 — 예외 목록을 만드는 순간
       그 목록이 또 하나의 관리 대상이 되고, 관리되지 않으면 검사가 거짓말을 시작한다.

여기가 `codes.py ⊆ i18n`의 **유일한 소관**이다 (P5에서 일원화).
`test_codes.py`는 `raise`에 code가 붙었는지만 본다 — 두 파일이 서로 미루면 아무도 안 한다.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
I18N = ROOT / "src" / "i18n"
SRC = ROOT / "src"

# `from gfxp import codes`는 gfxp/__init__.py(상수뿐)만 거치고 engine/store를 끌어오지 않는다 —
# decky 런타임이 없는 이 자리에서도 안전하다.
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes  # noqa: E402

# t("KEY") / t('KEY') — 키는 대문자·숫자·밑줄·점만 쓴다(설계 E18의 패턴과 같다).
T_CALL = re.compile(r"""\bt\(\s*["']([A-Z0-9_.]+)["']""")
# tCode(code, "FALLBACK_KEY") — 2번째 인자도 등재돼야 하는 키다. `\bt\(`로는 안 잡힌다.
TCODE_CALL = re.compile(r"""\btCode\(\s*[^,()]*,\s*["']([A-Z0-9_.]+)["']""")
PLACEHOLDER = re.compile(r"\{(\w+)\}")

fail = []

tables = {}
for lang in ("en", "ko"):
    path = I18N / f"{lang}.json"
    if not path.is_file():
        sys.exit(f"FAIL: {path} 없음")
    tables[lang] = json.loads(path.read_text(encoding="utf-8"))

# ── 1. 두 언어의 키 집합이 정확히 같다 ───────────────────────────────────────
en_keys, ko_keys = set(tables["en"]), set(tables["ko"])
if en_keys != ko_keys:
    fail.append(f"키 집합 불일치 — en에만 {sorted(en_keys - ko_keys)} / ko에만 {sorted(ko_keys - en_keys)}")

# ── 2. src가 부르는 키가 전부 등재돼 있다 ────────────────────────────────────
used = {}
for path in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx")):
    text = path.read_text(encoding="utf-8")
    for key in T_CALL.findall(text) + TCODE_CALL.findall(text):
        used.setdefault(key, []).append(path.relative_to(ROOT))
missing = {k: v for k, v in used.items() if k not in en_keys or k not in ko_keys}
if missing:
    for key, where in sorted(missing.items()):
        fail.append(f"등재되지 않은 키 t(\"{key}\") — {', '.join(str(p) for p in where)}")

# ── 3. 자리표시자가 두 언어에서 같다 ─────────────────────────────────────────
for key in sorted(en_keys & ko_keys):
    slots = {lang: set(PLACEHOLDER.findall(tables[lang][key])) for lang in tables}
    if slots["en"] != slots["ko"]:
        fail.append(f"자리표시자 불일치 {key} — en={sorted(slots['en'])} ko={sorted(slots['ko'])}")

# ── 5. codes.py의 에러 코드가 en/ko 양쪽에 등재돼 있다 ───────────────────────
code_set = set(codes.all_codes())
for lang, keys in (("en", en_keys), ("ko", ko_keys)):
    absent = sorted(code_set - keys)
    if absent:
        fail.append(f"{lang}.json에 없는 에러 코드 {len(absent)}종 — {absent}")

# ── 4. t() 밖의 사용자 가시 문자열이 없다 ────────────────────────────────────
VISIBLE_PROPS = ("title", "label", "strTitle", "strOKButtonText", "strCancelButtonText", "body")
# 사람이 읽는 글자: 한글 또는 라틴 문자 2자 이상
HUMAN = re.compile(r"[가-힣]|[A-Za-z]{2,}")
JSX_TEXT = re.compile(r">([^<>{}]+)<")
# ★ 2026-08-05 QA 재인증 R6: `<div>{"Visible English"}</div>` 처럼 **중괄호 안 리터럴**로 쓰면
#   위 JSX_TEXT 패턴을 피해 간다. 화면에 그대로 보이는 것은 같으므로 함께 잡는다.
#   `{{...}}`(style 객체 등)는 첫 글자가 `{`라 매치되지 않는다.
JSX_BRACED = re.compile(r"\{\s*[\"'`]([^\"'`]+)[\"'`]\s*\}")   # 백틱(템플릿 리터럴)까지 — QA 3회차 우회 5
PROP_LITERAL = re.compile(r"\b(" + "|".join(VISIBLE_PROPS) + r")\s*[:=]\s*[\"']([^\"']+)[\"']")

def _strip_comments(text):
    """주석을 지우되 **행 수를 보존한다.**

    규칙을 설명한 주석이 그 규칙의 검사에 걸리는 오탐이 이 프로젝트에서 두 번 났다 —
    그래서 지운다. 다만 블록 주석을 통째로 없애면 **줄이 접혀 행 번호가 어긋나고**,
    그러면 같은 줄에 붙인 `i18n-exempt` 표시가 엉뚱한 줄과 짝지어진다(실제로 그랬다).
    지운 자리에 개행을 같은 수만큼 남겨 줄 위치를 그대로 둔다.
    """
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)

scanned = 0
for path in sorted(SRC.rglob("*.tsx")) + sorted(SRC.rglob("*.ts")):
    lines = path.read_text(encoding="utf-8").splitlines()
    code = _strip_comments("\n".join(lines)).splitlines()
    scanned += 1
    for i, line in enumerate(code):
        raw_context = " ".join(lines[max(0, i - 1):i + 1])      # 같은 줄 + 윗줄
        if "i18n-exempt" in raw_context:
            continue
        # JSX 텍스트 규칙은 **.tsx에만** 건다. .ts에 걸면 제네릭(`callable<A, Env<T>>(route)`)의
        # 꺾쇠를 텍스트 노드로 오인해 거짓 FAIL을 낸다(실제로 냈다 — 오탐도 거짓 검사다).
        found = (
            [m.strip() for m in JSX_TEXT.findall(line)] + JSX_BRACED.findall(line)
            if path.suffix == ".tsx"
            else []
        )
        found += [v for _, v in PROP_LITERAL.findall(line)]
        for text in found:
            # ★ 템플릿 리터럴의 `${...}`는 **이미 t()를 거친 값이 들어오는 자리**다. 그것까지 세면
            #   `{`${a} — ${b}`}` 같은 정당한 조합이 위반이 된다(실제로 오탐했다).
            #   보간을 걷어낸 뒤에도 사람이 읽는 글자가 남을 때만 위반이다.
            if HUMAN.search(re.sub(r"\$\{[^}]*\}", "", text)):
                fail.append(
                    't() 밖 가시 문자열 %s:%d — "%s"' % (path.relative_to(ROOT), i + 1, text.strip())
                )

# ── 4′. **구문 구조로** 본 t() 밖 가시 문자열 (2026-08-07 QA R4) ─────────────
# 위 4번은 정규식이라 *"중괄호 안의 홑 리터럴"* 하나만 봤다. Codex가
# `<div>{"Visible " + "untranslated text"}</div>`를 넣자 그대로 통과했다 — 연결식·join·변수는
# 화면에 똑같이 보이는데 패턴만 다르다. 패턴을 늘리는 대신 **TypeScript AST**로 본다:
#     "JSX 자식 자리인가" + "t()/tCode()를 거쳤는가"
# 4번은 지우지 않고 **같이 돌린다** — .ts의 `title: "…"` 같은 객체 prop은 JSX가 아니라
# AST 규칙의 대상이 아니고, 두 검사가 덮는 범위가 다르다.
#: ★ `t()` 밖 하드코딩이 **허용되는 유일한 파일** (설계 B-3 · E13).
#:   ErrorBoundary의 폴백은 *i18n 자체가 못 뜨는 상황*에 뜨는 화면이다 — `t()`를 부르면
#:   폴백이 다시 던진다. 그래서 영어 리터럴로 고정한다.
#:   ⚠️ **예외는 넓어지려는 성질이 있다.** 아래 `check_hardcode_allowlist()`가
#:     ① 목록이 한 항목뿐인지 ② 그 파일이 실제로 존재하고 폴백을 들고 있는지
#:     ③ **i18n을 import하지 않는지**(=예외의 근거가 실재하는지)
#:     ④ `RENDER_FAILED` 표지가 다른 파일로 새지 않았는지를 잠근다.
HARDCODE_ALLOWED = frozenset({"src/ui/ErrorBoundary.tsx"})

SCANNER = ROOT / "qa" / "i18n_jsx_scan.cjs"
U1_NODE = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)
ast_hits = 0
allowed_hits = 0
if not U1_NODE.is_file():
    fail.append(f"툴체인 node가 없어 AST 가시 문자열 검사를 못 돌렸다 — {U1_NODE} "
                "(판정 불가는 통과가 아니다)")
else:
    targets = sorted(SRC.rglob("*.tsx")) + sorted(SRC.rglob("*.ts"))
    proc = subprocess.run([str(U1_NODE), str(SCANNER)] + [str(p) for p in targets],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        fail.append(f"AST 가시 문자열 검사가 실패했다(rc={proc.returncode}): "
                    f"{(proc.stderr or proc.stdout).strip()[-300:]}")
    else:
        source_lines = {}
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            hit = json.loads(line)
            path = pathlib.Path(hit["file"])
            if path not in source_lines:
                source_lines[path] = (ROOT / path).read_text(encoding="utf-8").splitlines()
            lines = source_lines[path]
            i = hit["line"] - 1
            # 의도적 예외는 같은 줄이나 바로 윗줄에 `i18n-exempt`를 적어 **눈에 보이게** 남긴다.
            if "i18n-exempt" in " ".join(lines[max(0, i - 1):i + 1]):
                continue
            if hit["file"] in HARDCODE_ALLOWED:
                allowed_hits += 1
                continue
            ast_hits += 1
            fail.append('t() 밖 가시 문자열(AST) %s:%d [%s] — "%s"'
                        % (hit["file"], hit["line"], hit["kind"], hit["text"].strip()))

# ── 4″. 하드코딩 예외가 **좁게 유지**되는가 (2026-08-07 마일스톤 R1) ─────────
def check_hardcode_allowlist():
    """예외 자체가 관리 대상이 된다 — 목록이 늘거나 근거가 사라지면 FAIL한다."""
    out = []
    if len(HARDCODE_ALLOWED) != 1:
        out.append(f"하드코딩 허용 목록이 {len(HARDCODE_ALLOWED)}개다 — 설계가 인정한 예외는 "
                   "ErrorBoundary 하나뿐이다(설계 B-3)")
    for rel in sorted(HARDCODE_ALLOWED):
        path = ROOT / rel
        if not path.is_file():
            out.append(f"허용 목록의 {rel}이 없다 — 목록이 낡았다(예외만 남고 근거가 사라졌다)")
            continue
        text = path.read_text(encoding="utf-8")
        if "RENDER_FAILED" not in text:
            out.append(f"{rel}에 RENDER_FAILED 폴백이 없다 — 허용할 이유가 실재하지 않는다")
        # ★ 예외의 **근거**: 이 파일이 i18n을 안 쓰기 때문에 하드코딩이 정당하다.
        #   i18n을 import하는 순간 그 근거가 무너지므로 예외도 무효다.
        for module in ("./i18n", "../i18n", "./deckyui", "../deckyui"):
            if f'from "{module}"' in text:
                out.append(f"{rel}이 {module}을 import한다 — 하드코딩 예외의 근거가 무너진다"
                           "(그것이 못 뜨는 상황이 바로 이 폴백이 뜨는 상황이다)")
    # RENDER_FAILED 표지가 허용 파일 밖으로 새지 않았는가
    leaked = [str(p.relative_to(ROOT)) for p in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx"))
              if "RENDER_FAILED" in p.read_text(encoding="utf-8")
              and str(p.relative_to(ROOT)) not in HARDCODE_ALLOWED]
    if leaked:
        out.append(f"RENDER_FAILED가 허용 파일 밖에도 있다: {leaked} — 폴백은 한 곳이어야 한다")
    return out


fail += check_hardcode_allowlist()

print(f"키 {len(en_keys)}종 / src 참조 {len(used)}종 / 두 언어 자리표시자 대조 완료")
print(f"가시 문자열 검사: {scanned}개 파일 (t() 밖 리터럴 0건이어야 한다) · AST 위반 {ast_hits}건 · "
      f"허용 예외 {allowed_hits}건 in {sorted(HARDCODE_ALLOWED)}")
print(f"에러 코드 대조: codes.py {len(code_set)}종 ⊆ en/ko 키 (부분 등재 불가)")

if fail:
    print("FAIL")
    for line in fail:
        print("  " + line)
    sys.exit(1)
print("PASS")
