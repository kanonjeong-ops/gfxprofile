"use strict";
/**
 * 팝업 공통 기반(설계 §4)의 계약을 **렌더해서** 잰다 — `qa/test_popup_shell.py`가 판정한다.
 *
 * 왜 grep이 아닌가: 이 프로젝트에서 거짓 검사가 다섯 번 났고 그중 둘이 *"grep이 규칙을 설명한
 * 주석을 잡았다"*였다. 골격의 계약(경계가 DialogBody **안쪽**인가 · 두 렌더러가 같은 것을
 * 그리는가 · 입력값이 살아남는가)은 전부 **구조와 동작**이라 표면 문법으로는 못 잰다.
 *
 * ★ 실행: node qa/popup_shell_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 *   소스디렉터리 인자는 **음성 대조군용**이다 — 사본에 위반을 주입해 같은 프로브를 돌린다.
 */
const path = require("path");
const {
  makeHost, h, find, findAll, texts, buttons, makeLoader, react,
} = require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ⚠️ 하네스(미니 React·렌더러·로더)는 **`qa/probe_kit.cjs` 한 곳**에 있다. P13에서 프로브가
//   셋으로 늘면서, 하네스 사본이 프로브마다 있으면 그중 하나만 고쳐지는 날이 온다.
//   이 파일이 재는 것은 하네스가 아니라 **팝업 공통 기반의 계약**이다.

// ── 모듈 목 ──────────────────────────────────────────────────────────────────
let modalThrows = false;
const shownModals = [];
const profileNameCalls = [];

const deckyui = {
  ConfirmModal: { __kind: "ConfirmModal" },
  DialogBody: { __kind: "DialogBody" },
  DialogButton: { __kind: "DialogButton" },
  DialogHeader: { __kind: "DialogHeader" },
  Focusable: { __kind: "Focusable" },
  ModalRoot: { __kind: "ModalRoot" },
  NavEntryPositionPreferences: { MAINTAIN_X: 2 },
  TextField: { __kind: "TextField" },
  showModal: (node) => {
    if (modalThrows) throw new TypeError("showModal is not a function");
    shownModals.push(node);
  },
};

const modules = {
  react,
  "./deckyui": deckyui,
  // ⚠️ `./rpc` 목은 두지 않는다(P15): 여기서 로드하는 것은 `popup.tsx`·`confirmSpecs.tsx`뿐이고
  //   둘 다 rpc를 **타입으로만** 참조한다(트랜스파일에서 사라진다). 실제로 부르는 코드가
  //   생기면 로더가 `unmocked: ./rpc`로 **소리 내어** 죽는다 — 조용히 통과하지 않는다.
  "./ui/ErrorBoundary": null,       // 실물을 쓴다(경계 배치가 판정 대상이다) — 아래에서 채운다
  "./i18n": {
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: (names) => { profileNameCalls.push(names); },
  },
};

const load = makeLoader(srcDir, modules);

const popup = load("popup.tsx");
// **폴백 모드**의 팝업 — `NESTED_CONFIRM` 한 줄만 뒤집은 사본이다(그 스위치가 실제로
// 렌더 경로를 가르는지, 그리고 두 경로가 같은 것을 그리는지를 이 사본으로 잰다).
const NESTED_ANCHOR = "export const NESTED_CONFIRM = true;";
let anchorFound = true;
const popupFallback = load("popup.tsx", (src) => {
  if (!src.includes(NESTED_ANCHOR)) { anchorFound = false; return src; }
  return src.replace(NESTED_ANCHOR, "export const NESTED_CONFIRM = false;");
});
const specs = load("confirmSpecs.tsx");

// ── ① 골격 ───────────────────────────────────────────────────────────────────
let closeModalSeen = null;
const closeModal = () => {};
const skeletonHost = makeHost(() =>
  h(popup.GfxPopup, {
    title: "POPUP_TITLE",
    icon: h("svg", null),
    where: "popup-g",
    closeModal,
    children: h("div", null, "BODY_CHILD"),
  }));
