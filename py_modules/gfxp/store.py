"""저장소 계층 — 레지스트리, 프로필 파일, 백업.

여기서는 정책 판단을 하지 않는다. 정책(가드)은 engine.py에 있다.
표준 라이브러리만 사용한다 (이 기기에 pip이 없음).
"""

import hashlib
import json
import logging
import os
import pwd
import re
import tempfile
import time

from . import codes

#: 이 층의 로거. 판단은 안 하지만 **비치명으로 접은 실패**는 남겨야 한다
#: (`atomic_write`의 디렉터리 fsync — 아래 D4). 이름 문법은 `gfxp.<모듈>`로 통일돼 있다.
_log = logging.getLogger("gfxp.store")

BACKUP_KEEP = 10
REGISTRY_VERSION = 1
DESKTOP_UID = 1000          # 핸드헬드의 주 사용자(SteamOS에서는 deck)

#: 프로필 슬롯 안에서 **우리가 만드는 부산물**의 이름. 그 밖의 파일은 전부 **본체**다.
#:   · `meta.json`         — 그 슬롯의 기록
#:   · `.applied`          — 옛 버전이 남긴 엔진 마커(지금은 아무도 쓰지 않지만 실물에 남아 있다)
#:   · `.gfxprofile-tmp-*` — `atomic_write`가 쓰다 죽었을 때의 잔재
META_NAME = "meta.json"
APPLIED_NAME = ".applied"
TMP_PREFIX = ".gfxprofile-tmp-"


def is_byproduct(name):
    """그 이름이 **부산물**인가 = 「본체가 아닌가」. 같은 질문을 하는 곳은 전부 여기를 지난다.

    ★ 왜 목록이 아니라 술어 하나인가(설계 §14-G ⓑ·ⓒ): 이 질문을 하는 자리가 넷인데
      (대피 목록 · 대피 전 링크 게이트 · 본체 실측 · 등록 가드 G14) 전에는 **각자 다른 목록**을
      들고 있었다. 거르는 집합과 등록 가능한 집합이 어긋나면 **그 교집합이 곧 결함이다** —
      대피에서는 부산물로 걸러지고 등록은 되는 이름이 있으면, 사용자는 성공 통지를 받고
      프로필 한 벌을 잃는다. 목록을 두 벌 적으면 언젠가 한쪽만 늘어난다.
    ⚠️ **점으로 시작하는 이름을 막는 것이 아니다.** 리눅스 게임의 `.gamerc` 같은 본체 이름은
      여기 안 걸린다 — 걸리는 것은 *"우리가 그 자리에 이미 쓰는 이름인가"*뿐이다.
    """
    return name in (META_NAME, APPLIED_NAME) or name.startswith(TMP_PREFIX)


def user_home():
    """**실제 사용자**의 홈. `os.path.expanduser("~")`를 직접 쓰지 말 것.

    ⚠️ M1의 원래 주석은 *"Decky 백엔드는 root로 돈다"*고 적었는데 **틀렸다.**
    Decky는 root가 opt-in이고(`plugin.json`의 `flags`), 우리 flags는 비어 있어 `deck`으로 돌아간다.

    그럼에도 이 사슬이 필요한 이유는 root가 아니라 **사용자명이 `deck`이 아닌 배포판**(Bazzite 등)
    때문이다. 그래서 loader가 준 `DECKY_USER_HOME`을 가장 먼저 본다 — 그게 있으면 추측이 필요 없다.
    UID 1000은 아무 단서도 없을 때의 마지막 수단이다.
    """
    explicit = os.environ.get("GFXPROFILE_HOME") or os.environ.get("DECKY_USER_HOME")
    if explicit:
        return explicit
    if os.geteuid() != 0:
        return os.path.expanduser("~")
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            return pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            pass
    try:
        return pwd.getpwuid(DESKTOP_UID).pw_dir
    except KeyError:
        return os.path.expanduser("~")


def home_path(*parts):
    return os.path.join(user_home(), *parts)


def data_dir():
    """데이터 루트. 테스트가 실제 데이터를 건드리지 않도록 환경변수로 갈아끼울 수 있다."""
    return os.environ.get("GFXPROFILE_DATA_DIR") or home_path(".local", "share", "gfxprofile")


def registry_path():
    return os.path.join(data_dir(), "registry.json")


def profiles_root(appid):
    return os.path.join(data_dir(), "profiles", str(appid))


def profile_dir(appid, profile):
    return os.path.join(profiles_root(appid), profile)


def backups_dir(appid):
    return os.path.join(data_dir(), "backups", str(appid))


# ---------------------------------------------------------------- 파일 유틸

def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()


def sha1_file(path):
    try:
        with open(path, "rb") as fh:
            return sha1_bytes(fh.read())
    except OSError:
        return None


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def looks_binary(data):
    """널 바이트가 있으면 바이너리로 본다. 줄 단위 학습 대상에서 제외하는 데만 쓴다."""
    return b"\x00" in data[:8192]


def count_lines(data):
    if looks_binary(data):
        return None
    return data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)


