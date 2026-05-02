// test_deeptutor_runtime_state.js — runtime state regression checks

var path = require("path");

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

function loadRuntime(options) {
  var config = options && typeof options === "object" ? options : {};
  var runtimePath = path.join(__dirname, "../packageDeeptutor/utils/runtime.js");
  var authPath = path.join(__dirname, "../packageDeeptutor/utils/auth.js");
  delete require.cache[require.resolve(runtimePath)];
  delete require.cache[require.resolve(authPath)];

  global.wx = {
    reLaunch: function (opts) {
      if (opts && typeof opts.complete === "function") {
        opts.complete();
      }
    },
    navigateTo: function () {},
    getNetworkType: function (opts) {
      if (opts && typeof opts.success === "function") {
        opts.success({ networkType: "wifi" });
      }
    },
    onNetworkStatusChange: function () {},
    getStorageSync: function () {
      return config.token || "";
    },
    removeStorageSync: function () {},
  };
  global.getCurrentPages = function () {
    return config.pages || [];
  };
  if (config.app) {
    global.getApp = function () {
      return config.app;
    };
  } else {
    delete global.getApp;
  }

  return require(runtimePath);
}

run("runtime state reads and writes app globalData when app is available", function () {
  var app = {
    globalData: {
      goHomeFlag: false,
      pendingConversationId: null,
      pendingChatQuery: "",
      pendingChatMode: "AUTO",
      networkAvailable: true,
      _authRedirecting: false,
    },
  };
  var runtime = loadRuntime({ token: "token_demo", app: app });

  runtime.markGoHome();
  runtime.setPendingConversationId("conv_42");
  runtime.setPendingChatIntent("继续上次的问题", "DEEP");
  runtime.setNetworkAvailable(false);
  runtime.setAuthRedirecting(true);

  assert(
    runtime.peekPendingConversationId() === "conv_42",
    "pending conversation id should be readable before consume",
  );
  assert(app.globalData.goHomeFlag === true, "goHomeFlag should sync into app globalData");
  assert(
    app.globalData.pendingConversationId === "conv_42",
    "pending conversation id should sync into app globalData",
  );
  assert(
    app.globalData.pendingChatQuery === "继续上次的问题",
    "pending chat query should sync into app globalData",
  );
  assert(
    app.globalData.pendingChatMode === "DEEP",
    "pending chat mode should sync into app globalData",
  );
  assert(app.globalData.networkAvailable === false, "network availability should sync into app globalData");
  assert(app.globalData._authRedirecting === true, "auth redirecting should sync into app globalData");

  assert(
    runtime.consumeGoHomeFlag() === true,
    "goHomeFlag should be consumed from the app globalData authority",
  );
  assert(app.globalData.goHomeFlag === false, "goHomeFlag should clear in app globalData after consume");
  assert(
    runtime.consumePendingConversationId() === "conv_42",
    "pending conversation id should be returned on first consume",
  );
  assert(
    app.globalData.pendingConversationId === "",
    "pending conversation id should clear in app globalData after consume",
  );
  assert(
    runtime.consumePendingConversationId() === "",
    "pending conversation id should be cleared after consume",
  );

  var intent = runtime.consumePendingChatIntent();
  assert(intent.query === "继续上次的问题", "pending chat intent should preserve query");
  assert(intent.mode === "DEEP", "pending chat intent should preserve mode");
  assert(
    app.globalData.pendingChatQuery === "",
    "pending chat query should clear in app globalData after consume",
  );
  assert(
    app.globalData.pendingChatMode === "AUTO",
    "pending chat mode should reset in app globalData after consume",
  );
  runtime.setWorkspaceBack("/packageDeeptutor/pages/report/report", "学情");
  assert(
    runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat") &&
      runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat").url ===
        "/packageDeeptutor/pages/report/report",
    "workspaceBack should still be managed by runtime when app is available",
  );
  assert(
    typeof app.globalData.workspaceBackUrl === "undefined" &&
      typeof app.globalData.workspaceBackLabel === "undefined",
    "workspaceBack should not be copied into app globalData",
  );

  var emptyIntent = runtime.consumePendingChatIntent();
  assert(emptyIntent.query === "", "pending chat query should clear after consume");
  assert(emptyIntent.mode === "AUTO", "pending chat mode should reset to AUTO after consume");
  assert(runtime.isNetworkAvailable() === false, "network availability should read from app globalData");
  assert(runtime.isAuthRedirecting() === true, "auth redirecting should read from app globalData");

  runtime.setAuthRedirecting(false);
  assert(app.globalData._authRedirecting === false, "auth redirecting should clear in app globalData");
});

