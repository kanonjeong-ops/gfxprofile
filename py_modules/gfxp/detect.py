"""모드 판정 — 이 파일 하나에 격리한다.

이 기기는 GPU 선택이 **부팅 시점에 확정**된다. all-ways-egpu가 부팅 때 /dev/dri/by-path를
몇 초 폴링해 primary를 정하고 끝내며, 재무장하는 udev 룰이 없다. 따라서 "지금 카드가 몇 개
꽂혀 있는가"는 판정 근거가 되지 못한다 — 부팅 후 eGPU를 꽂아도 그 세션은 계속 내장으로 그린다.

대신 부팅 시 기록되는 VULKAN_ADAPTER가 "이 게임이 어느 GPU로 그릴 것인가"를 직접 말해준다.
게임 프로세스가 이 값을 상속하므로, 프로필이 알아야 할 바로 그 정보다.

타 기기·타 eGPU 대응이 필요해지면 **이 파일 안에서만** 바뀌게 한다.
"""

import os
import re

MODE_DOCK = "dock"
MODE_INTERNAL = "internal"
MODE_UNKNOWN = "unknown"

DEFAULT_ENVD = "/etc/environment.d/00-vulkan-device.conf"
_ADAPTER_RE = re.compile(r"^\s*VULKAN_ADAPTER\s*=\s*(.+?)\s*$")


def envd_path():
    return os.environ.get("GFXPROFILE_ENVD") or DEFAULT_ENVD


def read_adapter():
    """(값, 출처)를 돌려준다. 못 찾으면 (None, None).

    환경변수를 먼저 본다 — 게임 프로세스가 실제로 상속하는 것이 그것이기 때문이다.
    """
    value = os.environ.get("VULKAN_ADAPTER")
    if value and value.strip():
        return value.strip(), "env"
    path = envd_path()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = _ADAPTER_RE.match(line)
                if match:
                    return match.group(1).strip().strip('"').strip("'"), path
    except OSError:
        pass
    return None, None


def by_path_cards():
    """/dev/dri/by-path의 카드 목록. **판정에 쓰지 않고 로그에만 남긴다.**

    all-ways-egpu는 'eGPU 카드 존재'가 아니라 'eGPU에 붙은 디스플레이 존재'로 판정한다.
    따라서 카드가 2개인데 VULKAN_ADAPTER는 내장인 상태가 정상적으로 존재하며,
    이를 불일치로 취급하면 정상 상황에서 unknown이 되어 툴이 과잉 차단된다.
    """
    directory = "/dev/dri/by-path"
    try:
        return sorted(n for n in os.listdir(directory) if n.endswith("-card"))
    except OSError:
        return []


def detect_mode(reg):
    """(mode, detail) 반환. detail은 사람이 읽을 판정 근거 한 줄."""
    override = reg.get("settings", {}).get("mode_override")
    if override:
        return override, "mode_override=%s (수동 지정이 자동 판정을 이깁니다)" % override

    adapter, source = read_adapter()
    if not adapter:
        # G1 — 신호 자체가 없다. 추측하지 않는다.
        return MODE_UNKNOWN, "VULKAN_ADAPTER를 찾을 수 없음 (%s 없음)" % envd_path()

    mode = reg.get("gpu_map", {}).get(adapter)
    if not mode:
        # G1 — 처음 보는 GPU. 등록 전까지 자동 경로는 전면 중단된다.
        return MODE_UNKNOWN, "VULKAN_ADAPTER=%s 가 gpu_map에 없음 (출처: %s)" % (adapter, source)

    return mode, "VULKAN_ADAPTER=%s -> %s (출처: %s)" % (adapter, mode, source)