const skeleton = skeletonHost.render();
const modalRoot = find(skeleton, "ModalRoot");
const header = find(skeleton, "DialogHeader");
const body = find(skeleton, "DialogBody");
const boundary = find(skeleton, "ErrorBoundary");
if (modalRoot) closeModalSeen = modalRoot.node.props.closeModal === closeModal;

const skeletonReport = {
  rootIsModalRoot: !!(skeleton && skeleton.rendered && skeleton.rendered.name === "ModalRoot"),
  hasHeader: !!header,
  hasBody: !!body,
  headerText: header ? texts(header.node).join(" ") : "",
  boundaryFound: !!boundary,
  // ★ R-4: 경계는 **DialogBody 안쪽**이어야 한다. 최상위를 감싸면 showModal의 closeModal 주입이
  //   경계에서 삼켜져 닫기 배선이 죽는다.
  boundaryInsideBody: !!(boundary && boundary.ancestors.some((a) => a.name === "DialogBody")),
  boundaryWrapsRoot: !!(boundary && !boundary.ancestors.some((a) => a.name === "ModalRoot")),
  closeModalReachedRoot: closeModalSeen,
  // 크기 무지정(A10)
  sizeProps: modalRoot
    ? ["popupWidth", "popupHeight", "bAllowFullSize"].filter((k) => k in modalRoot.node.props)
    : ["<ModalRoot 없음>"],
  childRendered: texts(skeleton).includes("BODY_CHILD"),
  scrollListMaxHeight: (() => {
    const listHost = makeHost(() => h(popup.PopupScrollList, { children: h("div", null, "ROW") }));
    const list = listHost.render();
    const focusable = find(list, "Focusable");
    return focusable ? focusable.node.props.style : null;
  })(),
  navPrefersMaintainX: popup.listRowNavProps.navEntryPreferPosition === 2,
};

// ── ② 뷰 전환·뒤로가기·목록 비리마운트 ───────────────────────────────────────
const backCalls = [];
const subHost = makeHost(() =>
  h(popup.PopupSubView, { onBack: () => backCalls.push(1), children: h("div", null, "SUB_BODY") }));
const sub = subHost.render();
const subFocusable = find(sub, "Focusable");
const subButtons = buttons(sub);
if (subButtons[0] && subButtons[0].onClick) subButtons[0].onClick();

const viewReport = {
  // GP#3 — 목록 뷰는 key가 없어야(=리마운트되지 않아야) 한다
  listKey: popup.subViewKey({ kind: "list" }) ?? null,
  mainKey: popup.subViewKey({ kind: "main" }) ?? null,
  detailKey: popup.subViewKey({ kind: "detail", appid: "1" }) ?? null,
  backupsKey: popup.subViewKey({ kind: "backups", appid: "1" }) ?? null,
  excludedKey: popup.subViewKey({ kind: "excluded" }) ?? null,
  firstChildIsBack: !!(subButtons[0] && /^BACK\b/.test(subButtons[0].label)),
  backHasPreferredFocus: !!(findAll(sub, "DialogButton")[0] || {}).node
    ? !!findAll(sub, "DialogButton")[0].node.props.preferredFocus
    : false,
  backCalls: backCalls.length,
  hasOnCancelButton: !!(subFocusable && typeof subFocusable.node.props.onCancelButton === "function"),
  cancelDescription: subFocusable ? subFocusable.node.props.onCancelActionDescription : null,
  bodyRendered: texts(sub).includes("SUB_BODY"),
};

// ── ③ 두 렌더러가 같은 spec을 같은 요소로 ────────────────────────────────────
function renderNested(spec) {
  const hostInstance = makeHost(() => h(popup.SpecConfirmModal, { spec, closeModal }));
  return { host: hostInstance, node: hostInstance.render() };
}
function renderFallback(spec, onClose) {
  const hostInstance = makeHost(() => h(popup.ConfirmOverlay, { spec, onClose: onClose || (() => {}) }));
  return { host: hostInstance, node: hostInstance.render() };
}

