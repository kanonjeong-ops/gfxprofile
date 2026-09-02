"""저장이 기존 프로필을 실제로 덮어쓰는가를 판정한다. 순수 조회이며 파일을 바꾸지 않는다.

반환값의 부호에 주의한다. 여기서 `True`는 저장을 진행하라는 뜻이 아니라 확인이 필요하다는
뜻이다. 호출자가 이를 진행 허가로 해석하면 확인 조건이 뒤집힌다.

슬롯 존재 여부는 meta가 아니라 `store.evacuable_names`가 현재 관측한 본체 목록으로 정한다.
meta가 없거나 비객체여도 본체가 남아 있으면 덮어쓰기 판정을 계속한다.

“내용이 이미 같다”는 판단은 기록의 SHA-1만 비교하지 않는다. 디스크 SHA-1과 설정 파일명을
`store.slot_holds`에 넘겨 슬롯 본체까지 확인한다. `engine.save_profile`의 무쓰기 분기도 같은
술어와 같은 종류의 값을 사용한다. `store.write_profile`은 본체를 먼저 쓰고 meta를 나중에
쓰므로 기록과 본체가 갈린 상태가 도달 가능하다.
"""
import os

from . import codes, engine, store

# `disk_state` 4분류. 현재 분류는 파일 존재 여부와 SHA-1 산출 여부를 완전히 갈라내지 않는다.
OTHER_PROFILE = "other_profile"   # 디스크 내용과 일치한 슬롯 디렉터리 이름을 같이 싣는다
UNKNOWN = "unknown"               # SHA-1은 읽었지만 어느 슬롯 본체와도 일치하지 않는다
MISSING = "missing"               # SHA-1이 없다 — 파일 없음뿐 아니라 기존 파일의 읽기 실패도 여기로 접힌다
LOOKUP_FAILED = "lookup_failed"   # `engine.disk_state` 호출 자체가 포착된 예외로 실패했다


def _state_fp(meta_sha1, disk_sha1, ring):
    """저장·적용 토큰 지문의 조립 규칙은 여기 하나다 — 관측은 부르는 쪽이 한다.

    `(슬롯 meta의 sha1, 디스크 sha1 + 링 지문)`. 조회 실패는 `None`을 그대로 싣는다 —
    없음도 지문의 일부라, 조회 실패 상태에서 발급한 토큰은 조회가 되기 시작하면 거부된다
    (안전한 방향이다 — 다시 물으면 되고, 그 사이 사용자가 본 화면은 이미 낡았다).

    둘째 칸에 백업 링의 지문을 합성한다. 확인창은 "이 백업이 지워집니다"라고 이름을 대며
      승인을 받는데, 그 사이 다른 동작이 링을 한 칸 돌리면 승인 대상이 달라진다. 개수는
      그대로일 수 있어(포화 링) 개수만으로는 안 걸린다. 합성이 안전한 이유는 `main._consume`이
      튜플 전체 동등 비교만 하고 문자열을 되쪼개지 않기 때문이다 — 슬롯 수를 늘리지 않고
      지문만 넓힌다.
    """
    return meta_sha1, "%s|ring=%s" % (disk_sha1, ring)


def _meta_sha1(appid, profile):
    """슬롯 meta가 기록하고 있는 내용 sha1. 못 읽거나 비-dict면 `None`.

    비-dict meta(손상 JSON)에서 `.get`이 AttributeError를 내면 지문 산출이 통째로 죽으므로
    `isinstance`로 접는다. 조회 실패도 `None`이다 — 없음도 지문의 일부다."""
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        return None
    return meta.get("sha1") if isinstance(meta, dict) else None


def _ring_observe(appid, items=()):
    """산출의 정본은 `restore.ring_observe` 하나다(적용·저장 공용).

    반환값은 `evicted`, `fingerprint`, `count`, `adding` 네 칸이다. 이 파일은 그중
    `evicted`·`fingerprint`·`adding`을 쓴다.

    `items`는 이 동작이 만들려는 `(tag, sha1)` 쌍이다. 같은 태그·내용의 사본이 있고 그 사본이
    이번 계획 뒤에도 살아남으면 새 백업을 만들지 않는다. 반대로 그 사본 자체가 이번 축출로
    사라질 자리라면 `store.plan_backups`가 다시 쓰도록 센다. 이 판정과 축출 예고는 같은 링
    나열에서 나온다.

    import는 함수 안에서 한다. `restore`가 이 모듈을 최상단에서 import하므로 여기서 최상단
    맞import를 만들면 순환 import가 된다.
    """
    from . import restore
    return restore.ring_observe(appid, items)


