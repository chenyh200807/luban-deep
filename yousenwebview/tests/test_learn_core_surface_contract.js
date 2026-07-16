// Run: node yousenwebview/tests/test_learn_core_surface_contract.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

function read(rel) {
  return fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
}

var learnJs = read("packageDeeptutor/pages/learn/learn.js");
var learnWxml = read("packageDeeptutor/pages/learn/learn.wxml");
var learnVm = read("packageDeeptutor/utils/learn-view-model.js");

assert(learnWxml.indexOf('bindtap="goTodayTask"') >= 0, "today task must own the primary action");
assert(
  learnWxml.indexOf("firstRunState === 'hidden' && !supplyError && vm.todayTask") >= 0,
  "first-run and canonical today task must be mutually exclusive",
);
assert(
  learnWxml.indexOf("!supplyError && firstRunState !== 'hidden'") >= 0 &&
    (learnWxml.match(/bindtap="openFirstRun"/g) || []).length === 1,
  "first-run state must expose exactly one primary journey CTA",
);
// 10a改:复习卡是到期状态视图,点击必须复用任务卡同一 handler(goTodayTask),
// 因此 canonical 路由入口恰好 2 处(任务卡主按钮 + 复习卡),不允许更多。
assert.strictEqual(
  (learnWxml.match(/bindtap="goTodayTask"/g) || []).length,
  2,
  "task button and review card must share the single canonical route handler",
);
assert(
  learnWxml.indexOf("vm.reviewCard") >= 0,
  "review card must be gated on the view-model reviewCard (next_step adjudication view)",
);
assert.strictEqual(learnWxml.indexOf("goSwitchPractice"), -1, "learning home must not expose a legacy switch-practice CTA");
assert.strictEqual(learnWxml.indexOf("goReview"), -1, "review card must not own a second route handler");
assert.strictEqual(learnWxml.indexOf("vm.dueCount"), -1, "due count must come from vm.reviewCard, never a free-floating field");
assert.strictEqual(learnWxml.indexOf("mastery_score"), -1, "learning home must not render pseudo-precise mastery");
assert.strictEqual(learnWxml.indexOf("已掌握"), -1, "learning home copy must never claim 已掌握");
assert.strictEqual(learnVm.indexOf("已掌握"), -1, "view model copy must never claim 已掌握");
// 轻练旁按钮:必须存在,且供给未接通时 learn.js 走诚实空态(禁 dead click)
assert.strictEqual(
  (learnWxml.match(/bindtap="goLightPractice"/g) || []).length,
  1,
  "task card must expose exactly one light-practice side button",
);
assert(learnJs.indexOf("快练准备中") >= 0, "light practice must degrade to an honest empty-state toast");
// 旅程轨道:6 步硬编码于 view-model,禁不存在的步骤
["半写", "填空"].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "journey must not fabricate a nonexistent step: " + needle);
});
assert(
  learnWxml.indexOf("近 3 天有效作答") >= 0 &&
    learnWxml.indexOf("{{vm.stats.recent_practice || 0}} 道") >= 0,
  "recent_three_done must be labeled as answer count rather than practice sessions",
);

["goReview", "goSwitchPractice", "goSeethrough", "route.lubanReview", "getLubanSeethroughLibrary", "F16"].forEach(function (needle) {
  assert.strictEqual(learnJs.indexOf(needle), -1, "learn.js must not retain first-class legacy surface: " + needle);
});
["secondaryCta", "mastery_score", "_seethroughSet", '"seethrough"'].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "view model must not retain legacy decision: " + needle);
});

var pageDef = null;
var navigations = [];
var toasts = [];
vm.runInNewContext(learnJs, {
  console: console,
  Promise: Promise,
  require: function (request) {
    if (request === "../../utils/route") {
      return {
        lubanStation: function (packId) { return "/station?pack_id=" + packId; },
      };
    }
    if (request === "../../utils/learn-view-model") return { buildLearnViewModel: function () { return {}; } };
    return {};
  },
  wx: {
    navigateTo: function (payload) { navigations.push(payload.url); },
    showToast: function (payload) { toasts.push(payload.title); },
  },
  Page: function (definition) { pageDef = definition; },
}, { filename: "packageDeeptutor/pages/learn/learn.js" });

function navigate(task) {
  var page = {
    data: { vm: { todayTask: task } },
    _navTo: pageDef._navTo,
  };
  pageDef.goTodayTask.call(page);
  return navigations.pop();
}

assert.strictEqual(
  navigate({ action_kind: "lesson", pack_id: "N01" }),
  "/station?pack_id=N01",
  "recommended learning task should enter the generic station route",
);
assert.strictEqual(
  navigate({ action_kind: "retest", practice_kind: "retest", pack_id: "N01", mode: "review", probe_id: "probe-1" }),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=N01&mode=review&training_intent_id=&probe_id=probe-1",
  "due task should enter the shared retest route in review mode",
);
assert.strictEqual(
  navigate({ action_kind: "retest", practice_kind: "retest", pack_id: "S05", mode: "forward", training_intent_id: "intent-1" }),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=S05&mode=forward&training_intent_id=intent-1&probe_id=",
  "post-lesson task should enter the same retest route in forward mode",
);

// ── 轻练旁按钮:供给真值路由 forward;未接通→诚实 toast,零导航 ──
function lightPractice(task) {
  var page = {
    data: { vm: { todayTask: task } },
    _navTo: pageDef._navTo,
  };
  pageDef.goLightPractice.call(page);
}

lightPractice({ light_practice_available: true, pack_id: "N01", task_state: "practice_active", training_intent_id: "intent-9" });
assert.strictEqual(
  navigations.pop(),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=N01&mode=forward&training_intent_id=intent-9&probe_id=",
  "light practice with supply should enter the shared retest route in forward mode",
);
lightPractice({ light_practice_available: true, pack_id: "N01", task_state: "review_due" });
assert.strictEqual(
  navigations.pop(),
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=N01&mode=forward&training_intent_id=&probe_id=",
  "light practice from a review task must not smuggle the probe identity into forward mode",
);
var navCountBefore = navigations.length;
lightPractice({ light_practice_available: false, pack_id: "N01", task_state: "learn_next" });
assert.strictEqual(navigations.length, navCountBefore, "no supply must mean no navigation (no dead click)");
assert.strictEqual(toasts.pop(), "快练准备中", "no supply must surface the honest preparing toast");

console.log("PASS test_learn_core_surface_contract.js");
