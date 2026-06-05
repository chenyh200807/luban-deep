// test_chat_question_context_continuity.js — standalone/shadow chat should preserve question authority across submit and retry.
// Run: node wx_miniprogram/tests/test_chat_question_context_continuity.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function loadChatPage() {
  var source = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
  var pageDef = null;
  var telemetryCalls = [];
  var streamCalls = [];
  var streamCallbacks = [];
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    setTimeout: function (fn) {
      if (typeof fn === "function") fn();
      return 1;
    },
    clearTimeout: function () {},
    getApp: function () {
      return { globalData: { networkAvailable: true } };
    },
    require: function (request) {
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/api") {
        return {
          unwrapResponse: function (raw) {
            return raw;
          },
          createConversation: function () {
            return Promise.resolve({ conversation: { id: "tb_created" } });
          },
        };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") {
        return {
          streamChat: function (opts, callbacks) {
            streamCalls.push(opts || {});
            streamCallbacks.push(callbacks || {});
            return function () {};
          },
        };
      }
      if (request === "../../utils/surface-telemetry") {
        return {
          track: function (eventName, payload) {
            telemetryCalls.push({ eventName: eventName, payload: payload || {} });
          },
          trackOnce: function (key, eventName, payload) {
            telemetryCalls.push({ key: key, eventName: eventName, payload: payload || {} });
          },
        };
      }
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
            return "上午好";
          },
          vibrate: function () {},
        };
      }
      if (request === "../../utils/logger") return { error: function () {}, warn: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") {
        return { buildLearningHomeViewModel: function () { return { recommendedPrompts: [] }; } };
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
      showToast: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}, {
      enableWebSearch: false,
      answerMode: "AUTO",
      messages: [],
      hasMessages: false,
      isStreaming: false,
    }),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  page._isWebSearchAvailable = function () {
    return false;
  };
  page._shouldAutoEnableWebSearch = function () {
    return false;
  };
  page._getSelectedTools = function () {
    return [];
  };
  page._persistPendingTurn = function () {};
  page._setupObserver = function () {};
  page._stop = function () {};
  page._buildTutorInteraction = function () {
    return { profile: "smart", hints: [] };
  };
  page._applySelectedToolHints = function (interaction) {
    return interaction;
  };

  return {
    page: page,
    telemetryCalls: telemetryCalls,
    streamCalls: streamCalls,
    streamCallbacks: streamCallbacks,
  };
}

(async function main() {
  await run("visible card submit should create canonical followup context", async function () {
    var loaded = loadChatPage();
    var payload = loaded.page._buildMcqSubmitPayload([
      {
        index: 1,
        questionId: "visible_q1",
        stem: "压型金属板屋面最低坡度是多少？",
        questionType: "single_choice",
        options: [
          { key: "A", text: "5%", selected: true },
          { key: "B", text: "1%" },
        ],
      },
    ]);

    assert(payload && payload.text === "我选A", "single card submit should keep text minimal");
    assert(
      payload.followupQuestionContext &&
        payload.followupQuestionContext.question_id === "visible_q1" &&
        payload.followupQuestionContext.options.A === "5%" &&
        payload.followupQuestionContext.user_answer === "A",
      "visible card state should become followup question context",
    );
  });

  await run("retry should resend original question context", async function () {
    var loaded = loadChatPage();
    loaded.page._sid = "tb_conv_retry";
    loaded.page._convId = "tb_conv_retry";

    loaded.page._doSend("我选A", {
      followupQuestionContext: {
        question_id: "retry_q1",
        question: "压型金属板屋面最低坡度是多少？",
        question_type: "choice",
        user_answer: "A",
      },
      structuredSubmitContext: {
        questions: [{ question_id: "retry_q1" }],
        answers: [{ question_id: "retry_q1", selected_answer: "A" }],
      },
      promptIntent: { type: "mcq_submit" },
    });
    var aiMessage = loaded.page.data.messages[1];
    loaded.page.data.isStreaming = false;

    loaded.page.onRetry({ currentTarget: { dataset: { msgid: aiMessage.id } } });

    assert(loaded.streamCalls.length === 2, "retry should open another stream turn");
    assert(
      loaded.streamCalls[1].followupQuestionContext &&
        loaded.streamCalls[1].followupQuestionContext.question_id === "retry_q1",
      "retry should preserve original followup question context",
    );
    assert(
      loaded.streamCalls[1].structuredSubmitContext &&
        loaded.streamCalls[1].structuredSubmitContext.answers[0].selected_answer === "A",
      "retry should preserve structured submit context",
    );
    assert(
      loaded.streamCalls[1].promptIntent && loaded.streamCalls[1].promptIntent.type === "mcq_submit",
      "retry should preserve prompt intent",
    );
    assert(
      loaded.streamCalls[1].persistUserMessage === false,
      "retry should not duplicate the persisted user message",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_chat_question_context_continuity.js (" + pass + " assertions)");
})();
