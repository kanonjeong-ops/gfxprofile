import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  makeApplyConfirmSpec, makeDeleteConfirmSpec, makeRestoreConfirmSpec, makeRestoreFollowUpSpec,
  makeResultSpec, makeSaveConfirmSpec,
} from "./confirmSpecs";
import { Focusable, ToggleField } from "./deckyui";
import {
  IconBolt, IconCheck, IconChevron, IconChip, IconList, IconRefresh, IconRestore, IconSave, IconTrash,
} from "./icons";
import { t, tCode } from "./i18n";
import {
  CARD_INNER_STYLE, CARD_STYLE, GfxPopup, ICON_SLOT_STYLE, PATH_BREAK_STYLE, PopupButton,
  PopupScrollList, PopupSubView, ROW_FLOW, STACKED_BUTTON_STYLE, STACKED_DESC_PAD,
  listRowNavProps, preferredChildEntryProps, subViewKey,
  usePopupData, usePopupGate, type GView,
} from "./popup";
import { slotSummary } from "./slots";
import {
  applyProfile, deleteGame, getOverview, listBackups, restoreBackup, saveProfile,
  type ApplyConfirmParams, type BackupRow, type ConfirmParams, type DeleteConfirmParams,
  type Overview, type OverviewGame, type Profile, type RestoreConfirmParams,
} from "./rpc";

/**
 * 게임별 적용·저장 팝업.
 *
 * 뷰 셋이 한 팝업 안에 있다: 목록 → 게임 상세 → 백업 목록. 모달을 새로 겹치지 않고 뷰를
 * 바꾸는 이유는 중첩 깊이를 한 겹으로 묶어 두기 위해서다 — 위에 뜨는 것은 확인창뿐이고,
 * 그래야 B 버튼이 무엇을 닫는지가 결정된다.
 *
 * 판정은 백엔드에 있다. 이 화면은 적용 가능 여부·덮어쓰기 여부·백업 종류를 다시 계산하지
 * 않는다. `CONFIRM_REQUIRED`를 받으면 받은 토큰을 그대로 되돌려 재호출할 뿐이다.
 */

// ── 스타일 ──────────────────────────────────────────────────────────────────
const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
/* 잔글씨 3종(META·DESC·HINT)은 한국어 문장을 그린다 — `keep-all`로 낱말 중간 줄바꿈을 막는다.
   경로·파일명 줄은 여기서 갈라져 `PATH_STYLE`이 맡는다. */
