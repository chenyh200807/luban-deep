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
  learnWxml.indexOf("!supplyError && vm.taskAuthorityAvailable && !vm.reviewCard") >= 0 &&
    learnWxml.indexOf("暂无到期考点") >= 0,
  "review empty state requires known task authority; partial reads must stay unknown",
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
// 六步完成态只许消费服务端 projection；仍禁前端自画跨步进度线与伪造勾选。
assert.strictEqual(learnWxml.indexOf("lr-jline-fill"), -1, "journey must not draw a progress line across unverified steps");
assert.strictEqual(learnWxml.indexOf("lr-jnode-check"), -1, "journey must not render done checkmarks without completion evidence");
// 六步旅程校验收权到共享 util(learn 页与学情页单一权威,禁第二套校验);
// canonical authority 字符串随之落在 station-journey.js,learn-view-model 只 require 它。
var stationJourneyVm = read("packageDeeptutor/utils/station-journey.js");
assert(stationJourneyVm.indexOf("station_journey_projection.read_model") >= 0, "journey must consume the canonical server projection (shared single authority)");
assert(learnVm.indexOf('require("./station-journey")') >= 0, "learn view-model must consume the shared journey authority, not a second validator");
assert.strictEqual(learnVm.indexOf("_journeyFor"), -1, "next_step modes must not infer six-step completion");
assert(
  learnWxml.indexOf("{{vm.nextStation.journey.statusText}}") >= 0 &&
    learnWxml.indexOf("{{vm.nextStation.journey.currentIndex}}/{{vm.nextStation.journey.total}}") < 0,
  "unknown journey must render an honest status instead of a fake 0/6 position",
);

