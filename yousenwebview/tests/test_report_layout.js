// test_report_layout.js — regression checks for the hosted learner-facing report page
// Run: node yousenwebview/tests/test_report_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxml"),
  "utf8",
);
var reportWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxss"),
  "utf8",
);
var reportSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
  "utf8",
);
var attemptDetailSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/attempt-detail/attempt-detail.js"),
  "utf8",
);
var attemptDetailWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/attempt-detail/attempt-detail.wxml"),
  "utf8",
);
var mistakeBookWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.wxml"),
  "utf8",
);
var mistakeBookWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.wxss"),
  "utf8",
);
var mistakeBookSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/mistake-book/mistake-book.js"),
  "utf8",
);
var appConfig = fs.readFileSync(path.join(__dirname, "../app.json"), "utf8");

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function assertIncludes(source, needle, message) {
  assert(source.indexOf(needle) >= 0, message);
}

function assertNotIncludes(source, needle, message) {
  assert(source.indexOf(needle) < 0, message);
}

function assertBefore(source, first, second, message) {
  var a = source.indexOf(first);
  var b = source.indexOf(second);
  assert(a >= 0 && b >= 0 && a < b, message);
}

assert(
  reportWxml.indexOf('wx:for="{{dimList}}"') >= 0,
  "host report page should render every diagnosis dimension below the radar summary",
);
assert(
  reportWxml.indexOf('class="overview-primary-btn" bindtap="goPractice"') >= 0,
  "host report primary training CTA should open the in-report training plan",
);
assert(
  reportWxml.indexOf("学习大脑") < 0,
  "host report page should not expose internal Learning Brain naming in the first learner-facing surface",
);
assertIncludes(reportWxml, "今日处方", "first viewport should be framed as a learner prescription");
assertIncludes(reportWxml, "为什么推荐", "secondary hero action should explain the recommendation instead of duplicating module naming");
assertIncludes(reportWxml, "掌握可信度", "first viewport should show mastery confidence");
assertIncludes(reportWxml, "{{overallMastery}}%", "first viewport should bind mastery from the read model");
assertIncludes(reportWxml, "{{masteryStatusLabel}}", "first viewport should render mastery confidence status from the read model");
assertIncludes(reportWxml, 'style="{{overviewDonutStyle}}"', "hero mastery ring should bind progress to the real mastery score");
assertIncludes(reportSource, "_buildOverviewDonutStyle", "hero mastery ring should derive a dynamic conic gradient");
assertIncludes(reportWxml, "近 3 天", "first viewport should include recent 3 day progress");
assertIncludes(reportWxml, "待补错因", "first viewport should include weak error reasons");
assertIncludes(reportWxml, "掌握可信度", "first viewport should include mastery confidence status");
assertIncludes(reportWxml, "overview-metrics", "top status should keep the visual metric-card style");
assertIncludes(reportWxml, "metric-sparkline", "recent progress metric should keep the mini chart style");
assertIncludes(reportWxml, "metric-mini-bars", "weak reason metric should keep the mini bar style");
assertIncludes(reportWxml, "metric-trend-bars", "mastery trend metric should keep the trend chart style");
assert(
  reportWxml.indexOf('class="metric-chip metric-chip-progress" bindtap=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-progress" data-detail=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-warn" bindtap=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-warn" data-detail=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-good" bindtap=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-good" data-detail=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-progress" hover-class=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-warn" hover-class=') < 0 &&
    reportWxml.indexOf('class="metric-chip metric-chip-good" hover-class=') < 0,
  "top metric cards should be read-only and not expose tap affordances",
);
assertIncludes(reportWxml, "{{battlePlan.focusTopic || learningReviewSummary.primaryFocus || focusHint || '先完成一轮定向训练'}}", "first viewport should bind current focus from the read model");
assertIncludes(reportWxml, "bindtap=\"goPractice\"", "primary training CTA should keep users inside report training");
assertIncludes(reportSource, 'this._setReportDetailView("training")', "goPractice should stay inside the report training detail");
assert(
  reportSource.indexOf("route.practice()") < 0,
  "report page should not route users into the unfinished practice center",
);
assertIncludes(reportWxml, "摸底测试", "home module grid should expose assessment as the calibration action");
assertIncludes(reportWxml, 'bindtap="goAssessment"', "assessment module should route to the assessment flow");
assert(
  reportWxml.indexOf('module-recheck" data-detail="training"') < 0,
  "assessment module should not duplicate the training detail route",
);
assertIncludes(reportWxml, "训练闭环", "training detail should explain the diagnosis-repair-verification loop");
assertIncludes(reportWxml, "training-action-card", "training detail should expose a one-tap execution action");
assertIncludes(reportWxml, "battle-plan-action", "training prescription should repeat the execution action near the concrete plan");
assertIncludes(reportWxml, "bindtap=\"executeTrainingAction\"", "training execution CTA should have a concrete tap handler");
assertIncludes(reportSource, "_buildTrainingExecutionAction", "report page should derive execution action from the existing prescription");
assertIncludes(reportSource, "runtime.setPendingChatIntent", "active prescription execution should route into chat with a training prompt");
assertIncludes(reportSource, "route.assessment()", "degraded prescription execution should route into the assessment flow");
assertIncludes(reportSource, "route.chat()", "active prescription execution should route to the chat workspace");
assertIncludes(reportWxml, "先看结论，再决定是否深入", "home page should separate conclusions from module navigation");
assertIncludes(reportWxml, "深入查看", "home page should expose detail modules as a separate toolbox section");
assertIncludes(reportWxml, "module-onboarding-tip", "clickable detail modules should expose a first-use affordance");
assertIncludes(reportWxml, "点开卡片看具体依据", "first-use affordance should explain that module cards open detail pages");
assertIncludes(reportWxml, "dismissReportModuleHint", "first-use affordance should be dismissible");
assertIncludes(reportSource, "REPORT_MODULE_HINT_STORAGE_KEY", "module hint dismissal should be persisted for returning users");
assertIncludes(reportSource, "_dismissReportModuleHint", "opening a module should dismiss the first-use affordance");
assert(
  reportWxml.indexOf('class="conclusion-card conclusion-card-primary" data-detail=') < 0 &&
    reportWxml.indexOf('class="conclusion-card" data-detail=') < 0,
  "conclusion cards should be read-only and avoid duplicating module links",
);
assertIncludes(reportWxml, "学情证据", "evidence module should be labelled as evidence rather than another conclusion");
assertIncludes(reportWxml, "今日训练", "training module should be distinct from the hero primary CTA");
assertIncludes(reportWxml, "错题归因", "mistake-book module should be framed as weak-error repair");
assertIncludes(reportWxml, "变化记录", "progress module should be framed as a history/detail view");
assertIncludes(reportWxss, ".conclusion-stack", "home page should include dedicated conclusion-card styling");
assertIncludes(reportWxss, ".overview-metrics", "home metric readout should keep dedicated chart-card styling");
assertIncludes(reportWxml, "真实作答证据", "attempt evidence cards should be visible before diagnostics");
assertIncludes(reportWxml, "class=\"attempt-card attempt-{{item.tone}}\"", "attempt cards should have a dedicated visual surface");
assertIncludes(reportWxml, "bindtap=\"openAttemptDetail\"", "attempt card should open detail on tap");
assertIncludes(appConfig, "pages/attempt-detail/attempt-detail", "host attempt detail page should be registered");
assertIncludes(reportSource, "wx.navigateTo", "host attempt detail action should navigate to a full page");
assertIncludes(reportSource, "/packageDeeptutor/pages/attempt-detail/attempt-detail", "host attempt detail action should target the full detail page");
assert(
  reportSource.indexOf("wx.showModal") < 0,
  "host attempt detail should not use a modal because long conversations and explanations get clipped",
);
assertIncludes(attemptDetailSource, "api.getLearningAttemptDetail", "host attempt detail page should call the mobile attempt-detail authority");
assertNotIncludes(attemptDetailWxml, "当时对话", "host attempt detail page should not duplicate the previous conversation transcript below the structured review");
assertNotIncludes(attemptDetailWxml, "detail.turns", "host attempt detail page should not render raw conversation turns after the structured explanation");
assertIncludes(attemptDetailWxml, "bindtap=\"goBack\"", "host attempt detail page should provide an explicit back button");
assertIncludes(reportWxml, "{{item.timeLabel}}", "attempt card should show time");
assertIncludes(reportWxml, "{{item.title}}", "attempt card should show question title");
assertIncludes(reportWxml, "{{item.resultLabel}}", "attempt card should show result");
assertIncludes(reportWxml, "{{item.answerLine}}", "attempt card should show user/correct answer line from read model");
assertIncludes(reportWxml, "{{item.diagnosisDetail || item.diagnosis}}", "attempt card should show one-line diagnosis from read model");
assertIncludes(reportWxml, "查看解析", "attempt card should expose analysis detail action");
assertIncludes(reportWxml, "wx:if=\"{{item.isBookmarked}}\"", "attempt card should render cloud bookmark state from read model");
assertIncludes(reportWxml, "{{item.bookmarkLabel || '已加入错题'}}", "attempt card should use backend bookmark label");
assertIncludes(reportWxml, "wx:elif=\"{{item.collectable}}\"", "attempt card should only expose save action when not already bookmarked");
assertIncludes(reportWxml, "收藏错题", "attempt card should expose mistake-book action without local inference");
assertIncludes(reportSource, "api.saveMistakeBookItem", "mistake-book action should call the cloud mistake-book authority");
assertNotIncludes(reportWxml, "保存学习卡", "attempt card should hide the unfinished notebook-card save action");
assertNotIncludes(reportWxml, "today-task-strip", "report home should hide the unfinished notebook-card today task strip");
assertNotIncludes(reportWxml, "今天时间少", "unfinished today task controls should stay hidden");
assertNotIncludes(reportWxml, "换一组", "unfinished today task controls should stay hidden");
assertIncludes(reportWxml, "我其实会，测一下", "diagnosis challenge should route to a retest instead of writing mastery");
assertNotIncludes(reportWxml, "学习卡片", "evidence detail should hide unfinished notebook-card assets");
assertIncludes(reportSource, "api.saveNotebookCard", "notebook-card action should call the existing notebook add_record authority");
assertIncludes(reportSource, "note_card_saved", "notebook-card save should emit product behavior through surface-events");
assertIncludes(reportSource, "today_task_started", "today task action should reuse product behavior authority");
assertIncludes(reportSource, "compressTodayTasks", "today compression should be implemented as local view filtering");
assertIncludes(reportSource, "rotateTodayTasks", "today reshuffle should be implemented as local view filtering");
assertIncludes(reportSource, "learner_challenge_mastery", "diagnosis challenge should be a retest intent, not a mastery write");
assertIncludes(appConfig, "pages/mistake-book/mistake-book", "host mistake-book page should be registered");
assertIncludes(reportWxml, "module-mistake-book", "report page should expose a dedicated mistake-book module");
assertIncludes(reportWxml, "bindtap=\"openMistakeBook\"", "mistake-book module should navigate to the dedicated page");
assertIncludes(reportSource, "route.mistakeBook()", "report mistake-book action should use the package route helper");
assertIncludes(mistakeBookSource, "api.getMistakeBook", "mistake-book page should read the cloud mistake-book authority");
assertIncludes(mistakeBookSource, "api.recordMistakeBookItemReview", "mistake-book page should support review recording");
assertIncludes(mistakeBookSource, "api.markMistakeBookItemMastered", "mistake-book page should support mastered state");
assertIncludes(mistakeBookSource, "api.removeMistakeBookItem", "mistake-book page should support removing items");
assertIncludes(mistakeBookWxml, "AI分析", "mistake-book page should expose AI analysis");
assertIncludes(mistakeBookWxml, "高频知识点", "mistake-book page should render concept distribution");
assertIncludes(mistakeBookWxml, "常见错因", "mistake-book page should render error distribution");
assertIncludes(mistakeBookWxml, "看解析", "mistake-book items should deep-link to attempt detail");
assertIncludes(mistakeBookWxss, ".chart-fill", "mistake-book page should include chart styling");
assertIncludes(reportWxml, "{{degradedHint}}", "report page should show degraded/cached summary hint when the network path is unavailable");
assertIncludes(reportWxml, "完成一次案例题批改", "empty state should explain how to generate learning facts");
assertBefore(reportWxml, "真实作答证据", "radar-canvas-wrap", "actionable diagnosis and evidence should appear before the radar");
assert(
  reportWxml.indexOf("eventId") < 0 && reportWxml.indexOf("attemptRef") < 0,
  "host report page should not render raw ids in learner-facing UI",
);
assert(
  reportWxss.indexOf(".level-L1_repeated") >= 0 &&
    reportWxss.indexOf(".level-L2_confirmed") >= 0 &&
    reportWxss.indexOf(".chain-not-improved") >= 0,
  "host report styles should distinguish L1/L2 Learning Brain evidence levels and training outcomes",
);
assert(
  reportWxss.indexOf(".dim-list") >= 0 && reportWxss.indexOf(".dim-bar") >= 0,
  "host report page should include styles for the diagnosis dimension list",
);
assert(
  reportWxss.indexOf(".attempt-card") >= 0 &&
    reportWxss.indexOf(".primary-training-cta") >= 0 &&
    reportWxss.indexOf(".degraded-hint") >= 0,
  "host report styles should cover attempt cards, restrained CTA, and degraded hints",
);
assert(
  reportWxss.indexOf("width: 280px") < 0 && reportWxss.indexOf("height: 280px") < 0,
  "host report radar should not use a fixed px size that can clip on small screens",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
