import { definePlugin, toaster, useQuickAccessVisible } from "@decky/api";
import { useCallback, useEffect, useState, type ReactElement, type ReactNode } from "react";
import {
  applyAll,
  getOverview,
  type ApplyAllConfirmParams,
  type ApplyRow,
  type Outcome,
  type Overview,
  type OverviewCounts,
  type Profile,
} from "./rpc";
import { ensureLang, setProfileNames, t, tCode, type StringKey } from "./i18n";
import { PLUGIN_VERSION } from "./version";
import { BulkApplyButton } from "./BulkApplyButton";
import { ErrorBoundary } from "./ui/ErrorBoundary";
import { GamesPopup } from "./GamesPopup";
import { DiscoverPopup } from "./DiscoverPopup";
import { SettingsPopup } from "./SettingsPopup";
import { IconCheck, IconGear, IconList, IconSearch, IconWarn } from "./icons";
import {
  ButtonItem,
  ConfirmModal,
  PanelSection,
  PanelSectionRow,
  showModal,
  titleClass,
  uicheckMissing,
} from "./deckyui";

// ── 진단 태그 ────────────────────────────────────────────────────────────────
// cef_log.txt는 여러 달치 append-only라, 태그에 이번 프론트 로드를 가리키는 nonce(fn)가
// 없으면 과거 부팅의 태그와 구분할 수 없다(설계 E6). 세 태그 전부에 fn을 붙인다.
// 이 문자열들은 **의도적으로 번역하지 않는다** — 번역되면 진단 grep이 언어에 따라 깨진다.

const FN = Math.random().toString(36).slice(2, 6);

// ★ [실측 2026-08-05] Steam CEF에서 **`console.error`만 `cef_log.txt`에 실린다.**
//   `log`/`warn`/`info`는 한 건도 안 남는다(프로브로 확인: error 1건 / 나머지 0건).
//   그래서 진단을 두 갈래로 나눈다 —
//     · 정상 신호는 `ui_hello`로 **백엔드 로그 한 곳에** 모은다. 거기엔 session·fn이 이미 있고,
//       플러그인별로 파일이 갈려 있어 부팅 세션을 구분할 필요조차 없다.
//     · **백엔드에 닿지 못한 경우에만** console.error로 남긴다. 그건 실제로 오류이므로
//       error 레벨이 의미상으로도 맞고, 그 상황에서 남길 곳이 cef_log뿐이다.
function failTag(msg: string): void {
  console.error(`[gfxprofile] ${msg} fn=${FN}`);
}

const PROFILE_KEY: Record<Profile, StringKey> = {
  dock: "PROFILE_DOCK",
  internal: "PROFILE_INTERNAL",
};

/**
 * 일괄 적용 결과를 **화면 최대 3줄**로 줄인다.
 *
 * ★ 왜 목록이 아니라 요약인가(2026-08-06 사용자 결정):
 *   *"간편하자고 만든 앱의 모달에 뜬 로그를 일일이 보고 있을 이유가 없다."*
 *   등록 게임이 200개까지 갈 수 있으므로 전량 나열은 성립하지도 않는다(설계 §0-A).
 *   **화면 = 지금 뭘 해야 하는지 / 로그 = 나중에 뭐가 있었는지**로 나눈다 —
 *   상세는 백엔드 로그의 `problems=`가 보관한다(main.py).
 *
 * ★ 왜 `outcome`이 아니라 `code`로 가르는가(외부 반증 채택):
 *   `refused` 하나에 **11종 코드**가 뭉개져 있다. 조치가 균일한 것은 `GAME_RUNNING` 하나뿐이고,
 *   나머지(프로필 없음·손상·백업 실패·경로 이상 …)는 게임마다 조치가 다르다.
 *   전부에 "종료 후 재시도"라고 말하면 **틀린 처방**이 된다 — 정보 없음보다 오정보가 나쁘다.
 */
const CAP_NAMES = 3;

