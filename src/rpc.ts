// ★ `callable<...>`을 쓰는 **유일한 파일**이다 (설계 3-A).
//   불변식: src/ 전체에서 `callable<`가 이 파일 밖에 0건.
//   이 검사는 한 줄 안에서 끝나는 형태라 다중행 import 같은 문제가 없다 — 실제로 성립한다.
//
// 백엔드의 모든 RPC는 봉투 하나로 돌아온다. 예외 없음:
//   성공  { ok: true,  data: {...} }
//   실패  { ok: false, code: "...", params: {...} }
// `@decky/api`의 callable은 결과를 그대로 넘겨줄 뿐 봉투를 풀어주지 않는다.

import { callable } from "@decky/api";

export type Env<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; params: Record<string, unknown> };

/** route 하나를 봉투 타입으로 선언한다. */
export const rpc = <A extends unknown[], T>(route: string) => callable<A, Env<T>>(route);

// ⚠️ ok:false를 예외로 바꾸지 않는다. CONFIRM_REQUIRED처럼 **정상 흐름**인 코드가 있어서,
//    던지면 호출부가 정상 경로를 try/catch로 다루게 된다. 호출부는 code로 분기한다.

export interface Hello {
  lang: string;
  lang_source: string;
  plugin_version: string;
  session: string;
  ui_types: string;
  loader: string;
}

export const uiHello = rpc<[version: string, fn: string, uicheck_missing: string[]], Hello>("ui_hello");

// ── 프로필 식별자 ────────────────────────────────────────────────────────────
// 2개 고정이다(M2-6). 백엔드 `route` 데코레이터도 인자 이름이 `profile`이면
// {dock, internal}만 통과시킨다 — 타입과 런타임 검증이 같은 것을 말한다.
export type Profile = "dock" | "internal";

export interface OverviewGame {
  appid: string;
  name: string;
  has_dock: boolean;
  has_internal: boolean;
  disk_matches: string | null;
  last_applied: string | null;
  cloud_synced: boolean;
  running: boolean;
}

export interface OverviewCounts {
  total: number;
  /** ★ 일괄 버튼 라벨이 쓰는 수 — 등록 수가 아니라 **그 프로필을 실제로 가진 게임 수**다. */
  dock_ready: number;
  internal_ready: number;
  running: number;
  /** 두 프로필 중 하나라도 없는 게임 수. 0이면 그 줄을 그리지 않는다(설계 E8 파급 2). */
  incomplete: number;
}

export interface Overview {
  games: OverviewGame[];
  counts: OverviewCounts;
}

// `detail`을 켜면 게임별 `disk_matches`(sha1 대조)까지 온다. QAM은 안 쓰고 전체 화면만 쓴다 —
// 200게임에서 그 계산은 파일 크기에 좌우돼 예산을 예측할 수 없다(설계 §0-A·§9-F A-3).
export const getOverview = rpc<[detail?: boolean], Overview>("get_overview");

/** 게임 하나에 적용. 보조 동작이다(주 동작은 일괄 적용). */
export const applyProfile = rpc<[appid: string, profile: Profile], { notes: string[]; sha1: string }>(
  "apply_profile",
);

// ── 저장 (덮어쓰기) ──────────────────────────────────────────────────────────
/**
 * 현재 디스크 상태를 프로필로 캡처한다.
 *
 * ★ **확인은 불리언이 아니라 백엔드가 발급한 1회용 토큰이다**(설계 §2-E-0).
 *   클라이언트가 준 불리언에는 provenance가 없어서, 백엔드가 *첫 호출부터 `true`*와
 *   *확인을 거친 뒤의 `true`*를 구별할 수 없다. 토큰은 그 구별을 계약으로 만든다.
 *
 * **흐름**: 토큰 없이 호출 → 덮어쓰기면 `{ok:false, code:"CONFIRM_REQUIRED", params}` →
 * 확인창을 띄우고 사용자가 확정하면 **받은 `params.confirm_token`을 그대로 되돌려** 재호출.
 *
 * ⚠️ `CONFIRM_REQUIRED`는 **실패가 아니라 흐름 신호**다. 토스트·로그에서 에러로 취급하지 마라.
 * ⚠️ 토큰은 **그때 관측한 상태에 묶여 있다.** 확인창을 띄운 사이에 게임이 설정을 다시 썼으면
 *   토큰이 무효가 되고 갱신된 값과 함께 `CONFIRM_REQUIRED`가 다시 나온다(TOCTOU).
 */
