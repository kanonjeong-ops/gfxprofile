import { definePlugin, toaster, useQuickAccessVisible } from "@decky/api";
import { useCallback, useEffect, useState, type ReactElement, type ReactNode } from "react";
import {
  applyAll,
  getOverview,
  type ApplyAllConfirmParams,
  type ApplyAllResult,
  type ApplyRow,
  type Env,
  type Outcome,
  type Overview,
  type OverviewCounts,
  type Profile,
} from "./rpc";
import { ensureLang, setProfileNames, t, tCode, type StringKey } from "./i18n";
import { PLUGIN_VERSION } from "./version";
import { BulkApplyButton } from "./BulkApplyButton";
import { ErrorBoundary } from "./ui/ErrorBoundary";
import { CARD_STYLE, ICON_SLOT_STYLE, KEEP_ALL_STYLE, SpecConfirmModal, useDataDoor } from "./popup";
import { makeApplyAllConfirmSpec } from "./confirmSpecs";
import { GamesPopup } from "./GamesPopup";
import { DiscoverPopup } from "./DiscoverPopup";
import { SettingsPopup } from "./SettingsPopup";
import { IconCheck, IconGear, IconList, IconSearch, IconWarn } from "./icons";
import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  showModal,
  titleClass,
  uicheckMissing,
} from "./deckyui";

// ── 진단 태그 ────────────────────────────────────────────────────────────────
// 로그는 여러 로드분이 한 파일에 쌓이므로, 태그에 이번 프론트 로드를 가리키는 nonce(fn)가
// 없으면 이번 로드의 줄을 과거 것과 구분할 수 없다. 태그를 만드는 자리가 `failTag` 하나라
// fn이 빠질 자리가 없다.
// 이 문자열들은 의도적으로 번역하지 않는다 — 번역되면 진단 grep이 언어에 따라 깨진다.

const FN = Math.random().toString(36).slice(2, 6);

// 진단을 두 경로로 남긴다.
// · 정상 신호는 `ui_hello`를 통해 백엔드 로그에 남긴다.
// · 프론트 실패는 `failTag`가 `console.error`와 fn 태그로 남긴다.
function failTag(msg: string): void {
  console.error(`[gfxprofile] ${msg} fn=${FN}`);
}

const PROFILE_KEY: Record<Profile, StringKey> = {
  dock: "PROFILE_DOCK",
  internal: "PROFILE_INTERNAL",
};

/**
 * 일괄 적용 결과를 화면 최대 3줄로 줄인다.
 *
 * 목록이 아니라 요약인 이유: 등록 게임이 200개까지 갈 수 있어 전량 나열이 성립하지 않는다.
 *   화면은 지금 뭘 해야 하는지를, 로그는 나중에 뭐가 있었는지를 맡는다 — 상세는 백엔드
 *   로그의 `problems=`가 보관한다(`Plugin.apply_all`).
 *
 * `outcome`이 아니라 `code`로 가르는 이유: `refused` 하나에 여러 코드가 뭉쳐 있고, 조치가
 *   균일한 것은 `GAME_RUNNING` 하나뿐이다. 나머지(프로필 없음·손상·백업 실패·경로 이상 …)는
 *   게임마다 조치가 달라서, 전부에 "종료 후 재시도"라고 말하면 틀린 처방이 된다.
 */
const CAP_NAMES = 3;

/** 이름 나열 한 줄 — 넘치면 `NAMES_AND_MORE`로 접는다. 두 사유 줄이 같은 규칙을 쓴다. */
function namesOf(rows: ApplyRow[]): string {
  const shown = rows.slice(0, CAP_NAMES).map((r) => r.name).join(", ");
  const more = rows.length - CAP_NAMES;
  return more > 0 ? t("NAMES_AND_MORE", { names: shown, n: more }) : shown;
}

/**
 * 직전 일괄 적용의 결과. 수신 시각까지 여기 담는다 — 봉투에는 시각이 없고, 화면이 결과를
 * 받은 순간이 곧 "언제 있었던 일인가"의 정본이다(봉투 확장 0).
 */
interface ApplySummary {
  headline: string;
  hints: string[];
  /** 문제 행이 하나라도 있었는가 — 제목 아이콘을 가른다(체크 / 주황 경고). */
  problems: boolean;
  at: number;
}

function buildSummary(
  profile: Profile,
  rows: ApplyRow[],
  counts: Partial<Record<Outcome, number>>,
): ApplySummary {
  const running = rows.filter((r) => r.code === "GAME_RUNNING");
  // 조치가 게임마다 다른 것 = 코드가 있는데 GAME_RUNNING이 아닌 것 + 코드 없는 error
  const specific = rows.filter(
    (r) => (r.code && r.code !== "GAME_RUNNING") || (r.outcome === "error" && !r.code),
  );
  const applied = counts.applied ?? 0;
  const profileName = t(PROFILE_KEY[profile]);

  const headline =
    applied === 0 && running.length === 0 && specific.length === 0
      ? t("APPLY_ALL_UNCHANGED", { profile: profileName })
      : t("APPLY_SUMMARY", { profile: profileName, total: rows.length, applied });

  const hints: string[] = [];
  // 이름을 말한다. "실행 중인 게임 3개"로는 어느 게임을 끄면 되는지 알 수 없어 사용자가 할 수
  //   있는 일이 없다. 이름은 결과 행에 이미 실려 있다(봉투 확장 0).
  if (running.length > 0) hints.push(t("APPLY_PROBLEM_REFUSED", { names: namesOf(running) }));

  // 사유를 화면에 낸다. Game Mode에는 터미널이 없어 "사유는 로그를 확인하십시오"는 사용자가
  //   따를 수 없는 안내다. `row.code`는 엔진이 병기해 프론트까지 와 있으므로, 엔진을 손대지
  //   않고 코드→문장 사전만으로 채운다.
  // 코드별로 묶는다. 뭉쳐서 한 사유만 말하면 나머지 게임에는 틀린 처방이 된다(위 `CAP_NAMES`
  //   주석의 갈래 근거). 묶음 수는 자르지 않는다 — 자르면 그 게임이 화면에서 통째로 사라진다.
  //   묶음 수는 서로 다른 실패 코드 수라 실사용에서 한두 개이고, 각 묶음은 이미 이름을
  //   `CAP_NAMES`로 자른다. 넘침 처리를 만드는 대신 넘칠 구조를 안 만든다.
  const byCode = new Map<string, ApplyRow[]>();
  for (const r of specific) {
    const code = r.code || "UNEXPECTED";     // 코드 없는 error도 사유가 있어야 한다
    const bucket = byCode.get(code);
    if (bucket) bucket.push(r);
    else byCode.set(code, [r]);
  }
  const groups = [...byCode.entries()].sort(
    (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]),
  );
  for (const [code, group] of groups) {
    hints.push(t("APPLY_PROBLEM_SPECIFIC", {
      names: namesOf(group),
      reason: tCode(code, "APPLY_FAILED"),
    }));
  }
  return {
    headline,
    hints,
    problems: running.length > 0 || specific.length > 0,
    at: Date.now(),
  };
}

