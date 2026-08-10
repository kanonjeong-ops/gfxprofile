"use strict";
/**
 * 「게임 추가」 탭(P6)을 **의미로** 재는 프로브.
 *
 * 재는 것 — 전부 *"눌러 보고 결과를 본다"*이지 grep이 아니다(이 프로젝트는 거짓 검사에 6번 뚫렸다):
 *   ① 0건 안내가 *"게임 없음"*이 아니라 *"자동 탐지가 못 찾았을 뿐"* 키다 (결정 8-a)
 *   ② registered 기본 필터가 **실제로** 걸러 내고, 토글이 상태를 **실제로** 바꾼다
 *   ③ confident 일괄 등록 버튼이 대상 수만큼 뜨고 눌리면 RPC가 나간다 (대상 0이면 버튼이 없다)
 *   ④ confident 단일 매치는 **선택기 없이 1탭**으로 등록된다 (모달 0회·선택기 0회)
 *   ⑤ `.sav`를 골라도 등록되지 않고 **거부 코드가 화면에 뜬다**
 *   ⑥ 선택기 취소가 **조용하다** (등록 0회 · note 0건 · unhandled rejection 0건)
 *   ⑦ D-패드 도달성 — 상호작용 컴포넌트가 전부 Focusable 자손인가
 *   ⑧ `filepicker.ts` **실물**: 취소(reject)를 null로 삼키고, 백엔드에 `realpath`가 아니라 `path`를 넘긴다
 *
 * 실행: node qa/discover_probe.cjs [게임수]   (기본 12)
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));
const N = Number(process.argv[2] || 12);

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ★ 취소가 조용한지는 **이것으로만** 잴 수 있다. `.then`만 붙인 코드는 여기 카운터가 올라간다.
let unhandled = 0;
process.on("unhandledRejection", () => { unhandled += 1; });

// ── 합성 데이터 ──────────────────────────────────────────────────────────────
function makeEntries(n) {
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const registered = i % 5 === 0;
    const confident = i % 7 !== 1;
    const appid = String(100000 + i);
    const cands = [];
    const count = confident ? 1 : 3;
    for (let c = 0; c < count; c += 1) {
      cands.push({
        path: `/lib/steamapps/compatdata/${appid}/pfx/drive_c/users/steamuser/AppData/Local/G${i}/cand${c}.ini`,
        tier: confident ? 1 : 3,
        size: 100 + c,
        mtime_label: "2026-08-01",
      });
    }
    out.push({
      appid,
      name: `Game ${String(n - i).padStart(3, "0")}`,
      library: "/lib",
      confident,
      registered,
      candidate_count: count,
      best: confident ? cands[0] : null,
      candidates: confident ? [] : cands,
    });
  }
  return out;
}

function makeCounts(entries) {
  return {
    total: entries.length,
    registered: entries.filter((e) => e.registered).length,
    unregistered: entries.filter((e) => !e.registered).length,
    confident_unregistered: entries.filter((e) => e.confident && !e.registered && e.best).length,
  };
}

// ── 렌더 트리 채집 ───────────────────────────────────────────────────────────
function h(type, props, ...children) {
  if (typeof type === "function") return type({ ...(props || {}), children });
  return { type, props: props || {}, children };
}
const Fragment = { __kind: "Fragment" };

/**
 * 자기 style만으로 **화면에서 사라지는가**. 조상 체인은 `walk`가 누적한다.
 *
 * ★★ 2026-08-07 재게이트 R5: 예전 판정은 «개수 + 시작 경로 + Focusable 조상»뿐이었다.
 *    그래서 상주 `Focusable`에 `display:"none"`만 얹으면 **렌더 트리에는 있고 화면에는 없는**
 *    버튼이 되는데, 개수도 맞고 `onClick`도 직접 부르면 잘 돌아 전부 통과했다(Codex가 뚫었다).
 *    → 「존재」의 뜻을 **트리에 있음**에서 **볼 수 있음**으로 옮긴다.
 *
 * ⚠️ 정직한 잔여 표면: 은닉 벡터는 원리적으로 열거가 안 된다 —
 *    화면 밖 좌표(`position:absolute; left:-9999px`), `clip-path`, `transform: scale(0)`,
 *    `z-index`로 덮기, 부모 `overflow:hidden` + 크기 0, CSS 클래스 경유 은닉(우리는 클래스의
 *    실제 규칙을 모른다). 여기서 잡는 것은 **인라인 style 대표 4종 + 표준 속성 2종**
 *    (`hidden`·`aria-hidden`)뿐이다.
 *    → **최종 근거는 실기 캡처다.** 이 프로브는 회귀를 잠글 뿐 "보였다"를 증명하지 못한다.
 */
