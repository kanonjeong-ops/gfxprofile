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
//
// ⚠️ **실패 봉투의 `params`에도 값이 실릴 수 있다.** 적용 계열은 실패해도 `checked_in`/`checkin`을
//    싣는다(F6 — 체크인은 적용 실패보다 먼저 일어날 수 있다). 표시 층만 이 값을 소비한다.

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
  /**
   * 그 게임의 백업 개수 — 「관리」 탭의 `[백업 N]` 라벨과 **비활성 판정**이 쓴다.
   * ★ **백엔드가 센다**(counts와 같은 규칙). 0이면 버튼을 비활성으로 그린다 —
   *   없는 조작을 권하지 않는다. `disk_matches`와 달리 `detail`과 무관하게 온다
   *   (관리 탭은 원본 설정 파일 전수 sha1을 피하려고 `detail=false`로 부른다).
   */
  backups: number;
  /**
   * 그 게임의 설정 파일 경로 — **표시 전용**이다.
   * ★ 프론트는 이 값으로 **경로 연산을 하지 않는다**(자르기·이어붙이기 금지). 백엔드가
   *   손상 registry를 정규화해서 준다 — 문자열이 아니거나 그 게임의 데이터 경로가 제자리가
   *   아니면 빈 문자열이고(등록 해제 확인창의 `config_path`와 **같은 판정**), **빈 값이면
   *   화면이 그 줄을 그리지 않는다**(기존 "0이면 안 그림" 문법).
   */
  config_path: string;
  /**
   * 두 프로필의 내용이 같은가(H3) — "갈아끼워도 달라지는 게 없다"를 화면이 말할 때 쓴다.
   * ★ **판정은 백엔드가 한다**(프론트 재계산 금지). 둘 다 적용 가능하고 두 meta sha가 비어
   *   있지 않으며 서로 같을 때만 참이다 — 조회 실패끼리의 우연한 일치로 참이 되지 않는다.
   */
  profiles_identical: boolean;
  /**
   * 슬롯별 **마지막 저장 시각의 표시값**(F5). 없으면 빈 문자열이다.
   * ★ 포맷은 **백엔드가 만든다** — 프론트가 날짜 문자열을 쪼개면 판정이 두 곳으로 갈린다.
   * ⚠️ 「저장」이지 **「적용」이 아니다.** 복원은 `last_applied`를 갱신하지 않으므로
   *   (M1 fence 동작) 두 개념을 화면에서 섞으면 낡은 값이 사실인 척 보인다.
   */
  saved_at: Record<Profile, string>;
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
  /**
   * 감지에서 제외한 게임 수(A9). 설정의 **[전체 초기화] 활성 조건**이 쓴다:
   * `total > 0 || excluded > 0`. 마지막 게임을 등록 해제하면 `total=0`인데 제외 목록은
   * 남으므로, total만 보면 그 목록을 지울 방법이 화면에서 사라진다.
   * ⚠️ **원본 키 수**다 — 표시할 수 없어 격리된 손상 항목도 "초기화로 지울 것"에는 포함된다.
   */
  excluded: number;
}

export interface Overview {
  games: OverviewGame[];
  counts: OverviewCounts;
  /**
   * 사용자가 정한 **프로필 표시명**(F11 ①). 빈 문자열이면 기본 이름(=`PROFILE_*` 번역)이다.
   * ★★ 표시 계층뿐이다 — 식별자 `dock`/`internal`은 경로·RPC 인자·registry 키로 **불변**이다.
   */
  profile_names: Record<Profile, string>;
}

// `detail`을 켜면 게임별 `disk_matches`(sha1 대조)까지 온다. QAM·설정 팝업은 안 쓰고
// **팝업 G(게임 목록)만** 쓴다 —
// 200게임에서 그 계산은 파일 크기에 좌우돼 예산을 예측할 수 없다(설계 §0-A·§9-F A-3).
export const getOverview = rpc<[detail?: boolean], Overview>("get_overview");

