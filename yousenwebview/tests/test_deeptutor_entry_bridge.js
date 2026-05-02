// test_deeptutor_entry_bridge.js — regression checks for deeptutor host bridge
// Run: /Applications/Codex.app/Contents/Resources/node yousenwebview/tests/test_deeptutor_entry_bridge.js

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
    var result = fn();
    if (result && typeof result.then === "function") {
      return result.catch(function (err) {
        fail++;
        errors.push(
          "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
        );
      });
    }
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
  return Promise.resolve();
}

function waitForTick() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 20);
  });
}

function loadBridgePage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/deeptutorEntry/deeptutorEntry.js"),
    "utf8",
  );
  var redirectCalls = [];
  var reLaunchCalls = [];
  var loadSubpackageCalls = [];
  var pageDef = null;
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    wx: {
      redirectTo: function (options) {
        redirectCalls.push(options);
      },
      reLaunch: function (options) {
        reLaunchCalls.push(options);
      },
      loadSubpackage: function (options) {
        loadSubpackageCalls.push(options);
        if (options && typeof options.success === "function") {
          options.success();
        }
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "pages/deeptutorEntry/deeptutorEntry.js",
  });

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
    wx: sandbox.wx,
    redirectCalls: redirectCalls,
    reLaunchCalls: reLaunchCalls,
    loadSubpackageCalls: loadSubpackageCalls,
  };
}

var tests = [];

tests.push(function () {
  return run("bridge loads subpackage before redirecting to login when unauthenticated", async function () {
    var setup = loadBridgePage();

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
    });
    setup.page.onReady();
    await waitForTick();

    assert(setup.loadSubpackageCalls.length === 1, "bridge should load the deeptutor subpackage once");
    assert(setup.redirectCalls.length === 1, "bridge should redirect to deeptutor login after subpackage load");
    assert(
      setup.redirectCalls[0] &&
        setup.redirectCalls[0].url.indexOf("/packageDeeptutor/pages/login/login?entrySource=") === 0,
      "bridge should target deeptutor login page",
    );
  });
});

tests.push(function () {
  return run("bridge redirects authenticated users directly to returnTo", async function () {
    var setup = loadBridgePage();

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      authenticated: "1",
    });
    setup.page.onReady();
    await waitForTick();

    assert(setup.loadSubpackageCalls.length === 1, "bridge should still load the deeptutor subpackage first");
    assert(setup.redirectCalls.length === 1, "bridge should redirect after subpackage load");
    assert(
      setup.redirectCalls[0] &&
        setup.redirectCalls[0].url ===
          "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
      "authenticated bridge should skip visible login page and target returnTo",
    );
  });
});

tests.push(function () {
  return run("bridge refuses authenticated returnTo outside deeptutor package", async function () {
    var setup = loadBridgePage();

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/pages/freeCourse/freeCourse",
      authenticated: "1",
    });
    setup.page.onReady();
    await waitForTick();

    assert(
      setup.redirectCalls[0] &&
        setup.redirectCalls[0].url.indexOf("/packageDeeptutor/pages/chat/chat?entry_source=") === 0,
      "authenticated bridge should sanitize returnTo and fallback to deeptutor chat",
    );
  });
});

tests.push(function () {
  return run("bridge falls back to reLaunch when redirectTo fails", async function () {
    var setup = loadBridgePage();

    setup.wx.redirectTo = function (options) {
      setup.redirectCalls.push(options);
      if (options && typeof options.fail === "function") {
        options.fail(new Error("mock redirect failure"));
      }
    };

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
    });
    setup.page.onReady();
    await waitForTick();

    assert(setup.redirectCalls.length === 1, "bridge should attempt redirectTo first");
    assert(setup.reLaunchCalls.length === 1, "bridge should fallback to reLaunch on redirect failure");
  });
});

tests.push(function () {
  return run("bridge surfaces error when both redirect and reLaunch fail", async function () {
    var setup = loadBridgePage();

    setup.wx.redirectTo = function (options) {
      setup.redirectCalls.push(options);
      if (options && typeof options.fail === "function") {
        options.fail({ errMsg: "redirectTo:fail timeout" });
      }
    };

    setup.wx.reLaunch = function (options) {
      setup.reLaunchCalls.push(options);
      if (options && typeof options.fail === "function") {
        options.fail({ errMsg: "reLaunch:fail timeout" });
      }
    };

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
    });
    setup.page.onReady();
    await waitForTick();

    assert(setup.page.data.loading === false, "bridge should leave loading state after final route failure");
    assert(
      setup.page.data.errorMsg === "reLaunch:fail timeout",
      "bridge should expose the final route error message",
    );
  });
});

tests.push(function () {
  return run("bridge surfaces error when subpackage loading fails", async function () {
    var setup = loadBridgePage();

    setup.wx.loadSubpackage = function (options) {
      setup.loadSubpackageCalls.push(options);
      if (options && typeof options.fail === "function") {
        options.fail({ errMsg: "loadSubpackage:fail not found" });
      }
    };

    setup.page.onLoad({
      entrySource: "free_course_inline_entry",
      returnTo: "/packageDeeptutor/pages/chat/chat?entry_source=free_course_inline_entry",
    });
    setup.page.onReady();
    await waitForTick();

    assert(setup.redirectCalls.length === 0, "bridge should not redirect after subpackage failure");
    assert(
      setup.page.data.errorMsg === "loadSubpackage:fail not found",
      "bridge should expose subpackage loading error",
    );
  });
});

tests
  .reduce(function (chain, testFactory) {
    return chain.then(function () {
      return testFactory();
    });
  }, Promise.resolve())
  .then(function () {
    if (fail) {
      console.error(errors.join("\n"));
      process.exit(1);
    }

    console.log("PASS test_deeptutor_entry_bridge.js (" + pass + " assertions)");
  });