const ZERO = (v) => v === 0 || v === "0" || v === "0px" || v === "0%" || v === "0em";
function hidesSelf(node) {
  const props = node.props || {};
  // ★★ 2026-08-07 3회차(QA 잔여 표면 이의 수용): 표준 HTML `hidden`은 오프스크린 좌표나
  //    z-index 덮기보다 **JSX에서 실수로 도달할 개연성이 훨씬 높은** 표준 기능이다.
  //    "은닉 벡터는 열거 불가"라는 선언 뒤에 숨기기엔 위험도가 달라 대표 계측에 넣는다.
  //    `hidden={false}`는 숨김이 아니다 — 참일 때만 센다.
  if (props.hidden === true || props.hidden === "" || props.hidden === "hidden") return true;
  if (props["aria-hidden"] === true || props["aria-hidden"] === "true") return true;
  const style = props.style || null;
  if (!style || typeof style !== "object") return false;
  if (String(style.display).toLowerCase() === "none") return true;
  if (String(style.visibility).toLowerCase() === "hidden") return true;
  if (style.opacity !== undefined && Number(style.opacity) === 0) return true;
  if (ZERO(style.width) || ZERO(style.height)) return true;
  if (ZERO(style.maxWidth) || ZERO(style.maxHeight)) return true;
  return false;
}

function walk(node, fn, ctx) {
  const state = ctx || { focusable: false, hidden: false };
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) { node.forEach((k) => walk(k, fn, state)); return; }
  const kind = node.type && node.type.__kind;
  const hidden = state.hidden || hidesSelf(node);
  fn(node, kind, state.focusable, hidden);
  const next = { focusable: state.focusable || kind === "Focusable", hidden };
  [].concat(node.children || []).forEach((k) => walk(k, fn, next));
}

function firstText(node) {
  let found = null;
  walk(node, (n) => {
    if (found !== null) return;
    for (const k of [].concat(n.children || [])) {
      if (typeof k === "string" && k.trim()) { found = k; return; }
    }
  });
  return found;
}

/** **보이는** 텍스트만. 숨겨진 가지의 글자는 사용자에게 없는 것과 같다. */
function allText(tree) {
  const out = [];
  walk(tree, (n, kind, focusable, hidden) => {
    if (hidden) return;
    for (const k of [].concat(n.children || [])) if (typeof k === "string") out.push(k);
  });
  return out;
}

/** **보이는** 버튼만. 숨은 버튼의 `onClick`은 프로브가 부를 수 있어도 사용자는 못 누른다. */
function buttons(tree) {
  const out = [];
  walk(tree, (n, kind, focusable, hidden) => {
    if (kind === "DialogButton" && !hidden) {
      out.push({ label: firstText(n), onClick: n.props.onClick, props: n.props });
    }
  });
  return out;
}

/** 숨겨진 상호작용 요소 — 있으면 그 자체가 사유다(진단용으로 따로 센다). */
function hiddenInteractive(tree) {
  const out = [];
  walk(tree, (n, kind, focusable, hidden) => {
    if (hidden && INTERACTIVE.has(kind)) out.push({ kind, label: firstText(n) });
  });
  return out;
}

function toggles(tree) {
  const out = [];
  walk(tree, (n, kind, focusable, hidden) => { if (kind === "ToggleField" && !hidden) out.push(n.props); });
  return out;
}

/**
 * 렌더 트리에 **입력 요소가 실제로 그려졌는가** (2026-08-07 QA R4).
 *
 * ★ 소스 금지 목록은 *"우리가 떠올린 이름"*만 덮는다. Codex가 `<textarea>`를 넣었을 때 그
 *   목록에 `<textarea`가 없어 통과했다. 이름을 바꿔 우회해도 **화면에 그려지면** 여기서 걸린다.
 *   판정은 태그 이름(소문자 intrinsic 요소)과 편집 가능 속성 둘 다 본다.
 */
