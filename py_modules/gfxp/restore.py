"""복원 정책 — 백업 목록 조회와 복원 확인 판정.

이 모듈은 아무것도 쓰지 않는다. 조회와 판정만 하고, 복원 쓰기는 접착층이 엔진
`restore_backup`을 부른다 — G15(`assert_backup_in_root`)·G5(실행 중)·G4(온전성 검사)가 전부
그 엔진 한 문에 모여 있다. 문을 둘로 만들면 언젠가 한쪽에 가드가 빠진다.

되돌릴 곳은 백업의 종류가 정한다(`target_of`):
    · `profile_dock`·`profile_internal` → 그 프로필 슬롯. 게임 설정 파일은 건드리지 않는다
    · 그 밖(`disk`·`unknown`)           → 게임 설정 파일

경로 봉쇄는 함수 진입 직후 한 번이고, 술어는 삭제와 공유한다
(`remove._paths_in_position`). 복원이 지나는 `backups/<appid>`가 외부 링크면
`assert_backup_in_root`의 기준점(`realpath(backups_dir)`)이 같이 밀려나 링크 너머 아무 파일이나
"백업 폴더 안"이 된다 — 임의 파일을 게임 설정 파일로 복사할 수 있다. 삭제와 복원이 같은
경계를 봐야 한쪽만 약해지지 않는다.
"""
import logging
import os

from . import codes, confirm, engine, remove, store

_log = logging.getLogger("gfxp.restore")

#: 안전하지 않은 경로에 쓰는 고정 지문. 어떤 실제 파일도 읽지 않고 만들어진다 —
#:   조회 자체가 곧 경로 탈출인 상황을 없앤다.
_UNSAFE_FP = "unsafe"

#: 백업 파일명의 해석은 `store.parse_backup_id` 하나다. 정렬(`store.backup_order_key`)도
#:   태그별 중복 판정(`store.backup_holds`)도 그 파서를 지나므로 「형식 불명」의 정의가 한 벌이다.
#:   여기 남는 것은 그 kind로 무엇을 하는가(아래 되돌릴 곳)뿐이다.

#: 행 `kind` → 되돌릴 곳. 판정은 백엔드 한 곳이다 — 프론트는 이 값을 그리기만 한다.
#: `unknown`이 게임 설정 파일로 가는 것은 출처를 모르기 때문이다(더 놀랍지 않은 쪽).
_TARGET_OF_KIND = {"profile_dock": "dock", "profile_internal": "internal"}
TARGET_CONFIG = "config"


def target_of(backup_id):
    """그 백업 행을 복원하면 어디가 바뀌는가 — `"dock"|"internal"|"config"`.

    토큰 결박(`main._restore_scope`)·행 표시(`backup_rows`의 `target`)·엔진 인자
    (`engine.restore_backup`의 `target`)가 같은 값을 써야 한다. 세 곳이 각자 kind를 해석하면
    어긋난 순간 "확인한 곳과 다른 곳에 쓰기"가 된다.
    """
    return _TARGET_OF_KIND.get(store.parse_backup_id(backup_id)["kind"], TARGET_CONFIG)


def _display_identity(row):
    """화면이 실제로 찍는 조합. 지금 그 조합은 `stamp_label · filename`이다
    (`src/confirmSpecs.tsx`의 `evictNote`).

    표시 조합이 바뀌면 이 함수도 같이 바꾼다 — 여기가 화면보다 좁아지는 순간 "화면에서는 같아
    보이는데 백엔드는 다르다고 판정"이 되어 구분 번호가 안 붙는다. 반대로 넓으면 번호가 필요
    없는 곳에 붙을 뿐이라 안전하다.
    """
    return (row["stamp_label"], row["filename"])


def _mark_duplicates(rows):
    """같은 표기가 둘 이상이면 구분 번호(`dup`)를 붙인다.

    번호는 그 표기를 공유하는 행을 `store.backup_order_key` 오름차순으로 놓은 순번이다.
    이 순서는 파일명 속 벽시계 stamp·충돌 번호·파일명에서 유도되며 실제 생성순서를 보증하지
    않는다. 화면 목록은 같은 키의 내림차순이다. 번호는 행의 위치가 아니라 파일에 붙는다.
    """
    groups = {}
    for row in rows:
        groups.setdefault(_display_identity(row), []).append(row)
    for members in groups.values():
        if len(members) < 2:
            continue                                 # 유일한 표기에는 번호를 붙이지 않는다
        ordered = sorted(members, key=lambda r: store.backup_order_key(r["backup_id"]))
        for number, row in enumerate(ordered, 1):
            row["dup"] = number
    return rows


