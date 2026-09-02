"""삭제 정책 — 게임 개별 삭제와 전체 초기화.

파괴의 문은 `delete_game_data` 하나다. 개별 삭제도 전체 초기화도 이 함수를 지나고, 경로 봉쇄
가드도 그 문 안 한 곳에만 있다 — 두 곳에 두면 언젠가 한쪽이 빠지고, 빠진 곳이 곧 구멍이 된다.

지우는 것은 툴의 데이터뿐이다. 게임 설정 파일 원본(`entry["config_path"]`)에는 손대지 않고
`.sav`는 열지도 않는다. 그래서 G5(실행 중 게임) 가드를 걸지 않는다 — 실행 중인 게임과 이 동작
사이에 상호작용이 없으므로 막을 이유가 없고, 이유 없는 가드는 문법 오염이다.

실행 순서가 곧 안전장치다:
    1. 대피(`store.make_backup`)  2. meta.json unlink ×2  3. profiles/<appid>/ rmtree
    4. registry 항목 제거
`rmtree`가 본체만 지우고 meta.json을 남긴 채 중단되면, 「적용할 수 있는가」를 meta와 본체 둘 다로
재는 소비자(`main._profile_ready`)와 meta의 기록만으로 재는 소비자(`engine.apply_all`의 already)가
서로 다른 답을 낸다. 그래서 그 기록을 먼저 지운다 — 어느 지점에서 멈춰도 meta가 없으므로 적용
계열의 두 판정이 함께 「없음」이고, "프로필 없는 등록 게임"과 동형이라 다시 삭제하면 완결된다.

이 순서가 「모든 소비자를 끈다」는 뜻은 아니다. 삭제 확인창(`delete_preview`)은 기록이 아니라
본체로 판정하므로(`store.slot_body_exists`) meta unlink 뒤 rmtree 전의 중간 상태를 「프로필 있음」
으로 본다 — 그것이 옳다. 본체가 남아 있으면 되찾을 내용이 있고, 다시 삭제하면 그 본체가
정상적으로 대피된다. 이 순서가 지키는 것은 적용 계열의 두 판정이 서로 어긋나지 않는 것뿐이다.

`save_registry`는 여기서 부르지 않는다 — 호출자(접착층 route)가 부른다.
"""
import json
import logging
import os
import shutil

from . import codes, engine, store

#: 이 모듈의 실패는 `Refused.params`(봉투로 화면까지)와 여기에 동시에 남는다.
#: `main.route`의 거부 로그는 route 이름과 code만 남기므로, 부분 삭제 상태를 진단하려면
#: appid·중단 지점이 따로 필요하다. 레코드를 실제 로그 파일로 흘리는 배선은 접착층의 일이다 —
#: gfxp는 decky에 의존하지 않는다.
_log = logging.getLogger("gfxp.remove")

#: 프로필은 2개 고정이다. 자유 문자열을 받을 이유가 없다.
PROFILES = ("dock", "internal")

#: 안전하지 않은 키(경로 탈출)에 쓰는 고정 지문. 이 값은 어떤 실제 파일도 읽지 않고
#: 만들어지므로, `"../../X"`·절대경로 키의 meta·backups를 조회하지 않는다.
_UNSAFE_FP = "unsafe"


def _in_place(real_path, real_parent, name):
    """심볼릭 링크를 다 푼 실경로가 정확히 그 부모의 그 이름인가.
    (`..`·절대경로·경로 중간 링크·직접 링크·루트 안 남의 게임을 가리키는 링크를 한 번에 닫는다.)"""
    return (os.path.dirname(real_path), os.path.basename(real_path)) == (real_parent, name)


def slot_in_position(appid, profile):
    """읽기 전용 소비자를 위한 좁은 술어 — `profiles/<appid>`와 그 안의 슬롯 하나만 본다.

    왜 넓은 `_paths_in_position`을 그대로 쓰면 안 되는가: 그쪽은 `backups/<appid>`까지
    요구한다 — 대피·prune이 그 경로를 만지기 때문이다. 그런데 슬롯 meta만 읽는
    소비자(`main._slot_view`·`main._disk_state_safe`)는 backups를 읽지 않는다. 넓은 술어를 쓰면
    `backups/<appid>`만 링크인 정상 게임에서 화면이 슬롯을 "없음"으로 말한다 — 없는 사실을
    만드는 쪽이다. 술어는 그 소비자가 실제로 만지는 경로와 같아야 한다.
    기준점을 appid에서 파생시키지 않는다 — 고정 앵커(`profiles` 홈)에서 시작한다.
    """
    appid = str(appid)
    real_root = os.path.realpath(store.profiles_root(appid))
    home_prof = os.path.realpath(os.path.join(store.data_dir(), "profiles"))
    if not _in_place(real_root, home_prof, appid):
        return False
    # 슬롯 검사는 root가 `profiles/<appid>`로 확정된 뒤라야 real_root를 기준점으로 재사용해도
    # 안전하다(신뢰할 수 없는 값에서 기준점을 파생시키지 않는다는 위 원칙 그대로).
    return _in_place(os.path.realpath(store.profile_dir(appid, profile)), real_root, str(profile))


