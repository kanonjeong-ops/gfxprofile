import { diskStateText } from "./confirmSpecs";
import { ConfirmModal } from "./deckyui";
import { t } from "./i18n";
import { BACKUP_WARN_APPLIES } from "./limits";
import type { ConfirmParams, Profile } from "./rpc";

/**
 * **저장(덮어쓰기) 확인창 — 정의는 이 파일 하나뿐이다.**
 *
 * ★ 왜 뺐는가(P9): 「관리」 탭의 복원 후속 제안이 **같은 저장 흐름**을 탄다(설계 F6-F8 §2-D:
 *   복원은 디스크만 되돌리고, 슬롯 반영은 기존 저장 흐름 그대로다). 같은 확인창을 두 화면에
 *   각자 그리면 문구·경고·`bDestructiveWarning`이 언젠가 갈라지고, **갈라진 쪽이 사용자에게
 *   덜 말하는 확인창**이 된다. 판정(토큰)은 이미 백엔드 한 곳인데 화면만 둘일 이유가 없다.
 *
 * ★ 여기는 **표시 전용**이다. "물어야 하는가"는 백엔드가 정하고(`CONFIRM_REQUIRED`),
 *   이 컴포넌트는 받은 `params`를 그릴 뿐이다 — 프론트가 조건을 다시 계산하지 않는다.
 */

/**
 * ⚠️ `diskStateText`는 **`confirmSpecs.tsx`로 옮겼다**(P12 §12 이식 맵). 저장·복원 확인창이
 *   같은 관문을 쓰는 규칙은 그대로이고, 사는 자리만 spec 파일로 갔다 — 이 컴포넌트는
 *   P15에서 spec으로 대체되어 사라진다.
 */

export function SaveConfirmModal({
  params,
  profile,
  onConfirm,
  closeModal,
}: {
  params: ConfirmParams;
  profile: Profile;
  onConfirm: () => void;
  /** `showModal`이 최상위 엘리먼트에 주입한다. 우리가 감싼 컴포넌트가 받으므로 그대로 넘긴다. */
  closeModal?: () => void;
}) {
  const label = t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL");
  return (
    <ConfirmModal
      strTitle={t("SAVE_CONFIRM_TITLE", { profile: label })}
      /*
       * ★ 2026-08-07 실기: `"\n\n"`로 이어 붙였더니 **한 문단으로 뭉쳐 렌더**됐다
       *   (`4a1892bae1 덮어쓸 내용:`이 붙어 읽혔다). `strDescription`은 `ReactNode`라
       *   문자열이 아니라 **엘리먼트로** 줘야 줄이 갈린다.
       */
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>{t("SAVE_CONFIRM_BODY")}</div>
          <div>{t("SAVE_CONFIRM_CURRENT", { size: params.size, sha1: params.sha1_short })}</div>
          <div>{t("SAVE_CONFIRM_INCOMING", { state: diskStateText(params) })}</div>
          {/* ★ 실측으로 확정된 한계를 여기서 말한다(P4-1): 덮어쓴 프로필의 대피본은
              `disk` 백업과 **한 링(10칸)을 공유**해서, 그 게임을 10번 적용하면 사라진다.
              "되돌릴 수 있다"고만 적으면 조건부 참이고, 조건을 안 적으면 오정보다. */}
          <div style={{ color: "#ffb454" }}>
            {t("SAVE_CONFIRM_BACKUP_LIMIT", { n: BACKUP_WARN_APPLIES })}
          </div>
        </div>
      }
      strOKButtonText={t("SAVE_CONFIRM_OK")}
      strCancelButtonText={t("CANCEL")}
      /*
       * ⚠️ **「기본 포커스를 취소에」는 여기서 못 한다** (2026-08-07 실측).
       *   `ConfirmModalProps`(`@decky/ui` 4.11.0 `Modal.d.ts:34`)는 `ModalRootProps`를
       *   상속할 뿐 **`preferredFocus`가 없다** — `tsc`가 잡았다.
       *   → 쓸 수 있는 방어는 `bDestructiveWarning` 하나다(파괴적 동작으로 표시).
       */
      bDestructiveWarning
      closeModal={closeModal}
      onOK={onConfirm}
    />
  );
}
