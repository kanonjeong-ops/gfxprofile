#!/usr/bin/env python3
"""P6 접착층 route 3개(`discover_games`·`register_confident`·`add_game`)의 계약을 잠근다.

★★ 측정 기준 (2026-08-07 재게이트에서 **표면 → 효과**로 옮겼다):
   T1은 호출 이름을, T3는 고정 표본 9개를, T5는 대표 예외 하나를 봤다. 셋 다 더 정교한
   변이(별칭 쓰기 / 표본 밖 문자열 정책 / 한 종만 재던지기)에 뚫렸다. **검사를 한 겹 더 쌓는
   대신 무엇을 재는지를 바꿨다** — 자세한 근거와 잔여 표면은 각 절 머리 주석에 있다.
     T1  이름 매칭      → **합성 세계 스냅샷 대조 + 쓰기 원시함수 가로채기**
     T3  고정 표본      → **랜덤 퍼징(매 실행 새 시드) + 모듈 전체 소스 리터럴 수확**
     T5  대표 예외 1종  → **런타임 전수 주입**(`Exception.__subclasses__()` 재귀)
   3회차에서 T3의 수확 범위(함수 본문 → 모듈 전체)와 T5의 표본(유한 행렬 8종 → 전수)을
   다시 넓혔다 — 둘 다 *"경계를 어디에 그었나"*가 우회 지점이었고, 경계 자체를 없앴다.

잠그는 것:
    T1 **`discover`는 아무것도 쓰지 않는다** — 탐지 route를 눌러서 데이터가 바뀌는 일은 없다
    T2 **일괄 등록 route는 appid 목록을 받지 않는다**(D20) — `_validate`가 리스트 원소를 못 보므로,
       목록을 받는 순간 경로 조각 주입이 되살아난다. **인자를 없애 그 상황 자체를 없앴다**
    T3 **경로 인자는 접착층이 검증하지 않는다** — 가드는 엔진 G11/G14 하나뿐이다.
       `_VALIDATORS`에 `config_path`가 들어가면 이중 판정이 되고 실패 code가 엉뚱해진다
    T4 **`warnings`는 `add_game` 성공 뒤에만 조회한다** — 순서를 어기면 거짓 경고가 난다(D20)
    T5 **하나가 실패해도 나머지는 계속**하고 봉투는 `ok:true`다(`apply_all`과 같은 불변식)
    T6 **`save_registry`는 루프 밖 1회**이고 **감사 로그가 그보다 먼저** 나간다(QA R4)

★ 반증(§B): 위 단언들이 **깨진 구현에서 실제로 FAIL하는지** 대조군으로 확인한다.
   "이 단언이 FAIL이 되는 입력이 존재하는가"에 답하지 못하는 검사는 거짓 검사다.

⚠️ 실데이터를 쓰지 않는다 — 데이터 루트를 임시 폴더로 격리하고 탐지 결과는 합성한다.
"""
import ast
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import pwd
import random
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
GFXP = ROOT / "py_modules" / "gfxp"

#: 경로 퍼저의 시드 — **매 실행 새로 뽑고 출력한다.** 고정 시드면 표본이 고정되고,
#: 고정 표본은 그것만 피하는 정책에 다시 뚫린다(그게 이번 반려 사유였다).
#: 실패를 재현하려면 출력된 시드를 `GFXP_FUZZ_SEED`로 넣으면 된다.
FUZZ_SEED = int(os.environ.get("GFXP_FUZZ_SEED") or random.SystemRandom().randrange(2 ** 32))

_TMP = tempfile.mkdtemp(prefix="gfxp-p6routes-")
os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = _TMP          # main.py가 이걸로 데이터를 격리한다
os.environ["DECKY_PLUGIN_DIR"] = str(ROOT)

#: decky 스텁 — 로그를 삼키지 않고 **순서까지** 붙잡는다(T6이 그 순서를 잰다).
LOG = []
_decky = types.ModuleType("decky")


class _Logger:
    def _add(self, level, msg, *args):
        LOG.append(("log", level, (msg % args) if args else msg))

    def info(self, msg, *a):
        self._add("info", msg, *a)

    def warning(self, msg, *a):
        self._add("warning", msg, *a)

    def error(self, msg, *a):
        self._add("error", msg, *a)


_decky.logger = _Logger()
sys.modules["decky"] = _decky
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "py_modules"))

import main  # noqa: E402


def call(fn, *args, owner=None, **kwargs):
    """`owner`를 주면 그 모듈의 `Plugin`으로 부른다 — §B의 **main.py 변이 사본**이 쓴다."""
    return asyncio.run(fn((owner or main.Plugin)(), *args, **kwargs))


