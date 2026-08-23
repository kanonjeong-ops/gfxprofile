"""저장이 **기존 프로필을 실제로 덮어쓰는가**를 판정한다 — 순수 조회, 파일을 바꾸지 않는다.

설계 정본 §2-E-0. M1 `ui_tk._confirm_overwrite`(`:649-684`)의 판단을 **분기까지 그대로** 옮긴 것이다.

### 왜 자기 파일에 사는가 — 셋 중 어디에 둬도 규칙을 깬다
- `engine.py` → **diff fence 위반**(허용 목록에 없다). 엔진은 M1 실사용 코드와 바이트 동일선을 지킨다
- `main.py`  → *"접착층은 정책 판단 금지"*(§2-C) 위반
- 프론트     → **fail-closed가 깨진다.** 프론트가 조건을 틀리면 확인 없이 덮어쓴다

→ **fence 밖의 새 파일**이면 셋 다 피한다. 파생 이득: 순수 함수라 Decky도 tkinter도 없이 테스트된다.

### ⚠️ 이 함수의 반환은 M1과 **뜻이 반대**인 곳이 있다
M1 `_confirm_overwrite`는 `True` = *"저장을 진행하라"*였다. 여기는 `True` = *"물어야 한다"*다.
M1이 `True`(진행)를 돌려주던 세 경우(meta 없음 · 내용 동일 · meta 읽기 실패)가 전부
여기서는 `False`(안 물음)가 된다. **옮길 때 이 부호를 뒤집지 않으면 확인창이 정반대로 뜬다.**

⚠️ 두 곳에서 **일부러 M1보다 좁다**(설계 §14-G ⓐ, 2026-08-22): *"meta 없음"*과 *"내용 동일"*이다.
둘 다 M1이 **기록**으로 판정하던 자리인데 실물에서는 기록과 본체가 갈릴 수 있다 — 기록만 사라지고
본체가 남은 슬롯이 있고, 기록은 A라는데 본체는 B인 슬롯도 있다(`write_profile`의 half-write).
M1의 「묻지 않고 진행」은 앞에서 본체를 대피 없이 지웠고, 뒤에서는 확인창 없이 대피·축출을 실행했다.
그래서 두 갈래 모두 판정이 **본체**를 본다 — 뒤쪽은 엔진과 **같은 술어**(`store.slot_holds`)를
같은 인자로 부른다. 나머지 세 분기는 그대로 동치다(`qa/test_confirm_equivalence.py`).
"""
import os

from . import codes, engine, store

# `disk_state` 4분류 — M1은 화면 문구를 합쳤지만 코드는 갈라 둔다.
# 합쳐 두면 `"unknown"`이 *"게임에서 조정함"*과 *"조회 실패"* 두 뜻을 갖게 되어
# 프론트가 문구를 고를 수 없다(설계 §2-E-0).
OTHER_PROFILE = "other_profile"   # 다른 프로필과 일치 — 그 이름을 같이 싣는다
UNKNOWN = "unknown"               # 어느 프로필과도 다름 — 게임에서 조정한 것으로 보인다
MISSING = "missing"               # 설정 파일이 없다
LOOKUP_FAILED = "lookup_failed"   # 조회 자체가 실패했다(권한·손상 등)


def _state_fp(meta_sha1, disk_sha1, ring):
    """저장·적용 토큰 지문의 **조립 규칙**은 여기 하나다 — 관측은 부르는 쪽이 한다(§14-G ⓕ).

    `(슬롯 meta의 sha1, 디스크 sha1 + 링 지문)`. 조회 실패는 `None`을 그대로 싣는다 —
    없음도 지문의 일부라, 조회 실패 상태에서 발급한 토큰은 조회가 되기 시작하면 거부된다
    (안전한 방향이다 — 다시 물으면 되고, 그 사이 사용자가 본 화면은 이미 낡았다).

    ★★ 둘째 칸에 **백업 링의 지문**을 합성한다(R14 #2). 저장·적용 확인창은 *"이 백업이
      지워집니다"*라고 **이름을 대며** 승인을 받는데, 그 사이 다른 동작이 링을 한 칸 돌리면
      승인 대상이 달라진다 — 예전에는 낡은 토큰이 그대로 통과해 **사용자가 승인하지 않은
      파일이** 지워졌다(포화 링에서는 개수도 그대로라 어떤 신호에도 안 걸렸다).
      합성이 안전한 이유는 `main._consume`이 튜플 **전체 동등 비교**만 하고 문자열을 되쪼개지
      않기 때문이다 — 슬롯 수를 늘리지 않고 지문만 넓힌다.
    ★ 이 함수는 예전 `main._state_fingerprint`가 하던 일의 **조립 절반**이다. 관측 절반은
      판정 함수로 옮겼다: 고지를 만들며 이미 읽은 값에서 지문이 나와야 그 사이의 변화가
      토큰에 구워지지 않는다(§14-G ⓕ).
    """
    return meta_sha1, "%s|ring=%s" % (disk_sha1, ring)


def _meta_sha1(appid, profile):
    """슬롯 meta가 **기록하고 있는 내용 sha1**. 못 읽거나 비-dict면 `None`.

    비-dict meta(손상 JSON)에서 `.get`이 AttributeError를 내면 저장 지문 산출이 통째로 죽는다
    (2026-08-09 조사) — 그래서 `isinstance`로 접는다. 조회 실패도 `None`이다."""
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        return None
    return meta.get("sha1") if isinstance(meta, dict) else None


