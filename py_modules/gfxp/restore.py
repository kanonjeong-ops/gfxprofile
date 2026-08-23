"""복원 정책 — 백업 **목록 조회**와 복원 **확인 판정**. 설계 정본 DESIGN-F6-F8 §2-A~§2-D.

### 왜 자기 파일에 사는가 — `confirm.py`·`remove.py`가 세운 선례 그대로
- `engine.py` → **diff fence 위반**. 엔진은 M1 실사용 코드와 기록된 diff 밖으로 안 움직인다
- `main.py`  → *"접착층은 정책 판단 금지"* 위반
→ **fence 밖의 새 파일**이 둘 다 피한다. 여기서는 기존 부품(`engine.game_or_fail`·
  `engine.running_game`·`store.list_backups`·`confirm._classify`)을 **조립만** 한다.

### ★ 쓰기의 문은 엔진 `restore_backup` **하나**다
이 모듈은 **아무것도 쓰지 않는다**(조회·판정뿐). 복원 자체는 접착층이 엔진을 부른다 —
그래서 G15(`assert_backup_in_root`)·G5(실행 중)·G4(크기 검사)가 전부 엔진 한 문에 남는다.

### ★ 되돌릴 곳은 백업의 종류가 정한다 (13판 — 설계 §14 · 12판의 2단계 시맨틱은 폐기)
    · `profile_*` 백업 → **그 프로필 슬롯**으로 직접 되돌린다(게임 설정 파일은 건드리지 않는다)
    · 그 밖의 백업     → **디스크(게임 설정 파일)** 로 되돌린다
12판까지는 ①디스크 복원 → ②`save_profile`로 슬롯에 얹는 2단계였다. 13판에서 「되돌릴 곳」
기준으로 재설계되면서 그 경로는 사라졌다 — 화면도 각 백업 행에 되돌릴 곳을 먼저 보여준다.

### ★ 경로 봉쇄는 **함수 진입 직후(0단계)** 한 번, 술어는 P8과 **공유**한다
`remove._paths_in_position`이 profiles/슬롯/backups를 realpath로 풀어 **정확 위치**인지 본다.
복원 경로가 지나는 것은 `backups/<appid>`인데, 그 디렉터리가 외부 링크면
`assert_backup_in_root`의 기준점(`realpath(backups_dir)`)이 **같이 밀려나** 링크 너머 아무
파일이나 "백업 폴더 안"이 된다 — 즉 임의 파일을 게임 설정 파일로 복사할 수 있다.
술어를 새로 만들지 않는 이유: 삭제와 복원이 **같은 경계**를 봐야 한 쪽만 약해지는 일이 없다.
"""
import logging
import os

from . import codes, confirm, engine, remove, store

_log = logging.getLogger("gfxp.restore")

#: 안전하지 않은 경로에 쓰는 고정 지문. 어떤 실제 파일도 읽지 않고 만들어진다(P8 Codex #2 문법).
_UNSAFE_FP = "unsafe"

#: ★ **백업 파일명의 해석은 `store.parse_backup_id` 하나다**(15판 §14-G ⓔ). 예전에는 그 파서가
#:   여기 살았고 `store.backup_order_key`는 같은 이름을 **자기 정규식**으로 따로 읽었다 —
#:   이름을 **만드는** 곳(`store._backup_name`)과 **읽는** 곳이 갈려 있던 것이 「형식 불명」의
#:   정의가 두 벌이 된 원인이다. 태그별 중복 판정(`store.backup_holds`)도 그 해석을 쓰므로
#:   정의는 한 곳이어야 한다. 여기 남는 것은 **그 kind로 무엇을 하는가**(아래 되돌릴 곳)뿐이다.

#: 행 `kind` → **되돌릴 곳**. 판정은 백엔드 한 곳이다(프론트가 kind로 재분류하지 않는다).
#: `unknown`이 게임 설정 파일로 가는 것은 *출처를 모르기 때문*이다 — 더 놀랍지 않은 쪽을 고른다
#: (설계 §5-C ⓐ · §6-O2).
_TARGET_OF_KIND = {"profile_dock": "dock", "profile_internal": "internal"}
TARGET_CONFIG = "config"


def target_of(backup_id):
    """그 백업 행을 [복원]하면 **어디가 바뀌는가** — `"dock"|"internal"|"config"`.

    ★ 이 함수가 정본이다. 토큰 결박(§5-F-1)·행 표시(§5-C ⓒ)·엔진 인자(§14-C)가 **같은 값**을
      써야 한다. 세 곳이 각자 kind를 해석하면 언젠가 하나가 어긋나고, 어긋난 순간
      *"확인한 곳과 다른 곳에 쓰기"*가 된다.
    """
    return _TARGET_OF_KIND.get(store.parse_backup_id(backup_id)["kind"], TARGET_CONFIG)