const INPUT_TAGS = new Set(["input", "textarea", "select", "option"]);
function inputElements(tree) {
  const out = [];
  // ⚠️ 입력 요소는 **숨겨져 있어도** 센다 — 숨긴 입력창도 포커스가 가면 키보드를 부른다.
  walk(tree, (n) => {
    if (typeof n.type === "string" && INPUT_TAGS.has(n.type.toLowerCase())) out.push(n.type);
    const kind = n.type && n.type.__kind;
    if (typeof kind === "string" && /Text(Field|Input|Area)|SearchField/.test(kind)) out.push(kind);
    for (const key of Object.keys(n.props || {})) {
      if (/^contenteditable$/i.test(key) && n.props[key]) out.push("contentEditable");
    }
  });
  return out;
}

// ★ status_probe.cjs와 **같은 집합**을 쓴다. 새 상호작용 컴포넌트가 생기면 두 곳이 같이 덮는다.
const INTERACTIVE = new Set(["ToggleField", "DialogButton", "ButtonItem"]);
function reachability(tree) {
  const acc = { unreachable: [], seen: 0, hidden: [] };
  walk(tree, (n, kind, inFocusable, hidden) => {
    if (!INTERACTIVE.has(kind)) return;
    // ★ 숨은 요소는 **도달했다고 세지 않는다.** `Focusable` 조상이 있어도 화면에 없으면
    //   D-패드가 갈 곳이 없다 — 「도달 가능」의 뜻이 그것이다(QA R5 재게이트).
    if (hidden) { acc.hidden.push(kind); return; }
    acc.seen += 1;
    if (!inFocusable) acc.unreachable.push(kind);
  });
  return acc;
}

// ── 미니 React (훅이 실제로 돌아야 "눌러 보고 결과를 본다"가 성립한다) ────────
let slots, slotIdx, effectsDone, pendingEffects, dirty;

function makeReact() {
  return {
    useCallback: (fn) => fn,
    // ★ **deps를 실제로 비교한다.** 슬롯당 1회만 돌리면 `[tab]`처럼 deps가 바뀌어 다시 돌아야 하는
    //   effect를 영영 안 돌린다 — 그러면 "탭을 오가면 다시 읽는가"를 잰다고 선언해 놓고
    //   배선을 통째로 우회하는 거짓 검사가 된다(2026-08-07 실기에서 이 버그가 실제로 있었다).
    //   ⚠️ deps를 안 준 effect는 **1회만** 돌린다 — 매 렌더 실행이면 이 렌더 루프가 정착하지 않는다.
    useEffect(fn, deps) {
      const i = slotIdx++;
      const prev = effectsDone.get(i);
      const changed = prev === undefined
        || (deps !== undefined && (prev.length !== deps.length || deps.some((d, k) => d !== prev[k])));
      if (changed) { effectsDone.set(i, deps ? [...deps] : []); pendingEffects.push(fn); }
    },
    useState(initial) {
      const i = slotIdx++;
      if (!(i in slots)) slots[i] = initial;
      return [slots[i], (v) => {
        const next = typeof v === "function" ? v(slots[i]) : v;
        if (next !== slots[i]) dirty = true;
        slots[i] = next;
      }];
    },
  };
}

const flush = () => new Promise((r) => setImmediate(r));

// ── 모듈 로더 ────────────────────────────────────────────────────────────────
function makeLoad(modules) {
  const cache = {};
  function load(rel) {
    if (cache[rel]) return cache[rel];
    const file = path.join(srcDir, rel);
    const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.React, jsxFactory: "h", jsxFragmentFactory: "Fragment", esModuleInterop: true,
      }, fileName: file,
    }).outputText;
    const exports = {};
    cache[rel] = exports;
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
    new Function("exports", "require", "module", "h", "Fragment", compiled)(
      exports, req, { exports }, h, Fragment);
    return exports;
  }
  return load;
}

// ── 한 회차 ──────────────────────────────────────────────────────────────────
/**
 * @param opts.entries      백엔드가 돌려줄 탐지 결과
 * @param opts.addGame      addGame RPC 목의 응답
 * @param opts.pick         pickConfigFile 목의 응답 (null = 취소)
 */
