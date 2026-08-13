import { useCallback, useState, type ReactNode } from "react";
import {
  makeDeleteConfirmSpec, makeRestoreConfirmSpec, makeRestoreFollowUpSpec, makeSaveConfirmSpec,
} from "./confirmSpecs";
import { Focusable, ToggleField } from "./deckyui";
import {
  IconBolt, IconCheck, IconChevron, IconChip, IconList, IconRefresh, IconRestore, IconSave, IconTrash,
} from "./icons";
import { t, tCode } from "./i18n";
import {
  CARD_INNER_STYLE, CARD_STYLE, GfxPopup, ICON_SLOT_STYLE, PopupButton, PopupScrollList,
  PopupSubView, STACKED_BUTTON_STYLE, STACKED_DESC_PAD, listRowNavProps, subViewKey,
  usePopupData, usePopupGate, type GView,
} from "./popup";
import { slotSummary } from "./slots";
import {
  applyProfile, deleteGame, getOverview, listBackups, restoreBackup, saveProfile,
  type BackupRow, type ConfirmParams, type DeleteConfirmParams, type Overview, type OverviewGame,
  type Profile, type RestoreConfirmParams,
} from "./rpc";

/**
 * **팝업 G — 게임별 적용/저장** (설계 §5).
 *
 * 뷰 셋이 한 팝업 안에 있다: 목록 → 게임 상세(›) → 백업 목록. 사라진 전체 화면의
 * 「현황」·「관리」 두 탭이 하던 일을 전부 여기로 모은 것이다(§12 이식 맵).
 *
 * ★★ **왜 한 팝업 안의 뷰인가**(모달을 새로 띄우지 않고): 상세·백업은 *"지금 보고 있는 그
 *   게임"*의 하위 화면이라 맥락이 이어져야 한다. 모달을 겹치면 중첩 깊이가 2를 넘고, 그때
 *   B 버튼이 무엇을 닫는지 사용자도 우리도 예측할 수 없게 된다(§4-C 중첩 깊이 불변식 ≤1 —
 *   확인창 한 겹만 위에 뜬다).
 *
 * ★ 판정은 **전부 백엔드에 있다.** 이 화면은 무엇이 적용 가능한지·덮어쓰기인지·어느 백업이
 *   어느 종류인지를 다시 계산하지 않는다. 프론트가 하는 일은 `CONFIRM_REQUIRED`를 받으면
 *   **받은 토큰을 그대로 되돌려 주는 것**뿐이다.
 *
 * ★ P15-C에서 QAM 진입 버튼에 배선됐다. 그 전에도 tsc·i18n 집합 검사·프로브는 돌고
 *   있었다 — 배선이 없다고 검사까지 미루면 배선하는 날 한꺼번에 터지기 때문이다.
 */

// ── 스타일 (한 곳에 모은다 — 카드가 세 뷰에서 같은 모양이어야 한다) ──────────
const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const META_STYLE = { fontSize: "11px", color: "#9aa0a6" } as const;
/**
 * 동작 버튼 아래 설명 줄 — 들여쓰기가 버튼의 가로 패딩과 같아 **라벨과 축을 공유**한다(§4-G 3항).
 * 이 상수는 `ActionButton`의 desc 전용이다(다른 설명 줄과 섞어 쓰지 말 것 — 축 공유가 깨진다).
 */
const DESC_STYLE = {
  fontSize: "11px", color: "#9aa0a6", margin: "2px 0 6px", paddingLeft: STACKED_DESC_PAD,
} as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;

/* 카드(§5-A)의 두 상수는 **`popup.tsx`에 있다** — 팝업 D의 후보 행과 같은 모양이어야 하고,
   값이 두 곳에 있으면 한쪽만 손대는 날 같은 목록이 화면마다 달라진다(P14 공용화). */

