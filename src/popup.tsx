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
 * 팝업 공통 기반 — 팝업 G·D·S가 공유하는 골격·뷰·확인 게이트·데이터 로드.
 * 각자 ModalRoot를 조립하면 경계 배치·닫기 배선·확인창 생명주기가 세 벌이 되고, 그중
 * 하나가 틀리면 그 화면만 조용히 다르게 동작한다. 여기서 한 번 맞추고 나머지는 내용만 채운다.
 *
 * 소비 화면은 넷 — 팝업 G·D·S와 QAM(`index.tsx`). QAM도 `useDataDoor`,
 * `SpecConfirmModal`과 공용 스타일을 직접 공유한다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const NOTE_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
/**
 * 동작 note 아래 보조 줄(재조회 실패). 한 단계 작은 글자라 "방금 한 일"과
 * "화면이 낡았을 수 있다"가 시각적으로 갈린다.
 */
const SUB_NOTE_STYLE = { fontSize: "11px", color: "#9aa0a6", wordBreak: "keep-all" } as const;

/** 아이콘이 제목과 같은 줄에 설 때의 자리. 색은 주변을 따라간다(아이콘은 currentColor다). */
const HEADER_ICON_STYLE = { display: "inline-flex", marginRight: "6px", verticalAlign: "-0.1em" } as const;

/**
 * 버튼 라벨 앞 아이콘 자리. 고정 폭이라 아이콘 유무로 버튼 폭이 흔들리지 않는다.
 * 관용구는 `<span style={ICON_SLOT_STYLE}><Icon/></span>{label}` 하나로 통일한다.
 * `ButtonItem.icon`은 버튼 내용이 아니라 Field 라벨 슬롯이라 이 용도에 쓰지 않는다.
 * 소비자는 팝업 3종·`index.tsx`·`BulkApplyButton.tsx`다.
 *
 * `verticalAlign`은 반드시 유지한다. 기본 baseline에서는 아이콘이 글자보다 위로 떠,
 * Steam 실기 rect에 맞춰 `-0.125em`만큼 내린 값이다. `middle`은 같은 실측에서 반대 방향
 * 오차를 냈다 — 관측 당시 Steam 빌드의 실기 결과이며 현행 런타임은 코드만으로 확인할 수 없다.
 * 폰트나 버튼 조판이 바뀌면 산식 추정이 아니라 QAM과 팝업 양쪽 rect로 다시 잰다.
 */
export const ICON_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginRight: "4px",
  verticalAlign: "-0.125em",
} as const;

/**
 * 한국어 낱말 보존(`word-break: keep-all`) — `ButtonItem`의 `description` 슬롯 전용.
 * CSS 기본 줄바꿈은 한국어를 글자 단위로 끊어, 좁은 잔글씨 컨테이너에서 낱말 한가운데가
 * 갈린다. `keep-all`은 낱말 경계에서만 끊게 하고, 그 자리를 쓰는 모든 한국어 문장이 함께 고쳐진다.
 * `description`은 style을 안 받는 prop이라 span이 유일 통로:
 * `<ButtonItem description={<span style={KEEP_ALL_STYLE}>{…}</span>}>`.
 * 소비자는 둘 — `index.tsx`(진입 버튼)·`BulkApplyButton`(사유 줄).
 *
 * 경로·파일명 슬롯에는 걸지 않는다(`PATH_BREAK_STYLE`이 맡는다). 끊을 낱말 경계가 없는
 * 문자열이라 넘칠 수 있고, `word-break`는 상속 속성이라 그쪽은 `normal`로 조상 값을 되돌린다.
 */
export const KEEP_ALL_STYLE = { wordBreak: "keep-all" } as const;

/**
 * 경로·파일명을 그리는 자리의 줄바꿈 규칙 — 잔글씨 스타일에 얹어 쓴다.
 * 규칙만 상수로 빼는 이유: 소비자마다 글자 크기가 달라(팝업 11px·확인창 12px) 스타일을
 * 통째 공유하면 크기까지 억지로 맞춰야 한다. 갈리면 안 되는 것은 줄바꿈 규칙 하나다.
 * `wordBreak:"normal"` — `word-break`는 상속 속성이라 조상의 `keep-all`이 여기까지 내려온다.
 *   경로엔 낱말 경계가 없어 그러면 줄이 통째로 넘친다.
 * `overflowWrap:"anywhere"` — `normal`만으로는 "넘칠 때 아무 데서나 끊어도 된다"는 허가가
 *   없어, 공백·하이픈이 없는 경로가 팝업을 넘어 화면 밖까지 밀린다. `anywhere`는 넘칠 때만
 *   끊으므로 짧은 경로의 모습은 그대로다. `break-all`이 아닌 이유는 그쪽은 안 넘쳐도 끊기
 *   때문. `break-word`보다 나은 점은 min-content 폭까지 줄여 부모 flex/모달이 경로 길이에
 *   끌려 넓어지는 것을 막는다는 것 — 크기를 지정하지 않는 이 화면에서 그 차이가 곧
 *   "화면 밖으로 나가는가"를 가른다.
 */
export const PATH_BREAK_STYLE = { wordBreak: "normal", overflowWrap: "anywhere" } as const;

// ── 골격 ──────────────────────────────────────────────────────────────

