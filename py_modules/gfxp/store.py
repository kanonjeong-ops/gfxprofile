"""저장소 계층 — 레지스트리, 프로필 파일, 백업.

파일 형식·원자적 쓰기·백업 링 불변식을 맡는다. 사용자 동작의 가드는 상위 계층에 둔다.
표준 라이브러리만 사용한다.
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

#: 이 층의 로거. 판단은 안 하지만 비치명으로 접은 실패는 남긴다
#: (`atomic_write`의 디렉터리 fsync). 이름은 `gfxp.<모듈>`로 통일한다.
_log = logging.getLogger("gfxp.store")

BACKUP_KEEP = 10
REGISTRY_VERSION = 1
DESKTOP_UID = 1000          # 핸드헬드의 주 사용자(SteamOS에서는 deck)

#: 프로필 슬롯 안에서 우리가 만드는 부산물의 이름. 그 밖의 파일은 전부 본체다.
#:   · `meta.json`         — 그 슬롯의 기록
#:   · `.applied`          — 옛 버전이 남긴 마커. 만드는 코드는 없고 걸러 내는 데만 쓴다
#:   · `.gfxprofile-tmp-*` — `atomic_write`가 쓰다 죽었을 때의 잔재
META_NAME = "meta.json"
APPLIED_NAME = ".applied"
TMP_PREFIX = ".gfxprofile-tmp-"


def is_byproduct(name):
    """그 이름이 부산물인가 = 「본체가 아닌가」. 같은 질문을 하는 곳은 전부 여기를 지난다.

    목록을 두 벌 적으면 언젠가 한쪽만 늘어난다. 거르는 집합과 등록 가능한 집합이 어긋나면
    그 교집합이 곧 결함이다 — 대피에서는 부산물로 걸러지고 등록은 되는 이름이 있으면
    사용자는 성공 통지를 받은 채 프로필 한 벌을 잃는다.
    소비자: `evacuable_names`(그리고 그것을 부르는 `slot_body_exists`) · `remove._evacuate` ·
    `engine.assert_config_candidate`.
    점으로 시작하는 이름을 막는 것이 아니다 — `.gamerc` 같은 본체 이름은 걸리지 않는다.
    걸리는 것은 "우리가 그 자리에 이미 쓰는 이름인가"뿐이다.
    """
    return name in (META_NAME, APPLIED_NAME) or name.startswith(TMP_PREFIX)


def user_home():
    """실제 사용자의 홈. `os.path.expanduser("~")`를 직접 쓰지 말 것.

    `GFXPROFILE_HOME`, loader가 준 `DECKY_USER_HOME`, 현재 비-root 사용자의 홈,
    `SUDO_USER`, UID 1000의 홈 순서로 찾고, 모두 실패하면 `expanduser`로 돌아간다.
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
    """널 바이트가 있으면 바이너리로 본다. 줄 수를 셀 대상인지 가리는 데만 쓴다(`count_lines`)."""
    return b"\x00" in data[:8192]


def count_lines(data):
    if looks_binary(data):
        return None
    return data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)