def _paths_in_position(appid):
    """이 appid가 만지게 될 모든 경로가 데이터 루트 안 제자리인가.

    검사 대상 = `profiles/<appid>` · 그 안의 두 슬롯 · `backups/<appid>`.
    심볼릭 링크를 전부 푼 뒤 정확 위치(dirname·basename)로 판정한다 — 이 한 함수가
    `..`·절대경로·경로 중간 링크·직접 링크·루트 안 남의 게임을 가리키는 링크를 전부 닫는다.

    파괴(rmtree·unlink)만이 아니라 대피(`store.make_backup`→`prune_backups`)와
    조회(`store.list_backups`·`store.load_meta`)가 전부 이 경로들을 지난다. 그래서 판정을 한 곳에
    두고 여러 갈래가 함께 쓴다:
      · 삭제 문(`delete_game_data`)은 `stage="escape"`로 거부
      · 지문·미리보기는 외부를 읽지 않고 센티널로 처리 — 안전하지 않은 키의 meta·backups를
        읽기 전에 통과시키지 않는다

    `backups/<appid>`까지 보는 이유: 1단계 대피가 `store.make_backup`→`prune_backups`를 거치는데,
    `backups/<appid>`가 외부 디렉터리 링크면 prune이 링크 너머 디렉터리를 열거해 초과분을
    `os.unlink` 한다 — 루트 밖 파일 삭제다. `prune_backups` 자신은 그 경로를 검사하지 않으므로
    막는 자리는 이 문이다.
    경로 정책을 `prune_backups`에도 적으면 같은 규칙이 두 곳에 살고, 이 함수가 여러 갈래의
    공용 술어 하나라는 구조가 깨진다. `store.py`는 정책 판단을 하지 않는 층이기도 하다.

    기준점을 appid에서 파생시키지 말 것 — `"../../X"` 키에서 기준점 자체가 같이 밀려나면
    검사가 무력해진다. 기준점(`profiles`/`backups` 홈)은 appid와 무관한 고정 앵커다.
    """
    appid = str(appid)
    # 프로필 루트·두 슬롯 판정은 좁은 술어 한 곳에 있다(위 `slot_in_position`) —
    # 같은 판정을 두 곳에 두면 언젠가 한쪽만 고쳐진다.
    for profile in PROFILES:
        if not slot_in_position(appid, profile):
            return False
    real_bk = os.path.realpath(store.backups_dir(appid))
    home_bk = os.path.realpath(os.path.join(store.data_dir(), "backups"))
    return _in_place(real_bk, home_bk, appid)


def _meta_observe(appid, profile):
    """슬롯 meta 파일을 한 번 읽어 `(기록, 파일 지문)`을 같이 낸다.

    · 기록      — dict가 아니면 `None`으로 접는다. 조회 실패(OSError·비JSON)뿐 아니라
      `"text"`·`[1]`·`1` 같은 유효 JSON이지만 객체가 아닌 meta도 여기서 접는다 — 그러지 않으면
      `.get()`이 `AttributeError`를 내고 삭제·초기화가 `UNEXPECTED`로 봉쇄된다.
    · 파일 지문 — meta 파일 자체의 sha1이다(기록의 `sha1` 필드가 아니다 — 아래
      `delete_fingerprint` 주석이 그 차이의 정본이다). 못 읽으면 `None`.

    왜 한 번에 내는가: 확인창은 이 기록으로 "{saved_at}에 저장됨"을 말하고 토큰은 같은 파일의
    지문에 묶인다. 고지와 지문이 각자 한 번씩 읽으면 그 사이에 저장이 끼었을 때 화면은 옛
    시각을 말하는데 토큰은 새 기록에 묶이고, 그 토큰은 2차 호출에서 그대로 통과한다.
    """
    path = store.profile_meta_path(appid, profile)
    try:
        raw = store.read_bytes(path)
    except OSError:
        return None, None                      # 없음·권한·디렉터리 — 지문도 없다("absent")
    digest = store.sha1_bytes(raw)
    try:
        meta = json.loads(raw.decode("utf-8"))
    except ValueError:                         # UnicodeDecodeError도 ValueError다
        return None, digest                    # 못 읽는 기록이어도 파일 지문은 사실이다
    return (meta if isinstance(meta, dict) else None), digest


def _delete_fp(meta_digests, backups):
    """개별 삭제 지문의 조립 규칙은 여기 하나다 — 관측은 부르는 쪽이 한다.

    자리가 둘이라서 뺐다: `delete_preview`(고지를 만들며 이미 읽은 값으로 낸다)와
    `delete_fingerprint`(다게임 `reset_fingerprint`가 게임마다 새로 관측해 부른다). 관측 시점이
    다른 것은 route가 다르니 정상이지만, 조립 규칙까지 갈리면 한쪽 토큰만 조용히 어긋난다.
    """
    return "|".join([(d or "absent") for d in meta_digests] + ["bk=%d" % backups])


