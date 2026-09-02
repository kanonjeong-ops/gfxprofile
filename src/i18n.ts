// 번역 대상 사용자 가시 문자열은 여기서 조회한다. 플러그인 고유명사와 ErrorBoundary의 비상
// 폴백은 예외다. 리터럴을 소스에 흩어 두고 나중에 모으는 방식은 이 프로젝트에서 이미 실패했다 —
// 놓친 자리는 코드 grep에 안 걸려 조용히 쌓인다. 그래서 문자열은 태어나는 시점부터 키로 만든다.
//
// 언어 판정은 백엔드가 한다. 프론트는 `ui_hello`가 돌려준 코드만 받는다 — 프론트가 LANG이나
// navigator를 보면 판정이 두 곳으로 갈린다. 이 기기가 그 반례다(Steam UI=한국어,
// LANG=en_US.UTF-8).

import en from "./i18n/en.json";
import ko from "./i18n/ko.json";
import { uiHello } from "./rpc";

export type StringKey = keyof typeof en;

const TABLES: Record<string, Partial<Record<StringKey, string>>> = { en, ko };

// 기본값은 영어다. 한국어가 영어 사용자에게 새는 것은 결함이지만, 그 반대(한국어 사용자가 판정
// 전 한순간 영어를 보는 것)는 아니다. QAM 본문은 언어 요청이 정착된 뒤 그리며,
// 판정 실패·타임아웃이면 영어로 연다.
let current = "en";

export function setLang(lang: string): void {
  current = lang in TABLES ? lang : "en";
  resolved = true;
  waiters.splice(0).forEach((f) => f());
}

// 언어 확정이 한 화면 컴포넌트 안에서만 일어나면, 그 화면을 거치지 않고 다른 화면이 먼저
//   마운트될 때 `current`가 기본값 "en" 그대로다 — 한국어 사용자에게 영어 화면이 뜬다. 그래서
//   "언어를 확정한다"를 화면과 무관한 모듈 수준의 일로 옮긴다. 지금 호출 지점은 QAM 하나지만,
//   확정이 화면에 매여 있지 않다는 것이 이 구조의 값어치다.
const LANG_TIMEOUT_MS = 3000;   // 이 안에 안 오면 기본 언어로 그린다
let resolved = false;
let waiters: Array<() => void> = [];
let inflight: Promise<{ code?: string }> | null = null;

/** 언어가 확정될 때까지 기다린다. 이미 확정됐으면 즉시 끝난다.
 *  중복 방지(`inflight`)는 이 모듈 인스턴스 안에서만 성립한다 — 인스턴스를 공유하지 않는 화면이
 *  둘이면 `ui_hello`가 각각 한 번씩 나간다. 호출 지점이 QAM 하나인 지금은 1회이고, 그보다 더
 *  줄이는 것은 Decky 런타임의 몫이다. */
/**
 * @param missing 첫 호출자만 백엔드로 보낸다(진단용 uicheck 목록) — 이미 확정된 뒤의 호출은
 *                즉시 `cached`로 끝나 목록을 보내지 않는다.
 * @returns 실패 사유(`code`) · `cached` · 빈 객체 중 하나. 언어 확정 여부와 무관하게 반드시 정착한다.
 */
export function ensureLang(
  version: string,
  fn: string,
  missing: string[] = [],
): Promise<{ code?: string; cached?: true }> {
  if (resolved) return Promise.resolve({ cached: true as const });
  if (!inflight) {
    // 어느 갈래든 정착하지 않으면 `langReady`가 false로 남아 화면이 영구히 빈다. 그래서 세
    //   갈래를 닫는다: 언어 없는 응답은 `NO_LANG`으로 정착하고, RPC 거부·성공 핸들러 예외는
    //   `catch`가, 무응답은 타임아웃이 정착시킨다.
    const call = uiHello(version, fn, missing)
      .then((res) => {
        if (res.ok && res.data && typeof res.data.lang === "string") {
          setLang(res.data.lang);
          return {};
        }
        resolveAnyway();
        return { code: res.ok ? "NO_LANG" : res.code };
      })
      .catch((err: unknown) => {              // 성공 핸들러 내부 예외까지 덮는다
        resolveAnyway();
        return { code: `THREW:${String(err)}` };
      });
    const timeout = new Promise<{ code?: string }>((done) => {
      setTimeout(() => {
        resolveAnyway();                       // 행이면 기본 언어(영어)로 그린다 — 빈 화면보다 낫다
        done({ code: "TIMEOUT" });
      }, LANG_TIMEOUT_MS);
    });
    inflight = Promise.race([call, timeout]);
  }
  return inflight;
}

// 실패해도 기다림은 끝낸다 — 판정이 안 되면 영어(기본값)로 그리는 것이 빈 화면보다 낫다.
function resolveAnyway(): void {
  resolved = true;
  waiters.splice(0).forEach((f) => f());
}