def needs_confirm(reg, appid, profile):
    """`(need, params, fingerprint)` — 저장이 기존 프로필을 실제로 덮어쓰는가.

    `need`가 True일 때만 `params`에 확인창이 쓸 정보가 실린다
    (`size` · `sha1_short` · `saved_at` · `disk_state` · `evicted` [· `matched_profile`]
     — `src/rpc.ts`의 `ConfirmParams`와 필드 단위로 짝을 이룬다).

    지문을 params와 함께 낸다. 고지를 만들며 이미 읽은 값이 그대로 지문이 되므로, 고지와
      지문 사이에 관측이 한 번 더 끼는 창이 없다.
    지문은 묻는 갈래에서만 낸다(`need`가 False면 `None`) — 토큰을 쓰지 않는 갈래라 잴 것이
      없고, 재면 정상 저장마다 링 나열이 붙는다.
    지문은 봉투로 나가지 않는다 — `params`가 아니라 세 번째 반환값이다.
    """
    appid = str(appid)
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        # 여기서 막지 않는다. 저장을 진행하면 `engine.save_profile`이 같은 meta를 다시 읽고
        #   실패하므로 결과는 「아무것도 안 쓰고 실패」다 — 화면에 나가는 문구도 그 결과와
        #   맞춰 "프로필 정보가 손상되어 저장할 수 없습니다"로 이미 정해져 있다(main.py의
        #   `save_profile`, `PROFILE_META_CORRUPT` 갈래).
        # `{"note": ...}`는 봉투로 나가지 않는다 — `need`가 False라 접착층이 `params`를
        #   쓰지 않는다. 지금 이 값을 읽는 곳은 `qa/test_confirm_equivalence.py`뿐이다.
        return False, {"note": "META_UNREADABLE"}, None

    # 판정 시점의 본체 존재 여부는 기록이 아니라 `store.evacuable_names`로 정한다.
    # 엔진도 실행 시 같은 헬퍼로 대피 대상을 다시 계산한다. 두 층이 공유하는 것은 선택 규칙이며,
    # 확인 시점의 목록 객체나 스냅샷 자체가 아니다.
    bodies = store.evacuable_names(appid, profile)
    if not bodies:
        return False, {}, None                # 진짜 빈 슬롯 — 잃을 것이 없다(엔진도 대피하지 않는다)
    if not isinstance(meta, dict):
        meta = {}                             # 기록은 못 믿어도 본체는 있다 — 재료는 아래에서 실측한다

    try:
        state = engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError):
        state = None                          # `{}`가 아니라 `None` — 아래에서 「조회 실패」와
                                              #   「파일 없음」을 갈라야 하기 때문이다
    disk_sha1 = state.get("sha1") if state else None

    # 「이미 같다」는 기록이 아니라 본체로 판정한다. `disk_sha1 == meta.get("sha1")`처럼 기록만
    #   보면, 본체를 먼저 쓰고 meta를 나중에 쓰는 `store.write_profile`이 중간에 죽어 남긴
    #   「본체 B · meta.sha1 A」 상태에서 정책층은 "이미 같다"며 안 묻고 엔진은 다르다며
    #   대피·쓰기·축출을 실행한다 — 확인창이 한 번도 안 뜬 채 포화 링의 최고령 백업이 고지
    #   없이 사라진다. 그 상태의 도달 경로는 `qa/test_slot_body_truth.py`에 적혀 있다.
    # 그래서 엔진과 같은 함수를 같은 인자로 부른다. 엔진의 무쓰기 분기는
    #   `store.slot_holds(appid, profile, store.sha1_bytes(data), os.path.basename(path))`인데,
    #   그 `path`가 `entry["config_path"]`이고 `data`가 그 파일의 바이트다 — 여기 `disk_sha1`과
    #   아래 `config_name`이 그 둘과 같은 값이다. 값 비교를 두 벌 적으면 언젠가 갈린다.
    # `state`가 `None`(조회 실패)이면 `disk_sha1`도 `None`이라 `slot_holds`가 곧바로 거짓이다 —
    #   따로 `state is not None` 가드를 두지 않아도 모르면 묻는 쪽으로 접힌다.
    # 실행·판정 계열(§8-D): 이 함수는 `game_or_fail`을 직접 부르지 않고(위 `disk_state` 경유의
    #   `Refused`는 자기 `except`가 삼킨다) 여기서 entry를 직접 읽는다. 반환이 truthy든 falsy든
    #   비-dict거나 `config_path`가 비-문자열이면 같은 이름 있는 거부를 낸다 — `or {}`가 falsy
    #   비-dict(`0`·`""`·`[]`)를 「미등록」으로 오진하던 갈래도 함께 닫힌다. 미등록(None) 계약은
    #   불변이라 None은 거르지 않는다.
    entry = store.game(reg, appid)
    if entry is not None and engine.entry_corrupt(entry):
        raise engine.Refused(
            "거부: appid %s의 등록 정보가 손상되었습니다 — 항목 값 %r." % (appid, entry),
            code=codes.REGISTRY_ENTRY_CORRUPT, appid=str(appid))
    entry = entry or {}
    config_name = os.path.basename(entry.get("config_path") or "")
    if store.slot_holds(appid, profile, disk_sha1, config_name):
        return False, {}, None                # 내용이 이미 같다 — 덮어써도 달라지는 것이 없다

    # 표시 재료는 필드 단위로 기록과 실측을 가른다 — 기준은 「기록이 통째로 비었나」가 아니라
    #   「이 칸을 못 믿나」다. 기록이 멀쩡하면 실측하지 않는다.
    size, sha1_short = _slot_materials(appid, profile, meta, bodies)
    # 축출 예고는 대피 대상 수가 아니라 `store.plan_backups`가 실제 쓰기로 계획한 수를 쓴다.
    #   같은 태그·내용의 사본이 계획 뒤에도 살아남으면 중복으로 빼고, 그 사본이 이번 축출로
    #   사라질 자리면 다시 쓰도록 센다. 엔진도 실행 시 같은 계획 함수를 사용한다.
    directory = store.profile_dir(appid, profile)
    tag = store.profile_tag(profile)
    ring = _ring_observe(
        appid, [(tag, store.sha1_file(os.path.join(directory, name))) for name in bodies])
    params = {
        "size": size,
        "sha1_short": sha1_short,
        # `saved_at`은 기록에서만 온다. 기록이 없으면 저장 시각은 모르는 것이 사실이고, 파일
        #   mtime은 저장 시각이 아니다(복사·복원·터치로도 바뀐다) — 지어내면 그 자체가 거짓이다.
        "saved_at": meta.get("saved_at") or "",
        "disk_state": _classify(state),
        # 이 저장이 현재 관측에서 실제로 지울 백업이다.
        #   슬롯 본체 목록을 `(tag, sha1)` 쌍으로 `ring_observe`에 넘기고, 살아남는 중복 사본은
        #   쓰기 수에서 빼되 이번 축출로 사라질 중복 사본은 다시 쓴다. 그 결과인 `adding`으로
        #   축출 목록을 계산한다. 축출 목록과 링 지문은 같은 링 나열에서 나온다.
        "evicted": ring["evicted"],
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]
    return True, params, _state_fp(meta.get("sha1"), disk_sha1, ring["fingerprint"])


