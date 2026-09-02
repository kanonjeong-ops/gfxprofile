import type { ReactNode } from "react";
import { t, tCode, tDefault } from "./i18n";
import { BACKUP_WARN_APPLIES, PROFILE_NAME_MAX } from "./limits";
import { PATH_BREAK_STYLE, type InputConfirmSpec, type PlainConfirmSpec } from "./popup";
import type {
  AddGameConfirmParams, ApplyAllConfirmParams, ApplyConfirmParams, ConfirmParams,
  DeleteConfirmParams, EvictedRow, Profile, ResetConfirmParams, RestoreConfirmParams,
} from "./rpc";

/**
 * 확인창과 결과창의 선언(spec)을 모은다.
 *
 * spec은 표시할 내용과 동작을 렌더러에서 분리한다. 언제 어떤 spec을 띄울지는 각 호출부가 정하고,
 * 이 파일은 받은 값으로 spec을 만든다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
/* 확인창 잔글씨 — 한국어 문장의 낱말 중간 줄바꿈을 막는다. 같은 줄바꿈 판단의 설명은
   `popup.tsx`의 `KEEP_ALL_STYLE`에 있다. */
const META_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
/**
 * 경로 줄 — 낱말 보존을 걸지 않는 잔글씨다(`GamesPopup`의 같은 이름과 같은 판단).
 * 줄바꿈 규칙은 `popup.tsx`의 `PATH_BREAK_STYLE` 하나에서 온다(`wordBreak:"normal"`로 조상의
 * `keep-all`을 되돌리고, 끊을 자리가 없는 경로를 넘칠 때만 끊는다 — 사유 정본은 그쪽 주석).
 * 글자 크기는 통일하지 않는다: 확인창은 12px, `GamesPopup`은 11px이다. 갈리면 안 되는 것은
 *   줄바꿈 규칙 하나뿐이고, 크기까지 묶으면 한쪽 화면의 잔글씨가 남의 사정으로 흔들린다.
 * 소비자는 하나 — 등록 해제 확인창의 `DELETE_CONFIRM_PATH`.
 */
const PATH_STYLE = { ...META_STYLE, ...PATH_BREAK_STYLE } as const;
const WARN_STYLE = { color: "#ffb454" } as const;

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

