// test_renderer_parity.js — keep wx and WebView renderers behaviorally aligned
// Run: node wx_miniprogram/tests/test_renderer_parity.js

var wxAiState = require("../utils/ai-message-state");
var wxMcq = require("../utils/mcq-detect");
var wxRenderSchema = require("../utils/render-schema");
var webAiState = require("../../yousenwebview/packageDeeptutor/utils/ai-message-state");
var webMcq = require("../../yousenwebview/packageDeeptutor/utils/mcq-detect");
var webRenderSchema = require("../../yousenwebview/packageDeeptutor/utils/render-schema");
var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

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

function loadStructuredRendererCases() {
  var fixturePath = path.resolve(
    __dirname,
    "../../tests/fixtures/wechat_structured_renderer_cases.json",
  );
  return JSON.parse(fs.readFileSync(fixturePath, "utf8"));
}

run("mcq-detect parity for plain mcq with receipt tail", function () {
  var text = [
    "现在给你出一道选择题：",
    "",
    "题目1：建筑构造",
    "防火门构造的基本要求有（ ）。",
    "A. 甲级防火门耐火极限为 1.5h",
    "B. 向内开启",
    "C. 关闭后应能从内外两侧手动开启",
    "D. 具有自行关闭功能",
    "",
    "回执：已生成 1 道题",
  ].join("\n");

  assertEqual(wxMcq.detect(text), webMcq.detect(text), "mcq detect output should match");
  assertEqual(wxMcq.stripReceipt(text), webMcq.stripReceipt(text), "stripReceipt output should match");
});

run("render-schema parity for canonical message normalization", function () {
  var input = {
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
      },
      {
        type: "formula_block",
        latex: "q=mc\\Delta t",
      },
      {
        type: "steps",
        title: "解题步骤",
        steps: [
          { index: 1, title: "审题" },
          { index: 2, title: "列式" },
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
        fallback_table: {
          headers: ["题型", "数量"],
          rows: [["单选题", "3"], ["多选题", "1"]],
        },
      },
    ],
    fallback_text: "兼容正文",
    meta: { streamingMode: "block_finalized" },
  };

  assertEqual(
    wxRenderSchema.createCanonicalMessage(input),
    webRenderSchema.createCanonicalMessage(input),
    "canonical message normalization should match",
  );
});

run("ai-message-state parity for structured presentation blocks", function () {
  var input = {
    content: "这段正文会作为 structured fallback 文本显示。",
    presentation: {
      blocks: [
        {
          type: "table",
          headers: [
            { text: "考点" },
            { text: "分值", align: "right" },
          ],
          rows: [
            [
              { text: "防火门" },
              { text: "2", highlight: true },
            ],
          ],
          caption: "表 1",
          mobile_strategy: "compact_cards",
        },
        {
          type: "formula_block",
          latex: "A = \\pi r^2",
          display_text: "A = πr²",
          copy_text: "A = \\pi r^2",
        },
        {
          type: "steps",
          title: "解题步骤",
          steps: [
            { index: 1, title: "审题", detail: "确认题目要求。" },
            { index: 2, title: "列式", detail: "把关键条件写出来。" },
          ],
        },
        {
          type: "recap",
          title: "本节课总结",
          summary: "先结构化，再渲染。",
          bullets: ["步骤要稳定", "总结要轻量"],
        },
        {
          type: "chart",
          chartType: "bar",
          title: "题型分布",
          summary: "图形失败时必须回退为数据卡。",
          series: [
            { name: "单选题", value: "3" },
            { name: "多选题", value: "1" },
          ],
          fallback_table: {
            headers: [
              { text: "题型" },
              { text: "数量" },
            ],
            rows: [
              [{ text: "单选题" }, { text: "3" }],
              [{ text: "多选题" }, { text: "1" }],
            ],
            mobile_strategy: "compact_cards",
          },
        },
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "某防水工程题目",
              question_type: "single_choice",
              options: [
                { key: "A", text: "方案A" },
                { key: "B", text: "方案B" },
              ],
              followup_context: {
                question_id: "q_1",
                correct_answer: "B",
              },
            },
          ],
          submit_hint: "请选择后提交答案",
        },
      ],
      fallback_text: "这段正文会作为 structured fallback 文本显示。",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  };

  assertEqual(
    wxAiState.deriveAiMessageRenderState(input),
    webAiState.deriveAiMessageRenderState(input),
    "structured presentation-backed ai-message render state should match",
  );
});

run("renderer sample set keeps wx and webview parity", function () {
  var cases = loadStructuredRendererCases();
  cases.forEach(function (sample) {
    var input = {
      content: sample.content,
      presentation: sample.presentation,
      parseBlocks: true,
    };
    assertEqual(
      wxAiState.deriveAiMessageRenderState(input),
      webAiState.deriveAiMessageRenderState(input),
      sample.name + " should keep wx/webview parity",
    );
  });
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_renderer_parity.js (" + pass + " assertions)");
