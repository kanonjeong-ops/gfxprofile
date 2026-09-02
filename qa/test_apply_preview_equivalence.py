#!/usr/bin/env python3
"""같은 관측 시점에서 미리보기 분류 ↔ 실제 실행 outcome의 대응 — 적대 합성 세계가 명세다.

### 왜 이 파일이 필요한가
실행 판정과 미리보기 판정이 별도 함수에 있으므로 두 결과의 대응을 검사한다 — 엔진(실행)과
`confirm.apply_all_preview`(미리보기). 미러는 언젠가 어긋나므로 어긋남을 테스트로 못박는다.
문서로 못박으면 문서만 맞는다.

이 파일이 재는 것은 그 두 판정의 대응이지 시점을 넘는 동치가 아니다. 확인 뒤 상태가 바뀌면
결과는 어느 방향으로도 달라질 수 있다 — 화면의 「예상」은 관측 시점의 분류다
(`main.py`의 `apply_all`·`confirm.apply_all_preview` 독스트링이 정본). 그래서 이 파일은
한 세계를 만들어 미리보기를 먼저 재고, 그 세계를 바꾸지 않은 채로 실행을 잰다.

### 왜 깨끗한 세계로는 부족한가
정상 게임만 있는 세계에서는 refused/error를 would_apply로 세는 4버킷 분류도 초록이다.
그래서 세계를 적대적으로 만든다 — 각 상태가 엔진의 5가지 outcome을 전부 만들어 낸다:

| 게임 | 상태 | 엔진 outcome | 미리보기 버킷 |
|---|---|---|---|
| 100 | 정상 전환 대상 | applied | would_apply |
| 200 | 디스크 = 프로필 | already | already |
| 300 | dock 프로필 없음 | no_profile | no_profile |
| 400 | meta만 잔존·본체 삭제 | refused(PROFILE_MISSING) | cannot_apply |
| 500 | 본체 변조(sha 불일치) | refused(PROFILE_CORRUPT) | cannot_apply |
| 600 | meta.json 손상(비JSON) | error | cannot_apply |
| 650 | meta가 유효 JSON이지만 비객체 | refused(PROFILE_CORRUPT) | cannot_apply |
| 660 | 등록 항목에 `config_path` 키 없음 | refused(REGISTRY_ENTRY_CORRUPT) | cannot_apply |
| 670 | `config_path`가 비-문자열(예: 123) | refused(REGISTRY_ENTRY_CORRUPT) | cannot_apply |
| 680 | `config_path`가 빈 문자열 | refused/error(빈 경로 가드) | cannot_apply |
| 700 | 실행 중 · 디스크 = 프로필 | already | already |
| 800 | 실행 중 · 디스크 ≠ 프로필 | refused(GAME_RUNNING) | running_refused |

700이 이 표의 핵심이다 — already 판정이 G5보다 먼저라(`engine.apply_all`의 `already` 갈래)
  실행 중이어도 디스크가 이미 그 프로필이면 `already`다. 이 순서를 뒤집으면 화면은
  "실행 중 2개 거부 예상"이라 말하는데 실제로는 1개만 거부된다. 중복 산정 규칙(게임 하나는
  정확히 한 버킷)도 여기서 잠긴다.

### 이 파일이 잠그는 것
  ① 게임별 버킷 ↔ outcome 대응(위 표 전수). 이것을 "1:1"이라 부르지 않는다: `cannot_apply`는
     `refused`(GAME_RUNNING 제외)와 `error`를 함께 받는다. 잠그는 것은 표의 12게임 각각이
     기대 버킷 하나에 들고, 그 실행 outcome이 해당 버킷의 허용 집합에 드는가이다.
  ② 격리 계약 — meta 손상 2건이 섞여 있어도 나머지 게임이 정상 분류된다.
     격리가 없으면 미리보기가 통째로 죽어 `CONFIRM_REQUIRED`가 영영 안 나오고
     일괄 적용 버튼이 전면 불능이 된다.
  ③ 미리보기가 파일을 1바이트도 안 바꾼다(합성 세계 전 파일 sha1 전수 대조).
  ④ 버킷 합 = 등록 수(어느 게임도 빠지거나 두 번 세지 않는다).

660: `entry["config_path"]`가 없으면 엔진은 `refused(REGISTRY_ENTRY_CORRUPT)`다(★ 19판 — 그
  전에는 `KeyError`가 게임별 외곽 try에 잡혀 `error`였다), 미리보기는 `cannot_apply`여야 한다.
  미리보기가 그 자리를 안 보면 `would_apply`로 센다 — "적용된다 해 놓고 안 되는" 어긋남이다.
  미러가 그 판정을 갖고 있는지를 이 세계가 잠근다(670의 비-문자열도 같은 술어가 잡고, 680의
  빈 문자열은 술어에 안 걸려 뒤의 빈 경로 가드가 잡는다 — 셋 다 `cannot_apply` 한 칸이다).
  버킷은 그대로다 — `cannot_apply`가 `refused`와 `error`를 함께 받으므로, 이 검사가 잠그는 것은
  봉투 코드가 아니라 버킷 대응이다.
  (남은 어긋남 하나 — `config_path`가 심볼릭 링크여서 G11이 거부하는 경우 — 는 설계가
   선언한 한계다: 실행 시점 가드는 미리보기가 예측하지 않는다. 방향은 같은 쪽으로 안전하다.)

### 단언 범위
`cannot_apply`는 "refused(GAME_RUNNING 제외)/error에 대응"이지 세부 code까지 예측한다고
단언하지 않는다. 미리보기는 분류이지 실행이 아니다 — `BACKUP_FAILED`처럼 실행 시점에만 나는
실패는 예측할 수 없고, 그 잔차는 실행 후 요약·로그가 정본으로 보고한다.
"""
import copy
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTERNAL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
TAMPERED = b"quality=????\nshadows=????\nsource=TAMPERED-BODY\n"

