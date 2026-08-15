#!/usr/bin/env python3
"""백업 링의 **순서 계약** — 오래된 것부터 사라진다 (R14 #3).

화면과 문서가 사용자에게 약속하는 문장은 하나다: *"백업 칸이 차면 **오래된 것부터** 밀려난다."*
그런데 2026-08-15 이전의 `store`는 링을 **파일명 사전순**으로 잘랐고, 같은 초에 만들어진 백업의
충돌 접미사는 문자열 비교에서 `-10-` < `-2-`가 된다. 그래서 같은 초에 12건이 쌓이면 남는 것이
`-9-,…,-2-,-12-,-11-`이었고 **열 번째로 만든 백업이 두 번째 것보다 먼저 잘려 나갔다.**
`make_backup`은 그때 **이미 지워진 경로를 성공값으로** 돌려주기까지 했다.

이 파일이 잠그는 것:
  ⓐ 같은 초에 `BACKUP_KEEP`을 넘겨 만들면 **가장 나중에 만든 KEEP건이 남는다**(생성 순서 = 진실)
  ⓑ `prune_backups(protect=…)`는 **그 파일을 절대 안 지운다** — 방금 쓴 파일이 그 자리에서
     잘리지 않는다는 불변식이다(`make_backup`이 **이미 지워진 경로**를 성공값으로 돌려주던 자리).
     ⚠️ 정직하게: 지금 구현에서는 순서 키(단조 seq)만으로도 새 파일이 맨 앞이라 이 인자가
       없어도 결과가 같다. 그래서 **이 절은 `prune_backups`를 직접 불러** 인자 계약을 잰다 —
       그러지 않으면 "FAIL하는 입력이 없는 검사"가 된다.
  ⓒ `list_backups`는 **최신 → 오래된 순**이고, prune은 그 꼬리를 자른다
  ⓓ **옛 이름과 섞여도** 순서가 유지된다(명명 규칙을 안 바꿨다는 사실의 잠금 — 마이그레이션 없음)
  ⓔ 음성 대조군: **사전 역순**은 이 픽스처에서 다른 답을 낸다(그래서 위 단언들이 항진식이 아니다)

★ 합성 데이터만 쓴다 — `GFXPROFILE_DATA_DIR`이 tmp라 실사용 데이터에 닿을 수 없다.
★ 같은 초를 **강제하지 않는다**: 12건을 그냥 만들면 초가 넘어갈 수 있어 픽스처가 무효가 된다.
  그래서 `time.strftime`을 **고정 stamp로 묶어**(계측기) 같은 초를 재현한다 — 파일 상태는
  전부 정상 API(`store.make_backup`)가 만든다.
"""
import os
import pathlib
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPID = "4242"
STAMP = "20260815-070000"


