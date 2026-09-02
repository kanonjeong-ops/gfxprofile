# 설계 개정 19판 초안 (4판) — 손상 registry 3층 대응과 오류 코드 정밀화 (DESIGN-AMENDMENT-R19-2026-08-30)

> **지위: 채택 확정(2026-08-30) — 반증 3패스 반영 4판, 개정 19판으로 정본 반영 완료. repo 편입본.**
> 참모(Opus) 작성, 2026-08-30. repo 편입(ⓒ: `docs/DESIGN-AMENDMENT-R19-2026-08-30.md`로 복사 + 이 지위 줄·파일명 표기를 편입본에 맞게 정정 + `DESIGN-UX` 제목줄 19판·정정 이력 1줄)은 구현 세션 몫.
> 수정 방법의 정본 = `FIXPLAN-2026-08-30.md` **v9** · 등급·처분 = `TRIAGE-2026-08-30.md` v4(3·4판에서 무변경) · 합격선 = `QAPLAN-2026-08-30.md` **v8**.
> **이 판(4판)의 조문은 v8·v7 반영으로 바뀌지 않았다** — 갱신된 것은 이 참조 줄과 O-3뿐이다.
> 반증 정본 = `codex-out/REFUTE-R19-LAST.md`(2판) · `codex-out/REFUTE-CORR3-LAST.md`(3판) · **`codex-out/REFUTE-R19-3PAN-LAST.md`(4판)** · 이종 검토 = `codex-out/REVIEW-F1A-DESIGN-LAST.md` · `codex-out/REFUTE-FIXES-LAST.md`.
> 3판 반영 이력의 상세 = `DESIGN-R19-CORR3-2026-08-30.md`(정정 패치 문서 — 본문 반영 완료, 이력 기록으로 보존).
> 구조: 개정 절마다 **「현행 조문 인용 → 개정 조문 전문 → 근거 → 파급」**(R10 관례). 이 초안만 읽고 구현 워커가
> F1·F2a의 코드·프론트·i18n 작업에 착수할 수 있어야 한다(자립형).
> **줄 번호는 2026-08-30 실측이고 표류한다 — 착수 시 심볼로 재확인한다.** 인용은 본문을 병기했다.
> 사용자 결정 제외 5건(F4-3 · F4-5 · F4-6 · F3-1 문구 · F3-2)은 이 초안이 **한 줄도 되살리지 않는다.**

## 0-0″. 초안 4판 개정 이력 (3판 정본을 대상으로 한 반증 3패스 반영 전량)

검토자 종합 = *"설계는 서 있으나 방법 정본이 기각된 안을 되살렸고, 판별 기준이 3판에서 새로 어긋났다."*
판정 **5 성립 · 1 부분 성립 · 2 실패**, 세션이 실물 재확인 후 **성립분 전건 + 배정 밖 1건**을 반영했다.

1. **[최심각] 방법 정본이 R19-1을 잃은 것을 되잡았다**(O-1 · FIXPLAN v7): `FIXPLAN` F1-b가 여전히
   *"`registry.json.corrupt-<stamp>`로 보관(no-clobber: 동명 존재 시 접미 증가)"*라 **O-1이 기각한
   `exists`+`os.replace` 파일안**을 그대로 지시하고 있었다. 방법 정본만 따르는 구현자는 경합·dangling
   symlink에서 **유일한 증거를 덮는** 그 결함을 되만든다. FIXPLAN에 `mkdir(holder)` → EEXIST면 다음 이름 →
   `os.replace(path, holder/basename)`를 명문화하고 **O-1이 정본임을 지목**했다. 설계 조문(§7-4′ 6항)은
   원래부터 디렉터리안이었다 — **바뀐 것은 방법 정본이지 설계가 아니다.**
2. **[판별 기준] C-1 기준 문장을 다시 썼다**(C-1 · C-2-1·C-2-2): 3판의 *"그 호출자를 **지나는** route가
   오늘 `ok:true`를 내는 세계가 있는가"*는 **재현되지 않는다** — `engine.disk_state`는 `restore.needs_confirm`의
   `already` 성공을 **지나므로** 문자 그대로 적용하면 보존 계열이 되고, `engine.apply_profile`도 `apply_all`
   봉투가 언제나 `ok:true`라 같은 함정에 빠진다. 기준을 **반사실 질문**으로 바꿨다:
   ***"이 자리가 `Refused`를 냈을 때 오늘 나가던 성공 답이 사라지는가."*** 단위(그 appid에 대한 답 ·
   일괄 route는 봉투가 아니라 **행**)와 반사실 범위(그 자리만 바꾼다)를 함께 못 박았다.
   **9자리 배정은 하나도 바뀌지 않았고 근거 문장과 검산표가 바뀌었다.**
3. **[자기모순] `_preview_one`의 미러를 「술어 호출」로 일원화했다**(C-1 · §14-H ⓛ): 3판은 §14-H가
   *"같은 술어를 부른다"*고 하는데 C절 전문은 **별도 `isinstance` 식을 다시 적어** 구현자가 두 갈래로 읽었다.
   **술어 호출이 정본**이고, 그러려면 헬퍼가 `engine` 모듈 공개여야 하므로 이름의 밑줄을 뺀다
   (`engine.entry_corrupt`). truthy 비-dict entry에서 `.get`이 먼저 죽는 문제는 **단축 평가 순서**로 답한다.
4. **[자기모순] §0-1 절 구성표의 I절 계수**를 정본 제목과 맞췄다(*"낡음 연쇄 7건(조문 4 · 주석 3)"* →
   *"조문 4건 · 코드 주석 12자리 · 검사 파일 문서 5자리"*).
5. **[자립성] `get_overview`의 접기 자리를 지목했다**(C-1 · C-2-3 · C-3 · P-1): 실물 사망점은 목록 조립이
   아니라 **정렬 키**다 — `sorted(reg["games"], key=lambda a: reg["games"][a].get("name", a))`.
   조문이 자리를 말하지 않으면 구현자가 루프 안만 고치고 **정렬에서 그대로 죽는다.**
6. **[배정 밖 · 2판 승계 구멍] `save_fresh_registry`의 `mkdir` 실패가 샜다**(§7-4′ 6항 · §15-D E60):
   코드 전문이 `except FileExistsError`만 잡아 `PermissionError`·ENOSPC는 **`RegistryError`로 변환되지 않고
   `UNEXPECTED`로 나갔다** — §7-4′ 5항의 *"격리 실패도 `RegistryError`다"*와 좁은 try의 안전 논거가 함께
   깨지는 자리다. `except OSError` 갈래를 더하고 E60 ⓐ에 `mkdir` 실패를 편입했다.
7. **[방법·합격선 정합]** F1-b의 *"신설 코드"* 서술 3자리(FIXPLAN F7-1 · QAPLAN §0 · §2 G3)를 정정했다 —
   §7-4′는 `CONFIRM_REQUIRED`를 유지하므로 **F1-b의 신설 백엔드 코드는 0**이고 신설 2키는 화면 전용이다.
   그 거짓 전제는 **신설 한도(코드 2종) 초과 구현을 유도**한다. QAPLAN에는 격리물의 **형(디렉터리)·바이트
   보존·충돌 3종 no-clobber** 단언과, 역전/무회귀 오라클의 **갈래 구분**을 넣었다(3판 신설 오라클이 G1
   머리말과 충돌하고 있었다).

**4판이 바꾸지 않은 것**: 9자리 층 배정 · 사용자 결정 제외 5건 · R19-1~R19-4 · **F1 합격 조건 문장** ·
U5 계약과 §14-F′ ⓒ 조건식 · F2b 슬롯 범위 · 편입 방식 · 실행 순서·커밋 단위 · TRIAGE v4.
(반증 각도 4·5 = **반박 실패** — 3판의 보존 배정과 ⓒ 조건식은 지지됐다.)

---

## 0-0′. 초안 3판 개정 이력 (세션 착수 전 실물 조사 + 반증 2패스 반영 전량)

세션 종합 = *"계약은 서 있으나, 층 정의가 오늘 사는 route 둘을 죽이고 · 조건식 하나가 그대로는 구현
불가이며 · 전문 하나가 방금 다듬은 주석을 지운다."* **실질 결함 1 + 문면 3 + 층 배정 2 + 술어 정합 1 =
7건 전건 반영했다.** 3판 반영 전량:

1. **[실질] C-1 층 판별 기준 재작성**(C-1): 층을 가르는 기준을 **「그 호출자를 지나는 route가 손상 항목에서
   오늘 `ok:true`를 내는 세계가 있는가」** 한 문장으로 못 박고, *"`game_or_fail`을 지나는 전부"*라는 정의를
   **폐기**했다. **`main.list_backups`와 `restore.needs_confirm`을 보존 계열로 옮긴다** — 전자는 결손
   항목에서, 후자는 비-dict + 슬롯 대상 `already`에서 **오늘 `ok:true`를 낸다.**
   `game_or_fail` 호출자 **전수 9자리** + `game_or_fail`을 지나지 않는 소비 지점 **7자리**(`engine.add_game`
   포함)를 새 기준으로 재배정하고 배정이 **기준만으로 재현되는지 검산표로 확인**했다(9/9 일치).
   **F1 합격 조건 전칭 명제의 예외는 0건이다** — 2판까지의 조문은 오늘 `ok:true`인 route 둘을 죽였다.
   부수 이득 둘: **비-dict 항목에서도 백업 목록이 뜬다** · **`{}` 항목을 삭제로 치울 수 있다.**
2. **[문면] §14-F′ ⓒ 조건식 확정**(A-1): *"`version > REGISTRY_VERSION`이면 검사하지 않는다"* →
   **`type(version) is int and version <= REGISTRY_VERSION`일 때만 검사한다.** 비-int version은
   ⓐ 비교 자체가 `TypeError`라 **구현이 불가능**했고 ⓑ 그 세계에도 **살아 있는 읽기가 있다**
   (`{"version":"2","games":["570"]}`에서 `discover_games`가 성공한다). 새 조건식은 2판보다
   **엄격해지는 세계가 하나도 없다**(스킵 집합이 커지기만 한다). §7-4′ preflight는 `version`을 읽지
   않으므로 무영향이고, 「비-int + 손상」의 재사망도 그 자리가 막는다.
   *(3판 1차 정정안이 근거로 들었던 「잃는 읽기 능력 0」은 이 반례로 철회됐다.)*
3. **[문면] B-5 ⑤-1의 지위 한정**(B-5): *"프론트 3파일 전문(그대로 쓴다)"*은 ⑤-2·⑤-3에만 적용된다.
   ⑤-1은 **타입 구조와 19판 신설 주석만 정본**이고 현행 주석 **7블록**은 **보존·병합**한다.
4. **[문면] I절 확대**(I): 제목을 *"fresh·F2a가 만드는"* → ***"19판이 만드는"***으로 넓히고 **6항(ⓘ~ⓝ)
   = 13자리**를 신설했다(계수는 항목별 검산표로 둔다). F7-1이 거짓으로 만드는 2자리 · F4-1·F1-c가
   거짓으로 만드는 검사 파일 문서 4자리 · `engine.apply_all` 외곽 except · `confirm._preview_one` ·
   **F1-c가 참으로 만들어 낡는 「KeyError는 안 잡는다」 3자리** · **(마)가 낡게 하는
   `ALREADY_REGISTERED` 단정 2자리**.
5. **[층 배정] `confirm.already_registered` = 실행·판정 계열**(§14-H ⓙ): 술어 직접 적용 →
   `Refused(REGISTRY_ENTRY_CORRUPT)`. 근거는 **거짓 진술**과 **못 믿는 값을 화면에 싣는 것** 둘이다
   (「막다른 길」은 근거가 아니다 — `ALREADY_REGISTERED` 문구도 등록 해제까지는 안내한다).
   이 문이 `engine.add_game`의 `entry.update` 사망점도 함께 막는다.
6. **[층 배정] `restore.target_sha1` = 조회 계열 · `restore.needs_confirm` = 보존 계열**(§14-H ⓚ):
   isinstance 격리 → **「모름」(`None`)**, `require_intact=False` + 비-dict 접기. **쓰기의 문은 여전히
   `engine.restore_backup` 하나**다. 세 `disk_state` 래퍼는 **코드 무변경**(이미 `Refused`를 접는다) —
   낡는 것은 독스트링뿐이다(I절 ⓜ).
7. **[술어 정합] `confirm._preview_one`**(§14-H ⓛ): 미리보기의 `config_path` 검사를 **truthiness와 형
   술어 둘 다**로 고친다 — 형 술어로 **교체**하면 빈 문자열 세계가 `would_apply`로 새어 새 동치 위반이
   생긴다. **신설 코드·i18n 키는 3판에서 0 증가**다.

**3판이 바꾸지 않은 것**: 사용자 결정 제외 5건 · R19-1~R19-4 · **F1 합격 조건 문장**(불변 정본) ·
U5 계약 · F2b 슬롯 범위 · 편입 방식 · FIXPLAN 실행 순서·커밋 단위 · TRIAGE v4의 등급·처분.

---

## 0-0. 초안 2판 개정 이력 (반증 1패스 반영 전량)

검토자 종합 = *"핵심 계약은 정확하나 타입 전문이 컴파일을 깨뜨리고, fresh 갈래가 생긴 뒤 거짓이 되는 기존
조문·화면 문구가 다수 남았다."* **최심각 1건 포함 전건을 반영했다.** 2판 반영 전량:

1. **[최심각] 타입 전문 컴파일 파괴 수정**(B-5): `makeResetConfirmSpec`의 매개변수를 **`ResetNormalConfirmParams`로
   좁히는 개정**을 조문화했다(1판의 *"정상 spec은 무변경"* 문장 **철회**). `SettingsPopup.runReset` 전문의 미정의
   식별자 `onOK`/`onSnapshot`을 **현행 인라인 콜백 기반**으로 다시 썼다.
2. **F2b 축소**(E절 ⓐ): 사용자 기확정 결정대로 **슬롯 `store.write_profile`만**. 1판의 config 갈래
   `atomic_write` 포함은 **철회**했다 — `PROFILE_WRITE_FAILED`의 문구 주어가 *"프로필을 저장하지 못했습니다"*
   (`ko.json:78`)라 게임 설정 파일 쓰기에 붙이면 오표기다. config 갈래는 백로그(재론: 실보고 1건).
3. **낡음 연쇄 8건 편입**(H·I절): `RESET_ZONE_BODY`·`RESET_HINT`(진입 화면 상시 문구) · §7 흐름 설명 ·
   §8-D `DELETE_FAILED` 3자리(§8-D·§10-A·`rpc.ts`) · §8-D 「토큰 6종」 · §5-G 「3인자 둘」·「meta-only 3곳」
   **기존 문장 대체** · §14-F 제목과 *"`store.py`는 fence"* · 코드 주석 3자리(`store.py`·`main.py`·`i18n.ts`) ·
   §10 머리말 「28종」.
4. **`REGISTRY_ENTRY_CORRUPT` 문구 재작성**(J절): 등록 해제가 **자동 감지 제외까지 수행**한다는 사실을 빠뜨려
   막다른 길이 될 수 있었다 — 기존 `DELETE_CONFIRM_REDISCOVER`(`ko.json:227`)와 **같은 사실 구조**로 ko/en 재작성.
5. **R19-1 격리 정책 재설계**(O-1): `exists`+`os.replace`는 no-clobber를 **보장하지 않는다**(검사-후-행동 창 ·
   dangling symlink 미탐). **`os.mkdir`의 EEXIST로 이름을 구조로 확보하는 격리 디렉터리** 방식으로 교체했다.
   *"rename 실패 세계 = atomic_write 실패 세계"* 등치는 **삭제**하고 근거를 *"증거를 잃지 않는 쪽으로 접는다"*로
   갈아 끼웠다. fsync 내구성 단정도 **크래시 중간 상태 3종의 안전성 논증**으로 대체했다.
   dangling `registry.json` 심링크는 **fresh에 진입하지 않는다**는 사실에 맞춰 적용 범위를 한정했다.
6. **preflight 자립성 보강**(B-2): `_reset_preflight`의 코드·메시지 전문 · **좁은 try의 코드 전문**(격리 실패가
   fresh 확인 재발급으로 먹히는 루프가 **구조적으로 불가능한 이유** 포함) · 발급→소비→저장 제어 흐름 전문.
7. **소소 정정**: *"신설 코드 3종"* → **2종** · F7-1 잠금 서술 정정(UI 전용 2키는 codes 검사 밖 —
   TypeScript `StringKey`와 en/ko 집합 검사의 **결합**으로 지켜진다).
8. **결정 확정 편입**: R19-3(`mode` 판별자)·R19-4(프론트 분기 0) **세션 확정**. R19-4는 세션이 **FIXPLAN v5를
   정정 완료**해 방법 정본과 초안이 일치한다 — 1판의 「FIXPLAN과의 차이 신고」 절을 **「정합 확인」**으로 바꿨다.
9. QAPLAN G4 「전 game entry 비-dict」 행은 세션 편집 오기가 정정돼 **「정상 reset 성공」**이 정답이다 — 인용 정정.

---

## 0. 착수 보고 — 브리핑 전제와 실물의 불일치 3건 (다른 작업보다 먼저)

브리핑 「미확인 5건」을 정본에서 전수 탐사했다. **3건은 실재, 1건은 전제가 깨졌고, 1건은 소재가 브리핑과 다르다.**

| # | 브리핑 전제 | 실물 | 처분 |
|---|---|---|---|
| 1 | reset 절에 「reset은 손상 registry의 탈출구가 아니다」류 조문 | **실재**. `§7` 상태 분기표 **「조회 실패」 행**(`:1565`) 말미: *"⚠️ 즉 **registry 손상의 탈출구가 아니다** — … 손상 복구는 UI 밖: `load_registry`의 오류 메시지가 `.bak` 복구/rm 절차를 안내한다"*. 짝인 `SettingsPopup.tsx` 주석(*"즉 이것은 손상 복구의 탈출구가 아니다"*)도 실재. 제정 경위는 §19 **17판 항 S-02** | **B절**이 반전한다 |
| 2 | §10-A i18n 키 **잠금 표**와 등재 의무 | **부분 실재 — 「표」는 없다.** 잠금 게이트 `test_wording_10a.py`는 **13판에 삭제**됐다(`:1777`: *"→ **13판: 해당 없음** … **바이트 값을 명시한다는 규칙은 유지된다** — 이 문서가 정본이고 대조는 리뷰가 한다"*). 12판 관례(`:1764`)로 **en 바이트를 적은 키는 en도 잠근다**. 단계 배정은 §10-D가 구속 | **J절**이 §10-A에 4행을 더한다. 「LOCKED 표 갱신」은 **대상 자체가 없다** |
| 3 | **§14 엔진 fence** — 변경을 신고할 자리와 관례 | **전제가 깨졌다. fence는 15판에서 폐지됐다**(§14-D, `:2483`; `:2560`: *"15판의 엔진 변경에는 **허용 diff도 승인 절차도 없다** — 그 자리는 회귀 전량과 코드 리뷰가 대신한다"*). 살아 있는 것은 규율 한 줄(`:2014`): *"route 층에서 구현 가능한 것은 엔진으로 내리지 않는다. 이 조건은 **15판에도 그대로 유효하다**"* | 신고 자리는 **§14의 판별 소절**이다(§14-G가 15판 몫). **M절**이 `§14-H`(19판 몫)를 신설한다 |
| 4 | §15 검사 정책과 F7 2종의 정합 | **실재**(`:2569`): *"**검사는 엔진·데이터 경로에만 만든다.**"* F7 둘 다 데이터·계약 경로라 정합. **덤**: 같은 머리말(`:2612`)의 *"⚠️ **코드 ↔ i18n 대조 검사는 존재하지 않는다**"*를 **F7-1이 거짓으로 만든다** | **K절**이 그 조문을 정정한다 |
| 5 | 오류 코드/봉투 계약 절 | **실재하되 소재가 셋**: 코드 문구 = §10-A 하위 행(`:1726-1727`) · reset 성공 봉투 = **§7 결과 봉투**(`:1567`)와 **§8-D 표**(`:1600`) · 버전 가드·탈출로 = §14-F(`:2510`) | **B·D절**이 세 곳을 함께 고친다 |

**불일치의 실질**은 #3 하나다 — *「§14 fence에 신고한다」는 지시를 그대로 따르면 폐지된 제도에 신고하는 조문이 된다.*
이 초안은 §14의 **현행 관례**(판별 소절 + 회귀·리뷰)를 따랐다(M절). 세션이 다르게 판정하면 M절만 교체하면 된다.

### 0-1. 판수 · 절 구성 · 결정 기록

**판수**: 정본 제목줄 = 「개정 18판」, §19 최신 항 = 18판(2026-08-26). **일치한다.**
채택 시 제목줄을 **「개정 19판」**으로 올리고 §19에 19판 항을 신설한다.

| 절 | 대상 | 닿는 조문 |
|---|---|---|
| A | F1-a 로더 입구 3구멍 | §14-F 확장(§14-F′ 신설) |
| B | F1-b `reset_all` fresh 탈출 갈래 | **§7 조회 실패 행 반전** · §7-4′ 신설 · §7 결과 봉투 · §8-D · rpc.ts·confirmSpecs·SettingsPopup 전문 |
| C | F1-c 항목 단위 손상 술어 + `REGISTRY_ENTRY_CORRUPT` | §8-D 정규화 규칙 확장 |
| D | F2a 부분완료 고지 | §7-5′ 신설 |
| E | F2b(**슬롯만**) · F4-1 · F4-2 | §14-E″ 신설 |
| F | F4-7 4분류 정오 | §5-E-2 계열 |
| G | F4-8 already 판정 통일 | **§5-G 두 문장 대체** |
| H | 설정 진입 화면 상시 문구의 한정 | §7 팝업 S |
| I | 낡음 연쇄(조문 4건 · 코드 주석 12자리 · 검사 파일 문서 5자리 — ★ 3판 확대) | §7·§8-D×3·§10·§14-F·코드 주석·검사 문서 |
| J | 신설 i18n 4키 전문 | §10-A |
| K | F7-1·F7-2 | §15 머리말 · §15-B |
| L | 알려진 한계 | §15-D E18·E52 축소 + E59~E61 |
| M | 엔진·store 층별 판별 | **§14-H 신설** |
| N | 설계 무변경 확인 | 조문 0 |
| O | 결정 기록(확정 4 · 열린 0) · 정합 확인 · 이견 | — |
| P | 파급 총괄 · 편입 지점 · 착수 순서 | — |

**결정 처분 기록 — 전건 확정, 대기 0**:

| # | 사안 | 확정(2026-08-30) |
|---|---|---|
| R19-1 | fresh 격리 방법 | **`os.mkdir` EEXIST로 이름을 구조 확보하는 격리 디렉터리**(참모 2판 재설계 — O-1) |
| R19-2 | no-clobber 규칙 | **R19-1에 흡수** — `exists` 루프를 폐기하고 `mkdir` 실패를 신호로 쓴다(O-1) |
| R19-3 | 봉투 판별자 이름 | **`mode` 채택**(세션 확정 — O-2) |
| R19-4 | `RESET_FAILED`의 프론트 분기 | **분기 0 채택**(세션 확정 + FIXPLAN v5 정정 완료 — O-2·O-3) |

---

## A절. §14-F 확장 — 로더 입구의 세 구멍 (F1-a)

### A-0. 현행 조문 인용

§14-F(`:2510`, 「레지스트리 버전 가드 (U5 — 14판 보수. **fence 밖: `main.py`·`codes.py`·i18n만**)」):

> 구판 플러그인이 신판 데이터를 만나면 **변경을 거부한다**(fail-closed, 데이터 보존 우선). **읽기는 막지 않는다.**
> **왜 route 층인가** — ① `load_registry`에서 거부하면 읽기까지 죽어 화면이 고지를 못 그린다 ② … ③ **`store.py`는 fence — 방어는 소비자 층에 둔다**(기존 선례).

(제목의 「fence 밖: …만」과 ③의 fence 서술은 **I절이 함께 교체한다** — fence는 15판에 폐지됐고 이 절이 `store.py`를 고친다.)

§10-A(`:1726`·`:1727`)가 `REGISTRY_UNREADABLE`·`REGISTRY_MALFORMED`의 ko/en 바이트를 잠근다(12판 — en도 잠금).

실물 `store.load_registry`가 **이미 하는 것**: 무효 JSON·비-UTF8 → `REGISTRY_UNREADABLE` · 최상위 비-dict → `REGISTRY_MALFORMED`.
**안 하는 것 셋**: ⓐ `open()`의 `OSError` ⓑ `settings` 비-dict ⓒ `games` 비-dict.
ⓑ는 `reg["settings"].setdefault(...)`에서 **그 자리 `AttributeError`**로 죽고, ⓐ·ⓒ는 소비자 층에 흩어져 `UNEXPECTED`가 된다.

### A-1. 개정 조문 전문 — §14-F′ 신설

