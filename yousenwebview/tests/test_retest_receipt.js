// Run: node yousenwebview/tests/test_retest_receipt.js
var assert = require("assert");
var receipt = require("../packageDeeptutor/utils/retest-receipt");

var submitted = ["q1", "q2"].map(function (id) { return { variant_id: id }; });
function body(items, correct, total) {
  return {
    items: items,
    score: { correct_count: correct, question_count: total },
  };
}
function rejects(value, label) {
  assert.throws(
    function () { receipt.validateCompletionReceipt(submitted, value); },
    /canonical completion receipt mismatch/,
    label,
  );
}

var valid = receipt.validateCompletionReceipt(
  submitted,
  body([
    { variant_id: "q2", is_correct: false },
    { variant_id: "q1", is_correct: true },
  ], 1, 2),
);
assert.strictEqual(valid.resultsById.q1.is_correct, true);
assert.strictEqual(valid.resultsById.q2.is_correct, false);
assert.strictEqual(valid.correctCount, 1);
assert.strictEqual(valid.questionCount, 2);

rejects(body([{ variant_id: "q1", is_correct: true }], 1, 2), "missing result");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q1", is_correct: false },
], 1, 2), "duplicate result");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q3", is_correct: false },
], 1, 2), "unknown result");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: 0 },
], 1, 2), "non-boolean score");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: false },
], 0, 2), "aggregate score mismatch");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: false },
], 1, 1), "question count mismatch");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: false },
], "1", "2"), "numeric strings are schema drift");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: false },
], 1.0, 2.5), "fractional aggregate is invalid");
rejects(body([
  { variant_id: "q1", is_correct: true },
  { variant_id: "q2", is_correct: false },
], -1, 2), "negative aggregate is invalid");

console.log("PASS test_retest_receipt.js");
