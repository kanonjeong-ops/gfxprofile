// ★ 사용자 가시 문자열은 **전부 여기를 거친다** (설계 E18).
//
// 소스에 리터럴을 두고 P5에서 훑어 옮기는 방식은 이 프로젝트에서 이미 실패했다 —
// M1에서 기능을 뺀 뒤 그것을 설명하는 문장 5곳이 옛날 그대로 남았고, 코드 grep만으로는
// 안 잡혀 문서까지 훑어야 했다. **한 번 놓치면 계속 쌓인다.**
// 그래서 문자열이 태어나는 시점부터 키로 만든다. P5는 "옮기는 일"이 아니라
// "언어 전환이 실제로 되는지 확인하는 일"만 남는다.
//
// 언어 **판정은 백엔드가 한다**(설계 E3). 프론트는 `ui_hello`가 돌려준 코드만 받는다 —
// 프론트가 LANG이나 navigator를 보는 순간 판정이 두 곳으로 갈리고, 이 기기가 바로
// 그 반례다(Steam UI=한국어, LANG=en_US.UTF-8).

import en from "./i18n/en.json";
import ko from "./i18n/ko.json";
import { uiHello } from "./rpc";

export type StringKey = keyof typeof en;

const TABLES: Record<string, Partial<Record<StringKey, string>>> = { en, ko };

// 기본값은 **영어**다. 축 1(배포 적합성)에서 한국어가 영어 사용자에게 새는 것은 결함이지만,
// 그 반대(한국어 사용자가 판정 전 한순간 영어를 보는 것)는 아니다.
// 게다가 화면은 lang이 확정된 뒤에 그려지므로(index.tsx) 이 기본값이 보일 일 자체가 드물다.
let current = "en";

export function setLang(lang: string): void {
  current = lang in TABLES ? lang : "en";
  resolved = true;
  waiters.splice(0).forEach((f) => f());
}

// ★ 2026-08-06 실기에서 드러난 것: 언어 확정이 **QAM 패널 컴포넌트 안에서만** 일어나고 있었다.
//   `addRoute`로 등록된 전체 화면은 독립적으로 마운트되므로, 패널을 한 번도 안 열고 전체 화면부터
//   열면 `current`가 기본값 "en" 그대로다 — 한국어 사용자에게 **영어 화면이 뜬다**(실기로 확인).
//   그래서 "언어를 확정한다"를 **화면과 무관한 모듈 수준의 일**로 옮긴다.
const LANG_TIMEOUT_MS = 3000;   // 이 안에 안 오면 기본 언어로 그린다
let resolved = false;
let waiters: Array<() => void> = [];
let inflight: Promise<{ code?: string }> | null = null;

export function isLangResolved(): boolean {
  return resolved;
}

/** 언어가 확정될 때까지 기다린다. 이미 확정됐으면 즉시 끝난다.
 *  ⚠️ **중복 방지는 모듈 인스턴스 안에서만 성립한다** — QA R3 실측: 실기의 QAM 패널과 라우트는
 *  인스턴스를 공유하지 않아 각각 1회씩(총 2회) `ui_hello`가 나간다(같은 백엔드 세션 토큰·7~8초 간격으로
 *  재로드가 아님이 확인됨). 패널 재오픈마다 나던 3번째 호출은 사라졌다. 더 줄이는 것은 Decky 런타임 문제다. */
/**
 * @param missing 첫 호출자만 백엔드로 보낸다(진단용 uicheck 목록).
 * @returns 실패 사유(`code`) 또는 빈 객체. **언어 확정 여부와 무관하게 반드시 정착한다.**
 */