/**
 * 중앙 팝업 하나. 크기를 지정하지 않는다(`popupWidth`/`popupHeight`/`bAllowFullSize` 금지).
 *
 * `ErrorBoundary`는 `DialogBody` 안쪽이다. `showModal`이 최상위 엘리먼트에 주입한
 * `closeModal`이 `GfxPopup`을 거쳐 `ModalRoot`까지 도달해야 하므로, 최상위를 경계로 감싸지 않는다.
 * 이 경계가 보호하는 범위는 `DialogBody`의 콘텐츠다. `ModalRoot`·`DialogBody` 자체의 렌더
 * 실패는 이 경계 밖이며, 호출부의 동기 try/catch가 그 실패까지 받는다고 가정하지 않는다.
 *
 * `onCancel`은 ModalRoot의 B 처리 통로로 열어 두지만 현재 소비자는 주지 않는다.
 * 비목록 뷰의 B 처리는 `PopupSubView`의 `Focusable.onCancelButton`이 맡는다.
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

// ── 버튼 ──────────────────────────────────────────────────────────────

/**
 * 팝업의 일반 콘텐츠 버튼은 이 래퍼로 그린다. 예외는 `ConfirmOverlay` 푸터의 두 버튼뿐이다.
 * Steam 실측에서 전역 `button.DialogButton { width:100% }`가 flex 자식에도 적용돼 목록 버튼이
 * 부풀고 옆 콘텐츠가 붕괴했다 — 관측 당시 Steam 빌드의 실기 결과이며 현행 런타임은 코드만으로
 * 확인할 수 없다. 새 버튼마다 같은 폭 보정을 빠뜨리지 않도록 래퍼와
 * `build.sh`의 파일 단위 검사로 사용 지점을 모은다.
 *
 * `fit-content`는 호출부 style 뒤에 병합한다. 그래야 호출부의 우발적인 width도 이 관문에서
 * 덮인다. 일반 호출부는 width를 지정하지 않는다.
 * 폭은 Steam 스타일시트가 있는 실기 CDP 조회나 스크린샷으로 판정한다.
 *
 * 타입은 `ComponentProps<typeof DialogButton>`을 쓴다. `DialogButtonProps`를
 * `@decky/ui`에서 직접 import하면 단일 import 관문을 어기고 `deckyui.ts`도 재수출하지 않는다.
 * ref는 투과하지 않는다. 필요해질 때 `forwardRef`로 확장한다.
 */
export function PopupButton({ style, children, ...props }: ComponentProps<typeof DialogButton>) {
  return <DialogButton {...props} style={{ ...style, width: "fit-content" }}>{children}</DialogButton>;
}

/**
 * 세로 스택 동작 버튼의 자리 — 설명 줄을 아래에 거느리는 버튼이다.
 * 좌측 정렬: 버튼 글자가 가운데, 아래 설명이 왼쪽이면 축이 어긋나고, `fit-content`로 폭이
 *   접히면 그 어긋남이 더 커진다.
 * 가로 행 버튼(이름 바꾸기·[다시 검색]·[모두 추가]·목록 행)은 대상이 아니다 — 행 안에서
 *   제 폭만 접으면 된다.
 */
export const STACKED_BUTTON_STYLE = {
  alignSelf: "flex-start", textAlign: "left", justifyContent: "flex-start",
} as const;

/**
 * 세로 스택 버튼의 설명 줄 들여쓰기 — 버튼의 가로 패딩과 같은 값이라 라벨과 설명이
 * 정렬 축을 공유한다. 값이 두 곳에 살면 한쪽만 고치는 날 축이 다시 갈린다.
 */
export const STACKED_DESC_PAD = "10px";

// ── 내부 뷰 ───────────────────────────────────────────────────────────

/** 팝업 G의 뷰. 깊이 최대 2, 부모가 정적이라 뒤로가기 대상이 분기하지 않는다. */
export type GView =
  | { kind: "list" }
  | { kind: "detail"; appid: string }
  | { kind: "backups"; appid: string };

export type DView = { kind: "main" } | { kind: "excluded" };

/**
 * 그 뷰를 그릴 때 쓸 `key` — 목록 뷰에는 주지 않는다.
 * 상세·백업·제외 뷰는 리마운트가 이득이고(스크롤 초기화) 목록은 상태(스크롤·마지막 조작 행)를
 * 잃어 손해다. 그래서 key를 주는 쪽만 정한다 — `undefined`면 React가 같은 자리로 보고 상태를 보존한다.
 */
export function subViewKey(view: { kind: string }): string | undefined {
  return view.kind === "list" || view.kind === "main" ? undefined : view.kind;
}

/**
 * 비목록 뷰의 껍데기 — `[← 뒤로]`가 DialogBody 최상단 첫 요소다.
 * 첫 요소인 이유: 진입 직후 B가 안 먹어도 보이는 탈출구가 스크롤 밖으로 밀리지 않는다.
 * B = 한 단계 뒤로: 본문을 감싸는 `Focusable`에 `onCancelButton`을 건다. 실효는 미검증이고
 *   폴백이 무해하다 — 안 먹으면 위 버튼만 남는다(기능 손실 0).
 * 초기 포커스도 여기서 준다(착지 대상 = `[← 뒤로]`). 뷰마다 각자 지정하면 한 뷰가 빠지고,
 *   빠진 뷰에서만 착지가 달라진다.
 * 그 지정이 실제로 읽히게 하는 짝이 `preferredChildEntryProps`다. 없으면 `preferredFocus`는
 *   조용히 무효이고, 지금 착지가 맞는 것은 `[← 뒤로]`가 문서 순서 첫째라 생긴 우연이다 —
 *   위쪽 요소가 하나라도 생기면 깨지고, 깨진 것을 알 방법이 없다. 그래서 우연을 계약으로 바꾼다.
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
 * 목록 카드 — 팝업 G의 게임·백업 행과 팝업 D의 후보 행이 같은 모양이어야 한다.
 * 주황 경고 테두리는 없다("프로필 없음"·"미등록"은 정상 상태이고, 상태는 배지가 말한다).
 * 소비자가 둘 이상이라 값을 각자 들면 같은 목록이 화면마다 달라진다 —
 * `POPUP_LIST_MAX_HEIGHT`를 한 곳으로 모은 것과 같은 판단이다.
 */
export const CARD_STYLE = {
  background: "rgba(255,255,255,0.05)",
  borderRadius: "4px",
  padding: "8px 10px",
  marginBottom: "4px",
} as const;

/**
 * 카드 내용의 폭 상한.
 * 모달 자체 크기는 지정하지 않는다. 대신 행 내용의 폭을 접어 이름과 버튼이 화면 양 끝으로
 * 벌어지는 것을 막는다 — 그 벌어짐이 "버튼과 게임이 안 맞물려 보인다"의 실체다.
 * 실측 폭이 나오면 이 숫자 하나만 고친다.
 */
export const CARD_INNER_STYLE = {
  maxWidth: "720px", display: "flex", flexDirection: "column", gap: "4px",
} as const;

