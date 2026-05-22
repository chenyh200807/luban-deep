// Ensures the interactive MCQ renderer submits an explicit grading intent.
// Run: node wx_miniprogram/tests/test_chat_mcq_submit_prompt.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var source = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
var pageDef = null;

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

var sandbox = {
  console: console,
  Date: Date,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  getApp: function () {
    return { globalData: {} };
  },
  require: function (request) {
    if (request === "../../utils/auth") return {};
    if (request === "../../utils/api") {
      return {
        unwrapResponse: function (raw) {
          return raw;
        },
      };
    }
    if (request === "../../utils/ai-message-state") {
      return { coerceUserVisibleContent: function (text) { return String(text || ""); } };
    }
    if (request === "../../utils/learning-home-view-model") {
      return { buildLearningHomeViewModel: function () { return { recommendedPrompts: [] }; } };
    }
    if (request === "../../utils/ws-stream") return {};
    if (request === "../../utils/surface-telemetry") return {};
    if (request === "../../utils/helpers") {
      return {
        getAnimConfig: function () {
          return {
            flushThrottleMs: 16,
            mdParseInterval: 3,
            enableBreathingOrbs: false,
            enableMarquee: false,
            enableMsgAnimation: false,
            enableFocusPulse: false,
          };
        },
        getTimeGreeting: function () {
          return "晚上好";
        },
        vibrate: function () {},
      };
    }
    if (request === "../../utils/logger") return { warn: function () {} };
    if (request === "../../utils/workflow-status") return {};
    if (request === "../../utils/citation-format") return {};
    if (request === "../../utils/chat-turn-recovery") return {};
    if (request === "../../utils/history-tombstone") {
      return { rememberDeletedConversationIds: function () {} };
    }
    if (request === "../../utils/devtools-markdown-fixtures") return {};
    throw new Error("unexpected require: " + request);
  },
  wx: {
    getStorageSync: function () {},
    setStorageSync: function () {},
    removeStorageSync: function () {},
    getSystemInfoSync: function () {
      return { windowWidth: 375, screenWidth: 375 };
    },
  },
  Page: function (def) {
    pageDef = def;
  },
};

vm.runInNewContext(source, sandbox, {
  filename: "wx_miniprogram/pages/chat/chat.js",
});

assert(pageDef && typeof pageDef._buildMcqSubmitPayload === "function", "chat page should expose MCQ submit payload builder");

var payload = pageDef._buildMcqSubmitPayload([
  {
    index: 1,
    stem: "题1",
    questionType: "single_choice",
    questionId: "q_1",
    followupContext: {
      question_id: "q_1",
      question: "题1",
      question_type: "single_choice",
      options: { A: "A1", B: "B1" },
    },
    options: [
      { key: "A", text: "A1", selected: false },
      { key: "B", text: "B1", selected: true },
    ],
  },
  {
    index: 2,
    stem: "题2",
    questionType: "single_choice",
    questionId: "q_2",
    followupContext: {
      question_id: "q_2",
      question: "题2",
      question_type: "single_choice",
      options: { A: "A2", B: "B2" },
    },
    options: [
      { key: "A", text: "A2", selected: false },
      { key: "B", text: "B2", selected: true },
    ],
  },
]);

assert(payload, "selected cards should build a submit payload");
assert(
  payload.text === "提交作答，请批改：第1题：B；第2题：B",
  "batch submit text should explicitly ask for grading instead of looking like a new practice request",
);
assert(
  payload.followupQuestionContext && payload.followupQuestionContext.items.length === 2,
  "batch submit should carry canonical question context for backend routing",
);

var single = pageDef._buildMcqSubmitPayload([
  {
    index: 1,
    stem: "题1",
    questionType: "single_choice",
    questionId: "q_1",
    followupContext: {
      question_id: "q_1",
      question: "题1",
      question_type: "single_choice",
      options: { A: "A1", B: "B1" },
    },
    options: [
      { key: "A", text: "A1", selected: false },
      { key: "B", text: "B1", selected: true },
    ],
  },
]);

assert(
  single.text === "提交作答，请批改：我选B",
  "single submit text should also carry explicit grading intent",
);

console.log("PASS test_chat_mcq_submit_prompt.js");
