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

function loadAppDefinition() {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var reLaunchCalls = [];
  var navigateCalls = [];
  var appDef = null;
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "./utils/request") {
        return { getrq: function () { return Promise.resolve({}); } };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function () {
        return "";
      },
      setStorageSync: function () {},
      removeStorageSync: function () {},
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

run("openDeeptutorLogin suppresses repeated navigateTo during active lock", function () {
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
  assert(loaded.navigateCalls.length === 1, "deeptutor flow should only issue one navigateTo call");
  assert(
    loaded.navigateCalls[0] &&
      loaded.navigateCalls[0].url.indexOf("/pages/deeptutorEntry/deeptutorEntry?entrySource=") === 0,
    "deeptutor flow should target the main-package bridge url",
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

run("deeptutor bridge should fallback to reLaunch when navigateTo fails", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.navigateTo = function (options) {
    loaded.navigateCalls.push(options);
    if (options && typeof options.fail === "function") {
      options.fail(new Error("mock navigateTo failure"));
    }
  };

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
    "deeptutor login should still start even if bridge navigateTo later fails",
  );
  assert(loaded.navigateCalls.length === 1, "bridge navigateTo should be attempted first");
  assert(loaded.reLaunchCalls.length === 1, "bridge reLaunch fallback should be attempted once");
  assert(failCount === 0, "successful bridge fallback should not trigger final failure callback");
});

run("deeptutor bridge should release lock if fallback reLaunch also fails", function () {
  var loaded = loadAppDefinition();
  loaded.app._resetCrossHomeNavigationLock();
  var failCount = 0;

  loaded.wx.navigateTo = function (options) {
    loaded.navigateCalls.push(options);
    if (options && typeof options.fail === "function") {
      options.fail(new Error("mock navigateTo failure"));
    }
  };

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
    "deeptutor bridge should attempt fallback flow",
  );
  assert(loaded.reLaunchCalls.length === 1, "bridge reLaunch fallback should still run");
  assert(
    loaded.app.isCrossHomeNavigationLocked() === false,
    "lock should be released after bridge fallback failure",
  );
  assert(failCount === 1, "final failure callback should run exactly once");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_cross_home_navigation.js (" + pass + " assertions)");
