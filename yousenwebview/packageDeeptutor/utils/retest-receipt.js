// Canonical retest terminal receipt validator.
// The page wrapper may render only after the server returns one exact boolean
// result per submitted variant plus a matching aggregate score.

function _mismatch() {
  throw new Error("canonical completion receipt mismatch");
}

function validateCompletionReceipt(submittedItems, body) {
  var submitted = Array.isArray(submittedItems) ? submittedItems : [];
  var response = body && typeof body === "object" ? body : {};
  var results = Array.isArray(response.items) ? response.items : [];
  if (!submitted.length || results.length !== submitted.length) _mismatch();

  var expected = {};
  submitted.forEach(function (item) {
    var id = String((item && item.variant_id) || "").trim();
    if (!id || expected[id]) _mismatch();
    expected[id] = true;
  });

  var resultsById = {};
  var computedCorrect = 0;
  results.forEach(function (result) {
    var id = String((result && result.variant_id) || "").trim();
    if (!id || !expected[id] || resultsById[id] || typeof result.is_correct !== "boolean") {
      _mismatch();
    }
    resultsById[id] = result;
    if (result.is_correct) computedCorrect += 1;
  });

  var score = response.score && typeof response.score === "object" ? response.score : {};
  var correctCount = score.correct_count;
  var questionCount = score.question_count;
  if (
    !Number.isInteger(correctCount) ||
    !Number.isInteger(questionCount) ||
    correctCount < 0 ||
    questionCount <= 0 ||
    questionCount !== submitted.length ||
    correctCount !== computedCorrect
  ) _mismatch();

  return {
    resultsById: resultsById,
    correctCount: correctCount,
    questionCount: questionCount,
  };
}

module.exports = {
  validateCompletionReceipt: validateCompletionReceipt,
};
