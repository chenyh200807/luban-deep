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
      throw new Error("unexpected require: " + request);
    },
    wx: {
      reLaunch: function () {},
      switchTab: function () {},
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
  };
}

(async function main() {
  var pageFiles = [
    "pages/login/login.js",
    "pages/login/manual.js",
    "pages/register/register.js",
  ];

  await run("non-auth bootstrap failure should not clear token", async function () {
    for (var i = 0; i < pageFiles.length; i++) {
      var setup = loadPage(pageFiles[i], {
        api: {
          getUserInfo: function () {
            return Promise.reject(new Error("profile unavailable"));
          },
        },
      });
      setup.page.onLoad({});
      await flushPromises();
      assert(
        setup.getClearCount() === 0,
        pageFiles[i] + " should preserve token on non-auth bootstrap failure",
      );
    }
  });

  await run("auth expired bootstrap failure should clear token", async function () {
    for (var i = 0; i < pageFiles.length; i++) {
      var setup = loadPage(pageFiles[i], {
        api: {
          getUserInfo: function () {
            return Promise.reject(new Error("AUTH_EXPIRED"));
          },
        },
      });
      setup.page.onLoad({});
      await flushPromises();
      assert(
        setup.getClearCount() === 1,
        pageFiles[i] + " should clear token only when auth really expired",
      );
    }
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_login_token_preserve.js (" + pass + " assertions)");
})();
