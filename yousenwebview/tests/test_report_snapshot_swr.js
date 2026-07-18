// Run: node yousenwebview/tests/test_report_snapshot_swr.js
// 守「缓存秒渲染 + 始终静默刷新」(SWR,无 fresh-skip)五件事:
// (a) 页面进入 + 新鲜缓存 → 先渲染缓存(带"正在刷新"提示),仍发起网络刷新,
//     网络回来覆盖并清提示;子页返回(第二次 onShow)同样强制刷新;
// (b) 页面进入 + 陈旧缓存 → 同上(缓存年龄不改变行为);
// (c) 网络失败 + 有缓存 → degradedHint 改口为"网络暂时不稳…",不残留"正在刷新…";
// (d) 无缓存 → 正常网络拉取;
// (e) 刷新成功 → 经 writeIfFresher(带 fetchStartedAt)写缓存,不走裸 write。
// 注:「新鲜即跳过网络」门已被对抗 review 证伪删除(会把陈旧/降级快照钉成终态、
// 吞掉其他 tab 刚完成的学习动作),本测试不再包含 fresh-skip 断言。
// harness 写法参照 tests/test_report_snapshot_dedupe.js;report-cache 用带
// read/write/writeIfFresher 的 stub,report-snapshot 用真模块(共享 builder 主路径)。
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

var SNAPSHOT_MAX_AGE_MS = 30 * 60 * 1000;

// 与生产 report-cache 语义一致(严格大于 maxAge 过期),但年龄可控。
// writeIfFresher 记录调用供 (e) 断言,并落盘到 entries(简化:测试内单飞行,
// 不复现并发写序竞争,写序真语义由 report-cache 自己的测试守)。
function makeReportCacheStub(state) {
  return {
    SNAPSHOT_MAX_AGE_MS: SNAPSHOT_MAX_AGE_MS,
    read: function (userId, maxAgeMs) {
      var entry = state.entries[userId];
      if (!entry) return null;
      var ageMs = Date.now() - entry.cachedAt;
      if (ageMs > Number(maxAgeMs || 0)) return null;
      return entry.snapshot;
    },
    write: function (userId, snapshot) {
      state.bareWrites.push(userId);
      state.entries[userId] = { cachedAt: Date.now(), snapshot: snapshot };
      return true;
    },
    writeIfFresher: function (userId, snapshot, fetchStartedAt) {
      state.writeIfFresherCalls.push({
        userId: userId,
        fetchStartedAt: fetchStartedAt,
      });
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

// opts.cacheAgeMs=null → 无缓存;opts.networkFails=true → unified report 拉取失败。
function buildScenario(opts) {
  var cacheAgeMs = opts.cacheAgeMs;
  var networkFails = opts.networkFails === true;
  var counters = { report: 0, home: 0, lessons: 0 };
  var cacheState = { entries: {}, bareWrites: [], writeIfFresherCalls: [] };
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
        return networkFails
          ? Promise.reject(new Error("simulated network failure"))
          : Promise.resolve(
              makeLearningReport("新鲜学情覆盖缓存", "intermediate"),
            );
      },
      getHomeDashboard: function () {
        counters.home += 1;
        return networkFails
          ? Promise.reject(new Error("simulated network failure"))
          : Promise.resolve({});
      },
      getLubanLessons: function () {
        counters.lessons += 1;
        return networkFails
          ? Promise.reject(new Error("simulated network failure"))
          : Promise.resolve(null);
      },
    },
  });
  return {
    counters: counters,
    cacheState: cacheState,
    page: createPageInstance(pageDef),
  };
}

var REFRESHING_HINT = "正在刷新，先显示上次学情快照";
var NETWORK_DEGRADED_HINT = "网络暂时不稳，已显示上次学情快照";

