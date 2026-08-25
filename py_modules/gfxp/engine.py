"""엔진 — 정책과 가드가 전부 여기 있다.

설계 원칙:
  P1  설정 파일을 통째로 교체한다. 내용을 파싱하지 않는다 (형식이 게임마다 다르므로).
  P4  .sav는 절대 열지 않는다 (클라우드 동기화 + 진행 데이터 포함).
  가드는 전부 "거부·무동작" 방향이다 (fail-closed).
"""

import os
import re

from . import codes, discover, store


class Refused(Exception):
    """가드에 걸려 거부됨. 사용자에게 그대로 보여줄 수 있는 메시지를 담는다.

    v2 추가: `code`(codes.py의 상수)와 `params`. 메시지는 M1 그대로 한국어를 들고 있고,
    프론트는 **메시지를 파싱하지 않고** code로 번역문을 고른다.
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

    ★ **매니페스트 우선 2패스**다 (v2). 첫 매치를 그대로 돌려주면 안 된다 —
      게임을 SD로 옮기면 내장 라이브러리에 **빈 pfx 껍데기**가 남고, 라이브러리 순서상
      껍데기가 항상 먼저 잡힌다. 그러면 SD에 있는 진짜 설정 파일이 prefix 밖으로 판정돼
      `check_path`(G11)가 정상 파일을 거부한다(TEKKEN 7 389730 실재 사례).
      게임이 **지금 어디에 설치돼 있는가**는 `appmanifest_<appid>.acf`가 정한다.
      2차 패스는 M1과 같은 동작이라, 매니페스트를 못 찾는 경우의 결과는 바뀌지 않는다.
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
    """G11 — 심볼릭 링크 금지, prefix(없으면 홈) 밖 금지."""
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

    **줄 수 검사는 "거의 같아야 마땅한" 두 대상에만 건다.**
    프로필 간 차이는 크더라도 비정상이 아니다 — 서로 다른 것이 이 툴의 존재 이유다.
    (QA 반려 ①: 이 구분이 없어 정상적인 프로필 전환이 영구히 거부됐다.)
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
    """G14 — 통째 교체 대상이 될 수 없는 파일을 거부한다 (fail-closed). **v2 신설.**

    P4('.sav는 절대 열지 않는다')의 **유일한 강제 지점**이다. M1에서 P4는 선언뿐이고
    강제 코드가 0줄이었다 — discover가 후보로 안 내놓았을 뿐이고, v2는 파일 선택기를 붙여
    임의 경로가 도달한다.

    거부 사유는 **다섯**이고(아래 ①~⑤) **전부 '그 파일이 무엇인가'가 아니라 '무엇이 아닌가'로만
    판정한다.** ⚠️ **에러 코드로 세면 넷이다** — ①과 ②가 `SAV_REFUSED`를 공유한다. 여기서 세는
    것은 **갈래**이고, 코드를 세어 「넷」이라 읽으면 아래 번호와 어긋난다.
    '설정 파일처럼 보이는가'는 거부가 아니라 경고 사유다(config_candidate_warnings).
    그 구분이 없으면 이 기기 밖의 정상 게임이 막힌다.

    가드는 **이 문 하나에서만** 건다. 여러 곳에 흩으면 한 곳이 빠져 조용히 뚫린다.
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
    # ③ 낡은 사본 — discover가 순회에서 프루닝하던 규칙을 여기서 상속한다.
    #   이걸 등록하면 툴은 죽은 파일을 관리하고 게임이 실제로 읽는 파일은 영영 안 바뀐다.
    # ★ `".bak" in s`는 너무 넓다 — `com.bakery.game` 같은 정상 폴더까지 막는다(리뷰 3-1).
    #   막으려는 것은 **백업 폴더**이므로 `.bak`으로 끝나거나 경로 성분이 backup으로 끝나는 것만 본다.
    if any(s.endswith(".bak") or ".bak." in s or s.endswith("backup") for s in segs):
        raise Refused("거부: 백업·구버전 폴더 안의 파일입니다. 이것을 등록하면 게임이 실제로 읽는 "
                      "파일은 영영 바뀌지 않습니다 — %s" % path,
                      code=codes.STALE_COPY_REFUSED, path=path)
    if low in discover._EXCLUDE_NAMES:                       # ④ 엔진 보일러플레이트
        raise Refused("거부: 게임 엔진 내부 설정 파일입니다 — %s" % base,
                      code=codes.ENGINE_BOILERPLATE_REFUSED, path=path)
    # ⑤ 프로필 슬롯이 이미 쓰는 이름 — 목록은 `store.is_byproduct` **하나**다(설계 §14-G ⓒ).
    #   목록을 여기 다시 적으면 언젠가 한쪽만 늘어나고, "거르기는 하는데 등록은 되는" 이름이
    #   생긴다 — 그 교집합이 곧 ⓑ가 고친 결함이다(대피 없이 사라지는 프로필).
    # ★ 「무엇이 아닌가」 원칙 그대로다: *"설정 파일처럼 보이는가"*가 아니라
    #   *"우리가 그 자리에 이미 쓰는 이름인가"*다. 점으로 시작하는 이름을 막는 것이 아니라서
    #   `.gamerc` 같은 리눅스 게임의 정상 설정 파일은 그대로 등록된다.
    if store.is_byproduct(base):
        raise Refused("거부: 이 플러그인이 프로필 폴더에서 쓰는 이름이라 등록할 수 없습니다 — %s"
                      % base,
                      code=codes.RESERVED_NAME_REFUSED, path=path)


