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
