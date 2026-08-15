#!/usr/bin/env python3
"""**복원 경로를 실제로 돌린다** — P4 착수 조건 ⑤(QA 이월, 2026-08-06).

왜 이 파일이 있나: P4는 **덮어쓰기**를 화면에 올리는 단계인데, QA 4라운드 동안
*"복원을 실제로 돌린 적이 한 번도 없었다."* **백업이 「있다」와 「복원해봤다」는 다르다.**
`save_profile`이 덮어쓰기 전에 `make_backup(tag="profile_<slot>")`을 부르는 줄(engine.py:443-447)이
있다는 것은 코드를 읽으면 알 수 있다. 그 줄이 **되돌릴 수 있는 무언가를 실제로 남기는지**는 다른 문제다.

여기서 증명하는 것은 **덮어쓴 프로필을 원래 바이트로 되돌릴 수 있다**는 것이고,
그 절차는 두 걸음이다(한 걸음이 아니다 — 이걸 몰라 절차를 잘못 안내하면 복구가 실패한다):

    ① restore_backup(profile_dock 백업)   →  **디스크**가 옛 프로필 내용이 된다
    ② save_profile(dock)                  →  그 디스크 내용이 **프로필 슬롯**으로 되돌아간다

`restore_backup(…)`은 **기본값(`target="config"`)에서는 프로필 슬롯에 쓰지 않는다.** 설정 파일에 쓴다.
①만 하고 멈추면 슬롯은 여전히 덮어쓴 내용이다.
(⚠️ R13부터 엔진은 `target="dock"|"internal"`도 받고, **화면의 [복원]은 프로필 백업 행에서 그쪽을
부른다** — 설계 §14-C. 그 경로는 `qa/test_restore_route.py` ⑨가 잰다. 이 파일이 잠그는 것은
**엔진의 2단계 절차 자체가 성립하는가**이고, 그 계약은 target 인자와 무관하게 유효하다.)

★ 이 테스트는 **합성 데이터**만 쓴다. 실사용 게임 설정 파일도 실사용 프로필도 건드리지 않는다.
"""
import os
import pathlib
import re
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

APPID = "444"
OLD = b"quality=ultra\nshadows=high\nsource=OLD-DOCK-PROFILE\n"
NEW = b"quality=low\nshadows=off\nsource=NEW-DOCK-PROFILE\n"


class _LaterClock:
    """`make_backup`의 타임스탬프만 **뒤 날짜로** 흘린다.

    왜 필요한가: 백업 링의 정렬 키는 파일명(=타임스탬프 접두어)이다. 실사용에서 적용은
    저장보다 **나중 시각**에 쌓이는데, 테스트가 전부 같은 초에 만들면 그 상황이 아니게 된다.
    15초를 실제로 기다리는 대신 시계만 앞당긴다 — 재는 대상은 시간이 아니라 **정렬·prune**이다.

    ⚠️ [2026-08-09 수리] 초판은 `"20260808-%06d"`라는 **날짜 리터럴**을 박아 두고 "저장 시점보다
      확실히 뒤"라고 적었다. 2026-08-09가 되자 그 날짜가 오히려 **앞**이 되어 대피본이 정렬
      맨 앞에 살아남았고, 이 절이 아무것도 못 재며 테스트가 통째로 FAIL했다(시한폭탄).
      **미래 시각을 실제 시계에서 파생**시키면 그 예외 자체가 생기지 않는다 — 리터럴을 다시
      박지 말 것.
    """

    #: 설정 단계의 실제 타임스탬프보다 확실히 뒤가 되게 하는 여유(초).
    _AHEAD = 3600

    def __init__(self, real):
        self._real = real
        self._n = 0
        self._base = real.time() + self._AHEAD

    def strftime(self, fmt, *args):
        if fmt == "%Y%m%d-%H%M%S":            # make_backup의 접두어일 때만 가로챈다
            self._n += 1                      # 호출마다 1초씩 — 링 안의 순서까지 결정된다
            return self._real.strftime(fmt, self._real.localtime(self._base + self._n))
        return self._real.strftime(fmt, *args)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _ui_warn_number():
    """화면이 사용자에게 말하는 숫자를 **소스에서 직접 읽는다.**

    테스트가 자기 상수를 들고 있으면 화면과 조용히 어긋난다 — 그게 QA 반려 ①의 형태였다.
    숫자는 `src/limits.ts` 한 곳에만 있고, 화면과 이 검사가 **같은 것을 본다.**
    """
    src = (ROOT / "src" / "limits.ts").read_text(encoding="utf-8")
    m = re.search(r"BACKUP_WARN_APPLIES\s*=\s*(\d+)", src)
    return int(m.group(1)) if m else None


