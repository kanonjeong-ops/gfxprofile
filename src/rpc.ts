// callable<...>을 쓰는 유일한 파일이다. 백엔드의 모든 RPC는 봉투 하나로 돌아온다:
//   성공  { ok: true,  data: {...} }
//   실패  { ok: false, code: "...", params: {...} }
// 모든 호출부는 callable의 반환값을 Env<T>로 취급해 ok로 분기한다.
// 고정 @decky/api 사본은 로더의 api.callable에 위임하므로, 봉투를 변형하지 않는지는 [런타임 미확인]이다.

import { callable } from "@decky/api";

export type Env<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; params: Record<string, unknown> };

/** route 하나를 봉투 타입으로 선언한다. */
export const rpc = <A extends unknown[], T>(route: string) => callable<A, Env<T>>(route);

// ok:false를 예외로 던지지 않는다 — CONFIRM_REQUIRED처럼 정상 흐름인 코드가 있어, 던지면
//   호출부가 정상 경로를 try/catch로 다뤄야 한다. 호출부는 code로 분기한다.
// 실패 봉투의 params에도 값이 실린다: CONFIRM_REQUIRED는 확인창이 그릴 값을 전부 params로
//   싣는다(토큰 포함). 표시 층만 소비한다.

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
// dock·internal 둘뿐이다. 백엔드도 인자 이름이 profile이면 이 둘만 통과시킨다 —
// 타입과 런타임 검증이 같은 것을 말한다.
export type Profile = "dock" | "internal";

export interface OverviewGame {
  appid: string;
  name: string;
  has_dock: boolean;
  has_internal: boolean;
  /**
   * 지금 게임 설정 파일과 같은 내용인 슬롯 전부. 두 프로필 내용이 같으면 둘 다 실린다.
   * detail=false이거나 포착된 조회 실패면 빈 배열이다. ★ 19판 — 등록 항목 손상도 포착 대상이
   * 됐다(백엔드가 REGISTRY_ENTRY_CORRUPT로 거부하고 래퍼가 그것을 접는다). 손상 항목은 이
   * 배열이 비고, 목록의 나머지 게임은 그대로 온다.
   */
  disk_matches: Profile[];
  /**
   * 그 게임의 백업 개수 — 「관리」 탭의 [백업 N] 라벨과 비활성 판정이 쓴다. 백엔드가 센다;
   * 0이면 버튼을 비활성으로 그린다. disk_matches와 달리 detail과 무관하게 온다(관리 탭은
   * 전수 sha1을 피하려 detail=false로 부른다).
   */
  backups: number;
  /**
   * 그 게임의 설정 파일 경로 — 표시 전용이다. 프론트는 이 값으로 경로 연산을 하지 않는다.
   * 백엔드가 정규화해서 주며, 문자열이 아니거나 데이터 경로가 제자리가 아니면 빈 문자열이다
   * (등록 해제 확인창의 unsafe 분기와 같은 술어 — remove._paths_in_position). 빈 값이면
   * 화면이 그 줄을 그리지 않는다.
   */
  config_path: string;
  /**
   * 두 프로필의 내용이 같은가 — "갈아끼워도 달라지는 게 없다"를 화면이 말할 때 쓴다. 판정은
   * 백엔드가 한다: 둘 다 적용 가능하고 두 meta sha가 비어 있지 않고 서로 같을 때만 참이다 —
   * 조회 실패끼리의 우연한 일치로 참이 되지 않는다.
   */
  profiles_identical: boolean;
  /**
   * 슬롯별 마지막 저장 시각의 표시값. 없으면 빈 문자열이다. 포맷은 백엔드가 만든다 —
   * 프론트가 날짜 문자열을 쪼개면 판정이 두 곳으로 갈린다.
   * 「저장」이지 「적용」이 아니다: 복원은 last_applied를 갱신하지 않으므로 두 개념을 섞으면
   * 낡은 값이 사실인 척 보인다.
   */
  saved_at: Record<Profile, string>;
  last_applied: string | null;
  cloud_synced: boolean;
  running: boolean;
}

export interface OverviewCounts {
  total: number;
  /** 일괄 버튼 라벨이 쓰는 수 — 등록 수가 아니라 그 프로필을 실제로 가진 게임 수다. */
  dock_ready: number;
  internal_ready: number;
  running: number;
  /** 두 프로필 중 하나라도 없는 게임 수. */
  incomplete: number;
  /**
   * 감지에서 제외한 게임 수. 설정의 [전체 초기화] 활성 조건이 쓴다: total > 0 || excluded > 0.
   * 마지막 게임을 등록 해제하면 total=0이어도 제외 목록은 남으므로, total만 보면 그 목록을
   * 지울 방법이 화면에서 사라진다.
   * 원본 키 수다 — 표시할 수 없어 격리된 손상 항목도 "초기화로 지울 것"에 포함된다.
   */
  excluded: number;
}

