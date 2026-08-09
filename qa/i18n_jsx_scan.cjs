"use strict";
/**
 * `t()` 밖의 **사용자 가시 문자열**을 TypeScript **Program + TypeChecker**로 찾는다.
 *
 * ── 왜 두 번 갈아엎었나 (측정 기준의 이동 기록) ───────────────────────────────
 * 1판 정규식: *"중괄호 안의 홑 리터럴"* 하나만 봤다. `{"A" + "B"}`에 뚫렸다.
 * 2판 구문 AST + 이름표 `Map`: 연결식·join은 잡았지만 **이름 철자로 Map을 조회**했다.
 *     그래서 Codex가 한 쌍으로 뚫었다 —
 *       · 거짓 음성: `const QA_LEAKED = "A" + "B"` → initializer가 직접 리터럴이 아니라 미등록
 *       · 거짓 양성: 동명 매개변수 `function F({ QA_SHADOWED }: { QA_SHADOWED: number })`를
 *                    모듈 상수로 오인 — 실제 렌더값은 숫자 `42`인데 위반으로 셌다
 *     **오탐도 거짓 검사다.** 철자는 바인딩이 아니다.
 * 3판(현재): 판정을 철자에서 **의미**로 옮긴다.
 *       · 바인딩은 `checker.getSymbolAtLocation()`이 가른다 — 섀도잉이 원리적으로 안 생긴다
 *       · 값은 **상수 접기**로 구한다(리터럴 · 템플릿 · 이항 `+` · 삼항 · 괄호 · `as const`,
 *         식별자는 심볼을 타고 재귀). "직접 리터럴인가"가 아니라 "무슨 값이 되는가"를 묻는다
 *
 * ── 정직한 잔여 표면 (닫지 못한 것) ──────────────────────────────────────────
 *   · 런타임에만 정해지는 값: `String(x)` · `arr[i]` · 함수 반환 · 외부 JSON import
 *   · `.concat()`·`reduce()`·전개 연산자로 조립한 문자열 — 접기 규칙에 없다
 *   · 접기 한도(`FOLD_DEPTH`)를 넘는 긴 식별자 사슬
 *   · `dangerouslySetInnerHTML`, DOM 직접 조작 — JSX 트리를 거치지 않는다
 *   이것들은 정적으로 못 잰다. **못 재는 것을 통과로 세지 않기 위해 여기 적는다.**
 *
 * 출력: 위반 1건당 JSON 한 줄 `{file, line, kind, text}`. 없으면 아무것도 안 찍는다.
 * 실행: node qa/i18n_jsx_scan.cjs <file> [file…]
 */
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

/** 화면에 뜨는 prop. 여기 실린 문자열은 사용자가 읽는다. */
const VISIBLE_PROPS = new Set([
  "title", "label", "strTitle", "strDescription", "strOKButtonText", "strCancelButtonText",
  "body", "placeholder", "tooltip",
]);
/** 번역을 거친 값을 만드는 함수. 이 호출 안의 리터럴은 **키**이지 문구가 아니다. */
const TRANSLATORS = new Set(["t", "tCode"]);
/** 식별자 사슬을 타고 들어가는 깊이 한도. 순환·폭발을 막는다. */
const FOLD_DEPTH = 6;
/** 한 표현식에서 접어 낼 수 있는 값의 최대 개수(삼항·연결식 조합 폭발 방지). */
const FOLD_MAX = 32;

/** 비교 연산 — `x === "dock"`의 `"dock"`은 화면 글자가 아니라 **판정값**이다. */
const COMPARISONS = new Set([
  ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken,
  ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken,
]);

/** 사람이 읽는 글자: 한글, 또는 라틴 문자 2자 이상. 보간(`${…}`)은 먼저 걷어낸다. */
function isHuman(text) {
  return /[가-힣]|[A-Za-z]{2,}/.test(String(text).replace(/\$\{[^}]*\}/g, ""));
}

function isTranslatorCall(node) {
  return ts.isCallExpression(node)
    && ts.isIdentifier(node.expression)
    && TRANSLATORS.has(node.expression.text);
}

/** 그 배열 리터럴이 `…join(…)`의 수신자인가. `as const`·괄호를 타고 올라가서 본다. */
function isJoined(array) {
  let node = array;
  while (node.parent && (ts.isAsExpression(node.parent) || ts.isParenthesizedExpression(node.parent))) {
    node = node.parent;
  }
  const parent = node.parent;
  return !!parent && ts.isPropertyAccessExpression(parent)
    && parent.expression === node && parent.name.text === "join";
}

/**
 * 식별자가 가리키는 **선언**을 심볼로 해석한다. 철자가 아니라 바인딩이다.
 * 매개변수·구조분해 바인딩이면 `null`을 돌려준다 — 그건 상수가 아니라 **다른 바인딩**이고,
 * 그것을 모듈 상수로 오인한 것이 2판의 거짓 양성이었다.
 */
