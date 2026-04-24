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
      path: "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor/pages/login/login.js",
      normalHandler: "handleWechatLogin",
      explicitHandler: "handleWechatPhoneNumber",
    },
    {
      path: "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor/pages/register/register.js",
      normalHandler: "handleWechatRegister",
      explicitHandler: "handleWechatPhoneNumber",
    },
    {
      path: "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram/pages/login/login.js",
      normalHandler: "handleWechatLogin",
      explicitHandler: "handleWechatPhoneNumber",
    },
    {
      path: "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram/pages/register/register.js",
      normalHandler: "handleWechatRegister",
      explicitHandler: "handleWechatPhoneNumber",
    },
  ];

  await run("plain wechat login/register should not implicitly call bindPhone", async function () {
    for (var i = 0; i < cases.length; i++) {
      var bindCalls = [];
      var apiMock = {
        wxLogin: function () {
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
      };
      var page = createSandbox(cases[i].path, apiMock, {});
      page.setData({ username: "18688888431", phone: "18688888431" });
      page[cases[i].normalHandler]();
      await flushPromises();
      await flushPromises();
      assert(
        bindCalls.length === 0,
        cases[i].path + " should keep plain WeChat login separate from bindPhone",
      );
    }
  });

  await run("explicit getPhoneNumber path should remain the only bindPhone writer", async function () {
    for (var i = 0; i < cases.length; i++) {
      var bindCalls = [];
      var apiMock = {
        wxLogin: function () {
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
      };
      var page = createSandbox(cases[i].path, apiMock, {});
      page[cases[i].explicitHandler]({
        detail: { code: "phone_code_123" },
      });
      await flushPromises();
      await flushPromises();
      assert(
        bindCalls.length === 1 && bindCalls[0] === "phone_code_123",
        cases[i].path + " should only bind phone from explicit getPhoneNumber authorization",
      );
    }
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_wechat_bind_phone_authority.js (" + pass + " assertions)");
})();
