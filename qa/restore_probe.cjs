"use strict";
/**
 * 「관리」 탭 백업/복원 UI를 **렌더+클릭으로** 잰다 (P9 · 상설화 P10).
 *
 * 왜 렌더+클릭인가: `test_confirm_ui`와 같은 이유다 — 표면 문법(grep)으로는 계약을 강제할 수
 * 없고(별칭·헬퍼·파생 변수로 우회된다), 이 프로젝트에서 그 방식이 네 라운드 연속 뚫렸다.
 * **무엇을 하든 결과가 같으면 같다**는 판정만이 우회를 가리지 않는다.
 *
 * 실행: node qa/restore_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 * 출력: JSON 한 줄.
 *  ① [백업 N] 라벨과 0건 비활성
 *  ② 클릭 → listBackups → 목록 모달(행 수·[복원] 버튼)
 *  ③ [복원] 클릭 → restoreBackup 무토큰 호출 → CONFIRM_REQUIRED → 확인창 → 토큰 그대로 재호출
 *  ④ restored(kind=profile_dock) → 후속 제안 모달 → OK → saveProfile 호출
 */
const fs = require("fs");
const path = require("path");
const projectRoot = path.resolve(__dirname, "..");
const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

globalThis.window = globalThis.window || { navigator: { userAgent: "probe" } };

const GAMES = [
  { appid: "100", name: "Has Backups", has_dock: true, has_internal: true, disk_matches: null,
    backups: 3, last_applied: "dock", cloud_synced: false, running: false },
  { appid: "200", name: "No Backups", has_dock: true, has_internal: false, disk_matches: null,
    backups: 0, last_applied: null, cloud_synced: false, running: false },
];
const ROWS = [
  { backup_id: "20260809-221532-profile_dock-video.ini", kind: "profile_dock",
    stamp: "20260809-221532", stamp_label: "2026-08-09 22:15:32", filename: "video.ini", size: 46 },
  { backup_id: "20260809-221530-disk-video.ini", kind: "disk",
    stamp: "20260809-221530", stamp_label: "2026-08-09 22:15:30", filename: "video.ini", size: 46 },
];
const CONFIRM = {
  ok: false, code: "CONFIRM_REQUIRED",
  params: { confirm_token: "RESTORE-TOKEN", appid: "100",
            backup_id: ROWS[0].backup_id, kind: "profile_dock", stamp: ROWS[0].stamp,
            stamp_label: ROWS[0].stamp_label, filename: "video.ini", size: 46, disk_state: "unknown" },
};

const buttons = [];
const modals = [];
const notes = [];
let restoreCalls = [], listCalls = [], saveCalls = [], renameCalls = [];
let throwOnNextModal = false;          // 확인창을 **다음 한 번만** 못 띄우게 한다
const nameSyncs = [];                  // load()가 표시명을 i18n에 반영했는가(R3)

function h(type, props, ...children) {
  if (typeof type === "function") return type({ ...(props || {}), children });
  const node = { type, props: props || {}, children };
  if (type && type.__kind === "DialogButton") {
    const label = children.flat(9).filter((c) => typeof c === "string").join(" ");
    buttons.push({ label, onClick: node.props.onClick, disabled: !!node.props.disabled, node });
  }
  return node;
}
function collect(node, acc) {
  if (!node || typeof node !== "object") return acc;
  if (Array.isArray(node)) { node.forEach((n) => collect(n, acc)); return acc; }
  acc.push(node);
  [].concat(node.children || [], node.props && node.props.strDescription ? [node.props.strDescription] : [])
    .forEach((k) => collect(k, acc));
  return acc;
}

