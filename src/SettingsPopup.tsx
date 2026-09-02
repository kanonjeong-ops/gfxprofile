import { useCallback, useRef } from "react";
import { makeNameEditSpec, makeResetConfirmSpec } from "./confirmSpecs";
import { Focusable } from "./deckyui";
import { IconGear, IconTrash } from "./icons";
import { hasProfileNameOverride, setProfileNames, t, tCode } from "./i18n";
import {
  GfxPopup, ICON_SLOT_STYLE, PopupButton, STACKED_BUTTON_STYLE, STACKED_DESC_PAD,
  usePopupData, usePopupGate,
} from "./popup";
import {
  getOverview, resetAll, setProfileName,
  type Overview, type Profile, type ResetConfirmParams,
} from "./rpc";

/**
 * 팝업 S — 설정. 전역 전용이다: 프로필 표시 이름과 전체 초기화뿐이고, 게임별 동작은
 * 하나도 없다.
 *
 * 왜 게임별 동작과 완전히 가르는가: 파괴 범위가 가장 큰 동작이 게임 목록 끝에 붙어 있으면
 * "다음 항목"으로 읽힌다. 화면을 갈라 그 오독의 자리를 없앤다.
 *
 * "위험 구역"이라는 빨간 구획은 두지 않는다. 렌더러가 따로 위험 블록으로 그리는 자리는
 * 초기화 확인창의 `warnBlock` 하나뿐이다 — 화면마다 위험 표시가 다르면 어느 것이 진짜
 * 경고인지 흐려진다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
/* 잔글씨 2종은 전부 한국어 문장을 그린다(이 화면에는 경로·파일명 슬롯이 없다) —
   `wordBreak: "keep-all"`로 낱말 중간 줄바꿈을 막는다(정본: `popup.tsx`의 `KEEP_ALL_STYLE`). */
