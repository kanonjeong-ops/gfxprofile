// `openFilePicker` 호출을 여기 한 곳에 모은다.
//
// ① 선택기가 거부한 Promise는 `null`로 접어 호출부로 예외를 내보내지 않는다.
// ② `filter`·`extensions`는 넘기지 않는다.
//
// `.sav` 차단은 선택기가 아니라 백엔드 G14가 유일한 방어선이다.

import { openFilePicker } from "@decky/api";

/**
 * `FileSelectionType.FILE`의 값은 0이다.
 *
 * `FileSelectionType`은 ambient const enum이고 런타임 모듈에는 값 export가 없다.
 * 숫자를 직접 쓰고 `openFilePicker` 시그니처에서 타입만 가져온다.
 */
const SELECT_FILE = 0 as unknown as Parameters<typeof openFilePicker>[0];

/**
 * 설정 파일을 고르게 한다. 선택기가 거부하면 `null`을 돌려준다.
 *
 * 백엔드에 넘기는 것은 `realpath`가 아니라 `path`다. `check_path`(G11)가 `os.path.islink`를
 *   먼저 보므로, realpath를 넘기면 심볼릭 링크 거부가 조용히 무력화된다.
 *   가드가 볼 수 있는 값을 그대로 넘긴다.
 */
export function pickConfigFile(startPath: string): Promise<string | null> {
  return openFilePicker(SELECT_FILE, startPath, true, true).then(
    (res) => res.path,
    () => null,
  );
}
