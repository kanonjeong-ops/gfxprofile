#!/usr/bin/env python3
"""`engine.compat_prefix()` — 매니페스트 우선 2패스를 잠근다.

무엇을 지키는가:
    게임을 SD로 옮긴 뒤 앞선 라이브러리에도 같은 appid의 pfx가 남으면 첫 매치 방식은 그쪽을
    고른다. 이 기기의 appid 389730도 두 라이브러리에 pfx가 있고 SD 쪽에 매니페스트가 있어,
    현재 2패스는 SD prefix를 고른다.

    → 1차 패스 = `appmanifest_<appid>.acf`가 있는 라이브러리의 pfx
      2차 패스 = 라이브러리 순서대로 첫 isdir — 매니페스트를 못 찾으면 1차가 없던 것과 같다.

이 테스트는 합성 라이브러리로 판정한다. 실데이터 절은 registry.json과 디렉터리 존재 여부만
읽는 읽기 전용이고, 설정 파일을 열지 않는다.

반증: 1차 패스를 제거한 소스 사본을 별도 모듈로 올려, 그 사본에서 합성 시나리오가 실제로
FAIL하는지 확인한다. 주입한 줄은 그대로 출력한다 — "이 단언이 FAIL이 되는 입력이 존재하는가"에
답하지 못하는 검사는 거짓 검사다.
"""
import json
import os
import pathlib
import pwd
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))
from gfxp import engine  # noqa: E402

APPID = "999001"
ENGINE_SRC = ROOT / "py_modules" / "gfxp" / "engine.py"

#: 반증 주입 — 이 한 줄만 바꾸면 1차(매니페스트) 패스가 통째로 사라진다.
#:   `INJECT_FROM`은 `engine.compat_prefix`의 2패스 반복문과 바이트 단위로 같아야 한다.
INJECT_FROM = "    for want_manifest in (True, False):"
INJECT_TO = "    for want_manifest in (False,):   # ★반증 주입: 매니페스트 패스 제거"


def home():
    """`$HOME`·`Path.home()`을 쓰지 않는다 — HOME 격리 함정(테스트가 자기 환경에 묶인다)."""
    return pwd.getpwuid(os.getuid()).pw_dir


# ── §2. 합성 라이브러리와 시나리오 ────────────────────────────────────────────

def build_libs(base, manifest_in, pfx_in):
    """라이브러리 2개를 만든다. `manifest_in`/`pfx_in`은 1-기반 번호 집합."""
    libs = []
    for i in (1, 2):
        lib = os.path.join(base, "lib%d" % i)
        os.makedirs(os.path.join(lib, "steamapps"), exist_ok=True)
        if i in pfx_in:
            os.makedirs(os.path.join(lib, "steamapps", "compatdata", APPID, "pfx"))
        if i in manifest_in:
            with open(os.path.join(lib, "steamapps", "appmanifest_%s.acf" % APPID), "w") as fh:
                fh.write('"AppState"\n{\n\t"appid"\t\t"%s"\n\t"name"\t\t"Synthetic"\n}\n' % APPID)
        libs.append(lib)
    return libs


def call(module, libs, appid=APPID):
    """`steam_libraries()`만 갈아끼우고 대상 함수를 부른다 (원복 보장)."""
    original = module.steam_libraries
    module.steam_libraries = lambda: list(libs)
    try:
        return module.compat_prefix(appid)
    finally:
        module.steam_libraries = original


#: (설명, 매니페스트 위치, pfx 위치, 기대 라이브러리 번호)
SCENARIOS = [
    # 본 사건. 1번 = 내장 껍데기(pfx만) / 2번 = 진짜(매니페스트+pfx).
    ("SD 이동 재현 — 1번은 껍데기, 2번에 매니페스트", {2}, {1, 2}, 2),
    # 순서를 뒤집어도 '매니페스트가 있는 쪽'을 고르는가 (= 단순히 마지막을 고르는 게 아니다)
    ("매니페스트가 1번에 있으면 1번", {1}, {1, 2}, 1),
    # 매니페스트가 없으면 2차 패스로 내려간다 — 라이브러리 순서대로 첫 isdir
    ("매니페스트 없음 — 기존 폴백(첫 매치)", set(), {1, 2}, 1),
    # 매니페스트는 2번인데 pfx가 1번에만 있다 → 1차 패스가 비어 2차로 내려간다
    ("매니페스트 쪽에 pfx가 없으면 2차 폴백", {2}, {1}, 1),
]


def check_scenarios(module, label):
    """SCENARIOS 전부를 돌려 `[(설명, 기대, 실제)]` 중 어긋난 것만 돌려준다."""
    bad = []
    base = tempfile.mkdtemp(prefix="gfxp-compat-")
    try:
        for i, (desc, man, pfx, want) in enumerate(SCENARIOS):
            sub = os.path.join(base, "case%d" % i)
            os.makedirs(sub)
            libs = build_libs(sub, man, pfx)
            got = call(module, libs)
            expect = os.path.join(libs[want - 1], "steamapps", "compatdata", APPID, "pfx")
            if got != expect:
                bad.append((desc, "lib%d" % want, got))
            elif label:
                print(f"  [{label}] {desc} → lib{want} ✓")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return bad


# ── §3. 반증 — 수정을 무력화한 사본 ───────────────────────────────────────────

