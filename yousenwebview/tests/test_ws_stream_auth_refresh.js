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
  var sent = [];
  var startPayloads = [];
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
          startChatTurn: function (payload) {
            startPayloads.push(payload || {});
            return Promise.resolve(config.startResponse || {
              stream: {
                url: "/api/v1/ws",
                subscribe: { turn_id: "turn_1" },
              },
              conversation: { id: "conv_1" },
            });
          },
          ensureFreshAuthToken: function () {
            ensureTokenCalls += 1;
            if (config.tokenError) return Promise.reject(config.tokenError);
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
          send: function (payload) {
            sent.push(JSON.parse(payload.data));
          },
          close: function () {},
          _open: function () {
            if (handlers.open) handlers.open();
          },
          _close: function (payload) {
            if (handlers.close) handlers.close(payload || {});
          },
          _message: function (payload) {
            if (handlers.message) {
              handlers.message({ data: JSON.stringify(payload || {}) });
            }
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
    sent: sent,
    startPayloads: startPayloads,
    runTimers: runTimers,
    getTimerDelays: function () {
      return timers
        .filter(function (handle) {
          return !handle.cleared;
        })
        .map(function (handle) {
          return handle.delay;
        });
    },
    getEnsureTokenCalls: function () {
      return ensureTokenCalls;
    },
  };
}

