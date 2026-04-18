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
    reLaunch: function () {},
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

  return require(runtimePath);
}

run("runtime pending conversation and intent are one-shot consumables", function () {
  var runtime = loadRuntime({ token: "token_demo" });

  runtime.setPendingConversationId("conv_42");
  runtime.setPendingChatIntent("继续上次的问题", "DEEP");

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

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_runtime_state.js (" + pass + " assertions)");
