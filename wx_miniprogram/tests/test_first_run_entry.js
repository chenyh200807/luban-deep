var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var source = fs.readFileSync(
  path.join(__dirname, "..", "utils", "first-run-entry.js"),
  "utf8",
);

function loadEntry(options) {
  options = options || {};
  var switchTabs = [];
  var relaunches = [];
  var sandbox = {
    module: { exports: {} },
    exports: {},
    wx: {
      getStorageSync: function () {
        return options.done || null;
      },
      reLaunch: function (payload) {
        relaunches.push(payload);
      },
      switchTab: function (payload) {
        switchTabs.push(payload);
      },
    },
  };
  vm.runInNewContext(source, sandbox, { filename: "first-run-entry.js" });
  return {
    entry: sandbox.module.exports,
    switchTabs: switchTabs,
    relaunches: relaunches,
  };
}

(function main() {
  // 新账号 + 未完成 → 进「第一分钟」，不落 chat
  var newUser = loadEntry({});
  newUser.entry.goHomeAfterAuth(true);
  assert.strictEqual(newUser.relaunches[0].url, "/pages/first-run/first-run");
  assert.strictEqual(newUser.switchTabs.length, 0);

  // 返回用户（isNewAccount=false）→ 直达 chat，绝不进剧本
  var returning = loadEntry({});
  returning.entry.goHomeAfterAuth(false);
  assert.strictEqual(returning.switchTabs[0].url, "/pages/chat/chat");
  assert.strictEqual(returning.relaunches.length, 0);

  // 新账号但本机已完成过剧本 → 直达 chat，不重复出题
  var completed = loadEntry({ done: { at: "2026-07-10T00:00:00Z" } });
  completed.entry.goHomeAfterAuth(true);
  assert.strictEqual(completed.switchTabs[0].url, "/pages/chat/chat");
  assert.strictEqual(completed.relaunches.length, 0);

  // isFirstRunDone 读盘：坏数据不抛，返回 false
  var probe = loadEntry({
    done: null,
  });
  assert.strictEqual(probe.entry.isFirstRunDone(), false);

  console.log("PASS test_first_run_entry.js (new-account / returning / completed authority)");
})();
