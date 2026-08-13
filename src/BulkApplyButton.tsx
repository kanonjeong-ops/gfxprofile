import { ButtonItem, PanelSectionRow } from "./deckyui";
import { IconBolt, IconChip } from "./icons";
import { t } from "./i18n";
import { ICON_SLOT_STYLE, KEEP_ALL_STYLE } from "./popup";
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
  /**
   * 그 프로필을 **실제로 가진** 게임 수. 등록 수가 아니다 — 등록 수를 쓰면 라벨이 거짓말을 한다.
   *
   * ★ **`undefined` = 아직 모른다**(counts 미도착 — 조회 전·조회 실패, 12판 C-1). 그때는
   *   괄호를 그리지 않고 버튼도 누를 수 없다: 모르는 채로 `(0개)`라 말하면 D01 위반이고,
   *   모르는 채로 활성이면 *"방금 읽던 것과 다른 현황"* 위에서 쓰기가 시작된다 — 그쪽이 더 나쁘다.
   * ⚠️ 이 옵셔널은 **counts 미도착을 표현하는 것일 뿐 `running`과 아무 관계가 없다.**
   *   이 파일의 구조적 방어(props에 `running`이 없어 타입을 고쳐야만 넣을 수 있다)는 그대로다.
   */
  ready?: number;
  /**
   * **사유 한 줄**(§3-A ⓑ · M1) — `description` 슬롯에 그린다.
   *
   * ★ 12판 규칙 — **「숫자가 말하지 못하는 것만 말한다」**: 등록이 0일 때만 선다.
   *   `ready === 0`은 위 라벨의 `(0개)`가 이미 같은 말을 하므로 사유 줄이 아니다.
   * ★★ 호출부(`index.tsx`의 `bulkHint`)가 **`total`만으로** 만든다(11판의 `ready`·`total`
   *   2항에서 축소 — `ready`는 이제 라벨이 전담한다). `running`은 그 식에 들어가지 않는다 —
   *   실행 중인 게임은 일괄 적용을 막지 않으므로(E1) 못 누르는 사유가 될 수 없고, 사유 문구가
   *   running을 읽기 시작하면 그 값이 활성 조건으로 새는 길이 생긴다. 재료가 줄었으므로
   *   그 보증은 오히려 강해졌다. 이 컴포넌트가 `running`을 **못 보는 구조**(위 참조)를
   *   hint가 우회해서는 안 된다.
   */
  hint?: string;
  busy: boolean;
  onApply: (profile: Profile) => void;
}) {
  return (
    <PanelSectionRow>
      {/* ★ 사유 줄은 **span으로 감싸 넘긴다** — `description`은 style을 받지 않는 prop이라
          한국어 낱말 보존(`KEEP_ALL_STYLE`)을 거는 통로가 이것뿐이다.
          ⚠️ **없는 줄은 여전히 없다**: `hint`가 없으면 감싸지도 않는다(빈 span을 넘기면
            "말할 게 없으면 그리지 않는다"가 깨지고, 관측면에서도 빈 사유가 있는 것이 된다).
          ⚠️ props 집합은 이 변경으로 **줄지도 늘지도 않았다**(E1 무접촉 — `running`은 여전히 없다). */}
      {/* ★ 활성 조건의 `?? 0`은 **모르면 잠근다**는 뜻이다(12판 C-1): counts 미도착에서
          `ready === 0`만 보면 `undefined`가 활성이 되어 *"모르는 채 눌리는 버튼"*이 된다 —
          그 상태로 누르면 백엔드는 방금 읽던 것과 다른 현황 위에서 쓰기를 시작하므로, 라벨의
          거짓 표시(`(0개)`)보다 나쁘다.
          ⚠️ E1과 무관하다 — 활성 재료는 여전히 `ready`·`busy` 둘뿐이고 `running`은 없다
            (build.sh 게이트 ③의 허용 목록도 그 둘 그대로다). */}
      <ButtonItem
        layout="below"
        description={hint ? <span style={KEEP_ALL_STYLE}>{hint}</span> : undefined}
        disabled={(ready ?? 0) === 0 || busy}
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
        {/* ★ 괄호는 **`ready`가 0이어도 `BULK_COUNT`다**(§2-B 12판). 0에서만 다른 키로 갈라
            그리면 같은 자리·같은 종류의 수가 한쪽만 숫자라 `(3개)`↔`(0개)` 비교가 깨진다.
            "0을 그리지 않는다" 관례와 무저촉 — 그 관례의 대상은 **사건 서술**이고 버튼 괄호는
            **상태 수치**다(§7 관례 정본). 갈라 그리던 `BULK_NONE`은 설계에 등재된 적 없는
            M1 승계 키였고 12판이 제거를 위해 처음 등재했다.
            ★★ 단 그 "0"은 **counts가 도착한 뒤의 0**이다(12판 C-1): 아직 모르는 동안에는
              괄호를 **아예 그리지 않는다** — 모르는 것을 0으로 말하는 것이 D01 위반이고,
              같은 화면의 카운트 줄·설명 줄·사유 줄은 이미 그렇게 침묵하고 있다. 즉 괄호의
              규칙은 두 층이다: **도착 여부**가 괄호의 유무를, **수**가 괄호의 내용을 정한다. */}
        {ready === undefined ? null : t("BULK_COUNT", { n: ready })}
      </ButtonItem>
    </PanelSectionRow>
  );
}
