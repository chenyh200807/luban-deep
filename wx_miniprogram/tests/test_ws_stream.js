// test_ws_stream.js — regression tests for wx_miniprogram/utils/ws-stream.js
// Run: node wx_miniprogram/tests/test_ws_stream.js

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

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function flush() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

global.getApp = function () {
  return { globalData: {} };
};

var socketState = {
  sent: [],
  closed: [],
  handlers: {},
};

global.wx = {
  getStorageSync: function () {
    return "";
  },
  connectSocket: function (opts) {
    socketState.url = opts.url;
    socketState.handlers = {};
    return {
      send: function (payload) {
        socketState.sent.push(JSON.parse(payload.data));
      },
      close: function (info) {
        socketState.closed.push(info || {});
        if (socketState.handlers.close) {
          socketState.handlers.close(info || {});
        }
      },
      onOpen: function (fn) {
        socketState.handlers.open = fn;
      },
      onMessage: function (fn) {
        socketState.handlers.message = fn;
      },
      onError: function (fn) {
        socketState.handlers.error = fn;
      },
      onClose: function (fn) {
        socketState.handlers.close = fn;
      },
    };
  },
};

var auth = require("../utils/auth");
var api = require("../utils/api");
var endpoints = require("../utils/endpoints");
var wsStream = require("../utils/ws-stream");

auth.getToken = function () {
  return "";
};
api.startChatTurn = function () {
  return Promise.resolve({
    stream: {
      url: "/api/v1/ws",
      subscribe: { turn_id: "turn_1" },
      resume: { seq: 0 },
      chat_id: "session_1",
    },
    conversation: { id: "session_1" },
  });
};
api.unwrapResponse = function (raw) {
  return raw;
};
endpoints.getPrimaryBaseUrl = function () {
  return "https://example.com";
};
endpoints.getSocketUrlCandidates = function () {
  return ["wss://example.com/api/v1/ws"];
};

function emitMessage(payload) {
  if (socketState.handlers.message) {
    socketState.handlers.message({ data: JSON.stringify(payload) });
  }
}

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