export interface Overview {
  games: OverviewGame[];
  counts: OverviewCounts;
  /**
   * 사용자가 정한 프로필 표시명. 빈 문자열이면 기본 이름(=PROFILE_* 번역)이다.
   * 표시 계층뿐이다 — 식별자 dock/internal은 경로·RPC 인자·registry 키로 불변이다.
   */
  profile_names: Record<Profile, string>;
}

// detail을 켜면 게임별 disk_matches(sha1 대조)까지 온다. 팝업 G(게임 목록)만 쓴다 —
// 200게임에서 그 계산은 파일 크기에 좌우돼 예산을 예측할 수 없어, QAM·설정 팝업은 끈다.
export const getOverview = rpc<[detail?: boolean], Overview>("get_overview");

/**
 * 게임 하나에 적용 — 저장된 프로필 → 게임 설정 파일 한 방향이다.
 *
 * 2단계 계약. 백엔드가 3-상태를 판정한다:
 *   · 두 슬롯 모두와 다른 파일을 덮어쓴다 → CONFIRM_REQUIRED + 토큰
 *   · 파일이 없거나 다른 슬롯과 같다 → 잃을 것이 없어 묻지 않고 즉시 적용된다
 *   · 이미 목표 슬롯과 같다 → outcome:"already", 아무것도 하지 않는다(엔진 미호출)
 * outcome이 성공 봉투의 정본이다 — "applied"면 파일이 바뀌었고 "already"면 안 바뀌었다.
 *   무쓰기를 침묵으로 처리하면 "먹통"으로 읽히므로 결과를 말해야 한다.
 * 토큰은 방향에 묶여 있다 — dock 확인창 토큰으로 internal을 적용할 수 없다.
 */
export const applyProfile = rpc<
  [appid: string, profile: Profile, confirm_token?: string],
  { notes: string[]; sha1: string; outcome: "applied" | "already" }
>("apply_profile");

/** 백업 링이 가득 찼을 때 이번 동작으로 실제로 지워질 백업 한 건. */
export interface EvictedRow {
  /**
   * 그 백업 파일의 고유 이름(예: 20260815-120000-disk-1-video.ini). 화면에 그리지 않는다 —
   * 사람이 읽을 물건이 아니다.
   */
  backup_id: string;
  kind: BackupKind;
  stamp_label: string;
  filename: string;
  /**
   * 같은 표기가 둘 이상일 때만 1 이상이다. 그 표기를 공유하는 행을 backup_order_key 오름차순으로
   * 놓은 번호이며 실제 생성 순서를 뜻하지 않는다. 0이면 표기가 유일하다.
   */
  dup: number;
}

/**
 * apply_profile이 CONFIRM_REQUIRED로 돌려주는 params. 아직 아무것도 안 바뀌었다.
 *
 * matches는 지금 파일과 같은 슬롯 전부다(보통 빈 배열 — 비어 있지 않으면 애초에 묻지 않는다).
 * evicted는 이 동작이 실제로 지울 백업이다. 비어 있으면 그 줄을 그리지 않는다.
 */
export interface ApplyConfirmParams {
  confirm_token: string;
  appid: string;
  profile: Profile;
  /** 덮어쓸 대상(=게임 설정 파일)이 지금 어떤 상태인가 — 저장·복원 확인창과 같은 4분류다. */
  disk_state: DiskState;
  matched_profile?: Profile;
  matches: Profile[];
  /**
   * 이번 적용이 지금 게임 설정 파일의 내용을 백업으로 대피시키는가.
   *
   * 화면의 "지금 내용은 백업으로 보관합니다 — 백업 한 칸을 씁니다"가 참인 조건이고, 복원
   *   확인창과 같은 필드·같은 술어다(confirm.apply_needs_confirm의 ring["adding"]). 같은 태그의
   *   링이 이미 그 내용을 담고 있으면 엔진이 백업 링에 새 항목을 쓰지 않으므로 거짓이다 — 그때
   *   이 줄을 그리면 사용자가 링 잔량을 아끼려 적용을 미루는데 실제로는 한 칸도 안 쓴다.
   * 값이 뜻을 갖는 것은 확인을 묻는 갈래다(그때만 화면이 읽는다).
   */
  evacuates: boolean;
  evicted: EvictedRow[];
}

