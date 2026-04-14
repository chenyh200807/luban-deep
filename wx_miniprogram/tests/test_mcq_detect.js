// test_mcq_detect.js — regression tests for wx_miniprogram/utils/mcq-detect.js
// Run: node wx_miniprogram/tests/test_mcq_detect.js

var mcq = require("../utils/mcq-detect");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function assertEqual(actual, expected, message) {
  var ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

run("markdown headings with bulleted options detect three cards", function () {
  var text = [
    "先做下面 3 题。",
    "",
    "### **第1题（单选题）**",
    "施工组织设计首先应明确什么？",
    "- A. 施工部署",
    "- B. 办公室装修",
    "",
    "### **第2题（判断题）**",
    "总时差用来判断是否影响总工期。",
    "- A. 对",
    "- B. 错",
    "",
    "### **第3题（单选题）**",
    "自由时差是指什么？",
    "- A. 不影响总工期的机动时间",
    "- B. 不影响紧后工作最早开始的机动时间",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 3, "should detect 3 questions");
  assertEqual(
    detected.questions.map(function (q) {
      return q.options.length;
    }),
    [2, 2, 2],
    "each question keeps its options",
  );
});

run("mixed choice and open question keep unresolved block in display text", function () {
  var text = [
    "我先给你三题。",
    "",
    "### **第1题（单选题）**",
    "屋面防水卷材施工前，基层应满足哪项要求？",
    "- A. 含水率适宜且表面平整",
    "- B. 可带明水直接铺贴",
    "",
    "### **第2题（单选题）**",
    "地基承载力验算关注什么？",
    "- A. 装饰色差",
    "- B. 土体稳定",
    "",
    "### **第3题（情景题）**",
    "请说明 CFG 桩复合地基面积置换率如何计算。",
    "",
    "### **答案与核心解析**",
    "这里不应该在前端提前展示。",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 2, "only choice questions become cards");
  assert(
    String(detected.displayText || "").indexOf("第3题（情景题）") >= 0,
    "open question should stay in display text",
  );
  assert(
    String(detected.displayText || "").indexOf("答案与核心解析") === -1,
    "answer section should be stripped",
  );
});

run("inline question title format still splits correctly", function () {
  var text = [
    "**题目1：概念判断**",
    "软土地基上最不合适的基础是？",
    "A. 筏板基础",
    "B. 箱形基础",
    "C. 独立基础",
    "D. 桩基础",
    "",
    "**题目2：参数选择**",
    "施工控制干密度不应小于多少？",
    "A. 1.67",
    "B. 1.68",
    "C. 1.69",
    "D. 1.70",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 2, "should detect 2 inline-titled questions");
  assertEqual(
    detected.questions.map(function (q) {
      return q.index;
    }),
    [1, 2],
    "question indexes should be stable",
  );
});

run("interleaved answers do not truncate later examples", function () {
  var text = [
    "好，地基基础是实务的重难点。",
    "",
    "### **一、概念判断**",
    "**例题1：** 关于土方回填，下列说法正确的是（ ）。",
    "A. 填方土料应尽量采用同类土",
    "B. 填土应从场地最低处开始，由下而上分层铺填",
    "C. 填方应在相对两侧或周围同时进行回填和夯实",
    "D. 当天填土，应在当天压实",
    "",
    "**答案与解析：**",
    "**正确答案：A、C、D**",
    "",
    "### **二、参数选择**",
    "**例题2：** 某基坑深6m，采用一级放坡，其坡顶有静载。根据规范，该基坑的坡度值最可能是（ ）。",
    "A. 1:0.5",
    "B. 1:0.75",
    "C. 1:1.0",
    "D. 1:1.25",
    "",
    "**答案与解析：**",
    "**正确答案：C**",
    "",
    "### **三、案例实操**",
    "**例题3：** 有哪些可行的地基处理措施可以减小基础底面积？",
    "",
    "**答案与解析：**",
    "略",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 2, "two choice examples should remain interactive");
  assert(
    String(detected.displayText || "").indexOf("例题3") >= 0,
    "case example should remain in display text",
  );
  assert(
    String(detected.displayText || "").indexOf("正确答案") === -1,
    "interleaved answers should not leak into display text",
  );
});

if (fail > 0) {
  console.error("mcq-detect tests failed: " + fail + " failed, " + pass + " passed");
  for (var i = 0; i < errors.length; i++) console.error(errors[i]);
  process.exit(1);
}

console.log("mcq-detect tests passed: " + pass);
