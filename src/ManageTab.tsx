import { useCallback, useEffect, useState, type ReactElement } from "react";
import { diskStateText } from "./confirmSpecs";
import { ConfirmModal, DialogButton, Focusable, ModalRoot, TextField, showModal } from "./deckyui";
import { setProfileNames, t, tCode, tDefault, type StringKey } from "./i18n";
import { PROFILE_NAME_MAX } from "./limits";
import { SaveConfirmModal } from "./saveConfirm";
import { slotSummary } from "./slots";
import {
  deleteGame, getOverview, listBackups, resetAll, restoreBackup, saveProfile, setProfileName,
  type BackupRow, type ConfirmParams, type DeleteConfirmParams, type Overview, type OverviewGame,
  type Profile, type ResetConfirmParams, type RestoreConfirmParams,
} from "./rpc";

/**
 * 전체 화면 「관리」 탭 (P8) — 게임 개별 삭제와 전체 초기화.
 *
 * ★★ **왜 여기인가 — 배치 자체가 첫 번째 방지 장치다**(설계 DESIGN-DELETE §4-A).
 *   · QAM 패널에는 아무것도 두지 않는다. QAM은 고빈도·496px 표면이라 파괴 동작의 자리가 아니다.
 *   · 「현황」 행에도 [삭제]를 두지 않는다. 그 화면은 F4가 이미 *"행이 길어 버튼↔게임 매칭이
 *     안 되고 오조작 위험"*을 지적한 자리다 — 거기에 파괴 버튼을 보태는 것은 방지 장치를
 *     쌓기 전에 사고 표면부터 넓히는 일이다. **확인창을 덧대는 것보다 오조작이 「생기지 않는
 *     구조」가 먼저다.**
 *
 * ★ 판정은 **전부 백엔드에 있다.** 이 화면은 무엇을 지울지 다시 계산하지 않고,
 *   "덮어쓰기인가"를 두 곳에서 판정하다 어긋난 저장 경로의 실패를 반복하지 않는다.
 *   프론트가 하는 일은 `CONFIRM_REQUIRED`를 받으면 **받은 토큰을 그대로 되돌려 주는 것**뿐이다.
 *
 * ★ 하단 패딩은 두지 않는다 — `StatusPage`의 스크롤 컨테이너가 `LIST_BOTTOM_PADDING`으로
 *   한 번에 처리한다(F2). 여기서 또 주면 여백이 두 번 붙는다.
 */

const META_STYLE = { fontSize: "11px", color: "#9aa0a6" } as const;
const HINT_STYLE = { fontSize: "11px", color: "#9aa0a6", margin: "4px 0 0" } as const;
const DANGER = "#ff6b5e";

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

/**
 * 개별 삭제 확인창 — 무엇을 잃는지 말하고 확정을 받는다.
 *
 * 값은 전부 `delete_preview`가 준 `params`에서 온다. **`get_overview`의 값과 섞지 않는다** —
 * 저쪽은 *"적용할 수 있는가"*(meta ∧ 본체), 이쪽은 *"지울 것이 있는가"*(meta)라 기준이 다르고,
 * 섞으면 확인창이 실제로 지워질 것과 다른 것을 말하게 된다.
 */
function DeleteConfirm({
  params,
  onConfirm,
  closeModal,
}: {
  params: DeleteConfirmParams;
  onConfirm: () => void;
  /** `showModal`이 최상위 엘리먼트에 주입한다. 우리가 감싼 컴포넌트가 받으므로 그대로 넘긴다. */
  closeModal?: () => void;
}) {
  const has: Record<Profile, boolean> = { dock: params.has_dock, internal: params.has_internal };
  return (
    <ConfirmModal
      strTitle={t("DELETE_CONFIRM_TITLE", { name: params.name })}
      /*
       * ★ 2026-08-07 실기 교훈(저장 확인창): `"\n\n"`으로 이어 붙이면 **한 문단으로 뭉쳐**
       *   렌더된다. `strDescription`은 `ReactNode`라 엘리먼트로 줘야 줄이 갈린다.
       */
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>{t("DELETE_CONFIRM_BODY")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {(["dock", "internal"] as const).map((p) => (
              <div key={p} style={META_STYLE}>
                {has[p]
                  ? t("DELETE_CONFIRM_SLOT", {
                      profile: t(profileKey(p)),
                      saved_at: params.saved_at?.[p] || t("DELETE_CONFIRM_SAVED_UNKNOWN"),
                    })
                  : t("DELETE_CONFIRM_SLOT_EMPTY", { profile: t(profileKey(p)) })}
              </div>
            ))}
          </div>
          {/* 대피가 선행한다는 사실을 말한다 — 삭제는 "빈 내용으로 덮어쓰기"이고, 이 툴의
              문법은 "어떤 쓰기든 그 전에 백업"이다(G13). 백업은 삭제 후에도 남는다. */}
          <div>{t("DELETE_CONFIRM_BACKUP", { n: params.backups })}</div>
          {/* ★ F10(자기 설명) — 사용자가 가장 오해하기 쉬운 지점이라 **반드시** 노출한다. */}
          <div style={{ color: "#ffb454" }}>{t("MANAGE_KEEP_CONFIG")}</div>
        </div>
      }
      strOKButtonText={t("DELETE_CONFIRM_OK")}
      strCancelButtonText={t("CANCEL")}
      /*
       * ⚠️ 「기본 포커스를 취소에」는 여기서 못 한다 — `ConfirmModalProps`에 `preferredFocus`가
       *   없다(2026-08-07 실측, `tsc`가 잡았다). 쓸 수 있는 표시는 `bDestructiveWarning` 하나다.
       */
      bDestructiveWarning
      closeModal={closeModal}
      onOK={onConfirm}
    />
  );
}