const plainFired = [];
const plainSpec = specs.makeSaveConfirmSpec(
  { size: 1234, sha1_short: "abc0123", saved_at: "", disk_state: "unknown", confirm_token: "T" },
  "dock",
  () => plainFired.push(1),
);
const nestedPlain = renderNested(plainSpec);
const fallbackPlain = renderFallback(plainSpec);

/** 입력형 확인창 하나를 두 렌더러에서 주행한다 — 타이핑·OK 값·비활성 전이를 같이 잰다. */
function driveInput(spec, typed) {
  const nested = renderNested(spec);
  const fallback = renderFallback(spec, () => {});
  const nestedField = find(nested.node, "TextField");
  const fallbackField = find(fallback.node, "TextField");
  const confirmModal = find(nested.node, "ConfirmModal");
  const before = {
    nestedValue: nestedField ? nestedField.node.props.value : null,
    fallbackValue: fallbackField ? fallbackField.node.props.value : null,
    nestedOkDisabled: confirmModal ? !!confirmModal.node.props.bOKDisabled : null,
    fallbackOkDisabled: buttons(fallback.node)[0] ? buttons(fallback.node)[0].disabled : null,
  };
  // 타이핑 — 두 렌더러 각각에 같은 입력을 준다
  if (nestedField) nestedField.node.props.onChange({ target: { value: typed } });
  if (fallbackField) fallbackField.node.props.onChange({ target: { value: typed } });
  const nestedAfter = nested.host.output;
  const fallbackAfter = fallback.host.output;
  const after = {
    nestedValue: find(nestedAfter, "TextField").node.props.value,
    fallbackValue: find(fallbackAfter, "TextField").node.props.value,
    nestedOkDisabled: !!find(nestedAfter, "ConfirmModal").node.props.bOKDisabled,
    fallbackOkDisabled: buttons(fallbackAfter)[0].disabled,
  };
  return { nested, fallback, before, after, nestedAfter, fallbackAfter };
}

const resetValues = [];
const resetSnapshots = [];
const resetSpec = specs.makeResetConfirmSpec(
  { confirm_token: "T", games: 3, profiles: 6, named: 1, excluded: 2, challenge: "delete" },
  "",
  (v) => resetValues.push(v),
  (v) => resetSnapshots.push(v),
);
const resetRun = driveInput(resetSpec, "delete");

const nameValues = [];
const nameSnapshots = [];
const nameSpec = specs.makeNameEditSpec(
  { profile: "dock", current: "PROFILE_DOCK", initial: "" },
  (v) => nameValues.push(v),
  (v) => nameSnapshots.push(v),
);
const nameRun = driveInput(nameSpec, "새 이름");

// OK를 누른다 — 값이 실려 나가는가 · **두 번 눌러도 한 번만** 나가는가(D-05 ②)
const resetOK = find(resetRun.nestedAfter, "ConfirmModal").node.props.onOK;
resetOK(); resetOK();
const nameOK = buttons(nameRun.fallbackAfter)[0].onClick;
nameOK(); nameOK();

// plain 스펙: OK 인자가 없어야 하고(무인자 시그니처), 취소는 onOK를 부르지 않는다
const plainOK = find(nestedPlain.node, "ConfirmModal").node.props.onOK;
plainOK();
const plainCancelBtn = buttons(fallbackPlain.node)[1];
if (plainCancelBtn && plainCancelBtn.onClick) plainCancelBtn.onClick();

const gateReport = {
  anchorFound,
  plainNestedTexts: texts(nestedPlain.node),
  plainFallbackTexts: texts(fallbackPlain.node),
  resetNestedTexts: texts(resetRun.nested.node),
  resetFallbackTexts: texts(resetRun.fallback.node),
  nameNestedTexts: texts(nameRun.nested.node),
  nameFallbackTexts: texts(nameRun.fallback.node),
  resetBefore: resetRun.before,
  resetAfter: resetRun.after,
  nameBefore: nameRun.before,
  nameAfter: nameRun.after,
  resetValues,
  nameValues,
  plainFired: plainFired.length,
  // 입력형은 최소 폭을 준다(§4-D · lsfg 선례) — 비입력형에는 없다
  inputMinWidth: (() => {
    const desc = find(resetRun.nested.node, "ConfirmModal").node.props.strDescription;
    return desc && desc.props && desc.props.style ? desc.props.style.minWidth : null;
  })(),
  plainMinWidth: (() => {
    const desc = find(nestedPlain.node, "ConfirmModal").node.props.strDescription;
    return desc && desc.props && desc.props.style ? desc.props.style.minWidth || null : null;
  })(),
  // 중첩 렌더러는 closeModal을 (1회 래퍼를 씌워) ConfirmModal에 넘긴다(D-05 ①)
  closeModalForwarded: typeof find(nestedPlain.node, "ConfirmModal").node.props.closeModal === "function",
};