/**
 * 왕복이 통째로 죽은 것(RPC 거절)을 실패 봉투로 바꾼다.
 *
 * 이 화면에는 "응답이 없었다"와 "실패 봉투가 왔다"가 같은 사실이다 — 일괄 적용이 끝나지
 *   못했고 무엇이 쓰였는지 모른다. 갈래를 둘로 두면 한쪽만 고쳐지는 날이 오고, 실제로 그렇게
 *   한쪽이 오래 침묵했다(아래 `runApplyAll`의 실패 갈래가 그 자리다).
 */
function deadApply(err: unknown): Env<ApplyAllResult> {
  failTag(`apply-all-failed err=${String(err)}`);
  return { ok: false, code: "UNEXPECTED", params: {} };
}

/**
 * 끝내지 못한 일괄 적용의 요약.
 *
 * 실패도 「직전 결과」에 남기는 이유: 확정 실행은 성공·실패를 가리지 않고 다시 읽으므로,
 *   실패 직후의 조회가 성공하면 현재군의 실패 줄은 수명 규칙대로 거둬진다. 그러면 "일괄
 *   적용이 도중에 멈췄다"가 화면 어디에도 안 남는다 — 오래 사는 자리는 과거군뿐이다.
 *   사유(`hints`)도 여기 함께 실어 보낸다.
 * 문구는 현재군 실패 줄과 겹치지 않는다: 저쪽은 왜 실패했나(코드), 이쪽은 그래서 지금 무슨
 *   상태인가(일부는 이미 바뀌었을 수 있다)이다.
 */
function stoppedSummary(profile: Profile, code: string): ApplySummary {
  return {
    headline: t("APPLY_ALL_STOPPED", { profile: t(PROFILE_KEY[profile]) }),
    hints: [tCode(code, "APPLY_FAILED")],
    problems: true,
    at: Date.now(),
  };
}

/**
 * 화면이 실패를 받은 시각까지 들고 있는다 — 언제 있었던 일인지가 사유만큼 중요하다.
 *
 * 사유를 누가 지었는가로 모양을 가른다. `tCode(code, fallback)`은 i18n에 등재된 코드면
 *   fallback 키를 항상 버린다 — 그것이 단일 관문의 정의이고, 백엔드가 준 코드에 대해서는
 *   옳다. 그런데 이 한 모양에 성질이 다른 둘이 들어온다: 백엔드가 준 코드와, 화면이 스스로
 *   지어낸 사유("확인창을 못 띄웠다" 같은). 뒤쪽을 그 관문에 넣으면 화면이 고른 이름이
 *   등재돼 있는 순간 호출부가 준 key가 통째로 사문이 된다 — `"UNEXPECTED"`가 등재된 키라
 *   "예기치 못한 오류"만 뜨고, 저장이 죽었는지 삭제가 죽었는지 화면이 말하지 못한다.
 * 등재되지 않은 문자열을 골라 피하는 규약은 막기이지 구조가 아니다 — 누군가 그 문자열을
 *   i18n에 등재하는 것만으로 나머지가 조용히 깨진다.
 * 그래서 갈래를 타입으로 만든다. 실패를 만드는 자리는 전부 출처를 밝혀야 하고(컴파일러가
 *   강제한다), 화면이 지어낸 사유가 `tCode` 관문에 닿는 경로 자체가 없어진다. 무엇을
 *   등재하든 동작이 안 변한다. 그리는 자리는 `renderStatusBox`의 실패 슬롯 하나다.
 * 필드 이름도 갈라 둔다(`code` / `reason`). 판별자만 갈라 두면 유니온은 "출처를 밝혀라"까지만
 *   강제한다 — 두 갈래의 모양이 같으면 렌더를 다시 `tCode(failure.code, …)` 한 줄로 되돌려도
 *   컴파일이 통과한다. 이름이 갈라져 있으면 그 줄이 그 자리에서 깨진다.
 */
type Failure =
  /** 백엔드가 준 코드다 — 코드→문구의 단일 관문(`tCode`)을 지난다. */
  | { kind: "code"; key: StringKey; code: string; at: number }
  /** 화면이 지어낸 사유다 — `key`가 곧 문장이고, `reason`은 `{code}` 자리를 채우는 꼬리표다. */
  | { kind: "local"; key: StringKey; reason: string; at: number };

// 마지막 일괄 적용 요약은 컴포넌트 밖에 둔다. QAM을 닫으면 패널이 언마운트되므로 상태에만
//   두면 "무슨 일이 있었는지"가 창을 닫는 순간 없어진다. 결과는 화면 수명보다 오래 남아야
//   한다.
let lastSummary: ApplySummary | null = null;

// 실패도 같은 수명이다. 성공만 모듈 변수로 살아남으면 "뭔가 안 됐다"가 성공보다 짧게 사는
//   비대칭이 된다. 소거 시점은 다음 동작 시작(새 일괄 적용 / 새 로드 성공)뿐이다.
let lastFailure: Failure | null = null;

