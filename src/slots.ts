import { t } from "./i18n";
import type { OverviewGame, Profile } from "./rpc";

/**
 * 게임 한 줄의 슬롯 상태 한 조각 — 목록 뷰와 상세 뷰가 같은 문장을 쓴다.
 *
 * 왜 공용 함수인가: 문장을 두 자리에서 조립하면 저장 시각 같은 항목을 한쪽에만 넣는 날
 *   같은 게임이 화면마다 다른 것을 말한다. 문장을 만드는 자리를 하나로 둔다.
 *
 * 「마지막 저장」이지 「마지막 적용」이 아니다. `engine.restore_backup`은 `last_applied`를
 *   건드리지 않으므로, 화면에 "마지막 적용"을 그리면 복원 직후에 낡은 값이 사실인 척 보인다.
 *   라벨에 「저장」을 박아 두 개념을 가른다.
 *
 * 프로필 이름은 `t("PROFILE_*")`를 지난다 — 사용자가 표시명을 바꾸면 여기도 따라온다.
 */
function slotText(game: OverviewGame, profile: Profile): string {
  const name = t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL");
  const ready = profile === "dock" ? game.has_dock : game.has_internal;
  if (!ready) return t("SLOT_EMPTY", { profile: name });
  // 시각 문자열은 백엔드가 만든 표시값이다 — 프론트는 날짜를 파싱하지 않는다.
  // 비어 있으면 날짜 없는 문장으로 떨어진다 — 모르는 것을 지어내지 않는다.
  const date = game.saved_at?.[profile];
  return date
    ? t("SLOT_SAVED_AT", { profile: name, date })
    : t("SLOT_SAVED", { profile: name });
}

/**
 * 한 게임의 두 슬롯 상태를 한 줄로. 화면은 이 문자열 하나만 그린다.
 *
 * 왜 조각이 아니라 완성된 줄인가: 구분자와 순서까지 여기 한 곳에 두면 두 뷰가 글자 하나까지
 *   같은 것을 말한다.
 */
export function slotSummary(game: OverviewGame): string {
  return `${slotText(game, "dock")} · ${slotText(game, "internal")}`;
}
