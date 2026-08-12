"use strict";
/**
 * 백업 뷰·복원 흐름(설계 §5-C)을 **렌더+클릭으로** 잰다 — `qa/test_restore_ui.py`가 판정한다.
 *
 * ★ P13 재작성: 대상이 「관리」 탭에서 **팝업 G의 상세 → 백업 뷰**로 옮겨졌다(§15-A 이식표).
 *   흐름 자체(3-상태 계약·토큰·2단계 시맨틱)는 그대로이고, **복원 성공 뒤 재조회**(D-07)가
 *   새로 붙었다 — 복원은 disk 대피본을 하나 만들므로 목록의 행 수·순서가 그 자리에서 바뀐다.
 *   화면을 그대로 두면 **방금 사라진 백업의 [복원] 버튼**이 남는다.
 *
 * ★ **양 모드 주행**: 확인창을 중첩 모달로 띄우는 기본 모드와, `NESTED_CONFIRM=false` 폴백
 *   모드를 각각 돌린다 — 폴백은 실기 실패 시의 탈출구인데, 안 돌리면 그날 처음 실행된다.
 *
 * ★ 실행: node qa/restore_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 */
const path = require("path");
const { makeHost, h, find, texts, buttons, makeLoader, react, settle } =
  require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

/** 백엔드의 링 상한(`store.BACKUP_KEEP`). "+1" 단순 기대는 포화 상태에서 거짓이다(N-04). */
const BACKUP_KEEP = 10;

const GAME = {
  appid: "300", name: "Zeta", has_dock: true, has_internal: true, disk_matches: null,
  backups: 3, config_path: "/cfg/zeta.ini", profiles_identical: false,
  saved_at: { dock: "2026-08-10 09:00", internal: "" },
  last_applied: "dock", cloud_synced: false, running: false,
};

const row = (id, kind, stampLabel) => ({
  backup_id: id, kind, stamp: id, stamp_label: stampLabel, filename: "video.ini", size: 46,
});

/** 기본 링 — 프로필 대피본 1 + disk 2. 종류가 섞여 있어야 문구 분기를 잴 수 있다. */
const BASE_ROWS = () => [
  row("20260810-090300", "profile_dock", "T-03"),
  row("20260810-090200", "disk", "T-02"),
  row("20260810-090100", "disk", "T-01"),
];

const SCENE = {
  rows: BASE_ROWS(),
  outcome: "restored",
  noConfirm: false,          // 설정 파일이 없어 **묻지 않고** 복원하는 갈래
  failCode: null,            // 조기 거부(GAME_RUNNING 등)
  throwOnNextModal: false,   // 후속 제안 창만 실패시킨다
};

const calls = { overview: [], list: [], restore: [], save: [] };
const shownModals = [];
const mutations = [];

function reset(rows) {
  SCENE.rows = rows || BASE_ROWS();
  SCENE.outcome = "restored";
  SCENE.noConfirm = false;
  SCENE.failCode = null;
  SCENE.listFailsNext = false;      // 복원 뒤 백업 목록 재조회가 실패하는 장면(P15-E R4)
  SCENE.throwOnNextModal = false;
  Object.values(calls).forEach((a) => { a.length = 0; });
  shownModals.length = 0;
  mutations.length = 0;
}