// ── 저장 (덮어쓰기) ──────────────────────────────────────────────────────────
/**
 * 현재 디스크 상태를 프로필로 캡처한다.
 *
 * 확인은 불리언이 아니라 백엔드가 발급한 1회용 토큰이다. 클라이언트가 준 불리언에는
 *   provenance가 없어 백엔드가 첫 호출부터 true와 확인을 거친 뒤의 true를 구별할 수 없다 —
 *   토큰이 그 구별을 계약으로 만든다.
 *
 * 흐름: 토큰 없이 호출 → 덮어쓰기면 {ok:false, code:"CONFIRM_REQUIRED", params} → 확인창을
 *   띄우고 사용자가 확정하면 받은 params.confirm_token을 그대로 되돌려 재호출.
 *
 * CONFIRM_REQUIRED는 실패가 아니라 흐름 신호다 — 토스트·로그에서 에러로 취급하지 마라.
 * 토큰은 그때 관측한 상태에 묶여 있다: 확인창을 띄운 사이 게임이 설정을 다시 썼으면 토큰이
 *   무효가 되고 갱신된 값과 함께 CONFIRM_REQUIRED가 다시 나온다(TOCTOU).
 */
export const saveProfile = rpc<
  [appid: string, profile: Profile, confirm_token?: string],
  {
    meta: { sha1: string; size: number; saved_at: string };
    /**
     * 거부가 아니라 경고 코드다(codes.py가 정본 — 지금은 WARN_SAVE_WHILE_RUNNING 하나).
     * 문장이 아니라 코드인 이유: 백엔드가 문장을 실어 보내면 영어 화면에 한국어가 붙는다.
     * 문장은 화면이 tCode로 현재 언어에서 고른다.
     */
    warning: string | null;
    /**
     * "already"면 프로필 본체·meta·백업 링은 쓰지 않았고 saved_at도 그대로다.
     * 다만 route는 registry와 그 .bak을 다시 저장하므로 RPC 전체의 무쓰기를 뜻하지 않는다.
     */
    outcome: "saved" | "already";
  }
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
  /**
   * 이 저장이 실제로 지울 백업(적용·복원과 같은 필드·같은 문구). 저장은 슬롯을 덮기 전에
   * 이전 본체를 대피시키고 그 대피가 링을 한 칸 태운다. 대피가 없는 갈래(본체 없음)에서는
   * 빈 배열이고, 그때는 그 줄을 그리지 않는다.
   */
  evicted: EvictedRow[];
}

/** engine.apply_all의 결과 코드. 값까지 그대로다 — 정렬·라벨이 여기 묶인다. */
export type Outcome = "error" | "refused" | "no_profile" | "applied" | "already";

export interface ApplyRow {
  appid: string;
  name: string;
  outcome: Outcome;
  /**
   * 거부·오류의 사유 코드(refused/error일 때만 값이 있다). 화면은 이것으로 "조치가 같은 것"과
   * "게임마다 다른 것"을 가른다 — refused 하나에 여러 코드가 뭉개져 있어 outcome만으로는 못
   * 가른다. note(한국어 자유문)는 파싱하지 않는다.
   */
  code?: string | null;
  /** 엔진이 쓴 사람용 설명. 화면에는 안 뜨고 백엔드 로그에만 남는다. */
  note: string;
}

export interface ApplyAllResult {
  results: ApplyRow[];
  counts: Partial<Record<Outcome, number>>;
}

/**
 * apply_all이 CONFIRM_REQUIRED로 돌려주는 params — 아직 아무것도 쓰지 않았다.
 *
 * 숫자는 예상이다(확정치가 아니다). 확인창을 띄운 사이 게임이 설정을 다시 쓸 수 있고, 실행
 *   시점에만 나는 실패(백업 실패 등)는 미리보기가 예측할 수 없다 — 결과의 정본은 실행 후
 *   요약과 백엔드 로그다. 화면 문구에 「예상」을 박아 둔다.
 *
 * 다섯 버킷이 엔진 결과 코드 5종을 빠짐없이 분류하고, 게임 하나는 정확히 한 버킷에만 든다.
 *   running_refused는 refused 중 실행 중인 것, cannot_apply는 나머지 refused와 error를 함께
 *   받으므로 대응이 1:1은 아니다. 판정 순서 = 엔진 실행 순서라, 실행 중이어도 디스크가 이미
 *   그 프로필이면 already다(running_refused는 디스크≠프로필인 것만 담는다).
 */
export interface ApplyAllConfirmParams {
  confirm_token: string;
  /** 미리보기를 만든 방향. 토큰이 이 값에 묶여 있어 다른 프로필에는 재생되지 않는다. */
  profile: Profile;
  /**
   * 등록된 게임 수 — 토큰 발급 시점의 스냅샷이다. 확인창 본문은 이 값만 그린다: getOverview의
   * total은 다른 시점의 조회라 토큰이 지문 낸 대상과 어긋날 수 있다. 아래 5버킷의 합 = 이 값이
   * 계약이다.
   */
  total: number;
  would_apply: number;
  already: number;
  no_profile: number;
  /** 실행 중이라 거부될 예상. 표시 전용이다 — 확인창 OK의 활성 조건에 들어가지 않는다. */
  running_refused: number;
  /** 프로필 본체 없음·내용 어긋남·정보 손상 등 적용 불가 예상. */
  cannot_apply: number;
  /**
   * 이 일괄 적용으로 지워질 백업 건수와 그런 게임 수. 게임이 여럿이라 이름은 대지 않는다 —
   * 나열하면 창이 터진다. 산출은 게임 하나짜리 확인창의 evicted[]와 같은 함수이고, 0이면 그
   * 줄을 그리지 않는다.
   */
  evicted: number;
  evict_games: number;
}