/**
 * 살아 있는 QAM 인스턴스들 — 모듈 변수가 바뀌면 여기로 알린다.
 *
 * 모듈 변수는 수명을 해결하지만 전달은 해결하지 않는다. `useState(lastSummary)`는 마운트 그
 *   순간 한 번 읽는데, 확인 모달이 열려 있는 동안 QAM 패널은 언마운트되고 일괄 적용은 그
 *   사이에 끝난다. 완료 콜백은 이미 죽은 인스턴스의 setState를 부르고, 그보다 먼저 재마운트된
 *   새 인스턴스는 `useState`를 이미 지나쳐 결과를 영영 모른다.
 * 고치는 방향은 새 상태를 만드는 것이 아니라 전달 시점을 여는 것이다 — 값의 정본도 수명도
 *   안 바뀐다.
 * 문은 하나다: 아래 두 함수 말고 `lastSummary`·`lastFailure`에 대입하는 자리를 두지 않는다.
 *   값과 통지가 한 함수 안에 묶여 있으면 "값은 바꿨는데 알리는 걸 잊는" 경로가 생길 수 없다.
 */
const statusListeners = new Set<() => void>();

/** 결과 요약을 바꾸는 유일한 문 — 모듈 변수와 통지가 함께 움직인다. */
function setLastSummary(next: ApplySummary | null) {
  lastSummary = next;
  statusListeners.forEach((notify) => notify());
}

/** 실패를 바꾸는 유일한 문(요약과 같은 규칙 — 수명 대칭을 전달에서도 지킨다). */
function setLastFailure(next: Failure | null) {
  lastFailure = next;
  statusListeners.forEach((notify) => notify());
}

/**
 * QAM 잔글씨 — 설명 줄과 카운트 줄이 쓴다.
 *
 * `wordBreak: "keep-all"`은 낱말 중간 줄바꿈을 막는다. 이 자리의 컨테이너는 268px이라 36자
 *   문장이 반드시 두 줄로 감기는데, CSS 기본값은 한국어를 글자 단위로 끊어 `QAM_ABOUT`이
 *   "…게임만 대상 / 으로 합니다."로 갈라졌다. 문장을 짧게 다듬는 대신 속성을 거는 이유는 이
 *   자리를 쓰는 모든 한국어 문장이 함께 고쳐지기 때문이다.
 *   사유·소비자·제외 규칙의 정본은 `popup.tsx`의 `KEEP_ALL_STYLE` 주석이다.
 */
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;

const MUTED_COLOR = "#9aa0a6";
/** 주의색은 주황 하나다 — 빨강은 쓰지 않는다. */
const WARN_COLOR = "#ffb454";

/**
 * 상태박스 — 최대 2장의 결과 카드를 세로로 쌓는다(위=현재군, 아래=과거군).
 *
 * 군 간 간격의 문은 여기 하나다. 카드 쪽 margin으로도 벌릴 수 있지만 값이 두 곳에 살면
 *   한쪽만 고치는 날 군 간격이 어긋난다(4+8=12px). 컨테이너가 gap을 소유하고 카드는
 *   `marginBottom:0`으로 목록용 4px를 덮는다 — 간격을 말하는 자리를 하나로 만든 것이다.
 * 부수 효과로 "현재군이 없을 때 과거군에 여백이 붙는" 형태 자체가 없어졌다: gap은 자식
 *   사이에만 적용되므로 카드가 하나면 여백이 생길 곳이 없다.
 */
const STATUS_STACK_STYLE = { display: "flex", flexDirection: "column", gap: "8px" } as const;

/**
 * 결과 카드 — 팝업 목록 카드와 같은 시각 언어다(`CARD_STYLE` 정본 1곳 재사용).
 *
 * 외곽 테두리 박스는 쓰지 않는다. 투명 배경 + 테두리 상자는 "로그창도 카드도 아닌 테두리 친
 *   문단"으로 읽히고, 묶음을 채운 배경으로 그리는 것이 이 화면들의 관용구다.
 * 정직성: 지금 데이터는 로그가 아니다(요약 1건 + 실패 1건, 이력 없음). 카드형은 "기록이 더
 *   있다"는 약속을 하지 않는 형태다.
 */
const STATUS_CARD_STYLE = {
  ...CARD_STYLE,
  marginBottom: "0",
  fontSize: "12px",
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  // 위 `HINT_STYLE`과 같은 사유 — 이 카드의 줄들도 268px 안에서 감기는 한국어 문장이다.
  //   상속되는 속성이지만 이 카드 안에는 경로·파일명 슬롯이 없다 — QAM은 경로를 그리지 않는다.
  wordBreak: "keep-all",
} as const;

/**
 * 과거군 카드의 머리 행 — 좌: 성패 아이콘 / 우: 수신 시각.
 *
 * 가변 텍스트는 이 행에 없다. 고정폭 둘 사이는 그냥 빈 공간이다. 아이콘·헤드라인·시각을 한
 *   flex 행에 두면 268px에서 세 항목이 낱자로 감겨 무너진다 — 헤드라인에 `minWidth:auto`가
 *   걸리고 시각에 `flexShrink`가 없기 때문이다. 규약으로 지키는 대신 어길 자리가 없는
 *   형태로 나눴다: 고정폭은 이 행에, 가변 텍스트는 전폭 블록 줄에.
 */
const RESULT_HEAD_STYLE = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
} as const;

/** 결과 진술 한 덩어리(머리 행 + 헤드라인) — 카드의 다른 줄들과 같은 층위의 "한 줄"이다. */
const RESULT_BLOCK_STYLE = { display: "flex", flexDirection: "column", gap: "4px" } as const;

/**
 * 헤드라인 — 전폭 블록이고 자연 줄바꿈이다.
 * ellipsis를 걸지 않는다: 수를 자르면 화면이 거짓을 말한다("전체 10개 중 8개…").
 */
const HEADLINE_STYLE = { fontWeight: "bold" } as const;

/** 수신 시각 — 고정폭 취급이라 줄어들지 않는다(flexShrink:0). 회색. */
const STAMP_STYLE = { flexShrink: 0, color: MUTED_COLOR } as const;

/**
 * 결과·실패를 받은 시각. 당일이면 `14:32`, 다른 날이면 `08-10 14:32`.
 *
 * 번역하지 않는다: 숫자와 구분 기호뿐이라 언어에 따라 달라질 글자가 없다. 달라져야 하는
 *   것은 12/24시간 표기인데 그 설정을 읽는 통로가 이 플러그인에 없다 — 지어내는 대신
 *   24시간 고정으로 한 가지 뜻만 갖게 한다.
 */
