"use strict";
/**
 * **렌더 프로브 공용 하네스** — 미니 React(진짜 훅) + 미니 렌더러 + 모듈 로더.
 *
 * ★★ 왜 공용인가: P12까지 프로브마다 자기 하네스를 들고 있었고, 그중 몇은 훅 슬롯 번호로
 *   상태를 주입하는 방식이라 **파일에서 useState 하나만 옮겨도 검사가 엉뚱한 값을 봤다.**
 *   여기 한 벌로 모으면 ① 재렌더·이펙트 정리가 도는 진짜 훅을 모든 프로브가 공유하고
 *   ② 하네스 자체의 버그를 한 번만 고친다. (`popup_shell_probe.cjs`가 P12에서 만든 것을
 *   P13에서 파일로 꺼낸 것이고, 동작은 그대로다 — `test_popup_shell`이 그 동일성을 잰다.)
 *
 * ⚠️ 실물 React가 아니다. 여기서 잴 수 있는 것은 **계약**(무엇을 그리는가·무엇이 호출되는가)
 *   까지이고, "보인다·눌린다"는 실기의 몫이다.
 */
const fs = require("fs");
const path = require("path");

// ── 미니 React ───────────────────────────────────────────────────────────────
//
// 슬롯 번호로 고정값을 돌려주는 목으로는 **입력에 따라 값이 바뀌는 계약**을 잴 수 없다.
// 그래서 재렌더·이펙트 정리까지 도는 아주 작은 훅 런타임을 둔다 — 한 번에 **훅을 쓰는
// 컴포넌트 하나**만 호스팅한다.
let host = null;

class Component {
  constructor(props) { this.props = props; this.state = {}; }
  setState(s) { Object.assign(this.state, typeof s === "function" ? s(this.state) : s); }
}

const react = {
  Component,
  useState(initial) {
    // ★ 세터는 **자기 호스트에 묶는다.** 전역 `host`를 나중에 읽으면 렌더가 끝난 뒤(=클릭·
    //   onChange 시점)에는 null이라 죽는다 — 실제로 그렇게 죽었다.
    const owner = host;
    const slot = owner.slot();
    if (!(slot in owner.hooks)) owner.hooks[slot] = typeof initial === "function" ? initial() : initial;
    return [
      owner.hooks[slot],
      (v) => { owner.hooks[slot] = typeof v === "function" ? v(owner.hooks[slot]) : v; owner.render(); },
    ];
  },
  useRef(initial) {
    const owner = host;
    const slot = owner.slot();
    if (!(slot in owner.hooks)) owner.hooks[slot] = { current: initial };
    return owner.hooks[slot];
  },
  useCallback(fn, deps) {
    const owner = host;
    const slot = owner.slot();
    const prev = owner.hooks[slot];
    if (!prev || !deps || !prev.deps || deps.some((d, i) => d !== prev.deps[i])) {
      owner.hooks[slot] = { deps, fn };
    }
    return owner.hooks[slot].fn;
  },
  useMemo(fn, deps) {
    const owner = host;
    const slot = owner.slot();
    const prev = owner.hooks[slot];
    if (!prev || !deps || !prev.deps || deps.some((d, i) => d !== prev.deps[i])) {
      owner.hooks[slot] = { deps, value: fn() };
    }
    return owner.hooks[slot].value;
  },
  useEffect(fn, deps) {
    const owner = host;
    const slot = owner.slot();
    const prev = owner.hooks[slot];
    const changed = !prev || !deps || !prev.deps || deps.some((d, i) => d !== prev.deps[i]);
    if (!changed) return;
    owner.pending.push(() => {
      if (prev && prev.cleanup) prev.cleanup();
      // ★ 슬롯을 **먼저** 기록한다: 이펙트 본문이 동기적으로 setState를 부르면(실물 코드가
      //   그런다 — `load()`의 `setBusy(true)`) 그 자리에서 재렌더가 돌고, 그때 이 슬롯이
      //   비어 있으면 같은 이펙트가 다시 큐에 들어가 **무한 재귀**가 된다(실제로 그랬다).
      owner.hooks[slot] = { deps, cleanup: null };
      const cleanup = fn();
      owner.hooks[slot].cleanup = typeof cleanup === "function" ? cleanup : null;
    });
  },
};

