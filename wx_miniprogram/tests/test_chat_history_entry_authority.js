// test_chat_history_entry_authority.js — history entry should open chat directly
// Run: node wx_miniprogram/tests/test_chat_history_entry_authority.js

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

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadChatPage() {
  var source = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
  var pageDef = null;
  var storage = {};
  var apiState = {
    getConversationMessagesCalls: [],
  };
  var app = {
    globalData: {
      pendingConversationId: "conv_history_direct",
      goHomeFlag: false,
    },
    checkAuth: function (cb) {
      if (typeof cb === "function") cb();
    },
  };

  var sandbox = {
    console: console,
    Date: Date,
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    getApp: function () {
      return app;
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          unwrapResponse: function (raw) {
            return raw;
          },
          getUserInfo: function () {
            return Promise.resolve({ username: "chenyh2008", points: 18 });
          },
          getAssessmentProfile: function () {
            return Promise.resolve({ level: "beginner" });
          },
          getConversationMessages: function (id) {
            apiState.getConversationMessagesCalls.push(id);
            return Promise.resolve({
              messages: [{ id: "u1", role: "user", content: "历史问题" }],
            });
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
        };
      }
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/auth") return {};
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/surface-telemetry") return { track: function () {}, trackOnce: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
      showToast: function () {},
      navigateTo: function () {},
      showModal: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });
  page._loadDashboard = function () {};
  page._checkDiagnostic = function () {};
  page._refreshPoints = function () {};
  page._setupObserver = function () {};
  page._releaseBottomAnchor = function () {};

  return {
    app: app,
    page: page,
    apiState: apiState,
  };
}

(async function main() {
  var loaded = loadChatPage();

  loaded.page.onLoad();
  assert(
    loaded.page.data.hasMessages === true,
    "pending history entry should suppress the hero before chat hydration",
  );

  loaded.page.onShow();
  await flushPromises();
  await flushPromises();

  assert(
    loaded.apiState.getConversationMessagesCalls.length === 1 &&
      loaded.apiState.getConversationMessagesCalls[0] === "conv_history_direct",
    "history entry should hydrate the selected conversation directly",
  );
  assert(
    loaded.app.globalData.pendingConversationId === null,
    "pending conversation id should still be consumed by the chat page",
  );
  assert(
    loaded.page.data.hasMessages === true && loaded.page.data.messages.length === 1,
    "history entry should stay on the chat surface after hydration",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_chat_history_entry_authority.js (" + pass + " assertions)");
})();
