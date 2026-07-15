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
    errors.push(
      "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
    );
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function createDeferred() {
  var deferred = {};
  deferred.promise = new Promise(function (resolve, reject) {
    deferred.resolve = resolve;
    deferred.reject = reject;
  });
  return deferred;
}

function loadChatPage(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var toastCalls = [];
  var storage = Object.assign({}, (overrides && overrides.storage) || {});
  var apiState = {
    getUserInfoCalls: 0,
    createConversationCalls: 0,
    getConversationMessagesCalls: [],
  };
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        return raw;
      },
      describeRequestError: function (_err, fallbackMsg) {
        return fallbackMsg;
      },
      getUserInfo: function () {
        apiState.getUserInfoCalls += 1;
        return Promise.resolve({ username: "chenyh2008", points: 18 });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 18 });
      },
      getPoints: function () {
        return Promise.resolve({ points: 18 });
      },
      getHomeDashboard: function () {
        return Promise.resolve({
          today_focus: { title: "今日焦点：建筑实务案例题" },
          review: { overdue: 0, due_today: 0 },
        });
      },
      createConversation: function () {
        apiState.createConversationCalls += 1;
        return Promise.resolve({ conversation: { id: "conv_001" } });
      },
      getConversationMessages: function (id) {
        apiState.getConversationMessagesCalls.push(id);
        return Promise.resolve({
          messages: [{ id: "u1", role: "user", content: "上一轮" }],
        });
      },
    },
    (overrides && overrides.api) || {},
  );
  var runtimeMock = Object.assign(
    {
      initNetworkMonitor: function () {},
      isNetworkAvailable: function () {
        return true;
      },
      checkAuth: function (cb) {
        if (typeof cb === "function") {
          cb("token");
        }
        return true;
      },
      consumeGoHomeFlag: function () {
        return false;
      },
      consumePendingConversationId: function () {
        return "";
      },
      peekPendingConversationId: function () {
        return "";
      },
      consumePendingChatIntent: function () {
        return {};
      },
      // 2026-06-12 契约演进（paywall）：chat.js 新增 _showLoginGate 调用 runtime.setPendingChatIntent
      // 以便游客保留发送内容到登录后恢复，需在 mock 中注册该函数。
      setPendingChatIntent: function () {},
      redirectToLogin: function () {},
      logout: function () {},
    },
    (overrides && overrides.runtime) || {},
  );
  var authMock = Object.assign(
    {
      getToken: function () {
        return "token";
      },
      getUserId: function () {
        return "student-a";
      },
      readOwnerStorage: function (key) {
        var envelope = storage[key + ":student-a"];
        if (!envelope || envelope.ownerId !== "student-a") return null;
        return envelope.value;
      },
      writeOwnerStorage: function (key, value) {
        storage[key + ":student-a"] = { ownerId: "student-a", value: value };
        return true;
      },
      removeOwnerStorage: function (key) {
        delete storage[key + ":student-a"];
        return true;
      },
    },
    (overrides && overrides.auth) || {},
  );
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout:
      overrides && overrides.immediateTimers
        ? function (fn) {
            if (typeof fn === "function") fn();
            return 1;
          }
        : setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") {
        return authMock;
      }
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/ai-message-state")
        return (overrides && overrides.aiMessageState) || {};
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
          isDark: function () {
            return true;
          },
          getTimeGreeting: function () {
            return "上午好";
          },
          vibrate: function () {},
        };
      }
      if (request === "../../utils/logger") {
        return {
          warn: function () {},
          error: function () {},
        };
      }
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") {
        return (overrides && overrides.chatTurnRecovery) || {};
      }
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") {
        return {
          track: function () {},
          trackOnce: function () {},
          trackModuleView: function () {},
          trackModuleExit: function () {},
        };
      }
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route")
        return {
          billing: function () {
            return "";
          },
        };
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
        return { track: function () {} };
      }
      if (request === "../../utils/history-tombstone")
        return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model")
        return require(
          path.join(
            __dirname,
            "../packageDeeptutor/utils/learning-home-view-model.js",
          ),
        );
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
      showToast: function (options) {
        toastCalls.push(options || {});
      },
      nextTick: function (fn) {
        if (typeof fn === "function") fn();
      },
      navigateTo: function () {},
      showModal: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  page._syncWorkspaceBack = function () {};
  page._setWorkspaceShellHidden = function () {};
  page._shouldShowWorkspaceShell = function () {
    return false;
  };
  page._syncWorkspaceChrome = function () {};
  if (!(overrides && overrides.preserveLoadDashboard)) {
    page._loadDashboard = function () {};
  }
  page._checkDiagnostic = function () {};
  page._applyHydratedConversationMessages = function (messages) {
    this.setData({
      messages: messages || [],
      hasMessages: !!(messages && messages.length),
    });
  };
  page._setupObserver = function () {};
  page._stop = function () {};
  page._scheduleSessionPersist = function () {};
  page._doSendCallCount = 0;
  page._doSend = function () {
    this._doSendCallCount += 1;
  };

  return {
    page: page,
    apiState: apiState,
    storage: storage,
    toastCalls: toastCalls,
  };
}

