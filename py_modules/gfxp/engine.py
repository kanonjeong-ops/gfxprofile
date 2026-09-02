"""엔진 — 설정 파일 교체·프로필 저장·복원과 그 가드.
확인 재료와 판정은 동작별 모듈과 접착층이 맡는다.

설계 원칙:
  P1  설정 파일을 통째로 교체한다. 내용을 파싱하지 않는다 (형식이 게임마다 다르므로).
  P4  등록할 설정 후보에서 .sav와 savegames 경로를 거부한다.
  변경 가드는 거부·무동작 방향을 우선한다.
"""

import os
import re

from . import codes, discover, store


class Refused(Exception):
    """가드에 걸려 거부됨. 표시용 `message`, 번역 선택용 `code`, 치환용 `params`를 싣는다.

    프론트는 메시지를 파싱하지 않고 `code`로 번역문을 고른다.
    """

    def __init__(self, message, code=None, **params):
        super().__init__(message)
        self.code = code
        self.params = params


# ---------------------------------------------------------------- Steam 조회

def steam_root():
    # store.home_path를 쓴다 — 이 백엔드는 `deck` 사용자로 돌지만(Decky는 root가 opt-in이고
    # 우리 plugin.json의 flags는 비어 있다), 사용자명이 `deck`이 아닌 배포판(Bazzite 등)이
    # 있으므로 홈은 언제나 store.user_home()이 정한다.
    for candidate in ((".steam", "steam"),
                      (".local", "share", "Steam"),
                      # flatpak Steam. 이 기기엔 없지만 배포 대상엔 있을 수 있다.
                      (".var", "app", "com.valvesoftware.Steam", ".steam", "steam"),
                      (".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam")):
        path = store.home_path(*candidate)
        if os.path.isdir(path):
            return path
    return store.home_path(".steam", "steam")