def _evacuable_items(appid):
    """이 게임을 지울 때 링에 넣으려 할 백업들 — `(tag, sha1)` 쌍이다(축출 예고의 재료).

    세는 쪽(`delete_preview`·`evict_on_delete`)과 지우는 쪽(`_evacuate`)이 같은 목록을 돈다
    (`store.evacuable_names`). 규칙을 자리마다 다시 적으면 예고와 실제가 갈린다.
    개수가 아니라 목록을 돌려준다: 같은 태그에 같은 내용이 이미 있으면 `store.make_backup`이
    아무것도 쓰지 않으므로 지워지는 백업도 없다. 그 판정은 링을 봐야 하는데 여기서 미리 세면
    링 나열이 둘이 된다 — 그래서 무엇을 만들려 하는지만 모아 주고, 판정은
    `restore.ring_observe`의 한 나열에 맡긴다.
    대피 대상은 여전히 목록 전부다(그래서 `_evacuate`는 그대로 전부를 돈다). 두 슬롯은 태그가
    다르므로 내용이 같아도 각각 쌓이고, 한 슬롯 안에 내용이 같은 본체가 둘이면 그 둘은
    `store.plan_backups`에서 한 건이 된다."""
    items = []
    for profile in PROFILES:
        directory = store.profile_dir(appid, profile)
        tag = store.profile_tag(profile)
        for name in store.evacuable_names(appid, profile):
            items.append((tag, store.sha1_file(os.path.join(directory, name))))
    return items