/** 이름 나열 한 줄 — 넘치면 `NAMES_AND_MORE`로 접는다. 두 사유 줄이 **같은 규칙**을 쓴다. */
function namesOf(rows: ApplyRow[]): string {
  const shown = rows.slice(0, CAP_NAMES).map((r) => r.name).join(", ");
  const more = rows.length - CAP_NAMES;
  return more > 0 ? t("NAMES_AND_MORE", { names: shown, n: more }) : shown;
}

/**
 * 직전 일괄 적용의 결과(§3-B 과거군). **수신 시각까지 여기 담는다** — 봉투에는 시각이 없고,
 * 화면이 결과를 받은 순간이 곧 "언제 있었던 일인가"의 정본이다(D02·M9. 봉투 확장 0).
 */
interface ApplySummary {
  headline: string;
  hints: string[];
  /** 문제 행이 하나라도 있었는가 — 제목 아이콘을 가른다(D05: 체크 / 주황 경고). */
  problems: boolean;
  /** 체크인이 일어난 게임 수(§5-E ⑦). 0이면 그 줄을 그리지 않는다. */
  checkin: number;
  at: number;
}

function buildSummary(
  profile: Profile,
  rows: ApplyRow[],
  counts: Partial<Record<Outcome, number>>,
  checkin: number,
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
  // ★ F16-ⓑ: **이름을 말한다.** "실행 중인 게임 3개"로는 어느 게임을 끄면 되는지 알 수 없어
  //   사용자가 할 수 있는 일이 없다. 이름은 결과 행에 이미 실려 있다(봉투 확장 0).
  if (running.length > 0) hints.push(t("APPLY_PROBLEM_REFUSED", { names: namesOf(running) }));

  // ★ P5: 사유를 **화면에** 낸다. 전까지는 *"사유는 로그를 확인하십시오"*였는데,
  //   Game Mode에는 터미널이 없어 사용자가 로그를 볼 방법이 사실상 없었다.
  //   `row.code`는 엔진이 이미 병기해 프론트까지 와 있다(v2가 M1에서 갈라 둔 지점) —
  //   엔진을 손대지 않고 코드→문장 사전만으로 채울 수 있다.
  // ★ 코드**별로 묶는다**. 뭉쳐서 한 사유만 말하면 나머지 게임에는 **틀린 처방**이 된다
  //   (`refused` 하나에 11종 코드가 들어 있다 — 위 주석 참조). 정보 없음보다 오정보가 나쁘다.
  //   묶음 수를 자르지 않는 이유: 자르면 그 게임은 화면에서 **통째로 사라진다.**
  //   묶음 수는 「서로 다른 실패 코드 수」라 실사용에서 1~2개이고, 각 묶음은 이미 이름을
  //   CAP_NAMES로 자른다 — 별도 넘침 처리를 만드는 대신 넘칠 구조를 안 만든다.
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
    checkin,
    at: Date.now(),
  };
}

/**
 * 일괄 적용 확인창 (F8) — **오발동을 막는 마찰**이다. 명세 정본 = 설계 §3-E.
 *
 * ★★ 이 모달은 설계 정본 §9-E 모달 정당성 기준(파괴적 **그리고** 저빈도)의 **예외**다.
 *   일괄 적용은 주 동작이고 매 부팅 누르는 고빈도 버튼이며 파괴적이지도 않다(백업이 선행되는
 *   정상 쓰기). 그럼에도 붙이는 근거는 **최신 사용자 결정(2026-08-09 — 오발동 방지 명시 요청)**이
 *   기준에 우선한다는 것이다. 전례가 실재한다: P2 실기에서 결과 목록을 드래그하다
 *   **의도하지 않은 일괄 적용이 실행됐다.**
 *
 * ★★ 본문의 `{total}`은 **미리보기 봉투가 준 값**이다(§3-E · Codex D-06) — 토큰을 발급한
 *   그 시점의 등록 수 스냅샷이다. `get_overview`의 total을 쓰면 *"토큰이 지문 낸 대상"*과
 *   화면 숫자가 어긋난다(다른 시점의 조회). 버킷 5개의 합 = 이 값이 계약이다.
 * ★ 숫자는 **전부 백엔드가 센 값**이고 화면은 「예상」이라고 말한다 — 실행 결과의 정본은
 *   적용 후 요약과 백엔드 로그다. 0인 버킷 줄은 그리지 않는다(`counts.incomplete`의 기존 규칙).
 * ★ `bDestructiveWarning`은 **붙이지 않는다**(세션 잠정 확정) — 일괄 적용은 파괴가 아니라
 *   주 동작이고, 붙이면 "저장 덮어쓰기·삭제 급"과 시각 언어가 뭉개진다. C 묶음 재검토 등재분.
 * ★ **OK는 항상 활성**이다. `running_refused`는 고지 줄에만 쓰이고 활성 조건에 절대 들어가지
 *   않는다 — 조건이 되는 순간 E1(실행 중 게임이 일괄 적용을 막지 않는다)이 모달 층에서 뒤집힌다.
 * ★ 무정보 상시 줄은 §3-E D04로 **삭제**됐다 — 「예상:」 접두가 이미 같은 말을 한다.
 *   (그 문구 키 `APPLY_ALL_CONFIRM_NOTE`도 P15에서 번역표에서 제거됐다.)
 */