/**
 * 전체 초기화 확인창 — **2단 방어**(확인 모달 + type-to-confirm).
 *
 * ★★ 입력 대조의 **판정은 백엔드에 있다.** 여기 `bOKDisabled`는 UX 보조일 뿐이고,
 *   런타임에 무효여도(설계 §4-D U20 ②) 사용자가 OK를 눌러 봐야 백엔드가 토큰 튜플 비교에서
 *   막고 `CONFIRM_REQUIRED`를 다시 낸다 — **fail-closed가 프론트의 성실함이 아니라 계약에서
 *   나온다.** 그래서 이 컴포넌트가 틀려도 데이터는 안 지워진다.
 *
 * ★ `challenge`는 **번역하지 않는다.** 백엔드 상수(`"delete"`)를 그대로 보여주고 그대로
 *   되돌린다. i18n에 넣으면 화면의 단어와 백엔드가 대조하는 상수가 언어에 따라 갈려
 *   **입력이 영영 안 맞는** 상태가 된다.
 */
function ResetConfirm({
  params,
  onConfirm,
  closeModal,
}: {
  params: ResetConfirmParams;
  onConfirm: (text: string) => void;
  closeModal?: () => void;
}) {
  // ★ 훅은 **이 컴포넌트 안**에 있다. StatusPage의 훅 슬롯 순서를 프로브가 참조하므로
  //   저쪽에는 새 useState를 추가하지 않는다(설계 §4-A 구현 주의).
  const [typed, setTyped] = useState("");
  const matched = typed === params.challenge;
  return (
    <ConfirmModal
      strTitle={t("RESET_CONFIRM_TITLE")}
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {/* 파괴 규모 고지는 **입력이 아니라 이 줄이 전담**한다 — challenge가 고정 단어라
              입력만으로는 규모를 알 수 없기 때문이다(설계 §4-C). 숫자는 백엔드가 센 값이다. */}
          <div>{t("RESET_CONFIRM_BODY", { games: params.games, profiles: params.profiles })}</div>
          <div style={META_STYLE}>{t("RESET_CONFIRM_BACKUP_KEPT")}</div>
          {/* ★ F11 ①: 표시명은 registry settings에 살아 **이 초기화에 같이 지워진다.**
              모르고 잃으면 안 되므로 미리 말한다. 0이면 줄을 그리지 않는다(기존 문법). */}
          {params.named > 0 ? <div>{t("RESET_CONFIRM_NAMES", { n: params.named })}</div> : null}
          <div style={{ color: "#ffb454" }}>{t("MANAGE_KEEP_CONFIG")}</div>
          <div>{t("RESET_CONFIRM_TYPE", { word: params.challenge })}</div>
          {/* `focusOnMount` — 빅픽처에서 텍스트 필드가 포커스를 받아야 가상 키보드가 뜬다.
              이 배선이 실제로 되는지가 U20 ①이다(타입 존재 ≠ 런타임 보장). */}
          <TextField
            label={t("RESET_CONFIRM_FIELD_LABEL")}
            value={typed}
            focusOnMount
            onChange={(e) => setTyped(e.target.value)}
          />
        </div>
      }
      strOKButtonText={t("RESET_CONFIRM_OK")}
      strCancelButtonText={t("CANCEL")}
      bDestructiveWarning
      bOKDisabled={!matched}
      closeModal={closeModal}
      onOK={() => onConfirm(typed)}
    />
  );
}

/** 백업 종류 문구 — **판정은 백엔드의 `kind` 코드**이고 화면은 문구만 고른다(`tier`와 같은 문법). */
function kindText(row: BackupRow): string {
  if (row.kind === "profile_dock" || row.kind === "profile_internal") {
    return t("BACKUP_KIND_PROFILE", {
      profile: t(row.kind === "profile_dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL"),
    });
  }
  if (row.kind === "disk") return t("BACKUP_KIND_DISK");
  return t("BACKUP_KIND_UNKNOWN");
}

