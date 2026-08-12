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
  // 현행 확인창들이 사는 파일(`ManageTab`·`DiscoverTab`)이 끌어오는 RPC — 이 프로브는
  // **확인창의 모양**만 재므로 전부 무동작 목이다(호출되면 영원히 대기하는 약속을 준다).
  "./rpc": {
    getOverview: () => new Promise(() => {}),
    listBackups: () => new Promise(() => {}),
    deleteGame: () => new Promise(() => {}),
    resetAll: () => new Promise(() => {}),
    restoreBackup: () => new Promise(() => {}),
    saveProfile: () => new Promise(() => {}),
    setProfileName: () => new Promise(() => {}),
    discoverGames: () => new Promise(() => {}),
    addGame: () => new Promise(() => {}),
    registerConfident: () => new Promise(() => {}),
  },
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

  return {
    nestedCloses,
    okFiredOnce: fired.length,
    cancelDisabledBefore,
    cancelDisabledAfter,
    fallbackCloses,
    throwClosedNested: throwCloses,
    throwClosedFallback: overlayThrowCloses,
    throwPropagated: threw,
  };
})();

// ── ③′ spec화 **전후 동일성** — 파라미터 조합별 **신구 렌더 대조** ──────────
//
// ★★ 왜 키 대조가 아니라 렌더 대조인가(2026-08-12 P12 게이트 C4): 소스에서 뽑은 **키 집합**은
//   *"어느 분기에서 어떤 값과 함께 그려지는가"*를 못 본다. 그래서 분기를 뒤집거나(빈 슬롯↔저장됨),
//   파라미터를 바꿔 넣거나, 프리필 규칙을 빠뜨려도 키 집합은 그대로라 **검사가 눈감았다**
//   (게이트가 변이로 실증했다). → 현행 컴포넌트와 spec을 **같은 파라미터로 각각 렌더해서**
//   화면에 나오는 글자·입력 초기값·OK 비활성까지 대조한다.
//
// ⚠️ 처분 예고: **P15에서 legacy 확인창 컴포넌트가 삭제되면 이 대조는 은퇴한다** —
//   그때 비교 대상이 사라지므로 스냅샷 고정으로 전환하거나 검사를 삭제한다(P15 결정).
//   그 전까지는 "옮기는 동안 잃은 것이 없다"를 잠그는 것이 이 검사의 유일한 일이다.
// ⚠️ **손실만 실패**로 본다(추가는 허용): P13이 §9·§7·§5-C의 신설 문구를 spec에 얹을 예정이라,
//   추가까지 막으면 그 단계에서 이 검사가 통째로 거짓말을 하게 된다.

/** 확인창 하나의 관측면 — 글자·입력 초기값·OK 비활성. 신구를 이 셋으로 대조한다. */
function faceOf(node) {
  const field = find(node, "TextField");
  const modal = find(node, "ConfirmModal");
  const okBtn = buttons(node)[0];
  return {
    texts: texts(node).slice().sort(),
    field: field ? field.node.props.value : null,
    okDisabled: modal ? !!modal.node.props.bOKDisabled : (okBtn ? okBtn.disabled : null),
  };
}

/** 두 렌더러(현행 컴포넌트 / spec)를 같은 파라미터로 돌려 관측면을 나란히 놓는다. */
function parityCase(label, drawLegacy, spec, typed) {
  const legacyHost = makeHost(drawLegacy);
  let legacyNode = legacyHost.render();
  const specRun = renderNested(spec);
  let specNode = specRun.node;
  if (typed !== undefined) {
    // 입력형: **같은 글자를 쳐 넣고** 다시 본다 — okDisabled의 동적 평가가 신구 같은지까지 잰다.
    const lf = find(legacyNode, "TextField");
    const sf = find(specNode, "TextField");
    if (lf) lf.node.props.onChange({ target: { value: typed } });
    if (sf) sf.node.props.onChange({ target: { value: typed } });
    legacyNode = legacyHost.output;
    specNode = specRun.host.output;
  }
  return { label, legacy: faceOf(legacyNode), spec: faceOf(specNode) };
}

