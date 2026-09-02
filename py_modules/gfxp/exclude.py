"""감지 제외 목록은 registry의 전역 `settings` 칸에 둔다.

저장된 제외 값이 dict가 아니면 읽기는 빈 dict로 접고, 쓰기는 그 자리를 새 dict로 바꾼다.
`add`는 같은 appid의 이름과 제외 시각을 갱신한다. `remove`는 없는 appid도 정상 종료한다.
저장은 호출자가 맡는다.
"""
import logging
import time

#: registry `settings` 안의 자리. 게임별이 아니라 전역이고, 전체 초기화에 같이 지워지는 것이
#: 맞다 — `labels.SETTINGS_KEY`와 같은 근거로 같은 자리에 산다.
SETTINGS_KEY = "discover_excluded"

_log = logging.getLogger("gfxp.exclude")


def _stamp():
    """제외 시각 — `store.write_profile`의 `saved_at`과 같은 형식이다.
    접착층 `_saved_label`이 형식 하나만 알면 되도록 맞춘다."""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def excluded_map(reg):
    """제외 목록 원본 dict(reg에 붙어 있는 것 그대로). 손상 값이면 빈 dict.

    반환값은 사본이 아니지만 여기에 직접 쓰지 마라 — 손상 값일 때는 reg와 무관한 빈 dict가
      나오므로 쓰기가 조용히 사라진다. 쓰기는 `add`/`remove`만 한다(문은 하나).
    개수를 셀 때도 이 함수를 쓴다: `get_overview`의 `counts.excluded`는 원본 키 수여야 한다.
      `rows`가 격리한 불량 항목도 전체 초기화로 지워지는 대상이기 때문이다 — 격리분을 빼고 세면
      「게임 0·제외 0」으로 보여 초기화 버튼이 비활성이 되고, 그 순간 불량 항목을 지울 길이
      화면에서 사라진다. `qa/test_discover_exclude.py`가 그 상태를 잠근다.
    """
    raw = (reg.get("settings") or {}).get(SETTINGS_KEY)
    return raw if isinstance(raw, dict) else {}


def _writable(reg):
    """쓰기용 자리. 없거나 손상됐으면 그 자리에서 빈 dict로 갈아 끼운다 —
    쓰기 경로가 「값이 이상하면 어떡하나」를 매번 다시 판단하지 않게 한다."""
    settings = reg.setdefault("settings", {})
    bucket = settings.get(SETTINGS_KEY)
    if not isinstance(bucket, dict):
        bucket = {}
        settings[SETTINGS_KEY] = bucket
    return settings, bucket


def is_excluded(reg, appid):
    return str(appid) in excluded_map(reg)


def add(reg, appid, name):
    """감지 제외에 올린다. 이미 있으면 이름과 제외 시각을 새 기록으로 갱신한다.

    이름은 제외 시점에 캡처한다. 게임을 지운 뒤에는 registry에 이름이 없고,
    미설치 게임은 탐지에서도 나오지 않기 때문이다.
    """
    appid = str(appid)
    _, bucket = _writable(reg)
    bucket[appid] = {"name": str(name or ""), "excluded_at": _stamp()}
    return bucket[appid]


def remove(reg, appid):
    """감지 제외에서 내린다. 있었으면 True — 호출자의 감사 로그가 그 값을 싣는다.

    없는 것을 내려도 정상 종료다. 재포함(`include_game`)과 등록 자동 해제(`add_game`)가 같은
    함수를 부르는데, 「제외돼 있을 때만 부른다」는 조건을 두 호출부가 각자 판단하면 갈라진다.
    """
    appid = str(appid)
    settings, bucket = _writable(reg)
    existed = bucket.pop(appid, None) is not None
    if not bucket:
        settings.pop(SETTINGS_KEY, None)      # 깨끗한 기본 상태로 되돌린다(labels와 같은 문법)
    return existed


def rows(reg):
    """화면용 목록 — 이름순, `[{appid, name, excluded_at}]`.

    항목 하나의 타입 오류가 route 전체를 죽이지 않는다: 값이 dict가 아닌 항목은 로그 한 줄을
      남기고 격리하며 나머지를 그린다(`qa/test_discover_exclude.py`가 잠근다). 필드도 폴백한다 —
      이름이 없으면 `appid 123`(`discover.discover`·`confirm.already_registered`와 같은 문법),
      시각이 없으면 빈 문자열(빈 값이면 화면이 그 자리를 안 그린다).
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
