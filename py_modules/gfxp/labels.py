"""프로필 표시명 정책.

`dock`과 `internal`은 경로·RPC·registry 식별자다. 사용자 표시명은
`settings.profile_names`에만 두며 식별자를 바꾸지 않는다. 변경값은 감사 로그에는 남는다.

표시명 상한은 `src/limits.ts`의 `PROFILE_NAME_MAX`와 수동으로 맞춘다. 현재 두 값은 20이다.
제어문자 치환·공백 접기·상한 자르기·빈 값 복귀를 각각 검증하는 테스트는 없다.

정책은 `main.py`가 아니라 이 파일에 둔다 — `confirm.py`·`remove.py`·`restore.py`와 같은
자리다. 접착층은 정책 판단을 하지 않고, 엔진은 fence다.

빈 값은 오류가 아니라 기본 이름 복귀로 처리한다. 공백만·제어문자·과길이·비문자열도 거부가
아니라 `normalize`의 대상이다 — 거부로 만들면 화면에 오류 분기가 생기고 "이름 지우기"를 할
방법도 사라진다. 다만 무예외는 이름 값에 한한 성질이다: `reg` 자체가 dict가 아니면
`stored`·`set_name`·`custom_count`가 다 `AttributeError`를 낸다. `settings`만 비-dict일
때는 `stored`는 접고 `set_name`은 터진다. 그 전제는 `store.load_registry`가 지킨다.
"""
import re

#: 프로필은 2개 고정이다. registry settings에 저장되는 키도 이 둘뿐이다.
PROFILES = ("dock", "internal")

#: registry `settings` 안의 자리. `settings`에 두는 이유: 게임별이 아니라 전역 설정이고,
#: 전체 초기화가 registry를 통째로 갈아 끼울 때 같이 초기화되는 것이 맞다(사용자에게는
#: 확인창이 그 사실을 미리 말한다 — 모르고 잃는 것만 막으면 된다).
SETTINGS_KEY = "profile_names"

#: 표시명 길이 상한(문자 수). 표시명은 QAM 일괄 적용 버튼에도 들어간다.
#: `BULK_APPLY`와 `BULK_COUNT`가 이어지므로 무제한 문자열을 받지 않는다.
#: 20은 픽셀 실측값이 아니다. 바꾸면 `src/limits.ts`의 `PROFILE_NAME_MAX`도 함께 맞춘다.
MAX_LEN = 20

#: 제어문자·개행·탭은 공백으로 바꾼 뒤 연속 공백을 하나로 접는다.
#: 지워 버리면 안 된다 — `"내장\nGPU"`가 `"내장GPU"`로 붙어 버린다(줄바꿈은 낱말을
#:   나누던 것이지 없던 것이 아니다).
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


def normalize(name):
    """사용자가 친 문자열 → 저장할 표시명. 못 쓸 값이면 빈 문자열(=기본값)을 돌려준다.

    잘라내기를 거부가 아니라 정규화로 처리하는 이유: 상한을 넘겼다고 저장이 실패하면 사용자는
    무엇이 잘못됐는지 모른 채 다시 쳐야 한다. 잘라서 저장하고 결과를 그대로 돌려주면 화면이
    실제 저장된 값을 보여준다(사용자가 본 것 = 저장된 것).
    """
    if not isinstance(name, str):
        return ""
    cleaned = _SPACES.sub(" ", _CONTROL.sub(" ", name)).strip()
    return cleaned[:MAX_LEN]


def stored(reg):
    """registry에 저장된 표시명 — 항상 두 키가 다 있는 dict. 미설정은 빈 문자열이다.

    빈 문자열이 곧 "기본 이름을 쓰라"는 뜻이다. 기본 이름 자체는 백엔드가 모른다 —
    번역(`PROFILE_DOCK`/`PROFILE_INTERNAL`)이라 언어에 따라 다르고, 그 판정은 프론트의 i18n
    한 곳에만 있어야 한다(두 곳에 두면 언젠가 갈라진다).
    """
    raw = (reg.get("settings") or {}).get(SETTINGS_KEY) or {}
    if not isinstance(raw, dict):
        raw = {}                       # 손상·수동 편집된 값은 미설정으로 접는다
    return {p: normalize(raw.get(p)) for p in PROFILES}


def set_name(reg, profile, name):
    """`reg`를 제자리에서 고친다. 저장은 호출자(접착층 route)가 한다 — 엔진 문법 그대로.

    반환은 적용 후 전체 표시명 dict다. 화면은 이 값을 그대로 그린다(프론트가 다시
    정규화하지 않는다 — 두 곳에서 다듬으면 사용자가 본 것과 저장된 것이 갈린다).
    """
    settings = reg.setdefault("settings", {})
    names = settings.get(SETTINGS_KEY)
    if not isinstance(names, dict):
        names = {}
    clean = normalize(name)
    if clean:
        names[str(profile)] = clean
    else:
        names.pop(str(profile), None)  # 빈 값 = 기본 이름으로 되돌리기
    if names:
        settings[SETTINGS_KEY] = names
    else:
        settings.pop(SETTINGS_KEY, None)   # 아무 것도 안 남으면 키 자체를 지운다(깨끗한 기본 상태)
    return stored(reg)


def custom_count(reg):
    """사용자가 직접 정한 이름의 개수. 전체 초기화 확인창이 "표시 이름도 초기화된다"를
    해당될 때만 말하기 위해 쓴다(0인 항목은 그리지 않는다는 기존 문법)."""
    return sum(1 for value in stored(reg).values() if value)
