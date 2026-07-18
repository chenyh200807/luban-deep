// test_report_layout.js — regression checks for the hosted learner-facing report page
// (B5 精简首页：近期进展 + 1–3 个盲点 + 唯一下一步)
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
var viewModelSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/learning-report-view-model.js"),
  "utf8",
);
var reportHomeViewModelSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/utils/report-home-view-model.js"),
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

function countOccurrences(source, needle) {
  return source.split(needle).length - 1;
}

// home block slice：只检查精简主面，不把保留的深入页算进首页信息架构。
var homeStart = reportWxml.indexOf("B5 精简学情首页");
var homeEnd = reportWxml.indexOf("reportDetailView == 'evidence'");
assert(
  homeStart >= 0 && homeEnd > homeStart,
  "report home surface should be the B5 compact block before the evidence detail",
);
var homeBlock = reportWxml.slice(homeStart, homeEnd);

// ── 首页只保留三件事，旧大盘/复习/精确掌握不再占据一等位置 ─────
assertIncludes(homeBlock, "近期进展", "home should show recent progress");
assertIncludes(homeBlock, "1–3 个盲点", "home should show one to three blind spots");
assertIncludes(homeBlock, "唯一下一步", "home should show one canonical next task");
assertIncludes(homeBlock, "reportHome.recentProgress", "progress must come from the compact projection");
assertIncludes(homeBlock, "reportHome.blindSpots", "blind spots must come from the compact projection");
assertIncludes(homeBlock, "reportHome.nextTask", "next task must come from the compact projection");
assertIncludes(homeBlock, "insufficient_evidence", "unknown evidence must fail closed explicitly");
[
  "masteryMap",
  "riskGearLabel",
  "overallMastery",
  "lr-map-grid",
  "分数账本",
  "错因结构",
  "openMistakeBook",
  "absorbDiagnosisIntoPlan",
].forEach(function (legacy) {
  assertNotIncludes(homeBlock, legacy, "compact home must remove legacy first-class surface: " + legacy);
});

// ── 首页唯一业务 CTA 复用 server next_step，不接受 report 自己排优先级 ──
assert(
  countOccurrences(homeBlock, 'bindtap="goReportHomeTask"') === 1,
  "authenticated report home must expose exactly one business CTA",
);
assertIncludes(reportSource, "api.getHomeDashboard", "report must fetch canonical home next_step");
assertIncludes(reportSource, "buildCanonicalLearningTask", "report and learning must share task translation");
assertIncludes(reportSource, "buildReportHomeViewModel", "report home must use a pure compact projection");
assertIncludes(reportHomeViewModelSource, "eventStatus.ok === true", "eligible learning evidence must be explicit");
assertIncludes(reportHomeViewModelSource, "eventCount > 0", "zero evidence must not fabricate progress or blind spots");
assertNotIncludes(homeBlock, "learningNextAction", "learning-brain action must not compete with home next_step");
assertNotIncludes(homeBlock, "pack_review", "review due must arrive only through home next_step");

// ── 保留在深入页的四态证据能力，不再挤占首页 ────────────────
assertIncludes(reportWxml, "{{observedCount}}", "detail views should surface the fourth (observed/未学) state count");
assertIncludes(reportSource, "observedCount", "report radar view model should count observed separately");
assertIncludes(viewModelSource, "observedCount", "shared view model should count observed separately");
assert(
  reportSource.indexOf('pct > 0 ? "weak" : "observed"') >= 0,
  "score-0 dimensions must classify as observed (未学), not weak — no red wall for the unlearned",
);
assertIncludes(reportWxml, "lr-fill-{{ch.status}}", "chapter bars should use backend four-state status classes, not backend hex colors");
// 禁红灯墙:掌握色阶不允许出现亮红/黄硬编码
assertNotIncludes(reportWxss, "#f87171", "mastery ladder must not use alarm red (红灯墙)");
assertNotIncludes(reportWxss, "#fb7185", "mastery ladder must not use alarm red (红灯墙)");

