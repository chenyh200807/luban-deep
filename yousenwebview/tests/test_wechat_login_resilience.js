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

function createHelpersMock() {
  return {
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
        screenHeight: 812,
        safeArea: { bottom: 778 },
        windowWidth: 375,
      };
    },
    isDark: function () {
      return true;
    },
  };
}

function createRouteMock() {
  return {
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
    },
    resolveInternalUrl: function (_value, fallback) {
      return fallback;
    },
    register: function () {
      return "/packageDeeptutor/pages/register/register";
    },
    manualLogin: function () {
      return "/packageDeeptutor/pages/login/manual";
    },
    login: function () {
      return "/packageDeeptutor/pages/login/login";
    },
  };
}

function loadPage(relativePath, options) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef = null;
  var state = {
    wxLoginCalls: 0,
    wxLoginCodes: [],
    reLaunchCalls: [],
    authTokens: [],
  };
  var loginCodes = (options && options.loginCodes) || ["code-1"];
  var apiMock = Object.assign(
    {
      wxLogin: function () {
        return Promise.resolve({
          token: "token_1",
          expires_at: 1800000000,
          user: { user_id: "user_1" },
        });
      },
      bindPhone: function () {
        return Promise.resolve({ ok: true });
      },
      getUserInfo: function () {
        return Promise.resolve({});
      },
      describeRequestError: function (err, fallbackMsg) {
        return fallbackMsg + "::" + String((err && err.message) || "");
      },
      shouldRetryWechatLogin: function () {
        return false;
      },
    },
    (options && options.api) || {},
  );
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    setInterval: function () {
      return 1;
    },
    clearInterval: function () {},
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return false;
          },
          clearToken: function () {},
          setToken: function (token, expiresAt) {
            state.authTokens.push({ token: token, expiresAt: expiresAt || 0 });
          },
        };
      }
      if (request === "../../utils/helpers") return createHelpersMock();
      if (request === "../../utils/route") return createRouteMock();
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: Object.assign(
      {
        login: function (config) {
          var code = loginCodes[state.wxLoginCalls];
          state.wxLoginCalls += 1;
          state.wxLoginCodes.push(code || "");
          config.success({ code: code || "" });
        },
        reLaunch: function (config) {
          state.reLaunchCalls.push(config.url);
        },
        navigateTo: function () {},
        showModal: function () {},
        showToast: function () {},
      },
      (options && options.wx) || {},
    ),
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: relativePath });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
    _initOrbScene: function () {},
    _initSubtitleScene: function () {},
    _startOrbMotion: function () {},
    _stopOrbMotion: function () {},
    _startSubtitleAutoPlay: function () {},
    _stopSubtitleAutoPlay: function () {},
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    state: state,
  };
}

(async function main() {
  var pageCases = [
    {
      path: "packageDeeptutor/pages/login/login.js",
      handler: "handleWechatLogin",
    },
    {
      path: "packageDeeptutor/pages/register/register.js",
      handler: "handleWechatRegister",
    },
  ];

  await run("wechat login should retry once with a fresh wx.login code after transient upstream failure", async function () {
    for (var i = 0; i < pageCases.length; i++) {
      var attempts = 0;
      var loaded = loadPage(pageCases[i].path, {
        loginCodes: ["code-first", "code-second"],
        api: {
          wxLogin: function (code) {
            attempts += 1;
            if (attempts === 1) {
              return Promise.reject(new Error("HTTP_502: {\"detail\":\"WeChat code2Session request timed out. Please try again.\"}"));
            }
            return Promise.resolve({
              token: "token_after_retry",
              expires_at: 1800000123,
              user: { user_id: "user_1" },
            });
          },
          shouldRetryWechatLogin: function (err) {
            return String((err && err.message) || "").indexOf("code2Session") >= 0;
          },
        },
      });

      loaded.page[pageCases[i].handler]();
      await flushPromises();
      await flushPromises();
      await flushPromises();

      assert(
        attempts === 2,
        pageCases[i].path + " should retry wxLogin once after transient upstream failure",
      );
      assert(
        loaded.state.wxLoginCalls === 2 &&
          loaded.state.wxLoginCodes[0] === "code-first" &&
          loaded.state.wxLoginCodes[1] === "code-second",
        pageCases[i].path + " should fetch a fresh wx.login code for the retry",
      );
      assert(
        loaded.state.reLaunchCalls.length === 1,
        pageCases[i].path + " should relaunch after retry succeeds",
      );
    }
  });

  await run("wechat login should surface timeout-specific message instead of generic network failure", async function () {
    var loaded = loadPage("packageDeeptutor/pages/login/login.js", {
      loginCodes: ["code-first", "code-second"],
      api: {
        wxLogin: function () {
          return Promise.reject(new Error("NETWORK_ERROR: request:fail timeout"));
        },
        shouldRetryWechatLogin: function () {
          return true;
        },
        describeRequestError: function (_err, _fallbackMsg) {
          return "请求超时，请稍后重试";
        },
      },
    });

    loaded.page.handleWechatLogin();
    await flushPromises();
    await flushPromises();
    await flushPromises();

    assert(
      loaded.state.wxLoginCalls === 2,
      "login page should still perform one safe retry before surfacing timeout-specific failure",
    );
    assert(
      loaded.page.data.errorMsg === "请求超时，请稍后重试",
      "login page should show timeout-specific message instead of generic network failure",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_wechat_login_resilience.js (" + pass + " assertions)");
})();
