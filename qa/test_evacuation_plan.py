#!/usr/bin/env python3
"""**대피의 중복 판정은 「동작이 시작할 때 한 번」이다** — 사용자 결정 D1(=B′) · D6.

### 무엇이 틀렸었나
등록 해제·전체 초기화는 두 슬롯을 **차례로** 백업 링에 대피시킨다. 그런데 판정이 호출마다
따로 났다: 먼저 쓴 대피본이 링을 밀어내면서 **뒤 항목이 「이미 있다」고 믿던 바로 그 사본을
잘라 냈다.** 그러면 뒤 슬롯은 옮기지도 않았는데 근거도 사라진다 — 프로필 내용이 **슬롯에도
백업에도 없다.** 중복인 쪽이 뒤면 대신 *예고보다 백업이 하나 더* 지워졌다.

### ★ 기존 33종이 이 축을 하나도 못 잡았다 (그래서 이 파일이 있다)
동작이 서로 다른 사본 **넷**(현행·보호집합·공유안·B′)이 **전부 33종을 통과했다**(발주 세션 실측).
통과는 *"안 깬다"*이지 *"잰다"*가 아니다. 이 파일은 **되돌리면 반드시 FAIL이 나야** 값이 있다.

### ⚠️ 픽스처의 함정 — 중복 판정은 **태그별**이다
근거 사본의 태그가 `disk`면 프로필 대피의 근거가 **되지 못한다**(§5-C ⓐ — 되돌릴 곳이 다른 두
행은 서로를 대신하지 못한다). 그것을 모르고 링을 `disk` 사본으로만 채우면 **승격 갈래에 한 번도
안 닿는다**(실기에서 실제로 빠졌던 함정). 그래서 근거 사본은 반드시 `profile_dock`/`profile_internal`
태그로 놓고, **축출 꼬리**(`entries[BACKUP_KEEP - adding:]`)에 들어오게 배치한다.

### 이 파일이 잠그는 것
  ⓐ **중복인 쪽이 앞**(dock)일 때 — 셋이 같이 서야 잰 것이다:
     ① 그 프로필 **내용이 백업에 남는가** ② 예고한 개수 == 실제 ③ **예고한 이름 == 실제 지워진 이름**
  ⓑ **중복인 쪽이 뒤**(internal)일 때 — 같은 셋. 현행은 ②③이 깨진다(예고 1건, 실제 2건 삭제).
  ⓒ **★ 음성 대조군 — 승격이 일어나면 안 되는 세계.** 근거 사본이 **축출 꼬리 밖**(링 중간)이면
     그것은 살아남으므로 근거가 유효하고, **아무것도 승격하지 않는다.** 이 세계가 없으면
     *"그냥 항상 쓴다"*는 구현이 ⓐⓑ를 초록으로 통과한다. 멀쩡한 백업의 **날짜가 안 바뀌는 것**도
     여기서 잰다(그 사본이 **같은 이름 그대로** 남아 있는가).
  ⓓ **D6 — 계획↔쓰기 창**(저장·삭제 두 갈래). 계획은 본체를 `sha1_file`로 재고 쓰기는
     `read_bytes`로 다시 읽는다. **그 사이 본체가 바뀌면 실제 키가 계획에 없다** — 거기서
     무쓰기로 접으면 **대피 없이 저장이 슬롯을 덮고 삭제가 `rmtree`까지 간다.**
     계획은 *"이것만 써라"*가 아니라 **"이건 중복이라도 써라"는 허가 목록**이어야 한다.
     ⚠️ 이 세계는 **현행 코드에는 없던 구멍**을 잠근다 — 과거 커밋에서는 FAIL하지 않는 것이 정상이고,
     구멍이 들어 있는 사본(`sbx-inv1-B2`)에서 FAIL한다. 미래의 재도입을 막는 자리다.
  ⓔ **링 상한은 그대로다** — 승격이 늘어도 `BACKUP_KEEP`칸을 넘지 않는다(기각된 보호집합 안이
     11·13칸으로 깨뜨렸던 자리다).
  ⓘ **★ 비포화 링에서는 아무도 안 밀려난다 — 그때 증인은 믿어야 한다**(N-01, 2026-08-23).
     ⓒ의 형제이고 **경계를 재는 쪽**이다: ⓒ는 근거 사본을 링 **한가운데**에 두어 *"살아남는 꼬리의
     경계"*를 안 잰다. 여기서는 링이 **`BACKUP_KEEP`보다 한 칸 적고** 근거가 **최고령**이라,
     꼬리를 한 칸이라도 과대평가하면 곧바로 증인을 불신한다. 그러면 정상 중복이 쓰이고
     **확인창이 예고하지 않은 백업이 삭제된다**(실측 — 우리가 D-01을 고치며 만든 결함이다).
     ⚠️ 판정을 `BACKUP_KEEP - len(plan)` 꼴로 쓰면 **링이 가득 찼다고 가정**하는 것이라 여기서 깨진다.
  ⓚ **★ 링이 상한을 넘고 계획이 **0건**이면 아무것도 안 밀려난다**(N-03) — **행동으로 잰다.**
     `prune_backups`는 `make_backup` **안에서 쓰기 뒤에만** 돈다. 한 건도 안 쓰면 prune 자체가
     안 돌아, 상한을 넘긴 링이라도 **그대로 남는다.** 계획 경로는 `adding == 0`을 특수 처리해
     이것을 지켰는데 계획 밖 판정이 그 분기를 안 가져와서, **예고 0인데 4건이 삭제**되고
     그중 둘은 **최신 10칸 안의 고유 백업**이었다(실측 — *"어차피 잘린다"*가 아니다).
     ★ 이 세계가 ⓙ의 사각 셋을 한꺼번에 덮는다 — **실제 `make_backup` 호출을 지나므로**
     술어가 죽은 헬퍼가 되거나 이름이 바뀌면 여기서 걸린다.
  ⓙ **★ 「살아남는 칸」 계산이 정의와 어긋나지 않는다 — 특히 계획이 링보다 클 때**(N-02).
     `entries[:len(entries) - doomed]` 꼴로 적으면 `doomed`가 링 칸수를 넘는 순간 인덱스가 **음수**가
     되고, 파이썬 음수 슬라이스는 **0개가 아니라 앞부분을 다시 신뢰한다**(계획 14 → 「전부 불신」이어야
     할 자리가 **6칸 신뢰**로 뒤집혔다). ⚠️ **`max(0, …)`가 슬라이스 인덱스 자리에 있어야** 막힌다.
     ★ 이 세계는 **단위 단언**이다 — `len(plan) > BACKUP_KEEP` 구간에서는 기존 링이 **어차피 전부**
     축출되므로 **행동으로는 차이가 안 난다**(직접 확인했다). 그래서 술어를 직접 잰다.
     ⚠️ **ⓔ(본체 11개)로는 못 잡는다** — 거기선 모든 본체가 새 내용이라 전부 계획에 들어가
     **계획 밖 갈래에 0회 닿는다**(실측). 세계를 넓히는 것으로는 안 되고 새로 세워야 한다.
  ⓖ **★ 계획 밖 키의 자체 판정도 「축출될 사본」을 근거로 삼지 않는다**(D-01, 2026-08-23).
     ⓓ와 같은 「계획 뒤 본체가 바뀐다」인데 **링이 포화**이고 **최고령 칸이 바뀐 내용의 유일한
     사본**이다. 자체 판정이 *호출 시점의 링*을 보면 그 최고령을 근거로 무쓰기가 되고,
     **뒤 슬롯의 계획된 쓰기가 바로 그 칸을 축출**한다 — 내용이 슬롯에도 링에도 없다(**전손**).
     **D1이 계획 경로에서 고친 병이 fallback 경로에 남아 있던 자리**이고 `c590d3c`에도 있었다.
     ⚠️ 저장 갈래로는 재현되지 않는다 — 저장은 대피가 한 슬롯뿐이라 **뒤따르는 쓰기가 없어**
     근거 사본이 축출되지 않는다. 두 슬롯을 차례로 옮기는 삭제라야 도달한다.
  ⓗ **판정은 「동작 경계에서 한 번」이다 — 횟수로 잰다.** 승인 1회는 `plan_backups`를
     **정확히 두 번**(고지 1 + 실행 1) 부른다. `>= 1`로만 재면 **계획 호출을 하나 더 넣은
     구현이 그대로 통과한다**(실측 — 이종 검토 지적). 그래서 등식으로 잠근다.
  ⓛ **★ 한 동작이 **둘 이상** 쓸 때, 먼저 쓴 대피본이 뒤 쓰기의 prune에 잘리지 않는다**
     (QA DEFECT-01 처방 ③, 2026-08-23). 링에 **지금보다 미래 stamp**를 가진 백업이 있으면 새
     대피본이 `backup_order_key` 기준 **가장 오래된 것**으로 읽힌다 — 자기 하나만 보호하는
     prune은 그것을 **다음 쓰기에서** 잘라 내고, 그 슬롯은 곧 `rmtree`된다(**전손**). 그런데
     결과 봉투는 `evacuated`로 *대피시켰다*고 보고한다. 실측(고치기 전): 링 12 · 미래 stamp에서
     **예고 4 · 실제 3 · dock 프로필 내용 소멸**(문턱은 그런 백업 9칸).
     ★ **음성 대조군이 붙는다**(정상 시각 링) — 거기서는 예고도 실제도 **그대로**여야 한다.
       보호를 넓히면서 정상 시각의 축출 수가 달라지면 그것도 결함이다.
     ★ **삭제(등록 해제)와 「본체가 둘 이상인 슬롯 저장」을 둘 다 지난다** — 계획 객체를 만드는
       호출부가 `remove`·`engine` **둘**이라, 한쪽만 되돌린 사본이 다른 쪽 세계를 그대로 통과한다.
     ⚠️ **이 세계가 잠그는 것은 「한 동작 안의 순서」뿐이다.** *"링 순서를 벽시계 stamp에서
       유도한다"*는 전제는 그대로 남고 화면의 시각 표기·목록 정렬도 그대로다 — 여기가 초록이라고
       *"시각 축을 닫았다"*로 읽으면 화면도 문서도 거짓이 된다.
  ⓕ **대피는 「할 수 있을 때」 한다**(사용자 결정 D4) — 슬롯 폴더를 **열거하지 못해도** 저장은
     성립한다. `store.atomic_write`는 `os.replace`가 `try` 안이고 디렉터리 fsync는 **밖**이라,
     예전에는 **본체를 덮은 뒤에** 예외가 났다: 화면은 *"프로필 정보가 손상되어 저장할 수
     없습니다"*라 말하는데 기록만 옛 내용을 가리켜 **그 프로필은 적용도 안 됐다.**
     ⚠️ **범위가 넓어서 잠근다**: `atomic_write`는 공용이고 호출부가 **일곱**이라, 무심코
     `raise`가 되살아나면 앱이 파일을 쓰는 **모든** 자리가 같이 영향받는다. 그리고 2번은
     **계약을 낮춘** 수정이라 되돌리기 쉬운 종류다.

### ★ 계측 — 경로가 실제로 몇 번 돌았는지 센다
`store.make_backup`을 감싸 **호출 시점의 링**으로 `backup_holds`를 먼저 재고, 그 뒤 실제로
파일이 만들어졌는지 본다. **「중복인데 썼다」 = 승격**이다. 0회면 이 파일은 아무것도 안 잰 것이고,
그 사실을 화면에 찍는다(0회면 FAIL로 끝난다 — 계측기 무효를 통과로 읽지 않는다).

★ 합성 데이터만 쓴다 — `DECKY_PLUGIN_RUNTIME_DIR`·`GFXPROFILE_HOME`이 tmp라 실사용 데이터에 닿을 수 없다.
"""
import asyncio
import os
import pathlib
import shutil
import sys
import tempfile
import time
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCK = b"quality=dock\nshadows=high\nsource=DOCK-PROFILE\n"
INTL = b"quality=intl\nshadows=low_\nsource=INTL-PROFILE\n"
MOVED = b"quality=mvd_\nshadows=mid_\nsource=CHANGED-BEHIND-PLAN\n"
#: ⓛ 전용 — **한 슬롯에 본체가 둘**인 상태를 만들어 저장이 백업을 둘 쓰게 한다.
EXTRA = b"quality=xtra\nshadows=none\nsource=SECOND-BODY-IN-SLOT\n"

