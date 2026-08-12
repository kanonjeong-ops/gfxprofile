#!/usr/bin/env python3
"""백업 뷰·복원 UI의 계약을 **렌더+클릭으로** 잠근다. 명세 정본 §15-B ⑦ (P13 재작성).

`qa/test_restore_route.py`가 백엔드 계약(3-상태·토큰·경로 봉쇄)을 잠그고, 이 파일은
**화면이 그 계약을 지키는가**를 잰다. 둘은 서로를 대체하지 않는다 —
백엔드가 아무리 옳아도 프론트가 토큰을 지어내거나 확인창을 건너뛰면 계약은 화면에서 깨진다.

⚠️ **P13에서 대상이 바뀌었다**: 「관리」 탭의 백업 모달 → **팝업 G의 상세 → 백업 뷰**(§15-A).
   흐름(3-상태·토큰·2단계 시맨틱)은 그대로 승계하고, 아래 D-07이 새로 붙었다.

### 잠그는 것
1. 상세의 `[백업 복원 (N)]`으로 백업 뷰에 들어가고, `[복원]` **1차 호출은 토큰 없이** 나간다
   (프론트가 토큰을 지어내면 계약이 무너진다).
2. `CONFIRM_REQUIRED`면 확인창이 뜨고, 확정 시 **백엔드가 준 토큰을 그대로** 되돌린다.
3. ★★ **복원 성공 뒤 재조회**(Codex D-07): 복원은 disk 대피본을 하나 만든다
   (`engine.py:705-709`) — 그 자리에서 ⓐ `list_backups` 재조회 ⓑ `get_overview` 재조회
   ⓒ 변경 통지가 나가야 한다. 안 하면 **방금 사라진 백업의 [복원] 버튼**이 화면에 남는다.
   기대 행 수는 **`min(old + 1, BACKUP_KEEP)`** 이다 — 링이 차 있으면 "+1"은 거짓이고,
   그때는 **최고령 행이 퇴출**된다(N-04).
4. `already`는 **무쓰기**다(백엔드 계약 §15-C 불변) — 링이 안 밀렸으므로 **백업 목록은 다시
   읽지 않는다**. 다만 overview 재조회·변경 통지는 **확정 실행의 문**을 그대로 지난다
   (P15-B §4-F ③ 개정: 무쓰기 판정은 봉투의 `CONFIRM_REQUIRED` 하나뿐이고, 프론트가
   outcome으로 다시 판정하면 그 판정이 백엔드와 갈리는 날 화면만 낡는다).
5. 후속 제안(2단계의 ②)은 **`kind`가 `profile_*`일 때만** 뜬다. 실사용 백업 다수인 `disk`는
   *"오지 않을 창"*을 약속하지 않고 `RESTORE_OK_MANUAL`로 남은 길을 알려 준다(R2·F7).
6. **복원은 성공했는데 후속 창만 못 뜬 경우**(R1): 디스크는 이미 다시 쓰였고 링도 1칸
   소모됐다 — 여기서 *"아무것도 지우지 않았습니다"*가 뜨면 **화면의 마지막 말이 사실과 반대**다.
7. 실행 중 게임의 조기 거부(`GAME_RUNNING`)에는 **확인창을 띄우지 않는다** — 확실히 거부될
   확인을 사용자에게 시키지 않는다.
8. **양 모드 주행**: `NESTED_CONFIRM` true/false 각각에서 같은 문구·같은 토큰 왕복이 성립하고,
   폴백에서는 오버레이가 떠 있는 동안 원 콘텐츠가 **렌더되지 않는다**(D-05 ⑤).

★ 이 테스트도 **자기 자신을 반증한다** — 알려진 위반 11종을 주입해 전부 검출되는지 본다.
⚠️ 한계: node에서 컴포넌트를 직접 렌더한다. **빅픽처 실기 관찰을 대체하지 않는다.**
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "restore_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)
TOKEN = "RESTORE-TOKEN"
FIRST_BACKUP = "20260810-090300"
BACKUP_KEEP = 10

BYPASSES = [
    ("복원 뒤 백업 목록을 다시 안 읽음(사라진 백업의 버튼이 남는다)", "GamesPopup.tsx",
     r'setNote\(t\("RESTORE_OK", \{ stamp \}\)\);\n          refreshBackups\(game\.appid\);',
     'setNote(t("RESTORE_OK", { stamp }));'),
    ("already에서 백업 목록까지 다시 읽음(링이 안 밀렸는데 쓸데없는 왕복)", "GamesPopup.tsx",
     r'setNote\(t\("RESTORE_ALREADY"\)\);\n            return;',
     'setNote(t("RESTORE_ALREADY"));\n            refreshBackups(game.appid);\n            return;'),
    ("복원을 조회 취급(확정 실행인데 overview·통지가 안 나간다)", "GamesPopup.tsx",
     r'runMutation\(\(\) => restoreBackup\(game\.appid, row\.backup_id, token\), "RESTORE_FAILED"',
     'runQuery(() => restoreBackup(game.appid, row.backup_id, token), "RESTORE_FAILED"'),
    ("복원 1차 호출에 토큰을 지어냄", "GamesPopup.tsx",
     r"restoreBackup\(game\.appid, row\.backup_id, token\), \"RESTORE_FAILED\"",
     'restoreBackup(game.appid, row.backup_id, token ?? "MADE-UP-TOKEN"), "RESTORE_FAILED"'),
    ("확정 시 받은 토큰이 아닌 값을 되돌림", "GamesPopup.tsx",
     r"void runRestore\(game, row, p\.confirm_token\);",
     'void runRestore(game, row, "SOMETHING-ELSE");'),
    ("조기 거부에도 확인창을 띄움(확실히 거부될 확인을 시킨다)", "GamesPopup.tsx",
     r'if \(res\.code === "CONFIRM_REQUIRED"\) \{\n          const p = res\.params as unknown as RestoreConfirmParams;',
     'if (res.code !== "__never__") {\n          const p = res.params as unknown as RestoreConfirmParams;'),
    ("후속 제안 실패 문구를 삭제용 하나로 합침(성공 뒤에 '안 지웠습니다'가 뜬다)", "GamesPopup.tsx",
     r'"RESTORE_FOLLOWUP_MODAL_FAILED",', '"MANAGE_MODAL_FAILED",'),
    ("disk 복원 뒤 남은 길을 안 알려 줌", "GamesPopup.tsx",
     r'setNote\(t\("RESTORE_OK_MANUAL", \{ stamp \}\)\);', 'setNote(t("RESTORE_OK", { stamp }));'),
    ("최신순 힌트를 뺌(사용자가 정반대 행을 고른다)", "GamesPopup.tsx",
     r'<div style=\{HINT_STYLE\}>\{t\("BACKUP_LIST_ORDER_HINT"\)\}</div>', ""),
    ("후속 제안 예고를 조건 없이 표시(오지 않을 창을 약속한다)", "GamesPopup.tsx",
     r'\{hasProfileRow \? <div style=\{HINT_STYLE\}>\{t\("BACKUP_LIST_FOLLOWUP_HINT"\)\}</div> : null\}',
     '<div style={HINT_STYLE}>{t("BACKUP_LIST_FOLLOWUP_HINT")}</div>'),
    ("복원 확인창이 disk 백업에도 후속 제안을 약속", "confirmSpecs.tsx",
     r'\{fromProfile \? t\("RESTORE_CONFIRM_SLOT_ASK"\) : t\("RESTORE_CONFIRM_SLOT_NOTE"\)\}',
     '{t("RESTORE_CONFIRM_SLOT_ASK")}'),
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
    if not r.get("anchorFound"):
        out.append("★NESTED_CONFIRM 앵커를 못 찾았다 — 폴백 모드를 **한 번도 안 재고** 통과할 뻔했다")

    nested = r.get("nested") or {}
    if not nested.get("reached"):
        out.append("백업 뷰까지 못 갔다 — 측정 대상에 못 닿았다")
        return out

    # ═══ 1·2 3-상태와 토큰 ═══════════════════════════════════════════════════
    call1 = nested.get("call1") or []
    if call1[:2] != ["300", FIRST_BACKUP]:
        out.append(f"복원 1차 호출 인자가 다르다: {call1}")
    elif len(call1) > 2 and call1[2]:
        out.append(f"★복원 1차 호출에 토큰이 실려 있다({call1[2]!r}) ★프론트가 토큰을 지어냈다")
    ctexts = nested.get("confirmTexts") or []
    if not has_key(ctexts, "RESTORE_CONFIRM_BODY"):
        out.append(f"복원 확인창이 무엇을 덮어쓰는지 말하지 않는다: {ctexts}")
    if not has_key(ctexts, "RESTORE_CONFIRM_SLOT_ASK"):
        out.append(f"프로필 대피본 확인창이 후속 제안을 예고하지 않는다: {ctexts}")
    call2 = nested.get("call2") or []
    if len(call2) < 3 or call2[2] != TOKEN:
        out.append(f"★확정 시 되돌린 토큰이 백엔드가 준 것과 다르다: {call2}")

    # ═══ 3 D-07 재조회 ═══════════════════════════════════════════════════════
    before_rows = (nested.get("before") or {}).get("rows")
    if nested.get("listAfter") != 1:
        out.append(f"★복원 성공 뒤 백업 목록을 다시 읽지 않는다({nested.get('listAfter')}회) — "
                   f"복원이 대피본을 하나 만들어 행이 바뀌는데, 화면에는 **방금 사라진 백업의 "
                   f"[복원] 버튼**이 남는다(D-07)")
    if nested.get("overviewAfter") != 1:
        out.append(f"★복원 성공 뒤 overview를 다시 읽지 않는다({nested.get('overviewAfter')}회) — "
                   f"백업 수·디스크 상태가 낡은 채로 남는다")
    expected_rows = min((before_rows or 0) + 1, BACKUP_KEEP)
    if nested.get("rowsAfter") != expected_rows:
        out.append(f"복원 뒤 행 수가 {nested.get('rowsAfter')}다(기대 min({before_rows}+1,"
                   f"{BACKUP_KEEP})={expected_rows})")
    metas = nested.get("metasAfter") or []
    if not metas or "T-NEW" not in metas[0]:
        out.append(f"★맨 위 행이 방금 만들어진 대피본이 아니다: {metas[:2]} — 목록은 최신순이다")
    if not nested.get("stillOnBackupView"):
        out.append("복원 뒤 백업 뷰를 떠났다 — 연속 복원 시나리오가 끊긴다(D-07: 화면은 머문다)")
    if not nested.get("mutations"):
        out.append("복원 뒤 변경 통지가 없다 — QAM이 낡은 값을 말하게 된다")

    ring = r.get("ring") or {}
    if ring.get("beforeRows") != BACKUP_KEEP or ring.get("afterRows") != BACKUP_KEEP:
        out.append(f"★링이 가득 찬 상태의 행 수가 {ring.get('beforeRows')}→{ring.get('afterRows')}다 — "
                   f"상한은 {BACKUP_KEEP}이고 '+1' 단순 기대는 포화 시 거짓이다(N-04)")
    if not ring.get("newestFirst"):
        out.append("포화 상태에서 새 대피본이 맨 위에 오지 않았다")
    if not ring.get("evictedGone"):
        out.append("★포화 상태에서 최고령 행이 화면에 그대로 남아 있다 — 눌러도 없는 파일이다")

    # ═══ 4 already — 링은 그대로, overview는 확정 실행처럼 다시 읽는다 ═══════
    already = r.get("already") or {}
    if already.get("listAfter"):
        out.append(f"★`already`인데 백업 목록을 다시 읽었다({already.get('listAfter')}회) — "
                   f"링이 안 밀렸으므로 행은 한 줄도 안 바뀐다")
    if already.get("overviewAfter") != 1 or already.get("mutations") != 1:
        out.append(f"★`already`가 확정 실행의 문을 지나지 않았다 — overview "
                   f"{already.get('overviewAfter')}회 · 통지 {already.get('mutations')}회"
                   f"(각 1이어야 한다). 무쓰기 판정은 **봉투의 `CONFIRM_REQUIRED` 하나**이고, "
                   f"프론트가 outcome으로 다시 판정하면 그 판정이 백엔드와 갈리는 날 화면만 "
                   f"낡는다(P15-B §4-F ③ 개정 — 백엔드의 '무쓰기' 계약 자체는 불변)")
    if already.get("modals"):
        out.append(f"`already`에 확인창이 떴다({already.get('modals')}개)")
    if not has_key(already.get("notes") or [], "RESTORE_ALREADY"):
        out.append(f"`already`를 실패처럼 말한다: {already.get('notes')}")

    # ═══ 5 disk 대피본 ═══════════════════════════════════════════════════════
    disk = r.get("disk") or {}
    dtexts = disk.get("confirmTexts") or []
    if has_key(dtexts, "RESTORE_CONFIRM_SLOT_ASK"):
        out.append(f"★disk 백업 확인창이 후속 제안을 약속한다 — 그 창은 오지 않는다: {dtexts}")
    if not has_key(dtexts, "RESTORE_CONFIRM_SLOT_NOTE"):
        out.append(f"disk 백업 확인창에 '프로필은 그대로' 안내가 없다: {dtexts}")
    if disk.get("modalsAfter") != 1:
        out.append(f"disk 복원 뒤 창이 {disk.get('modalsAfter')}개다(확인창 1개뿐이어야 한다)")
    if not has_key(disk.get("notes") or [], "RESTORE_OK_MANUAL"):
        out.append(f"★disk 복원 뒤 남은 길(프로필 저장)을 알려 주지 않는다: {disk.get('notes')} — "
                   f"이 내용은 다음 적용 때 프로필 내용으로 되돌아간다(F7)")

    # ═══ 6 후속 창만 실패 ════════════════════════════════════════════════════
    tail = (r.get("followUpFailed") or {}).get("notes") or []
    if any("MANAGE_MODAL_FAILED" in x for x in tail):
        out.append(f"★복원이 성공했는데 '아무것도 지우지 않았습니다'가 떴다 ★화면이 거짓을 말한다: {tail}")
    if not any("RESTORE_FOLLOWUP_MODAL_FAILED" in x for x in tail):
        out.append(f"후속 제안 실패의 전용 안내가 없다: {tail}")

    # ═══ 7 조기 거부 ═════════════════════════════════════════════════════════
    refused = r.get("refused") or {}
    if refused.get("modals"):
        out.append(f"★조기 거부(GAME_RUNNING)인데 확인창이 떴다({refused.get('modals')}개) — "
                   f"확실히 거부될 확인을 사용자에게 시키지 않는다")
    if not any("GAME_RUNNING" in x for x in (refused.get("notes") or [])):
        out.append(f"거부 사유를 화면이 말하지 않는다: {refused.get('notes')}")

    # ═══ 8 양 모드 ═══════════════════════════════════════════════════════════
    fb = r.get("fallback") or {}
    if not fb.get("reached"):
        out.append("폴백 모드에서 백업 뷰까지 못 갔다")
    else:
        if sorted(fb.get("confirmTexts") or []) != sorted(ctexts):
            out.append(f"★폴백 모드의 확인창 문구가 다르다 — 모드를 바꾸는 순간 사용자가 보는 "
                       f"내용이 바뀐다\n      중첩={sorted(ctexts)}\n      폴백={sorted(fb.get('confirmTexts') or [])}")
        if fb.get("modalsUsed"):
            out.append(f"폴백 모드인데 showModal을 {fb.get('modalsUsed')}회 썼다")
        if not fb.get("bodyHiddenDuringConfirm"):
            out.append("★폴백 오버레이가 떠 있는데 백업 목록이 함께 렌더된다 — 포커스가 뒤 "
                       "콘텐츠로 갈 수 있다. 격리는 숨김이 아니라 **미렌더**여야 한다(D-05 ⑤)")
        fb2 = fb.get("call2") or []
        if len(fb2) < 3 or fb2[2] != TOKEN:
            out.append(f"★폴백 모드에서 토큰 왕복이 깨졌다: {fb2}")

    # ═══ 백업 뷰의 안내 (§5-C) ═══════════════════════════════════════════════
    hints = r.get("hints") or []
    for key in ("BACKUP_LIST_HINT", "BACKUP_LIST_ORDER_HINT", "BACKUP_RING_HINT",
                "BACKUP_LIST_FOLLOWUP_HINT"):
        if not has_key(hints, key):
            out.append(f"백업 뷰에 {key} 안내가 없다: {hints}")
    if has_key(r.get("hintsDiskOnly") or [], "BACKUP_LIST_FOLLOWUP_HINT"):
        out.append(f"★프로필 대피본이 하나도 없는데 '복원 뒤에 물어본다'고 예고한다: "
                   f"{r.get('hintsDiskOnly')} — 그 창은 오지 않는다")
    if not has_key(r.get("hintsDiskOnly") or [], "BACKUP_RING_HINT"):
        out.append("disk만 있는 링에서 밀려남 안내가 사라졌다")

    # ═══ 후속 제안 → 기존 저장 흐름 ══════════════════════════════════════════
    if not has_key(nested.get("followUpTexts") or [], "RESTORE_FOLLOWUP_TITLE"):
        out.append(f"프로필 대피본 복원 뒤 후속 제안이 안 떴다: {nested.get('followUpTexts')}")
    saves = nested.get("saveCalls") or []
    if not saves or saves[0][:2] != ["300", "dock"]:
        out.append(f"후속 제안을 확정했는데 저장이 안 나갔다: {saves}")
    elif len(saves[0]) > 2 and saves[0][2]:
        out.append("후속 저장의 1차 호출에 토큰이 실려 있다 ★저장 계약도 무너진다")
    return out


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")     # 판정 불가는 통과가 아니라 거부다(QA R7)
        return 1

    result, err = run_probe(ROOT / "src")
    if result is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1

    bad = violations(result)
    nested = result.get("nested") or {}
    print("백업 뷰·복원 UI 계약 (렌더+클릭으로 측정)")
    print(f"  1차 무토큰={not (nested.get('call1') or [None, None, None])[2]} · 확정 토큰 반환="
          f"{(nested.get('call2') or [None, None, None])[2] == TOKEN} · 폴백 모드 왕복="
          f"{((result.get('fallback') or {}).get('call2') or [None, None, None])[2] == TOKEN}")
    print(f"  D-07 재조회: 목록 {nested.get('listAfter')}회 · overview {nested.get('overviewAfter')}회 · "
          f"행 {(nested.get('before') or {}).get('rows')}→{nested.get('rowsAfter')} · "
          f"포화 {result.get('ring')}")
    print(f"  already: 백업목록 {(result.get('already') or {}).get('listAfter')}회 · overview "
          f"{(result.get('already') or {}).get('overviewAfter')}회 · 통지 "
          f"{(result.get('already') or {}).get('mutations')}회 · "
          f"disk note={(result.get('disk') or {}).get('notes')}")
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