def _slot_materials(appid, profile, meta, bodies):
    """확인창이 대는 `(size, sha1_short)` — 기록이 못 미더운 칸만 본체에서 잰다.

    왜 필드 단위인가: 기록이 통째로 비었을 때만 실측하면, `{"foo": 1}`처럼 비지는 않았는데
      크기·해시가 없는 기록에서 화면이 멀쩡한 본체를 옆에 두고 "지금 저장돼 있는 것: 0 B"라
      말한다. 갈래를 넓히는 대신 판정의 단위를 바꾸면 그 예외 자체가 없어진다.
    재는 대상은 이 판정에서 `store.evacuable_names`로 얻은 `bodies`다. 엔진도 실행 시 같은
      선택 규칙을 다시 사용하지만, 두 호출 사이에 파일이 바뀔 수 있으므로 동일 스냅샷이라고
      약속하지 않는다.
    해시는 본체가 하나일 때만 댄다. 여럿인데 하나를 고르면 화면이 어느 것의 해시인지 말할 수
      없는 값을 사실처럼 내놓는다. 모르면 비운다.
    실측이 실패해도(OSError) 저장을 막지 않는다: 그 값만 0·빈 문자열로 두고 확인창은 그대로
      뜬다. 이 갈래의 본질은 확인과 대피이지 표시값이 아니다.
    """
    size = meta.get("size") or 0
    sha1_short = (meta.get("sha1") or "")[:10]
    # 기록은 「본체와 맞을 때만」 믿는다. 필드가 비지 않았다는 것은 "기록이 있다"이지
    #   "기록이 맞다"가 아니다. 같은 `meta`의 같은 두 필드(`size`·`sha1`)를 쓰는
    #   `engine.save_profile`의 크기 가드도 `store.slot_holds`로 같은 조건을 건다.
    #   본체는 새것인데 기록은 옛것인 반쪽 상태는 도달 가능하다 — `main.save_profile`의
    #   `except OSError`가 적어 둔 그 상태다(본체를 먼저 쓰고 기록을 나중에 쓴다). 거기서
    #   기록을 그냥 믿으면 확인창이 잃지 않을 것의 크기·해시를 댄다.
    trusted = store.slot_holds(appid, profile, meta.get("sha1"), meta.get("filename"))
    if size and sha1_short and trusted:
        return size, sha1_short               # 기록이 본체와 맞는다 — 파일을 다시 열지 않는다
    if not trusted:
        # 기록이 본체와 어긋난다 — 값이 차 있어도 그 칸을 쓰면 안 된다. 비워서 아래 실측
        #   갈래로 보낸다(비어 있던 칸을 채우는 것과 같은 자리를 지난다).
        size, sha1_short = 0, ""
    directory = store.profile_dir(appid, profile)
    if not size:
        for name in bodies:
            try:
                size += os.path.getsize(os.path.join(directory, name))
            except OSError:
                pass                          # 그 파일만 안 세고 넘어간다
    if not sha1_short and len(bodies) == 1:
        # `store.sha1_file`은 읽기 실패 시 `None`이라 예외로 새지 않는다.
        sha1_short = (store.sha1_file(os.path.join(directory, bodies[0])) or "")[:10]
    return size, sha1_short


APPLY_STATES = ("already", "proceed", "confirm")


def _disk_state_or_none(reg, appid):
    """`engine.disk_state`가 거부되거나 파일·값·타입 관련 포착 대상 예외를 내면 조회 실패(`None`)로
    접는다. 적용 판정 전체가 해당 조회 실패로 중단되지 않게 하기 위해서다.
    `restore._disk_state`도 같은 예외 집합을 `None`으로 접고, `main._disk_state_safe`는 이를 빈
    dict로 접는다.

    `{}`가 아니라 `None`인 것이 중요하다. 아래에서 조회 실패와 파일 없음을 구분한다.
    """
    try:
        return engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError, AttributeError, TypeError):
        return None


