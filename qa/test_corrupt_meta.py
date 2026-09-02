#!/usr/bin/env python3
"""손상된 meta.json 하나가 현황·저장·삭제 전체를 UNEXPECTED로 무너뜨리지 않는지 본다.

유효 JSON 비객체 세 종은 `load_meta`가 그대로 돌려준다. 소비자는 이를 비어 있는 기록처럼
접거나 적용 불가로 처리한다. JSON 파싱·UTF-8 디코딩 실패는 다른 갈래다. 저장 route는
`ValueError`를 `PROFILE_META_CORRUPT`로 바꾼다.

이 테스트는 손상 4종마다 현황 두 경로의 성공, 저장의 UNEXPECTED 부재, 삭제 확인 응답을 잰다.
저장 성공이나 정확한 비-UNEXPECTED 실패 코드는 단언하지 않는다.

`store.profile_file_path`는 비객체 기록에서 여전히 TypeError를 낼 수 있지만, 여기서 도는 세
경로는 그 함수를 호출하지 않는다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 유효 JSON 비객체 3종 + 비JSON 1종 — 앞의 셋은 load_meta가 그대로 돌려주고, 넷째는 예외가 된다.
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
            # 매 케이스 깨끗한 게임 — 상태 누적 아티팩트를 피한다.
            reg = store.load_registry()
            reg["games"]["222"] = {"name": "H", "config_path": str(cfg)}
            engine.save_profile(reg, "222", "dock")
            store.save_registry(reg)
            # dock 슬롯의 meta.json을 손상시킨다(본체는 그대로 — meta만).
            with open(store.profile_meta_path("222", "dock"), "w", encoding="utf-8") as fh:
                fh.write(content)

            # ① 현황 탭 두 경로 — UNEXPECTED로 죽으면 안 된다.
            # 이 상태에서 슬롯은 「적용 불가」로 접힌다(`main._slot_view`가 비-dict 기록을 거른다)
            #    — 그래서 적용 갈래의 `PROFILE_CORRUPT`에는 이 파일이 닿지 않는다.
            ov_f = rpc(main, "get_overview")
            if not ov_f.get("ok"):
                P("[%s] get_overview(detail=false)가 손상 meta에 죽었다 — %s" % (kind, ov_f.get("code")))
            ov_t = rpc(main, "get_overview", True)               # 게임 목록 화면이 쓰는 경로
            if not ov_t.get("ok"):
                P("★[%s] get_overview(detail=true=현황 탭)가 손상 meta 하나로 통째 죽었다 — %s"
                  % (kind, ov_t.get("code")))

            # ② 저장(다른 슬롯) — 손상 슬롯 때문에 UNEXPECTED가 나지 않는지만 본다.
            #    저장 성공이나 그 밖의 실패 코드는 이 파일이 판정하지 않는다.
            sv = rpc(main, "save_profile", "222", "internal")
            if not sv.get("ok") and sv.get("code") == "UNEXPECTED":
                P("★[%s] save_profile이 손상 meta에 UNEXPECTED로 죽었다" % kind)

            # ③ 삭제 — `test_delete_game` ⑧-c와 겹치지만 여기서는 4종 전수로 건다. CONFIRM이 정상.
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
