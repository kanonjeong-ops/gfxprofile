"use strict";
/**
 * 확인창 spec **7종이 실제로 부르는 문구 키**를 기록한다 — `qa/test_confirm_keys.py`가 판정한다.
 *
 * ### 왜 이 프로브가 생겼나 — 50키 중 34키가 무측정이었다
 * `confirmSpecs.tsx`는 확인창 7종의 **선언 하나뿐인 정본**인데, 그 안의 키가 실제로 화면에
 * 나오는지를 재는 검사가 없었다. 2026-08-12 게이트 C6의 실증: `SAVE_CONFIRM_BACKUP_LIMIT` ·
 * `DELETE_CONFIRM_BODY` · `RESET_CONFIRM_NAMES` · `SAVE_CONFIRM_CURRENT` 를 각각 **지워도
 * 회귀 전량이 초록**이었다(검출 0). 지워진 것은 *"대피본이 곧 밀려난다"*·*"무엇을 지운다"*
 * 같은, 되돌리기 어려운 동작 직전에 사용자가 읽어야 할 문장이다.
 *
 * ### 무엇을 재는가 — 키를 **열거하지 않는다**
 * 이 프로브는 각 spec을 **분기별 장면 전량**으로 구성해 보고 그때 불린 키의 합집합을 낸다.
 * 판정기는 그 합집합을 `confirmSpecs.tsx`의 **선언(소스)** 과 대조한다:
 *   · 선언에 있는데 어느 장면에서도 안 불린 키 → 그 문장은 **도달 불가**이거나 장면이 모자라다
 *   · spec별 키 **개수 등호**(판정기의 표) → 한 줄이 조용히 사라지면 FAIL
 * 그래서 이 파일에는 키 이름이 한 개도 적혀 있지 않다 — 적어야 하는 것은 **장면**뿐이다.
 *
 * ★ `t()`/`tDefault()`는 받은 키를, `tCode()`는 **폴백 키**를 기록한다(첫 인자는 백엔드 코드라
 *   spec의 선언이 아니다 — 그쪽은 `test_codes`·`test_i18n_sets`가 본다).
 * ★ spec의 body는 JSX지만 **구성 시점에 평가**된다(컴포넌트가 아니다) — 그래서 "구성했다"가
 *   곧 "그렸다"이다. 조건부 줄(`params.x ? … : null`)도 이 시점에 갈린다.
 *
 * 실행: node qa/confirm_keys_probe.cjs [소스디렉터리]   (기본 = 이 저장소의 src)
 */
const path = require("path");
const { makeLoader } = require(path.join(__dirname, "probe_kit.cjs"));

const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(path.resolve(__dirname, ".."), "src");

globalThis.window = globalThis.window || { navigator: { userAgent: "gfxprofile-probe" } };

// ── 키 기록 목 ───────────────────────────────────────────────────────────────
let seen = [];
const modules = {
  "./i18n": {
    t: (k) => { seen.push(String(k)); return String(k); },
    tCode: (code, fallback) => { seen.push(String(fallback)); return `${code}/${fallback}`; },
    tDefault: (k) => { seen.push(String(k)); return String(k); },
  },
};

const specs = makeLoader(srcDir, modules)("confirmSpecs.tsx");
const noop = () => {};

/** 확인창 하나를 그 장면대로 구성하고, 그때 불린 키를 돌려준다. */
function drive(build) {
  seen = [];
  build();
  return seen.slice();
}

// ── 장면 ─────────────────────────────────────────────────────────────────────
//
// **분기마다 한 장면**이다. 장면이 모자라면 판정기가 "선언에는 있는데 안 불린 키"로 잡는다 —
// 그때 할 일은 키를 표에서 빼는 것이 아니라 **여기에 장면을 더하는 것**이다.
const SAVE = (over) => Object.assign(
  { size: 1234, sha1_short: "abc0123", saved_at: "2026-08-10 09:00", disk_state: "unknown", confirm_token: "T" },
  over || {});

const DELETE = (over) => Object.assign(
  { name: "게임 하나", has_dock: true, has_internal: true, backups: 2,
    config_path: "/cfg/one.ini", saved_at: { dock: "2026-08-10 09:00", internal: "2026-08-09 08:00" },
    confirm_token: "T" },
  over || {});

const RESTORE = (over) => Object.assign(
  { backup_id: "b1", stamp_label: "2026-08-10 09:00", kind: "disk", disk_state: "unknown", confirm_token: "T" },
  over || {});

const RESET = (over) => Object.assign(
  { games: 3, profiles: 6, named: 1, excluded: 2, challenge: "delete", confirm_token: "T" },
  over || {});