// ── ③″ 모달 생명주기 방어 (D-05 ②③ — 2026-08-12 게이트 C3) ──────────────────
//
// 실물 `ConfirmModal`은 OK·취소 **각각의 경로에서 스스로** `closeModal`을 부른다. 우리 게이트도
// 닫으므로, 래퍼가 없으면 한 창에 대해 닫기가 두 번 발화한다 — 그 사이 다른 모달이 떠 있으면
// **남의 창을 닫는다.** 그리고 `onOK`가 동기적으로 던지면 닫기가 건너뛰어져 **아무 버튼도 안
// 듣는 창**이 남는다. 둘 다 여기서 잰다.
const lifecycle = (() => {
  // (a) 중첩 — 우리 닫기 + ConfirmModal 자기 닫기 + 이중 탭 = 실제 닫기 1회
  let closes = 0;
  const fired = [];
  const spec = { ...plainSpec, onOK: () => fired.push(1) };
  const hostA = makeHost(() => h(popup.SpecConfirmModal, { spec, closeModal: () => { closes += 1; } }));
  hostA.render();
  const modal = () => find(hostA.output, "ConfirmModal").node.props;
  const cancelDisabledBefore = !!modal().bCancelDisabled;
  modal().onOK();                    // 우리 게이트가 닫는다
  modal().closeModal();              // 실물 ConfirmModal이 자기 경로로 또 닫는다
  modal().onOK();                    // 이중 탭
  const nestedCloses = closes;
  const cancelDisabledAfter = !!modal().bCancelDisabled;

  // (b) 폴백 — OK를 누르면 오버레이가 닫힌다(정확히 1회)
  let overlayCloses = 0;
  const fb = renderFallback({ ...plainSpec, onOK: () => {} }, () => { overlayCloses += 1; });
  const okBtn = buttons(fb.node)[0];
  okBtn.onClick();
  okBtn.onClick();
  const fallbackCloses = overlayCloses;

  // (c) `onOK`가 **던져도** 창은 닫힌다(try/finally)
  let throwCloses = 0;
  let threw = false;
  const boom = { ...plainSpec, onOK: () => { throw new Error("주입: onOK 실패"); } };
  const hostC = makeHost(() => h(popup.SpecConfirmModal, { spec: boom, closeModal: () => { throwCloses += 1; } }));
  hostC.render();
  try {
    find(hostC.output, "ConfirmModal").node.props.onOK();
  } catch (err) {
    threw = true;                    // 예외는 삼키지 않는다 — 진단은 위로 올라가야 한다
  }
  let overlayThrowCloses = 0;
  const fbBoom = renderFallback(boom, () => { overlayThrowCloses += 1; });
  try {
    buttons(fbBoom.node)[0].onClick();
  } catch (err) { /* 위와 같다 */ }

  // (d) **취소** — 닫기는 정확히 1회이고 `onOK`는 **한 번도** 안 나간다(단일 종료의 반대쪽).
  //     취소 뒤의 OK·이중 탭까지 눌러 본다: 계약이 한쪽 방향으로만 성립하면 그건 우연이다.
  let cancelCloses = 0;
  const cancelFired = [];
  const cancelSpec = { ...plainSpec, onOK: () => cancelFired.push(1) };
  const hostD = makeHost(() => h(popup.SpecConfirmModal,
    { spec: cancelSpec, closeModal: () => { cancelCloses += 1; } }));
  hostD.render();
  const modalD = () => find(hostD.output, "ConfirmModal").node.props;
  modalD().onCancel();                 // 취소
  modalD().closeModal();               // 실물 ConfirmModal이 자기 경로로 또 닫는다
  modalD().onCancel();                 // 이중 탭
  modalD().onOK();                     // 취소 뒤의 확인 — 없던 일이어야 한다

  // (e) **폴백 렌더러의 B(취소 배선)** — 같은 계약이 다른 렌더러에서도 성립하는가.
  let overlayCancelCloses = 0;
  const overlayFired = [];
  const fbCancel = renderFallback({ ...plainSpec, onOK: () => overlayFired.push(1) },
    () => { overlayCancelCloses += 1; });
  const overlayCancel = find(fbCancel.node, "Focusable").node.props.onCancelButton;
  if (overlayCancel) { overlayCancel(); overlayCancel(); }
  buttons(fbCancel.node)[0].onClick();  // 취소 뒤 OK 버튼

  return {
    nestedCloses,
    okFiredOnce: fired.length,
    cancelDisabledBefore,
    cancelDisabledAfter,
    fallbackCloses,
    throwClosedNested: throwCloses,
    throwClosedFallback: overlayThrowCloses,
    throwPropagated: threw,
    cancelCloses,
    cancelOkFired: cancelFired.length,
    overlayCancelWired: !!overlayCancel,
    overlayCancelCloses,
    overlayCancelOkFired: overlayFired.length,
  };
})();

