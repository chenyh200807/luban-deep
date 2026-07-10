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

function httpError(status, detail) {
  var err = new Error("HTTP_" + status + ": " + JSON.stringify({ detail: detail }));
  err.statusCode = status;
  err.payload = { detail: detail };
  return err;
}

function describeRequestErrorForTest(err, fallbackMsg, opts) {
  var status = err && err.statusCode ? err.statusCode : 0;
  var detailText = err && err.payload ? String(err.payload.detail || "") : "";
  var customMap = opts && opts.customMap;
  if (typeof customMap === "function") {
    var customMsg = customMap({
      status: status,
      detailText: detailText,
      payload: err && err.payload,
      rawMessage: String((err && err.message) || ""),
    });
    if (customMsg) return customMsg;
  }
  return fallbackMsg;
}

function loadPage(relativePath, overrides) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef = null;
  var toastCalls = [];
  var modalCalls = [];
  var apiMock = Object.assign(
    {
      request: function () {
        return Promise.resolve({
          sent: true,
          retry_after: 60,
          phone: "18688888431",
          delivery: "sms",
          message: "验证码发送成功",
        });
      },
      describeRequestError: describeRequestErrorForTest,
    },
    (overrides && overrides.api) || {},
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
      if (request === "../../utils/auth") return { isLoggedIn: function () { return false; } };
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, screenHeight: 812, safeArea: { bottom: 778 } };
          },
          isDark: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
          resolveInternalUrl: function (_value, fallback) {
            return fallback;
          },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      if (request === "../../utils/surface-telemetry")
        return { trackProductBehavior: function () {} };
      if (request === "../../utils/flags")
        return { resolvePostAuthLanding: function (t) { return t; }, shouldLandOnDoubleWheel: function () { return false; } };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function (options) {
        toastCalls.push(options || {});
      },
      showModal: function (options) {
        modalCalls.push(options || {});
      },
      navigateTo: function () {},
      reLaunch: function () {},
    },
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
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    toastCalls: toastCalls,
    modalCalls: modalCalls,
  };
}

(async function main() {
  var pageFiles = [
    "packageDeeptutor/pages/login/login.js",
    "packageDeeptutor/pages/login/manual.js",
  ];

  await run("sms send success should show immediate success feedback", async function () {
    for (var i = 0; i < pageFiles.length; i++) {
      var setup = loadPage(pageFiles[i]);
      setup.page.setData({ username: "18688888431" });
      setup.page.sendCode();
      await flushPromises();
      assert(
        setup.toastCalls.length === 1,
        pageFiles[i] + " should show a success toast after sms send accepted",
      );
      assert(
        setup.toastCalls[0] && setup.toastCalls[0].title === "验证码发送成功",
        pageFiles[i] + " should surface sms success message immediately",
      );
    }
  });

  await run("release login pages should not expose backend debug sms code", async function () {
    for (var i = 0; i < pageFiles.length; i++) {
      var setup = loadPage(pageFiles[i], {
        api: {
          request: function () {
            return Promise.resolve({
              sent: true,
              retry_after: 60,
              message: "验证码发送成功",
              debug_code: "246810",
            });
          },
        },
      });
      setup.page.setData({ username: "18688888431" });
      setup.page.sendCode();
      await flushPromises();
      assert(
        setup.page.data.phoneCode === "",
        pageFiles[i] + " should not auto-fill backend debug_code in release",
      );
      assert(
        setup.modalCalls.length === 0,
        pageFiles[i] + " should not show backend debug_code modal in release",
      );
      assert(
        setup.toastCalls.length === 1 &&
          setup.toastCalls[0].title === "验证码发送成功",
        pageFiles[i] + " should keep normal sms feedback without exposing debug_code",
      );
    }
  });

  await run("phone-code login should preserve identity conflict errors", async function () {
    for (var i = 0; i < pageFiles.length; i++) {
      var setup = loadPage(pageFiles[i], {
        api: {
          request: function (requestOptions) {
            if (requestOptions.url === "/api/v1/auth/verify-code") {
              return Promise.reject(httpError(400, "手机号身份冲突，请联系客服"));
            }
            return Promise.resolve({ sent: true, retry_after: 60 });
          },
        },
      });
      setup.page.setData({ username: "18688888431", phoneCode: "123456" });

      setup.page.verifyCode();
      await flushPromises();
      await flushPromises();

      assert(
        setup.page.data.errorMsg === "手机号身份存在冲突，请联系客服",
        pageFiles[i] + " should not describe identity conflicts as OTP mistakes",
      );
    }
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_login_send_code_feedback.js (" + pass + " assertions)");
})();