Promise.resolve(
  run("stopStream sends cancel_turn and treats cancelled turn as graceful completion", async function () {
    socketState.sent = [];
    socketState.closed = [];
    socketState.handlers = {};

    var doneCount = 0;
    var errorCount = 0;
    var abort = wsStream.streamChat(
      {
        query: "帮我出一道题",
        sessionId: "session_1",
        mode: "AUTO",
      },
      {
        onDone: function () {
          doneCount += 1;
        },
        onError: function () {
          errorCount += 1;
        },
      },
    );

    await flush();
    if (socketState.handlers.open) {
      socketState.handlers.open();
    }

    assertEqual(socketState.sent[0], {
      type: "subscribe_turn",
      turn_id: "turn_1",
      after_seq: 0,
    }, "socket should subscribe to the active turn first");

    abort({ cancelTurn: true });

    assertEqual(socketState.sent[1], {
      type: "cancel_turn",
      turn_id: "turn_1",
    }, "abort with cancelTurn should request server-side cancellation");

    emitMessage({
      type: "error",
      content: "Turn cancelled",
      metadata: { turn_terminal: true, status: "cancelled" },
      turn_id: "turn_1",
      session_id: "session_1",
    });
    emitMessage({
      type: "done",
      metadata: { status: "cancelled" },
      turn_id: "turn_1",
      session_id: "session_1",
    });
    await flush();

    assert(doneCount === 1, "cancelled turn should still finish exactly once");
    assert(errorCount === 0, "cancelled turn should not surface as an error");
  }),
)
  .then(function () {
    return run("duplicate seq content events are ignored during reconnect replay", async function () {
      socketState.sent = [];
      socketState.closed = [];
      socketState.handlers = {};

      var tokens = [];
      var doneCount = 0;
      wsStream.streamChat(
        {
          query: "建筑构造是什么？",
          sessionId: "session_1",
          mode: "AUTO",
        },
        {
          onToken: function (token) {
            tokens.push(token);
          },
          onDone: function () {
            doneCount += 1;
          },
        },
      );

      await flush();
      if (socketState.handlers.open) {
        socketState.handlers.open();
      }

      emitMessage({
        type: "content",
        seq: 8,
        content: "## 结论\n",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "content",
        seq: 8,
        content: "## 结论\n",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "content",
        seq: 9,
        content: "建筑构造是组成方式。\n",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "done",
        seq: 10,
        turn_id: "turn_1",
        session_id: "session_1",
      });
      await flush();

      assertEqual(
        tokens,
        ["## 结论\n", "建筑构造是组成方式。\n"],
        "replayed content with the same seq should not be appended twice",
      );
      assert(doneCount === 1, "done should still complete exactly once after replay filtering");
    });
  })
  .then(function () {
    return run("telemetry callback emits ws/session/resume lifecycle events", async function () {
      socketState.sent = [];
      socketState.closed = [];
      socketState.handlers = {};

      var originalStartChatTurn = api.startChatTurn;
      api.startChatTurn = function () {
        return Promise.resolve({
          stream: {
            url: "/api/v1/ws",
            subscribe: { turn_id: "turn_telemetry" },
            resume: { seq: 7 },
            chat_id: "session_telemetry",
          },
          conversation: { id: "session_telemetry" },
        });
      };

      var telemetry = [];
      wsStream.streamChat(
        {
          query: "继续上一题",
          sessionId: "session_telemetry",
          mode: "AUTO",
        },
        {
          onTelemetryEvent: function (payload) {
            telemetry.push(payload);
          },
        },
      );

      await flush();
      if (socketState.handlers.open) {
        socketState.handlers.open();
      }

      emitMessage({
        type: "session",
        metadata: {
          session_id: "session_telemetry",
          turn_id: "turn_telemetry",
        },
      });
      emitMessage({
        type: "content",
        seq: 8,
        content: "恢复后的第一段内容",
        turn_id: "turn_telemetry",
        session_id: "session_telemetry",
      });
      await flush();

      api.startChatTurn = originalStartChatTurn;

      assertEqual(
        telemetry.map(function (item) {
          return item.eventName;
        }),
        [
          "ws_connected",
          "resume_attempted",
          "session_event_received",
          "resume_succeeded",
        ],
        "telemetry callback should expose ws/session/resume lifecycle in order",
      );
    });
  })
  .then(function () {
    return run("internal visibility events never enter user token or presentation callbacks", async function () {
      socketState.sent = [];
      socketState.closed = [];
      socketState.handlers = {};

      var tokens = [];
      var presentations = [];
      var statuses = [];
      wsStream.streamChat(
        {
          query: "建筑构造是什么？",
          sessionId: "session_1",
          mode: "AUTO",
        },
        {
          onToken: function (token) {
            tokens.push(token);
          },
          onPresentation: function (payload) {
            presentations.push(payload);
          },
          onStatus: function (payload) {
            statuses.push(payload);
          },
        },
      );

      await flush();
      if (socketState.handlers.open) {
        socketState.handlers.open();
      }

      emitMessage({
        type: "content",
        seq: 11,
        content: "我来读取相关技能文件。",
        visibility: "internal",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "progress",
        seq: 12,
        content: "后台处理中",
        visibility: "internal",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "result",
        seq: 13,
        visibility: "internal",
        metadata: {
          presentation: {
            type: "qa",
            answer: "不该显示",
          },
        },
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "content",
        seq: 14,
        content: "建筑构造是研究建筑物组成与连接方式的技术。",
        visibility: "public",
        turn_id: "turn_1",
        session_id: "session_1",
      });
      emitMessage({
        type: "done",
        seq: 15,
        turn_id: "turn_1",
        session_id: "session_1",
      });
      await flush();

      assertEqual(
        tokens,
        ["建筑构造是研究建筑物组成与连接方式的技术。"],
        "internal content must be dropped before onToken",
      );
      assertEqual(presentations, [], "internal result presentation must be dropped");
      assertEqual(statuses, [], "internal status events must be dropped");
    });
  })
  .then(function () {
    if (fail) {
      console.error(errors.join("\n"));
      process.exit(1);
    }
    console.log("PASS test_ws_stream.js (" + pass + " assertions)");
  });
