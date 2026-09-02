#!/usr/bin/env python3
"""G14/G15 — 등록 후보 거부 5갈래(코드 4종), 정상 통과, 백업 경계 거부를 검증한다.

등록 route는 `config_path`를 별도로 판정하지 않고 `engine.add_game`에 넘긴다. 엔진은 먼저
`check_path`로 대상 자체의 링크와 허용 경계 밖 실경로를 거부한 뒤, `assert_config_candidate`로
등록 후보가 될 수 없는 이름과 경로 성분을 거부한다.

이 파일의 CASES는 뒤쪽 G14만 직접 부른다. 실제 파일을 만들거나 열지 않으며, 경고
(`engine.config_candidate_warnings`)와 G11은 검증하지 않는다. G15는 백업 루트 밖 경로 한 건을 건다.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import codes, engine  # noqa: E402

APPID = "3489700"   # 이 값으로 prefix를 찾지 않는다 — G14·G15는 경로 문자열만 본다.

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
    # 오탐 방지 — 이것들은 통과해야 한다
    ("정상 UE 설정",
     "/home/deck/x/pfx/drive_c/users/steamuser/AppData/Local/SB/Saved/Config/GameUserSettings.ini",
     None),
    ("공백이 있는 Saved Games (savegames 세그먼트 아님)",
     "/home/deck/x/pfx/drive_c/users/steamuser/Saved Games/ACE/video.videosettings",
     None),
    ("이름에 backup이 들어간 **파일**(폴더가 아님)",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/settings.backup.ini",
     None),
    # 예약 이름 — 슬롯이 이미 쓰는 이름은 등록도 막는다.
    #   대피에서 거르는 집합과 등록 가능한 집합이 어긋나면, 그 차집합의 프로필이 대피 없이 사라진다.
    #   목록의 정본은 `store.is_byproduct` 하나다.
    ("슬롯 기록 이름 meta.json",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/meta.json",
     codes.RESERVED_NAME_REFUSED),
    ("옛 엔진 마커 이름 .applied",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/.applied",
     codes.RESERVED_NAME_REFUSED),
    ("쓰다 죽은 잔재 이름 .gfxprofile-tmp-*",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/.gfxprofile-tmp-ab12",
     codes.RESERVED_NAME_REFUSED),
    # 봉쇄가 아니라는 증거 — 점으로 시작하는 정상 설정 파일은 그대로 등록된다.
    #   `is_byproduct`가 막는 것은 점이 아니라 우리가 그 자리에 이미 쓰는 이름뿐이다.
    ("점으로 시작하는 리눅스 게임 설정 .gamerc",
     "/home/deck/x/pfx/drive_c/users/steamuser/Documents/G/.gamerc",
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
    """실사용 등록 게임이 하나도 막히지 않는가. 읽기 전용(registry.json만 읽는다)."""
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
