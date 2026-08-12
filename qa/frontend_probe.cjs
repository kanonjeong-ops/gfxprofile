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

const allButtons = [];
const applyCalls = [];
//: P10 — `applyAll`에 실제로 들어간 인자 전량(프로필 + 토큰). `applyCalls`는 E1이 쓰던
//: "눌렀더니 호출은 나갔는가"의 지표라 **모양을 바꾸지 않는다**(바꾸면 그 판정이 조용히 깨진다).
const rpcCalls = [];
const modals = [];
let modalThrows = false;      // 확인창을 못 띄우는 상황(진단 가능성 요건)
const TOKEN_FOR = (profile) => `TOKEN-${profile}`;
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
  if (type && type.__kind === "ButtonItem") allButtons.push(node);
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
    // ★ P15-E: QAM이 공용 문(`useDataDoor`)을 쓰면서 ref를 든다. 이 프로브는 **한 번만
    //   그리므로**(재렌더 없음) 새 상자를 돌려줘도 관측 대상인 E1 판정에는 영향이 없다 —
    //   ref의 지속성 자체는 `popup_shell_probe`의 진짜 훅 런타임이 잰다.
    useRef: (initial) => ({ current: initial }),
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
    toaster: { toast: () => {} },
    useQuickAccessVisible: () => true,
  },
  "./rpc": {
    // ★ P10(F8): **2단계 계약**이다 — 토큰 없는 1차 호출은 아무것도 쓰지 않고
    //   `CONFIRM_REQUIRED` + 5버킷 미리보기를 돌려준다. 백엔드와 같은 모양이어야
    //   프론트가 실제로 무엇을 하는지 잴 수 있다(목이 낡으면 "실행됐다"를 오판한다).
    //   ⚠️ 미리보기에 `running_refused: 1`을 넣는다 — E1의 위험이 모달 층으로 옮겨갈 수
    //     있는 자리(그 숫자를 이유로 OK를 죽이는 우회)를 재기 위한 조건이다.
    applyAll: (profile, token) => {
      applyCalls.push(profile);
      rpcCalls.push({ profile, token: token === undefined ? null : token });
      if (!token) {
        return Promise.resolve({
          ok: false,
          code: "CONFIRM_REQUIRED",
          params: {
            // ★ P15-C: 확인창 본문이 쓰는 `total`은 **미리보기 봉투가 준 값**이다(§3-E).
            //   버킷 5개의 합과 같아야 한다는 계약도 여기서 지킨다(8+0+1+1+0 = 10).
            confirm_token: TOKEN_FOR(profile),
            profile,
            total: 10,
            would_apply: 8, already: 0, no_profile: 1, running_refused: 1, cannot_apply: 0,
          },
        });
      }
      // `checkin`은 P11에서 봉투에 추가됐다(§5-E) — 목이 낡으면 화면이 TypeError로 죽는다.
      return Promise.resolve({ ok: true, data: { results: [], counts: {}, checkin: [] } });
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
    // P9/F11: i18n 목이 낡으면 렌더가 통째로 죽고 \"로직 FAIL\"처럼 보인다.
    setProfileNames: () => {},
    tDefault: (k) => String(k),
    setLang: () => {},
  },
  // ★ P15-E: QAM이 조회·변이를 `popup.tsx`의 공용 문으로 지나면서 그 모듈까지 끌어온다 —
  //   골격 컴포넌트가 목에 없으면 로더가 죽고, 그 죽음이 "E1 FAIL"로 오독된다.
  "./deckyui": {
    ButtonItem: { __kind: "ButtonItem" },
    ConfirmModal: { __kind: "ConfirmModal" },
    DialogBody: { __kind: "DialogBody" },
    DialogHeader: { __kind: "DialogHeader" },
    Focusable: { __kind: "Focusable" },
    NavEntryPositionPreferences: { MAINTAIN_X: 2 },
    TextField: { __kind: "TextField" },
    ToggleField: { __kind: "ToggleField" },
    DialogButton: { __kind: "DialogButton" },
    ModalRoot: { __kind: "ModalRoot" },
    PanelSection: { __kind: "PanelSection" },
    PanelSectionRow: { __kind: "PanelSectionRow" },
    showModal: (node) => {
      // `showModal`은 런타임에 얻어지는 값이라 **undefined일 수 있다** — 그 상황을 만들어
      // "안전하지만 아무 흔적도 없이 죽는" 경로가 남아 있지 않은지 본다(QA 반려 ②).
      if (modalThrows) throw new TypeError("showModal is not a function");
      modals.push(node);
    },
    titleClass: () => undefined,
    uicheckMissing: () => missing,
  },
  // ★ P15-C 배선: QAM이 팝업 3종을 **엘리먼트로** 연다. 이 프로브의 소관은 E1(일괄 적용)
  //   하나이므로 팝업 본체는 목으로 세운다 — 실물을 끌어오면 이 프로브가 팝업 내부 변화에
  //   따라 깨지고, 그때 "E1이 깨졌다"로 오독된다. 팝업 배선의 판정은 `qam_probe.cjs`다.
  "./GamesPopup": { GamesPopup: { __kind: "GamesPopup" } },
  "./DiscoverPopup": { DiscoverPopup: { __kind: "DiscoverPopup" } },
  "./SettingsPopup": { SettingsPopup: { __kind: "SettingsPopup" } },
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

// ★ P15-C: QAM에는 이제 `ButtonItem`이 5개다(일괄 2 + 팝업 진입 3). **E1의 대상은 일괄 2개**이고,
//   진입 버튼은 `qam_probe.cjs`가 잰다. 라벨로 가른다 — i18n 목이 키를 그대로 돌려주므로
//   일괄 버튼의 라벨은 `BULK_APPLY …`로 시작한다.
//   ⚠️ 골라내기가 실패하면(라벨 키가 바뀌면) 아래 `buttons`가 0개가 되고 호출부가 FAIL한다 —
//     조용히 다른 것을 재지 않는다.
const buttons = allButtons.filter((b) => textOf(b.children).trim().startsWith("BULK_APPLY"));
const labels = buttons.map((b) => textOf(b.children).trim());
// hint(§3-A ⓑ)는 `description` 슬롯으로 온다 — **`running`이 새어 들었는지**를 여기서 관측한다.
const hints = buttons.map((b) => {
  const d = b.props.description;
  return d === undefined || d === null ? "" : String(d);
});
// ★ 눌러 본다. `disabled=false`인데 아무 일도 안 하는 버튼은 **눌리지 않는 것과 같다.**
buttons.forEach((b) => {
  try {
    if (typeof b.props.onClick === "function") b.props.onClick();
  } catch (e) {
    /* 클릭 자체가 던지면 그것도 동작하지 않는 것이다 — applyCalls로 판정된다 */
  }
});

// ★ P10: 확인창은 **`.then` 콜백**에서 뜨므로 마이크로태스크를 한 번 흘려야 관측된다.
//   여기서 기다리지 않으면 "모달 0개"를 보고 **아무것도 못 잰 채** 판정하게 된다.
const settle = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  await settle();
  const okDisabled = modals.some((m) => m && m.props && m.props.bOKDisabled);
  const modalKinds = modals.map((m) => (m && m.type && m.type.__kind) || String(m));
  // 확인창의 OK를 누른다 — **받은 토큰을 그대로** 되돌려 2차 호출이 나가야 실행이다.
  for (const m of modals) {
    const onOK = m && m.props && m.props.onOK;
    if (typeof onOK === "function") onOK();
  }
  await settle();
  const executed = rpcCalls.filter((c) => c.token).map((c) => c.profile);
  const replayedForeignToken = rpcCalls.some((c) => c.token && c.token !== TOKEN_FOR(c.profile));

  // ④ 확인창을 **못 띄우는** 상황: 그래도 실행되면 안 되고(fail-closed), 흔적은 남아야 한다.
  modalThrows = true;
  const beforeFail = rpcCalls.length;
  buttons.forEach((b) => {
    try {
      if (typeof b.props.onClick === "function") b.props.onClick();
    } catch (e) { /* 위와 같다 */ }
  });
  await settle();
  const executedAfterModalFailure = rpcCalls.slice(beforeFail).some((c) => c.token);
  modalThrows = false;

  console.log(
    JSON.stringify({
      buttons: buttons.map((b, i) => ({ label: labels[i], disabled: !!b.props.disabled })),
      // 화면에 있는 ButtonItem 전량(일괄 2 + 진입 3). 골라내기가 헛돌면 여기서 드러난다.
      allButtonLabels: allButtons.map((b) => textOf(b.children).trim()),
      // ★ §15-A: hint가 `running`을 만지지 않는가 — 주입 현황은 running=1·ready>0이므로
      //   두 hint는 **비어 있어야** 한다(사유가 없다). 채워지면 running이 새어 든 것이다.
      hints,
      langReady: true,
      missing,
      // ★ 측정 경로에 닿았는지 — 주입한 dock_ready(9)가 라벨에 보이는가.
      sawCounts: labels.some((l) => l.includes("9")),
      // 각 버튼을 눌렀을 때 실제로 일괄 적용이 호출됐는가(대리 지표가 아니라 의미).
      applyCalls,
      // 조상 스타일로 클릭이 막혀 있는가.
      styleBlocked: findBlocked(content, false),
      // ── P10(F8) 2단계 계약 ──────────────────────────────────────────────
      // 1차 호출에 토큰이 실려 있으면 프론트가 토큰을 지어낸 것이다(계약 붕괴).
      firstCallsHadToken: rpcCalls.slice(0, 2).some((c) => !!c.token),
      confirmModals: modalKinds,
      // ★ E1이 모달 층으로 옮겨간 형태 — 실행 중 수를 이유로 OK를 죽이면 같은 위반이다.
      modalOkDisabled: okDisabled,
      // OK를 눌렀을 때 **받은 토큰 그대로** 2차 호출이 나갔는가.
      executed,
      replayedForeignToken,
      // 확인창이 안 떠도 실행되면 fail-closed가 깨진 것이다.
      executedAfterModalFailure,
    }),
  );
})();