#: 승격/무쓰기 계측. 세계마다 `reset()`하고 그 세계의 동작만 센다.
COUNT = {"call": 0, "wrote": 0, "skipped": 0, "plan_calls": 0, "off_plan": 0,
         "promoted_write": 0, "promoted_plan": 0, "plan_fallback": 0}


def reset():
    for k in COUNT:
        COUNT[k] = 0


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


def instrument(store):
    """`make_backup`을 감싼다 — **구현이 아니라 관측 가능한 사실만** 센다.

    ★ 판정은 호출 **전에** 한다: `backup_holds`는 링을 보고, 계획 소속은 `make_backup`이
      허가를 소비(`discard`)하기 전에 봐야 한다. 뒤에 재면 둘 다 거짓이 된다.
    ★ `plan` 인자를 **모르는 판본에서도 돈다**(`**kw`를 그대로 전달할 뿐이다).
    """
    real = store.make_backup

    def wrapped(appid, data, tag, filename, **kw):
        safe = tag.replace("/", "_").replace(":", "_")
        sha = store.sha1_bytes(data)
        held = bool(store.backup_holds(store.list_backups(appid), safe, sha))
        plan = kw.get("plan")
        in_plan = plan is not None and (safe, sha) in plan
        if plan is not None and not in_plan:
            COUNT["off_plan"] += 1          # ★ 계획 밖 갈래에 **닿았다**(썼는지와 별개)
        out = real(appid, data, tag, filename, **kw)
        COUNT["call"] += 1
        if out:
            COUNT["wrote"] += 1
            if held:
                COUNT["promoted_write"] += 1    # **쓸 때도 여전히** 중복이었는데 썼다
            if plan is not None and not in_plan:
                COUNT["plan_fallback"] += 1     # 계획 밖 키를 스스로 판정해 썼다 (D6)
        else:
            COUNT["skipped"] += 1
        return out

    store.make_backup = wrapped
    return real