/**
 * 백업 목록 — **읽기 전용 진입점**이다. 여기서 파괴적인 일은 일어나지 않고,
 * [복원]을 눌러야 비로소 확인창(또는 무동작 안내)으로 넘어간다.
 *
 * ★ 목록·순서·파일명 파싱은 **전부 백엔드가 준 값**이다. 프론트는 문자열을 쪼개지도,
 *   다시 정렬하지도 않는다 — 두 곳에서 판정하면 화면이 실제와 다른 것을 말하게 된다.
 * ★ `ConfirmModal`이 아니라 `ModalRoot`인 이유: 이 창의 답은 "예/아니오"가 아니라
 *   **여러 행 중 하나 고르기**다. OK 버튼이 있으면 "무엇을" 확정하는지가 모호해진다.
 */
function BackupList({
  name,
  rows,
  onRestore,
  closeModal,
}: {
  name: string;
  rows: BackupRow[];
  onRestore: (row: BackupRow) => void;
  closeModal?: () => void;
}) {
  return (
    <ModalRoot closeModal={closeModal}>
      <div style={{ fontSize: "18px", fontWeight: "bold", marginBottom: "4px" }}>
        {t("BACKUP_LIST_TITLE", { name })}
      </div>
      {/* ★ 2단계 시맨틱을 **목록에서 먼저** 말한다 — 복원이 프로필까지 되돌린다고 오해하면
          복구 절차를 잘못 밟는다(`qa/test_restore_path.py`의 독스트링이 경고한 그대로다).
          ⚠️ 2026-08-10 QA R2: 예전 문구는 *"복원 뒤 프로필에도 넣을지 물어본다"*고 **조건 없이**
            약속했는데, 그 제안은 `kind`가 `profile_*`일 때만 뜬다. 실사용 백업은 대부분
            `disk`(적용·복원 직전 대피본)라 **오지 않을 창을 약속하는** 문구였다. */}
      <div style={HINT_STYLE}>{t("BACKUP_LIST_HINT")}</div>
      {rows.length === 0 ? (
        <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>
          {t("BACKUP_LIST_EMPTY")}
        </div>
      ) : (
        <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "10px" }}>
          {rows.map((row) => (
            <Focusable
              key={row.backup_id}
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 4px" }}
            >
              <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                <div style={{ fontSize: "14px" }}>{kindText(row)}</div>
                <div style={META_STYLE}>
                  {t("BACKUP_ROW_META", {
                    stamp: row.stamp_label || t("BACKUP_STAMP_UNKNOWN"),
                    size: row.size,
                    filename: row.filename,
                  })}
                </div>
              </div>
              <DialogButton
                onClick={() => {
                  // 목록을 먼저 닫는다 — 확인창이 목록 위에 겹쳐 뜨면 무엇을 확정하는지 흐려진다.
                  closeModal?.();
                  onRestore(row);
                }}
                style={{ minWidth: "96px", padding: "6px 8px", fontSize: "13px" }}
              >
                {t("BACKUP_RESTORE")}
              </DialogButton>
            </Focusable>
          ))}
        </Focusable>
      )}
    </ModalRoot>
  );
}

/**
 * 복원 확인창 — **덮어쓰는 것은 게임 설정 파일**이라고 분명히 말한다.
 *
 * 값은 전부 백엔드 `params`에서 온다(`disk_state` 4분류는 저장 확인창과 같은 관문을 쓴다).
 * ⚠️ 백업 잔량을 숫자로 약속하지 않는다 — 링 크기는 봉투에 없고, "N칸 중"은 잔량 약속으로
 *   읽혀 오정보가 된다(P8-2 이탈 #8과 같은 판단). 말해야 하는 사실은 *한 칸을 쓴다*와
 *   *가장 오래된 것이 밀릴 수 있다* 둘뿐이다.
 */
function RestoreConfirm({
  params,
  onConfirm,
  closeModal,
}: {
  params: RestoreConfirmParams;
  onConfirm: () => void;
  closeModal?: () => void;
}) {
  return (
    <ConfirmModal
      strTitle={t("RESTORE_CONFIRM_TITLE")}
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>
            {t("RESTORE_CONFIRM_BODY", {
              stamp: params.stamp_label || params.backup_id,
            })}
          </div>
          <div>{t("RESTORE_CONFIRM_CURRENT", { state: diskStateText(params) })}</div>
          <div style={META_STYLE}>{t("RESTORE_CONFIRM_BACKUP")}</div>
          {/* 2단계 시맨틱 — 이 창이 끝나도 프로필 슬롯은 그대로다.
              ★ 후속 제안은 **그 백업이 어느 프로필의 대피본일 때만** 뜬다(`kind`). 그래서
                문구도 그때만 그 약속을 한다 — `disk`·`unknown`은 슬롯을 추론할 근거가 없어
                제안이 오지 않는다(2026-08-10 QA R2: 조건 없는 약속은 대다수 경로에서 거짓이었다). */}
          <div style={{ color: "#ffb454" }}>
            {params.kind === "profile_dock" || params.kind === "profile_internal"
              ? t("RESTORE_CONFIRM_SLOT_ASK")
              : t("RESTORE_CONFIRM_SLOT_NOTE")}
          </div>
        </div>
      }
      strOKButtonText={t("RESTORE_CONFIRM_OK")}
      strCancelButtonText={t("CANCEL")}
      bDestructiveWarning
      closeModal={closeModal}
      onOK={onConfirm}
    />
  );
}

