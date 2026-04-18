// test_chat_points_sync.js — chat hero points should follow wallet balance

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

function loadChatPage(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var pageDef = null;
  var storage = Object.assign({}, (overrides && overrides.storage) || {});
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        if (raw && typeof raw === "object" && raw.data && typeof raw.data === "object") {
          return raw.data;
        }
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({ username: "chenyh2008", points: 0 });
      },
      getWallet: function () {
        return Promise.resolve({ balance: 88 });
      },
      getPoints: function () {
        return Promise.resolve({ points: 0 });
      },
    },
    (overrides && overrides.api) || {},
  );
  var authMock = {
    getToken: function () {
      return "token";
    },
    setToken: function () {},
  };
  var helpersMock = {
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
    setTheme: function () {},
  };
  var runtimeMock = {
    initNetworkMonitor: function () {},
    checkAuth: function (cb) {
      cb();
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
    clearWorkspaceBack: function () {},
  };
  var flagsMock = {
    shouldShowWorkspaceShell: function () {
      return false;
    },
    isFeatureEnabled: function () {
      return true;
    },
  };
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return authMock;
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/logger") return { warn: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route") return { billing: function () { return "/billing"; } };
      if (request === "../../utils/flags") return flagsMock;
      if (request === "../../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key] || "";
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
      showToast: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
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

  page._syncWorkspaceChrome = function () {};
  page._syncWorkspaceBack = function () {};
  page._setWorkspaceShellHidden = function () {};
  page._shouldShowWorkspaceShell = function () {
    return false;
  };
  page._loadDashboard = function () {};
  page._checkDiagnostic = function () {};
  page._setupObserver = function () {};
  page._restoreConversation = function () {};
  page.clearMessages = function () {};
  page._send = function () {};

  return { page: page };
}

(async function main() {
  await run("chat hero points should prefer wallet balance over stale profile points", async function () {
    var loaded = loadChatPage({
      api: {
        getUserInfo: function () {
          return Promise.resolve({ username: "chenyh2008", points: 0 });
        },
        getWallet: function () {
          return Promise.resolve({ balance: 128 });
        },
      },
    });

    loaded.page.onLoad({});
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(loaded.page.data.userPoints === 128, "chat hero points should update from wallet balance");
    assert(loaded.page.data.billingBalance === 128, "billing balance should stay in sync with wallet balance");
  });

  await run("chat hero points should fallback to legacy points api when wallet fails", async function () {
    var loaded = loadChatPage({
      api: {
        getUserInfo: function () {
          return Promise.resolve({ username: "chenyh2008", points: 0 });
        },
        getWallet: function () {
          return Promise.reject(new Error("wallet unavailable"));
        },
        getPoints: function () {
          return Promise.resolve({ points: 36 });
        },
      },
    });

    loaded.page.onLoad({});
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(loaded.page.data.userPoints === 36, "chat hero points should fallback to points api");
    assert(loaded.page.data.billingBalance === 36, "fallback points should sync billing balance too");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_chat_points_sync.js (" + pass + " assertions)");
})();