def instrument_plan(store):
    """계획을 내는 자리를 감싼다 — **승격의 정의는 여기다.**

    ⚠️ 「쓸 때 중복이었는가」만 세면 **중복인 쪽이 뒤일 때 승격을 못 본다**: 먼저 쓴 대피본이
      근거 사본을 이미 밀어내 버려서, 두 번째 쓰기 시점에는 중복이 아니다. 그것이 바로 이
      결함의 기전이므로, 승격은 **판정 시점**(계획을 낼 때 중복인데도 계획에 넣었는가)에서 센다.
    ★ `plan_backups`가 없는 판본(이 수정 이전)에서는 감싸지 않는다 — 그때는 아래 관측
      단언(①②③)이 이미 FAIL한다. 계측이 없다고 통과로 읽히지 않는다.
    """
    real = getattr(store, "plan_backups", None)
    if real is None:
        return None

    def wrapped(entries, items):
        COUNT["plan_calls"] += 1        # ★ **몇 번 판정했는가** — "한 번"이 계약의 절반이다
        out = real(entries, items)
        for tag, sha1 in out:
            if sha1 and store.backup_holds(entries, tag, sha1):
                COUNT["promoted_plan"] += 1     # 중복인데 계획이 허가했다 = 승격
        return out

    store.plan_backups = wrapped
    return real


def ring_survivors(entries, adding, keep):
    """**독립 오라클** — `adding`건을 쓴 뒤 **원래 항목 중** 살아남는 것.

    ★★ 생산 코드의 식(`_doomed_tail`)을 **인용하지 않는다.** 그것을 오라클로 쓰면 항진식이 되어
      *"코드로 코드를 재게"* 된다. 대신 **링의 동작 자체**를 흉내 낸다: 새 백업은 맨 앞(최신)에
      놓이고, `prune_backups`는 **오래된 것부터** 잘라 `keep`칸으로 맞춘다.
    ★ **쓰기가 0건이면 아무도 안 밀린다** — `prune_backups`는 `make_backup` **안에서 쓰기 뒤에만**
      돌기 때문이다. 링이 `keep`을 넘겨 있어도 그렇다. (이 한 줄이 N-03이 깨진 자리이고,
      **예전 ⓙ의 기대값은 결함과 같은 방향으로 틀려 있었다** — 그래서 초록이 나왔다.)
    ★ **전제: 백업 stamp가 시각순으로 단조 증가한다.** "새 백업이 맨 앞(최신)"이라는 이 오라클의
      뼈대는 그 위에서만 성립한다 — 미래·역행 stamp가 섞이면 최신 순서가 뒤집혀 전제가 깨진다.
    """
    if adding <= 0:
        return list(entries)
    ring = ["#new%d" % i for i in range(adding)] + list(entries)
    have = set(entries)
    return [e for e in ring[:keep] if e in have]


def rpc(main, name, *args, **kwargs):
    return asyncio.run(getattr(main.Plugin(), name)(*args, **kwargs))