function makeHost(renderFn) {
  const h0 = {
    hooks: [],
    pending: [],
    index: 0,
    output: null,
    slot() { return this.index++; },
    render() {
      const prev = host;
      host = h0;
      h0.index = 0;
      h0.pending = [];
      try {
        h0.output = renderFn();
        const queued = h0.pending;
        h0.pending = [];
        queued.forEach((run) => run());
      } finally {
        host = prev;
      }
      return h0.output;
    },
    /** 언마운트 — 이펙트 정리를 실제로 돌린다(입력 스냅샷이 여기서 나간다). */
    unmount() {
      h0.hooks.forEach((slot) => { if (slot && slot.cleanup) slot.cleanup(); });
    },
  };
  return h0;
}

// ── 미니 렌더러 ──────────────────────────────────────────────────────────────
const Fragment = { __kind: "Fragment" };

function isClassComponent(type) {
  return typeof type === "function" && type.prototype && type.prototype instanceof Component;
}

function nameOf(type) {
  if (typeof type === "string") return type;
  if (type && type.__kind) return type.__kind;
  if (typeof type === "function") return type.name || "anonymous";
  return String(type);
}

/**
 * 컴포넌트를 그 자리에서 그린다.
 *
 * ⚠️ 실물 React는 `<X/>`를 **엘리먼트만 만들고** 나중에 그리지만 이 프로브는 즉시 그린다.
 *   그래서 렌더 밖(클릭 핸들러 안)에서 만들어지는 엘리먼트 — 예: `showModal(<SpecConfirmModal/>)` —
 *   도 여기로 온다. 그때 훅을 걸 호스트가 없으면 **컴포넌트가 죽고**, 그 죽음이 게이트의
 *   try/catch에 잡혀 *"모달을 못 띄웠다"*로 오독된다(실제로 그렇게 오독했다).
 *   → 호스트가 없으면 **임시 호스트**를 만들어 그 안에서 그린다.
 */
function renderComponent(type, merged) {
  const draw = () => (isClassComponent(type) ? new type(merged).render() : type(merged));
  if (host) return draw();
  return makeHost(draw).render();
}

function h(type, props, ...children) {
  const flat = children.flat(9).filter((c) => c !== null && c !== undefined && c !== false);
  const merged = { ...(props || {}) };
  if (flat.length) merged.children = flat.length === 1 ? flat[0] : flat;
  const node = { type, props: merged, children: flat, name: nameOf(type) };
  if (typeof type === "function") node.rendered = renderComponent(type, merged);
  return node;
}

/**
 * 트리 전체(자식 + 컴포넌트 렌더 결과 + prop으로 넘어간 엘리먼트)를 훑는다.
 *
 * ★★ **같은 노드는 한 번만 센다**(2026-08-12 P13에서 발견): 이 렌더러는 함수 컴포넌트를 그
 *   자리에서 그려 결과를 `.rendered`에 매달아 두는데, 부모의 `children`으로 넘어간 엘리먼트가
 *   자식 컴포넌트의 렌더 결과 **안에도 같은 객체로** 나타난다(`<GfxPopup>{body}</GfxPopup>`의
 *   body가 그렇다). 중복을 안 걸러 내면 카드 4장이 24장으로 세어지고, **순서·개수·인덱스로
 *   클릭하는 검사가 전부 엉뚱한 것을 집는다.** 노드 동일성(객체 참조)으로 거른다.
 */