def atomic_write(path, data, mode=None, owner=None):
    """같은 디렉터리 tmp -> fsync -> os.replace. 도중에 죽어도 반쪽 파일이 남지 않는다.

    디렉터리도 fsync한다 — rename을 메타데이터까지 내리려는 것이다. 다만 그 fsync의 실패는
    치명이 아니다: 새 이름이 제자리에 있으면 로그만 남기고 넘어간다. `os.replace`는 위 `try`
    안이고 이 fsync는 밖이라, 여기서 예외를 올리면 본체를 이미 덮은 뒤에 쓰기 실패를 말하게
    된다 — 호출자는 안 바뀌었다고 읽는데 본체는 바뀐 상태다. 계약은 "덮어쓰기 전에 반드시
    대피한다"가 아니라 "대피는 할 수 있을 때 한다"이다.
    이 함수는 앱이 파일을 쓰는 모든 자리가 지나는 공용 경로라 그 완화도 전부에 걸린다. 다만
    잃는 것은 「이름의 지속」이지 내용의 온전성이 아니다 — 파일 내용은 위에서 이미 fsync한다.
    `durable=` 같은 인자로 범위를 좁히지 않는다 — 접착층이 끌 수 있는 가드가 되기 때문이다.

    `owner=(uid, gid)`를 주면 쓰기 후 소유자를 되돌린다. 지금은 백엔드가 root로 돌지 않아
    무해한 무동작이지만, root로 도는 경로가 생기면 게임 설정 파일이 root 소유가 되어
    게임(deck)이 종료 시 다시 쓰지 못한다.
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
                pass            # 소유권 복원 실패는 비치명으로 취급한다
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
        # 새 이름이 제자리에 있을 때만 접는다. 없으면 쓰기가 성립하지 않은 것이므로 올린다 —
        # 안 쓴 것을 썼다고 말하지 않는다.
        # (열거가 막힌 폴더에서도 `exists`는 답한다 — `0300`은 `listdir`만 막고 이름으로 여는
        #  것은 된다. 이 경로가 성립하는 전제다.)
        if not os.path.exists(path):
            raise
        # 좁게 잡는다 — `OSError`뿐이다. 넓게 잡으면 이 자리가 다른 실패까지 삼킨다.
        _log.warning("atomic_write: 디렉터리 fsync 실패(비치명) path=%s dir=%s: %s: %s",
                     path, directory, type(exc).__name__, exc)


# ---------------------------------------------------------------- 레지스트리

def default_registry():
    return {
        "version": REGISTRY_VERSION,
        # last_appid: 현재 UI가 기록하거나 복원하지 않는다. 게임 삭제 때 그 게임을 가리키는
        # 기존 값만 읽어 `None`으로 정리한다.
        "settings": {"auto_apply": False, "mode_override": None, "last_appid": None},
        # gpu_map: 현재 동작 결정에는 쓰이지 않고 기본 레지스트리와 전체 초기화에만 남아 있다.
        "gpu_map": {},
        "games": {},
    }


class RegistryError(Exception):
    """레지스트리를 읽을 수 없음. 사용자에게 그대로 보여줄 안내를 담는다.

    `code`(codes.py 상수)와 `params`를 드는 형태가 `engine.Refused`와 같다 — 접착층이 두
    예외를 같은 방식으로 봉투에 실을 수 있어야 분기가 늘지 않는다.
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
    """그 슬롯이 실제로 그 내용을 들고 있는가 — 기록(meta)이 아니라 본체 실측까지 본다.

    판정의 문은 여기 하나다. meta만 믿으면 "이 내용은 저 슬롯에 보존돼 있다"가 거짓일 수 있고
    (meta는 B라는데 본체가 없거나 C인 저장소 손상), 그 전제 위에서 적용은 대피를 생략하고
    게임 설정 파일을 덮으며 복원은 "이미 같다"며 손상된 슬롯을 못 고친다.
    모르면 거짓을 돌려준다 — 안전한 쪽이 고지·대피·쓰기 경로다.

    `filename`을 주면 그 이름으로 남아 있는지까지 본다 — 이름이 달라지면 슬롯에 남는 파일이
    실제로 바뀌므로 "달라지는 것이 없다"가 거짓이 된다. 4인자로 부르는 곳은 수를 세지 말고
    이름을 적는다(개수로 적으면 늘린 사람이 안 고친다):
      · `engine.save_profile` — 크기 가드의 기준값을 믿을지 판정(`trusted`)
      · `engine.save_profile` — 저장의 무쓰기 판정
      · `confirm.needs_confirm` — "이미 같다" 조기반환
      · `confirm._slot_materials` — 확인창 표시재료(크기·해시)를 믿을지 판정
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
    """그 슬롯에서 대피 대상이 되는 본체 파일 이름들(이름순). 조회 전용이다.

    세는 쪽과 지우는 쪽이 같은 함수를 돈다 — 기준이 갈리면 확인창이 약속한 축출 수와 실제가
    어긋난다. 제외는 부산물(`is_byproduct`)·링크·비일반 파일이고, 그 밖은 전부 본체다.
    이 목록의 길이가 곧 「링에 쌓일 백업 수」는 아니다: 같은 태그에 같은 내용이 이미 있으면
    `make_backup`이 아무것도 쓰지 않는다. 대피 대상은 여전히 이 목록 전부이고, 그중 몇 건이
    실제로 파일이 되는가는 `plan_backups`가 가른다 — 축출 예고는 그쪽을 세야 한다.
    링크가 빠지는 이유: 링크를 따라가면 외부 파일이 백업에 복사된다(`.sav` 경계). 삭제 쪽은
    `remove._evacuate`가 슬롯 안의 링크를 거부하고, 저장 쪽은 `slot_body_exists`가 이 목록을
    그대로 써서 링크뿐인 슬롯을 빈 슬롯으로 본다.
    왜 `store`에 사는가: 소비자가 `remove`와 `engine` 양쪽인데 `remove`가 `engine`을
    import하는 방향이라, 양쪽에서 부를 수 있는 자리가 이 아래층뿐이다.
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
    """meta 없이 그 슬롯에 실물이 남아 있는가만 본다 — `evacuable_names`가 세는 그 목록이다.

    meta가 손상되면 본체의 이름을 알 수 없어(`profile_file_path`가 meta의 filename으로 경로를
    만든다) "무엇이 있는지"는 못 말한다. 그러나 "무언가 있다"는 말할 수 있고, 그 차이가
    「빈 슬롯(묻지 않음)」과 「대피할 것이 있다(묻는다)」를 가른다.

    세는 목록과 대피하는 목록이 같은 함수다. 규칙을 여기 다시 적으면 언젠가 한쪽만 늘어나고,
    그 순간 묻지 않고 대피하거나(고지 없는 링 소모) 묻고도 대피하지 않는다(무백업 덮어쓰기).
    심볼릭 링크는 본체로 세지 않는다 — 슬롯에 링크뿐이면 빈 슬롯으로 보고 조용히 덮는다.
    덮어쓰기는 안전하다: `atomic_write`가 tmp→rename이라 링크를 대체할 뿐, 링크가 가리키는
    바깥 파일에 쓰지 않는다.
    """
    return bool(evacuable_names(appid, profile))


