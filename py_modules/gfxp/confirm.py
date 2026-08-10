"""저장이 **기존 프로필을 실제로 덮어쓰는가**를 판정한다 — 순수 조회, 파일을 바꾸지 않는다.

설계 정본 §2-E-0. M1 `ui_tk._confirm_overwrite`(`:649-684`)의 판단을 **분기까지 그대로** 옮긴 것이다.

### 왜 자기 파일에 사는가 — 셋 중 어디에 둬도 규칙을 깬다
- `engine.py` → **diff fence 위반**(허용 목록에 없다). 엔진은 M1 실사용 코드와 바이트 동일선을 지킨다
- `main.py`  → *"접착층은 정책 판단 금지"*(§2-C) 위반
- 프론트     → **fail-closed가 깨진다.** 프론트가 조건을 틀리면 확인 없이 덮어쓴다

→ **fence 밖의 새 파일**이면 셋 다 피한다. 파생 이득: 순수 함수라 Decky도 tkinter도 없이 테스트된다.

### ⚠️ 이 함수의 반환은 M1과 **뜻이 반대**인 곳이 있다
M1 `_confirm_overwrite`는 `True` = *"저장을 진행하라"*였다. 여기는 `True` = *"물어야 한다"*다.
M1이 `True`(진행)를 돌려주던 세 경우(meta 없음 · 내용 동일 · meta 읽기 실패)가 전부
여기서는 `False`(안 물음)가 된다. **옮길 때 이 부호를 뒤집지 않으면 확인창이 정반대로 뜬다.**
"""
import os

from . import engine, store

# `disk_state` 4분류 — M1은 화면 문구를 합쳤지만 코드는 갈라 둔다.
# 합쳐 두면 `"unknown"`이 *"게임에서 조정함"*과 *"조회 실패"* 두 뜻을 갖게 되어
# 프론트가 문구를 고를 수 없다(설계 §2-E-0).
OTHER_PROFILE = "other_profile"   # 다른 프로필과 일치 — 그 이름을 같이 싣는다
UNKNOWN = "unknown"               # 어느 프로필과도 다름 — 게임에서 조정한 것으로 보인다
MISSING = "missing"               # 설정 파일이 없다
LOOKUP_FAILED = "lookup_failed"   # 조회 자체가 실패했다(권한·손상 등)


def needs_confirm(reg, appid, profile):
    """`(need, params)` — 저장이 기존 프로필을 실제로 덮어쓰는가.

    `need`가 True일 때만 `params`에 확인창이 쓸 정보가 실린다
    (`size` · `sha1_short` · `saved_at` · `disk_state` [· `matched_profile`]).
    """
    appid = str(appid)
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        # ★ 여기서 막지 않는다 — **M1과 같은 자리에서 같은 방식으로** 실패해야 한다.
        #   저장을 진행하면 `engine.save_profile`이 같은 meta를 다시 읽고 실패하므로
        #   **결과는 「아무것도 안 쓰고 실패」**로 M1과 동치다(설계 5분기표 4행).
        #   ⚠️ 그래서 이 note의 문구는 *"확인 없이 저장을 시도합니다"*가 아니라
        #      **"프로필 정보가 손상되어 저장할 수 없습니다"**로 옮겨야 한다 — 결과와 어긋나면 오정보다.
        return False, {"note": "META_UNREADABLE"}

    if not meta:
        return False, {}                      # 빈 슬롯에 처음 저장 — 잃을 것이 없다

    try:
        state = engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError):
        state = None                          # ★ `{}`가 아니라 `None` — 아래에서 「조회 실패」와
                                              #   「파일 없음」을 갈라야 하기 때문이다

    if state is not None and state.get("sha1") and state["sha1"] == meta.get("sha1"):
        return False, {}                      # 내용이 이미 같다 — 덮어써도 달라지는 것이 없다

    params = {
        "size": meta.get("size") or 0,
        "sha1_short": (meta.get("sha1") or "")[:10],
        "saved_at": meta.get("saved_at") or "",
        "disk_state": _classify(state),
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]
    return True, params


