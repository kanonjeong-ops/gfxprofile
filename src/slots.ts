import { t } from "./i18n";
import type { OverviewGame, Profile } from "./rpc";

/**
 * 게임 한 줄의 **슬롯 상태 한 조각** — 「현황」과 「관리」가 같은 문장을 쓴다.
 *
 * ★ 왜 공용 함수인가: 두 탭이 각자 문장을 조립하고 있었고, F5(마지막 저장일자)를 한쪽에만
 *   넣으면 같은 게임이 화면마다 다른 것을 말하게 된다. 문장을 만드는 자리를 하나로 둔다.
 *
 * ★★ **「마지막 저장」이지 「마지막 적용」이 아니다.** 복원(`restore_backup`)은 `last_applied`를
 *   갱신하지 않으므로(M1 fence 동작 — DESIGN-F6-F8 §6), 화면에 "마지막 적용"을 그리면
 *   복원 직후에 **낡은 값이 사실인 척** 보인다. 그래서 라벨에 「저장」을 박아 두 개념을 가른다 —
 *   *없는 사실을 만들어 말하지 않는다.*
 *
 * ★ 프로필 이름은 `t("PROFILE_*")`를 지난다 — 사용자가 표시명을 바꾸면(F11 ①) 여기도 자동으로
 *   따라온다(이름의 정본은 i18n 한 곳이다).
 */
function slotText(game: OverviewGame, profile: Profile): string {
  const name = t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL");
  const ready = profile === "dock" ? game.has_dock : game.has_internal;
  if (!ready) return t("SLOT_EMPTY", { profile: name });
  // 시각 문자열은 **백엔드가 만든 표시값**이다(프론트는 날짜를 파싱하지 않는다).
  // 없으면(옛 프로필·조회 실패) 날짜 없는 문장으로 떨어진다 — 모르는 것을 지어내지 않는다.
  const date = game.saved_at?.[profile];
  return date
    ? t("SLOT_SAVED_AT", { profile: name, date })
    : t("SLOT_SAVED", { profile: name });
}

/**
 * 한 게임의 **두 슬롯 상태를 한 줄로**. 화면은 이 문자열 하나만 그린다.
 *
 * ★ 왜 조각이 아니라 완성된 줄인가: 구분자와 순서까지 여기 한 곳에 두면 두 탭이 **글자
 *   하나까지 같은 것**을 말한다. 그리고 화면 쪽 JSX에 `"dock"` 같은 리터럴이 남지 않아
 *   가시 문자열 검사(E18 4항 AST)가 오탐 없이 도는 부수 이득도 있다 —
 *   검사를 느슨하게 하는 대신 **검사에 걸릴 이유 자체를 없앤다.**
 */
export function slotSummary(game: OverviewGame): string {
  return `${slotText(game, "dock")} · ${slotText(game, "internal")}`;
}