def _matching_profiles(appid, disk_sha1):
    """디스크 내용과 같은 슬롯 전부. `engine.disk_state`의 first-match break를 쓰지 않는다.

    왜 다시 도는가: 엔진은 첫 일치에서 멈추므로 두 슬롯 내용이 같을 때 임의로 한쪽만 고른다.
      그 값을 화면 마커로 쓰면 나머지 한쪽을 "적용돼 있지 않다"고 거짓으로 말한다. 판정을
      여기서 하면 봉투가 사실대로 배열을 싣는다.
    비용을 정직하게: 슬롯 meta 2개 + (기록이 일치할 때만) 그 본체를 읽는다. `disk_state`가
      방금 읽은 값을 못 쓰는 이유는 그것이 first-match에서 멈춰 나머지 슬롯을 아예 안 보기
      때문이다.
      (`get_overview`는 이 함수를 쓰지 않는다: 거기서는 `main._slot_view`가 이미 두 sha를
       들고 있어 파일 접근이 0 증가다 — `main._disk_matches`.)

    판정은 본체 실측까지다(`store.slot_holds`). meta만 보면 "이 내용은 저 슬롯에 보존돼 있다"가
      거짓일 수 있고, 이 값이 곧 묻지 않고 진행 + 대피 생략의 근거라 거짓인 순간 디스크의
      마지막 온전한 사본이 고지 없이 사라진다. 모르면 목록에서 뺀다.
    """
    if not disk_sha1:
        return []
    return [p for p in ("dock", "internal") if store.slot_holds(appid, p, disk_sha1)]