/**
 * 주 동작 — 등록된 전부에 같은 프로필을 적용한다.
 *
 * 사전 검증·registry 읽기·미리보기 산출이 성공하면, 유효한 토큰이 없는 호출은 아무것도 쓰지 않고
 * CONFIRM_REQUIRED와 미리보기를 돌려준다. 그 전 단계의 실패는 토큰 없이 다른 실패 코드로 끝날 수 있다.
 * 미리보기는 바꿀 것이 없어도 발급된다.
 * 확인창에서 확정하면 받은 params.confirm_token을 그대로 되돌려 재호출해야 실행된다.
 * 토큰은 선택한 프로필에 묶여 있다 — dock 미리보기 토큰으로 internal을 적용할 수 없다.
 * 게임별 실패가 있어도 봉투는 ok:true다 — 봉투를 실패로 만들면 "하나가 실패해도 나머지는
 *   계속"이라는 불변식이 봉투 층에서 뒤집힌다.
 */
export const applyAll = rpc<[profile: Profile, confirm_token?: string], ApplyAllResult>("apply_all");

// ── 게임 추가 ────────────────────────────────────────────────────────────────

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
   * 애매한 게임에만 채워진다. 확신 게임은 후보 목록을 펼칠 일이 없고(1탭 등록), 설치 500게임
   * 상한에서 전량을 실으면 봉투가 수 MB가 된다(백엔드 _entry_payload).
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
 * 감지에서 제외한 게임 한 건. "삭제 = 등록 해제 + 감지 제외"의 결과가 여기 쌓인다.
 * name은 제외 시점에 캡처한 값이다 — 지운 뒤에는 registry에도 없고 미설치 게임은 탐지에도
 *   안 나오므로, 화면이 그릴 이름이 이것뿐이다.
 * excluded_at_label은 백엔드가 만든 표시값(YYYY-MM-DD HH:MM)이다. 알 수 없으면 빈 문자열이고,
 *   그때 화면은 그 자리를 그리지 않는다. 프론트가 날짜를 쪼개지 않는다.
 */
export interface ExcludedRow {
  appid: string;
  name: string;
  excluded_at_label: string;
}

/**
 * 감지 제외를 해제한다. 재포함은 등록이 아니며, 호출 뒤 후보로 다시 보일 수 있을 뿐이다.
 * 제외돼 있지 않은 appid도 성공 봉투를 돌려주지만 매 호출 registry 저장과 감사 로그가 발생하므로
 * 무쓰기 멱등 동작은 아니다. 반환은 discoverGames의 excluded와 같은 모양이다.
 */
export const includeGame = rpc<[appid: string], { excluded: ExcludedRow[] }>("include_game");

/**
 * discover_games 봉투의 내용물.
 *
 * 이름을 붙여 한 곳에서만 정의한다 — 화면(팝업 D)이 이 모양을 상태 타입으로 다시 적으면
 *   봉투가 늘어날 때 두 곳이 갈리고, 갈린 쪽은 조용히 낡는다.
 */
export interface DiscoverData {
  entries: DiscoverEntry[];
  counts: DiscoverCounts;
  /**
   * 감지에서 제외한 게임들 — 「제외한 게임」 뷰의 재료다. 제외분은 entries에 구조적으로 없다
   * (백엔드가 탐지 목록을 만드는 한 곳에서 거른다).
   */
  excluded: ExcludedRow[];
  /**
   * Steam 라이브러리 루트들 — 파일 선택기를 어디서 열지가 여기서 나온다(첫 루트를 시작 위치로
   * 쓴다). 비어 있으면 선택기를 열지 않고 DISCOVER_NO_LIBRARY 안내를 띄운다(「파일 직접 고르기」
   * 버튼 자체는 무조건 그린다). 프론트가 경로를 지어내지 않는다.
   */
  libraries: string[];
}

