// test_chat_terminal_recovery.js — empty terminal done must not erase recovery identity.
// Run: node wx_miniprogram/tests/test_chat_terminal_recovery.js

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
  return Promise.resolve().then(function () {
    return Promise.resolve();
  });
}

function loadChatPage(options) {
  var opts = options || {};
  var source = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
  var pageDef = null;
  var storage = {};
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    setInterval: function () {
      return 1;
    },
    clearInterval: function () {},
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
          getConversationMessages: opts.getConversationMessages || function () {
            return Promise.resolve({ messages: [] });
          },
        };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/surface-telemetry") {
        return { track: function () {}, trackOnce: function () {} };
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
          isDark: function () {
            return false;
          },
          syncTabBar: function () {},
        };
      }
      if (request === "../../utils/logger") return { error: function () {}, warn: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") {
        return require(path.join(__dirname, "../utils/chat-turn-recovery.js"));
      }
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") {
        return { buildLearningHomeViewModel: function () { return { recommendedPrompts: [] }; } };
      }
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
      messages: [],
      hasMessages: false,
      isStreaming: false,
      canStopStream: false,
    }),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  page._setupObserver = function () {};
  page._teardownObserver = function () {};
  page._testStorage = storage;
  return page;
}

(async function main() {
  var page = loadChatPage();
  page._pendingTurn = {
    conversationId: "tb_conv_done_empty",
    baselineCount: 0,
    query: "案例题批改",
    clientTurnId: "client_done_empty",
    turnId: "turn_done_empty",
    createdAt: Date.now(),
  };
  page._streamId = "a-empty";
  page._find = function (id) {
    return id === "a-empty" ? 0 : -1;
  };
  page._buildAiMessageUpdates = function () {
    return {
      state: { renderableContent: "", blocks: [], mcqCards: [] },
      updates: {},
    };
  };
  page.setData({
    messages: [{ id: "a-empty", role: "ai", content: "", streaming: true }],
    isStreaming: true,
    canStopStream: true,
  });
  var emptyDoneBackgroundContinues = 0;
  page._continuePendingTurnRecoveryInBackground = function () {
    emptyDoneBackgroundContinues += 1;
  };

  page._onDone();
  for (var i = 0; i < 8; i++) {
    await flushPromises();
  }

  assert(
    page._pendingTurn && page._pendingTurn.clientTurnId === "client_done_empty",
    "empty done recovery exhaustion should preserve pending identity",
  );
  assert(page.data.isStreaming === false, "empty done recovery exhaustion should unlock streaming state");
  assert(page.data.canStopStream === false, "empty done recovery exhaustion should clear stop affordance");
  assert(
    emptyDoneBackgroundContinues === 1,
    "empty done short recovery exhaustion should continue canonical history recovery in the background",
  );

  var foregroundPage = loadChatPage({
    getConversationMessages: function () {
      return Promise.resolve({
        messages: [
          {
            role: "user",
            content: "案例题批改",
            client_turn_id: "client_foreground_pending",
          },
        ],
      });
    },
  });
  foregroundPage._persistPendingTurn({
    conversationId: "tb_conv_foreground_pending",
    baselineCount: 0,
    query: "案例题批改",
    clientTurnId: "client_foreground_pending",
    turnId: "turn_foreground_pending",
    createdAt: Date.now(),
  });
  foregroundPage.setData({
    messages: [
      { id: "u0", role: "user", content: "案例题批改", streaming: false },
      { id: "a0", role: "ai", content: "本地仍在等待服务端结果", streaming: true },
    ],
    hasMessages: true,
    isStreaming: false,
    canStopStream: false,
  });

  foregroundPage._pendingRecoveryActive = true;
  await foregroundPage._recoverTurnFromHistory({
    maxAttempts: 1,
    unlockOnExhausted: true,
    keepPendingOnExhausted: true,
    hydrateOnExhausted: false,
  });
  for (var j = 0; j < 8; j++) {
    await flushPromises();
  }

  assert(
    foregroundPage.data.messages.length === 2 &&
      foregroundPage.data.messages[1].content === "本地仍在等待服务端结果",
    "foreground recovery exhaustion should not hydrate incomplete canonical history over local pending UI",
  );
  assert(
    foregroundPage._pendingTurn &&
      foregroundPage._pendingTurn.clientTurnId === "client_foreground_pending",
    "foreground recovery exhaustion should keep pending identity for later canonical history recovery",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_chat_terminal_recovery.js (" + pass + " assertions)");
})();
