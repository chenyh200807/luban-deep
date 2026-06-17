// test_report_layout.js — regression checks for the learner-facing report page
// Run: node wx_miniprogram/tests/test_report_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../pages/report/report.wxml"),
  "utf8",
);
var reportWxss = fs.readFileSync(
  path.join(__dirname, "../pages/report/report.wxss"),
  "utf8",
);
var reportSource = fs.readFileSync(
  path.join(__dirname, "../pages/report/report.js"),
  "utf8",
);
var attemptDetailSource = fs.readFileSync(
  path.join(__dirname, "../pages/attempt-detail/attempt-detail.js"),
  "utf8",
);
var attemptDetailWxml = fs.readFileSync(
  path.join(__dirname, "../pages/attempt-detail/attempt-detail.wxml"),
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
  reportWxml.indexOf('<text class="overview-tip" wx:if="{{studyTip}}">{{studyTip}}</text>') >= 0,
  "report overview should still render learner studyTip",
);
assert(
  reportWxml.indexOf('wx:elif="{{focusHint}}"') < 0,
  "report overview should not render focusHint a second time above the dedicated insight strip",
);
assert(
  reportWxml.indexOf('<view class="insight-strip glass-card" wx:if="{{focusHint}}">') >= 0,
  "report page should keep the dedicated focusHint insight strip",
);
assert(
  reportWxml.indexOf('wx:for="{{dimList}}"') >= 0,
  "report page should render every diagnosis dimension, not only the radar summary",
);
assert(
  reportWxml.indexOf('class="metric-chip metric-chip-progress" bindtap="goPractice"') >= 0,
  "report today's progress metric should open the practice page",
);
assert(
  reportWxml.indexOf("学习大脑") < 0,
  "report page should not expose internal Learning Brain naming in the first learner-facing surface",
);
assertIncludes(reportWxml, "今日学习复盘", "first viewport should be framed as a learner review");
assertIncludes(reportWxml, "掌握可信度", "first viewport should show mastery confidence");
assertIncludes(reportWxml, "{{overviewScore}}%", "first viewport should bind the overview authority score from the read model");
assertIncludes(reportWxml, "{{masteryStatusLabel}}", "first viewport should render mastery confidence status from the read model");
assertIncludes(reportWxml, "今日", "first viewport should include today's progress");
assertIncludes(reportWxml, "近3天", "first viewport should include recent 3 day progress");
assertIncludes(reportWxml, "{{streakDays}}天", "first viewport should include streak");
assertIncludes(reportWxml, "{{learningReviewSummary.primaryFocus || focusHint || '先完成一次批改'}}", "first viewport should bind current focus from the read model");
assertIncludes(reportWxml, "bindtap=\"goPractice\"", "primary training CTA should route to practice");
assertIncludes(reportWxml, "真实作答证据", "attempt evidence cards should be visible before diagnostics");
assertIncludes(reportWxml, "class=\"attempt-card attempt-{{item.tone}}\"", "attempt cards should have a dedicated visual surface");
assertIncludes(reportWxml, "bindtap=\"openAttemptDetail\"", "attempt card should open detail on tap");
assertIncludes(appConfig, "pages/attempt-detail/attempt-detail", "attempt detail page should be registered");
assertIncludes(reportSource, "wx.navigateTo", "attempt detail action should navigate to a full page");
assertIncludes(reportSource, "/pages/attempt-detail/attempt-detail", "attempt detail action should target the full detail page");
assert(
  reportSource.indexOf("wx.showModal") < 0,
  "attempt detail should not use a modal because long conversations and explanations get clipped",
);
assertIncludes(attemptDetailSource, "api.getLearningAttemptDetail", "attempt detail page should call the mobile attempt-detail authority");
assertNotIncludes(attemptDetailWxml, "当时对话", "attempt detail page should not duplicate the previous conversation transcript below the structured review");
assertNotIncludes(attemptDetailWxml, "detail.turns", "attempt detail page should not render raw conversation turns after the structured explanation");
assertIncludes(attemptDetailWxml, "bindtap=\"goBack\"", "attempt detail page should provide an explicit back button");
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
assertIncludes(reportWxml, "{{degradedHint}}", "report page should show degraded/cached summary hint when the network path is unavailable");
assertIncludes(reportWxml, "完成一次案例题批改", "empty state should explain how to generate learning facts");
assertBefore(reportWxml, "真实作答证据", "radar-canvas-wrap", "actionable diagnosis and evidence should appear before the radar");
assert(
  reportWxml.indexOf("eventId") < 0 && reportWxml.indexOf("attemptRef") < 0,
  "report page should not render raw ids in learner-facing UI",
);
assert(
  reportWxss.indexOf("width: 280px") < 0 && reportWxss.indexOf("height: 280px") < 0,
  "report radar should not use a fixed px size that can clip on small screens",
);
assert(
  reportWxss.indexOf(".attempt-card") >= 0 &&
    reportWxss.indexOf(".primary-training-cta") >= 0 &&
    reportWxss.indexOf(".degraded-hint") >= 0,
  "report styles should cover attempt cards, restrained CTA, and degraded hints",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