/** 복원 1회가 링에 하는 일 — **disk 대피본 1개 추가 + 즉시 prune**(`store.py:307-313`). */
function pushDiskBackup() {
  SCENE.rows = [row("20260810-099999", "disk", "T-NEW"), ...SCENE.rows].slice(0, BACKUP_KEEP);
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
    showModal: (node) => {
      if (SCENE.throwOnNextModal) { SCENE.throwOnNextModal = false; throw new TypeError("showModal is not a function"); }
      shownModals.push(node);
    },
  },
  "./i18n": {
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: () => {},
  },
  "./rpc": {
    getOverview: (...a) => {
      calls.overview.push(a);
      return Promise.resolve({
        ok: true,
        data: {
          games: [{ ...GAME, backups: SCENE.rows.length }],
          counts: { total: 1, dock_ready: 1, internal_ready: 1, running: 0, incomplete: 0, excluded: 0 },
          profile_names: { dock: "", internal: "" },
        },
      });
    },
    listBackups: (...a) => {
      calls.list.push(a);
      // ★ P15-E R4: **뒤따르는 재조회만** 실패시킨다(뷰를 여는 첫 조회는 성공해야 장면이 선다).
      if (SCENE.listFailsNext && calls.list.length > 1) {
        return Promise.resolve({ ok: false, code: "BACKUP_DIR_UNREADABLE", params: {} });
      }
      return Promise.resolve({ ok: true, data: { backups: SCENE.rows } });
    },
    restoreBackup: (...a) => {
      calls.restore.push(a);
      if (SCENE.failCode) return Promise.resolve({ ok: false, code: SCENE.failCode, params: {} });
      const hit = SCENE.rows.find((r) => r.backup_id === a[1]) || SCENE.rows[0];
      const base = {
        appid: "300", backup_id: hit.backup_id, kind: hit.kind, stamp: hit.stamp,
        stamp_label: hit.stamp_label, filename: hit.filename, size: hit.size, disk_state: "unknown",
      };
      if (SCENE.outcome === "already") {
        // ★ 무쓰기 갈래 — 링도 안 밀린다. 화면이 재조회하면 그게 결함이다.
        return Promise.resolve({ ok: true, data: { ...base, outcome: "already" } });
      }
      if (!a[2] && !SCENE.noConfirm) {
        return Promise.resolve({ ok: false, code: "CONFIRM_REQUIRED", params: { ...base, confirm_token: "RESTORE-TOKEN" } });
      }
      pushDiskBackup();
      return Promise.resolve({ ok: true, data: { ...base, outcome: "restored", restored: "/x" } });
    },
    saveProfile: (...a) => { calls.save.push(a); return Promise.resolve({ ok: true, data: { meta: {}, warning: null } }); },
    applyProfile: () => new Promise(() => {}),
    deleteGame: () => new Promise(() => {}),
    setProfileName: () => new Promise(() => {}),
    resetAll: () => new Promise(() => {}),
  },
};

// ── 두 모드 ──────────────────────────────────────────────────────────────────
const baseLoad = makeLoader(srcDir, modules);
const NESTED_ANCHOR = "export const NESTED_CONFIRM = true;";
let anchorFound = true;
const popupFallback = baseLoad("popup.tsx", (src) => {
  if (!src.includes(NESTED_ANCHOR)) { anchorFound = false; return src; }
  return src.replace(NESTED_ANCHOR, "export const NESTED_CONFIRM = false;");
});
const NestedPopup = baseLoad("GamesPopup.tsx").GamesPopup;
// 폴백 사본 — `./popup`만 갈아 끼운 같은 화면이다(호출부는 한 줄도 안 바뀐다).
const FallbackPopup = makeLoader(srcDir, { ...modules, "./popup": popupFallback })("GamesPopup.tsx").GamesPopup;

const byPrefix = (root, re) => buttons(root).filter((b) => re.test(b.label));
const restoreButtons = (ui) => byPrefix(ui(), /^BACKUP_RESTORE$/);
const rowMetas = (ui) => texts(ui()).filter((x) => /^BACKUP_ROW_META/.test(x));

/** 팝업을 띄우고 **백업 뷰까지** 간다: 목록 → › → [백업 복원 N]. */
async function openBackupView(Impl) {
  const host = makeHost(() => h(Impl, { onMutate: () => mutations.push(1) }));
  host.render();
  const ui = () => host.output;
  await settle();
  const chevron = byPrefix(ui(), /^$/)[0];
  if (!chevron) return { ui, reached: false };
  chevron.onClick();
  const open = byPrefix(ui(), /^OPEN_BACKUPS\b/)[0];
  if (!open || open.disabled) return { ui, reached: false };
  open.onClick();
  await settle();
  return { ui, reached: restoreButtons(ui).length > 0 };
}

/** 지금 떠 있는 확인창(중첩=showModal 노드 / 폴백=팝업 안 오버레이)의 관측면. */
function currentConfirm(ui, nested) {
  if (nested) {
    const node = shownModals[shownModals.length - 1] || null;
    if (!node) return null;
    const modal = find(node, "ConfirmModal");
    return { texts: texts(node), ok: modal ? modal.node.props.onOK : null };
  }
  const overlay = find(ui(), "ConfirmOverlay");
  if (!overlay) return null;
  const okBtn = buttons(overlay.node)[0];
  return { texts: texts(overlay.node), ok: okBtn ? okBtn.onClick : null };
}

