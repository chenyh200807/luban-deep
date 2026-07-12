// Run: node yousenwebview/tests/test_learn_first_run_entry.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flushPromises() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function loadLearn(options) {
  options = options || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = { navigateTo: [], completeFirstRun: [], clearPending: 0, done: 0, syncTabBar: 0 };
  var state = options.state || { state: "new", checkpoint: null, pending: null };
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getLubanLessons: function () { return Promise.resolve({}); },
          getHomeDashboard: function () { return Promise.resolve({}); },
          getLearningReport: function () { return Promise.resolve({}); },
          getLubanSeethroughLibrary: function () { return Promise.resolve({}); },
          unwrapResponse: function (value) { return value; },
          completeFirstRun: function (payload) {
            calls.completeFirstRun.push(payload);
            return Promise.resolve({ sync_status: "synced" });
          },
        };
      }
      if (request === "../../utils/auth") return { getUserId: function () { return "user-1"; } };
      if (request === "../../utils/first-run-entry") {
        return {
          getState: function () { return state; },
          clearPendingSync: function () { calls.clearPending++; },
          markDone: function () { calls.done++; },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          syncTabBar: function () { calls.syncTabBar++; },
        };
      }
      if (request === "../../utils/runtime") return { setPendingChatIntent: function () {} };
      if (request === "../../utils/route") {
        return {
          resolve: function (value) { return "/packageDeeptutor/" + value; },
          lubanReview: function () { return "/packageDeeptutor/pages/review/review"; },
          chat: function () { return "/packageDeeptutor/pages/chat/chat"; },
        };
      }
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/learn-view-model") {
        return { buildLearnViewModel: function () { return { hasSupply: false, posters: [], stats: {} }; } };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
      navigateTo: function (payload) { calls.navigateTo.push(payload); },
      reLaunch: function () {},
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, { filename: "learn.js" });
  var page = {
    data: Object.assign({}, pageDef.data || {}, { loading: false, _preview: true }),
    setData: function (next) { this.data = Object.assign({}, this.data, next || {}); },
    selectComponent: function () { return null; },
  };
  Object.keys(pageDef || {}).forEach(function (key) { if (key !== "data") page[key] = pageDef[key]; });
  return { page: page, calls: calls };
}

(async function main() {
  var fresh = loadLearn();
  fresh.page.onShow();
  assert.strictEqual(fresh.page.data.firstRunState, "new");
  fresh.page.openFirstRun();
  assert.strictEqual(
    fresh.calls.navigateTo[0].url,
    "/packageDeeptutor/pages/first-run/first-run",
  );

  var pendingPayload = { completion_id: "completion-pending-0001" };
  var pending = loadLearn({ state: { state: "syncing", checkpoint: null, pending: pendingPayload } });
  pending.page.onShow();
  await flushPromises();
  await flushPromises();
  assert.strictEqual(pending.calls.completeFirstRun.length, 1);
  assert.strictEqual(pending.calls.completeFirstRun[0].completion_id, "completion-pending-0001");
  assert.strictEqual(pending.calls.clearPending, 1);
  assert.strictEqual(pending.calls.done, 1);
  assert.strictEqual(pending.page.data.firstRunState, "hidden");
  assert(pending.calls.syncTabBar > 0, "Learning home restores the five-tab shell");

  var wxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.wxml"),
    "utf8",
  );
  assert(wxml.indexOf("firstRunState") >= 0);
  assert(wxml.indexOf("先做 4 道题，让鲁班认识你") >= 0);

  console.log("PASS test_learn_first_run_entry.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