# ---------------------------------------------------------------- 백업


def profile_tag(profile):
    """그 슬롯의 대피본이 다는 tag. 조립은 여기 한 곳이다.

    자리마다 `"profile_%s" % profile`을 손으로 적으면 아래 `KINDS`만 늘거나 조립부만 느는
    날이 온다 — 그 순간 대피본의 태그가 `KINDS` 밖으로 나가 자기가 만든 백업을 형식 불명으로
    읽는다.
    """
    return "profile_%s" % profile


#: 현재 제품 호출부가 `make_backup`에 넘기는 tag 목록. 파서는 이 밖의 tag를 `unknown`으로 읽는다.
#: 적용·복원 직전 대피본 `disk` + 슬롯 대피본 둘.
KIND_DISK = "disk"
KIND_UNKNOWN = "unknown"
KINDS = (KIND_DISK, profile_tag("dock"), profile_tag("internal"))

#: stamp는 하이픈을 품는다(`%Y%m%d-%H%M%S` = 8+1+6 = 15자). 첫 `-`로 자르면 깨진다 —
#: 고정폭으로 떼고 형태를 정규식으로 확인한다.
_STAMP_LEN = 15
_STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$")
#: 같은 초 충돌 접미사 — `<stamp>-<tag>-<n>-<filename>`.
_SEQ_RE = re.compile(r"^(\d+)-(.+)$")


