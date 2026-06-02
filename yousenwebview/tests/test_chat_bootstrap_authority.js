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
        return Promise.resolve({ messages: [{ id: "u1", role: "user", content: "上一轮" }] });
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
      logout: function () {},
    },
    (overrides && overrides.runtime) || {},
  );
  var authMock = Object.assign(
    {
      getToken: function () {
        return "token";
      },
    },
    (overrides && overrides.auth) || {},
  );
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") {
        return authMock;
      }
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/ai-message-state") return {};
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
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") {
        return {
          track: function () {},
          trackOnce: function () {},
        };
      }
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route") return { billing: function () { return ""; } };
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
      if (request === "../../utils/history-tombstone") return { rememberDeletedConversationIds: function () {} };
      if (request === "../../utils/learning-home-view-model") return require(path.join(__dirname, "../packageDeeptutor/utils/learning-home-view-model.js"));
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
    this.setData({ messages: messages || [], hasMessages: !!(messages && messages.length) });
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
    toastCalls: toastCalls,
  };
}

(async function main() {
  await run("chat page should not wait for profile bootstrap before entering send pipeline", async function () {
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
  });

  await run("chat page should keep pending auto-send independent from degraded profile bootstrap", async function () {
    var sendCount = 0;
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
          return { query: "继续上一题", mode: "AUTO" };
        },
      },
    });

    loaded.page._send = function () {
      sendCount += 1;
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

    assert(sendCount === 1, "pending auto-send should use token authority even when profile is degraded");
    assert(dashboardCount === 0, "pending auto-send should not spend a dashboard request before start-turn");
    assert(diagnosticCount === 0, "pending auto-send should not spend a diagnostic request before start-turn");
  });

  await run("chat page should still hydrate hero dashboard when profile bootstrap is degraded", async function () {
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

    assert(dashboardCount === 1, "hero dashboard should still load without a pending send");
    assert(diagnosticCount === 1, "hero diagnostic prompt should still load without a pending send");
  });

  await run("hero diagnostic check should wait for dashboard hydration", async function () {
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

    assert(diagnosticCount === 0, "diagnostic request should not compete with the dashboard request");

    dashboardDeferred.resolve();
    await flushPromises();
    await flushPromises();

    assert(diagnosticCount === 1, "diagnostic request should run after dashboard hydration settles");
  });

  await run("chat page should keep a default today focus when dashboard request fails", async function () {
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

    assert(loaded.page.data.focusTitle === "今日推进", "dashboard failure should still set default focus title");
    assert(loaded.page.data.focusText === "今日推进", "dashboard failure should still make focus bar renderable");
  });

  await run("chat page should hydrate the current session when returning from workspace shell", async function () {
    var loaded = loadChatPage({
      storage: {
        current_session_id: "conv_return",
        current_session_ts: Date.now(),
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
  });

  await run("history entry should suppress hero before pending conversation hydration", async function () {
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
        loaded.apiState.getConversationMessagesCalls[0] === "conv_history_direct",
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
  });

  await run("manual send should not fail just because profile bootstrap later fails", async function () {
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
    assert(loaded.toastCalls.length === 0, "profile bootstrap failure should not toast over an active send");
  });

  await run("chat page should not call profile bootstrap or create conversation after auth redirect starts", async function () {
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
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_chat_bootstrap_authority.js (" + pass + " assertions)");
})();
