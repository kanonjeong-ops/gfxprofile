import { useCallback, useEffect, useState } from "react";
import { DialogButton, Focusable, ToggleField, showModal } from "./deckyui";
import { DiscoverTab } from "./DiscoverTab";
import { ensureLang, isLangResolved, setProfileNames, t, tCode } from "./i18n";
import { LIST_BOTTOM_PADDING } from "./limits";
import { ManageTab } from "./ManageTab";
import { slotSummary } from "./slots";
import { SaveConfirmModal } from "./saveConfirm";
import { PLUGIN_VERSION } from "./version";
import {
  applyProfile, getOverview, saveProfile,
  type ConfirmParams, type Overview, type OverviewGame, type Profile,
} from "./rpc";

/**
 * 전체 화면 「현황」 탭 — 게임마다 두 프로필의 상태를 한 줄로 보여준다.
 *
 * ★ 왜 전체 화면인가: QAM은 **496px**이라 목록이 안 들어간다(2026-08-05 실측, 9행도 넘쳤다).
 *   그리고 이 화면은 **매 부팅 누르는 자리가 아니라** 프로필을 만들고 점검하는 저빈도 자리다.
 *
 * ★ 200게임에서도 성립해야 한다(설계 §0-A 상한):
 *   - **미완성 게임을 위로** 올린다 — 스크롤 없이 "무엇이 덜 됐나"가 먼저 보인다
 *   - **「미완성만 보기」 토글** — 텍스트 입력이 없다(M2-6: 이번 버전은 타이핑 0회)
 *   - `detail=true`로 한 번만 왕복한다 — 게임마다 RPC를 부르면 200번이 된다
 */

