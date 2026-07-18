// Run: node yousenwebview/tests/test_learn_snapshot_swr.js
// 学习页快照 SWR(stale-while-revalidate)收口——统一策略:缓存秒渲染+始终静默刷新
// (fresh-skip 门被对抗 review 证伪后删除,本文件锚定新契约):
// (a) 30min 内快照 → onLoad 不等网络,立即渲染整页 vm(loading 直接落地),
//     且**仍发起**三路刷新请求(revalidate 无条件);
// (b) 新鲜快照(1s)同样不跳过网络——不存在任何"fresh 即跳过"路径;
// (c) 刷新成功后经唯一 builder(真 report-snapshot 模块)组装并
//     reportCache.writeIfFresher(带发起时刻);report 无效(空对象)builder
//     返 null 不写;
// (d) 用户中途切换(发起后 getUserId 变化)→ 网络成功也不写缓存(写侧守卫);
// (e) _shownOnce:onLoad 后首个 onShow 不重复加载,后续 onShow 重新加载。
// 红线:不动 test_learn_refresh_race.js 的 epoch 守卫语义,本文件只加 SWR 维度。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

// 写侧校验用真 builder(与 learn.js 生产 require 同一模块):空 report 过不了
// isLearningReportPayload 校验 → 不写,这条 fail-closed 语义必须测真件不测 stub。
var realReportSnapshot = require("../packageDeeptutor/utils/report-snapshot");

function deferred() {
  var d = {};
  d.promise = new Promise(function (resolve, reject) {
    d.resolve = resolve;
    d.reject = reject;
  });
  return d;
}
function flush() {
  return new Promise(function (r) { setTimeout(r, 0); });
}

// 过 isLearningReportPayload 校验的最小合法 learning report payload
function validReport(userId) {
  return {
    user_id: userId,
    schema_version: 2,
    authority: { read_model: "learning-report-read-model" },
    overview: {},
    freshness: {},
    learning_brain: {},
  };
}

function validDashboard(tag) {
  return {
    tag: tag || "dashboard",
    learner_settings: {},
    review: {},
    mastery: {},
    today: {},
    next_step: {
      mode: "learn_next",
      source_authority: "home-next-step-projection",
      source_ref: "pack:c04",
      reason: "canonical next station",
      target_pack_id: "c04",
    },
  };
}

function validLessons(tag) {
  return {
    tag: tag,
    pack_universe: 1,
    lessons: [{ pack_id: "c04" }],
  };
}

function cachedSnapshotFixture() {
  return {
    report: validReport("u1"),
    homeDashboard: validDashboard("cached"),
    lessons: validLessons("cached"),
  };
}