def ring_observe(appid, items=()):
    """백업 링을 한 번 나열해 축출 예고·링 지문·칸 수·실제로 쌓일 수를 같이 낸다 —
    `{"evicted": [...], "fingerprint": …, "count": N, "adding": K}`.

    `items`는 이 동작이 만들려는 백업들(`(tag, sha1)` 쌍)이다. 개수가 아니라 무엇을 만드는지를
    받는 이유: 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이 아무것도 쓰지 않으므로
    지워지는 백업도 없다. 그 판정은 링을 봐야 하는데 부르는 쪽에서 따로 하면 나열이 둘이 된다 —
    그래서 중복 판정도 이 한 번의 나열 안에서 하고, `adding`이 그 결과다.

    왜 한 번인가: 고지와 토큰 지문이 각자 링을 나열하면 그 두 관측 사이에 링이 도는 창이 생긴다.
    확인창은 옛 목록의 이름을 대고 토큰은 새 목록에 묶여, 2차 호출에서 그 토큰이 그대로 통과한다 —
    사용자가 승인한 이름과 실제로 지워지는 파일이 다른 상태다. 창이 좁아도 없는 창은 아니다.
    지문은 `adding`과 무관하게 링 전체의 이름 순서다: 축출이 0건이어도 링이 돌면 지문은 움직인다.
    `count`도 같은 나열에서 낸다 — 화면의 "현재 백업 N건"이 지문이 잰 링과 다른 순간의 링을 세면,
    같은 확인창 안에서 두 숫자가 서로 다른 시각을 가리킨다.
    안전하지 않은 경로는 읽지 않는다 — 고정 센티널과 빈 목록·0으로 접는다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return {"evicted": [], "fingerprint": _UNSAFE_FP, "count": 0, "adding": 0}
    entries = store.list_backups(appid)              # 나열은 여기 한 번이다
    names = [os.path.basename(p) for p in entries]
    observed = {"evicted": [],
                "fingerprint": store.sha1_bytes("\n".join(names).encode("utf-8")),
                "count": len(names),
                "adding": 0}
    if not items:
        return observed                              # 백업을 안 만드는 갈래는 지울 것도 없다
    # 고지가 보는 판정과 엔진이 집행하는 판정이 같은 함수여야 화면과 실제가 갈리지 않는다
    #   (`store.plan_backups` → `store.make_backup`).
    adding = len(store.plan_backups(entries, items))
    observed["adding"] = adding
    if adding <= 0:
        # 전부 중복 — 한 칸도 안 쓰므로 축출도 없다. 비용 단락이지 두 번째 규칙이 아니다:
        # `store._doomed_tail`도 `adding == 0`이면 빈 집합을 낸다(같은 답).
        return observed
    rows = []
    for name in names:                               # 먼저 링 전체를 만든다 (아래 이유)
        info = store.parse_backup_id(name)
        rows.append({"backup_id": name, "kind": info["kind"],
                     "stamp_label": info["stamp_label"], "filename": info["filename"],
                     "dup": 0})
    # 구분 번호는 링 전체를 보고 매긴 뒤 자른다 — 지워질 것만 보고 매기면, 쌍둥이 중 하나만
    #   지워질 때 번호가 안 붙어 화면이 남는 쪽까지 가리키는 이름을 댄다.
    _mark_duplicates(rows)
    # 꼬리는 `store._doomed_tail` 한 곳에서만 유도한다. 그 산술을 여기 한 벌 더 두면 값이
    #   같은 동안은 안 보이다가, 링 의미를 바꾸는 날 확인창이 약속한 축출과 실제로 지워지는
    #   파일이 갈린다.
    #   `rows`는 `names`(=`entries`)와 같은 순서로 만들었으므로 짝지어 거른다.
    doomed = store._doomed_tail(entries, adding)
    observed["evicted"] = [row for row, path in zip(rows, entries) if path in doomed]
    return observed


def evict_preview(appid, items):
    """이 동작이 `items`를 백업하려 할 때 실제로 지워질 파일들.

    `items` = `(tag, sha1)` 쌍들 = 만들려는 백업. 개수가 아닌 이유는 위 `ring_observe`에 있다
    (중복이면 안 만들고, 안 만들면 안 지운다).

    산출의 정본은 위 `ring_observe` 하나다. 이 함수는 그 위의 얇은 래퍼로, 축출 이름 목록만
    필요하고 지문은 필요 없는 자리가 쓴다 — 지금 소비자는 둘이다:
    `confirm.apply_all_evict_preview`(일괄 적용) · `remove.evict_on_delete`(전체 초기화).
    지문이 함께 필요한 자리(단일 게임 확인창 넷 = 저장·개별 적용·복원·등록 해제)는
    `ring_observe`를 지난다 — 여기를 한 번 더 부르면 관측이 둘로 갈린다.
    순서의 정본은 `store.backup_order_key` 하나이고, 표시 목록(`backup_rows`)도 그 순서를 쓴다.
    꼬리 산술의 정본은 `store._doomed_tail` 하나다 — 아래는 그 이유 설명이지 두 번째 규칙이
    아니다.
    `BACKUP_KEEP - adding`인 이유: 새 백업이 목록 맨 앞에 `adding`건 끼어들면 기존 항목이 그만큼
    밀린다. prune은 새 목록의 `[BACKUP_KEEP:]`을 지우므로, 지워지는 것은 지금 목록의
    `[KEEP-adding:]`이다. `adding`이 링보다 크면 지금 목록 전부가 지워진다 — 음수 슬라이스로
    뒤에서 세는 사고를 막으려고 0에서 자른다.
    항목은 고유 `backup_id`를 싣고 거기에 화면이 그릴 조각을 얹는다(봉투 계약 `EvictedRow`).
    id는 화면에 그리지 않는다 — 대상이 하나임을 증명하는 자리이고, 사람이 읽는 것은 조각 쪽이다.
    빈 `items`를 여기서 먼저 끊는다: 만들 것이 없는 게임에서 링을 나열하지 않는다(답은 어느
    쪽이든 `[]`다).
    """
    if not items:
        return []
    return ring_observe(appid, items)["evicted"]


def evict_digest(plan):
    """게임별 축출 대상(`(appid, [backup_id, …])` 목록)을 토큰에 묶을 한 문자열로 접는다.

    왜 개수가 아니라 대상인가: 다게임 토큰의 링 신호는 `remove._delete_fp`의 개수(`bk=%d`)뿐인데,
    포화 링이 한 칸 도는 동안 그 개수는 `store.BACKUP_KEEP`으로 불변이라 대상이 바뀌어도 낡은
    토큰이 통과한다. 개수는 지문이 아니라 요약이다.
    축출이 0건인 게임은 싣지 않는다 — 약속하지 않은 것은 재지 않는다.
    순서를 그대로 담는다: 목록 순서가 곧 "무엇이 먼저 잘리는가"라 순서가 바뀌면 대상이 바뀐 것과 같다.
    """
    body = "\n".join("%s=%s" % (appid, ",".join(ids)) for appid, ids in plan)
    return store.sha1_bytes(body.encode("utf-8"))


def ring_fingerprint(appid):
    """백업 링의 지문 — 지금 목록의 이름을 순서 그대로 잰다.

    개수가 아니라 순서 있는 이름 전체를 잰다: 포화 링에서는 개수가 `store.BACKUP_KEEP`으로
    불변인 채 대상만 바뀌므로 개수 신호로는 잡히지 않는다.
    산출은 `ring_observe` 한 곳이다. 확인창이 이름을 대는 자리에서는 이 함수를 따로 부르지
    않는다 — 고지와 지문이 각자 링을 나열하면 그 사이의 변화가 토큰에 구워진다. 여기 남는
    이유는 "링만 재고 싶은" 소비자(검사의 계측기)가 그 뜻을 이름으로 말할 수 있게 하려는 것이다.
    안전하지 않은 경로를 읽지 않는 것은 `ring_observe`가 이미 접기 때문이다.
    """
    return ring_observe(appid)["fingerprint"]


def _entries(appid):
    """복원 가능한 백업 파일의 실경로 목록. 링크는 뺀다.

    엔진 G15가 링크된 백업을 거부하므로, 링크를 목록에 실으면 누를 수는 있는데 항상 거부되는
    행이 생긴다 — 없는 조작을 권하지 않는다.
    """
    out = []
    for path in store.list_backups(appid):
        if os.path.islink(path):
            continue
        out.append(path)
    return out


def backup_count(appid):
    """`[백업 N]` 라벨이 쓰는 수. 백엔드가 센다 — 프론트는 다시 세지 않는다.

    안전하지 않은 경로는 조회하지 않고 0으로 접는다. `get_overview`는 registry의 games 키를
    그대로 도는데, 손상·수동 편집된 registry의 키는 route의 인자 검증(`_VALIDATORS`)을 한 번도
    지나지 않는다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return 0
    return len(_entries(appid))


