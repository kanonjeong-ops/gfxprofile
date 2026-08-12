import { useCallback, useState } from "react";
import { makeDiscoverWarnSpec } from "./confirmSpecs";
import { DialogButton, Focusable, ToggleField } from "./deckyui";
import { pickConfigFile } from "./filepicker";
import { IconRefresh, IconRestore, IconSearch } from "./icons";
import { t, tCode } from "./i18n";
import {
  CARD_INNER_STYLE, CARD_STYLE, GfxPopup, PopupScrollList, PopupSubView,
  listRowNavProps, subViewKey, usePopupData, usePopupGate, type DView,
} from "./popup";
import {
  addGame, discoverGames, includeGame, registerConfident,
  type AddGameConfirmParams, type DiscoverCandidate, type DiscoverData, type DiscoverEntry,
  type ExcludedRow,
} from "./rpc";

/**
 * **팝업 D — 게임 감지** (설계 §6). 사라진 「게임 추가」 탭이 하던 일을 팝업으로 옮긴 것이다.
 *
 * ★★ **타이핑이 하나도 없다**(P6부터의 불변식): Game Mode에서는 온스크린 키보드가 자동으로
 *   뜨지 않는다. appid나 경로를 손으로 치게 만들면 이 화면은 핸드헬드에서 못 쓴다 —
 *   그래서 **입력 요소를 하나도 두지 않는다.** 목록에서 고르거나 파일 선택기로 고른다.
 *
 * ★★ **현행 기능은 전량 보존한다**(§6-A Codex S-01): 확신 단일매치 1탭 등록 · 행별
 *   [파일 직접 고르기] · 애매 행의 [후보 보기/접기] · 하단 상주 [파일 직접 고르기] ·
 *   2단계 토큰 계약 · 0건 장문 안내 · 수동 등록 오류 안내. 재편은 **배치와 선택 흐름**만
 *   바꾼다(GP#7 액션 줄 순서 · GP#8 제외 진입 위치 · GP#10 선택 즉시 등록 전환).
 *
 * ★ 500게임 규모 대응 장치는 **둘**이다: ① 「등록된 게임 숨기기」(기본 ON) ② 확신 후보 일괄
 *   등록. 잔여(애매한 것)는 사람이 봐야 하는 항목이라 원리상 더 줄일 수단이 없다.
 *
 * ★ P15-C에서 QAM 진입 버튼에 배선됐다. 그 전에도 tsc·i18n 집합 검사·프로브는 돌고
 *   있었다 — 배선이 없다고 검사까지 미루면 배선하는 날 한꺼번에 터지기 때문이다.
 */

const COLUMN_STYLE = { display: "flex", flexDirection: "column", gap: "10px" } as const;
const META_STYLE = { fontSize: "11px", color: "#9aa0a6" } as const;
const HINT_STYLE = { fontSize: "12px", color: "#9aa0a6" } as const;
const DESC_STYLE = { fontSize: "11px", color: "#9aa0a6", margin: "2px 0 6px" } as const;
const SUMMARY_ROW_STYLE = {
  display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "8px", fontSize: "13px",
} as const;
const TITLE_STYLE = { fontSize: "16px", fontWeight: "bold" } as const;
const ROW_STYLE = { display: "flex", alignItems: "center", gap: "8px" } as const;
const NAME_STYLE = {
  flex: "1 1 auto", minWidth: 0, fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis",
} as const;

/** 아이콘 자리 — 고정 폭이라 아이콘 유무로 버튼 폭이 흔들리지 않는다(GP#2). */
const ICON_SLOT_STYLE = {
  display: "inline-flex", width: "1em", justifyContent: "center", marginRight: "4px",
} as const;