def _measure_eviction(parent, plays_between):
    """**실제 `apply_profile`을 반복**해서 대피본이 몇 회 만에 링 밖으로 밀리는지 잰다.
    밀리지 않으면 `None`을 돌려준다 — 그것도 **결과**다(아래 참조).

    `plays_between=True`면 매 적용 전에 게임이 설정 파일을 다시 쓴 상황을 만든다.
    **그쪽이 실사용이고, R13부터는 그쪽에서만 링이 밀린다.**

    ★★ R13(설계 §14-B): 적용은 게임 설정 파일이 **어느 슬롯과도 다를 때만** 대피본을 만든다.
      그래서 유휴(`plays_between=False`)에서는 A↔B를 아무리 왕복해도 링이 **한 칸도 안 밀린다** —
      디스크가 언제나 직전에 적용한 슬롯과 같기 때문이다. 12판까지는 그 왕복마다 1건씩 쌓였고,
      G3 체크인이 있던 시절에는 실사용에서 2건씩 쌓였다.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-evict-", dir=str(parent)))
    for name in [k for k in list(sys.modules) if k.startswith("gfxp")]:
        del sys.modules[name]
    os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    from gfxp import engine, store

    cfg = tmp / "game" / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(OLD)
    reg = store.default_registry()
    engine.add_game(reg, APPID, str(cfg), name="EvictTarget")
    engine.save_profile(reg, APPID, "dock")
    cfg.write_bytes(NEW)
    engine.save_profile(reg, APPID, "internal")
    # ⚠️ 크기를 원본과 비슷하게 유지한다 — G4 온전성 검사가 25~400% 밖을 거부한다
    #    (짧은 더미를 쓰다가 실제로 거부당했다: "기준의 16%")
    cfg.write_bytes(b"quality=third\nshadows=mid\nsource=THIRD-STATE-XX\n")
    engine.save_profile(reg, APPID, "dock")            # dock 덮어쓰기 → 대피본 생성
    keep = [p for p in store.list_backups(APPID)
            if "profile_dock" in os.path.basename(p)][0]

    real_time, store.time = store.time, _LaterClock(store.time)
    try:
        for i in range(40):
            if plays_between:
                # 게임이 자기 설정을 다시 썼다. 크기는 원본 대역 안에 둔다(G4).
                cfg.write_bytes(b"quality=played\nshadows=var\nsource=INGAME-%03d-X\n" % i)
            engine.apply_profile(reg, APPID, "internal" if i % 2 == 0 else "dock")
            if not os.path.exists(keep):
                return i + 1
        return None
    finally:
        store.time = real_time


def build_world(tmp):
    """게임 1개짜리 합성 세계. 전부 tmp 안에 있어 실물과 무관하다."""
    os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)          # check_path의 홈 경계도 tmp로
    from gfxp import engine, store                     # 환경 설정 뒤에 import

    cfg = tmp / "game" / "video.ini"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_bytes(OLD)
    reg = store.default_registry()
    engine.add_game(reg, APPID, str(cfg), name="RestoreTarget")
    store.save_registry(reg)
    return engine, store, reg, cfg


def profile_backups(store, appid):
    """`profile_*` 태그가 붙은 백업만 — `disk` 백업과 **한 링을 공유**한다."""
    return [p for p in store.list_backups(appid)
            if "-profile_" in os.path.basename(p)]


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-restore-"))
    try:
        engine, store, reg, cfg = build_world(tmp)
        from gfxp import codes
        problems = []

        # ---------------------------------------------------------- 1) 덮어쓰기
        engine.save_profile(reg, APPID, "dock")                 # 프로필 dock = OLD
        first = store.load_meta(APPID, "dock")
        cfg.write_bytes(NEW)
        engine.save_profile(reg, APPID, "dock")                 # 덮어쓴다 → dock = NEW
        second = store.load_meta(APPID, "dock")

        if first["sha1"] == second["sha1"]:
            problems.append("덮어쓰기가 안 일어났다 — 이 테스트가 재려던 상황에 닿지 못했다")

        # ---------------------------------------------------------- 2) 대피본이 실재하나
        backups = profile_backups(store, APPID)
        if len(backups) != 1:
            problems.append(f"profile_ 백업이 1개여야 하는데 {len(backups)}개 — 덮어쓴 프로필이 사라진다")
        elif store.sha1_bytes(store.read_bytes(backups[0])) != first["sha1"]:
            problems.append("대피본 내용이 덮어쓰기 전 프로필과 다르다 — 되돌려도 그 값이 아니다")

        # ---------------------------------------------------------- 3) ★ 실제로 복원한다
        # ①만으로는 부족하다는 것까지 같이 잰다 — 절차를 한 걸음으로 안내하면 복구가 실패한다.
        engine.restore_backup(reg, APPID, backups[0])           # ① 디스크 ← 옛 프로필
        if store.sha1_bytes(cfg.read_bytes()) != first["sha1"]:
            problems.append("① restore_backup 후 디스크가 옛 프로필 바이트가 아니다")
        if store.load_meta(APPID, "dock")["sha1"] != second["sha1"]:
            problems.append("① 단계가 프로필 슬롯까지 되돌렸다 — 문서의 2단계 절차 설명이 틀린 것이니 "
                            "테스트가 아니라 절차 안내를 고쳐야 한다")

        engine.save_profile(reg, APPID, "dock")                 # ② 슬롯 ← 디스크
        restored = store.load_meta(APPID, "dock")
        if restored["sha1"] != first["sha1"]:
            problems.append(f"★복원 실패 — 프로필이 원래 바이트로 안 돌아왔다 "
                            f"({restored['sha1'][:8]} != {first['sha1'][:8]})")
        if cfg.read_bytes() != OLD:
            problems.append("복원 후 디스크 내용이 원본과 바이트 동일하지 않다")

        # ---------------------------------------------------------- 4) G15 — 루트 밖 백업은 거부
        outside = tmp / "evil.ini"
        outside.write_bytes(b"quality=evil\n")
        try:
            engine.restore_backup(reg, APPID, str(outside))
            problems.append("데이터 루트 밖 경로를 복원했다 — G15가 안 걸린다")
        except Exception as exc:
            if getattr(exc, "code", None) != codes.BACKUP_OUT_OF_ROOT:
                problems.append(f"루트 밖 경로 거부 코드가 BACKUP_OUT_OF_ROOT가 아니다 — {exc!r}")

        # ---------------------------------------------------------- 5) ★ 링 밀림 — 실측한다
        # `disk` 백업과 `profile_*` 백업이 **BACKUP_KEEP 한 링을 공유**한다.
        # 적용은 가장 자주 눌리는 버튼이고 실제 적용마다 `disk` 백업이 하나씩 쌓인다.
        # → **덮어쓴 프로필의 유일한 사본이 밀려 사라질 수 있다.** 몇 번 만에 사라지는지를
        #   추정이 아니라 실측으로 남긴다. (엔진은 fence 대상이라 여기서 고칠 수 없다 — 기록이 목적)
        #
        # ⚠️ 첫 판은 **재려던 상황에 닿지 못했다**(2026-08-07). filler를 전부 같은 초에 만들었더니
        #    파일명이 `…-profile_dock-…` vs `…-disk-…`로 갈리고 역순 정렬에서 `p > d`라
        #    프로필 백업이 오히려 맨 앞에 살아남았다 — 15번을 밀어도 안 밀렸다.
        #    실사용은 적용이 **나중 시각**에 쌓이므로 그 상황이 아니다. 시각을 흘려서 재야 한다.
        #
        # ⚠️⚠️ [2026-08-07 QA 반려 ①] **첫 판은 이 절을 통째로 잘못 쟀다.**
        #   합성 `disk` 백업을 손으로 밀어서 **실제 적용 경로를 한 번도 안 탔다.** 그래서
        #   *"적용 1회 = 백업 1개"*라는 틀린 전제 위에서 10회라는 숫자가 나왔고, 그 숫자가
        #   **사용자 확인창에 그대로 실려 나갔다**(위험을 2배 낙관한 거짓 약속).
        #   → **실제 `apply_profile`을 돌려서 잰다.** 그리고 사용자에게 말하는 숫자와 대조한다.
        #
        # ★★ [R13 재작성] 기대값이 **반전됐다**(설계 §7-2 #2). 적용은 이제 디스크가 어느 슬롯과도
        #   다를 때만 대피본을 만든다(§14-B) — 그래서
        #     · 유휴(A↔B 왕복만)  → **한 칸도 안 밀린다**(`None`)  ← 0 소모가 새 계약이다
        #     · 실사용(게임이 재기록) → 1건/회로 밀린다
        #   *"G3 체크인이 백업을 더 민다"*는 옛 단언은 삭제했다 — 체크인 자체가 사라졌다(§14-A).
        #   방향 검사(화면 숫자 ≤ 실측)는 **그대로 남긴다**: 그것이 이 절의 존재 이유다.
        evicted = {}
        for label, plays in (("idle", False), ("real", True)):
            evicted[label] = _measure_eviction(tmp, plays)

        warn_n = _ui_warn_number()
        if evicted["idle"] is not None:
            problems.append(
                f"★유휴 왕복에서 대피본이 {evicted['idle']}회 만에 밀렸다 — R13은 「디스크가 어느 "
                f"슬롯과도 다를 때만 백업」이므로 **0 소모**여야 한다(§14-B가 무력화됐다)")
        if evicted["real"] is None:
            problems.append("실사용 경로에서도 대피본이 안 밀렸다 — 계측기가 아무것도 못 쟀다 "
                            "(이 절의 단언이 항진식이 된다)")
        elif warn_n is None:
            problems.append("UI 경고 숫자(BACKUP_WARN_APPLIES)를 src/limits.ts에서 못 읽었다 — "
                            "화면이 말하는 값과 대조할 수 없으면 이 검사는 무의미하다")
        elif warn_n > evicted["real"]:
            # ★ 방향이 중요하다. 화면 숫자가 실측보다 **크면** 사용자에게 안전을 과장한 것이다.
            #   작은 쪽(=일찍 경고)은 보수적이라 허용한다.
            problems.append(
                f"★확인창이 「{warn_n}번」이라고 말하는데 실사용 실측은 {evicted['real']}번이다 — "
                f"**사용자에게 안전을 과장하고 있다**(정보 없음보다 오정보가 나쁘다). "
                f"src/limits.ts의 BACKUP_WARN_APPLIES를 {evicted['real']} 이하로 내려라")

        print(f"합성 게임 1개 / 시나리오 5종  (데이터: {tmp})")
        print(f"  덮어쓰기 {first['sha1'][:8]}→{second['sha1'][:8]} / "
              f"복원 →{restored['sha1'][:8]} / G15 거부")
        print(f"  ★대피본 소멸까지 실제 적용: 유휴 {evicted['idle']}회 / "
              f"실사용(게임이 설정 재기록) {evicted['real']}회 — 화면 경고 {warn_n}회 "
              f"(BACKUP_KEEP={store.BACKUP_KEEP})")
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
