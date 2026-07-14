// Run: node yousenwebview/tests/test_learn_supply_authority.js
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
  var calls = { redirects: [], lessons: 0, lessonOpts: null };
  var loggedIn = options.loggedIn !== false;
  var lessons = options.lessons || Promise.resolve({
    lessons: [{ pack_id: "A01", title: "检验批验收程序", card_hosted: true }],
    pack_universe: 41,
  });
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getLubanLessons: function (requestOptions) {
            calls.lessons += 1;
            calls.lessonOpts = requestOptions || {};
            if (options.expireOnLessons) {
              loggedIn = false;
              return Promise.reject(new Error("AUTH_EXPIRED"));
            }
            return lessons;
          },
          getHomeDashboard: function () {
            if (options.expireOnDashboard) {
              loggedIn = false;
              return Promise.reject(new Error("AUTH_EXPIRED"));
            }
            return Promise.reject(new Error("dashboard unavailable"));
          },
          getLearningReport: function () { return Promise.reject(new Error("report unavailable")); },
          getLubanSeethroughLibrary: function () { return Promise.resolve({}); },
          unwrapResponse: function (value) { return value; },
          describeRequestError: function (_error, fallback) { return fallback; },
        };
      }
      if (request === "../../utils/auth") {
        return {
          getUserId: function () { return loggedIn ? "user-1" : ""; },
          isLoggedIn: function () { return loggedIn; },
        };
      }
      if (request === "../../utils/runtime") {
        return {
          redirectToLogin: function (url) { calls.redirects.push(url); },
        };
      }
      if (request === "../../utils/first-run-entry") {
        return {
          getState: function () { return { state: "hidden", checkpoint: null, pending: null }; },
        };
      }
      if (request === "../../utils/helpers") return { syncTabBar: function () {} };
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/route") {
        return {
          learn: function () { return "/packageDeeptutor/pages/learn/learn"; },
          resolve: function (value) { return "/packageDeeptutor/" + value; },
        };
      }
      if (request === "../../utils/learn-view-model") {
        return {
          buildLearnViewModel: function (args) {
            var rows = (args.lessons && args.lessons.lessons) || [];
            return {
              hasSupply: rows.length > 0,
              nextStation: rows.length ? rows[0] : null,
              posters: rows,
              routePreview: rows,
              stats: {},
              todayProgress: {},
            };
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
    },
    Page: function (definition) { pageDef = definition; },
  };
  vm.runInNewContext(source, sandbox, { filename: "learn.js" });
  var page = {
    data: Object.assign({}, pageDef.data || {}),
    setData: function (next) { this.data = Object.assign({}, this.data, next || {}); },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

(async function main() {
  var anonymous = loadLearn({ loggedIn: false });
  anonymous.page.onLoad({});
  anonymous.page.onShow();
  assert.deepStrictEqual(anonymous.calls.redirects, ["/packageDeeptutor/pages/learn/learn"]);
  assert.strictEqual(anonymous.calls.lessons, 0, "未登录不得把 401 投影成无教学供给");

  var expired = loadLearn({ expireOnLessons: true });
  expired.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.deepStrictEqual(expired.calls.redirects, ["/packageDeeptutor/pages/learn/learn"]);
  assert.strictEqual(expired.calls.lessonOpts.suppressAuthRedirect, true);
  assert.strictEqual(expired.page.data.supplyError, "", "expired auth must redirect, not render supply error");

  var optionalExpired = loadLearn({ expireOnDashboard: true });
  optionalExpired.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.deepStrictEqual(optionalExpired.calls.redirects, ["/packageDeeptutor/pages/learn/learn"]);
  assert.strictEqual(optionalExpired.page.data.supplyError, "", "optional read auth expiry must not be swallowed");

  var failed = loadLearn({ lessons: Promise.reject(new Error("lesson authority unavailable")) });
  failed.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(failed.page.data.loading, false);
  assert.strictEqual(
    failed.page.data.supplyError,
    "教学资源加载失败，请检查登录或网络后重试",
  );
  assert.strictEqual(failed.page.data.vm.nextStation, null);

  var partial = loadLearn();
  partial.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(partial.page.data.supplyError, "");
  assert.strictEqual(partial.page.data.vm.nextStation.pack_id, "A01");
  assert.strictEqual(partial.page.data.loading, false);

  var wxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.wxml"),
    "utf8",
  );
  assert(wxml.indexOf("不是微课未上线") >= 0);
  assert(wxml.indexOf('bindtap="retrySupply"') >= 0);
  assert(wxml.indexOf('<view class="lr-status-row" wx:if="{{!supplyError}}">') >= 0);
  console.log("PASS test_learn_supply_authority.js (16 assertions)");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