function stampOf(at: number): string {
  const two = (n: number) => String(n).padStart(2, "0");
  const d = new Date(at);
  const hm = `${two(d.getHours())}:${two(d.getMinutes())}`;
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  return sameDay ? hm : `${two(d.getMonth() + 1)}-${two(d.getDate())} ${hm}`;
}

/**
 * 일괄 버튼 아래 사유 한 줄. `ButtonItem`의 `description` 슬롯으로 그린다.
 *
 * 숫자가 말하지 못하는 것만 말한다: `total === 0`일 때만 줄이 선다. `total > 0 && ready === 0`은
 *   라벨의 `(0개)`가 이미 같은 말을 하므로 줄을 그리지 않는다. 갈 곳 안내는 카운트 줄의
 *   `NO_GAMES`가 전담한다.
 * 이 식에는 `running`이 들어가지 않는다. 파생 재료는 `total` 하나다 — 실행 중인 게임은 일괄
 *   적용을 막지 않으므로 "왜 못 누르는가"의 사유가 될 수 없고, 여기서 한 번 running을 읽으면
 *   그 값이 활성 조건으로 새어 들어갈 길이 생긴다.
 * `counts`가 아직 없으면 아무 말도 하지 않는다 — 등록 수를 모르는 동안 "적용할 게임이
 *   없습니다"라고 말하면 화면이 거짓을 말한다.
 * 두 버튼이 같은 값을 받는 것이 계약이다 — 그래서 `profile` 인자가 없다.
 */
function bulkHint(counts: OverviewCounts | undefined): string | undefined {
  if (!counts) return undefined;
  if (counts.total === 0) return t("BULK_NO_GAMES");
  return undefined;
}

/**
 * QAM의 팝업 진입 버튼 하나 — 아이콘 + 라벨 + 설명 한 줄.
 *
 * 설명(`description`)은 "거기서 무엇을 하는가"를 말한다: 진입 안내를 상단 설명 영역에 몰아
 *   넣으면 그 문단이 매번 읽히는 소음이 되고, 정작 버튼 옆은 비어 있다.
 */
function EntryButton({
  icon,
  label,
  desc,
  onOpen,
}: {
  icon: ReactNode;
  label: string;
  desc: string;
  onOpen: () => void;
}) {
  return (
    <PanelSectionRow>
      {/* 아이콘은 children 안이다. `icon` prop은 버튼 내용이 아니라 Field의 라벨 슬롯이라
          `layout="below"`+라벨 없음에서 버튼 위 26px에 고아로 뜬다.
          관용구는 프로젝트에 하나 — `ICON_SLOT_STYLE`(popup.tsx). */}
      {/* 설명은 span으로 감싸 넘긴다 — `description`은 style을 받지 않는 prop이라
          한국어 낱말 보존(`KEEP_ALL_STYLE`)을 거는 통로가 이것뿐이다. 감싸도 슬롯은 그대로
          Field의 설명 자리이고, 글자·배치는 변하지 않는다. */}
      <ButtonItem
        layout="below"
        description={<span style={KEEP_ALL_STYLE}>{desc}</span>}
        onClick={onOpen}
      >
        <span style={ICON_SLOT_STYLE}>{icon}</span>{label}
      </ButtonItem>
    </PanelSectionRow>
  );
}

