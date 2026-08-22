// Decky 자신의 설치 경로로 로컬 ZIP을 설치한다 (sudo 불필요 · 실사용자와 같은 경로).
//   loader v3.2.6: utilities/install_plugin → 프롬프트 emit → utilities/confirm_plugin_install
//   artifact가 file:// 로 시작하면 로더가 로컬 ZIP을 그대로 연다(browser.py:194-197).
// ★ ZIP 최상위 폴더명이 곧 런타임 경로(data/settings/logs)가 된다 — plugin.json의 name이 아니다.
//
// ★ 이 파일은 **템플릿**이다. `build.sh package`가 경로와 sha256을 박아
//   `pkg/install.js`를 생성한다. 이 파일을 그대로 실행하지 마라.
(async () => {
  const ZIP = "__ZIP_PATH__";
  const SHA256 = "__ZIP_SHA256__";
  // ★ NAME은 **plugin.json의 name(표시명)**이다. IDENT(ZIP 폴더명)가 아니다 —
  //   로더가 이 값으로 매니페스트를 매칭한다(browser.py). 둘을 혼동하면 설치가 죽는다(E19).
  const NAME = "__PLUGIN_NAME__";
  const VERSION = "__PLUGIN_VERSION__";

  const B = window.DeckyBackend;
  if (!B) return "DeckyBackend 없음";
  if (ZIP.indexOf("__") === 0) return "템플릿을 그대로 실행했다 — build.sh package로 생성한 pkg/install.js를 쓸 것";

  let rid = null;
  // ★ 이름·버전으로 **우리 요청만** 받는다. 이 이벤트는 전역이라, 필터 없이 마지막 request_id를
  //   집으면 남의 플러그인 설치를 대신 확정할 수 있다. confirm은 조회가 아니라 실제 설치다.
  const onPrompt = (name, version, request_id) => {
    if (name === NAME && version === VERSION && rid === null) rid = request_id;
  };
  B.addEventListener("loader/add_plugin_install_prompt", onPrompt);
  try {
    // hash를 문자열로 넘기면 로더가 검증한다 — 손상·낡은 ZIP이 **그대로 풀리는 것**을 막는다.
    // ⚠️ 검증을 켜도 **기존 설치를 먼저 지운 뒤 실패하는 갈래는 그대로 있다**(browser.py:
    //    삭제 → 추출 순서, 해시 비교는 추출 함수 안이다). 검증을 끄면 거기서 더 나아가
    //    **깨진 것이 풀린다.** 즉 이 인자가 가르는 것은 「지워지는가」가 아니라
    //    「지워진 자리에 무엇이 들어가는가」다. (2026-08-23 상류 소스로 실증)
    await B.call("utilities/install_plugin", "file://" + ZIP, NAME, VERSION, SHA256);
    for (let i = 0; i < 60 && rid === null; i++) await new Promise((r) => setTimeout(r, 100));
    if (rid === null) return "우리 설치 프롬프트(request_id)를 못 받음";
    await B.call("utilities/confirm_plugin_install", rid);
    // ⚠️ 알려진 한계: Decky 자신의 listener도 같은 이벤트로 확인 모달을 띄운다. 우리가 백엔드로
    //    직접 confirm하면 그 모달이 화면에 남을 수 있고, 나중에 누르면 이미 pop된 id를 다시 부른다.
    //    무해하지만(요청 map에 없어 실패), 모달이 보이면 그냥 닫으면 된다.
    return "confirmed request_id=" + rid + " sha256=" + SHA256.slice(0, 12);
  } catch (e) {
    return "예외: " + (e && e.message ? e.message : String(e));
  } finally {
    B.removeEventListener("loader/add_plugin_install_prompt", onPrompt);
  }
})()
