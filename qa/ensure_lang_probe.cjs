"use strict";
/**
 * `ensureLang`이 **어떤 경우에도 정착(settle)하는지** 잰다.
 *
 * 왜: 2026-08-06 QA R2 지적 ⑬ — 주석엔 "기다림은 반드시 끝낸다"고 적혀 있었으나 실제로는
 *   ① 응답이 영영 안 오는 경우(행) ② `{ok:true}`인데 data가 없어 성공 핸들러가 던지는 경우가
 *   **정착하지 않았다.** 라우트가 `langReady`를 영원히 못 받아 **화면이 영구히 빈다.**
 *   "안 끝나는 것"은 예외를 안 던지므로 일반 테스트로는 안 잡힌다 — 시간 제한을 두고 재야 한다.
 *
 * 실행: node qa/ensure_lang_probe.cjs   (JSON 한 줄 출력)
 */
const fs = require("fs");
const path = require("path");
const projectRoot = path.resolve(__dirname, "..");
const ts = require(path.join(projectRoot, "node_modules", "typescript"));
const cases={
  "행(응답 없음)": () => new Promise(()=>{}),
  "거부": () => Promise.reject(new Error("boom")),
  "ok:false": () => Promise.resolve({ok:false, code:"X"}),
  "ok:true인데 data 없음": () => Promise.resolve({ok:true}),
  "정상": () => Promise.resolve({ok:true, data:{lang:"ko"}}),
};
const out = {};
(async () => {
  for (const [name, impl] of Object.entries(cases)) {
    const src=fs.readFileSync(path.join(projectRoot,"src","i18n.ts"),"utf8");
    const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
    const exports={};
    const req=(n)=> n==="./rpc" ? {uiHello: impl} : (n.includes("json") ? JSON.parse(fs.readFileSync(path.join(projectRoot, "src", n.replace("./","")),"utf8")) : {});
    new Function("exports","require","module",js)(exports,req,{exports});
    let settled="NEVER-SETTLED";
    const p=exports.ensureLang("0","t").then(r=>{settled="RESOLVE "+JSON.stringify(r);},e=>{settled="REJECT "+e;});
    await Promise.race([p, new Promise(r=>setTimeout(r,4000))]);
    out[name] = settled;
  }
  console.log(JSON.stringify(out));
})();
