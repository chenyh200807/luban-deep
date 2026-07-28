var fs = require("fs");
var path = require("path");

var repoRoot = path.join(__dirname, "../..");
var pass = 0;
var fail = 0;
var errors = [];

function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

function assertIncludes(source, token, message) {
  if (source.indexOf(token) >= 0) pass++;
  else {
    fail++;
    errors.push("FAIL: " + message + " missing " + token);
  }
}

var shadowJs = read("wx_miniprogram/pages/chat/chat.js");
var shadowWxml = read("wx_miniprogram/pages/chat/chat.wxml");
var productionJs = read("yousenwebview/packageDeeptutor/pages/chat/chat.js");
var productionWxml = read("yousenwebview/packageDeeptutor/pages/chat/chat.wxml");
var tutorSkill = read("deeptutor/tutorbot/skills/construction-exam-tutor/SKILL.md");

assertIncludes(shadowJs, 'desc: "建筑实务考点梳理"', "shadow knowledge map scope");
assertIncludes(shadowWxml, "直接问建筑实务：考点、真题、规范、错题", "shadow input scope");
assertIncludes(productionJs, 'desc: "建筑实务考点梳理"', "production knowledge map scope");
// 生产版首屏 placeholder 在 2026-07-28 改成了「粘贴答案」引导（批改入口）。
// 断言不再钉死旧字面量，改为钉死**职责**：placeholder 单一定义处必须仍点明「建筑实务」，
// 否则输入框这一层的跨专业披露就丢了。影子版 wx_miniprogram 未改版，仍按旧字面量断言。
(function assertProductionInputScope() {
  var match = /var CHAT_INPUT_PLACEHOLDER = "([^"]*)";/.exec(productionJs);
  if (!match) {
    fail++;
    errors.push("FAIL: production input scope — CHAT_INPUT_PLACEHOLDER 单一定义处不见了");
    return;
  }
  assertIncludes(match[1], "建筑实务", "production input scope placeholder");
})();
[shadowWxml, productionWxml].forEach(function (source) {
  assertIncludes(
    source,
    "当前深度覆盖一建建筑实务，其他专业陆续上线",
    "visible coverage disclosure",
  );
});
assertIncludes(tutorSkill, "## 覆盖范围诚实声明（非建筑专业）", "skill policy");
assertIncludes(tutorSkill, "不得把建筑实务的条文、数值、案例采分点", "anti-fabrication policy");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_cross_subject_honesty.js (" + pass + " assertions)");
