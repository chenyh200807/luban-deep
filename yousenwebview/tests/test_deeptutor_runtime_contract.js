// test_deeptutor_runtime_contract.js — runtime thin-layer regression checks

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

function loadModule(relativePath) {
  var fullPath = path.join(__dirname, "..", relativePath);
  delete require.cache[require.resolve(fullPath)];
  return require(fullPath);
}

run("host-runtime reads and writes theme against host globalData", function () {
  var storage = {};
  var app = {
    globalData: {
      theme: "light",
    },
  };

  global.wx = {
    getStorageSync: function (key) {
      return storage[key];
    },
    setStorageSync: function (key, value) {
      storage[key] = value;
    },
  };
  global.getApp = function () {
    return app;
  };

  var hostRuntime = loadModule("packageDeeptutor/utils/host-runtime.js");

  assert(hostRuntime.getTheme() === "light", "host-runtime should prefer host global theme");
  assert(hostRuntime.setTheme("dark") === "dark", "host-runtime should return normalized theme");
  assert(app.globalData.theme === "dark", "host-runtime should sync theme back to host globalData");
  assert(storage.theme === "dark", "host-runtime should persist theme into storage");
});

run("helpers theme helpers delegate to host-runtime", function () {
  var storage = {};
  var app = {
    globalData: {
      theme: "dark",
    },
  };

  global.wx = {
    getStorageSync: function (key) {
      return storage[key];
    },
    setStorageSync: function (key, value) {
      storage[key] = value;
    },
  };
  global.getApp = function () {
    return app;
  };

  var helpers = loadModule("packageDeeptutor/utils/helpers.js");

  assert(helpers.getTheme() === "dark", "helpers should read theme through host-runtime");
  helpers.setTheme("light");
  assert(app.globalData.theme === "light", "helpers should update host global theme");
  assert(storage.theme === "light", "helpers should persist theme through host-runtime");
});

run("flags resolves workspace flags through host runtime layer", function () {
  var app = {
    getDeeptutorWorkspaceFlags: function () {
      return {
        workspaceEnabled: true,
        historyEnabled: false,
        reportEnabled: true,
        profileEnabled: false,
        assessmentEnabled: true,
      };
    },
  };

  global.wx = {
    showToast: function () {},
    reLaunch: function () {},
  };
  global.getApp = function () {
    return app;
  };

  var flags = loadModule("packageDeeptutor/utils/flags.js");

  var resolved = flags.getWorkspaceFlags();
  assert(resolved.historyEnabled === false, "flags should read history flag from host runtime");
  assert(resolved.profileEnabled === false, "flags should read profile flag from host runtime");
  assert(flags.isFeatureEnabled("history") === false, "flags helper should honor disabled history");
  assert(flags.shouldShowWorkspaceShell() === true, "workspace shell should stay visible when report remains enabled");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_runtime_contract.js (" + pass + " assertions)");
