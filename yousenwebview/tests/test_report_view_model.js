// Run: node yousenwebview/tests/test_report_view_model.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var wxVmPath = path.join(
  __dirname,
  "../../wx_miniprogram/utils/learning-report-view-model.js",
);
var yousenVmPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/learning-report-view-model.js",
);
var reportPath = path.join(__dirname, "../packageDeeptutor/pages/report/report.js");

var wxHash = fs.readFileSync(wxVmPath, "utf8");
var yousenHash = fs.readFileSync(yousenVmPath, "utf8");
assert.strictEqual(
  wxHash,
  yousenHash,
  "wx and yousen report view models must stay byte-identical",
);

var wxVm = require(wxVmPath);
var yousenVm = require(yousenVmPath);
var report = {
  schema_version: 2,
  overview: { today_done: 2, learner_level: "beginner", focus_hint: "防水工程" },
  radar_dimensions: [{ name: "防水工程", value: 0.36 }],
  mastery: { overall_mastery: 36, groups: [], hotspots: [], review_summary: {} },
  today_prescription: {
    title: "今天先复测防水工程",
    why_this_now: "最近 2 次案例题都漏写节点构造，先用同考点题复测。",
    evidence_refs: ["evt1", "evt2"],
    source: "training_intent",
    prescription_authority: "training_intent",
    primary_action: { type: "retest_training", intent_id: "lti_1" },
  },
  learner_facing: {
    summary: { title: "学习复盘", today_done: 2, primary_focus: "防水工程" },
    recent_attempts: [{ key: "a1", title: "防水节点", diagnosis: "概念混淆" }],
    next_action: { title: "防水工程专项", intent: { source: "learning_report" } },
  },
};

assert.deepStrictEqual(
  wxVm.buildLearningReportViewModel(report),
  yousenVm.buildLearningReportViewModel(report),
);
var vm = yousenVm.buildLearningReportViewModel(report);
assert.strictEqual(vm.prescription.reason, report.today_prescription.why_this_now);
assert.deepStrictEqual(vm.prescription.evidenceRefs, ["evt1", "evt2"]);
assert.strictEqual(vm.prescription.authority, "training_intent");
assert.strictEqual(yousenVm.toReportPageData(vm).prescriptionAuthority, "training_intent");

var loopReport = {
  schema_version: 2,
  mastery: {
    overall_mastery: {
      score: 40,
      confidence: 0.72,
      status: "needs_confirmation",
    },
    groups: [],
    hotspots: [],
    knowledge_summary: {
      total_textbook_chapters: 13,
      leaf_nodes: 2786,
      evaluated_topics: 2,
      weak_topics: 1,
      textbook_chapters: [
        {
          chapter_no: 3,
          chapter_name: "第3章 建筑工程施工技术",
          evaluated_topics: 2,
          weak_topics: 1,
          top_topics: ["地下室防水工程施工"],
          status: "weak",
        },
      ],
    },
    review_summary: {},
  },
  long_term_analytics: {
    recurrent_errors: [
      {
        concept_id: "1A413050",
        error_code: "near_synonym_not_accepted",
        occurrence_count: 2,
        last_seen_at: "2026-06-08T08:00:00Z",
      },
    ],
  },
  revalidation_queue: {
    items: [
      {
        kind: "revalidation_probe",
        status: "active",
        intent: {
          source: "revalidation_queue",
          concept_id: "1A413050",
          concept_label: "地下室防水工程施工",
        },
      },
    ],
  },
  learning_state: {
    ability_state: [
      {
        dimension: "code_application",
        state: "recurring",
        evidence_count: 2,
        confidence: 0.8,
      },
    ],
    knowledge_state: [
      {
        knowledge_node_id: "1A413050",
        label: "地下室防水工程施工",
        state: "recurring",
        evidence_count: 2,
        confidence: 0.8,
      },
    ],
  },
  learning_brain: {
    projection_subject: "construction_exam_learning_truth",
    weak_points: [
      {
        concept_id: "1A413050",
        label: "地下室防水工程施工",
        error_code: "near_synonym_not_accepted",
        evidence_refs: ["attempt_m32_001", "attempt_m32_002"],
        occurrence_timeline: [
          { event_id: "attempt_m32_001", observed_at: "2026-06-07T08:00:00Z" },
          { event_id: "attempt_m32_002", observed_at: "2026-06-08T08:00:00Z" },
        ],
      },
    ],
  },
};
var loopPageData = yousenVm.toReportPageData(
  yousenVm.buildLearningReportViewModel(loopReport),
);
assert.strictEqual(loopPageData.overallMastery, 40);
assert(
  loopPageData.radarDimensions.length > 0,
  "ability data must project from unified learning_state when mastery groups are empty",
);
assert.strictEqual(loopPageData.knowledgeSummary.totalTextbookChapters, 13);
assert(
  loopPageData.textbookChapters.length > 0,
  "textbook directory progress must project from unified mastery.knowledge_summary",
);
assert(
  loopPageData.masteryGroups.length > 0,
  "mastery distribution must not stay empty when unified report has Learning Brain evidence",
);
assert(
  loopPageData.hotspots.length > 0,
  "weak hotspot distribution must project from Learning Brain weak_points/recurrent errors when mastery.hotspots is empty",
);
assert.strictEqual(loopPageData.hotspots[0].name, "建筑工程施工技术");
assert.strictEqual(loopPageData.reviewSummary.total_due, 1);
assert.strictEqual(loopPageData.reviewSummary.overdue_count, 0);

var source = fs.readFileSync(reportPath, "utf8");
assert(
  source.indexOf("learning-report-view-model") >= 0 &&
    source.indexOf("buildLearningReportViewModel") >= 0 &&
    source.indexOf("toReportPageData") >= 0 &&
    source.indexOf("prescriptionAuthority") >= 0,
  "yousen report page must consume the shared learning report view model",
);
var hydrateBody = source.split("_hydrateFromUnifiedReport(snapshot)")[1].split("onReady()")[0];
assert(hydrateBody.indexOf("_normalizeRadarDimensions(") < 0);
assert(hydrateBody.indexOf("_buildRadarViewModel(") < 0);
assert(hydrateBody.indexOf("_normalizeLearningBrainPayload(") < 0);
