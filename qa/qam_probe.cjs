"use strict";
/**
 * **QAM 재편(설계 §3)** 을 렌더+클릭으로 잰다 — `qa/test_qam.py`가 판정한다.
 *
 * 재는 것
 *   ① 상태박스(§3-B): 슬롯 조건 · 두 군 분리 · 시각 표기 · busy 투명도 · 승계(요약·실패) ·
 *      **counts 미도착에 NO_GAMES 미표시**(D01) ·
 *      **12판: ④ 시작 안내 슬롯 폐기** — 달리 말할 것이 없으면 박스가 통째로 미렌더되지만,
 *      **미렌더 조건에 프로필 수는 들어가지 않는다**(`noProfilesRunning` 장면이 그 음성 대조군)
 *   ② 카운트 줄(§3-C)과 일괄 버튼 라벨 괄호·hint(§3-A ⓑ — 12판: 괄호는 0도 숫자로 그린다)
 *   ③ 설명 영역(§3-D 판정표): **어느 상태에서도 0줄 또는 1줄**([없음, 없음, GUIDE, ABOUT])
 *   ④ 팝업 3종 배선(§4-A): 어느 컴포넌트를 여는가 · `onMutate` 전달 · 실패 고지 3종 ·
 *      **onMutate 멱등**(P15-B 인계 ① — 거부에도 발화한다)
 *   ⑤ 일괄 적용 확인창 게이트(§3-E): 무토큰 1차 → 확인창 → 토큰 재호출 ·
 *      본문 `{total}`이 **미리보기 봉투의 값**인가(이월 #5·D-06)
 *
 * ★ 시나리오마다 **모듈을 새로 로드한다**: `lastSummary`·`lastFailure`가 모듈 변수라
 *   (설계 §3-B 수명) 한 프로세스에서 이어 쓰면 앞 시나리오가 뒤를 오염시킨다.
 *   **승계를 재는 자리만** 같은 모듈을 두 번 마운트한다 — 그것이 곧 QAM 재개방이다.
 *
 * ⚠️ E1(일괄 적용이 막히지 않는가)은 여기 소관이 아니다 — `frontend_probe.cjs`가 잰다.
 *
 * 실행: node qa/qam_probe.cjs [소스디렉터리]
 */
const path = require("path");
const { makeHost, h, find, findAll, texts, makeLoader, react, settle } =
  require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ── 장면 ─────────────────────────────────────────────────────────────────────
const counts = (over) => Object.assign(
  { total: 9, dock_ready: 9, internal_ready: 8, running: 0, incomplete: 0, excluded: 0 },
  over || {},
);

const SCENE = {
  /** null = 응답이 영영 안 온다(=로딩 중) */
  overview: { ok: true, counts: counts() },
  hang: false,
  /** applyAll 미리보기 봉투의 total — **overview의 total과 일부러 다르게 둔다**(출처 판별). */
  previewTotal: 42,
  applyResult: null,
  /** 1차·2차 왕복을 붙잡아 둔다(진행 중 화면을 재기 위해) */
  holdApply: false,
  /** 조회 응답을 **손에 쥔다** — 역순 도착(P15-E R2)을 만들려면 순서를 우리가 정해야 한다. */
  holdOverview: false,
  modalThrows: false,
};

const calls = { overview: 0, apply: [], modals: [], toasts: [] };
let releaseApply = null;
/** 붙잡아 둔 조회들의 resolve — 먼저 나간 것이 `[0]`이다. */
const heldOverviews = [];

function resetCalls() {
  calls.overview = 0;
  calls.apply.length = 0;
  calls.modals.length = 0;
  calls.toasts.length = 0;
  heldOverviews.length = 0;
}

/** 조회 봉투 하나 — 붙잡아 둔 응답을 나중에 이 모양으로 놓아 준다. */
const overviewEnvelope = (o) => (o.ok
  ? { ok: true, data: { games: [], counts: o.counts, profile_names: { dock: "", internal: "" } } }
  : { ok: false, code: o.code || "REGISTRY_UNREADABLE", params: {} });

const modules = {
  react,
  "@decky/api": {
    definePlugin: (fn) => fn,
    toaster: { toast: (v) => { calls.toasts.push(v); } },
    useQuickAccessVisible: () => true,
  },
  // ★ P15-E: QAM이 조회·변이를 `popup.tsx`의 공용 문(`useDataDoor`)으로 지나면서 이 화면도
  //   그 모듈을 끌어온다 — 골격 컴포넌트까지 목이 있어야 로더가 산다(팝업 3종은 여기서
  //   목으로 갈아 끼우므로 실제로 그려지지는 않는다).
  "./deckyui": {
    ButtonItem: { __kind: "ButtonItem" },
    ConfirmModal: { __kind: "ConfirmModal" },
    DialogBody: { __kind: "DialogBody" },
    DialogButton: { __kind: "DialogButton" },
    DialogHeader: { __kind: "DialogHeader" },
    Focusable: { __kind: "Focusable" },
    ModalRoot: { __kind: "ModalRoot" },
    NavEntryPositionPreferences: { MAINTAIN_X: 2 },
    TextField: { __kind: "TextField" },
    ToggleField: { __kind: "ToggleField" },
    PanelSection: { __kind: "PanelSection" },
    PanelSectionRow: { __kind: "PanelSectionRow" },
    showModal: (node) => {
      // `showModal`은 런타임에 얻어지는 값이라 **undefined일 수 있다** — 그 상황에서 화면이
      // 어느 화면을 못 띄웠는지 말하는지가 §3-A의 계약이다(F21).
      if (SCENE.modalThrows) throw new TypeError("showModal is not a function");
      calls.modals.push(node);
    },
    titleClass: () => undefined,
    uicheckMissing: () => [],
  },
  "./i18n": {
    // 키를 그대로 돌려준다 — 렌더 대조가 언어에 묶이지 않게(프로젝트 공통 관례).
    t: (k, p) => (p ? `${k} ${Object.values(p).join(" ")}` : String(k)),
    tCode: (code, fallback) => `${code}/${fallback}`,
    tDefault: (k) => String(k),
    setProfileNames: () => {},
    ensureLang: () => Promise.resolve({}),
  },
  "./rpc": {
    getOverview: () => {
      calls.overview += 1;
      if (SCENE.hang) return new Promise(() => {});
      if (SCENE.holdOverview) {
        return new Promise((resolve) => { heldOverviews.push(resolve); });
      }
      return Promise.resolve(overviewEnvelope(SCENE.overview));
    },
    applyAll: (profile, token) => {
      calls.apply.push({ profile, token: token === undefined ? null : token });
      const answer = () => {
        if (!token) {
          return {
            ok: false,
            code: "CONFIRM_REQUIRED",
            params: {
              confirm_token: `TOKEN-${profile}`,
              profile,
              total: SCENE.previewTotal,
              would_apply: 1, already: 0, no_profile: 0, running_refused: 0, cannot_apply: 0,
            },
          };
        }
        return SCENE.applyResult(profile);
      };
      if (!SCENE.holdApply) return Promise.resolve(answer());
      return new Promise((resolve) => { releaseApply = () => resolve(answer()); });
    },
  },
  // 팝업 3종은 **열리는 사실과 받은 prop**만 본다. 내부는 각자의 프로브가 잰다.
  "./GamesPopup": { GamesPopup: { __kind: "GamesPopup" } },
  "./DiscoverPopup": { DiscoverPopup: { __kind: "DiscoverPopup" } },
  "./SettingsPopup": { SettingsPopup: { __kind: "SettingsPopup" } },
};

