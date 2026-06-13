var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];
var repoRoot = path.resolve(__dirname, "..", "..");

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

function createAuthMock() {
  return {
    setToken: function () {},
  };
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

function createSandbox(sourcePath, apiMock, extras) {
  var source = fs.readFileSync(sourcePath, "utf8");
  var pageDef = null;
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
      if (request === "../../utils/auth") return createAuthMock();
      if (request === "../../utils/helpers") return createHelpersMock();
      if (request === "../../utils/route") {
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
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request + " for " + sourcePath);
    },
    wx: Object.assign(
      {
        login: function (options) {
          options.success({ code: "wechat_code" });
        },
        switchTab: function () {},
        reLaunch: function () {},
        navigateTo: function () {},
        navigateBack: function () {},
        showModal: function () {},
        showToast: function () {},
      },
      extras || {},
    ),
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: sourcePath });

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

  return page;
}

(async function main() {
  var cases = [
    {
      path: path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      normalHandler: "handleWechatLogin",
      explicitHandler: "handleWechatPhoneNumber",
    },
    {
      path: path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/register/register.js"),
      normalHandler: "handleWechatRegister",
      explicitHandler: "handleWechatPhoneNumber",
    },
  ];

  await run("primary quick-login button must request phone authorization", async function () {
    var loginWxml = fs.readFileSync(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.wxml"),
      "utf8",
    );
    assert(
      loginWxml.indexOf('open-type="getPhoneNumber"') >= 0,
      "primary quick-login button should use getPhoneNumber",
    );
    assert(
      loginWxml.indexOf('bindgetphonenumber="handleWechatPhoneNumber"') >= 0,
      "primary quick-login button should bind handleWechatPhoneNumber",
    );
    assert(
      loginWxml.indexOf('bindtap="handleWechatLogin"') === -1,
      "primary quick-login button must not call plain wx.login handler",
    );
  });

  await run("plain wechat login/register handlers should not issue tokens", async function () {
    for (var i = 0; i < cases.length; i++) {
      var loginCalls = [];
      var apiMock = {
        wxLogin: function (value) {
          loginCalls.push(value);
          return Promise.resolve({ token: "token_1" });
        },
        wxLoginWithPhone: function () {
          return Promise.resolve({ token: "token_2" });
        },
        bindPhone: function () {
          return Promise.resolve({ token: "token_3" });
        },
        getUserInfo: function () {
          return Promise.resolve({});
        },
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
      };
      var page = createSandbox(cases[i].path, apiMock, {});
      page.setData({ username: "18688888431", phone: "18688888431" });
      page[cases[i].normalHandler]();
      await flushPromises();
      await flushPromises();
      assert(
        loginCalls.length === 0,
        cases[i].path + " should not issue a token from plain wx.login",
      );
    }
  });

  await run("explicit getPhoneNumber path should login with phone_code atomically", async function () {
    for (var i = 0; i < cases.length; i++) {
      var bindCalls = [];
      var loginCalls = [];
      var apiMock = {
        wxLogin: function () {
          throw new Error("plain wxLogin must not be called from phone authorization");
        },
        wxLoginWithPhone: function (loginCode, phoneCode) {
          loginCalls.push({ loginCode: loginCode, phoneCode: phoneCode });
          return Promise.resolve({
            token: "token_1",
            user_id: "user_1",
            user: { user_id: "user_1" },
          });
        },
        bindPhone: function (value) {
          bindCalls.push(value);
          return Promise.resolve({
            token: "token_2",
            user_id: "user_1",
            user: { user_id: "user_1" },
          });
        },
        getUserInfo: function () {
          return Promise.resolve({});
        },
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
        shouldRetryWechatLogin: function () {
          return false;
        },
      };
      var page = createSandbox(cases[i].path, apiMock, {});
      page[cases[i].explicitHandler]({
        detail: { code: "phone_code_123" },
      });
      await flushPromises();
      await flushPromises();
      assert(
        loginCalls.length === 1 &&
          loginCalls[0].loginCode === "wechat_code" &&
          loginCalls[0].phoneCode === "phone_code_123",
        cases[i].path + " should exchange wx.login code and phone code together",
      );
      assert(
        bindCalls.length === 0,
        cases[i].path + " should not mint a token before phone binding",
      );
    }
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_wechat_bind_phone_authority.js (" + pass + " assertions)");
})();