def _ring_observe(appid, items=()):
    """§5-E-3의 산출 함수를 부른다 — **정본은 `restore.ring_observe` 하나**다(적용·저장 공용).

    돌려주는 것은 `{"evicted": [...], "fingerprint": …}`: **축출 예고와 그 지문이 한 번의
    나열에서 같이 나온다**(§14-G ⓕ — 일괄 적용·전체 초기화가 쓰던 문법 그대로다).

    `items`는 그 동작이 **만들려는 백업들**(`(tag, sha1)` 쌍)이다. 개수가 아닌 이유는 §14-G ⓔ:
    같은 태그에 같은 내용이 이미 있으면 아무것도 안 만들고, 안 만들면 안 지운다. 그 중복 판정도
    **같은 한 번의 나열** 안에서 이뤄진다(ⓕ) — 부르는 쪽이 미리 세면 나열이 둘이 된다.

    ⚠️ import를 함수 안에서 한다: `restore`가 이 모듈을 import하므로(restore.py 상단)
      최상단에서 맞import하면 순환이 된다. 순환을 CPython의 부분초기화 동작에 기대는 것보다,
      **부르는 자리에서 한 줄**로 끊는 편이 실패 모드가 없다(그 기대가 깨지면 플러그인이
      통째로 안 뜬다).
    """
    from . import restore
    return restore.ring_observe(appid, items)