/**
 * 「덮어쓸 내용」이 지금 어떤 상태인지를 한 줄로 — 백엔드가 준 4분류를 그대로 쓴다.
 *
 * 프론트가 분류를 합치지 않는다: `unknown`(어느 프로필과도 다름)과 `lookup_failed`(읽지 못함)는
 *   다른 사실이고 화면 문구도 다르다 — 한 값으로 접으면 문구를 고를 수 없다.
 * 저장·적용·복원 확인창이 같은 관문을 쓴다 — 같은 백엔드 값이 화면마다 다른 말로 보이면
 *   사용자는 셋을 다른 상태로 읽는다.
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
        {/* 덮어쓴 프로필의 대피본은 `disk` 백업과 한 링을 공유한다. 이 게임에 새 백업이
            계속 추가되면 오래된 대피본이 밀려날 수 있으므로, 무조건 되돌릴 수 있다고 약속하지
            않는다. */}
        <div style={WARN_STYLE}>{t("SAVE_CONFIRM_BACKUP_LIMIT", { n: BACKUP_WARN_APPLIES })}</div>
        {/* 지금 지워지는 것은 위 일반 경고가 아니라 이 줄이 이름으로 말한다 — 다른 확인창과
            같은 필드·같은 문구다. 지울 것이 없으면 그리지 않는다. */}
        {evictNote(params.evicted)}
      </div>
    ),
    okText: t("SAVE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 개별 등록 해제 확인 — 무엇을 잃는지 말하고 확정을 받는다.
 *
 * 값은 전부 `delete_preview`가 준 `params`에서 온다. `get_overview`의 값과 섞지 않는다 —
 * 저쪽은 "적용할 수 있는가"(meta ∧ 본체), 이쪽은 "지울 것이 있는가"(본체)라 기준이 다르고,
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
            문법은 "어떤 쓰기든 그 전에 백업"이다. 백업은 삭제 후에도 남는다. */}
        <div>{t("DELETE_CONFIRM_BACKUP", { n: params.backups })}</div>
        {/* 위 줄은 남는 쪽을 말한다. 대피가 링을 밀어내 사라지는 쪽은 여기서 이름으로 말한다
            (저장·적용·복원과 같은 필드·같은 문구). 없으면 그리지 않는다. */}
        {evictNote(params.evicted)}
        {/* 설정 파일 경로는 삭제 전 registry의 `config_path`에서 가져온다. unsafe-key 분기에서는
            빈 문자열이 오며, 빈 값이면 이 줄을 그리지 않는다. */}
        {params.config_path ? <div style={PATH_STYLE}>{t("DELETE_CONFIRM_PATH", { path: params.config_path })}</div> : null}
        {/* 재등록·복원 경로 예고 — 삭제는 등록을 해제하고 이 게임을 감지 제외 목록에 올리므로
            다음 감지 목록에서도 사라진다. 되돌아오는 길을 지우기 전에 말해 둔다. */}
        <div>{t("DELETE_CONFIRM_REDISCOVER")}</div>
        {/* 사용자가 가장 오해하기 쉬운 지점이라 반드시 노출한다.
            색은 회색(META)이다: 이 문장은 "게임 설정 파일 원본은 건드리지 않는다"는 안심
            정보인데, 안심 정보가 경고 옷을 입으면 화면의 위험 신호가 둘이 되고 진짜 위험
            (초기화 확인창의 `warnBlock`)의 무게가 깎인다. 키 단위 판단이라 이 키를 쓰는 두
            자리(초기화·등록 해제)를 같이 맞춘다. */}
        <div style={META_STYLE}>{t("MANAGE_KEEP_CONFIG")}</div>
      </div>
    ),
    okText: t("DELETE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 축출 고지 한 줄 — 저장·등록 해제·적용·복원이 같은 필드·같은 문구를 쓴다.
 *
 * 주어가 "적용하면"이 아니라 "진행하면"인 이유: 축출은 백업을 만드는 순간 일어나고
 *   (`store.make_backup`이 쓰기 뒤에 `prune_backups`를 부른다), 그 뒤 본 쓰기가 실패해도 이미
 *   지워진 뒤다. "적용하면"이라고 쓰면 실패 갈래에서 그 문장이 거짓이 된다.
 * 이름을 댄다: 무엇을 잃는지 말하지 않으면 사용자는 승인할 대상을 모른 채 승인한다.
 *   비어 있으면 줄 자체를 그리지 않는다.
 * 그 이름이 하나를 가리켜야 한다: 같은 초에 같은 설정 파일로 만들어진 백업 두 개는
 *   `stamp_label · filename`만으로는 같은 문자열이 된다. 그때만 구분 번호를 덧붙이고, 붙일지
 *   말지의 판정은 백엔드(`row.dup`)다 — 여기서 다시 세지 않는다.
 *   `backup_id`는 그대로 노출하지 않는다 — 사용자가 읽을 물건이 아니다.
 */
function evictNote(evicted?: EvictedRow[]) {
  if (!evicted || evicted.length === 0) return null;
  const list = evicted
    .map((row) => {
      const base = `${row.stamp_label || t("BACKUP_STAMP_UNKNOWN")} · ${row.filename}`;
      return row.dup > 0 ? `${base} ${t("BACKUP_EVICT_DUP", { n: row.dup })}` : base;
    })
    .join(" · ");
  return <div style={WARN_STYLE}>{t("BACKUP_EVICT_NOTE", { n: evicted.length, list })}</div>;
}

/**
 * 여러 게임짜리 축출 예상 — 일괄 적용·전체 초기화가 공유한다.
 *
 * 게임별 이름 대신 미리보기 시점의 예상 건수와 해당 게임 수를 말한다. 산출은 개별 확인창과
 * 같은 링 관측을 바탕으로 하지만, 실행 시점의 실패로 실제 축출은 더 적을 수 있다.
 * 0이면 그리지 않는다.
 */
function evictSummary(n: number, games: number) {
  if (!n || n <= 0) return null;
  return <div style={WARN_STYLE}>{t("BACKUP_EVICT_SUMMARY", { n, games })}</div>;
}

/**
 * 개별 적용 확인 — "이 파일에만 있는 내용이 사라질 수 있는" 갈래에서만 뜬다.
 *
 * 「유일한」이 아니다: 이 창이 떴다고 반드시 잃는 것은 아니다 — 슬롯 본체가 깨진 상태도 이
 *   갈래로 오고, 그때는 승인해도 엔진이 `PROFILE_CORRUPT`로 거부해 아무것도 안 바뀐다.
 *   계약은 "잃을 수 있으면 묻는다"이지 "물으면 잃는다"가 아니다 — 이 창의 문구를 그 전제로
 *   다시 쓰지 말 것.
 * 백엔드가 이 창을 띄울지 정한다(`confirm.apply_needs_confirm`). 프론트는 조건을 다시
 *   계산하지 않는다 — 두 곳에서 판정하면 언젠가 갈리고, 갈린 쪽이 프론트면 무방비가 된다.
 * 탈출구를 같이 준다(`APPLY_CONFIRM_SAVE_HINT`): 지금 파일을 잃고 싶지 않은 사용자에게
 *   "취소하고 저장부터"라는 길이 있다는 사실 자체가 이 창의 값어치다.
 */
export function makeApplyConfirmSpec(
  params: ApplyConfirmParams,
  profile: Profile,
  onOK: () => void,
): PlainConfirmSpec {
  const label = t(profileKey(profile));
  return {
    kind: "plain",
    title: t("APPLY_CONFIRM_TITLE", { profile: label }),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("APPLY_CONFIRM_BODY", { profile: label })}</div>
        <div>{t("APPLY_CONFIRM_CURRENT", { state: diskStateText(params) })}</div>
        {/* "백업 한 칸을 씁니다"는 대피가 실제로 일어날 때만 참이다 — 복원 확인창과 같은
            술어·같은 가드다. 같은 내용이 이미 링에 있으면 엔진은 한 칸도 안 쓰므로, 가드 없이
            그리면 링 잔량을 아끼려는 사용자에게 화면이 정반대를 말한다. 판정을 백엔드의 술어
            하나(`evacuates`)로 옮기면 갈래가 늘어도 이 줄이 따라 틀리지 않는다. */}
        {params.evacuates ? <div style={META_STYLE}>{t("APPLY_CONFIRM_KEEP")}</div> : null}
        {evictNote(params.evicted)}
        <div style={META_STYLE}>{t("APPLY_CONFIRM_SAVE_HINT", { profile: label })}</div>
      </div>
    ),
    okText: t("APPLY_CONFIRM_OK", { profile: label }),
    onOK,
  };
}

