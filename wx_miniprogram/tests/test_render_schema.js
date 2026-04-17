// test_render_schema.js — regression tests for internal render schema registry
// Run: node wx_miniprogram/tests/test_render_schema.js

var renderSchema = require("../utils/render-schema");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) {
    pass++;
    return;
  }
  fail++;
  errors.push(
    "FAIL: " +
      message +
      "\n  expected: " +
      JSON.stringify(expected) +
      "\n  actual:   " +
      JSON.stringify(actual),
  );
}

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

run("internal render schemas register the minimal canonical set", function () {
  assertEqual(
    Object.keys(renderSchema.INTERNAL_RENDER_SCHEMAS).sort(),
    [
      "canonical_message",
      "chart_block",
      "formula_block",
      "mcq_block",
      "recap_block",
      "render_model",
      "steps_block",
      "table_block",
    ],
    "registry should contain the minimal internal schemas",
  );
});

run("canonical message keeps normalized mcq, table, formula, steps, recap and chart blocks", function () {
  var canonical = renderSchema.createCanonicalMessage({
    message_id: "msg_1",
    blocks: [
      {
        type: "mcq",
        questions: [
          {
            index: 1,
            stem: "防火门构造的基本要求有（ ）。",
            question_type: "multi_choice",
            options: {
              a: "甲级防火门耐火极限为 1.5h",
              c: "关闭后应能从内外两侧手动开启",
            },
            followup_context: { question_id: "q_1" },
          },
        ],
        submit_hint: "请选择后提交答案",
      },
      {
        type: "table",
        headers: ["项目", "要求"],
        rows: [["防火门", "具有自行关闭功能"]],
        mobile_strategy: "compact_cards",
      },
      {
        type: "formula_block",
        latex: "q=mc\\Delta t",
        display_text: "q = mcΔt",
      },
      {
        type: "steps",
        title: "推导步骤",
        steps: [
          { index: 1, title: "列式" },
          { index: 2, title: "代入" },
        ],
      },
      {
        type: "summary",
        text: "本节课总结",
        bullets: ["先识别主语义", "再走结构化渲染"],
      },
      {
        type: "chart",
        chart_type: "bar",
        title: "题型分布",
        summary: "本题组中选择题占比更高。",
        series: [
          { name: "单选题", value: "3" },
          { name: "多选题", value: "1" },
        ],
        axes: { x: "题型", y: "数量" },
        legend: ["题型", "数量"],
        caption: "图 1 题型统计",
        fallback_table: {
          headers: ["题型", "数量"],
          rows: [["单选题", "3"], ["多选题", "1"]],
          mobile_strategy: "compact_cards",
        },
      },
      {
        type: "unknown_block",
        text: "should be ignored",
      },
    ],
    fallback_text: "兼容正文",
    meta: { streamingMode: "block_finalized" },
  });

  assertEqual(canonical.messageId, "msg_1", "message id should normalize");
  assertEqual(canonical.blocks.length, 6, "unknown block should be filtered");
  assertEqual(canonical.blocks[0].type, "mcq", "first block should be mcq");
  assertEqual(canonical.blocks[0].questions[0].questionId, "q_1", "mcq question id should normalize");
  assertEqual(canonical.blocks[1].mobileStrategy, "compact_cards", "table mobile strategy should normalize");
  assertEqual(canonical.blocks[2].displayText, "q = mcΔt", "formula display text should normalize");
  assertEqual(canonical.blocks[3].type, "steps", "steps should normalize as a dedicated block");
  assertEqual(canonical.blocks[4].type, "recap", "summary alias should normalize to recap");
  assertEqual(canonical.blocks[4].summary, "本节课总结", "recap summary should preserve body text");
  assertEqual(canonical.blocks[5].fallbackTable.mobileStrategy, "compact_cards", "chart fallback table should normalize");
});

run("legacy summary block is normalized to recap", function () {
  var canonical = renderSchema.createCanonicalMessage({
    blocks: [
      {
        type: "summary",
        text: "本节课总结",
      },
    ],
  });

  assertEqual(canonical.blocks.length, 1, "legacy summary alias should still be accepted");
  assertEqual(canonical.blocks[0].type, "recap", "legacy summary alias should normalize to recap");
  assertEqual(canonical.blocks[0].summary, "本节课总结", "recap summary should be preserved");
  assertEqual(canonical.blocks[0].title, "教学总结", "recap title should default to teaching summary");
});

run("render model preserves compatibility fields and diagnostic fields", function () {
  var model = renderSchema.createRenderModel({
    renderableContent: "下面先做一道题。",
    blocks: null,
    mcqCards: [{ index: 1, stem: "题干", options: [{ key: "A", text: "选项A" }] }],
    mcqHint: "请选择后提交答案",
    mcqReceipt: "receipt_1",
    mcqInteractiveReady: true,
    visibleBlocks: [{ type: "mcq" }],
    streamPhase: "complete",
  });

  assertEqual(model.blocks, null, "legacy blocks field should preserve null");
  assertEqual(model.visibleBlocks.length, 1, "visible blocks should normalize");
  assertEqual(model.streamPhase, "complete", "stream phase should normalize");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_render_schema.js (" + pass + " assertions)");
