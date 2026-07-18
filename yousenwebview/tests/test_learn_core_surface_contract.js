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
// 10a fallback:任务卡唯一渲染源 = vm.taskCard(= todayTask || browseTask),
// 让 day-0/首跑未完成/后端未部署等态下页面仍长成 10a 定稿(不塌成 hero+海报)。
// 门不再挂 firstRunState(首跑卡仍在上方=第一视觉);禁掌握百分比不变。
assert(
  learnWxml.indexOf("!supplyError && vm.taskCard") >= 0,
  "task card must render from the single vm.taskCard source in any state (todayTask || browseTask)",
);
assert.strictEqual(
  learnWxml.indexOf("vm.todayTask"),
  -1,
  "task card must not bind vm.todayTask directly; render source is the merged vm.taskCard",
);
assert(
  learnWxml.indexOf("!supplyError && firstRunState !== 'hidden'") >= 0 &&
    (learnWxml.match(/bindtap="openFirstRun"/g) || []).length === 1,
  "first-run state must expose exactly one primary journey CTA (first-run card stays as first visual)",
);
// browse 兜底卡不得声称"今日任务":kicker 由 view-model 派生("从这里开始"),
// wxml 不再硬编码"今天最该完成"(那是真今日任务卡的 kicker,现由数据驱动)。
assert(
  learnWxml.indexOf("{{vm.taskCard.kicker}}") >= 0,
  "task card kicker must be data-driven so browse never claims 今日任务",
);
assert(learnVm.indexOf("从这里开始") >= 0, "browse task must use a 推荐起点 kicker, not a 今日任务 claim");
// 复习模块无到期时渲染诚实空态(10a改),而非整块消失。
assert(
  learnWxml.indexOf("!supplyError && !vm.reviewCard") >= 0 &&
    learnWxml.indexOf("暂无到期考点") >= 0,
  "review module must render an honest empty state when nothing is due (never vanish)",
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
// 红队 A2:轻练按钮在 review_due(到期验证优先)必须隐藏,不给绕开路径;
// 可见性由 view-model 单点裁决(light_practice_visible),页面/wxml 不重判。
assert(
  learnWxml.indexOf('wx:if="{{vm.taskCard.light_practice_visible}}"') >= 0,
  "light practice button visibility must be gated by the view-model (hidden under review_due)",
);
// 旅程轨道:6 步硬编码于 view-model,禁不存在的步骤
["半写", "填空"].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "journey must not fabricate a nonexistent step: " + needle);
});
// 红队 A1:前端无逐步完成证据 → 禁 done 勾/进度线跨未完成节点/写死复习日程
assert.strictEqual(learnWxml.indexOf("lr-jline-fill"), -1, "journey must not draw a progress line across unverified steps");
assert.strictEqual(learnWxml.indexOf("lr-jnode-check"), -1, "journey must not render done checkmarks without completion evidence");
["明日验证", "3 日抽查"].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "journey copy must not hardcode a review schedule: " + needle);
});
assert.strictEqual(learnVm.indexOf("昨天的"), -1, "review copy must not claim 昨天 (cycle length is server-owned)");
// 10a整页改版:标签随设计稿改「近 3 天练习」,但单位必须仍是「道」(作答数)——
// recent_three_done 是作答计数,禁用「次」冒充练习会话数(合同意图不变)。
assert(
  learnWxml.indexOf("近 3 天练习") >= 0 &&
    learnWxml.indexOf("{{vm.stats.recent_practice || 0}} 道") >= 0,
  "recent_three_done must be labeled as answer count rather than practice sessions",
);
// 三指标卡③已验证考点:只许消费 view-model 的 mastered 事实计数
// (verified_stations,terminal 证据),禁前端自算/禁掌握百分比。
assert(
  learnWxml.indexOf("已验证考点") >= 0 &&
    learnWxml.indexOf("{{vm.stats.verified_stations || 0}} 站") >= 0,
  "verified stations metric must project vm.stats.verified_stations (mastered fact count)",
);

["goReview", "goSwitchPractice", "goSeethrough", "route.lubanReview", "getLubanSeethroughLibrary", "F16"].forEach(function (needle) {
  assert.strictEqual(learnJs.indexOf(needle), -1, "learn.js must not retain first-class legacy surface: " + needle);
});
["secondaryCta", "mastery_score", "_seethroughSet", '"seethrough"'].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "view model must not retain legacy decision: " + needle);
});

