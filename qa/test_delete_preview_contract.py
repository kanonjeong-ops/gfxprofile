#!/usr/bin/env python3
"""delete_preview 봉투 계약 — unsafe 갈래에서도 필수 필드를 전부 싣는가 (F7-2).

계약 검사다(화면을 재지 않는다). `remove.delete_preview`의 unsafe 갈래(경로가 데이터 루트 안
제자리가 아닌 등록 항목)는 아무 파일도 읽지 않고 고정 params를 낸다. 그 params가 `rpc.ts`의
`DeleteConfirmParams` 필수 필드를 전부 실어야 프론트가 없는 값을 읽다 죽지 않는다. `evicted`는
그 계약의 필수 필드인데 unsafe 갈래에서 런타임만 빠져 있었다(F4-4가 넣음) — 이 검사가 그 잠금이다.

정본은 `src/rpc.ts`의 `DeleteConfirmParams`다. 필드 목록을 여기 두 벌로 적으면 갈리므로 그
인터페이스에서 **비-옵셔널 필드**를 파싱해 대조한다. `confirm_token`은 판정 함수가 아니라 delete
route가 `_issue`로 채우는 필드라 delete_preview의 params에는 없는 것이 정상이므로 대조에서 뺀다.
"""
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

#: delete route가 나중에 채우는 필드 — 판정 함수(delete_preview)의 params엔 없는 것이 정상이다.
_ROUTE_FILLED = {"confirm_token"}


def required_fields():
    """`rpc.ts`의 `DeleteConfirmParams`에서 비-옵셔널 필드 이름을 뽑는다 — 정본은 그 인터페이스다."""
    src = (ROOT / "src" / "rpc.ts").read_text(encoding="utf-8")
    m = re.search(r"export interface DeleteConfirmParams\s*\{(.*?)\n\}", src, re.S)
    if not m:
        return None
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)   # 블록 주석 안의 `:`·이름 오인 방지
    out = []
    for fm in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)(\??)\s*:", body, re.M):
        if fm.group(2) != "?":                                # 옵셔널은 계약상 없어도 되므로 뺀다
            out.append(fm.group(1))
    return out


def main():
    problems = []
    fields = required_fields()
    if not fields:
        print("FAIL")
        print("  src/rpc.ts에서 DeleteConfirmParams를 파싱하지 못했다 (fail-closed)")
        return 1

    with tempfile.TemporaryDirectory() as td:
        os.environ["GFXPROFILE_DATA_DIR"] = os.path.join(td, "data")
        os.environ["GFXPROFILE_HOME"] = td
        from gfxp import remove, store  # noqa: E402
        reg = store.default_registry()
        # unsafe 갈래 트리거: 경로 탈출 키를 등록 항목으로 심는다(제자리 아님 → _paths_in_position False).
        #   등록 항목이어야 game_or_fail(require_intact=False)를 지나 unsafe 갈래에 닿는다.
        escape = "../../ESCAPE"
        reg["games"][escape] = {"name": "evil", "config_path": os.path.join(td, "x.ini")}
        if remove._paths_in_position(escape):                 # 사전 조건 — 항진식 방지
            print("FAIL")
            print("  전제 실패 — 탈출 키가 unsafe(제자리 아님)로 판정되지 않았다")
            return 1
        params, _fp = remove.delete_preview(reg, escape)

    want = [f for f in fields if f not in _ROUTE_FILLED]
    missing = [f for f in want if f not in params]
    if missing:
        problems.append("unsafe 갈래 params에 DeleteConfirmParams 필수 필드 누락: %s (실린 키: %s)"
                        % (missing, sorted(params)))
    if params.get("evicted") != []:
        problems.append("unsafe 갈래 evicted가 [] 아님: %r (F4-4 잠금)" % params.get("evicted"))

    print("delete_preview 봉투 계약 — unsafe 갈래에서 DeleteConfirmParams 필수 필드 %d개 대조"
          % len(want))
    for p in problems:
        print("  " + p)
    print("FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
