// Run: node yousenwebview/tests/test_retest_mcq_reselect.js
//
// 单选题(single_choice)可改选收权合同 —— 2026-07-21 交互修复。
// root-cause 五点:①one business fact=MCQ 在用户离开该题前必须可自由改选;
// ②one authority=MCQ 的 answered(定稿)由 nextQuestion(离开动作)唯一写入;
// ③onOptionTap 降级为纯草稿选择(只写 selectedOptionId,不设 answered/不计数/不提交);
// ⑤纯前端交互态,不动后端判分真值(服务端仍统一重判)。
// 判断题(onChoiceTap)ship 了 expected_ok、点即揭示对错 → 点即定稿是对的,维持现状。
//
// 测试形态沿用 test_retest_fig_board.js 先例:vm.runInNewContext 全模块执行 + 桩 Page 捕获
// config,再用假 this(data + 支持 bracket-path 的 setData)驱动 Page 方法做行为断言。
// 禁 new Function(仓库安全 hook)。
var fs = require("fs");
var path = require("path");
var assert = require("assert");
var vmod = require("vm");

var retest = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.js"),
  "utf-8",
);
var retestWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/luban/retest/retest.wxml"),
  "utf-8",
);

// ─────────────────────────────────────────────────────────────
// (A) 静态收权断言:两个写入点收成一个 authority=nextQuestion/_finalizeCurrent。
// ─────────────────────────────────────────────────────────────

// onOptionTap 只能是纯草稿选择:不设 answered、不计数、不提交、不埋点。
var opStart = retest.indexOf("onOptionTap(event) {");
assert.ok(opStart >= 0, "onOptionTap must exist");
var opEnd = retest.indexOf("\n  },", opStart);
assert.ok(opEnd > opStart, "onOptionTap body must be delimitable");
var opBody = retest.slice(opStart, opEnd);
assert.strictEqual(opBody.indexOf("answered: true"), -1, "onOptionTap must not finalize (answered:true)");
assert.strictEqual(opBody.indexOf('.answered"] = true'), -1, "onOptionTap must not write answered=true via patch");
assert.strictEqual(opBody.indexOf("_submitCompletion"), -1, "onOptionTap must not submit completion");
assert.strictEqual(opBody.indexOf("answeredCount"), -1, "onOptionTap must not count answers");
assert.strictEqual(opBody.indexOf("trackProductBehavior"), -1, "onOptionTap must not emit per-tap telemetry (would pollute on reselect)");
assert.ok(opBody.indexOf("selectedOptionId") >= 0, "onOptionTap must record the selected option id (mutable draft)");

// _finalizeCurrent 是 MCQ 定稿唯一权威:answered=true + answeredCount 累加 + 持久化草稿。
var fcStart = retest.indexOf("_finalizeCurrent() {");
assert.ok(fcStart >= 0, "_finalizeCurrent (single finalize authority) must exist");
var fcEnd = retest.indexOf("\n  },", fcStart);
var fcBody = retest.slice(fcStart, fcEnd);
assert.ok(fcBody.indexOf('.answered"] = true') >= 0, "_finalizeCurrent must set answered=true");
assert.ok(fcBody.indexOf("answeredCount") >= 0, "_finalizeCurrent must accumulate answeredCount");
assert.ok(fcBody.indexOf("_persistDraft") >= 0, "_finalizeCurrent must persist the draft on leave");
// 幂等:已定稿或非单选题 no-op(防重复计数)
assert.ok(fcBody.indexOf('item.answered || item.answer_type !== "single_choice"') >= 0, "_finalizeCurrent must be idempotent for already-answered / non-MCQ items");

// nextQuestion(离开动作)必须先定稿当前题。
var nqStart = retest.indexOf("nextQuestion() {");
var nqEnd = retest.indexOf("\n  },", nqStart);
var nqBody = retest.slice(nqStart, nqEnd);
assert.ok(nqBody.indexOf("_finalizeCurrent()") >= 0, "nextQuestion must finalize the current question before leaving");
assert.ok(nqBody.indexOf("_submitCompletion") >= 0, "nextQuestion must submit on the last question (unified server rescore)");

// 判断题 onChoiceTap 维持现状:点即定稿(answered=true 在 tap 时写)。
var ocStart = retest.indexOf("onChoiceTap(event) {");
var ocEnd = retest.indexOf("\n  },", ocStart);
var ocBody = retest.slice(ocStart, ocEnd);
assert.ok(ocBody.indexOf('.answered"] = true') >= 0, "onChoiceTap (boolean) must still finalize on tap — expected_ok is shipped, revealing then editing = cheating");

// wxml:"下一题/查看结果"出现条件从 answered 改为 selectedOptionId(选了就能进)。
assert.ok(
  retestWxml.indexOf("answer_type === 'single_choice' && items[currentIndex].selectedOptionId}}") >= 0,
  "MCQ advance button must appear once an option is selected (not on answered)",
);
assert.strictEqual(
  retestWxml.indexOf("answer_type === 'single_choice' && items[currentIndex].answered}}"),
  -1,
  "MCQ pending block must no longer gate on answered",
);
// 改选高亮复用既有 selected class(selectedOptionId 驱动),无需新 class。
assert.ok(
  retestWxml.indexOf("items[currentIndex].selectedOptionId === option.option_id ? 'selected'") >= 0,
  "reselect highlight must reuse the existing selected class driven by selectedOptionId",
);

