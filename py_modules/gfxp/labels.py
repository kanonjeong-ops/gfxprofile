"""프로필 **표시명** 정책 — F11 ①. 사용자가 정한 이름의 정규화·상한·기본값 복귀.

### ★★ 표시 계층 하나만 바꾼다 — 식별자는 불변이다
`dock`/`internal`은 **경로 조각이자 RPC 인자이자 registry 키**다(`profiles/<appid>/dock/`,
`_VALIDATORS["profile"]`, `entry["last_applied"]`, 백업 파일명의 `profile_dock` tag …).
여기서 다루는 것은 **화면에 보이는 글자뿐**이고, 그 글자는 어떤 경로·키에도 쓰이지 않는다.
(⚠️ 정정 2026-08-10 QA R5: *"로그에도 안 쓰인다"*고 적었으나 **감사 로그에는 값이 남는다** —
 `main.set_profile_name`이 `name=%r`로 무엇을 바꿨는지 기록한다. 그건 **정상**이다:
 되돌리기 어려운 변경의 흔적을 남기는 것이 이 프로젝트의 규칙이고, 그 값은 로그의 **내용**이지
 경로·키가 아니다. 주석이 실물보다 강하게 말하고 있었다.)
이름을 바꿔도 저장된 프로필은 그대로 그 자리에 있어야 한다 — 그것이 이 기능의 안전 단언이다.
⚠️ **그 단언을 잠그던 검사(`qa/test_profile_names.py`)는 삭제됐다**(2026-08-15 UI 검사 계열 정리 —
  사용자 지정). 지금 이 단언을 지키는 것은 **구조뿐이다**: 이 파일은 `settings`의 문자열 하나만
  쓰고 경로·키를 만드는 코드에 손이 닿지 않는다. 검사가 아니라 그 구조를 깨지 않는 것이 방어선이고,
  화면 상한 사본(`src/limits.ts`의 `PROFILE_NAME_MAX`)도 이제 **손으로** 맞춰야 한다.

### 왜 자기 파일에 사는가
`confirm.py`·`remove.py`·`restore.py`가 세운 선례 그대로 **fence 밖 정책 파일**이다.
`main.py`에 두면 *"접착층은 정책 판단 금지"* 위반이고, 엔진은 fence다.

### ★ 나쁜 입력에 예외를 붙이지 않는다 — **기본값으로 접는다**
빈 문자열·공백만·제어문자·과길이는 거부(예외)가 아니라 **정규화**의 대상이다. 거부로 만들면
화면에 오류 처리가 생기고, 사용자가 "이름 지우기"(=기본값으로 되돌리기)를 할 방법도 사라진다.
→ 정규화 결과가 빈 문자열이면 **설정을 지운다** = 기본 이름으로 돌아간다.
"""
import re

#: 프로필은 2개 고정이다(M2-6). registry settings에 저장되는 키도 이 둘뿐이다.
PROFILES = ("dock", "internal")

#: registry `settings` 안의 자리. **`settings`에 두는 이유**: 게임별이 아니라 전역 설정이고,
#: 전체 초기화가 registry를 통째로 갈아 끼울 때 **같이 초기화되는 것이 맞다**(사용자에게는
#: 확인창이 그 사실을 미리 말한다 — 모르고 잃는 것만 막으면 된다).
SETTINGS_KEY = "profile_names"

#: 표시명 길이 상한(문자 수). 근거: 가장 좁은 표면인 QAM 패널(496px)의 일괄 버튼 라벨이
#: `전부 {이름}(으)로 (N개)` 꼴이고, 기본 이름 `eGPU 독`(7자)에서 그 줄이 한 줄에 들어간다.
#: 20자면 기본값의 3배 가까이 허용하면서도 그 버튼이 두 줄을 넘지 않는다 —
#: **길이를 막지 않으면 화면이 깨지고, 깨진 화면은 되돌릴 UI조차 가린다.**
#: (픽셀 실측이 아니라 현행 최장 라벨 대비 여유로 잡은 값이다. 실기에서 좁으면 이 숫자만 고친다.)
MAX_LEN = 20

#: 제어문자·개행·탭은 **공백으로 바꾼 뒤** 연속 공백을 하나로 접는다.
#: ⚠️ 지워 버리면 안 된다 — `"내장\nGPU"`가 `"내장GPU"`로 **붙어 버린다**(줄바꿈은 단어를
#:   나누던 것이지 없던 것이 아니다). 테스트가 이 경우를 잡았다.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


def normalize(name):
    """사용자가 친 문자열 → **저장할 표시명**. 못 쓸 값이면 빈 문자열(=기본값)을 돌려준다.

    잘라내기를 **거부가 아니라 정규화**로 처리하는 이유: 20자를 넘겼다고 저장이 실패하면
    사용자는 무엇이 잘못됐는지 모른 채 다시 쳐야 한다. 잘라서 저장하고 **결과를 그대로
    돌려주면** 화면이 실제 저장된 값을 보여준다(사용자가 본 것 = 저장된 것).
    """
    if not isinstance(name, str):
        return ""
    cleaned = _SPACES.sub(" ", _CONTROL.sub(" ", name)).strip()
    return cleaned[:MAX_LEN]


def stored(reg):
    """registry에 저장된 표시명 — 항상 두 키가 다 있는 dict. 미설정은 빈 문자열이다.

    빈 문자열이 곧 *"기본 이름을 쓰라"*는 뜻이다. **기본 이름 자체는 백엔드가 모른다** —
    번역(`PROFILE_DOCK`/`PROFILE_INTERNAL`)이라 언어에 따라 다르고, 그 판정은 프론트의 i18n
    한 곳에만 있어야 한다(두 곳에 두면 언젠가 갈라진다).
    """
    raw = (reg.get("settings") or {}).get(SETTINGS_KEY) or {}
    if not isinstance(raw, dict):
        raw = {}                       # 손상·수동 편집된 값은 미설정으로 접는다
    return {p: normalize(raw.get(p)) for p in PROFILES}


def set_name(reg, profile, name):
    """`reg`를 제자리에서 고친다. 저장은 호출자(접착층 route)가 한다 — 엔진 문법 그대로.

    반환은 **적용 후 전체 표시명 dict**다. 화면은 이 값을 그대로 그린다(프론트가 다시
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
    """사용자가 직접 정한 이름의 개수. 전체 초기화 확인창이 *"표시 이름도 초기화된다"*를
    **해당될 때만** 말하기 위해 쓴다(0인 항목은 그리지 않는다는 기존 문법)."""
    return sum(1 for value in stored(reg).values() if value)
