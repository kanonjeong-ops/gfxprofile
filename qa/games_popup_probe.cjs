"use strict";
/**
 * 팝업 G(설계 §5)의 목록·상세 계약을 **렌더+클릭으로** 잰다 — `qa/test_games_popup.py`가 판정한다.
 *
 * 왜 렌더+클릭인가: 이 프로젝트에서 **거짓 검사가 여섯 번** 났고 그중 둘이 *"grep이 규칙을
 * 설명한 주석을 잡았다"*였다. 별칭·헬퍼·파생 변수를 가리지 않는 판정은 **눌러 보고 무슨 일이
 * 나는지 보는 것**뿐이다.
 *
 * ★ 실행: node qa/games_popup_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 *   소스디렉터리 인자는 **음성 대조군용**이다 — 사본에 위반을 주입해 같은 프로브를 돌린다.
 */
const path = require("path");
const { makeHost, h, find, findAll, texts, buttons, makeLoader, react, settle } =
  require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ── 합성 데이터 ──────────────────────────────────────────────────────────────
//
// 네 게임이 **서로 다른 갈래**를 하나씩 맡는다 — 한 갈래만 있으면 검사가 그 갈래만 보고 통과한다.
const game = (over) => Object.assign({
  appid: "0", name: "?", has_dock: false, has_internal: false, disk_matches: null,
  backups: 0, config_path: "", profiles_identical: false,
  saved_at: { dock: "", internal: "" }, last_applied: null, cloud_synced: false, running: false,
}, over);

const GAMES = [
  // 이름순이 아닌 순서로 준다 — 화면이 정렬하는지 보려면 입력이 흐트러져 있어야 한다.
  game({ appid: "300", name: "Zeta", has_dock: true, has_internal: true, disk_matches: "dock",
         backups: 2, config_path: "/cfg/zeta.ini", saved_at: { dock: "2026-08-10 09:00", internal: "2026-08-09 08:00" } }),
  game({ appid: "100", name: "Alpha", has_dock: true, has_internal: false, backups: 0, running: true }),
  game({ appid: "200", name: "Mid", has_dock: true, has_internal: true, backups: 1,
         config_path: "/cfg/mid.ini", profiles_identical: true }),
  game({ appid: "400", name: "Empty" }),
];
const COUNTS = { total: 4, dock_ready: 3, internal_ready: 2, running: 1, incomplete: 2, excluded: 2 };

/** 시나리오마다 갈아 끼우는 상태. 모듈 목은 **제자리 갱신**으로 이것을 읽는다. */
const SCENE = {
  games: GAMES,
  counts: COUNTS,
  overviewOk: true,
  applyResult: null,
  saveResult: null,
  deleteResult: null,
  /** 조회 응답을 **손에 쥐고 있는다** — busy가 켜져 있는 그 순간의 화면을 재기 위해서다. */
  holdOverview: false,
};

/** 붙잡아 둔 조회 응답을 놓아 주는 손잡이(없으면 붙잡은 조회가 없다는 뜻이다). */
let releaseOverview = null;

const calls = { overview: [], apply: [], save: [], del: [], list: [] };
const shownModals = [];
const mutations = [];

function resetCalls() {
  Object.values(calls).forEach((a) => { a.length = 0; });
  shownModals.length = 0;
  mutations.length = 0;
}

const overviewEnvelope = () => (SCENE.overviewOk
  ? { ok: true, data: { games: SCENE.games, counts: SCENE.counts, profile_names: { dock: "", internal: "" } } }
  : { ok: false, code: "REGISTRY_UNREADABLE", params: {} });