function StatusRow({
  game,
  busy,
  onApply,
  onSave,
}: {
  game: OverviewGame;
  busy: boolean;
  onApply: (appid: string, profile: Profile) => void;
  onSave: (appid: string, profile: Profile) => void;
}) {
  const incomplete = !game.has_dock || !game.has_internal;
  return (
    <Focusable
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "6px 10px",
        borderLeft: incomplete ? "3px solid #ffb454" : "3px solid transparent",
      }}
    >
      <div style={{ flex: "1 1 auto", minWidth: 0 }}>
        <div style={{ fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis" }}>
          {game.name}
        </div>
        <div style={{ fontSize: "11px", color: "#9aa0a6" }}>
          {/* ★ F5: 「저장됨 · 시각」. 문장은 `slots.ts` 한 곳에서 만든다 — 두 탭이 같은 것을
              말해야 하고, 「저장」과 「적용」을 화면이 섞지 않아야 한다(복원은 적용 기록을
              갱신하지 않는다 — 없는 사실을 만들지 않는다). */}
          {slotSummary(game)}
          {game.disk_matches ? ` · ${t("DISK_NOW", { profile: t(game.disk_matches === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") })}` : ""}
        </div>
      </div>
      {/*
        개별 적용은 **보조 동작**이다(주 동작은 QAM의 일괄 적용).
        ★ P4에서 저장을 붙였다. 프로필마다 [적용]·[저장]을 나란히 둔다 — M1의 주 흐름이
          *"게임에서 설정을 맞추고 완전 종료 → 그 프로필 줄에 저장"*이라 슬롯별로 갈려 있어야 한다.
        ⚠️ **[적용]에는 확인창을 붙이지 않는다**(사용자 판정 — 가장 자주 누르는 버튼이라 순수
           마찰이다. 재제안 금지). **[저장]에만 붙는다** — 저장은 덮어쓰기다.
      */}
      {(["dock", "internal"] as const).map((p) => (
        <div key={p} style={{ display: "flex", gap: "4px", flex: "0 0 auto" }}>
          <DialogButton
            disabled={busy || !(p === "dock" ? game.has_dock : game.has_internal)}
            onClick={() => onApply(game.appid, p)}
            style={{ minWidth: "88px", padding: "6px 8px", fontSize: "13px" }}
          >
            {t("APPLY_SHORT", { profile: t(p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") })}
          </DialogButton>
          {/* 저장은 **빈 슬롯에도** 눌러야 한다 — 프로필을 처음 만드는 동작이 이것이다.
              그래서 `has_*`로 비활성화하지 않는다(적용과 조건이 다르다).
              ★ 2026-08-07 실기: 라벨이 양쪽 다 「여기에 저장」이라 **어느 프로필인지 위치로만**
                갈렸다. M1은 세로 목록이라 줄 자체가 프로필이었지만 여기는 가로다.
                그리고 **빈 슬롯 첫 저장은 확인창이 안 뜨므로**(잃을 것이 없어서) 잘못 눌러도
                막아 줄 것이 없다 — *"무엇을 하는지 알고 누른다"*(결정 3-B) 위반이다. → 슬롯을 라벨에 박는다. */}
          <DialogButton
            disabled={busy}
            onClick={() => onSave(game.appid, p)}
            style={{ minWidth: "104px", padding: "6px 8px", fontSize: "13px" }}
          >
            {t("SAVE_SHORT", { profile: t(p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") })}
          </DialogButton>
        </div>
      ))}
    </Focusable>
  );
}

export function StatusPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [incompleteOnly, setIncompleteOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // ★ 라우트는 QAM 패널과 무관하게 마운트된다 — 패널을 안 열고 전체 화면부터 열면 언어가
  //   확정돼 있지 않다(2026-08-06 실기에서 영어로 뜨는 것을 확인). 여기서 직접 확정한다.
  const [langReady, setLangReady] = useState(isLangResolved());
  /**
   * ★ 「게임 추가」는 **새 route가 아니라 이 화면의 탭**이다(P6).
   *   route를 하나 더 만들면 `addRoute`/`removeRoute` 짝이 둘이 되고 `ensureLang`이 세 번째로
   *   나간다 — 얻는 것 없이 실패 지점만 는다. 게다가 게임 추가는 **저빈도 설정 작업**이라
   *   주 동작(QAM의 일괄 적용)과 경쟁하지 않는다.
   *   ⚠️ 이 `useState`는 **맨 뒤**에 둔다. 기존 프로브가 훅 슬롯 순서로 상태를 주입하므로
   *     중간에 끼워 넣으면 P3·P4 검사가 통째로 어긋난다.
   */
  const [tab, setTab] = useState<"status" | "discover" | "manage">("status");
  useEffect(() => {
    // 성공·실패 어느 쪽이든 게이트를 연다 — 안 열면 화면이 영원히 빈다(QA R2 ⑬)
    ensureLang(PLUGIN_VERSION, "route").then(
      () => setLangReady(true),
      () => setLangReady(true),
    );
  }, []);

  const load = useCallback(() => {
    // detail=true — 이 화면만 `disk_matches`를 쓴다.
    getOverview(true).then(
      (res) => {
        // ★ 표시명(F11 ①)은 봉투로 온다 — 상태를 넣기 **전에** i18n에 반영해야 첫 렌더부터
        //   사용자가 정한 이름이 나온다(나중에 갈아 끼우면 이름이 한 번 깜빡인다).
        if (res.ok) setProfileNames(res.data.profile_names);
        if (res.ok) setOverview(res.data);
        else setNote(tCode(res.code, "LOAD_FAILED"));
      },
      () => setNote(tCode("UNEXPECTED", "LOAD_FAILED")),
    );
  }, []);

  // ★ 2026-08-07 실기: 「게임 추가」에서 TEKKEN 7을 등록하고 「현황」으로 돌아왔더니
  //   **「등록 9개」가 그대로**였다. `load()`가 마운트 때 한 번뿐이라 탭 왕복이 갱신을 안 탄다.
  //   *"화면이 낡은 숫자를 말한다"*는 이 프로젝트가 반복해 고쳐 온 실패 모드다(라벨이 거짓말을 한다).
  //   → 「현황」으로 들어올 때마다 다시 읽는다. 마운트도 이 경로를 타므로 호출 수는 늘지 않는다.
  useEffect(() => {
    if (tab === "status") load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const onApply = useCallback(
    (appid: string, profile: Profile) => {
      setBusy(true);
      applyProfile(appid, profile)
        .then(
          (res) => {
            setNote(
              res.ok
                ? t("APPLY_ONE_OK", { profile: t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL") })
                : tCode(res.code, "APPLY_FAILED"),
            );
            load();
          },
          () => setNote(tCode("UNEXPECTED", "APPLY_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    [load],
  );

  /**
   * 저장 — 덮어쓰기라 **백엔드가 확인을 요구할 수 있다.**
   *
   * ★ 판정은 백엔드에만 있다. 여기서 *"덮어쓰기인가"*를 다시 계산하지 않는다 —
   *   두 곳에서 판정하면 언젠가 어긋나고, 어긋나는 순간 **확인 없는 덮어쓰기**가 생긴다.
   *   프론트가 하는 일은 `CONFIRM_REQUIRED`를 받으면 **받은 토큰을 그대로 되돌려 주는 것**뿐이다.
   *
   * ★★ `showModal`이 `undefined`여도 **안전하다** — 확인창이 안 뜨면 사용자가 확정할 수 없고,
   *   확정이 없으면 토큰이 안 돌아가고, 토큰이 없으면 백엔드가 저장하지 않는다.
   *   **fail-closed가 프론트의 성실함이 아니라 계약에서 나온다.** (R1이 지적한
   *   *"showModal은 export가 항상 함수라 self-check로 못 거른다"*가 여기서는 위험이 아니다.)
   */
  const onSave = useCallback(
    (appid: string, profile: Profile) => {
      const label = t(profile === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL");
      const finish = (res: Awaited<ReturnType<typeof saveProfile>>) => {
        setNote(res.ok ? t("SAVE_OK", { profile: label }) : tCode(res.code, "SAVE_FAILED"));
        load();
      };
      setBusy(true);
      saveProfile(appid, profile)
        .then((res) => {
          if (res.ok) return finish(res);
          if (res.code !== "CONFIRM_REQUIRED") return finish(res);

          // 덮어쓰기다 — 무엇을 잃는지 보여주고 확정을 받는다.
          const p = res.params as unknown as ConfirmParams;
          /*
           * ★ [2026-08-07 QA 반려 ②] **확인창을 못 띄우면 그 사실을 말해야 한다.**
           *   `showModal`은 런타임에 얻어지는 값이라 `undefined`일 수 있고, 그러면
           *   `TypeError`가 **`.then` 콜백 안에서** 난다 — `.then(fn, errFn)`의 두 번째 인자는
           *   그것을 못 잡는다. 그대로 두면 **note도 토스트도 없이 저장 버튼이 흔적 없이 죽는다.**
           *   안전한 쪽(=아무것도 안 씀)인 건 맞지만, 설계 §2-E-0이 요구한 것은 안전 **그리고**
           *   **진단 가능성**이다. "안전하니 됐다"로 요건을 조용히 바꾸지 않는다.
           */
          try {
            /*
             * ★ 확인창 자체는 `saveConfirm.tsx` 한 곳에 있다(P9) — 「관리」 탭의 복원 후속
             *   저장이 같은 흐름을 타기 때문이다. 같은 창을 두 화면이 각자 그리면 언젠가
             *   한쪽이 덜 말하게 된다.
             */
            showModal(
              <SaveConfirmModal
                params={p}
                profile={profile}
                onConfirm={() => {
                  setBusy(true);
                  // 받은 토큰을 **그대로** 되돌린다. 지어낼 수 없고, 고쳐 봐야 거부된다.
                  saveProfile(appid, profile, p.confirm_token)
                    .then(finish, () => setNote(tCode("UNEXPECTED", "SAVE_FAILED")))
                    .finally(() => setBusy(false));
                }}
              />,
            );
          } catch (err) {
            // 백엔드에 닿지 못한 것이 아니라 **화면이 못 뜬 것**이다 — 이건 실제로 오류라
            // `console.error`가 맞는 레벨이고, 이 레벨만 `cef_log`에 실린다(실측 사실 ②).
            console.error("[gfxprofile] confirm modal failed", err);
            setNote(t("SAVE_CONFIRM_MODAL_FAILED"));
          }
        }, () => setNote(tCode("UNEXPECTED", "SAVE_FAILED")))
        .finally(() => setBusy(false));
    },
    [load],
  );

  const games = overview?.games ?? [];
  // ★ 미완성을 위로. 같은 등급이면 이름순 — 200게임에서 "무엇이 덜 됐나"가 스크롤 없이 보인다.
  const sorted = [...games].sort((a, b) => {
    const ai = !a.has_dock || !a.has_internal ? 0 : 1;
    const bi = !b.has_dock || !b.has_internal ? 0 : 1;
    return ai - bi || a.name.localeCompare(b.name);
  });
  const shown = incompleteOnly ? sorted.filter((g) => !g.has_dock || !g.has_internal) : sorted;

  if (!langReady) return <div />;

  return (
    <div
      style={{
        // ★ 2026-08-06 실기: 위쪽을 16px만 두니 **제목이 Steam 상단바에 가려** 잘려 보였다.
        //   route 화면은 상단바 아래에서 시작하지 않는다 — 우리가 비워 줘야 한다.
        // ★ 아래쪽도 **같은 뿌리의 문제**다(F2, 사용자 실기 재현 확정): 16px로는 목록 마지막
        //   항목이 하단바에 가린다. 값은 `limits.ts` 한 곳에 있고 **세 탭이 이 컨테이너를
        //   공유**하므로, 탭이 늘어도 여기 하나만 맞으면 된다(탭별 패딩 금지 — DELETE §4-B).
        padding: `56px 20px ${LIST_BOTTOM_PADDING}`,
        height: "100%",
        overflowY: "auto",
      }}
    >
      {/* i18n-exempt: 플러그인 이름(고유명사) */}
      <div style={{ fontSize: "20px", fontWeight: "bold", marginBottom: "4px" }}>eGPU Game Config Swap</div>

      {/* 탭 버튼도 `Focusable` 안에 있어야 한다 — 밖에 두면 D-패드가 영영 도달하지 못한다
          (2026-08-06 실기에서 토글이 실제로 그랬다). `DialogButton`이라 도달성 검사가 자동으로 덮는다. */}
      <Focusable style={{ display: "flex", gap: "8px", margin: "4px 0 10px" }}>
        {(["status", "discover", "manage"] as const).map((key) => (
          <DialogButton
            key={key}
            onClick={() => setTab(key)}
            style={{
              minWidth: "140px", padding: "6px 10px", fontSize: "13px",
              opacity: tab === key ? 1 : 0.55,
            }}
          >
            {t(key === "status" ? "TAB_STATUS" : key === "discover" ? "TAB_DISCOVER" : "TAB_MANAGE")}
          </DialogButton>
        ))}
      </Focusable>

      {/*
        ⚠️ 분기를 **한 줄에 이어 쓰지 않는다.** `A /> : tab === "manage" ? <B` 형태가 되면
        `test_i18n_sets`의 JSX 텍스트 정규식(`>…<`)이 그 사이의 코드를 **화면 글자로 오인**해
        거짓 FAIL을 낸다(실제로 냈다). 검사를 느슨하게 하는 대신 코드를 갈라 놓는다 —
        오탐도 거짓 검사이고, 느슨해진 검사는 다음 사람이 꺼 버린다.
      */}
      {tab === "discover" ? (
        <DiscoverTab />
      ) : tab === "manage" ? (
        <ManageTab />
      ) : (
        <>
      <div style={{ fontSize: "13px", color: "#9aa0a6", marginBottom: "12px" }}>
        {overview === null ? "" : t("STATUS_SUMMARY", {
          total: overview?.counts.total ?? 0,
          incomplete: overview?.counts.incomplete ?? 0,
        })}
      </div>

      {/* ★ 2026-08-06 실기: ToggleField가 Focusable 밖에 있어 **D-패드로 도달할 수 없었다.**
          게임패드 네비게이션은 Focusable 컨테이너 안만 순회한다 — 행 목록(아래)은 감싸져 있어서
          도달됐고 이 토글만 영영 포커스를 못 받았다. 핸드헬드에서 못 누르는 컨트롤은 없는 것과 같다.
          `test_status_page.py`는 필터 **로직**만 재고 **도달성**은 안 재서 통과했다. */}
      <Focusable>
        <ToggleField
          label={t("FILTER_INCOMPLETE_ONLY")}
          checked={incompleteOnly}
          onChange={setIncompleteOnly}
        />
      </Focusable>

      {note ? (
        <div style={{ fontSize: "12px", color: "#9aa0a6", margin: "8px 0" }}>{note}</div>
      ) : null}

      <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "8px" }}>
        {shown.map((g) => (
          <StatusRow key={g.appid} game={g} busy={busy} onApply={onApply} onSave={onSave} />
        ))}
      </Focusable>

      {/* ★ 2026-08-06 QA 지적 ⑦: overview가 null인 경우는 (a) 최초 로딩 중 (b) get_overview 실패
          두 가지다. 예전엔 둘 다 "등록된 게임이 없습니다"로 단언해서, 9게임이 멀쩡한데 화면이
          0개라고 거짓말했다. **모르는 것을 없다고 말하지 않는다.** */}
      {overview === null ? (
        // 실패 문구는 위의 note 줄이 이미 그린다 — 여기서 또 그리면 같은 말을 두 번 한다.
        // note가 없다면 아직 로딩 중이다.
        note ? null : (
          <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>{t("LOADING")}</div>
        )
      ) : shown.length === 0 ? (
        <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>
          {t(incompleteOnly ? "FILTER_NONE_INCOMPLETE" : "NO_GAMES")}
        </div>
      ) : null}
        </>
      )}
    </div>
  );
}