// ── ③′ spec화 전후 동일성(신구 렌더 대조) — **은퇴**(P15) ──────────────────
//
// 이 자리에는 전체 화면 시절의 확인창 컴포넌트(구 「현황」·「관리」·「게임 추가」 화면과
// 저장 확인창 파일에 살던 7종)와 spec을 **같은 파라미터로 각각 렌더해** 대조하는 26조합
// 검사가 있었다. 그 컴포넌트들이
// P15에서 삭제되어 **비교 대상 자체가 사라졌다** — 예고된 처분(P12 게이트 C4 · 설계 §12)대로
// 은퇴한다. "옮기는 동안 잃은 것이 없다"는 이 검사의 유일한 일이었고, 그 이사는 끝났다.
//
// ⚠️ 스냅샷 고정으로 바꾸지 않는 이유: 신 코드끼리의 대조는 ③(양 렌더러 동일성)이 이미
//   하고 있고, spec 문구 자체는 `test_wording_10a`(값 바이트 고정)와 팝업별 프로브가 잡는다.
//   여기서 렌더 결과를 다시 박제하면 **문구를 고칠 때마다 갱신해야 하는 사본**이 하나 더
//   생길 뿐이다(고정 대상이 늘면 계획된 개정을 검사가 막는다 — 이월 대장 #10과 같은 성질).


// ── ④ 게이트 두 모드 + 실패 note ─────────────────────────────────────────────
function driveGate(mod, spec) {
  const notes = [];
  const gateHost = makeHost(() => {
    const gate = mod.usePopupGate();
    return { gate, body: gate.renderBody(h("div", null, "ORIGINAL_CONTENT")) };
  });
  let state = gateHost.render();
  state.gate.gate(spec, "MODAL_FAILED", (msg) => notes.push(msg));
  state = gateHost.output;
  return { host: gateHost, state, notes };
}

shownModals.length = 0;
const nestedGate = driveGate(popup, plainSpec);
const nestedGateReport = {
  modalsShown: shownModals.length,
  // 띄운 것이 같은 spec을 든 SpecConfirmModal인가(게이트가 spec을 그대로 넘겼는가)
  modalIsSpecConfirm: !!(shownModals[0] && shownModals[0].name === "SpecConfirmModal"),
  modalSpecIsSame: !!(shownModals[0] && shownModals[0].props.spec === plainSpec),
  overlayShown: !!nestedGate.state.gate.overlay,
  // 중첩 모드에서는 원 콘텐츠가 그대로 남는다
  bodyTexts: texts(nestedGate.state.body),
  notes: nestedGate.notes,
};