def delete_preview(reg, appid):
    """`(params, fingerprint)` — 확인창이 보여줄 것 + 그 고지에 묶을 토큰 지문.
    순수 조회 — 아무것도 쓰지 않는다.

    미등록이면 여기서 `GAME_NOT_REGISTERED`가 난다(문은 `engine.game_or_fail` 하나).

    「저장돼 있나」의 판정 기준은 본체 존재다(`store.slot_body_exists`). 세는 쪽과 대피·삭제하는
    쪽이 같은 목록을 돈다: 그 술어는 `store.evacuable_names`를 그대로 부르고, 아래 `_evacuate`가
    실제로 옮기는 것도 그 목록이다. 여기만 meta 존재로 재면, 기록만 없고 본체는 멀쩡한 슬롯에서
    화면이 "저장된 것 없음"이라 말한 뒤 승인하면 실제로는 대피와 삭제가 일어난다 — 손실은 없고
    화면만 사실과 다르다. 그 상태는 앱이 만든다(기록 쓰기 실패 · 삭제의 `rmtree` 중단).
    `main._profile_ready`(meta ∧ 본체)와는 다르다: 저쪽은 "적용할 수 있는가"라 기록까지 요구한다.
    여기가 재는 것은 "되찾을 내용이 있는가"다.
    그래서 기록만 남은 슬롯은 「없음」으로 뜬다. 삭제가 그 `meta.json`을 지우기는 하지만 사용자가
    잃는 프로필 내용은 없다.
    `saved_at`은 그대로 기록에서 온다 — 「있는가」와 「언제인가」는 다른 축이고, 기록이 없으면
    시각은 정말 모른다. 기록 없는 본체는 「있음」 + 빈 시각이 되어 화면이 그 자리를 "저장 시각
    미상"으로 그린다.

    `config_path`는 확인창의 "설정 파일: {path}" 한 줄이 쓴다 — 표시 전용이다. 대피본에는 meta가
    없어 원본 경로를 아는 곳이 삭제 전의 registry뿐이라, 지우기 직전 화면이 그 경로를 보여줄
    마지막 기회가 여기다. str이 아니면 빈 문자열로 접는다 — 빈 값이면 화면이 그 줄을 안 그린다.

    지문을 params와 함께 낸다. 고지를 받은 뒤 지문을 따로 관측하면 그 사이의 변화가 토큰에
    구워져, 확인창이 이름을 댄 백업과 실제로 지워지는 백업이 갈린다. 지금은 고지에 쓴 바로 그
    관측값이 지문이 되고, 링 나열도 한 번뿐이다.
    소비자가 둘이다 — 삭제 route와 `main._profile_total`(전체 초기화 확인창의 "프로필 M개").
    반환을 튜플로 둔 것은 한쪽만 고치면 조용히 깨지는 것을 막기 위해서다: 지문을 `params`의 키로
    얹으면 `_profile_total`은 아무 말 없이 통과하고, 삭제 route가 `**params`로 splat하는 순간
    지문이 화면 봉투로 샌다.
    """
    appid = str(appid)
    entry = engine.game_or_fail(reg, appid)
    name = entry.get("name") or ("appid %s" % appid)
    if not _paths_in_position(appid):
        # 안전하지 않은 키 — 외부를 읽지 않는다. "지울 프로필 없음"으로 보고하고, 실제 삭제
        # 문에서 escape로 남긴다. 확인창은 이 게임을 빈 것으로 표시한다.
        # 경로도 말하지 않는다: 이 게임은 화면이 정상적으로 안내할 수 있는 상태가 아니다.
        # 지문도 아무 파일도 읽지 않는 고정 센티널이다(양쪽 칸 모두).
        # 이 갈래의 params에는 `evicted`가 없다 — 봉투 계약(`DeleteConfirmParams`)에서는 필수
        # 필드다. 화면은 없는 값을 빈 목록처럼 다루지만, 계약과 어긋난 자리라는 것은 알고 있어야 한다.
        return ({"appid": appid, "name": name, "has_dock": False, "has_internal": False,
                 "saved_at": {p: "" for p in PROFILES}, "backups": 0, "config_path": ""},
                (_UNSAFE_FP, _UNSAFE_FP))
    from . import restore                       # 순환 회피 — `restore`가 이 모듈을 최상단에서 import한다
    metas, digests = {}, []
    for profile in PROFILES:                    # 슬롯 meta는 슬롯당 한 번만 읽는다
        metas[profile], digest = _meta_observe(appid, profile)
        digests.append(digest)
    # 「저장돼 있나」는 본체 기준이다(위 독스트링이 정본). 술어를 여기 다시 적지 않고
    #   `store.slot_body_exists`를 그대로 부른다: 그것이 곧 대피가 도는 목록(`evacuable_names`)이다.
    #   바로 아래 `_evacuable_items`도 같은 목록을 도므로 두 나열을 붙여 둔다 — 사이가 벌어지면
    #   화면이 「있다」고 한 슬롯과 축출 예고가 센 슬롯이 갈릴 창이 생긴다.
    bodies = {p: store.slot_body_exists(appid, p) for p in PROFILES}
    # 링도 한 번만 나열한다 — 축출 예고·"현재 백업 N건"·링 지문이 전부 이 한 관측이다.
    ring = restore.ring_observe(appid, _evacuable_items(appid))
    config_path = entry.get("config_path")
    params = {
        "appid": appid,
        "name": name,
        "has_dock": bodies["dock"],
        "has_internal": bodies["internal"],
        "saved_at": {p: (metas[p] or {}).get("saved_at") or "" for p in PROFILES},
        "backups": ring["count"],
        "config_path": config_path if isinstance(config_path, str) else "",
        # 이 해제가 실제로 지울 백업(적용·복원·저장과 같은 필드·같은 문구).
        #   대피는 슬롯 본체를 링에 밀어 넣으므로, 링이 차 있으면 그만큼 오래된 백업이 사라진다.
        #   "현재 백업 N건"은 남는 쪽을 말할 뿐 무엇이 사라지는지는 말하지 않는다.
        "evicted": ring["evicted"],
    }
    # 축출 대상 자체를 토큰에 묶는다. `_delete_fp`의 링 신호는 개수(`bk=%d`)이고
    #   `ring["fingerprint"]`는 링의 이름 순서뿐이라, 그 둘이 하나도 안 움직이는데 축출 대상만
    #   바뀌는 자리가 있다 — 슬롯 본체가 하나 늘거나 줄면 대피 개수(`_evacuable_items`)가 달라져
    #   링에서 잘리는 깊이가 바뀐다. 그때 확인창이 이름을 댄 것과 다른 백업이 지워지는데도 낡은
    #   토큰이 통과한다. `apply_all`·`reset_all`은 이미 `restore.evict_digest`를 자기 슬롯에
    #   합성한다 — 같은 판단을 이 route에도 적용하는 것이다.
    # digest는 위 한 번의 관측(`ring["evicted"]`)에서 나온다 — 여기서 링을 다시 나열하면 고지와
    #   지문이 서로 다른 시각의 링을 가리킨다.
    # 축출 0건이면 싣지 않는다: 약속하지 않은 것은 재지 않는다(`reset_evict_preview`도 빈 게임을
    #   plan에서 뺀다).
    # 합성은 이 자리에서만 한다. `_delete_fp`에 넣으면 `delete_fingerprint`를 타고
    #   `reset_fingerprint` → `apply_all`·`reset_all` 토큰까지 번지는데, 그 둘은 이미 `|evict=`를
    #   자기 슬롯에 따로 합성하므로 이중 결박이 되고 다게임 지문이 게임별 본체 개수에까지 묶인다.
    evicted_ids = [row["backup_id"] for row in ring["evicted"]]
    fingerprint = "%s|evict=%s" % (
        _delete_fp(digests, ring["count"]),
        restore.evict_digest([(appid, evicted_ids)] if evicted_ids else []))
    return params, (fingerprint, ring["fingerprint"])