const SCENES = {
  makeSaveConfirmSpec: [
    // 프로필 2종 × disk_state 4분류 — `diskStateText`의 갈래가 전부 여기서 갈린다.
    ["dock·다른 프로필과 일치", () => specs.makeSaveConfirmSpec(
      SAVE({ disk_state: "other_profile", matched_profile: "internal" }), "dock", noop)],
    ["internal·게임에서 조정(unknown)", () => specs.makeSaveConfirmSpec(
      SAVE({ disk_state: "unknown" }), "internal", noop)],
    ["설정 파일 없음(missing)", () => specs.makeSaveConfirmSpec(
      SAVE({ disk_state: "missing" }), "dock", noop)],
    ["조회 실패(lookup_failed)", () => specs.makeSaveConfirmSpec(
      SAVE({ disk_state: "lookup_failed" }), "dock", noop)],
  ],
  makeDeleteConfirmSpec: [
    ["두 슬롯 다 있음·경로 있음", () => specs.makeDeleteConfirmSpec(DELETE(), noop)],
    ["빈 슬롯 섞임·저장 시각 없음", () => specs.makeDeleteConfirmSpec(
      DELETE({ has_internal: false, saved_at: { dock: "", internal: "" } }), noop)],
    ["unsafe-key(경로 빈 값 — R-11)", () => specs.makeDeleteConfirmSpec(
      DELETE({ config_path: "" }), noop)],
  ],
  makeRestoreConfirmSpec: [
    ["프로필 대피본(후속 제안 예고)", () => specs.makeRestoreConfirmSpec(
      RESTORE({ kind: "profile_dock", disk_state: "other_profile", matched_profile: "dock" }), noop)],
    ["disk 백업(2단계 고지)", () => specs.makeRestoreConfirmSpec(
      RESTORE({ kind: "disk", disk_state: "unknown" }), noop)],
    // 두 프로필 이름이 **둘 다** 나오는지는 `other_profile` 두 장면으로만 갈린다
    // (이 spec은 프로필 이름을 `diskStateText` 경유로만 부른다).
    ["다른 프로필과 일치(internal)", () => specs.makeRestoreConfirmSpec(
      RESTORE({ kind: "disk", disk_state: "other_profile", matched_profile: "internal" }), noop)],
    ["설정 파일 없음(missing)", () => specs.makeRestoreConfirmSpec(
      RESTORE({ disk_state: "missing" }), noop)],
    ["조회 실패(lookup_failed)", () => specs.makeRestoreConfirmSpec(
      RESTORE({ disk_state: "lookup_failed" }), noop)],
  ],
  makeRestoreFollowUpSpec: [
    ["dock", () => specs.makeRestoreFollowUpSpec("dock", noop)],
    ["internal", () => specs.makeRestoreFollowUpSpec("internal", noop)],
  ],
  makeDiscoverWarnSpec: [
    ["경고 2종", () => specs.makeDiscoverWarnSpec(
      { name: "게임 하나", config_path: "/cfg/one.ini", warnings: ["WARN_OUTSIDE_SCAN_ROOTS", "WARN_SMALL_FILE"], confirm_token: "T" },
      noop)],
    ["경고 0종(빈 목록도 그린다)", () => specs.makeDiscoverWarnSpec(
      { name: "게임 둘", config_path: "/cfg/two.ini", warnings: [], confirm_token: "T" }, noop)],
  ],
  makeResetConfirmSpec: [
    ["표시명·제외 둘 다 있음", () => specs.makeResetConfirmSpec(RESET(), "", noop, noop)],
    ["둘 다 0(줄을 그리지 않는 갈래)", () => specs.makeResetConfirmSpec(
      RESET({ named: 0, excluded: 0 }), "", noop, noop)],
  ],
  makeNameEditSpec: [
    ["기본 이름 그대로(빈 칸으로 연다)", () => specs.makeNameEditSpec(
      { profile: "dock", current: "PROFILE_DOCK" }, noop, noop)],
    ["사용자가 정한 이름(internal)", () => specs.makeNameEditSpec(
      { profile: "internal", current: "내 프로필" }, noop, noop)],
  ],
};

const out = { specs: {} };
for (const [name, scenes] of Object.entries(SCENES)) {
  const union = new Set();
  const detail = [];
  for (const [label, build] of scenes) {
    // 장면 하나가 죽어도 나머지는 잰다 — 프로브가 통째로 죽으면 판정이 "검사 무효"로 뭉개진다.
    let keys = null;
    let error = null;
    try {
      keys = drive(build);
    } catch (err) {
      error = String(err);
    }
    (keys || []).forEach((k) => union.add(k));
    detail.push({ label, keys: keys || [], error });
  }
  out.specs[name] = { keys: [...union].sort(), scenes: detail };
}
out.driven = Object.keys(SCENES).sort();

console.log(JSON.stringify(out));
