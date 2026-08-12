#!/usr/bin/env python3
"""팝업 공통 기반(설계 §4)의 계약 — **렌더해서** 잰다. 명세 정본 §15-B ③.

이 파일이 잠그는 6가지:
  ① **골격**: ModalRoot > DialogHeader + DialogBody, **ErrorBoundary는 DialogBody 안쪽**(R-4),
     `closeModal`이 ModalRoot까지 살아서 도달, 크기 무지정(A10)
  ② **뷰 전환·뒤로가기·목록 비리마운트**(GP#3): `key`는 상세·백업·제외 뷰에만 —
     목록에 주면 복귀할 때마다 스크롤·마지막 조작 행이 통째로 버려진다
  ③ **두 렌더러가 같은 spec을 같은 요소로**(중첩/폴백): 문구 집합 동일 + **입력형 2종**의
     TextField 상태 → `okDisabled` **동적 재평가** → `onOK(value)` 전달(R-1 회귀 잠금)
     + **단일 종료**(두 번 눌러도 한 번만 — D-05 ②)
  ③′ **spec화 전후 동일성**: 현행 확인창 7종을 **파라미터 조합별로 신구 각각 렌더**해 대조
     (문구·입력 초기값·OK 비활성). 손실만 실패, 추가는 허용 — P15에서 legacy가 삭제되면 은퇴한다
  ③″ **모달 생명주기**(D-05 ②③): 닫기가 정확히 1회(실물 ConfirmModal이 자기 경로에서도
     `closeModal`을 부른다) · 발화 뒤 취소 잠금 · **`onOK`가 던져도 창은 닫힌다**
  ④ **게이트 실패**: `showModal`이 죽으면 **호출부가 준 failKey 문구**가 뜨고 `onOK`는 안 나간다
     (안전한 것과 진단 가능한 것은 다른 요건이다)
  ⑤ **데이터 로드·자체 재조회**: 마운트 1회 조회 · `profile_names` 선반영(R-6) · `reload()` 재조회
     · 실패 봉투는 `tCode(failKey)` 경유
  ⑥ **입력값 보존**(GP#9): 언마운트 시 스냅샷이 나가고, 그 값을 `initial`로 되돌리면 복원된다

그리고 **폴백 격리**(D-05 ⑤): 오버레이가 떠 있는 동안 원 콘텐츠는 **렌더되지 않는다**
(숨김·포커스 차단이 아니라 미렌더 — 갈 수 있는 경로 자체를 없앤다).

⚠️ 범위 밖(정직하게): `onMutate()` **발화**는 팝업 화면(P13·P14)이 변이 성공 뒤에 부르는
   계약이라 그 단계 프로브의 몫이다. 여기서는 화면이 그 통지를 만들 재료 —
   **자기 재조회(`reload`)가 실제로 RPC를 다시 부른다** — 까지만 잠근다.
⚠️ 실효가 실기 몫인 것도 명시: `preferredFocus`·`MAINTAIN_X`·`onCancelButton`은 **타입에
   실재하고 폴백이 무해**하다는 것까지가 여기서 잴 수 있는 전부다(§16-③④가 런타임 판정).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "popup_shell_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)


def main():                                                    # noqa: C901  (판정 나열)
    if not U1.is_file():
        # ★ 판정할 수 없을 때는 통과가 아니라 **거부**다 (QA R7). SKIP 후 exit 0으로 두면
        #   툴체인이 옮겨진 순간 이 계약을 한 줄도 안 재고 초록이 된다.
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    proc = subprocess.run([str(U1), str(PROBE)], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print("FAIL — 프로브가 죽었다")
        print("  " + (proc.stderr or proc.stdout).strip().splitlines()[-1])
        return 1
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    problems = []

    def P(msg):
        problems.append(msg)

    sk, vw, gate = r["skeleton"], r["views"], r["gate"]
    nested, fallback = r["nestedGate"], r["fallbackGate"]

    # ═══ ① 골격 ══════════════════════════════════════════════════════════════
    if not sk["rootIsModalRoot"]:
        P("① 최상위가 ModalRoot가 아니다 — showModal이 closeModal을 주입할 자리가 없다")
    if not (sk["hasHeader"] and sk["hasBody"]):
        P(f"① DialogHeader/DialogBody 구획이 없다 — header={sk['hasHeader']} body={sk['hasBody']}")
    if not sk["boundaryFound"]:
        P("① ErrorBoundary가 없다 — 렌더 실패가 팝업 밖으로 번진다")
    if not sk["boundaryInsideBody"]:
        P("★① ErrorBoundary가 DialogBody **안쪽**이 아니다 — 최상위를 감싸면 showModal의 "
          "closeModal 주입이 경계에서 삼켜져 **닫기 배선이 죽는다**(R-4)")
    if sk["boundaryWrapsRoot"]:
        P("★① ErrorBoundary가 ModalRoot 바깥에 있다 — 같은 사고(R-4)의 다른 형태다")
    if not sk["closeModalReachedRoot"]:
        P("★① closeModal이 ModalRoot까지 도달하지 않는다 — 팝업을 닫을 방법이 사라진다")
    if sk["sizeProps"]:
        P(f"① 팝업이 크기를 지정한다({sk['sizeProps']}) — A10은 크기 무지정이다")
    if not sk["childRendered"]:
        P("① 본문이 렌더되지 않았다 — 골격이 자식을 삼킨다")
    style = sk["scrollListMaxHeight"] or {}
    if style.get("maxHeight") != "420px" or style.get("paddingBottom") != "48px":
        P(f"① 목록 컨테이너가 limits 상수를 쓰지 않는다 — {style} "
          f"(실기 조정 지점이 한 곳이라는 것이 그 상수의 값어치다)")
    if style.get("overflowY") != "auto":
        P(f"① 목록 컨테이너에 내부 스크롤이 없다 — {style}")
    if not sk["navPrefersMaintainX"]:
        P("① 행 이동 성향이 라이브러리 상수(MAINTAIN_X)가 아니다 — 하드코딩 값 금지(§13)")

    # ═══ ② 뷰 전환·뒤로가기·목록 비리마운트 ═══════════════════════════════════
    if vw["listKey"] is not None or vw["mainKey"] is not None:
        P(f"★② 목록 뷰에 key가 붙는다(list={vw['listKey']} main={vw['mainKey']}) — "
          f"복귀할 때마다 목록이 통째로 리마운트되어 스크롤·마지막 조작 행이 버려진다(GP#3)")
    for name, key in (("detail", vw["detailKey"]), ("backups", vw["backupsKey"]),
                      ("excluded", vw["excludedKey"])):
        if key != name:
            P(f"② {name} 뷰의 key가 없다({key}) — 뷰 전환 시 스크롤이 초기화되지 않는다")
    if not vw["firstChildIsBack"]:
        P("★② [← 뒤로]가 비목록 뷰의 첫 요소가 아니다 — B가 안 먹는 갈래에서 탈출구가 "
          "스크롤 밖으로 밀린다")
    if vw["backCalls"] != 1:
        P(f"② 뒤로가기 클릭이 {vw['backCalls']}회 전달됐다(1이어야 한다)")
    if not vw["backHasPreferredFocus"]:
        P("② [← 뒤로]에 preferredFocus가 없다 — 비목록 뷰의 착지 대상이 지정되지 않았다(§4-E ①). "
          "런타임 실효는 실기 몫이지만 **지정 자체가 빠지면** 실기에서 잴 것도 없다")
    if not vw["hasOnCancelButton"]:
        P("② 비목록 뷰에 onCancelButton이 없다 — B=한 단계 뒤로(1안)의 배선이 빠졌다")
    if vw["cancelDescription"] != "BACK":
        P(f"② 하단 바 힌트가 t('BACK')이 아니다({vw['cancelDescription']}) — 표시와 실동작이 갈린다")
    if not vw["bodyRendered"]:
        P("② 비목록 뷰가 본문을 렌더하지 않았다")

    # ═══ ③ 두 렌더러, 한 spec ═════════════════════════════════════════════════
    if not gate["anchorFound"]:
        P("★③ NESTED_CONFIRM 앵커를 못 찾았다 — 폴백 모드를 **한 번도 안 재고** 통과할 뻔했다")
    # ⚠️ 순서는 다를 수 있다(중첩은 title/ok/cancel이 prop, 폴백은 자식) — **집합**으로 본다.
    for label, a, b in (
        ("plain(저장)", gate["plainNestedTexts"], gate["plainFallbackTexts"]),
        ("input(초기화)", gate["resetNestedTexts"], gate["resetFallbackTexts"]),
        ("input(이름 편집)", gate["nameNestedTexts"], gate["nameFallbackTexts"]),
    ):
        if sorted(a) != sorted(b):
            P(f"★③ {label}: 두 렌더러의 문구가 다르다 — 폴백으로 넘어가는 순간 사용자가 보는 "
              f"내용이 바뀐다\n      중첩={sorted(a)}\n      폴백={sorted(b)}")
        if not a:
            P(f"③ {label}: 중첩 렌더러가 아무 글자도 안 그렸다 — 검사가 대상에 닿지 못했다")
    # 입력형: 초기값 → 타이핑 → okDisabled 동적 재평가 (R-1의 회귀 잠금)
    rb, ra = gate["resetBefore"], gate["resetAfter"]
    if not (rb["nestedOkDisabled"] and rb["fallbackOkDisabled"]):
        P(f"★③ 초기화 확인창의 OK가 처음부터 활성이다 — okDisabled가 평가되지 않는다 ({rb})")
    if ra["nestedOkDisabled"] or ra["fallbackOkDisabled"]:
        P(f"★③ challenge를 정확히 입력했는데 OK가 계속 비활성이다 — 입력이 반영되지 않는다 ({ra})")
    if ra["nestedValue"] != "delete" or ra["fallbackValue"] != "delete":
        P(f"③ TextField가 입력값을 반영하지 않는다 — {ra}")
    nb, na = gate["nameBefore"], gate["nameAfter"]
    if nb["nestedOkDisabled"] or na["nestedOkDisabled"]:
        P(f"★③ 이름 편집의 OK가 비활성이다 — 빈 값은 오류가 아니라 '기본 이름으로 되돌리기'다 "
          f"({nb} → {na})")
    # onOK는 값을 싣고, **두 번 눌러도 한 번만** 나간다(D-05 ②)
    if gate["resetValues"] != ["delete"]:
        P(f"★③ 초기화 onOK가 {gate['resetValues']}로 발화했다 — 값이 안 실렸거나 "
          f"이중 탭이 두 번 발화했다(토큰을 두 번 쓰는 경로)")
    if gate["nameValues"] != ["새 이름"]:
        P(f"★③ 이름 편집 onOK가 {gate['nameValues']}로 발화했다 — 같은 사고")
    if gate["plainFired"] != 1:
        P(f"③ plain onOK가 {gate['plainFired']}회 발화했다(1이어야 한다) — 취소가 onOK를 "
          f"불렀거나 이중 발화다")
    if gate["inputMinWidth"] != "400px":
        P(f"③ 입력형에 minWidth 400px가 없다({gate['inputMinWidth']}) — lsfg 선례(§4-D)")
    if gate["plainMinWidth"]:
        P(f"③ 비입력형에 minWidth가 붙었다({gate['plainMinWidth']}) — 입력 모달 전용이다")
    if not gate["closeModalForwarded"]:
        P("★③ 중첩 렌더러가 closeModal을 그대로 전달하지 않는다(D-05 ①)")

    # ═══ ③′ spec화 **전후 동일성** — 파라미터 조합별 신구 렌더 대조 (§17 완료 기준) ═══
    #
    #   현행 확인창 컴포넌트와 spec을 **같은 파라미터로 각각 렌더**해서 화면 글자·입력 초기값·
    #   OK 비활성을 대조한다. 옮기다 한 줄이 빠지거나 분기가 뒤집히면 *사용자에게 덜 말하거나
    #   다른 것을 말하는 확인창*이 되는데, 새 것끼리만 보면 그 손실이 안 보인다.
    #
    #   ⚠️ **손실만 실패**다(추가는 허용): P13이 §9·§7·§5-C의 신설 문구를 spec에 얹을 예정이라
    #     추가까지 막으면 그 단계에서 이 검사가 통째로 거짓말을 한다.
    #   ⚠️ 입력 초기값·OK 비활성은 **양방향 일치**를 요구한다 — 그 둘은 "더 말하기"가 성립하지
    #     않는 값이고, 프리필 규칙(C2)·challenge 판정이 여기서 갈리면 조용한 오작동이다.
    #   ⚠️ **처분 예고**: P15에서 legacy 확인창이 삭제되면 이 대조는 **은퇴한다**(비교 대상이
    #     사라진다) — 스냅샷 고정으로 전환하거나 삭제한다. P15의 결정 사항으로 넘긴다.
    parity_lost = {}
    # 조합을 추가하면 이 상수를 의식적으로 갱신하라 — 하한 방식은 검사 범위가 조용히
    # 줄어드는 경로였다(P13 게이트 C3). `<20`이던 시절엔 조합을 하나 지워도 통과했다.
    if len(r["parity"]) != 26:
        P(f"③′ 대조 조합이 {len(r['parity'])}개다(고정 26) — 분기를 흔들지 않으면 이 검사는 "
          f"**한 갈래만 보고** 통과한다. 늘렸다면 이 상수를 함께 갱신하라")
    for case in r["parity"]:
        label, legacy, spec_face = case["label"], case["legacy"], case["spec"]
        if case.get("legacyCaptured") is False or legacy is None:
            P(f"★③′ {label}: 현행 확인창을 못 꺼냈다 — 대조가 항진식이다"
              f"(버튼 라벨={case.get('addButtonLabel')})")
            continue
        lost = [x for x in legacy["texts"] if x not in spec_face["texts"]]
        if lost:
            parity_lost[label] = lost
            P(f"★③′ {label}: spec화하며 문구가 사라졌거나 달라졌다 — {lost}\n"
              f"      spec={spec_face['texts']}")
        if legacy["field"] != spec_face["field"]:
            P(f"★③′ {label}: 입력 초기값이 다르다 — 현행 {legacy['field']!r} / spec "
              f"{spec_face['field']!r} (프리필 규칙이 갈렸다)")
        if legacy["okDisabled"] != spec_face["okDisabled"]:
            P(f"★③′ {label}: OK 비활성 판정이 다르다 — 현행 {legacy['okDisabled']} / spec "
              f"{spec_face['okDisabled']}")

    # ═══ ③″ 모달 생명주기 방어 (D-05 ②③) ═════════════════════════════════════
    life = r["lifecycle"]
    if life["nestedCloses"] != 1:
        P(f"★③″ 중첩 확인창의 닫기가 {life['nestedCloses']}회 발화했다 — 실물 ConfirmModal은 "
          f"자기 경로에서도 closeModal을 부르므로, 1회 래퍼가 없으면 **남의 창을 닫는다**")
    if life["okFiredOnce"] != 1:
        P(f"★③″ onOK가 {life['okFiredOnce']}회 발화했다(1이어야 한다)")
    if life["cancelDisabledBefore"] or not life["cancelDisabledAfter"]:
        P(f"③″ 발화 뒤 취소가 잠기지 않는다(before={life['cancelDisabledBefore']} "
          f"after={life['cancelDisabledAfter']}) — OK와 취소의 상호 배타가 화면에 안 보인다")
    if life["fallbackCloses"] != 1:
        P(f"★③″ 폴백 오버레이가 OK 뒤에 {life['fallbackCloses']}회 닫혔다(1이어야 한다)")
    if life["throwClosedNested"] != 1 or life["throwClosedFallback"] != 1:
        P(f"★③″ `onOK`가 던졌을 때 창이 안 닫힌다(중첩 {life['throwClosedNested']} / 폴백 "
          f"{life['throwClosedFallback']}) — 빗장은 걸렸는데 창은 남아 **아무 버튼도 안 듣는** "
          f"상태가 된다(D-05 ③)")
    if not life["throwPropagated"]:
        P("③″ `onOK`의 예외를 삼켰다 — 창은 닫되 원인은 위로 올라가야 한다(진단 가능성)")

    # ═══ ④ 게이트 두 모드 + 실패 ══════════════════════════════════════════════
    if nested["modalsShown"] != 1 or not nested["modalIsSpecConfirm"] or not nested["modalSpecIsSame"]:
        P(f"★④ 중첩 모드가 spec을 그대로 들고 모달을 1회 띄우지 않았다 — {nested}")
    if nested["overlayShown"]:
        P("④ 중첩 모드인데 오버레이까지 떴다 — 확인창이 둘이다")
    if "ORIGINAL_CONTENT" not in nested["bodyTexts"]:
        P("④ 중첩 모드에서 원 콘텐츠가 사라졌다 — 팝업 본문은 그대로 있어야 한다")
    if fallback["modalsShown"] != 0 or not fallback["overlayShown"]:
        P(f"★④ 폴백 모드가 오버레이로 그리지 않는다 — {fallback}")
    if fallback["originalContentRendered"]:
        P("★④ 폴백 오버레이가 떠 있는데 원 콘텐츠가 **함께 렌더**된다 — 포커스가 뒤 콘텐츠로 "
          "갈 수 있다. 격리는 숨김이 아니라 **미렌더**여야 한다(D-05 ⑤)")
    if not fallback["restoredAfterClose"]:
        P("★④ 오버레이를 닫았는데 원 콘텐츠가 안 돌아온다 — 팝업이 빈 화면이 된다")
    if not fallback["overlayHasCancelButton"]:
        P("④ 폴백 오버레이에 B(취소) 배선이 없다 — 나갈 길이 버튼 하나뿐이다")
    fail = r["failure"]
    if fail["notes"] != ["MODAL_FAILED"]:
        P(f"★④ 확인창을 못 띄웠는데 화면 안내가 호출부 문구가 아니다({fail['notes']}) — "
          f"공유 문장은 어느 경로에선 반드시 거짓이 된다(2026-08-10 QA R1)")
    if fail["okFired"]:
        P("★④ 확인창을 못 띄웠는데 onOK가 발화했다 ★fail-closed가 깨졌다")
    if fail["overlayShown"]:
        P("④ 중첩 실패 시 오버레이로 조용히 넘어갔다 — 모드 전환은 스위치 한 줄의 일이지 "
          "런타임 폴백이 아니다(두 경로가 섞이면 실기 판정이 불가능해진다)")

    # ═══ ⑤ 데이터 로드·자체 재조회 ════════════════════════════════════════════
    data = r["data"]
    if data["mountCalls"] != 1:
        P(f"⑤ 마운트 시 조회가 {data['mountCalls']}회다(1이어야 한다)")
    if not data["dataArrived"]:
        P("⑤ 봉투가 도착했는데 상태에 반영되지 않았다")
    if data["profileNamesTaken"] != 1 or not data["profileNamesValue"]:
        P(f"★⑤ profile_names가 i18n에 실리지 않았다({data['profileNamesTaken']}회) — "
          f"소비자 한 곳이 빠져 '초기화 뒤에도 옛 표시명이 남는' 사고가 났던 자리다(R-6)")
    if data["afterReloadCalls"] != 2:
        P(f"★⑤ reload()가 재조회하지 않았다({data['afterReloadCalls']}회) — 변이 뒤 열려 있는 "
          f"팝업 화면이 낡은 채로 남는다(§4-F)")
    if data["noteOnFail"] != "REGISTRY_UNREADABLE/LOAD_FAILED":
        P(f"⑤ 실패 note가 tCode(code, failKey) 경유가 아니다 — {data['noteOnFail']}")

    # ═══ ⑥ 입력값 보존 ═══════════════════════════════════════════════════════
    snap = r["snapshot"]
    if snap["snapshots"] != ["delete", "delete"] or snap["nameSnapshots"] != ["새 이름", "새 이름"]:
        P(f"★⑥ 언마운트 스냅샷이 렌더러마다 1회씩 최신 값으로 나가지 않았다 — "
          f"{snap['snapshots']} / {snap['nameSnapshots']} (가상 키보드로 찍은 값이 B 오조작 "
          f"한 번에 사라진다)")
    if snap["restoredInitial"] != "delete":
        P(f"★⑥ 보존값을 initial로 줬는데 화면이 복원하지 않는다({snap['restoredInitial']!r})")

    print("팝업 공통 기반 — 골격·뷰·게이트 양 모드·실패·로드·입력 보존 (렌더로 측정)")
    print(f"  ① 경계 in DialogBody={sk['boundaryInsideBody']} · closeModal 도달="
          f"{sk['closeModalReachedRoot']} · 크기 지정={sk['sizeProps'] or '없음'}")
    print(f"  ② key: list={vw['listKey']} detail={vw['detailKey']} · 뒤로 첫 요소="
          f"{vw['firstChildIsBack']} · B 배선={vw['hasOnCancelButton']}")
    print(f"  ③ 문구 동일 3종 · okDisabled {gate['resetBefore']['nestedOkDisabled']}→"
          f"{gate['resetAfter']['nestedOkDisabled']} · onOK 값={gate['resetValues']}")
    print(f"  ③′ spec화 전후: 파라미터 조합 {len(r['parity'])}건 신구 렌더 대조 · 손실="
          f"{parity_lost or '없음'}")
    print(f"  ③″ 생명주기: 닫기 {life['nestedCloses']}회 · onOK {life['okFiredOnce']}회 · "
          f"throw에도 닫힘(중첩 {life['throwClosedNested']}/폴백 {life['throwClosedFallback']})")
    print(f"  ④ 중첩 모달={nested['modalsShown']} / 폴백 오버레이={fallback['overlayShown']}"
          f"(원 콘텐츠 미렌더={not fallback['originalContentRendered']}) · 실패 note={fail['notes']}")
    print(f"  ⑤ 조회 {data['mountCalls']}→{data['afterReloadCalls']}회 · 표시명 선반영="
          f"{data['profileNamesTaken']}회 · ⑥ 복원={snap['restoredInitial']!r}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