def main_test():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-ring-order-"))
    try:
        os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
        os.environ["GFXPROFILE_HOME"] = str(tmp)
        sys.path.insert(0, str(ROOT / "py_modules"))
        from gfxp import store                                        # noqa: E402
        problems = []

        def P(msg):
            problems.append(msg)

        def names():
            return [os.path.basename(p) for p in store.list_backups(APPID)]

        # ── 계측기: 같은 초를 재현한다 (make_backup의 stamp만 고정) ───────────
        real_strftime = time.strftime

        def frozen(fmt, *args):
            return STAMP if fmt == "%Y%m%d-%H%M%S" else real_strftime(fmt, *args)

        time.strftime = frozen
        try:
            # ── ⓐⓑ 같은 초에 KEEP+2건 ─────────────────────────────────────
            made = []
            for i in range(store.BACKUP_KEEP + 2):
                path = store.make_backup(APPID, b"body-%02d\n" % i, "disk", "video.ini")
                made.append(os.path.basename(path))
                if not os.path.exists(path):
                    P("★make_backup이 **이미 지워진 경로**를 돌려줬다 — %s (%d번째)"
                      % (os.path.basename(path), i))
            if len(set(made)) != len(made):
                P("사전 조건 실패 — 같은 이름을 두 번 만들었다(덮어쓰기) %s" % made)
            if len(names()) != store.BACKUP_KEEP:
                P("사전 조건 실패 — 링이 %d건이다(기대 %d)" % (len(names()), store.BACKUP_KEEP))
            expected_survivors = made[-store.BACKUP_KEEP:]
            if names() != list(reversed(expected_survivors)):
                P("★ⓐ/ⓒ 남은 백업이 **생성 순서의 최신 %d건**이 아니다\n"
                  "      남음(최신순)=%s\n      기대       =%s\n      만든 순서   =%s"
                  % (store.BACKUP_KEEP, names(), list(reversed(expected_survivors)), made))
            gone = [n for n in made if n not in names()]
            if gone != made[:2]:
                P("★ⓐ 잘려 나간 것이 **가장 먼저 만든 2건**이 아니다 — 잘림=%s (기대 %s)"
                  % (gone, made[:2]))

            # ── ⓑ `protect`는 **꼬리에 있어도** 살아남는다 ────────────────
            #    링을 KEEP+2로 만들어 두고, **가장 오래된 것**을 protect로 지정해 부른다.
            #    보호가 없으면 그것부터 잘린다 — 그래서 이 절은 인자를 지우는 변이에서 FAIL한다.
            shutil.rmtree(store.backups_dir(APPID), ignore_errors=True)
            os.makedirs(store.backups_dir(APPID), exist_ok=True)
            for i in range(store.BACKUP_KEEP + 2):
                name = ("%s-disk-video.ini" % STAMP if i == 0
                        else "%s-disk-%d-video.ini" % (STAMP, i))
                with open(os.path.join(store.backups_dir(APPID), name), "wb") as fh:
                    fh.write(b"guard-%02d\n" % i)
            oldest = store.list_backups(APPID)[-1]
            store.prune_backups(APPID, protect=oldest)
            if os.path.basename(oldest) not in names():
                P("★ⓑ protect로 지정한 파일이 지워졌다 — %s (남음=%s)"
                  % (os.path.basename(oldest), names()))
            if len(names()) != store.BACKUP_KEEP:
                P("★ⓑ protect가 링 크기를 바꿨다 — %d건(기대 %d)" % (len(names()), store.BACKUP_KEEP))
            shutil.rmtree(store.backups_dir(APPID), ignore_errors=True)
            for i in range(store.BACKUP_KEEP + 2):     # ⓐ의 상태를 되돌려 아래 절이 잇게 한다
                store.make_backup(APPID, b"body-%02d\n" % i, "disk", "video.ini")

            # ── ⓔ 음성 대조군: 사전 역순은 다른 답을 낸다 ──────────────────
            lex = sorted(names(), reverse=True)
            if lex == names():
                P("★ⓔ 음성 대조군 무효 — 사전 역순이 우연히 같다. 이 픽스처로는 정렬 결함을 못 잡는다")

            # ── ⓓ 옛 이름과 섞기 ─────────────────────────────────────────
            #   명명 규칙은 R14에서 **바꾸지 않았다**(기존 사용자 기기의 백업이 그대로 읽혀야
            #   한다). 그래서 "옛 파일"은 같은 규칙으로 만들어진 파일이고, 이 절은 그 사실을
            #   *다른 초*(더 이른 stamp)의 파일을 섞어 확인한다 — 더 오래된 것이 먼저 잘린다.
            shutil.rmtree(store.backups_dir(APPID), ignore_errors=True)
            older = []
            for i in range(4):                       # 옛 초의 파일 4건(seq 0~3)
                name = ("20260101-000000-disk-video.ini" if i == 0
                        else "20260101-000000-disk-%d-video.ini" % i)
                os.makedirs(store.backups_dir(APPID), exist_ok=True)
                with open(os.path.join(store.backups_dir(APPID), name), "wb") as fh:
                    fh.write(b"old-%02d\n" % i)
                older.append(name)
            fresh = []
            for i in range(store.BACKUP_KEEP - 2):   # 새 초의 파일로 링을 넘긴다
                fresh.append(os.path.basename(
                    store.make_backup(APPID, b"new-%02d\n" % i, "disk", "video.ini")))
            survivors = names()
            if survivors[-1] != older[2]:
                P("★ⓓ 옛 이름이 섞이자 최고령 판정이 틀렸다 — 꼬리=%s (기대 %s)\n      전체=%s"
                  % (survivors[-1], older[2], survivors))
            if any(n in survivors for n in older[:2]):
                P("★ⓓ 옛 파일 중 **가장 오래된 2건**이 안 잘렸다 — %s" % survivors)
            if [n for n in fresh if n not in survivors]:
                P("★ⓓ 새로 만든 백업이 옛 파일보다 먼저 잘렸다 — %s"
                  % [n for n in fresh if n not in survivors])
            # 옛 이름끼리도 seq 순서가 지켜지는가(사전순이면 `-1-`이 접미사 없는 것보다 앞선다)
            if sorted(survivors, reverse=True) == survivors:
                P("★ⓓ 음성 대조군 무효 — 이 혼합 픽스처에서도 사전 역순이 같은 답을 낸다")
        finally:
            time.strftime = real_strftime

        print("백업 링 순서 — 같은 초 %d건 · 옛 이름 혼합 (데이터: %s)"
              % (store.BACKUP_KEEP + 2, tmp))
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