def _slot_meta(appid, profile):
    """슬롯 meta를 dict일 때만 돌려준다. 손상·비객체·없음은 전부 `None`이다.

    복원은 망가진 상태를 되돌리는 경로라, 손상 하나로 조회가 죽으면 안 된다
    (`_disk_state`·`main._slot_view`와 같은 판단)."""
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _evacuation_source(appid, profile, meta):
    """복원이 대피시킬 바로 그 파일의 경로 — 없으면 `""`. 대피 판정의 정본은 여기 하나다.

    엔진 `restore_backup`의 슬롯 대피 조건과 같은 술어다: meta가 dict이고 그 `filename`이
    문자열이며 그 이름의 본체가 실재할 때만 대피가 일어난다. 화면이 약속하는 것("백업 한 칸을
    씁니다")과 엔진이 실제로 하는 일이 한 술어에서 나와야 어긋날 자리가 없다. 조건을 자리마다
    다시 적으면 한 자리에만 걸려, 확인창이 없는 프로필을 「…에 저장됨」이라 하고 쓰지도 않는
    링을 「한 칸 씁니다」라고 말한다.

    이 함수는 "대피할 파일이 무엇인가"까지만 답한다. 그 대피가 링에 칸을 쓰는가에는 조건이
    하나 더 붙는다 — 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이 아무것도 쓰지
    않는다. 부르는 쪽이 `store.plan_backups`로 그 한 조건을 마저 본다.
    `meta`를 인자로 받는다: 같은 판정 안에서 meta를 두 번 읽으면 그 사이의 변화로 두 답이
    갈릴 수 있다. 부르는 쪽이 이미 읽은 그 값을 그대로 쓴다.
    """
    name = meta.get("filename") if meta else None
    if not isinstance(name, str) or not name:
        return ""
    path = os.path.join(store.profile_dir(appid, profile), name)
    return path if os.path.exists(path) else ""


