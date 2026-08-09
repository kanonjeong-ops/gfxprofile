"use strict";
/**
 * 프론트 불변식을 **의미로** 재는 프로브 (2026-08-05 QA 3회차 대응).
 *
 * 왜 만들었나: E1("일괄 버튼은 실행 중인 게임 때문에 비활성화되지 않는다")을 정규식으로 지키려다
 * 세 라운드 연속 뚫렸다 — 파생 변수 → 값 오염 → `.ts` helper → 예외 마커 스푸핑.
 * **표면 문법을 아무리 좁혀도 "의미"와는 다르다.** 그래서 실제로 렌더해서 버튼의 `disabled`를 본다.
 * 이 방식은 우회 수단(변수·헬퍼·별칭·마커)을 가리지 않는다 — 무엇을 하든 결과가 disabled면 잡힌다.
 *
 * 실행: node qa/frontend_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 * 출력: JSON 한 줄. { buttons:[{label,disabled}], langReady, missing, sawCounts }
 *
 * ⚠️ 이 프로브는 React를 흉내 낸다(훅 슬롯 순서에 의존). 그래서 **"측정하려던 경로에 닿았는지"**를
 *   `sawCounts`(라벨에 주입한 수가 보이는가)로 같이 내보낸다 — 호출부가 그걸 확인하지 않으면
 *   컴포넌트 구조가 바뀌었을 때 **아무것도 못 재고 통과**한다. 이 프로젝트에서 세 번 난 사고다.
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

// 주입할 현황: **실행 중인 게임이 1개 있고, 두 프로필 다 대상이 있다.**
// E1이 지키는 상황이 정확히 이것이다 — 이때 두 버튼은 눌려야 한다.
const COUNTS = { total: 9, dock_ready: 9, internal_ready: 8, running: 1, incomplete: 1 };

// ★ 2026-08-06 QA 4회차: `typeof window !== "undefined" ? {disabled:true} : {}` 처럼
//   **프로브가 브라우저가 아니라는 사실**을 신호로 삼아 위반을 숨기는 코드가 나왔다.
//   전역을 흉내 내 그 신호를 없앤다. (일반해는 아니다 — 한계는 테스트 문서에 적었다.)
globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };
globalThis.document = globalThis.document || { title: "gfxprofile-probe" };

const buttons = [];
const applyCalls = [];
let missing = [];
let hookSlot = 0;

function h(type, props, ...children) {
  if (typeof type === "function") {
    // ErrorBoundary는 **클래스 컴포넌트**다(설계 E13) — 함수처럼 부르면 TypeError가 난다.
    // 정상 경로에서는 경계가 자식을 그대로 통과시키므로 render()를 한 번 부르면 된다.
    // (경계의 실동작 자체는 `test_error_boundary.py`가 던져 보며 따로 잰다.)
    if (type.prototype && type.prototype.isReactComponent) {
      return new type({ ...(props || {}), children }).render();
    }
    return type({ ...(props || {}), children });
  }
  const node = { type, props: props || {}, children };
  if (type && type.__kind === "ButtonItem") buttons.push(node);
  return node;
}

function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node.children) return [].concat(node.children).map(textOf).join("");
  return "";
}

/** ErrorBoundary가 React 클래스 컴포넌트다(설계 E13) — 목에도 기반 클래스가 있어야 한다. */
class Component {
  constructor(props) { this.props = props; this.state = {}; }
}
Component.prototype.isReactComponent = {};

const modules = {
  react: {
    Component,
    useCallback: (fn) => fn,
    useEffect: () => {},
    useState(initial) {
      const slot = hookSlot++;
      // 슬롯 0 = langReady(true로 강제), 슬롯 1 = overview(현황 주입).
      // 어긋나면 sawCounts가 false로 나오고 호출부가 실패로 판정한다.
      if (slot === 0) return [true, () => {}];
      if (slot === 1) return [{ games: [], counts: COUNTS }, () => {}];
      return [initial, () => {}];
    },
  },
  "@decky/api": {
    definePlugin: (fn) => fn,
    // 전체 화면 route 등록. 프로브는 QAM 패널만 렌더하므로 호출 사실만 받아 둔다.
    routerHook: { addRoute: () => {}, removeRoute: () => {} },
    toaster: { toast: () => {} },
    useQuickAccessVisible: () => true,
  },
  "./rpc": {
    applyAll: (profile) => {
      applyCalls.push(profile);
      return Promise.resolve({ ok: true, data: { results: [], counts: {} } });
    },
    getOverview: () => Promise.resolve({ ok: true, data: { games: [], counts: COUNTS } }),
    uiHello: () => Promise.resolve({ ok: true, data: { lang: "en" } }),
  },
  "./i18n": {
    // 라벨을 그대로 돌려주되 자리표시자는 채운다 — 라벨에서 개수를 확인해야 하기 때문이다.
    t: (key, params) =>
      params ? String(key) + " " + Object.values(params).join(" ") : String(key),
    // ★ P5: `tCode`(코드→문구 단일 관문)도 목에 넣는다 — 없으면 소비처가 TypeError로
    //   죽고 "로직 FAIL"처럼 보인다(인계 문서 5-B의 낡은 목 함정).
    tCode: (code) => String(code),
    setLang: () => {},
  },
  "./deckyui": {
    ButtonItem: { __kind: "ButtonItem" },
    Focusable: { __kind: "Focusable" },
    Navigation: { Navigate: () => {} },
    ToggleField: { __kind: "ToggleField" },
    DialogButton: { __kind: "DialogButton" },
    ModalRoot: { __kind: "ModalRoot" },
    PanelSection: { __kind: "PanelSection" },
    PanelSectionRow: { __kind: "PanelSectionRow" },
    showModal: () => {},
    titleClass: () => undefined,
    uicheckMissing: () => missing,
  },
};

