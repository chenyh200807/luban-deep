// Run: node yousenwebview/tests/test_report_snapshot_swr.js
// 守「新鲜即跳过网络」(SWR)三件事:
// (a) 页面进入(首个 onShow)+ 新鲜缓存(< FRESH_MAX_AGE_MS)→ 直接以缓存为终态,
//     不发任何网络请求,loading 态全清;
// (b) 页面进入 + 陈旧缓存 → 先 hydrate 缓存(带"上次学情快照"提示)再网络刷新覆盖;
// (c) 子页返回(后续 onShow)→ 强制刷新,不被新鲜缓存跳过(刚发生学习动作)。
// 另守:直接调用 _loadReportPage()(不带 freshSkip)保持 SWR 旧行为,不跳网络。
// harness 写法参照 tests/test_report_snapshot_dedupe.js;report-cache 用带
// readWithMeta/FRESH_MAX_AGE_MS 的 stub,report-snapshot 用真模块(共享 builder 主路径)。
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

async function run(name, fn) {
  try {
    await fn();
  } catch (err) {
    fail++;
    errors.push(
      "ERROR: " + name + " -> " + (err && err.stack ? err.stack : err),
    );
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

async function settle() {
  for (var i = 0; i < 5; i++) await flushPromises();
}

var realReportSnapshot = require(
  path.join(__dirname, "../packageDeeptutor/utils/report-snapshot.js"),
);

var FRESH_MAX_AGE_MS = 60 * 1000;
var SNAPSHOT_MAX_AGE_MS = 30 * 60 * 1000;

// 与生产 report-cache 语义一致(严格大于 maxAge 过期),但年龄可控。
function makeReportCacheStub(state) {
  return {
    FRESH_MAX_AGE_MS: FRESH_MAX_AGE_MS,
    SNAPSHOT_MAX_AGE_MS: SNAPSHOT_MAX_AGE_MS,
    readWithMeta: function (userId, maxAgeMs) {
      var entry = state.entries[userId];
      if (!entry) return null;
      var ageMs = Date.now() - entry.cachedAt;
      if (ageMs > Number(maxAgeMs || 0)) return null;
      return { snapshot: entry.snapshot, ageMs: ageMs };
    },
    read: function (userId, maxAgeMs) {
      var hit = this.readWithMeta(userId, maxAgeMs);
      return hit ? hit.snapshot : null;
    },
    write: function (userId, snapshot) {
      state.writes.push(userId);
      state.entries[userId] = { cachedAt: Date.now(), snapshot: snapshot };
      return true;
    },
  };
}

function makeLearningReport(focusHint, level) {
  return {
    ok: true,
    schema_version: 2,
    authority: {
      read_model: "learning-report-read-model",
      progress_source: "learner_memory_events.learning_evidence",
      learning_brain_source: "dry_run_learning_evidence",
      deprecated_page_sources: [],
    },
    degraded: false,
    degraded_sources: [],
    source_status: {},
    freshness: {
      event_count: 3,
      unknown_date_count: 0,
      window_truncated: false,
    },
    overview: {
      today_done: 2,
      daily_target: 6,
      streak_days: 1,
      focus_hint: focusHint,
      learner_level: level,
    },
    mastery: {
      overall_mastery: 20,
      groups: [],
      hotspots: [],
      review_summary: {},
    },
    radar_dimensions: [{ name: "建筑物的构成与设计要求", value: 0.2 }],
    learning_brain: {},
    learner_facing: {},
  };
}

function loadReportPage(stubs) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
    "utf8",
  );
  var pageDef = null;
  var storage = {};
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
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      showModal: function () {},
      showToast: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") return stubs.api;
      if (request === "../../utils/report-cache") return stubs.reportCache;
      // SWR 主路径必须消费共享组装权威,不给 harness fallback 留活口。
      if (request === "../../utils/report-snapshot") return realReportSnapshot;
      if (request === "../../utils/surface-telemetry") {
        return {
          trackModuleView: function () {},
          trackModuleExit: function () {},
          trackProductBehavior: function () {},
        };
      }
      if (request === "../../utils/auth") {
        return {
          isLoggedIn: function () {
            return true;
          },
          getUserId: function () {
            return "student_a";
          },
          readOwnerStorage: function () {
            return null;
          },
          writeOwnerStorage: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, pixelRatio: 2 };
          },
          isDarkOr: function () {
            return false;
          },
          syncTabBar: function () {},
          vibrate: function () {},
        };
      }
      if (request === "../../utils/runtime") {
        return {
          getWorkspaceBack: function () {
            return null;
          },
        };
      }
      if (request === "../../utils/route") {
        return {
          report: function () {
            return "/packageDeeptutor/pages/report/report";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        };
      }
      if (request === "../../utils/flags") {
        return {
          ensureFeatureEnabled: function () {
            return true;
          },
          isFeatureEnabled: function () {
            return true;
          },
          shouldShowWorkspaceShell: function () {
            return true;
          },
        };
      }
      if (request === "../../utils/learning-report-view-model") {
        return require(
          path.join(
            __dirname,
            "../packageDeeptutor/utils/learning-report-view-model.js",
          ),
        );
      }
      if (request === "../../utils/learn-view-model") {
        return require(
          path.join(__dirname, "../packageDeeptutor/utils/learn-view-model.js"),
        );
      }
      if (request === "../../utils/report-home-view-model") {
        return require(
          path.join(
            __dirname,
            "../packageDeeptutor/utils/report-home-view-model.js",
          ),
        );
      }
      if (request === "../../utils/taxonomy") {
        return require(
          path.join(__dirname, "../packageDeeptutor/utils/taxonomy.js"),
        );
      }
      return {};
    },
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/report/report.js",
  });
  return pageDef;
}

