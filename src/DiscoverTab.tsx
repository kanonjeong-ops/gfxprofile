import { useCallback, useEffect, useState } from "react";
import { ConfirmModal, DialogButton, Focusable, ToggleField, showModal } from "./deckyui";
import { pickConfigFile } from "./filepicker";
import { t, tCode } from "./i18n";
import {
  addGame, discoverGames, registerConfident,
  type AddGameConfirmParams, type DiscoverCandidate, type DiscoverCounts, type DiscoverEntry,
} from "./rpc";

/**
 * 전체 화면 「게임 추가」 탭 (P6) — 미등록 게임을 **타이핑 0회**로 등록한다.
 *
 * ★ 왜 타이핑이 없는가: Game Mode에서는 온스크린 키보드가 자동으로 뜨지 않는다(Valve 버그).
 *   appid나 경로를 손으로 입력하게 만들면 이 화면은 Game Mode에서 사실상 못 쓴다.
 *   그래서 입력 요소를 **하나도 두지 않는다** — 목록에서 고르거나 파일 선택기로 고른다.
 *
 * ★ 왜 새 route가 아니라 탭인가: `addRoute`/`removeRoute` 짝이 하나로 유지되고,
 *   `StatusPage`의 `langReady` 게이트를 그대로 물려받는다. 새 화면을 만들면 언어 확정을
 *   또 직접 해야 하고(`ensureLang` 3번째 호출), 얻는 것이 없다.
 *
 * ★ 500게임 규모 대응 장치는 **둘**이다(설계 §9-E, 외부 검증 반증 3·4로 재수정된 조항):
 *   ① 「등록된 게임 숨기기」 토글 — 이미 등록한 것을 다시 안 보여준다
 *   ② **확신 후보 일괄 등록** — ①만으로는 "전부 미등록"인 최악을 못 줄인다
 *   잔여(애매한 것)는 원리상 더 줄일 수단이 없다 — 사람이 봐야 하는 항목이고,
 *   잘못 자동화하면 G14가 막으려는 바로 그 사고가 난다.
 */

function tierKey(tier: number) {
  return tier === 1 ? "DISCOVER_TIER1" : tier === 2 ? "DISCOVER_TIER2" : "DISCOVER_TIER3";
}

const META_STYLE = { fontSize: "11px", color: "#9aa0a6" } as const;

/**
 * 수동으로 고른 파일에서 appid를 읽는다 — **타이핑 0회를 지키면서** 자동 스캔이 놓친
 * **Proton 게임**을 등록하는 방법이다.
 *
 * ⚠️ **네이티브 리눅스 게임은 이 경로로도 등록되지 않는다**(2026-08-07 마일스톤 R4).
 *   appid를 prefix 경로에서 읽으므로 prefix 밖 파일은 어느 게임의 것인지 알 방법이 없고,
 *   설령 알아도 G11(`check_path`)이 prefix 밖을 거부한다. 네이티브 지원은 **범위 밖**으로
 *   확정된 항목이다 — 그러니 **화면 문구가 그것을 약속하지 않아야 한다**(`DISCOVER_NONE_FOUND`).
 *
 * ★ 이것은 **가드가 아니라 식별자 추출**이다. 잘못 읽어도 경계는 그대로다 —
 *   백엔드 `check_path`(G11)가 *"그 appid의 prefix 아래인가"*를 다시 보고 거부한다.
 *   문은 여전히 엔진 하나다.
 */
const COMPAT_APPID = /\/steamapps\/compatdata\/(\d+)\/pfx\//;

function CandidateLine({ cand }: { cand: DiscoverCandidate }) {
  return (
    <div style={META_STYLE}>
      {t(tierKey(cand.tier))}
      {" · "}
      {t("DISCOVER_CANDIDATE_META", { size: cand.size, date: cand.mtime_label })}
    </div>
  );
}

