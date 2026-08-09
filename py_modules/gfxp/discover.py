"""설치된 게임과 설정 파일 후보를 자동으로 찾는다.

**왜 필요한가**: Game Mode에서는 온스크린 키보드가 자동으로 뜨지 않는다(Valve 버그).
그래서 appid와 경로를 손으로 입력하게 만들면 Game Mode에서 사실상 못 쓴다.
**타이핑을 없애는 것이 목적**이고, 그러려면 목록에서 고르게 해야 한다.

판정은 보수적으로 한다 — 확실한 것만 '확실'로 올리고, 애매하면 후보를 늘어놓고 사용자가 고르게 한다.
잘못 잡은 경로로 파일을 덮어쓰는 것보다 한 번 더 묻는 쪽이 싸다.
"""

import os
import re
import time

from . import engine

# tier 1 = 확실. Unreal Engine 표준 경로의 GameUserSettings.ini.
_STRONG = re.compile(r"/Saved/Config/Windows[^/]*/GameUserSettings\.ini$", re.I)

# tier 2 = 게임별로 확인된 이름들 (RESEARCH-2026-08-01.md의 전수조사 결과)
_KNOWN_NAMES = {
    "gameusersettings.ini",          # UE 계열 (비표준 경로에 있는 경우)
    "video.ini",                     # Assetto Corsa
    "video.videosettings",           # Assetto Corsa EVO (바이너리)
    "hardware_settings_config.xml",  # DiRT Rally 2.0
    "userconfigselections",          # Forza Horizon 6 (XML, 확장자 없음)
    "settings.nuts",                 # It Takes Two (JSON)
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
    """prefix 안에서 설정 파일 후보를 찾는다. 훑는 범위를 좁게 제한한다."""
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
    # 같은 tier 안에서는 **최근에 수정된 것이 위로** 온다.
    # 게임이 실제로 쓰고 있는 파일이 가장 최근에 수정된 것이기 때문이다 — ETS2처럼 같은 이름의
    # 설정 파일이 여러 군데 있는 경우(네이티브 시절 잔재·프로필 폴더·현재 prefix) 현재 쓰는 것을
    # 맨 위로 올려준다. **자동 확정은 여전히 하지 않는다** — 순서만 돕고 판단은 사용자가 한다.
    found.sort(key=lambda item: (item["tier"], -item["mtime"], len(item["path"])))
    return found


def mtime_label(candidate):
    """후보의 수정 날짜. 어느 것이 '요즘 쓰는 파일'인지 눈으로 판단할 근거가 된다."""
    stamp = candidate.get("mtime")
    return time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"


def discover(known_appids=()):
    """설치된 게임별 설정 파일 후보 목록.

    반환: [{appid, name, library, candidates[], confident, registered}] — 이름순 정렬.
    `confident`가 True면 tier 1 후보가 정확히 하나라 자동으로 잡아도 되는 경우다.
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
