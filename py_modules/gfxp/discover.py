"""설치된 게임과 설정 파일 후보를 자동으로 찾는다.

Game Mode에는 온스크린 키보드가 자동으로 뜨지 않는다. appid와 경로를 손으로 치게 만들면
핸드헬드에서 못 쓰는 화면이 되므로, 목록에서 고르게 하는 것이 이 모듈의 존재 이유다.

판정은 보수적으로 한다 — 확실한 것만 확실로 올리고, 애매하면 후보를 늘어놓고 사용자가 고른다.
잘못 잡은 경로로 파일을 덮어쓰는 것보다 한 번 더 묻는 쪽이 싸다.
"""

import os
import re
import time

from . import engine

# tier 1 = 확실. Unreal Engine 표준 경로의 GameUserSettings.ini.
_STRONG = re.compile(r"/Saved/Config/Windows[^/]*/GameUserSettings\.ini$", re.I)

# tier 2 = 알려진 설정 파일 이름
_KNOWN_NAMES = {
    "gameusersettings.ini",
    "video.ini",
    "video.videosettings",
    "hardware_settings_config.xml",
    "userconfigselections",
    "settings.nuts",
    "graphicsoptions.xml",
    "graphicssettings.ini",
    "videoconfig.txt",
}

# tier 3 = 이름만으로는 확신할 수 없는 것들
_WEAK_SUFFIXES = (".ini", ".cfg", ".xml", ".json", ".conf")
_WEAK_HINTS = ("video", "graphic", "display", "setting", "option", "config")

# 엔진 보일러플레이트 — 사용자가 만지는 그래픽 설정이 아니다
_EXCLUDE_NAMES = {
    "engine.ini", "scalability.ini", "input.ini", "compat.ini", "game.ini",
    "deviceprofiles.ini", "hardware.ini", "crashreportclient.ini", "manifest.ini",
    "paper2d.ini", "niagara.ini", "controlrig.ini", "fullbodyik.ini",
    "apexdestruction.ini", "runtimeoptions.ini", "motosynth.ini", "synthesis.ini",
    "hairstrands.ini", "livelink.ini", "magicleap.ini", "physxvehicles.ini",
    "variantmanagercontent.ini", "editorscriptingutilities.ini",
    "magicleaplightestimation.ini", "win.ini", "system.ini",
}
_EXCLUDE_DIRS = {
    "crashreportclient", "crashes", "logs", "shadercache", "cache", "cmscache",
    "backup", "backup_savegames", "temp", "tmp", "webcache", "node_modules",
}

# prefix 안에서 훑을 뿌리들. 전체를 훑으면 느리고 쓸모없는 것만 나온다.
_SCAN_ROOTS = (
    "drive_c/users/steamuser/AppData/Local",
    "drive_c/users/steamuser/AppData/LocalLow",
    "drive_c/users/steamuser/AppData/Roaming",
    "drive_c/users/steamuser/Documents",
    "drive_c/users/steamuser/Saved Games",
)
_MAX_DEPTH = 6

_SKIP_NAME_PREFIXES = ("proton", "steam linux runtime", "steamworks common")