/**
 * 목록 스크롤 컨테이너 — 높이 상한과 하단 완충이 한 곳에서 온다.
 * 행마다 패딩을 두지 않는다: 값이 두 곳이면 새 목록에서 한쪽을 빠뜨리고, 빠뜨린 목록에서
 * 하단 여백 결함이 재발한다.
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
        /* 패드로 맨 아래에 닿았을 때 마지막 카드가 잘리지 않게 하는 유일한 자리
           (근거·숫자는 `limits.ts`의 이 상수 주석이 정본). Steam은 포커스 요소 하단을
           컨테이너 하단에 맞추고 멈추므로, 그보다 아래의 카드 메타 줄은 `paddingBottom`으로는
           보이지 않는다. */
        scrollPaddingBottom: POPUP_LIST_FOCUS_SLACK,
      }}
    >
      {children}
    </Focusable>
  );
}

/**
 * 목록 행에 붙이는 이동 성향 — 수직 이동 중 커서가 좌우로 튀는 것을 막는다.
 * 숫자를 박지 않고 라이브러리 enum을 쓴다(`deckyui.ts` 주석 참조).
 * 이것은 2중 방어의 한 겹이다(다른 겹 = 버튼 폭 고정). 런타임 실효는 실기가 판정하고,
 * 안 먹어도 화면은 그대로 동작한다.
 */
export const listRowNavProps = {
  navEntryPreferPosition: NavEntryPositionPreferences.MAINTAIN_X,
} as const;

/**
 * `preferredFocus`를 실제로 듣게 만드는 선언.
 * 컨테이너로 포커스가 들어올 때 Steam은 자기 `navEntryPreferPosition`을 보고 갈래를 고르는데,
 * 자손의 preferred-focus 표시를 훑는 갈래는 `PREFERRED_CHILD`일 때뿐이다(Steam 본체 실측).
 * 그 밖의 값(기본값 = 지정 없음)이면 문서 순서 첫 focusable이 가져가, 카드에 `preferredFocus`를
 * 달아도 목록 위 필터 줄이 이겼다 — 오타가 아니라 조용한 무효다. 이 갈래 서술은 관측 당시
 *   Steam 빌드의 실기 결과이며 현행 런타임은 코드만으로 확인할 수 없다.
 * 그래서 선언은 자식이 아니라 진입 컨테이너에 붙는다: `preferredFocus`(어느 자식)와 이 prop
 *   (그 표시를 볼 것인가)은 한 쌍이고, 한쪽만 있으면 아무 일도 안 일어난다.
 * 붙일 자리는 `preferredFocus`를 단 자손 전체를 품는 가장 바깥 컨테이너다 — 스크롤 목록에만
 *   붙이면 팝업 진입이 그 바깥에서 시작하므로 여전히 필터 줄에 선다.
 */
export const preferredChildEntryProps = {
  navEntryPreferPosition: NavEntryPositionPreferences.PREFERRED_CHILD,
} as const;

/**
 * 가로로 늘어선 버튼 줄에 붙인다.
 * 값은 반드시 `"row"`다. Steam 본체가 받는 낱말은 정해져 있고(row·column·grid 등), 그 밖의
 *   낱말(흔한 `"horizontal"` 포함)은 콘솔에 경고를 찍고 NONE = "지정하지 않은 것"이 된다 —
 *   오타가 아니라 조용한 무효라 화면은 고쳐진 듯 보이고 실기에서만 안 고쳐진다(Steam 실측 —
 *   관측 당시 Steam 빌드의 실기 결과이며 현행 런타임은 코드만으로 확인할 수 없다).
 * 지정이 없으면 Steam은 그 Focusable의 계산된 스타일로 방향을 추정한다: `display:flex`면
 *   `flex-direction`을 따르고 그 밖에는 `column`으로 떨어진다. 그래서 이미 flex 행인 컨테이너는
 *   지정 없이도 좌우가 살았고, 행 스타일이 flex가 아닌 컨테이너(배경·패딩만 있는 목록 카드)만
 *   세로로 오판돼 좌우 키가 죽었다.
 * 상수로 두는 이유: 새 버튼 줄마다 손으로 적으면 언젠가 한 줄이 빠지고, 그 줄에서만 좌우가
 *   죽는다 — 실기에서만 드러나 발견이 가장 늦다.
 * 가로 focusable이 둘 이상일 때만 붙인다. 세로 묶음에 붙이면 반대로 상하가 죽는다.
 */
export const ROW_FLOW = { "flow-children": "row" } as const;

// ── 확인 게이트 ───────────────────────────────────────────────────────

interface ConfirmSpecBase {
  title: string;
  /** 기존 확인창들의 `strDescription` 내용물 그대로. */
  body: ReactNode;
  /** 강조 블록(전체 초기화 전용). */
  warnBlock?: ReactNode;
  okText: string;
  cancelText?: string;
  /**
   * 취소가 없는 창(결과 팝업). 되돌릴 것이 없는 통지에 [취소]가 있으면 "취소하면 되돌려지나?"
   * 라는 없는 선택지를 만든다. 두 렌더러가 같은 것을 그린다: 중첩은 Steam의 `bAlertDialog`
   * (OK 단독), 폴백은 취소 버튼을 아예 그리지 않는다.
   * `bAlertDialog`가 이 빌드에서 실제로 취소를 감추는지는 실기 판정이다 — 안 먹으면 [취소]가
   * 하나 더 보일 뿐이고 누르면 같이 닫힌다(손실 없는 실패).
   */
  noCancel?: boolean;
}

export interface PlainConfirmSpec extends ConfirmSpecBase {
  kind: "plain";
  onOK: () => void;
}

export interface InputConfirmSpec extends ConfirmSpecBase {
  kind: "input";
  /** 렌더러가 TextField와 그 상태를 소유한다(호출부는 값을 들고 있지 않는다). */
  input: { label: string; initial: string };
  /** 입력값에서 파생하는 동적 비활성. 미지정 = OK 항상 활성. */
  okDisabled?: (value: string) => boolean;
  onOK: (value: string) => void;
  /** 언마운트 직전 마지막 입력값 — 호출부가 보존했다가 `input.initial`로 되돌려준다. */
  onInputSnapshot?: (value: string) => void;
}

/**
 * 확인창 하나의 선언. 렌더 방식(중첩/폴백)과 무관하게 같은 값을 그린다.
 * union인 이유: `onOK(inputValue?: string)` 단일형은 strict 빌드에서 `string | undefined`가
 * `runRename(name: string)` 같은 실물 시그니처와 충돌한다. `kind`로 갈라 두면 렌더러가 타입
 * 내로잉으로 `string` 확정을 얻는다.
 */
