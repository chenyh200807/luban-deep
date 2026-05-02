// test_package_tab_switch_performance.js — package workspace shell should not relaunch for tab switches
// Run: node yousenwebview/tests/test_package_tab_switch_performance.js

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

function loadShell(overrides) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/custom-tab-bar/index.js"),
    "utf8",
  );
  var componentDef = null;
  var redirectCalls = [];
  var reLaunchCalls = [];
  var workspaceBack = null;
  var options = overrides || {};
  var sandbox = {
    console: console,
    require: function (request) {
      if (request === "../utils/route") {
        return {
          chat: function () { return "/packageDeeptutor/pages/chat/chat"; },
          history: function () { return "/packageDeeptutor/pages/history/history"; },
          report: function () { return "/packageDeeptutor/pages/report/report"; },
          profile: function () { return "/packageDeeptutor/pages/profile/profile"; },
        };
      }
      if (request === "../utils/runtime") {
        return {
          setWorkspaceBack: function (url, label) {
            workspaceBack = { url: url, label: label };
          },
          clearWorkspaceBack: function () {
            workspaceBack = null;
          },
        };
      }
      if (request === "../utils/flags") {
        return {
          resolveShellList: function (list) { return list; },
          shouldShowWorkspaceShell: function () { return true; },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      redirectTo: function (call) {
        redirectCalls.push(call);
        if (options.redirectFails && call && typeof call.fail === "function") {
          call.fail(new Error("mock redirect failure"));
        }
      },
      reLaunch: function (call) {
        reLaunchCalls.push(call);
        if (options.reLaunchFails && call && typeof call.fail === "function") {
          call.fail(new Error("mock relaunch failure"));
        }
      },
    },
    Component: function (def) {
      componentDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/custom-tab-bar/index.js",
  });
  return {
    def: componentDef,
    wx: sandbox.wx,
    redirectCalls: redirectCalls,
    reLaunchCalls: reLaunchCalls,
    getWorkspaceBack: function () { return workspaceBack; },
  };
}

function createInstance(def) {
  var instance = {
    data: JSON.parse(JSON.stringify(def.data || {})),
    setData: function (patch) {
      Object.keys(patch || {}).forEach(function (key) {
        instance.data[key] = patch[key];
      });
    },
  };
  Object.keys(def.methods || {}).forEach(function (name) {
    instance[name] = def.methods[name];
  });
  return instance;
}

run("package tab switch gives immediate feedback and uses redirectTo", function () {
  var loaded = loadShell();
  var shell = createInstance(loaded.def);

  shell.switchTab({ currentTarget: { dataset: { index: 3 } } });

  assert(shell.data.selected === 3, "selected tab should update before navigation completes");
  assert(loaded.redirectCalls.length === 1, "tab switch should use redirectTo as the primary path");
  assert(
    loaded.redirectCalls[0].url === "/packageDeeptutor/pages/profile/profile",
    "redirectTo should target the selected package page",
  );
  assert(loaded.reLaunchCalls.length === 0, "tab switch should not relaunch the whole package on the happy path");
  assert(
    loaded.getWorkspaceBack() &&
      loaded.getWorkspaceBack().url === "/packageDeeptutor/pages/chat/chat",
    "tab switch should preserve workspace back target",
  );
});

run("package tab switch falls back to reLaunch only when redirectTo fails", function () {
  var loaded = loadShell({ redirectFails: true });
  var shell = createInstance(loaded.def);

  shell.switchTab({ currentTarget: { dataset: { index: 1 } } });

  assert(loaded.redirectCalls.length === 1, "redirectTo should still be attempted first");
  assert(loaded.reLaunchCalls.length === 1, "reLaunch should only be used as a fallback");
  assert(
    loaded.reLaunchCalls[0].url === "/packageDeeptutor/pages/history/history",
    "fallback reLaunch should preserve the selected destination",
  );
});

run("package tab switch ignores active tab", function () {
  var loaded = loadShell();
  var shell = createInstance(loaded.def);

  shell.switchTab({ currentTarget: { dataset: { index: 0 } } });

  assert(loaded.redirectCalls.length === 0, "active tab should not navigate again");
  assert(loaded.reLaunchCalls.length === 0, "active tab should not relaunch");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_tab_switch_performance.js (" + pass + " assertions)");
