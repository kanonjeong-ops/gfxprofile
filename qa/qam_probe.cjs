"use strict";
/**
 * **QAM 재편(설계 §3)** 을 렌더+클릭으로 잰다 — `qa/test_qam.py`가 판정한다.
 *
 * 재는 것
 *   ① 상태박스(§3-B): 슬롯 조건 · 두 군 분리 · 시각 표기 · busy 투명도 · 승계(요약·실패) ·
 *      `NO_PROFILES_YET` 소멸 조건 · **counts 미도착에 NO_GAMES 미표시**(D01)
 *   ② 카운트 줄(§3-C)과 일괄 버튼 hint(§3-A ⓑ)
 *   ③ 설명 영역(§3-D): `QAM_ABOUT` 상시 · `QAM_ABOUT_GUIDE`는 **④와 같은 조건**(U-5)
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

/** 시각 표기(§3-B ⑤·③): 당일은 `· 14:32`, 다른 날은 `· 08-10 14:32`. */
const STAMP = /·\s(\d{2}-\d{2}\s)?\d{2}:\d{2}$/;

const styleOf = (node) => node.props.style || {};

/** 렌더 조각들을 이어 붙인 글자 — 조각 경계의 공백은 하나로 접는다. */
const flatten = (node) => texts(node).join(" ").replace(/\s+/g, " ").trim();

/** 줄 하나 — 글자·색·아이콘·시각 표기. */
function lineOf(node) {
  const text = flatten(node);
  return {
    key: node.props.key === undefined ? null : String(node.props.key),
    text,
    color: styleOf(node).color || null,
    icons: ["IconCheck", "IconWarn"].filter((name) => !!find(node, name)),
    stamped: STAMP.test(text),
  };
}

/** 상태박스(§3-B) — 없으면 null. 있으면 군 배열(위=현재군, 아래=과거군). */
function statusBox(root) {
  let box = null;
  const scan = (node) => {
    const s = styleOf(node);
    if (!box && typeof s.border === "string" && s.border.indexOf("rgba(255,255,255,0.15)") >= 0) {
      box = node;
    }
  };
  findAll(root, "div").forEach(({ node }) => scan(node));
  if (!box) return null;
  const groups = box.children.filter((c) => c && typeof c === "object" && c.props);
  return {
    groups: groups.map((g) => ({
      opacity: styleOf(g).opacity === undefined ? 1 : styleOf(g).opacity,
      marginTop: styleOf(g).marginTop === undefined ? null : styleOf(g).marginTop,
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

function buttonItems(root) {
  return findAll(root, "ButtonItem").map(({ node }) => ({
    label: flatten(node),
    description: node.props.description === undefined ? null : String(node.props.description),
    disabled: !!node.props.disabled,
    icon: node.props.icon ? node.props.icon.name : null,
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
  if (!btn || btn.disabled) return { s, blocked: true };
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
      bulkIcons: s.view.bulk.map((b) => b.icon),
      bulkDisabled: s.view.bulk.map((b) => b.disabled),
      entries: s.view.entries.map((b) => ({ label: b.label, desc: b.description, icon: b.icon })),
      texts: s.view.texts,
    };
  }

  // ═══ ④ 시작 안내(H2) — NO_PROFILES_YET과 QAM_ABOUT_GUIDE는 **같은 조건** ══
  {
    const s = await snapshot({ overview: { ok: true, counts: counts({ dock_ready: 0, internal_ready: 0 }) } });
    out.noProfiles = {
      keys: keysOf(s.view.lines),
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      texts: s.view.texts,
    };
  }
  {
    // 프로필이 **하나** 생긴 순간 두 줄이 함께 사라져야 한다(조건 공유의 실증).
    const s = await snapshot({ overview: { ok: true, counts: counts({ dock_ready: 1, internal_ready: 0 }) } });
    out.oneProfile = {
      keys: keysOf(s.view.lines),
      hints: s.view.bulk.map((b) => b.description),
      texts: s.view.texts,
    };
  }
  {
    // 등록 0 — 카운트 자리가 NO_GAMES를 맡고, 시작 안내·설명 ②는 뜨지 않는다.
    const s = await snapshot({ overview: { ok: true, counts: counts({ total: 0, dock_ready: 0, internal_ready: 0 }) } });
    out.noGames = {
      keys: keysOf(s.view.lines),
      count: s.view.count,
      hints: s.view.bulk.map((b) => b.description),
      texts: s.view.texts,
    };
  }

  // ═══ ③ 실패 줄 + 시각 · 승계 · 소거 ═══════════════════════════════════════
  {
    const s = await snapshot({ overview: { ok: false, code: "REGISTRY_UNREADABLE" } });
    out.loadFailed = {
      lines: s.view.lines.map((l) => ({ key: l.key, text: l.text, color: l.color, stamped: l.stamped })),
      count: s.view.count,
    };

    // **같은 모듈을 다시 마운트** = QAM을 닫았다 다시 연 것이다(F20 승계).
    SCENE.hang = true;                       // 새 조회는 아직 안 왔다
    const again = mount(s.mod);
    await settle();
    out.failureCarried = boxLines(again.ui()).map((l) => ({ key: l.key, text: l.text }));

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
      })),
      groups: (run.afterBox ? run.afterBox.groups : []).map((g) => ({
        opacity: g.opacity, marginTop: g.marginTop, keys: g.lines.map((l) => l.key),
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
      groups: (statusBox(ui.ui()) || { groups: [] }).groups.map((g) => ({
        keys: g.lines.map((l) => l.key), marginTop: g.marginTop, opacity: g.opacity,
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