function loadLearn(options) {
  var opts = options || {};
  var cacheFixture = opts.cache || null; // { snapshot, ageMs } | null
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.js"),
    "utf8",
  );
  var pageDef = null;
  var state = {
    navigations: [], toasts: [],
    lessons: [], dashboards: [], reports: [],
    reads: [], writes: [],
    currentUserId: "u1", // 可变:模拟用户中途切换(写侧守卫用例)
  };
  var reportCacheStub = {
    SNAPSHOT_MAX_AGE_MS: 30 * 60 * 1000,
    read: function (userId, maxAgeMs) {
      state.reads.push({ userId: userId, maxAgeMs: maxAgeMs });
      if (!cacheFixture) return null;
      if (cacheFixture.ageMs > Number(maxAgeMs || 0)) return null;
      return cacheFixture.snapshot;
    },
    writeIfFresher: function (userId, snapshot, fetchStartedAt) {
      state.writes.push({ userId: userId, snapshot: snapshot, fetchStartedAt: fetchStartedAt });
      return true;
    },
  };
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    Date: Date,
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getLubanLessons: function () { var d = deferred(); state.lessons.push(d); return d.promise; },
          getHomeDashboard: function () { var d = deferred(); state.dashboards.push(d); return d.promise; },
          getLearningReport: function () { var d = deferred(); state.reports.push(d); return d.promise; },
          unwrapResponse: function (v) { return v; },
          describeRequestError: function (_e, fb) { return fb; },
        };
      }
      if (request === "../../utils/auth") {
        return {
          getUserId: function () { return state.currentUserId; },
          isLoggedIn: function () { return true; },
        };
      }
      if (request === "../../utils/runtime") return { redirectToLogin: function () {} };
      if (request === "../../utils/first-run-entry") {
        return { getState: function () { return { state: "hidden", checkpoint: null, pending: null }; } };
      }
      if (request === "../../utils/helpers") return { isDarkOr: function () { return false; }, isDark: function () { return false; }, vibrate: function () {}, syncTabBar: function () {} };
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/route") {
        return { learn: function () { return "/learn"; }, resolve: function (v) { return "/" + v; } };
      }
      if (request === "../../utils/learn-view-model") {
        return {
          // marker = lessons.tag:同时服务缓存 hydrate(cached.lessons)
          // 与网络成功路径(res[2]),可分辨投影来源。
          buildLearnViewModel: function (args) {
            var tag = (args && args.lessons && args.lessons.tag) || "";
            return {
              hasSupply: !!tag,
              marker: tag,
              nextStation: null,
              posters: [],
              routePreview: [],
              stats: {},
              todayProgress: {},
              todayTask: null,
            };
          },
        };
      }
      if (request === "../../utils/report-cache") return reportCacheStub;
      if (request === "../../utils/report-snapshot") return realReportSnapshot;
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
      navigateTo: function (p) { state.navigations.push(p.url); },
      showToast: function (p) { state.toasts.push(p.title); },
      stopPullDownRefresh: function () {},
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, { filename: "learn.js" });
  var page = { data: Object.assign({}, pageDef.data || {}) };
  page.setData = function (next) { this.data = Object.assign({}, this.data, next || {}); };
  Object.keys(pageDef).forEach(function (k) { if (k !== "data") page[k] = pageDef[k]; });
  return { page: page, state: state };
}

function requestCount(state) {
  return state.lessons.length + state.dashboards.length + state.reports.length;
}

