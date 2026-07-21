const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "../packageDeeptutor");

function loadPage(relativePath, modules) {
  const source = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
  let definition = null;
  const sandbox = {
    Promise,
    console,
    Page(value) {
      definition = value;
    },
    require(request) {
      if (!(request in modules)) throw new Error("unexpected require: " + request);
      return modules[request];
    },
    wx: { getSystemInfoSync: () => ({ statusBarHeight: 20 }) },
  };
  vm.runInNewContext(source, sandbox, { filename: relativePath });
  return definition;
}

function makePage(definition) {
  const page = Object.assign({}, definition);
  page.data = Object.assign({}, definition.data);
  page.setData = function (patch) {
    Object.assign(this.data, patch);
  };
  return page;
}

{
  let redirected = "";
  let lessonCalls = 0;
  const page = makePage(loadPage("pages/luban/stations/stations.js", {
    "../../../utils/api": { getLubanLessons() { lessonCalls += 1; return Promise.resolve({}); } },
    "../../../utils/auth": { isLoggedIn: () => false },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} },
    "../../../utils/route": { lubanStations: () => "/packageDeeptutor/pages/luban/teaching-points/teaching-points" },
    "../../../utils/runtime": { redirectToLogin: (target) => { redirected = target; } },
    "../../../utils/learn-view-model": { buildLearnViewModel: () => ({}) },
    "../../../utils/surface-telemetry": { trackProductBehavior() {}, trackModuleView() {}, trackModuleExit() {} },
  }));
  page.onLoad();
  assert.strictEqual(redirected, "/packageDeeptutor/pages/luban/teaching-points/teaching-points");
  assert.strictEqual(lessonCalls, 0, "anonymous route page must not call protected lessons API");
}

{
  let redirected = "";
  let detailCalls = 0;
  let telemetryCalls = 0;
  const page = makePage(loadPage("pages/luban/station/station.js", {
    "../../../utils/api": { getLubanLessonDetail() { detailCalls += 1; return Promise.resolve({}); }, issueLubanCardEntry() { return Promise.resolve({ entry_ticket: "card-capability" }); } },
    "../../../utils/auth": { isLoggedIn: () => false },
    "../../../utils/route": { lubanStation: (packId) => "/packageDeeptutor/pages/luban/station/station?pack_id=" + packId },
    "../../../utils/runtime": { redirectToLogin: (target) => { redirected = target; } },
    "../../../utils/surface-telemetry": { trackProductBehavior() { telemetryCalls += 1; } },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} },
  }));
  page.onLoad({ pack_id: "F16" });
  assert.strictEqual(redirected, "/packageDeeptutor/pages/luban/station/station?pack_id=F16");
  assert.strictEqual(detailCalls, 0, "anonymous deep link must not call protected detail API");
  assert.strictEqual(telemetryCalls, 0, "anonymous deep link must not emit a station-view event");
}

{
  const route = require(path.join(ROOT, "utils/route.js"));
  const target = route.lubanStation("A01");
  assert.strictEqual(target, "/packageDeeptutor/pages/luban/station/station?pack_id=A01");
  assert.strictEqual(
    route.lubanStation("D14", 2),
    "/packageDeeptutor/pages/luban/station/station?pack_id=D14&episode=2",
    "第二集保留在原生站点深链，服务端负责 fail-closed 选择实际发布页",
  );
  assert.strictEqual(route.resolveInternalUrl(target, "/fallback"), target, "login returnTo must preserve station deep links");
  const stationsWxml = fs.readFileSync(path.join(ROOT, "pages/luban/stations/stations.wxml"), "utf8");
  assert(stationsWxml.indexOf('<view class="sr-hero" wx:if="{{!errorText}}">') >= 0, "route errors must not render false 0/40 progress");
}

(async function testExpiredTokenReturnTargets() {
  let stationsLoggedIn = true;
  let stationsRedirect = "";
  let stationsOptions = null;
  const stationsPage = makePage(loadPage("pages/luban/stations/stations.js", {
    "../../../utils/api": {
      getLubanLessons(options) { stationsOptions = options; stationsLoggedIn = false; return Promise.reject(new Error("AUTH_EXPIRED")); },
      getLearningReport() { return Promise.resolve({}); },
      getHomeDashboard() { return Promise.resolve({}); },
      unwrapResponse(value) { return value; },
      describeRequestError(_error, fallback) { return fallback; },
    },
    "../../../utils/auth": { isLoggedIn: () => stationsLoggedIn },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} },
    "../../../utils/route": { lubanStations: () => "/packageDeeptutor/pages/luban/teaching-points/teaching-points" },
    "../../../utils/runtime": { redirectToLogin: (target) => { stationsRedirect = target; } },
    "../../../utils/learn-view-model": { buildLearnViewModel: () => ({}) },
    "../../../utils/surface-telemetry": { trackProductBehavior() {}, trackModuleView() {}, trackModuleExit() {} },
  }));
  stationsPage.onLoad();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.strictEqual(stationsRedirect, "/packageDeeptutor/pages/luban/teaching-points/teaching-points");
  assert.strictEqual(stationsOptions.suppressAuthRedirect, true);
  assert.strictEqual(stationsPage.data.errorText, "", "expired route auth must redirect, not fabricate an empty route");

  let stationLoggedIn = true;
  let stationRedirect = "";
  let stationOptions = null;
  const stationPage = makePage(loadPage("pages/luban/station/station.js", {
    "../../../utils/api": {
      getLubanLessonDetail(_packId, options) { stationOptions = options; stationLoggedIn = false; return Promise.reject(new Error("AUTH_EXPIRED")); },
      issueLubanCardEntry() { return Promise.resolve({ entry_ticket: "card-capability" }); },
      describeRequestError(_error, fallback) { return fallback; },
    },
    "../../../utils/auth": { isLoggedIn: () => stationLoggedIn },
    "../../../utils/route": { lubanStation: (packId) => "/packageDeeptutor/pages/luban/station/station?pack_id=" + packId },
    "../../../utils/runtime": { redirectToLogin: (target) => { stationRedirect = target; } },
    "../../../utils/surface-telemetry": { trackProductBehavior() {} },
    "../../../utils/helpers": { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} },
  }));
  stationPage.onLoad({ pack_id: "F16" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.strictEqual(stationRedirect, "/packageDeeptutor/pages/luban/station/station?pack_id=F16");
  assert.strictEqual(stationOptions.suppressAuthRedirect, true);
  assert.strictEqual(stationPage.data.errorText, "", "expired station auth must redirect, not show a false content error");

  console.log("PASS test_luban_station_auth_authority.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
