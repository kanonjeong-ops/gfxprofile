"use strict";
/**
 * 팝업 D — 게임 감지(설계 §6)를 **렌더+클릭으로** 잰다 — `qa/test_discover_ui.py`가 판정한다.
 *
 * ★ P14 재작성: 대상이 전체화면 「게임 추가」 탭에서 **팝업 D**로 옮겨졌고(§15-A 이식표),
 *   하네스도 자체 미니 React에서 **공용 `qa/probe_kit.cjs`**로 옮겼다. 재는 것은 그대로다 —
 *   기존 판정(타이핑 0회·0건 안내·필터+일괄·확신 1탭·2단계 토큰·취소 조용·거부 표시·재조회)은
 *   전량 살아 있고, 설계가 새로 요구한 것(GP#7 액션 줄 순서 · GP#8 제외 진입 · GP#10 선택 즉시
 *   등록 전환 · §9-③ 등록 note 분기 · §6-B 제외 뷰)이 더해졌다.
 *
 * ★★ 「존재」의 뜻은 **화면에서 볼 수 있음**이다(2026-08-07 재게이트 R5): 상주 버튼에
 *   `display:none`만 얹으면 개수·시작 경로·Focusable 조상이 전부 성립하는데 사용자는 아무것도
 *   못 본다(Codex가 그렇게 뚫었다). 그래서 이 프로브는 **조상 체인까지 누적해** 숨은 것을
 *   목록·도달성·글자 집계에서 뺀다.
 *   ⚠️ 은닉 벡터는 원리적으로 열거가 안 된다(오프스크린·clip-path·CSS 클래스…) —
 *     **최종 근거는 실기 캡처다.** 이 프로브는 회귀를 잠글 뿐 "보였다"를 증명하지 않는다.
 *
 * ★ 실행: node qa/discover_probe.cjs [게임수] [소스디렉터리]
 *   소스디렉터리 인자는 **음성 대조군용**이다 — 사본에 위반을 주입해 같은 프로브를 돌린다.
 */
const path = require("path");
const { makeHost, h, find, findAll, walk, makeLoader, react, settle } =
  require(path.join(__dirname, "probe_kit.cjs"));

