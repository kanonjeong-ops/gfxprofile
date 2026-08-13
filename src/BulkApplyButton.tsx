import { ButtonItem, PanelSectionRow } from "./deckyui";
import { IconBolt, IconChip } from "./icons";
import { t } from "./i18n";
import { ICON_SLOT_STYLE } from "./popup";
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
  hint,
  busy,
  onApply,
}: {
  profile: Profile;
  /** 그 프로필을 **실제로 가진** 게임 수. 등록 수가 아니다 — 등록 수를 쓰면 라벨이 거짓말을 한다. */
  ready: number;
  /**
   * 비활성일 때의 **사유 한 줄**(§3-A ⓑ · M1) — `description` 슬롯에 그린다.
   *
   * ★★ 호출부(`index.tsx`의 `bulkHint`)가 **`ready`·`total`만으로** 만든다. `running`은 그 식에
   *   들어가지 않는다 — 실행 중인 게임은 일괄 적용을 막지 않으므로(E1) 못 누르는 사유가 될 수
   *   없고, 사유 문구가 running을 읽기 시작하면 그 값이 활성 조건으로 새는 길이 생긴다.
   *   이 컴포넌트가 `running`을 **못 보는 구조**(위 참조)를 hint가 우회해서는 안 된다.
   */
  hint?: string;
  busy: boolean;
  onApply: (profile: Profile) => void;
}) {
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        description={hint}
        disabled={ready === 0 || busy}
        onClick={() => onApply(profile)}
      >
        {/* ★ 아이콘은 **children 안**이다(§3-A 10판 정오 — D2): `icon` prop은 Field의 라벨 슬롯이라
            버튼 위에 고아로 뜨고 그 슬롯이 아이콘을 16×20으로 구긴다(D6). 관용구·상수는
            프로젝트에 하나(`ICON_SLOT_STYLE`, popup.tsx).
            ⚠️ props 집합은 이 변경으로 **줄지도 늘지도 않았다**(E1 무접촉 — `running`은 여전히 없다). */}
        <span style={ICON_SLOT_STYLE}>{profile === "dock" ? <IconBolt /> : <IconChip />}</span>
        {/* ★ 라벨은 **표시명 하나**에서 나온다(F11) — 프로필 이름이 문장에 박혀 있으면
            사용자가 이름을 바꿨을 때 이 버튼만 옛 이름을 말한다. 이름의 정본은 i18n의
            `PROFILE_*` 한 곳이고, 사용자가 정한 이름은 거기서 덮어써진다. */}
        {t("BULK_APPLY", { profile: t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") })}{" "}
        {ready > 0 ? t("BULK_COUNT", { n: ready }) : t("BULK_NONE")}
      </ButtonItem>
    </PanelSectionRow>
  );
}