async function run(opts) {
  slots = []; effectsDone = new Map(); dirty = false;
  const calls = { discover: 0, addGame: [], registerConfident: 0, picker: [], modal: 0, modalEls: [] };
  // 렌더된 입력 요소를 회차 전체에 걸쳐 모은다 — 한 화면만 보면 다른 화면의 우회를 놓친다.
  const inputsSeen = [];
  const entries = opts.entries;

  const modules = {
    react: makeReact(),
    "./rpc": {
      discoverGames: () => {
        calls.discover += 1;
        return Promise.resolve({
          ok: true,
          data: { entries, counts: makeCounts(entries), libraries: opts.libraries ?? ["/lib"] },
        });
      },
      addGame: (appid, p, name, token) => {
        calls.addGame.push({ appid, path: p, name, token });
        // ★ 2단계 계약: 토큰을 되돌려 준 재호출은 **성공**해야 한다(백엔드 동작을 그대로 흉내낸다).
        const res = token ? (opts.addGameConfirmed || { ok: true, data: { name: "Confirmed", warnings: [] } })
                          : (opts.addGame || { ok: true, data: { name: "Added", warnings: [] } });
        return Promise.resolve(res);
      },
      registerConfident: () => {
        calls.registerConfident += 1;
        return Promise.resolve({ ok: true, data: { results: [], counts: { added: 0 } } });
      },
    },
    "./i18n": {
      t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
      tCode: (code) => String(code),
      // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 "로직 FAIL"처럼 보인다(인계 문서 5-B).
      setProfileNames: () => {},
      tDefault: (k) => String(k),
      // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 \"로직 FAIL\"처럼 보인다.
      setProfileNames: () => {},
      tDefault: (k) => String(k),
    },
    "./filepicker": {
      pickConfigFile: (start) => {
        calls.picker.push(start);
        return Promise.resolve("pick" in opts ? opts.pick : null);
      },
    },
    "./deckyui": {
      ConfirmModal: { __kind: "ConfirmModal" },
      DialogButton: { __kind: "DialogButton" },
      Focusable: { __kind: "Focusable" },
      ToggleField: { __kind: "ToggleField" },
      // ★ 모달을 **붙잡아 둔다.** 횟수만 세면 "떴다"까지만 알 수 있고, 확인/취소가 실제로
      //   무엇을 하는지(=R1의 핵심)를 못 잰다.
      showModal: (el) => { calls.modal += 1; calls.modalEls.push(el); },
    },
  };
  const { DiscoverTab } = makeLoad(modules)("DiscoverTab.tsx");

  async function render() {
    for (let pass = 0; pass < 25; pass += 1) {
      slotIdx = 0; pendingEffects = []; dirty = false;
      const tree = h(DiscoverTab, null);
      const fx = pendingEffects;
      for (const f of fx) f();
      await flush(); await flush();
      inputsSeen.push(...inputElements(tree));
      if (!dirty) return tree;
    }
    throw new Error("렌더가 정착하지 않았다(무한 갱신)");
  }
  const act = async (fn) => { await fn(); await flush(); await flush(); return render(); };
  return { render, act, calls, modules, inputsSeen };
}