const N = Number(process.argv[2] || 12);
const srcDir = process.argv[3] ? path.resolve(process.argv[3]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ★ 취소가 조용한지는 **이것으로만** 잴 수 있다. `.then`만 붙인 코드는 여기 카운터가 올라간다.
let unhandled = 0;
process.on("unhandledRejection", () => { unhandled += 1; });

// ── 합성 데이터 ──────────────────────────────────────────────────────────────
//
// 한 갈래만 있으면 검사가 그 갈래만 보고 통과한다 — 등록됨·확신·애매가 섞여 있어야 한다.
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

const excludedRow = (appid, name, label) => ({ appid, name, excluded_at_label: label });

// ── 가시성 (조상 체인 누적) ──────────────────────────────────────────────────
const ZERO = (v) => v === 0 || v === "0" || v === "0px" || v === "0%" || v === "0em";

/** 자기 style·속성만으로 **화면에서 사라지는가**. 조상 누적은 `chain`이 한다. */
function hidesSelf(node) {
  const props = node.props || {};
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

const isHidden = (node, ancestors) => hidesSelf(node) || ancestors.some(hidesSelf);
const inFocusable = (ancestors) => ancestors.some((a) => a.name === "Focusable");

/** 화면에 **보이는** 글자만. 숨겨진 가지의 글자는 사용자에게 없는 것과 같다. */
const VISIBLE_PROPS = ["strTitle", "strOKButtonText", "strCancelButtonText", "label", "title"];
function visibleTexts(root) {
  const out = [];
  walk(root, (node, ancestors) => {
    if (isHidden(node, ancestors)) return;
    node.children.forEach((c) => { if (typeof c === "string") out.push(c); });
    VISIBLE_PROPS.forEach((key) => {
      if (typeof node.props[key] === "string") out.push(node.props[key]);
    });
  });
  return out;
}

/** 노드 안의 첫 문자열 — 버튼 라벨을 아이콘 span 너머에서도 집는다. */
function firstText(node) {
  let found = null;
  walk(node, (n) => {
    if (found !== null) return;
    n.children.forEach((c) => { if (found === null && typeof c === "string" && c.trim()) found = c; });
  });
  return found;
}

/** **보이는** 버튼만. 숨은 버튼의 `onClick`은 프로브가 부를 수 있어도 사용자는 못 누른다. */
function buttons(root) {
  const out = [];
  walk(root, (node, ancestors) => {
    if (node.name !== "DialogButton") return;
    if (isHidden(node, ancestors)) return;
    out.push({
      label: firstText(node) || "",
      onClick: node.props.onClick,
      disabled: !!node.props.disabled,
      style: node.props.style || {},
      node,
    });
  });
  return out;
}

/** 숨겨진 상호작용 요소 — 있으면 그 자체가 사유다(진단용으로 따로 센다). */
const INTERACTIVE = new Set(["ToggleField", "DialogButton", "ButtonItem"]);
function hiddenInteractive(root) {
  const out = [];
  walk(root, (node, ancestors) => {
    if (INTERACTIVE.has(node.name) && isHidden(node, ancestors)) {
      out.push(`${node.name}:${firstText(node) || ""}`);
    }
  });
  return out;
}

function reachability(root) {
  const acc = { unreachable: [], seen: 0 };
  walk(root, (node, ancestors) => {
    if (!INTERACTIVE.has(node.name)) return;
    // ★ 숨은 요소는 **도달했다고 세지 않는다** — Focusable 조상이 있어도 화면에 없으면
    //   D-패드가 갈 곳이 없다(「도달 가능」의 뜻이 그것이다).
    if (isHidden(node, ancestors)) return;
    acc.seen += 1;
    if (!inFocusable(ancestors)) acc.unreachable.push(node.name);
  });
  return acc;
}

/**
 * 렌더 트리에 **입력 요소가 실제로 그려졌는가**(2026-08-07 QA R4).
 *
 * ★ 소스 금지 목록은 *"우리가 떠올린 이름"*만 덮는다. 이름을 바꿔 우회해도 **그리면** 걸린다.
 * ⚠️ 숨겨져 있어도 센다 — 숨긴 입력창도 포커스가 가면 키보드를 부른다.
 */
const INPUT_TAGS = new Set(["input", "textarea", "select", "option"]);
function inputElements(root) {
  const out = [];
  walk(root, (node) => {
    const name = node.name;
    if (typeof name === "string" && INPUT_TAGS.has(name.toLowerCase())) out.push(name);
    if (typeof name === "string" && /Text(Field|Input|Area)|SearchField/.test(name)) out.push(name);
    Object.keys(node.props).forEach((key) => {
      if (/^contenteditable$/i.test(key) && node.props[key]) out.push("contentEditable");
    });
  });
  return [...new Set(out)];
}

/** 카드의 게임명 순서 — 이름 노드는 `NAME_STYLE`의 ellipsis로 식별한다. */
function cardNames(root) {
  const out = [];
  walk(root, (node, ancestors) => {
    if (node.name !== "div" || isHidden(node, ancestors)) return;
    const style = node.props.style || {};
    if (style.textOverflow === "ellipsis" && style.fontSize === "15px"
        && typeof node.children[0] === "string") {
      out.push(node.children[0]);
    }
  });
  return out;
}

// ── 한 회차 ──────────────────────────────────────────────────────────────────
/**
 * @param scene.entries    discover 봉투의 entries
 * @param scene.excluded   discover 봉투의 excluded (「제외한 게임」 뷰의 재료)
 * @param scene.addGame    addGame 목의 1차 응답
 * @param scene.addGameConfirmed 토큰을 되돌린 재호출의 응답
 * @param scene.pick       pickConfigFile 목의 응답 (null = 취소)
 */
function scene(opts) {
  const state = {
    entries: opts.entries || [],
    excluded: opts.excluded ? opts.excluded.slice() : [],
    libraries: opts.libraries || ["/lib"],
  };
  const calls = { discover: 0, add: [], bulk: 0, include: [], picker: [] };
  const shownModals = [];
  const mutations = [];

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
      showModal: (node) => { shownModals.push(node); },
    },
    "./i18n": {
      // 키를 그대로 돌려준다 — 렌더 대조가 언어에 묶이지 않게. (값의 규율은 `test_wording_10a`.)
      t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
      tCode: (code, fallback) => `${code}/${fallback}`,
      tDefault: (k) => String(k),
      setProfileNames: () => {},
    },
    "./filepicker": {
      pickConfigFile: (start) => {
        calls.picker.push(start);
        return Promise.resolve("pick" in opts ? opts.pick : null);
      },
    },
    "./rpc": {
      discoverGames: () => {
        calls.discover += 1;
        return Promise.resolve({
          ok: true,
          data: {
            entries: state.entries,
            counts: makeCounts(state.entries),
            excluded: state.excluded,
            libraries: state.libraries,
          },
        });
      },
      addGame: (appid, p, name, token) => {
        calls.add.push({ appid, path: p, name, token: token ?? null });
        // ★ 2단계 계약: 토큰을 되돌린 재호출은 **성공**한다(백엔드 동작을 그대로 흉내낸다).
        const res = token
          ? (opts.addGameConfirmed || { ok: true, data: { name: "Confirmed", backups: 0 } })
          : (opts.addGame || { ok: true, data: { name: "Added", backups: 0 } });
        return Promise.resolve(res);
      },
      registerConfident: () => {
        calls.bulk += 1;
        return Promise.resolve({ ok: true, data: { results: [], counts: { added: 0 } } });
      },
      includeGame: (appid) => {
        calls.include.push(appid);
        // 백엔드처럼 **실제로 목록에서 빠진다** — 그래야 "재포함 뒤 재조회"가 화면에서 보인다.
        state.excluded = state.excluded.filter((row) => row.appid !== appid);
        return Promise.resolve({ ok: true, data: { excluded: state.excluded } });
      },
    },
  };

  const { DiscoverPopup } = makeLoader(srcDir, modules)("DiscoverPopup.tsx");
  const host = makeHost(() => h(DiscoverPopup, { onMutate: () => mutations.push(1) }));
  host.render();
  return { host, ui: () => host.output, calls, shownModals, mutations, state };
}

