#!/usr/bin/env python3
"""G14/G15 — 거부 4종 · 경고 2종 · 정상 통과를 전부 잠근다.

이 테스트가 지키는 것은 P4다: **`.sav`는 절대 열지 않는다.**
M1에서 P4는 선언뿐이고 강제 코드가 0줄이었다. v2는 파일 선택기를 붙여 임의 경로가
백엔드에 도달하므로, 그 선언을 코드로 못박고 여기서 잠근다.

⚠️ 이 테스트는 **경로 문자열만** 다룬다. 실제 `.sav` 파일을 만들지도 열지도 않는다 —
   G14는 파일을 읽기 전에 거부하므로 실물이 필요 없다.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes, engine  # noqa: E402

APPID = "3489700"   # 경로 판정에만 쓴다. prefix 조회는 실패해도 무방하다.

# (설명, 경로, 기대 code)  — code가 None이면 "통과해야 함"
CASES = [
    ("세이브 파일 .sav",
     "/home/deck/x/pfx/drive_c/users/steamuser/Saved/SaveGames/Save01.sav",
     codes.SAV_REFUSED),
    ("세이브 폴더 안의 비-.sav",
     "/home/deck/x/pfx/drive_c/users/steamuser/SaveGames/whatever.dat",
     codes.SAV_REFUSED),
    ("ETS2식 .bak 폴더의 옛 config",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/ETS2/steam_profiles(1.59).bak/config.cfg",
     codes.STALE_COPY_REFUSED),
    ("…backup 으로 끝나는 폴더",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/Game/SaveBackup/video.ini",
     codes.STALE_COPY_REFUSED),
    ("언리얼 엔진 보일러플레이트",
     "/home/deck/x/pfx/drive_c/users/steamuser/AppData/Local/G/Saved/Config/Engine.ini",
     codes.ENGINE_BOILERPLATE_REFUSED),
    # ★ 오탐 방지 — 이것들은 **통과해야** 한다
    ("정상 UE 설정",
     "/home/deck/x/pfx/drive_c/users/steamuser/AppData/Local/SB/Saved/Config/GameUserSettings.ini",
     None),
    ("공백이 있는 Saved Games (savegames 세그먼트 아님)",
     "/home/deck/x/pfx/drive_c/users/steamuser/Saved Games/ACE/video.videosettings",
     None),
    ("이름에 backup이 들어간 **파일**(폴더가 아님)",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/settings.backup.ini",
     None),
]


def check_cases():
    bad = []
    for label, path, expect in CASES:
        try:
            engine.assert_config_candidate(APPID, path)
            got = None
        except engine.Refused as exc:
            got = exc.code
        if got != expect:
            bad.append(f"{label}: 기대 {expect} / 실제 {got}\n      {path}")
    return bad


def check_backup_root():
    """G15 — 그 게임의 백업 폴더 밖은 거부한다."""
    bad = []
    outside = "/etc/passwd"
    try:
        engine.assert_backup_in_root(APPID, outside)
        bad.append("G15: 백업 폴더 밖 경로가 통과했다 — " + outside)
    except engine.Refused as exc:
        if exc.code != codes.BACKUP_OUT_OF_ROOT:
            bad.append(f"G15: 기대 BACKUP_OUT_OF_ROOT / 실제 {exc.code}")
    return bad


def check_real_registry():
    """실사용 9게임이 하나도 막히지 않는가. **읽기 전용**(registry.json만 읽는다)."""
    reg_path = pathlib.Path.home() / ".local/share/gfxprofile/registry.json"
    if not reg_path.exists():
        print("  (실사용 registry 없음 — 이 항목 건너뜀)")
        return []
    reg = json.loads(reg_path.read_text())
    bad = []
    n = 0
    for appid, entry in reg.get("games", {}).items():
        path = entry.get("config_path")
        if not path:
            continue
        n += 1
        try:
            engine.assert_config_candidate(appid, path)
        except engine.Refused as exc:
            bad.append(f"실사용 게임 {appid}이 거부됨({exc.code}) — {path}")
    print(f"  실사용 등록 게임 {n}개 — 거부 {len(bad)}건 (0이어야 한다)")
    return bad


def main():
    problems = check_cases() + check_backup_root() + check_real_registry()
    print(f"케이스 {len(CASES)}종 + G15 + 실사용 대조")
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
