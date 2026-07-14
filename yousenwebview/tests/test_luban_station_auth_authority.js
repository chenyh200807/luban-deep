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
    "../../../utils/helpers": {},
    "../../../utils/route": { lubanStations: () => "/packageDeeptutor/pages/luban/stations/stations" },
    "../../../utils/runtime": { redirectToLogin: (target) => { redirected = target; } },
    "../../../utils/learn-view-model": { buildLearnViewModel: () => ({}) },
  }));
  page.onLoad();
  assert.strictEqual(redirected, "/packageDeeptutor/pages/luban/stations/stations");
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
    "../../../utils/helpers": {},
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
    "../../../utils/helpers": {},
    "../../../utils/route": { lubanStations: () => "/packageDeeptutor/pages/luban/stations/stations" },
    "../../../utils/runtime": { redirectToLogin: (target) => { stationsRedirect = target; } },
    "../../../utils/learn-view-model": { buildLearnViewModel: () => ({}) },
  }));
  stationsPage.onLoad();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.strictEqual(stationsRedirect, "/packageDeeptutor/pages/luban/stations/stations");
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
    "../../../utils/helpers": {},
  }));
  stationPage.onLoad({ pack_id: "F16" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.strictEqual(stationRedirect, "/packageDeeptutor/pages/luban/station/station?pack_id=F16");
  assert.strictEqual(stationOptions.suppressAuthRedirect, true);
  assert.strictEqual(stationPage.data.errorText, "", "expired station auth must redirect, not show a false content error");

  let tapLoggedIn = true;
  let tapRedirect = "";
  let progressOptions = null;
  const tapPage = makePage(loadPage("pages/luban/station/station.js", {
    "../../../utils/api": {
      getLubanLessonDetail() {
        return Promise.resolve({
          title: "F16",
          card_url: "https://cdn/f16/lesson.html",
          practice_url: "https://cdn/f16/practice.html",
        });
      },
      issueLubanCardEntry() { return Promise.resolve({ entry_ticket: "card-capability" }); },
      unwrapResponse(value) { return value; },
      postLessonProgress(_packId, _tier, _sha, options) {
        progressOptions = options;
        tapLoggedIn = false;
        return Promise.reject(new Error("AUTH_EXPIRED"));
      },
      describeRequestError(_error, fallback) { return fallback; },
    },
    "../../../utils/auth": { isLoggedIn: () => tapLoggedIn },
    "../../../utils/route": { lubanStation: (packId) => "/packageDeeptutor/pages/luban/station/station?pack_id=" + packId },
    "../../../utils/runtime": { redirectToLogin: (target) => { tapRedirect = target; } },
    "../../../utils/surface-telemetry": { trackProductBehavior() {} },
    "../../../utils/helpers": {},
  }));
  tapPage.onLoad({ pack_id: "F16" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const continued = await tapPage.onPrimaryTap();
  assert.strictEqual(continued, false);
  assert.strictEqual(progressOptions.suppressAuthRedirect, true);
  assert.strictEqual(tapRedirect, "/packageDeeptutor/pages/luban/station/station?pack_id=F16");
  assert.strictEqual(tapPage.data.tier, "lesson", "expired evidence write must not race into practice");
  assert.strictEqual(tapPage.data._lessonReported, false, "failed evidence write must remain retryable");

  console.log("PASS test_luban_station_auth_authority.js (20 assertions)");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
