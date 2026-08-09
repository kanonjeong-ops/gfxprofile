#!/usr/bin/env python3
"""배포 ZIP 안에서 **RPC가 살아 있는지** 검사한다 — 설계 E19 (B)의 단일 정본.

무엇을 보는가:
    ZIP 안 `dist/index.js`에 `@decky/rollup`이 구워 넣은 `manifest`의 `name`이,
    같은 ZIP 안 `plugin.json`의 `name`과 같은지.

왜 이것이 RPC 생존인가:
    프론트의 `callable`은 그 baked manifest name을 **라우팅 키**로 쓴다. `plugin.json`만 고치고
    번들을 다시 굽지 않으면 프론트가 옛 이름으로 백엔드를 부르다 죽는다.

★ 왜 별도 파일인가 (2026-08-06 QA 지적 ①):
    이 로직이 `build.sh` 안에만 있었을 때는 **FAIL하는 입력을 만들 수 없었다** —
    `build.sh package`가 항상 `pnpm run build`를 선행해 dist를 새로 굽기 때문에, 낡은 dist를
    심어도 재빌드가 덮어썼다. 즉 "검사"가 자기 파이프라인 안에서 구조적으로 항상 참이었고,
    그런데도 테스트 독스트링에는 **작동하지 않는 반증 케이스가 문서로 박혀** 있었다.
    → 로직을 여기로 빼서 **임의의 ZIP을 인자로 받게** 했다. 이제 테스트가 변조한 ZIP 사본을
      만들어 이 함수가 실제로 거부하는지 **실행으로** 확인할 수 있다.

사용:
    from check_zip_manifest import verify        # ValueError를 던진다
    python3 qa/check_zip_manifest.py <zip> <ident>
"""
import json
import re
import sys
import zipfile

MANIFEST_RE = re.compile(r"manifest\s*=\s*(\{.*?\})", re.S)


def verify(zip_path, ident):
    """ZIP 안 번들의 manifest.name == plugin.json의 name 인지 확인. 어긋나면 ValueError."""
    with zipfile.ZipFile(zip_path) as z:
        try:
            manifest_name = json.loads(z.read(f"{ident}/plugin.json"))["name"]
        except KeyError:
            raise ValueError(f"ZIP에 {ident}/plugin.json이 없다 (최상위 폴더명이 {ident}가 맞나?)")
        try:
            bundle = z.read(f"{ident}/dist/index.js").decode("utf-8", "replace")
        except KeyError:
            raise ValueError(f"ZIP에 {ident}/dist/index.js가 없다")

    m = MANIFEST_RE.search(bundle)
    if not m:
        # fail-closed — 못 찾으면 통과가 아니라 실패다. 번들 형식이 바뀌면 검사가 조용히
        # 무력화되는 패턴을 이 프로젝트가 이미 두 번 겪었다.
        raise ValueError("dist/index.js에서 baked manifest를 찾지 못했다 (번들 형식이 바뀌었나?)")
    try:
        baked = json.loads(m.group(1)).get("name")
    except json.JSONDecodeError as e:
        # ★ QA 지적 ④: 비탐욕 정규식이라 manifest에 중첩 객체가 생기면 첫 `}`에서 끊긴다.
        #   예전엔 여기서 JSONDecodeError 트레이스백으로 죽어, 위의 fail-closed 진단 메시지를
        #   **건너뛰었다.** 판정 대신 크래시하지 않도록 같은 갈래로 합류시킨다.
        raise ValueError(f"baked manifest를 해석하지 못했다 — 번들 형식이 바뀌었을 수 있다 ({e})")

    if baked != manifest_name:
        raise ValueError(
            f"번들에 박힌 manifest.name({baked!r})이 plugin.json의 name({manifest_name!r})과 다르다 "
            f"— dist를 다시 빌드하지 않았다. 이대로 설치하면 RPC가 죽는다")
    return manifest_name


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        name = verify(sys.argv[1], sys.argv[2])
    except ValueError as e:
        sys.exit(f"FAIL {e}")
    print(f"PASS RPC 생존 — manifest.name = {name!r}")