def load_mutant():
    """1차 패스를 제거한 engine.py 사본을 `gfxp._engine_mutant`로 올린다."""
    import types
    src = ENGINE_SRC.read_text()
    if INJECT_FROM not in src:
        return None, f"주입 지점을 못 찾았다(코드가 바뀌었나?): {INJECT_FROM!r}"
    mutant = src.replace(INJECT_FROM, INJECT_TO, 1)
    mod = types.ModuleType("gfxp._engine_mutant")
    mod.__package__ = "gfxp"
    mod.__file__ = str(ENGINE_SRC) + "(mutant)"
    sys.modules["gfxp._engine_mutant"] = mod
    exec(compile(mutant, mod.__file__, "exec"), mod.__dict__)   # noqa: S102 — 반증 전용
    # 주입 증거 — 사본이 실제로 컴파일한 소스에서 그 줄을 뽑는다.
    # (`inspect.getsource`는 디스크에 없는 사본을 못 읽는다. 여기서는 우리가 원문을 들고 있다.)
    mod._injected_lines = [ln for ln in mutant.splitlines() if "want_manifest in" in ln]
    if mod.compat_prefix is engine.compat_prefix:
        return None, "사본이 원본과 같은 함수를 들고 있다 — 주입이 실패했다"
    return mod, None


# ── §4. 실데이터 대조 (읽기 전용) ─────────────────────────────────────────────

def single_pass(appid):
    """1차 패스가 없을 때의 동작을 재현한 대조군 — 첫 isdir."""
    for root in engine.steam_libraries():
        path = os.path.join(root, "steamapps", "compatdata", str(appid), "pfx")
        if os.path.isdir(path):
            return path
    return None


REGISTRIES = (
    ("M1", os.path.join(home(), ".local", "share", "gfxprofile", "registry.json")),
    ("v2", os.path.join(home(), "homebrew", "data", "gfxprofile", "registry.json")),
)


def check_real_registries():
    """등록된 게임 전부에서 2패스와 1패스를 대조한다.

    ① `config_path` 문자열이 2패스 prefix의 실경로와 구분자 접두로 맞아야 한다.
       이 검사는 `config_path` 자체를 실경로화하지 않으므로 일반적인 조상 판정은 아니다.
    ② 둘의 답이 달라졌다면 1패스 값은 이 접두 조건을 만족하지 않고 2패스 값은 만족해야 한다.
    """
    bad, seen, changed, unchanged = [], 0, [], 0
    for label, path in REGISTRIES:
        if not os.path.exists(path):
            print(f"  ({label} registry 없음 — 건너뜀: {path})")
            continue
        with open(path, "r", encoding="utf-8") as fh:
            reg = json.load(fh)
        for appid, entry in sorted((reg.get("games") or {}).items()):
            cfg = entry.get("config_path")
            if not cfg:
                continue
            seen += 1
            new = engine.compat_prefix(appid)
            old = single_pass(appid)
            new_ok = bool(new) and cfg.startswith(os.path.realpath(new) + os.sep)
            old_ok = bool(old) and cfg.startswith(os.path.realpath(old) + os.sep)
            if not new_ok:
                bad.append(f"{label} {appid}: 수정 후 prefix가 config_path의 조상이 아니다 ★불변식 위반"
                           f"\n      prefix={new}\n      config={cfg}")
            if old == new:
                unchanged += 1
            else:
                changed.append((label, appid, old, new, old_ok))
                if old_ok:
                    bad.append(f"{label} {appid}: 옛 값도 정상이었는데 반환이 바뀌었다 — 불필요한 변경"
                               f"\n      전={old}\n      후={new}")
    print(f"  실데이터 등록 게임 {seen}개 — 수정 전후 동일 {unchanged}개 / 달라진 것 {len(changed)}개")
    for label, appid, old, new, _ in changed:
        print(f"    ★ {label} {appid}: 오거부를 고친 변경\n       전={old}\n       후={new}")
    if seen == 0:
        print("  ⚠️ 훑은 게임이 0개다 — 이 절은 아무것도 판정하지 못했다")
    return bad


def main():
    problems = []

    print("§2 합성 시나리오 (수정본)")
    problems += [f"시나리오 실패: {d} — 기대 {w} / 실제 {g}" for d, w, g in
                 check_scenarios(engine, "수정본")]

    print("\n§3 반증 — 1차 패스를 제거한 사본에서 FAIL이 나는가")
    print(f"  주입: {INJECT_FROM.strip()!r}\n     →  {INJECT_TO.strip()!r}")
    mutant, err = load_mutant()
    if err:
        problems.append("반증 불가 — " + err)      # 판정할 수 없으면 통과가 아니라 거부다
    else:
        print(f"  사본이 실제로 컴파일한 줄: {mutant._injected_lines}")
        mut_bad = check_scenarios(mutant, "")
        descs = [d for d, _, _ in mut_bad]
        print(f"  사본에서 어긋난 시나리오 {len(mut_bad)}개: {descs}")
        if SCENARIOS[0][0] not in descs:
            problems.append(
                "반증 실패 — 1차 패스를 제거해도 §2가 통과한다. 이 검사는 수정을 재고 있지 않다")
        for d, w, g in mut_bad:
            if d in (SCENARIOS[2][0], SCENARIOS[3][0]):
                problems.append(f"반증 이상 — 폴백 시나리오까지 깨졌다({d}). 주입이 과하다")

    print("\n§4 실데이터 대조 (읽기 전용)")
    problems += check_real_registries()

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  " + p)
        return 1
    print("\nPASS — 매니페스트 우선 2패스 · 폴백 불변 · 반증 성립")
    return 0


if __name__ == "__main__":
    sys.exit(main())