/** 탐지는 인자가 없고 아무것도 쓰지 않는다(순수 탐색). */
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
 * appid 목록을 보내지 않는다 — 백엔드가 스스로 탐지해 confident·미등록만 등록한다. 리스트
 *   원소는 백엔드 인자 검증(_VALIDATORS)을 통과하지 않아, 목록을 받으면 경로 조각 주입 통로가
 *   열린다. 인자가 없어 그 통로도 없다.
 * apply_all과 같다: 게임별 실패가 있어도 봉투는 ok:true다.
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
   * WARN_* 코드. 거부가 아니다. 값이 있다는 것은 "이 경고들을 사용자가 이미 확인했다"는
   * 뜻이다 — 경고가 있는 등록은 확인 토큰 없이 여기까지 올 수 없다(아래 2단계 계약).
   */
  warnings: string[];
  /**
   * 등록 직후 그 게임에 남아 있는 백업 개수. 등록을 해제해도 백업은 남으므로, 다시 등록한
   * 순간 "복원할 것이 있다"를 안내할 수 있어야 한다. 백엔드가 센다. 0이면 그 안내를 안 그린다.
   */
  backups: number;
}

/**
 * add_game이 CONFIRM_REQUIRED로 돌려주는 params. 아직 등록되지 않은 상태다.
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
 * 게임 하나 등록 — 후보 1탭 등록과 파일 선택기가 같은 문을 쓴다.
 *
 * config_path는 프론트가 검증하지 않는다. 경계는 백엔드 엔진 하나다(check_path →
 *   assert_config_candidate). 파일 선택기는 편의이지 경계가 아니다 — allowAllFiles가 기본 true라
 *   .sav도 고를 수 있고, 그것을 막는 것은 assert_config_candidate뿐이다.
 *
 * 2단계 계약. WARN_*가 나오는 파일은 첫 호출에서 저장되지 않고 {ok:false,
 *   code:"CONFIRM_REQUIRED", params}가 온다. 확인창에서 확정하면 받은 params.confirm_token을
 *   그대로 되돌려 재호출해야 등록된다. 취소하면 registry는 1바이트도 바뀌지 않는다.
 *   CONFIRM_REQUIRED는 실패가 아니라 흐름 신호다(saveProfile과 같다). 경고가 없으면 토큰 없이
 *   즉시 등록된다 — 자동 후보와 무경고 수동 선택은 묻지 않는다.
 *
 * 이미 등록된 appid는 ALREADY_REGISTERED로 거부된다. 엔진 add_game이 기존 config_path를 조용히
 *   갈아치우면 다음 적용이 엉뚱한 파일을 덮어쓰기 때문이다. 경로 변경은 아직 지원하지 않는다.
 * ★ 19판 — 등록 기록이 손상된 항목은 REGISTRY_ENTRY_CORRUPT로 거부된다(그 봉투에는
 *   name·config_path가 실리지 않는다 — 못 믿는 값이다). 화면은 두 코드를 각자의 문구로 그린다.
 */
export const addGame = rpc<
  [appid: string, config_path: string, name?: string, confirm_token?: string],
  AddGameResult
>("add_game");

// ── 삭제·전체 초기화 ─────────────────────────────────────────────────────────
//
// 지우는 것은 이 플러그인의 데이터뿐이다: registry 항목 + profiles/<appid>/. 게임 설정 파일
//   원본(config_path)에는 손대지 않고, backups/도 남는다 — 백업이 마지막 안전망이라 삭제가
//   그것까지 지우면 자기 문법을 어긴다. 그래서 실행 중인 게임도 막지 않는다: 상호작용이
//   없는 곳의 가드는 문법 오염이다.

/**
 * delete_game이 CONFIRM_REQUIRED로 돌려주는 params. 아직 아무것도 지워지지 않았다.
 *
 * 이 값들은 확인창 전용이다 — 목록(get_overview)의 has_dock/has_internal과 섞어 쓰지 마라.
 *   저쪽은 "적용할 수 있는가"(meta ∧ 본체)를, 이쪽은 "지울 것이 있는가"(본체)를 재서 판정
 *   기준이 다르다.
 */
