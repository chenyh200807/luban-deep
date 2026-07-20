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
  note_assets: {
    items: [
      {
        note_id: "note_1",
        card_type: "review_note",
        title: "防水节点学习卡",
        summary: "复测节点构造。",
        source_linked: true,
        source_label: "来自一次答疑",
        action: { label: "测一下", type: "probe", turn_id: "turn_1" },
      },
    ],
  },
  today_tasks: [
    {
      task_id: "note:note_1",
      title: "防水节点学习卡",
      subtitle: "复测节点构造。",
      source: "note_assets",
      note_id: "note_1",
      action: { label: "测一下", type: "probe" },
    },
  ],
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
assert.strictEqual(yousenVm.toReportPageData(vm).noteAssets[0].noteId, "note_1");
assert.strictEqual(yousenVm.toReportPageData(vm).todayTasks[0].source, "note_assets");

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
    review_summary: { total_due: 9, overdue_count: 2 },
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
  pack_review: {
    enabled: true,
    degraded: false,
    authority: "revalidation_queue",
    due: [{ pack_id: "F16", probe_id: "probe_f16" }],
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
  grading_to_brain_loop: {
    status: "needs_retest",
    next_required_action: "complete_revalidation_probe",
    evidence_refs: ["attempt_m32_001", "attempt_m32_002"],
    current_action: {
      title: "同类 exact_required 术语题复测",
      action_type: "retest_or_targeted_practice",
      prescription_authority: "training_intent",
    },
    stages: [
      { key: "grading_result", label: "本次批改", status: "ready" },
      { key: "learner_claim", label: "长期画像", status: "ready" },
      { key: "personalization_context", label: "个性化上下文", status: "ready" },
      { key: "next_action", label: "下一步动作", status: "ready" },
      { key: "retest", label: "复测结果", status: "due" },
    ],
    authority: {
      grading_evidence: "learner_memory_events.learning_evidence",
      learner_model: "LearningBrainReadModel",
      personalization: "PersonalizationContextPack",
      action: "training_intent",
      retest: "prescription_outcomes",
    },
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
assert.strictEqual(loopPageData.reviewSummary.state, "known");
assert.strictEqual(loopPageData.gradingLoopStatus, "needs_retest");
assert.strictEqual(loopPageData.gradingLoopNextRequiredAction, "complete_revalidation_probe");
assert.deepStrictEqual(loopPageData.gradingLoopEvidenceRefs, ["attempt_m32_001", "attempt_m32_002"]);
assert.strictEqual(loopPageData.gradingLoopStages.length, 5);
assert.strictEqual(loopPageData.gradingLoopAuthority.personalization, "PersonalizationContextPack");

var source = fs.readFileSync(reportPath, "utf8");
var wxmlSource = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/report/report.wxml"),
  "utf8",
);
assert.strictEqual(
  wxmlSource.indexOf("当前证据未发现待补盲点"),
  -1,
  "诊断未知不得冒充未发现盲点",
);
assert(
  source.indexOf("learning-report-view-model") >= 0 &&
    source.indexOf("buildLearningReportViewModel") >= 0 &&
    source.indexOf("toReportPageData") >= 0 &&
    source.indexOf("prescriptionAuthority") >= 0 &&
    source.indexOf("gradingLoopStatus") >= 0,
  "yousen report page must consume the shared learning report view model",
);
assert(
  wxmlSource.indexOf("gradingLoopStages") >= 0 &&
    wxmlSource.indexOf("gradingLoopStatus") >= 0 &&
    wxmlSource.indexOf("gradingLoopEvidenceRefs") >= 0,
  "yousen report page must render the Grading-to-Brain loop projection",
);
var hydrateBody = source.split("_hydrateFromUnifiedReport(snapshot)")[1].split("onReady()")[0];
assert(hydrateBody.indexOf("_normalizeRadarDimensions(") < 0);
assert(hydrateBody.indexOf("_buildRadarViewModel(") < 0);
assert(hydrateBody.indexOf("_normalizeLearningBrainPayload(") < 0);

// ── 10e:pack_lifecycle → 掌握地图投影(四态 + 蓝环第五态,双轨) ──
var lifecycleReport = {
  schema_version: 2,
  pack_lifecycle: {
    authority: "pack_lifecycle_projection.read_model",
    degraded: false,
    packs: {
      F16: { lifecycle_state: "mastered", blue_ring: "empty" },
      N01: { lifecycle_state: "exposed", blue_ring: "exposed" },
      C01: { lifecycle_state: "practiced", blue_ring: "exposed" },
      J01: { lifecycle_state: "dormant", blue_ring: "empty" },
      Q02: { lifecycle_state: "unlearned", blue_ring: "empty" },
    },
  },
  long_term_analytics: {
    recurrent_errors: [],
    progression_summary: {
      trend_direction: "improving",
      active_weak_count: 0,
      recurrent_error_count: 0,
    },
  },
};
assert.deepStrictEqual(
  wxVm.buildPackMasteryMap(lifecycleReport, { lessons: [{ pack_id: "f16", title: "防水" }] }),
  yousenVm.buildPackMasteryMap(lifecycleReport, { lessons: [{ pack_id: "f16", title: "防水" }] }),
);
var map = yousenVm.buildPackMasteryMap(lifecycleReport, {
  lessons: [{ pack_id: "f16", title: "防水" }, { pack_id: "N01", title: "网络计划" }],
});
assert.strictEqual(map.available, true);
assert.strictEqual(map.packUniverse, 5);
// 四态掌握轨映射
var byId = {};
map.cells.forEach(function (cell) { byId[cell.packId] = cell; });
assert.strictEqual(byId.F16.state, "stable");
assert.strictEqual(byId.F16.stateLabel, "稳了");
assert.strictEqual(byId.C01.state, "watch");
assert.strictEqual(byId.C01.stateLabel, "再看一眼");
assert.strictEqual(byId.J01.state, "reverify");
assert.strictEqual(byId.J01.stateLabel, "待复验");
assert.strictEqual(byId.Q02.state, "unlearned");
assert.strictEqual(byId.Q02.stateLabel, "未学");
// 蓝环第五态:接触轨,文案永带"待验证";掌握轨已动(practiced)则蓝环不再呈现
assert.strictEqual(byId.N01.state, "blue");
assert.strictEqual(byId.N01.blueRing, true);
assert(byId.N01.stateLabel.indexOf("待验证") >= 0, "blue state copy must carry 待验证");
assert.strictEqual(byId.C01.blueRing, false, "mastery track takes over once practiced — no double track on one cell");
// 蓝环绝不进掌握色阶计数
assert.deepStrictEqual(map.counts, { stable: 1, watch: 1, reverify: 1, unlearned: 1, blue: 1 });
// 绿灯 lessons join(大小写归一)
assert.strictEqual(byId.F16.green, true);
assert.strictEqual(byId.F16.title, "防水");
assert.strictEqual(byId.Q02.green, false);
// manifest 可含内部 pack，但“40 站全景”只投影正式教学路线中的 pack；
// 标题、cells 与四态计数必须同源，不能再把 E01 算成第 41 站。
var formalRouteReport = JSON.parse(JSON.stringify(lifecycleReport));
formalRouteReport.pack_lifecycle.packs.E01 = {
  lifecycle_state: "unlearned",
  blue_ring: "empty",
};
var formalLessons = {
  lessons: [
    { pack_id: "F16", title: "防水" },
    { pack_id: "N01", title: "网络计划" },
    { pack_id: "E01", title: "内部计价包" },
  ],
  teaching_points: [
    { pack_id: "F16" },
    { pack_id: "N01" },
    { pack_id: "C01" },
    { pack_id: "J01" },
    { pack_id: "Q02" },
  ],
};
var formalMap = yousenVm.buildPackMasteryMap(formalRouteReport, formalLessons);
assert.deepStrictEqual(
  wxVm.buildPackMasteryMap(formalRouteReport, formalLessons),
  formalMap,
);
assert.strictEqual(formalMap.packUniverse, 5);
assert.strictEqual(formalMap.cells.some(function (cell) { return cell.packId === "E01"; }), false);
assert.deepStrictEqual(formalMap.counts, { stable: 1, watch: 1, reverify: 1, unlearned: 1, blue: 1 });
// 降级不造数:packs 空 → available=false
assert.strictEqual(yousenVm.buildPackMasteryMap({}, null).available, false);
assert.strictEqual(
  yousenVm.buildPackMasteryMap({ pack_lifecycle: { degraded: true, packs: { F16: { lifecycle_state: "unlearned" } } } }, null).degraded,
  true,
);

// ── 10e:方向性趋势 + 风险档位词(read model 字段纯翻译) ──
var lifecyclePageData = yousenVm.toReportPageData(
  yousenVm.buildLearningReportViewModel(lifecycleReport),
);
assert.strictEqual(lifecyclePageData.trendDirection, "improving");
assert(lifecyclePageData.trendNarrative.length > 0, "improving trend must produce a directional narrative");
assert.strictEqual(lifecyclePageData.recurrentErrorCount, 0);
// 无 mastery status → 档位词兜底"待评估",不造档
assert.strictEqual(lifecyclePageData.riskGearLabel, "待评估");
var gearPageData = yousenVm.toReportPageData(
  yousenVm.buildLearningReportViewModel({
    schema_version: 2,
    mastery: { overall_mastery: { score: 20, status: "weak" }, groups: [], hotspots: [] },
  }),
);
assert.strictEqual(gearPageData.riskGearLabel, "中高");
assert.strictEqual(gearPageData.riskGearTone, "warn");

// ── 10e:四态雷达计数,observed 不再折进 normal ──
var fourStateRadar = yousenVm.toReportPageData(
  yousenVm.buildLearningReportViewModel({
    schema_version: 2,
    radar_dimensions: [
      { name: "建筑设计与构造", value: 0.8, score: 80, status: "strong" },
      { name: "建筑工程施工技术", value: 0.5, score: 50, status: "normal" },
      { name: "施工进度管理", value: 0.2, score: 20, status: "weak" },
      { name: "施工安全管理", value: 0, score: 0, status: "observed" },
    ],
  }),
);
assert.strictEqual(fourStateRadar.strongCount, 1);
assert.strictEqual(fourStateRadar.normalCount, 1, "observed must NOT be folded into normal");
assert.strictEqual(fourStateRadar.weakCount, 1);
assert.strictEqual(fourStateRadar.observedCount, 1, "observed (未学) must surface as its own fourth state");

// ── 每站六步进展全景:掌握地图点格「按 pack 取六步」派生 ──────────────
// 复用共享 stationJourneyFor 的严格校验;缺 pack/降级/校验不过 → ready=false
// + 中性占位「正在核对服务端学习记录」,前端零阶段推断。
var journeyReport = {
  schema_version: 2,
  station_journey: {
    authority: "station_journey_projection.read_model",
    schema_version: 1,
    degraded: false,
    packs: {
      N01: {
        pack_id: "N01",
        journey_state: "active",
        current_step_id: "practice",
        steps: [
          { id: "lesson", status: "completed" },
          { id: "practice", status: "current" },
          { id: "diagnosis", status: "upcoming" },
          { id: "immediate_confirm", status: "upcoming" },
          { id: "due_validation", status: "upcoming" },
          { id: "followup", status: "future" },
        ],
      },
    },
  },
};

// wx 与 yousen 报表 vm 必须给出逐字节相同的派生(单一权威,双树镜像)。
assert.deepStrictEqual(
  wxVm.buildStationJourneyPanorama(journeyReport, "N01"),
  yousenVm.buildStationJourneyPanorama(journeyReport, "N01"),
);

var panorama = yousenVm.buildStationJourneyPanorama(journeyReport, "n01");
assert.strictEqual(panorama.ready, true);
assert.strictEqual(panorama.packId, "N01", "pack id normalized to upper case");
assert.strictEqual(panorama.steps.length, 6);
assert.deepStrictEqual(
  panorama.steps.map(function (s) { return s.label; }),
  ["动画讲懂", "训练 5 题", "错因讲评", "轻练确认", "到期验证", "后续抽查"],
  "six canonical steps in fixed order",
);
assert.strictEqual(panorama.steps[0].state, "done");
assert.strictEqual(panorama.steps[1].state, "current");
assert.strictEqual(panorama.currentStepId, "practice");
assert.strictEqual(panorama.placeholder, "", "ready panorama carries no placeholder");
// 就绪文案不得硬编码服务端没签的复习周期(禁"明天/3 天后")。
panorama.steps.concat([{ label: panorama.statusText }, { label: panorama.foot }]).forEach(function (s) {
  assert.strictEqual(/明天|昨天|后天|\d+\s*天后/.test(s.label || ""), false,
    "panorama copy must not fabricate a schedule the server did not sign: " + s.label);
});

// degraded 投影 → fail-quiet:ready=false + 中性占位,不渲染六步。
var degradedJourneyReport = JSON.parse(JSON.stringify(journeyReport));
degradedJourneyReport.station_journey.degraded = true;
var degradedPanorama = yousenVm.buildStationJourneyPanorama(degradedJourneyReport, "N01");
assert.strictEqual(degradedPanorama.ready, false, "degraded projection must fail closed");
assert.strictEqual(degradedPanorama.available, false);
assert.deepStrictEqual(degradedPanorama.steps, [], "no six-step render under degrade");
assert.strictEqual(degradedPanorama.placeholder, "正在核对服务端学习记录");

// 投影缺该 pack → 同样 fail-quiet(取投影里没有的 A01)。
var missingPackPanorama = yousenVm.buildStationJourneyPanorama(journeyReport, "A01");
assert.strictEqual(missingPackPanorama.ready, false, "absent pack must not borrow another station's progress");
assert.strictEqual(missingPackPanorama.placeholder, "正在核对服务端学习记录");
assert.strictEqual(missingPackPanorama.statusText, "");

// 空 report / 垃圾入参不抛,一律占位。
assert.strictEqual(yousenVm.buildStationJourneyPanorama({}, "N01").ready, false);
assert.strictEqual(yousenVm.buildStationJourneyPanorama(null, "").placeholder, "正在核对服务端学习记录");

// 未就绪文案红线:禁「看穿/识破/揭穿/露馅」审视词(中性呈现)。
[degradedPanorama, missingPackPanorama, panorama].forEach(function (p) {
  ["placeholder", "statusText", "foot"].forEach(function (field) {
    var text = String(p[field] || "");
    assert.strictEqual(/看穿|识破|揭穿|露馅/.test(text), false,
      "panorama copy must stay warm/neutral, no scrutiny words: " + field + "=" + text);
  });
});

// ── 轻练确认重入口:服务端投影只读字段 → 面板 confirmEntry(fail-closed) ──
// 有错题且供给覆盖的真实服务端形状:confirm current(带 confirm_facts/
// confirm_anchor)+ due_validation scheduled 同在(服务端合法多 actionable)。
var confirmJourneyReport = {
  schema_version: 2,
  station_journey: {
    authority: "station_journey_projection.read_model",
    schema_version: 1,
    degraded: false,
    packs: {
      N01: {
        pack_id: "N01",
        journey_state: "active",
        current_step_id: "immediate_confirm",
        steps: [
          { id: "lesson", status: "completed", reason: "lesson_viewed" },
          { id: "practice", status: "completed" },
          { id: "diagnosis", status: "completed", reason: "canonical_feedback_ready" },
          {
            id: "immediate_confirm",
            status: "current",
            reason: "safe_confirm_available",
            confirm_facts: ["fact-n01", "fact x"],
            confirm_anchor: "terminal_forward",
          },
          { id: "due_validation", status: "scheduled" },
          { id: "followup", status: "future" },
        ],
      },
    },
  },
};

// 双树 vm 派生逐字节一致(单一权威)。
assert.deepStrictEqual(
  wxVm.buildStationJourneyPanorama(confirmJourneyReport, "N01"),
  yousenVm.buildStationJourneyPanorama(confirmJourneyReport, "N01"),
);

var confirmPanorama = yousenVm.buildStationJourneyPanorama(confirmJourneyReport, "N01");
assert.strictEqual(
  confirmPanorama.ready,
  true,
  "server-legal multi-actionable shape (confirm current + due scheduled) must not fail closed",
);
assert.strictEqual(confirmPanorama.currentStepId, "immediate_confirm");
assert.strictEqual(confirmPanorama.confirmEntry.visible, true, "panel CTA must appear");
assert.deepStrictEqual(confirmPanorama.confirmEntry.facts, ["fact-n01", "fact x"]);
assert.strictEqual(confirmPanorama.confirmEntry.anchor, "terminal_forward");
// URL 与回执现场 retest.js goConfirmFacts 同形:逐 fact 编码 + 字面逗号连接。
assert.strictEqual(
  confirmPanorama.confirmEntry.url,
  "/packageDeeptutor/pages/luban/retest/retest?pack_id=N01" +
    "&mode=forward&confirm_facts=fact-n01,fact%20x" +
    "&confirm_anchor=terminal_forward",
  "confirm session url must byte-match the receipt-scene entry shape",
);

// fail-closed:字段缺失/空/状态不符 → 不亮 CTA,绝不猜。
function confirmReportWith(patch) {
  var clone = JSON.parse(JSON.stringify(confirmJourneyReport));
  var step = clone.station_journey.packs.N01.steps[3];
  Object.keys(patch).forEach(function (key) {
    if (patch[key] === undefined) delete step[key];
    else step[key] = patch[key];
  });
  return clone;
}
[
  confirmReportWith({ confirm_facts: undefined }),
  confirmReportWith({ confirm_facts: [] }),
  confirmReportWith({ confirm_facts: ["", "  "] }),
  confirmReportWith({ confirm_anchor: undefined }),
  confirmReportWith({ confirm_anchor: "" }),
  confirmReportWith({ reason: "some_new_reason" }),
].forEach(function (broken, index) {
  var p = yousenVm.buildStationJourneyPanorama(broken, "N01");
  assert.strictEqual(
    p.confirmEntry.visible,
    false,
    "missing/empty reentry fields must fail closed, case " + index,
  );
  assert.strictEqual(p.confirmEntry.url, "", "no url may be fabricated, case " + index);
});
// confirm 非 current(unavailable)→ 即使字段被伪造塞入也不亮。
var notCurrent = confirmReportWith({ status: "unavailable", reason: "safe_confirm_unavailable" });
notCurrent.station_journey.packs.N01.current_step_id = "due_validation";
assert.strictEqual(
  yousenVm.buildStationJourneyPanorama(notCurrent, "N01").confirmEntry.visible,
  false,
  "non-current confirm step must never light the reentry CTA",
);
// 未就绪(降级)→ confirmEntry 同步 fail-closed。
assert.strictEqual(degradedPanorama.confirmEntry.visible, false);
assert.strictEqual(degradedPanorama.confirmEntry.url, "");

// 报表页必须消费共享派生并以内联展开面板渲染(不新起 overlay 体系)。
assert(
  source.indexOf("buildStationJourneyPanorama") >= 0 &&
    source.indexOf("stationJourneyPanel") >= 0 &&
    source.indexOf("openMasteryCell") >= 0,
  "report page must consume the shared per-station six-step derivation",
);
assert(
  wxmlSource.indexOf("stationJourneyPanel") >= 0 &&
    wxmlSource.indexOf("lr-sjp-steps") >= 0,
  "report wxml must render the inline six-step panorama panel",
);
// 轻练确认重入口:面板 CTA 必须接线(js handler + wxml 可见性门 + 暖文案)。
assert(
  source.indexOf("goConfirmFromPanorama") >= 0 &&
    wxmlSource.indexOf("goConfirmFromPanorama") >= 0 &&
    wxmlSource.indexOf("stationJourneyPanel.confirmEntry.visible") >= 0 &&
    wxmlSource.indexOf("去确认错题 · 当场弄懂") >= 0,
  "report page must wire the confirm reentry CTA behind the server-projected visibility gate",
);
// 掌握地图 wxml 不得再宣称审视口吻;点格提示改为看六步进展。
assert.strictEqual(
  /看穿|识破|揭穿|露馅/.test(wxmlSource),
  false,
  "report wxml must not use scrutiny words in mastery-map / panorama copy",
);

console.log("PASS test_report_view_model.js");
