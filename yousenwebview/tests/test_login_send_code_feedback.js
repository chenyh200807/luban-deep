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

function loadPage(relativePath) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef = null;
  var toastCalls = [];
  var apiMock = {
    request: function () {
      return Promise.resolve({
        sent: true,
        retry_after: 60,
        phone: "18688888431",
        delivery: "sms",
        message: "验证码发送成功",
      });
    },
  };
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
      throw new Error("unexpected require: " + request);
    },
    wx: {
      showToast: function (options) {
        toastCalls.push(options || {});
      },
      showModal: function () {},
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

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_login_send_code_feedback.js (" + pass + " assertions)");
})();