def steam_libraries():
    """libraryfolders.vdf에 등재된 라이브러리 경로 전부 (SD카드 등 포함)."""
    roots = [steam_root()]
    vdf = os.path.join(steam_root(), "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = re.search(r'"path"\s+"([^"]+)"', line)
                if match:
                    roots.append(match.group(1))
    except OSError:
        pass
    # realpath로 중복을 제거한다 — ~/.steam/steam은 ~/.local/share/Steam의 심볼릭 링크라
    # 그냥 두면 같은 라이브러리를 두 번 훑고 게임이 두 번씩 나온다.
    seen = []
    real_seen = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        real = os.path.realpath(root)
        if real in real_seen:
            continue
        real_seen.add(real)
        seen.append(root)
    return seen


def compat_prefix(appid):
    """해당 appid의 Proton prefix 경로. 없으면 None.

    매니페스트 우선 2패스다. 첫 매치를 그대로 돌려주면 안 된다 — 게임을 SD로 옮기면 내장
    라이브러리에 빈 pfx 껍데기가 남고 라이브러리 순서상 껍데기가 먼저 잡힌다. 그러면 SD에
    있는 진짜 설정 파일이 prefix 밖으로 판정돼 `check_path`(G11)가 정상 파일을 거부한다
    (TEKKEN 7 389730 실재 사례). 지금 어디에 설치돼 있는가는 `appmanifest_<appid>.acf`가
    정하므로 1차 패스는 그 파일이 있는 라이브러리만 본다. 매니페스트를 못 찾으면 2차 패스가
    라이브러리 순서대로 되돌아간다.
    """
    roots = steam_libraries()
    for want_manifest in (True, False):
        for root in roots:
            if want_manifest and not os.path.exists(
                    os.path.join(root, "steamapps", "appmanifest_%s.acf" % appid)):
                continue
            path = os.path.join(root, "steamapps", "compatdata", str(appid), "pfx")
            if os.path.isdir(path):
                return path
    return None


def remotecache_entries(appid):
    """Steam 클라우드가 추적하는 상대 경로 목록. 파일이 없으면 None (미동기화와 구분)."""
    base = os.path.join(steam_root(), "userdata")
    if not os.path.isdir(base):
        return None
    for user in os.listdir(base):
        path = os.path.join(base, user, str(appid), "remotecache.vdf")
        if os.path.exists(path):
            entries = []
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    stripped = line.strip()
                    match = re.match(r'^"([^"]+)"$', stripped)
                    if match and "." in match.group(1):
                        entries.append(match.group(1))
            return entries
    return None


# ---------------------------------------------------------------- 가드

def running_game(appid):
    """G5 — 해당 게임이 실행 중인가.

    게임은 종료 시점에 설정 파일을 다시 쓴다. 실행 중에 교체하면 종료 시 덮어써져
    '아무 일도 안 일어난 것처럼' 보인다. 가장 나쁜 실패 모드라 막는다.
    """
    needle = ("SteamAppId=%s" % appid).encode()
    try:
        pids = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            with open("/proc/%s/environ" % pid, "rb") as fh:
                blob = fh.read()
        except (OSError, PermissionError):
            continue
        for item in blob.split(b"\0"):
            if item == needle:
                return True
    return False


def check_path(appid, path):
    """G11 — 대상 자체가 심볼릭 링크면 거부하고, 실경로가 prefix(없으면 홈) 밖이면 거부한다."""
    if os.path.islink(path):
        raise Refused("거부: 대상 경로가 심볼릭 링크입니다 — %s" % path, code=codes.PATH_IS_SYMLINK)
    real = os.path.realpath(path)
    prefix = compat_prefix(appid)
    if prefix:
        if not real.startswith(os.path.realpath(prefix) + os.sep):
            raise Refused(
                "거부: 경로가 이 게임의 Proton prefix 밖입니다.\n"
                "  경로: %s\n  prefix: %s" % (real, prefix),
                code=codes.PATH_OUTSIDE_PREFIX
            )
    else:
        home = os.path.realpath(store.user_home())
        if not real.startswith(home + os.sep):
            raise Refused("거부: appid %s의 prefix를 찾을 수 없고 경로가 홈 밖입니다 — %s" % (appid, real), code=codes.PATH_OUTSIDE_HOME)
    return real


def check_sanity(data, ref_size=None, ref_lines=None, what="파일"):
    """G4 — 통째 교체 전에 형식 무관하게 온전성만 본다 (파싱 아님).

    크기 25~400%, 텍스트면 줄 수 ±20%. 기준이 없으면 비어있지 않은지만 본다.

    줄 수 검사는 "거의 같아야 마땅한" 두 대상에만 건다. 프로필 간 차이는 크더라도 비정상이
    아니다 — 서로 다른 것이 이 툴의 존재 이유다. 이 구분이 없으면 정상적인 프로필 전환이
    영구히 거부된다.
    """
    if not data:
        raise Refused("거부: %s가 비어 있습니다 (0바이트)." % what, code=codes.FILE_EMPTY)
    if ref_size:
        ratio = len(data) / float(ref_size)
        if ratio < 0.25 or ratio > 4.0:
            raise Refused(
                "거부: %s 크기가 기준의 %.0f%%입니다 (허용 25~400%%). "
                "다른 파일을 가리키고 있을 수 있습니다." % (what, ratio * 100),
                code=codes.SIZE_OUT_OF_RANGE
            )
    if ref_lines:
        lines = store.count_lines(data)
        if lines is not None:
            ratio = lines / float(ref_lines)
            if ratio < 0.8 or ratio > 1.2:
                raise Refused(
                    "거부: %s 줄 수가 기준의 %.0f%%입니다 (허용 80~120%%)." % (what, ratio * 100),
                    code=codes.LINE_COUNT_OUT_OF_RANGE
                )


_SAV_DENY_SUFFIX = (".sav",)
_SAV_DENY_SEGMENT = ("savegames",)      # 정확 일치. "Saved Games"(공백)는 여기 안 걸린다


def assert_config_candidate(appid, path):
    """G14 — 새로 등록할 설정 후보가 될 수 없는 파일을 거부한다 (fail-closed).

    `.sav` 파일과 `savegames` 경로를 등록 단계에서 거부한다. 이 함수는 기존 레지스트리의
    `config_path`를 다시 검증하는 관문이 아니다.

    거부 갈래는 다섯이고(아래 ①~⑤), 에러 코드로 세면 넷이다 — ①과 ②가
    `SAV_REFUSED`를 공유한다. '설정 파일처럼 보이는가'는 거부가 아니라
    `config_candidate_warnings`의 경고 사유다.
    """
    base = os.path.basename(path)
    low = base.lower()
    if low.endswith(_SAV_DENY_SUFFIX):                       # ① 세이브 파일 — P4
        raise Refused("거부: 세이브 파일(.sav)은 다루지 않습니다 — %s" % path,
                      code=codes.SAV_REFUSED, path=path)
    segs = [s.lower() for s in os.path.normpath(path).split(os.sep)[:-1]]   # 디렉터리만
    if any(s in _SAV_DENY_SEGMENT for s in segs):            # ② 세이브 폴더 — P4
        raise Refused("거부: 세이브 폴더 안의 파일은 다루지 않습니다 — %s" % path,
                      code=codes.SAV_REFUSED, path=path)
    # ③ 낡은 사본 — discover가 순회에서 프루닝하는 규칙을 여기서 좁혀 상속한다.
    #   이걸 등록하면 툴은 죽은 파일을 관리하고 게임이 실제로 읽는 파일은 영영 안 바뀐다.
    #   `discover`의 `".bak" in d`는 등록 판정에는 너무 넓다 — `com.bakery.game` 같은 정상
    #   폴더까지 막는다. 막으려는 것은 백업 폴더이므로 `.bak`으로 끝나거나 `.bak.`을 품거나
    #   경로 성분이 backup으로 끝나는 것만 본다.
    if any(s.endswith(".bak") or ".bak." in s or s.endswith("backup") for s in segs):
        raise Refused("거부: 백업·구버전 폴더 안의 파일입니다. 이것을 등록하면 게임이 실제로 읽는 "
                      "파일은 영영 바뀌지 않습니다 — %s" % path,
                      code=codes.STALE_COPY_REFUSED, path=path)
    if low in discover._EXCLUDE_NAMES:                       # ④ 엔진 보일러플레이트
        raise Refused("거부: 게임 엔진 내부 설정 파일입니다 — %s" % base,
                      code=codes.ENGINE_BOILERPLATE_REFUSED, path=path)
    # ⑤ 프로필 슬롯이 이미 쓰는 이름 — 목록은 `store.is_byproduct` 하나다.
    #   목록을 여기 다시 적으면 언젠가 한쪽만 늘어나고, "대피에서는 걸러지는데 등록은 되는"
    #   이름이 생긴다 — 그 이름의 프로필이 대피 없이 사라진다.
    #   「무엇이 아닌가」 원칙 그대로다: "설정 파일처럼 보이는가"가 아니라 "우리가 그 자리에
    #   이미 쓰는 이름인가"다. 어떤 이름이 걸리는지는 `store.is_byproduct`가 정본이다.
    if store.is_byproduct(base):
        raise Refused("거부: 이 플러그인이 프로필 폴더에서 쓰는 이름이라 등록할 수 없습니다 — %s"
                      % base,
                      code=codes.RESERVED_NAME_REFUSED, path=path)


def config_candidate_warnings(appid, path):
    """등록은 허용하되 화면에 되묻게 만드는 신호 — 거부가 아니다.

    `add_game`의 반환값에 싣지 않는다. 접착층이 따로 부른다 — 경고는 정책이 아니라 표시다.
    """
    out = []
    if discover._classify(path)[0] is None:
        out.append(codes.WARN_NOT_DISCOVER_CANDIDATE)
    prefix = compat_prefix(appid)
    if prefix:
        real_prefix = os.path.realpath(prefix)
        rel = os.path.realpath(path)[len(real_prefix) + 1:]
        if not any(rel.startswith(r.replace("/", os.sep) + os.sep)
                   for r in discover._SCAN_ROOTS):
            out.append(codes.WARN_OUTSIDE_SCAN_ROOTS)
    return out


def assert_backup_in_root(appid, backup_path):
    """G15 — 복원은 그 게임의 백업 폴더 안만 읽는다. 링크도 거부한다.

    지금은 RPC가 경로 대신 backup_id를 받아 접착층에서 폴더 밖에 도달할 수 없다. 그래도 엔진이
    스스로 보장한다 — 이 함수가 없으면 다음 호출자가 생기는 날 파일시스템 어디든 읽어서 게임
    설정 파일에 쓸 수 있다.
    """
    root = os.path.realpath(store.backups_dir(appid))
    real = os.path.realpath(backup_path)
    if os.path.islink(backup_path) or not real.startswith(root + os.sep):
        raise Refused("거부: 이 게임의 백업 폴더 밖 경로입니다 — %s" % backup_path,
                      code=codes.BACKUP_OUT_OF_ROOT, path=backup_path)


def detect_cloud_synced(appid, config_path):
    """G6 휴리스틱 — 설정 파일이 Steam 클라우드 동기화 대상일 가능성을 찾는다.

    ① remotecache 항목과 경로 세그먼트 전체 접미 일치
       (basename만 맞추면 서로 다른 `config.cfg`를 오인할 수 있다)
    ② ctime과 mtime이 다르면 클라우드 쓰기 가능성으로 기록

    ②만으로 쓰기 주체를 증명하지는 못한다.
    """
    reasons = []
    entries = remotecache_entries(appid)
    if entries:
        parts = [p for p in os.path.normpath(config_path).split(os.sep) if p]
        for entry in entries:
            entry_parts = [p for p in entry.replace("\\", "/").split("/") if p]
            if entry_parts and parts[-len(entry_parts):] == entry_parts:
                reasons.append("remotecache 항목과 경로 일치: %s" % entry)
                break
    try:
        info = os.stat(config_path)
        if abs(info.st_ctime - info.st_mtime) > 0.000001:
            reasons.append("ctime != mtime (클라우드가 마지막으로 쓴 파일로 보임)")
    except OSError:
        pass
    return (len(reasons) > 0), reasons


# ---------------------------------------------------------------- 조회

def entry_corrupt(entry):
    """그 registry 항목의 기록이 손상됐는가 — 비-dict이거나 `config_path`가 문자열이 아니다.

    실행 계열의 문(`game_or_fail`)과 정책층 미러(`confirm._preview_one`)가 같은 술어를 부른다 —
    두 벌로 적으면 언젠가 갈린다. 그래서 이름 앞에 밑줄을 두지 않고 모듈 공개로 둔다.
    빈 문자열 `""`은 손상이 아니다(문자열이다) — 빈 경로의 처리는 경로 가드·미러의 truthiness
    조건이 맡는다. `None`(미등록)은 이 술어의 밖이다: 부르는 쪽이 그 계약을 먼저 가른다.
    """
    if not isinstance(entry, dict):
        return True
    return not isinstance(entry.get("config_path"), str)


def game_or_fail(reg, appid, require_intact=True):
    entry = store.game(reg, appid)
    if entry is None:
        raise Refused("거부: appid %s가 등록되어 있지 않습니다. 먼저 add 하십시오." % appid, code=codes.GAME_NOT_REGISTERED)
    if require_intact and entry_corrupt(entry):
        raise Refused("거부: appid %s의 등록 정보가 손상되었습니다 — 항목 값 %r." % (appid, entry),
                      code=codes.REGISTRY_ENTRY_CORRUPT, appid=str(appid))
    return entry


def disk_state(reg, appid):
    """디스크의 현재 설정 파일이 어느 프로필과 일치하는지.

    `matches`는 "이 내용은 저 슬롯에 보존돼 있다"는 주장이다. 그래서 기록(meta)이 아니라
    본체 실측까지 보는 `store.slot_holds`로 판정한다. meta는 B라는데 본체가 없거나 C인 슬롯을
    "일치"라고 말하면, 그 위에서 `apply_profile`이 대피를 생략하고 게임 설정 파일을 덮어
    마지막 온전한 사본이 사라진다. 모르면 `None`(=일치 없음)이라 고지·대피 쪽으로 접힌다.
    첫 일치에서 멈춘다 — 두 슬롯이 같은 내용일 때 어느 쪽이 실릴지는 `list_profiles` 순서가 정한다.
    """
    entry = game_or_fail(reg, appid)
    path = entry["config_path"]
    result = {"exists": os.path.exists(path), "sha1": None, "matches": None}
    if not result["exists"]:
        return result
    result["sha1"] = store.sha1_file(path)
    for profile in store.list_profiles(appid):
        if store.slot_holds(appid, profile, result["sha1"]):
            result["matches"] = profile
            break
    return result


# ---------------------------------------------------------------- 동작

def add_game(reg, appid, config_path, name=None):
    appid = str(appid)
    path = os.path.abspath(os.path.expanduser(config_path))
    real = check_path(appid, path)                       # G11
    assert_config_candidate(appid, real)                  # G14
    if not os.path.exists(real):
        raise Refused("거부: 파일이 존재하지 않습니다 — %s" % real, code=codes.FILE_NOT_FOUND)
    if not os.path.isfile(real):
        raise Refused("거부: 일반 파일이 아닙니다 — %s" % real, code=codes.NOT_REGULAR_FILE)
    check_sanity(store.read_bytes(real), what="설정 파일")   # G4
    synced, reasons = detect_cloud_synced(appid, real)     # G6
    entry = reg["games"].setdefault(appid, {})
    entry.update({
        "name": name or entry.get("name") or ("appid %s" % appid),
        "config_path": real,
        "cloud_synced": synced,
        "cloud_reasons": reasons,
    })
    entry.setdefault("last_applied", None)
    entry.setdefault("applied_sha1", None)
    entry.setdefault("auto", False if synced else True)
    entry.setdefault("sticky_lines", [])
    entry.setdefault("sticky_candidates", {})
    if synced:
        entry["auto"] = False                              # G6 — 자동은 고정 해제
    return entry


def save_profile(reg, appid, profile):
    """현재 디스크 상태를 프로필로 캡처한다.

    반환의 `outcome`은 두 값이다 — `"saved"`(캡처했다) / `"already"`(한 바이트도 쓰지 않았다).
    무쓰기 갈래의 조건은 아래 무쓰기 분기 주석이 정본이다.
    """
    appid = str(appid)
    entry = game_or_fail(reg, appid)
    path = entry["config_path"]
    check_path(appid, path)                                # G11
    if not os.path.exists(path):
        raise Refused("거부: 설정 파일이 없습니다 — %s" % path, code=codes.CONFIG_MISSING)
    data = store.read_bytes(path)
    old = store.load_meta(appid, profile)
    if not isinstance(old, dict):
        # 기록이 dict가 아니어도(`[1,2]`·`"str"`·`42`) 본체는 있을 수 있다. 여기서 접지 않으면
        #   아래 `old.get(...)`이 AttributeError를 내고, 확인창을 띄워 승인까지 받은 저장이
        #   `UNEXPECTED`로 죽는다 — 묻기는 하고 못 고치는 상태다. 대피 대상은 meta가 아니라
        #   본체(`store.evacuable_names`)가 정하므로 못 믿는 기록은 비운 것과 같이 다룬다.
        #   `confirm.needs_confirm`이 같은 자리에서 같은 모양으로 접는다.
        old = {}
    # 같은 슬롯의 이전 캡처와 크기만 대조한다. 줄 수까지 묶으면 게임 업데이트로
    # 옵션 항목이 늘어난 정상 캡처가 거부된다.
    # 기준값은 기록이 본체와 맞을 때만 쓴다. 기록의 `size`는 본체와 다른 세대를 가리킬 수 있고
    #   (`store.atomic_write`가 디렉터리 fsync 실패를 비치명으로 넘긴다), 그 값으로 가드가 돌면
    #   멀쩡한 저장이 `SIZE_OUT_OF_RANGE`로 거부된다.
    # 맞지 않으면 크기 대조만 건너뛴다 — 거부하지 않는다. 믿을 수 없는 기준 앞에서 막는 쪽으로
    #   가면 사용자가 그 프로필에서 빠져나올 길이 없다. 빈 파일 거부(`FILE_EMPTY`)와 그 앞의
    #   경로 가드는 그대로 돈다.
    # 판정은 아래 무쓰기 분기와 같은 술어다(`store.slot_holds`) — 기록의 sha1·파일명으로 물으면
    #   그 술어가 곧 "기록이 본체와 맞는가"가 된다. 그 술어는 meta를 다시 읽으므로 그 사이
    #   기록이 바뀌면 거짓이 나와 대조를 건너뛴다 — 갈리는 방향은 항상 안전한 쪽이다.
    trusted = store.slot_holds(appid, profile, old.get("sha1"), old.get("filename"))
    check_sanity(data, old.get("size") if trusted else None, None,
                 what="현재 설정 파일")                                      # G4

    # ---- 달라지는 것이 없으면 아무것도 쓰지 않는다
    #
    # 저장은 슬롯을 덮기 전에 이전 내용을 대피시키는데(바로 아래), 그 대피본은 게임당 10칸짜리
    # 링(`store.BACKUP_KEEP`)을 한 칸 태우고 가장 오래된 복구 지점을 밀어낸다. 내용이 이미
    # 같으면 얻는 것 없이 그 손실만 남는다 — 사용자 쪽에서 보면 아무것도 안 바뀌는 동작이
    # 복구 지점 하나를 조용히 먹는 고지 없는 손실이다. `saved_at`도 같이 지킨다: 실제로
    # 캡처한 적 없는 시각이 찍히면 "언제 저장한 프로필인가"가 거짓이 된다.
    # 판정은 지금 읽은 바이트로 한다(route가 미리 잰 값이 아니라). 재는 시점과 쓰는 시점
    #   사이에 게임·클라우드가 파일을 바꿔도 결론이 어긋나지 않는다.
    # 기록이 아니라 슬롯의 실물과 대조한다: meta만 믿으면 본체가 깨졌거나 사라진 슬롯에서
    #   "이미 같다"며 넘어가 재저장으로 고칠 길이 사라진다. 파일명이 달라진 경우도 쓴다 —
    #   그때는 슬롯에 남는 파일 이름이 실제로 바뀌므로 "달라지는 것이 없다"가 거짓이다.
    # 술어는 적용·확인창과 공용이다(`store.slot_holds`) — 같은 질문을 두 벌로 적지 않는다.
    if store.slot_holds(appid, profile, store.sha1_bytes(data), os.path.basename(path)):
        # 실행 중 경고도 싣지 않는다 — 저장 자체가 없었으므로 "지금 캡처하면"이 성립하지 않는다.
        return {"meta": old, "warning": None, "outcome": "already"}

    warning = None
    if running_game(appid):
        # 문장이 아니라 코드를 돌려준다. 백엔드가 한국어 문장을 실어 보내면 영어 화면에
        #   한국어가 그대로 붙는다 — 문장은 화면이 현재 언어로 고른다(`i18n`의 같은 키).
        warning = codes.WARN_SAVE_WHILE_RUNNING
    # ---- 덮어쓰기 전, 슬롯의 본체를 전부 대피시킨다
    #
    # 조건은 「기록이 있는가」가 아니라 「본체가 있는가」다. 슬롯의 `meta.json`이 없거나
    #   `{}`·`null`이면, 기록으로 판정하는 순간 정상 본체가 바로 옆에 있어도 "빈 슬롯이라 잃을
    #   것이 없다"로 접혀 확인 없이·대피 없이 덮인다 — 그 프로필은 슬롯에도 백업 링에도 안
    #   남는다. 앱이 그 상태를 만드는 경로가 둘 있다(새 슬롯 저장 중 meta 쓰기 실패로 본체만
    #   남음 / 삭제가 `rmtree`에서 중단). 그때 화면은 「프로필 없음」이라 사용자의 자연스러운
    #   재저장이 곧 파괴 트리거가 된다.
    # 그래서 대피 대상은 meta가 아니라 디렉터리 열거로 얻는다(`store.evacuable_names`) —
    #   meta를 못 믿는 상태가 이 갈래의 전제인데 그 meta로 파일 이름을 만들면 같은 거짓을
    #   한 번 더 믿는 것이 된다.
    # 본체가 여럿이면 여럿 다 대피한다. 앱이 그 상태를 만들지는 않는다(같은 appid 재등록은
    #   등록 route가 `ALREADY_REGISTERED`로 거부하고, 슬롯 복원은 그 슬롯이 쓰던 이름을
    #   유지한다). 그래도 목록으로 도는 이유는 밖에서 들어온 파일·중단된 삭제 잔재가 남을 수
    #   있고, 그때 한 개만 대피시키면 나머지가 고지 없이 사라지기 때문이다.
    #   확인창의 축출 예고도 같은 목록에서 산출된다(`confirm.needs_confirm`) — 세는 쪽과
    #   지우는 쪽이 같은 함수를 돌아야 예고와 실제가 맞는다.
    # 다만 링에 쌓이는 개수는 이 목록의 길이가 아니다: 같은 태그에 같은 내용이 이미 있으면
    #   `store.make_backup`이 아무것도 쓰지 않는다. 단 그 사본이 이번 동작에서 어차피 축출될
    #   자리이면 `store.plan_backups`가 쓰기를 허가한다. 대피 대상은 어느 쪽이든 전부다.
    # 그 판정은 여기서 한 번 내려 루프에 넘긴다. 호출마다 다시 재면 먼저 쓴 대피본이 밀어낸
    #   칸을 뒤 항목이 계속 근거로 믿어 그 내용이 통째로 사라진다. 목록을 먼저 잡는 이유도
    #   같다 — 세는 쪽과 도는 쪽이 다른 나열을 보면 계획이 어긋난다.
    directory = store.profile_dir(appid, profile)
    names = store.evacuable_names(appid, profile)
    plan = store.BackupPlan(store.plan_backups(
        store.list_backups(appid),
        [(store.profile_tag(profile), store.sha1_file(os.path.join(directory, n))) for n in names]))
    for name in names:
        try:
            store.make_backup(appid, store.read_bytes(os.path.join(directory, name)),
                              store.profile_tag(profile), name, plan=plan)
        except OSError as exc:                             # G13 — 대피 실패면 아무것도 쓰지 않는다
            # 백업 호출만 좁게 잡는다. 넓게 잡으면 다른 실패까지 삼켜 `BACKUP_FAILED`가 거짓
            #   사유가 되고, 사용자는 원인과 다른 복구 안내를 받는다.
            raise Refused("거부: 백업에 실패해 저장을 중단했습니다 (%s). 프로필은 그대로입니다."
                          % exc, code=codes.BACKUP_FAILED)
    meta = store.write_profile(appid, profile, os.path.basename(path), data, src=path)
    return {"meta": meta, "warning": warning, "outcome": "saved"}


def apply_profile(reg, appid, profile):
    """프로필을 제자리에 적용한다 — 한 방향이다(저장된 프로필 → 게임 설정 파일).

    적용은 프로필 슬롯을 어떤 경우에도 덮어쓰지 않는다(A11). 되쓰기를 넣으면 직전 적용과 같은
    프로필일 때 「방금 바꾼 값 → 그 슬롯 → 다시 디스크」가 되어 파일이 한 바이트도 안 바뀐다.
    """
    appid = str(appid)
    entry = game_or_fail(reg, appid)
    path = entry["config_path"]
    check_path(appid, path)                                # G11

    if running_game(appid):                                # G5
        raise Refused(
            "거부: 게임이 실행 중입니다. 게임을 완전히 종료한 뒤 적용하십시오.\n"
            "  (실행 중에 교체하면 게임이 종료하면서 덮어써 아무 효과가 없습니다.)",
            code=codes.GAME_RUNNING
        )

    target_meta = store.load_meta(appid, profile)
    # meta가 truthy 비-dict(손상 JSON: `[..]`·`"str"`·`42`)면 「미저장」이 아니라 손상이다(§14-E″ ⓑ).
    #   `store.profile_file_path`가 isinstance 게이트로 `None`을 주므로 아래 PROFILE_MISSING으로
    #   샐 수 있는데, 그것은 실재하는 손상을 「아직 저장 안 됨」으로 오표기한다. 여기서 가른다.
    if target_meta and not isinstance(target_meta, dict):
        raise Refused("거부: 프로필 '%s'의 기록이 손상되었습니다 (저장소 손상)." % profile,
                      code=codes.PROFILE_CORRUPT)
    target_file = store.profile_file_path(appid, profile)
    if not (target_meta and target_file and os.path.exists(target_file)):
        raise Refused("거부: 프로필 '%s'이 없습니다. 먼저 save 하십시오." % profile, code=codes.PROFILE_MISSING)
    target_data = store.read_bytes(target_file)
    if store.sha1_bytes(target_data) != target_meta.get("sha1"):
        raise Refused("거부: 프로필 '%s'의 내용이 메타와 어긋납니다 (저장소 손상)." % profile, code=codes.PROFILE_CORRUPT)

    notes = []
    # 적용 직전에 sticky 학습을 넣지 않는다. 일반 흐름이 적용 → 플레이 중 조정 → 다시 적용이라,
    # 여기서 학습하면 사용자가 방금 바꾼 값을 게임이 되돌린 값으로 흡수한다.

    # 적용 직전에 현재 디스크를 `last_applied` 슬롯으로 되쓰지 않는다(A11). 직전 적용 기록은
    # 현재 파일의 정체를 증명하지 못한다 — 게임 업데이트·수동 복원·클라우드 동기화가 모두 그
    # 기록을 거짓으로 만든다.
    # `state`는 아래 백업 조건이 쓴다.
    state = disk_state(reg, appid)

    # ---- 적용
    #
    # 적용할 프로필의 온전성은 자기 자신의 meta로만 판정한다(sha1은 위에서 이미 대조).
    # 현재 디스크와 크기·줄 수를 비교하면 두 프로필이 정상적인 이유로 크게 다를 때 전환 자체가
    # 영구히 거부된다 — 그건 이 툴이 하려는 일 그 자체다.
    check_sanity(target_data, what="적용할 프로필")               # G4
    # ---- 대피본은 이 파일에만 있는 내용일 때만 만든다
    #
    # 디스크가 어느 슬롯과 같으면 그 내용은 이미 슬롯에 보존돼 있다. 그때도 백업하면 10칸 링
    # (`store.BACKUP_KEEP`)을 1칸 태우고, 그만큼 정작 되돌려야 할 지점이 밀려 사라진다
    # (`apply_all`의 `already` 갈래가 같은 근거로 같은 판단을 한다).
    # 그러나 `state`는 위 `disk_state` 호출에서 잰 값이고 쓰기는 아래 `store.atomic_write`다.
    #   그 사이에 게임·클라우드가 파일을 고유값으로 바꾸면 어느 슬롯에도 백업에도 없는 내용을
    #   덮게 된다. 그래서 쓰기 직전에 다시 확인한다 — 비용은 sha1 1회뿐이다(파일은 어차피
    #   여기서 다시 읽는다).
    if state["exists"]:
        # read_bytes와 그것을 쓰는 조건문까지 블록째 try 안이다(§14-E″ ⓒ · `restore_backup`의
        #   같은 자리와 동형). 읽을 수 없는 설정 파일(권한·EIO)의 `OSError`가 try 밖이면
        #   `UNEXPECTED`로 새는데, 이 대피가 실패하면 뒤의 쓰기(`atomic_write`)에 도달하지 않으므로
        #   실패 사유는 `BACKUP_FAILED`이고 문구 "원본은 그대로입니다"가 전 갈래에서 참이다.
        try:
            disk_data = store.read_bytes(path)
            if not state["matches"] or store.sha1_bytes(disk_data) != state["sha1"]:
                store.make_backup(appid, disk_data, store.KIND_DISK, os.path.basename(path))
        except OSError as exc:                               # G13
            raise Refused("거부: 백업에 실패해 적용을 중단했습니다 (%s). 원본은 그대로입니다." % exc, code=codes.BACKUP_FAILED)

    # 기존 파일의 권한과 소유권을 임시 파일에 이어받도록 요청한다. 소유권 복원 실패는
    # `store.atomic_write`가 비치명으로 취급하므로, owner 전달이 보존 성공을 보장하지는 않는다.
    mode = None
    owner = None
    try:
        info = os.stat(path)
        mode = info.st_mode & 0o777
        owner = (info.st_uid, info.st_gid)
    except OSError:
        pass
    store.atomic_write(path, target_data, mode, owner)            # G9

    entry["last_applied"] = profile
    entry["applied_sha1"] = store.sha1_bytes(target_data)
    entry["last_learn_sha1"] = None
    return {"notes": notes, "sha1": entry["applied_sha1"]}


#: apply_all의 게임별 결과 코드. 화면이 이 문자열로 분기한다(`src/rpc.ts`의 `Outcome`).
BULK_OUTCOMES = ("applied", "already", "no_profile", "refused", "error")


def apply_all(reg, profile):
    """등록된 모든 게임에 같은 프로필을 적용한다. 게임별 결과 목록을 돌려준다.

    하나가 실패해도 나머지를 계속 진행한다. 모드를 바꿔 부팅한 상황에서 "5개 중 2개만 바뀌고
    멈췄다"는 결과는 아무것도 안 한 것보다 나쁘다 — 어디까지 됐는지 모르는 채로 게임에 들어가게
    된다. 그래서 중단하지 않고, 대신 무엇이 안 됐는지를 전부 돌려준다. 호출자는 이 목록을 반드시
    사용자에게 보여줘야 한다.

    반환: `[{"appid", "name", "outcome", "code", "note"}]`. `outcome`은 `BULK_OUTCOMES` 중 하나다.
    `code`는 `refused`/`error`일 때만 값이 있고 나머지는 `None`이다.
    게임은 appid 정렬 순서로 처리한다. 화면 목록의 이름순과 같은 순서는 보장하지 않는다.

    저장은 하지 않는다. 레지스트리 영속화는 호출자의 몫이다.
    """
    results = []
    for appid in sorted(reg["games"]):
        entry = reg["games"].get(appid)
        # row 조립은 게임별 try 밖이다. 비-dict 항목에서 `entry.get`이 여기서 죽으면 루프가
        #   통째로 무너지므로 이름만 안전하게 접는다 — 손상 판정·거부는 try 안의
        #   `game_or_fail`이 `Refused(REGISTRY_ENTRY_CORRUPT)`로 낸다(§14-H).
        name = entry.get("name") if isinstance(entry, dict) else None
        row = {"appid": appid, "name": name or appid,
               "outcome": "error", "note": "", "code": None}
        results.append(row)

        # 게임 하나의 처리 전체를 감싼다 — 실패 지점이 어디든 그 게임만 실패해야 한다.
        try:
            meta = store.load_meta(appid, profile)
            if not meta:
                row["outcome"] = "no_profile"
                row["note"] = "프로필 '%s'을 아직 만들지 않았습니다." % profile
                continue

            # ---- 이미 그 프로필이면 쓰지 않는다. 성능이 아니라 안전 때문이다.
            #
            # 백업은 게임당 10개 링이고(`store.BACKUP_KEEP`) 한 칸이 쌓일 때마다 오래된 것이
            # 잘려 나간다. 디스크가 이미 그 프로필이면 이 경로는 0개를 쌓는다 — "적용 한 번마다
            # 최소 1개가 쌓인다"고 적지 않는 이유가 바로 아래 `already` 갈래다.
            # `apply_profile`의 `state["matches"]`와는 다른 술어다: 저쪽은 "어느 슬롯이든
            #   같은가"이고 여기는 "지금 그 프로필인가"다. 뒤바꿔 읽으면 링 소모량을 반대로 센다.
            #   `src/limits.ts`가 화면 쪽에서 같은 사실을 적는다 — 두 자리가 어긋나면 화면이
            #   약속한 백업 수와 실제가 갈린다.
            # 일괄 적용은 이 툴에서 가장 자주 눌리는 버튼이 되므로, 아무것도 달라지지 않는
            # 재적용까지 백업을 쌓으면 정작 되돌려야 할 때 되돌릴 지점이 링 밖으로 밀려 사라진다.
            # 게임이 N개면 한 번에 N개가 동시에 밀린다.
            try:
                state = disk_state(reg, appid)
            except Exception:
                state = {}
            # 「이미 그 프로필」은 기록끼리(`state.sha1 == meta.sha1`) 맞대지 않고 본체 실측으로
            #   판정한다(§5-G · F4-8): meta가 B라는데 본체가 C·없음인 슬롯을 "이미 적용됨"이라
            #   말하면 손상을 고칠 자리를 침묵한다. `state.get`은 필수다 — `disk_state` 실패 시
            #   `state`가 `{}`라 직접 첨자는 `KeyError`다. 판정이 거짓이면 아래 정상 실행으로
            #   낙하하고, 대상 상태에 따라 PROFILE_CORRUPT·PROFILE_MISSING·error가 된다(새 outcome 없음).
            if store.slot_holds(appid, profile, state.get("sha1")):
                row["outcome"] = "already"
                _record_already(entry, appid, profile, meta)
                continue

            result = apply_profile(reg, appid, profile)
            row["outcome"] = "applied"
            row["note"] = "  ".join(result.get("notes") or [])
        except Refused as exc:
            row["outcome"] = "refused"
            row["note"] = str(exc).splitlines()[0]
            row["code"] = exc.code
        except Exception as exc:
            # 일부러 넓게 잡는다. 이 함수의 존재 이유는 "하나가 실패해도 나머지는 계속 간다"이고,
            # 그 약속은 예외 종류에 따라 깨지면 안 된다.
            # ★ 19판 — 이 자리에서 가장 흔했던 예외가 사라졌다: 레지스트리 항목 손상
            #   (`config_path` 결손·비-dict)은 이제 `game_or_fail`이 `Refused(REGISTRY_ENTRY_CORRUPT)`로
            #   내고, 그것은 위의 `except Refused` 갈래가 받아 `refused` + 그 코드로 보고한다
            #   (익명 `error`가 아니다). 이 절을 그래도 넓게 두는 이유는 남은 미지의 예외
            #   때문이다 — 알려진 사건을 자기 코드로 빼내는 것과 최후 그물을 없애는 것은 다른
            #   일이다(§15-D E52 ⓑ). 사람이 읽을 문장을 앞에 두고 예외는 괄호로 남긴다 —
            #   Game Mode엔 터미널이 없어 이 note가 유일한 단서다.
            row["outcome"] = "error"
            row["note"] = ("이 게임의 등록 정보를 처리하지 못했습니다. 다시 등록해 보십시오. "
                           "(%s: %s)" % (type(exc).__name__, exc))
            row["code"] = codes.UNEXPECTED
    return results


def _record_already(entry, appid, profile, meta):
    """디스크가 이미 목표 프로필과 같아 쓰지 않고 넘어갈 때 기록을 사실에 맞춘다.

    파일은 안 건드리지만 기록은 진짜 적용과 똑같이 맞춘다 — `apply_profile`이 쓰기 뒤에 넣는
    세 줄과 같은 값이다. 같은 결과에 두 가지 기록이 남으면 어느 쪽이 사실인지 말할 수 없다.
    `last_applied`는 개요 봉투로 나간다(`Plugin.get_overview` → `src/rpc.ts`의 `OverviewGame`).
    `last_learn_sha1`은 삭제된 학습 캐시의 잔재다 — 지금 이 값을 읽는 코드는 없고, 두 경로의
    기록 모양을 맞추려고 같이 비운다.
    """
    entry["last_applied"] = profile
    entry["applied_sha1"] = meta.get("sha1")
    entry["last_learn_sha1"] = None


def restore_backup(reg, appid, backup_path, target="config"):
    """백업을 되돌릴 곳으로 되돌린다. 되돌리기 전 그 자리의 현재 내용도 백업한다.

    `target="config"`          → 게임 설정 파일.
    `target="dock"|"internal"` → 그 프로필 슬롯.

    왜 새 함수가 아니라 인자인가: 복원 쓰기의 문은 이 함수 하나라는 것이 계약이고(`restore`
      모듈은 조회·판정만 한다), 그래서 G15(`assert_backup_in_root`)·G4(`check_sanity`)가 한
      문에 산다. 문을 둘로 만들면 언젠가 한쪽에 가드가 빠진다. 두 가드는 분기보다 앞에 있다.
    슬롯 복원은 실행 중을 거부하지 않는다: 프로필 슬롯은 게임이 읽지도 쓰지도 않는 플러그인
      데이터다. 거부하면 "게임 켜 둔 채 프로필만 되돌리기"라는 안전한 조작이 막힌다
      (선례 = `save_profile`은 실행 중 저장을 허용하고 경고만 싣는다).
    슬롯 복원은 `applied_sha1`·`last_learn_sha1`을 건드리지 않는다 — 디스크가 안 바뀌었다.
    """
    appid = str(appid)
    entry = game_or_fail(reg, appid)
    path = entry["config_path"]
    check_path(appid, path)
    assert_backup_in_root(appid, backup_path)             # G15
    if target == "config" and running_game(appid):
        raise Refused("거부: 게임이 실행 중입니다.", code=codes.GAME_RUNNING)
    if not os.path.exists(backup_path):
        raise Refused("거부: 백업 파일이 없습니다 — %s" % backup_path, code=codes.BACKUP_FILE_MISSING)
    data = store.read_bytes(backup_path)
    check_sanity(data, what="백업 파일")
    if target in ("dock", "internal"):
        # 대피 조건: meta가 dict이고 그 `filename`의 본체가 실재할 때만 대피한다.
        # 아니면 대피할 대상 자체를 특정할 수 없다.
        # 저장의 대피와는 조건이 다르다 — `save_profile`은 meta를 조건에 넣지 않고
        #   `store.evacuable_names`로 디렉터리를 열거한다. meta를 못 믿는 상태가 그쪽 갈래의
        #   전제라서 일부러 갈라 뒀다. 복원이 meta를 쓰는 이유는 다르다: 되돌릴 슬롯의
        #   이름을 유지해야 하기 때문이다.
        try:
            old = store.load_meta(appid, target)
        except (OSError, ValueError):
            # 복원은 망가진 상태를 되돌리는 경로다. 손상된 meta 하나로 그 경로가 막히면
            # 사용자에게 남는 수단이 없다(`restore._disk_state`와 같은 판단·같은 이유).
            old = None
        old_name = old.get("filename") if isinstance(old, dict) else None
        if not isinstance(old_name, str) or not old_name:
            old_name = None
        if old_name:
            old_file = store.profile_file_path(appid, target)
            if old_file and os.path.exists(old_file):
                try:
                    store.make_backup(appid, store.read_bytes(old_file),
                                      store.profile_tag(target), old_name)
                except OSError as exc:                    # G13 — 대피 실패면 아무것도 쓰지 않는다
                    # 적용·저장·삭제와 같은 코드(`BACKUP_FAILED`)로 나간다. 그대로 올려보내면
                    # 접착층에서 `UNEXPECTED`가 되고, 같은 실패가 경로마다 다른 사유로 보여
                    # 사용자가 원인과 다른 복구 안내를 받는다.
                    raise Refused("거부: 백업에 실패해 복원을 중단했습니다 (%s). 원본은 그대로입니다."
                                  % exc, code=codes.BACKUP_FAILED)
        # 슬롯 본체의 이름은 그 슬롯이 이미 쓰던 이름을 유지한다(모르면 설정 파일 이름 —
        # `save_profile`이 쓰는 값과 같다). 이름을 갈면 옛 본체가 고아로 남는다.
        store.write_profile(appid, target, old_name or os.path.basename(path),
                            data, src=backup_path)
        return {"restored": backup_path}
    if os.path.exists(path):
        try:
            store.make_backup(appid, store.read_bytes(path), store.KIND_DISK, os.path.basename(path))
        except OSError as exc:                            # G13 — 위 슬롯 갈래와 같은 문법
            raise Refused("거부: 백업에 실패해 복원을 중단했습니다 (%s). 원본은 그대로입니다."
                          % exc, code=codes.BACKUP_FAILED)
    store.atomic_write(path, data)
    entry["applied_sha1"] = store.sha1_bytes(data)
    entry["last_learn_sha1"] = None
    return {"restored": backup_path}
