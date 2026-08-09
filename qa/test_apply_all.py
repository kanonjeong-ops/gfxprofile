#!/usr/bin/env python3
"""일괄 적용의 불변식 — **하나가 실패해도 나머지는 계속**한다.

M1의 핵심 약속이고(정본 5-A · QA 5라운드 R1), 설계 E1이 원안에서 되돌린 바로 그 규칙이다.
원안대로 "실행 중인 게임이 있으면 버튼 비활성"이면 **아무것도 적용되지 않는다.**

★ 이 테스트는 **합성 데이터**만 쓴다. 실사용 게임 설정 파일을 건드리지 않는다 —
  실데이터로 돌리면 그 게임의 현재 설정이 실제로 덮어써진다.
"""
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))


def build_world(tmp):
    """게임 3개짜리 합성 세계. 전부 tmp 안에 있어 실물과 무관하다."""
    os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)          # check_path의 홈 경계도 tmp로
    from gfxp import codes, engine, store              # 환경 설정 뒤에 import

    reg = store.default_registry()
    for n, appid in enumerate(("111", "222", "333"), start=1):
        cfg = tmp / ("game%d" % n) / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("quality=dock\nlines=%d\n" % n)
        engine.add_game(reg, appid, str(cfg), name="Game%d" % n)
        engine.save_profile(reg, appid, "dock")        # 지금 내용을 dock으로 저장
        cfg.write_text("quality=internal\nlines=%d\n" % n)
        engine.save_profile(reg, appid, "internal")    # 바꾼 내용을 internal로
    store.save_registry(reg)
    return engine, store, reg


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-apply-"))
    try:
        engine, store, reg = build_world(tmp)
        from gfxp import codes                      # 경로 설정 뒤라 여기서 import한다
        problems = []

        # 1) 전부 dock으로 — 디스크는 지금 internal이므로 3개 다 applied여야 한다
        rows = engine.apply_all(reg, "dock")
        outcomes = [r["outcome"] for r in rows]
        if outcomes != ["applied"] * 3:
            problems.append(f"1차 일괄 적용: 기대 3×applied / 실제 {outcomes}")

        # 2) 같은 프로필 재적용 — 디스크가 이미 그 프로필이므로 전부 already (쓰기 없음)
        rows = engine.apply_all(reg, "dock")
        outcomes = [r["outcome"] for r in rows]
        if outcomes != ["already"] * 3:
            problems.append(f"재적용: 기대 3×already / 실제 {outcomes}")

        # 3) ★ 불변식 — 하나가 실패해도 나머지는 계속한다.
        #    ⚠️ 파일을 **지우는 것은 실패가 아니다** — atomic_write가 새로 만들어 복구해 준다
        #    (첫 시도에서 이걸 몰라 테스트가 거짓 FAIL을 냈다). 실제로 쓰기가 막히게 만든다:
        #    폴더에서 쓰기 권한을 뺀다.
        os.chmod(tmp / "game2", 0o500)
        rows = engine.apply_all(reg, "internal")
        by_id = {r["appid"]: r["outcome"] for r in rows}
        if by_id.get("222") == "applied":
            problems.append("실패해야 할 게임이 적용됐다")
        if by_id.get("111") != "applied" or by_id.get("333") != "applied":
            problems.append(f"하나가 실패하자 나머지가 멈췄다 — {by_id}  ★불변식 위반")
        if len(rows) != 3:
            problems.append(f"결과 행이 3개가 아니다({len(rows)}) — 무엇이 안 됐는지 알 수 없다")

        # 4) 실패한 게임의 사유가 결과에 실린다 (화면에 보여줄 수 있어야 한다)
        os.chmod(tmp / "game2", 0o700)          # 정리할 수 있게 되돌린다
        row222 = next(r for r in rows if r["appid"] == "222")
        # ★ 2026-08-06: `code or note`는 너무 느슨했다(외부 검증 반증 2).
        #   화면은 **`code`로** "조치가 같은 것"과 "게임마다 다른 것"을 가른다 — `note`(한국어 자유문)로는
        #   못 가른다. 그러니 `code`가 **반드시** 있어야 하고, 그것이 없으면 화면이 오정보를 낸다.
        if not row222.get("code"):
            problems.append("실패 행에 code가 없다 — 화면이 사유를 구분할 수 없다(오정보의 원인)")
        elif row222["code"] != codes.UNEXPECTED:
            problems.append(f"권한 오류는 UNEXPECTED여야 하는데 {row222['code']}가 왔다")
        if not row222.get("note"):
            problems.append("실패 행에 note가 없다 — 로그에 남길 사유가 사라진다")

        # 5) 정상 행에는 code가 없다 — 있으면 화면이 정상을 문제로 분류한다
        for rid in ("111", "333"):
            r = next(x for x in rows if x["appid"] == rid)
            if r.get("code"):
                problems.append(f"{rid}는 성공인데 code가 실렸다({r['code']}) — 화면이 문제로 센다")

        print(f"합성 게임 3개 / 시나리오 4종  (데이터: {tmp})")
        print(f"  1차={['applied']*3} 재적용=already×3 "
              f"실패격리={by_id} 사유={row222.get('code') or row222.get('note','')[:30]}")
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
    sys.exit(main())