def already_registered(reg, appid):
    """이미 등록된 appid인가 — 맞으면 화면이 쓸 `params`, 아니면 `None`. (2026-08-07 QA R2)

    ★ 왜 여기인가: `engine.add_game`은 기존 entry에 `config_path`를 **무조건 덮어쓴다**
      (`:420-426`의 `setdefault` + `entry.update`). 그래서 같은 appid로 다시 등록하면 경로가
      조용히 바뀌고, 그 다음 `apply_profile`이 **새 경로의 파일을 프로필 내용으로 덮어쓴다.**
      QA가 합성 데이터로 실피해를 재현했다(`UNRELATED_FILE_OVERWRITTEN=True`).

      막을 자리는 셋 중 하나인데 —
        엔진   → M1과 바이트 동일선(diff fence)을 깬다
        main   → *"접착층은 정책 판단 금지"*(§2-C)
        프론트 → 버튼을 숨겨도 route 계약은 열려 있다(QA가 지적한 바로 그 구멍)
      → `needs_confirm`과 같은 이유로 **여기**가 자리다.

    ⚠️ 경로 변경 자체를 지원하지 않는다. 지금 필요한 것은 *"조용히 바뀌지 않는 것"*이고,
      경로 변경 전용 확인 계약은 그것을 원하는 화면이 생길 때 만든다(백로그).
    """
    entry = (reg.get("games") or {}).get(str(appid))
    if entry is None:
        return None
    return {"appid": str(appid),
            "name": entry.get("name") or ("appid %s" % appid),
            "config_path": entry.get("config_path") or ""}


def add_game_needs_confirm(warnings):
    """수동 등록이 **저장 전에** 되물어야 하는가. (2026-08-07 QA R1)

    ★ 계약의 절반은 **묻지 않는 것**이다. 자동 탐지 후보는 구조적으로 경고가 없고, 무경고 수동
      선택도 마찬가지다 — 거기까지 되물으면 `save_profile`이 명시적으로 피한 *확인창 지옥*이
      등록 경로에 그대로 재현된다.
    """
    return bool(warnings), {"warnings": list(warnings)}


# ── 일괄 적용 미리보기 (F8 / P10) ────────────────────────────────────────────
#
# ★★ **판정 미러가 두 곳이 되는 것을 감수한 자리다.** 엔진에 dry-run 플래그를 넣는 것은
#   diff fence 위반이라 불가능하므로, 미리보기는 `engine.apply_all`의 판정을 **읽기 전용으로
#   재현**한다. 그래서 계약을 문서가 아니라 **테스트로** 못박는다
#   (`qa/test_apply_preview_equivalence.py` — 적대 합성 세계 전수).
#
# ★ 버킷은 **5개**이고 엔진 `BULK_OUTCOMES` 5종과 1:1이다(engine.py:551).
#   4버킷(refused/error를 would_apply로 셈)은 반증에서 잡힌 오산이다 —
#   "적용 예상 9개"라고 해 놓고 실제로는 3개만 되는 화면이 나온다.
#: 미리보기 버킷 ↔ 엔진 outcome: would_apply→applied · already→already ·
#: no_profile→no_profile · running_refused→refused(GAME_RUNNING) · cannot_apply→refused(기타)/error
APPLY_BUCKETS = ("would_apply", "already", "no_profile", "running_refused", "cannot_apply")