export interface DeleteConfirmParams {
  confirm_token: string;
  appid: string;
  name: string;
  has_dock: boolean;
  has_internal: boolean;
  /**
   * 슬롯별 마지막 저장 시각의 표시값(YYYY-MM-DD HH:MM). 저장된 적이 없으면 빈 문자열이다.
   * 포맷은 백엔드가 만든다 — 같은 값이 화면마다 다른 모양으로 보이지 않게 한 곳을 지난다.
   */
  saved_at: Record<Profile, string>;
  /** 그 게임의 현재 백업 개수. 삭제해도 이 백업들은 남는다. */
  backups: number;
  /**
   * 그 게임의 설정 파일 경로 — 확인창의 "설정 파일: {path}" 한 줄이 쓴다. 대피본에는 meta가
   * 없어 원본 경로를 아는 곳이 삭제 전의 registry뿐이라, 지우기 직전이 그 경로를 보여줄 마지막
   * 기회다. 빈 문자열일 수 있다(경로가 정상 상태가 아닌 게임) — 빈 값이면 그 줄을 안 그린다.
   */
  config_path: string;
  /**
   * 이 등록 해제가 실제로 지울 백업(저장·적용·복원과 같은 필드·같은 문구). 해제는 슬롯 본체를
   * 백업 링으로 대피시키므로, 링이 차 있으면 그만큼 오래된 백업이 사라진다. "현재 백업 N건"은
   * 남는 쪽을 말할 뿐 무엇이 사라지는지는 말하지 않는다.
   */
  evicted: EvictedRow[];
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
 * 항상 묻는다. 저장(saveProfile)과 달리 "잃을 것이 없는 삭제"는 없다 — 최소한 등록
 *   메타데이터를 잃는다. 저빈도 동작이라 확인창 지옥 우려도 없다.
 * 토큰은 그 게임의 프로필 상태에 묶여 있다: 확인창을 띄운 사이 어느 슬롯이든 저장되면 무효가
 *   되고 갱신된 params와 함께 CONFIRM_REQUIRED가 다시 온다(TOCTOU).
 * DELETE_FAILED는 삭제 실패를 params와 함께 신호한다(stage에 어디서 멈췄는지,
 *   profile_delete_started에 프로필 데이터 삭제가 시작됐는지가 실린다) — profile_delete_started가
 *   부분 삭제인지 아닌지를 가른다. 다시 삭제하면 남은 것부터 이어서 지운다. 단 부분완료를 남기는
 *   코드가 이것뿐은 아니다 — 프로필 데이터 삭제가 성공한 뒤 registry 저장이 실패하면 봉투는
 *   UNEXPECTED가 되고, 그때도 프로필 데이터는 지워졌는데 registry는 그대로인 부분완료가 남는다.
 *   UNEXPECTED를 「무변경」으로 다루지 마라.
 *
 * ── DELETE_FAILED의 params 계약 ──
 * - stage: 진단용 단계 이름이다. 화면 분기의 근거로 쓰지 마라 — 같은 문자열 "escape"를 다른
 *   코드(restore.py의 BACKUP_OUT_OF_ROOT)도 쓰므로 이 값만으로는 "무엇이 지워졌나"가 결정되지
 *   않는다.
 * - profile_delete_started: 화면이 읽어야 하는 사실 필드.
 *   - false — 등록 정보와 프로필 데이터의 삭제 단계가 시작되지 않았다. 그 둘은 그대로다. 단
 *     "아무것도 안 바뀌었다"가 아니다 — 삭제 전에 슬롯 본체를 백업으로 대피시키므로 백업 링은
 *     이미 바뀌어 있을 수 있다. 그래서 안전 문구의 주어를 「등록 정보와 프로필 데이터」로 한정한다.
 *   - true — 프로필 데이터가 일부 지워졌을 수 있다. 다시 삭제하면 남은 것부터 이어서 지운다.
 *   필드가 없거나 boolean이 아니면 true처럼 보수적으로 다뤄라. 백엔드는 이 필드를 DELETE_FAILED
 *   단일 생성점에서만 싣고, qa/test_delete_game.py가 그 생성점을 잠근다.
 */
export const deleteGame = rpc<[appid: string, confirm_token?: string], DeleteResult>("delete_game");

/** reset_all이 CONFIRM_REQUIRED로 돌려주는 params. 아직 아무것도 지워지지 않았다. */
export interface ResetConfirmParams {
  confirm_token: string;
  /** 파괴 내역 — 화면이 다시 세지 않는다(두 곳에서 세면 언젠가 어긋난다). */
  games: number;
  profiles: number;
  /**
   * 사용자가 직접 정한 표시명의 개수. 표시명은 registry settings에 살아서 전체 초기화에 같이
   * 지워진다 — 모르고 잃지 않게 확인창이 미리 말한다. 0이면 안 그린다.
   */
  named: number;
  /**
   * 감지 제외 목록의 건수. 초기화는 registry를 통째로 갈아 끼우므로 제외 목록도 같이 지워진다 —
   * 모르고 잃지 않게 확인창이 미리 말한다. 0이면 그 줄을 그리지 않는다.
   */
  excluded: number;
  /**
   * 사용자가 그대로 입력해야 하는 확인 단어. 번역하지 않는다 — i18n에 넣으면 화면이 보여주는
   * 단어와 백엔드가 대조하는 상수가 언어에 따라 갈려 입력이 영영 안 맞는다. 백엔드가 준 값을
   * 그대로 보여주고 그대로 대조한다.
   */
  challenge: string;
  /**
   * 이 초기화로 지워질 백업 건수와 그런 게임 수(일괄 적용과 같은 필드). 초기화는 게임마다 슬롯
   * 본체를 대피시키므로 링이 찬 게임에서는 오래된 백업이 밀려난다. 이름은 대지 않는다(게임이
   * 여럿이다). 0이면 그 줄을 그리지 않는다.
   */
  evicted: number;
  evict_games: number;
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
  /**
   * 초기화가 실제로 지운 registry settings 범주의 건수.
   *
   * 왜 결과 봉투가 들고 오나: 완료 문구가 「무엇이 사라졌는지」를 말하려면 세 범주(등록 게임·
   *   표시 이름·감지 제외)를 다 알아야 하는데, counts.deleted는 게임만 센다. 그것만으로 문장을
   *   만들면 등록 0 · 제외 N인 상태에서 화면이 "0개 삭제"라 말하면서 제외 N건과 표시 이름을
   *   조용히 잃는다.
   * 프론트가 다시 세지 않는다(counts와 같은 규칙). 확인창 params의 named/excluded와는 다른
   *   시점의 값이라 그쪽을 재사용하지도 않는다.
   * 게임별 실패와 무관하게 유효하다: reset_all은 실패분 게임만 되심으므로(fresh["games"] =
   *   dict(reg["games"])) settings는 부분 실패에도 통째로 갈린다. 즉 이 두 수는 「지우려 했던
   *   것」이 아니라 지운 것이다.
   */
  cleared: {
    /** 사용자가 정한 프로필 표시명 수. 0이면 완료 문구가 그 줄을 그리지 않는다. */
    named: number;
    /** 감지 제외 목록의 건수. 0이면 완료 문구가 그 줄을 그리지 않는다. */
    excluded: number;
  };
}

/**
 * 전체 초기화 = 개별 삭제의 반복 + registry 공장초기화(settings·gpu_map 포함). backups/는
 * 그대로 남는다.
 *
 * 방어가 2중이다: 1회용 토큰 + type-to-confirm. 판정은 둘 다 백엔드에 있고, confirm_text는 토큰
 *   튜플의 한 칸으로 비교된다 — 프론트의 OK 비활성은 UX 보조일 뿐이라 런타임에 안 먹어도
 *   백엔드가 막는다.
 * applyAll과 같은 불변식: 게임별 실패가 있어도 봉투는 ok:true다. 실패한 게임의 registry 항목은
 *   남는다(registry가 항상 디스크 실물과 일치한다).
 */
export const resetAll = rpc<[confirm_token?: string, confirm_text?: string], ResetAllResult>(
  "reset_all",
);

// ── 표시명 ───────────────────────────────────────────────────────────────────
/**
 * 프로필의 전역 표시명을 바꾼다. 화면 글자만 바뀐다 — 저장된 프로필·백업·경로는 그대로이고
 * 식별자 dock/internal은 이 호출로 절대 움직이지 않는다. 단 감사 로그에는 새 이름이 남는다
 * (main.set_profile_name이 name=%r로 기록한다) — 되돌리기 어려운 변경의 흔적을 남기는 것이 이
 * 프로젝트의 규칙이고, 그 값은 로그의 내용이지 경로·키가 아니다.
 *
 * 빈 값·공백만 보내면 기본 이름으로 되돌아간다(거부가 아니다 — 그것이 "이름 지우기"다).
 * 길이 상한을 넘으면 백엔드가 잘라서 저장하고 결과를 돌려준다. 화면은 돌려받은 값을 그대로
 * 그린다 — 프론트가 다시 다듬으면 사용자가 본 것과 저장된 것이 갈린다.
 */
export const setProfileName = rpc<
  [profile: Profile, name?: string],
  { profile_names: Record<Profile, string> }
>("set_profile_name");

// ── 백업 복원 ────────────────────────────────────────────────────────────────
//
// 되돌릴 곳은 행이 정한다. profile_* 백업은 그 프로필 슬롯으로, disk·unknown은 게임 설정 파일로
//   간다. 판정은 백엔드가 하고 화면은 target을 그린다 — 프론트가 kind로 목적지를 다시 분류하면
//   그 판정이 백엔드와 갈리는 날 확인한 곳과 다른 곳에 쓰기가 일어난다. 슬롯을 되돌린 뒤 게임에도
//   반영할지는 후속 제안이 묻는다.

/** 백업 종류. 파일명 파싱은 백엔드가 한다 — 프론트는 이 코드로 문구만 고른다. */
export type BackupKind = "disk" | "profile_dock" | "profile_internal" | "unknown";

/** 되돌릴 곳. kind에서 파생되지만 판정은 백엔드이고 프론트는 이 값만 읽는다. */
export type RestoreTarget = Profile | "config";

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
  /**
   * 이 행을 [복원]하면 어디가 바뀌는가. 판정은 백엔드 한 곳이다.
   * "dock"/"internal" = 그 프로필 슬롯 · "config" = 게임 설정 파일.
   */
  target: RestoreTarget;
  /**
   * 되돌릴 곳의 지금 내용이 이 백업과 같은가. 누르기 전에 말해 결과 팝업이 뜰 이유를 줄인다.
   * 모르면 false다(손상 슬롯 등) — 모르는 것을 "같다"고 말하지 않는다.
   */
  same_as_target: boolean;
}

