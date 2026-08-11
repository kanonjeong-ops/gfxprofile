import { t, tCode, tDefault } from "./i18n";
import { BACKUP_WARN_APPLIES, PROFILE_NAME_MAX } from "./limits";
import type { InputConfirmSpec, PlainConfirmSpec } from "./popup";
import type {
  AddGameConfirmParams, ConfirmParams, DeleteConfirmParams, Profile,
  ResetConfirmParams, RestoreConfirmParams,
} from "./rpc";

/**
 * **확인창의 선언(spec) — 정의는 이 파일 하나뿐이다.**
 *
 * ★★ 왜 컴포넌트가 아니라 spec인가(§4-C): 확인창을 **어떻게 그릴지**(팝업 위 중첩 모달 /
 *   팝업 내부 오버레이)는 실기에서 갈릴 수 있는 문제이고, **무엇을 물을지**는 갈리면 안 되는
 *   문제다. 둘을 갈라 두면 렌더 방식을 한 줄(`NESTED_CONFIRM`)로 바꿔도 문구·정보량은
 *   한 글자도 안 움직인다.
 *
 * ★ 여기는 **표시 전용**이다. "물어야 하는가"는 백엔드가 정하고(`CONFIRM_REQUIRED`),
 *   이 파일은 받은 `params`를 그릴 뿐이다 — 프론트가 조건을 다시 계산하지 않는다.
 *
 * ⚠️ 문구·정보량은 **현행 유지가 원칙**이다(P12 spec화 범위). 설계가 명시한 변경분
 *   (§9 등록 해제 안내 3종 · §7 초기화 제외 고지 · §5-C 백업 문구)은 그 화면을 만드는
 *   단계(P13)에서 이 파일에 반영한다 — 지금 섞으면 "spec화 전후 문구 동일성" 검사가
 *   무엇을 재는지 알 수 없게 된다.
 * ⚠️ `bDestructiveWarning`은 spec에 없다: 실측상 **시각 효과가 없고**(§1-10) A8이
 *   "위험색 차등 없음 — 초기화 확인창의 ⚠ 블록만"으로 확정했다. 경고는 `warnBlock`이 맡는다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const META_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;
const WARN_STYLE = { color: "#ffb454" } as const;

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

/**
 * 「덮어쓸 내용」이 지금 어떤 상태인지를 한 줄로 — 백엔드가 준 4분류를 그대로 쓴다.
 *
 * ★ M1은 화면 문구를 합쳤지만 **코드는 갈라 둔다**(설계 §2-E-0). 합치면 `"unknown"`이
 *   *"게임에서 조정함"*과 *"조회 실패"* 두 뜻을 갖게 되어 문구를 고를 수 없다.
 * ★ 저장 확인창과 복원 확인창이 **같은 관문**을 쓴다 — 같은 백엔드 값이 화면마다 다른 말로
 *   보이면 사용자는 둘을 다른 상태로 읽는다.
 */
export function diskStateText(p: {
  disk_state: ConfirmParams["disk_state"];
  matched_profile?: Profile;
}): string {
  if (p.disk_state === "other_profile" && p.matched_profile) {
    return t("DISK_STATE_OTHER", { profile: t(profileKey(p.matched_profile)) });
  }
  if (p.disk_state === "unknown") return t("DISK_STATE_UNKNOWN");
  if (p.disk_state === "missing") return t("DISK_STATE_MISSING");
  return t("DISK_STATE_LOOKUP_FAILED");
}

