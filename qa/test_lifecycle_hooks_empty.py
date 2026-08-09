#!/usr/bin/env python3
"""생명주기 훅 `_uninstall`·`_migration`이 **비어 있음**을 AST로 잠근다 — P7 완료 기준 ②.

왜 필요한가:
    로더는 제거 시 `Plugin._uninstall()`을, 로드 시 `Plugin._migration()`을 **있으면 그대로
    실행한다**(`decky_loader/plugin/sandboxed_plugin.py`, hasattr 확인 후 await). 즉 이 두
    함수 본문에 파일을 지우거나 옮기거나 쓰는 코드가 한 줄이라도 들어가면, **플러그인을 지웠을
    뿐인데 사용자의 registry·profiles·backups가 함께 날아간다.** 완료 기준의 "`_uninstall`이
    비어 있음"은 사람 눈으로만 지켜지고 있었다(설계 REV2 E19 / RESEARCH-P7 §B-2, §C-1-a).

무엇을 잠그는가 — **함수 본문이 위험 동작(파일 삭제·이동·쓰기)을 하지 않는다**:
    L1 구조 허용목록: 본문에 올 수 있는 문(statement)은 `pass` · 문자열 리터럴(독스트링) ·
       `decky.logger.<level>(...)` 호출 **셋뿐**이다. 대입·with·import·try·조건문 전부 위반.
    L2 위험 호출 스캔: 본문 어디에 있든(로그 인자 안에 숨겨도) 허용 로거 호출이 아닌 Call은
       전부 위반이고, 그중 파일 삭제·이동·쓰기·프로세스 실행·`migrate_*`는 이유를 따로 붙인다.

⚠️ 중복 아님: `build.sh grep`의 AST 검사는 **`decky.migrate_*`를 이름으로 호출하는지**를
   프로젝트 전역에서 본다(0건). 이 검사는 **이 두 함수의 본문이 무슨 일을 하는지**를 본다 —
   `shutil.rmtree(...)`는 저쪽 검사에 안 걸리고 여기서만 걸린다.

⚠️ 주석·독스트링 grep 금지: 이 프로젝트에서 문자열 검색이 주석에 오탐한 사고가 두 번 있었다.
   판정은 전부 `ast`로만 한다.

반증(매 실행마다 실제로 돌린다 — 문서가 아니라 실행으로 증명한다):
    R1  `_uninstall`에 `shutil.rmtree(...)` 주입      → 검출해야 한다
    R2  `_migration`에 `decky.migrate_settings()` 주입 → 검출해야 한다
    R3  로거 호출의 **인자 안에** `shutil.rmtree(...)` 숨김 → 검출해야 한다
    N1  (음성 대조군) `_uninstall`에 로그 한 줄 추가    → 검출하면 안 된다
    N2  (음성 대조군) `_migration`을 `pass` 그대로 둠   → 검출하면 안 된다
    N1·N2가 없으면 "무엇이든 FAIL"인 무의미한 검사와 구별되지 않는다.

허용 범위를 **의도적으로** 넓혀야 한다면 ALLOWED_LOGGER를 고치는 것이 유일한 문이다.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"
CLASS = "Plugin"
HOOKS = ("_uninstall", "_migration")

# 허용되는 유일한 호출: decky.logger.<level>(...)
ALLOWED_LOGGER = ("decky", "logger")

# 위반 사유를 구체적으로 붙일 이름들(허용목록 밖이면 어차피 전부 위반이다 — 이건 진단용 라벨).
DANGER_LEAF = {
    # 삭제
    "rmtree", "remove", "unlink", "rmdir", "removedirs", "cleanup_plugin_settings",
    # 이동·복사
    "rename", "replace", "move", "copy", "copy2", "copyfile", "copytree",
    # 쓰기·생성
    "write_text", "write_bytes", "write", "writelines", "truncate", "open",
    "mkdir", "makedirs", "touch", "dump", "save", "flush",
    # 권한·링크
    "chmod", "chown", "symlink", "link",
    # 프로세스
    "system", "run", "Popen", "call", "check_call", "check_output", "spawn",
}


def dotted(node):
    """Name/Attribute 체인을 'a.b.c' 문자열로. 아니면 None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def is_allowed_logger_call(call):
    """decky.logger.info(...) 형태인가 — 정확히 3단계 점 표기만 인정한다."""
    name = dotted(call.func)
    if not name:
        return False
    parts = name.split(".")
    return len(parts) == 3 and tuple(parts[:2]) == ALLOWED_LOGGER


