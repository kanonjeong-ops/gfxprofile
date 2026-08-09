import { definePlugin, routerHook, toaster, useQuickAccessVisible } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import {
  applyAll,
  getOverview,
  type ApplyRow,
  type Outcome,
  type Overview,
  type Profile,
} from "./rpc";
import { ensureLang, t, tCode, type StringKey } from "./i18n";
import { PLUGIN_VERSION } from "./version";
import { BulkApplyButton } from "./BulkApplyButton";
import { ErrorBoundary } from "./ui/ErrorBoundary";
import { StatusPage } from "./StatusPage";
import {
  DialogButton,
  Navigation,
  PanelSection,
  PanelSectionRow,
  titleClass,
  uicheckMissing,
} from "./deckyui";

// ── 진단 태그 ────────────────────────────────────────────────────────────────
// cef_log.txt는 여러 달치 append-only라, 태그에 이번 프론트 로드를 가리키는 nonce(fn)가
// 없으면 과거 부팅의 태그와 구분할 수 없다(설계 E6). 세 태그 전부에 fn을 붙인다.
// 이 문자열들은 **의도적으로 번역하지 않는다** — 번역되면 진단 grep이 언어에 따라 깨진다.

// 전체 화면 route. `onDismount`에서 반드시 제거한다 — 플러그인을 껐다 켜면 중복 등록된다.
const ROUTE = "/gfxprofile";
const FN = Math.random().toString(36).slice(2, 6);

// ★ [실측 2026-08-05] Steam CEF에서 **`console.error`만 `cef_log.txt`에 실린다.**
//   `log`/`warn`/`info`는 한 건도 안 남는다(프로브로 확인: error 1건 / 나머지 0건).
//   그래서 진단을 두 갈래로 나눈다 —
//     · 정상 신호는 `ui_hello`로 **백엔드 로그 한 곳에** 모은다. 거기엔 session·fn이 이미 있고,
//       플러그인별로 파일이 갈려 있어 부팅 세션을 구분할 필요조차 없다.
//     · **백엔드에 닿지 못한 경우에만** console.error로 남긴다. 그건 실제로 오류이므로
//       error 레벨이 의미상으로도 맞고, 그 상황에서 남길 곳이 cef_log뿐이다.
//   이 구조는 "cef_log를 grep해 부팅 세션을 가려내는" 문제를 통째로 없앤다.
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

function buildSummary(
  profile: Profile,
  rows: ApplyRow[],
  counts: Partial<Record<Outcome, number>>,
): { headline: string; hints: string[] } {
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
  if (running.length > 0) hints.push(t("APPLY_PROBLEM_REFUSED", { n: running.length }));

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
    const shown = group.slice(0, CAP_NAMES).map((r) => r.name).join(", ");
    const more = group.length - CAP_NAMES;
    const names = more > 0 ? t("NAMES_AND_MORE", { names: shown, n: more }) : shown;
    hints.push(t("APPLY_PROBLEM_SPECIFIC", { names, reason: tCode(code, "APPLY_FAILED") }));
  }
  return { headline, hints };
}

// ★ 마지막 일괄 적용 요약은 **컴포넌트 밖**에 둔다.
//   QAM을 닫으면 패널이 언마운트되므로(실측: 다시 열면 요약 줄이 사라졌다) 상태에만 두면
//   "무슨 일이 있었는지"가 창을 닫는 순간 없어진다. 결과는 화면 수명보다 오래 남아야 한다.
let lastSummary: { title: string; body: string } | null = null;

const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;

