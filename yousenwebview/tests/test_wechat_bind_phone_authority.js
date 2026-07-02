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
    isLoggedIn: function () {
      return false;
    },
    setToken: function () {},
    clearToken: function () {},
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
    {
      path: path.join(repoRoot, "wx_miniprogram/pages/login/login.js"),
      normalHandler: "handleWechatLogin",
      explicitHandler: "handleWechatPhoneNumber",
    },
  ];

  await run("primary quick-login button must request phone authorization", async function () {
    var wxmlPaths = [
      "yousenwebview/packageDeeptutor/pages/login/login.wxml",
      "wx_miniprogram/pages/login/login.wxml",
    ];
    for (var i = 0; i < wxmlPaths.length; i++) {
      var loginWxml = fs.readFileSync(path.join(repoRoot, wxmlPaths[i]), "utf8");
      assert(
        loginWxml.indexOf("privacy-consent-row") >= 0,
        wxmlPaths[i] + " should show an explicit privacy consent row",
      );
      assert(
        loginWxml.indexOf("privacy-consent-row") >
          loginWxml.indexOf('class="btn-wechat-stack"'),
        wxmlPaths[i] + " should place privacy consent below the primary button to avoid hero text overlap",
      );
      assert(
        loginWxml.indexOf('bindtap="handlePrivacyRequiredTap"') >= 0,
        wxmlPaths[i] + " should block unchecked privacy consent before getPhoneNumber",
      );
      assert(
        loginWxml.indexOf('open-type="agreePrivacyAuthorization"') >= 0,
        wxmlPaths[i] + " privacy checkbox should use WeChat native privacy authorization",
      );
      assert(
        loginWxml.indexOf('bindagreeprivacyauthorization="handlePrivacyAgreementAuthorized"') >= 0,
        wxmlPaths[i] + " privacy checkbox should handle native agreement callback",
      );
      assert(
        loginWxml.indexOf('wx:if="{{privacyChecked}}"') >= 0,
        wxmlPaths[i] + " getPhoneNumber button should render only after privacy consent",
      );
      assert(
        loginWxml.indexOf('open-type="getPhoneNumber"') >= 0,
        wxmlPaths[i] + " primary quick-login button should use getPhoneNumber",
      );
      assert(
        loginWxml.indexOf('bindgetphonenumber="handleWechatPhoneNumber"') >= 0,
        wxmlPaths[i] + " primary quick-login button should bind handleWechatPhoneNumber",
      );
      assert(
        loginWxml.indexOf('bindtap="handleWechatLogin"') === -1,
        wxmlPaths[i] + " primary quick-login button must not call plain wx.login handler",
      );
    }
  });

  await run("privacy consent row should wrap instead of overlapping nearby copy", async function () {
    var wxssPaths = [
      "yousenwebview/packageDeeptutor/pages/login/login.wxss",
      "wx_miniprogram/pages/login/login.wxss",
    ];
    for (var i = 0; i < wxssPaths.length; i++) {
      var loginWxss = fs.readFileSync(path.join(repoRoot, wxssPaths[i]), "utf8");
      assert(
        loginWxss.indexOf("flex-wrap: wrap") >= 0,
        wxssPaths[i] + " should allow long privacy copy to wrap",
      );
      assert(
        loginWxss.indexOf("margin: 14rpx 0 0") >= 0,
        wxssPaths[i] + " should attach privacy copy below the primary button",
      );
      assert(
        loginWxss.indexOf(".privacy-consent-button::after") >= 0,
        wxssPaths[i] + " should remove the native button border from privacy checkbox",
      );
    }
  });

  await run("privacy consent controls should stay readable on the dark login background", async function () {
    var wxssPaths = [
      "yousenwebview/packageDeeptutor/pages/login/login.wxss",
      "wx_miniprogram/pages/login/login.wxss",
    ];
    for (var i = 0; i < wxssPaths.length; i++) {
      var loginWxss = fs.readFileSync(path.join(repoRoot, wxssPaths[i]), "utf8");
      assert(
        loginWxss.indexOf(".privacy-checkbox") >= 0,
        wxssPaths[i] + " should style the visible privacy checkbox",
      );
      assert(
        loginWxss.indexOf(".privacy-checkbox.checked") >= 0,
        wxssPaths[i] + " should style the checked privacy checkbox state",
      );
      assert(
        loginWxss.indexOf(".privacy-checkmark") >= 0,
        wxssPaths[i] + " should style the checkmark instead of inheriting default dark text",
      );
      assert(
        loginWxss.indexOf(".privacy-copy") >= 0 &&
          loginWxss.indexOf("rgba(226, 232, 240, 0.68)") >= 0,
        wxssPaths[i] + " should render privacy copy in a readable light color",
      );
      assert(
        loginWxss.indexOf(".privacy-link") >= 0 && loginWxss.indexOf("#8fc7ff") >= 0,
        wxssPaths[i] + " should render the privacy guide link in a visible accent color",
      );
    }
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
      page.setData({ privacyChecked: true });
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

  await run("login page should query privacy status without prompting on entry", async function () {
    var privacyRequests = 0;
    var privacySettingRequests = 0;
    var page = createSandbox(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      {
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
      },
      {
        getPrivacySetting: function (options) {
          privacySettingRequests++;
          options.success({
            needAuthorization: true,
            privacyContractName: "《鲁班智考用户隐私保护指引》",
          });
          if (options.complete) options.complete({});
        },
        requirePrivacyAuthorize: function (options) {
          privacyRequests++;
          options.success({});
          if (options.complete) options.complete({});
        },
      },
    );

    page.onLoad({});
    await flushPromises();

    assert(privacySettingRequests === 1, "login page should query privacy setting on entry");
    assert(privacyRequests === 0, "login page must not prompt privacy authorization on entry");
    assert(page.data.privacyChecked === false, "login page should keep privacy unchecked when authorization is needed");
    assert(
      page.data.privacyContractName === "《鲁班智考用户隐私保护指引》",
      "login page should show WeChat privacy contract name",
    );
  });

  await run("privacy checkbox should authorize privacy before enabling phone login", async function () {
    var privacyRequests = 0;
    var page = createSandbox(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      {
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
      },
      {
        requirePrivacyAuthorize: function (options) {
          privacyRequests++;
          options.success({});
          if (options.complete) options.complete({});
        },
      },
    );

    page.setData({ privacyChecked: false, privacyNeedAuthorization: true });
    page.handlePrivacyCheckboxTap();
    await flushPromises();

    assert(privacyRequests === 1, "privacy checkbox should call WeChat privacy authorization");
    assert(page.data.privacyChecked === true, "privacy checkbox should enable phone login after consent");
    assert(page.data.errorMsg === "", "privacy checkbox success should clear stale errors");
  });

  await run("native privacy agreement callback should enable phone login", async function () {
    var page = createSandbox(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      {
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
      },
      {},
    );

    page.setData({
      privacyChecked: false,
      privacyNeedAuthorization: true,
      errorMsg: "请先勾选同意用户隐私保护指引后继续",
    });
    page.handlePrivacyAgreementAuthorized({});

    assert(page.data.privacyChecked === true, "native privacy callback should check consent");
    assert(page.data.privacyNeedAuthorization === false, "native privacy callback should clear authorization need");
    assert(page.data.errorMsg === "", "native privacy callback should clear the blocking error");
  });

  await run("unchecked privacy consent should block quick login before getPhoneNumber", async function () {
    var page = createSandbox(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      {
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
      },
      {},
    );

    page.setData({ privacyChecked: false });
    page.handlePrivacyRequiredTap();

    assert(
      page.data.errorMsg.indexOf("勾选") >= 0,
      "unchecked quick login should tell users to check the privacy agreement first",
    );
  });

  await run("privacy gate interruption should not be reported as phone verification failure", async function () {
    var loginCalls = [];
    var privacyRequests = 0;
    var page = createSandbox(
      path.join(repoRoot, "yousenwebview/packageDeeptutor/pages/login/login.js"),
      {
        wxLoginWithPhone: function () {
          loginCalls.push(true);
          return Promise.resolve({ token: "token_1" });
        },
        describeRequestError: function (_err, fallback) {
          return fallback;
        },
        shouldRetryWechatLogin: function () {
          return false;
        },
      },
      {
        requirePrivacyAuthorize: function (options) {
          privacyRequests++;
          options.success({});
          if (options.complete) options.complete({});
        },
      },
    );

    page.handleWechatPhoneNumber({
      detail: { errMsg: "getPhoneNumber:fail privacy permission is not authorized" },
    });
    await flushPromises();
    await flushPromises();

    assert(loginCalls.length === 0, "privacy interruption must not call phone login backend");
    assert(privacyRequests === 0, "privacy interruption must not prompt privacy authorization after getPhoneNumber");
    assert(
      page.data.errorMsg.indexOf("未完成手机号验证") === -1,
      "privacy interruption should not be shown as phone verification failure",
    );
    assert(
      page.data.errorMsg.indexOf("勾选") >= 0,
      "privacy interruption should send users back to the explicit checkbox consent step",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_wechat_bind_phone_authority.js (" + pass + " assertions)");
})();
