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

function run(name, fn) {
  try {
    fn();
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
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return { getToken: function () { return "token"; } };
      if (request === "../../utils/api") return { unwrapResponse: function (raw) { return raw; } };
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
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
          isDark: function () { return true; },
          getTimeGreeting: function () { return "晚上好"; },
        };
      }
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      return {};
    },
    wx: {
      getStorageSync: function () { return ""; },
      removeStorageSync: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  return pageDef;
}

function loadWsStream() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/ws-stream.js"),
    "utf8",
  );
  var module = { exports: {} };
  var sandbox = {
    module: module,
    exports: module.exports,
    require: function (request) {
      if (request === "./auth") return { getToken: function () { return "token"; } };
      if (request === "./api") return {};
      if (request === "./endpoints") return {};
      if (request === "./host-runtime") return {};
      throw new Error("unexpected require: " + request);
    },
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/ws-stream.js",
  });
  return module.exports;
}

run("chat page should show workflow status by default", function () {
  var pageDef = loadChatPage();
  assert(pageDef && pageDef.data && pageDef.data.showInternalStatus === true, "showInternalStatus should default to true");
});

run("internal thinking status should be sanitized before entering workflow trace", function () {
  var wsStream = loadWsStream();
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));

  var payload = wsStream.buildStatusEvent({
    type: "thinking",
    content: "private chain of thought that should stay hidden",
    source: "chat",
    stage: "responding",
    metadata: { visibility: "internal" },
  });
  var entry = workflowStatus.buildWorkflowEntry(payload);

  assert(payload.content === "", "internal thinking payload content should be stripped");
  assert(payload.data === "responding", "internal thinking payload should fall back to stage name");
  assert(entry.title === "正在整理最终回答", "workflow entry should use safe stage summary");
  assert(entry.rawText === "正在整理最终回答", "workflow raw text should stay on safe summarized wording");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_workflow_status_restore.js (" + pass + " assertions)");
