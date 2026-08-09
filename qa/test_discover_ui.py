#!/usr/bin/env python3
"""P6 「게임 추가」 탭의 완료 기준을 **실행형으로** 잠근다.

잠그는 것(설계 단계표 P6 행 + 결정 8-a):
    ① **미등록 게임이 등록된다 · 타이핑 0회** — 텍스트 입력 요소가 하나도 없다
    ② **`.sav`를 골라도 등록되지 않고 이유가 화면에 뜬다**(G14가 유일한 방어선)
    ③ **자동 탐지 0건이어도 "게임 없음"이 아니라 "자동 탐지가 못 찾았을 뿐"** 안내가 뜬다
    ④ **registered 기본 필터 + confident 일괄 등록**으로 500게임 규모를 감당한다
    ⑤ **confident 단일 매치는 인라인 1탭**(모달 없음·선택기 없음)
    ⑥ **warnings 재확인 모달은 수동 파일 선택기 경로에서만** 뜬다
    ⑦ 선택기 취소가 조용하다 — `openFilePicker`는 취소를 `reject('User canceled')`로 알린다

★★ 2026-08-07 재게이트 R5: 「존재」의 뜻을 **렌더 트리에 있음**에서 **화면에서 볼 수 있음**으로
   옮겼다. 상주 버튼에 `display:none`만 얹으면 개수·시작 경로·Focusable 조상이 전부 성립하는데
   사용자는 아무것도 못 본다(Codex가 그렇게 뚫었다). 프로브가 자기+조상 style을 누적해
   가시성을 판정하고(`discover_probe.cjs`의 `hidesSelf`), 버튼·텍스트·도달성 집계가 **보이는
   것만** 센다. 은닉 벡터는 열거가 원리적으로 불가하므로(오프스크린·clip-path·CSS 클래스 등)
   **최종 근거는 실기 캡처다** — 이 검사는 회귀를 잠글 뿐 "보였다"를 증명하지 않는다.

⚠️ 한계: node에서 컴포넌트를 렌더한다. **실기 관찰을 대체하지 않는다** —
   파일 선택기 자체가 Game Mode에서 뜨는지·D-패드로 조작되는지는 빅픽처에서만 확인된다
   (`ModalRoot`+`WithSuspense` lazy 로딩이라 정적으로는 못 잰다).
"""
import json
import pathlib
import re
import subprocess
import sys

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