function Content() {
  const missing = uicheckMissing();
  const visible = useQuickAccessVisible();

  // langReady = ui_hello가 (성공이든 실패든) 끝났다 = 어느 언어로 그릴지 확정됐다.
  // 이것을 기다렸다가 그리기 때문에 "영어로 그렸다가 한국어로 바뀌는" 깜빡임이 없다 —
  // 폴백 문구를 나중에 갈아끼우는 처리를 만드는 대신 그 상황 자체를 없앴다.
  const [langReady, setLangReady] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failure, setFailure] = useState<{ key: StringKey; code: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // 마지막 일괄 적용의 요약. 한 줄이라 스크롤을 만들지 않는다(긴 목록은 모달에 있다).
  // 초기값을 모듈 변수에서 받으므로 QAM을 닫았다 열어도 남아 있다.
  const [summary, setSummary] = useState(lastSummary);

  const refresh = useCallback(() => {
    getOverview().then(
      (res) => {
        if (res.ok) {
          setOverview(res.data);
          setFailure(null);
        } else {
          setFailure({ key: "LOAD_FAILED", code: res.code });
        }
      },
      (err) => {
        // 백엔드에 닿지 못한 경우다 — 남길 곳이 cef_log뿐이라 여기만 console.error다.
        failTag(`overview-failed err=${String(err)}`);
        setFailure({ key: "LOAD_FAILED", code: "UNEXPECTED" });
      },
    );
  }, []);

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

  const runApplyAll = useCallback(
    (profile: Profile) => {
      setBusy(true);
      applyAll(profile)
        .then(
          (res) => {
            if (res.ok) {
              const { headline, hints } = buildSummary(profile, res.data.results, res.data.counts);

              // ★ 결과의 **정본은 이 상태**다. 모달은 없앴고(2026-08-06 사용자 결정),
              //   토스트는 QAM이 닫혀 있어도 도달하는 부가 채널일 뿐이다 —
              //   토스트가 실패해도 아래 요약 줄은 이미 붙잡혀 있다.
              lastSummary = { title: headline, body: hints.join(" · ") };
              setSummary(lastSummary);
              setFailure(null);

              try {
                toaster.toast({ title: headline, body: hints.join(" · ") });
              } catch (err) {
                failTag(`toast-failed err=${String(err)}`);
              }
              refresh();
            } else {
              // ⚠️ 게임별 실패는 여기 오지 않는다. 봉투가 ok:false인 것은
              //    일괄 적용 자체가 시작도 못 한 경우뿐이다.
              setFailure({ key: "APPLY_FAILED", code: res.code });
            }
          },
          (err) => {
            failTag(`apply-all-failed err=${String(err)}`);
            setFailure({ key: "APPLY_FAILED", code: "UNEXPECTED" });
          },
        )
        .finally(() => setBusy(false));
    },
    [refresh],
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

  return (
    <>
      {/* i18n-exempt: 플러그인 이름(고유명사) */}
      <PanelSection title="eGPU Game Config Swap">
        {/*
          ★ 활성 조건은 **「그 프로필을 실제로 가진 게임 수 ≥ 1」 하나뿐**이다(설계 E1).
            실행 중인 게임 수는 여기 절대 들어가지 않는다 — 들어가면 게임 하나가 켜져 있다는
            이유로 아무것도 적용되지 않고, 그건 M1 불변식("하나만 거부하고 나머지는 적용")의
            정면 위반이다. running은 아래 고지 한 줄에서 **표시로만** 쓴다.
        */}
        {(["dock", "internal"] as const).map((profile) => (
          <BulkApplyButton
            key={profile}
            profile={profile}
            ready={(profile === "dock" ? counts?.dock_ready : counts?.internal_ready) ?? 0}
            busy={busy}
            onApply={runApplyAll}
          />
        ))}

        {busy && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>{t("APPLYING")}</div>
          </PanelSectionRow>
        )}

        {runningNote && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>{runningNote}</div>
          </PanelSectionRow>
        )}

        {!!counts?.incomplete && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>{t("PROFILE_INCOMPLETE", { n: counts.incomplete })}</div>
          </PanelSectionRow>
        )}

        {counts?.total === 0 && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>{t("NO_GAMES")}</div>
          </PanelSectionRow>
        )}

        {summary && (
          <PanelSectionRow>
            <div style={HINT_STYLE}>{summary.title}</div>
          </PanelSectionRow>
        )}

        {summary?.body ? (
          <PanelSectionRow>
            <div style={{ ...HINT_STYLE, color: "#ffb454" }}>{summary.body}</div>
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          {/*
            전체 화면으로 가는 유일한 입구. QAM(496px)에는 목록이 안 들어가므로
            현황·개별 조작은 저기서 한다(설계 §3 프론트 2층).
          */}
          <DialogButton onClick={() => Navigation.Navigate(ROUTE)}>
            {t("OPEN_FULL_SCREEN")}
          </DialogButton>
        </PanelSectionRow>

        {failure && (
          <PanelSectionRow>
            <div style={{ ...HINT_STYLE, color: "#ffb454" }}>
              {/* 원시 코드 식별자를 그대로 보이지 않는다 — tCode가 단일 관문이다(P5). */}
              {tCode(failure.code, failure.key)}
            </div>
          </PanelSectionRow>
        )}
      </PanelSection>
    </>
  );
}

/**
 * 전체 화면 route를 경계로 감싼 것 (설계 E13).
 * `routerHook.addRoute`는 **컴포넌트**를 받으므로 인라인 JSX가 아니라 이 래퍼가 필요하다.
 */
function RoutedStatusPage() {
  return (
    <ErrorBoundary where="route">
      <StatusPage />
    </ErrorBoundary>
  );
}

export default definePlugin(() => {
  // ★ 두 진입점을 **각각** 감싼다(설계 E13). 하나만 감싸면 다른 쪽 렌더 실패가 그대로 트리를
  //   무너뜨리고, 그 화면은 Game Mode에서 아무 단서도 남기지 않는다.
  routerHook.addRoute(ROUTE, RoutedStatusPage, { exact: true });
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
    onDismount() {
      routerHook.removeRoute(ROUTE);
    },
  };
});
