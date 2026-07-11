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
assertIncludes(productionJs, "直接问建筑实务：考点、真题、规范、错题", "production input scope");
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
