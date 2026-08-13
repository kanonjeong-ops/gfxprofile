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

### 언어 — **12판에서 잠금 범위가 9키 → 32키로 넓어졌다**
§10-A가 en 값까지 명시한 키만 en을 함께 잠근다. 11판까지는 9키였다(`SAVE_CONFIRM_BODY` +
U-9 7키 + `UI_CHECK_FAILED`). 12판은 **§10-A 표에 en 열을 신설해 개정 대상의 en 바이트를
전량 확정했다** — 이번 개정의 절반이 *ko/en 의미 불일치*(사실성 22번·큐 7번)를 고치는 일이라,
ko만 잠그면 같은 종류의 어긋남이 en에 남아 다음 점검이 또 적발한다. `RESET_CONFIRM_WARN`의
`⚠ ` 접두도 ko에만 복원하면 en 화면에서 표식이 사라진다.
산식: 9 + 사실성 순증 17(20키 중 3키는 이미 en 잠금) + 큐 en 확정 6 = **32**.
**예외 2키**(`QAM_ABOUT_GUIDE`·`BULK_NO_GAMES`)는 설계가 en을 권고·비잠금으로 남겨 ko만 잠근다 —
설계가 en 값을 확정하지 않은 자리에 이 검사가 값을 창작하면, 다음에 설계가 확정할 때
**검사가 설계를 막는다.**

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
    # §10-A: `RESTORE_OK_MANUAL` (F7·탭 소멸 → **12판 사실성 16**: 프로필이 하나도 없거나
    #   다시 적용하지 않는 사용자에게 "다음 적용 때는 되돌아갑니다"는 일어나지 않을 일의 단언이라
    #   조건절로 내렸다. "결과까지 명시"(F7)는 유지된다.
    "RESTORE_OK_MANUAL": {
        "ko": "게임 설정 파일을 {stamp}의 백업으로 되돌렸습니다. 나중에 저장된 프로필을 "
              "적용하면 게임 설정 파일은 그 프로필 내용으로 바뀝니다. 복원한 내용을 "
              "프로필로 보관하려면 이 게임의 프로필로 저장해 주세요.",
        "en": "Restored the game's settings file from the {stamp} backup. If you later "
              "apply a saved profile, the game's settings file will change to that "
              "profile's content. To keep the restored content as a profile, save it as "
              "a profile for this game.",
    },
    # §10-A: `BACKUP_KIND_PROFILE` / `BACKUP_KIND_DISK` (F2 → **12판 사실성 15**: 이 백업은
    #   덮어쓰기·등록 해제·초기화 **세 경로**에서 만들어지는데 "밀려난"은 그중 하나만 참이라
    #   라벨이 경위를 단언하면 나머지 두 경로에서 거짓이 된다. **라벨은 종류만, 사건은
    #   `BACKUP_LIST_ORDER_HINT`가** — F2의 "사용자 사건 언어" 취지는 그 줄이 계속 전담한다.
    "BACKUP_KIND_PROFILE": {"ko": "{profile} 프로필 백업", "en": "{profile} profile backup"},
    "BACKUP_KIND_DISK": {"ko": "적용·복원 직전 자동 백업(게임 설정 파일)"},
    # ── QAM 재편(P15-C에서 합류) ──────────────────────────────────────────────
    #    §10-A: `BULK_APPLY`(A5) · `APPLY_ALL_CONFIRM_TITLE`(M8) ·
    #    `APPLY_ALL_CONFIRM_BODY`(§3-E — `{total}`은 preview params 단독 출처) ·
    #    `APPLY_PROBLEM_REFUSED`(F16-ⓑ — `{names}`+NAMES_AND_MORE CAP).
    #    en 값은 §10-A가 확정하지 않아 ko만 잠근다.
    "BULK_APPLY": {"ko": "{profile} 프로필 적용"},
    "APPLY_ALL_CONFIRM_TITLE": {"ko": "「{profile}」 프로필로 일괄 적용할까요?"},
    #    ⚠️ 12판(사실성 7): 등록 게임 **전부**의 파일을 교체한다는 단언이 실물과 다르다 —
    #       프로필 없음·실행 중·이미 동일은 교체되지 않는다. 5버킷 미리보기와 같은 사실을
    #       본문이 말하게 맞췄다(`{total}`의 출처 계약은 불변).
    "APPLY_ALL_CONFIRM_BODY": {
        "ko": "등록된 게임 {total}개의 상태를 확인하고, 적용할 수 있으며 변경이 필요한 "
              "게임에 「{profile}」 프로필을 적용합니다.",
        "en": "Checks the state of {total} registered game(s) and applies the "
              "“{profile}” profile where it can be applied and would make a change.",
    },
    "APPLY_PROBLEM_REFUSED": {
        "ko": "{names} 실행 중이라 적용되지 않았습니다 — 종료 후 다시 눌러 주세요",
    },
    # ── 감지 팝업(P14에서 합류) ────────────────────────────────────────────────
    #    §10-A: `DISCOVER_RESCAN`(L2) · `DISCOVER_ADD_CONFIDENT`·`DISCOVER_BADGE_CONFIDENT`(M3 —
    #    "확신"이라는 내부 용어를 화면에서 걷어낸다). en 값은 §10-A가 확정하지 않아 ko만 잠근다.
    #    ⚠️ `DISCOVER_BADGE_CONFIDENT`는 12판(사실성 5)에서 값이 바뀌고 **en도 함께 잠긴다**:
    #       휴리스틱 후보를 *검증 완료된 설정 파일*로 단언하지 않는다. 배지 3종의 대비도
    #       선명해진다(등록됨 / 자동 선택 후보 / 후보 N개). 근거의 **종류**는 등급 라벨
    #       `DISCOVER_TIER1~3`이 따로 말하므로 중복이 아니다.
    "DISCOVER_RESCAN": {"ko": "다시 검색"},
    "DISCOVER_ADD_CONFIDENT": {"ko": "설정 파일을 찾은 게임 {n}개 모두 추가"},
    "DISCOVER_BADGE_CONFIDENT": {"ko": "자동 선택 후보", "en": "Auto-selection candidate"},
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
    #    ⚠️ 12판(사실성 10): 두 키의 11판 값은 **"직전 목록의 자동 백업이 함께 저장돼 있다"**를
    #       근거로 들었는데 그 `.bak`은 항상 있지는 않다. 신 사유 = 유일한 UI 내 조치(재시도) +
    #       **이 실패가 프로필·백업을 바꾸지 않았다는 사실**로 최악의 공포를 차단한다.
    #       UI 밖 복구 경로는 말하지 않는다(존재가 보장되지 않는다).
    "REGISTRY_UNREADABLE": {
        "ko": "플러그인의 게임 목록을 읽지 못했습니다. 플러그인을 껐다 켠 뒤 다시 시도해 "
              "주세요. 계속되면 게임 목록 파일이 손상됐을 수 있습니다. 프로필과 백업은 "
              "바뀌지 않았습니다.",
        "en": "The plugin's game list could not be read. Toggle the plugin off and on, "
              "then please try again. If this continues, the game-list file may be "
              "damaged. Profiles and backups were not changed.",
    },
    "REGISTRY_MALFORMED": {
        "ko": "플러그인의 게임 목록 형식이 올바르지 않습니다. 프로필과 백업은 바뀌지 "
              "않았습니다.",
        "en": "The plugin's game list has an invalid format. Profiles and backups were "
              "not changed.",
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
    #    ⚠️ 12판(사실성 8): 재감지만으로는 안 되고 **먼저 등록을 해제해야** 동선이 통한다.
    #       en의 화면 이름은 **실재하는 라벨**과 같아야 한다 — 개정안 원문의
    #       `[Per-game apply/save]`는 존재하지 않는 이름이라 `OPEN_GAMES`·`GAMES_TITLE`의
    #       실물 "Apply / save per game"으로 맞췄다(없는 이름을 가리키는 안내는 사실성
    #       수정이 고치려던 바로 그 종류의 결함이다).
    "CONFIG_MISSING": {
        "ko": "게임의 설정 파일이 없습니다. 게임을 실행해 그래픽 설정을 열면 파일이 "
              "만들어질 수 있습니다. 그래도 없으면 [게임별 적용/저장]에서 먼저 이 게임의 "
              "등록을 해제한 뒤, [게임 감지]에서 파일을 다시 골라 등록해 주세요.",
        "en": "The game's config file does not exist. Running the game and opening its "
              "graphics settings may create it. If it still does not appear, first "
              "unregister this game in [Apply / save per game], then pick the file "
              "again in [Detect games].",
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
    #    ⚠️ 12판(큐 6 — 어법 통일): ko만 "…시도해 **주세요**"로 바뀐다. en은 **무변경**이다 —
    #       어법 문제는 ko에만 있었고, 고칠 것이 없는 자리를 건드리면 잠금이 값을 창작한다.
    "UI_CHECK_FAILED": {
        "ko": "화면 구성 요소를 찾지 못했습니다 ({missing}) — 플러그인을 껐다 켜서 다시 "
              "시도해 주세요. 계속되면 Decky 설정의 플러그인 로그에 원인이 남아 있습니다.",
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
    # ② `SAVE_GUIDE`는 **12판에서 키째 사라졌다** → `SAVE_GUIDE_DOCK`/`SAVE_GUIDE_INTERNAL`
    #    2키로 분할(§5-B·§10-A). 신설 키 블록에 값이 있다.
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
    # ══ 12판에서 §10-A가 값을 확정하며 합류한 21키 ═══════════════════════════════
    #
    # ★ **en 잠금 범위가 여기서 바뀐다**(11판 관례 변경): 아래 키 중 §10-A가 en 바이트를 적은
    #   것은 en도 함께 잠근다. 이번 개정의 절반이 *ko/en 의미 불일치*를 고치는 일이라, ko만
    #   잠그면 같은 종류의 어긋남이 en에 남아 다음 점검이 또 적발한다.
    #   **예외 2키**(`QAM_ABOUT_GUIDE`·`BULK_NO_GAMES`)는 설계가 en을 권고·미확정으로 남겼으므로
    #   ko만 잠근다 — 설계가 확정하지 않은 자리에 검사가 값을 창작하면 안 된다(머리말 「언어」).
    #
    # ── ① 저장 안내 2줄(§5-B — 구 `SAVE_GUIDE` 분할) ──────────────────────────────
    #    키를 나눈 이유: ⓐ 한 키에 두 문장이라 렌더에서 줄이 안 나뉜다(값에 개행을 넣어도
    #    `white-space` 미지정이라 이어붙는다) ⓑ "{dock} **연결 상태에서**"는 표시명이 사용자
    #    지정 가능하다는 사실과 충돌한다(F11 — "「고성능」 연결 상태에서"는 성립하지 않는다.
    #    이름은 프로필의 이름이지 연결 상태의 이름이 아니다) ⓒ ko 안에서 앞·뒤 대구가 어긋나 있었다
    #    ⓓ ko/en 의미 불일치(en은 원래 "for {dock}"라 연결 상태를 전제하지 않았다).
    #    ★ **핵심은 "게임을 종료하고"다**: 게임은 종료할 때 설정 파일을 다시 쓰므로, 실행 중에
    #      저장하면 디스크에 남은 옛 값이 저장될 수 있다. 11판까지 그 경고는 저장 버튼을 누르려는
    #      **순간에야** 떴다(`SAVE_DESC_RUNNING` — 그것은 그대로 둔다. 사후 방어와 사전 안내는
    #      소관이 다르다).
    #    ⚠️ **구 `SAVE_GUIDE`의 잠복 결함 경고는 두 키가 그대로 물려받는다**: 조사 문제는 기본
    #      표시명("eGPU"·"내장")에서는 **우연히 맞아** 실기에서 드러나지 않고, 사용자가 이름을
    #      바꾸는 날(F11 — "독"·"iGPU"류) 그날 틀린다. `{dock}용`·`{internal}용`의 "용"은
    #      이형태가 없는 불변 접미라 어떤 이름에도 안 틀린다(§10-E).
    #      소관 분리: **문법**("이형태 조사가 붙었나")은 `test_wording_particles`가 상시로 보고,
    #      **값**("설계가 정한 그 문장인가")은 여기가 본다. 한쪽만 있으면 규칙을 지키는 아무
    #      문장으로나 바뀌어도(저쪽) 또는 규칙을 어겨도(이쪽) 초록불이다.
    "SAVE_GUIDE_DOCK": {
        "ko": "게임에서 {dock}용 그래픽 옵션을 맞춘 뒤, 게임을 종료하고 "
              "[{dock} 프로필 저장]을 눌러 주세요.",
        "en": "Set the game's graphics options for {dock}, close the game, then press "
              "[Save {dock} profile].",
    },
    "SAVE_GUIDE_INTERNAL": {
        "ko": "게임에서 {internal}용 그래픽 옵션을 맞춘 뒤, 게임을 종료하고 "
              "[{internal} 프로필 저장]을 눌러 주세요.",
        "en": "Set the game's graphics options for {internal}, close the game, then "
              "press [Save {internal} profile].",
    },
    # ── ② QAM 재편 6키(§3-A·§3-C·§3-D — §10-C 잠정에서 §10-A 확정으로 승격) ──────
    #    `QAM_ABOUT`이 "적용합니다"가 아니라 **"대상으로 합니다"**인 이유: 실행 중인 게임은
    #    대상이면서도 거부되므로 "적용한다"는 단언이 거짓이 될 수 있다.
    #    `QAM_ABOUT_GUIDE`는 ko/en **동시에** 치환자 0이다(11판 값의 `{dock}`·`{internal}` 소멸) —
    #    함께 잃으므로 비대칭이 아니고 `test_i18n_sets`와 무저촉이다.
    #    `COUNT_SUMMARY`는 **분모를 문장 앞으로** 뺐다: `3/10`의 `10`이 등록 게임 수라는 사실이
    #    화면 어디에도 없었다. D03(의미 라벨 부착)은 그대로 유효하다 — "프로필 저장:"이 그 라벨이다.
    "QAM_ABOUT": {
        "ko": "프로필 적용 버튼은 해당 프로필이 저장된 게임만 대상으로 합니다.",
        "en": "Each profile button targets only games with that profile saved.",
    },
    "QAM_ABOUT_GUIDE": {"ko": "[게임별 적용/저장]에서 게임별 그래픽 설정을 저장할 수 있습니다."},
    "COUNT_SUMMARY": {
        "ko": "게임 {total}개 등록 · 프로필 저장: {dock} {dock_ready} · "
              "{internal} {internal_ready}",
        "en": "Registered: {total} · Profiles saved: {dock} {dock_ready} · "
              "{internal} {internal_ready}",
    },
    # "거부"는 도구가 사용자를 물리치는 어감이나 실제 동작은 건너뛰기다(큐 6).
    "BULK_RUNNING_NOTE": {
        "ko": "실행 중인 게임 {n}개는 건너뜁니다 — 나머지는 적용됩니다",
        "en": "{n} running game(s) are skipped — the rest are applied",
    },
    # 명사구 3겹 난독 해소(큐 6). **"게임 설정 파일"은 남긴다**(A5 — 소유자 명시).
    "CHECKIN_MANY": {
        "ko": "{n}개는 바꾸기 전 게임 설정 파일 내용을 직전 프로필에 저장했습니다",
        "en": "For {n} game(s), the settings file content before the change was saved "
              "into the previous profile",
    },
    # 사유 줄 새 규칙(§3-A ⓑ)의 유일한 문구. 갈 곳 안내는 카운트 줄 `NO_GAMES`가 전담한다.
    "BULK_NO_GAMES": {"ko": "적용할 게임이 없습니다"},
    # ── ③ 사실성 점검 채택분 13키(§16-⑯ 표의 번호를 사유로 적는다) ────────────────
    "SAV_REFUSED": {                                                        # 1
        "ko": "확장자가 「.sav」인 파일과 이름이 「savegames」인 폴더 안의 파일은 "
              "등록할 수 없습니다(대소문자 구분 없음).",
        "en": "Files with a “.sav” extension and files inside a folder named "
              "“savegames” cannot be registered (case-insensitive).",
    },
    "BACKUP_FAILED": {                                                      # 2
        "ko": "백업에 실패해 작업을 중단했습니다. 프로필 적용 중이었다면 적용 전 게임 "
              "설정 파일 내용이 직전 프로필에 이미 저장됐을 수 있습니다.",
        "en": "The operation stopped because the backup failed. If this happened while "
              "applying a profile, the pre-apply contents of the game's settings file "
              "may already have been saved to the previous profile.",
    },
    # 3·4 — `{profiles}`가 *인식 가능한 기록 수*임을 밝히고, 집계되지 않은 슬롯 데이터도
    #       지워질 수 있음과 링(BACKUP_KEEP) pruning 가능성을 더한다. F23(재등록 전제 명시)은
    #       마지막 문장이 그대로 들고 간다.
    # ⚠️ `⚠ ` 접두는 **ko·en 양쪽**에 유지한다: A8이 인정한 유일한 위험 표식이 이 문자열 안에
    #    있고 `confirmSpecs.tsx`의 warnBlock은 별도 아이콘을 그리지 않는다. ko에만 복원하면
    #    en 화면에서 표식이 사라진다.
    "RESET_CONFIRM_WARN": {                                                 # 3·4
        "ko": "⚠ 초기화는 등록 기록 {games}개와 플러그인이 인식할 수 있는 프로필 기록 "
              "{profiles}개를 삭제 대상으로 삼습니다. 이 수에 포함되지 않은 프로필 "
              "데이터도 삭제될 수 있습니다. 백업 폴더는 남지만 프로필 데이터를 옮겨 두는 "
              "동안 오래된 백업이 밀려날 수 있습니다. 백업 내용을 되살리려면 게임을 다시 "
              "등록한 뒤 복원해 주세요.",
        "en": "⚠ Reset targets {games} registration record(s) and {profiles} profile "
              "record(s) the plugin can recognize for deletion. Profile data not "
              "included in these counts may also be deleted. Backup folders remain, but "
              "older backups may be pushed out while profile data is moved. To recover "
              "backup content, register the game again and then restore it.",
    },
    # 10판은 `RESET_HINT`를 무변경으로 두었는데 그 값("백업은 남고")은 **백업 폴더 보존과 백업
    # 항목 전량 보존을 구분하지 않았다** — 초기화는 프로필 데이터를 백업으로 대피시키므로 링이
    # 밀려 오래된 백업이 사라질 수 있다. 전담 소관(§7-6)은 그대로이고 전담하는 사실이 정확해졌다.
    "RESET_HINT": {                                                         # 4
        "ko": "백업 폴더는 남지만 프로필 데이터를 옮겨 두는 동안 오래된 백업이 밀려날 수 "
              "있습니다. 게임 설정 파일 원본은 건드리지 않습니다.",
        "en": "Backup folders remain, but older backups may be pushed out while profile "
              "data is moved. The original game settings files are not touched.",
    },
    "APPLY_ALL_UNCHANGED": {                                                # 6
        "ko": "{profile} — 바뀐 게임 설정 파일이 없습니다",
        "en": "{profile} — no game settings files changed",
    },
    "SAVE_CONFIRM_BACKUP_LIMIT": {                                          # 9
        "ko": "이전 프로필 파일을 읽을 수 있는 경우에만 백업을 만듭니다. 만들어진 백업은 "
              "이 게임을 {n}번쯤 더 적용하면 목록에서 밀려 사라질 수 있습니다.",
        "en": "A backup is created only if the previous profile file can be read. Any "
              "backup created may drop off the list after roughly {n} more applies for "
              "this game.",
    },
    "BACKUP_OUT_OF_ROOT": {                                                 # 12
        "ko": "이 게임의 프로필 또는 백업 데이터 경로가 제자리에 있지 않습니다.",
        "en": "This game's profile or backup data path is not in its expected location.",
    },
    # 13 — "다시 하면 이어서 지운다"는 약속을 뺐다: 삭제 **전** 거부 갈래에서 거짓이기 때문이다.
    #      ⚠️ `RESET_LEFT_NOTE`의 같은 약속은 초기화 route가 실제로 남은 것부터 재시도하는
    #        구조라 참이므로 **값이 유지된다** — 두 키는 이제 같은 문법을 공유하지 않는다.
    "DELETE_FAILED": {                                                      # 13
        "ko": "등록 해제를 완료하지 못했습니다. 프로필 데이터가 이미 일부 또는 전부 "
              "지워졌을 수 있습니다.",
        "en": "Unregistering could not be completed. Some or all profile data may "
              "already have been deleted.",
    },
    # 17 — 11판 값은 ⓐ "설정"을 소유자 없이 써 A5에 저촉(실물은 이미 고쳐져 있었고 **문서만
    #      낡아 있었다**) ⓑ "이전 내용은 백업에 있습니다"가 대피 성립 시에만 참인데 체크인은
    #      대피 실패 갈래를 가진다 → **백업 존재 약속을 뺀다**(백업은 §5-C가 실물 목록으로 말한다).
    "CHECKIN_ONE": {                                                        # 17
        "ko": "적용 전 게임 설정 파일 내용을 {profile} 프로필에 저장했습니다.",
        "en": "Saved the pre-apply contents of the game's settings file to the "
              "{profile} profile.",
    },
    "DISCOVER_NONE_FOUND": {                                                # 19
        "ko": "자동 감지 결과에 표시할 게임이 없습니다. 자동 감지는 Proton prefix"
              "(…/steamapps/compatdata/<appid>/pfx/…) 안만 확인합니다. 네이티브 Linux "
              "게임은 설정 파일이 prefix 밖에 있어 현재 등록할 수 없으며, 아래 버튼으로도 "
              "등록할 수 없습니다. 감지되지 않은 Proton 게임이 있다면 아래 버튼으로 해당 "
              "게임 prefix 안의 설정 파일을 골라 주세요. 아니라면 그 게임을 한 번이라도 "
              "실행했는지 확인해 주세요.",
        "en": "There are no games to show in the auto-detection results. Auto-detection "
              "only checks inside Proton prefixes (…/steamapps/compatdata/<appid>/pfx/…). "
              "Native Linux games keep their settings files outside prefixes, so they "
              "cannot currently be registered, including with the button below. If a "
              "Proton game was not detected, use the button below to pick its config "
              "file inside that game's prefix. Otherwise, check that the game has been "
              "run at least once.",
    },
    # 20 — 9판이 *수*를 뺀 것과 같은 이유가 *"볼 수 있습니다"* 에도 적용된다(손상 기록만 남으면
    #      제외 화면에 그릴 행이 없어 그 약속이 거짓이 된다 — §15-D E5). 다만 갈 곳을 잃으면
    #      제외된 게임을 되찾는 **유일한 동선**이 사라지므로, 약속이 아닌 **위치 진술**로 낮춰
    #      경로를 남긴다 — 목록이 거기 있다는 사실은 행이 0이어도 참이다.
    "GAMES_EXCLUDED_NOTE": {                                                # 20
        "ko": "게임 감지 제외 기록이 남아 있습니다 — 제외 목록은 [게임 감지]의 "
              "「제외한 게임」에 있습니다.",
        "en": "Some game-detection exclusion records remain — the exclusion list is "
              "under “Excluded games” in [Detect games].",
    },
    "DELETE_CONFIRM_REDISCOVER": {                                          # 21
        "ko": "등록을 해제하면 자동 감지에서도 제외됩니다. 다시 쓰려면 [게임 감지]의 "
              "「제외한 게임」에서 다시 포함하거나 파일을 직접 골라 등록해 주세요. 남아 "
              "있는 백업이 있다면 재등록한 뒤 백업 내용을 복원할 수 있습니다.",
        "en": "Unregistering also excludes the game from automatic detection. To use it "
              "again, put it back from “Excluded games” in [Detect games] or pick its "
              "file yourself. If any backups remain, their content can be restored "
              "after the game is registered again.",
    },
    # ★ 마침표 없음이 **형제 3키의 관례**다(2026-08-13 실기 접수). `OPEN_DISCOVER_DESC`·
    #   `OPEN_SETTINGS_DESC`는 ko·en 모두 마침표가 없는데 이 키만 있었다 — 사실성 22번이
    #   ko 값을 다시 쓰면서 딸려 들어간 것이다. 같은 자리·같은 종류의 줄이 하나만 다르면
    #   화면이 두 가지 문법을 말한다. **잠금표도 함께 옮긴다**(값이 바뀌었는데 표가 낡으면
    #   이 검사가 실물을 막는다 — 그러면 다음 사람이 검사를 끈다).
    "OPEN_GAMES_DESC": {                                                    # 22
        "ko": "게임별로 프로필을 저장하고 한 게임씩 적용합니다",
        "en": "Saves profiles per game and applies them one game at a time",
    },
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
#:   "LOCKED 53"과 "TOTAL 53"이 우연히 같은 수다. PINNED가 다시 생기는 날 두 수는 갈라진다 —
#:   개념을 뭉쳐 기억하지 말 것(10판 초안 2판 지적 4).
#:   28 → 33 (10판: D절 4행 + E절 `RESET_ZONE_BODY` 1행)
#:   33 → 53 (12판 산식: 33 − 1(`SAVE_GUIDE` 키째 폐기) + 2(2키로 분할) + 6(§10-C 잠정에서
#:            승격한 QAM 재편 6키) + 13(사실성 점검이 §10-A에 값 행을 새로 만든 13키))
TOTAL_FIXED = 53


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