def load_mutant_main(replacements, tag):
    """`main.py`의 **실물 사본**에 변이를 주입해 별도 모듈로 올린다.

    ★ 왜 필요한가 (2026-08-07 QA R3): 대조군을 손으로 흉내 내면 **자기 판정**이 된다.
      예전 B2는 `KeyboardInterrupt`(route가 원래 안 잡는 예외)로 "중단됨"을 확인했는데,
      그건 *"일반 예외 격리가 사라진 구현"*을 재현하지 않아 T5의 회귀 잠금 근거가 못 됐다.
      여기서는 **진짜 소스의 그 줄**을 고친 사본을 올려 돌린다.

    앵커가 정확히 1개가 아니면 예외를 던진다 — **주입되지 않은 채로 "못 잡았다"고 말하는 것이
    가장 나쁜 실패**다(변이가 안 붙었는데 대조군이 성립했다고 착각한다).
    `gfxp` 모듈은 `sys.modules`를 공유하므로 `Patch`가 이 사본에도 그대로 걸린다.
    """
    src = (ROOT / "main.py").read_text()
    applied = []
    for old, new in replacements:
        if src.count(old) != 1:
            raise AssertionError("변이 앵커가 %d개다(1개여야 한다): %r" % (src.count(old), old))
        src = src.replace(old, new)
        applied.append((old.strip().splitlines()[0], new.strip().splitlines()[0]))
    path = pathlib.Path(_TMP) / ("main_%s.py" % tag)
    path.write_text(src)
    spec = importlib.util.spec_from_file_location("main_%s" % tag, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, applied


# ── 합성 탐지 결과 ───────────────────────────────────────────────────────────
def synth(n=4, prefix="/synth"):
    out = []
    for i in range(n):
        appid = str(500000 + i)
        confident = i != 1                      # 1번은 애매한 게임
        cands = [{"path": f"{prefix}/{appid}/c{c}.ini", "tier": 1 if confident else 3,
                  "reason": "x", "size": 10 + c, "mtime": 1.0 * (i + c)}
                 for c in range(1 if confident else 3)]
        out.append({"appid": appid, "name": f"Game {i}", "library": prefix,
                    "candidates": cands, "confident": confident, "registered": False})
    return out


class Patch:
    """탐지·등록을 합성으로 갈아끼운다. **원복을 보장한다**(다음 검사가 오염되지 않게)."""

    def __init__(self, entries=None, add_game=None):
        self.entries = entries
        self.add_game = add_game
        self.saved = {}

    def __enter__(self):
        self.saved["discover"] = main.discover.discover
        self.saved["add_game"] = main.engine.add_game
        self.saved["warnings"] = main.engine.config_candidate_warnings
        self.saved["save"] = main.store.save_registry
        if self.entries is not None:
            main.discover.discover = lambda known_appids=(): [
                dict(e, registered=e["appid"] in known_appids) for e in self.entries]
        if self.add_game is not None:
            main.engine.add_game = self.add_game
        self.warn_calls = []
        self.save_calls = []
        real_warn = self.saved["warnings"]
        main.engine.config_candidate_warnings = lambda a, p: (
            self.warn_calls.append((a, p)) or LOG.append(("warnings", a, p)) or [])
        main.store.save_registry = lambda reg: (
            self.save_calls.append(json.loads(json.dumps(reg))) or LOG.append(("save", "", "")))
        self.real_warn = real_warn
        return self

    def __exit__(self, *exc):
        main.discover.discover = self.saved["discover"]
        main.engine.add_game = self.saved["add_game"]
        main.engine.config_candidate_warnings = self.saved["warnings"]
        main.store.save_registry = self.saved["save"]
        return False


# ── T1. discover 순수성 — **효과로 잰다** ────────────────────────────────────
#
# ★★ 2026-08-07 재게이트 R3: 예전 판정은 **호출 이름 매칭**(`_write_calls`)이었다. 그래서
#    `qa_writer = Path(...).open` 처럼 **별칭에 담아 부르면** 이름이 `qa_writer`라 놓쳤다
#    (Codex가 실제로 그렇게 뚫었다). 이름을 더 모으는 방식은 다음 별칭에 또 뚫린다 —
#    `getattr`·`operator.methodcaller`·`exec`·subprocess까지 가면 열거가 원리적으로 끝나지 않는다.
#
#    → **무엇으로 썼는지를 묻지 않고, 쓰였는지를 본다.** 측정을 문법에서 효과로 옮긴다:
#      ① 합성 세계(임시 폴더)의 파일 목록 + 내용 해시를 실행 전후로 떠서 대조한다.
#         별칭이든 `os.write`든 subprocess든 **그 안에 쓰면 반드시 잡힌다.**
#      ② 세계 **밖**으로 쓰는 것은 스냅샷으로 못 본다. 그래서 쓰기 원시함수를 실행 동안
#         가로채(intercept) 호출을 기록한다. 별칭은 **패치된 뒤에** 만들어지므로 같이 잡힌다.
#
# ⚠️ 정직한 잔여 표면(닫히지 않은 것):
#    - 우리가 감싸기 **전에** 모듈 최상위에서 만들어 둔 별칭(`_o = open` at import)으로
#      합성 세계 **밖**에 쓰는 경우 — ②를 우회한다(①의 범위 밖이라 ①도 못 본다)
#    - `ctypes`로 syscall 직접 호출, `mmap` 쓰기 — 감싼 API를 안 거친다
#    - 합성 세계 밖 경로에 subprocess로 쓰는 경우
#    이 셋은 "잴 수 없다"고 적는다. **못 재는 것을 통과로 세지 않기 위해서다.**

#: 실행 동안 감싸는 쓰기 원시함수. 이름 목록이지만 **판정 기준이 아니라 계측 지점**이다 —
#: 여기 없는 이름으로 불러도 결국 이 함수들을 거치면 잡힌다(별칭·getattr 포함).
def _install_write_probe(record):
    """쓰기 원시함수를 감싸고 `(원복 함수)`를 돌려준다. **읽기는 그대로 통과시킨다.**"""
    import builtins
    import io
    import shutil
    import subprocess

    undo = []

    def wrap(owner, name, is_write):
        original = getattr(owner, name)

        def wrapper(*args, **kwargs):
            if is_write(args, kwargs):
                record.append("%s.%s(%s)" % (getattr(owner, "__name__", owner), name,
                                             ", ".join(repr(a)[:60] for a in args[:2])))
            return original(*args, **kwargs)

        setattr(owner, name, wrapper)
        undo.append(lambda: setattr(owner, name, original))

    def mode_of(args, kwargs, index):
        mode = kwargs.get("mode")
        if mode is None and len(args) > index:
            mode = args[index]
        return str(mode if mode is not None else "r")

    always = lambda *_a, **_k: True                                     # noqa: E731
    wrap(builtins, "open", lambda a, k: any(c in mode_of(a, k, 1) for c in "wax+"))
    wrap(io, "open", lambda a, k: any(c in mode_of(a, k, 1) for c in "wax+"))
    wrap(pathlib.Path, "open", lambda a, k: any(c in mode_of(a, k, 1) for c in "wax+"))
    for name in ("write_text", "write_bytes", "touch", "mkdir", "rename", "replace",
                 "unlink", "rmdir", "symlink_to", "hardlink_to", "chmod"):
        if hasattr(pathlib.Path, name):
            wrap(pathlib.Path, name, always)
    for name in ("write", "open", "remove", "unlink", "rename", "replace", "mkdir",
                 "makedirs", "rmdir", "removedirs", "truncate", "symlink", "link",
                 "chmod", "utime", "pwrite"):
        if hasattr(os, name):
            # `os.open`은 flags를 받는다 — 읽기 전용(O_RDONLY=0)만 통과시킨다.
            check = (lambda a, k: bool((k.get("flags", a[1] if len(a) > 1 else 0)) & 0o3)) \
                if name == "open" else always
            wrap(os, name, check)
    for name in ("copy", "copy2", "copyfile", "copytree", "move", "rmtree"):
        if hasattr(shutil, name):
            wrap(shutil, name, always)
    for name in ("run", "call", "check_call", "check_output", "Popen"):
        if hasattr(subprocess, name):
            wrap(subprocess, name, always)     # 무엇을 시키는지 모른다 — 부르는 것 자체가 위반이다

    def restore():
        for fn in reversed(undo):
            fn()
    return restore


def _snapshot(root):
    """합성 세계의 **상태 전량**. 경로 → (크기, 내용 sha1). 디렉터리 자체도 항목으로 센다."""
    state = {}
    for current, dirs, files in os.walk(root):
        for name in dirs:
            state[os.path.join(current, name) + os.sep] = ("dir", "")
        for name in files:
            path = os.path.join(current, name)
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError as exc:
                state[path] = ("unreadable", str(exc))
                continue
            state[path] = (len(data), hashlib.sha1(data).hexdigest())
    return state


def _build_world(root):
    """`discover`가 실제로 훑는 모양의 합성 라이브러리. **읽을 것이 있어야 측정이 공허하지 않다.**"""
    library = root / "library"
    for i, appid in enumerate(("500100", "500101", "500102")):
        prefix = library / "steamapps" / "compatdata" / appid / "pfx"
        config = prefix / "drive_c" / "users" / "steamuser" / "AppData" / "Local" / f"G{i}" \
            / "Saved" / "Config" / "WindowsNoEditor"
        config.mkdir(parents=True)
        (config / "GameUserSettings.ini").write_text("[Scalability]\nsg.Res=%d\n" % i)
        (config / "Engine.ini").write_text("boilerplate\n")          # 제외 대상 — 걸러져야 한다
        docs = prefix / "drive_c" / "users" / "steamuser" / "Documents" / f"G{i}"
        docs.mkdir(parents=True)
        (docs / "video.ini").write_text("res=1\n")
        manifest = library / "steamapps" / f"appmanifest_{appid}.acf"
        manifest.write_text('"AppState"\n{\n\t"name"\t\t"Synth Game %d"\n}\n' % i)
    return library


def load_mutant_discover(replacements, tag):
    """`discover.py`의 **실물 사본**에 변이를 주입해 별도 패키지로 올린다.

    `from . import engine`가 있어서 패키지 문맥이 필요하다 — 임시 패키지를 만들고 그 안의
    `engine`을 **진짜 `gfxp.engine`으로 미리 묶어** 준다(엔진은 손대지 않는다).
    """
    src = (GFXP / "discover.py").read_text()
    applied = []
    for old, new in replacements:
        if src.count(old) != 1:
            raise AssertionError("변이 앵커가 %d개다(1개여야 한다): %r" % (src.count(old), old))
        src = src.replace(old, new)
        applied.append(new.strip().splitlines()[0])
    name = "gfxpmut_%s" % tag
    pkg = pathlib.Path(_TMP) / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "discover.py").write_text(src)
    if str(_TMP) not in sys.path:
        sys.path.insert(0, str(_TMP))
    package = importlib.import_module(name)
    package.engine = main.engine                      # `from . import engine`가 이걸 집는다
    sys.modules[name + ".engine"] = main.engine
    return importlib.import_module(name + ".discover"), applied


