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
      getAssessmentProfile: async function () {
        profileCalls++;
        return {
          chapter_mastery: {
            建筑构造: { name: "建筑构造", mastery: 100 },
            地基基础: { name: "地基基础", mastery: 100 },
            防水工程: { name: "防水工程", mastery: 0 },
            主体结构: { name: "主体结构", mastery: 100 },
            施工管理: { name: "施工管理", mastery: 100 },
          },
        };
      },
      getRadarData: async function () {
        radarCalls++;
        return {
          dimensions: [
            { label: "建筑构造", score: 0, value: 0 },
            { label: "地基基础", score: 0, value: 0 },
            { label: "防水工程", score: 0, value: 0 },
            { label: "主体结构", score: 0, value: 0 },
            { label: "施工管理", score: 0, value: 0 },
          ],
        };
      },
      unwrapResponse: function (raw) {
        return raw;
      },
    },
    auth: {
      getUserId: function () {
        return "2d9eac15-5d26-4e93-941b-9ec6345ce6d9";
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

  assert(profileCalls === 1, "report radar flow should always load assessment profile first");
  assert(radarCalls === 0, "positive assessment profile should prevent zero radar override");
  assert(page.data.radarLoading === false, "report radar flow should finish loading");
  assert(page.data.radarError === false, "report radar flow should stay healthy");
  assert(page.data.avgScore === 80, "assessment profile should drive radar average");
  assert(page.data.strongCount === 4, "assessment profile should produce strong chapter counts");
  assert(page.data.weakCount === 1, "assessment profile should preserve weak chapter counts");
  assert(
    JSON.stringify(page.data.dimList.map(function (item) {
      return [item.name, item.pct];
    })) ===
      JSON.stringify([
        ["防水工程", 0],
        ["建筑构造", 100],
        ["地基基础", 100],
        ["主体结构", 100],
        ["施工管理", 100],
      ]),
    "zero radar response should not overwrite assessment mastery details",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_radar_authority.js (" + pass + " assertions)");
}

run().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