def apply_needs_confirm(reg, appid, profile):
    """`(state, params, fingerprint)` — 개별 적용의 3-상태 계약이다.

        "already"  게임 설정 파일이 이미 목표 슬롯과 같다 → 접착층이 엔진을 부르기 전에
                   반환한다. 파일도 링도 건드리지 않는다.
        "proceed"  파일이 없거나(재생) 다른 슬롯과 같다(그 내용은 이미 슬롯에 보존돼 있다)
                   → 잃을 것이 없으므로 묻지 않는다. 계약의 절반은 묻지 않는 것이다.
        "confirm"  두 슬롯 모두와 다르다(또는 조회 실패) → 이 파일에만 있는 내용이 사라질 수
                   있는 갈래다. 확인 토큰을 요구한다.
                   「유일한」이 아니다: 여기 온다고 반드시 잃는 것은 아니다 — 슬롯 본체가
                   깨진 상태도 이 갈래로 오고, 그때는 승인해도 엔진이 `PROFILE_CORRUPT`로
                   거부해 아무것도 안 바뀐다. 계약은 "잃을 수 있으면 묻는다"이지
                   "물으면 잃는다"가 아니다.

    실행 중 게임은 상태 판정 전에 `engine.running_game`으로 조기 거부한다. 확인창 사이에 게임이
      켜지는 경우는 실제 쓰기 직전의 `engine.apply_profile` 검사에서 다시 거부한다.
    슬롯 없음·손상은 조기 거부하지 않는다 — 근거는 미러를 늘리지 않는다 하나다. 확인 뒤
      엔진이 `PROFILE_CORRUPT`로 거부하고 파일은 한 바이트도 안 바뀐다(링도 안 돈다).
      이 갈래는 경합 없이 한 번의 탭으로 도달한다: 본체만 깨진 슬롯에서 `main._slot_view`는
      "meta가 읽히고 본체 파일이 존재한다"까지만 재므로 `has_dock=True`이고, 프론트의 활성
      조건이 `busy || !has[p]`라 버튼이 활성인 채로 「저장됨 · 날짜」로 그려진다.

    지문을 params와 함께 낸다. 고지를 만들며 이미 읽은 값이 그대로 지문이 되므로, 고지와
      지문 사이에 관측이 한 번 더 끼는 창이 없다.
    지문은 `confirm` 갈래에서만 낸다(`already`·`proceed`는 `None`) — 토큰을 쓰지 않는다.
    지문은 봉투로 나가지 않는다 — `params`가 아니라 세 번째 반환값이다.
    """
    appid = str(appid)
    engine.game_or_fail(reg, appid)                  # 미등록 → GAME_NOT_REGISTERED
    if engine.running_game(appid):
        raise engine.Refused(
            "거부: 게임이 실행 중입니다. 게임을 완전히 종료한 뒤 적용하십시오.",
            code=codes.GAME_RUNNING, appid=appid)

    state = _disk_state_or_none(reg, appid)
    disk_sha1 = state.get("sha1") if state else None
    matches = _matching_profiles(appid, disk_sha1)
    params = {
        "appid": appid,
        "profile": profile,
        # 덮어쓸 대상(=게임 설정 파일)이 지금 어떤 상태인가 — 저장·복원 확인창과 같은 4분류다.
        "disk_state": _classify(state),
        "matches": matches,
        # 이 적용이 백업 링에 실제로 새 항목을 쓰는가는 `ring["adding"]`으로 정한다.
        # 같은 `disk` 태그·내용의 사본이 있어도 그 사본이 이번 축출로 사라질 자리면 다시 쓸 수 있다.
        # 따라서 기존 사본의 존재만으로 `evacuates=False`나 빈 `evicted`를 단정하지 않는다.
        # 이 값은 확인을 요구하는 갈래에서만 화면이 읽는다.
        "evacuates": False,
        # 이 동작이 백업을 1건 만들 때 실제로 지워질 파일들. 적용·복원 공용이다.
        # `confirm` 갈래에서만 채운다(복원도 대칭이다): `already`는 무쓰기이고, `proceed`는
        #   잃을 것이 없는 갈래라 대피본을 만들지 않는다. 링을 안 쓰는 갈래에 고지를 실으면
        #   화면이 일어나지 않을 삭제를 말한다.
        "evicted": [],
    }
    if matches:
        # 4분류의 `other_profile`이 이름을 하나 요구한다(기존 문구 계약). 배열이 정본이고
        # 이 값은 그 첫 원소다 — 화면 문구가 쓰던 자리를 깨지 않는다.
        params["matched_profile"] = matches[0]

    if state is None:
        # 모르면 묻는다. 디스크 조회가 실패했으므로 지문의 디스크 칸도 `None`이고, 그 `None`이
        # 곧 지문의 일부다 — 조회가 되기 시작하면 낡은 토큰이 거부된다(안전한 방향).
        return "confirm", params, _state_fp(_meta_sha1(appid, profile), None,
                                            _ring_observe(appid)["fingerprint"])
    if not state.get("exists"):
        return "proceed", params, None               # 파일 없음 — 잃을 것이 없다(재생)
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        meta = None
    # 이 값은 지문의 meta 칸이다 — 아래 판정은 이 값을 쓰지 않지만, 토큰은 여기서 한 번만
    #   읽은 그 값을 쓴다(관측을 늘리지 않는다).
    target_sha1 = meta.get("sha1") if isinstance(meta, dict) else None
    # 「이미 같다」는 기록이 아니라 본체 실측이다. `target_sha1 == disk_sha1`로 판정하면
    #   본체만 깨진 슬롯에 대고 화면이 "이미 적용됨"이라 답한다. 그 순간이 고치기 가장 쉬운
    #   자리인데(디스크에 그 내용이 그대로 있어 [저장] 한 번이면 슬롯이 되살아난다) 앱이
    #   침묵하고, 다른 프로필을 한 번 거치고 나면 같은 버튼이 `PROFILE_CORRUPT`로 막힌다.
    #   복원의 `already`도 같은 이유로 본체 실측이다.
    # 판정 자체의 추가 IO는 0이다: `matches`는 두 줄 위(`_matching_profiles`)에서 이미 두 슬롯
    #   양쪽에 `store.slot_holds`를 돌려 놓았다.
    #   다만 「이 변경의 IO가 0」은 아니다: `already`였던 상태가 `confirm`으로 옮겨가면 그
    #   갈래가 링을 한 번 나열한다. 늘어난 것은 판정이 아니라 갈래 이동분이다.
    if profile in matches:
        return "already", params, None
    if matches:
        return "proceed", params, None               # 다른 슬롯과 같다 — 그 내용은 보존돼 있다
    # 조회에 성공했고 디스크 내용이 어느 슬롯 본체와도 일치하지 않을 때 대피 계획을 만든다.
    # 같은 태그·내용의 사본이 계획 뒤에도 살아남으면 새로 쓰지 않지만, 그 사본이 이번 축출로
    # 사라질 자리면 다시 쓴다. 판정은 `store.plan_backups`가 맡는다.
    ring = _ring_observe(appid, [(store.KIND_DISK, disk_sha1)])
    # 고지·지문·대피 여부가 전부 그 한 나열에서 나온다 — 링을 다시 관측하지 않는다.
    #   `adding`이 0이면 링에 한 칸도 안 쌓이므로 「백업 한 칸을 씁니다」도 거짓이고 지워질
    #   것도 없다(복원 확인창도 같은 두 줄을 쓴다 — `restore.needs_confirm`).
    params["evacuates"] = bool(ring["adding"])
    params["evicted"] = ring["evicted"]
    return "confirm", params, _state_fp(target_sha1, disk_sha1, ring["fingerprint"])