run("runtime logout clears mirrored app globalData state", function () {
  var reLaunchCalls = [];
  var app = {
    globalData: {
      goHomeFlag: true,
      pendingConversationId: "conv_88",
      pendingChatQuery: "旧问题",
      pendingChatMode: "DEEP",
      networkAvailable: true,
      _authRedirecting: false,
    },
  };
  var runtime = loadRuntime({
    token: "token_demo",
    app: app,
  });

  global.wx.reLaunch = function (opts) {
    reLaunchCalls.push(opts);
    if (opts && typeof opts.complete === "function") {
      opts.complete();
    }
  };

  runtime.logout();

  assert(app.globalData.goHomeFlag === false, "logout should clear goHomeFlag in app globalData");
  assert(
    app.globalData.pendingConversationId === "",
    "logout should clear pendingConversationId in app globalData",
  );
  assert(app.globalData.pendingChatQuery === "", "logout should clear pendingChatQuery in app globalData");
  assert(app.globalData.pendingChatMode === "AUTO", "logout should reset pendingChatMode in app globalData");
  assert(app.globalData._authRedirecting === false, "logout should release auth redirecting in app globalData");
  assert(
    reLaunchCalls.length === 1 && reLaunchCalls[0].url === "/packageDeeptutor/pages/login/login",
    "logout should redirect to login",
  );
});

run("runtime workspaceBack ignores self-target and clears on consume", function () {
  var runtime = loadRuntime({
    token: "token_demo",
    pages: [{ route: "packageDeeptutor/pages/chat/chat" }],
  });

  runtime.setWorkspaceBack("/packageDeeptutor/pages/report/report", "学情");
  var back = runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat");
  assert(back && back.url === "/packageDeeptutor/pages/report/report", "workspaceBack should return external target");
  assert(back && back.label === "学情", "workspaceBack should preserve label");

  var consumed = runtime.consumeWorkspaceBack("/packageDeeptutor/pages/chat/chat");
  assert(consumed && consumed.url === "/packageDeeptutor/pages/report/report", "workspaceBack should be returned once");
  assert(runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat") === null, "workspaceBack should clear after consume");

  runtime.setWorkspaceBack("/packageDeeptutor/pages/chat/chat", "对话");
  assert(runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat") === null, "workspaceBack should suppress self-target loops");
});

run("runtime pending conversation and intent still work without app fallback", function () {
  var runtime = loadRuntime({ token: "token_demo" });

  runtime.setPendingConversationId("conv_42");
  runtime.setPendingChatIntent("继续上次的问题", "DEEP");

  assert(
    runtime.peekPendingConversationId() === "conv_42",
    "pending conversation id should be readable from fallback store before consume",
  );
  assert(
    runtime.consumePendingConversationId() === "conv_42",
    "pending conversation id should be returned on first consume",
  );
  assert(
    runtime.consumePendingConversationId() === "",
    "pending conversation id should be cleared after consume",
  );

  var intent = runtime.consumePendingChatIntent();
  assert(intent.query === "继续上次的问题", "pending chat intent should preserve query");
  assert(intent.mode === "DEEP", "pending chat intent should preserve mode");

  var emptyIntent = runtime.consumePendingChatIntent();
  assert(emptyIntent.query === "", "pending chat query should clear after consume");
  assert(emptyIntent.mode === "AUTO", "pending chat mode should reset to AUTO after consume");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_runtime_state.js (" + pass + " assertions)");