shownModals.length = 0;
const fallbackGate = driveGate(popupFallback, plainSpec);
const fallbackBodyTexts = texts(fallbackGate.state.body);
// 폴백 오버레이를 닫으면 원 콘텐츠가 돌아온다
const overlayClose = find(fallbackGate.state.body, "Focusable");
const fallbackCancelBtn = buttons(fallbackGate.state.body)[1];
if (fallbackCancelBtn && fallbackCancelBtn.onClick) fallbackCancelBtn.onClick();
const fallbackAfterClose = texts(fallbackGate.host.output.body);

const fallbackGateReport = {
  modalsShown: shownModals.length,
  overlayShown: !!fallbackGate.state.gate.overlay,
  bodyTexts: fallbackBodyTexts,
  // ★ D-05 ⑤: 오버레이가 떠 있는 동안 원 콘텐츠는 **렌더되지 않는다**(숨김이 아니라 미렌더)
  originalContentRendered: fallbackBodyTexts.includes("ORIGINAL_CONTENT"),
  restoredAfterClose: fallbackAfterClose.includes("ORIGINAL_CONTENT"),
  overlayHasCancelButton: !!(overlayClose && typeof overlayClose.node.props.onCancelButton === "function"),
};

// 게이트 실패 — showModal이 죽으면 **failKey 경유 문구**가 화면에 뜨고 onOK는 안 나간다
shownModals.length = 0;
modalThrows = true;
const failFired = [];
const failSpec = { ...plainSpec, onOK: () => failFired.push(1) };
const failGate = driveGate(popup, failSpec);
modalThrows = false;
const failureReport = {
  notes: failGate.notes,
  okFired: failFired.length,
  overlayShown: !!failGate.state.gate.overlay,
};

// ── ⑤ 데이터 로드·자체 재조회 ────────────────────────────────────────────────
const loadCalls = [];
let envelope = {
  ok: true,
  data: { games: [], profile_names: { dock: "독", internal: "내장" } },
};
const dataHost = makeHost(() => {
  const state = popup.usePopupData(() => {
    loadCalls.push(1);
    return Promise.resolve(envelope);
  }, "LOAD_FAILED");
  return state;
});
let dataState = dataHost.render();