const ROW_STYLE = { display: "flex", alignItems: "center", gap: "6px" } as const;
const NAME_STYLE = { flex: "1 1 auto", minWidth: 0, fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis" } as const;

/**
 * 적용 버튼 2종의 **공통 폭**(GP#2). 두 버튼이 같은 `minWidth`를 갖고, 아래 두 아이콘 자리도
 * 마커 유무와 무관하게 같은 폭이라 **전 행의 버튼 x좌표가 같다** — 수직 이동 중 커서가 좌우로
 * 튀지 않는다(`MAINTAIN_X`와 2중 방어).
 */
const APPLY_BUTTON_STYLE = {
  minWidth: "110px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto",
} as const;

/**
 * 라벨 뒤 **마커 자리 — 상시 예약**(GP#2). 마커가 없어도 같은 폭의 빈 자리를 그린다.
 * 조건부로 자리 자체를 없애면 그 행만 버튼이 좁아져 열이 어긋난다.
 */
const MARKER_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginLeft: "4px",
} as const;

/** "현재 적용됨" 강조 배경(A7). 폭에 영향을 주지 않는 속성만 쓴다. */
const MARKED_BACKGROUND = "rgba(126,204,255,0.22)";

const CHEVRON_BUTTON_STYLE = { minWidth: "40px", padding: "6px 4px", flex: "0 0 auto" } as const;
/** 상세 뷰의 동작 버튼 4종 — **세로 스택**이라 §4-G 3항의 좌측 정렬 축을 쓴다. */
const ACTION_BUTTON_STYLE = {
  minWidth: "220px", padding: "6px 10px", fontSize: "13px", ...STACKED_BUTTON_STYLE,
} as const;
const CHIP_STYLE = {
  fontSize: "11px", background: "rgba(255,255,255,0.12)", borderRadius: "3px",
  padding: "1px 6px", marginLeft: "6px",
} as const;

/** 등록 해제를 목록 동작과 시각적으로 가른다(M12·GP#13) — 파괴는 "다음 항목"처럼 읽히면 안 된다. */
const DIVIDER_STYLE = { borderTop: "1px solid #3a3f44", marginTop: "12px", paddingTop: "12px" } as const;

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

function profileIcon(p: Profile) {
  if (p === "dock") return <IconBolt />;
  return <IconChip />;
}

/**
 * `running`을 읽는 **이 파일의 유일한 문**(E1 — `build.sh` grep ③ 계약).
 *
 * ★★ 왜 함수 하나로 모으는가: 값을 읽는 자리가 흩어지면 언젠가 한 자리가 **활성 조건**으로
 *   새어 들어간다("실행 중이면 버튼 비활성"). 그건 판정을 화면이 하는 것이고, E1이 막는 바로
 *   그 형태다 — 판정은 백엔드가 하고 **화면은 사실 표시만** 한다. 문을 하나 두면 새어 나갈
 *   자리 자체가 없다.
 */
// e1-display-only
const isRunning = (game: OverviewGame) => game.running;

/** 실행 중 칩 — 표시 전용. 적용 버튼은 이것으로 비활성화되지 않는다(§5-D). */
function RunningChip({ game }: { game: OverviewGame }) {
  if (!isRunning(game)) return null;
  return <span style={CHIP_STYLE}>{t("RUNNING_CHIP")}</span>;
}

/** 백업 종류 문구 — **판정은 백엔드의 `kind` 코드**이고 화면은 문구만 고른다. */
function kindText(row: BackupRow): string {
  if (row.kind === "profile_dock" || row.kind === "profile_internal") {
    return t("BACKUP_KIND_PROFILE", {
      profile: t(row.kind === "profile_dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL"),
    });
  }
  if (row.kind === "disk") return t("BACKUP_KIND_DISK");
  return t("BACKUP_KIND_UNKNOWN");
}