export const saveProfile = rpc<
  [appid: string, profile: Profile, confirm_token?: string],
  { meta: { sha1: string; size: number; saved_at: string }; warning: string | null }
>("save_profile");

/** 디스크가 지금 어떤 상태인지 — 확인창이 "무엇을 덮어쓰는지"를 말할 때 쓴다. */
export type DiskState = "other_profile" | "unknown" | "missing" | "lookup_failed";

/** `CONFIRM_REQUIRED`의 `params`. 확인창이 그리는 값이 전부 여기서 온다. */
export interface ConfirmParams {
  confirm_token: string;
  /** 지금 저장돼 있는 것 */
  size: number;
  sha1_short: string;
  saved_at: string;
  /** 덮어쓸 내용(=디스크)이 어떤 상태인가 */
  disk_state: DiskState;
  /** `disk_state === "other_profile"`일 때 어느 프로필과 같은지 */
  matched_profile?: Profile;
}

/** M1 `engine.apply_all`의 결과 코드. 값까지 그대로다 — 정렬·라벨이 여기 묶인다. */
export type Outcome = "error" | "refused" | "no_profile" | "applied" | "already";

export interface ApplyRow {
  appid: string;
  name: string;
  outcome: Outcome;
  /**
   * 거부·오류의 사유 코드(`refused`/`error`일 때만 값이 있다).
   * ★ 화면은 이것으로 "조치가 같은 것"과 "게임마다 다른 것"을 가른다 —
   *   `refused` 하나에 **11종 코드**가 뭉개져 있어서 outcome만으로는 못 가른다.
   *   `note`(한국어 자유문)를 파싱하지 않는다. 그건 v2가 명시적으로 버린 방식이다.
   */
  code?: string | null;
  /** 엔진이 쓴 사람용 설명. 화면에는 안 뜨고 백엔드 로그에만 남는다. */
  note: string;
}

export interface ApplyAllResult {
  results: ApplyRow[];
  counts: Partial<Record<Outcome, number>>;
}

// ⚠️ 게임별 실패가 있어도 **봉투는 ok:true**다. 봉투를 실패로 만들면
//    "하나가 실패해도 나머지는 계속"이라는 M1 불변식이 봉투 층에서 뒤집힌다.
export const applyAll = rpc<[profile: Profile], ApplyAllResult>("apply_all");

// ── 게임 추가 (P6) ───────────────────────────────────────────────────────────

/** 설정 파일 후보 하나. `reason`(엔진의 한국어 자유문)은 오지 않는다 — 문구는 `tier`로 고른다. */
export interface DiscoverCandidate {
  path: string;
  /** 1 = UE 표준 경로 · 2 = 알려진 이름 · 3 = 이름만 그럴듯함 */
  tier: number;
  size: number;
  mtime_label: string;
}

export interface DiscoverEntry {
  appid: string;
  name: string;
  /** 파일 선택기의 시작 위치를 만들 때 쓴다. */
  library: string;
  confident: boolean;
  registered: boolean;
  candidate_count: number;
  /** `confident`일 때의 자동 선택값. 아니면 null. */
  best: DiscoverCandidate | null;
  /**
   * ⚠️ **애매한 게임에만 채워진다.** 확신 게임은 후보 목록을 펼칠 일이 없고(1탭 등록),
   * 설치 500게임 상한에서 전량을 실으면 봉투가 수 MB가 된다(백엔드 `_entry_payload`).
   */
  candidates: DiscoverCandidate[];
}

export interface DiscoverCounts {
  total: number;
  registered: number;
  unregistered: number;
  /** 일괄 등록 버튼의 라벨이 쓰는 수. 프론트가 다시 세지 않는다. */
  confident_unregistered: number;
}

/** 탐지는 **인자가 없고 아무것도 쓰지 않는다**(순수 탐색). */
export const discoverGames = rpc<
  [],
  {
    entries: DiscoverEntry[];
    counts: DiscoverCounts;
    /**
     * Steam 라이브러리 루트들. **탐지 0건일 때 파일 선택기를 어디서 열지**가 여기서 나온다 —
     * `entries`가 비면 시작 위치를 만들 근거가 사라지고, 그러면 0건 안내가 가리키는
     * 「파일 직접 고르기」를 그릴 수 없다(2026-08-07 QA R5). 프론트가 경로를 지어내지 않는다.
     */
    libraries: string[];
  }