const modules = {
  react,
  "./deckyui": {
    ConfirmModal: { __kind: "ConfirmModal" },
    DialogBody: { __kind: "DialogBody" },
    DialogButton: { __kind: "DialogButton" },
    DialogHeader: { __kind: "DialogHeader" },
    Focusable: { __kind: "Focusable" },
    ModalRoot: { __kind: "ModalRoot" },
    NavEntryPositionPreferences: { MAINTAIN_X: 2 },
    TextField: { __kind: "TextField" },
    ToggleField: { __kind: "ToggleField" },
    showModal: (node) => { shownModals.push(node); },
  },
  "./i18n": {
    // 키를 그대로 돌려준다 — 렌더 대조가 언어에 묶이지 않게. (값의 규율은 `test_wording_a5`.)
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: () => {},
  },
  "./rpc": {
    getOverview: (...a) => {
      calls.overview.push(a);
      if (!SCENE.holdOverview) return Promise.resolve(overviewEnvelope());
      return new Promise((resolve) => { releaseOverview = () => resolve(overviewEnvelope()); });
    },
    applyProfile: (...a) => { calls.apply.push(a); return Promise.resolve(SCENE.applyResult); },
    saveProfile: (...a) => { calls.save.push(a); return Promise.resolve(SCENE.saveResult(a)); },
    deleteGame: (...a) => { calls.del.push(a); return Promise.resolve(SCENE.deleteResult(a)); },
    listBackups: (...a) => { calls.list.push(a); return Promise.resolve({ ok: true, data: { backups: [] } }); },
    restoreBackup: () => new Promise(() => {}),
    setProfileName: () => new Promise(() => {}),
    resetAll: () => new Promise(() => {}),
  },
};

const load = makeLoader(srcDir, modules);
const { GamesPopup } = load("GamesPopup.tsx");

/** 팝업 하나를 띄운다. 반환값의 `ui()`가 **지금 화면**이다. */
function mount() {
  const host = makeHost(() => h(GamesPopup, { onMutate: () => mutations.push(1) }));
  host.render();
  return { host, ui: () => host.output };
}

const label = (b) => b.label;
const byPrefix = (root, re) => buttons(root).filter((b) => re.test(b.label));

/**
 * 지금 화면이 어디든 **목록 뷰까지 되돌아간다.**
 *
 * ★ 왜 필요한가: 음성 대조군은 화면을 일부러 망가뜨린다("삭제 뒤 상세에 머무름" 등). 그때
 *   프로브가 **죽으면** 판정부는 "검출 실패"가 아니라 "실행 실패"를 보게 되고, 그 둘은 다르다 —
 *   위반을 심었는데 검사가 죽는 것은 **검출이 아니다.** 각 시나리오를 같은 자리에서 시작시킨다.
 */
function toList(ui) {
  for (let guard = 0; guard < 5; guard += 1) {
    const back = byPrefix(ui(), /^BACK\b/)[0];
    if (!back) return true;
    back.onClick();
  }
  return !byPrefix(ui(), /^BACK\b/)[0];
}

/** 카드의 게임명 순서 — 이름 노드는 `NAME_STYLE`의 ellipsis로 식별한다. */
function cardNames(root) {
  const out = [];
  findAll(root, "div").forEach(({ node }) => {
    const style = node.props.style || {};
    if (style.textOverflow === "ellipsis" && typeof node.children[0] === "string") {
      out.push(node.children[0]);
    }
  });
  return out;
}

/** 적용 버튼 하나의 관측면 — 폭·비활성·마커·아이콘 자리. */
function applyFace(b) {
  const slots = [];
  findAll(b.node, "span").forEach(({ node }) => {
    const style = node.props.style || {};
    if (style.width) slots.push(style.width);
  });
  return {
    label: b.label,
    disabled: b.disabled,
    minWidth: (b.style || {}).minWidth,
    marked: findAll(b.node, "IconCheck").length > 0,
    background: (b.style || {}).background || null,
    slots,
  };
}

