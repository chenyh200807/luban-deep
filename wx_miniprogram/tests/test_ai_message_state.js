// test_ai_message_state.js — regression tests for wx_miniprogram/utils/ai-message-state.js
// Run: node wx_miniprogram/tests/test_ai_message_state.js

var aiMessageState = require("../utils/ai-message-state");
var fs = require("fs");
var path = require("path");

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

function loadStructuredRendererCases() {
  var fixturePath = path.resolve(
    __dirname,
    "../../tests/fixtures/wechat_structured_renderer_cases.json",
  );
  return JSON.parse(fs.readFileSync(fixturePath, "utf8"));
}

run("pure mcq content no longer becomes interactive without presentation", function () {
  var text = [
    "题目1：建筑构造",
    "防火门构造的基本要求有（ ）。",
    "A. 甲级防火门耐火极限为 1.5h",
    "B. 向内开启",
    "C. 关闭后应能从内外两侧手动开启",
    "D. 具有自行关闭功能",
    "E. 开启后，门扇不应跨越变形缝",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  assertEqual(state.renderableContent, text, "plain content should remain visible");
  assert(state.blocks && state.blocks.length > 0, "plain content should stay in markdown flow");
  assertEqual(state.mcqCards, null, "text-only choice content should not create interactive cards");
  assertEqual(state.mcqInteractiveReady, false, "text-only choice content should stay non-interactive");
});

run("plain text without mcq strips receipt but keeps body", function () {
  var text = [
    "屋面防水等级应结合建筑性质、使用功能和重要程度综合确定。",
    "",
    "回执：已生成 1 道题",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: false,
  });

  assertEqual(
    state.renderableContent,
    "屋面防水等级应结合建筑性质、使用功能和重要程度综合确定。",
    "plain answer body should remain after receipt is stripped",
  );
  assertEqual(state.blocks, null, "parseBlocks=false should avoid markdown parsing");
  assertEqual(state.mcqCards, null, "plain text should not create mcq cards");
  assertEqual(state.mcqInteractiveReady, false, "plain text should not become interactive");
});

run("internal DSML tool calls are not rendered as user-visible content", function () {
  var text = [
    "让我先查一下你的学习记录。",
    '< | DSML | toolcalls>< | DSML | invoke name="readfile">< | DSML | parameter name="filepath" string="true">/app/data/tutorbot/construction-exam-coach/workspace/skills/memory/PROFILE.md</ | DSML | parameter></ | DSML | invoke></ | DSML | toolcalls>',
  ].join("\n\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: false,
  });

  assertEqual(
    state.renderableContent,
    "暂时未生成适合直接展示的答案，请重试一次。",
    "DSML tool calls should fail closed before rendering",
  );
  assert(
    state.renderableContent.indexOf("DSML") < 0 &&
      state.renderableContent.indexOf("PROFILE.md") < 0,
    "internal tool payload should not survive in renderable content",
  );
});

run("service presentation block becomes the primary mcq source", function () {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: "### Question 1\n某防水工程题目",
    presentation: {
      blocks: [
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
      fallback_text: "### Question 1\n某防水工程题目",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: false,
  });

  assert(state.mcqCards && state.mcqCards.length === 1, "presentation block should generate a card");
  assertEqual(state.mcqCards[0].questionId, "q_1", "question id should come from service presentation");
  assertEqual(state.mcqInteractiveReady, true, "presentation block should remain interactive");
  assertEqual(state.mcqReceipt, "", "presentation path should not be polluted by text-detect receipts");
  assertEqual(state.renderableContent, "", "pure mcq presentation should not duplicate the card text");
  assertEqual(state.hasStructuredContent, false, "mcq-only presentation should not suppress markdown fallback paths");
});

