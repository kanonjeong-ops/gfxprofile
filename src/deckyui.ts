// @decky/ui를 import하는 유일한 파일이다.
//
// 이유: @decky/ui의 컴포넌트는 우리 번들에 들어가지 않는다. @decky/rollup이 external로 빼고
// Decky Loader가 전역 `DFL`로 준다. 설치된 @decky/ui 소스에서 컴포넌트는 Steam 내부 webpack
// 모듈을 `findModuleExport`로 찾아 얻는다 — 실제 Loader 런타임의 조회 실패 동작은 [미확인]이다.
// 타입 검사로는 절대 잡히지 않는다(`ModalRoot`는 아예 타입이 `any`다).
//
// 그래서 (1) import 지점을 한 곳으로 모으고 (2) 여기서 런타임 self-check를 돌린다.
// 불변식: 그 모듈을 참조하는 src/ 파일이 이 파일 하나뿐이어야 한다 — build.sh의 grep 단계가
// 주석을 지우지 않고 원문에 거는 검사라, 다른 파일 주석에 import 구문을 예시로 적어도 죽는다.

import {
  ButtonItem,
  ConfirmModal,
  // 팝업 골격의 구획. `DialogHeader`·`DialogBody` 둘 다 `@decky/ui`의 타입 선언에 실재하고,
  //   런타임에 못 얻어지면 `uicheckMissing`이 이름을 모아 백엔드 로그로 보고한다.
  DialogBody,
  DialogButton,
  DialogHeader,
  Focusable,
  // `ModalRoot`는 타입이 `any`다(`@decky/ui`의 `Modal.d.ts`) — 기존 관례대로 여기에 명시해 둔다.
  //    타입 검사가 이 컴포넌트에 대해서는 아무것도 보장하지 않는다.
  //    주 경로에서 쓴다 — 팝업 3종의 골격(`popup.tsx`의 `GfxPopup`)이 이것으로 뜬다. 확인창의
  //      폴백 렌더러(`ConfirmOverlay`)는 이것을 쓰지 않는다: 이미 떠 있는 `GfxPopup` 안쪽에
  //      `Focusable`로 그리므로, 이 항목을 여기 남기는 근거는 폴백이 아니라 그 골격이다.
  //    여기 올려 두는 것 자체가 관측 장치이기도 하다 — self-check가 런타임에 실제로 얻어지는지
  //      보고, 못 얻으면 `uicheck_missing`으로 백엔드 로그에 남는다.
  ModalRoot,
  // 열 유지의 값은 라이브러리 상수로 쓴다 — 숫자를 박으면 라이브러리가 값을 바꾸는 날 조용히
  //   다른 뜻이 된다. `NavEntryPositionPreferences`는 enum이라 값이 아니라 이름으로 결합한다.
  //   런타임에 못 얻어지면 self-check가 보고한다.
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
 * self-check 대상. 위 import 목록과 정확히 같아야 한다 — build.sh의 U19 self-check가
 * import·REQUIRED·재수출 목록 셋을 대조하고, 이름과 값이 다른 항목도 잡는다.
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
 * `staticClasses.Title`을 직접 읽지 않는다.
 * staticClasses 자체가 undefined면 `.Title` 접근이 plugin 초기화 중에 TypeError를 내고,
 * 그러면 self-check도 진단 로그도 도달하지 못한 채 플러그인이 통째로 죽는다.
 * 안전장치는 자기가 감시하는 실패에 자기가 걸려선 안 된다.
 */
export function titleClass(): string | undefined {
  return staticClasses?.Title;
}
