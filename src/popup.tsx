import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ConfirmModal, DialogBody, DialogButton, DialogHeader, Focusable, ModalRoot,
  NavEntryPositionPreferences, TextField, showModal,
} from "./deckyui";
import { setProfileNames, t, tCode, type StringKey } from "./i18n";
import { POPUP_LIST_MAX_HEIGHT, POPUP_LIST_TAIL_PAD } from "./limits";
import type { Env } from "./rpc";
import { ErrorBoundary } from "./ui/ErrorBoundary";

/**
 * **팝업 공통 기반** (설계 §4) — 팝업 G·D·S가 공유하는 골격·뷰·확인 게이트·데이터 로드.
 *
 * ★★ 이 파일이 존재하는 이유: 팝업 3종이 각자 ModalRoot를 조립하면 **경계 배치·닫기 배선·
 *   확인창 생명주기가 세 벌**이 되고, 그중 하나가 틀린 날 그 화면만 조용히 다르게 동작한다.
 *   여기서 한 번 맞추면 나머지는 내용만 채운다.
 *
 * ★ 화면(P13·P14)은 아직 이 파일을 쓰지 않는다 — P12는 기반만 놓는다(신·구 공존).
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const NOTE_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;

/** 아이콘이 제목과 같은 줄에 설 때의 자리. 색은 주변을 따라간다(아이콘은 currentColor다). */
const HEADER_ICON_STYLE = { display: "inline-flex", marginRight: "6px", verticalAlign: "-0.1em" } as const;

// ── 골격 (§4-A) ──────────────────────────────────────────────────────────────

/**
 * 중앙 팝업 하나. **크기를 지정하지 않는다**(A10 — `popupWidth`/`popupHeight`/`bAllowFullSize` 금지).
 *
 * ★★ `ErrorBoundary`는 **`DialogBody` 안쪽**이다(R-4). `showModal`은 `closeModal`을
 *   **최상위 엘리먼트에만** 주입하므로(`index.tsx:141-143`·`ManageTab.tsx:53-54`가 계약으로
 *   문서화한 사실), 최상위를 경계로 감싸면 주입이 경계에서 삼켜져 **닫기 배선이 죽는다.**
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
 *   런타임 실효는 실기 ④가 판정하고, 안 먹으면 문서 순서 착지(=같은 자리)라 손실이 없다.
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
      onCancelButton={onBack}
      onCancelActionDescription={t("BACK")}
      style={COLUMN_STYLE}
    >
      <DialogButton
        preferredFocus
        onClick={onBack}
        style={{ alignSelf: "flex-start", minWidth: "96px", padding: "6px 10px", fontSize: "13px" }}
      >
        {t("BACK")}
      </DialogButton>
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
 *   빠뜨린 목록에서 GP#15가 그대로 재발한다(`LIST_BOTTOM_PADDING`의 교훈 그대로).
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

// ── 확인 게이트 (§4-C) ───────────────────────────────────────────────────────

interface ConfirmSpecBase {
  title: string;
  /** 기존 확인창들의 `strDescription` 내용물 그대로. */
  body: ReactNode;
  /** ⚠ 강조 블록(전체 초기화 전용 — A8). */
  warnBlock?: ReactNode;
  okText: string;
  cancelText?: string;
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

