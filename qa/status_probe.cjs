"use strict";
/**
 * 전체 화면 「현황」 탭(P3)을 **의미로** 재는 프로브.
 *
 * 재는 것(설계 §9-E ② — P3 완료 기준의 200게임 대응 재정의):
 *   ① **미완성 게임이 위로** 정렬된다 — 스크롤 없이 "무엇이 덜 됐나"가 먼저 보인다
 *   ② **「미완성만 보기」 토글**이 실제로 걸러 낸다
 *   ③ **200게임에서도** 렌더가 성립하고 위 둘이 유지된다
 *
 * 왜 DOM이 아니라 이걸로 재나: Steam의 `ToggleField`는 커스텀 컴포넌트라 `.click()`이 안 먹는다.
 * 실기 DOM 관찰은 "보인다"까지만 확인할 수 있고 **로직은 못 잰다.** 둘은 서로를 대체하지 않는다.
 *
 * 실행: node qa/status_probe.cjs [게임수]   (기본 9 — 이 기기 실데이터와 같은 규모)
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));
const N = Number(process.argv[2] || 9);

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// 합성 현황: N개 중 3개가 미완성(internal 없음). 이름은 정렬을 확인할 수 있게 역순으로 만든다.
const games = Array.from({ length: N }, (_, i) => ({
  appid: String(1000 + i),
  name: `Game ${String(N - i).padStart(3, "0")}`,
  has_dock: true,
  has_internal: i % 7 !== 0,        // 7의 배수 번째가 미완성
  disk_matches: "dock",
  last_applied: "dock",
  cloud_synced: false,
  running: false,
  // P9: 봉투에 추가된 필드. 이 프로브는 안 읽지만 **목이 실물 모양과 어긋나면**
  //   나중에 그 필드를 읽는 코드가 들어왔을 때 조용히 undefined를 본다.
  backups: 0,
}));
const incompleteCount = games.filter((g) => !g.has_internal).length;

let toggleOnChange = null;
let toggleState = false;
const rows = [];

function h(type, props, ...children) {
  if (typeof type === "function") return type({ ...(props || {}), children });
  const node = { type, props: props || {}, children };
  if (type && type.__kind === "ToggleField") {
    toggleOnChange = node.props.onChange;
    toggleState = !!node.props.checked;
  }
  return node;
}

// 렌더 트리에서 게임 행(이름 텍스트)을 순서대로 뽑는다.
function collectNames(node, out) {
  if (!node || typeof node !== "object") return out;
  if (Array.isArray(node)) { node.forEach((k) => collectNames(k, out)); return out; }
  const kids = [].concat(node.children || []);
  // StatusRow는 이름을 담은 div를 첫 자식으로 갖는다 — 텍스트가 "Game "으로 시작하면 행이다.
  for (const k of kids) {
    if (typeof k === "string" && k.startsWith("Game ")) out.push(k);
    else collectNames(k, out);
  }
  return out;
}

// ★ QA R2 지적 ⑫: 실기에서 찾아 고친 "토글이 Focusable 밖이라 D-패드로 도달 불가"를
//   **아무 테스트도 재지 않았다.** 래퍼만 떼면 그대로 PASS했다 — 실기로만 잡히는 줄 알았는데
//   렌더 트리에서 조상을 훑으면 정적으로 잴 수 있다. 실기가 필요 없는 것을 실기에 미루지 않는다.
//
// ★ [2026-08-07 P4-3] **이름 하나를 세던 것을 집합으로 바꿨다.**
//   예전 판정은 `kind === "ToggleField"` 하나만 봤다. P4가 저장·확인 버튼을 붙이면
//   **아무도 그 도달성을 안 재는** 상태가 되고, 그건 D9-1이 그대로 재발하는 자리다
//   (QA가 P4로 넘긴 조건 ①). 만든 뒤에 검사를 붙이는 방식은 R2 ⑫에서 이미 실패했다.
//   → 상호작용 컴포넌트를 **집합으로 열거**하면, 새 버튼이 생기는 순간 자동으로 덮인다.
//   *"핸드헬드에서 못 누르는 확인 버튼은 확인창이 아니라 잠금이다."*
const INTERACTIVE = new Set(["ToggleField", "DialogButton", "ButtonItem"]);

/** Focusable 조상이 없는 상호작용 컴포넌트를 모은다. `{unreachable:[kind…], seen:n}` */
function scanReachability(node, inFocusable, acc) {
  if (!node || typeof node !== "object") return acc;
  if (Array.isArray(node)) {
    node.forEach((k) => scanReachability(k, inFocusable, acc));
    return acc;
  }
  const kind = node.type && node.type.__kind;
  if (INTERACTIVE.has(kind)) {
    acc.seen += 1;
    if (!inFocusable) acc.unreachable.push(kind);
  }
  const next = inFocusable || kind === "Focusable";
  [].concat(node.children || []).forEach((k) => scanReachability(k, next, acc));
  return acc;
}