/**
 * 게임 하나에 적용. 보조 동작이다(주 동작은 일괄 적용).
 *
 * ★ `checked_in` = 적용 **전에** 엔진이 현재 디스크를 되쓴 직전 프로필(F6). 없으면 `null`.
 *   체크인은 조용한 덮어쓰기라(백업 링 1칸 소모) 화면이 그 사실을 말해야 한다.
 * ⚠️ **실패 봉투(`params`)에도 실린다** — "적용은 실패했는데 프로필은 이미 바뀐" 상태가
 *   실재한다(엔진은 체크인을 쓴 뒤에 백업·쓰기 실패로 거부할 수 있다). 실패 note에도 병기한다.
 */
export const applyProfile = rpc<
  [appid: string, profile: Profile],
  { notes: string[]; sha1: string; checked_in: Profile | null }
>("apply_profile");

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

/** 체크인이 일어난 게임 한 건(F6). `profile` = 현재 디스크가 되쓰인 **직전 프로필**이다. */
export interface CheckinRow {
  appid: string;
  name: string;
  profile: Profile;
}

export interface ApplyAllResult {
  results: ApplyRow[];
  counts: Partial<Record<Outcome, number>>;
  /**
   * 이번 일괄 적용에서 **체크인이 일어난 게임들**(F6). 없으면 빈 배열이다.
   * ★ 결과 행(`results`)은 엔진 반환 그대로이고 이 값은 **별도 필드**다 — 행을 변형하면
   *   route와 엔진 직접 호출의 동등성(G10)이 무너진다.
   * ⚠️ `applyProfile`과 같이 **실패 봉투에도** 실릴 수 있다(`params.checkin`).
   */
  checkin: CheckinRow[];
}

// ⚠️ 게임별 실패가 있어도 **봉투는 ok:true**다. 봉투를 실패로 만들면
//    "하나가 실패해도 나머지는 계속"이라는 M1 불변식이 봉투 층에서 뒤집힌다.
/**
 * `apply_all`이 `CONFIRM_REQUIRED`로 돌려주는 `params` — **아직 아무것도 쓰지 않았다.**
 *
 * 숫자는 **예상**이다(확정치가 아니다). 확인창을 띄운 사이 게임이 설정을 다시 쓸 수 있고,
 * 실행 시점에만 나는 실패(백업 실패 등)는 미리보기가 예측할 수 없다 —
 * **결과의 정본은 실행 후 요약과 백엔드 로그**다. 화면 문구에 「예상」을 박아 둔다.
 *
 * ★ 다섯 버킷은 엔진의 결과 코드 5종을 **빠짐없이 안전하게 분류**한다(정확한 표현은 이것이다 —
 *   `running_refused`는 `refused` 중 실행 중인 것, `cannot_apply`는 나머지 `refused`와 `error`를
 *   함께 받으므로 대응이 1:1은 아니다). 게임 하나는 정확히 한 버킷에만 든다.
 *   판정 순서 = 엔진 실행 순서이므로, **실행 중이어도 디스크가 이미 그 프로필이면 `already`**다
 *   (`running_refused`는 실제로 거부될 것 = 디스크≠프로필인 것만 담는다).
 */
export interface ApplyAllConfirmParams {
  confirm_token: string;
  /** 미리보기를 만든 방향. 토큰이 이 값에 묶여 있어 다른 프로필에는 재생되지 않는다. */
  profile: Profile;
  /**
   * 등록된 게임 수 — **토큰 발급 시점의 스냅샷**이다. 확인창 본문은 **이 값만** 그린다:
   * `getOverview`의 total은 다른 시점의 조회라 토큰이 지문 낸 대상과 어긋날 수 있다.
   * 아래 5버킷의 합 = 이 값이 계약이다.
   */
  total: number;
  would_apply: number;
  already: number;
  no_profile: number;
  /** 실행 중이라 **거부될 예상**. 표시 전용이다 — 확인창 OK의 활성 조건에 절대 들어가지 않는다. */
  running_refused: number;
  /** 프로필 본체 없음·내용 어긋남·정보 손상 등 **적용 불가 예상**. */
  cannot_apply: number;
}