def t1_discover_pure(module=None):
    """`discover()`를 합성 세계에서 **실제로 돌리고** 세계가 변했는지 본다.

    `module`을 주면 그 사본을 돌린다 — §B의 변이 대조군이 쓴다.
    """
    module = module or main.discover
    bad = []
    root = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-t1-world-", dir=_TMP))
    library = _build_world(root)

    real_libraries = main.engine.steam_libraries
    main.engine.steam_libraries = lambda: [str(library)]
    writes = []
    before = _snapshot(root)
    restore = _install_write_probe(writes)
    try:
        results = module.discover(known_appids=set())
    finally:
        restore()
        main.engine.steam_libraries = real_libraries
    after = _snapshot(root)

    # ★ 측정이 대상에 닿았는가 — 아무것도 못 읽었으면 "안 썼다"는 공허한 참이다.
    if len(results) != 3:
        bad.append(f"합성 세계에서 게임 {len(results)}개를 봤다(3개여야 한다) — 검사가 대상에 닿지 못했다")
    elif not all(e["candidates"] for e in results):
        bad.append("후보를 하나도 못 찾았다 — 검사가 대상에 닿지 못했다")

    # ① 효과: 세계가 1바이트라도 변했는가
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    for label, items in (("생성", added), ("삭제", removed), ("변경", changed)):
        for item in items[:5]:
            bad.append(f"discover가 합성 세계를 {label}했다: {item} ★순수 탐색이 아니다")

    # ② 가로채기: 세계 밖으로 쓰는 것도 본다(별칭이든 무엇이든 원시함수는 거친다)
    for call in writes[:5]:
        bad.append(f"discover가 쓰기 원시함수를 호출했다: {call} ★순수 탐색이 아니다")

    return bad, len(before), len(writes)


