#!/usr/bin/env python3
"""`confirm.needs_confirm`을 M1 `ui_tk._confirm_overwrite`에서 옮긴 기대표와 대조한다.

M1 코드를 읽지는 않는다. 이 파일이 직접 강제하는 것은 일곱 시나리오의 `need`, 지정한
`disk_state`·`note`, 1·2행의 빈 params, 그리고 지문의 진릿값이다.

| # | 입력 | M1 | 이 파일이 확인하는 값 |
|---|---|---|---|
| 1 | 기존 meta 없음(빈 슬롯) | True(진행) | `need=False`, 빈 params |
| 2 | 디스크 sha1 == meta sha1 | True(진행) | `need=False`, 빈 params |
| 3 | 내용 다름 | 확인창 | `need=True`, 세 `disk_state` 갈래와 표시 키 |
| 4 | `load_meta` 예외(손상) | True(진행) | `need=False`, `note=META_UNREADABLE` |
| 5 | `disk_state` 예외 | 확인창 | `need=True`, `disk_state=lookup_failed` |

M1의 True는 "저장을 진행하라", 여기의 True는 "물어야 한다"라 부호가 반대다.
합성 데이터만 쓴다.
"""
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

APPID = "666"
BASE = b"quality=base\nshadows=high\ndetail=ultra\n"
OTHER = b"quality=other\nshadows=none\ndetail=low__\n"


def world(tmp):
    os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    from gfxp import confirm, engine, store
    cfg = tmp / "game" / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(BASE)
    reg = store.default_registry()
    engine.add_game(reg, APPID, str(cfg), name="EquivTarget")
    return confirm, engine, store, reg, cfg


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-equiv-"))
    try:
        confirm, engine, store, reg, cfg = world(tmp)
        problems = []
        seen = []

        def check(label, expect_need, expect_state=None, expect_note=None):
            # 판정 함수는 지문까지 함께 낸다 — 묻는 갈래에서만이고 나머지는 None이다.
            # 여기서 잠그는 것은 동치표라 지문은 유효성만 본다.
            need, params, fp = confirm.needs_confirm(reg, APPID, "dock")
            seen.append(label)
            if bool(fp) != bool(need):
                problems.append(f"[{label}] 지문이 need={need}와 어긋난다(fp={fp!r}) — "
                                f"★묻는 갈래에는 지문이 있어야 하고, 안 묻는 갈래는 잴 것이 없다")
            if need != expect_need:
                problems.append(f"[{label}] need={need} (기대 {expect_need}) "
                                f"★부호가 뒤집혔거나 분기가 빠졌다")
            if expect_state is not None and params.get("disk_state") != expect_state:
                problems.append(f"[{label}] disk_state={params.get('disk_state')!r} "
                                f"(기대 {expect_state!r})")
            if expect_note is not None and params.get("note") != expect_note:
                problems.append(f"[{label}] note={params.get('note')!r} (기대 {expect_note!r})")
            # 안 물을 때 확인창 재료를 실어 보내면 프론트가 그것을 그릴 수 있게 된다
            if not need and expect_note is None and params:
                problems.append(f"[{label}] 안 묻는데 params가 비어 있지 않다({params})")
            return params

        # ── 1) 빈 슬롯 — 잃을 것이 없다 ───────────────────────────────────────
        check("빈 슬롯", False)

        # ── 2) 디스크 == 프로필 ───────────────────────────────────────────────
        engine.save_profile(reg, APPID, "dock")
        check("내용 동일", False)

        # ── 3) 내용 다름 — 어느 프로필과도 안 맞음(게임에서 조정) ──────────────
        cfg.write_bytes(OTHER)
        p = check("내용 다름(unknown)", True, expect_state=confirm.UNKNOWN)
        for key in ("size", "sha1_short", "saved_at"):
            if key not in p:
                problems.append(f"확인창 재료에 {key}가 없다 — 무엇을 잃는지 못 보여준다")

        # ── 3-b) 다른 프로필과 일치 ───────────────────────────────────────────
        engine.save_profile(reg, APPID, "internal")     # internal = OTHER
        p = check("다른 프로필과 일치", True, expect_state=confirm.OTHER_PROFILE)
        if p.get("matched_profile") != "internal":
            problems.append(f"matched_profile={p.get('matched_profile')!r} — 어느 프로필인지 못 말한다")

        # ── 3-c) 설정 파일이 없다 ─────────────────────────────────────────────
        cfg.unlink()
        check("설정 파일 없음", True, expect_state=confirm.MISSING)
        cfg.write_bytes(OTHER)

        # ── 4) meta 손상 — 안 묻고 진행하고, 저장 쪽에서 실패한다 ─────────────
        meta_path = pathlib.Path(store.profile_meta_path(APPID, "dock"))
        good = meta_path.read_bytes()
        meta_path.write_bytes(b"{ not json at all")
        check("meta 손상", False, expect_note="META_UNREADABLE")
        meta_path.write_bytes(good)

        # ── 5) disk_state 조회 실패 → lookup_failed (missing과 갈라야 한다) ───
        real = engine.disk_state

        def boom(*_a, **_k):
            raise OSError("synthetic lookup failure")

        engine.disk_state = boom
        try:
            check("조회 실패", True, expect_state=confirm.LOOKUP_FAILED)
        finally:
            engine.disk_state = real

        # 갈래 수를 못박는다 — 위 check 호출이 지워지면 여기서 걸린다.
        # (호출은 전부 무조건 실행되므로 실행 중에 이 수가 줄어들 수는 없다.)
        if len(seen) < 7:
            problems.append(f"분기를 {len(seen)}개만 돌았다(7개여야 한다) — 검사가 헐거워졌다")
        # 4분류는 서로 다른 값이어야 한다. 합치면 프론트가 문구를 고를 수 없다.
        states = {confirm.OTHER_PROFILE, confirm.UNKNOWN, confirm.MISSING, confirm.LOOKUP_FAILED}
        if len(states) != 4:
            problems.append(f"disk_state 4분류가 서로 다르지 않다({states}) — 두 뜻이 한 값에 뭉쳤다")

        print(f"needs_confirm 분기 {len(seen)}종 (M1 동치표 5행 + disk_state 4분류)")
        print("  " + " / ".join(seen))
        if problems:
            print("\nFAIL")
            for x in problems:
                print("  " + x)
            return 1
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
