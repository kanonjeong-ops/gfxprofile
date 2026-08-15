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
/* 잔글씨 3종(META·DESC·HINT)은 **한국어 문장**을 그린다 — `wordBreak: "keep-all"`로 낱말
   중간 줄바꿈을 막는다(사유·제외 규칙의 정본은 `popup.tsx`의 `KEEP_ALL_STYLE` 주석). */
const META_STYLE = { fontSize: "11px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
/**
 * 경로·파일명 줄 — **낱말 보존을 걸지 않는** 잔글씨다(위 `META_STYLE`과 갈라지는 지점).
 *
 * ★★ 왜 상수를 따로 두는가: 같은 회색 11px인데 **줄바꿈 규칙만** 다르다. 호출부에서
 *   `{...META_STYLE, wordBreak:"normal"}`로 덧쓰면 예외가 슬롯마다 흩어지고 하나를 빠뜨리는
 *   날이 온다 — *"경로를 그리는 자리"*라는 개념에 이름을 주어 **예외가 생길 자리 자체를 없앤다.**
 * ★ `normal`을 **명시한다**: `wordBreak`는 상속되는 속성이라 조상이 `keep-all`이면 여기까지
 *   내려오고, 경로에는 끊을 낱말 경계가 없어 그러면 줄이 통째로 넘친다.
 * 소비자는 둘 — 상세 뷰의 `GAME_CONFIG_PATH`, 백업 목록 행의 `BACKUP_ROW_META`(파일명).
 */
const PATH_STYLE = { ...META_STYLE, ...PATH_BREAK_STYLE } as const;
/**
 * 동작 버튼 아래 설명 줄 — 들여쓰기가 버튼의 가로 패딩과 같아 **라벨과 축을 공유**한다(§4-G 3항).
 * 이 상수는 `ActionButton`의 desc 전용이다(다른 설명 줄과 섞어 쓰지 말 것 — 축 공유가 깨진다).
 */
const DESC_STYLE = {
  fontSize: "11px", color: "#9aa0a6", margin: "2px 0 6px", paddingLeft: STACKED_DESC_PAD,
  wordBreak: "keep-all",
} as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;

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

/**
 * **`[프로필과 다름]` 칩**(R13 §5-A) — 지금 게임 설정 파일이 저장된 어느 프로필과도 다르다.
 *
 * ★★ 목적은 **적용 확인창이 놀라움이 되지 않게** 하는 것이다: 확인창이 뜨는 조건이 바로 이
 *   상태이므로, 누르기 전에 보이면 창은 예고된 것이 된다(§4-I ⑤-ⓑ — 팝업을 참게 만드는 것이
 *   아니라 **팝업의 이유를 줄인다**).
 * ★ 자리도 모양도 `RunningChip`과 같다 — **줄 수가 변하지 않는다**(§4-I ①-ⓒ).
 * ★ 프로필이 하나도 없으면 그리지 않는다(A6 — 없는 것을 지적하지 않는다).
 */
function DivergedChip({ game }: { game: OverviewGame }) {
  if (game.disk_matches.length > 0) return null;
  if (!game.has_dock && !game.has_internal) return null;
  return <span style={CHIP_STYLE}>{t("SLOT_DIVERGED")}</span>;
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

/**
 * **되돌릴 곳** 한 줄 — 판정은 백엔드의 `target`이고 화면은 문구만 고른다(§5-C ⓐ).
 *
 * ⚠️ `kind`로 고르지 않는다: 파일명이 바뀐 프로필 대피본은 `unknown`으로 접히고 그때 목적지는
 *   게임 설정 파일이다(`restore.parse_backup_id`). 두 값의 파생 규칙이 갈리는 날 화면이
 *   **실제로 쓰이는 곳과 다른 곳**을 가리킨다.
 */
function targetText(row: BackupRow): string {
  if (row.target === "dock" || row.target === "internal") {
    return t("BACKUP_ROW_TARGET_PROFILE", { profile: t(profileKey(row.target)) });
  }
  return t("BACKUP_ROW_TARGET_DISK");
}

/** 목록 행 하나(§5-A). 게임명 + [eGPU 적용][내장 적용][›] + 메타 한 줄. */
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
  /** 이 행에 착지시킬 것인가(§4-E ① — 목록 복귀 시 마지막 조작 행). */
  focused: boolean;
  /** 마운트하면서 **스스로 포커스를 가져올 것인가**(호출부의 `firstCards` 주석이 정본). */
  takeFocus: boolean;
  onApply: (game: OverviewGame, profile: Profile) => void;
  onOpen: (game: OverviewGame) => void;
}) {
  const has: Record<Profile, boolean> = { dock: game.has_dock, internal: game.has_internal };
  return (
    // ★ ROW_FLOW — 이 카드 안의 focusable은 버튼 3개가 **한 줄에 나란히** 서 있다.
    //   빠뜨리면 좌우 키가 죽고 위아래로만 순회한다(2026-08-15 실기 ①).
    //   ★★ 여기가 **실기 ①이 실제로 난 자리**다: 카드 스타일(`CARD_STYLE`)은 flex가 아니라
    //     배경·패딩만 있는 블록이라, 지정이 없으면 Steam의 방향 추정이 `column`으로 떨어진다
    //     (추정 규칙은 `ROW_FLOW` 주석). flex 행인 다른 줄들과 갈리는 지점이 이것이다.
    /* ★★ `autoFocus`가 **같이** 서 있는 이유(D4 — 2026-08-15 실기 타임라인):
         `preferredFocus`는 *"컨테이너로 포커스가 들어올 때 누구를 고를까"*이고, 그 진입은
         **팝업이 처음 그려지는 순간 딱 한 번** 일어난다. 그런데 그때 목록은 아직
         「불러오는 중…」이고 **카드가 존재하지 않는다**(실측: 진입 t+0ms 시점 버튼 1개 ·
         30ms 뒤에 28개). 없는 자식을 고를 수는 없으니 Steam은 문서 순서로 떨어지고 —
         필터 토글이 이긴다. 데이터가 도착해도 **다시 들어오는 일이 없으므로** 포커스는
         거기 머문다(실측: 같은 요소가 y251→y141로 밀려났을 뿐 이동 0회).
         `autoFocus`는 **마운트 시점에** 그 노드가 스스로 포커스를 요청하는 다른 축이라
         (`library.js` `OnMount` → `DeferredFocus.RequestFocus`), 늦게 도착한 카드에도 듣는다.
       ★ 둘은 경쟁하지 않는다 — **같은 카드**를 가리키고, 서로가 못 막는 갈래를 하나씩 맡는다:
         진입이 늦으면 `preferredFocus`(상세→목록 복귀 실측 확인), 진입이 이르면 `autoFocus`.
         한쪽만 두면 그 갈래에서만 조용히 어긋난다.
       ★★ 다만 두 축의 **조건은 다르다**(`focused` vs `takeFocus`): `autoFocus`는 *마운트할
         때마다* 듣기 때문에, 필터를 끄면서 숨었던 카드가 되돌아오는 순간에도 발동해
         **필터 줄에 있던 커서를 목록으로 끌어간다**(실측 (580,141)→(479,421)). 사용자는
         방금 만진 토글 자리에 있길 기대하므로(다시 켤 수도 있다) 그건 포커스 훔치기다.
         → 조건을 **첫 데이터 도착 한 번**으로 좁힌다(호출부 `firstCards`). */
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
              /* 비활성 조건은 **그 프로필이 없을 때**뿐이다(A6의 유일한 시각 표현).
                 실행 중 여부는 여기 들어가지 않는다 — 누르면 백엔드가 거부하고 사유가 note로 뜬다. */
              disabled={busy || !has[p]}
              onClick={() => onApply(game, p)}
              style={{
                ...APPLY_BUTTON_STYLE,
                /* ★ 배열 판정(R13 §5-A): 두 프로필의 내용이 같으면 **두 버튼 모두**에 마커가 선다.
                   12판은 백엔드가 첫 일치만 골라 나머지 한쪽을 "적용 안 됨"이라 거짓말했다. */
                background: game.disk_matches.includes(p) ? MARKED_BACKGROUND : undefined,
              }}
            >
              <span style={ICON_SLOT_STYLE}>{profileIcon(p)}</span>
              {t("APPLY_SHORT", { profile: t(profileKey(p)) })}
              {/* ★ 마커 자리는 **항상** 있다 — 없을 땐 같은 폭의 빈 자리다(GP#2).
                  마커가 있어도 누를 수 있다: 재적용은 백엔드에서 `already`로 무해하다. */}
              <span style={MARKER_SLOT_STYLE}>{game.disk_matches.includes(p) ? <IconCheck /> : null}</span>
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
          <DivergedChip game={game} />
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
  /* ★ 게이트를 **먼저** 만든다: 아래 데이터 훅이 §4-I ⑥에서 결과 팝업을 띄우려면 게이트가
     이미 있어야 한다. `usePopupGate`는 데이터에 의존하지 않으므로 순서만 바꾸면 된다. */
  const { gate, renderBody } = usePopupGate();
  /**
   * 결과 팝업을 띄우는 자리 — **ref로 든다**(§4-I ⑥ 배선).
   * 데이터 훅이 이 함수를 부르는데, 그 함수는 데이터 훅이 준 `setNote`를 쓴다. 순환을 값으로
   * 풀면 한쪽이 반드시 낡으므로 **최신 것을 가리키는 상자**를 둔다(문이 `notify`를 드는 방식 그대로).
   */
  const showResultRef = useRef<(text: string) => void>(() => {});
  /* ★ 변이 통지·재조회·busy는 **훅 한 곳**을 지난다(§4-F 개정) — 이 파일에는 그 배선이 없다. */
  const { data, noteText, setNote, setReloadNote, noteView, busy, reload, runMutation, runQuery } =
    usePopupData<Overview>(load, "LOAD_FAILED", onMutate,
      // §4-I ⑥ — 성공했는데 화면이 못 따라온 경우. **판정은 문이 했고** 여기는 그리기만 한다.
      () => showResultRef.current(t("RESULT_STALE_NOTE")));

  /**
   * **결과 팝업**(§4-I ②·④) — 새 줄이 생기는 통지는 전부 여기로 나간다.
   *
   * ★★ 왜 note가 아닌가: 목록 뷰의 note는 **스크롤 목록 위**에 있어 줄이 하나 생기면 아래 목록
   *   전체가 내려간다 — 방금 누른 행이 손가락 아래에서 움직이는 자리다.
   * ★ 창을 못 띄우면 **그 결과를 note로** 말한다(창이 안 떴다는 사실보다 결과가 중요하다).
   *   그때는 note가 그 사정도 같이 말한다 — 사용자가 왜 여기 적혔는지 알 수 있게.
   */
  const showResult = useCallback(
    (text: string): true => {
      gate(makeResultSpec(<div>{text}</div>), "RESULT_MODAL_FAILED",
           (why) => setNote(`${text} ${why}`));
      // ★ **말했다는 사실**을 문에 돌려준다(§4-I ⑥) — 문은 이걸 보고 stale 창을 겹치지 않는다.
      //   창을 못 띄운 경우에도 note로 말했으므로 사실은 같다(침묵이 아니다).
      return true;
    },
    [gate, setNote],
  );
  showResultRef.current = showResult;

  const games = data?.games ?? [];
  const counts = data?.counts;

  /**
   * **첫 데이터 도착인가** — 카드의 `autoFocus`를 켤 유일한 순간이다(D4 후속).
   *
   * ★ 왜 한 번뿐인가: `autoFocus`가 필요한 갈래는 *"팝업 진입 시점엔 목록이 아직 「불러오는
   *   중…」이라 고를 카드가 없었다"* 하나뿐이다. 그 뒤의 마운트(필터 OFF로 숨었던 카드가
   *   되돌아오는 것)는 **사용자가 다른 곳을 조작하던 중**이라, 같은 prop이 그때는 포커스
   *   훔치기가 된다.
   * ★ 왜 ref를 **effect에서** 내리는가: 렌더 도중 뒤집으면 그 렌더가 버려질 때(동시성 모드의
   *   재실행) 첫 도착을 놓친다. 커밋 뒤에 내리면 화면에 실제로 나간 렌더가 기준이 된다.
   * ★ 목록으로 **돌아올 때**의 착지는 이것과 무관하다 — 진입 컨테이너의 `PREFERRED_CHILD`가
   *   맡는다(`renderList`의 주석 · 실측 확인). 그래서 좁혀도 잃는 갈래가 없다.
   */
  const cardsSeenRef = useRef(false);
  const firstCards = games.length > 0 && !cardsSeenRef.current;
  useEffect(() => {
    if (games.length > 0) cardsSeenRef.current = true;
  }, [games.length]);

  /**
   * **지금 어느 뷰인가** — 아래 두 판정(무엇을 다시 읽는가 · 결과를 말할 것인가)이 이 값에 달렸다.
   *
   * ★ 왜 ref인가: 동작 콜백들은 deps를 고정해 두므로(재생성되면 확인창 안에 갇힌 옛 콜백이
   *   생긴다) 상태를 직접 읽으면 **첫 렌더의 뷰**를 본다. 최신 것을 가리키는 상자를 둔다 —
   *   `showResultRef`가 순환을 푸는 방식 그대로다.
   */
  const viewRef = useRef(view);
  viewRef.current = view;

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
   * **백업 목록을 보고 있으면 그것을 다시 읽는다** — 재조회 판정의 문 하나(D-07 ⓐ 확장).
   *
   * ★★ 왜 호출부가 아니라 여기인가(2026-08-15 QA R1): 백업을 만드는 동작은 복원만이 아니다.
   *   **적용도 `disk` 대피본을 1건 만들고**, 링이 차 있으면 그 순간 목록의 마지막 행이 사라진다.
   *   그런데 재조회가 복원 경로에만 손으로 붙어 있어서, 백업 뷰에서 출발한 적용(복원 후속 제안의
   *   [지금 적용])이 그대로 빠졌다 — **방금 지워진 백업의 [복원] 버튼**이 화면에 남고, 누르면
   *   `BACKUP_FILE_MISSING`이 뜬다. 규칙을 뷰에 묶어 두면 새 동작이 늘어도 따라온다.
   */
  const refreshShownBackups = useCallback(() => {
    const shown = viewRef.current;
    if (shown.kind === "backups") refreshBackups(shown.appid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 적용이 **실제로 쓴 뒤** — 침묵할지 말할지를 여기 한 곳에서 정한다.
   *
   * ★★ 성공 침묵(§4-I ⓪)의 전제는 *"화면이 그 변화를 보인다"*이고, 그 전제는 **뷰마다 다르다**:
   *   목록·상세에는 적용 마커와 슬롯 요약이 있어 참이지만, **백업 목록 뷰에는 둘 다 없다.**
   *   거기서 침묵하면 [지금 적용]을 눌러도 화면이 한 픽셀도 안 바뀌고, **무반응은 곧 고장으로
   *   읽힌다**(A12). 설계가 복원 결과에 대해 같은 근거를 적어 둔 자리(§5-C)와 같은 판단이다.
   * ★ 판정을 호출부에 두지 않는다 — "지금 어느 뷰였더라"를 기억하게 하면 다음에 추가되는
   *   동작이 또 빠뜨린다(이번 결함이 정확히 그렇게 났다).
   */
  const settleApplied = useCallback(
    (profile: Profile): boolean | void => {
      refreshShownBackups();
      if (viewRef.current.kind !== "backups") return;   // 마커가 그 자리에서 옮겨 간다 — 침묵(⓪)
      return showResult(t("APPLY_OK", { profile: t(profileKey(profile)) }));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showResult],
  );

  /**
   * 적용 — **저장된 프로필 → 게임 설정 파일** 한 방향이다(A11). 묻는 조건은 백엔드가 정한다.
   *
   * ★★ 결과를 말하는 규칙이 셋이다(§4-I):
   *   · `applied` → **뷰가 정한다**(`settleApplied`). 마커가 보이는 뷰에서는 침묵, 마커가 없는
   *     백업 뷰에서는 결과 팝업 — 침묵의 전제가 그 화면에서 성립하지 않는다.
   *   · `already` → **결과 팝업.** 아무것도 안 바뀐 것은 화면이 못 보이고, 무반응은 곧 고장으로
   *     읽힌다(A12) — 실기 결함 ③이 정확히 이 자리였다.
   *   · 거부·실패 → **결과 팝업**(사유).
   * ★ `CONFIRM_REQUIRED`는 흐름 신호다: 확인창을 띄우고 **받은 토큰을 그대로** 되돌려 재호출한다.
   *   토큰은 방향에 묶여 있어 다른 프로필에는 소비되지 않는다.
   */
  const runApply = useCallback(
    (game: OverviewGame, profile: Profile, token?: string) => {
      // 확정 실행이다 — 재조회·변경 통지는 **성공·실패를 가리지 않고** 훅이 붙인다(§4-F ③).
      void runMutation(() => applyProfile(game.appid, profile, token), "APPLY_FAILED", (res) => {
        if (res.ok) {
          if (res.data.outcome === "applied") return settleApplied(profile);
          return showResult(t("APPLY_ALREADY", { profile: t(profileKey(profile)) }));
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ApplyConfirmParams;
          gate(
            makeApplyConfirmSpec(p, profile, () => { runApply(game, profile, p.confirm_token); }),
            // 토큰이 안 돌아가면 적용은 일어나지 않는다 — 이 문구가 참인 자리다.
            "APPLY_CONFIRM_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // ★ 실패도 **쓴 뒤일 수 있다**(대피본은 만들고 그 다음 쓰기에서 죽는 갈래) — 백업 뷰에
        //   있다면 목록이 이미 낡았다. 복원의 실패 갈래와 같은 판단·같은 문(D-07 ⓐ).
        refreshShownBackups();
        return showResult(tCode(res.code, "APPLY_FAILED"));
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, settleApplied, showResult],
  );

  /**
   * 저장 — 덮어쓰기라 **백엔드가 확인을 요구할 수 있다.** 빈 슬롯 첫 저장은 묻지 않는다
   * (잃을 것이 없다 — §15-C 정상 동작).
   *
   * ★ 실행 중 저장은 **거부가 아니라 경고**다(engine.py:452-455). 봉투의 `warning`을 성공
   *   note에 병기한다 — 저장은 됐지만 값이 게임 종료 시 달라질 수 있다는 사실이다.
   *
   * ★★ 결과를 말하는 규칙이 **적용과 대칭**이다(§4-I · R13):
   *   · `saved` → **침묵.** 슬롯 상태와 저장 시각이 화면에서 바뀌므로 화면 자체가 결과다.
   *   · `already` → **결과 팝업.** 백엔드가 한 바이트도 쓰지 않은 갈래라 화면이 하나도 안 바뀐다 —
   *     무반응은 곧 고장으로 읽힌다(A12). 적용의 `APPLY_ALREADY`와 같은 자리·같은 문법이다.
   */
  const runSave = useCallback(
    (appid: string, profile: Profile, token?: string) =>
      runMutation(() => saveProfile(appid, profile, token), "SAVE_FAILED", (res) => {
        if (res.ok) {
          if (res.data.outcome === "already") {
            return showResult(t("SAVE_ALREADY", { profile: t(profileKey(profile)) }));
          }
          // ★ 저장 성공은 **침묵**이다(§4-I ⓪·⑤-ⓐ) — 슬롯 상태와 저장 시각이 화면에서 바뀐다.
          //   단 실행 중 저장의 경고는 **화면이 못 보이는 사실**이라 그때만 말한다.
          if (res.data.warning) {
            // ★ 봉투의 `warning`은 **코드**다(R14 #10) — 문장은 여기서 현재 언어로 고른다.
            //   예전에는 백엔드가 한국어 문장을 실어 보내 **영어 화면에 한국어가 붙었다.**
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
            // 토큰이 안 돌아가면 저장은 일어나지 않는다 — "저장하지 않았습니다"가 참이다.
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
   * 복원 — 3-상태 계약(§15-C 불변)이고 기준은 **되돌릴 곳**이다(R13 §5-C ⓑ):
   * `already`는 무쓰기 · 되돌릴 곳이 비어 있으면 무토큰 즉시 · 그 외는 `CONFIRM_REQUIRED`.
   *
   * ★★ **목적지는 봉투의 `target`이 정본**이다 — 프론트가 `kind`로 다시 분류하지 않는다.
   *   두 곳에서 판정하면 언젠가 갈리고, 갈린 순간 *"확인한 곳과 다른 곳에 쓰기"*가 된다.
   * ★★ **성공 뒤 재조회**(D-07): 복원은 대피본을 하나 새로 만든다 — 백업 목록의 행 수·순서가
   *   그 자리에서 바뀌고, 링이 차 있으면 가장 오래된 행이 사라진다. 화면을 그대로 두면
   *   **방금 사라진 백업의 [복원] 버튼**이 남는다.
   * ★ 슬롯 복원 성공은 **후속 제안**으로 잇는다(§5-C ⓔ, 방향 반전): 되돌린 내용은 아직 프로필에만
   *   있고 게임은 옛 설정으로 돈다 — 그 사실을 말하고 **적용할지 묻는다**(확인창 하나로 손실 둘을
   *   승인받지 않으므로, 그 적용 경로가 또 물을 수 있다).
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
            // 실패가 아니다 — 되돌릴 것이 없었다는 뜻이고, 쓰기도 링 소모도 0이다.
            return showResult(slot
              ? t("RESTORE_ALREADY_PROFILE", { profile: t(profileKey(slot)) })
              : t("RESTORE_ALREADY"));
          }
          // ★ 재조회는 **뷰가 정한다**(R1에서 문 하나로 모았다) — 이 경로는 언제나 백업 뷰에서
          //   출발하지만, 규칙이 호출부에 흩어져 있으면 다음 동작이 또 빠뜨린다.
          refreshShownBackups();
          if (slot) {
            gate(
              makeRestoreFollowUpSpec(slot, stamp, () => { runApply(game, slot); }),
              // ★ 여기서는 **복원이 이미 끝났다.** "아무것도 안 했다"고 말하면 거짓이다 —
              //   못 한 것은 후속 제안뿐이고, 그 문구가 남은 길을 알려 준다.
              // ★★ 치환자를 **채워서** 준다(R3): 이 문구는 *"[{profile} 적용]을 눌러 주세요"*로
              //   끝나는데, 값을 안 주면 게이트가 중괄호를 그대로 그려 **어느 버튼인지 지목하지
              //   못한다.** 적용 버튼은 둘이고 틀린 쪽을 누르면 다른 프로필이 게임에 쓰인다.
              { key: "RESTORE_FOLLOWUP_MODAL_FAILED", params: { profile: t(profileKey(slot)) } },
              setNote,
            );
            // 후속 제안 창이 **복원 완료 문장을 품고 있다**(RESTORE_OK_PROFILE) — 창으로 말했다.
            return true;
          }
          // `disk`·`unknown`은 게임 설정 파일로 간다 — 어느 슬롯의 내용인지 추론할 근거가 없다.
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
        // GAME_RUNNING(조기 거부)·BACKUP_FILE_MISSING(그 사이 prune) 등 — tCode 단일 관문.
        refreshShownBackups();
        return showResult(tCode(res.code, "RESTORE_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, refreshShownBackups, runApply, showResult],
  );

  /**
   * 등록 해제 = **등록 말소 + 감지 제외**(A9). 성공하면 목록으로 돌아가고, 사라진 행 대신
   * **인접 행**에 착지시킨다(§4-B) — 방금 지운 자리에 포커스를 두면 어디로 갔는지 알 수 없다.
   */
  const runDelete = useCallback(
    (appid: string, token?: string) =>
      runMutation(() => deleteGame(appid, token), "DELETE_ACTION_FAILED", (res) => {
        if (res.ok) {
          // ★ 침묵(§4-I ⓪) — 목록으로 돌아가고 그 행이 사라진다. 화면 자체가 결과다.
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
        return showResult(tCode(res.code, "DELETE_ACTION_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, showResult],
  );

  /** 백업 뷰로 — 목록을 **먼저 받아** 연다(빈 창이 떴다가 채워지는 중간 상태를 만들지 않는다). */
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
      /* ★★ 목록 뷰의 **진입 컨테이너**다(D4): 카드의 `preferredFocus`는 이 선언이 있는
         컨테이너를 지나 들어올 때만 읽힌다(근거는 `preferredChildEntryProps` 주석 — Steam
         본체 실측). 필터 줄과 목록을 **함께** 품어야 하므로 자리는 여기 하나뿐이다:
         스크롤 목록에 붙이면 팝업 진입이 그 바깥에서 시작해 여전히 필터 줄에 선다. */
      <Focusable {...preferredChildEntryProps} style={COLUMN_STYLE}>
        <Focusable {...ROW_FLOW} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
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

        <PopupScrollList>
          {shown.map((game, index) => {
            // 두 축이 **같은 행**을 가리킨다(GameCard 주석). 조건만 다르다.
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

        {/* ★★ note는 **목록 아래**다(§4-I ③ · 실기 결함 ③의 재발 방지). 목록 위에 두면 줄이
            하나 생길 때마다 **아래 목록 전체가 내려가** 방금 누른 행이 손가락 아래에서 움직인다.
            남은 소비자는 「화면이 낡았다」(재조회 실패 둘째 줄)와 결과 창을 못 띄웠을 때의
            대타뿐이다 — 동작 결과는 전부 결과 팝업으로 나간다(§4-I ②). */}
        {noteView}

        {/* ★ 「모르는 것을 없다고 말하지 않는다」 — data가 null인 것은 로딩 중이거나 조회
            실패이지 0개가 아니다. 실패 문구는 note가 이미 그린다. */}
        {renderListTail()}

        {/* ★ U-8: 제외된 게임이 있을 때만 한 줄. 0건이면 완전 미표시다(A6 간결·"0이면 안 그림").
            ★★ **수를 말하지 않는다**(2026-08-12 P16 게이트 C1): 표시 조건에 쓰는 `counts.excluded`는
              **원본 키 수**(raw)이고, 이 안내가 가리키는 제외 뷰는 **손상 항목을 격리한 뒤의 rows**를
              보여 준다(설계 §15-D E5). 조건에 raw를 쓰는 것은 옳지만(A9 ④ 도달성), 같은 수를
              *"거기서 볼 수 있습니다"*라는 약속에 재사용하면 그 약속이 어긋난다.
              수를 아예 안 말하면 **어긋날 자리가 소멸한다** — 문구에 자리표시자가 없다.
            ★★ 12판(§5-A): 같은 이유가 *"볼 수 있습니다"* 에도 적용돼 **가시성 약속을 위치 진술로
              낮췄다**(손상 기록만 남으면 제외 화면에 그릴 행이 0이라 약속이 거짓이 된다).
              ⚠️ **경로를 지운 것이 아니다** — 제외된 게임을 되찾는 유일한 동선이므로
              "[게임 감지]의 「제외한 게임」에 있습니다"는 그대로 남는다(행이 0이어도 참이다). */}
        {counts && counts.excluded > 0 ? (
          <div style={META_STYLE}>{t("GAMES_EXCLUDED_NOTE")}</div>
        ) : null}
      </Focusable>
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
  /**
   * 상태 줄 **4분기**(R13 §5-B) — `disk_matches`가 배열이 되면서 「둘 다와 같음」이 생겼다.
   *
   * ★ `PROFILES_IDENTICAL`(H3)과 **중복이 아니다**: 저쪽은 *저장 기록상 두 슬롯이 서로 같다*이고,
   *   이쪽은 *지금 게임 파일이 그 둘과 같다*이다. 두 사실은 따로 참일 수 있다.
   * ★ 프로필이 하나도 없으면 줄 자체를 그리지 않는다(A6 — 없는 것을 지적하지 않는다).
   */
  function statusLine(game: OverviewGame) {
    if (game.disk_matches.length >= 2) return t("GAME_DETAIL_STATUS_BOTH");
    const only = game.disk_matches[0];
    if (only) return t("GAME_DETAIL_STATUS", { profile: t(profileKey(only)) });
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
        {game.config_path ? <div style={PATH_STYLE}>{t("GAME_CONFIG_PATH", { path: game.config_path })}</div> : null}
        {/* ★ H3-ⓐ: 게임별 재촉이 아니라 **조작 방법 설명**이다(F10 성격 — A6와 무관).
            ★★ 12판: 한 키 두 문장을 **두 키·두 요소**로 나눴다(§5-B) — 값에 개행을 넣어도
              `white-space` 미지정이라 한 줄로 이어붙었다. 순서는 **아래 저장 버튼 2개와 같다**
              (dock → internal): 어긋나면 사용자가 줄과 버튼을 짝짓지 못한다.
            ★ "게임을 종료하고"가 핵심이다 — 게임은 종료할 때 설정 파일을 다시 쓰므로, 실행 중에
              저장하면 디스크에 남은 옛 값이 저장될 수 있다. 사후 방어(`SAVE_DESC_RUNNING`)는
              그대로 두되, 안내가 미리 말하면 실수 자체가 생기지 않는다. */}
        <div style={HINT_STYLE}>{t("SAVE_GUIDE_DOCK", { dock: t("PROFILE_DOCK") })}</div>
        <div style={HINT_STYLE}>{t("SAVE_GUIDE_INTERNAL", { internal: t("PROFILE_INTERNAL") })}</div>

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
    // 프로필로 되돌아가는 행이 있을 때만 "그 뒤에 물어본다"고 예고한다 —
    // 조건 없는 약속은 실사용 다수인 `disk` 행에서 거짓이 된다(2026-08-10 QA R2의 교훈).
    // ★ 판정은 **`target`**이다(R13): `kind`로 고르면 파일명이 바뀌어 `unknown`으로 접힌 행에서
    //   화면과 실제 목적지가 갈린다(`targetText`와 같은 근거·같은 값).
    const hasProfileRow = rows.some((r) => r.target !== "config");
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
              {/* ★★ 카드 안쪽은 **목록 카드와 같은 이중 구조**다(`CARD_INNER_STYLE` 바깥 ·
                  `ROW_STYLE` 안쪽). 두 상수를 **한 div에 펼쳐 합치지 않는다**: `CARD_INNER_STYLE`은
                  세로 스택(`flexDirection:"column"`)이고 `ROW_STYLE`에는 방향이 없어서, 합치면
                  방향이 `column`으로 살아남고 `alignItems:"center"`가 가로 중앙으로 작동해
                  **텍스트가 가운데로 좁아지고 [복원]이 그 아래로 내려간다**(2026-08-15 실측:
                  inner `flex-direction:column` · 글 x339 w240 · 버튼 x412 y377).
                  같은 것은 같은 방법으로 그린다 — 폭 상한은 바깥, 가로 배치는 안쪽. */}
              <div style={CARD_INNER_STYLE}>
                <div style={ROW_STYLE}>
                  <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                    <div style={{ fontSize: "14px" }}>
                      {kindText(row)}
                      {/* ★ 되돌릴 곳의 **지금 내용이 이 백업과 같다**(§5-C ⓒ) — 누르기 전에 말하면
                          "아무 일도 안 일어났다"는 결과 팝업이 뜰 이유 자체가 준다.
                          ⚠️ 모르면 백엔드가 false를 주므로 배지가 안 뜬다(없는 사실을 만들지 않는다). */}
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
                    {/* ★★ **되돌릴 곳**을 행마다 고정 한 줄로 말한다(§5-C ⓐ·ⓒ). 값은 백엔드가 준
                        `target`이고 프론트는 `kind`로 재분류하지 않는다 — 두 곳에서 판정하면
                        화면이 가리키는 곳과 실제로 쓰이는 곳이 갈리는 날이 온다. */}
                    <div style={META_STYLE}>{targetText(row)}</div>
                  </div>
                  {/* ★ 같은 내용이어도 **비활성화하지 않는다**(§5-C ⓒ): 패드에서 비활성 버튼은
                      포커스를 못 받아 사용자가 이유를 알 길이 없다. 눌리면 백엔드가 무쓰기로
                      끝내고 결과 팝업이 그 사실을 말한다. */}
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

  // ── 뷰 선택 ────────────────────────────────────────────────────────────────
  //
  // ⚠️ *"분기를 한 줄에 이어 쓰지 않는다"*(`A /> : x ? <B` 금지)는 관례의 **근거는 소멸했다** —
  //   그 사이의 코드를 화면 글자로 오인하던 `qa/test_i18n_sets.py`는 2026-08-15 UI 검사 계열
  //   삭제에 함께 지워졌다. 지금 이 관례를 강제하는 것은 없다. 아래처럼 **이른 반환 문장으로
  //   나눠 쓰는 형태**는 읽기 쉬워서 유지할 뿐이고, 어겨도 깨지는 검사는 이제 없다.
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