def config_candidate_warnings(appid, path):
    """등록은 허용하되 화면에 되묻게 만드는 신호. **거부가 아니다.** v2 신설.

    엔진 반환값에 싣지 않고 접착층이 따로 조회한다 — 경고는 정책이 아니라 표시이고,
    반환 구조를 바꾸면 M1과의 diff fence가 헐거워진다.
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
    """G15 — 복원은 **그 게임의 백업 폴더 안**만 읽는다. v2 신설.

    M1의 restore_backup은 backup_path에 check_path를 걸지 않아 파일시스템 어디든 읽어서
    게임 설정 파일에 쓸 수 있었다. RPC가 경로 대신 backup_id를 받게 바뀌었으므로 접착층에서는
    도달할 수 없지만, **엔진 자신이 그것을 보장해야** 다음 호출자가 생겨도 안전하다.
    """
    root = os.path.realpath(store.backups_dir(appid))
    real = os.path.realpath(backup_path)
    if os.path.islink(backup_path) or not real.startswith(root + os.sep):
        raise Refused("거부: 이 게임의 백업 폴더 밖 경로입니다 — %s" % backup_path,
                      code=codes.BACKUP_OUT_OF_ROOT, path=backup_path)


def detect_cloud_synced(appid, config_path):
    """G6 판정 — 설정 파일이 Steam 클라우드 동기화 대상인가.

    ① remotecache 항목과 **경로 세그먼트 전체 접미 일치**
       (basename 매칭은 오답을 낸다: ETS2는 클라우드가 추적하는 config.cfg와
        실제 그래픽 설정 config.cfg가 경로가 다른 별개 파일이다)
    ② ctime != mtime 이면 클라우드가 쓴 파일
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

def game_or_fail(reg, appid):
    entry = store.game(reg, appid)
    if not entry:
        raise Refused("거부: appid %s가 등록되어 있지 않습니다. 먼저 add 하십시오." % appid, code=codes.GAME_NOT_REGISTERED)
    return entry