def parse_backup_id(backup_id):
    """백업 파일명 하나를 표시·정렬용 조각으로 읽는다.

    `<stamp>-<tag>[-<n>]-<filename>` → `kind` · `stamp` · `stamp_label` · `seq` · `filename`.
    형태가 안 맞으면 `kind="unknown"`, `stamp=""`, `filename=원본 이름 그대로`로 돌린다.
    `backup_order_key`도 이 파서를 써서 「형식 불명」의 정의를 공유한다.

    파일명 자체가 `12-video.ini`처럼 시작하면 `12`를 충돌 접미사로 읽는 모호성이 있다.
    영향은 같은 stamp 안의 표시 순서와 표시 파일명에 한정되며, 복원 대상은 `backup_id`
    전체 문자열로 지정한다.
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
    """정렬·prune·표시가 함께 쓰는 순서 키 `(stamp, seq, name)`. 클수록 앞에 놓는다.

    같은 stamp의 충돌 접미사는 문자열이 아니라 정수 `seq`로 비교한다. 형식을 못 읽는 이름은
    `("", -1, name)`으로 정형 백업 뒤에 놓는다. 형식 판정은 `parse_backup_id`에만 둔다.
    이 키는 파일명 속 벽시계 stamp의 순서이지 실제 생성 순서를 보증하지 않는다.
    """
    info = parse_backup_id(name)
    if info["kind"] == KIND_UNKNOWN:
        return ("", -1, name)
    return (info["stamp"], info["seq"], name)


def _next_seq(directory, stamp):
    """같은 초 안에서 단조 증가하는 다음 일련번호. 0이면 접미사를 붙이지 않는다.

    이름 충돌만 피하는 것으로는 부족하다: tag가 다르면 충돌이 안 나서 같은 초의 두 백업이
    둘 다 seq 0이 되고, 그러면 둘 사이의 생성 순서를 파일명만으로는 알 수 없다. 그 초의
    최대 번호 + 1을 쓰면 순서가 이름에 남는다.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    used = [key[1] for key in map(backup_order_key, names) if key[0] == stamp]
    return max(used) + 1 if used else 0


def backup_holds(entries, tag, sha1):
    """그 태그의 백업 링이 이미 그 내용을 담고 있는가 — 담고 있으면 그 경로, 아니면 `""`.

    `entries`는 부르는 쪽이 이미 나열해 둔 링(`list_backups`의 결과)이다 — 여기서 다시
    나열하지 않는다. 확인창은 축출 예고·링 지문·이 판정을 한 번의 나열에서 내야 한다: 나열이
    둘이면 그 사이에 링이 도는 창이 생기고, 화면이 댄 이름과 실제로 지워지는 파일이 갈린다.
    관측은 부르는 쪽이 한 번, 규칙은 여기 한 곳이다.

    중복 판정의 문은 여기 하나다 — `make_backup`의 무쓰기 갈래도 `plan_backups`의 축출 예고도
    이 술어를 본다. 규칙을 고지층에 다시 적으면 화면이 일어나지 않을 삭제를 말하거나 일어날
    삭제를 침묵한다.
    태그별이지 전역이 아니다: 되돌릴 곳이 다른 두 행은 서로를 대신하지 못한다. 두 프로필의
    내용이 같을 때 전역으로 거르면 한쪽 태그의 행이 통째로 사라지고, 화면은 그것을 "이쪽은
    백업이 없다"로 읽는다.
    형식 불명(`unknown`)은 참여하지 않는다: 앱이 만들지 않은 이름이라 그 행이 되돌아가는 곳은
    게임 설정 파일이고, 프로필 대피본을 대신하지 못한다. 그것과 같다는 이유로 대피를 건너뛰지
    않고 그것을 지우지도 않는다. (태그 인자 자체가 `unknown`이어도 같은 조건에서 걸러진다.)
    링크도 참여하지 않는다: 엔진이 링크된 백업의 복원을 거부하므로 되돌릴 수 있는 행이
    아니다. 대신할 수 없는 것이 대피를 막으면 안 된다. 링크를 열지 않으므로 `.sav` 경계도 그대로다.
    모르면(`sha1`이 없다) 담고 있지 않다고 답한다 — 대피하는 쪽·고지하는 쪽이 안전하다.
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


def _doomed_tail(entries, adding):
    """이 동작이 `adding`건을 쓸 때 링에서 밀려날 자리. 계획 경로와 계획 밖 판정이 같이 쓴다.

    이 식을 두 벌로 적지 마라. `plan_backups`와 `_trusted_entries`가 각자 적고 있던 동안
    같은 경계에서 결함이 되풀이됐다 — 매번 산술을 고쳐 닫았고 매번 다른 경계가 남았다.
    그래서 산술이 아니라 자리를 고쳤다: 경계 조건이 몇 개든 한 곳에만 있고, 계획 밖 판정은
    그 여집합을 구조로 받는다.
    `adding == 0`은 「꼬리 없음」이다 — 링이 상한을 넘어도 그렇다. `prune_backups`는
    `make_backup` 안에서 쓰기 뒤에만 돌기 때문에, 한 건도 안 쓰면 아무도 안 밀려난다.
    상한을 넘긴 링을 「어차피 `BACKUP_KEEP`칸으로 잘린다」고 읽으면 여기서 틀린다.
    """
    return set(entries[max(0, BACKUP_KEEP - adding):]) if adding > 0 else set()


def plan_backups(entries, items):
    """`items`(= `(tag, sha1)` 쌍들)를 링에 넣을 때 실제로 파일이 생기는 것들만 남긴다.
    판정은 동작이 시작할 때 여기서 한 번이고, 아래 `make_backup`은 그 결과를 집행한다.

    `entries`는 위 `backup_holds`와 같은 뜻이다 — 한 번 나열한 링을 그대로 받는다.

    축출 예고의 `adding`이 이 목록의 길이다 — 확인창은 "이 백업이 지워집니다"라며 이름을 대는
    자리라, 만들지도 않을 백업까지 세면 화면이 일어나지 않을 삭제를 약속한다.

    비교 대상이 이 동작에서 축출될 항목이면 중복으로 보지 않는다. 한 동작이 두 슬롯을 차례로
    대피시킬 때, 먼저 쓴 백업이 링을 밀어내면서 뒤 항목이 「이미 있다」고 믿던 바로 그 사본을
    잘라 낸다 — 거기서 무쓰기로 접으면 그 내용은 슬롯에도 백업에도 남지 않는다. 그래서 승격은
    그 사본이 어차피 축출될 자리일 때만 일어나고, 프로필 하나만 저장하는 갈래는 아무것도 안 쓴다.
    쓰기가 늘면 축출이 깊어지고 깊어지면 중복이 더 풀린다 — 그래서 고정점까지 돈다. 쓸 것의
    집합은 단조 증가이고 `items` 수가 상한이라 반드시 멈춘다.
    축출 자리를 자르는 식은 `_doomed_tail` 하나다(`restore.ring_observe`도 그것을 부른다) —
    여기 옮겨 적지 않는다. 옮겨 적으면 식이 바뀔 때 인용만 옛 모양으로 남는다.
    같은 쌍이 두 번 오면 한 번만 센다: 먼저 쓴 것이 그 다음 것의 중복이 되므로 실제로도 한 건만
    생긴다.
    `sha1`을 모르면(읽기 실패) 쓸 것으로 센다 — 침묵한 삭제가 과하게 예고한 삭제보다 나쁘다.
    그 항목은 `make_backup`의 계획 조회에 걸리지 않으므로 쓰는 쪽이 그 자리에서 스스로 판정한다 —
    계획은 허가 목록이지 백지가 아니다.
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
        doomed = _doomed_tail(entries, adding)
        nxt = [u for u in uniq if (not u[2]) or (u[2] in doomed)]
        if len(nxt) == len(write):             # 고정점 — 단조 증가라 길이가 같으면 집합도 같다
            return [(t, s) for t, s, _ in nxt]
        write = nxt