export function DiscoverTab() {
  const [entries, setEntries] = useState<DiscoverEntry[] | null>(null);
  const [counts, setCounts] = useState<DiscoverCounts | null>(null);
  // 탐지 0건일 때 파일 선택기를 어디서 열지 — 백엔드가 준 실재 경로다(프론트가 지어내지 않는다).
  const [libraries, setLibraries] = useState<string[]>([]);
  // ★ 기본값은 **숨김**이다(설계: registered 기본 필터). 이 화면에 오는 이유는
  //   "아직 등록 안 한 것"을 찾기 위해서다.
  const [hideRegistered, setHideRegistered] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    setBusy(true);
    discoverGames()
      .then(
        (res) => {
          if (res.ok) {
            setEntries(res.data.entries);
            setCounts(res.data.counts);
            setLibraries(res.data.libraries ?? []);
          } else {
            setNote(tCode(res.code, "LOAD_FAILED"));
          }
        },
        () => setNote(tCode("UNEXPECTED", "LOAD_FAILED")),
      )
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * 등록 — 후보 1탭 등록·후보 선택·파일 선택기가 **같은 함수**를 쓴다.
   *
   * ★★ **2단계 계약**이다 (2026-08-07 QA R1). 경고가 나오는 파일은 첫 호출에서 **저장되지 않고**
   *   `CONFIRM_REQUIRED`가 온다 — 그때 확인창을 띄우고, 사용자가 확정하면 **받은 토큰을 그대로
   *   되돌려** 재호출한다. 취소하면 아무 일도 없다(registry는 1바이트도 안 바뀐 상태다).
   *   이전 구현은 백엔드가 먼저 저장하고 화면이 그 뒤에 되물었다 — 확인창이 통보였다.
   *
   * ⚠️ 어느 경로에서 확인창이 뜨는지는 **백엔드가 정한다.** 프론트가 `manual` 여부로 고르던
   *   방식을 버렸다: 판정이 두 곳에 있으면 언젠가 어긋나고, 그때 무방비가 되는 쪽은 프론트다.
   *   자동 후보는 구조적으로 경고가 없어 어차피 모달이 뜨지 않는다.
   */
  const register = useCallback(
    (appid: string, path: string, name?: string, token?: string) => {
      setBusy(true);
      return addGame(appid, path, name, token)
        .then(
          (res) => {
            if (!res.ok) {
              // ⚠️ CONFIRM_REQUIRED는 **실패가 아니라 흐름 신호**다 — 오류 문구로 그리지 않는다.
              if (res.code === "CONFIRM_REQUIRED") {
                confirmModal(res.params as unknown as AddGameConfirmParams, appid, path, name);
                return;
              }
              // `.sav`를 골라도 여기로 온다 — 등록되지 않고 **이유가 화면에 뜬다**(P6 완료 기준).
              // 이미 등록된 게임(ALREADY_REGISTERED)도 같은 자리다.
              setNote(tCode(res.code, "DISCOVER_ADD_FAILED"));
              return;
            }
            // 이름은 **백엔드가 확정한 값**을 쓴다. 수동 등록에는 프론트가 아는 이름이 없다.
            setNote(t("DISCOVER_ADDED", { name: res.data.name }));
            load();
          },
          () => setNote(tCode("UNEXPECTED", "DISCOVER_ADD_FAILED")),
        )
        .finally(() => setBusy(false));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [load],
  );

  /** 파일 선택기 경로. **취소는 조용히 끝난다**(`pickConfigFile`이 null을 돌려준다). */
  const pick = useCallback(
    (entry: DiscoverEntry) => {
      // 시작 위치는 그 게임의 prefix. 사용자가 어디서부터 뒤져야 하는지 몰라도 되게 한다.
      const start = `${entry.library}/steamapps/compatdata/${entry.appid}/pfx`;
      return pickConfigFile(start).then((path) => {
        if (!path) return;                       // 취소 — 오류가 아니다. 아무 것도 하지 않는다.
        return register(entry.appid, path, entry.name);
      });
    },
    [register],
  );

  /**
   * 탐지가 **아무것도 못 찾았을 때**의 수동 등록 (2026-08-07 QA R5).
   *
   * ★ 0건 안내가 「파일 직접 고르기」를 권하는데 그 버튼이 화면에 없던 것이 반려 사유다.
   *   존재하지 않는 조작을 권하는 문장은 오정보다 — 문구를 지우는 대신 **조작을 만들었다.**
   *   자동 스캔이 놓친 **Proton 게임**(비표준 경로에 설정을 두는 것)을 손으로 고르는 것이
   *   이 상황의 정답이다. ⚠️ 네이티브 리눅스 게임은 여기 해당하지 않는다 — 마일스톤 R4.
   *
   * ★ appid는 고른 경로에서 읽는다. 못 읽으면 등록하지 않고 이유를 말한다 —
   *   `compatdata` 밖 파일은 어차피 G11이 거부하므로, 그 전에 사람 말로 알려주는 편이 낫다.
   */
  const pickManual = useCallback(() => {
    const root = libraries[0];
    const start = root ? `${root}/steamapps/compatdata` : "/";
    return pickConfigFile(start).then((path) => {
      if (!path) return;                         // 취소 — 조용히 끝난다.
      const found = COMPAT_APPID.exec(path);
      if (!found) {
        setNote(t("DISCOVER_MANUAL_NO_APPID"));
        return;
      }
      // 이름은 넘기지 않는다 — 아는 이름이 없다. 엔진이 appid로 채우고, 화면은 그 값을 보여준다.
      return register(found[1], path);
    });
  }, [libraries, register]);

  /**
   * **등록 전** 재확인 — 백엔드가 `CONFIRM_REQUIRED`를 낼 때만 뜬다.
   *
   * ⚠️ 경고는 거부가 아니지만, 이 시점에 **등록은 아직 되지 않았다.** 확인해야 저장되고,
   *   취소하면 아무 일도 일어나지 않는다. (예전 문구는 *"등록은 되었지만"*이었다 — 그때는
   *   실제로 그랬고, 그것이 QA R1이 반려한 바로 그 동작이다.)
   */
  function confirmModal(p: AddGameConfirmParams, appid: string, path: string, name?: string) {
    try {
      showModal(
        <ConfirmModal
          strTitle={t("DISCOVER_WARN_TITLE", { name: p.name })}
          strDescription={
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div>{t("DISCOVER_WARN_BODY")}</div>
              {p.warnings.map((code) => (
                <div key={code} style={{ color: "#ffb454" }}>{tCode(code, "UNEXPECTED")}</div>
              ))}
            </div>
          }
          strOKButtonText={t("DISCOVER_WARN_KEEP")}
          strCancelButtonText={t("CANCEL")}
          /* 받은 토큰을 **그대로** 되돌린다. 지어낼 수 없고, 고쳐 봐야 거부된다. */
          onOK={() => { void register(appid, path, name, p.confirm_token); }}
        />,
      );
    } catch (err) {
      // 확인창이 못 뜬 것이고, 그래서 **등록도 되지 않았다.** 둘을 섞어 말하지 않는다.
      console.error("[gfxprofile] discover confirm modal failed", err);
      setNote(t("DISCOVER_WARN_MODAL_FAILED"));
    }
  }

  const runBulk = useCallback(() => {
    setBusy(true);
    registerConfident()
      .then(
        (res) => {
          if (!res.ok) {
            setNote(tCode(res.code, "DISCOVER_ADD_FAILED"));
            return;
          }
          const added = res.data.counts.added ?? 0;
          setNote(t("DISCOVER_BULK_DONE", { added, failed: res.data.results.length - added }));
          load();
        },
        () => setNote(tCode("UNEXPECTED", "DISCOVER_ADD_FAILED")),
      )
      .finally(() => setBusy(false));
  }, [load]);

  const all = entries ?? [];
  // 미등록 우선 → 확신 우선 → 이름순. 지금 할 일이 위로 온다.
  const sorted = [...all].sort(
    (a, b) =>
      Number(a.registered) - Number(b.registered) ||
      Number(b.confident) - Number(a.confident) ||
      a.name.localeCompare(b.name),
  );
  const shown = hideRegistered ? sorted.filter((e) => !e.registered) : sorted;
  const confidentN = counts?.confident_unregistered ?? 0;

  return (
    <div>
      <div style={{ fontSize: "13px", color: "#9aa0a6", margin: "4px 0 10px" }}>
        {counts === null
          ? busy
            ? t("DISCOVER_SCANNING")
            : ""
          : t("DISCOVER_SUMMARY", { total: counts.total, unregistered: counts.unregistered })}
      </div>

      <Focusable style={{ display: "flex", gap: "8px", marginBottom: "6px" }}>
        {/* ★ 일괄 등록 — 500게임 규모(전부 미등록인 최악)를 실제로 줄이는 유일한 장치.
            대상이 0개면 아예 그리지 않는다: 눌러도 아무 일이 없는 버튼은 라벨이 거짓말을 한다. */}
        {confidentN > 0 ? (
          <DialogButton disabled={busy} onClick={runBulk} style={{ minWidth: "220px" }}>
            {t("DISCOVER_ADD_CONFIDENT", { n: confidentN })}
          </DialogButton>
        ) : null}
        <DialogButton disabled={busy} onClick={load} style={{ minWidth: "120px" }}>
          {t("DISCOVER_RESCAN")}
        </DialogButton>
      </Focusable>

      <Focusable>
        <ToggleField
          label={t("FILTER_HIDE_REGISTERED")}
          checked={hideRegistered}
          onChange={setHideRegistered}
        />
      </Focusable>

      {note ? <div style={{ ...META_STYLE, fontSize: "12px", margin: "8px 0" }}>{note}</div> : null}

      <Focusable style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "8px" }}>
        {shown.map((entry) => {
          const open = expanded === entry.appid;
          const chosen = picked[entry.appid];
          return (
            <Focusable
              key={entry.appid}
              style={{
                display: "flex", flexDirection: "column", gap: "4px", padding: "6px 10px",
                borderLeft: entry.registered ? "3px solid transparent" : "3px solid #ffb454",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                  <div style={{ fontSize: "15px", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {entry.name}
                  </div>
                  <div style={META_STYLE}>
                    {entry.registered
                      ? t("DISCOVER_BADGE_REGISTERED")
                      : entry.confident
                        ? t("DISCOVER_BADGE_CONFIDENT")
                        : t("DISCOVER_BADGE_AMBIGUOUS", { n: entry.candidate_count })}
                  </div>
                </div>

                {/* 등록된 게임에는 버튼을 두지 않는다 — `add_game`은 확인 없이 경로를 덮어쓰므로,
                    화면에서 그 경로를 아예 만들지 않는 것이 가드보다 확실하다. */}
                {entry.registered ? null : (
                  <div style={{ display: "flex", gap: "4px", flex: "0 0 auto" }}>
                    {entry.confident && entry.best ? (
                      /* ★ 확신 단일 매치는 **모달 없이 1탭**이다(설계). 후보가 하나뿐이라
                         펼쳐 봐야 고를 것이 없고, 경고도 구조적으로 발생하지 않는다. */
                      <DialogButton
                        disabled={busy}
                        onClick={() => register(entry.appid, entry.best!.path, entry.name)}
                        style={{ minWidth: "88px", padding: "6px 8px", fontSize: "13px" }}
                      >
                        {t("DISCOVER_ADD")}
                      </DialogButton>
                    ) : (
                      <DialogButton
                        disabled={busy}
                        onClick={() => setExpanded(open ? null : entry.appid)}
                        style={{ minWidth: "88px", padding: "6px 8px", fontSize: "13px" }}
                      >
                        {t(open ? "DISCOVER_HIDE_CANDIDATES" : "DISCOVER_SHOW_CANDIDATES")}
                      </DialogButton>
                    )}
                    <DialogButton
                      disabled={busy}
                      onClick={() => void pick(entry)}
                      style={{ minWidth: "120px", padding: "6px 8px", fontSize: "13px" }}
                    >
                      {t("DISCOVER_PICK_FILE")}
                    </DialogButton>
                  </div>
                )}
              </div>

              {/* 애매한 게임의 후보를 **화면 안에서** 펼친다(모달이 아니다).
                  후보를 골라도 바로 등록되지 않는다 — 포커스 이동만으로 등록되면 안 된다. */}
              {open && !entry.registered
                ? entry.candidates.map((cand) => (
                    <Focusable
                      key={cand.path}
                      style={{ display: "flex", alignItems: "center", gap: "8px", paddingLeft: "12px" }}
                    >
                      <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                        <div style={{ fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {cand.path}
                        </div>
                        <CandidateLine cand={cand} />
                      </div>
                      <DialogButton
                        disabled={busy}
                        onClick={() => setPicked((p) => ({ ...p, [entry.appid]: cand.path }))}
                        style={{ minWidth: "76px", padding: "4px 8px", fontSize: "12px" }}
                      >
                        {t(chosen === cand.path ? "DISCOVER_CHOSEN" : "DISCOVER_CHOOSE")}
                      </DialogButton>
                    </Focusable>
                  ))
                : null}

              {open && chosen && !entry.registered ? (
                <Focusable style={{ paddingLeft: "12px" }}>
                  <DialogButton
                    disabled={busy}
                    onClick={() => register(entry.appid, chosen, entry.name)}
                    style={{ minWidth: "120px", padding: "6px 8px", fontSize: "13px" }}
                  >
                    {t("DISCOVER_ADD")}
                  </DialogButton>
                </Focusable>
              ) : null}
            </Focusable>
          );
        })}
      </Focusable>

      {/* ★ 0건 안내 — *"게임이 없다"*고 단언하지 않는다.
          `discover()`는 `compatdata/<appid>/pfx` 구조에 묶여 있어 **네이티브 리눅스 게임은
          스캔 대상 자체가 아니다**(tier 판정 이전에 배제된다). 그 한계를 화면이 말하지 않으면
          사용자는 "설치한 게임이 없다"로 읽는다 — 그건 오정보다(결정 8-a).
          `discover.py`가 diff fence의 바이트 동일 대상이라 코드 주석으로는 말할 수 없고,
          **이 문구가 그 역할을 대신 짊어진다.** */}
      {entries === null ? (
        note ? null : <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>{t("LOADING")}</div>
      ) : shown.length === 0 ? (
        <div style={{ fontSize: "13px", color: "#9aa0a6", marginTop: "12px" }}>
          {t(all.length === 0 ? "DISCOVER_NONE_FOUND" : "DISCOVER_NONE_UNREGISTERED")}
        </div>
      ) : null}

      {/* ★★ 수동 등록은 **1급 경로다** — 목록 상태와 무관하게 탭 하단에 상주한다
          (2026-08-07 빅픽처 실기, QA R5-b).

          ⚠️ 처음엔 이 버튼을 0건 분기(`all.length === 0`) **안**에 뒀다. 그랬더니 이 기기 실측
            (탐지 10 / 등록 10)에서 화면에는 「전부 이미 등록돼 있습니다」만 뜨고 **진입점이
            어디에도 없었다.** 탐지가 하나라도 성공한 기기에서는 수동 선택기가 사실상 소멸한다 —
            그런데 그것이 자동 스캔이 놓친 **Proton 게임**을 등록할 유일한 길이다
            (네이티브 리눅스 게임은 prefix 밖이라 이 경로로도 등록되지 않는다 — 마일스톤 R4).
            안내 문구가 가리키는 조작이 있는지만 보면 이 결함이 안 보인다: 그 상태의 문구는
            버튼을 권하지 않아 «문구↔버튼»은 정합인데도 기능이 도달 불가였다.
          → 조건을 없앤다. 조건이 없으면 어긋날 조건도 없다. */}
      {entries === null ? null : (
        <Focusable style={{ marginTop: "14px" }}>
          <DialogButton disabled={busy} onClick={() => void pickManual()} style={{ minWidth: "180px" }}>
            {t("DISCOVER_PICK_FILE")}
          </DialogButton>
        </Focusable>
      )}
    </div>
  );
}
