#!/usr/bin/env python3
"""**기록(meta)을 어디까지 믿는가** — 사용자 결정 D8(크기 가드) · D5(삭제 확인창) · §14-E′(실패 사유).

세 수정이 같은 축에 있다. 앱은 슬롯의 **기록**과 **본체**를 따로 들고 있고, 기록이 본체와
어긋나는 상태를 **앱 자신이 만든다**(기록 쓰기 실패 · 삭제의 `rmtree` 중단 · 디렉터리 fsync를
비치명으로 낮춘 뒤의 쌍 원자성 저하). 그런데도 세 자리가 기록을 그대로 믿고 있었다:

  · **크기 가드**가 기록의 `size`를 기준으로 써서, 세대가 어긋나면 **멀쩡한 저장을 거부**했다(D8).
    → 방향이 나쁘다. 이 프로젝트가 한계로 남긴 것들은 전부 *"과하게 알려 준다"*였는데
      이건 **막는 방향**이고 사용자 기준 ③(메인 기능 막힘)에 닿는다.
  · **삭제 확인창**이 기록 유무로 *"저장돼 있나"*를 판정해서, 기록만 없고 본체는 멀쩡한 슬롯에서
    *"저장된 것 없음"*이라 말하고 승인하면 실제로는 대피와 삭제가 일어났다(D5).
  · **저장 실패 사유**가 기록 손상과 기기 문제(디스크 가득참·권한)를 **한 코드로 뭉갰다**(§14-E′).
    → 사용자가 엉뚱한 것을 의심하고 엉뚱한 복구를 시도한다.

### ★ 세 자리 모두 **양방향으로** 잰다
한 방향만 재면 *"가드를 아예 껐다"* · *"전부 True로 바꿨다"* · *"전부 새 코드로 바꿨다"*는
구현이 초록으로 지나간다. 그래서 세계마다 **음성 대조군**을 붙인다.

### 이 파일이 잠그는 것 여덟
  ① 기록이 **다른 세대**를 가리키는 슬롯 — 저장이 **거부되지 않는다**(크기 대조만 건너뛴다).
  ② **음성 대조군** — 기록이 본체와 맞는 정상 슬롯에서는 4배 넘는 파일이 **여전히 거부**된다.
  ③ **음성 대조군** — 빈 파일 거부(`FILE_EMPTY`)는 그대로 돈다(가드 전체를 끈 것이 아니다).
  ④ 기록만 지운 슬롯 — 삭제 확인창이 **「있다」**고 말한다(본체 기준).
  ⑤ **음성 대조군** — 본체만 지운 슬롯은 **「없다」**고 말한다(기록만 남은 것은 되찾을 내용이 아니다).
  ⑥ 쓰기가 막히면(`OSError`) `PROFILE_WRITE_FAILED`.
  ⑦ **음성 대조군** — 잘린 JSON 기록은 `PROFILE_META_CORRUPT` **그대로**(`JSONDecodeError ⊂ ValueError`).
  ⑧ **음성 대조군** — 비-UTF8 기록도 `PROFILE_META_CORRUPT`(`UnicodeDecodeError ⊂ ValueError`).

### ★ 계측 — 크기 가드에 **무엇이 기준으로 들어갔는지** 직접 센다
`engine.check_sanity`를 감싸 저장 갈래(`what="현재 설정 파일"`)의 `ref_size`가 `None`인지 본다.
①에서 `None`이 아니면 이 파일은 결함을 재지 못한 것이고, ②에서 `None`이면 가드가 꺼진 것이다.
**둘 다 화면에 찍는다.**

★ 합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp라 실사용 데이터에 닿을 수 없다.
"""
import asyncio
import json
import os
import pathlib
import shutil
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: 옛 세대의 기록이 가리키는 내용. 아래 NEW와 **4배 넘게** 차이 나야 이 파일이 무언가를 잰다.
TINY = b"q=1\nz=2\n"
#: 슬롯에 실제로 놓인 본체(새 세대).
BODY = b"# slot body\n" + b"k=v\n" * 120
#: 이번에 저장할 설정 파일 내용.
NEW = b"# new config\n" + b"a=b\n" * 150

#: 저장 갈래 `check_sanity` 호출 기록 — `(ref_size, ...)`.
SANITY = []


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