const byLabel = (root, re) => buttons(root).filter((b) => re.test(b.label));

/**
 * 라벨로 찾아 **있으면** 누른다.
 *
 * ★★ 왜 없으면 조용히 지나가는가: 음성 대조군은 화면을 일부러 망가뜨린다("버튼을 지움"·
 *   "전환이 안 일어남"). 그때 프로브가 **죽으면** 판정부는 "검출 실패"가 아니라 "실행 실패"를
 *   보게 되고, 그 둘은 다르다 — 위반을 심었는데 검사가 죽는 것은 **검출이 아니다.**
 *   눌리지 않았다는 사실은 뒤따르는 관측값(호출 수·라벨)이 대신 말한다.
 */
function press(root, re, index) {
  const b = byLabel(root, re)[index || 0];
  if (!b) return false;
  b.onClick();
  return true;
}
const hasText = (root, key) => visibleTexts(root).some((x) => x === key || x.startsWith(key + " "));
const textsFor = (root, key) => visibleTexts(root).filter((x) => x === key || x.startsWith(key + " "));

/** 액션 줄 버튼의 **문서 순서** — GP#7은 순서 자체가 요구다. */
function buttonOrder(root) {
  return buttons(root).map((b) => b.label);
}

(async () => {
  const out = { n: N };

  // ═══ ① 목록: 필터·L3·액션 줄 순서·제외 진입·1탭 등록 ══════════════════════
  {
    const entries = makeEntries(N);
    const s = scene({
      entries,
      excluded: [excludedRow("900001", "Excluded One", "2026-08-11 09:00"),
                 excludedRow("900002", "Excluded Two", "")],
    });
    await settle();
    let ui = s.ui();

    out.discoverCalls = s.calls.discover;
    out.registeredCount = entries.filter((e) => e.registered).length;
    out.rowsDefault = cardNames(ui).length;
    out.defaultHidesRegistered = cardNames(ui).every((name) => {
      const e = entries.find((x) => x.name === name);
      return e && !e.registered;
    });
    // 제외분은 후보 목록에 **없다**(백엔드가 거르고, 화면도 섞지 않는다).
    out.mainShowsExcludedName = cardNames(ui).some((x) => x.startsWith("Excluded"));

    // ── L3: 숨긴 것이 있으면 숨겼다고 말한다 ────────────────────────────────
    out.hiddenNoteDefault = textsFor(ui, "DISCOVER_HIDDEN_NOTE");
    out.summaryShown = textsFor(ui, "DISCOVER_SUMMARY");

    // ── GP#7: [다시 검색]이 [모두 추가]보다 **먼저** ────────────────────────
    const order = buttonOrder(ui);
    out.rescanIndex = order.findIndex((x) => x.startsWith("DISCOVER_RESCAN"));
    out.bulkIndex = order.findIndex((x) => x.startsWith("DISCOVER_ADD_CONFIDENT"));
    out.excludedIndex = order.findIndex((x) => x.startsWith("DISCOVER_EXCLUDED_OPEN"));
    out.firstCardIndex = order.findIndex((x) => x === "DISCOVER_ADD"
      || x.startsWith("DISCOVER_SHOW_CANDIDATES") || x.startsWith("DISCOVER_HIDE_CANDIDATES"));

    // ── GP#8: 제외 진입 행 ──────────────────────────────────────────────────
    const excludedBtn = byLabel(ui, /^DISCOVER_EXCLUDED_OPEN/)[0];
    out.excludedButtonLabel = excludedBtn ? excludedBtn.label : null;
    out.excludedButtonDisabled = excludedBtn ? excludedBtn.disabled : null;

    // ── 일괄 등록 ───────────────────────────────────────────────────────────
    const bulk = byLabel(ui, /^DISCOVER_ADD_CONFIDENT/)[0];
    out.bulkPresent = !!bulk;
    out.bulkLabel = bulk ? bulk.label : null;
    out.bulkExpectedN = makeCounts(entries).confident_unregistered;

    // ── 도달성·가시성·타이핑 ────────────────────────────────────────────────
    const reach = reachability(ui);
    out.unreachable = reach.unreachable;
    out.interactiveSeen = reach.seen;
    out.hiddenInteractive = hiddenInteractive(ui);
    out.inputElements = inputElements(ui);

    // ── 확신 1탭 등록: 선택기 0 · 모달 0 · best 경로 ────────────────────────
    const addBtn = byLabel(ui, /^DISCOVER_ADD$/)[0];
    out.confidentAddPresent = !!addBtn;
    if (addBtn) addBtn.onClick();
    await settle();
    ui = s.ui();
    out.addGameCalls = s.calls.add.length;
    out.addGameUsedBestPath = s.calls.add.length === 1
      && entries.some((e) => e.best && e.best.path === s.calls.add[0].path);
    out.addGameToken = s.calls.add.length ? s.calls.add[0].token : null;
    out.filePickerCallsOnConfident = s.calls.picker.length;
    out.modalCallsOnConfident = s.shownModals.length;
    // §9-③: 남은 백업이 0이면 **그 안내를 그리지 않는다**.
    out.addedNote = textsFor(ui, "DISCOVER_ADDED");
    out.addedBackupNote = textsFor(ui, "DISCOVER_ADDED_HAS_BACKUPS");
    out.addReloads = s.calls.discover;                 // 등록됐으니 다시 읽는다(1 → 2)
    out.addMutations = s.mutations.length;

    // ── [다시 검색] ─────────────────────────────────────────────────────────
    const before = s.calls.discover;
    const rescan = byLabel(ui, /^DISCOVER_RESCAN/)[0];
    if (rescan) rescan.onClick();
    await settle();
    ui = s.ui();
    out.rescanCalls = s.calls.discover - before;

    // ── 필터 토글 ───────────────────────────────────────────────────────────
    const toggle = find(ui, "ToggleField");
    out.toggleWired = !!(toggle && typeof toggle.node.props.onChange === "function");
    out.toggleCheckedDefault = toggle ? toggle.node.props.checked : null;
    if (toggle) toggle.node.props.onChange(false);
    ui = s.ui();
    out.toggleDrivesState = find(ui, "ToggleField").node.props.checked === false;
    out.rowsAfterToggle = cardNames(ui).length;
    out.toggleRevealsRegistered = cardNames(ui).some((name) => {
      const e = entries.find((x) => x.name === name);
      return e && e.registered;
    });
    // 숨긴 것이 없으면 "숨겼다"는 말도 사라진다 — 화면이 거짓을 말하지 않는다.
    out.hiddenNoteAfterToggle = textsFor(ui, "DISCOVER_HIDDEN_NOTE");
    find(ui, "ToggleField").node.props.onChange(true);
    ui = s.ui();

    // ── 일괄 등록 클릭 ──────────────────────────────────────────────────────
    const bulkNow = byLabel(ui, /^DISCOVER_ADD_CONFIDENT/)[0];
    if (bulkNow) bulkNow.onClick();
    await settle();
    ui = s.ui();
    out.bulkClickCalls = s.calls.bulk;

    // ── 행별 + 상주 「파일 직접 고르기」(QA R5-b) ───────────────────────────
    //   개수만 세면 행 버튼과 구별이 안 된다 — **시작 경로**로 가른다:
    //   행 버튼 = `<lib>/steamapps/compatdata/<appid>/pfx` · 상주 버튼 = `<lib>/steamapps/compatdata`
    const picks = byLabel(ui, /^DISCOVER_PICK_FILE$/);
    out.pickButtonsWithRows = picks.length;
    out.unregisteredRowsShown = cardNames(ui).filter((name) => {
      const e = entries.find((x) => x.name === name);
      return e && !e.registered;
    }).length;
    const pickerBefore = s.calls.picker.length;
    const addBefore = s.calls.add.length;
    if (picks.length) picks[picks.length - 1].onClick();
    await settle();
    ui = s.ui();
    out.tailPickStart = s.calls.picker[pickerBefore] ?? null;
    out.tailPickAddDelta = s.calls.add.length - addBefore;   // 취소(pick 미지정)라 0이어야 한다
    out.pickFileDescShown = hasText(ui, "DISCOVER_PICK_FILE_DESC");
    out.manualPickReachable = reachability(ui).unreachable.length === 0;

    // 행별 선택기는 **그 게임의 prefix**에서 시작한다.
    const rowPickBefore = s.calls.picker.length;
    press(ui, /^DISCOVER_PICK_FILE$/);
    await settle();
    out.rowPickStart = s.calls.picker[rowPickBefore] ?? null;
  }

  // ═══ §9-③ 등록 note 분기 — 남은 백업이 있으면 복원 경로를 그 자리에서 말한다 ══
  {
    const entries = makeEntries(6);
    const s = scene({ entries, addGame: { ok: true, data: { name: "Zeta", backups: 3 } } });
    await settle();
    press(s.ui(), /^DISCOVER_ADD$/);
    await settle();
    out.backupsNote = textsFor(s.ui(), "DISCOVER_ADDED_HAS_BACKUPS");
    out.backupsPlainNote = textsFor(s.ui(), "DISCOVER_ADDED");
  }

  // ═══ GP#10 애매 후보 — 1압 [선택] · 2압 [이 파일로 추가] ══════════════════
  {
    // 전부 애매하게 만든다 — 확신 행의 [추가]와 섞이면 "목록 끝 [추가] 제거"를 못 잰다.
    const entries = makeEntries(6).map((e) => ({
      ...e,
      registered: false,
      confident: false,
      best: null,
      candidate_count: 3,
      candidates: [0, 1, 2].map((c) => ({
        path: `/lib/steamapps/compatdata/${e.appid}/pfx/drive_c/users/steamuser/AppData/Local/G/cand${c}.ini`,
        tier: 3,
        size: 100 + c,
        mtime_label: "2026-08-01",
      })),
    }));
    // 화면은 이름순으로 그린다 — **첫 카드의 후보**가 아래 클릭 대상이다.
    const firstEntry = [...entries].sort((a, b) => a.name.localeCompare(b.name))[0];
    const s = scene({ entries });
    await settle();
    let ui = s.ui();

    const show = byLabel(ui, /^DISCOVER_SHOW_CANDIDATES/)[0];
    out.ambiguousHasShowButton = !!show;
    out.addButtonsBeforeChoose = byLabel(ui, /^DISCOVER_ADD$/).length;
    if (show) show.onClick();
    ui = s.ui();

    // M4: 파일명(굵게)과 경로(축약)가 **갈라져** 보인다.
    const files = [];
    const paths = [];
    walk(ui, (node, ancestors) => {
      if (node.name !== "div" || isHidden(node, ancestors)) return;
      const style = node.props.style || {};
      if (typeof node.children[0] !== "string") return;
      if (style.fontWeight === "bold" && style.fontSize === "13px") files.push(node.children[0]);
      if (style.fontSize === "11px" && style.textOverflow === "ellipsis") paths.push(node.children[0]);
    });
    out.candidateFiles = files;
    out.candidatePaths = paths;
    out.candidateTierTexts = visibleTexts(ui).filter((x) => x.startsWith("DISCOVER_TIER")).length;

    const candLabels = (root) => buttons(root)
      .map((b) => b.label)
      .filter((x) => x === "DISCOVER_CHOOSE" || x === "DISCOVER_CANDIDATE_ADD");
    out.candLabelsInitial = candLabels(ui);

    // 1압 — 등록 RPC 0회 + 같은 버튼이 [이 파일로 추가]로 전환
    out.firstPressLanded = press(ui, /^DISCOVER_CHOOSE$/);
    await settle();
    ui = s.ui();
    out.addCallsAfterFirstPress = s.calls.add.length;
    out.candLabelsAfterFirst = candLabels(ui);
    out.addButtonsAfterChoose = byLabel(ui, /^DISCOVER_ADD$/).length;

    // 다른 후보를 고르면 전환이 **그 행으로 옮겨가고** 원 행은 [선택]으로 돌아온다
    out.otherPressLanded = press(ui, /^DISCOVER_CHOOSE$/, 1);
    await settle();
    ui = s.ui();
    out.candLabelsAfterOther = candLabels(ui);
    out.addCallsAfterOtherPress = s.calls.add.length;

    // 2압 — 그 자리에서 등록. 경로는 **고른 후보의 것**이어야 한다.
    const chosenIndex = out.candLabelsAfterOther.indexOf("DISCOVER_CANDIDATE_ADD");
    out.secondPressLanded = press(ui, /^DISCOVER_CANDIDATE_ADD$/);
    await settle();
    ui = s.ui();
    out.addCallsAfterSecondPress = s.calls.add.length;
    out.addPathSecondPress = s.calls.add.length ? s.calls.add[s.calls.add.length - 1].path : null;
    out.expectedCandPath = firstEntry.candidates[chosenIndex]
      ? firstEntry.candidates[chosenIndex].path : null;
    out.secondPressToken = s.calls.add.length ? s.calls.add[s.calls.add.length - 1].token : null;
    out.secondPressModals = s.shownModals.length;
  }

  // ═══ §6-B 제외한 게임 뷰 ═════════════════════════════════════════════════
  {
    const entries = makeEntries(6);
    const s = scene({
      entries,
      excluded: [excludedRow("900001", "Excluded One", "2026-08-11 09:00"),
                 excludedRow("900002", "Excluded Two", "")],
    });
    await settle();
    let ui = s.ui();

    press(ui, /^DISCOVER_EXCLUDED_OPEN/);
    ui = s.ui();
    out.excludedViewOpened = hasText(ui, "DISCOVER_EXCLUDED_TITLE");
    out.excludedViewTexts = visibleTexts(ui).filter((x) => x.startsWith("DISCOVER_EXCLUDED")
      || x.startsWith("DISCOVER_INCLUDE") || x === "BACK");
    out.excludedRowNames = visibleTexts(ui).filter((x) => x.startsWith("Excluded"));
    // 날짜가 빈 값이면 그 줄을 그리지 않는다 — 빈 라벨은 화면이 거짓을 말하는 것이다.
    out.excludedRowMeta = textsFor(ui, "DISCOVER_EXCLUDED_ROW");
    out.excludedHasBack = byLabel(ui, /^BACK$/).length;
    // 제외 뷰에서 후보 카드가 보이면 뷰 전환이 아니라 덧그리기다.
    out.excludedViewCards = cardNames(ui).filter((x) => x.startsWith("Game ")).length;

    const include = byLabel(ui, /^DISCOVER_INCLUDE$/)[0];
    out.includeButtons = byLabel(ui, /^DISCOVER_INCLUDE$/).length;
    const discoverBefore = s.calls.discover;
    if (include) include.onClick();
    await settle();
    ui = s.ui();
    out.includeCalls = s.calls.include;
    out.includeAddGameCalls = s.calls.add.length;        // 재포함은 **등록이 아니다**
    out.includedNote = textsFor(ui, "DISCOVER_INCLUDED_NOTE");
    out.includeReloads = s.calls.discover - discoverBefore;
    out.includeMutations = s.mutations.length;
    out.excludedRowsAfterInclude = visibleTexts(ui).filter((x) => x.startsWith("Excluded")).length;

    // 남은 하나까지 포함하면 **빈 목록 문구**가 뜬다(그 자리에 남아 있어도 화면이 참이다).
    const last = byLabel(ui, /^DISCOVER_INCLUDE$/)[0];
    if (last) last.onClick();
    await settle();
    ui = s.ui();
    out.excludedEmptyText = hasText(ui, "DISCOVER_EXCLUDED_EMPTY");

    // [← 뒤로] → 기본 뷰. 그리고 제외 0건이면 진입 버튼은 **비활성으로 남는다**(M6 기각).
    press(ui, /^BACK$/);
    ui = s.ui();
    out.backToMain = cardNames(ui).some((x) => x.startsWith("Game "));
    const zero = byLabel(ui, /^DISCOVER_EXCLUDED_OPEN/)[0];
    out.excludedZeroPresent = !!zero;
    out.excludedZeroLabel = zero ? zero.label : null;
    out.excludedZeroDisabled = zero ? zero.disabled : null;
  }

  // ═══ 0건 안내 + 그 안내가 가리키는 조작이 실재하는가 ══════════════════════
  {
    const s = scene({
      entries: [],
      excluded: [],
      pick: "/lib/steamapps/compatdata/424242/pfx/drive_c/users/steamuser/AppData/Local/G/x.ini",
    });
    await settle();
    let ui = s.ui();
    out.emptySaysNotFound = hasText(ui, "DISCOVER_NONE_FOUND");
    out.emptySaysNoGames = hasText(ui, "NO_GAMES");
    out.emptyBulkPresent = byLabel(ui, /^DISCOVER_ADD_CONFIDENT/).length > 0;
    out.emptyHiddenInteractive = hiddenInteractive(ui);
    out.emptyInputElements = inputElements(ui);

    const pickBtn = byLabel(ui, /^DISCOVER_PICK_FILE$/)[0];
    out.emptyPickPresent = !!pickBtn;
    out.emptyPickReachable = reachability(ui).unreachable.length === 0 && reachability(ui).seen >= 1;
    if (pickBtn) pickBtn.onClick();
    await settle();
    ui = s.ui();
    out.emptyPickOpensPicker = s.calls.picker.length;
    out.emptyPickStart = s.calls.picker[0] || null;
    out.emptyPickRegisters = s.calls.add.length;
    out.emptyPickAppid = s.calls.add[0] ? s.calls.add[0].appid : null;
  }

  // ═══ prefix 밖 파일 — 등록하지 않고 **이유를 말한다** ═════════════════════
  {
    const s = scene({ entries: [], excluded: [], pick: "/home/deck/Documents/random.ini" });
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    await settle();
    out.outsideRegisters = s.calls.add.length;
    out.outsideSaysWhy = hasText(s.ui(), "DISCOVER_MANUAL_NO_APPID");
  }

  // ═══ 전부 등록됨 — 0건과 **다른** 안내 + 진입점 상주 ══════════════════════
  {
    const entries = makeEntries(4).map((e) => ({ ...e, registered: true }));
    const s = scene({ entries, excluded: [] });
    await settle();
    const ui = s.ui();
    out.allRegisteredSaysDifferent = hasText(ui, "DISCOVER_NONE_UNREGISTERED")
      && !hasText(ui, "DISCOVER_NONE_FOUND");
    out.allRegisteredBulkPresent = byLabel(ui, /^DISCOVER_ADD_CONFIDENT/).length > 0;
    out.allRegisteredPickPresent = byLabel(ui, /^DISCOVER_PICK_FILE$/).length > 0;
    out.allRegisteredPickReachable = reachability(ui).unreachable.length === 0;
    out.allRegisteredHiddenInteractive = hiddenInteractive(ui);
  }

  // ═══ `.sav` 거부 — 등록되지 않고 사유가 화면에 뜬다 ═══════════════════════
  {
    const entries = makeEntries(4);
    const s = scene({
      entries,
      excluded: [],
      pick: "/lib/steamapps/compatdata/100001/pfx/drive_c/users/steamuser/SaveGames/Save01.sav",
      addGame: { ok: false, code: "SAV_REFUSED", params: {} },
    });
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    await settle();
    const ui = s.ui();
    out.savRefusedShown = visibleTexts(ui).some((x) => x.startsWith("SAV_REFUSED"));
    out.savAddedText = hasText(ui, "DISCOVER_ADDED");
    out.savDiscoverReloads = s.calls.discover;          // 실패했으니 목록을 다시 안 읽는다(1)
    out.savModals = s.shownModals.length;
    out.savMutations = s.mutations.length;
  }

  // ═══ 선택기 취소가 조용한가 ══════════════════════════════════════════════
  {
    const s = scene({ entries: makeEntries(4), excluded: [], pick: null });
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    await settle();
    out.cancelAddCalls = s.calls.add.length;
    out.cancelModals = s.shownModals.length;
    out.cancelNoteTexts = visibleTexts(s.ui()).filter((x) => x.includes("FAILED") || x.includes("/"));
  }

  // ═══ **등록 전** 재확인 — 2단계 토큰 계약(QA R1) ══════════════════════════
  //
  // ⚠️ 취소와 확인은 **각자 다른 회차**에서 잰다: 확인 게이트는 「단일 종료」 계약(§4-C D-05 ②)
  //   이라 한 창에서 취소가 한 번 발화하면 그 뒤의 확인은 없던 일이 된다(그것이 옳다).
  //   같은 창에 둘 다 눌러 놓고 "확인이 안 먹었다"고 읽으면 그 오독이 곧 거짓 검사가 된다.
  const warnScene = () => scene({
    entries: makeEntries(4),
    excluded: [],
    pick: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
    addGame: {
      ok: false,
      code: "CONFIRM_REQUIRED",
      params: {
        confirm_token: "tok-synthetic",
        warnings: ["WARN_NOT_DISCOVER_CANDIDATE"],
        name: "Game 004",
        config_path: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
      },
    },
    addGameConfirmed: { ok: true, data: { name: "Game 004", backups: 0 } },
  });

  {
    const s = warnScene();
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    // ⚠️ 확인창은 **RPC가 돌아온 뒤**에 뜬다(CONFIRM_REQUIRED는 응답이다) — 여기서 안 기다리면
    //   프로브가 "모달이 없다"고 읽고, 그 오독이 곧 거짓 검사가 된다.
    await settle();
    out.warnModals = s.shownModals.length;
    out.warnAddCallsBefore = s.calls.add.length;
    out.warnTokensBefore = s.calls.add.map((c) => c.token);
    // CONFIRM_REQUIRED는 **흐름 신호**다 — 오류 문구로 그려지면 안 된다.
    out.warnShowsErrorNote = visibleTexts(s.ui()).some((x) => x.startsWith("CONFIRM_REQUIRED"));
    const modalEl = s.shownModals[0] || null;
    const confirm = modalEl ? find(modalEl, "ConfirmModal") : null;
    out.warnModalTexts = modalEl ? visibleTexts(modalEl) : [];
    out.warnCodeInModal = modalEl
      ? visibleTexts(modalEl).some((x) => x.startsWith("WARN_NOT_DISCOVER_CANDIDATE"))
      : false;
    out.warnModalHasOK = !!(confirm && typeof confirm.node.props.onOK === "function");

    // 취소 = **아무 일도 없다**(등록 RPC도, 재조회도, 변경 통지도 늘지 않는다)
    if (confirm) confirm.node.props.onCancel();
    await settle();
    out.warnCancelAddCalls = s.calls.add.length;
    out.warnCancelReloads = s.calls.discover;
    out.warnCancelMutations = s.mutations.length;
  }
  {
    const s = warnScene();
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    await settle();
    // 확인 = **받은 토큰을 그대로 되돌려** 재호출
    const confirm = s.shownModals[0] ? find(s.shownModals[0], "ConfirmModal") : null;
    if (confirm) confirm.node.props.onOK();
    await settle();
    out.warnOkAddCalls = s.calls.add.length;
    out.warnOkToken = s.calls.add.length > 1 ? s.calls.add[s.calls.add.length - 1].token : null;
    out.warnOkReloads = s.calls.discover;                // 등록됐으니 다시 읽는다(2)
    out.warnOkMutations = s.mutations.length;
    out.warnOkNote = textsFor(s.ui(), "DISCOVER_ADDED");
  }

  // ═══ 이미 등록된 appid — 백엔드가 거부하고 화면이 사유를 말한다(QA R2) ════
  {
    const s = scene({
      entries: makeEntries(4),
      excluded: [],
      pick: "/lib/steamapps/compatdata/100001/pfx/whatever.ini",
      addGame: { ok: false, code: "ALREADY_REGISTERED", params: { appid: "100001" } },
    });
    await settle();
    press(s.ui(), /^DISCOVER_PICK_FILE$/);
    await settle();
    out.alreadyShown = visibleTexts(s.ui()).some((x) => x.startsWith("ALREADY_REGISTERED"));
    out.alreadyModals = s.shownModals.length;
    out.alreadyReloads = s.calls.discover;               // 실패했으니 다시 안 읽는다(1)
  }

  // ═══ 조회 실패 — 모르는 것을 **없다고 말하지 않는다** ═════════════════════
  {
    const modules = {
      react,
      "./deckyui": {
        ConfirmModal: { __kind: "ConfirmModal" }, DialogBody: { __kind: "DialogBody" },
        DialogButton: { __kind: "DialogButton" }, DialogHeader: { __kind: "DialogHeader" },
        Focusable: { __kind: "Focusable" }, ModalRoot: { __kind: "ModalRoot" },
        NavEntryPositionPreferences: { MAINTAIN_X: 2 }, TextField: { __kind: "TextField" },
        ToggleField: { __kind: "ToggleField" }, showModal: () => {},
      },
      "./i18n": {
        t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
        tCode: (code, fallback) => `${code}/${fallback}`,
        tDefault: (k) => String(k), setProfileNames: () => {},
      },
      "./filepicker": { pickConfigFile: () => Promise.resolve(null) },
      "./rpc": {
        discoverGames: () => Promise.resolve({ ok: false, code: "REGISTRY_UNREADABLE", params: {} }),
        addGame: () => new Promise(() => {}),
        registerConfident: () => new Promise(() => {}),
        includeGame: () => new Promise(() => {}),
      },
    };
    const { DiscoverPopup } = makeLoader(srcDir, modules)("DiscoverPopup.tsx");
    const host = makeHost(() => h(DiscoverPopup, {}));
    host.render();
    await settle();
    const seen = visibleTexts(host.output);
    // 「훑는 중」이 실패 상태에 남아 있으면 화면이 영영 거짓을 말한다 — 그것까지 채집한다.
    out.failTexts = seen.filter((x) => x.startsWith("REGISTRY_UNREADABLE")
      || x.startsWith("DISCOVER_NONE") || x === "LOADING" || x === "DISCOVER_SCANNING");
  }

  // ═══ `filepicker.ts` **실물** — 취소를 삼키고 path를 넘긴다 ═══════════════
  {
    const rejecting = makeLoader(srcDir, {
      "@decky/api": { openFilePicker: () => Promise.reject("User canceled") },
    });
    out.pickerCancelResolvesNull = (await rejecting("filepicker.ts").pickConfigFile("/x")) === null;
    const resolving = makeLoader(srcDir, {
      "@decky/api": {
        openFilePicker: () => Promise.resolve({ path: "/p/link.ini", realpath: "/p/real.ini" }),
      },
    });
    // ★ realpath를 넘기면 G11의 심볼릭 링크 거부가 조용히 무력화된다 — path여야 한다.
    out.pickerReturnsPathNotRealpath =
      (await resolving("filepicker.ts").pickConfigFile("/x")) === "/p/link.ini";
  }

  await settle();
  out.unhandledRejections = unhandled;
  // 팝업 골격이 실제로 섰는가 — 이게 없으면 위 판정 전부가 공허하다.
  {
    const s = scene({ entries: makeEntries(3), excluded: [] });
    await settle();
    out.hasModalRoot = !!find(s.ui(), "ModalRoot");
    out.headerTitle = (() => {
      const header = find(s.ui(), "DialogHeader");
      return header ? firstText(header.node) : null;
    })();
    out.popupWhere = (() => {
      const boundary = findAll(s.ui(), "ErrorBoundary")[0];
      return boundary ? boundary.node.props.where : null;
    })();
  }

  console.log(JSON.stringify(out));
})().catch((err) => { console.error(err); process.exit(1); });
