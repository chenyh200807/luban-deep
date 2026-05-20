// test_report_learning_brain.js — Learning Brain report surface contract
// Run: node wx_miniprogram/tests/test_report_learning_brain.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

function injectModule(modulePath, exportsValue) {
  require.cache[modulePath] = {
    id: modulePath,
    filename: modulePath,
    loaded: true,
    exports: exportsValue,
  };
}

async function run() {
  const reportPath = path.join(__dirname, "../pages/report/report.js");
  const apiPath = path.join(__dirname, "../utils/api.js");
  const helpersPath = path.join(__dirname, "../utils/helpers.js");
  const wxmlPath = path.join(__dirname, "../pages/report/report.wxml");
  const wxssPath = path.join(__dirname, "../pages/report/report.wxss");
  const apiSource = fs.readFileSync(apiPath, "utf8");
  const reportWxml = fs.readFileSync(wxmlPath, "utf8");
  const reportWxss = fs.readFileSync(wxssPath, "utf8");
  const reportSource = fs.readFileSync(reportPath, "utf8");

  // 静态契约：mini-program 入口不得消费 legacy_compat（plan §数据契约 + Open Gaps G5）
  assert(
    reportSource.indexOf("legacy_compat") < 0,
    "wx report page must not consume legacy_compat — it is for backend reconciliation only",
  );
  // 静态契约：onShow 必须触发 unified report 主入口 _loadLearningReport；retry 也只走 unified
  assert(
    /onShow\s*\(\)[\s\S]*?_loadLearningReport\s*\(/.test(reportSource),
    "wx report onShow must invoke the unified _loadLearningReport entry",
  );
  assert(
    reportSource.indexOf("retryRadar()") >= 0 &&
      /retryRadar\(\)\s*\{[\s\S]*?_loadLearningReport\s*\(/.test(reportSource),
    "wx report retryRadar must re-enter the unified _loadLearningReport entry",
  );

  assert(
    apiSource.indexOf("/api/v1/mobile/learning-report") >= 0,
    "api should expose the unified learning report read model endpoint",
  );
  assert(
    fs.readFileSync(reportPath, "utf8").indexOf("api.getLearningReport(100)") >=
      0 &&
      fs.readFileSync(reportPath, "utf8").indexOf("this._loadOverview();") <
        0 &&
      fs
        .readFileSync(reportPath, "utf8")
        .indexOf("this._loadLearningBrain();") < 0 &&
      fs.readFileSync(reportPath, "utf8").indexOf("this._loadRadar();") < 0 &&
      fs.readFileSync(reportPath, "utf8").indexOf("this._loadMastery();") < 0,
    "report page should make the learning-report read model the page decision authority",
  );
  assert(
    reportSource.indexOf('return "综合能力"') < 0 &&
      reportSource.indexOf('return "知识点 " + text.toUpperCase()') >= 0,
    "report page must not collapse taxonomy codes into the meaningless 综合能力 label",
  );
  assert(
    reportSource.indexOf('code === "M01"') >= 0 &&
      reportSource.indexOf('code === "M10"') >= 0,
    "report page stale-data fallback should cover the full MCQ error taxonomy",
  );
  assert(
    apiSource.indexOf(".catch(function") < 0 ||
      apiSource.indexOf("runLearningBrainHarnessCaseGrading(") >
        apiSource.indexOf("function getLearningBrainProjection"),
    "projection read should not silently write local QA harness events",
  );
  assert(
    reportWxml.indexOf("当前可信结论") >= 0 &&
      reportWxml.indexOf("证据流") >= 0 &&
      reportWxml.indexOf("训练闭环") >= 0 &&
      reportWxml.indexOf("下一步训练") >= 0,
    "report should render the Learning Brain visible chain sections",
  );
  assert(
    reportWxml.indexOf("learningBrainGraphStats.typedGraphEdgeCount") >= 0,
    "report should expose typed graph edge count",
  );
  assert(
    reportWxml.indexOf('wx:for="{{item.eventIds}}"') >= 0,
    "report should render compact event ids instead of raw JSON",
  );
  assert(
    reportWxml.indexOf("{{item.levelLabel || item.level}}") >= 0 &&
      reportWxml.indexOf("event {{item.eventId}}") < 0,
    "report should render learner-facing Chinese labels instead of machine labels",
  );
  assert(
    reportWxml.indexOf("JSON.stringify") < 0 &&
      reportWxml.indexOf("compiled_objects") < 0,
    "report surface should not dump long projection JSON",
  );
  assert(
    fs.readFileSync(reportPath, "utf8").indexOf("CHAPTER_CODE_LABELS") < 0 &&
      fs
        .readFileSync(reportPath, "utf8")
        .indexOf("LEARNING_BRAIN_OBJECT_LABELS") < 0 &&
      fs
        .readFileSync(reportPath, "utf8")
        .indexOf("LEARNING_BRAIN_EDGE_LABELS") < 0 &&
      fs
        .readFileSync(reportPath, "utf8")
        .indexOf("LEARNING_BRAIN_ERROR_LABELS") < 0 &&
      fs.readFileSync(reportPath, "utf8").indexOf("question_tests_concept:") <
        0,
    "report page should not keep Learning Brain taxonomy truth in the UI layer",
  );
  assert(
    reportWxss.indexOf(".level-L1_repeated") >= 0 &&
      reportWxss.indexOf(".level-L2_confirmed") >= 0 &&
      reportWxss.indexOf(".chain-not-improved") >= 0,
    "report styles should visually distinguish L1/L2 evidence levels and training outcomes",
  );

  let pageDef = null;
  global.Page = function (definition) {
    pageDef = definition;
  };
  global.getApp = function () {
    return {
      globalData: {},
      checkAuth: function (cb) {
        if (cb) cb();
      },
    };
  };
  global.wx = {};

  const mockApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getLearningBrainProjection: async function () {
      return {
        data: {
          projection_subject: "construction_exam_learning_truth",
          event_count: 2,
          created_claim_count: 1,
          typed_graph_edge_count: 7,
          weak_points: [
            {
              concept_id: "1A432000",
              error_code: "E02",
              display_title: "工程招标投标与合同管理 上出现 采分点遗漏 错因",
              display_meta:
                "知识点：工程招标投标与合同管理；错因：采分点遗漏；案例题补强",
              evidence_level: "L1_repeated",
              evidence_level_label: "重复出现",
              supporting_event_ids: ["evt1abcdef", "evt2abcdef"],
            },
          ],
          compiled_objects: {
            "concept:1A432000": {
              current_truth: "专项施工方案程序存在重复漏点",
              evidence_level: "L2_confirmed",
              supporting_event_ids: ["evt_confirmed_001"],
            },
          },
          visible_sections: {
            current_truth: [
              {
                object_key: "concept:1A432000",
                object_type: "concept",
                current_truth: "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                evidence_level: "L2_confirmed",
                evidence_level_label: "已确认",
                display_label: "知识点",
                display_title: "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                display_meta: "知识点：工程招标投标与合同管理",
                supporting_event_ids: ["evt_confirmed_001"],
              },
              {
                object_key:
                  "error:我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题:M07",
                object_type: "error",
                display_title:
                  "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 上出现 M07 错因",
                display_meta: "错因：错因 M07",
                evidence_level: "L0_observed",
                supporting_event_ids: ["e8b7f3a8123456782c60"],
              },
            ],
            evidence_flow: [
              {
                event_id: "evt1abcdef",
                edge_type: "question_tests_concept",
                display_label: "题目考查知识点",
                display_title: "题目考查知识点",
                display_path:
                  "案例题：专项训练 001 → 知识点：工程招标投标与合同管理",
              },
              {
                event_id: "evt2abcdef",
                edge_type: "training_not_improved_error",
                display_label: "训练后仍需巩固",
                display_title: "训练后仍需巩固",
                display_path:
                  "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
              },
              {
                event_id: "e8b7f3a8123456782c60",
                edge_type: "error_points_to_training",
                display_title:
                  "我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 上出现 M06 错因",
                display_path:
                  "训练建议：practice / 我想练习主体结构相关的题目 请严格围绕以下当前学习锚点出题 -> 案例题： q_1",
              },
            ],
            next_training: [
              {
                concept_id: "1A432000",
                error_code: "E02",
                claim: "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                display_label: "训练建议",
                display_title: "工程招标投标与合同管理 上出现 采分点遗漏 错因",
                display_meta:
                  "知识点：工程招标投标与合同管理；错因：采分点遗漏；案例题补强",
              },
            ],
          },
          typed_graph_edges: [
            {
              edge_type: "question_tests_concept",
              from: { id: "wechat-harness-case-001", type: "question" },
              to: { id: "1A432000", type: "concept" },
              evidence_event_id: "evt1abcdef",
              display_title: "题目考查知识点",
              display_path:
                "案例题：专项训练 001 → 知识点：工程招标投标与合同管理",
            },
            {
              edge_type: "error_points_to_training",
              from: { id: "E02", type: "error" },
              to: { id: "1A432000:training", type: "training" },
              evidence_event_id: "evt2abcdef",
              display_title: "错因指向训练",
              display_path:
                "错因：采分点遗漏 → 训练建议：工程招标投标与合同管理",
            },
          ],
          graph_chain: {
            training_uses_question: [
              {
                edge_type: "training_uses_question",
                from: { id: "1A432000:training", type: "next_training" },
                to: { id: "wechat-harness-case-002", type: "question" },
                reason_edge_event_id: "evt2abcdef",
                display_path: "训练建议：案例题补强 → 案例题：专项训练 002",
              },
            ],
            training_not_improved_error: [
              {
                edge_type: "training_not_improved_error",
                from: { id: "1A432000:training", type: "next_training" },
                to: { id: "1A432000:E02", type: "error" },
                reason_edge_event_id: "evt2abcdef",
                display_meta:
                  "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
                display_path:
                  "训练建议：案例题补强 → 错因：工程招标投标与合同管理 / 采分点遗漏",
              },
            ],
          },
          grading_results: [
            {
              next_training_signal: {
                concept: "1A432000",
                focus: "危险性较大工程专项方案程序",
                mode: "projected_rubric",
              },
            },
          ],
        },
      };
    },
    getLearningReport: async function () {
      return {
        data: {
          ok: true,
          schema_version: 1,
          authority: {
            read_model: "learning-report-read-model",
            progress_source: "learner_memory_events.learning_evidence",
            learning_brain_source: "dry_run_learning_evidence",
            deprecated_page_sources: [],
          },
          degraded: false,
          degraded_sources: [],
          source_status: {},
          freshness: {
            event_count: 2,
            unknown_date_count: 0,
            window_truncated: false,
          },
          overview: {
            today_done: 1,
            daily_target: 30,
            streak_days: 1,
            due_today_count: 0,
            weak_node_count: 1,
            focus_hint: "优先补强 工程招标投标与合同管理",
            learner_level: "beginner",
            study_tip: "先补关键采分点",
          },
          mastery: {
            overall_mastery: 20,
            groups: [
              {
                name: "需要加强",
                avg_mastery: 20,
                chapters: [{ name: "工程招标投标与合同管理", mastery: 20 }],
              },
            ],
            hotspots: [{ name: "工程招标投标与合同管理", mastery: 20 }],
            review_summary: { total_due: 0, overdue_count: 0 },
          },
          radar_dimensions: [{ name: "工程招标投标与合同管理", value: 0.2 }],
          learning_brain: await this.getLearningBrainProjection(),
        },
      };
    },
  };

  injectModule(apiPath, mockApi);
  injectModule(helpersPath, {});
  delete require.cache[reportPath];
  require(reportPath);

  const ctx = {
    data: {},
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
  };

  await pageDef._loadLearningBrain.call(ctx);

  assert.strictEqual(ctx.data.learningBrainLoading, false);
  assert.strictEqual(ctx.data.learningBrainError, false);
  assert.strictEqual(ctx.data.learningBrainEmpty, false);
  assert.strictEqual(ctx.data.learningBrainGraphStats.typedGraphEdgeCount, 7);
  assert.strictEqual(ctx.data.learningBrainGraphStats.eventCount, 2);
  assert.strictEqual(ctx.data.learningBrainTruths[0].level, "L2_confirmed");
  assert.strictEqual(ctx.data.learningBrainTruths[0].levelLabel, "已确认");
  assert(
    ctx.data.learningBrainTruths[0].meta.indexOf("工程招标投标与合同管理") >=
      0 && ctx.data.learningBrainTruths[0].meta.indexOf("concept:") < 0,
    "compiled truth meta should use backend display label",
  );
  assert.strictEqual(ctx.data.learningBrainEvidence[0].type, "题目考查知识点");
  assert(
    ctx.data.learningBrainEvidence[0].path.indexOf("案例题") >= 0 &&
      ctx.data.learningBrainEvidence[0].path.indexOf(
        "知识点：工程招标投标与合同管理",
      ) >= 0,
    "evidence path should translate typed graph nodes",
  );
  assert(
    ctx.data.learningBrainEvidence.some(function (item) {
      return item.type === "训练后仍需巩固";
    }),
    "visible evidence should include the training outcome edge",
  );
  assert.strictEqual(
    ctx.data.learningBrainChains[0].outcome,
    "本次训练结果：未改善",
  );
  assert.strictEqual(ctx.data.learningBrainChains[0].tone, "not-improved");
  assert(
    ctx.data.learningBrainChains[0].title.indexOf("采分点遗漏") >= 0 &&
      ctx.data.learningBrainChains[0].training.indexOf(
        "工程招标投标与合同管理",
      ) >= 0 &&
      ctx.data.learningBrainChains[0].question.indexOf("案例题") >= 0,
    "visible chain should connect readable error, recommended training, and selected question",
  );
  assert(
    ctx.data.learningBrainTraining[0].meta.indexOf("工程招标投标与合同管理") >=
      0,
    "training recommendation should show taxonomy label",
  );
  assert.strictEqual(
    ctx.data.learningBrainGraphStats.projectionSubjectLabel,
    "建筑实务学习事实",
  );
  assert(
      JSON.stringify(ctx.data).indexOf("concept:1A432000") < 0 &&
      JSON.stringify(ctx.data).indexOf("question_tests_concept") < 0,
    "learner-facing report state should not expose machine taxonomy codes when backend display fields exist",
  );
  assert(
    JSON.stringify(ctx.data).indexOf("M07") < 0 &&
      JSON.stringify(ctx.data).indexOf("M06") < 0 &&
      JSON.stringify(ctx.data).indexOf("e8b7f3a8") < 0 &&
      JSON.stringify(ctx.data).indexOf("practice /") < 0 &&
      JSON.stringify(ctx.data).indexOf("q_1") < 0,
    "learner-facing report state should hide stale backend raw error codes, event ids, and training ids",
  );
  assert(
    JSON.stringify(ctx.data).indexOf("主体结构") >= 0 &&
      JSON.stringify(ctx.data).indexOf("多选错选") >= 0 &&
      JSON.stringify(ctx.data).indexOf("多选漏选") >= 0,
    "stale backend Learning Brain fields should still become learner-readable Chinese copy",
  );

  const reportCtx = {
    data: {},
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
    _drawRadar: function () {},
  };
  await pageDef._loadLearningReport.call(reportCtx);
  assert.strictEqual(reportCtx.data.todayDone, 1);
  assert.strictEqual(reportCtx.data.dailyTarget, 30);
  assert.strictEqual(reportCtx.data.weakNodeCount, 1);
  assert.strictEqual(reportCtx.data.overallMastery, 20);
  assert.strictEqual(reportCtx.data.learningBrainGraphStats.eventCount, 2);
  assert.strictEqual(reportCtx.data.learningBrainEmpty, false);

  // ─── G6: 入口只调一次 getLearningReport，旧 5 个接口调用次数为 0 ─────────────
  const callCounters = {
    learningReport: 0,
    todayProgress: 0,
    homeDashboard: 0,
    assessmentProfile: 0,
    masteryDashboard: 0,
    learningBrainProjection: 0,
  };
  const countingApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getLearningReport: async function () {
      callCounters.learningReport += 1;
      return {
        data: {
          ok: true,
          schema_version: 1,
          authority: {
            read_model: "learning-report-read-model",
            progress_source: "learner_memory_events.learning_evidence",
            learning_brain_source: "dry_run_learning_evidence",
            deprecated_page_sources: [],
          },
          degraded: false,
          degraded_sources: [],
          source_status: {},
          freshness: {
            event_count: 1,
            unknown_date_count: 0,
            window_truncated: false,
          },
          overview: {
            today_done: 1,
            recent_three_done: 1,
            attempt_count: 1,
            today_unique_questions: 1,
            recent_three_unique_questions: 1,
            unique_question_count: 1,
            daily_target: 30,
            streak_days: 1,
          },
          mastery: {
            overall_mastery: 0,
            groups: [],
            hotspots: [],
            review_summary: { total_due: 0 },
          },
          radar_dimensions: [],
          learning_brain: {},
          progress_feedback: { cards: [], milestones: [] },
        },
      };
    },
    getTodayProgress: async function () {
      callCounters.todayProgress += 1;
      return { data: {} };
    },
    getHomeDashboard: async function () {
      callCounters.homeDashboard += 1;
      return { data: {} };
    },
    getAssessmentProfile: async function () {
      callCounters.assessmentProfile += 1;
      return { data: {} };
    },
    getMasteryDashboard: async function () {
      callCounters.masteryDashboard += 1;
      return { data: {} };
    },
    getLearningBrainProjection: async function () {
      callCounters.learningBrainProjection += 1;
      return { data: {} };
    },
    getRadarData: async function () {
      return { data: { dimensions: [] } };
    },
  };
  injectModule(apiPath, countingApi);
  delete require.cache[reportPath];
  const reportModule = require(reportPath);
  // Re-capture pageDef from the freshly required module
  const entryCtx = {
    data: {},
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
    _drawRadar: function () {},
  };
  // onShow → app.checkAuth → _loadLearningReport
  let pageDef2 = null;
  global.Page = function (definition) {
    pageDef2 = definition;
  };
  delete require.cache[reportPath];
  require(reportPath);
  await pageDef2._loadLearningReport.call(entryCtx);

  assert.strictEqual(
    callCounters.learningReport,
    1,
    "wx report main entry must call getLearningReport exactly once",
  );
  assert.strictEqual(
    callCounters.todayProgress,
    0,
    "wx report main entry must not call legacy getTodayProgress",
  );
  assert.strictEqual(
    callCounters.homeDashboard,
    0,
    "wx report main entry must not call legacy getHomeDashboard",
  );
  assert.strictEqual(
    callCounters.assessmentProfile,
    0,
    "wx report main entry must not call legacy getAssessmentProfile",
  );
  assert.strictEqual(
    callCounters.masteryDashboard,
    0,
    "wx report main entry must not call legacy getMasteryDashboard",
  );
  assert.strictEqual(
    callCounters.learningBrainProjection,
    0,
    "wx report main entry must not call legacy getLearningBrainProjection",
  );

  // ─── G6: degraded UI 暴露 — page.data.degradedHint / degradedSources ─────
  const degradedApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getLearningReport: async function () {
      return {
        data: {
          ok: true,
          schema_version: 1,
          authority: {
            read_model: "learning-report-read-model",
            progress_source: "learner_memory_events.learning_evidence",
            learning_brain_source: "dry_run_learning_evidence",
            deprecated_page_sources: [],
          },
          degraded: true,
          degraded_sources: ["mastery_dashboard"],
          source_status: {
            mastery_dashboard: {
              ok: false,
              latency_ms: 30,
              error: "RuntimeError: offline",
            },
            today_progress: { ok: true, latency_ms: 5, error: null },
          },
          freshness: {
            event_count: 0,
            unknown_date_count: 0,
            window_truncated: false,
          },
          overview: {
            today_done: 0,
            recent_three_done: 0,
            attempt_count: 0,
            today_unique_questions: 0,
            recent_three_unique_questions: 0,
            unique_question_count: 0,
            daily_target: 30,
            streak_days: 0,
          },
          mastery: {
            overall_mastery: 0,
            groups: [],
            hotspots: [],
            review_summary: { total_due: 0 },
          },
          radar_dimensions: [],
          learning_brain: {},
          progress_feedback: { cards: [], milestones: [] },
        },
      };
    },
  };
  injectModule(apiPath, degradedApi);
  delete require.cache[reportPath];
  let pageDef3 = null;
  global.Page = function (definition) {
    pageDef3 = definition;
  };
  require(reportPath);

  const degradedCtx = {
    data: {},
    _canvasReady: false,
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
    _drawRadar: function () {},
  };
  await pageDef3._loadLearningReport.call(degradedCtx);
  assert(
    typeof degradedCtx.data.degradedHint === "string" &&
      degradedCtx.data.degradedHint.length > 0 &&
      degradedCtx.data.degradedHint.indexOf("掌握度看板") >= 0,
    "wx degraded=true must surface a Chinese degradedHint containing the source label",
  );
  assert(
    Array.isArray(degradedCtx.data.degradedSources) &&
      degradedCtx.data.degradedSources.indexOf("mastery_dashboard") >= 0,
    "wx degraded payload must expose degradedSources array",
  );
  assert.strictEqual(
    degradedCtx.data.reportFallbackActive,
    false,
    "wx degraded payload (unified still succeeded) must NOT set reportFallbackActive",
  );

  // ─── window_truncated=true → unified 成功但必须显式降级 ───────────────
  const truncatedApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getLearningReport: async function () {
      var payload = await degradedApi.getLearningReport();
      payload.data.degraded = false;
      payload.data.degraded_sources = [];
      payload.data.freshness.window_truncated = true;
      return payload;
    },
  };
  injectModule(apiPath, truncatedApi);
  delete require.cache[reportPath];
  let pageDefWindow = null;
  global.Page = function (definition) {
    pageDefWindow = definition;
  };
  require(reportPath);
  const truncatedCtx = {
    data: {},
    _canvasReady: false,
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
    _drawRadar: function () {},
  };
  await pageDefWindow._loadLearningReport.call(truncatedCtx);
  assert(
    truncatedCtx.data.degradedHint.indexOf("近 3 天窗口") >= 0,
    "wx window_truncated=true must surface a degraded hint for the recent window",
  );
  assert(
    truncatedCtx.data.degradedSources.indexOf("learning_report_window") >= 0,
    "wx window_truncated=true must include learning_report_window in degradedSources",
  );
  assert.strictEqual(
    truncatedCtx.data.reportFallbackActive,
    false,
    "wx window_truncated=true still uses unified payload, not legacy fallback",
  );

  // ─── unified payload 失败（throw）→ fallback degraded state ───────────────
  const failingApi = {
    unwrapResponse: function (raw) {
      return raw && raw.data ? raw.data : raw;
    },
    getLearningReport: async function () {
      throw new Error("simulated 5xx");
    },
  };
  injectModule(apiPath, failingApi);
  delete require.cache[reportPath];
  let pageDef4 = null;
  global.Page = function (definition) {
    pageDef4 = definition;
  };
  require(reportPath);
  const failingCtx = {
    data: {},
    _canvasReady: false,
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch);
    },
    _drawRadar: function () {},
  };
  await pageDef4._loadLearningReport.call(failingCtx);
  assert.strictEqual(
    failingCtx.data.reportFallbackActive,
    true,
    "wx unified failure must mark reportFallbackActive=true",
  );
  assert(
    typeof failingCtx.data.degradedHint === "string" &&
      failingCtx.data.degradedHint.length > 0,
    "wx unified failure must surface a degradedHint string",
  );
  assert(
    Array.isArray(failingCtx.data.degradedSources) &&
      failingCtx.data.degradedSources.indexOf("learning_report") >= 0,
    "wx unified failure must list learning_report in degradedSources",
  );

  console.log("PASS test_report_learning_brain.js");
}

run().catch(function (error) {
  console.error(error);
  process.exit(1);
});
