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
  var calls = { navigateTo: [], completeFirstRun: [], completeFirstRunOptions: [], redirects: [], clearPending: 0, done: 0, syncTabBar: 0, refreshFromServer: [] };
  var state = options.state || { state: "new", checkpoint: null, pending: null };
  var loggedIn = true;
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
          completeFirstRun: function (payload, requestOptions) {
            calls.completeFirstRun.push(payload);
            calls.completeFirstRunOptions.push(requestOptions || {});
            if (options.expireFirstRun) {
              loggedIn = false;
              return Promise.reject(new Error("AUTH_EXPIRED"));
            }
            return Promise.resolve({ sync_status: "synced" });
          },
          errorCodeOf: function () { return "unknown_error"; },
          getAssessmentProfile: function () { return Promise.resolve({}); },
        };
      }
      if (request === "../first-run/script-data") {
        // learn.js 陈旧 pending 自愈会读取 SCRIPT_VERSION;pending 无 script_version → 触发重放对齐
        return { SCRIPT_VERSION: "first_run_script.v1@test" };
      }
      if (request === "../../utils/auth") return {
        getUserId: function () { return "user-1"; },
        isLoggedIn: function () { return loggedIn; },
      };
      if (request === "../../utils/first-run-entry") {
        return {
          getState: function () { return state; },
          clearPendingSync: function () { calls.clearPending++; },
          markDone: function () { calls.done++; },
          refreshFromServer: function (userId) {
            calls.refreshFromServer.push(userId);
            return Promise.resolve(options.serverSnapshot || state);
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          isDarkOr: function () { return false; },
          syncTabBar: function () { calls.syncTabBar++; },
        };
      }
      if (request === "../../utils/runtime") return {
        setPendingChatIntent: function () {},
        redirectToLogin: function (target) { calls.redirects.push(target); },
      };
      if (request === "../../utils/route") {
        return {
          resolve: function (value) { return "/packageDeeptutor/" + value; },
          lubanReview: function () { return "/packageDeeptutor/pages/review/review"; },
          chat: function () { return "/packageDeeptutor/pages/chat/chat"; },
          learn: function () { return "/packageDeeptutor/pages/learn/learn"; },
        };
      }
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/learn-view-model") {
        return { buildLearnViewModel: function () { return { hasSupply: false, posters: [], stats: {} }; } };
      }
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
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
  assert.strictEqual(pending.calls.completeFirstRunOptions[0].suppressAuthRedirect, true);
  assert.strictEqual(pending.calls.clearPending, 1);
  assert.strictEqual(pending.calls.done, 1);
  assert.strictEqual(pending.page.data.firstRunState, "hidden");
  assert(pending.calls.syncTabBar > 0, "Learning home restores the five-tab shell");

  var expiredPending = loadLearn({
    state: { state: "syncing", checkpoint: null, pending: { completion_id: "completion-expired-0001" } },
    expireFirstRun: true,
  });
  expiredPending.page.onShow();
  await flushPromises();
  await flushPromises();
  assert.deepStrictEqual(expiredPending.calls.redirects, ["/packageDeeptutor/pages/learn/learn"]);
  assert.strictEqual(expiredPending.calls.clearPending, 0);
  assert.strictEqual(expiredPending.calls.done, 0);

  // 本地 new + 服务端已完成 → learn 回读投影后把门收成 hidden。
  var serverDone = loadLearn({
    state: { state: "new", checkpoint: null, pending: null },
    serverSnapshot: { state: "hidden", checkpoint: null, pending: null },
  });
  serverDone.page.onShow();
  assert.strictEqual(serverDone.page.data.firstRunState, "new", "renders local snapshot synchronously first");
  assert.deepStrictEqual(serverDone.calls.refreshFromServer, ["user-1"], "queries server once for a new local gate");
  await flushPromises();
  await flushPromises();
  assert.strictEqual(serverDone.page.data.firstRunState, "hidden", "server completion collapses the gate");

  // 本地 new + 服务端也未完成（真新用户）→ 维持 new，只查一次。
  var serverNew = loadLearn({
    state: { state: "new", checkpoint: null, pending: null },
    serverSnapshot: { state: "new", checkpoint: null, pending: null },
  });
  serverNew.page.onShow();
  await flushPromises();
  assert.strictEqual(serverNew.page.data.firstRunState, "new", "genuine new user keeps the gate");
  serverNew.page.onShow();
  assert.strictEqual(serverNew.calls.refreshFromServer.length, 1, "server readback is guarded to once per page lifetime");

  // 本地 hidden（有 DONE）→ 不查服务端。
  var localHidden = loadLearn({ state: { state: "hidden", checkpoint: null, pending: null } });
  localHidden.page.onShow();
  await flushPromises();
  assert.strictEqual(localHidden.calls.refreshFromServer.length, 0, "no server readback when local DONE exists");

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