(async function main() {
  await run(
    "chat page should not wait for profile bootstrap before entering send pipeline",
    async function () {
      var bootstrapDeferred = createDeferred();
      var loaded = loadChatPage({
        api: {
          getUserInfo: function () {
            loaded.apiState.getUserInfoCalls += 1;
            return bootstrapDeferred.promise;
          },
        },
      });

      loaded.page.onLoad({});
      loaded.page.onShow();
      loaded.page._send("帮我分析这道题");
      await flushPromises();

      assert(
        loaded.apiState.createConversationCalls === 0,
        "first turn should not pre-create conversation while profile bootstrap is pending",
      );
      assert(
        loaded.page._doSendCallCount === 1,
        "send pipeline should use token authority and continue without waiting for profile bootstrap",
      );

      bootstrapDeferred.resolve({ username: "chenyh2008", points: 18 });
      await flushPromises();
      await flushPromises();

      assert(
        loaded.apiState.createConversationCalls === 0,
        "profile bootstrap completion should not add a separate create-conversation roundtrip",
      );
      assert(
        loaded.page._doSendCallCount === 1,
        "profile bootstrap completion should not replay the same send",
      );
    },
  );

  await run(
    "chat page should keep pending auto-send independent from degraded profile bootstrap",
    async function () {
      var sendCount = 0;
      var sentOptions = null;
      var dashboardCount = 0;
      var diagnosticCount = 0;
      var loaded = loadChatPage({
        api: {
          getUserInfo: function () {
            loaded.apiState.getUserInfoCalls += 1;
            return Promise.reject(new Error("profile temporarily unavailable"));
          },
        },
        runtime: {
          consumePendingChatIntent: function () {
            return {
              query: "继续上一题",
              mode: "AUTO",
              followupQuestionContext: {
                question_id: "q_wrong_1",
                question: "地下防水卷材搭接做法正确的是？",
                question_type: "choice",
              },
            };
          },
        },
      });

      loaded.page._send = function (_query, opts) {
        sendCount += 1;
        sentOptions = opts || null;
      };
      loaded.page._loadDashboard = function () {
        dashboardCount += 1;
      };
      loaded.page._checkDiagnostic = function () {
        diagnosticCount += 1;
      };

      loaded.page.onLoad({});
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        sendCount === 1,
        "pending auto-send should use token authority even when profile is degraded",
      );
      assert(
        sentOptions &&
          sentOptions.followupQuestionContext &&
          sentOptions.followupQuestionContext.question_id === "q_wrong_1",
        "pending auto-send should preserve followup question context",
      );
      assert(
        dashboardCount === 0,
        "pending auto-send should not spend a dashboard request before start-turn",
      );
      assert(
        diagnosticCount === 0,
        "pending auto-send should not spend a diagnostic request before start-turn",
      );
    },
  );

  await run(
    "chat page should still hydrate hero dashboard when profile bootstrap is degraded",
    async function () {
      var dashboardCount = 0;
      var diagnosticCount = 0;
      var loaded = loadChatPage({
        api: {
          getUserInfo: function () {
            loaded.apiState.getUserInfoCalls += 1;
            return Promise.reject(new Error("profile temporarily unavailable"));
          },
        },
      });

      loaded.page._loadDashboard = function () {
        dashboardCount += 1;
      };
      loaded.page._checkDiagnostic = function () {
        diagnosticCount += 1;
      };

      loaded.page.onLoad({});
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        dashboardCount === 1,
        "hero dashboard should still load without a pending send",
      );
      assert(
        diagnosticCount === 1,
        "hero diagnostic prompt should still load without a pending send",
      );
    },
  );

  await run(
    "hero diagnostic check should wait for dashboard hydration",
    async function () {
      var dashboardDeferred = createDeferred();
      var diagnosticCount = 0;
      var loaded = loadChatPage({});

      loaded.page._loadDashboard = function () {
        return dashboardDeferred.promise;
      };
      loaded.page._checkDiagnostic = function () {
        diagnosticCount += 1;
      };

      loaded.page.onLoad({});
      loaded.page.onShow();
      await flushPromises();

      assert(
        diagnosticCount === 0,
        "diagnostic request should not compete with the dashboard request",
      );

      dashboardDeferred.resolve();
      await flushPromises();
      await flushPromises();

      assert(
        diagnosticCount === 1,
        "diagnostic request should run after dashboard hydration settles",
      );
    },
  );

  await run(
    "chat page should hide today focus when dashboard request fails",
    async function () {
      var loaded = loadChatPage({
        preserveLoadDashboard: true,
        api: {
          getHomeDashboard: function () {
            return Promise.reject(new Error("NETWORK_ERROR"));
          },
        },
      });

      loaded.page._loadDashboard();
      await flushPromises();

      assert(
        loaded.page.data.focusTitle === "",
        "dashboard failure should not render a non-canonical default focus title",
      );
      assert(
        loaded.page.data.focusText === "",
        "dashboard failure should not make the focus bar renderable",
      );
    },
  );

  await run(
    "chat page should hydrate the current session when returning from workspace shell",
    async function () {
      var loaded = loadChatPage({
        storage: {
          "deeptutor.chat.currentSession.v1:student-a": {
            ownerId: "student-a",
            value: { conversationId: "conv_return", savedAt: Date.now() },
          },
        },
      });

      loaded.page.onLoad({});
      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        loaded.apiState.getConversationMessagesCalls.length === 1 &&
          loaded.apiState.getConversationMessagesCalls[0] === "conv_return",
        "returning to chat with a current session should hydrate that conversation",
      );
      assert(
        loaded.page.data.hasMessages === true,
        "hydrated current session should restore the visible chat, not an empty hero",
      );
    },
  );

  await run(
    "chat page should discard local draft sessions before hydration",
    async function () {
      var loaded = loadChatPage({
        storage: {
          "deeptutor.chat.currentSession.v1:student-a": {
            ownerId: "student-a",
            value: { conversationId: "s_1780445194569", savedAt: Date.now() },
          },
        },
      });

      loaded.page.onLoad({});
      loaded.page.onShow();
      await flushPromises();

      assert(
        loaded.apiState.getConversationMessagesCalls.length === 0,
        "local draft session ids should not be hydrated as backend conversations",
      );
      assert(
        loaded.page._convId === null,
        "local draft session should not remain as the current conversation id",
      );
    },
  );

  await run(
    "history entry should suppress hero before pending conversation hydration",
    async function () {
      var pendingConversationId = "conv_history_direct";
      var pendingChatIntentConsumed = false;
      var sendCount = 0;
      var loaded = loadChatPage({
        runtime: {
          peekPendingConversationId: function () {
            return pendingConversationId;
          },
          consumePendingConversationId: function () {
            var id = pendingConversationId;
            pendingConversationId = "";
            return id;
          },
          consumePendingChatIntent: function () {
            pendingChatIntentConsumed = true;
            return { query: "我想练习建筑构造相关的题目", mode: "DEEP" };
          },
        },
      });
      loaded.page._send = function () {
        sendCount += 1;
      };

      loaded.page.onLoad({});
      assert(
        loaded.page.data.hasMessages === true,
        "pending history entry should enter chat chrome before the first hydration response",
      );

      loaded.page.onShow();
      await flushPromises();
      await flushPromises();

      assert(
        loaded.apiState.getConversationMessagesCalls.length === 1 &&
          loaded.apiState.getConversationMessagesCalls[0] ===
            "conv_history_direct",
        "pending history entry should hydrate the selected conversation directly",
      );
      assert(
        loaded.page.data.hasMessages === true,
        "hydrated history entry should remain on the chat surface",
      );
      assert(
        pendingChatIntentConsumed === true && sendCount === 0,
        "history restore should consume but not replay stale pending chat intent",
      );
    },
  );

  await run(
    "manual send should not fail just because profile bootstrap later fails",
    async function () {
      var bootstrapDeferred = createDeferred();
      var loaded = loadChatPage({
        api: {
          getUserInfo: function () {
            loaded.apiState.getUserInfoCalls += 1;
            return bootstrapDeferred.promise;
          },
        },
      });

      loaded.page.onLoad({});
      loaded.page.onShow();
      loaded.page._send("帮我分析这道题");
      await flushPromises();
      assert(
        loaded.apiState.createConversationCalls === 0,
        "manual send should avoid the extra create-conversation roundtrip",
      );
      assert(
        loaded.page._doSendCallCount === 1,
        "manual send should enter stream pipeline before non-authoritative profile bootstrap resolves",
      );

      bootstrapDeferred.reject(new Error("profile temporarily unavailable"));
      await flushPromises();
      await flushPromises();

      assert(
        loaded.apiState.createConversationCalls === 0,
        "profile bootstrap failure should not trigger create-conversation",
      );
      assert(
        loaded.page._doSendCallCount === 1,
        "profile bootstrap failure should not roll back an already-started send",
      );
      assert(
        loaded.toastCalls.length === 0,
        "profile bootstrap failure should not toast over an active send",
      );
    },
  );

  await run(
    "manual send should release stale pending recovery instead of leaving the chat locked",
    async function () {
      var loaded = loadChatPage({});
      loaded.page._sid = "conv_stale";
      loaded.page._convId = "conv_stale";
      loaded.page._pendingTurn = {
        conversationId: "conv_stale",
        baselineCount: 1,
        query: "上一轮卡住的问题",
        clientTurnId: "client_stale",
        createdAt: Date.now(),
      };
      loaded.page._pendingRecoveryActive = true;
      loaded.page._abort = null;
      loaded.page.setData({
        hasMessages: true,
        isStreaming: true,
        messages: [{ id: "u0", role: "user", content: "上一轮卡住的问题" }],
      });

      loaded.page._send("我现在要问新问题");

      assert(
        loaded.page._doSendCallCount === 1,
        "manual send should enter the stream pipeline after releasing stale pending recovery",
      );
      assert(
        loaded.page._pendingTurn === null,
        "stale pending recovery should be demoted before the new turn becomes authoritative",
      );
      assert(
        loaded.page._sid === "conv_stale" &&
          loaded.page._convId === "conv_stale",
        "manual send should keep the current conversation anchor while releasing only the stale recovery state",
      );
    },
  );

  await run(
    "manual send should still refuse while an active stream is running",
    async function () {
      var loaded = loadChatPage({});
      loaded.page._sid = "conv_active";
      loaded.page._convId = "conv_active";
      loaded.page._pendingRecoveryActive = true;
      loaded.page._abort = function () {};
      loaded.page.setData({
        hasMessages: true,
        isStreaming: true,
        messages: [{ id: "a0", role: "ai", content: "", streaming: true }],
      });

      loaded.page._send("不要打断活跃流");

      assert(
        loaded.page._doSendCallCount === 0,
        "manual send should not start a second turn while an active stream still owns the surface",
      );
    },
  );

  await run(
    "chat page should not call profile bootstrap or create conversation after auth redirect starts",
    async function () {
      var loaded = loadChatPage({
        auth: {
          getToken: function () {
            return "";
          },
        },
        runtime: {
          checkAuth: function () {
            return true;
          },
        },
      });

      loaded.page.onLoad({});
      loaded.page._send("帮我分析这道题");
      await flushPromises();

      assert(
        loaded.apiState.getUserInfoCalls === 0,
        "manual send should not bootstrap auth profile when the authoritative token is already missing",
      );
      assert(
        loaded.apiState.createConversationCalls === 0,
        "manual send should not create conversation after auth redirect starts",
      );
    },
  );

  await run(
    "cold-start pending turn recovery should not lock manual input",
    async function () {
      var never = createDeferred();
      var loaded = loadChatPage({
        storage: {
          "chat_pending_turn_v1:student-a": {
            ownerId: "student-a",
            value: {
              conversationId: "conv_pending",
              baselineCount: 1,
              query: "上一轮较慢的问题",
              clientTurnId: "client_pending",
              createdAt: Date.now(),
            },
          },
        },
        api: {
          getConversationMessages: function (id) {
            loaded.apiState.getConversationMessagesCalls.push(id);
            return never.promise;
          },
        },
        chatTurnRecovery: {
          hasRecoveredAssistant: function () {
            return false;
          },
        },
      });

      loaded.page.onLoad({});
      assert(
        loaded.page.data.isStreaming === false,
        "pending turn cold start should show chat chrome without claiming an active stream",
      );

      loaded.page.onShow();
      await flushPromises();

      assert(
        loaded.page.data.isStreaming === false,
        "background pending recovery must keep the input sendable",
      );
      assert(
        loaded.page._pendingRecoveryActive === true,
        "background recovery should still try to recover the authoritative pending turn",
      );
      assert(
        loaded.page._pendingTurn &&
          loaded.page._pendingTurn.conversationId === "conv_pending",
        "background recovery must not erase the durable pending turn before terminal recovery",
      );
    },
  );

  await run(
    "cold-start pending turn recovery should not hydrate incomplete server history",
    async function () {
      var hydratedCalls = 0;
      var loaded = loadChatPage({
        immediateTimers: true,
        storage: {
          "chat_pending_turn_v1:student-a": {
            ownerId: "student-a",
            value: {
              conversationId: "conv_pending_incomplete",
              baselineCount: 0,
              query: "上一轮较慢的问题",
              clientTurnId: "client_pending_incomplete",
              turnId: "turn_pending_incomplete",
              createdAt: Date.now(),
            },
          },
        },
        api: {
          getConversationMessages: function (id) {
            loaded.apiState.getConversationMessagesCalls.push(id);
            return Promise.resolve({
              messages: [
                {
                  role: "user",
                  content: "上一轮较慢的问题",
                  client_turn_id: "client_pending_incomplete",
                },
              ],
            });
          },
        },
        chatTurnRecovery: {
          hasRecoveredAssistant: function () {
            return false;
          },
        },
      });

      loaded.page._applyHydratedConversationMessages = function () {
        hydratedCalls += 1;
        this.setData({
          messages: [{ id: "server", role: "user", content: "不完整历史" }],
          hasMessages: true,
        });
      };
      loaded.page.setData({
        messages: [
          { id: "u0", role: "user", content: "上一轮较慢的问题" },
          { id: "a0", role: "ai", content: "本地仍在等待服务端结果", streaming: true },
        ],
        hasMessages: true,
        isStreaming: false,
        canStopStream: false,
      });

      loaded.page._startPendingTurnBackgroundRecovery();
      await flushPromises();
      await flushPromises();
      await flushPromises();

      assert(
        hydratedCalls === 0,
        "background recovery exhaustion should not hydrate incomplete canonical history",
      );
      assert(
        loaded.page.data.messages.length === 2 &&
          loaded.page.data.messages[1].content === "本地仍在等待服务端结果",
        "background recovery exhaustion should keep the local pending UI intact",
      );
      assert(
        loaded.page._pendingTurn &&
          loaded.page._pendingTurn.clientTurnId === "client_pending_incomplete",
        "background recovery exhaustion should preserve pending identity",
      );
    },
  );

  await run(
    "stream flush should use lightweight render state until done",
    async function () {
      var deriveCalls = 0;
      var loaded = loadChatPage({
        aiMessageState: {
          coerceUserVisibleContent: function (text) {
            return String(text || "");
          },
          deriveAiMessageRenderState: function () {
            deriveCalls += 1;
            return {
              renderableContent: "heavy",
              blocks: [{ id: "b1" }],
              mcqCards: null,
              mcqHint: "",
              mcqReceipt: "",
              mcqInteractiveReady: false,
              mcqReviewMode: false,
              originalContent: "",
              originalCollapsed: true,
              hasStructuredContent: false,
            };
          },
        },
      });
      loaded.page.setData({
        messages: [
          {
            id: "a0",
            role: "ai",
            content: "",
            renderableContent: "",
            blocks: [],
            streaming: true,
          },
        ],
      });
      loaded.page._streamId = "a0";
      loaded.page._messageIndexMap = { a0: 0 };
      loaded.page._buf = "第一段流式内容";

      loaded.page._flush();

      assert(
        deriveCalls === 0,
        "stream flush should not run heavy AI message derivation",
      );
      assert(
        loaded.page.data["messages[0].renderableContent"] === "第一段流式内容",
        "stream flush should still render visible text immediately",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log(
    "PASS test_chat_bootstrap_authority.js (" + pass + " assertions)",
  );
})();
