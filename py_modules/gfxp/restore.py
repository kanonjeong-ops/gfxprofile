"""복원 정책 — 백업 **목록 조회**와 복원 **확인 판정**. 설계 정본 DESIGN-F6-F8 §2-A~§2-D.

### 왜 자기 파일에 사는가 — `confirm.py`·`remove.py`가 세운 선례 그대로
- `engine.py` → **diff fence 위반**. 엔진은 M1 실사용 코드와 기록된 diff 밖으로 안 움직인다
- `main.py`  → *"접착층은 정책 판단 금지"* 위반
→ **fence 밖의 새 파일**이 둘 다 피한다. 여기서는 기존 부품(`engine.game_or_fail`·
  `engine.running_game`·`store.list_backups`·`confirm._classify`)을 **조립만** 한다.

### ★ 쓰기의 문은 엔진 `restore_backup` **하나**다
이 모듈은 **아무것도 쓰지 않는다**(조회·판정뿐). 복원 자체는 접착층이 엔진을 부른다 —
그래서 G15(`assert_backup_in_root`)·G5(실행 중)·G4(크기 검사)가 전부 엔진 한 문에 남는다.

### ★ 복원은 **2단계 시맨틱**이다 (실물 사실 2 · `qa/test_restore_path.py`가 잠근 절차)
    ① `engine.restore_backup` → **디스크(게임 설정 파일)** 가 백업 내용이 된다
    ② `save_profile`          → 그 디스크 내용이 **프로필 슬롯**으로 들어간다
①만 하고 멈춘 상태도 정상이다(디스크만 복원). 화면이 ②를 후속 제안으로 잇는다.

### ★ 경로 봉쇄는 **함수 진입 직후(0단계)** 한 번, 술어는 P8과 **공유**한다
`remove._paths_in_position`이 profiles/슬롯/backups를 realpath로 풀어 **정확 위치**인지 본다.
복원 경로가 지나는 것은 `backups/<appid>`인데, 그 디렉터리가 외부 링크면
`assert_backup_in_root`의 기준점(`realpath(backups_dir)`)이 **같이 밀려나** 링크 너머 아무
파일이나 "백업 폴더 안"이 된다 — 즉 임의 파일을 게임 설정 파일로 복사할 수 있다.
술어를 새로 만들지 않는 이유: 삭제와 복원이 **같은 경계**를 봐야 한 쪽만 약해지는 일이 없다.
"""
import logging
import os
import re

from . import codes, confirm, engine, remove, store

_log = logging.getLogger("gfxp.restore")

#: `store.make_backup`이 붙이는 tag 전량. 이 목록 밖은 `unknown`으로 접는다.
#: (`profile_%s` 두 개 + 적용/복원 직전 대피본 `disk`.)
KIND_DISK = "disk"
KIND_UNKNOWN = "unknown"
KINDS = (KIND_DISK, "profile_dock", "profile_internal")

#: **stamp는 하이픈을 품는다**(`%Y%m%d-%H%M%S` = 8+1+6 = 15자). 첫 `-`로 자르면 깨진다 —
#: 고정폭으로 떼고 형태를 정규식으로 확인한다(설계 §2-C 경고).
_STAMP_LEN = 15
_STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$")
#: 같은 초 충돌 접미사 — `<stamp>-<tag>-<n>-<filename>`.
_SEQ_RE = re.compile(r"^(\d+)-(.+)$")

#: 안전하지 않은 경로에 쓰는 고정 지문. 어떤 실제 파일도 읽지 않고 만들어진다(P8 Codex #2 문법).
_UNSAFE_FP = "unsafe"