function resolveConstDeclaration(identifier, checker) {
  let symbol = checker.getSymbolAtLocation(identifier);
  if (!symbol) return null;
  if (symbol.flags & ts.SymbolFlags.Alias) {
    try { symbol = checker.getAliasedSymbol(symbol); } catch (_e) { /* 해석 불가 — 그대로 둔다 */ }
  }
  const declarations = symbol.declarations || [];
  for (const decl of declarations) {
    // ★ 여기가 섀도잉을 가르는 지점이다. 같은 철자여도 바인딩이 다르면 값이 없다.
    if (ts.isParameter(decl) || ts.isBindingElement(decl)) return null;
    if (ts.isVariableDeclaration(decl) && decl.initializer) return decl.initializer;
    if (ts.isPropertyAssignment(decl) && decl.initializer) return decl.initializer;
    if (ts.isEnumMember(decl) && decl.initializer) return decl.initializer;
  }
  return null;
}

/**
 * 그 표현식이 될 수 있는 **문자열 값들**. 못 정하면 빈 배열.
 *
 * ★ 2판은 *"initializer가 직접 문자열 리터럴인가"*만 봤다. 그래서 `"A" + "B"`로 만든 상수를
 *   놓쳤다(Codex의 `QA_LEAKED`). 여기서는 **값을 계산**한다 — 형태가 아니라 결과를 본다.
 */
/** 그 표현식이 가리키는 **배열 리터럴**. 식별자면 심볼을 타고 초기화식까지 따라간다. */
function resolveArrayLiteral(node, checker, depth) {
  if (!node || depth < 0) return null;
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node)
      || ts.isTypeAssertionExpression(node)) {
    return resolveArrayLiteral(node.expression, checker, depth);
  }
  if (ts.isArrayLiteralExpression(node)) return node;
  if (ts.isIdentifier(node)) {
    const initializer = resolveConstDeclaration(node, checker);
    return initializer ? resolveArrayLiteral(initializer, checker, depth - 1) : null;
  }
  return null;
}

function foldValues(node, checker, depth) {
  if (!node || depth < 0) return [];
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return [node.text];
  if (ts.isParenthesizedExpression(node)) return foldValues(node.expression, checker, depth);
  if (ts.isAsExpression(node) || ts.isTypeAssertionExpression(node)
      || (ts.isSatisfiesExpression && ts.isSatisfiesExpression(node))) {
    return foldValues(node.expression, checker, depth);
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = foldValues(node.left, checker, depth);
    const right = foldValues(node.right, checker, depth);
    const out = [];
    for (const a of left) for (const b of right) if (out.length < FOLD_MAX) out.push(a + b);
    return out;
  }
  if (ts.isConditionalExpression(node)) {
    // 어느 가지든 화면에 뜰 수 있다 — 둘 다 후보로 센다.
    return foldValues(node.whenTrue, checker, depth).concat(
      foldValues(node.whenFalse, checker, depth)).slice(0, FOLD_MAX);
  }
  if (ts.isTemplateExpression(node)) {
    let acc = [node.head.text];
    for (const span of node.templateSpans) {
      const parts = foldValues(span.expression, checker, depth);
      const next = [];
      for (const a of acc) {
        // 보간을 못 접으면 그 자리를 `${}`로 남긴다 — `isHuman`이 걷어낸다.
        for (const b of (parts.length ? parts : ["${}"])) {
          if (next.length < FOLD_MAX) next.push(a + b + span.literal.text);
        }
      }
      acc = next;
    }
    return acc;
  }
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
      && node.expression.name.text === "join") {
    // `["A","B"].join(" ")` — 이어 붙인 결과가 그대로 렌더된다.
    // ★★ 2026-08-07 3회차: 예전에는 수신자가 **직접 배열 리터럴**일 때만 접었다. Codex가
    //    배열을 상수에 담아 `QA_FINAL_PARTS.join("")`으로 부르자 그대로 통과했다 —
    //    한 글자씩 쪼개 놓아 `isHuman`("라틴 2자 이상")까지 정확히 우회했다.
    //    수신자도 **심볼을 타고** 배열 리터럴까지 따라간다(식별자 사슬 = 값의 일부다).
    const array = resolveArrayLiteral(node.expression.expression, checker, depth);
    if (array) {
      const sep = node.arguments.length ? (foldValues(node.arguments[0], checker, depth)[0] ?? "") : ",";
      const parts = [];
      for (const element of array.elements) {
        const values = foldValues(element, checker, depth);
        if (!values.length) return [];        // 하나라도 못 접으면 정적 값이 아니다
        parts.push(values[0]);
      }
      return [parts.join(sep)];
    }
  }
  if (ts.isIdentifier(node)) {
    const initializer = resolveConstDeclaration(node, checker);
    return initializer ? foldValues(initializer, checker, depth - 1) : [];
  }
  return [];
}

/**
 * 한 표현식 안에서 **번역을 거치지 않은** 사람 글자를 모은다.
 * `t()`/`tCode()` 호출은 통째로 건너뛴다 — 그 안의 리터럴은 키다.
 */