PROFILE = "dock"
RUNNING = {"700", "800"}

#: 버킷 → 허용되는 엔진 outcome. `cannot_apply`만 둘을 받는다(위 「단언 범위」).
ALLOWED = {
    "would_apply": {"applied"},
    "already": {"already"},
    "no_profile": {"no_profile"},
    "running_refused": {"refused"},
    "cannot_apply": {"refused", "error"},
}


def world_sha(root):
    import hashlib
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, root)] = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                out[os.path.relpath(path, root)] = "unreadable"
    return out


def build_world(tmp, engine, store):
    """표의 게임을 전부 만든다. 전부 실제 저장 경로를 태워 만든다(손으로 밀지 않는다)."""
    reg = store.load_registry()
    cfgs = {}

    def add(appid, name, internal=True):
        cfg = tmp / ("game%s" % appid) / "video.ini"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_bytes(DOCK)
        engine.add_game(reg, appid, str(cfg), name=name)
        engine.save_profile(reg, appid, "dock")
        if internal:
            cfg.write_bytes(INTERNAL)
            engine.save_profile(reg, appid, "internal")
        cfgs[appid] = cfg
        return cfg

    add("100", "Normal").write_bytes(INTERNAL)            # 디스크≠dock → applied
    add("200", "Already").write_bytes(DOCK)               # 디스크==dock → already
    # 300: dock 프로필을 만들지 않는다 — internal만 있는 게임
    cfg300 = tmp / "game300" / "video.ini"
    cfg300.parent.mkdir(parents=True, exist_ok=True)
    cfg300.write_bytes(INTERNAL)
    engine.add_game(reg, "300", str(cfg300), name="NoDockProfile")
    engine.save_profile(reg, "300", "internal")
    cfgs["300"] = cfg300

    add("400", "MetaOnly").write_bytes(INTERNAL)
    os.unlink(store.profile_file_path("400", "dock"))     # 본체만 지운다(meta는 남긴다)

    add("500", "TamperedBody").write_bytes(INTERNAL)
    with open(store.profile_file_path("500", "dock"), "wb") as fh:
        fh.write(TAMPERED)                                # meta의 sha1과 어긋나게 만든다

    add("600", "CorruptMeta").write_bytes(INTERNAL)
    with open(store.profile_meta_path("600", "dock"), "wb") as fh:
        fh.write(b"\x00\xff not json at all \x00")

    add("650", "NonDictMeta").write_bytes(INTERNAL)
    with open(store.profile_meta_path("650", "dock"), "w", encoding="utf-8") as fh:
        fh.write('"valid json but not an object"')

    add("660", "NoConfigPath").write_bytes(INTERNAL)
    reg["games"]["660"].pop("config_path", None)          # 손상·수동 편집된 등록 항목

    add("670", "NonStrConfigPath").write_bytes(INTERNAL)
    reg["games"]["670"]["config_path"] = 123              # 비-문자열 — 손상 술어가 잡는다

    add("680", "EmptyConfigPath").write_bytes(INTERNAL)
    reg["games"]["680"]["config_path"] = ""               # 빈 문자열 — 술어엔 안 걸리나 빈 경로 가드가 잡는다

    add("700", "RunningAlready").write_bytes(DOCK)        # 실행 중 · 디스크==dock
    add("800", "RunningDiffer").write_bytes(INTERNAL)     # 실행 중 · 디스크≠dock

    store.save_registry(reg)
    return reg, cfgs


EXPECTED = {
    "100": "would_apply",
    "200": "already",
    "300": "no_profile",
    "400": "cannot_apply",
    "500": "cannot_apply",
    "600": "cannot_apply",
    "650": "cannot_apply",
    "660": "cannot_apply",     # config_path 없음 → 엔진은 refused(REGISTRY_ENTRY_CORRUPT)
    "670": "cannot_apply",     # config_path 비-문자열 → 손상 술어 → refused(REGISTRY_ENTRY_CORRUPT)
    "680": "cannot_apply",     # config_path 빈 문자열 → 빈 경로 가드 → refused/error
    "700": "already",          # already가 G5보다 먼저다 — 실행 중이어도 already
    "800": "running_refused",
}


