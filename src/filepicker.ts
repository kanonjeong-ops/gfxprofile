// ★ `openFilePicker`를 부르는 **유일한 파일**이다. 선택기의 함정 3개를 여기 한 곳에 가둔다 —
//   호출부마다 기억해서 처리하는 방식이면 언젠가 한 곳이 빠지고, 빠진 곳이 곧 버그가 된다.
//
//   ① **취소는 resolve가 아니라 `reject('User canceled')`다**(로더 `plugin-loader.tsx:607` 실물).
//      `.then`만 붙이면 사용자가 뒤로가기를 누를 때마다 unhandled rejection이 난다.
//      취소는 **정상 흐름**이므로 조용히 끝내야 한다 — 오류 토스트를 띄우면 그게 오정보다.
//   ② **`filter` 인자는 구조적으로 무효다.** 선택기는 filter를 백엔드 RPC 인자로 그대로 넘기고
//      로더의 소켓 전송은 `JSON.stringify`다 — `RegExp`는 `{}`가 되고 함수는 `null`이 된다.
//      **넘기지 않는다.**
//   ③ **`extensions`도 넘기지 않는다.** `allowAllFiles` 기본값이 true라 어차피 풀리고,
//      우리 도메인은 애초에 확장자로 못 거른다(실데이터 후보에 `UserConfigSelections`처럼
//      확장자가 없는 파일이 있다). 걸러지지도 않으면서 정상 파일만 숨긴다.
//
//   → **`.sav` 차단은 선택기가 아니라 백엔드 G14가 유일한 방어선이다.**

import { openFilePicker } from "@decky/api";

/**
 * `FileSelectionType.FILE`(=0).
 *
 * ⚠️ `FileSelectionType`은 `declare const enum`이라 **값으로 import하지 않는다.**
 *   지금 tsconfig에서는 tsc가 값을 인라인해 주지만, 파일 단위로 컴파일하는 환경
 *   (`isolatedModules`·`transpileModule`)에서는 인라인이 불가능해 런타임에 `undefined`가 된다.
 *   숫자를 직접 쓰고 타입만 시그니처에서 빌려 온다 — 컴파일 방식에 묶이지 않는다.
 */
const SELECT_FILE = 0 as unknown as Parameters<typeof openFilePicker>[0];

/**
 * 설정 파일을 고르게 한다. **취소하면 `null`** — 예외로 새어 나가지 않는다.
 *
 * ★ 백엔드에 넘기는 것은 `realpath`가 아니라 **`path`**다. `check_path`(G11)는
 *   `os.path.islink(path)`를 **먼저** 보므로, realpath를 넘기면 심볼릭 링크 거부가
 *   조용히 무력화된다. 가드가 볼 수 있는 값을 그대로 넘긴다.
 */
export function pickConfigFile(startPath: string): Promise<string | null> {
  return openFilePicker(SELECT_FILE, startPath, true, true).then(
    (res) => res.path,
    () => null, // 'User canceled' — 정상 흐름이다. 아무 것도 하지 않는다.
  );
}
