import {
  useCallback, useEffect, useRef, useState, type ComponentProps, type ReactNode,
} from "react";
import {
  ConfirmModal, DialogBody, DialogButton, DialogHeader, Focusable, ModalRoot,
  NavEntryPositionPreferences, TextField, showModal,
} from "./deckyui";
import { setProfileNames, t, tCode, type StringKey } from "./i18n";
import { POPUP_LIST_FOCUS_SLACK, POPUP_LIST_MAX_HEIGHT, POPUP_LIST_TAIL_PAD } from "./limits";
import type { Env } from "./rpc";
import { ErrorBoundary } from "./ui/ErrorBoundary";

/**
 * **팝업 공통 기반** (설계 §4) — 팝업 G·D·S가 공유하는 골격·뷰·확인 게이트·데이터 로드.
 *
 * ★★ 이 파일이 존재하는 이유: 팝업 3종이 각자 ModalRoot를 조립하면 **경계 배치·닫기 배선·
 *   확인창 생명주기가 세 벌**이 되고, 그중 하나가 틀린 날 그 화면만 조용히 다르게 동작한다.
 *   여기서 한 번 맞추면 나머지는 내용만 채운다.
 *
 * ★ 소비자는 **넷**이다: 팝업 G·D·S(P13·P14)와 QAM(P15-E — `useDataDoor`만 직접 쓴다).
 *   P12에 기반만 놓였던 신·구 공존기는 P15-D 원자 제거로 끝났다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const NOTE_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
/**
 * 동작 note 아래에 붙는 **보조 줄**(P15-E R4) — 지금은 "다시 읽지 못했다" 한 종류다.
 * 한 단계 작은 글자라 *"방금 한 일"*과 *"화면이 낡았을 수 있다"*가 시각적으로 갈린다.
 */
const SUB_NOTE_STYLE = { fontSize: "11px", color: "#9aa0a6", wordBreak: "keep-all" } as const;

/** 아이콘이 제목과 같은 줄에 설 때의 자리. 색은 주변을 따라간다(아이콘은 currentColor다). */
const HEADER_ICON_STYLE = { display: "inline-flex", marginRight: "6px", verticalAlign: "-0.1em" } as const;

/**
 * **버튼 라벨 앞 아이콘 자리**(§3-A 10판) — 고정 폭이라 아이콘 유무로 버튼 폭이 흔들리지 않는다(GP#2).
 *
 * ★★ 아이콘 관용구는 프로젝트에 **하나**다: `<span style={ICON_SLOT_STYLE}><Icon/></span>{label}`.
 *   `ButtonItem`의 `icon` prop은 버튼 내용이 아니라 **Field의 라벨 슬롯**이라 아이콘이 버튼 **위**에
 *   고아로 뜨고(D2 실측) 그 슬롯의 부모 높이가 아이콘을 16×20으로 구긴다(D6) — 그래서 QAM도
 *   팝업과 같은 이 관용구를 쓴다.
 * ★ 왜 여기 있는가: P16까지 `GamesPopup`·`SettingsPopup`·`DiscoverPopup`이 **같은 값을 각자** 들고
 *   있었다. 한쪽만 손대는 날 아이콘 배치가 화면마다 갈린다 — `CARD_STYLE`을 여기로 모은 것과 같은
 *   판단이다. 소비자는 다섯이다: 팝업 3종 + QAM의 `index.tsx`·`BulkApplyButton.tsx`.
 *
 * ★★ `verticalAlign`을 **반드시** 준다 — 빠뜨리면 아이콘이 버튼 중심보다 위로 뜬다(2026-08-13 반려).
 *   inline-flex 상자의 기본값은 `baseline`이고, 그 상자의 baseline은 첫 flex 항목인 svg의
 *   **하단 margin edge**다. 즉 아이콘 밑변이 글자 baseline에 앉는데, 글자의 시각 중심은 baseline보다
 *   위(=`(A−D)/2`, A·D는 폰트 ascent·descent)에 있으므로 **아이콘만 상대적으로 떠오른다.**
 *   QAM 실측(버튼 h40 · svg top +10 · h16)으로 이 폰트의 `(A−D)/2 = 0.375em`이 나왔고,
 *   필요한 하강량 = `(A−D)/2 − 0.5em` = **−0.125em**이다(길이 오프셋은 양수가 위로 올린다).
 *   이 값이 em인 것이 핵심이다 — 오차의 정체가 **폰트 비례량**이라 QAM(16px)과 팝업 버튼(13px)에
 *   같은 상수 하나로 맞는다. 위 항등식은 line-height와 무관하므로 줄 높이가 달라져도 유효하다.
 *   ⚠️ `verticalAlign:"middle"`은 답이 아니다: 아이콘 중심을 `baseline − x-height/2`에 놓는데
 *   이 폰트는 x-height ≈ 0.52em이라 필요한 0.75em에 못 미쳐 **오차가 −2px에서 +1.8px로 뒤집힐 뿐**이다
 *   (산술 검증 — 실기 rect로 재판정한다). 바로 위 `HEADER_ICON_STYLE`이 같은 계열의 −0.1em을
 *   경험적으로 들고 있는 것도 같은 원인의 흔적이다.
 */
export const ICON_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginRight: "4px",
  verticalAlign: "-0.125em",
} as const;

/**
 * **한국어 낱말 보존**(`word-break: keep-all`) — `ButtonItem`의 `description` 슬롯 전용 관용구.
 *
 * ★★ 왜 필요한가: CSS 기본 줄바꿈은 한국어를 **글자 단위**로 끊는다. QAM 잔글씨 컨테이너는
 *   268px뿐이라 한 문장이 두 줄로 감기는데, 그 자리가 낱말 한가운데다 —
 *   실기에서 "…게임만 대상 / 으로 합니다."로 갈라진 것이 접수 경위다(2026-08-13).
 *   `keep-all`은 낱말 경계에서만 끊게 하는 표준 속성이고, 문장을 짧게 다듬는 땜빵과 달리
 *   **그 자리를 쓰는 모든 한국어 문장이 함께** 고쳐진다.
 *
 * ★ 다른 잔글씨 슬롯은 이 상수를 쓰지 않는다 — 자기 스타일 상수에 속성을 직접 실었다.
 *   여기에 상수가 따로 있는 이유는 **`description`이 style을 받지 않는 prop**이기 때문이다:
 *   `<ButtonItem description={<span style={KEEP_ALL_STYLE}>{…}</span>}>`가 유일한 통로다.
 *   소비자는 둘 — QAM의 진입 버튼(`index.tsx`)과 일괄 적용 버튼의 사유 줄(`BulkApplyButton`).
 *
 * ⚠️ **경로·파일명 슬롯에는 걸지 않는다**(`GAME_CONFIG_PATH`·`BACKUP_ROW_META`·후보 경로).
 *   끊을 낱말 경계가 없는 문자열이라 넘칠 수 있다 — 그 자리는 `PATH_STYLE` 계열이 맡고,
 *   `word-break`가 **상속되는 속성**이라 그쪽은 `normal`을 명시해 조상의 값을 되돌린다.
 */
export const KEEP_ALL_STYLE = { wordBreak: "keep-all" } as const;

/**
 * **경로·파일명을 그리는 자리의 줄바꿈 규칙**(실기 결함 2026-08-15 ⑤) — 잔글씨 스타일에 얹어 쓴다.
 *
 * ★★ 왜 규칙만 상수로 빼는가: 소비자마다 글자 크기가 다르다(팝업 11px · 확인창 12px). 스타일을
 *   통째로 공유하려 하면 크기까지 억지로 맞추게 되고, 결국 각자 복사해 갈라진다. **갈리면 안 되는
 *   것은 줄바꿈 규칙 하나**이므로 그것만 이름을 준다.
 * ★ `wordBreak:"normal"` — `word-break`는 **상속되는 속성**이라 조상이 `keep-all`이면 여기까지
 *   내려온다. 경로에는 끊을 낱말 경계가 없어 그러면 줄이 통째로 넘친다.
 * ★★ `overflowWrap:"anywhere"` — **이것이 2026-08-15 실기 ⑤의 수정 본체다.** `normal`만으로는
 *   *"넘칠 때 아무 데서나 끊어도 된다"*는 허가가 없다. 경로에는 공백도 하이픈도 없어 줄바꿈
 *   기회가 **0개**이므로, 한 줄이 팝업을 넘고 **모니터 화면 밖까지** 밀고 나갔다(사용자 사진으로
 *   확정 — Forza의 compatdata 경로). `anywhere`는 넘칠 때만 끊으므로 짧은 경로의 모습은 그대로다.
 *   ⚠️ `break-all`이 아니다: 그쪽은 넘치지 않아도 아무 데서나 끊어 짧은 이름까지 흉해진다.
 *   ⚠️ `anywhere`가 `break-word`보다 나은 이유는 **min-content 폭까지 줄여** 부모 flex/모달이
 *   경로 길이에 끌려 넓어지는 것을 막는다는 점이다 — 팝업이 크기를 지정하지 않는(A10) 이 화면에서
 *   그 차이가 곧 "화면 밖으로 나가는가"를 가른다.
 */
export const PATH_BREAK_STYLE = { wordBreak: "normal", overflowWrap: "anywhere" } as const;

// ── 골격 (§4-A) ──────────────────────────────────────────────────────────────

/**
 * 중앙 팝업 하나. **크기를 지정하지 않는다**(A10 — `popupWidth`/`popupHeight`/`bAllowFullSize` 금지).
 *
 * ★★ `ErrorBoundary`는 **`DialogBody` 안쪽**이다(R-4). `showModal`은 `closeModal`을
 *   **최상위 엘리먼트에만** 주입하므로(구 화면들이 계약으로 문서화해 둔 실측 사실),
 *   최상위를 경계로 감싸면 주입이 경계에서 삼켜져 **닫기 배선이 죽는다.**
 *   한계도 정직하게: **ModalRoot 자체의 렌더 실패는 이 경계가 못 가둔다** — 그건 호출부의
 *   `showModal` try/catch가 실패 고지로 받는다(§3-A 문법, 이 파일의 `useConfirmGate`와 동형).
 *
 * ⚠️ `onCancel`(=ModalRoot의 B 처리)은 **받아만 두고 지금은 아무도 주지 않는다**(§4-E ③):
 *   B의 실동작은 비목록 뷰의 `Focusable.onCancelButton`으로 잡는 것이 1안이고, ModalRoot까지
 *   동시에 건드리면 실기에서 어느 쪽이 잡았는지 가릴 수 없다. 구조만 열어 둔다.
 */
