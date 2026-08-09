import { ButtonItem, PanelSectionRow } from "./deckyui";
import { t } from "./i18n";
import type { Profile } from "./rpc";

/**
 * 일괄 적용 버튼 하나. **주 동작이다** — 모드를 바꿔 부팅했을 때 누르는 그 버튼.
 *
 * ★ 이 컴포넌트가 따로 있는 이유는 재사용이 아니라 **`running`을 못 보게 하려는 것**이다
 *   (설계 §9-F A-4, 2026-08-06).
 *
 *   지켜야 할 불변식(E1): **실행 중인 게임이 있어도 일괄 적용은 막히지 않는다.**
 *   막으면 게임 하나가 켜져 있다는 이유로 아무것도 적용되지 않고, 그건 M1의 약속
 *   ("하나만 거부하고 나머지는 적용")을 정면으로 뒤집는다.
 *
 *   그 불변식을 **텍스트 검사로** 지키려다 네 라운드 연속 뚫렸다 —
 *   파생 변수 → `ready` 값 오염 → `.ts` helper → 예외 마커 스푸핑 → onClick 무력화.
 *   전부 *"버튼을 그리는 코드가 `running`에 손이 닿는다"*는 같은 뿌리에서 나왔다.
 *
 *   **그래서 손이 닿지 않게 했다.** 이 파일의 props에는 `running`이 없고, 넣으려면
 *   타입을 고쳐야 한다 — 한 줄로 숨길 수 없고 리뷰에 반드시 걸린다.
 *   검사로 막던 것을 **구조로 없앤 것**이고, 그것이 이 프로젝트의 원칙이다.
 */
export function BulkApplyButton({
  profile,
  ready,
  busy,
  onApply,
}: {
  profile: Profile;
  /** 그 프로필을 **실제로 가진** 게임 수. 등록 수가 아니다 — 등록 수를 쓰면 라벨이 거짓말을 한다. */
  ready: number;
  busy: boolean;
  onApply: (profile: Profile) => void;
}) {
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        disabled={ready === 0 || busy}
        onClick={() => onApply(profile)}
      >
        {t(profile === "dock" ? "BULK_DOCK" : "BULK_INTERNAL")}{" "}
        {ready > 0 ? t("BULK_COUNT", { n: ready }) : t("BULK_NONE")}
      </ButtonItem>
    </PanelSectionRow>
  );
}