function untranslatedText(expr, checker) {
  const found = [];
  const visit = (node) => {
    if (isTranslatorCall(node)) return;                     // 번역을 거친 가지다 — 안 본다
    // ★ **중첩 JSX로 내려가지 않는다.** 내려가면 안쪽 `style={{ display: "flex" }}`까지
    //   "가시 문자열"로 세어 오탐이 쏟아진다. 안쪽 JSX는 바깥 visitor가 다시 훑는다.
    if (node !== expr && (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)
        || ts.isJsxFragment(node) || ts.isJsxExpression(node) || ts.isJsxAttribute(node))) {
      return;
    }
    // 배열 리터럴 — **`join()`으로 이어 붙일 때만** 화면 글자가 된다.
    //   `(["dock","internal"] as const).map(…)`의 원소는 값 목록이지 문구가 아니다.
    if (ts.isArrayLiteralExpression(node) && !isJoined(node)) {
      for (const element of node.elements) {
        if (!ts.isStringLiteral(element) && !ts.isNoSubstitutionTemplateLiteral(element)) visit(element);
      }
      return;
    }
    // 비교 연산의 문자열 피연산자는 값이다 — 세면 `profile === "dock"`이 위반이 된다.
    if (ts.isBinaryExpression(node) && COMPARISONS.has(node.operatorToken.kind)) {
      for (const side of [node.left, node.right]) {
        if (!ts.isStringLiteral(side) && !ts.isNoSubstitutionTemplateLiteral(side)) visit(side);
      }
      return;
    }
    if (ts.isIdentifier(node)) {
      // `obj.name`의 `name`은 속성 이름이지 변수가 아니다.
      const parent = node.parent;
      const isPropertyName = parent
        && ((ts.isPropertyAccessExpression(parent) && parent.name === node)
          || (ts.isPropertyAssignment(parent) && parent.name === node));
      if (!isPropertyName) {
        for (const value of foldValues(node, checker, FOLD_DEPTH)) {
          if (isHuman(value)) found.push(value);
        }
      }
      return;                                               // 식별자 아래로는 더 볼 것이 없다
    }
    // 직접 쓰인 리터럴·연결식·템플릿은 값으로 접어서 본다(형태가 아니라 결과).
    for (const value of foldValues(node, checker, FOLD_DEPTH)) {
      if (isHuman(value)) found.push(value);
    }
    ts.forEachChild(node, visit);
  };
  visit(expr);
  return [...new Set(found)];
}

function scan(sourceFile, checker) {
  const file = sourceFile.fileName;
  const hits = [];
  const at = (node) => sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;

  const visit = (node) => {
    // ① JSX 텍스트 노드 — `<div>보이는 글자</div>`
    if (ts.isJsxText(node) && isHuman(node.text)) {
      hits.push({ file, line: at(node), kind: "JSX_TEXT", text: node.text.trim() });
    }
    // ② JSX **자식 자리**의 중괄호 표현식 — 연결식·join·변수 우회가 전부 여기로 온다
    if (ts.isJsxExpression(node) && node.expression && node.parent
        && (ts.isJsxElement(node.parent) || ts.isJsxFragment(node.parent))) {
      for (const found of untranslatedText(node.expression, checker)) {
        hits.push({ file, line: at(node), kind: "JSX_CHILD_EXPR", text: found });
      }
    }
    // ③ 사용자가 읽는 prop
    if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name)
        && VISIBLE_PROPS.has(node.name.text) && node.initializer) {
      const init = node.initializer;
      const expr = ts.isJsxExpression(init) ? init.expression : init;
      if (expr) {
        for (const found of untranslatedText(expr, checker)) {
          hits.push({ file, line: at(node), kind: `PROP:${node.name.text}`, text: found });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return hits;
}

const files = process.argv.slice(2).map((f) => path.resolve(f));   // 호출자의 cwd 기준
if (files.length === 0) {
  console.error("사용법: node qa/i18n_jsx_scan.cjs <file> [file…]");
  process.exit(2);
}

// ★ `createProgram`이 있어야 TypeChecker가 나오고, TypeChecker가 있어야 **바인딩**을 가른다.
//   `noLib`로 표준 라이브러리는 건너뛴다 — 우리가 쓰는 것은 타입 추론이 아니라 심볼 해석이다.
const program = ts.createProgram(files, {
  jsx: ts.JsxEmit.React,
  target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  allowJs: false,
  noEmit: true,
  noLib: true,
  skipLibCheck: true,
  types: [],
});
const checker = program.getTypeChecker();
const wanted = new Set(files);
let scanned = 0;
for (const sourceFile of program.getSourceFiles()) {
  if (!wanted.has(path.resolve(sourceFile.fileName))) continue;
  scanned += 1;
  for (const hit of scan(sourceFile, checker)) {
    console.log(JSON.stringify({ ...hit, file: path.relative(projectRoot, hit.file) }));
  }
}
if (scanned !== files.length) {
  // ★ 대상에 닿지 못한 검사는 통과가 아니다 — 조용히 0건을 내지 않는다.
  console.error(`대상 ${files.length}개 중 ${scanned}개만 훑었다 — 검사가 대상에 닿지 못했다`);
  process.exit(3);
}
