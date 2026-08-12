"use strict";
/**
 * 팝업 S(설계 §7)의 계약을 **렌더+클릭으로** 잰다 — `qa/test_settings_popup.py`가 판정한다.
 *
 * 핵심은 **[전체 초기화]의 활성 조건**(D-01): `total > 0 || excluded > 0`.
 * 마지막 게임을 등록 해제하면 `total=0`인데 감지 제외 목록은 남는다 — `total`만 보면 그 목록을
 * 지울 방법이 화면에서 사라져 A9 ④가 도달 불가가 된다.
 *
 * ★ 실행: node qa/settings_popup_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 */
const path = require("path");
const { makeHost, h, find, findAll, texts, buttons, makeLoader, react, settle } =
  require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

const counts = (total, excluded) => ({
  total, dock_ready: total, internal_ready: total, running: 0, incomplete: 0, excluded,
});

const SCENE = {
  counts: counts(2, 0),
  overviewOk: true,
  hang: false,                       // 응답이 영영 안 오는 상태(=로딩 중)
  profileNames: { dock: "", internal: "" },
  resetResult: null,
};

const calls = { overview: [], reset: [], rename: [] };
const shownModals = [];
const mutations = [];
const nameSyncs = [];

function resetCalls() {
  Object.values(calls).forEach((a) => { a.length = 0; });
  shownModals.length = 0;
  mutations.length = 0;
}

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
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: (v) => { nameSyncs.push(v); },
  },
  "./rpc": {
    getOverview: (...a) => {
      calls.overview.push(a);
      if (SCENE.hang) return new Promise(() => {});
      return Promise.resolve(SCENE.overviewOk
        ? { ok: true, data: { games: [], counts: SCENE.counts, profile_names: SCENE.profileNames } }
        : { ok: false, code: "REGISTRY_UNREADABLE", params: {} });
    },
    resetAll: (...a) => { calls.reset.push(a); return Promise.resolve(SCENE.resetResult(a)); },
    setProfileName: (...a) => {
      calls.rename.push(a);
      return Promise.resolve({ ok: true, data: { profile_names: { dock: a[1] || "", internal: "" } } });
    },
    applyProfile: () => new Promise(() => {}),
    saveProfile: () => new Promise(() => {}),
    deleteGame: () => new Promise(() => {}),
    listBackups: () => new Promise(() => {}),
    restoreBackup: () => new Promise(() => {}),
  },
};

const load = makeLoader(srcDir, modules);
const { SettingsPopup } = load("SettingsPopup.tsx");
const popup = load("popup.tsx");

function mount() {
  const host = makeHost(() => h(SettingsPopup, { onMutate: () => mutations.push(1) }));
  host.render();
  return { host, ui: () => host.output };
}

const byPrefix = (root, re) => buttons(root).filter((b) => re.test(b.label));
const resetButton = (root) => byPrefix(root, /^RESET_OPEN\b/)[0];

/** 화면 상태 하나의 관측면 — 초기화 버튼의 활성과 카운트 문구. */
async function snapshotState(cfg) {
  Object.assign(SCENE, cfg);
  resetCalls();
  const ui = mount();
  await settle();
  const btn = resetButton(ui.ui());
  const seen = texts(ui.ui());
  return {
    hasButton: !!btn,
    enabled: btn ? !btn.disabled : null,
    zone: seen.filter((x) => /^RESET_ZONE_BODY/.test(x)),
    note: seen.filter((x) => /REGISTRY_UNREADABLE/.test(x)),
  };
}