# ── T2. 인자 없음 (AST + 동작) ───────────────────────────────────────────────
def route_params(name):
    """`main.py`에서 그 route의 파라미터 이름 목록. 데코레이터가 시그니처를 지워서
    `inspect`로는 못 본다 — 소스에서 직접 읽는다."""
    tree = ast.parse((ROOT / "main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return [a.arg for a in node.args.args]
    return None


def t2_no_appid_list():
    bad = []
    for name in ("discover_games", "register_confident"):
        params = route_params(name)
        if params is None:
            bad.append(f"{name} route를 main.py에서 찾지 못했다 — 검사가 대상에 닿지 못했다")
        elif params != ["self"]:
            bad.append(f"{name}이 인자를 받는다: {params} ★D20 위반 — "
                       "리스트 원소는 _validate를 통과하지 않는다(경로 조각 주입 부활)")
    # 동작으로도 확인한다: 목록을 보내면 **아무것도 등록되지 않는다**
    with Patch(entries=synth()) as p:
        env = call(main.Plugin.register_confident, ["../../etc"])
        if env.get("ok"):
            bad.append("register_confident가 appid 목록을 받아 성공했다 ★D20 위반")
        if p.save_calls:
            bad.append("appid 목록을 보냈는데 registry가 저장됐다 ★D20 위반")
    return bad


# ── T3. 경로 인자를 접착층이 검증하지 않는다 ─────────────────────────────────
def t3_path_not_validated():
    bad = []
    if "config_path" in main._VALIDATORS:
        bad.append("_VALIDATORS에 config_path가 있다 — 엔진과 이중 판정이 되고 "
                   "실패가 BAD_IDENTIFIER라는 엉뚱한 code로 나간다 ★설계 §3-A 위반")
    if "appid" not in main._VALIDATORS:
        bad.append("_VALIDATORS에 appid가 없다 — 경로 조각이 되는 값이 무검증이다")
    # appid는 걸리고(BAD_IDENTIFIER), 경로는 엔진 code로 거부되어야 한다
    env = call(main.Plugin.add_game, "../../etc", "/etc/passwd")
    if env.get("code") != "BAD_IDENTIFIER":
        bad.append(f"잘못된 appid가 BAD_IDENTIFIER로 안 걸린다 — {env}")
    env = call(main.Plugin.add_game, "999999", "/etc/passwd")
    if env.get("ok") or env.get("code") not in ("PATH_OUTSIDE_PREFIX", "PATH_OUTSIDE_HOME"):
        bad.append(f"홈·prefix 밖 경로가 엔진 code로 거부되지 않는다 — {env}")
    # ⚠️ G11이 G14보다 먼저 돈다 — 홈 밖 경로면 `.sav`에 닿기도 전에 걸린다.
    #   G14를 실제로 재려면 **홈 안**의 경로여야 한다(`$HOME`이 아니라 pwd로 구한다).
    home = pwd.getpwuid(os.getuid()).pw_dir
    env = call(main.Plugin.add_game, "999999", os.path.join(home, "x/pfx/y/SaveGames/a.sav"))
    if env.get("code") != "SAV_REFUSED":
        bad.append(f".sav가 G14로 거부되지 않는다 — {env}")
    bad += t3b_route_adds_no_path_policy(main, seed=FUZZ_SEED)
    return bad


# ── T3b. route의 독자 경로 정책 — **구조화 랜덤 퍼징 + 소스 리터럴 수확** ────
#
# ★★ 2026-08-07 재게이트 R3: 예전 판정은 **고정 표본 9개**(`_ODD_PATHS`)였다. Codex가
#    `endswith(".qa_policy")` 정책을 넣자 표본에 그 문자열이 없어 그대로 통과했다.
#    표본을 늘리는 방식은 원리적으로 끝나지 않는다 — 정책이 노리는 문자열은 무한하다.
#
#    → 두 축으로 옮긴다.
#      ① **랜덤 퍼징**: 매 실행 새 시드(출력한다)로 경로를 N≥200개 생성한다. 깊이·길이·
#         확장자·문자 계열(공백·탭·유니코드·제어문자·점)을 조합해 *모양의 공간*을 훑는다.
#      ② **소스 리터럴 수확**: route가 경로를 두고 하는 판단은 결국 **그 소스에 쓰인 문자열**로
#         표현된다. `add_game` 본문의 문자열 상수를 전부 뽑아 접미·중간 세그먼트로 심는다.
#         `.qa_policy` 같은 특정 문자열 정책은 **열거가 아니라 구성으로** 걸린다.
#
# ⚠️ 정직한 잔여 표면: 소스 리터럴로 표현되지 않고 퍼저의 모양 공간에도 안 걸리는 정책
#    (예: `len(path) > 4096`, 해시 기반 판정, 정규식 문자 클래스 조합). 길이·깊이는 넓게
#    흔들지만 **전수가 아니다.** 이 한계는 닫지 못했다고 적는다.

_FUZZ_N = 240
_SEGMENT_ALPHABETS = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "  \t",                                   # 공백·탭
    "가나다라마설정파일",                      # 한글
    "Ünïcødé—«»",                             # 라틴 확장·기호
    "...--__",                                # 점·구분자
    "\x01\x0b\x1f",                           # 제어문자
)
_FUZZ_EXTENSIONS = ("", ".ini", ".cfg", ".xml", ".json", ".INI", ".tar.gz", ".", ".sav", ".bak")


#: 입력 도메인의 **퇴화 경계**. 퍼저는 확률적이라 빈 문자열·공백만·루트 같은 극단을 어쩌다
#: 못 밟을 수 있다 — 경계는 고정으로 반드시 포함한다(특정 변이를 노린 열거가 아니라,
#: *"경계를 밟았음"*을 보장하는 퍼징의 기본 의무다).
_BOUNDARY_PATHS = ("", " ", "   ", "\t", "\n", "/", ".", "..", "/.", "//", "/ /", "x", "/" + "a" * 512)


def _fuzz_paths(rng, extra_literals, count=_FUZZ_N):
    """경로 **모양의 공간**을 훑는 표본. 고정 목록이 아니라 매 실행 다시 만든다."""
    paths = list(_BOUNDARY_PATHS)
    for _ in range(count):
        depth = rng.randint(0, 12)
        segments = []
        for _ in range(depth):
            alphabet = rng.choice(_SEGMENT_ALPHABETS)
            segments.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 14))))
        if rng.random() < 0.15:
            segments.insert(rng.randint(0, len(segments)) if segments else 0, "..")
        stem = "".join(rng.choice(rng.choice(_SEGMENT_ALPHABETS)) for _ in range(rng.randint(0, 20)))
        extension = rng.choice(_FUZZ_EXTENSIONS)
        if rng.random() < 0.2:                # 랜덤 확장자 — 확장자 기반 정책을 노린다
            extension = "." + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz_")
                                      for _ in range(rng.randint(1, 10)))
        path = "/".join(segments + [stem + extension])
        if rng.random() < 0.7:
            path = "/" + path
        if rng.random() < 0.05:               # 아주 긴 경로 — 길이 기반 정책을 노린다
            path = path + "/" + "x" * rng.randint(200, 400)
        paths.append(path)
    # ② 소스 리터럴 수확 — route가 쓰는 문자열을 그대로 경로에 심는다
    for literal in extra_literals:
        paths.append("/synth/610000/probe" + literal)
        paths.append("/synth/610000/" + literal + "/config.ini")
        paths.append(literal)
    return paths


def _route_string_literals(module):
    """그 모듈의 문자열 상수 **전량**. 경로 정책은 어디에 적히든 여기에 흔적을 남긴다.

    ★★ 2026-08-07 3회차: 예전에는 `add_game` **함수 본문**만 훑었다. Codex가 정책 문자열을
      **모듈 상수**로 빼자(`QA_FINAL_SUFFIX = ".p6module_constant"`) 본문에는 식별자만 남아
      수확 범위를 벗어났다 — `.qa_policy`와 효과가 같은 접미 정책인데 통과했다.
      "함수 본문"이라는 경계 자체가 임의였다. 모듈 전체로 넓히면 **상수를 어디로 옮기든**
      (모듈 상수·클래스 속성·다른 함수·기본 인자) 같은 파일에 있는 한 수확된다.

    ⚠️ 남는 것: **다른 모듈**에 둔 상수. 다만 이 프로젝트에서 route가 참조하는 모듈은
      `codes`·`confirm`·`engine`·`store`뿐이고 앞의 둘은 검사가 따로 잠근다.
    """
    source = pathlib.Path(module.__file__).read_text()
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docstrings:
                continue                       # 독스트링은 경로 조각이 될 일이 없다
            text = node.value.strip()
            if 0 < len(text) <= 40 and "\n" not in text:
                out.add(text)
    return sorted(out)


