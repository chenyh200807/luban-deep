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

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
}

function exists(relativePath) {
  return fs.existsSync(path.join(__dirname, "..", relativePath));
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

function createRouteMock() {
  return {
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
    },
    login: function () {
      return "/packageDeeptutor/pages/login/login";
    },
    manualLogin: function (query) {
      var suffix = query && query.loginMode ? "?loginMode=" + query.loginMode : "";
      return "/packageDeeptutor/pages/login/manual" + suffix;
    },
    resolveInternalUrl: function (_value, fallback) {
      return fallback;
    },
  };
}

function loadPage(relativePath, options) {
  var source = read(relativePath);
  var pageDef = null;
  var requests = [];
  var modalCalls = [];
  var redirectCalls = [];
  var toastCalls = [];
  var apiMock = Object.assign(
    {
      request: function (requestOptions) {
        requests.push(requestOptions);
        if (requestOptions.url === "/api/v1/auth/send-code") {
          return Promise.resolve({
            sent: true,
            retry_after: 60,
            message: "验证码发送成功",
          });
        }
        if (requestOptions.url === "/api/v1/auth/reset-password") {
          return Promise.resolve({
            success: true,
            message: "密码已重置，请使用新密码登录",
          });
        }
        return Promise.reject(new Error("unexpected request: " + requestOptions.url));
      },
      describeRequestError: function (_err, fallbackMsg) {
        return fallbackMsg;
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
      if (request === "../../utils/auth") return { isLoggedIn: function () { return false; } };
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, screenHeight: 812, safeArea: { bottom: 778 } };
          },
        };
      }
      if (request === "../../utils/route") return createRouteMock();
      if (request === "../../utils/analytics") return { track: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function (opts) {
        toastCalls.push(opts || {});
      },
      showModal: function (opts) {
        modalCalls.push(opts || {});
      },
      redirectTo: function (opts) {
        redirectCalls.push(opts || {});
      },
      navigateBack: function (opts) {
        if (opts && typeof opts.fail === "function") opts.fail();
      },
      reLaunch: function (opts) {
        redirectCalls.push(opts || {});
      },
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
    requests: requests,
    modalCalls: modalCalls,
    redirectCalls: redirectCalls,
    toastCalls: toastCalls,
  };
}