const META_STYLE = { fontSize: "11px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6", wordBreak: "keep-all" } as const;
const SECTION_STYLE = { marginTop: "16px", paddingTop: "10px", borderTop: "1px solid #3a3f44" } as const;
const SECTION_TITLE_STYLE = { fontSize: "14px", fontWeight: "bold", marginBottom: "6px" } as const;
const ROW_STYLE = { display: "flex", alignItems: "center", gap: "8px", padding: "6px 0" } as const;

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
   * type-to-confirm으로 찍다 만 값. 가상 키보드로 한 글자씩 찍은 입력이 B 오조작 한 번에
   * 사라지지 않게, 확인창이 언마운트될 때 여기로 받아 두었다가 다음에 되돌려준다.
   *
   * 상태가 아니라 ref다: 확인창의 `onOK`는 그 창을 연 시점의 클로저를 들고 있고, TOCTOU
   *   재질문은 그 안에서 자기 자신(`runReset`)을 다시 부른다. 상태로 들면 재질문이 보는 값은
   *   창이 열리던 시점의 것 — 즉 방금 찍은 입력이 없는 값이다. ref는 언제 만들어진
   *   클로저에서 읽어도 지금 값이라 그 갈래 자체가 없다(`usePopupData`의 `notify` ref와 같은
   *   판단).
   * 화면은 이 값을 그리지 않는다 — 그리는 것은 확인창의 TextField이고 그 상태는 렌더러가
   *   소유한다. 다시 그릴 이유가 없으므로 상태일 필요도 없다.
   */
  const resetTyped = useRef("");
  const nameTyped = useRef<Partial<Record<Profile, string>>>({});

  // 이 화면은 `disk_matches`를 쓰지 않는다 — detail을 켜면 게임마다 원본 파일 sha1을 다시 읽는다.
  const load = useCallback(() => getOverview(), []);
  /* busy·재조회·변경 통지는 훅 한 곳을 지난다. */
  const { data, noteText, setNote, noteView, busy, runMutation } =
    usePopupData<Overview>(load, "LOAD_FAILED", onMutate);
  const { gate, renderBody } = usePopupGate();

  const counts = data?.counts;

  /**
   * 전체 초기화 — 흐름은 다른 파괴 동작과 같다(토큰 없이 한 번 → `CONFIRM_REQUIRED` →
   * 받은 토큰을 그대로 되돌림). 다른 점은 확인창이 2단(입력 대조)이라는 것뿐이다.
   *
   * 게임별 실패가 있어도 봉투는 `ok:true`다 — 무엇이 남았는지를 같이 말한다.
   */
  const runReset = useCallback(
    (token?: string, text?: string) =>
      runMutation(() => resetAll(token, text), "RESET_ACTION_FAILED", (res) => {
        if (res.ok) {
          const deleted = res.data.counts.deleted ?? 0;
          const left = res.data.results.length - deleted;
          /* 완료 문구는 지운 것만 말한다 — 0인 범주는 문장 자체를 그리지 않는다. 다 지워졌을
             때 "0개 남음"을 그리면 없던 일을 사건처럼 말하게 되고, 남은 게 있을 때는 같은 수를
             두 번 말하게 된다.
             `counts.deleted`(=게임 수) 하나로 초기화를 통째로 선언하지 않는다: 등록 0 · 제외
             N인 상태에서는 화면이 "0개 삭제"라고 말하는 사이 제외 N건과 표시 이름이 조용히
             사라진다 — 부분합을 전체처럼 말하는 자리다. 범주마다 제 수를 말하고, 말할 것이
             하나도 없을 때만 일반 완료문을 그린다.
             `cleared`는 봉투가 준 값이다(`counts`와 같은 규칙 — 프론트가 다시 세지 않는다).
             확인창 `params`의 `named`/`excluded`는 다른 시점의 값이라 재사용하지 않는다. */
          const parts: string[] = [];
          if (deleted > 0) {
            parts.push(t("RESET_OK_GAMES", { n: deleted }));
          }
          if (res.data.cleared.named > 0) {
            parts.push(t("RESET_OK_NAMES", { n: res.data.cleared.named }));
          }
          if (res.data.cleared.excluded > 0) {
            parts.push(t("RESET_OK_EXCLUDED", { n: res.data.cleared.excluded }));
          }
          // 남은 것은 `left > 0`일 때만 이 줄이 말한다 — 언제나 마지막이다.
          if (left > 0) {
            parts.push(t("RESET_LEFT_NOTE", { left }));
          }
          if (parts.length === 0) {
            parts.push(t("RESET_OK"));
          }
          setNote(parts.join(" "));
          resetTyped.current = "";     // 성공했으면 보존할 입력도 없다
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ResetConfirmParams;
          gate(
            makeResetConfirmSpec(
              p,
              resetTyped.current,
              (value) => { void runReset(p.confirm_token, value); },
              (value) => { resetTyped.current = value; },
            ),
            // 토큰이 안 돌아가면 아무것도 지워지지 않는다 — 이 문구가 참인 자리다.
            "MANAGE_MODAL_FAILED",
            setNote,
          );
          return;
        }
        // 토큰 발급 전 또는 확정 실행 중의 실패다. 상태를 단정하지 않고 재조회·통지한다.
        setNote(tCode(res.code, "RESET_ACTION_FAILED"));
      }),
    // 보존값을 ref로 읽으므로 이 문은 한 번 만들어지면 계속 옳다 — deps에 입력값이 없다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate],
  );

  /**
   * 표시 이름 변경 — 식별자는 이 경로로 절대 움직이지 않는다. 백엔드가 정규화(공백 정리·
   * 상한 자르기·빈 값이면 기본값 복귀)한 결과를 그대로 받아 i18n에 반영한다.
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
        nameTyped.current = { ...nameTyped.current, [profile]: undefined };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /**
   * 편집창을 연다. 프리필 규칙(기본 이름이면 빈 칸)은 spec 안에 있다 — 호출부가 계산하면
   * 여기와 TOCTOU 재오픈이 각자 판단해 언젠가 갈라진다.
   */
  function askRename(profile: Profile) {
    gate(
      makeNameEditSpec(
        // `t()`는 사용자가 정한 이름이 있으면 그것을 돌려준다 = "지금 보이는 이름".
        { profile, current: t(profileKey(profile)), snapshot: nameTyped.current[profile] },
        (value) => { void runRename(profile, value); },
        (value) => { nameTyped.current = { ...nameTyped.current, [profile]: value }; },
      ),
      "NAME_EDIT_MODAL_FAILED",
      setNote,
    );
  }

  /**
   * 초기화 버튼의 활성 조건: `total > 0 || excluded > 0`.
   *
   * 왜 `total`만으로는 안 되는가: 마지막 게임을 등록 해제하면 `total`은 0이 되는데 감지 제외
   *   목록은 남는다. `total>0`만 조건이면 그 목록을 지울 방법이 화면에서 사라진다 —
   *   초기화가 제외 목록도 지운다는 사실이 도달 불가가 된다.
   * 수는 봉투가 준 값이다(`counts.excluded`) — 프론트가 다시 세지 않는다.
   * 조회 실패(=counts 없음)일 때는 활성 유지다: ⓐ 일시 원인이 섞여 있어 원천 차단은 과잉이고
   *   ⓑ 눌러도 오발동이 없다 — 백엔드가 토큰+challenge로 fail-closed이고, registry가 실제로
   *   손상됐다면 `reset_all`이 첫 줄의 `load_registry()`에서 같은 코드로 거부해 토큰 발급
   *   자체가 안 된다(정확한 사유가 note로 뜨는 정직한 실패).
   *   즉 이것은 손상 복구의 탈출구가 아니다. 로딩 중(아직 아무것도 모름)만 비활성이다.
   */
  const loading = data === null && !noteText;
  const resetEnabled = counts ? counts.total > 0 || counts.excluded > 0 : !loading;

  return (
    <GfxPopup title={t("SETTINGS_TITLE")} icon={<IconGear />} where="popup-s" closeModal={closeModal}>
      {renderBody(
        <div style={COLUMN_STYLE}>
          {noteView}

          {/* ── 프로필 표시 이름 ─────────────────────────────────────────────
              바꾸는 것은 화면 글자뿐이다. 저장된 프로필·백업·경로는 그대로 있고,
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
                      {/* 봉투의 빈 문자열이 곧 "기본 이름"이다 — 화면이 다시 판정하지 않는다.
                          출처는 라벨과 같은 저장소(setProfileNames 합류점): 이름 변경 직후
                          reload가 실패해도 배지가 낡은 overview를 읽고 성공 문구를 부정하지
                          않는다. */}
                      {hasProfileNameOverride(profile) ? t("MANAGE_NAME_CUSTOM") : t("MANAGE_NAME_DEFAULT")}
                    </div>
                  </div>
                  <PopupButton
                    disabled={busy}
                    onClick={() => askRename(profile)}
                    style={{ minWidth: "140px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto" }}
                  >
                    {t("MANAGE_NAME_EDIT")}
                  </PopupButton>
                </Focusable>
              ))}
            </Focusable>
          </div>

          {/* ── 전체 초기화 ──────────────────────────────────────────────────
              구획선으로만 가른다(빨간 구획·"위험 구역" 명칭 없음). */}
          <div style={SECTION_STYLE}>
            <div style={SECTION_TITLE_STYLE}>{t("SETTINGS_RESET_TITLE")}</div>
            <div style={{ fontSize: "13px", marginBottom: "8px" }}>
              {/* 수를 모르면 모른다고 말한다 — 0으로 그리면 화면이 거짓을 말한다.
                  그래서 파괴 범위와 수를 두 줄로 가른다. 수를 문장 한가운데 슬롯에 끼우면
                    수를 모를 때 그 자리에 "확인 불가" 같은 조각이 들어가 문장이 깨진다.
                    첫 줄이 파괴 범위만 말하면 세 상태에서 문장이 같고, 갈리는 것은 둘째
                    줄뿐이다 — 바로 아래 파괴 버튼이 상태에 따라 움직일 여지를 그만큼 줄인다.
                  둘째 줄은 3상태다: 수치 · 확인 중 · 확인 불가. 로딩(아직 아무것도 모름)과
                    조회 실패(알 수 없음)를 한 문장으로 접으면 실패가 "곧 나오는 중"으로
                    읽힌다 — 가르는 것은 위 `loading`이다(버튼 활성 조건과 같은 값). */}
              <div>{t("RESET_ZONE_BODY")}</div>
              <div>
                {counts
                  ? t("RESET_ZONE_COUNT", { n: counts.total })
                  : loading
                    ? t("RESET_ZONE_LOADING")
                    : t("RESET_ZONE_UNKNOWN")}
              </div>
            </div>
            <Focusable>
              {/* 설명 줄(RESET_HINT)을 아래 거느리는 세로 스택 버튼이다. */}
              <PopupButton
                disabled={busy || !resetEnabled}
                onClick={() => { void runReset(); }}
                style={{ minWidth: "220px", padding: "6px 10px", ...STACKED_BUTTON_STYLE }}
              >
                <span style={ICON_SLOT_STYLE}><IconTrash /></span>
                {t("RESET_OPEN")}
              </PopupButton>
            </Focusable>
            {/* 들여쓰기는 이 줄에만 준다 — `HINT_STYLE`은 위 이름 바꾸기 줄(가로 행)도
                쓰는데, 거기까지 밀면 세로 스택이 아닌 자리의 축이 어긋난다. */}
            <div style={{ ...HINT_STYLE, paddingLeft: STACKED_DESC_PAD }}>{t("RESET_HINT")}</div>
          </div>
        </div>,
      )}
    </GfxPopup>
  );
}
