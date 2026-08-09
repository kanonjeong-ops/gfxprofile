"""저장소 계층 — 레지스트리, 프로필 파일, 백업.

여기서는 정책 판단을 하지 않는다. 정책(가드)은 engine.py에 있다.
표준 라이브러리만 사용한다 (이 기기에 pip이 없음).
"""

import hashlib
import json
import os
import pwd
import tempfile
import time

from . import codes

BACKUP_KEEP = 10
REGISTRY_VERSION = 1
DESKTOP_UID = 1000          # 핸드헬드의 주 사용자(SteamOS에서는 deck)


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

    디렉터리 자체도 fsync해서 rename이 메타데이터까지 내려가게 한다.

    `owner=(uid, gid)`를 주면 쓰기 후 소유자를 되돌린다.
    ⚠️ M1 주석은 이것을 *"Decky 백엔드가 root로 돌기 때문"*이라 적었는데 **틀린 전제였다**
    (root는 opt-in이고 우리 `flags`는 비어 있다). 그래도 남겨 두는 이유는, 언젠가 root로 도는
    경로가 생기면 게임 설정 파일이 root 소유가 되어 **게임(deck)이 종료 시 다시 쓰지 못하기**
    때문이다. 지금은 무해한 무동작이다.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gfxprofile-tmp-")
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
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


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
    return os.path.join(profile_dir(appid, profile), "meta.json")


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


def applied_copy_path(appid, profile):
    """적용 시점의 사본. sticky 학습이 '우리가 쓴 내용'과 대조하는 기준이다."""
    return os.path.join(profile_dir(appid, profile), ".applied")


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


# ---------------------------------------------------------------- 백업

def make_backup(appid, data, tag, filename):
    """어떤 쓰기든 그 전에 여기를 거친다. 실패하면 호출자가 작업을 중단해야 한다 (G13)."""
    directory = backups_dir(appid)
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_tag = tag.replace("/", "_").replace(":", "_")
    name = "%s-%s-%s" % (stamp, safe_tag, filename)
    path = os.path.join(directory, name)
    # 같은 초에 두 번 백업하면 덮어쓰므로 접미사를 붙인다.
    suffix = 1
    while os.path.exists(path):
        path = os.path.join(directory, "%s-%s-%d-%s" % (stamp, safe_tag, suffix, filename))
        suffix += 1
    atomic_write(path, data)
    prune_backups(appid)
    return path


def list_backups(appid):
    directory = backups_dir(appid)
    if not os.path.isdir(directory):
        return []
    entries = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if not name.startswith(".gfxprofile-tmp-")
    ]
    return sorted(entries, reverse=True)


def prune_backups(appid):
    entries = list_backups(appid)
    for path in entries[BACKUP_KEEP:]:
        try:
            os.unlink(path)
        except OSError:
            pass