/**
 * 주 동작 — 등록된 전부에 같은 프로필을 적용한다.
 *
 * ★★ **2단계 계약**이다(F8). 토큰 없이 부르면 **아무것도 쓰지 않고**
 *   `{ok:false, code:"CONFIRM_REQUIRED", params}`(미리보기)가 온다. 확인창에서 사용자가
 *   확정하면 **받은 `params.confirm_token`을 그대로 되돌려** 재호출해야 실행된다.
 *   **항상 묻는다** — 바꿀 것이 없어도 묻는다. 이 확인창의 목적은 데이터 보호가 아니라
 *   **의도치 않은 발동 차단**이라, 조건부로 만들면 방지 장치가 비결정적이 된다.
 * ⚠️ 토큰은 **선택한 프로필에 묶여** 있다 — dock 미리보기 토큰으로 internal을 적용할 수 없다.
 * ⚠️ 게임별 실패가 있어도 **봉투는 ok:true**다. 봉투를 실패로 만들면
 *    "하나가 실패해도 나머지는 계속"이라는 M1 불변식이 봉투 층에서 뒤집힌다.
 */
export const applyAll = rpc<[profile: Profile, confirm_token?: string], ApplyAllResult>("apply_all");

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

/**
 * 감지에서 제외한 게임 한 건(A9). *"삭제 = 등록 해제 + 감지 제외"*의 결과가 여기 쌓인다.
 * ★ `name`은 **제외 시점에 캡처한 값**이다 — 지운 뒤에는 registry에도 없고 미설치 게임은
 *   탐지에도 안 나오므로, 화면이 그릴 이름이 이것 말고는 없다.
 * ★ `excluded_at_label`은 **백엔드가 만든 표시값**(`YYYY-MM-DD HH:MM`)이다. 알 수 없으면 빈
 *   문자열이고, 그때 화면은 그 자리를 그리지 않는다. 프론트가 날짜를 쪼개지 않는다.
 */
export interface ExcludedRow {
  appid: string;
  name: string;
  excluded_at_label: string;
}

/**
 * 감지 제외를 해제한다 — **한 버튼 한 쓰기**다. 재포함은 **등록이 아니다**:
 * 이 호출 뒤 그 게임은 감지 목록에 후보로 다시 뜰 뿐이고, 등록은 사용자가 거기서 한다.
 * ★ 제외돼 있지 않은 appid도 **정상 종료**(멱등)다 — 호출 조건을 화면이 판단하지 않는다.
 * ★ 반환은 `discoverGames`의 `excluded`와 **같은 모양**이다(백엔드 공통 헬퍼).
 */
export const includeGame = rpc<[appid: string], { excluded: ExcludedRow[] }>("include_game");

/**
 * `discover_games` 봉투의 내용물.
 *
 * ★ 이름을 붙여 **한 곳에서만** 정의한다 — 화면(팝업 D)이 이 모양을 상태 타입으로 다시
 *   적으면 봉투가 늘어날 때 두 곳이 갈리고, 갈린 쪽은 조용히 낡는다.
 */
export interface DiscoverData {
  entries: DiscoverEntry[];
  counts: DiscoverCounts;
  /**
   * 감지에서 제외한 게임들(A9) — 「제외한 게임」 뷰의 재료다. 제외분은 `entries`에
   * **구조적으로 없다**(백엔드가 탐지 목록을 만드는 한 곳에서 거른다).
   */
  excluded: ExcludedRow[];
  /**
   * Steam 라이브러리 루트들. **탐지 0건일 때 파일 선택기를 어디서 열지**가 여기서 나온다 —
   * `entries`가 비면 시작 위치를 만들 근거가 사라지고, 그러면 0건 안내가 가리키는
   * 「파일 직접 고르기」를 그릴 수 없다(2026-08-07 QA R5). 프론트가 경로를 지어내지 않는다.
   */
  libraries: string[];
}

