#!/usr/bin/env python3
"""**확인 없는 덮어쓰기는 불가능하다** — 그 유일한 증명. 설계 §2-E-0 · P4 착수 조건 ③.

이 파일이 왜 중요한가: 인계 문서가 *"`test_save_needs_token` 6항목은 **한 번도 실행된 적이 없다**.
그전까지 「TOCTOU가 닫혔다」는 **주장이지 증명이 아니다**"*라고 적어 둔 자리다.
그리고 QA가 P4로 넘긴 조건 ③이 *"**막아야 할 상황을 실제로 만들어** 검증하라 —
「검사하는 코드가 있다」는 검증이 아니다"*였다.

**소스 패턴(grep)으로는 이 계약을 강제할 수 없다.** 2판이 붙였던 `confirmed:\\s*true` grep은
positional 호출 `saveProfile(appid, profile, true)`를 **못 잡아 무효**였다(반증자 실측:
그 패턴 0건 / 실제 호출 1건). 그래서 **실제로 돌려서** 잰다.

★ 실데이터에 닿을 수 없다 — `main.py`는 `DECKY_PLUGIN_RUNTIME_DIR`이 없으면 **뜨지도 않고**,
  있으면 그것을 `GFXPROFILE_DATA_DIR`에 **무조건 대입**한다. 여기서는 그것이 tmp다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPID = "555"
A = b"quality=A\nshadows=high\n"      # 프로필에 저장될 내용
B = b"quality=B\nshadows=low\n"       # 디스크의 다른 내용 (덮어쓰기 상황을 만든다)
C = b"quality=C\nshadows=mid\n"


def boot(tmp):
    """`main.py`를 샌드박스에서 띄운다. `decky`는 로더가 주는 모듈이라 여기서 흉내 낸다."""
    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None,
        error=lambda *a, **k: None, debug=lambda *a, **k: None)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")   # ← 격리는 이 한 줄이 한다
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def call(main, *args, **kwargs):
    """route는 async다(Decky가 반환값을 await한다). 봉투를 그대로 돌려준다."""
    return asyncio.run(main.Plugin().save_profile(*args, **kwargs))


def main_test():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-token-"))
    try:
        main = boot(tmp)
        from gfxp import codes, engine, store
        problems = []

        cfg = tmp / "game" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(A)
        reg = store.default_registry()
        engine.add_game(reg, APPID, str(cfg), name="TokenTarget")
        store.save_registry(reg)

        def slot_sha1():
            return (store.load_meta(APPID, "dock") or {}).get("sha1")

        def is_confirm(env):
            return env.get("ok") is False and env.get("code") == codes.CONFIRM_REQUIRED

        # ── 0) 안 물어야 하는 두 경우 ─────────────────────────────────────────
        # 이게 깨지면 **초기 세팅(A·B 두 벌 만들기)이 통째로 확인창 지옥**이 된다 —
        # 사용자가 명시적으로 피한 마찰이라 계약의 절반은 "묻지 않는 것"이다.
        env = call(main, APPID, "dock")                   # 빈 슬롯 첫 저장
        if not env.get("ok"):
            problems.append(f"빈 슬롯 첫 저장에 확인을 요구했다 — 초기 세팅이 확인창 지옥이 된다 ({env})")
        saved_A = slot_sha1()

        env = call(main, APPID, "dock")                   # 내용이 이미 같다
        if not env.get("ok"):
            problems.append(f"내용이 같은 재저장에 확인을 요구했다 — 잃을 것이 없는 저장이다 ({env})")

        # ── 덮어쓰기 상황을 만든다 ────────────────────────────────────────────
        cfg.write_bytes(B)
        if slot_sha1() != saved_A:
            problems.append("사전 조건이 안 섰다 — 프로필이 이미 바뀌었다")

        # ── ① 토큰 없음 ──────────────────────────────────────────────────────
        env = call(main, APPID, "dock")
        if not is_confirm(env):
            problems.append(f"① 토큰 없이 덮어쓰기가 통과했다 ★계약 위반 ({env})")
        tok1 = (env.get("params") or {}).get("confirm_token")
        if not tok1:
            problems.append("① CONFIRM_REQUIRED에 confirm_token이 없다 — 프론트가 확정할 방법이 없다")
        if slot_sha1() != saved_A:
            problems.append("① 거부인데 프로필이 바뀌었다 — 「파일을 건드리지 않는다」가 거짓이다")

        # ── ② 위조 토큰 ──────────────────────────────────────────────────────
        env = call(main, APPID, "dock", confirm_token="아무-문자열-지어냄")
        if not is_confirm(env):
            problems.append(f"② 지어낸 토큰으로 덮어쓰기가 통과했다 ★계약 위반 ({env})")
        if slot_sha1() != saved_A:
            problems.append("② 거부인데 프로필이 바뀌었다")

        # ── ③ 정상 토큰 ──────────────────────────────────────────────────────
        env = call(main, APPID, "dock", confirm_token=tok1)
        if not env.get("ok"):
            problems.append(f"③ 백엔드가 방금 발급한 토큰인데 저장이 안 됐다 ({env})")
        if slot_sha1() == saved_A:
            problems.append("③ 저장 성공이라는데 프로필이 안 바뀌었다 — 재려던 경로에 닿지 못했다")

        # ── ④ 1회용 소각 ─────────────────────────────────────────────────────
        # ★ 행위 수준에서만 재면 **거부 사유가 「소각」인지 「상태 변경」인지 갈리지 않는다**
        #   (③ 직후엔 상태도 같이 바뀌기 때문이다). 그래서 소각 자체를 인자 고정으로 직접 잰다.
        tok = main._issue("999", "dock", "m", "d")
        if not main._consume(tok, "999", "dock", "m", "d"):
            problems.append("④ 방금 발급한 토큰이 첫 소비에서 거부됐다")
        if main._consume(tok, "999", "dock", "m", "d"):
            problems.append("④ 같은 토큰이 두 번 통과했다 — 1회용이 아니다 ★계약 위반")
        if tok1 in main._CONFIRM_TOKENS:
            problems.append("④ ③에서 쓴 토큰이 아직 살아 있다 — 소각되지 않았다")

        # ── ⑤ 상태 바인딩 (TOCTOU) ──────────────────────────────────────────
        # 토큰을 받은 **뒤** 디스크가 바뀌면, 사용자가 확인창에서 본 숫자는 이미 낡았다.
        cfg.write_bytes(C)
        env = call(main, APPID, "dock")                   # 새 토큰 발급 (상태 = C)
        tok5 = (env.get("params") or {}).get("confirm_token")
        before5 = slot_sha1()
        cfg.write_bytes(A)                                # ← 확인창을 띄운 사이에 게임이 다시 썼다
        env = call(main, APPID, "dock", confirm_token=tok5)
        if not is_confirm(env):
            problems.append(f"⑤ 상태가 바뀌었는데 낡은 토큰이 통과했다 ★TOCTOU가 안 닫혔다 ({env})")
        if slot_sha1() != before5:
            problems.append("⑤ 거부인데 프로필이 바뀌었다")

        # ── ⑥ 만료 ───────────────────────────────────────────────────────────
        cfg.write_bytes(C)
        env = call(main, APPID, "dock")
        tok6 = (env.get("params") or {}).get("confirm_token")
        real_ttl, main._CONFIRM_TTL = main._CONFIRM_TTL, 0     # 모달을 열어 둔 채 오래 둔 상황
        try:
            env = call(main, APPID, "dock", confirm_token=tok6)
        finally:
            main._CONFIRM_TTL = real_ttl
        if not is_confirm(env):
            problems.append(f"⑥ 만료된 토큰이 통과했다 ★계약 위반 ({env})")

        print("확인 토큰 계약 6항목 + 「묻지 않는」 2경우  (데이터: %s)" % tmp)
        print("  ①없음 ②위조 ③정상 ④소각 ⑤상태바인딩 ⑥만료  / 빈슬롯·동일내용은 무확인 저장")
        if problems:
            print("\nFAIL")
            for p in problems:
                print("  " + p)
            return 1
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