const META_STYLE = { fontSize: "11px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
/**
 * 경로·파일명 줄 — `META_STYLE`과 같은 회색 잔글씨인데 줄바꿈 규칙만 다르다.
 *
 * `normal`을 명시하는 이유: `word-break`는 상속되는 속성이라 조상의 `keep-all`이 여기까지
 *   내려오고, 경로에는 끊을 낱말 경계가 없어 그러면 줄이 통째로 넘친다.
 * 호출부에서 `META_STYLE`을 덧써 예외를 만들지 않는다. "경로를 그리는 자리"에 이름을 주어
 *   예외가 생길 자리를 없앤다.
 * 소비자는 둘 — 상세 뷰의 `GAME_CONFIG_PATH` 줄과 백업 행의 `BACKUP_ROW_META` 줄이다.
 */
const PATH_STYLE = { ...META_STYLE, ...PATH_BREAK_STYLE } as const;
/**
 * 동작 버튼 아래 설명 줄 — 왼쪽 패딩이 `STACKED_DESC_PAD`라 버튼 라벨과 세로 축을 공유한다.
 * `ActionButton`의 desc 전용이다. 다른 설명 줄에 섞어 쓰면 그 축이 깨진다.
 */
const DESC_STYLE = {
  fontSize: "11px", color: "#9aa0a6", margin: "2px 0 6px", paddingLeft: STACKED_DESC_PAD,
  wordBreak: "keep-all",
} as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;

/* 카드의 두 상수(`CARD_STYLE`·`CARD_INNER_STYLE`)는 `popup.tsx`에 있다 — 다른 팝업의 목록
   행과 같은 모양이어야 하고, 값이 두 곳이면 한쪽만 손대는 날 같은 목록이 화면마다 달라진다. */

const ROW_STYLE = { display: "flex", alignItems: "center", gap: "6px" } as const;
const NAME_STYLE = { flex: "1 1 auto", minWidth: 0, fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis" } as const;

/**
 * 적용 버튼 2종의 공통 폭. 두 버튼이 같은 `minWidth`를 갖고 아이콘 자리와 마커 자리도 폭이
 * 고정이라 전 행의 버튼 x좌표가 같다 — 수직 이동 중 커서가 좌우로 튀지 않는다.
 * 이동 성향(`listRowNavProps`)과 2중 방어다: 한쪽이 안 들어도 나머지가 남는다.
 */
const APPLY_BUTTON_STYLE = {
  minWidth: "110px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto",
} as const;

/**
 * 라벨 뒤 마커 자리 — 상시 예약이다. 마커가 없어도 같은 폭의 빈 자리를 그린다.
 * 조건부로 자리 자체를 없애면 그 행만 버튼이 좁아져 열이 어긋난다.
 */
const MARKER_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginLeft: "4px",
} as const;

/** "현재 적용됨" 강조 배경. 폭에 영향을 주지 않는 속성만 쓴다 — 열 정렬이 깨지지 않게. */
const MARKED_BACKGROUND = "rgba(126,204,255,0.22)";

const CHEVRON_BUTTON_STYLE = { minWidth: "40px", padding: "6px 4px", flex: "0 0 auto" } as const;
/** 상세 뷰의 동작 버튼 — 세로로 쌓이므로 `STACKED_BUTTON_STYLE`의 좌측 정렬 축을 쓴다. */
const ACTION_BUTTON_STYLE = {
  minWidth: "220px", padding: "6px 10px", fontSize: "13px", ...STACKED_BUTTON_STYLE,
} as const;
const CHIP_STYLE = {
  fontSize: "11px", background: "rgba(255,255,255,0.12)", borderRadius: "3px",
  padding: "1px 6px", marginLeft: "6px",
} as const;

/** 등록 해제를 위 동작들과 선으로 가른다 — 파괴가 "다음 항목"처럼 읽히면 안 된다. */
const DIVIDER_STYLE = { borderTop: "1px solid #3a3f44", marginTop: "12px", paddingTop: "12px" } as const;

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

function profileIcon(p: Profile) {
  if (p === "dock") return <IconBolt />;
  return <IconChip />;
}

/**
 * `running`을 읽는 이 파일의 유일한 문.
 *
 * `build.sh`가 `src` 전체를 훑어 `.running` 접근 줄마다 바로 위나 같은 줄에
 *   `e1-display-only` 마커가 있는지 보고, 없으면 빌드를 세운다. 아래 마커 줄과 접근 줄
 *   사이에는 아무것도 끼울 수 없다.
 * 읽는 자리를 흩으면 언젠가 한 자리가 활성 조건으로 새어 들어간다("실행 중이면 버튼 비활성").
 *   그건 판정을 화면이 하는 것이다 — 판정은 백엔드가 하고 화면은 사실 표시만 한다.
 */
// e1-display-only
const isRunning = (game: OverviewGame) => game.running;

/** 실행 중 칩 — 표시 전용이다. 적용 버튼의 비활성 조건에는 이 값이 들어가지 않는다. */
function RunningChip({ game }: { game: OverviewGame }) {
  if (!isRunning(game)) return null;
  return <span style={CHIP_STYLE}>{t("RUNNING_CHIP")}</span>;
}

/**
 * "프로필과 다름" 칩 — 지금 게임 설정 파일이 저장된 어느 프로필과도 같지 않다는 표시다.
 *
 * 목적은 적용 확인창을 예고하는 것이다: 확인창이 뜨는 조건이 바로 이 상태이므로, 누르기 전에
 *   보이면 창이 놀라움이 되지 않는다.
 * 모양은 `RunningChip`과 같은 `CHIP_STYLE`이라 줄 수가 변하지 않는다.
 * 프로필이 하나도 없으면 그리지 않는다 — 없는 것을 지적하지 않는다.
 */
function DivergedChip({ game }: { game: OverviewGame }) {
  if (game.disk_matches.length > 0) return null;
  if (!game.has_dock && !game.has_internal) return null;
  return <span style={CHIP_STYLE}>{t("SLOT_DIVERGED")}</span>;
}

/** 백업 종류 문구 — 판정은 백엔드가 준 `kind` 코드이고 화면은 문구만 고른다. */
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
 * 되돌릴 곳 한 줄 — 판정은 백엔드가 준 `target`이고 화면은 문구만 고른다.
 *
 * `kind`로 고르지 않는다: 백업 파일 이름이 형식에서 벗어나면 `store.parse_backup_id`가
 *   `kind`를 `unknown`으로 접고, `restore.target_of`는 그때 목적지를 게임 설정 파일로 준다.
 *   두 값을 각자 해석하면 화면이 가리키는 곳과 실제로 쓰이는 곳이 갈린다.
 */
function targetText(row: BackupRow): string {
  if (row.target === "dock" || row.target === "internal") {
    return t("BACKUP_ROW_TARGET_PROFILE", { profile: t(profileKey(row.target)) });
  }
  return t("BACKUP_ROW_TARGET_DISK");
}

/** 목록 행 하나 — 게임명 + 적용 버튼 2개 + 상세로 가는 버튼, 그 아래 슬롯 요약 한 줄. */
function GameCard({
  game,
  busy,
  focused,
  takeFocus,
  onApply,
  onOpen,
}: {
  game: OverviewGame;
  busy: boolean;
  /** 목록으로 들어올 때 이 행에 착지시킬 것인가 — 마지막으로 조작한 행이 그 대상이다. */
  focused: boolean;
  /** 마운트하면서 스스로 포커스를 가져올 것인가 — 켜는 조건은 호출부의 `firstCards`가 정한다. */
  takeFocus: boolean;
  onApply: (game: OverviewGame, profile: Profile) => void;
  onOpen: (game: OverviewGame) => void;
}) {
  const has: Record<Profile, boolean> = { dock: game.has_dock, internal: game.has_internal };
  return (
    // ROW_FLOW — 이 카드 안의 focusable은 버튼들이 한 줄에 나란히 서 있다. 빠뜨리면 좌우 키가
    //   죽고 위아래로만 순회한다.
    //   `CARD_STYLE`은 flex가 아니라 배경·패딩만 있는 블록이라, 지정이 없으면 방향 추정이
    //   `column`으로 떨어진다 — 이미 flex 행인 컨테이너와 갈리는 지점이 이것이다.
    /* `autoFocus`가 `preferredFocus`와 같이 서 있는 이유:
         `preferredFocus`는 컨테이너로 포커스가 들어올 때 누구를 고를까이고, 그 진입은 팝업이
         처음 그려질 때 일어난다. 그때 목록은 아직 비어 있어 고를 카드가 없으므로 포커스는
         문서 순서대로 필터 줄에 선다. 데이터가 늦게 도착해도 진입은 다시 일어나지 않는다.
         `autoFocus`는 마운트하는 노드가 스스로 포커스를 요청하는 다른 축이라 늦게 온 카드에도
         듣는다.
       둘은 같은 카드를 가리키고 서로가 못 막는 갈래를 하나씩 맡는다. 한쪽만 두면 그 갈래에서만
         조용히 어긋난다.
       다만 조건이 다르다(`focused` 대 `takeFocus`): `autoFocus`는 마운트할 때마다 듣기 때문에,
         필터를 끄면서 숨었던 카드가 되돌아오는 순간에도 발동해 필터 줄에 있던 커서를 목록으로
         끌어간다. 사용자는 방금 만진 토글 자리에 있길 기대하므로 그건 포커스 훔치기다 —
         그래서 조건을 첫 데이터 도착 한 번으로 좁힌다(호출부 `firstCards`). */
    <Focusable
      {...listRowNavProps}
      {...ROW_FLOW}
      preferredFocus={focused}
      autoFocus={takeFocus}
      style={CARD_STYLE}
    >
      <div style={CARD_INNER_STYLE}>
        <div style={ROW_STYLE}>
          <div style={NAME_STYLE}>{game.name}</div>
          {(["dock", "internal"] as const).map((p) => (
            <PopupButton
              key={p}
              /* 비활성 조건은 그 프로필이 없을 때뿐이다. 실행 중 여부는 들어가지 않는다 —
                 누르면 백엔드가 `GAME_RUNNING`으로 거부하고 그 사유를 화면이 말한다. */
              disabled={busy || !has[p]}
              onClick={() => onApply(game, p)}
              style={{
                ...APPLY_BUTTON_STYLE,
                /* `disk_matches`는 배열이다 — 두 프로필의 내용이 같으면 두 버튼 모두에 마커가
                   선다. 백엔드가 첫 일치에서 멈추는 값(`engine.disk_state`)을 그대로 쓰면
                   나머지 한쪽이 "적용 안 됨"으로 보인다. */
                background: game.disk_matches.includes(p) ? MARKED_BACKGROUND : undefined,
              }}
            >
              <span style={ICON_SLOT_STYLE}>{profileIcon(p)}</span>
              {t("APPLY_SHORT", { profile: t(profileKey(p)) })}
              {/* 마커 자리는 항상 있다 — 없을 땐 같은 폭의 빈 자리다.
                  마커가 있어도 누를 수 있다: 이미 같은 내용이면 백엔드가 `already`로 끝낸다. */}
              <span style={MARKER_SLOT_STYLE}>{game.disk_matches.includes(p) ? <IconCheck /> : null}</span>
            </PopupButton>
          ))}
          {/* 톱니가 아니라 chevron이다 — 톱니는 전역 설정 진입 전용이라 여기 쓰면
              "이 게임의 설정"으로 읽혀 두 개념이 섞인다. */}
          <PopupButton disabled={busy} onClick={() => onOpen(game)} style={CHEVRON_BUTTON_STYLE}>
            <IconChevron />
          </PopupButton>
        </div>
        <div style={META_STYLE}>
          {/* 문장은 `slots.ts`가 만든다 — 목록과 상세가 같은 말을 해야 한다. */}
          {slotSummary(game)}
          <RunningChip game={game} />
          <DivergedChip game={game} />
        </div>
      </div>
    </Focusable>
  );
}

/** 동작 버튼과 그 아래 설명 한 줄. 설명이 없으면 자리도 만들지 않는다. */
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
   * 변이를 QAM 쪽에 알린다. 확정 실행이면 성공·실패를 가리지 않고 알린다 — 엔진은 쓴 뒤에
   * 거부할 수 있어서, 실패했다고 아무것도 안 바뀐 것이 아니다. 부르는 자리는 `useDataDoor`다.
   * 열려 있는 이 팝업의 화면 갱신은 별개이고, 그쪽도 같은 문이 맡는다.
   */
  onMutate?: () => void;
  /** `showModal`이 최상위 엘리먼트에 주입한다. */
  closeModal?: () => void;
}) {
  const [view, setView] = useState<GView>({ kind: "list" });
  const [noProfileOnly, setNoProfileOnly] = useState(false);
  /**
   * 마지막으로 조작한 행 — 목록으로 돌아올 때 그 행에 착지시킨다. 스크롤은 포커스를 따라가므로
   * 위치 복원을 따로 들고 있지 않아도 된다.
   */
  const [lastRow, setLastRow] = useState<string | null>(null);
  const [backups, setBackups] = useState<BackupRow[] | null>(null);

  const load = useCallback(() => getOverview(true), []);
  /* 게이트를 먼저 만든다: 아래 데이터 훅이 결과 팝업을 띄우려면 게이트가 이미 있어야 한다.
     `usePopupGate`는 인자를 받지 않아 데이터에 의존하지 않으므로 순서만 바꾸면 된다. */
  const { gate, renderBody } = usePopupGate();
  /**
   * 결과 팝업을 띄우는 자리 — ref로 든다.
   * 데이터 훅이 이 함수를 부르는데, 그 함수는 그 훅이 준 `setNote`를 쓴다. 순환을 값으로 풀면
   * 한쪽이 반드시 낡으므로 최신 것을 가리키는 상자를 둔다.
   */
  const showResultRef = useRef<(text: string) => void>(() => {});
  const { data, noteText, setNote, setReloadNote, noteView, busy, reload, runMutation, runQuery } =
    usePopupData<Overview>(load, "LOAD_FAILED", onMutate,
      // 변이는 성공했는데 뒤따른 재조회가 실패한 경우. 판정은 데이터 훅이 했고 여기는 그리기만 한다.
      () => showResultRef.current(t("RESULT_STALE_NOTE")));

  /**
   * 결과 팝업 — 동작 결과 통지는 전부 여기로 나간다.
   *
   * 왜 note가 아닌가: note가 줄을 하나 얻으면 같은 화면의 다른 줄들이 밀린다 — 방금 누른 행이
   *   손가락 아래에서 움직이는 자리다.
   * 창을 못 띄우면 그 결과를 note로 말한다(창이 안 떴다는 사실보다 결과가 중요하다). 그때는
   *   note가 그 사정도 같이 말한다 — 사용자가 왜 여기 적혔는지 알 수 있게.
   */
  const showResult = useCallback(
    (text: string): true => {
      gate(makeResultSpec(<div>{text}</div>), "RESULT_MODAL_FAILED",
           (why) => setNote(`${text} ${why}`));
      // 말했다는 사실을 데이터 훅에 돌려준다 — 그쪽은 이 값을 보고 「화면이 낡았다」 창을 겹치지
      //   않는다. 창을 못 띄운 경우에도 note로 말했으므로 사실은 같다(침묵이 아니다).
      return true;
    },
    [gate, setNote],
  );
  showResultRef.current = showResult;

  const games = data?.games ?? [];
  const counts = data?.counts;

  /**
   * 첫 데이터 도착인가 — 카드의 `autoFocus`를 켤 유일한 순간이다.
   *
   * 왜 한 번뿐인가: `autoFocus`가 필요한 갈래는 "팝업에 들어온 시점엔 목록이 비어 있어 고를
   *   카드가 없었다" 하나뿐이다. 그 뒤의 마운트(필터를 끄면서 숨었던 카드가 되돌아오는 것)는
   *   사용자가 다른 곳을 조작하던 중이라, 같은 prop이 그때는 포커스 훔치기가 된다.
   * 왜 ref를 effect에서 내리는가: 렌더 도중 뒤집으면 그 렌더가 버려질 때 첫 도착을 놓친다.
   *   커밋 뒤에 내리면 화면에 실제로 나간 렌더가 기준이 된다.
   * 목록으로 돌아올 때의 착지는 이것과 무관하다 — `renderList`의 진입 컨테이너가 맡는다.
   *   그래서 좁혀도 잃는 갈래가 없다.
   */
  const cardsSeenRef = useRef(false);
  const firstCards = games.length > 0 && !cardsSeenRef.current;
  useEffect(() => {
    if (games.length > 0) cardsSeenRef.current = true;
  }, [games.length]);

  /**
   * 지금 어느 뷰인가 — 아래 두 판정(무엇을 다시 읽는가 · 결과를 말할 것인가)이 이 값에 달렸다.
   *
   * 왜 ref인가: 동작 콜백들은 deps를 좁게 고정해 두므로(재생성되면 확인창 안에 갇힌 옛 콜백이
   *   생긴다) 상태를 직접 읽으면 만들어질 때의 뷰를 본다. 최신 것을 가리키는 상자를 둔다.
   */
  const viewRef = useRef(view);
  viewRef.current = view;

  /**
   * 백업 목록을 다시 읽는다. 실패해도 화면은 남고, 그 사실은 note의 둘째 줄이 말한다.
   *
   * 실패 사유를 `setNote`로 쓰면 방금 한 동작의 결과를 덮는다: 복원은 성공했는데 목록 재조회가
   *   실패하면 복원 결과와 후속 안내가 통째로 사라진다. 두 사실은 서로 다르고 둘 다 참이라
   *   자리를 갈라 둘 다 말한다 — 그래서 `setReloadNote`를 쓴다.
   */
  const refreshBackups = useCallback(
    (appid: string) => {
      // 읽기 전용이라 `runQuery`다 — busy만 같이 쓰고 재조회·변이 통지는 붙지 않는다.
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
   * 백업 목록을 보고 있으면 그것을 다시 읽는다 — 재조회 판정을 지나는 문 하나다.
   *
   * 왜 호출부가 아니라 여기인가: 백업을 만드는 동작은 복원만이 아니다. 적용도 지금 게임 설정
   *   파일의 내용이 어느 슬롯에도 없으면 대피본을 만들고, 링이 차 있으면 그 순간 목록의 마지막
   *   행이 사라진다. 재조회를 호출부마다 손으로 붙이면 백업 뷰에서 출발한 적용처럼 나중에 늘어난
   *   경로가 빠지고, 화면에는 방금 사라진 백업의 복원 버튼이 남아 `BACKUP_FILE_MISSING`을 부른다.
   *   규칙을 뷰에 묶어 두면 새 동작이 늘어도 따라온다.
   */
  const refreshShownBackups = useCallback(() => {
    const shown = viewRef.current;
    if (shown.kind === "backups") refreshBackups(shown.appid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 적용이 실제로 쓴 뒤 — 침묵할지 말할지를 여기 한 곳에서 정한다.
   *
   * 성공 침묵의 전제는 "화면이 그 변화를 보인다"이고, 그 전제는 뷰마다 다르다: 목록·상세에는
   *   적용 마커와 슬롯 요약이 있어 참이지만 백업 목록 뷰에는 둘 다 없다. 거기서 침묵하면 화면이
   *   하나도 안 바뀌고, 무반응은 고장으로 읽힌다.
   * 판정을 호출부에 두지 않는다 — "지금 어느 뷰였더라"를 기억하게 하면 다음에 추가되는 동작이
   *   또 빠뜨린다.
   */
  const settleApplied = useCallback(
    (profile: Profile): boolean | void => {
      refreshShownBackups();
      if (viewRef.current.kind !== "backups") return;   // 마커와 슬롯 요약이 그 자리에서 바뀐다 — 침묵
      return showResult(t("APPLY_OK", { profile: t(profileKey(profile)) }));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showResult],
  );

  /**
   * 적용 — 저장된 프로필에서 게임 설정 파일로 가는 한 방향이다. 묻는 조건은 백엔드가 정한다.
   *
   * 결과를 말하는 규칙이 셋이다:
   *   · `applied` → 뷰가 정한다(`settleApplied`). 마커가 보이는 뷰에서는 침묵, 백업 뷰에서는
   *     결과 팝업 — 침묵의 전제가 그 화면에서 성립하지 않는다.
   *   · `already` → 결과 팝업. 아무것도 안 바뀐 것은 화면이 못 보이고 무반응은 고장으로 읽힌다.
   *   · 거부·실패 → 결과 팝업(사유).
   * `CONFIRM_REQUIRED`는 흐름 신호다: 확인창을 띄우고 받은 토큰을 그대로 되돌려 재호출한다.
   *   토큰은 이 게임·이 프로필에 묶여 있어 다른 프로필에는 소비되지 않는다.
   */
  const runApply = useCallback(
    (game: OverviewGame, profile: Profile, token?: string) => {
      // 확정 실행이라 `runMutation`이다 — 재조회·변경 통지는 성공·실패를 가리지 않고 그 문이 붙인다
      //   (`CONFIRM_REQUIRED`만 그 앞에서 되돌아간다).
      void runMutation(() => applyProfile(game.appid, profile, token), "APPLY_FAILED", (res) => {
        if (res.ok) {
          if (res.data.outcome === "applied") return settleApplied(profile);
          return showResult(t("APPLY_ALREADY", { profile: t(profileKey(profile)) }));
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ApplyConfirmParams;
          gate(
            makeApplyConfirmSpec(p, profile, () => { runApply(game, profile, p.confirm_token); }),
            "APPLY_CONFIRM_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // 실패도 쓴 뒤일 수 있다 — 대피본을 만든 다음 설정 파일 쓰기에서 죽는 갈래가 있다.
        //   백업 뷰에 있다면 목록이 이미 낡았으므로, 복원의 실패 갈래와 같은 문을 지난다.
        refreshShownBackups();
        return showResult(tCode(res.code, "APPLY_FAILED"));
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, settleApplied, showResult],
  );

  /**
   * 저장 — 덮어쓰기라 백엔드가 확인을 요구할 수 있다. 빈 슬롯 첫 저장은 묻지 않는다(잃을 것이 없다).
   *
   * 실행 중 저장은 거부가 아니라 경고다 — `engine.save_profile`이 `running_game`이면
   *   `WARN_SAVE_WHILE_RUNNING`을 봉투에 싣는다. 그 값을 성공 통지에 병기한다.
   *
   * 결과를 말하는 규칙은 적용과 대칭이다:
   *   · `saved` → 침묵. 슬롯 상태와 저장 시각이 화면에서 바뀌므로 화면 자체가 결과다.
   *   · `already` → 결과 팝업. 한 바이트도 쓰지 않은 갈래라 화면이 하나도 안 바뀐다 —
   *     무반응은 고장으로 읽힌다. 적용의 `APPLY_ALREADY`와 같은 자리·같은 문법이다.
   */
  const runSave = useCallback(
    (appid: string, profile: Profile, token?: string) =>
      runMutation(() => saveProfile(appid, profile, token), "SAVE_FAILED", (res) => {
        if (res.ok) {
          if (res.data.outcome === "already") {
            return showResult(t("SAVE_ALREADY", { profile: t(profileKey(profile)) }));
          }
          // 저장 성공은 침묵이다 — 슬롯 상태와 저장 시각이 화면에서 바뀐다.
          //   단 실행 중 저장의 경고는 화면이 못 보이는 사실이라 그때만 말한다.
          if (res.data.warning) {
            // 봉투의 `warning`은 문장이 아니라 코드다 — 문장은 여기서 현재 언어로 고른다.
            //   백엔드가 문장을 실어 보내면 영어 화면에 한국어가 붙는다.
            //   미등재 코드는 `tCode`가 fallback으로 흘린다(단일 관문 — 원문 코드가 보인다).
            return showResult(
              `${t("SAVE_OK", { profile: t(profileKey(profile)) })} ${tCode(res.data.warning, "UNEXPECTED")}`,
            );
          }
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ConfirmParams;
          gate(
            makeSaveConfirmSpec(p, profile, () => { void runSave(appid, profile, p.confirm_token); }),
            "SAVE_CONFIRM_MODAL_FAILED",
            setNote,
          );
          return;
        }
        return showResult(tCode(res.code, "SAVE_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, showResult],
  );

  /**
   * 복원 — 판정은 세 갈래이고 기준은 되돌릴 곳이다: `already`는 무쓰기 · 되돌릴 곳이 비어
   * 있으면 토큰 없이 즉시 · 그 외는 `CONFIRM_REQUIRED`.
   *
   * 목적지는 봉투의 `target`이 정본이다 — 프론트가 `kind`로 다시 분류하지 않는다.
   * 성공 뒤 백업 목록을 재조회한다. 복원이 기존 목적지 내용을 대피하면 목록 구성이 바뀔 수 있고,
   *   포화 링에서는 `backup_order_key` 꼬리의 행이 사라질 수 있다.
   * 슬롯 복원 성공은 후속 제안으로 잇는다: 되돌린 내용은 아직 프로필에만 있으므로 게임에도
   *   적용할지 묻는다.
   */
  const runRestore = useCallback(
    (game: OverviewGame, row: BackupRow, token?: string) =>
      runMutation(() => restoreBackup(game.appid, row.backup_id, token), "RESTORE_FAILED", (res) => {
        if (res.ok) {
          const target = res.data.target;
          const slot: Profile | null =
            target === "dock" || target === "internal" ? target : null;
          const stamp = res.data.stamp_label || res.data.backup_id;
          if (res.data.outcome === "already") {
            // 실패가 아니다 — 되돌릴 곳이 이미 그 백업과 같다는 뜻이라 쓰기도 링 소모도 0이다.
            return showResult(slot
              ? t("RESTORE_ALREADY_PROFILE", { profile: t(profileKey(slot)) })
              : t("RESTORE_ALREADY"));
          }
          // 재조회는 뷰가 정한다(`refreshShownBackups`) — 이 경로는 언제나 백업 뷰에서 출발하지만,
          //   규칙이 호출부에 흩어져 있으면 다음 동작이 또 빠뜨린다.
          refreshShownBackups();
          if (slot) {
            gate(
              makeRestoreFollowUpSpec(slot, stamp, () => { runApply(game, slot); }),
              // 여기서는 복원이 이미 끝났다. "아무것도 안 했다"고 말하면 거짓이다 — 못 한 것은
              //   후속 제안뿐이고, 실패 문구가 남은 길을 알려 준다.
              // 치환자를 채워서 준다: 이 실패 문구에는 프로필 자리가 있고, 값을 안 주면 `t`가
              //   중괄호를 그대로 남겨 어느 버튼인지 지목하지 못한다. 적용 버튼은 둘이라 틀린
              //   쪽을 누르면 다른 프로필이 게임에 쓰인다.
              { key: "RESTORE_FOLLOWUP_MODAL_FAILED", params: { profile: t(profileKey(slot)) } },
              setNote,
            );
            // 후속 제안 창이 복원 완료 문장(`RESTORE_OK_PROFILE`)을 품고 있다 — 창으로 말했다.
            return true;
          }
          // `target`이 슬롯이 아닌 행이다 — 게임 설정 파일로 간다(`restore.target_of`).
          return showResult(t("RESTORE_OK_MANUAL", { stamp }));
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
        // 실패 코드는 `tCode` 단일 관문을 지난다 — 미등재 코드도 원문이 보이게 흐른다.
        refreshShownBackups();
        return showResult(tCode(res.code, "RESTORE_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, refreshShownBackups, runApply, showResult],
  );

  /**
   * 등록 해제 = 등록 말소 + 감지 제외. 성공하면 목록으로 돌아가고, 사라진 행 대신 인접 행에
   * 착지시킨다 — 방금 지운 자리에 포커스를 두면 커서가 어디로 갔는지 알 수 없다.
   */
  const runDelete = useCallback(
    (appid: string, token?: string) =>
      runMutation(() => deleteGame(appid, token), "DELETE_ACTION_FAILED", (res) => {
        if (res.ok) {
          // 침묵 — 목록으로 돌아가고 그 행이 사라진다. 화면 자체가 결과다.
          setView({ kind: "list" });
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          // 흐름 신호다 — 오류 문구로 그리지 않는다. 확인창을 띄운 사이 상태가 바뀌었으면
          //   백엔드가 갱신된 params와 함께 다시 이 코드를 낸다.
          const p = res.params as unknown as DeleteConfirmParams;
          gate(
            makeDeleteConfirmSpec(p, () => { void runDelete(appid, p.confirm_token); }),
            "MANAGE_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // `DELETE_FAILED`도 여기로 온다 — 다시 해제하면 남은 것부터 이어서 지운다.
        //
        // 그런데 `DELETE_FAILED`는 한 문장으로 덮을 수 없는 두 종류다: 삭제 도중 실패(일부가
        //   지워졌을 수 있다)와 시작 전 거부(등록 정보와 프로필 데이터는 그대로다). 뒤쪽에
        //   부분 삭제 경고를 보이면 화면이 거짓을 말한다.
        //   갈림의 근거는 `params.stage`가 아니다 — 같은 문자열 `"escape"`를 `restore.py`가
        //     다른 코드(`BACKUP_OUT_OF_ROOT`)에도 쓴다. 백엔드가 사실 필드로 싣는
        //     `profile_delete_started`를 읽는다(계약 전문은 `rpc.ts`의 `deleteGame`).
        //   필드가 없거나 boolean이 아니면 보수적으로 간다 — `=== false`로만 안전 갈래를 연다.
        //   `DELETE_FAILED`가 아닌 코드는 계속 `tCode` 단일 관문을 지난다.
        if (res.code === "DELETE_FAILED") {
          const beforeDelete = res.params.profile_delete_started === false;
          return showResult(
            beforeDelete ? t("DELETE_FAILED_BEFORE_DELETE") : t("DELETE_FAILED"),
          );
        }
        return showResult(tCode(res.code, "DELETE_ACTION_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, showResult],
  );

  /** 백업 뷰로 — 목록을 먼저 받고 그 다음에 연다. 빈 화면이 떴다가 채워지는 중간 상태가 없다. */
  const openBackups = useCallback(
    (game: OverviewGame) =>
      runQuery(() => listBackups(game.appid), "BACKUP_LIST_FAILED", (res) => {
        if (!res.ok) {
          showResult(tCode(res.code, "BACKUP_LIST_FAILED"));
          return;
        }
        setBackups(res.data.backups);
        setView({ kind: "backups", appid: game.appid });
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showResult],
  );

  /** 등록 해제 뒤 착지할 인접 행(다음 항목, 없으면 이전). 목록이 비면 null이다. */
  function neighbourOf(appid: string): string | null {
    const index = shown.findIndex((g) => g.appid === appid);
    if (index < 0) return null;
    const next = shown[index + 1] || shown[index - 1];
    return next ? next.appid : null;
  }

  // ── 목록 뷰 ─────────────────────────────────────────────────────────────────
  //
  // 정렬은 이름순 하나뿐이다. "덜 된 것을 위로" 같은 재정렬은 화면이 바뀔 때마다 행이 이동해
  // 근육 기억이 무너진다 — 순서 안정성을 택한다.
  const sorted = [...games].sort((a, b) => a.name.localeCompare(b.name));
  // 필터 술어 — 두 프로필 중 하나라도 없는 게임만 남긴다.
  const shown = noProfileOnly ? sorted.filter((g) => !g.has_dock || !g.has_internal) : sorted;

  function renderList() {
    return (
      /* 목록 뷰의 진입 컨테이너다: 카드의 `preferredFocus`는 `preferredChildEntryProps`가
         붙은 컨테이너를 지나 들어올 때만 읽힌다. 필터 줄과 목록을 함께 품어야 하므로 자리는
         여기 하나뿐이다 — 스크롤 목록에만 붙이면 팝업 진입이 그 바깥에서 시작해 여전히 필터
         줄에 선다. */
      <Focusable {...preferredChildEntryProps} style={COLUMN_STYLE}>
        <Focusable {...ROW_FLOW} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <ToggleField
              label={t("FILTER_NO_PROFILE_ONLY")}
              checked={noProfileOnly}
              onChange={setNoProfileOnly}
            />
          </div>
          {/* "게임을 끄고 왔는데 화면이 낡았을 수 있다"의 탈출구. 초기 포커스는 첫 카드로 가므로
              이 줄이 통행세가 되지 않는다. */}
          <PopupButton
            disabled={busy}
            onClick={() => reload()}
            style={{ minWidth: "120px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
          >
            <span style={ICON_SLOT_STYLE}><IconRefresh /></span>
            {t("REFRESH")}
          </PopupButton>
        </Focusable>

        <PopupScrollList>
          {shown.map((game, index) => {
            // 두 축(`focused`·`takeFocus`)이 같은 행을 가리킨다 — 조건만 다르다.
            const rowFocused = lastRow ? game.appid === lastRow : index === 0;
            return (
              <GameCard
                key={game.appid}
                game={game}
                busy={busy}
                focused={rowFocused}
                takeFocus={firstCards && rowFocused}
                onApply={runApply}
                onOpen={(g) => { setLastRow(g.appid); setView({ kind: "detail", appid: g.appid }); }}
              />
            );
          })}
        </PopupScrollList>

        {/* note는 목록 아래다. 위에 두면 줄이 하나 생길 때마다 아래 목록 전체가 내려가 방금 누른
            행이 손가락 아래에서 움직인다.
            남은 소비자는 재조회 실패 둘째 줄과 결과 창을 못 띄웠을 때의 대타뿐이다 — 동작 결과는
            전부 결과 팝업으로 나간다. */}
        {noteView}

        {/* 모르는 것을 없다고 말하지 않는다 — `data`가 null인 것은 아직 못 읽었다는 뜻이지
            0개가 아니다. 실패 문구는 note가 이미 그린다. */}
        {renderListTail()}

        {/* 제외된 게임이 있을 때만 한 줄. 0건이면 아예 그리지 않는다.
            수를 말하지 않는다: 표시 조건에 쓰는 `counts.excluded`는 원본 키 수인데, 이 안내가
              가리키는 제외 목록은 손상 항목을 격리한 뒤의 행들이라 두 수가 다를 수 있다. 조건에
              원본 수를 쓰는 것은 옳다(격리된 항목도 초기화로 지울 것에 든다) — 그 수를 화면 약속에
              재사용하지 않으면 어긋날 자리가 없어진다.
            같은 이유로 "볼 수 있습니다"라는 가시성 약속 대신 어디에 있는지만 말한다. 그 경로는
              제외된 게임을 되찾는 유일한 동선이라 지우지 않는다. */}
        {counts && counts.excluded > 0 ? (
          <div style={META_STYLE}>{t("GAMES_EXCLUDED_NOTE")}</div>
        ) : null}
      </Focusable>
    );
  }

  /**
   * 목록이 비었을 때의 한 줄 — 왜 비었는지가 세 갈래다: 아직 못 읽었다 · 등록이 0이다 ·
   * 필터가 전부 걸러냈다.
   *
   * 필터 뒤의 개수만 보고 "등록된 게임이 없다"고 말하면 안 된다. 필터가 전부 걸러낸 상태는
   *   모든 게임이 두 프로필을 다 가진 정상 종착점이라, 그 화면에서 등록이 0이라 말하는 것은
   *   거짓이고 처방(게임 감지로 가라)까지 틀린다. 실제로 할 일은 필터를 끄는 것뿐이다.
   */
  function renderListTail() {
    if (data === null) {
      if (noteText) return null;
      return <div style={HINT_STYLE}>{t("LOADING")}</div>;
    }
    if (shown.length > 0) return null;
    // 필터 전 목록이 0 — 여기서만 "추가하러 가라"가 참이다.
    if (sorted.length === 0) return <div style={HINT_STYLE}>{t("NO_GAMES")}</div>;
    return <div style={HINT_STYLE}>{t("FILTER_ALL_HAVE_PROFILES")}</div>;
  }

  // ── 게임 상세 뷰 ────────────────────────────────────────────────────────────
  /**
   * 상태 줄 — `disk_matches`가 배열이라 「둘 다와 같음」 갈래가 따로 있다.
   *
   * `PROFILES_IDENTICAL`과 중복이 아니다: 저쪽은 저장된 두 슬롯이 서로 같다는 말이고, 이쪽은
   *   지금 게임 설정 파일이 그 둘과 같다는 말이다. 두 사실은 따로 참일 수 있다.
   * 프로필이 하나도 없으면 빈 문자열을 돌려 줄 자체를 그리지 않는다.
   */
  function statusLine(game: OverviewGame) {
    if (game.disk_matches.length >= 2) return t("GAME_DETAIL_STATUS_BOTH");
    const only = game.disk_matches[0];
    if (only) return t("GAME_DETAIL_STATUS", { profile: t(profileKey(only)) });
    if (!game.has_dock && !game.has_internal) return "";
    // 어느 슬롯과도 다른 상태다 — 게임에서 방금 값을 바꾼 직후가 여기이고, 저장 버튼의 존재
    //   이유를 화면이 스스로 설명한다.
    return t("GAME_DETAIL_DIVERGED");
  }

  function renderDetail(game: OverviewGame) {
    const status = statusLine(game);
    const saveDesc = isRunning(game) ? t("SAVE_DESC_RUNNING") : t("SAVE_DESC");
    return (
      <div style={COLUMN_STYLE}>
        {/* 게임명을 고정 맥락으로 둔다 — 이 뷰의 모든 동작이 이 게임 하나에만 걸린다. */}
        <div style={{ fontSize: "16px", fontWeight: "bold" }}>{game.name}</div>
        {status ? <div style={{ fontSize: "13px" }}>{status}</div> : null}
        <div style={META_STYLE}>
          {slotSummary(game)}
          <RunningChip game={game} />
        </div>
        {/* 같은 내용을 두 슬롯에 저장해 둔 상태 — 전환해도 아무 변화가 없어 "고장"으로 읽힌다.
            판정은 백엔드가 두 meta sha를 대조해서 하고, 화면은 그 사실만 말한다. */}
        {game.profiles_identical ? <div style={HINT_STYLE}>{t("PROFILES_IDENTICAL")}</div> : null}
        {/* 경로가 문자열이 아니거나 제자리가 아니면 백엔드가 빈 문자열을 준다 — 그때는 안 그린다. */}
        {game.config_path ? <div style={PATH_STYLE}>{t("GAME_CONFIG_PATH", { path: game.config_path })}</div> : null}
        {/* 게임별 재촉이 아니라 조작 방법 설명이다.
            두 문장을 두 키·두 요소로 나눈다 — 한 키에 개행을 넣어도 `white-space` 미지정이라
              한 줄로 이어붙는다. 순서는 아래 저장 버튼과 같다(dock → internal): 어긋나면
              사용자가 줄과 버튼을 짝짓지 못한다.
            "게임을 종료하고"가 핵심이다 — 실행 중에 저장하면 디스크에 남은 옛 값이 저장될 수
              있다. 사후 방어(`SAVE_DESC_RUNNING`)는 그대로 두되, 안내가 미리 말하면 실수 자체가
              생기지 않는다. */}
        <div style={HINT_STYLE}>{t("SAVE_GUIDE_DOCK", { dock: t("PROFILE_DOCK") })}</div>
        <div style={HINT_STYLE}>{t("SAVE_GUIDE_INTERNAL", { internal: t("PROFILE_INTERNAL") })}</div>

        {(["dock", "internal"] as const).map((p) => (
          <ActionButton
            key={p}
            label={t("SAVE_SHORT", { profile: t(profileKey(p)) })}
            desc={saveDesc}
            icon={<IconSave />}
            /* 저장은 빈 슬롯에도 눌러야 한다 — 프로필을 처음 만드는 동작이 이것이라, 비활성
               조건에 슬롯 유무가 들어가지 않는다. */
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

  // ── 백업 목록 뷰 ────────────────────────────────────────────────────────────
  function renderBackups(game: OverviewGame) {
    const rows = backups ?? [];
    // 프로필로 되돌아가는 행이 있을 때만 "그 뒤에 물어본다"고 예고한다 — 조건 없는 약속은
    //   설정 파일로 되돌아가는 행에서 거짓이 된다.
    // 판정은 `target`이다. `kind`로 고르면 이름이 형식에서 벗어나 `unknown`으로 접힌 행에서
    //   화면과 실제 목적지가 갈린다(`targetText`와 같은 근거·같은 값).
    const hasProfileRow = rows.some((r) => r.target !== "config");
    return (
      <div style={COLUMN_STYLE}>
        <div style={{ fontSize: "16px", fontWeight: "bold" }}>
          {t("BACKUP_LIST_TITLE", { name: game.name })}
        </div>
        <div style={HINT_STYLE}>{t("BACKUP_LIST_HINT")}</div>
        {hasProfileRow ? <div style={HINT_STYLE}>{t("BACKUP_LIST_FOLLOWUP_HINT")}</div> : null}
        {/* "최신 = 방금 저장한 나쁜 것"이라는 짐작이 정반대 행을 고르게 한다 — 그래서 순서의
            뜻을 글로 말한다. 정렬은 백엔드가 이미 했고 프론트는 다시 정렬하지 않는다. 그 순서는
            파일명 속 벽시계 stamp에서 유도된 것이라 실제 생성 순서를 보증하지는 않는다. */}
        <div style={HINT_STYLE}>{t("BACKUP_LIST_ORDER_HINT")}</div>
        {/* 링 안내는 질적으로만 말한다 — "N칸 중" 같은 수는 잔량 약속으로 읽혀 오정보가 된다. */}
        <div style={HINT_STYLE}>{t("BACKUP_RING_HINT")}</div>

        <PopupScrollList>
          {rows.map((row) => (
            <Focusable key={row.backup_id} {...listRowNavProps} style={CARD_STYLE}>
              {/* 카드 안쪽은 목록 카드와 같은 이중 구조다(`CARD_INNER_STYLE` 바깥 · `ROW_STYLE`
                  안쪽). 두 상수를 한 div에 펼쳐 합치지 않는다: `CARD_INNER_STYLE`은 세로 스택이고
                  `ROW_STYLE`에는 방향이 없어서, 합치면 방향이 `column`으로 살아남고
                  `alignItems:"center"`가 가로 중앙으로 작동해 텍스트가 가운데로 좁아지고 복원
                  버튼이 그 아래로 내려간다.
                  폭 상한은 바깥, 가로 배치는 안쪽 — 같은 것은 같은 방법으로 그린다. */}
              <div style={CARD_INNER_STYLE}>
                <div style={ROW_STYLE}>
                  <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                    <div style={{ fontSize: "14px" }}>
                      {kindText(row)}
                      {/* 되돌릴 곳의 지금 내용이 이 백업과 같다는 표시 — 누르기 전에 말하면
                          "아무 일도 안 일어났다"는 결과 팝업이 뜰 이유가 준다.
                          모르면 백엔드가 false를 주므로 배지가 안 뜬다 — 없는 사실을 만들지 않는다. */}
                      {row.same_as_target ? <span style={CHIP_STYLE}>{t("BACKUP_ROW_SAME")}</span> : null}
                    </div>
                    {/* 파일명이 들어가는 줄이라 `PATH_STYLE`이다 — 문장이 아니라 식별자다. */}
                    <div style={PATH_STYLE}>
                      {t("BACKUP_ROW_META", {
                        stamp: row.stamp_label || t("BACKUP_STAMP_UNKNOWN"),
                        size: row.size,
                        filename: row.filename,
                      })}
                    </div>
                    {/* 되돌릴 곳을 행마다 한 줄로 말한다. 값은 백엔드가 준 `target`이고 프론트는
                        `kind`로 재분류하지 않는다 — 두 곳에서 판정하면 화면이 가리키는 곳과 실제로
                        쓰이는 곳이 갈리는 날이 온다. */}
                    <div style={META_STYLE}>{targetText(row)}</div>
                  </div>
                  {/* 같은 내용이어도 비활성화하지 않는다: 패드에서 비활성 버튼은 포커스를 못 받아
                      사용자가 이유를 알 길이 없다. 눌리면 백엔드가 `already`로 끝내고 결과 팝업이
                      그 사실을 말한다. */}
                  <PopupButton
                    disabled={busy}
                    onClick={() => { void runRestore(game, row); }}
                    style={{ minWidth: "96px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
                  >
                    {t("BACKUP_RESTORE")}
                  </PopupButton>
                </div>
              </div>
            </Focusable>
          ))}
        </PopupScrollList>
        {rows.length === 0 ? <div style={HINT_STYLE}>{t("BACKUP_LIST_EMPTY")}</div> : null}
        {noteView}
      </div>
    );
  }

  // ── 뷰 선택 ─────────────────────────────────────────────────────────────────
  // 한 분기를 다음 분기에 한 줄로 잇지 않고, 각 갈래를 독립된 이른 반환으로 쓴다.
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
      {/* 본문은 반드시 `renderBody`를 지난다: 오버레이가 있으면 그것만 그리므로, 오버레이와
          원 콘텐츠가 동시에 떠 있는 상태를 호출부가 만들 수 없다. */}
      {renderBody(renderView())}
    </GfxPopup>
  );
}