class BackupPlan(set):
    """한 동작의 백업 허가 목록(`(safe_tag, sha1)`의 집합) + 그 동작이 이미 쓴 경로.

    집합 부분은 `make_backup`이 `in`으로 보고 `discard`로 소비하면서 줄인다 —
    `_trusted_entries`의 `len(plan)`은 그래서 "앞으로 남은 쓰기"를 센다. 호출부는
    `BackupPlan(plan_backups(...))`로 만들어 한 동작 안의 여러 호출에 같은 객체를 넘긴다.
    `written`이 여기 붙은 이유: prune이 보호할 것이 "방금 쓴 파일 하나"가 아니라 "이번 동작이
    쓴 것 전부"라, 그 목록을 이고 다닐 동작 경계 객체가 필요한데 계획이 이미 그 경계다.
    두 번째 객체를 만들어 나란히 들고 다니면 언젠가 한쪽만 넘기는 호출부가 생긴다.
    `plan`이 `None`인 갈래(단일 쓰기)에는 이 객체가 없다 — 보호할 것도 자기 하나뿐이다.
    실제 쓰기가 일어나는 호출에 평범한 `set`을 넘기면 `make_backup`이 `written`을 찾는 자리에서
    실패한다. 조용히 종전 동작으로 돌아가지 않게 이 실패를 감추지 않는다.
    """

    def __init__(self, items=()):
        super().__init__(items)
        #: 이 동작이 실제로 만든 백업 경로 — 쓴 순서다(`prune_backups`가 그 순서를 쓴다).
        self.written = []