/**
 * 복원 성공 뒤의 **후속 제안**(2단계의 ②) — 백업이 어느 프로필의 대피본인지 백엔드가
 * `kind`로 알려줄 때만 뜬다. `disk`·`unknown`은 슬롯을 추론할 근거가 없어 안내만 한다.
 */
function RestoreFollowUp({
  profile,
  onConfirm,
  closeModal,
}: {
  profile: Profile;
  onConfirm: () => void;
  closeModal?: () => void;
}) {
  const label = t(profileKey(profile));
  return (
    <ConfirmModal
      strTitle={t("RESTORE_FOLLOWUP_TITLE")}
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>{t("RESTORE_FOLLOWUP_BODY", { profile: label })}</div>
        </div>
      }
      strOKButtonText={t("RESTORE_FOLLOWUP_OK")}
      strCancelButtonText={t("RESTORE_FOLLOWUP_SKIP")}
      closeModal={closeModal}
      onOK={onConfirm}
    />
  );
}

/**
 * 표시 이름 편집창 (F11 ①) — **P8의 type-to-confirm과 같은 부품·같은 배선**이다
 * (`ConfirmModal` + `TextField` + `focusOnMount`).
 *
 * ★ 왜 같은 패턴인가: Game Mode에서 텍스트 입력에 **가상 키보드가 뜨는지가 아직 실사용
 *   미확인**(U20 ①)이다. 두 입력 UI가 서로 다른 부품을 쓰면 실기에서 따로 판정해야 하고,
 *   폴백이 필요해지면 두 곳을 각각 고쳐야 한다. 같은 패턴이면 **한 번에 같이 판정**된다.
 * ★ OK는 **항상 활성**이다 — 빈 입력은 오류가 아니라 *"기본 이름으로 되돌리기"*다.
 *   (`bOKDisabled`의 런타임 동작도 미확인(U20 ②)인데, 여기서는 기댈 필요조차 없다.)
 */
function NameEditModal({
  profile,
  current,
  fallback,
  maxLen,
  onConfirm,
  closeModal,
}: {
  profile: Profile;
  /** 지금 화면에 보이는 이름(기본이든 사용자 것이든). */
  current: string;
  /** 비웠을 때 돌아갈 기본 이름 — 번역이 정본이다(백엔드는 이 값을 모른다). */
  fallback: string;
  maxLen: number;
  onConfirm: (name: string) => void;
  closeModal?: () => void;
}) {
  // ★ 훅은 **이 컴포넌트 안**에 있다. StatusPage의 훅 슬롯 순서를 프로브가 참조하므로
  //   저쪽에는 새 useState를 추가하지 않는다(P8 ResetConfirm과 같은 이유).
  const [typed, setTyped] = useState(current === fallback ? "" : current);
  void profile;   // 식별자는 화면에 쓰지 않는다 — 이름만 다룬다(표시 계층 분리를 눈에 보이게)
  return (
    <ConfirmModal
      strTitle={t("NAME_EDIT_TITLE")}
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>{t("NAME_EDIT_BODY", { current })}</div>
          <div style={META_STYLE}>{t("NAME_EDIT_HINT", { fallback, max: maxLen })}</div>
          <div style={{ color: "#ffb454" }}>{t("MANAGE_NAMES_HINT")}</div>
          <TextField
            label={t("NAME_EDIT_FIELD_LABEL")}
            value={typed}
            focusOnMount
            onChange={(e) => setTyped(e.target.value)}
          />
        </div>
      }
      strOKButtonText={t("NAME_EDIT_OK")}
      strCancelButtonText={t("CANCEL")}
      closeModal={closeModal}
      onOK={() => onConfirm(typed)}
    />
  );
}

