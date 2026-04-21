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

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadWsStream(config) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/ws-stream.js"),
    "utf8",
  );
  var timers = [];
  var connects = [];
  var tasks = [];
  var ensureTokenCalls = 0;
  var tokenQueue = (config.tokens || []).slice();

  function fakeSetTimeout(fn, delay) {
    var handle = {
      fn: fn,
      delay: delay,
      cleared: false,
    };
    timers.push(handle);
    return handle;
  }

  function fakeClearTimeout(handle) {
    if (handle) {
      handle.cleared = true;
    }
  }

  function runTimers(maxDelay) {
    timers.forEach(function (handle) {
      if (!handle.cleared && handle.delay <= maxDelay) {
        handle.cleared = true;
        handle.fn();
      }
    });
  }

  var sandbox = {
    console: {
      warn: function () {},
      log: console.log,
      error: console.error,
    },
    setTimeout: fakeSetTimeout,
    clearTimeout: fakeClearTimeout,
    Promise: Promise,
    Math: {
      max: Math.max,
      min: Math.min,
      pow: Math.pow,
      floor: Math.floor,
      random: function () {
        return 0;
      },
    },
    require: function (request) {
      if (request === "./auth") {
        return {
          getToken: function () {
            return "stale-token";
          },
        };
      }
      if (request === "./api") {
        return {
          unwrapResponse: function (raw) {
            return raw;
          },
          startChatTurn: function () {
            return Promise.resolve({
              stream: {
                url: "/api/v1/ws",
                subscribe: { turn_id: "turn_1" },
              },
              conversation: { id: "conv_1" },
            });
          },
          ensureFreshAuthToken: function () {
            ensureTokenCalls += 1;
            return Promise.resolve(tokenQueue.shift() || "");
          },
        };
      }
      if (request === "./endpoints") {
        return {
          getPrimaryBaseUrl: function () {
            return "https://api.example.com";
          },
          getSocketUrlCandidates: function () {
            return ["wss://api.example.com/api/v1/ws"];
          },
        };
      }
      if (request === "./host-runtime") {
        return {
          getChatEngine: function () {
            return "";
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      connectSocket: function (options) {
        var handlers = {};
        var task = {
          onOpen: function (fn) {
            handlers.open = fn;
          },
          onClose: function (fn) {
            handlers.close = fn;
          },
          onError: function (fn) {
            handlers.error = fn;
          },
          onMessage: function (fn) {
            handlers.message = fn;
          },
          send: function () {},
          close: function () {},
          _open: function () {
            if (handlers.open) handlers.open();
          },
          _close: function (payload) {
            if (handlers.close) handlers.close(payload || {});
          },
        };
        connects.push(options);
        tasks.push(task);
        return task;
      },
    },
    module: { exports: {} },
    exports: {},
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/ws-stream.js",
  });

  return {
    wsStream: sandbox.module.exports,
    connects: connects,
    tasks: tasks,
    runTimers: runTimers,
    getEnsureTokenCalls: function () {
      return ensureTokenCalls;
    },
  };
}

(async function main() {
  await run("ws stream should use fresh token for initial socket connect", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });

    loaded.wsStream.streamChat(
      { query: "继续", sessionId: "conv_1" },
      { onError: function () {} },
    );

    await flushPromises();
    await flushPromises();

    assert(loaded.getEnsureTokenCalls() === 1, "initial socket connect should request a fresh token once");
    assert(loaded.connects.length === 1, "initial socket should connect once");
    assert(
      loaded.connects[0].header.Authorization === "Bearer fresh-token-1",
      "initial socket connect should use refreshed bearer token instead of stale snapshot",
    );
  });

  await run("ws reconnect should re-read fresh token instead of reusing stale snapshot", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1", "fresh-token-2"],
    });

    loaded.wsStream.streamChat(
      { query: "继续", sessionId: "conv_1" },
      { onError: function () {} },
    );

    await flushPromises();
    await flushPromises();

    loaded.tasks[0]._close({ code: 1006, reason: "dropped" });
    loaded.runTimers(1000);
    await flushPromises();
    await flushPromises();

    assert(loaded.getEnsureTokenCalls() === 2, "reconnect should request a fresh token again");
    assert(loaded.connects.length === 2, "reconnect should open a second socket");
    assert(
      loaded.connects[1].header.Authorization === "Bearer fresh-token-2",
      "reconnect should use the newest token instead of the startup snapshot",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_ws_stream_auth_refresh.js (" + pass + " assertions)");
})();