export type ConfirmSpec = PlainConfirmSpec | InputConfirmSpec;

/**
 * 확인창을 중첩 모달로 띄울지, 팝업 내부 오버레이로 그릴지.
 * 실기에서 중첩이 실패하면 이 한 줄만 false로 바꾼다 — 두 렌더러가 같은 spec을 같은 요소로
 * 그리므로 호출부는 한 줄도 안 바뀐다. 그것이 이 구조의 값어치다.
 */
export const NESTED_CONFIRM = true;

/**
 * 게이트가 창을 못 띄웠을 때 할 말의 재료 — 키 하나이거나, 치환자가 있으면 값까지 온다.
 * 이 자리의 문구는 "무엇이 안 됐고 이제 무엇을 누르면 되는가"를 말하는데, 그 「무엇」이 경로마다
 * 다른 값일 수 있다(예: `{profile}`을 품은 실패 문구). 게이트가 `t(key)`만 부르면 화면에 치환자가
 * 그대로 떠 어느 버튼인지 지목하지 못하고, 틀린 적용 버튼을 누르면 다른 프로필이 게임에 쓰인다.
 * 계약이 치환자를 인정하면 재발할 자리가 없다. 키만 주는 호출부는 한 글자도 바뀌지 않는다.
 */
export type GateFailure = StringKey | { key: StringKey; params: Record<string, string | number> };

/** 게이트 실패 문구를 만드는 단일 관문 — 두 형태를 여기서만 푼다. */
function failText(fail: GateFailure): string {
  return typeof fail === "string" ? t(fail) : t(fail.key, fail.params);
}

/** 게이트 시그니처 — 실패 문구는 호출부가 준다(공유 문장이 어느 경로에선 거짓이 되는 사고 방지). */
export type ConfirmGate = (spec: ConfirmSpec, fail: GateFailure, onFail: (msg: string) => void) => void;

/**
 * 두 렌더러가 공유하는 한 벌의 상태·계약.
 * 단일 종료: OK와 취소는 상호 배타이고 `onOK`는 최대 1회다. 두 번째 눌림이 도착할 때 이미
 *   닫히는 중일 수 있고, 그때 또 발화하면 토큰을 두 번 쓰거나 같은 파괴를 두 번 요청한다.
 *   빗장은 상태가 아니라 ref다: 상태로 막으면 두 번째 눌림이 재렌더 전에 도착할 때 낡은
 *   핸들러가 `done=false`를 보고 통과한다. ref는 같은 틱에 즉시 잠긴다.
 *   (`done` 상태는 버튼을 비활성으로 보이게 하는 몫만 맡는다.)
 * 입력 스냅샷은 언마운트 시 1회다 — 렌더러가 사라지는 시점이 곧 값을 잃는 시점이라, 호출부는
 *   "언제 저장할까"를 판단할 필요가 없다.
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
      // OK 후 종료 정책: RPC 결과를 기다리지 않고 즉시 닫는다. 결과·오류는 팝업 note가 보고하고,
      //   TOCTOU 재질문은 갱신 params로 새 창을 연다.
      // `finally`인 이유: `onOK`가 동기적으로 던지면 닫기가 건너뛰어져 확인창이 남고 빗장만
      //   걸린 상태 — 아무 버튼도 안 듣는, 빠져나갈 수 없는 자리가 된다. 던지든 말든 창은 닫는다.
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
 * 두 렌더러가 그리는 같은 본문. 여기 한 곳에서 만들어야 중첩/폴백의 문구가 갈리지 않는다.
 * 문자열을 `"\n\n"`로 이어 붙이지 않는다 — 한 문단으로 뭉쳐 렌더된다. `ReactNode`는 엘리먼트로
 * 줘야 줄이 갈린다.
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
          /* 빅픽처에서 텍스트 필드가 포커스를 받아야 가상 키보드가 뜬다. */
          focusOnMount
          style={INPUT_FACE_STYLE}
          onChange={(e) => setValue(e.target.value)}
        />
      ) : null}
    </div>
  );
}

/**
 * 입력형 확인창의 입력면.
 * Steam `TextField`의 기본은 흰 통짜 면이라 어두운 다이얼로그에서 "이 창의 일부가 아닌 것"처럼
 * 튄다. 계약: 입력면은 주변 배경과 같은 어두운 계열이고 경계는 미세 대비/1px 윤곽으로 식별된다.
 * 이 자리가 하나인 이유: 중첩과 폴백이 같은 `specBody`를 그린다 — 각자 칠하면 두 모드의 입력창이
 *   달라 보인다. 글자색만 명시한다: 면이 어두워졌으므로 상속에 맡기면 안 읽힐 수 있다.
 * 판정은 실기 스샷이다(자동 검사로는 실물 CSS를 모른다).
 */
const INPUT_FACE_STYLE = {
  background: "rgba(0,0,0,0.35)",
  color: "#ffffff",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "4px",
  padding: "6px 8px",
} as const;

/** 입력형 확인창의 최소 폭 — 비입력형에는 걸지 않는다. */
function specWrapStyle(spec: ConfirmSpec) {
  return spec.kind === "input" ? { minWidth: "400px" } : undefined;
}

