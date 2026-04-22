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
  var authState = {
    setTokenCalls: [],
  };
  var apiMock = Object.assign(
    {
      unwrapResponse: function (raw) {
        return raw;
      },
      getUserInfo: function () {
        return Promise.resolve({ id: "wx_user_bootstrap", username: "chenyh2008", points: 12 });
      },
    },
    (overrides && overrides.api) || {},
  );
  var authMock = {
    getToken: function () {
      return "token";
    },
    getUserId: function () {
      return "local_login_user";
    },
    setToken: function (token, userId) {
      authState.setTokenCalls.push({ token: token, userId: userId });
    },
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
    syncTabBar: function () {},
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
      if (request === "../../utils/surface-telemetry") {
        return { track: function () {}, trackOnce: function () {} };
      }
      if (request === "../../utils/runtime") return runtimeMock;
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") return flagsMock;
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      removeStorageSync: function () {},
      nextTick: function (fn) {
        if (typeof fn === "function") fn();
      },
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
  page._loadDashboard = function () {};
  page._checkDiagnostic = function () {};
  page._restoreConversation = function () {};
  page._send = function () {};
  page._setupObserver = function () {};

  return {
    page: page,
    authState: authState,
  };
}

(async function main() {
  await run("chat bootstrap should not rewrite auth authority from auth profile payload", async function () {
    var loaded = loadChatPage();

    loaded.page.onLoad({});
    loaded.page.onShow();
    await flushPromises();
    await flushPromises();

    assert(
      loaded.authState.setTokenCalls.length === 0,
      "chat bootstrap must not call auth.setToken after getUserInfo succeeds",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_chat_auth_authority.js (" + pass + " assertions)");
})();