> #### 14-F′. 로더 입구의 형태 검사 (19판 신설 — F1-a)
>
> `store.load_registry`는 **읽어서 dict로 만드는 데까지** 책임진다. 그 과정에서 확정적으로 실패하는 세 자리를
> 이름 있는 `RegistryError`로 봉투화한다 — **새 코드는 만들지 않는다**(둘 다 §10-A가 값을 잠근 기존 코드다).
>
> | # | 자리 | 코드 | 버전 게이트 |
> |---|---|---|---|
> | ⓐ | `open()`이 던지는 `OSError`(권한·EIO·`IsADirectoryError` 등) | `REGISTRY_UNREADABLE` | **없다 — 무조건** |
> | ⓑ | `settings`가 dict가 아님 | `REGISTRY_MALFORMED` | **없다 — 무조건** |
> | ⓒ | `games`가 dict가 아님 | `REGISTRY_MALFORMED` | **`type(version) is int and version <= REGISTRY_VERSION`일 때만 검사한다** |
>
> **검사 순서는 고정이다**: ① 최상위 dict 확인(현행) → ② `base = default_registry()`의 최상위 결손 키
> `setdefault` 채움(현행) → ③ **ⓑ·ⓒ 형태 검사(신설)** → ④ `settings` 내부 기본값 `setdefault`(현행).
> ③을 ②보다 앞에 두면 `{}`나 키가 빠진 registry를 불필요하게 거부하고, ④보다 뒤에 두면 ⓑ가 검사에 닿기 전에
> `AttributeError`로 죽는다.
>
> **ⓒ에만 버전 게이트가 붙는 이유는 U5 계약이다**(*"읽기는 허용하고 변경만 막는다"*). 미래 registry
> `{"version": 2, "settings": {}, "games": []}`는 **현행 로더를 통과하고 그 뒤 읽기도 성공한다** —
> `get_overview`는 `for appid in sorted(reg["games"])`가 0회 돌아 정상 성공하고, `discover_games`는
> `discover.discover(known_appids=set(reg["games"]))`로 넘겨 `"registered": appid in known_appids`에
> **실제로 쓴다**(`games=["570"]`이면 570이 등록으로 판정된다 — 우연히 예외가 안 나는 것이 아니라 유의미한
> 읽기다). ⓒ를 무조건 검사로 만들면 **지금 성공하는 미래 registry 읽기를 실패로 바꾼다 — U5 회귀다.**
> ⓑ에는 같은 반례가 없다(현행 로더가 그 자리에서 이미 죽는다) — 순이득이므로 무조건이다.
> **이 게이트가 남기는 「미래 + 손상 → reset 재사망」 구멍은 로더가 아니라 탈출로 입구에서 막는다**(§7-4′ preflight).
>
> **★ 19판 3판 정정 — 게이트를 「스킵 조건」이 아니라 「검사 조건」으로 적는다.** 2판 초안의
> *"`version > REGISTRY_VERSION`이면 검사하지 않는다"*는 **그대로는 구현이 불가능하고**, 구현 가능하게
> 고쳐도 **읽기를 하나 죽인다.** 둘 다 닫는 형태가 위 표의 조건식이다.
> - **구현 불가**: `version`이 int가 아니면 그 비교 자체가 `TypeError`이고, 그 예외는 `route`의 마지막
>   갈래에 잡혀 **`UNEXPECTED` 봉투**가 된다 — 로더가 익명 오류를 내는 것은 이 절이 없애려던 그 상태다.
> - **U5 읽기 회귀(구체 반례)**: `{"version": "2", "settings": {}, "games": ["570"]}`는 **오늘
>   `load_registry`를 통과하고**(최상위 dict 검사만 한다) `discover_games`가 **성공한다** —
>   그 route는 `games`를 mapping으로 색인하지 않고 `set(reg["games"])`로 **membership 집합**으로만 쓰기
>   때문이다(`main._discover_entries`). ⓒ를 그 세계에까지 돌리면 **살아 있는 읽기 route 하나가 죽는다.**
> - **그래서 검사 조건을 「형이 int이고, 그 값이 현재 버전 이하일 때」로 좁힌다.** 이 형태는 2판보다
>   **엄격해지는 세계가 하나도 없다** — 스킵 집합에 「비-int version」이 **더해지기만** 한다.
> - **문법은 `main._registry_newer`에서 승계한다** — `isinstance`가 아니라 `type(...) is int`다. 그 함수의
>   독스트링이 이유를 적어 두었다: *"`True`는 `int`의 인스턴스라 `version: true`가 검사를 통과하고,
>   `True > 1`은 거짓이 된다. 형 자체를 본다."* 같은 사실을 두 자리에서 다르게 판정하면 언젠가 갈린다.
>   따라서 `{"version": true, …}`도 **미래 registry가 아니고 ⓒ 검사도 받지 않는다** — 로더는 그 파일을
>   해석하지 않고, 판정은 route가 한다.
> - **비-int version을 로더가 거부하지는 않는다.** 로더가 보는 것은 `games`의 형태뿐이고, `version`은
>   **게이트를 열지 말지의 판단 재료로만** 읽는다. 오늘 비-int 판정은 **route 층 `main._registry_newer`가
>   `REGISTRY_MALFORMED`로 낸다 — 변경 동작에서만**이다. 로더에서 막으면 **U5 「읽기는 허용하고 변경만
>   막는다」가 깨진다.** 층 배정은 §14-F ③ 개정과 같다 — *store가 보는 것은 형태이고, 버전이라는 의미는
>   route가 본다.*
> - ⚠️ **이 게이트가 남기는 것을 정직하게 적는다**: 비-int·미래 version + 비-dict `games`인 파일은
>   **로더를 통과하고**, 그 뒤 `games`를 mapping으로 쓰는 읽기(`get_overview`)는 **오늘처럼 `UNEXPECTED`로
>   죽는다.** 19판은 그것을 고치지 않는다 — 고치려면 로더가 그 세계를 거부해야 하는데 그것이 위의 U5
>   회귀다. **대신 탈출로는 열려 있다**: `reset_all`의 preflight는 **버전을 읽지 않으므로** 이 세계를
>   fresh 갈래로 보낸다(§7-4′ 1항). 즉 **「미래 + 손상」뿐 아니라 「비-int + 손상」의 재사망도 같은 자리가
>   막는다.**
>
> **원인은 메시지 문자열에 넣는다**: `raise ... from exc`만으로는 부족하다 — `route`의 `RegistryError` 갈래는
> `logger.info(... code=%s)`와 `_fail(..., message=str(exc), ...)`만 하고 traceback을 남기지 않아 `__cause__`가
> 봉투 변환 뒤 운영 로그에서 사실상 사라진다. **`OSError`의 종류·`errno`·경로를 새 `RegistryError`의 메시지
> 문자열에 직접 적는다.** (프론트는 `message`를 어디서도 읽지 않는다 — src 전수 grep 0건. 화면은 `t(code)`이고
> 이 문자열의 독자는 로그와 세션이다.)
>
> **`load_registry`의 `"초기화: rm %s"` 안내 문구는 제거한다.** 화면 노출은 원래 없었으나, 로그·봉투를 읽는
> 사람에게 **오진 시 파괴를 유도하는 문장**이고, 19판부터 그 안내가 가리키던 일을 **인앱 탈출로(§7-4′)가
> 대신한다.** (`store.save_registry` 독스트링의 *"`.bak`이 있어야 손상 시 안내가 실제 복구 경로가 된다"*가
> 이 제거로 낡는다 — I절 ⓕ.)
>
> **항목 단위 손상(비-dict 항목 · `config_path` 결손)은 입구에서 막지 않는다** — 제품의 명문 설계가 항목 단위
> 격리이기 때문이다(§8-D 정규화 규칙 · `engine.apply_all`의 게임별 외곽 try). 처분은 §8-D 확장(C절)이다.

### A-2. 근거

- 세 구멍은 재현 하네스로 실측됐다(r6(a) 비-dict settings = 전면 불능 `AttributeError` · r7 읽기 실패 = `UNEXPECTED`).
- **범위를 셋으로 좁힌 것이 이 절의 핵심이다.** v3까지의 「`REGISTRY_CORRUPT` 재사용」은 **실재하지 않는 이름**이었고,
  무조건 컨테이너 검사는 U5 회귀였다(REVIEW-F1A §1 — 반례 실증).
- **봉투화 배관은 신설하지 않는다**: `load_registry` 호출은 `main.py` 14곳 + `@mutating` 관문 1곳뿐이고 `@route`가
  최외곽이라 `except (engine.Refused, store.RegistryError)` 한 자리로 **전부 수렴**한다.
- 적대적 입력(과중첩 JSON의 `RecursionError` · FIFO에서 `open`이 대기)은 **범위 밖으로 명시 유지**. FIFO는
  `open()`이 반환하지 않아 이 절의 어떤 검사에도 닿지 않는다 — 재론 조건은 실보고 1건이다.

### A-3. 파급

| 대상 | 내용 |
|---|---|
| 코드 | `store.load_registry` 한 함수. **통독 게이트 대상**(조각 치환 금지 — 블록을 다시 쓴다) |
| 코드(문서) | `labels.py` 거짓 docstring 재작성 · `codes.py:REGISTRY_NEWER` U5 근거 과대 서술 축소 · `store.save_registry` 독스트링(I절 ⓕ) |
| i18n | **0** — 신설 코드 없음 |
| 검사 | G4의 U5 행이 **미래 version + `games=[]`에서 `get_overview`·`discover_games` 성공을 정답으로** 잠근다(이 행이 없으면 검증이 U5 회귀를 승인한다 — REVIEW-F1A §7) |
| 타 절 | B절 preflight가 ⓒ의 버전 게이트를 전제로 선다 · I절 ⓕ가 §14-F 제목·③을 교체 |

---

## B절. §7 반전 — `reset_all` fresh 탈출 갈래 (F1-b)

### B-0. 현행 조문 인용

§7 상태 분기표 「조회 실패」 행(`:1565`):

> **초기화 버튼은 활성 유지하되 근거는 다음과 같다**: ⓐ 조회 실패에는 일시 원인(권한·경합)이 섞여 있어 원천 차단은 과잉 ⓑ 눌러도 오발동 위험이 없다 — 백엔드가 토큰+challenge로 fail-closed이고, registry가 실제로 손상됐다면 **`reset_all` route도 첫 줄의 `load_registry()`에서 같은 코드로 거부되므로 토큰 발급 자체가 안 된다**. ⚠️ 즉 **registry 손상의 탈출구가 아니다** — 초판·2판의 "손상이 바로 초기화가 필요한 상황" 서사는 실물과 어긋나 폐기(손상 복구는 UI 밖: `load_registry`의 오류 메시지가 `.bak` 복구/rm 절차를 안내한다)

§7 결과 봉투 조문(`:1567`) 머리:

> `reset_all` 성공은 `_ok(results=results, counts=counts, cleared=cleared)`이고 **`cleared: {named, excluded}` 신설** … 프론트가 조각을 모아 `parts.join(" ")`로 한 문자열을 만든다 … **네 조각이 모두 안 붙을 때만** 폴백 `RESET_OK`

§14-F 말미(`:2537`):

> ⚠️ **알려진 한계**: i18n 문구가 안내하는 「전체 초기화」 탈출로는 미래 스키마가 **구조를 바꾸면** 성립하지 않는다(`reset_all`이 옛 구조를 읽다가 `UNEXPECTED`로 죽는다 — QA 메모리 재현으로 실증).

### B-1. 개정 조문 전문 ① — §7 상태 분기표 「조회 실패」 행 (대체)

> | **조회 실패** | note(`tCode`) + 카운트 자리 "확인 불가"(`RESET_ZONE_UNKNOWN`). **초기화 버튼은 활성 유지**하고, 근거는 **19판에서 하나 더 늘었다**: ⓐ 조회 실패에는 일시 원인(권한·경합)이 섞여 있어 원천 차단은 과잉 ⓑ 눌러도 오발동 위험이 없다 — 백엔드가 토큰+challenge로 fail-closed다 ⓒ **19판 — 손상 상태에서 이 버튼이 실제로 하는 일이 생겼다**: `reset_all`은 registry를 읽지 못하면 **fresh 복구 갈래**로 갈라져 확인창을 띄우고, 승인하면 목록을 새로 시작한다(§7-4′). **★ 17판 S-02의 「registry 손상의 탈출구가 아니다」는 19판에서 폐기한다** — 그 조문이 딛던 사실 둘이 함께 바뀌었다: (1) *"`load_registry()`에서 같은 코드로 거부되므로 토큰 발급 자체가 안 된다"* → **fresh 갈래가 그 거부를 받아 자기 토큰을 발급한다**(`_CONFIRM_TOKENS`는 registry를 읽지 않으므로 손상 상태에서도 발급·소비가 성립한다 — 실물 확인) (2) *"손상 복구는 UI 밖 · `load_registry`의 오류 메시지가 `.bak` 복구/rm 절차를 안내한다"* → **그 문구는 §14-F′가 제거했고, 복구는 UI 안으로 들어왔다.** ⚠️ **초판·2판 서사로 되돌아간 것이 아니다**: 초판은 *"손상이 곧 초기화가 필요한 상황"*이라며 **정상 초기화**를 탈출로로 지목했는데, 19판이 여는 것은 **지우는 대상이 다른 별도 갈래**다(§7-4′ 2항). ⚠️ **이 화면의 상시 두 줄(`RESET_ZONE_BODY`·`RESET_HINT`)은 정상 초기화를 서술한다** — 그 한정은 §7 팝업 S 스케치 각주(19판)에 있다 |

### B-2. 개정 조문 전문 ② — §7-4′ 신설 (구현 계약 전문)

> ### 7-4′. 손상 registry의 fresh 복구 갈래 (19판 신설 — F1-b)
>
> **1. 진입 판정 — preflight는 `reset_all`이 자기 문 앞에서 한다.**
> ```python
> def _reset_preflight(reg):
>     """탈출로 입구의 형태 검사 — 버전 무관.
>
>     로더(§14-F′ ⓒ)는 미래 registry의 `games`를 검사하지 않는다(U5: 읽기는 막지 않는다).
>     그 게이트가 남기는 「미래 + 손상 → reset 재사망」을 여기서 막는다. 미래 registry의
>     읽기 능력은 이 검사로 조금도 줄지 않는다 — 여기는 탈출로 입구이지 읽기 경로가 아니다.
>     보는 것은 컨테이너 둘뿐이다: appid 키와 항목의 형태는 보지 않는다(그 둘은 registry가
>     멀쩡한 세계의 문제이고, §8-D 정규화 규칙이 정상 갈래에서 처리한다).
>     """
>     for key in ("games", "settings"):
>         if not isinstance(reg.get(key), dict):
>             raise store.RegistryError(
>                 "거부: 레지스트리 형식이 올바르지 않습니다 — %s가 dict가 아닙니다 (%s: %r). 파일: %s"
>                 % (key, type(reg.get(key)).__name__, reg.get(key), store.registry_path()),
>                 code=codes.REGISTRY_MALFORMED)
> ```
> **코드는 `REGISTRY_MALFORMED`다** — 로더의 같은 사건(§14-F′ ⓑⓒ)과 같은 코드여야 한다. 이 값은 fresh 토큰
> 지문의 재료이기도 하므로(4항), 발급 시점과 소비 시점에 **같은 원인이면 같은 코드가 나와야 한다.**
>
> **2. 두 갈래는 지우는 대상이 다르다 — 이것이 이 절의 중심 사실이다.**
>
> | | 정상 초기화 | **fresh 복구 초기화** |
> |---|---|---|
> | 지우는 것 | 등록 기록 · **슬롯 프로필 데이터**(백업으로 대피) · 표시명 · 감지 제외 | **게임 목록 파일 하나**(격리 디렉터리로 옮겨 남긴다) |
> | 안 지우는 것 | 백업 폴더 · 게임 설정 파일 원본 | **프로필 · 백업 · 게임 설정 파일 원본 전부** |
> | 이유 | 열거할 수 있으니 지운다 | **열거할 수 없다** — 무엇이 등록돼 있었는지 모르는 상태다 |
>
> 화면은 이 차이를 말해야 한다(§10-A `RESET_FRESH_CONFIRM_WARN`·`RESET_OK_FRESH`).
> **fresh 뒤 사용자가 잃는 것은 「무엇이 등록돼 있었나」뿐이고, 게임을 다시 등록하면 그 게임의 프로필과
> 백업을 그대로 다시 쓴다**(슬롯은 appid로 키가 잡혀 있고 재등록은 `add_game`이 `config_path`를 다시 준다).
>
> **3. 확인 계약 — 코드는 `CONFIRM_REQUIRED` 그대로, params를 판별 가능한 합집합으로.**
> 신설 코드를 만들지 않는다(프론트의 확인 게이트 배관을 그대로 쓴다). 판별자는 **`mode`** 한 필드다.
> - 정상 갈래: `mode:"normal"` + 현행 필드 전부(`games`·`profiles`·`named`·`excluded`·`evicted`·`evict_games`·`challenge`·`confirm_token`).
> - fresh 갈래: `mode:"fresh"` + `confirm_token`·`challenge`**만**. 수를 싣지 않는다 — **셀 수 없기 때문이다**
>   (못 세는 수를 0으로 그리면 화면이 거짓을 말한다).
> **2단 방어(토큰 + type-to-confirm)는 fresh에서도 유지한다** — 되돌릴 수 없는 동작이라는 성격은 같다.
>
> **4. 토큰 — fresh는 스코프도 지문도 별개다.**
> ```python
> _RESET_FRESH_SCOPE = "reset_all:fresh"   # 정상 갈래의 `_RESET_SCOPE`와 섞지 않는다
>
> def _reset_fresh_fingerprint(code):
>     """fresh 토큰에 묶을 지문 — 발급과 소비가 같은 규칙을 같은 순서로 재계산한다.
>
>     정상 갈래의 지문(`reset_fingerprint|evict=`)은 `reg["games"]` 순회를 요구해 이 상태에서는
>     산출 자체가 불가능하다. 그래서 **관측 가능한 파일 상태**에 결박한다. 고정 상수를 쓰면 파일이
>     바뀌어도 토큰이 살아남아 TOCTOU 방어가 통째로 사라진다 — 상수는 최후의 한 자리뿐이다.
>     """
>     path = store.registry_path()
>     sha = store.sha1_file(path)                      # 읽기 실패면 None(store.py 실측)
>     if sha:
>         return "sha1=%s|code=%s" % (sha, code)
>     try:
>         st = os.stat(path)
>         return "stat=%d:%d:%d|code=%s" % (st.st_size, st.st_mtime_ns, st.st_ino, code)
>     except OSError:
>         return "unobservable|code=%s" % code          # 결박할 관측이 없다는 사실을 그대로 받는다
> ```
> **스코프를 가르는 이유**: 두 갈래가 **지우는 대상이 다르므로**(2항), 확인한 것과 실행한 것이 갈릴 여지를
> 문자열에서 막는다 — `_apply_scope`·`_restore_scope`가 방향·목적지를 스코프에 합성한 것과 **같은 판단·같은 방어**다.
> (§8-D 「토큰 6종」 행은 **7종**으로 현행화한다 — I절 ⓓ.)
>
> **5. 제어 흐름 — 좁은 try와 그 밖의 전부.**
> ```python
> @route
> def reset_all(self, confirm_token=None, confirm_text=None):
>     # 이 try가 답하는 질문은 「registry를 읽고 이해할 수 있나」 **하나**다. 넓히면 fresh 저장
>     #   실패(격리 실패도 `RegistryError`다 — §7-4′ 6항)가 다시 fresh 확인 발급으로 먹혀
>     #   사용자가 같은 확인창을 무한히 다시 본다.
>     # 구조적으로도 안전하다: `except` 절 **안에서** 난 예외는 같은 `try`가 다시 잡지 않는다
>     #   (파이썬 의미론). 아래 `_reset_fresh`가 올리는 것은 `@route`의 봉투로 곧장 나간다.
>     try:
>         reg = store.load_registry()
>         _reset_preflight(reg)
>     except store.RegistryError as exc:
>         return self._reset_fresh(exc, confirm_token, confirm_text)
>     ... 현행 정상 갈래 그대로(확인 params에 mode="normal" 추가, 성공 봉투에 mode="normal" 추가) ...
>
> def _reset_fresh(self, exc, confirm_token, confirm_text):
>     """손상 registry의 탈출 갈래. 게임을 하나도 순회하지 않는다 — 열거할 수 없는 상태가 전제다."""
>     fp = _reset_fresh_fingerprint(exc.code)
>     if not _consume(confirm_token, "*", _RESET_FRESH_SCOPE, fp, confirm_text or ""):
>         return _fail(codes.CONFIRM_REQUIRED,
>                      mode="fresh",
>                      confirm_token=_issue("*", _RESET_FRESH_SCOPE, fp, _RESET_CHALLENGE),
>                      challenge=_RESET_CHALLENGE)
>     # 감사 로그는 쓰기보다 먼저(기존 관례). 격리 경로는 성공 뒤에 한 줄 더 남긴다.
>     decky.logger.info("reset_all fresh session=%s cause=%s", SESSION, exc.code)
>     quarantined = store.save_fresh_registry()        # 실패는 RegistryError로 그대로 올린다
>     decky.logger.info("reset_all fresh done session=%s quarantined=%s", SESSION, quarantined)
>     return _ok(mode="fresh", results=[], counts={}, cleared={"named": 0, "excluded": 0})
> ```
>
> **6. 저장 — `save_registry`를 **부르지 않는** 전용 경로.**
> `store.save_registry`는 **직전 파일이 JSON으로 파싱되기만 하면** `.bak`으로 승격한다(shape는 안 본다) —
> fresh 갈래가 그것을 지나면 **JSON-valid 손상본이 정상 `.bak`을 덮는다.** 그래서 전용 helper를 둔다.
> ```python
> _CORRUPT_SEQ_MAX = 100
>
> def save_fresh_registry():
>     """손상 원문을 격리한 뒤 공장초기 registry를 쓴다. 격리 디렉터리 경로를 돌려준다.
>
>     `save_registry`를 부르지 않는 것이 이 함수의 존재 이유다(위 문단).
>     **인자를 받지 않는 것이 두 번째 안전장치다**: 밖에서 만든 dict가 이 문으로 들어올 수 없어
>     `_save_registry`(문 ② 버전 가드)를 지나지 않아도 `version`이 언제나 현재 값이다 —
>     §14-F의 *"탈출을 허용하는 것은 예외 분기가 아니라 데이터 자체다"*와 같은 문법이고,
>     여기서는 **함수 시그니처가 그 데이터를 강제한다.**
>     `.bak`은 건드리지 않는다(rotate 없음) — 손상 이전의 정상 `.bak`이 남는 것이 이 갈래의 계약이다.
>     """
>     path = registry_path()
>     base = "%s.corrupt-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
>     holder = None
>     for seq in range(1, _CORRUPT_SEQ_MAX + 1):
>         candidate = base if seq == 1 else "%s-%d" % (base, seq)
>         try:
>             # 이름 확보는 `mkdir`의 EEXIST가 **구조로** 한다. `os.path.exists` 검사 뒤
>             #   `os.replace`를 쓰면 검사와 rename 사이에 목적지가 생겨도 조용히 덮고,
>             #   dangling symlink는 `exists`가 거짓이라 아예 못 본다. `mkdir`은 그 둘을 다
>             #   EEXIST로 거부한다 — 손상 원문은 사본이 없는 증거라 덮어쓰기를 구조로 막는다.
>             os.mkdir(candidate)
>         except FileExistsError:
>             continue
>         except OSError as exc:
>             # ★ 19판 4판 정정 — EEXIST 아닌 실패(권한·ENOSPC·읽기 전용 마운트 등)를 여기서
>             #   봉투화한다. 안 잡으면 이 함수가 `OSError`를 그대로 올려 route의 마지막 갈래에서
>             #   **익명 `UNEXPECTED`**가 되는데, 그것은 5항이 좁은 try를 정당화하며 든 전제
>             #   («격리 실패도 `RegistryError`다»)를 깨뜨린다. 아무것도 쓰지 않은 상태이므로
>             #   문구의 "프로필과 백업은 바뀌지 않았습니다"가 이 자리에서 참이다.
>             raise RegistryError(
>                 "거부: 손상된 레지스트리를 치울 자리를 만들지 못했습니다 — %s: %s: %s"
>                 % (candidate, type(exc).__name__, exc), code=codes.REGISTRY_UNREADABLE)
>         holder = candidate
>         break
>     if holder is None:
>         raise RegistryError(
>             "거부: 손상된 레지스트리를 치울 이름을 얻지 못했습니다 — %s (…-%d까지 시도)"
>             % (base, _CORRUPT_SEQ_MAX), code=codes.REGISTRY_UNREADABLE)
>     try:
>         # 목적지는 방금 만든 빈 디렉터리 안이라 **반드시 비어 있다** — 유형(일반 파일·심링크·
>         #   디렉터리)에 관계없이 rename이 성립하고, 심링크는 링크 자신만 옮겨진다(대상 무접촉).
>         os.replace(path, os.path.join(holder, os.path.basename(path)))
>     except OSError as exc:
>         # 격리에 실패하면 **아무것도 쓰지 않는다.** fresh 쓰기는 `atomic_write`가 이 경로를
>         #   덮는 일이라, 원문을 치우지 못한 채 진행하면 유일한 증거를 지운다.
>         raise RegistryError(
>             "거부: 손상된 레지스트리를 치우지 못해 초기화를 중단했습니다 — %s → %s: %s: %s"
>             % (path, holder, type(exc).__name__, exc), code=codes.REGISTRY_UNREADABLE)
>     atomic_write(path, json.dumps(default_registry(), indent=2,
>                                   ensure_ascii=False).encode("utf-8"))
>     return holder
> ```
>
> **6-1. 격리 규칙 — 적용 범위와 크래시 안전성.**
> - **유형을 묻지 않는다.** 일반 파일·심링크·디렉터리·읽기 불가 파일 전부 같은 경로를 지난다. 읽어서 복사하는
>   방식은 *정확히 필요한 경우*(chmod 000)에 실패하고, 유형별 분기는 새 실패 축을 만든다.
> - **적용 범위는 fresh 갈래뿐이고, dangling 심링크는 여기 오지 않는다**: `load_registry`는
>   `os.path.exists(path)`가 거짓이면 **즉시 `default_registry()`를 돌려준다** — dangling 심링크는 그 검사에서
>   「파일 없음」이라 오류가 나지 않고, 따라서 **정상 갈래**로 간다. 그 갈래에서 `atomic_write`가 심링크 자신을
>   새 registry로 대체하는 것은 **19판이 만드는 동작이 아니라 현행 동작**이다(이 초안은 그것을 바꾸지 않는다).
> - **크래시 중간 상태 3종이 모두 안전하다** — 내구성을 fsync에 걸지 않는다(`atomic_write`는 디렉터리 fsync가
>   실패해도 새 이름이 제자리면 **경고로 접는다** — 그래서 *"fsync가 하므로 내구화된다"*는 보장이 아니다):
>   ① `mkdir` 뒤 중단 → 빈 `.corrupt-*` 디렉터리 하나가 남고 registry는 그대로 → 다음 실행이 다시 fresh로 들어와
>   새 이름으로 성공한다(잔여는 §15-D E61) ② `os.replace` 뒤 중단 → `registry.json`이 없다 → `load_registry`가
>   `default_registry()`를 돌려주므로 **플러그인은 빈 목록으로 정상 동작한다**(탈출은 사실상 완료됐다)
>   ③ 완료. **세 상태 모두 재시도 가능하고 데이터 손실이 없다.**
> - **격리 단계의 실패는 전부 `RegistryError`다**(★ 4판 명시): 이름 확보(`mkdir`)든 이동(`os.replace`)이든
>   상한 소진이든 같다 — 그래야 5항의 좁은 try가 *"격리 실패도 `RegistryError`"*라는 전제 위에 설 수 있고,
>   그 실패가 **fresh 확인 재발급으로 먹히지 않는다**(`except` 절 안에서 난 예외는 같은 `try`가 다시 잡지
>   않는다). 어느 실패든 **아무것도 쓰지 않은 상태**라 문구가 그 자리에서 참이다.
> - **`atomic_write` 실패**(격리는 성공, 새 파일 쓰기 실패)는 `OSError`가 그대로 올라 `UNEXPECTED` 봉투가 된다.
>   화면은 실패라 말하지만 **탈출은 이미 성립해 있다**(상태 ②) — 사용자가 다시 눌렀을 때 이번에는 **정상 갈래**로
>   들어가 0게임 초기화를 하고 `RESET_OK`로 끝난다. 과소 보고이고 **자기교정된다**(§15-D E60).
> - **`.corrupt-*`는 앱이 지우지 않는다**(§15-D E61). 데이터 루트를 열거하는 코드가 없어(실측) 다른 판정에 섞이지 않는다.
>
> **7. 되심기 없음.** fresh 갈래는 게임을 **한 개도 순회하지 않는다.** 손상 항목이 새 registry에 되심어지는 일도
> 없다. 비-숫자 appid 키의 처분(정상 갈래의 되심기 제외)은 §14-H ⓘ와 §15-D E59다.
>
> **8. 성공 봉투**: §7 결과 봉투 조문(개정 ③)이 정한다.