def needs_confirm(reg, appid, profile):
    """`(need, params, fingerprint)` — 저장이 기존 프로필을 실제로 덮어쓰는가.

    `need`가 True일 때만 `params`에 확인창이 쓸 정보가 실린다
    (`size` · `sha1_short` · `saved_at` · `disk_state` [· `matched_profile`]).

    ★★ **지문을 params와 함께 낸다**(15판 §14-G ⓕ). 예전에는 접착층이 고지를 받은 **뒤**
      `main._state_fingerprint`를 불러 meta·디스크·링을 **다시** 읽었고, 그 두 관측 사이의
      변화는 토큰에 구워져 영구히 안 보였다. 지금은 고지에 쓴 바로 그 관측값이 지문이 된다.
    ⚠️ 지문은 **묻는 갈래에서만** 낸다(`need`가 False면 `None`) — 토큰을 쓰지 않는 갈래라
      잴 것이 없고, 재면 정상 저장마다 링 나열이 붙는다.
    ⚠️ **지문은 봉투로 나가지 않는다** — `params`가 아니라 **세 번째 반환값**이다.
    """
    appid = str(appid)
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        # ★ 여기서 막지 않는다 — **M1과 같은 자리에서 같은 방식으로** 실패해야 한다.
        #   저장을 진행하면 `engine.save_profile`이 같은 meta를 다시 읽고 실패하므로
        #   **결과는 「아무것도 안 쓰고 실패」**로 M1과 동치다(설계 5분기표 4행).
        #   ⚠️ 그래서 이 note의 문구는 *"확인 없이 저장을 시도합니다"*가 아니라
        #      **"프로필 정보가 손상되어 저장할 수 없습니다"**로 옮겨야 한다 — 결과와 어긋나면 오정보다.
        return False, {"note": "META_UNREADABLE"}, None

    # ★★ 판정은 「기록이 있는가」가 **아니라** 「본체가 있는가」다(설계 §14-G ⓐ). 예전에는
    #   `if not meta:`였다 — `meta.json`이 없거나 `{}`·`null`·`0`·`""`이면 **정상 본체가 바로
    #   옆에 있어도** 빈 슬롯으로 접혀 **확인 없이** 덮였다. 엔진의 무대피와 한 쌍이라
    #   그 프로필은 슬롯에도 백업 링에도 안 남았고, 화면은 그 상태를 「프로필 없음」으로 말해
    #   **재저장이 곧 파괴 트리거**였다. 정책층만 고치면 *"묻기는 하는데 승인하면 여전히 무백업
    #   삭제"*가 되므로 `engine.save_profile`과 **함께** 고쳐야 한 사건이 닫힌다.
    # ★★ **이 목록이 곧 엔진이 대피시킬 목록이다**(같은 `store.evacuable_names`를 돈다).
    #   예전에는 `_slot_backup_pending`이 엔진 조건을 **거울처럼 흉내 냈는데**, 흉내는 언젠가
    #   어긋나고 어긋나는 순간 화면이 *일어나지 않을 삭제*를 말하거나 *일어날 삭제*를 침묵한다.
    #   거울을 없애고 같은 술어를 직접 본다 — 축출 예고의 **개수**도 여기서 나온다(아래 `evicted`).
    bodies = store.evacuable_names(appid, profile)
    if not bodies:
        return False, {}, None                # 진짜 빈 슬롯 — 잃을 것이 없다(엔진도 대피하지 않는다)
    if not isinstance(meta, dict):
        meta = {}                             # 기록은 못 믿어도 본체는 있다 — 재료는 아래에서 실측한다

    try:
        state = engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError):
        state = None                          # ★ `{}`가 아니라 `None` — 아래에서 「조회 실패」와
                                              #   「파일 없음」을 갈라야 하기 때문이다
    disk_sha1 = state.get("sha1") if state else None

    # ★★ 「이미 같다」도 **기록이 아니라 본체**로 판정한다(설계 §14-G ⓐ / QA R1 D-1, 2026-08-22).
    #   예전에는 `disk_sha1 == meta.get("sha1")`이었다 — **기록만** 보는 판정이다. 그런데 같은
    #   질문에 엔진(`engine.save_profile`)은 `store.slot_holds`로 **본체 실측**을 했고, 두 술어가
    #   갈리는 상태가 실재한다: `write_profile`이 본체를 먼저 쓰고 meta를 나중에 쓰므로 그 사이에
    #   죽으면 **본체 B · meta.sha1 A**가 남는다(`qa/test_slot_body_truth.py`가 정상 도달 경로로
    #   적어 둔 그 상태다). 디스크가 A면 정책층은 *"이미 같다"*며 **안 묻고**, 엔진은 다르다며
    #   **대피·쓰기·축출을 실행했다** — 확인창이 한 번도 안 뜬 채 포화 링의 최고령 백업이
    #   고지 없이 사라진다. 확인창의 계약(*"무엇을 잃는지 이름으로 말한다"*)이 통째로 깨지는 갈래다.
    # ★★ 그래서 **같은 함수를 같은 인자로** 부른다 — 값 비교를 두 벌 적으면 그것이 또 하나의
    #   거울이고(§14-G ⓐ가 `_slot_backup_pending`을 없앤 이유), 거울은 언젠가 어긋난다.
    #   엔진은 `store.slot_holds(appid, profile, store.sha1_bytes(data), os.path.basename(path))`를
    #   부르는데 그 `path`가 곧 `entry["config_path"]`이고 `data`가 그 파일의 바이트다 —
    #   여기 `disk_sha1`(= `store.sha1_file(entry["config_path"])`)과 아래 `config_name`이
    #   **같은 두 값**이다(engine.py:365-368·399).
    # ★ `state`가 `None`(조회 실패)이면 `disk_sha1`도 `None`이라 `slot_holds`가 곧바로 거짓이다 —
    #   옛 `state is not None` 가드가 하던 일을 술어가 이미 한다(모르면 묻는 쪽으로 접힌다).
    entry = store.game(reg, appid) or {}
    config_name = os.path.basename(entry.get("config_path") or "")
    if store.slot_holds(appid, profile, disk_sha1, config_name):
        return False, {}, None                # 내용이 이미 같다 — 덮어써도 달라지는 것이 없다

    # ★★ 표시 재료는 **필드 단위로** 기록과 실측을 가른다(설계 §14-G ⓐ / 2026-08-22 보강).
    #   예전에는 `if not meta:` 하나였다 — 그래서 `{"foo": 1}`처럼 **비지는 않았지만 크기·해시가
    #   없는** 기록에서는 그 갈래에 못 들어가고, 화면이 멀쩡한 본체를 옆에 두고 *"지금 저장돼
    #   있는 것: 0 B"*라 말했다. 「기록이 통째로 비었나」가 아니라 **「이 칸을 못 믿나」**가
    #   기준이어야 갈래가 하나 남는다(구조로 예외를 없앤다).
    #   기록이 멀쩡하면 실측하지 않는다 — 기존 문구·검사가 그 값을 전제한다.
    size, sha1_short = _slot_materials(appid, profile, meta, bodies)
    # ★★ 축출 예고의 개수는 **실제로 링에 쌓일 백업 수**다(설계 §14-G ⓔ). 대피 대상은 위
    #   `bodies` 전부지만, 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이 아무것도
    #   쓰지 않으므로 **지워지는 백업도 없다.** 목록의 길이를 그대로 쓰면 확인창이 이름을 대며
    #   *일어나지 않을 삭제*를 약속한다. 판정은 엔진의 무쓰기 갈래와 **같은 술어**
    #   (`store.backup_holds`)를 지난다 — 규칙을 여기 다시 적으면 언젠가 어긋난다.
    directory = store.profile_dir(appid, profile)
    tag = store.profile_tag(profile)
    ring = _ring_observe(
        appid, [(tag, store.sha1_file(os.path.join(directory, name))) for name in bodies])
    params = {
        "size": size,
        "sha1_short": sha1_short,
        # ★ `saved_at`은 **기록에서만** 온다. 기록이 없으면 저장 시각은 **모르는 것이 사실**이고,
        #   파일 mtime은 저장 시각이 아니다(복사·복원·터치로도 바뀐다) — 지어내면 그 자체가 거짓이다.
        "saved_at": meta.get("saved_at") or "",
        "disk_state": _classify(state),
        # ★ 이 저장이 **실제로 지울 백업**(R14 #1 — 적용·복원과 같은 필드·같은 문구).
        #   저장은 슬롯을 덮기 전에 본체를 대피시키고, 그 대피가 링을 **본체 수만큼** 태운다.
        #   ★★ 그래서 `adding`은 1이 아니라 **실제로 쌓일 대피본의 수**다: 하드코딩된 1은 본체가
        #     하나뿐일 때만 맞는 숫자였고, 본체가 둘 이상인 슬롯에서 화면이 **실제보다 적은
        #     축출을 예고**한다 — 이 확인창은 지워질 백업을 *이름으로* 대는 자리라 예고한 목록과
        #     실제 축출이 일치해야 한다(설계 §14-G ⓐ / 조사 §2-B). 반대 방향의 거짓말(중복이라
        #     안 만드는데 지운다고 말하기)은 `ring_observe`가 그 한 나열 안에서 막는다(§14-G ⓔ).
        #   대피가 없는 갈래(본체 0개)는 여기 오지 않는다 — 위에서 이미 「안 묻는다」로 돌아섰다.
        #   ★★ 그 목록과 **그 지문이 한 번의 나열에서 같이 나온다**(§14-G ⓕ) — 아래 토큰 지문이
        #     쓰는 링이 지금 화면이 이름을 대는 바로 그 링이다.
        "evicted": ring["evicted"],
    }
    if state is not None and state.get("matches"):
        params["matched_profile"] = state["matches"]
    return True, params, _state_fp(meta.get("sha1"), disk_sha1, ring["fingerprint"])