// ─────────────────────────────────────────────────────────────
// (B) 行为断言:vm 全模块执行 + 桩 Page 捕获 config,驱动 Page 方法。
// ─────────────────────────────────────────────────────────────
var captured = null;
function stub() {
  return {
    // 各 util 用到的方法都给安全 no-op / 假值,避免 undefined 调用崩溃
    trackProductBehavior: function () {},
    isDarkOr: function () { return false; },
    completeLubanRetest: function () { return { then: function () { return { catch: function () {} }; } }; },
    unwrapResponse: function (x) { return x; },
    describeRequestError: function () { return ""; },
    errorCodeOf: function () { return ""; },
    // writeOwnerStorage 故意不提供 → _persistDraft 的 selectionId/writeOwnerStorage 双守卫使其 no-op
    readOwnerStorage: function () { return null; },
    removeOwnerStorage: function () {},
  };
}
var sandbox = {
  module: { exports: {} },
  require: stub,
  Page: function (cfg) { captured = cfg; },
  console: console,
  wx: { getSystemInfoSync: function () { return {}; } },
};
sandbox.exports = sandbox.module.exports;
vmod.runInNewContext(retest, sandbox, { filename: "retest.js" });
assert.ok(captured && typeof captured.onOptionTap === "function", "Page config with methods must be captured");

// bracket-path setData(支持 "items[0].selectedOptionId" 与普通键)
function applyPath(obj, keyPath, value) {
  var tokens = [];
  keyPath.replace(/[^.\[\]]+|\[(\d+)\]/g, function (m, idx) {
    tokens.push(idx !== undefined ? Number(idx) : m);
    return "";
  });
  var cur = obj;
  for (var i = 0; i < tokens.length - 1; i += 1) cur = cur[tokens[i]];
  cur[tokens[tokens.length - 1]] = value;
}
function makePage(data) {
  var ctx = Object.create(captured); // 方法走原型
  ctx.data = data;
  ctx.setData = function (patch) {
    Object.keys(patch).forEach(function (k) { applyPath(ctx.data, k, patch[k]); });
  };
  return ctx;
}
function tapEvent(index, extra) {
  return { currentTarget: { dataset: Object.assign({ index: index }, extra) } };
}

// ── B1: MCQ 可反复改选(tap A 再 tap B,selectedOptionId 变 B 且 answered 仍 false,不计数) ──
(function () {
  var page = makePage({
    items: [
      {
        answer_type: "single_choice",
        options: [{ option_id: "opt_a" }, { option_id: "opt_b" }],
        answered: false,
        selectedOptionId: "",
      },
      { answer_type: "single_choice", options: [{ option_id: "opt_x" }], answered: false, selectedOptionId: "" },
    ],
    total: 2,
    currentIndex: 0,
    answeredCount: 0,
    selectionId: "",
    syncStatus: "idle",
  });

  page.onOptionTap(tapEvent(0, { optionId: "opt_a" }));
  assert.strictEqual(page.data.items[0].selectedOptionId, "opt_a", "first tap records option A");
  assert.strictEqual(page.data.items[0].answered, false, "selecting must NOT finalize (answered stays false)");
  assert.strictEqual(page.data.answeredCount, 0, "selecting must NOT count");

  page.onOptionTap(tapEvent(0, { optionId: "opt_b" }));
  assert.strictEqual(page.data.items[0].selectedOptionId, "opt_b", "reselect overwrites to option B before leaving");
  assert.strictEqual(page.data.items[0].answered, false, "reselect still does not finalize");
  assert.strictEqual(page.data.answeredCount, 0, "reselect still does not count");

  // ── B2: 离开该题(nextQuestion)才 answered=true + 计数一次 ──
  page.nextQuestion();
  assert.strictEqual(page.data.items[0].answered, true, "leaving the question finalizes it (answered=true)");
  assert.strictEqual(page.data.answeredCount, 1, "leaving counts exactly once");
  assert.strictEqual(page.data.currentIndex, 1, "leaving advances to the next question");
  assert.strictEqual(page.data.items[0].selectedOptionId, "opt_b", "finalized answer is the last selected option (B)");

  // ── B2b: 防重复计数(已定稿题再 finalize 不重复 ++)——回到 index 0 再 nextQuestion 不应重复计数 ──
  page.data.currentIndex = 0;
  page.nextQuestion();
  assert.strictEqual(page.data.answeredCount, 1, "re-finalizing an already-answered item must not double count (idempotent)");

  // 已定稿题不可再改选(离开即锁)
  page.onOptionTap(tapEvent(0, { optionId: "opt_a" }));
  assert.strictEqual(page.data.items[0].selectedOptionId, "opt_b", "an already-finalized MCQ item is locked (no reselect after leaving)");
})();

// ── B3: 判断题行为不变(onChoiceTap 点即定稿) ──
(function () {
  var page = makePage({
    items: [
      { answer_type: "boolean", expected_ok: true, answered: false, correct: null, chosenOk: null },
      { answer_type: "boolean", expected_ok: false, answered: false, correct: null, chosenOk: null },
    ],
    total: 2,
    currentIndex: 0,
    answeredCount: 0,
    correctCount: 0,
    selectionId: "",
    syncStatus: "idle",
  });
  page.onChoiceTap(tapEvent(0, { choice: "ok" }));
  assert.strictEqual(page.data.items[0].answered, true, "boolean question still finalizes on tap (unchanged)");
  assert.strictEqual(page.data.items[0].correct, true, "boolean correctness revealed on tap (unchanged)");
  assert.strictEqual(page.data.answeredCount, 1, "boolean tap counts immediately (unchanged)");
})();

console.log("PASS test_retest_mcq_reselect.js");