(async () => {
  const out = {};

  // ═══ 활성 조건 4갈래 (§7 상태 분기표 · D-01) ═════════════════════════════
  out.base = await snapshotState({ counts: counts(2, 0), overviewOk: true, hang: false });
  out.excludedOnly = await snapshotState({ counts: counts(0, 1) });   // ★ 게임 0 · 제외 1
  out.nothing = await snapshotState({ counts: counts(0, 0) });
  out.loadFailed = await snapshotState({ overviewOk: false, counts: counts(0, 0) });
  out.loading = await snapshotState({ hang: true, overviewOk: true });

  // ═══ 초기화 흐름 (토큰·type-to-confirm·결과 문구) ═════════════════════════
  Object.assign(SCENE, { hang: false, overviewOk: true, counts: counts(3, 2) });

  async function driveReset(excluded) {
    SCENE.resetResult = (a) => (a[0]
      ? { ok: true, data: { results: [{}, {}, {}], counts: { deleted: 2 } } }
      : { ok: false, code: "CONFIRM_REQUIRED", params: {
          confirm_token: "RESET-TOKEN", games: 3, profiles: 5, named: 1,
          excluded, challenge: "delete" } });
    resetCalls();
    const ui = mount();
    await settle();
    const btn = resetButton(ui.ui());
    if (!btn || btn.disabled) return { ui, blocked: true };
    btn.onClick();
    await settle();
    return { ui, blocked: false, modal: shownModals[0] || null };
  }

  /**
   * 확인창을 **우리 호스트로 다시 그린다.**
   *
   * ⚠️ `showModal`이 받은 노드는 그 순간의 렌더 결과다 — 타이핑 뒤 그 노드를 다시 읽으면
   *   **낡은 값**이 나오고, 그러면 "입력해도 OK가 안 열린다"를 못 가려낸다(항진식이 된다).
   *   같은 spec을 우리가 호스팅하면 재렌더 결과를 그대로 볼 수 있다.
   */
  function mirrorOf(modalNode) {
    const spec = modalNode ? modalNode.props.spec : null;
    if (!spec) return null;
    const host = makeHost(() => h(popup.SpecConfirmModal, { spec, closeModal: () => {} }));
    host.render();
    return {
      host,
      type: (value) => find(host.output, "TextField").node.props.onChange({ target: { value } }),
      okDisabled: () => !!find(host.output, "ConfirmModal").node.props.bOKDisabled,
      ok: () => find(host.output, "ConfirmModal").node.props.onOK(),
    };
  }

  {
    const run = await driveReset(2);
    out.resetBlocked = run.blocked;
    out.resetCall1 = calls.reset[0];
    out.resetModalTexts = run.modal ? texts(run.modal) : [];
    const mirror = mirrorOf(run.modal);
    out.resetMirrored = !!mirror;
    if (mirror) {
      out.resetOkBefore = mirror.okDisabled();
      mirror.type("wrong");
      out.resetOkWrong = mirror.okDisabled();
      mirror.type("delete");
      out.resetOkTyped = mirror.okDisabled();
      mirror.ok();
    }
    await settle();
    out.resetCall2 = calls.reset[1];
    out.resetNote = texts(run.ui.ui()).filter((x) => /RESET_OK|RESET_LEFT_NOTE/.test(x));
    out.resetMutations = mutations.length;
  }
  {
    // 제외 0건이면 그 줄을 그리지 않는다("0이면 안 그림" 문법).
    const run = await driveReset(0);
    out.resetModalTextsNoExcluded = run.modal ? texts(run.modal) : [];
  }

  // ═══ 입력값 보존 (GP#9) ══════════════════════════════════════════════════
  //
  // 확인창은 `showModal`이 띄운다 — 그 인스턴스의 언마운트를 프로브가 잡을 수 없으므로,
  // **같은 spec을 우리 호스트로 다시 그려** 타이핑 → 언마운트를 재현하고, 그 값이 다음
  // 확인창의 `initial`로 되돌아오는지 본다(호출부가 스냅샷을 붙들고 있는지의 판정).
  {
    const run = await driveReset(2);
    const mirror = mirrorOf(run.modal);
    out.snapshotSpecFound = !!mirror;
    if (mirror) {
      mirror.type("dele");
      mirror.host.unmount();                // 여기서 onInputSnapshot이 나간다
      const btn = resetButton(run.ui.ui());
      shownModals.length = 0;
      if (btn) btn.onClick();
      await settle();
      const again = shownModals[0];
      out.reopenedInitial = again ? find(again, "TextField").node.props.value : null;
    }
  }

  // ═══ 표시 이름 편집 ══════════════════════════════════════════════════════
  {
    resetCalls();
    nameSyncs.length = 0;
    const ui = mount();
    await settle();
    out.renameButtons = byPrefix(ui.ui(), /^MANAGE_NAME_EDIT\b/).length;
    byPrefix(ui.ui(), /^MANAGE_NAME_EDIT\b/)[0].onClick();
    const modal = shownModals[0] || null;
    out.renameModalTexts = modal ? texts(modal) : [];
    const nameMirror = mirrorOf(modal);
    out.renameMirrored = !!nameMirror;
    if (nameMirror) {
      out.renameOkDisabled = nameMirror.okDisabled();   // 빈 입력 = 기본 이름 복귀라 **항상 활성**
      nameMirror.type("거실 TV");
      nameMirror.ok();
    }
    await settle();
    out.renameCall = calls.rename[0];
    out.renameSyncs = nameSyncs.slice();
    out.renameNote = texts(ui.ui()).filter((x) => /NAME_EDIT_OK_NOTE|NAME_EDIT_RESET_NOTE/.test(x));
    out.renameMutations = mutations.length;
    out.sectionTitles = texts(ui.ui()).filter((x) => /^SETTINGS_/.test(x));
    // 게임별 동작이 이 화면에 새어 들어오지 않았는가(A4 — 전역 전용)
    out.allButtons = buttons(ui.ui()).map((b) => b.label);
    out.perGameLeak = findAll(ui.ui(), "ToggleField").length;
  }

  console.log(JSON.stringify(out));
})();