/** 목록 조회 — 읽기 전용이다. 아무것도 쓰지 않는다. */
export const listBackups = rpc<[appid: string], { backups: BackupRow[] }>("list_backups");

/**
 * restore_backup이 돌려주는 값 — 성공(restored)과 무동작(already)을 outcome으로 가른다.
 *
 * already는 실패가 아니다. 되돌릴 곳이 이미 그 백업과 같으면 백엔드가 엔진을 부르기 전에
 *   돌려준다(쓰기 0 · 대피 0 · 링 소모 0). 그래야 같은 행을 두 번 눌러도 되돌릴 지점이 링 밖으로
 *   밀리지 않는다.
 */
export interface RestoreResult extends RestoreConfirmParams {
  outcome: "restored" | "already";
  /** 실제로 복원한 백업의 경로(엔진 반환값). `already`면 없다. */
  restored?: string;
}

/**
 * restore_backup이 CONFIRM_REQUIRED로 돌려주는 params. 아직 아무것도 안 바뀌었다.
 * (confirm_token은 확인 요구일 때만 실린다 — 성공 응답에는 없다.)
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
  /** 되돌릴 곳. 확인창 문구도 후속 제안도 이 값으로 갈린다. */
  target: RestoreTarget;
  /** 게임 설정 파일이 지금 어떤 상태인가 — 저장 확인창과 같은 4분류다. */
  disk_state: DiskState;
  /** `disk_state === "other_profile"`일 때 어느 프로필과 같은지. */
  matched_profile?: Profile;
  /**
   * 되돌릴 곳이 슬롯일 때 그 슬롯의 마지막 저장 시각 표시값. 모르면 빈 문자열이다. 기록이
   * 가리키는 본체가 실재할 때만 실린다 — 기록만 남고 실물이 없는 슬롯에서 이 값을 그리면 화면이
   * 없는 프로필을 「…에 저장됨」이라 말한다. 판정은 백엔드 한 곳이다.
   */
  saved_at?: string;
  /**
   * 이번 복원이 지금 그 자리의 내용을 백업으로 대피시키는가.
   *
   * 화면의 "복원 전에 지금의 내용도 백업으로 보관합니다 — 백업 한 칸을 씁니다"가 참인 조건이고,
   *   엔진의 대피 조건과 같은 술어에서 나온다(restore._evacuation_source). 자리마다 조건을 다시
   *   세우면 언젠가 화면이 쓰지도 않는 링을 약속한다.
   * 값이 뜻을 갖는 것은 확인을 묻는 갈래다. already 응답에도 같은 params가 실려 오지만 그 갈래는
   *   아무것도 쓰지 않으므로 이 값을 근거로 삼지 말 것.
   */
  evacuates: boolean;
  /** 이번 복원이 실제로 지울 백업들(적용과 같은 필드·같은 문구). */
  evicted: EvictedRow[];
  /**
   * 되돌릴 슬롯의 저장 기록이 손상돼 지금 내용을 대피시킬 수 없는 상태인가. 참이면 확인창이
   * "되살릴 수 없다"를 명시하고 묻는다 — 조용히 잃지 않는다.
   */
  slot_unreadable?: boolean;
}

/**
 * 백업 하나를 그 행의 되돌릴 곳으로 되돌린다.
 *
 * 묻는 경우와 안 묻는 경우가 갈린다(백엔드 3-상태 판정, 기준은 되돌릴 곳이다):
 *   · 되돌릴 곳의 내용이 다르다 → CONFIRM_REQUIRED + 토큰(저장·삭제와 같은 계약)
 *   · 되돌릴 곳이 비어 있다(설정 파일 없음·빈 슬롯) → 잃을 것이 없어 묻지 않고 재생한다
 *   · 이미 그 백업과 같다 → outcome:"already", 아무것도 하지 않는다
 * 실행 중 거부는 게임 설정 파일로 되돌릴 때만이다 — 프로필 슬롯은 게임이 읽지도 쓰지도 않으므로
 *   게임을 켜 둔 채로도 되돌릴 수 있다.
 * 토큰은 목적지와 백업 파일에 묶여 있다 — 다른 행·다른 슬롯에 재사용할 수 없다.
 */
export const restoreBackup = rpc<
  [appid: string, backup_id: string, confirm_token?: string],
  RestoreResult
>("restore_backup");