def _slot_materials(appid, profile, meta, bodies):
    """확인창이 대는 `(size, sha1_short)` — **기록이 못 미더운 칸만 본체에서 잰다**(§14-G ⓐ).

    ★★ 왜 필드 단위인가: 이 확인창은 「무엇을 잃는가」를 대는 자리다. 기록이 통째로 비었을
      때만 실측하면, `{"foo": 1}`처럼 **비지는 않았는데 크기·해시가 없는** 기록에서 화면이
      멀쩡한 본체를 옆에 두고 *"지금 저장돼 있는 것: 0 B"*라 말한다 — 고지가 아니라 오정보다.
      갈래를 넓히는 대신 **판정의 단위를 바꾸면** 그 예외 자체가 없어진다.
    ★ 재는 대상은 **엔진이 대피시킬 바로 그 목록**(`bodies` = `store.evacuable_names`)이다 —
      규칙을 여기 다시 적으면 언젠가 한쪽만 어긋나 화면과 실제가 갈린다.
    ★ 해시는 **본체가 하나일 때만** 댄다. 여럿인데 하나를 고르면 화면이 *어느 것의 해시인지
      말할 수 없는 값*을 사실처럼 내놓는다 — 그건 거짓말이다. 모르면 비운다.
    ★ 실측이 실패해도(OSError) **저장을 막지 않는다**: 그 값만 0·빈 문자열로 두고 확인창은
      그대로 뜬다. 이 갈래의 본질은 확인과 대피이지 표시값이 아니다.
    """
    size = meta.get("size") or 0
    sha1_short = (meta.get("sha1") or "")[:10]
    # ★★ **기록은 「본체와 맞을 때만」 믿는다**(사용자 결정 D8의 형제 자리 — QA DEFECT-04).
    #   필드가 비지 않았다는 것은 *"기록이 있다"*이지 *"기록이 맞다"*가 아니다. 같은 `meta`의
    #   같은 두 필드(`size`·`sha1`)를 쓰는 크기 가드(`engine.save_profile`)는 이미
    #   `store.slot_holds`로 그 조건을 걸었는데 이 화면만 안 걸고 있었다.
    #   ⚠️ 이 반쪽 상태(본체 새것 · 기록 옛것)는 **이 캠페인이 스스로 적어 둔 도달 경로**다 —
    #     `main.save_profile`의 `except OSError`가 *"본체를 먼저 쓰고 기록을 나중에 쓰므로
    #     반쪽 상태가 남을 수 있다"*고 말한 그 상태다. 거기서 확인창이 **잃지 않을 것의
    #     크기·해시**를 댔다(실측: 기록 4 B/9dc9cfd3b3 ↔ 본체 20 B/8d93f3af2a).
    trusted = store.slot_holds(appid, profile, meta.get("sha1"), meta.get("filename"))
    if size and sha1_short and trusted:
        return size, sha1_short               # 기록이 본체와 맞는다 — 파일을 다시 열지 않는다
    if not trusted:
        # ★ 기록이 본체와 **어긋난다** — 값이 차 있어도 그 칸을 쓰면 안 된다. 비워서 아래
        #   실측 갈래로 보낸다(비어 있던 칸을 채우는 기존 문법과 같은 자리를 지난다).
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


#: 개별 적용 판정의 3-상태 (설계 §5-E-2). `restore.needs_confirm`과 **같은 문법**이다.
APPLY_STATES = ("already", "proceed", "confirm")


def _disk_state_or_none(reg, appid):
    """`engine.disk_state`는 fence 대상이라 비-dict meta에서 AttributeError를 낸다(engine.py:306).
    적용 판정이 손상 슬롯 하나로 죽으면 **묻지도 못하고 실패**하므로 조회 실패(`None`)로 접는다 —
    `restore._disk_state`·`main._disk_state_safe`와 같은 판단·같은 이유다.
    `{}`가 아니라 `None`인 것이 중요하다: 아래에서 「조회 실패」와 「파일 없음」을 갈라야 한다."""
    try:
        return engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError, AttributeError, TypeError):
        return None


def _matching_profiles(appid, disk_sha1):
    """디스크 내용과 같은 슬롯 **전부**. `engine.disk_state`의 first-match break를 쓰지 않는다.

    ★ 왜 다시 도는가: 엔진은 첫 일치에서 멈추므로(engine.py:306-309) 두 슬롯 내용이 같을 때
      **임의로 한쪽만** 고른다. 그 값을 화면 마커로 쓰면 나머지 한쪽을 "적용돼 있지 않다"고
      거짓으로 말한다(설계 §5-A). 판정을 여기서 하면 봉투가 사실대로 배열을 싣는다.
    ⚠️ 비용을 정직하게: **슬롯 meta 2개 + (일치할 때만) 그 본체를 다시 읽는다.** `disk_state`가
      방금 읽은 값을 못 쓰는 이유는 그것이 first-match에서 멈춰 **나머지 슬롯을 아예 안 보기**
      때문이다.
      (`get_overview`는 이 함수를 쓰지 않는다: 거기서는 `_slot_view`가 이미 두 sha를 들고 있어
       파일 접근이 실제로 0 증가다 — `main._disk_matches`.)

    ★★ 판정은 **본체 실측까지**다(`store.slot_holds` — R14 #4). meta만 보면 *"이 내용은 저
      슬롯에 보존돼 있다"*가 거짓일 수 있고, 이 값이 곧 **묻지 않고 진행 + 대피 생략**의 근거라
      거짓인 순간 디스크의 마지막 온전한 사본이 고지 없이 사라진다. 모르면 목록에서 뺀다.
    """
    if not disk_sha1:
        return []
    return [p for p in ("dock", "internal") if store.slot_holds(appid, p, disk_sha1)]