/** 모듈을 **새로** 읽는다 — 모듈 변수(승계)가 시나리오를 넘어 새지 않게. */
function freshModule() {
  return makeLoader(srcDir, modules)("index.tsx");
}

function mount(mod) {
  const host = makeHost(() => mod.default().content);
  host.render();
  return { host, ui: () => host.output };
}

// ── 관측면 ───────────────────────────────────────────────────────────────────

/**
 * **인라인** 시각 표기(§3-B ③ 실패 줄): 당일은 `· 14:32`, 다른 날은 `· 08-10 14:32`.
 * 문장 **뒤에** 붙는 형태라 끝에 앵커를 건다.
 */
const STAMP = /·\s(\d{2}-\d{2}\s)?\d{2}:\d{2}$/;

/**
 * **머리 행**의 시각(§3-B ⑤ 과거군 카드, 10판): 구분자 `·` 없이 **자기 자리**에 선다.
 * 9판까지는 헤드라인 뒤 인라인이었는데 268px에서 낱자로 감겨 붕괴했다(D4) — 그래서
 * 고정폭 자리로 옮겼고, 판독도 **글자 끝**이 아니라 **그 자리**를 본다.
 */
const HEAD_STAMP = /^(\d{2}-\d{2}\s)?\d{2}:\d{2}$/;

const styleOf = (node) => node.props.style || {};

/** 렌더 조각들을 이어 붙인 글자 — 조각 경계의 공백은 하나로 접는다. */
const flatten = (node) => texts(node).join(" ").replace(/\s+/g, " ").trim();

/**
 * 줄 안에 **시각 전용 자리**(flexShrink:0 span)가 있고 그 글자가 시각인가.
 * ★ 자리를 보는 이유: 텍스트 끝만 보면 헤드라인이 시각보다 뒤에 오는 10판 배치에서
 *   "시각이 없다"고 오판한다 — 배치가 바뀌어도 **계약(시각을 말한다)**은 그대로다.
 */
function headStamped(node) {
  return findAll(node, "span").some(({ node: s }) =>
    styleOf(s).flexShrink === 0 && HEAD_STAMP.test(flatten(s)));
}

/** 결과 헤드라인(§3-B ⑤) — 굵은 전폭 블록. 없으면 null(현재군 줄들에는 없다). */
function headlineOf(node) {
  const hit = findAll(node, "div").find(({ node: d }) => styleOf(d).fontWeight === "bold");
  return hit ? flatten(hit.node) : null;
}

/**
 * 헤드라인이 **머리 행 안**에 있는가 — 있으면 §3-B 10판 폭 규약 위반이다.
 *
 * ★★ 규약은 *"고정폭 요소(아이콘·시각)와 가변 텍스트를 같은 flex 행에 두지 않는다"*이고,
 *   9판이 정확히 그렇게 해서 268px에서 세 항목이 낱자로 감겨 붕괴했다(D4). 헤드라인 **글자**만
 *   보는 검사는 배치가 9판으로 되돌아가도 초록불이다 — 그래서 **어디에 있는지**를 따로 잰다.
 *   머리 행은 `justifyContent:"space-between"`으로 식별한다(그 행의 정의적 속성이다).
 */
function headlineInHeadRow(node) {
  const hit = findAll(node, "div").find(({ node: d }) => styleOf(d).fontWeight === "bold");
  if (!hit) return false;
  return hit.ancestors.some((a) => styleOf(a).justifyContent === "space-between");
}

/** 줄 하나 — 글자·색·아이콘·시각 표기·헤드라인. */
function lineOf(node) {
  const text = flatten(node);
  return {
    key: node.props.key === undefined ? null : String(node.props.key),
    text,
    color: styleOf(node).color || null,
    icons: ["IconCheck", "IconWarn"].filter((name) => !!find(node, name)),
    // 인라인(③ 실패)이든 머리 행(⑤ 결과)이든 **시각을 말했는가**가 판정 항목이다.
    stamped: STAMP.test(text) || headStamped(node),
    // 헤드라인(⑤)은 **자기 자리**에서 읽는다 — flatten은 머리 행의 시각이 앞에 붙어
    // "무슨 결과인가"를 앞머리로 판정할 수 없다. 위치가 아니라 역할로 집는다.
    headline: headlineOf(node),
    // 그 자리가 **머리 행 밖**인지도 함께 잰다(§3-B 폭 규약 — D4 재발 방지).
    headlineInHead: headlineInHeadRow(node),
  };
}