/** 탐지는 **인자가 없고 아무것도 쓰지 않는다**(순수 탐색). */
export const discoverGames = rpc<[], DiscoverData>("discover_games");

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
  /**
   * 등록 직후 그 게임에 **남아 있는 백업 개수**. 등록을 해제해도 백업은 남으므로, 다시 등록한
   * 순간 "복원할 것이 있다"를 안내할 수 있어야 한다(§9-③). **백엔드가 센다.**
   * 0이면 그 안내를 그리지 않는다(기존 "0이면 안 그림" 문법).
   */
  backups: number;
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
  /**
   * 슬롯별 마지막 저장 시각의 **표시값**(`YYYY-MM-DD HH:MM`). 저장된 적이 없으면 빈 문자열이다.
   * 포맷은 백엔드가 만든다 — 같은 값이 화면마다 다른 모양으로 보이지 않게 한 곳을 지난다(F5).
   */
  saved_at: Record<Profile, string>;
  /** 그 게임의 현재 백업 개수. 삭제해도 이 백업들은 남는다. */
  backups: number;
  /**
   * 그 게임의 설정 파일 경로 — 확인창의 *"설정 파일: {path}"* 한 줄이 쓴다(§9-②).
   * 대피본에는 meta가 없어 원본 경로를 아는 곳이 삭제 **전**의 registry뿐이라, 지우기 직전이
   * 그 경로를 보여줄 마지막 기회다.
   * ⚠️ **빈 문자열일 수 있다**(경로가 정상 상태가 아닌 게임). 빈 값이면 그 줄을 그리지 않는다.
   */
  config_path: string;
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
   * 사용자가 직접 정한 표시명의 개수(F11 ①). 표시명은 registry `settings`에 살아서
   * **전체 초기화에 같이 지워진다** — 모르고 잃지 않게 확인창이 미리 말한다. 0이면 안 그린다.
   */
  named: number;
  /**
   * 감지 제외 목록의 건수(A9 ④). 초기화는 registry를 통째로 갈아 끼우므로 **제외 목록도 같이
   * 지워진다** — 모르고 잃지 않게 확인창이 미리 말한다. 0이면 그 줄을 그리지 않는다.
   */
  excluded: number;
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

// ── 표시명 (F11 ①) ──────────────────────────────────────────────────────────
/**
 * 프로필의 전역 표시명을 바꾼다. **화면 글자만 바뀐다** — 저장된 프로필·백업·경로는 그대로이고
 * 식별자 `dock`/`internal`은 이 호출로 절대 움직이지 않는다.
 * ⚠️ 정정(2026-08-10 최종 QA): *"로그도 그대로"*는 틀렸다 — **감사 로그에는 새 이름이 남는다**
 *   (`main.set_profile_name`이 `name=%r`로 기록한다). 되돌리기 어려운 변경의 흔적을 남기는 것은
 *   이 프로젝트의 규칙이고, 그 값은 로그의 **내용**이지 경로·키가 아니다.
 *
 * ★ 빈 값·공백만 보내면 **기본 이름으로 되돌아간다**(거부가 아니다 — 그것이 "이름 지우기"다).
 * ★ 길이 상한을 넘으면 백엔드가 **잘라서 저장하고 결과를 돌려준다.** 화면은 돌려받은 값을
 *   그대로 그린다 — 프론트가 다시 다듬으면 사용자가 본 것과 저장된 것이 갈린다.
 */
export const setProfileName = rpc<
  [profile: Profile, name?: string],
  { profile_names: Record<Profile, string> }
>("set_profile_name");

