#!/usr/bin/env python3
"""§10-A 확정값 고정 게이트 — 설계가 못 박은 문구를 **바이트로** 잠근다 (P13 게이트 C2).

### 왜 이 검사가 생겼나 — 실제로 뚫려 있던 구멍
설계 `DESIGN-UX-2026-08-11.md` §10-A는 값이 개정된 키를 표로 확정해 두었는데, 검사는
`SAVE_CONFIRM_BODY` **한 키만** 값을 봤다. 나머지는 "누가 반영했겠지"에 맡겨졌고,
U-9 에러 문구 7키가 **미반영인 채 P11·P12·P13 세 단계를 통과했다** — 배선된 UI가 쓰는
키라 실사용 노출까지 있었다. 핸드오프가 "7키 전수가 완료 기준"이라 경고했는데도 그랬다.

왜 다른 검사가 못 잡았나: `test_i18n_sets`는 **키 집합과 자리표시자**를 본다. ko·en이
*함께* 낡으면 두 파일은 서로 완벽히 정합이라 아무 말도 하지 않는다. `test_wording_a5`는
확인창 키군의 **금칙어**를 본다 — 옛 문구가 금칙어를 안 쓰면 역시 초록불이다.
집합만 잠그고 값을 안 잠그면 "설계와 다른 화면"이 영원히 통과한다.

### 구조 — 예외 목록을 만들지 않는다
§10-A가 값을 명시한 키는 **전부** 아래 두 표 중 하나에 있어야 한다. "이건 나중에"라는
면제 목록을 두면 그 목록이 곧 다음 라운드의 누락이 된다(「구조로 예외를 없애라」).

- `LOCKED` — 실물이 §10-A 확정값과 **같아야** 하는 키. 다르면 실패.
- `PINNED`  — 아직 §10-A 값이 아닌 키. **현행 값을 그대로 못 박고** 왜 다른지·어디서
  합류하는지를 같이 적는다. 면제가 아니라 **다른 값으로 잠근 것**이라, 몰래 바뀌면 실패한다.
  `converge`가 적힌 키는 실물이 그 값이 되는 순간 실패한다 — "합류했으니 `LOCKED`로 옮기라"는
  신호다(래칫: 한 번 맞춘 값은 다시 풀리지 않는다).

### 언어
§10-A가 en 값까지 명시한 키만 en을 함께 잠근다(`SAVE_CONFIRM_BODY` + U-9 7키 + `UI_CHECK_FAILED` = 9키).
나머지는 ko만 — 설계가 en 값을 확정하지 않은 자리에 이 검사가 값을 창작하면, 다음에
설계가 확정할 때 **검사가 설계를 막는다.**

### §10-A 표에 **바이트 값이 없는** 행 (여기서 다루지 않는다 — 소관을 적어 둔다)
- `MANAGE_NAMES_HINT 등 "설정" 충돌 문구` → "프로필로 통일" — 대상 키를 열거하지 않은
  **어휘 규칙 행**. 기계 판정은 `test_wording_a5`의 A5 금칙 검사가 한다.
- `POPUP_*_MODAL_FAILED` 3종 — "각 대상명 포함 문구". §10-C의 **잠정** 문구라 값 미확정.

⚠️ **`UI_CHECK_FAILED`는 이 목록에서 나갔다**(2026-08-12 P16 게이트 C3): 8판은 U-9 규율만
넓히고 값을 "구현 확정"으로 남겨 두었는데, 그러면 **같은 규율을 지키는 키 중 이 하나만
안 잠긴다** — 옛 문구("— 로그를 확인하십시오")로 되돌려도 아무 검사가 말하지 않았다.
9판이 §10-A에 ko/en 값을 등재했고(설계가 먼저), 그래서 아래 `LOCKED`로 편입한다(검사가 나중).

### §10-A 행이 늘거나 값이 바뀌면
표에 키를 추가하고 `TOTAL_FIXED`를 **의식적으로** 갱신한다. 상수를 두는 이유는 C3와 같다 —
표에서 한 줄이 조용히 사라져도 검사가 초록불이면 그 검사는 거짓말을 시작한다.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
I18N = ROOT / "src" / "i18n"

SPEC = "DESIGN-UX-2026-08-11.md §10-A"

#: 실물 == §10-A 확정값. 출처는 전부 §10-A 표의 해당 행이다.
LOCKED = {
    # §10-A: `PROFILE_DOCK` / `PROFILE_INTERNAL` → "eGPU" / "내장" (§2-B)
    "PROFILE_DOCK": {"ko": "eGPU"},
    "PROFILE_INTERNAL": {"ko": "내장"},
    # §10-A: `SAVE_SHORT` (A5)
    "SAVE_SHORT": {"ko": "{profile} 프로필 저장"},
    # §10-A: `NO_GAMES` (존재하는 조작 안내)
    "NO_GAMES": {"ko": "등록된 게임이 없습니다 — [게임 감지]에서 추가할 수 있습니다"},
    # §10-A: `SLOT_SAVED_AT` — **개정 철회**, 현행 유지가 확정값이다(F9 + R-8③).
    "SLOT_SAVED_AT": {"ko": "{profile} 저장됨 · {date}"},
    # §10-A: `RESTORE_OK_MANUAL` (F7·탭 소멸)
    "RESTORE_OK_MANUAL": {
        "ko": "{stamp}의 백업으로 되돌렸습니다 — 이 내용은 지금 게임 설정 파일에만 "
              "있습니다. 다음 적용 때는 프로필 내용으로 되돌아갑니다. 계속 쓰려면 이 "
              "게임의 프로필 저장으로 저장하십시오.",
    },
    # §10-A: `BACKUP_KIND_PROFILE` / `BACKUP_KIND_DISK` (F2)
    "BACKUP_KIND_PROFILE": {"ko": "{profile} 프로필에서 밀려난 이전 내용"},
    "BACKUP_KIND_DISK": {"ko": "적용·복원 직전 자동 백업(게임 설정 파일)"},
    # ── QAM 재편(P15-C에서 합류) ──────────────────────────────────────────────
    #    §10-A: `BULK_APPLY`(A5) · `APPLY_ALL_CONFIRM_TITLE`(M8) ·
    #    `APPLY_ALL_CONFIRM_BODY`(§3-E — `{total}`은 preview params 단독 출처) ·
    #    `APPLY_PROBLEM_REFUSED`(F16-ⓑ — `{names}`+NAMES_AND_MORE CAP).
    #    en 값은 §10-A가 확정하지 않아 ko만 잠근다.
    "BULK_APPLY": {"ko": "{profile} 프로필 적용"},
    "APPLY_ALL_CONFIRM_TITLE": {"ko": "「{profile}」 프로필로 일괄 적용할까요?"},
    "APPLY_ALL_CONFIRM_BODY": {
        "ko": "등록된 게임 {total}개를 대상으로 게임 설정 파일을 「{profile}」 "
              "프로필로 갈아끼웁니다.",
    },
    "APPLY_PROBLEM_REFUSED": {
        "ko": "{names} 실행 중이라 적용되지 않았습니다 — 종료 후 다시 눌러 주세요",
    },
    # ── 감지 팝업(P14에서 합류) ────────────────────────────────────────────────
    #    §10-A: `DISCOVER_RESCAN`(L2) · `DISCOVER_ADD_CONFIDENT`·`DISCOVER_BADGE_CONFIDENT`(M3 —
    #    "확신"이라는 내부 용어를 화면에서 걷어낸다). en 값은 §10-A가 확정하지 않아 ko만 잠근다.
    "DISCOVER_RESCAN": {"ko": "다시 검색"},
    "DISCOVER_ADD_CONFIDENT": {"ko": "설정 파일을 찾은 게임 {n}개 모두 추가"},
    "DISCOVER_BADGE_CONFIDENT": {"ko": "설정 파일 확인됨"},
    # §10-A: `SAVE_CONFIRM_BODY` (Codex D-09) — A5 게이트가 기준으로 삼는 문구.
    "SAVE_CONFIRM_BODY": {
        "ko": "이 프로필에 저장돼 있던 이전 내용을 덮어씁니다.",
        "en": "This overwrites what was previously saved in this profile.",
    },
    # ── §10-A 에러 문구 5계열 7키 (U-9 세션 처분 · RECOVERY F19) ─────────────────
    #    공통 규율: "로그를 확인하십시오"류 막다른 길 금지 — 실재 UI 동선만 가리킨다.
    #    A5(프로필을 "설정"이라 부르지 않는다)·A6(재촉 아닌 오류 대응 사실) 준수.
    "UNEXPECTED": {
        "ko": "예기치 못한 오류가 발생했습니다 — 다시 시도해 보십시오. 반복되면 Decky "
              "설정의 플러그인 로그에 원인이 남아 있습니다.",
        "en": "Unexpected error — please try again. If it persists, the cause is "
              "recorded in the plugin log under Decky settings.",
    },
    "REGISTRY_UNREADABLE": {
        "ko": "플러그인의 게임 목록을 읽지 못했습니다 — 플러그인을 껐다 켜서 다시 시도해 "
              "보십시오. 계속되면 목록 파일이 손상된 것입니다. 저장된 프로필과 백업은 "
              "그대로 남아 있고, 직전 목록의 자동 백업도 함께 저장돼 있습니다.",
        "en": "Couldn't read the plugin's game list — toggle the plugin off and on to "
              "retry. If this persists the list file is damaged. Your saved profiles "
              "and backups are intact, and an automatic backup of the previous list is "
              "kept alongside it.",
    },
    "REGISTRY_MALFORMED": {
        "ko": "플러그인의 게임 목록이 손상되었습니다. 저장된 프로필과 백업은 그대로 남아 "
              "있고, 직전 목록의 자동 백업도 함께 저장돼 있습니다.",
        "en": "The plugin's game list is damaged. Your saved profiles and backups are "
              "intact, and an automatic backup of the previous list is kept alongside it.",
    },
    "PROFILE_CORRUPT": {
        "ko": "저장된 프로필이 기록된 정보와 어긋나 손상됐을 수 있습니다 — 이 게임의 "
              "프로필 저장으로 다시 저장하거나, [백업 복원]에서 이전 내용을 되살릴 수 "
              "있습니다.",
        "en": "This saved profile doesn't match its records and may be damaged — save "
              "the profile again for this game, or bring back an earlier version from "
              "[Restore backup].",
    },
    "SIZE_OUT_OF_RANGE": {
        "ko": "설정 파일 크기가 저장 당시 기준과 너무 달라 아무것도 바꾸지 않고 "
              "멈췄습니다 — 게임 업데이트로 파일이 크게 바뀌었을 수 있습니다. 게임에서 "
              "설정을 확인한 뒤 프로필을 다시 저장하면 새 기준으로 갱신됩니다.",
        "en": "The config file's size differs too much from when the profile was saved, "
              "so nothing was changed — a game update may have restructured it. Check "
              "your settings in-game, then save the profile again to refresh the baseline.",
    },
    "LINE_COUNT_OUT_OF_RANGE": {
        "ko": "설정 파일 줄 수가 저장 당시 기준과 너무 달라 아무것도 바꾸지 않고 "
              "멈췄습니다 — 게임 업데이트로 파일이 크게 바뀌었을 수 있습니다. 게임에서 "
              "설정을 확인한 뒤 프로필을 다시 저장하면 새 기준으로 갱신됩니다.",
        "en": "The config file's line count differs too much from when the profile was "
              "saved, so nothing was changed — a game update may have restructured it. "
              "Check your settings in-game, then save the profile again to refresh the "
              "baseline.",
    },
    "CONFIG_MISSING": {
        "ko": "게임의 설정 파일이 없습니다 — 게임을 한 번 실행해 그래픽 설정을 열면 "
              "만들어지는 경우가 대부분입니다. 그래도 없으면 [게임 감지]에서 파일을 "
              "다시 골라 등록할 수 있습니다.",
        "en": "The game's config file doesn't exist — running the game once and opening "
              "its graphics settings usually creates it. If it still doesn't appear, "
              "pick the file again from [Detect games].",
    },
    # ── 8판(P16 문서 마감)에서 §10-A 셀이 실물로 정정되며 합류한 4키 ──────────────
    #    셋(RESTORE_FOLLOWUP_MODAL_FAILED·DELETE_CONFIRM_TITLE·DELETE_OK)은 **구현이
    #    설계 셀보다 앞서 있던** 자리다 — P13·P15에서 "되돌리지 말고 문서를 고친다"로
    #    판정하고 P16 마감에 셀을 정정했다(설계 §10-A + 「」 관례 절). 이제 두 쪽이 같으므로
    #    PINNED(다른 값으로 잠금)에 남을 이유가 없다 — 래칫대로 LOCKED로 옮긴다.
    #    `RESET_OK`는 반대 방향이다: P16 E4로 **값 자체를 고쳤고**(0을 그리지 않는다),
    #    §10-A 셀도 그 값으로 확정됐다. en은 §10-A가 확정하지 않아 ko만 잠근다.
    "RESTORE_FOLLOWUP_MODAL_FAILED": {
        "ko": "게임 설정 파일은 되돌렸습니다. 다만 프로필에도 저장할지 묻는 창을 표시하지 "
              "못했습니다 — 이 게임의 프로필 저장으로 저장하십시오.",
    },
    "DELETE_CONFIRM_TITLE": {"ko": "「{name}」의 등록을 해제할까요?"},
    "DELETE_OK": {"ko": "「{name}」의 등록을 해제했습니다"},
    "RESET_OK": {"ko": "초기화 완료 — {deleted}개 삭제"},
    # ── 9판에서 §10-A가 값을 확정하며 합류한 1키(P16 게이트 C3) ─────────────────
    #    U-9 7키와 **같은 규율**을 지키는 문구인데 8판까지 값이 미확정이라 혼자 안 잠겨
    #    있었다. en까지 §10-A가 명시하므로 두 언어를 함께 잠근다.
    "UI_CHECK_FAILED": {
        "ko": "화면 구성 요소를 찾지 못했습니다 ({missing}) — 플러그인을 껐다 켜서 다시 "
              "시도해 보십시오. 계속되면 Decky 설정의 플러그인 로그에 원인이 남아 있습니다.",
        "en": "Some UI components were not found ({missing}) — toggle the plugin off and on "
              "to retry. If it persists, the cause is recorded in the plugin log under "
              "Decky settings.",
    },
    # ── 10판에서 §10-A가 값을 확정하며 합류한 5키 (D5 치환자 조사 4 + §7 중복 정리 1) ────
    #    앞의 넷은 **조사를 안 쓰는 문형으로 갈아탄** 자리다(§10-E). 문법 판정은
    #    `test_wording_particles`가 상시로 하고, 이 표는 **그 결과 문구가 무엇인지**를 잠근다 —
    #    소관이 다르다: 저쪽은 "이형태 조사가 붙었나", 여기는 "설계가 정한 그 문장인가".
    #    조사 규칙만 잠그면 규칙을 지키는 아무 문장으로나 바뀌어도 초록불이다.
    #    en 값은 §10-A가 확정하지 않아(권고·비잠금) ko만 잠근다 — 기존 관례.
    #
    # ① `APPLY_SUMMARY` — "{profile}로"가 실기에서 "내장로"를 그렸다(D5 실물 그 자리).
    #    부수 이득: "전환"은 A5 용어 계열 밖의 어휘였다. 이제 일괄 버튼(`BULK_APPLY`)과
    #    결과 줄이 **같은 동사**를 쓴다 — 누른 것과 보고된 것의 어휘가 일치한다.
    #    성패를 문장이 단정하지 않는 명사구인 이유: 성패는 아이콘(D05)이 말하므로
    #    문제 행이 있는 결과에서도 이 헤드라인은 참이다.
    "APPLY_SUMMARY": {"ko": "{profile} 프로필 적용 — 전체 {total}개 중 {applied}개 변경"},
    # ② `SAVE_GUIDE` — **잠복 결함**이었다. 기본 표시명("eGPU"·"내장")에서는 우연히 맞아
    #    실기에서 드러나지 않지만, 사용자가 이름을 바꾸면(F11 — "독"·"iGPU"류) 그날 틀린다.
    #    "{dock}를"→"{dock} 연결 상태에서"(조사 소거) · "{internal}으로 쓸"→"{internal}일 때 쓸"
    #    (계사 "일"은 이형태가 없다). 두 "[… 프로필 저장]을"은 대괄호 버튼명 뒤라 비접촉.
    "SAVE_GUIDE": {
        "ko": "{dock} 연결 상태에서 게임의 그래픽 옵션을 맞춘 뒤 [{dock} 프로필 저장]을, "
              "{internal}일 때 쓸 그래픽 옵션을 맞춘 뒤 [{internal} 프로필 저장]을 누릅니다.",
    },
    # ③ `APPLY_ONE_OK` — 병기형("eGPU을(를)")은 틀린 건 아니나 표시가 거칠었다.
    #    조사를 불변 명사 '프로필'에 붙이는 권장 정본 문형(§10-E ⓒ)으로 공짜 해소.
    #    `CHECKIN_ONE`("… {profile} 프로필에 …")과 문형이 맞는다.
    "APPLY_ONE_OK": {"ko": "{profile} 프로필을 적용했습니다"},
    # ④ `RESET_CONFIRM_TYPE` — 초안 1판의 **손 전수 점검이 놓쳤던 키**(기계 게이트가 필요한
    #    이유의 실증). {word}는 백엔드 고정 상수 "delete"(비번역 계약)라 오독 위험은 사실상
    #    없었지만, 무예외 원칙을 세운 게이트가 자기 자신을 예외로 두면 원칙이 무너진다.
    #    치환자를 문미로 보내 조사는 불변 명사 '단어'에 붙인다 — 바로 아래가 입력창이라
    #    문미 제시가 시선 흐름과도 맞는다.
    "RESET_CONFIRM_TYPE": {"ko": "확인하려면 아래에 다음 단어를 입력하십시오: {word}"},
    # ⑤ `RESET_ZONE_BODY` — 조사 건이 아니라 **§7 중복 정리**의 몫이다(E절).
    #    설정 화면에서 "백업은 남습니다."를 이 줄과 `RESET_HINT`가 **둘 다** 말하고 있었다.
    #    "각 사실은 정확히 한 번만" 원칙에 따라 백업 잔존은 `RESET_HINT`가 전담하고
    #    이 줄은 파괴 내역만 말한다(`RESET_HINT`는 무변경).
    "RESET_ZONE_BODY": {"ko": "전체 초기화 — 등록 {n}개와 저장된 프로필을 모두 지웁니다."},
}

#: 아직 §10-A 값이 아닌 키 — **현행 값으로 잠근다**. `converge`가 있으면 그 값에 도달하는
#: 순간 실패한다(= LOCKED로 옮기라는 신호). 없으면 §10-A 셀 표기가 실물보다 낡았다는 뜻이고,
#: 어느 쪽을 고칠지는 `note`가 가리키는 자리에서 판단한다.
PINNED: dict = {
    # ⚠️ **지금은 비어 있다 — 래칫이 전부 합류했다**(P16 문서 마감).
    #    이력: QAM 4키는 P15-C에서, 감지 팝업 3키는 P14에서 §10-A 값에 도달해 LOCKED로 옮겼고,
    #    남아 있던 3키(RESTORE_FOLLOWUP_MODAL_FAILED·DELETE_CONFIRM_TITLE·DELETE_OK)는
    #    **문서 쪽이 낡은 경우**라 8판에서 §10-A 셀을 실물로 정정하고 함께 LOCKED로 옮겼다.
    #    비어 있음은 "잠글 것이 없다"가 아니라 **설계와 실물이 전부 붙었다**는 뜻이다.
    #    다음에 설계 셀과 실물이 갈리는 키가 생기면 여기에 현행 값으로 못 박고(면제가 아니다)
    #    `note`에 왜 다른지·어디서 합류하는지를 적는다.
}

#: 두 표의 합 — §10-A에서 바이트 값을 뽑아낼 수 있는 키의 전수. 표를 늘리거나 줄이면
#: 이 숫자를 **의식적으로** 갱신하라. 하한(>=)이 아니라 등호인 이유: 한 줄이 조용히
#: 사라져도 통과하는 검사는 검사가 아니다(P13 게이트 C3와 같은 판단).
#: ⚠️ 산정 전제: `TOTAL_FIXED = len(LOCKED) + len(PINNED)`이고 **현재 PINNED는 0**이라
#:   "LOCKED 33"과 "TOTAL 33"이 우연히 같은 수다. PINNED가 다시 생기는 날 두 수는 갈라진다 —
#:   개념을 뭉쳐 기억하지 말 것(10판 초안 2판 지적 4).
#:   28 → 33 (10판: D절 4행 + E절 `RESET_ZONE_BODY` 1행)
TOTAL_FIXED = 33


def diff_at(expected, actual):
    """첫 불일치 지점을 사람이 읽을 수 있게. 공백·대시 한 글자 차이가 눈으로는 안 보인다."""
    if actual is None:
        return "키 자체가 없다"
    n = min(len(expected), len(actual))
    for i in range(n):
        if expected[i] != actual[i]:
            return (f"{i}번째 글자부터 다르다 — 기대 {expected[i]!r}"
                    f"(U+{ord(expected[i]):04X}) / 실제 {actual[i]!r}"
                    f"(U+{ord(actual[i]):04X})\n"
                    f"        …{expected[max(0, i - 12):i + 12]!r}\n"
                    f"        …{actual[max(0, i - 12):i + 12]!r}")
    if len(expected) != len(actual):
        longer, who = (actual[n:], "실제") if len(actual) > n else (expected[n:], "기대")
        return f"{n}글자까지 같고 {who} 쪽에 {longer!r}가 더 붙어 있다"
    return "차이 없음"


def main():
    problems = []
    tables = {}
    for lang in ("ko", "en"):
        path = I18N / f"{lang}.json"
        if not path.is_file():
            print(f"FAIL: {path} 없음")
            return 1
        tables[lang] = json.loads(path.read_text(encoding="utf-8"))

    overlap = set(LOCKED) & set(PINNED)
    if overlap:
        problems.append(f"★같은 키가 두 표에 있다 — 어느 쪽이 진짜인지 알 수 없다: "
                        f"{sorted(overlap)}")

    total = len(LOCKED) + len(PINNED)
    if total != TOTAL_FIXED:
        problems.append(
            f"★고정 키가 {total}개다(선언 {TOTAL_FIXED}개) — §10-A 표에서 행이 늘거나 "
            f"줄었다면 TOTAL_FIXED를 의식적으로 갱신하라. 검사 범위가 조용히 줄어드는 "
            f"경로를 막는 상수다")

    langs_checked = 0
    for key, spec in LOCKED.items():
        for lang in ("ko", "en"):
            if lang not in spec:
                continue
            langs_checked += 1
            actual = tables[lang].get(key)
            if actual != spec[lang]:
                problems.append(
                    f"★{key}({lang})가 {SPEC} 확정값이 아니다 — {diff_at(spec[lang], actual)}\n"
                    f"      기대: {spec[lang]}\n      실제: {actual}")

    for key, spec in PINNED.items():
        langs_checked += 1
        actual = tables["ko"].get(key)
        converge = spec.get("converge")
        if converge is not None and actual == converge:
            problems.append(
                f"★{key}(ko)가 {SPEC} 값에 도달했다 — 표를 옮길 차례다: PINNED에서 "
                f"지우고 LOCKED에 확정값으로 넣어라(그래야 다시 낡지 않는다)\n"
                f"      사유였던 것: {spec['note']}")
        elif actual != spec["ko"]:
            problems.append(
                f"★{key}(ko)가 못 박은 현행 값과 다르다 — {diff_at(spec['ko'], actual)}\n"
                f"      못 박은 값: {spec['ko']}\n      실제: {actual}\n"
                f"      (이 키를 왜 아직 안 바꾸는가: {spec['note']})\n"
                f"      {SPEC} 값으로 가려던 것이면 LOCKED로 옮겨 잠가라")

    missing = [k for k in list(LOCKED) + list(PINNED) if k not in tables["ko"]]
    if missing:
        problems.append(f"★i18n에 없는 키를 잠그고 있다(이름이 바뀌었나?): {missing}")

    print(f"§10-A 확정값 고정 게이트 — 고정 {total}키 "
          f"(LOCKED {len(LOCKED)} · PINNED {len(PINNED)}) · 값 대조 {langs_checked}건")
    print(f"  en까지 고정: {sorted(k for k, v in LOCKED.items() if 'en' in v)}")
    print(f"  합류 대기(converge): "
          f"{sorted(k for k, v in PINNED.items() if 'converge' in v)}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