let hookSlot = 0;
const state = [];
const modules = {
  react: {
    useCallback: (fn) => fn,
    useEffect: () => {},
    useState(initial) {
      const slot = hookSlot++;
      if (slot === 0) return [{ games: GAMES, counts: { total: 2, dock_ready: 2, internal_ready: 1, running: 0, incomplete: 1, } }, () => {}];
      if (slot === 2) return [initial, (v) => { if (v) notes.push(String(v)); }];
      return [state[slot] !== undefined ? state[slot] : initial, (v) => { state[slot] = v; }];
    },
  },
  "./rpc": {
    // load()가 부르는 조회 — **표시명이 실려 온다.** 이걸 i18n에 반영하지 않으면
    // 전체 초기화 뒤에도 옛 이름이 화면에 남는다(2026-08-10 QA R3).
    getOverview: () => Promise.resolve({
      ok: true,
      data: { games: GAMES, counts: { total: 2, dock_ready: 2, internal_ready: 1, running: 0, incomplete: 1 },
              profile_names: { dock: "다시 읽은 이름", internal: "" } },
    }),
    deleteGame: () => new Promise(() => {}),
    resetAll: () => new Promise(() => {}),
    listBackups: (...a) => { listCalls.push(a); return Promise.resolve({ ok: true, data: { backups: ROWS } }); },
    restoreBackup: (...a) => {
      restoreCalls.push(a);
      // ★ 실물처럼 **그 백업의 kind**를 돌려준다(R2: 문구가 kind로 갈린다).
      const row = ROWS.find((r) => r.backup_id === a[1]) || ROWS[0];
      const params = { ...CONFIRM.params, backup_id: row.backup_id, kind: row.kind,
                       stamp: row.stamp, stamp_label: row.stamp_label };
      return Promise.resolve(a[2]
        ? { ok: true, data: { ...params, outcome: "restored", restored: "/x" } }
        : { ...CONFIRM, params });
    },
    saveProfile: (...a) => { saveCalls.push(a); return Promise.resolve({ ok: true, data: { meta: {}, warning: null } }); },
    // ★ F11 ①: 화면이 보내는 첫 인자는 **식별자**여야 한다(표시명이 아니다).
    setProfileName: (...a) => {
      renameCalls.push(a);
      return Promise.resolve({ ok: true, data: { profile_names: { dock: a[1] || "", internal: "" } } });
    },
  },
  "./i18n": {
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (c) => String(c),
    // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 \"로직 FAIL\"처럼 보인다.
    setProfileNames: (v) => { nameSyncs.push(v); },
    tDefault: (k) => String(k),
    isLangResolved: () => true, ensureLang: () => Promise.resolve(),
  },
  "./deckyui": {
    ConfirmModal: { __kind: "ConfirmModal" },
    DialogButton: { __kind: "DialogButton" },
    Focusable: { __kind: "Focusable" },
    ModalRoot: { __kind: "ModalRoot" },
    TextField: { __kind: "TextField" },
    showModal: (node) => {
      if (throwOnNextModal) { throwOnNextModal = false; throw new TypeError("showModal is not a function"); }
      modals.push(node);
    },
  },
};

function load(rel) {
  const file = path.join(srcDir, rel);
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React, jsxFactory: "h", jsxFragmentFactory: "Fragment", esModuleInterop: true },
    fileName: file,
  }).outputText;
  const exports = {};
  const req = (name) => {
    if (modules[name]) return modules[name];
    if (name.startsWith(".")) {
      const base = name.replace(/^\.\//, "");
      for (const ext of [".tsx", ".ts", ".json"]) {
        const p = path.join(srcDir, base + ext);
        if (fs.existsSync(p)) return ext === ".json" ? JSON.parse(fs.readFileSync(p, "utf8")) : load(base + ext);
      }
    }
    throw new Error("unmocked: " + name);
  };
  const Fragment = { __kind: "Fragment" };
  new Function("exports", "require", "module", "h", "Fragment", compiled)(exports, req, { exports }, h, Fragment);
  return exports;
}

const { ManageTab } = load("ManageTab.tsx");
hookSlot = 0;
h(ManageTab, null);

const settle = () => new Promise((r) => setTimeout(r, 0));
const backupBtns = buttons.filter((b) => /^MANAGE_BACKUPS/.test(b.label));