export function GfxPopup({
  title,
  icon,
  where,
  closeModal,
  onCancel,
  children,
}: {
  title: string;
  icon?: ReactNode;
  /** 로그에서 어느 팝업인지 가르는 값 — 화면에 뜨지 않는다(`popup-g|d|s`). */
  where: string;
  /** `showModal`이 최상위 엘리먼트에 주입한다. 그대로 ModalRoot에 넘긴다. */
  closeModal?: () => void;
  onCancel?: () => void;
  children: ReactNode;
}) {
  return (
    <ModalRoot closeModal={closeModal} onCancel={onCancel}>
      <DialogHeader>
        {icon ? <span style={HEADER_ICON_STYLE}>{icon}</span> : null}
        {title}
      </DialogHeader>
      <DialogBody>
        <ErrorBoundary where={where}>{children}</ErrorBoundary>
      </DialogBody>
    </ModalRoot>
  );
}

// ── 버튼 (§4-G) ──────────────────────────────────────────────────────────────

/**
 * **팝업 층의 버튼은 전부 이것으로 그린다**(§4-G 10판 신설 — D1).
 *
 * ★★ 왜 래퍼인가: Steam 본체 CSS가 `button.DialogButton { width:100% }`를 **전역**으로 건다.
 *   블록 부모만의 이야기가 아니다 — flex 자식에도 발현한다(`flex-basis:auto`가 width를 읽는다).
 *   실기 실측: 목록 행의 적용 버튼이 각각 **584.7px**로 부풀고, 그 옆 게임 이름 div는
 *   **0px로 붕괴**해 식별 불가가 됐다. [내장 적용]과 chevron은 모달 오른쪽 **밖**으로 밀렸다.
 *   진단 초안은 "블록 부모 4곳만 오염"으로 봤는데 그건 실측으로 반증됐다.
 *
 * ★★ 그래서 **문을 하나로 만든다.** 네 자리를 골라 고치면 다음에 추가되는 버튼이 같은 함정에
 *   빠지고, 그때는 아무도 이 사실을 기억하지 못한다. 래퍼 + `build.sh` grep ⑤(DialogButton
 *   직접 사용은 이 파일만 허용)로 **빠뜨릴 자리 자체를 없앤다** — E1을 텍스트 검사에서 구조로
 *   옮긴 것과 같은 판단이다(「구조로 예외를 없애라」).
 *
 * ★ `fit-content`를 호출부 style **뒤에** 병합하는 이유: 먼저 병합하면 호출부가 무심코
 *   width를 얹어 문이 샌다. 호출부는 width를 지정하지 않는다 — minWidth·flex·padding·색만.
 *   팝업 층에서 전폭 버튼이 필요한 자리는 실측상 0곳이다.
 *
 * ⚠️ **폭은 자동 검사로 판정되지 않는다.** 화면 프로브는 삭제됐고(사용자 결정 — 검사는 엔진·핵심
 *   기능에만), 애초에 Steam 스타일시트가 프로브에 없어 원리적으로도 못 잡았다.
 *   판정 수단은 **실기 CDP 스타일 조회나 스샷뿐**이다.
 *
 * ⚠️ 타입은 `ComponentProps<typeof DialogButton>`이다. `DialogButtonProps`를 `@decky/ui`에서
 *   직접 import하면 **build.sh grep ①(단일 관문) 위반**이고 `deckyui.ts`는 그 타입을
 *   재수출하지 않는다.
 * ⚠️ `children`을 구조분해해 JSX 자식으로 넘기는 **관례의 근거는 소멸했다**: 그렇게 하라고
 *   요구하던 것은 라벨을 JSX 자리에서만 읽던 `qa/probe_kit.cjs`였고, 그 프로브는
 *   2026-08-15 UI 검사 계열 삭제에 함께 지워졌다. 지금 이 형태를 강제하는 검사는 없다.
 *   `{...props}`에 남겨도 렌더 결과는 같으므로 **바꿀 이유도 없어** 표준 JSX 표기로 둔다.
 * ⚠️ `ref`는 투과되지 않는다(`ComponentProps`에 RefAttributes가 없다). 현 호출부에 ref 사용이
 *   0이라 무해하고, 필요해지는 날 forwardRef로 확장한다 — **지금 만들지 않는다.**
 */
export function PopupButton({ style, children, ...props }: ComponentProps<typeof DialogButton>) {
  return <DialogButton {...props} style={{ ...style, width: "fit-content" }}>{children}</DialogButton>;
}

/**
 * **세로 스택 동작 버튼**의 자리(§4-G 3항) — 설명 줄을 아래에 거느리는 버튼이다.
 *
 * ★ 좌측 정렬인 이유: 현행은 버튼 글자가 가운데, 바로 아래 설명은 왼쪽이라 **축이 어긋난다.**
 *   `fit-content`로 폭이 접히면 그 어긋남이 더 크게 보인다.
 * ⚠️ 가로 행 버튼은 대상이 아니다(이름 바꾸기 2 · [다시 검색]·[모두 추가] 줄 · 목록 행 버튼) —
 *   그것들은 행 안에서 제 폭만 접으면 된다.
 */
export const STACKED_BUTTON_STYLE = {
  alignSelf: "flex-start", textAlign: "left", justifyContent: "flex-start",
} as const;

/**
 * 세로 스택 버튼의 **설명 줄 들여쓰기** — 버튼의 가로 패딩과 같은 값이라 라벨과 설명이
 * **정렬 축을 공유**한다. 값이 두 곳에 살면 한쪽만 고치는 날 축이 다시 갈린다.
 */
export const STACKED_DESC_PAD = "10px";

// ── 내부 뷰 (§4-B) ───────────────────────────────────────────────────────────

/** 팝업 G의 뷰. 깊이 최대 2이고 부모가 **정적**이라 뒤로가기 대상이 분기하지 않는다. */
export type GView =
  | { kind: "list" }
  | { kind: "detail"; appid: string }
  | { kind: "backups"; appid: string };

/** 팝업 D의 뷰. */
export type DView = { kind: "main" } | { kind: "excluded" };

/**
 * 그 뷰를 그릴 때 쓸 `key` — **목록 뷰에는 주지 않는다**(GP#3).
 *
 * ★ 초판의 `key={view.kind}` 전면 리마운트는 목록 상태(스크롤·마지막 조작 행)를 매번 버렸다.
 *   상세·백업·제외 뷰는 리마운트가 이득이고(스크롤 초기화) 목록은 손해다 —
 *   그래서 **key를 주는 쪽만 정한다.** `undefined`면 React가 같은 자리로 보고 상태를 보존한다.
 */
export function subViewKey(view: { kind: string }): string | undefined {
  return view.kind === "list" || view.kind === "main" ? undefined : view.kind;
}

/**
 * 비목록 뷰의 껍데기 — **`[← 뒤로]`가 DialogBody 최상단 첫 요소**다(§4-B).
 *
 * ★ 첫 요소인 이유: 진입 직후 B가 안 먹는 것으로 드러나도(실기 ③) 화면에 보이는 탈출구가
 *   스크롤 밖으로 밀리지 않는다.
 * ★ B = 한 단계 뒤로(§4-E ③ 1안): 본문을 감싸는 `Focusable`에 `onCancelButton`을 건다.
 *   실효는 미검증이고 **폴백이 무해**하다 — 안 먹으면 위 버튼만 남는다(기능 손실 0).
 * ★ 초기 포커스도 여기서 준다(§4-E ①: 상세·백업·제외 뷰의 착지 대상 = `[← 뒤로]`) —
 *   뷰마다 각자 지정하면 한 뷰가 빠지고, 빠진 뷰에서만 착지가 달라진다.
 * ★★ 그 지정이 **실제로 읽히게** 하는 짝이 `preferredChildEntryProps`다(2026-08-15 D4 후속).
 *   없으면 `preferredFocus`는 조용히 무효이고, 지금까지 착지가 맞았던 것은 `[← 뒤로]`가
 *   **문서 순서 첫째**라서 생긴 우연이다 — 이 뷰들에 위쪽 요소가 하나라도 생기는 날 그 우연이
 *   깨지고, 깨진 것을 알 방법이 없다. 그래서 **눈에 보이는 변화 없이** 우연을 계약으로 바꾼다.
 */
export function PopupSubView({
  onBack,
  children,
}: {
  onBack: () => void;
  children: ReactNode;
}) {
  return (
    <Focusable
      {...preferredChildEntryProps}
      onCancelButton={onBack}
      onCancelActionDescription={t("BACK")}
      style={COLUMN_STYLE}
    >
      <PopupButton
        preferredFocus
        onClick={onBack}
        style={{ alignSelf: "flex-start", minWidth: "96px", padding: "6px 10px", fontSize: "13px" }}
      >
        {t("BACK")}
      </PopupButton>
      {children}
    </Focusable>
  );
}

/**
 * 목록 **카드**(§5-A R1 ④-A) — 팝업 G의 게임·백업 행과 팝업 D의 후보 행이 같은 모양이어야 한다.
 *
 * ★ **주황 경고 테두리는 없다**(A6 — "프로필 없음"·"미등록"은 정상 상태이고, 상태는 배지가 말한다).
 * ★ 왜 여기 있는가: P13까지는 `GamesPopup` 안의 private 상수였는데 P14에서 소비자가 둘이 됐다.
 *   같은 값을 두 파일이 각자 들고 있으면 한쪽만 손대는 날 **같은 목록이 화면마다 달라진다** —
 *   `POPUP_LIST_MAX_HEIGHT`를 `limits.ts` 한 곳으로 모은 것과 같은 판단이다.
 */
export const CARD_STYLE = {
  background: "rgba(255,255,255,0.05)",
  borderRadius: "4px",
  padding: "8px 10px",
  marginBottom: "4px",
} as const;

/**
 * 카드 **내용**의 폭 상한(GP#11 — F4 재발 방지).
 *
 * 모달 자체 크기는 지정하지 않는다(A10). 대신 행 내용의 폭을 접어 이름과 버튼이 화면 양 끝으로
 * 벌어지는 것을 막는다 — 그 벌어짐이 *"버튼과 게임이 안 맞물려 보인다"*(F4)의 실체다.
 * 실측 폭(§16-⑥)이 나오면 이 숫자 하나만 고친다.
 */
