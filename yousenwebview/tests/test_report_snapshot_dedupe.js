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
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
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
      navigateTo: function () {},
      reLaunch: function () {},
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

function createPageInstance(pageDef) {
  var page = Object.assign({}, pageDef);
  page.data = Object.assign({}, pageDef.data);
  page.setData = function (patch) {
    this.data = Object.assign({}, this.data, patch);
  };
  page._ensureRadarRendered = function () {};
  return page;
}

(async function main() {
  await run("report onShow should hydrate all state from one snapshot without duplicate assessment reads", async function () {
    var counters = {
      today: 0,
      home: 0,
      assessment: 0,
      mastery: 0,
      wallet: 0,
      radar: 0,
    };
    var pageDef = loadReportPage({
      api: {
        unwrapResponse: function (raw) {
          return raw;
        },
        getTodayProgress: async function () {
          counters.today += 1;
          return { today_done: 6, daily_target: 12, streak_days: 3 };
        },
        getHomeDashboard: async function () {
          counters.home += 1;
          return {
            review: { due_today: 2 },
            mastery: { weak_nodes: [{ name: "防水工程" }] },
            today: { hint: "继续推进防水工程专项训练" },
            study_plan: {
              focus_topic: "防水工程",
              priority_task: "后端下发：先补 3 个待复习点，再做 5 题巩固",
              study_method: "后端下发：先梳理防水工程，再做真题强化，最后回看错题",
              time_budget: "约 18 分钟，先复习后加练",
              coach_note: "后端下发：这是 learner-state 统一生成的作战建议",
            },
            progress_feedback: {
              summary: "后端下发：近 3 天累计完成 18 题，比前 3 天多 6 题",
              insight: "后端下发：系统已经把“防水工程”锁定为当前主攻",
              cards: [
                {
                  label: "近 3 天完成",
                  value: "18题",
                  detail: "比前 3 天多 6 题",
                  tone_class: "tone-good",
                },
                {
                  label: "连续学习",
                  value: "3天",
                  detail: "学习节奏正在形成",
                  tone_class: "tone-good",
                },
              ],
              milestones: [
                {
                  title: "刚完成一次专题梳理",
                  detail: "最近完成了屋面卷材铺贴、节点收头的梳理",
                  tone_class: "tone-good",
                },
              ],
            },
          };
        },
        getAssessmentProfile: async function () {
          counters.assessment += 1;
          return {
            level: "intermediate",
            chapter_mastery: {
              建筑构造: { name: "建筑构造", mastery: 80 },
              防水工程: { name: "防水工程", mastery: 20 },
            },
            diagnostic_feedback: {
              learner_profile: {
                study_tip: "先补防水工程",
              },
            },
          };
        },
        getMasteryDashboard: async function () {
          counters.mastery += 1;
          return {
            overall_mastery: 50,
            groups: [
              {
                name: "需要加强",
                avg_mastery: 20,
                chapters: [{ name: "防水工程", mastery: 20 }],
              },
            ],
            hotspots: [{ name: "防水工程", mastery: 20 }],
            review_summary: { total_due: 2, overdue_count: 1 },
          };
        },
        getWallet: async function () {
          counters.wallet += 1;
          return { balance: 66 };
        },
        getRadarData: async function () {
          counters.radar += 1;
          return {
            dimensions: [{ label: "防水工程", score: 20, value: 0.2 }],
          };
        },
      },
      auth: {
        getUserId: function () {
          return "report-user";
        },
      },
      helpers: {
        getWindowInfo: function () {
          return { statusBarHeight: 20, pixelRatio: 2 };
        },
        isDark: function () {
          return true;
        },
        syncTabBar: function () {},
        vibrate: function () {},
      },
      runtime: {
        getWorkspaceBack: function () {
          return null;
        },
        checkAuth: function (cb) {
          cb();
        },
      },
      route: {
        report: function () {
          return "/packageDeeptutor/pages/report/report";
        },
        billing: function () {
          return "/packageDeeptutor/pages/billing/billing";
        },
        assessment: function () {
          return "/packageDeeptutor/pages/assessment/assessment";
        },
        chat: function () {
          return "/packageDeeptutor/pages/chat/chat";
        },
      },
      flags: {
        ensureFeatureEnabled: function () {
          return true;
        },
        isFeatureEnabled: function () {
          return true;
        },
        shouldShowWorkspaceShell: function () {
          return true;
        },
      },
    });
    var page = createPageInstance(pageDef);

    page.onShow();
    await flushPromises();
    await flushPromises();

    assert(counters.today === 1, "report bootstrap should read today progress once");
    assert(counters.home === 1, "report bootstrap should read homepage dashboard once");
    assert(counters.assessment === 1, "report bootstrap should read assessment profile once");
    assert(counters.mastery === 1, "report bootstrap should read mastery dashboard once");
    assert(counters.wallet === 1, "report bootstrap should read wallet once");
    assert(counters.radar === 0, "positive assessment profile should avoid dedicated radar fallback");
    assert(page.data.userPoints === 66, "report bootstrap should hydrate wallet balance from shared snapshot");
    assert(page.data.learnerLevel === "intermediate", "report bootstrap should hydrate overview from shared snapshot");
    assert(page.data.avgScore === 50, "report bootstrap should hydrate radar from shared assessment snapshot");
    assert(page.data.learnerStageTitle === "中级阶段", "report bootstrap should expose a user-facing learner stage title");
    assert(
      page.data.battlePlan && page.data.battlePlan.focusTopic === "防水工程",
      "report bootstrap should hydrate AI battle plan focus from backend study plan authority",
    );
    assert(
      page.data.battlePlan &&
        page.data.battlePlan.priorityTask === "后端下发：先补 3 个待复习点，再做 5 题巩固",
      "report bootstrap should prefer backend study plan over local battle-plan synthesis",
    );
    assert(
      page.data.battlePlan &&
        page.data.battlePlan.coachNote === "后端下发：这是 learner-state 统一生成的作战建议",
      "report bootstrap should preserve backend coach note from study plan authority",
    );
    assert(
      page.data.progressSummary === "后端下发：近 3 天累计完成 18 题，比前 3 天多 6 题",
      "report bootstrap should prefer backend progress feedback summary over local synthesis",
    );
    assert(
      page.data.progressInsight === "后端下发：系统已经把“防水工程”锁定为当前主攻",
      "report bootstrap should hydrate backend progress feedback insight",
    );
    assert(
      Array.isArray(page.data.progressCards) && page.data.progressCards.length === 2,
      "report bootstrap should prefer backend progress feedback cards over local fallback cards",
    );
    assert(
      Array.isArray(page.data.progressMilestones) && page.data.progressMilestones.length === 1,
      "report bootstrap should hydrate backend progress milestones",
    );
  });

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_report_snapshot_dedupe.js (" + pass + " assertions)");
})();