function Content() {
  const missing = uicheckMissing();
  const visible = useQuickAccessVisible();

  // langReady = ui_hello가 (성공이든 실패든) 끝났다 = 어느 언어로 그릴지 확정됐다.
  // 이것을 기다렸다가 그리기 때문에 "영어로 그렸다가 한국어로 바뀌는" 깜빡임이 없다 —
  // 폴백 문구를 나중에 갈아끼우는 처리를 만드는 대신 그 상황 자체를 없앴다.
  const [langReady, setLangReady] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  // 초기값을 모듈 변수에서 받으므로 QAM을 닫았다 열어도 남아 있다(요약·실패 모두).
  const [failure, setFailureState] = useState(lastFailure);
  /** busy 중 요청 단계: 토큰 없음은 확인 자료 요청, 토큰 있음은 확정 실행 시도다. 실제 결과는 응답이 정한다. */
  const [previewing, setPreviewing] = useState(false);
  const [summary, setSummary] = useState(lastSummary);

  /**
   * 모듈 변수의 변화를 살아 있는 동안 계속 따라간다.
   *
   * 해제는 반환값이 한다. 언마운트한 인스턴스가 목록에 남으면 죽은 setState가 계속 불린다.
   */
  useEffect(() => {
    const sync = () => {
      setSummary(lastSummary);
      setFailureState(lastFailure);
    };
    statusListeners.add(sync);
    // 마운트(`useState`)와 이 구독 사이에도 결과가 도착할 수 있다 — 그 틈을 여기서 닫는다.
    //   단 어긋났을 때만 맞춘다: 조건 없이 부르면 재렌더가 하나 더 늘고, 그 한 번이 공용 문의
    //   조회를 다시 켠다.
    if (lastSummary !== summary || lastFailure !== failure) sync();
    return () => { statusListeners.delete(sync); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 실패는 모듈 변수와 상태를 함께 움직인다 — 두 곳에 각자 쓰면 언젠가 갈린다.
   * 상태는 위 구독이 받는다(문이 하나라 이 함수가 setState를 직접 부를 이유가 없다).
   */
  const setFailure = useCallback((next: Failure | null) => {
    setLastFailure(next);
  }, []);

  /**
   * 결과도 모듈 변수와 상태를 함께 움직인다(실패와 같은 규칙) — 그리고 토스트도 여기서
   * 나간다. 결과가 잡히는 자리를 하나로 두면 "성공만 토스트가 나가는" 비대칭이 생길 자리가
   * 없다. 토스트는 QAM이 닫혀 있어도 닿는 부가 채널일 뿐이고, 실패해도 요약 줄은 이미
   * 붙잡혀 있다.
   */
  const keepSummary = useCallback((next: ApplySummary) => {
    // 모듈 변수 + 통지가 한 문이다 — 이 화면이 그 사이 언마운트됐어도 살아 있는 화면이
    // 결과를 받는다. 죽은 인스턴스에 setState를 부르던 자리가 이것이었다.
    setLastSummary(next);
    try {
      toaster.toast({ title: next.headline, body: next.hints.join(" · ") });
    } catch (err) {
      failTag(`toast-failed err=${String(err)}`);
    }
  }, []);

  /**
   * 현황 조회 — 팝업 3종과 같은 문을 지난다.
   *
   * QAM은 `usePopupData`를 쓰지 않는 네 번째 소비자라, 조회·변이를 손으로 배선하면 그 문의
   *   세 보증(세대 가드 · 확정 실행의 재조회 · 실패 봉투 판독)을 하나도 못 받는다. 그러면
   *   낡은 응답이 카운트를 되돌리고, 낡은 실패가 최신 성공 위에 주황 줄을 세우고, 일괄 적용
   *   실패 봉투의 체크인이 통째로 침묵한다. 화면 표현(상태박스·받은 시각·QAM 재개방 승계)은
   *   팝업과 다르므로 표현만 sink로 내주고 규칙은 공유한다 — QAM 전용 가드를 덧대는 방식은
   *   같은 사고를 다섯 번째 소비자에게 남긴다.
   * `refresh`는 여러 번 불려도 다시 읽는 일만 한다: 팝업의 `onMutate`는 거부·실패에도
   *   발화해 한 동작에 여러 번 오고, 그때마다 다른 일을 하면 화면이 흔들린다.
   */
  const load = useCallback(() => getOverview(), []);
  const door = useDataDoor<Overview>(load, {
    onData: (data) => {
      // 표시명을 먼저 반영한다 — 라벨이 그려지기 전이어야 이름이 안 깜빡인다.
      setProfileNames(data.profile_names);
      setOverview(data);
      // 새 로드 성공 = 다음 동작의 시작이다 — 승계해 온 실패를 여기서 거둔다.
      setFailure(null);
    },
    // 봉투가 준 코드다 — `tCode` 단일 관문이 맞는 자리다(`kind:"code"`).
    onLoadFail: (code) => {
      setFailure({ kind: "code", key: "LOAD_FAILED", code, at: Date.now() });
    },
    // 조회 왕복이 통째로 죽었다 — 봉투가 없으니 백엔드 코드도 없다(`kind:"local"`).
    //   이 갈래를 `onLoadFail("UNEXPECTED", err)`로 합치면 등재된 그 코드가 `LOAD_FAILED`를
    //   이겨 "현황을 못 읽었다"는 사실이 화면에서 사라진다.
    onLoadDead: (err) => {
      // 백엔드에 닿지 못한 경우다 — 남길 곳이 cef_log뿐이라 `failTag`로 진단을 남긴다.
      failTag(`overview-failed err=${String(err)}`);
      setFailure({ kind: "local", key: "LOAD_FAILED", reason: "UNEXPECTED", at: Date.now() });
    },
    // 왕복이 통째로 죽은 갈래 — 일괄 적용은 아래에서 스스로 봉투로 바꿔 받으므로 여기 오지
    // 않는다. 남겨 두는 것은 그 밖의 죽음(호출이 그 자리에서 던지는 경우)을 위한 자리다.
    onCallFail: (key, err) => {
      failTag(`call-failed key=${key} err=${String(err)}`);
      // 봉투가 없다 = 백엔드가 준 코드도 없다. `"UNEXPECTED"`는 화면이 붙인 꼬리표이므로
      //   `kind:"local"`이다 — `tCode`에 넣으면 그것이 등재된 키라 호출부가 준 `key`를 이겨
      //   무엇이 죽었는지가 사라진다. 팝업 쪽 같은 갈래와 같은 처분이다
      //   (`popup.tsx`의 `onCallFail: (key) => setNote(t(key, { code: "UNEXPECTED" }))`).
      setFailure({ kind: "local", key, reason: "UNEXPECTED", at: Date.now() });
    },
  });
  const refresh = door.reload;
  /** 쓰는 왕복이 도는 중인가 — 조회(재조회)는 "적용 중"이라 말하지 않는다. */
  const busy = door.mutating;
  /**
   * 문이 잠겨 있는가 — 조회든 변이든 왕복이 하나라도 도는 중이면 참이다.
   *
   * 표시축(`busy`)과 갈라 두는 이유: 두 축은 묻는 것이 다르다. `busy`(=`mutating`)는 "지금
   *   화면이 무슨 일을 하고 있다고 말해야 하는가"이고, 이쪽은 "지금 쓰기를 시작해도 되는가"다.
   *   조회가 도는 중에 일괄 적용을 누르면 백엔드는 방금 읽고 있던 것과 다른 현황 위에서 쓰기를
   *   시작한다. 그래서 버튼 잠금만 이 축으로 옮긴다.
   * 반대로 상태박스·투명도는 `busy`를 그대로 쓴다: 조회 왕복에 "적용 중"이라 말하면 화면이
   *   거짓을 말하고, 재조회는 사용자가 시킨 일이 아니라 화면이 스스로 하는 일이다.
   * 팝업 진입 버튼은 잠그지 않는다 — 팝업은 열리자마자 자기 조회를 하고 자기 문을 쓴다.
   */
  const locking = door.busy;

  // mount 태그는 useEffect에서 찍는다. 컴포넌트 본문은 render 단계라, 거기서 찍으면 뒤이은
  //   자식 렌더가 실패해도 "mounted"가 남아 진단이 거짓말을 한다. useEffect는 commit 이후에만
  //   돌고, 빈 deps라 재렌더로 중복되지도 않는다.
  useEffect(() => {
    // 백엔드가 살아 있는지, 언어 판정이 무엇으로 이겼는지를 한 번에 확인한다.
    // 실패해도 화면을 죽이지 않는다 — 진단 태그만 남기고 기본 언어(en)로 간다.
    // 이 파일이 `ensureLang`을 부르는 자리는 여기 하나다. 진단 목록(missing)은 첫 호출자만
    //   백엔드로 보내므로, 언어가 이미 확정된 뒤의 마운트에서는 그 목록이 안 나간다 —
    //   그때는 아래에서 직접 로그로 남긴다. 정보를 잃지 않는다.
    ensureLang(PLUGIN_VERSION, FN, missing).then(
      (r) => {
        if (r.code) failTag(`hello-failed code=${r.code}`);
        if (r.cached && missing.length > 0) failTag(`uicheck-missing=${missing.join(",")}`);
        setLangReady(true);
      },
      (err) => {
        failTag(`hello-failed err=${String(err)}`);
        setLangReady(true);
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // QAM이 보일 때만 갱신한다(`useQuickAccessVisible`). 닫혀 있는 패널을 위해 게임마다 슬롯
  // meta와 백업 목록을 읽고 `/proc`을 훑는 조회를 계속 돌릴 이유가 없다.
  useEffect(() => {
    if (visible && !busy) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  /**
   * 일괄 적용 — 토큰 없는 요청은 현재 상태를 분류해 확인 자료와 토큰을 요청한다. 토큰을 실은
   *   요청은 실행을 시도하지만, 상태가 달라졌으면 다시 확인을 요구할 수 있다. 미리보기는 관측
   *   시점의 분류이며 실제 결과와의 동치를 보장하지 않는다.
   *
   * 판정은 백엔드에만 있다. 여기서 적용 대상을 다시 세지 않는다.
   * 확인창을 못 띄우면 그 사실을 말한다. `showModal` 호출 실패는 로컬 실패로 기록한다.
   */
  const runApplyAll = useCallback(
    (profile: Profile, token?: string) => {
      setPreviewing(!token);
      // 새 동작의 시작 — 승계해 온 실패는 여기서 거둔다. 과거군(요약)은 남는다.
      setFailure(null);
      // 팝업 3종과 같은 문을 지난다: busy·세대 가드·재조회·통지가 여기서 온다.
      //   토큰 발급·재확인 신호는 흐름 응답이라 재조회와 통지를 붙이지 않는다. 확정 실행 응답은
      //   성공·실패와 무관하게 다시 읽는다 — 엔진은 쓴 뒤에도 실패할 수 있다.
      // 왕복이 통째로 죽으면 `deadApply`가 실패 봉투로 바꾼다.
      void door.runMutation(
        () => applyAll(profile, token).catch(deadApply),
        "APPLY_FAILED",
        (res) => {
          if (!res.ok && res.code === "CONFIRM_REQUIRED") {
            // 실패가 아니라 흐름 신호다(`codes.FLOW_CODES`) — 오류 문구로 그리지 않는다.
            //    이 시점에 백엔드는 파일을 하나도 건드리지 않았다(문도 재조회를 붙이지 않는다).
            const p = res.params as unknown as ApplyAllConfirmParams;
            try {
              // 다른 확인창과 같은 렌더러를 지난다(`SpecConfirmModal`). 확인 내용은
              //   `confirmSpecs`가, 렌더링과 포커스 처리는 공용 렌더러가 맡는다.
              // 받은 토큰을 그대로 되돌린다. 토큰 값이 달라지면 백엔드가 거부한다.
              showModal(
                <SpecConfirmModal
                  spec={makeApplyAllConfirmSpec(p, () => runApplyAll(profile, p.confirm_token))}
                />,
              );
            } catch (err) {
              failTag(`apply-confirm-modal-failed err=${String(err)}`);
              // 화면이 만든 사유이므로 `kind:"local"`로 기록해 `tCode` 관문을 지나지 않는다.
              //   호출부의 키가 문장을 정하고 `"MODAL"`은 진단 꼬리표로만 남는다.
              //   `APPLY_CONFIRM_MODAL_FAILED`에는 `{code}` 자리가 없어 꼬리표가 화면에 나오지 않는다.
              setFailure({ kind: "local", key: "APPLY_CONFIRM_MODAL_FAILED", reason: "MODAL", at: Date.now() });
            }
            return;
          }
          if (res.ok) {
            // 결과의 정본은 이 상태다. 토스트는 QAM이 닫혀 있어도 도달하는 부가 채널일
            //   뿐이라, 토스트가 실패해도 아래 요약 줄은 이미 붙잡혀 있다.
            keepSummary(buildSummary(profile, res.data.results, res.data.counts));
            setFailure(null);
            return;
          }
          // 봉투가 `ok:false`라고 해서 일괄 적용이 시작도 못 한 것은 아니다: 엔진이 설정
          //   파일을 다 바꾼 뒤 `save_registry`가 실패하면 백엔드는 `Refused(code=UNEXPECTED)`를
          //   낸다. 그때 일부는 이미 바뀐 상태이므로, 화면은 무슨 일이 있었는지와 왜 멈췄는지를
          //   함께 말한다.
          keepSummary(stoppedSummary(profile, res.code));
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [door.runMutation, setFailure],
  );

  /**
   * 팝업 하나를 연다.
   *
   * 엘리먼트를 함수로 받는다: 여기서 미리 만들면 `showModal`이 없는 상황에서도 팝업이 한 번
   *   그려진다. 열지 못할 화면을 먼저 그릴 이유가 없다.
   * 실패는 대상 이름을 포함해 말한다 — "화면을 못 띄웠다"만으로는 어느 화면인지 알 수 없다.
   *   사유를 지은 것은 화면이므로 `kind:"local"`이고, 그래서 `failKey`가 그대로 문장이 된다.
   */
  const openPopup = useCallback(
    (make: () => ReactElement, failKey: StringKey) => {
      try {
        showModal(make());
      } catch (err) {
        failTag(`popup-modal-failed key=${failKey} err=${String(err)}`);
        setFailure({ kind: "local", key: failKey, reason: "MODAL", at: Date.now() });
      }
    },
    [setFailure],
  );

  // 언어가 확정되기 전에는 번역이 필요한 안내 문구를 그리지 않는다. self-check 실패 안내도
  //   언어 확정 뒤에 그린다. 컴포넌트 누락 상태의 대기 화면은 검사 대상 컴포넌트를 쓰지 않는다.
  //   플러그인 이름은 고유명사라 번역하지 않는다.
  if (!langReady) return missing.length > 0 ? <div /> : <PanelSection title="eGPU Game Config Swap" />;

  //   실패 안내를 검사 대상 컴포넌트로 그리지 않는다. PanelSection이 undefined인 상황을
  //     알리려고 PanelSection을 쓰면 그 안내마저 깨진다. 순수 div로 그린다.
  //   문구는 `t()`를 거친다. 설계가 인정한 하드코딩 예외는 ErrorBoundary 하나뿐이고,
  //     `t()`는 우리 번들 안이라 @decky/ui가 없어도 동작한다.
  if (missing.length > 0) {
    return (
      <div style={{ padding: "8px", fontSize: "13px" }}>
        {t("UI_CHECK_FAILED", { missing: missing.join(", ") })}
      </div>
    );
  }

  const counts = overview?.counts;

  /**
   * 프로필이 아직 하나도 없는 상태 — 등록은 있는데 두 프로필 중 어느 것도 저장된 게임이 없다.
   *
   * 소비자는 둘이다: 설명 줄과 아래 실행 중 고지의 문구 갈래. 새 조건을 세우지 않고 이 식을
   *   그대로 쓴다 — 두 일괄 버튼의 `ready`가 각각 `dock_ready`·`internal_ready`이므로 이 식이
   *   참인 것과 두 버튼이 다 `(0개)`인 것은 같은 사실이다. 조건을 따로 적으면 같은 사실을 두
   *   곳에서 판정하게 되고, 언젠가 한쪽만 움직인다.
   */
  const noProfilesYet =
    !!counts && counts.total > 0 && counts.dock_ready + counts.internal_ready === 0;

  /**
   * 실행 중 게임 고지의 문구 갈래.
   *
   * 프로필 유무와 무관하게 한 문구를 쓰면 등록 직후(프로필 0)에도 "— 나머지는 적용됩니다"라고
   *   말하게 된다. 그때 두 일괄 버튼은 `(0개)`로 비활성이라 적용될 「나머지」가 없다 — 온보딩
   *   직후가 정확히 이 상태다.
   * 줄 자체를 감추지는 않는다: "프로필 0 + 게임 실행 중"은 저장 안내가 유도하는 정상 흐름이고,
   *   그때도 상태박스는 서야 한다. 거짓인 절반만 덜어낸다.
   */
  const runningNoteKey = noProfilesYet ? "BULK_RUNNING_NOTE_NO_TARGET" : "BULK_RUNNING_NOTE";

  // `running`은 이 한 줄에서만 읽는다 — 문을 하나로 모아 두면 활성 조건으로 새어 들어갈
  //   자리가 없다. 식별자 이름만 검사하면 값을 오염시켜 우회할 수 있어, 검사는 "running은
  //   표시 전용 표시가 붙은 줄에서만"을 본다(`build.sh`).
  //   문구 갈래는 위에서 이미 정해져 있다 — 그 판정에 `running`이 들어가지 않는다.
  // e1-display-only
  const runningNote = counts?.running ? t(runningNoteKey, { n: counts.running }) : null;

  /** 카운트 줄. 조회 전에는 빈 자리다 — 모르는 것을 0으로 말하지 않는다. */
  const countText = !counts
    ? ""
    : counts.total === 0
      ? t("NO_GAMES")
      : t("COUNT_SUMMARY", {
          dock: t("PROFILE_DOCK"),
          dock_ready: counts.dock_ready,
          total: counts.total,
          internal: t("PROFILE_INTERNAL"),
          internal_ready: counts.internal_ready,
        });

  /**
   * 상태박스 — 위=지금 / 아래=직전 결과로 나뉜 한 개의 박스.
   * 두 군 모두 비면 박스 자체를 그리지 않는다.
   */
  function renderStatusBox(): ReactNode {
    const now: ReactNode[] = [];
    // ⓪ 아직 아무것도 모른다. 실패가 있으면 그쪽이 더 정확한 말을 하므로 이 줄은 물러난다.
    if (!overview && !failure) {
      now.push(<div key="loading" style={{ color: MUTED_COLOR }}>{t("LOADING")}</div>);
    }
    // ① 진행 중 — 토큰 없는 요청은 확인 자료 요청, 토큰 있는 요청은 실행 시도다. 실제 결과는 응답이 정한다.
    if (busy) {
      now.push(
        <div key="busy" style={{ color: MUTED_COLOR }}>
          {previewing ? t("APPLY_PREVIEWING") : t("APPLYING")}
        </div>,
      );
    }
    // ② 실행 중 게임 고지 — 표시 전용이다. 활성 조건이 아니다.
    if (runningNote) {
      now.push(<div key="running" style={{ color: MUTED_COLOR }}>{runningNote}</div>);
    }
    // ③ 실패 — 사유와 받은 시각을 함께. 사유가 지나는 문은 출처가 정한다(`Failure`):
    //   백엔드 코드는 `tCode` 단일 관문으로, 화면이 지어낸 사유는 그 관문을 지나지 않고
    //   호출부가 준 키가 곧 문장이 된다(`{code}`가 있는 키면 꼬리표가 그 자리에 실린다).
    //   TS 필드는 `reason`인데 치환자는 `{code}`다 — 치환자 이름은 i18n 문자열 쪽 계약이라
    //     (10개 문구가 그 이름을 쓴다) 같이 고치는 것이 아니다.
    if (failure) {
      now.push(
        <div key="failure" style={{ color: WARN_COLOR }}>
          {failure.kind === "code"
            ? tCode(failure.code, failure.key)
            : t(failure.key, { code: failure.reason })}
          <span>{" · "}{stampOf(failure.at)}</span>
        </div>,
      );
    }
    // ④ 시작 안내 슬롯은 없다 — 그 안내가 하던 일을 설명 줄이 겸하므로, 같은 사실을 두
    //   자리에서 말하지 않는다.
    //   미렌더 조건에 프로필 수는 들어가지 않는다. ② `runningNote`는 `counts.running`만 보고,
    //   과거군도 마찬가지다. "프로필 0 + 게임 실행 중"은 저장 안내가 유도하는 정상 흐름이라
    //   그때 상태박스는 선다.

    const past: ReactNode[] = [];
    if (summary) {
      // ⑤ 결과 제목 — 아이콘이 성패를 먼저 말하고, 시각이 "언제 것인지"를 말한다.
      past.push(
        <div key="result" style={{ ...RESULT_BLOCK_STYLE, color: MUTED_COLOR }}>
          <div style={RESULT_HEAD_STYLE}>
            {/* `fontSize:"16px"`는 "성패 아이콘 16px 고정"의 이행이다. 아이콘은 1em이라
                주변 글자 크기를 따라가는데, 카드가 12px이라 그대로 두면 12px로 줄어든다 —
                크기를 못 박은 조문이 상속에 조용히 먹히던 자리다. */}
            <span
              style={{
                display: "inline-flex",
                fontSize: "16px",
                color: summary.problems ? WARN_COLOR : MUTED_COLOR,
              }}
            >
              {summary.problems ? <IconWarn /> : <IconCheck />}
            </span>
            <span style={STAMP_STYLE}>{stampOf(summary.at)}</span>
          </div>
          <div style={HEADLINE_STYLE}>{summary.headline}</div>
        </div>,
      );
      // ⑥ 사유 — 이름과 조치가 여기 있다. 색은 주황 하나뿐이다.
      if (summary.hints.length > 0) {
        past.push(
          <div key="why" style={{ color: WARN_COLOR }}>{summary.hints.join(" · ")}</div>,
        );
      }
    }

    if (now.length === 0 && past.length === 0) return null;
    return (
      <PanelSectionRow>
        <div style={STATUS_STACK_STYLE}>
          {now.length > 0 ? <div style={STATUS_CARD_STYLE}>{now}</div> : null}
          {past.length > 0 ? (
            /* busy 동안 과거군 카드 전체가 흐려진다 — "지금 것이 아니다"를 숨기지 않고
               말하는 방법이다. 투명도는 줄이 아니라 카드 단위로 건다. */
            <div style={{ ...STATUS_CARD_STYLE, opacity: busy ? 0.4 : 1 }}>{past}</div>
          ) : null}
        </div>
      </PanelSectionRow>
    );
  }

  return (
    <>
      {/*
        제목을 두지 않는다 — QAM 헤더의 `titleView`가 이미 플러그인 이름을 말한다.
      */}
      <PanelSection>
        {/*
          데이터 자격 조건은 그 프로필을 실제로 가진 게임 수가 1 이상인 것이다. 실행 중인 게임
            수는 이 조건에 들어가지 않는다. 별도로 조회·변이 왕복 중에는 버튼을 잠근다.

          `ready`는 counts가 없으면 `undefined`를 그대로 넘긴다. 호출부에서 0으로 접으면 현황을
            모르는 동안 라벨만 `(0개)`를 그리게 된다. 괄호 유무와 비활성 판정은 버튼이 맡는다.
        */}
        {(["dock", "internal"] as const).map((profile) => (
          <BulkApplyButton
            key={profile}
            profile={profile}
            ready={counts ? (profile === "dock" ? counts.dock_ready : counts.internal_ready) : undefined}
            hint={bulkHint(counts)}
            /* 잠금은 조회까지 포함한 문으로 판단한다(위 `locking` 주석). */
            busy={locking}
            onApply={runApplyAll}
          />
        ))}

        {/* 설명 영역 — 어느 상태에서든 한 줄만 그린다. 위에서부터 먼저 참인 행 하나:
              1행 `!counts`(로딩 · 조회 실패 · 실패 승계 재개방) → 줄 자체가 없다(모르는
                   상태에서 단언하지 않는다. 조회 실패는 `overview`를 만들지 않는다)
              2행 등록 0 → 없다(그 상태의 안내는 카운트 줄 `NO_GAMES`가 전담 — 손가락 하나)
              3행 프로필 0 → `QAM_ABOUT_GUIDE`   4행 그 외 → `QAM_ABOUT`
            자리(placeholder)를 잡지 않는다: 1·2행에서는 영구히 없는 줄이라 빈 칸이 상주하면
              "말할 게 없으면 그리지 않는다"와 어긋난다.
            키를 변수로 넘기지 않는다 — 리터럴 두 갈래로 쓴다. 변수 경유로 쓰면 사람이 grep으로
              그 키의 사용처를 못 찾아, 살아 있는 키를 죽은 키로 오인한다. */}
        {!counts || counts.total === 0 ? null : (
          <PanelSectionRow>
            <div style={HINT_STYLE}>
              {noProfilesYet ? t("QAM_ABOUT_GUIDE") : t("QAM_ABOUT")}
            </div>
          </PanelSectionRow>
        )}

        {renderStatusBox()}

        {/* 카운트 줄은 조회 전에도 자리를 지킨다 — 값이 도착할 때 화면이 튀지 않는다. */}
        <PanelSectionRow>
          <div style={{ ...HINT_STYLE, minHeight: "16px" }}>{countText}</div>
        </PanelSectionRow>

        <EntryButton
          icon={<IconSearch />}
          label={t("OPEN_DISCOVER")}
          desc={t("OPEN_DISCOVER_DESC")}
          onOpen={() => openPopup(
            () => <DiscoverPopup onMutate={refresh} />,
            "POPUP_DISCOVER_MODAL_FAILED",
          )}
        />
        <EntryButton
          icon={<IconList />}
          label={t("OPEN_GAMES")}
          desc={t("OPEN_GAMES_DESC")}
          onOpen={() => openPopup(
            () => <GamesPopup onMutate={refresh} />,
            "POPUP_GAMES_MODAL_FAILED",
          )}
        />
        <EntryButton
          icon={<IconGear />}
          label={t("OPEN_SETTINGS")}
          desc={t("OPEN_SETTINGS_DESC")}
          onOpen={() => openPopup(
            () => <SettingsPopup onMutate={refresh} />,
            "POPUP_SETTINGS_MODAL_FAILED",
          )}
        />
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // 진입점은 QAM 하나다. 그 하나를 경계로 감싼다: 감싸지 않으면 렌더 실패가 트리를 통째로
  //   무너뜨리고, Game Mode에서 아무 단서도 안 남는다.
  //   팝업 3종은 각자 자기 `DialogBody` 안쪽에 경계를 세운다.
  return {
    name: "eGPU Game Config Swap",
    // titleClass()는 staticClasses가 없어도 TypeError를 내지 않는다(deckyui.ts).
    // 플러그인 이름은 고유명사라 번역하지 않는다.
    titleView: <div className={titleClass()}>eGPU Game Config Swap</div>,
    content: (
      <ErrorBoundary where="qam">
        <Content />
      </ErrorBoundary>
    ),
    icon: (
      <svg width="1em" height="1em" viewBox="0 0 16 16" fill="currentColor">
        <path d="M2 3h12v8H9v2h2v1H5v-1h2v-2H2V3zm1 1v6h10V4H3z" />
      </svg>
    ),
    // `onDismount`를 두지 않는다. `statusListeners` 등록은 `Content`의 effect cleanup이 해제한다.
  };
});