export function ensureLang(
  version: string,
  fn: string,
  missing: string[] = [],
): Promise<{ code?: string; cached?: true }> {
  if (resolved) return Promise.resolve({ cached: true as const });
  if (!inflight) {
    // ★ 2026-08-06 QA R2 지적 ⑬: 예전 판은 **거부만** 덮었다. 실제로는 세 가지가 더 있었다 —
    //   ① RPC가 영영 안 돌아오는 경우(행) ② `{ok:true}`인데 `data`가 없어 성공 핸들러가 던지는 경우
    //   ③ 그래서 promise가 REJECT로 끝나는 경우. 셋 다 `langReady`가 영원히 false로 남아
    //   **화면이 영구히 빈다.** "반드시 끝난다"고 주석에 적었을 뿐 코드가 그렇지 않았다.
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

// 실패해도 **기다림은 끝낸다** — 판정이 안 되면 영어(기본값)로 그리는 것이 빈 화면보다 낫다.
function resolveAnyway(): void {
  resolved = true;
  waiters.splice(0).forEach((f) => f());
}

/**
 * 프로필 **표시명 덮어쓰기** (F11 ①) — 사용자가 정한 이름이 `PROFILE_DOCK`/`PROFILE_INTERNAL`을
 * 대신한다.
 *
 * ★★ **왜 i18n 층인가**: 화면에서 프로필 이름이 나오는 자리는 이미 전부 그 두 키를 지난다
 *   (버튼 라벨·확인창·요약·백업 종류 …). 여기서 한 번 갈아 끼우면 **모든 자리가 자동으로**
 *   따라온다 — 컴포넌트마다 이름을 프롭으로 나르면 언젠가 한 곳이 빠지고, 빠진 곳만
 *   옛 이름을 말한다. *"두 곳에서 판정하면 언젠가 어긋난다"*의 표시 계층 판이다.
 * ★ **식별자는 이 함수가 절대 건드리지 않는다.** 바뀌는 것은 `t()`가 돌려주는 글자뿐이고
 *   `dock`/`internal`은 경로·RPC 인자·registry 키로 그대로 남는다.
 * ★ 빈 값·공백만은 **기본 이름으로 되돌린다**(백엔드도 같은 규칙으로 정규화한다 —
 *   여기 방어는 봉투가 손상됐을 때 빈 라벨이 화면에 남지 않게 하는 마지막 그물이다).
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
 * **덮어쓰기를 무시한** 기본 문구. 표시명 편집창이 *"비우면 무엇으로 돌아가는지"*를 말할 때만
 * 쓴다 — `t()`는 사용자가 정한 이름을 돌려주므로 그것으로는 기본 이름을 보여줄 수 없다.
 */
export function tDefault(key: StringKey): string {
  return TABLES[current]?.[key] ?? en[key] ?? key;
}

/**
 * `{name}` 자리를 params로 채운다.
 *
 * 키가 없으면 **키 문자열 자체**를 돌려준다 — 빈 화면보다 낫고, 무엇이 빠졌는지도 보인다.
 * (P5의 집합 항등 테스트가 이 상황 자체를 없애는 것이 본래 방어선이다.)
 */
export function t(key: StringKey, params?: Record<string, string | number>): string {
  const raw = overrides[key] ?? TABLES[current]?.[key] ?? en[key] ?? key;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/**
 * 백엔드 **에러 코드**를 사람이 읽는 문장으로 — 코드→문구의 **단일 관문**이다.
 *
 * ★ 왜 헬퍼인가(설계 E18 / P5):
 *   `res.code`는 `string`이고 `t()`는 `StringKey`를 받는다. 호출부마다 `as StringKey`를
 *   뿌리면 **미등재 코드가 조용히 새어** 키 문자열(= `"GAME_RUNNING"`)이 그대로 화면에 뜬다.
 *   실제로 P4까지 `t("APPLY_FAILED", { code })`가 원시 식별자를 그대로 보이고 있었다 —
 *   영어 화면에서는 티가 안 나지만 한국어 화면에서는 명백한 미번역 잔재다.
 *   문을 하나로 모아 두면 미등재 코드는 **항상** fallback으로 흐른다(예외처리 대신 구조).
 *
 * @param code     백엔드가 준 코드 문자열(`codes.py`가 정본).
 * @param fallback 등재되지 않은 코드일 때 쓸 키. `{code}` 자리에 원문 코드를 실어 보인다 —
 *                 사라지는 것보다 낫고, 무엇이 빠졌는지도 드러난다.
 *
 * ⚠️ `qa/test_i18n_sets.py` 5항이 `codes.py ⊆ i18n`을 강제하므로 **백엔드 코드는 fallback을
 *   타지 않는다.** fallback이 실제로 쓰이는 것은 프론트가 스스로 만든 코드(`TIMEOUT` 등)뿐이다.
 */
export function tCode(code: string, fallback: StringKey): string {
  return code in en ? t(code as StringKey) : t(fallback, { code });
}
