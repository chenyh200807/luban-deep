// Run: node yousenwebview/tests/test_report_home_core_contract.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var learnVm = require("../packageDeeptutor/utils/learn-view-model");
var reportHomeVm = require("../packageDeeptutor/utils/report-home-view-model");

var lessons = {
  lessons: [
    {
      pack_id: "N01",
      title: "网络计划关键线路",
      card_hosted: true,
      light_practice_available: true,
    },
  ],
};

assert.strictEqual(
  learnVm.buildCanonicalLearningTask({ homeDashboard: {}, lessons: lessons }),
  null,
  "green lessons must not manufacture a primary task when server next_step is absent",
);

var canonicalTask = learnVm.buildCanonicalLearningTask({
  homeDashboard: {
    next_step: {
      mode: "review_due",
      source_ref: "probe_n01",
      target_pack_id: "N01",
      reason: "错因到期验证",
    },
  },
  lessons: lessons,
  // review 路由资格消费 canonical due 条目(retest_available === true),
  // 不复用 forward-only 的 lessons light_practice_available 旗标。
  report: {
    pack_review: {
      authority: "revalidation_queue",
      enabled: true,
      due: [{ pack_id: "N01", probe_id: "probe_n01", retest_available: true }],
    },
  },
});
assert.strictEqual(canonicalTask.pack_id, "N01");
assert.strictEqual(canonicalTask.probe_id, "probe_n01");
assert.strictEqual(canonicalTask.mode, "review");
assert.strictEqual(canonicalTask.practice_kind, "retest");

var report = {
  source_status: { learner_events: { ok: true } },
  freshness: { event_count: 4 },
  overview: { recent_three_done: 3 },
};
var reportPageData = {
  trendNarrative: "反复出现的错因在减少，方向是对的",
  learningDiagnosisCards: [
    { key: "a", title: "审题边界", meta: "最近出现 2 次", detail: "漏看限制词" },
    { key: "b", title: "规范条件", meta: "最近出现 2 次", detail: "适用条件混淆" },
    { key: "c", title: "案例表达", meta: "最近出现 1 次", detail: "采分点不完整" },
    { key: "d", title: "不应出现在首页", meta: "第 4 条", detail: "超出上限" },
  ],
};
var home = reportHomeVm.buildReportHomeViewModel({
  report: report,
  reportPageData: reportPageData,
  nextTask: canonicalTask,
});
assert.strictEqual(home.evidenceState, "known");
assert.strictEqual(home.recentProgress.available, true);
assert.strictEqual(home.recentProgress.title, "近 3 天完成 3 道有效作答");
assert.strictEqual(home.blindSpots.length, 3, "home must expose at most three evidence-backed blind spots");
assert.strictEqual(home.nextTask.probe_id, "probe_n01");
assert.strictEqual(home.nextTaskAvailable, true);

var insufficient = reportHomeVm.buildReportHomeViewModel({
  report: {
    source_status: { learner_events: { ok: false } },
    freshness: { event_count: 0 },
    overview: { recent_three_done: 99 },
  },
  reportPageData: reportPageData,
  nextTask: null,
});
assert.strictEqual(insufficient.evidenceState, "insufficient_evidence");
assert.strictEqual(insufficient.recentProgress.available, false);
assert.deepStrictEqual(insufficient.blindSpots, []);
assert.strictEqual(insufficient.nextTask, null);
assert.strictEqual(insufficient.nextTaskAvailable, false);

var reportWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxml"),
  "utf8",
);
var reportSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.js"),
  "utf8",
);
assert(
  reportWxml.indexOf(
    '<view class="report-page paper {{isDark?\'\':\'light\'}} {{reportDetailView != \'home\' ? \'report-detail-active\' : \'\'}}">',
  ) >= 0,
  "the user-owned paper/ink root class must be preserved byte-for-byte",
);
var homeStart = reportWxml.indexOf("B5 精简学情首页");
var homeEnd = reportWxml.indexOf("reportDetailView == 'evidence'");
var homeBlock = reportWxml.slice(homeStart, homeEnd);
assert(homeStart >= 0 && homeEnd > homeStart);
assert(homeBlock.indexOf("近期进展") >= 0);
assert(homeBlock.indexOf("1–3 个盲点") >= 0);
assert(homeBlock.indexOf("唯一下一步") >= 0);
assert(homeBlock.indexOf("insufficient_evidence") >= 0);
assert.strictEqual((homeBlock.match(/bindtap="goReportHomeTask"/g) || []).length, 1);
[
  "masteryMap",
  "riskGearLabel",
  "overallMastery",
  "openMistakeBook",
  "absorbDiagnosisIntoPlan",
  "goPractice",
].forEach(function (legacy) {
  assert.strictEqual(homeBlock.indexOf(legacy), -1, "home must not retain first-class legacy surface: " + legacy);
});
assert(reportSource.indexOf("api.getHomeDashboard") >= 0, "report must read canonical home next_step");
assert(reportSource.indexOf("buildCanonicalLearningTask") >= 0, "report and learning must share task translation");
assert(
  /buildCanonicalLearningTask\(\{[\s\S]{0,500}?report:\s*report\b/.test(reportSource),
  "report page must feed pack_review into the canonical task so review supply is not killed by the forward-only light flag",
);
assert(
  reportSource.indexOf("this._reportHomeOwnerId !== reportOwnerId") >= 0 &&
    reportSource.indexOf("this.setData({ reportHome: _emptyReportHome() })") >= 0,
  "account changes must clear the previous learner's compact report before cache/network hydration",
);

console.log("PASS test_report_home_core_contract.js");