### B-3. 개정 조문 전문 ③ — §7 결과 봉투 조문 (해당 문단 대체·확장)

> - 결과 봉투(**★ 17판 · QA DEFECT-05 / ★ 19판 — `mode` 신설·부분완료 갈래**): `reset_all` 성공은
>   `_ok(mode=mode, results=results, counts=counts, cleared=cleared)`다. **`mode: "normal" | "fresh"`가
>   19판 신설 최상위 필드**이고, 나머지 세 필드의 계약(17판)은 불변이다 — `cleared`는 중첩 dict이고 `**`로 펼치지 않는다.
>   - **`mode:"normal"`**: 17판 조문 그대로. 프론트가 `parts.join(" ")`로 조각을 모은다(`RESET_OK_GAMES` /
>     `RESET_OK_NAMES` / `RESET_OK_EXCLUDED` / `RESET_LEFT_NOTE`, 네 조각이 다 안 붙으면 폴백 `RESET_OK`).
>   - **`mode:"fresh"`**: `results=[]` · `counts={}` · `cleared={named:0, excluded:0}`을 **반드시 싣는다**
>     (`SettingsPopup`이 성공 직후 `res.data.counts.deleted`·`res.data.results.length`·`res.data.cleared.named`를
>     즉시 읽는다 — 비우면 성공한 자리에서 프론트가 죽는다). 완료 문구는 **조각 조립을 타지 않고
>     `RESET_OK_FRESH` 하나**다. **`RESET_OK`로 접으면 안 된다** — *"초기화 작업을 마쳤습니다"*는 프로필
>     데이터가 지워졌다는 뜻으로 읽히는데 fresh는 그것을 하나도 안 지웠다(§7-4′ 2항). §15 R16이 기록한
>     그 유형(*"화면 문장이 실제보다 넓게 약속하거나 다른 것을 가리킨다"*)의 자리다.
>   - **부분완료(19판 — F2a)**: 마지막 registry 저장이 `OSError`로 실패하면 성공 봉투가 아니라
>     **`RESET_FAILED` 실패 봉투**다(§7-5′). fresh 갈래에서는 이 코드가 나가지 않는다(그 갈래는 아무 게임도
>     지우지 않는다 — 저장 실패의 처분은 §7-4′ 6-1이다).

### B-4. 개정 조문 전문 ④ — §8-D RPC 표 (교체·신설)

> | `reset_all` | 확인 params | ~~`excluded=len(exclude.excluded_map(reg))` 추가(§7 고지)~~ → **★ 19판: 판별 유니언**. `mode:"normal"`이면 현행 전 필드(`games`·`profiles`·`named`·`excluded`·`evicted`·`evict_games`·`challenge`), `mode:"fresh"`면 `confirm_token`·`challenge`만(§7-4′ 3항) |
> | `reset_all` | **성공 봉투(★ 17판 → ★ 19판 확장)** | `_ok(mode=..., results=..., counts=..., cleared=...)` — **`mode: "normal"\|"fresh"` 최상위 신설**. `cleared:{named,excluded}`(17판)는 불변. fresh는 세 필드를 **빈 값으로 반드시 싣는다** |
> | `reset_all` | **실패 봉투(★ 19판 — F2a)** | 마지막 `_save_registry(fresh)`의 `OSError`만 좁게 잡아 **`RESET_FAILED`**(§7-5′). `RegistryError`는 그대로 올린다 |
>
> `rpc.ts` 바인딩 추가(§8-D 코드 블록):
> ```ts
> // ── 19판 ──────────────────────────────────────────────────────────────────
> // ResetConfirmParams = ResetNormalConfirmParams | ResetFreshConfirmParams  (판별자 `mode`)
> // ResetAllResult에 mode: "normal" | "fresh"
> // makeResetConfirmSpec의 매개변수는 ResetNormalConfirmParams로 좁는다(유니언을 그대로 받으면 컴파일 불가)
> ```

### B-5. 개정 조문 전문 ⑤ — 프론트 3파일 전문

⚠️ **★ 19판 3판 정정 — 「그대로 쓴다」의 범위.** ⑤-2·⑤-3은 실물과 대조 완료된 전문이라 **그대로 쓴다.**
⑤-1(`rpc.ts`)만 다르다: **정본인 것은 타입 구조와 19판이 신설한 주석뿐이고, 현행 주석은 보존·병합한다.**
아래 ⑤-1은 갈래를 보여주려고 기존 설명을 압축했는데, 그 압축본을 그대로 붙이면 **직전 주석 캠페인이
다듬은 문장이 사라진다.** 주석은 조문이 아니라 **코드 옆에 남아 그 자리를 여는 사람이 읽는 정본**이므로,
설계 초안이 조용히 줄일 대상이 아니다.

**보존 대상은 다음 7블록이다**(현행 `src/rpc.ts` — 심볼로 지목):

| # | 자리 | 현행 주석이 들고 있는 것 | ⑤-1의 압축본 |
|---|---|---|---|
| ⓐ | `ResetConfirmParams.named` | *"표시명은 registry settings에 살아서 전체 초기화에 같이 지워진다 — 모르고 잃지 않게 확인창이 미리 말한다"* | *"사용자가 직접 정한 표시명의 개수. 0이면 그 줄을 안 그린다."* |
| ⓑ | `ResetConfirmParams.excluded` | *"초기화는 registry를 통째로 갈아 끼우므로 제외 목록도 같이 지워진다 — 모르고 잃지 않게…"* | 한 줄로 축약 |
| ⓒ | `ResetConfirmParams.challenge` | 번역 금지 이유 + *"백엔드가 준 값을 그대로 보여주고 그대로 대조한다"* | 마지막 문장 소실 |
| ⓓ | `ResetConfirmParams.evicted` | *"초기화는 게임마다 슬롯 본체를 대피시키므로 링이 찬 게임에서는 오래된 백업이 밀려난다. 이름은 대지 않는다(게임이 여럿이다)"* | 한 줄로 축약 |
| ⓔ | `ResetAllResult.cleared` | **3문단** — 「왜 결과 봉투가 들고 오나」·「프론트가 다시 세지 않는다」·「게임별 실패와 무관하게 유효한 이유(`fresh["games"] = dict(reg["games"])`)」 | 한 줄 |
| ⓕ | `cleared.named` 필드 주석 | *"0이면 완료 문구가 그 줄을 그리지 않는다"* | **소실**(필드 주석 자체가 없다) |
| ⓖ | `cleared.excluded` 필드 주석 | 동상 | **소실** |

**병합 규칙**: 필드가 그대로 남는 자리(ⓐ~ⓓ·ⓔ~ⓖ)는 **현행 주석 본문을 유지하고**, 19판이 더하는 사실
(`mode` 판별자 · fresh에서 셋이 빈 값 · fresh에서 `cleared`가 둘 다 0)만 **덧붙인다.** ⑤-1의 문장을
현행 문장으로 **대체하지 않는다** — 두 문장이 같은 사실을 말하면 현행 쪽을 남긴다.
**⑤-1이 새로 정하는 것**은 다음 넷이고, 이것만이 그 코드 블록의 정본 부분이다:
① `ResetMode` 타입 신설 ② `ResetConfirmBase` 분리와 `ResetNormalConfirmParams`/`ResetFreshConfirmParams`
유니언 ③ `mode`를 **두 갈래에 모두** 싣는 이유(§3-A 12판 C-1 선례) ④ fresh가 **수를 싣지 않는 것이 계약**
이라는 진술과 `ResetAllResult.mode` 주석.
**⑤-2·⑤-3은 이 단서의 대상이 아니다** — ⑤-2는 *"본문은 한 글자도 바꾸지 않는다"*가 이미 조문이고(시그니처
한 줄만 바뀐다), ⑤-3은 현행 인라인 콜백 형태를 그대로 승계했다. **둘 다 실물과 대조 완료**
(`makeResetConfirmSpec`의 4인자 시그니처 · `runReset`의 `runMutation(() => resetAll(token, text), …)` 형태).

**⑤-1. `rpc.ts` 타입** (현행 `ResetConfirmParams` 단일 인터페이스와 `ResetAllResult`를 대체 — **위 단서대로 주석은 병합**):

```ts
/** 초기화가 실제로 한 일의 갈래. 두 갈래는 **지우는 대상이 다르다**(§7-4′ 2항) —
 *  화면이 그 차이를 말해야 하므로 봉투가 판별자를 싣는다. */
export type ResetMode = "normal" | "fresh";

/**
 * reset_all이 CONFIRM_REQUIRED로 돌려주는 params. 아직 아무것도 지워지지 않았다.
 *
 * 판별자는 `mode` 한 필드이고 **두 갈래에 모두** 싣는다 — 한쪽에만 두고 「없으면 저쪽」으로
 *   읽으면 필드가 빠진 봉투가 조용히 반대 갈래로 간다. 같은 함정을 이 프로젝트는 이미 한 번
 *   겪었다(§3-A 12판 C-1: `ready`가 undefined일 때 `ready===0`만 보면 버튼이 활성이 됐다).
 * 프론트의 판별자 관례가 `kind`인 것(popup.tsx의 DView·ConfirmSpec)과 충돌하지 않는다 —
 *   그쪽은 **프론트가 만들어 프론트가 읽는 뷰·스펙**의 판별자이고 이것은 **백엔드 봉투**의
 *   필드다. 층이 다르고, 이름이 같으면 오히려 `BackupKind`("백업 종류")와 뜻이 겹친다.
 */
export interface ResetConfirmBase {
  confirm_token: string;
  /**
   * 사용자가 그대로 입력해야 하는 확인 단어. 번역하지 않는다 — i18n에 넣으면 화면이 보여주는
   * 단어와 백엔드가 대조하는 상수가 언어에 따라 갈려 입력이 영영 안 맞는다.
   * fresh 갈래도 2단 방어를 유지한다(되돌릴 수 없다는 성격은 같다).
   */
  challenge: string;
}

/** 정상 갈래 — registry를 읽었고, 무엇을 지우는지 셀 수 있다. */
export interface ResetNormalConfirmParams extends ResetConfirmBase {
  mode: "normal";
  /** 파괴 내역 — 화면이 다시 세지 않는다(두 곳에서 세면 언젠가 어긋난다). */
  games: number;
  profiles: number;
  /** 사용자가 직접 정한 표시명의 개수. 0이면 그 줄을 안 그린다. */
  named: number;
  /** 감지 제외 목록의 건수. 0이면 그 줄을 그리지 않는다. */
  excluded: number;
  /** 이 초기화로 밀려날 백업 건수와 그런 게임 수. 0이면 그 줄을 그리지 않는다. */
  evicted: number;
  evict_games: number;
}

/**
 * 손상 복구 갈래 — registry를 읽지 못했다.
 *
 * **수를 싣지 않는 것이 계약이다.** 무엇이 등록돼 있었는지 셀 수 없는 상태이므로, 0을 그리면
 *   화면이 거짓을 말한다(§7-4′ 3항). 이 갈래가 지우는 것은 게임 목록 파일 하나뿐이고
 *   프로필·백업은 하나도 지우지 않는다 — 확인창 문구가 그 사실을 말한다.
 */
export interface ResetFreshConfirmParams extends ResetConfirmBase {
  mode: "fresh";
}

export type ResetConfirmParams = ResetNormalConfirmParams | ResetFreshConfirmParams;

export type ResetOutcome = "deleted" | "refused" | "error";

export interface ResetRow {
  appid: string;
  name: string;
  outcome: ResetOutcome;
  /** `refused`/`error`일 때만 값이 있다. 화면은 `note`가 아니라 이것으로 사유를 가른다. */
  code?: string | null;
  note: string;
}

export interface ResetAllResult {
  /**
   * 어느 갈래로 끝났나(§7-4′ 2항). `"fresh"`면 아래 셋은 전부 빈 값이고, 완료 문구는
   * 조각 조립을 타지 않고 `RESET_OK_FRESH` 하나다 — `RESET_OK`("초기화 작업을 마쳤습니다")로
   * 접으면 지우지 않은 프로필 데이터를 지웠다고 말하게 된다.
   */
  mode: ResetMode;
  results: ResetRow[];
  counts: Partial<Record<ResetOutcome, number>>;
  /** 초기화가 실제로 지운 registry settings 범주의 건수. fresh에서는 둘 다 0이다. */
  cleared: {
    named: number;
    excluded: number;
  };
}
```

**⑤-2. `confirmSpecs.tsx` — 정상 spec의 매개변수 타입 개정 + fresh spec 신설.**

> **현행**(`confirmSpecs.tsx`, `makeResetConfirmSpec` 시그니처):
> ```tsx
> export function makeResetConfirmSpec(
>   params: ResetConfirmParams,
>   initial: string, ...
> ```
> 본문이 곧바로 `params.games`·`params.profiles`·`params.named`·`params.excluded`·`params.evicted`·
> `params.evict_games`를 읽는다.
>
> **개정**: 매개변수 타입을 **`ResetNormalConfirmParams`로 좁힌다.** 본문은 한 글자도 바꾸지 않는다.
> ```tsx
> export function makeResetConfirmSpec(
>   params: ResetNormalConfirmParams,          // ★ 19판 — 유니언을 그대로 받으면 fresh 구성원에
>   initial: string,                           //   없는 6필드 접근이 TypeScript 오류다
>   onOK: (value: string) => void,
>   onInputSnapshot?: (value: string) => void,
> ): InputConfirmSpec { /* 본문 무변경 */ }
> ```
> `import` 목록의 `ResetConfirmParams`도 `ResetNormalConfirmParams`로 바꾼다.
>
> **fresh 전용 spec 신설**:
> ```tsx
> /**
>  * 손상 복구 초기화 확인 — 정상 초기화와 **지우는 대상이 다르다**(§7-4′ 2항).
>  * 2단 방어(토큰 + type-to-confirm)는 같고, 파괴 규모 고지가 수가 아니라 **범위 진술**이다:
>  *   셀 수 없는 상태이므로 수를 그리지 않는다.
>  */
> export function makeResetFreshConfirmSpec(
>   params: ResetFreshConfirmParams,
>   initial: string,
>   onOK: (value: string) => void,
>   onInputSnapshot?: (value: string) => void,
> ): InputConfirmSpec {
>   return {
>     kind: "input",
>     title: t("RESET_CONFIRM_TITLE"),                 // "전체 초기화할까요?" 재사용
>     warnBlock: <div>{t("RESET_FRESH_CONFIRM_WARN")}</div>,
>     body: (
>       <div style={COLUMN_STYLE}>
>         {/* 회색(META) — 정상 초기화·등록 해제 확인창의 같은 키와 같은 판단이다. */}
>         <div style={META_STYLE}>{t("MANAGE_KEEP_CONFIG")}</div>
>         <div>{t("RESET_CONFIRM_TYPE", { word: params.challenge })}</div>
>       </div>
>     ),
>     okText: t("RESET_CONFIRM_OK"),
>     input: { label: t("RESET_CONFIRM_FIELD_LABEL"), initial },
>     okDisabled: (value) => value !== params.challenge,
>     onOK,
>     onInputSnapshot,
>   };
> }
> ```

**⑤-3. `SettingsPopup.runReset` — 두 분기**(현행 인라인 콜백 형태를 유지한다):

```tsx
      runMutation(() => resetAll(token, text), "RESET_ACTION_FAILED", (res) => {
        if (res.ok) {
          if (res.data.mode === "fresh") {
            /* 조각 조립을 타지 않는다 — fresh는 프로필 데이터를 하나도 안 지웠다(§7-4′ 2항).
               `RESET_OK`("초기화 작업을 마쳤습니다")로 접으면 화면이 실제보다 넓게 말한다. */
            setNote(t("RESET_OK_FRESH"));
            resetTyped.current = "";
            return;
          }
          /* …현행 17판 조각 조립(deleted / cleared.named / cleared.excluded / left)… */
          return;
        }
        if (res.code === "CONFIRM_REQUIRED") {
          const p = res.params as unknown as ResetConfirmParams;
          /* 콜백 둘은 현행 인라인 그대로다 — 두 spec이 함께 쓰도록 이름만 준다. */
          const onOK = (value: string) => { void runReset(p.confirm_token, value); };
          const onSnapshot = (value: string) => { resetTyped.current = value; };
          switch (p.mode) {
            case "fresh":
              // 토큰이 안 돌아가면 아무것도 지워지지 않는다 — 이 문구가 참인 자리다.
              gate(makeResetFreshConfirmSpec(p, resetTyped.current, onOK, onSnapshot),
                   "MANAGE_MODAL_FAILED", setNote);
              return;
            case "normal":
              gate(makeResetConfirmSpec(p, resetTyped.current, onOK, onSnapshot),
                   "MANAGE_MODAL_FAILED", setNote);
              return;
            default:
              /* 타입상 도달 불가이나 런타임 방어를 남긴다 — 확인창을 못 그리면 아무것도 안
                 지운다(fail-closed). 모르는 mode를 정상으로 접으면 수 자리가 undefined로
                 렌더되고, fresh로 접으면 파괴 규모 고지가 통째로 빠진다. 둘 다 안 된다. */
              setNote(tCode(res.code, "RESET_ACTION_FAILED"));
              return;
          }
        }
        // 토큰 발급 전 또는 확정 실행 중의 실패다(RESET_FAILED도 여기를 지난다 — §7-5′).
        setNote(tCode(res.code, "RESET_ACTION_FAILED"));
      }),
```
`switch`의 `case "normal"`에서 `p`는 `ResetNormalConfirmParams`로 좁혀지므로 ⑤-2의 개정 시그니처와 맞는다.
`default` 절은 `p`를 건드리지 않으므로 `never` 좁힘과 충돌하지 않는다.

### B-6. 근거

- **탈출로가 실제로 없었다**는 것이 출발점이다. 실측: 비-dict `settings` 하나로 전 route가 `AttributeError`에
  죽고 `reset_all`도 첫 줄에서 같이 죽는다 — 17판 S-02가 *"정직한 실패"*라 부른 상태의 실질은 **인앱 복구 수단 0**이었다.
- **`CONFIRM_REQUIRED` 유지**: 확인 게이트 배관은 코드 하나로 열린다. 신설 코드를 만들면 배관이 둘이 되고,
  둘째 배관은 손상 상태에서만 도는 **아무도 안 밟는 코드**가 된다(§14-D가 fence에서 배운 종류의 위험).
- **`mode`를 두 갈래에 모두 싣는 근거**는 §3-A 12판 C-1 선례다.
- **fresh 완료 문구를 따로 두는 근거**는 §15 R16 관측이다.
- **`.bak` 우회의 근거는 실물 인용**: `save_registry`는 `json.loads(previous.decode("utf-8"))`만 확인하고
  `atomic_write(path + ".bak", previous)`를 한다 — shape 손상본은 정말 승격된다(REVIEW-F1A §4).

### B-7. 파급

| 대상 | 내용 |
|---|---|
| 백엔드 | `main.reset_all`(preflight·fresh·`mode`) · `main._reset_preflight`·`_reset_fresh`·`_reset_fresh_fingerprint`·`_RESET_FRESH_SCOPE` · **`store.save_fresh_registry()`·`_CORRUPT_SEQ_MAX` 신설** |
| 프론트 | `rpc.ts`(⑤-1 — **타입 구조만 정본, 현행 주석 7블록은 보존·병합**) · `confirmSpecs.tsx`(⑤-2 — **정상 spec 시그니처 개정 포함**) · `SettingsPopup.tsx`(⑤-3) |
| i18n | **신설 2키** `RESET_FRESH_CONFIRM_WARN`·`RESET_OK_FRESH`(J절) |
| 주석(F1-d) | `SettingsPopup.tsx`의 *"즉 이것은 손상 복구의 탈출구가 아니다"* · `main.reset_all` docstring의 토큰 지문 서술 · `rpc.ts`의 *"전체 초기화 = 개별 삭제의 반복"* 설명 · `main._save_registry`의 *"reset_all도 여기를 지난다"*(I절 ⓖ) |
| 한계 | **§14-F의 ⚠️ 알려진 한계가 닫힌다**(L절) · E60·E61 신설 |
| 검사 | QAPLAN G1 「F1-b 전용 행」(토큰 재계산 거부 · `.bak` 해시 불변 + `.corrupt-*` 생성 · chmod 000 탈출) + G4 U5·preflight 확장 행(**★ 3판 — 비-int version 4세계 포함**) |
| 실기 | **하지 않는다** — 손상 registry를 실기기에 만들지 않는다(QAPLAN §4-3). 정상 갈래 무회귀(확인창 → 취소)만 본다 |

---

## C절. 항목 단위 손상 — 공용 술어와 신설 코드 (F1-c)

### C-0. 현행 조문 인용

§8-D 말미(`:1652`, 「손상 registry 정규화 규칙 (Codex D-08 — 신설 봉투 필드 공통)」):

> 신설 필드는 전부 "raw registry 값"이 아니라 **표시용 정규화 값**이다 — `config_path`: str 아니면 `""` … `_excluded_rows(reg)`: … **개별 항목도 값이 dict가 아니면 그 항목을 결과에서 제외(격리)하고 로그 1줄**을 남긴다.

`codes.py`에 **LOOKUP 계열 코드가 없다**(실측 — 상수 34개 전수).

### C-1. 개정 조문 전문 — §8-D 정규화 규칙 확장