// ── owner 2026-07-18 两卡分离:练题卡=纯练题(禁学习语义);视频卡=学习动作+旅程条 ──
// 先剥离注释(注释里为文档目的会提到「进站学习」等词),只对真实 markup 做块级断言。
var learnWxmlNoComments = learnWxml.replace(/<!--[\s\S]*?-->/g, "");
var practiceStart = learnWxmlNoComments.indexOf('class="lr-task pk-card');
var practiceEnd = learnWxmlNoComments.indexOf('class="lr-lesson pk-card');
assert(practiceStart >= 0 && practiceEnd > practiceStart, "practice card block must be identifiable");
var practiceMarkup = learnWxmlNoComments.slice(practiceStart, practiceEnd);
["进站学习", "先看讲解", "先看这一站", "继续学习"].forEach(function (needle) {
  assert.strictEqual(
    practiceMarkup.indexOf(needle),
    -1,
    "practice card must not carry any learning-mode semantics: " + needle,
  );
});
assert.strictEqual(
  practiceMarkup.indexOf("这一站会带你走完"),
  -1,
  "the station journey narrative must move out of the practice card",
);
assert.strictEqual(
  practiceMarkup.indexOf("vm.taskCard.journey"),
  -1,
  "practice card must not bind a journey any more (journey lives on the video card)",
);
assert(
  practiceMarkup.indexOf("vm.taskCard.redirectNote") >= 0,
  "practice card must honestly label the redirect target station name",
);

var lessonStart = practiceEnd;
var lessonEnd = learnWxmlNoComments.indexOf('class="lr-rvc pk-card');
assert(lessonStart >= 0 && lessonEnd > lessonStart, "video learning card block must be identifiable");
var lessonMarkup = learnWxmlNoComments.slice(lessonStart, lessonEnd);
assert(
  lessonMarkup.indexOf('bindtap="goLesson"') >= 0 && lessonMarkup.indexOf("进站学习") >= 0,
  "video learning card must own the 进站学习 action (goLesson)",
);
assert(
  lessonMarkup.indexOf("这一站会带你走完") >= 0 && lessonMarkup.indexOf("vm.nextStation.journey") >= 0,
  "station journey narrative lives on the video card, fed by vm.nextStation.journey",
);
// goLesson(进站学习)只许出现在视频卡,练题卡永不承担学习路由。
assert.strictEqual(
  practiceMarkup.indexOf("goLesson"),
  -1,
  "practice card must never bind the lesson route handler",
);
assert(
  (learnWxml.match(/bindtap="goLesson"/g) || []).length >= 1,
  "video card owns the lesson route (stage tap + 进站学习 button share goLesson)",
);
// 供给真值单点红线:redirect 目标仍走 _practiceKindFor/_firstRetestStation(禁第二处方)
assert(
  learnVm.indexOf("_firstRetestStation") >= 0 && learnVm.indexOf("_practiceKindFor") >= 0,
  "redirect target must be resolved from the single supply-truth source, no second prescription",
);

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
    data: { vm: { taskCard: task } },
    _navTo: pageDef._navTo,
  };
  pageDef.goTodayTask.call(page);
  return navigations.pop();
}

// owner 2026-07-18 两卡分离:置顶练题卡永远练题——goTodayTask 只转发 retest,
// 永不进站学习(lesson 动作已归视频卡 goLesson)。
var navCountLesson = navigations.length;
navigate({ action_kind: "lesson", pack_id: "N01" });
assert.strictEqual(
  navigations.length,
  navCountLesson,
  "practice card handler must never route a lesson (进站学习 belongs to the video card)",
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

// 视频学习卡「进站学习」= goLesson,路由 vm.nextStation(与练题卡 redirect 目标解耦)。
function enterStation(station) {
  var page = {
    data: { vm: { nextStation: station } },
    _navTo: pageDef._navTo,
  };
  pageDef.goLesson.call(page);
  return navigations.pop();
}
assert.strictEqual(
  enterStation({ pack_id: "N01", card_hosted: true }),
  "/station?pack_id=N01",
  "video card 进站学习 (goLesson) enters the generic station route",
);
var navCountUnhosted = navigations.length;
enterStation({ pack_id: "N01", card_hosted: false });
assert.strictEqual(navigations.length, navCountUnhosted, "unhosted station must not navigate (honest toast instead)");
assert.strictEqual(toasts.pop(), "这一站微课即将开通", "unhosted lesson click explains 微课即将开通");

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
// 红队 A2:review_due 下即使残留 stale 可用旗标,页面守卫也必须拒绝
// forward 旁路(否则可绕开到期验证并重开 fresh cycle 清掉 review streak)。
var navBeforeReview = navigations.length;
lightPractice({ light_practice_available: true, pack_id: "N01", task_state: "review_due" });
assert.strictEqual(
  navigations.length,
  navBeforeReview,
  "review_due must never offer a probe-less forward bypass around due verification",
);
assert.strictEqual(toasts.pop(), "先完成今天的到期验证", "review_due light-practice click must explain the due-first rule");
var navCountBefore = navigations.length;
lightPractice({ light_practice_available: false, pack_id: "N01", task_state: "learn_next" });
assert.strictEqual(navigations.length, navCountBefore, "no supply must mean no navigation (no dead click)");
assert.strictEqual(toasts.pop(), "快练准备中", "no supply must surface the honest preparing toast");

console.log("PASS test_learn_core_surface_contract.js");