def evict_on_delete(appid):
    """이 게임의 슬롯을 대피시킬 때 실제로 지워질 백업(대피가 링을 밀어내는 만큼).

    이름이 가리키는 것보다 좁게 쓰인다: 개별 등록 해제 route는 지문이 함께 필요해서 위
    `delete_preview`가 `restore.ring_observe`를 직접 부른다. 지금 이 함수를 부르는 곳은 전체
    초기화(`reset_evict_preview`)와 검사뿐이다 — 여기를 근거로 "등록 해제가 이 함수를 지난다"고
    읽지 말 것.

    import를 함수 안에서 한다: `restore`가 이 모듈을 최상단에서 import하므로 여기서 맞import를
    만들면 순환이 된다. `confirm._ring_observe`도 같은 이유로 같은 모양이다.
    """
    appid = str(appid)
    if not _paths_in_position(appid):
        return []                              # 안전하지 않은 키는 조회하지 않는다
    from . import restore
    return restore.evict_preview(appid, _evacuable_items(appid))


def reset_evict_preview(reg):
    """전체 초기화가 실제로 지울 백업 — `{"evicted": N, "evict_games": M, "fingerprint": …}`.

    일괄 적용의 `confirm.apply_all_evict_preview`와 같은 판단이다: 게임이 여럿이라 이름 대신
    수만 약속하고, 그 수는 게임별 산출(`evict_on_delete`)의 합이라 나열본과 같은 근거에서 나온다.

    `fingerprint`는 화면 값이 아니라 토큰에 묶을 값이다. `reset_fingerprint`의 링 신호는 게임별
    개수(`bk=%d`)뿐이라 포화 링이 한 칸 도는 동안 그 개수는 `store.BACKUP_KEEP`으로 불변이고,
    그러면 확인창이 약속한 것과 다른 파일이 지워지는데도 낡은 토큰이 통과한다. 그래서 개수가
    아니라 대상 목록 자체를 지문으로 낸다(`restore.evict_digest` — 일괄 적용과 같은 함수다).
    재는 것 / 못 재는 것: 재는 것은 이 호출 시점에 게임별로 지워질 backup_id 전량과 순서다.
    못 재는 것은 ⓐ 실행 시점에만 나는 실패(대피 실패·경로 봉쇄)로 그 게임의 삭제가 통째로
    중단되는 갈래 — 예고보다 덜 지워지는 안전한 방향이다 ⓑ 게임별 예외로 건너뛴 게임
    ⓒ 축출이 0건인 게임의 링 변화(약속한 것이 없다).
    중복이라 대피본을 안 만드는 갈래는 여기 안 든다 — `_evacuable_items`가 준 목록을
    `ring_observe`가 그 한 나열 안에서 이미 갈랐다. ⓐ와 섞어 읽지 말 것: ⓐ는 실패라 못 재는
    것이고, 중복은 정상 갈래라 재는 것이다.
    """
    from . import restore                      # 순환 회피 — 위 `evict_on_delete` 참조
    plan = []
    for appid in sorted(reg["games"]):
        try:
            rows = evict_on_delete(appid)
        except Exception:                      # noqa: BLE001 — 게임별 격리(초기화 루프와 동형)
            continue
        if rows:
            plan.append((str(appid), [row["backup_id"] for row in rows]))
    return {"evicted": sum(len(ids) for _, ids in plan),
            "evict_games": len(plan),
            "fingerprint": restore.evict_digest(plan)}


def delete_fingerprint(appid):
    """개별 삭제 상태의 보조 지문.

    슬롯별 meta 파일 sha와 현재 백업 개수를 결합한다. 백업 이름은 싣지 않으므로 포화 링의
    구성만 바뀌면 이 값은 그대로일 수 있다. 개별 삭제 route는 `delete_preview`가 별도의 링·축출
    대상 지문을 함께 만들고, 전체 초기화 route도 `reset_evict_preview`의 지문을 따로 합성한다.
    """
    appid = str(appid)
    if not _paths_in_position(appid):
        return _UNSAFE_FP
    return _delete_fp([_meta_observe(appid, p)[1] for p in PROFILES],
                      len(store.list_backups(appid)))


def reset_fingerprint(reg):
    """registry 파일 sha와 전 등록 게임의 `delete_fingerprint`를 결합한다.

    이 값만으로 모든 링 변화를 재지는 못한다. 전체 초기화 토큰은 별도로 산출한 축출 대상
    지문을 합성한다.
    """
    reg_sha = store.sha1_file(store.registry_path()) or "absent"
    games = "&".join("%s=%s" % (a, delete_fingerprint(a)) for a in sorted(reg["games"]))
    return store.sha1_bytes(("%s#%s" % (reg_sha, games)).encode("utf-8"))


