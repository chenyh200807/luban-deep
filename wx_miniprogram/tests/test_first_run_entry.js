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
  var conversationCalls = 0;
  var exported;
  var sandbox = {
    module: { exports: {} },
    exports: {},
    clearTimeout: clearTimeout,
    setTimeout: setTimeout,
    require: function (request) {
      assert.strictEqual(request, "./api");
      return {
        getConversations: function () {
          conversationCalls++;
          return options.getConversations();
        },
      };
    },
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
  exported = sandbox.module.exports;
  return {
    entry: exported,
    switchTabs: switchTabs,
    relaunches: relaunches,
    conversationCalls: function () {
      return conversationCalls;
    },
  };
}

async function flush() {
  await new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

(async function main() {
  var completed = loadEntry({
    done: { at: "2026-07-10T00:00:00Z" },
    getConversations: function () {
      throw new Error("completed users must not query history");
    },
  });
  completed.entry.goHomeAfterAuth();
  assert.strictEqual(completed.conversationCalls(), 0);
  assert.strictEqual(completed.switchTabs[0].url, "/pages/chat/chat");

  var newUser = loadEntry({
    getConversations: function () {
      return Promise.resolve({ data: { conversations: [] } });
    },
  });
  newUser.entry.goHomeAfterAuth();
  await flush();
  assert.strictEqual(newUser.relaunches[0].url, "/pages/first-run/first-run");
  assert.strictEqual(newUser.switchTabs.length, 0);

  var returningUser = loadEntry({
    getConversations: function () {
      return Promise.resolve({ items: [{ id: "conversation-1" }] });
    },
  });
  returningUser.entry.goHomeAfterAuth();
  await flush();
  assert.strictEqual(returningUser.switchTabs[0].url, "/pages/chat/chat");
  assert.strictEqual(returningUser.relaunches.length, 0);

  var unavailable = loadEntry({
    getConversations: function () {
      return Promise.reject(new Error("network unavailable"));
    },
  });
  unavailable.entry.goHomeAfterAuth();
  await flush();
  assert.strictEqual(unavailable.switchTabs[0].url, "/pages/chat/chat");
  assert.strictEqual(unavailable.relaunches.length, 0);

  console.log("PASS test_first_run_entry.js (new/returning/fail-open authority)");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