def t3b_route_adds_no_path_policy(mod, seed=None):
    """route와 엔진의 **수락 집합이 같은가** — 차등 판정.

    엔진 스텁이 경로 해시로 수락/거부를 갈라 **양방향**을 다 잰다:
      · 엔진이 수락한 것을 route가 거부 → route에 **추가 정책**이 생겼다(문이 둘)
      · 엔진이 거부한 것을 route가 수락 → route가 거부를 **삼켰다**
      · code가 다름                     → route가 사유를 갈아치웠다

    ⚠️ 대상은 **경로 정책**뿐이다. appid마다 새 값을 써서 `ALREADY_REGISTERED`(R2)와 섞이지
      않게 한다 — 그건 경로가 아니라 등록 상태에 대한 정책이고, 백엔드에 있는 것이 맞다.
    """
    bad = []
    rng = random.Random(seed)
    paths = _fuzz_paths(rng, _route_string_literals(mod))
    decided = {"accept": 0, "refuse": 0}

    def judge(path):
        """엔진의 판정 — 경로 해시로 갈라 **거부 쪽도** 표본에 들어가게 한다."""
        return hashlib.sha1(path.encode("utf-8", "surrogatepass")).digest()[0] % 4 == 0

    def stub(reg, appid, path, name=None):
        if judge(path):
            raise main.engine.Refused("합성 엔진 거부", code="PATH_OUTSIDE_PREFIX")
        entry = {"name": name or appid, "config_path": path, "cloud_synced": False}
        reg["games"][str(appid)] = entry
        return entry

    completed = False
    with Patch(entries=synth(), add_game=stub):
        for i, path in enumerate(paths):
            refused = judge(path)
            decided["refuse" if refused else "accept"] += 1
            env = call(mod.Plugin.add_game, str(610000 + i), path, owner=mod.Plugin)
            if refused:
                if env.get("ok") or env.get("code") != "PATH_OUTSIDE_PREFIX":
                    bad.append(f"엔진이 거부한 경로에서 route가 다른 결과를 냈다: {path!r} → {env}")
            elif not env.get("ok"):
                bad.append(f"엔진이 수락한 경로를 route가 거부했다: {path!r} → "
                           f"{env.get('code')} ★설계 §3-A 위반 — 경로 판정의 문은 엔진 하나다")
            if len(bad) >= 5:
                break                       # 다섯 건이면 사유는 충분하다
        else:
            completed = True
    # 측정이 대상에 닿았는가 — 한쪽으로만 쏠렸으면 차등 판정이 성립하지 않는다.
    # (중간에 끊었으면 표본이 안 찼을 뿐이므로 이 판정을 하지 않는다)
    if completed and (decided["accept"] < 20 or decided["refuse"] < 20):
        bad.append(f"표본이 한쪽으로 쏠렸다 {decided} — 차등 판정이 성립하지 않는다")
    return bad


# ── T4. warnings는 add_game 성공 뒤에만 ──────────────────────────────────────
def t4_warn_order():
    bad = []

    def boom(reg, appid, path, name=None):
        raise main.engine.Refused("합성 거부", code="PATH_OUTSIDE_PREFIX")

    with Patch(entries=synth(), add_game=boom) as p:
        env = call(main.Plugin.add_game, "500000", "/synth/500000/c0.ini")
        if env.get("ok"):
            bad.append("엔진이 거부했는데 route가 성공했다")
        if p.warn_calls:
            bad.append(f"add_game이 실패했는데 warnings를 조회했다: {p.warn_calls} ★D20 순서 규약 위반 — "
                       "전제가 깨진 경로에서 길이 슬라이싱이 거짓 경고를 만든다")
        if p.save_calls:
            bad.append("등록이 거부됐는데 registry를 저장했다")

    def ok(reg, appid, path, name=None):
        entry = {"name": name or appid, "config_path": path, "cloud_synced": False}
        reg["games"][str(appid)] = entry
        return entry

    with Patch(entries=synth(), add_game=ok) as p:
        LOG.clear()
        env = call(main.Plugin.add_game, "500000", "/synth/500000/c0.ini", "Game 0")
        if not env.get("ok"):
            bad.append(f"정상 등록이 실패했다 — {env}")
        if len(p.warn_calls) != 1:
            bad.append(f"warnings 조회가 {len(p.warn_calls)}회다(성공 뒤 1회여야 한다)")
        order = [kind for kind, *_ in LOG]
        if order != ["warnings", "log", "save"]:
            bad.append(f"호출 순서가 틀렸다: {order} (기대 warnings → log → save)")
    return bad


# ── T5·T6. 일괄 등록: 하나 실패해도 계속 · 저장 1회 · 로그가 먼저 ───────────
def t5_bulk_continues(exc_report=None):
    bad = []
    entries = synth(4)
    failed_appid = entries[2]["appid"]

    def flaky(reg, appid, path, name=None):
        if str(appid) == failed_appid:
            raise main.engine.Refused("합성 거부", code="FILE_NOT_FOUND")
        reg["games"][str(appid)] = {"name": name, "config_path": path}
        return reg["games"][str(appid)]

    with Patch(entries=entries, add_game=flaky) as p:
        LOG.clear()
        env = call(main.Plugin.register_confident)
        if not env.get("ok"):
            bad.append(f"게임 하나가 실패했다고 봉투가 실패가 됐다 — {env} ★불변식 위반")
            return bad
        rows = env["data"]["results"]
        # 애매한 게임(1번)은 대상이 아니다 — confident 3개만 시도해야 한다
        if len(rows) != 3:
            bad.append(f"확신 후보 3개를 시도해야 하는데 {len(rows)}개다 — {[r['appid'] for r in rows]}")
        added = [r["appid"] for r in rows if r["outcome"] == "added"]
        refused = [(r["appid"], r["code"]) for r in rows if r["outcome"] == "refused"]
        if len(added) != 2 or refused != [(failed_appid, "FILE_NOT_FOUND")]:
            bad.append(f"하나가 실패해도 나머지가 계속되지 않았다 — added={added} refused={refused}")
        if len(p.save_calls) != 1:
            bad.append(f"save_registry가 {len(p.save_calls)}회 불렸다 — 루프 밖 1회여야 한다")
        elif sorted(p.save_calls[0]["games"]) != sorted(added):
            bad.append(f"저장된 registry가 등록 결과와 다르다 — {sorted(p.save_calls[0]['games'])}")
        order = [kind for kind, *_ in LOG if kind in ("log", "save")]
        if order[-2:] != ["log", "save"]:
            bad.append(f"감사 로그가 save_registry보다 먼저 나가지 않았다: {order} ★QA R4 위반")
        # 거부 사유가 로그에 남는가 — 남기지 않으면 "무엇이 왜 안 됐나"가 어디에도 없다
        audit = [m for k, _, m in LOG if k == "log" and "register_confident" in m]
        if not audit or failed_appid not in audit[-1] or "FILE_NOT_FOUND" not in audit[-1]:
            bad.append(f"감사 로그에 실패 게임의 사유가 없다: {audit[-1:]!r}")

    # 등록이 0건이면 registry를 건드리지 않는다
    with Patch(entries=[dict(e, registered=True) for e in entries]) as p:
        env = call(main.Plugin.register_confident)
        if p.save_calls:
            bad.append("등록 0건인데 registry를 저장했다 — 이유 없는 실데이터 쓰기다")

    bad += t5b_general_exception_isolated(main, exc_report)
    return bad


