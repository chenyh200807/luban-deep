// test_cross_home_navigation.js — regression checks for cross-home nav guard
// Run: /Applications/Codex.app/Contents/Resources/node yousenwebview/tests/test_cross_home_navigation.js

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

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function loadAppDefinition(storage) {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var reLaunchCalls = [];
  var navigateCalls = [];
  var loadSubpackageCalls = [];
  var appDef = null;
  var store = storage || {};
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "./api/baseApi") {
        return { GetSysInfo: "Action=GetSysInfo" };
      }
      if (request === "./utils/config") {
        return { baseUrl: "https://xytk.kailly.com/Api/Xytk.ashx?" };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return store[key] || "";
      },
      setStorageSync: function () {},
      removeStorageSync: function () {},
      request: function (options) {
        if (options && typeof options.success === "function") {
          options.success({ data: { status: 1, data: {} } });
        }
      },
      nextTick: function (task) {
        if (typeof task === "function") task();
      },
      loadSubpackage: function (options) {
        loadSubpackageCalls.push(options);
        if (options && typeof options.success === "function") {
          options.success({});
        }
      },
      reLaunch: function (options) {
        reLaunchCalls.push(options);
      },
      redirectTo: function (options) {
        navigateCalls.push(options);
      },
      navigateTo: function (options) {
        navigateCalls.push(options);
      },
    },
    App: function (def) {
      appDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: "app.js" });

  return {
    app: appDef,
    wx: sandbox.wx,
    reLaunchCalls: reLaunchCalls,
    navigateCalls: navigateCalls,
    loadSubpackageCalls: loadSubpackageCalls,
  };
}

run("goHostHome suppresses repeated reLaunch during active lock", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();

  assert(loaded.app.goHostHome({}) === true, "first host-home navigation should start");
  assert(loaded.app.goHostHome({}) === false, "second host-home navigation should be ignored while locked");
  assert(loaded.reLaunchCalls.length === 1, "host-home flow should only issue one reLaunch call");
  assert(
    loaded.reLaunchCalls[0] && loaded.reLaunchCalls[0].url === "/pages/freeCourse/freeCourse",
    "host-home flow should target the freeCourse host home directly",
  );
});

run("openDeeptutorLogin routes through host bridge and suppresses repeated entry during active lock", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();

  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {},
    ) === true,
    "first deeptutor navigation should start",
  );
  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {},
    ) === false,
    "second deeptutor navigation should be ignored while locked",
  );
  assert(
    loaded.loadSubpackageCalls.length === 0,
    "app-level deeptutor flow should leave subpackage loading to the host bridge",
  );
  assert(loaded.navigateCalls.length === 0, "deeptutor flow should not keep the host page stack");
  assert(loaded.reLaunchCalls.length === 1, "deeptutor flow should replace the host page stack once");
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("/pages/deeptutorEntry/deeptutorEntry?entrySource=") === 0,
    "unauthenticated deeptutor flow should target the host bridge first",
  );
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("&authenticated=0") > 0,
    "unauthenticated deeptutor bridge URL should preserve login intent",
  );
});

run("openDeeptutorLogin routes to returnTo when token is locally valid", function () {
  var loaded = loadAppDefinition({
    auth_token: "token",
    auth_token_exp: Math.floor(Date.now() / 1000) + 3600,
  });
  loaded.app._resetCrossHomeNavigationLock();

  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {},
    ) === true,
    "authenticated deeptutor navigation should start",
  );
  assert(loaded.navigateCalls.length === 0, "authenticated flow should not keep the host page stack");
  assert(loaded.reLaunchCalls.length === 1, "authenticated flow should issue one reLaunch call");
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("/pages/deeptutorEntry/deeptutorEntry?entrySource=") === 0,
    "authenticated flow should enter the host bridge first",
  );
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("&authenticated=1") > 0,
    "authenticated bridge URL should preserve authenticated intent",
  );
});