def parse_backup_id(backup_id):
    """백업 파일명 하나를 표시용 조각으로. **파싱은 백엔드가 한다**(프론트는 문자열을 안 쪼갠다).

    `<stamp>-<tag>[-<n>]-<filename>` → `kind` · `stamp` · `stamp_label` · `seq` · `filename`.
    형태가 안 맞으면 `kind="unknown"`, `stamp=""`, `filename=원본 이름 그대로` —
    화면은 kind 코드로 i18n 문구를 고르므로 미지 형식도 안전하게 그려진다.

    ⚠️ 남는 모호성: 파일명 자체가 `12-video.ini`처럼 시작하면 그 `12`가 충돌 접미사로 읽힌다.
      store의 명명 규칙에 내재된 모호성이라 여기서 해소할 수 없고, 영향은 **같은 초 안의
      표시 순서**뿐이다(복원 대상은 `backup_id` 전체 문자열로 지정되므로 오동작은 없다).
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


def _entries(appid):
    """복원 가능한 백업 파일의 실경로 목록. **링크는 뺀다.**

    엔진 G15가 `os.path.islink(backup_path)`를 그대로 거부하므로, 링크를 목록에 실으면
    누를 수는 있는데 항상 거부되는 행이 생긴다 — *없는 조작을 권하지 않는다*(QA R5 문법).
    """
    out = []
    for path in store.list_backups(appid):
        if os.path.islink(path):
            continue
        out.append(path)
    return out


def backup_count(appid):
    """`[백업 N]` 라벨이 쓰는 수. **백엔드가 센다**(프론트 재계산 금지 — counts와 같은 규칙).

    안전하지 않은 경로는 **조회하지 않고** 0으로 접는다(P8 Codex #2와 같은 센티널 문법) —
    `get_overview`는 registry의 games **키**를 그대로 도는데, 손상·수동 편집된 registry의
    키는 `_VALIDATORS`를 한 번도 지나지 않는다(`reset_all`이 걸렸던 바로 그 자리).
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return 0
    return len(_entries(appid))


def backup_rows(appid):
    """백업 목록 — **최신순**. 순수 조회, 아무것도 쓰지 않는다.

    ⚠️ **정렬은 여기서 명시한다.** `store.list_backups`의 역순 사전 정렬을 그대로 쓰면,
      같은 초 충돌 접미사(`<stamp>-<tag>-1-<파일명>`)가 원소 파일명과 비교돼 **사전순 ≠ 시간순**이
      된다(접미사 숫자 자리에 파일명 첫 글자가 오는 비교가 된다). (stamp, seq)로 잰다 —
      정렬 기준도 백엔드 한 곳이다(설계 §2-C).
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        _log.error("list_backups refused appid=%r stage=escape (backups 경로가 제자리가 아님)", appid)
        return []
    keyed = []
    for path in _entries(appid):
        name = os.path.basename(path)
        info = parse_backup_id(name)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0                      # 조회 실패는 표시값 0 — 목록 자체가 죽지는 않는다
        keyed.append((info["stamp"], info["seq"], name, {
            "backup_id": name,
            "kind": info["kind"],
            "stamp": info["stamp"],
            "stamp_label": info["stamp_label"],
            "filename": info["filename"],
            "size": size,
        }))
    keyed.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [row for _, _, _, row in keyed]


def _assert_in_position(appid):
    """0단계 — **모든 조회·판정보다 먼저다.** 뒤에 두면 그 사이의 조회가 이미 링크를 따라간다
    (P8 이탈 #3과 같은 근거: 검사 자리가 늦으면 검사 앞의 동작이 곧 탈출 경로다)."""
    if remove._paths_in_position(appid):
        return
    _log.error("restore refused appid=%r stage=escape (backups/profiles 경로가 제자리가 아님)", appid)
    raise engine.Refused(
        "거부: 이 게임의 백업 폴더가 데이터 루트 안 제자리가 아닙니다.\n"
        "  아무것도 복원하지 않았습니다.",
        code=codes.BACKUP_OUT_OF_ROOT, appid=str(appid), stage="escape")


def _disk_state(reg, appid):
    """`engine.disk_state`는 fence 대상이라 비-dict meta에서 AttributeError를 낸다(engine.py:306).
    복원은 **망가진 상태를 되돌리는 경로**라, 손상 meta 하나로 복원이 막히면 안 된다 —
    조회 실패(`None`)로 접는다. `main._disk_state_safe`와 같은 판단·같은 이유다."""
    try:
        return engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError, AttributeError, TypeError):
        return None


def needs_confirm(reg, appid, backup_id):
    """`(state, params)` — **3-상태 계약**이다(불리언이 아니다).

        "already"  디스크가 이미 그 백업과 같다 → 접착층이 **엔진을 부르기 전에 반환**한다.
                   엔진 `restore_backup`에는 already 스킵이 없어(engine.py:692-710 — 무조건
                   대피+쓰기) 낙하시키면 같은 행 [복원]을 다시 누를 때마다 **백업 링이 1칸씩
                   소모**된다. `apply_all`의 already와 같은 이유·같은 자리다.
        "proceed"  설정 파일이 없다 → 복원이 파일을 **재생**하는 것이라 잃을 것이 없다.
                   묻지 않는다(빈 슬롯 첫 저장과 동형 — 계약의 절반은 묻지 않는 것이다).
        "confirm"  내용이 다른 파일을 덮어쓴다 → 확인 토큰을 요구한다.

    ★ **실행 중 게임은 상태 판정 전에 조기 거부**한다(설계 §2-B-1). 엔진 G5가 확정적으로
      거부할 것을 확인창까지 통과시켜 토큰을 소각한 뒤 거부하는 것은 무의미한 마찰이다 —
      *확실히 거부될 확인을 사용자에게 시키지 않는다.* 집행의 문은 여전히 엔진 G5 하나이고
      (여기는 예의상 조회), 확인창 사이에 게임이 켜지는 TOCTOU는 그 G5가 같은 코드로 잡는다.
    """
    appid = str(appid)
    _assert_in_position(appid)                       # 0단계
    entry = engine.game_or_fail(reg, appid)          # 미등록 → GAME_NOT_REGISTERED
    if engine.running_game(appid):                   # 조기 거부 (§2-B-1)
        raise engine.Refused(
            "거부: 게임이 실행 중입니다. 게임을 완전히 종료한 뒤 복원하십시오.",
            code=codes.GAME_RUNNING, appid=appid)

    info = parse_backup_id(backup_id)
    backup_path = os.path.join(store.backups_dir(appid), str(backup_id))
    state = _disk_state(reg, appid)
    params = {
        "appid": appid,
        "backup_id": str(backup_id),
        "kind": info["kind"],
        "stamp": info["stamp"],
        "stamp_label": info["stamp_label"],
        "filename": info["filename"],
        "size": (os.path.getsize(backup_path) if os.path.exists(backup_path) else 0),
        # 덮어쓸 대상(=디스크)이 지금 어떤 상태인가 — 저장 확인창과 **같은 4분류**를 쓴다.
        "disk_state": confirm._classify(state),
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]

    config_path = entry.get("config_path") or ""
    if not os.path.exists(config_path):
        return "proceed", params                     # 잃을 것이 없다
    disk_sha = store.sha1_file(config_path)
    backup_sha = store.sha1_file(backup_path)
    if disk_sha and backup_sha and disk_sha == backup_sha:
        return "already", params
    return "confirm", params


def fingerprint(reg, appid, backup_id):
    """토큰에 묶을 상태 지문 `(디스크 sha1, 백업 파일 sha1)`.

    · 디스크 쪽: 확인창을 띄운 사이 게임이 설정을 다시 쓰면 무효가 된다(TOCTOU — `save_profile`
      과 같은 문법). 사용자가 본 "무엇을 덮어쓰는가"가 이미 낡았기 때문이다.
    · 백업 쪽: 발급~소비 사이 prune으로 **같은 이름의 파일이 바뀌는** 극단 케이스까지 잡는다.

    조회 실패는 `"absent"`로 적는다 — 없음도 지문의 일부다(없다가 생기면 무효가 되는 쪽이 안전).
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return _UNSAFE_FP, _UNSAFE_FP
    entry = (reg.get("games") or {}).get(appid) or {}
    disk = store.sha1_file(entry.get("config_path") or "") or "absent"
    backup = store.sha1_file(os.path.join(store.backups_dir(appid), str(backup_id))) or "absent"
    return disk, backup