function createPageInstance(pageDef) {
  var page = Object.assign({}, pageDef);
  page.data = Object.assign({}, pageDef.data);
  page.setData = function (patch) {
    this.data = Object.assign({}, this.data, patch);
  };
  page._ensureRadarRendered = function () {};
  return page;
}

function buildScenario(cacheAgeMs) {
  var counters = { report: 0, home: 0, lessons: 0 };
  var cacheState = { entries: {}, writes: [] };
  var cachedSnapshot = realReportSnapshot.buildUnifiedReportSnapshot({
    report: makeLearningReport("缓存学情先显示", "beginner"),
    homeDashboard: null,
    lessons: null,
  });
  if (cacheAgeMs !== null) {
    cacheState.entries.student_a = {
      cachedAt: Date.now() - cacheAgeMs,
      snapshot: cachedSnapshot,
    };
  }
  var pageDef = loadReportPage({
    reportCache: makeReportCacheStub(cacheState),
    api: {
      unwrapResponse: function (raw) {
        return raw;
      },
      getLearningReport: function () {
        counters.report += 1;
        return Promise.resolve(
          makeLearningReport("新鲜学情覆盖缓存", "intermediate"),
        );
      },
      getHomeDashboard: function () {
        counters.home += 1;
        return Promise.resolve({});
      },
      getLubanLessons: function () {
        counters.lessons += 1;
        return Promise.resolve(null);
      },
    },
  });
  return {
    counters: counters,
    cacheState: cacheState,
    page: createPageInstance(pageDef),
  };
}

(async function main() {
  await run(
    "(a) page enter + fresh cache -> zero network, loading cleared",
    async function () {
      var s = buildScenario(5 * 1000); // 5s < FRESH_MAX_AGE_MS
      s.page.onShow();
      await settle();
      assert(
        s.counters.report === 0 &&
          s.counters.home === 0 &&
          s.counters.lessons === 0,
        "fresh snapshot on page enter must skip all network reads",
      );
      assert(
        s.page.data.radarLoading === false &&
          s.page.data.masteryLoading === false &&
          s.page.data.learningBrainLoading === false,
        "fresh-skip must clear radar/mastery/learningBrain loading flags",
      );
      assert(
        s.page.data.focusHint === "缓存学情先显示",
        "fresh-skip must hydrate page data from the cached snapshot",
      );
      assert(
        s.page.data.degradedHint === "",
        "fresh-skip is a terminal render — must not show the refreshing-hint copy",
      );

      // (c) 子页返回:第二次 onShow,缓存仍然新鲜,也必须强制刷新。
      s.page.onShow();
      await settle();
      assert(
        s.counters.report === 1,
        "second onShow (sub-page return) must force a unified report refresh despite fresh cache",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存" &&
          s.page.data.learnerLevel === "中级",
        "sub-page return refresh must overwrite cached data with the fresh payload",
      );
      assert(
        s.cacheState.writes.length === 1 &&
          s.cacheState.writes[0] === "student_a",
        "forced refresh must write the fresh snapshot back to the cache",
      );
    },
  );

  await run(
    "(b) page enter + stale cache -> hydrate cached first, then refresh",
    async function () {
      var s = buildScenario(10 * 60 * 1000); // 10min: usable but not fresh
      s.page.onShow();
      // 缓存 hydrate 在 _loadReportPage 首个 await 之前同步完成。
      assert(
        s.page.data.focusHint === "缓存学情先显示" &&
          s.page.data.degradedHint.indexOf("上次学情快照") >= 0,
        "stale cache on page enter must render immediately with the refreshing hint",
      );
      await settle();
      assert(
        s.counters.report === 1,
        "stale cache on page enter must still trigger exactly one unified report read",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存" &&
          s.page.data.degradedHint === "",
        "fresh network payload must replace the stale cached snapshot",
      );
    },
  );

  await run(
    "direct _loadReportPage() keeps SWR behavior (no fresh-skip without flag)",
    async function () {
      var s = buildScenario(5 * 1000); // fresh cache
      await s.page._loadReportPage();
      assert(
        s.counters.report === 1,
        "_loadReportPage without freshSkip must still refresh over a fresh cache (dedupe-test parity)",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存",
        "flagless load must end on the fresh payload",
      );
    },
  );

  await run(
    "page enter with no cache -> normal network load",
    async function () {
      var s = buildScenario(null);
      s.page.onShow();
      await settle();
      assert(
        s.counters.report === 1,
        "first onShow without cache must load from network",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存",
        "network payload must hydrate the page when no cache exists",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_snapshot_swr.js (" + pass + " assertions)");
})();