> **손상 registry 정규화 규칙(Codex D-08 — 신설 봉투 필드 공통 / ★ 19판 — 항목 자체로 확대)**:
> - (기존 3항 불변)
> - **★ 19판 — `games`의 항목(entry)도 같은 규칙을 받는다.** 항목 값이 dict가 아니거나 `config_path`가
>   문자열이 아니면 **손상 항목**이다. 처분은 **층에 따라 셋으로 갈린다** — 같은 사실에 대해 층마다 할 일이 다르다.
>
> **층을 가르는 기준은 이름도 호출 여부도 아니고, 관측 가능한 이 한 문장이다(★ 19판 4판 정정):**
> > **이 자리가 `Refused(REGISTRY_ENTRY_CORRUPT)`를 냈을 때, 손상 항목에 대해 오늘 나가던 「성공 답」이
> > 하나라도 사라지면 보존 계열이다. 하나도 사라지지 않으면 실행 계열이다.**
>
> **셋을 함께 못 박아야 이 문장이 재현된다**:
> ① **반사실 질문이다** — *그 자리만* `Refused`로 바꿨을 때를 묻는다. 하류의 다른 자리가 또 거부하는지는
>    이 질문에 들어오지 않는다(그건 그 자리의 배정이 답한다).
> ② **「성공 답」의 단위는 그 appid에 대해 화면이 받는 답**이다 — 봉투가 `ok:true`이면서 그 항목에 대해
>    거부·오류가 아닌 것. **일괄 route(`apply_all`·`reset_all`)에서는 봉투가 아니라 그 게임의 행이 단위다** —
>    그 봉투는 게임별 실패와 무관하게 **언제나 `ok:true`**라 봉투로 재면 아무것도 못 가른다.
>    (`main._fail`은 `{"ok": False, …}`를 내므로 `CONFIRM_REQUIRED`는 성공이 **아니다**.)
> ③ **「지나는가」로 재지 않는다.** 3판까지의 *"그 호출자를 **지나는** route가 `ok:true`를 내는가"*는
>    **재현되지 않는 기준이었다**: `engine.disk_state`는 `restore.needs_confirm`의 `already` 성공을 **지나지만**,
>    그 자리가 거부해도 그 성공은 **살아남는다**(호출자 다섯이 전부 `Refused`를 접는다). **지나는 것과
>    거는 것은 다르다** — 재는 것은 통과 경로가 아니라 **의존**이다.
>
> **F1 합격 조건 문장의 「살아 있던 route」와 같은 것을 재는 것도 이 문장의 목적이다** — 기준과 합격선이 다른
> 것을 재면 조문이 합격선을 조용히 깎는다. **19판에 이 전칭 명제의 예외는 0건이다.**
> 「`game_or_fail`을 지나는가」도 기준이 **아니다.** 그 함수는 미등록 판정의 문일 뿐이고, 지나는 것들 중에는
> 반환 entry를 **쓰지 않는** 것도 있다. 기준을 호출 여부로 잡으면 **오늘 `ok:true`를 내는 route 둘이 19판에서
> 죽는다**(`main.list_backups` · `main.restore_backup`의 슬롯 `already` — C-2 근거).
> 배정 결과는 자리마다 다시 판단하지 않도록 **§14-H 층별 판별표에 전수로 못 박는다.**
>
> | 층 | 처분 | 이유 |
> |---|---|---|
> | **실행 계열** — 오늘 `ok:true`가 없는 자리(`engine.disk_state`·`save_profile`·`apply_profile`·`restore_backup`·**`add_game`** · `confirm.needs_confirm`·`apply_needs_confirm`·`already_registered`) | `Refused(REGISTRY_ENTRY_CORRUPT)` | 손상 항목 위에서 쓰기를 하면 무엇을 덮는지 모른다. **모르면 거부**가 이 프로젝트의 가드 방향이다. **잃는 성공이 없으므로** 앞에서 거부하는 것이 순이득이다 — 오늘 그 자리들이 내는 것은 익명 `UNEXPECTED`이거나, 확인창을 띄워 승인까지 받은 뒤의 죽음이다(`engine.save_profile`의 meta 접기 주석이 *"묻기는 하고 못 고치는 상태"*라 부른 그것) |
> | **조회·집계·보존 계열** — 오늘 `ok:true`가 있는 자리(`get_overview`의 **정렬 키와 목록 조립** · `main._profile_total` · **`main.list_backups`** · `reset_all` row 조립 · `engine.apply_all` row 조립 · **`restore.needs_confirm`** · **`restore.target_sha1`**) | **`require_intact=False`** + 그 자리에서 **비-dict 접기 / isinstance 격리**(값은 **「모름」**) | 항목 하나가 화면 전체를 죽이지 않는다는 것이 명문 설계이고, **오늘 나가던 성공을 19판이 회수하지 않는다**는 것이 F1 합격 조건이다. **이름 폴백 문자열은 각 자리의 기존 값을 그대로 쓴다**(현재 `"appid 570"`/`"570"` 혼재의 통일은 화면 문구 변경이라 이번 범위 밖 — 백로그) |
> | **삭제 계열**(`remove.delete_preview` · `remove.delete_game_data`) | **검증을 우회한다**(`require_intact=False` + 비-dict를 `{}`로 접기) | 손상 항목을 치우는 것이 그 경로의 **존재 이유**다. 여기서 막으면 사용자가 그 항목에서 영영 못 빠져나온다(§14-G ⓐ가 *"막아서 잃는 것이 더 크다"*로 판정한 것과 같은 형태) |
>
> **술어는 하나다.** `engine` 안의 헬퍼 하나(`engine.entry_corrupt`)로 두고 **새 모듈 의존을 만들지 않는다**
> (`labels` 등에 얹으면 엔진이 정책 모듈을 알게 된다). **★ 4판 — 이름 앞에 밑줄을 두지 않는다**: 정책층의
> 미러(`confirm._preview_one`)가 이 술어를 **부르는 것이 정본**이라 모듈 공개여야 한다. 문은 `engine.game_or_fail` 하나를 유지하고, **실행 계열이 아닌 호출자는
> 인자로 그 사실을 선언**한다 — 문을 둘로 만들면 언젠가 한쪽에 가드가 빠진다(§14-C가 복원에서 한 판단과 동형).
> ```
> engine.game_or_fail(reg, appid, require_intact=True)
>     entry is None                    → Refused(GAME_NOT_REGISTERED)     # 미등록 계약 불변
>     require_intact and 손상          → Refused(REGISTRY_ENTRY_CORRUPT)
>     그 밖                            → entry 그대로
> ```
> **`require_intact=False`가 뜻하는 것을 한 줄로 못 박는다**: *"`None`이 아니면 통과시키고, 못 믿는 값의 처리는
> **부르는 쪽이 자기 자리에서** 한다."* 그래서 그 호출자는 **반드시** 다음 둘 중 하나를 함께 한다 —
> ⓐ 반환을 쓰면 **비-dict를 `{}`로 접는다**(`entry.get(...)`이 그 자리에서 죽지 않게: `remove` 삭제 2함수 ·
> `restore.needs_confirm`) ⓑ 반환을 안 쓰면 **아무것도 하지 않는다**(`main.list_backups`).
> **접기를 빠뜨리면 인자가 가드를 끈 것과 같아진다.**
>
> ⚠️ **`{}`(빈 dict) 항목의 처분이 층마다 갈린다 — 의도된 것이다.** 지금은 `{}`가 falsy라 **모든 자리에서**
> `GAME_NOT_REGISTERED`가 나가는데, `games`에 키가 있으므로 **「미등록」은 거짓**이다. 19판부터
> **실행 계열은 `REGISTRY_ENTRY_CORRUPT`**(손상이라고 정직하게 말한다), **`require_intact=False` 계열은
> 통과**(그래서 `{}` 항목도 **삭제로 치울 수 있고 백업 목록도 뜬다** — 오늘은 둘 다 「미등록」으로 막힌다).
> 두 처분 모두 오늘보다 사용자가 할 수 있는 일이 늘어난다. 앱이 만드는 상태가 아니다
> (`engine.add_game`은 언제나 `config_path`를 심는다).
>
> **`confirm.needs_confirm`·`confirm.already_registered`에도 같은 술어를 적용한다** — 이 둘은 `game_or_fail`을
> **직접 부르지 않는다**(전자는 `engine.disk_state` 경유의 `Refused`를 자기 `except`가 삼킨 뒤
> `store.game(reg, appid) or {}`로 낙하하고, 후자는 `reg["games"]`를 직접 읽는다). 그래서 **반환이 truthy든
> falsy든 비-dict면 같은 `Refused(REGISTRY_ENTRY_CORRUPT)`**를 낸다 — `or {}`가 falsy 비-dict(`0`·`""`·`[]`)를
> **「미등록」으로 오진**하던 갈래도 함께 닫힌다. **`already_registered`가 막는 문 하나가 더 있다**:
> `engine.add_game`의 `reg["games"].setdefault(appid, {})` → `entry.update({...})`는 truthy 비-dict에서 그 자리
> `AttributeError`를 내는데, 제품 route에서는 이 판정이 **먼저** 거부하므로 그 사망점에 도달하지 않는다
> (엔진 쪽에 술어를 따로 심지 않는 이유 — §14-H ⓙ).
> **미등록(`None`) 계약과 빈 슬롯 저장 계약(`bodies`가 없으면 `need=False`)은 불변이다.**
>
> **미리보기의 미러 판정도 같은 술어를 쓴다(★ 19판 3판 정정).** `confirm._preview_one`은 엔진을 부르지 않고
> 같은 결론을 **재현**하는 자리다(그 함수의 독스트링: *"판정 순서 = 엔진 실행 순서다"*). 그래서 판정이 갈리면
> **미리보기↔실행 동치가 그 자리에서 깨진다** — `config_path`가 truthy 비-문자열(예: `123`)이면 미리보기는
> `would_apply`, 실행은 `refused(REGISTRY_ENTRY_CORRUPT)`이고 `ALLOWED["would_apply"] = {"applied"}`가
> 그것을 실패로 잡는다. 현행 truthiness 검사를 **truthiness와 형 술어 둘 다**로 바꾼다 — **어느 한쪽으로
> 교체하지 않는다.** **★ 4판 — 형 조건은 술어를 「다시 적지 않고」 부른다**(같은 사실을 두 벌 적으면
> 언젠가 갈린다. §14-H ⓛ과 이 조문이 3판에서 갈려 있었다 — 이 형태가 정본이다):
> ```
> entry = (reg.get("games") or {}).get(str(appid))
> if engine.entry_corrupt(entry) or not entry.get("config_path"):
>     return "cannot_apply"
> ```
> **술어를 부르려면 헬퍼가 모듈 공개여야 한다** — `engine` 안에 두되 **이름 앞의 밑줄을 뺀다**
> (`engine.entry_corrupt`). 새 모듈 의존은 생기지 않는다(`confirm`은 이미 `engine`을 import한다:
> `game_or_fail`·`disk_state`·`running_game`). `game_or_fail`도 같은 헬퍼를 쓰므로 **술어는 한 벌이다.**
> **truthy 비-dict entry에서 `.get`이 먼저 죽는 문제는 단축 평가가 답한다**: `entry_corrupt(entry)`가 참이면
> `or`의 오른쪽은 **평가되지 않는다.** 순서를 뒤집으면 그 자리에서 `AttributeError`가 난다 — **조건의 순서가
> 계약이다.** (`_preview_one`은 `reg["games"]`를 순회하는 자리에서만 불리므로 `entry`가 `None`인 경우는 없다.)
> **두 조건이 각각 다른 엔진 사실을 미러한다**: **술어 호출**은 손상 항목의 거부를 미러하고,
> **truthiness 조건**은 **빈 문자열이 손상 술어에 걸리지 않는다는 사실**을 미러한다(빈 문자열도 문자열이다).
> 빈 경로에서 엔진이 무엇을 내는지는 경로 가드가 정하는데, `os.path.realpath("")`가 **현재 작업 디렉터리**로
> 해석되므로 결말이 환경에 따라 갈린다(prefix가 있으면 `PATH_OUTSIDE_PREFIX` 거부, 없으면 뒤의 쓰기가
> `OSError` → `UNEXPECTED`). **어느 쪽이든 `cannot_apply`가 받는 결말이다**(`{"refused", "error"}`).
> **이 조건을 빼면 빈 문자열 세계가 `would_apply`로 새어 새 동치 위반이 생긴다** — 형 술어로 **교체**하는
> 것이 아니라 **더하는** 이유가 이것 하나다. 버킷은 `cannot_apply` 그대로이므로 봉투·화면·`BULK_OUTCOMES`
> 어디에도 새 갈래가 생기지 않는다.
>
> **부수 이득 둘**: ⓐ **비-dict 항목에서도 백업 목록이 뜬다**(오늘은 config-target 백업이 있으면 죽는다 —
> 그 항목의 백업 파일은 멀쩡히 남아 있는데도 그렇다) ⓑ **`{}` 항목을 삭제로 치울 수 있다.**
> **손상 항목에서 되찾을 수단이 둘 더 열린다.**

### C-2. 근거

- **지점 열거로는 안 닫힌다**는 것이 이종 검토의 실증이다 — 3곳+래퍼를 고쳐도 사망점이 남았다(`main.py` reset row
  조립 · `remove.py` · `engine.py` · `confirm.py` 2곳 · `restore.py`).
- **v3의 전제 하나가 깨져 있었다**: *"`game_or_fail`이 confirm 판정까지 덮는다"*는 거짓이다(위 인용).
- **삭제 우회의 근거**는 REVIEW-F1A §2다: 우회가 없으면 손상 항목이 **개별 삭제로도 전체 초기화로도 청소
  불능**이 되어 「탈출 완결성」이 항목 축에서 깨진다.

#### C-2-1. `game_or_fail` 호출자 전수 9자리 (★ 19판 4판 정정 — 반사실 기준으로 재작성)

**전수성의 근거**: `grep -rn "game_or_fail" --include=*.py` = 정의 1 + 프로덕션 호출 **9** + 검사 하네스 1
(`qa/test_save_no_write_when_same.py`의 `legacy_save` — 정상 registry만 다루므로 기본값 `True`로 무영향).
동적 호출·별칭은 없다(`getattr`·문자열 디스패치 0건).
**「거부하면 사라지는 성공 답」 칸이 층을 정한다** — 위 판별 기준의 반사실 질문을 자리마다 한 번씩 물은 것이고,
단위는 **그 appid에 대해 화면이 받는 답**이다(일괄 route는 봉투가 아니라 **행**).
**결손** = `config_path` 키가 없는 dict, **비-dict** = truthy 비-dict 항목.

| # | 호출자 | 이 자리가 거부하면 **사라지는 오늘의 성공 답** | **19판 배정** | 근거 |
|---|---|---|---|---|
| 1 | `engine.disk_state` | **없다.** 호출자 다섯이 **전부 `Refused`를 접는다** — `confirm._disk_state_or_none`·`restore._disk_state`·`main._disk_state_safe`는 `except`에 `engine.Refused`가 들어 있고, `engine.apply_all`·`confirm._preview_one`은 `except Exception`이다. 7번의 슬롯 `already` 성공도 **그대로 산다**(그 경로는 `restore._disk_state`를 지난다) | **실행**(`True`) | **거는 것이 없으므로 공짜다.** 오히려 **부수 이득이 크다**: 지금 새는 `KeyError`(결손)·`TypeError`(비-dict)는 그 다섯 중 `KeyError`를 안 잡는 자리에서 route를 통째로 죽이는데, 얌전한 `Refused`가 되면 **격리가 처음으로 실제 작동한다** |
| 2 | `engine.save_profile` | **없다** — 오늘 그 appid의 답은 `UNEXPECTED`(결손 `KeyError` · 비-dict `TypeError`)다 | **실행**(`True`) | 그 경로에 쓴다. 잃는 성공이 없으므로 앞에서 이름 있게 거부하는 것이 순이득 |
| 3 | `engine.apply_profile` | **없다** — 개별 route는 `UNEXPECTED`, 일괄에서는 그 게임의 **행이 `error(UNEXPECTED)`**다(봉투의 `ok:true`는 게임별 실패와 무관하므로 단위가 아니다 — 판별 기준 ②) | **실행**(`True`) | 그 경로를 덮는다 |
| 4 | `engine.restore_backup` | **없다** — 오늘 `UNEXPECTED`다 | **실행**(`True`) | 두 갈래 모두 `config_path`를 쓴다. **쓰기의 문은 이 하나로 남는다** |
| 5 | `remove.delete_preview` | **있다** — 결손 항목에서 **삭제 확인창이 정상으로 뜬다**(`ok`) | **삭제 우회**(`False` + `{}` 접기) | 결손에서 오늘 사는 것을 **계속 살리고**, 비-dict·`{}`에서 **새로 살린다**. 손상 항목을 치우는 것이 이 경로의 존재 이유다 |
| 6 | `remove.delete_game_data` | **있다** — 결손 항목에서 **삭제가 완주한다**(`ok`) | **삭제 우회**(동상) | 동상 |
| 7 | `restore.needs_confirm` | **있다** — 비-dict + **슬롯 대상** + 백업 내용 = 슬롯 본체에서 `main.restore_backup`이 엔진을 부르기 전에 **`ok(outcome="already")`**를 낸다(슬롯 갈래는 entry를 한 번도 안 읽고, `restore._disk_state`가 `TypeError`를 `None`으로 접는다) | **보존**(`False` + `{}` 접기) | **오늘 나가는 성공이므로 보존한다.** 접기 뒤 config 갈래는 `""` → `os.path.exists("")` 거짓 → `proceed`로 나가고, 실제 쓰기는 **`engine.restore_backup`(`require_intact=True`)이 `REGISTRY_ENTRY_CORRUPT`로 거부**한다 — 오늘 그 자리의 익명 `UNEXPECTED`가 이름 있는 거부가 되므로 **개선이다.** 대가는 슬롯 `confirm` 갈래의 **왕복 1회**(토큰을 받고 눌렀는데 거부) — **F1 합격 조건 문장과 바꿀 수 없는 대가다** |
| 8 | `confirm.apply_needs_confirm` | **없다** — 비-dict에서 결론은 `"confirm"`이고 route는 `_fail(CONFIRM_REQUIRED)`(=`ok:false`)를 낸다. 결손은 `_disk_state_or_none`이 `KeyError`를 안 접어 `UNEXPECTED` | **실행**(`True`) | 오늘은 승인 뒤 엔진이 죽으므로 *묻기는 하고 못 고치는 상태*이고, 앞에서 거부하는 것이 개선이다. (7과 답이 갈리는 이유는 취향이 아니라 **사라지는 성공 답의 유무** 하나다) |
| 9 | `main.list_backups` | **있다** — ⓐ 결손 dict에서는 **모든 백업 종류에서** 목록이 뜬다 ⓑ 비-dict에서도 **profile 백업만 있으면** 뜬다 | **조회**(`False`) | 반환 entry를 **쓰지 않는다**(호출문 주석이 *"미등록 → GAME_NOT_REGISTERED"*라 적어 두었다). 그래서 접기도 필요 없다 |

⚠️ **행 9의 정확한 사망 조건은 「config-target 백업의 존재」다.** `restore._TARGET_OF_KIND =
{"profile_dock": "dock", "profile_internal": "internal"}`이고 그 밖의 kind(`disk`·`unknown`)만
`TARGET_CONFIG`로 떨어지는데, **`restore.target_sha1`은 `target == TARGET_CONFIG`일 때만 registry entry를
읽는다**(슬롯 갈래는 `_slot_meta`만 본다). 그래서 **비-dict 항목 + profile 백업만**이면 오늘도 성공한다 —
**QA 오라클의 세계는 반드시 `disk`/`unknown` 백업 1건 이상이어야 한다**(그렇지 않으면 수정 전에도 통과해
오라클이 아무것도 못 잰다 — QAPLAN G1).

#### C-2-2. 판별 기준의 자기 정합 검산 (★ 4판 재작성)

기준 문장만으로 위 9자리가 **재현되는지** 역방향으로 검산한다. 절차는 셋이다:
**① 그 자리를 `Refused`로 바꾼다(그 자리만) → ② 손상 항목에 대해 오늘 나가던 답을 자리별로 나열한다 →
③ 그중 「성공 답」이 사라지는지 본다**(일괄 route는 봉투가 아니라 행을 본다).

| 판정 재료 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| 사라지는 성공 답이 있나 | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✓ |
| 기준이 지정하는 층 | 실행 | 실행 | 실행 | 실행 | 보존 | 보존 | 보존 | 실행 | 보존 |
| 위 표의 배정과 일치 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**9/9 일치 — 기준이 배정을 재현한다.**
⚠️ **3판 기준으로는 재현되지 않았다**(4판이 고친 것): *"그 호출자를 **지나는** route가 `ok:true`를 내는가"*로
읽으면 **행 1과 행 3이 어긋난다** — `engine.disk_state`는 7번의 `already` 성공을 지나고, `engine.apply_profile`은
`apply_all`의 `ok:true` 봉투를 지나기 때문이다. **지나는 것과 거는 것을 가르지 못하는 기준은 기준이 아니다.**
**보존 계열 안에서 「접기」와 「아무것도 안 함」이 갈리는 것은 층 판정이 아니라 구현 세부**다(반환을 쓰면 접고
안 쓰면 안 접는다 — 위 술어 블록의 ⓐ/ⓑ).

#### C-2-3. `game_or_fail`을 지나지 않는 항목 소비 지점 전수 7자리

| 자리 | 오늘 `ok:true`인 세계 | **19판 배정** | 비고 |
|---|---|---|---|
| `confirm.needs_confirm`(저장 확인)의 `store.game(reg, appid) or {}` | **없다**(결손은 확인창까지 가지만 엔진이 죽고, 비-dict는 `basename(123)`류 `TypeError`) | **실행**(술어 직접 적용) | 위 술어 블록 |
| `confirm.already_registered`의 `(reg.get("games") or {}).get(...)` | **없다**(그 route의 결론은 언제나 거부 봉투다 — 결손은 `ALREADY_REGISTERED`, 비-dict는 `UNEXPECTED`) | **실행·판정**(술어 직접 적용) | §14-H ⓙ |
| `engine.add_game`의 `reg["games"].setdefault(appid, {})` → `entry.update({...})` | **없다** — truthy 비-dict면 `.update`에서 `AttributeError` | **실행 — 앞단이 이미 막는다(술어 미삽입)** | 제품 route에서는 `already_registered`가 **먼저** 거부하므로 도달하지 않는다. **술어를 여기 심지 않는 것이 확정 판단이다**: `setdefault`가 결손 dict를 정상 갱신하므로, 심으면 **「손상 항목을 재등록으로 고치는 길」이 막힌다.** 이 표에 남기는 이유는 다음 사람이 **빠뜨린 자리로 읽지 않게** 하기 위해서다 |
| `restore.target_sha1`(config 대상)의 `... or {}` | **있다**(결손 → `None`으로 접혀 목록이 뜬다) | **조회**(isinstance 격리 → `None`) | §14-H ⓚ · 행 9의 생존이 여기 달려 있다 |
| `main.get_overview`의 **정렬 키**와 목록 조립 | **있다**(결손에서 목록이 뜬다) | **조회** | ⚠️ **사망점은 루프 안이 아니라 정렬 키다**: `sorted(reg["games"], key=lambda a: reg["games"][a].get("name", a))` — 비-dict 항목이 하나 있으면 **루프가 시작되기도 전에** 그 첫 줄에서 `AttributeError`로 죽는다. 루프 안만 고치면 화면은 그대로 전면 불능이다(`config_path` isinstance 접기는 이미 루프 안에 있다) |
| `main._profile_total` · `main.reset_all` row 조립 · `engine.apply_all` row 조립 | **있다**(결손에서 전부 뜬다) | **조회** | 비-dict에서 죽는다(`entry.get("name")`이 게임별 try **밖**) |
| `confirm._preview_one`의 `config_path` 술어 | **있다**(결손 → `cannot_apply`로 정상 집계) | **조회 — 술어 정합** | 위 술어 블록의 미러 조문 · §14-H ⓛ |

### C-3. 파급

| 대상 | 내용 |
|---|---|
| 백엔드 | `engine`(**모듈 공개 술어 `entry_corrupt`** + `game_or_fail` 인자 — 정책층 미러가 부른다: C-1·§14-H ⓒ·ⓛ) · `confirm.needs_confirm` · **`confirm.already_registered`(★ 3판)** · **`confirm._preview_one`의 `config_path` 술어(★ 3판)** · **`main.get_overview`(★ 4판 — 목록 조립만이 아니라 `sorted(...)`의 **정렬 키**가 실사망점이다)**·`_profile_total`·`reset_all` row(게임별 try **안**으로) · **`main.list_backups`(`require_intact=False` — ★ 3판)** · `engine.apply_all` row · **`restore.needs_confirm`(`require_intact=False` + 비-dict 접기 — ★ 3판)** · **`restore.target_sha1` isinstance 격리(★ 3판)** · `remove` 삭제 2함수 |
| i18n | **신설 1키** `REGISTRY_ENTRY_CORRUPT`(J절) |
| 검사 | `qa/test_reset_all.py`의 좀비 키 기대값 **정답 교체**(L절 E59) · `qa/test_confirm_equivalence.py`의 print 리터럴 괄호 문면 현행화 — **검사 로직·폭 무변경** |
| 검사(문서 — ★ 3판) | `qa/test_apply_preview_equivalence.py` 문서 **3자리**(660 표 행 · 660 해설 · 기대 버킷 트레일링 주석) 현행화 — **로직·폭 무변경, 초록 유지**(I절 ⓙ) |
| 검사(세계 — ★ 3판) | 같은 파일에 **세계 2개 추가**(`config_path: 123` · `config_path: ""`) — 미리보기 술어 정합의 잠금(G4) |
| 주석(★ 3판) | `engine.apply_all` 외곽 except(I ⓚ) · `confirm._preview_one`(I ⓛ) · **KeyError 경계 3자리**(I ⓜ) · **`ALREADY_REGISTERED` 단정 2자리**(I ⓝ) |
| 앵커 주의 | `qa/test_discover_routes.py`가 `main.py` **소스 문자열을 앵커로 잡는다**(공백 포함) — 편집이 그 문자열을 깨뜨리면 안 된다 |
| 검사(결합) | G4의 **결합 변이 검사**: row 조립·`_profile_total` 격리를 제거한 mutant가 실패해야 한다(선택적 리버트 탐지 — REVIEW-F1A §6) |