def already_registered(reg, appid):
    """이미 등록된 appid인가 — 맞으면 화면이 쓸 `params`, 아니면 `None`.

    막아야 하는 것: `engine.add_game`은 기존 entry의 `config_path`를 무조건 덮어쓴다
      (`setdefault`로 entry를 얻은 뒤 `entry.update`가 경로를 다시 넣는다). 그래서 같은
      appid로 다시 등록하면 경로가 조용히 바뀌고, 그 다음 `apply_profile`이 새 경로의 파일을
      프로필 내용으로 덮어쓴다 — 등록과 무관한 파일이 지워지는 갈래다. 프론트에서 버튼을
      숨겨도 route 계약은 열려 있으므로 백엔드 판정이 있어야 한다.

    경로 변경 자체를 지원하지 않는다. 지금 필요한 것은 "조용히 바뀌지 않는 것"이고, 경로 변경
      전용 확인 계약은 그것을 원하는 화면이 생길 때 만든다.
    """
    entry = (reg.get("games") or {}).get(str(appid))
    if entry is None:
        return None
    # 실행·판정 계열(§8-D · §14-H ⓙ): 이 함수는 `game_or_fail`을 지나지 않고 entry를 직접
    #   읽으며 그 뒤 `entry.get(...)`이 비-dict에서 죽는다. 손상 항목이면 「이미 등록됨」은 참이
    #   아니고(등록 기록이 깨진 것이다), 못 믿는 `name`·`config_path`를 화면 봉투에 실어선 안
    #   되므로 이름 있는 거부를 낸다. 이 문이 `engine.add_game`의 `entry.update` 사망점도 함께
    #   막는다 — 그래서 엔진 쪽에는 술어를 심지 않는다(재등록 복구 길을 열어 둔다).
    if engine.entry_corrupt(entry):
        raise engine.Refused(
            "거부: appid %s의 등록 정보가 손상되었습니다 — 항목 값 %r." % (appid, entry),
            code=codes.REGISTRY_ENTRY_CORRUPT, appid=str(appid))
    return {"appid": str(appid),
            "name": entry.get("name") or ("appid %s" % appid),
            "config_path": entry.get("config_path") or ""}


def add_game_needs_confirm(warnings):
    """수동 등록이 저장 전에 되물어야 하는가.

    계약의 절반은 묻지 않는 것이다. 자동 탐지 후보는 `_classify`를 통과해 `_SCAN_ROOTS` 아래에서
    만들어지므로 `config_candidate_warnings`의 두 경고 조건을 구조적으로 피한다. 경고가 없는 수동
    선택도 묻지 않는다. 경고가 있을 때만 확인을 요구한다.
    """
    return bool(warnings), {"warnings": list(warnings)}


# ── 일괄 적용 미리보기 ───────────────────────────────────────────────────────
#
# 판정 미러가 두 곳이 되는 것을 감수한 자리다. 엔진에 dry-run 플래그를 넣는 것은 diff fence
#   위반이라 불가능하므로, 미리보기는 `engine.apply_all`의 판정을 읽기 전용으로 재현한다.
#   그래서 계약을 문서가 아니라 테스트로 못박는다
#   (`qa/test_apply_preview_equivalence.py` — 적대 합성 세계 전수).
#
# 버킷은 5개이고, 엔진 `BULK_OUTCOMES` 5종을 빠짐없이 분류한다.
#   이것을 "1:1"이라고 부르면 안 된다 — 아래 표대로 `running_refused`는 `refused` 중 실행
#     중인 것만, `cannot_apply`는 나머지 `refused`와 `error`를 함께 받는다. 즉 버킷→outcome은
#     다대일이 섞인 전사(全射) 분류이고, 보장하는 것은 ① 모든 outcome이 어느 버킷엔가 든다
#     ② 게임 하나는 정확히 한 버킷에만 든다 — 이 둘이다.
#   4버킷(refused/error를 would_apply로 셈)은 오산이다 — "적용 예상 9개"라고 해 놓고 실제로는
#     3개만 되는 화면이 나온다.
#
# 미리보기는 같은 관측 시점의 엔진 판정 순서를 재현한다. 확인 뒤 상태가 바뀌면 결과는 어느
#   방향으로도 달라질 수 있다. 특히 실행 중 상태는 축출 대상을 바꾸지 않는 한 토큰 지문에 남지
#   않으므로, 미리보기에서 `running_refused`였던 게임이 확인 뒤 종료되면 실제로 적용될 수 있다.
#   화면의 「예상」은 동치 보증이 아니라 관측 시점의 분류라는 뜻이다.
#
#   지문은 registry 상태와 축출 대상을 묶지만 디스크 sha1·실행 상태 자체를 묶지는 않는다.
#   그 변화가 축출 대상을 바꾸면 다시 묻고, 바꾸지 않으면 기존 토큰이 통과할 수 있다.
#: 미리보기 버킷 ← 엔진 outcome: would_apply←applied · already←already ·
#: no_profile←no_profile · running_refused←refused(GAME_RUNNING) · cannot_apply←refused(기타)+error
APPLY_BUCKETS = ("would_apply", "already", "no_profile", "running_refused", "cannot_apply")


