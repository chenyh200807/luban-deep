// Run: node yousenwebview/tests/test_luban_projection_refresh.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function instantiate(relativePath, dependencies, wxOverrides) {
  var source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  var pageDef;
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    require: function (request) {
      if (Object.prototype.hasOwnProperty.call(dependencies, request)) return dependencies[request];
      throw new Error("unexpected require: " + request);
    },
    wx: Object.assign({
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
      stopPullDownRefresh: function () {},
    }, wxOverrides || {}),
    Page: function (definition) { pageDef = definition; },
  };
  vm.runInNewContext(source, sandbox, { filename: relativePath });
  var page = {
    data: JSON.parse(JSON.stringify(pageDef.data)),
    setData: function (patch) { Object.assign(this.data, patch || {}); },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return page;
}

async function testStationsNormalizesToTeachingPoints() {
  var reportCalls = 0;
  var redirectedTo = "";
  var api = {
    getLubanLessons: function () { return Promise.resolve({ items: [] }); },
    getLearningReport: function () { reportCalls += 1; return Promise.resolve({}); },
    getHomeDashboard: function () { return Promise.resolve({}); },
    unwrapResponse: function (value) { return value; },
  };
  var page = instantiate("packageDeeptutor/pages/luban/stations/stations.js", {
    "../../../utils/api": api,
    "../../../utils/auth": { isLoggedIn: function () { return true; } },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, isDark: function () { return false; } },
    "../../../utils/route": {
      lubanStations: function () { return "/teaching-points"; },
      lubanTeachingPoints: function () { return "/teaching-points"; },
    },
    "../../../utils/runtime": { redirectToLogin: function () {} },
    "../../../utils/learn-view-model": {
      buildLearnViewModel: function () { return { posters: [], litCount: 0, packUniverse: 40 }; },
    },
    "../../../utils/surface-telemetry": { trackProductBehavior: function () {}, trackModuleView: function () {}, trackModuleExit: function () {} },
  }, {
    redirectTo: function (payload) { redirectedTo = payload.url; },
  });

  page.onLoad();
  page.onShow();
  assert.strictEqual(redirectedTo, "/teaching-points", "legacy stations route must normalize to the 74-card C route");
  assert.strictEqual(reportCalls, 0, "legacy stations route must not fetch or render the competing 40-card projection");
}

async function testReviewRefresh() {
  var reportCalls = 0;
  var api = {
    getMistakeBook: function () { return Promise.resolve({}); },
    getLearningReport: function () { reportCalls += 1; return Promise.resolve({ pack_review: {} }); },
    getLubanConceptCardLibrary: function () { return Promise.resolve({}); },
    getLubanLessons: function () { return Promise.resolve({ items: [] }); },
    unwrapResponse: function (value) { return value; },
    describeRequestError: function (_error, fallback) { return fallback; },
  };
  var page = instantiate("packageDeeptutor/pages/luban/review/review.js", {
    "../../../utils/api": api,
    "../../../utils/auth": { isLoggedIn: function () { return true; } },
    "../../../utils/flags": { shouldShowWorkspaceShell: function () { return true; } },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, syncTabBar: function () {} },
    "../../../utils/route": { lubanReview: function () { return "/review"; } },
    "../../../utils/runtime": { redirectToLogin: function () {} },
    "../../../utils/mistake-book-view-model": {
      buildMistakeBookViewModel: function () { return {}; },
    },
    "../../../utils/review-view-model": {
      buildReviewViewModel: function () { return { dueEntries: [] }; },
    },
    "../../../utils/surface-telemetry": { trackProductBehavior: function () {}, trackModuleView: function () {}, trackModuleExit: function () {} },
  });

  page.onLoad();
  page.onShow();
  assert.strictEqual(reportCalls, 1, "first review onShow must not duplicate onLoad requests");
  await flush();
  page.onShow();
  assert.strictEqual(reportCalls, 2, "returning to review must refresh exactly once");
}

(async function main() {
  await testStationsNormalizesToTeachingPoints();
  await testReviewRefresh();
  console.log("PASS test_luban_projection_refresh.js");
})().catch(function (error) {
  console.error(error);
  process.exit(1);
});