def target_sha1(reg, appid, target):
    """되돌릴 곳의 지금 내용 지문. 모르면 `None`.

    · `config` → 게임 설정 파일의 sha1(파일을 읽는다)
    · 슬롯     → 그 슬롯 본체 파일의 sha1

    기록(meta)이 아니라 본체를 읽는다. 이 값의 소비자 셋이 전부 "되돌릴 곳이 지금 무엇을 들고
    있는가"를 묻기 때문이다 — `already` 판정 · 목록의 `same_as_target` 배지 · 토큰 지문. 기록만
    믿으면 meta는 B라는데 본체가 C인 슬롯에서 셋 다 거짓이 되고, 복구 버튼이 "이미 같습니다"로
    끝나 손상된 슬롯을 못 고친다 — 복원은 바로 그 손상을 되돌리는 경로다.
    비용은 슬롯 본체 파일 1회 읽기다(목록당 대상별 1회 — `backup_rows`가 캐시한다).
    모르면 `None`이라 배지는 안 그려지고 `already`도 성립하지 않는다(안전한 방향).
    """
    if target == TARGET_CONFIG:
        # 조회 계열(§8-D · §14-H ⓚ): 손상 항목은 「모름」(`None`)에 합류시킨다 — 목록이 뜨고
        #   `already`·배지가 안 켜지는 안전한 방향이다. `sha1_file("")`의 우연한 접힘에 기대지
        #   않고 형을 직접 본다(비-dict entry는 `.get`이 죽으므로 isinstance로 먼저 가른다).
        entry = (reg.get("games") or {}).get(str(appid))
        config_path = entry.get("config_path") if isinstance(entry, dict) else None
        if not isinstance(config_path, str):
            return None
        return store.sha1_file(config_path)
    meta = _slot_meta(appid, target)
    name = meta.get("filename") if meta else None
    if not isinstance(name, str) or not name:
        return None
    return store.sha1_file(os.path.join(store.profile_dir(appid, target), name))