def _preview_one(reg, appid, profile, running):
    """게임 하나가 어느 버킷에 드는가. 판정 순서 = 엔진 실행 순서다.

    순서가 계약이다. `already` 판정이 G5(실행 중)보다 먼저이므로
      (`engine.apply_all`의 `already` 갈래가 `apply_profile` 진입 전에 스킵한다) 실행 중이어도
      디스크==프로필이면 `already`다. 순서를 바꾸면 화면이 "실행 중 N개는 거부 예상"이라고
      말하는데 실제로는 조용히 already가 되어, 미리보기와 결과가 어긋난다.

    예외는 이 함수 밖에서 게임별로 격리된다 — 두 호출자(`apply_all_preview`·
      `apply_all_evict_preview`)가 각자 엔진 외곽 try와 동형으로 감싼다.
    """
    meta = store.load_meta(appid, profile)
    if not meta:
        return "no_profile"
    try:
        state = engine.disk_state(reg, appid)
    except Exception:                      # noqa: BLE001 — 엔진의 같은 자리(`engine.apply_all`의 `disk_state` try/except)와 동형
        state = {}
    if state.get("sha1") and state["sha1"] == meta.get("sha1"):
        return "already"
    # 손상된 등록 항목(비-dict · `config_path` 비-문자열)은 엔진이 `refused(REGISTRY_ENTRY_CORRUPT)`를
    #   낸다(★ 19판 — 그 전에는 `entry["config_path"]`의 `KeyError`가 게임별 외곽 try에 잡혀
    #   `error`였다). 거부는 `apply_profile`의 첫 줄 `game_or_fail`에서 나므로 여전히 G5보다
    #   먼저다 — 실행 중이어도 이 갈래가 이긴다.
    #   아래 조건은 엔진의 두 사실을 함께 미러한다: 손상 술어의 거부(비-문자열)와, 빈 경로가
    #   뒤에서 맞는 실패(빈 문자열 — 그 값은 손상 술어에 안 걸린다)를 한 줄로 접는다. 둘 다
    #   화면에서는 「적용 불가」 한 칸이다. 이 줄이 없으면 미리보기는 `would_apply`라고 세고
    #   실행은 거부된다 — "적용된다 해 놓고 안 되는" 어긋남이다.
    #   **조건의 순서가 계약이다** — 술어 호출이 앞이라야 truthy 비-dict entry에서 `.get`이
    #   단축 평가로 건너뛰어진다. 엔진 술어를 여기 다시 적지 않고 `engine.entry_corrupt`를
    #   부른다(그래서 그 헬퍼가 모듈 공개다). 버킷은 `cannot_apply` 그대로다(그 버킷이
    #   `refused`와 `error`를 함께 받는다).
    entry = (reg.get("games") or {}).get(str(appid))
    if engine.entry_corrupt(entry) or not entry.get("config_path"):
        return "cannot_apply"
    if str(appid) in running:
        return "running_refused"           # G5 — 디스크≠프로필일 때만 여기 온다
    path = store.profile_file_path(appid, profile)
    if not (path and os.path.exists(path)):
        return "cannot_apply"              # PROFILE_MISSING
    if store.sha1_file(path) != meta.get("sha1"):
        return "cannot_apply"              # PROFILE_CORRUPT
    return "would_apply"


def apply_all_preview(reg, profile, running):
    """일괄 적용이 무엇을 할 예정인가 — 5버킷 개수. 아무것도 쓰지 않는다.

    `running`은 접착층의 `_running_appids()`가 준 집합이다(/proc 1회 스캔) — 게임마다
    `engine.running_game`을 부르면 등록 수에 정비례하는 재스캔이 된다.

    게임별 예외 격리가 엔진과 동형이다. `store.load_meta`는 손상 JSON에서 예외를 그대로
      던지는데(`json.load`를 감싸지 않는다) 격리가 없으면 meta 손상 1건이 미리보기 전체를
      UNEXPECTED로 만들어 `CONFIRM_REQUIRED`가 영영 안 나오고 일괄 적용 버튼이 전면 불능이 된다.
      엔진은 그 게임만 `error`로 강등하고 계속 가므로, 미리보기가 전멸하면 "하나가 실패해도
      나머지는 계속"이 미리보기 층에서 뒤집힌다.
      → 어떤 예외든 그 게임만 `cannot_apply`로 강등하고 다음 게임을 계속한다.

    미리보기는 같은 관측 시점의 엔진 판정 순서를 재현한다. 확인 뒤 상태가 바뀌면 결과는 어느
    방향으로도 달라질 수 있다. 특히 실행 중 상태는 축출 대상을 바꾸지 않는 한 토큰 지문에 남지
    않으므로, 미리보기에서 `running_refused`였던 게임이 확인 뒤 종료되면 실제로 적용될 수 있다.
    화면의 「예상」은 동치 보증이 아니라 관측 시점의 분류라는 뜻이다.

    지문은 registry 상태와 축출 대상을 묶지만 디스크 sha1·실행 상태 자체를 묶지는 않는다.
    그 변화가 축출 대상을 바꾸면 다시 묻고, 바꾸지 않으면 기존 토큰이 통과할 수 있다.
    """
    counts = dict.fromkeys(APPLY_BUCKETS, 0)
    for appid in sorted(reg["games"]):
        try:
            bucket = _preview_one(reg, appid, profile, running)
        except Exception:                  # noqa: BLE001 — 엔진 `apply_all`의 게임별 외곽 try와 동형
            bucket = "cannot_apply"
        counts[bucket] += 1
    return counts