(async () => {
  const out = { anchorFound };

  // ═══ ① 프로필 대피본 복원 — 3-상태·토큰·D-07 재조회·후속 제안 ════════════
  {
    reset();
    const view = await openBackupView(NestedPopup);
    const before = { rows: restoreButtons(view.ui).length, list: calls.list.length, overview: calls.overview.length };
    restoreButtons(view.ui)[0].onClick();            // 맨 위 = 프로필 대피본
    await settle();
    const confirm = currentConfirm(view.ui, true);
    const res = { reached: view.reached, call1: calls.restore[0], before,
                  confirmTexts: confirm ? confirm.texts : [] };
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    res.call2 = calls.restore[1];
    // ★ D-07: 복원은 disk 대피본을 하나 만든다 — 목록과 overview를 각각 다시 읽어야 한다.
    res.listAfter = calls.list.length - before.list;
    res.overviewAfter = calls.overview.length - before.overview;
    res.rowsAfter = restoreButtons(view.ui).length;
    res.metasAfter = rowMetas(view.ui);
    res.stillOnBackupView = res.rowsAfter > 0;       // 연속 복원 시나리오 지원(화면은 머문다)
    res.mutations = mutations.length;
    const followUp = shownModals[shownModals.length - 1] || null;
    res.followUpTexts = followUp ? texts(followUp) : [];
    const okNode = followUp ? find(followUp, "ConfirmModal") : null;
    if (okNode) okNode.node.props.onOK();
    await settle();
    res.saveCalls = calls.save.slice();
    res.notes = texts(view.ui()).filter((x) => /RESTORE_|SAVE_OK/.test(x));
    out.nested = res;
  }

  // ═══ ①′ **폴백 모드**(`NESTED_CONFIRM=false`) 주행 ═══════════════════════
  //
  // 폴백은 실기에서 중첩이 실패할 때의 탈출구다 — 안 돌리면 그날 처음 실행된다.
  // ⚠️ 여기서는 **첫 확인창까지**만 잰다. 후속 제안은 같은 자리에 오버레이가 연달아 뜨는
  //   형태인데, 이 프로브의 미니 훅 런타임은 **언마운트 개념이 없어** 앞 오버레이의 상태를
  //   뒤 오버레이가 물려받는다(실물 React는 그 사이의 `overlay===null` 렌더에서 언마운트한다).
  //   하네스의 한계이지 제품의 한계가 아니므로, 여기서 재는 것을 **정직하게 좁힌다** —
  //   후속 제안 체인은 위 중첩 모드가 덮는다.
  {
    reset();
    const view = await openBackupView(FallbackPopup);
    const modalsBefore = shownModals.length;
    restoreButtons(view.ui)[0].onClick();
    await settle();
    const confirm = currentConfirm(view.ui, false);
    out.fallback = {
      reached: view.reached,
      call1: calls.restore[0],
      confirmTexts: confirm ? confirm.texts : [],
      // ★ D-05 ⑤: 오버레이가 떠 있는 동안 원 콘텐츠는 **렌더되지 않는다**(숨김이 아니라 미렌더).
      bodyHiddenDuringConfirm: restoreButtons(view.ui).length === 0,
      modalsUsed: shownModals.length - modalsBefore,
    };
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    out.fallback.call2 = calls.restore[1];
    out.fallback.mutations = mutations.length;
  }

  // ═══ ② 링 포화 — 행 수는 min(old+1, 10)이고 최고령 행이 퇴출된다(N-04) ════
  {
    const full = Array.from({ length: BACKUP_KEEP }, (_, i) =>
      row(`202608100${String(90 - i).padStart(4, "0")}`, i === 0 ? "profile_dock" : "disk", `F-${i}`));
    reset(full);
    const view = await openBackupView(NestedPopup);
    const oldest = full[full.length - 1].stamp_label;
    const beforeRows = restoreButtons(view.ui).length;
    restoreButtons(view.ui)[0].onClick();
    await settle();
    const confirm = currentConfirm(view.ui, true);
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    out.ring = {
      beforeRows,
      afterRows: restoreButtons(view.ui).length,
      newestFirst: (rowMetas(view.ui)[0] || "").includes("T-NEW"),
      evictedGone: !rowMetas(view.ui).some((x) => x.includes(oldest)),
    };
  }

  // ═══ ③ `already` — 백업 목록은 그대로, overview는 다시 읽는다(§4-F ③ 개정) ═
  //
  // ★ 백엔드 계약("`already`는 무쓰기")은 그대로다(§15-C). 바뀐 것은 **프론트가 그 사실을
  //   어떻게 아는가**이다: 이제 무쓰기 판정은 봉투의 `CONFIRM_REQUIRED` 하나뿐이고,
  //   `already`는 **확정 실행의 성공 응답**이라 같은 문을 지난다. 링은 안 밀렸으므로
  //   백업 목록 재조회(`listBackups`)는 여전히 0이다.
  {
    reset();
    SCENE.outcome = "already";
    const view = await openBackupView(NestedPopup);
    const before = { list: calls.list.length, overview: calls.overview.length };
    restoreButtons(view.ui)[0].onClick();
    await settle();
    out.already = {
      listAfter: calls.list.length - before.list,
      overviewAfter: calls.overview.length - before.overview,
      modals: shownModals.length,
      notes: texts(view.ui()).filter((x) => /RESTORE_/.test(x)),
      mutations: mutations.length,
    };
  }

  // ═══ ④ disk 대피본 — 오지 않을 후속 제안을 약속하지 않는다(R2) ═══════════
  {
    reset();
    const view = await openBackupView(NestedPopup);
    restoreButtons(view.ui)[1].onClick();            // 두 번째 행 = disk
    await settle();
    const confirm = currentConfirm(view.ui, true);
    out.disk = { confirmTexts: confirm ? confirm.texts : [] };
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    out.disk.modalsAfter = shownModals.length;       // 확인창 1개뿐(후속 제안 없음)
    out.disk.notes = texts(view.ui()).filter((x) => /RESTORE_/.test(x));
  }

  // ═══ ④′ 복원 성공 + **백업 목록 재조회 실패** — 둘 다 말한다(P15-E R4) ═══
  //
  // 복원은 끝났고(설정 파일이 바뀌었다) 목록만 못 읽은 상태다. 예전에는 재조회 실패가
  // 같은 note 자리를 덮어써서 *"이 내용은 지금 게임 설정 파일에만 있습니다 — 계속 쓰려면
  // 프로필로 저장하십시오"*라는 **후속 조치 안내가 통째로 사라졌다.**
  {
    reset();
    SCENE.listFailsNext = true;
    const view = await openBackupView(NestedPopup);
    restoreButtons(view.ui)[1].onClick();            // 두 번째 행 = disk(후속 제안 없는 갈래)
    await settle();
    const confirm = currentConfirm(view.ui, true);
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    await settle();
    const seen = texts(view.ui());
    out.listFail = {
      restoreNotes: seen.filter((x) => /RESTORE_/.test(x)),
      listFailNote: seen.filter((x) => /BACKUP_LIST_FAILED/.test(x)),
    };
    SCENE.listFailsNext = false;
  }

  // ═══ ⑤ 복원은 성공했는데 **후속 제안 창만** 못 뜬 경우(R1) ═══════════════
  {
    reset();
    const view = await openBackupView(NestedPopup);
    restoreButtons(view.ui)[0].onClick();
    await settle();
    const confirm = currentConfirm(view.ui, true);
    SCENE.throwOnNextModal = true;                   // 다음 창(=후속 제안)만 실패시킨다
    if (confirm && confirm.ok) confirm.ok();
    await settle();
    out.followUpFailed = {
      notes: texts(view.ui()).filter((x) => /RESTORE_|MANAGE_MODAL_FAILED/.test(x)),
      restoreCalls: calls.restore.length,
    };
  }

  // ═══ ⑥ 조기 거부(GAME_RUNNING) — 확실히 거부될 확인을 시키지 않는다 ══════
  {
    reset();
    SCENE.failCode = "GAME_RUNNING";
    const view = await openBackupView(NestedPopup);
    restoreButtons(view.ui)[0].onClick();
    await settle();
    out.refused = {
      modals: shownModals.length,
      notes: texts(view.ui()).filter((x) => /GAME_RUNNING|RESTORE_/.test(x)),
    };
  }

  // ═══ ⑦ 백업 뷰의 안내 3줄(§5-C) ═════════════════════════════════════════
  {
    reset();
    const view = await openBackupView(NestedPopup);
    out.hints = texts(view.ui()).filter((x) => /^BACKUP_LIST_|^BACKUP_RING_/.test(x));
    // 프로필 대피본이 없는 링에서는 "복원 뒤에 물어본다" 예고가 뜨지 않는다.
    reset(BASE_ROWS().filter((r) => r.kind === "disk"));
    const diskOnly = await openBackupView(NestedPopup);
    out.hintsDiskOnly = texts(diskOnly.ui()).filter((x) => /^BACKUP_LIST_|^BACKUP_RING_/.test(x));
  }

  console.log(JSON.stringify(out));
})();
