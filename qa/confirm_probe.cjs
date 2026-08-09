"use strict";
/**
 * **`[적용]`엔 확인창이 없고 `[저장]`엔 있다** — 그것을 **클릭 결과로** 잰다(P4-5 · QA 이월 ④).
 *
 * 왜 grep이 아닌가: 이 프로젝트에서 **거짓 검사가 다섯 번** 나왔고 그중 둘이 *"grep이 규칙을
 * 설명한 주석을 잡았다"*였다. 그리고 규칙을 소스 패턴으로 강제하려던 시도(`confirmed:\s*true`)는
 * **positional 호출을 못 잡아 무효**였다(실측). **표면 문법으로는 이 계약을 강제할 수 없다.**
 * → `test_frontend_e1.py`가 E1에 쓴 방식을 그대로 쓴다: **실제로 눌러 보고 무슨 일이 나는지 본다.**
 *   우회 수단(별칭·헬퍼·파생 변수·주석 마커)을 **가리지 않는다** — 무엇을 하든 결과가 같으면 같다.
 *
 * 실행: node qa/confirm_probe.cjs
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

const GAME = {
  appid: "1000", name: "Probe Game", has_dock: true, has_internal: true,
  disk_matches: "dock", last_applied: "dock", cloud_synced: false, running: false,
};

// ── 관측 ─────────────────────────────────────────────────────────────────────
let modalsShown = 0;            // showModal이 몇 번 불렸나
let modalThrows = false;        // showModal이 죽는 상황을 만든다(QA 반려 ②)
const notes = [];               // setNote로 화면에 뜬 안내
let saveCalls = [];             // save_profile 호출 인자
let applyCalls = [];            // apply_profile 호출 인자
const buttons = [];             // 렌더된 DialogButton {label, onClick}

function h(type, props, ...children) {
  if (typeof type === "function") return type({ ...(props || {}), children });
  const node = { type, props: props || {}, children };
  if (type && type.__kind === "DialogButton") {
    const label = children.flat(9).filter((c) => typeof c === "string").join(" ");
    buttons.push({ label, onClick: node.props.onClick, disabled: !!node.props.disabled });
  }
  return node;
}

// 백엔드가 "덮어쓰기다"라고 답하는 상황을 만든다 — 확인창이 떠야 하는 유일한 경우다.
const CONFIRM_ENV = {
  ok: false, code: "CONFIRM_REQUIRED",
  params: { confirm_token: "TOKEN-FROM-BACKEND", size: 1234, sha1_short: "abcdef0123",
            saved_at: "2026-08-07T00:00:00+0900", disk_state: "unknown" },
};

let hookSlot = 0;
const modules = {
  react: {
    useCallback: (fn) => fn,
    useEffect: () => {},
    useState(initial) {
      const slot = hookSlot++;
      if (slot === 0) {
        return [{ games: [GAME], counts: { total: 1, dock_ready: 1, internal_ready: 1, running: 0, incomplete: 0 } }, () => {}];
      }
      if (slot === 3) return [initial, (v) => { if (v) notes.push(String(v)); }];
      return [initial, () => {}];
    },
  },
  "./rpc": {
    getOverview: () => new Promise(() => {}),
    applyProfile: (...a) => { applyCalls.push(a); return Promise.resolve({ ok: true, data: {} }); },
    saveProfile: (...a) => {
      saveCalls.push(a);
      // 토큰을 들고 오면 성공, 아니면 확인을 요구한다 — 백엔드 계약과 같은 모양이다.
      return Promise.resolve(a[2] ? { ok: true, data: { meta: {}, warning: null } } : CONFIRM_ENV);
    },
  },
  "./i18n": {
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    // ★ P5: `tCode`(코드→문구 단일 관문)도 목에 넣는다 — 없으면 소비처가 TypeError로
    //   죽고 "로직 FAIL"처럼 보인다(인계 문서 5-B의 낡은 목 함정).
    tCode: (code) => String(code),
    isLangResolved: () => true,
    ensureLang: () => Promise.resolve(),
  },
  "./version": { PLUGIN_VERSION: "0.0.0-probe" },
  // ★ P6: 「게임 추가」 탭은 이 프로브의 관심사가 아니다(전용 프로브 discover_probe.cjs가 잰다).
  //   목을 안 두면 그쪽이 끌어오는 `@decky/api`(파일 선택기)까지 여기서 로드돼 렌더가 통째로 죽고,
  //   그게 "로직 FAIL"처럼 보인다 — 인계 문서 5-B의 낡은 목 함정 그대로다.
  "./DiscoverTab": { DiscoverTab: () => null },
  // ★ P8: 「관리」 탭도 같은 이유로 목을 둔다 — 이 프로브의 관심사가 아니고,
  //   목이 없으면 실물 ManageTab이 로드되며 낡은 목(`./rpc`에 deleteGame 없음 등)에
  //   걸려 렌더가 통째로 죽고 그게 "로직 FAIL"처럼 보인다.
  "./ManageTab": { ManageTab: () => null },
  "./deckyui": {
    ConfirmModal: { __kind: "ConfirmModal" },
    DialogButton: { __kind: "DialogButton" },
    Focusable: { __kind: "Focusable" },
    ToggleField: { __kind: "ToggleField" },
    showModal: (node) => {
      if (modalThrows) throw new TypeError("showModal is not a function");
      modalsShown += 1; lastModal = node;
    },
  },
};
let lastModal = null;

function load(rel) {
  const file = path.join(srcDir, rel);
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React, jsxFactory: "h", jsxFragmentFactory: "Fragment", esModuleInterop: true,
    }, fileName: file,
  }).outputText;
  const exports = {};
  const req = (name) => {
    if (modules[name]) return modules[name];
    if (name.startsWith(".")) {
      const base = name.replace(/^\.\//, "");
      for (const ext of [".tsx", ".ts"]) {
        if (fs.existsSync(path.join(srcDir, base + ext))) return load(base + ext);
      }
    }
    throw new Error("unmocked: " + name);
  };
  const Fragment = { __kind: "Fragment" };
  new Function("exports", "require", "module", "h", "Fragment", compiled)(exports, req, { exports }, h, Fragment);
  return exports;
}

const { StatusPage } = load("StatusPage.tsx");
hookSlot = 0;
h(StatusPage, null);

// 라벨은 i18n 목이 키를 그대로 돌려주므로 키로 갈린다.
const applyBtns = buttons.filter((b) => /^APPLY_/.test(b.label));
const saveBtns = buttons.filter((b) => /^SAVE_(DOCK|INTERNAL)_SHORT/.test(b.label));

const settle = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  // ── ① [적용]을 누른다 → 확인창이 뜨면 안 된다 ─────────────────────────────
  modalsShown = 0;
  for (const b of applyBtns) b.onClick && b.onClick();
  await settle();
  const modalsAfterApply = modalsShown;
  const appliedCount = applyCalls.length;

  // ── ② [저장]을 누른다 → 확인창이 떠야 하고, 그 전에 저장이 일어나면 안 된다 ──
  modalsShown = 0; saveCalls = [];
  const saveBtn = saveBtns[0];
  saveBtn && saveBtn.onClick && saveBtn.onClick();
  await settle();
  const modalsAfterSave = modalsShown;
  const firstCallHadToken = saveCalls.length > 0 && saveCalls[0][2] !== undefined;

  // ── ③ 확인창의 OK를 누른다 → **백엔드가 준 토큰 그대로** 재호출해야 한다 ────
  let tokenSentBack = null;
  const onOK = lastModal && lastModal.props && lastModal.props.onOK;
  if (typeof onOK === "function") {
    onOK();
    await settle();
    const withToken = saveCalls.find((c) => c[2] !== undefined);
    tokenSentBack = withToken ? withToken[2] : null;
  }

  // ── ④ [QA 반려 ②] showModal이 죽으면 **그 사실을 화면이 말해야** 한다 ──────────
  //    안전한 건 맞다(토큰이 없으니 저장 안 됨). 하지만 "안전"과 "진단 가능"은 다른 요건이다.
  modalThrows = true; notes.length = 0; saveCalls = [];
  saveBtn && saveBtn.onClick && saveBtn.onClick();
  await settle();
  const noteOnModalFailure = notes.join(" | ");
  const savedDespiteModalFailure = saveCalls.some((c) => c[2] !== undefined);
  modalThrows = false;

  console.log(JSON.stringify({
    // 측정 경로에 닿았는지부터 — 버튼이 안 잡히면 아무것도 못 잰 것이다
    applyButtons: applyBtns.length,
    saveButtons: saveBtns.length,
    // ① 적용은 확인창을 띄우지 않는다 (사용자 판정 — 가장 자주 누르는 버튼이라 순수 마찰)
    modalsAfterApply,
    appliedCount,
    // ② 저장은 확인창을 띄운다. 그리고 **첫 호출은 토큰 없이** 나가야 한다
    //    (토큰을 프론트가 지어내 붙이면 계약이 무너진다)
    modalsAfterSave,
    firstSaveCallHadToken: firstCallHadToken,
    // ③ 확정 시 백엔드가 준 토큰을 **그대로** 되돌린다
    tokenSentBack,
    modalIsConfirmModal: !!(lastModal && lastModal.type && lastModal.type.__kind === "ConfirmModal"),
    // 파괴적 동작 표시 — `preferredFocus`가 ConfirmModalProps에 없어서 쓸 수 있는 방어가 이것뿐이다
    destructiveFlagged: !!(lastModal && lastModal.props && lastModal.props.bDestructiveWarning),
    // ④ 모달이 죽었을 때: 화면에 안내가 뜨는가 / 그래도 저장은 안 되는가
    noteOnModalFailure,
    savedDespiteModalFailure,
  }));
})();
