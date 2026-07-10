// 首体验漏斗埋点（2026-07-10）：/surface-events 强制登录后，pre-auth 事件
// 必须先入队、登录成功后随首个带 token 的事件冲刷，且保留原始 collected_at_ms。
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

function loadTelemetry(state) {
  var source = fs.readFileSync(
    path.join(__dirname, "..", "utils", "surface-telemetry.js"),
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
        return {
          getToken: function () {
            return state.token;
          },
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "https://example.test";
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      request: function (options) {
        requests.push(options);
        if (
          state.networkOnline === false &&
          typeof options.fail === "function"
        ) {
          options.fail({ errMsg: "request:fail network disconnected" });
        }
      },
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
    },
  };
  sandbox.global = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "surface-telemetry.js" });
  return { telemetry: sandbox.module.exports, requests: requests };
}

(function testPreAuthEventsAreQueuedNotSent() {
  var state = { token: "" };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "login", action: "view" },
  });
  assert(
    loaded.requests.length === 0,
    "pre-auth track must queue instead of firing wx.request (got " +
      loaded.requests.length +
      ")",
  );
})();

(function testQueueFlushesAfterLogin() {
  var state = { token: "" };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "login", action: "view" },
  });
  loaded.telemetry.track("auth_authorize_clicked", {
    metadata: { module: "login", action: "authorize" },
  });
  assert(loaded.requests.length === 0, "still queued before token");

  state.token = "tok_after_login";
  loaded.telemetry.track("auth_result", {
    metadata: { module: "login", action: "complete", result: "success" },
  });
  assert(
    loaded.requests.length === 3,
    "queued events + current event all delivered after login (got " +
      loaded.requests.length +
      ")",
  );
  var names = loaded.requests.map(function (r) {
    return r.data.event_name;
  });
  assert(
    names[0] === "module_viewed" &&
      names[1] === "auth_authorize_clicked" &&
      names[2] === "auth_result",
    "flush preserves queue order then current event (got " + names.join(",") + ")",
  );
  for (var i = 0; i < loaded.requests.length; i++) {
    assert(
      loaded.requests[i].header.Authorization === "Bearer tok_after_login",
      "flushed event " + i + " carries Authorization header",
    );
    assert(
      loaded.requests[i].data.collected_at_ms > 0 &&
        loaded.requests[i].data.collected_at_ms <=
          loaded.requests[i].data.sent_at_ms,
      "collected_at_ms preserved and not after sent_at_ms",
    );
  }
})();

(function testNetworkFailureIsRetriedAfterRecoveryWithStableEventId() {
  var state = { token: "tok", networkOnline: false };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("chat_message_sent", {
    metadata: { module: "chat", action: "send", seq: 1 },
  });
  assert(loaded.requests.length === 1, "online-auth event attempts delivery");

  state.networkOnline = true;
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "chat", action: "view", seq: 2 },
  });

  assert(
    loaded.requests.length === 3,
    "failed event retries before the recovery event (got " +
      loaded.requests.length +
      ")",
  );
  assert(
    loaded.requests[1].data.event_name === "chat_message_sent" &&
      loaded.requests[2].data.event_name === "module_viewed",
    "recovery flushes the failed event before the new event",
  );
  assert(
    loaded.requests[0].data.event_id === loaded.requests[1].data.event_id,
    "retry preserves event_id for server-side idempotency",
  );
  assert(
    loaded.requests[0].data.collected_at_ms ===
      loaded.requests[1].data.collected_at_ms,
    "retry preserves the original collection timestamp",
  );
})();

(function testQueueCapDropsOldest() {
  var state = { token: "" };
  var loaded = loadTelemetry(state);
  for (var i = 0; i < 25; i++) {
    loaded.telemetry.track("module_viewed", {
      metadata: { module: "chat", action: "view", seq: i },
    });
  }
  state.token = "tok";
  loaded.telemetry.track("chat_message_sent", {
    metadata: { module: "chat", action: "send" },
  });
  // 上限 20 条队列 + 1 条当前事件
  assert(
    loaded.requests.length === 21,
    "queue capped at 20 oldest-dropped (got " + loaded.requests.length + ")",
  );
  assert(
    loaded.requests[0].data.metadata.seq === 5,
    "oldest events dropped first (first flushed seq=" +
      loaded.requests[0].data.metadata.seq +
      ")",
  );
})();

(function testTrackProductBehaviorCarriesVisitId() {
  var state = { token: "tok" };
  var loaded = loadTelemetry(state);
  loaded.telemetry.trackProductBehavior("chat_message_sent", {
    module: "chat",
    action: "send",
    objectType: "chat_turn",
  });
  assert(loaded.requests.length === 1, "behavior event delivered with token");
  var meta = loaded.requests[0].data.metadata;
  assert(
    typeof meta.visit_id === "string" && meta.visit_id.length > 0,
    "trackProductBehavior injects visit_id (required by server validation)",
  );
  assert(
    meta.module === "chat" && meta.action === "send",
    "module/action mapped into metadata",
  );
})();

console.log("pass=" + pass + " fail=" + fail);
if (errors.length) {
  errors.forEach(function (line) {
    console.error(line);
  });
  process.exit(1);
}