def run(n):
    proc = subprocess.run([str(U1), str(PROBE), str(n)], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def check_no_typing():
    """텍스트 입력 요소 0건. **Game Mode에는 온스크린 키보드가 자동으로 안 뜬다** —
    입력 요소가 하나라도 생기면 그 화면은 핸드헬드에서 못 쓴다."""
    bad = []
    for name in ("DiscoverTab.tsx", "filepicker.ts"):
        src = (ROOT / "src" / name).read_text()
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


def check(r, n):
    p = []
    tag = f"N={n}: "

    # 측정 경로에 닿았는지부터 — 아무것도 안 그렸으면 아래 단언은 전부 공허하다
    if r["discoverCalls"] != 1:
        p.append(tag + f"탐지 RPC가 {r['discoverCalls']}회 나갔다(1회여야 한다)")
    if r["rowsDefault"] != n - r["registeredCount"]:
        p.append(tag + f"기본 목록이 {r['rowsDefault']}행이다(기대 {n - r['registeredCount']})")
    if r["interactiveSeen"] < 4:
        p.append(tag + f"상호작용 컴포넌트를 {r['interactiveSeen']}개만 봤다 — "
                       "검사가 재려던 대상에 닿지 못했다(INTERACTIVE 집합이 낡았을 수 있다)")

    # ④ registered 기본 필터
    if r["toggleCheckedDefault"] is not True:
        p.append(tag + "「등록된 게임 숨기기」가 기본으로 켜져 있지 않다 ★P6 기준 위반")
    if not r["defaultHidesRegistered"]:
        p.append(tag + "기본 상태에서 이미 등록된 게임이 목록에 보인다 ★P6 기준 위반")
    if not r["toggleWired"]:
        p.append(tag + "필터 토글에 onChange가 안 걸렸다")
    if not r["toggleDrivesState"]:
        p.append(tag + "토글을 눌러도 상태가 안 바뀐다 — 배선이 죽었다")
    if r["rowsAfterToggle"] != n or not r["toggleRevealsRegistered"]:
        p.append(tag + f"토글을 껐는데 등록된 게임이 안 나온다({r['rowsAfterToggle']}행)")

    # ④ confident 일괄 등록
    if not r["bulkPresent"]:
        p.append(tag + "확신 후보 일괄 등록 버튼이 없다 ★P6 기준 위반")
    elif r["bulkLabel"] != f"DISCOVER_ADD_CONFIDENT {r['bulkExpectedN']}":
        p.append(tag + f"일괄 버튼 라벨의 수가 틀렸다: {r['bulkLabel']} (기대 {r['bulkExpectedN']})")
    if r["bulkClickCalls"] != 1:
        p.append(tag + f"일괄 버튼을 눌렀는데 RPC가 {r['bulkClickCalls']}회 나갔다(1회여야 한다)")

    # ⑤ confident 단일 매치 = 인라인 1탭
    if not r["confidentAddPresent"]:
        p.append(tag + "확신 게임에 인라인 [추가] 버튼이 없다 ★P6 기준 위반")
    if r["addGameCalls"] != 1 or not r["addGameUsedBestPath"]:
        p.append(tag + f"1탭 등록이 best 후보 경로로 1회 나가지 않았다(calls={r['addGameCalls']})")
    if r["filePickerCallsOnConfident"] != 0:
        p.append(tag + "확신 게임인데 파일 선택기가 떴다 ★'모달 없이 1탭' 위반")
    if r["modalCallsOnConfident"] != 0:
        p.append(tag + "확신 게임 등록에 모달이 떴다 ★'모달 없이 1탭' 위반")

    # 애매한 게임은 후보를 펼쳐 사람이 고른다
    if not r["ambiguousHasShowButton"]:
        p.append(tag + "애매한 게임에 후보 펼침 버튼이 없다")
    if r.get("candidatePathsShown", 0) < 1 or r.get("chooseButtons", 0) < 1:
        p.append(tag + "후보를 펼쳤는데 경로·선택 버튼이 안 나온다")

    # ⑦ D-패드 도달성
    if r["unreachable"]:
        p.append(tag + f"{r['unreachable']}가 Focusable 밖이라 D-패드로 도달할 수 없다 ★기준 위반")

    # ① 타이핑 0회 — **렌더 결과로도** 잰다(소스 금지 목록 우회 방지, 2026-08-07 QA R4)
    if r["inputElements"] or r["emptyInputElements"]:
        p.append(tag + f"입력 요소가 실제로 그려졌다: {r['inputElements'] + r['emptyInputElements']} "
                       "★P6 기준 위반(타이핑 0회) — Game Mode에는 온스크린 키보드가 안 뜬다")

    # ③ 0건 안내
    if not r["emptySaysNotFound"]:
        p.append(tag + "탐지 0건 안내가 DISCOVER_NONE_FOUND가 아니다 ★결정 8-a 위반")
    if r["emptySaysNoGames"]:
        p.append(tag + "탐지 0건인데 '등록된 게임이 없습니다'(NO_GAMES)라고 단언한다 ★결정 8-a 위반")
    if r["emptyBulkPresent"]:
        p.append(tag + "탐지 0건인데 일괄 등록 버튼이 있다 — 라벨이 거짓말을 한다")

    # ③″ 수동 등록 진입점은 **목록 상태와 무관하게 상주한다** (2026-08-07 실기, QA R5-b)
    #     ⚠️ 이 단언이 없으면 «0건 안내 ↔ 버튼» 정합만 보게 되고, 실기에서 난 결함
    #        (탐지 10 / 등록 10 → 진입점이 화면 어디에도 없음)은 **그 검사를 통과한다.**
    #        그 상태의 문구는 CTA를 권하지 않아 문구↔버튼이 정합이기 때문이다.
    #     ★ 개수만 세면 행 버튼과 구별이 안 된다 — **시작 경로**로 가른다:
    #        행 버튼 = `<lib>/steamapps/compatdata/<appid>/pfx` · 상주 버튼 = `<lib>/steamapps/compatdata`
    if r.get("pickButtonsWithRows") != r.get("unregisteredRowsShown", -1) + 1:
        p.append(tag + f"목록이 있는 상태의 「파일 직접 고르기」 버튼이 {r.get('pickButtonsWithRows')}개다"
                       f"(미등록 행 {r.get('unregisteredRowsShown')}개 + 상주 1개여야 한다) "
                       "★QA R5-b — 탐지가 성공한 기기에서 수동 등록 경로가 소멸한다")
    if r.get("tailPickStart") != "/lib/steamapps/compatdata":
        p.append(tag + f"목록 아래 상주 버튼의 시작 위치가 라이브러리 기준이 아니다: "
                       f"{r.get('tailPickStart')!r} — 행 버튼만 있고 상주 버튼이 없는 상태다")
    if r.get("tailPickAddDelta") != 0:
        p.append(tag + "상주 버튼에서 선택기를 취소했는데 등록 RPC가 나갔다")
    if not r.get("manualPickReachable"):
        p.append(tag + "목록 상태의 상주 버튼이 Focusable 밖이다 — D-패드로 못 누른다")
    if not r.get("allRegisteredPickPresent"):
        p.append(tag + "「전부 이미 등록됨」 상태에 수동 등록 진입점이 없다 ★QA R5-b 반려 사유 "
                       "— 탐지 밖 게임(네이티브 리눅스 등)을 등록할 유일한 길이 막힌다")
    if not r.get("allRegisteredPickReachable"):
        p.append(tag + "「전부 이미 등록됨」 상태의 상주 버튼이 Focusable 밖이다")

    # ③‴ **렌더 트리에는 있는데 화면에는 없는** 상호작용 요소가 없다 (2026-08-07 재게이트 R5)
    #     ⚠️ 위 단언들만으로는 `display:none` 하나로 전부 통과한다 — 개수도 맞고 프로브는
    #        숨은 버튼의 onClick도 부를 수 있기 때문이다. 「존재」의 뜻을 **트리에 있음**에서
    #        **볼 수 있음**으로 옮겼고(`discover_probe.cjs`의 `hidesSelf`), 여기서 그것을 잠근다.
    for key, where in (("hiddenInteractive", "목록 상태"),
                       ("emptyHiddenInteractive", "탐지 0건 상태"),
                       ("allRegisteredHiddenInteractive", "전부 등록됨 상태")):
        if r.get(key):
            p.append(tag + f"{where}에 **화면에서 숨겨진** 상호작용 요소가 있다: {r[key]} "
                           "★사용자가 볼 수도 누를 수도 없다 — 렌더 트리에 있는 것은 존재가 아니다")

    # ③′ 0건 안내가 **가리키는 조작이 실재한다** (2026-08-07 QA R5)
    #    존재하지 않는 조작을 권하는 문장은 오정보다 — 문구만 고치고 끝내지 않았다는 잠금이다.
    if not r["emptyPickPresent"]:
        p.append(tag + "탐지 0건 안내가 「파일 직접 고르기」를 권하는데 그 버튼이 없다 ★QA R5 반려 사유")
    if not r["emptyPickReachable"]:
        p.append(tag + "0건 상태의 수동 등록 버튼이 Focusable 밖이다 — D-패드로 못 누른다")
    if r.get("emptyPickOpensPicker") != 1:
        p.append(tag + f"0건 상태의 버튼을 눌러도 선택기가 안 뜬다({r.get('emptyPickOpensPicker')}회)")
    if not (r.get("emptyPickStart") or "").endswith("/steamapps/compatdata"):
        p.append(tag + f"수동 선택기의 시작 위치가 라이브러리 기준이 아니다: {r.get('emptyPickStart')!r} — "
                       "프론트가 경로를 지어내면 안 된다(백엔드 libraries가 정본)")
    if r.get("emptyPickRegisters") != 1 or r.get("emptyPickAppid") != "424242":
        p.append(tag + f"수동 등록이 경로에서 읽은 appid로 나가지 않았다"
                       f"(calls={r.get('emptyPickRegisters')} appid={r.get('emptyPickAppid')!r})")
    # compatdata 밖 파일은 **등록하지 않고 이유를 말한다** — 조용히 실패하지 않는다
    if r.get("emptyPickOutsideRegisters") != 0:
        p.append(tag + "prefix 밖 파일을 골랐는데 등록 RPC가 나갔다 — appid를 지어낸 것이다")
    if not r.get("emptyPickOutsideSaysWhy"):
        p.append(tag + "prefix 밖 파일을 골랐는데 이유가 화면에 안 뜬다 — 조용히 아무 일도 안 한다")
    if not r["allRegisteredSaysDifferent"]:
        p.append(tag + "전부 등록된 경우와 탐지 0건이 같은 문구다 — 두 상황은 다르다")
    if r["allRegisteredBulkPresent"]:
        p.append(tag + "등록할 것이 없는데 일괄 등록 버튼이 있다")

    # ② .sav 거부
    if not r["savRefusedShown"]:
        p.append(tag + ".sav를 골랐는데 거부 사유가 화면에 안 뜬다 ★P6 완료 기준 위반")
    if r["savAddedText"]:
        p.append(tag + ".sav가 거부됐는데 '추가했습니다'가 떴다 — 화면이 거짓말을 한다")
    if r["savDiscoverReloads"] != 1:
        p.append(tag + "등록이 거부됐는데 목록을 다시 불렀다 — 실패를 성공처럼 다룬다")
    if r["savModalCalls"] != 0:
        p.append(tag + "거부된 등록에 확인 모달이 떴다")

    # ⑦ 취소가 조용하다
    if r["cancelAddGameCalls"] != 0:
        p.append(tag + "선택기를 취소했는데 등록 RPC가 나갔다")
    if r["cancelNoteTexts"]:
        p.append(tag + f"선택기를 취소했는데 오류 문구가 떴다: {r['cancelNoteTexts']}")
    if r["cancelModalCalls"] != 0:
        p.append(tag + "선택기를 취소했는데 모달이 떴다")
    if r["unhandledRejections"] != 0:
        p.append(tag + f"unhandled rejection {r['unhandledRejections']}건 — "
                       "취소가 reject로 오는데 잡지 않았다")

    # ⑥ **등록 전** 재확인 모달 — 2단계 계약 (2026-08-07 QA R1)
    if r["manualWarnModalCalls"] != 1:
        p.append(tag + f"CONFIRM_REQUIRED를 받았는데 확인창이 {r['manualWarnModalCalls']}회 떴다(1회여야 한다)")
    if r["inlineWarnModalCalls"] != 0:
        p.append(tag + "백엔드가 묻지 않은 경로(자동 후보 1탭)에서 확인창이 떴다 — 확인창 지옥의 시작이다")
    if r["manualAddCallsBeforeConfirm"] != 1 or r["manualTokenBeforeConfirm"] != [None]:
        p.append(tag + f"확인 전 호출이 이상하다(calls={r['manualAddCallsBeforeConfirm']} "
                       f"tokens={r['manualTokenBeforeConfirm']}) — 첫 호출은 토큰 없이 1회여야 한다")
    if r["manualShowsErrorNote"]:
        p.append(tag + "CONFIRM_REQUIRED를 오류 문구로 그렸다 ★flow code를 에러로 취급 — 봉투 계약 위반")
    if not r["manualWarnShownInModal"]:
        p.append(tag + "확인창에 경고 코드가 안 실렸다 — 무엇을 확인하라는지 알 수 없다")
    if not r["confirmModalHasOK"]:
        p.append(tag + "확인창에 onOK가 없다 — 확인해도 등록되지 않는다")
    if r["confirmModalHasCancelSideEffect"]:
        p.append(tag + "확인창의 취소에 동작이 걸려 있다 ★취소는 **아무 일도 없어야** 한다(QA R1 수용 기준)")
    if r["confirmCancelAddCalls"] != 1:
        p.append(tag + f"취소 뒤에도 등록 RPC가 나갔다({r['confirmCancelAddCalls']}회, 1이어야 한다)")
    if r["confirmOkAddCalls"] != 2 or r["confirmOkSentToken"] != "tok-synthetic":
        p.append(tag + f"확인해도 **받은 토큰 그대로** 재호출되지 않는다"
                       f"(calls={r['confirmOkAddCalls']} token={r['confirmOkSentToken']!r})")
    if r["confirmOkReloads"] != 2:
        p.append(tag + f"확인 뒤 등록됐는데 목록을 다시 안 읽는다({r['confirmOkReloads']}회)")

    # ⑥′ 기등록 appid 거부가 화면에 뜬다 (2026-08-07 QA R2)
    if not r["alreadyRegisteredShown"]:
        p.append(tag + "ALREADY_REGISTERED로 거부됐는데 사유가 화면에 안 뜬다")
    if r["alreadyRegisteredModalCalls"] != 0:
        p.append(tag + "거부된 등록에 확인창이 떴다 — 확인해도 등록되지 않는데 묻는 것은 오정보다")
    if r["alreadyRegisteredReloads"] != 1:
        p.append(tag + "등록이 거부됐는데 목록을 다시 불렀다 — 실패를 성공처럼 다룬다")

    # ⑧' 탭 왕복 — 「게임 추가」에서 등록하고 돌아오면 「현황」이 다시 읽어야 한다
    if r["tabButtons"] != ["TAB_STATUS", "TAB_DISCOVER"]:
        p.append(tag + f"탭 버튼이 둘이 아니다: {r['tabButtons']} — 검사가 대상에 닿지 못했다")
    if not r["discoverTabRendered"]:
        p.append(tag + "「게임 추가」 탭을 눌러도 그 화면이 안 뜬다")
    if r["overviewCallsOnMount"] != 1:
        p.append(tag + f"마운트에서 현황을 {r['overviewCallsOnMount']}회 읽었다(1회여야 한다)")
    if r["overviewCallsOnDiscover"] != r["overviewCallsOnMount"]:
        p.append(tag + "「게임 추가」 탭으로 갔는데 현황을 또 읽었다 — 쓸데없는 왕복이다")
    if not r["statusTabReloads"]:
        p.append(tag + "「현황」으로 돌아왔는데 다시 읽지 않는다 — "
                       "게임을 등록하고 넘어오면 **낡은 숫자**가 뜬다(2026-08-07 실기에서 실제로 그랬다)")
    if r["tabReachability"]:
        p.append(tag + f"탭 왕복 뒤 {r['tabReachability']}가 Focusable 밖이다")

    # ⑨ filepicker 실물
    if not r["pickerCancelResolvesNull"]:
        p.append(tag + "filepicker가 취소(reject)를 null로 삼키지 않는다")
    if not r["pickerReturnsPathNotRealpath"]:
        p.append(tag + "filepicker가 path가 아니라 realpath를 돌려준다 — G11의 심볼릭 링크 거부가 무력화된다")
    return p


def main():
    if not U1.is_file():
        print(f"FAIL — 툴체인 node가 없다: {U1}")     # 판정 불가는 통과가 아니라 거부다
        return 1

    problems = check_no_typing() + check_picker_pitfalls()
    for n in (12, 500):                               # 이 기기 규모 / 설계 상한(설치 500게임)
        r, err = run(n)
        if r is None:
            print(f"FAIL — 프로브 실행 실패(N={n}): {err}")
            return 1
        problems += check(r, n)
        print(f"N={n:3d}: 전체 {n}행 / 등록됨 {r['registeredCount']}개 → 기본 {r['rowsDefault']}행 · "
              f"확신 일괄 {r['bulkExpectedN']}개 · 상호작용 {r['interactiveSeen']}개 · "
              f"unhandled {r['unhandledRejections']}건")

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