class _QaCustomError(Exception):
    """사용자 정의 예외 — 표준 계층 밖의 종류도 격리되는지 본다."""


#: 손으로 고른 대표 8종. **바닥이지 전부가 아니다** — 아래 전수 수집이 본체다.
_SEED_EXCEPTIONS = (
    ValueError("합성 ValueError"),
    TypeError("합성 TypeError"),
    KeyError("합성 KeyError"),
    RuntimeError("합성 RuntimeError"),
    OSError(13, "합성 OSError"),
    ArithmeticError("합성 ArithmeticError"),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "합성 UnicodeDecodeError"),
    _QaCustomError("합성 사용자 정의 예외"),
)


def _all_exception_instances():
    """지금 프로세스에 **존재하는 `Exception` 하위형 전부**를 인스턴스로 만든다.

    ★★ 2026-08-07 3회차: 예전에는 손으로 고른 **8종 행렬**이었다. Codex가 행렬에 없는
      `NotImplementedError` 한 종만 재던지자 그대로 통과했다 — *"한 종을 고르면 그 칸에서
      걸린다"*는 주장은 **유한 행렬 밖 하위형에는 성립하지 않았다.** 목록을 늘리는 것은
      다음 하위형에 또 뚫린다.
      → 목록을 **런타임에 전수로** 만든다. `Exception.__subclasses__()`를 재귀로 훑으면
        그 시점에 import된 모든 예외형이 나온다. 구현이 **기존 타입 중 무엇을 고르든**
        그 칸이 표본에 있다.

    ⚠️ 정직한 잔여 표면(이제 이것만 남는다):
      · **변이 자신이 정의한 커스텀 타입**을 스스로 던지고 스스로 재던지는 경우 —
        수집 시점에 그 클래스가 아직 없을 수 있다. 다만 이는 *"실수로 격리가 깨진다"*는
        이 검사의 위협 모델(유지보수 사고) 밖이고, 그렇게 하려면 **의도적 공모**가 필요하다.
      · `BaseException` 직계(`KeyboardInterrupt`·`SystemExit`) — route가 원래 안 잡고
        **잡아서도 안 된다**(중단 신호). 의도적 제외다.
      · 인스턴스화에 실패해 건너뛴 형 — **개수를 출력한다**(0건 함정 방지).
    """
    seen, ordered = set(), []

    def collect(cls):
        for sub in cls.__subclasses__():
            if sub in seen:
                continue
            seen.add(sub)
            ordered.append(sub)
            collect(sub)

    collect(Exception)
    instances, skipped = list(_SEED_EXCEPTIONS), []
    have = {type(e) for e in instances}
    for cls in ordered:
        if cls in have:
            continue
        made = None
        for args in ((), ("합성 전수 주입",)):
            try:
                candidate = cls(*args)
                str(candidate)                 # note 문자열을 만들 수 있어야 한다
                made = candidate
                break
            except Exception:                  # noqa: BLE001  인스턴스화 불가 — 던질 수도 없다
                continue
        if made is None:
            skipped.append(cls.__name__)
        else:
            instances.append(made)
    return instances, skipped


def t5b_general_exception_isolated(mod, report=None):
    """**어떤 예외가 나도** 중간 게임 뒤가 계속 처리되는가 — **런타임 전수**로 잰다.

    ★★ 2026-08-07 재게이트 R3: 예전 T5b는 `ValueError` **한 종류**만 넣었다. 그래서
      `except Exception as exc: if isinstance(exc, TypeError): raise` 처럼 **한 종만 골라
      재던지는** 구현을 놓쳤다(Codex가 그렇게 뚫었다). 대표 하나로는 *"종류에 무관하다"*를
      잴 수 없다 — 무관함은 **여러 종류에 대해 같은 결과**로만 보인다.

    ⚠️ 정직한 잔여 표면: `BaseException`(`KeyboardInterrupt`·`SystemExit`)은 행렬에 넣지 않는다.
      route의 `except Exception`은 원래 그것들을 잡지 않고, 잡아서도 안 된다(중단 신호다).
    """
    bad = []
    instances, skipped = _all_exception_instances()
    for exc in instances:
        kind = type(exc).__name__
        entries = synth(4)
        boom_appid = entries[2]["appid"]      # 확신 3개 중 가운데 — 뒤에 처리될 게임이 남는다
        last_appid = entries[3]["appid"]

        def boom(reg, appid, path, name=None, _exc=exc, _boom=boom_appid):
            if str(appid) == _boom:
                raise _exc
            reg["games"][str(appid)] = {"name": name, "config_path": path}
            return reg["games"][str(appid)]

        with Patch(entries=entries, add_game=boom) as p:
            env = call(mod.Plugin.register_confident, owner=mod.Plugin)
            if not env.get("ok"):
                bad.append(f"[{kind}] 예외 하나로 봉투가 통째로 실패가 됐다 — {env} ★불변식 위반")
                continue
            rows = {r["appid"]: r for r in env["data"]["results"]}
            if len(rows) != 3:
                bad.append(f"[{kind}] 예외 뒤에 처리가 멈췄다 — 시도 {len(rows)}개(3개여야 한다)")
            # ★ 엔진의 `Refused`/`RegistryError`는 **설계상 다른 자리**로 간다(`refused` + code).
            #   전수 수집이 그 둘까지 끌어오므로 여기서 갈라 준다 — 둘을 `error`로 요구하면
            #   **정상 계약을 위반으로 세는 오탐**이 된다.
            expected = "refused" if isinstance(exc, (main.engine.Refused, main.store.RegistryError)) \
                else "error"
            outcome = rows.get(boom_appid, {}).get("outcome")
            if outcome != expected:
                bad.append(f"[{kind}] 예외가 {expected} 행으로 안 남았다 — {rows.get(boom_appid)}")
            elif expected == "error" and kind not in rows[boom_appid].get("note", ""):
                bad.append(f"[{kind}] error 행에 예외 종류가 안 남았다 — {rows[boom_appid]}")
            if rows.get(last_appid, {}).get("outcome") != "added":
                bad.append(f"[{kind}] 예외 **뒤** 게임이 등록되지 않았다 — {rows.get(last_appid)} "
                           "★'하나가 실패해도 나머지는 계속' 위반")
            if len(p.save_calls) != 1:
                bad.append(f"[{kind}] save_registry가 {len(p.save_calls)}회다(1회여야 한다)")
    if report is not None:
        report["injected"] = len(instances)
        report["skipped"] = skipped
    # 측정이 대상에 닿았는가 — 전수 수집이 무너져 씨앗만 남으면 옛 유한 행렬로 퇴화한 것이다
    if len(instances) < 40:
        bad.append(f"수집된 예외형이 {len(instances)}종뿐이다 — 전수 수집이 동작하지 않았다"
                   f"(유한 행렬로 퇴화하면 행렬 밖 하위형에 다시 뚫린다)")
    return bad


