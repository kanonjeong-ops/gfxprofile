#!/usr/bin/env python3
"""QAM 재편(설계 §3)을 **렌더+클릭으로** 잠근다 — 명세 §15-B ⑤ + 배선(§3-A·§4-A) + §3-E.

### 무엇을 재는가
QAM은 이 플러그인에서 **매 부팅 열리는 유일한 화면**이고, P15-C부터는 팝업 3종으로 가는
모든 길이 여기 하나뿐이다. 그래서 여기서 깨지면 사용자는 기능 자체에 도달하지 못한다.

1. **상태박스**(§3-B) — 슬롯 8종이 *각자의 조건에서만* 뜨는가 · 현재군/과거군이 갈려 있는가 ·
   결과·실패에 **받은 시각**이 붙는가 · busy 동안 과거군이 흐려지는가 ·
   요약과 실패가 **QAM 재개방을 넘어 승계**되는가(F20) · 새 로드 성공이 실패를 거두는가.
2. **D01** — `counts` 미도착에는 "등록된 게임이 없습니다"를 **말하지 않는다**. 모르는 것을
   0으로 말하면 화면이 거짓을 말한다(카운트 줄·일괄 버튼 hint 양쪽).
3. **H2 조건 공유**(§3-B ④ · §3-D ② · U-5) — 시작 안내와 설명 ②는 **같은 조건 하나**를 쓴다.
   프로필이 하나 생기면 둘이 **함께** 사라져야 한다. 조건이 갈리면 한 줄만 남는다(정합 ⓐ).
4. **배선**(§3-A 6~8 · §4-A) — 어느 버튼이 어느 팝업을 여는가 · `onMutate`가 갔는가 ·
   못 띄웠을 때 **어느 화면인지 말하는가**(F21) · **onMutate 멱등**(P15-B 인계 ①:
   거부에도 발화하므로 한 동작에 여러 번 온다).
5. **§3-E 확인창 게이트** — 1차는 토큰 없이 · 확인창 본문의 `{total}`은 **미리보기 봉투**가
   준 값(장면은 overview.total=9 / preview.total=42로 갈라 둔다 — 다른 출처를 쓰면 여기서
   드러난다. 이월 대장 #5·Codex D-06) · 확정 시 **받은 토큰 그대로** 2차 호출.

### 재지 않는 것
E1(실행 중인 게임이 일괄 적용을 막지 않는가)은 `test_frontend_e1.py`의 소관이다. 여기서
같은 것을 또 재면 두 검사가 서로를 믿다가 둘 다 낡는다.

★ 이 테스트도 **자기 자신을 반증한다** — 아래 `BYPASSES`에 적힌 알려진 위반을 **전량** 주입해
  **그 판정이** 잡는지 본다(기대 판정 지정: 다른 가드가 대신 잡아 주는 「이중 가드 위장」을
  무효로 친다). ⚠️ 여기에 **개수를 적지 않는다** — 표가 늘 때마다 문서만 낡는다(P16 E9:
  실제로 "19종"이라 적힌 채 표는 23종이 됐다). 실행 로그가 검출 건을 한 줄씩 찍는다.

⚠️ 원리적 한계: 프로브는 node에서 컴포넌트를 직접 렌더한다 — 실제 Steam CEF·React·@decky/ui가
  아니다. "보인다·눌린다"·투명도의 실제 렌더는 실기(§16 ⑪)가 판정한다.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "qa" / "qam_probe.cjs"
U1 = pathlib.Path(
    "/home/deck/ClaudeWork/GfxProfileToolV2/u1-toolchain/u1-bundle/toolchain/node-v22.23.2-linux-x64/bin/node"
)

#: (설명, 대상 파일, 정규식, 치환, **기대 판정 조각**)
BYPASSES = [
    # 카드 계약 속성 — 배경색만 맞으면 통과하던 자리를 두 방향으로 막는다(이종 QA 적발).
    ("카드에 외곽 테두리 재도입(9판 '테두리 친 문단'으로 회귀 — D3)", "index.tsx",
     r'const STATUS_CARD_STYLE = \{\n  \.\.\.CARD_STYLE,',
     'const STATUS_CARD_STYLE = {\n  ...CARD_STYLE,\n  border: "1px solid rgba(255,255,255,0.15)",',
     "외곽 테두리가 있다"),
    ("카드 모서리를 목록 카드와 다르게(시각 언어 통일이 깨진다)", "index.tsx",
     r'const STATUS_CARD_STYLE = \{\n  \.\.\.CARD_STYLE,',
     'const STATUS_CARD_STYLE = {\n  ...CARD_STYLE,\n  borderRadius: "12px",',
     "borderRadius가 §3-B 계약과 다르다"),
    # 10판: 군 간 간격의 문이 **컨테이너 gap 하나**로 옮겨졌다(카드 margin이 아니다).
    # 문이 하나뿐이라 대조군도 그 하나를 닫는다 — 닫으면 두 카드가 붙는다.
    ("과거군 간격 소멸(두 군이 한 덩어리로 붙는다)", "index.tsx",
     r'const STATUS_STACK_STYLE = \{ display: "flex", flexDirection: "column", gap: "8px" \}',
     'const STATUS_STACK_STYLE = { display: "flex", flexDirection: "column", gap: "0px" }',
     "군 사이 여백"),
    # 10판: 투명도는 군 <div>가 아니라 **과거군 카드**에 걸린다(카드 단위 — D02-ⓑ).
    ("busy 투명도 제거(지금 것과 직전 것이 같아 보인다)", "index.tsx",
     r"opacity: busy \? 0\.4 : 1 \}", "opacity: 1 }",
     "과거군이 흐려지지 않는다"),
    # 10판: 시각이 헤드라인 뒤 인라인에서 **머리 행 우측 자리**로 옮겨졌다(D4 봉쇄).
    # 9판 배치로 되돌리는 대조군 — 헤드라인을 머리 행 **안**으로 옮긴다(D4의 그 형태).
    ("헤드라인을 머리 행으로 되돌림(고정폭 행에 가변 텍스트 — D4 회귀)", "index.tsx",
     r'            <span style=\{STAMP_STYLE\}>\{stampOf\(summary\.at\)\}</span>\n'
     r'          </div>\n'
     r'          <div style=\{HEADLINE_STYLE\}>\{summary\.headline\}</div>\n',
     '            <div style={HEADLINE_STYLE}>{summary.headline}</div>\n'
     '            <span style={STAMP_STYLE}>{stampOf(summary.at)}</span>\n'
     '          </div>\n',
     "헤드라인이 머리 행"),
    ("결과 시각 제거(언제 있었던 일인지 사라진다)", "index.tsx",
     r'            <span style=\{STAMP_STYLE\}>\{stampOf\(summary\.at\)\}</span>\n', "",
     "결과 줄에 시각이 없다"),
    ("실패 시각 제거", "index.tsx",
     r'          <span>\{" · "\}\{stampOf\(failure\.at\)\}</span>\n', "",
     "실패 줄에 시각이 없다"),
    # 결함 #3: 구독을 끊으면 **승계는 살아 있고 전달만 죽는다** — 두 계약이 다르다는 증거다.
    ("결과 전달 구독 제거(적용이 끝나도 열려 있는 화면에 안 온다 — 결함#3 회귀)", "index.tsx",
     r"    statusListeners\.add\(sync\);\n", "",
     "열려 있는 화면에 결과가 오지 않는다"),
    # 같은 결함을 **문 쪽에서** 두 방향으로 더 막는다. 위 대조군은 구독자(받는 쪽)를 끊고,
    # 아래 둘은 통지자(보내는 쪽)를 끊는다 — 한쪽만 잠그면 반대쪽 회귀가 그대로 통과한다.
    ("요약 문의 통지 누락(값은 남는데 알리지 않는다 — 결함#3 회귀)", "index.tsx",
     r"  lastSummary = next;\n  statusListeners\.forEach\(\(notify\) => notify\(\)\);\n",
     "  lastSummary = next;\n",
     "열려 있는 화면에 결과가 오지 않는다"),
    ("요약을 구판 직접 대입으로 환원(문을 우회한다 — 결함#3 회귀)", "index.tsx",
     r"    setLastSummary\(next\);\n",
     "    lastSummary = next;\n    setSummary(next);\n",
     "열려 있는 화면에 결과가 오지 않는다"),
    # 10판: 모듈 변수를 쓰는 자리가 **모듈 수준의 문 하나**로 옮겨졌다(결함#3) — 들여쓰기가
    # 4칸에서 2칸이 됐다. 지우면 값이 안 남아 승계가 깨진다(전달과는 다른 계약이다).
    ("실패 승계 제거(QAM을 닫으면 실패만 사라진다 — F20 회귀)", "index.tsx",
     r"\n  lastFailure = next;\n", "",
     "실패가 승계되지 않는다"),
    ("실패 소거 누락(로드가 성공했는데 옛 실패가 남는다)", "index.tsx",
     r"      // 새 로드 성공 = 다음 동작의 시작이다 — 승계해 온 실패를 여기서 거둔다\(§3-B 수명\)\.\n      setFailure\(null\);\n",
     "",
     "새 로드가 성공했는데"),
    # 12판: 이 식의 소비자는 **설명 줄 한 곳**만 남았다(상태박스 ④ 폐기). 변이는 그대로 두고
    # 기대 판정만 이관한다 — 프로필이 생겼는데 설명 줄이 GUIDE에서 안 갈아탄다.
    ("H2 조건 붕괴(프로필이 생겨도 설명 줄이 GUIDE에 머문다)", "index.tsx",
     r"counts\.dock_ready \+ counts\.internal_ready === 0",
     "counts.dock_ready * counts.internal_ready === 0",
     "프로필이 생겼는데"),
    # ★ 11판의 "설명 ②에 별도 조건 신설" 변이는 **소스 패턴이 사라져 조용히 죽는다**(누적 구조
    #   폐기). 같은 자리를 12판 판정표로 다시 겨눈다 — **2행(등록 0 갈래)을 지우는** 변이다.
    ("판정표 2행 삭제(등록이 0인데 설명 줄이 뜬다)", "index.tsx",
     r"\{!counts \|\| counts\.total === 0 \? null : \(",
     "{!counts ? null : (",
     "등록이 0인데 설명 줄"),
    # ── 12판 신설 음성 대조군 5종(N-a·N-b·N-c·N-d·N-e) ────────────────────────
    # N-a: 라벨 괄호를 0에서만 다른 키로 갈라 그리던 형태(= 제거된 `BULK_NONE`)로 되돌린다.
    #      이 계약을 잡는 검사가 없어 그 키가 5개월을 살아남았다.
    #      ★ 기대 장면은 **counts가 도착한 쪽**이다(프로필0·등록0에서 `ready===0`이 실재한다) —
    #        미도착 장면의 괄호 부재는 아래 C-1 대조군이 따로 잰다.
    ("라벨 괄호를 0에서 다른 키로 갈라 그림(BULK_NONE 복원)", "BulkApplyButton.tsx",
     r"        \{ready === undefined \? null : t\(\"BULK_COUNT\", \{ n: ready \}\)\}",
     '        {(ready ?? 0) > 0 ? t("BULK_COUNT", { n: ready }) : t("BULK_NONE")}',
     "라벨의 괄호가 계약과 다르다(프로필0)"),
    # ── C-1 음성 대조군 2종: "counts 도착"이라는 문이 라벨·활성 양쪽을 지배하는가 ──────
    # ⓐ 호출부의 `?? 0` 폴백 부활 — 모르는 채 `(0개)`를 단언하던 형태.
    ("counts 미도착에 ready 0 폴백 부활(모르는데 (0개)라 단언)", "index.tsx",
     r"ready=\{counts \? \(profile === \"dock\" \? counts\.dock_ready : counts\.internal_ready\) : undefined\}",
     'ready={(profile === "dock" ? counts?.dock_ready : counts?.internal_ready) ?? 0}',
     "라벨의 괄호가 계약과 다르다(로딩)"),
    # ⓑ 활성 조건의 폴백 제거 — `undefined`가 활성이 되어 **모르는 채 눌리는 버튼**이 된다.
    #    ★ 기대 장면은 **조회 실패**다: 로딩 중에는 `locking`이 이미 잠그고 있어(§4-F 문) 이
    #      회귀가 드러나지 않는다. 조회가 **끝났는데 counts가 없는** 상태 — 실패 갈래 — 만이
    #      `ready`의 폴백이 유일한 방어선인 자리다. 로딩 장면의 같은 판정은 그대로 두되(잠금이
    #      풀리는 날 그쪽도 잡는다), 실증의 무게는 여기에 있다.
    ("비활성 폴백 제거(counts 미도착인데 버튼이 눌린다)", "BulkApplyButton.tsx",
     r"        disabled=\{\(ready \?\? 0\) === 0 \|\| busy\}",
     "        disabled={ready === 0 || busy}",
     "counts 미도착(조회 실패)인데 일괄 적용 버튼이 눌린다"),
    # N-b: 사유 줄이 다시 `ready`를 읽는 형태 — 라벨의 `(0개)`와 같은 말을 두 번 한다.
    ("사유 줄이 ready를 본다(라벨과 같은 말을 두 번 한다)", "index.tsx",
     r'  if \(counts\.total === 0\) return t\("BULK_NO_GAMES"\);',
     '  if (counts.total === 0) return t("BULK_NO_GAMES");\n'
     '  if (counts.dock_ready + counts.internal_ready === 0) return t("BULK_NO_GAMES");',
     "사유 줄이 붙었다"),
    # N-c: 11판의 **누적 구조**(①상시 + ②조건부)로 되돌린다 — 두 키가 한 화면에 동시에 선다.
    ("설명 영역을 상시+조건부 누적 구조로 되돌림(두 줄이 함께 뜬다)", "index.tsx",
     r"\{!counts \|\| counts\.total === 0 \? null : \(\n"
     r"          <PanelSectionRow>\n"
     r"            <div style=\{HINT_STYLE\}>\n"
     r"              \{noProfilesYet \? t\(\"QAM_ABOUT_GUIDE\"\) : t\(\"QAM_ABOUT\"\)\}\n"
     r"            </div>\n"
     r"          </PanelSectionRow>\n"
     r"        \)\}",
     '<PanelSectionRow>\n'
     '          <div style={HINT_STYLE}>{t("QAM_ABOUT")}</div>\n'
     '        </PanelSectionRow>\n'
     '        {noProfilesYet && (\n'
     '          <PanelSectionRow>\n'
     '            <div style={HINT_STYLE}>{t("QAM_ABOUT_GUIDE")}</div>\n'
     '          </PanelSectionRow>\n'
     '        )}',
     "배타성 위반"),
    # N-d: **미렌더 조건에 프로필 수를 넣는** 형태. `noProfiles` 장면만 보면 통과하고,
    #      `running:1`을 더한 대조군에서만 드러난다.
    ("상태박스 미렌더 조건에 프로필 수를 넣음(실행 중 고지가 사라진다)", "index.tsx",
     r"  function renderStatusBox\(\): ReactNode \{\n    const now: ReactNode\[\] = \[\];",
     "  function renderStatusBox(): ReactNode {\n    if (noProfilesYet) return null;\n"
     "    const now: ReactNode[] = [];",
     "프로필 0 + 실행 중"),
    # ★★ 위 변이를 **N-d만 피해 가게 좁힌** 형태(QA 게이트 적발 — 이것이 전 검사를 통과했다).
    #    "실행 중일 때만 예외"로 두면 현재군 한 슬롯은 살아나지만 **과거군·실패가 사라진다.**
    #    두 형태를 각각 다른 판정으로 겨눠, 어느 축의 표본이 죽어도 드러나게 한다.
    ("미렌더 조건에 프로필 수 + running만 예외(직전 결과가 사라진다)", "index.tsx",
     r"  function renderStatusBox\(\): ReactNode \{\n    const now: ReactNode\[\] = \[\];",
     "  function renderStatusBox(): ReactNode {\n"
     "    if (noProfilesYet && !runningNote) return null;\n"
     "    const now: ReactNode[] = [];",
     "직전 일괄 결과가 화면에서 사라졌다"),
    ("호출부에서 프로필 0을 통째로 숨김(실패 줄까지 사라진다)", "index.tsx",
     r"        \{renderStatusBox\(\)\}",
     "        {noProfilesYet && !counts?.running ? null : renderStatusBox()}",
     "실패 줄이 사라졌다"),
    # N-e: 판정표 1행을 **로딩만 덮게** 좁힌다 — 조회 실패·실패 승계에서 설명 줄이 되살아난다.
    #      (`?.`는 좁힌 뒤에도 렌더가 죽지 않게 하는 것뿐이다 — 실제 회귀도 그렇게 생긴다.)
    ("판정표 1행을 로딩만 덮게 좁힘(조회 실패에서 설명 줄이 되살아난다)", "index.tsx",
     r"\{!counts \|\| counts\.total === 0 \? null : \(",
     "{(!overview && !failure) || counts?.total === 0 ? null : (",
     "counts 미도착"),
    ("D01 위반 — 카운트 줄이 조회 전에 '게임 없음'을 단언", "index.tsx",
     r'  const countText = !counts\n    \? ""', '  const countText = !counts\n    ? t("NO_GAMES")',
     "조회 전인데 카운트 줄이"),
    ("D01 위반 — hint가 조회 전에 '게임 없음'을 단언", "index.tsx",
     r"  if \(!counts\) return undefined;", '  if (!counts) return t("NO_GAMES");',
     "조회 전인데 일괄 버튼 사유가"),
    ("확인창 본문의 total을 다른 출처로(토큰이 지문 낸 대상과 어긋난다)", "index.tsx",
     r"t\(\"APPLY_ALL_CONFIRM_BODY\", \{ total: params\.total, profile: profileName \}\)",
     't("APPLY_ALL_CONFIRM_BODY", { total: 9, profile: profileName })',
     "확인창 본문의 total"),
    ("1차 호출에 토큰을 지어냄(무쓰기 미리보기 계약 붕괴)", "index.tsx",
     r"applyAll\(profile, token\)\.catch\(deadApply\)",
     'applyAll(profile, token ?? "MADE-UP-TOKEN").catch(deadApply)',
     "1차 호출에 토큰"),
    ("진입 버튼이 다른 팝업을 연다", "index.tsx",
     r"            \(\) => <GamesPopup onMutate=\{refresh\} />,",
     "            () => <SettingsPopup onMutate={refresh} />,",
     "OPEN_GAMES"),
    ("팝업에 onMutate를 안 넘김(변이해도 QAM이 낡는다)", "index.tsx",
     r"            \(\) => <DiscoverPopup onMutate=\{refresh\} />,",
     "            () => <DiscoverPopup />,",
     "onMutate를 받지 못했다"),
    ("팝업 실패 고지가 대상을 말하지 않음(F21 회귀)", "index.tsx",
     r'        setFailure\(\{ key: failKey, code: "MODAL", at: Date\.now\(\) \}\);',
     '        setFailure({ key: "APPLY_CONFIRM_MODAL_FAILED", code: "MODAL", at: Date.now() });',
     "실패 고지가 그 화면을 가리키지 않는다"),
    ("통지 1회에 조회 2회(멱등 아님 — 통지가 잦은 경로에서 비용이 배로)", "index.tsx",
     r"            \(\) => <DiscoverPopup onMutate=\{refresh\} />,",
     "            () => <DiscoverPopup onMutate={() => { refresh(); refresh(); }} />,",
     "통지 1회에 조회가"),
    ("진행 문구 분기 소멸(무쓰기 확인 중에도 '적용 중'이라 말한다)", "index.tsx",
     r"\{previewing \? t\(\"APPLY_PREVIEWING\"\) : t\(\"APPLYING\"\)\}", '{t("APPLYING")}',
     "미리보기 중인데"),
    ("체크인 고지 소멸(직전 프로필이 조용히 바뀐다)", "index.tsx",
     r"      if \(summary\.checkin > 0\) \{", "      if (summary.checkin > 99) {",
     "체크인"),
    ("결과 아이콘이 언제나 체크(문제가 있었는데 성공처럼 보인다)", "index.tsx",
     r"\{summary\.problems \? <IconWarn /> : <IconCheck />\}", "{<IconCheck />}",
     "문제가 있는 결과"),
    # ── P15-E R1·R2: 뿌리(공용 문)와 표시층을 각각 겨눈다 ────────────────────
    ("실패 봉투의 체크인을 안 읽음(직전 프로필이 조용히 바뀐다)", "index.tsx",
     r"checkinCount\(res\.params\)", "0",
     "체크인이 침묵한다"),
    ("실패 봉투를 직전 결과에 안 남김(P15-E 이전의 침묵 갈래로 되돌림)", "index.tsx",
     r"keepSummary\(stoppedSummary\(profile, res\.code, checkinCount\(res\.params\)\)\);",
     'setFailure({ key: "APPLY_FAILED", code: res.code, at: Date.now() });',
     "직전 결과에 아무 기록이 없다"),
    ("세대 가드를 뺌 — QAM이 공용 문의 보증을 못 받는다", "popup.tsx",
     r"      // 옛 응답은 \*\*없던 일\*\*이다 — 화면은 이미 더 새 것을 알고 있다\.\n"
     r"      if \(mine !== generation\.current\) return;\n", "",
     "세대 가드가 없다"),
    # ── C4: 잠금축을 표시축으로 되돌림(조회 중에 쓰기가 시작된다) ─────────────
    ("일괄 버튼 잠금을 변이축으로 되돌림(조회 중에 쓰기가 시작된다)", "index.tsx",
     r"            busy=\{locking\}", "            busy={busy}",
     "조회가 도는 중인데 일괄 적용 버튼이 열려 있다"),
    ("확정 실행 **실패**에 재조회를 안 붙임 — QAM만 낡는다", "popup.tsx",
     r"if \(!writing \|\| isTokenIssue\(res\)\) return;", "if (!writing || !res.ok) return;",
     "현황을 다시 읽지 않았다"),
]


def run_probe(src_dir=None):
    args = [str(U1), str(PROBE)]
    if src_dir is not None:
        args.append(str(src_dir))
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


def keys(lines):
    return [l["key"] for l in lines]


def has(texts, key):
    return any(x == key or x.startswith(key + " ") for x in texts)


#: 일괄 버튼 라벨의 **끝 괄호**. 규칙은 두 층이다(§2-B 12판 + C-1 정정):
#:   ⓐ **counts 도착 여부**가 괄호의 유무를 정한다 — 미도착이면 괄호가 **아예 없다**(D01).
#:   ⓑ 도착한 뒤에는 `ready`가 0이어도 `BULK_COUNT`로 그린다 — 0에서만 다른 키로 갈라 그리면
#:      같은 자리·같은 종류의 수가 한쪽만 숫자라 `(3개)`↔`(0개)` 비교가 깨진다.
#: ⚠️ **이 계약을 잡는 검사가 지금까지 하나도 없었다**(라벨 접두 `BULK_APPLY`만 봤다) —
#:   미등재 승계 키 `BULK_NONE`이 5개월 안 걸린 이유다.
LABEL_COUNT = re.compile(r"^BULK_APPLY \S+ BULK_COUNT (\d+)$")
LABEL_BARE = re.compile(r"^BULK_APPLY \S+$")


def label_counts(labels):
    """라벨을 세 갈래로 읽는다 — **`int`**=괄호 안의 수 · **`None`**=괄호 없음(counts 미도착의
    정직한 표현) · **원문 문자열**=그 밖의 무엇이든(다른 키로 갈라 그렸다). 세 번째를 `None`과
    뭉치면 *"모른다고 말한 것"*과 *"거짓말한 것"*이 판정에서 같아진다."""
    out = []
    for label in labels:
        label = label or ""
        m = LABEL_COUNT.match(label)
        if m:
            out.append(int(m.group(1)))
        elif LABEL_BARE.match(label):
            out.append(None)
        else:
            out.append(label)
    return out


def violations(r):                                             # noqa: C901  (판정 나열)
    out = []

    # ═══ ⓪·D01 로딩 ══════════════════════════════════════════════════════════
    load = r["loading"]
    if keys(load["lines"]) != ["loading"]:
        out.append(f"⓪ 조회 전 상태박스가 로딩 한 줄이 아니다: {load['lines']}")
    if load["count"] != "":
        out.append(f"★D01 위반 — 조회 전인데 카운트 줄이 무언가를 단언한다: {load['count']!r} "
                   f"(모르는 것을 0으로 말하면 화면이 거짓을 말한다)")
    if any(h for h in load["hints"]):
        out.append(f"★D01 위반 — 조회 전인데 일괄 버튼 사유가 채워졌다: {load['hints']}")

    # ═══ N-e ③-D 판정표 1행이 덮는 **상태 전부**에서 설명 줄 부재 ════════════════
    #
    # 1행(`!counts`)은 한 조건이 여러 화면 상태를 덮는다: **로딩 · 조회 실패 · 실패 승계
    # 재개방**. 조회 실패는 `overview`를 만들지 않으므로(`onLoadFail`이 `setFailure`만 한다)
    # `counts`가 없다 — 실물의 그 사실에 기대는 갈래다.
    # ★ "장면 하나(로딩)"로 줄이면 **조회 실패에서 설명 줄이 되살아나도 초록불**이다. 모르는
    #   상태에서 화면이 단언하면 그것이 D01 위반이고, 세 장면을 다 들어야 그 구멍이 닫힌다.
    for scene, texts_ in (("로딩", load["texts"]),
                          ("조회 실패", r["loadFailed"]["texts"]),
                          ("실패 승계 재개방", r["failureCarriedTexts"])):
        for key in ("QAM_ABOUT", "QAM_ABOUT_GUIDE"):
            if has(texts_, key):
                out.append(f"★③-D 1행 위반 — counts 미도착({scene}) 화면인데 설명 줄 {key}가 "
                           f"섰다. 등록 수도 프로필 수도 모르는 상태에서 그 문장은 참인지 "
                           f"거짓인지조차 알 수 없다(D01)")

    # ═══ ② 정상 화면 ═════════════════════════════════════════════════════════
    nm = r["normal"]
    if keys(nm["lines"]) != ["running"]:
        out.append(f"② 실행 중 고지 한 줄만 있어야 한다: {nm['lines']}")
    if nm["lines"] and nm["lines"][0]["color"] != "#9aa0a6":
        out.append(f"② 실행 중 고지가 회색이 아니다({nm['lines'][0]['color']}) — 사실 진술이지 경고가 아니다")
    if not (nm["count"] or "").startswith("COUNT_SUMMARY"):
        out.append(f"③-C 카운트 줄이 COUNT_SUMMARY가 아니다: {nm['count']!r}")
    if any(h for h in nm["hints"]):
        out.append(f"③-A ⓑ 대상이 있는데 사유가 붙었다: {nm['hints']}")
    if nm["bulkIcons"] != ["IconBolt", "IconChip"]:
        out.append(f"§11 일괄 버튼 아이콘 배정이 다르다: {nm['bulkIcons']}")
    if any(nm["bulkDisabled"]):
        out.append(f"대상이 있는데 일괄 버튼이 비활성이다: {nm['bulkDisabled']}")
    want_entries = [
        ("OPEN_DISCOVER", "OPEN_DISCOVER_DESC", "IconSearch"),
        ("OPEN_GAMES", "OPEN_GAMES_DESC", "IconList"),
        ("OPEN_SETTINGS", "OPEN_SETTINGS_DESC", "IconGear"),
    ]
    got_entries = [(e["label"], e["desc"], e["icon"]) for e in nm["entries"]]
    if got_entries != want_entries:
        out.append(f"§3-A 6~8 진입 버튼의 순서·설명·아이콘이 설계와 다르다: {got_entries}")
    if has(nm["texts"], "OPEN_FULL_SCREEN"):
        out.append("★구 전체화면 입구가 QAM에 남아 있다 — §3-A 재편에서 제거된 버튼이다")

    # ═══ ④ 폐기 · ③-D 3갈래 · N-a 라벨 괄호 ═══════════════════════════════════
    npf = r["noProfiles"]
    if not npf["boxNull"]:
        out.append(f"★④ 폐기 확인 — 달리 말할 것이 없는 화면(등록 있음·프로필 0·실행 중 0·"
                   f"실패 없음·직전 결과 없음)인데 상태박스가 섰다: {npf['keys']}. 12판에서 "
                   f"시작 안내 슬롯이 사라져 이 상태에서는 박스가 통째로 미렌더된다(잔글씨 5 → 2)")
    if not has(npf["texts"], "QAM_ABOUT_GUIDE"):
        out.append("③-D 3행 — 프로필이 하나도 없는데 설명 줄이 QAM_ABOUT_GUIDE가 아니다")
    if has(npf["texts"], "QAM_ABOUT"):
        out.append("★③-D 배타성 위반 — 프로필 0 화면에 QAM_ABOUT이 함께 떴다. 설명 영역은 "
                   "어느 상태에서도 **0줄 또는 1줄**이다(상시+조건부 누적 구조는 12판에서 폐기)")
    if npf["hints"] != [None, None]:
        out.append(f"★③-A ⓑ 프로필이 없다는 이유로 사유 줄이 붙었다: {npf['hints']} — 라벨의 "
                   f"`(0개)`가 이미 같은 말을 한다(12판: 숫자가 말하지 못하는 것만 말한다)")

    # ═══ N-d 미렌더의 **음성 대조군** — 프로필 수는 미렌더 조건이 아니다 ═════════
    #
    # 위 장면에 `running:1`만 더한 것이다. `runningNote`는 `counts.running`만 보고 프로필
    # 유무를 보지 않으므로 상태박스가 **선다.** "프로필 0 → 무조건 null"로 오독한 구현은
    # 여기서만 드러나고, 그 조합은 §5-B 저장 안내가 유도하는 정상 흐름 그 자체다.
    npr = r["noProfilesRunning"]
    if npr["boxNull"] or keys(npr["lines"]) != ["running"]:
        out.append(f"★프로필 0 + 실행 중인데 상태박스가 서지 않는다(box null={npr['boxNull']}, "
                   f"{keys(npr['lines'])}) — 미렌더 조건에 **프로필 수**를 넣었다는 뜻이다. "
                   f"조건은 '현재군·과거군 줄이 모두 0'이고 프로필 수는 거기 없다(§3-B). "
                   f"프로필이 없다는 이유로 실행 중 고지를 숨기면 화면이 거짓을 말한다")
    elif not npr["lines"][0]["text"].startswith("BULK_RUNNING_NOTE"):
        out.append(f"★프로필 0 + 실행 중의 그 한 줄이 실행 중 고지가 아니다: {npr['lines']}")

    # ═══ 미렌더 조건의 **나머지 두 축** — 과거군·실패도 프로필 수를 보지 않는다 ═══
    #
    # ★★ 위 N-d는 **현재군 한 슬롯**(실행 중 고지)만 잰다. 그래서 *"프로필 0이면 숨긴다 — 단
    #   실행 중일 때만 예외"*로 좁힌 구현이 검사를 통째로 통과했다(QA 게이트 적발). §3-B의
    #   계약은 *"현재군·과거군 줄이 **모두** 0일 때만 미렌더"*이므로, 축마다 표본이 있어야
    #   검사가 계약만큼 넓어진다 — **검사가 계약보다 좁은데 문서가 넓게 위임하는** 형태를
    #   이 프로젝트는 다섯 번 겪었다.
    nps = r["noProfilesSummary"]
    if nps["boxNull"] or "result" not in keys(nps["lines"]):
        out.append(f"★프로필 0인데 **직전 일괄 결과가 화면에서 사라졌다**(box null="
                   f"{nps['boxNull']}, {keys(nps['lines'])}) — 미렌더 조건에 프로필 수가 들어갔다는 "
                   f"뜻이다. 과거군은 `lastSummary` 하나만 보고 프로필 유무를 보지 않는다. "
                   f"일괄 적용 뒤 등록을 전부 해제하면 실사용에서 바로 도달하는 상태이고, "
                   f"거기서 결과를 숨기면 *무슨 일이 있었는지*가 화면에서 사라진다(§3-B)")
    npx = r["noProfilesFailure"]
    if npx["boxNull"] or keys(npx["lines"]) != ["failure"]:
        out.append(f"★프로필 0인데 **실패 줄이 사라졌다**(box null={npx['boxNull']}, "
                   f"{keys(npx['lines'])}) — 실패도 프로필 수와 무관하다. ⚠️ 이 축은 "
                   f"`failureCarried`(counts 미도착)로는 못 덮는다: 거기서는 '프로필 0'이라는 "
                   f"사실 자체가 화면에 없다. 조회가 성공해 counts가 도착한 위에서 실패가 뜨는 "
                   f"이 표본만이 두 사실을 동시에 참으로 만든다")

    one = r["oneProfile"]
    if has(one["texts"], "QAM_ABOUT_GUIDE"):
        out.append("★프로필이 생겼는데 설명 줄이 여전히 QAM_ABOUT_GUIDE다 — 3행과 4행은 "
                   "**같은 식의 참/거짓**이라 프로필이 하나 생기는 순간 갈아타야 한다")
    if not has(one["texts"], "QAM_ABOUT"):
        out.append("③-D 4행 — 프로필이 있는데 설명 줄이 QAM_ABOUT이 아니다")
    if one["hints"] != [None, None]:
        out.append(f"③-A ⓑ 등록이 있는데 사유 줄이 붙었다: {one['hints']} — 프로필이 없는 쪽의 "
                   f"사정은 라벨의 `(0개)`가 말한다")

    ng = r["noGames"]
    if ng["count"] != "NO_GAMES":
        out.append(f"③-C 등록 0인데 카운트 자리가 안내를 맡지 않았다: {ng['count']!r}")
    if ng["hints"] != ["BULK_NO_GAMES", "BULK_NO_GAMES"]:
        out.append(f"③-A ⓑ 등록 0의 사유가 BULK_NO_GAMES가 아니다: {ng['hints']} — 갈 곳 안내는 "
                   f"카운트 줄의 NO_GAMES가 전담하고, 사유 줄은 '적용할 게임이 없다'만 말한다")
    for key in ("QAM_ABOUT", "QAM_ABOUT_GUIDE"):
        if has(ng["texts"], key):
            out.append(f"★③-D 2행 위반 — 등록이 0인데 설명 줄 {key}가 떴다. 그 상태의 안내는 "
                       f"카운트 줄 NO_GAMES가 전담한다([게임 감지]를 가리키는 손가락은 하나다)")

    # ═══ N-a 라벨 괄호 — counts 도착이 유무를, 수가 내용을 정한다(§2-B 12판 + C-1) ═══
    #
    # ★ counts **도착** 장면(정상·프로필0·프로필1·등록0)이 "0도 숫자로 그린다"의 증거이고,
    #   counts **미도착** 장면(로딩·조회 실패)이 "모르면 괄호가 없다"의 증거다. 두 축을 한
    #   판정으로 함께 잠근다 — 한쪽만 두면 나머지 한쪽이 조용히 뒤집힌다.
    for scene, snap, want in (("로딩", load, [None, None]),
                              ("조회 실패", r["loadFailed"], [None, None]),
                              ("정상", nm, [9, 8]), ("프로필0", npf, [0, 0]),
                              ("프로필1", one, [1, 0]), ("등록0", ng, [0, 0])):
        got = label_counts(snap["labels"])
        if got != want:
            out.append(f"★③-A 라벨의 괄호가 계약과 다르다({scene}): {snap['labels']} → {got} "
                       f"(기대 {want}). ⓐ counts 미도착이면 괄호가 **없다** — 모르는 것을 `(0개)`로 "
                       f"말하면 같은 화면의 카운트 줄·설명 줄·사유 줄이 지키는 D01을 라벨만 어긴다. "
                       f"ⓑ 도착한 뒤에는 0도 숫자로 그린다 — 0에서만 다른 키로 갈라 그리면 같은 "
                       f"자리의 수가 한쪽만 숫자라 `(3개)`↔`(0개)` 비교가 깨진다(버튼 괄호는 "
                       f"**상태 수치**다 — §7 관례 정본: 0에서 침묵하는 것은 **사건 서술**이다)")

    # ═══ C-1 counts 미도착이면 **누를 수 없다** ═══════════════════════════════════
    #
    # ★★ 라벨의 거짓 표시보다 나쁜 것이 **모르는 채 눌리는 버튼**이다: 그 상태로 누르면 백엔드는
    #   방금 읽고 있던 것과 **다른 현황** 위에서 쓰기를 시작한다(§4-F가 문을 하나로 합친 이유).
    #   `ready`를 옵셔널로 바꾸면서 `disabled={ready === 0 || busy}`는 `undefined`에서 **활성**이
    #   되므로, 폴백(`(ready ?? 0) === 0`)이 빠지는 순간을 잡을 판정이 반드시 있어야 한다.
    for scene, snap in (("로딩", load), ("조회 실패", r["loadFailed"])):
        if snap["disabled"] != [True, True]:
            out.append(f"★C-1 counts 미도착({scene})인데 일괄 적용 버튼이 눌린다: "
                       f"{snap['disabled']} — 대상 수를 모르는 채 활성이면 사용자는 무엇에 적용되는지 "
                       f"모르고 누르고, 백엔드는 방금 읽던 것과 다른 현황 위에서 쓰기를 시작한다. "
                       f"모르면 잠근다(`(ready ?? 0) === 0`)")

    # ═══ ③ 실패 줄 · 승계 · 소거 ══════════════════════════════════════════════
    lf = r["loadFailed"]
    if keys(lf["lines"]) != ["failure"]:
        out.append(f"③ 조회 실패에 실패 줄 하나가 아니다: {lf['lines']}")
    else:
        line = lf["lines"][0]
        if line["color"] != "#ffb454":
            out.append(f"③ 실패 줄이 주황이 아니다: {line['color']} (색은 2단 — 빨강 없음 A8)")
        if "REGISTRY_UNREADABLE" not in line["text"]:
            out.append(f"③ 실패 사유가 tCode 관문을 지나지 않았다: {line['text']!r}")
        if not line["stamped"]:
            out.append(f"★③ 실패 줄에 시각이 없다: {line['text']!r} — 언제 것인지 모르면 "
                       f"방금 실패인지 어제 실패인지 알 수 없다")
    if keys(r["failureCarried"]) != ["failure"]:
        out.append(f"★F20 위반 — 실패가 승계되지 않는다(QAM을 닫으면 사라진다): {r['failureCarried']}")
    if r["failureCleared"]:
        out.append(f"★새 로드가 성공했는데 옛 실패가 남아 있다: {r['failureCleared']} "
                   f"(소거 시점 = 다음 동작 시작 — §3-B 수명)")

    # ═══ ⑤ 확인창 게이트(§3-E) ═══════════════════════════════════════════════
    # ⚠️ **필드가 없는 것**과 값이 틀린 것은 다른 사건이다. JSON은 `undefined`를 실어 나르지
    #    않으므로, 버튼을 못 눌러 측정 자체가 없었던 회차에는 키가 통째로 빠져 온다. 예전에는
    #    여기서 `KeyError: confirmFound`로 판정기가 죽었다(P16 E10) — 위반은 잡혔는데 사람이
    #    받는 것은 진단이 아니라 스택 트레이스였다. 이제 **측정 없음**을 그렇게 말한다.
    cf = r["confirm"]
    if cf.get("blocked"):
        out.append("⑤ 일괄 버튼을 누를 수 없었다 — 게이트를 잴 수 없다(검사 무효). "
                   "확인창·토큰 판정은 **측정이 없어** 건너뛴다")
    else:
        for field in ("confirmFound", "firstCall", "secondCall", "confirmTexts"):
            if field not in cf:
                out.append(f"⑤ 프로브가 {field}를 싣지 않았다 — 측정이 이뤄지지 않았다"
                           f"(검사 무효): {sorted(cf)}")
        if not cf.get("confirmFound"):
            out.append("★⑤ 확인창이 뜨지 않았다 — F8 마찰이 사라졌다")
        if (cf.get("firstCall") or {}).get("token") is not None:
            out.append(f"★⑤ 1차 호출에 토큰이 실렸다: {cf.get('firstCall')} — 프론트가 토큰을 지어냈다")
        if (cf.get("secondCall") or {}).get("token") != "TOKEN-dock":
            out.append(f"★⑤ 확정 시 받은 토큰 그대로 2차 호출이 나가지 않았다: {cf.get('secondCall')}")
        confirm_texts = cf.get("confirmTexts") or []
        body = [x for x in confirm_texts if x.startswith("APPLY_ALL_CONFIRM_BODY")]
        if not body:
            out.append(f"⑤ 확인창 본문이 없다: {confirm_texts}")
        elif "42" not in body[0]:
            # 장면은 overview.total=9 · preview.total=42다. 9가 보이면 다른 시점의 조회를 그린 것이다.
            out.append(f"★⑤ 확인창 본문의 total이 미리보기 봉투의 값이 아니다: {body[0]!r} "
                       f"(preview.total=42 / overview.total=9 — 토큰이 지문 낸 대상과 어긋난다, D-06)")
        if any(x.startswith("APPLY_ALL_CONFIRM_NOTE") for x in confirm_texts):
            out.append("⑤ 무정보 상시 줄(APPLY_ALL_CONFIRM_NOTE)이 남아 있다 — §3-E D04에서 삭제됐다")

    # ═══ ⑤⑥⑦ 결과 줄 ════════════════════════════════════════════════════════
    rp = r["resultProblem"]
    got = keys(rp["lines"])
    # 슬롯마다 **따로** 판정한다 — 구성 한 줄로 뭉치면 어느 줄이 사라졌는지가 판정에서 지워진다.
    by_key = {l["key"]: l for l in rp["lines"]}
    if "result" not in by_key:
        out.append(f"⑤ 결과 제목 줄이 없다: {got}")
    if "why" not in by_key:
        out.append(f"⑥ 문제가 있었는데 사유 줄이 없다: {got} — 무엇을 해야 하는지가 사라진다")
    if "checkin" not in by_key:
        out.append(f"★⑦ 체크인 고지가 없다: {got} — 직전 프로필이 조용히 바뀐 사실을 "
                   f"화면이 말하지 않는다(§5-E)")
    if got != ["result", "why", "checkin"] and len(by_key) == 3:
        out.append(f"⑤⑥⑦ 결과 줄 순서가 다르다: {got}")
    if len(by_key) == 3:
        title, why, checkin = by_key["result"], by_key["why"], by_key["checkin"]
        if title["icons"] != ["IconWarn"]:
            out.append(f"★⑤ 문제가 있는 결과인데 아이콘이 경고가 아니다: {title['icons']} (D05)")
        if not title["stamped"]:
            out.append(f"★⑤ 결과 줄에 시각이 없다: {title['text']!r}")
        # §3-B 10판 폭 규약: 고정폭(아이콘·시각) 행에 **가변 텍스트를 넣지 않는다**. 9판이 셋을
        # 한 줄에 두어 268px에서 낱자로 감겨 붕괴했다(D4). 글자만 보는 판정은 그 배치로
        # 되돌아가도 초록불이라, **어디에 있는지**를 따로 잠근다.
        if title.get("headlineInHead"):
            out.append("★⑤ 헤드라인이 머리 행(고정폭 행) 안에 있다 — 아이콘·시각과 한 flex 행에 "
                       "가변 텍스트를 두면 268px에서 셋이 함께 감긴다(D4가 그 붕괴였다)")
        if "APPLY_PROBLEM_REFUSED" not in why["text"] or "게임 둘" not in why["text"]:
            out.append(f"⑥ 거부 사유가 **이름**을 말하지 않는다(F16-ⓑ): {why['text']!r}")
        if "APPLY_PROBLEM_SPECIFIC" not in why["text"]:
            out.append(f"⑥ 코드별 사유 묶음이 없다: {why['text']!r}")
        if why["color"] != "#ffb454":
            out.append(f"⑥ 사유 줄이 주황이 아니다: {why['color']}")
        if not checkin["text"].startswith("CHECKIN_MANY"):
            out.append(f"★⑦ 체크인 고지가 없다: {checkin['text']!r} — 직전 프로필이 조용히 바뀐다")
        if checkin["color"] != "#9aa0a6":
            out.append(f"⑦ 체크인 고지는 사실 진술이라 회색이다: {checkin['color']}")
    if rp["toasts"] != 1:
        out.append(f"결과 토스트가 {rp['toasts']}회다(1회여야 한다 — 닫혀 있는 QAM에도 닿는 부가 채널)")

    rc = r["resultClean"]
    if keys(rc["lines"]) != ["result"]:
        out.append(f"⑥⑦ 문제·체크인이 0인데 줄이 생겼다: {keys(rc['lines'])} (0이면 안 그림)")
    elif rc["lines"][0]["icons"] != ["IconCheck"]:
        out.append(f"⑤ 문제 0인 결과의 아이콘이 체크가 아니다: {rc['lines'][0]['icons']}")

    # ═══ ① 진행 문구 · 군 분리 · 투명도 ══════════════════════════════════════
    pv, ap, ab = r["previewing"], r["applying"], r["afterBusy"]
    if pv["keys"] != ["busy", "result"]:
        out.append(f"① 미리보기 중 화면 구성이 다르다: {pv['keys']}")
    if not any(x == "APPLY_PREVIEWING" for x in pv["texts"]):
        out.append(f"★① 미리보기 중인데 '확인 중'이라 말하지 않는다: {pv['texts']} "
                   f"(무쓰기 왕복과 실제 쓰기는 다른 말이다 — D14)")
    if not any(x == "APPLYING" for x in ap["texts"]):
        out.append(f"① 토큰 재호출(실행) 중인데 '적용 중'이라 말하지 않는다: {ap['texts']}")
    for name, snap in (("미리보기", pv), ("적용", ap)):
        # ⚠️ JSON은 undefined를 실어 나르지 않는다 — 값이 **없는 것**도 위반이다(박스·군이 사라진 경우).
        if snap.get("pastOpacity") != 0.4:
            out.append(f"★① {name} 중 과거군이 흐려지지 않는다(opacity={snap.get('pastOpacity')}) — "
                       f"직전 결과가 '지금 것'처럼 보인다(D02-ⓑ)")
    if ab.get("pastOpacity") != 1:
        out.append(f"① 왕복이 끝났는데 결과가 흐린 채다: {ab.get('pastOpacity')}")
    # ═══ 카드 계약 속성(§3-B 10판) ════════════════════════════════════════════
    #
    # ★★ 찾는 조건과 **재는 조건**은 다른 일이다. 프로브는 카드를 배경색 하나로 찾는데,
    #   그것만 판정하면 나머지 시각 계약(모서리·안쪽 여백·글자 크기·줄 간격)을 전부 깨뜨려도
    #   초록불이다(이종 QA 적발). `CARD_STYLE` 정본 재사용이 10판의 요지이므로 그 값들을 잠근다.
    # ★ `border`는 **없어야 하는 것**을 재는 자리다: 9판 테두리 박스 폐기가 D3의 핵심이라,
    #   되살아나면 카드형이 아니라 *"테두리 친 문단"*으로 돌아간다(사용자 접수 문구 그대로).
    CARD_CONTRACT = {
        "borderRadius": "4px", "padding": "8px 10px", "fontSize": "12px", "innerGap": "6px",
    }
    for card in r["resultProblem"]["groups"]:
        for prop, want in CARD_CONTRACT.items():
            if card.get(prop) != want:
                out.append(f"★결과 카드의 {prop}가 §3-B 계약과 다르다: {card.get(prop)!r} "
                           f"(기대 {want!r}) — 카드는 팝업 목록 카드와 **같은 시각 언어**여야 한다"
                           f"(CARD_STYLE 정본 재사용). 배경색만 맞고 나머지가 갈리면 같은 것이 "
                           f"화면마다 다르게 보인다")
        if card.get("border"):
            out.append(f"★결과 카드에 외곽 테두리가 있다: {card['border']!r} — 9판의 테두리 박스는 "
                       f"*\"로그창도 카드도 아닌 테두리 친 문단\"*으로 읽혀 10판에서 폐기됐다(D3). "
                       f"되살리면 카드형 전환이 무의미해진다")

    groups = r["resultProblem"]["groups"]
    # ★ 10판: "현재군이 비었는데 과거군에 여백이 붙는" 9판의 결함은 **재발할 형태가 없어졌다** —
    #   간격을 컨테이너 gap이 소유하므로 카드가 하나면 여백이 생길 자리가 없다. 그래서 여기서는
    #   여백이 아니라 **카드가 하나뿐인가**만 잰다(FAIL을 만들 수 없는 검사는 장식이다).
    if len(groups) != 1:
        out.append(f"⑤ 현재군이 비었는데 카드가 {len(groups)}장이다: {groups}")
    # 두 군이 함께 있을 때가 **분리가 의미를 갖는 유일한 상황**이다(D06 — 위=지금 / 아래=직전).
    pvg = pv.get("groups") or []
    if len(pvg) != 2 or pvg[0]["keys"] != ["busy"] or pvg[1]["keys"] != ["result"]:
        out.append(f"★① 현재군과 과거군이 갈려 있지 않다: {pvg} — 지금 일어나는 일과 직전 결과가 "
                   f"한 덩어리로 읽힌다")
    elif pv.get("boxGap") != "8px":
        out.append(f"★① 두 군 사이 여백이 없다(컨테이너 gap={pv.get('boxGap')}) — 시각 분리가 사라졌다")
    # 카드가 목록용 4px를 그대로 물려받으면 간격이 8이 아니라 12가 된다 — 덮었는지 함께 본다.
    elif any(g.get("marginBottom") != "0" for g in pvg):
        out.append(f"① 결과 카드가 목록용 marginBottom을 덮지 않았다: "
                   f"{[g.get('marginBottom') for g in pvg]} — 군 간격이 gap+margin으로 겹친다")
    if r["summaryCarried"] and keys(r["summaryCarried"]) != ["result"]:
        out.append(f"요약 승계가 깨졌다: {r['summaryCarried']}")
    if not r["summaryCarried"]:
        out.append("★요약이 승계되지 않는다 — QAM을 닫으면 무슨 일이 있었는지 사라진다")

    # ═══ 결과 **전달**(확인 모달 중 재마운트) — 실기 결함 #3 회귀 잠금 ═════════
    #
    # 승계(위)와 전달(여기)은 다른 계약이다. 승계는 *"닫았다 열어도 남아 있는가"*이고,
    # 전달은 *"내가 열려 있는 동안 끝난 일이 화면에 오는가"*다. 실기에서 후자만 깨져 있었다 —
    # §3-E 확인 모달이 열리는 동안 QAM이 언마운트되고, 완료가 재마운트보다 늦으면 새 인스턴스는
    # `useState(lastSummary)`를 이미 지나쳐 **결과를 영영 모른다**(닫았다 열어야 뜬다).
    # ★ 이 시나리오는 **요약 문 단독**을 잰다(정지 갈래 = `keepSummary`만 부른다 + 후속 재조회도
    #   붙잡아 둔다). 성공 갈래는 뒤에 `setFailure(null)`이 붙어 **실패 문의 통지에 요약이
    #   편승**하므로, 요약 쪽 통지를 지워도 화면이 채워져 대조군이 샌다 — 두 문이 서로를 가린다.
    if "result" in (r["deliveryBeforeDone"] or []):
        out.append(f"결함#3 재현 전제가 깨졌다 — 완료 전인데 이미 결과가 있다: "
                   f"{r['deliveryBeforeDone']} (붙잡은 왕복이 실제로 안 붙잡혔다)")
    dad = r["deliveryAfterDone"]
    by_key = {l["key"]: l for l in dad}
    if "result" not in by_key:
        out.append(f"★결함#3 적용이 끝났는데 **열려 있는 화면에 결과가 오지 않는다**: "
                   f"{[l['key'] for l in dad]} — 확인창이 뜬 사이 QAM이 언마운트되고 완료가 "
                   f"재마운트보다 늦으면 결과가 죽은 인스턴스로 간다. 모듈 변수는 값의 정본일 뿐 "
                   f"**전달 수단이 아니다** — 갱신을 살아 있는 화면에 알려야 한다")
    elif "APPLY_ALL_STOPPED" not in by_key["result"]["text"]:
        out.append(f"★결함#3 전달된 것이 그 결과가 아니다: {by_key['result']['text']!r}")

    # ═══ ④ 배선 ══════════════════════════════════════════════════════════════
    want_wiring = [
        ("OPEN_DISCOVER", "DiscoverPopup"),
        ("OPEN_GAMES", "GamesPopup"),
        ("OPEN_SETTINGS", "SettingsPopup"),
    ]
    for (label, component), got in zip(want_wiring, r["wiring"]):
        if got["label"] != label or got["component"] != component:
            out.append(f"★④ {label}이 {got['component']}를 연다(기대 {component})")
        if not got["hasOnMutate"]:
            out.append(f"★④ {got['label']}이 연 팝업이 onMutate를 받지 못했다 — 그 팝업에서 "
                       f"무엇을 바꿔도 QAM 숫자가 낡은 채 남는다")
    idem = r["idempotent"]
    if idem["onceCalls"] != 1:
        out.append(f"★④ 통지 1회에 조회가 {idem['onceCalls']}회 나갔다 — 통지는 거부에도 오므로 "
                   f"한 동작에 여러 번 온다(P15-B 인계 ①)")
    if idem["thriceCalls"] != idem["onceCalls"] + 3:
        out.append(f"④ 통지 3회의 조회 수가 선형이 아니다: {idem['thriceCalls']}")
    if not idem["sameScreen"]:
        out.append("★④ 같은 통지를 반복했더니 화면이 달라졌다 — 갱신 핸들러가 멱등이 아니다")
    if idem["applyCalls"]:
        out.append(f"★④ 통지가 쓰기(applyAll)를 불렀다: {idem['applyCalls']}회")
    if idem["boxKeys"]:
        out.append(f"④ 통지만 했는데 상태박스에 줄이 생겼다: {idem['boxKeys']}")

    # ═══ R1 일괄 적용 **실패 봉투** — 침묵하지 않는다 ═════════════════════════
    #
    # 백엔드는 설정 파일을 다 바꾼 **뒤** `save_registry`가 실패하면
    # `Refused(code=UNEXPECTED, checkin=관측값)`을 낸다(main.py:861-862 · D-02).
    # 예전 화면은 *"봉투가 ok:false인 것은 시작도 못 한 경우뿐"*이라는 **거짓 전제** 아래
    # 실패 줄 하나만 세우고 체크인을 통째로 버렸다 — 개별 적용(팝업 G)은 같은 갈래를 이미
    # 정확히 읽고 있었으므로, 같은 사실이 화면마다 다르게 취급되던 자리다.
    af = r["applyFailed"]
    if af["blocked"]:
        out.append("R1 일괄 버튼을 누를 수 없었다 — 실패 봉투 갈래를 잴 수 없다(검사 무효)")
    af_by = {l["key"]: l for l in af["lines"]}
    if "result" not in af_by:
        out.append(f"★R1 일괄 적용이 실패했는데 **직전 결과에 아무 기록이 없다**: "
                   f"{keys(af['lines'])} — 확정 실행은 실패해도 곧바로 다시 읽으므로(§4-F ③) "
                   f"현재군의 실패 줄은 다음 조회 성공에 거둬진다(§3-B 수명). 오래 사는 자리는 "
                   f"과거군뿐이고, 거기가 비면 *무슨 일이 있었는지*가 화면에서 사라진다")
    # 10판: 시각이 머리 행으로 올라가 flatten의 앞머리를 차지한다 — 그래서 "무슨 결과인가"는
    #   **헤드라인 자리**에서 읽는다(위치가 아니라 역할로 집는다. `in` 대조로 느슨하게 풀지 않았다).
    elif not (af_by["result"].get("headline") or "").startswith("APPLY_ALL_STOPPED"):
        out.append(f"★R1 실패한 실행의 결과 줄이 「도중에 멈췄다」고 말하지 않는다: "
                   f"{af_by['result']['text']!r}")
    if "checkin" not in af_by or not af_by["checkin"]["text"].startswith("CHECKIN_MANY"):
        out.append(f"★R1 실패 봉투의 **체크인이 침묵한다**: {keys(af['lines'])} — 봉투에 실려 온 "
                   f"체크인 2건은 *직전 프로필이 조용히 바뀐* 사실이다(§5-E)")
    if "why" not in af_by or "UNEXPECTED" not in af_by["why"]["text"]:
        out.append(f"★R1 멈춘 **사유**가 화면에 없다: {keys(af['lines'])} — 코드→문구 단일 관문을 "
                   f"지난 사유가 없으면 사용자가 할 수 있는 일이 없다")
    if af_by.get("result", {}).get("icons") != ["IconWarn"]:
        out.append(f"★R1 실패한 실행인데 결과 아이콘이 경고가 아니다: "
                   f"{af_by.get('result', {}).get('icons')} (D05)")
    if not af_by.get("result", {}).get("stamped"):
        out.append(f"R1 실패한 실행의 결과 줄에 시각이 없다: {af_by.get('result', {}).get('text')!r}")
    if af["overviewCalls"] < 2:
        out.append(f"★R1 일괄 적용이 실패했는데 **현황을 다시 읽지 않았다**(조회 {af['overviewCalls']}회) — "
                   f"엔진은 쓴 뒤에 거부할 수 있어 화면이 낡은 채로 남는다(§4-F ③ 개정)")
    if af["toasts"] != 1:
        out.append(f"R1 실패 결과의 토스트가 {af['toasts']}회다(1회여야 한다) — 성공만 부가 채널로 "
                   f"알리면 *실패가 성공보다 조용한* 비대칭이 생긴다(F20과 같은 형태)")
    if keys(r["applyFailedCarried"]) != ["result", "why", "checkin"]:
        out.append(f"★R1 실패한 실행의 기록이 QAM 재개방을 못 넘는다: {r['applyFailedCarried']}")

    # ═══ C4 조회 보류 중 — 잠금축(문)과 표시축(D14)은 다른 축이다 ═════════════
    #
    # `door.busy`(조회+변이)와 `door.mutating`(변이만)을 한 변수로 쓰면 둘 중 하나가 반드시
    # 거짓말을 한다: `mutating`으로 잠그면 **조회가 도는 중에 쓰기가 시작되고**(방금 읽던 것과
    # 다른 현황 위에서 쓴다 — §4-F가 문을 하나로 합친 이유), `busy`로 표시하면 재조회에까지
    # "적용 중"이라 말한다(D14). 그래서 잠금은 문으로, 표시는 변이로 나눈다.
    qp = r.get("queryPending") or {}
    if qp.get("held") != 1:
        out.append(f"C4 보류 조회를 만들지 못했다(held={qp.get('held')}) — 측정 대상에 못 닿았다"
                   f"(검사 무효)")
    else:
        if qp.get("bulkDisabled") != [True, True]:
            out.append(f"★C4 조회가 도는 중인데 일괄 적용 버튼이 열려 있다: "
                       f"{qp.get('bulkDisabled')} — 지금 누르면 백엔드는 **방금 읽고 있던 것과 다른 "
                       f"현황** 위에서 쓰기를 시작한다. 잠금은 `door.busy`(조회 포함)로 판단한다")
        if qp.get("entryDisabled") != [False, False, False]:
            out.append(f"★C4 조회 때문에 팝업 진입 버튼까지 잠겼다: {qp.get('entryDisabled')} — "
                       f"팝업은 열리자마자 **자기 조회**를 하고 자기 문을 쓴다. QAM의 재조회가 "
                       f"화면 전체를 막으면 사용자는 아무 데도 못 간다")
        if "busy" in (qp.get("keys") or []):
            out.append(f"★C4 조회 왕복인데 상태박스가 진행 중이라 말한다: {qp.get('texts')} — "
                       f"재조회는 사용자가 시킨 일이 아니다. 표시축은 변이(`mutating`)뿐이다(D14)")
        if qp.get("bulkAfter") != [False, False]:
            out.append(f"C4 조회가 끝났는데 일괄 버튼이 잠긴 채다: {qp.get('bulkAfter')}")

    # ═══ R2 조회 **역순 도착** — 낡은 응답은 없던 일이다 ══════════════════════
    for name, snap in (("성공", r["staleOrder"]), ("실패", r["staleFailure"])):
        if snap["loads"] != 2:
            out.append(f"R2 조회가 2회 겹치지 않았다({snap['loads']}) — 측정 대상에 못 닿았다")
            continue
        if "3" not in (snap["afterNew"]["count"] or ""):
            out.append(f"R2 새 응답이 카운트에 반영되지 않았다: {snap['afterNew']['count']!r} "
                       f"(측정 대상에 못 닿았다)")
        if snap["afterStale"]["count"] != snap["afterNew"]["count"]:
            out.append(f"★R2 세대 가드가 없다 — 낡은 {name} 응답이 뒤늦게 도착하자 카운트가 "
                       f"{snap['afterNew']['count']!r} → {snap['afterStale']['count']!r}로 되돌아갔다. "
                       f"팝업 통지·확정 실행 뒤 재조회는 겹치고, 먼저 나간 응답이 나중에 오는 것은 "
                       f"실사용의 흔한 순서다(§4-F ①)")
        if snap["afterStale"]["keys"]:
            out.append(f"★R2 낡은 {name} 응답이 상태박스에 줄을 세웠다: {snap['afterStale']['keys']} — "
                       f"최신 성공 위에 옛 실패가 주황으로 뜨는 자리다")

    seen_fail = []
    for note in r["modalFailure"]:
        want = "POPUP_" + note["label"].replace("OPEN_", "") + "_MODAL_FAILED"
        if not note["lines"] or want not in note["lines"][0]:
            out.append(f"★④ {note['label']} 실패 고지가 그 화면을 가리키지 않는다: "
                       f"{note['lines']} (기대 {want} — F21)")
        seen_fail += note["lines"]
    if len(set(seen_fail)) != 3 and len(seen_fail) == 3:
        out.append(f"④ 세 팝업의 실패 고지가 서로 구별되지 않는다: {seen_fail}")
    if r["modalFailureApplyCalls"]:
        out.append(f"④ 팝업을 못 띄웠는데 적용이 나갔다: {r['modalFailureApplyCalls']}회")
    return out


def main():
    if not U1.is_file():
        # 판정 불가는 통과가 아니라 거부다(QA R7).
        print(f"FAIL — 툴체인 node가 없다: {U1}")
        return 1

    r, err = run_probe()
    if r is None:
        print(f"FAIL — 프로브가 실행되지 않았다: {err}")
        return 1

    bad = violations(r)
    print("QAM 재편 — 상태박스·카운트·설명·배선·확인창 (렌더+클릭으로 측정)")
    print(f"  상태박스 슬롯: 로딩={keys(r['loading']['lines'])} · 정상={keys(r['normal']['lines'])} · "
          f"프로필0={r['noProfiles']['keys']}(box null={r['noProfiles']['boxNull']}) · "
          f"프로필0+실행중={keys(r['noProfilesRunning']['lines'])} · 프로필1={r['oneProfile']['keys']}")
    print(f"  미렌더 조건 3축(프로필 수는 조건이 아니다): 실행중={keys(r['noProfilesRunning']['lines'])} · "
          f"직전결과={keys(r['noProfilesSummary']['lines'])} · 실패={keys(r['noProfilesFailure']['lines'])}")
    print(f"  설명 줄 3갈래: 로딩·조회실패·승계=없음 · 등록0=없음 · "
          f"프로필0={'GUIDE' if has(r['noProfiles']['texts'], 'QAM_ABOUT_GUIDE') else '없음'} · "
          f"프로필1={'ABOUT' if has(r['oneProfile']['texts'], 'QAM_ABOUT') else '없음'} · "
          f"라벨 괄호={label_counts(r['normal']['labels'])}/{label_counts(r['noProfiles']['labels'])}")
    print(f"  결과: 문제 있음={keys(r['resultProblem']['lines'])} / 문제 0={keys(r['resultClean']['lines'])} · "
          f"승계(실패/요약)={keys(r['failureCarried'])}/{keys(r['summaryCarried'])}")
    # ⚠️ 요약 줄은 **측정이 없었던 회차에도 죽지 않는다**(E10과 같은 처분). 상태박스가 통째로
    #   사라지면 `pastOpacity`는 JSON에 실리지 않는데, 예전엔 여기서 KeyError로 죽어
    #   *"무엇이 위반이었나"*가 스택 트레이스로 뭉개졌다 — 판정은 아래 목록이 말해야 한다.
    print(f"  진행: {r['previewing'].get('texts', [])[:1]}→{r['applying'].get('texts', [])[:1]} · "
          f"과거군 투명도 {r['previewing'].get('pastOpacity', '측정없음')}"
          f"→{r['afterBusy'].get('pastOpacity', '측정없음')}")
    print(f"  배선: " + " · ".join(f"{w['label']}→{w['component']}" for w in r["wiring"])
          + f" · 통지 멱등(1→{r['idempotent']['onceCalls']} · 3→{r['idempotent']['thriceCalls']})")
    # 요약 줄도 **측정이 없었던 회차**에 죽지 않는다 — 진단은 판정 목록이 말한다(E10).
    print(f"  확인창: 1차 토큰={(r['confirm'].get('firstCall') or {}).get('token')} · "
          f"2차={(r['confirm'].get('secondCall') or {}).get('token')} · "
          f"본문={[x for x in (r['confirm'].get('confirmTexts') or []) if x.startswith('APPLY_ALL_CONFIRM_BODY')]}")
    if bad:
        print("\nFAIL")
        for b in bad:
            print("  " + b)
        return 1

    # ── 음성 대조군: 알려진 위반이 **그 판정으로** 잡히는가 ────────────────────
    for label, target, pattern, replacement, expect in BYPASSES:
        source = (ROOT / "src" / target).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            case = pathlib.Path(tmp) / "src"
            shutil.copytree(ROOT / "src", case)
            injected, n = re.subn(pattern, replacement, source, count=1)
            if n != 1:
                print(f"FAIL — 음성 대조군 주입 실패({label}): 대상 식을 못 찾았다. 검사가 무효다.")
                return 1
            (case / target).write_text(injected, encoding="utf-8")
            control, err = run_probe(case)
            if control is None:
                print(f"FAIL — 음성 대조군 프로브 실행 실패({label}): {err}")
                return 1
            caught = violations(control)
            hit = [c for c in caught if expect in c]
            if not hit:
                print(f"FAIL — 위반을 주입했는데 **그 판정이** 안 잡았다: {label}")
                print(f"       기대 조각 {expect!r} / 잡힌 것: {caught}")
                return 1
            print(f"  음성 대조군 검출: {label} → {hit[0].splitlines()[0][:100]}")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