def instrument(engine):
    """저장 갈래의 크기 가드에 **무엇이 기준으로 들어갔는지** 기록한다."""
    real = engine.check_sanity

    def wrapped(data, ref_size=None, ref_lines=None, what="파일"):
        if what == "현재 설정 파일":
            SANITY.append(ref_size)
        return real(data, ref_size, ref_lines, what)

    engine.check_sanity = wrapped


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():                                                # noqa: C901  (세계 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-meta-trust-"))
    unchmod = []
    try:
        main = boot(tmp)
        from gfxp import codes, engine, remove, store
        instrument(engine)
        problems = []
        notes = []

        def P(msg):
            problems.append(msg)

        def build(appid, body):
            """그 슬롯에 `body`를 담은 정상 게임 하나(기록과 본체가 맞는 상태)."""
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(body)
            engine.add_game(reg, appid, str(cfg), name="g%s" % appid)
            engine.save_profile(reg, appid, "dock")
            engine.save_profile(reg, appid, "internal")
            store.save_registry(reg)
            return cfg

        def save(appid):
            """확인창 → 승인. 실패면 코드를, 성공이면 `"ok"`를 돌려준다."""
            del SANITY[:]
            env = rpc(main, "save_profile", appid=appid, profile="dock")
            p = env.get("params") or {}
            if not env.get("ok") and env.get("code") == codes.CONFIRM_REQUIRED:
                env = rpc(main, "save_profile", appid=appid, profile="dock",
                          confirm_token=p.get("confirm_token"))
            return "ok" if env.get("ok") else env.get("code")

        def slot_body(appid, profile):
            d = pathlib.Path(store.profile_dir(appid, profile))
            for f in sorted(d.iterdir()):
                if not store.is_byproduct(f.name):
                    return f.read_bytes()
            return None

        # ── 계측기 유효성: 4배 밖이어야 크기 가드가 발동한다 ──────────────────
        ratio = len(NEW) / float(len(TINY))
        if ratio <= 4.0:
            P("계측기 무효 — NEW/TINY 비율이 %.1f배라 크기 가드가 애초에 안 걸린다" % ratio)

        # ── ① 세대가 어긋난 슬롯 → 거부되지 않는다 ───────────────────────────
        cfg = build("8101", BODY)
        mp = pathlib.Path(store.profile_meta_path("8101", "dock"))
        meta = json.loads(mp.read_text(encoding="utf-8"))
        meta.update({"sha1": store.sha1_bytes(TINY), "size": len(TINY),
                     "lines": store.count_lines(TINY)})           # ★ 옛 세대를 가리키게 한다
        mp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        cfg.write_bytes(NEW)
        got = save("8101")
        if got != "ok":
            P("① 세대가 어긋난 슬롯에서 저장이 막혔다 — code=%s (사용자가 그 프로필에서 못 빠져나온다)"
              % got)
        elif slot_body("8101", "dock") != NEW:
            P("① 저장은 성공했다는데 슬롯 본체가 새 내용이 아니다")
        if SANITY and SANITY[-1] is not None:
            P("① 크기 가드가 **믿을 수 없는 기록의 size**를 기준으로 받았다 — ref_size=%r"
              % SANITY[-1])
        notes.append("① 세대 어긋남: 결과=%s · 저장 갈래 ref_size=%r (None이어야 정상)"
                     % (got, SANITY[-1] if SANITY else "호출 없음"))

        # ── ② 음성 대조군 — 정상 슬롯에서는 가드가 그대로 산다 ───────────────
        cfg = build("8102", TINY)
        cfg.write_bytes(NEW)
        got = save("8102")
        if got != codes.SIZE_OUT_OF_RANGE:
            P("② 정상 슬롯인데 4배 넘는 파일이 거부되지 않았다 — 결과=%s (가드를 아예 껐다)" % got)
        if SANITY and SANITY[-1] is None:
            P("② 정상 슬롯인데 크기 가드에 기준이 안 들어갔다 — ref_size=None (가드가 꺼졌다)")
        notes.append("② 정상 슬롯: 결과=%s · 저장 갈래 ref_size=%r (기록의 size여야 정상)"
                     % (got, SANITY[-1] if SANITY else "호출 없음"))

        # ── ③ 음성 대조군 — 빈 파일 거부는 그대로 ────────────────────────────
        cfg = build("8103", BODY)
        cfg.write_bytes(b"")
        got = save("8103")
        if got != codes.FILE_EMPTY:
            P("③ 빈 파일이 `FILE_EMPTY`로 거부되지 않았다 — 결과=%s" % got)

        # ── ④ 기록만 지운 슬롯 → 확인창이 「있다」 ────────────────────────────
        build("8104", BODY)
        for p_ in remove.PROFILES:
            os.unlink(store.profile_meta_path("8104", p_))
        reg = store.load_registry()
        params, _fp = remove.delete_preview(reg, "8104")
        if not (params["has_dock"] and params["has_internal"]):
            P("④ 기록만 없고 본체는 멀쩡한 슬롯을 확인창이 「저장된 것 없음」이라 말한다 — "
              "has_dock=%s has_internal=%s" % (params["has_dock"], params["has_internal"]))
        notes.append("④ 기록만 없음: has=(%s, %s) · saved_at=%s"
                     % (params["has_dock"], params["has_internal"], params.get("saved_at")))

        # ── ⑤ 음성 대조군 — 본체만 지운 슬롯 → 「없다」 ───────────────────────
        build("8105", BODY)
        for p_ in remove.PROFILES:
            d = pathlib.Path(store.profile_dir("8105", p_))
            for f in list(d.iterdir()):
                if not store.is_byproduct(f.name):
                    f.unlink()
        reg = store.load_registry()
        params, _fp = remove.delete_preview(reg, "8105")
        if params["has_dock"] or params["has_internal"]:
            P("⑤ 본체가 없는(되찾을 내용이 없는) 슬롯을 확인창이 「저장됨」이라 말한다 — "
              "has_dock=%s has_internal=%s" % (params["has_dock"], params["has_internal"]))
        notes.append("⑤ 본체만 없음: has=(%s, %s)"
                     % (params["has_dock"], params["has_internal"]))

        # ── ⑥ 쓰기가 막히면 `PROFILE_WRITE_FAILED` ───────────────────────────
        want_io = getattr(codes, "PROFILE_WRITE_FAILED", None)
        cfg = build("8106", BODY)
        cfg.write_bytes(NEW[:len(BODY)])                          # 크기 가드에 안 걸리게
        slot = pathlib.Path(store.profile_dir("8106", "dock"))
        os.chmod(slot, 0o500)
        unchmod.append(slot)
        blocked = True
        try:                                                      # ★ 계측기 자기검증
            probe = slot / ".probe"
            probe.write_bytes(b"x")
            probe.unlink()
            blocked = False
        except OSError:
            pass
        if not blocked:
            P("⑥ 계측기 무효 — `0500`인데도 슬롯에 쓸 수 있다(root로 도는가?). 이 세계는 안 쟀다")
        else:
            got = save("8106")
            if want_io is None:
                P("⑥ `codes.PROFILE_WRITE_FAILED`가 없다 — 저장 실패 사유가 갈려 있지 않다 "
                  "(결과=%s)" % got)
            elif got != want_io:
                P("⑥ 쓰기 실패(권한)가 `%s`로 나갔다 — 기대=%s. 기기 상태 문제를 「기록 손상」이라 "
                  "말하면 사용자가 엉뚱한 복구를 시도한다" % (got, want_io))
            notes.append("⑥ 쓰기 막힘(0500): 결과=%s" % got)
        os.chmod(slot, 0o700)

        # ── ⑦⑧ 음성 대조군 — 기록 손상 둘은 `PROFILE_META_CORRUPT` 그대로 ────
        for label, appid, raw in (("⑦잘린JSON", "8107", b'{"filename": "vid'),
                                  ("⑧비UTF8", "8108", b'\xff\xfe{"a":1}')):
            cfg = build(appid, BODY)
            cfg.write_bytes(NEW[:len(BODY)])
            pathlib.Path(store.profile_meta_path(appid, "dock")).write_bytes(raw)
            got = save(appid)
            if got != codes.PROFILE_META_CORRUPT:
                P("%s 손상된 기록이 `%s`로 나갔다 — 기대=%s (기록 손상까지 쓰기 실패로 뭉갰다)"
                  % (label, got, codes.PROFILE_META_CORRUPT))
            notes.append("%s: 결과=%s" % (label, got))

        print("기록을 어디까지 믿는가 — ①②③ 크기 가드(양방향+빈 파일) / ④⑤ 삭제 확인창(양방향) / "
              "⑥⑦⑧ 저장 실패 사유(양방향)  (데이터: %s)" % tmp)
        for n in notes:
            print("  계측: " + n)
        return finish(problems, tmp)
    finally:
        for d in unchmod:
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def finish(problems, tmp):
    if problems:
        print("\nFAIL")
        for x in problems:
            print("  " + x)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
