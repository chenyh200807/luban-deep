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

run("chinese numbered titles split correctly", function () {
  var text = [
    "题目一：建筑构造",
    "防火门构造的基本要求有（ ）。",
    "A. 甲级防火门耐火极限为 1.5h",
    "B. 向内开启",
    "C. 关闭后应能从内外两侧手动开启",
    "D. 具有自行关闭功能",
    "E. 开启后，门扇不应跨越变形缝",
    "",
    "题目二：屋面工程",
    "倒置式屋面保温层应设置在（ ）。",
    "A. 找平层下",
    "B. 防水层上",
    "C. 结构层上",
    "D. 保护层下",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 2, "should detect 2 chinese-numbered questions");
  assertEqual(
    detected.questions.map(function (q) {
      return q.questionType;
    }),
    ["multi_choice", "single_choice"],
    "question types should stay stable",
  );
});

run("explanation prefix remains visible when bare question marker is used", function () {
  var text = [
    "我先给你讲解防水工程的核心知识点，然后出一道选择题。",
    "",
    "## 防水工程核心知识讲解",
    "",
    "### 一、屋面防水",
    "1. 防水层应按等级和设防要求设置。",
    "",
    "## 现在给你出一道选择题：",
    "",
    "**题目：** 关于室内防水工程，下列做法正确的是：",
    "",
    "A. 卫生间墙面防水层高度做到1.2m即可",
    "B. 淋浴区墙面防水层高度应不小于1.8m",
    "C. 厨房地面不需要做防水层",
    "D. 独立水容器防水不属于室内防水范畴",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 1, "should detect a single question card");
  assert(
    String(detected.displayText || "").indexOf("防水工程核心知识讲解") >= 0,
    "explanation prefix should remain in display text",
  );
  assertEqual(
    detected.questions[0].stem,
    "关于室内防水工程，下列做法正确的是：",
    "stem should keep only the choice question",
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

run("answer explanation with A/B/C/D conditions should not become first card", function () {
  var text = [
    "**第一题的答案：**",
    "",
    "**需要专家论证。**",
    "",
    "**判断依据：**",
    "混凝土模板支撑工程，需要专家论证的条件包括：",
    "A. 搭设高度 5m 及以上",
    "B. 搭设跨度 10m 及以上",
    "C. 施工总荷载 10kN/m² 及以上",
    "D. 集中线荷载 15kN/m 及以上",
    "",
    "题目中建筑高度较大，因此该工程需要组织专家论证。",
    "",
    "**第二题（选择题）：**",
    "",
    "**题目：**",
    "关于建筑幕墙工程的安全管理，下列说法正确的是：",
    "",
    "A. 建筑幕墙安装工程属于危险性较大的分部分项工程",
    "B. 幕墙施工不需要编制专项施工方案",
    "C. 高处作业吊篮不需要专项验收",
    "D. 幕墙安装前无需进行技术交底",
  ].join("\n");

  var detected = mcq.detect(text);
  assert(detected, "detected should exist");
  assertEqual(detected.total, 1, "only the real second question becomes a card");
  assert(
    String(detected.displayText || "").indexOf("第一题的答案") >= 0,
    "first answer explanation should remain visible",
  );
  assert(
    String(detected.stem || "").indexOf("关于建筑幕墙工程的安全管理") >= 0,
    "card stem should come from the actual second question",
  );
});

run("standalone answer explanation with option-like lines should not become mcq", function () {
  var text = [
    "**第一题的答案：**",
    "",
    "**需要专家论证。**",
    "",
    "**判断依据：**",
    "混凝土模板支撑工程，需要专家论证的条件包括：",
    "A. 搭设高度 5m 及以上",
    "B. 搭设跨度 10m 及以上",
    "C. 施工总荷载 10kN/m² 及以上",
    "D. 集中线荷载 15kN/m 及以上",
    "",
    "**踩分点：**",
    "1. 直接判断需要专家论证",
    "2. 明确依据是住建部令第 37 号附件一",
  ].join("\n");

  var detected = mcq.detect(text);
  assertEqual(detected, null, "answer explanation should stay plain text");
});

run("stripReceipt removes visible receipt tail without touching answer body", function () {
  var text = [
    "屋面防水等级应结合建筑性质、使用功能和重要程度综合确定。",
    "",
    "回执：已生成 1 道题",
  ].join("\n");

  assertEqual(
    mcq.stripReceipt(text),
    "屋面防水等级应结合建筑性质、使用功能和重要程度综合确定。",
    "visible receipt tail should be removed",
  );
});

if (fail > 0) {
  console.error("mcq-detect tests failed: " + fail + " failed, " + pass + " passed");
  for (var i = 0; i < errors.length; i++) console.error(errors[i]);
  process.exit(1);
}

console.log("mcq-detect tests passed: " + pass);
