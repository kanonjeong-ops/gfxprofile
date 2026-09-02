"""에러 코드 상수의 정의 모음.

`codes` 상수 · 소스의 `code=` 사용 · en.json 키 · ko.json 키 —
이 네 집합 사이에서 기계가 강제하는 관계는 다음 두 가지뿐이다:
    `Refused`/`RegistryError`의 `code=codes.X`가 정의돼 있음  (qa/test_codes.py)
    en.json 키 == ko.json 키                                (qa/test_i18n_keys.py)
미사용 상수는 실패가 아니며, codes.py와 번역 키를 맞대는 검사도 없다.

코드는 사람이 읽는 메시지와 분리된 식별자다. 백엔드는 의미 코드를 보내고,
프론트는 그 코드로 현재 언어의 문장을 고른다.
"""

# ── 경로·파일 가드 (engine.check_path / check_sanity / add_game) ──────────────
PATH_IS_SYMLINK = "PATH_IS_SYMLINK"
PATH_OUTSIDE_PREFIX = "PATH_OUTSIDE_PREFIX"
PATH_OUTSIDE_HOME = "PATH_OUTSIDE_HOME"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
NOT_REGULAR_FILE = "NOT_REGULAR_FILE"
FILE_EMPTY = "FILE_EMPTY"
SIZE_OUT_OF_RANGE = "SIZE_OUT_OF_RANGE"
LINE_COUNT_OUT_OF_RANGE = "LINE_COUNT_OUT_OF_RANGE"

# ── 등록·프로필 ──────────────────────────────────────────────────────────────
GAME_NOT_REGISTERED = "GAME_NOT_REGISTERED"
CONFIG_MISSING = "CONFIG_MISSING"
PROFILE_MISSING = "PROFILE_MISSING"
PROFILE_CORRUPT = "PROFILE_CORRUPT"

# ── 적용·백업 ───────────────────────────────────────────────────────────────
GAME_RUNNING = "GAME_RUNNING"
BACKUP_FAILED = "BACKUP_FAILED"
BACKUP_FILE_MISSING = "BACKUP_FILE_MISSING"

# ── 레지스트리 (store.RegistryError) ─────────────────────────────────────────
REGISTRY_UNREADABLE = "REGISTRY_UNREADABLE"
REGISTRY_MALFORMED = "REGISTRY_MALFORMED"
# 이 데이터를 더 새 버전의 플러그인이 만들었다. 미지 키 자체는 `load_registry`의 `setdefault`와
# `save_registry`의 전체 직렬화 사이에서 보존된다 — 「모르는 필드가 통째로 사라진다」가 근거가
# 아니다. 낡은 코드가 모르는 스키마의 의미를 지킬 수 없으므로, 읽기는 그대로 두고 바꾸는
# 동작만 막는다 (접착층 `main.py`의 `_guard_not_newer`).
REGISTRY_NEWER = "REGISTRY_NEWER"
# 등록된 항목 하나의 기록이 손상됐다(비-dict 항목 · `config_path`가 문자열이 아님).
# 그 항목 위에서 쓰기를 하면 무엇을 덮는지 모르므로 이름 있는 거부로 멈춘다 — 항목 하나가
# 화면·목록 전체를 죽이지 않게 조회·삭제 계열은 통과시킨다(§8-D 정규화 규칙 · §14-H).
REGISTRY_ENTRY_CORRUPT = "REGISTRY_ENTRY_CORRUPT"

# ── 등록 후보·백업 경로 가드 ──────────────────────────────────────────────────────
SAV_REFUSED = "SAV_REFUSED"                          # .sav 및 savegames 폴더
STALE_COPY_REFUSED = "STALE_COPY_REFUSED"            # *.bak / *.bak.* / *backup 폴더의 옛 사본
ENGINE_BOILERPLATE_REFUSED = "ENGINE_BOILERPLATE_REFUSED"
# 프로필 슬롯이 이미 쓰는 이름(`store.is_byproduct`). 이 이름으로 등록하면 저장은 성공을
# 보고하면서 슬롯이 손상되고, 삭제는 그 파일을 부산물로 걸러 대피 없이 지운다.
RESERVED_NAME_REFUSED = "RESERVED_NAME_REFUSED"
BACKUP_OUT_OF_ROOT = "BACKUP_OUT_OF_ROOT"            # 그 게임의 백업 폴더 밖

# ── 삭제 (remove.py) ──────────────────────────────────────────────────────
# 삭제 경로의 실패. 사용자가 등록 정보와 프로필 데이터의 삭제가 시작됐는지 구별할 수 있어야 한다.
# `remove._delete_failed`가 `appid`·`stage`·`profile_delete_started`를 싣고,
# `route`가 실패 봉투에 `message`를 더한다. 화면 분기는 `profile_delete_started`만 사용하며
# `stage`는 진단용이다. 계약 원문은 `src/rpc.ts`의 `deleteGame`이다.
# 대피 실패는 `BACKUP_FAILED`이며, 그때 등록 정보와 프로필 데이터는 지우지 않는다.
DELETE_FAILED = "DELETE_FAILED"

# ── RPC 경계·응답 코드 ────────────────────────────────────────────────────────
BACKUP_ID_INVALID = "BACKUP_ID_INVALID"
BAD_IDENTIFIER = "BAD_IDENTIFIER"        # appid/profile/backup_id가 경로 조각으로 부적격
PROFILE_META_CORRUPT = "PROFILE_META_CORRUPT"
# `save_profile`에서 `OSError`가 난 경우다. `ValueError`로 분류하는 기록 손상과 구분해,
# 화면이 저장 공간과 파일 권한을 확인하도록 안내한다.
PROFILE_WRITE_FAILED = "PROFILE_WRITE_FAILED"
CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
# 이미 등록된 appid를 다시 등록하려 했다.
# 엔진 `add_game`은 `entry.update(config_path=...)`로 기존 경로를 조용히 갈아치우고,
# 그 다음 적용이 엉뚱한 파일을 프로필 내용으로 덮어쓴다.
# 경로 변경 기능은 아직 없다 — 거부가 기본이다.
ALREADY_REGISTERED = "ALREADY_REGISTERED"
UNEXPECTED = "UNEXPECTED"

# ── 경고 코드 (거부 사유가 아니다) ──────────────────────────────────────────────────
WARN_OUTSIDE_SCAN_ROOTS = "WARN_OUTSIDE_SCAN_ROOTS"
WARN_NOT_DISCOVER_CANDIDATE = "WARN_NOT_DISCOVER_CANDIDATE"
# 실행 중인 게임을 저장했다 — 저장은 됐고, 그 값이 게임 종료 시 덮일 수 있다는 사실만 알린다.
WARN_SAVE_WHILE_RUNNING = "WARN_SAVE_WHILE_RUNNING"

#: 실패가 아니라 정상 흐름 신호인 코드. 토스트·로그에서 에러로 취급하지 않는다.
FLOW_CODES = frozenset({CONFIRM_REQUIRED})


def all_codes():
    """이 모듈의 공개 대문자 문자열 상수 집합.

    `qa/test_codes.py`는 `Refused`·`RegistryError`의 `code=codes.X`가
    이 집합에 정의돼 있는지 검사한다. `FLOW_CODES` 같은 집합 값은 포함하지 않는다.
    """
    return frozenset(
        v for k, v in globals().items()
        if k.isupper() and isinstance(v, str) and not k.startswith("_")
    )
