#!/usr/bin/env python3
"""확인창 spec 7종의 **문구 키를 잠근다** — 선언(소스) ↔ 실제 구성(렌더) 대조 + 개수 등호.

### 왜 이 검사가 생겼나 — 50키 중 34키가 어떤 검사에도 안 잡혔다
`confirmSpecs.tsx`는 확인창의 **선언 하나뿐인 정본**인데(§4-C), 거기 적힌 키가 실제로 화면에
나오는지를 재는 검사가 없었다. 2026-08-12 qa-lead 게이트 C6의 실증: 아래 4줄을 **각각 지워도
회귀 전량이 초록**이었다(검출 0).

    SAVE_CONFIRM_BACKUP_LIMIT   덮어쓴 대피본이 곧 밀려 사라진다는 유일한 고지
    DELETE_CONFIRM_BODY         무엇을 지우는지 말하는 첫 문장
    RESET_CONFIRM_NAMES         초기화가 표시 이름까지 지운다는 고지
    SAVE_CONFIRM_CURRENT        지금 덮어쓸 내용의 크기·지문

전부 **되돌리기 어려운 동작 직전**에 사용자가 읽어야 하는 문장이다. 왜 아무도 못 봤나:
`test_i18n_sets`는 키 **집합**을(값이 살아 있으면 참) · `test_wording_10a`는 §10-A가 값을 명시한
키의 **바이트**를(§10-A 밖 키는 대상이 아니다) · `test_wording_a5`는 **금칙어**를(안 쓰면 초록) ·
팝업 프로브들은 **자기 화면이 부르는 키**를 본다 — 확인창 spec은 팝업이 게이트에 통째로
넘기는 값이라 그 그물 사이로 빠졌다.

### 구조 — 키를 **열거하지 않는다**
이 파일에는 키 이름이 한 개도 없다(그래서 낡지 않는다). 재는 것은 두 가지 관계다.

1. **선언 == 구성**: `confirmSpecs.tsx`의 각 spec 함수가 적어 둔 키(소스 파싱, 헬퍼 전개)와
   프로브가 **분기별 장면 전량**을 구성했을 때 실제로 불린 키의 합집합이 같아야 한다.
   → 선언에만 있는 키 = **도달 불가 문장**(또는 장면 부족)이고, 구성에만 있는 키 = 파서가
     못 본 자리다. 어느 쪽이든 "적어 놓고 안 재는" 상태의 재발이다.
2. **spec별 키 개수 등호**(`EXPECTED_KEYS`): 관계 1만으로는 **한 줄을 지우면 양쪽이 같이
   줄어** 통과한다(위 4키가 정확히 그 형태다). 개수는 **의식적으로 갱신하는 한 곳**이고,
   여기서 등호가 깨지면 키가 늘었거나 줄었다는 뜻이다 — 하한(>=)이 아니라 등호인 이유는
   `test_wording_10a`의 `TOTAL_FIXED`와 같다(조용히 줄어도 통과하는 검사는 검사가 아니다).

거기에 파싱 규칙 자체를 지키는 가드 둘: **추출한 리터럴은 전부 i18n에 등재된 키**여야 하고
(아니면 "대문자 문자열 = 문구 키"라는 전제가 깨진 것이다), **프로브가 몬 spec 목록 == 소스의
`export function make*Spec` 목록**이어야 한다(새 확인창을 장면 없이 추가할 수 없다).

★ 이 검사도 **자기 자신을 반증한다** — 위 4키를 각각 지운 사본에 같은 판정을 돌려 전부
  잡히는지 본다. 하나라도 안 잡히면 *"이 검사는 그 손실에 대해 무효다"*라며 스스로 실패한다.
⚠️ 범위 밖: 문구의 **내용**(§10-A 바이트 고정 = `test_wording_10a`) · 확인창이 **뜨는가**
  (백엔드 `needs_confirm` = `test_confirm_equivalence`) · 두 렌더러 동일성(`test_popup_shell`).
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "confirm_keys_probe.cjs"
SOURCE = ROOT / "src" / "confirmSpecs.tsx"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

#: spec별 **키 개수**. 늘거나 줄면 여기를 **의식적으로** 갱신한다 — 그 한 번의 손이
#: "문장 하나가 조용히 사라졌다"와 "일부러 늘렸다"를 가른다. (숫자의 근거는 소스 선언이고,
#: 실패 메시지가 어느 키가 늘고 줄었는지까지 말해 준다.)
EXPECTED_KEYS = {
    "makeSaveConfirmSpec": 12,
    "makeDeleteConfirmSpec": 12,
    "makeRestoreConfirmSpec": 13,
    "makeRestoreFollowUpSpec": 6,
    "makeDiscoverWarnSpec": 4,
    # 10판(§7 중복 정리): `RESET_CONFIRM_BODY`·`RESET_CONFIRM_BACKUP_KEPT` 두 줄이 **키째**
    # 빠졌다 — 수량과 백업 잔존을 ⚠ warnBlock이 이미 말하고 있었고, 같은 사실을 두 번
    # 말하면 어느 쪽이 정본인지 화면이 답하지 못한다. 10 → 8이다(음성 대조군은 그 −1인 7).
    "makeResetConfirmSpec": 8,
    "makeNameEditSpec": 8,
}

SPEC_NAME = re.compile(r"^make[A-Za-z]*Spec$")
#: 이 파일의 **대문자 스네이크 문자열 리터럴 = 문구 키**다(주석 제거 후). 아래 `i18n 등재`
#: 가드가 그 전제를 지킨다 — 키가 아닌 대문자 리터럴이 생기면 그 자리에서 FAIL한다.
KEY_LITERAL = re.compile(r"""["']([A-Z][A-Z0-9_]{2,})["']""")
FUNC_HEAD = re.compile(r"^(?:export\s+)?function\s+(\w+)\s*\(", re.M)


def strip_comments(text):
    """주석을 지운다(행 수 보존). 규칙을 설명한 주석이 그 규칙의 검사에 걸리는 오탐이
    이 프로젝트에서 두 번 났다 — 여기 주석에는 키 이름이 그대로 적혀 있다."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def declared_keys(source_text):
    """소스가 **선언한** 키를 함수별로 — 헬퍼(`profileKey`·`diskStateText`)는 전개해서 합친다.

    함수는 전부 최상위이고 다음 `function` 머리까지가 한 블록이다(닫는 `}`가 0열).
    """
    text = strip_comments(source_text)
    heads = list(FUNC_HEAD.finditer(text))
    blocks = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        blocks[m.group(1)] = text[m.start():end]

    own = {name: set(KEY_LITERAL.findall(body)) for name, body in blocks.items()}
    calls = {
        name: {other for other in blocks
               if other != name and re.search(r"\b%s\s*\(" % re.escape(other), body)}
        for name, body in blocks.items()
    }

    def resolve(name, chain):
        keys = set(own[name])
        for callee in calls[name]:
            if callee in chain:          # 순환은 이 파일에 없지만, 생겨도 죽지 않는다
                continue
            keys |= resolve(callee, chain | {name})
        return keys

    return {name: resolve(name, {name}) for name in blocks}, sorted(
        n for n in blocks if SPEC_NAME.match(n))


def run_probe(src_dir=None):
    cmd = [str(U1), str(PROBE)] + ([str(src_dir)] if src_dir else [])
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def violations(probe, source_text, i18n_keys):        # noqa: C901  (판정 나열)
    """프로브 결과 + 같은 소스의 선언을 대조한다. **음성 대조군이 이 함수를 그대로 다시 돌린다.**"""
    out = []
    all_declared, spec_names = declared_keys(source_text)

    # ── 가드 ①: 프로브가 몬 spec == 소스의 export한 spec ──────────────────────
    driven = sorted(probe.get("driven") or [])
    if driven != spec_names:
        out.append(f"★확인창 spec 목록이 프로브와 소스에서 다르다 — 프로브 {driven} / "
                   f"소스 {spec_names}. 새 확인창을 **장면 없이** 추가하면 그 문장들은 "
                   f"태어나자마자 무측정이 된다(그것이 C6가 잡은 상태다)")

    # ── 가드 ②: 추출한 리터럴이 전부 i18n 키인가(파싱 전제의 실재) ────────────
    literals = set()
    for name in spec_names:
        literals |= all_declared.get(name, set())
    stray = sorted(k for k in literals if k not in i18n_keys)
    if stray:
        out.append(f"★i18n에 없는 대문자 리터럴을 키로 세고 있다: {stray} — "
                   f"「대문자 문자열 = 문구 키」 전제가 깨졌다(파서를 고치거나 그 리터럴을 없애라)")

    # ── 관계 ①·②: 선언 ↔ 구성 · 개수 등호 ───────────────────────────────────
    for name in spec_names:
        declared = all_declared.get(name, set())
        got = probe.get("specs", {}).get(name)
        if got is None:
            out.append(f"★{name}: 프로브가 이 spec을 재지 않았다 — 측정 없음(검사 무효)")
            continue
        for scene in got.get("scenes") or []:
            if scene.get("error"):
                out.append(f"★{name}[{scene['label']}] 장면이 죽었다: {scene['error']} — "
                           f"그 분기는 **한 글자도 재지 못했다**")
        rendered = set(got.get("keys") or [])
        missing = sorted(declared - rendered)
        extra = sorted(rendered - declared)
        if missing:
            out.append(f"★{name}: 선언에는 있는데 **어떤 장면에서도 안 불린** 키 {missing} — "
                       f"도달 불가 문장이거나 장면이 모자라다. 표에서 빼지 말고 "
                       f"`confirm_keys_probe.cjs`에 그 분기의 장면을 더하라")
        if extra:
            out.append(f"★{name}: 구성에는 나오는데 선언 파싱이 못 본 키 {extra} — "
                       f"파서 전제(최상위 함수·대문자 리터럴)가 깨졌다. 검사가 헐거워졌다")

        want = EXPECTED_KEYS.get(name)
        if want is None:
            out.append(f"★{name}: 개수 표에 없다 — 확인창이 늘었으면 `EXPECTED_KEYS`를 "
                       f"의식적으로 갱신하라(현재 {len(declared)}키)")
        elif len(declared) != want:
            out.append(f"★{name}의 문구 키가 {len(declared)}개다(표 {want}개) — "
                       f"확인창에서 문장이 **사라졌거나** 늘었다. 지금 선언된 키: "
                       f"{sorted(declared)}\n      되돌리기 어려운 동작 직전의 문장이 조용히 "
                       f"빠지는 자리다(C6). 의도한 변경이면 `EXPECTED_KEYS`를 갱신하라")

    stale = sorted(set(EXPECTED_KEYS) - set(spec_names))
    if stale:
        out.append(f"★개수 표에 없는 spec이 적혀 있다: {stale} — 이름이 바뀌었거나 사라졌다"
                   f"(표가 낡으면 그 spec은 다시 무측정이 된다)")
    return out


#: 음성 대조군 — C6가 실증한 **4키 제거** 그대로. (설명, 정규식, 치환, 기대 판정 조각)
#: ★ 전부 `confirmSpecs.tsx` 한 줄을 지운다: 지우면 선언과 구성이 **같이** 줄어 관계 ①은
#:   통과한다 — 잡는 것은 **개수 등호**다. 그래서 기대 조각도 개수 판정의 문장으로 잡는다.
BYPASSES = [
    ("대피본 소멸 고지를 지움(SAVE_CONFIRM_BACKUP_LIMIT)",
     r'\n *<div style=\{WARN_STYLE\}>\{t\("SAVE_CONFIRM_BACKUP_LIMIT"[^\n]*\n', "\n",
     "makeSaveConfirmSpec의 문구 키가 11개다"),
    ("무엇을 지우는지 말하는 첫 문장을 지움(DELETE_CONFIRM_BODY)",
     r'\n *<div>\{t\("DELETE_CONFIRM_BODY"\)\}</div>\n', "\n",
     "makeDeleteConfirmSpec의 문구 키가 11개다"),
    ("표시 이름 소멸 고지를 지움(RESET_CONFIRM_NAMES)",
     r'\n *\{params\.named > 0 \? <div>\{t\("RESET_CONFIRM_NAMES"[^\n]*\n', "\n",
     # 10판: reset spec이 10 → 8키가 됐으므로 한 줄을 지운 사본은 7키다("9개다"에서 갱신).
     # ★ 이 하드코딩은 **일부러** 손으로 맞춘다 — 자동 계산으로 바꾸면 개수 판정과 같은
     #   식을 두 번 쓰게 되어, 그 식이 틀린 날 음성 대조군이 틀린 채로 통과한다.
     "makeResetConfirmSpec의 문구 키가 7개다"),
    ("덮어쓸 내용의 크기·지문을 지움(SAVE_CONFIRM_CURRENT)",
     r'\n *<div>\{t\("SAVE_CONFIRM_CURRENT"[^\n]*\n', "\n",
     "makeSaveConfirmSpec의 문구 키가 11개다"),
]


def main():
    if not U1.is_file():
        # 판정 불가는 통과가 아니라 **거부**다(QA R7).
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    i18n_keys = set(json.loads((ROOT / "src" / "i18n" / "ko.json").read_text(encoding="utf-8")))
    source = SOURCE.read_text(encoding="utf-8")
    probe, err = run_probe()
    if probe is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1

    bad = violations(probe, source, i18n_keys)
    declared, spec_names = declared_keys(source)
    total = sum(len(declared[n]) for n in spec_names)
    print(f"확인창 spec {len(spec_names)}종 · 문구 키 {total}건(선언 ↔ 구성 대조 + 개수 등호)")
    for name in spec_names:
        got = (probe.get("specs", {}).get(name) or {})
        print(f"  {name}: 선언 {len(declared[name])} · 구성 {len(got.get('keys') or [])} · "
              f"장면 {len(got.get('scenes') or [])}종")
    if bad:
        print("\nFAIL")
        for b in bad:
            print("  " + b)
        return 1

    # ── 음성 대조군: C6가 실증한 손실 4종이 지금은 잡히는가 ────────────────────
    for label, pattern, replacement, expect in BYPASSES:
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            injected, n = re.subn(pattern, replacement, source, count=1)
            if n != 1:
                # 주입이 안 됐는데 "통과"로 읽는 것이 이 프로젝트에서 세 번 난 사고다.
                print(f"FAIL — 음성 대조군 주입 실패({label}): 대상 줄을 못 찾았다. 검사가 무효다.")
                return 1
            (case / "confirmSpecs.tsx").write_text(injected, encoding="utf-8")
            control, err = run_probe(case)
            if control is None:
                print(f"FAIL — 음성 대조군 프로브 실행 실패({label}): {err}")
                return 1
            caught = violations(control, injected, i18n_keys)
            hit = [c for c in caught if expect in c]
            if not hit:
                print(f"FAIL — 문장을 지웠는데 **그 판정이** 안 잡았다: {label}")
                print(f"       기대 조각 {expect!r} / 잡힌 것: {caught}")
                return 1
            print(f"  음성 대조군 검출: {label} → {hit[0].splitlines()[0][:110]}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