const ACTION_ROW_STYLE = { display: "flex", flexWrap: "wrap", gap: "8px" } as const;
const RESCAN_BUTTON_STYLE = { minWidth: "140px", padding: "6px 10px", fontSize: "13px" } as const;
const BULK_BUTTON_STYLE = { minWidth: "260px", padding: "6px 10px", fontSize: "13px" } as const;
const EXCLUDED_BUTTON_STYLE = { minWidth: "200px", padding: "6px 10px", fontSize: "13px" } as const;
const PICK_BUTTON_STYLE = { minWidth: "180px", padding: "6px 10px", fontSize: "13px" } as const;
const INCLUDE_BUTTON_STYLE = {
  minWidth: "120px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto",
} as const;

/** 행 버튼 2종은 **폭이 고정**이다 — 행마다 x좌표가 같아야 수직 이동 중 커서가 안 튄다(GP#2). */
const ROW_ACTION_STYLE = {
  minWidth: "96px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto",
} as const;
const ROW_PICK_STYLE = {
  minWidth: "140px", padding: "6px 8px", fontSize: "13px", flex: "0 0 auto",
} as const;

/**
 * 후보 행의 버튼 — [선택]과 [이 파일로 추가]가 **같은 자리·같은 폭**이다(GP#10).
 * 라벨 길이로 폭이 바뀌면 전환이 "버튼이 움직인 것"으로 보인다.
 */
const CANDIDATE_BUTTON_STYLE = {
  minWidth: "150px", padding: "4px 8px", fontSize: "12px", flex: "0 0 auto",
} as const;
const CANDIDATE_ROW_STYLE = {
  display: "flex", alignItems: "center", gap: "8px", paddingLeft: "12px",
} as const;
/** 파일명은 굵게, 경로는 죽여서 — 사람이 고르는 단서는 **파일명**이다(M4). */
const CANDIDATE_FILE_STYLE = {
  fontSize: "13px", fontWeight: "bold", overflow: "hidden", textOverflow: "ellipsis",
} as const;
const CANDIDATE_PATH_STYLE = {
  fontSize: "11px", color: "#9aa0a6", overflow: "hidden", textOverflow: "ellipsis",
} as const;

function tierKey(tier: number) {
  return tier === 1 ? "DISCOVER_TIER1" : tier === 2 ? "DISCOVER_TIER2" : "DISCOVER_TIER3";
}

/**
 * 수동으로 고른 파일에서 appid를 읽는다 — **타이핑 0회를 지키면서** 자동 스캔이 놓친
 * **Proton 게임**을 등록하는 방법이다.
 *
 * ⚠️ **네이티브 리눅스 게임은 이 경로로도 등록되지 않는다**(마일스톤 R4). appid를 prefix
 *   경로에서 읽으므로 prefix 밖 파일은 어느 게임의 것인지 알 방법이 없고, 설령 알아도
 *   `check_path`(G11)가 prefix 밖을 거부한다.
 *
 * ★ 이것은 **가드가 아니라 식별자 추출**이다 — 잘못 읽어도 경계는 그대로다(문은 엔진 하나).
 */
const COMPAT_APPID = /\/steamapps\/compatdata\/(\d+)\/pfx\//;

/** 경로에서 마지막 조각(파일명). 구분자가 없으면 전체가 파일명이다. */
function fileNameOf(path: string): string {
  const cut = path.lastIndexOf("/");
  return cut < 0 ? path : path.slice(cut + 1);
}

/** 축약할 때 남기는 뒤쪽 조각 수 — 게임을 가르는 정보는 대개 끝에 있다. */
const PATH_TAIL_SEGMENTS = 3;

/**
 * 경로를 **뒤에서부터** 줄인다(M4) — prefix 경로는 앞이 길고 앞쪽은 전부 같다.
 * 프론트가 경로를 **가공해 넘기는 일은 없다** — 이 값은 화면에만 쓰고, 등록에는 원본을 쓴다.
 */
