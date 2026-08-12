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
/** i18n 표시명 덮어쓰기(실물 `i18n.ts`의 `overrides`와 같은 자리). */
const overrides = {};
const shownModals = [];
const mutations = [];
const nameSyncs = [];

function resetCalls() {
  Object.values(calls).forEach((a) => { a.length = 0; });
  shownModals.length = 0;
  mutations.length = 0;
  Object.keys(overrides).forEach((k) => { delete overrides[k]; });
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
  // ★ P15-E R6ⓓ: 표시명 덮어쓰기를 **실물과 같은 모양으로** 흉내 낸다 — `t()`는 사용자가 정한
  //   이름을 돌려주고 `tDefault()`는 기본 문구를 돌려준다(i18n.ts의 계약 그대로).
  //   이게 없으면 "사용자가 이름을 정해 둔 상태"를 프로브가 아예 만들 수 없어, 편집창의
  //   프리필 규칙(기본이면 빈 칸 / 사용자 이름이면 채움)의 **한쪽 갈래를 못 잰다.**
  "./i18n": {
    t: (k, p) => {
      const raw = overrides[k] === undefined ? String(k) : overrides[k];
      return p ? `${raw} ${Object.values(p).join(" ")}` : raw;
    },
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: (v) => {
      nameSyncs.push(v);
      for (const slot of ["dock", "internal"]) {
        const key = slot === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
        const value = ((v && v[slot]) || "").trim();
        if (value) overrides[key] = value;
        else delete overrides[key];
      }
    },
    // 실물과 같은 저장소(overrides)를 읽는다 — 배지 출처가 setProfileNames 합류점임을
    // 목에서도 재현해야 P15-E C1(낡은 overview 배지)의 회귀가 이 프로브에 잡힌다.
    hasProfileNameOverride: (slot) =>
      (slot === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") in overrides,
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

  // ═══ R5 TOCTOU **재질문에도 입력이 살아 있다**(GP#9) ═════════════════════
  //
  // 초기화는 지문이 어긋나면 **갱신된 params로 다시 묻는다**. 그 재질문은 확인창 안에서
  // `runReset`을 다시 부르는데, 보존값을 상태로 들면 그 클로저는 **창이 열리던 시점의 값**을
  // 본다 — 즉 방금 찍은 입력이 없는 값이다. 가상 키보드로 한 글자씩 찍는 화면에서 이것은
  // "매번 처음부터 다시 치라"는 뜻이 된다.
  {
    Object.assign(SCENE, { hang: false, overviewOk: true, counts: counts(3, 2) });
    // 토큰을 되돌려도 **또** CONFIRM_REQUIRED — TOCTOU 재질문 그 자체다.
    SCENE.resetResult = (a) => ({
      ok: false,
      code: "CONFIRM_REQUIRED",
      params: {
        confirm_token: `RESET-${calls.reset.length}`,
        games: 3, profiles: 5, named: 1, excluded: 2, challenge: "delete",
      },
    });
    resetCalls();
    const ui = mount();
    await settle();
    const btn = resetButton(ui.ui());
    if (btn) btn.onClick();
    await settle();
    const first = shownModals[0] || null;
    const mirror = mirrorOf(first);
    out.toctouFound = !!mirror;
    if (mirror) {
      mirror.type("delete");
      mirror.ok();                    // 사용자가 확정 → 토큰을 되돌려 재호출
      mirror.host.unmount();          // 창이 닫히며 스냅샷이 나간다(실물과 같은 순서)
      await settle();
      await settle();
      const again = shownModals[1] || null;
      out.toctouModals = shownModals.length;
      out.toctouInitial = again ? find(again, "TextField").node.props.value : null;
      out.toctouTokens = calls.reset.map((a) => a[0] ?? null);
    }
  }

  // ═══ R6ⓓ 표시 이름 편집의 **프리필 규칙**(기본이면 빈 칸 / 사용자 이름이면 채움) ═══
  //
  // 빈 칸이 곧 *"기본으로 되돌리기"*라서, 기본 이름을 글자로 채워 두면 사용자는 그것을 지워야만
  // 기본으로 돌아간다(같은 뜻을 두 방법으로 표현하게 된다). 규칙은 spec 안에 있고, 여기서는
  // **두 상태를 실제로 만들어** 모달의 TextField 값을 본다.
  async function prefillOf(names) {
    Object.assign(SCENE, { hang: false, overviewOk: true, counts: counts(3, 0), profileNames: names });
    resetCalls();
    const ui = mount();
    await settle();
    const edit = byPrefix(ui.ui(), /^MANAGE_NAME_EDIT\b/)[0];
    if (!edit) return null;
    edit.onClick();
    await settle();
    const modal = shownModals[0] || null;
    const field = modal ? find(modal, "TextField") : null;
    return {
      value: field ? field.node.props.value : null,
      // 화면이 그 상태를 뭐라고 부르는지도 같이 본다(메타 줄: 기본 / 직접 정한 이름).
      meta: texts(ui.ui()).filter((x) => x === "MANAGE_NAME_DEFAULT" || x === "MANAGE_NAME_CUSTOM"),
    };
  }
  out.prefillDefault = await prefillOf({ dock: "", internal: "" });
  out.prefillCustom = await prefillOf({ dock: "거실 TV", internal: "" });

  // ═══ C1(재게이트) 이름 변경 성공 + 재조회 실패 — 배지가 성공 문구를 부정하지 않는가 ═══
  //
  // 이름 변경 응답이 정본(profile_names)을 싣고 오고 setProfileNames로 합류한다. 그 직후
  // 재조회가 실패하면 overview 봉투는 낡은 채다 — 배지가 그 낡은 봉투를 읽으면 같은 화면에서
  // "「도킹이름」으로 바꿨습니다"와 "기본 이름"이 서로를 부정한다(P15-E 재게이트 C1).
  {
    Object.assign(SCENE, { hang: false, overviewOk: true, counts: counts(3, 0), profileNames: { dock: "", internal: "" } });
    resetCalls();
    nameSyncs.length = 0;
    const ui = mount();
    await settle();
    SCENE.overviewOk = false;             // 이름 변경 뒤의 재조회부터 실패
    byPrefix(ui.ui(), /^MANAGE_NAME_EDIT\b/)[0].onClick();
    const modal = shownModals[shownModals.length - 1] || null;
    const nameMirror = mirrorOf(modal);
    if (nameMirror) { nameMirror.type("도킹이름"); nameMirror.ok(); }
    await settle();
    const seen = texts(ui.ui());
    out.c1BadgeAfterRenameReloadFail = seen.filter((x) => x === "MANAGE_NAME_DEFAULT" || x === "MANAGE_NAME_CUSTOM");
    out.c1OkNoteShown = seen.some((x) => /NAME_EDIT_OK_NOTE/.test(x));
  }

  console.log(JSON.stringify(out));
})();
