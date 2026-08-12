#!/usr/bin/env python3
"""팝업 S(설계 §7)의 계약을 **렌더+클릭으로** 잠근다. 명세 정본 §15-B ⑨(UI 층) + §7 분기표.

`qa/test_discover_exclude.py` ⑨가 **route 층**에서 "게임 0 · 제외 1"을 잠갔다면, 여기는
**화면 층**이다 — 백엔드가 `counts.excluded`를 아무리 정확히 세도 화면이 그것을 안 쓰면
사용자에게는 없는 기능이다.

### 잠그는 것
1. **[전체 초기화] 활성 조건 = `total > 0 || excluded > 0`**(Codex D-01, 세션 확정).
   ★ 마지막 게임을 등록 해제하면 `total=0`인데 감지 제외 목록은 남는다. `total`만 보면
   그 목록을 지울 방법이 UI에서 사라져 **A9 ④("초기화에 제외 포함")가 도달 불가**가 된다.
   ★ 수는 **봉투가 준 값**이다 — 프론트가 다시 세지 않는다.
2. **상태 분기표**(F24·S-02): 로딩 중에는 비활성(판정 재료가 아직 없다) / **조회 실패에는
   활성 유지 + 카운트 자리 "확인 불가"**. 실패에도 활성인 근거는 ⓐ 일시 원인이 섞여 있고
   ⓑ 눌러도 오발동이 없다는 것이다(토큰+challenge fail-closed). **손상 복구의 탈출구가
   아니다** — 눌러 보면 백엔드가 정확한 사유를 돌려준다.
3. **2단 방어**: 1차 호출은 토큰 없이 · 확인창은 `challenge`를 정확히 입력해야 OK가 열리고
   · 확정 시 **받은 토큰과 입력값을 그대로** 되돌린다.
4. **⚠ 경고 블록**(A8이 인정한 유일한 위험색)과 **제외 목록 고지**(0건이면 미표시).
5. **입력값 보존**(GP#9): 치다 만 값이 다음 확인창의 초기값으로 돌아온다 — 가상 키보드로
   한 글자씩 찍은 입력이 B 오조작 한 번에 사라지지 않는다.
6. **표시 이름 변경은 RPC 첫 인자로 식별자**를 보낸다(표시명이 그 자리로 새면 저장된 프로필이
   길을 잃는다) · 편집창 OK는 **항상 활성**(빈 입력 = 기본 이름으로 되돌리기).
7. **A4 전역 전용**: 이 화면에 게임별 동작이 하나도 없다.

★ 이 테스트도 **자기 자신을 반증한다** — 알려진 위반 11종을 주입해 전부 검출되는지 본다.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "settings_popup_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

BYPASSES = [
    ("활성 조건에서 제외 건수를 뺌(A9 ④가 도달 불가가 된다)", "SettingsPopup.tsx",
     r"counts\.total > 0 \|\| counts\.excluded > 0", "counts.total > 0"),
    ("조회 실패에서 초기화를 원천 차단", "SettingsPopup.tsx",
     r"const resetEnabled = counts \? counts\.total > 0 \|\| counts\.excluded > 0 : !loading;",
     "const resetEnabled = counts ? counts.total > 0 || counts.excluded > 0 : false;"),
    ("로딩 중에도 초기화를 활성으로(판정 재료가 없는데 누를 수 있다)", "SettingsPopup.tsx",
     r"const loading = data === null && !note;", "const loading = false;"),
    ("카운트를 모르는데 0으로 단언", "SettingsPopup.tsx",
     r'counts \? counts\.total : t\("RESET_ZONE_UNKNOWN"\)', "counts ? counts.total : 0"),
    ("초기화 1차 호출에 토큰을 지어냄", "SettingsPopup.tsx",
     r"return resetAll\(token, text\)", 'return resetAll(token ?? "MADE-UP-TOKEN", text)'),
    ("확정 시 받은 토큰이 아닌 값을 되돌림", "SettingsPopup.tsx",
     r"void runReset\(p\.confirm_token, value\);", 'void runReset("SOMETHING-ELSE", value);'),
    ("남은 것을 말하지 않음(무엇이 안 지워졌는지 사라진다)", "SettingsPopup.tsx",
     r'setNote\(left > 0 \? `\$\{ok\} \$\{t\("RESET_LEFT_NOTE", \{ left \}\)\}` : ok\);',
     "setNote(ok);"),
    ("치다 만 입력을 버림(가상 키보드 입력이 날아간다)", "SettingsPopup.tsx",
     r"\n                  resetTyped,\n", '\n                  "",\n'),
    ("이름 변경 RPC에 식별자 대신 표시명을 보냄", "SettingsPopup.tsx",
     r"return setProfileName\(profile, name\)", "return setProfileName(name as never, name)"),
    ("초기화 확인창의 ⚠ 경고 블록을 뺌", "confirmSpecs.tsx",
     r'warnBlock: <div>\{t\("RESET_CONFIRM_WARN", \{ games: params\.games, profiles: params\.profiles \}\)\}</div>,',
     ""),
    ("제외 고지를 0건에도 표시", "confirmSpecs.tsx",
     r"\{params\.excluded > 0 \?", "{params.excluded >= 0 ?"),
]


def run_probe(src_dir):
    proc = subprocess.run([str(U1), str(PROBE), str(src_dir)],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def has_key(texts, key):
    return any(x == key or x.startswith(key + " ") for x in texts)


def violations(r):                                             # noqa: C901  (판정 나열)
    out = []

    # ═══ 1·2 활성 조건과 상태 분기 ════════════════════════════════════════════
    states = {k: r.get(k) or {} for k in ("base", "excludedOnly", "nothing", "loadFailed", "loading")}
    for name, state in states.items():
        if not state.get("hasButton"):
            out.append(f"[{name}] 초기화 버튼이 화면에 없다 — 기능이 있다는 사실 자체는 보여야 한다")
    if states["base"].get("enabled") is not True:
        out.append(f"등록이 있는데 초기화가 비활성이다: {states['base']}")
    if states["excludedOnly"].get("enabled") is not True:
        out.append("★§15-B ⑨ **게임 0 · 제외 1**인데 초기화가 비활성이다 — 그 제외 목록을 지울 "
                   "방법이 화면에서 사라진다(A9 ④ 도달 불가, D-01)")
    if states["nothing"].get("enabled") is not False:
        out.append("지울 것이 하나도 없는데 초기화가 활성이다 — 눌러도 아무 일이 없는 버튼은 "
                   "라벨이 거짓말을 한다")
    if states["loadFailed"].get("enabled") is not True:
        out.append("조회 실패에서 초기화를 원천 차단했다 — 일시 원인(권한·경합)이 섞여 있고, "
                   "눌러도 백엔드가 fail-closed다(F24·S-02)")
    if not has_key(states["loadFailed"].get("zone") or [], "RESET_ZONE_BODY"):
        out.append("조회 실패 화면에 초기화 구역 설명이 없다")
    elif "RESET_ZONE_UNKNOWN" not in " ".join(states["loadFailed"].get("zone") or []):
        out.append(f"★조회에 실패했는데 카운트를 단언한다: {states['loadFailed'].get('zone')} — "
                   f"모르는 것은 '확인 불가'라고 말한다")
    if not states["loadFailed"].get("note"):
        out.append("조회 실패 사유를 화면이 말하지 않는다")
    if states["loading"].get("enabled") is not False:
        out.append("★로딩 중인데 초기화가 활성이다 — 판정 재료(카운트)가 아직 없다")
    if states["base"].get("zone") != ["RESET_ZONE_BODY 2"]:
        out.append(f"초기화 구역이 봉투의 등록 수를 말하지 않는다: {states['base'].get('zone')}")

    # ═══ 3 2단 방어 ══════════════════════════════════════════════════════════
    if r.get("resetBlocked"):
        out.append("초기화 흐름을 시작조차 못 했다 — 측정 대상에 못 닿았다")
        return out
    call1 = r.get("resetCall1") or []
    if call1 and call1[0]:
        out.append(f"★초기화 1차 호출에 토큰이 실려 있다({call1[0]!r}) ★프론트가 토큰을 지어냈다")
    if not r.get("resetMirrored"):
        out.append("초기화 확인창을 못 꺼냈다 — 대조가 항진식이다")
        return out
    if r.get("resetOkBefore") is not True or r.get("resetOkWrong") is not True:
        out.append(f"★확인 단어를 입력하기 전인데 OK가 열려 있다 — before={r.get('resetOkBefore')} "
                   f"wrong={r.get('resetOkWrong')}")
    if r.get("resetOkTyped") is not False:
        out.append("★확인 단어를 정확히 입력했는데 OK가 계속 잠겨 있다 — 입력이 반영되지 않는다")
    if (r.get("resetCall2") or []) != ["RESET-TOKEN", "delete"]:
        out.append(f"★확정 시 되돌린 토큰·입력값이 다르다: {r.get('resetCall2')}")
    note = " ".join(r.get("resetNote") or [])
    if "RESET_OK" not in note:
        out.append(f"초기화 결과를 화면이 말하지 않는다: {r.get('resetNote')}")
    if "RESET_LEFT_NOTE" not in note:
        out.append(f"★남은 것을 말하지 않는다: {r.get('resetNote')} — 게임별 실패가 있어도 봉투는 "
                   f"ok:true라, 무엇이 안 지워졌는지는 화면만이 말할 수 있다(F26)")
    if r.get("resetMutations") != 1:
        out.append(f"초기화 뒤 변경 통지가 {r.get('resetMutations')}회다(1이어야 한다)")

    # ═══ 4 경고 블록·제외 고지 ═══════════════════════════════════════════════
    mtexts = r.get("resetModalTexts") or []
    for key, why in (
        ("RESET_CONFIRM_WARN", "재등록 전제를 밝힌 ⚠ 경고 블록이 없다 — '백업은 남는다'만 "
                               "말하면 '언제든 되살릴 수 있다'로 읽힌다(F23·A8)"),
        ("RESET_CONFIRM_TYPE", "확인 단어 안내가 없다"),
        ("MANAGE_KEEP_CONFIG", "'게임 설정 파일은 안 건드린다'를 말하지 않는다"),
        ("RESET_CONFIRM_EXCLUDED", "감지 제외 목록도 지워진다는 고지가 없다(A9 ④)"),
    ):
        if not has_key(mtexts, key):
            out.append(f"★{why} — {mtexts}")
    if has_key(r.get("resetModalTextsNoExcluded") or [], "RESET_CONFIRM_EXCLUDED"):
        out.append("제외 0건인데 제외 고지를 그린다 — '0이면 안 그림' 문법")
    if not has_key(r.get("resetModalTextsNoExcluded") or [], "RESET_CONFIRM_WARN"):
        out.append("제외 0건 확인창에 ⚠ 경고 블록이 없다 — 경고는 제외와 무관하다")

    # ═══ 5 입력값 보존 ═══════════════════════════════════════════════════════
    if not r.get("snapshotSpecFound"):
        out.append("입력 보존을 잴 확인창을 못 꺼냈다")
    elif r.get("reopenedInitial") != "dele":
        out.append(f"★치다 만 입력이 다음 확인창에 복원되지 않는다({r.get('reopenedInitial')!r}) — "
                   f"가상 키보드로 찍은 값이 B 오조작 한 번에 사라진다(GP#9)")

    # ═══ 6 표시 이름 ═════════════════════════════════════════════════════════
    if r.get("renameButtons") != 2:
        out.append(f"이름 바꾸기 버튼이 {r.get('renameButtons')}개다(프로필 2개 = 2개)")
    if not r.get("renameMirrored"):
        out.append("이름 편집창을 못 꺼냈다 — 대조가 항진식이다")
    else:
        if r.get("renameOkDisabled"):
            out.append("이름 편집창의 OK가 비활성이다 — 빈 입력은 '기본 이름으로 되돌리기'라 "
                       "막으면 안 된다")
        rename = r.get("renameCall") or []
        if not rename or rename[0] != "dock":
            out.append(f"★이름 변경 RPC의 첫 인자가 식별자가 아니다: {rename} "
                       f"★표시명이 식별자 자리로 샜다")
        if not any(isinstance(v, dict) and v.get("dock") == "거실 TV" for v in (r.get("renameSyncs") or [])):
            out.append(f"백엔드가 정규화한 결과를 i18n에 반영하지 않는다: {r.get('renameSyncs')}")
        if not has_key(r.get("renameNote") or [], "NAME_EDIT_OK_NOTE"):
            out.append(f"이름 변경 결과를 화면이 말하지 않는다: {r.get('renameNote')}")
        if r.get("renameMutations") != 1:
            out.append(f"이름 변경 뒤 변경 통지가 {r.get('renameMutations')}회다(1이어야 한다)")

    # ═══ 7 A4 전역 전용 ══════════════════════════════════════════════════════
    for key in ("SETTINGS_TITLE", "SETTINGS_NAMES_TITLE", "SETTINGS_RESET_TITLE"):
        if not has_key(r.get("sectionTitles") or [], key):
            out.append(f"구획 제목 {key}가 없다: {r.get('sectionTitles')}")
    if sorted(r.get("allButtons") or []) != ["MANAGE_NAME_EDIT", "MANAGE_NAME_EDIT", "RESET_OPEN"]:
        out.append(f"★설정 팝업에 전역 동작 밖의 버튼이 있다: {r.get('allButtons')} — "
                   f"설정은 **전역 전용**이고 게임별 동작과 완전히 분리된다(A4)")
    if r.get("perGameLeak"):
        out.append("설정 팝업에 목록 필터류 컨트롤이 들어왔다 — 게임별 화면과 섞이고 있다(A4)")
    return out


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    result, err = run_probe(ROOT / "src")
    if result is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1

    bad = violations(result)
    print("팝업 S 설정 계약 (렌더+클릭으로 측정)")
    print(f"  활성: 등록2={(result.get('base') or {}).get('enabled')} · "
          f"게임0/제외1={(result.get('excludedOnly') or {}).get('enabled')} · "
          f"아무것도없음={(result.get('nothing') or {}).get('enabled')} · "
          f"조회실패={(result.get('loadFailed') or {}).get('enabled')} · "
          f"로딩={(result.get('loading') or {}).get('enabled')}")
    print(f"  초기화: 1차 토큰={((result.get('resetCall1') or [None])[0])} · OK 잠금 "
          f"{result.get('resetOkBefore')}→{result.get('resetOkTyped')} · 확정={result.get('resetCall2')}")
    print(f"  보존={result.get('reopenedInitial')!r} · 이름 변경={result.get('renameCall')}")
    if bad:
        print("\nFAIL")
        for b in bad:
            print("  " + b)
        return 1

    for label, target, pattern, replacement in BYPASSES:
        source = (ROOT / "src" / target).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            injected, n = re.subn(pattern, replacement, source, count=1)
            if n != 1:
                print(f"FAIL — 음성 대조군 주입 실패({label}): 대상 식을 못 찾았다. 검사가 무효다.")
                return 1
            (case / target).write_text(injected, encoding="utf-8")
            control, err = run_probe(case)
            if control is None:
                print(f"FAIL — 음성 대조군 프로브 실행 실패({label}): {err}")
                return 1
            caught = violations(control)
            if not caught:
                print(f"FAIL — 위반을 주입했는데 통과했다: {label}")
                print("       **이 테스트는 그 위반에 대해 무효다.**")
                return 1
            print(f"  음성 대조군 검출: {label} → {caught[0].splitlines()[0]}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
