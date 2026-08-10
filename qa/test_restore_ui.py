#!/usr/bin/env python3
"""복원 UI의 계약을 **렌더+클릭으로** 잠근다 (P9 구현 / P10에서 상설화).

`qa/test_restore_route.py`가 백엔드 계약(3-상태·토큰·경로 봉쇄)을 잠그고, 이 파일은
**화면이 그 계약을 지키는가**를 잰다. 둘은 서로를 대체하지 않는다 —
백엔드가 아무리 옳아도 프론트가 토큰을 지어내거나 확인창을 건너뛰면 계약은 화면에서 깨진다.

### 잠그는 것
1. `[백업 N]`은 **백엔드가 센 수**를 라벨에 쓰고, **0건이면 비활성**이다
   (눌러도 빈 목록으로 이끄는 버튼은 라벨이 거짓말을 한다 — QA R5의 문법).
2. 누르면 `list_backups`가 **그 게임 하나**에 대해 나가고 목록 모달이 뜬다(읽기 전용 진입).
3. `[복원]` **1차 호출은 토큰 없이** 나간다 — 프론트가 토큰을 지어내면 계약이 무너진다.
4. `CONFIRM_REQUIRED`면 **파괴 표시가 붙은 확인창**이 뜨고, 확정 시 **백엔드가 준 토큰을
   그대로** 되돌린다(지어낸 값이면 백엔드가 거부한다 — 화면이 조용히 실패한다).
5. **표시 이름 변경**(F11 ①)은 RPC 첫 인자로 **식별자**를 보낸다 — 표시명이 그 자리로 새면
   저장된 프로필이 길을 잃는다. 편집창의 OK는 **항상 활성**이다(빈 입력 = 기본값 되돌리기).
6. 복원 성공(`kind=profile_*`) 뒤 **2단계 후속 제안**이 뜨고, 확정하면 기존 저장 흐름
   (`save_profile`)이 나간다. ①에서 멈춘 상태도 정상이므로 제안은 강요가 아니다.

### 왜 렌더+클릭인가 (grep이 아니라)
`test_confirm_ui`와 같은 이유다 — 이 프로젝트에서 **거짓 검사가 여섯 번** 나왔고 그중 둘이
*"grep이 규칙을 설명한 주석을 잡았다"*였다. 별칭·헬퍼·파생 변수를 가리지 않는 판정은
**눌러 보고 무슨 일이 나는지 보는 것**뿐이다.

★ 이 테스트는 **자기 자신을 반증한다** — 알려진 위반 7종을 주입해 전부 검출되는지 확인하고,
  하나라도 안 잡히면 *"이 테스트는 무효다"*라며 스스로 실패한다.
⚠️ 한계: node에서 컴포넌트를 직접 렌더한다(실제 Steam CEF·@decky/ui가 아니다).
  **빅픽처 실기 관찰을 대체하지 않는다** — 실기는 "보인다·눌린다"까지, 이 검사는 계약까지다.
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
TOKEN = "RESTORE-TOKEN"          # 프로브가 백엔드 대신 돌려주는 값
BACKUP_ID = "20260809-221532-profile_dock-video.ini"

#: 알려진 위반 7종. (설명, 정규식, 치환) — 전부 `src/ManageTab.tsx`에 주입한다.
#: 목록이 낡아 주입이 실패하면 테스트가 **스스로 무효를 선언한다**(fail-closed).
BYPASSES = [
    (
        "1차 호출에 토큰을 지어냄",
        r"return restoreBackup\(game\.appid, row\.backup_id, token\)",
        'return restoreBackup(game.appid, row.backup_id, token ?? "MADE-UP-TOKEN")',
    ),
    (
        "확정 시 받은 토큰이 아닌 값을 되돌림",
        r"onConfirm=\{\(\) => \{ void runRestore\(game, row, p\.confirm_token\); \}\}",
        'onConfirm={() => { void runRestore(game, row, "SOMETHING-ELSE"); }}',
    ),
    (
        # ★ F11 ①: 표시명이 **식별자 자리**로 새는 형태 — 이 기능의 유일한 치명 실패 모드다.
        "이름 변경 RPC에 식별자 대신 표시명을 보냄",
        r"onConfirm=\{\(name\) => \{ void runRename\(profile, name\); \}\}",
        "onConfirm={(name) => { void runRename(current as never, name); }}",
    ),
    (
        # ★ R2: 문구를 다시 조건 없이 약속하는 회귀 — disk 백업에서 거짓이 된다.
        "후속 제안 약속을 무조건 표시",
        r'\? t\("RESTORE_CONFIRM_SLOT_ASK"\)\n\s*: t\("RESTORE_CONFIRM_SLOT_NOTE"\)',
        '? t("RESTORE_CONFIRM_SLOT_ASK")\n              : t("RESTORE_CONFIRM_SLOT_ASK")',
    ),
    (
        # ★ R1: 경로별 문구를 다시 하나로 합치는 회귀 — 복원 성공 뒤에 "안 지웠습니다"가 뜬다.
        "모달 실패 문구를 삭제용 하나로 합침",
        r'"RESTORE_FOLLOWUP_MODAL_FAILED",',
        '"MANAGE_MODAL_FAILED",',
    ),
    (
        # ★ R3: 갱신 경로에서 표시명 반영을 뺀다 — 초기화 뒤 옛 이름이 화면에 남는다.
        "갱신(load)에서 표시명 반영 제거",
        r"        if \(res\.ok\) setProfileNames\(res\.data\.profile_names\);\n",
        "",
    ),
    (
        "백업 0건인데 버튼이 활성(빈 목록으로 이끈다)",
        r"disabled=\{busy \|\| game\.backups === 0\}",
        "disabled={busy}",
    ),
]


def run_probe(src_dir):
    proc = subprocess.run([str(U1), str(PROBE), str(src_dir)],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-1:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def violations(r):
    """계약 위반의 관찰 가능한 형태. 하나라도 있으면 화면이 계약을 안 지킨 것이다."""
    out = []
    labels = [b["label"] for b in r.get("backupButtons", [])]
    if len(labels) != 2:
        out.append(f"[백업 N] 버튼이 {len(labels)}개다(2개여야 한다 — 측정 대상에 못 닿았다)")
        return out
    if "3" not in labels[0]:
        out.append(f"라벨에 백엔드가 센 수가 없다: {labels[0]!r}")
    if r["backupButtons"][0]["disabled"]:
        out.append("백업이 있는 게임의 버튼이 비활성이다")
    if not r["backupButtons"][1]["disabled"]:
        out.append("백업 0건인데 버튼이 활성이다 — 없는 조작을 권한다")
    calls = r.get("listCalls") or []
    # 목록은 **누른 그 게임**만 조회한다(다른 게임의 백업을 긁어오지 않는다).
    # 호출 횟수는 시나리오가 목록을 여러 번 열므로 세지 않는다 — appid만 본다.
    if not calls or any(c != ["100"] for c in calls):
        out.append(f"list_backups 호출 인자가 잘못됐다: {calls}")
    if r.get("modal1") != "ModalRoot":
        out.append(f"목록이 ModalRoot로 뜨지 않았다: {r.get('modal1')}")
    if r.get("restoreButtons") != 2:
        out.append(f"목록의 [복원] 버튼이 {r.get('restoreButtons')}개다(백업 2건 = 2개)")
    call1 = r.get("restoreCall1") or []
    if len(call1) < 3 or call1[0] != "100" or call1[1] != BACKUP_ID:
        out.append(f"1차 복원 호출 인자가 다르다: {call1}")
    elif call1[2]:
        out.append(f"1차 복원 호출에 토큰이 실려 있다({call1[2]!r}) ★프론트가 토큰을 지어냈다")
    if r.get("modal2") != "ConfirmModal":
        out.append(f"복원 확인창이 ConfirmModal이 아니다: {r.get('modal2')}")
    if not r.get("modal2Destructive"):
        out.append("복원 확인창에 bDestructiveWarning이 없다 — 되돌리기 어려운 동작임을 안 말한다")
    call2 = r.get("restoreCall2") or []
    if len(call2) < 3 or call2[2] != TOKEN:
        out.append(f"확정 시 되돌린 토큰이 백엔드가 준 것과 다르다: {call2}")
    if r.get("modal3") != "ConfirmModal" or r.get("modal3Title") != "RESTORE_FOLLOWUP_TITLE":
        out.append(f"2단계 후속 제안이 안 떴다: {r.get('modal3')} / {r.get('modal3Title')}")
    # ── F11 ①: 표시 이름 변경도 같은 화면이다. **식별자가 화면 경계에서 안 움직이는지** 본다.
    if r.get("renameButtons") != 2:
        out.append(f"이름 바꾸기 버튼이 {r.get('renameButtons')}개다(프로필 2개 = 2개)")
    if r.get("nameModal") != "ConfirmModal":
        out.append(f"이름 편집창이 ConfirmModal이 아니다: {r.get('nameModal')}")
    if r.get("nameModalOkDisabled"):
        out.append("이름 편집창의 OK가 비활성이다 — 빈 입력은 '기본 이름으로 되돌리기'라 막으면 안 된다")
    renames = r.get("renameCalls") or []
    if not renames or renames[0][0] != "dock":
        out.append(f"이름 변경 RPC의 첫 인자가 식별자가 아니다: {renames} ★표시명이 식별자 자리로 샜다")
    # ── R2(2026-08-10 QA): **오지 않을 후속 제안을 약속하지 않는다** ────────────────
    #    후속 제안은 `kind`가 `profile_*`일 때만 뜬다. 실사용 백업은 대부분 `disk`(적용·복원
    #    직전 대피본)라, 조건 없는 약속은 **대다수 경로에서 거짓**이 된다.
    prof_texts = " ".join(r.get("modal2Texts") or [])
    disk_texts = " ".join(r.get("diskConfirmTexts") or [])
    if not disk_texts:
        out.append("disk 백업의 확인창 문구를 못 읽었다 — 측정 대상에 못 닿았다")
    else:
        if "RESTORE_CONFIRM_SLOT_ASK" in disk_texts:
            out.append("disk 백업 확인창이 후속 제안을 약속한다 ★그 창은 오지 않는다")
        if "RESTORE_CONFIRM_SLOT_NOTE" not in disk_texts:
            out.append(f"disk 백업 확인창에 '프로필은 그대로' 안내가 없다: {disk_texts}")
    if "RESTORE_CONFIRM_SLOT_ASK" not in prof_texts:
        out.append(f"프로필 대피본 확인창이 후속 제안을 예고하지 않는다: {prof_texts}")

    # ── R1(2026-08-10 QA): **복원 성공 뒤 후속 창만 실패**했을 때 화면이 하는 말 ────────
    #    디스크는 이미 다시 쓰였고 백업 링도 1칸 소모됐다. 여기서 "아무것도 지우지
    #    않았습니다"가 뜨면 **마지막 말이 사실과 반대**다(공유 문구 하나가 5경로를 덮던 결함).
    tail = r.get("notesAfterFollowUpModalFailure") or []
    if not tail:
        out.append("복원 성공 뒤 후속 창 실패 시나리오에서 아무 안내도 안 떴다 — 흔적 없이 죽는다")
    else:
        if any("MANAGE_MODAL_FAILED" in n for n in tail):
            out.append(f"복원이 성공했는데 '아무것도 지우지 않았습니다'가 떴다 ★화면이 거짓을 말한다: {tail}")
        if not any("RESTORE_FOLLOWUP_MODAL_FAILED" in n for n in tail):
            out.append(f"후속 제안 실패의 전용 안내가 없다: {tail}")
        if not any("RESTORE_OK" in n for n in tail):
            out.append(f"복원이 성공했다는 사실이 화면에서 사라졌다: {tail}")

    # ── R3(2026-08-10 QA): 목록 갱신 경로가 **표시명을 i18n에 반영**하는가 ──────────────
    #    이 한 줄이 빠져 전체 초기화 뒤에도 옛 커스텀 이름이 화면에 남았다(확인창의 약속이 거짓).
    syncs = r.get("nameSyncs") or []
    if not syncs:
        out.append("갱신(load)이 표시명을 i18n에 반영하지 않는다 ★초기화·변경 뒤 옛 이름이 남는다")
    elif not any(isinstance(v, dict) and v.get("dock") == "다시 읽은 이름" for v in syncs):
        out.append(f"갱신이 봉투의 표시명을 그대로 반영하지 않았다: {syncs[:3]}")

    saves = r.get("saveCalls") or []
    if not saves or saves[0][:2] != ["100", "dock"]:
        out.append(f"후속 제안을 확정했는데 저장이 안 나갔다: {saves}")
    elif saves[0][2]:
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
    print("복원 UI 계약 (렌더+클릭으로 측정)")
    print(f"  버튼 {[b['label'] for b in result['backupButtons']]} · 목록 {result.get('modal1')}"
          f"({result.get('restoreButtons')}행) · 1차 무토큰={not (result.get('restoreCall1') or [None,None,None])[2]}"
          f" · 확정 토큰 반환={(result.get('restoreCall2') or [None,None,None])[2] == TOKEN}")
    print(f"  안내: {result.get('notes')}")
    if bad:
        print("\nFAIL")
        for b in bad:
            print("  " + b)
        return 1

    # ── 음성 대조군: 알려진 위반 7종이 지금도 잡히는가 ─────────────────────────
    target = "ManageTab.tsx"
    source = (ROOT / "src" / target).read_text(encoding="utf-8")
    for label, pattern, replacement in BYPASSES:
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
            print(f"  음성 대조군 검출: {label} → {caught[0]}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