def main_test():                                                # noqa: C901
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-preview-eq-"))
    os.environ["GFXPROFILE_DATA_DIR"] = str(tmp / "data")
    os.environ["GFXPROFILE_HOME"] = str(tmp)
    from gfxp import confirm, engine, store
    problems = []
    real_running = engine.running_game
    try:
        reg, cfgs = build_world(tmp, engine, store)

        def P(msg):
            problems.append(msg)

        # 실행 중 게임을 합성한다 — 미리보기가 받는 집합과 같은 사실이어야 한다.
        engine.running_game = lambda appid: str(appid) in RUNNING

        # ── ③ 미리보기는 아무것도 쓰지 않는다 ────────────────────────────────
        before = world_sha(tmp)
        try:
            counts = confirm.apply_all_preview(copy.deepcopy(reg), PROFILE, RUNNING)
        except Exception as exc:                                # noqa: BLE001
            # 격리 계약이 깨지면 여기서 예외가 나온다. 그 사실 자체가 결함이므로 traceback으로
            #   죽지 말고 무슨 일인지 말하고 끝낸다 — 진단이 사라지는 실패를 만들지 않는다.
            print("미리보기 버킷 대응 — 적대 세계 %d게임" % len(EXPECTED))
            print("\nFAIL")
            print("  ★② 미리보기가 예외로 죽었다(%s: %s) — 손상 게임 1건이 미리보기를 전멸시키면 "
                  "CONFIRM_REQUIRED가 영영 안 나오고 **일괄 적용 버튼이 전면 불능**이 된다"
                  % (type(exc).__name__, exc))
            return 1
        after = world_sha(tmp)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        if changed:
            P("★③ 미리보기가 파일을 바꿨다 — %s" % sorted(changed)[:5])

        # ── ④ 버킷 합 = 등록 수 ──────────────────────────────────────────────
        if sum(counts.values()) != len(reg["games"]):
            P("★④ 버킷 합(%d)이 등록 수(%d)와 다르다 — 게임이 빠지거나 두 번 셌다"
              % (sum(counts.values()), len(reg["games"])))

        # ── ② 격리: 손상 2건이 있어도 나머지가 정상 분류된다 ─────────────────
        #    (격리가 없으면 ③의 전체 미리보기가 예외로 죽어 여기까지 오지도 못한다)
        per_game = {}
        for appid in sorted(reg["games"]):
            one = copy.deepcopy(reg)
            one["games"] = {appid: reg["games"][appid]}
            try:
                got = confirm.apply_all_preview(one, PROFILE, RUNNING)
            except Exception as exc:                            # noqa: BLE001
                per_game[appid] = "★예외:%s" % type(exc).__name__
                continue
            picked = [k for k, v in got.items() if v]
            per_game[appid] = picked[0] if len(picked) == 1 else "★중복/미분류:%s" % picked

        from_per_game = {}
        for bucket in per_game.values():
            from_per_game[bucket] = from_per_game.get(bucket, 0) + 1
        if from_per_game != {k: v for k, v in counts.items() if v}:
            P("★② 전체 미리보기(%s)와 게임별 판정의 합(%s)이 다르다 — 격리 계약이 깨졌다"
              % ({k: v for k, v in counts.items() if v}, from_per_game))

        for appid, want in EXPECTED.items():
            if per_game.get(appid) != want:
                P("① [%s] 미리보기 버킷이 %s다(기대 %s)" % (appid, per_game.get(appid), want))

        # ── ① 실제 실행과의 대응(버킷이 그 outcome을 받는가) ────────────────────
        #    미리보기를 먼저 재고 나서 실행한다 — 순서를 바꾸면 미리보기가 실행 후 세계를 본다.
        rows = engine.apply_all(copy.deepcopy(reg), PROFILE)
        outcomes = {r["appid"]: (r["outcome"], r.get("code")) for r in rows}
        if set(outcomes) != set(EXPECTED):
            P("① 실행 결과 게임 집합이 다르다 — %s" % sorted(outcomes))
        for appid, want in EXPECTED.items():
            outcome, code = outcomes.get(appid, ("<없음>", None))
            if outcome not in ALLOWED[want]:
                P("★① [%s] 미리보기=%s인데 실제 outcome=%s(code=%s) — 버킷이 그 결과를 안 받는다"
                  % (appid, want, outcome, code))
            if want == "running_refused" and code != "GAME_RUNNING":
                P("★① [%s] running_refused로 셌는데 실제 거부 사유가 %s다 — 실행 중이 아니라 "
                  "다른 이유로 거부됐다(버킷 정의가 어긋난다)" % (appid, code))
            if want == "cannot_apply" and code == "GAME_RUNNING":
                P("★① [%s] cannot_apply로 셌는데 실제로는 GAME_RUNNING이다 — running_refused여야 한다"
                  % appid)

        print("미리보기 버킷 대응 — 적대 세계 %d게임 / 버킷 %s" % (len(EXPECTED), counts))
        print("  실제 outcome: %s" % {a: o for a, (o, _c) in sorted(outcomes.items())})
        if problems:
            print("\nFAIL")
            for p in problems:
                print("  " + p)
            return 1
        print("PASS")
        return 0
    finally:
        engine.running_game = real_running
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_test())