const noop = () => {};
const DELETE_BASE = {
  confirm_token: "T", appid: "1", name: "Game", has_dock: true, has_internal: true,
  saved_at: { dock: "2026-08-10 09:00", internal: "2026-08-09 08:00" }, backups: 2,
  config_path: "/cfg",
};
const RESTORE_BASE = {
  appid: "1", backup_id: "b1", kind: "profile_dock", stamp: "20260810-090000",
  stamp_label: "2026-08-10 09:00", filename: "video.ini", size: 10, disk_state: "unknown",
};
const RESET_BASE = {
  confirm_token: "T", games: 3, profiles: 6, named: 1, excluded: 2, challenge: "delete",
};
const SAVE_BASE = {
  confirm_token: "T", size: 1234, sha1_short: "abc0123", saved_at: "2026-08-10T09:00:00+0900",
  disk_state: "unknown",
};

// 현행 확인창들 — `ManageTab`의 것은 **모듈 private**이라 사본에 export를 덧붙여 꺼낸다.
const legacyManage = load("ManageTab.tsx", (src) => src +
  "\nexport { DeleteConfirm, ResetConfirm, RestoreConfirm, RestoreFollowUp, NameEditModal };\n");
const legacySave = load("saveConfirm.tsx");

const parity = [];

// ① 저장(덮어쓰기) — 프로필 2 × 디스크 상태 4
[["dock"], ["internal"]].forEach(([profile]) => {
  [
    { disk_state: "other_profile", matched_profile: "dock" },
    { disk_state: "unknown" },
    { disk_state: "missing" },
    { disk_state: "lookup_failed" },
  ].forEach((variant) => {
    const params = { ...SAVE_BASE, ...variant };
    parity.push(parityCase(
      `Save[${profile}/${variant.disk_state}]`,
      () => h(legacySave.SaveConfirmModal, { params, profile, onConfirm: noop }),
      specs.makeSaveConfirmSpec(params, profile, noop),
    ));
  });
});

// ② 등록 해제 — 슬롯 유무 4조합 + 저장 시각 미상 + 백업 0건
[
  { has_dock: true, has_internal: true },
  { has_dock: false, has_internal: false, backups: 0 },
  { has_dock: true, has_internal: false, saved_at: { dock: "", internal: "" } },
  { has_dock: false, has_internal: true, backups: 0 },
].forEach((variant, i) => {
  const params = { ...DELETE_BASE, ...variant };
  parity.push(parityCase(
    `Delete[${i}]`,
    () => h(legacyManage.DeleteConfirm, { params, onConfirm: noop }),
    specs.makeDeleteConfirmSpec(params, noop),
  ));
});

// ③ 전체 초기화 — 표시명 유/무 × (입력 전 / challenge 입력 후)
[1, 0].forEach((named) => {
  const params = { ...RESET_BASE, named };
  parity.push(parityCase(
    `Reset[named=${named}]`,
    () => h(legacyManage.ResetConfirm, { params, onConfirm: noop }),
    specs.makeResetConfirmSpec(params, "", noop),
  ));
  parity.push(parityCase(
    `Reset[named=${named}/typed]`,
    () => h(legacyManage.ResetConfirm, { params, onConfirm: noop }),
    specs.makeResetConfirmSpec(params, "", noop),
    params.challenge,
  ));
});
// challenge와 다른 입력 — OK가 계속 잠겨 있어야 한다(신구 같은 판정인가)
parity.push(parityCase(
  "Reset[typed=wrong]",
  () => h(legacyManage.ResetConfirm, { params: RESET_BASE, onConfirm: noop }),
  specs.makeResetConfirmSpec(RESET_BASE, "", noop),
  "delet",
));

// ④ 복원 — 대피본 종류 4 × 디스크 상태
[
  { kind: "profile_dock", disk_state: "other_profile", matched_profile: "internal" },
  { kind: "profile_internal", disk_state: "unknown" },
  { kind: "disk", disk_state: "missing" },
  { kind: "unknown", disk_state: "lookup_failed" },
].forEach((variant) => {
  const params = { ...RESTORE_BASE, ...variant };
  parity.push(parityCase(
    `Restore[${variant.kind}]`,
    () => h(legacyManage.RestoreConfirm, { params, onConfirm: noop }),
    specs.makeRestoreConfirmSpec(params, noop),
  ));
});