/**
 * 프로필 표시명 덮어쓰기 — 사용자가 정한 이름이 `PROFILE_DOCK`/`PROFILE_INTERNAL`을 대신한다.
 *
 * 왜 i18n 층인가: 화면에서 프로필 이름이 나오는 자리는 이미 전부 그 두 키를 지난다(버튼 라벨·
 *   확인창·요약·백업 종류 …). 여기서 한 번 갈아 끼우면 모든 자리가 따라온다 — 컴포넌트마다
 *   이름을 프롭으로 나르면 언젠가 한 곳이 빠지고, 빠진 곳만 옛 이름을 말한다.
 * 식별자는 이 함수가 건드리지 않는다. 바뀌는 것은 `t()`가 돌려주는 글자뿐이고 `dock`/`internal`은
 *   경로·RPC 인자·registry 키로 그대로 남는다.
 * 빈 값·공백만이면 기본 이름으로 되돌린다. 백엔드에서 정규화된 봉투가 오지만, 여기서도 빈
 *   라벨만은 막는다.
 */
const PROFILE_NAME_KEYS = { dock: "PROFILE_DOCK", internal: "PROFILE_INTERNAL" } as const;
const overrides: Partial<Record<StringKey, string>> = {};

export function setProfileNames(names?: { dock?: string; internal?: string } | null): void {
  for (const slot of ["dock", "internal"] as const) {
    const key = PROFILE_NAME_KEYS[slot];
    const value = (names?.[slot] ?? "").trim();
    if (value) overrides[key] = value;
    else delete overrides[key];
  }
}

/**
 * 배지("기본 이름"/"직접 정한 이름")가 라벨과 같은 저장소를 읽게 하는 조회.
 * overview 재조회든 이름 변경 응답이든 `setProfileNames`가 이미 이 저장소에 합류시켰다 —
 * 낡은 overview 봉투를 따로 읽으면 라벨과 배지가 서로를 부정한다.
 */
export function hasProfileNameOverride(slot: "dock" | "internal"): boolean {
  return PROFILE_NAME_KEYS[slot] in overrides;
}

/**
 * 덮어쓰기를 무시한 기본 문구. 표시명 편집창이 "비우면 무엇으로 돌아가는지"를 말할 때만 쓴다 —
 * `t()`는 사용자가 정한 이름을 돌려주므로 그것으로는 기본 이름을 보여줄 수 없다.
 */
export function tDefault(key: StringKey): string {
  return TABLES[current]?.[key] ?? en[key] ?? key;
}

/**
 * `{name}` 자리를 params로 채운다.
 *
 * 조회 순서는 덮어쓰기 → 현재 언어 → 영어 → 키 문자열이다. 현재 언어에 키가 없으면 영어로
 * 내려가고, 키 문자열이 그대로 나오는 것은 영어에도 없을 때뿐이다 — `StringKey`가 영어 표의
 * 키로 좁혀져 있어 타입이 그 상황을 먼저 막는다. 지금 남은 검사(`qa/test_i18n_keys.py`)가 재는
 * 것은 ko·en 키 집합 항등과 빈 값 부재뿐이다.
 */
export function t(key: StringKey, params?: Record<string, string | number>): string {
  const raw = overrides[key] ?? TABLES[current]?.[key] ?? en[key] ?? key;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/**
 * 백엔드 에러 코드를 사람이 읽는 문장으로 — 코드→문구의 단일 관문이다.
 *
 * 왜 헬퍼인가: `res.code`는 `string`이고 `t()`는 `StringKey`를 받는다. 호출부마다 `as StringKey`를
 *   뿌리면 미등재 코드가 조용히 새어 키 문자열이 그대로 화면에 뜬다. 문을 하나로 모아 두면
 *   미등재 코드는 항상 fallback으로 흐른다 — 예외처리 대신 구조다.
 *
 * @param code     백엔드가 준 코드 문자열(`codes.py`가 정본).
 * @param fallback 등재되지 않은 코드일 때 쓸 키. `{code}` 자리에 원문 코드를 실어 보인다 —
 *                 사라지는 것보다 낫고, 무엇이 빠졌는지도 드러난다.
 *
 * `codes.py`의 코드가 i18n에 다 있는지 대조하는 검사는 저장소에 없다. `qa/test_i18n_keys.py`는
 *   ko·en 키 집합 항등과 빈 값만 보고, `qa/test_codes.py`는 쓰인 코드가 `codes.py`에 있는지만
 *   한 방향으로 본다. 그러니 "백엔드 코드는 fallback을 타지 않는다"는 보증이 아니다 — 새 코드를
 *   `codes.py`에 넣고 i18n에 안 넣으면 이 관문이 원문 코드를 화면에 흘린다. 화면이 비지는 않지만
 *   문구를 등재하는 것은 사람의 몫이고, 코드를 더하는 커밋이 i18n 두 파일을 같이 건드려야 한다.
 */
export function tCode(code: string, fallback: StringKey): string {
  return code in en ? t(code as StringKey) : t(fallback, { code });
}
