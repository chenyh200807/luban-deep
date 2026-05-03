const assert = require("assert");
const path = require("path");

function injectModule(modulePath, exportsValue) {
  require.cache[modulePath] = {
    id: modulePath,
    filename: modulePath,
    loaded: true,
    exports: exportsValue,
  };
}

async function run() {
  const reportPath = path.join(__dirname, "../pages/report/report.js");
  const apiPath = path.join(__dirname, "../utils/api.js");
  const authPath = path.join(__dirname, "../utils/auth.js");
  const helpersPath = path.join(__dirname, "../utils/helpers.js");

  let pageDef = null;
  global.Page = function (definition) {
    pageDef = definition;
  };
  global.getApp = function () {
    return {
      checkAuth: function (cb) {
        if (typeof cb === "function") cb();
      },
      globalData: {},
    };
  };
  global.wx = {
    getStorageSync: function () {
      return null;
    },
  };

  const mockApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getAssessmentProfile: async function () {
      return {
        chapter_mastery: {
          "1A412030": { name: "1A412030", mastery: 100 },
          地基基础: { name: "地基基础", mastery: 100 },
          防水工程: { name: "防水工程", mastery: 0 },
          主体结构: { name: "主体结构", mastery: 100 },
          施工管理: { name: "施工管理", mastery: 100 },
        },
      };
    },
    getRadarData: async function () {
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
  };

  injectModule(apiPath, mockApi);
  injectModule(authPath, { getUserId: () => "2d9eac15-5d26-4e93-941b-9ec6345ce6d9" });
  injectModule(helpersPath, {});

  delete require.cache[reportPath];
  require(reportPath);

  const ctx = {
    data: {},
    _canvasReady: false,
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
  };

  await pageDef._loadRadar.call(ctx);

  assert.strictEqual(ctx.data.avgScore, 80, "assessment profile should drive radar average");
  assert.strictEqual(ctx.data.strongCount, 4, "non-zero assessment dimensions should be preserved");
  assert.strictEqual(ctx.data.weakCount, 1, "weak count should come from assessment profile");
  assert.deepStrictEqual(
    ctx.data.dimList.map((item) => [item.name, item.pct]),
      [
        ["防水工程", 0],
        ["结构设计与建筑材料", 100],
        ["地基基础", 100],
        ["主体结构", 100],
        ["施工管理", 100],
      ],
      "report detail list should use Chinese chapter labels and not be overwritten by zero radar response",
    );

  console.log("PASS test_report_radar_authority.js (4 assertions)");
}

run().catch(function (error) {
  console.error(error);
  process.exit(1);
});
