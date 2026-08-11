"""감지 제외 목록 정책 — A9 *"삭제 = 등록 해제 + 감지 제외"*. 설계 정본 DESIGN-UX §8-A·§8-B.

### 왜 자기 파일에 사는가 — `confirm.py`·`remove.py`·`restore.py`·`labels.py`가 세운 선례 그대로
- `engine.py`/`store.py` → **diff fence 위반**. 엔진은 M1과 기록된 diff 밖으로 안 움직인다
- `main.py` → *"접착층은 정책 판단 금지"* 위반
→ **fence 밖의 새 파일**이 둘 다 피한다. 여기서는 registry의 한 칸을 읽고 쓰는 일만 한다.

### ★ `store.default_registry()`를 건드리지 않는다 — 구조가 이미 우리 편이다
`load_registry`는 **미지의 `settings` 키를 그대로 보존**하고(store.py:189-194) 이 모듈의
소비처는 전부 `.get` 폴백이다. 그래서 기본값 등록 없이도 값이 살아남는다 — fence 재계약 0.
그 대가로 **전체 초기화의 제외 소거가 공짜**다: `reset_all`은 `default_registry()`를 통째로
갈아 끼우므로(main.py:910-911) 제외 목록도 같이 사라진다. 지우는 코드가 따로 없다.

### ★ 나쁜 입력에 예외를 붙이지 않는다 — **빈 목록으로 접는다** (`labels.py`와 같은 판단)
손상·수동 편집된 값에서 거부 코드를 새로 만들면, 화면에는 "제외 목록을 못 읽었다"는 분기가
생기고 사용자는 그것을 고칠 방법이 없다. 대신 **안전한 방향으로 접는다** — 제외가 사라지면
후보가 더 보일 뿐 파괴는 없다. **이 모듈이 만드는 새 거부 코드는 0개다.**

### ★ 전 함수 멱등
`dict`라서 중복이 원천적으로 불가능하고(O(1) 조회), 없는 것을 지우는 것도 정상 종료다.
`save_registry`는 여기서 부르지 않는다 — 엔진 문법 그대로 **호출자(접착층 route)**가 부른다.
"""
import logging
import time

#: registry `settings` 안의 자리. 게임별이 아니라 전역이고, 전체 초기화에 같이 지워지는 것이
#: 맞다(§8-A) — `labels.SETTINGS_KEY`와 같은 근거로 같은 자리에 산다.
SETTINGS_KEY = "discover_excluded"

_log = logging.getLogger("gfxp.exclude")


def _stamp():
    """제외 시각 — `store.write_profile`의 `saved_at`과 **같은 형식**이다.
    접착층의 `_saved_label`이 그 형식 하나만 알면 되도록 맞춘다(형식이 둘이면 표기가 갈린다)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def excluded_map(reg):
    """제외 목록 **원본 dict**(reg에 붙어 있는 것 그대로). 손상 값이면 빈 dict.

    ⚠️ 반환값은 사본이 아니지만 **여기에 직접 쓰지 마라** — 손상 값일 때는 reg와 무관한 빈
      dict가 나오므로 쓰기가 조용히 사라진다. 쓰기는 `add`/`remove`만 한다(문은 하나).
    ★ 개수를 셀 때도 이 함수를 쓴다: `counts.excluded`는 **원본 키 수**여야 한다(§8-D D-08) —
      아래 `rows`가 격리한 불량 항목도 "전체 초기화로 지울 것"에는 포함되기 때문이다.
      격리분을 빼고 세면 "게임 0·제외 0"으로 보여 초기화 버튼이 비활성이 되고,
      그 순간 불량 항목을 지울 방법이 UI에서 사라진다(D-01).
    """
    raw = (reg.get("settings") or {}).get(SETTINGS_KEY)
    return raw if isinstance(raw, dict) else {}


def _writable(reg):
    """쓰기용 자리. 없거나 손상됐으면 **그 자리에서 빈 dict로 갈아 끼운다** —
    쓰기 경로가 "값이 이상하면 어떡하나"를 매번 다시 판단하지 않도록 구조로 없앤다."""
    settings = reg.setdefault("settings", {})
    bucket = settings.get(SETTINGS_KEY)
    if not isinstance(bucket, dict):
        bucket = {}
        settings[SETTINGS_KEY] = bucket
    return settings, bucket


def is_excluded(reg, appid):
    return str(appid) in excluded_map(reg)


def add(reg, appid, name):
    """감지 제외에 올린다. 이미 있으면 **기록을 새로 쓴다**(멱등 — 결과 상태가 하나다).

    이름을 **제외 시점에 캡처**하는 이유: 게임을 지운 뒤에는 registry에 이름이 없고,
    미설치 게임은 탐지에서도 안 나온다 — 그때 화면이 그릴 이름이 여기 말고는 없다.
    """
    appid = str(appid)
    _, bucket = _writable(reg)
    bucket[appid] = {"name": str(name or ""), "excluded_at": _stamp()}
    return bucket[appid]


def remove(reg, appid):
    """감지 제외에서 내린다. **있었으면 True**(호출자의 감사 로그 `was_excluded=`가 쓴다).

    없는 것을 내려도 정상 종료다 — 재포함 버튼과 등록 자동 해제가 같은 함수를 부르는데,
    "제외돼 있을 때만 부른다"는 조건을 두 호출부가 각자 판단하면 언젠가 갈라진다.
    """
    appid = str(appid)
    settings, bucket = _writable(reg)
    existed = bucket.pop(appid, None) is not None
    if not bucket:
        settings.pop(SETTINGS_KEY, None)      # 깨끗한 기본 상태로 되돌린다(labels와 같은 문법)
    return existed


def rows(reg):
    """화면용 목록 — **이름순**, `[{appid, name, excluded_at}]`.

    ★ 항목 하나의 타입 오류가 route 전체를 죽이지 않는다(§8-D D-08): 값이 dict가 아닌 항목은
      **격리**하고(로그 1줄) 나머지를 그린다. 필드도 마찬가지로 폴백한다 —
      이름이 없으면 `appid 123`(접착층 `_entry_payload`와 같은 문법), 시각이 없으면 빈 문자열
      (빈 값이면 화면이 그 자리를 안 그린다는 기존 문법).
    """
    out = []
    for appid, item in excluded_map(reg).items():
        if not isinstance(item, dict):
            _log.error("excluded 항목 격리 appid=%r type=%s (값이 dict가 아니다)",
                       appid, type(item).__name__)
            continue
        name = item.get("name")
        excluded_at = item.get("excluded_at")
        out.append({
            "appid": str(appid),
            "name": name if isinstance(name, str) and name else ("appid %s" % appid),
            "excluded_at": excluded_at if isinstance(excluded_at, str) else "",
        })
    # 이름이 같으면 appid로 갈린다 — 정렬이 실행마다 흔들리면 화면 행 순서가 이유 없이 바뀐다.
    out.sort(key=lambda row: (row["name"].lower(), row["appid"]))
    return out