/**
 * 중첩 확인창의 `closeModal` 호출을 최대 한 번만 통과시키는 래퍼.
 * 게이트의 `fire`와 Steam `ConfirmModal`이 같은 종료 경로에서 각각 닫기를 요청할 수 있다는
 * 실측에 대응한다. 어느 쪽이 먼저 와도 실제 콜백은 한 번만 실행한다.
 * 빗장은 ref라 같은 틱에 즉시 잠기고 재렌더에도 유지된다.
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
 * 일반 확인창의 기본 포커스를 [취소]로 옮긴다.
 * 파괴 동작인 OK에 처음부터 포커스가 있으면 A 한 번의 관성 입력으로 승인될 수 있다.
 * `ConfirmModal`에는 초기 포커스 대상을 넘기는 통로가 없어, 우리가 준 취소 라벨로 버튼을 찾고
 * 본문에서 올라간 현재 `[role=dialog]` 안에서만 `.focus()`한다. 못 찾으면 기존 동작을 유지한다.
 *
 * 한 프레임 늦추는 것은 마운트 뒤 Steam의 지연 포커스가 먼저 건 포커스를 덮었던 실측에 대한
 * 대응이다 — 관측 당시 Steam 빌드의 실기 결과이며 현행 런타임은 코드만으로 확인할 수 없다.
 * Steam 내부 타이머 값이나 chunk 이름에는 의존하지 않는다.
 * 입력형은 `TextField.focusOnMount`를 보존해야 가상 키보드 진입을 빼앗지 않으므로 제외한다.
 * `noCancel` 창에는 취소 버튼이 없으므로 제외한다.
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
 * 중첩 렌더러 — `showModal`로 팝업 위에 `ConfirmModal`을 띄운다.
 * `closeModal`은 `showModal`이 최상위에 주입한 것이다 — 1회 래퍼를 씌워 `ConfirmModal`에 넘기고,
 * 우리 게이트도 같은 래퍼를 쓴다. 두 경로가 각자 닫아도 실제 닫기는 한 번이다.
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
  /* 본문 div가 초기 포커스의 앵커다 — 여기서 위로 올라가 우리 창을 찾는다. */
  const bodyRef = useCancelFirstFocus(spec);
  return (
    <ConfirmModal
      strTitle={spec.title}
      strDescription={
        <div ref={bodyRef} style={specWrapStyle(spec)}>{specBody(spec, gate.value, gate.setValue)}</div>
      }
      strOKButtonText={spec.okText}
      strCancelButtonText={spec.cancelText ?? t("CANCEL")}
      /* 결과 팝업은 OK 하나다 — Steam의 알림 다이얼로그 모드. */
      bAlertDialog={spec.noCancel}
      bOKDisabled={gate.okDisabled}
      /* 발화 뒤에는 취소도 잠근다 — OK와 취소가 상호 배타라는 계약을 화면에서도 지킨다. */
      bCancelDisabled={gate.done}
      closeModal={close}
      onOK={gate.onOK}
      onCancel={gate.onCancel}
    />
  );
}

/**
 * 폴백 렌더러 — 중첩이 실기에서 실패할 때 팝업 안에 그리는 같은 창.
 * 이 오버레이가 떠 있는 동안 원 콘텐츠가 사라지는 것은 호출부가 `usePopupGate().renderBody`로
 * 본문을 감쌌을 때다 — 그 관용구는 usePopupGate 주석이 정본이다.
 */
/**
 * 폴백 확인창 푸터 버튼의 시각 — 잠긴 모습은 Steam `DialogButton disabled` 기본에 맡긴다.
 * 한때 비활성일 때 반투명 면을 우리가 그렸다: 미완 상태의 파괴 버튼이 흐린 글자만으로 렌더돼
 *   "죽은 텍스트"로 읽힌다는 판단이었다. 2026-09-02 실기에서 그 면이 라벨 크기의 알약으로 보여
 *   푸터 버튼 안에 또 다른 작은 버튼이 있는 것처럼 읽혔고, 사용자는 면이 없던 이전 모습
 *   (`ClaudeWork/GfxProfileToolV2/shots/before-confirm-reset-0016.png`)을 정상으로 판정했다.
 *   실기 증거는 `field-20260902-20260902-203630/evidence/f1b-reset-confirm.png`.
 * 이 잠긴 모습은 `delete`를 입력하기 전에만 지나가는 자리라 화면 도달 빈도가 낮다 — 안 읽히는
 *   쪽의 값보다 잘못 읽히는 쪽의 대가가 컸다.
 * 중첩 렌더러의 OK 라벨도 같은 이유로 면을 그리지 않는다. 두 렌더러의 잠김 시각이 같아야
 *   한다는 계약은 "둘 다 Steam 기본 dimming에 기댄다"로 지켜진다 — 우리가 값을 적어 맞추지
 *   않으므로 한쪽만 갈릴 자리도 없다.
 */
const OVERLAY_BUTTON_STYLE = { minWidth: "120px" } as const;

export function ConfirmOverlay({ spec, onClose }: { spec: ConfirmSpec; onClose: () => void }) {
  const gate = useSpecGate(spec, onClose);
  return (
    <Focusable onCancelButton={gate.onCancel} style={{ ...COLUMN_STYLE, ...specWrapStyle(spec) }}>
      <div style={{ fontSize: "18px", fontWeight: "bold" }}>{spec.title}</div>
      {specBody(spec, gate.value, gate.setValue)}
      {/* 이 두 버튼만 `DialogButton`을 직접 쓴다(파일 단위 예외 — `build.sh` grep ⑤가 popup.tsx만 허용).
          Steam `ConfirmModal`의 푸터는 `DialogTwoColLayout`이 반폭씩 나눠 가져 전역 `width:100%`
          오염에 면역이다. 폴백이 여기서 `fit-content`로 접으면 중첩과 폴백의 푸터 모양이 갈려
          "두 렌더러가 같은 것을 그린다" 계약이 깨진다. 파일 밖 예외 목록은 두지 않는다 —
          목록을 두면 그 목록이 다음 라운드의 구멍이 된다. */}
      <Focusable {...ROW_FLOW} style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
        <DialogButton
          onClick={gate.onOK}
          disabled={gate.okDisabled}
          style={OVERLAY_BUTTON_STYLE}
        >
          {spec.okText}
        </DialogButton>
        {/* 결과 팝업에는 취소가 없다 — 숨기는 것이 아니라 그리지 않는다.
            중첩 렌더러의 `bAlertDialog`와 같은 결과를 폴백에서도 내야 계약이 선다. */}
        {spec.noCancel ? null : (
          <DialogButton
            onClick={gate.onCancel}
            disabled={gate.done}
            style={OVERLAY_BUTTON_STYLE}
          >
            {spec.cancelText ?? t("CANCEL")}
          </DialogButton>
        )}
      </Focusable>
    </Focusable>
  );
}

