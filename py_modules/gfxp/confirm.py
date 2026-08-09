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


def _classify(state):
    if state is None:
        return LOOKUP_FAILED
    if state.get("matches"):
        return OTHER_PROFILE
    if state.get("sha1"):
        return UNKNOWN
    return MISSING