function shortDir(path: string): string {
  const cut = path.lastIndexOf("/");
  if (cut < 0) return "";
  const parts = path.slice(0, cut).split("/").filter((seg) => seg.length > 0);
  if (parts.length <= PATH_TAIL_SEGMENTS) return path.slice(0, cut);
  return `…/${parts.slice(-PATH_TAIL_SEGMENTS).join("/")}`;
}

function CandidateMeta({ cand }: { cand: DiscoverCandidate }) {
  return (
    <div style={META_STYLE}>
      {t(tierKey(cand.tier))}
      {" · "}
      {t("DISCOVER_CANDIDATE_META", { size: cand.size, date: cand.mtime_label })}
    </div>
  );
}

/** 배지 — 상태를 **말로** 그린다. 주황 테두리는 없다(§6-A: 미등록은 정상 상태다). */
function badgeText(entry: DiscoverEntry): string {
  if (entry.registered) return t("DISCOVER_BADGE_REGISTERED");
  if (entry.confident) return t("DISCOVER_BADGE_CONFIDENT");
  return t("DISCOVER_BADGE_AMBIGUOUS", { n: entry.candidate_count });
}

/**
 * 후보 카드 하나(§6-A 6항).
 *
 * ★ 미등록 행의 버튼 구성은 **현행 그대로**다(S-01): 확신이면 `[추가]`(1탭) · 애매하면
 *   `[후보 보기/접기]`, 그리고 **어느 쪽이든** 행별 `[파일 직접 고르기]`. 행별 선택기는
 *   탐지 후보가 전부 틀렸을 때의 게임별 탈출구라 제거하지 않는다.
 * ★ 등록된 게임에는 버튼을 두지 않는다 — `add_game`은 이미 등록된 appid를 거부하고,
 *   화면에서 그 경로를 아예 만들지 않는 것이 가드보다 확실하다.
 */
function EntryCard({
  entry,
  busy,
  focused,
  open,
  chosen,
  onAdd,
  onToggleCandidates,
  onPick,
  onChoose,
}: {
  entry: DiscoverEntry;
  busy: boolean;
  /** 이 행에 착지시킬 것인가(§4-E ① — 팝업 D의 초기 포커스는 첫 후보 카드다). */
  focused: boolean;
  open: boolean;
  /** 이 게임에서 지금 고른 후보 경로. 없으면 빈 문자열. */
  chosen: string;
  onAdd: (entry: DiscoverEntry, path: string) => void;
  onToggleCandidates: (entry: DiscoverEntry) => void;
  onPick: (entry: DiscoverEntry) => void;
  onChoose: (entry: DiscoverEntry, path: string) => void;
}) {
  return (
    <Focusable {...listRowNavProps} preferredFocus={focused} style={CARD_STYLE}>
      <div style={CARD_INNER_STYLE}>
        <div style={ROW_STYLE}>
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <div style={NAME_STYLE}>{entry.name}</div>
            <div style={META_STYLE}>{badgeText(entry)}</div>
          </div>
          {entry.registered ? null : (
            <div style={{ display: "flex", gap: "4px", flex: "0 0 auto" }}>
              {entry.confident && entry.best ? (
                /* ★ 확신 단일 매치는 **모달 없이 1탭**이다(현행 유지): 후보가 하나뿐이라
                   펼쳐 봐야 고를 것이 없고, 경고도 구조적으로 발생하지 않는다. */
                <DialogButton
                  disabled={busy}
                  onClick={() => onAdd(entry, entry.best ? entry.best.path : "")}
                  style={ROW_ACTION_STYLE}
                >
                  {t("DISCOVER_ADD")}
                </DialogButton>
              ) : (
                <DialogButton
                  disabled={busy}
                  onClick={() => onToggleCandidates(entry)}
                  style={ROW_ACTION_STYLE}
                >
                  {t(open ? "DISCOVER_HIDE_CANDIDATES" : "DISCOVER_SHOW_CANDIDATES")}
                </DialogButton>
              )}
              <DialogButton disabled={busy} onClick={() => onPick(entry)} style={ROW_PICK_STYLE}>
                {t("DISCOVER_PICK_FILE")}
              </DialogButton>
            </div>
          )}
        </div>

        {/* 애매한 게임의 후보를 **화면 안에서** 펼친다(모달이 아니다).
            ★ GP#10 — 선택 즉시 등록 전환: 후보 버튼이 `[선택]`에서 **같은 자리** `[이 파일로
              추가]`로 바뀌고 두 번째 A로 등록된다. 목록 끝의 별도 [추가] 버튼은 없앴다 —
              "포커스 이동만으로 등록되지 않는다"(두 번의 의도적 누름)는 원칙은 그대로이고,
              이동 낭비만 0이 된다. */}
        {open && !entry.registered
          ? entry.candidates.map((cand) => (
              <Focusable key={cand.path} {...listRowNavProps} style={CANDIDATE_ROW_STYLE}>
                <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                  <div style={CANDIDATE_FILE_STYLE}>{fileNameOf(cand.path)}</div>
                  <div style={CANDIDATE_PATH_STYLE}>{shortDir(cand.path)}</div>
                  <CandidateMeta cand={cand} />
                </div>
                <DialogButton
                  disabled={busy}
                  onClick={() => {
                    if (chosen === cand.path) onAdd(entry, cand.path);
                    else onChoose(entry, cand.path);
                  }}
                  style={CANDIDATE_BUTTON_STYLE}
                >
                  {t(chosen === cand.path ? "DISCOVER_CANDIDATE_ADD" : "DISCOVER_CHOOSE")}
                </DialogButton>
              </Focusable>
            ))
          : null}
      </div>
    </Focusable>
  );
}