(async function main() {
  await run(
    "(a) page enter + fresh cache -> cached render first, still refreshes over network",
    async function () {
      var s = buildScenario({ cacheAgeMs: 5 * 1000 });
      s.page.onShow();
      // 缓存 hydrate 在 _loadReportPage 首个 await 之前同步完成。
      assert(
        s.page.data.focusHint === "缓存学情先显示" &&
          s.page.data.degradedHint === REFRESHING_HINT,
        "fresh cache on page enter must render cached data immediately with the refreshing hint",
      );
      assert(
        s.page.data.radarLoading === false &&
          s.page.data.masteryLoading === false &&
          s.page.data.learningBrainLoading === false,
        "cached hydrate must clear radar/mastery/learningBrain loading flags",
      );
      await settle();
      assert(
        s.counters.report === 1,
        "fresh cache must NOT skip the network — exactly one unified report read on page enter",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存" &&
          s.page.data.learnerLevel === "中级" &&
          s.page.data.degradedHint === "",
        "network payload must overwrite the cached render and clear the refreshing hint",
      );

      // 子页返回:第二次 onShow(刚发生学习动作)同样强制刷新。
      s.page.onShow();
      await settle();
      assert(
        s.counters.report === 2,
        "second onShow (sub-page return) must refresh again — onShow behavior is uniform",
      );
    },
  );

  await run(
    "(b) page enter + stale cache -> hydrate cached first, then refresh",
    async function () {
      var s = buildScenario({ cacheAgeMs: 10 * 60 * 1000 }); // 10min, still < SNAPSHOT_MAX_AGE_MS
      s.page.onShow();
      assert(
        s.page.data.focusHint === "缓存学情先显示" &&
          s.page.data.degradedHint === REFRESHING_HINT,
        "stale cache on page enter must render immediately with the refreshing hint",
      );
      await settle();
      assert(
        s.counters.report === 1,
        "stale cache on page enter must trigger exactly one unified report read",
      );
      assert(
        s.page.data.focusHint === "新鲜学情覆盖缓存" &&
          s.page.data.degradedHint === "",
        "fresh network payload must replace the stale cached snapshot",
      );
    },
  );

  await run(
    "(c) network failure + cache -> degraded hint replaces the refreshing hint",
    async function () {
      var s = buildScenario({ cacheAgeMs: 5 * 1000, networkFails: true });
      s.page.onShow();
      assert(
        s.page.data.degradedHint === REFRESHING_HINT,
        "cached hydrate must show the refreshing hint before the network settles",
      );
      await settle();
      assert(
        s.counters.report === 1,
        "network-failure path must still have attempted the unified report read",
      );
      assert(
        s.page.data.focusHint === "缓存学情先显示",
        "network failure must keep showing the cached snapshot data",
      );
      assert(
        s.page.data.degradedHint === NETWORK_DEGRADED_HINT,
        "failed refresh must replace the refreshing hint with the network-degraded hint, not keep '" +
          REFRESHING_HINT +
          "'",
      );
      assert(
        s.page.data.radarLoading === false &&
          s.page.data.masteryLoading === false &&
          s.page.data.learningBrainLoading === false,
        "network-failure-with-cache branch must clear loading flags",
      );
      assert(
        s.page.data.reportFallbackActive === false,
        "cached fallback must not flip reportFallbackActive",
      );
    },
  );

  await run(
    "(d) page enter with no cache -> normal network load",
    async function () {
      var s = buildScenario({ cacheAgeMs: null });
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

  await run(
    "(e) successful refresh writes cache via writeIfFresher (ordered write guard)",
    async function () {
      var s = buildScenario({ cacheAgeMs: null });
      var before = Date.now();
      s.page.onShow();
      await settle();
      assert(
        s.cacheState.writeIfFresherCalls.length === 1 &&
          s.cacheState.writeIfFresherCalls[0].userId === "student_a",
        "successful refresh must persist through writeIfFresher exactly once",
      );
      assert(
        typeof s.cacheState.writeIfFresherCalls[0].fetchStartedAt === "number" &&
          s.cacheState.writeIfFresherCalls[0].fetchStartedAt >= before,
        "writeIfFresher must receive the fetchStartedAt anchor recorded before the fetch",
      );
      assert(
        s.cacheState.bareWrites.length === 0,
        "success path must not fall back to the bare write() (would bypass the write-order guard)",
      );
    },
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_snapshot_swr.js (" + pass + " assertions)");
})();
