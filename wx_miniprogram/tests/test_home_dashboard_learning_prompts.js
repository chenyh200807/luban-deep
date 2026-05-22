// Run: node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var wxVmPath = path.join(__dirname, "../utils/learning-home-view-model.js");
var yousenVmPath = path.join(
  __dirname,
  "../../yousenwebview/packageDeeptutor/utils/learning-home-view-model.js",
);
var chatSourcePath = path.join(__dirname, "../pages/chat/chat.js");
var chatWxmlPath = path.join(__dirname, "../pages/chat/chat.wxml");
var wsSourcePath = path.join(__dirname, "../utils/ws-stream.js");

var wxVm = require(wxVmPath);
var yousenVm = require(yousenVmPath);
var dashboard = {
  review: { overdue: 1, due_today: 2 },
  today_focus: {
    label: "今日焦点",
    title: "主体结构专项",
    meta: "来自最近批改",
    prompt_intent: { source: "home_dashboard", learning_signal_type: "home_prompt_clicked" },
  },
  recommended_prompts: [
    {
      text: "讲一下主体结构验收",
      prompt_type: "concept_explain",
      intent: { source: "home_dashboard", learning_signal_type: "concept_explain" },
      evidence_refs: ["evt-home-1"],
      learning_state_ref: "knowledge:1A432000",
      suggested_mode: "deep",
    },
    {
      text: "我还是没懂防水节点",
      prompt_type: "still_confused",
      intent: { source: "home_dashboard", learning_signal_type: "still_confused" },
    },
  ],
};

assert.deepStrictEqual(
  wxVm.buildLearningHomeViewModel(dashboard),
  yousenVm.buildLearningHomeViewModel(dashboard),
);
var model = wxVm.buildLearningHomeViewModel(dashboard);
assert.strictEqual(model.reviewCount, 3);
assert.strictEqual(model.focusQuery, "讲一下主体结构验收");
assert.strictEqual(model.recommendedPrompts.length, 2);
assert.strictEqual(model.recommendedPrompts[0].promptIntent.learning_signal_type, "concept_explain");
assert.deepStrictEqual(model.recommendedPrompts[0].evidenceRefs, ["evt-home-1"]);
assert.strictEqual(model.recommendedPrompts[0].learningStateRef, "knowledge:1A432000");
assert.strictEqual(model.recommendedPrompts[0].suggestedMode, "deep");

var chatSource = fs.readFileSync(chatSourcePath, "utf8");
var chatWxml = fs.readFileSync(chatWxmlPath, "utf8");
var wsSource = fs.readFileSync(wsSourcePath, "utf8");
assert(chatSource.indexOf("learning-home-view-model") >= 0);
assert(chatSource.indexOf("onRecommendedPromptTap") >= 0);
assert(chatWxml.indexOf("recommendedPrompts") >= 0);
assert(chatSource.indexOf("showStaticExamples") >= 0);
assert(chatWxml.indexOf("showStaticExamples") >= 0);
assert(wsSource.indexOf("prompt_intent") >= 0);
assert(fs.readFileSync(wxVmPath, "utf8").indexOf("buildFallbackFocusQuery") < 0);

function loadChatPage(getHomeDashboard) {
  var capturedPage = null;
  var sandbox = {
    Page: function (definition) {
      capturedPage = definition;
    },
    __wxConfig: { platform: "devtools" },
    wx: {
      getMenuButtonBoundingClientRect: function () {
        return { left: 320 };
      },
      removeStorageSync: function () {},
      getStorageSync: function () {
        return null;
      },
      setStorageSync: function () {},
      showToast: function () {},
    },
    getApp: function () {
      return { globalData: { networkAvailable: true } };
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          unwrapResponse: function (value) {
            return value && value.data ? value.data : value;
          },
          getHomeDashboard: getHomeDashboard,
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getAnimConfig: function () {
            return {
              flushThrottleMs: 16,
              mdParseInterval: 4,
              enableBreathingOrbs: false,
              enableMarquee: false,
              enableMsgAnimation: false,
              enableFocusPulse: false,
            };
          },
          getTimeGreeting: function () {
            return "你好";
          },
          vibrate: function () {},
        };
      }
      if (request === "../../utils/logger") {
        return { warn: function () {}, info: function () {}, error: function () {} };
      }
      if (request === "../../utils/history-tombstone") {
        return {
          rememberDeletedConversationIds: function () {},
          readDeletedConversationIds: function () {
            return {};
          },
        };
      }
      if (request === "../../utils/learning-home-view-model") return wxVm;
      return {};
    },
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
  };
  vm.runInNewContext(chatSource, sandbox, { filename: chatSourcePath });
  assert(capturedPage);
  return capturedPage;
}

function instantiatePage(pageDefinition) {
  var sent = [];
  var page = Object.assign({}, pageDefinition, {
    data: JSON.parse(JSON.stringify(pageDefinition.data || {})),
    setData: function (update) {
      this.data = Object.assign({}, this.data, update || {});
    },
    _send: function (query, options) {
      sent.push({ query: query, options: options || {} });
    },
  });
  return { page: page, sent: sent };
}

function flushPromises() {
  return Promise.resolve().then(function () {
    return Promise.resolve();
  });
}

(async function () {
  var successDefinition = loadChatPage(function () {
    return Promise.resolve({ data: dashboard });
  });
  var success = instantiatePage(successDefinition);
  success.page._loadDashboard();
  await flushPromises();
  assert.strictEqual(success.page.data.showStaticExamples, false);
  success.page.onFocusTap();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(success.sent)), [
    {
      query: "讲一下主体结构验收",
      options: {
        promptIntent: {
          source: "home_dashboard",
          learning_signal_type: "home_prompt_clicked",
        },
      },
    },
  ]);

  var emptyDefinition = loadChatPage(function () {
    return Promise.resolve({ data: { today_focus: { title: "今日焦点" }, recommended_prompts: [] } });
  });
  var empty = instantiatePage(emptyDefinition);
  empty.page._loadDashboard();
  await flushPromises();
  assert.strictEqual(empty.page.data.showStaticExamples, true);
  empty.page.onFocusTap();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(empty.sent)), []);
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