function ApplyAllConfirm({
  params,
  onConfirm,
  closeModal,
}: {
  params: ApplyAllConfirmParams;
  onConfirm: () => void;
  /** `showModal`이 최상위 엘리먼트에 주입한다. 우리가 감싼 컴포넌트가 받으므로 그대로 넘긴다. */
  closeModal?: () => void;
}) {
  const profileName = t(PROFILE_KEY[params.profile]);
  // 0인 버킷은 줄에서 뺀다 — 없는 것을 0으로 나열하면 정작 중요한 숫자가 묻힌다.
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
  return (
    <ConfirmModal
      strTitle={t("APPLY_ALL_CONFIRM_TITLE", { profile: profileName })}
      strDescription={
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <div>{t("APPLY_ALL_CONFIRM_BODY", { total: params.total, profile: profileName })}</div>
          {parts.length > 0 ? <div>{t("APPLY_ALL_CONFIRM_EXPECT", { list: parts.join(" · ") })}</div> : null}
        </div>
      }
      strOKButtonText={t("APPLY_ALL_CONFIRM_OK")}
      strCancelButtonText={t("CANCEL")}
      closeModal={closeModal}
      onOK={onConfirm}
    />
  );
}

/** 화면이 실패를 **받은 시각까지** 들고 있는다 — 언제 있었던 일인지가 사유만큼 중요하다. */
interface Failure {
  key: StringKey;
  code: string;
  at: number;
}

// ★ 마지막 일괄 적용 요약은 **컴포넌트 밖**에 둔다.
//   QAM을 닫으면 패널이 언마운트되므로(실측: 다시 열면 요약 줄이 사라졌다) 상태에만 두면
//   "무슨 일이 있었는지"가 창을 닫는 순간 없어진다. 결과는 화면 수명보다 오래 남아야 한다.
let lastSummary: ApplySummary | null = null;

// ★★ 실패도 **같은 수명**이다(F20 — §3-B 수명 규칙). 예전에는 성공만 모듈 변수로 살아남고
//   실패는 QAM을 닫는 순간 사라졌다 — *"뭔가 안 됐다"*는 사실이 성공보다 짧게 사는 비대칭이다.
//   소거 시점은 **다음 동작 시작**(새 일괄 적용 / 새 로드 성공)뿐이다.
let lastFailure: Failure | null = null;

const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;

const MUTED_COLOR = "#9aa0a6";
/** 주의색은 **주황 하나**다 — 빨강은 쓰지 않는다(A8). */
const WARN_COLOR = "#ffb454";

/** 상태박스(§3-B) — 시각 박스는 **한 개**이고, 내용이 0줄이면 아예 그리지 않는다. */
const BOX_STYLE = {
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "4px",
  padding: "8px 10px",
  fontSize: "12px",
  display: "flex",
  flexDirection: "column",
} as const;

const GROUP_STYLE = { display: "flex", flexDirection: "column", gap: "6px" } as const;

/** 결과 제목 줄 — 아이콘과 글이 같은 줄에 선다. */
const RESULT_ROW_STYLE = { display: "flex", alignItems: "center", gap: "6px" } as const;