/**
 * 상태박스(§3-B 10판) — 없으면 null. 있으면 **결과 카드 배열**(위=현재군, 아래=과거군).
 *
 * ★★ 10판에서 테두리 박스가 폐기됐다. 예전엔 `border: 1px solid rgba(255,255,255,0.15)`로
 *   박스를 찾았는데, 그 셀렉터를 그대로 두면 카드형 전환 후 **"박스 없음"으로 오판**한다
 *   (검사가 조용히 아무것도 안 재는 상태 — 이 프로젝트가 가장 경계하는 형태다).
 *   이제 카드는 `CARD_STYLE`의 배경으로 식별한다(팝업 목록 카드와 **같은 시각 언어**를 쓰는 것이
 *   10판의 요지이므로, 같은 값으로 찾는 것이 계약과 일치한다).
 * ★ 군 간 간격은 **컨테이너 gap 하나**가 소유한다(카드의 marginTop/marginBottom이 아니다) —
 *   값이 두 곳에 살면 한쪽만 고치는 날 간격이 어긋나므로 문을 하나로 모았다. 그래서 여기서도
 *   간격은 카드가 아니라 컨테이너에서 읽는다.
 */
const CARD_BG = "rgba(255,255,255,0.05)";

function statusBox(root) {
  const cards = findAll(root, "div").filter(({ node }) => styleOf(node).background === CARD_BG);
  if (cards.length === 0) return null;
  // 컨테이너 = 카드의 **직계 부모**. ancestors의 마지막이 그것이다.
  const parents = cards[0].ancestors;
  const container = parents.length > 0 ? parents[parents.length - 1] : null;
  return {
    gap: container && styleOf(container).gap !== undefined ? styleOf(container).gap : null,
    groups: cards.map(({ node: g }) => ({
      opacity: styleOf(g).opacity === undefined ? 1 : styleOf(g).opacity,
      marginBottom: styleOf(g).marginBottom === undefined ? null : styleOf(g).marginBottom,
      // ★★ **카드의 계약 속성**(§3-B 10판). 배경색 하나로만 찾으면 나머지를 다 깨뜨려도
      //   검사가 초록불이다 — 찾는 조건과 **재는 조건**은 다른 일이다(이종 QA 적발).
      //   `border`는 **없어야** 하는 것을 재는 자리다: 9판 테두리 박스 폐기가 D3의 핵심이라
      //   되살아나면 카드형이 아니라 "테두리 친 문단"으로 돌아간다.
      borderRadius: styleOf(g).borderRadius === undefined ? null : styleOf(g).borderRadius,
      padding: styleOf(g).padding === undefined ? null : styleOf(g).padding,
      fontSize: styleOf(g).fontSize === undefined ? null : styleOf(g).fontSize,
      innerGap: styleOf(g).gap === undefined ? null : styleOf(g).gap,
      border: styleOf(g).border === undefined ? null : styleOf(g).border,
      lines: g.children.filter((c) => c && typeof c === "object" && c.props).map(lineOf),
    })),
  };
}

/** 상태박스의 모든 줄을 한 줄로 편 것(슬롯 존재 판정용). */
function boxLines(root) {
  const box = statusBox(root);
  if (!box) return [];
  return box.groups.reduce((acc, g) => acc.concat(g.lines), []);
}

/** 카운트 줄(§3-C) — 조회 전에도 **자리를 지키는** 그 줄. */
function countLine(root) {
  const hit = findAll(root, "div").find(({ node }) => styleOf(node).minHeight === "16px");
  if (!hit) return null;
  return flatten(hit.node);
}

/**
 * 버튼의 아이콘 — **children 선두의 아이콘 슬롯**에서 읽는다(§3-A 10판 정오).
 *
 * ★ 왜 자리를 옮겼는가: `ButtonItem`의 `icon` prop은 버튼 내용이 아니라 **Field의 라벨 슬롯**이라
 *   `layout="below"`+라벨 없음 조합에서 아이콘이 버튼 **위**에 고아로 뜬다(D2 실측). 그래서 실물이
 *   `<span style={ICON_SLOT_STYLE}><Icon/></span>{label}` 관용구로 옮겼고, 판독도 그 자리로 온다.
 *   **판정 항목("아이콘이 실재하는가·어느 아이콘인가")은 그대로다 — 읽는 자리만 바뀌었다.**
 *
 * 슬롯 식별은 `ICON_SLOT_STYLE`의 값(1em 고정 폭 + 오른쪽 여백)으로 한다 — 라벨 **뒤**에 서는
 * 마커 자리(`MARKER_SLOT_STYLE`, marginLeft)와 이 조합으로 갈린다.
 */
function slotIcon(node) {
  const hit = findAll(node, "span").find(({ node: s }) => {
    const st = styleOf(s);
    return st.width === "1em" && st.marginRight === "4px";
  });
  if (!hit) return null;
  const icon = hit.node.children.find((c) => c && typeof c === "object" && c.name);
  return icon ? icon.name : null;
}

/**
 * 라벨 — **children만** 편다.
 *
 * ★★ 왜 `flatten(node)`가 아닌가: `walk`는 **prop으로 넘어간 엘리먼트까지** 화면의 일부로
 *   훑는다(그 자체는 옳다 — 설명 슬롯도 사용자가 읽는다). 그런데 설명이 엘리먼트가 된
 *   2026-08-13 이후에는 그 글자가 **라벨에 붙어** `"OPEN_GAMES OPEN_GAMES_DESC"`가 된다.
 *   라벨과 설명은 다른 슬롯이므로 읽는 자리도 갈라야 한다 — props를 비운 사본을 훑어
 *   children만 본다(판정 항목은 그대로다: 라벨이 무엇인가).
 */
const childText = (node) => flatten({ ...node, props: {} });

/**
 * 설명 슬롯의 **글자**. 문자열이면 그대로, 엘리먼트면 펴서 읽는다.
 *
 * ★ 2026-08-13: 한국어 낱말 보존(`KEEP_ALL_STYLE`)을 걸려면 `description`이 style을 받아야
 *   하는데 그 prop에는 자리가 없어 실물이 `<span>`으로 감싸 넘긴다. `String(엘리먼트)`는
 *   `"[object Object]"`가 되므로 — **글자가 아닌 것을 글자로 재는** 상태가 된다 — 편다.
 *   판정 항목은 그대로다: 그 슬롯에 무슨 말이 서 있는가(없으면 여전히 `null`이다).
 */