# ── T7. 감지 제외 봉투 — 두 route가 같은 목록을 본다 (A9 · 설계 §8-C·§8-D) ──
def t7_excluded_envelope():
    """제외 필터는 `_discover_entries` **한 곳**이라, 화면 목록(`discover_games`)과 일괄 등록
    (`register_confident`)이 구조적으로 같은 것을 본다. 두 곳에서 거르면 *"화면에 안 뜬 게임이
    등록되는"* 어긋남이 언젠가 생긴다 — 여기서 그 한 곳이 두 route 모두에 듣는지 잰다.

    (제외의 전 계약은 `qa/test_discover_exclude.py`가 잠근다. 이 절은 **P6 route 봉투**의 몫만.)
    """
    bad = []
    entries = synth(4)
    hidden = entries[0]["appid"]
    reg = main.store.load_registry()
    reg["settings"]["discover_excluded"] = {
        hidden: {"name": "숨긴 게임", "excluded_at": "2026-08-11T09:00:00+0900"}}
    main.store.save_registry(reg)
    try:
        with Patch(entries=entries) as p:
            env = call(main.Plugin.discover_games)
            seen = {e["appid"] for e in env["data"]["entries"]}
            if hidden in seen:
                bad.append(f"제외한 게임이 탐지 목록에 남았다 — {sorted(seen)}")
            rows = env["data"].get("excluded")
            if [r["appid"] for r in rows or []] != [hidden]:
                bad.append(f"discover_games 봉투의 excluded가 제외분을 안 싣는다 — {rows}")
            elif set(rows[0]) != {"appid", "name", "excluded_at_label"}:
                bad.append(f"excluded 행의 키 집합이 계약과 다르다 — {sorted(rows[0])}")

            env = call(main.Plugin.register_confident)
            tried = {r["appid"] for r in env["data"]["results"]}
            if hidden in tried:
                bad.append(f"제외한 게임이 일괄 등록에 섞였다 — {sorted(tried)} ★두 route가 다른 것을 봤다")
            if p.save_calls and hidden in p.save_calls[-1]["games"]:
                bad.append("제외한 게임이 registry에 저장됐다")
    finally:
        reg = main.store.load_registry()
        reg["settings"].pop("discover_excluded", None)
        main.store.save_registry(reg)
    return bad