(async () => {
  const out = {};

  // ═══ ① 목록: 정렬·마커·비활성·running 칩·제외 안내 ═══════════════════════
  resetCalls();
  const main = mount();
  await settle();
  out.mountOverviewCalls = calls.overview.length;
  out.mountDetail = (calls.overview[0] || [])[0];         // detail=true여야 disk_matches가 온다
  out.listOrder = cardNames(main.ui());
  out.applyFaces = byPrefix(main.ui(), /^APPLY_SHORT/).map(applyFace);
  out.listTexts = texts(main.ui());
  out.chevrons = byPrefix(main.ui(), /^$/).length;        // 라벨 없는 버튼(= ›)
  out.runningChipCount = out.listTexts.filter((x) => x === "RUNNING_CHIP").length;
  out.excludedNote = out.listTexts.filter((x) => /^GAMES_EXCLUDED_NOTE/.test(x));

  // ═══ ② 필터 술어 (!has_dock || !has_internal) ════════════════════════════
  const toggle = find(main.ui(), "ToggleField");
  out.toggleLabel = toggle ? toggle.node.props.label : null;
  if (toggle) toggle.node.props.onChange(true);
  out.filteredOrder = cardNames(main.ui());
  // 필터를 켠 채 상세에 들어갔다 돌아와도 **목록 상태가 살아 있는가**(GP#3의 실사용 형태)
  const chevronAfterFilter = byPrefix(main.ui(), /^$/)[0];
  if (chevronAfterFilter) chevronAfterFilter.onClick();
  const backBtn = byPrefix(main.ui(), /^BACK\b/)[0];
  if (backBtn) backBtn.onClick();
  out.filterAfterRoundTrip = find(main.ui(), "ToggleField").node.props.checked;
  out.orderAfterRoundTrip = cardNames(main.ui());
  find(main.ui(), "ToggleField").node.props.onChange(false);

  // ═══ ⑨ [다시 확인] → getOverview 재호출 ═════════════════════════════════
  const before = calls.overview.length;
  const refreshBtn = byPrefix(main.ui(), /^REFRESH\b/)[0];
  out.refreshButton = !!refreshBtn;
  if (refreshBtn) refreshBtn.onClick();
  await settle();
  out.refreshCalls = calls.overview.length - before;

  // ═══ ④·§5-E 적용: 무확인 + 체크인 고지(성공/실패 양쪽) ═══════════════════
  SCENE.applyResult = { ok: true, data: { notes: [], sha1: "x", checked_in: "internal" } };
  resetCalls();
  const applyBtns = byPrefix(main.ui(), /^APPLY_SHORT/);
  // Zeta(300)의 「내장 적용」 — 카드 순서상 마지막 게임의 두 번째 버튼이다.
  const zetaInternal = applyBtns[applyBtns.length - 1];
  zetaInternal.onClick();
  await settle();
  out.applyCall = calls.apply[0];
  out.applyModals = shownModals.length;                   // ★ 개별 적용에는 확인창이 없다
  out.applyNote = texts(main.ui()).filter((x) => /APPLY_ONE_OK|CHECKIN_ONE/.test(x));
  out.applyReloaded = calls.overview.length;
  out.applyMutations = mutations.length;

  // 실패 봉투에도 체크인이 실린다(D-02) — 화면이 그 사실에 침묵하면 안 된다.
  SCENE.applyResult = { ok: false, code: "BACKUP_FAILED", params: { checked_in: "dock" } };
  resetCalls();
  byPrefix(main.ui(), /^APPLY_SHORT/)[0].onClick();
  await settle();
  out.applyFailNote = texts(main.ui()).filter((x) => /BACKUP_FAILED|CHECKIN_ONE/.test(x));
  out.applyFailMutations = mutations.length;              // 체크인은 변이다 — QAM에 알린다

  // ═══ ③ 상세 뷰 3분기 ════════════════════════════════════════════════════
  function openDetail(name) {
    toList(main.ui);
    const names = cardNames(main.ui());
    const chevron = byPrefix(main.ui(), /^$/)[names.indexOf(name)];
    if (!chevron) return { texts: [], buttons: [] };
    chevron.onClick();
    const view = {
      texts: texts(main.ui()),
      buttons: buttons(main.ui()).map((b) => ({ label: b.label, disabled: b.disabled })),
    };
    toList(main.ui);
    return view;
  }
  out.detailZeta = openDetail("Zeta");
  out.detailMid = openDetail("Mid");
  out.detailEmpty = openDetail("Empty");

  // ═══ ④ 저장: 덮어쓰기는 확인창 · 빈 슬롯은 무확인 ════════════════════════
  SCENE.saveResult = (a) => (a[2]
    ? { ok: true, data: { meta: {}, warning: null } }
    : { ok: false, code: "CONFIRM_REQUIRED", params: {
        confirm_token: "SAVE-TOKEN", size: 12, sha1_short: "abc0123",
        saved_at: "2026-08-10 09:00", disk_state: "unknown" } });
  resetCalls();
  {
    toList(main.ui);
    const names = cardNames(main.ui());
    byPrefix(main.ui(), /^$/)[names.indexOf("Zeta")].onClick();
    const saveBtn = byPrefix(main.ui(), /^SAVE_SHORT/)[0];
    saveBtn.onClick();
    await settle();
    out.saveCall1 = calls.save[0];
    out.saveModal = shownModals.length;
    const modal = shownModals[0] ? find(shownModals[0], "ConfirmModal") : null;
    out.saveModalTexts = shownModals[0] ? texts(shownModals[0]) : [];
    if (modal) modal.node.props.onOK();
    await settle();
    out.saveCall2 = calls.save[1];
    out.saveMutations = mutations.length;
    toList(main.ui);
  }

  // 빈 슬롯 첫 저장 — 백엔드가 묻지 않으면 화면도 묻지 않는다(§15-C).
  SCENE.saveResult = () => ({ ok: true, data: { meta: {}, warning: "실행 중이라 주의" } });
  resetCalls();
  {
    toList(main.ui);
    const names = cardNames(main.ui());
    byPrefix(main.ui(), /^$/)[names.indexOf("Empty")].onClick();
    byPrefix(main.ui(), /^SAVE_SHORT/)[0].onClick();
    await settle();
    out.emptySlotSaveCalls = calls.save.length;
    out.emptySlotSaveModals = shownModals.length;
    out.emptySlotSaveNote = texts(main.ui()).filter((x) => /SAVE_OK/.test(x));
    toList(main.ui);
  }

  // ═══ §15-B ⑥ 등록 해제 안내 3종 ═════════════════════════════════════════
  async function driveDelete(configPath) {
    SCENE.deleteResult = (a) => (a[1]
      ? { ok: true, data: { appid: "300", name: "Zeta", evacuated: {}, backups: 2 } }
      : { ok: false, code: "CONFIRM_REQUIRED", params: {
          confirm_token: "DELETE-TOKEN", appid: "300", name: "Zeta",
          has_dock: true, has_internal: true, backups: 2,
          saved_at: { dock: "2026-08-10 09:00", internal: "" }, config_path: configPath } });
    resetCalls();
    toList(main.ui);
    const names = cardNames(main.ui());
    const chevron = byPrefix(main.ui(), /^$/)[names.indexOf("Zeta")];
    if (!chevron) return { call1: null, modal: null };
    chevron.onClick();
    const unregister = byPrefix(main.ui(), /^UNREGISTER_GAME\b/)[0];
    if (!unregister) return { call1: null, modal: null };
    unregister.onClick();
    // ⚠️ 확인창은 **RPC가 돌아온 뒤**에 뜬다(CONFIRM_REQUIRED는 응답이다) — 여기서 안 기다리면
    //   프로브가 "모달이 없다"고 읽고, 그 오독이 곧 거짓 검사가 된다.
    await settle();
    return { call1: calls.del[0], modal: shownModals[0] || null };
  }
  {
    const run = await driveDelete("/cfg/zeta.ini");
    out.deleteCall1 = run.call1;
    out.deleteModalTexts = run.modal ? texts(run.modal) : [];
    const modal = run.modal ? find(run.modal, "ConfirmModal") : null;
    if (modal) modal.node.props.onOK();
    await settle();
    out.deleteCall2 = calls.del[1];
    out.deleteMutations = mutations.length;
    // 성공하면 목록으로 돌아간다(상세에 남아 있으면 없는 게임을 보고 있게 된다).
    out.afterDeleteButtons = buttons(main.ui()).map(label).filter((x) => /^BACK\b/.test(x)).length;
  }
  {
    // unsafe-key 분기는 entry를 안 읽어 **빈 경로**가 온다 — 그때는 그 줄을 그리지 않는다(R-11).
    const run = await driveDelete("");
    out.deleteModalTextsNoPath = run.modal ? texts(run.modal) : [];
    const modal = run.modal ? find(run.modal, "ConfirmModal") : null;
    if (modal) modal.node.props.onCancel();
    toList(main.ui);
  }

  // ═══ §4-F ② busy 통합 — **조회 중에도** 목록 조작이 잠긴다 ═══════════════
  //
  // 예전에는 `reload()`가 busy를 안 켜서 [다시 확인] 연타가 조회에 무방비였다(P14 O1).
  // 응답을 손에 쥔 채 화면을 찍는다 — 잠기는 순간이 곧 재는 대상이다.
  {
    toList(main.ui);
    SCENE.holdOverview = true;
    releaseOverview = null;
    resetCalls();
    const beforeBtn = byPrefix(main.ui(), /^REFRESH\b/)[0];
    out.busyBeforeReload = {
      refresh: beforeBtn.disabled,
      applies: byPrefix(main.ui(), /^APPLY_SHORT/).filter((b) => b.disabled).length,
    };
    beforeBtn.onClick();
    await settle();
    out.busyDuringReload = {
      refresh: byPrefix(main.ui(), /^REFRESH\b/)[0].disabled,
      // 전부 잠긴다(빈 슬롯 비활성과 섞이지 않게 **전수**로 본다 — 8개 중 8개)
      applies: byPrefix(main.ui(), /^APPLY_SHORT/).filter((b) => b.disabled).length,
      chevrons: byPrefix(main.ui(), /^$/).filter((b) => b.disabled).length,
      calls: calls.overview.length,
    };
    // 응답이 도착하면 문이 다시 열린다 — 잠금이 **영구**가 되면 그것도 결함이다.
    SCENE.holdOverview = false;
    if (releaseOverview) releaseOverview();
    await settle();
    out.busyAfterReload = {
      refresh: byPrefix(main.ui(), /^REFRESH\b/)[0].disabled,
      applies: byPrefix(main.ui(), /^APPLY_SHORT/).filter((b) => b.disabled).length,
    };
  }

  // ═══ §4-F ③ 확정 실행 **실패**도 재조회+통지 (이월 대장 #4) ═══════════════
  //
  // `DELETE_FAILED`는 **부분 삭제**다 — 일부는 이미 지워졌는데 화면이 낡으면 지워진 게임이
  // 목록에 그대로 남는다. 성공 경로에만 통지를 붙이던 비대칭을 여기서 잠근다.
  {
    SCENE.deleteResult = () => ({ ok: false, code: "DELETE_FAILED", params: {} });
    resetCalls();
    toList(main.ui);
    const names = cardNames(main.ui());
    byPrefix(main.ui(), /^$/)[names.indexOf("Zeta")].onClick();
    byPrefix(main.ui(), /^UNREGISTER_GAME\b/)[0].onClick();
    await settle();
    out.deleteFail = {
      note: texts(main.ui()).filter((x) => /DELETE_FAILED/.test(x)),
      modals: shownModals.length,
      reloads: calls.overview.length,
      mutations: mutations.length,
    };
    toList(main.ui);
  }

  // ═══ ③ 200게임 렌더 ═════════════════════════════════════════════════════
  SCENE.games = Array.from({ length: 200 }, (_, i) =>
    game({ appid: String(1000 + i), name: `Game ${String(i).padStart(3, "0")}`, has_dock: true, has_internal: true }));
  SCENE.counts = { total: 200, dock_ready: 200, internal_ready: 200, running: 0, incomplete: 0, excluded: 0 };
  resetCalls();
  {
    const many = mount();
    await settle();
    out.bulkCards = cardNames(many.ui()).length;
    out.bulkApplyButtons = byPrefix(many.ui(), /^APPLY_SHORT/).length;
    out.bulkExcludedNote = texts(many.ui()).filter((x) => /^GAMES_EXCLUDED_NOTE/.test(x));
  }

  // ═══ 조회 실패 — 모르는 것을 없다고 말하지 않는다(§5-D) ══════════════════
  SCENE.overviewOk = false;
  resetCalls();
  {
    const failed = mount();
    await settle();
    const seen = texts(failed.ui());
    out.failTexts = seen.filter((x) => /REGISTRY_UNREADABLE|NO_GAMES|LOADING/.test(x));
  }
  SCENE.overviewOk = true;
  SCENE.games = GAMES;
  SCENE.counts = COUNTS;

  console.log(JSON.stringify(out));
})();
