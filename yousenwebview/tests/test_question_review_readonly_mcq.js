// Run: node yousenwebview/tests/test_question_review_readonly_mcq.js

var aiMessageState = require("../packageDeeptutor/utils/ai-message-state");

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) return;
  throw new Error(
    message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

var state = aiMessageState.deriveAiMessageRenderState({
  content: "### 第 1 题\n关于混凝土保护层厚度，下列哪个说法是正确的？",
  presentation: {
    blocks: [
      {
        type: "mcq",
        questions: [
          {
            index: 1,
            stem: "关于混凝土保护层厚度，下列哪个说法是正确的？",
            question_type: "single_choice",
            options: [
              { key: "A", text: "方案A" },
              { key: "B", text: "方案B" },
            ],
            followup_context: {
              question_id: "q_review_1",
              correct_answer: "B",
            },
            review_notes: {
              display_answer: "B",
              analysis: "B 更符合规范。",
            },
          },
        ],
        submit_hint: "题目讲评，已展示解析，不需要提交答案。",
        review_mode: true,
      },
    ],
    fallback_text: "### 第 1 题\n关于混凝土保护层厚度，下列哪个说法是正确的？",
    meta: { streamingMode: "block_finalized" },
  },
  parseBlocks: false,
});

assertEqual(!!state.mcqCards, true, "question review should render the question card");
assertEqual(state.mcqCards.length, 1, "question review should expose one card");
assertEqual(state.mcqInteractiveReady, false, "question review card must be read-only");
assertEqual(
  state.mcqHint,
  "题目讲评，已展示解析，不需要提交答案。",
  "question review hint should describe read-only mode",
);
assertEqual(state.mcqReviewMode, true, "question review renderer should know this is a review card");
assertEqual(
  state.mcqCards[0].reviewNotes,
  { displayAnswer: "B", analysis: "B 更符合规范。" },
  "question review should show the public answer and explanation outside the original-text toggle",
);

console.log("PASS test_question_review_readonly_mcq.js");
