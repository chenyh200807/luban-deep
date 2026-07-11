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

function loadPage(relativePath, overrides) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef = null;
  var clearCount = 0;
  var switchTabCalls = [];
  var apiMock = Object.assign(
    {
      getUserInfo: function () {
        return Promise.reject(new Error("profile unavailable"));
      },
    },
    (overrides && overrides.api) || {},
  );
  var authMock = Object.assign(
    {
      isLoggedIn: function () {
        return true;
      },
      clearToken: function () {
        clearCount++;
      },
    },
    (overrides && overrides.auth) || {},
  );
  var helpersMock = {
    getWindowInfo: function () {
      return {
        statusBarHeight: 20,
        screenHeight: 812,
        safeArea: { bottom: 778 },
      };
    },
    isDark: function () {
      return true;
    },
  };
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/api") return apiMock;
      if (request === "../../utils/auth") return authMock;
      if (request === "../../utils/helpers") return helpersMock;
      if (request === "../../utils/surface-telemetry") {
        return {
          track: function () {},
          trackOnce: function () {},
          trackProductBehavior: function () {},
        };
      }
      if (request === "../../utils/first-run-entry") {
        return {
          goHomeAfterAuth: function () {
            sandbox.wx.switchTab({ url: "/pages/chat/chat" });
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      reLaunch: function () {},
      switchTab: function (options) {
        switchTabCalls.push(options);
      },
      navigateTo: function () {},
      showModal: function () {},
      showToast: function () {},
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
    getClearCount: function () {
      return clearCount;
    },
    switchTabCalls: switchTabCalls,
  };
}

(async function main() {
  var bootstrapPages = ["pages/login/manual.js", "pages/register/register.js"];

  await run("manual/register pages with local token should skip visible profile gate", async function () {
    for (var i = 0; i < bootstrapPages.length; i++) {
      var profileCalls = 0;
      var setup = loadPage(bootstrapPages[i], {
        api: {
          getUserInfo: function () {
            profileCalls++;
            return Promise.reject(new Error("profile unavailable"));
          },
        },
      });
      setup.page.onLoad({});
      await flushPromises();
      assert(profileCalls === 0, bootstrapPages[i] + " should not block redirect on profile bootstrap");
      assert(
        setup.getClearCount() === 0,
        bootstrapPages[i] + " should leave token cleanup to the target page",
      );
      assert(
        setup.switchTabCalls.length === 1 &&
          setup.switchTabCalls[0].url === "/pages/chat/chat",
        bootstrapPages[i] + " should enter chat immediately when a local token exists",
      );
    }
  });

  await run("manual/register pages without a valid token should stay on auth form", async function () {
    for (var i = 0; i < bootstrapPages.length; i++) {
      var setup = loadPage(bootstrapPages[i], {
        auth: {
          isLoggedIn: function () {
            return false;
          },
        },
      });
      setup.page.onLoad({});
      await flushPromises();
      assert(setup.getClearCount() === 0, bootstrapPages[i] + " should not clear token without one");
      assert(setup.switchTabCalls.length === 0, bootstrapPages[i] + " should stay visible for login");
    }
  });

  await run("login page with local token and phone should enter chat", async function () {
    var profileCalls = 0;
    var setup = loadPage("pages/login/login.js", {
      api: {
        getUserInfo: function () {
          profileCalls++;
          return Promise.resolve({ username: "chenyh2008", phone: "18688888431" });
        },
      },
    });
    setup.page.onLoad({});
    await flushPromises();
    assert(profileCalls === 1, "login page should verify phone binding before redirect");
    assert(setup.getClearCount() === 0, "login page should leave token cleanup to the target page");
    assert(
      setup.switchTabCalls.length === 1 &&
        setup.switchTabCalls[0].url === "/pages/chat/chat",
      "login page should enter chat when a local token has bound phone",
    );
  });

  await run("login page with local token but no phone should stay in bind-phone mode", async function () {
    var setup = loadPage("pages/login/login.js", {
      api: {
        getUserInfo: function () {
          return Promise.resolve({ username: "chenyh2008", phone: "" });
        },
      },
    });
    setup.page.onLoad({});
    await flushPromises();
    assert(setup.getClearCount() === 0, "login page should keep token while asking for phone binding");
    assert(setup.switchTabCalls.length === 0, "login page should not enter chat before phone binding");
    assert(setup.page.data.loginMode === "bind_phone_only", "login page should show bind-phone-only mode");
  });

  await run("login page should clear expired local token", async function () {
    var setup = loadPage("pages/login/login.js", {
      api: {
        getUserInfo: function () {
          return Promise.reject(new Error("AUTH_EXPIRED"));
        },
      },
    });
    setup.page.onLoad({});
    await flushPromises();
    assert(setup.getClearCount() === 1, "login page should clear expired token after profile check fails");
    assert(setup.switchTabCalls.length === 0, "login page should remain visible after token expiry");
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_login_token_preserve.js (" + pass + " assertions)");
})();