# ── §B. 반증 — 깨진 구현에서 실제로 FAIL하는가 ───────────────────────────────
def falsify():
    """각 단언을 **고의로 깨뜨린 대조군**에 걸어 본다. 통과하면 그 검사는 거짓 검사다."""
    report, bad = [], []

    # B1: warnings를 먼저 부르는 구현 → T4가 잡아야 한다
    real_add = main.engine.add_game

    def wrong_order(reg, appid, path, name=None):
        main.engine.config_candidate_warnings(appid, path)      # ★ 순서 위반 주입
        raise main.engine.Refused("합성 거부", code="PATH_OUTSIDE_PREFIX")

    with Patch(entries=synth(), add_game=wrong_order) as p:
        call(main.Plugin.add_game, "500000", "/synth/500000/c0.ini")
        caught = bool(p.warn_calls)
    report.append(("B1 warnings를 add_game 전에 호출", caught))
    if not caught:
        bad.append("B1 반증 실패 — 순서를 어겨도 T4가 못 잡는다")

    # B2: 일반 예외 격리를 좁힌 **main.py 실물 사본** → T5b가 잡아야 한다
    #     ★ 예전 B2는 `KeyboardInterrupt`가 뚫는 것을 "검출"로 셌다 — 그건 자기 판정이라
    #       *"`except Exception`이 좁아진 구현"*의 대조군이 되지 못했다(2026-08-07 QA R3).
    narrowed, applied = load_mutant_main(
        [("            except Exception as exc:                       # noqa: BLE001",
          "            except RuntimeError as exc:                    # QA MUTATION")],
        "narrow_except")
    for old, new in applied:
        print(f"     [주입] main.py  {old}  →  {new}")
    caught = bool(t5b_general_exception_isolated(narrowed))
    report.append(("B2 일반 예외 격리를 RuntimeError로 좁힌 사본", caught))
    if not caught:
        bad.append("B2 반증 실패 — except를 좁혀도 T5가 못 잡는다")

    # B2-b: **한 종류만** 골라 재던지는 사본 → 행렬이 아니면 원리적으로 못 잡는다
    selective, applied = load_mutant_main(
        [("            except Exception as exc:                       # noqa: BLE001",
          "            except Exception as exc:                       # QA MUTATION\n"
          "                if isinstance(exc, TypeError):\n"
          "                    raise")],
        "selective_reraise")
    print("     [주입] main.py  register_confident의 except에 `if isinstance(exc, TypeError): raise` 추가")
    caught = bool(t5b_general_exception_isolated(selective))
    report.append(("B2-b 한 종류(TypeError)만 재던지는 사본", caught))
    if not caught:
        bad.append("B2-b 반증 실패 — 한 종만 재던져도 T5가 못 잡는다(행렬이 대표 하나로 퇴화했다)")

    # B2′: route가 독자 경로 정책을 끼워 넣은 **실물 사본** → T3b가 잡아야 한다
    policy, applied = load_mutant_main(
        [("        reg = store.load_registry()\n\n        known = confirm.already_registered(reg, appid)",
          "        if not str(config_path).strip():                   # QA MUTATION\n"
          "            raise engine.Refused('공백 경로', code=codes.BAD_IDENTIFIER)\n"
          "        reg = store.load_registry()\n\n        known = confirm.already_registered(reg, appid)")],
        "glue_policy")
    for old, new in applied:
        print(f"     [주입] main.py  add_game 앞에 glue 경로 정책 추가  ({new})")
    caught = bool(t3b_route_adds_no_path_policy(policy, seed=FUZZ_SEED))
    report.append(("B2′ route에 엔진 밖 경로 정책 주입(퇴화 경계형)", caught))
    if not caught:
        bad.append("B2′ 반증 실패 — route에 독자 경로 정책을 넣어도 T3가 못 잡는다")

    # B2″: **특정 확장자**를 노리는 정책 → 고정 표본으로는 원리적으로 못 잡는다.
    #      소스 리터럴 수확이 그 문자열을 경로로 되돌려 심어 **구성으로** 잡는다.
    suffix, _applied = load_mutant_main(
        [("        reg = store.load_registry()\n\n        known = confirm.already_registered(reg, appid)",
          "        if str(config_path).endswith('.qa_policy'):       # QA MUTATION\n"
          "            return _fail(codes.BAD_IDENTIFIER)\n"
          "        reg = store.load_registry()\n\n        known = confirm.already_registered(reg, appid)")],
        "suffix_policy")
    print("     [주입] main.py  add_game에 `.qa_policy` 접미 거부 정책 추가")
    print(f"            수확된 소스 리터럴 {len(_route_string_literals(suffix))}개로 경로를 되심는다")
    caught = bool(t3b_route_adds_no_path_policy(suffix, seed=FUZZ_SEED))
    report.append(("B2″ route에 특정 확장자 거부 정책 주입(소스 리터럴 수확)", caught))
    if not caught:
        bad.append("B2″ 반증 실패 — 특정 문자열을 노리는 정책을 T3가 못 잡는다")

    # B3: discover.py에 쓰기를 넣은 **실물 사본**을 실제로 돌린다 → T1(효과 측정)이 잡아야 한다
    #     ★ 판정이 문법에서 효과로 옮겨졌으므로 대조군도 *소스를 훑는 것*이 아니라
    #       *돌려서 세계가 변했는가*가 된다. 아래 4종은 **쓰는 수단이 전부 다르다** —
    #       이름 매칭으로는 b·c·d를 못 잡는다(b가 Codex가 뚫은 그 형태다).
    anchor = "    results.sort(key=lambda item: item[\"name\"].lower())"
    outside = os.path.join(_TMP, "b3-outside-write")
    mutants = {
        "save_registry 호출(세계 밖)": [
            (anchor,
             "    engine.store.save_registry(engine.store.default_registry())  # QA MUTATION\n"
             + anchor)],
        "별칭 우회 qa_writer = Path(...).open (세계 밖)": [
            (anchor,
             '    qa_writer = __import__("pathlib").Path(%r).open  # QA MUTATION\n'
             '    qa_writer("w").close()\n' % outside + anchor)],
        "import 시점 별칭으로 **세계 안**에 쓰기": [
            ("import os\nimport re\nimport time",
             "import os\nimport re\nimport time\n_QA_OPEN = open  # QA MUTATION (계측 이전에 만들어진 별칭)"),
            ("            candidates = _scan_prefix(prefix)",
             "            _QA_OPEN(os.path.join(prefix, 'qa_alias.ini'), 'w').close()  # QA MUTATION\n"
             "            candidates = _scan_prefix(prefix)")],
        "저수준 os.open+os.write (세계 밖)": [
            (anchor,
             "    _fd = os.open(%r, os.O_WRONLY | os.O_CREAT)  # QA MUTATION\n"
             "    os.write(_fd, b'x')\n    os.close(_fd)\n" % (outside + "-fd") + anchor)],
    }
    for i, (label, reps) in enumerate(mutants.items()):
        try:
            module, applied = load_mutant_discover(reps, "b3_%d" % i)
        except AssertionError as exc:
            bad.append(f"B3 변이가 주입되지 않았다({label}) — {exc}")
            continue
        print(f"     [주입] discover.py  {label}")
        for line in applied:
            print(f"            + {line}")
        mut_bad = t1_discover_pure(module)
        caught = bool(mut_bad[0])
        report.append((f"B3 discover 사본: {label}", caught))
        if caught:
            print(f"            → 검출: {mut_bad[0][0]}")
        else:
            bad.append(f"B3 반증 실패 — {label}를 넣고 돌려도 T1이 못 잡는다")
    # 음성 대조군: 손대지 않은 사본은 여전히 깨끗하다(변이 판정이 무엇이든 잡는 것은 아니다)
    clean, _ = load_mutant_discover([(anchor, anchor + "  # QA CONTROL (동작 무변경)")], "b3_clean")
    clean_bad = t1_discover_pure(clean)[0]
    report.append(("B3′ 손대지 않은 discover 사본은 통과(음성 대조군)", not clean_bad))
    if clean_bad:
        bad.append(f"B3′ 음성 대조군 실패 — 원본이 위반으로 잡혔다: {clean_bad}")

    # B4: register_confident가 appid 목록을 받는 구현 → T2가 잡아야 한다
    fake = "class X:\n    def register_confident(self, appids=None):\n        pass\n"
    params = [a.arg for n in ast.walk(ast.parse(fake))
              if isinstance(n, ast.FunctionDef) and n.name == "register_confident"
              for a in n.args.args]
    report.append(("B4 appids 인자를 가진 route", params != ["self"]))
    if params == ["self"]:
        bad.append("B4 반증 실패 — 인자를 붙여도 T2의 판정 기준이 못 잡는다")

    return report, bad


def main_():
    problems = []

    pure_bad, snapshot_n, write_n = t1_discover_pure()
    print(f"T1 discover 순수성(효과 측정) — 합성 세계 {snapshot_n}개 항목 전후 대조 · "
          f"쓰기 원시함수 호출 {write_n}건 (변화 0 · 호출 0이어야 한다)")
    problems += pure_bad

    problems += t2_no_appid_list()
    print("T2 일괄 등록 route에 appid 목록 인자 없음 (AST + 동작)")

    problems += t3_path_not_validated()
    print(f"T3 경로 인자 무검증 — _VALIDATORS = {sorted(main._VALIDATORS)} · "
          f"차등 퍼징 {_FUZZ_N}+개 경로 · seed={FUZZ_SEED} "
          f"(재현: GFXP_FUZZ_SEED={FUZZ_SEED})")

    problems += t4_warn_order()
    print("T4 warnings 조회는 add_game 성공 뒤 1회 · 순서 warnings→log→save")

    exc_report = {}
    problems += t5_bulk_continues(exc_report)
    print(f"T5/T6 하나 실패해도 계속 · save_registry 1회 · 로그가 먼저 · "
          f"예외 **전수 주입** {exc_report.get('injected', 0)}종 "
          f"(인스턴스화 불가로 건너뜀 {len(exc_report.get('skipped', []))}종"
          + (f": {', '.join(exc_report['skipped'][:6])}…" if exc_report.get("skipped") else "")
          + ")")

    problems += t7_excluded_envelope()
    print("T7 감지 제외 — 두 route가 같은 목록을 본다 · discover_games 봉투의 excluded 모양")

    # ★ 앵커가 사라지면 **크래시가 아니라 FAIL**이다. 크래시는 위에서 모은 problems를 못 찍고
    #   죽어서 "무엇이 걸렸는지"를 통째로 가린다 — 진단 가능성이 안전만큼 중요하다.
    try:
        report, fals_bad = falsify()
    except AssertionError as exc:
        report, fals_bad = [], [f"§B 반증을 돌리지 못했다(변이 앵커 소실) — {exc}"]
    print("\n§B 반증 (깨뜨렸을 때 FAIL이 나는가)")
    for label, caught in report:
        print(f"  {'✓' if caught else '✗'} {label} → {'검출됨' if caught else '못 잡음'}")
    problems += fals_bad

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    try:
        code = main_()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