/** 목록 행 하나(§5-A). 게임명 + [eGPU 적용][내장 적용][›] + 메타 한 줄. */
function GameCard({
  game,
  busy,
  focused,
  onApply,
  onOpen,
}: {
  game: OverviewGame;
  busy: boolean;
  /** 이 행에 착지시킬 것인가(§4-E ① — 목록 복귀 시 마지막 조작 행). */
  focused: boolean;
  onApply: (game: OverviewGame, profile: Profile) => void;
  onOpen: (game: OverviewGame) => void;
}) {
  const has: Record<Profile, boolean> = { dock: game.has_dock, internal: game.has_internal };
  return (
    <Focusable {...listRowNavProps} preferredFocus={focused} style={CARD_STYLE}>
      <div style={CARD_INNER_STYLE}>
        <div style={ROW_STYLE}>
          <div style={NAME_STYLE}>{game.name}</div>
          {(["dock", "internal"] as const).map((p) => (
            <PopupButton
              key={p}
              /* 비활성 조건은 **그 프로필이 없을 때**뿐이다(A6의 유일한 시각 표현).
                 실행 중 여부는 여기 들어가지 않는다 — 누르면 백엔드가 거부하고 사유가 note로 뜬다. */
              disabled={busy || !has[p]}
              onClick={() => onApply(game, p)}
              style={{
                ...APPLY_BUTTON_STYLE,
                background: game.disk_matches === p ? MARKED_BACKGROUND : undefined,
              }}
            >
              <span style={ICON_SLOT_STYLE}>{profileIcon(p)}</span>
              {t("APPLY_SHORT", { profile: t(profileKey(p)) })}
              {/* ★ 마커 자리는 **항상** 있다 — 없을 땐 같은 폭의 빈 자리다(GP#2).
                  마커가 있어도 누를 수 있다: 재적용은 백엔드에서 `already`로 무해하다. */}
              <span style={MARKER_SLOT_STYLE}>{game.disk_matches === p ? <IconCheck /> : null}</span>
            </PopupButton>
          ))}
          {/* ★ 톱니가 아니라 chevron이다(H4) — 톱니는 전역 [설정] 전용이라 여기 쓰면
              "이 게임의 설정"으로 읽혀 두 개념이 섞인다. */}
          <PopupButton disabled={busy} onClick={() => onOpen(game)} style={CHEVRON_BUTTON_STYLE}>
            <IconChevron />
          </PopupButton>
        </div>
        <div style={META_STYLE}>
          {/* 문장은 `slots.ts` 한 곳에서 만든다 — 목록과 상세가 같은 말을 해야 한다(F5). */}
          {slotSummary(game)}
          <RunningChip game={game} />
        </div>
      </div>
    </Focusable>
  );
}

/** 동작 버튼 + 그 아래 한 줄 설명(F10 자기 설명). 설명이 없으면 자리도 만들지 않는다. */
function ActionButton({
  label,
  desc,
  icon,
  disabled,
  onClick,
}: {
  label: string;
  desc?: string;
  icon: ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <div>
      <PopupButton disabled={disabled} onClick={onClick} style={ACTION_BUTTON_STYLE}>
        <span style={ICON_SLOT_STYLE}>{icon}</span>
        {label}
      </PopupButton>
      {desc ? <div style={DESC_STYLE}>{desc}</div> : null}
    </div>
  );
}

