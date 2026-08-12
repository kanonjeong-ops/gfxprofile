"use strict";
/**
 * 표시명 덮어쓰기(F11 ①)를 **실제 i18n 모듈을 돌려서** 잰다.
 *
 * 왜 이 프로브가 필요한가: 표시명은 `t("PROFILE_DOCK")`을 지나는 **모든 화면**을 한 번에
 * 바꾼다. 그 "한 번에"가 성립하는지는 문자열 표를 읽어서는 알 수 없고, `t()`를 실제로 불러
 * 봐야 안다. 그리고 **식별자는 이 경로로 절대 움직이지 않는다**는 것도 여기서 같이 본다 —
 * 덮어쓰기의 대상은 표시 키 2개뿐이어야 한다.
 *
 * 실행: node qa/i18n_names_probe.cjs [소스디렉터리]
 * 출력: JSON 한 줄.
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(projectRoot, "src");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));

const modules = {
  // 언어 확정 RPC는 이 프로브의 관심사가 아니다 — 영영 안 오는 것으로 둔다(행 경로는 별도 테스트).
  "./rpc": { uiHello: () => new Promise(() => {}) },
};

function load(rel) {
  const file = path.join(srcDir, rel);
  const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true, resolveJsonModule: true,
    }, fileName: file,
  }).outputText;
  const exports = {};
  const req = (name) => {
    if (modules[name]) return modules[name];
    if (name.startsWith(".")) {
      const base = name.replace(/^\.\//, "");
      for (const ext of [".ts", ".tsx", ".json", ""]) {
        const p = path.join(srcDir, base + ext);
        if (!fs.existsSync(p) || !fs.statSync(p).isFile()) continue;
        // ★ 확장자는 **찾아낸 파일**로 판정한다. 요청 문자열에 이미 `.json`이 붙어 있으면
        //   빈 확장자로 먼저 맞아떨어지는데, 그때 TS 트랜스파일러에 넘기면 통째로 죽는다.
        return p.endsWith(".json") ? JSON.parse(fs.readFileSync(p, "utf8")) : load(base + ext);
      }
    }
    throw new Error("unmocked: " + name);
  };
  new Function("exports", "require", "module", compiled)(exports, req, { exports });
  return exports;
}

const i18n = load("i18n.ts");
const ko = JSON.parse(fs.readFileSync(path.join(srcDir, "i18n", "ko.json"), "utf8"));
i18n.setLang("ko");

const out = {};
out.defaultDock = i18n.t("PROFILE_DOCK");
out.defaultInternal = i18n.t("PROFILE_INTERNAL");
// 기본 이름은 번역표 그대로여야 한다(덮어쓰기 이전 상태 = 아무 것도 안 한 상태)
out.defaultMatchesTable = out.defaultDock === ko.PROFILE_DOCK;

// ── 덮어쓰기 ────────────────────────────────────────────────────────────────
i18n.setProfileNames({ dock: "거실 TV", internal: "" });
out.afterDock = i18n.t("PROFILE_DOCK");
out.afterInternal = i18n.t("PROFILE_INTERNAL");        // 빈 값 = 기본 이름 그대로
out.tDefaultDock = i18n.tDefault("PROFILE_DOCK");      // 편집창이 "비우면 돌아갈 이름"을 말할 때 쓴다
// ★ 이름이 **문장 안에서도** 따라오는가 — 라벨이 각자 이름을 박아 두면 여기서 갈린다.
out.bulkLabel = i18n.t("BULK_APPLY", { profile: i18n.t("PROFILE_DOCK") });
out.applyShort = i18n.t("APPLY_SHORT", { profile: i18n.t("PROFILE_DOCK") });
out.saveShort = i18n.t("SAVE_SHORT", { profile: i18n.t("PROFILE_DOCK") });
// ★ 덮어쓰기의 사정거리 — 다른 키는 하나도 안 변해야 한다(식별자·문구 오염 방지).
// (P15: 옛 대조 키 `TAB_MANAGE`는 전체화면 탭과 함께 사라졌다 — 프로필 이름과 무관한
//  아무 키나 되지만, **자리표시자가 없는 키**여야 대조가 값 그대로 성립한다.)
out.unrelatedKey = i18n.t("GAMES_TITLE");
out.unrelatedMatchesTable = out.unrelatedKey === ko.GAMES_TITLE;

// ── 되돌리기: 공백만 입력은 기본 이름 ────────────────────────────────────────
i18n.setProfileNames({ dock: "   ", internal: "내장" });
out.blankResetsDock = i18n.t("PROFILE_DOCK");
out.internalAfter = i18n.t("PROFILE_INTERNAL");
i18n.setProfileNames(null);                             // 봉투가 없을 때(조회 실패 등)
out.nullResetsDock = i18n.t("PROFILE_DOCK");
out.nullResetsInternal = i18n.t("PROFILE_INTERNAL");

console.log(JSON.stringify(out));