def _trusted_entries(appid, plan):
    """무쓰기 판정의 근거로 삼아도 되는 링 항목 — 이번 동작이 축출할 꼬리를 뺀 나머지.

    축출될 사본은 근거가 아니다: 먼저 쓴 대피본이 근거 사본을 밀어내므로, 호출 시점에 보이는
    사본이 그 동작이 끝나면 없을 수 있다. 그것을 근거로 무쓰기가 되면 그 내용은 슬롯에도
    백업에도 남지 않는다.
    묻는 것은 「이 쓰기를 안 했을 때 증인이 살아남는가」다 — 그래서 지금 판정 중인 쓰기는
    꼬리에 세지 않는다. 자기 쓰기를 세면 자기실현 회로가 된다: "이 쓰기가 일어난다"는 가정이
    꼬리를 키우고 → 증인이 꼬리에 들어가고 → 안 믿게 되고 → 정말로 쓴다.
    (`plan_backups`는 같은 순환을 고정점으로 푼다. 여기는 필요 없다 — "안 썼을 때"를 물으면
     순환 자체가 생기지 않는다.)
    식은 위 `_doomed_tail` 하나이고 여기는 그 여집합이다 — 산술을 다시 적지 않는다.
    `BACKUP_KEEP - len(plan)`으로 세면 안 된다: 그 식은 링이 가득 찼다고 가정하므로, 비포화
    링에서는 살아남을 증인을 불신하게 된다.
    `plan`은 쓸 때마다 줄고 `entries`는 매번 다시 나열하므로 호출마다 다시 재도 맞는다.
    `plan`이 없으면(단일 쓰기) 축출도 자기 것 하나뿐이라 링 전체가 근거다.
    """
    entries = list_backups(appid)
    if plan is None:
        return entries
    doomed = _doomed_tail(entries, len(plan))
    return [e for e in entries if e not in doomed]


def make_backup(appid, data, tag, filename, plan=None):
    """게임 설정이나 슬롯 본체를 덮어쓰기 전에 대피본을 만든다. 실패하면 호출자가 작업을
    중단해야 한다.

    기본적으로 같은 태그에 같은 내용이 있으면 쓰지 않는다. 여러 건을 한 동작에서 대피할 때는
    `plan_backups`가 먼저 판정하고 `BackupPlan`을 넘긴다. 계획이 허가한 키는 근거 사본이 이번
    동작에서 밀려날 수 있으므로 중복이어도 쓴다. 계획에 없는 키는 `_trusted_entries`로 다시
    판정한다. 계획은 허가 목록이며, 소비한 키는 `discard`한다.

    호출부는 `remove._evacuate` · `engine.save_profile` · `engine.apply_profile` ·
    `engine.restore_backup`(두 자리)이다. 호출부를 늘리면 이 목록도 갱신한다.
    이 함수 자체는 기존 백업을 지우지 않는다. 링 삭제는 `prune_backups`에만 맡긴다.
    만들었으면 경로, 쓰지 않았으면 `None`을 돌린다. 현재 호출부는 반환값을 쓰지 않는다.
    중복 억제는 앞으로 만들 백업에만 적용하며 이미 쌓인 중복을 소급 정리하지 않는다.
    """
    safe_tag = tag.replace("/", "_").replace(":", "_")
    key = (safe_tag, sha1_bytes(data))
    if plan is not None and key in plan:
        # 계획이 이 건을 허가했다 — 중복이어도 쓴다(근거 사본이 이번 동작에서 축출될 자리다).
        # 허가는 한 건에 한 번이라 여기서 뺀다: 같은 키가 또 오면 방금 쓴 것이 진짜 중복이고,
        # 그때는 옆의 `elif`가 그것을 찾아 무쓰기로 접는다(`plan_backups`가 한 번만 센 것과 같다).
        plan.discard(key)
    elif backup_holds(_trusted_entries(appid, plan), safe_tag, key[1]):
        return None                     # 디렉터리조차 만들지 않는다 — 무쓰기는 무쓰기다
    directory = backups_dir(appid)
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    seq = _next_seq(directory, stamp)
    path = os.path.join(directory, _backup_name(stamp, safe_tag, seq, filename))
    # 같은 초에 두 번 백업하면 덮어쓰므로 접미사를 붙인다. (위 `_next_seq`가 이미 비켜 준
    # 자리라 보통 한 번도 돌지 않는다 — 남겨 두는 것은 덮어쓰기만은 구조로 막기 위해서다.)
    while os.path.exists(path):
        seq += 1
        path = os.path.join(directory, _backup_name(stamp, safe_tag, seq, filename))
    atomic_write(path, data)
    # 방금 쓴 파일은 이 자리에서 지워지지 않는다(불변식). 순서 키가 옳으면 어차피 맨 앞이지만,
    # 이름을 못 읽는 극단(위 `backup_order_key`의 폴백)에서도 이 인자가 그 사실을 보장한다 —
    # 성공값으로 돌려주는 경로가 이미 지워진 경로일 수는 없다.
    # 한 동작이 여럿 쓰면 「방금 쓴 것」만으로는 모자라다: 링에 미래 stamp가 있으면 새 대피본이
    # 가장 오래된 것으로 읽혀, 먼저 쓴 대피본이 뒤 쓰기의 prune에 잘려 나간다. 그래서 계획이
    # 이 동작의 쓰기를 누적해 전부 보호한다. 불변식은 넓어졌을 뿐 그대로다 — 여기서 돌려주는
    # 경로는 이 동작이 끝날 때까지 링에 있다. 예외는 이 동작이 `BACKUP_KEEP`보다 많이 쓰는
    # 경우뿐이고, 그때는 자기 것 중 먼저 쓴 것부터 밀려난다.
    if plan is None:
        prune_backups(appid, protect=path)          # 단일 쓰기 — 보호할 것은 자기 하나뿐이다
    else:
        plan.written.append(path)
        prune_backups(appid, protect=plan.written)
    return path