def _preview_one(reg, appid, profile, running):
    """게임 하나가 어느 버킷에 드는가. **판정 순서 = 엔진 실행 순서**다.

    ★ 순서가 계약이다(설계 §3-B 2조). `already` 판정이 G5(실행 중)보다 **먼저**이므로
      (engine.py:594-598이 `apply_profile` 진입 전에 스킵한다) **실행 중이어도 디스크==프로필이면
      `already`**다. 순서를 바꾸면 화면이 "실행 중 N개는 거부 예상"이라고 말하는데 실제로는
      조용히 already가 되어, 미리보기와 결과가 어긋난다.

    ★ 예외는 **이 함수 밖에서** 게임별로 격리된다(`apply_all_preview`) — 엔진 외곽 try와 동형이다.
    """
    meta = store.load_meta(appid, profile)
    if not meta:
        return "no_profile"
    try:
        state = engine.disk_state(reg, appid)
    except Exception:                      # noqa: BLE001 — 엔진의 같은 자리(engine.py:592-593)와 동형
        state = {}
    if state.get("sha1") and state["sha1"] == meta.get("sha1"):
        return "already"
    # ★ `config_path`가 없는 등록 항목(손상·수동 편집)은 엔진이 **error**를 낸다 —
    #   `apply_profile`이 `entry["config_path"]`에서 KeyError를 내고(engine.py:469) 그 예외가
    #   외곽 try에 잡힌다. 그 판정이 **G5보다 먼저**라(경로를 먼저 읽는다) 실행 중이어도 error다.
    #   이 줄이 없으면 미리보기는 `would_apply`라고 세고 실행은 실패한다 — "적용된다 해 놓고
    #   안 되는" 어긋남이다(2026-08-10 qa-lead 권고 4-A. QA 5라운드 R1과 같은 버그 클래스).
    if not (reg.get("games") or {}).get(str(appid), {}).get("config_path"):
        return "cannot_apply"
    if str(appid) in running:
        return "running_refused"           # G5 — 디스크≠프로필일 때만 여기 온다
    path = store.profile_file_path(appid, profile)
    if not (path and os.path.exists(path)):
        return "cannot_apply"              # PROFILE_MISSING
    if store.sha1_file(path) != meta.get("sha1"):
        return "cannot_apply"              # PROFILE_CORRUPT
    return "would_apply"


def apply_all_preview(reg, profile, running):
    """일괄 적용이 **무엇을 할 예정인가** — 5버킷 개수. **아무것도 쓰지 않는다.**

    `running`은 접착층의 `_running_appids()`가 준 집합이다(/proc 1회 스캔) — 게임마다
    `engine.running_game`을 부르면 등록 수에 정비례하는 재스캔이 된다.

    ★★ **게임별 예외 격리가 엔진과 동형이다**(설계 §3-B 1조). `store.load_meta`는 손상 JSON에서
      예외를 그대로 던지는데(store.py:235-240, json.load 무보호) 격리가 없으면 **meta 손상
      1건이 미리보기 전체를 UNEXPECTED로 만들어** `CONFIRM_REQUIRED`가 영영 안 나오고
      **일괄 적용 버튼이 전면 불능**이 된다. 엔진은 그 게임만 `error`로 강등하고 계속 가므로,
      미리보기가 전멸하면 "하나가 실패해도 나머지는 계속"이 미리보기 층에서 뒤집힌다.
      → 어떤 예외든 그 게임만 `cannot_apply`로 강등하고 **다음 게임을 계속**한다.

    ⚠️ 예측하지 **못하는** 것이 있다 — 실행 시점에만 나는 실패(G11 경로 가드·G4 크기 검사·
      `BACKUP_FAILED` 등)는 `would_apply`로 세어 놓고 실제로는 `refused`가 될 수 있다.
      그래서 화면 문구는 **「예상」**이고, 결과의 정본은 실행 후 요약·로그다. 미리보기는
      *분류*이지 실행이 아니다(설계 §3-B 후단).
    """
    counts = dict.fromkeys(APPLY_BUCKETS, 0)
    for appid in sorted(reg["games"]):
        try:
            bucket = _preview_one(reg, appid, profile, running)
        except Exception:                  # noqa: BLE001 — 엔진 외곽 try(engine.py:579-580)와 동형
            bucket = "cannot_apply"
        counts[bucket] += 1
    return counts


def _classify(state):
    if state is None:
        return LOOKUP_FAILED
    if state.get("matches"):
        return OTHER_PROFILE
    if state.get("sha1"):
        return UNKNOWN
    return MISSING