def apply_all_evict_preview(reg, profile, running):
    """일괄 적용이 실제로 지울 백업 — `{"evicted": N, "evict_games": M, "fingerprint": …}`.

    왜 이름을 대지 않는가: 게임이 여럿이라 게임마다 나열하면 확인창이 터진다. 그래서 수만
      약속하고, 그 수는 게임별 산출(`restore.evict_preview`)의 합이라 나열본과 같은 근거에서
      나온다. 이름이 필요한 자리는 게임이 하나인 확인창들(저장·적용·복원·등록 해제)이고
      거기서는 이름을 댄다. 수가 정확하면 인지 요건은 충족된다 — 읽히지 않는 열 게임짜리
      목록은 인지시킨 것이 아니다.
    수가 어긋나지 않는 근거: ⓐ 판정 순서가 엔진과 같고(`_preview_one`) ⓑ 대피 조건도 엔진과
      같으며(디스크가 있고 어느 슬롯에도 보존돼 있지 않을 때만 — `engine.apply_profile`)
      ⓒ 토큰이 이 산출의 지문에 묶인다(아래).
    `fingerprint` — 화면에 실을 값이 아니라 토큰에 묶을 값이다. `remove.reset_fingerprint`
      하나로는 부족하다:
        · 그 지문의 링 신호는 개수뿐이라 포화 링이 도는 것(개수 불변)을 못 잡고,
        · 애초에 설정 파일 sha는 의도적으로 빠져 있어, 확인창을 띄운 사이 게임·클라우드가
          설정 파일을 고유 내용으로 바꾸면 "축출 0건"이라 말한 토큰이 그대로 통과할 수 있다 —
          그 다음 실행이 대피본을 만들며 고지하지 않은 백업 1건을 지운다.
      그래서 지문은 개수가 아니라 대상 목록 그 자체(`restore.evict_digest`)로 낸다.
    재는 것 / 못 재는 것(정직하게):
        재는 것  = 이 호출 시점에 각 게임에서 지워질 backup_id 전량과 그 순서. 하나라도
                   달라지면 지문이 달라져 낡은 토큰이 거부되고 새 목록으로 다시 묻는다.
        못 재는 것 = ⓐ 실행 시점에만 나는 실패(G11·G4·BACKUP_FAILED)로 적용이 거부되면 그 게임의
                   축출도 안 일어난다 — 예고보다 덜 지워지는 안전한 방향이라 화면은 「예상」이라
                   말한다. ⓑ 게임별 예외로 건너뛴 게임의 내부 상태(모르면 약속하지 않는다).
                   ⓒ 축출이 0건인 게임의 링 변화 — 지울 것이 없으면 약속한 것도 없다.
      같은 태그·내용의 사본이 링에 있어도 그것이 이번 동작의 축출 대상이면 새 대피본을 만든다.
        `store.plan_backups`가 살아남는 중복만 무쓰기로 접고, 실제 쓰기 수와 축출 대상을 함께
        정한다.
      그래서 「디스크 sha1을 지문에서 뺀다」는 여전히 유효하되 범위가 좁아졌다: 설정 파일이
        다시 쓰여도 토큰은 그대로다 — 그 변화가 지워질 백업을 바꾸는 때(=그 게임의 링이 이미
        가득 찬 때)만 예외다. 그때는 확인→재확인이 마찰이 아니라 고지의 정정이다.
    비용은 게임당 한 패스가 아니다. `_preview_one`이 슬롯 meta를 읽고 그 안의
      `engine.disk_state`가 슬롯마다 meta를 다시 읽으며, would_apply로 살아남은 게임에는
      이 함수가 `disk_state`를 한 번 더 부른다. 게다가 `Plugin.apply_all`은 확인 갈래에서
      이 함수와 `apply_all_preview`를 둘 다 돌리고 소비 갈래에서도 이 함수를 다시 돌린다 —
      호출당 게임 목록 위를 두 패스씩 지난다. 실행이 곧 그 파일들을 다 만지므로 새 정비례가
      생기는 것은 아니지만, 「게임당 meta 1회」로 읽으면 안 된다.
    """
    from . import restore                     # 순환 회피 — `remove`의 지역 import와 같은 이유·같은 문법
    plan = []
    for appid in sorted(reg["games"]):
        try:
            if _preview_one(reg, appid, profile, running) != "would_apply":
                continue
            state = engine.disk_state(reg, appid)
            if not state.get("exists") or state.get("matches"):
                continue                      # 대피본을 안 만드는 갈래
            # 같은 태그·내용의 사본이 링에 있어도 그것이 이번 동작의 축출 대상이면 새 대피본을 만든다.
            # `store.plan_backups`가 살아남는 중복만 무쓰기로 접고, 실제 쓰기 수와 축출 대상을 함께 정한다.
            rows = restore.evict_preview(appid, [(store.KIND_DISK, state.get("sha1"))])
        except Exception:                     # noqa: BLE001 — 게임별 격리(엔진 외곽 try와 동형)
            continue                          # 그 게임은 세지 않는다(모르면 약속하지 않는다)
        if rows:
            plan.append((str(appid), [row["backup_id"] for row in rows]))
    return {"evicted": sum(len(ids) for _, ids in plan),
            "evict_games": len(plan),
            "fingerprint": restore.evict_digest(plan)}


def _classify(state):
    if state is None:
        return LOOKUP_FAILED
    if state.get("matches"):
        return OTHER_PROFILE
    if state.get("sha1"):
        return UNKNOWN
    return MISSING