def _display_identity(row):
    """**화면이 실제로 찍는 조합.** 지금 그 조합은 `stamp_label · filename`이다
    (`src/confirmSpecs.tsx`의 `evictNote`).

    ⚠️ 표시 조합이 바뀌면 이 함수도 같이 바꾼다 — 여기가 화면보다 **좁아지는** 순간
      *"화면에서는 같아 보이는데 백엔드는 다르다고 판정"*이 되어 구분 번호가 안 붙는다.
      반대로 넓으면(화면이 조각을 더 그리면) 번호가 필요 없는 곳에 붙을 뿐이라 안전하다.
    """
    return (row["stamp_label"], row["filename"])


def _mark_duplicates(rows):
    """같은 표기가 둘 이상이면 **구분 번호(`dup`)를 붙인다** — 화면이 대는 이름이 실제로 그
    하나를 가리키게 (2026-08-15 QA 재심 A · S2).

    ★★ 무엇이 문제였나: 항목 표기는 `stamp_label · filename` 둘뿐인데, 같은 초에 같은 설정
      파일로 만들어진 정상 백업 두 개(`…-disk-video.ini` / `…-disk-1-video.ini`)는 그 둘이
      **완전히 같은 문자열**이 된다. 확인창은 *"이것이 지워집니다"*라고 이름을 대며 승인을
      받는데, 그 이름이 둘을 가리키면 사용자는 **무엇을 승인했는지 모른 채** 승인한다.
    ★ 원시 파일명을 그대로 노출하는 것은 답이 아니다 — 사용자는
      `20260815-120000-disk-1-video.ini`를 읽고 싶어 하지 않는다. 백엔드가 파싱해 사람이 읽는
      조각으로 준다는 기존 원칙(`store.parse_backup_id`)을 뒤집는 일이기도 하다.
    ★ **같을 때만** 붙인다: 늘 붙이면 대부분(유일한 표기)에 뜻 모를 번호가 달려 읽는 비용만
      늘고, 사용자는 그 번호가 무엇을 세는지 알 길이 없다. 번호는 *모호할 때의 해소 장치*다.
    ★ 번호의 뜻 = **그 표기를 공유하는 것들 중 먼저 만들어진 것이 1번**이다. 순서는
      `store.backup_order_key` — prune·목록·축출 예고가 이미 쓰는 **그 순서 하나**다(R14 #3).
      표시 목록은 최신순이라 화면에는 큰 번호가 먼저 오지만, 번호는 **행의 자리**가 아니라
      **파일 자체**를 가리켜야 하므로 생성 순서로 매긴다.
    ★★ **그룹의 범위는 「지워질 것」이 아니라 「그 게임의 백업 링 전체」다.** 좁히면 둘 중 하나만
      지워지는 경우(=한쪽은 남는다)에 번호가 안 붙어, 화면이 대는 이름이 **남는 쪽까지** 가리킨다
      — 사용자가 가장 알고 싶은 것이 바로 *"내 두 백업 중 어느 쪽이 사라지나"*인 자리다.
    ★ 번호가 겹치지 않는 근거: `backup_order_key`의 마지막 축이 파일명이고 파일명은 한
      디렉터리에서 유일하다 → 그룹 안에서 전순서가 되어 `enumerate`가 1:1이다.
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
    """백업 링을 **한 번 나열해** 축출 예고·링 지문·칸 수·실제로 쌓일 수를 같이 낸다 —
    `{"evicted": [...], "fingerprint": …, "count": N, "adding": K}`.

    `items`는 이 동작이 **만들려는 백업들**(`(tag, sha1)` 쌍)이다. 개수가 아니라 무엇을
    만드는지를 받는 이유(§14-G ⓔ): 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이
    아무것도 쓰지 않으므로 **지워지는 백업도 없다.** 그 판정은 링을 봐야 하는데, 그것을 부르는
    쪽에서 따로 하면 **나열이 둘이 되어 위 ⓕ가 닫은 창이 그대로 다시 열린다.** 그래서 중복
    판정도 이 한 번의 나열 안에서 한다 — `adding`이 그 결과다.

    ★★ **왜 한 번인가**(설계 §14-G ⓕ): 예전에는 고지(`evict_preview`)와 토큰 지문
      (`ring_fingerprint`)이 **각자 링을 나열**했다. 그 두 관측 사이에 링이 돌면 확인창은
      **옛 목록의 이름**을 대고 토큰은 **새 목록**에 묶여, 2차 호출에서 그 토큰이 그대로
      통과했다 — *사용자가 승인한 이름과 실제로 지워지는 파일이 다른* 상태다. 창은 좁지만
      (실측 183~217µs) 좁은 창은 **없는 창이 아니다.**
      다게임 경로(`apply_all`·`reset_all`)는 처음부터 *"축출 예고와 그 지문은 한 번의 산출에서
      같이 나온다"*였다 — 이 함수가 그 문법을 단일 게임 경로로 옮긴 것이고, 그래서 판정 함수가
      params와 지문을 **함께** 돌려줄 수 있다.
    ★ 지문은 `adding`과 무관하게 **링 전체의 이름 순서**다(아래 `ring_fingerprint` 주석):
      축출이 0건이어도 링이 돌면 지문은 움직여야 한다.
    ★ `count`도 같은 나열에서 낸다 — 화면의 *"현재 백업 N건"*이 지문이 잰 링과 다른 순간의
      링을 세면, 같은 확인창 안에서 두 숫자가 서로 다른 시각을 가리킨다.
    ★ 안전하지 않은 경로는 **읽지 않는다**(P8 Codex #2) — 고정 센티널과 빈 목록·0으로 접는다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return {"evicted": [], "fingerprint": _UNSAFE_FP, "count": 0, "adding": 0}
    entries = store.list_backups(appid)              # ★ 나열은 **여기 한 번**이다(ⓕ)
    names = [os.path.basename(p) for p in entries]
    observed = {"evicted": [],
                "fingerprint": store.sha1_bytes("\n".join(names).encode("utf-8")),
                "count": len(names),
                "adding": 0}
    if not items:
        return observed                              # 백업을 안 만드는 갈래는 지울 것도 없다
    # ★ 고지가 보는 판정과 엔진이 집행하는 판정이 **같은 함수**여야 화면과 실제가 갈리지 않는다.
    adding = len(store.plan_backups(entries, items))
    observed["adding"] = adding
    if adding <= 0:
        # 전부 중복 — 한 칸도 안 쓰므로 축출도 없다. ★ 이것은 **비용 단락**이지 두 번째 규칙이
        # 아니다: 아래 `store._doomed_tail`도 `adding == 0`이면 빈 집합을 낸다(같은 답).
        return observed
    rows = []
    for name in names:                               # ★ 먼저 **링 전체**를 만든다 (아래 이유)
        info = store.parse_backup_id(name)
        rows.append({"backup_id": name, "kind": info["kind"],
                     "stamp_label": info["stamp_label"], "filename": info["filename"],
                     "dup": 0})
    # ★ 구분 번호는 **링 전체를 보고** 매긴 뒤 자른다 — 지워질 것만 보고 매기면, 쌍둥이 중
    #   하나만 지워질 때 번호가 안 붙어 화면이 남는 쪽까지 가리키는 이름을 댄다.
    _mark_duplicates(rows)
    # ★★ 꼬리는 **`store._doomed_tail` 한 곳**에서만 유도한다(QA DEFECT-08). 예전에는 이 줄이
    #   같은 산술을 한 벌 더 갖고 있었고, 그 함수에서 경계 결함이 **네 번** 났다
    #   (호출 시점 링 · 자기 쓰기를 셈 · 음수 슬라이스 · `adding == 0`). 값이 같다고 두면
    #   다음번에 링 의미를 바꿀 때 **확인창이 약속한 축출과 실제로 지워지는 파일이 갈린다.**
    #   `rows`는 `names`(=`entries`)와 **같은 순서로** 만들었으므로 짝지어 거른다.
    doomed = store._doomed_tail(entries, adding)
    observed["evicted"] = [row for row, path in zip(rows, entries) if path in doomed]
    return observed


def evict_preview(appid, items):
    """이 동작이 **`items`를 백업하려 할 때 실제로 지워질** 파일들(설계 §5-E-3).

    `items` = `(tag, sha1)` 쌍들 = 만들려는 백업. **개수가 아닌 이유는 위 `ring_observe`**에
    있다(중복이면 안 만들고, 안 만들면 안 지운다 — §14-G ⓔ).

    ★★ **산출의 정본은 위 `ring_observe` 하나다**(R14 #1 → 15판 ⓕ). 경로마다 따로 세면 어느
      하나는 반드시 화면과 실제가 어긋난다. 이 함수는 그 위의 **얇은 래퍼**로, 축출 **이름
      목록만** 필요하고 지문은 필요 없는 자리가 쓴다 — 지금 소비자는 **둘**이다:
      `confirm.apply_all_evict_preview`(일괄 적용) · `remove.evict_on_delete`(전체 초기화).
      **지문이 함께 필요한 자리(단일 게임 확인창 넷 = 적용·저장·복원·등록 해제)는
      `ring_observe`를 직접 부른다** — 여기를 한 번 더 부르면 관측이 둘로 갈린다(위 ⓕ).
    ★★ 정렬은 `store.list_backups`(=prune이 실제로 자르는 목록)다. 표시 목록(`backup_rows`)도
      **같은 순서**를 쓴다 — 순서의 정본은 `store.backup_order_key` 하나다(R14 #3에서 통합).
    ★ **그 산술의 정본은 `store._doomed_tail` 하나다** — 아래는 그 **이유 설명**이지 두 번째
      규칙이 아니다(`adding == 0`이면 꼬리가 아예 없다는 갈래도 거기 있다).
    ★ `BACKUP_KEEP - adding`인 이유: 새 백업이 목록 맨 앞에 `adding`건 끼어들면 기존 항목이 그만큼
      밀린다. prune은 새 목록의 `[BACKUP_KEEP:]`을 지우므로, 지워지는 것은 **지금 목록의
      `[KEEP-adding:]`**이다. `adding`이 링보다 크면(슬롯에 파일이 아주 많은 삭제 경로) 지금
      목록 전부가 지워진다 — 음수 슬라이스로 뒤에서 세는 사고를 막으려고 0에서 자른다.
    ★ 항목은 **고유 `backup_id`를 싣고** 거기에 화면이 그릴 조각을 얹는다(봉투 계약
      `EvictedRow`). id는 화면에 그리지 않는다 — 대상이 하나임을 **증명**하는 자리이고
      (토큰 지문·검사가 이 값으로 실제 삭제분과 대조한다), 사람이 읽는 것은 조각 쪽이다.
    ★ 빈 `items`를 **여기서** 먼저 끊는다: 지문이 필요 없는 호출자(다게임 합산)가 만들 것도
      없는 게임에서 링을 나열하지 않게 하려는 것이다(비용 단락 — 답은 어느 쪽이든 `[]`다).
    """
    if not items:
        return []
    return ring_observe(appid, items)["evicted"]


def evict_digest(plan):
    """게임별 축출 대상(`(appid, [backup_id, …])` 목록)을 **토큰에 묶을 한 문자열**로 접는다.

    ★★ 왜 개수가 아니라 대상인가(2026-08-15 QA 재심 B): 다게임 경로(일괄 적용·전체 초기화)의
      토큰은 `remove.reset_fingerprint` 하나에 묶여 있었는데, 그 지문의 링 신호는 **개수**
      (`bk=%d`)뿐이다. **포화 링이 한 칸 도는 동안 개수는 10으로 불변**이므로 대상이 바뀌어도
      낡은 토큰이 통과했다. 개수는 *지문이 아니라 요약*이다.
    ★ 축출이 0건인 게임은 **싣지 않는다** — 약속하지 않은 것은 지문도 재지 않는다(그 게임의
      링이 어떻게 움직이든 이 동작이 지울 것은 없다).
    ★ 순서를 그대로 담는다: 목록 순서가 곧 *"무엇이 먼저 잘리는가"*라 순서가 바뀌면 대상이
      바뀐 것과 같다.
    """
    body = "\n".join("%s=%s" % (appid, ",".join(ids)) for appid, ids in plan)
    return store.sha1_bytes(body.encode("utf-8"))


def ring_fingerprint(appid):
    """확인 토큰에 묶을 **백업 링의 지문** — 지금 목록의 이름을 순서 그대로 잰다.

    ★★ 왜 필요한가(R14 #2): 확인창은 *"이 백업이 지워집니다"*라고 **이름을 대며** 약속하는데,
      토큰 지문에는 링이 없었다. 확인창을 띄운 사이 다른 동작이 링을 한 칸 돌리면 **낡은 토큰이
      그대로 통과**하고, 실제로 지워지는 것은 사용자가 승인한 파일이 **아닌** 다른 파일이었다.
    ★ 개수가 아니라 **순서 있는 이름 전체**를 잰다: 포화 링에서는 개수가 10으로 불변인 채
      대상만 바뀌므로 개수 신호로는 잡히지 않는다(그 경로가 실제 재현 시나리오였다).
    ★ 안전하지 않은 경로는 **읽지 않는다** — `backup_count`·`evict_preview`와 같은 센티널 문법.
    ★★ **산출은 `ring_observe` 한 곳이다**(§14-G ⓕ). 확인창이 이름을 대는 자리에서는 이 함수를
      따로 부르지 않는다 — 고지와 지문이 각자 링을 나열하면 그 사이의 변화가 토큰에 구워진다.
      여기 남는 이유는 *"링만 재고 싶은"* 소비자(검사의 계측기)가 그 뜻을 이름으로 말할 수 있게
      하기 위해서다.
    """
    return ring_observe(appid)["fingerprint"]


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


def _slot_meta(appid, profile):
    """슬롯 meta를 **dict일 때만** 돌려준다. 손상·비객체·없음은 전부 `None`이다.

    복원은 망가진 상태를 되돌리는 경로라, 손상 하나로 조회가 죽으면 안 된다
    (`_disk_state`·`main._slot_view`와 같은 판단)."""
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _evacuation_source(appid, profile, meta):
    """복원이 **대피시킬 바로 그 파일**의 경로 — 없으면 `""`. 대피 판정의 정본은 여기 하나다.

    ★★ **엔진 `restore_backup`의 대피 조건과 같은 술어다**: meta가 dict이고 그 `filename`이
      문자열이며 **그 이름의 본체가 실재할 때만** 대피가 일어난다(engine.py의 `old_name` /
      `old_file` 두 조건). 화면이 약속하는 것(*"백업 한 칸을 씁니다"*)과 엔진이 실제로 하는 일이
      **한 술어**에서 나와야 어긋날 자리가 없다.
    ⚠️ 이 함수는 *"대피할 파일이 무엇인가"*까지만 답한다. 그 대피가 **링에 칸을 쓰는가**는
      한 조건이 더 붙는다 — 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이 아무것도
      쓰지 않는다(§14-G ⓔ). 부르는 쪽이 `store.plan_backups`로 그 한 조건을 마저 본다.
    ★★ 왜 함수로 빼는가(2026-08-15 QA R2): 이 조건은 4-B **9행과 10행에서 각각 다른 이유로**
      거짓이 되는데, 자리마다 조건을 다시 적었더니 9행에만 걸리고 **10행이 빠졌다** — 그 결과
      확인창이 *없는 프로필을 「…에 저장됨」*이라 하고 *쓰지도 않는 링을 「한 칸 씁니다」*라고
      말했다. 술어가 하나면 빠뜨릴 자리가 없다.
    ★ `meta`를 **인자로 받는다**: 같은 판정 안에서 meta를 두 번 읽으면 그 사이의 변화로 두 답이
      갈릴 수 있다. 부르는 쪽이 이미 읽은 그 값을 그대로 쓴다.
    """
    name = meta.get("filename") if meta else None
    if not isinstance(name, str) or not name:
        return ""
    path = os.path.join(store.profile_dir(appid, profile), name)
    return path if os.path.exists(path) else ""


def target_sha1(reg, appid, target):
    """**되돌릴 곳의 지금 내용** 지문. 모르면 `None`.

    · `config` → 게임 설정 파일의 sha1(파일을 읽는다)
    · 슬롯     → **그 슬롯 본체 파일의 sha1**(설계 §5-F-1)

    ★★ 13판까지는 슬롯 쪽을 **meta의 기록값**으로 답했다(IO 0). 그런데 이 값의 소비자 셋이
      전부 *"되돌릴 곳이 지금 무엇을 들고 있는가"*를 묻는다 — `already` 판정 · 목록의
      `same_as_target` 배지 · 토큰 지문. 기록만 믿으면 **meta는 B라는데 본문이 C인 슬롯**에서
      셋 다 거짓이 된다(R14 #5): 복구 버튼이 *"이미 같습니다"*로 끝나 **손상된 슬롯을 못 고치고**,
      복원은 손상을 되돌리는 경로인데 바로 그 자리에서 막힌다.
    ★ 비용은 슬롯 본체 파일 1회 읽기다(목록당 대상별 1회 — `backup_rows`가 캐시한다).
      **모르면 `None`**이라 배지는 안 그려지고 `already`도 성립하지 않는다(안전한 방향).
    """
    if target == TARGET_CONFIG:
        entry = (reg.get("games") or {}).get(str(appid)) or {}
        return store.sha1_file(entry.get("config_path") or "")
    meta = _slot_meta(appid, target)
    name = meta.get("filename") if meta else None
    if not isinstance(name, str) or not name:
        return None
    return store.sha1_file(os.path.join(store.profile_dir(appid, target), name))


def backup_rows(reg, appid):
    """백업 목록 — **최신순**. 순수 조회, 아무것도 쓰지 않는다.

    ⚠️ **정렬은 `store.list_backups` 하나다**(R14 #3에서 통합). 예전에는 그쪽이 역사전순이라
      같은 초 충돌 접미사에서 시간순이 깨졌고(`-10-` < `-2-`), 그래서 여기서 `(stamp, seq)`로
      **다시 정렬**했다. 두 순서가 갈리는 동안 **prune이 자르는 것과 화면이 보여주는 순서가
      달랐고**, 축출 예고가 지워지지 않을 이름을 댈 수 있었다. 이제 순서의 정본은
      `store.backup_order_key` 한 곳이고 여기는 그 순서를 **그대로** 그린다.

    ★ 13판: 행마다 **되돌릴 곳**(`target`)과 **지금과 같음**(`same_as_target`)을 같이 준다
      (설계 §5-C ⓒ) — 누르기 전에 말하면 결과 팝업이 뜰 이유 자체가 준다(§4-I ⑤-ⓑ).
      판정은 **백엔드 한 곳**이다: 프론트가 `kind`로 목적지를 재분류하지 않는다.
    ★ `same_as_target`은 **모르면 false**다(배지를 안 그린다) — 모르는 것을 "같다"고 말하지 않는다.
    ★ 비용: 백업 파일 ≤10건의 sha1 + 대상 지문(설정 파일 또는 슬롯 **본체** 1회씩). **뷰를 열 때 1회**다.
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


def _restore_fp(current, backup, ring):
    """복원 토큰 지문의 **조립 규칙**은 여기 하나다 — 관측은 부르는 쪽이 한다(§14-G ⓕ).

    `(되돌릴 곳의 sha1, 백업 파일 sha1 + 링 지문)`. 조회 실패는 `"absent"`로 적는다 —
    없음도 지문의 일부다(없다가 생기면 무효가 되는 쪽이 안전).

    ★ 왜 조립만 하는가: 이 값을 내는 자리가 둘이다 — **판정 함수**(`needs_confirm`이 고지를
      만들며 이미 잰 값으로 낸다)와 **`fingerprint`**(새로 관측해 낸다, 검사의 오라클).
      관측이 갈리는 것은 자리마다 재는 시점이 다르기 때문이라 정상이지만, **조립 규칙까지
      갈리면** 검사가 초록인 채로 route의 토큰만 어긋난다. 규칙은 한 줄에 둔다.
    """
    return (current or "absent", "%s|ring=%s" % (backup or "absent", ring))


def needs_confirm(reg, appid, backup_id):
    """`(state, params, fingerprint)` — **3-상태 계약**이다(불리언이 아니다). 판정 기준은 **되돌릴 곳**이다.

        "already"  되돌릴 곳이 이미 그 백업과 같다 → 접착층이 **엔진을 부르기 전에 반환**한다.
                   엔진 `restore_backup`에는 already 스킵이 없어(무조건 대피+쓰기) 낙하시키면
                   같은 행 [복원]을 다시 누를 때마다 **백업 링이 1칸씩 소모**된다.
        "proceed"  되돌릴 곳이 비어 있다(설정 파일 없음 / 빈 슬롯) → 복원이 **재생**하는 것이라
                   잃을 것이 없다. 묻지 않는다 — 계약의 절반은 묻지 않는 것이다.
        "confirm"  내용이 다른 것을 덮어쓴다 → 확인 토큰을 요구한다.

    ★★ 13판(설계 §5-C ⓑ): 12판은 대상이 무엇이든 **게임 설정 파일 하나만** 봤다. 그래서
      `profile_dock` 백업을 되돌리려는데 게임 설정 파일이 우연히 그것과 같으면 무쓰기로 끝났고,
      정작 되돌리려던 슬롯은 그대로였다. 기준을 목적지로 옮긴다.
    ★ **실행 중 조기 거부는 `config` 대상에만** 건다(설계 §14-C): 프로필 슬롯은 게임이 읽지도
      쓰지도 않으므로 거부할 이유가 없고, 거부하면 *"게임 켜 둔 채 프로필만 되돌리기"*가 막힌다.
      집행의 문은 여전히 엔진 G5 하나이고(여기는 예의상 조회), TOCTOU는 그 G5가 잡는다.
    ★ **축출 고지(`evicted`)는 대피가 실제로 일어나는 갈래에만** 실린다(적용과 대칭 — §5-E-3).
      `already`·`proceed`·대피 불가 갈래는 링을 쓰지 않으므로 지워질 파일도 없다.

    ★★ **지문을 params와 함께 낸다**(15판 §14-G ⓕ). 예전에는 접착층이 고지를 받은 **뒤** 다시
      `fingerprint()`를 불렀고, 그 두 관측 사이의 변화가 토큰에 구워져 영구히 안 보였다.
      지금은 고지에 쓴 **바로 그 관측값**(되돌릴 곳의 sha1 · 백업 sha1 · `ring_observe`)이
      그대로 지문이 된다.
    ⚠️ 지문은 **`confirm` 갈래에서만** 낸다(`already`·`proceed`는 `None`) — 토큰을 쓰지 않는
      갈래라 잴 것이 없고, 재면 링 나열이 매 조회마다 붙는다.
    ⚠️ **지문은 봉투로 나가지 않는다** — `params`가 아니라 **세 번째 반환값**이다. 접착층이
      `**params`로 splat해도 화면 계약에 새 필드가 생기지 않는다(main.py:840-842와 같은 규칙).
    """
    appid = str(appid)
    _assert_in_position(appid)                       # 0단계
    entry = engine.game_or_fail(reg, appid)          # 미등록 → GAME_NOT_REGISTERED

    info = store.parse_backup_id(backup_id)
    target = _TARGET_OF_KIND.get(info["kind"], TARGET_CONFIG)
    if target == TARGET_CONFIG and engine.running_game(appid):    # 조기 거부 (§2-B-1)
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
        # **되돌릴 곳** — 화면 문구도 토큰 결박도 엔진 인자도 이 값 하나를 쓴다(§5-F-1).
        "target": target,
        # 게임 설정 파일이 지금 어떤 상태인가 — 저장 확인창과 **같은 4분류**를 쓴다.
        # (슬롯 복원에서도 싣는다: "게임 설정 파일은 바뀌지 않습니다"를 말하는 화면의 재료다.)
        "disk_state": confirm._classify(state),
        # 이 복원이 **백업 링에 한 칸을 쓰는가**(R2 — 화면의 「백업 한 칸을 씁니다」가 참인 조건).
        # 기본은 **거짓**이다: 약속은 그것이 참인 갈래에서만 켠다 — 없는 대피를 말하면 사용자는
        # 남아 있지도 않을 복구 지점을 믿는다.
        # ★ **같은 내용이 이미 그 태그의 링에 있으면 거짓이다**(§14-G ⓔ): 엔진이 아무것도 쓰지
        #   않으므로 칸을 안 쓴다. 그 내용이 백업에 있다는 사실은 여전히 참이지만, 이 필드가
        #   말하는 것은 *"이 동작이 칸을 태우는가"*다 — 안 태우면 축출도 없다(`evicted`도 빈다).
        # ⚠️ 이 값이 뜻을 갖는 것은 **`confirm` 갈래**다(화면이 그때만 읽는다 — 다른 상태에는
        #   확인창 자체가 없다). `already`는 아무것도 쓰지 않으므로 여기 실린 값을 근거로 삼지 말 것.
        "evacuates": False,
        "evicted": [],
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]

    if target == TARGET_CONFIG:
        config_path = entry.get("config_path") or ""
        if not os.path.exists(config_path):
            return "proceed", params, None           # 잃을 것이 없다(재생) — 대피도 없다
        # ★ 이 sha1이 곧 **되돌릴 곳의 지문**이다(`target_sha1(reg, appid, "config")`와 같은 값·
        #   같은 파일). 판정에 쓴 값을 그대로 토큰에 묶으므로 둘이 다른 시점을 볼 수 없다.
        disk_sha = store.sha1_file(config_path)
        if disk_sha and backup_sha and disk_sha == backup_sha:
            return "already", params, None
        # 엔진은 설정 파일이 **있을 때만** 그것을 대피시키고(engine.restore_backup 끝단), 같은
        # 태그에 **같은 내용이 이미 있으면 아무것도 쓰지 않는다**(§14-G ⓔ). 화면의 「백업 한 칸을
        # 씁니다」는 **칸을 쓸 때만** 참이므로 그때만 켠다 — 이미 링에 있는 내용이면 잃는 것도
        # 새로 태우는 칸도 없다. 판정은 엔진의 무쓰기 갈래와 **같은 술어**(`store.backup_holds`)다.
        ring = ring_observe(appid, [(store.KIND_DISK, disk_sha)])
        # ★ 고지·지문·**대피 여부**가 전부 그 한 나열에서 나온다(ⓕ) — `adding`이 0이면 링에
        #   한 칸도 안 쌓이므로 「백업 한 칸을 씁니다」도 거짓이고 지워질 것도 없다.
        params["evacuates"] = bool(ring["adding"])
        params["evicted"] = ring["evicted"]
        return "confirm", params, _restore_fp(disk_sha, backup_sha, ring["fingerprint"])

    # ---- 프로필 슬롯으로 되돌린다 (설계 4-B 2·3·4·9·10행)
    meta = _slot_meta(appid, target)
    name = meta.get("filename") if meta else None
    # ★★ **술어 하나가 두 문장을 함께 정한다**(R2 — 9행과 10행이 갈리던 자리):
    #   ⓐ 「복원 전에 지금의 내용도 백업으로 보관합니다 — 백업 한 칸을 씁니다」
    #   ⓑ 「덮어쓸 대상(현재 …): {saved_at}에 저장됨」
    #   10행(기록만 있고 실물이 없다)에서는 **둘 다 거짓**이다 — 엔진은 대피할 파일을 못 찾아
    #   링을 쓰지 않고, 덮어쓸 내용도 그 자리에 없다. 그런데 9행에만 조건이 걸려 있어서
    #   10행 확인창이 두 문장을 그대로 그렸다.
    source = _evacuation_source(appid, target, meta)
    # ★ **본체 sha는 여기서 한 번만 잰다.** 이 값이 두 곳에 쓰인다 — 아래 `already` 판정의
    #   「되돌릴 곳의 지금 내용」(= `target_sha1(reg, appid, target)`과 **같은 파일·같은 값**)과,
    #   대피가 실제로 링을 쓰는지의 판정이다. 두 번 읽으면 그 사이의 변화로 두 답이 갈린다(ⓕ).
    slot_sha = store.sha1_file(source) if source else None
    # ★ 대피가 링을 쓰는 조건은 **본체가 있고** + 같은 태그에 같은 내용이 아직 없을 때다
    #   (§14-G ⓔ). 앞의 조건은 여기서, 뒤의 조건은 아래 한 번의 링 나열이 함께 답한다 —
    #   그 사이의 갈래들(9행·10행·2행)은 링을 쓰지 않으므로 기본값 **거짓** 그대로 나간다.
    # 저장 시각은 **그 기록이 가리키는 본체가 실재할 때만** 그 자리의 내용을 설명한다.
    params["saved_at"] = (meta.get("saved_at") or "") if source else ""
    if not isinstance(name, str) or not name:
        if store.slot_body_exists(appid, target):
            # 9행 — 기록이 손상됐고 실물은 남아 있다. **대피할 대상을 특정할 수 없으므로**
            # 확인창이 그 사실을 말하고 묻는다(A12 = 고지하고 묻기이지 모르면 막기가 아니다).
            # ★ 되돌릴 곳의 지문은 **`None`(=absent)**이다: `target_sha1`도 여기서는 본체
            #   이름을 못 만들어 `None`을 낸다 — 그 값을 다시 재지 않고 그대로 쓴다.
            params["slot_unreadable"] = True
            return "confirm", params, _restore_fp(
                None, backup_sha, ring_observe(appid)["fingerprint"])
        return "proceed", params, None               # 3행 — 빈 슬롯. 잃을 것이 없다
    if not source:
        # 10행 — 기록만 있고 실물이 없다. **묻는 것은 유지한다**: 이 슬롯은 지금 깨져 있고,
        # 복원은 그 깨진 자리에 쓰는 동작이다(3행처럼 "빈 슬롯"이라고 단정할 근거가 없다).
        # 다만 위에서 `evacuates=False`·`saved_at=""`이 되었으므로 확인창은 **없는 대피와
        # 없는 저장 시각을 말하지 않는다.**
        # ★ `source`가 비었다 = 그 이름의 본체가 없다 = `target_sha1`도 `None`이다(같은 술어).
        return "confirm", params, _restore_fp(
            None, backup_sha, ring_observe(appid)["fingerprint"])
    # ★ 판정은 **본문 실측**이다(R14 #5 — `target_sha1`과 같은 값·같은 파일). meta의 기록값으로
    #   판정하면 *"기록은 B인데 본문은 C"*인 손상 슬롯에서 `already`가 되어 **복구 버튼이 그
    #   자리에서 막힌다** — 복원은 바로 그 손상을 되돌리려는 경로다.
    # ★★ 이 값이 곧 **되돌릴 곳의 지문**이다 — 판정과 토큰이 같은 관측을 쓴다(ⓕ). 예전에는
    #   접착층이 `fingerprint()`를 다시 불러 이 본체를 **한 번 더 읽었고**, 그 사이의 변화가
    #   토큰에 구워졌다. 위에서 `slot_sha`를 이미 잰 것이 그 관측이다.
    if slot_sha and backup_sha and slot_sha == backup_sha:
        return "already", params, None               # 2행
    ring = ring_observe(appid, [(store.profile_tag(target), slot_sha)])   # 4행
    # ★ 중복이면 대피본이 안 생기므로(§14-G ⓔ) 「백업 한 칸을 씁니다」도 축출도 없다 —
    #   그 판정과 축출 예고와 지문이 **한 나열**에서 같이 나온다(ⓕ).
    params["evacuates"] = bool(ring["adding"])
    params["evicted"] = ring["evicted"]
    return "confirm", params, _restore_fp(slot_sha, backup_sha, ring["fingerprint"])


def fingerprint(reg, appid, backup_id):
    """토큰에 묶을 상태 지문 `(되돌릴 곳의 sha1, 백업 파일 sha1 + 링 지문)`.

    · 대상 쪽: 확인창을 띄운 사이 그 자리의 내용이 바뀌면 무효가 된다(TOCTOU — `save_profile`과
      같은 문법). 사용자가 본 "무엇을 덮어쓰는가"가 이미 낡았기 때문이다.
      **13판: 그 자리는 대상에 따라 다르다** — 설정 파일이거나 프로필 슬롯이다(§5-F-1).
      12판처럼 언제나 디스크를 재면, 슬롯을 덮어쓰는 복원이 **디스크만 안 바뀌면** 낡은 토큰으로
      통과한다.
    · 백업 쪽: 발급~소비 사이 prune으로 **같은 이름의 파일이 바뀌는** 극단 케이스까지 잡는다.
    · **링 쪽(R14 #2)**: 확인창이 *"이 백업이 지워집니다"*라고 이름을 대고 승인을 받았으므로,
      그 사이 링이 돌면 **승인 대상이 달라진다.** 백업 지문과 같은 칸에 합성해 싣는다 —
      `_consume`은 튜플 **전체 동등 비교**만 하고 문자열을 되쪼개지 않으므로(main.py) 합성이
      안전하고, 슬롯을 늘리지 않아 발급·소비 양쪽 계약이 한 줄도 안 바뀐다.

    조회 실패는 `"absent"`로 적는다 — 없음도 지문의 일부다(없다가 생기면 무효가 되는 쪽이 안전).

    ⚠️ **복원 route는 이 함수를 부르지 않는다**(15판 §14-G ⓕ). route가 쓰는 지문은
      `needs_confirm`이 고지를 만들며 **이미 잰 값**으로 낸 것이다 — 여기를 다시 부르면 관측이
      둘이 되어 그 사이의 변화가 토큰에 구워진다. 이 함수는 *"지금 이 조합의 지문은 무엇인가"*를
      **새로 관측**해 묻는 자리(검사의 사전 조건·계측기)를 위해 남는다.
      조립 규칙은 `_restore_fp` **한 곳**이라 두 자리가 규칙으로 갈릴 수는 없다.
    """
    appid = str(appid)
    if not remove._paths_in_position(appid):
        return _UNSAFE_FP, _UNSAFE_FP
    return _restore_fp(
        target_sha1(reg, appid, target_of(backup_id)),
        store.sha1_file(os.path.join(store.backups_dir(appid), str(backup_id))),
        ring_observe(appid)["fingerprint"])
