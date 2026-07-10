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

function createRouteMock() {
  return {
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
    },
    login: function () {
      return "/packageDeeptutor/pages/login/login";
    },
    resolveInternalUrl: function (_value, fallback) {
      return fallback;
    },
  };
}

function loadPage(options) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/register/register.js"),
    "utf8",
  );
  var pageDef = null;
  var requests = [];
  var apiMock = Object.assign(
    {
      request: function (requestOptions) {
        requests.push(requestOptions);
        return Promise.resolve({
          token: "token_1",
          expires_at: 1800000000,
          user: { user_id: "user_1" },
        });
      },
      describeRequestError: describeRequestErrorForTest,
      regAttribution: function () {
        return { channel: "", scene: "" };
      },
    },
    (options && options.api) || {},
  );
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () { return false; },
          setToken: function () {},
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, screenHeight: 812, safeArea: { bottom: 778 } };
          },
          isDark: function () { return true; },
        };
      }
      if (request === "../../utils/route") return createRouteMock();
      if (request === "../../utils/analytics") return { track: function () {} };
      if (request === "../../utils/first-run-entry")
        return { reLaunchAfterAuth: function (target) { sandbox.wx.reLaunch({ url: target }); } };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      reLaunch: function () {},
      navigateBack: function () {},
      showToast: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: "register.js" });

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
  return { page: page, requests: requests };
}

(async function main() {
  await run("register page preserves safe backend registration error semantics", async function () {
    var cases = [
      ["用户名已存在", "该账号已存在，请直接登录"],
      ["该手机号已被注册，请直接登录或找回密码", "该手机号已注册，请直接登录或找回密码"],
      ["该手机号已被注册，请更换手机号或直接登录。", "该手机号已注册，请直接登录或找回密码"],
      ["手机号身份冲突，请联系客服", "手机号身份存在冲突，请联系客服"],
      ["手机号格式不正确", "请输入正确的手机号"],
      ["其他错误", "注册信息填写有误，请检查后重试"],
    ];
    for (var i = 0; i < cases.length; i++) {
      var setup = loadPage({
        api: {
          request: function () {
            return Promise.reject(httpError(400, cases[i][0]));
          },
        },
      });
      setup.page.setData({
        username: "new_student",
        phone: "13812345678",
        password: "StrongPass123", // pragma: allowlist secret
        confirmPassword: "StrongPass123", // pragma: allowlist secret
      });

      setup.page.handleRegister();
      await flushPromises();
      await flushPromises();

      assert(
        setup.page.data.errorMsg === cases[i][1],
        "register error '" + cases[i][0] + "' should map to '" + cases[i][1] + "'",
      );
    }
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_register_flow.js (" + pass + " assertions)");
})();
