// test_interaction_hints.js — learner-facing affordance hints should cover hidden tap targets
// Run: node yousenwebview/tests/test_interaction_hints.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", rel), "utf8");
}

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

var practiceWxml = read("pages/practice/practice.wxml");
var practiceWxss = read("pages/practice/practice.wxss");
var historyWxml = read("pages/history/history.wxml");
var historyWxss = read("pages/history/history.wxss");
var mistakeWxml = read("pages/mistake-book/mistake-book.wxml");
var mistakeWxss = read("pages/mistake-book/mistake-book.wxss");
var assessmentWxml = read("pages/assessment/assessment.wxml");
var assessmentWxss = read("pages/assessment/assessment.wxss");
var reportWxml = read("pages/report/report.wxml");

assert(
  practiceWxml.indexOf("点 Logo 回首页") >= 0 &&
    practiceWxml.indexOf('aria-label="回到对话首页"') >= 0 &&
    practiceWxss.indexOf(".nav-logo-tip") >= 0,
  "practice page logo should visibly explain it returns to the home conversation",
);
assert(
  practiceWxml.indexOf("点卡片会回到对话，并生成对应训练") >= 0 &&
    practiceWxss.indexOf(".section-hint") >= 0,
  "practice mode cards should explain their cross-page action before first use",
);
assert(
  historyWxml.indexOf("点对话继续；右侧按钮可归档或删除。") >= 0 &&
    historyWxss.indexOf(".history-entry-hint") >= 0,
  "history page should explain row and management affordances",
);
assert(
  mistakeWxml.indexOf("点错题卡片或“看解析”，可回到当时解析依据。") >= 0 &&
    mistakeWxss.indexOf(".mb-list-hint") >= 0,
  "mistake book should explain that cards open the original explanation",
);
assert(
  assessmentWxml.indexOf("点数字可跳题，已选答案会保留。") >= 0 &&
    assessmentWxss.indexOf(".answer-card-hint") >= 0,
  "assessment answer sheet should explain jump navigation",
);
assert(
  reportWxml.indexOf("先看结论 · 想深入再点开") >= 0 &&
    reportWxml.indexOf("点任意格 · 深链学习站") >= 0,
  "report 10e diagnosis sheet should explain its read-then-drill affordances (header + map cell hint)",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_interaction_hints.js (" + pass + " assertions)");
