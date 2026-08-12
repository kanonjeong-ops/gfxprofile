// ★ @decky/ui를 import하는 **유일한 파일**이다 (설계 S10).
//
// 이유: @decky/ui의 컴포넌트는 우리 번들에 들어가지 않는다. @decky/rollup이 external로 빼고
// Decky Loader가 전역 `DFL`로 준다. 그래서 컴포넌트는 런타임에 Steam 내부 webpack 모듈을
// 시그니처로 찾아 얻어지고, **실패하면 예외가 아니라 `undefined`가 된다.**
// 타입 검사로는 절대 잡히지 않는다(`ModalRoot`는 아예 타입이 `any`다).
//
// 그래서 (1) import 지점을 한 곳으로 모으고 (2) 여기서 런타임 self-check를 돌린다.
// 불변식: 그 모듈을 참조하는 src/ 파일이 이 파일 하나뿐이어야 한다(build.sh의 grep 단계).

import {
  ButtonItem,
  ConfirmModal,
  // ★ 팝업 골격의 구획(§4-A·§13). 타입은 `Dialog.d.ts:23,28`에 실재하고 lsfg-vk가 런타임에서
  //   실제로 쓴다(dist:1652-1656). 못 얻어지면 `uicheckMissing`이 백엔드 로그로 보고한다.
  DialogBody,
  DialogButton,
  DialogHeader,
  Focusable,
  // ⚠️ `ModalRoot`는 **타입이 `any`다**(`@decky/ui` 4.11.0 `Modal.d.ts:47`) — 기존 관례대로
  //    여기에 명시해 둔다. 타입 검사가 이 컴포넌트에 대해서는 아무것도 보장하지 않는다.
  //    ★ **주 경로에서 쓴다**(정정 2026-08-10 QA R5: 예전 주석은 "직접 쓰지 않는다"였다) —
  //      팝업 3종의 골격(`popup.tsx`의 `GfxPopup`)이 이것으로 뜬다.
  //      전체 초기화 확인창의 **폴백 경로**(설계 §4-D ②: `bOKDisabled`가 런타임에 무효면
  //      lsfg-vk처럼 자작 모달 + 자체 버튼 disabled)도 이 컴포넌트를 쓴다.
  //      **여기 올려 두는 것 자체가 관측 장치**이기도 하다 — self-check가 런타임에 실제로
  //      얻어지는지 보고, 못 얻으면 `uicheck_missing`으로 백엔드 로그에 남는다.
  ModalRoot,
  // ★ 열 유지(§4-E ②)의 값은 **라이브러리 상수**로 쓴다 — 숫자 2를 박으면 라이브러리가 값을
  //   바꾸는 날 조용히 다른 뜻이 된다(`FooterLegend.d.ts:33-36`). enum이라 값이 아니라 이름으로
  //   결합한다. 런타임에 못 얻어지면 self-check가 보고한다.
  NavEntryPositionPreferences,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";

export {
  ButtonItem,
  ConfirmModal,
  DialogBody,
  DialogButton,
  DialogHeader,
  Focusable,
  ModalRoot,
  NavEntryPositionPreferences,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  showModal,
  staticClasses,
};

/**
 * self-check 대상. 위 import 목록과 **정확히 같아야 한다** —
 * `build.sh grep`의 U19 검사가 두 목록을 뽑아 대조한다(P2에서 자동화, 반증 시험 완료).
 * 손으로 맞추던 시절에는 어긋나도 아무 일이 없었고, 그때 self-check는 빠진 컴포넌트를
 * **조용히 안 봤다** — 검사가 있는데 보지 않는 상태가 가장 나쁘다.
 */
const REQUIRED: Record<string, unknown> = {
  ButtonItem,
  ConfirmModal,
  DialogBody,
  DialogButton,
  DialogHeader,
  Focusable,
  ModalRoot,
  NavEntryPositionPreferences,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  showModal,
  staticClasses,
};

/** 런타임에 실제로 얻어지지 않은 것들의 이름을 돌려준다. 비어 있으면 정상. */
export function uicheckMissing(): string[] {
  return Object.keys(REQUIRED).filter((k) => REQUIRED[k] == null);
}

/**
 * `staticClasses.Title`을 **직접 읽지 않는다.**
 * staticClasses 자체가 undefined면 `.Title` 접근이 plugin 초기화 중에 TypeError를 내고,
 * 그러면 self-check도 진단 로그도 도달하지 못한 채 플러그인이 통째로 죽는다.
 * 안전장치는 자기가 감시하는 실패에 자기가 걸려선 안 된다.
 */
export function titleClass(): string | undefined {
  return staticClasses?.Title;
}
