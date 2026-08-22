"""에러 코드의 **단일 소스**.

왜 한 파일인가: 코드가 여러 곳에 흩어지면 번역 파일(en/ko)과 어긋나도 아무도 모른다.
그래서 검증을 **개수가 아니라 집합 항등**으로 한다 —
    codes.py의 상수 집합 == 소스에서 실제로 쓰인 code= 집합 == en.json 키 == ko.json 키
개수 기준("18개")은 코드가 하나 늘 때마다 깨져서 유지보수 부담만 남는다(설계 E2).

코드는 **사람이 읽는 메시지와 분리된 식별자**다. 메시지는 엔진이 한국어로 들고 있고(M1 그대로),
프론트는 code로 번역문을 고른다. 메시지 문자열을 파싱해 분류하지 않는다.
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

# ── 적용·백업 ────────────────────────────────────────────────────────────────
GAME_RUNNING = "GAME_RUNNING"
BACKUP_FAILED = "BACKUP_FAILED"
BACKUP_FILE_MISSING = "BACKUP_FILE_MISSING"

# ── 레지스트리 (store.RegistryError) ─────────────────────────────────────────
REGISTRY_UNREADABLE = "REGISTRY_UNREADABLE"
REGISTRY_MALFORMED = "REGISTRY_MALFORMED"
# 이 데이터를 **더 새 버전의 플러그인이 만들었다.** 낡은 코드가 모르는 스키마 위에 쓰면 조용히
# 뭉개므로, 읽기는 그대로 두고 **바꾸는 동작만** 막는다 (접착층 `main.py`의 `_registry_newer`).
REGISTRY_NEWER = "REGISTRY_NEWER"

# ── 신설 가드 G14/G15 (v2에서 추가 — M1에는 없다) ────────────────────────────
SAV_REFUSED = "SAV_REFUSED"                          # .sav 및 savegames 폴더
STALE_COPY_REFUSED = "STALE_COPY_REFUSED"            # *.bak / *backup 폴더의 옛 사본
ENGINE_BOILERPLATE_REFUSED = "ENGINE_BOILERPLATE_REFUSED"
# 프로필 슬롯이 이미 쓰는 이름(`store.is_byproduct`). 이 이름으로 등록하면 저장은 성공을
# 보고하면서 슬롯이 손상되고, 삭제는 그 파일을 부산물로 걸러 대피 없이 지운다(설계 §14-G ⓒ).
RESERVED_NAME_REFUSED = "RESERVED_NAME_REFUSED"
BACKUP_OUT_OF_ROOT = "BACKUP_OUT_OF_ROOT"            # G15 — 그 게임의 백업 폴더 밖

# ── 삭제 (remove.py — M2에서 추가) ───────────────────────────────────────────
# 삭제 도중 실패. **부분 삭제 상태를 남길 수 있는 유일한 실패 경로**라서 UNEXPECTED로
# 뭉개면 안 된다 — 사용자가 "지워진 것인가"를 알 수 없다(설계 DESIGN-DELETE §3-C).
# `params`에 appid와 중단 지점(stage)이 실려 화면·로그가 어디서 멈췄는지 가린다.
# 대피(백업) 실패는 여기가 아니라 기존 `BACKUP_FAILED`다 — 그때는 아무것도 지우지 않는다.
DELETE_FAILED = "DELETE_FAILED"

# ── 접착층(main.py)에서만 나는 것 — 엔진은 이 코드를 쓰지 않는다 ─────────────
BACKUP_ID_INVALID = "BACKUP_ID_INVALID"
BAD_IDENTIFIER = "BAD_IDENTIFIER"        # appid/profile/backup_id가 경로 조각으로 부적격
PROFILE_META_CORRUPT = "PROFILE_META_CORRUPT"
# 프로필을 저장하다 **파일 입출력 자체가 실패했다** — 저장 공간 부족(`ENOSPC`)·권한·읽기 전용.
# ★ 위 `PROFILE_META_CORRUPT`를 **하나에서 둘로 가른 것**이지 새 사건을 만든 것이 아니다(§14-E′
#   16판): 그 코드가 *"기록이 깨졌다"*와 *"쓰지 못했다"* 두 사건을 함께 가리켰고, **둘 중 하나만
#   맞는 복구 안내**를 했다. 기록 손상의 안내는 「다시 저장」인데 기기 상태 문제는 공간을 비우거나
#   권한을 고쳐야 한다 — 뭉개면 사용자가 엉뚱한 복구를 시도한다.
PROFILE_WRITE_FAILED = "PROFILE_WRITE_FAILED"
CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
# 이미 등록된 appid를 다시 등록하려 했다 (2026-08-07 QA R2).
# 엔진 `add_game`은 `entry.update(config_path=...)`로 기존 경로를 **조용히 갈아치우고**,
# 그 다음 적용이 엉뚱한 파일을 프로필 내용으로 덮어쓴다(QA가 실피해를 재현했다).
# 경로 변경 기능은 아직 없다 — **거부가 기본**이다.
ALREADY_REGISTERED = "ALREADY_REGISTERED"
UNEXPECTED = "UNEXPECTED"

# ── 경고 (거부가 아니다 — 등록은 되고 화면에 표시만 된다. 설계 D1′) ──────────
WARN_OUTSIDE_SCAN_ROOTS = "WARN_OUTSIDE_SCAN_ROOTS"
WARN_NOT_DISCOVER_CANDIDATE = "WARN_NOT_DISCOVER_CANDIDATE"
# 실행 중인 게임을 저장했다 — 저장은 **됐고**, 그 값이 게임 종료 시 덮일 수 있다는 사실만 알린다.
# ★ 이 상수가 있는 이유(2026-08-15 R14 #10): 엔진이 **한국어 문장**을 봉투에 실어 보내
#   영어 화면에 그대로 붙었다. 백엔드는 의미 코드만 주고 문장은 화면이 고른다.
WARN_SAVE_WHILE_RUNNING = "WARN_SAVE_WHILE_RUNNING"

#: 실패가 아니라 **정상 흐름 신호**인 코드. 토스트·로그에서 에러로 취급하지 않는다.
FLOW_CODES = frozenset({CONFIRM_REQUIRED})


def all_codes():
    """이 모듈이 정의한 코드 전체. 4집합 항등 검사가 이걸 기준으로 삼는다."""
    return frozenset(
        v for k, v in globals().items()
        if k.isupper() and isinstance(v, str) and not k.startswith("_")
    )