export const CARD_INNER_STYLE = {
  maxWidth: "720px", display: "flex", flexDirection: "column", gap: "4px",
} as const;

/**
 * 목록 스크롤 컨테이너(§4-D) — 높이 상한과 하단 완충이 **한 곳**에서 온다.
 *
 * ★ 행마다 패딩을 두지 않는다: 값이 두 곳에 있으면 새 목록이 생길 때 한쪽을 빠뜨리고,
 *   빠뜨린 목록에서 GP#15가 그대로 재발한다(전체 화면 시절 하단 여백 상수의 교훈 그대로).
 */
export function PopupScrollList({ children }: { children: ReactNode }) {
  return (
    <Focusable
      style={{
        display: "flex",
        flexDirection: "column",
        maxHeight: POPUP_LIST_MAX_HEIGHT,
        overflowY: "auto",
        paddingBottom: POPUP_LIST_TAIL_PAD,
        /* ★ 패드로 맨 아래에 닿았을 때 **마지막 카드가 잘리지 않게** 하는 유일한 자리
           (실기 결함 2026-08-15 ② — 근거·숫자는 `limits.ts`의 이 상수 주석이 정본).
           Steam은 포커스 요소 하단을 컨테이너 하단에 맞추고 멈추므로, 그 요소보다 아래에 있는
           카드 메타 줄은 `paddingBottom`으로는 절대 보이지 않는다. */
        scrollPaddingBottom: POPUP_LIST_FOCUS_SLACK,
      }}
    >
      {children}
    </Focusable>
  );
}

/**
 * 목록 **행**에 붙이는 이동 성향(§4-E ②) — 수직 이동 중 커서가 좌우로 튀는 것을 막는다.
 *
 * ★ 숫자 2를 박지 않는다 — 라이브러리 enum을 쓴다(`deckyui.ts` 주석 참조).
 * ★ 이것은 2중 방어의 한 겹이다(다른 겹 = 버튼 폭 고정 §5-A). 런타임 실효는 실기 ④가 판정하고,
 *   안 먹어도 화면은 그대로 동작한다.
 */
export const listRowNavProps = {
  navEntryPreferPosition: NavEntryPositionPreferences.MAINTAIN_X,
} as const;

/**
 * **`preferredFocus`를 실제로 듣게 만드는 선언**(§4-E ① — 2026-08-15 실기 D4).
 *
 * ★★ 왜 이것 없이는 무효인가(Steam 본체 실측 — `steamui/library.js`
 *   `FindFocusableDescendant`): 컨테이너로 포커스가 **들어올 때** Steam은 자기
 *   `navEntryPreferPosition`을 보고 갈래를 고르는데, 자손의 `BWantsPreferredFocus()`를
 *   훑는 BFS는 **`PREFERRED_CHILD`인 갈래에만** 있다. 그 밖의 값(우리 기본값 = 지정 없음)이면
 *   곧장 `FindNextFocusableChildInDirection(FORWARD)`로 떨어져 **문서 순서 첫 focusable**이
 *   가져간다. 그래서 카드에 `preferredFocus`를 아무리 달아도 목록 위의 필터 줄이 이겼다
 *   (실기: 팝업을 열면 초기 포커스가 필터 토글) — **오타가 아니라 조용한 무효**다.
 * ★ 그래서 선언은 **자식이 아니라 진입 컨테이너**에 붙는다: `preferredFocus`(어느 자식인가)와
 *   이 prop(그 표시를 볼 것인가)은 **한 쌍**이고, 한쪽만 있으면 아무 일도 일어나지 않는다.
 * ★ BFS는 깊이 무관이라 컨테이너와 카드 사이에 스크롤 래퍼가 끼어도 찾아낸다.
 * ⚠️ 붙일 자리는 **`preferredFocus`를 단 자손 전체를 품는 가장 바깥 컨테이너**다. 스크롤
 *   목록에만 붙이면 포커스가 그 목록에 들어올 때만 듣는데, 팝업 진입은 그 **바깥**에서
 *   시작하므로 여전히 필터 줄에 선다(실기에서 실제로 그렇게 났다).
 */
export const preferredChildEntryProps = {
  navEntryPreferPosition: NavEntryPositionPreferences.PREFERRED_CHILD,
} as const;

/**
 * **가로로 늘어선 버튼 줄**에 붙인다(§4-E ② 보강 — 실기 결함 2026-08-15 ①).
 *
 * ★★ 값은 반드시 **`"row"`**다. Steam 본체가 받는 낱말은 `column`·`column-reverse`·`row`·
 *   `row-reverse`·`grid`·`geometric` **여섯뿐**이고(steamui `library.js`의 flow-children
 *   해석 함수 실측), 그 밖의 낱말은 콘솔에 `Unhandled flow-children: …`을 찍고 **`NONE`**,
 *   즉 *"지정하지 않은 것"*이 된다. 흔히 보이는 `"horizontal"`도 여기에 걸린다 —
 *   **오타가 아니라 조용한 무효**라서 화면은 고쳐진 것처럼 보이고 실기에서만 안 고쳐진다.
 * ★★ 지정이 없으면(=NONE) Steam은 **그 Focusable의 계산된 스타일로 방향을 추정한다**:
 *   `display:flex`면 `flex-direction`을 그대로 따르고(단 `flex-wrap:wrap`이면 `grid`),
 *   그 밖의 경우는 **`column`으로 떨어진다**. 그래서 *이미 flex 행인 컨테이너는 지정이 없어도
 *   좌우가 살아 있었고*, **행 스타일이 flex가 아닌 컨테이너**(예: 목록 카드 — 배경·패딩만
 *   있는 블록)만 세로로 오판돼 좌우 키가 죽었다. 실기 ①의 `[eGPU 적용][내장 적용][›]`이
 *   정확히 그 자리다(자식 3개가 한 줄인데 카드는 블록이라 `column`으로 추정됐다).
 * ★ 상수로 두는 이유: 새 버튼 줄이 생길 때마다 하이픈 prop을 손으로 적으면 언젠가 한 줄이
 *   빠지고, 빠진 그 줄에서만 좌우가 죽는다 — 실기에서만 드러나는 결함이라 발견이 가장 늦다.
 *   추정에 기대지 않고 **선언해 두면** 나중에 배치 스타일을 손대도 이동이 따라 무너지지 않는다.
 * ⚠️ **가로로 놓인 focusable이 둘 이상일 때만** 붙인다. 세로로 쌓인 묶음에 붙이면 반대로
 *   상하가 죽는다. focusable이 하나뿐인 행(백업 행·후보 행)은 붙일 이유가 없다.
 */
export const ROW_FLOW = { "flow-children": "row" } as const;

// ── 확인 게이트 (§4-C) ───────────────────────────────────────────────────────

interface ConfirmSpecBase {
  title: string;
  /** 기존 확인창들의 `strDescription` 내용물 그대로. */
  body: ReactNode;
  /** ⚠ 강조 블록(전체 초기화 전용 — A8). */
  warnBlock?: ReactNode;
  okText: string;
  cancelText?: string;
  /**
   * **취소가 없는 창**(§4-I ④ 결과 팝업). 되돌릴 것이 없는 통지에 [취소]가 있으면
   * *"취소하면 되돌려지나?"*라는 **없는 선택지**를 만든다.
   * ★ 두 렌더러가 같은 것을 그린다: 중첩은 Steam의 `bAlertDialog`(OK 단독 — 실물 선례
   *   `674.js`의 알림 계열이 전부 이 조합이다), 폴백은 취소 버튼을 **아예 그리지 않는다.**
   * ⚠️ `bAlertDialog`가 이 빌드에서 실제로 취소를 감추는지는 **실기 판정**이다. 안 먹으면
   *   결과 팝업에 [취소]가 하나 더 보일 뿐이고 누르면 같이 닫힌다 — 손실 없는 실패다.
   */
  noCancel?: boolean;
}

export interface PlainConfirmSpec extends ConfirmSpecBase {
  kind: "plain";
  onOK: () => void;
}

export interface InputConfirmSpec extends ConfirmSpecBase {
  kind: "input";
  /** 렌더러가 TextField와 그 상태를 **소유**한다(호출부는 값을 들고 있지 않는다). */
  input: { label: string; initial: string };
  /** 입력값에서 파생하는 동적 비활성. 미지정 = OK 항상 활성. */
  okDisabled?: (value: string) => boolean;
  onOK: (value: string) => void;
  /** 언마운트 직전 마지막 입력값 — 호출부가 보존했다가 `input.initial`로 되돌려준다(GP#9). */
  onInputSnapshot?: (value: string) => void;
}

/**
 * 확인창 하나의 **선언**. 렌더 방식(중첩/폴백)과 무관하게 같은 값을 그린다.
 *
 * ★★ 왜 union인가(Codex N-03): `onOK(inputValue?: string)` 단일형은 strict 빌드에서
 *   `string | undefined`가 `runRename(name: string)` 같은 **실물 시그니처와 충돌**한다.
 *   `kind`로 갈라 두면 렌더러가 타입 내로잉으로 `string` 확정을 얻는다.
 */
export type ConfirmSpec = PlainConfirmSpec | InputConfirmSpec;

/**
 * 확인창을 **중첩 모달로** 띄울지, 팝업 **내부 오버레이**로 그릴지.
 *
 * ★ 실기(§16-②)에서 중첩이 실패하면 **이 한 줄만 false**로 바꾼다 — 두 렌더러가 같은 spec을
 *   같은 요소로 그리므로 호출부는 한 줄도 안 바뀐다. 그것이 이 구조의 값어치다.
 */
export const NESTED_CONFIRM = true;

/**
 * 게이트가 **창을 못 띄웠을 때 할 말**의 재료 — 키 하나이거나, **치환자가 있으면 값까지** 온다.
 *
 * ★★ 왜 키만으로는 안 되는가(2026-08-15 QA R3): 이 자리의 문구는 *"무엇이 안 됐고 이제 무엇을
 *   누르면 되는가"*를 말하는데, 그 「무엇」이 **경로마다 다른 값**일 수 있다. 실제로 복원 후속
 *   제안의 실패 문구는 `{profile}`을 품게 됐는데 게이트가 `t(key)`만 부르고 있어 화면에
 *   **중괄호가 그대로** 떴고, *"[{profile} 적용]을 눌러 주세요"*가 어느 버튼인지 지목하지
 *   못했다 — 두 적용 버튼 중 **틀린 쪽을 누르면 다른 프로필이 게임에 쓰인다.**
 * ★ 그래서 **문을 넓힌다**: 치환자를 키에서 걷어내면 그 한 문장은 고쳐지지만, 다음에 같은
 *   필요가 생기는 자리에서 똑같이 재발한다. 계약이 치환자를 인정하면 재발할 자리가 없다.
 * ★ 키만 주는 호출부는 **한 글자도 바뀌지 않는다**(문자열이 그대로 유효한 값이다).
 */
