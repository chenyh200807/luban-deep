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
var wxReportWxmlPath = path.join(__dirname, "../pages/report/report.wxml");
var wxTaxonomyPath = path.join(__dirname, "../utils/taxonomy.js");
var yousenTaxonomyPath = path.join(
  __dirname,
  "../../yousenwebview/packageDeeptutor/utils/taxonomy.js",
);

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
    { name: "主体结构工程施工", value: 0.72, score: 72, status: "strong" },
    { name: "地基基础工程相关规定", value: 0.28, score: 28, status: "weak" },
  ],
  mastery: {
    overall_mastery: { score: 52, confidence: 0.55, status: "developing" },
    groups: [{ name: "薄弱点", chapters: [{ name: "屋面与防水工程施工", mastery: 28 }] }],
    hotspots: [{ name: "屋面与防水工程施工", mastery: 28 }],
    knowledge_summary: {
      total_nodes: 3735,
      coded_nodes: 3733,
      leaf_nodes: 2786,
      unique_codes: 1284,
      duplicate_code_rows: 2449,
      total_textbook_chapters: 13,
      evaluated_topics: 2,
      evaluated_leaf_points: 1,
      mastered_topics: 0,
      developing_topics: 1,
      weak_topics: 1,
      unmeasured_leaf_points: 2785,
      textbook_chapters: [
        {
          chapter_no: 1,
          chapter_name: "第1章 建筑工程设计技术",
          section_count: 5,
          evaluated_topics: 1,
          mastered_topics: 0,
          developing_topics: 1,
          weak_topics: 0,
          top_topics: ["建筑构造设计要求"],
          status: "developing",
        },
        {
          chapter_no: 3,
          chapter_name: "第3章 建筑工程施工技术",
          section_count: 8,
          evaluated_topics: 1,
          mastered_topics: 0,
          developing_topics: 0,
          weak_topics: 1,
          top_topics: ["屋面与防水工程施工"],
          status: "weak",
        },
      ],
    },
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
    evidence_timeline: [
      { key: "e1", title: "最近一次批改", line: "主体结构答错" },
    ],
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
assert.strictEqual(wxModel.mastery.knowledgeSummary.totalTextbookChapters, 13);
assert.strictEqual(wxModel.mastery.knowledgeSummary.leafNodes, 2786);
assert.strictEqual(wxModel.mastery.knowledgeSummary.codedNodes, 3733);
assert.strictEqual(wxModel.mastery.knowledgeSummary.uniqueCodes, 1284);
assert.strictEqual(wxModel.mastery.knowledgeSummary.textbookChapters.length, 2);
assert.strictEqual(wxModel.mastery.groups[0].expanded, false);
assert.strictEqual(wxModel.mastery.groups[0].chapterCount, 1);
assert.strictEqual(wxModel.mastery.groups[0].previewText, "1 个子章节");
assert.strictEqual(wxModel.learningBrain.attempts[0].attemptRef, "signed-ref");
assert.strictEqual(
  wxModel.learningBrain.training[0].intent.source,
  "learning_report",
);
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
assert.strictEqual(pageData.knowledgeSummary.totalTextbookChapters, 13);
assert.strictEqual(pageData.textbookChapters[0].chapterName, "第1章 建筑工程设计技术");
assert.strictEqual(pageData.learningBrainAttempts[0].title, "主体结构验收条件");
assert.strictEqual(
  pageData.learningAttemptCards[0].subjectId,
  "construction_exam_1",
);
assert.strictEqual(pageData.learningAttemptCards[0].isBookmarked, true);
assert.strictEqual(
  pageData.learningAttemptCards[0].bookmarkLabel,
  "已加入错题",
);
assert.strictEqual(
  pageData.learningBrainNextAction.intent.source,
  "learning_report",
);

var wxReportSource = fs.readFileSync(wxReportPath, "utf8");
assert(
  wxReportSource.indexOf("schemaVersion === 1 || schemaVersion === 2") >= 0,
  "wx report page must accept learning-report schema v1 and v2 payloads",
);
assert(
  wxReportSource.indexOf("learning-report-view-model") >= 0 &&
    wxReportSource.indexOf("buildLearningReportViewModel") >= 0 &&
    wxReportSource.indexOf("toReportPageData") >= 0,
  "wx report page must consume the shared learning report view model",
);
var loadBody = wxReportSource
  .split("async _loadLearningReport()")[1]
  .split("toggleMastery()")[0];
assert(loadBody.indexOf("normalizeMasteryGroups(") < 0);
assert(loadBody.indexOf("normalizeRadarState(") < 0);
assert(loadBody.indexOf("normalizeLearningBrainPayload(") < 0);
assert(
  wxReportSource.indexOf("toggleMasteryGroup") >= 0,
  "wx report page must let mastery groups expand and collapse independently",
);
var wxReportWxml = fs.readFileSync(wxReportWxmlPath, "utf8");
assert(
  wxReportWxml.indexOf('wx:if="{{item.expanded}}"') >= 0 &&
    wxReportWxml.indexOf("group-preview-list") < 0,
  "wx report mastery map must hide child chapters until a group is expanded",
);
assert(
  wxReportWxml.indexOf("教材目录进度") >= 0 &&
    wxReportWxml.indexOf("textbookChapters") >= 0 &&
    wxReportWxml.indexOf("knowledgeSummary") >= 0,
  "wx report page must render read-model knowledge_summary textbook chapters",
);
assert.strictEqual(
  fs.readFileSync(wxTaxonomyPath, "utf8"),
  fs.readFileSync(yousenTaxonomyPath, "utf8"),
  "wx and yousen taxonomy display helpers must stay byte-identical",
);

var noisyReport = {
  schema_version: 2,
  overview: {},
  radar_dimensions: [
    { name: "那题", value: 0.72 },
    { name: "考卷", value: 0.72 },
    { name: "1A415041", value: 0.25 },
    { name: "1A420000", value: 0.25 },
    { name: "主体结构工程施工", value: 0.2 },
  ],
  mastery: {
    overall_mastery: 46,
    groups: [
      {
        name: "需要加强",
        avg_mastery: 46,
        chapters: [
          { name: "那题", mastery: 72 },
          { name: "考卷", mastery: 72 },
          { name: "1A415041", mastery: 25 },
          { name: "1A420000", mastery: 25 },
          { name: "防水 / 装饰 / 机电", mastery: 25 },
          {
            name: "1A411011",
            mastery: 20,
            taxonomy_path: ["建筑工程技术", "建筑设计与构造", "建筑设计", "建筑物分类与构成"],
          },
          {
            name: "1A411012",
            mastery: 25,
            taxonomy_path: ["建筑工程技术", "建筑设计与构造", "建筑设计", "建筑构造设计要求"],
          },
          { name: "屋面与防水工程施工", mastery: 30 },
          { name: "安全管理", mastery: 35 },
        ],
      },
    ],
    hotspots: [{ name: "那题", mastery: 72 }],
  },
};
var noisyModel = wxVm.buildLearningReportViewModel(noisyReport);
var noisyJson = JSON.stringify(noisyModel);
assert(noisyJson.indexOf("那题") < 0, "deictic question labels must not reach the report view model");
assert(noisyJson.indexOf("考卷") < 0, "exam-paper labels must not reach the report view model");
assert(noisyJson.indexOf("1A415041") < 0, "unresolved taxonomy codes must not render as chapters");
assert(noisyJson.indexOf("1A420000") < 0, "legacy parent codes must not render as chapters");
assert(noisyJson.indexOf("防水 / 装饰 / 机电") < 0, "slash-composed pseudo topics must not render as chapters");
assert.deepStrictEqual(
  noisyModel.radar.dims.map(function (dim) {
    return dim.name;
  }),
  ["第3章 建筑工程施工技术"],
);
assert.strictEqual(noisyModel.mastery.hotspots.length, 0);
assert.deepStrictEqual(
  noisyModel.mastery.groups.map(function (group) {
    return group.name;
  }),
  ["第1章 建筑工程设计技术", "第3章 建筑工程施工技术"],
);
assert.strictEqual(noisyModel.mastery.groups[0].chapters.length, 2);
assert.deepStrictEqual(
  noisyModel.mastery.groups[0].chapters.map(function (chapter) {
    return chapter.name;
  }),
  ["建筑物分类与构成", "建筑构造设计要求"],
);
assert.strictEqual(noisyModel.mastery.groups[0].expanded, false);
assert.strictEqual(noisyModel.mastery.groups[0].chapterCount, 2);
assert.strictEqual(noisyModel.mastery.groups[0].previewChapters.length, 2);
assert.strictEqual(noisyModel.mastery.groups[0].hiddenCount, 0);
assert.strictEqual(noisyModel.mastery.groups[0].previewText, "2 个子章节");
assert.strictEqual(noisyModel.mastery.groups[1].chapters.length, 1);
assert.deepStrictEqual(
  noisyModel.mastery.groups[1].chapters.map(function (chapter) {
    return chapter.name;
  }),
  ["屋面与防水工程施工"],
);

// ─── Batch C Task 8: state / scoring point map / prescription ───────────

var batchCReport = {
  ok: true,
  schema_version: 2,
  overview: { today_done: 0, daily_target: 0, streak_days: 0 },
  learning_state: {
    knowledge_state: [
      {
        node_id: "1A412010",
        label: "结构工程材料",
        state: "weak",
        evidence_count: 2,
        evidence_refs: ["e1", "e2"],
        granularity: "scoring_point",
        last_observed_at: "2026-05-22T08:00:00+08:00",
      },
    ],
    ability_state: [
      {
        dimension: "code_application",
        state: "weak",
        evidence_count: 2,
        evidence_refs: ["e1", "e2"],
        last_observed_at: "2026-05-22T08:00:00+08:00",
      },
    ],
    behavior_state: [
      {
        dimension: "recurrence",
        state: "recurring",
        evidence_count: 2,
        evidence_refs: ["e1", "e2"],
      },
    ],
    source_status: {
      authority: "learner_memory_events.learning_evidence",
      model: "rule_based_v1",
      grading_fact_count: 8,
      conversation_signal_count: 2,
    },
  },
  scoring_point_map: {
    items: [
      {
        point_id: "p_fire",
        label: "甲乙丙级耐火极限",
        granularity: "scoring_point",
        rubric_mode: "curated_rubric",
        knowledge_node_id: "1A412010",
        ability_dimension: "code_application",
        miss_count: 2,
        evidence_refs: ["e1", "e2"],
        error_codes: ["E02"],
        next_action: {
          kind: "repair_and_verify",
          intent: {
            intent_version: 2,
            status: "active",
            concept_label: "甲乙丙级耐火极限",
            ability_dimension: "code_application",
            evidence_refs: ["e1", "e2"],
            prescription_steps: [
              { phase: "repair_root", question_count: 2 },
              { phase: "expression_drill", question_count: 1 },
              { phase: "transfer_case", question_count: 1 },
              { phase: "verification_probe", question_count: 1 },
            ],
          },
        },
      },
    ],
    empty_state: "",
    source_status: { authority: "learner_memory_events.learning_evidence" },
  },
  next_training: [
    {
      key: "loop-1",
      title: "今日处方",
      intent: {
        intent_version: 2,
        status: "active",
        concept_id: "1A412010",
        concept_label: "甲乙丙级耐火极限",
        ability_dimension: "code_application",
        behavior_state: "recurring",
        evidence_refs: ["e1", "e2"],
        prescription_steps: [
          { phase: "repair_root", question_count: 2 },
          { phase: "expression_drill", question_count: 1 },
          { phase: "transfer_case", question_count: 1 },
          { phase: "verification_probe", question_count: 1 },
        ],
        success_criteria: { requires_revalidation: true },
      },
    },
  ],
  attempts: [
    {
      attempt_key: "attempt-fire-door",
      attempt_ref: "ref-fire-door",
      time_label: "今天 10:55",
      question_title: "关于防火门的构造要求，下列哪项说法是正确的？",
      result_label: "答错",
      tone: "wrong",
      answer_line: "你选：A；正确：D",
      diagnosis: "把耐火极限和双扇门关闭顺序混在了一起。",
      why_it_matters: "A 选项错在把甲级防火门耐火极限记成 1.0h；本题应先判断构造对象，再核对双扇防火门应按顺序关闭。",
      actions: { detail: true },
    },
  ],
  degraded: false,
  degraded_sources: [],
};

var batchCWx = wxVm.buildLearningReportViewModel(batchCReport);
var batchCYousen = yousenVm.buildLearningReportViewModel(batchCReport);
assert.deepStrictEqual(
  batchCWx,
  batchCYousen,
  "wx and yousen Batch C view-models must stay byte-identical",
);

// learningState exposed with knowledge/ability/behavior arrays.
assert.strictEqual(batchCWx.learningState.knowledgeState[0].nodeId, "1A412010");
assert.strictEqual(batchCWx.learningState.knowledgeState[0].state, "weak");
assert.strictEqual(
  batchCWx.learningState.abilityState[0].dimension,
  "code_application",
);
assert.strictEqual(batchCWx.learningState.behaviorState[0].state, "recurring");
assert.strictEqual(batchCWx.learningState.isEmpty, false);

// The learner-facing model must present the report as a learning-state engine,
// not as raw backend enums or a thin statistics panel.
assert.strictEqual(batchCWx.evidenceEngine.title, "学习状态推断引擎");
assert.strictEqual(batchCWx.evidenceEngine.summary, "融合 10 条历史学习证据");
assert.strictEqual(batchCWx.evidenceEngine.isVisible, true);
assert.strictEqual(batchCWx.evidenceEngine.sources.length, 7);
assert.deepStrictEqual(
  batchCWx.evidenceEngine.sources.map(function (item) {
    return item.label;
  }),
  [
    "长期答题记录",
    "案例题答案",
    "采分点命中",
    "错因标签",
    "时间衰减",
    "知识图谱关系",
    "题目难度",
  ],
);
assert.strictEqual(batchCWx.evidenceEngine.sources[0].value, "8 条");
assert.strictEqual(batchCWx.evidenceEngine.sources[0].statusLabel, "已接入");
assert.strictEqual(batchCWx.evidenceEngine.sources[2].value, "1 项");
assert.strictEqual(batchCWx.evidenceEngine.sources[6].statusLabel, "待积累");

// scoringPointMap exposes 采分点 granularity label and v2 intent.
var spItem = batchCWx.scoringPointMap.items[0];
assert.strictEqual(spItem.granularity, "scoring_point");
assert.strictEqual(spItem.granularityLabel, "采分点");
assert.strictEqual(spItem.missCount, 2);
assert.deepStrictEqual(spItem.evidenceRefs, ["e1", "e2"]);
assert.strictEqual(spItem.nextActionIntent.intent_version, 2);

// prescription pulled from active v2 next_training intent.
assert.strictEqual(batchCWx.prescription.status, "active");
assert.strictEqual(batchCWx.prescription.title, "甲乙丙级耐火极限");
assert.strictEqual(batchCWx.prescription.abilityDimension, "code_application");
assert.deepStrictEqual(batchCWx.prescription.evidenceRefs, ["e1", "e2"]);
assert.strictEqual(batchCWx.prescription.steps.length, 4);
assert.strictEqual(batchCWx.prescription.steps[0].phase, "repair_root");
assert.strictEqual(batchCWx.prescription.ctaLabel, "开始训练");

// toReportPageData flattens for setData.
var batchCPage = wxVm.toReportPageData(batchCWx);
assert.strictEqual(
  batchCPage.prescriptionTitle,
  "围绕「甲乙丙级耐火极限」先完成一轮定向训练",
);
assert.strictEqual(batchCPage.prescriptionStatus, "active");
assert.strictEqual(batchCPage.prescriptionSteps.length, 4);
assert.strictEqual(batchCPage.learningStateKnowledge[0].nodeId, "1A412010");
assert.strictEqual(
  batchCPage.learningStateAbility[0].dimension,
  "code_application",
);
assert.strictEqual(batchCPage.learningStateBehavior[0].state, "recurring");
assert.strictEqual(
  batchCPage.scoringPointMapItems[0].granularityLabel,
  "采分点",
);
assert.strictEqual(batchCPage.scoringPointMapEmptyState, "");
assert.strictEqual(batchCPage.learningStateIsEmpty, false);
assert.strictEqual(batchCPage.mistakeHistoryCards.length, 1);
assert.strictEqual(batchCPage.mistakeHistoryCards[0].timeLabel, "今天 10:55");
assert.strictEqual(
  batchCPage.mistakeHistoryCards[0].questionTitle,
  "关于防火门的构造要求，下列哪项说法是正确的？",
);
assert.strictEqual(
  batchCPage.mistakeHistoryCards[0].answerLine,
  "你选：A；正确：D",
);
assert.strictEqual(
  batchCPage.mistakeHistoryCards[0].whyWrong,
  "A 选项错在把甲级防火门耐火极限记成 1.0h；本题应先判断构造对象，再核对双扇防火门应按顺序关闭。",
);
var promptLikeMistake = wxVm.buildLearningReportViewModel({
  learner_facing: {
    recent_attempts: [
      {
        title:
          "我想练习建筑构造相关的题目 请严格围绕以下当前学习锚点出题",
        result_label: "答错",
        tone: "wrong",
        answer_line: "你选：C；正确：D",
        diagnosis: "把防火门关闭顺序判断成同时关闭。",
      },
    ],
  },
});
var promptLikeMistakePage = wxVm.toReportPageData(promptLikeMistake);
assert.strictEqual(
  promptLikeMistakePage.mistakeHistoryCards[0].questionTitle,
  "建筑构造相关错题",
);
assert.ok(
  promptLikeMistakePage.mistakeHistoryCards[0].questionTitle.indexOf("我想练习") < 0,
  "mistake history should not expose training prompt text as a question title",
);
var promptLikePrescription = wxVm.buildLearningReportViewModel({
  next_training: [
    {
      title: "那出5道题",
      reason: "training_mode=mixed_rev",
      intent: {
        intent_version: 2,
        status: "active",
        concept_label: "那出5道题",
        error_label: "多选错选",
        evidence_refs: ["ev_opaque"],
        prescription_steps: [{ phase: "repair_root", question_count: 1 }],
      },
    },
  ],
});
var promptLikePrescriptionPage = wxVm.toReportPageData(promptLikePrescription);
assert.strictEqual(promptLikePrescriptionPage.prescriptionStatus, "degraded");
assert.strictEqual(promptLikePrescriptionPage.prescriptionTitle, "补一题可诊断练习");
assert.strictEqual(promptLikePrescriptionPage.prescriptionCtaLabel, "补一题诊断");
assert.strictEqual(promptLikePrescriptionPage.prescriptionEvidenceCount, 1);
assert.ok(
  promptLikePrescriptionPage.prescriptionTitle.indexOf("那出5道题") < 0,
  "prescription title should not expose prompt-like text as a training topic",
);
assert.ok(
  promptLikePrescriptionPage.prescriptionReason.indexOf("training_mode") < 0,
  "prescription reason should not expose internal mode markers",
);
assert.strictEqual(batchCPage.engineEvidenceSummary, "融合 10 条历史学习证据");
assert.strictEqual(batchCPage.engineEvidenceVisible, true);
assert.strictEqual(batchCPage.engineEvidenceSources.length, 7);
assert.strictEqual(
  batchCPage.prescriptionTitle,
  "围绕「甲乙丙级耐火极限」先完成一轮定向训练",
);
assert.strictEqual(batchCPage.prescriptionMeta.length, 3);
assert.deepStrictEqual(
  batchCPage.prescriptionMeta.map(function (item) {
    return item.label;
  }),
  ["规范应用", "同类错误复发", "2 条证据"],
);
assert.strictEqual(
  batchCPage.learningStateKnowledge[0].stateHeadline,
  "需要优先补上",
);
assert.strictEqual(
  batchCPage.learningStateKnowledge[0].actionLabel,
  "先回到这一知识点的条件边界",
);
assert.strictEqual(
  batchCPage.learningStateAbility[0].stateHeadline,
  "规范应用还不稳",
);
assert.strictEqual(
  batchCPage.learningStateBehavior[0].stateHeadline,
  "同类错误正在复发",
);
[
  batchCPage.prescriptionTitle,
  batchCPage.learningStateKnowledge[0].stateHeadline,
  batchCPage.learningStateAbility[0].stateHeadline,
  batchCPage.learningStateBehavior[0].stateHeadline,
  batchCPage.mistakeHistoryCards[0].whereWrong,
  batchCPage.mistakeHistoryCards[0].whyWrong,
].forEach(function (text) {
  assert(!/weak|recurrence|question_reading|discovery_probe|code_application/.test(text));
});

var flagOffReport = JSON.parse(JSON.stringify(batchCReport));
flagOffReport.feature_flags = {
  enabled: false,
  state_projection: false,
  action_loop: false,
};
var flagOffVm = wxVm.buildLearningReportViewModel(flagOffReport);
assert.strictEqual(
  flagOffVm.evidenceEngine.isVisible,
  false,
  "feature-flag-disabled projections must not expose the engine panel",
);
assert.strictEqual(wxVm.toReportPageData(flagOffVm).engineEvidenceVisible, false);

var zeroEvidenceFlagOnReport = {
  ok: true,
  schema_version: 2,
  feature_flags: {
    enabled: true,
    state_projection: true,
    action_loop: true,
  },
  overview: {},
  mastery: {
    overall_mastery: {
      score: 0,
      confidence: 0.2,
      status: "insufficient_evidence",
    },
    hotspots: [],
  },
  learning_state: {
    knowledge_state: [],
    ability_state: [],
    behavior_state: [],
    source_status: {
      authority: "learner_memory_events.learning_evidence",
      model: "rule_based_v1",
      grading_fact_count: 0,
      conversation_signal_count: 0,
    },
  },
  scoring_point_map: {
    items: [],
    empty_state: "no_evidence",
    source_status: {
      authority: "learner_memory_events.learning_evidence",
      total_case_event_count: 0,
      map_eligible_event_count: 0,
    },
  },
  learner_facing: {},
  learning_brain: {},
  freshness: { event_count: 0 },
  next_training: [],
};
var zeroEvidenceFlagOnVm = wxVm.buildLearningReportViewModel(
  zeroEvidenceFlagOnReport,
);
assert.strictEqual(
  zeroEvidenceFlagOnVm.evidenceEngine.isVisible,
  false,
  "synthetic mastery confidence must not light up the engine without real evidence",
);
assert.strictEqual(
  wxVm.toReportPageData(zeroEvidenceFlagOnVm).engineEvidenceSources.length,
  0,
);

var explicitZeroMasteryReport = {
  ok: true,
  schema_version: 2,
  overview: {},
  radar_dimensions: [
    {
      name: "1A411011",
      value: 0.62,
      score: 62,
      level: "normal",
      taxonomy_path: ["建筑工程技术", "建筑设计与构造", "建筑设计", "建筑物分类与构成"],
    },
  ],
  mastery: {
    overall_mastery: {
      score: 0,
      confidence: 0.86,
      status: "stable",
    },
    groups: [],
    hotspots: [],
    review_summary: { total_due: 1, overdue_count: 0 },
  },
  learner_facing: {},
  learning_brain: {},
  freshness: { event_count: 2 },
  next_training: [],
};
var explicitZeroMasteryPage = wxVm.toReportPageData(
  wxVm.buildLearningReportViewModel(explicitZeroMasteryReport),
);
assert.strictEqual(
  explicitZeroMasteryPage.overallMastery,
  0,
  "explicit zero mastery must survive page-data normalization",
);
assert.strictEqual(
  explicitZeroMasteryPage.overviewScore,
  0,
  "report overview score must not hide a real zero mastery behind radar fallback",
);

// Keyword-only / rubric_pending honesty.
var pendingReport = {
  ok: true,
  schema_version: 2,
  overview: {},
  learning_state: {
    knowledge_state: [],
    ability_state: [],
    behavior_state: [],
    source_status: {},
  },
  scoring_point_map: {
    items: [],
    empty_state: "rubric_pending",
    source_status: {},
  },
  next_training: [],
};
var pendingVm = wxVm.buildLearningReportViewModel(pendingReport);
assert.strictEqual(pendingVm.scoringPointMap.emptyState, "rubric_pending");
assert.strictEqual(
  pendingVm.scoringPointMap.emptyStateLabel,
  "本题暂无可拆采分点，已先按审题要点收集",
);
assert.strictEqual(pendingVm.learningState.isEmpty, true);
assert.strictEqual(
  pendingVm.evidenceEngine.isVisible,
  false,
  "empty/degraded projections must not show the engine panel",
);
assert.strictEqual(
  wxVm.toReportPageData(pendingVm).engineEvidenceSources.length,
  0,
  "page data must keep the engine panel hidden when no active evidence exists",
);
// Degraded fallback prescription must NOT fabricate a strong action.
assert.strictEqual(pendingVm.prescription.status, "degraded");

// Keyword-only granularity → "审题要点" UI label.
var keywordReport = {
  ok: true,
  schema_version: 2,
  overview: {},
  scoring_point_map: {
    items: [
      {
        point_id: "kw1",
        label: "对角线布点",
        granularity: "keyword_only",
        rubric_mode: "projected_rubric",
        miss_count: 1,
        evidence_refs: ["k1"],
        next_action: {
          kind: "discovery_probe",
          intent: { intent_version: 2, status: "degraded" },
        },
      },
    ],
    empty_state: "",
    source_status: {},
  },
  next_training: [],
};
var keywordVm = wxVm.buildLearningReportViewModel(keywordReport);
assert.strictEqual(
  keywordVm.scoringPointMap.items[0].granularityLabel,
  "审题要点",
);

// WXML render contract: report.wxml must surface the four Batch C labels.
var reportWxml = fs.readFileSync(
  path.join(__dirname, "../pages/report/report.wxml"),
  "utf8",
);
assert(
  reportWxml.indexOf("今天先做什么") >= 0,
  "wx report.wxml must orient the prescription as the next learning action",
);
assert(
  reportWxml.indexOf("学习状态推断引擎") >= 0,
  "wx report.wxml must show the learning-state engine frame",
);
assert(
  reportWxml.indexOf("engineEvidenceVisible") >= 0,
  "wx report.wxml must gate the engine panel on backend evidence visibility",
);
assert(
  reportWxml.indexOf("为什么这样安排") >= 0,
  "wx report.wxml must explain why the prescription was generated",
);
assert(
  reportWxml.indexOf("错题历史怎么证明") >= 0,
  "wx report.wxml must make the learning-state diagnosis concrete through wrong-attempt history",
);
assert(
  reportWxml.indexOf("mistakeHistoryCards") >= 0,
  "wx report.wxml must render concrete mistake history cards from backend attempts",
);
assert(
  reportWxml.indexOf("知识状态") >= 0,
  "wx report.wxml must show 知识状态",
);
assert(
  reportWxml.indexOf("能力状态") >= 0,
  "wx report.wxml must show 能力状态",
);
assert(
  reportWxml.indexOf("行为状态") >= 0,
  "wx report.wxml must show 行为状态",
);
assert(
  reportWxml.indexOf("采分点怎么补") >= 0,
  "wx report.wxml must frame scoring-point gaps as a repair path",
);
assert(
  reportWxml.indexOf("scoringPointMapEmptyLabel") >= 0,
  "wx report.wxml must surface honest empty state",
);

console.log("PASS test_report_view_model.js (Batch C extension)");