(async () => {
  const out = { backupButtons: backupBtns.map((b) => ({ label: b.label, disabled: b.disabled })) };
  // ② 첫 게임의 [백업 3] 클릭
  backupBtns[0] && backupBtns[0].onClick && backupBtns[0].onClick();
  await settle();
  out.listCalls = listCalls;
  out.modal1 = modals[0] && modals[0].type && modals[0].type.__kind;
  const restoreBtns = buttons.filter((b) => b.label === "BACKUP_RESTORE");
  out.restoreButtons = restoreBtns.length;
  // ③ 첫 [복원] 클릭
  restoreBtns[0] && restoreBtns[0].onClick && restoreBtns[0].onClick();
  await settle();
  out.restoreCall1 = restoreCalls[0];
  out.modal2 = modals[1] && modals[1].type && modals[1].type.__kind;
  out.modal2Destructive = !!(modals[1] && modals[1].props && modals[1].props.bDestructiveWarning);
  out.modal2Texts = collect(modals[1], []).flatMap((n) => (n.children || []).filter((c) => typeof c === "string"));
  // 확인창 OK
  const onOK = modals[1] && modals[1].props && modals[1].props.onOK;
  if (typeof onOK === "function") { onOK(); await settle(); }
  out.restoreCall2 = restoreCalls[1];
  out.modal3 = modals[2] && modals[2].type && modals[2].type.__kind;
  out.modal3Title = modals[2] && modals[2].props && modals[2].props.strTitle;
  // ④ 후속 제안 OK → saveProfile
  const onOK2 = modals[2] && modals[2].props && modals[2].props.onOK;
  if (typeof onOK2 === "function") { onOK2(); await settle(); }
  out.saveCalls = saveCalls;
  // ⑤ 표시 이름 바꾸기 — 버튼 → 편집창 → 확정. **RPC의 첫 인자가 식별자여야 한다.**
  const renameBtn = buttons.find((b) => b.label === "MANAGE_NAME_EDIT");
  out.renameButtons = buttons.filter((b) => b.label === "MANAGE_NAME_EDIT").length;
  if (renameBtn && renameBtn.onClick) renameBtn.onClick();
  await settle();
  const nameModal = modals[modals.length - 1];
  out.nameModal = nameModal && nameModal.type && nameModal.type.__kind;
  out.nameModalOkDisabled = !!(nameModal && nameModal.props && nameModal.props.bOKDisabled);
  const onOK3 = nameModal && nameModal.props && nameModal.props.onOK;
  if (typeof onOK3 === "function") { onOK3(); await settle(); }
  out.renameCalls = renameCalls;
  // ★ R3: load()(복원·이름변경 성공 뒤 갱신 경로)가 표시명을 i18n에 반영했는가.
  out.nameSyncs = nameSyncs;

  // ★ R2 — `disk` 백업(실사용 다수)의 확인창은 **오지 않을 후속 제안을 약속하면 안 된다.**
  //   목록을 다시 열고 두 번째 행(=`disk`)을 복원해 그 창의 문구를 본다.
  const backupBtnAgain = buttons.filter((b) => /^MANAGE_BACKUPS/.test(b.label))[0];
  if (backupBtnAgain && backupBtnAgain.onClick) backupBtnAgain.onClick();
  await settle();
  const restoreBtnsDisk = buttons.filter((b) => b.label === "BACKUP_RESTORE");
  const diskBtn = restoreBtnsDisk[restoreBtnsDisk.length - 1];   // 마지막 렌더의 disk 행
  if (diskBtn && diskBtn.onClick) diskBtn.onClick();
  await settle();
  const diskModal = modals[modals.length - 1];
  out.diskConfirmKind = (restoreCalls[restoreCalls.length - 1] || [])[1];
  out.diskConfirmTexts = collect(diskModal, []).flatMap((n) => (n.children || []).filter((c) => typeof c === "string"));

  // ★ R1 시나리오 — **복원은 성공했는데 후속 제안 창만 못 뜬 경우.**
  //   디스크는 이미 다시 쓰였고 백업 링도 1칸 소모됐다. 이때 화면이 "아무것도 지우지
  //   않았습니다"라고 말하면 **마지막 말이 사실과 반대**가 된다(qa-lead 재현).
  notes.length = 0;
  const restoreBtns2 = buttons.filter((b) => b.label === "BACKUP_RESTORE");
  if (restoreBtns2[0] && restoreBtns2[0].onClick) restoreBtns2[0].onClick();
  await settle();
  const confirm2 = modals[modals.length - 1];
  const onOK4 = confirm2 && confirm2.props && confirm2.props.onOK;
  throwOnNextModal = true;                    // 다음 창(=후속 제안)만 실패시킨다
  if (typeof onOK4 === "function") { onOK4(); await settle(); }
  throwOnNextModal = false;
  out.notesAfterFollowUpModalFailure = notes.slice();
  out.notes = notes;
  console.log(JSON.stringify(out));
})();