export type GateFailure = StringKey | { key: StringKey; params: Record<string, string | number> };

/** 게이트 실패 문구를 만드는 **단일 관문** — 두 형태를 여기서만 푼다. */
function failText(fail: GateFailure): string {
  return typeof fail === "string" ? t(fail) : t(fail.key, fail.params);
}

/** 게이트 시그니처 — **실패 문구는 호출부가 준다**(공유 문장이 어느 경로에선 거짓이 되는 사고 방지). */
export type ConfirmGate = (spec: ConfirmSpec, fail: GateFailure, onFail: (msg: string) => void) => void;

/**
 * 두 렌더러가 공유하는 **한 벌의 상태·계약**(D-05).
 *
 * ★★ 단일 종료(D-05 ②): OK와 취소는 상호 배타이고 `onOK`는 **최대 1회**다. 두 번째 눌림이
 *   도착할 때 이미 닫히는 중일 수 있고, 그때 한 번 더 발화하면 토큰을 두 번 쓰거나 같은 파괴를
 *   두 번 요청한다.
 *   ⚠️ 빗장은 **상태가 아니라 ref**다(2026-08-12 프로브가 실제로 뚫었다): 상태로 막으면
 *     두 번째 눌림이 **재렌더 전에** 도착할 때 낡은 핸들러가 `done=false`를 보고 그대로
 *     통과한다 — 빅픽처의 이중 탭이 정확히 그 타이밍이다. ref는 같은 틱에 즉시 잠긴다.
 *     (`done` 상태는 버튼을 비활성으로 **보이게** 하는 몫만 맡는다.)
 * ★ 입력 스냅샷(GP#9)은 **언마운트 시 1회**다. 렌더러가 사라지는 시점이 곧 값을 잃는 시점이라,
 *   그 자리에서만 알려 주면 호출부는 "언제 저장할까"를 판단할 필요가 없다.
 */