function descText(d) {
  if (d === undefined || d === null) return null;
  return typeof d === "object" ? flatten(d) : String(d);
}

function buttonItems(root) {
  return findAll(root, "ButtonItem").map(({ node }) => ({
    label: childText(node),
    description: descText(node.props.description),
    disabled: !!node.props.disabled,
    icon: slotIcon(node),
    onClick: node.props.onClick,
  }));
}

const bulkOf = (root) => buttonItems(root).filter((b) => b.label.indexOf("BULK_APPLY") === 0);
const entriesOf = (root) => buttonItems(root).filter((b) => b.label.indexOf("OPEN_") === 0);

/** 화면 전체의 가시 문자열(설명 영역 등 박스 밖 줄까지). */
const seen = (root) => texts(root);

/** 한 장면을 그려 관측면을 모은다. */
async function snapshot(cfg) {
  Object.assign(SCENE, cfg);
  resetCalls();
  const mod = freshModule();
  const ui = mount(mod);
  await settle();
  await settle();
  return {
    mod,
    ui,
    view: {
      box: statusBox(ui.ui()),
      lines: boxLines(ui.ui()),
      count: countLine(ui.ui()),
      bulk: bulkOf(ui.ui()),
      entries: entriesOf(ui.ui()),
      texts: seen(ui.ui()),
      overviewCalls: calls.overview,
    },
  };
}

const keysOf = (lines) => lines.map((l) => l.key);

