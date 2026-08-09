import { useCallback, useEffect, useState } from "react";
import { ConfirmModal, DialogButton, Focusable, TextField, showModal } from "./deckyui";
import { t, tCode } from "./i18n";
import {
  deleteGame, getOverview, resetAll,
  type DeleteConfirmParams, type Overview, type OverviewGame, type Profile, type ResetConfirmParams,
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

function ManageRow({
  game,
  busy,
  onDelete,
}: {
  game: OverviewGame;
  busy: boolean;
  onDelete: (appid: string) => void;
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
          {t(game.has_dock ? "SLOT_SAVED" : "SLOT_EMPTY", { profile: t("PROFILE_DOCK") })}
          {" · "}
          {t(game.has_internal ? "SLOT_SAVED" : "SLOT_EMPTY", { profile: t("PROFILE_INTERNAL") })}
        </div>
      </div>
      {/* ★ 행당 파괴 버튼은 **하나뿐**이다. F6의 [백업 N](읽기 전용 진입)이 나중에 같은 행에
          붙어도 오탭의 최악 결과가 "모달 하나 잘못 열림"에 머물러야 한다 — 그 비대칭이
          이 행 구성의 근거다(설계 §4-B 개정 2판). */}
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
    try {
      showModal(
        <DeleteConfirm params={p} onConfirm={() => { void runDelete(p.appid, p.confirm_token); }} />,
      );
    } catch (err) {
      console.error("[gfxprofile] delete confirm modal failed", err);
      setNote(t("MANAGE_MODAL_FAILED"));
    }
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

  function askReset(p: ResetConfirmParams) {
    try {
      showModal(
        <ResetConfirm
          params={p}
          onConfirm={(text) => { void runReset(p.confirm_token, text); }}
        />,
      );
    } catch (err) {
      console.error("[gfxprofile] reset confirm modal failed", err);
      setNote(t("MANAGE_MODAL_FAILED"));
    }
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
          <ManageRow key={g.appid} game={g} busy={busy} onDelete={(appid) => void runDelete(appid)} />
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
