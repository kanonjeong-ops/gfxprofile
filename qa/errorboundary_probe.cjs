"use strict";
/**
 * `src/ui/ErrorBoundary.tsx`를 **실제로 던지게 해서** 재는 프로브 (설계 E13).
 *
 * grep으로 `componentDidCatch`가 있는지 세는 것은 검사가 아니다 — 있어도 아무것도 안 잡는
 * 구현이 통과한다. 여기서는 **자식이 throw하게 만들고** 폴백이 실제로 뜨는지,
 * 진단이 실제로 남는지, 정상 자식은 그대로 통과하는지를 본다.
 *
 * 재는 것:
 *   ① 자식이 throw → `getDerivedStateFromError`가 상태를 바꾸고 **폴백이 렌더된다**
 *   ② 폴백 문구가 **영어 고정**이다(한글 0자) · `RENDER_FAILED` 표지가 있다
 *   ③ 폴백이 **intrinsic 요소만** 쓴다 — `@decky/ui` 컴포넌트를 그리지 않는다
 *      (안전장치가 자기가 감시하는 실패에 걸리면 안 된다)
 *   ④ `componentDidCatch`가 `[gfxprofile] boundary where=…` 진단을 남긴다
 *   ⑤ **정상 자식은 그대로 통과**한다(경계가 정상 렌더를 가로채지 않는다)
 *   ⑥ 경계가 `t()`/i18n을 부르지 않는다 — 그것이 못 뜨는 상황이 여기로 오기 때문이다
 *
 * 실행: node qa/errorboundary_probe.cjs
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

// ── 미니 React — 클래스 컴포넌트가 실제로 필요하다 ───────────────────────────
function h(type, props, ...children) {
  return { type, props: props || {}, children: children.flat() };
}
const Fragment = { __kind: "Fragment" };

class Component {
  constructor(props) { this.props = props; this.state = {}; }
}
Component.prototype.isReactComponent = {};

const logs = [];
const originalError = console.error;

/**
 * React의 오류 경계 동작을 **최소한으로** 재현한다:
 * 자식을 그리다 throw하면 `getDerivedStateFromError`로 상태를 만들고,
 * `componentDidCatch`를 부른 뒤 **다시 그린다.**
 */
function renderNode(node) {
  if (node === null || node === undefined || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map(renderNode);
  const { type, props, children } = node;
  if (typeof type === "function") {
    const isClass = type.prototype && type.prototype.isReactComponent;
    if (isClass) {
      const instance = new type({ ...props, children });
      let tree;
      try {
        tree = renderNode(instance.render());
      } catch (err) {
        if (typeof type.getDerivedStateFromError !== "function") throw err;
        instance.state = { ...instance.state, ...type.getDerivedStateFromError(err) };
        if (typeof instance.componentDidCatch === "function") {
          instance.componentDidCatch(err, { componentStack: "\n    at QaThrowingChild" });
        }
        tree = renderNode(instance.render());
      }
      return { type: type.name || "Class", props, children: [tree] };
    }
    return renderNode(type({ ...props, children }));
  }
  return { type, props, children: children.map(renderNode) };
}

function texts(node, out = []) {
  if (typeof node === "string") { out.push(node); return out; }
  if (!node || typeof node !== "object") return out;
  if (Array.isArray(node)) { node.forEach((k) => texts(k, out)); return out; }
  [].concat(node.children || []).forEach((k) => texts(k, out));
  return out;
}

function tags(node, out = []) {
  if (!node || typeof node !== "object") return out;
  if (Array.isArray(node)) { node.forEach((k) => tags(k, out)); return out; }
  if (typeof node.type === "string") out.push(node.type);
  else if (node.type && node.type.__kind) out.push(`DECKY:${node.type.__kind}`);
  [].concat(node.children || []).forEach((k) => tags(k, out));
  return out;
}

// ── 모듈 로더 ────────────────────────────────────────────────────────────────
/** `argv[2]`로 다른 경계 파일을 지정할 수 있다 — §B의 변이 사본이 그 자리로 들어온다. */
const BOUNDARY = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(projectRoot, "src/ui/ErrorBoundary.tsx");

function load(file, modules) {
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React, jsxFactory: "h", jsxFragmentFactory: "Fragment", esModuleInterop: true,
    }, fileName: file,
  }).outputText;
  const exports = {};
  const req = (name) => {
    if (modules[name]) return modules[name];
    throw new Error("unmocked: " + name);
  };
  new Function("exports", "require", "module", "h", "Fragment", compiled)(
    exports, req, { exports }, h, Fragment);
  return exports;
}

function main() {
  const out = {};
  const source = fs.readFileSync(BOUNDARY, "utf8");

  // ⑥ 경계가 i18n·@decky/ui에 의존하지 않는다 — 의존하면 그것이 못 뜰 때 폴백도 못 뜬다.
  out.imports = [...source.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);

  const { ErrorBoundary } = load(BOUNDARY, { react: { Component } });
  out.isClassComponent = !!(ErrorBoundary.prototype && ErrorBoundary.prototype.isReactComponent);
  out.hasDerived = typeof ErrorBoundary.getDerivedStateFromError === "function";
  out.hasDidCatch = typeof ErrorBoundary.prototype.componentDidCatch === "function";

  // ⑤ 정상 자식 — 경계를 그대로 통과한다
  console.error = (...args) => logs.push(args.map(String).join(" "));
  try {
    const okChild = () => h("div", null, "QA_NORMAL_CHILD");
    const okTree = renderNode(h(ErrorBoundary, { where: "qa-normal" }, h(okChild, null)));
    out.normalTexts = texts(okTree);
    out.normalLogs = logs.length;

    // ① 자식이 throw — 폴백이 떠야 한다
    logs.length = 0;
    const boom = () => { throw new Error("QA_SYNTHETIC_RENDER_FAILURE"); };
    const failTree = renderNode(h(ErrorBoundary, { where: "qa-boom" }, h(boom, null)));
    const failText = texts(failTree).join(" ");
    out.fallbackText = failText.trim();
    out.fallbackShown = failText.includes("RENDER_FAILED");
    // ② 영어 고정 — 한글이 한 자라도 있으면 t()를 거친 것이거나 번역 대상이 된 것이다
    out.fallbackHasHangul = /[가-힣]/.test(failText);
    // ③ intrinsic 요소만 — @decky/ui 컴포넌트를 그리면 그것이 undefined일 때 폴백도 죽는다
    out.fallbackTags = [...new Set(tags(failTree))];
    // ④ 진단
    out.diagLogs = logs.slice();
    out.diagTagged = logs.some((l) => l.includes("[gfxprofile] boundary") && l.includes("qa-boom"));
    out.diagHasError = logs.some((l) => l.includes("QA_SYNTHETIC_RENDER_FAILURE"));
  } finally {
    console.error = originalError;
  }

  console.log(JSON.stringify(out));
}

main();
