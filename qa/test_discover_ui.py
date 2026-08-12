#!/usr/bin/env python3
"""팝업 D(게임 감지, 설계 §6)의 계약을 **렌더+클릭으로** 잠근다. 명세 정본 §15-A 이식표 + §17 P14.

⚠️ **P14에서 대상이 바뀌었다**: 전체화면 「게임 추가」 탭 → **팝업 D**(`src/DiscoverPopup.tsx`).
   프로브도 자체 하네스에서 공용 `qa/probe_kit.cjs`로 옮겼다. **기존 판정은 전량 살아 있고**
   (아래 ①~⑧), 설계가 새로 요구한 것(⑨~⑬)이 더해졌다.
   전체화면 탭은 **P15에서 삭제됐다** — 전환기 대상은 더 이상 없고, 검사는 팝업 D와
   선택기만 본다.

### 잠그는 것 — 13판정
    ① **타이핑 0회** — 소스에 입력 컴포넌트가 없고, **렌더 결과에도** 입력 요소가 없다.
       Game Mode에는 온스크린 키보드가 자동으로 안 뜬다 — 입력이 하나라도 생기면 이 화면은
       핸드헬드에서 못 쓴다.
    ② **`.sav`를 골라도 등록되지 않고 이유가 화면에 뜬다**(G14가 유일한 방어선) · 실패는
       목록을 다시 읽지 않는다(실패를 성공처럼 다루지 않는다).
    ③ **탐지 0건은 "게임 없음"이 아니다**(결정 8-a) · 「전부 이미 등록됨」과 **다른 문구** ·
       그 안내가 가리키는 **[파일 직접 고르기]가 실재·도달·동작**한다(QA R5·R5-b).
    ④ **등록된 게임 숨기기 기본 ON** + 토글이 실제로 상태를 바꾼다 + **확신 후보 일괄 등록**
       (라벨의 수 = 봉투 값 · 클릭 1회 · 대상 0이면 버튼 없음).
    ⑤ **확신 단일 매치 = 모달 없이 1탭**(선택기 0회·모달 0회·`best` 경로·토큰 없음) +
       **행별 [파일 직접 고르기] 상주**(S-01 — 후보가 전부 틀렸을 때의 게임별 탈출구).
    ⑥ **2단계 토큰 계약**(QA R1): 확인 전에는 저장되지 않고, 확정 시 **받은 토큰을 그대로**
       되돌린다. 취소는 아무 일도 없다. 백엔드가 안 묻는 경로(자동 후보 1탭)에는 확인창이 없다.
    ⑦ **선택기 취소가 조용하다**(등록 0·문구 0·모달 0·unhandled 0) + `filepicker.ts` 실물
       (취소를 null로 삼키고, `realpath`가 아니라 `path`를 넘긴다).
    ⑧ **등록 = 자체 재조회 + 변경 통지**(§4-F ③ 개정 — 성공·거부 무관. 무쓰기가 보장된
       응답은 `CONFIRM_REQUIRED` 하나뿐이다). 전체화면 시절의 「탭을 오가면 현황이 다시
       읽는가」가 팝업에서 갖는 형태다 — 낡은 숫자가 화면에 남는 사고의 재발 방지.
    ⑨ **§6-B 제외한 게임 뷰**: 진입·통일 문구·행(빈 날짜면 그 줄 없음)·[다시 포함]이
       **한 버튼 한 쓰기**(등록 RPC 0회)·note가 **다음 경로를 병기**·재조회로 목록이 줄고·
       빈 목록 문구·[← 뒤로]로 복귀.
    ⑩ **제외분은 후보 목록에 없다** + 제외 0건이어도 **진입 버튼은 남고 비활성**(M6 기각 —
       복구 렌즈의 유일한 화면 발견 경로라 숨기지 않는다).
    ⑪ **액션 줄 순서 = [다시 검색] 먼저**(GP#7) + **제외 진입은 목록 위**(GP#8 — 하단에 두면
       도달 비용이 목록 길이에 비례한다).
    ⑫ **GP#10 선택 즉시 등록 전환**: 1압 [선택]은 등록 0회 + 같은 자리가 [이 파일로 추가]로
       바뀌고, 2압이 **고른 경로로** 등록한다. 다른 후보를 고르면 전환이 옮겨간다.
       목록 끝의 별도 [추가] 버튼은 **없다**(선택 전후로 개수가 안 변한다).
    ⑬ **§9-③ 등록 note 분기**(남은 백업이 있으면 복원 경로를 그 자리에서 말한다) +
       **L3 숨김 병기**(숨긴 게 있으면 숨겼다고 말하고, 없으면 그 말도 사라진다) + 팝업 골격.

### 「존재」의 뜻 — 렌더 트리에 있음이 아니라 **화면에서 볼 수 있음**
2026-08-07 재게이트 R5: 상주 버튼에 `display:none`만 얹으면 개수·시작 경로·Focusable 조상이
전부 성립하는데 사용자는 아무것도 못 본다(Codex가 그렇게 뚫었다). 프로브가 **조상 체인까지
누적해** 가시성을 판정하고, 버튼·글자·도달성 집계가 **보이는 것만** 센다.
⚠️ 은닉 벡터는 원리적으로 열거가 안 된다 — **최종 근거는 실기 캡처다.**

★ 이 테스트도 **자기 자신을 반증한다** — 알려진 위반을 사본에 주입해 전부 검출되는지 보고,
  하나라도 안 잡히면 *"이 테스트는 그 위반에 대해 무효다"*라며 스스로 실패한다.
⚠️ 한계: node에서 컴포넌트를 직접 렌더한다(실제 Steam CEF·`@decky/ui`가 아니다).
  포커스·B버튼·실제 폭·파일 선택기의 실물 동작은 실기(§16)의 몫이다.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "discover_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

#: 타이핑 0회 — 이 이름들이 소스에 있으면 텍스트 입력이 생긴 것이다(M2-6).
#
# ★ 2026-08-07 QA R4: 예전 목록에는 **`<textarea`가 없었다.** Codex가
#   `<textarea aria-label="QA MUTATION…"/>`를 실제로 넣었는데 이 검사가 통과했다 —
#   금지 목록이 *"우리가 떠올린 컴포넌트"*였지 *"입력 요소"*가 아니었기 때문이다.
#   그래서 (1) 목록을 **입력 요소 등가물 전부**로 넓히고 (2) **렌더 결과로도** 잰다
#   (`discover_probe.cjs`의 `inputElements` — 이름을 바꿔 우회해도 그리면 걸린다).
TYPING_COMPONENTS = (
    # Decky/Steam 컴포넌트
    "TextField", "TextInput", "TextArea", "showModalInput", "SearchField",
    # DOM 입력 요소 등가물
    "<input", "<textarea", "<select", "<option",
    # 편집 가능 속성 — 태그가 div여도 키보드 입력이 생긴다
    "contentEditable", "contenteditable", "suppressContentEditableWarning",
    # 브라우저 기본 입력 프롬프트
    "window.prompt", "designMode",
)

#: 타이핑 0회를 지켜야 하는 파일 — **없으면 실패**다(감지 화면과 선택기가 사라졌다면
#: 검사가 대상을 잃은 것이다). P15까지 공존하던 전환기 파일 목록은 그 파일이 삭제되며 없앴다.
TYPING_REQUIRED = ("DiscoverPopup.tsx", "filepicker.ts")


def run_probe(n, src_dir=None):
    args = [str(U1), str(PROBE), str(n)]
    if src_dir is not None:
        args.append(str(src_dir))
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def check_no_typing():
    """텍스트 입력 요소 0건. **Game Mode에는 온스크린 키보드가 자동으로 안 뜬다** —
    입력 요소가 하나라도 생기면 그 화면은 핸드헬드에서 못 쓴다."""
    bad = []
    for name in TYPING_REQUIRED:
        if not (ROOT / "src" / name).is_file():
            bad.append(f"{name}이 없다 — 타이핑 0회 검사가 대상을 잃었다(판정 불가는 통과가 아니다)")
    for name in TYPING_REQUIRED:
        path = ROOT / "src" / name
        if not path.is_file():
            continue                      # 위 루프가 이미 "대상을 잃었다"로 실패시켰다
        src = path.read_text(encoding="utf-8")
        for needle in TYPING_COMPONENTS:
            if needle in src:
                bad.append(f"{name}에 텍스트 입력이 생겼다 — {needle} ★P6 기준 위반(타이핑 0회)")
    return bad


def check_picker_pitfalls():
    """선택기 호출의 **구조적 함정 2개**를 잠근다.

    ⚠️ 이것만은 정적 검사다 — `filter`/`extensions`를 넘겨도 **아무 일도 안 일어나는 것처럼
      보이기 때문**에 동작으로는 잴 수 없다(JSON 직렬화에서 조용히 `{}`/누락이 된다).
      "잴 수 없으니 안 잰다"가 아니라, 잴 수 없는 것만 여기서 본다.
    """
    src = (ROOT / "src" / "filepicker.ts").read_text()
    call = re.search(r"openFilePicker\(([^;]*?)\)\.then", src, re.S)
    bad = []
    if not call:
        return ["filepicker.ts에서 openFilePicker 호출을 찾지 못했다 — 검사가 대상에 닿지 못했다"]
    args = [a.strip() for a in call.group(1).split(",")]
    if len(args) > 4:
        bad.append(f"openFilePicker에 5번째 이후 인자를 넘겼다({len(args)}개) — "
                   "filter는 JSON 직렬화를 못 넘고 extensions는 무확장자 설정 파일을 숨긴다")
    if "@decky/api" not in src:
        bad.append("filepicker.ts가 @decky/api를 쓰지 않는다 — 검사가 대상에 닿지 못했다")
    others = [p for p in (ROOT / "src").glob("*.ts*") if p.name != "filepicker.ts"]
    leaked = [p.name for p in others if "openFilePicker" in p.read_text()]
    if leaked:
        bad.append(f"openFilePicker를 filepicker.ts 밖에서 부른다: {leaked} — 취소 처리가 흩어진다")
    return bad


def check(r, n):                                                   # noqa: C901  (판정 나열)
    p = []
    tag = f"N={n}: "

    # 측정 경로에 닿았는지부터 — 아무것도 안 그렸으면 아래 단언은 전부 공허하다
    if r["discoverCalls"] != 1:
        p.append(tag + f"마운트 시 탐지 RPC가 {r['discoverCalls']}회 나갔다(1회여야 한다)")
    if not r.get("hasModalRoot") or r.get("popupWhere") != "popup-d":
        p.append(tag + f"팝업 골격이 안 섰다 — ModalRoot={r.get('hasModalRoot')} "
                       f"경계={r.get('popupWhere')!r} (§4-A: 경계는 DialogBody 안쪽·popup-d)")
    if r.get("headerTitle") != "DISCOVER_TITLE":
        p.append(tag + f"팝업 제목이 감지 화면의 것이 아니다: {r.get('headerTitle')!r}")
    if r["interactiveSeen"] < 4:
        p.append(tag + f"상호작용 컴포넌트를 {r['interactiveSeen']}개만 봤다 — "
                       "검사가 재려던 대상에 닿지 못했다")
    if r["rowsDefault"] != n - r["registeredCount"]:
        p.append(tag + f"기본 목록이 {r['rowsDefault']}행이다(기대 {n - r['registeredCount']})")

    # ═══ ① 타이핑 0회 — **렌더 결과로도** 잰다 ════════════════════════════════
    for key in ("inputElements", "emptyInputElements"):
        if r.get(key):
            p.append(tag + f"입력 요소가 실제로 그려졌다({key}): {r[key]} ★타이핑 0회 위반 — "
                           "Game Mode에는 온스크린 키보드가 안 뜬다")

    # ═══ ③‴ 화면에 **없는** 상호작용 요소가 없다(재게이트 R5) ═════════════════
    for key, where in (("hiddenInteractive", "목록 상태"),
                       ("emptyHiddenInteractive", "탐지 0건 상태"),
                       ("allRegisteredHiddenInteractive", "전부 등록됨 상태")):
        if r.get(key):
            p.append(tag + f"{where}에 **화면에서 숨겨진** 상호작용 요소가 있다: {r[key]} "
                           "★사용자가 볼 수도 누를 수도 없다 — 렌더 트리에 있는 것은 존재가 아니다")
    if r["unreachable"]:
        p.append(tag + f"{r['unreachable']}가 Focusable 밖이라 D-패드로 도달할 수 없다 ★기준 위반")

    # ═══ ④ 필터 기본 ON + 일괄 등록 ═══════════════════════════════════════════
    if r["toggleCheckedDefault"] is not True:
        p.append(tag + "「등록된 게임 숨기기」가 기본으로 켜져 있지 않다 ★P6 기준 위반")
    if not r["defaultHidesRegistered"]:
        p.append(tag + "기본 상태에서 이미 등록된 게임이 목록에 보인다 ★P6 기준 위반")
    if not r["toggleWired"] or not r["toggleDrivesState"]:
        p.append(tag + "필터 토글 배선이 죽었다(onChange 또는 상태 반영 없음)")
    if r["rowsAfterToggle"] != n or not r["toggleRevealsRegistered"]:
        p.append(tag + f"토글을 껐는데 등록된 게임이 안 나온다({r['rowsAfterToggle']}행)")
    if not r["bulkPresent"]:
        p.append(tag + "확신 후보 일괄 등록 버튼이 없다 ★P6 기준 위반")
    elif r["bulkLabel"] != f"DISCOVER_ADD_CONFIDENT {r['bulkExpectedN']}":
        p.append(tag + f"일괄 버튼 라벨의 수가 틀렸다: {r['bulkLabel']} (기대 {r['bulkExpectedN']}) — "
                       "수는 봉투가 준 값이고 프론트가 다시 세지 않는다")
    if r["bulkClickCalls"] != 1:
        p.append(tag + f"일괄 버튼을 눌렀는데 RPC가 {r['bulkClickCalls']}회 나갔다(1회여야 한다)")
    if r["emptyBulkPresent"] or r["allRegisteredBulkPresent"]:
        p.append(tag + "등록할 것이 없는데 일괄 등록 버튼이 있다 — 라벨이 거짓말을 한다")

    # ═══ ⑤ 확신 1탭 + 행별 선택기 상주 (S-01 보존) ════════════════════════════
    if not r["confidentAddPresent"]:
        p.append(tag + "확신 게임에 인라인 [추가] 버튼이 없다 ★P6 기준 위반")
    if r["addGameCalls"] != 1 or not r["addGameUsedBestPath"]:
        p.append(tag + f"1탭 등록이 best 후보 경로로 1회 나가지 않았다(calls={r['addGameCalls']})")
    if r["addGameToken"] is not None:
        p.append(tag + f"1탭 등록의 첫 호출에 토큰이 실려 있다({r['addGameToken']!r}) "
                       "★프론트가 토큰을 지어냈다")
    if r["filePickerCallsOnConfident"] or r["modalCallsOnConfident"]:
        p.append(tag + f"확신 게임 등록에 선택기·모달이 떴다"
                       f"(picker={r['filePickerCallsOnConfident']} modal={r['modalCallsOnConfident']}) "
                       "★'모달 없이 1탭' 위반")
    #   ★ 개수만 세면 행 버튼과 상주 버튼이 구별되지 않는다 — **시작 경로**로 가른다.
    if r["pickButtonsWithRows"] != r["unregisteredRowsShown"] + 1:
        p.append(tag + f"「파일 직접 고르기」가 {r['pickButtonsWithRows']}개다"
                       f"(미등록 행 {r['unregisteredRowsShown']}개 + 상주 1개여야 한다) "
                       "★행별 탈출구(S-01) 또는 상주 진입점(QA R5-b)이 사라졌다")
    if r["tailPickStart"] != "/lib/steamapps/compatdata":
        p.append(tag + f"상주 버튼의 시작 위치가 라이브러리 기준이 아니다: {r['tailPickStart']!r}")
    if not (r.get("rowPickStart") or "").endswith("/pfx"):
        p.append(tag + f"행별 버튼이 그 게임의 prefix에서 시작하지 않는다: {r.get('rowPickStart')!r}")
    if r["tailPickAddDelta"] != 0:
        p.append(tag + "상주 버튼에서 선택기를 취소했는데 등록 RPC가 나갔다")
    if not r["manualPickReachable"]:
        p.append(tag + "상주 버튼이 Focusable 밖이다 — D-패드로 못 누른다")
    if not r["pickFileDescShown"]:
        p.append(tag + "상주 버튼이 무엇을 하는 것인지 말하지 않는다(H5 설명 줄 없음)")

    # ═══ ③ 0건·전부등록 안내 ══════════════════════════════════════════════════
    if not r["emptySaysNotFound"] or r["emptySaysNoGames"]:
        p.append(tag + "탐지 0건 안내가 틀렸다 ★결정 8-a — 「자동 탐지가 못 찾았을 뿐」이지 "
                       "「게임이 없다」가 아니다")
    if not r["allRegisteredSaysDifferent"]:
        p.append(tag + "전부 등록된 경우와 탐지 0건이 같은 문구다 — 두 상황은 다르다")
    if not r["emptyPickPresent"] or not r["emptyPickReachable"]:
        p.append(tag + "탐지 0건 안내가 「파일 직접 고르기」를 권하는데 그 버튼이 없거나 도달 불가다 "
                       "★QA R5 반려 사유")
    if not r["allRegisteredPickPresent"] or not r["allRegisteredPickReachable"]:
        p.append(tag + "「전부 이미 등록됨」 상태에 수동 등록 진입점이 없다 ★QA R5-b 반려 사유 — "
                       "탐지 밖 게임(네이티브 리눅스 등)을 등록할 유일한 길이 막힌다")
    if r["emptyPickOpensPicker"] != 1 or not (r["emptyPickStart"] or "").endswith("/steamapps/compatdata"):
        p.append(tag + f"0건 상태의 버튼이 라이브러리 기준 위치에서 선택기를 열지 않는다"
                       f"({r['emptyPickOpensPicker']}회, {r['emptyPickStart']!r})")
    if r["emptyPickRegisters"] != 1 or r["emptyPickAppid"] != "424242":
        p.append(tag + f"수동 등록이 경로에서 읽은 appid로 나가지 않았다"
                       f"(calls={r['emptyPickRegisters']} appid={r['emptyPickAppid']!r})")
    if r["outsideRegisters"] != 0 or not r["outsideSaysWhy"]:
        p.append(tag + "prefix 밖 파일을 골랐을 때 등록이 나가거나 이유가 화면에 안 뜬다 — "
                       "조용히 아무 일도 안 하면 안 된다")

    # ═══ ② `.sav` 거부 ═══════════════════════════════════════════════════════
    if not r["savRefusedShown"]:
        p.append(tag + ".sav를 골랐는데 거부 사유가 화면에 안 뜬다 ★P6 완료 기준 위반")
    if r["savAddedText"]:
        p.append(tag + ".sav가 거부됐는데 '추가했습니다'가 떴다 — 화면이 거짓말을 한다")
    # ★ P15-B §4-F ③ 개정: 등록은 **확정 실행**이라 거부돼도 다시 읽고 알린다(reload 2 = 마운트+1).
    #   거부 봉투는 "쓰지 않았다"를 보장하지 않는다 — 무쓰기 보장은 `CONFIRM_REQUIRED` 하나뿐이다.
    if r["savDiscoverReloads"] != 2 or r["savMutations"] != 1:
        p.append(tag + f"등록이 거부됐는데 목록을 다시 읽지 않았다"
                       f"(reload={r['savDiscoverReloads']} mutate={r['savMutations']}, 기대 2·1) — "
                       "확정 실행은 성공·실패를 가리지 않는다(§4-F ③)")
    if r["savAddedText"]:
        p.append(tag + "거부됐는데 성공 문구가 떴다")
    if r["savModals"]:
        p.append(tag + "거부된 등록에 확인 모달이 떴다")
    if not r["alreadyShown"] or r["alreadyModals"] or r["alreadyReloads"] != 2:
        p.append(tag + f"이미 등록된 appid 거부의 처리가 틀렸다(표시={r['alreadyShown']} "
                       f"모달={r['alreadyModals']} 재조회={r['alreadyReloads']}, 기대 2) — QA R2")

    # ═══ ⑦ 취소가 조용하다 + filepicker 실물 ══════════════════════════════════
    # ★ 전 RPC 델타 == 0 (picker 자체 +1만 예외 — 그것이 행위다). 열거 방식은 새 RPC가
    #   취소 갈래에 끼는 날 눈감는다(P15-E 재게이트 C2 — 열거 누락 3회 재발의 종결).
    delta = dict(r["cancelRpcDelta"])
    if delta.pop("picker", None) != 1:
        p.append(tag + f"취소 회차에 선택기 호출이 정확히 1이 아니다({r['cancelRpcDelta']})")
    if any(v != 0 for v in delta.values()):
        p.append(tag + f"선택기 취소 후 RPC 델타가 0이 아니다({r['cancelRpcDelta']})")
    if r["cancelAddCalls"] or r["cancelModals"] or r["cancelNoteTexts"]:
        p.append(tag + f"선택기를 취소했는데 무슨 일이 일어났다(add={r['cancelAddCalls']} "
                       f"modal={r['cancelModals']} note={r['cancelNoteTexts']})")
    if r["unhandledRejections"] != 0:
        p.append(tag + f"unhandled rejection {r['unhandledRejections']}건 — "
                       "취소가 reject로 오는데 잡지 않았다")
    if not r["pickerCancelResolvesNull"]:
        p.append(tag + "filepicker가 취소(reject)를 null로 삼키지 않는다")
    if not r["pickerReturnsPathNotRealpath"]:
        p.append(tag + "filepicker가 path가 아니라 realpath를 돌려준다 — "
                       "G11의 심볼릭 링크 거부가 무력화된다")

    # ═══ ⑥ 2단계 토큰 계약 ════════════════════════════════════════════════════
    if r["warnModals"] != 1:
        p.append(tag + f"CONFIRM_REQUIRED를 받았는데 확인창이 {r['warnModals']}회 떴다(1회여야 한다)")
    if r["warnAddCallsBefore"] != 1 or r["warnTokensBefore"] != [None]:
        p.append(tag + f"확인 전 호출이 이상하다(calls={r['warnAddCallsBefore']} "
                       f"tokens={r['warnTokensBefore']}) — 첫 호출은 토큰 없이 1회여야 한다")
    if r["warnShowsErrorNote"]:
        p.append(tag + "CONFIRM_REQUIRED를 오류 문구로 그렸다 ★flow code를 에러로 취급 — 봉투 계약 위반")
    if not r["warnCodeInModal"] or not r["warnModalHasOK"]:
        p.append(tag + f"확인창에 경고 코드나 확인 동작이 없다: {r['warnModalTexts']}")
    # ★ P15-E R6ⓑ: 등록 하나만 세던 판정을 **왕복 전량**으로 넓힌다. 취소의 계약은 "그 쓰기를
    #   안 한다"가 아니라 **"아무것도 안 한다"**이고, 좁게 재면 다른 쓰기(일괄 등록·재포함)나
    #   선택기 재개방으로 새는 갈래가 그대로 통과한다.
    if (r["warnCancelAddCalls"] != 1 or r["warnCancelReloads"] != 1 or r["warnCancelMutations"]
            or r["warnCancelBulkCalls"] or r["warnCancelIncludeCalls"]
            or r["warnCancelPickerCalls"] != 1):
        p.append(tag + f"취소했는데 무슨 일이 일어났다(add={r['warnCancelAddCalls']} "
                       f"reload={r['warnCancelReloads']} mutate={r['warnCancelMutations']} "
                       f"일괄={r['warnCancelBulkCalls']} 재포함={r['warnCancelIncludeCalls']} "
                       f"선택기={r['warnCancelPickerCalls']}, 기대 1·1·0·0·0·1) "
                       "★취소는 **아무 일도 없어야** 한다(QA R1 수용 기준)")
    if r["warnOkAddCalls"] != 2 or r["warnOkToken"] != "tok-synthetic":
        p.append(tag + f"확인해도 **받은 토큰 그대로** 재호출되지 않는다"
                       f"(calls={r['warnOkAddCalls']} token={r['warnOkToken']!r})")
    if r["warnOkReloads"] != 2 or r["warnOkMutations"] != 1 or not r["warnOkNote"]:
        p.append(tag + f"확인 뒤 등록됐는데 재조회·통지·안내가 빠졌다"
                       f"(reload={r['warnOkReloads']} mutate={r['warnOkMutations']} "
                       f"note={r['warnOkNote']})")

    # ═══ ⑧ 등록 성공 = 자체 재조회 + 변경 통지 (§4-F) ═════════════════════════
    if r["addReloads"] != 2 or r["addMutations"] != 1:
        p.append(tag + f"등록에 성공했는데 자체 재조회·변경 통지가 빠졌다"
                       f"(reload={r['addReloads']} mutate={r['addMutations']}) — "
                       "QAM Content는 팝업이 떠 있는 동안 언마운트일 수 있어 둘은 다른 일이다")
    if r["rescanCalls"] != 1:
        p.append(tag + f"[다시 검색]을 눌렀는데 조회가 {r['rescanCalls']}회다(1이어야 한다)")

    # ═══ ⑬ §9-③ note 분기 + L3 숨김 병기 ═════════════════════════════════════
    if r["addedNote"] != ["DISCOVER_ADDED Added"] or r["addedBackupNote"]:
        p.append(tag + f"백업 0건 등록에서 note가 틀렸다(plain={r['addedNote']} "
                       f"backups={r['addedBackupNote']}) — 0이면 복원 안내를 그리지 않는다")
    if not r["backupsNote"] or r["backupsPlainNote"]:
        p.append(tag + f"★§9-③ 남은 백업이 있는데 복원 경로를 말하지 않는다"
                       f"(backups={r['backupsNote']} plain={r['backupsPlainNote']}) — "
                       "등록을 해제해도 백업은 남는다. 재등록한 그 자리가 유일한 안내 지점이다")
    if r["backupsNote"] and " 3" not in r["backupsNote"][0]:
        p.append(tag + f"복원 안내가 백업 수를 말하지 않는다: {r['backupsNote']}")
    if r["hiddenNoteDefault"] != [f"DISCOVER_HIDDEN_NOTE {r['registeredCount']}"]:
        p.append(tag + f"★L3 숨김 병기가 틀렸다: {r['hiddenNoteDefault']} "
                       f"(기대 등록 {r['registeredCount']}개) — 숨긴 것을 말하지 않으면 "
                       "「감지가 안 되네」로 읽힌다")
    if r["hiddenNoteAfterToggle"]:
        p.append(tag + f"토글을 껐는데도 「숨겨져 있습니다」가 남아 있다: {r['hiddenNoteAfterToggle']}")
    if not r["summaryShown"]:
        p.append(tag + "요약 줄이 없다")

    # ═══ ⑪ 액션 줄 순서(GP#7) · 제외 진입 위치(GP#8) ═════════════════════════
    if not (0 <= r["rescanIndex"] < r["bulkIndex"]):
        p.append(tag + f"★GP#7 [다시 검색]이 먼저가 아니다(rescan={r['rescanIndex']} "
                       f"bulk={r['bulkIndex']}) — 진입 직후 A 관성의 착지가 무해한 쪽이어야 한다")
    if not (0 <= r["excludedIndex"] < r["firstCardIndex"]):
        p.append(tag + f"★GP#8 제외 진입이 목록 위 전용 행이 아니다(excluded={r['excludedIndex']} "
                       f"firstCard={r['firstCardIndex']}) — 하단에 두면 도달 비용이 목록 길이에 "
                       "비례해 「존재를 보인다」가 게임패드에서 성립하지 않는다")

    # ═══ ⑩ 제외분 비표시 + 0건 비활성 유지 ════════════════════════════════════
    if r["mainShowsExcludedName"]:
        p.append(tag + "제외한 게임이 후보 목록에 보인다 — 제외분은 목록에 없어야 한다")
    if r["excludedButtonLabel"] != "DISCOVER_EXCLUDED_OPEN 2" or r["excludedButtonDisabled"]:
        p.append(tag + f"제외 진입 버튼이 봉투의 수를 말하지 않거나 비활성이다"
                       f"({r['excludedButtonLabel']!r} disabled={r['excludedButtonDisabled']})")
    if not r["excludedZeroPresent"] or r["excludedZeroDisabled"] is not True:
        p.append(tag + f"★제외 0건에서 진입 버튼이 사라지거나 활성으로 남았다"
                       f"(present={r['excludedZeroPresent']} disabled={r['excludedZeroDisabled']}) — "
                       "M6 기각: 복구 렌즈의 유일한 화면 발견 경로라 숨기지 않고, 눌러도 갈 곳이 "
                       "없는 버튼은 활성이면 라벨이 거짓말을 한다")

    if r.get("mainShowsExcludedText"):
        p.append(tag + "★제외한 게임의 이름이 기본 뷰의 **화면 글자 어딘가**에 보인다 — 카드가 "
                       "아니어도 이 화면에 있으면 제외가 아니다(카드 이름만 보던 판정의 사각)")

    # ═══ R6ⓐ 수동 등록의 **시작 위치는 봉투가 준 경로뿐** ═════════════════════
    #
    # 상주 버튼은 조건 없이 항상 있으므로(GP#16) **조회 실패로 라이브러리를 모르는 상태**에서도
    # 눌린다. 예전에는 그때 `"/"`를 지어냈다 — 코드 바로 위 주석은 *"경로를 지어내지 않는다"*
    # 였다(이월 #6: 주석↔코드 자기모순). 지어내는 대신 그 자리에서 다시 읽는다.
    starts = r.get("blindPickStarts") or []
    if starts != ["/lib/steamapps/compatdata"]:
        p.append(tag + f"★시작 위치를 모르는 상태에서 선택기를 {starts}에서 열었다 — 봉투가 준 "
                       f"라이브러리 경로 말고는 시작점이 없다(파일 시스템 루트는 이 도메인의 "
                       f"시작점이 아니다)")
    if not r.get("blindPickRequery"):
        p.append(tag + "★시작 위치를 모르는데 **다시 읽지도 않았다** — 근거 없이 열거나 아무 일도 "
                       "안 하는 두 갈래뿐인 자리다")
    if r.get("blindPickAdds") != 1:
        p.append(tag + f"다시 읽어 연 선택기의 결과로 등록이 나가지 않았다(add={r.get('blindPickAdds')}) — "
                       f"수동 등록 경로가 중간에 끊겼다")
    if r.get("noLibraryPickers") or not r.get("noLibraryNote"):
        p.append(tag + f"라이브러리를 못 찾았는데 선택기를 열거나(=아무 데서나 시작) 그 사실을 "
                       f"말하지 않는다(picker={r.get('noLibraryPickers')} "
                       f"note={r.get('noLibraryNote')})")

    # ═══ ⑨ §6-B 제외한 게임 뷰 ═══════════════════════════════════════════════
    if not r["excludedViewOpened"] or r["excludedHasBack"] != 1:
        p.append(tag + f"제외 뷰가 안 열리거나 [← 뒤로]가 없다(opened={r['excludedViewOpened']} "
                       f"back={r['excludedHasBack']})")
    for key in ("DISCOVER_EXCLUDED_TITLE", "DISCOVER_EXCLUDED_HINT"):
        if key not in (r["excludedViewTexts"] or []):
            p.append(tag + f"제외 뷰에 {key}가 없다 — F12·M15 통일 문구가 이 화면의 요구다")
    if r["excludedRowNames"] != ["Excluded One", "Excluded Two"] or r["includeButtons"] != 2:
        p.append(tag + f"제외 행이 봉투대로 안 그려졌다(names={r['excludedRowNames']} "
                       f"buttons={r['includeButtons']})")
    if len(r["excludedRowMeta"] or []) != 1:
        p.append(tag + f"제외 날짜 줄이 {len(r['excludedRowMeta'] or [])}개다(라벨이 있는 1건만) — "
                       "빈 값이면 그 줄을 그리지 않는다")
    if r["excludedViewCards"]:
        p.append(tag + f"제외 뷰에 후보 카드가 {r['excludedViewCards']}개 보인다 — 뷰 전환이 아니라 "
                       "덧그리기다")
    if r["includeCalls"][:1] != ["900001"] or r["includeAddGameCalls"]:
        p.append(tag + f"★[다시 포함]이 한 버튼 한 쓰기가 아니다(include={r['includeCalls']} "
                       f"addGame={r['includeAddGameCalls']}) — 재포함은 **등록이 아니다**")
    if not r["includedNote"] or "Excluded One" not in r["includedNote"][0]:
        p.append(tag + f"★재포함 note가 없거나 대상을 말하지 않는다: {r['includedNote']} — "
                       "F11·F13: 다음 경로를 병기하지 않으면 「포함했는데 왜 그대로냐」가 된다")
    if r["includeReloads"] != 1 or r["includeMutations"] != 1:
        p.append(tag + f"재포함 뒤 재조회·통지가 빠졌다(reload={r['includeReloads']} "
                       f"mutate={r['includeMutations']})")
    if r["excludedRowsAfterInclude"] != 1:
        p.append(tag + f"재포함했는데 목록이 안 줄었다({r['excludedRowsAfterInclude']}행 남음)")
    if not r["excludedEmptyText"]:
        p.append(tag + "제외 목록이 비었는데 빈 목록 문구가 없다 — 화면이 아무 말도 안 한다")
    if not r["backToMain"]:
        p.append(tag + "[← 뒤로]로 기본 뷰에 못 돌아온다")

    # ═══ ⑫ GP#10 선택 즉시 등록 전환 ══════════════════════════════════════════
    if not r["ambiguousHasShowButton"]:
        p.append(tag + "애매한 게임에 후보 펼침 버튼이 없다")
    if len(r["candidateFiles"] or []) != 3 or len(r["candidatePaths"] or []) != 3:
        p.append(tag + f"후보를 펼쳤는데 파일명·경로가 안 나온다(files={r['candidateFiles']} "
                       f"paths={r['candidatePaths']}) — M4: 파일명과 경로를 갈라 보여 준다")
    if r["candidateTierTexts"] != 3:
        p.append(tag + f"후보의 tier 설명이 {r['candidateTierTexts']}개다(후보 3개 = 3) — "
                       "고를 근거를 화면에서 지웠다")
    if r["candLabelsInitial"] != ["DISCOVER_CHOOSE"] * 3:
        p.append(tag + f"펼친 직후 후보 버튼이 [선택]이 아니다: {r['candLabelsInitial']}")
    if r["addCallsAfterFirstPress"] != 0:
        p.append(tag + f"★1압에서 등록 RPC가 {r['addCallsAfterFirstPress']}회 나갔다 — "
                       "「두 번의 의도적 누름」 원칙 위반(포커스·1탭으로 등록되면 안 된다)")
    if r["candLabelsAfterFirst"] != ["DISCOVER_CANDIDATE_ADD", "DISCOVER_CHOOSE", "DISCOVER_CHOOSE"]:
        p.append(tag + f"★1압 뒤 **같은 자리**가 [이 파일로 추가]로 안 바뀐다: "
                       f"{r['candLabelsAfterFirst']} (GP#10)")
    if r["addButtonsBeforeChoose"] != 0 or r["addButtonsAfterChoose"] != 0:
        p.append(tag + f"★목록 끝에 별도 [추가] 버튼이 있다(before={r['addButtonsBeforeChoose']} "
                       f"after={r['addButtonsAfterChoose']}) — GP#10에서 제거된 이동 낭비다")
    if r["candLabelsAfterOther"] != ["DISCOVER_CHOOSE", "DISCOVER_CHOOSE", "DISCOVER_CANDIDATE_ADD"]:
        p.append(tag + f"다른 후보를 골랐는데 전환이 안 옮겨간다: {r['candLabelsAfterOther']}")
    if r["addCallsAfterOtherPress"] != 0:
        p.append(tag + "선택을 옮기는 것만으로 등록 RPC가 나갔다")
    if r["addCallsAfterSecondPress"] != 1:
        p.append(tag + f"2압에서 등록이 1회 나가지 않았다({r['addCallsAfterSecondPress']}회)")
    if r["addPathSecondPress"] != r["expectedCandPath"]:
        p.append(tag + f"★2압이 **고른 후보의 경로**로 등록하지 않았다\n"
                       f"      보낸 것: {r['addPathSecondPress']}\n"
                       f"      골랐던 것: {r['expectedCandPath']}")
    if r["secondPressToken"] is not None or r["secondPressModals"]:
        p.append(tag + f"2압 등록이 토큰을 지어냈거나 모달을 띄웠다"
                       f"(token={r['secondPressToken']!r} modal={r['secondPressModals']})")

    # ═══ 조회 실패 — 모르는 것을 없다고 말하지 않는다 ═════════════════════════
    fails = r.get("failTexts") or []
    if not any(x.startswith("REGISTRY_UNREADABLE") for x in fails):
        p.append(tag + f"조회 실패 사유를 화면이 말하지 않는다: {fails}")
    if any(x.startswith("DISCOVER_NONE") for x in fails):
        p.append(tag + f"★조회에 실패했는데 「탐지된 것이 없다」고 단언한다: {fails}")
    if any(x in ("DISCOVER_SCANNING", "LOADING") for x in fails):
        p.append(tag + f"★조회가 실패했는데 화면은 아직 「훑는 중」이라고 말한다: {fails} — "
                       "그 문장은 영영 안 바뀐다(한 상태에 한 문장)")
    return p


# ── 음성 대조군 ───────────────────────────────────────────────────────────────
#
# 주입 방식을 **하나로** 통일한다(치환/이동 두 갈래를 각각 다루면 목록이 늘 때마다 분기가 는다).
# 각 항목은 `(설명, 대상 파일, 변환 함수)`이고, 변환이 실패하면 검사가 **스스로 무효를 선언**한다.
def sub(pattern, replacement):
    def apply(text):
        out, n = re.subn(pattern, replacement, text, count=1)
        return out if n == 1 else None
    return apply


def move_after(block_pattern, anchor):
    """블록을 잘라 **뒤쪽 앵커 다음**으로 옮긴다 — 순서 요구(GP#7·GP#8)의 음성 대조군."""
    def apply(text):
        m = re.search(block_pattern, text, re.S)
        if not m:
            return None
        rest = text[:m.start()] + text[m.end():]
        at = rest.find(anchor, m.start())
        if at < 0:
            return None
        at += len(anchor)
        return rest[:at] + "\n" + m.group(0) + rest[at:]
    return apply


BYPASSES = [
    # 앵커는 액션 줄 **안쪽**의 끝이다 — `</Focusable>`을 앵커로 쓰면 버튼이 Focusable 밖으로
    # 나가 「도달 불가」로 잡히고, 그러면 순서 판정이 일했는지 알 수 없다(대조군이 다른 것을 잰다).
    ("GP#7 액션 줄 순서를 뒤집음([모두 추가]가 먼저)", "DiscoverPopup.tsx",
     move_after(r"<DialogButton disabled=\{busy\} onClick=\{\(\) => reload\(\)\}.*?</DialogButton>",
                ") : null}")),
    ("GP#8 제외 진입을 목록 아래로 옮김", "DiscoverPopup.tsx",
     move_after(r"<Focusable>\s*<DialogButton\s+disabled=\{busy \|\| excluded\.length === 0\}.*?</Focusable>",
                "</PopupScrollList>")),
    ("제외 0건인데 진입 버튼을 활성으로", "DiscoverPopup.tsx",
     sub(r"disabled=\{busy \|\| excluded\.length === 0\}", "disabled={busy}")),
    ("L3 숨김 병기를 지움", "DiscoverPopup.tsx",
     sub(r"\{hiddenN > 0 \? <div style=\{META_STYLE\}>\{t\(\"DISCOVER_HIDDEN_NOTE\", \{ n: hiddenN \}\)\}</div> : null\}",
         "{null}")),
    ("§9-③ 등록 note 분기를 없앰(항상 짧은 안내)", "DiscoverPopup.tsx",
     sub(r"setNote\(res\.data\.backups > 0\s*\n\s*\? t\(\"DISCOVER_ADDED_HAS_BACKUPS\"[^;]*?\);",
         'setNote(t("DISCOVER_ADDED", { name: res.data.name }));')),
    ("GP#10 1압에서 곧바로 등록(두 번의 의도적 누름 위반)", "DiscoverPopup.tsx",
     sub(r"if \(chosen === cand\.path\) onAdd\(entry, cand\.path\);\s*\n\s*else onChoose\(entry, cand\.path\);",
         "onAdd(entry, cand.path);")),
    ("GP#10 전환 없음(라벨이 [선택] 고정)", "DiscoverPopup.tsx",
     sub(r"\{t\(chosen === cand\.path \? \"DISCOVER_CANDIDATE_ADD\" : \"DISCOVER_CHOOSE\"\)\}",
         '{t("DISCOVER_CHOOSE")}')),
    ("재포함이 등록까지 함(한 버튼 한 쓰기 위반)", "DiscoverPopup.tsx",
     sub(r"setNote\(t\(\"DISCOVER_INCLUDED_NOTE\", \{ name: row\.name \}\)\);",
         'setNote(t("DISCOVER_INCLUDED_NOTE", { name: row.name }));\n'
         '            void register(row.appid, "/lib/steamapps/compatdata/1/pfx/a.ini", row.name);')),
    ("재포함 뒤 재조회 없음(목록이 낡는다)", "DiscoverPopup.tsx",
     sub(r"runMutation\(\(\) => includeGame\(row\.appid\), \"DISCOVER_INCLUDE_FAILED\", \(res\) => \{",
         "includeGame(row.appid).then((res) => {")),
    ("상주 [파일 직접 고르기]를 화면에서 숨김", "DiscoverPopup.tsx",
     sub(r"onClick=\{\(\) => \{ void pickManual\(\); \}\} style=\{PICK_BUTTON_STYLE\}",
         'onClick={() => { void pickManual(); }} style={{ ...PICK_BUTTON_STYLE, display: "none" }}')),
    ("행별 [파일 직접 고르기]를 없앰(S-01 보존 파괴)", "DiscoverPopup.tsx",
     sub(r"<DialogButton disabled=\{busy\} onClick=\{\(\) => onPick\(entry\)\} style=\{ROW_PICK_STYLE\}>\s*\n\s*\{t\(\"DISCOVER_PICK_FILE\"\)\}\s*\n\s*</DialogButton>",
         "")),
    ("확신 1탭이 선택기를 엶(모달 없이 1탭 위반)", "DiscoverPopup.tsx",
     sub(r"onClick=\{\(\) => onAdd\(entry, entry\.best \? entry\.best\.path : \"\"\)\}",
         "onClick={() => onPick(entry)}")),
    ("등록 1차 호출에 토큰을 지어냄", "DiscoverPopup.tsx",
     sub(r"addGame\(appid, path, name, token\), \"DISCOVER_ADD_FAILED\"",
         'addGame(appid, path, name, token ?? "MADE-UP-TOKEN"), "DISCOVER_ADD_FAILED"')),
    ("확정 시 받은 토큰이 아닌 값을 되돌림", "DiscoverPopup.tsx",
     sub(r"void register\(appid, path, name, p\.confirm_token\);",
         'void register(appid, path, name, "SOMETHING-ELSE");')),
    ("「등록된 게임 숨기기」 기본값을 끔", "DiscoverPopup.tsx",
     sub(r"const \[hideRegistered, setHideRegistered\] = useState\(true\);",
         "const [hideRegistered, setHideRegistered] = useState(false);")),
    ("등록이 공용 문을 안 지남(거부·성공 어느 쪽도 목록이 안 바뀐다)", "DiscoverPopup.tsx",
     sub(r"runMutation\(\(\) => addGame\(appid, path, name, token\), \"DISCOVER_ADD_FAILED\", \(res\) => \{",
         "addGame(appid, path, name, token).then((res) => {")),
    ("변경 통지를 훅에서 끊음(QAM이 낡은 값을 말한다)", "popup.tsx",
     sub(r"      reload\(\);\n      notify\.current\?\.\(\);", "      reload();")),
    # ── P15-E R6 ─────────────────────────────────────────────────────────────
    ("시작 위치를 모를 때 `/`를 지어냄(이월 #6 주석↔코드 자기모순 복원)", "DiscoverPopup.tsx",
     sub(r'      const known = data && data\.libraries\.length > 0 \? data\.libraries\[0\] : "";\n'
         r"      if \(known\) return openManual\(known\);",
         '      const known = data && data.libraries.length > 0 ? data.libraries[0] : "/";\n'
         "      return openManual(known);")),
    ("제외한 게임 이름을 기본 뷰에 흘림(카드 밖 자리)", "DiscoverPopup.tsx",
     sub(r"\{renderTail\(\)\}",
         '{renderTail()}\n        <div>{excluded.map((row) => row.name).join(" ")}</div>')),
    ("취소가 확인처럼 발화(단일 종료의 반대쪽 붕괴)", "popup.tsx",
     sub(r"      if \(ok\) \{", "      if (true) {")),
]


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")     # 판정 불가는 통과가 아니라 거부다
        return 1

    problems = check_no_typing() + check_picker_pitfalls()
    baseline = None
    for n in (12, 500):                               # 이 기기 규모 / 설계 상한(설치 500게임)
        r, err = run_probe(n)
        if r is None:
            print(f"FAIL — 프로브 실행 실패(N={n}): {err}")
            return 1
        if baseline is None:
            baseline = r
        problems += check(r, n)
        print(f"N={n:3d}: 전체 {n}행 / 등록됨 {r['registeredCount']}개 → 기본 {r['rowsDefault']}행 · "
              f"확신 일괄 {r['bulkExpectedN']}개 · 상호작용 {r['interactiveSeen']}개 · "
              f"unhandled {r['unhandledRejections']}건")
    print(f"  액션 줄 순서: 다시검색={baseline['rescanIndex']} 일괄={baseline['bulkIndex']} "
          f"제외={baseline['excludedIndex']} 첫카드={baseline['firstCardIndex']}")
    print(f"  GP#10: 초기={baseline['candLabelsInitial']} → 1압={baseline['candLabelsAfterFirst']} "
          f"→ 다른 후보={baseline['candLabelsAfterOther']} (등록 RPC {baseline['addCallsAfterSecondPress']}회)")
    print(f"  제외 뷰: 행={baseline['excludedRowNames']} include={baseline['includeCalls']} "
          f"재조회={baseline['includeReloads']} · §9-③ note={baseline['backupsNote']}")

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1

    # ── 음성 대조군: 알려진 위반이 지금도 잡히는가 ─────────────────────────────
    for label, target, transform in BYPASSES:
        source = (ROOT / "src" / target).read_text(encoding="utf-8")
        injected = transform(source)
        if injected is None or injected == source:
            # 주입이 안 됐는데 "통과"로 읽는 것이 이 프로젝트에서 세 번 난 사고다.
            print(f"FAIL — 음성 대조군 주입 실패({label}): 대상 식을 못 찾았다. 검사가 무효다.")
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            (case / target).write_text(injected, encoding="utf-8")
            control, err = run_probe(12, case)
            if control is None:
                print(f"FAIL — 음성 대조군 프로브 실행 실패({label}): {err}")
                return 1
            caught = check(control, 12)
            if not caught:
                print(f"FAIL — 위반을 주입했는데 통과했다: {label}")
                print("       **이 테스트는 그 위반에 대해 무효다.**")
                return 1
            # 몇 개의 판정이 걸렸는지도 적는다 — 의도한 판정 말고 **다른 판정만** 걸리는 경우가
            # 있고(파급 효과), 그때 어느 쪽이 일했는지는 이 수와 첫 줄로 가늠한다.
            print(f"  음성 대조군 검출({len(caught)}건): {label} → {caught[0].splitlines()[0][:104]}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