let hookSlot = 0;
const state = [];
const modules = {
  react: {
    useCallback: (fn) => fn,
    useEffect: () => {},          // 로드 effect는 안 돌린다 — overview를 직접 주입한다
    useState(initial) {
      const slot = hookSlot++;
      if (slot === 0) return [{ games, counts: { total: N, dock_ready: N, internal_ready: N - incompleteCount, running: 0, incomplete: incompleteCount } }, () => {}];
      if (slot === 1) return [state[1] !== undefined ? state[1] : initial, (v) => { state[1] = v; }];
      return [initial, () => {}];
    },
  },
  "./rpc": { getOverview: () => new Promise(() => {}), applyProfile: () => new Promise(() => {}) },
  "./i18n": {
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    // ★ P5: `tCode`(코드→문구 단일 관문)도 목에 넣는다 — 없으면 소비처가 TypeError로
    //   죽고 "로직 FAIL"처럼 보인다(인계 문서 5-B의 낡은 목 함정).
    tCode: (code) => String(code),
    // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 \"로직 FAIL\"처럼 보인다.
    setProfileNames: () => {},
    tDefault: (k) => String(k),
    // ★ 언어 확정은 이미 끝난 것으로 둔다 — 이 프로브가 재는 것은 정렬·필터 로직이지 i18n이 아니다.
    //   (목을 안 늘리면 렌더가 통째로 죽어 "로직 FAIL"처럼 보인다 — 인계 문서 5-B의 경고 지점)
    isLangResolved: () => true,
    ensureLang: () => Promise.resolve(),
  },
  "./version": { PLUGIN_VERSION: "0.0.0-probe" },
  // ⚠️ `deckyui`에 컴포넌트를 추가하면 **이 목도 같이 늘려야 한다**(인계 문서 5-B ④ —
  //    `routerHook` 누락으로 한 번 깨졌다). 목이 낡으면 렌더가 통째로 죽고 "로직 FAIL"처럼 보인다.
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
    showModal: () => {},
  },
};

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

// 1차: 필터 꺼짐
hookSlot = 0;
const off = collectNames(h(StatusPage, null), []);

// 2차: 필터 켜짐 — ★ **토글을 실제로 눌러서** 켠다.
//   2026-08-06 QA 지적 ⑤: 예전엔 `state[1] = true`로 상태를 직접 주입했다. 그러면 토글이
//   완전히 죽어 있어도(`onChange={() => {}}`, `checked={false}` 고정) 필터가 켜져 PASS했다 —
//   "토글 배선"을 검증한다고 선언해 놓고 배선을 통째로 우회하는 **거짓 검사**였다.
//   지금은 렌더된 onChange를 그대로 호출한다. 배선이 끊기면 상태가 안 바뀌어 2차 렌더가
//   1차와 같아지고, test_status_page.py의 필터 단언이 FAIL한다.
// 도달성: 렌더 트리에서 ToggleField가 Focusable 자손인가
hookSlot = 0;
const reach = scanReachability(h(StatusPage, null), false, { unreachable: [], seen: 0 });
const toggleReachable = reach.unreachable.length === 0;

const stateBeforeToggle = state[1];
if (typeof toggleOnChange === "function") toggleOnChange(true);
const toggleActuallyChangedState = state[1] !== stateBeforeToggle;
hookSlot = 0;
const on = collectNames(h(StatusPage, null), []);

const firstIncompleteIndex = off.findIndex((n) => {
  const g = games.find((x) => `Game ${String(N - games.indexOf(x)).padStart(3, "0")}` === n);
  return g && !g.has_internal;
});

console.log(JSON.stringify({
  n: N,
  incompleteCount,
  rowsWithoutFilter: off.length,
  rowsWithFilter: on.length,
  // ① 미완성이 맨 앞 incompleteCount개를 차지하는가
  incompleteFirst: off.slice(0, incompleteCount).every((name) => {
    const g = games.find((x) => x.name === name);
    return g && !g.has_internal;
  }),
  // ② 필터가 미완성만 남기는가
  filterKeepsOnlyIncomplete: on.every((name) => {
    const g = games.find((x) => x.name === name);
    return g && !g.has_internal;
  }),
  toggleWired: typeof toggleOnChange === "function",
  // ★ 배선이 **의미로** 살아 있는가 — onChange를 호출했더니 상태가 실제로 바뀌었는가.
  //   함수이기만 하면 통과하던 예전 판정(QA 지적 ⑤)을 대체한다.
  toggleDrivesState: toggleActuallyChangedState,
  // ★ D-패드 도달성 — Focusable 밖에 있으면 핸드헬드에서 **영영 누를 수 없다**(실기 실증).
  //   이름 하나가 아니라 상호작용 컴포넌트 **전부**를 본다(P4의 저장·확인 버튼도 자동으로 덮인다).
  toggleReachable,
  unreachable: reach.unreachable,
  // ★ 몇 개를 봤는지 같이 낸다 — **0개를 훑고 「전부 도달 가능」이라 말하는 것**이
  //   이 프로젝트가 반복해 당한 함정이다(컴포넌트 이름이 바뀌면 조용히 0이 된다).
  interactiveSeen: reach.seen,
  firstIncompleteIndex,
}));
