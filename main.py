"""gfxprofile v2 — Decky 백엔드 접착층 (P1).

경계가 이 파일의 일이다: 데이터 격리 · 봉투 · RPC 배선 · 생명주기 로그 · 화면용 시각 표기.
도메인 규칙은 `py_modules/gfxp/` 엔진에 두고, 이 파일은 그 결과를 RPC 흐름과 접착층에 둔
관문(레지스트리 버전 가드 U5 · 확인 토큰)으로 집행한다.

절대 하지 말 것
  - `decky.migrate_*` 호출 금지. `_migration()`은 의도적으로 비워 둔다 — 그 함수들이
    원본을 어떻게 다루는지는 저장소 밖이라 [미확인]이고, 부르지 않는 한 확인할 일이 없다.
  - 데이터 경로를 문자열로 박지 말 것 — 접착층은 loader가 준 `DECKY_PLUGIN_RUNTIME_DIR`를
    데이터 루트로 쓰고, 외부 `GFXPROFILE_DATA_DIR`을 그 값으로 덮어 엔진 폴백을 쓰지 않는다.
    폴백 경로는 M1 호환 경로와 글자가 같다 — 아래 데이터 격리가 그것을 막는 이유다.
    표시명(`plugin.json`의 `name`)과 설치 이름(IDENT)은 이 저장소에서 이미 갈려 있고,
    로더가 `DECKY_PLUGIN_*_DIR`를 무엇으로 조립하는지는 [미확인]이다.
"""

import copy
import functools
import inspect
import json
import logging
import os
import secrets
import time
import traceback

import decky

# ── 데이터 격리 — import 시점에 못박는다 ─────────────────────────────────────
# 외부 GFXPROFILE_DATA_DIR을 loader가 준 DECKY_PLUGIN_RUNTIME_DIR로 덮어, 엔진
# store.data_dir()의 폴백을 쓰지 않는다. 그 폴백은 M1 호환 경로다.
# loader가 준 값 자체가 M1이나 그 별칭이면 격리는 성립하지 않는다 — 그 대조는 [미확인].
#
# setdefault가 아니라 대입이다. setdefault면 외부에서 들어온 값이 이기고
# "격리했다"는 말이 조건부가 된다.
#
# assert가 아니라 raise다. assert는 `python3 -O`에서 통째로 사라져
# "구조적 보장"이 플래그 하나에 무너진다.
_RUNTIME_DIR = os.environ.get("DECKY_PLUGIN_RUNTIME_DIR")
if not _RUNTIME_DIR:
    raise RuntimeError(
        "DECKY_PLUGIN_RUNTIME_DIR이 없다. 이 백엔드는 Decky 로더 안에서만 돈다 — "
        "격리 경로를 모르는 채로 뜨면 M1의 실사용 데이터를 건드릴 수 있다."
    )
os.environ["GFXPROFILE_DATA_DIR"] = _RUNTIME_DIR

from gfxp import (codes, confirm, discover, engine, exclude, labels, lang,  # noqa: E402
                  remove, restore, store)                     # (격리 뒤에 import해야 한다)

#: 로드 1회당 하나. SESSION을 싣는 접착층 로그를 이번 로드분으로 좁히는 토큰이다.
SESSION = "%d-%s" % (int(time.time()), secrets.token_hex(3))


# ── gfxp 로거 배선 ───────────────────────────────────────────────────────────
# `gfxp` 모듈들은 decky에 의존하지 않는다(테스트가 로더 없이 돈다는 것이 그 값어치다).
# 그래서 정책 자리에서는 표준 `logging`으로만 남기고, gfxp 레코드를 `decky.logger`로
# 전달하는 배선은 접착층인 여기가 한다.
#
# `decky.logger.handlers`를 복사해 붙이지 않는다. 그 로거가 핸들러 없이 상위로
# propagate하는 구성이면 복사할 것이 없어 조용히 아무 데도 안 실린다. 대신 레코드를
# `decky.logger`로 되돌려 보낸다 — 어디에 실리는지는 decky가 정한다.
class _DeckyBridge(logging.Handler):
    def emit(self, record):
        try:
            decky.logger.log(record.levelno, "%s %s", record.name, record.getMessage())
        except Exception:                                   # noqa: BLE001
            pass          # 로깅이 앱을 죽이지 않는다


def _wire_gfxp_logging():
    logger = logging.getLogger("gfxp")
    logger.setLevel(logging.INFO)
    logger.propagate = False        # 루트로도 새면 같은 줄이 두 번 남는다
    if not any(isinstance(h, _DeckyBridge) for h in logger.handlers):
        logger.addHandler(_DeckyBridge())


_wire_gfxp_logging()


# ── 봉투 ─────────────────────────────────────────────────────────────────────
# 모든 RPC 반환은 이 둘 중 하나다. 예외 없음. 최상위에 다른 키를 두지 않는다.
#     성공 {"ok": true,  "data": {...}}
#     실패 {"ok": false, "code": "...", "params": {...}}
# 프론트는 `src/rpc.ts` 헬퍼 하나로 이 봉투를 타입으로 선언하고, 호출부가 ok로 분기한다.

def _ok(**data):
    return {"ok": True, "data": data}


def _fail(code, **params):
    return {"ok": False, "code": code, "params": params}


def _sealed(env):
    """봉투를 강제한다 — 모양을 만들어 주는 것과 지키게 하는 것은 다르다.

    키 집합이 정확히 맞는지, 그리고 JSON으로 직렬화되는지까지 여기서 본다.
    직렬화는 이 경계 밖(전송 계층)에서 터지면 봉투로 못 바꾸고 프론트엔 정체불명 오류만 간다.
    """
    keys = set(env)
    expect = {"ok", "data"} if env.get("ok") is True else {"ok", "code", "params"}
    if not isinstance(env.get("ok"), bool) or keys != expect:
        decky.logger.error("envelope violation session=%s keys=%s", SESSION, sorted(keys))
        return {"ok": False, "code": codes.UNEXPECTED, "params": {}}
    try:
        json.dumps(env)
    except (TypeError, ValueError) as exc:
        decky.logger.error("envelope not serializable session=%s: %s", SESSION, exc)
        return {"ok": False, "code": codes.UNEXPECTED, "params": {}}
    return env


#: RPC 인자 이름 → 검증기. 이름이 같으면 자동으로 걸린다.
#: 각 route가 기억해서 부르는 방식이면 언젠가 하나가 빠지고, 빠진 곳이 곧 구멍이 된다.
_VALIDATORS = {
    # appid는 `store.profiles_root`의 경로 조각이다.
    # 절대경로와 상위 경로 표기를 받지 않도록 숫자만 허용한다.
    "appid": lambda v: str(v).isdigit(),
    # RPC 프로필 슬롯은 dock·internal 둘뿐이다. 자유 문자열을 받을 이유가 없다.
    "profile": lambda v: v in ("dock", "internal"),
    # 백업 식별자는 basename뿐이다. 경로가 아니다.
    "backup_id": lambda v: isinstance(v, str) and "/" not in v and not v.startswith("."),
}


def _validate(name, value):
    check = _VALIDATORS.get(name)
    if check and not check(value):
        raise engine.Refused("거부: 잘못된 %s 값입니다 — %r" % (name, value),
                             code=codes.BAD_IDENTIFIER, field=name)


def route(fn):
    """RPC 하나를 봉투로 감싸고, 경로 조각이 되는 인자를 자동 검증한다.

    봉투화와 인자 검증이 여기 한 곳이라 각 route가 그것을 되풀이하지 않는다.
    정책 거부인 `Refused`와 `RegistryError`는 각자의 `code`로 실패 봉투에 싣고,
    그 밖의 예외는 아래 일반 예외 갈래에서 `UNEXPECTED`로 봉투화한다.
    """
    param_names = list(inspect.signature(fn).parameters)

    async def wrapped(*args, **kwargs):
        # 인자 검증은 반드시 try 안이다. 밖에 두면 `_validate`가 던지는
        #   `Refused(BAD_IDENTIFIER)`가 봉투를 거치지 않고 그대로 프론트로 튀어,
        #   "모든 RPC가 봉투 하나로 돌아온다"는 계약(`src/rpc.ts`)이 깨진다.
        #   여기서 던지면 아래 `except (Refused, RegistryError)`가 받아 봉투에 싣는다.
        # Decky는 플러그인 메서드의 반환값을 await 한다. 동기 메서드를 노출하면 실행은 되고
        #   로그도 남는데 프론트에는 `object dict can't be used in 'await' expression`만 돌아온다.
        #   그래서 경계(이 래퍼)만 async로 두고, 엔진은 동기 그대로 둔다.
        try:
            for name, value in list(zip(param_names, args)) + list(kwargs.items()):
                _validate(name, value)
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return _sealed(result if isinstance(result, dict) and "ok" in result
                           else _ok(**(result or {})))
        except (engine.Refused, store.RegistryError) as exc:
            decky.logger.info("refused session=%s route=%s code=%s", SESSION, fn.__name__, exc.code)
            return _fail(exc.code or codes.UNEXPECTED, message=str(exc), **exc.params)
        except Exception:                                   # noqa: BLE001
            # 여기 오는 것은 우리가 예상하지 못한 것뿐이다. 삼키지 않고 로그에 전문을 남긴다 —
            # Game Mode에는 터미널이 없어 로그가 유일한 단서다.
            decky.logger.error("unexpected session=%s route=%s\n%s",
                               SESSION, fn.__name__, traceback.format_exc())
            return _fail(codes.UNEXPECTED)
    wrapped.__name__ = fn.__name__
    return wrapped


# ── 레지스트리 버전 가드 (U5) ────────────────────────────────────────────────
# 레지스트리 version이 현재 코드보다 높으면, 이 코드가 그 버전의 의미를 모른 채 알려진 값을
# 현재 규칙으로 바꾸고 dict 전체를 다시 쓸 수 있다. 미지 키 자체는 `load_registry`의
# `setdefault`와 `save_registry`의 전체 직렬화 사이에서 보존된다. 읽기는 허용하고 변경만 막는다.
# 전체 초기화는 현재 version의 새 dict를 만들어 이 상태에서 빠져나오는 경로다.
# 가드는 접착층의 RPC·저장 관문에 둔다.

def _registry_newer(reg):
    """레지스트리 version이 현재 코드의 `REGISTRY_VERSION`보다 높은가.

    `isinstance`를 쓰지 않는다 — `True`는 `int`의 인스턴스라 `version: true`가 검사를
    통과하고, `True > 1`은 거짓이 된다. 형 자체를 본다.
    """
    version = reg.get("version")
    if type(version) is not int:                    # noqa: E721 — 위 독스트링 참조
        raise store.RegistryError(
            "거부: 레지스트리 형식이 올바르지 않습니다 — version이 정수가 아닙니다.",
            code=codes.REGISTRY_MALFORMED)
    return version > store.REGISTRY_VERSION


def _guard_not_newer(reg):
    """관문 둘이 공유하는 거부. 문구를 두 벌로 두면 언젠가 갈라진다."""
    if _registry_newer(reg):
        raise store.RegistryError(
            "거부: 이 데이터는 더 새 버전의 플러그인이 만들었습니다 — 데이터를 지키기 위해 "
            "변경하는 동작을 멈췄습니다.",
            code=codes.REGISTRY_NEWER)


def mutating(fn):
    """문 ① — 데이터를 바꾸는 RPC의 관문. 엔진이 파일을 쓰기 전에 막는다.

    왜 쓰기 직전(문 ②)만으로는 부족한가: 엔진은 게임 설정 파일·프로필·백업을 먼저 쓰고
    registry 저장은 마지막이다. 거기서 막으면 "바뀌지 않았습니다"가 거짓이 된다.
    `functools.wraps`가 필수다. 없으면 `route`가 보는 시그니처가 `(*args, **kwargs)`로
    납작해져 `param_names`가 비고, 그러면 위치 인자 검증(`_validate`)이 통째로 빠진다.
    `wraps`가 다는 `__wrapped__`를 `inspect.signature`가 따라가 원래 목록을 준다.
    """
    @functools.wraps(fn)
    def guarded(*args, **kwargs):
        _guard_not_newer(store.load_registry())
        return fn(*args, **kwargs)
    return guarded


def _save_registry(reg):
    """문 ② — 영속화 직전, 실제로 쓰려는 그 dict를 검사한다.

    이 래퍼에 예외 경로는 없다 — 정상 갈래의 reset_all(탈출로)은 여전히 여기를 지나지만, 그것이
    영속화하는 dict는 `store.default_registry()` 기반이라 `version`이 현재 값이고 검사를 자연
    통과한다. 탈출을 허용하는 것은 예외 분기가 아니라 데이터 자체다 — 구조가 예외를 없앤 자리.
    ★ 19판 — **fresh 갈래는 여기를 지나지 않는다**: `store.save_fresh_registry()`가 인자를 받지
    않아 밖에서 만든 dict가 그 문으로 들어올 수 없고, 그래서 버전 가드 없이도 `version`이 언제나
    현재 값이다(§7-4′ 6항). 구조가 예외를 없앤 자리가 하나 더 늘었다.
    """
    _guard_not_newer(reg)
    store.save_registry(reg)