def _backup_name(stamp, safe_tag, seq, filename):
    if seq <= 0:
        return "%s-%s-%s" % (stamp, safe_tag, filename)
    return "%s-%s-%d-%s" % (stamp, safe_tag, seq, filename)


def list_backups(appid):
    """그 게임의 백업을 `backup_order_key` 내림차순으로 돌린다.
    prune·축출 예고·화면 목록이 이 순서를 공유한다.
    """
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
    """`backup_order_key` 순서의 꼬리를 잘라 링을 `BACKUP_KEEP`칸으로 제한한다.

    `protect`는 이번 동작이 쓴 경로 하나 또는 쓴 순서의 목록이다. 보호 대상을 나중에 쓴
    것부터 앞에 놓고 나머지 링을 이은 뒤 한 번만 자른다. 보호 대상도 링 상한을 차지하며,
    상한보다 많으면 그중 먼저 쓴 것부터 밀려난다.

    한 동작이 여러 백업을 쓰면 지금 것 하나만 보호해서는 안 된다. 첫 쓰기보다 미래 stamp인
    기존 항목이 `BACKUP_KEEP - 1`건 이상이면, 두 번째 prune에서 첫 쓰기가 꼬리로 밀린다.
    그래서 `BackupPlan.written`이 이번 동작의 쓰기를 누적해 넘긴다.

    이 처분은 한 동작 안에서는 쓴 순서를 우선한다. 동작 밖의 순서는 여전히 파일명 속 벽시계
    stamp에서 유도하므로 시계 역행 자체는 고치지 않는다.
    자르는 자리는 `[BACKUP_KEEP:]` 하나다. 링에 없는 보호 경로는 목록에서 제외한다.
    """
    ring = list_backups(appid)                       # 최신순 — 자르는 순서의 정본이다
    if protect is None:
        mine = []
    elif isinstance(protect, str):
        mine = [protect]                             # 단일 쓰기 — 보호할 것은 자기 하나뿐이다
    else:
        mine = list(protect)                         # 이번 동작이 쓴 것 전부(쓴 순서)
    have, seat = set(ring), set(mine)
    # 이번 동작이 쓴 것을 나중에 쓴 것부터 맨 앞에 놓는다 = 그것들이 이 링의 최신이다.
    ordered = [p for p in reversed(mine) if p in have] + [p for p in ring if p not in seat]
    for path in ordered[BACKUP_KEEP:]:
        try:
            os.unlink(path)
        except OSError:
            pass