const dataReport = { mountCalls: loadCalls.length };
const settle = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  await settle();
  dataState = dataHost.output;
  dataReport.dataArrived = !!dataState.data;
  // R-6: profile_names는 **상태 반영보다 먼저** i18n에 실린다
  dataReport.profileNamesTaken = profileNameCalls.length;
  dataReport.profileNamesValue = profileNameCalls[0] || null;

  // 자체 재조회(변이 성공 뒤 팝업이 스스로 부른다)
  dataState.reload();
  await settle();
  dataReport.afterReloadCalls = loadCalls.length;

  // 실패 봉투 → note는 tCode(failKey) 경유
  envelope = { ok: false, code: "REGISTRY_UNREADABLE", params: {} };
  dataHost.output.reload();
  await settle();
  dataReport.noteOnFail = dataHost.output.noteText;

  // ── ⑥ 입력값 보존 (GP#9) ───────────────────────────────────────────────────
  // 언마운트 시 스냅샷이 나가고, 그 값을 initial로 되돌리면 화면이 복원된다.
  // 두 렌더러를 각각 언마운트한다 — **렌더러마다 자기 값이** 나가야 한다(둘 다 1회씩).
  resetRun.nested.host.unmount();
  resetRun.fallback.host.unmount();
  nameRun.nested.host.unmount();
  nameRun.fallback.host.unmount();
  const snapshot = resetSnapshots[resetSnapshots.length - 1];
  const restoredSpec = specs.makeResetConfirmSpec(
    { confirm_token: "T", games: 3, profiles: 6, named: 1, excluded: 2, challenge: "delete" },
    snapshot || "",
    () => {},
  );
  const restored = renderNested(restoredSpec);
  const snapshotReport = {
    snapshots: resetSnapshots,
    nameSnapshots,
    restoredInitial: find(restored.node, "TextField").node.props.value,
  };

  // ── ⑤′ §4-F 개정: 세대 가드 · busy 문 하나 · 확정 실행 재조회 규칙 ─────────
  //
  // 여기서 재는 것은 **훅 자체**다. 팝업 화면을 거치지 않는 이유: 이 계약은 세 팝업이
  // 상속하는 한 벌이고, 화면을 통해서만 재면 *"그 화면이 마침 그렇게 생겼을 뿐"*인 통과가
  // 섞인다(팝업별 관측은 `test_games_popup`의 busy·확정 실행 실패 판정이 맡는다).

  /** 응답을 **손에 쥔 채** 부르는 조회 — 세대·busy는 그 순간에만 관측된다. */
  function heldLoader(sink) {
    return () => new Promise((resolve) => { sink.push(resolve); });
  }
  const okEnv = (tag) => ({ ok: true, data: { tag } });

  function mountData(loader, onMutate) {
    const host = makeHost(() => popup.usePopupData(loader, "LOAD_FAILED", onMutate));
    host.render();
    return host;
  }

  // ⓐ 세대 가드 — **역순 완료**: 나중에 부른 조회가 먼저 도착하고, 옛 응답이 뒤늦게 온다.
  const genSink = [];
  const genHost = mountData(heldLoader(genSink));
  await settle();
  genHost.output.reload();
  await settle();
  genSink[1](okEnv("NEW"));                     // 새 세대가 먼저 도착
  await settle();
  const genMid = genHost.output.data;
  genSink[0](okEnv("OLD"));                     // 옛 세대가 뒤늦게 도착 — 버려져야 한다
  await settle();
  const generationReport = {
    loads: genSink.length,
    afterNew: genMid ? genMid.tag : null,
    afterStale: genHost.output.data ? genHost.output.data.tag : null,
    staleNote: genHost.output.noteText,
  };

  // ⓐ′ 낡은 **실패** 응답도 버린다 — 아니면 성공한 화면 밑에 옛 실패 사유가 뜬다.
  const genSink2 = [];
  const genHost2 = mountData(heldLoader(genSink2));
  await settle();
  genHost2.output.reload();
  await settle();
  genSink2[1](okEnv("NEW"));
  await settle();
  genSink2[0]({ ok: false, code: "REGISTRY_UNREADABLE", params: {} });
  await settle();
  generationReport.staleFailNote = genHost2.output.noteText;
  generationReport.staleFailData = genHost2.output.data ? genHost2.output.data.tag : null;

  // ⓑ busy — 마운트 조회 중에 이미 켜져 있고, 겹친 왕복이 **다 끝나야** 열린다.
  const busySink = [];
  const busyHost = mountData(heldLoader(busySink));
  const busyReport = { onMount: busyHost.output.busy };
  busySink[0](okEnv("A"));
  await settle();
  busyReport.afterLoad = busyHost.output.busy;
  // 변이 하나와 조회 하나를 **겹친다**: 변이가 먼저 끝나도 조회가 남아 있으면 잠긴 채여야 한다.
  const mutSink = [];
  void busyHost.output.runMutation(() => new Promise((r) => mutSink.push(r)), "ACT_FAILED", () => {});
  await settle();
  busyReport.duringMutation = busyHost.output.busy;
  busyHost.output.reload();
  await settle();
  mutSink[0]({ ok: true, data: {} });
  await settle();
  busyReport.whileReloadPending = busyHost.output.busy;   // 조회가 남았다 — 아직 잠김
  // 남은 조회를 전부 흘려보낸다(변이 성공이 붙인 자동 재조회까지) — 그래야 문이 다시 열린다.
  for (let guard = 0; guard < 5 && busyHost.output.busy; guard += 1) {
    busySink.splice(0).forEach((resolve) => resolve(okEnv("B")));
    await settle();
  }
  busyReport.afterAll = busyHost.output.busy;

  // ⓒⓓ 문의 규칙 — 응답 종류별로 재조회·통지가 붙는지.
  const OUTCOMES = {
    ok: () => Promise.resolve({ ok: true, data: { tag: "X" } }),
    fail: () => Promise.resolve({ ok: false, code: "DELETE_FAILED", params: {} }),
    token: () => Promise.resolve({ ok: false, code: "CONFIRM_REQUIRED", params: { confirm_token: "T" } }),
    reject: () => Promise.reject(new TypeError("rpc died")),
  };
  const doorReport = {};
  for (const mode of ["runMutation", "runQuery"]) {
    for (const [name, call] of Object.entries(OUTCOMES)) {
      const loads = [];
      const mutations = [];
      const host = mountData(
        () => { loads.push(1); return Promise.resolve(okEnv("BASE")); },
        () => { mutations.push(1); },
      );
      await settle();
      const seen = [];
      await host.output[mode](call, "ACT_FAILED", (res) => { seen.push(!!res.ok); });
      await settle();
      doorReport[`${mode}.${name}`] = {
        reloads: loads.length - 1,           // 마운트 1회는 뺀다
        mutations: mutations.length,
        results: seen,                        // 거절이면 onResult는 안 불린다
        note: host.output.noteText,
      };
    }
  }

  // ── ⑦ R4: **변이 성공 + 재조회 실패는 둘 다 참**이다 ──────────────────────
  //
  // 예전에는 재조회 실패가 성공 note와 **같은 자리**를 덮어써서, 후속 조치 안내
  // (`RESTORE_OK_MANUAL`·`DELETE_FAILED`·`SAVE_OK`+warning·`RESET_LEFT_NOTE`)가 통째로
  // 사라졌다 — 사용자는 *"복원했으니 이 게임의 프로필로 저장하라"*는 다음 걸음을 잃는다.
  const bothNotes = await (async () => {
    let loads = 0;
    let loadOk = true;
    const host = makeHost(() => popup.usePopupData(() => {
      loads += 1;
      return Promise.resolve(loadOk
        ? { ok: true, data: { tag: "BASE" } }
        : { ok: false, code: "REGISTRY_UNREADABLE", params: {} });
    }, "LOAD_FAILED"));
    host.render();
    await settle();
    loadOk = false;                                   // 이제부터 재조회가 실패한다
    await host.output.runMutation(
      () => Promise.resolve({ ok: true, data: {} }),
      "ACT_FAILED",
      () => { host.output.setNote("RESTORE_OK_MANUAL"); },
    );
    await settle();
    await settle();
    return {
      loads,
      texts: texts(host.output.noteView),
      noteText: host.output.noteText,
      // 재조회가 실패했으니 **데이터는 옛것 그대로**여야 한다(모르는 값으로 덮지 않는다).
      data: host.output.data ? host.output.data.tag : null,
    };
  })();

  // ── ⑧ R8: 호출이 **동기적으로 던져도** 문은 닫힌다 ────────────────────────
  //
  // `begin()` 뒤에 `.finally(end)`를 이어 붙이는 구조에서는, `call`이 그 자리에서 던지면
  // `.finally`가 **부착되기 전에** 스택을 빠져나가 busy가 영구히 잠긴다(아무 버튼도 안 듣는 팝업).
  const syncThrow = await (async () => {
    const host = makeHost(() => popup.usePopupData(
      () => Promise.resolve({ ok: true, data: { tag: "BASE" } }), "LOAD_FAILED"));
    host.render();
    await settle();
    let propagated = false;
    try {
      void host.output.runMutation(
        () => { throw new TypeError("callable is not a function"); },
        "ACT_FAILED",
        () => {},
      );
    } catch (err) {
      propagated = true;      // 클릭 핸들러 밖으로 새어 나갔다 — 화면은 아무 말도 못 한다
    }
    await settle();
    await settle();
    return { propagated, busy: host.output.busy, note: host.output.noteText };
  })();

  console.log(JSON.stringify({
    bothNotes,
    syncThrow,
    skeleton: skeletonReport,
    views: viewReport,
    gate: gateReport,
    lifecycle,
    nestedGate: nestedGateReport,
    fallbackGate: fallbackGateReport,
    failure: failureReport,
    data: dataReport,
    snapshot: snapshotReport,
    generation: generationReport,
    busy: busyReport,
    door: doorReport,
  }));
})();
