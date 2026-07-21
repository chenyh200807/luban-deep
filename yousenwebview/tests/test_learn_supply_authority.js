// Run: node yousenwebview/tests/test_learn_supply_authority.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function flushPromises() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function validDashboard(nextStep) {
  var payload = {
    learner_settings: { exam_date: "", daily_target: 5 },
    review: { overdue: 0, due_today: 0 },
    mastery: { weak_nodes: [] },
    today: { hint: "" },
  };
  if (nextStep) payload.next_step = nextStep;
  return payload;
}

function validReport(todayDone) {
  return {
    schema_version: 1,
    authority: { read_model: "learning-report-read-model" },
    overview: { today_done: todayDone || 0, daily_target: 5 },
    freshness: { event_count: 0, window_truncated: false },
    learning_brain: { weak_points: [] },
    pack_lifecycle: { packs: {} },
    pack_review: { enabled: true, degraded: false, due: [] },
  };
}

function loadLearn(options) {
  options = options || {};
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = { redirects: [], lessons: 0, lessonOpts: null, buildArgs: [], cacheWrites: [], cacheReads: [] };
  var loggedIn = options.loggedIn !== false;
  var lessons = options.lessons || Promise.resolve({
    lessons: [{ pack_id: "A01", title: "检验批验收程序", card_hosted: true }],
    pack_universe: 41,
    teaching_topic_universe: 40,
    teaching_points: [{ pack_id: "A01" }],
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
            return options.dashboard || Promise.reject(new Error("dashboard unavailable"));
          },
          getLearningReport: function () {
            return options.report || Promise.reject(new Error("report unavailable"));
          },
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
      if (request === "../../utils/helpers") return { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} };
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/route") {
        return {
          learn: function () { return "/packageDeeptutor/pages/learn/learn"; },
          resolve: function (value) { return "/packageDeeptutor/" + value; },
          lubanStation: function (packId) { return "/station?pack_id=" + packId; },
        };
      }
      if (request === "../../utils/learn-view-model") {
        var realLearnVm = require("../packageDeeptutor/utils/learn-view-model");
        return {
          buildLearnViewModel: function (args) {
            calls.buildArgs.push(args);
            return realLearnVm.buildLearnViewModel(args);
          },
        };
      }
      if (request === "../../utils/report-cache") {
        return {
          SNAPSHOT_MAX_AGE_MS: 1800000,
          // cachedAgeMs 模拟快照真实年龄:读取窗小于快照年龄时返回 null,
          // 用于区分 30min 秒渲染窗与 last-known-good 供给兜底窗。
          read: function (userId, maxAgeMs) {
            calls.cacheReads.push(maxAgeMs);
            if (options.cachedAgeMs && Number(maxAgeMs) < options.cachedAgeMs) return null;
            return options.cached || null;
          },
          writeIfFresher: function (userId, snapshot, startedAt) {
            calls.cacheWrites.push({ userId: userId, snapshot: snapshot, startedAt: startedAt });
          },
        };
      }
      if (request === "../../utils/report-snapshot") {
        return require("../packageDeeptutor/utils/report-snapshot");
      }
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
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

  // ── 供给显示仲裁(2026-07-21 收权):错误终态只在「从未有任何已知供给」时合法 ──
  var cachedTriple = {
    homeDashboard: validDashboard({
      mode: "learn_next",
      source_authority: "pack_lifecycle_projection",
      source_ref: "A01",
      reason: "cached",
    }),
    report: validReport(1),
    lessons: {
      lessons: [{ pack_id: "A01", title: "缓存站" }],
      pack_universe: 41,
      teaching_topic_universe: 40,
      teaching_points: [{ pack_id: "A01" }],
    },
  };

  // 已在屏的供给(30min 内快照秒渲染)不得被瞬时请求失败替换成错误卡。
  var failedButOnScreen = loadLearn({
    lessons: Promise.reject(new Error("request:fail transient")),
    cached: cachedTriple,
  });
  failedButOnScreen.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(
    failedButOnScreen.page.data.supplyError,
    "",
    "transient refresh failure must not overwrite on-screen supply with an error terminal",
  );
  assert.strictEqual(failedButOnScreen.page.data.vm.nextStation.pack_id, "A01");
  assert.strictEqual(failedButOnScreen.page.data.vm.projectionState, "stale");
  assert.strictEqual(failedButOnScreen.page.data.vm.actionsEnabled, false);

  // 冷启动 + 请求失败 + 快照超过 30min 秒渲染窗:last-known-good 供给兜底,
  // 不弹错误卡(供给是慢变 manifest 投影,旧供给仍可学)。
  var failedWithLkg = loadLearn({
    lessons: Promise.reject(new Error("request:fail transient")),
    cached: cachedTriple,
    cachedAgeMs: 2 * 60 * 60 * 1000,
  });
  failedWithLkg.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(
    failedWithLkg.page.data.supplyError,
    "",
    "cold start with last-known-good supply must render stale supply, not the error card",
  );
  assert.strictEqual(failedWithLkg.page.data.vm.nextStation.pack_id, "A01");
  assert.strictEqual(failedWithLkg.page.data.vm.projectionState, "stale");
  assert.strictEqual(failedWithLkg.page.data.vm.actionsEnabled, false);
  assert(
    failedWithLkg.calls.cacheReads.some(function (age) { return Number(age) > 1800000; }),
    "supply fallback reads a wider last-known-good window than the 30min hydrate window",
  );

  // last-known-good 里没有合法供给:错误卡仍是唯一合法终态(不发明供给)。
  var failedWithInvalidLkg = loadLearn({
    lessons: Promise.reject(new Error("request:fail transient")),
    cached: { homeDashboard: {}, report: {}, lessons: {} },
    cachedAgeMs: 2 * 60 * 60 * 1000,
  });
  failedWithInvalidLkg.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(
    failedWithInvalidLkg.page.data.supplyError,
    "教学资源加载失败，请检查登录或网络后重试",
    "invalid last-known-good must not fabricate supply; error terminal stays",
  );

  var partial = loadLearn();
  partial.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(partial.page.data.supplyError, "");
  assert.strictEqual(partial.page.data.vm.nextStation.pack_id, "A01");
  assert.strictEqual(partial.page.data.vm.taskCard, null, "partial reads must not invent a task CTA");
  assert.strictEqual(partial.page.data.vm.actionsEnabled, false);
  assert.strictEqual(partial.page.data.vm.progressAvailable, false);
  assert.strictEqual(partial.page.data.vm.projectionState, "partial");
  assert.strictEqual(partial.calls.cacheWrites.length, 0, "partial snapshots must never enter cache");
  assert.strictEqual(partial.page.data.loading, false);

  var live = loadLearn({
    dashboard: Promise.resolve(validDashboard({
      mode: "learn_next",
      source_authority: "pack_lifecycle_projection",
      source_ref: "A01",
      reason: "next",
    })),
    report: Promise.resolve(validReport(2)),
  });
  live.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(live.page.data.vm.actionsEnabled, true);
  assert.strictEqual(live.page.data.vm.progressAvailable, true);
  assert.strictEqual(live.page.data.vm.projectionState, "live");
  assert.strictEqual(live.calls.cacheWrites.length, 1, "only a complete live snapshot may enter cache");

  var stale = loadLearn({
    cached: {
      homeDashboard: validDashboard({
        mode: "learn_next",
        source_authority: "pack_lifecycle_projection",
        source_ref: "A01",
        reason: "cached",
      }),
      report: validReport(1),
      lessons: {
        lessons: [{ pack_id: "A01", title: "缓存站" }],
        pack_universe: 41,
        teaching_topic_universe: 40,
        teaching_points: [{ pack_id: "A01" }],
      },
    },
  });
  stale.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(stale.page.data.vm.projectionState, "stale");
  assert.strictEqual(stale.page.data.vm.actionsEnabled, false, "stale task identities must not be clickable");
  assert.strictEqual(stale.page.data.vm.progressAvailable, true, "complete stale stats remain displayable");
  assert.strictEqual(stale.page.data.vm.packUniverse, 40, "cached user route must keep the formal 40-station denominator");
  assert.strictEqual(stale.calls.cacheWrites.length, 0, "failed refresh must not refresh cache age");

  var invalid200 = loadLearn({
    dashboard: Promise.resolve({}),
    report: Promise.resolve({}),
  });
  invalid200.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(invalid200.page.data.vm.projectionState, "partial");
  assert.strictEqual(invalid200.page.data.vm.actionsEnabled, false);
  assert.strictEqual(invalid200.page.data.vm.progressAvailable, false);
  assert.strictEqual(invalid200.page.data.vm.taskCard, null);
  assert.strictEqual(invalid200.page.data.vm.litCount, 0, "internal zero may exist but UI is gated unknown");
  assert.strictEqual(invalid200.calls.cacheWrites.length, 0);

  var invalidLessons = loadLearn({
    lessons: Promise.resolve({}),
    dashboard: Promise.resolve(validDashboard()),
    report: Promise.resolve(validReport(0)),
  });
  invalidLessons.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(
    invalidLessons.page.data.supplyError,
    "教学资源加载失败，请检查登录或网络后重试",
    "HTTP 200 with an invalid lessons payload is an authority failure",
  );

  var invalidCache = loadLearn({
    cached: { homeDashboard: {}, report: {}, lessons: {} },
  });
  invalidCache.page.onLoad({});
  await flushPromises();
  await flushPromises();
  assert.strictEqual(invalidCache.page.data.vm.projectionState, "partial");
  assert.strictEqual(invalidCache.page.data.vm.actionsEnabled, false);

  var wxml = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.wxml"),
    "utf8",
  );
  assert(wxml.indexOf("不是微课未上线") >= 0);
  assert(wxml.indexOf('bindtap="retrySupply"') >= 0);
  assert(wxml.indexOf('<view class="lr-status-row" wx:if="{{!supplyError}}">') >= 0);
  assert(
    wxml.indexOf("!supplyError && vm.taskAuthorityAvailable && !vm.reviewCard") >= 0,
    "partial task authority must not become a no-review-due claim",
  );
  console.log("PASS test_learn_supply_authority.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