/** 저장(덮어쓰기) 확인 — 빈 슬롯 첫 저장은 백엔드가 묻지 않으므로 여기 오지 않는다. */
export function makeSaveConfirmSpec(
  params: ConfirmParams,
  profile: Profile,
  onOK: () => void,
): PlainConfirmSpec {
  const label = t(profileKey(profile));
  return {
    kind: "plain",
    title: t("SAVE_CONFIRM_TITLE", { profile: label }),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("SAVE_CONFIRM_BODY")}</div>
        <div>{t("SAVE_CONFIRM_CURRENT", { size: params.size, sha1: params.sha1_short })}</div>
        <div>{t("SAVE_CONFIRM_INCOMING", { state: diskStateText(params) })}</div>
        {/* ★ 실측으로 확정된 한계(P4-1): 덮어쓴 프로필의 대피본은 `disk` 백업과 **한 링(10칸)을
            공유**해서 그 게임을 몇 번 적용하면 사라진다. "되돌릴 수 있다"고만 적으면 조건부 참이고,
            조건을 안 적으면 오정보다. */}
        <div style={WARN_STYLE}>{t("SAVE_CONFIRM_BACKUP_LIMIT", { n: BACKUP_WARN_APPLIES })}</div>
      </div>
    ),
    okText: t("SAVE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 개별 등록 해제 확인 — 무엇을 잃는지 말하고 확정을 받는다.
 *
 * 값은 전부 `delete_preview`가 준 `params`에서 온다. **`get_overview`의 값과 섞지 않는다** —
 * 저쪽은 *"적용할 수 있는가"*(meta ∧ 본체), 이쪽은 *"지울 것이 있는가"*(meta)라 기준이 다르고,
 * 섞으면 확인창이 실제로 지워질 것과 다른 것을 말하게 된다.
 */
export function makeDeleteConfirmSpec(
  params: DeleteConfirmParams,
  onOK: () => void,
): PlainConfirmSpec {
  const has: Record<Profile, boolean> = { dock: params.has_dock, internal: params.has_internal };
  return {
    kind: "plain",
    title: t("DELETE_CONFIRM_TITLE", { name: params.name }),
    body: (
      <div style={COLUMN_STYLE}>
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
        <div style={WARN_STYLE}>{t("MANAGE_KEEP_CONFIG")}</div>
      </div>
    ),
    okText: t("DELETE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 복원 확인 — **덮어쓰는 것은 게임 설정 파일**이라고 분명히 말한다.
 *
 * ⚠️ 백업 잔량을 숫자로 약속하지 않는다 — 링 크기는 봉투에 없고, "N칸 중"은 잔량 약속으로
 *   읽혀 오정보가 된다(P8-2 이탈 #8과 같은 판단).
 */
export function makeRestoreConfirmSpec(
  params: RestoreConfirmParams,
  onOK: () => void,
): PlainConfirmSpec {
  const fromProfile = params.kind === "profile_dock" || params.kind === "profile_internal";
  return {
    kind: "plain",
    title: t("RESTORE_CONFIRM_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("RESTORE_CONFIRM_BODY", { stamp: params.stamp_label || params.backup_id })}</div>
        <div>{t("RESTORE_CONFIRM_CURRENT", { state: diskStateText(params) })}</div>
        <div style={META_STYLE}>{t("RESTORE_CONFIRM_BACKUP")}</div>
        {/* 2단계 시맨틱 — 이 창이 끝나도 프로필 슬롯은 그대로다.
            ★ 후속 제안은 **그 백업이 어느 프로필의 대피본일 때만** 뜬다(`kind`). 그래서 문구도
              그때만 그 약속을 한다 — 조건 없는 약속은 대다수 경로(=`disk`)에서 거짓이었다. */}
        <div style={WARN_STYLE}>
          {fromProfile ? t("RESTORE_CONFIRM_SLOT_ASK") : t("RESTORE_CONFIRM_SLOT_NOTE")}
        </div>
      </div>
    ),
    okText: t("RESTORE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 복원 성공 뒤의 **후속 제안**(2단계의 ②) — 백업이 어느 프로필의 대피본인지 백엔드가 `kind`로
 * 알려줄 때만 뜬다. 취소 문구가 "건너뛰기"인 것도 그 성격 때문이다(거부가 아니라 선택).
 */
export function makeRestoreFollowUpSpec(profile: Profile, onOK: () => void): PlainConfirmSpec {
  return {
    kind: "plain",
    title: t("RESTORE_FOLLOWUP_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("RESTORE_FOLLOWUP_BODY", { profile: t(profileKey(profile)) })}</div>
      </div>
    ),
    okText: t("RESTORE_FOLLOWUP_OK"),
    cancelText: t("RESTORE_FOLLOWUP_SKIP"),
    onOK,
  };
}

/**
 * 등록 **전** 경고 재확인 — 백엔드가 `CONFIRM_REQUIRED`를 낼 때만 뜬다.
 *
 * ⚠️ 경고는 거부가 아니지만, 이 시점에 **등록은 아직 되지 않았다.** 확인해야 저장되고,
 *   취소하면 아무 일도 일어나지 않는다.
 */
export function makeDiscoverWarnSpec(
  params: AddGameConfirmParams,
  onOK: () => void,
): PlainConfirmSpec {
  return {
    kind: "plain",
    title: t("DISCOVER_WARN_TITLE", { name: params.name }),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("DISCOVER_WARN_BODY")}</div>
        {params.warnings.map((code) => (
          <div key={code} style={WARN_STYLE}>{tCode(code, "UNEXPECTED")}</div>
        ))}
      </div>
    ),
    okText: t("DISCOVER_WARN_KEEP"),
    onOK,
  };
}

/**
 * 전체 초기화 확인 — **2단 방어**(1회용 토큰 + type-to-confirm)의 화면 쪽.
 *
 * ★★ 입력 대조의 **판정은 백엔드에 있다.** `okDisabled`는 UX 보조일 뿐이고, 런타임에 무효여도
 *   (U20 ②) 사용자가 OK를 눌러 봐야 백엔드가 토큰 튜플 비교에서 막는다 — **fail-closed가
 *   프론트의 성실함이 아니라 계약에서 나온다.**
 * ★ `challenge`는 **번역하지 않는다.** 백엔드 상수를 그대로 보여주고 그대로 되돌린다 —
 *   i18n에 넣으면 화면의 단어와 백엔드 상수가 언어에 따라 갈려 입력이 영영 안 맞는다.
 * ★ `initial`은 호출부가 보존해 둔 직전 입력이다(GP#9) — TOCTOU 재질문·오조작 재오픈에서
 *   가상 키보드로 찍은 값을 다시 치게 하지 않는다.
 */
export function makeResetConfirmSpec(
  params: ResetConfirmParams,
  initial: string,
  onOK: (value: string) => void,
  onInputSnapshot?: (value: string) => void,
): InputConfirmSpec {
  return {
    kind: "input",
    title: t("RESET_CONFIRM_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        {/* 파괴 규모 고지는 **입력이 아니라 이 줄이 전담**한다 — challenge가 고정 단어라
            입력만으로는 규모를 알 수 없기 때문이다. 숫자는 백엔드가 센 값이다. */}
        <div>{t("RESET_CONFIRM_BODY", { games: params.games, profiles: params.profiles })}</div>
        <div style={META_STYLE}>{t("RESET_CONFIRM_BACKUP_KEPT")}</div>
        {/* ★ F11 ①: 표시명은 registry settings에 살아 **이 초기화에 같이 지워진다.**
            모르고 잃으면 안 되므로 미리 말한다. 0이면 줄을 그리지 않는다(기존 문법). */}
        {params.named > 0 ? <div>{t("RESET_CONFIRM_NAMES", { n: params.named })}</div> : null}
        <div style={WARN_STYLE}>{t("MANAGE_KEEP_CONFIG")}</div>
        <div>{t("RESET_CONFIRM_TYPE", { word: params.challenge })}</div>
      </div>
    ),
    okText: t("RESET_CONFIRM_OK"),
    input: { label: t("RESET_CONFIRM_FIELD_LABEL"), initial },
    okDisabled: (value) => value !== params.challenge,
    onOK,
    onInputSnapshot,
  };
}

/**
 * 프로필 표시 이름 편집 (F11 ①) — 초기화와 **같은 부품·같은 배선**이다.
 *
 * ★ 같은 패턴인 이유: Game Mode의 가상 키보드 동작이 아직 실사용 미확인(U20 ①)이라,
 *   두 입력 UI가 서로 다른 부품을 쓰면 실기에서 따로 판정하고 폴백도 따로 만들어야 한다.
 * ★ OK는 **항상 활성**이다(`okDisabled` 미지정) — 빈 입력은 오류가 아니라
 *   *"기본 이름으로 되돌리기"*다. 그래서 `bOKDisabled`의 런타임 동작에 기댈 필요조차 없다.
 * ★ `onOK`가 `(value: string)`으로 확정이라 실물 시그니처(`runRename(name: string)`)와 정합한다.
 *
 * ★★ **프리필 규칙은 이 함수 안에 있다**(2026-08-12 P12 게이트 C2): 지금 보이는 이름이
 *   **기본 이름 그대로면 빈 칸**으로, 사용자가 정한 이름이면 **그 이름을 채운 채로** 연다.
 *   빈 칸이 곧 *"기본으로 되돌리기"*라서, 기본 이름을 글자로 채워 두면 사용자가 그것을 지워야만
 *   기본으로 돌아가는 꼴이 된다(=같은 뜻을 두 방법으로 표현하게 된다).
 *   ⚠️ 이 계산을 **호출부에 맡기지 않는다**: 재료(`current`·`profile`)를 이미 여기서 받고,
 *     호출부가 계산하면 팝업 S와 TOCTOU 재오픈 경로가 각자 판단해 언젠가 갈라진다.
 *     `snapshot`(사용자가 치다 만 값)이 있으면 그것이 이긴다 — 보존이 프리필보다 우선이다.
 */
export function makeNameEditSpec(
  args: {
    profile: Profile;
    /** 지금 화면에 보이는 이름(기본이든 사용자 것이든). */
    current: string;
    /** 직전에 치다 만 값(GP#9 보존분). 있으면 프리필 규칙보다 우선한다. */
    snapshot?: string;
  },
  onOK: (value: string) => void,
  onInputSnapshot?: (value: string) => void,
): InputConfirmSpec {
  // 비웠을 때 돌아갈 **기본 이름**은 번역이 정본이다(백엔드는 이 값을 모른다).
  const fallback = tDefault(profileKey(args.profile));
  const initial = args.snapshot ?? (args.current === fallback ? "" : args.current);
  return {
    kind: "input",
    title: t("NAME_EDIT_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("NAME_EDIT_BODY", { current: args.current })}</div>
        <div style={META_STYLE}>{t("NAME_EDIT_HINT", { fallback, max: PROFILE_NAME_MAX })}</div>
        <div style={WARN_STYLE}>{t("MANAGE_NAMES_HINT")}</div>
      </div>
    ),
    okText: t("NAME_EDIT_OK"),
    input: { label: t("NAME_EDIT_FIELD_LABEL"), initial },
    onOK,
    onInputSnapshot,
  };
}