function useSpecGate(spec: ConfirmSpec, close?: () => void) {
  const [value, setValue] = useState(spec.kind === "input" ? spec.input.initial : "");
  const [done, setDone] = useState(false);
  const fired = useRef(false);
  // 언마운트 시점에 최신 값을 읽어야 한다 — 클로저에 갇힌 초기값을 알리면 보존이 거짓말이 된다.
  const latest = useRef(value);
  latest.current = value;
  const snapshot = spec.kind === "input" ? spec.onInputSnapshot : undefined;
  useEffect(
    () => () => { snapshot?.(latest.current); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const fire = (ok: boolean) => {
    if (fired.current) return;           // 단일 종료 — 두 번째 눌림은 없던 일이다
    fired.current = true;                // 같은 틱에 잠근다(재렌더를 기다리지 않는다)
    setDone(true);                       // 화면에서도 비활성으로 보이게
    try {
      if (ok) {
        if (spec.kind === "input") spec.onOK(latest.current);
        else spec.onOK();
      }
    } finally {
      // ★ OK 후 종료 정책(D-05 ③): RPC 결과를 기다리지 않고 **즉시** 닫는다.
      //   결과·오류는 팝업 note가 보고하고, TOCTOU 재질문은 갱신 params로 **새** 창을 연다.
      // ★★ `finally`인 이유: `onOK`가 **동기적으로 던지면**(호출부의 버그·목 실패) 닫기가
      //   건너뛰어져 **확인창이 화면에 남고 빗장만 걸린** 상태가 된다 — 아무 버튼도 안 듣는
      //   창이 떠 있는, 사용자가 빠져나갈 수 없는 자리다. 던지든 말든 창은 닫는다.
      close?.();
    }
  };

  return {
    value,
    setValue,
    done,
    okDisabled: (spec.kind === "input" ? !!spec.okDisabled?.(value) : false) || done,
    onOK: () => fire(true),
    onCancel: () => fire(false),
  };
}

/**
 * 두 렌더러가 그리는 **같은 본문**. 여기 한 곳에서 만들어야 중첩/폴백의 문구가 갈리지 않는다.
 *
 * ⚠️ 문자열을 `"\n\n"`로 이어 붙이지 않는다 — 2026-08-07 실기에서 **한 문단으로 뭉쳐** 렌더됐다.
 *   `ReactNode`는 엘리먼트로 줘야 줄이 갈린다.
 */
function specBody(
  spec: ConfirmSpec,
  value: string,
  setValue: (v: string) => void,
): ReactNode {
  return (
    <div style={COLUMN_STYLE}>
      {spec.warnBlock ? <div style={{ color: "#ffb454" }}>{spec.warnBlock}</div> : null}
      {spec.body}
      {spec.kind === "input" ? (
        <TextField
          label={spec.input.label}
          value={value}
          /* 빅픽처에서 텍스트 필드가 포커스를 받아야 가상 키보드가 뜬다(U20 ① 실기 대상). */
          focusOnMount
          style={INPUT_FACE_STYLE}
          onChange={(e) => setValue(e.target.value)}
        />
      ) : null}
    </div>
  );
}

/**
 * **입력형 확인창의 입력면**(§4-C 10판 — 실기 신규 소견 ⓐ).
 *
 * ★★ Steam `TextField`의 기본값은 **흰 통짜 면**이다. 어두운 다이얼로그 한가운데서 그것만
 *   튀어 "이 창의 일부가 아닌 것"처럼 보인다(실기 확인). 계약은 *"입력면은 주변 다이얼로그
 *   배경과 같은 어두운 계열이고, 경계는 미세 대비 또는 1px 윤곽으로 식별된다"*이다.
 * ★ 이 자리가 하나인 이유: 중첩(`SpecConfirmModal`)과 폴백(`ConfirmOverlay`)이 **같은
 *   `specBody`를 그린다.** 두 렌더러가 같은 것을 그린다는 §4-C 계약이 있으므로, 시각도 그
 *   한 곳에 산다 — 각자 칠하면 언젠가 두 모드의 입력창이 달라 보인다.
 * ★ 윤곽 색은 새로 지어낸 값이 아니다 — 9판 상태박스 테두리가 쓰던 값을 그대로 물려받았다.
 *   글자색만 명시한다: 면이 어두워졌으므로 상속에 맡기면 안 읽힐 수 있다.
 * ⚠️ 판정은 **실기 스샷**이다(§16-⑮ ⓖ). 자동 검사로는 못 잰다 — 화면 프로브는 삭제됐고,
 *   있었더라도 실물 CSS를 모른다.
 */
const INPUT_FACE_STYLE = {
  background: "rgba(0,0,0,0.35)",
  color: "#ffffff",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "4px",
  padding: "6px 8px",
} as const;

/** 입력형 확인창의 최소 폭(lsfg dist:912 선례) — 비입력형에는 걸지 않는다(§4-D). */
function specWrapStyle(spec: ConfirmSpec) {
  return spec.kind === "input" ? { minWidth: "400px" } : undefined;
}

/**
 * `closeModal`을 **정확히 한 번만** 통과시키는 래퍼(D-05 ②).
 *
 * ★★ 왜 필요한가: 실물 `ConfirmModal`은 OK·취소 **각각의 경로에서 스스로** `closeModal`을
 *   부른다. 우리도 `fire`의 `finally`에서 닫아야 하므로(위 참조) 그대로 두면 같은 창에 대해
 *   닫기가 두 번 발화한다 — 그 사이에 다른 모달이 열려 있으면 **남의 창을 닫는** 자리다.
 *   빗장은 ref다: 같은 틱에 잠기고 재렌더에도 살아남는다.
 */
function useCloseOnce(closeModal?: () => void) {
  const closed = useRef(false);
  return useCallback(() => {
    if (closed.current) return;
    closed.current = true;
    closeModal?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closeModal]);
}

/**
 * 중첩 확인창의 **비활성 OK 라벨 면**(F-2 ①, 10판) — 폴백의 `overlayButtonStyle`과 같은 값이다.
 *
 * ★ 두 렌더러가 같은 것을 그린다는 §4-C 계약은 **잠긴 모습**에도 적용된다. 다만 같게 만드는
 *   것은 *적어 넣는 숫자*가 아니라 **화면에 나오는 값**이다 — 아래 산술이 그 차이다.
 *
 * ★★ 왜 0.25인가(실측 유도): Steam의 `Disabled` 클래스가 **버튼 전체에 `opacity:0.4`를 곱한다.**
 *   그래서 1차 시도의 `0.10` 면은 화면에서 `0.10 × 0.4 = 0.04` 상당으로 눌렸고, 실기 대비는
 *   Δ10.28 — 여전히 면으로 식별되지 않았다(합성 검산 일치 확인). 곱해질 것을 알고 **미리
 *   나눠 둔다**: `0.25 × 0.4 = 0.10` 유효.
 * ★ 폴백(`overlayButtonStyle`)도 **같은 0.25**를 쓴다. 두 렌더러가 같은 것을 그리려면 **적어
 *   넣는 숫자가 아니라 화면에 나오는 값**이 같아야 하는데, 폴백 버튼 역시 `DialogButton`의
 *   `disabled`라 같은 `Disabled` dimming이 걸린다 — 그러니 같은 숫자가 곧 같은 유효값이다.
 *   ⚠️ **이건 가정이다**: 폴백 경로는 `showModal`이 죽었을 때만 진입하므로 실기에서 재현해
 *     재보지 못했다(중첩 쪽 ×0.4만 실측). 같은 컴포넌트·같은 prop이라는 근거뿐이고, 만약
 *     폴백에 dimming이 없다면 그쪽이 두 배 밝게 보인다 — 확인되면 폴백만 0.10으로 되돌린다.
 * ⚠️ 여기엔 `opacity`를 걸지 않는다 — Steam이 이미 흐리게 그린다(실기 Δ10.5는 *너무 흐린*
 *   것이 아니라 **면이 없는** 것이 문제였다). 우리가 또 흐리게 하면 이중으로 죽는다.
 */
const OK_DISABLED_FACE_STYLE = {
  display: "inline-block",
  background: "rgba(255,255,255,0.25)",
  padding: "2px 10px",
  borderRadius: "4px",
} as const;

/**
 * 중첩 모드의 OK 라벨 — **비활성일 때만** 면을 가진 span으로 감싼다.
 *
 * ★★ 실기에서 type-to-confirm 미완 상태의 [전체 초기화]가 배경 대비 **Δ10.5**로 면이 식별되지
 *   않았다(옆 [취소]는 면이 있다). 버튼이 "잠겨 있다"가 아니라 **"죽은 텍스트"**로 읽힌다.
 *   버튼 자체는 Steam `ConfirmModal` 내부라 우리 손이 닿지 않지만, **라벨 자리는 우리 것**이다 —
 *   `strOKButtonText`가 `ReactNode`를 받는다(`Modal.ts:78` 실측). 그 자리에 면을 그린다.
 * ★ 활성일 때는 **문자열 그대로** 돌려준다: 평소 모습을 바꾸지 않는다는 것이 이 수정의 조건이다.
 *   활성 경로의 DOM은 이 함수가 없을 때와 한 글자도 다르지 않다.
 * ⚠️ 이것은 **실험**이다 — 면이 라벨 자리에만 생기므로 버튼 전체 면과는 다르게 보일 수 있다.
 *   판정은 실기 스샷(§16-⑮ ⓗ)이고, 불충분으로 판명되면 "중첩 모드 비활성 Primary 시각은
 *   Steam 소유"로 §15-D에 알려진 한계 1행을 등재하고 종결한다(개정안 F-2).
 */
function okFace(label: string, disabled: boolean): ReactNode {
  return disabled ? <span style={OK_DISABLED_FACE_STYLE}>{label}</span> : label;
}

/**
 * 확인창의 **기본 포커스를 [취소]로** 옮긴다(D2 — 2026-08-15 실기).
 *
 * ★★ 왜 필요한가: 손실 가능한 행동은 **인지시키고 묻는다**는 것이 확인창의 존재 이유인데,
 *   파괴적 버튼(OK) 위에 커서가 서 있으면 A 한 번의 관성으로 승인된다 — 그건 **물은 것이
 *   아니다.** 실측(2026-08-15): 푸터는 `DialogBody > DialogFooter > DialogTwoColLayout >
 *   [OK, 취소]`이고 두 버튼 다 `tabindex`·`autofocus`가 없어 **문서 순서로 첫 번째(OK)**가
 *   `gpfocus`를 가져간다("Primary라서"가 아니다).
 * ★★ 왜 DOM `.focus()`인가: `@decky/ui`의 `ConfirmModalProps`에 **초기 포커스를 넘길 prop이
 *   없고** 버튼 순서도 Steam 소유다. 라이브 실측에서 취소 버튼에 `.focus()`를 부르니
 *   `gpfocus`가 따라 옮겨졌다 — Steam 내비게이션이 DOM 포커스를 따른다.
 * ★★ 찾는 방법이 **라벨**인 이유: "마지막 버튼" 같은 위치 가정은 Steam이 순서를 바꾸는 날
 *   조용히 틀린다. 라벨은 **우리가 준 값**이라 우리가 아는 유일하게 확실한 표지다.
 *   못 찾으면 **아무것도 하지 않는다**(무해 폴백 — 지금 동작 그대로).
 * ★ 앵커는 본문 ref에서 올라간 `[role=dialog]`다. `document`에서 훑으면 뒤에 깔린 팝업의
 *   같은 라벨을 집을 수 있다 — 우리 창 안에서만 찾는다.
 * ★ rAF 한 프레임 미루는 이유: Steam의 `DeferredFocus`가 마운트 뒤 **1ms 타이머**로 자기
 *   포커스를 실행한다(`chunk~2dcc5aaf7.js`의 `RequestFocus` → `Schedule(1, …)` 실측).
 *   `useEffect`에서 곧바로 부르면 그 뒤에 덮여 없던 일이 된다.
 *
 * ⚠️ **입력형(`kind:"input"`)은 대상이 아니다**: 그 창의 초기 포커스는 `TextField`의
 *   `focusOnMount`가 가져가야 빅픽처 가상 키보드가 뜬다(U20 ①). 게다가 입력형은 OK가
 *   입력이 맞을 때까지 **비활성**이라 관성 승인이 원리적으로 불가능하다 — 이 수정이 막으려는
 *   위험이 없는 자리에서 유일한 입력 경로를 빼앗을 이유가 없다.
 * ⚠️ `noCancel`(결과 팝업)은 취소가 아예 없다 — 버튼 하나뿐이라 지금도 옳다.
 */
function useCancelFirstFocus(spec: ConfirmSpec) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const label = (spec.cancelText ?? t("CANCEL")).trim();
  const skip = !!spec.noCancel || spec.kind === "input";
  useEffect(() => {
    if (skip) return undefined;
    const frame = requestAnimationFrame(() => {
      const dialog = bodyRef.current?.closest("[role=dialog]");
      if (!dialog) return;
      const buttons = Array.from(dialog.querySelectorAll<HTMLElement>("button, .DialogButton"));
      buttons.find((el) => (el.textContent ?? "").trim() === label)?.focus();
    });
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return bodyRef;
}

/**
 * **중첩 렌더러** — `showModal`로 팝업 위에 `ConfirmModal`을 띄운다(lsfg dist:1647 선례).
 *
 * ★ `closeModal`은 `showModal`이 최상위에 주입한 것이다(D-05 ①) — **1회 래퍼를 씌워**
 *   `ConfirmModal`에 넘기고, 우리 게이트도 같은 래퍼를 쓴다. 두 경로가 각자 닫아도 실제
 *   닫기는 한 번이다.
 */
export function SpecConfirmModal({
  spec,
  closeModal,
}: {
  spec: ConfirmSpec;
  closeModal?: () => void;
}) {
  const close = useCloseOnce(closeModal);
  const gate = useSpecGate(spec, close);
  /* ★ 본문 div가 **초기 포커스의 앵커**다(D2) — 여기서 위로 올라가 우리 창을 찾는다. */
  const bodyRef = useCancelFirstFocus(spec);
  return (
    <ConfirmModal
      strTitle={spec.title}
      strDescription={
        <div ref={bodyRef} style={specWrapStyle(spec)}>{specBody(spec, gate.value, gate.setValue)}</div>
      }
      strOKButtonText={okFace(spec.okText, gate.okDisabled)}
      strCancelButtonText={spec.cancelText ?? t("CANCEL")}
      /* 결과 팝업은 OK 하나다(§4-I ④) — Steam의 알림 다이얼로그 모드. */
      bAlertDialog={spec.noCancel}
      bOKDisabled={gate.okDisabled}
      /* 발화 뒤에는 취소도 잠근다 — OK와 취소가 **상호 배타**라는 계약을 화면에서도 지킨다. */
      bCancelDisabled={gate.done}
      closeModal={close}
      onOK={gate.onOK}
      onCancel={gate.onCancel}
    />
  );
}

/**
 * **폴백 렌더러** — 중첩이 실기에서 실패할 때 팝업 안에 그리는 같은 창.
 *
 * ★★ 격리는 **구조**로 한다(D-05 ⑤): 이 오버레이가 떠 있는 동안 원래 콘텐츠는 아예
 *   **렌더하지 않는다**(`usePopupGate().renderBody`). 숨김이나 포커스 차단 로직으로 막으면
 *   그 로직이 틀린 날 뒤 콘텐츠가 조작 가능해진다 — 갈 수 있는 경로 자체를 없앤다.
 */
/**
 * 폴백 확인창 푸터 버튼의 시각 — **비활성이어도 면을 유지한다**(F-2, 10판).
 *
 * ★★ 실기에서 type-to-confirm 미완 상태의 [전체 초기화]가 **면 없이 흐린 글자만**으로
 *   렌더됐다(옆 [취소]는 면이 있었다). 그러면 *"여기 버튼이 있고 지금은 잠겨 있다"*가 아니라
 *   **"죽은 텍스트"**로 읽힌다 — 사용자는 무엇을 하면 열리는지도 모른 채 지나간다.
 *   그래서 `disabled` 기본 스타일에 기대지 않고 **면을 우리가 그린다**.
 *
 * ★★ 값은 중첩(`OK_DISABLED_FACE_STYLE`)과 **같은 0.25**다 — 그쪽 주석의 산술이 정본이다.
 *   이 버튼도 `DialogButton disabled`라 Steam `Disabled`의 `×0.4`가 같이 걸린다고 보므로,
 *   같은 숫자가 곧 같은 유효값(0.10)이 된다. 두 렌더러의 **잠김 시각이 같아야 한다**는 것이
 *   §4-C 계약이고, 계약은 적힌 숫자가 아니라 화면에 나온 값으로 지켜진다.
 * ⚠️ `opacity`를 **걸지 않는다**: Steam이 이미 흐리게 그린다(실기 Δ10.5·Δ10.28은 *너무 흐린*
 *   것이 아니라 **면이 없는** 것이 문제였다). 우리가 또 흐리게 하면 이중으로 죽는다.
 * ⚠️ **미검증 가정**: 이 경로는 `showModal`이 죽었을 때만 그려져 실기에서 재현하지 못했다.
 *   폴백에 dimming이 없다면 여기만 두 배 밝게 보인다 — 그때는 이 값만 0.10으로 되돌린다.
 *   (§15-D 알려진 한계 등재 후보.)
 */
function overlayButtonStyle(disabled: boolean) {
  return disabled
    ? { minWidth: "120px", background: "rgba(255,255,255,0.25)" }
    : { minWidth: "120px" };
}

export function ConfirmOverlay({ spec, onClose }: { spec: ConfirmSpec; onClose: () => void }) {
  const gate = useSpecGate(spec, onClose);
  return (
    <Focusable onCancelButton={gate.onCancel} style={{ ...COLUMN_STYLE, ...specWrapStyle(spec) }}>
      <div style={{ fontSize: "18px", fontWeight: "bold" }}>{spec.title}</div>
      {specBody(spec, gate.value, gate.setValue)}
      {/* ★★ 이 두 버튼만 `DialogButton`을 **직접** 쓴다(§4-G 2항 ⓑ가 인정한 유일한 예외).
          사유: Steam `ConfirmModal`의 푸터는 `DialogTwoColLayout`이 `flex-grow:1`로 **반폭씩**
          나눠 갖는다(전역 `width:100%` 오염에 구조적으로 면역이라 손댈 이유도 없다).
          폴백이 여기서 `fit-content`로 접으면 **중첩 모드와 폴백 모드의 푸터 모양이 갈리고**,
          그러면 §4-C "두 렌더러가 같은 것을 그린다" 계약과 F-1이 자기모순에 빠진다.
          ⚠️ 이 예외는 **파일 단위로** 잠근다 — `build.sh` grep ⑤가 popup.tsx만 허용한다.
             파일 밖 예외 목록은 두지 않는다(목록을 두면 그 목록이 다음 라운드의 구멍이 된다). */}
      <Focusable {...ROW_FLOW} style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
        <DialogButton
          onClick={gate.onOK}
          disabled={gate.okDisabled}
          style={overlayButtonStyle(gate.okDisabled)}
        >
          {spec.okText}
        </DialogButton>
        {/* ★ 결과 팝업(§4-I ④)에는 취소가 **없다** — 숨기는 것이 아니라 그리지 않는다.
            중첩 렌더러의 `bAlertDialog`와 같은 결과를 폴백에서도 내야 §4-C 계약이 선다. */}
        {spec.noCancel ? null : (
          <DialogButton
            onClick={gate.onCancel}
            disabled={gate.done}
            style={overlayButtonStyle(gate.done)}
          >
            {spec.cancelText ?? t("CANCEL")}
          </DialogButton>
        )}
      </Focusable>
    </Focusable>
  );
}

/**
 * 팝업이 쓰는 확인 게이트 한 벌 — **게이트와 격리가 같이 온다.**
 *
 * ★ `renderBody`를 통해서만 본문을 그리게 해서, 폴백 모드에서 *"오버레이와 원 콘텐츠가 동시에
 *   떠 있는"* 상태를 **호출부가 만들 수 없게** 한다(구조로 예외를 없앤다).
 * ★ `showModal`이 죽는 경우(런타임에 undefined일 수 있다)는 **화면이 말한다** — 안전한 것과
 *   진단 가능한 것은 다른 요건이다(구 화면의 확인창 열기가 세운 문법 그대로).
 */
export function usePopupGate(): {
  gate: ConfirmGate;
  overlay: ConfirmSpec | null;
  renderBody: (children: ReactNode) => ReactNode;
} {
  const [overlay, setOverlay] = useState<ConfirmSpec | null>(null);

  const gate = useCallback<ConfirmGate>((spec, fail, onFail) => {
    if (NESTED_CONFIRM) {
      try {
        showModal(<SpecConfirmModal spec={spec} />);
      } catch (err) {
        console.error("[gfxprofile] confirm gate failed", err);
        // ★ 치환자가 있는 문구도 여기서 채워진다(R3) — `failText`가 두 형태의 단일 관문이다.
        onFail(failText(fail));
      }
      return;
    }
    setOverlay(spec);
  }, []);

  const renderBody = useCallback(
    (children: ReactNode) =>
      overlay ? <ConfirmOverlay spec={overlay} onClose={() => setOverlay(null)} /> : children,
    [overlay],
  );

  return { gate, overlay, renderBody };
}

// ── 데이터 로드·갱신 (§4-F) ──────────────────────────────────────────────────

/**
 * 팝업 하나가 마운트 시 부르는 **자기 조회 RPC** — 봉투를 그대로 돌려준다.
 *
 * ⚠️ *"화살표 타입(`() => Promise<…>`)을 한 줄에 쓰지 않는다"*는 관례의 **근거는 소멸했다**:
 *   그 요구를 하던 것은 `.tsx`에서 `>…<`를 JSX 텍스트로 오인하던 `qa/test_i18n_sets.py`의
 *   가시 문자열 정규식인데, 그 검사는 2026-08-15 UI 검사 계열 삭제에 함께 지워졌다.
 *   지금 한 줄 화살표 타입을 막는 것은 아무것도 없다. 그럼에도 이 **이름 붙은 호출 시그니처**는
 *   남긴다 — 여러 팝업이 같은 로더 모양을 참조하는 재사용 가능한 타입이라 그 자체로 값을 한다.
 */
export interface PopupLoader<T> {
  (): Promise<Env<T>>;
}

/**
 * 왕복 하나를 부르는 얇은 호출자.
 *
 * ★ 이름을 붙인 이유는 위 `PopupLoader`와 같다 — **재사용되는 호출 시그니처**라서다.
 *   원래 근거였던 "한 줄 화살표 타입이 검사에 오탐된다"는 그 검사(`test_i18n_sets`)가
 *   삭제돼 소멸했다. 지금 이 형태를 강제하는 검사는 없다.
 */
export interface PopupCall<R> {
  (): Promise<Env<R>>;
}

/**
 * 받은 봉투로 **화면 문구만** 정하는 자리(재조회·통지는 호출부의 일이 아니다).
 *
 * ★ `true`를 돌려주면 *"이번 결과를 **창으로** 말했다"*는 뜻이다(§4-I ⑥ 2겹 방지). 호출부는
 *   그 **사실만** 알린다 — 화면이 낡았는지의 판정은 여전히 문이 한다.
 */
export interface PopupResult<R> {
  (res: Env<R>): boolean | void;
}

/**
 * RPC 한 왕복을 감싸는 **문**(§4-F 개정). 호출부는 봉투를 받아 화면 문구만 정하고,
 * busy·재조회·변경 통지·예기치 못한 실패 문구는 전부 이 문이 맡는다.
 *
 * ⚠️ 인자를 줄줄이 한 줄에 쓰지 않는 이유는 `PopupLoader`와 같다(`.tsx`의 `>…<` 오탐).
 */
export interface PopupRunner {
  <R>(
    call: PopupCall<R>,
    failKey: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void>;
}

/**
 * **무쓰기가 보장된 응답**인가 — 토큰 발급(`CONFIRM_REQUIRED`)뿐이다(§4-F ③).
 *
 * ★★ 판정을 **응답**에 두는 것이 핵심이다. "미리보기 호출"·"확정 호출"은 프론트가 붙이는
 *   이름일 뿐이고, 같은 route가 토큰 유무에 따라 둘 다 된다(삭제·초기화·복원이 전부 그렇다).
 *   실제로 *"이번엔 아무것도 안 썼다"*를 아는 것은 백엔드가 보낸 이 코드 하나다.
 *   그 외 응답(성공·실패·거절·예외)은 **썼는지 모른다** — 모르면 다시 읽는다.
 */
function isTokenIssue(res: { ok: boolean; code?: string }): boolean {
  return !res.ok && res.code === "CONFIRM_REQUIRED";
}

/**
 * 왕복 하나 — `begin`/`end`를 **구조적으로** 짝짓는다(P15-E R8).
 *
 * ★★ `call()`이 **동기적으로 던져도** 여기서는 거절이 된다. 예전에는 `begin()` 뒤에
 *   `call().then(…).finally(end)`를 이어 붙였는데, `call`이 그 자리에서 던지면 `.finally`가
 *   **부착되기 전에** 스택을 빠져나가 `end`가 영영 안 돌았다 — busy가 영구히 잠겨 아무 버튼도
 *   안 듣는 팝업이다. 도달성(런타임에 RPC가 동기적으로 던지는가)은 미확정이지만, 가드를
 *   **문 하나**로 모으는 편이 예외 갈래를 세는 것보다 싸다.
 * ★ 동기 throw와 비동기 거절이 **같은 자리(`onSettle`의 err)**로 온다 — 두 갈래를 따로 두면
 *   한쪽만 고쳐지는 날이 온다.
 * ★ `end`는 `onSettle`보다 **뒤에** 돈다: 화면 문구가 정해지기 전에 문이 열리면, 그 틈에
 *   낡은 화면이 조작 가능해진다.
 */
function inDoor<R>(
  begin: () => void,
  end: () => void,
  call: PopupCall<R>,
  onSettle: (res: Env<R> | null, err: unknown) => void,
): Promise<void> {
  begin();
  // ★ 호출 자체는 **동기로** 나간다(마이크로태스크로 미루지 않는다) — 누른 그 자리에서 왕복이
  //   시작한다는 관측 가능한 순서를 바꾸지 않기 위해서다. 바꾸는 것은 **죽는 방식**뿐이다.
  let started: Promise<Env<R>>;
  try {
    started = call();
  } catch (err) {
    started = Promise.reject(err);
  }
  return started
    .then(
      (res) => { onSettle(res, null); },
      (err) => { onSettle(null, err); },
    )
    .finally(end);
}

/**
 * 문을 지나는 왕복이 **화면에 닿는 자리**. 소비자(팝업 3종·QAM)가 채운다.
 *
 * ★ 문구를 문이 정하지 않는 이유: 같은 실패라도 팝업은 note 한 줄이고 QAM은 상태박스의
 *   실패 슬롯(+받은 시각)이다. 공유해야 하는 것은 **규칙**(무엇을 언제 다시 읽는가)이지
 *   문장이 아니다.
 */
export interface DoorSink<T> {
  /**
   * **새 왕복이 시작됐다**(조회·변이 공용) — 화면이 들고 있는 *직전 왕복의 말*은 여기서 낡는다.
   *
   * ★★ 왜 문에 있는가(2026-08-15 QA R7): note를 **거두는 호출이 전 소스에 0건**이었다.
   *   GamesPopup의 성공은 대부분 침묵이라, 왕복이 한 번 죽어 *"예기치 못한 오류가
   *   발생했습니다"*가 뜨면 **다시 눌러 성공해도 그 문장이 목록 아래에 그대로 남는다** —
   *   사용자는 방금 성공한 동작을 실패로 읽는다. 거두는 자리를 호출부마다 두면 그중 하나를
   *   반드시 빠뜨리므로, *"새 동작이 시작되면 지난 동작의 말은 낡는다"*는 규칙을 **문 하나**에 둔다.
   * ★ `reload`는 이 신호를 내지 않는다: 변이 뒤 자동 재조회가 여기 걸리면, **방금 그 변이가
   *   남긴 말**(결과·실패 사유)을 스스로 지운다. 신호의 뜻은 *"사용자가 새 동작을 걸었다"*이지
   *   *"왕복이 나갔다"*가 아니다.
   * ★ 미지정이면 아무 일도 안 한다 — QAM처럼 「직전 결과 + 받은 시각」을 일부러 붙잡아 두는
   *   화면은 이 신호를 받지 않으면 지금 동작 그대로다.
   */
  onStart?: () => void;
  /** 최신 세대의 조회가 성공했다 — 봉투의 payload. */
  onData: (data: T) => void;
  /**
   * 조회가 실패했다 — **봉투가 왔고 `ok:false`인 경우뿐**이다. `code`는 그 봉투의 코드이므로
   * 소비자는 `tCode` 단일 관문에 그대로 실어도 된다.
   *
   * ★★ 예전에는 **왕복이 죽은 경우까지 이 문으로** 나갔다(`"UNEXPECTED"`를 코드 자리에 실어서).
   *   그러면 소비자의 `tCode(code, failKey)`가 등재된 그 키를 만나 **failKey를 통째로 버리고**
   *   "예기치 못한 오류"만 그린다 — *어느 화면이 못 읽혔는지*가 사라진다(QA DEFECT-03).
   *   감시자 문자열을 고르는 방식으로는 그 함정을 못 벗어나므로 **문을 갈랐다**(아래).
   */
  onLoadFail: (code: string) => void;
  /**
   * **조회 왕복이 죽었다**(봉투 자체가 없다) — 백엔드가 준 코드는 **존재하지 않는다.**
   *
   * ★ 그래서 이 문은 코드를 주지 않는다. 소비자가 그릴 수 있는 것은 *자기가 아는 실패 키*뿐이고
   *   (`tCode`에 넣을 재료가 애초에 없다), 진단 원문이 필요한 소비자를 위해 `err`만 온다.
   * ★ 변이 쪽 `onCallFail`과 **같은 대칭**이다: 봉투가 온 갈래와 왕복이 죽은 갈래는 서로 다른
   *   문으로 나간다. 소비자가 이 문을 안 채우면 **컴파일이 깨진다** — 다뤄야 할 갈래를 잊는
   *   경로가 없다.
   */
  onLoadDead: (err: unknown) => void;
  /**
   * 변이·조회 **왕복이 죽었다**(봉투가 없다) — 호출부가 준 failKey와 함께.
   * ★ 여기 오는 것은 **화면이 직접 건 호출**(`runMutation`·`runQuery`)이다. 문이 스스로 도는
   *   `reload`의 죽음은 위 `onLoadDead`로 나간다 — 그쪽은 호출부가 준 키가 없다.
   */
  onCallFail: (key: StringKey, err: unknown) => void;
  /**
   * **변이는 성공했는데 뒤따르는 재조회가 실패했다**(§4-I ⑥ — 성공 침묵의 유일한 예외).
   *
   * ★★ 이 갈래에서 화면은 옛 상태를 그대로 보여준다 — 마커가 안 움직이므로 사용자 눈에는
   *   *"눌렀는데 아무 일도 안 일어난"* 먹통이다. **무반응은 곧 고장으로 읽힌다**(A12).
   *   그래서 성공 침묵의 예외로 여기서만 말한다.
   * ★ **판정은 이 문 하나**가 한다: 두 사실(변이 성공 여부·그 뒤 재조회 결과)을 다 아는 자리가
   *   여기뿐이다. 호출부가 각자 판단하면 팝업마다 조건이 갈린다.
   * ★ 미지정이면 아무 일도 안 한다 — 둘째 줄 note는 그대로 뜬다(자리가 다르다).
   */
  onStaleAfterWrite?: () => void;
}

/** 문이 돌려주는 것 — 상태 표시 2종과 호출 3종. */
export interface DataDoor {
  /** 왕복이 하나라도 진행 중인가(조회·변이 공용). */
  busy: boolean;
  /** **쓸 수 있는 왕복**이 진행 중인가 — "적용 중"처럼 조회와 갈라 말해야 하는 화면이 쓴다. */
  mutating: boolean;
  /** 다시 읽는다. 인자는 **문 내부용**이다(§4-I ⑥) — 화면이 부를 때는 인자 없이 부른다. */
  reload: (afterWrite?: boolean) => void;
  /** **확정 실행**(쓸 수 있는 호출). 응답이 토큰 발급이 아니면 재조회 + 변경 통지가 따라온다. */
  runMutation: PopupRunner;
  /** **조회**(읽기 전용 호출). busy만 같이 쓰고 재조회·통지는 하지 않는다. */
  runQuery: PopupRunner;
}

/**
 * 조회·변이가 지나는 **문 하나**(§4-F 개정) — 세 보증이 여기 한 곳에 있다.
 *
 *   ① **세대 가드**: 재조회는 겹칠 수 있고(연타·변이 뒤 자동 재조회), 먼저 나간 응답이 나중에
 *      도착하면 **낡은 값이 새 값을 덮는다.** 응답마다 자기 세대를 들고 와서 최신 세대만
 *      반영한다 — 빗장은 **상태가 아니라 ref**다(P12 `useCloseOnce`의 교훈: 상태로 막으면
 *      재렌더 전에 도착한 두 번째가 낡은 값을 보고 그대로 통과한다).
 *   ② **busy 문 하나**: 조회도 변이도 이 문을 지나므로 여기서만 켜고 끈다. 예전에는
 *      `reload()`가 busy를 안 켜서 [다시 검색] 연타가 **조회에는 무방비**였다(P14 O1).
 *      왕복이 겹칠 수 있으니 불리언이 아니라 **진행 수**로 센다.
 *   ③ **확정 실행은 성공·실패를 가리지 않고 다시 읽는다**: 엔진은 **쓴 뒤에** 거부할 수 있어
 *      (체크인·부분 삭제) *"실패했는데 디스크는 바뀐"* 상태가 실재한다. 무쓰기가 보장된 응답은
 *      `CONFIRM_REQUIRED` 하나뿐이다.
 *
 * ★★ **왜 훅에서 한 겹 더 갈랐는가**(P15-E): 팝업 3종은 `usePopupData`로 이 문을 상속받는데
 *   **QAM은 네 번째 소비자**이면서 자기 조회·변이를 손으로 배선하고 있었다 — 그래서 세 보증이
 *   QAM에만 없었고, 낡은 응답이 카운트를 되돌리고 실패 봉투가 침묵했다(P15-E R1·R2).
 *   QAM은 화면 표현(상태박스·시각·승계)이 팝업과 다르므로 `usePopupData`를 통째로 쓸 수 없다 —
 *   **화면 처리는 sink로 내주고 규칙만 공유한다.** 규칙이 한 곳이면 소비자가 늘어도 상속된다.
 */
export function useDataDoor<T>(
  load: PopupLoader<T>,
  sink: DoorSink<T>,
  /** 변이 통지 — 확정 실행이 끝나면 이 문이 부른다(소비자가 각자 부르지 않는다). */
  onMutate?: () => void,
): DataDoor {
  const [busy, setBusy] = useState(false);
  const [mutating, setMutating] = useState(false);
  /** 진행 중인 왕복 수(조회·변이 공용) / 그중 쓸 수 있는 것의 수. */
  const inFlight = useRef(0);
  const writes = useRef(0);
  /** 조회 세대 — `reload`마다 오르고, 그보다 낡은 응답은 버린다. */
  const generation = useRef(0);
  /**
   * 통지·화면 처리는 **ref로** 든다 — 그래야 아래 문들이 **언제 만들어졌든 같게 동작**한다.
   * (문을 매 렌더 새로 만들면서 prop을 클로저로 잡으면, 확인창 안에 갇힌 옛 문이 옛 통지를
   * 부르게 된다. 호출부가 deps를 정확히 적어야만 옳은 구조는 언젠가 틀린다.)
   */
  const notify = useRef(onMutate);
  notify.current = onMutate;
  const to = useRef(sink);
  to.current = sink;

  const begin = useCallback((writing: boolean) => {
    inFlight.current += 1;
    setBusy(true);
    if (!writing) return;
    writes.current += 1;
    setMutating(true);
  }, []);

  const end = useCallback((writing: boolean) => {
    inFlight.current -= 1;
    if (inFlight.current <= 0) {
      inFlight.current = 0;
      setBusy(false);
    }
    if (!writing) return;
    writes.current -= 1;
    if (writes.current <= 0) {
      writes.current = 0;
      setMutating(false);
    }
  }, []);

  /**
   * 다시 읽는다. `afterWrite`는 **성공한 변이가 부른 재조회**라는 표시다(§4-I ⑥) —
   * 그 재조회가 실패하면 화면이 결과를 못 보이므로 문이 그 사실을 알린다.
   * ⚠️ 세대 가드에 걸린(=더 새 조회가 이미 나간) 응답은 알리지 않는다: 화면이 낡았는지는
   *   **최신 조회**가 정한다.
   */
  const reload = useCallback((afterWrite?: boolean) => {
    generation.current += 1;
    const mine = generation.current;
    return inDoor(() => begin(false), () => end(false), load, (res, err) => {
      // 옛 응답은 **없던 일**이다 — 화면은 이미 더 새 것을 알고 있다.
      if (mine !== generation.current) return;
      if (!res) {
        to.current.onLoadDead(err);
        if (afterWrite) to.current.onStaleAfterWrite?.();
        return;
      }
      if (!res.ok) {
        to.current.onLoadFail(res.code);
        if (afterWrite) to.current.onStaleAfterWrite?.();
        return;
      }
      to.current.onData(res.data);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, begin, end]);

  /**
   * 두 문이 공유하는 한 벌 — `mutating`만 다르다.
   *
   * ★ note는 **즉시** 뜬다(§4-F ④): 재조회 응답을 기다리지 않는다. 순서를 기다릴 이유였던
   *   *"낡은 데이터가 새 note와 어긋난다"*는 세대 가드가 구조적으로 막는다.
   */
  function runWith<R>(
    writing: boolean,
    call: PopupCall<R>,
    key: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void> {
    // ★ 지난 왕복의 말은 여기서 낡는다(R7) — **시작할 때** 거둔다. 정착 뒤에 거두면 이번
    //   왕복이 방금 적은 말까지 같이 지운다.
    to.current.onStart?.();
    return inDoor(() => begin(writing), () => end(writing), call, (res, err) => {
      // ★ **성공한 변이**만 §4-I ⑥의 대상이다: 실패는 이미 사유를 말했고, 왕복이 죽은 경우는
      //   무엇이 쓰였는지조차 모른다 — 거기에 "동작은 끝났습니다"를 얹으면 거짓이 된다.
      let wroteOk = false;
      // ★★ **§4-I ⑥은 「성공 침묵」의 예외다.** 이번 왕복이 이미 창으로 결과를 말했다면 화면은
      //   침묵하지 않았고, 사용자는 무슨 일이 있었는지 이미 읽었다 — 그 위에 창을 하나 더 얹으면
      //   중첩 깊이 ≤1 불변식만 깨고 새로 알려 주는 것은 없다. 그때 「화면이 낡았다」는
      //   **둘째 줄 note**가 계속 말한다(자리가 다르고, 창이 닫혀도 남는다 — ⑥의 마지막 조항).
      let spoken = false;
      if (res) {
        spoken = onResult(res) === true;
        if (!writing || isTokenIssue(res)) return;
        wroteOk = res.ok;
      } else {
        to.current.onCallFail(key, err);
        if (!writing) return;
      }
      reload(wroteOk && !spoken);
      notify.current?.();
    });
  }

  function runMutation<R>(
    call: PopupCall<R>,
    key: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void> {
    return runWith(true, call, key, onResult);
  }

  function runQuery<R>(
    call: PopupCall<R>,
    key: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void> {
    return runWith(false, call, key, onResult);
  }

  return { busy, mutating, reload, runMutation, runQuery };
}

/**
 * 팝업 하나의 데이터 수명 — **마운트 시 자기 RPC**를 부르고, 변이 뒤 **자기가 다시 조회**한다.
 * 규칙은 전부 `useDataDoor`가 들고, 여기는 **팝업의 화면 처리**(데이터·note)만 얹는다.
 *
 * ★★ `profile_names` 선반영(R-6): 봉투에 그 필드가 있으면 **상태 반영보다 먼저** i18n에
 *   태운다. 소비자마다 손으로 챙기던 시절에 한 곳이 빠져 *"초기화 뒤에도 옛 표시명이 남는"*
 *   사고가 났다(2026-08-10 QA R3) — 여기서 **구조적으로** 태우면 빠뜨릴 자리가 없다.
 * ★★ 왜 팝업이 자기 재조회를 하는가(§4-F): QAM `Content`는 팝업이 떠 있는 동안 언마운트일 수
 *   있어 `onMutate`만으로는 **열려 있는 팝업 화면이 낡는다.** 통지(onMutate)와 자기 갱신은
 *   다른 일이다.
 *
 * ★★ **note는 두 줄이다**(P15-E R4): 동작이 남긴 말(`setNote`)과 **재조회 실패**는 서로 다른
 *   사실이고 **둘 다 참일 수 있다** — 복원은 성공했는데 목록을 다시 못 읽은 상태가 그렇다.
 *   예전에는 재조회 실패가 같은 자리를 덮어써서 *"되돌렸습니다 — 계속 쓰려면 저장하십시오"*
 *   같은 **후속 조치 안내가 통째로 사라졌다.** 자리를 갈라 두면 덮어쓸 수가 없다.
 */
export function usePopupData<T>(
  load: PopupLoader<T>,
  failKey: StringKey,
  /** 변이 통지 — 확정 실행이 끝나면 이 훅이 부른다(팝업이 각자 부르지 않는다). */
  onMutate?: () => void,
  /**
   * **성공했는데 화면이 못 따라온 경우**에 부른다(§4-I ⑥). 판정은 문이 하고, **그리는 것은
   * 팝업의 일**이다 — 이 훅은 확인 게이트를 모른다(알면 두 훅이 서로를 붙잡는다).
   */
  onStaleAfterWrite?: () => void,
): {
  data: T | null;
  /**
   * 화면이 지금 **무언가 말하고 있는가**를 판정할 때 쓰는 값(동작 note가 있으면 그것,
   * 없으면 재조회 실패 사유). 그리는 것은 `noteView`가 한다.
   */
  noteText: string | null;
  setNote: (v: string | null) => void;
  /**
   * **뒤따르는 재조회**의 결과를 쓰는 자리(둘째 줄) — 실패면 사유, 성공이면 `null`.
   *
   * ★ 팝업이 자기 하위 목록을 다시 읽는 경우(복원 뒤 백업 목록)가 이 자리다. 그 실패를
   *   `setNote`로 쓰면 **방금 한 동작의 결과와 후속 조치 안내를 덮는다** — 훅의 재조회가
   *   덮던 것과 같은 사고이고, 같은 해소(자리를 가른다)를 쓴다.
   */
  setReloadNote: (v: string | null) => void;
  /** note 자리 — **두 줄을 함께** 그린다. 팝업이 한 줄만 그릴 방법을 두지 않는다. */
  noteView: ReactNode;
  busy: boolean;
  reload: () => void;
  runMutation: PopupRunner;
  runQuery: PopupRunner;
} {
  const [data, setData] = useState<T | null>(null);
  const [note, setNote] = useState<string | null>(null);
  /** **재조회**만 쓰는 자리 — 동작 note를 덮지 않는다(둘째 줄). */
  const [loadNote, setLoadNoteState] = useState<string | null>(null);
  /**
   * 지금 둘째 줄에 있는 말이 **이 훅의 재조회**에서 온 것인가.
   *
   * ★ 팝업이 스스로 부르는 뒤따르는 재조회(예: 복원 뒤 백업 목록 다시 읽기)도 같은 줄을 쓴다.
   *   그때까지 훅의 조회 성공이 그 줄을 거두면, *"백업 목록은 여전히 못 읽었다"*는 사실이
   *   **무관한 조회 하나가 성공했다는 이유로** 사라진다. 출처를 함께 들어 자기 것만 거둔다.
   */
  const ownLoadNote = useRef(false);
  const stale = useRef(onStaleAfterWrite);
  stale.current = onStaleAfterWrite;

  const setReloadNote = useCallback((value: string | null) => {
    ownLoadNote.current = false;
    setLoadNoteState(value);
  }, []);

  /** 둘째 줄에 **이 훅의 조회**가 쓴다는 표시까지 함께 — 위 `setReloadNote`의 대칭이다.
   *  ★ 조회 실패의 두 갈래(봉투 / 왕복 사망)가 같은 줄을 쓰므로, 출처 표시와 쓰기를 한 문에
   *    묶어 둔다. 갈래가 늘 때 한쪽만 표시를 빠뜨리는 경로를 만들지 않는다. */
  const setOwnLoadNote = useCallback((value: string) => {
    ownLoadNote.current = true;
    setLoadNoteState(value);
  }, []);

  const door = useDataDoor<T>(
    load,
    {
      // ★ **동작 note는 직전 왕복의 말이다**(R7) — 새 동작이 걸리면 그 말은 낡는다.
      //   둘째 줄(`loadNote`)은 여기서 손대지 않는다: 그쪽은 *"화면이 낡았다"*는 다른 사실이고
      //   자기 출처(`ownLoadNote`)를 보고 스스로 거둔다.
      onStart: () => setNote(null),
      onData: (payload) => {
        // ★ 상태 반영보다 **먼저** — 아래 setData로 다시 그려질 때 이미 새 이름이어야 한다.
        const named = payload as { profile_names?: { dock?: string; internal?: string } };
        if (named && named.profile_names) setProfileNames(named.profile_names);
        setData(payload);
        if (ownLoadNote.current) setLoadNoteState(null);
      },
      // 봉투가 준 코드다 — `tCode` 단일 관문이 맞는 자리다.
      onLoadFail: (code) => setOwnLoadNote(tCode(code, failKey)),
      // ★ 왕복이 죽었다 = **백엔드 코드가 없다.** `"UNEXPECTED"`는 화면이 붙이는 꼬리표이므로
      //   `tCode`가 아니라 `t(failKey, …)`다 — 아래 `onCallFail`과 같은 처분이고, 그래야
      //   *어느 화면이 못 읽혔는지*가 남는다(QA DEFECT-03).
      onLoadDead: () => setOwnLoadNote(t(failKey, { code: "UNEXPECTED" })),
      // ★ **`tCode`를 쓰면 안 되는 자리다**(QA DEFECT-03): `tCode(code, fallback)`은
      //   `code in en ? t(code) : t(fallback, {code})`이고 `"UNEXPECTED"`는 **등재된 키**라
      //   `key`가 **항상 버려진다.** 그러면 저장이 죽었는지 삭제가 죽었는지 화면이 말하지
      //   못하고, 위 인터페이스의 *"호출부가 준 failKey와 함께"*가 거짓이 된다
      //   (`runMutation(call, "SAVE_FAILED", …)`의 둘째 인자가 이 갈래에서 전부 사문이었다).
      //   ⚠️ 위 `onLoadFail`은 **봉투가 온 경로뿐**이라 `code`가 진짜 백엔드 코드다 — 그쪽은
      //     `tCode`가 맞다.
      //   ⚠️⚠️ 예전 이 자리의 경고는 그 한정어 없이 *"onLoadFail은 백엔드 코드라 tCode가 맞다"*
      //     라고만 적어 **왕복이 죽은 경로까지 그 문으로 나가던 사실을 가렸고**, 뒤에 "같이
      //     고치지 말 것"까지 붙어 **틀린 전제가 수정을 막았다.** 그 경로는 이제 `onLoadDead`라는
      //     다른 문이다 — 세 줄은 이제 모양부터 다르다.
      onCallFail: (key) => setNote(t(key, { code: "UNEXPECTED" })),
      // ★ ref로 최신 것을 부른다 — 이 훅이 만들어질 때의 클로저를 잡으면 확인창 안에 갇힌
      //   옛 콜백이 불린다(문이 `notify`를 ref로 드는 것과 같은 이유).
      onStaleAfterWrite: () => stale.current?.(),
    },
    onMutate,
  );

  useEffect(() => {
    door.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    data,
    noteText: note ?? loadNote,
    setNote,
    setReloadNote,
    noteView: <PopupNotes note={note} loadNote={loadNote} />,
    busy: door.busy,
    reload: door.reload,
    runMutation: door.runMutation,
    runQuery: door.runQuery,
  };
}

/**
 * 팝업 하단 note **자리** — 없는 줄은 자리도 만들지 않는다(기존 "0이면 안 그림" 문법).
 *
 * ★ 내보내지 않는다(P15-E R4): 밖에서 그릴 수 있으면 재조회 실패 줄을 빠뜨린 자리가 언젠가
 *   생긴다. 그리는 방법은 `usePopupData().noteView` 하나뿐이다 — 문이 하나면 빠질 자리가 없다.
 */
function PopupNotes({ note, loadNote }: { note: string | null; loadNote: string | null }) {
  return (
    <>
      {note ? <div style={NOTE_STYLE}>{note}</div> : null}
      {loadNote ? <div style={SUB_NOTE_STYLE}>{loadNote}</div> : null}
    </>
  );
}