/**
 * 결과·실패를 **받은 시각**. 당일이면 `14:32`, 다른 날이면 `08-10 14:32`(D02·M9).
 *
 * ★ 번역하지 않는다: 숫자와 구분 기호뿐이라 언어에 따라 달라질 글자가 없다.
 *   (달라져야 하는 것은 12/24시간 표기인데, Steam 설정을 프론트가 읽을 방법이 없다 —
 *    지어내는 대신 24시간 고정으로 **한 가지 뜻만** 갖게 한다.)
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
 * 일괄 버튼 아래 **사유 한 줄**(§3-A ⓑ · M1). `ButtonItem`의 `description` 슬롯으로 그린다.
 *
 * ★★ 이 식에는 **`running`이 들어가지 않는다.** 파생 재료는 `total`·`ready`뿐이다 —
 *   실행 중인 게임은 일괄 적용을 막지 않으므로(E1) *"왜 못 누르는가"*의 사유가 될 수 없고,
 *   여기서 한 번 running을 읽으면 그 값이 활성 조건으로 새어 들어갈 길이 생긴다.
 * ★ `counts`가 아직 없으면 **아무 말도 하지 않는다**(D01) — 등록 수를 모르는 동안
 *   "등록된 게임이 없습니다"라고 말하면 화면이 거짓을 말한다.
 */
function bulkHint(counts: OverviewCounts | undefined, profile: Profile): string | undefined {
  if (!counts) return undefined;
  if (counts.total === 0) return t("NO_GAMES");
  const ready = profile === "dock" ? counts.dock_ready : counts.internal_ready;
  return ready === 0 ? t("BULK_NO_PROFILES") : undefined;
}

