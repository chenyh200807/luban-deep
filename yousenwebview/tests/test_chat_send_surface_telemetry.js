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
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var telemetryCalls = [];
  var streamCalls = [];
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    setTimeout: function (fn) {
      if (typeof fn === "function") fn();
      return 1;
    },
    clearTimeout: function () {},
    require: function (request) {
      if (request === "../../utils/auth") {
        return {
          getToken: function () {
            return "token";
          },
        };
      }
      if (request === "../../utils/api") {
        return {
          unwrapResponse: function (raw) {
            return raw;
          },
        };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") {
        return {
          streamChat: function (opts) {
            streamCalls.push(opts || {});
            return function () {};
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
          shouldAutoEnableWebSearch: function () {
            return false;
          },
        };
      }
      if (request === "../../utils/logger") {
        return {
          error: function () {},
          warn: function () {},
        };
      }
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") {
        return {
          track: function (eventName, payload) {
            telemetryCalls.push({
              type: "track",
              eventName: eventName,
              payload: payload || {},
            });
          },
          trackOnce: function (key, eventName, payload) {
            telemetryCalls.push({
              type: "trackOnce",
              key: key,
              eventName: eventName,
              payload: payload || {},
            });
          },
        };
      }
      if (request === "../../utils/runtime") {
        return {
          isNetworkAvailable: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          billing: function () {
            return "/packageDeeptutor/pages/billing/billing";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () {
            return false;
          },
          isFeatureEnabled: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/analytics") {
        return {
          track: function () {},
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function () {},
      navigateTo: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}, {
      enableWebSearch: false,
      answerMode: "AUTO",
      entrySource: "devtools",
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

  page._shouldAutoEnableWebSearch = function () {
    return false;
  };
  page._getSelectedTools = function () {
    return [];
  };
  page._scheduleSessionPersist = function () {};
  page._syncMessageIndexMap = function () {};
  page._syncWorkspaceChrome = function () {};
  page._setupObserver = function () {};
  page._buildTutorInteraction = function () {
    return {
      profile: "smart",
      hints: [],
    };
  };

  return {
    page: page,
    telemetryCalls: telemetryCalls,
    streamCalls: streamCalls,
  };
}

(async function main() {
  await run("_doSend should emit surface telemetry and continue to ws stream without ReferenceError", async function () {
    var loaded = loadChatPage();
    loaded.page._sid = "tb_conv_001";
    loaded.page._convId = "tb_conv_001";

    loaded.page._doSend("防水等级和设防层数有什么区别？");

    assert(
      loaded.telemetryCalls.length >= 1 &&
        loaded.telemetryCalls[0].eventName === "start_turn_sent",
      "_doSend should emit start_turn_sent telemetry before opening the stream",
    );
    assert(
      loaded.streamCalls.length === 1 &&
        loaded.streamCalls[0].sessionId === "tb_conv_001",
      "_doSend should continue into ws stream after telemetry",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_chat_send_surface_telemetry.js (" + pass + " assertions)");
})();