/** 게이트 시그니처 — **실패 문구는 호출부가 준다**(공유 문장이 어느 경로에선 거짓이 되는 사고 방지). */
export type ConfirmGate = (spec: ConfirmSpec, failKey: StringKey, onFail: (msg: string) => void) => void;

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
          onChange={(e) => setValue(e.target.value)}
        />
      ) : null}
    </div>
  );
}

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
  return (
    <ConfirmModal
      strTitle={spec.title}
      strDescription={<div style={specWrapStyle(spec)}>{specBody(spec, gate.value, gate.setValue)}</div>}
      strOKButtonText={spec.okText}
      strCancelButtonText={spec.cancelText ?? t("CANCEL")}
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
export function ConfirmOverlay({ spec, onClose }: { spec: ConfirmSpec; onClose: () => void }) {
  const gate = useSpecGate(spec, onClose);
  return (
    <Focusable onCancelButton={gate.onCancel} style={{ ...COLUMN_STYLE, ...specWrapStyle(spec) }}>
      <div style={{ fontSize: "18px", fontWeight: "bold" }}>{spec.title}</div>
      {specBody(spec, gate.value, gate.setValue)}
      <Focusable style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
        <DialogButton onClick={gate.onOK} disabled={gate.okDisabled} style={{ minWidth: "120px" }}>
          {spec.okText}
        </DialogButton>
        <DialogButton onClick={gate.onCancel} disabled={gate.done} style={{ minWidth: "120px" }}>
          {spec.cancelText ?? t("CANCEL")}
        </DialogButton>
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
 *   진단 가능한 것은 다른 요건이다(`ManageTab.openModal`이 세운 문법 그대로).
 */
export function usePopupGate(): {
  gate: ConfirmGate;
  overlay: ConfirmSpec | null;
  renderBody: (children: ReactNode) => ReactNode;
} {
  const [overlay, setOverlay] = useState<ConfirmSpec | null>(null);

  const gate = useCallback<ConfirmGate>((spec, failKey, onFail) => {
    if (NESTED_CONFIRM) {
      try {
        showModal(<SpecConfirmModal spec={spec} />);
      } catch (err) {
        console.error("[gfxprofile] confirm gate failed", err);
        onFail(t(failKey));
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
 * ⚠️ 화살표 타입(`() => Promise<…>`)을 **한 줄에 쓰지 않는다**: `test_i18n_sets`의 가시 문자열
 *   정규식이 `.tsx`에서 `>…<`를 JSX 텍스트로 오인해 거짓 FAIL을 낸다(`.ts`는 같은 이유로 이미
 *   제외돼 있다). 호출 시그니처 인터페이스로 두면 오탐이 **구조적으로** 생기지 않는다.
 */
export interface PopupLoader<T> {
  (): Promise<Env<T>>;
}

/** 왕복 하나를 부르는 얇은 호출자 — 인자에 화살표 타입을 쓰지 않기 위한 이름이기도 하다. */
export interface PopupCall<R> {
  (): Promise<Env<R>>;
}

/** 받은 봉투로 **화면 문구만** 정하는 자리(재조회·통지는 호출부의 일이 아니다). */
export interface PopupResult<R> {
  (res: Env<R>): void;
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
 * 팝업 하나의 데이터 수명 — **마운트 시 자기 RPC**를 부르고, 변이 뒤 **자기가 다시 조회**한다.
 *
 * ★★ `profile_names` 선반영(R-6): 봉투에 그 필드가 있으면 **상태 반영보다 먼저** i18n에
 *   태운다. 소비자마다 손으로 챙기던 시절에 한 곳이 빠져 *"초기화 뒤에도 옛 표시명이 남는"*
 *   사고가 났다(2026-08-10 QA R3) — 여기서 **구조적으로** 태우면 빠뜨릴 자리가 없다.
 * ★★ 왜 팝업이 자기 재조회를 하는가(§4-F): QAM `Content`는 팝업이 떠 있는 동안 언마운트일 수
 *   있어 `onMutate`만으로는 **열려 있는 팝업 화면이 낡는다.** 통지(onMutate)와 자기 갱신은
 *   다른 일이다.
 *
 * ★★ **세대 가드**(§4-F ① 개정): 재조회는 겹칠 수 있고(연타·변이 뒤 자동 재조회), 먼저 나간
 *   응답이 나중에 도착하면 **낡은 값이 새 값을 덮는다.** 응답마다 자기 세대를 들고 와서
 *   최신 세대만 반영한다 — 빗장은 **상태가 아니라 ref**다(P12 `useCloseOnce`의 교훈:
 *   상태로 막으면 재렌더 전에 도착한 두 번째가 낡은 값을 보고 그대로 통과한다).
 * ★★ **busy는 문이 하나다**(§4-F ② 개정): 조회도 변이도 이 훅을 지나므로 여기서만 켜고 끈다.
 *   예전에는 `reload()`가 busy를 안 켜서 [다시 검색] 연타가 **조회에는 무방비**였다(P14 O1).
 *   왕복이 겹칠 수 있으니 불리언이 아니라 **진행 수**로 센다 — 하나가 끝났다고 남은 왕복 중에
 *   화면이 열리면, 그 열린 틈이 곧 예전 버그다.
 */
export function usePopupData<T>(
  load: PopupLoader<T>,
  failKey: StringKey,
  /** 변이 통지 — 확정 실행이 끝나면 이 훅이 부른다(팝업이 각자 부르지 않는다). */
  onMutate?: () => void,
): {
  data: T | null;
  note: string | null;
  setNote: (v: string | null) => void;
  busy: boolean;
  reload: () => void;
  /** **확정 실행**(쓸 수 있는 호출). 응답이 토큰 발급이 아니면 재조회 + 변경 통지가 따라온다. */
  runMutation: PopupRunner;
  /** **조회**(읽기 전용 호출). busy만 같이 쓰고 재조회·통지는 하지 않는다. */
  runQuery: PopupRunner;
} {
  const [data, setData] = useState<T | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** 진행 중인 왕복 수(조회·변이 공용). */
  const inFlight = useRef(0);
  /** 조회 세대 — `reload`마다 오르고, 그보다 낡은 응답은 버린다. */
  const generation = useRef(0);
  /**
   * 통지 대상은 **ref로** 든다 — 그래야 아래 문들이 **언제 만들어졌든 같게 동작**한다.
   * (문을 매 렌더 새로 만들면서 prop을 클로저로 잡으면, 확인창 안에 갇힌 옛 문이 옛 통지를
   * 부르게 된다. 호출부가 deps를 정확히 적어야만 옳은 구조는 언젠가 틀린다.)
   */
  const notify = useRef(onMutate);
  notify.current = onMutate;

  const begin = useCallback(() => {
    inFlight.current += 1;
    setBusy(true);
  }, []);

  const end = useCallback(() => {
    inFlight.current -= 1;
    if (inFlight.current <= 0) {
      inFlight.current = 0;
      setBusy(false);
    }
  }, []);

  const reload = useCallback(() => {
    generation.current += 1;
    const mine = generation.current;
    begin();
    return load()
      .then(
        (res) => {
          // 옛 응답은 **없던 일**이다 — 화면은 이미 더 새 것을 알고 있다.
          if (mine !== generation.current) return;
          if (!res.ok) {
            setNote(tCode(res.code, failKey));
            return;
          }
          // ★ 상태 반영보다 **먼저** — 아래 setData로 다시 그려질 때 이미 새 이름이어야 한다.
          const payload = res.data as { profile_names?: { dock?: string; internal?: string } };
          if (payload && payload.profile_names) setProfileNames(payload.profile_names);
          setData(res.data);
        },
        () => {
          if (mine !== generation.current) return;
          setNote(tCode("UNEXPECTED", failKey));
        },
      )
      .finally(end);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, failKey, begin, end]);

  /**
   * 두 문이 공유하는 한 벌 — `mutating`만 다르다.
   *
   * ★ note는 **즉시** 뜬다(§4-F ④): 재조회 응답을 기다리지 않는다. 순서를 기다릴 이유였던
   *   *"낡은 데이터가 새 note와 어긋난다"*는 세대 가드가 구조적으로 막는다.
   * ★ 실패(거절·예외)에도 확정 실행이면 재조회한다 — 엔진은 **쓴 뒤에** 거부할 수 있어
   *   (체크인·부분 삭제) *"실패했는데 디스크는 바뀐"* 상태가 실재한다. 안 읽으면 화면이 그
   *   상태에 침묵한다.
   */
  function runWith<R>(
    mutating: boolean,
    call: PopupCall<R>,
    key: StringKey,
    onResult: PopupResult<R>,
  ): Promise<void> {
    begin();
    return call()
      .then(
        (res) => {
          onResult(res);
          if (!mutating || isTokenIssue(res)) return;
          reload();
          notify.current?.();
        },
        () => {
          setNote(tCode("UNEXPECTED", key));
          if (!mutating) return;
          reload();
          notify.current?.();
        },
      )
      .finally(end);
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

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { data, note, setNote, busy, reload, runMutation, runQuery };
}

/** 팝업 하단 note 한 줄 — 없으면 자리도 만들지 않는다(기존 "0이면 안 그림" 문법). */
export function PopupNote({ note }: { note: string | null }) {
  if (!note) return null;
  return <div style={NOTE_STYLE}>{note}</div>;
}
