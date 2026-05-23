// Run: node yousenwebview/tests/test_mistake_book_view_model.js

var assert = require("assert");
var vm = require("../packageDeeptutor/utils/mistake-book-view-model");

var model = vm.buildMistakeBookViewModel({
  ok: true,
  items: [
    {
      event_id: "e1",
      attempt_ref: "ref1",
      title: "主体结构验收题",
      concept_label: "主体结构",
      error_label: "关键词误读",
      saved_at: "2026-05-20T08:00:00+08:00",
      review_due_at: "2020-01-01T08:00:00+08:00",
      note: "把验收主体看错了",
    },
    {
      event_id: "e2",
      attempt_ref: "ref2",
      title: "主体结构构造题",
      concept_label: "主体结构",
      error_label: "关键词误读",
      saved_at: "2026-05-21T08:00:00+08:00",
    },
    {
      event_id: "e3",
      attempt_ref: "ref3",
      title: "防水题",
      concept_label: "防水工程",
      error_label: "规范数字混淆",
      mastered_at: "2026-05-22T08:00:00+08:00",
    },
  ],
});

assert.strictEqual(model.count, 3);
assert.strictEqual(model.activeCount, 2);
assert.strictEqual(model.dueCount, 1);
assert.strictEqual(model.masteredCount, 1);
assert.strictEqual(model.conceptBars[0].label, "主体结构");
assert.strictEqual(model.conceptBars[0].count, 2);
assert.strictEqual(model.errorBars[0].label, "关键词误读");
assert(model.aiInsight.title.indexOf("主体结构") >= 0);
assert(model.aiInsight.summary.indexOf("关键词误读") >= 0);
assert.strictEqual(model.items[0].state, "due");
assert.strictEqual(model.items[2].state, "mastered");

var empty = vm.buildMistakeBookViewModel({ items: [] });
assert.strictEqual(empty.empty, true);
assert(empty.aiInsight.summary.indexOf("收藏错题") >= 0);

console.log("PASS test_mistake_book_view_model.js");