def main_test():                                                # noqa: C901  (세계 나열)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gfxp-evac-plan-"))
    unchmod = []
    try:
        main = boot(tmp)
        from gfxp import codes, engine, remove, store
        instrument(store)
        planned = instrument_plan(store)
        problems = []
        notes = []

        def P(msg):
            problems.append(msg)

        def names(appid):
            return [os.path.basename(p) for p in store.list_backups(appid)]

        def holds(appid, kind, data):
            """그 태그의 링이 그 내용을 담은 백업 **이름들**."""
            want = store.sha1_bytes(data)
            out = []
            for path in store.list_backups(appid):
                info = store.parse_backup_id(os.path.basename(path))
                if info["kind"] == kind and store.sha1_file(path) == want:
                    out.append(os.path.basename(path))
            return out

        def build(appid):
            """dock=DOCK · internal=INTL 두 슬롯. 첫 저장이라 대피가 없어 링은 비어 있다."""
            reg = store.load_registry()
            cfg = tmp / ("game%s" % appid) / "video.ini"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_bytes(DOCK)
            engine.add_game(reg, appid, str(cfg), name="g%s" % appid)
            engine.save_profile(reg, appid, "dock")
            cfg.write_bytes(INTL)
            engine.save_profile(reg, appid, "internal")
            cfg.write_bytes(DOCK)
            store.save_registry(reg)
            return cfg

        def filler(appid, i):
            store.make_backup(appid, b"filler-%02d\n" % i, store.KIND_DISK, "fill%02d.ini" % i)

        def witness(appid, profile, data):
            """근거 사본 — **`profile_*` 태그**라야 프로필 대피의 중복 판정에 낀다."""
            store.make_backup(appid, data, store.profile_tag(profile), "video.ini")

        def delete_via_route(appid):
            """확인창 → 승인. `(예고 이름들, 예고 adding, 실제 사라진 이름들, 봉투)`."""
            before = names(appid)
            ask = rpc(main, "delete_game", appid)
            p = ask.get("params") or {}
            promised = [r["backup_id"] for r in (p.get("evicted") or [])]
            reset()                                       # ★ 예고까지는 안 센다 — 실행만 센다
            done = rpc(main, "delete_game", appid, confirm_token=p.get("confirm_token"))
            after = names(appid)
            gone = [n for n in before if n not in after]
            return promised, p.get("evicted"), gone, done, ask

        def check_ring_cap(appid, where):
            if len(names(appid)) > store.BACKUP_KEEP:
                P("%s 링 상한이 깨졌다 — %d칸 (BACKUP_KEEP=%d)"
                  % (where, len(names(appid)), store.BACKUP_KEEP))

        # ── ⓐ·ⓑ 중복인 쪽이 앞/뒤 ────────────────────────────────────────────
        for tag, (appid, dup_profile, dup_data, live_profile, live_data) in {
            "ⓐ앞(dock이 중복)": ("9101", "dock", DOCK, "internal", INTL),
            "ⓑ뒤(internal이 중복)": ("9102", "internal", INTL, "dock", DOCK),
        }.items():
            build(appid)
            witness(appid, dup_profile, dup_data)         # ★ 최고령 = 근거 사본
            for i in range(store.BACKUP_KEEP - 1):
                filler(appid, i)
            if len(names(appid)) != store.BACKUP_KEEP:
                P("%s 계측기 무효 — 포화 링을 못 만들었다(%d칸)" % (tag, len(names(appid))))
                continue
            found = holds(appid, store.profile_tag(dup_profile), dup_data)
            if len(found) != 1 or names(appid)[-1] != found[0]:
                P("%s 계측기 무효 — 근거 사본이 최고령이 아니다(축출 꼬리에 안 든다) — %s"
                  % (tag, found))
                continue

            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("%s 등록 해제가 실패했다 — code=%s" % (tag, done.get("code")))
                continue
            # ① 내용이 백업에 남는가 — 두 프로필 다
            for prof, data in (("dock", DOCK), ("internal", INTL)):
                if not holds(appid, store.profile_tag(prof), data):
                    P("%s ① %s 프로필 내용이 슬롯에도 백업에도 없다 (승격이 안 일어났다)"
                      % (tag, prof))
            # ② 예고한 개수 == 실제 새로 쌓인 수
            if len(promised) != len(gone):
                P("%s ② 예고 %d건 ≠ 실제 지워진 %d건 (예고=%s / 실제=%s)"
                  % (tag, len(promised), len(gone), promised, gone))
            # ③ 예고한 이름 == 실제 지워진 이름
            if sorted(promised) != sorted(gone):
                P("%s ③ 예고한 이름과 실제 지워진 이름이 다르다 — 예고=%s / 실제=%s"
                  % (tag, sorted(promised), sorted(gone)))
            # 승격이 실제로 돌았는가 (계측)
            if planned is None:
                P("%s `store.plan_backups`가 없다 — 판정이 동작 경계로 올라가 있지 않다" % tag)
            elif COUNT["promoted_plan"] < 1:
                P("%s 승격이 0회다 — 축출될 사본을 여전히 근거로 믿었다 (계측: %s)"
                  % (tag, dict(COUNT)))
            if COUNT["plan_calls"] != 2:
                P("%s 계획 산출이 %d회다 — 승인 1회는 **고지 1 + 실행 1 = 정확히 2회**여야 한다. "
                  "늘면 「동작 경계에서 한 번」이 깨진 것이고(관측이 갈린다), 줄면 고지나 실행이 "
                  "계획을 안 본 것이다" % (tag, COUNT["plan_calls"]))
            notes.append("%s 계획산출 %d회 · 승격(판정시점) %d · 승격(쓸때도 중복) %d · 쓰기 %d · 무쓰기 %d"
                         % (tag, COUNT["plan_calls"], COUNT["promoted_plan"],
                            COUNT["promoted_write"], COUNT["wrote"], COUNT["skipped"]))
            check_ring_cap(appid, tag)

        # ── ⓒ 음성 대조군 — 근거가 축출 꼬리 **밖**이면 승격하지 않는다 ──────
        appid = "9103"
        build(appid)
        for i in range(5):                                # 더 오래된 것 다섯
            filler(appid, i)
        witness(appid, "dock", DOCK)                      # 근거 = 링 한가운데
        for i in range(5, store.BACKUP_KEEP - 1):         # 더 새것 넷
            filler(appid, i)
        keep_name = holds(appid, store.profile_tag("dock"), DOCK)
        if len(names(appid)) != store.BACKUP_KEEP or len(keep_name) != 1:
            P("ⓒ 계측기 무효 — 링 %d칸 · 근거 사본 %d개" % (len(names(appid)), len(keep_name)))
        elif names(appid).index(keep_name[0]) >= store.BACKUP_KEEP - 1:
            P("ⓒ 계측기 무효 — 근거 사본이 축출 꼬리 안에 있다(이 세계의 전제가 깨졌다)")
        else:
            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("ⓒ 등록 해제가 실패했다 — code=%s" % done.get("code"))
            else:
                if COUNT["promoted_plan"] or COUNT["promoted_write"]:
                    P("ⓒ 살아남을 사본을 근거로 두고도 승격했다 — 판정 %d회·쓰기 %d회 "
                      "(멀쩡한 백업의 날짜가 바뀐다)"
                      % (COUNT["promoted_plan"], COUNT["promoted_write"]))
                if COUNT["skipped"] < 1:
                    P("ⓒ 중복인 쪽이 무쓰기로 접히지 않았다 — 계측: %s" % dict(COUNT))
                if keep_name[0] in gone:
                    P("ⓒ 근거 사본이 지워졌다 — %s (축출 꼬리 밖인데 사라졌다)" % keep_name[0])
                if len(promised) != len(gone) or sorted(promised) != sorted(gone):
                    P("ⓒ 예고와 실제가 다르다 — 예고=%s / 실제=%s" % (sorted(promised), sorted(gone)))
                if not holds(appid, store.profile_tag("internal"), INTL):
                    P("ⓒ internal 프로필 내용이 백업에 없다")
                notes.append("ⓒ 승격(판정시점) %d회(0이어야 정상) · 쓰기 %d · 무쓰기 %d"
                             % (COUNT["promoted_plan"], COUNT["wrote"], COUNT["skipped"]))
                check_ring_cap(appid, "ⓒ")

        # ── ⓔ 링 상한 — 대피 대상이 링보다 많아도 `BACKUP_KEEP`을 넘지 않는다 ──
        #    ★ 기각된 「보호 집합」 안이 정확히 여기서 깨진다: 보호 대상이 상한을 넘으면
        #      `keep = BACKUP_KEEP - len(protect)`가 **음수**가 되어 링이 11·13칸이 된다(실측).
        #      본체가 둘뿐인 세계(ⓐⓑⓒ)로는 이 자리에 닿지 못한다 — 그래서 세계를 따로 세운다.
        appid = "9106"
        build(appid)
        extra = store.BACKUP_KEEP + 1
        slotdir = pathlib.Path(store.profile_dir(appid, "dock"))
        for i in range(extra):                            # 슬롯 본체를 상한보다 많이
            (slotdir / ("body%02d.ini" % i)).write_bytes(b"body-%02d\n" % i)
        for i in range(store.BACKUP_KEEP):
            filler(appid, 100 + i)
        if len(store.evacuable_names(appid, "dock")) <= store.BACKUP_KEEP:
            P("ⓔ 계측기 무효 — 대피 대상이 %d개뿐이라 상한을 넘기지 못한다"
              % len(store.evacuable_names(appid, "dock")))
        else:
            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("ⓔ 등록 해제가 실패했다 — code=%s" % done.get("code"))
            check_ring_cap(appid, "ⓔ")
            if len(promised) != len(gone) or sorted(promised) != sorted(gone):
                P("ⓔ 예고와 실제가 다르다 — 예고 %d건 / 실제 %d건" % (len(promised), len(gone)))
            notes.append("ⓔ 본체 %d개·상한 %d: 링 %d칸(≤%d여야 정상) · 예고 %d = 실제 %d"
                         % (extra, store.BACKUP_KEEP, len(names(appid)), store.BACKUP_KEEP,
                            len(promised), len(gone)))

        real_read = store.read_bytes

        # ── ⓘ 비포화 링 + 근거가 최고령 → **무쓰기 · 축출 0** (N-01) ──────────
        #    링이 `BACKUP_KEEP`보다 적으면 이 동작이 써도 **아무도 안 밀려난다.** 그러면 최고령
        #    사본도 살아남으므로 **믿어야 한다.** 여기서 불신하면 정상 중복이 쓰이고, 확인창은
        #    축출 0건이라 아무 이름도 대지 않았는데 **백업이 하나 사라진다.**
        appid = "9109"
        build(appid)
        witness(appid, "dock", DOCK)                  # 최고령 = dock 내용의 근거 사본
        for i in range(store.BACKUP_KEEP - 2):        # 링 = KEEP - 1 (비포화)
            filler(appid, 300 + i)
        seat = holds(appid, store.profile_tag("dock"), DOCK)
        if (len(names(appid)) != store.BACKUP_KEEP - 1 or len(seat) != 1
                or names(appid)[-1] != seat[0]):
            P("ⓘ 계측기 무효 — 링 %d칸(%d이어야 한다) · 근거 %d개 · 최고령 일치=%s"
              % (len(names(appid)), store.BACKUP_KEEP - 1, len(seat),
                 seat[:1] == names(appid)[-1:]))
        else:
            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("ⓘ 등록 해제가 실패했다 — code=%s" % done.get("code"))
            else:
                if gone:
                    P("ⓘ **예고에 없던 백업이 사라졌다** — 예고=%s / 실제 사라짐=%s. 링이 가득 차지 "
                      "않아 아무도 안 밀려나는데 정상 중복을 썼다" % (promised, gone))
                if seat[0] not in names(appid):
                    P("ⓘ 최고령 근거 사본이 사라졌다 — %s (살아남을 자리인데 축출됐다)" % seat[0])
                if COUNT["skipped"] < 1:
                    P("ⓘ 정상 중복이 무쓰기로 접히지 않았다 — 계측: %s" % dict(COUNT))
                if promised:
                    P("ⓘ 축출 예고가 비어 있지 않다 — %s (비포화 링이라 0건이어야 한다)" % promised)
                check_ring_cap(appid, "ⓘ")
                notes.append("ⓘ 비포화(%d칸)·근거가 최고령: 예고 %d · 실제축출 %d · 무쓰기 %d · "
                             "증인 생존 %s · 링 %d"
                             % (store.BACKUP_KEEP - 1, len(promised), len(gone),
                                COUNT["skipped"], seat[0] in names(appid), len(names(appid))))

        # ── ⓚ 상한 초과 링 + 빈 계획 → **예고 0 == 실제 축출 0** (N-03) ────────
        appid = "9111"
        build(appid)
        kbd = pathlib.Path(store.backups_dir(appid))
        kbd.mkdir(parents=True, exist_ok=True)
        #   증인 둘을 **최고령**에 둔다 — 상한 밖 꼬리라 「어차피 잘린다」로 오판하기 쉬운 자리.
        (kbd / "20260101-000000-profile_dock-video.ini").write_bytes(DOCK)
        (kbd / "20260101-000001-profile_internal-video.ini").write_bytes(INTL)
        for i in range(store.BACKUP_KEEP):                # 상한 초과(= KEEP + 2칸)
            (kbd / ("20260301-0000%02d-disk-uniq.ini" % i)).write_bytes(b"uniq-%02d\n" % i)
        kbefore = names(appid)
        kplan = store.plan_backups(store.list_backups(appid), remove._evacuable_items(appid))
        if len(kbefore) != store.BACKUP_KEEP + 2 or kplan:
            P("ⓚ 계측기 무효 — 링 %d칸(%d이어야 한다) · 계획 %d건(0이어야 한다)"
              % (len(kbefore), store.BACKUP_KEEP + 2, len(kplan)))
        else:
            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("ⓚ 등록 해제가 실패했다 — code=%s" % done.get("code"))
            else:
                if promised:
                    P("ⓚ 축출 예고가 비어 있지 않다 — %s (계획 0건이면 0건이어야 한다)" % promised)
                if gone:
                    P("ⓚ **예고 0인데 백업이 사라졌다** — %s. 한 건도 안 쓰면 `prune`이 안 도는데 "
                      "상한 초과 링을 「어차피 잘린다」고 읽었다" % gone)
                if len(names(appid)) != len(kbefore):
                    P("ⓚ 링 칸수가 바뀌었다 — %d → %d (그대로여야 한다)"
                      % (len(kbefore), len(names(appid))))
                if COUNT["skipped"] < 2:
                    P("ⓚ 두 슬롯이 무쓰기로 접히지 않았다 — 계측: %s" % dict(COUNT))
                notes.append("ⓚ 상한 초과(%d칸)·계획 0: 예고 %d · 실제축출 %d · 무쓰기 %d · 링 %d"
                             % (len(kbefore), len(promised), len(gone), COUNT["skipped"],
                                len(names(appid))))

        # ── ⓙ 「살아남는 칸」 계산 — 격자 전수 (N-02) ─────────────────────────
        #    정의: 이 쓰기를 **안 했을 때** 살아남는 칸 = `max(0, 링 - max(0, 링 + 계획 - KEEP))`.
        trusted_fn = getattr(store, "_trusted_entries", None)
        if trusted_fn is None:
            notes.append("ⓙ 이 판본엔 계획 밖 판정 자체가 없다(`_trusted_entries` 부재) — 잴 것이 없다")
        else:
            appid = "9110"
            bd = pathlib.Path(store.backups_dir(appid))
            bad, checked = [], 0
            for ring in (0, 1, 9, store.BACKUP_KEEP, store.BACKUP_KEEP + 2):
                shutil.rmtree(str(bd), ignore_errors=True)
                bd.mkdir(parents=True, exist_ok=True)
                for i in range(ring):                 # prune을 거치지 않고 직접 놓는다
                    (bd / ("20260101-0000%02d-disk-g.ini" % i)).write_bytes(b"g%02d\n" % i)
                have = len(store.list_backups(appid))
                listed = store.list_backups(appid)
                for size in (0, 1, 2, store.BACKUP_KEEP - 1, store.BACKUP_KEEP,
                             store.BACKUP_KEEP + 1, store.BACKUP_KEEP + 4):
                    fake = set(("tag%d" % j, "sha%d" % j) for j in range(size))
                    want = ring_survivors(listed, size, store.BACKUP_KEEP)
                    got = list(trusted_fn(appid, fake))
                    checked += 1
                    if got != want:          # ★ 개수가 아니라 **항목**을 본다(같은 수의 꼬리를 줘도 걸린다)
                        bad.append("링%d·계획%d → 신뢰 %d개%s (%d개여야 하고 항목도 달라진다)"
                                   % (have, size, len(got),
                                      "" if len(got) != len(want) else "(개수는 같다)", len(want)))
            shutil.rmtree(str(bd), ignore_errors=True)
            if bad:
                P("ⓙ 「살아남는 칸」이 정의와 어긋난다 %d칸 — %s%s"
                  % (len(bad), " / ".join(bad[:4]), " …" if len(bad) > 4 else ""))
            if checked < 20:
                P("ⓙ 계측기 무효 — 격자를 %d칸밖에 안 쟀다" % checked)
            # ★ 오라클이 항진식이 아님을 **음성 대조군**으로 보인다: 틀린 답을 주면 걸려야 한다.
            sample = ["e%02d" % i for i in range(store.BACKUP_KEEP)]
            if (ring_survivors(sample, 0, store.BACKUP_KEEP) != sample
                    or len(ring_survivors(sample, 1, store.BACKUP_KEEP)) != store.BACKUP_KEEP - 1
                    or ring_survivors(sample, store.BACKUP_KEEP + 3, store.BACKUP_KEEP) != []):
                P("ⓙ 계측기 무효 — 오라클이 링 동작을 흉내 내지 못한다"
                  "(0건→전부 · 1건→한 칸 밀림 · 상한 초과→전부 밀림 중 하나가 깨졌다)")
            notes.append("ⓙ 「살아남는 칸」 격자 %d칸 대조 · 어긋남 %d칸(0이어야 정상)"
                         % (checked, len(bad)))

        # ── ⓖ 계획 밖 키의 판정도 **축출될 사본을 근거로 삼지 않는다** (D-01) ────
        #    ⓓ와 같은 「계획 뒤 본체가 바뀐다」이지만 **링이 포화**이고 **최고령 칸이 바뀐 내용의
        #    유일한 사본**이다. 계획 밖 판정이 「호출 시점의 링」을 보면 그 최고령을 근거로 삼아
        #    무쓰기가 되고, **뒤 슬롯의 계획된 쓰기가 바로 그 칸을 축출**한다 — 내용이 슬롯에도
        #    링에도 없다(전손). D1이 계획 경로에서 고친 병이 **fallback 경로에 남아 있던 자리**다.
        #    ⚠️ 저장 갈래로는 재현되지 않는다: 저장은 대피가 한 슬롯뿐이라 **뒤따르는 쓰기가 없어**
        #      근거 사본이 축출되지 않는다. 두 슬롯을 차례로 옮기는 삭제라야 도달한다.
        appid = "9108"
        build(appid)
        witness(appid, "dock", MOVED)                 # 최고령 = 바뀐 뒤 내용의 **유일한** 사본
        for i in range(store.BACKUP_KEEP - 1):
            filler(appid, 200 + i)
        only = holds(appid, store.profile_tag("dock"), MOVED)
        if len(names(appid)) != store.BACKUP_KEEP or len(only) != 1 or names(appid)[-1] != only[0]:
            P("ⓖ 계측기 무효 — 링 %d칸 · 근거 %d개 · 최고령 일치=%s"
              % (len(names(appid)), len(only), only[:1] == names(appid)[-1:]))
        else:
            reset()
            dockdir = store.profile_dir(appid, "dock")

            def dock_moves(path):                     # **dock 본체만** 계획 뒤에 바뀐다
                if str(path).startswith(dockdir):
                    with open(path, "wb") as fh:
                        fh.write(MOVED)
                    return MOVED
                return real_read(path)

            store.read_bytes = dock_moves
            try:
                reg = store.load_registry()
                remove.delete_game_data(reg, appid)
                store.save_registry(reg)
                gerr = None
            except Exception as exc:                  # noqa: BLE001
                gerr = "%s: %s" % (type(exc).__name__, exc)
            finally:
                store.read_bytes = real_read
            alive = holds(appid, store.profile_tag("dock"), MOVED)
            if gerr:
                P("ⓖ 등록 해제가 실패했다 — %s" % gerr)
            elif not alive:
                P("ⓖ **전손** — 계획 밖 키가 「축출될 사본」을 근거로 무쓰기가 됐고, 뒤 슬롯의 "
                  "쓰기가 그 사본을 축출했다. 그 내용이 슬롯에도 링에도 없다")
            if COUNT["off_plan"] < 1:
                P("ⓖ 계측기 무효 — 계획 밖 갈래에 한 번도 **닿지** 않았다 (계측: %s)" % dict(COUNT))
            check_ring_cap(appid, "ⓖ")
            notes.append("ⓖ 포화 링·최고령이 유일 근거: 생존 %d(≥1이어야 정상) · 계획밖 도달 %d · "
                         "그중 쓰기 %d · 무쓰기 %d"
                         % (len(alive), COUNT["off_plan"], COUNT["plan_fallback"],
                            COUNT["skipped"]))

        # ── ⓕ 대피는 **할 수 있을 때** 한다 (D4) — 열거 못 해도 저장이 성립한다 ──
        #    `0300` = 쓰기·통과는 되고 **열거만 막힌다**(실측). 그래서 `evacuable_names`가
        #    조용히 빈 목록이 되어 대피가 0건이 되고, 그 다음 디렉터리 fsync가 실패한다.
        #    ⚠️ 잃는 것은 **「이름의 지속」이지 내용의 온전성이 아니다** — 그래서 이 세계는
        #      *"백업이 만들어졌는가"*가 아니라 *"저장이 성립하고 기록과 본체가 맞는가"*를 잰다.
        appid = "9107"
        cfg = build(appid)
        cfg.write_bytes(MOVED)                            # 무쓰기 갈래로 접히지 않게
        slotdir = pathlib.Path(store.profile_dir(appid, "dock"))
        os.chmod(slotdir, 0o300)                          # 열거 불가 · 쓰기 가능
        unchmod.append(slotdir)
        try:                                              # ★ 계측기 자기검증
            os.listdir(slotdir)
            P("ⓕ 계측기 무효 — `0300`인데 열거가 된다(root로 도는가?). 이 세계는 안 쟀다")
        except OSError:
            reg = store.load_registry()
            try:
                engine.save_profile(reg, appid, "dock")
                store.save_registry(reg)
                err = None
            except Exception as exc:                      # noqa: BLE001
                err = "%s: %s" % (type(exc).__name__, exc)
            meta = store.load_meta(appid, "dock")
            body = b""
            if isinstance(meta, dict) and isinstance(meta.get("filename"), str):
                try:
                    body = (slotdir / meta["filename"]).read_bytes()
                except OSError as exc:
                    err = err or "본체를 읽지 못했다: %s" % exc
            paired = isinstance(meta, dict) and store.sha1_bytes(body) == meta.get("sha1")
            if err:
                P("ⓕ 폴더를 열거 못 한다는 이유로 저장이 실패했다 — %s "
                  "(본체는 이미 덮였고 기록만 옛것을 가리킨다 → 그 프로필은 적용도 안 된다)" % err)
            elif not paired:
                P("ⓕ 저장은 성공했다는데 기록과 본체가 어긋난다 — 그 프로필은 적용도 안 된다")
            elif body != MOVED:
                P("ⓕ 슬롯 본체가 새 내용이 아니다")
            notes.append("ⓕ 열거 불가(0300) 저장: 오류=%s · 기록↔본체 일치=%s · 대피 %d건"
                         % (err, paired, len(store.list_backups(appid))))
        os.chmod(slotdir, 0o700)

        # ── ⓓ D6 — 계획을 만든 뒤 본체가 바뀌면 **백업이 만들어진다** ─────────
        #    계획(`sha1_file`)과 쓰기(`read_bytes`) 사이의 창을 실제로 벌린다.
        def moving_read(path):
            if "%sprofiles%s" % (os.sep, os.sep) in str(path):
                with open(path, "wb") as fh:              # 계획이 잡은 지문을 무효로 만든다
                    fh.write(MOVED)
                return MOVED
            return real_read(path)

        # ⓓ-1 저장 갈래
        appid = "9104"
        cfg = build(appid)
        cfg.write_bytes(INTL + b"new\n")                  # 무쓰기 갈래로 접히지 않게
        reset()
        store.read_bytes = moving_read
        try:
            reg = store.load_registry()
            engine.save_profile(reg, appid, "dock")
            saved_err = None
        except Exception as exc:                          # noqa: BLE001
            saved_err = "%s: %s" % (type(exc).__name__, exc)
        finally:
            store.read_bytes = real_read
        if saved_err:
            P("ⓓ-1 저장이 실패했다 — %s" % saved_err)
        elif not holds(appid, store.profile_tag("dock"), MOVED):
            P("ⓓ-1 계획 밖 내용이 **대피 없이** 덮였다 — 백업 링에 그 내용이 없다 (D6 구멍)")
        notes.append("ⓓ-1 저장: 쓰기 %d · 무쓰기 %d · 계획밖 자체판정 %d"
                     % (COUNT["wrote"], COUNT["skipped"], COUNT["plan_fallback"]))

        # ⓓ-2 삭제 갈래
        appid = "9105"
        build(appid)
        reset()
        store.read_bytes = moving_read
        try:
            reg = store.load_registry()
            remove.delete_game_data(reg, appid)
            store.save_registry(reg)
            del_err = None
        except Exception as exc:                          # noqa: BLE001
            del_err = "%s: %s" % (type(exc).__name__, exc)
        finally:
            store.read_bytes = real_read
        if del_err:
            P("ⓓ-2 등록 해제가 실패했다 — %s" % del_err)
        elif len(holds(appid, store.profile_tag("dock"), MOVED)) < 1 or \
                len(holds(appid, store.profile_tag("internal"), MOVED)) < 1:
            P("ⓓ-2 계획 밖 내용이 **대피 없이** rmtree됐다 — 백업 링에 그 내용이 없다 (D6 구멍)")
        notes.append("ⓓ-2 삭제: 쓰기 %d · 무쓰기 %d · 계획밖 자체판정 %d"
                     % (COUNT["wrote"], COUNT["skipped"], COUNT["plan_fallback"]))

        # ── ⓛ 한 동작의 **먼저 쓴 대피본**은 뒤 쓰기의 prune에 안 잘린다 (DEFECT-01 ③) ──
        def stamped_ring(appid, count, years):
            """링을 **직접 놓는다**(prune을 안 지난다). stamp의 **연도만** `years`만큼 민다.

            ★★ **시스템 시각을 건드리지 않는다** — 미는 것은 파일 **이름**뿐이고, 그것이
              `store.backup_order_key`가 읽는 전부다. 시각을 바꾸면 이 검사가 도는 기기의
              다른 모든 것도 같이 바뀐다.
            ★ 연도를 **박아 두지 않는다** — `2027`처럼 적으면 그 해가 지나는 순간 이 세계가
              조용히 **반대편**(과거 stamp)을 재게 되고, 그때도 초록이 뜬다.
            """
            d = pathlib.Path(store.backups_dir(appid))
            shutil.rmtree(str(d), ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
            year = int(time.strftime("%Y")) + years
            for i in range(count):
                (d / ("%04d%02d%02d-1200%02d-disk-o%02d.ini"
                      % (year, (i // 28) + 1, (i % 28) + 1, i, i))).write_bytes(b"o-%02d\n" % i)

        def reads_oldest(appid):
            """**지금 쓰는 백업이 이 링에서 가장 오래된 것으로 읽히는가** — 이 세계의 전제."""
            now = store.backup_order_key("%s-profile_dock-video.ini"
                                         % time.strftime("%Y%m%d-%H%M%S"))
            return now < min(store.backup_order_key(n) for n in names(appid))

        RING = store.BACKUP_KEEP + 2          # 링 12 = 예고 4건이 나오는 자리(실측 최대 피해)
        for tag, years in (("ⓛ-1 삭제·미래stamp", +1), ("ⓛ-2 삭제·정상시각(대조군)", -1)):
            appid = "9112" if years > 0 else "9113"
            build(appid)
            stamped_ring(appid, RING, years)
            if len(names(appid)) != RING:
                P("%s 계측기 무효 — 링 %d칸(%d이어야 한다)" % (tag, len(names(appid)), RING))
                continue
            if reads_oldest(appid) != (years > 0):
                P("%s 계측기 무효 — 「지금 쓴 백업이 최고령으로 읽히는가」가 %s다(이 세계의 전제가 깨졌다)"
                  % (tag, reads_oldest(appid)))
                continue
            promised, rows, gone, done, ask = delete_via_route(appid)
            if not done.get("ok"):
                P("%s 등록 해제가 실패했다 — code=%s" % (tag, done.get("code")))
                continue
            if not promised:
                P("%s 계측기 무효 — 축출 예고가 0건이라 이 세계는 아무것도 안 잰다" % tag)
                continue
            # ① 두 프로필 내용이 **백업에 남는가** — 슬롯은 이미 rmtree됐다
            for prof, data in (("dock", DOCK), ("internal", INTL)):
                if not holds(appid, store.profile_tag(prof), data):
                    P("%s ① **전손** — %s 프로필 내용이 슬롯에도 백업에도 없다. 먼저 쓴 대피본이 "
                      "뒤 쓰기의 prune에 잘렸다(봉투는 evacuated=%s라 보고한다)"
                      % (tag, prof, done.get("data", {}).get("evacuated")))
            # ②③ 예고한 개수·이름 == 실제
            if len(promised) != len(gone):
                P("%s ② 예고 %d건 ≠ 실제 지워진 %d건 (예고=%s / 실제=%s)"
                  % (tag, len(promised), len(gone), sorted(promised), sorted(gone)))
            if sorted(promised) != sorted(gone):
                P("%s ③ 예고한 이름과 실제 지워진 이름이 다르다 — 예고=%s / 실제=%s"
                  % (tag, sorted(promised), sorted(gone)))
            check_ring_cap(appid, tag)
            notes.append("%s 링 %d·최고령으로 읽힘=%s: 예고 %d = 실제 %d · dock남음 %s · "
                         "internal남음 %s · 링 %d"
                         % (tag, RING, years > 0, len(promised), len(gone),
                            bool(holds(appid, store.profile_tag("dock"), DOCK)),
                            bool(holds(appid, store.profile_tag("internal"), INTL)),
                            len(names(appid))))

        # ── ⓛ-3·4 **본체가 둘 이상인 슬롯 저장**도 같은 자리다 (engine 쪽 호출부) ──
        for tag, years in (("ⓛ-3 저장·미래stamp", +1), ("ⓛ-4 저장·정상시각(대조군)", -1)):
            appid = "9114" if years > 0 else "9115"
            cfg = build(appid)
            (pathlib.Path(store.profile_dir(appid, "dock")) / "extra.ini").write_bytes(EXTRA)
            stamped_ring(appid, RING, years)
            cfg.write_bytes(MOVED)                    # 디스크가 슬롯과 달라야 확인창이 뜬다
            if sorted(store.evacuable_names(appid, "dock")) != ["extra.ini", "video.ini"]:
                P("%s 계측기 무효 — dock 본체가 둘이 아니다: %s"
                  % (tag, store.evacuable_names(appid, "dock")))
                continue
            if len(names(appid)) != RING or reads_oldest(appid) != (years > 0):
                P("%s 계측기 무효 — 링 %d칸 · 최고령으로 읽힘=%s"
                  % (tag, len(names(appid)), reads_oldest(appid)))
                continue
            before = names(appid)
            ask = rpc(main, "save_profile", appid, "dock")
            p = ask.get("params") or {}
            promised = [r["backup_id"] for r in (p.get("evicted") or [])]
            reset()
            done = rpc(main, "save_profile", appid, "dock", confirm_token=p.get("confirm_token"))
            gone = [n for n in before if n not in names(appid)]
            if not done.get("ok"):
                P("%s 저장이 실패했다 — code=%s params=%s" % (tag, done.get("code"), p))
                continue
            if len(promised) < 2:
                P("%s 계측기 무효 — 축출 예고가 %d건이다(본체 둘을 대피시키면 2건 이상이어야 한다)"
                  % (tag, len(promised)))
                continue
            # ① 대피본 **둘 다** 링에 남는가 — 먼저 쓴 쪽(extra.ini = 이름순 앞)이 잘리던 자리다
            for what, data in (("extra.ini(먼저 쓴 쪽)", EXTRA), ("video.ini", DOCK)):
                if not holds(appid, store.profile_tag("dock"), data):
                    P("%s ① %s의 대피본이 링에 없다 — 먼저 쓴 대피본이 뒤 쓰기의 prune에 잘렸다"
                      % (tag, what))
            if len(promised) != len(gone) or sorted(promised) != sorted(gone):
                P("%s ②③ 예고와 실제가 다르다 — 예고=%s / 실제=%s"
                  % (tag, sorted(promised), sorted(gone)))
            check_ring_cap(appid, tag)
            notes.append("%s 링 %d·최고령으로 읽힘=%s: 예고 %d = 실제 %d · extra남음 %s · "
                         "video남음 %s · 링 %d"
                         % (tag, RING, years > 0, len(promised), len(gone),
                            bool(holds(appid, store.profile_tag("dock"), EXTRA)),
                            bool(holds(appid, store.profile_tag("dock"), DOCK)),
                            len(names(appid))))

        print("대피 계획은 동작 경계에서 한 번 — ⓐ앞 / ⓑ뒤 / ⓒ음성 대조군(승격 0) / "
              "ⓓD6 계획↔쓰기 창(저장·삭제) / ⓔ링 상한 / ⓕ열거 불가에도 저장 성립 / "
              "ⓖ계획 밖 판정도 축출될 사본을 안 믿는다 / ⓘ비포화 링에서는 증인을 믿는다 / "
              "ⓙ살아남는 칸 격자 / ⓚ상한 초과+빈 계획 / "
              "ⓛ먼저 쓴 대피본은 뒤 쓰기의 prune에 안 잘린다(삭제·저장 × 미래stamp·정상시각)  "
              "(데이터: %s)" % tmp)
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
