// test_deeptutor_feature_gate_state.js — feature gate / workspaceBack regression checks

var path = require("path");

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

function loadModules(flagOverrides) {
  var runtimePath = path.join(__dirname, "../packageDeeptutor/utils/runtime.js");
  var flagsPath = path.join(__dirname, "../packageDeeptutor/utils/flags.js");
  var hostRuntimePath = path.join(__dirname, "../packageDeeptutor/utils/host-runtime.js");
  var authPath = path.join(__dirname, "../packageDeeptutor/utils/auth.js");

  delete require.cache[require.resolve(runtimePath)];
  delete require.cache[require.resolve(flagsPath)];
  delete require.cache[require.resolve(hostRuntimePath)];
  delete require.cache[require.resolve(authPath)];

  var reLaunchCalls = [];
  var toastCalls = [];

  global.wx = {
    reLaunch: function (options) {
      reLaunchCalls.push(options);
    },
    navigateTo: function () {},
    showToast: function (options) {
      toastCalls.push(options);
    },
    getNetworkType: function (opts) {
      if (opts && typeof opts.success === "function") {
        opts.success({ networkType: "wifi" });
      }
    },
    onNetworkStatusChange: function () {},
    getStorageSync: function () {
      return "token_demo";
    },
    removeStorageSync: function () {},
  };
  global.getCurrentPages = function () {
    return [{ route: "packageDeeptutor/pages/chat/chat" }];
  };
  global.getApp = function () {
    return {
      getDeeptutorWorkspaceFlags: function () {
        return Object.assign(
          {
            workspaceEnabled: true,
            historyEnabled: true,
            reportEnabled: true,
            profileEnabled: true,
            assessmentEnabled: true,
          },
          flagOverrides || {},
        );
      },
    };
  };

  return {
    runtime: require(runtimePath),
    flags: require(flagsPath),
    reLaunchCalls: reLaunchCalls,
    toastCalls: toastCalls,
  };
}

run("feature gate clears stale workspaceBack before redirecting to chat", function () {
  var loaded = loadModules({ reportEnabled: false });

  loaded.runtime.setWorkspaceBack("/packageDeeptutor/pages/report/report", "学情");

  assert(loaded.flags.ensureFeatureEnabled("report") === false, "disabled report gate should block access");
  assert(loaded.toastCalls.length === 1, "disabled report gate should toast once");
  assert(
    loaded.reLaunchCalls.length === 1 &&
      loaded.reLaunchCalls[0] &&
      loaded.reLaunchCalls[0].url === "/packageDeeptutor/pages/chat/chat",
    "disabled report gate should redirect to chat",
  );
  assert(
    loaded.runtime.getWorkspaceBack("/packageDeeptutor/pages/chat/chat") === null,
    "disabled report gate should clear stale workspaceBack target",
  );
});

run("route-level enablement reflects workspace and page flags", function () {
  var loaded = loadModules({
    workspaceEnabled: false,
    historyEnabled: true,
    reportEnabled: true,
    profileEnabled: true,
  });

  assert(
    loaded.flags.isRouteEnabled("/packageDeeptutor/pages/history/history") === false,
    "workspace-disabled history route should be treated as unavailable",
  );
  assert(
    loaded.flags.isRouteEnabled("/packageDeeptutor/pages/report/report?from=profile") === false,
    "workspace-disabled report route with query should still be unavailable",
  );
  assert(
    loaded.flags.isRouteEnabled("/packageDeeptutor/pages/assessment/assessment") === true,
    "assessment route should remain independently controlled",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_feature_gate_state.js (" + pass + " assertions)");