def backup_rows(reg, appid):
    """백업 목록 — `store.backup_order_key` 내림차순. 순수 조회, 아무것도 쓰지 않는다.

    이 순서는 파일명에서 유도되며 실제 나이·생성순서를 뜻하지 않는다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        _log.error("list_backups refused appid=%r stage=escape (backups 경로가 제자리가 아님)", appid)
        return []
    targets = {}                          # 대상 지문은 목록당 한 번만 잰다
    out = []
    for path in _entries(appid):
        name = os.path.basename(path)
        info = store.parse_backup_id(name)
        target = _TARGET_OF_KIND.get(info["kind"], TARGET_CONFIG)
        if target not in targets:
            targets[target] = target_sha1(reg, appid, target)
        current = targets[target]
        backup_sha = store.sha1_file(path)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0                      # 조회 실패는 표시값 0 — 목록 자체가 죽지는 않는다
        out.append({
            "backup_id": name,
            "kind": info["kind"],
            "stamp": info["stamp"],
            "stamp_label": info["stamp_label"],
            "filename": info["filename"],
            "size": size,
            "target": target,
            "same_as_target": bool(current and backup_sha and current == backup_sha),
        })
    return out


def _assert_in_position(appid):
    """0단계 — 모든 조회·판정보다 먼저다. 뒤에 두면 그 사이의 조회가 이미 링크를 따라간다:
    검사 자리가 늦으면 검사 앞의 동작이 곧 탈출 경로다."""
    if remove._paths_in_position(appid):
        return
    _log.error("restore refused appid=%r stage=escape (backups/profiles 경로가 제자리가 아님)", appid)
    raise engine.Refused(
        "거부: 이 게임의 백업 폴더가 데이터 루트 안 제자리가 아닙니다.\n"
        "  아무것도 복원하지 않았습니다.",
        code=codes.BACKUP_OUT_OF_ROOT, appid=str(appid), stage="escape")


def _disk_state(reg, appid):
    """`engine.disk_state` 조회 중 아래 예외 목록에 든 실패는 `None`으로 접는다.

    ★ 19판 — 그 경계가 닫혔다. 등록 항목 손상은 `engine.disk_state`의 `game_or_fail`이
    `Refused(REGISTRY_ENTRY_CORRUPT)`로 내고, 아래 `except`의 `engine.Refused`가 그것을 잡는다.
    즉 이 래퍼가 이제 항목 손상까지 「조회 실패」로 접는다.
    """
    try:
        return engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError, AttributeError, TypeError):
        return None


def _restore_fp(current, backup, ring):
    """복원 토큰 지문의 조립 규칙은 여기 하나다 — 관측은 부르는 쪽이 한다.

    `(되돌릴 곳의 sha1, 백업 파일 sha1 + 링 지문)`. 조회 실패는 `"absent"`로 적는다 —
    없음도 지문의 일부다(없다가 생기면 무효가 되는 쪽이 안전).

    왜 조립만 하는가: 이 값을 내는 자리가 둘이다 — `needs_confirm`(고지를 만들며 이미 잰 값으로
    낸다)과 `fingerprint`(새로 관측해 낸다, 검사의 오라클). 관측이 갈리는 것은 자리마다 재는
    시점이 달라 정상이지만, 조립 규칙까지 갈리면 검사가 초록인 채로 route의 토큰만 어긋난다.
    """
    return (current or "absent", "%s|ring=%s" % (backup or "absent", ring))


def needs_confirm(reg, appid, backup_id):
    """`(state, params, fingerprint)` — 3-상태 계약이다(불리언이 아니다). 판정 기준은 되돌릴 곳이다.

        "already"  되돌릴 곳이 이미 그 백업과 같다 → 접착층이 엔진을 부르기 전에 반환한다.
                   엔진 `restore_backup`에는 already 스킵이 없어(무조건 대피+쓰기) 낙하시키면
                   같은 행을 다시 누를 때마다 백업 링이 1칸씩 소모된다.
        "proceed"  되돌릴 곳이 비어 있다(설정 파일 없음 / 빈 슬롯) → 복원이 재생하는 것이라
                   잃을 것이 없다. 묻지 않는다 — 계약의 절반은 묻지 않는 것이다.
        "confirm"  내용이 다른 것을 덮어쓴다 → 확인 토큰을 요구한다.

    기준이 되돌릴 곳인 이유: 게임 설정 파일 하나만 보면 `profile_dock` 백업을 되돌리려는데
    설정 파일이 우연히 그것과 같을 때 무쓰기로 끝나고, 정작 되돌리려던 슬롯은 그대로다.
    실행 중 조기 거부는 `config` 대상에만 건다: 프로필 슬롯은 게임이 읽지도 쓰지도 않으므로
    거부할 이유가 없고, 거부하면 "게임 켜 둔 채 프로필만 되돌리기"가 막힌다. 집행의 문은 여전히
    엔진 G5 하나이고(여기는 예의상 조회) TOCTOU는 그 G5가 잡는다.
    축출 고지(`evicted`)는 대피가 실제로 일어나는 갈래에만 실린다. `already`·`proceed`·대피
    불가 갈래는 링을 쓰지 않으므로 지워질 파일도 없다.

    지문을 params와 함께 낸다. 고지를 만든 뒤 따로 관측하면 그 두 관측 사이의 변화가 토큰에
    구워져 영구히 안 보인다. 지금은 고지에 쓴 바로 그 관측값(되돌릴 곳의 sha1 · 백업 sha1 ·
    `ring_observe`)이 그대로 지문이 된다.
    지문은 `confirm` 갈래에서만 낸다(`already`·`proceed`는 `None`) — 토큰을 쓰지 않는 갈래라
    잴 것이 없고, 재면 링 나열이 매 조회마다 붙는다.
    지문은 봉투로 나가지 않는다 — `params`가 아니라 세 번째 반환값이다. 접착층이 `**params`로
    splat해도 화면 계약에 새 필드가 생기지 않는다(저장·삭제도 같은 모양이다:
    `confirm.needs_confirm` · `remove.delete_preview`).
    """
    appid = str(appid)
    _assert_in_position(appid)                       # 0단계
    # 보존 계열(§8-D · §14-H ⓚ): 비-dict + 슬롯 대상에서 오늘 나가던 `already` 성공을 지킨다 —
    #   검증을 끄고(`require_intact=False`) 비-dict를 `{}`로 접는다. 접기 뒤 config 갈래는 `""`
    #   → `os.path.exists("")` 거짓 → `proceed`로 나가고, 실제 쓰기는 여전히
    #   `engine.restore_backup`(`require_intact=True`)이 `REGISTRY_ENTRY_CORRUPT`로 거부한다.
    entry = engine.game_or_fail(reg, appid, require_intact=False)   # 미등록 → GAME_NOT_REGISTERED
    if not isinstance(entry, dict):
        entry = {}

    info = store.parse_backup_id(backup_id)
    target = _TARGET_OF_KIND.get(info["kind"], TARGET_CONFIG)
    if target == TARGET_CONFIG and engine.running_game(appid):    # 조기 거부 — 집행은 엔진 G5
        raise engine.Refused(
            "거부: 게임이 실행 중입니다. 게임을 완전히 종료한 뒤 복원하십시오.",
            code=codes.GAME_RUNNING, appid=appid)

    backup_path = os.path.join(store.backups_dir(appid), str(backup_id))
    backup_sha = store.sha1_file(backup_path)
    state = _disk_state(reg, appid)
    params = {
        "appid": appid,
        "backup_id": str(backup_id),
        "kind": info["kind"],
        "stamp": info["stamp"],
        "stamp_label": info["stamp_label"],
        "filename": info["filename"],
        "size": (os.path.getsize(backup_path) if os.path.exists(backup_path) else 0),
        # 되돌릴 곳 — 화면 문구도 토큰 결박(`main._restore_scope`)도 엔진 인자도 이 값 하나를 쓴다.
        "target": target,
        # 게임 설정 파일이 지금 어떤 상태인가 — 저장 확인창과 같은 4분류를 쓴다.
        # (슬롯 복원에서도 싣는다: "게임 설정 파일은 바뀌지 않습니다"를 말하는 화면의 재료다.)
        "disk_state": confirm._classify(state),
        # 이 복원이 백업 링에 한 칸을 쓰는가 — 화면의 「백업 한 칸을 씁니다」가 참인 조건이다.
        # 기본은 거짓이다: 약속은 그것이 참인 갈래에서만 켠다 — 없는 대피를 말하면 사용자는
        # 남아 있지도 않을 복구 지점을 믿는다.
        # 같은 내용이 이미 그 태그의 링에 있으면 거짓이다: 엔진이 아무것도 쓰지 않으므로 칸을
        #   안 쓴다. 그 내용이 백업에 있다는 사실은 여전히 참이지만, 이 필드가 말하는 것은
        #   "이 동작이 칸을 태우는가"다 — 안 태우면 축출도 없다(`evicted`도 빈다).
        # 이 값이 뜻을 갖는 것은 `confirm` 갈래다. `already` 응답에도 같은 params가 실려 오지만
        #   그 갈래는 아무것도 쓰지 않으므로 여기 실린 값을 근거로 삼지 말 것.
        "evacuates": False,
        "evicted": [],
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]

    if target == TARGET_CONFIG:
        config_path = entry.get("config_path") or ""
        if not os.path.exists(config_path):
            return "proceed", params, None           # 잃을 것이 없다(재생) — 대피도 없다
        # 이 sha1이 곧 되돌릴 곳의 지문이다(`target_sha1(reg, appid, "config")`와 같은 값·같은
        #   파일). 판정에 쓴 값을 그대로 토큰에 묶으므로 둘이 다른 시점을 볼 수 없다.
        disk_sha = store.sha1_file(config_path)
        if disk_sha and backup_sha and disk_sha == backup_sha:
            return "already", params, None
        # 엔진은 설정 파일이 있을 때만 그것을 대피시키고(`engine.restore_backup`의 config 갈래),
        # 같은 태그에 같은 내용이 이미 있으면 아무것도 쓰지 않는다. 화면의 「백업 한 칸을
        # 씁니다」는 칸을 쓸 때만 참이므로 그때만 켠다 — 이미 링에 있는 내용이면 잃는 것도 새로
        # 태우는 칸도 없다. 판정은 엔진의 무쓰기 갈래와 같은 술어(`store.backup_holds`)다.
        ring = ring_observe(appid, [(store.KIND_DISK, disk_sha)])
        # 고지·지문·대피 여부가 전부 그 한 나열에서 나온다 — `adding`이 0이면 링에 한 칸도 안
        #   쌓이므로 「백업 한 칸을 씁니다」도 거짓이고 지워질 것도 없다.
        params["evacuates"] = bool(ring["adding"])
        params["evicted"] = ring["evicted"]
        return "confirm", params, _restore_fp(disk_sha, backup_sha, ring["fingerprint"])

    # ---- 프로필 슬롯으로 되돌린다
    meta = _slot_meta(appid, target)
    name = meta.get("filename") if meta else None
    # 술어 하나가 두 문장을 함께 정한다:
    #   ⓐ 「복원 전에 지금의 내용도 백업으로 보관합니다 — 백업 한 칸을 씁니다」
    #   ⓑ 「덮어쓸 대상(현재 …): {saved_at}에 저장됨」
    #   기록은 있는데 그 이름의 본체가 없는 슬롯에서는 둘 다 거짓이다 — 엔진은 대피할 파일을
    #   못 찾아 링을 쓰지 않고, 덮어쓸 내용도 그 자리에 없다. 조건을 문장마다 따로 적으면
    #   한쪽에만 걸려 확인창이 없는 대피와 없는 저장 시각을 말한다.
    source = _evacuation_source(appid, target, meta)
    # 본체 sha는 여기서 한 번만 잰다. 이 값이 두 곳에 쓰인다 — 아래 `already` 판정의 「되돌릴
    #   곳의 지금 내용」(= `target_sha1(reg, appid, target)`과 같은 파일·같은 값)과, 대피가
    #   실제로 링을 쓰는지의 판정이다. 두 번 읽으면 그 사이의 변화로 두 답이 갈린다.
    slot_sha = store.sha1_file(source) if source else None
    # 대피가 링을 쓰는 조건은 본체가 있고 + 같은 태그에 같은 내용이 아직 없을 때다. 앞의
    #   조건은 여기서, 뒤의 조건은 아래 한 번의 링 나열이 함께 답한다 — 그 사이에서 반환하는
    #   갈래들은 링을 쓰지 않으므로 기본값 거짓 그대로 나간다.
    # 저장 시각은 그 기록이 가리키는 본체가 실재할 때만 그 자리의 내용을 설명한다.
    params["saved_at"] = (meta.get("saved_at") or "") if source else ""
    if not isinstance(name, str) or not name:
        if store.slot_body_exists(appid, target):
            # 기록이 손상됐고 실물은 남아 있다. 대피할 대상을 특정할 수 없으므로 확인창이 그
            # 사실을 말하고 묻는다 — 고지하고 묻기이지 모르면 막기가 아니다.
            # 되돌릴 곳의 지문은 `None`(=absent)이다: `target_sha1`도 여기서는 본체 이름을 못
            #   만들어 `None`을 낸다 — 그 값을 다시 재지 않고 그대로 쓴다.
            params["slot_unreadable"] = True
            return "confirm", params, _restore_fp(
                None, backup_sha, ring_observe(appid)["fingerprint"])
        return "proceed", params, None               # 빈 슬롯 — 잃을 것이 없다
    if not source:
        # 기록만 있고 실물이 없다. 묻는 것은 유지한다: 이 슬롯은 지금 깨져 있고, 복원은 그
        # 깨진 자리에 쓰는 동작이다(위의 빈 슬롯 갈래처럼 "잃을 것이 없다"고 단정할 근거가 없다).
        # 다만 위에서 `evacuates=False`·`saved_at=""`이 되었으므로 확인창은 없는 대피와 없는
        # 저장 시각을 말하지 않는다.
        # `source`가 비었다 = 그 이름의 본체가 없다 = `target_sha1`도 `None`이다(같은 술어).
        return "confirm", params, _restore_fp(
            None, backup_sha, ring_observe(appid)["fingerprint"])
    # 판정은 본체 실측이다(`target_sha1`과 같은 값·같은 파일). meta의 기록값으로 판정하면
    #   "기록은 B인데 본체는 C"인 손상 슬롯에서 `already`가 되어 복구 버튼이 그 자리에서
    #   막힌다 — 복원은 바로 그 손상을 되돌리려는 경로다.
    # 이 값이 곧 되돌릴 곳의 지문이다 — 판정과 토큰이 같은 관측을 쓴다. 지문을 여기서 다시
    #   관측하면 그 사이의 변화가 토큰에 구워진다. 위에서 잰 `slot_sha`가 그 관측이다.
    if slot_sha and backup_sha and slot_sha == backup_sha:
        return "already", params, None
    ring = ring_observe(appid, [(store.profile_tag(target), slot_sha)])
    # 중복이면 대피본이 안 생기므로 「백업 한 칸을 씁니다」도 축출도 없다 — 그 판정과 축출
    #   예고와 지문이 한 나열에서 같이 나온다.
    params["evacuates"] = bool(ring["adding"])
    params["evicted"] = ring["evicted"]
    return "confirm", params, _restore_fp(slot_sha, backup_sha, ring["fingerprint"])


def fingerprint(reg, appid, backup_id):
    """토큰에 묶을 상태 지문 `(되돌릴 곳의 sha1, 백업 파일 sha1 + 링 지문)`.

    · 대상 쪽: 확인창을 띄운 사이 그 자리의 내용이 바뀌면 무효가 된다(TOCTOU). 사용자가 본
      "무엇을 덮어쓰는가"가 이미 낡았기 때문이다. 그 자리는 대상에 따라 다르다 — 설정 파일이거나
      프로필 슬롯이다(`target_of`). 언제나 게임 설정 파일만 재면, 슬롯을 덮어쓰는 복원이 설정
      파일만 안 바뀌면 낡은 토큰으로 통과한다.
    · 백업 쪽: 발급~소비 사이 prune으로 같은 이름의 파일이 바뀌는 극단 케이스까지 잡는다.
    · 링 쪽: 확인창이 "이 백업이 지워집니다"라고 이름을 대고 승인을 받았으므로, 그 사이 링이
      돌면 승인 대상이 달라진다. 백업 지문과 같은 칸에 합성해 싣는다 — `main._consume`은 튜플
      전체 동등 비교만 하고 문자열을 되쪼개지 않으므로 합성이 안전하고, 슬롯을 늘리지 않아
      발급·소비 양쪽 계약이 한 줄도 안 바뀐다.

    조회 실패는 `"absent"`로 적는다 — 없음도 지문의 일부다(없다가 생기면 무효가 되는 쪽이 안전).

    복원 route는 이 함수를 부르지 않는다. route가 쓰는 지문은 `needs_confirm`이 고지를 만들며
    이미 잰 값으로 낸 것이다 — 여기를 다시 부르면 관측이 둘이 되어 그 사이의 변화가 토큰에
    구워진다. 이 함수는 "지금 이 조합의 지문은 무엇인가"를 새로 관측해 묻는 자리(검사의 사전
    조건·계측기)를 위해 남는다. 조립 규칙은 `_restore_fp` 한 곳이라 두 자리가 규칙으로 갈릴 수는
    없다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return _UNSAFE_FP, _UNSAFE_FP
    return _restore_fp(
        target_sha1(reg, appid, target_of(backup_id)),
        store.sha1_file(os.path.join(store.backups_dir(appid), str(backup_id))),
        ring_observe(appid)["fingerprint"])
