// Run: node yousenwebview/tests/test_learn_refresh_race.js
// 红队 A4 收口:学习页供给刷新竞态。
// 1) 单调 request epoch:乱序到达的旧响应不得覆盖较新投影(旧 true 复活);
// 2) 刷新 in-flight 期间轻练 CTA 禁点(供给可能已撤回,不给绕过窗口);
// 3) 刷新 settle 后恢复可点(不误伤正常路径)。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

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

function loadLearn() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/learn/learn.js"),
    "utf8",
  );
  var pageDef = null;
  var state = { navigations: [], toasts: [], lessons: [], dashboards: [], reports: [] };
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
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
        return { getUserId: function () { return "u1"; }, isLoggedIn: function () { return true; } };
      }
      if (request === "../../utils/runtime") return { redirectToLogin: function () {} };
      if (request === "../../utils/first-run-entry") {
        return { getState: function () { return { state: "hidden", checkpoint: null, pending: null }; } };
      }
      if (request === "../../utils/helpers") return { syncTabBar: function () {} };
      if (request === "../../utils/flags") return { shouldShowWorkspaceShell: function () { return true; } };
      if (request === "../../utils/route") {
        return { learn: function () { return "/learn"; }, resolve: function (v) { return "/" + v; } };
      }
      if (request === "../../utils/learn-view-model") {
        return {
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
              todayTask: {
                light_practice_available: true,
                light_practice_visible: true,
                pack_id: "N01",
                task_state: "practice_active",
                training_intent_id: "ti-" + tag,
                // goTodayTask 可路由所需字段(复现二轮 A4:主任务/复习卡旧身份导航)
                action_kind: "retest",
                practice_kind: "retest",
                mode: "forward",
                probe_id: "",
              },
            };
          },
        };
      }
      if (request === "../../utils/surface-telemetry") {
        return { trackModuleView: function () {}, trackModuleExit: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () { return { statusBarHeight: 44 }; },
      navigateTo: function (p) { state.navigations.push(p.url); },
      showToast: function (p) { state.toasts.push(p.title); },
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, { filename: "learn.js" });
  var page = { data: Object.assign({}, pageDef.data || {}) };
  page.setData = function (next) { this.data = Object.assign({}, this.data, next || {}); };
  Object.keys(pageDef).forEach(function (k) { if (k !== "data") page[k] = pageDef[k]; });
  return { page: page, state: state };
}

(async function main() {
  // ── 1) 乱序响应:较旧 load 的响应最后到达,不得覆盖最新投影 ──
  var t1 = loadLearn();
  t1.page.onLoad({}); // load #1(挂起)
  await flush();
  t1.page._load(); // load #2(刷新)
  await flush();
  // load #2 先完成
  t1.state.lessons[1].resolve({ tag: "fresh", lessons: [] });
  t1.state.dashboards[1].resolve({});
  t1.state.reports[1].resolve({});
  await flush();
  await flush();
  assert.strictEqual(t1.page.data.vm.marker, "fresh", "latest load must project");
  // load #1 姗姗来迟
  t1.state.lessons[0].resolve({ tag: "stale", lessons: [] });
  t1.state.dashboards[0].resolve({});
  t1.state.reports[0].resolve({});
  await flush();
  await flush();
  assert.strictEqual(
    t1.page.data.vm.marker,
    "fresh",
    "stale out-of-order response must not overwrite the latest projection",
  );

  // ── 2) 刷新 in-flight:轻练 CTA 与主任务/复习卡(goTodayTask)一律禁点 ──
  // 二轮红队 A4:旧 VM 的 review_due/probe 或 practice_active 身份在刷新窗口内
  // 仍可被主按钮/复习卡按旧 pack/probe 导航——两个入口都必须挡在 _refreshing 后面。
  var t2 = loadLearn();
  t2.page.onLoad({});
  t2.state.lessons[0].resolve({ tag: "first", lessons: [] });
  t2.state.dashboards[0].resolve({});
  t2.state.reports[0].resolve({});
  await flush();
  await flush();
  assert.strictEqual(t2.page.data.vm.marker, "first");
  t2.page._load(); // 刷新开始,尚未 settle
  await flush();
  var navBefore = t2.state.navigations.length;
  t2.page.goLightPractice();
  assert.strictEqual(
    t2.state.navigations.length,
    navBefore,
    "light practice must be blocked while a supply refresh is in flight",
  );
  t2.page.goTodayTask();
  assert.strictEqual(
    t2.state.navigations.length,
    navBefore,
    "primary task button / review card must not navigate on a stale identity mid-refresh",
  );

  // ── 3) 刷新 settle 后两个入口都恢复 ──
  t2.state.lessons[1].resolve({ tag: "second", lessons: [] });
  t2.state.dashboards[1].resolve({});
  t2.state.reports[1].resolve({});
  await flush();
  await flush();
  t2.page.goLightPractice();
  assert.strictEqual(
    t2.state.navigations.length,
    navBefore + 1,
    "light practice must work again after the refresh settles",
  );
  t2.page.goTodayTask();
  assert.strictEqual(
    t2.state.navigations.length,
    navBefore + 2,
    "primary task navigation must work again after the refresh settles",
  );

  console.log("PASS test_learn_refresh_race.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
