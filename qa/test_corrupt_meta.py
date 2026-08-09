#!/usr/bin/env python3
"""손상된 meta.json 하나가 현황·저장·삭제를 통째로 죽이지 않는다 (2026-08-09 조사 발견).

배경: `store.load_meta`는 fence 대상이라 유효 JSON이지만 dict가 아닌 값(`"text"`·`[1,2]`·`42`)이나
비JSON 바이트를 **그대로/예외로** 돌려준다. 이를 소비하는 세 갈래가 방어 없이 dict로 다루면:
  · `store.profile_file_path`가 `meta["filename"]`에서 TypeError (→ _profile_ready → get_overview)
  · `engine.disk_state`가 `meta.get`에서 AttributeError (fence, engine.py:306 — get_overview detail·저장 지문)
  · `(meta or {}).get`이 비-dict에서 AttributeError (_state_fingerprint)
→ 손상 슬롯 **하나** 때문에 현황 탭 전체가 UNEXPECTED로 안 뜨는 등 광범위 봉쇄가 났다.
이 조사가 잡은 것은 Codex #5(삭제·초기화 봉쇄, test_delete_game ⑧-c에서 잠금)의 **현황·저장 갈래**다.

방어 자리(fence 밖 소비자):
  · main._profile_ready — load_meta가 dict 아니면 적용 불가로 접음
  · main._state_fingerprint — 비-dict면 meta_sha1=None
  · main._disk_state_safe — disk_state 소비를 한 곳에 모아 넓은 except로 감쌈(두더지 잡기 방지)

손상 meta는 악의가 아니라 **디스크 사고로도 도달 가능한 실제 상태**다(save_profile docstring도 그리 적음).
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 유효 JSON 비객체 3종 + 비JSON 바이트 1종 — 각각 다른 소비 지점을 때린다.
CORRUPT = [("문자열", '"just a string"'), ("배열", "[1, 2, 3]"),
           ("숫자", "42"), ("비JSON", "\x00\xff not json at all")]


def boot(tmp):
    fake = types.ModuleType("decky")
    noop = lambda *a, **k: None                                  # noqa: E731
    fake.logger = types.SimpleNamespace(info=noop, warning=noop, error=noop, debug=noop, log=noop)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-corrupt-"))
    fails = []

    def P(msg):
        fails.append(msg)

    try:
        main = boot(tmp)
        from gfxp import store, engine

        cfg = tmp / "c.ini"
        cfg.write_text("quality=high\nres=4k\n" * 3)

        for kind, content in CORRUPT:
            # 매 케이스 깨끗한 게임 — 상태 누적 아티팩트를 피한다(조사 중 실제로 겪은 함정).
            reg = store.load_registry()
            reg["games"]["222"] = {"name": "H", "config_path": str(cfg)}
            engine.save_profile(reg, "222", "dock")
            store.save_registry(reg)
            # dock 슬롯의 meta.json을 손상시킨다(본체는 그대로 — meta만).
            with open(store.profile_meta_path("222", "dock"), "w", encoding="utf-8") as fh:
                fh.write(content)

            # ① 현황 탭 두 경로 — UNEXPECTED로 죽으면 안 된다.
            ov_f = rpc(main, "get_overview")
            if not ov_f.get("ok"):
                P("[%s] get_overview(detail=false)가 손상 meta에 죽었다 — %s" % (kind, ov_f.get("code")))
            ov_t = rpc(main, "get_overview", True)               # StatusPage(현황 탭)가 쓰는 경로
            if not ov_t.get("ok"):
                P("★[%s] get_overview(detail=true=현황 탭)가 손상 meta 하나로 통째 죽었다 — %s"
                  % (kind, ov_t.get("code")))

            # ② 저장(다른 슬롯) — 손상 slot이 지문 계산을 죽이면 안 된다(UNEXPECTED 금지).
            sv = rpc(main, "save_profile", "222", "internal")
            if not sv.get("ok") and sv.get("code") == "UNEXPECTED":
                P("★[%s] save_profile이 손상 meta에 UNEXPECTED로 죽었다" % kind)

            # ③ 삭제(#5 — test_delete_game ⑧-c와 중복이나 여기선 4종 전수로) — CONFIRM이 정상.
            dl = rpc(main, "delete_game", "222")
            if dl.get("code") != "CONFIRM_REQUIRED":
                P("★[%s] delete_game이 손상 meta에 CONFIRM_REQUIRED를 못 냈다 — %s" % (kind, dl.get("code")))

            # 다음 케이스를 위해 정리(삭제 확인 안 했으니 수동 제거).
            reg = store.load_registry()
            reg["games"].pop("222", None)
            store.save_registry(reg)
            shutil.rmtree(store.profiles_root("222"), ignore_errors=True)

        if fails:
            print("FAIL — 손상 meta가 정상 경로를 죽였다:")
            for f in fails:
                print("  " + f)
            return 1
        print("PASS — 손상 meta 4종 × (현황 false/true · 저장 · 삭제) 전부 방어됨")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