---

## D절. §7-5′ 신설 — 부분완료 고지 (F2a)

### D-0. 현행 조문 인용

§8-D(`:1623`)의 `delete_game` `DELETE_FAILED` params 행 말미:

> ⚠️ `DELETE_FAILED`는 **부분 삭제 상태를 의도적으로 신호하는** 유일 코드이나 **유일한 부분 완료 경로는 아니다** — 삭제 성공 뒤 `_save_registry`가 던지면 … `UNEXPECTED`

같은 사실이 §10-A `DELETE_FAILED_BEFORE_DELETE` 행(`:1751`)과 `rpc.ts`의 `deleteGame` 독스트링에도 있다
(*"프로필 데이터 삭제가 성공한 뒤 registry 저장이 실패하면 봉투는 UNEXPECTED가 되고 … UNEXPECTED를
「무변경」으로 다루지 마라"*). **셋 다 F2a 뒤에 거짓이 된다** — I절 ⓒ가 함께 교체한다.

### D-1. 개정 조문 전문 — §7-5′ 신설

> ### 7-5′. 파괴 뒤의 저장 실패는 부분완료로 고지한다 (19판 신설 — F2a · E52 처방)
>
> **두 route가 같은 모양의 구멍을 갖고 있다**: 파일을 이미 지운 뒤 마지막 registry 저장이 실패하면 봉투가
> `UNEXPECTED`로 나가 화면이 *"예기치 못한 오류 — 다시 시도해 보십시오"*라고 말한다.
> **이미 지워졌다는 사실을 아무도 말하지 않는다.**
>
> - **`delete_game`**: `remove.delete_game_data` 성공 뒤의 `_save_registry`를 **`except OSError`로 좁게**
>   감싸 `DELETE_FAILED` + `profile_delete_started=True`로 내보낸다. **기존 계약·기존 프론트 분기를
>   재사용한다** — 신설이 아니라 **미도달 갈래를 도달시키는 것**이다.
>   ⚠️ **`RegistryError`는 그대로 올린다.** `REGISTRY_NEWER`를 `DELETE_FAILED`로 삼키면 U5 고지가 사라진다.
> - **`reset_all`**: 마지막 `_save_registry(fresh)`를 같은 방식으로 감싸 **신설 코드 `RESET_FAILED`**로 내보낸다.
>   문구는 **조건부**여야 한다 — 그 시점에 지워진 양은 0에서 전부까지 무엇이든 될 수 있다. 기존
>   `DELETE_FAILED` 번역과 **같은 문법**을 쓴다(*"…이미 일부 또는 전부 지워졌을 수 있습니다. 다시 …하면
>   남은 것부터 이어서 지웁니다"*). 단정형(*"지워졌습니다"*)은 금지다.
>   **재시도가 실제로 이어서 지운다**는 약속은 참이다 — 초기화 route는 실패분만 남기고 다음 실행이 남은
>   것부터 돈다(§7 `RESET_LEFT_NOTE`가 같은 약속을 이미 하고 있고 참임의 근거도 같다).
> - **`fresh` 갈래에서는 이 코드가 나가지 않는다** — 그 갈래는 게임을 하나도 안 지운다(§7-4′ 7항).
>   fresh의 저장 실패 처분은 §7-4′ 6-1이다.
> - **`exclude.add`의 비영속은 손대지 않는다** — 재시도로 완결되는 것이 실측됐다(문서에만 남긴다).
>
> **프론트 분기는 두지 않는다(19판 확정)**: `SettingsPopup`의 마지막 줄이 이미
> `setNote(tCode(res.code, "RESET_ACTION_FAILED"))`이고, `tCode`는 **`code`가 i18n 키로 존재하면 그 값을
> 그대로 쓴다**(`code in en ? t(code) : t(fallback, {code})`). 즉 `RESET_FAILED`를 §10-A에 등재하는 순간
> 화면에 정확한 문장이 뜬다.
> ⚠️ **이 면제는 「사실 필드가 없는 코드」에만 성립한다** — `tCode`는 `res.params`를 받지 않고 `t(code)`에
> 치환값도 넘기지 않는다. `DELETE_FAILED`처럼 **사실 필드가 두 문장을 가르는** 코드는 소비자가 명시 분기를
> 둔다(`GamesPopup`의 `profile_delete_started` 분기). `RESET_FAILED`에는 갈릴 문장이 없다 —
> *분기는 갈릴 것이 있을 때만 만든다.*

### D-2. 근거

- 두 자리 모두 **재현 하네스로 실측된 미도달 갈래**다(`repro_init1.py`·`repro_reset.py`: `UNEXPECTED` + `params={}`).
- `DELETE_FAILED` 재사용의 근거: 그 코드·그 필드·그 프론트 분기가 **이미 완성돼 있고 도달만 못 하고 있었다.**
- `RESET_FAILED` 신설의 근거: `RESET_*` 계열 전수 확인 결과 **부분완료를 말하는 코드가 없다.**
  `RESET_ACTION_FAILED`는 백엔드 코드가 아니라 **프론트 폴백 키**(`{code}`를 받는다)라 같은 자리에 쓸 수 없다 —
  이름이 닮았으므로 `codes.py`에 그 구분을 한 줄로 적어 둔다.

### D-3. 파급

| 대상 | 내용 |
|---|---|
| 백엔드 | `main.delete_game`(좁은 `except OSError`) · `main.reset_all`(동상 + `RESET_FAILED`) · `codes.py` 상수 1개 |
| 프론트 | **0**(D-1 마지막 문단) |
| i18n | **신설 1키** `RESET_FAILED`(J절) |
| 조문 | §8-D `:1623` · §10-A `:1751` · `rpc.ts` `deleteGame` 독스트링 — **셋 다 교체**(I절 ⓒ) |
| 한계 | **§15-D E52가 크게 닫힌다**(L절) |
| 검사 | `repro_init1.py`·`repro_reset.py` 봉투 역전(G1) · **F7-1이 새 코드의 ko/en 등재를 잠근다** |

---

## E절. 오류 코드 정밀화 3건 — §14-E″ 신설 (F2b · F4-1 · F4-2)

### E-0. 현행 조문 인용

§14-E′(`:2140`, 「백업 실패 코드의 통일」):

> **해소**: 엔진에서 **대피(`make_backup`) 호출만 좁게** 감싸 `BACKUP_FAILED`로 통일한다.
> **★ 좁게 감싸는 것이 핵심이다**: 함수 전체를 감싸면 meta 읽기 실패까지 `BACKUP_FAILED`가 되어 **반대 방향의 오정보**가 된다. 코드 하나가 하나의 사건만 가리키게 하는 것이 이 수정의 목적이다.
> … **신설 코드 `PROFILE_WRITE_FAILED`**. ko *"프로필을 저장하지 못했습니다 — 저장 공간이나 파일 권한을 확인해 주세요"* … `qa/test_codes.py`의 `glue_only` 집합에 새 코드를 넣는다(**엔진이 안 쓰는 접착층 전용 코드다**).

### E-1. 개정 조문 전문 — §14-E″ 신설

> #### 14-E″. 규칙 2를 형제 갈래에 마저 적용한다 (19판 — E52 처방)
>
> 16판이 세운 규칙은 *"실패 사유의 출처를 타입으로 가른다"*였고, **적용된 곳은 저장 하나였다**(§15-D E52).
> 19판이 형제 셋에 같은 규칙을 적용한다. **셋 다 신설 코드 0 — 이미 있는 코드를 제자리로 보낸다.**
>
> | | 자리 | 지금 | 19판 | 왜 |
> |---|---|---|---|---|
> | ⓐ | `engine.restore_backup`의 **슬롯 갈래 쓰기** | 쓰기 실패가 봉투 밖으로 새어 `UNEXPECTED` | **슬롯 갈래의 `store.write_profile` 호출만** 좁게 감싸 `Refused(PROFILE_WRITE_FAILED)` | **함수 전체를 감싸면 안 된다** — 백업 파일 **읽기** 실패(`store.read_bytes(backup_path)`)까지 「쓰기 실패」로 오분류된다(§14-E′가 저장에서 적어 둔 그 문장이 판별 기준이다). ⚠️ **config 갈래의 `store.atomic_write`는 이 조문에 넣지 않는다** — `PROFILE_WRITE_FAILED`의 문구 주어가 *"프로필을 저장하지 못했습니다"*라 **게임 설정 파일** 쓰기 실패에 붙이면 오표기다. 그 자리는 **백로그**(재론: 실보고 1건) |
> | ⓑ | `store.profile_file_path` + `engine.apply_profile`의 대상 판정 | `meta`가 **truthy 비-dict**면 `meta["filename"]`이 `TypeError` → `UNEXPECTED` | `store` 쪽은 isinstance 게이트로 거부하고, **`engine`이 비-dict를 구분해 `PROFILE_CORRUPT`로 내보낸다** | **`None` 반환으로 끝내면 안 된다** — 그러면 `engine`의 `PROFILE_MISSING`("아직 저장되지 않았습니다")으로 나가 **실재하는 손상을 「미저장」으로 오표기**한다. `PROFILE_CORRUPT`의 §10-A 문구는 복구 동선 2개(재저장·백업 복원)를 실재 UI로 가리킨다 |
> | ⓒ | `engine.apply_profile`의 적용 전 디스크 백업 | `store.read_bytes(path)`가 `try` **밖**이라 그 `OSError`가 `UNEXPECTED` | `read_bytes`와 **그것을 쓰는 조건문까지 블록째** `try` 안으로 옮겨 `BACKUP_FAILED`로 수렴(=`restore_backup`의 같은 자리와 동형) | 「1줄 이동」이 아니라 **블록 재배치**다 — 통독 게이트 대상. 문구 *"원본은 그대로입니다"*는 옮긴 뒤에도 전 갈래에서 참이다(백업 실패 시 쓰기에 도달하지 않는다) |
>
> ⚠️ **§14-E′의 마지막 줄이 19판에서 낡는다**: *"`glue_only` 집합에 새 코드를 넣는다(**엔진이 안 쓰는**
> 접착층 전용 코드다)"* — ⓐ가 **엔진에서** `PROFILE_WRITE_FAILED`를 던지므로 그 괄호는 참이 아니다.
> **검사는 안 깨진다**(`glue_only`는 `unused` print에만 쓰이고 합격 판정에 관여하지 않는다 — 실물 주석이
> 스스로 *"무효항"*이라 적어 두었다). **`qa/test_codes.py`에서 `PROFILE_WRITE_FAILED`를 `glue_only`에서
> 뺀다** — 무효한 목록이라도 거짓을 담아 두면 다음 사람이 유효한 가드로 읽는다.

### E-2. 근거

- ⓐ의 좁힘은 Codex NARROW 판정의 직접 반영이고, **슬롯 한 자리로의 추가 축소는 사용자 기확정 결정**이다
  (문구 주어 불일치 — E-1 표의 ⚠️).
- ⓑ의 코드 선택은 Codex NARROW: *"실재하는 손상을 「미저장」으로 오표기하지 마라."*
- ⓒ는 §14-E′가 세운 「같은 사건은 같은 코드」의 미적용분이다 — 같은 함수 안에서 백업 실패 하나가 두 코드로 갈리고 있었다.
- 셋 모두 **「이미 있는 코드를 제 사건에 붙이는」 수정**이다. `BULK_OUTCOMES` 5종·봉투 스키마·프론트 분기
  어디에도 새 갈래가 생기지 않는다.

### E-3. 파급

| 대상 | 내용 |
|---|---|
| 백엔드 | `engine.restore_backup`(**슬롯 쓰기 1자리**) · `store.profile_file_path` + `engine.apply_profile`(대상 판정) · `engine.apply_profile`(백업 블록 재배치) |
| i18n | **0** — 셋 다 기존 코드 |
| 검사 | 신설 `repro_restore_meta.py`가 ⓐ를 잠근다 — **ⓐ백업 읽기 실패 · ⓑmeta 쓰기 실패 · ⓒregistry 쓰기 실패 셋을 따로 주입해 봉투가 각각 갈리는지**(수정 전 대조군 선확보) · r4·r5(→`PROFILE_CORRUPT`) · r7(→`BACKUP_FAILED`) |
| 검사(문서) | `qa/test_codes.py`의 `glue_only`에서 `PROFILE_WRITE_FAILED` 제거 |
| 검사(문서 — ★ 3판) | `qa/test_apply_preview_equivalence.py` 세계 표의 **650 행**(`error` → `refused(PROFILE_CORRUPT)`) 현행화(I절 ⓙ①) — 로직·폭 무변경 |
| 백로그 | `restore_backup` **config 갈래**의 쓰기 실패 분류(전용 코드 없이는 오표기라 미착수 — 재론: 실보고 1건) |
| 한계 | §15-D E52 축소(L절). **E51은 손대지 않는다** — `save_profile`의 읽기 실패 갈래는 범위 밖이고 등재 존치 |

---

## F절. §5-E-2 계열 정오 — 읽을 수 없는 설정 파일의 분류 (F4-7)

### F-0. 현행 조문 인용

`confirm.py` 상수 주석(실물): *"`MISSING` — SHA-1이 없다 — **파일 없음뿐 아니라 기존 파일의 읽기 실패도
여기로 접힌다**"* / *"`disk_state` 4분류. 현재 분류는 파일 존재 여부와 SHA-1 산출 여부를 완전히 갈라내지
않는다."* — **자백이 주석에 있고 화면은 그대로 거짓을 말한다.**

### F-1. 개정 조문 전문 — §5-E-2 4분류 표에 각주 추가

> **★ 19판 정오 — `MISSING`은 「없다」만 말한다.** `_classify`가 `state["exists"]`가 참인데 `sha1`이 `None`인
> 상태(권한·EIO로 읽기 실패)를 `MISSING`으로 접어, 확인창이 *"설정 파일이 없습니다"*라고 말하면서 동시에
> *"백업 한 칸을 씁니다"*라고 말했다(모순 — r6(b) 실측). 19판부터 **`exists`가 참이고 `sha1`이 없으면
> `LOOKUP_FAILED`**다.
> **신설은 0이다** — `DISK_STATE_LOOKUP_FAILED`(*"설정 파일을 읽지 못했습니다"* / *"the config file could not
> be read"*)가 이미 등재돼 있고 정확히 그 문장이다. **i18n·`rpc.ts`·`confirmSpecs` 무변경.**
> `confirm.py` 상수 주석의 자백 문구도 같은 커밋에서 현행화한다.
> ⚠️ **분류값은 F7-1의 검사 범위 밖이다**(그 검사는 `codes.py` 상수와 번역을 맞댄다 — 분류값은 `codes` 상수가
> 아니다). 이번에 신설 분류가 없으므로 대조 대상 자체가 없다.

### F-2. 근거 · 파급

- **최소안이다**: 새 분류값을 만들면 `rpc.ts`·`confirmSpecs`·i18n 세 곳이 함께 움직인다. 기존 값 하나로 모순이
  닫히므로 그 왕복을 사지 않는다.
- 파급: `confirm._classify` 한 함수 + 그 파일 상단 상수 주석. 검사 = r6(b)에서 문구가 *"없습니다"* → *"읽지 못했습니다"*로 역전.

---

## G절. §5-G 소비자 명단 — already 판정을 본체로 통일 (F4-8)

### G-0. 현행 조문 인용

§5-G(`:1433`):

> **3인자 둘**(*"어느 이름으로든 보존됐나"*) — `engine.disk_state`의 `matches`(`engine.py:323` = 적용 대피 생략의 근거) · `confirm._matching_profiles`(`confirm.py:273` = 화면 마커·`matches[]`).

§5-G(`:1452`):

> **남은 meta-only 판정 3곳은 범위 밖으로 뒀다** — 근거는 §15-D E18.

### G-1. 개정 조문 전문 — 위 두 문장을 **대체**한다

> **3인자 넷**(*"그 슬롯이 그 내용을 들고 있나"*) — `engine.disk_state`의 `matches`(`engine.py` = 적용 대피
> 생략의 근거) · `confirm._matching_profiles`(화면 마커·`matches[]`) · **★ 19판 추가 둘**:
> `engine.apply_all`의 **already 분기** · `confirm._preview_one`의 **already 분기**.
> (⚠️ 17판이 *"개수 표기를 버린다"*고 적었으나 이 자리는 소비자 **이름**을 열거하는 문장이라 수가 다시 붙었다.
> 규칙은 그대로다 — **수를 세는 것이 아니라 이름을 적고, 이름을 더할 때 수도 같이 고친다.**)
>
> 추가 둘은 지금 `state["sha1"] == meta.get("sha1")`로 **기록끼리 맞대고** 있어 본체가 깨진 슬롯을
> *"이미 적용됨"*이라 말한다. 판정을 `store.slot_holds(appid, profile, state.get("sha1"))`로 옮긴다.
> - **`state.get` 가드는 필수다** — `disk_state`가 실패하면 `state`가 `{}`라 직접 첨자는 `KeyError`다
>   (두 자리 모두 위에 `except`가 있어 게임별 격리로 접히지만, 그 격리는 판정 실패용이지 코드 오류용이 아니다).
> - **엔진 쪽에 새 outcome은 없다.** 판정이 거짓이 되면 정상 실행 판정으로 낙하하고, **대상 상태에 따라**
>   `PROFILE_CORRUPT`(본체 불일치)·`PROFILE_MISSING`(본체 없음)·`error`(filename 결손 등) 중 하나가 된다 —
>   *"항상 `PROFILE_CORRUPT`"는 일반 명제가 아니다.* `BULK_OUTCOMES` 5종 불변.
> - **미리보기 쪽도 새 버킷이 없다.** 기존 `cannot_apply`로 간다(버킷에는 오류 코드가 없다 — 수 변화로 판정).
> - **비용**: 게임당 meta 재로드 1 + 본체 read 1 + sha1 1. 지불하는 이유는 §5-G 본문과 같다 —
>   *"모르거나 어긋나면 「일치 없음」으로 접히고, 그러면 화면은 고지하고 대피한다."* 실측은 QAPLAN G5.
>
> **★ 19판 — 「남은 meta-only 판정 3곳은 범위 밖으로 뒀다」는 문장을 대체한다.**
> 위 둘을 옮겼으므로 **남은 meta-only 판정은 `main._disk_matches` 배지 하나**다(§15-D E18).
> 16판 각주(*"15판까지 이 「셋」은 거짓이었다 — 넷째 자리가 빠져 있었다"*)는 이력으로 그대로 둔다.

### G-2. 파급

| 대상 | 내용 |
|---|---|
| 백엔드 | `engine.apply_all` · `confirm._preview_one` — **같은 커밋**(한쪽만 고치면 미리보기와 결과가 갈린다) |
| i18n | 0 |
| 검사 | r6(c) 필드 단위(engine·개별 확정 = `PROFILE_CORRUPT` / preview = `already` 0 감소·`cannot_apply` 1 증가) + **filename 결손 별도 행**(bulk `error` / preview `cannot_apply`) + `qa/test_apply_preview_equivalence.py` |
| 한계 | §15-D E18 「3곳」 → 「1곳」(L절) |

---

## H절. §7 팝업 S — 진입 화면 상시 두 줄의 한정 (낡음 ⓐ)

### H-0. 현행 조문 인용

§7 팝업 S 스케치(`:1509`·`:1512`)와 실물(`SettingsPopup.tsx`):

> 전체 초기화 — 등록 기록과 저장된 프로필을 모두 지웁니다.       ← `RESET_ZONE_BODY`
> 백업 폴더는 남지만 프로필 데이터를 옮겨 두는 동안 오래된 백업이 밀려날 수 있습니다. 게임 설정 파일 원본은 건드리지 않습니다.  ← `RESET_HINT`

두 값 모두 §10-A가 바이트를 잠근 행이다(`RESET_ZONE_BODY`는 17판 DEFECT-02, `RESET_HINT`는 12판 사실성 4번).
두 줄은 **조회 성공·로딩·조회 실패 세 상태에서 모두 무조건 그려진다**(조건은 둘째 줄에만 있다).

### H-1. 개정 조문 전문 — §7 팝업 S 스케치에 각주 신설 (값 변경 0 · 코드 변경 0)

> **★ 19판 각주 — 이 두 줄은 정상 초기화를 서술한다.** fresh 복구 초기화(§7-4′)는 프로필도 백업도 지우지
> 않으므로, 손상 상태에서 이 두 줄은 **실제보다 넓은 파괴**를 말한다. **값은 바꾸지 않고 소관을 한정한다**:
> - **파괴 범위의 정본 고지는 확인창의 warnBlock 하나다**(§7 10판 — *"수량·백업 잔존·재등록 전제의 **유일한**
>   자리"*). fresh 갈래에서는 `RESET_FRESH_CONFIRM_WARN`이 그 자리를 맡아 **되돌릴 수 없는 조작 직전에**
>   정확한 사실을 말한다. 진입 화면의 두 줄은 구획 설명이지 고지가 아니다.
> - **그 화면은 이미 진실을 말하고 있다**: registry가 손상돼 조회가 실패하면 note 자리에 `REGISTRY_UNREADABLE`·
>   `REGISTRY_MALFORMED` 문구가 뜨고(*"게임 목록을 읽지 못했습니다 … 프로필과 백업은 바뀌지 않았습니다"*),
>   둘째 줄이 `RESET_ZONE_UNKNOWN`("현재 등록 수를 확인할 수 없습니다")으로 갈린다.
> - **방향은 과대 고지다.** 화면이 실제보다 **더 많이 지운다고** 말하고 실제로는 덜 지운다 — 이 프로젝트가 두 번
>   「안전한 방향」으로 판정한 쪽이다(§15-D E19·E29, E10에 인용).
>
> ⚠️ **공짜가 아니라는 사실을 함께 적는다**: 과대 고지는 여기서 **탈출로를 안 누르게 만드는** 방향으로도 작용할
> 수 있다(*"프로필이 다 지워진다니 못 누르겠다"*). 그래서 **재론 조건을 단다 — 실기·실사용에서 「손상 상태인데
> 초기화를 누르지 못했다」 관측 1건이면 병기안을 재상정한다.**
>
> **기각한 대안 둘**:
> ⓐ **값 변경**(두 줄을 두 갈래 모두에 참인 문장으로 다시 씀) — 상시 노출 문구를 드문 상태에 맞춰 모호하게
>   만든다. 사용자가 F3-1을 제외할 때 쓴 판단과 같다(*"특수 케이스의 정직성을 위해 상시 문구의 가독성을
>   희생하지 않는다"*). 게다가 §10-A가 바이트를 잠근 두 행을 흔든다.
> ⓑ **조건부 병기**(손상일 때만 한 줄 추가) — 화면이 「지금이 fresh 세계인가」를 알아야 하는데, `usePopupData`가
>   주는 것은 **이미 번역된 `noteText` 문자열**이고 **실패 코드는 노출하지 않는다**(훅 반환 타입 실측).
>   코드를 노출하려면 팝업 3종이 공유하는 훅의 계약을 바꿔야 한다 — **최소 개정의 반대**다.

---

## I절. 19판이 만드는 낡음 연쇄 — 조문 4건 · 코드 주석 12자리 · 검사 파일 문서 5자리

각 항은 **현행 인용 → 개정 조문**이다. 전부 사실 정정이고 새 결정은 없다.

**★ 19판 3판 정정 — 제목의 「fresh·F2a가」를 「19판이」로 넓힌다.** 낡음의 원인이 셋 더 있다: **F1-c**가
`KeyError: config_path` 서술 전부를 · **F4-1**이 비-dict meta의 `error` 서술을 · **F7-1**이
*"코드↔번역 대조 검사는 없다"* 서술을 거짓으로 만들고, **`already_registered` 술어 적용**이
`ALREADY_REGISTERED` 단정 2자리를 낡게 한다. *전수를 주장하는 문장은 그 주장 자체가 검사 대상이다* —
그래서 **수를 항목별로 적어 검산 가능하게 둔다**:

| 항 | 코드 주석 | 검사 파일 문서 | 소계 |
|---|---|---|---|
| ⓒ③·ⓕ·ⓖ(2판분) | 4 | 0 | 4 |
| ⓘ | 1 (`codes.py`) | 1 (`qa/test_codes.py`) | 2 |
| ⓙ | 0 | 4 (`qa/test_apply_preview_equivalence.py`) | 4 |
| ⓚ | 1 | 0 | 1 |
| ⓛ | 1 | 0 | 1 |
| ⓜ | 3 | 0 | 3 |
| ⓝ | 2 | 0 | 2 |
| **계** | **12** | **5** | **17** |

**3판이 더하는 것은 ⓘ~ⓝ의 13자리**다(2판분 4자리는 그대로). **조문 4건은 2판 계수를 그대로 둔다** —
3판 정정은 그 축을 다시 세지 않았다.
**탐사 범위(3판 정정 시 실행)**: `grep -rn` 5축 — ⓐ `KeyError` ⓑ `config_path`(주석·독스트링 문맥)
ⓒ `대조하는 검사|맞대는 검사|검사는 (저장소에 )?없다` ⓓ `UNEXPECTED`(주석 문맥) ⓔ `ALREADY_REGISTERED`.
대상 = `main.py` · `py_modules/gfxp/*.py` · `src/*.ts` · `src/*.tsx` · `qa/*.py`.

### ⓑ §7 흐름 설명 (`:1517`)

> **현행**: - 전체 초기화: `resetAll()` 1차 → 게이트 `ResetConfirmSpec`(입력형). 본문 구성(위→아래 …)
>
> **개정**: - 전체 초기화: `resetAll()` 1차 → 게이트. **★ 19판 — spec이 둘이다**: 정상 갈래는
> `ResetConfirmSpec`(입력형, 아래 본문 구성), **손상 복구 갈래는 `makeResetFreshConfirmSpec`**(§7-4′ 3항 —
> 수를 싣지 않는 별도 본문). **아래 본문 구성 1~5는 정상 갈래의 것이다.**

### ⓒ F2a가 거짓으로 만드는 「UNEXPECTED」 서술 3자리

> **현행 ①** §8-D `delete_game` `DELETE_FAILED` params 행 말미: *"⚠️ `DELETE_FAILED`는 부분 삭제 상태를
> 의도적으로 신호하는 유일 코드이나 **유일한 부분 완료 경로는 아니다** — 삭제 성공 뒤 `_save_registry`가
> 던지면 … `UNEXPECTED`"*
> **개정 ①**: *"⚠️ **★ 19판 — 그 예외가 사라졌다.** 삭제 성공 뒤 `_save_registry`의 `OSError`도 §7-5′가
> `DELETE_FAILED` + `profile_delete_started=True`로 접으므로, 이제 `DELETE_FAILED`는 **부분 삭제 상태를
> 신호하는 유일 코드이자 이 route의 유일한 부분완료 경로**다. (`RegistryError`는 여전히 그대로 올라간다 —
> `REGISTRY_NEWER`를 삼키지 않기 위해서다.)"*
>
> **현행 ②** §10-A `DELETE_FAILED_BEFORE_DELETE` 행 사유 칸: *"…삭제 뒤 `_save_registry` 실패의
> `UNEXPECTED` 갈래도 부분 완료를 낼 수 있어 *유일*하지는 않다. §8-D"*
> **개정 ②**: 그 절을 삭제하고 *"(★ 19판 — 그 `UNEXPECTED` 갈래는 §7-5′가 닫았다.)"*로 대체.
>
> **현행 ③** `rpc.ts` `deleteGame` 독스트링: *"단 부분완료를 남기는 코드가 이것뿐은 아니다 — 프로필 데이터
> 삭제가 성공한 뒤 registry 저장이 실패하면 봉투는 UNEXPECTED가 되고 … UNEXPECTED를 「무변경」으로 다루지 마라."*
> **개정 ③**: *"★ 19판 — 그 갈래도 이제 `DELETE_FAILED`(+`profile_delete_started=true`)로 온다. 프로필 데이터
> 삭제가 시작된 뒤의 실패는 이 코드 하나로 수렴한다."*

### ⓓ §8-D 「토큰 6종」 행 (`:1630`)

> **현행**: | **토큰 6종** | 지문 | **링 지문 결박**(§5-E-4): 저장·적용은 … · 등록 해제는 … · **R15: 일괄 적용·전체 초기화는 `evict_digest`를 슬롯 3에 합성** |
>
> **개정**: | **토큰 7종(★ 19판)** | 지문 | (현행 서술 전부 불변) + **19판 신설 = 전체 초기화의 fresh 스코프**
> (`_RESET_FRESH_SCOPE`). 이 하나는 **링 지문을 결박하지 않는다** — 그 갈래는 백업을 만들지도 축출하지도 않기
> 때문이다. 대신 **registry 원문 관측값 + `RegistryError.code`**에 결박한다(§7-4′ 4항). 스코프를 정상 갈래와
> 가른 이유는 `_apply_scope`·`_restore_scope`와 같다 — **두 갈래가 지우는 대상이 다르다** |

### ⓔ §5-G 두 문장 (`:1433`·`:1452`) — **G-1이 대체 전문을 갖는다**

(중복 기재하지 않는다. 편입 시 G-1의 전문으로 두 문장을 **교체**한다 — 추가만 하면 §5-G 안에 옛 전수 선언이 남는다.)

### ⓕ §14-F 제목과 ③ (`:2510`·`:2521`)

> **현행 제목**: ### 14-F. 레지스트리 버전 가드 (U5 — 14판 보수. **fence 밖: `main.py`·`codes.py`·i18n만**)
> **개정 제목**: ### 14-F. 레지스트리 버전 가드 (U5 — 14판 보수. ~~fence 밖: `main.py`·`codes.py`·i18n만~~
> **★ 19판: fence는 15판에 폐지됐고(§14-D), 19판이 `store.load_registry`에 형태 검사를 더한다 — §14-F′·§14-H ⓐ**)
>
> **현행 ③**: *"③ `store.py`는 fence — 방어는 소비자 층에 둔다(기존 선례)."*
> **개정 ③**: *"③ **버전 판정은 소비자 층에 둔다** — 그 판정이 「무엇을 바꾸려 하는가」를 알아야 하고 그것은
> route만 안다. ⚠️ **★ 19판 — 근거에서 fence를 뺀다**: 15판에 폐지됐고(§14-D), 19판은 `store.load_registry`를
> 실제로 고친다(§14-F′). **다만 고치는 것의 성격이 다르다** — store가 보는 것은 「읽어서 dict가 되는가」라는
> **형태**이고, 버전이라는 **의미**는 여전히 route가 본다. 층 판별은 §14-H."*
>
> **`store.save_registry` 독스트링**(A절 파급): *"`.bak`이 있어야 손상 시 안내가 실제 복구 경로가 된다
> (없으면 안내가 거짓말이 된다)"* → **★ 19판**: 그 안내(`load_registry`의 rm/복구 문구)는 §14-F′가 제거했고,
> 인앱 탈출로(§7-4′)가 그 일을 대신한다. `.bak`은 이제 **사람이 손으로 되살릴 마지막 재료**로 남는다 —
> 그래서 **fresh 갈래가 `.bak`을 건드리지 않는 것이 계약**이다(§7-4′ 6항).

### ⓖ 코드 주석 2자리 (ⓕ의 `store.py` 외)

> **`main._save_registry` 독스트링**: *"이 래퍼에 예외 경로는 없다 — **reset_all(탈출로)도 여기를 지나지만**,
> 그것이 영속화하는 dict는 `store.default_registry()` 기반이라 …"*
> → **★ 19판**: *"…정상 갈래의 reset_all은 여전히 여기를 지난다. **fresh 갈래는 여기를 지나지 않는다** —
> `store.save_fresh_registry()`가 인자를 받지 않아 밖에서 만든 dict가 그 문으로 들어올 수 없고, 그래서
> 버전 가드 없이도 `version`이 언제나 현재 값이다(§7-4′ 6항). **구조가 예외를 없앤 자리가 하나 더 늘었다.**"*
>
> **`i18n.tCode` 독스트링**: *"`codes.py`의 코드가 i18n에 다 있는지 대조하는 검사는 **저장소에 없다**. …
> 그러니 「백엔드 코드는 fallback을 타지 않는다」는 보증이 아니다"*
> → **★ 19판**: 그 검사가 생겼다(`qa/test_codes_i18n.py` — F7-1). 문단을 *"…대조하는 검사는
> `qa/test_codes_i18n.py`가 한다(19판 신설). 그래도 이 폴백은 지운다 — 검사가 없는 환경(개발 중 편집)과
> 백엔드가 미지의 코드를 보내는 경우가 남는다"*로 고친다.

### ⓗ §10 머리말 에러 코드 키군 수 (`:1689`)

> **현행**: 에러 코드 키군은 **13판 R14에서 27 → 28종**(`WARN_SAVE_WHILE_RUNNING` 신설 — §10-F).
> **개정**: 에러 코드 키군은 13판 R14에서 27 → 28종, **★ 19판에서 28 → 30종**
> (`REGISTRY_ENTRY_CORRUPT`·`RESET_FAILED` 신설 — §10-A). ⚠️ **이 수는 `codes.py` 상수 기준이고, 19판이
> 더하는 i18n 키는 넷이다**(나머지 둘은 화면 전용 문구다 — `RESET_FRESH_CONFIRM_WARN`·`RESET_OK_FRESH`).

### ⓘ F7-1이 거짓으로 만드는 「대조 검사 없음」 서술 2자리 (★ 19판 3판 정정)

> **현행 ①** `py_modules/gfxp/codes.py` 모듈 독스트링: *"이 네 집합 사이에서 기계가 강제하는 관계는 다음
> 두 가지뿐이다: … **미사용 상수는 실패가 아니며, codes.py와 번역 키를 맞대는 검사도 없다.**"*
> **개정 ①**: *"…기계가 강제하는 관계는 다음 **세 가지**다:
> `Refused`/`RegistryError`의 `code=codes.X`가 정의돼 있음(`qa/test_codes.py`) ·
> en.json 키 == ko.json 키(`qa/test_i18n_keys.py`) ·
> **`codes` 상수 ⊆ en.json 키 ∧ ⊆ ko.json 키(`qa/test_codes_i18n.py` — 19판 신설)**.
> 미사용 상수는 여전히 실패가 아니다 — 잠기는 것은 **등재**이지 사용이 아니다."*
>
> **현행 ②** `qa/test_codes.py` 독스트링: *"번역 키(en/ko json)와 맞대는 검사는 저장소에 없다 —
> `qa/test_i18n_keys.py`가 보는 것은 …"*
> **개정 ②**: *"★ 19판 — 번역 키와 맞대는 검사가 생겼다(`qa/test_codes_i18n.py`). 이 본이 보는 것은
> 여전히 `code=` 사용과 상수 정의의 대응이고, **등재 대조는 그쪽 본의 몫**이다 — 재는 대상이 다르면
> 본을 가른다(R14의 처분과 같다)."*

(⚠️ `src/i18n.ts`의 `tCode` 독스트링은 **ⓖ가 이미 다룬다** — 중복 기재하지 않는다. 세 자리가 **같은
거짓말을 각자 하고 있었다**는 사실이 F7-1의 존재 이유 그 자체다.)

### ⓙ F4-1·F1-c가 거짓으로 만드는 `qa/test_apply_preview_equivalence.py` 문서 4자리 (★ 19판 3판 정정)

**검사 로직·폭은 무변경이고, 검사는 초록을 유지한다** — `ALLOWED["cannot_apply"] = {"refused", "error"}`가
두 outcome을 모두 받으므로 봉투 코드가 바뀌어도 버킷 판정은 그대로다. **고치는 것은 그 파일이 스스로
적어 둔 사실 서술뿐이다.**

> **현행 ①** 세계 표 `| 650 | meta가 유효 JSON이지만 비객체 | error | cannot_apply |`
> **개정 ①**: `| 650 | meta가 유효 JSON이지만 비객체 | refused(PROFILE_CORRUPT) | cannot_apply |` (★ 19판 — §14-E″ ⓑ)
>
> **현행 ②** `| 660 | 등록 항목에 config_path 키 없음 | error(UNEXPECTED) | cannot_apply |`
> **개정 ②**: `| 660 | 등록 항목에 config_path 키 없음 | refused(REGISTRY_ENTRY_CORRUPT) | cannot_apply |` (★ 19판 — F1-c)
>
> **현행 ③** 표 아래 해설: *"660: `entry["config_path"]`가 없으면 **엔진은 `error`**, 미리보기는
> `cannot_apply`여야 한다."*
> **개정 ③**: *"660: `entry["config_path"]`가 없으면 **엔진은 `refused(REGISTRY_ENTRY_CORRUPT)`**(★ 19판 —
> 그 전에는 `KeyError`가 게임별 외곽 try에 잡혀 `error`였다), 미리보기는 `cannot_apply`여야 한다.
> **버킷은 그대로다** — `cannot_apply`가 `refused`와 `error`를 함께 받기 때문이고, 이 검사가 잠그는 것은
> 봉투 코드가 아니라 **버킷 대응**이다."*
>
> **현행 ④** 기대 버킷 표의 트레일링 주석: `"660": "cannot_apply",     # config_path 없음 → 엔진은 error`
> **개정 ④**: `"660": "cannot_apply",     # config_path 없음 → 엔진은 refused(REGISTRY_ENTRY_CORRUPT)`

### ⓚ F1-c가 거짓으로 만드는 `engine.apply_all` 외곽 `except` 주석 (★ 19판 3판 정정)

> **현행**: *"일부러 넓게 잡는다. … 좁게 잡으면 **레지스트리 항목 손상(`KeyError: config_path`) 하나에
> 전체 루프가 죽고**, 결과 창조차 못 뜬다. … 앞부분이 없으면 사용자는 `KeyError: 'config_path'`만 보고
> 무엇을 해야 할지 알 수 없고…"*
> **개정**: *"일부러 넓게 잡는다. 이 함수의 존재 이유는 「하나가 실패해도 나머지는 계속 간다」이고, 그
> 약속은 예외 종류에 따라 깨지면 안 된다. **★ 19판 — 이 자리에서 가장 흔했던 예외가 사라졌다**:
> 레지스트리 항목 손상은 이제 `engine.game_or_fail`이 **`Refused(REGISTRY_ENTRY_CORRUPT)`**로 내고,
> 그것은 **위의 `except Refused` 갈래**가 받아 `refused` + 그 코드로 보고한다(익명 `error`가 아니다).
> 이 절을 그래도 넓게 두는 이유는 **남은 미지의 예외** 때문이다 — 알려진 사건을 자기 코드로 빼내는 것과
> 최후 그물을 없애는 것은 다른 일이다(§15-D E52 ⓑ). 사람이 읽을 문장을 앞에 두고 예외는 괄호로 남긴다 —
> Game Mode엔 터미널이 없어 이 note가 유일한 단서다."*

### ⓛ F1-c가 거짓으로 만드는 `confirm._preview_one` 주석 (★ 19판 3판 정정)

> **현행**: *"`config_path`가 없는 등록 항목(손상·수동 편집)은 **엔진이 error를 낸다** — `apply_profile`이
> `entry["config_path"]`에서 **KeyError를 내고** 그 예외가 엔진의 게임별 외곽 try에 잡힌다. 그 첨자가
> G5보다 먼저라(경로를 먼저 읽는다) 실행 중이어도 error다. 이 줄이 없으면 미리보기는 `would_apply`라고
> 세고 실행은 실패한다 — "적용된다 해 놓고 안 되는" 어긋남이다."*
> **개정**: *"손상된 등록 항목은 **엔진이 `refused(REGISTRY_ENTRY_CORRUPT)`를 낸다**(★ 19판 — 그 전에는
> `entry["config_path"]`의 `KeyError`가 게임별 외곽 try에 잡혀 `error`였다). 거부는 `apply_profile`의
> **첫 줄 `game_or_fail`**에서 나므로 **여전히 G5보다 먼저다** — 실행 중이어도 이 갈래가 이긴다.
> **아래 조건은 엔진의 두 사실을 함께 미러한다**: 손상 술어의 거부(비-문자열)와, 빈 경로가 뒤에서 맞는
> 실패(빈 문자열 — 그 값은 손상 술어에 안 걸린다)를 한 줄로 접는다. 둘 다 화면에서는 「적용 불가」 한 칸이다.
> 이 줄이 없으면 미리보기는 `would_apply`라고 세고 실행은 거부된다 — "적용된다 해 놓고 안 되는"
> 어긋남이다. **버킷은 `cannot_apply` 그대로다**(그 버킷이 `refused`와 `error`를 함께 받는다)."*

### ⓜ F1-c가 **참으로 만들어** 낡는 「KeyError는 안 잡는다」 경계 서술 3자리 (★ 19판 3판 정정)

**방향이 반대인 낡음이다** — 세 자리가 *"이 래퍼는 `config_path` 결손의 `KeyError`를 못 잡으므로 전체 실패를
막는다고 약속할 수 없다"*고 **정직하게 한계를 적어 두었는데**, F1-c가 `engine.disk_state`의 그 자리를
`Refused`로 바꾸면 **세 래퍼가 전부 그 예외를 잡게 되어 한계가 사라진다.** 한계 서술을 남겨 두면 다음
사람이 없는 구멍을 막으러 온다.

> **현행 ①** `restore._disk_state` 독스트링: *"registry 항목에 `config_path`가 없을 때의 `KeyError`는 현재
> 잡지 않으므로, 모든 손상 상태를 복구 가능한 조회 실패로 접는 경계는 아니다."*
> **개정 ①**: *"★ 19판 — 그 경계가 닫혔다. 등록 항목 손상은 `engine.disk_state`의 `game_or_fail`이
> `Refused(REGISTRY_ENTRY_CORRUPT)`로 내고 그 코드는 위 목록 첫 항이다. 즉 **이 래퍼가 이제 항목 손상까지
> 「조회 실패」로 접는다.**"*
>
> **현행 ②** `main._disk_state_safe` 독스트링: *"미등록·경로 타입·파일 조회 실패는 이 래퍼가 접지만,
> 등록 항목에 `config_path` 키가 없어서 나는 `KeyError`는 현재 잡지 않는다. 따라서 이 래퍼만으로
> `get_overview(detail=True)` 전체 실패를 막는다고 약속할 수 없다."*
> **개정 ②**: *"미등록·경로 타입·파일 조회 실패를 이 래퍼가 접는다. **★ 19판 — 등록 항목 손상도 여기
> 들어왔다**(`engine.disk_state`가 `Refused(REGISTRY_ENTRY_CORRUPT)`를 낸다). 다만 이 래퍼가 지키는 것은
> **`disk_matches` 한 칸**이다 — 목록 조립 자체의 항목 격리는 `get_overview`의 게임별 접기가 한다."*
>
> **현행 ③** `src/rpc.ts`의 `OverviewGame.disk_matches` 주석: *"detail=false이거나 포착된 조회 실패면 빈
> 배열이다. **등록 항목에 config_path가 없어서 나는 KeyError는 현재 포착하지 않아 get_overview 자체가
> 실패할 수 있다.**"*
> **개정 ③**: *"detail=false이거나 포착된 조회 실패면 빈 배열이다. **★ 19판 — 등록 항목 손상도 포착 대상이
> 됐다**(백엔드가 `REGISTRY_ENTRY_CORRUPT`로 거부하고 래퍼가 그것을 접는다). 손상 항목은 이 배열이 비고,
> 목록의 나머지 게임은 그대로 온다."*

### ⓝ `already_registered` 술어가 거짓으로 만드는 `ALREADY_REGISTERED` 단정 2자리 (★ 19판 3판 정정)

**둘 다 범위 한정 없이 단정한다** — §14-H ⓙ 뒤 손상된 기존 항목은 `ALREADY_REGISTERED`가 아니라
`REGISTRY_ENTRY_CORRUPT`로 거부되므로, 그대로 두면 계약 문서가 거짓이 된다.

> **현행 ①** `main.add_game` 독스트링: *"이미 등록된 appid는 `codes.ALREADY_REGISTERED`로 거부한다.
> 경로 변경 기능은 아직 없다. 판정은 `confirm.already_registered`가 한다."*
> **개정 ①**: *"이미 등록된 appid는 `codes.ALREADY_REGISTERED`로 거부한다. 경로 변경 기능은 아직 없다.
> 판정은 `confirm.already_registered`가 한다. **★ 19판 — 그 항목의 등록 기록이 손상돼 있으면
> `REGISTRY_ENTRY_CORRUPT`가 대신 나간다**(§8-D 정규화 규칙): 「이미 등록됨」은 그 기록을 믿을 수 있을
> 때만 참인 진술이고, 못 믿는 `name`·`config_path`를 화면 봉투에 실어 보내지 않기 위해서다."*
>
> **현행 ②** `src/rpc.ts`의 `addGame` 문서: *"이미 등록된 appid는 ALREADY_REGISTERED로 거부된다. 엔진
> add_game이 기존 config_path를 조용히 …"*
> **개정 ②**: 같은 문장 뒤에 *"**★ 19판 — 등록 기록이 손상된 항목은 `REGISTRY_ENTRY_CORRUPT`로 거부된다**
> (그 봉투에는 `name`·`config_path`가 실리지 않는다 — 못 믿는 값이다). 화면은 두 코드를 각자의 문구로
> 그린다."*를 잇는다.

---

## J절. §10-A 신설 4키 — 값 전문과 잠금 처분

### J-0. 현행 관례 확인

- §10-A는 **키별 행 표**다. 잠금 게이트(`test_wording_10a.py`)는 13판에 삭제됐고, *"바이트 값을 명시한다는
  규칙은 유지된다 — 이 문서가 정본이고 대조는 리뷰가 한다"*.
- **12판 관례**: *"위 표에서 **en 바이트를 적은 키는 en도 확정·잠근다**."*
- §10-D(구속): 신설 키는 **그 키를 참조하는 파일이 생기는 단계에 en/ko 동반 편입**.
- §10-E(조사 규칙): 아래 4키는 **치환자가 0개**라 무저촉이다.

### J-1. 개정 조문 전문 — §10-A 표에 4행 추가

> | **`REGISTRY_ENTRY_CORRUPT`(19판 신설 — F1-c)** | ko "이 게임의 등록 정보가 손상돼 동작을 멈췄습니다. 이 게임의 등록을 해제한 뒤, [게임 감지]의 「제외한 게임」에서 다시 포함하거나 파일을 직접 골라 등록해 주세요. 프로필과 백업은 바뀌지 않았습니다." / en "This game's registration record is damaged, so the action was stopped. Unregister this game, then put it back from “Excluded games” in [Detect games] or pick its file yourself. Profiles and backups were not changed." | 에러 문구 5계열의 문법 승계. **★ 복구 동선은 `DELETE_CONFIRM_REDISCOVER`와 같은 사실 구조를 쓴다**(*"등록을 해제하면 자동 감지에서도 제외됩니다. 다시 쓰려면 [게임 감지]의 「제외한 게임」에서 다시 포함하거나 파일을 직접 골라 등록해 주세요"*) — **「등록 해제 → 자동 감지 목록에서 다시 추가」만 말하면 막다른 길이다**: 등록 해제는 그 게임을 감지 제외 목록에 넣으므로 일반 감지 결과에 다시 나타나지 않는다(§8 "삭제 = 등록 해제 + 감지 제외"). 두 동선(제외 뷰의 [다시 포함] · [파일 직접 고르기]) 모두 §6-A·§6-B에 실재하고, 손상 항목의 등록 해제 자체는 §8-D 정규화 규칙이 우회로 열어 둔다. 마지막 문장은 `REGISTRY_*` 계열과 같고 이 코드는 쓰기 **전** 거부라 참이다. ko/en 모두 잠근다 |
> | **`RESET_FAILED`(19판 신설 — F2a)** | ko "초기화를 완료하지 못했습니다. 프로필 데이터가 이미 일부 또는 전부 지워졌을 수 있습니다. 다시 초기화하면 남은 것부터 이어서 지웁니다." / en "The reset could not be completed. Some or all profile data may already have been deleted. Run the reset again to continue with what remains." | **`DELETE_FAILED`와 같은 문법**(§7-5′): 조건부 서술 + 재시도 약속. 약속이 참인 근거는 `RESET_LEFT_NOTE`와 같다(초기화 route가 실패분만 남기고 다음 실행이 남은 것부터 돈다). ⚠️ **프론트 폴백 키 `RESET_ACTION_FAILED`("초기화하지 못했습니다 ({code})")와 다른 것이다** — 이쪽은 백엔드 코드이고 `tCode`가 코드 값을 우선한다. 치환자가 없어 분기 없이 `tCode`만으로 뜬다(§7-5′). ko/en 모두 잠근다 |
> | **`RESET_FRESH_CONFIRM_WARN`(19판 신설 — F1-b)** | ko "⚠ 이 플러그인의 게임 목록 파일을 쓸 수 없는 상태입니다. 초기화하면 목록을 빈 상태로 새로 시작하고, 지금 파일은 이름을 바꿔 그대로 남깁니다. 저장된 프로필과 백업은 지우지 않습니다 — 게임을 다시 등록하면 그 게임에 저장돼 있던 프로필과 백업을 다시 쓸 수 있습니다." / en "⚠ This plugin's game-list file is in an unusable state. Resetting starts the list over empty and keeps the current file under a different name. Saved profiles and backups are not deleted — register a game again to use the profiles and backups it already has." | §7-4′ 2항의 표를 한 문단으로 말한다. **⚠ 기호는 ko·en 양쪽 값의 맨 앞에 유지한다**(§7 세션 확정 — warnBlock 렌더러가 아이콘을 따로 그리지 않는다). **수를 말하지 않는다**(셀 수 없다 — 못 세는 수를 0으로 그리면 거짓이 된다). 재등록 전제 명시는 `RESET_CONFIRM_WARN`의 F23 문법 그대로다. 진입 화면 두 줄의 과대 고지를 **이 창이 교정한다**(H-1). ko/en 모두 잠근다 |
> | **`RESET_OK_FRESH`(19판 신설 — F1-b)** | ko "게임 목록을 새로 시작했습니다. 저장된 프로필과 백업은 지우지 않았습니다 — 게임을 다시 등록하면 그대로 다시 쓸 수 있습니다." / en "The game list has been started over. Saved profiles and backups were not deleted — register a game again to use them as they are." | §7 결과 봉투 `mode:"fresh"`의 **단독 완료 문구**. `RESET_OK`("초기화 작업을 마쳤습니다")로 접으면 지우지 않은 프로필 데이터를 지웠다고 말하게 된다(§15 R16 관측의 그 유형). 조각 조립(`parts.join`)을 타지 않는다. ko/en 모두 잠근다 |

**키 수**: 실물 ko 265 / en 265, 집합 항등(실측) → **19판 후 269 / 269**.
**단계 배정**(§10-D): 네 키 모두 **참조 파일이 생기는 그 커밋에** ko/en 동반 편입한다 —
`REGISTRY_ENTRY_CORRUPT`는 F1-c 커밋, `RESET_FRESH_CONFIRM_WARN`·`RESET_OK_FRESH`는 F1-b 커밋,
`RESET_FAILED`는 F2a 커밋.

**등재를 지키는 수단은 키 종류에 따라 다르다**(K절과 짝):
- **백엔드 코드 2종**(`REGISTRY_ENTRY_CORRUPT`·`RESET_FAILED`) — **F7-1이 직접 잠근다**(codes ⊆ en ∧ ⊆ ko).
- **화면 전용 2키**(`RESET_FRESH_CONFIRM_WARN`·`RESET_OK_FRESH`) — `codes.py` 상수가 아니라 **F7-1 밖이다.**
  이 둘은 **TypeScript `StringKey = keyof typeof en`**(en에 없으면 `t()` 호출이 **컴파일 오류**)와
  **`qa/test_i18n_keys.py`의 ko↔en 집합 항등**의 **결합**으로 지켜진다 — en을 빠뜨리면 빌드가 깨지고,
  en에만 넣고 ko를 빠뜨리면 그 검사가 잡는다.

**잔존어 전수 검사**(§10 머리말 구속): 네 값에 "미완"·"현황 탭"·(프로필 의미의) "설정" 0건 — 확인 완료.

---

## K절. §15 — 검사 신설 2종과 머리말 정정 (F7-1 · F7-2)

### K-0. 현행 조문 인용

§15 머리말(`:2569`): *"**검사는 엔진·데이터 경로에만 만든다.** … **남기는 것 = 틀리면 사용자 파일이 조용히
사라지는 경로**(적용·복원·삭제·초기화·토큰·**코드 계약**·패키징)."*
같은 머리말(`:2612`): *"⚠️ **코드 ↔ i18n 대조 검사는 존재하지 않는다** — `test_codes.py`가 가리키는
`test_i18n_sets.py`가 UI 검사 정리 때 삭제됐다. 실물은 지금 정합이지만 **그것을 지키는 것은 검사가 아니다**."*
같은 머리말(`:2620`): *"**★ 16판 — 검사 총수를 문서에 숫자로 적지 않는다.**"*

### K-1. 개정 조문 전문 ① — §15 머리말 ⚠️ 문단 대체

> ⚠️ ~~**코드 ↔ i18n 대조 검사는 존재하지 않는다** … 그것을 지키는 것은 검사가 아니다~~ →
> **★ 19판 해소**: `qa/test_codes_i18n.py`(F7-1)가 그 자리를 채운다 — `codes.py`의 전 코드가 `en.json`·
> `ko.json` **양쪽에 등재**돼 있고 두 파일의 키 집합이 항등인지 본다.
> ⚠️ **범위를 정확히 적는다**: 잠기는 것은 **`codes.py` 상수**다(19판 신설 2종 포함).
> ⓐ `confirm.py`의 disk_state **분류값**은 `codes` 상수가 아니라 범위 밖이다(19판은 분류값을 신설하지 않는다).
> ⓑ **화면 전용 i18n 키도 범위 밖이다** — 그쪽은 TypeScript `StringKey`와 `qa/test_i18n_keys.py`의 결합이
> 지킨다(§10-A 19판 4행의 「등재를 지키는 수단」).

### K-2. 개정 조문 전문 ② — §15-B에 신규 테스트 2본

> **★ 19판 신설 2본** — 둘 다 §15 검사 정책에 정합한다(**데이터·계약 경로**이고 화면을 재지 않는다).
>
> 1. **`qa/test_codes_i18n.py`(F7-1) — 코드↔번역 전수 대조.**
>    - **잰다**: `codes.all_codes()` ⊆ `en.json` 키 ∧ ⊆ `ko.json` 키 ∧ `en` 키 == `ko` 키.
>    - **못 잰다**: 문구가 *옳은지*. 그것은 이 문서와 리뷰의 몫이다(§10-A와 같은 처분).
>      화면 전용 키의 존재도 못 잰다(K-1 ⓑ).
>    - 왜 `test_i18n_keys.py`에 얹지 않는가: 그 본은 **ko↔en 항등과 빈 값 부재**만 보는 i18n 내부 검사이고,
>      이쪽은 **파이썬 상수와 프론트 자원의 대조**다. 재는 대상이 다르면 본을 가른다(R14의 처분과 같다).
>      *세션 재량으로 기존 본에 갈래를 더하는 쪽을 택해도 계약은 같다(§15-A R16 선례).*
> 2. **`qa/test_delete_preview_contract.py`(F7-2) — `delete_preview` 봉투 계약.**
>    - **잰다**: `remove.delete_preview`가 **unsafe 갈래에서도** `DeleteConfirmParams`의 필수 필드를 전부 싣는가
>      (`evicted` 포함 — 그 필드는 `rpc.ts`에 이미 **필수**로 선언돼 있고 런타임만 빠져 있었다).
>    - 잠그는 것: F4-4.
>
> **검사 총수는 여기 적지 않는다**(16판 규칙 — `build.sh`의 `qa/test_*.py` 글로브가 센다).

---

## L절. §15-D 알려진 한계 — 축소 2건 · 해소 1건 · 신설 3건

### L-1. 축소·해소 (개정 조문 전문)

> | **E18**(13판 R14 — **★ 19판 축소**) | ~~**남은 meta-only 판정 3곳**: `engine.apply_all` · `confirm._preview_one` · `main._disk_matches` 배지~~ → **19판이 앞의 둘을 `store.slot_holds`로 옮겼다**(§5-G). **남은 것은 `main._disk_matches` 배지 하나**다 — 표시 경로이고 손실 경로가 아니다(면제 근거는 13판 그대로). *전수를 주장하는 문장은 그 주장 자체가 검사 대상이다 — 16판이 「셋」을 한 번 고쳤고 19판은 그 수를 다시 줄인다.* |
> | **E52**(18판 — QA R2 ADVISORY-R2-06 — **★ 19판 대부분 닫힘**) | ~~규칙 2가 적용·복원·registry 형제 갈래에 안 갔다~~ → **19판이 닫은 것**: **registry 읽기의 `OSError`**(§14-F′ ⓐ) · **등록 해제 성공 뒤의 registry 저장 실패**(§7-5′ — `DELETE_FAILED` + `profile_delete_started`) · **복원의 슬롯 쓰기 실패**(§14-E″ ⓐ) · **같은 손상 meta가 적용에서 `UNEXPECTED`이던 자리**(§14-E″ ⓑ → `PROFILE_CORRUPT`) · **적용 전 백업 읽기 실패**(§14-E″ ⓒ → `BACKUP_FAILED`). **남는 것 둘**: ⓐ **복원의 config 갈래 쓰기 실패** — `PROFILE_WRITE_FAILED`의 주어가 「프로필」이라 붙일 수 없고 전용 코드는 만들지 않았다(백로그, 재론: 실보고 1건) ⓑ `engine.apply_all`·route의 `except Exception` 자체 — 그것은 뭉뚱그림이 아니라 **게임별 격리·최후 봉투화라는 다른 계약**이고, 19판은 그 안의 **알려진 사건들을** 자기 코드로 빼냈을 뿐이다. **형제 E51은 손대지 않았다**(저장의 읽기 실패 갈래 — 등재 존치) |
> | **§14-F ⚠️ 알려진 한계 — ★ 19판 해소** | ~~i18n 문구가 안내하는 「전체 초기화」 탈출로는 미래 스키마가 구조를 바꾸면 성립하지 않는다(`reset_all`이 옛 구조를 읽다가 `UNEXPECTED`로 죽는다)~~ → **§7-4′의 버전 무관 preflight가 그 자리를 막는다.** 컨테이너가 우리가 아는 모양이 아니면 `reset_all`은 **옛 구조를 읽지 않고** fresh 갈래로 간다(항목 모양이 다른 경우는 §8-D 정규화 규칙의 삭제 우회가 청소한다). `REGISTRY_NEWER`의 i18n 문구(*"이 버전으로 새로 시작하려면 [전체 초기화]를 쓸 수 있습니다"*)가 **처음으로 무조건 참이 된다 — 값은 바꾸지 않는다.** ⚠️ **마이그레이션이 생긴 것은 아니다**(그 조문은 그대로다). 잔여는 아래 E59 |

### L-2. 신설 (개정 조문 전문)

> | **E59**(19판 — F1-c 국소안의 값) | **정상 초기화의 되심기에서 비-숫자 appid 키를 제외한다** — 그 키는 개별 삭제(appid 숫자 검증)로도, 초기화(되심기)로도 청소할 수 없어 **영구히 남는 항목**이었다(실측). 대가: 비-숫자 키가 **경로 봉쇄가 아닌 이유**(I/O 실패 등)로 삭제에 실패했다면 registry에서만 사라지고 `profiles/<key>`가 남는 **유령**이 된다 | **국소안을 고른다.** preflight에서 비-숫자 키 전량을 fresh로 보내는 안은 **키 하나로 전체 초기화**라 과잉이다. 유령의 도달성은 극히 낮다 — 앱은 비-숫자 키를 **만들지 않고**(`add_game`의 appid 검증), 외부 주입 키가 비-숫자이면서 동시에 제자리이고 동시에 I/O로 실패해야 한다. **막아서 잃는 것(영구 잔존 항목)이 더 크다**는 판단은 §14-G ⓐ와 같은 형태다. **회귀 잠금**: `qa/test_reset_all.py`의 탈출 키 행은 *"거부된 탈출 키가 registry에서 사라졌다 = 실패"*를 정답으로 갖고 있다 — **같은 커밋에서 그 기대값을 뒤집는다**(검사 폭 축소가 아니라 **정답 교체**다) |
> | **E60**(19판 — fresh 저장의 실패 보고 / ★ 4판 — 격리 실패의 범위 정정) | fresh 갈래에서 ⓐ **격리 실패는 `REGISTRY_UNREADABLE`로 나간다** — 실제 사건은 *"읽지 못했다"*가 아니라 *"치우지 못했다"*다. **세 갈래가 여기 든다(★ 4판)**: 이름 확보 실패(`os.mkdir`의 EEXIST 아닌 `OSError` — 권한·ENOSPC·읽기 전용 마운트) · 이동 실패(`os.replace`의 `OSError`) · 이름 상한 소진(`_CORRUPT_SEQ_MAX`). *(3판까지 이 항은 `os.replace`만 열거했고, 코드 전문도 `except FileExistsError`만 잡아 나머지가 익명 `UNEXPECTED`로 샜다 — §7-4′ 6항과 함께 닫았다.)* ⓑ **격리 성공 뒤 `atomic_write` 실패**는 `UNEXPECTED`로 나가는데, 그 시점에 `registry.json`은 이미 없어 **탈출은 사실상 성립해 있다**(다음 `load_registry`가 `default_registry()`를 돌려준다) — 화면이 실패라 말하는데 실제로는 빠져나온 상태다 | **코드를 늘리지 않는다.** ⓐ 원인은 봉투 `message`와 로그에 errno·경로로 남고, 문구의 실질 정보(*"프로필과 백업은 바뀌지 않았습니다"*)가 그 자리에서 참이다 ⓑ **자기교정된다** — 사용자가 다시 누르면 이번에는 **정상 갈래**로 들어가 0게임 초기화를 하고 `RESET_OK`(또는 여전히 쓰기가 막히면 `RESET_FAILED`)로 정확히 끝난다. 둘 다 도달에 I/O 실패가 필요하다(5·6급 기본 처분과 같다). **과소 보고는 과대 보고보다 안전한 방향이다** — 사용자가 한 번 더 누를 뿐이고 그 재시도가 무해하다 |
> | **E61**(19판 — 격리물의 수명) | 격리한 손상 원문은 `registry.json.corrupt-<stamp>/registry.json`으로 남고 **앱이 지우지 않는다.** 링도 상한도 없다. 크래시가 `mkdir`과 `os.replace` 사이에서 나면 **빈 디렉터리**만 남는다 | 누적은 **손상 사건당 1건**이다(fresh가 성공하면 다음 실행은 정상 registry를 읽어 이 갈래에 오지 않는다). 데이터 루트를 열거하는 코드가 없어(실측) 다른 판정·표시에 섞이지 않는다. 링을 만들면 *"복구 재료를 앱이 지운다"*는 반대 방향의 위험이 생긴다 — **지우지 않는 쪽이 안전하다.** 빈 디렉터리도 지우지 않는다: 그것이 비었는지 판정하는 코드가 늘고, 그 판정이 틀리면 증거를 지운다 |

---

## M절. §14-H 신설 — 19판의 엔진·store 층별 판별

### M-0. 현행 관례 인용

§14 머리말(`:2014`): *"route 층에서 구현 가능한 것은 엔진으로 내리지 않는다. **이 조건은 15판에도 그대로
유효하다**(fence는 없어졌지만 *가장 얕은 층에서 고친다*는 규율은 fence 때문에 생긴 것이 아니다). …
**각 항의 「왜 엔진인가」가 그 판단이다**."*
§14-D(`:2560`): *"15판의 엔진 변경에는 **허용 diff도 승인 절차도 없다** — 그 자리는 회귀 전량과 코드 리뷰가 대신한다."*

### M-1. 개정 조문 전문 — §14-H 신설

> ### 14-H. 19판 — 손상 registry 3층 대응의 층별 판별 (engine 4 · store 2 · 정책층 7 · route 3)
>
> **정책층 7항의 열거**(수를 적으면 그 수도 검사 대상이다): ① `confirm.needs_confirm` 술어(ⓗ)
> ② `confirm._preview_one` already(ⓗ) ③ `confirm._classify` 정오(ⓗ) ④ `confirm.already_registered`
> 술어(ⓙ) ⑤ `restore.needs_confirm` 보존 배정(ⓚ) ⑥ `restore.target_sha1` 격리(ⓚ)
> ⑦ `confirm._preview_one`의 `config_path` 술어(ⓛ).
>
> **fence는 없다**(§14-D). 이 소절은 승인 절차가 아니라 **「왜 이 층인가」의 기록**이고, 지키는 것은 회귀
> 전량과 코드 리뷰다. 각 항이 *route에서 못 하는 이유*를 댄다.
>
> | | 층 | 자리 | 왜 이 층인가 |
> |---|---|---|---|
> | ⓐ | **store** | `load_registry` 형태 검사 3구멍(§14-F′) | **읽어서 dict를 만드는 것이 이 함수의 일**이다. route로 올리면 14곳 + 관문 1곳이 각자 같은 검사를 갖게 되고 언젠가 하나가 빠진다. **형태**는 store가 보고 **버전이라는 의미**는 여전히 route가 본다(§14-F ③ 개정) |
> | ⓑ | **store** | `save_fresh_registry()` 신설(§7-4′ 6항) | `registry_path`·`atomic_write`·`default_registry`가 전부 store에 있다. route가 데이터 루트에 직접 `os.mkdir`·`os.replace`를 거는 것은 층을 뚫는 것이다. **인자를 받지 않는 시그니처가 버전 가드 우회의 안전장치**다 |
> | ⓒ | **engine** | 손상 항목 술어 `entry_corrupt` + `game_or_fail(require_intact=)` | 실행 계열의 **문이 하나**라는 것이 계약이다. 정책층에 두면 엔진 직접 진입점이 그 문을 안 지난다. **`labels` 등 새 모듈 의존은 만들지 않는다** — 헬퍼는 engine 안에 산다. **★ 4판 — 모듈 공개다**(밑줄 없음): 정책층 미러가 이 술어를 부르므로. 술어를 두 벌 적지 않는 것이 이 항의 전부다 |
> | ⓓ | **engine** | `restore_backup` **슬롯** 쓰기 봉투(§14-E″ ⓐ) | **어느 호출이 「슬롯 쓰기」인지 아는 것은 이 함수뿐**이다. route에서 감싸면 읽기 실패·config 쓰기까지 같은 코드가 된다 |
> | ⓔ | **engine** | 적용 전 백업 블록 재배치(§14-E″ ⓒ) | 같은 함수 안의 `try` 경계 문제다. 밖에서는 손댈 수 없다 |
> | ⓕ | **engine** | `apply_all` already 판정 → `slot_holds`(§5-G) | 판정이 엔진과 정책층에서 갈리면 미리보기와 결과가 어긋난다. **둘을 같은 커밋에서 같은 술어로** |
> | ⓖ | **store + engine** | `profile_file_path` isinstance 게이트 + engine의 `PROFILE_CORRUPT` 구분(§14-E″ ⓑ) | 게이트는 store(경로를 만드는 자리), **코드 선택은 engine**(거부 문구를 아는 자리). 층을 갈라야 «미저장»과 «손상»이 안 섞인다 |
> | ⓗ | **정책층** | `confirm.needs_confirm` 술어 · `_preview_one` already · `_classify` 정오 | 확인·미리보기 판정은 원래 `confirm.py`의 일이다(§14-E 기각 기록: *"판정은 `confirm.py` 한 곳, 엔진은 쓰기만"*) |
> | ⓘ | **route** | `reset_all` preflight·fresh 갈래·`mode`·**비-숫자 키 되심기 제외** · `delete_game`/`reset_all` 부분완료 · 조회·집계 격리 · **`list_backups`의 `require_intact=False`**(★ 3판) | **전부 route에서 할 수 있는 일이라 route에서 한다.** U5 가드를 route에 둔 §14-F의 판단과 같다 |
> | ⓙ | **정책층** | `confirm.already_registered`의 손상 술어(★ 3판) | **판정이 곧 거부인 자리**다. 이 함수는 `game_or_fail`을 지나지 않고 `(reg.get("games") or {}).get(appid)`로 직접 읽으며, 그 뒤 `entry.get("name")`·`entry.get("config_path")`가 **비-dict에서 그 자리 `AttributeError`**를 낸다 — 등록 route가 통째로 `UNEXPECTED`로 죽는다(오늘). 술어를 적용해 **`Refused(REGISTRY_ENTRY_CORRUPT)`**를 내면 그 죽음이 이름 있는 거부가 된다. **이 문이 `engine.add_game`의 `entry.update` 사망점도 함께 막는다** |
> | ⓚ | **정책층** | `restore.target_sha1`의 config 갈래 **isinstance 격리** + `restore.needs_confirm`의 **`require_intact=False` + 비-dict 접기**(★ 3판) | **오늘 나가는 성공 둘이 여기 걸려 있다**(§8-D 판별 기준): `main.list_backups`의 목록과 `main.restore_backup`의 슬롯 `already`다. `target_sha1`은 답을 모를 때 이미 **`None`(모름)**을 돌려주도록 계약돼 있으므로(*"모르면 `None`이라 배지는 안 그려지고 `already`도 성립하지 않는다 — 안전한 방향"*), 손상 항목을 그 「모름」에 합류시키는 것이 최소 변경이다. `needs_confirm`은 **판정만 하고 쓰지 않는 자리**이고, 실제 쓰기의 문은 `engine.restore_backup`(`require_intact=True`) 하나로 남는다 — **문은 여전히 하나다** |
> | ⓛ | **정책층** | `confirm._preview_one`의 `config_path` 술어 정합(★ 3판 · 형태 확정 ★ 4판) | 미리보기는 **엔진 판정의 미러**이고 미러가 갈리면 화면이 *"적용된다 해 놓고 안 되는"* 말을 한다. 엔진 술어를 정책층에서 **다시 적지 않고 `engine.entry_corrupt(entry)`를 부른다**(그래서 ⓒ의 헬퍼가 모듈 공개다). **빈 문자열 조건은 미러 쪽에만 남는다**(엔진에서는 경로 가드가 그 일을 한다). **조건의 순서가 계약이다** — 술어 호출이 앞이라야 truthy 비-dict entry에서 `.get`이 단축 평가로 건너뛰어진다. 전문은 §8-D |
>
> **`remove.py`는 「엔진」이 아니다**(fence 시절부터 밖이었다) — 삭제 우회(§8-D)와 `evicted` 필드(F4-4)는 이 표에 세지 않는다.
>
> **ⓙ에 붙는 판단 기록(★ 3판)**:
> - **오늘 `ok:true`가 없다**: 비-dict에서는 `UNEXPECTED`, 결손·`{}`에서는 `ALREADY_REGISTERED`(둘 다
>   `ok:false`). **이 route가 손상 항목에서 성공을 내는 세계는 없다** — §8-D 판별 기준이 실행 계열을 지정한다.
> - **왜 `ALREADY_REGISTERED`가 아닌가**: 그 코드의 문구는 *"이미 등록된 게임입니다 — 다른 파일로 바꾸려면
>   먼저 등록을 해제해야 합니다"*로 **등록 해제라는 방향까지는 맞게 가리킨다.** 그래서 「막다른 길」이
>   근거는 아니다. 근거는 둘이다: ① **참이 아닌 것을 말한다** — 그 항목은 「등록돼 있다」가 아니라 「등록
>   기록이 깨져 있다」이고, 화면이 정상 등록인 척하면 사용자는 자기 데이터가 멀쩡하다고 믿는다(§15 R16이
>   기록한 유형) ② **`_fail(..., **known)`이 그 항목에서 읽은 `name`·`config_path`를 화면에 싣는다** —
>   못 믿는 기록을 표시 재료로 그대로 내보내는 자리다. `REGISTRY_ENTRY_CORRUPT`는 그 둘을 싣지 않고,
>   문구가 **등록 해제 뒤의 복귀 동선**(제외 뷰의 [다시 포함] · [파일 직접 고르기])까지 마저 말한다.
> - **`add_game`은 `@mutating`이다** — 이 거부는 쓰기 전이므로 `REGISTRY_ENTRY_CORRUPT`의 마지막 문장
>   (*"프로필과 백업은 바뀌지 않았습니다"*)이 이 자리에서 참이다. 계약 문서 2자리가 함께 낡는다(I절 ⓝ).
> - **`engine.add_game`에 술어를 심지 않는다**: `setdefault`가 결손 dict를 정상 갱신하므로 술어를 심으면
>   **「손상 항목을 재등록으로 고치는 길」이 막힌다.** 앞단(ⓙ)이 그 문을 잠그는 것으로 족하다(§8-D C-2-3).
>
> **ⓚ의 격리 형태**(「접는다」의 뜻이 자리마다 갈리지 않게 조문으로 못 박는다):
> ```
> entry = (reg.get("games") or {}).get(str(appid))
> config_path = entry.get("config_path") if isinstance(entry, dict) else None
> return store.sha1_file(config_path) if isinstance(config_path, str) else None
> ```
> **`store.sha1_file("")`에 기대지 않는다** — 지금 결손 dict가 사는 것은 `or ""` → `sha1_file("")` → `None`
> 이라는 **우연한 접힘**이고, 그 우연을 계약으로 승격시키면 `sha1_file`의 구현이 바뀔 때 조용히 깨진다.
> **모름은 모름으로 명시해서 낸다.**
> **`restore._disk_state`·`confirm._disk_state_or_none`·`main._disk_state_safe`는 코드를 고치지 않는다** —
> 세 래퍼의 `except`가 이미 `engine.Refused`를 잡으므로 자동으로 접힌다. 낡는 것은 독스트링뿐이다(I절 ⓜ).

### M-2. 근거

- 이 표의 존재 이유는 **「가장 얕은 층에서 고친다」 규율의 이행 기록**이다. fence가 하던 「기준선 대조」는 15판에
  회귀 전량과 리뷰로 대체됐고(§14-D), 남은 것은 **판단의 근거를 문서에 남기는 일**뿐이다.
- ⓘ 행이 가장 중요하다 — **route에서 되는 것을 엔진으로 내리지 않았다**는 선언이다.

---

## N절. 설계 무변경 확인 (조문 0)

*무엇을 안 고치는지 적지 않으면 다음 사람이 빠뜨린 것으로 읽는다.*

| 항목 | 처분 |
|---|---|
| **F4-4**(`remove.py` unsafe 갈래에 `"evicted": []`) | **조문 0.** `DeleteConfirmParams.evicted`는 `rpc.ts`에 **이미 필수**로 선언돼 있다 — 런타임이 계약을 안 지키고 있었을 뿐이다. **잠금만 신설**(F7-2, K절) |
| **F3**(`store.py` 백업 정렬 트레일링 주석 1곳) | **조문 0.** 화면 비노출·주석 정정. §5-C 백업 정렬 조문은 이미 `backup_order_key`를 정본으로 갖고 있다 |
| **F5**(테스트 리터럴 5건) | **조문 0.** 검사 로직·폭 무변경. **열거를 믿지 말고 전수 grep으로** 센다(실측: 「동치성」 3곳·「5종」의 실제 절 6개) |
| **F6**(조사·인계 문서 정정 부기) | **조문 0.** 캠페인 관례(취소선 + 정정 + 근거 링크) |
| **§8-B `exclude.is_excluded`** | **무변경 — 조문 그대로 살아 있다**(`:1582`가 공개 API로 명시) |
| **§5-C 백업 이름 표시 문구 4값 · `PROFILE_META_CORRUPT` 복구 안내** | **무변경.** 사용자 결정 제외분이고 관련 조문을 건드리지 않는다 |
| **`RESET_ZONE_BODY`·`RESET_HINT` 값** | **무변경**(H절 — 값이 아니라 소관을 한정한다) |
| **`REGISTRY_NEWER` 값** | **무변경**(L-1 — 그 문구가 참이 되는 것이지 문구가 바뀌는 것이 아니다) |
| **§14-A/B/B′/C/D′/E′ 본문 · §5-E 지문 계약 · §5-F 토큰 계약** | **무변경.** 19판은 이 조문들 위에 갈래를 더할 뿐 계약을 바꾸지 않는다 |

---

## O절. 결정 기록 · 정합 확인 · 이견

### O-1. R19-1·R19-2 확정 — fresh 격리 방법 (2판 재설계)

**확정: `os.mkdir`의 EEXIST로 이름을 구조 확보하는 격리 디렉터리**(§7-4′ 6항 코드 전문).

| 안 | 내용 | 판정 |
|---|---|---|
| **(가) mkdir 격리 디렉터리** | `mkdir(registry.json.corrupt-<stamp>[-seq])` → 성공한 이름 안으로 원문을 `os.replace` | **채택.** ① **no-clobber가 구조적이다** — `mkdir`은 목적지가 무엇이든(일반 파일·디렉터리·**dangling symlink** 포함) `EEXIST`로 실패한다. 검사-후-행동 창이 없다 ② **유형 불문 성립** — 목적지가 방금 만든 빈 디렉터리 안이라 원문이 파일이든 심링크든 디렉터리든 rename이 성립한다 ③ 읽기 권한이 필요 없다(디렉터리 쓰기 권한만) — *정확히 필요한 경우*(chmod 000)에 동작한다 |
| (나) 1판안: `exists` 루프 + `os.replace` | `make_backup` 관용구 승계 | **기각(반증 성립).** `os.replace`는 목적지가 있으면 덮는 연산이고 `exists` 검사와 rename 사이 창이 남는다. 게다가 `os.path.exists`는 **dangling symlink를 거짓으로 본다** — 그 이름이 dangling link면 조용히 덮인다. 선례인 `make_backup`도 같은 창을 갖지만 **거기서 잃는 것은 링 10칸 중 하나**이고 여기서 잃는 것은 **사본이 없는 유일한 증거**다 |
| (다) `O_CREAT\|O_EXCL` 선점 + rename | 이름을 파일로 선점 | **기각.** `rename(2)`는 원본이 **디렉터리**이면 목적지가 없거나 빈 디렉터리여야 한다 — 선점해 둔 빈 *파일* 위로 디렉터리를 옮길 수 없다. 유형별 분기가 되살아난다 |
| (라) `os.link` + `unlink` | EEXIST가 구조적 | **기각.** 디렉터리는 하드링크할 수 없다(EPERM) |
| (마) 창을 명시적으로 수용 | (나)를 쓰되 한계로 등재 | **기각.** (가)가 같은 비용에 구조적 보장을 준다 — 수용할 이유가 없다 |

**함께 확정한 것 셋**(1판의 잘못된 논거를 갈아 끼운다):
- **「rename 실패 세계 = atomic_write 실패 세계」 등치는 삭제한다**(거짓 — 유형 충돌·경합은 부모 디렉터리가
  쓰기 불가라는 뜻이 아니다). 격리 실패 시 무쓰기의 진짜 근거는 **「증거를 잃지 않는 쪽으로 접는다」**이다:
  fresh 쓰기는 `atomic_write`가 그 경로를 덮는 일이라, 원문을 치우지 못한 채 진행하면 유일한 증거를 지운다.
- **fsync 내구성 단정도 삭제한다**(`atomic_write`는 디렉터리 fsync 실패를 **경고로 접는다**). 대신
  **크래시 중간 상태 3종이 모두 안전하고 재시도 가능하다**를 논증한다(§7-4′ 6-1).
- **적용 범위를 한정한다**: dangling `registry.json` 심링크는 `load_registry`의 `os.path.exists`가 거짓이라
  **오류 없이 `default_registry()`가 반환되어 fresh에 진입하지 않는다.** 그 경우 정상 갈래의 `atomic_write`가
  심링크 자신을 대체하는데, 그것은 **현행 동작이고 이 초안이 바꾸지 않는다.**

### O-2. R19-3·R19-4 세션 확정 기록

| # | 사안 | 확정 | 근거 |
|---|---|---|---|
| **R19-3** | 봉투 판별자 이름 | **`mode` 채택**(세션 확정 2026-08-30) | popup.tsx의 `kind`는 **프론트가 만들어 프론트가 읽는 뷰·스펙**의 판별자로 층이 다르고, 봉투에서 `kind`를 쓰면 `BackupKind`("백업 종류")와 뜻이 겹친다. FIXPLAN(v6)의 필드 이름과도 일치한다 |
| **R19-4** | `RESET_FAILED`의 프론트 분기 | **분기 0 채택**(세션 확정 2026-08-30) | `tCode`가 `code in en`이면 코드 값을 우선한다(실측). 갈릴 문장이 없는 코드에 분기를 두면 죽은 코드가 하나 는다. **면제 범위는 「사실 필드가 없는 코드」로 한정**한다 — `tCode`는 `res.params`를 소비하지 않으므로 `DELETE_FAILED`류는 계속 명시 분기가 필요하다(§7-5′ ⚠️ 문단) |

### O-3. FIXPLAN v6 · QAPLAN v5 정합 확인 (1판의 「차이 신고」를 대체)

**2판까지**: 세션이 FIXPLAN v5를 **두 자리 정정 완료**했다 — ① F2a의 「프론트 분기 1개」 → **분기 0**(R19-4)
② F2b의 쓰기 자리 → **슬롯 `write_profile`만**(config 갈래는 백로그).
QAPLAN v4의 G4 「전 game entry 비-dict」 행도 세션이 **「정상 reset 성공」**으로 정정했다(편집 오기) —
이 초안의 §8-D 정규화 규칙(항목 손상은 컨테이너 preflight가 아니라 게임별 격리·삭제 우회로 처리)과 정합한다.

**★ 3판**: 3판 정정이 방법 정본·합격선에 **2차 낡음**을 만들어 세션이 두 문서를 함께 올렸다.
- **FIXPLAN → v6**(5항): F1-a ③ 조건식(`type(version) is int and version <= REGISTRY_VERSION`) ·
  F1-c 실행 계열의 **정의 교체**(「`game_or_fail`을 지나는 전부」 폐기) · 우회 목록에
  **`main.list_backups`·`restore.needs_confirm`** · 조회 목록에 **`restore.target_sha1`** ·
  판정 목록에 **`confirm.already_registered`**와 **`_preview_one` 술어 정합**.
  **실행 순서·커밋 단위·제외 5건은 v6에서 바뀌지 않았다.**
- **QAPLAN → v5**: G1 r1~r3 행에 **생존 오라클 4개**(결손 `list_backups` · 비-dict + **config-target 백업**
  `list_backups` · **비-dict 슬롯 `already` 보존** · 배지 미표시) + `already_registered` 행 신설,
  사망점 체크리스트에 **자리별 처분** 명시, G4에 **비-int version 4세계**와 **`config_path` 비-문자열·
  빈 문자열 세계**.
**★ 4판**: 3판 정본을 대상으로 한 반증 3패스에서 **방법 정본·합격선의 2차 낡음이 다시 나왔고** 세션이 함께 올렸다.
- **FIXPLAN → v7**: F1-b의 격리 방식을 **R19-1(디렉터리안)으로 명문화**(v6까지 남아 있던 *"`registry.json.corrupt-<stamp>`로 보관 · 동명 존재 시 접미 증가"*는 **O-1이 기각한 파일안**이다 — 방법 정본만 따르면 기각된 안이 되살아난다) · F7-1 항의 *"F1-b 신설 코드"* 정정 · 조회 목록에 `get_overview`의 **정렬 키** 지목.
- **QAPLAN → v6**: fresh 게이트에 **격리물의 형(디렉터리)·원문 바이트 보존·충돌 3종 no-clobber** 단언 · G1 머리말에 **역전/무회귀 오라클 갈래** 명시(3판 신설 생존 오라클이 *"수정 전 FAIL"* 규칙과 충돌하고 있었다) · 생존 오라클 3행 추가 · *"F1-b 신설 코드"* 2자리 정정.
**★ 4판 후속 — 결정 전수 동기화(FIXPLAN v8 · QAPLAN v7)**: 같은 유형의 누락이 세 번 나(격리 방식 · 판별 기준 · 술어 가시성) 세션이 **R19 4판의 구속력 있는 결정을 전수로 뽑아 자리별 대조**했다. **설계 조문은 하나도 바뀌지 않았고**, 방법 정본·합격선에서 다음이 정정됐다:
- **[다르게 말하던 것]** 술어 가시성 — FIXPLAN이 *"헬퍼는 `engine` 내부(비공개)로"*라 적어, 그대로 따르면 `confirm._preview_one`이 부를 수 없어 **술어가 두 벌**이 된다(§14-H ⓒ·ⓛ이 닫은 결함). **`engine.entry_corrupt`(모듈 공개)**로 정정하고 미러의 **호출 형태·조건 순서**를 함께 실었다.
- **[아무 말도 안 하던 것 — 채운 것]** 로더 **검사 순서**(§14-F′) · fresh **스코프 분리**(§7-4′ 4항) · **fresh 갈래에는 `RESET_FAILED`가 안 나간다**(§7-5′ — 「fresh」가 두 뜻으로 쓰이는 자리다) · **⑤-1 주석 보존·병합**(B-5) · **낡음 연쇄의 정본은 I절**이라는 지목 · `glue_only` 정리(§14-E″) · QAPLAN 사망점 목록의 **`get_overview` 정렬 키**.
- **[아무 말도 안 해도 되는 것]** §14-H 층 기록 · §15-D 한계(E59~E61) · §10-A 문구 값 · `confirm.apply_needs_confirm`(기본값 `require_intact=True`가 그대로 정답이라 방법 문서가 말할 것이 없다).
**★ 4판 후속 2 — 3차 반증(동기화 범위, `codex-out/REFUTE-SYNC-LAST.md`)**: **판별 기준의 재현성은 반박 실패**로 그 축이 닫혔다(9자리·비-호출 소비 지점에 새 반례 없음). 방법·합격선에서 6건이 더 정정됐고 **설계 조문은 또 하나도 바뀌지 않았다**(FIXPLAN v9 · QAPLAN v8):
① **정상 갈래의 `mode:"normal"`**이 방법 문면에 없었다 — 그대로 구현하면 `switch (p.mode)`가 `default`로 떨어져 **정상 초기화 확인창이 안 뜬다**(§7-4′ 3항·§7 결과 봉투가 둘 다에 요구한다). ② 격리 의사코드의 `atomic_write` 인자가 **dict**였다(실물은 bytes — §7-4′ 6항 전문의 `json.dumps(...).encode("utf-8")`). ③ 생존 오라클의 **갈래 표기 자기모순**(ⓔ·ⓕ는 역전이다). ④ G3의 *"프론트 분기 도달"*이 **R19-4(분기 0)와 충돌**했다. ⑤ 실행 계열을 **열거가 아니라 범위로** 적고 **「그대로 두는 자리」**(`apply_needs_confirm` 등 · 기본값 `True`)를 명시했다. ⑥ **프론트 정상 확인 계약**(`makeResetConfirmSpec` 매개변수 좁힘 · unknown-mode fail-closed)이 결정 목록에 없었다.
**판정 기준도 함께 못 박았다**: *"방법·합격선이 설계와 어긋나거나 불완전한 서술로 오구현을 유도하면 결함이고, 방법이 침묵하되 설계가 그 자리의 정본으로 지목돼 있으면 허용"*이다 — 그래서 §10-A의 i18n 값·I절 낡음 연쇄·§15-D 한계는 **옮겨 적지 않고 지목만** 둔다(값·목록을 두 벌 두면 갈린다. ②가 그 대가가 실제로 난 자리다).
**그 결과 세 문서 사이의 모순은 0이다** — 전 항목 대조 완료.

### O-4. 이견 1건 — 세션 브리핑의 「§14 엔진 fence 신고」 전제 (1판 승계)

브리핑은 *"§14 엔진 fence — 신고할 자리와 관례"*를 미확인 항목으로 지정했으나 **fence는 15판에 폐지됐다.**
그 지시를 문자 그대로 따르면 **폐지된 제도에 신고하는 조문**이 된다 — 이 초안은 §14의 **현행 관례**를 따라
§14-H를 신설했다(M절). 세션이 다르게 판정하면 M절만 교체하면 되고 다른 절은 M절에 의존하지 않는다.

**열린 결정: 0건.** (R19-1·R19-2는 참모 재설계로, R19-3·R19-4는 세션 판정으로 전건 확정.)

### O-5. 3판 미확인·조건부 (구현 워커에게 전달할 것)

1. **`main._profile_ready`의 `profile_file_path` KeyError 주석은 아직 참이다** — §14-E″ ⓑ가 더하는 것은
   **비-dict meta의 isinstance 게이트**이고, 그 주석이 말하는 것은 **dict인데 `filename` 키가 없는 meta**의
   `KeyError`다. **구현이 게이트를 `filename` 결손까지 넓히면 그 주석이 낡는다** — 그때는 I절에 자리를
   하나 더 더한다.
2. **빈 `config_path`(`""`)는 이번 범위 밖이다(세션 확정)**: 그 값은 손상 술어에 걸리지 않으므로 오늘 동작이
   그대로 남는다 — `check_path`가 통과하면 `store.atomic_write("")`의 `os.replace(tmp, "")`가 `OSError`를
   내 route가 `UNEXPECTED`로 끝나고, cwd의 부모에 임시 파일이 하나 남는다(`atomic_write`가
   `dirname(abspath(""))`에 `mkstemp`한다). 술어를 *"비어 있지 않은 문자열이 아니면 손상"*으로 한 단어
   넓히면 그 자리가 이름 있는 거부가 되지만, **2판이 확정한 술어 문면을 바꾸는 일이고 도달성이 E59의
   「좀비 키」와 같은 등급(외부 편집 전용)**이라 넓히지 않는다. **재론 조건: 실보고 1건.**
   미리보기 쪽 방어는 §8-D 미러 조문의 truthiness 조건이 이미 맡는다.
3. **3판의 생사 판정은 전부 코드 판독이다**(저장소 무수정 제약 하에서 하네스 실행은 하지 않았다).
   특히 **「비-dict + 슬롯 `already` 보존」 오라클이 3판 최심각 정정을 잠그는 유일한 기계 판정**이므로,
   QAPLAN G1이 그 한 행을 실측으로 확정한다.

---

## P절. 파급 총괄 · 편입 지점 · 착수 순서

### P-1. 파일별 파급 총괄

| 파일 | 절 | 내용 |
|---|---|---|
| `py_modules/gfxp/store.py` | A · B · E · I | `load_registry` 형태 검사 3 + rm 문구 제거 · **`save_fresh_registry()`(**인자를 받지 않는다** — 밖에서 만든 dict가 못 들어오는 것이 버전 가드 우회의 안전장치다: §7-4′ 6항·§14-H ⓑ)·`_CORRUPT_SEQ_MAX` 신설** · `profile_file_path` isinstance 게이트(**거부만 한다 — `None` 반환으로 끝내면 engine이 `PROFILE_MISSING`으로 오표기하므로 코드 선택은 engine이 한다: §14-E″ ⓑ·§14-H ⓖ**) · `save_registry` 독스트링(ⓕ) |
| `py_modules/gfxp/engine.py` | C · E · G · I | 손상 술어 **`entry_corrupt`(모듈 공개 — 밑줄 없음. 정책층 미러가 부른다: C-1·§14-H ⓒ·ⓛ)** + `game_or_fail(reg, appid, require_intact=True)`(**기본값이 `True`**) · `restore_backup` **슬롯 쓰기 1자리** · 적용 전 백업 블록 재배치 · 대상 meta 비-dict → `PROFILE_CORRUPT` · `apply_all` already·row 격리 **+ 외곽 except 주석 정정(I ⓚ — ★ 3판)** |
| `py_modules/gfxp/confirm.py` | C · F · G · I | `needs_confirm` 술어 · **`already_registered` 술어(★ 3판)** · `_classify` 정오 + 상수 주석 · `_preview_one` already **+ `config_path` 술어 정합(★ 3판 — `engine.entry_corrupt(entry) or not entry.get("config_path")`. **조건의 순서가 계약이다**: 술어 호출이 앞이라야 truthy 비-dict에서 `.get`이 단축 평가로 건너뛰어진다) + 주석 정정(I ⓛ)** |
| `py_modules/gfxp/restore.py` | C · I(★ 3판) | `target_sha1` config 갈래 isinstance 격리 · `needs_confirm`의 `require_intact=False` + 비-dict 접기 · `_disk_state` 독스트링(I ⓜ①) — **`_disk_state` 함수 코드는 무변경** |
| `py_modules/gfxp/remove.py` | C · N | 삭제 2함수의 우회(**`require_intact=False`** + 비-dict → `{}` 접기) · unsafe 갈래 `"evicted": []` |
| `py_modules/gfxp/labels.py` | A | 거짓 docstring 재작성 |
| `py_modules/gfxp/codes.py` | C · D · I | `REGISTRY_ENTRY_CORRUPT`·`RESET_FAILED` 상수 + `REGISTRY_NEWER` 주석 축소 **+ 모듈 독스트링의 「맞대는 검사도 없다」 정정(I ⓘ① — ★ 3판)** |
| `main.py` | B · C · D · I | `reset_all`(preflight·fresh·`mode`·부분완료·row 격리·비-숫자 키 되심기 제외) · `_reset_preflight`·`_reset_fresh`·`_reset_fresh_fingerprint`·`_RESET_FRESH_SCOPE` · `delete_game`(부분완료) · `get_overview` 격리(**★ 4판 — `sorted(reg["games"], key=…)`의 정렬 키 포함**)·`_profile_total` 격리 · **`list_backups`의 `require_intact=False`(★ 3판)** · `_save_registry` 독스트링(ⓖ) · **`_disk_state_safe` 독스트링(I ⓜ②) · `add_game` 독스트링(I ⓝ① — ★ 3판)** |
| `src/rpc.ts` | B · I | 판별 유니언·`ResetMode`·`ResetAllResult.mode`(**★ 3판 — 현행 주석 7블록 보존·병합**) · `deleteGame` 독스트링(ⓒ③) · **`OverviewGame.disk_matches` 주석(I ⓜ③) · `addGame` 문서(I ⓝ② — ★ 3판)** |
| `src/confirmSpecs.tsx` | B | **`makeResetConfirmSpec` 매개변수 타입을 `ResetNormalConfirmParams`로 좁힌다**(유니언을 그대로 받으면 fresh에 없는 6필드 접근이 TS 오류 — 본문은 무변경, `import` 이름도 함께: B-5 ⑤-2) + `makeResetFreshConfirmSpec` 신설 |
| `src/SettingsPopup.tsx` | B | 성공·확인 두 분기 + 주석 정정 |
| `src/i18n.ts` | I | `tCode` 독스트링(ⓖ) |
| `src/i18n/ko.json`·`en.json` | J | **4키 신설**(265 → 269, 항등 유지) |
| `qa/test_reset_all.py` | L(E59) | 좀비 키 기대값 **정답 교체** |
| `qa/test_confirm_equivalence.py` | C | print 리터럴 괄호 문면 현행화(로직 무변경) |
| `qa/test_codes.py` | E · I | `glue_only`에서 `PROFILE_WRITE_FAILED` 제거 **+ 독스트링의 「번역 키와 맞대는 검사는 없다」 정정(I ⓘ② — ★ 3판)** |
| `qa/test_apply_preview_equivalence.py` | C · E · I(★ 3판) | 세계 표 650·660 · 660 해설 · 기대 버킷 트레일링 주석(**문서 4자리**) **+ 세계 2개 추가**(`config_path: 123` · `""`) — **검사 로직·폭 무변경** |
| `qa/test_codes_i18n.py`·`qa/test_delete_preview_contract.py` | K | **신설 2본** |

### P-2. 정본 편입 지점 (채택 시 세션이 밟는 순서)

1. 제목줄 「개정 18판」 → **「개정 19판」**
2. **§5-E-2** 4분류 각주(F-1) · **§5-G** 두 문장 **대체**(G-1 = 낡음 ⓔ)
3. **§7** — 상태 분기표 「조회 실패」 행 대체(B-1) · **§7-4′ 신설**(B-2) · 결과 봉투 조문 대체(B-3) ·
   **§7-5′ 신설**(D-1) · 팝업 S 스케치 각주 신설(H-1) · 흐름 설명 개정(I ⓑ)
4. **§8-D** — reset 3행 교체·1행 신설(B-4) · `rpc.ts` 블록에 19판 주석 3줄 · **정규화 규칙 확장**(C-1 —
   **★ 3판 문면**: 판별 기준 한 문장 + 3층 표 + `require_intact=False`의 뜻 + 미리보기 미러 조문.
   **예외 각주는 없다**) · `DELETE_FAILED` params 행 개정(I ⓒ①) · 「토큰 6종」→7종(I ⓓ)
5. **§10** — 머리말 「28→30종」(I ⓗ) · **§10-A 4행 추가**(J-1) · `DELETE_FAILED_BEFORE_DELETE` 행 개정(I ⓒ②)
6. **§14** — **§14-F′ 신설**(A-1 — **★ 3판 ⓒ 조건식**) · §14-F **제목·③ 교체**(I ⓕ) · §14-F 말미 한계에
   **해소 부기**(L-1) · **§14-E″ 신설**(E-1) + §14-E′ 말미 `glue_only` 부기 · **§14-H 신설**(M-1 —
   **★ 3판: ⓙ·ⓚ·ⓛ 3행 포함, 머리말 층별 수 `정책층 7`, ⓘ 행에 `list_backups`**)
7. **§15** 머리말 ⚠️ 문단 대체(K-1) · **§15-B** 2본 등재(K-2) · **§15-D** E18·E52 대체 + E59~E61 신설(L)
8. **§19** — 19판 항 신설

**★ 3판 — 편입 지점의 수는 늘지 않았다.** 3판이 더한 문면은 전부 위 8지점 **안**에 들어간다:
- **B-5의 3판 단서**(⑤-1 주석 보존·병합)는 정본에 편입되는 조문이 아니라 **구현 지시**라 지점이 아니다.
- **I절 신설 6항(ⓘ~ⓝ)**도 지점이 아니다 — 대상이 전부 **코드 주석·검사 파일 문서**이고
  `docs/DESIGN-UX-2026-08-11.md` 본문이 아니다. 편입 방식은 P-3의 **「I절 낡음 연쇄는 각 관련 커밋에 분배」**
  규칙 그대로다(ⓘ→F7 커밋 · ⓙ→F1-c와 F4-1 커밋에 분할 · ⓚⓛⓜⓝ→F1-c 커밋).
- **C-2-1~C-2-3의 전수 배정표**는 근거이지 조문이 아니다 — 정본에 옮기지 않는다(옮기는 것은 §8-D의
  판별 기준 한 문장과 §14-H의 층별 행이다).

### P-3. 커밋 단위(FIXPLAN 실행 순서와 동일 — 이 초안이 순서를 바꾸지 않는다)

```
0. 사전  주석 캠페인 64파일 분리 커밋 · repro 단언화 · repro_restore_meta 대조군 ·
         test_apply_preview_equivalence 기준선 · 하네스 격리·정리
1. F1 ①  A절(§14-F′) + C절(§8-D 정규화·술어)            → G1 r1~r3·r6(a) + G4
   F1 ②  B절(§7-4′ · 봉투 · 프론트 3파일 · i18n 2키)     → G1 F1-b 전용 행
2. F2a   D절(§7-5′ · i18n 1키)                          → repro_init1/reset 역전
3. F3    (주석 1곳)
4. F4    E절 ⓑⓒ · F절 · G절 — 각각 독립 커밋            → G1 해당 행
5. F2b   E절 ⓐ(슬롯 쓰기만)                             → repro_restore_meta 역전
6. F5    (리터럴)
7. F7    K절 신설 2본
8. F6    (문서 정정 — 병행 가능. I절 낡음 연쇄는 각 관련 커밋에 분배)
→ QAPLAN 게이트로 검증 라운드
```

**착수 전 확인 3가지**: ① `qa/test_apply_preview_equivalence.py`를 실제로 돌려 기준선을 잡을 것(A군 격리라
F1 뒤에도 초록일 수 있다 — 초록이 「항목 격리 계약 생존」을 증명하지 못한다는 사실을 판정서에 명기)
② `qa/test_discover_routes.py`가 잡은 `main.py` **소스 문자열 앵커**(공백 포함)를 깨뜨리지 말 것
③ **한 F 안에서 파일을 고칠 때는 통독 게이트** — 조각 치환이 아니라 블록을 다시 쓰고 고친 뒤 통독.
