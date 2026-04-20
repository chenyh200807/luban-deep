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

function loadReportPage(stubs) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
    "utf8",
  );
  var pageDef = null;
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Page: function (def) {
      pageDef = def;
    },
    wx: {
      nextTick: function (fn) {
        if (typeof fn === "function") fn();
      },
    },
    require: function (request) {
      if (request === "../../utils/api") return stubs.api;
      if (request === "../../utils/auth") return stubs.auth;
      if (request === "../../utils/helpers") return stubs.helpers;
      if (request === "../../utils/runtime") return stubs.runtime;
      if (request === "../../utils/route") return stubs.route;
      if (request === "../../utils/flags") return stubs.flags;
      return {};
    },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/report/report.js",
  });
  return pageDef;
}

function createPageInstance(pageDef, data) {
  var page = Object.assign({}, pageDef);
  page.data = Object.assign({}, pageDef.data, data);
  page.setData = function (patch) {
    this.data = Object.assign({}, this.data, patch);
  };
  return page;
}

async function run() {
  var radarCalls = 0;
  var profileCalls = 0;
  var pageDef = loadReportPage({
    api: {
      getRadarData: async function () {
        radarCalls++;
        return {
          dimensions: [
            { label: "建筑构造", score: 80, value: 0.8 },
            { label: "地基基础", score: 40, value: 0.4 },
          ],
        };
      },
      getAssessmentProfile: async function () {
        profileCalls++;
        throw new Error("HTTP_500");
      },
      unwrapResponse: function (raw) {
        return raw;
      },
    },
    auth: {
      getUserId: function () {
        return "stale_user_alias";
      },
    },
    helpers: {
      getWindowInfo: function () {
        return { pixelRatio: 2 };
      },
    },
    runtime: {},
    route: {},
    flags: {},
  });
  var page = createPageInstance(pageDef, {
    radarLoading: true,
    radarError: false,
  });
  page._ensureRadarRendered = function () {};

  await page._loadRadar();

  assert(profileCalls === 1, "report radar flow should try assessment profile first");
  assert(radarCalls === 1, "report radar flow should fall back to dedicated radar when assessment fails");
  assert(page.data.radarLoading === false, "report radar flow should finish loading after radar fallback succeeds");
  assert(page.data.radarError === false, "report radar fallback should not leave the page in error state");
  assert(page.data.radarDimensions.length === 2, "report radar fallback should still populate dimensions");
  assert(page.data.radarDimensions[0].name === "建筑构造", "report radar fallback should preserve radar labels");
  assert(page.data.avgScore === 60, "report radar fallback should recompute average score from radar dimensions");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_radar_fallback.js (" + pass + " assertions)");
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
