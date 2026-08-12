#!/usr/bin/env python3
"""팝업 G(설계 §5)의 목록·상세 계약을 **렌더+클릭으로** 잠근다. 명세 정본 §15-B ②(+ ⑤·⑥).

`qa/test_status_page.py`·`qa/test_confirm_ui.py`가 전체화면 「현황」 탭에 대해 잠그던 것을
팝업 판으로 옮기고(§15-A 이식표), 설계가 새로 요구한 것들을 더한다.
(전체화면은 P15에서 사라진다 — 그때 저 두 파일이 은퇴하고 이 파일이 그 자리를 대신한다.)

### 잠그는 것 — §15-B ② 9판정
    ① **이름순 단일 정렬**(재정렬 없음 — 화면이 바뀔 때마다 행이 움직이면 근육 기억이 무너진다)
    ② **필터 술어 = `!has_dock || !has_internal`**(현행 `StatusPage.tsx:237` 승계, R-9).
       *하나라도 없음*이지 *둘 다 없음*이 아니다 — 뒤집히면 "덜 된 게임"의 대부분이 사라진다.
    ③ **200게임 렌더**(설계 상한). 렌더 성립과 조작 확장성은 별개 문제로 기록돼 있다(GP#5).
    ④ **적용은 무확인 · 저장은 확인창**(사용자 확정). 저장 1차 호출은 **토큰 없이** 나가고,
       확정 시 **백엔드가 준 토큰을 그대로** 되돌린다. 빈 슬롯 첫 저장은 백엔드가 묻지 않으므로
       화면도 묻지 않는다(§15-C 정상 동작).
    ⑤ **마커 = `disk_matches`만**. "프로필이 있다"가 아니라 "지금 그것이 적용돼 있다"이다.
    ⑥ **빈 슬롯 적용 버튼 비활성**(A6의 유일한 시각 표현) · **저장 버튼은 활성**(첫 생성 동작).
    ⑦ **running은 칩으로만**. 적용 버튼은 활성을 유지한다 — 판정은 백엔드가 하고 화면은 사실만
       말한다(E1의 정신). 여기가 무너지면 게임 하나가 켜져 있다는 이유로 조작이 막힌다.
    ⑧ **적용 버튼 2종의 폭·아이콘 자리 동일**(GP#2). 마커 유무로 폭이 바뀌면 전 행의 버튼
       x좌표가 흔들려 수직 이동 중 커서가 좌우로 튄다.
    ⑨ **[다시 확인] → `get_overview` 재호출**(F17 — "게임을 끄고 왔는데 화면이 낡았다"의 탈출구).

### 그리고
    · **체크인 고지**(§5-E): 성공 note **와 실패 note 양쪽**에 붙는다 — 엔진은 체크인을 쓴
      **뒤에** 거부할 수 있어 *"적용은 실패했는데 프로필은 이미 바뀐"* 상태가 실재한다(D-02).
    · **상태 줄 3분기**(D11) · `PROFILES_IDENTICAL`(H3-ⓑ) · 설정 파일 경로(빈 값이면 미표시).
    · **등록 해제 안내 3종 중 2종**(§15-B ⑥): 재등록 예고는 항상, 경로는 **빈 값이면 줄 자체를
      안 그린다**(R-11). ⚠️ 리터럴이 아니라 **키 참조**로 판정한다(문구는 §10-A의 소관이다).
    · 조회 실패에 **`NO_GAMES`를 말하지 않는다** — 모르는 것을 없다고 말하지 않는다.

### 왜 렌더+클릭인가 (grep이 아니라)
이 프로젝트에서 **거짓 검사가 여섯 번** 났고 그중 둘이 *"grep이 규칙을 설명한 주석을 잡았다"*
였다. 별칭·헬퍼·파생 변수를 가리지 않는 판정은 **눌러 보고 무슨 일이 나는지 보는 것**뿐이다.

★ 이 테스트도 **자기 자신을 반증한다** — 알려진 위반 11종을 사본에 주입해 전부 검출되는지
  확인하고, 하나라도 안 잡히면 *"이 테스트는 그 위반에 대해 무효다"*라며 스스로 실패한다.
⚠️ 한계: node에서 컴포넌트를 직접 렌더한다(실제 Steam CEF·`@decky/ui`가 아니다).
  포커스·B버튼·실제 폭은 실기(§16)의 몫이다.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "games_popup_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

#: 카드 순서(이름순) × 프로필 2 — 적용 버튼 8개의 기대 비활성 상태.
#: Alpha(dock만·실행 중) · Empty(둘 다 없음) · Mid(둘 다 있음) · Zeta(둘 다 있음·dock 적용됨)
EXPECTED_APPLY_DISABLED = [False, True, True, True, False, False, False, False]
#: 마커는 **Zeta의 dock 하나**뿐이다(`disk_matches === "dock"`).
EXPECTED_MARKED_INDEX = 6

#: 알려진 위반. (설명, 대상 파일, 정규식, 치환) — 주입이 실패하면 검사가 **스스로 무효를 선언**한다.
BYPASSES = [
    ("정렬을 하지 않음(입력 순서 그대로)", "GamesPopup.tsx",
     r"\.sort\(\(a, b\) => a\.name\.localeCompare\(b\.name\)\)", ".sort(() => 0)"),
    ("필터 술어를 '둘 다 없음'으로 뒤집음", "GamesPopup.tsx",
     r"filter\(\(g\) => !g\.has_dock \|\| !g\.has_internal\)",
     "filter((g) => !g.has_dock && !g.has_internal)"),
    ("마커를 '프로필이 있으면'으로 바꿈(적용 여부가 아니라)", "GamesPopup.tsx",
     r"<span style=\{MARKER_SLOT_STYLE\}>\{game\.disk_matches === p \? <IconCheck /> : null\}</span>",
     "<span style={MARKER_SLOT_STYLE}>{has[p] ? <IconCheck /> : null}</span>"),
    ("마커 자리를 조건부로 만듦(폭 불변식 파괴)", "GamesPopup.tsx",
     r"<span style=\{MARKER_SLOT_STYLE\}>\{game\.disk_matches === p \? <IconCheck /> : null\}</span>",
     "{game.disk_matches === p ? <span style={MARKER_SLOT_STYLE}><IconCheck /></span> : null}"),
    ("빈 슬롯인데 적용 버튼을 활성으로", "GamesPopup.tsx",
     r"disabled=\{busy \|\| !has\[p\]\}", "disabled={busy}"),
    ("실행 중이면 적용 버튼을 비활성으로(E1 정신 위반)", "GamesPopup.tsx",
     r"disabled=\{busy \|\| !has\[p\]\}", "disabled={busy || !has[p] || game.running}"),
    ("[다시 확인]이 아무것도 재조회하지 않음", "GamesPopup.tsx",
     r"onClick=\{\(\) => reload\(\)\}", "onClick={() => undefined}"),
    ("저장 1차 호출에 토큰을 지어냄", "GamesPopup.tsx",
     r"runMutation\(\(\) => saveProfile\(appid, profile, token\), \"SAVE_FAILED\"",
     'runMutation(() => saveProfile(appid, profile, token ?? "MADE-UP-TOKEN"), "SAVE_FAILED"'),
    ("확정 시 받은 토큰이 아닌 값을 되돌림", "GamesPopup.tsx",
     r"void runSave\(appid, profile, p\.confirm_token\);",
     'void runSave(appid, profile, "SOMETHING-ELSE");'),
    ("체크인 고지를 뺌(조용한 덮어쓰기가 화면에서 사라진다)", "GamesPopup.tsx",
     r"setNote\(checkedIn \? `\$\{base\} \$\{t\(\"CHECKIN_ONE\", \{ profile: t\(profileKey\(checkedIn\)\) \}\)\}` : base\);",
     "setNote(base);"),
    ("등록 해제 뒤 상세 뷰에 머무름(없는 게임을 보고 있게 된다)", "GamesPopup.tsx",
     r'setView\(\{ kind: "list" \}\);\n          return;', "return;"),
    # ── §4-F 개정(P15-B): 확정 실행은 **성공·실패 무관** 재조회+통지다 ──────────
    ("확정 실행을 조회 취급(실패하면 화면이 낡은 채로 남는다)", "GamesPopup.tsx",
     r'runMutation\(\(\) => deleteGame\(appid, token\), "DELETE_ACTION_FAILED"',
     'runQuery(() => deleteGame(appid, token), "DELETE_ACTION_FAILED"'),
    # ── busy는 **훅**의 계약이라 대상 파일도 훅이다(팝업엔 방어 코드가 없다) ────
    ("reload()가 busy를 안 켬(조회 연타에 무방비 — P14 O1의 재발)", "popup.tsx",
     r"    const mine = generation\.current;\n    begin\(\);", "    const mine = generation.current;"),
    ("제외 안내를 0건에도 표시", "GamesPopup.tsx",
     r"counts && counts\.excluded > 0", "counts && counts.excluded >= 0"),
    ("설정 파일 경로 줄을 빈 값에도 그림", "confirmSpecs.tsx",
     r"\{params\.config_path \? <div style=\{META_STYLE\}>\{t\(\"DELETE_CONFIRM_PATH\", \{ path: params\.config_path \}\)\}</div> : null\}",
     '<div style={META_STYLE}>{t("DELETE_CONFIRM_PATH", { path: params.config_path })}</div>'),
]


def run_probe(src_dir):
    proc = subprocess.run([str(U1), str(PROBE), str(src_dir)],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def has_key(texts, key):
    """그 키를 **참조해서** 그린 줄이 있는가. 목의 `t()`가 키를 그대로 돌려주므로 접두로 본다."""
    return any(x == key or x.startswith(key + " ") for x in texts)


def violations(r):                                             # noqa: C901  (판정 나열)
    out = []

    # ═══ 마운트·조회 ══════════════════════════════════════════════════════════
    if r.get("mountOverviewCalls") != 1:
        out.append(f"마운트 시 조회가 {r.get('mountOverviewCalls')}회다(1이어야 한다)")
    if r.get("mountDetail") is not True:
        out.append("get_overview를 detail 없이 부른다 — 그러면 disk_matches가 안 와 마커를 그릴 수 없다")

    # ═══ ① 이름순 단일 정렬 ═══════════════════════════════════════════════════
    if r.get("listOrder") != ["Alpha", "Empty", "Mid", "Zeta"]:
        out.append(f"① 목록이 이름순이 아니다: {r.get('listOrder')}")

    # ═══ ② 필터 술어 ══════════════════════════════════════════════════════════
    if r.get("toggleLabel") != "FILTER_NO_PROFILE_ONLY":
        out.append(f"② 필터 토글 라벨이 다르다: {r.get('toggleLabel')}")
    if r.get("filteredOrder") != ["Alpha", "Empty"]:
        out.append(f"★② 필터 술어가 '하나라도 없음'이 아니다: {r.get('filteredOrder')} "
                   f"(기대 ['Alpha','Empty'] — Empty만 남으면 '둘 다 없음'으로 뒤집힌 것이다)")
    if r.get("filterAfterRoundTrip") is not True or r.get("orderAfterRoundTrip") != r.get("filteredOrder"):
        out.append(f"② 상세를 다녀오니 목록 상태가 초기화됐다 — 필터={r.get('filterAfterRoundTrip')} "
                   f"목록={r.get('orderAfterRoundTrip')} (GP#3: 목록 뷰는 리마운트하지 않는다)")

    # ═══ ③ 200게임 ════════════════════════════════════════════════════════════
    if r.get("bulkCards") != 200 or r.get("bulkApplyButtons") != 400:
        out.append(f"③ 200게임이 다 안 그려졌다 — 카드 {r.get('bulkCards')} / 적용 버튼 "
                   f"{r.get('bulkApplyButtons')}")
    if r.get("bulkExcludedNote"):
        out.append(f"③ 제외 0건인데 제외 안내를 그린다: {r.get('bulkExcludedNote')} "
                   f"(0이면 완전 미표시 — '0이면 안 그림' 문법)")
    if r.get("excludedNote") != ["GAMES_EXCLUDED_NOTE 2"]:
        out.append(f"제외 안내가 봉투의 수를 말하지 않는다: {r.get('excludedNote')}")

    # ═══ ④ 적용 무확인 · 저장 확인 ════════════════════════════════════════════
    if r.get("applyCall") != ["300", "internal"]:
        out.append(f"④ 적용 호출 인자가 다르다: {r.get('applyCall')}")
    if r.get("applyModals"):
        out.append(f"★④ 개별 적용에 확인창이 떴다({r.get('applyModals')}개) — 사용자 확정 사항이다"
                   f"(가장 자주 누르는 버튼이라 순수 마찰이다)")
    if r.get("applyReloaded") != 1 or r.get("applyMutations") != 1:
        out.append(f"④ 적용 뒤 자체 재조회·변경 통지가 없다 — 재조회 {r.get('applyReloaded')} "
                   f"통지 {r.get('applyMutations')}")
    save1 = r.get("saveCall1") or []
    if save1[:2] != ["300", "dock"]:
        out.append(f"④ 저장 1차 호출 인자가 다르다: {save1}")
    elif len(save1) > 2 and save1[2]:
        out.append(f"★④ 저장 1차 호출에 토큰이 실려 있다({save1[2]!r}) ★프론트가 토큰을 지어냈다")
    if r.get("saveModal") != 1:
        out.append(f"★④ 덮어쓰기 저장인데 확인창이 {r.get('saveModal')}개다(1이어야 한다)")
    if not has_key(r.get("saveModalTexts") or [], "SAVE_CONFIRM_BODY"):
        out.append(f"④ 저장 확인창이 무엇을 덮어쓰는지 말하지 않는다: {r.get('saveModalTexts')}")
    save2 = r.get("saveCall2") or []
    if len(save2) < 3 or save2[2] != "SAVE-TOKEN":
        out.append(f"★④ 확정 시 되돌린 토큰이 백엔드가 준 것과 다르다: {save2}")
    if r.get("emptySlotSaveCalls") != 1 or r.get("emptySlotSaveModals"):
        out.append(f"★④ 빈 슬롯 첫 저장에서 화면이 스스로 물었다 — 호출 {r.get('emptySlotSaveCalls')} "
                   f"모달 {r.get('emptySlotSaveModals')} (묻는가는 백엔드가 정한다 — §15-C)")
    if not has_key(r.get("emptySlotSaveNote") or [], "SAVE_OK"):
        out.append(f"④ 저장 성공을 화면이 말하지 않는다: {r.get('emptySlotSaveNote')}")

    # ═══ ⑤⑥⑦⑧ 적용 버튼의 관측면 ════════════════════════════════════════════
    faces = r.get("applyFaces") or []
    if len(faces) != 8:
        out.append(f"적용 버튼이 {len(faces)}개다(게임 4 × 프로필 2 = 8) — 측정 대상에 못 닿았다")
        return out
    disabled = [f["disabled"] for f in faces]
    if disabled != EXPECTED_APPLY_DISABLED:
        out.append(f"★⑥⑦ 적용 버튼 비활성 패턴이 다르다: {disabled}\n"
                   f"      기대 {EXPECTED_APPLY_DISABLED} — 빈 슬롯만 비활성이고, **실행 중은 "
                   f"비활성 사유가 아니다**(판정은 백엔드가 한다)")
    marked = [i for i, f in enumerate(faces) if f["marked"]]
    if marked != [EXPECTED_MARKED_INDEX]:
        out.append(f"★⑤ 마커가 붙은 버튼이 {marked}다(기대 [{EXPECTED_MARKED_INDEX}] = Zeta의 dock) — "
                   f"마커는 '프로필이 있다'가 아니라 **'지금 그것이 적용돼 있다'**(disk_matches)다")
    for i, f in enumerate(faces):
        if f["minWidth"] != "110px":
            out.append(f"⑧ 적용 버튼[{i}]의 폭이 고정값이 아니다: {f['minWidth']}")
        if f["slots"] != ["1em", "1em"]:
            out.append(f"★⑧ 적용 버튼[{i}]의 아이콘·마커 자리가 {f['slots']}다(['1em','1em'] 고정) — "
                       f"마커 유무로 폭이 바뀌면 전 행의 버튼 x좌표가 흔들린다(GP#2)")
        if f["marked"] and not f["background"]:
            out.append(f"⑤ 마커가 붙었는데 강조 배경이 없다[{i}] — 체크만으로는 눈에 안 든다(A7)")
        if not f["marked"] and f["background"]:
            out.append(f"⑤ 마커가 없는데 강조 배경이 붙었다[{i}]: {f['background']}")
    if r.get("runningChipCount") != 1:
        out.append(f"★⑦ 실행 중 칩이 {r.get('runningChipCount')}개다(실행 중 게임 1개 = 1)")
    if r.get("chevrons") != 4:
        out.append(f"상세 진입 버튼이 {r.get('chevrons')}개다(게임 4 = 4)")

    # ═══ ⑨ [다시 확인] ═══════════════════════════════════════════════════════
    if not r.get("refreshButton"):
        out.append("⑨ [다시 확인] 버튼이 없다 — 낡은 화면에서 빠져나갈 길이 없다(F17)")
    elif r.get("refreshCalls") != 1:
        out.append(f"★⑨ [다시 확인]을 눌렀는데 조회가 {r.get('refreshCalls')}회다(1이어야 한다)")

    # ═══ §5-E 체크인 고지 — 성공·실패 양쪽 ════════════════════════════════════
    ok_note = " ".join(r.get("applyNote") or [])
    if "APPLY_ONE_OK" not in ok_note or "CHECKIN_ONE" not in ok_note:
        out.append(f"★체크인 고지가 성공 note에 없다: {r.get('applyNote')} — 조용한 덮어쓰기+백업 "
                   f"1칸 소모가 화면에서 사라진다(F6)")
    fail_note = " ".join(r.get("applyFailNote") or [])
    if "BACKUP_FAILED" not in fail_note or "CHECKIN_ONE" not in fail_note:
        out.append(f"★체크인 고지가 **실패** note에 없다: {r.get('applyFailNote')} — 엔진은 체크인을 "
                   f"쓴 **뒤에** 거부할 수 있다. '적용은 실패했는데 프로필은 이미 바뀐' 상태에 "
                   f"화면이 침묵한다(D-02)")
    if r.get("applyFailMutations") != 1:
        out.append(f"체크인만 일어난 실패에서 변경 통지가 {r.get('applyFailMutations')}회다 — "
                   f"디스크·백업이 실제로 바뀌었으므로 QAM도 낡는다")

    # ═══ 상세 뷰 3분기 ════════════════════════════════════════════════════════
    zeta = (r.get("detailZeta") or {}).get("texts") or []
    mid = (r.get("detailMid") or {}).get("texts") or []
    empty = (r.get("detailEmpty") or {}).get("texts") or []
    if not zeta or not mid or not empty:
        out.append("상세 뷰를 못 열었다 — 측정 대상에 못 닿았다")
        return out
    if not has_key(zeta, "GAME_DETAIL_STATUS") or has_key(zeta, "GAME_DETAIL_DIVERGED"):
        out.append(f"상태 줄 분기 ①(적용됨)이 틀렸다: {[x for x in zeta if 'GAME_DETAIL' in x]}")
    if not has_key(mid, "GAME_DETAIL_DIVERGED") or has_key(mid, "GAME_DETAIL_STATUS"):
        out.append(f"상태 줄 분기 ②(어느 프로필과도 다름)가 틀렸다: {[x for x in mid if 'GAME_DETAIL' in x]}")
    if has_key(empty, "GAME_DETAIL_STATUS") or has_key(empty, "GAME_DETAIL_DIVERGED"):
        out.append(f"★상태 줄 분기 ③: 프로필이 하나도 없는데 상태를 단언한다 — "
                   f"{[x for x in empty if 'GAME_DETAIL' in x]} (없는 것은 지적하지 않는다 — A6)")
    if not has_key(mid, "PROFILES_IDENTICAL"):
        out.append("★두 프로필이 같다는 사실(H3-ⓑ)을 말하지 않는다 — 전환해도 무변화라 '고장'으로 읽힌다")
    if has_key(zeta, "PROFILES_IDENTICAL") or has_key(empty, "PROFILES_IDENTICAL"):
        out.append("두 프로필이 같지 않은 게임에까지 PROFILES_IDENTICAL을 그린다 — 봉투 값 그대로여야 한다")
    if not has_key(zeta, "GAME_CONFIG_PATH"):
        out.append("설정 파일 경로를 상시 표시하지 않는다(복구 렌즈의 요구 — §5-B)")
    if has_key(empty, "GAME_CONFIG_PATH"):
        out.append("경로가 빈 값인데 그 줄을 그린다 — 빈 값이면 안 그린다(D-08)")
    for name, view in (("Zeta", zeta), ("Mid", mid), ("Empty", empty)):
        if not has_key(view, "SAVE_GUIDE"):
            out.append(f"{name} 상세에 저장 방법 안내가 없다(H3-ⓐ)")
    empty_buttons = {b["label"]: b["disabled"] for b in (r.get("detailEmpty") or {}).get("buttons", [])}
    for lbl, want in (("SAVE_SHORT PROFILE_DOCK", False), ("SAVE_SHORT PROFILE_INTERNAL", False),
                      ("OPEN_BACKUPS 0", True)):
        if lbl not in empty_buttons:
            out.append(f"빈 게임 상세에 [{lbl}] 버튼이 없다: {sorted(empty_buttons)}")
        elif empty_buttons[lbl] != want:
            out.append(f"★빈 게임 상세의 [{lbl}] 비활성이 {empty_buttons[lbl]}다(기대 {want}) — "
                       f"저장은 **프로필을 처음 만드는 동작**이라 빈 슬롯에도 눌려야 하고, "
                       f"백업 0건 버튼은 빈 목록으로 이끌면 안 된다")

    # ═══ §15-B ⑥ 등록 해제 안내 (키 참조로 판정 — 리터럴 grep 금지) ═══════════
    del1 = r.get("deleteCall1") or []
    if len(del1) < 1 or del1[0] != "300":
        out.append(f"등록 해제 1차 호출 인자가 다르다: {del1}")
    elif len(del1) > 1 and del1[1]:
        out.append(f"★등록 해제 1차 호출에 토큰이 실려 있다({del1[1]!r}) ★프론트가 토큰을 지어냈다")
    dtexts = r.get("deleteModalTexts") or []
    if not dtexts:
        out.append("등록 해제 확인창이 안 떴다 — 측정 대상에 못 닿았다")
    else:
        if not has_key(dtexts, "DELETE_CONFIRM_REDISCOVER"):
            out.append("★§9-① 재등록·복원 경로 예고가 없다 — 등록 해제는 **감지 제외**까지 하므로 "
                       "돌아오는 길을 지우기 전에 말해야 한다(A9)")
        if not has_key(dtexts, "DELETE_CONFIRM_PATH"):
            out.append("★§9-② 설정 파일 경로가 없다 — 대피본에는 meta가 없어 경로를 아는 곳이 "
                       "삭제 전 registry뿐이다(§1-6)")
        if not has_key(dtexts, "MANAGE_KEEP_CONFIG"):
            out.append("등록 해제 확인창이 '게임 설정 파일은 안 건드린다'를 말하지 않는다")
    if has_key(r.get("deleteModalTextsNoPath") or [], "DELETE_CONFIRM_PATH"):
        out.append(f"★경로가 빈 값인데 '설정 파일:' 줄을 그린다 — {r.get('deleteModalTextsNoPath')} "
                   f"(unsafe-key 분기는 entry를 안 읽어 빈 값이 온다 — R-11)")
    del2 = r.get("deleteCall2") or []
    if len(del2) < 2 or del2[1] != "DELETE-TOKEN":
        out.append(f"★등록 해제 확정 시 되돌린 토큰이 다르다: {del2}")
    if r.get("afterDeleteButtons"):
        out.append("★등록 해제 성공 뒤에도 상세 뷰에 머문다 — 방금 지운 게임의 화면을 보고 있게 된다")
    if r.get("deleteMutations") != 1:
        out.append(f"등록 해제 뒤 변경 통지가 {r.get('deleteMutations')}회다(1이어야 한다)")

    # ═══ §4-F ② busy 통합 — 조회 중에도 목록 조작이 잠긴다(P14 O1) ════════════
    before, during, after = (r.get("busyBeforeReload") or {}, r.get("busyDuringReload") or {},
                             r.get("busyAfterReload") or {})
    if before.get("refresh") is not False or before.get("applies") != 3:
        out.append(f"조회가 없을 때부터 화면이 잠겨 있다 — {before} (기대 refresh=False·빈 슬롯 3개만 비활성)")
    if during.get("calls") != 1:
        out.append(f"★[다시 확인]이 조회를 부르지 않았다({during.get('calls')}회) — 측정 대상에 못 닿았다")
    elif during.get("refresh") is not True or during.get("applies") != 8 or during.get("chevrons") != 4:
        out.append(f"★§4-F ② 조회가 도는 중인데 화면이 열려 있다 — {during} "
                   f"(기대 refresh=True·적용 8/8·상세 4/4 비활성). `reload()`가 busy를 안 켜면 "
                   f"[다시 확인] 연타가 **조회에는 무방비**가 된다(P14 O1)")
    if after.get("refresh") is not False or after.get("applies") != 3:
        out.append(f"★응답이 왔는데 화면이 잠긴 채로 남았다 — {after} (busy가 안 풀리면 팝업이 죽는다)")

    # ═══ §4-F ③ 확정 실행 **실패**도 재조회+통지 (이월 대장 #4) ═══════════════
    dfail = r.get("deleteFail") or {}
    if not dfail.get("note"):
        out.append(f"등록 해제 실패 사유를 화면이 말하지 않는다: {dfail}")
    if dfail.get("modals"):
        out.append(f"등록 해제 실패에 확인창이 떴다({dfail.get('modals')}개)")
    if dfail.get("reloads") != 1 or dfail.get("mutations") != 1:
        out.append(f"★§4-F ③ `DELETE_FAILED`(부분 삭제)인데 재조회 {dfail.get('reloads')}회 · "
                   f"통지 {dfail.get('mutations')}회다(각 1이어야 한다) — 일부는 **이미 지워졌다.** "
                   f"확정 실행은 성공·실패를 가리지 않고 다시 읽고 알린다(P15-B 개정)")

    # ═══ 조회 실패 — 모르는 것을 없다고 말하지 않는다 ═════════════════════════
    fail_texts = r.get("failTexts") or []
    if not any("REGISTRY_UNREADABLE" in x for x in fail_texts):
        out.append(f"조회 실패 사유를 화면이 말하지 않는다: {fail_texts}")
    if any(x == "NO_GAMES" for x in fail_texts):
        out.append(f"★조회에 실패했는데 '등록된 게임이 없습니다'라고 단언한다: {fail_texts}")
    return out


def main():
    if not U1.is_file():
        # 판정 불가는 통과가 아니라 **거부**다(QA R7).
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    result, err = run_probe(ROOT / "src")
    if result is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1

    bad = violations(result)
    print("팝업 G 목록·상세 계약 (렌더+클릭으로 측정)")
    print(f"  ① 순서={result.get('listOrder')} · ② 필터={result.get('filteredOrder')} · "
          f"③ 200게임 카드={result.get('bulkCards')}")
    print(f"  ④ 적용 확인창={result.get('applyModals')} / 저장 확인창={result.get('saveModal')}"
          f"(빈 슬롯 {result.get('emptySlotSaveModals')}) · ⑨ 다시 확인={result.get('refreshCalls')}회")
    print(f"  ⑤⑧ 마커={[i for i, f in enumerate(result.get('applyFaces') or []) if f['marked']]} · "
          f"⑦ 실행 중 칩={result.get('runningChipCount')} · 체크인 note={result.get('applyNote')}")
    print(f"  §4-F ② busy: 조회 전 {result.get('busyBeforeReload')} → 조회 중 "
          f"{result.get('busyDuringReload')} → 응답 뒤 {result.get('busyAfterReload')}")
    print(f"  §4-F ③ 확정 실행 실패(DELETE_FAILED): {result.get('deleteFail')}")
    if bad:
        print("\nFAIL")
        for b in bad:
            print("  " + b)
        return 1

    # ── 음성 대조군: 알려진 위반이 지금도 잡히는가 ─────────────────────────────
    for label, target, pattern, replacement in BYPASSES:
        source = (ROOT / "src" / target).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            injected, n = re.subn(pattern, replacement, source, count=1)
            if n != 1:
                # 주입이 안 됐는데 "통과"로 읽는 것이 이 프로젝트에서 세 번 난 사고다.
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
