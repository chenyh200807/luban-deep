// test_practice_entry_prompts.js — regression checks for focus/practice prompt contracts
// Run: node wx_miniprogram/tests/test_practice_entry_prompts.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var chatJs = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.js"),
  "utf8",
);
var practiceJs = fs.readFileSync(
  path.join(__dirname, "../pages/practice/practice.js"),
  "utf8",
);

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

assert(
  chatJs.indexOf("请给我来5道高价值选择题，不要提前给答案和解析。") >= 0,
  "focus prompt should request 5 choice questions without upfront answers",
);
assert(
  practiceJs.indexOf("给我来5道高价值选择题，不要提前给答案和解析。") >= 0,
  "practice smart mode should align with structured 5-question contract",
);
assert(
  practiceJs.indexOf("请给我来5道选择题，不要提前给答案和解析。") >= 0,
  "practice chapter entry should request 5 choice questions without upfront answers",
);
assert(
  practiceJs.indexOf("每次只出一题") === -1,
  "practice prompts should not promise single-question sequencing that the current UI does not implement",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_practice_entry_prompts.js (" + pass + " assertions)");