function walk(node, visit) {
  const seen = new Set();
  const go = (n, ancestors) => {
    if (n === null || n === undefined || typeof n !== "object") return;
    if (Array.isArray(n)) { n.forEach((x) => go(x, ancestors)); return; }
    if (!n.type) return;
    if (seen.has(n)) return;
    seen.add(n);
    visit(n, ancestors);
    const next = ancestors.concat([n]);
    n.children.forEach((c) => go(c, next));
    // props로 넘어간 엘리먼트(strDescription 등)도 화면의 일부다
    Object.entries(n.props).forEach(([key, value]) => {
      if (key === "children") return;
      if (value && typeof value === "object" && value.type) go(value, next);
    });
    if (n.rendered) go(n.rendered, next);
  };
  go(node, []);
}

function find(root, name) {
  let hit = null;
  walk(root, (node, ancestors) => { if (!hit && node.name === name) hit = { node, ancestors }; });
  return hit;
}

function findAll(root, name) {
  const out = [];
  walk(root, (node, ancestors) => { if (node.name === name) out.push({ node, ancestors }); });
  return out;
}

/** 화면에 보이는 글자 전부 — 자식 문자열 + 가시 prop. 두 렌더러 대조의 기준값이다. */
const VISIBLE_PROPS = ["strTitle", "strOKButtonText", "strCancelButtonText", "label", "title"];
function texts(root) {
  const out = [];
  walk(root, (node) => {
    node.children.forEach((c) => { if (typeof c === "string") out.push(c); });
    VISIBLE_PROPS.forEach((key) => {
      if (typeof node.props[key] === "string") out.push(node.props[key]);
    });
  });
  return out;
}

function buttons(root) {
  return findAll(root, "DialogButton").map(({ node }) => ({
    label: node.children.filter((c) => typeof c === "string").join(" "),
    onClick: node.props.onClick,
    disabled: !!node.props.disabled,
    style: node.props.style || {},
    node,
  }));
}

// ── 모듈 로더 ────────────────────────────────────────────────────────────────
/**
 * `src/`의 TypeScript를 그 자리에서 트랜스파일해 불러온다.
 *
 * @param srcDir  소스 디렉터리(음성 대조군은 **사본 경로**를 준다 — 원본을 절대 고치지 않는다)
 * @param modules 목 테이블. 여기 있는 이름은 실물 대신 목이 간다.
 */
function makeLoader(srcDir, modules) {
  const projectRoot = path.resolve(__dirname, "..");
  const ts = require(path.join(projectRoot, "node_modules", "typescript"));
  const cache = new Map();

  function load(rel, patch) {
    const key = rel + (patch ? "#patched" : "");
    if (cache.has(key)) return cache.get(key);
    const file = path.join(srcDir, rel);
    let source = fs.readFileSync(file, "utf8");
    if (patch) source = patch(source);
    const compiled = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.React, jsxFactory: "h", jsxFragmentFactory: "Fragment", esModuleInterop: true,
      }, fileName: file,
    }).outputText;
    const exports = {};
    cache.set(key, exports);
    const req = (name) => {
      if (modules[name]) return modules[name];
      if (name.startsWith(".")) {
        const base = name.replace(/^\.\//, "");
        for (const ext of ["", ".tsx", ".ts", ".json"]) {
          const p = path.join(srcDir, base + ext);
          if (fs.existsSync(p) && fs.statSync(p).isFile()) {
            // ★ 확장자는 **찾아낸 파일**로 판정한다 — 요청에 이미 `.json`이 붙어 있으면 빈
            //   확장자로 먼저 맞는데, 그때 TS 트랜스파일러에 넘기면 통째로 죽는다.
            return p.endsWith(".json") ? JSON.parse(fs.readFileSync(p, "utf8")) : load(base + ext);
          }
        }
      }
      throw new Error("unmocked: " + name);
    };
    new Function("exports", "require", "module", "h", "Fragment", compiled)(
      exports, req, { exports }, h, Fragment);
    return exports;
  }

  return load;
}

/** 마이크로태스크가 정착할 때까지 한 틱 기다린다(RPC 목이 Promise라 필요하다). */
const settle = () => new Promise((r) => setTimeout(r, 0));

module.exports = {
  Component, react, makeHost, h, Fragment, nameOf,
  walk, find, findAll, texts, buttons, makeLoader, settle,
};