def disk_state(reg, appid):
    """디스크의 현재 설정 파일이 어느 프로필과 일치하는지.

    ★★ `matches`는 *"이 내용은 저 슬롯에 **보존돼 있다**"*는 주장이다(2026-08-15 R14 #4).
      그래서 기록(meta)이 아니라 **본체 실측**까지 본 `store.slot_holds`로 판정한다. meta는
      B라는데 본체가 없거나 C인 슬롯을 "일치"라고 말하면, 그 위에서 `apply_profile`이
      **대피(백업)를 생략하고** 게임 설정 파일을 덮어 **마지막 온전한 사본이 사라진다.**
      모르면 `None`(=일치 없음)이라 항상 고지·대피 쪽으로 접힌다.
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
    assert_config_candidate(appid, real)                  # G14 (v2 신설)
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

    반환의 `outcome`은 두 값이다 — `"saved"`(실제로 캡처했다) / `"already"`(**한 바이트도
    쓰지 않았다**). 아래 무쓰기 분기 주석이 그 계약의 정본이다.
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
        # ★ 기록이 dict가 아니어도(`[1,2]`·`"str"`·`42`) **본체는 있을 수 있다**. 여기서 접지
        #   않으면 아래 `old.get(...)`이 AttributeError를 내고, 확인창을 띄워 승인까지 받은
        #   저장이 `UNEXPECTED`로 죽는다 — 묻기는 하고 못 고치는 상태다. 판정은 이미 meta가
        #   아니라 본체(`store.evacuable_names`)가 하므로, 못 믿는 기록은 **비운 것과 같이**
        #   다루면 된다(`confirm.needs_confirm`의 같은 줄과 같은 모양·같은 이유).
        old = {}
    # 같은 슬롯의 이전 캡처와 크기만 대조한다. 줄 수까지 묶으면 게임 업데이트로
    # 옵션 항목이 늘어난 정상 캡처가 거부된다.
    # ★ 기준값은 **기록이 본체와 맞을 때만** 쓴다(사용자 결정 D8, 2026-08-23). 기록의 `size`는
    #   본체와 **다른 세대**를 가리킬 수 있고(디렉터리 fsync를 비치명으로 낮춘 뒤로 본체·기록의
    #   쌍 원자성이 더 낮다 — `store.atomic_write`), 그 값으로 가드가 돌면 **멀쩡한 저장이
    #   `SIZE_OUT_OF_RANGE`로 거부된다.** 이 프로젝트가 한계로 남긴 것들과 달리 **막는 방향**이다.
    # ★ 맞지 않으면 **크기 대조만 건너뛴다 — 거부하지 않는다.** 믿을 수 없는 기준을 만났을 때
    #   막는 쪽으로 가면 사용자가 그 프로필에서 빠져나올 길이 없다(설계 §14-G ⓐ와 같은 판단).
    #   빈 파일 거부(`FILE_EMPTY`)와 그 앞의 경로 가드는 **그대로 돈다.**
    # ★ 판정은 **아래 무쓰기 분기와 같은 술어**다(`store.slot_holds` — 판정을 두 벌로 적지 않는다,
    #   R14 #4·#5). 기록이 가진 sha1·파일명으로 물으면 그 술어가 곧 *"기록이 본체와 맞는가"*가 된다.
    #   ⚠️ 그 술어는 meta를 **다시 읽는다.** 그 사이 기록이 바뀌면 거짓이 나와 대조를 건너뛰므로,
    #     두 번 읽기가 갈리는 방향은 **항상 안전한 쪽**이다.
    trusted = store.slot_holds(appid, profile, old.get("sha1"), old.get("filename"))
    check_sanity(data, old.get("size") if trusted else None, None,
                 what="현재 설정 파일")                                      # G4

    # ---- 달라지는 것이 없으면 **아무것도 쓰지 않는다** (R13 — 설계 §14-B 링 보존)
    #
    # 저장은 슬롯을 덮기 전에 이전 내용을 대피시키는데(바로 아래), 그 대피본은 게임당 10칸짜리
    # 링(`store.BACKUP_KEEP`)을 한 칸 태우고 **가장 오래된 복구 지점을 밀어낸다.** 내용이 이미
    # 같으면 얻는 것 없이 그 손실만 남는다 — `apply_profile`이 "이 파일에만 있는 내용일 때만
    # 대피"로 정한 것과 같은 근거이고(§14-B), 사용자 쪽에서 보면 **아무것도 안 바뀌는 동작이
    # 복구 지점 하나를 조용히 먹는** 고지 없는 손실이다. `saved_at`도 같이 지킨다: 실제로
    # 캡처한 적 없는 시각이 찍히면 "언제 저장한 프로필인가"가 거짓이 된다.
    # ★ 판정은 **지금 읽은 바이트**로 한다(route가 미리 잰 값이 아니라). 재는 시점과 쓰는 시점
    #   사이에 게임·클라우드가 파일을 바꿔도 결론이 어긋나지 않는다 — `apply_profile`이 쓰기
    #   직전에 다시 확인하는 것과 같은 문법이다.
    # ★ 기록이 아니라 **슬롯의 실물**과 대조한다: meta만 믿으면 본체가 깨졌거나 사라진 슬롯에서
    #   "이미 같다"며 넘어가 **재저장으로 고칠 길이 사라진다.** 파일명이 달라진 경우도 쓴다 —
    #   그때는 슬롯에 남는 파일 이름이 실제로 바뀌므로 "달라지는 것이 없다"가 거짓이다.
    # ★ 판정은 **공용 술어 한 곳**이다(`store.slot_holds`) — 적용의 "다른 슬롯에 보존됨"과
    #   복원의 "이미 같다"가 같은 질문을 각자 답하다 서로 어긋났던 자리다(R14 #4·#5).
    if store.slot_holds(appid, profile, store.sha1_bytes(data), os.path.basename(path)):
        # 실행 중 경고도 싣지 않는다 — 저장 자체가 없었으므로 "지금 캡처하면"이 성립하지 않는다.
        return {"meta": old, "warning": None, "outcome": "already"}

    warning = None
    if running_game(appid):
        # ★ 문장이 아니라 **코드**를 돌려준다(R14 #10). 백엔드가 한국어 문장을 실어 보내면
        #   영어 화면에 한국어가 그대로 붙는다(실제로 붙어 있었다 — `GamesPopup`이 성공 문구
        #   뒤에 이 값을 이어 그렸다). 문장은 화면이 현재 언어로 고른다.
        warning = codes.WARN_SAVE_WHILE_RUNNING
    # ---- 덮어쓰기 전, 슬롯의 **본체를 전부** 대피시킨다 (설계 §14-G ⓐ)
    #
    # ★★ 조건은 「기록이 있는가」가 **아니라** 「본체가 있는가」다. 예전에는 `if old:`였다 —
    #   슬롯의 `meta.json`이 없거나 `{}`·`null`·`0`·`""`이면 **정상 본체가 바로 옆에 있어도**
    #   *"빈 슬롯이라 잃을 것이 없다"*로 접어 **확인 없이·대피 없이** 덮었고, 그 프로필은
    #   슬롯에도 백업 링에도 안 남았다. 앱이 스스로 그 상태를 만드는 경로가 둘 실증됐다
    #   (새 슬롯 저장 중 meta 쓰기 실패 → 본체만 남음 / 삭제가 `rmtree`에서 중단).
    #   그 상태에서 화면은 「프로필 없음」이라 **사용자의 자연스러운 재저장이 곧 파괴 트리거**였다.
    # ★ 그래서 대피 대상은 meta가 아니라 **디렉터리 열거**로 얻는다(`store.evacuable_names`) —
    #   meta를 못 믿는 상태가 이 갈래의 전제인데 그 meta로 파일 이름을 만들면 같은 거짓을
    #   한 번 더 믿는 것이 된다.
    # ★ 본체가 여럿이면 **여럿 다** 대피한다. ⚠️ 그 상태를 **앱이 만들지는 않는다**(설계
    #   §15-D E34 — 2026-08-22 확인): 같은 appid 재등록은 `confirm.already_registered`가
    #   `ALREADY_REGISTERED`로 **거부**하므로 등록된 게임의 설정 파일명이 바뀌지 않고,
    #   슬롯 복원도 **그 슬롯이 이미 쓰던 이름을 유지**한다(`restore_backup`의 슬롯 갈래).
    #   그래도 목록으로 도는 이유는 밖에서 들어온 파일·중단된 삭제 잔재가 남을 수 있고,
    #   그때 **한 개만 대피시키면 나머지가 고지 없이 사라지기** 때문이다.
    #   확인창의 축출 예고도 **같은 목록**에서 산출된다
    #   (`confirm.needs_confirm`) — 세는 쪽과 지우는 쪽이 같은 함수를 돌아야 예고와 실제가 맞는다.
    # ★ 다만 **개수는 이 목록의 길이가 아니다**(설계 §14-G ⓔ): 같은 태그에 같은 내용이 이미
    #   있으면 `store.make_backup`이 아무것도 쓰지 않는다. 대피 대상은 그대로 전부지만 링에
    #   실제로 쌓이는 것은 그중 일부이고, 확인창은 `store.plan_backups`로 **그쪽**을 센다.
    #   ★ 단 **그 「이미 있는 사본」이 이번 동작에서 어차피 축출될 자리이면** `plan_backups`가
    #     쓰기를 허가한다(D1) — 그때는 중복이어도 새로 담긴다. 대피 대상은 어느 쪽이든 전부다.
    # ★ 그 판정을 **여기서 한 번** 내려 루프에 넘긴다(사용자 결정 D1). 호출마다 다시 재면 먼저
    #   쓴 대피본이 밀어낸 칸을 뒤 항목이 계속 근거로 믿어 **그 내용이 통째로 사라진다.**
    #   목록을 먼저 잡는 이유도 같다 — 세는 쪽과 도는 쪽이 다른 나열을 보면 계획이 어긋난다.
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
            # ★ **백업 호출만 좁게 잡는다**(R14 #7). 넓게 잡으면 다른 실패까지 삼켜
            #   `BACKUP_FAILED`가 거짓 사유가 된다. 접착층이 이 예외를 `PROFILE_META_CORRUPT`로
            #   오인하던 자리이기도 하다 — 사용자가 **원인과 다른 복구 안내**를 받았다.
            raise Refused("거부: 백업에 실패해 저장을 중단했습니다 (%s). 프로필은 그대로입니다."
                          % exc, code=codes.BACKUP_FAILED)
    meta = store.write_profile(appid, profile, os.path.basename(path), data, src=path)
    return {"meta": meta, "warning": warning, "outcome": "saved"}


def apply_profile(reg, appid, profile):
    """프로필을 제자리에 적용한다 — **한 방향이다**(저장된 프로필 → 게임 설정 파일).

    ★ 13판 A11(2026-08-15): 적용 과정에서 프로필 슬롯을 **어떤 경우에도** 덮어쓰지 않는다.
      12판까지 여기 있던 체크인(적용 직전 현재 파일을 직전 적용 슬롯에 되쓰기)은 삭제됐다 —
      실기에서 "적용을 여섯 번 눌렀는데 파일이 한 번도 안 바뀐" 원인이 그것이었다(설계 §14-A).
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
    target_file = store.profile_file_path(appid, profile)
    if not (target_meta and target_file and os.path.exists(target_file)):
        raise Refused("거부: 프로필 '%s'이 없습니다. 먼저 save 하십시오." % profile, code=codes.PROFILE_MISSING)
    target_data = store.read_bytes(target_file)
    if store.sha1_bytes(target_data) != target_meta.get("sha1"):
        raise Refused("거부: 프로필 '%s'의 내용이 메타와 어긋납니다 (저장소 손상)." % profile, code=codes.PROFILE_CORRUPT)

    notes = []
    # 여기 있던 sticky 학습 호출은 2026-08-03에 뺐다 — **오염의 가장 굵은 경로였다.**
    # 실사용 흐름이 "적용 → 플레이 → 인게임 조정 → 다시 적용"이라, 이 자리의 학습은 사용자가
    # 방금 손으로 바꾼 값을 매번 "게임이 되돌린 값"으로 집어삼켰다(M1-FIELD-ISSUES-2026-08-03.md).
    # 학습 코드 자체는 15판에서 삭제됐다(설계 §14-G ⓖ).

    # ---- 체크인은 13판에서 삭제됐다 (설계 §14-A · A11)
    #
    # 여기 있던 블록은 적용 **직전에** 현재 디스크를 `last_applied` 슬롯으로 되쓰고, 그 값을
    # 다시 디스크에 썼다. 직전 적용이 지금 적용과 같은 프로필이면 「방금 바꾼 값 → 그 슬롯 →
    # 다시 디스크」가 되어 **파일이 한 바이트도 안 바뀐다**(실기 6회 재현, 로그는 성공을 6회 찍었다).
    # 근본은 *직전 적용 기록이 현재 파일의 정체를 증명하지 못한다*는 것이다 — 게임 업데이트·
    # 수동 복원·클라우드 동기화가 같은 차이를 만든다.
    # `state`는 남긴다: 아래 백업 조건이 쓴다.
    state = disk_state(reg, appid)

    # ---- 적용
    #
    # 적용할 프로필의 온전성은 **자기 자신의 meta**로만 판정한다 (sha1은 위에서 이미 대조).
    # 현재 디스크(=직전 프로필)와 크기·줄 수를 비교하면, 두 프로필이 정상적인 이유로
    # 크게 다를 때 전환 자체가 영구히 거부된다 — 그건 이 툴이 하려는 일 그 자체다.
    check_sanity(target_data, what="적용할 프로필")               # G4
    # ---- 대피본은 **이 파일에만 있는 내용일 때만** 만든다 (설계 §14-B)
    #
    # 디스크가 어느 슬롯과 같으면 그 내용은 이미 슬롯에 보존돼 있다. 그때도 백업하면 10칸 링
    # (`store.BACKUP_KEEP`)을 1칸 태우고, 그만큼 **정작 되돌려야 할 지점이 밀려 사라진다**
    # (`apply_all`이 :594-601에서 이미 확정한 판단과 같은 근거다).
    # ⚠️ 그러나 `state`는 위(:497)에서 잰 값이고 쓰기는 아래(:544)다. 그 사이에 게임·클라우드가
    #   파일을 고유값으로 바꾸면 **어느 슬롯에도 백업에도 없는 내용**을 덮게 된다.
    #   그래서 **쓰기 직전에 다시 확인한다** — 비용은 sha1 1회뿐이다(파일은 어차피 여기서 다시 읽는다).
    if state["exists"]:
        disk_data = store.read_bytes(path)
        if not state["matches"] or store.sha1_bytes(disk_data) != state["sha1"]:
            try:
                store.make_backup(appid, disk_data, store.KIND_DISK, os.path.basename(path))
            except OSError as exc:                               # G13
                raise Refused("거부: 백업에 실패해 적용을 중단했습니다 (%s). 원본은 그대로입니다." % exc, code=codes.BACKUP_FAILED)

    # 권한과 소유자를 그대로 이어받는다. 소유자 보존은 Decky(백엔드가 root) 확장을 막지 않기 위함.
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


