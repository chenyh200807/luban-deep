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
  var storage = state.storage || {};
  var sandbox = {
    console: console,
    Date: state.dateShim || Date,
    Math: Math,
    module: { exports: {} },
    require: function (request) {
      if (request === "./auth") {
        return {
          getToken: function () { return state.token; },
          getUserId: function () { return state.userId || ""; },
        };
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
        } else if (state.autoRespond && typeof options.success === "function") {
          options.success({ data: { accepted: true, status: "accepted" } });
        }
      },
      getStorageSync: function (key) { return storage[key]; },
      setStorageSync: function (key, value) { storage[key] = value; },
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "surface-telemetry.js" });
  return { telemetry: sandbox.module.exports, requests: requests, storage: storage };
}

(function testPreAuthQueueIsNotAttributedToLaterLogin() {
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
  assert(loaded.requests.length === 1, "login discards unowned pre-auth event instead of attributing it to the member");
  assert(
    loaded.requests[0].data.event_name === "auth_result",
    "only the authenticated member event is sent",
  );
})();

(function testAsyncRequestsDoNotResendInFlightQueue() {
  var state = { token: "tok", userId: "member-a", networkOnline: true };
  var loaded = loadTelemetry(state);
  for (var i = 0; i < 10; i++) {
    loaded.telemetry.track("module_viewed", {
      metadata: { module: "learning", action: "view", index: i },
    });
  }
  assert(loaded.requests.length === 10, "ten in-flight events produce ten requests, not a triangular retry storm");
  loaded.requests.forEach(function (request) {
    request.success({ data: { accepted: true, status: "accepted" } });
  });
})();

(function testAccountSwitchDoesNotReplayPriorOwnerEvents() {
  var state = { token: "tok-a", userId: "member-a", networkOnline: false };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "history", action: "view" },
  });
  var priorEventId = loaded.requests[0].data.event_id;
  state.token = "tok-b";
  state.userId = "member-b";
  state.networkOnline = true;
  state.autoRespond = true;
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "chat", action: "view" },
  });
  assert(loaded.requests.length === 2, "account switch drops mismatched owner event instead of replaying it");
  assert(loaded.requests[1].data.event_id !== priorEventId, "new owner only sends its own event");
})();

(function testNetworkFailureRetriesStableEnvelope() {
  var state = { token: "tok", userId: "member-a", networkOnline: false };
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

(function testOfflineStormIsBoundedByBackoff() {
  // 2026-07-19 事故回归：网络故障期密集埋点（练习返回触发 module_exited/
  // module_viewed 连环），旧实现每次 track 全量重放队列 → 300+ 请求风暴
  // 吃满 wx.request 并发，饿死 lessons/dashboard 业务请求。
  var clock = { nowMs: 1752900000000 };
  var dateShim = { now: function () { return clock.nowMs; } };
  var state = {
    token: "tok",
    userId: "member-a",
    networkOnline: false,
    dateShim: dateShim,
  };
  var loaded = loadTelemetry(state);
  for (var i = 0; i < 12; i++) {
    loaded.telemetry.track("module_exited", {
      metadata: { module: "practice", action: "return", seq: i },
    });
    clock.nowMs += 50;
  }
  assert(
    loaded.requests.length <= 4,
    "offline burst is capped by backoff, not amplified (got " +
      loaded.requests.length +
      " requests for 12 tracks)",
  );
  // 退避窗口过期 + 网络恢复后，队列恢复投递
  state.networkOnline = true;
  state.autoRespond = true;
  clock.nowMs += 61000;
  var before = loaded.requests.length;
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "learning", action: "view" },
  });
  assert(
    loaded.requests.length > before + 1,
    "queued events flush after backoff expires and network recovers",
  );
})();

(function testTerminalRejectionDequeuesEvent() {
  // 服务端明确终结拒收（422 等）：重发同一载荷无意义，必须出队，
  // 否则事件永不出队、队列涨满后放大所有后续 track。
  var state = { token: "tok", userId: "member-a", networkOnline: true };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("note_card_saved", {
    metadata: { module: "learning", action: "save" },
  });
  loaded.requests[0].success({ statusCode: 422, data: { detail: "invalid" } });
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "learning", action: "view" },
  });
  assert(
    loaded.requests.length === 2,
    "422-rejected event is dequeued, not replayed (got " +
      loaded.requests.length +
      ")",
  );
  var stored = loaded.storage["deeptutor_surface_telemetry_pending_v1"] || [];
  assert(
    stored.every(function (event) { return event.eventName !== "note_card_saved"; }),
    "terminally rejected event no longer persisted in pending queue",
  );
})();

(function testUnauthorizedKeepsEventQueuedAndBacksOff() {
  // 401 = token 过期：事件保留（等重新登录后随新 token 冲刷），但计入退避,
  // 避免过期 token 期间无限重发。
  var clock = { nowMs: 1752900000000 };
  var dateShim = { now: function () { return clock.nowMs; } };
  var state = {
    token: "tok-expired",
    userId: "member-a",
    networkOnline: true,
    dateShim: dateShim,
  };
  var loaded = loadTelemetry(state);
  loaded.telemetry.track("chat_message_sent", {
    metadata: { module: "chat", action: "send" },
  });
  loaded.requests[0].success({ statusCode: 401, data: {} });
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "chat", action: "view" },
  });
  loaded.requests[1].success({ statusCode: 401, data: {} });
  loaded.requests[2].success({ statusCode: 401, data: {} });
  var before = loaded.requests.length;
  loaded.telemetry.track("module_viewed", {
    metadata: { module: "learning", action: "view" },
  });
  assert(
    loaded.requests.length === before,
    "after repeated 401s tracking only enqueues during backoff (got " +
      (loaded.requests.length - before) +
      " extra requests)",
  );
  var stored = loaded.storage["deeptutor_surface_telemetry_pending_v1"] || [];
  assert(
    stored.some(function (event) { return event.eventName === "chat_message_sent"; }),
    "401 event stays queued for post-relogin flush",
  );
})();

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_surface_telemetry_pending_queue.js (" + pass + " assertions)");
