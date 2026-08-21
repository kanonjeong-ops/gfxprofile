#!/usr/bin/env python3
"""**내용이 같은 저장은 한 바이트도 쓰지 않는다** — R13 신설 (설계 §14-B 링 보존 · §4-I).

R13 이전의 `engine.save_profile`은 디스크 내용 == 프로필 내용이어도 그대로 실행됐다:
`confirm.needs_confirm`이 *"달라지는 게 없다"*며 **묻지 않고** 통과시키면, 엔진이 이전 프로필을
대피시키고(=게임당 10칸 링을 1칸 회전 → **최고령 복구 지점 소멸**) `saved_at`을 갱신했다.
사용자 쪽에서 보면 **아무것도 안 바뀌는 동작이 복구 지점 하나를 조용히 먹는** 것이라,
"손실 가능 행동은 인지시키고 묻는다"는 원칙의 정면 위반이다(적용은 이미 `already` 무쓰기다).

### 재는 방법 — 슬롯 (이름·inode·mtime_ns·sha1) + 백업 링의 (이름, sha1) 집합
`sha1`만 보면 **같은 바이트를 다시 쓴 경우**를 통과시킨다(정확히 이 결함의 형태다).
`store.atomic_write`은 tmp→rename이라 **inode가 바뀌므로** inode·mtime_ns를 같이 재면 잡힌다.
`meta.json`도 같은 잣대로 재므로 `saved_at` 갱신은 그 파일의 sha1 변화로 드러난다.
백업 링은 **집합**으로 잰다 — 링이 가득 찬 상태에서 1건이 늘면 최고령 1건이 잘려 나가므로
개수만으로는 안 드러나고, 집합이면 「추가」와 「축출」이 둘 다 걸린다.

### 음성 대조군 — 무쓰기 분기를 **제거한 엔진**을 꽂으면 반드시 FAIL해야 한다
그렇지 않으면 이 파일은 아무것도 재지 않는 것이다(이 프로젝트의 새 검사 인증 관례).

### 같이 잠그는 것 — **무쓰기가 복구 경로를 막지 않는다**
슬롯 본체가 깨졌거나 사라졌으면 기록상 sha1이 같아도 **실제로 쓴다.** meta만 믿고 넘어가면
"다시 저장해서 고친다"는 유일한 자가 복구 경로가 사라진다.

### 같이 잠그는 것 2 — **그 쓰기는 「고지 뒤에」 일어난다** (QA R1 D-1, 2026-08-22)
본체가 깨진 슬롯의 재저장은 깨진 본체를 대피시키므로 **가득 찬 링의 최고령 복구 지점을 태운다.**
그런데 판정층(`confirm.needs_confirm`)이 기록만 보면 *"이미 같다"*며 안 묻고, 엔진은 본체 실측으로
다르다며 실행했다 — **확인창이 한 번도 안 뜬 채** 백업이 하나 사라지는 갈래였다. 아래 ④는
「쓴다」와 「묻고 쓴다」를 **둘 다** 잰다(묻기 전에 링이 움직이지 않는 것까지).

★ 합성 데이터만 쓴다 — `GFXPROFILE_HOME`·`DECKY_PLUGIN_RUNTIME_DIR`이 tmp라 실사용 데이터에
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
    """최고령 백업의 파일명(`list_backups`는 이름 역순 = 최신 우선)."""
    entries = store.list_backups(appid)
    return os.path.basename(entries[-1]) if entries else None


def fill_ring(store, appid, filename):
    """링을 **가득** 채운다 — 1건만 더 쌓여도 최고령이 잘려 나가는 상태를 만든다."""
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
        fill_ring(store, APPID, "video.ini")                 # 링을 가득 채운다

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

        # ── ② 음성 대조군: 무쓰기 분기를 **제거한** 엔진에서는 ①이 FAIL해야 한다 ──
        def legacy_save(reg_, appid_, profile_):
            """R13 이전 본문의 재현 — 내용이 같아도 대피본을 만들고 다시 쓴다."""
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

        # ── ③ 진짜로 달라진 저장은 **여전히 쓴다**(무쓰기가 저장을 죽이지 않았다) ──
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

        # ── ④ 슬롯 본체가 **깨졌으면** 기록이 같아도 쓴다 — 단 **묻고** 쓴다 ─────
        #
        # ★★ 여기가 정책층과 엔진의 술어가 갈리던 자리다(QA R1 D-1, 2026-08-22).
        #   `meta.sha1`은 디스크와 같은데 본체가 다르면 — `write_profile`이 본체를 먼저 쓰고
        #   meta를 나중에 쓰므로 그 사이에 죽으면 실제로 생기는 상태다 — 엔진은 `slot_holds`가
        #   거짓이라 **대피·쓰기·축출을 실행하는데** 정책층은 기록만 보고 *"이미 같다"*며
        #   **안 물었다.** 확인창이 한 번도 안 뜬 채 포화 링의 최고령 백업이 사라졌다.
        #   그래서 이 갈래가 잠그는 것은 **둘**이다: ⓐ 자가 복구 경로가 살아 있다(쓴다)
        #   ⓑ 그 쓰기가 **고지 뒤에** 일어난다(대피가 링을 태우므로).
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

        # ── ⑤ 슬롯 본체가 **사라졌으면** 다시 만든다 ──────────────────────────
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