function loadModule(relPath) {
  const file = path.join(srcDir, relPath);
  const source = fs.readFileSync(file, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React,
      jsxFactory: "h",
      jsxFragmentFactory: "Fragment",   // <>…</>가 React.Fragment로 나가지 않게
      esModuleInterop: true,
    },
    fileName: file,
  }).outputText;

  const exports = {};
  const req = (name) => {
    if (modules[name]) return modules[name];
    // 소스 안의 다른 모듈(예: 우회로 새로 만든 helper)은 **실제로 로드한다** —
    // helper에 숨겨진 로직도 그대로 실행되어야 의미를 잴 수 있다.
    if (name.startsWith(".")) {
      // 확장자를 붙여 실제 파일을 찾는다 — `.tsx`(컴포넌트)와 `.ts`(로직) 둘 다 있다.
      const base = name.replace(/^\.\//, "");
      for (const ext of [".tsx", ".ts"]) {
        if (fs.existsSync(path.join(srcDir, base + ext))) return loadModule(base + ext);
      }
      throw new Error("모듈을 찾지 못했다: " + name);
    }
    throw new Error("unmocked module: " + name);
  };
  const Fragment = { __kind: "Fragment" };
  new Function("exports", "require", "module", "h", "Fragment", compiled)(exports, req, { exports }, h, Fragment);
  return exports;
}

const mod = loadModule("index.tsx");
const plugin = mod.default();
const content = plugin.content;
const rendered = typeof content === "object" && content.type ? content : null;
void rendered;

// 렌더 트리를 훑어 `pointerEvents:"none"` 아래에 일괄 버튼이 있는지 본다 —
// 버튼을 활성으로 두고 조상에서 클릭을 죽이는 우회를 잡는다.
function findBlocked(node, blocked) {
  if (!node || typeof node !== "object") return false;
  // ★ `.map()`이 만든 배열은 **자식 배열 안에 배열로** 들어온다. 이걸 건너뛰면 일괄 버튼 행이
  //   통째로 순회에서 빠진다(실제로 그래서 pointerEvents 우회를 못 잡았다).
  if (Array.isArray(node)) return node.some((k) => findBlocked(k, blocked));
  const style = (node.props && node.props.style) || {};
  const nowBlocked = blocked || style.pointerEvents === "none";
  if (node.type && node.type.__kind === "ButtonItem" && nowBlocked) return true;
  const kids = [].concat(node.children || []);
  return kids.some((k) => findBlocked(k, nowBlocked));
}

const labels = buttons.map((b) => textOf(b.children).trim());
// ★ 눌러 본다. `disabled=false`인데 아무 일도 안 하는 버튼은 **눌리지 않는 것과 같다.**
buttons.forEach((b) => {
  try {
    if (typeof b.props.onClick === "function") b.props.onClick();
  } catch (e) {
    /* 클릭 자체가 던지면 그것도 동작하지 않는 것이다 — applyCalls로 판정된다 */
  }
});
console.log(
  JSON.stringify({
    buttons: buttons.map((b, i) => ({ label: labels[i], disabled: !!b.props.disabled })),
    langReady: true,
    missing,
    // ★ 측정 경로에 닿았는지 — 주입한 dock_ready(9)가 라벨에 보이는가.
    sawCounts: labels.some((l) => l.includes("9")),
    // 각 버튼을 눌렀을 때 실제로 일괄 적용이 호출됐는가(대리 지표가 아니라 의미).
    applyCalls,
    // 조상 스타일로 클릭이 막혀 있는가.
    styleBlocked: findBlocked(content, false),
  }),
);
