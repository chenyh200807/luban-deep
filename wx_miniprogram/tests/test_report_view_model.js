// Run: node wx_miniprogram/tests/test_report_view_model.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var wxVmPath = path.join(__dirname, "../utils/learning-report-view-model.js");
var yousenVmPath = path.join(
  __dirname,
  "../../yousenwebview/packageDeeptutor/utils/learning-report-view-model.js",
);
var wxReportPath = path.join(__dirname, "../pages/report/report.js");

var wxVm = require(wxVmPath);
var yousenVm = require(yousenVmPath);

var report = {
  ok: true,
  schema_version: 2,
  overview: {
    today_done: 4,
    daily_target: 12,
    streak_days: 3,
    due_today_count: 2,
    weak_node_count: 1,
    focus_hint: "继续推进主体结构",
    learner_level: "intermediate",
    study_tip: "先复盘错因，再做变式题",
  },
  radar_dimensions: [
    { name: "主体结构", value: 0.72 },
    { name: "防水工程", value: 0.28 },
  ],
  mastery: {
    overall_mastery: { score: 52, confidence: 0.55, status: "developing" },
    groups: [{ name: "薄弱点", chapters: [{ name: "防水工程", mastery: 28 }] }],
    hotspots: [{ name: "防水工程", mastery: 28 }],
    review_summary: { total_due: 2, overdue_count: 1 },
  },
  attempts: [
    {
      attempt_key: "attempt-1",
      attempt_ref: "signed-ref",
      subject_id: "construction_exam_1",
      bot_id: "construction-exam",
      time_label: "今天 09:20",
      question_title: "主体结构验收条件",
      question_preview: "主体结构验收条件",
      result_label: "答错",
      tone: "wrong",
      answer_line: "你选 A，正确 B",
      diagnosis: "多选漏选",
      why_it_matters: "漏掉验收条件",
      actions: { bookmark: true },
      is_bookmarked: true,
      bookmark_label: "已加入错题",
    },
  ],
  learner_facing: {
    summary: {
      title: "今日学习复盘",
      headline: "最近练习集中暴露主体结构薄弱点",
      primary_focus: "主体结构",
      today_done: 4,
      recent_three_done: 3,
      weak_count: 1,
    },
    recent_attempts: [
      {
        key: "attempt-1",
        attempt_ref: "signed-ref",
        time_label: "今天 09:20",
        title: "主体结构验收条件",
        result_label: "答错",
        tone: "wrong",
        answer_line: "你选 A，正确 B",
        diagnosis: "多选漏选",
        diagnosis_detail: "漏掉验收条件",
        collectable: true,
      },
    ],
    diagnoses: [{ key: "d1", title: "多选漏选", detail: "条件组合不完整" }],
    evidence_timeline: [{ key: "e1", title: "最近一次批改", line: "主体结构答错" }],
    training_loops: [{ key: "l1", title: "错因到训练", outcome: "仍需巩固" }],
    next_action: {
      title: "主体结构 3 题变式训练",
      subtitle: "围绕漏选错因",
      cta: "开始训练",
      estimated_minutes: 8,
      intent: { intent_type: "practice", source: "learning_report" },
    },
  },
  degraded: false,
  degraded_sources: [],
};

var wxModel = wxVm.buildLearningReportViewModel(report);
var yousenModel = yousenVm.buildLearningReportViewModel(report);

assert.deepStrictEqual(wxModel, yousenModel);
assert.strictEqual(wxModel.overview.todayDone, 4);
assert.strictEqual(wxModel.radar.weakCount, 1);
assert.strictEqual(wxModel.mastery.overall, 52);
assert.strictEqual(wxModel.mastery.overallStatusLabel, "正在形成");
assert.strictEqual(wxModel.learningBrain.attempts[0].attemptRef, "signed-ref");
assert.strictEqual(wxModel.learningBrain.training[0].intent.source, "learning_report");
assert.strictEqual(wxModel.hero.headline, "当前最该补：主体结构");
assert.strictEqual(wxModel.metrics[1].key, "recent_three");
assert.strictEqual(wxModel.attempts[0].attemptRef, "signed-ref");
assert.strictEqual(wxModel.attempts[0].subjectId, "construction_exam_1");
assert.strictEqual(wxModel.attempts[0].tone, "wrong");
assert.strictEqual(wxModel.attempts[0].isBookmarked, true);
assert.strictEqual(wxModel.attempts[0].bookmarkLabel, "已加入错题");
assert.strictEqual(wxModel.nextTraining[0].intent.source, "learning_report");
assert(Array.isArray(wxModel.masteryDimensions));
assert("stableTruths" in wxModel);
assert("recentObservations" in wxModel);
assert("mistakeBook" in wxModel);

var pageData = wxVm.toReportPageData(wxModel);
assert.strictEqual(pageData.todayDone, 4);
assert.strictEqual(pageData.masteryStatusLabel, "正在形成");
assert.strictEqual(pageData.learningBrainAttempts[0].title, "主体结构验收条件");
assert.strictEqual(pageData.learningAttemptCards[0].subjectId, "construction_exam_1");
assert.strictEqual(pageData.learningAttemptCards[0].isBookmarked, true);
assert.strictEqual(pageData.learningAttemptCards[0].bookmarkLabel, "已加入错题");
assert.strictEqual(pageData.learningBrainNextAction.intent.source, "learning_report");

var wxReportSource = fs.readFileSync(wxReportPath, "utf8");
assert(
  wxReportSource.indexOf("learning-report-view-model") >= 0 &&
    wxReportSource.indexOf("buildLearningReportViewModel") >= 0 &&
    wxReportSource.indexOf("toReportPageData") >= 0,
  "wx report page must consume the shared learning report view model",
);
var loadBody = wxReportSource.split("async _loadLearningReport()")[1].split("toggleMastery()")[0];
assert(loadBody.indexOf("normalizeMasteryGroups(") < 0);
assert(loadBody.indexOf("normalizeRadarState(") < 0);
assert(loadBody.indexOf("normalizeLearningBrainPayload(") < 0);