(async function main() {
  // ── (a) 陈旧但可用的快照(2min):onLoad 同步秒渲染,不等任何网络响应;
  //        同时仍发三路刷新请求(revalidate 半边)──
  var beforeLoadTs = Date.now();
  var ta = loadLearn({ cache: { snapshot: cachedSnapshotFixture(), ageMs: 2 * 60 * 1000 } });
  ta.page.onLoad({});
  // onLoad 返回即断言:没有任何 deferred 被 resolve,vm 必须已经在屏
  assert.strictEqual(ta.page.data.vm && ta.page.data.vm.marker, "cached", "cached snapshot must hydrate vm synchronously");
  assert.strictEqual(ta.page.data.loading, false, "cached hydrate must clear loading before network settles");
  assert.strictEqual(ta.page.data.supplyError, "", "cached hydrate must clear supplyError");
  assert.strictEqual(requestCount(ta.state), 3, "stale snapshot must still trigger the three refresh requests");
  assert.strictEqual(ta.state.reads[0].userId, "u1", "cache read must be owner-scoped to the current user");
  assert.strictEqual(ta.state.reads[0].maxAgeMs, 30 * 60 * 1000, "cache read must use SNAPSHOT_MAX_AGE_MS");
  // lessons 快通道在已有 vm 时不做部分回退(既有语义,顺带守住)
  ta.state.lessons[0].resolve(validLessons("fastlane"));
  await flush();
  assert.strictEqual(ta.page.data.vm.marker, "cached", "lessons fast lane must not partially overwrite a hydrated vm");

  // ── (c) hydrate 后刷新成功:写侧经真 builder 组装,writeIfFresher 带发起时刻 ──
  ta.state.dashboards[0].resolve(validDashboard("live"));
  ta.state.reports[0].resolve(validReport("u1"));
  await flush();
  await flush();
  assert.strictEqual(ta.page.data.vm.marker, "fastlane", "network success must overwrite the cached projection");
  assert.strictEqual(ta.state.writes.length, 1, "successful refresh must write the unified snapshot exactly once");
  assert.strictEqual(ta.state.writes[0].userId, "u1", "snapshot write must be owner-scoped to the user who started the fetch");
  assert.strictEqual(ta.state.writes[0].snapshot.report.user_id, "u1", "written snapshot must embed the raw report payload");
  assert.strictEqual(ta.state.writes[0].snapshot.lessons.tag, "fastlane", "written snapshot must embed the raw lessons payload");
  var startedAt = ta.state.writes[0].fetchStartedAt;
  assert.ok(
    typeof startedAt === "number" && startedAt >= beforeLoadTs && startedAt <= Date.now(),
    "writeIfFresher must receive the fetch start timestamp (write-order guard input)",
  );

  // ── (c2) report 无效(unwrap 出空对象):builder fail-closed,不写缓存 ──
  var tc = loadLearn({ cache: null });
  tc.page.onLoad({});
  assert.strictEqual(tc.page.data.loading, true, "no cache → loading stays until network settles");
  tc.state.lessons[0].resolve(validLessons("net"));
  tc.state.dashboards[0].resolve({});
  tc.state.reports[0].resolve({}); // 空对象过不了 isLearningReportPayload
  await flush();
  await flush();
  assert.strictEqual(tc.page.data.vm.marker, "net", "network projection still lands without cache");
  assert.strictEqual(tc.state.writes.length, 0, "invalid report must never be written to the snapshot cache");

  // ── (b) 新鲜快照(1s):照样渲染,且**不跳过**三路网络刷新(fresh-skip 已删) ──
  var tb = loadLearn({ cache: { snapshot: cachedSnapshotFixture(), ageMs: 1000 } });
  tb.page.onLoad({});
  assert.strictEqual(tb.page.data.vm && tb.page.data.vm.marker, "cached", "fresh snapshot must hydrate vm");
  assert.strictEqual(
    requestCount(tb.state),
    3,
    "fresh snapshot must NOT skip the network — always silently revalidate",
  );
  // ── (e) _shownOnce:onLoad 后首个 onShow 不重复加载 ──
  tb.page.onShow();
  await flush();
  assert.strictEqual(requestCount(tb.state), 3, "first onShow right after onLoad must not re-trigger a load");
  // 后续 onShow(从站点/练习返回)= 无参 _load 重新加载
  tb.page.onShow();
  await flush();
  assert.strictEqual(requestCount(tb.state), 6, "subsequent onShow must re-load (always silent refresh, no force plumbing)");
  tb.state.lessons[1].resolve(validLessons("after-action"));
  tb.state.dashboards[1].resolve(validDashboard("after-action"));
  tb.state.reports[1].resolve(validReport("u1"));
  await flush();
  await flush();
  assert.strictEqual(tb.page.data.vm.marker, "after-action", "post-action refresh must land the new projection");
  assert.strictEqual(tb.state.writes.length, 1, "post-action refresh success must write the snapshot");

  // ── (d) 用户中途切换:发起后 getUserId 变化 → 网络成功也不写缓存 ──
  var td = loadLearn({ cache: { snapshot: cachedSnapshotFixture(), ageMs: 1000 } });
  td.page.onLoad({});
  assert.strictEqual(requestCount(td.state), 3, "load must always fire the three requests");
  td.state.currentUserId = "u2"; // 在途期间用户切换(孤儿响应的用户维)
  td.state.lessons[0].resolve(validLessons("orphan"));
  td.state.dashboards[0].resolve(validDashboard("orphan"));
  td.state.reports[0].resolve(validReport("u1"));
  await flush();
  await flush();
  assert.strictEqual(
    td.state.writes.length,
    0,
    "a fetch started as u1 must not write the cache after the user switched to u2",
  );

  console.log("PASS test_learn_snapshot_swr.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