def why_dangerous(call):
    name = dotted(call.func) or ast.dump(call.func)[:40]
    leaf = name.split(".")[-1]
    if leaf.startswith("migrate_"):
        return f"{name}() — decky의 migrate_*는 원본을 삭제한다"
    if leaf in DANGER_LEAF:
        return f"{name}() — 파일 삭제·이동·쓰기·프로세스 실행 계열"
    return f"{name}() — 허용목록(decky.logger.*) 밖의 호출"


def find_hook(tree, hook):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == CLASS:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == hook:
                    return item
    return None


def analyze(tree):
    """위반 목록을 돌려준다. 빈 리스트 = 비어 있음이 확인됨."""
    bad = []
    for hook in HOOKS:
        fn = find_hook(tree, hook)
        if fn is None:
            bad.append(f"{CLASS}.{hook}()가 없다 — 이름이 바뀌었거나 지워졌다(fail-closed)")
            continue
        if not isinstance(fn, ast.AsyncFunctionDef):
            bad.append(f"{hook}()가 async가 아니다 — 로더는 await로 부른다")

        # L1 구조 허용목록
        for stmt in fn.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                    and isinstance(stmt.value.value, str):
                continue                                   # 독스트링/문자열 리터럴
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) \
                    and is_allowed_logger_call(stmt.value):
                continue                                   # 로그 한 줄
            kind = type(stmt).__name__
            bad.append(f"{hook}():{stmt.lineno} 허용되지 않는 문 {kind} — "
                       f"본문은 pass/문자열/decky.logger.* 셋만 허용된다")

        # L2 위험 호출 스캔 (로그 인자 안에 숨겨도 잡는다)
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and not is_allowed_logger_call(node):
                bad.append(f"{hook}():{getattr(node, 'lineno', '?')} 위험 호출 {why_dangerous(node)}")
            # 람다·컴프리헨션으로 감싼 지연 실행도 본문에 있을 이유가 없다
            if isinstance(node, (ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                bad.append(f"{hook}():{getattr(node, 'lineno', '?')} "
                           f"{type(node).__name__} — 본문에 있을 이유가 없다(우회 표면)")
    return bad


def inject(hook, snippet):
    """실제 main.py를 파싱해 hook 본문 끝에 snippet을 넣은 **사본 트리**를 만든다."""
    tree = ast.parse(MAIN.read_text(), filename=str(MAIN))
    fn = find_hook(tree, hook)
    if fn is None:
        sys.exit(f"반증을 만들 수 없다 — {hook}()를 못 찾았다")
    fn.body.extend(ast.parse(snippet).body)
    return ast.fix_missing_locations(tree)


fail = []
real = ast.parse(MAIN.read_text(), filename=str(MAIN))

# ── 본 검사 ──────────────────────────────────────────────────────────────────
violations = analyze(real)
if violations:
    fail.extend(violations)

# ── 반증 R1~R3 / 음성 대조군 N1~N2 ───────────────────────────────────────────
CASES = [
    ("R1", "_uninstall", "shutil.rmtree(store.data_dir())", True),
    ("R2", "_migration", "decky.migrate_settings()", True),
    ("R3", "_uninstall", 'decky.logger.info("bye %s", shutil.rmtree(store.data_dir()))', True),
    ("N1", "_uninstall", 'decky.logger.info("extra line session=%s", SESSION)', False),
    ("N2", "_migration", "pass", False),
]
proof = []
for tag, hook, snippet, must_detect in CASES:
    got = analyze(inject(hook, snippet))
    detected = bool(got)
    shown = "\n".join(f"      검출: {g}" for g in got) if got else "      통과: 검출 0건"
    proof.append(f"  {tag} {hook} ← {snippet.splitlines()[-1]!r}\n{shown}")
    if detected != must_detect:
        fail.append(f"반증 {tag} 실패 — {hook}에 {snippet.splitlines()[-1]!r}를 주입했는데 "
                    f"{'검출하지 못했다' if must_detect else '엉뚱하게 검출했다'} "
                    f"(이 검사는 무효다)")

print("주입 반증 결과:")
print("\n".join(proof))

if fail:
    print("FAIL")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print(f"PASS 생명주기 훅 2종 비어 있음 — {CLASS}._uninstall / {CLASS}._migration "
      f"(반증 3종 검출 · 음성 대조군 2종 통과)")