// ── 백업 복원 (P9) ───────────────────────────────────────────────────────────
//
// ★★ **복원은 2단계 시맨틱이다.** `restoreBackup`은 **디스크(게임 설정 파일)** 만 되돌리고
//   프로필 슬롯은 건드리지 않는다. 그 내용을 슬롯에 넣는 ②는 기존 `saveProfile` 흐름이 맡는다 —
//   화면이 그 두 걸음을 안내해야 한다(①만 하고 멈춰도 정상 상태다).

/** 백업 종류. **파일명 파싱은 백엔드가 한다** — 프론트는 이 코드로 문구만 고른다. */
export type BackupKind = "disk" | "profile_dock" | "profile_internal" | "unknown";

/** 백업 한 건. 값은 전부 백엔드가 계산한 것이다(프론트는 문자열을 쪼개지 않는다). */
export interface BackupRow {
  /** 복원할 때 그대로 돌려보내는 식별자(basename). */
  backup_id: string;
  kind: BackupKind;
  /** 원본 형식 `YYYYMMDD-HHMMSS`. 정렬은 백엔드가 이미 했다 — 화면이 다시 정렬하지 않는다. */
  stamp: string;
  /** 사람이 읽는 시각. 파싱 불능이면 빈 문자열이다. */
  stamp_label: string;
  /** 백업된 설정 파일의 이름. 형식 미상이면 백업 파일명 그대로다. */
  filename: string;
  size: number;
}

/** 목록 조회 — **읽기 전용**이다. 아무것도 쓰지 않는다. */
export const listBackups = rpc<[appid: string], { backups: BackupRow[] }>("list_backups");

/**
 * `restore_backup`이 돌려주는 값 — 성공(`restored`)과 **무동작**(`already`)을 `outcome`으로 가른다.
 *
 * ⚠️ `already`는 실패가 아니다. 디스크가 이미 그 백업과 같으면 백엔드가 **엔진을 부르기 전에**
 *   돌려준다(쓰기 0 · 대피 0 · 백업 링 소모 0). 그래야 같은 행을 두 번 눌러도 되돌릴 지점이
 *   링 밖으로 밀리지 않는다.
 */
export interface RestoreResult extends RestoreConfirmParams {
  outcome: "restored" | "already";
  /** 실제로 복원한 백업의 경로(엔진 반환값). `already`면 없다. */
  restored?: string;
}

/**
 * `restore_backup`이 `CONFIRM_REQUIRED`로 돌려주는 `params`. **아직 아무것도 안 바뀌었다.**
 * (`confirm_token`은 확인 요구일 때만 실린다 — 성공 응답에는 없다.)
 */
export interface RestoreConfirmParams {
  confirm_token?: string;
  appid: string;
  backup_id: string;
  kind: BackupKind;
  stamp: string;
  stamp_label: string;
  filename: string;
  size: number;
  /** 덮어쓸 대상(=디스크)이 지금 어떤 상태인가 — 저장 확인창과 **같은 4분류**다. */
  disk_state: DiskState;
  /** `disk_state === "other_profile"`일 때 어느 프로필과 같은지. */
  matched_profile?: Profile;
}

/**
 * 백업 하나를 **디스크**로 되돌린다.
 *
 * ★ **묻는 경우와 안 묻는 경우가 갈린다**(백엔드 3-상태 판정):
 *   · 내용이 다른 파일을 덮어쓴다 → `CONFIRM_REQUIRED` + 토큰(저장·삭제와 같은 계약)
 *   · 설정 파일이 아예 없다 → 잃을 것이 없어 **묻지 않고** 재생한다
 *   · 디스크가 이미 그 백업과 같다 → `outcome:"already"`로 **아무것도 하지 않는다**
 * ⚠️ 실행 중인 게임은 **토큰을 발급하기 전에** `GAME_RUNNING`으로 거부된다 —
 *   확실히 거부될 확인을 사용자에게 시키지 않는다.
 */
export const restoreBackup = rpc<
  [appid: string, backup_id: string, confirm_token?: string],
  RestoreResult
>("restore_backup");
