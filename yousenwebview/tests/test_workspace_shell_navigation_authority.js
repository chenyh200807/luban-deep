// test_workspace_shell_navigation_authority.js — workspace shell should preserve task return authority
// Run: node yousenwebview/tests/test_workspace_shell_navigation_authority.js

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

function loadTabBar(selected) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/custom-tab-bar/index.js"),
    "utf8",
  );
  var componentDef = null;
  var calls = {
    setWorkspaceBack: [],
    clearWorkspaceBack: 0,
    reLaunch: [],
  };
  var routeMock = {
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
    },
    history: function () {
      return "/packageDeeptutor/pages/history/history";
    },
    report: function () {
      return "/packageDeeptutor/pages/report/report";
    },
    profile: function () {
      return "/packageDeeptutor/pages/profile/profile";
    },
  };
  var sandbox = {
    console: console,
    require: function (request) {
      if (request === "../utils/route") return routeMock;
      if (request === "../utils/runtime") {
        return {
          setWorkspaceBack: function (url, label) {
            calls.setWorkspaceBack.push({ url: url, label: label });
          },
          clearWorkspaceBack: function () {
            calls.clearWorkspaceBack++;
          },
        };
      }
      if (request === "../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () {
            return true;
          },
          resolveShellList: function (list) {
            return list;
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      reLaunch: function (payload) {
        calls.reLaunch.push(payload || {});
      },
    },
    Component: function (def) {
      componentDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "yousenwebview/packageDeeptutor/custom-tab-bar/index.js",
  });
  var component = {
    data: Object.assign({}, componentDef.data, { selected: selected }),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(componentDef.methods || {}).forEach(function (key) {
    component[key] = componentDef.methods[key];
  });
  return { component: component, calls: calls };
}

var fromChat = loadTabBar(0);
fromChat.component.switchTab({ currentTarget: { dataset: { index: 2 } } });
assert(
  fromChat.calls.setWorkspaceBack.length === 1 &&
    fromChat.calls.setWorkspaceBack[0].url === "/packageDeeptutor/pages/chat/chat" &&
    fromChat.calls.setWorkspaceBack[0].label === "对话",
  "leaving an active chat should preserve chat as the return target",
);
assert(fromChat.calls.clearWorkspaceBack === 0, "leaving chat should not clear return authority");
assert(
  fromChat.calls.reLaunch.length === 1 &&
    fromChat.calls.reLaunch[0].url === "/packageDeeptutor/pages/report/report",
  "shell should still relaunch to the selected page",
);

var fromReport = loadTabBar(2);
fromReport.component.switchTab({ currentTarget: { dataset: { index: 0 } } });
assert(
  fromReport.calls.setWorkspaceBack.length === 1 &&
    fromReport.calls.setWorkspaceBack[0].url === "/packageDeeptutor/pages/report/report" &&
    fromReport.calls.setWorkspaceBack[0].label === "学情",
  "returning from report to chat should preserve report as chat back target",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_workspace_shell_navigation_authority.js (" + pass + " assertions)");
