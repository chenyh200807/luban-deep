// test_package_chat_feedback_interaction.js — package feedback popover should be selectable and submit reliably
// Run: node yousenwebview/tests/test_package_chat_feedback_interaction.js

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

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
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

function applyPath(target, pathExpr, value) {
  var match = /^messages\[(\d+)\]\.([A-Za-z0-9_]+)$/.exec(pathExpr);
  if (!match) {
    target[pathExpr] = value;
    return;
  }
  var idx = Number(match[1]);
  var key = match[2];
  var messages = (target.messages || []).slice();
  messages[idx] = Object.assign({}, messages[idx] || {}, { [key]: value });
  target.messages = messages;
}

function loadChatPage(submitFeedback) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var toasts = [];
  var helpersMock = {
    getAnimConfig: function () {
      return {};
    },
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
        windowWidth: 375,
        screenWidth: 375,
        windowHeight: 812,
        screenHeight: 812,
        safeArea: { bottom: 778 },
      };
    },
    isDark: function () {
      return true;
    },
    getTimeGreeting: function () {
      return "上午好";
    },
    syncTabBar: function () {},
    vibrate: function () {},
  };
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/api") {
        return {
          submitFeedback: submitFeedback,
          unwrapResponse: function (raw) {
            return raw;
          },
        };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/history-tombstone") {
        return { rememberDeletedConversationIds: function () {} };
      }
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") return { track: function () {}, trackOnce: function () {} };
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      removeStorageSync: function () {},
      showToast: function (payload) {
        toasts.push(payload);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "yousenwebview/packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      var copy = Object.assign({}, this.data);
      Object.keys(next || {}).forEach(function (key) {
        applyPath(copy, key, next[key]);
      });
      this.data = copy;
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });
  return { page: page, toasts: toasts };
}

function flush() {
  return Promise.resolve().then(function () {
    return Promise.resolve();
  });
}

async function run() {
  var wxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
    "utf8",
  );
  assert(
    /<wxs\s+module=["']feedbackTag["']>/.test(wxml),
    "package feedback selected state should use a WXS reader that mini-program templates can execute",
  );
  assert(
    wxml.indexOf("feedbackTags.indexOf(") === -1,
    "package feedback selected state should not rely on indexOf calls inside WXML expressions",
  );
  ["事实错误", "产生幻觉", "逻辑不通", "格式混乱"].forEach(function (tag) {
    assert(
      wxml.indexOf("feedbackTag.has(feedbackTags, '" + tag + "')") >= 0,
      "package feedback tag should render selected class from canonical feedbackTags: " + tag,
    );
  });

  var calls = [];
  var loaded = loadChatPage(function (payload) {
    calls.push(payload);
    return Promise.resolve({ ok: true });
  });
  loaded.page._convId = "tb_feedback";
  loaded.page.setData({
    messages: [{ id: "m1", role: "ai", feedback: "", engineTurnId: "turn_feedback_1" }],
    feedbackTags: [],
    feedbackComment: "",
    answerMode: "AUTO",
  });
  loaded.page.onThumbDown({ currentTarget: { dataset: { msgid: "m1" } } });
  assert(loaded.page.data.feedbackMsgId === "m1", "thumb down should open feedback popover");
  assert(loaded.page.data.scrollToId === "msg-bottom", "thumb down should anchor feedback popover above composer");

  loaded.page.onFeedbackTag({ currentTarget: { dataset: { tag: "事实错误" } } });
  loaded.page.onFeedbackTag({ currentTarget: { dataset: { tag: "格式混乱" } } });
  assertEqual(loaded.page.data.feedbackTags, ["事实错误", "格式混乱"], "feedback tags should toggle on");
  loaded.page.onFeedbackTag({ currentTarget: { dataset: { tag: "格式混乱" } } });
  assertEqual(loaded.page.data.feedbackTags, ["事实错误"], "feedback tag should toggle off");
  loaded.page.onFeedbackTag({ currentTarget: { dataset: { tag: "格式混乱" } } });

  loaded.page.onFeedbackInput({ detail: { value: "答案引用范围不对" } });
  loaded.page.onFeedbackSubmit();
  assert(loaded.page.data.feedbackSubmitting === true, "submit should enter submitting state");
  await flush();

  assertEqual(calls.length, 1, "submit should call feedback API once");
  assertEqual(calls[0].turn_id, "turn_feedback_1", "submit should persist canonical engine turn id when available");
  assertEqual(calls[0].reason_tags, ["事实错误", "格式混乱"], "submit should persist selected tags");
  assertEqual(calls[0].comment, "答案引用范围不对", "submit should persist optional comment");
  assert(loaded.page.data.feedbackMsgId === "", "successful submit should close popover");
  assert(loaded.toasts[0].title === "感谢反馈", "successful submit should show success toast");

  var failed = loadChatPage(function () {
    return Promise.reject(new Error("network"));
  });
  failed.page.setData({
    messages: [{ id: "m2", role: "ai", feedback: "down" }],
    feedbackMsgId: "m2",
    feedbackTags: ["逻辑不通"],
  });
  failed.page.onFeedbackSubmit();
  await flush();

  assert(failed.page.data.feedbackMsgId === "m2", "failed submit should keep popover open");
  assert(failed.page.data.feedbackSubmitting === false, "failed submit should leave submitting state");
  assert(failed.toasts[0].title === "提交失败，请稍后重试", "failed submit should not pretend success");
}

run().then(function () {
  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_package_chat_feedback_interaction.js (" + pass + " assertions)");
});
