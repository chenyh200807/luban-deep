var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) pass++;
  else {
    fail++;
    errors.push("FAIL: " + message);
  }
}

function loadTelemetry(state) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/surface-telemetry.js"),
    "utf8",
  );
  var requests = [];
  var storage = {};
  var sandbox = {
    console: console,
    Date: Date,
    Math: Math,
    module: { exports: {} },
    require: function (request) {
      if (request === "./auth") {
        return { getToken: function () { return state.token; } };
      }
      if (request === "./endpoints") {
        return { getPrimaryBaseUrl: function () { return "https://example.test"; } };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        requests.push(options);
        if (state.networkOnline === false && typeof options.fail === "function") {
          options.fail({ errMsg: "request:fail network disconnected" });
        }
      },
      getStorageSync: function (key) { return storage[key]; },
      setStorageSync: function (key, value) { storage[key] = value; },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "surface-telemetry.js" });
  return { telemetry: sandbox.module.exports, requests: requests };
}

(function testPreAuthQueueFlushesAfterLogin() {
  var state = { token: "", networkOnline: true };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "login", action: "view" },
  });
  assert(loaded.requests.length === 0, "pre-auth event is queued, not rejected by server");
  state.token = "tok";
  loaded.telemetry.track("auth_result", {
    metadata: { module: "login", action: "complete", result: "success" },
  });
  assert(loaded.requests.length === 2, "login flushes queued event before current event");
  assert(
    loaded.requests[0].data.event_name === "module_viewed" &&
      loaded.requests[1].data.event_name === "auth_result",
    "pre-auth order is preserved",
  );
})();

(function testNetworkFailureRetriesStableEnvelope() {
  var state = { token: "tok", networkOnline: false };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("chat_message_sent", {
    metadata: { module: "chat", action: "send" },
  });
  state.networkOnline = true;
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "chat", action: "view" },
  });
  assert(loaded.requests.length === 3, "failed event retries on next online track");
  assert(
    loaded.requests[0].data.event_id === loaded.requests[1].data.event_id,
    "retry keeps stable event_id",
  );
  assert(
    loaded.requests[1].data.event_name === "chat_message_sent" &&
      loaded.requests[2].data.event_name === "module_viewed",
    "recovered event is flushed before current event",
  );
})();

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_surface_telemetry_pending_queue.js (" + pass + " assertions)");