function ManageRow({
  game,
  busy,
  onDelete,
  onBackups,
}: {
  game: OverviewGame;
  busy: boolean;
  onDelete: (appid: string) => void;
  onBackups: (game: OverviewGame) => void;
}) {
  return (
    <Focusable
      style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 10px" }}
    >
      <div style={{ flex: "1 1 auto", minWidth: 0 }}>
        <div style={{ fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis" }}>
          {game.name}
        </div>
        <div style={META_STYLE}>
          {/* F5 — 문장은 `slots.ts` 한 곳에서 만든다(현황 탭과 같은 말을 해야 한다). */}
          {slotSummary(game)}
        </div>
      </div>
      {/* ★ 행당 파괴 버튼은 **하나뿐**이다. F6의 [백업 N]은 **읽기 전용 진입**이라
          오탭의 최악 결과가 "모달 하나 잘못 열림"에 머문다 — 그 비대칭이 이 행 구성의
          근거다(설계 §4-B 개정 2판).
          ★ 0건이면 **비활성**이다: 눌러도 빈 목록으로 이끄는 버튼은 라벨이 거짓말을 한다.
            숫자는 백엔드가 센 값이다(프론트 재계산 금지). */}
      <DialogButton
        disabled={busy || game.backups === 0}
        onClick={() => onBackups(game)}
        style={{ minWidth: "96px", padding: "6px 8px", fontSize: "13px" }}
      >
        {t("MANAGE_BACKUPS", { n: game.backups })}
      </DialogButton>
      <DialogButton
        disabled={busy}
        onClick={() => onDelete(game.appid)}
        style={{ minWidth: "96px", padding: "6px 8px", fontSize: "13px" }}
      >
        {t("MANAGE_DELETE")}
      </DialogButton>
    </Focusable>
  );
}

export function ManageTab() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    // 관리 탭은 has_dock/has_internal만 쓰고 disk_matches(detail 전용, 원본 설정 파일 전수 sha)는
    // 안 읽는다 — detail을 끈다(Codex #6: 관리 탭 진입마다 모든 원본 파일을 읽던 낭비 제거).
    getOverview().then(
      (res) => {
        // ★★ 2026-08-10 QA R3: 이 한 줄이 빠져 있어서 **전체 초기화 뒤에도 i18n의 덮어쓰기가
        //   남았다.** 백엔드는 표시명을 비웠는데 화면은 같은 행에서 옛 커스텀 이름과
        //   "기본 이름"을 동시에 말했다 — 확인창이 한 *"기본값으로 돌아갑니다"*가 거짓이 됐다.
        //   `getOverview` 소비자 셋(현황·QAM·여기)이 **같은 형태**여야 한다.
        if (res.ok) setProfileNames(res.data.profile_names);
        if (res.ok) setOverview(res.data);
        else setNote(tCode(res.code, "LOAD_FAILED"));
      },
      () => setNote(tCode("UNEXPECTED", "LOAD_FAILED")),
    );
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 개별 삭제 — 토큰 없이 한 번 불러 `CONFIRM_REQUIRED`를 받고, 확인 뒤 **그 토큰을 그대로**
   * 되돌려 재호출한다.
   *
   * ⚠️ 확인 뒤에도 `CONFIRM_REQUIRED`가 다시 올 수 있다(확인창을 띄운 사이 프로필이
   *   저장됐다 = TOCTOU). 그때는 **갱신된 params로 다시 묻는다** — 사용자가 본 숫자가 이미
   *   낡았으므로 그대로 밀어붙이면 안 된다. 사용자가 확정을 누를 때만 한 걸음 나아가므로
   *   이 되묻기는 스스로 반복하지 않는다.
   */
  const runDelete = useCallback(
    (appid: string, token?: string) => {
      setBusy(true);
      return deleteGame(appid, token)
        .then(
          (res) => {
            if (res.ok) {
              setNote(t("DELETE_OK", { name: res.data.name }));
              load();
              return;
            }
            if (res.code === "CONFIRM_REQUIRED") {
              // ⚠️ 흐름 신호다 — 오류 문구로 그리지 않는다.
              askDelete(res.params as unknown as DeleteConfirmParams);
              return;
            }
            // `DELETE_FAILED`도 여기로 온다 — 부분 삭제 상태일 수 있고, 다시 삭제하면 완결된다.
            setNote(tCode(res.code, "DELETE_ACTION_FAILED"));
            load();
          },
          () => setNote(tCode("UNEXPECTED", "DELETE_ACTION_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load],
  );

  /**
   * ★★ 확인창을 **못 띄우면 그 사실을 말한다**(2026-08-07 QA 반려 ②).
   *   `showModal`은 런타임에 얻어지는 값이라 `undefined`일 수 있고, 그러면 `TypeError`가
   *   `.then` 콜백 안에서 나 **note도 토스트도 없이 버튼이 흔적 없이 죽는다.**
   *   안전한 쪽(=아무것도 안 지움)인 건 맞지만, 요구된 것은 안전 **그리고** 진단 가능성이다.
   */
  function askDelete(p: DeleteConfirmParams) {
    openModal(
      <DeleteConfirm params={p} onConfirm={() => { void runDelete(p.appid, p.confirm_token); }} />,
      // 삭제는 토큰이 없으면 일어나지 않는다 — "아무것도 지우지 않았습니다"가 참인 유이한 자리(+초기화).
      "MANAGE_MODAL_FAILED",
    );
  }

  /** 전체 초기화 — 흐름은 개별 삭제와 같고, 확인창만 2단(입력 대조)이다. */
  const runReset = useCallback(
    (token?: string, text?: string) => {
      setBusy(true);
      return resetAll(token, text)
        .then(
          (res) => {
            if (res.ok) {
              const deleted = res.data.counts.deleted ?? 0;
              // ⚠️ 게임별 실패가 있어도 봉투는 ok:true다 — 무엇이 남았는지를 같이 말한다.
              setNote(t("RESET_OK", { deleted, left: res.data.results.length - deleted }));
              load();
              return;
            }
            if (res.code === "CONFIRM_REQUIRED") {
              askReset(res.params as unknown as ResetConfirmParams);
              return;
            }
            setNote(tCode(res.code, "RESET_ACTION_FAILED"));
            load();
          },
          () => setNote(tCode("UNEXPECTED", "RESET_ACTION_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load],
  );

  // ── 백업 복원 (P9) ─────────────────────────────────────────────────────────
  //
  // ★★ **2단계 시맨틱**을 화면이 그대로 수행한다(설계 F6-F8 §2-A·§2-D):
  //   ① `restoreBackup` → 게임 설정 파일이 백업 내용이 된다
  //   ② (제안) `saveProfile` → 그 내용이 프로필 슬롯으로 들어간다
  //   ①에서 멈춘 상태도 **정상**이라 중간 이탈에 복구 코드가 필요 없다.

  /**
   * 확인창을 **못 띄우면 그 사실을 말한다** — 안전한 것과 진단 가능한 것은 다른 요건이다.
   *
   * ★★ **문구는 호출부가 준다**(2026-08-10 QA R1). 한 문장을 공유하면 그 문장이 어느 한
   *   경로에서는 반드시 거짓이 된다 — 실제로 *"아무것도 지우지 않았습니다"*가 저장·복원·
   *   목록·이름 편집까지 덮었고, **복원이 성공해 디스크가 이미 바뀌고 백업 링이 1칸 소모된
   *   뒤**에 그 문장이 성공 안내를 덮어썼다. 화면의 마지막 말이 사실과 반대였던 것이다.
   *   `index.tsx`에서 전용 키를 만든 판단(P10 이탈 #1)을 여기서 빠뜨린 자리다.
   */
  function openModal(node: ReactElement, failKey: StringKey) {
    try {
      showModal(node);
    } catch (err) {
      console.error("[gfxprofile] modal failed", err);
      setNote(t(failKey));
    }
  }

  /**
   * 복원 후속 저장 — **기존 저장 흐름 그대로**다(같은 route·같은 토큰 계약·같은 확인창).
   * 복원 직후의 디스크 내용을 슬롯에 넣는 것이므로 덮어쓰기면 저장 확인창이 뜬다.
   */
  const runSave = useCallback(
    (appid: string, profile: Profile, token?: string) => {
      setBusy(true);
      return saveProfile(appid, profile, token)
        .then(
          (res) => {
            if (res.ok) {
              setNote(t("SAVE_OK", { profile: t(profileKey(profile)) }));
              load();
              return;
            }
            if (res.code === "CONFIRM_REQUIRED") {
              const p = res.params as unknown as ConfirmParams;
              openModal(
                <SaveConfirmModal
                  params={p}
                  profile={profile}
                  onConfirm={() => { void runSave(appid, profile, p.confirm_token); }}
                />,
                // 저장은 토큰이 없으면 일어나지 않는다 — "저장하지 않았습니다"가 참이다.
                "SAVE_CONFIRM_MODAL_FAILED",
              );
              return;
            }
            setNote(tCode(res.code, "SAVE_FAILED"));
          },
          () => setNote(tCode("UNEXPECTED", "SAVE_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load],
  );

  /**
   * 복원 — 흐름은 삭제와 같다: 토큰 없이 한 번 부르고, 확인이 필요하면 **받은 토큰을 그대로**
   * 되돌린다. 다른 점은 백엔드가 **묻지 않는 두 갈래**를 돌려줄 수 있다는 것이다:
   *   · `already` — 디스크가 이미 그 백업과 같다. 아무것도 쓰지 않았고 링도 안 밀렸다.
   *   · `restored`(무토큰) — 설정 파일이 없어 잃을 것이 없었다.
   */
  const runRestore = useCallback(
    (game: OverviewGame, row: BackupRow, token?: string) => {
      setBusy(true);
      return restoreBackup(game.appid, row.backup_id, token)
        .then(
          (res) => {
            if (res.ok) {
              if (res.data.outcome === "already") {
                // 실패가 아니다 — 되돌릴 것이 없었다는 뜻이다.
                setNote(t("RESTORE_ALREADY"));
                return;
              }
              const stamp = res.data.stamp_label || res.data.backup_id;
              setNote(t("RESTORE_OK", { stamp }));
              load();                       // 복원이 대피본을 하나 만들었다 — 개수가 바뀐다
              const kind = res.data.kind;
              if (kind === "profile_dock" || kind === "profile_internal") {
                const profile: Profile = kind === "profile_dock" ? "dock" : "internal";
                openModal(
                  <RestoreFollowUp
                    profile={profile}
                    onConfirm={() => { void runSave(game.appid, profile); }}
                  />,
                  // ★ 여기서는 **복원이 이미 끝났다.** "아무것도 안 했다"고 말하면 거짓이다 —
                  //   못 한 것은 후속 제안뿐이고, 남은 길(현황 탭에서 저장)을 알려 준다.
                  "RESTORE_FOLLOWUP_MODAL_FAILED",
                );
              } else {
                // `disk`·`unknown`은 어느 슬롯의 내용인지 추론할 근거가 없다 — 안내만 한다.
                setNote(t("RESTORE_OK_MANUAL", { stamp }));
              }
              return;
            }
            if (res.code === "CONFIRM_REQUIRED") {
              const p = res.params as unknown as RestoreConfirmParams;
              openModal(
                <RestoreConfirm
                  params={p}
                  onConfirm={() => { void runRestore(game, row, p.confirm_token); }}
                />,
                // 토큰이 안 돌아가면 복원은 일어나지 않는다(계약에서 나오는 fail-closed).
                "RESTORE_MODAL_FAILED",
              );
              return;
            }
            // GAME_RUNNING(조기 거부) · BACKUP_FILE_MISSING(그 사이 prune) · G4 거부 등 —
            // 전부 `tCode` 단일 관문으로 문구를 고른다. 여기서 코드별 분기를 만들지 않는다.
            setNote(tCode(res.code, "RESTORE_FAILED"));
            load();
          },
          () => setNote(tCode("UNEXPECTED", "RESTORE_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load, runSave],
  );

  /** 목록을 **먼저 받아** 모달을 연다 — 빈 창이 떴다가 채워지는 중간 상태를 만들지 않는다. */
  const openBackups = useCallback(
    (game: OverviewGame) => {
      setBusy(true);
      return listBackups(game.appid)
        .then(
          (res) => {
            if (!res.ok) {
              setNote(tCode(res.code, "BACKUP_LIST_FAILED"));
              return;
            }
            openModal(
              <BackupList
                name={game.name}
                rows={res.data.backups}
                onRestore={(row) => { void runRestore(game, row); }}
              />,
              // 목록은 읽기 전용 진입이다 — 못 띄운 것 말고는 아무 일도 없었다.
              "BACKUP_LIST_MODAL_FAILED",
            );
          },
          () => setNote(tCode("UNEXPECTED", "BACKUP_LIST_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runRestore],
  );

  /**
   * 표시 이름 변경 (F11 ①) — **식별자는 이 경로로 절대 움직이지 않는다.**
   * 백엔드가 정규화(공백 정리·상한 자르기·빈 값이면 기본값 복귀)한 **결과를 그대로** 받아
   * i18n에 반영한다 — 프론트가 다시 다듬으면 사용자가 본 것과 저장된 것이 갈린다.
   */
  const runRename = useCallback(
    (profile: Profile, name: string) => {
      setBusy(true);
      return setProfileName(profile, name)
        .then(
          (res) => {
            if (!res.ok) {
              setNote(tCode(res.code, "NAME_EDIT_FAILED"));
              return;
            }
            setProfileNames(res.data.profile_names);
            const saved = res.data.profile_names[profile];
            setNote(saved ? t("NAME_EDIT_OK_NOTE", { name: saved }) : t("NAME_EDIT_RESET_NOTE"));
            load();                       // 라벨이 바뀌었으니 목록도 다시 그린다
          },
          () => setNote(tCode("UNEXPECTED", "NAME_EDIT_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load],
  );

  function askRename(profile: Profile) {
    // 기본 이름은 **번역이 정본**이다. 사용자가 정한 이름이 있으면 i18n이 이미 그것을 돌려주므로
    // `t()` 한 번이면 "지금 보이는 이름"이 되고, 기본값은 봉투의 빈 문자열로 판별한다.
    const current = t(profileKey(profile));
    openModal(
      <NameEditModal
        profile={profile}
        current={current}
        fallback={tDefault(profileKey(profile))}
        maxLen={PROFILE_NAME_MAX}
        onConfirm={(name) => { void runRename(profile, name); }}
      />,
      "NAME_EDIT_MODAL_FAILED",
    );
  }

  function askReset(p: ResetConfirmParams) {
    openModal(
      <ResetConfirm params={p} onConfirm={(text) => { void runReset(p.confirm_token, text); }} />,
      "MANAGE_MODAL_FAILED",
    );
  }

  const games = overview?.games ?? [];
  const sorted = [...games].sort((a, b) => a.name.localeCompare(b.name));
  const total = overview?.counts.total ?? 0;

  return (
    <div>
      <div style={{ fontSize: "13px", color: "#9aa0a6", margin: "4px 0 2px" }}>
        {overview === null ? "" : t("MANAGE_SUMMARY", { total })}
      </div>
      {/* ★ F10 선반영 — 동작 아래 한 줄 설명. 이 화면에서 사용자가 가장 오해하기 쉬운 것이
          *"게임 설정까지 지워지나"*이므로 목록 위에서 먼저 답한다. */}
      <div style={HINT_STYLE}>{t("MANAGE_DELETE_HINT")}</div>

      {note ? <div style={{ ...META_STYLE, fontSize: "12px", margin: "8px 0" }}>{note}</div> : null}

      <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "8px" }}>
        {sorted.map((g) => (
          <ManageRow
            key={g.appid}
            game={g}
            busy={busy}
            onDelete={(appid) => void runDelete(appid)}
            onBackups={(game) => void openBackups(game)}
          />
        ))}
      </Focusable>

      {/* 「모르는 것을 없다고 말하지 않는다」 — null은 로딩 중이거나 조회 실패다(둘 다 0개가 아니다). */}
      {overview === null ? (
        note ? null : (
          <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>{t("LOADING")}</div>
        )
      ) : sorted.length === 0 ? (
        <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>{t("NO_GAMES")}</div>
      ) : null}

      {/* ── 표시 이름 (F11 ①) ────────────────────────────────────────────────
          ★ 바꾸는 것은 **화면 글자뿐**이다. 저장된 프로필·백업·경로는 그대로 있고,
            그 사실을 안내 줄이 말한다(사용자가 가장 오해하기 쉬운 지점이다). */}
      <div style={{ marginTop: "24px", paddingTop: "12px", borderTop: "1px solid #3a3f44" }}>
        <div style={{ fontSize: "14px", fontWeight: "bold", marginBottom: "6px" }}>
          {t("MANAGE_NAMES_TITLE")}
        </div>
        <div style={HINT_STYLE}>{t("MANAGE_NAMES_HINT")}</div>
        <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "8px" }}>
          {(["dock", "internal"] as const).map((profile) => (
            <Focusable
              key={profile}
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "6px 10px" }}
            >
              <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                <div style={{ fontSize: "15px" }}>{t("MANAGE_NAME_ROW", { profile: t(profileKey(profile)) })}</div>
                <div style={META_STYLE}>
                  {overview?.profile_names?.[profile]
                    ? t("MANAGE_NAME_CUSTOM")
                    : t("MANAGE_NAME_DEFAULT")}
                </div>
              </div>
              <DialogButton
                disabled={busy}
                onClick={() => askRename(profile)}
                style={{ minWidth: "120px", padding: "6px 8px", fontSize: "13px" }}
              >
                {t("MANAGE_NAME_EDIT")}
              </DialogButton>
            </Focusable>
          ))}
        </Focusable>
      </div>

      {/* ── 위험 구역 ─────────────────────────────────────────────────────────
          시각적으로 갈라 둔다. 파괴 범위가 가장 큰 동작이 목록의 연장선에 있으면
          "다음 항목"처럼 읽힌다 — 경계선과 경고색이 그 오독을 막는 장치다. */}
      <div
        style={{
          marginTop: "24px", paddingTop: "12px", borderTop: `1px solid ${DANGER}`,
        }}
      >
        <div style={{ fontSize: "14px", fontWeight: "bold", color: DANGER, marginBottom: "6px" }}>
          {t("MANAGE_DANGER_TITLE")}
        </div>
        <div style={{ fontSize: "13px", marginBottom: "8px" }}>
          {t("RESET_ZONE_BODY", { n: total })}
        </div>
        <Focusable>
          {/* 등록 0개면 비활성 — 눌러도 아무 일이 없는 버튼은 라벨이 거짓말을 한다.
              ⚠️ 숨기지 않고 **비활성**으로 둔다: 기능이 있다는 사실 자체는 보여야 한다. */}
          <DialogButton
            disabled={busy || total === 0}
            onClick={() => void runReset()}
            style={{ minWidth: "200px" }}
          >
            {t("RESET_OPEN")}
          </DialogButton>
        </Focusable>
        <div style={HINT_STYLE}>{t("RESET_HINT")}</div>
      </div>
    </div>
  );
}
