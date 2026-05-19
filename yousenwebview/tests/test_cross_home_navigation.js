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

run("openDeeptutorLogin loads subpackage and suppresses repeated direct route during active lock", function () {
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
  assert(loaded.loadSubpackageCalls.length === 1, "deeptutor flow should only load the subpackage once");
  assert(
    loaded.loadSubpackageCalls[0] && loaded.loadSubpackageCalls[0].name === "packageDeeptutor",
    "deeptutor flow should load the packageDeeptutor subpackage",
  );
  assert(loaded.navigateCalls.length === 0, "deeptutor flow should not keep the host page stack");
  assert(loaded.reLaunchCalls.length === 1, "deeptutor flow should replace the host page stack once");
  assert(
    loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url.indexOf("/packageDeeptutor/pages/login/login?entrySource=") === 0,
    "unauthenticated deeptutor flow should target the package login url directly",
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
      loaded.reLaunchCalls[0].url ===
        "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
    "authenticated flow should enter the package returnTo url directly",
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
      loaded.reLaunchCalls[0].url.indexOf("/packageDeeptutor/pages/login/login?entrySource=") === 0,
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

run("deeptutor direct route should reLaunch after subpackage load", function () {
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
    "deeptutor login should start after subpackage load",
  );
  assert(loaded.loadSubpackageCalls.length === 1, "subpackage load should be attempted first");
  assert(loaded.navigateCalls.length === 0, "direct navigateTo should not be used for cross-surface entry");
  assert(loaded.reLaunchCalls.length === 1, "direct reLaunch should be attempted once");
  assert(failCount === 0, "successful direct reLaunch should not trigger final failure callback");
});

run("deeptutor direct route should release lock if reLaunch fails", function () {
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
    "deeptutor direct route should attempt reLaunch flow",
  );
  assert(loaded.navigateCalls.length === 0, "direct navigateTo should not run");
  assert(loaded.reLaunchCalls.length === 1, "direct reLaunch should still run");
  assert(
    loaded.app.isCrossHomeNavigationLocked() === false,
    "lock should be released after direct fallback failure",
  );
  assert(failCount === 1, "final failure callback should run exactly once");
});

run("deeptutor direct route should release lock when subpackage load fails", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.loadSubpackage = function (options) {
    loaded.loadSubpackageCalls.push(options);
    if (options && typeof options.fail === "function") {
      options.fail(new Error("mock loadSubpackage failure"));
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
    "deeptutor direct route should attempt subpackage load",
  );
  assert(loaded.navigateCalls.length === 0, "route should not navigate before subpackage load succeeds");
  assert(
    loaded.app.isCrossHomeNavigationLocked() === false,
    "lock should be released after subpackage load failure",
  );
  assert(failCount === 1, "subpackage load failure should run final failure callback once");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_cross_home_navigation.js (" + pass + " assertions)");