run("openDeeptutorLogin sends expired token users to login", function () {
  var loaded = loadAppDefinition({
    auth_token: "token",
    auth_token_exp: Math.floor(Date.now() / 1000) - 1,
  });
  loaded.app._resetCrossHomeNavigationLock();

  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {},
    ) === true,
    "expired deeptutor navigation should still start",
  );
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("/pages/deeptutorEntry/deeptutorEntry?entrySource=") === 0 &&
      loaded.reLaunchCalls[0].url.indexOf("&authenticated=0") > 0,
    "expired token should not skip the login gate",
  );
});

run("navigation failure should release lock for immediate retry", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.reLaunch = function (options) {
    loaded.reLaunchCalls.push(options);
    if (options && typeof options.fail === "function") {
      options.fail(new Error("mock failure"));
    }
  };

  assert(
    loaded.app.goHostHome({
      onFail: function () {
        failCount++;
      },
    }) === true,
    "failing host-home navigation should still attempt the first jump",
  );
  assert(
    loaded.app.isCrossHomeNavigationLocked() === false,
    "lock should be released immediately after navigation failure",
  );
  assert(failCount === 1, "failure callback should run exactly once");
  assert(
    loaded.app.goHostHome({}) === true,
    "host-home navigation should be retryable right after a failure",
  );
});

run("deeptutor entry should reLaunch to host bridge", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.reLaunch = function (options) {
    loaded.reLaunchCalls.push(options);
  };

  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {
        onFail: function () {
          failCount++;
        },
      },
    ) === true,
    "deeptutor login should start through the bridge",
  );
  assert(loaded.loadSubpackageCalls.length === 0, "app-level entry should not load subpackage directly");
  assert(loaded.navigateCalls.length === 0, "direct navigateTo should not be used for cross-surface entry");
  assert(loaded.reLaunchCalls.length === 1, "bridge reLaunch should be attempted once");
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("/pages/deeptutorEntry/deeptutorEntry?entrySource=") === 0,
    "deeptutor entry should target the host bridge URL",
  );
  assert(failCount === 0, "successful bridge reLaunch should not trigger final failure callback");
});

run("deeptutor entry should release lock if bridge reLaunch fails", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.reLaunch = function (options) {
    loaded.reLaunchCalls.push(options);
    if (options && typeof options.fail === "function") {
      options.fail(new Error("mock reLaunch failure"));
    }
  };

  assert(
    loaded.app.openDeeptutorLogin(
      "free_course_inline_entry",
      "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      {
        onFail: function () {
          failCount++;
        },
      },
    ) === true,
    "deeptutor bridge route should attempt reLaunch flow",
  );
  assert(loaded.navigateCalls.length === 0, "direct navigateTo should not run");
  assert(loaded.reLaunchCalls.length === 1, "bridge reLaunch should still run");
  assert(
    loaded.app.isCrossHomeNavigationLocked() === false,
    "lock should be released after bridge launch failure",
  );
  assert(failCount === 1, "final failure callback should run exactly once");
});

run("logout should redirect to package login before relaunch fallback", function () {
  var loaded = loadAppDefinition({ token: "mock-token" });
  loaded.wx.redirectTo = function (options) {
    loaded.navigateCalls.push(options);
    if (options && typeof options.complete === "function") {
      options.complete();
    }
  };
  loaded.wx.reLaunch = function (options) {
    loaded.reLaunchCalls.push(options);
  };

  loaded.app.logout();

  assert(loaded.navigateCalls.length === 1, "logout should try package login redirect first");
  assert(
    loaded.navigateCalls[0] &&
      loaded.navigateCalls[0].url === "/packageDeeptutor/pages/login/login",
    "logout should target package login",
  );
  assert(loaded.reLaunchCalls.length === 0, "logout should not relaunch when redirect succeeds");
  assert(loaded.app.globalData._authRedirecting === false, "logout should release auth redirect flag");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_cross_home_navigation.js (" + pass + " assertions)");