// ── 近期进展不画假曲线 ───────────────────────────────────────
assertNotIncludes(homeBlock, "polyline", "no fake trend curve — backend has no numeric time series");
assertNotIncludes(homeBlock, "canvas", "no chart canvas on the 10e home surface");
assertIncludes(viewModelSource, "trend_direction", "trend narrative must derive from long_term_analytics.progression_summary");

// ── 首页只读投影/深链，文案禁审视词 ─────────────────────────
assertNotIncludes(homeBlock, "api.save", "compact home surface adds no write paths");
var forbiddenWords = ["看穿", "识破", "揭穿", "露馅"];
forbiddenWords.forEach(function (word) {
  assertNotIncludes(reportWxml, word, "report copy must not use the auditing word " + word);
  assertNotIncludes(reportSource, word, "report source copy must not use the auditing word " + word);
  assertNotIncludes(viewModelSource, word, "view model copy must not use the auditing word " + word);
});

// 旧掌握地图仍只属于深入页兼容能力，不再是首页发布门。
assertIncludes(viewModelSource, "buildPackMasteryMap", "deep report map keeps its shared pure projection");

// ── 保留的深入页与证据链契约(旧断言仍然成立的部分) ─────────
assertIncludes(reportWxml, "真实作答证据", "attempt evidence cards should stay in the evidence detail");
assertIncludes(reportWxml, 'class="attempt-card attempt-{{item.tone}}"', "attempt cards should keep a dedicated visual surface");
assertIncludes(reportWxml, 'bindtap="openAttemptDetail"', "attempt card should open detail on tap");
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
assertIncludes(attemptDetailWxml, 'bindtap="goBack"', "host attempt detail page should provide an explicit back button");
assertIncludes(reportWxml, "{{item.timeLabel}}", "attempt card should show time");
assertIncludes(reportWxml, "{{item.resultLabel}}", "attempt card should show result");
assertIncludes(reportWxml, "{{item.answerLine}}", "attempt card should show user/correct answer line from read model");
assertIncludes(reportWxml, "{{item.diagnosisDetail || item.diagnosis}}", "attempt card should show one-line diagnosis from read model");
assertIncludes(reportWxml, "查看解析", "attempt card should expose analysis detail action");
assertIncludes(reportWxml, 'wx:if="{{item.isBookmarked}}"', "attempt card should render cloud bookmark state from read model");
assertIncludes(reportWxml, "{{item.bookmarkLabel || '已加入错题'}}", "attempt card should use backend bookmark label");
assertIncludes(reportWxml, 'wx:elif="{{item.collectable}}"', "attempt card should only expose save action when not already bookmarked");
assertIncludes(reportWxml, "收藏错题", "attempt card should expose mistake-book action without local inference");
assertIncludes(reportSource, "api.saveMistakeBookItem", "mistake-book action should call the cloud mistake-book authority");
assertIncludes(reportWxml, "保存学习卡", "attempt card should expose the P0A source-linked notebook-card save action");
assertIncludes(reportWxml, "我其实会，测一下", "diagnosis challenge should route to a retest instead of writing mastery");
assertIncludes(reportSource, "api.saveNotebookCard", "notebook-card action should call the existing notebook add_record authority");
assertIncludes(reportSource, "note_card_saved", "notebook-card save should emit product behavior through surface-events");
assertIncludes(reportSource, "learner_challenge_mastery", "diagnosis challenge should be a retest intent, not a mastery write");
assertIncludes(appConfig, "pages/mistake-book/mistake-book", "host mistake-book page should be registered");
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
// 纸墨朱竹 token 落地
assertIncludes(reportWxss, '@import "/packageDeeptutor/styles/paper-ink.wxss"', "10e surface must use the paper-ink token sheet");
assertIncludes(reportWxml, 'class="report-page paper', "report page root must opt into the --pk-* token scope");

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_report_layout.js (" + pass + " assertions)");