/**
 * 팝업이 쓰는 확인 게이트 한 벌 — 게이트와 격리가 같이 온다.
 * 현재 팝업 3종은 본문을 renderBody로 감싸, 폴백 오버레이가 있으면 원 콘텐츠 대신 오버레이를 그린다.
 * 훅의 타입이 사용을 강제하지는 않으므로 새 소비자도 같은 관용구를 지켜야 한다.
 * `showModal`이 죽는 경우(런타임에 undefined일 수 있다)는 화면이 말한다 — 안전한 것과 진단
 *   가능한 것은 다른 요건이다.
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
        // 치환자가 있는 문구도 여기서 채워진다 — `failText`가 두 형태의 단일 관문이다.
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

// ── 데이터 로드·갱신 ──────────────────────────────────────────────────

export interface PopupLoader<T> {
  (): Promise<Env<T>>;
}

export interface PopupCall<R> {
  (): Promise<Env<R>>;
}

/**
 * 받은 봉투로 화면 문구만 정하는 자리(재조회·통지는 호출부의 일이 아니다).
 * `true`를 돌려주면 "이번 결과를 창으로 말했다"는 뜻이다(2겹 방지). 호출부는 그 사실만 알리고,
 * 화면이 낡았는지의 판정은 문이 한다.
 */
export interface PopupResult<R> {
  (res: Env<R>): boolean | void;
}

/**
 * RPC 한 왕복을 감싸는 문. 호출부는 봉투를 받아 화면 문구만 정하고, busy·재조회·변경 통지·
 * 예기치 못한 실패 문구는 전부 이 문이 맡는다.
 */