#: apply_all의 게임별 결과 코드. UI·CLI가 이 문자열로 분기한다.
BULK_OUTCOMES = ("applied", "already", "no_profile", "refused", "error")


def apply_all(reg, profile):
    """등록된 모든 게임에 같은 프로필을 적용한다. 게임별 결과 목록을 돌려준다.

    **하나가 실패해도 나머지를 계속 진행한다.** 모드를 바꿔 부팅한 상황에서 "5개 중 2개만
    바뀌고 멈췄다"는 결과는 아무것도 안 한 것보다 나쁘다 — 어디까지 됐는지 모르는 채로
    게임에 들어가게 된다. 그래서 **중단하지 않고, 대신 무엇이 안 됐는지를 전부 돌려준다.**
    호출자는 이 목록을 **반드시 사용자에게 보여줘야 한다**(UI는 결과 창, CLI는 표 출력).

    반환: `[{"appid", "name", "outcome", "code", "note"}]`. `outcome`은 `BULK_OUTCOMES` 중 하나다.
    `code`는 `refused`/`error`일 때만 값이 있다(`Refused.code` 또는 `codes.UNEXPECTED`) —
    나머지는 `None`이다. 화면이 "실행 중이라 못 했다"와 "프로필이 깨졌다"를 구분하려면 이게 필요하다.
    등록 순서가 아니라 **appid 정렬 순서**로 돈다 — UI의 게임 목록과 같은 순서라야
    결과를 대조할 수 있다.

    저장은 하지 않는다. 호출자가 `store.save_registry(reg)`를 부른다.
    """
    results = []
    for appid in sorted(reg["games"]):
        entry = reg["games"].get(appid) or {}
        row = {"appid": appid, "name": entry.get("name") or appid,
               "outcome": "error", "note": "", "code": None}
        results.append(row)

        # 게임 하나의 처리 전체를 감싼다 — 실패 지점이 어디든 **그 게임만** 실패해야 한다.
        try:
            meta = store.load_meta(appid, profile)
            if not meta:
                row["outcome"] = "no_profile"
                row["note"] = "프로필 '%s'을 아직 만들지 않았습니다." % profile
                continue

            # ---- 이미 그 프로필이면 **쓰지 않는다**. 성능이 아니라 안전 때문이다.
            #
            # 백업은 게임당 10개 링이고(store.BACKUP_KEEP) 한 칸이 쌓일 때마다 오래된 것이
            # 잘려 나간다.
            # ★ *"적용 한 번마다 최소 1개가 쌓인다"*고 적지 않는다 — **바로 이 분기가 그것을
            #   막는다.** 디스크가 이미 그 프로필이면 이 경로는 **0개**를 쌓는다(바로 아래
            #   `already` 갈래 = `state["sha1"] == meta["sha1"]`).
            #   ⚠️ `apply_profile`의 `state["matches"]`와 **다른 술어다** — 저쪽은 *"어느
            #   슬롯이든 같은가"*이고 여기는 *"지금 그 프로필인가"*다. 이 주석의 첫 판이
            #   그 둘을 뒤바꿔 적었다(QA R3 DEFECT-R3-01).
            #   `src/limits.ts`도 같은 사실을 적는다(*"적용만 반복 → 0개/회 → 대피본이
            #   밀리지 않는다"*). 이 주석이 한동안 그것과 정반대를 말했다(QA R2 ADVISORY-R2-02).
            # 일괄 적용은 이 툴에서 가장 자주 눌리는 버튼이 되므로,
            # 아무것도 달라지지 않는 재적용까지 백업을 쌓으면 **정작 되돌려야 할 때 되돌릴
            # 지점이 링 밖으로 밀려 사라진다.** 게임이 N개면 한 번에 N개가 동시에 밀린다.
            try:
                state = disk_state(reg, appid)
            except Exception:
                state = {}
            if state.get("sha1") and state["sha1"] == meta.get("sha1"):
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
            # **일부러 넓게 잡는다.** 이 함수의 존재 이유는 "하나가 실패해도 나머지는 계속
            # 간다"이고, 그 약속은 예외 **종류**에 따라 깨지면 안 된다. 좁게 잡았다가
            # 레지스트리 항목 손상(`KeyError: config_path`) 하나에 전체 루프가 죽었다
            # (QA 5라운드 R1). 그러면 UI는 결과 창조차 못 띄우고 멈추는데, **Game Mode엔
            # 터미널이 없어 사용자가 원인을 볼 방법이 아예 없다.**
            # 사람이 읽을 문장을 앞에 두고 예외는 괄호로 남긴다. 앞부분이 없으면 사용자는
            # `KeyError: 'config_path'`만 보고 무엇을 해야 할지 알 수 없고, 뒷부분이 없으면
            # 내가 원인을 못 찾는다 — **Game Mode엔 터미널이 없어 이 줄이 유일한 단서다.**
            row["outcome"] = "error"
            row["note"] = ("이 게임의 등록 정보를 처리하지 못했습니다. 다시 등록해 보십시오. "
                           "(%s: %s)" % (type(exc).__name__, exc))
            row["code"] = codes.UNEXPECTED
    return results


