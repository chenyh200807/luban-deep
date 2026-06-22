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

function flushPromises() {
  return Promise.resolve().then(function () {
    return Promise.resolve();
  });
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
  var streamCallbacks = [];
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
          getConversationMessages: function () {
            return Promise.resolve({ messages: [] });
          },
        };
      }
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") {
        return {
          streamChat: function (opts, callbacks) {
            streamCalls.push(opts || {});
            streamCallbacks.push(callbacks || {});
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
          vibrate: function () {},
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
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") return require(path.join(__dirname, "../packageDeeptutor/utils/learning-home-view-model.js"));
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
    streamCallbacks: streamCallbacks,
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

  await run("first _doSend should skip pre-created conversation and adopt start-turn ids", async function () {
    var loaded = loadChatPage();
    loaded.page._sid = "";
    loaded.page._convId = null;

    loaded.page._doSend("错题复盘：房子");

    assert(loaded.streamCalls.length === 1, "first send should enter ws stream directly");
    assert(
      loaded.streamCalls[0].sessionId === "",
      "first send should not require a pre-created conversation id",
    );

    loaded.streamCallbacks[0].onStarted({
      sessionId: "tb_created_1",
      turnId: "turn_created_1",
      conversation: { id: "tb_created_1" },
      turn: { id: "turn_created_1" },
    });

    assert(loaded.page._sid === "tb_created_1", "start-turn conversation id should become page session id");
    assert(loaded.page._convId === "tb_created_1", "start-turn conversation id should become page conversation id");
    assert(
      loaded.page._pendingTurn &&
        loaded.page._pendingTurn.conversationId === "tb_created_1" &&
        loaded.page._pendingTurn.turnId === "turn_created_1",
      "pending turn recovery should persist the authoritative ids after start-turn returns",
    );
  });

  await run("final next_best_action should attach to the visible AI message", async function () {
    var loaded = loadChatPage();
    loaded.page._streamId = "a0";
    loaded.page._find = function (id) {
      return id === "a0" ? 0 : -1;
    };
    loaded.page.setData({
      messages: [
        {
          id: "a0",
          role: "ai",
          content: "已完成批改",
          renderableContent: "已完成批改",
          blocks: [],
          streaming: false,
        },
      ],
    });

    loaded.page._onFinal({
      next_best_action: {
        title: "先补一题可诊断练习",
        target: "屋面防水薄弱点",
      },
    });

    assert(
      loaded.page.data["messages[0].nextBestAction"] &&
        loaded.page.data["messages[0].nextBestAction"].title === "先补一题可诊断练习",
      "final next_best_action should be attached to the current visible AI message",
    );
  });

  await run("next_best_action tap should reuse server-projected query", async function () {
    var loaded = loadChatPage();
    var sentQuery = "";
    loaded.page._find = function (id) {
      return id === "a0" ? 0 : -1;
    };
    loaded.page._send = function (query) {
      sentQuery = query;
    };
    loaded.page.setData({
      isStreaming: false,
      messages: [
        {
          id: "a0",
          role: "ai",
          nextBestAction: {
            title: "先补一题可诊断练习",
            target: "屋面防水薄弱点",
            query: "请围绕屋面防水薄弱点出一道诊断题，等我作答后再批改。",
          },
        },
      ],
    });

    loaded.page.onNextBestActionTap({
      currentTarget: { dataset: { msgid: "a0" } },
    });

    assert(
      sentQuery === "请围绕屋面防水薄弱点出一道诊断题，等我作答后再批改。",
      "next_best_action tap should enter the existing _send pipeline with the server-projected query",
    );
  });

  await run("next_best_action tap should keep bounded fallback for legacy payloads", async function () {
    var loaded = loadChatPage();
    var sentQuery = "";
    loaded.page._find = function (id) {
      return id === "a0" ? 0 : -1;
    };
    loaded.page._send = function (query) {
      sentQuery = query;
    };
    loaded.page.setData({
      isStreaming: false,
      messages: [
        {
          id: "a0",
          role: "ai",
          nextBestAction: {
            title: "先补一题可诊断练习",
            target: "屋面防水薄弱点",
          },
        },
      ],
    });

    loaded.page.onNextBestActionTap({
      currentTarget: { dataset: { msgid: "a0" } },
    });

    assert(
      sentQuery === "针对我的薄弱点出一道练习题：屋面防水薄弱点。出题后等我作答再批改。",
      "legacy next_best_action payloads should still fall back to a bounded practice request",
    );
  });

  await run("first _doSend should not send a local draft session as conversation_id", async function () {
    var loaded = loadChatPage();
    loaded.page._sid = "s_1780445194569";
    loaded.page._convId = null;

    loaded.page._doSend("继续追问房子专项训练");

    assert(loaded.streamCalls.length === 1, "local draft session should still enter ws stream");
    assert(
      loaded.streamCalls[0].sessionId === "",
      "local draft session must not be sent as the backend conversation id",
    );
    assert(
      !loaded.page._pendingTurn,
      "pending turn should wait for the authoritative start-turn conversation id",
    );
  });

  await run("mcq submit should convert visible card state into canonical followup context", async function () {
    var loaded = loadChatPage();
    var payload = loaded.page._buildMcqSubmitPayload([
      {
        index: 1,
        questionId: "visible_q1",
        stem: "压型金属板屋面最低坡度是多少？",
        questionType: "single_choice",
        options: [
          { key: "A", text: "5%", selected: true },
          { key: "B", text: "1%" },
          { key: "C", text: "2%" },
          { key: "D", text: "3%" },
        ],
      },
    ]);

    assert(payload && payload.followupQuestionContext, "visible card submit should carry followup context");
    if (payload && payload.followupQuestionContext) {
      assert(
        payload.followupQuestionContext.question_id === "visible_q1",
        "visible card followup context should preserve question id",
      );
      assert(
        payload.followupQuestionContext.question === "压型金属板屋面最低坡度是多少？",
        "visible card followup context should preserve stem",
      );
      assert(
        payload.followupQuestionContext.options &&
          payload.followupQuestionContext.options.A === "5%",
        "visible card followup context should preserve options",
      );
      assert(
        payload.followupQuestionContext.user_answer === "A",
        "visible card followup context should preserve learner answer",
      );
    }
  });

  await run("retry should resend the original followup question context", async function () {
    var loaded = loadChatPage();
    loaded.page._sid = "tb_conv_retry";
    loaded.page._convId = "tb_conv_retry";

    loaded.page._doSend("我选A", {
      followupQuestionContext: {
        question_id: "retry_q1",
        question: "压型金属板屋面最低坡度是多少？",
        question_type: "choice",
        user_answer: "A",
      },
    });
    var aiMessage = loaded.page.data.messages[1];
    loaded.page.data.isStreaming = false;

    loaded.page.onRetry({ currentTarget: { dataset: { msgid: aiMessage.id } } });

    assert(loaded.streamCalls.length === 2, "retry should start a new stream turn");
    assert(
      loaded.streamCalls[1].followupQuestionContext &&
        loaded.streamCalls[1].followupQuestionContext.question_id === "retry_q1",
      "retry should preserve the original followup question context",
    );
    assert(
      loaded.streamCalls[1].persistUserMessage === false,
      "retry should still avoid duplicating the persisted user message",
    );
  });

  await run("done callback during recovery should not erase pending turn identity", async function () {
    var loaded = loadChatPage();
    var pending = {
      conversationId: "tb_conv_recover",
      baselineCount: 0,
      query: "你是谁",
      clientTurnId: "client_recover_1",
      turnId: "turn_recover_1",
      createdAt: Date.now(),
    };

    loaded.page._pendingTurn = pending;
    loaded.page._recoveringTurn = true;
    loaded.page._streamId = "missing-stream-message";
    loaded.page.setData({
      messages: [],
      isStreaming: true,
      canStopStream: true,
    });

    loaded.page._onDone();

    assert(
      loaded.page._pendingTurn &&
        loaded.page._pendingTurn.clientTurnId === "client_recover_1",
      "transport done after an error must not erase the pending turn before history recovery can use it",
    );
    assert(
      loaded.page._recoveringTurn === true,
      "transport done after an error must not mark recovery as finished",
    );
  });

  await run("done without visible answer should recover from canonical history", async function () {
    var loaded = loadChatPage();
    var pending = {
      conversationId: "tb_conv_done_empty",
      baselineCount: 0,
      query: "你能做什么",
      clientTurnId: "client_done_empty_1",
      turnId: "turn_done_empty_1",
      createdAt: Date.now(),
    };
    var recoveryCalls = [];
    var cleared = false;

    loaded.page._pendingTurn = pending;
    loaded.page._recoveringTurn = false;
    loaded.page._streamId = "a-empty";
    loaded.page._find = function (id) {
      return id === "a-empty" ? 0 : -1;
    };
    loaded.page._buildAiMessageUpdates = function () {
      return {
        state: {
          renderableContent: "",
          blocks: [],
          mcqCards: [],
        },
        updates: {},
      };
    };
    loaded.page._recoverTurnFromHistory = function (options) {
      recoveryCalls.push(options || {});
      return Promise.resolve(true);
    };
    loaded.page._clearPendingTurn = function () {
      cleared = true;
      this._pendingTurn = null;
    };
    loaded.page.setData({
      messages: [{ id: "a-empty", role: "ai", content: "", streaming: true }],
      isStreaming: true,
      canStopStream: true,
    });

    loaded.page._onDone();

    assert(
      recoveryCalls.length === 1,
      "terminal done with no rendered answer should trigger history recovery",
    );
    assert(
      recoveryCalls.length === 1 && recoveryCalls[0].unlockOnExhausted === true,
      "empty terminal recovery should unlock the composer if history still has no answer",
    );
    assert(
      loaded.page._pendingTurn &&
        loaded.page._pendingTurn.clientTurnId === "client_done_empty_1",
      "empty terminal recovery should keep pending identity until recovery finishes",
    );
    assert(!cleared, "empty terminal recovery should not clear pending synchronously");
  });

  await run("empty terminal recovery exhaustion should keep pending identity", async function () {
    var loaded = loadChatPage();
    var pending = {
      conversationId: "tb_conv_done_slow_history",
      baselineCount: 0,
      query: "案例题批改",
      clientTurnId: "client_done_slow_history_1",
      turnId: "turn_done_slow_history_1",
      createdAt: Date.now(),
    };
    var cleared = false;
    var hydrated = false;

    loaded.page._pendingTurn = pending;
    loaded.page._recoveringTurn = false;
    loaded.page._streamId = "a-empty-slow-history";
    loaded.page._find = function (id) {
      return id === "a-empty-slow-history" ? 0 : -1;
    };
    loaded.page._buildAiMessageUpdates = function () {
      return {
        state: {
          renderableContent: "",
          blocks: [],
          mcqCards: [],
        },
        updates: {},
      };
    };
    loaded.page._clearPendingTurn = function () {
      cleared = true;
      this._pendingTurn = null;
    };
    loaded.page._applyHydratedConversationMessages = function () {
      hydrated = true;
    };
    loaded.page.setData({
      messages: [{ id: "a-empty-slow-history", role: "ai", content: "", streaming: true }],
      isStreaming: true,
      canStopStream: true,
    });

    loaded.page._onDone();
    await flushPromises();

    assert(!cleared, "empty terminal recovery exhaustion must not clear pending identity");
    assert(!hydrated, "empty terminal recovery exhaustion must not hydrate incomplete history");
    assert(
      loaded.page._pendingTurn &&
        loaded.page._pendingTurn.clientTurnId === "client_done_slow_history_1",
      "empty terminal recovery exhaustion should preserve durable pending identity",
    );
    assert(
      loaded.page.data.isStreaming === false &&
        loaded.page.data.canStopStream === false,
      "empty terminal recovery exhaustion should unlock the composer",
    );
  });

  await run("error recovery exhaustion should not start a second terminal recovery", async function () {
    var loaded = loadChatPage();
    var pending = {
      conversationId: "tb_conv_error_exhausted",
      baselineCount: 0,
      query: "你是谁",
      clientTurnId: "client_error_exhausted_1",
      turnId: "turn_error_exhausted_1",
      createdAt: Date.now(),
    };
    var recoveryCalls = [];
    var cleared = false;

    loaded.page._pendingTurn = pending;
    loaded.page._recoveringTurn = false;
    loaded.page._streamId = "a-error-empty";
    loaded.page._find = function (id) {
      return id === "a-error-empty" ? 0 : -1;
    };
    loaded.page._buildWorkflowState = function () {
      return {};
    };
    loaded.page._setWorkflowState = function () {};
    loaded.page._buildAiMessageUpdates = function () {
      return {
        state: {
          renderableContent: "",
          blocks: [],
          mcqCards: [],
        },
        updates: {},
      };
    };
    loaded.page._recoverTurnFromHistory = function (options) {
      recoveryCalls.push(options || {});
      return Promise.resolve(false);
    };
    loaded.page._clearPendingTurn = function () {
      cleared = true;
      this._pendingTurn = null;
    };
    loaded.page.setData({
      messages: [{ id: "a-error-empty", role: "ai", content: "", streaming: true }],
      isStreaming: true,
      canStopStream: true,
    });

    loaded.page._onError("连接失败");
    await flushPromises();

    assert(
      recoveryCalls.length === 1,
      "once error recovery is exhausted, terminal cleanup should not start a second history recovery",
    );
    assert(cleared, "exhausted error recovery should clear pending so the composer unlocks");
    assert(loaded.page.data.isStreaming === false, "exhausted error recovery should stop streaming UI");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_chat_send_surface_telemetry.js (" + pass + " assertions)");
})();
