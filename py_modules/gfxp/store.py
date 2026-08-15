"""저장소 계층 — 레지스트리, 프로필 파일, 백업.

여기서는 정책 판단을 하지 않는다. 정책(가드)은 engine.py에 있다.
표준 라이브러리만 사용한다 (이 기기에 pip이 없음).
"""

import hashlib
import json
import os
import pwd
import re
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

    `filename`을 주면 **그 이름으로 남아 있는지**까지 본다(저장의 무쓰기 판정만 쓴다 —
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


# ---------------------------------------------------------------- 백업

#: 백업 파일명 `<stamp>-<tag>[-<n>]-<filename>`에서 **생성 순서**를 읽는다.
#: stamp는 `%Y%m%d-%H%M%S`(하이픈 포함 15자)이고, 그 뒤 tag 다음에 오는 정수가 같은 초 안의
#: 일련번호다. 접미사가 없으면 0(그 초의 첫 백업)이다.
_ORDER_RE = re.compile(r"^(\d{8}-\d{6})-[^-]+-(?:(\d+)-)?.+$")


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
    """
    m = _ORDER_RE.match(name)
    if not m:
        return ("", -1, name)
    return (m.group(1), int(m.group(2) or 0), name)


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


def make_backup(appid, data, tag, filename):
    """어떤 쓰기든 그 전에 여기를 거친다. 실패하면 호출자가 작업을 중단해야 한다 (G13)."""
    directory = backups_dir(appid)
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_tag = tag.replace("/", "_").replace(":", "_")
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
        if not name.startswith(".gfxprofile-tmp-")
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
