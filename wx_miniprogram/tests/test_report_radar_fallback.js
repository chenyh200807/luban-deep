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
  let radarCalls = 0;
  let requestedUserId = "";

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

  injectModule(apiPath, {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getAssessmentProfile: async function () {
      return {
        chapter_mastery: {
          建筑构造: { name: "建筑构造", mastery: 0 },
          地基基础: { name: "地基基础", mastery: 0 },
        },
      };
    },
    getRadarData: async function (userId) {
      radarCalls++;
      requestedUserId = userId;
      return {
        dimensions: [
          { label: "建筑构造", score: 70, value: 0.7 },
          { label: "地基基础", score: 50, value: 0.5 },
        ],
      };
    },
  });
  injectModule(authPath, {
    getUserId: function () {
      throw new Error("wx report radar fallback should not read auth storage");
    },
  });
  injectModule(helpersPath, {
    getWindowInfo: function () {
      return { statusBarHeight: 20 };
    },
    isDark: function () {
      return true;
    },
    syncTabBar: function () {},
    vibrate: function () {},
  });

  delete require.cache[reportPath];
  require(reportPath);

  const ctx = {
    data: { radarLoading: true, radarError: false },
    _canvasReady: false,
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
  };

  await pageDef._loadRadar.call(ctx);

  assert.strictEqual(radarCalls, 1, "wx report radar should fallback to dedicated radar when assessment data is empty");
  assert.strictEqual(requestedUserId, "self", "wx report radar fallback should use the authenticated self subject");
  assert.strictEqual(ctx.data.radarError, false, "wx report radar fallback should stay healthy");
  assert.strictEqual(ctx.data.avgScore, 60, "wx report radar fallback should recompute average score");

  console.log("PASS test_report_radar_fallback.js (4 assertions)");
}

run().catch(function (error) {
  console.error(error);
  process.exit(1);
});