def _delete_failed(appid, stage, message, *, profile_delete_started, cause=None):
    """`DELETE_FAILED`의 단일 생성점. 이 코드를 만드는 함수는 여기 하나뿐이고,
    `qa/test_delete_game.py`가 소스를 AST로 읽어 그 「하나뿐임」을 잠근다.

    왜 한 곳으로 모으는가 — 이 코드는 화면에서 두 문장으로 갈린다.
      "프로필 데이터가 이미 일부 또는 전부 지워졌을 수 있습니다"와
      "등록 정보와 프로필 데이터는 지우지 않았습니다"는 서로 부정이라, 갈림이 틀리면 화면이
      거짓을 말한다. 그 갈림의 근거를 `stage` 문자열 화이트리스트에 매달면 새 거부 자리를 만든
      사람이 목록 갱신을 잊는 순간 조용히 거짓이 된다 — 게다가 같은 `"escape"`를 `restore.py`가
      다른 코드(`BACKUP_OUT_OF_ROOT`)에도 쓴다.
      그래서 갈림의 근거를 필수 키워드 인자로 올린다. 안 실으면 TypeError로 즉시 죽는다 —
      잊을 수 있는 자리 자체가 없어진다.

    `profile_delete_started=False`의 뜻은 「등록 정보와 프로필 데이터의 삭제 단계가 시작되지
      않았다」다. "아무것도 안 바뀌었다"가 아니다 — 삭제 전에 슬롯 본체를 백업으로 대피시키므로,
      한 슬롯을 대피시킨 뒤 다음 슬롯에서 거부되면 백업 링은 이미 바뀌어 있다. 그래서 안전
      문구의 주어를 「등록 정보와 프로필 데이터」로 한정한다. `True`는 삭제 단계 안에서 멈췄다 =
      부분 삭제가 남을 수 있다. (계약 원문은 `src/rpc.ts`의 `deleteGame`.)

    `stage`는 진단용 단계 이름이다. 화면 분기의 근거로 쓰지 않는다.
    """
    #: 두 갈래(원인 예외 연결 유무)가 같은 인자를 쓴다 — 한 곳에서만 만든다.
    #: `raise engine.Refused(...)`를 직접 두 번 쓰는 이유는 `qa/test_codes.py`가
    #: `raise Refused(code=codes.X)` 호출 형태를 AST로 훑기 때문이다. 여기서 예외를 변수에
    #: 담아 `raise 이름`으로 던지면 그 검사의 시야에서 이 자리가 사라진다.
    params = dict(appid=str(appid), stage=stage,
                  profile_delete_started=profile_delete_started)
    if cause is None:
        raise engine.Refused(message, code=codes.DELETE_FAILED, **params)
    raise engine.Refused(message, code=codes.DELETE_FAILED, **params) from cause


def _fail(appid, stage, exc, path=None):
    """진단 가능성을 남기고 거부한다 — `UNEXPECTED`로 뭉개면 사용자가 "지워진 것인가"를 알 수 없다.

    이 문을 지나는 것은 `meta`·`rmtree` — 삭제 단계 안에서 실패한 자리뿐이다. 그래서
    `profile_delete_started=True`다. 시작 전 거부(`escape`)는 여기로 오지 않고
    `_delete_failed(..., profile_delete_started=False)`를 직접 부른다."""
    _log.error("delete failed appid=%s stage=%s path=%s: %s: %s",
               appid, stage, path or "", type(exc).__name__, exc)
    _delete_failed(
        appid, stage,
        "거부: 삭제 도중 실패했습니다 (단계: %s) — %s\n"
        "  다시 삭제하면 남은 것부터 이어서 지웁니다." % (stage, exc),
        profile_delete_started=True, cause=exc)


def _backup_failed(appid, exc, path):
    """대피가 성립하지 않았다 → 아무것도 지우지 않고 중단한다 (G13). 원본 무손실."""
    _log.error("delete evacuation failed appid=%s path=%s: %s: %s",
               appid, path, type(exc).__name__, exc)
    raise engine.Refused(
        "거부: 삭제 전 대피(백업)에 실패해 아무것도 지우지 않았습니다 — %s" % exc,
        code=codes.BACKUP_FAILED, appid=appid, stage="backup") from exc