def _plugin_version():
    """설치된 package.json 객체의 version. 파일 열기·JSON 파싱 실패면 unknown —
    소비처가 `ui_hello` 응답 봉투 하나뿐이라 실패해도 판정에 영향이 없다."""
    path = os.path.join(os.environ.get("DECKY_PLUGIN_DIR", ""), "package.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("version", "unknown")
    except (OSError, ValueError):
        return "unknown"


def _ui_types_version():
    """빌드 시점에 우리가 본 @decky/ui 버전 = 타입 기준선(package.json의 devDependencies).

    런타임에 실제로 쓰이는 컴포넌트는 이 버전이 아니다. `@decky/rollup`이 `@decky/ui`를 external로
    빼서 Decky Loader가 전역 `DFL`로 준다. 즉 타입 기준선과 런타임 실물이 다를 수 있고 그 어긋남은
    조용하다. 그래서 둘(ui_types / loader)을 나란히 보고한다.

    그 어긋남을 재는 검사는 없다 — 로그에 나란히 실린 두 값을 사람이 견줘야 한다.
    """
    path = os.path.join(os.environ.get("DECKY_PLUGIN_DIR", ""), "package.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            pkg = json.load(fh)
        return pkg.get("devDependencies", {}).get("@decky/ui", "unknown")
    except (OSError, ValueError):
        return "unknown"


def _running_appids():
    """지금 실행 중인 게임 appid 집합. `/proc`을 딱 한 번만 훑는다.

    엔진의 `running_game()`은 호출 한 번마다 `/proc` 전체를 훑는다 — 게임마다 부르면 등록 수에
    정비례하는 재스캔이 된다. 한 번만 훑어 집합을 만들면 그 비용이 등록 수와 무관해진다.
    화면을 열 때마다 내는 비용이라 정비례를 끊는 것이 맞다.

    엔진 `running_game`은 그대로 둔다 — 그건 diff fence 대상이고, 개별 적용 경로
    (`apply_profile`)에서는 게임 하나만 보므로 재스캔이 문제가 되지 않는다. 여기는 접착층이다.
    """
    needle_prefix = b"SteamAppId="
    running = set()
    try:
        pids = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return running
    for pid in pids:
        try:
            with open("/proc/%s/environ" % pid, "rb") as fh:
                blob = fh.read()
        except (OSError, PermissionError):
            continue                      # 남의 프로세스는 못 읽는다 — 엔진과 같은 동작이다
        for item in blob.split(b"\0"):
            if item.startswith(needle_prefix):
                running.add(item[len(needle_prefix):].decode("utf-8", "replace"))
    return running


def _discover_entries(reg):
    """탐지 1회 + appid 기준 dedup. 두 route(`discover_games`·`register_confident`)가 같은
    목록을 봐야 하므로 여기 한 곳에서만 만든다 — 두 곳에서 만들면 화면에 뜬 것과 실제로
    등록되는 것이 언젠가 어긋난다(`get_overview`의 counts와 같은 이유).

    dedup이 필요한 이유: 같은 appid의 prefix가 두 라이브러리에 다 있고 양쪽이 다 후보를 내면
    같은 게임이 2행 나온다. 후보가 많은 쪽을 남긴다 — 껍데기가 진짜를 밀어내지 않는다.

    감지 제외의 필터도 여기 한 곳뿐이다(`qa/test_discover_exclude.py`가 잠근다). dedup 이전에
      거른다 — 제외된 appid가 dedup 경쟁에 끼면 계산만 늘고 결과는 같다. `discover.py`는 fence라
      인자를 늘리지 않는다: 제외는 탐지 알고리즘이 아니라 표시 정책이고, 그 정책을 두 route가
      공유하는 자리가 여기다.
    """
    excluded = exclude.excluded_map(reg)
    best = {}
    for entry in discover.discover(known_appids=set(reg["games"])):
        if entry["appid"] in excluded:
            continue
        prev = best.get(entry["appid"])
        if prev is None or len(entry["candidates"]) > len(prev["candidates"]):
            best[entry["appid"]] = entry
    return sorted(best.values(), key=lambda e: e["name"].lower())


def _candidate(cand):
    """후보 하나를 봉투용으로 줄인다.

    엔진의 `reason`(한국어 자유문)은 싣지 않는다. 화면에 그대로 뿌리면 영어 사용자에게 한국어가
      새고 `t()` 밖 문자열이 화면에 생긴다. 프론트는 `tier`로 문구를 고른다 — 코드로 분류하고
      문구는 i18n이 고른다는 이 프로젝트의 규칙 그대로다.
    """
    return {
        "path": cand["path"],
        "tier": cand["tier"],
        "size": cand["size"],
        "mtime_label": discover.mtime_label(cand),
    }


def _entry_payload(entry):
    """탐지 entry 하나를 봉투용으로.

    확신 후보에는 후보 전량을 싣지 않는다. 후보 절대경로가 봉투 크기를 지배하는데, 확신 게임은
      화면에서 후보 목록을 펼칠 일이 없다(1탭 등록이다). 설치 500게임 상한에서 전량을 실으면
      봉투가 수 MB가 된다 — 사람이 골라야 하는 애매한 게임만 전량 싣는다.
    """
    best = discover.best_candidate(entry)
    return {
        "appid": entry["appid"],
        "name": entry["name"],
        "library": entry["library"],
        "confident": entry["confident"],
        "registered": entry["registered"],
        "candidate_count": len(entry["candidates"]),
        "best": _candidate(best) if best else None,
        "candidates": [] if entry["confident"] else [_candidate(c) for c in entry["candidates"]],
    }


def _saved_label(value):
    """`meta.saved_at`(ISO `2026-08-10T09:26:51+0900`) → 화면용 `2026-08-10 09:26`.

    프론트가 문자열을 쪼개면 판정이 두 곳으로 갈리므로 백엔드 한 곳에서 포맷한다
    (백업 파일명 해석을 `store` 한 곳에 몰아 둔 것과 같은 이유).
    파싱하지 않는다 — 자리로 잘라 낸다. 문자열 형식이 예상과 다르면 원문을 그대로 돌려준다
    (모르는 값을 예쁘게 꾸미려다 없는 사실을 만들지 않는다).
    """
    text = value or ""
    if len(text) >= 16 and text[10] == "T":
        return text[:10] + " " + text[11:16]
    return text


def _excluded_rows(reg):
    """감지 제외 목록을 봉투용으로 — `[{appid, name, excluded_at_label}]`.

    `discover_games`와 `include_game`이 같은 헬퍼를 지난다 — `qa/test_discover_exclude.py`가 두
      봉투의 모양이 같은지 잠근다. 봉투 모양이 route마다 다르면 화면이 route별 분기를 갖게 되고,
      그 분기가 곧 어긋남의 자리가 된다.
    시각 표기는 `_saved_label` 한 함수를 지난다 — 같은 값이 화면마다 다른 모양으로 보이지 않는다.
    """
    return [{"appid": row["appid"], "name": row["name"],
             "excluded_at_label": _saved_label(row["excluded_at"])}
            for row in exclude.rows(reg)]


def _slot_view(appid, profile):
    """그 슬롯의 `(적용을 시도할 수 있는가, 마지막 저장 표시값, meta의 sha1)` —
    meta를 한 번만 읽는다.

    첫 칸이 재는 것은 「meta가 읽히고 본체 파일이 존재한다」까지다. 엔진은 실행 시점에 더 본다 —
    본체 sha1과 meta sha1 대조(`PROFILE_CORRUPT`), 읽기 실패, 경로 가드(G11). 즉 참이어도
    적용이 거부될 수 있다. 「엔진이 수락하는 조건과 같다」가 아니라 「엔진이 요구하는 최소 전제」이고,
    그 이상은 화면이 미리 약속하지 않는다(약속하면 라벨이 거짓말을 한다).

    슬롯 상태와 `saved_at`을 한 번의 meta 읽기에서 같이 꺼낸다 — 판정과 표시값을 따로 부르면
    같은 meta를 슬롯당 두 번, 세 번 읽는다(`store.profile_file_path`가 meta를 다시 연다).
    봉투는 넓어지지만 파일 접근은 줄어들므로 `detail` 게이트가 필요 없다 — 게이트의 근거는
    「파일 크기에 좌우되는 예측 불가 비용」인데 여기엔 해당하지 않는다.

    meta가 dict가 아니면(비JSON 손상·유효 JSON이지만 비객체) 적용 불가 슬롯으로 본다.
    그러지 않으면 아래 `meta.get`이 AttributeError를 내고 현황 탭 전체가 죽는다
    (store는 fence라 방어를 소비자인 여기 둔다).

    세 번째 칸 `meta의 sha1`도 같은 meta 읽기에서 꺼내므로 meta 읽기는 슬롯당 한 번이다.
    본체 존재 확인은 별도의 파일시스템 조회다. str이 아니면 빈 문자열로 접는다:
    `profiles_identical` 판정이 `None == None` 같은 우연 일치로 참이 되면 안 된다.

    안전하지 않은 슬롯은 읽지 않는다. `get_overview`는 registry의 games 키를 그대로 도는데 그 키는
    `_VALIDATORS`를 한 번도 지나지 않는다 — 접지 않으면 손상·수동 편집된 `"../../X"`·절대경로
    키에서 데이터 루트 밖 meta를 읽게 된다. 슬롯 판정의 문은 `remove.slot_in_position` 하나이고,
    `restore.backup_count`·슬롯 지문이 쓰는 `remove._paths_in_position`도 그 함수를 부른다
    (그쪽은 `backups/<appid>`까지 더 본다).
    """
    if not remove.slot_in_position(appid, profile):
        return False, "", ""
    try:
        meta = store.load_meta(appid, profile)
    except (OSError, ValueError):
        return False, "", ""
    if not isinstance(meta, dict):
        return False, "", ""
    sha1 = meta.get("sha1")
    if not isinstance(sha1, str):
        sha1 = ""
    filename = meta.get("filename")
    if not filename or not isinstance(filename, str):
        # 파일명이 없으면 본체를 가리킬 수 없다 = 적용 불가. (`profile_file_path`는 이 경우
        # KeyError를 내므로 여기서 접는 것이 엔진 수락 조건과 같은 결론에 더 안전하게 닿는다.)
        return False, _saved_label(meta.get("saved_at")), sha1
    path = os.path.join(store.profile_dir(appid, profile), filename)
    return os.path.exists(path), _saved_label(meta.get("saved_at")), sha1


def _profile_ready(appid, profile):
    """그 프로필에 적용 시도를 시작할 최소 슬롯 전제가 갖춰졌는가.

    `meta.json`만 보면 안 된다. meta는 남아 있는데 프로필 본체가 사라지면 `load_meta`는 그대로
    참을 돌려주고, 화면은 `(1개)`라며 버튼을 활성화한 뒤 누르면 거부가 난다 — 라벨이 거짓말을
    한다. 그래서 판정 재료를 엔진의 `PROFILE_MISSING` 판정과 같게 맞춘다
    (`engine.apply_profile`: meta 있음 ∧ 본체 파일 존재).
    엔진은 그 판정 앞에 경로 가드(G11)와 실행 중 검사(G5)를, 뒤에 sha1 대조를 더 둔다 —
    여기서 참인데 실행이 거부될 수 있고, 그 차이는 실행 결과가 보고한다. 두 곳이 다른 최소 전제를
    쓰면 언젠가 어긋난다는 논지는 그대로다.

    판정 자체는 `_slot_view` 한 곳에 있다 — 여기와 `get_overview`가 각자 판정하면 「화면에는
    저장됐다는데 적용은 거부되는」 어긋남이 언젠가 생긴다. 이 함수는 그 판정의 이름 붙은 입구로
    남는다(`qa/test_delete_game.py`가 이 이름을 부른다).
    """
    return _slot_view(appid, profile)[0]


def _disk_state_safe(reg, appid):
    """`engine.disk_state`의 `Refused`·`OSError`·`ValueError`·`AttributeError`·`TypeError`를
    빈 dict(「알 수 없음」)로 접는 래퍼.

    비-dict meta는 `store.slot_holds`가 걸러 낸다. 미등록·경로 타입·파일 조회 실패를 이 래퍼가
    접는다. ★ 19판 — 등록 항목 손상도 여기 들어왔다(`engine.disk_state`가
    `Refused(REGISTRY_ENTRY_CORRUPT)`를 낸다). 다만 이 래퍼가 지키는 것은 `disk_matches` 한
    칸이다 — 목록 조립 자체의 항목 격리는 `get_overview`의 게임별 접기가 한다.

    안전하지 않은 슬롯은 `remove.slot_in_position`으로 진입 전에 접고, 두 슬롯 모두를 요구한다."""
    if not all(remove.slot_in_position(appid, p) for p in remove.PROFILES):
        return {}
    try:
        return engine.disk_state(reg, appid)
    except (engine.Refused, OSError, ValueError, AttributeError, TypeError):
        return {}


def _disk_matches(reg, appid, dock_sha, intl_sha):
    """지금 게임 설정 파일과 같은 내용인 슬롯 전부 — `[]`·`["dock"]`·`["dock","internal"]`.

    두 슬롯의 내용이 같으면 둘 다 실린다. 엔진의 first-match break를 쓰지 않는 이유는
    `get_overview`의 `disk_matches` 필드 주석에 있다.
    슬롯 쪽 재료는 `_slot_view`가 이미 읽은 meta sha 둘이다. 디스크 sha1은 이 함수가
    `_disk_state_safe`를 불러 새로 잰다 — `detail=True`에서만 도는 추가 조회이고, 그래서
    `disk_matches`가 `detail` 게이트 뒤에 있다.
    모르면 빈 배열이다(조회 실패·손상·제자리 아님) — 모르는 것을 「같다」고 말하지 않는다.
    """
    disk_sha = _disk_state_safe(reg, appid).get("sha1")
    if not disk_sha:
        return []
    return [name for name, sha in (("dock", dock_sha), ("internal", intl_sha))
            if sha and sha == disk_sha]


# ── 확인 토큰 ────────────────────────────────────────────────────────────────
# 확인 여부는 클라이언트 불리언이 아니라 백엔드가 발급한 1회용 토큰으로 증명한다.
#
# 클라이언트 불리언에는 출처가 없다. 백엔드는 첫 호출부터 참인 값과, 확인 요청을 받은 뒤
# 되돌아온 참인 값을 구별할 수 없다.
#
# 보장: 덮어쓰기 판정이 참이면, 현재 appid·scope·두 상태값과 일치하는 토큰을 소비하기 전에는
# 쓰기 호출로 내려가지 않는다. 토큰은 한 번 소비되며 만료된다.
# 비보장: 사람이 실제로 모달을 봤는지는 증명하지 않는다. 클라이언트가 받은 토큰을 화면 표시 없이
# 곧바로 돌려보내는 것은 이 경계 밖이다.
#
# 토큰 저장소는 모듈 전역이다. `Plugin`에는 `__init__`이 없고, 토큰은 발급 RPC와 소비 RPC 사이에
# 로드된 백엔드 모듈의 수명 동안 살아 있어야 한다.
#
# `_issue`와 `_consume`이 비교하는 결박값은 `(appid, scope, state_a, state_b)` 네 칸이고,
# 저장 레코드에는 만료 판정을 위한 `issued_at`이 다섯 번째로 붙는다.
# 저장은 `profile`을 scope로 쓰고, 등록은 `_ADD_GAME_SCOPE`를 쓴다. RPC의 `profile` 검증기가
# `dock`·`internal`만 허용하므로 `"add_game"`과 충돌하지 않는다. 적용·복원의 합성 scope는
# 아래 `_apply_scope`와 `_restore_scope`가 만든다.
_CONFIRM_TOKENS = {}          # token -> (appid, scope, state_a, state_b, issued_at)
_CONFIRM_TTL = 180            # 초. 모달을 오래 열어 두면 만료된다
_CONFIRM_MAX = 32             # 토큰이 무한히 쌓이지 않게 — 발급만 하고 안 쓰는 경로가 정상 흐름이다
_ADD_GAME_SCOPE = "add_game"  # 등록 토큰의 네임스페이스. profile 값과 절대 겹치지 않는다
_DELETE_SCOPE = "delete_game"  # 개별 삭제 토큰의 네임스페이스
_RESET_SCOPE = "reset_all"
_RESET_FRESH_SCOPE = "reset_all:fresh"   # 손상 복구 갈래 — 정상 갈래의 `_RESET_SCOPE`와 섞지 않는다
#   (두 갈래가 지우는 대상이 다르므로 확인한 것과 실행한 것이 갈릴 여지를 스코프에서 막는다 — §7-4′ 4항).
_RESTORE_SCOPE = "restore_backup"   # 복원 토큰의 네임스페이스(합성 스코프의 앞자리 — 아래 `_restore_scope`)
_APPLY_ALL_SCOPE = "apply_all"      # 일괄 적용 토큰의 네임스페이스(방향은 4번 칸에 묶는다)
_APPLY_ONE_SCOPE = "apply_profile"  # 개별 적용 토큰의 네임스페이스(합성 스코프의 앞자리 — 아래 `_apply_scope`)
# 적용·복원은 슬롯 2에 방향·대상을 합성해 묶는다(아래 두 헬퍼). 비워 두면 dock 확인창에서
#   받은 토큰이 internal에 그대로 소비돼, 사용자가 확인한 것과 다른 방향/다른 곳의 쓰기가
#   확인 없이 실행된다(`apply_all`이 4번 칸에 profile을 묶은 것과 같은 결함·같은 방어).
#   합성이 안전한 이유: `_consume`은 튜플 전체 동등 비교만 하고 문자열을 되쪼개지 않는다.
#   profile은 {dock, internal}, target은 {dock, internal, config}로 고정 어휘이고 앞자리에
#   와서, 서로 다른 (target, backup_id)가 같은 합성 문자열을 만들 수 없다.

#: 전체 초기화의 type-to-confirm 문자열 — 고정 단어다. 등록 수 같은 가변값이 아니다:
#: 위조 방지는 토큰의 몫이고 입력은 이해 확인 장치다. 파괴 규모 고지는 입력이 아니라
#: 확인창의 warnBlock(games·profiles)이 전담한다(`src/confirmSpecs.tsx`).
#: 번역하지 않는다 — 번역하면 사용자가 본 challenge와 백엔드 상수가 언어에 따라 갈린다.
_RESET_CHALLENGE = "delete"


def _apply_scope(profile):
    """개별 적용 토큰의 슬롯 2 — 방향(dock/internal)을 싣는다. 왜인지는 위 `_APPLY_ONE_SCOPE` 주석."""
    return "%s:%s" % (_APPLY_ONE_SCOPE, profile)


def _restore_scope(target, backup_id):
    """복원 토큰의 슬롯 2 — 목적지(dock/internal/config)와 백업 파일 id를 싣는다."""
    return "%s:%s:%s" % (_RESTORE_SCOPE, target, backup_id)


def _profile_total(reg):
    """등록 게임들의 슬롯 본체 수 — 전체 초기화 확인창의 "프로필 M개".

    각 게임의 `remove.delete_preview`가 낸 `has_dock`·`has_internal`을 센다. 이 값은 본체 존재
    기준이며, meta와 본체를 모두 요구하는 `get_overview`의 적용 가능 수와는 다를 수 있다.

    `delete_preview`의 개별 삭제 지문은 슬롯 수 계산에 쓰지 않는다. 전체 초기화 route는
    `remove.reset_fingerprint`와 `remove.reset_evict_preview`의 축출 지문을 합성해 별도의
    다게임 토큰 지문을 만든다.
    """
    total = 0
    for appid in reg["games"]:
        info, _fp = remove.delete_preview(reg, appid)
        total += int(info["has_dock"]) + int(info["has_internal"])
    return total


def _warn_fingerprint(warnings):
    """등록 토큰에 묶을 경고 지문. 사용자가 본 경고와 실제 저장 직전의 경고가 같아야 한다.

    정렬해 이어 붙인다. 같은 경고 목록이면 입력 순서만 달라도 같은 지문이 된다.
    """
    return ",".join(sorted(warnings))


def _issue(appid, profile, meta_sha1, disk_sha1):
    if len(_CONFIRM_TOKENS) >= _CONFIRM_MAX:
        # 가장 오래된 것부터 절반을 버린다. 만료된 것만 골라 버리는 것이 아니라 아직 유효한
        #   토큰도 함께 사라지는데, 그때 사용자는 CONFIRM_REQUIRED를 한 번 더 받을 뿐이라
        #   안전한 방향이다(파일은 안 건드린다).
        for old in sorted(_CONFIRM_TOKENS, key=lambda k: _CONFIRM_TOKENS[k][4])[:_CONFIRM_MAX // 2]:
            _CONFIRM_TOKENS.pop(old, None)
    tok = secrets.token_urlsafe(16)
    _CONFIRM_TOKENS[tok] = (appid, profile, meta_sha1, disk_sha1, time.monotonic())
    return tok


def _consume(tok, appid, profile, meta_sha1, disk_sha1):
    """유효하면 True를 돌려주고 즉시 소각한다. 어떤 실패든 False.

    `pop`이 먼저다 — 검증에 실패해도 토큰은 사라진다. 남겨 두면 상태를 바꿔 가며 같은 토큰을
      계속 시험해 볼 수 있게 된다.
    비교는 4칸 튜플 전체 동등이다 — 스코프 문자열을 되쪼개지 않으므로 합성 스코프가 안전하다.
    """
    rec = _CONFIRM_TOKENS.pop(tok, None)
    if rec is None:
        return False
    a, p, m, d, issued = rec
    if time.monotonic() - issued > _CONFIRM_TTL:
        return False
    return (a, p, m, d) == (appid, profile, meta_sha1, disk_sha1)


# ── 손상 registry의 fresh 복구 탈출 갈래 (19판 — §7-4′) ────────────────────────

def _reset_preflight(reg):
    """탈출로 입구의 형태 검사 — 버전 무관.

    로더(§14-F′ ⓒ)는 미래 registry의 `games`를 검사하지 않는다(U5: 읽기는 막지 않는다).
    그 게이트가 남기는 「미래 + 손상 → reset 재사망」을 여기서 막는다. 미래 registry의
    읽기 능력은 이 검사로 조금도 줄지 않는다 — 여기는 탈출로 입구이지 읽기 경로가 아니다.
    보는 것은 컨테이너 둘뿐이다: appid 키와 항목의 형태는 보지 않는다(그 둘은 registry가
    멀쩡한 세계의 문제이고, §8-D 정규화 규칙이 정상 갈래에서 처리한다).
    """
    for key in ("games", "settings"):
        if not isinstance(reg.get(key), dict):
            raise store.RegistryError(
                "거부: 레지스트리 형식이 올바르지 않습니다 — %s가 dict가 아닙니다 (%s: %r). 파일: %s"
                % (key, type(reg.get(key)).__name__, reg.get(key), store.registry_path()),
                code=codes.REGISTRY_MALFORMED)


def _reset_fresh_fingerprint(code):
    """fresh 토큰에 묶을 지문 — 발급과 소비가 같은 규칙을 같은 순서로 재계산한다.

    정상 갈래의 지문(`reset_fingerprint|evict=`)은 `reg["games"]` 순회를 요구해 이 상태에서는
    산출 자체가 불가능하다. 그래서 **관측 가능한 파일 상태**에 결박한다. 고정 상수를 쓰면 파일이
    바뀌어도 토큰이 살아남아 TOCTOU 방어가 통째로 사라진다 — 상수는 최후의 한 자리뿐이다.
    """
    path = store.registry_path()
    sha = store.sha1_file(path)                      # 읽기 실패면 None(store.py 실측)
    if sha:
        return "sha1=%s|code=%s" % (sha, code)
    try:
        st = os.stat(path)
        return "stat=%d:%d:%d|code=%s" % (st.st_size, st.st_mtime_ns, st.st_ino, code)
    except OSError:
        return "unobservable|code=%s" % code          # 결박할 관측이 없다는 사실을 그대로 받는다


class Plugin:
    # ── RPC ──────────────────────────────────────────────────────────────────
    @route
    def ui_hello(self, version, fn, uicheck_missing=None):
        """프론트가 뜨자마자 부른다. 진단의 시작점이고, 언어 판정 결과가 여기서 나온다.

        `fn`은 프론트 로드 1회를 가리키는 nonce다. 로그는 여러 로드분이 한 파일에 쌓이므로
        이게 없으면 이번 로드의 줄을 과거 것과 구분할 수 없다.
        """
        language, source = lang.detect()
        decky.logger.info(
            "ui hello session=%s fn=%s front=%s lang=%s lang_source=%s uicheck_missing=%s",
            SESSION, fn, version, language, source, uicheck_missing or [],
        )
        if not source.startswith("steam-registry:"):
            # Steam UI 언어를 못 읽어 폴백했다. `source`를 남겨 판정 실패가 숨지 않게 한다.
            decky.logger.warning("lang fallback session=%s source=%s", SESSION, source)
        return _ok(
            lang=language,
            lang_source=source,
            plugin_version=_plugin_version(),
            session=SESSION,
            ui_types=_ui_types_version(),
            loader=os.environ.get("DECKY_VERSION", "unknown"),
        )

    @route
    def get_overview(self, detail=False):
        """전체 현황 — 화면이 필요로 하는 것을 한 번에 준다.

        게임별로 RPC를 부르면 N번 왕복이 되고, 화면이 부분적으로 채워지는 중간 상태가 생긴다.
        `counts`는 프론트가 다시 세지 않게 백엔드가 준다 — 두 곳에서 세면 언젠가 어긋난다.

        `detail=True`면 게임별 `disk_matches`(sha1 대조)까지 계산한다. QAM(`index.tsx`)과
        설정 팝업은 그 값을 안 읽으므로 기본은 계산하지 않는다 — 게임 수만큼 돌면서 설정 파일을
        통째로 읽는 비용이라 파일 크기에 좌우돼 예산을 예측할 수 없다. `GamesPopup`이 열릴 때만
        그 값을 낸다.
        """
        reg = store.load_registry()
        try:
            running = _running_appids()          # /proc을 1회만 훑는다 — 근거는 `_running_appids` 독스트링
            games = []
            for appid in sorted(reg["games"], key=lambda a: (
                    reg["games"][a].get("name", a)
                    if isinstance(reg["games"][a], dict) else a)):
                entry = reg["games"][appid]
                if not isinstance(entry, dict):
                    # 조회 격리(§8-D · §14-H ⓘ): 손상 항목도 목록에 뜬다. ★ 실사망점은 정렬
                    #   키다 — 비-dict 항목 하나가 위 `sorted(...)`의 `.get`에서 루프 시작 전에
                    #   죽인다. 정렬 키(위)와 이 접기는 함께 있어야 한다: 하나만 고치면 다른
                    #   자리에서 그대로 죽는다.
                    entry = {}
                # 슬롯 상태와 마지막 저장 시각을 같이 꺼낸다(meta 읽기 1회 — `_slot_view`).
                dock_ready, dock_saved, dock_sha = _slot_view(appid, "dock")
                intl_ready, intl_saved, intl_sha = _slot_view(appid, "internal")
                config_path = entry.get("config_path")
                if not isinstance(config_path, str) or not remove._paths_in_position(appid):
                    # 경로가 제자리가 아닌 게임에는 경로를 말하지 않는다 — `delete_preview`의
                    #   unsafe 분기와 같은 술어(`remove._paths_in_position`)·같은 결론이다.
                    #   화면이 "설정 파일: …"이라고 안내할 수 있는 상태가 아니고, 두 화면이 같은
                    #   게임을 두고 다르게 말하면 어느 쪽이 참인지 사용자가 가릴 방법이 없다.
                    config_path = ""
                games.append({
                    "appid": appid,
                    "name": entry.get("name") or ("appid %s" % appid),
                    "has_dock": dock_ready,
                    "has_internal": intl_ready,
                    # 화면의 "설정 파일: {path}" 한 줄 — 표시 전용이다.
                    #   빈 값이면 화면이 그 줄을 안 그린다(기존 "0이면 안 그림" 문법).
                    #   프론트는 이 값으로 경로 연산을 하지 않는다 — 경로 판단은 전부 백엔드다.
                    "config_path": config_path,
                    # 두 프로필의 내용이 같은가 — "갈아끼워도 달라지는 게 없다"를 화면이
                    #   말할 수 있게 한다. 둘 다 적용 가능하고, 두 meta sha가 비어 있지 않은
                    #   문자열이며, 서로 같을 때만 참이다 — `None == None`류 우연 일치로 참이
                    #   되면 화면이 없는 사실을 말한다. 재료는 위에서 이미 읽었다(IO 순증 0).
                    "profiles_identical": bool(dock_ready and intl_ready
                                               and dock_sha and dock_sha == intl_sha),
                    # 상시 표시용. 「마지막 저장」이지 「마지막 적용」이 아니다.
                    #   복원(`engine.restore_backup`)은 `last_applied`를 갱신하지 않으므로,
                    #   화면에 "마지막 적용"을 그리면 복원 뒤에 낡은 값이 사실인 척 보인다.
                    #   그래서 이 봉투도 화면도 「저장」만 말한다 — 없는 사실을 만들지 않는다.
                    "saved_at": {"dock": dock_saved, "internal": intl_saved},
                    # 배열이다. 두 슬롯의 내용이 같으면 둘 다 실린다.
                    #   `engine.disk_state`는 첫 일치에서 `break` 하므로, 그 값을 그대로 쓰면
                    #   봉투가 임의로 한쪽만 고르고, 화면은 나머지 한쪽을 "적용돼 있지 않다"고
                    #   거짓으로 말한다. 어느 쪽이 실릴지는 `store.list_profiles` 순서가 정한다.
                    #   슬롯 쪽 재료는 위에서 이미 읽은 두 meta sha다.
                    #   `detail=False`면 빈 배열이다. 「모른다」를 빈 배열로 적는 것이 아니라,
                    #     그 호출이 묻지 않은 값이라는 뜻이다.
                    "disk_matches": _disk_matches(reg, appid, dock_sha, intl_sha) if detail else [],
                    # 게임 목록 팝업의 `[백업 N]`이 쓰는 수 — 백엔드가 센다(counts와 같은 규칙).
                    #   `detail`과 무관하게 낸다: 이 값의 비용은 백업 디렉터리 나열뿐이고
                    #   설정 파일을 읽지 않으므로, detail 게이트의 근거(파일 크기에 좌우되는
                    #   예측 불가 비용)가 여기엔 적용되지 않는다. 봉투에서 빼면 목록 화면이
                    #   게임마다 따로 물어야 한다.
                    "backups": restore.backup_count(appid),
                    "last_applied": entry.get("last_applied"),
                    "cloud_synced": bool(entry.get("cloud_synced")),
                    "running": appid in running,
                })
            # 사용자가 정한 표시명. 빈 문자열이면 기본 이름이고, 그 기본 이름이 무엇인지는
            #   백엔드가 모른다 — 번역이라 언어에 따라 다르고 판정은 프론트 i18n 한 곳에만
            #   있어야 한다. 식별자(`dock`/`internal`)는 이 값과 무관하게 불변이다.
            return _ok(games=games, profile_names=labels.stored(reg), counts={
                "total": len(games),
                # 일괄 버튼 라벨이 쓰는 수 — 등록 수가 아니라 그 프로필을 실제로 가진 게임 수다.
                #   등록 수를 쓰면 없는 게임은 건너뛰므로 라벨이 거짓말을 한다.
                "dock_ready": sum(1 for g in games if g["has_dock"]),
                "internal_ready": sum(1 for g in games if g["has_internal"]),
                "running": sum(1 for g in games if g["running"]),
                # 두 프로필 중 하나라도 없는 게임 수. 봉투 계약(`rpc.ts`의 `OverviewCounts`)에는
                # 있으나 지금 이 값을 그리는 화면은 없다 — 살릴 때도 프론트에서 games를 다시
                # 세지 않는다(두 곳에서 세면 언젠가 어긋난다).
                "incomplete": sum(1 for g in games if not (g["has_dock"] and g["has_internal"])),
                # 감지에서 제외한 게임 수. 설정 팝업의 [전체 초기화] 활성 조건이 쓴다 —
                #   마지막 게임을 등록 해제하면 `total=0`인데 제외 목록은 남으므로, total만 보면
                #   그 목록을 지울 방법이 UI에서 사라진다. 원본 키 수다(격리분 포함 —
                #   `exclude.excluded_map` 주석 참조).
                "excluded": len(exclude.excluded_map(reg)),
            })
        except Exception:
            # 스키마가 갈라져 조립이 죽는 최악 경로에서 정확한 고지를 낸다.
            #   여기까지 온 예외의 사유가 「이 데이터를 더 새 버전이 만들었다」일 수 있는데,
            #   그대로 두면 화면에는 UNEXPECTED만 남아 사용자가 할 일을 알 수 없다.
            #   호환일 때는 아무 개입도 하지 않는다 — 아래 `raise`가 원래 실패를 그대로
            #     올려보내고, route 데코레이터가 늘 하던 대로 봉투에 싣는다.
            _guard_not_newer(reg)
            raise

    @route          # 바깥 — 봉투. 뒤집히면 RegistryError가 봉투 없이 전송 계층으로 샌다.
    @mutating       # 안쪽 — 관문. 순서를 뒤집지 마라(위 `mutating` 독스트링).
    def apply_profile(self, appid, profile, confirm_token=None):
        """게임 하나에 적용 — 저장된 프로필 → 게임 설정 파일 한 방향이다(A11).

        2단계 계약이다. 판정은 `confirm.apply_needs_confirm` 한 곳이고 여기는 그
          3-상태(`already`/`proceed`/`confirm`)를 봉투로 옮길 뿐이다 — 접착층은 정책 판단을
          하지 않는다. 세 상태의 뜻과 경계는 그 함수의 독스트링이 정본이다.
        `already`에서 엔진을 부르지 않는 것은 이 route의 몫이다 — 엔진에는 already 스킵이 없어
          낙하시키면 같은 내용을 파일에 다시 쓴다.
        토큰 슬롯 2에 방향을 묶는다(`_apply_scope`) — 안 묶으면 dock 확인창에서 받은 토큰으로
          internal이 적용된다.
        `CONFIRM_REQUIRED`는 실패가 아니라 흐름 신호다(`codes.FLOW_CODES`).
        """
        reg = store.load_registry()
        # 실행 중 게임·미등록은 여기서 `Refused`로 나간다(route 데코레이터가 봉투에 싣는다).
        # 판정 함수가 params와 지문을 함께 돌려준다 — 고지에 쓴 그 관측값이
        #   그대로 지문이 되므로 고지와 지문 사이에 관측이 한 번 더 끼는 창이 없다.
        #   지문은 `params`가 아니라 별도 변수다 — `**params`로 splat해도 화면 봉투에 안 샌다.
        state, params, fp = confirm.apply_needs_confirm(reg, appid, profile)
        if state == "already":
            # 쓰기 0 · 백업 0 · 링 소모 0. 무반응이 아니라 결과다 — 화면이 그 사실을 말한다.
            return _ok(outcome="already", **params)
        if state == "confirm":
            meta_sha1, disk_sha1 = fp
            scope = _apply_scope(profile)
            if not _consume(confirm_token, str(appid), scope, meta_sha1, disk_sha1):
                # 여기서 파일을 건드리지 않는다. 없든 위조든 만료든 방향이 다르든 상태가
                #   바뀌었든 전부 같은 자리다 — 화면이 할 일은 "다시 물어보기" 하나뿐이다.
                #   새 토큰은 지금 관측한 상태에 묶여 나간다(TOCTOU).
                return _fail(codes.CONFIRM_REQUIRED,
                             confirm_token=_issue(str(appid), scope, meta_sha1, disk_sha1),
                             **params)
        try:
            result = engine.apply_profile(reg, appid, profile)
            # 설정 파일을 실제로 갈아끼운 사실을 남긴다. 남기지 않으면 "내 설정이 왜 바뀌었지"를
            #   나중에 추적할 방법이 없다 — Game Mode엔 터미널이 없어 로그가 유일한 단서다.
            #   레지스트리 저장보다 먼저 남긴다: 저장이 실패해도 파일은 이미 바뀐 뒤다.
            decky.logger.info("apply_profile session=%s appid=%s profile=%s state=%s",
                              SESSION, appid, profile, state)
            _save_registry(reg)
        except engine.Refused:
            raise                       # route 데코레이터가 code·params를 그대로 실패 봉투에 싣는다
        except Exception as exc:        # noqa: BLE001 — 파일이 이미 바뀐 뒤일 수 있는 실패
            # 전문 로그는 여기서 남긴다(데코레이터의 UNEXPECTED 경로는 사유를 못 싣는다).
            # 로그 접두는 데코레이터와 같은 `unexpected`다 — 진단은 접두로 grep한다.
            decky.logger.error("unexpected session=%s route=apply_profile appid=%s profile=%s\n%s",
                               SESSION, appid, profile, traceback.format_exc())
            raise engine.Refused("거부: 예기치 못한 오류로 적용을 마치지 못했습니다.",
                                 code=codes.UNEXPECTED) from exc
        return _ok(**result, outcome="applied")

    @route
    @mutating
    def apply_all(self, profile, confirm_token=None):
        """주 동작 — 등록된 전부에 같은 프로필을 적용한다.

        2단계 계약이다. 토큰이 없으면 아무것도 쓰지 않고 `CONFIRM_REQUIRED` + 5버킷 미리보기를
        돌려준다. 2차 호출의 동작은 토큰 검사를 뺀 나머지가 그대로다 — 하나 거부·나머지 적용·
        봉투 `ok:true`.

        항상 묻는다(would_apply=0이어도). 위협 모델은 데이터 손실이 아니라 의도치 않은 발동
        그 자체다. "변경 없을 때만 조용히 실행"으로 조건부를 만들면 방지 장치가 어떤 때는 잡고
        어떤 때는 안 잡는 비결정적 물건이 된다.

        토큰 슬롯 = `("*", _APPLY_ALL_SCOPE, fp, profile)`이고 `fp`는 아래에서 합성한다.
        4번 칸에 profile을 묶는다 — 비워 두면 dock 미리보기에서 발급한 토큰이
        `apply_all("internal", token)`에 그대로 소비돼, 사용자가 확인한 것과 다른 방향의 일괄
        쓰기가 확인 없이 실행된다. `reset_all`이 challenge를 같은 칸에 넣는 문법 그대로라
        `_issue`/`_consume`은 한 줄도 고치지 않는다.

        미리보기는 같은 관측 시점의 엔진 판정 순서를 재현한다. 확인 뒤 상태가 바뀌면 결과는 어느
        방향으로도 달라질 수 있다. 특히 실행 중 상태는 축출 대상을 바꾸지 않는 한 토큰 지문에 남지
        않으므로, 미리보기에서 `running_refused`였던 게임이 확인 뒤 종료되면 실제로 적용될 수 있다.
        화면의 「예상」은 동치 보증이 아니라 관측 시점의 분류라는 뜻이다.

        지문은 registry 상태와 축출 대상을 묶지만 디스크 sha1·실행 상태 자체를 묶지는 않는다.
        그 변화가 축출 대상을 바꾸면 다시 묻고, 바꾸지 않으면 기존 토큰이 통과할 수 있다.
        디스크 sha1을 지문에 넣으면 실행 중인 게임이 설정을 다시 쓸 때마다 토큰이 무효가 되어
        확인→재확인 루프가 생기고 방지 장치가 사용 불능이 된다 — 그래서 일부러 뺀다.

        그래서 슬롯 3(`fp`)은 `remove.reset_fingerprint`에 축출 지문을 이어 붙인 값이다.
        `reset_fingerprint` 하나로는 "몇 건이 지워집니다"라는 약속을 지킬 수 없다 —
          · 그 지문의 링 신호는 게임별 개수뿐이라 포화 링의 회전(개수 불변)을 못 잡고,
          · 설정 파일 sha가 위 이유로 지문에서 빠져 있어, 확인창을 띄운 사이 게임·클라우드가
            설정 파일을 고유 내용으로 바꾸면 "축출 0건"이라 말한 토큰이 그대로 통과할 수 있다.
            그 다음 실행은 대피본을 만들고 prune이 돌아 고지에 없던 백업 1건을 지운다(손실 경로).
        그래서 개수가 아니라 대상(게임별 `backup_id` 전량·순서)의 지문을 슬롯 3에 합성한다.
        `_consume`은 4칸 튜플 전체 동등 비교만 하고 문자열을 되쪼개지 않으므로 합성이 안전하고,
        슬롯을 늘리지 않아 발급·소비 계약이 한 줄도 안 바뀐다.
        디스크 sha 배제는 여전히 유효하되 범위가 좁아졌다 — 설정 파일이 다시 쓰여도 토큰은
        그대로이고, 그 변화가 지워질 백업을 바꾸는 때(=그 게임 링이 이미 가득 찬 때)만 다시
        묻는다. 그때의 재확인은 마찰이 아니라 고지의 정정이다.
        못 재는 것은 미리보기 전체와 같다(`confirm.apply_all_evict_preview` 독스트링이 정본).

        게임별 실패가 있어도 봉투는 `ok:true`다. 일괄 적용의 불변식은 "하나가 실패해도 나머지는
        계속"이고, 봉투를 실패로 만들면 그 불변식이 봉투 층에서 뒤집힌다. 무엇이 안 됐는지는
        `results[].outcome`으로 전부 올라간다.
        """
        reg = store.load_registry()
        # `running`은 /proc 1회 스캔 결과이고 지문과 두 미리보기가 그 하나를 공유한다 —
        #   두 번 재면 그 사이 게임이 켜져 토큰이 잰 세계와 화면이 말하는 세계가 갈린다.
        #   발급 갈래로 내리면 안 된다: 지문은 소비 갈래에서도 같은 방법으로 다시 나야 한다.
        running = _running_appids()
        # 축출 예고와 그 지문은 한 번의 산출에서 같이 나온다 — 화면이 말하는 수와 토큰이
        # 묶는 대상이 같은 관측이라야 "수가 정확하다"가 성립한다.
        evict = confirm.apply_all_evict_preview(reg, profile, running)
        fp = "%s|evict=%s" % (remove.reset_fingerprint(reg), evict["fingerprint"])
        if not _consume(confirm_token, "*", _APPLY_ALL_SCOPE, fp, profile):
            # 여기서 파일을 하나도 건드리지 않는다. 미리보기는 순수 조회다.
            preview = confirm.apply_all_preview(reg, profile, running)
            return _fail(codes.CONFIRM_REQUIRED,
                         confirm_token=_issue("*", _APPLY_ALL_SCOPE, fp, profile),
                         # 확인창 본문의 "등록된 게임 {total}개"는 이 값만 쓴다:
                         #   토큰 발급 시점의 스냅샷이라, 화면 숫자가 토큰이 지문 낸 대상과
                         #   언제나 같은 것을 가리킨다(`get_overview`의 total은 다른 시점의
                         #   조회라 어긋날 수 있다). 5버킷의 합 = 이 값이 계약이다.
                         # 축출 고지는 수만 싣는다 — 게임이 여럿이라 이름을 나열하면 창이
                         #   터진다. 산출은 게임별 예고와 같은 함수다.
                         #   지문(`fingerprint`)은 싣지 않는다 — 토큰의 재료이지 화면 값이
                         #     아니다. 통째로 splat하면 봉투 계약에 없는 필드가 화면까지 샌다.
                         profile=profile, total=len(reg["games"]),
                         evicted=evict["evicted"], evict_games=evict["evict_games"],
                         **preview)
        try:
            results = engine.apply_all(reg, profile)
            counts = {}
            for row in results:
                counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
            # 감사 로그는 `save_registry`보다 먼저 남긴다.
            #   뒤에 두면, registry 저장이 실패해 예외가 나가는 순간 설정 파일은 이미 바뀐 뒤인데
            #   로그가 한 줄도 없는 상태가 된다(엔진은 config를 먼저 쓴다).
            #   그리고 `applied`만 적으면 안 된다 — outcome이 `error`인 게임도 설정 파일은 이미
            #   바뀌었을 수 있다(같은 이유). 전 게임의 outcome을 그대로 남겨야 "무엇이 바뀌었을
            #   수 있는가"를 로그만으로 좁힐 수 있다.
            #   outcome만으로는 부족하다: 어느 게임이 왜 거부됐는지가 어디에도 안 남는다.
            #   화면에서 상세를 뺀 근거가 "로그가 정본"인데 그 로그에 사유가 없으면 그 정보는
            #   그냥 사라진 것이다. 그래서 문제 행(code가 있는 것)만 상세를 싣는다 —
            #   정상(applied/already/no_profile)은 code가 없어 자동으로 빠지므로 등록이 많아도
            #   안 불어난다. `note`는 200자로 자른다(예외 메시지에 긴 경로가 실릴 수 있다).
            problems = {
                r["appid"]: {"code": r.get("code"), "note": (r.get("note") or "")[:200]}
                for r in results if r.get("code")
            }
            decky.logger.info(
                "apply_all session=%s profile=%s counts=%s outcomes=%s problems=%s",
                SESSION, profile, counts,
                {r["appid"]: r["outcome"] for r in results}, problems,
            )
            _save_registry(reg)
        except Exception as exc:        # noqa: BLE001 — `save_registry` 실패도 여기로 온다
            # 엔진 `apply_all`은 게임별 예외를 내부에서 격리하므로 여기로 `Refused`가
            #   올라오는 갈래는 없다 — 안 오는 것을 잡는 분기를 두지 않는다(죽은 문 금지).
            decky.logger.error("unexpected session=%s route=apply_all profile=%s\n%s",
                               SESSION, profile, traceback.format_exc())
            raise engine.Refused("거부: 예기치 못한 오류로 일괄 적용을 마치지 못했습니다.",
                                 code=codes.UNEXPECTED) from exc
        return _ok(results=results, counts=counts)

    @route
    @mutating
    def save_profile(self, appid, profile, confirm_token=None):
        """현재 디스크 상태를 프로필로 캡처한다. 기존 프로필을 덮어쓸 때만 확인을 요구한다.

        빈 슬롯에 처음 저장하는 것(=초기 세팅에서 A·B 두 벌 만들기)은 잃을 것이 없으므로 묻지
        않는다. "저장이면 무조건 묻는다"로 만들면 초기 세팅이 통째로 확인창이 된다 — 사용자가
        명시적으로 피한 마찰이다.

        `CONFIRM_REQUIRED`는 실패가 아니라 흐름 신호인데 `{ok:false}` 봉투를 쓴다
        (`codes.FLOW_CODES`). 토스트·로그에서 에러로 취급하지 마라.
        """
        reg = store.load_registry()
        # 판정 함수가 params와 지문을 함께 돌려준다 — 적용과 같은 문법이다.
        #   고지에 쓴 그 관측값이 그대로 지문이 되므로, 고지와 지문 사이에 낄 창이 없다.
        need, params, fp = confirm.needs_confirm(reg, appid, profile)
        if need:
            meta_sha1, disk_sha1 = fp
            if not _consume(confirm_token, appid, profile, meta_sha1, disk_sha1):
                # 여기서 파일을 건드리지 않는다. 토큰이 없든 위조든 만료든 상태가 바뀌었든
                #   전부 같은 자리로 온다 — 사유를 갈라 봐야 화면이 할 일은 "다시 물어보기" 하나다.
                #   새 토큰은 지금 관측한 상태에 묶여 나간다. 확인창을 띄운 사이에 게임이
                #     설정을 다시 썼다면 사용자가 보는 숫자도 같이 갱신돼야 하기 때문이다(TOCTOU).
                return _fail(codes.CONFIRM_REQUIRED,
                             confirm_token=_issue(appid, profile, meta_sha1, disk_sha1),
                             **params)
        try:
            result = engine.save_profile(reg, appid, profile)
        except ValueError as exc:
            # 손상된 `meta.json`이나 그 안의 잘못된 값은 저장 전에 `ValueError`를 낼 수 있다.
            # 일반 `UNEXPECTED`로 뭉개면 복구 안내를 할 수 없으므로 사유를 밝힌다.
            # 이 갈래는 아무것도 쓰지 않고 실패한다: meta 읽기와 크기 가드는 엔진의 첫 쓰기보다
            # 앞이고, 이후의 `store.slot_holds`는 `ValueError`를 내부에서 거짓으로 접는다.
            raise engine.Refused("거부: 프로필 정보가 손상되어 저장할 수 없습니다 — %s" % exc,
                                 code=codes.PROFILE_META_CORRUPT) from exc
        except OSError as exc:
            # 기기 상태 문제는 「손상」이 아니다. 디스크 가득참(`ENOSPC`)·슬롯 폴더 권한·그 밖의
            #   입출력 실패를 위 코드로 내보내면 화면이 "프로필 정보가 손상되어"라 말하고 사용자는
            #   엉뚱한 복구(재저장·백업 복원)를 시도한다 — 정작 해야 할 일은 공간을 비우거나
            #   권한을 고치는 것이다.
            # 여기서는 "아무것도 쓰지 않고 실패한다"가 참이 아니다: `store.write_profile`이 본체를
            #   먼저 쓰고 기록을 나중에 쓰므로 반쪽 상태가 남을 수 있다. 그래서 이 갈래는 그
            #   문장을 데려오지 않는다.
            raise engine.Refused(
                "거부: 프로필을 저장하지 못했습니다 (저장 공간이나 파일 권한을 확인해 주세요) — %s"
                % exc, code=codes.PROFILE_WRITE_FAILED) from exc
        # 덮어쓰기는 되돌리기 어려운 동작이다. 레지스트리 저장보다 먼저 남긴다 — 저장이 실패해도
        #   프로필 파일은 이미 바뀐 뒤다.
        # `outcome`을 같이 남긴다: `already`는 한 바이트도 안 쓴 갈래라, 이 값이 없으면 로그만
        #   보고 "저장했다"와 "쓰지 않았다"를 구별할 수 없다 — 백업 링이 왜 안 돌았는지를
        #   사후에 확인할 유일한 단서다(Game Mode엔 터미널이 없다).
        decky.logger.info(
            "save_profile session=%s appid=%s profile=%s overwrote=%s outcome=%s sha1=%s",
            SESSION, appid, profile, need, result.get("outcome"),
            (result.get("meta") or {}).get("sha1", "")[:10],
        )
        _save_registry(reg)
        return _ok(**result)

    # ── 게임 추가 ────────────────────────────────────────────────────────────
    @route
    def discover_games(self):
        """설치된 게임을 훑어 설정 파일 후보를 돌려준다. 인자가 없다 · 아무것도 쓰지 않는다.

        `discover`의 파일 접근은 전부 읽기 전용이다 — 여는 것은 `open(..., "r")` 하나뿐이고
        나머지는 디렉터리·메타데이터 조회다. 등록은 별도 route가 하고, 이 route를 불러서
        무엇이 바뀌는 일은 없다.

        `counts`는 백엔드가 센다 — 프론트가 다시 세면 두 곳에서 세는 것이고, 언젠가 어긋난다
        (`get_overview`와 같은 규칙).
        """
        reg = store.load_registry()
        entries = _discover_entries(reg)
        payload = [_entry_payload(e) for e in entries]
        counts = {
            "total": len(payload),
            "registered": sum(1 for e in payload if e["registered"]),
            "unregistered": sum(1 for e in payload if not e["registered"]),
            "confident_unregistered": sum(
                1 for e in payload if e["confident"] and not e["registered"] and e["best"]),
        }
        decky.logger.info("discover session=%s counts=%s", SESSION, counts)
        # `libraries`는 탐지 0건일 때 파일 선택기를 어디서 열지를 화면에 알려준다.
        #   0건이면 `entries`가 비어 시작 위치를 만들 근거가 사라지는데, 그러면 안내가 가리키는
        #   「파일 직접 고르기」를 화면이 그릴 수 없다 — 없는 조작을 권하는 문구가 된다.
        #   프론트가 경로를 지어내지 않게 백엔드가 실재하는 루트를 준다.
        # `excluded`는 감지에서 제외한 게임 — 「제외한 게임 보기」 뷰의 재료다.
        #   `include_game`과 같은 헬퍼를 지나므로 두 봉투의 모양이 구조적으로 같다.
        return _ok(entries=payload, counts=counts, libraries=engine.steam_libraries(),
                   excluded=_excluded_rows(reg))

    @route
    @mutating
    def include_game(self, appid):
        """감지 제외를 해제한다 — 한 버튼 한 쓰기(재포함 경로).

        재포함은 등록이 아니다. 여기서 하는 일은 제외 목록에서 내리는 것뿐이고, 그러면 그 게임이
          탐지 목록에 후보로 다시 뜬다(설치돼 있고 설정 파일이 있을 때). 등록은 사용자가 감지
          목록에서 다시 한다 — 한 버튼이 두 가지 쓰기를 하지 않는다.
        제외돼 있지 않은 appid도 정상 종료다(멱등). 「제외돼 있을 때만 부른다」는 조건을 호출부가
          판단하면 화면과 백엔드가 언젠가 갈라진다 — 결과 상태만 계약한다.
        """
        reg = store.load_registry()
        record = exclude.excluded_map(reg).get(str(appid))
        name = record.get("name") if isinstance(record, dict) else ""
        was_excluded = exclude.remove(reg, appid)
        # 감사 로그는 `save_registry`보다 먼저.
        decky.logger.info("include_game session=%s appid=%s name=%s was_excluded=%s",
                          SESSION, appid, name, was_excluded)
        _save_registry(reg)
        return _ok(excluded=_excluded_rows(reg))

    @route
    @mutating
    def register_confident(self):
        """확신 후보를 한 번에 등록한다.

        appid 목록을 인자로 받지 않는다. `_validate`는 파라미터 이름 단위로만 도는데 리스트 안의
          원소는 그 검사를 통과하지 않는다 — `appids=["../../x"]`가 그대로 `reg["games"]` 키와
          `compat_prefix`의 경로 조각이 된다. 인자를 없애면 검증할 것 자체가 없다
          (`qa/test_discover_routes.py`가 인자 없음을 잠근다). 사용자가 「무엇을 등록할지」 고르는
          것은 화면의 필터일 뿐, 목록을 왕복시킬 이유가 없다.

        경로는 백엔드가 `best_candidate()`로 정한다 — 프론트가 경로를 만들지 않는다.

        감지 제외에 대해 이 route는 아무것도 하지 않는다. 제외분은 `_discover_entries` 필터가
          구조적으로 배제하므로 여기 도달 자체가 불가능하고, 여기에 해제를 한 줄 더 두면 문이
          둘이 된다 — 가드는 문 하나다.

        `apply_all`과 같은 원칙: 하나가 실패해도 나머지는 계속하고 봉투는 `ok:true`다. 무엇이
          안 됐는지는 `results[]`의 outcome과 사유로 전부 올라간다.
        """
        reg = store.load_registry()
        results = []
        for entry in _discover_entries(reg):
            if entry["registered"] or not entry["confident"]:
                continue
            cand = discover.best_candidate(entry)
            row = {"appid": entry["appid"], "name": entry["name"],
                   "outcome": "added", "code": None, "note": ""}
            results.append(row)
            if cand is None:
                # confident인데 best가 없다 = 엔진 판정이 어긋난 것. 조용히 넘기지 않는다.
                row.update(outcome="error", note="confident인데 후보를 고르지 못했습니다")
                continue
            try:
                engine.add_game(reg, entry["appid"], cand["path"], entry["name"])
            except (engine.Refused, store.RegistryError) as exc:
                row.update(outcome="refused", code=exc.code, note=str(exc).splitlines()[0])
            # 아래 `except` 줄을 다른 route에 복제하지 말 것.
            #   `qa/test_discover_routes.py`의 §B 반증이 이 줄을 변이 앵커로 쓴다
            #   (그 줄만 고친 main.py 사본을 올려 「격리가 사라진 구현」을 재현한다).
            #   같은 문자열이 파일에 둘이면 앵커가 모호해져 반증이 아예 안 돈다 —
            #   테스트가 그 상황을 AssertionError로 크게 실패시키므로 조용히 썩지는 않는다.
            except Exception as exc:                       # noqa: BLE001
                # 넓게 잡는다 — 이 함수의 존재 이유가 「하나가 실패해도 나머지는 계속」이고,
                # 그 약속이 예외 종류에 따라 깨지면 안 된다(apply_all과 같은 판단).
                row.update(outcome="error",
                           note="%s: %s" % (type(exc).__name__, exc))
        counts = {}
        for row in results:
            counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
        # 감사 로그는 `save_registry`보다 먼저 — `qa/test_discover_routes.py`가 그 순서를 잰다.
        #   문제 행만 사유를 싣는다: 정상 행은 자동으로 빠지므로 500게임에서도 로그가 안 불어난다.
        problems = {r["appid"]: {"code": r["code"], "note": r["note"][:200]}
                    for r in results if r["outcome"] != "added"}
        decky.logger.info(
            "register_confident session=%s counts=%s added=%s problems=%s",
            SESSION, counts, [r["appid"] for r in results if r["outcome"] == "added"], problems)
        if counts.get("added"):
            _save_registry(reg)          # 루프 밖 1회. 등록이 0건이면 쓰지 않는다.
        return _ok(results=results, counts=counts)

    @route
    @mutating
    def add_game(self, appid, config_path, name=None, confirm_token=None):
        """게임 하나를 등록한다 — 탐지 목록의 후보 1탭 등록과 파일 선택기가 같은 문을 쓴다.

        2단계 계약이다. 경고가 나오는 파일은 첫 호출에서 저장하지 않는다 — 검증만 하고
          `CONFIRM_REQUIRED`와 1회용 토큰을 돌려주고, 사용자가 확인창에서 확정해 토큰과 함께
          다시 부를 때 비로소 저장한다.

          경고가 없으면 토큰 없이 즉시 등록한다. 계약의 절반은 묻지 않는 것이다 — 자동 탐지
            후보(구조적으로 무경고)와 무경고 수동 선택까지 되물으면 `save_profile`이 명시적으로
            피한 확인창 지옥이 등록 경로에 재현된다.

        이미 등록된 appid는 `codes.ALREADY_REGISTERED`로 거부한다. 경로 변경 기능은 아직 없다.
          판정은 `confirm.already_registered`가 한다. ★ 19판 — 그 항목의 등록 기록이 손상돼
          있으면 `REGISTRY_ENTRY_CORRUPT`가 대신 나간다(§8-D 정규화 규칙): 「이미 등록됨」은 그
          기록을 믿을 수 있을 때만 참인 진술이고, 못 믿는 `name`·`config_path`를 화면 봉투에
          실어 보내지 않기 위해서다.

        검증 단계에서 엔진 문을 복제하지 않는다. `reg`의 일회용 사본에 진짜 `engine.add_game`을
          통과시켜 G11/G14를 그대로 받는다 — 문은 여전히 하나이고, 사본은 버려지므로 실제
          registry는 1바이트도 바뀌지 않는다.

        `config_path`를 여기서 검증하지 않는다. 이 값은 진짜 절대경로여야 하므로 `_VALIDATORS`식
          형태 검증으로는 아무것도 보장하지 못하고, 접착층에 가드를 하나 더 만들면 정책 판단이
          두 곳으로 갈린다. 문은 엔진 하나다 — `check_path`(G11, 심볼릭 링크·prefix 밖) →
          `assert_config_candidate`(G14, `.sav` 등 5갈래 — 열거의 정본은 그 함수의 독스트링이다).
          `_VALIDATORS`에 `config_path`를 넣으면 실패가 `BAD_IDENTIFIER`라는 엉뚱한 사유로 나가
          화면이 문구를 못 고른다(`qa/test_discover_routes.py`가 이중 판정을 막는다).
          (`appid`는 경로 조각이 되므로 데코레이터가 자동으로 숫자만 통과시킨다.)

        `warnings`는 `add_game`이 통과한 뒤에만 조회한다 — 근거는 그 줄의 주석이 정본이다.
        """
        reg = store.load_registry()

        known = confirm.already_registered(reg, appid)
        if known:
            decky.logger.info("add_game refused-existing session=%s appid=%s", SESSION, appid)
            return _fail(codes.ALREADY_REGISTERED, **known)

        # ── 1단계: 검증만. 일회용 사본에 진짜 엔진을 통과시킨다(문은 하나) ───────────
        probe = engine.add_game(copy.deepcopy(reg), appid, config_path, name)
        real_path = probe["config_path"]
        # `warnings`는 `add_game`이 통과한 뒤에만 조회한다 — `qa/test_discover_routes.py`가
        #   이 순서를 잰다. `config_candidate_warnings`는 경로가 prefix 아래라는 것을 전제로
        #   길이 슬라이싱을 하므로, 먼저 부르면 전제가 깨진 채 의미 없는 문자열로 거짓 경고를
        #   만든다. 결과는 (appid, 확정 경로)만의 함수라 2단계에서 다시 부르지 않는다.
        warnings = engine.config_candidate_warnings(appid, real_path)

        need, params = confirm.add_game_needs_confirm(warnings)
        if need and not _consume(confirm_token, str(appid), _ADD_GAME_SCOPE,
                                 real_path, _warn_fingerprint(warnings)):
            # 여기서 실제 registry는 아직 바뀌지 않는다. 토큰은 이번 1단계가 확정한 경로와
            #   경고 지문으로 검증한다. 실제 등록은 아래에서 원본 config_path를 다시 해석한다.
            return _fail(codes.CONFIRM_REQUIRED,
                         confirm_token=_issue(str(appid), _ADD_GAME_SCOPE,
                                              real_path, _warn_fingerprint(warnings)),
                         name=probe.get("name"), config_path=real_path, **params)

        # ── 2단계: 같은 문을 실제 registry에 통과시킨다 ─────────────────────────────
        entry = engine.add_game(reg, appid, config_path, name)
        # 등록하면 감지 제외도 자동으로 풀린다. 사용자가 이 게임을 다시 쓰기로 한 마당에
        #   「감지에서 숨김」이 남아 있으면, 나중에 등록을 해제했을 때 목록에 안 뜨는 이유를
        #   아무도 설명할 수 없다. 제외는 탐지 표시 정책이라 엔진이 아니라 여기서 푼다.
        was_excluded = exclude.remove(reg, appid)
        # 봉투 재료는 커밋(save_registry) 전에 다 확보한다. 뒤에 두면 대피본 조회가 실패하는
        #   순간 등록은 영구화됐는데 봉투는 UNEXPECTED가 되고, 사용자가 다시 누르면
        #   `ALREADY_REGISTERED`라 화면이 영영 성공을 말하지 못한다.
        #   (조회는 가볍고, 안전하지 않은 경로는 0으로 접힌다.)
        backups = restore.backup_count(appid)
        # 등록은 registry를 바꾸는 동작이다. `save_registry`보다 먼저 남긴다.
        decky.logger.info(
            "add_game session=%s appid=%s name=%s cloud=%s warnings=%s confirmed=%s "
            "was_excluded=%s backups=%s path=%s",
            SESSION, appid, entry.get("name"), entry.get("cloud_synced"), warnings, need,
            was_excluded, backups, entry.get("config_path"))
        _save_registry(reg)
        # 엔진 entry를 통째로 싣지 않는다 — 내부 필드(sticky_*)는 화면이 쓰지 않고,
        # 구조가 바뀔 때마다 봉투 계약이 같이 흔들린다.
        return _ok(
            appid=str(appid),
            name=entry.get("name"),
            config_path=entry.get("config_path"),
            cloud_synced=bool(entry.get("cloud_synced")),
            warnings=warnings,
            # 재등록 직후의 대피본 안내 — 등록을 해제해도 백업은 남으므로, 다시 등록한 순간
            #   「복원할 것이 있다」를 화면이 말할 수 있어야 한다. 세는 것은 백엔드다(프론트
            #   재계산 금지). 값은 커밋 전에 확보했다(위 주석).
            backups=backups,
        )

    # ── 삭제 ─────────────────────────────────────────────────────────────────
    @route
    @mutating
    def delete_game(self, appid, confirm_token=None):
        """등록 + 프로필을 지운다. 백업(`backups/`)은 남긴다 — 마지막 안전망이다.

        게임 설정 파일 원본(`config_path`)은 건드리지 않는다. 지우는 것은 툴의 데이터뿐이라
        실행 중인 게임을 막지도 않는다 — 상호작용이 없는 곳에 가드를 세우는 것은 문법 오염이다.

        항상 묻는다. 빈 슬롯 저장과 달리 "잃을 것이 없는 삭제"는 없고(최소한 등록 메타데이터를
        잃는다), 저빈도 동작이라 확인창 지옥 우려가 성립하지 않는다.

        토큰은 그 게임의 프로필 상태(두 슬롯의 meta 파일 sha1 + 백업 링)에 묶인다 — 확인창을
        띄운 사이 어느 슬롯이든 저장되면 낡은 토큰이 거부되고 다시 묻는다(TOCTOU).
        """
        reg = store.load_registry()
        # 판정 함수가 params와 지문을 함께 돌려준다. 여기서 지문을 따로 더 관측하면 그 사이의
        #   변화가 토큰에 구워진다 — 지금은 고지에 쓴 그 관측값이 지문이다.
        # 네 번째 칸은 백업 링의 지문이다. 확인창이 "이 백업이 지워집니다"라고 이름을 대므로,
        #   그 사이 링이 돌면 승인 대상이 달라진다 — 그때는 새 목록으로 다시 묻는다. 포화 링은
        #   개수가 `store.BACKUP_KEEP`으로 불변이라 세 번째 칸의 개수 신호에는 안 걸린다.
        # 세 번째 칸에는 축출 대상 전량의 지문(`|evict=`)이 함께 접혀 있다(합성은
        #   `remove.delete_preview`). 링의 이름도 개수도 그대로인데 슬롯 본체 수가 변해 잘리는
        #   깊이만 달라지는 자리를 그 칸이 잡는다 — `apply_all`·`reset_all`과 같은 문법이다.
        #   여기는 옮기기만 한다.
        # 지문은 `params`가 아니라 별도 변수다 — 아래 `**params` splat에 안 섞인다.
        params, (fp, ring) = remove.delete_preview(reg, appid)   # 미등록이면 GAME_NOT_REGISTERED
        # 시각 표기는 한 함수(`_saved_label`)를 지난다 — 같은 값이 화면마다 다른 모양으로
        # 보이지 않게.
        params["saved_at"] = {p: _saved_label(v) for p, v in (params.get("saved_at") or {}).items()}
        if not _consume(confirm_token, str(appid), _DELETE_SCOPE, fp, ring):
            # 여기서 아무것도 지우지 않는다. 토큰이 없든 위조든 만료든 사이에 상태가 바뀌었든
            #   전부 같은 자리다 — 화면이 할 일은 "다시 물어보기" 하나뿐이다.
            return _fail(codes.CONFIRM_REQUIRED,
                         confirm_token=_issue(str(appid), _DELETE_SCOPE, fp, ring),
                         **params)
        result = remove.delete_game_data(reg, appid)       # 대피 실패 시 BACKUP_FAILED
        # 삭제 = 등록 해제 + 감지 제외다. 삭제가 성공한 뒤에만 제외에 올린다 — 먼저 올리면
        #   삭제가 실패했을 때 "등록도 돼 있는데 감지에서도 숨은" 상태가 남는다.
        #   이름은 `result`에서 가져온다: 이 시점 이후로는 registry에 그 게임의 이름이 없다.
        exclude.add(reg, appid, result["name"])
        # 감사 로그는 `save_registry`보다 먼저. 뒤에 두면 저장이 실패해 예외가 나가는 순간
        #   파일은 이미 지워졌는데 로그가 한 줄도 없는 상태가 된다.
        decky.logger.info(
            "delete_game session=%s appid=%s name=%s evacuated=%s backups=%s excluded=True",
            SESSION, result["appid"], result["name"], result["evacuated"], result["backups"])
        # ★ 19판(§7-5′) — 프로필 데이터는 이미 지워졌다(delete_game_data 성공). 여기서 registry
        #   저장이 실패하면 봉투가 `UNEXPECTED`로 나가 "이미 지워졌다"를 아무도 말하지 않는다.
        #   `OSError`만 좁게 잡아 `DELETE_FAILED`의 **단일 생성점**(`remove._delete_failed`)을 지난다
        #   — 신설이 아니라 미도달 갈래를 도달시키는 것이고, `profile_delete_started=True`가
        #   기존 프론트 분기를 그대로 켠다. **`RegistryError`는 그대로 올린다**: `REGISTRY_NEWER`를
        #   `DELETE_FAILED`로 삼키면 U5 고지가 사라진다.
        try:
            _save_registry(reg)
        except OSError as exc:
            remove._delete_failed(
                str(appid), "save_registry",
                "거부: 프로필 데이터는 지웠으나 등록 정보 저장에 실패했습니다 — %s\n"
                "  다시 삭제하면 남은 것부터 이어서 완결합니다." % exc,
                profile_delete_started=True, cause=exc)
        return _ok(**result)

    @route
    def reset_all(self, confirm_token=None, confirm_text=None):
        """전체 초기화 = 게임별 삭제 + registry 공장초기화.

        게임별로 `remove.delete_game_data`를 지나며, 슬롯 본체는 먼저 백업한다. 백업 디렉터리를
        통째로 없애지는 않지만 포화 링에서는 오래된 백업이 축출될 수 있다.

        확인은 1회용 토큰과 입력 대조를 함께 쓴다. 토큰 지문은 registry·프로필 meta·축출 대상을
        묶는다. 게임별 실패는 격리하고, 실패한 게임의 registry 항목만 남긴다.

        `@mutating`을 두지 않아 더 새 버전의 registry도 초기화할 수 있다. 저장하는 것은 현재
        버전의 새 registry이므로 `_save_registry`의 버전 가드를 통과한다.

        ★ 19판 — registry를 읽지 못하거나(`load_registry`) 컨테이너 형태가 깨졌으면
        (`_reset_preflight`) **fresh 복구 갈래**(`_reset_fresh`)로 갈라진다: 게임을 한 개도
        순회하지 않고 손상 원문을 격리 디렉터리로 옮긴 뒤 공장초기 목록을 쓴다. 그 갈래의 토큰
        지문은 `reg["games"]` 순회가 불가능하므로 registry 파일의 관측 상태(sha1, 없으면 stat)에
        결박하고(`_reset_fresh_fingerprint`), 스코프도 정상 갈래(`_RESET_SCOPE`)와 별개다
        (`_RESET_FRESH_SCOPE`). 아래는 정상 갈래(`mode:"normal"`) 그대로다.
        """
        # 이 try가 답하는 질문은 「registry를 읽고 이해할 수 있나」 **하나**다. 넓히면 fresh 저장
        #   실패(격리 실패도 `RegistryError`다 — §7-4′ 6항)가 다시 fresh 확인 발급으로 먹혀
        #   사용자가 같은 확인창을 무한히 다시 본다. 구조적으로도 안전하다: `except` 절 안에서 난
        #   예외는 같은 `try`가 다시 잡지 않으므로 `_reset_fresh`가 올리는 것은 `@route`의 봉투로
        #   곧장 나간다.
        try:
            reg = store.load_registry()
            _reset_preflight(reg)
        except store.RegistryError as exc:
            return self._reset_fresh(exc, confirm_token, confirm_text)
        # 축출 예고와 그 지문은 한 번의 산출에서 같이 나온다(일괄 적용과 같은 문법).
        evict = remove.reset_evict_preview(reg)
        fp = "%s|evict=%s" % (remove.reset_fingerprint(reg), evict["fingerprint"])
        if not _consume(confirm_token, "*", _RESET_SCOPE, fp, confirm_text or ""):
            return _fail(codes.CONFIRM_REQUIRED,
                         # ★ 19판 — 판별자를 정상 갈래에도 싣는다. 안 실으면 프론트 switch가
                         #   default(fail-closed)로 떨어져 정상 확인창이 아예 안 뜬다(§7-4′ 3항).
                         mode="normal",
                         confirm_token=_issue("*", _RESET_SCOPE, fp, _RESET_CHALLENGE),
                         games=len(reg["games"]),
                         profiles=_profile_total(reg),
                         # 표시명은 registry settings에 살아서 이 초기화에 같이 지워진다.
                         #   모르고 잃으면 안 되므로 확인창이 미리 말한다
                         #   (0이면 화면이 그 줄을 안 그린다 — 기존 문법).
                         named=labels.custom_count(reg),
                         # 초기화는 registry를 통째로 갈아 끼우므로 감지 제외 목록도 같이
                         #   지워진다(지우는 코드가 따로 없다). 모르고 잃으면 안 되므로
                         #   확인창이 미리 말한다(0이면 화면이 그 줄을 안 그린다 — 기존 문법).
                         excluded=len(exclude.excluded_map(reg)),
                         # 축출 고지는 수만 싣는다(일괄 적용과 같은 판단·같은 필드). 초기화는
                         #   게임마다 슬롯 본체를 대피시키므로 링이 찬 게임에서는 그만큼
                         #   오래된 백업이 사라진다. 산출은 개별 해제 예고와 같은 함수다.
                         #   지문은 싣지 않는다 — 토큰의 재료다.
                         evicted=evict["evicted"], evict_games=evict["evict_games"],
                         challenge=_RESET_CHALLENGE)

        # 「지운 것」의 수는 파괴 전에 센다. 아래에서 `default_registry()`가 settings를 통째로
        #   갈아 끼우고 되심는 것은 `games`뿐이므로, 지금 registry에 있는 표시명·감지 제외
        #   항목은 게임별 성패와 무관하게 전부 사라진다. 즉 이 두 수는 「지우려 했던 것」이
        #   아니라 지운 것이다.
        # 세는 함수는 위 확인창 params와 같은 것이다 — 두 곳에서 다르게 세면 언젠가 갈린다.
        #   다만 시점이 다르다: 저기는 토큰 발급 시점, 여기는 실행 시점이다. 그래서 화면도
        #   확인창의 수를 완료 문구에 재사용하지 않고 이 봉투의 값을 쓴다.
        # `counts.deleted`는 게임만 센다. 그것 하나로 완료 문구를 만들면 등록 0 · 제외 N인
        #   상태에서 화면이 "0개 삭제"라고 말하는 사이 제외 N건과 표시 이름이 조용히 사라진다.
        cleared = {"named": labels.custom_count(reg),
                   "excluded": len(exclude.excluded_map(reg))}

        results = []
        for appid in sorted(reg["games"]):                 # sorted가 사본이라 순회 중 pop해도 안전
            entry = reg["games"].get(appid)
            # row 조립은 게임별 try 밖이다 — 비-dict 항목에서 `entry.get`이 여기서 죽으면 루프가
            #   무너지므로 이름만 안전하게 접는다(§8-D · §14-H ⓘ). 손상 항목의 삭제 자체는
            #   아래 `delete_game_data`(require_intact=False)가 우회로 처리한다.
            name = entry.get("name") if isinstance(entry, dict) else None
            row = {"appid": appid, "name": name or appid,
                   "outcome": "deleted", "code": None, "note": ""}
            results.append(row)
            try:
                remove.delete_game_data(reg, appid)
            except (engine.Refused, store.RegistryError) as exc:
                row.update(outcome="refused", code=exc.code, note=str(exc).splitlines()[0])
            except Exception as exc:            # noqa: BLE001 — 초기화도 같은 불변식이다
                # 넓게 잡는 이유는 `register_confident`·`apply_all`과 같다: 이 루프의 존재
                # 이유가 "하나가 실패해도 나머지는 계속"이고, 그 약속이 예외 종류에 따라
                # 깨지면 안 된다.
                row.update(outcome="error", code=codes.UNEXPECTED,
                           note="%s: %s" % (type(exc).__name__, exc))
        counts = {}
        for row in results:
            counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1

        # registry는 통째로 공장초기화하되(settings·gpu_map 포함), 실패한 게임의 항목은
        #   되살려 심는다 — 지워지지 않은 프로필이 registry에서만 사라지면 "미등록인데
        #   profiles/가 남은" 유령 상태가 된다.
        #   `delete_game_data`가 성공분만 pop했으므로 지금 `reg["games"]`가 곧 실패분이다.
        fresh = store.default_registry()
        # E59(§14-H ⓘ): 되심기에서 비-숫자 appid 키를 제외한다 — 그 키는 개별 삭제(appid 숫자
        #   검증 거부)로도 초기화(되심기)로도 청소할 수 없어 영구히 남던 항목이다. 숫자 키의
        #   실패분만 되살려 심는다. `add_game`은 비-숫자 키를 만들지 않으므로 정상 데이터는
        #   영향이 없다.
        fresh["games"] = {k: v for k, v in reg["games"].items() if str(k).isdigit()}
        # 감사 로그는 `save_registry`보다 먼저 — 전 게임 outcome을 남긴다.
        #   문제 행만 사유를 싣는다(정상은 code가 없어 자동으로 빠진다).
        problems = {r["appid"]: {"code": r["code"], "note": r["note"][:200]}
                    for r in results if r["outcome"] != "deleted"}
        decky.logger.info(
            "reset_all session=%s counts=%s outcomes=%s problems=%s",
            SESSION, counts, {r["appid"]: r["outcome"] for r in results}, problems)
        # ★ 19판(§7-5′) — 게임을 지운 뒤 마지막 저장이 실패하면 봉투가 `UNEXPECTED`로 나가
        #   "이미 지워졌다"를 아무도 말하지 않는다. `OSError`만 좁게 잡아 신설 `RESET_FAILED`로
        #   접는다(문구는 조건부 — 지워진 양이 0~전부라 단정형 금지, 재시도가 실패분부터 이어
        #   지운다). 치환자가 없어 프론트 분기 없이 `tCode`만으로 뜬다.
        #   ⚠️ 이 갈래는 **정상(mode:"normal")** 저장 실패에만 성립한다 — fresh 복구 갈래는
        #   `_reset_fresh`가 `store.save_fresh_registry`로 따로 처리하고 거기서는 `RESET_FAILED`가
        #   나가지 않는다(그 갈래는 게임을 하나도 안 지운다 — §7-4′ 6-1). `RegistryError`는 그대로 올린다.
        try:
            _save_registry(fresh)
        except OSError as exc:
            return _fail(codes.RESET_FAILED, message=str(exc))
        return _ok(mode="normal", results=results, counts=counts, cleared=cleared)

    def _reset_fresh(self, exc, confirm_token, confirm_text):
        """손상 registry의 탈출 갈래. 게임을 하나도 순회하지 않는다 — 열거할 수 없는 상태가 전제다.

        확인 params·성공 봉투 둘 다 `mode:"fresh"`를 싣고 수는 싣지 않는다(셀 수 없다 — 못 세는
        수를 0으로 그리면 화면이 거짓을 말한다). 코드는 `CONFIRM_REQUIRED` 그대로다(신설 백엔드
        코드 0). 격리·저장은 `store.save_fresh_registry`가 하고, 그 실패(`RegistryError`)는 이
        메서드가 잡지 않고 `@route` 봉투로 곧장 올린다(§7-4′ 5항).
        """
        fp = _reset_fresh_fingerprint(exc.code)
        if not _consume(confirm_token, "*", _RESET_FRESH_SCOPE, fp, confirm_text or ""):
            return _fail(codes.CONFIRM_REQUIRED,
                         mode="fresh",
                         confirm_token=_issue("*", _RESET_FRESH_SCOPE, fp, _RESET_CHALLENGE),
                         challenge=_RESET_CHALLENGE)
        # 감사 로그는 쓰기보다 먼저(기존 관례). 격리 경로는 성공 뒤에 한 줄 더 남긴다.
        decky.logger.info("reset_all fresh session=%s cause=%s", SESSION, exc.code)
        quarantined = store.save_fresh_registry()        # 실패는 RegistryError로 그대로 올린다
        decky.logger.info("reset_all fresh done session=%s quarantined=%s", SESSION, quarantined)
        return _ok(mode="fresh", results=[], counts={}, cleared={"named": 0, "excluded": 0})

    # ── 표시명 ───────────────────────────────────────────────────────────────
    @route
    @mutating
    def set_profile_name(self, profile, name=None):
        """프로필의 전역 표시명을 바꾼다. 화면 글자만 바뀐다.

        식별자는 건드리지 않는다. `dock`/`internal`은 경로 조각(`profiles/<appid>/dock/`)이자
        RPC 인자이자 registry 키다. 여기서 저장하는 것은 `settings.profile_names`의 문자열
        하나뿐이고, 저장된 프로필·백업·로그·테스트가 무는 문자열은 하나도 움직이지 않는다
        (`_VALIDATORS["profile"]`가 여전히 {dock, internal}만 통과시킨다).

        빈 값·공백만 입력은 거부가 아니라 기본값 복귀다(`labels.normalize`). 거부로 만들면
        "이름 지우기"를 할 방법이 사라지고, 화면에는 쓸데없는 오류 분기가 생긴다.
        상한 초과는 잘라서 저장하고 결과를 돌려준다 — 화면이 그 값을 그대로 그리므로
        사용자가 본 것과 저장된 것이 갈리지 않는다.
        """
        reg = store.load_registry()
        names = labels.set_name(reg, profile, name)
        # 감사 로그는 `save_registry`보다 먼저.
        decky.logger.info("set_profile_name session=%s profile=%s name=%r",
                          SESSION, profile, names.get(str(profile), ""))
        _save_registry(reg)
        return _ok(profile_names=names)

    # ── 백업 복원 ────────────────────────────────────────────────────────────
    @route
    def list_backups(self, appid):
        """그 게임의 백업 목록. 읽기 전용 — 아무것도 쓰지 않는다.

        파일명 파싱·정렬은 전부 백엔드가 한다(`restore.backup_rows`). 프론트가 문자열을 쪼개면
        판정이 두 곳으로 갈리고, 그 순간 화면이 실제와 다른 것을 말한다.
        """
        reg = store.load_registry()
        # 조회 계열(§8-D · §14-H ⓘ): 반환 entry를 쓰지 않으므로 검증만 끄면 된다(접기 불요).
        #   손상 항목에서도 백업 목록이 뜬다 — 그 항목의 백업 파일은 멀쩡히 남아 있다.
        engine.game_or_fail(reg, appid, require_intact=False)   # 미등록 → GAME_NOT_REGISTERED
        return _ok(backups=restore.backup_rows(reg, appid))

    @route
    @mutating
    def restore_backup(self, appid, backup_id, confirm_token=None):
        """백업 하나를 그 행의 되돌릴 곳으로 되돌린다.

        목적지는 행의 종류가 정한다 — `profile_*` 백업은 그 프로필 슬롯으로, `disk`·`unknown`은
        게임 설정 파일로. 전부 게임 설정 파일로 보내면 "프로필을 덮어쓰기 직전에 대피시킨 사본"을
        되돌려도 정작 그 프로필은 그대로다. 판정은 백엔드 한 곳(`restore.target_of`)이고 화면은
        그 값을 그린다.

        판정은 3-상태다(`restore.needs_confirm`), 기준은 되돌릴 곳이다:
        `already`는 엔진을 부르기 전에 돌려준다 — 엔진에는 already 스킵이 없어서 낙하시키면 같은
        백업을 다시 누를 때마다 대피본이 쌓여 백업 링이 밀린다.
        `proceed`(빈 자리)는 잃을 것이 없어 묻지 않는다. `confirm`만 토큰을 요구한다.

        토큰은 (목적지, 백업 파일 id, 목적지 지문, 백업 지문) 전부에 묶인다. 목적지·백업 id를
        안 묶으면 두 슬롯 내용이 같고 두 대피본 내용도 같을 때, dock 확인창에서 받은 토큰으로
        internal 슬롯을 덮어쓸 수 있다. 지문 쪽은 확인창 사이의 변경을 잡는다.
        """
        reg = store.load_registry()
        # 실행 중 게임·경로 봉쇄·미등록은 여기서 `Refused`로 나간다(route 데코레이터가 봉투에 싣는다).
        # 판정 함수가 params와 지문을 함께 돌려준다(적용·저장·삭제와 같은 문법). 여기서
        #   `restore.fingerprint`를 따로 부르면 되돌릴 곳의 본체·백업 파일·링을 다시 읽게 되고,
        #   그 두 관측 사이의 변화가 토큰에 구워진다.
        state, params, fp = restore.needs_confirm(reg, appid, backup_id)
        target = params["target"]
        # 표시 문자열 변환은 백엔드 한 곳이다(`_saved_label` — `_slot_view`의 saved_at과 같은 함수).
        if "saved_at" in params:
            params["saved_at"] = _saved_label(params["saved_at"])
        if state == "already":
            # 엔진을 부르지 않으므로 쓰기 0 · 대피 0 · 링 소모 0.
            return _ok(outcome="already", **params)
        if state == "confirm":
            fp_target, fp_backup = fp
            scope = _restore_scope(target, backup_id)
            if not _consume(confirm_token, str(appid), scope, fp_target, fp_backup):
                # 여기서 파일을 건드리지 않는다. 없든 위조든 만료든 목적지가 다르든 상태가
                #   바뀌었든 전부 같은 자리다 — 화면이 할 일은 "다시 물어보기" 하나뿐이다.
                return _fail(codes.CONFIRM_REQUIRED,
                             confirm_token=_issue(str(appid), scope, fp_target, fp_backup),
                             **params)
        # 여기서부터는 쓴 뒤일 수 있다 — 적용 route와 같은 문법으로 감싼다.
        #   `engine.restore_backup`은 대피본을 만들고 슬롯·설정 파일을 이미 바꾼 다음이라,
        #   그 뒤의 `save_registry`가 죽어도 디스크는 되돌아가지 않는다. 감싸지 않으면 이 갈래가
        #   데코레이터의 익명 `UNEXPECTED`로 접혀 ⓐ 어느 route에서 무엇을 하다 죽었는지가 전문
        #   로그에 남지 않고 ⓑ 봉투가 "복원을 마치지 못했다"(부분 완료를 인정하는 말)를 실을
        #   자리도 없다.
        try:
            result = engine.restore_backup(
                reg, appid, os.path.join(store.backups_dir(appid), str(backup_id)), target)
            # 감사 로그는 `save_registry`보다 먼저. 뒤에 두면 저장이 실패해 예외가 나가는 순간
            #   파일은 이미 바뀌었는데 로그가 한 줄도 없는 상태가 된다.
            decky.logger.info(
                "restore_backup session=%s appid=%s backup=%s kind=%s target=%s state=%s",
                SESSION, appid, backup_id, params["kind"], target, state)
            _save_registry(reg)
        except engine.Refused:
            raise                       # route 데코레이터가 code·params를 그대로 실패 봉투에 싣는다
        except Exception as exc:        # noqa: BLE001 — 파일·슬롯이 이미 바뀐 뒤일 수 있는 실패
            # 전문 로그는 여기서 남긴다(데코레이터의 UNEXPECTED 경로는 사유를 못 싣는다).
            # 로그 접두는 데코레이터와 같은 `unexpected`다 — 진단은 접두로 grep한다.
            decky.logger.error("unexpected session=%s route=restore_backup appid=%s backup=%s\n%s",
                               SESSION, appid, backup_id, traceback.format_exc())
            raise engine.Refused("거부: 예기치 못한 오류로 복원을 마치지 못했습니다.",
                                 code=codes.UNEXPECTED) from exc
        return _ok(outcome="restored", **params, **result)

    # ── 생명주기 ─────────────────────────────────────────────────────────────
    async def _main(self):
        language, source = lang.detect()
        decky.logger.info(
            "backend up session=%s phase=P1 lang=%s lang_source=%s data_dir=%s",
            SESSION, language, source, store.data_dir(),
        )

    async def _unload(self):
        decky.logger.info("backend down session=%s", SESSION)

    async def _uninstall(self):
        # runtime data는 지우지 않는다 — 여기서 지우면 재설치로도 되돌릴 길이 없다.
        decky.logger.info("uninstall session=%s (runtime data left intact)", SESSION)

    async def _migration(self):
        # 의도적으로 비워 둔다 — decky.migrate_* 호출 금지(파일 머리 독스트링 참조).
        # 이 금지는 build.sh 불변식 검사 ②의 AST 게이트가 강제한다.
        pass
