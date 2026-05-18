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

  assert(
    apiSource.indexOf("/api/v1/learning-brain/projection") >= 0,
    "api should call the canonical Learning Brain projection endpoint first",
  );
  assert(
    apiSource.indexOf(".catch(function") < 0 ||
      apiSource.indexOf("runLearningBrainHarnessCaseGrading(") > apiSource.indexOf("function getLearningBrainProjection"),
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
    reportWxml.indexOf("wx:for=\"{{item.eventIds}}\"") >= 0,
    "report should render compact event ids instead of raw JSON",
  );
  assert(
    reportWxml.indexOf("{{item.levelLabel || item.level}}") >= 0 &&
      reportWxml.indexOf("event {{item.eventId}}") < 0,
    "report should render learner-facing Chinese labels instead of machine labels",
  );
  assert(
    reportWxml.indexOf("JSON.stringify") < 0 && reportWxml.indexOf("compiled_objects") < 0,
    "report surface should not dump long projection JSON",
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
    return { globalData: {}, checkAuth: function (cb) { if (cb) cb(); } };
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
              evidence_level: "L1_repeated",
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
          typed_graph_edges: [
            {
              edge_type: "question_tests_concept",
              from: { id: "wechat-harness-case-001", type: "question" },
              to: { id: "1A432000", type: "concept" },
              evidence_event_id: "evt1abcdef",
            },
            {
              edge_type: "error_points_to_training",
              from: { id: "E02", type: "error" },
              to: { id: "1A432000:training", type: "training" },
              evidence_event_id: "evt2abcdef",
            },
          ],
          graph_chain: {
            training_uses_question: [
              {
                edge_type: "training_uses_question",
                from: { id: "1A432000:training", type: "next_training" },
                to: { id: "wechat-harness-case-002", type: "question" },
                reason_edge_event_id: "evt2abcdef",
              },
            ],
            training_not_improved_error: [
              {
                edge_type: "training_not_improved_error",
                from: { id: "1A432000:training", type: "next_training" },
                to: { id: "1A432000:E02", type: "error" },
                reason_edge_event_id: "evt2abcdef",
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
    ctx.data.learningBrainTruths[0].meta.indexOf("工程招标投标与合同管理") >= 0 &&
      ctx.data.learningBrainTruths[0].meta.indexOf("concept:") < 0,
    "compiled truth meta should use taxonomy Chinese label",
  );
  assert.strictEqual(ctx.data.learningBrainTruths[1].level, "L1_repeated");
  assert.strictEqual(ctx.data.learningBrainTruths[1].levelLabel, "重复出现");
  assert(
    ctx.data.learningBrainTruths[1].meta.indexOf("漏写关键采分点") >= 0,
    "weak point should show readable error label",
  );
  assert.strictEqual(ctx.data.learningBrainEvidence[0].type, "题目考查知识点");
  assert(
    ctx.data.learningBrainEvidence[0].path.indexOf("案例题") >= 0 &&
      ctx.data.learningBrainEvidence[0].path.indexOf("知识点：工程招标投标与合同管理") >= 0,
    "evidence path should translate typed graph nodes",
  );
  assert(
    ctx.data.learningBrainEvidence.some(function (item) {
      return item.type === "训练后仍需巩固";
    }),
    "visible evidence should include the training outcome edge",
  );
  assert.strictEqual(ctx.data.learningBrainChains[0].outcome, "本次训练结果：未改善");
  assert.strictEqual(ctx.data.learningBrainChains[0].tone, "not-improved");
  assert(
    ctx.data.learningBrainChains[0].title.indexOf("漏写关键采分点") >= 0 &&
      ctx.data.learningBrainChains[0].training.indexOf("工程招标投标与合同管理") >= 0 &&
      ctx.data.learningBrainChains[0].question.indexOf("案例题") >= 0,
    "visible chain should connect readable error, recommended training, and selected question",
  );
  assert(
    ctx.data.learningBrainTraining[0].meta.indexOf("工程招标投标与合同管理") >= 0,
    "training recommendation should show taxonomy label",
  );
  assert.strictEqual(ctx.data.learningBrainGraphStats.projectionSubjectLabel, "建筑实务学习事实");

  console.log("PASS test_report_learning_brain.js (24 assertions)");
}

run().catch(function (error) {
  console.error(error);
  process.exit(1);
});