export interface PopupRunner {
  <R>(
    call: PopupCall<R>,
    failKey: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void>;
}

/**
 * 이 문이 재조회·변경 통지를 생략하는 응답은 CONFIRM_REQUIRED뿐이다. 이는 모든 무쓰기 응답을
 * 분류한 결과가 아니라, 토큰 발급만 공통 흐름 신호로 식별하고 나머지는 보수적으로 재조회하는 정책이다.
 */
function isTokenIssue(res: { ok: boolean; code?: string }): boolean {
  return !res.ok && res.code === "CONFIRM_REQUIRED";
}

/**
 * 왕복 하나 — `begin`/`end`를 구조적으로 짝짓는다.
 * `call()`의 동기 throw도 Promise 거절로 바꿔 `finally(end)`가 항상 붙도록 한다. 도달성(RPC가
 *   동기적으로 던지는가)은 미확정이지만, 가드를 문 하나로 모으는 편이 예외 갈래를 세는 것보다 싸다.
 * 동기 throw와 비동기 거절이 같은 자리(`onSettle`의 err)로 온다 — 두 갈래를 따로 두면 한쪽만
 *   고쳐지는 날이 온다.
 * `end`는 `onSettle`보다 뒤에 돈다: 화면 문구가 정해지기 전에 문이 열리면 그 틈에 낡은 화면이
 *   조작 가능해진다.
 */
function inDoor<R>(
  begin: () => void,
  end: () => void,
  call: PopupCall<R>,
  onSettle: (res: Env<R> | null, err: unknown) => void,
): Promise<void> {
  begin();
  // 호출 자체는 동기로 나간다(마이크로태스크로 미루지 않는다) — 누른 그 자리에서 왕복이
  //   시작한다는 관측 가능한 순서를 바꾸지 않기 위해서다. 바꾸는 것은 죽는 방식뿐이다.
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
 * 문을 지나는 왕복이 화면에 닿는 자리. 소비자(팝업 3종·QAM)가 채운다.
 * 문구를 문이 정하지 않는 이유: 같은 실패라도 팝업은 note 한 줄, QAM은 상태박스의 실패 슬롯
 * (+받은 시각)이다. 공유하는 것은 규칙(무엇을 언제 다시 읽는가)이지 문장이 아니다.
 */
export interface DoorSink<T> {
  /**
   * 새 왕복이 시작됐다(조회·변이 공용) — 화면이 든 직전 왕복의 말은 여기서 낡는다.
   * 거두는 자리를 호출부마다 두면 하나를 빠뜨려, 죽은 왕복이 남긴 "예기치 못한 오류"가 다시 눌러
   *   성공해도 목록 아래 남는다. 그래서 "새 동작이 시작되면 지난 말은 낡는다"를 문 하나에 둔다.
   * `reload`는 이 신호를 내지 않는다: 변이 뒤 자동 재조회가 여기 걸리면 방금 그 변이가 남긴
   *   말을 스스로 지운다. 신호의 뜻은 "사용자가 새 동작을 걸었다"이지 "왕복이 나갔다"가 아니다.
   * 미지정이면 아무 일도 안 한다.
   */
  onStart?: () => void;
  /** 최신 세대의 조회가 성공했다 — 봉투의 payload. */
  onData: (data: T) => void;
  /**
   * 조회가 실패했다 — 봉투가 왔고 `ok:false`인 경우뿐이다. `code`는 그 봉투의 코드이므로
   * 소비자는 `tCode` 단일 관문에 그대로 실어도 된다.
   * (왕복이 죽은 경우까지 이 문으로 내보내면 `tCode`가 등재된 그 코드를 만나 failKey를 통째로
   *  버리고 "예기치 못한 오류"만 그린다 — 어느 화면이 못 읽혔는지가 사라진다. 그래서 문을 갈랐다.)
   */
  onLoadFail: (code: string) => void;
  /**
   * 조회 왕복이 죽었다(봉투 자체가 없다) — 백엔드 코드는 존재하지 않는다.
   * 그래서 코드를 주지 않는다. 소비자가 그릴 수 있는 것은 자기가 아는 실패 키뿐이고, 진단 원문이
   * 필요한 소비자를 위해 `err`만 온다. 변이 쪽 `onCallFail`과 같은 대칭이다 — 안 채우면 컴파일이 깨진다.
   */
  onLoadDead: (err: unknown) => void;
  /**
   * 변이·조회 왕복이 죽었다(봉투가 없다) — 호출부가 준 failKey와 함께.
   * 여기 오는 것은 화면이 직접 건 호출(`runMutation`·`runQuery`)이다. 문이 스스로 도는 `reload`의
   * 죽음은 `onLoadDead`로 나간다 — 그쪽은 호출부가 준 키가 없다.
   */
  onCallFail: (key: StringKey, err: unknown) => void;
  /**
   * 변이는 성공했는데 뒤따르는 재조회가 실패했다(성공 침묵의 유일한 예외).
   * 이 갈래에서 화면은 옛 상태를 그대로 보여준다 — 마커가 안 움직여 "눌렀는데 아무 일도 안
   *   일어난" 먹통으로 읽힌다. 그래서 여기서만 말한다.
   * 판정은 이 문 하나가 한다: 두 사실(변이 성공 여부·그 뒤 재조회 결과)을 다 아는 자리가 여기뿐이다.
   * 미지정이면 아무 일도 안 한다.
   */
  onStaleAfterWrite?: () => void;
}

export interface DataDoor {
  /** 왕복이 하나라도 진행 중인가(조회·변이 공용). */
  busy: boolean;
  /** 쓸 수 있는 왕복이 진행 중인가 — "적용 중"처럼 조회와 갈라 말해야 하는 화면이 쓴다. */
  mutating: boolean;
  /** 다시 읽는다. 인자는 문 내부용이다 — 화면이 부를 때는 인자 없이 부른다. */
  reload: (afterWrite?: boolean) => void;
  /** 확정 실행(쓸 수 있는 호출). 응답이 토큰 발급이 아니면 재조회 + 변경 통지가 따라온다. */
  runMutation: PopupRunner;
  /** 조회(읽기 전용 호출). busy만 같이 쓰고 재조회·통지는 하지 않는다. */
  runQuery: PopupRunner;
}

/**
 * 조회·변이가 지나는 문 하나 — 세 보증이 여기 한 곳에 있다.
 *   ① 세대 가드: 재조회는 겹칠 수 있고(연타·변이 뒤 자동 재조회), 먼저 나간 응답이 나중에
 *      도착하면 낡은 값이 새 값을 덮는다. 응답마다 자기 세대를 들고 와 최신 세대만 반영한다 —
 *      빗장은 상태가 아니라 ref다(상태로 막으면 재렌더 전에 도착한 두 번째가 낡은 값을 통과시킨다).
 *   ② busy 문 하나: 조회도 변이도 이 문을 지나므로 여기서만 켜고 끈다. 왕복이 겹칠 수 있어
 *      불리언이 아니라 진행 수로 센다.
 *   ③ 확정 실행은 성공·실패를 가리지 않고 다시 읽는다: 엔진은 쓴 뒤에 거부할 수 있어(체크인·부분
 *      삭제) "실패했는데 디스크는 바뀐" 상태가 실재한다. 재조회를 생략하는 응답은 토큰 발급
 *      (`CONFIRM_REQUIRED`)뿐이며, 이는 무쓰기 응답 전량의 분류가 아니라 보수적 재조회 정책이다
 *      (`isTokenIssue`).
 *
 * 왜 훅에서 한 겹 더 갈랐나: 팝업 3종은 `usePopupData`로 이 문을 상속받는데 QAM은 네 번째
 *   소비자이면서 자기 조회·변이를 손으로 배선해, 세 보증이 QAM에만 없었다. QAM은 화면 표현이
 *   달라 `usePopupData`를 통째로 쓸 수 없으므로 — 화면 처리는 sink로 내주고 규칙만 공유한다.
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
   * 통지·화면 처리는 ref로 든다 — 그래야 아래 문들이 언제 만들어졌든 같게 동작한다.
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
   * 다시 읽는다. `afterWrite`는 성공한 변이가 부른 재조회라는 표시다 —
   * 그 재조회가 실패하면 화면이 결과를 못 보이므로 문이 그 사실을 알린다.
   * 세대 가드에 걸린(=더 새 조회가 이미 나간) 응답은 알리지 않는다: 화면이 낡았는지는
   *   최신 조회가 정한다.
   */
  const reload = useCallback((afterWrite?: boolean) => {
    generation.current += 1;
    const mine = generation.current;
    return inDoor(() => begin(false), () => end(false), load, (res, err) => {
      // 옛 응답은 없던 일이다 — 화면은 이미 더 새 것을 알고 있다.
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
   * 두 호출 경로가 공유하는 한 벌 — `mutating` 여부만 다르다.
   * 결과 note는 뒤따르는 재조회를 기다리지 않고 즉시 쓴다. 따라서 재조회가 끝날 때까지 note와
   * 이전 data가 잠시 함께 보일 수 있다. 세대 가드는 그 구간을 없애는 장치가 아니라, 겹친 조회 중
   * 오래된 응답이 더 최신 응답을 덮지 못하게 하는 장치다.
   */
  function runWith<R>(
    writing: boolean,
    call: PopupCall<R>,
    key: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void> {
    // 지난 왕복의 말은 여기서 낡는다 — 시작할 때 거둔다. 정착 뒤에 거두면 이번
    //   왕복이 방금 적은 말까지 같이 지운다.
    to.current.onStart?.();
    return inDoor(() => begin(writing), () => end(writing), call, (res, err) => {
      // 성공한 변이만 「성공 뒤 재조회 실패 알림」의 대상이다: 실패는 이미 사유를 말했고, 왕복이
      //   죽은 경우는 무엇이 쓰였는지조차 모른다 — 거기에 "동작은 끝났습니다"를 얹으면 거짓이 된다.
      let wroteOk = false;
      // 이 알림은 「성공 침묵」의 예외다. 이번 왕복이 이미 창으로 결과를 말했다면 화면은
      //   침묵하지 않았고, 사용자는 무슨 일이 있었는지 이미 읽었다 — 그 위에 창을 하나 더 얹으면
      //   중첩 깊이 ≤1 불변식만 깨고 새로 알려 주는 것은 없다. 그때 「화면이 낡았다」는
      //   둘째 줄 note가 계속 말한다(자리가 다르고, 창이 닫혀도 남는다).
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
 * 팝업 하나의 데이터 수명 — 마운트 시 자기 RPC를 부르고, 변이 뒤 자기가 다시 조회한다.
 * 규칙은 전부 `useDataDoor`가 들고, 여기는 팝업의 화면 처리(데이터·note)만 얹는다.
 * `profile_names`가 있으면 `setData`보다 먼저 `setProfileNames`에 반영한다.
 * 왜 팝업이 자기 재조회를 하는가: QAM `Content`는 팝업이 떠 있는 동안 언마운트일 수 있어
 *   `onMutate`만으로는 열려 있는 팝업 화면이 낡는다. 통지와 자기 갱신은 다른 일이다.
 * note는 두 줄이다: 동작이 남긴 말(`setNote`)과 재조회 실패는 서로 다른 사실이고 둘 다 참일 수
 *   있다(복원은 성공, 목록은 못 읽음). 자리를 갈라 두면 덮어쓸 수가 없다.
 */
export function usePopupData<T>(
  load: PopupLoader<T>,
  failKey: StringKey,
  /** 변이 통지 — 확정 실행이 끝나면 이 훅이 부른다(팝업이 각자 부르지 않는다). */
  onMutate?: () => void,
  /**
   * 성공했는데 화면이 못 따라온 경우에 부른다(변이 성공 뒤 재조회 실패). 판정은 문이 하고,
   * 그리는 것은 팝업의 일이다 — 이 훅은 확인 게이트를 모른다(알면 두 훅이 서로를 붙잡는다).
   */
  onStaleAfterWrite?: () => void,
): {
  data: T | null;
  /**
   * 화면이 지금 무언가 말하고 있는가를 판정할 때 쓰는 값(동작 note가 있으면 그것,
   * 없으면 재조회 실패 사유). 그리는 것은 `noteView`가 한다.
   */
  noteText: string | null;
  setNote: (v: string | null) => void;
  /**
   * 뒤따르는 재조회의 결과를 쓰는 자리(둘째 줄) — 실패면 사유, 성공이면 `null`.
   * 팝업이 자기 하위 목록을 다시 읽는 경우(복원 뒤 백업 목록)가 이 자리다. 그 실패를
   *   `setNote`로 쓰면 방금 한 동작의 결과와 후속 조치 안내를 덮는다 — 훅의 재조회가 덮던 것과
   *   같은 사고이고, 같은 해소(자리를 가른다)를 쓴다.
   */
  setReloadNote: (v: string | null) => void;
  /** 팝업 하단의 표준 렌더는 noteView다. noteText는 로딩·빈 상태 판정용으로도 공개되므로,
   *  타입이 별도 렌더를 금지하지는 않는다. */
  noteView: ReactNode;
  busy: boolean;
  reload: () => void;
  runMutation: PopupRunner;
  runQuery: PopupRunner;
} {
  const [data, setData] = useState<T | null>(null);
  const [note, setNote] = useState<string | null>(null);
  /** 재조회만 쓰는 자리 — 동작 note를 덮지 않는다(둘째 줄). */
  const [loadNote, setLoadNoteState] = useState<string | null>(null);
  /**
   * 지금 둘째 줄에 있는 말이 이 훅의 재조회에서 온 것인가.
   * 팝업이 스스로 부르는 뒤따르는 재조회(예: 복원 뒤 백업 목록 다시 읽기)도 같은 줄을 쓴다.
   *   그때까지 훅의 조회 성공이 그 줄을 거두면, "백업 목록은 여전히 못 읽었다"는 사실이 무관한
   *   조회 하나가 성공했다는 이유로 사라진다. 출처를 함께 들어 자기 것만 거둔다.
   */
  const ownLoadNote = useRef(false);
  const stale = useRef(onStaleAfterWrite);
  stale.current = onStaleAfterWrite;

  const setReloadNote = useCallback((value: string | null) => {
    ownLoadNote.current = false;
    setLoadNoteState(value);
  }, []);

  /** 둘째 줄에 이 훅의 조회가 쓴다는 표시까지 함께 — 위 `setReloadNote`의 대칭이다.
   *  조회 실패의 두 갈래(봉투 / 왕복 사망)가 같은 줄을 쓰므로, 출처 표시와 쓰기를 한 문에
   *    묶어 둔다. 갈래가 늘 때 한쪽만 표시를 빠뜨리는 경로를 만들지 않는다. */
  const setOwnLoadNote = useCallback((value: string) => {
    ownLoadNote.current = true;
    setLoadNoteState(value);
  }, []);

  const door = useDataDoor<T>(
    load,
    {
      // 동작 note는 직전 왕복의 말이다 — 새 동작이 걸리면 그 말은 낡는다.
      //   둘째 줄(`loadNote`)은 여기서 손대지 않는다: 그쪽은 "화면이 낡았다"는 다른 사실이고
      //   자기 출처(`ownLoadNote`)를 보고 스스로 거둔다.
      onStart: () => setNote(null),
      onData: (payload) => {
        // 상태 반영보다 먼저 — 아래 setData로 다시 그려질 때 이미 새 이름이어야 한다.
        const named = payload as { profile_names?: { dock?: string; internal?: string } };
        if (named && named.profile_names) setProfileNames(named.profile_names);
        setData(payload);
        if (ownLoadNote.current) setLoadNoteState(null);
      },
      // 봉투가 준 코드다 — `tCode` 단일 관문이 맞는 자리다.
      onLoadFail: (code) => setOwnLoadNote(tCode(code, failKey)),
      // 왕복이 죽었다 = 백엔드 코드가 없다. `"UNEXPECTED"`는 화면이 붙이는 꼬리표이므로 `tCode`가
      //   아니라 `t(failKey, …)`다 — 그래야 어느 화면이 못 읽혔는지가 남는다.
      onLoadDead: () => setOwnLoadNote(t(failKey, { code: "UNEXPECTED" })),
      // 여기서 `tCode`를 쓰면 안 된다: `tCode(code, fallback)`은 `code in en ? t(code) : t(fallback,{code})`
      //   이고 `"UNEXPECTED"`는 등재된 키라 `failKey`가 항상 버려진다 — 저장이 죽었는지 삭제가 죽었는지
      //   화면이 말하지 못한다. (위 `onLoadFail`은 봉투가 온 경로뿐이라 `code`가 진짜 백엔드 코드다 —
      //   그쪽은 `tCode`가 맞다.)
      onCallFail: (key) => setNote(t(key, { code: "UNEXPECTED" })),
      // ref로 최신 것을 부른다 — 이 훅이 만들어질 때의 클로저를 잡으면 확인창 안에 갇힌
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
 * 팝업 하단 note 자리 — 없는 줄은 자리도 만들지 않는다.
 * 내보내지 않는다. 이 컴포넌트로 가는 표준 통로는 `usePopupData().noteView`이고, 공개된
 * `noteText`로 팝업이 따로 그리는 것을 타입이 막지는 않는다.
 */
function PopupNotes({ note, loadNote }: { note: string | null; loadNote: string | null }) {
  return (
    <>
      {note ? <div style={NOTE_STYLE}>{note}</div> : null}
      {loadNote ? <div style={SUB_NOTE_STYLE}>{loadNote}</div> : null}
    </>
  );
}