// ── owner 2026-07-18 对齐第10轮定稿 10a:收回 #512/#514 两卡拆分 ──
// 站点身份与学习旅程回到同一张「一体化站点卡」(lr-lesson):头部行(下一站·pack +
// 站名 + chip + 折叠箭头) + 舞台 + 路线/课程架 + 旅程条 + 为什么先走这一站。
// 今日任务卡(lr-task)是专门练题模块,排在站点卡"下方"。
var learnWxmlNoComments = learnWxml.replace(/<!--[\s\S]*?-->/g, "");
// 一体化站点卡必须重新拥有头部行与站点身份(定稿 ①头部行)。
assert(
  learnWxmlNoComments.indexOf("lr-lesson-head") >= 0,
  "integrated station card must render the header row (下一站 · pack + 站名 + chip)",
);
assert(
  learnWxmlNoComments.indexOf("vm.nextStation.title") >= 0,
  "station name must appear in the integrated station card header (per 10th-final 10a)",
);
assert(
  learnWxmlNoComments.indexOf("下一站") >= 0,
  "integrated station card must announce 下一站 station identity",
);
// 头部行折叠箭头(定稿 ①):整卡可折叠,handler=toggleStation,状态=stationOpen。
assert(
  learnWxml.indexOf('bindtap="toggleStation"') >= 0 &&
    learnWxml.indexOf("stationOpen") >= 0 &&
    learnJs.indexOf("toggleStation") >= 0,
  "station card header must be collapsible via toggleStation/stationOpen",
);
// 旅程条在站点卡:数据源=vm.nextStation.journey;任务卡不再携带 journey。
assert(
  learnWxmlNoComments.indexOf("vm.nextStation.journey") >= 0 &&
    learnWxmlNoComments.indexOf("这一站会带你走完") >= 0,
  "station journey track must render on the integrated station card from vm.nextStation.journey",
);
assert.strictEqual(
  learnWxmlNoComments.indexOf("vm.taskCard.journey"),
  -1,
  "practice/task card must not bind a journey (it lives on the station card)",
);
assert.strictEqual(
  learnWxmlNoComments.indexOf("lr-journey-ringbox"),
  -1,
  "task card journey ring stays retired (前端不算掌握)",
);
// 定稿站点卡无独立「进站学习」按钮:播放/进站走舞台点击(goLesson)。
assert(
  learnWxmlNoComments.indexOf('bindtap="goLesson"') >= 0,
  "station card stage must own the 进站学习 action via goLesson (tap the stage)",
);
assert.strictEqual(
  learnWxmlNoComments.indexOf("lr-lesson-btn"),
  -1,
  "站点卡不得保留独立「进站学习」按钮(定稿播放走舞台点击)",
);
// 顺序:一体化站点卡在前,今日任务卡在后(定稿 10a)。
var lessonIdx = learnWxmlNoComments.indexOf('class="lr-lesson pk-card');
var taskIdx = learnWxmlNoComments.indexOf('class="lr-task pk-card');
assert(lessonIdx >= 0 && taskIdx >= 0, "both integrated station card and task card must render");
assert(lessonIdx < taskIdx, "integrated station card must precede the task card (10th-final order)");
// 今日任务卡区块(lr-task → 复习卡)不得拥有 goLesson/journey(学习旅程归站点卡)。
var taskBlock = learnWxmlNoComments.slice(
  taskIdx,
  learnWxmlNoComments.indexOf('class="lr-rvc pk-card'),
);
assert(taskBlock.length > 0, "task card block must be delimited before the review card");
assert.strictEqual(
  taskBlock.indexOf("goLesson"),
  -1,
  "task card must not own the lesson route (学习动作归站点卡舞台)",
);
assert.strictEqual(
  taskBlock.indexOf("journey"),
  -1,
  "task card markup must carry no journey remnants",
);
["明日验证", "3 日抽查"].forEach(function (needle) {
  assert.strictEqual(learnVm.indexOf(needle), -1, "journey copy must not hardcode a review schedule: " + needle);
});
assert.strictEqual(learnVm.indexOf("昨天的"), -1, "review copy must not claim 昨天 (cycle length is server-owned)");
// 10a整页改版:标签随设计稿改「近 3 天练习」,但单位必须仍是「道」(作答数)——
// recent_three_done 是作答计数,禁用「次」冒充练习会话数(合同意图不变)。
assert(
  learnWxml.indexOf("近 3 天练习") >= 0 &&
    learnWxml.indexOf("vm.progressAvailable ? vm.stats.recent_practice : '—'") >= 0,
  "recent_three_done must be labeled as answer count rather than practice sessions",
);
// 三指标卡③已验证考点:只许消费 view-model 的 mastered 事实计数
// (verified_stations,terminal 证据),禁前端自算/禁掌握百分比。
assert(
  learnWxml.indexOf("已验证考点") >= 0 &&
    learnWxml.indexOf("vm.progressAvailable ? vm.stats.verified_stations : '—'") >= 0,
  "verified stations metric must project vm.stats.verified_stations (mastered fact count)",
);
assert.strictEqual(learnWxml.indexOf("vm.litCount || 0"), -1, "unknown route progress must not become 0");
assert(learnJs.indexOf("taskAuthorityAvailable: false") >= 0, "partial reads must fail-close task authority");
assert(learnJs.indexOf("actionsEnabled === false") >= 0, "stale/partial actions must be blocked");

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
    data: { vm: { todayTask: task, actionsEnabled: true } },
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
    data: { vm: { todayTask: task, actionsEnabled: true } },
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

// ── 视频学习卡 goLesson:进站学习/舞台播放 → 站点页;card_hosted=false 诚实降级 ──
function enterStation(station) {
  var page = {
    data: { vm: { nextStation: station, actionsEnabled: true } },
    _navTo: pageDef._navTo,
  };
  pageDef.goLesson.call(page);
}
enterStation({ pack_id: "N01", card_hosted: true });
assert.strictEqual(
  navigations.pop(),
  "/station?pack_id=N01",
  "video card 进站学习 (goLesson) must enter the generic station route",
);
var navCountUnhosted = navigations.length;
enterStation({ pack_id: "N01", card_hosted: false });
assert.strictEqual(navigations.length, navCountUnhosted, "unhosted station must not navigate (no dead click)");
assert.strictEqual(toasts.pop(), "这一站微课即将开通", "unhosted lesson tap must explain honestly");
var navCountNoStation = navigations.length;
enterStation({});
assert.strictEqual(navigations.length, navCountNoStation, "no station means no navigation");

console.log("PASS test_learn_core_surface_contract.js");
