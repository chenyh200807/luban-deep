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

run("long markdown tables use compact cards on mobile", function () {
  var text = [
    "| 序号 | 安排内容 | 判断 | 理由 |",
    "|------|----------|------|------|",
    "| （1） | 工程设计总承包由集团工程设计部承担 | 不正确 | 工程设计部是内部管理部门，不属于具备资质的设计单位。 |",
    "| （2） | 主体设计分包给集团设计公司 | 不正确 | 主体设计不得分包。 |",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  assert(state.blocks && state.blocks.length === 1, "markdown table should remain one render block");
  assertEqual(state.blocks[0].type, "table", "markdown table should parse as table");
  assertEqual(state.blocks[0].mobileStrategy, "compact_cards", "long markdown table should use compact cards");
  assertEqual(state.blocks[0].headers.length, 4, "table headers should be preserved");
  assertEqual(state.blocks[0].rows.length, 2, "table rows should be preserved");
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

run("mcq presentation supports multiple generated choice aliases", function () {
  var state = aiMessageState.deriveAiMessageRenderState({
    content: "",
    presentation: {
      blocks: [
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "《建筑法》属于（ ）。",
              question_type: "single_choice",
              options: [
                { key: "A", text: "法律" },
                { key: "B", text: "行政法规" },
              ],
              followup_context: { question_id: "q_1" },
            },
            {
              index: 2,
              stem: "正确的说法有（ ）。",
              question_type: "multi_choice",
              options: [
                { key: "A", text: "说法A" },
                { key: "B", text: "说法B" },
              ],
              followup_context: { question_id: "q_2" },
            },
          ],
          submit_hint: "多题作答，先分别点选，再提交答案。",
        },
      ],
      fallback_text: "",
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: false,
  });

  assert(state.mcqCards && state.mcqCards.length === 2, "all generated questions should become cards");
  assertEqual(state.mcqCards[0].questionType, "single_choice", "single choice alias should stay interactive");
  assertEqual(state.mcqCards[1].questionType, "multi_choice", "multi choice alias should stay interactive");
  assertEqual(state.mcqInteractiveReady, true, "whole question set should be interactive");
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
    "## 采分点",
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
  var calloutLabels = (state.blocks || []).map(function (block) {
    return block.label || "";
  });
  assert(
    calloutLabels.indexOf("结论") >= 0 && calloutLabels.indexOf("采分点") >= 0,
    "teaching prose around the mcq should remain visible as callouts",
  );
  assertEqual(state.renderableContent, "", "mixed mcq fallback should not render duplicate plain text");
  assert(state.originalContent.indexOf("## 结论") >= 0, "full original stays behind the toggle");
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

run("teaching markdown headings render as semantic callouts", function () {
  var text = [
    "## 核心结论",
    "",
    "先判断责任边界。",
    "",
    "## 采分点",
    "",
    "- 写清判断结论。",
    "",
    "## 易错点",
    "",
    "- 不要把合同责任和现场责任混在一起。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  var callouts = (state.blocks || []).filter(function (block) {
    return block.type === "callout";
  });
  assertEqual(
    callouts.map(function (block) {
      return block.label + ":" + block.variant;
    }),
    ["核心结论:conclusion", "采分点:highlight", "易错点:warning"],
    "mandatory teaching headings should use the dedicated callout renderer",
  );
});

run("mnemonic and next-step headings render as semantic callouts", function () {
  var text = [
    "## 记忆口诀",
    "",
    "先判责，再找法，最后写做法。",
    "",
    "## 下一步建议",
    "",
    "- 先用一道案例题检验这个判断顺序。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  var callouts = (state.blocks || []).filter(function (block) {
    return block.type === "callout";
  });
  assertEqual(
    callouts.map(function (block) {
      return block.label + ":" + block.variant;
    }),
    ["记忆口诀:tip", "下一步建议:tip"],
    "mnemonic and next-step advice headings should use the dedicated callout renderer",
  );
});

run("structured presentation keeps teaching fallback callouts renderable", function () {
  var text = [
    "## 核心结论",
    "",
    "先判断责任边界。",
    "",
    "## 采分点",
    "",
    "- 写清判断结论。",
    "",
    "## 易错点",
    "",
    "- 不要把合同责任和现场责任混在一起。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    presentation: {
      blocks: [
        {
          type: "steps",
          title: "解题步骤",
          steps: [{ index: 1, title: "审题", detail: "先找责任主体。" }],
        },
      ],
      fallback_text: text,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  var blockTypes = (state.blocks || []).map(function (block) {
    return block.type + ":" + (block.label || block.title || "");
  });
  assert(
    blockTypes.indexOf("steps:解题步骤") >= 0,
    "structured teaching block should still render",
  );
  assert(
    JSON.stringify(state.blocks).indexOf("先判断责任边界") >= 0 &&
      JSON.stringify(state.blocks).indexOf("不要把合同责任和现场责任混在一起") >= 0,
    "non-mcq teaching fallback should remain available as full markdown blocks",
  );
  assertEqual(state.renderableContent, "", "non-mcq fallback appended as blocks should not duplicate plain text");
});

run("non-mcq structured presentation keeps full teaching fallback prose", function () {
  var text = [
    "先给你一个结论前的必要前提。",
    "",
    "## 结论",
    "",
    "横道图适合看持续时间，网络图更适合分析关键线路。",
    "",
    "## 采分点",
    "",
    "- 写出关键线路应看网络逻辑关系。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    presentation: {
      blocks: [
        {
          type: "table",
          title: "对比表",
          columns: ["工具", "适用点"],
          rows: [["网络图", "关键线路"]],
        },
      ],
      fallback_text: text,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  assertEqual(state.renderableContent.indexOf("先给你一个结论前的必要前提。") >= 0, true, "non-mcq fallback should keep prose before teaching callouts");
  assertEqual(state.renderableContent.indexOf("横道图适合看持续时间") >= 0, true, "non-mcq fallback should keep normal conclusion prose");
  assert(state.blocks && state.blocks.length === 1, "canonical table should remain the only structured block");
  assertEqual(state.blocks[0].type, "table", "non-mcq canonical block should stay canonical");
});

run("structured presentation keeps mnemonic and next-step fallback callouts renderable", function () {
  var text = [
    "## 记忆口诀",
    "",
    "先判责，再找法，最后写做法。",
    "",
    "## 下一步建议",
    "",
    "- 先用一道案例题检验这个判断顺序。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    presentation: {
      blocks: [
        {
          type: "steps",
          title: "练习安排",
          steps: [{ index: 1, title: "做题", detail: "先做一道同类题。" }],
        },
      ],
      fallback_text: text,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  var blockTypes = (state.blocks || []).map(function (block) {
    return block.type + ":" + (block.label || block.title || "");
  });
  assert(
    blockTypes.indexOf("steps:练习安排") >= 0,
    "structured block should still render with mnemonic fallback",
  );
  assert(
    JSON.stringify(state.blocks).indexOf("先判责，再找法") >= 0 &&
      JSON.stringify(state.blocks).indexOf("案例题检验") >= 0,
    "non-mcq mnemonic fallback should remain available as full markdown blocks",
  );
  assertEqual(state.renderableContent, "", "non-mcq mnemonic fallback appended as blocks should not duplicate plain text");
});

run("mcq presentation folds duplicate original text behind a toggle", function () {
  var text = [
    "关于民用建筑构造要求的说法，正确的是（ ）。",
    "A. 楼梯平台上部及下部过道处的净高不应小于2.20m",
    "B. 住宅建筑室内净高不应低于2.40m",
    "C. 临空高度在24m以下时，阳台栏杆净高不应低于1.10m",
    "D. 屋面面层均应采用不燃材料",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    presentation: {
      blocks: [
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "关于民用建筑构造要求的说法，正确的是（ ）。",
              question_type: "single_choice",
              options: [
                { key: "A", text: "楼梯平台上部及下部过道处的净高不应小于2.20m" },
                { key: "B", text: "住宅建筑室内净高不应低于2.40m" },
                { key: "C", text: "临空高度在24m以下时，阳台栏杆净高不应低于1.10m" },
                { key: "D", text: "屋面面层均应采用不燃材料" },
              ],
              followup_context: {
                question_id: "q_building_1",
                correct_answer: "C",
              },
            },
          ],
          submit_hint: "请选择后提交答案",
        },
      ],
      fallback_text: text,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  assert(state.mcqCards && state.mcqCards.length === 1, "mcq card should render");
  assertEqual(state.renderableContent, "", "duplicate original mcq text should not render above the card");
  assertEqual(state.blocks.length, 0, "duplicate original mcq text should not stay in markdown blocks");
  assertEqual(state.originalContent, text, "original text should still be available behind the toggle");
  assertEqual(state.originalCollapsed, true, "original text should be collapsed by default");
});

run("mcq presentation keeps teaching fallback without repeating question text", function () {
  var text = [
    "关于民用建筑构造要求的说法，正确的是（ ）。",
    "A. 楼梯平台上部及下部过道处的净高不应小于2.20m",
    "B. 住宅建筑室内净高不应低于2.40m",
    "C. 临空高度在24m以下时，阳台栏杆净高不应低于1.10m",
    "D. 屋面面层均应采用不燃材料",
    "",
    "## 采分点",
    "",
    "- 抓住“临空高度24m以下”对应的栏杆净高。",
    "",
    "## 易错点",
    "",
    "- 不要把住宅室内净高和栏杆净高混在一起。",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    presentation: {
      blocks: [
        {
          type: "mcq",
          questions: [
            {
              index: 1,
              stem: "关于民用建筑构造要求的说法，正确的是（ ）。",
              question_type: "single_choice",
              options: [
                { key: "A", text: "楼梯平台上部及下部过道处的净高不应小于2.20m" },
                { key: "B", text: "住宅建筑室内净高不应低于2.40m" },
                { key: "C", text: "临空高度在24m以下时，阳台栏杆净高不应低于1.10m" },
                { key: "D", text: "屋面面层均应采用不燃材料" },
              ],
              followup_context: {
                question_id: "q_building_1",
                correct_answer: "C",
              },
            },
          ],
          submit_hint: "请选择后提交答案",
        },
      ],
      fallback_text: text,
      meta: { streamingMode: "block_finalized" },
    },
    parseBlocks: true,
  });

  var rendered = JSON.stringify(state.blocks || []);
  var callouts = (state.blocks || []).filter(function (block) {
    return block.type === "callout";
  });
  assertEqual(state.renderableContent, "", "mcq plus teaching fallback should not render plain text above the card");
  assertEqual(state.originalContent, text, "full original should stay available behind the toggle");
  assert(
    rendered.indexOf("楼梯平台上部") < 0 &&
      rendered.indexOf("住宅建筑室内净高") < 0,
    "render blocks should not repeat original options",
  );
  assertEqual(
    callouts.map(function (block) {
      return block.label + ":" + block.variant;
    }),
    ["采分点:highlight", "易错点:warning"],
    "teaching fallback should still render as dedicated callouts",
  );
  assert(
    JSON.stringify(callouts[0].nodes).indexOf("临空高度24m以下") >= 0,
    "teaching callout should retain its bullet body",
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

run("blank-separated and compact ordered markers keep visible numbering", function () {
  var text = [
    "## 管理篇",
    "",
    "7. 机械设备与临时设施管理",
    "",
    "8.绿色施工与环境保护",
    "",
    "9.劳务与分包管理",
    "-实名制、分包资质审查",
  ].join("\n");

  var state = aiMessageState.deriveAiMessageRenderState({
    content: text,
    parseBlocks: true,
  });

  var olBlocks = state.blocks.filter(function (block) {
    return block.type === "ol";
  });
  var ulBlocks = state.blocks.filter(function (block) {
    return block.type === "ul";
  });

  assertEqual(olBlocks[0].items[0].index, 7, "first separated ordered item keeps index 7");
  assertEqual(olBlocks[1].items[0].index, 8, "compact separated ordered item keeps index 8");
  assertEqual(olBlocks[2].items[0].index, 9, "third separated ordered item keeps index 9");
  assertEqual(ulBlocks[0].items[0].raw, "实名制、分包资质审查", "compact bullet stays segmented");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_ai_message_state.js (" + pass + " assertions)");