def atomic_write(path, data, mode=None, owner=None):
    """같은 디렉터리 tmp -> fsync -> os.replace. 도중에 죽어도 반쪽 파일이 남지 않는다 (G9).

    디렉터리도 fsync한다 — rename을 메타데이터까지 내리려는 것이다. ⚠️ **다만 그 fsync의 실패는
    치명이 아니다**(사용자 결정 D4, 2026-08-23): 새 이름이 제자리에 있으면 로그만 남기고 넘어간다.
    `os.replace`는 위 `try` 안이고 이 fsync는 **밖**이라, 예전에는 **본체를 덮은 뒤에** 예외가 났다 —
    폴더를 열거하지 못하는 슬롯에 저장하면 화면은 *"프로필 정보가 손상되어 저장할 수 없습니다"*라
    말하는데 본체는 이미 덮였고 기록만 옛 내용을 가리켜 **그 프로필은 적용도 안 됐다**(실측:
    저장 `PROFILE_META_CORRUPT` → 적용 `PROFILE_CORRUPT`). 계약을 *"덮어쓰기 전에 반드시 대피한다"*에서
    **"대피는 할 수 있을 때 한다"**로 낮춘 것이 그 처분이다.
    ⚠️ **잃는 것의 범위를 알고 하는 것이다**: 이 함수는 공용이고 호출부가 **일곱**이다
    (등록 정보 2 · 프로필 본체·기록 2 · 백업 1 · 적용 1 · 복원 1). 즉 앱이 파일을 쓰는 **모든**
    자리의 내구성이 같이 낮아진다. 다만 **잃는 것은 「이름의 지속」이지 내용의 온전성이 아니다** —
    파일 내용 자체는 위에서 이미 fsync하므로 깨진 파일이 남지는 않는다.
    ★ **`durable=` 같은 인자로 범위를 좁히지 않는다**(D4) — 접착층이 끌 수 있는 가드가 되기 때문이다.

    `owner=(uid, gid)`를 주면 쓰기 후 소유자를 되돌린다.
    ⚠️ M1 주석은 이것을 *"Decky 백엔드가 root로 돌기 때문"*이라 적었는데 **틀린 전제였다**
    (root는 opt-in이고 우리 `flags`는 비어 있다). 그래도 남겨 두는 이유는, 언젠가 root로 도는
    경로가 생기면 게임 설정 파일이 root 소유가 되어 **게임(deck)이 종료 시 다시 쓰지 못하기**
    때문이다. 지금은 무해한 무동작이다.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=TMP_PREFIX)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        if owner is not None:
            try:
                os.chown(tmp, owner[0], owner[1])
            except (OSError, PermissionError):
                pass            # root가 아니면 원래 소유자 그대로다 — 실패해도 무해
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        # ★ **새 이름이 제자리에 있을 때만** 접는다(D4). 없으면 쓰기가 성립하지 않은 것이므로
        #   종전대로 올린다 — 안 쓴 것을 썼다고 말하지 않는다.
        #   (열거가 막힌 폴더에서도 `exists`는 답한다: 실측상 `0300`은 `listdir`만 막히고
        #    이름으로 여는 것은 된다.)
        if not os.path.exists(path):
            raise
        # 좁게 잡는다 — `OSError`뿐이다. 넓게 잡으면 이 자리가 다른 실패까지 삼킨다.
        _log.warning("atomic_write: 디렉터리 fsync 실패(비치명) path=%s dir=%s: %s: %s",
                     path, directory, type(exc).__name__, exc)


# ---------------------------------------------------------------- 레지스트리

def default_registry():
    return {
        "version": REGISTRY_VERSION,
        # last_appid: 마지막으로 보고 있던 게임. 다음 실행에서 그 게임부터 보여준다 —
        # Game Mode에서는 키 입력 한 번이 비싸고(온스크린 키보드가 안 뜨고 패드로 조작한다),
        # 게임이 N개면 매 실행마다 평균 N/2회를 ◀▶로 헛되이 눌러야 했다.
        "settings": {"auto_apply": False, "mode_override": None, "last_appid": None},
        # 부팅 시 확정되는 VULKAN_ADAPTER 값 -> 모드. 독 값은 첫 독 세션에서 추가된다.
        "gpu_map": {},
        "games": {},
    }


class RegistryError(Exception):
    """레지스트리를 읽을 수 없음. 사용자에게 그대로 보여줄 안내를 담는다.

    v2 추가: `code`(codes.py 상수)와 `params`. engine.Refused와 같은 형태다 —
    접착층이 두 예외를 같은 방식으로 봉투에 실을 수 있어야 분기가 늘지 않는다.
    """

    def __init__(self, message, code=None, **params):
        super().__init__(message)
        self.code = code
        self.params = params


def load_registry():
    path = registry_path()
    if not os.path.exists(path):
        return default_registry()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            reg = json.load(fh)
    except (ValueError, UnicodeDecodeError) as exc:
        # 손상된 레지스트리로 계속 진행하지 않는다 (fail-closed). 자동 삭제도 하지 않는다.
        backup = path + ".bak"
        hint = ("  복구: mv %s %s" % (backup, path)) if os.path.exists(backup) else \
               ("  초기화: rm %s  (등록 정보만 사라지고 프로필·백업은 남습니다)" % path)
        raise RegistryError(
            "거부: 레지스트리가 손상되어 읽을 수 없습니다.\n"
            "  파일: %s\n  원인: %s\n%s" % (path, exc, hint),
            code=codes.REGISTRY_UNREADABLE)
    if not isinstance(reg, dict):
        raise RegistryError("거부: 레지스트리 형식이 올바르지 않습니다 — %s" % path, code=codes.REGISTRY_MALFORMED)
    base = default_registry()
    for key, value in base.items():
        reg.setdefault(key, value)
    for key, value in base["settings"].items():
        reg["settings"].setdefault(key, value)
    return reg


def save_registry(reg):
    """직전 레지스트리를 .bak으로 남기고 저장한다.

    .bak이 있어야 손상 시 안내가 실제 복구 경로가 된다 (없으면 안내가 거짓말이 된다).
    """
    path = registry_path()
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                previous = fh.read()
            json.loads(previous.decode("utf-8"))     # 멀쩡한 것만 .bak으로 승격
            atomic_write(path + ".bak", previous)
        except (OSError, ValueError, UnicodeDecodeError):
            pass                                     # 이미 깨진 것을 .bak으로 덮지 않는다
    data = json.dumps(reg, indent=2, ensure_ascii=False).encode("utf-8")
    atomic_write(path, data)


def game(reg, appid):
    return reg["games"].get(str(appid))


# ---------------------------------------------------------------- 프로필

def list_profiles(appid):
    root = profiles_root(appid)
    if not os.path.isdir(root):
        return []
    return sorted(
        name for name in os.listdir(root)
        if os.path.isdir(os.path.join(root, name))
    )


def profile_meta_path(appid, profile):
    return os.path.join(profile_dir(appid, profile), META_NAME)


def load_meta(appid, profile):
    path = profile_meta_path(appid, profile)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def profile_file_path(appid, profile):
    """프로필이 담고 있는 설정 파일의 경로. 원본 파일명을 그대로 유지한다."""
    meta = load_meta(appid, profile)
    if not meta:
        return None
    return os.path.join(profile_dir(appid, profile), meta["filename"])


def write_profile(appid, profile, filename, data, src):
    directory = profile_dir(appid, profile)
    os.makedirs(directory, exist_ok=True)
    atomic_write(os.path.join(directory, filename), data)
    meta = {
        "filename": filename,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sha1": sha1_bytes(data),
        "size": len(data),
        "lines": count_lines(data),
        "src": src,
    }
    atomic_write(
        profile_meta_path(appid, profile),
        json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"),
    )
    return meta


def slot_holds(appid, profile, sha1, filename=None):
    """그 슬롯이 **실제로** 그 내용을 들고 있는가 — 기록(meta)이 아니라 **본체 실측**까지 본다.

    ★★ **판정의 문은 여기 하나다**(2026-08-15 R14 #4·#5). 예전에는 세 소비자가 각자 물었다:
      · `save_profile`의 무쓰기 분기 — meta sha ∧ 파일명 ∧ 본체 sha (세 가지를 다 봤다)
      · `disk_state`의 `matches`     — **meta sha만** 봤다
      · `restore.needs_confirm`의 `already` — **meta sha만** 봤다
      뒤의 둘이 "이 내용은 저 슬롯에 보존돼 있다"는 **거짓 전제**를 만들 수 있었다(meta는 B라는데
      본체가 없거나 C인 저장소 손상). 그 전제 위에서 적용은 **대피(백업)를 생략하고** 게임 설정
      파일을 덮었고, 복원은 *"이미 같다"*며 **손상된 슬롯을 못 고쳤다.**
      → 셋이 같은 술어를 부른다. 모르면 **거짓**을 돌려준다(안전한 쪽 = 고지·대피·쓰기 경로).

    `filename`을 주면 **그 이름으로 남아 있는지**까지 본다(**4인자 소비자 둘**이 쓴다 —
    저장의 무쓰기 판정과 그 확인창 판정(`confirm.needs_confirm`, QA R1 D-1로 합류) —
    이름이 달라지면 슬롯에 남는 파일이 실제로 바뀌므로 "달라지는 것이 없다"가 거짓이 된다).
    """
    if not sha1 or not isinstance(sha1, str):
        return False
    try:
        meta = load_meta(appid, profile)
    except (OSError, ValueError):
        return False                          # 기록을 못 읽으면 "들고 있다"고 말할 수 없다
    if not isinstance(meta, dict) or meta.get("sha1") != sha1:
        return False
    if filename is not None and meta.get("filename") != filename:
        return False
    name = meta.get("filename")
    if not isinstance(name, str) or not name:
        return False                          # 본체를 가리킬 수 없다
    body = os.path.join(profile_dir(appid, profile), name)
    return os.path.exists(body) and sha1_file(body) == sha1


def evacuable_names(appid, profile):
    """그 슬롯에서 **대피 대상이 되는 본체 파일 이름들**(이름순). 조회 전용이다.

    ★ 세는 쪽과 지우는 쪽이 **같은 함수**를 돈다(R14 #1): 하나는 세고 하나는 지우는데 기준이
      갈리면 확인창이 약속한 축출 수와 실제가 어긋난다. 그래서 규칙을 여기 한 곳에 둔다 —
      부산물(`is_byproduct`)·**링크**·비일반 파일 제외, 그 밖은 전부 본체다.
    ⚠️ **이 목록의 길이가 곧 「링에 쌓일 백업 수」는 아니다**(설계 §14-G ⓔ, 2026-08-22):
      같은 태그에 같은 내용이 이미 있으면 `make_backup`이 아무것도 쓰지 않는다. 대피 **대상**은
      여전히 이 목록 전부이고(그래서 지우는 쪽은 그대로 이 함수를 돈다), 그중 **몇 건이 실제로
      파일이 되는가**는 `plan_backups`가 가른다 — 축출 예고는 그쪽을 세야 한다.
      ★ 단 **그 「이미 있는 사본」이 이번 동작에서 어차피 축출될 자리이면** `plan_backups`가
        쓰기를 허가한다(D1) — 그때는 중복이어도 새로 담긴다. 대피 대상 목록은 어느 쪽이든 그대로다.
    ★ 예전에는 **점으로 시작하는 이름을 통째로** 뺐다. 리눅스 게임의 `.gamerc` 같은 본체가
      그래서 대피에서 빠졌고, 삭제는 `ok: true` · `evacuated: {}`로 끝났다(설계 §14-G ⓑ).
    ⚠️ **링크는 여기서 빠진다.** 삭제 쪽에서는 `remove._evacuate`가 슬롯 안의 링크를 아예
      **거부**하므로 대피도 축출도 일어나지 않고(링크를 따라가면 외부 파일이 백업에 복사된다
      = `.sav` 경계), 저장 쪽에서는 아래 `slot_body_exists`가 이 목록을 그대로 써서 **링크뿐인
      슬롯을 빈 슬롯으로 본다**(2026-08-22 사용자 결정 — 앱이 만들지 않은 상태까지 책임지지 않는다).
    ★ 왜 `store`에 사는가: 소비자가 `remove`와 `engine` 양쪽인데 `remove`가 `engine`을
      import하는 방향이라(remove.py 상단) `remove`에 두면 엔진에서 못 부른다. 이 파일은
      `codes` 말고는 아무것도 import하지 않는 맨 아래층이라 어느 쪽에서든 부를 수 있다.
    """
    directory = profile_dir(appid, profile)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    out = []
    for name in names:
        if is_byproduct(name):
            continue
        path = os.path.join(directory, name)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        out.append(name)
    return out


def slot_body_exists(appid, profile):
    """meta 없이 **그 슬롯에 실물이 남아 있는가**만 본다 — 위 `evacuable_names`가 세는 그 목록이다.

    meta가 손상되면 본체의 이름을 알 수 없으므로(`profile_file_path`가 meta의 filename으로
    경로를 만든다) *"무엇이 있는지"*는 못 말한다. 그러나 *"무언가 있다"*는 말할 수 있고, 그 차이가
    「빈 슬롯(묻지 않음)」과 「대피할 것이 있다(묻는다)」를 가른다.

    ★★ **세는 목록과 대피하는 목록이 같은 함수다**(설계 §14-G ⓐ). 저장은 이 술어로 *"물을
      것인가"*를 정하고 실제 대피는 `evacuable_names`가 준 이름들로 한다 — 규칙을 여기 다시
      적으면 언젠가 한쪽만 늘어나고, 그 순간 **묻지 않고 대피하거나(고지 없는 링 소모) 묻고도
      대피하지 않는다**(무백업 덮어쓰기). 그래서 목록을 다시 만들지 않고 그 함수를 그대로 부른다.
    ★ 심볼릭 링크는 **본체로 세지 않는다**(2026-08-22 사용자 결정): 앱이 만들지 않은 상태
      (외부 요인으로 생긴 링크)까지 앱이 책임지면 경계가 계속 늘어난다. 슬롯에 링크뿐이면
      **빈 슬롯으로 보고 조용히 덮는다 — 별도 고지도 하지 않는다.** 덮어쓰기는 안전하다:
      `atomic_write`가 tmp→rename이라 링크를 **대체**할 뿐 링크가 가리키는 바깥 파일에 쓰지 않는다.
      (예전에는 `os.path.isfile`이 링크를 따라가 **여기서만** 본체로 셌다 — 그 불일치를 없앤 것이다.)
    ★ 부산물 판정도 `is_byproduct` 하나를 지난다 — 예전에는 `meta.json`과 `.applied` **둘만**
      뺐고, 그래서 `.gfxprofile-tmp-*` 잔재 하나 때문에 **빈 슬롯이 「본체 있음」으로 읽혔다**.
    """
    return bool(evacuable_names(appid, profile))


# ---------------------------------------------------------------- 백업


def profile_tag(profile):
    """그 슬롯의 대피본이 다는 tag. **조립은 여기 한 곳**이다.

    자리마다 `"profile_%s" % profile`을 손으로 적으면 아래 `KINDS`만 늘어나거나 조립부만
    늘어나는 날이 온다 — 그 순간 대피본의 태그가 `KINDS` 밖으로 나가 **자기가 만든 백업을
    형식 불명으로 읽는다.**
    """
    return "profile_%s" % profile


#: `make_backup`이 붙이는 tag 전량 = *"우리가 만든 이름인가"*를 가르는 목록. 밖은 `unknown`이다.
#: (적용·복원 직전 대피본 `disk` + 슬롯 대피본 두 개.)
KIND_DISK = "disk"
KIND_UNKNOWN = "unknown"
KINDS = (KIND_DISK, profile_tag("dock"), profile_tag("internal"))

#: **stamp는 하이픈을 품는다**(`%Y%m%d-%H%M%S` = 8+1+6 = 15자). 첫 `-`로 자르면 깨진다 —
#: 고정폭으로 떼고 형태를 정규식으로 확인한다(설계 §2-C 경고).
_STAMP_LEN = 15
_STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$")
#: 같은 초 충돌 접미사 — `<stamp>-<tag>-<n>-<filename>`.
_SEQ_RE = re.compile(r"^(\d+)-(.+)$")


def parse_backup_id(backup_id):
    """백업 파일명 하나를 조각으로 되읽는다 — 아래 `_backup_name`의 **역함수**다.

    `<stamp>-<tag>[-<n>]-<filename>` → `kind` · `stamp` · `stamp_label` · `seq` · `filename`.
    형태가 안 맞으면 `kind="unknown"`, `stamp=""`, `filename=원본 이름 그대로` —
    화면은 kind 코드로 i18n 문구를 고르므로 미지 형식도 안전하게 그려진다.
    **파싱은 백엔드가 한다**(프론트는 문자열을 안 쪼갠다).

    ★★ **「형식 불명」의 정의는 여기 하나다**(설계 §14-G ⓔ, 2026-08-22). 예전에는 이 파서가
      `restore`에 살고, 순서 키(`backup_order_key`)는 **자기 정규식**으로 같은 이름을 따로
      읽었다 — 그쪽은 tag를 `[^-]+`로 **아무 문자열이나** 받았다. 그래서 우리가 만들지 않는
      tag를 단 파일이 화면에서는 *형식 불명*(종류도 시각도 안 뜬다)인데 정렬에서는 *정상 백업*
      으로 취급됐다. **이름을 만드는 곳과 읽는 곳을 한 파일에 둔다** — 갈려 있던 것이 정의가
      두 벌이 된 원인이다.
    ⚠️ 남는 모호성: 파일명 자체가 `12-video.ini`처럼 시작하면 그 `12`가 충돌 접미사로 읽힌다.
      명명 규칙에 내재된 모호성이라 여기서 해소할 수 없고, 영향은 **같은 초 안의 표시 순서**
      뿐이다(복원 대상은 `backup_id` 전체 문자열로 지정되므로 오동작은 없다).
    """
    name = str(backup_id)
    unknown = {"kind": KIND_UNKNOWN, "stamp": "", "stamp_label": "", "seq": 0, "filename": name}
    if len(name) <= _STAMP_LEN or name[_STAMP_LEN] != "-":
        return unknown
    m = _STAMP_RE.match(name[:_STAMP_LEN])
    if not m:
        return unknown
    rest = name[_STAMP_LEN + 1:]
    for kind in KINDS:
        if not rest.startswith(kind + "-"):
            continue
        tail = rest[len(kind) + 1:]
        seq = 0
        seq_match = _SEQ_RE.match(tail)
        if seq_match:
            seq, tail = int(seq_match.group(1)), seq_match.group(2)
        if not tail:
            return unknown
        return {
            "kind": kind,
            "stamp": name[:_STAMP_LEN],
            "stamp_label": "%s-%s-%s %s:%s:%s" % m.groups(),
            "seq": seq,
            "filename": tail,
        }
    return unknown


def backup_order_key(name):
    """정렬·prune·표시가 **함께 쓰는** 순서 키 `(stamp, seq, name)`. 클수록 새것이다.

    ★★ 왜 사전순이 아닌가(2026-08-15 R14 #3): 같은 초의 충돌 접미사는 **문자열로 비교하면
      `-10-`이 `-2-`보다 앞선다.** 역사전순 prune은 그 순서의 꼬리를 자르므로, 같은 초에
      12건이 쌓이면 **열 번째로 만든 백업이 두 번째 것보다 먼저 잘려 나갔다** —
      화면과 문서가 약속한 *"오래된 것부터 사라진다"*의 정반대이고, `make_backup`이
      **방금 지워진 경로를 성공값으로** 돌려주는 자리이기도 했다.
    ★ 옛 이름과 새 이름이 섞여도 규칙은 하나다: 이 함수는 **파일명만** 보고 순서를 읽으므로
      기존 백업(같은 명명 규칙으로 만들어진 것)이 그대로 올바른 자리에 놓인다. 명명 규칙을
      바꾸지 않은 이유가 그것이다 — 바꾸면 마이그레이션 없이는 옛 파일의 순서를 잃는다.
    ⚠️ 형식을 못 읽는 이름(사용자가 넣은 파일 등)은 `("", -1, name)`으로 **가장 오래된 것**
      취급한다. 표시 정렬(`restore.backup_rows`)이 이미 같은 결론을 내고 있었고, 두 순서가
      갈리면 화면이 지워지지 않을 파일 이름을 댄다.
    ★ *"형식을 못 읽는다"*의 뜻은 **위 `parse_backup_id`가 정한다**(§14-G ⓔ). 예전에는 여기에
      자기 정규식이 따로 있었고 그것이 tag를 아무 문자열이나 받아서, **화면은 형식 불명이라는데
      정렬은 정상 백업으로 세는** 이름이 있었다.
    """
    info = parse_backup_id(name)
    if info["kind"] == KIND_UNKNOWN:
        return ("", -1, name)
    return (info["stamp"], info["seq"], name)


def _next_seq(directory, stamp):
    """같은 초 안에서 **단조 증가하는** 다음 일련번호. 0이면 접미사를 붙이지 않는다.

    ★ 이름 충돌만 피하는 것으로는 부족하다: tag가 다르면 충돌이 안 나서 같은 초의 두 백업이
      **둘 다 seq 0**이 되고, 그러면 둘 사이의 생성 순서를 파일명만으로는 알 수 없다.
      그 초의 최대 번호 + 1을 쓰면 순서가 이름에 남는다.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    used = [key[1] for key in map(backup_order_key, names) if key[0] == stamp]
    return max(used) + 1 if used else 0


def backup_holds(entries, tag, sha1):
    """그 **태그의** 백업 링이 이미 그 내용을 담고 있는가 — 담고 있으면 그 경로, 아니면 `""`.

    ★★ `entries`는 **부르는 쪽이 이미 나열해 둔** 링(`list_backups`의 결과)이다 — 여기서 다시
      나열하지 않는다(§14-G ⓕ). 확인창은 축출 예고·링 지문·이 판정을 **한 번의 나열**에서
      내야 한다: 나열이 둘이면 그 사이에 링이 도는 창이 생기고, 그러면 화면이 댄 이름과 실제로
      지워지는 파일이 갈린다. 관측은 부르는 쪽이 한 번, 규칙은 여기 한 곳이다.

    ★★ **중복 판정의 문은 여기 하나다**(설계 §14-G ⓔ). 아래 `make_backup`의 무쓰기 갈래도,
      확인창의 축출 예고도 이 술어를 본다. 규칙을 고지층에 다시 적으면 언젠가 어긋나고,
      어긋나는 순간 화면이 *일어나지 않을 삭제*를 말하거나 *일어날 삭제*를 침묵한다.
    ★ **태그별이다 — 전역이 아니다**(사용자 확정 2026-08-22): 되돌릴 곳이 다른 두 행은 서로를
      대신하지 못한다(§5-C ⓐ). 두 프로필의 내용이 같을 때 전역으로 거르면 한쪽 태그의 행이
      통째로 사라지고, 화면은 그것을 *"이쪽은 백업이 없다"*로 읽는다.
    ★ **형식 불명(`unknown`)은 판정에 참여하지 않는다**: 앱이 만들지 않는 이름 = 바깥에서 들어온
      파일이고, 그 행이 되돌아가는 곳은 게임 설정 파일이라 프로필 대피본을 대신하지 못한다.
      그것과 같다는 이유로 대피를 건너뛰지 않고, 그것을 지우지도 않는다 — 태그별로 나눈 이유와
      같은 이유다. (태그 인자 자체가 `unknown`이어도 같은 조건에서 걸러진다.)
    ★ **링크는 참여하지 않는다**: 엔진 G15가 링크된 백업의 복원을 **거부**하므로 그것은 되돌릴
      수 있는 행이 아니다(`restore._entries`가 목록에서 빼는 이유와 같다) — 대신할 수 없는 것이
      대피를 막으면 안 된다. 링크를 열지 않으므로 `.sav` 경계도 그대로다.
    ★ 모르면(`sha1`이 없다) **담고 있지 않다**고 답한다 — 대피하는 쪽·고지하는 쪽이 안전하다.
    """
    if not sha1 or not isinstance(sha1, str):
        return ""
    for path in entries:
        if os.path.islink(path):
            continue
        kind = parse_backup_id(os.path.basename(path))["kind"]
        if kind == KIND_UNKNOWN or kind != tag:
            continue
        if sha1_file(path) == sha1:
            return path
    return ""


def plan_backups(entries, items):
    """`items`(= `(tag, sha1)` 쌍들)를 링에 넣을 때 **실제로 파일이 생기는 것들**만 남긴다.
    **판정은 동작이 시작할 때 여기서 한 번**이고, 아래 `make_backup`은 그 결과를 집행한다.

    `entries`는 위 `backup_holds`와 같은 뜻이다 — **한 번 나열한 링**을 그대로 받는다(ⓕ).

    축출 예고의 `adding`이 이 목록의 길이다 — 확인창은 *"이 백업이 지워집니다"*라며 이름을 대는
    자리라, 만들지도 않을 백업까지 세면 화면이 **일어나지 않을 삭제**를 약속한다.

    ★★ **비교 대상이 이 동작에서 축출될 항목이면 중복으로 보지 않는다**(사용자 결정 D1,
      2026-08-22). 한 동작이 두 슬롯을 차례로 대피시킬 때, 먼저 쓴 백업이 링을 밀어내면서
      **뒤 항목이 「이미 있다」고 믿던 바로 그 사본을 잘라 낸다** — 거기서 무쓰기로 접으면 그
      내용은 슬롯에도 백업에도 남지 않는다. 어차피 잘려 나갈 사본은 근거가 못 되므로 새로 담는다.
      ★ 그래서 승격은 **그 사본이 이번 동작에서 어차피 축출될 자리일 때만** 일어난다. 남을
        백업의 날짜는 안 바뀌고, 프로필 하나만 저장하는 갈래는 종전대로 아무것도 안 쓴다.
    ★ 쓰기가 늘면 축출이 깊어지고, 깊어지면 중복이 더 풀린다 — 그래서 **고정점**까지 돈다.
      쓸 것의 집합은 단조 증가이고 `items` 수가 상한이라 반드시 멈춘다.
    ★ 축출 자리를 자르는 식은 `restore.ring_observe`와 **같다**(`entries[BACKUP_KEEP - adding:]`).
      두 곳이 다른 식을 쓰면 화면이 댄 이름과 실제로 살아남는 내용이 갈린다.
    ★ 같은 쌍이 두 번 오면 **한 번만** 센다: 먼저 쓴 것이 그 다음 것의 중복이 되므로 실제로도
      한 건만 생긴다(한 슬롯에 내용이 같은 본체가 둘 있는 저장·삭제가 그 자리다).
    ★ `sha1`을 모르면(읽기 실패) **쓸 것으로 센다** — 예고보다 덜 지워지는 쪽이 안전하다.
      침묵한 삭제가 과하게 예고한 삭제보다 나쁘다. (그 항목은 아래 `make_backup`의 계획 조회에
      걸리지 않으므로 쓰는 쪽은 그 자리에서 스스로 판정한다 — 계획은 **허가 목록**이지 백지가 아니다.)
    """
    seen, uniq = set(), []
    for tag, sha1 in items:
        if not sha1:
            uniq.append((tag, sha1, ""))       # 모르면 쓸 것으로 — 중복 판정에 참여시키지 않는다
            continue
        if (tag, sha1) in seen:
            continue
        seen.add((tag, sha1))
        uniq.append((tag, sha1, backup_holds(entries, tag, sha1)))   # 셋째 = 근거 사본의 경로
    write = [u for u in uniq if not u[2]]
    while True:
        adding = len(write)
        # 이 동작이 `adding`칸을 쓰면 링의 꼬리가 그만큼 잘린다 — 그 자리에 있는 사본은 근거가 못 된다.
        doomed = set(entries[max(0, BACKUP_KEEP - adding):]) if adding > 0 else set()
        nxt = [u for u in uniq if (not u[2]) or (u[2] in doomed)]
        if len(nxt) == len(write):             # 고정점 — 단조 증가라 길이가 같으면 집합도 같다
            return [(t, s) for t, s, _ in nxt]
        write = nxt


def make_backup(appid, data, tag, filename, plan=None):
    """어떤 쓰기든 그 전에 여기를 거친다. 실패하면 호출자가 작업을 중단해야 한다 (G13).

    ★★ **같은 태그에 같은 내용이 이미 있으면 아무것도 쓰지 않는다**(설계 §14-G ⓔ). 디스크
      설정은 dock ↔ internal 두 내용 **사이를 왕복**하므로, 내용을 안 보고 매번 쌓으면 링 10칸이
      같은 사본으로 찬다 — 실측 81칸 중 지금 어디에도 없어 백업이 있어야만 되찾을 수 있는
      내용은 **7종**뿐이었고 **세 게임은 10칸 전부가 사본**이었다. 마모의 주범은 실패가 아니라
      정상 동작이다. **다섯 호출부가 전부 여기를 지난다** — 쓰기의 문은 그대로 이 함수 하나다.
    ⚠️ **판정까지 이 문 하나였던 것은 여기까지다**(사용자 결정 D1, 2026-08-22): 한 동작이 백업을
      **여럿** 쓰는 자리는 위 `plan_backups`가 **동작 경계에서 한 번** 판정하고 그 계획(`plan`)을
      여기로 넘긴다. 매 호출마다 다시 재면, 먼저 쓴 백업이 밀어낸 칸을 뒤 항목이 계속 근거로
      믿어 **내용이 통째로 사라진다.** `plan`이 없으면(단일 쓰기) 종전대로 여기서 스스로 잰다.
      (`plan`은 `(safe_tag, sha1)`의 **집합**이고 이 함수가 소비하면서 줄인다 — 호출부가
      `set(plan_backups(...))`로 만들어 한 동작 안의 여러 호출에 **같은 객체**를 넘긴다.)
    ★ **계획은 「이것만 써라」가 아니라 「이건 중복이라도 써라」는 허가 목록이다**(사용자 결정
      D6, 2026-08-22). 계획에 없는 키를 만나면 건너뛰지 않고 **그 자리에서 스스로 판정한다** —
      계획은 본체를 `sha1_file`로 재고 쓰기는 `read_bytes`로 다시 읽으므로, 그 사이에 본체가
      바뀌면 실제 키가 계획에 없다. 거기서 무쓰기로 접으면 **대피 없이 저장이 슬롯을 덮고 삭제가
      `rmtree`까지 간다** — 계획을 도입하면서 새로 열릴 뻔한 자리라 안전한 쪽으로 닫아 둔다.
    ★ **이 함수는 파일을 지우지 않는다** = 이미 있는 것을 지우고 새로 담지 **않는다.** 반대
      방식은 *파일을 지우는 자리*를 하나 새로 만든다 — 링에서 파일이 사라지는 자리는 아래
      `prune_backups` 하나로 족하다. 이 프로젝트에는 무쓰기 갈래의 문법이 이미 둘 있다
      (적용의 `already` · 저장의 `already`).
    ⚠️ 다만 *"남는 것은 언제나 「먼저 담긴 것」이고 사용자가 보는 결과는 같다"*는 **한 번 부를
      때만 참이었다**(D1). 계획이 *"중복이라도 써라"*고 허가하는 자리는 **먼저 담긴 사본이 이번
      동작의 축출로 어차피 사라지는 자리**이고, 그 내용은 새 날짜로 다시 담겨 살아남는다.
      갈리는 것은 내용이 아니라 그 사본의 **날짜**다.
    ★ **반환값이 무쓰기를 말한다**: 만들었으면 경로, 안 만들었으면 `None`이다. 이미 그 내용을
      담고 있는 백업의 경로를 대신 돌려주지 않는 것은, 돌려주면 부르는 쪽이 *방금 만든 것*과
      구별할 수 없기 때문이다. (다섯 호출부는 지금 전부 반환을 버린다 — 계약이 필요한 곳은
      고지층이고 그쪽은 위 `plan_backups`로 **같은 판정**을 미리 본다.)
    ★ 규칙은 **앞으로 만들 백업에만** 걸린다. 이미 쌓인 사본을 소급해서 정리하지 않는다 —
      그래서 구현 직후의 링은 포화 상태 그대로이고, 중복이 빠져 여유가 생기는 것은 링이 한 바퀴
      돈 **뒤**다(그 사이에는 §15-D에 적은 잔여 위험이 실제로 열려 있다).
    """
    safe_tag = tag.replace("/", "_").replace(":", "_")
    key = (safe_tag, sha1_bytes(data))
    if plan is not None and key in plan:
        # 계획이 이 건을 허가했다 — 중복이어도 쓴다(근거 사본이 이번 동작에서 축출될 자리다).
        # 허가는 **한 건에 한 번**이라 여기서 뺀다: 같은 키가 또 오면 방금 쓴 것이 진짜 중복이고,
        # 그때는 옆의 `elif`가 그것을 찾아 무쓰기로 접는다(`plan_backups`가 한 번만 센 것과 같다).
        plan.discard(key)
    elif backup_holds(list_backups(appid), safe_tag, key[1]):
        return None                     # ★ 디렉터리조차 만들지 않는다 — 무쓰기는 무쓰기다
    directory = backups_dir(appid)
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    seq = _next_seq(directory, stamp)
    path = os.path.join(directory, _backup_name(stamp, safe_tag, seq, filename))
    # 같은 초에 두 번 백업하면 덮어쓰므로 접미사를 붙인다. (위 `_next_seq`가 이미 비켜 준
    # 자리라 보통 한 번도 돌지 않는다 — 남겨 두는 것은 **덮어쓰기만은 구조로 막기** 위해서다.)
    while os.path.exists(path):
        seq += 1
        path = os.path.join(directory, _backup_name(stamp, safe_tag, seq, filename))
    atomic_write(path, data)
    # ★ **방금 쓴 파일은 이 자리에서 지워지지 않는다**(불변식). 순서 키가 옳으면 어차피 맨
    #   앞이지만, 이름을 못 읽는 극단(위 `backup_order_key`의 폴백)에서도 이 인자가 그 사실을
    #   보장한다 — 성공값으로 돌려주는 경로가 이미 지워진 경로일 수는 없다.
    prune_backups(appid, protect=path)
    return path


def _backup_name(stamp, safe_tag, seq, filename):
    if seq <= 0:
        return "%s-%s-%s" % (stamp, safe_tag, filename)
    return "%s-%s-%d-%s" % (stamp, safe_tag, seq, filename)


def list_backups(appid):
    """그 게임의 백업 **최신순**. prune·축출 예고·화면 목록이 전부 이 순서를 쓴다."""
    directory = backups_dir(appid)
    if not os.path.isdir(directory):
        return []
    entries = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if not name.startswith(TMP_PREFIX)
    ]
    return sorted(entries, key=lambda p: backup_order_key(os.path.basename(p)), reverse=True)


def prune_backups(appid, protect=None):
    """링을 `BACKUP_KEEP`칸으로 자른다 — **오래된 것부터**(위 `backup_order_key`).

    `protect`는 방금 쓴 파일이다. 절대 지우지 않고, 대신 한 칸을 차지한 것으로 센다.
    """
    entries = [p for p in list_backups(appid) if p != protect]
    keep = BACKUP_KEEP - (1 if protect else 0)
    for path in entries[keep:]:
        try:
            os.unlink(path)
        except OSError:
            pass