// ── 시나리오 ─────────────────────────────────────────────────────────────────
async function main() {
  const out = {};

  // ① 정상 목록 --------------------------------------------------------------
  {
    const entries = makeEntries(N);
    const s = await run({ entries });
    let tree = await s.render();
    const rowNames = (t) => allText(t).filter((x) => x.startsWith("Game "));

    out.n = N;
    out.discoverCalls = s.calls.discover;
    out.registeredCount = entries.filter((e) => e.registered).length;
    out.rowsDefault = rowNames(tree).length;
    // ② 기본 상태에서 **등록된 게임이 안 보인다**
    out.defaultHidesRegistered = rowNames(tree).every((name) => {
      const e = entries.find((x) => x.name === name);
      return e && !e.registered;
    });
    const tg = toggles(tree);
    out.toggleWired = tg.length === 1 && typeof tg[0].onChange === "function";
    out.toggleCheckedDefault = tg.length === 1 ? tg[0].checked : null;

    const reach = reachability(tree);
    out.unreachable = reach.unreachable;
    out.interactiveSeen = reach.seen;

    // ③ 일괄 등록 버튼
    const bulk = buttons(tree).find((b) => (b.label || "").startsWith("DISCOVER_ADD_CONFIDENT"));
    out.bulkPresent = !!bulk;
    out.bulkLabel = bulk ? bulk.label : null;
    out.bulkExpectedN = makeCounts(entries).confident_unregistered;

    // ④ confident 1탭 등록 — **선택기가 안 뜨고** addGame이 1회, 경로는 best
    const addBtn = buttons(tree).find((b) => b.label === "DISCOVER_ADD");
    out.confidentAddPresent = !!addBtn;
    if (addBtn) tree = await s.act(() => addBtn.onClick());
    out.addGameCalls = s.calls.addGame.length;
    out.addGameUsedBestPath =
      s.calls.addGame.length === 1 &&
      entries.some((e) => e.best && e.best.path === s.calls.addGame[0].path);
    out.filePickerCallsOnConfident = s.calls.picker.length;
    out.modalCallsOnConfident = s.calls.modal;

    // 토글을 **실제로 눌러** 상태가 바뀌는가
    const before = toggles(tree)[0].checked;
    tree = await s.act(() => toggles(tree)[0].onChange(false));
    out.toggleDrivesState = toggles(tree)[0].checked !== before;
    out.rowsAfterToggle = rowNames(tree).length;
    out.toggleRevealsRegistered = rowNames(tree).some((name) => {
      const e = entries.find((x) => x.name === name);
      return e && e.registered;
    });

    // 애매한 게임: 후보 펼침 → 경로가 화면에 나온다
    const showBtn = buttons(tree).find((b) => b.label === "DISCOVER_SHOW_CANDIDATES");
    out.ambiguousHasShowButton = !!showBtn;
    if (showBtn) {
      const t2 = await s.act(() => showBtn.onClick());
      out.candidatePathsShown = allText(t2).filter((x) => x.includes("/cand")).length;
      out.chooseButtons = buttons(t2).filter((b) => b.label === "DISCOVER_CHOOSE").length;
    }
    out.bulkClickCalls = 0;
    if (bulk) {
      await s.act(() => bulk.onClick());
      out.bulkClickCalls = s.calls.registerConfident;
    }
    // ★ 타이핑 0회를 **렌더 결과로** 잰다 (QA R4). 소스 금지 목록을 우회해도 여기서 걸린다.
    out.inputElements = [...new Set(s.inputsSeen)];

    // ★ 수동 등록 진입점이 **목록이 있는 상태에서도** 있는가 (QA R5-b).
    //   실기에서 탐지 10/등록 10이면 화면에 진입점이 하나도 없었다 — 0건 분기 안에만 있었기 때문이다.
    //   ⚠️ 개수만 세면 행 버튼과 구별이 안 된다. **시작 경로로 가른다**:
    //      행 버튼 = `<lib>/steamapps/compatdata/<appid>/pfx` · 상주 버튼 = `<lib>/steamapps/compatdata`
    tree = await s.render();
    const picks = buttons(tree).filter((b) => b.label === "DISCOVER_PICK_FILE");
    out.pickButtonsWithRows = picks.length;
    out.unregisteredRowsShown = rowNames(tree).filter((name) => {
      const e = entries.find((x) => x.name === name);
      return e && !e.registered;
    }).length;
    const pickerBefore = s.calls.picker.length;
    const addBefore = s.calls.addGame.length;
    if (picks.length) await s.act(() => picks[picks.length - 1].onClick());
    out.tailPickStart = s.calls.picker[pickerBefore] ?? null;
    out.tailPickAddDelta = s.calls.addGame.length - addBefore;   // 취소(pick 미지정)라 0이어야 한다
    out.manualPickReachable = reachability(tree).unreachable.length === 0;
    // ★ 숨겨진 상호작용 요소 — 렌더 트리에는 있는데 화면에 없는 것 (QA R5 재게이트)
    out.hiddenInteractive = hiddenInteractive(tree).map((h) => `${h.kind}:${h.label}`);
  }

  // ⑤ 0건 안내 + **안내가 가리키는 조작이 실재하는가** (QA R5) ----------------
  {
    const s = await run({
      entries: [],
      pick: "/lib/steamapps/compatdata/424242/pfx/drive_c/users/steamuser/AppData/Local/G/x.ini",
    });
    let tree = await s.render();
    const texts = allText(tree);
    out.emptyTexts = texts.filter((x) => x.startsWith("DISCOVER_NONE") || x === "NO_GAMES");
    out.emptySaysNotFound = texts.includes("DISCOVER_NONE_FOUND");
    out.emptySaysNoGames = texts.includes("NO_GAMES");
    out.emptyBulkPresent = buttons(tree).some((b) =>
      (b.label || "").startsWith("DISCOVER_ADD_CONFIDENT"));

    // ★ 반려 R5의 핵심: 0건 안내가 「파일 직접 고르기」를 권하는데 그 버튼이 없었다.
    //   존재(present)·도달(Focusable 자손)·호출(눌러서 선택기가 뜨고 등록까지 간다)을 다 잰다.
    const pickBtn = buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE");
    out.emptyPickPresent = !!pickBtn;
    out.emptyPickReachable = reachability(tree).unreachable.length === 0
      && reachability(tree).seen >= 1;
    if (pickBtn) {
      tree = await s.act(() => pickBtn.onClick());
      out.emptyPickOpensPicker = s.calls.picker.length;
      out.emptyPickStart = s.calls.picker[0] || null;
      // appid는 고른 경로에서 읽는다 — 타이핑 없이 등록이 실제로 나가야 한다.
      out.emptyPickRegisters = s.calls.addGame.length;
      out.emptyPickAppid = s.calls.addGame[0] ? s.calls.addGame[0].appid : null;
      out.emptyPickPath = s.calls.addGame[0] ? s.calls.addGame[0].path : null;
    }
    out.emptyInputElements = [...new Set(s.inputsSeen)];
    out.emptyHiddenInteractive = hiddenInteractive(tree).map((h) => `${h.kind}:${h.label}`);
  }

  // ⑤″ compatdata 밖 파일을 고르면 **등록하지 않고 이유를 말한다** (QA R5) -----
  {
    const s = await run({ entries: [], pick: "/home/deck/Documents/random.ini" });
    let tree = await s.render();
    const pickBtn = buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE");
    tree = await s.act(() => pickBtn.onClick());
    out.emptyPickOutsideRegisters = s.calls.addGame.length;
    out.emptyPickOutsideSaysWhy = allText(tree).includes("DISCOVER_MANUAL_NO_APPID");
  }

  // ⑤' 전부 등록된 경우 — 0건이지만 **다른** 안내여야 한다
  {
    const entries = makeEntries(4).map((e) => ({ ...e, registered: true }));
    const s = await run({ entries });
    const tree = await s.render();
    const texts = allText(tree);
    out.allRegisteredSaysDifferent =
      texts.includes("DISCOVER_NONE_UNREGISTERED") && !texts.includes("DISCOVER_NONE_FOUND");
    out.allRegisteredBulkPresent = buttons(tree).some((b) =>
      (b.label || "").startsWith("DISCOVER_ADD_CONFIDENT"));
    // ★ 「전부 등록됨」 상태에도 수동 진입점은 있어야 한다 (QA R5-b — 실기에서 이 상태가 문제였다).
    //   이 상태의 안내 문구는 CTA를 권하지 않는다. 즉 «문구↔버튼» 정합만 보면 결함이 안 보인다.
    out.allRegisteredPickPresent = buttons(tree).some((b) => b.label === "DISCOVER_PICK_FILE");
    out.allRegisteredPickReachable = reachability(tree).unreachable.length === 0;
    out.allRegisteredHiddenInteractive = hiddenInteractive(tree).map((h) => `${h.kind}:${h.label}`);
  }

  // ⑥ .sav 거부 — 선택기로 고른 뒤 백엔드가 거부한다 -------------------------
  {
    const entries = makeEntries(4);
    const s = await run({
      entries,
      pick: "/lib/steamapps/compatdata/100001/pfx/drive_c/users/steamuser/SaveGames/Save01.sav",
      addGame: { ok: false, code: "SAV_REFUSED", params: {} },
    });
    let tree = await s.render();
    const pickBtn = buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE");
    tree = await s.act(() => pickBtn.onClick());
    const texts = allText(tree);
    out.savRefusedShown = texts.includes("SAV_REFUSED");
    out.savAddedText = texts.some((x) => x.startsWith("DISCOVER_ADDED"));
    out.savDiscoverReloads = s.calls.discover;      // 실패했으니 목록을 다시 안 불러야 한다(1회뿐)
    out.savModalCalls = s.calls.modal;
  }

  // ⑦ 선택기 취소가 조용한가 -------------------------------------------------
  {
    const entries = makeEntries(4);
    const s = await run({ entries, pick: null });
    let tree = await s.render();
    const pickBtn = buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE");
    tree = await s.act(() => pickBtn.onClick());
    const texts = allText(tree);
    out.cancelAddGameCalls = s.calls.addGame.length;
    out.cancelNoteTexts = texts.filter((x) => x.startsWith("DISCOVER_") && x !== "DISCOVER_ADD"
      && !x.startsWith("DISCOVER_ADD_CONFIDENT") && x.startsWith("DISCOVER_ADD_FAILED"));
    out.cancelModalCalls = s.calls.modal;
  }

  // ⑧ **등록 전** 재확인 모달 — 백엔드가 CONFIRM_REQUIRED를 낼 때만 (QA R1) -----
  //   ⚠️ 예전 프로브는 `{ok:true, warnings:[…]}`(=이미 저장된 상태)를 흉내 냈다. 그 자체가
  //     반려된 동작이다. 이제 백엔드 계약대로 **저장 없이** CONFIRM_REQUIRED가 오는 것을 흉내낸다.
  const CONFIRM_ENV = {
    ok: false,
    code: "CONFIRM_REQUIRED",
    params: {
      confirm_token: "tok-synthetic",
      warnings: ["WARN_NOT_DISCOVER_CANDIDATE"],
      name: "Game 004",
      config_path: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
    },
  };
  {
    const entries = makeEntries(4);
    const s = await run({
      entries,
      pick: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
      addGame: CONFIRM_ENV,
    });
    let tree = await s.render();
    tree = await s.act(() => buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE").onClick());
    out.manualWarnModalCalls = s.calls.modal;
    out.manualAddCallsBeforeConfirm = s.calls.addGame.length;
    out.manualTokenBeforeConfirm = s.calls.addGame.map((c) => c.token ?? null);
    // CONFIRM_REQUIRED는 **흐름 신호**다 — 오류 문구로 그려지면 안 된다.
    out.manualShowsErrorNote = allText(tree).some((x) => x === "CONFIRM_REQUIRED"
      || x.startsWith("DISCOVER_ADD_FAILED"));
    out.manualWarnShownInModal = (() => {
      const el = s.calls.modalEls[0];
      return !!el && JSON.stringify(el.props.strDescription || "").includes("WARN_NOT_DISCOVER_CANDIDATE");
    })();

    // 취소 = **아무 일도 없다**. onCancel이 아예 없어야 하고, 눌러도 RPC가 안 나간다.
    const el = s.calls.modalEls[0];
    out.confirmModalHasOK = !!(el && typeof el.props.onOK === "function");
    out.confirmModalHasCancelSideEffect = !!(el && typeof el.props.onCancel === "function");
    out.confirmCancelAddCalls = s.calls.addGame.length;   // 취소 후에도 그대로여야 한다

    // 확인 = **받은 토큰을 그대로 되돌려** 재호출한다
    if (el && el.props.onOK) tree = await s.act(() => el.props.onOK());
    out.confirmOkAddCalls = s.calls.addGame.length;
    out.confirmOkSentToken = s.calls.addGame.length > 1
      ? s.calls.addGame[s.calls.addGame.length - 1].token : null;
    out.confirmOkReloads = s.calls.discover;             // 등록됐으니 목록을 다시 읽는다

    // 같은 상황이라도 **자동 후보 1탭 경로**에서는 백엔드가 묻지 않으므로 모달이 없다
    const s2 = await run({ entries, addGame: { ok: true, data: { name: "Game 004", warnings: [] } } });
    let t2 = await s2.render();
    await s2.act(() => buttons(t2).find((b) => b.label === "DISCOVER_ADD").onClick());
    out.inlineWarnModalCalls = s2.calls.modal;
  }

  // ⑧″ 이미 등록된 appid는 백엔드가 거부하고 화면이 사유를 말한다 (QA R2) -------
  {
    const entries = makeEntries(4);
    const s = await run({
      entries,
      pick: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
      addGame: { ok: false, code: "ALREADY_REGISTERED", params: { appid: "100001" } },
    });
    let tree = await s.render();
    tree = await s.act(() => buttons(tree).find((b) => b.label === "DISCOVER_PICK_FILE").onClick());
    out.alreadyRegisteredShown = allText(tree).includes("ALREADY_REGISTERED");
    out.alreadyRegisteredModalCalls = s.calls.modal;
    out.alreadyRegisteredReloads = s.calls.discover;      // 실패했으니 목록을 다시 안 읽는다
  }

  // ⑧' 탭 왕복 — 「게임 추가」에서 등록하고 돌아왔을 때 「현황」이 **다시 읽는가** ------
  //   2026-08-07 실기에서 실제로 낡은 숫자가 떴다(등록 직후에도 "등록 9개").
  {
    slots = []; effectsDone = new Map(); dirty = false;
    let overviewCalls = 0;
    const modules = {
      react: makeReact(),
      "./rpc": {
        getOverview: () => {
          overviewCalls += 1;
          return Promise.resolve({
            ok: true,
            data: { games: [], counts: { total: 0, dock_ready: 0, internal_ready: 0, running: 0, incomplete: 0 } },
          });
        },
        applyProfile: () => new Promise(() => {}),
        saveProfile: () => new Promise(() => {}),
      },
      "./i18n": {
        t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
        tCode: (code) => String(code),
        // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 "로직 FAIL"처럼 보인다(인계 문서 5-B).
        setProfileNames: () => {},
        tDefault: (k) => String(k),
        isLangResolved: () => true,
        ensureLang: () => Promise.resolve(),
      },
      "./version": { PLUGIN_VERSION: "0.0.0-probe" },
      "./limits": { BACKUP_WARN_APPLIES: 6 },
      "./DiscoverTab": { DiscoverTab: () => ({ type: "div", props: {}, children: ["__DISCOVER__"] }) },
      // ★ P8: 「관리」 탭 — 이 절이 재는 것은 탭 왕복과 재조회다. 실물을 끌어오면
      //   낡은 목에 걸려 렌더가 죽고 "탭 로직 FAIL"처럼 보인다(같은 함정).
      "./ManageTab": { ManageTab: () => ({ type: "div", props: {}, children: ["__MANAGE__"] }) },
      "./deckyui": {
        ConfirmModal: { __kind: "ConfirmModal" },
        DialogButton: { __kind: "DialogButton" },
        Focusable: { __kind: "Focusable" },
        ToggleField: { __kind: "ToggleField" },
        showModal: () => {},
      },
    };
    const { StatusPage } = makeLoad(modules)("StatusPage.tsx");
    async function render() {
      for (let pass = 0; pass < 25; pass += 1) {
        slotIdx = 0; pendingEffects = []; dirty = false;
        const tree = h(StatusPage, null);
        for (const f of pendingEffects) f();
        await flush(); await flush();
        if (!dirty) return tree;
      }
      throw new Error("StatusPage 렌더가 정착하지 않았다");
    }
    const act = async (fn) => { await fn(); await flush(); await flush(); return render(); };

    let tree = await render();
    const labels = buttons(tree).map((b) => b.label);
    out.tabButtons = labels.filter((l) => l === "TAB_STATUS" || l === "TAB_DISCOVER");
    out.overviewCallsOnMount = overviewCalls;

    const toDiscover = buttons(tree).find((b) => b.label === "TAB_DISCOVER");
    tree = await act(() => toDiscover.onClick());
    out.discoverTabRendered = allText(tree).includes("__DISCOVER__");
    out.overviewCallsOnDiscover = overviewCalls;

    const toStatus = buttons(tree).find((b) => b.label === "TAB_STATUS");
    tree = await act(() => toStatus.onClick());
    out.overviewCallsAfterReturn = overviewCalls;
    out.statusTabReloads = overviewCalls > out.overviewCallsOnDiscover;
    out.tabReachability = reachability(tree).unreachable;
  }

  // ⑨ filepicker.ts **실물** — 취소를 삼키고 path를 넘기는가 -----------------
  {
    const rejecting = makeLoad({ "@decky/api": { openFilePicker: () => Promise.reject("User canceled") } });
    out.pickerCancelResolvesNull = (await rejecting("filepicker.ts").pickConfigFile("/x")) === null;
    const resolving = makeLoad({
      "@decky/api": { openFilePicker: () => Promise.resolve({ path: "/p/link.ini", realpath: "/p/real.ini" }) },
    });
    // ★ realpath를 넘기면 G11의 심볼릭 링크 거부가 조용히 무력화된다 — path여야 한다.
    out.pickerReturnsPathNotRealpath = (await resolving("filepicker.ts").pickConfigFile("/x")) === "/p/link.ini";
  }

  await flush(); await flush();
  out.unhandledRejections = unhandled;
  console.log(JSON.stringify(out));
}

main().catch((err) => { console.error(err); process.exit(1); });