>("discover_games");

export interface RegisterRow {
  appid: string;
  name: string;
  outcome: "added" | "refused" | "error";
  code?: string | null;
  note: string;
}

/**
 * 확신 후보 일괄 등록.
 *
 * ★★ **appid 목록을 보내지 않는다**(설계 D20). 백엔드가 스스로 탐지해 confident·미등록만
 *   등록한다 — 리스트 원소는 백엔드의 인자 검증(`_VALIDATORS`)을 통과하지 않으므로,
 *   목록을 보내는 순간 경로 조각 주입이 되살아난다. **인자를 없애 그 상황 자체를 없앴다.**
 * ⚠️ `apply_all`과 같다: 게임별 실패가 있어도 봉투는 `ok:true`다.
 */
export const registerConfident = rpc<
  [],
  { results: RegisterRow[]; counts: Partial<Record<string, number>> }
>("register_confident");

export interface AddGameResult {
  appid: string;
  name: string;
  config_path: string;
  cloud_synced: boolean;
  /**
   * `WARN_*` 코드. **거부가 아니다.** 값이 있다는 것은 *"이 경고들을 사용자가 이미 확인했다"*는
   * 뜻이다 — 경고가 있는 등록은 확인 토큰 없이 여기까지 올 수 없기 때문이다(아래 2단계 계약).
   */
  warnings: string[];
}

/**
 * `add_game`이 `CONFIRM_REQUIRED`로 돌려주는 `params`. **아직 등록되지 않은 상태**다.
 */
export interface AddGameConfirmParams {
  confirm_token: string;
  /** 되물어야 하는 이유. `tCode`로 문구를 고른다. */
  warnings: string[];
  /** 백엔드가 확정한 이름·경로(엔진이 정규화한 값이다 — 프론트가 보낸 문자열이 아니다). */
  name: string;
  config_path: string;
}

/**
 * 게임 하나 등록 — 후보 1탭 등록과 파일 선택기가 **같은 문**을 쓴다.
 *
 * ★ `config_path`는 프론트가 검증하지 않는다. 경계는 백엔드 엔진 하나다
 *   (`check_path` G11 → `assert_config_candidate` G14). 파일 선택기는 **편의이지 경계가 아니다** —
 *   `allowAllFiles`가 기본 true라 `.sav`도 고를 수 있고, 그것을 막는 것은 G14뿐이다.
 *
 * ★★ **2단계 계약**이다 (2026-08-07 QA R1). `WARN_*`가 나오는 파일은 첫 호출에서
 *   **저장되지 않고** `{ok:false, code:"CONFIRM_REQUIRED", params}`가 온다. 확인창을 띄우고
 *   사용자가 확정하면 **받은 `params.confirm_token`을 그대로 되돌려** 재호출해야 등록된다.
 *   취소하면 아무 일도 일어나지 않는다 — registry는 1바이트도 바뀌지 않은 상태다.
 *   ⚠️ `CONFIRM_REQUIRED`는 **실패가 아니라 흐름 신호**다(`saveProfile`과 같다).
 *   ⚠️ 경고가 없으면 토큰 없이 즉시 등록된다 — 자동 후보와 무경고 수동 선택은 묻지 않는다.
 *
 * ★ 이미 등록된 appid는 `ALREADY_REGISTERED`로 **거부**된다. 엔진 `add_game`이 기존
 *   `config_path`를 조용히 갈아치우면 다음 적용이 엉뚱한 파일을 덮어쓰기 때문이다(QA R2).
 *   경로 변경은 아직 지원하지 않는다.
 */
export const addGame = rpc<
  [appid: string, config_path: string, name?: string, confirm_token?: string],
  AddGameResult
>("add_game");

// ── 삭제·전체 초기화 (P8) ────────────────────────────────────────────────────
//
// ★★ 지우는 것은 **이 플러그인의 데이터뿐**이다: registry 항목 + `profiles/<appid>/`.
//   게임 설정 파일 원본(`config_path`)에는 손대지 않고, `backups/`도 남는다 —
//   백업이 마지막 안전망이라 삭제가 그것까지 지우면 자기 문법(G13)을 어긴다(설계 §2-A·§2-B).
//   그래서 실행 중인 게임도 막지 않는다: 상호작용이 없는 곳의 가드는 문법 오염이다.