export function DiscoverPopup({
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
  const [view, setView] = useState<DView>({ kind: "main" });
  /** 기본값은 **숨김**이다 — 이 화면에 오는 이유는 "아직 등록 안 한 것"을 찾기 위해서다. */
  const [hideRegistered, setHideRegistered] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});

  const load = useCallback(() => discoverGames(), []);
  /* ★ busy·재조회·변경 통지는 **훅 한 곳**을 지난다(§4-F 개정). */
  const { data, noteText, setNote, noteView, busy, reload, runMutation, runQuery } =
    usePopupData<DiscoverData>(load, "LOAD_FAILED", onMutate);
  const { gate, renderBody } = usePopupGate();

  const entries = data ? data.entries : [];
  const counts = data ? data.counts : null;
  const excluded = data ? data.excluded : [];

  /**
   * 등록 — 후보 1탭 등록·후보 선택·파일 선택기가 **같은 함수**를 쓴다.
   *
   * ★★ **2단계 계약**이다(2026-08-07 QA R1). 경고가 나오는 파일은 첫 호출에서 **저장되지 않고**
   *   `CONFIRM_REQUIRED`가 온다 — 그때 확인창을 띄우고, 확정하면 **받은 토큰을 그대로 되돌려**
   *   재호출한다. 취소하면 registry는 1바이트도 안 바뀐 상태다.
   * ⚠️ 어느 경로에서 확인창이 뜨는지는 **백엔드가 정한다.** 프론트가 `manual` 여부로 고르면
   *   판정이 두 곳에 생기고, 언젠가 어긋나면 무방비가 되는 쪽은 프론트다.
   * ★ 성공 note는 **남은 백업 수로 갈린다**(§9-③): 등록을 해제해도 백업은 남으므로, 다시
   *   등록한 순간 "복원할 것이 있다"를 **그 자리에서** 말해야 한다. 0이면 그 줄이 없다.
   */
  const register = useCallback(
    (appid: string, path: string, name?: string, token?: string) =>
      runMutation(() => addGame(appid, path, name, token), "DISCOVER_ADD_FAILED", (res) => {
        if (!res.ok) {
          // ⚠️ CONFIRM_REQUIRED는 **실패가 아니라 흐름 신호**다 — 오류 문구로 그리지 않는다.
          //   무쓰기가 보장된 유일한 응답이라 재조회도 붙지 않는다(§4-F ③).
          if (res.code === "CONFIRM_REQUIRED") {
            const p = res.params as unknown as AddGameConfirmParams;
            gate(
              makeDiscoverWarnSpec(p, () => { void register(appid, path, name, p.confirm_token); }),
              // 확인창이 못 뜬 것이고, 그래서 **등록도 되지 않았다**(둘을 섞어 말하지 않는다).
              "DISCOVER_WARN_MODAL_FAILED",
              setNote,
            );
            return;
          }
          // `.sav`를 골라도·이미 등록된 게임이어도 여기로 온다 — 등록되지 않고 이유가 뜬다.
          setNote(tCode(res.code, "DISCOVER_ADD_FAILED"));
          return;
        }
        // 이름은 **백엔드가 확정한 값**이다. 수동 등록에는 프론트가 아는 이름이 없다.
        setNote(res.data.backups > 0
          ? t("DISCOVER_ADDED_HAS_BACKUPS", { name: res.data.name, n: res.data.backups })
          : t("DISCOVER_ADDED", { name: res.data.name }));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gate],
  );

  /** 행별 파일 선택기. 시작 위치는 **그 게임의 prefix**다. 취소는 조용히 끝난다. */
  const pick = useCallback(
    (entry: DiscoverEntry) => {
      const start = `${entry.library}/steamapps/compatdata/${entry.appid}/pfx`;
      return pickConfigFile(start).then((path) => {
        if (!path) return;                       // 취소 — 오류가 아니다. 아무 것도 하지 않는다.
        return register(entry.appid, path, entry.name);
      });
    },
    [register],
  );

  /**
   * 하단 상주 선택기(§6-A 7항 · GP#16) — **조건 없이 항상 있다.**
   *
   * ⚠️ 예전에는 이 버튼이 0건 분기 **안**에 있었다. 그랬더니 탐지 10 / 등록 10인 기기에서
   *   화면에는 「전부 이미 등록돼 있습니다」만 뜨고 **진입점이 어디에도 없었다**(2026-08-07 실기).
   *   그런데 그것이 자동 스캔이 놓친 Proton 게임을 등록할 유일한 길이다.
   *   → 조건을 없앤다. 조건이 없으면 어긋날 조건도 없다.
   * ★★ 시작 위치는 **봉투가 준 라이브러리 경로뿐**이다(P15-E R6ⓐ). 예전 코드는 바로 이 줄에
   *   *"프론트가 경로를 지어내지 않는다"*고 적어 두고, 바로 아래에서 조회 전·조회 실패에
   *   `"/"`를 지어냈다 — 파일 시스템 루트는 이 도메인의 시작점이 아니고(게임 prefix는 열 단계
   *   아래다), **주석과 코드가 서로 다른 말을 하는 자리**는 다음 사람이 둘 중 하나를 믿다가
   *   틀린다. 근거가 없으면 지어내는 대신 **그 자리에서 다시 읽는다** — 그 응답이 곧 시작점이다.
   */
  const openManual = useCallback(
    (root: string) =>
      pickConfigFile(`${root}/steamapps/compatdata`).then((path) => {
        if (!path) return;                       // 취소 — 조용히 끝난다.
        const found = COMPAT_APPID.exec(path);
        if (!found) {
          setNote(t("DISCOVER_MANUAL_NO_APPID"));
          return;
        }
        // 이름은 넘기지 않는다 — 아는 이름이 없다. 엔진이 appid로 채우고 화면은 그 값을 쓴다.
        return register(found[1], path);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [register],
  );

  const pickManual = useCallback(
    () => {
      const known = data && data.libraries.length > 0 ? data.libraries[0] : "";
      if (known) return openManual(known);
      // 아직·또는 다시 모르는 상태다. 조회는 **읽기 전용**이라 재조회·통지가 붙지 않는다.
      return runQuery(load, "LOAD_FAILED", (res) => {
        if (!res.ok) {
          setNote(tCode(res.code, "LOAD_FAILED"));
          return;
        }
        const root = res.data.libraries.length > 0 ? res.data.libraries[0] : "";
        // 라이브러리를 못 찾은 것은 **모르는 상태**다 — 아무 데서나 열지 않고 그 사실을 말한다.
        if (!root) {
          setNote(t("DISCOVER_NO_LIBRARY"));
          return;
        }
        void openManual(root);
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, openManual],
  );

  /** 확신 후보 일괄 등록 — 대상 수는 **봉투가 준 값**이고 프론트가 다시 세지 않는다. */
  const runBulk = useCallback(
    () =>
      runMutation(() => registerConfident(), "DISCOVER_ADD_FAILED", (res) => {
        if (!res.ok) {
          setNote(tCode(res.code, "DISCOVER_ADD_FAILED"));
          return;
        }
        const added = res.data.counts.added ?? 0;
        const failed = res.data.results.length - added;
        // 실패가 **없으면 그 절을 그리지 않는다** — "0개는 추가하지 못했습니다"는 아무 일도
        // 없었던 것을 사건처럼 말한다(§7 `RESET_OK`+`RESET_LEFT_NOTE`와 같은 문법).
        const done = t("DISCOVER_BULK_DONE", { added });
        setNote(failed > 0 ? `${done} ${t("DISCOVER_BULK_FAILED_NOTE", { failed })}` : done);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /**
   * 감지 제외 해제 — **한 버튼 한 쓰기**다(§6-B). 재포함은 **등록이 아니다**: 이 호출 뒤
   * 그 게임은 감지 목록에 후보로 다시 뜰 뿐이고, 등록은 사용자가 거기서 한다.
   * 그래서 note가 **다음 경로를 병기**한다(F11·F13) — 안 그러면 "포함했는데 왜 그대로냐"가 된다.
   */
  const runInclude = useCallback(
    // 제외 목록과 후보 목록이 **함께** 바뀐다 — 봉투를 통째로 다시 읽는다(§4-F, 훅이 붙인다).
    (row: ExcludedRow) =>
      runMutation(() => includeGame(row.appid), "DISCOVER_INCLUDE_FAILED", (res) => {
        if (!res.ok) {
          setNote(tCode(res.code, "DISCOVER_INCLUDE_FAILED"));
          return;
        }
        setNote(t("DISCOVER_INCLUDED_NOTE", { name: row.name }));
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // ── 기본 뷰 (§6-A) ─────────────────────────────────────────────────────────
  //
  // 미등록 우선 → 확신 우선 → 이름순. 지금 할 일이 위로 온다.
  const sorted = [...entries].sort(
    (a, b) =>
      Number(a.registered) - Number(b.registered) ||
      Number(b.confident) - Number(a.confident) ||
      a.name.localeCompare(b.name),
  );
  const shown = hideRegistered ? sorted.filter((e) => !e.registered) : sorted;
  const confidentN = counts ? counts.confident_unregistered : 0;
  /** L3 — 숨긴 것이 있으면 **숨겼다고 말한다**("감지가 안 되네"라는 오독을 차단한다). */
  const hiddenN = hideRegistered && counts ? counts.registered : 0;

  /**
   * 요약 줄의 글자 — **한 상태에 한 문장**이다.
   *
   * ⚠️ 「훑는 중」과 「로딩 중」을 두 자리에서 각각 그리면 같은 상태를 두 번 말하고, 조회가
   *   실패했을 때는 그 중 하나가 **영영 「훑는 중」으로 남아** 화면이 거짓을 말한다.
   *   그래서 상태를 여기 한 곳에서 고른다: 값이 있으면 요약 · 없고 사유가 있으면 침묵(note가
   *   말한다) · 둘 다 없으면 훑는 중.
   */
  function summaryText(): string {
    if (counts) {
      return t("DISCOVER_SUMMARY", { total: counts.total, unregistered: counts.unregistered });
    }
    return noteText ? "" : t("DISCOVER_SCANNING");
  }

  function renderTail() {
    // 아직 모르는 것은 **없는 것이 아니다** — 로딩·실패 어느 쪽도 요약 줄과 note가 말한다.
    if (data === null) return null;
    if (shown.length > 0) return null;
    /* ★ 0건 안내는 *"게임이 없다"*고 말하지 않는다. 탐지는 `compatdata/<appid>/pfx` 구조에
       묶여 있어 **네이티브 리눅스 게임은 스캔 대상 자체가 아니다** — 그 한계를 화면이
       말하지 않으면 사용자는 "설치한 게임이 없다"로 읽는다(결정 8-a). */
    return (
      <div style={HINT_STYLE}>
        {t(entries.length === 0 ? "DISCOVER_NONE_FOUND" : "DISCOVER_NONE_UNREGISTERED")}
      </div>
    );
  }

  function renderMain() {
    return (
      <div style={COLUMN_STYLE}>
        <div style={SUMMARY_ROW_STYLE}>
          <div>{summaryText()}</div>
          {hiddenN > 0 ? <div style={META_STYLE}>{t("DISCOVER_HIDDEN_NOTE", { n: hiddenN })}</div> : null}
        </div>

        {/* ★ GP#7 — [다시 검색]이 **먼저**다: 진입 직후의 A 관성이 착지하는 자리가 무해한
            쪽(다시 읽기)이어야 한다. 일괄 등록은 대상이 0이면 아예 그리지 않는다 —
            눌러도 아무 일이 없는 버튼은 라벨이 거짓말을 한다. */}
        <Focusable style={ACTION_ROW_STYLE}>
          <DialogButton disabled={busy} onClick={() => reload()} style={RESCAN_BUTTON_STYLE}>
            <span style={ICON_SLOT_STYLE}><IconRefresh /></span>
            {t("DISCOVER_RESCAN")}
          </DialogButton>
          {confidentN > 0 ? (
            <DialogButton disabled={busy} onClick={() => { void runBulk(); }} style={BULK_BUTTON_STYLE}>
              {t("DISCOVER_ADD_CONFIDENT", { n: confidentN })}
            </DialogButton>
          ) : null}
        </Focusable>

        <Focusable>
          <ToggleField
            label={t("FILTER_HIDE_REGISTERED")}
            checked={hideRegistered}
            onChange={setHideRegistered}
          />
        </Focusable>

        {/* ★ GP#8 — 제외 진입은 **목록 위 전용 행**이다: 하단에 두면 도달 비용이 목록 길이에
            비례해 "존재를 보인다"는 논거가 게임패드에서 성립하지 않는다.
            0건이면 **비활성으로 남긴다**(M6 기각) — 복구 렌즈의 유일한 화면 발견 경로라
            숨기지 않는다. */}
        <Focusable>
          <DialogButton
            disabled={busy || excluded.length === 0}
            onClick={() => setView({ kind: "excluded" })}
            style={EXCLUDED_BUTTON_STYLE}
          >
            {t("DISCOVER_EXCLUDED_OPEN", { n: excluded.length })}
          </DialogButton>
        </Focusable>

        {noteView}

        <PopupScrollList>
          {shown.map((entry, index) => (
            <EntryCard
              key={entry.appid}
              entry={entry}
              busy={busy}
              focused={index === 0}
              open={expanded === entry.appid}
              chosen={picked[entry.appid] ?? ""}
              onAdd={(e, path) => { void register(e.appid, path, e.name); }}
              onToggleCandidates={(e) => setExpanded(expanded === e.appid ? null : e.appid)}
              onPick={(e) => { void pick(e); }}
              onChoose={(e, path) => setPicked((prev) => ({ ...prev, [e.appid]: path }))}
            />
          ))}
        </PopupScrollList>

        {renderTail()}

        <Focusable>
          <DialogButton disabled={busy} onClick={() => { void pickManual(); }} style={PICK_BUTTON_STYLE}>
            {t("DISCOVER_PICK_FILE")}
          </DialogButton>
        </Focusable>
        {/* H5 — 이 버튼이 무엇을 하는 것인지 그 자리에서 말한다(자기 설명). */}
        <div style={DESC_STYLE}>{t("DISCOVER_PICK_FILE_DESC")}</div>
      </div>
    );
  }

  // ── 제외한 게임 뷰 (§6-B) ──────────────────────────────────────────────────
  function renderExcluded() {
    return (
      <div style={COLUMN_STYLE}>
        <div style={TITLE_STYLE}>{t("DISCOVER_EXCLUDED_TITLE")}</div>
        {/* F12·M15 통일 문구 — 「등록 해제」 어휘와 정합이고, 다시 포함하면 무엇이 되는지를
            **조건까지** 말한다(동어반복 "다시 포함하면 제외가 해제됩니다"는 폐기). */}
        <div style={HINT_STYLE}>{t("DISCOVER_EXCLUDED_HINT")}</div>
        {noteView}

        <PopupScrollList>
          {excluded.map((row) => (
            <Focusable key={row.appid} {...listRowNavProps} style={CARD_STYLE}>
              <div style={{ ...CARD_INNER_STYLE, ...ROW_STYLE }}>
                <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                  <div style={NAME_STYLE}>{row.name}</div>
                  {/* 날짜를 모르면 그 줄을 그리지 않는다 — 빈 값을 라벨로 감싸면 화면이 거짓을
                      말한다(백엔드가 만든 표시값을 그대로 쓴다). */}
                  {row.excluded_at_label ? (
                    <div style={META_STYLE}>{t("DISCOVER_EXCLUDED_ROW", { date: row.excluded_at_label })}</div>
                  ) : null}
                </div>
                <DialogButton
                  disabled={busy}
                  onClick={() => { void runInclude(row); }}
                  style={INCLUDE_BUTTON_STYLE}
                >
                  <span style={ICON_SLOT_STYLE}><IconRestore /></span>
                  {t("DISCOVER_INCLUDE")}
                </DialogButton>
              </div>
            </Focusable>
          ))}
        </PopupScrollList>
        {excluded.length === 0 ? <div style={HINT_STYLE}>{t("DISCOVER_EXCLUDED_EMPTY")}</div> : null}
      </div>
    );
  }

  // ── 뷰 선택 ────────────────────────────────────────────────────────────────
  //
  // ⚠️ 분기를 한 줄에 이어 쓰지 않는다 — `A /> : x ? <B` 형태가 되면 `test_i18n_sets`의
  //   JSX 텍스트 정규식이 그 사이의 코드를 화면 글자로 오인해 거짓 FAIL을 낸다.
  function renderView() {
    if (view.kind === "excluded") {
      return (
        <PopupSubView key={subViewKey(view)} onBack={() => setView({ kind: "main" })}>
          {renderExcluded()}
        </PopupSubView>
      );
    }
    return renderMain();
  }

  return (
    <GfxPopup title={t("DISCOVER_TITLE")} icon={<IconSearch />} where="popup-d" closeModal={closeModal}>
      {/* ★ 본문은 **반드시** `renderBody`를 지난다(§4-C D-05 ⑤): 폴백 모드에서 오버레이와
          원 콘텐츠가 동시에 떠 있는 상태를 호출부가 만들 수 없게 하는 장치다. */}
      {renderBody(renderView())}
    </GfxPopup>
  );
}