run("mcq presentation keeps mixed teaching content visible", function () {
  var content = [
    "好的，我们直接进入防水工程最容易失分的一个核心考点。",
    "",
    "## 结论",
    "",
    "防水工程最容易失分的是 **钢板止水带搭接参数**：焊接搭接长度不应小于 50mm，并采用双面焊。",
    "",
    "## 判断依据",
    "",
    "- 焊接搭接：50mm + 双面焊",
    "- 冷搭接：20mm + 单面焊或铆接",
    "",
    "## 考试场景判断",
    "",
    "题目：地下防水工程中，关于钢板止水带施工的说法，正确的是：",
    "",
    "A. 焊接搭接长度不应小于20mm，采用单面焊",
    "B. 焊接搭接长度不应小于50mm，采用双面焊",
    "",
    "## 踩分点",
    "",
    "- 两个参数必须成对匹配。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: content,
    presentation: {
      blocks: [
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "地下防水工程中，关于钢板止水带施工的说法，正确的是：",
              question_type: "single_choice",
              options: [
                { key: "A", text: "焊接搭接长度不应小于20mm，采用单面焊" },
                { key: "B", text: "焊接搭接长度不应小于50mm，采用双面焊" },
              ],
              followup_context: {
                question_id: "q_waterproof_1",
                correct_answer: "B",
              },
            },
          ],
          submit_hint: "请选择后提交答案",
        },
      ],
      fallback_text: content,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  assert(state.mcqCards && state.mcqCards.length === 1, "mcq card should still render");
  assert(
    state.renderableContent.indexOf("## 结论") >= 0 &&
      state.renderableContent.indexOf("## 踩分点") >= 0,
    "teaching prose around the mcq should remain visible",
  );
  assert(state.blocks && state.blocks.length > 0, "mixed fallback should stay in markdown flow");
  assertEqual(state.hasStructuredContent, false, "mcq-only projection should not take over body rendering");
});

run("structured table and formula blocks become the render source", function () {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: "这段文字只做 fallback，不应覆盖结构化块。",
    presentation: {
      blocks: [
        {
          type: "table",
          headers: [
            { text: "考点" },
            { text: "分值" },
          ],
          rows: [
            [
              { text: "防火门" },
              { text: "2" },
            ],
          ],
          caption: "表 1 防火门考点",
          mobile_strategy: "compact_cards",
        },
        {
          type: "formula_block",
          latex: "A = \\pi r^2",
          displayText: "A = πr²",
          svgUrl: "https://example.com/formula.svg",
          copyText: "A = \\pi r^2",
        },
      ],
      fallback_text: "结构化内容优先展示",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  assertEqual(state.hasStructuredContent, true, "structured presentation should be marked as structured");
  assert(state.blocks && state.blocks.length === 2, "structured blocks should become the primary render blocks");
  assertEqual(state.blocks[0].type, "table", "table should stay canonical");
  assertEqual(state.blocks[0].headers[0].text, "考点", "table headers should be normalized to text cells");
  assertEqual(state.blocks[0].rows[0][1].text, "2", "table rows should be normalized to text cells");
  assertEqual(state.blocks[0].caption, "表 1 防火门考点", "table caption should be preserved");
  assertEqual(state.blocks[0].mobileStrategy, "compact_cards", "mobile strategy should be normalized");
  assertEqual(state.blocks[1].type, "formula_block", "formula should stay canonical");
  assertEqual(state.blocks[1].displayText, "A = πr²", "formula display text should be preserved");
  assertEqual(state.blocks[1].svgUrl, "https://example.com/formula.svg", "formula svg url should be preserved");
  assertEqual(state.blocks[1].copyText, "A = \\pi r^2", "formula copy text should be preserved");
  assert(state.visibleBlocks && state.visibleBlocks.length === 2, "visibleBlocks should retain canonical blocks");
});

run("structured steps recap and chart blocks become the render source", function () {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: "步骤、总结和图表都应以结构化卡片显示。",
    presentation: {
      blocks: [
        {
          type: "steps",
          title: "解题步骤",
          steps: [
            { index: 1, title: "识别题型", detail: "先确认题目要求。", status: "done" },
            { index: 2, title: "提取条件", detail: "把关键条件写出来。" },
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
          axes: { x: "题型", y: "数量" },
          caption: "图 1 题型统计",
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
      ],
      fallback_text: "步骤、总结和图表都应以结构化卡片显示。",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  assertEqual(state.hasStructuredContent, true, "structured presentation should stay structured");
  assertEqual(state.blocks.length, 3, "three structured blocks should render");
  assertEqual(state.blocks[0].type, "steps", "steps should be preserved as a structured card");
  assertEqual(state.blocks[0].steps.length, 2, "steps card should normalize ordered items");
  assertEqual(state.blocks[1].type, "recap", "recap should be preserved as a structured card");
  assertEqual(state.blocks[1].bullets.length, 2, "recap bullets should be preserved");
  assertEqual(state.blocks[2].type, "chart", "chart should be preserved as a structured card");
  assertEqual(state.blocks[2].fallbackTable.mobileStrategy, "compact_cards", "chart fallback table should normalize");
  assertEqual(state.visibleBlocks.length, 3, "visibleBlocks should retain all canonical blocks");
  assertEqual(state.renderableContent, "", "text-native structured blocks should not repeat fallback prose");
});

run("structured mcq still renders as cards and does not regress table path", function () {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: "题干正文",
    presentation: {
      blocks: [
        {
          type: "table",
          headers: [{ text: "A" }],
          rows: [[{ text: "1" }]],
        },
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "请选答案",
              questionType: "single_choice",
              options: [
                { key: "A", text: "选项A" },
                { key: "B", text: "选项B" },
              ],
              followup_context: {
                question_id: "q_mcq_1",
                correct_answer: "B",
              },
            },
          ],
          submit_hint: "请选择后提交答案",
        },
      ],
      fallback_text: "题干正文",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: false,
  });

  assert(state.blocks && state.blocks.length === 1, "mcq should be excluded from render blocks");
  assertEqual(state.blocks[0].type, "table", "non-mcq structured blocks should still render");
  assert(state.mcqCards && state.mcqCards.length === 1, "mcq should still become a card");
  assertEqual(state.mcqCards[0].questionId, "q_mcq_1", "mcq question id should be preserved");
  assertEqual(state.mcqInteractiveReady, true, "mcq presentation should remain interactive");
  assertEqual(state.renderableContent, "", "mcq-backed structured text should not duplicate the card stem");
});