def _evacuate(appid, profile, plan=None):
    """그 슬롯의 본체 파일 전부를 백업 링으로 대피시킨다. 대피한 파일명 목록을 돌려준다.

    `plan`은 두 슬롯이 공유하는 하나다(아래 `delete_game_data`가 만든다) — 중복 판정을 슬롯마다
    다시 내리면 먼저 대피한 쪽이 밀어낸 칸을 뒤 슬롯이 근거로 믿는다.

    meta의 `filename`이 아니라 디렉터리를 열거한다(`store.evacuable_names`). meta가 손상돼
    읽히지 않는 슬롯도 본체는 멀쩡히 있을 수 있는데, meta를 통해서만 찾으면 그 본체가 대피 없이
    rmtree된다 — 예외 분기를 하나 더 만드는 대신 본체를 찾는 방법 자체를 meta에서 뗀다.
    「본체 파일 전부」에서 빠지는 것은 부산물뿐이다(`store.is_byproduct` — `meta.json` ·
    `.applied` · 크래시 잔재 `.gfxprofile-tmp-*`). 점으로 시작하는 이름을 통째로 빼지 않는다:
    `.gamerc` 같은 본체 이름이 그 필터에 걸리면 대피 없이 사라진다.

    중복이라 새 파일이 안 만들어져도 그 이름은 목록에 싣는다 — 빼지 말 것.
    `store.make_backup`은 같은 태그에 같은 내용이 이미 있으면 아무것도 쓰지 않고 `None`을
    돌려주는데, 그때도 "이 내용은 백업에 있다"는 참이다. 이 목록이 실리는 곳은 삭제 결과 봉투의
    `evacuated`이고 거기 실리는 것은 백업 경로가 아니라 본체 파일명이라, 뜻이 어긋나지 않는다.
    여기서 "안 만들었으니 빼야 한다"로 고치면 화면이 빈 `evacuated`를 받아 대피 없이 지워진
    상태와 구별되지 않는다 — 사용자는 남아 있는 복구 지점을 없다고 읽는다.
    """
    directory = store.profile_dir(appid, profile)
    saved = []
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return saved                       # 슬롯이 없다 = 대피할 것이 없다
    except OSError as exc:
        # 목록조차 못 읽으면 무엇을 대피시켜야 하는지 알 수 없다 = 대피 실패다.
        _backup_failed(appid, exc, directory)
    # ── 링크 게이트 — 대피를 한 건도 시작하기 전에 목록 전체를 본다 ─────────
    #   슬롯 안의 링크는 대피 대상이 아니다. `os.path.isfile`은 링크를 따라가므로 그것만 보면
    #     `read_bytes`가 외부 파일(.sav 등)을 백업에 복사한다 — ".sav를 열지 않는다"는 경계가
    #     무너진다. `islink`는 lstat 기반이라 따라가지 않는다. 대피 전이라 원본은 아직
    #     무손실이므로 여기서 거부하면 아무것도 잃지 않는다.
    for name in names:
        if store.is_byproduct(name):
            continue
        path = os.path.join(directory, name)
        if os.path.islink(path):
            _log.error("delete refused appid=%r stage=escape slot=%s name=%s (링크된 파일)",
                       appid, profile, name)
            # 대피 전이라 등록 정보·프로필 데이터의 삭제 단계는 시작되지 않았다.
            # (앞 슬롯의 대피는 이미 끝났을 수 있다 → 백업 링까지 부정하지는 않는다.)
            _delete_failed(
                appid, "escape",
                "거부: 프로필 안에 링크된 파일이 있습니다 — %s\n"
                "  링크를 따라가면 외부 파일을 백업에 복사하게 됩니다. 지우지 않았습니다." % path,
                profile_delete_started=False)

    # ── 대피 — 세는 목록과 같은 함수를 돈다 ─────────────────────────────────────
    #   확인창이 약속한 축출 수는 `store.evacuable_names`에서 산출된다. 지우는 쪽이 다른 목록을
    #   돌면 약속과 실제가 갈린다 — 두 곳에서 판정하지 않는다.
    #   목록은 전부 돈다. 그중 같은 태그에 같은 내용이 이미 있는 것은 `store.make_backup`이
    #     아무것도 쓰지 않고 `None`을 돌려준다 — 링을 안 태우는 것이지 건너뛰는 것이 아니다.
    #     확인창의 개수는 `_evacuable_items` → `restore.ring_observe`가 같은 술어로 미리 갈라 둔다.
    #     단 그 「이미 있는 것」이 이번 동작에서 어차피 축출될 자리이면 `store.plan_backups`가
    #       쓰기를 허가한다 — 그때는 중복이어도 새로 담기고 `None`이 아닌 경로가 돌아온다.
    for name in store.evacuable_names(appid, profile):
        path = os.path.join(directory, name)
        try:
            # 정상 저장이 덮어쓰기 전에 하는 대피와 같은 문법이다 — `engine.save_profile`도
            # `store.evacuable_names`가 준 목록을 돌며 `store.make_backup`을 부른다.
            # 삭제 = "빈 내용으로 덮어쓰기"이므로 대피가 선행해야 대칭이다.
            store.make_backup(appid, store.read_bytes(path), store.profile_tag(profile), name,
                              plan=plan)
        except OSError as exc:
            _backup_failed(appid, exc, path)   # G13 — 원본을 하나도 건드리지 않고 중단
        saved.append(name)
    return saved