(async function main() {
  var direct = loadWsStream({ tokens: ["fresh-token-1"] }).wsStream;
  assert(
    direct.normalizeErrorMessage('HTTP_500: {"detail":"Internal Server Error"}') ===
      "服务暂时不可用，请稍后重试",
    "HTTP 500 details should not be exposed to users",
  );
  assert(
    direct.normalizeErrorMessage("read_file path=\"/app/data/HEARTBEAT.md\"") ===
      "服务暂时不可用，请稍后重试",
    "internal file operation errors should not be exposed to users",
  );

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

  await run("fresh-token failure should fail before opening a socket", async function () {
    var loaded = loadWsStream({
      tokenError: new Error("AUTH_EXPIRED"),
    });
    var errors = [];
    var doneCount = 0;

    loaded.wsStream.streamChat(
      { query: "继续", sessionId: "conv_1" },
      {
        onError: function (message) {
          errors.push(message);
        },
        onDone: function () {
          doneCount += 1;
        },
      },
    );

    await flushPromises();
    await flushPromises();

    assert(loaded.getEnsureTokenCalls() === 1, "token refresh should be attempted once");
    assert(loaded.connects.length === 0, "socket must not open when fresh auth token cannot be resolved");
    assert(errors[0] === "登录已失效，请重新登录", "auth refresh failure should use unified auth error copy");
    assert(doneCount === 1, "auth refresh failure should finish the local stream once");
  });

  await run("first-turn stream should let start-turn create the conversation", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var started = [];

    loaded.wsStream.streamChat(
      { query: "错题复盘：房子", clientTurnId: "client_turn_new" },
      {
        onStarted: function (payload) {
          started.push(payload || {});
        },
        onError: function () {},
      },
    );

    await flushPromises();
    await flushPromises();

    assert(loaded.startPayloads.length === 1, "start-turn should run even without a pre-created session id");
    assert(
      !Object.prototype.hasOwnProperty.call(loaded.startPayloads[0], "conversation_id"),
      "first-turn payload should omit conversation_id so backend start-turn owns session creation",
    );
    assert(
      started.length === 1 &&
        started[0].sessionId === "conv_1" &&
        started[0].turnId === "turn_1",
      "stream should surface backend-created conversation and turn ids to the page",
    );
    loaded.tasks[0]._open();
    assert(
      loaded.sent[0].type === "subscribe_turn" && loaded.sent[0].turn_id === "turn_1",
      "socket should subscribe to the authoritative turn returned by start-turn",
    );
  });

  await run("public result should project next_best_action display fields only", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var finals = [];

    loaded.wsStream.streamChat(
      { query: "继续", sessionId: "conv_1" },
      {
        onFinal: function (payload) {
          finals.push(payload || {});
        },
        onError: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.tasks[0]._message({
      type: "result",
      visibility: "public",
      metadata: {
        response: "已完成批改。",
        next_best_action: {
          title: "先补一题可诊断练习",
          target: "屋面防水\n薄弱点",
          query: "针对我的薄弱点出一道练习题：屋面防水薄弱点。出题后等我作答再批改。",
          why_this_now: "刚刚错在构造层级。",
          materials: ["教材第 5 章", "", "错题本"],
          success_measure: "能独立说出 2 个设防层级",
          action_type: "practice",
          intent: { internal: true },
          evidence_refs: ["hidden"],
          training_intent_id: "secret",
        },
      },
      turn_id: "turn_1",
      session_id: "conv_1",
    });
    await flushPromises();

    assert(finals.length === 1, "result event should emit one final payload");
    assert(
      finals[0].next_best_action &&
        finals[0].next_best_action.title === "先补一题可诊断练习",
      "next_best_action title should be projected for display",
    );
    assert(
      finals[0].next_best_action &&
        finals[0].next_best_action.target.indexOf("\n") === -1,
      "next_best_action target should be sanitized before reaching the page",
    );
    assert(
      finals[0].next_best_action &&
        finals[0].next_best_action.materials.length === 2,
      "next_best_action materials should drop blank entries",
    );
    assert(
      finals[0].next_best_action &&
        finals[0].next_best_action.query ===
          "针对我的薄弱点出一道练习题：屋面防水薄弱点。出题后等我作答再批改。",
      "next_best_action query should be projected for the page action",
    );
    assert(
      Object.keys(finals[0].next_best_action).sort().join(",") ===
        "materials,query,successMeasure,target,title,whyThisNow",
      "next_best_action should expose only page display fields",
    );
    assert(
      finals[0].next_best_action &&
        !Object.prototype.hasOwnProperty.call(finals[0].next_best_action, "intent") &&
        !Object.prototype.hasOwnProperty.call(finals[0].next_best_action, "evidence_refs") &&
        !Object.prototype.hasOwnProperty.call(finals[0].next_best_action, "training_intent_id"),
      "next_best_action must not expose internal training authority fields",
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

  await run("early cancel should wait for the created turn and send cancel_turn", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });

    var statuses = [];
    var abort = loaded.wsStream.streamChat(
      { query: "请系统分析一套完整提分方案", sessionId: "conv_1", clientTurnId: "client_turn_1" },
      {
        onStatus: function (payload) {
          statuses.push(payload);
        },
      },
    );

    abort({ cancelTurn: true });
    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();

    assert(
      loaded.startPayloads[0] && loaded.startPayloads[0].client_turn_id === "client_turn_1",
      "start-turn payload should preserve the surface client turn id",
    );
    assert(loaded.sent[0].type === "subscribe_turn", "early cancel should subscribe to the created turn first");
    assert(loaded.sent[1].type === "cancel_turn", "early cancel should then cancel the authoritative turn");
    assert(
      statuses.some(function (item) { return item.data === "cancelling"; }),
      "early cancel should expose a visible stopping status",
    );
  });

  await run("start-turn payload should preserve explicit generation capability", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });

    loaded.wsStream.streamChat(
      {
        query: "请出 3 道同类选择题",
        sessionId: "conv_1",
        capability: "deep_question",
        promptIntent: {
          learning_signal_type: "assessment_wrong_item_practice",
          attempt_ref: "attempt_signed",
        },
      },
      { onError: function () {} },
    );

    await flushPromises();
    await flushPromises();

    assert(
      loaded.startPayloads[0] && loaded.startPayloads[0].capability === "deep_question",
      "wrong-item practice should reach backend deep_question authority instead of default chat",
    );
    assert(
      loaded.startPayloads[0] &&
        loaded.startPayloads[0].prompt_intent &&
        loaded.startPayloads[0].prompt_intent.attempt_ref === "attempt_signed",
      "explicit generation capability should not drop assessment prompt intent",
    );
  });

  await run("start-turn payload should send only canonical followup question context", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });

    loaded.wsStream.streamChat(
      {
        query: "我选A",
        sessionId: "conv_1",
        followupQuestionContext: {
          question_id: "q_visible_1",
          question: "压型金属板屋面最低坡度是多少？",
          question_type: "choice",
          options: { A: "5%", B: "1%" },
          user_answer: "A",
        },
        structuredSubmitContext: {
          questions: [{ question_id: "q_visible_1", selected_answer: "A" }],
        },
      },
      { onError: function () {} },
    );

    await flushPromises();
    await flushPromises();

    assert(
      loaded.startPayloads[0] &&
        loaded.startPayloads[0].followup_question_context &&
        loaded.startPayloads[0].followup_question_context.question_id === "q_visible_1",
      "start-turn should receive canonical followup question context",
    );
    assert(
      !Object.prototype.hasOwnProperty.call(loaded.startPayloads[0], "structuredSubmitContext") &&
        !Object.prototype.hasOwnProperty.call(loaded.startPayloads[0], "structured_submit_context"),
      "start-turn payload must not grow a second structured submit authority",
    );
  });

  await run("default idle budget should outlive long case grading turns", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });

    loaded.wsStream.streamChat(
      { query: "请批改这道案例题", sessionId: "conv_1" },
      {
        onStatus: function () {},
        onError: function () {},
        onDone: function () {},
      },
    );

    await flushPromises();
    await flushPromises();

    assert(
      loaded.getTimerDelays().some(function (delay) {
        return delay >= 210000;
      }),
      "default idle timeout should wait beyond the 180s server turn deadline",
    );
  });

  await run("idle timeout should wait for terminal event without cancelling authoritative turn", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var statuses = [];

    loaded.wsStream.streamChat(
      { query: "请分析一套完整的复习方案", sessionId: "conv_1", idleTimeoutMs: 5 },
      {
        onStatus: function (payload) {
          statuses.push(payload);
        },
        onError: function () {},
        onDone: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.runTimers(5);

    assert(loaded.sent[0].type === "subscribe_turn", "idle timeout should subscribe first");
    assert(
      loaded.sent.length === 1,
      "idle timeout must not cancel the authoritative server turn",
    );
    assert(
      statuses.some(function (item) {
        return item.data === "awaiting_terminal" && item.metadata && item.metadata.reason === "idle_timeout";
      }),
      "idle timeout should expose a visible terminal-wait status",
    );
  });

  await run("repeated idle ticks should keep waiting for terminal outcome", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var statuses = [];
    var errors = [];

    loaded.wsStream.streamChat(
      {
        query: "请分析一套完整的复习方案",
        sessionId: "conv_1",
        idleTimeoutMs: 5,
        maxTerminalWaitTicksAfterCancel: 2,
      },
      {
        onStatus: function (payload) {
          statuses.push(payload);
        },
        onError: function (message) {
          errors.push(message);
        },
        onDone: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.runTimers(5);
    loaded.runTimers(5);

    assert(loaded.sent[0].type === "subscribe_turn", "idle timeout should subscribe first");
    assert(
      loaded.sent.length === 1,
      "repeated idle ticks must not send cancel_turn",
    );
    assert(errors.length === 0, "second idle tick while waiting should not surface page-level timeout");
    assert(
      statuses.some(function (item) { return item.data === "awaiting_terminal"; }),
      "second idle tick should wait for the canonical terminal event",
    );
  });

  await run("idle wait exhaustion should not claim a stop request was sent", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var errors = [];

    loaded.wsStream.streamChat(
      {
        query: "请分析一套完整的复习方案",
        sessionId: "conv_1",
        idleTimeoutMs: 5,
        maxTerminalWaitTicksAfterCancel: 1,
      },
      {
        onStatus: function () {},
        onError: function (message) {
          errors.push(message);
        },
        onDone: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.runTimers(5);
    loaded.runTimers(5);
    loaded.runTimers(5);

    assert(loaded.sent.length === 1, "idle exhaustion must not send cancel_turn");
    assert(errors.length === 1, "idle exhaustion should surface one local wait-exhausted message");
    assert(
      errors[0].indexOf("停止请求") === -1,
      "idle exhaustion message must not claim a stop request was sent",
    );
  });

  await run("long gap after first token should keep visible case-analysis status alive", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var statuses = [];

    loaded.wsStream.streamChat(
      { query: "请批改这道案例题", sessionId: "conv_1" },
      {
        onStatus: function (payload) {
          statuses.push(payload);
        },
        onError: function () {},
        onDone: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.tasks[0]._message({
      type: "content",
      seq: 1,
      content: "这道案例题我已经进入逐采分点批改。",
    });
    loaded.runTimers(30000);

    assert(
      statuses.some(function (item) {
        return item.data === "analysis_continuing" && item.metadata && item.metadata.reason === "quiet_after_first_token";
      }),
      "long silence after first visible token should show a continuing-analysis status",
    );
    assert(loaded.sent.length === 1, "quiet visible-status tick must not cancel or resend the turn");
  });

  await run("public result should surface assistant_content as final response", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var finals = [];

    loaded.wsStream.streamChat(
      { query: "请批改案例题", sessionId: "conv_1" },
      {
        onFinal: function (payload) {
          finals.push(payload || {});
        },
        onError: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.tasks[0]._message({
      type: "result",
      visibility: "public",
      metadata: {
        assistant_content: "这是当前轮的最终批改答案",
      },
    });

    assert(
      finals.some(function (item) { return item.response === "这是当前轮的最终批改答案"; }),
      "current page should render result.metadata.assistant_content without waiting for history recovery",
    );
  });

  await run("public result must not use metadata.content as final response", async function () {
    var loaded = loadWsStream({
      tokens: ["fresh-token-1"],
    });
    var finals = [];

    loaded.wsStream.streamChat(
      { query: "请批改案例题", sessionId: "conv_1" },
      {
        onFinal: function (payload) {
          finals.push(payload || {});
        },
        onError: function () {},
      },
    );

    await flushPromises();
    await flushPromises();
    loaded.tasks[0]._open();
    loaded.tasks[0]._message({
      type: "result",
      visibility: "public",
      metadata: {
        content: "不应作为最终答案的内部内容",
        metadata: { content: "嵌套内部内容也不应作为最终答案" },
      },
    });

    assert(
      finals.length === 0,
      "metadata.content must not become a final answer projection",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_ws_stream_auth_refresh.js (" + pass + " assertions)");
})();