run("structured renderer sample set remains renderable", function () {
  var cases = loadStructuredRendererCases();
  assert(cases.length >= 3, "sample set should cover multiple structured cases");

  cases.forEach(function (sample) {
    var state = aiMessageState.deriveAiMessageRenderState({
      content: sample.content,
      presentation: sample.presentation,
      parseBlocks: true,
    });
    var expected = sample.expected || {};
    var renderBlockTypes = (state.blocks || []).map(function (block) {
      return block.type;
    });
    var visibleBlockTypes = (state.visibleBlocks || []).map(function (block) {
      return block.type;
    });

    assertEqual(
      state.hasStructuredContent,
      expected.hasStructuredContent,
      sample.name + " should preserve structured-content flag",
    );
    assertEqual(
      renderBlockTypes,
      expected.renderBlockTypes,
      sample.name + " should preserve primary render block types",
    );
    assertEqual(
      visibleBlockTypes,
      expected.visibleBlockTypes,
      sample.name + " should preserve canonical visible block types",
    );
    assertEqual(
      state.mcqCards ? state.mcqCards.length : 0,
      expected.mcqCount,
      sample.name + " should preserve mcq card count",
    );
  });
});

run("markdown blocks expose rich-text nodes for inline emphasis and punctuation", function () {
  var text = [
    "**拿分要点：**",
    "1. **时间限制**：必须记住\"24小时\"这个关键数字，这是考试常考点",
    "2. **顺序要求**：初拧→复拧→终拧，三个步骤都要在24小时内完成",
    "",
    "**易错点提醒：**",
    "- 不要记成\"48小时\"或\"72小时\"，必须是\"24小时\"",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  assert(state.blocks && state.blocks.length >= 4, "markdown content should stay renderable");
  assert(Array.isArray(state.blocks[0].nodes), "section title paragraph should expose nodes");
  assert(
    Array.isArray(state.blocks[1].items[0].nodes),
    "ordered list item should expose inline rich-text nodes",
  );
  assertEqual(
    state.blocks[1].items[0].nodes[0].children[0].text,
    "时间限制：",
    "ordered list label should normalize colon into the bold label",
  );
  assertEqual(
    state.blocks[1].items[0].nodes[1].text.indexOf(" 必须记住"),
    0,
    "ordered list trailing text should stay attached after label normalization",
  );
});

run("markdown normalization flattens nested lists into the supported mobile subset", function () {
  var text = [
    "## 2.设防层数（定量要求）",
    "",
    "- **举例**：",
    "  - 屋面一级防水→**不应少于3道防水层**",
    "  - 地下工程二级防水  →  **不应少于2道防水层**",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  assertEqual(
    state.renderableContent.indexOf("- 屋面一级防水 → **不应少于3道防水层**") >= 0,
    true,
    "renderable content should normalize nested bullet indentation and arrow spacing",
  );
  assert(
    state.blocks && state.blocks[2] && state.blocks[2].type === "ul",
    "normalized content should remain inside supported unordered lists",
  );
  assertEqual(
    state.blocks[2].items.length,
    3,
    "flattened example lines should stay as sibling list items instead of a broken paragraph",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_ai_message_state.js (" + pass + " assertions)");