def apply_needs_confirm(reg, appid, profile):
    """`(state, params, fingerprint)` — 개별 적용의 **3-상태 계약**이다(설계 §5-E-2).

        "already"  게임 설정 파일이 이미 목표 슬롯과 같다 → 접착층이 **엔진을 부르기 전에**
                   반환한다. 파일도 링도 건드리지 않는다.
        "proceed"  파일이 없거나(재생) **다른 슬롯과 같다**(그 내용은 이미 슬롯에 보존돼 있다)
                   → 잃을 것이 없으므로 묻지 않는다. 계약의 절반은 묻지 않는 것이다.
        "confirm"  두 슬롯 모두와 다르다(또는 조회 실패) → **이 파일에만 있는 내용이 사라질 수
                   있는 갈래**다. 확인 토큰을 요구한다.
                   ⚠️ **「유일한」이 아니다**(2026-08-22 정정): 여기 온다고 반드시 잃는 것은
                   아니다 — 슬롯 본체가 깨진 상태도 이 갈래로 오고, 그때는 승인해도 엔진이
                   `PROFILE_CORRUPT`로 거부해 아무것도 안 바뀐다(설계 §15-D E10).
                   계약은 *"잃을 수 있으면 묻는다"*이지 *"물으면 잃는다"*가 아니다.

    ★ 실행 중 게임은 상태 판정 **전에** 조기 거부한다(`restore.needs_confirm`과 같은 자리·같은
      이유): 엔진 G5가 확정적으로 거부할 것을 확인창까지 통과시켜 토큰을 태우는 것은 무의미한
      마찰이다. 집행의 문은 여전히 엔진 G5 하나이고, 확인창 사이에 게임이 켜지는 TOCTOU는 그 G5가
      같은 코드로 잡는다.
    ★ 슬롯 없음·손상은 **조기 거부하지 않는다** — 근거는 **미러를 늘리지 않는다** 하나다
      (온전성을 미리 대조하면 판정층이 엔진의 검사를 흉내 내게 된다 — 설계 §15-D E10).
      확인 뒤 엔진이 `PROFILE_CORRUPT`로 거부하고 **파일은 한 바이트도 안 바뀐다**(링도 안 돈다).
      ⚠️ **2026-08-22 정정(실측)**: 예전에 여기 함께 적혀 있던 두 절(*"버튼이 이미 비활성이다"* ·
        *"도달하려면 확인창을 띄운 사이 슬롯이 사라져야 한다"*)은 **둘 다 거짓이다.** 본체만 깨진
        슬롯에서 `main._slot_view`는 *"meta가 읽히고 본체 파일이 **존재**한다"*까지만 재므로
        `has_dock=True`이고, 프론트의 활성 조건이 `busy || !has[p]`라 **버튼은 활성**이다
        (화면도 「저장됨 · 날짜」로 그린다). 경합 없이 **한 번의 탭으로 도달한다.**

    ★★ **지문을 params와 함께 낸다**(15판 §14-G ⓕ). 예전에는 접착층이 3-상태를 받은 **뒤**
      `main._state_fingerprint`를 불러 meta·디스크·링을 **다시** 읽었고, 그 두 관측 사이의
      변화는 토큰에 구워져 영구히 안 보였다(디스크 sha1은 이 route에서만 **두 번** 읽혔다).
    ⚠️ 지문은 **`confirm` 갈래에서만** 낸다(`already`·`proceed`는 `None`) — 토큰을 쓰지 않는다.
    ⚠️ **지문은 봉투로 나가지 않는다** — `params`가 아니라 **세 번째 반환값**이다.
    """
    appid = str(appid)
    engine.game_or_fail(reg, appid)                  # 미등록 → GAME_NOT_REGISTERED
    if engine.running_game(appid):                   # 조기 거부 (§5-E-2)
        raise engine.Refused(
            "거부: 게임이 실행 중입니다. 게임을 완전히 종료한 뒤 적용하십시오.",
            code=codes.GAME_RUNNING, appid=appid)

    state = _disk_state_or_none(reg, appid)
    disk_sha1 = state.get("sha1") if state else None
    matches = _matching_profiles(appid, disk_sha1)
    params = {
        "appid": appid,
        "profile": profile,
        # 덮어쓸 대상(=게임 설정 파일)이 지금 어떤 상태인가 — 저장·복원 확인창과 **같은 4분류**다.
        "disk_state": _classify(state),
        "matches": matches,
        # 이 적용이 **백업 링에 한 칸을 쓰는가**(QA R1 D-3 — 화면의 「백업 한 칸을 씁니다」가
        # 참인 조건). **복원과 같은 필드·같은 기본값·같은 술어다**(restore.needs_confirm).
        # 기본은 **거짓**이다: 약속은 그것이 참인 갈래에서만 켠다 — 없는 대피를 말하면 사용자는
        # 남아 있지도 않을 복구 지점을 믿고, 링 잔량을 아끼려고 적용을 미룬다.
        # ★ **같은 내용이 이미 `disk` 태그의 링에 있으면 거짓이다**(§14-G ⓔ): `make_backup`이
        #   아무것도 쓰지 않으므로 칸을 안 태우고, 안 태우니 축출도 없다(`evicted`도 빈다).
        #   판정을 여기 다시 적지 않는다 — 아래 한 번의 링 나열이 `adding`으로 답한다(ⓕ).
        # ⚠️ 이 값이 뜻을 갖는 것은 **`confirm` 갈래**다(화면이 그때만 읽는다).
        "evacuates": False,
        # 이 동작이 백업을 1건 만들 때 **실제로 지워질** 파일들(설계 §5-E-3). 적용·복원 공용이다.
        # ★ **`confirm` 갈래에서만 채운다**(복원과 대칭 — §5-C ⓖ): `already`는 무쓰기이고,
        #   `proceed`는 잃을 것이 없는 갈래라 **대피본을 만들지 않는다**(§14-B). 링을 안 쓰는
        #   갈래에 고지를 실으면 화면이 *일어나지 않을 삭제*를 말한다.
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
    # ★ 이 값은 **지문의 meta 칸**이다(§14-G ⓕ) — 아래 판정은 이 값을 쓰지 않지만, 토큰은
    #   여기서 **한 번만** 읽은 그 값을 쓴다(관측을 늘리지 않는다).
    target_sha1 = meta.get("sha1") if isinstance(meta, dict) else None
    # ★★ 「이미 같다」는 **기록이 아니라 본체 실측**이다(2026-08-22 — QA R2 N-1, 사용자 결정).
    #   `target_sha1 == disk_sha1`로 판정하면 **본체만 깨진 슬롯**에 대고 화면이 *"이미
    #   적용됨"*이라 답한다. 그 순간이 고치기 가장 쉬운 자리인데(디스크에 그 내용이 그대로
    #   있어 [저장] 한 번이면 슬롯이 되살아난다) 앱이 침묵하고, 다른 프로필을 한 번 거치고 나면
    #   같은 버튼이 `PROFILE_CORRUPT`로 막힌다 — 고칠 수 있던 시점을 놓치게 만든다.
    #   복원의 `already`가 R14 #5에서 **같은 이유로** 이미 본체 실측이다 — 같은 문법이다.
    # ⚠️ **판정 자체의 추가 IO는 0이다**: `matches`는 두 줄 위(`_matching_profiles`)에서 이미 두
    #   슬롯 양쪽에 `store.slot_holds`를 돌려 놓았다. 이 한 자리에서만 §15-D E18의 비용 근거가
    #   성립하지 않는 이유이고, 그것이 여기만 고치는 근거다(나머지 셋은 게임 수만큼 비용이 붙는다).
    #   ⚠️ **「이 변경의 IO가 0」은 아니다**(실측): `already`였던 상태가 `confirm`으로 옮겨가면
    #     그 갈래가 링을 한 번 나열한다 — 포화 링에서 `sha1_file` **3회 → 13회**(`load_meta`는
    #     4회로 불변). 늘어난 것은 판정이 아니라 **갈래 이동분**이다.
    if profile in matches:
        return "already", params, None
    if matches:
        return "proceed", params, None               # 다른 슬롯과 같다 — 그 내용은 보존돼 있다
    # ★ 여기서만 대피본이 생긴다(§14-B). 그마저도 **같은 태그에 같은 내용이 이미 있으면
    #   만들어지지 않으므로**(§14-G ⓔ) 지워질 백업도 없다 — 엔진의 무쓰기 갈래와 같은 술어를
    #   본다(`store.backup_holds`). 디스크 sha1은 위에서 이미 잰 그 값이다(관측을 늘리지 않는다).
    ring = _ring_observe(appid, [(store.KIND_DISK, disk_sha1)])
    # ★ 고지·지문·**대피 여부**가 전부 그 한 나열에서 나온다(ⓕ) — 링을 **다시 관측하지 않는다.**
    #   `adding`이 0이면 링에 한 칸도 안 쌓이므로 「백업 한 칸을 씁니다」도 거짓이고 지워질
    #   것도 없다(복원 확인창과 **같은 모양**이다 — restore.py의 같은 두 줄).
    params["evacuates"] = bool(ring["adding"])
    params["evicted"] = ring["evicted"]
    return "confirm", params, _state_fp(target_sha1, disk_sha1, ring["fingerprint"])


def already_registered(reg, appid):
    """이미 등록된 appid인가 — 맞으면 화면이 쓸 `params`, 아니면 `None`. (2026-08-07 QA R2)

    ★ 왜 여기인가: `engine.add_game`은 기존 entry에 `config_path`를 **무조건 덮어쓴다**
      (`:420-426`의 `setdefault` + `entry.update`). 그래서 같은 appid로 다시 등록하면 경로가
      조용히 바뀌고, 그 다음 `apply_profile`이 **새 경로의 파일을 프로필 내용으로 덮어쓴다.**
      QA가 합성 데이터로 실피해를 재현했다(`UNRELATED_FILE_OVERWRITTEN=True`).

      막을 자리는 셋 중 하나인데 —
        엔진   → M1과 바이트 동일선(diff fence)을 깬다
        main   → *"접착층은 정책 판단 금지"*(§2-C)
        프론트 → 버튼을 숨겨도 route 계약은 열려 있다(QA가 지적한 바로 그 구멍)
      → `needs_confirm`과 같은 이유로 **여기**가 자리다.

    ⚠️ 경로 변경 자체를 지원하지 않는다. 지금 필요한 것은 *"조용히 바뀌지 않는 것"*이고,
      경로 변경 전용 확인 계약은 그것을 원하는 화면이 생길 때 만든다(백로그).
    """
    entry = (reg.get("games") or {}).get(str(appid))
    if entry is None:
        return None
    return {"appid": str(appid),
            "name": entry.get("name") or ("appid %s" % appid),
            "config_path": entry.get("config_path") or ""}


def add_game_needs_confirm(warnings):
    """수동 등록이 **저장 전에** 되물어야 하는가. (2026-08-07 QA R1)

    ★ 계약의 절반은 **묻지 않는 것**이다. 자동 탐지 후보는 구조적으로 경고가 없고, 무경고 수동
      선택도 마찬가지다 — 거기까지 되물으면 `save_profile`이 명시적으로 피한 *확인창 지옥*이
      등록 경로에 그대로 재현된다.
    """
    return bool(warnings), {"warnings": list(warnings)}


# ── 일괄 적용 미리보기 (F8 / P10) ────────────────────────────────────────────
#
# ★★ **판정 미러가 두 곳이 되는 것을 감수한 자리다.** 엔진에 dry-run 플래그를 넣는 것은
#   diff fence 위반이라 불가능하므로, 미리보기는 `engine.apply_all`의 판정을 **읽기 전용으로
#   재현**한다. 그래서 계약을 문서가 아니라 **테스트로** 못박는다
#   (`qa/test_apply_preview_equivalence.py` — 적대 합성 세계 전수).
#
# ★ 버킷은 **5개**이고, 엔진 `BULK_OUTCOMES` 5종(engine.py:551)을 **빠짐없이 안전하게 분류**한다.
#   ⚠️ 표현 주의(2026-08-10 최종 QA): 이것을 *"1:1"*이라고 부르면 안 된다 — 아래 표대로
#     `running_refused`는 `refused` 중 실행 중인 것만, `cannot_apply`는 나머지 `refused`와
#     `error`를 **함께** 받는다. 즉 버킷→outcome은 다대일이 섞인 **전사(全射) 분류**이고,
#     보장하는 것은 ① 모든 outcome이 어느 버킷엔가 든다 ② 게임 하나는 정확히 한 버킷에만 든다
#     ③ 어긋나더라도 "적용된다 해 놓고 안 되는" **안전한 방향**이다 — 이 셋이다.
#   4버킷(refused/error를 would_apply로 셈)은 반증에서 잡힌 오산이다 —
#   "적용 예상 9개"라고 해 놓고 실제로는 3개만 되는 화면이 나온다.
#: 미리보기 버킷 ← 엔진 outcome: would_apply←applied · already←already ·
#: no_profile←no_profile · running_refused←refused(GAME_RUNNING) · cannot_apply←refused(기타)+error
APPLY_BUCKETS = ("would_apply", "already", "no_profile", "running_refused", "cannot_apply")


def _preview_one(reg, appid, profile, running):
    """게임 하나가 어느 버킷에 드는가. **판정 순서 = 엔진 실행 순서**다.

    ★ 순서가 계약이다(설계 §3-B 2조). `already` 판정이 G5(실행 중)보다 **먼저**이므로
      (engine.py:594-598이 `apply_profile` 진입 전에 스킵한다) **실행 중이어도 디스크==프로필이면
      `already`**다. 순서를 바꾸면 화면이 "실행 중 N개는 거부 예상"이라고 말하는데 실제로는
      조용히 already가 되어, 미리보기와 결과가 어긋난다.

    ★ 예외는 **이 함수 밖에서** 게임별로 격리된다(`apply_all_preview`) — 엔진 외곽 try와 동형이다.
    """
    meta = store.load_meta(appid, profile)
    if not meta:
        return "no_profile"
    try:
        state = engine.disk_state(reg, appid)
    except Exception:                      # noqa: BLE001 — 엔진의 같은 자리(engine.py:592-593)와 동형
        state = {}
    if state.get("sha1") and state["sha1"] == meta.get("sha1"):
        return "already"
    # ★ `config_path`가 없는 등록 항목(손상·수동 편집)은 엔진이 **error**를 낸다 —
    #   `apply_profile`이 `entry["config_path"]`에서 KeyError를 내고(engine.py:469) 그 예외가
    #   외곽 try에 잡힌다. 그 판정이 **G5보다 먼저**라(경로를 먼저 읽는다) 실행 중이어도 error다.
    #   이 줄이 없으면 미리보기는 `would_apply`라고 세고 실행은 실패한다 — "적용된다 해 놓고
    #   안 되는" 어긋남이다(2026-08-10 qa-lead 권고 4-A. QA 5라운드 R1과 같은 버그 클래스).
    if not (reg.get("games") or {}).get(str(appid), {}).get("config_path"):
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
    """일괄 적용이 **무엇을 할 예정인가** — 5버킷 개수. **아무것도 쓰지 않는다.**

    `running`은 접착층의 `_running_appids()`가 준 집합이다(/proc 1회 스캔) — 게임마다
    `engine.running_game`을 부르면 등록 수에 정비례하는 재스캔이 된다.

    ★★ **게임별 예외 격리가 엔진과 동형이다**(설계 §3-B 1조). `store.load_meta`는 손상 JSON에서
      예외를 그대로 던지는데(store.py:235-240, json.load 무보호) 격리가 없으면 **meta 손상
      1건이 미리보기 전체를 UNEXPECTED로 만들어** `CONFIRM_REQUIRED`가 영영 안 나오고
      **일괄 적용 버튼이 전면 불능**이 된다. 엔진은 그 게임만 `error`로 강등하고 계속 가므로,
      미리보기가 전멸하면 "하나가 실패해도 나머지는 계속"이 미리보기 층에서 뒤집힌다.
      → 어떤 예외든 그 게임만 `cannot_apply`로 강등하고 **다음 게임을 계속**한다.

    ⚠️ 예측하지 **못하는** 것이 있다 — 실행 시점에만 나는 실패(G11 경로 가드·G4 크기 검사·
      `BACKUP_FAILED` 등)는 `would_apply`로 세어 놓고 실제로는 `refused`가 될 수 있다.
      그래서 화면 문구는 **「예상」**이고, 결과의 정본은 실행 후 요약·로그다. 미리보기는
      *분류*이지 실행이 아니다(설계 §3-B 후단).
    """
    counts = dict.fromkeys(APPLY_BUCKETS, 0)
    for appid in sorted(reg["games"]):
        try:
            bucket = _preview_one(reg, appid, profile, running)
        except Exception:                  # noqa: BLE001 — 엔진 외곽 try(engine.py:579-580)와 동형
            bucket = "cannot_apply"
        counts[bucket] += 1
    return counts


def apply_all_evict_preview(reg, profile, running):
    """일괄 적용이 **실제로 지울 백업** — `{"evicted": N, "evict_games": M, "fingerprint": …}`.

    ★★ 왜 이름을 대지 않는가(R14 #1): 게임이 여럿이라 게임마다 나열하면 확인창이 터진다.
      그래서 **수만 약속하고**, 그 수는 게임별 산출(`restore.evict_preview`)의 합이라 나열본과
      같은 근거에서 나온다. 이름이 필요한 자리는 게임이 하나인 확인창들(저장·적용·복원·등록
      해제)이고 거기서는 이름을 댄다. **수가 정확하면 인지 요건은 충족된다**(세션 확정
      2026-08-15) — 읽히지 않는 열 게임짜리 목록은 인지시킨 것이 아니다.
    ★★ 수가 어긋나지 않는 근거: ⓐ 판정 순서가 엔진과 같고(`_preview_one`) ⓑ 대피 조건도 엔진과
      같으며(디스크가 있고 어느 슬롯에도 보존돼 있지 않을 때만 — engine.apply_profile)
      ⓒ **토큰이 이 산출의 지문에 묶인다**(아래).
    ★★ `fingerprint` — **화면에 실을 값이 아니라 토큰에 묶을 값**이다(2026-08-15 QA 재심 B).
      `remove.reset_fingerprint`만으로는 부족했다:
        · 그 지문의 링 신호는 **개수**뿐이라 포화 링이 도는 것(개수 불변)을 못 잡고,
        · 애초에 **설정 파일 sha는 의도적으로 빠져 있어**(§3-C) 확인창을 띄운 사이 게임·클라우드가
          설정 파일을 고유 내용으로 바꾸면 *"축출 0건"*이라 말한 토큰이 그대로 통과했다 —
          그 다음 실행이 대피본을 만들며 **고지하지 않은 백업 1건을 지웠다.**
      그래서 지문은 개수가 아니라 **대상 목록 그 자체**(`restore.evict_digest`)로 낸다.
    ⚠️ **재는 것 / 못 재는 것**(정직하게):
        재는 것  = 이 호출 시점에 각 게임에서 지워질 **backup_id 전량과 그 순서**. 하나라도
                   달라지면 지문이 달라져 낡은 토큰이 거부되고 새 목록으로 다시 묻는다.
        못 재는 것 = ⓐ 실행 시점에만 나는 실패(G11·G4·BACKUP_FAILED)로 적용이 거부되면 그 게임의
                   축출도 안 일어난다 — 예고보다 **덜** 지워지는 안전한 방향이라 화면은 「예상」이라
                   말한다. ⓑ 게임별 예외로 건너뛴 게임의 내부 상태(모르면 약속하지 않는다).
                   ⓒ **축출이 0건인 게임의 링 변화** — 지울 것이 없으면 약속한 것도 없다.
      ⚠️ **중복이라 대피본을 안 만드는 갈래(§14-G ⓔ)는 여기 안 든다** — 그것은 위에서 이미 세어
        뺐다(`store.plan_backups`). ⓐ와 섞어 읽지 말 것: ⓐ는 *실패*라 못 재는 것이고, 중복은
        **정상 갈래**라 재는 것이다. 둘을 뭉뚱그리면 "예고가 원래 헐겁다"는 변명이 생긴다.
      ⚠️ 그래서 §3-C의 *"디스크 sha1을 지문에서 뺀다"*는 **여전히 유효하되 범위가 좁아졌다**:
        설정 파일이 다시 쓰여도 토큰은 그대로다 — **그 변화가 지워질 백업을 바꾸는 때**(=그 게임의
        링이 이미 가득 찬 때)만 예외다. 그때는 확인→재확인이 마찰이 아니라 **고지의 정정**이다.
    ★ 비용은 등록 게임당 meta 1회 + 설정 파일 sha1 + backups 나열이고, **확인 호출과 실행 호출에서
      각 1패스**다(실행이 곧 그 파일들을 다 만지므로 정비례가 새로 생기는 것은 아니다).
    """
    from . import restore                     # 순환 회피 — `_evict_preview`와 같은 이유·같은 문법
    plan = []
    for appid in sorted(reg["games"]):
        try:
            if _preview_one(reg, appid, profile, running) != "would_apply":
                continue
            state = engine.disk_state(reg, appid)
            if not state.get("exists") or state.get("matches"):
                continue                      # 대피본을 안 만드는 갈래(§14-B)
            # ★ 같은 태그에 같은 내용이 이미 있으면 대피본이 **안 만들어진다**(§14-G ⓔ) —
            #   그 게임은 지울 것이 없으므로 plan에서 빠진다(중복이면 빈 목록이 돌아온다).
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
