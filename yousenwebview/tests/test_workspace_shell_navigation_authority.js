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
    learn: function () {
      return "/packageDeeptutor/pages/learn/learn";
    },
    history: function () {
      return "/packageDeeptutor/pages/history/history";
    },
    chat: function () {
      return "/packageDeeptutor/pages/chat/chat";
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
      redirectTo: function (payload) {
        calls.reLaunch.push(payload || {});
      },
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

// 五 tab 壳顺序: 学习0 / 历史1 / 问鲁班2 / 学情3 / 我的4
var fromChat = loadTabBar(2);
fromChat.component.switchTab({ currentTarget: { dataset: { index: 3 } } });
assert(
  fromChat.calls.setWorkspaceBack.length === 1 &&
    fromChat.calls.setWorkspaceBack[0].url === "/packageDeeptutor/pages/chat/chat" &&
    fromChat.calls.setWorkspaceBack[0].label === "问鲁班",
  "leaving an active chat should preserve chat as the return target",
);
assert(fromChat.calls.clearWorkspaceBack === 0, "leaving chat should not clear return authority");
assert(
  fromChat.calls.reLaunch.length === 1 &&
    fromChat.calls.reLaunch[0].url === "/packageDeeptutor/pages/report/report",
  "shell should still relaunch to the selected page",
);

var fromReport = loadTabBar(3);
fromReport.component.switchTab({ currentTarget: { dataset: { index: 2 } } });
assert(
  fromReport.calls.setWorkspaceBack.length === 1 &&
    fromReport.calls.setWorkspaceBack[0].url === "/packageDeeptutor/pages/report/report" &&
    fromReport.calls.setWorkspaceBack[0].label === "学情",
  "returning from report to chat should preserve report as chat back target",
);

// 历史是正式 tab：离开时必须保留历史作为返回目标。
var fromHistory = loadTabBar(1);
fromHistory.component.switchTab({ currentTarget: { dataset: { index: 2 } } });
assert(
  fromHistory.calls.setWorkspaceBack.length === 1 &&
    fromHistory.calls.setWorkspaceBack[0].url === "/packageDeeptutor/pages/history/history" &&
    fromHistory.calls.setWorkspaceBack[0].label === "历史" &&
    fromHistory.calls.clearWorkspaceBack === 0,
  "leaving history should preserve the history tab as return authority",
);
assert(
  fromHistory.calls.reLaunch.length === 1 &&
    fromHistory.calls.reLaunch[0].url === "/packageDeeptutor/pages/chat/chat",
  "shell-less page tab tap should still navigate to the target tab",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_workspace_shell_navigation_authority.js (" + pass + " assertions)");