def delete_game_data(reg, appid):
    """파괴의 유일한 문. 대피 → meta unlink×2 → rmtree → registry 항목 제거.

    `reg`를 제자리에서 고친다. 저장은 호출자가 한다.
    실패는 전부 `Refused`다 — `BACKUP_FAILED`(대피 단계, 원본 무손실) 또는 `DELETE_FAILED`
    (`stage`로 어디서 멈췄는지 알린다).

    바로 위 줄은 `stage`로 진단한다는 뜻이지 화면이 `stage`로 갈린다는 뜻이 아니다.
    `DELETE_FAILED`는 경로 봉쇄와 대피 중 링크 게이트에서도 난다 — 그쪽은 아직 아무것도 지우지
    않은 거부다. 화면이 두 경우를 가르는 근거는 `stage`가 아니라 `_delete_failed`가 싣는
    `profile_delete_started` 한 필드다.
    """
    appid = str(appid)
    entry = engine.game_or_fail(reg, appid)
    name = entry.get("name") or ("appid %s" % appid)
    root = store.profiles_root(appid)

    # ── 0. 경로 봉쇄 — 모든 쓰기보다 먼저다 (G15의 realpath 문법 그대로) ───────────
    #
    # 왜 여기 한 곳인가: `delete_game` route는 `main._VALIDATORS`가 appid를 숫자로 막지만
    #   `reset_all`은 appid 파라미터가 없어 그 검증을 한 번도 지나지 않는다 — registry의
    #   games 키가 그대로 여기로 들어온다. 손상·수동 편집된 registry에 `"../../X"`나 절대경로
    #   키가 있으면 `os.path.join`이 데이터 루트 접두어를 통째로 버려 루트 밖이 rmtree/unlink
    #   된다. route에 검증을 덧대면 문이 둘이 되고 언젠가 한쪽이 빠진다 — 파괴의 문 안에서 막는다.
    #
    # 판정은 `_paths_in_position` 한 함수다 — `profiles/<appid>`·슬롯 2개·`backups/<appid>`가
    #   심볼릭 링크를 푼 뒤 전부 제자리인지 본다. 조회(`delete_preview`·`delete_fingerprint`)도
    #   같은 함수로 안전을 판정하므로 삭제 문과 조회가 같은 경계를 공유한다. backups까지 보는
    #   이유는 대피(`store.make_backup`→`prune_backups`)가 그 경로를 지나기 때문이다.
    if not _paths_in_position(appid):
        _log.error("delete refused appid=%r stage=escape (경로 봉쇄 — profiles/슬롯/backups 제자리 아님)",
                   appid)
        # 모든 쓰기보다 먼저다 → 대피조차 시작하지 않았다(`profile_delete_started=False`).
        _delete_failed(
            appid, "escape",
            "거부: 삭제 대상 경로가 이 플러그인의 데이터 루트 안 제자리가 아닙니다.\n"
            "  등록 정보가 손상됐을 수 있습니다. 지우지 않았습니다.",
            profile_delete_started=False)

    # ── 1. 대피 (실패 → BACKUP_FAILED, 전체 중단 · 원본 무손실) ──────────────────
    evacuated = {}
    # 중복 판정은 여기서 한 번이고 두 슬롯이 같은 계획을 쓴다. 고지층
    #   (`delete_preview` → `restore.ring_observe`)이 세는 것과 같은 목록·같은 함수다.
    plan = store.BackupPlan(
        store.plan_backups(store.list_backups(appid), _evacuable_items(appid)))
    for profile in PROFILES:
        saved = _evacuate(appid, profile, plan)
        if saved:
            evacuated[profile] = saved

    # ── 2. meta.json unlink ×2 (적용 계열 소비자의 공통 판정 기준을 먼저 없앤다) ──
    #   없는 meta를 실패로 보지 않는다 — 한쪽 프로필만 저장한 게임이 정상으로 존재한다.
    #   없는 meta는 "이미 지워진 것"과 동치다.
    for profile in PROFILES:
        path = store.profile_meta_path(appid, profile)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            _fail(appid, "meta", exc, path)

    # ── 3. profiles/<appid>/ 통째로 ─────────────────────────────────────────────
    #   파일명을 열거해 지우지 않는다 — 크래시 잔재(`.gfxprofile-tmp-*`) 같은 미지의 파일마다
    #   예외가 생긴다. meta 선행 unlink가 rmtree의 삭제 순서가 임의라는 사실을 무력화한다.
    try:
        shutil.rmtree(root)
    except FileNotFoundError:
        pass                               # 프로필을 한 번도 만들지 않은 게임 — 정상이다
    except OSError as exc:
        _fail(appid, "rmtree", exc, root)

    # ── 4. registry 항목 제거 + last_appid 정리 ─────────────────────────────────
    #   registry를 마지막에 지운다. 반대 순서로 하다 중단되면 "미등록인데 profiles/가 남은"
    #   정의되지 않은 상태가 되고, 재등록 시 유령 프로필이 되살아난다.
    reg["games"].pop(appid, None)
    settings = reg.setdefault("settings", {})
    if settings.get("last_appid") == appid:
        # 등록 목록에 없는 appid를 가리키는 상태를 만들지 않는다 — 예외가 생기지 않는 구조.
        settings["last_appid"] = None

    return {"appid": appid, "name": name, "evacuated": evacuated,
            "backups": len(store.list_backups(appid))}
