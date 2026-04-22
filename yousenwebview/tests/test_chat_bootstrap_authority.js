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
      createConversation: function () {
        apiState.createConversationCalls += 1;
        return Promise.resolve({ conversation: { id: "conv_001" } });
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
  page._loadDashboard = function () {};
  page._checkDiagnostic = function () {};
  page._restoreConversation = function () {};
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
  await run("chat page should wait for bootstrap auth validation before creating conversation", async function () {
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
      "conversation creation must wait until bootstrap auth validation resolves",
    );
    assert(
      loaded.page._doSendCallCount === 0,
      "send pipeline should not continue before bootstrap auth validation completes",
    );

    bootstrapDeferred.resolve({ username: "chenyh2008", points: 18 });
    await flushPromises();
    await flushPromises();

    assert(
      loaded.apiState.createConversationCalls === 1,
      "conversation creation should resume once bootstrap auth validation succeeds",
    );
    assert(
      loaded.page._doSendCallCount === 1,
      "send pipeline should continue after bootstrap auth validation succeeds",
    );
  });

  await run("chat page should block pending auto-send when bootstrap auth validation fails", async function () {
    var sendCount = 0;
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

    loaded.page.onLoad({});
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(sendCount === 0, "pending auto-send should stay blocked when auth bootstrap is not authoritative");
  });

  await run("chat page should not race past a failing bootstrap promise on manual send", async function () {
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
      "manual send should stay behind the in-flight bootstrap promise",
    );

    bootstrapDeferred.reject(new Error("profile temporarily unavailable"));
    await flushPromises();
    await flushPromises();

    assert(
      loaded.apiState.createConversationCalls === 0,
      "manual send should not create a conversation when bootstrap auth validation fails",
    );
    assert(
      loaded.page._doSendCallCount === 0,
      "manual send should not enter the stream pipeline when bootstrap auth validation fails",
    );
    assert(
      loaded.toastCalls.length >= 1 &&
        loaded.toastCalls[loaded.toastCalls.length - 1].title === "服务暂时不可用，请稍后重试",
      "manual send should surface an availability toast instead of a misleading create-conversation failure",
    );
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