// ⑤ 복원 후속 제안 — 프로필 2
["dock", "internal"].forEach((profile) => {
  parity.push(parityCase(
    `RestoreFollowUp[${profile}]`,
    () => h(legacyManage.RestoreFollowUp, { profile, onConfirm: noop }),
    specs.makeRestoreFollowUpSpec(profile, noop),
  ));
});

// ⑥ 표시 이름 편집 — ★ **프리필 규칙**(기본 이름이면 빈 칸, 사용자 이름이면 채운 채)
[
  { current: "PROFILE_DOCK", note: "기본 이름 = 빈 칸" },
  { current: "내 독", note: "사용자 이름 = 채운 채" },
].forEach(({ current }) => {
  parity.push(parityCase(
    `NameEdit[${current}]`,
    () => h(legacyManage.NameEditModal, {
      profile: "dock", current, fallback: "PROFILE_DOCK", maxLen: 20, onConfirm: noop,
    }),
    specs.makeNameEditSpec({ profile: "dock", current }, noop),
  ));
});

// ⑦ 등록 경고 — 현행은 `DiscoverTab` 안의 클로저라 **화면을 태워서** 꺼낸다.
const discoverWarn = (() => {
  const entry = {
    appid: "500", name: "Warned Game", library: "/lib", confident: true, registered: false,
    candidate_count: 1, best: { path: "/lib/x.ini", tier: 1, size: 10, mtime_label: "m" },
    candidates: [],
  };
  const warnParams = {
    confirm_token: "T", warnings: ["WARN_OUTSIDE_SCAN_ROOTS", "WARN_NOT_DISCOVER_CANDIDATE"],
    name: entry.name, config_path: entry.best.path,
  };
  modules["./filepicker"] = { pickConfigFile: () => Promise.resolve(null) };
  // ⚠️ **제자리 갱신**이다 — 새 객체로 바꾸면 이미 로드된 `ManageTab`이 옛 목을 붙든 채로 남는다.
  Object.assign(modules["./rpc"], {
    discoverGames: () => Promise.resolve({
      ok: true,
      data: {
        entries: [entry],
        counts: { total: 1, registered: 0, unregistered: 1, confident_unregistered: 1 },
        libraries: ["/lib"], excluded: [],
      },
    }),
    addGame: () => Promise.resolve({ ok: false, code: "CONFIRM_REQUIRED", params: warnParams }),
    registerConfident: () => Promise.resolve({ ok: true, data: { results: [], counts: {} } }),
  });
  const discover = load("DiscoverTab.tsx");
  const discoverHost = makeHost(() => h(discover.DiscoverTab, {}));
  discoverHost.render();
  return { host: discoverHost, warnParams };
})();

// ── ④ 게이트 두 모드 + 실패 note ─────────────────────────────────────────────

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
  dataReport.noteOnFail = dataHost.output.note;

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

  // ⑦ 등록 경고 — 화면이 데이터를 받은 뒤 [추가]를 눌러야 현행 확인창이 뜬다.
  await settle();
  const addButton = buttons(discoverWarn.host.output)
    .find((b) => /^DISCOVER_ADD\b|^DISCOVER_ADD_ONE\b/.test(b.label));
  shownModals.length = 0;
  if (addButton && addButton.onClick) addButton.onClick();
  await settle();
  const legacyWarn = shownModals[shownModals.length - 1] || null;
  parity.push({
    label: "DiscoverWarn",
    legacy: legacyWarn ? faceOf(legacyWarn) : null,
    spec: faceOf(renderNested(specs.makeDiscoverWarnSpec(discoverWarn.warnParams, noop)).node),
    // 현행 확인창을 못 꺼냈으면 **대조가 항진식**이다 — 판정부가 이 값을 보고 FAIL시킨다.
    legacyCaptured: !!legacyWarn,
    addButtonLabel: addButton ? addButton.label : null,
  });

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
    staleNote: genHost.output.note,
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
  generationReport.staleFailNote = genHost2.output.note;
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
        note: host.output.note,
      };
    }
  }

  console.log(JSON.stringify({
    skeleton: skeletonReport,
    views: viewReport,
    gate: gateReport,
    lifecycle,
    parity,
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