export function GamesPopup({
  onMutate,
  closeModal,
}: {
  /**
   * 변이를 QAM에 알린다(§4-F ③ 개정 — 확정 실행이면 **성공·실패를 가리지 않는다**: 엔진은
   * 쓴 뒤에 거부할 수 있다). 화면 갱신은 **이 팝업이 스스로** 한다 — 다른 일이다.
   */
  onMutate?: () => void;
  /** `showModal`이 최상위 엘리먼트에 주입한다. */
  closeModal?: () => void;
}) {
  const [view, setView] = useState<GView>({ kind: "list" });
  const [noProfileOnly, setNoProfileOnly] = useState(false);
  /**
   * 마지막으로 조작한 행(§4-B) — 목록으로 돌아올 때 그 행에 착지시켜 **스크롤 위치가
   * 복원되게** 한다(포커스 추종). 목록 자체는 리마운트하지 않으므로(GP#3) 이 값만 있으면 된다.
   */
  const [lastRow, setLastRow] = useState<string | null>(null);
  const [backups, setBackups] = useState<BackupRow[] | null>(null);

  const load = useCallback(() => getOverview(true), []);
  /* ★ 변이 통지·재조회·busy는 **훅 한 곳**을 지난다(§4-F 개정) — 이 파일에는 그 배선이 없다. */
  const { data, noteText, setNote, setReloadNote, noteView, busy, reload, runMutation, runQuery } =
    usePopupData<Overview>(load, "LOAD_FAILED", onMutate);
  const { gate, renderBody } = usePopupGate();

  const games = data?.games ?? [];
  const counts = data?.counts;

  /**
   * 백업 뷰의 목록을 **다시 읽는다**(D-07 ⓐ). 실패해도 화면은 남는다 — 둘째 줄이 말한다.
   *
   * ★★ 실패 사유를 `setNote`로 쓰면 **방금 한 동작의 결과를 덮는다**(P15-E R4의 같은 사고):
   *   복원은 성공했는데 목록 재조회가 실패하면 *"이 내용은 지금 게임 설정 파일에만 있습니다 —
   *   계속 쓰려면 프로필로 저장하십시오"*라는 **후속 조치 안내가 통째로 사라졌다.**
   *   두 사실은 서로 다르고 둘 다 참이라, 자리를 갈라 둘 다 말한다.
   */
  const refreshBackups = useCallback(
    (appid: string) => {
      // 읽기 전용이다 — busy만 같이 쓰고 재조회·통지는 붙지 않는다.
      void runQuery(() => listBackups(appid), "BACKUP_LIST_FAILED", (res) => {
        if (res.ok) {
          setBackups(res.data.backups);
          setReloadNote(null);
          return;
        }
        setReloadNote(tCode(res.code, "BACKUP_LIST_FAILED"));
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /**
   * 적용 — **확인창 없이 즉시**다(사용자 확정: 가장 자주 누르는 버튼이라 순수 마찰이다).
   *
   * ★ 성공·실패 **양쪽에서** 체크인을 병기한다(§5-E): 엔진은 체크인을 쓴 **뒤에** 백업·쓰기
   *   실패로 거부할 수 있어, *"적용은 실패했는데 프로필은 이미 바뀐"* 상태가 실재한다.
   *   성공 경로에만 붙이면 화면이 그 상태에 침묵한다.
   */
  const runApply = useCallback(
    (game: OverviewGame, profile: Profile) => {
      // 확정 실행이다 — 재조회·변경 통지는 **성공·실패를 가리지 않고** 훅이 붙인다(§4-F ③).
      // 체크인만 일어난 실패가 정확히 그 이유다: 디스크·백업이 이미 바뀌었을 수 있다.
      void runMutation(() => applyProfile(game.appid, profile), "APPLY_FAILED", (res) => {
        const checkedIn = res.ok
          ? res.data.checked_in
          : ((res.params as unknown as { checked_in?: Profile | null }).checked_in ?? null);
        const base = res.ok
          ? t("APPLY_ONE_OK", { profile: t(profileKey(profile)) })
          : tCode(res.code, "APPLY_FAILED");
        setNote(checkedIn ? `${base} ${t("CHECKIN_ONE", { profile: t(profileKey(checkedIn)) })}` : base);
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /**
   * 저장 — 덮어쓰기라 **백엔드가 확인을 요구할 수 있다.** 빈 슬롯 첫 저장은 묻지 않는다
   * (잃을 것이 없다 — §15-C 정상 동작).
   *
   * ★ 실행 중 저장은 **거부가 아니라 경고**다(engine.py:452-455). 봉투의 `warning`을 성공
   *   note에 병기한다 — 저장은 됐지만 값이 게임 종료 시 달라질 수 있다는 사실이다.
   */
  const runSave = useCallback(
    (appid: string, profile: Profile, token?: string) =>
      runMutation(() => saveProfile(appid, profile, token), "SAVE_FAILED", (res) => {
        if (res.ok) {
          const ok = t("SAVE_OK", { profile: t(profileKey(profile)) });
          setNote(res.data.warning ? `${ok} ${res.data.warning}` : ok);
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ConfirmParams;
          gate(
            makeSaveConfirmSpec(p, profile, () => { void runSave(appid, profile, p.confirm_token); }),
            // 토큰이 안 돌아가면 저장은 일어나지 않는다 — "저장하지 않았습니다"가 참이다.
            "SAVE_CONFIRM_MODAL_FAILED",
            setNote,
          );
          return;
        }
        setNote(tCode(res.code, "SAVE_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate],
  );

  /**
   * 복원 — 3-상태 계약(§15-C 불변): `already`는 무쓰기 · 설정 파일이 없으면 무토큰 즉시 ·
   * 그 외는 `CONFIRM_REQUIRED`.
   *
   * ★★ **성공 뒤 재조회**(D-07): 복원은 disk 대피본을 하나 새로 만든다(`engine.py:705-709`) —
   *   백업 목록의 행 수·순서가 그 자리에서 바뀌고, 링이 차 있으면 가장 오래된 행이 사라진다.
   *   화면을 그대로 두면 **방금 사라진 백업의 [복원] 버튼**이 남는다. 그래서 백업 목록을
   *   여기서 다시 읽고(overview 재조회·통지는 훅이 붙인다).
   * ★ `already`도 **확정 실행의 응답**이라 overview 재조회·통지가 따라온다(§4-F ③ 개정):
   *   무쓰기 여부를 프론트가 outcome으로 다시 판정하면, 그 판정이 백엔드와 갈리는 날 화면만
   *   낡는다. 백업 목록은 링이 안 밀렸으므로 여기서 다시 읽지 않는다.
   */
  const runRestore = useCallback(
    (game: OverviewGame, row: BackupRow, token?: string) =>
      runMutation(() => restoreBackup(game.appid, row.backup_id, token), "RESTORE_FAILED", (res) => {
        if (res.ok) {
          if (res.data.outcome === "already") {
            // 실패가 아니다 — 되돌릴 것이 없었다는 뜻이고, 쓰기도 링 소모도 0이다.
            setNote(t("RESTORE_ALREADY"));
            return;
          }
          const stamp = res.data.stamp_label || res.data.backup_id;
          setNote(t("RESTORE_OK", { stamp }));
          refreshBackups(game.appid);
          const kind = res.data.kind;
          if (kind === "profile_dock" || kind === "profile_internal") {
            const profile: Profile = kind === "profile_dock" ? "dock" : "internal";
            gate(
              makeRestoreFollowUpSpec(profile, () => { void runSave(game.appid, profile); }),
              // ★ 여기서는 **복원이 이미 끝났다.** "아무것도 안 했다"고 말하면 거짓이다 —
              //   못 한 것은 후속 제안뿐이고, 그 문구가 남은 길을 알려 준다.
              "RESTORE_FOLLOWUP_MODAL_FAILED",
              setNote,
            );
            return;
          }
          // `disk`·`unknown`은 어느 슬롯의 내용인지 추론할 근거가 없다 — 안내만 한다.
          setNote(t("RESTORE_OK_MANUAL", { stamp }));
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as RestoreConfirmParams;
          gate(
            makeRestoreConfirmSpec(p, () => { void runRestore(game, row, p.confirm_token); }),
            "RESTORE_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // GAME_RUNNING(조기 거부)·BACKUP_FILE_MISSING(그 사이 prune) 등 — tCode 단일 관문.
        setNote(tCode(res.code, "RESTORE_FAILED"));
        refreshBackups(game.appid);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, refreshBackups, runSave],
  );

  /**
   * 등록 해제 = **등록 말소 + 감지 제외**(A9). 성공하면 목록으로 돌아가고, 사라진 행 대신
   * **인접 행**에 착지시킨다(§4-B) — 방금 지운 자리에 포커스를 두면 어디로 갔는지 알 수 없다.
   */
  const runDelete = useCallback(
    (appid: string, token?: string) =>
      runMutation(() => deleteGame(appid, token), "DELETE_ACTION_FAILED", (res) => {
        if (res.ok) {
          setNote(t("DELETE_OK", { name: res.data.name }));
          setView({ kind: "list" });
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          // ⚠️ 흐름 신호다 — 오류 문구로 그리지 않는다. TOCTOU면 갱신된 params로 다시 묻는다.
          const p = res.params as unknown as DeleteConfirmParams;
          gate(
            makeDeleteConfirmSpec(p, () => { void runDelete(appid, p.confirm_token); }),
            // 토큰이 없으면 아무것도 지워지지 않는다 — 이 문구가 참인 유이한 자리(+초기화).
            "MANAGE_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // `DELETE_FAILED`(부분 삭제)도 여기로 온다 — 다시 해제하면 남은 것부터 이어서 지운다.
        // 그 갈래는 **일부가 이미 지워진** 변이라, 재조회·통지가 성공과 같이 따라온다(§4-F ③).
        setNote(tCode(res.code, "DELETE_ACTION_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate],
  );

  /** 백업 뷰로 — 목록을 **먼저 받아** 연다(빈 창이 떴다가 채워지는 중간 상태를 만들지 않는다). */
  const openBackups = useCallback(
    (game: OverviewGame) =>
      runQuery(() => listBackups(game.appid), "BACKUP_LIST_FAILED", (res) => {
        if (!res.ok) {
          setNote(tCode(res.code, "BACKUP_LIST_FAILED"));
          return;
        }
        setBackups(res.data.backups);
        setView({ kind: "backups", appid: game.appid });
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /** 등록 해제 뒤 착지할 **인접 행**(다음 항목, 없으면 이전). 목록이 비면 null이다. */
  function neighbourOf(appid: string): string | null {
    const index = shown.findIndex((g) => g.appid === appid);
    if (index < 0) return null;
    const next = shown[index + 1] || shown[index - 1];
    return next ? next.appid : null;
  }

  // ── 목록 뷰 (§5-A) ─────────────────────────────────────────────────────────
  //
  // 정렬은 **이름순 단일**이다(초판 유지). "덜 된 것을 위로" 같은 재정렬은 화면이 바뀔 때마다
  // 행이 이동해 근육 기억이 무너진다 — 순서 안정성을 택한다.
  const sorted = [...games].sort((a, b) => a.name.localeCompare(b.name));
  // 필터 술어는 **구 「현황」 화면에서 그대로 승계**한 것이다(R-9): 두 프로필 중 **하나라도 없음**.
  const shown = noProfileOnly ? sorted.filter((g) => !g.has_dock || !g.has_internal) : sorted;

  function renderList() {
    return (
      <div style={COLUMN_STYLE}>
        <Focusable style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <ToggleField
              label={t("FILTER_NO_PROFILE_ONLY")}
              checked={noProfileOnly}
              onChange={setNoProfileOnly}
            />
          </div>
          {/* ★ F17: "게임을 끄고 왔는데 화면이 낡았을 수 있다"의 탈출구. 초기 포커스가 첫 카드라
              이 줄이 통행세가 되지 않는다(GP#6). */}
          <PopupButton
            disabled={busy}
            onClick={() => reload()}
            style={{ minWidth: "120px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
          >
            <span style={ICON_SLOT_STYLE}><IconRefresh /></span>
            {t("REFRESH")}
          </PopupButton>
        </Focusable>

        {noteView}

        <PopupScrollList>
          {shown.map((game, index) => (
            <GameCard
              key={game.appid}
              game={game}
              busy={busy}
              focused={lastRow ? game.appid === lastRow : index === 0}
              onApply={runApply}
              onOpen={(g) => { setLastRow(g.appid); setView({ kind: "detail", appid: g.appid }); }}
            />
          ))}
        </PopupScrollList>

        {/* ★ 「모르는 것을 없다고 말하지 않는다」 — data가 null인 것은 로딩 중이거나 조회
            실패이지 0개가 아니다. 실패 문구는 위 note가 이미 그린다. */}
        {renderListTail()}

        {/* ★ U-8: 제외된 게임이 있을 때만 한 줄. 0건이면 완전 미표시다(A6 간결·"0이면 안 그림").
            ★★ **수를 말하지 않는다**(2026-08-12 P16 게이트 C1): 표시 조건에 쓰는 `counts.excluded`는
              **원본 키 수**(raw)이고, 이 안내가 가리키는 제외 뷰는 **손상 항목을 격리한 뒤의 rows**를
              보여 준다(설계 §15-D E5). 조건에 raw를 쓰는 것은 옳지만(A9 ④ 도달성), 같은 수를
              *"거기서 볼 수 있습니다"*라는 약속에 재사용하면 그 약속이 어긋난다.
              수를 아예 안 말하면 **어긋날 자리가 소멸한다** — 문구에 자리표시자가 없다. */}
        {counts && counts.excluded > 0 ? (
          <div style={META_STYLE}>{t("GAMES_EXCLUDED_NOTE")}</div>
        ) : null}
      </div>
    );
  }

  /**
   * 목록이 비었을 때의 한 줄 — **왜 비었는지가 세 갈래**다(P15-E R3).
   *
   * ★★ 예전에는 필터를 적용한 뒤의 `shown.length`만 보고 언제나 "등록된 게임이 없습니다 —
   *   [게임 감지]에서 추가할 수 있습니다"라고 말했다. 그런데 **필터가 전부 걸러낸 상태**는
   *   정상 운용의 종착점이다(모든 게임이 두 프로필을 다 가진 상태) — 그 화면에서 등록이 0이라
   *   말하는 것은 **거짓**이고, 처방(게임 감지로 가라)까지 틀린다. 실제로 할 일은 필터를 끄는
   *   것뿐이다. 그래서 **원본 0**과 **필터 0**을 가른다.
   */
  function renderListTail() {
    if (data === null) {
      if (noteText) return null;
      return <div style={HINT_STYLE}>{t("LOADING")}</div>;
    }
    if (shown.length > 0) return null;
    // 등록 자체가 0 — 여기서만 "추가하러 가라"가 참이다.
    if (sorted.length === 0) return <div style={HINT_STYLE}>{t("NO_GAMES")}</div>;
    return <div style={HINT_STYLE}>{t("FILTER_ALL_HAVE_PROFILES")}</div>;
  }

  // ── 게임 상세 뷰 (§5-B) ────────────────────────────────────────────────────
  function statusLine(game: OverviewGame) {
    if (game.disk_matches === "dock" || game.disk_matches === "internal") {
      return t("GAME_DETAIL_STATUS", { profile: t(profileKey(game.disk_matches)) });
    }
    // 프로필이 하나도 없으면 줄 자체를 그리지 않는다(A6 — 없는 것을 지적하지 않는다).
    if (!game.has_dock && !game.has_internal) return "";
    // 게임에서 방금 조정한 직후가 이 상태다 — 저장 버튼의 존재 이유를 화면이 스스로 설명한다.
    return t("GAME_DETAIL_DIVERGED");
  }

  function renderDetail(game: OverviewGame) {
    const status = statusLine(game);
    const saveDesc = isRunning(game) ? t("SAVE_DESC_RUNNING") : t("SAVE_DESC");
    return (
      <div style={COLUMN_STYLE}>
        {/* 게임명을 고정 맥락으로 둔다 — 여기서는 **다른 게임을 건드릴 방법이 없다.** */}
        <div style={{ fontSize: "16px", fontWeight: "bold" }}>{game.name}</div>
        {status ? <div style={{ fontSize: "13px" }}>{status}</div> : null}
        <div style={META_STYLE}>
          {slotSummary(game)}
          <RunningChip game={game} />
        </div>
        {/* ★ H3-ⓑ: 같은 상태를 두 슬롯에 저장한 온보딩 함정 — 전환해도 아무 변화가 없어
            "고장"으로 읽힌다. 판정은 백엔드(meta sha 대조)이고 화면은 사실만 말한다. */}
        {game.profiles_identical ? <div style={HINT_STYLE}>{t("PROFILES_IDENTICAL")}</div> : null}
        {/* 경로가 정상 상태가 아니면 백엔드가 빈 문자열을 준다 — 그때는 줄을 그리지 않는다. */}
        {game.config_path ? <div style={META_STYLE}>{t("GAME_CONFIG_PATH", { path: game.config_path })}</div> : null}
        {/* ★ H3-ⓐ: 게임별 재촉이 아니라 **조작 방법 설명**이다(F10 성격 — A6와 무관). */}
        <div style={HINT_STYLE}>
          {t("SAVE_GUIDE", { dock: t("PROFILE_DOCK"), internal: t("PROFILE_INTERNAL") })}
        </div>

        {(["dock", "internal"] as const).map((p) => (
          <ActionButton
            key={p}
            label={t("SAVE_SHORT", { profile: t(profileKey(p)) })}
            desc={saveDesc}
            icon={<IconSave />}
            /* 저장은 **빈 슬롯에도** 눌러야 한다 — 프로필을 처음 만드는 동작이 이것이다. */
            disabled={busy}
            onClick={() => { void runSave(game.appid, p); }}
          />
        ))}

        <ActionButton
          label={t("OPEN_BACKUPS", { n: game.backups })}
          desc={t("OPEN_BACKUPS_DESC")}
          icon={<IconRestore />}
          /* 0건이면 비활성 — 눌러도 빈 목록으로 이끄는 버튼은 라벨이 거짓말을 한다. */
          disabled={busy || game.backups === 0}
          onClick={() => { void openBackups(game); }}
        />

        <div style={DIVIDER_STYLE}>
          <ActionButton
            label={t("UNREGISTER_GAME")}
            desc={t("UNREGISTER_GAME_DESC")}
            icon={<IconTrash />}
            disabled={busy}
            onClick={() => {
              setLastRow(neighbourOf(game.appid));
              void runDelete(game.appid);
            }}
          />
        </div>
      </div>
    );
  }

  // ── 백업 목록 뷰 (§5-C) ────────────────────────────────────────────────────
  function renderBackups(game: OverviewGame) {
    const rows = backups ?? [];
    // 프로필 대피본이 목록에 있을 때만 "복원 뒤에 물어본다"고 예고한다 —
    // 조건 없는 약속은 실사용 다수인 `disk` 행에서 거짓이 된다(2026-08-10 QA R2의 교훈).
    const hasProfileRow = rows.some((r) => r.kind === "profile_dock" || r.kind === "profile_internal");
    return (
      <div style={COLUMN_STYLE}>
        <div style={{ fontSize: "16px", fontWeight: "bold" }}>
          {t("BACKUP_LIST_TITLE", { name: game.name })}
        </div>
        <div style={HINT_STYLE}>{t("BACKUP_LIST_HINT")}</div>
        {hasProfileRow ? <div style={HINT_STYLE}>{t("BACKUP_LIST_FOLLOWUP_HINT")}</div> : null}
        {/* ★ F2: 사용자의 멘탈 모델("최신 = 방금 저장한 나쁜 것")이 정반대 행을 고르게 한다.
            정렬은 백엔드가 이미 했고(프론트 재정렬 0), 화면은 그 순서의 뜻을 말한다. */}
        <div style={HINT_STYLE}>{t("BACKUP_LIST_ORDER_HINT")}</div>
        {/* ★ F4는 **질적으로만** 말한다 — "N칸 중"은 잔량 약속으로 읽혀 오정보가 된다
            (P8-2 이탈 #8로 확정된 판단). */}
        <div style={HINT_STYLE}>{t("BACKUP_RING_HINT")}</div>

        <PopupScrollList>
          {rows.map((row) => (
            <Focusable key={row.backup_id} {...listRowNavProps} style={CARD_STYLE}>
              <div style={{ ...CARD_INNER_STYLE, ...ROW_STYLE }}>
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
                <PopupButton
                  disabled={busy}
                  onClick={() => { void runRestore(game, row); }}
                  style={{ minWidth: "96px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
                >
                  {t("BACKUP_RESTORE")}
                </PopupButton>
              </div>
            </Focusable>
          ))}
        </PopupScrollList>
        {rows.length === 0 ? <div style={HINT_STYLE}>{t("BACKUP_LIST_EMPTY")}</div> : null}
        {noteView}
      </div>
    );
  }

  // ── 뷰 선택 ────────────────────────────────────────────────────────────────
  //
  // ⚠️ 분기를 한 줄에 이어 쓰지 않는다 — `A /> : x ? <B` 형태가 되면 `test_i18n_sets`의
  //   JSX 텍스트 정규식이 그 사이의 코드를 화면 글자로 오인해 거짓 FAIL을 낸다(실제로 냈다).
  function renderView() {
    if (view.kind === "list") return renderList();
    const game = games.find((g) => g.appid === view.appid);
    if (!game) {
      // 조회가 아직 안 왔거나 그 사이 사라진 게임이다 — 지어내지 않고 돌아갈 길만 남긴다.
      return (
        <PopupSubView key={subViewKey(view)} onBack={() => setView({ kind: "list" })}>
          <div style={HINT_STYLE}>{noteText ?? t("LOADING")}</div>
        </PopupSubView>
      );
    }
    if (view.kind === "backups") {
      return (
        <PopupSubView key={subViewKey(view)} onBack={() => setView({ kind: "detail", appid: game.appid })}>
          {renderBackups(game)}
        </PopupSubView>
      );
    }
    return (
      <PopupSubView key={subViewKey(view)} onBack={() => setView({ kind: "list" })}>
        {renderDetail(game)}
        {noteView}
      </PopupSubView>
    );
  }

  return (
    <GfxPopup title={t("GAMES_TITLE")} icon={<IconList />} where="popup-g" closeModal={closeModal}>
      {/* ★ 본문은 **반드시** `renderBody`를 지난다(§4-C D-05 ⑤): 폴백 모드에서 오버레이와
          원 콘텐츠가 동시에 떠 있는 상태를 호출부가 만들 수 없게 하는 장치다. */}
      {renderBody(renderView())}
    </GfxPopup>
  );
}