/**
 * QAM의 팝업 진입 버튼 하나(§3-A 6~8) — 아이콘 + 라벨 + 설명 한 줄.
 *
 * ★ 설명(`description`)은 *"거기서 무엇을 하는가"*를 말한다(M10): 진입 안내를 상단 설명 영역에
 *   몰아 넣으면 그 문단이 매번 읽히는 소음이 되고, 정작 버튼 옆은 비어 있다.
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
      <ButtonItem layout="below" icon={icon} description={desc} onClick={onOpen}>
        {label}
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
  // 초기값을 모듈 변수에서 받으므로 QAM을 닫았다 열어도 남아 있다(요약·실패 모두 — F20).
  const [failure, setFailureState] = useState(lastFailure);
  const [busy, setBusy] = useState(false);
  /** busy 중 **무엇을 하는 중인가**(§3-B ①): 무토큰 1차 = 확인 중 / 토큰 재호출 = 적용 중. */
  const [previewing, setPreviewing] = useState(false);
  const [summary, setSummary] = useState(lastSummary);

  /** 실패는 **모듈 변수와 상태를 함께** 움직인다 — 두 곳에 각자 쓰면 언젠가 갈린다. */
  const setFailure = useCallback((next: Failure | null) => {
    lastFailure = next;
    setFailureState(next);
  }, []);

  /**
   * 현황 재조회 — **멱등이다.** 몇 번을 불러도 같은 봉투를 다시 읽어 덮어쓸 뿐이고,
   * 세거나 쌓는 것이 없다.
   *
   * ★★ 그래야 하는 이유(P15-B 인계 ①): 팝업의 `onMutate`는 **거부·실패에도 발화한다**
   *   (엔진은 쓴 뒤에 거부할 수 있으므로 "실패했으니 안 읽는다"가 틀린 규칙이다).
   *   즉 이 핸들러는 한 동작에 여러 번 올 수 있고, 그때마다 다른 일을 하면 화면이 흔들린다.
   */
  const refresh = useCallback(() => {
    getOverview().then(
      (res) => {
        if (res.ok) {
          // 표시명(F11 ①)을 먼저 반영한다 — 라벨이 그려지기 전이어야 이름이 안 깜빡인다.
          setProfileNames(res.data.profile_names);
          setOverview(res.data);
          // 새 로드 성공 = 다음 동작의 시작이다 — 승계해 온 실패를 여기서 거둔다(§3-B 수명).
          setFailure(null);
        } else {
          setFailure({ key: "LOAD_FAILED", code: res.code, at: Date.now() });
        }
      },
      (err) => {
        // 백엔드에 닿지 못한 경우다 — 남길 곳이 cef_log뿐이라 여기만 console.error다.
        failTag(`overview-failed err=${String(err)}`);
        setFailure({ key: "LOAD_FAILED", code: "UNEXPECTED", at: Date.now() });
      },
    );
  }, [setFailure]);

  // ★ mount 태그는 **useEffect에서** 찍는다. 컴포넌트 본문은 render 단계라, 거기서 찍으면
  //   뒤이은 자식 렌더가 실패해도 "mounted"가 남아 진단이 거짓말을 한다. useEffect는
  //   commit 이후에만 돌고, 빈 deps라 재렌더로 중복되지도 않는다.
  useEffect(() => {
    // 백엔드가 살아 있는지, 언어 판정이 무엇으로 이겼는지를 한 번에 확인한다.
    // 실패해도 화면을 죽이지 않는다 — 진단 태그만 남기고 기본 언어(en)로 간다.
    // ★ QA R2 지적 ⑭: 예전엔 패널이 `uiHello`를 직접 불러, 라우트의 ensureLang과 합쳐
    //   한 세션에 ui_hello가 **3번** 나갔다(fn=hobb/route/hobb). 경로를 하나로 합친다.
    //   ⚠️ 진단 목록(missing)은 **첫 호출자만** 보내므로, 라우트가 먼저 떠서 생략됐다면
    //     여기서 직접 로그로 남긴다 — 정보를 잃지 않는다.
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

  // QAM이 보일 때만 갱신한다(`useQuickAccessVisible`). 닫혀 있는 패널을 위해
  // 9게임 sha1과 running 조회를 계속 돌릴 이유가 없다.
  useEffect(() => {
    if (visible && !busy) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  /**
   * 일괄 적용 — **1차 호출은 미리보기, 2차 호출이 실행**이다(F8).
   *
   * ★ 판정은 백엔드에만 있다. 여기서 "무엇이 적용될까"를 다시 세지 않는다 — 프론트가 세면
   *   두 곳에서 세는 것이고 언젠가 어긋난다(`counts`와 같은 규칙).
   * ★★ 확인창을 **못 띄우면 그 사실을 말한다**(2026-08-07 QA 반려 ②). `showModal`은 런타임에
   *   얻어지는 값이라 `undefined`일 수 있고, 그러면 `TypeError`가 `.then` 콜백 안에서 나
   *   **아무 흔적 없이 버튼이 죽는다.** 안전(=토큰이 없어 실행되지 않음)과 진단 가능성은
   *   다른 요건이다.
   */
  const runApplyAll = useCallback(
    (profile: Profile, token?: string) => {
      setBusy(true);
      setPreviewing(!token);
      // 새 동작의 시작 — 승계해 온 실패는 여기서 거둔다(§3-B 수명). 과거군(요약)은 남는다.
      setFailure(null);
      applyAll(profile, token)
        .then(
          (res) => {
            if (!res.ok && res.code === "CONFIRM_REQUIRED") {
              // ⚠️ 실패가 아니라 **흐름 신호**다(FLOW_CODES) — 오류 문구로 그리지 않는다.
              //    이 시점에 백엔드는 파일을 1바이트도 쓰지 않았다.
              const p = res.params as unknown as ApplyAllConfirmParams;
              try {
                showModal(
                  <ApplyAllConfirm
                    params={p}
                    // 받은 토큰을 **그대로** 되돌린다. 지어낼 수 없고, 고쳐 봐야 거부된다.
                    onConfirm={() => runApplyAll(profile, p.confirm_token)}
                  />,
                );
              } catch (err) {
                failTag(`apply-confirm-modal-failed err=${String(err)}`);
                // ⚠️ code에 `"UNEXPECTED"`를 넣으면 안 된다 — `tCode`는 **i18n에 등재된 코드면
                //   그 문구를 이긴다**(단일 관문의 정의). 그러면 "예기치 못한 오류"가 떠서
                //   *확인창이 안 떴다*는 진짜 사유가 사라진다. 등재되지 않은 코드를 줘야
                //   fallback(=아래 키)이 화면에 나온다.
                setFailure({ key: "APPLY_CONFIRM_MODAL_FAILED", code: "MODAL", at: Date.now() });
              }
              return;
            }
            if (res.ok) {
              // ★ 결과의 **정본은 이 상태**다. 모달은 없앴고(2026-08-06 사용자 결정),
              //   토스트는 QAM이 닫혀 있어도 도달하는 부가 채널일 뿐이다 —
              //   토스트가 실패해도 아래 요약 줄은 이미 붙잡혀 있다.
              lastSummary = buildSummary(
                profile,
                res.data.results,
                res.data.counts,
                res.data.checkin.length,
              );
              setSummary(lastSummary);
              setFailure(null);

              try {
                toaster.toast({ title: lastSummary.headline, body: lastSummary.hints.join(" · ") });
              } catch (err) {
                failTag(`toast-failed err=${String(err)}`);
              }
              refresh();
            } else {
              // ⚠️ 게임별 실패는 여기 오지 않는다. 봉투가 ok:false인 것은
              //    일괄 적용 자체가 시작도 못 한 경우뿐이다.
              setFailure({ key: "APPLY_FAILED", code: res.code, at: Date.now() });
            }
          },
          (err) => {
            failTag(`apply-all-failed err=${String(err)}`);
            setFailure({ key: "APPLY_FAILED", code: "UNEXPECTED", at: Date.now() });
          },
        )
        .finally(() => setBusy(false));
    },
    [refresh, setFailure],
  );

  /**
   * 팝업 하나를 연다(§3-A 6~8 · §4-A).
   *
   * ★ 엘리먼트를 **함수로 받는다**: 여기서 미리 만들면 `showModal`이 없는 상황에서도 팝업이
   *   한 번 그려진다. 열지 못할 화면을 먼저 그릴 이유가 없다.
   * ★ 실패는 **대상 이름을 포함해** 말한다(F21) — "화면을 못 띄웠다"만으로는 어느 화면인지
   *   알 수 없다. `code`에 등재되지 않은 값을 주어 `tCode`가 그 키로 떨어지게 한다(위 참조).
   */
  const openPopup = useCallback(
    (make: () => ReactElement, failKey: StringKey) => {
      try {
        showModal(make());
      } catch (err) {
        failTag(`popup-modal-failed key=${failKey} err=${String(err)}`);
        setFailure({ key: failKey, code: "MODAL", at: Date.now() });
      }
    },
    [setFailure],
  );

  // ★ 실패 안내를 **검사 대상 컴포넌트로 그리지 않는다.**
  //   PanelSection이 undefined인 상황을 알리려고 PanelSection을 쓰면 그 안내마저 깨진다.
  //   안전장치는 자기가 감시하는 실패에 걸려선 안 된다.
  // ★ 언어가 확정되기 전에는 **어떤 사용자 문구도 그리지 않는다. self-check 실패 안내도 예외가 아니다.**
  //   (2026-08-05 QA R5 재인증: `t()`로 옮기는 것만으로는 절반만 고친 것이었다 —
  //    한국어 사용자에게 언어 판정 전 영어가 먼저 뜨는 경로가 그대로 남아 있었다.)
  //   ⚠️ 이 대기 화면조차 **검사 대상 컴포넌트를 쓰면 안 된다** — `PanelSection`이 없어서 안내하려는
  //     상황에서 `PanelSection`으로 대기 화면을 그리면 그 대기 화면이 먼저 깨진다.
  //   i18n-exempt: 플러그인 이름은 고유명사라 번역하지 않는다(가시 문자열이 아니라 식별자다).
  if (!langReady) return missing.length > 0 ? <div /> : <PanelSection title="eGPU Game Config Swap" />;

  //   ★ 실패 안내를 **검사 대상 컴포넌트로 그리지 않는다.** PanelSection이 undefined인 상황을
  //     알리려고 PanelSection을 쓰면 그 안내마저 깨진다. 순수 div로 그린다.
  //   ★ 문구는 `t()`를 거친다. 설계가 인정한 하드코딩 예외는 ErrorBoundary 하나뿐이고,
  //     `t()`는 우리 번들 안이라 @decky/ui가 없어도 동작한다.
  if (missing.length > 0) {
    return (
      <div style={{ padding: "8px", fontSize: "13px" }}>
        {t("UI_CHECK_FAILED", { missing: missing.join(", ") })}
      </div>
    );
  }

  const counts = overview?.counts;

  // ★ `running`은 **이 한 줄에서만** 읽는다 — 문을 하나로 모아 두면 활성 조건으로 새어 들어갈 자리가 없다.
  //   (2026-08-05 QA 재인증 R6: 식별자 이름만 검사하면 `const ready = counts.running ? 0 : …` 처럼
  //    **값을 오염**시켜 우회할 수 있다. 그래서 검사도 "running은 표시 전용 표시가 붙은 줄에서만"으로 바꿨다.)
  // e1-display-only
  const runningNote = counts?.running ? t("BULK_RUNNING_NOTE", { n: counts.running }) : null;

  /**
   * **시작 안내 조건**(§3-B ④ · §3-D ② — H2). 두 줄이 이 하나의 식을 공유한다:
   * 조건을 각자 두면 프로필이 처음 생긴 날 한 줄만 사라진다.
   * 프로필이 하나라도 생기면 영구히 거짓이 된다.
   */
  const noProfilesYet =
    !!counts && counts.total > 0 && counts.dock_ready + counts.internal_ready === 0;

  /** 카운트 줄(§3-C). 조회 전에는 **빈 자리**다 — 모르는 것을 0으로 말하지 않는다(D01). */
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
   * 상태박스(§3-B) — **위=지금 / 아래=직전 결과**로 나뉜 한 개의 박스(D06).
   * 두 군 모두 비면 박스 자체를 그리지 않는다.
   */
  function renderStatusBox(): ReactNode {
    const now: ReactNode[] = [];
    // ⓪ 아직 아무것도 모른다. 실패가 있으면 그쪽이 더 정확한 말을 하므로 이 줄은 물러난다.
    if (!overview && !failure) {
      now.push(<div key="loading" style={{ color: MUTED_COLOR }}>{t("LOADING")}</div>);
    }
    // ① 진행 중 — 확인 중(무쓰기 왕복)과 적용 중(실제 쓰기)은 다른 말이다(D14).
    if (busy) {
      now.push(
        <div key="busy" style={{ color: MUTED_COLOR }}>
          {previewing ? t("APPLY_PREVIEWING") : t("APPLYING")}
        </div>,
      );
    }
    // ② 실행 중 게임 고지 — **표시 전용**이다(E1). 활성 조건이 아니다.
    if (runningNote) {
      now.push(<div key="running" style={{ color: MUTED_COLOR }}>{runningNote}</div>);
    }
    // ③ 실패 — 사유(tCode 단일 관문)와 **받은 시각**을 함께.
    if (failure) {
      now.push(
        <div key="failure" style={{ color: WARN_COLOR }}>
          {tCode(failure.code, failure.key)}
          <span>{" · "}{stampOf(failure.at)}</span>
        </div>,
      );
    }
    // ④ 시작 안내(H2) — 특정 게임을 겨냥하지 않으므로 A6(재촉 금지)에 저촉되지 않는다.
    if (noProfilesYet) {
      now.push(<div key="start" style={{ color: MUTED_COLOR }}>{t("NO_PROFILES_YET")}</div>);
    }

    const past: ReactNode[] = [];
    if (summary) {
      // ⑤ 결과 제목 — 아이콘이 성패를 먼저 말하고(D05), 시각이 "언제 것인지"를 말한다.
      past.push(
        <div key="result" style={{ ...RESULT_ROW_STYLE, color: MUTED_COLOR }}>
          <span style={{ display: "inline-flex", color: summary.problems ? WARN_COLOR : MUTED_COLOR }}>
            {summary.problems ? <IconWarn /> : <IconCheck />}
          </span>
          <span>{summary.headline}</span>
          <span>{" · "}{stampOf(summary.at)}</span>
        </div>,
      );
      // ⑥ 사유 — 이름과 조치가 여기 있다. 색은 주황 하나뿐이다(A8).
      if (summary.hints.length > 0) {
        past.push(
          <div key="why" style={{ color: WARN_COLOR }}>{summary.hints.join(" · ")}</div>,
        );
      }
      // ⑦ 체크인 고지(§5-E) — 사실 진술이므로 회색이다. 0건이면 줄을 만들지 않는다.
      if (summary.checkin > 0) {
        past.push(
          <div key="checkin" style={{ color: MUTED_COLOR }}>
            {t("CHECKIN_MANY", { n: summary.checkin })}
          </div>,
        );
      }
    }

    if (now.length === 0 && past.length === 0) return null;
    return (
      <PanelSectionRow>
        <div style={BOX_STYLE}>
          {now.length > 0 ? <div style={GROUP_STYLE}>{now}</div> : null}
          {past.length > 0 ? (
            /* busy 동안 과거군은 흐려진다 — *"지금 것이 아니다"*를 숨기지 않고 말하는 방법이다(D02-ⓑ). */
            <div
              style={{
                ...GROUP_STYLE,
                marginTop: now.length > 0 ? "8px" : "0",
                opacity: busy ? 0.4 : 1,
              }}
            >
              {past}
            </div>
          ) : null}
        </div>
      </PanelSectionRow>
    );
  }

  return (
    <>
      {/*
        ★ 제목을 두지 않는다(§3-A) — QAM 헤더의 `titleView`가 이미 플러그인 이름을 말한다.
      */}
      <PanelSection>
        {/*
          ★ 활성 조건은 **「그 프로필을 실제로 가진 게임 수 ≥ 1」 하나뿐**이다(설계 E1).
            실행 중인 게임 수는 여기 절대 들어가지 않는다 — 들어가면 게임 하나가 켜져 있다는
            이유로 아무것도 적용되지 않고, 그건 M1 불변식("하나만 거부하고 나머지는 적용")의
            정면 위반이다. running은 상태박스 고지 한 줄에서 **표시로만** 쓴다.
        */}
        {(["dock", "internal"] as const).map((profile) => (
          <BulkApplyButton
            key={profile}
            profile={profile}
            ready={(profile === "dock" ? counts?.dock_ready : counts?.internal_ready) ?? 0}
            hint={bulkHint(counts, profile)}
            busy={busy}
            onApply={runApplyAll}
          />
        ))}

        {/* 설명 영역(§3-D) — ①은 상시, ②는 시작 안내와 **같은 조건**에서만 뜬다(U-5). */}
        <PanelSectionRow>
          <div style={HINT_STYLE}>{t("QAM_ABOUT")}</div>
        </PanelSectionRow>
        {noProfilesYet && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>
              {t("QAM_ABOUT_GUIDE", { dock: t("PROFILE_DOCK"), internal: t("PROFILE_INTERNAL") })}
            </div>
          </PanelSectionRow>
        )}

        {renderStatusBox()}

        {/* 카운트 줄은 조회 전에도 **자리를 지킨다** — 값이 도착할 때 화면이 튀지 않는다. */}
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
  // ★ 진입점은 **QAM 하나**다(P15 — 전체 화면 route 제거). 그 하나를 경계로 감싼다(설계 E13):
  //   감싸지 않으면 렌더 실패가 트리를 통째로 무너뜨리고, Game Mode에서 아무 단서도 안 남는다.
  //   팝업 3종은 각자 자기 `DialogBody` 안쪽에 경계를 세운다(§4-A, R-4).
  return {
    name: "eGPU Game Config Swap",
    // titleClass()는 staticClasses가 없어도 TypeError를 내지 않는다(deckyui.ts).
    // i18n-exempt: 플러그인 이름(고유명사)
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
    // ★ `onDismount`를 두지 않는다(P15): 정리할 전역 등록이 하나도 없다. 빈 훅을 남겨 두면
    //   "여기서 무언가 정리한다"는 거짓 신호가 되고, 로더는 없으면 부르지 않는다.
  };
});