(async function main() {
  await run("password reset page is registered in the Deeptutor subpackage", function () {
    var appConfig = JSON.parse(read("app.json"));
    var packagePages = appConfig.subpackages[0].pages;
    assert(
      exists("packageDeeptutor/pages/login/reset-password.js"),
      "reset password page script should exist",
    );
    assert(
      packagePages.indexOf("pages/login/reset-password") >= 0,
      "app.json should register packageDeeptutor/pages/login/reset-password",
    );
  });

  await run("route helper owns the password reset path", function () {
    var routePath = path.join(__dirname, "../packageDeeptutor/utils/route.js");
    delete require.cache[require.resolve(routePath)];
    var route = require(routePath);
    assert(
      typeof route.passwordReset === "function",
      "route.passwordReset helper should exist",
    );
    assert(
      route.passwordReset({ entrySource: "bridge" }) ===
        "/packageDeeptutor/pages/login/reset-password?entrySource=bridge",
      "route.passwordReset should build a Deeptutor package URL",
    );
    assert(
      route.resolveInternalUrl(
        "/packageDeeptutor/pages/login/reset-password?entrySource=bridge",
        "/packageDeeptutor/pages/chat/chat",
      ) === "/packageDeeptutor/pages/login/reset-password?entrySource=bridge",
      "route resolver should allow reset password return targets",
    );
  });

  await run("login surfaces expose a direct forgot password action", function () {
    assert(
      read("packageDeeptutor/pages/login/login.wxml").indexOf("goPasswordReset") >= 0,
      "primary login should expose forgot password navigation",
    );
    assert(
      read("packageDeeptutor/pages/login/manual.wxml").indexOf("goPasswordReset") >= 0,
      "manual login should expose forgot password navigation",
    );
  });

  await run("password reset page validates password strength before requesting reset", async function () {
    if (!exists("packageDeeptutor/pages/login/reset-password.js")) {
      assert(false, "reset password page script should exist before behavior can be tested");
      return;
    }
    var setup = loadPage("packageDeeptutor/pages/login/reset-password.js");
    setup.page.setData({
      username: "reset_student",
      phone: "13955556666",
      phoneCode: "123456",
      password: "abc123",
      confirmPassword: "abc123",
    });
    setup.page.handleResetPassword();
    await flushPromises();

    assert(setup.requests.length === 0, "weak reset password should not call backend");
    assert(
      setup.page.data.errorMsg === "密码需包含大写字母、小写字母和数字",
      "weak reset password should use the same strength bar as registration",
    );
  });

  await run("password reset page sends SMS code and resets without auto-login", async function () {
    if (!exists("packageDeeptutor/pages/login/reset-password.js")) {
      assert(false, "reset password page script should exist before behavior can be tested");
      return;
    }
    var setup = loadPage("packageDeeptutor/pages/login/reset-password.js");
    setup.page.setData({
      username: "reset_student",
      phone: "13955556666",
      phoneCode: "123456",
      password: "NewPass123",
      confirmPassword: "NewPass123",
    });

    setup.page.sendCode();
    await flushPromises();
    setup.page.handleResetPassword();
    await flushPromises();

    assert(
      setup.requests[0].url === "/api/v1/auth/send-code",
      "reset page should request SMS code through the auth code authority",
    );
    assert(
      setup.requests[0].data.username === "reset_student" &&
        setup.requests[0].data.phone === "13955556666",
      "reset page should bind SMS code request to username and registered phone",
    );
    assert(
      setup.requests[1].url === "/api/v1/auth/reset-password",
      "reset page should call the dedicated password reset endpoint",
    );
    assert(
      setup.requests[1].data.username === "reset_student" &&
        setup.requests[1].data.phone === "13955556666" &&
        setup.requests[1].data.code === "123456" &&
        setup.requests[1].data.password === "NewPass123",
      "reset endpoint payload should include username, phone, code, and new password",
    );
    assert(
      setup.modalCalls.length === 1 &&
        setup.modalCalls[0].title === "密码已重置",
      "reset success should show a confirmation modal",
    );
    assert(
      setup.redirectCalls.length === 0,
      "reset success should not auto-login before the user confirms",
    );

    setup.modalCalls[0].success({ confirm: true });
    assert(
      setup.redirectCalls.length === 1 &&
        setup.redirectCalls[0].url.indexOf("/packageDeeptutor/pages/login/manual?loginMode=password") === 0,
      "after confirmation reset page should return to password login mode",
    );
  });

  await run("password reset page preserves safe backend reset error semantics", async function () {
    var cases = [
      ["账号或手机号不匹配", "账号和手机号不匹配，请确认注册账号和绑定手机号"],
      ["验证码不存在，请先获取验证码", "请先获取验证码"],
      ["验证码已过期，请重新获取", "验证码已过期，请重新获取"],
      ["验证码错误次数过多，请重新获取验证码", "验证码错误次数过多，请重新获取验证码"],
      ["验证码错误", "验证码错误，请重新输入"],
      ["其他填写错误", "信息填写有误，请检查后重试"],
    ];
    for (var i = 0; i < cases.length; i++) {
      var setup = loadPage("packageDeeptutor/pages/login/reset-password.js", {
        api: {
          describeRequestError: describeRequestErrorForTest,
          request: function (requestOptions) {
            if (requestOptions.url === "/api/v1/auth/reset-password") {
              return Promise.reject(httpError(400, cases[i][0]));
            }
            return Promise.resolve({ sent: true, retry_after: 60 });
          },
        },
      });
      setup.page.setData({
        username: "reset_student",
        phone: "13955556666",
        phoneCode: "123456",
        password: "NewPass123",
        confirmPassword: "NewPass123",
      });

      setup.page.handleResetPassword();
      await flushPromises();
      await flushPromises();

      assert(
        setup.page.data.errorMsg === cases[i][1],
        "reset error '" + cases[i][0] + "' should map to '" + cases[i][1] + "'",
      );
    }
  });

  await run("password reset send-code preserves account phone mismatch semantics", async function () {
    var setup = loadPage("packageDeeptutor/pages/login/reset-password.js", {
      api: {
        describeRequestError: describeRequestErrorForTest,
        request: function (requestOptions) {
          if (requestOptions.url === "/api/v1/auth/send-code") {
            return Promise.reject(httpError(400, "账号或手机号不匹配"));
          }
          return Promise.reject(new Error("unexpected request"));
        },
      },
    });
    setup.page.setData({
      username: "reset_student",
      phone: "13955556666",
    });

    setup.page.sendCode();
    await flushPromises();

    assert(
      setup.page.data.errorMsg === "账号和手机号不匹配，请确认注册账号和绑定手机号",
      "send-code account phone mismatch should be visible before reset submit",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_password_reset_flow.js (" + pass + " assertions)");
})();
