#!/usr/bin/env python3
"""내용이 같은 저장은 슬롯과 백업 링을 바꾸지 않는다.

무쓰기 분기가 없으면 디스크 내용과 슬롯 내용이 같아도 엔진이 이전 본체를 대피시키고
프로필을 다시 쓴다. 이 파일은 route를 호출하되 슬롯과 백업 링만 스냅샷한다. route가
마지막에 저장하는 레지스트리까지 포함한 전역 무쓰기는 재지 않는다.

### 재는 방법 — 슬롯의 (이름, inode, mtime_ns, sha1) + 백업 링의 (이름, sha1) 집합
sha1만 보면 같은 바이트 재기록을 통과시킨다. `store.atomic_write`는 임시 파일을 교체하므로
inode·mtime_ns를 함께 잰다. `saved_at` 값이 달라지면 meta sha1도 달라지지만, 같은 초의
재기록은 inode·mtime_ns로 잡는다. 링은 집합으로 재서 추가와 축출을 함께 잡는다.

### 음성 대조군
무쓰기 분기를 뺀 엔진을 꽂으면 ①의 슬롯 또는 링 스냅샷이 반드시 달라져야 한다.

### 같이 재는 것
슬롯 본체가 깨졌거나 사라졌으면 기록상 sha1이 같아도 다시 쓰고, 깨진 본체를 대피하는
갈래는 확인 뒤에 실행한다. ④는 확인 요구, 확인 전 링 불변, 승인 뒤 저장과 복구를 잰다.

합성 데이터만 쓴다 — `GFXPROFILE_HOME`·`DECKY_PLUGIN_RUNTIME_DIR`이 tmp라 실사용 데이터에
닿을 수 없다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPID = "777"
BASE = b"quality=base\nshadows=high\ndetail=ultra\n"
OTHER = b"quality=othr\nshadows=none\ndetail=low__\n"


def boot(tmp):
    def sink(fmt="", *args, **kwargs):
        return None

    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(info=sink, warning=sink, error=sink, debug=sink,
                                        log=lambda level, fmt="", *a, **k: None)
    sys.modules["decky"] = fake
    os.environ["DECKY_PLUGIN_RUNTIME_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "py_modules"))
    import main                                                  # noqa: E402
    return main


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def slot_state(store, appid, profile):
    """슬롯 디렉터리의 (이름, inode, mtime_ns, sha1) — `meta.json` 포함(saved_at이 여기 있다)."""
    directory = store.profile_dir(appid, profile)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    rows = []
    for name in names:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        info = os.stat(path)
        rows.append((name, info.st_ino, info.st_mtime_ns, store.sha1_file(path)))
    return rows


def ring_state(store, appid):
    """백업 링의 (이름, sha1) 집합. 추가도 축출도 이 집합을 바꾼다."""
    return sorted((os.path.basename(p), store.sha1_file(p)) for p in store.list_backups(appid))


def oldest(store, appid):
    """`store.list_backups` 정렬의 마지막 백업 파일명."""
    entries = store.list_backups(appid)
    return os.path.basename(entries[-1]) if entries else None


def fill_ring(store, appid, filename):
    """링을 가득 채운다 — 1건만 더 쌓여도 정렬 꼬리가 잘릴 상태를 만든다."""
    for i in range(store.BACKUP_KEEP):
        store.make_backup(appid, b"filler-%03d\n" % i, "disk", filename)


def main_test():                                                # noqa: C901  (갈래 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-save-nowrite-"))
    try:
        main = boot(tmp)
        from gfxp import engine, store
        problems = []

        def P(msg):
            problems.append(msg)

        cfg = tmp / "game" / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(BASE)
        reg = store.default_registry()
        engine.add_game(reg, APPID, str(cfg), name="SaveNoWrite")
        store.save_registry(reg)

        # 첫 저장(빈 슬롯) — 여기까지는 당연히 쓴다. 이후의 기준선이 된다.
        env = rpc(main, "save_profile", APPID, "dock")
        if not env.get("ok") or (env.get("data") or {}).get("outcome") != "saved":
            P("사전 조건: 빈 슬롯 첫 저장이 outcome=saved로 끝나지 않았다 (%s)" % env)
        fill_ring(store, APPID, "video.ini")

        # ── ① 내용이 같은 저장 — 무쓰기 ───────────────────────────────────────
        before_slot = slot_state(store, APPID, "dock")
        before_ring = ring_state(store, APPID)
        before_oldest = oldest(store, APPID)
        env = rpc(main, "save_profile", APPID, "dock")
        after_slot = slot_state(store, APPID, "dock")
        after_ring = ring_state(store, APPID)

        if not env.get("ok"):
            P("① 내용이 같은 저장이 실패했다 — 묻지 않고 성공해야 한다 (%s)" % env)
        if (env.get("data") or {}).get("outcome") != "already":
            P("① 봉투의 outcome이 already가 아니다 — 화면이 사실을 말할 근거가 없다 (%s)" % env)
        if before_slot != after_slot:
            P("★① 무쓰기라는데 슬롯이 움직였다(saved_at 갱신·재기록)\n      전=%s\n      후=%s"
              % (before_slot, after_slot))
        if before_ring != after_ring:
            P("★① 무쓰기라는데 백업 링이 돌았다 — 최고령 복구 지점이 밀려난다\n"
              "      전 %d건 / 후 %d건\n      사라진=%s\n      생긴=%s"
              % (len(before_ring), len(after_ring),
                 sorted(set(before_ring) - set(after_ring)),
                 sorted(set(after_ring) - set(before_ring))))
        if oldest(store, APPID) != before_oldest:
            P("★① 최고령 백업이 바뀌었다 (%s → %s)" % (before_oldest, oldest(store, APPID)))

        # ── ② 음성 대조군: 무쓰기 분기를 제거한 엔진에서는 ①이 FAIL해야 한다 ──
        def legacy_save(reg_, appid_, profile_):
            """무쓰기 분기가 없던 시절의 재현 — 내용이 같아도 대피본을 만들고 다시 쓴다."""
            entry = engine.game_or_fail(reg_, str(appid_))
            path = entry["config_path"]
            data = store.read_bytes(path)
            old = store.load_meta(str(appid_), profile_)
            if old:
                old_file = store.profile_file_path(str(appid_), profile_)
                if old_file and os.path.exists(old_file):
                    store.make_backup(str(appid_), store.read_bytes(old_file),
                                      "profile_%s" % profile_, old["filename"])
            meta = store.write_profile(str(appid_), profile_, os.path.basename(path),
                                       data, src=path)
            return {"meta": meta, "warning": None, "outcome": "saved"}

        real_save = engine.save_profile
        engine.save_profile = legacy_save
        try:
            probe_slot_before = slot_state(store, APPID, "dock")
            probe_ring_before = ring_state(store, APPID)
            probe_oldest_before = oldest(store, APPID)
            rpc(main, "save_profile", APPID, "dock")
            probe_slot_after = slot_state(store, APPID, "dock")
            probe_ring_after = ring_state(store, APPID)
            probe_oldest_after = oldest(store, APPID)
        finally:
            engine.save_profile = real_save
        if probe_slot_before == probe_slot_after and probe_ring_before == probe_ring_after:
            P("★음성 대조군 무효 — 무쓰기 분기를 뗀 엔진에서도 슬롯·링이 그대로로 보였다. "
              "이 검사는 아무것도 재지 않는다")
        if probe_oldest_before == probe_oldest_after:
            P("★음성 대조군 무효 — 가득 찬 링에 1건이 쌓였는데 최고령이 그대로다. "
              "링 축출을 재는 계측기가 고장 났다")

        # ── ③ 진짜로 달라진 저장은 여전히 쓴다(무쓰기가 저장을 죽이지 않았다) ──
        cfg.write_bytes(OTHER)
        env = rpc(main, "save_profile", APPID, "dock")        # 덮어쓰기 → 확인 요구
        token = (env.get("params") or {}).get("confirm_token")
        if not token:
            P("③ 덮어쓰기인데 확인 토큰이 안 왔다 (%s)" % env)
        before_slot = slot_state(store, APPID, "dock")
        env = rpc(main, "save_profile", APPID, "dock", confirm_token=token)
        if not env.get("ok") or (env.get("data") or {}).get("outcome") != "saved":
            P("③ 내용이 달라진 저장이 실행되지 않았다 (%s)" % env)
        if slot_state(store, APPID, "dock") == before_slot:
            P("★③ 저장했다는데 슬롯이 그대로다 — 무쓰기 분기가 정상 저장까지 삼켰다")
        if (store.load_meta(APPID, "dock") or {}).get("sha1") != store.sha1_bytes(OTHER):
            P("③ 저장 뒤 슬롯 내용이 디스크와 다르다")

        # ── ④ 슬롯 본체가 깨졌으면 기록이 같아도 쓴다 — 단 묻고 쓴다 ─────
        #
        # 여기가 정책층과 엔진의 술어가 갈리던 자리다. `meta.sha1`은 디스크와 같은데 본체가
        #   다른 상태는 `write_profile`이 본체를 먼저 쓰고 meta를 나중에 쓰므로 실제로 생긴다.
        #   기록만 보는 판정은 "이미 같다"며 안 묻는데 엔진은 본체 실측으로 대피·쓰기·축출을
        #   실행한다 — 확인창 없이 포화 링의 정렬 꼬리가 사라진다.
        #   그래서 이 갈래가 재는 것은 둘이다: ⓐ 자가 복구 경로가 살아 있다(쓴다)
        #   ⓑ 그 쓰기가 고지 뒤에 일어난다(대피가 링을 태우므로).
        body = store.profile_file_path(APPID, "dock")
        with open(body, "wb") as fh:
            fh.write(b"corrupted-body\n")                     # meta의 sha1과 어긋난다
        broken_sha1 = store.sha1_file(body)
        ring_before = ring_state(store, APPID)
        env = rpc(main, "save_profile", APPID, "dock")
        token = (env.get("params") or {}).get("confirm_token")
        if env.get("code") != "CONFIRM_REQUIRED" or not token:
            P("★④ 본체가 깨진 슬롯을 **묻지 않고** 처리했다 — 대피가 링을 태우는데 고지가 없다 "
              "(%s)" % env)
        else:
            if ring_state(store, APPID) != ring_before:
                P("★④ 확인을 요구하면서 링이 이미 움직였다 — 묻기 전에 쓴 것이다")
            env = rpc(main, "save_profile", APPID, "dock", confirm_token=token)
        if (env.get("data") or {}).get("outcome") != "saved":
            P("★④ 슬롯 본체가 깨졌는데 already로 넘어갔다 — 재저장으로 고칠 길이 사라진다 (%s)"
              % env)
        if store.sha1_file(body) != store.sha1_bytes(OTHER):
            P("★④ 깨진 슬롯이 복구되지 않았다")
        if broken_sha1 not in [sha for _name, sha in ring_state(store, APPID)]:
            P("★④ 깨진 본체가 대피되지 않았다 — 확인창은 잃을 것을 말하는데 실제로는 버렸다")

        # ── ⑤ 슬롯 본체가 사라졌으면 다시 만든다 ──────────────────────────
        os.unlink(body)
        env = rpc(main, "save_profile", APPID, "dock")
        if (env.get("data") or {}).get("outcome") != "saved":
            P("★⑤ 슬롯 본체가 없는데 already로 넘어갔다 — 빈 프로필이 영구히 남는다 (%s)" % env)
        if not os.path.exists(body):
            P("★⑤ 슬롯 본체가 다시 만들어지지 않았다")

        print("내용 동일 저장의 무쓰기 — 갈래 5종 + 음성 대조군 (데이터: %s)" % tmp)
        print("  링 %d칸 가득 상태에서 판정 · 최고령=%s" % (store.BACKUP_KEEP, before_oldest))
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