/**
 * `delete_game`이 `CONFIRM_REQUIRED`로 돌려주는 `params`. **아직 아무것도 지워지지 않았다.**
 *
 * ⚠️ 이 값들은 확인창 전용이다 — 목록(`get_overview`)의 `has_dock`/`has_internal`과
 *   **섞어 쓰지 마라.** 저쪽은 *"적용할 수 있는가"*(meta ∧ 본체)를, 이쪽은
 *   *"지울 것이 있는가"*(meta)를 재서 판정 기준이 다르다.
 */
export interface DeleteConfirmParams {
  confirm_token: string;
  appid: string;
  name: string;
  has_dock: boolean;
  has_internal: boolean;
  /** 슬롯별 마지막 저장 시각. 저장된 적이 없으면 빈 문자열이다. */
  saved_at: Record<Profile, string>;
  /** 그 게임의 현재 백업 개수. 삭제해도 이 백업들은 남는다. */
  backups: number;
}

export interface DeleteResult {
  appid: string;
  name: string;
  /** 삭제 전에 백업으로 대피시킨 파일들(슬롯별). 비어 있으면 대피할 프로필이 없었다는 뜻이다. */
  evacuated: Partial<Record<Profile, string[]>>;
  backups: number;
}

/**
 * 게임 하나의 등록·프로필을 지운다.
 *
 * ★★ **항상 묻는다.** 저장(`saveProfile`)과 달리 "잃을 것이 없는 삭제"는 없다 —
 *   최소한 등록 메타데이터를 잃는다. 저빈도 동작이라 확인창 지옥 우려도 성립하지 않는다.
 * ⚠️ 토큰은 **그 게임의 프로필 상태에 묶여** 있다. 확인창을 띄운 사이 어느 슬롯이든
 *   저장되면 무효가 되고 갱신된 `params`와 함께 `CONFIRM_REQUIRED`가 다시 온다(TOCTOU).
 * ⚠️ `DELETE_FAILED`는 **부분 삭제 상태**를 남길 수 있는 유일한 코드다(`params.stage`에
 *   어디서 멈췄는지가 실린다). 다시 삭제하면 남은 것부터 이어서 지운다.
 */
export const deleteGame = rpc<[appid: string, confirm_token?: string], DeleteResult>("delete_game");

/** `reset_all`이 `CONFIRM_REQUIRED`로 돌려주는 `params`. **아직 아무것도 지워지지 않았다.** */
export interface ResetConfirmParams {
  confirm_token: string;
  /** 파괴 내역 — 화면이 다시 세지 않는다(두 곳에서 세면 언젠가 어긋난다). */
  games: number;
  profiles: number;
  /**
   * 사용자가 그대로 입력해야 하는 확인 단어.
   * ★★ **번역하지 않는다.** i18n에 넣는 순간 화면이 보여주는 단어와 백엔드가 대조하는
   *   상수가 언어에 따라 갈려 **입력이 영영 안 맞는** 상태가 된다. 백엔드가 준 이 값을
   *   그대로 보여주고 그대로 대조한다.
   */
  challenge: string;
}

export type ResetOutcome = "deleted" | "refused" | "error";

export interface ResetRow {
  appid: string;
  name: string;
  outcome: ResetOutcome;
  /** `refused`/`error`일 때만 값이 있다. 화면은 `note`가 아니라 이것으로 사유를 가른다. */
  code?: string | null;
  note: string;
}

export interface ResetAllResult {
  results: ResetRow[];
  counts: Partial<Record<ResetOutcome, number>>;
}

/**
 * 전체 초기화 = **개별 삭제의 반복 + registry 공장초기화**(settings·gpu_map 포함).
 * `backups/`는 그대로 남는다.
 *
 * ★★ 방어가 **2중**이다: 1회용 토큰 + type-to-confirm. 판정은 둘 다 백엔드에 있고,
 *   `confirm_text`는 토큰 튜플의 한 칸으로 비교된다 — 프론트의 OK 비활성은 UX 보조일 뿐이라
 *   그것이 런타임에 안 먹어도(§4-D U20 ②) 백엔드가 막는다.
 * ⚠️ `applyAll`과 같은 불변식: **게임별 실패가 있어도 봉투는 `ok:true`**다. 실패한 게임의
 *   registry 항목은 남는다(registry가 항상 디스크 실물과 일치한다).
 */
export const resetAll = rpc<[confirm_token?: string, confirm_text?: string], ResetAllResult>(
  "reset_all",
);
