import { useCallback, useState } from "react";
import { makeNameEditSpec, makeResetConfirmSpec } from "./confirmSpecs";
import { DialogButton, Focusable } from "./deckyui";
import { IconGear, IconTrash } from "./icons";
import { setProfileNames, t, tCode } from "./i18n";
import { GfxPopup, PopupNote, usePopupData, usePopupGate } from "./popup";
import {
  getOverview, resetAll, setProfileName,
  type Overview, type Profile, type ResetConfirmParams,
} from "./rpc";

/**
 * **팝업 S — 설정** (설계 §7). **전역 전용**이다: 프로필 표시 이름과 전체 초기화뿐이고,
 * 게임별 동작은 하나도 없다(A4).
 *
 * ★★ 왜 게임별 동작과 완전히 가르는가: 「관리」 탭 시절에는 게임 목록·삭제·표시명·초기화가
 *   한 화면에 있었고, 그래서 *"전체 초기화"*가 게임 행들의 **연장선**처럼 읽혔다. 파괴 범위가
 *   가장 큰 동작이 목록 끝에 붙어 있으면 "다음 항목"으로 읽힌다 — 화면을 갈라서 그 오독의
 *   자리를 없앤다.
 *
 * ★ **"위험 구역"이라는 빨간 구획은 두지 않는다**(§18-① 확정). 위험색은 초기화 확인창의
 *   ⚠ 블록 하나뿐이다(A8) — 화면마다 위험 표시가 다르면 어느 것이 진짜 경고인지 흐려진다.
 *
 * ★ P15-C에서 QAM 진입 버튼에 배선됐다(그 전에는 아무도 부르지 않았고, tsc·i18n·프로브만 돌았다).
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const META_STYLE = { fontSize: "11px", color: "#9aa0a6" } as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;
const SECTION_STYLE = { marginTop: "16px", paddingTop: "10px", borderTop: "1px solid #3a3f44" } as const;
const SECTION_TITLE_STYLE = { fontSize: "14px", fontWeight: "bold", marginBottom: "6px" } as const;
const ROW_STYLE = { display: "flex", alignItems: "center", gap: "8px", padding: "6px 0" } as const;
const ICON_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginRight: "4px",
} as const;

function profileKey(p: Profile) {
  return p === "dock" ? "PROFILE_DOCK" : "PROFILE_INTERNAL";
}

export function SettingsPopup({
  onMutate,
  closeModal,
}: {
  onMutate?: () => void;
  closeModal?: () => void;
}) {
  /**
   * type-to-confirm으로 찍다 만 값(GP#9). 가상 키보드로 한 글자씩 찍은 입력이 B 오조작
   * 한 번에 사라지지 않게, 확인창이 언마운트될 때 여기로 받아 두었다가 다음에 되돌려준다.
   */
  const [resetTyped, setResetTyped] = useState("");
  const [nameTyped, setNameTyped] = useState<Partial<Record<Profile, string>>>({});

  // 이 화면은 `disk_matches`를 쓰지 않는다 — detail을 켜면 게임마다 원본 파일 sha1을 다시 읽는다.
  const load = useCallback(() => getOverview(), []);
  /* ★ busy·재조회·변경 통지는 **훅 한 곳**을 지난다(§4-F 개정). */
  const { data, note, setNote, busy, runMutation } = usePopupData<Overview>(load, "LOAD_FAILED", onMutate);
  const { gate, renderBody } = usePopupGate();

  const counts = data?.counts;

  /**
   * 전체 초기화 — 흐름은 다른 파괴 동작과 같다(토큰 없이 한 번 → `CONFIRM_REQUIRED` →
   * 받은 토큰을 **그대로** 되돌림). 다른 점은 확인창이 2단(입력 대조)이라는 것뿐이다.
   *
   * ⚠️ 게임별 실패가 있어도 봉투는 `ok:true`다 — **무엇이 남았는지**를 같이 말한다(F26).
   */
  const runReset = useCallback(
    (token?: string, text?: string) =>
      runMutation(() => resetAll(token, text), "RESET_ACTION_FAILED", (res) => {
        if (res.ok) {
          const deleted = res.data.counts.deleted ?? 0;
          const left = res.data.results.length - deleted;
          const ok = t("RESET_OK", { deleted, left });
          setNote(left > 0 ? `${ok} ${t("RESET_LEFT_NOTE", { left })}` : ok);
          setResetTyped("");           // 성공했으면 보존할 입력도 없다
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ResetConfirmParams;
          gate(
            makeResetConfirmSpec(
              p,
              resetTyped,
              (value) => { void runReset(p.confirm_token, value); },
              setResetTyped,
            ),
            // 토큰이 안 돌아가면 아무것도 지워지지 않는다 — 이 문구가 참인 자리다.
            "MANAGE_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // 확정 실행의 거절이다 — 어디까지 지워졌는지 모르므로 재조회·통지가 따라온다(§4-F ③).
        setNote(tCode(res.code, "RESET_ACTION_FAILED"));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate, resetTyped],
  );

  /**
   * 표시 이름 변경 — **식별자는 이 경로로 절대 움직이지 않는다.** 백엔드가 정규화(공백 정리·
   * 상한 자르기·빈 값이면 기본값 복귀)한 **결과를 그대로** 받아 i18n에 반영한다.
   */
  const runRename = useCallback(
    (profile: Profile, name: string) =>
      runMutation(() => setProfileName(profile, name), "NAME_EDIT_FAILED", (res) => {
        if (!res.ok) {
          setNote(tCode(res.code, "NAME_EDIT_FAILED"));
          return;
        }
        setProfileNames(res.data.profile_names);
        const saved = res.data.profile_names[profile];
        setNote(saved ? t("NAME_EDIT_OK_NOTE", { name: saved }) : t("NAME_EDIT_RESET_NOTE"));
        setNameTyped((prev) => ({ ...prev, [profile]: undefined }));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /**
   * 편집창을 연다. **프리필 규칙(기본 이름이면 빈 칸)은 spec 안에 있다** — 호출부가 계산하면
   * 여기와 TOCTOU 재오픈이 각자 판단해 언젠가 갈라진다(P12 게이트 C2).
   */
  function askRename(profile: Profile) {
    gate(
      makeNameEditSpec(
        // `t()`는 사용자가 정한 이름이 있으면 그것을 돌려준다 = "지금 보이는 이름".
        { profile, current: t(profileKey(profile)), snapshot: nameTyped[profile] },
        (value) => { void runRename(profile, value); },
        (value) => setNameTyped((prev) => ({ ...prev, [profile]: value })),
      ),
      "NAME_EDIT_MODAL_FAILED",
      setNote,
    );
  }

  /**
   * **초기화 버튼의 활성 조건**(D-01 — 세션 확정): `total > 0 || excluded > 0`.
   *
   * ★★ 왜 `total`만으로는 안 되는가: 마지막 게임을 등록 해제하면 `total`은 0이 되는데 감지
   *   제외 목록은 남는다. `total>0`만 조건이면 **그 목록을 지울 방법이 화면에서 사라져**
   *   A9 ④("초기화가 제외 목록도 지운다")가 도달 불가가 된다.
   * ★ 수는 **봉투가 준 값**이다(`counts.excluded`) — 프론트가 다시 세지 않는다.
   * ★ 조회 실패(=counts 없음)일 때는 **활성 유지**다(F24·S-02): ⓐ 일시 원인이 섞여 있어 원천
   *   차단은 과잉이고 ⓑ 눌러도 오발동이 없다 — 백엔드가 토큰+challenge로 fail-closed이고,
   *   registry가 실제로 손상됐다면 `reset_all`이 첫 줄의 `load_registry()`에서 같은 코드로
   *   거부해 **토큰 발급 자체가 안 된다**(정확한 사유가 note로 뜨는 정직한 실패).
   *   ⚠️ 즉 이것은 **손상 복구의 탈출구가 아니다.** 로딩 중(아직 아무것도 모름)만 비활성이다.
   */
  const loading = data === null && !note;
  const resetEnabled = counts ? counts.total > 0 || counts.excluded > 0 : !loading;

  return (
    <GfxPopup title={t("SETTINGS_TITLE")} icon={<IconGear />} where="popup-s" closeModal={closeModal}>
      {renderBody(
        <div style={COLUMN_STYLE}>
          <PopupNote note={note} />

          {/* ── 프로필 표시 이름 ─────────────────────────────────────────────
              바꾸는 것은 **화면 글자뿐**이다. 저장된 프로필·백업·경로는 그대로 있고,
              그 사실을 안내 줄이 말한다(사용자가 가장 오해하기 쉬운 지점이다). */}
          <div>
            <div style={SECTION_TITLE_STYLE}>{t("SETTINGS_NAMES_TITLE")}</div>
            <div style={HINT_STYLE}>{t("MANAGE_NAMES_HINT")}</div>
            <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "6px" }}>
              {(["dock", "internal"] as const).map((profile) => (
                <Focusable key={profile} style={ROW_STYLE}>
                  <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                    <div style={{ fontSize: "15px" }}>{t("MANAGE_NAME_ROW", { profile: t(profileKey(profile)) })}</div>
                    <div style={META_STYLE}>
                      {/* 봉투의 빈 문자열이 곧 "기본 이름"이다 — 화면이 다시 판정하지 않는다. */}
                      {data?.profile_names?.[profile] ? t("MANAGE_NAME_CUSTOM") : t("MANAGE_NAME_DEFAULT")}
                    </div>
                  </div>
                  <DialogButton
                    disabled={busy}
                    onClick={() => askRename(profile)}
                    style={{ minWidth: "140px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
                  >
                    {t("MANAGE_NAME_EDIT")}
                  </DialogButton>
                </Focusable>
              ))}
            </Focusable>
          </div>

          {/* ── 전체 초기화 ──────────────────────────────────────────────────
              구획선으로만 가른다(빨간 구획·"위험 구역" 명칭 없음 — §18-①). */}
          <div style={SECTION_STYLE}>
            <div style={SECTION_TITLE_STYLE}>{t("SETTINGS_RESET_TITLE")}</div>
            <div style={{ fontSize: "13px", marginBottom: "8px" }}>
              {/* 수를 모르면 **모른다고 말한다** — 0으로 그리면 화면이 거짓을 말한다. */}
              {t("RESET_ZONE_BODY", { n: counts ? counts.total : t("RESET_ZONE_UNKNOWN") })}
            </div>
            <Focusable>
              <DialogButton
                disabled={busy || !resetEnabled}
                onClick={() => { void runReset(); }}
                style={{ minWidth: "220px" }}
              >
                <span style={ICON_SLOT_STYLE}><IconTrash /></span>
                {t("RESET_OPEN")}
              </DialogButton>
            </Focusable>
            <div style={HINT_STYLE}>{t("RESET_HINT")}</div>
          </div>
        </div>,
      )}
    </GfxPopup>
  );
}