def _app_name(library, appid):
    path = os.path.join(library, "steamapps", "appmanifest_%s.acf" % appid)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = re.search(r'"name"\s+"([^"]*)"', line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return None


def _classify(path):
    """(tier, 이유) 반환. tier가 None이면 후보가 아니다."""
    name = os.path.basename(path).lower()
    if name in _EXCLUDE_NAMES:
        return None, None
    if _STRONG.search(path):
        return 1, "Unreal Engine 표준 경로"
    if name in _KNOWN_NAMES:
        return 2, "알려진 설정 파일 이름"
    lowered = name.lower()
    if lowered.endswith(_WEAK_SUFFIXES) and any(h in lowered for h in _WEAK_HINTS):
        return 3, "이름에 설정 관련 단어가 있음"
    return None, None


def _scan_prefix(prefix):
    """prefix 안의 설정 파일 후보 — `{path, tier, reason, size, mtime}` 목록."""
    found = []
    for relative in _SCAN_ROOTS:
        root = os.path.join(prefix, relative)
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip("/").count("/")
        for current, dirs, files in os.walk(root):
            if current.count("/") - base_depth >= _MAX_DEPTH:
                dirs[:] = []
                continue
            # 이름이 정확히 걸리는 것 + 백업 흔적(.bak, ~backup)을 통째로 쳐낸다.
            # ETS2는 `steam_profiles(1.59.1.0s).bak/` 같은 폴더에 옛 config.cfg를 잔뜩 남긴다.
            dirs[:] = [
                d for d in dirs
                if d.lower() not in _EXCLUDE_DIRS
                and ".bak" not in d.lower()
                and not d.lower().endswith("backup")
            ]
            for filename in files:
                path = os.path.join(current, filename)
                tier, reason = _classify(path)
                if tier is None:
                    continue
                try:
                    info = os.stat(path)
                except OSError:
                    continue
                if info.st_size == 0 or info.st_size > 4 * 1024 * 1024:
                    continue            # 빈 파일과 지나치게 큰 파일은 설정이 아니다
                found.append({
                    "path": path, "tier": tier, "reason": reason,
                    "size": info.st_size, "mtime": info.st_mtime,
                })
    # 같은 tier에서는 mtime 내림차순, 그다음 경로 길이순으로 정렬한다.
    # 순서만 돕는 휴리스틱이며 자동 확정에는 쓰지 않는다.
    found.sort(key=lambda item: (item["tier"], -item["mtime"], len(item["path"])))
    return found


def mtime_label(candidate):
    """후보의 수정 날짜."""
    stamp = candidate.get("mtime")
    return time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"


def discover(known_appids=()):
    """설치된 게임별 설정 파일 후보 목록.

    반환: [{appid, name, library, candidates[], confident, registered}] — 이름순 정렬.
    `confident`의 정의는 둘이다: tier 1이 정확히 하나거나, tier 1이 없고 tier 2 이하가 정확히 하나.
    """
    results = []
    for library in engine.steam_libraries():
        compat = os.path.join(library, "steamapps", "compatdata")
        if not os.path.isdir(compat):
            continue
        for appid in sorted(os.listdir(compat)):
            if not appid.isdigit() or appid == "0":
                continue
            prefix = os.path.join(compat, appid, "pfx")
            if not os.path.isdir(prefix):
                continue
            name = _app_name(library, appid)
            if name and name.lower().startswith(_SKIP_NAME_PREFIXES):
                continue                # Proton·런타임 도구는 게임이 아니다
            candidates = _scan_prefix(prefix)
            if not candidates:
                continue
            strong = [c for c in candidates if c["tier"] == 1]
            named = [c for c in candidates if c["tier"] <= 2]
            # 확실 = tier 1이 정확히 하나거나, tier 1이 없고 알려진 이름 후보가 정확히 하나.
            # tier 3(이름만 그럴듯한 것)뿐이면 절대 확실로 올리지 않는다 — ETS2가 그 경우이고,
            # 거기서 자동 선택은 '같은 이름 다른 파일' 함정에 그대로 빠진다.
            confident = len(strong) == 1 or (not strong and len(named) == 1)
            results.append({
                "appid": appid,
                "name": name or ("appid %s" % appid),
                "library": library,
                "candidates": candidates,
                "confident": confident,
                "registered": appid in known_appids,
            })
    results.sort(key=lambda item: item["name"].lower())
    return results


def best_candidate(entry):
    """확실한 경우의 자동 선택값. 확실하지 않으면 None (사용자가 골라야 한다)."""
    if not entry.get("confident"):
        return None
    for tier in (1, 2):
        for candidate in entry["candidates"]:
            if candidate["tier"] == tier:
                return candidate
    return None