/** 일괄 적용을 끝까지 몰아본다 — 확인창 → 토큰 재호출 → 결과 줄. */
async function driveApply(scene, profile) {
  const s = await snapshot(scene);
  const btn = bulkOf(s.ui.ui()).find((b) => b.label.indexOf(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") > 0);
  // ★ 못 눌러도 **모양은 그대로** 돌려준다: JSON은 `undefined`를 실어 나르지 않아, 여기서
  //   필드를 빼면 판정기가 그 키에서 죽는다(P16 E10 — 검출은 됐는데 진단이 스택 트레이스였다).
  //   "측정이 없었다"는 것도 값으로 말해야 판정기가 그렇게 읽는다.
  if (!btn || btn.disabled) {
    return {
      s, blocked: true, firstCall: null, secondCall: null,
      confirmFound: false, confirmTexts: [], afterLines: [], afterBox: null,
    };
  }
  btn.onClick();
  await settle();
  const modal = calls.modals[0] || null;
  const confirm = modal ? find(modal, "ConfirmModal") : null;
  const out = {
    s,
    blocked: false,
    firstCall: calls.apply[0] || null,
    confirmTexts: confirm ? texts(confirm.node) : [],
    confirmFound: !!confirm,
  };
  if (confirm) {
    confirm.node.props.onOK();
    await settle();
  }
  out.secondCall = calls.apply[1] || null;
  out.afterLines = boxLines(s.ui.ui());
  out.afterBox = statusBox(s.ui.ui());
  return out;
}

(async () => {
  const out = {};

  // ═══ ⓪ 로딩 · D01(counts 미도착에 NO_GAMES 미표시) ═══════════════════════
  {
    const s = await snapshot({ hang: true, overview: { ok: true, counts: counts() } });
    out.loading = {
      lines: s.view.lines.map((l) => ({ key: l.key, text: l.text })),
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      labels: s.view.bulk.map((b) => b.label),
      // ★ C-1: counts 미도착에서는 **누를 수 없어야** 한다(모르는 채 활성이 더 나쁜 거짓이다).
      disabled: s.view.bulk.map((b) => b.disabled),
      texts: s.view.texts,
    };
  }

  // ═══ ② 실행 중 고지 · 카운트 · 설명 영역 상시 ═════════════════════════════
  {
    const s = await snapshot({ hang: false, overview: { ok: true, counts: counts({ running: 2 }) } });
    out.normal = {
      lines: s.view.lines.map((l) => ({ key: l.key, text: l.text, color: l.color })),
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      labels: s.view.bulk.map((b) => b.label),
      bulkIcons: s.view.bulk.map((b) => b.icon),
      bulkDisabled: s.view.bulk.map((b) => b.disabled),
      entries: s.view.entries.map((b) => ({ label: b.label, desc: b.description, icon: b.icon })),
      texts: s.view.texts,
    };
  }

  // ═══ ③-D 설명 줄 3갈래(§3-D 판정표) · ④ 폐기 확인 ════════════════════════
  {
    // 등록 있음 · 프로필 0 · **실행 중 0 · 실패 없음 · 직전 결과 없음** —
    // 달리 말할 것이 없으므로 상태박스가 통째로 미렌더되고, 설명 줄은 GUIDE 하나다.
    const s = await snapshot({ overview: { ok: true, counts: counts({ dock_ready: 0, internal_ready: 0 }) } });
    out.noProfiles = {
      keys: keysOf(s.view.lines),
      boxNull: s.view.box === null,
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      labels: s.view.bulk.map((b) => b.label),
      texts: s.view.texts,
    };
  }
  {
    // ★★ N-d **음성 대조군 전용 장면**: 위 장면에 `running:1`만 더한 것이다.
    //   프로필 수는 미렌더 조건이 아니므로 여기서는 상태박스가 `BULK_RUNNING_NOTE` 한 줄로
    //   **선다.** "프로필 0 → 무조건 null"이라는 오독을 잡는 유일한 표본이고, 이 조합은 드문
    //   것이 아니라 §5-B 저장 안내("게임에서 옵션을 맞춘 뒤 종료하고 저장")가 유도하는
    //   흐름 그 자체다 — 사용자가 게임을 켠 채 QAM을 여는 순간이 정확히 이 상태다.
    const s = await snapshot({
      overview: { ok: true, counts: counts({ dock_ready: 0, internal_ready: 0, running: 1 }) },
    });
    out.noProfilesRunning = {
      boxNull: s.view.box === null,
      lines: s.view.lines.map((l) => ({ key: l.key, text: l.text })),
      texts: s.view.texts,
    };
  }
  {
    // 프로필이 **하나** 생긴 순간 설명 줄이 GUIDE에서 ABOUT으로 갈아탄다(같은 식의 참/거짓).
    const s = await snapshot({ overview: { ok: true, counts: counts({ dock_ready: 1, internal_ready: 0 }) } });
    out.oneProfile = {
      keys: keysOf(s.view.lines),
      hints: s.view.bulk.map((b) => b.description),
      labels: s.view.bulk.map((b) => b.label),
      texts: s.view.texts,
    };
  }
  {
    // 등록 0 — 카운트 자리가 NO_GAMES를 맡고(갈 곳 안내 전담), 설명 줄은 **아예 없다**.
    const s = await snapshot({ overview: { ok: true, counts: counts({ total: 0, dock_ready: 0, internal_ready: 0 }) } });
    out.noGames = {
      keys: keysOf(s.view.lines),
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      labels: s.view.bulk.map((b) => b.label),
      texts: s.view.texts,
    };
  }

  // ═══ ③ 실패 줄 + 시각 · 승계 · 소거 ═══════════════════════════════════════
  {
    const s = await snapshot({ overview: { ok: false, code: "REGISTRY_UNREADABLE" } });
    out.loadFailed = {
      lines: s.view.lines.map((l) => ({ key: l.key, text: l.text, color: l.color, stamped: l.stamped })),
      count: s.view.count,
      // ★ C-1: 조회 실패도 **counts 미도착**이다 — 라벨 괄호 부재·비활성을 로딩과 같은 잣대로 잰다.
      labels: bulkOf(s.ui.ui()).map((b) => b.label),
      disabled: bulkOf(s.ui.ui()).map((b) => b.disabled),
      // ★ 12판(N-e): 조회 실패도 §3-D 판정표 **1행**(`!counts`)이 덮는 상태다 — 실패는
      //   `overview`를 만들지 않으므로 `counts`가 없다. 여기서 `texts`를 모으지 않던 탓에
      //   *"조회 실패에서 설명 줄이 되살아나도 초록불"*인 구멍이 있었다.
      texts: s.view.texts,
    };

    // **같은 모듈을 다시 마운트** = QAM을 닫았다 다시 연 것이다(F20 승계).
    SCENE.hang = true;                       // 새 조회는 아직 안 왔다
    const again = mount(s.mod);
    await settle();
    out.failureCarried = boxLines(again.ui()).map((l) => ({ key: l.key, text: l.text }));
    // ★ 12판(N-e): **실패 승계 재개방**도 판정표 1행이 덮는 상태다(새 조회는 아직 안 왔다).
    out.failureCarriedTexts = seen(again.ui());

    // 새 로드가 성공하면 승계된 실패는 거둔다(§3-B 수명).
    SCENE.hang = false;
    SCENE.overview = { ok: true, counts: counts() };
    const third = mount(s.mod);
    await settle();
    await settle();
    out.failureCleared = keysOf(boxLines(third.ui()));
  }

  // ═══ ⑤ 확인창 게이트(§3-E) + 결과 줄(⑤⑥⑦) ═══════════════════════════════
  {
    const run = await driveApply({
      hang: false,
      holdApply: false,
      previewTotal: 42,                        // overview.total(9)과 **다르다**
      overview: { ok: true, counts: counts() },
      applyResult: (profile) => ({
        ok: true,
        data: {
          results: [
            { appid: "1", name: "게임 하나", outcome: "applied", code: null, note: "" },
            { appid: "2", name: "게임 둘", outcome: "refused", code: "GAME_RUNNING", note: "" },
            { appid: "3", name: "게임 셋", outcome: "refused", code: "CONFIG_MISSING", note: "" },
          ],
          counts: { applied: 1, refused: 2 },
          checkin: [{ appid: "1", name: "게임 하나", profile }],
        },
      }),
    }, "dock");
    out.confirm = {
      blocked: run.blocked,
      firstCall: run.firstCall,
      secondCall: run.secondCall,
      confirmFound: run.confirmFound,
      confirmTexts: run.confirmTexts,
    };
    out.resultProblem = {
      lines: (run.afterLines || []).map((l) => ({
        key: l.key, text: l.text, color: l.color, icons: l.icons, stamped: l.stamped,
        headline: l.headline, headlineInHead: l.headlineInHead,
      })),
      groups: (run.afterBox ? run.afterBox.groups : []).map((g) => ({
        opacity: g.opacity, marginBottom: g.marginBottom, keys: g.lines.map((l) => l.key),
        borderRadius: g.borderRadius, padding: g.padding, fontSize: g.fontSize,
        innerGap: g.innerGap, border: g.border,
      })),
      toasts: calls.toasts.length,
    };
  }
  {
    // 문제 0 · 체크인 0 — 아이콘은 체크, 사유·체크인 줄은 아예 없다.
    const run = await driveApply({
      previewTotal: 3,
      overview: { ok: true, counts: counts() },
      applyResult: () => ({
        ok: true,
        data: {
          results: [{ appid: "1", name: "게임 하나", outcome: "applied", code: null, note: "" }],
          counts: { applied: 1 },
          checkin: [],
        },
      }),
    }, "internal");
    out.resultClean = {
      lines: (run.afterLines || []).map((l) => ({ key: l.key, text: l.text, icons: l.icons })),
      groups: (run.afterBox ? run.afterBox.groups : []).map((g) => g.lines.map((l) => l.key)),
    };
  }

  // ═══ ① 진행 중 문구 2종 + 과거군 투명도 ═══════════════════════════════════
  {
    // 먼저 결과를 하나 만들어 과거군을 채운 뒤, 다음 일괄에서 busy 화면을 잰다.
    const run = await driveApply({
      holdApply: false,
      previewTotal: 5,
      overview: { ok: true, counts: counts() },
      applyResult: () => ({
        ok: true,
        data: { results: [], counts: { applied: 0 }, checkin: [] },
      }),
    }, "dock");
    const ui = run.s.ui;

    SCENE.holdApply = true;
    const btn = bulkOf(ui.ui())[0];
    if (btn) btn.onClick();                       // 1차 = 미리보기(무쓰기)
    await settle();
    out.previewing = {
      keys: keysOf(boxLines(ui.ui())),
      texts: boxLines(ui.ui()).map((l) => l.text),
      pastOpacity: ((statusBox(ui.ui()) || { groups: [] }).groups[1] || {}).opacity,
      // 두 군이 **함께 있을 때**의 분리 — 여백은 이 상황에서만 의미가 있다(D06).
      // 10판: 간격은 카드가 아니라 **컨테이너 gap**이 소유한다(문이 하나).
      boxGap: (statusBox(ui.ui()) || {}).gap,
      groups: (statusBox(ui.ui()) || { groups: [] }).groups.map((g) => ({
        keys: g.lines.map((l) => l.key), marginBottom: g.marginBottom, opacity: g.opacity,
      })),
    };
    // ⚠️ 아래는 **변조된 소스에서도 죽지 않아야 한다** — 프로브가 죽으면 판정이 "검사 무효"로
    //   뭉개져 어떤 위반이었는지 사라진다. 없으면 없다고 적고 지나간다(판정은 호출부가 한다).
    if (releaseApply) releaseApply();    // 미리보기 응답 도착 → 확인창
    await settle();
    const lastModal = calls.modals[calls.modals.length - 1] || null;
    const confirm = lastModal ? find(lastModal, "ConfirmModal") : null;
    if (confirm) confirm.node.props.onOK();   // 2차 = 실행(토큰)
    await settle();
    out.applying = {
      keys: keysOf(boxLines(ui.ui())),
      texts: boxLines(ui.ui()).map((l) => l.text),
      pastOpacity: ((statusBox(ui.ui()) || { groups: [] }).groups[1] || {}).opacity,
      confirmFound: !!confirm,
    };
    if (releaseApply) releaseApply();
    await settle();
    SCENE.holdApply = false;
    out.afterBusy = {
      keys: keysOf(boxLines(ui.ui())),
      pastOpacity: ((statusBox(ui.ui()) || { groups: [] }).groups[0] || {}).opacity,
    };
  }

  // ═══ 결과 전달(확인 모달 중 재마운트) — 실기 결함 #3 회귀 잠금 ════════════
  //
  // ★★ 재는 것: **적용이 끝나는 시점에 그 결과를 시작한 화면이 이미 죽어 있어도**, 그때
  //   살아 있는 화면이 결과를 받는가. 실기 증상은 *"적용은 됐는데 결과 카드가 안 뜨고 QAM을
  //   닫았다 열어야 뜬다"*였다 — 원인은 `useState(lastSummary)`가 **마운트 순간 한 번만** 읽는
  //   것이었고(§3-E 확인 모달이 열리는 동안 QAM 패널이 언마운트된다), 재마운트가 완료보다
  //   빠르면 새 인스턴스는 결과를 영영 모른다.
  // ★ 위의 「요약 승계」 시나리오는 이것을 **못 잡는다**: 거기서는 완료가 재마운트보다 앞서
  //   `useState`가 이미 값을 읽는다. 순서를 뒤집어야 드러나는 결함이라 자리를 따로 둔다.
  {
    const s = await snapshot({
      // ⚠️ 1차(미리보기)까지 붙잡으면 **확인창이 뜨지 않는다** — 재현하려는 경합은 확인창
      //   *뒤*에 있으므로, 1차는 통과시키고 2차(확정 실행)만 붙잡는다.
      holdApply: false,
      previewTotal: 2,
      overview: { ok: true, counts: counts() },
      // ★★ **요약 문 단독 경로**를 고른다(`ok:false` 정지 갈래 — `keepSummary`만 부르고
      //   `setFailure`를 뒤따르지 않는다. 성공 갈래는 `keepSummary(); setFailure(null);`이라
      //   **실패 문의 통지에 요약이 편승**해, 요약 쪽 통지를 지워도 화면이 채워진다 —
      //   두 문이 서로를 가려 대조군이 새는 자리였다).
      applyResult: () => ({ ok: false, code: "UNEXPECTED", params: { checkin: ["1", "2"] } }),
    });
    const btn = bulkOf(s.ui.ui()).find((b) => b.label.indexOf("PROFILE_DOCK") > 0);
    if (btn) btn.onClick();                       // 1차 = 미리보기(무쓰기) → 확인창
    await settle();
    SCENE.holdApply = true;                       // 여기서부터 2차를 붙잡는다
    // ★ 확정 실행 뒤에 붙는 재조회(§4-F ③)도 붙잡는다 — 그 조회가 성공하면 `setFailure(null)`이
    //   돌아 **또 편승 통지**가 생긴다. 재는 것은 "요약 문 하나로 화면이 채워지는가"다.
    SCENE.holdOverview = true;
    const confirm = calls.modals[0] ? find(calls.modals[0], "ConfirmModal") : null;
    if (confirm) confirm.node.props.onOK();       // 2차 = 확정 실행(붙잡혀 있다)
    await settle();
    // 확인 모달이 뜬 사이 QAM이 죽는다(실기: innerText "") — 그리고 완료 **전에** 다시 열린다.
    s.ui.host.unmount();
    const reopened = mount(s.mod);
    await settle();
    out.deliveryBeforeDone = keysOf(boxLines(reopened.ui()));
    if (releaseApply) releaseApply();             // 이제야 적용이 끝난다
    await settle();
    await settle();
    out.deliveryAfterDone = boxLines(reopened.ui()).map((l) => ({ key: l.key, text: l.text }));
    SCENE.holdApply = false;
    SCENE.holdOverview = false;
    releaseApply = null;
  }

  // ═══ 요약 승계(QAM 재개방) ════════════════════════════════════════════════
  {
    const run = await driveApply({
      previewTotal: 2,
      overview: { ok: true, counts: counts() },
      applyResult: () => ({
        ok: true,
        data: {
          results: [{ appid: "1", name: "게임 하나", outcome: "applied", code: null, note: "" }],
          counts: { applied: 1 },
          checkin: [],
        },
      }),
    }, "dock");
    const again = mount(run.s.mod);
    await settle();
    await settle();
    out.summaryCarried = boxLines(again.ui()).map((l) => ({ key: l.key, text: l.text }));
  }

  // ═══ 프로필 0 + **직전 일괄 결과** — 미렌더 조건의 두 번째 축 ══════════════
  //
  // ★★ 왜 장면이 하나 더 필요한가: `noProfilesRunning`은 **현재군**(실행 중 고지)이 프로필 수와
  //   무관함만 잰다. 그래서 *"프로필 0이면 숨긴다 — 단 실행 중일 때만 예외"*로 좁힌 구현
  //   (`if (noProfilesYet && !runningNote) return null;`)이 **전 검사를 통과했다.** §3-B의 계약은
  //   *"현재군·과거군 줄이 모두 0일 때만 미렌더"*이고 과거군도 프로필 수를 보지 않으므로,
  //   그 축을 잴 표본이 없으면 검사가 계약보다 좁아진다.
  // ★ 이 상태는 실사용에서 도달한다: **일괄 적용을 한 뒤 등록을 전부 해제하면** 프로필 0인데
  //   직전 결과는 남아 있다. 기존 「요약 승계」와 같은 결과 주입을 쓰되, **재개방 시점의 현황만**
  //   프로필 0으로 바꾼다(`lastSummary`는 모듈 변수라 승계된다 — §3-B 수명).
  {
    const run = await driveApply({
      previewTotal: 2,
      overview: { ok: true, counts: counts() },
      applyResult: () => ({
        ok: true,
        data: {
          results: [{ appid: "1", name: "게임 하나", outcome: "applied", code: null, note: "" }],
          counts: { applied: 1 },
          checkin: [],
        },
      }),
    }, "dock");
    SCENE.overview = {
      ok: true,
      counts: counts({ dock_ready: 0, internal_ready: 0, running: 0 }),
    };
    const again = mount(run.s.mod);
    await settle();
    await settle();
    out.noProfilesSummary = {
      boxNull: statusBox(again.ui()) === null,
      lines: boxLines(again.ui()).map((l) => ({ key: l.key, text: l.text })),
      count: countLine(again.ui()),
      texts: seen(again.ui()),
    };
  }

  // ═══ 프로필 0 + **실패 줄** — 미렌더 조건의 세 번째 축 ════════════════════
  //
  // ★ `failureCarried`로는 이 축을 못 덮는다: 거기는 **counts 미도착** 상태라(승계된 실패 +
  //   새 조회 없음) "프로필 0"이라는 사실 자체가 화면에 없다. 여기서는 조회가 성공해 counts가
  //   도착해 있고(프로필 0), 그 위에서 팝업을 못 띄워 실패 줄이 선다 — 두 사실이 동시에 참인
  //   유일한 표본이다. 실패도 프로필 수를 보지 않으므로 상태박스는 선다.
  {
    const s = await snapshot({
      modalThrows: true,
      overview: { ok: true, counts: counts({ dock_ready: 0, internal_ready: 0, running: 0 }) },
    });
    entriesOf(s.ui.ui())[0].onClick();
    await settle();
    out.noProfilesFailure = {
      boxNull: statusBox(s.ui.ui()) === null,
      lines: boxLines(s.ui.ui()).map((l) => ({ key: l.key, text: l.text })),
      texts: seen(s.ui.ui()),
    };
    SCENE.modalThrows = false;
  }

  // ═══ ④ 팝업 3종 배선 + onMutate 멱등 ═════════════════════════════════════
  {
    const s = await snapshot({
      hang: false, holdApply: false, modalThrows: false,
      overview: { ok: true, counts: counts() },
    });
    const opened = [];
    for (const entry of entriesOf(s.ui.ui())) {
      calls.modals.length = 0;
      entry.onClick();
      await settle();
      const node = calls.modals[0] || null;
      opened.push({
        label: entry.label,
        component: node ? node.name : null,
        hasOnMutate: !!(node && typeof node.props.onMutate === "function"),
      });
    }
    out.wiring = opened;

    // 멱등: 같은 통지를 여러 번 받아도 화면은 같은 자리에 머문다(거부에도 발화하므로 반복이 실재).
    calls.modals.length = 0;
    entriesOf(s.ui.ui())[0].onClick();
    await settle();
    // 통지 자체가 없는 변조(onMutate 미전달)에서도 죽지 않는다 — 그 위반은 위 `wiring`이 잡는다.
    const notify = (calls.modals[0] && calls.modals[0].props.onMutate) || (() => {});
    const before = calls.overview;
    notify();
    await settle();
    const once = { overview: calls.overview - before, texts: seen(s.ui.ui()).join("|") };
    notify(); notify(); notify();
    await settle();
    const thrice = { overview: calls.overview - before, texts: seen(s.ui.ui()).join("|") };
    out.idempotent = {
      onceCalls: once.overview,
      thriceCalls: thrice.overview,
      sameScreen: once.texts === thrice.texts,
      applyCalls: calls.apply.length,
      boxKeys: keysOf(boxLines(s.ui.ui())),
    };
  }

  // ═══ ④ 팝업을 못 띄운 경우 — **어느 화면인지** 말한다(F21) ═══════════════
  {
    const s = await snapshot({ modalThrows: true, overview: { ok: true, counts: counts() } });
    const notes = [];
    for (const entry of entriesOf(s.ui.ui())) {
      entry.onClick();
      await settle();
      notes.push({
        label: entry.label,
        lines: boxLines(s.ui.ui()).filter((l) => l.key === "failure").map((l) => l.text),
      });
    }
    out.modalFailure = notes;
    out.modalFailureApplyCalls = calls.apply.length;   // 팝업 실패가 적용을 부르지 않는다
    SCENE.modalThrows = false;
  }

  // ═══ R1 일괄 적용 **실패 봉투** — 체크인·요약·재조회 ═════════════════════
  //
  // 백엔드는 `save_registry`가 실패하면 **설정 파일을 이미 바꾼 뒤**에
  // `Refused(code=UNEXPECTED, checkin=관측값)`을 낸다(main.py:861-862 · D-02).
  // 그 봉투에는 체크인된 게임 목록이 실려 있는데, 화면은 오래 침묵했다(P15-E R1).
  {
    const run = await driveApply({
      hang: false, holdApply: false, holdOverview: false, previewTotal: 7,
      overview: { ok: true, counts: counts() },
      applyResult: () => ({
        ok: false,
        code: "UNEXPECTED",
        params: {
          checkin: [
            { appid: "1", name: "게임 하나", profile: "dock" },
            { appid: "2", name: "게임 둘", profile: "internal" },
          ],
        },
      }),
    }, "dock");
    const overviewAfterApply = calls.overview;
    await settle();
    out.applyFailed = {
      blocked: run.blocked,
      lines: (run.afterLines || []).map((l) => ({
        key: l.key, text: l.text, color: l.color, icons: l.icons, stamped: l.stamped,
        headline: l.headline, headlineInHead: l.headlineInHead,
      })),
      groups: (run.afterBox ? run.afterBox.groups : []).map((g) => g.lines.map((l) => l.key)),
      // 확정 실행은 성공·실패를 가리지 않고 다시 읽는다(§4-F ③) — 마운트 1 + 실패 뒤 1.
      overviewCalls: overviewAfterApply,
      toasts: calls.toasts.length,
    };
    // 실패도 **QAM 재개방을 넘어 승계**된다(§3-B 수명 — 성공 요약과 같은 규칙).
    const again = mount(run.s.mod);
    await settle();
    await settle();
    out.applyFailedCarried = boxLines(again.ui()).map((l) => ({ key: l.key, text: l.text }));
  }

  // ═══ C4 **조회 보류 중** — 잠금축과 표시축이 갈라져 있는가 ════════════════
  //
  // 두 축은 묻는 것이 다르다: 상태박스는 *"화면이 무슨 일을 한다고 말해야 하는가"*(변이만 —
  // 재조회에 "적용 중"이라 말하면 거짓이다, D14)이고, 버튼 잠금은 *"지금 쓰기를 시작해도
  // 되는가"*(조회 포함 — 읽는 중에 쓰기를 시작하면 방금 읽던 것과 다른 현황 위에서 쓴다)이다.
  // 그리고 **팝업 진입은 어느 쪽도 아니다** — 팝업은 열리자마자 자기 조회를 하고 자기 문을 쓴다.
  {
    const s = await snapshot({
      hang: false, holdApply: false, holdOverview: false, modalThrows: false,
      overview: { ok: true, counts: counts() },
    });
    // 데이터는 이미 도착했다(대상 있음 = 평소라면 눌리는 상태). 여기서 **조회 하나를 붙잡는다.**
    SCENE.holdOverview = true;
    calls.modals.length = 0;
    const entry = entriesOf(s.ui.ui())[0];
    if (entry) entry.onClick();
    await settle();
    const popup = calls.modals[0] || null;
    if (popup && popup.props.onMutate) popup.props.onMutate();   // 팝업 통지 → 재조회 1회(보류)
    await settle();
    out.queryPending = {
      held: heldOverviews.length,
      bulkDisabled: bulkOf(s.ui.ui()).map((b) => b.disabled),
      entryDisabled: entriesOf(s.ui.ui()).map((b) => b.disabled),
      keys: keysOf(boxLines(s.ui.ui())),
      texts: boxLines(s.ui.ui()).map((l) => l.text),
    };
    // 보류를 풀어 다음 장면으로 새지 않게 한다 — 그리고 문이 **다시 열리는지**까지 본다.
    heldOverviews.splice(0).forEach((resolve) => resolve(
      overviewEnvelope({ ok: true, counts: counts() })));
    await settle();
    out.queryPending.bulkAfter = bulkOf(s.ui.ui()).map((b) => b.disabled);
    SCENE.holdOverview = false;
  }

  // ═══ R2 조회 **역순 도착** — 낡은 응답이 새 화면을 덮는가 ═════════════════
  //
  // QAM의 재조회는 겹친다(팝업 통지는 거부에도 오고, 확정 실행 뒤에도 자동으로 붙는다).
  // 먼저 나간 조회가 **나중에** 도착하는 것은 실사용에서 흔한 순서다.
  async function driveStale(staleEnvelope) {
    const s = await snapshot({
      hang: false, holdApply: false, holdOverview: true, modalThrows: false,
      overview: { ok: true, counts: counts() },
    });
    // 팝업을 열어 **그 팝업의 통지**로 두 번째 조회를 만든다(실사용의 그 경로 그대로).
    const entry = entriesOf(s.ui.ui())[0];
    calls.modals.length = 0;
    if (entry) entry.onClick();
    await settle();
    const popup = calls.modals[0] || null;
    if (popup && popup.props.onMutate) popup.props.onMutate();
    await settle();
    // 새 세대(두 번째)가 **먼저** 도착한다.
    if (heldOverviews[1]) {
      heldOverviews[1](overviewEnvelope({ ok: true, counts: counts({ total: 3, dock_ready: 1, internal_ready: 1 }) }));
    }
    await settle();
    const afterNew = { count: countLine(s.ui.ui()), keys: keysOf(boxLines(s.ui.ui())) };
    // 낡은 세대(첫 번째)가 뒤늦게 도착한다 — **없던 일이어야 한다.**
    if (heldOverviews[0]) heldOverviews[0](staleEnvelope);
    await settle();
    return {
      loads: heldOverviews.length,
      afterNew,
      afterStale: { count: countLine(s.ui.ui()), keys: keysOf(boxLines(s.ui.ui())) },
    };
  }

  out.staleOrder = await driveStale(
    overviewEnvelope({ ok: true, counts: counts({ total: 9, dock_ready: 9, internal_ready: 8 }) }),
  );
  out.staleFailure = await driveStale(overviewEnvelope({ ok: false, code: "REGISTRY_UNREADABLE" }));
  SCENE.holdOverview = false;

  console.log(JSON.stringify(out));
})();