/**
 * 일괄 적용 확인 — 오발동을 막는 마찰이다.
 *
 * 다른 확인창과 같은 렌더러(`SpecConfirmModal`)를 지난다 — 취소 우선 포커스·1회 종료 빗장·
 *   닫기 1회 래퍼가 전부 거기서 온다. 이 창만 따로 그리면 그 셋을 비켜 간다.
 * 본문의 `{total}`은 미리보기 봉투가 준 값이다 — 토큰을 발급한 그 시점의 등록 수 스냅샷이라
 *   화면 숫자가 토큰이 지문 낸 대상과 같은 것을 가리킨다. 버킷 5개의 합 = 이 값이 계약이다.
 *   0인 버킷 줄은 그리지 않는다.
 * 숫자는 전부 백엔드가 센 값이고 화면은 「예상」이라고 말한다 — 실행 결과의 정본은 적용 후
 *   요약과 백엔드 로그다.
 * OK는 항상 활성이다. `running_refused`는 고지 줄에만 쓰이고 활성 조건에 들어가지 않는다 —
 *   조건이 되는 순간 "실행 중 게임이 일괄 적용을 막지 않는다"가 모달 층에서 뒤집힌다.
 */
export function makeApplyAllConfirmSpec(
  params: ApplyAllConfirmParams,
  onOK: () => void,
): PlainConfirmSpec {
  const profileName = t(profileKey(params.profile));
  // 없는 것을 0으로 나열하면 정작 중요한 숫자가 묻힌다.
  const parts = (
    [
      ["APPLY_ALL_PREVIEW_APPLY", params.would_apply],
      ["APPLY_ALL_PREVIEW_ALREADY", params.already],
      ["APPLY_ALL_PREVIEW_NO_PROFILE", params.no_profile],
      ["APPLY_ALL_PREVIEW_RUNNING", params.running_refused],
      ["APPLY_ALL_PREVIEW_CANNOT", params.cannot_apply],
    ] as const
  )
    .filter(([, n]) => n > 0)
    .map(([key, n]) => t(key, { n }));
  return {
    kind: "plain",
    title: t("APPLY_ALL_CONFIRM_TITLE", { profile: profileName }),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("APPLY_ALL_CONFIRM_BODY", { total: params.total, profile: profileName })}</div>
        {parts.length > 0 ? <div>{t("APPLY_ALL_CONFIRM_EXPECT", { list: parts.join(" · ") })}</div> : null}
        {/* 이 동작도 게임마다 백업을 만들며 오래된 백업을 밀어낸다. 게임이 여럿이라 이름 대신
            수로 말한다 — 산출은 게임 하나짜리 확인창과 같다. */}
        {evictSummary(params.evicted, params.evict_games)}
      </div>
    ),
    okText: t("APPLY_ALL_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 결과 팝업 — 새 부품을 만들지 않고 `kind:"plain"`을 쓰되 취소가 없는 spec이다.
 *
 * 왜 창인가: 결과를 목록 위 한 줄로 그리면 아래 목록 전체가 내려간다 — 방금 누른 행이 손가락
 *   아래에서 움직이는 자리다. 위치가 흔들릴 수 있는 통지는 팝업으로 뺀다.
 * 취소가 없는 이유: 되돌릴 것이 없다. 이미 끝난 일을 알리는 창에 [취소]가 있으면 "취소하면
 *   되돌려지나?"라는 없는 선택지를 만든다.
 * 중첩 깊이는 늘지 않는다 — 확인창은 `onOK`가 돌아오는 즉시 닫히고 이 창은 그 뒤에 뜬다
 *   (순차이지 중첩이 아니다).
 */
export function makeResultSpec(body: ReactNode, onOK?: () => void): PlainConfirmSpec {
  return {
    kind: "plain",
    title: t("RESULT_TITLE"),
    body: <div style={COLUMN_STYLE}>{body}</div>,
    okText: t("RESULT_OK"),
    noCancel: true,
    onOK: onOK ?? (() => {}),
  };
}

/**
 * 복원 확인 — 되돌릴 곳을 말한다. 목적지는 백엔드가 준 `target`이 정본이고, 프론트는 `kind`로
 * 다시 분류하지 않는다.
 *
 * 백업 잔량을 숫자로 약속하지 않는다 — 링 크기는 봉투에 없고, "N칸 중"은 잔량 약속으로 읽혀
 *   오정보가 된다. 실제로 지워질 것은 `evicted`가 이름으로 말한다.
 */
export function makeRestoreConfirmSpec(
  params: RestoreConfirmParams,
  onOK: () => void,
): PlainConfirmSpec {
  const stamp = params.stamp_label || params.backup_id;
  const slot = params.target === "dock" || params.target === "internal" ? params.target : null;
  if (slot) {
    const label = t(profileKey(slot));
    return {
      kind: "plain",
      title: t("RESTORE_CONFIRM_TITLE_PROFILE", { profile: label }),
      body: (
        <div style={COLUMN_STYLE}>
          <div>{t("RESTORE_CONFIRM_BODY_PROFILE", { profile: label, stamp })}</div>
          {/* 덮어쓸 대상은 그 슬롯이다 — 게임 설정 파일의 4분류를 여기 그리면 딴 것을 말한다.
              저장 시각을 모르면 그 줄을 그리지 않는다. */}
          {params.saved_at ? (
            <div>{t("RESTORE_CONFIRM_CURRENT_PROFILE", { profile: label, saved_at: params.saved_at })}</div>
          ) : null}
          {/* 대피가 불가능한 상태는 그 사실을 먼저 말한다 — 고지하고 묻지, 모른다고 막지 않는다. */}
          {params.slot_unreadable ? (
            <div style={WARN_STYLE}>{t("RESTORE_CONFIRM_SLOT_UNREADABLE")}</div>
          ) : null}
          {/* "백업 한 칸을 씁니다"는 대피가 실제로 일어날 때만 참이다. 판정을 백엔드의 술어
              하나(`evacuates` = 엔진의 대피 조건)로 옮기면 갈래가 늘어도 이 줄이 따라 틀리지
              않는다 — 대피가 없는 갈래(기록만 있고 실물이 없는 슬롯 등)까지 한 자리에서
              걸러진다. */}
          {params.evacuates ? <div style={META_STYLE}>{t("RESTORE_CONFIRM_BACKUP")}</div> : null}
          {evictNote(params.evicted)}
          {/* 게임 설정 파일은 안 바뀐다는 사실 + 그래서 뒤에 무엇을 묻는지. */}
          <div style={WARN_STYLE}>{t("RESTORE_CONFIRM_SLOT_ASK")}</div>
        </div>
      ),
      okText: t("RESTORE_CONFIRM_OK"),
      onOK,
    };
  }
  return {
    kind: "plain",
    title: t("RESTORE_CONFIRM_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        <div>{t("RESTORE_CONFIRM_BODY", { stamp })}</div>
        <div>{t("RESTORE_CONFIRM_CURRENT", { state: diskStateText(params) })}</div>
        {/* 슬롯 갈래와 같은 술어를 쓴다 — 조건을 자리마다 다시 세우지 않는 것이 규칙이다. */}
        {params.evacuates ? <div style={META_STYLE}>{t("RESTORE_CONFIRM_BACKUP")}</div> : null}
        {evictNote(params.evicted)}
        {/* 저장해 둔 프로필은 그대로다 — `disk`·`unknown` 행에서는 후속 제안도 없다. */}
        <div style={WARN_STYLE}>{t("RESTORE_CONFIRM_SLOT_NOTE")}</div>
      </div>
    ),
    okText: t("RESTORE_CONFIRM_OK"),
    onOK,
  };
}

/**
 * 프로필 슬롯 복원 뒤의 후속 제안 — "게임에도 지금 적용할까요?"
 *
 * 취소 문구가 "건너뛰기"인 것은 그 성격 때문이다(거부가 아니라 선택) — 취소해도 슬롯 복원은
 *   남는다. 사용자가 원한 일은 이미 됐다.
 * 여기서 OK를 눌러도 적용 경로가 다시 물을 수 있다 — 확인창 하나로 손실 둘을 승인받지 않는다.
 */
export function makeRestoreFollowUpSpec(
  profile: Profile,
  stamp: string,
  onOK: () => void,
): PlainConfirmSpec {
  const label = t(profileKey(profile));
  return {
    kind: "plain",
    title: t("RESTORE_FOLLOWUP_TITLE"),
    body: (
      <div style={COLUMN_STYLE}>
        {/* 끝난 일을 먼저 말한다: 이 창은 제안이지만, 사용자가 방금 누른 복원의 결과를 여기서
            확인하지 못하면 그 동작은 어디에서도 보고되지 않는다. */}
        <div>{t("RESTORE_OK_PROFILE", { profile: label, stamp })}</div>
        <div>{t("RESTORE_FOLLOWUP_BODY", { profile: label })}</div>
      </div>
    ),
    okText: t("RESTORE_FOLLOWUP_OK"),
    cancelText: t("RESTORE_FOLLOWUP_SKIP"),
    onOK,
  };
}

/**
 * 등록 전 경고 재확인 — 백엔드가 `CONFIRM_REQUIRED`를 낼 때만 뜬다.
 *
 * 경고는 거부가 아니지만, 이 시점에 등록은 아직 되지 않았다. 확인해야 저장되고, 취소하면
 *   아무 일도 일어나지 않는다.
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
 * 전체 초기화 확인 — 2단 방어(1회용 토큰 + type-to-confirm)의 화면 쪽.
 *
 * 입력 대조의 판정은 백엔드에 있다. `okDisabled`는 UX 보조일 뿐이고, 그것이 무효여도 사용자가
 *   OK를 눌러 봐야 백엔드가 토큰 튜플 비교에서 막는다 — fail-closed가 프론트의 성실함이 아니라
 *   계약에서 나온다.
 * `challenge`는 번역하지 않는다. 백엔드 상수를 그대로 보여주고 그대로 되돌린다 — i18n에 넣으면
 *   화면의 단어와 백엔드 상수가 언어에 따라 갈려 입력이 영영 안 맞는다.
 * `initial`은 호출부가 보존해 둔 직전 입력이다 — 재질문·재오픈에서 가상 키보드로 찍은 값을
 *   다시 치게 하지 않는다.
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
    /* 이 파일에서 `warnBlock`을 쓰는 확인창은 이것 하나다 — 렌더러가 이 블록만 따로 위험색으로
       그린다.
       "백업은 남습니다"만으로는 거짓에 가깝다 — 남은 백업을 쓰려면 그 게임을 다시 등록해야
       하고, 그 전제를 안 적으면 사용자는 "언제든 되살릴 수 있다"로 읽는다. 재등록이 가능한
       근거는 초기화가 감지 제외 목록까지 지운다는 사실이다. */
    warnBlock: <div>{t("RESET_CONFIRM_WARN", { games: params.games, profiles: params.profiles })}</div>,
    body: (
      <div style={COLUMN_STYLE}>
        {/* 파괴 규모 고지는 위 warnBlock이 전담한다 — `challenge`가 고정 단어라 입력만으로는
            규모를 알 수 없으므로 고지 자체는 반드시 있어야 하지만, 한 번만 있어야 한다. 같은
            사실을 두 톤으로 두 번 말하면 어느 쪽이 정본인지 화면이 답하지 못한다. 숫자의
            출처도 warnBlock 하나다. */}
        {/* 표시명은 registry settings에 살아 이 초기화에 같이 지워진다. 모르고 잃으면 안 되므로
            미리 말한다. 0이면 줄을 그리지 않는다. */}
        {params.named > 0 ? <div>{t("RESET_CONFIRM_NAMES", { n: params.named })}</div> : null}
        {/* 초기화는 registry를 통째로 갈아 끼우므로 감지 제외 목록도 같이 지워진다. 그 사실이
            위 warnBlock의 "다시 등록해서 복원한다"를 참으로 만드는 근거이기도 하다. */}
        {params.excluded > 0 ? <div>{t("RESET_CONFIRM_EXCLUDED", { n: params.excluded })}</div> : null}
        {/* 초기화도 백업을 만들며 지운다: 게임마다 슬롯 본체를 대피시키므로 링이 찬 게임에서는
            가장 오래된 백업이 밀려난다. warnBlock이 "백업은 남습니다"라고 말하는 바로 그 창이라,
            사라지는 몫을 말하지 않으면 그 문장이 조건부로 거짓이 된다. */}
        {evictSummary(params.evicted, params.evict_games)}
        {/* 회색(META) — 등록 해제 확인창의 같은 키와 같은 이유·같은 판단이다. */}
        <div style={META_STYLE}>{t("MANAGE_KEEP_CONFIG")}</div>
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
 * 프로필 표시 이름 편집 — 전체 초기화와 같은 입력 spec 렌더러를 쓴다.
 *
 * OK는 항상 활성이다. 빈 입력은 오류가 아니라 기본 이름으로 되돌리기다.
 *
 * 프리필 규칙은 이 함수 안에 있다: 지금 보이는 이름이 기본 이름이면 빈 칸으로, 사용자 이름이면
 * 그 이름으로 연다. `snapshot`이 있으면 프리필보다 우선한다.
 */
export function makeNameEditSpec(
  args: {
    profile: Profile;
    /** 지금 화면에 보이는 이름(기본이든 사용자 것이든). */
    current: string;
    /** 직전에 치다 만 값. 있으면 프리필 규칙보다 우선한다. */
    snapshot?: string;
  },
  onOK: (value: string) => void,
  onInputSnapshot?: (value: string) => void,
): InputConfirmSpec {
  // 비웠을 때 돌아갈 기본 이름은 번역이 정본이다 — 백엔드는 이 값을 모른다.
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