def _record_already(entry, appid, profile, meta):
    """디스크가 이미 목표 프로필과 같아 **쓰지 않고 넘어갈 때** 기록을 사실에 맞춘다.

    파일은 안 건드리지만 **기록은 진짜 적용과 똑같이** 맞춰야 한다. 둘 다 필요하다.

    1. `last_applied` — 이게 다른 프로필을 가리키고 있으면, 나중에 사용자가 인게임에서
       조정한 뒤의 체크인이 **그 조정을 엉뚱한 프로필에 써 넣는다**(G3는 "디스크가 다른
       프로필과 정확히 일치할 때"만 막아 주는데, 조정 후에는 그 조건이 이미 깨져 있다).
    2. `last_learn_sha1` — 학습 캐시의 잔재다. 학습 코드는 15판에서 삭제됐지만(설계 §14-G ⓖ)
       필드가 남아 있어, 기록을 진짜 적용과 같은 모양으로 맞춰 둔다.
    """
    entry["last_applied"] = profile
    entry["applied_sha1"] = meta.get("sha1")
    entry["last_learn_sha1"] = None


def restore_backup(reg, appid, backup_path, target="config"):
    """백업을 **되돌릴 곳**으로 되돌린다. 되돌리기 전 그 자리의 현재 내용도 백업한다.

    `target="config"`        → 게임 설정 파일(12판까지의 유일한 동작).
    `target="dock"|"internal"` → **그 프로필 슬롯**(설계 §14-C · 13판 신설).

    ★ 왜 새 함수가 아니라 인자인가: *"쓰기의 문은 이 함수 하나"*가 계약이고(restore.py:9-11)
      그래서 G15(`assert_backup_in_root`)·G4(`check_sanity`)가 한 문에 산다. 문을 둘로 만들면
      언젠가 한쪽에 가드가 빠진다. 두 가드는 **분기보다 앞**에 그대로 있다.
    ★ 슬롯 복원은 **실행 중을 거부하지 않는다**: 프로필 슬롯은 게임이 읽지도 쓰지도 않는
      플러그인 데이터다. 거부하면 *"게임 켜 둔 채 프로필만 되돌리기"*라는 안전한 조작이 막힌다
      (선례 = 실행 중 저장은 허용+경고, :452-455).
    ★ 슬롯 복원은 `applied_sha1`·`last_learn_sha1`을 **건드리지 않는다** — 디스크가 안 바뀌었다.
    """
    appid = str(appid)
    entry = game_or_fail(reg, appid)
    path = entry["config_path"]
    check_path(appid, path)
    assert_backup_in_root(appid, backup_path)             # G15 (v2 신설)
    if target == "config" and running_game(appid):
        raise Refused("거부: 게임이 실행 중입니다.", code=codes.GAME_RUNNING)
    if not os.path.exists(backup_path):
        raise Refused("거부: 백업 파일이 없습니다 — %s" % backup_path, code=codes.BACKUP_FILE_MISSING)
    data = store.read_bytes(backup_path)
    check_sanity(data, what="백업 파일")
    if target in ("dock", "internal"):
        # 대피 조건: **meta가 dict이고 그 `filename`의 본체가 실재할 때만** 대피한다.
        # 아니면 대피할 대상 자체를 특정할 수 없다(설계 §5-C ⓗ·E11).
        # ⚠️ 예전에는 이 줄이 *"`save_profile`과 같은 문법·같은 조건"*이라 적었는데 **거짓이었다**:
        #   저장의 대피는 meta를 조건에 넣지 않고 **디렉터리를 열거**한다(`save_profile`의
        #   `for name in store.evacuable_names(...)` 루프 — 지금 `:450-464`). meta를 못 믿는
        #   상태가 그쪽 갈래의 전제라서 일부러 갈라 둔 것이다(`:425` 주석이 그 근거의 정본).
        #   **복원이 meta를 쓰는 이유는 다르다** — 되돌릴 슬롯의 *이름*을 유지해야 하기 때문이다.
        try:
            old = store.load_meta(appid, target)
        except (OSError, ValueError):
            # 복원은 **망가진 상태를 되돌리는 경로**다. 손상된 meta 하나로 그 경로가 막히면
            # 사용자에게 남는 수단이 없다(restore._disk_state와 같은 판단·같은 이유).
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
                    # 적용·저장·삭제와 **같은 코드**로 나간다(R14 #7). 예전에는 이 예외가 그대로
                    # 올라가 접착층에서 `UNEXPECTED`가 됐고, 같은 실패가 경로마다 다른 사유로
                    # 보였다 — 사용자는 원인과 다른 복구 안내를 받는다.
                    raise Refused("거부: 백업에 실패해 복원을 중단했습니다 (%s). 원본은 그대로입니다."
                                  % exc, code=codes.BACKUP_FAILED)
        # 슬롯 본체의 이름은 **그 슬롯이 이미 쓰던 이름**을 유지한다(모르면 설정 파일 이름 —
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
