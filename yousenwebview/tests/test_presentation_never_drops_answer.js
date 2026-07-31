// test_presentation_never_drops_answer.js
// Run: node yousenwebview/tests/test_presentation_never_drops_answer.js
//
// 回归：终态 result 事件携带的 canonical presentation 绝不能把正文擦掉。
//
// 线上事故（2026-07-31，owner 报「答案不显示 / 流式输出消失」）：
//   服务端一轮案例题正常发出 384 条 content 流式事件 + result.response 3318 字，
//   小程序却只剩一张「本轮处理已完成 / 已完成题型识别和答案组织，可查看简要摘要」卡片。
//   根因在 ai-message-state.js 两个函数口径不一致：
//     shouldRenderStructuredFallback 用「豁免名单」{table,formula_block,chart,image}，
//       遇到名单外类型就把 renderableContent 清成 ""；
//     buildStructuredRenderableBlocks 只渲染 {table,steps,recap,chart,formula_*}。
//   差集 {paragraph,heading,callout,quote,code,list} 既被清正文又不渲染成块 => 整篇答案消失。
//   服务端 render_presentation.py 明确会产出这些类型，正文一并放在 fallback_text 里。
//
// 本测试锁死的硬不变量：
//   对 canonical schema 里的**每一个** block 类型，只要 presentation 带了 fallback_text，
//   渲染态就必须至少有一样可见内容（renderableContent / blocks / mcqCards）。
//   新增 block 类型若忘了配渲染分支，这里会直接红。

var assert = require("assert");
var path = require("path");

var UTILS = path.join(__dirname, "../packageDeeptutor/utils");
var aiMessageState = require(path.join(UTILS, "ai-message-state.js"));
var renderSchema = require(path.join(UTILS, "render-schema.js"));

var ANSWER_BODY = [
  "## 案例分析",
  "",
  "本题考查施工进度控制与工期索赔。",
  "",
  "事件一中，项目经理的做法不妥。理由：根据合同约定，工期顺延须在事件发生后 14 天内提出书面申请。",
  "",
  "事件二中，监理工程师应当签发工程暂停令。",
].join("\n");

function renderWith(presentation) {
  return aiMessageState.deriveAiMessageRenderState({
    content: ANSWER_BODY,
    presentation: presentation,
    parseBlocks: true,
  });
}

function visibleSurfaceCount(state) {
  var text = String((state && state.renderableContent) || "").trim();
  var blocks = (state && state.blocks) || [];
  var cards = (state && state.mcqCards) || [];
  var original = String((state && state.originalContent) || "").trim();
  return text.length + blocks.length + cards.length + original.length;
}

// 每种 block 类型的最小合法载荷，形状对齐服务端 render_presentation.py 的产出。
var BLOCK_FIXTURES = {
  paragraph: { type: "paragraph", text: "本题考查施工进度控制。" },
  heading: { type: "heading", text: "案例分析" },
  list: { type: "list", items: ["理由一：未在 14 天内报送", "理由二：缺少监理签认"] },
  callout: { type: "callout", text: "结论：项目经理做法不妥。" },
  quote: { type: "quote", text: "《建设工程施工合同》通用条款第 7.5 条" },
  code: { type: "code", text: "总工期 = 计划工期 + 顺延天数" },
  table: {
    type: "table",
    headers: ["事件", "是否可索赔"],
    rows: [["事件一", "否"], ["事件二", "是"]],
  },
  mcq: {
    type: "mcq",
    questions: [
      {
        id: "q1",
        stem: "下列关于工期顺延的说法，正确的是？",
        options: [
          { key: "A", text: "无需书面申请" },
          { key: "B", text: "须在 14 天内书面申请" },
        ],
      },
    ],
  },
  formula_inline: { type: "formula_inline", latex: "T=T_0+\\Delta t" },
  formula_block: { type: "formula_block", latex: "T=T_0+\\Delta t" },
  chart: {
    type: "chart",
    chartType: "line",
    title: "进度偏差",
    series: [{ name: "计划", points: [1, 2, 3] }],
  },
  image: { type: "image", text: "网络计划图" },
  steps: {
    type: "steps",
    title: "解题步骤",
    steps: [{ index: 1, title: "识别事件", detail: "先分清可索赔与不可索赔" }],
  },
  recap: {
    type: "recap",
    title: "教学总结",
    summary: "工期索赔的三个要件",
    bullets: ["书面申请", "14 天时限", "监理签认"],
  },
};

// ---------------------------------------------------------------------------
// 1) 硬不变量：任何单一 block 类型都不得吞掉答案
// ---------------------------------------------------------------------------
var allTypes = Object.keys(renderSchema.BLOCK_TYPES);
assert(allTypes.length > 0, "render-schema must expose BLOCK_TYPES");

allTypes.forEach(function (key) {
  var type = renderSchema.BLOCK_TYPES[key];
  var fixture = BLOCK_FIXTURES[type];
  assert(
    fixture,
    "新增了 block 类型 '" + type + "' 但没在本测试补 fixture——" +
      "请补上并确认它不会吞掉正文（见文件头事故说明）",
  );

  var state = renderWith({
    schema_version: 1,
    blocks: [fixture],
    fallback_text: ANSWER_BODY,
  });

  assert(
    visibleSurfaceCount(state) > 0,
    "block 类型 '" + type + "' 让整篇答案消失了：" +
      "renderableContent/blocks/mcqCards/originalContent 全空。" +
      "服务端已经把正文放在 fallback_text 里，客户端不得主动丢弃。",
  );
});

// ---------------------------------------------------------------------------
// 2) 事故直采样本：纯散文型 presentation 必须原样保留正文
//    （这是 owner 那一轮案例题的实际形态）
// ---------------------------------------------------------------------------
[
  [BLOCK_FIXTURES.paragraph],
  [BLOCK_FIXTURES.heading, BLOCK_FIXTURES.paragraph],
  [BLOCK_FIXTURES.callout],
  [BLOCK_FIXTURES.list],
  [BLOCK_FIXTURES.quote],
  [BLOCK_FIXTURES.code],
].forEach(function (blocks) {
  var label = blocks
    .map(function (b) {
      return b.type;
    })
    .join("+");
  var state = renderWith({
    schema_version: 1,
    blocks: blocks,
    fallback_text: ANSWER_BODY,
  });
  assert(
    String(state.renderableContent || "").indexOf("监理工程师应当签发工程暂停令") >= 0 ||
      (state.blocks || []).length > 0,
    "散文型 presentation(" + label + ") 必须把 fallback_text 正文渲染出来",
  );
});

// ---------------------------------------------------------------------------
// 3) 对照组：真正会被渲染成结构块的类型，仍然按原样吞掉重复正文
//    （防止修复过度、导致正文与结构块重复刷屏）
// ---------------------------------------------------------------------------
[["steps", BLOCK_FIXTURES.steps], ["recap", BLOCK_FIXTURES.recap]].forEach(function (row) {
  var state = renderWith({
    schema_version: 1,
    blocks: [row[1]],
    fallback_text: ANSWER_BODY,
  });
  assert.strictEqual(
    String(state.renderableContent || "").trim(),
    "",
    row[0] + " 块自身即正文，不应再重复渲染 fallback_text",
  );
  assert(
    (state.blocks || []).length > 0,
    row[0] + " 块必须被渲染成结构块，否则答案同样会消失",
  );
});

// table/chart/formula 这类「图示型」块不承载正文，正文必须并存
[["table", BLOCK_FIXTURES.table], ["chart", BLOCK_FIXTURES.chart]].forEach(function (row) {
  var state = renderWith({
    schema_version: 1,
    blocks: [row[1]],
    fallback_text: ANSWER_BODY,
  });
  assert(
    String(state.renderableContent || "").trim().length > 0,
    row[0] + " 块不承载正文，fallback_text 必须并存",
  );
});

// ---------------------------------------------------------------------------
// 3b) 混合形态：一个"能渲染且承载正文"的块 + 图示型块，仍按去重处理；
//     但只要混进一个没有渲染分支的类型，正文就必须回来。
// ---------------------------------------------------------------------------
var mixedSubsuming = renderWith({
  schema_version: 1,
  blocks: [BLOCK_FIXTURES.steps, BLOCK_FIXTURES.recap, BLOCK_FIXTURES.chart],
  fallback_text: ANSWER_BODY,
});
assert.strictEqual(
  String(mixedSubsuming.renderableContent || "").trim(),
  "",
  "steps+recap+chart 全部可渲染且 steps/recap 即正文，不应重复渲染 fallback_text",
);
assert(
  (mixedSubsuming.blocks || []).length >= 3,
  "steps+recap+chart 必须各自渲染成结构块",
);

var mixedWithUnrenderable = renderWith({
  schema_version: 1,
  blocks: [BLOCK_FIXTURES.steps, BLOCK_FIXTURES.paragraph],
  fallback_text: ANSWER_BODY,
});
assert(
  visibleSurfaceCount(mixedWithUnrenderable) > 0,
  "steps+paragraph 中 paragraph 无渲染分支，正文必须保留，宁可重复也不能丢",
);

// 未知/未来新增的 block 类型必须 fail-open（保留正文），不得吞答案
var unknownType = renderWith({
  schema_version: 1,
  blocks: [BLOCK_FIXTURES.table, { type: "timeline_v2", text: "未来新增类型" }],
  fallback_text: ANSWER_BODY,
});
assert(
  visibleSurfaceCount(unknownType) > 0,
  "遇到没有渲染分支的未知 block 类型时必须保留正文（fail-open）",
);

// ---------------------------------------------------------------------------
// 3c) 事故主因：结构块是「补充」而不是「替代」时，正文一个字都不能少。
//     还原 rubric_grader_v1.py:1188 的真实形态——案例题判分下发
//     content=完整批改正文（数千字）+ blocks=[一张两行的 recap 结论卡]。
//     只要凭"出现了 recap"就吞正文，学员就只剩一张小结论卡（owner 线上现场）。
//     判据必须按内容比对：正文显著长于结构块投影 => 必须保留。
// ---------------------------------------------------------------------------
var gradingNarrative = [];
for (var g = 1; g <= 40; g++) {
  gradingNarrative.push("第" + g + "段：本段展开采分点分析与教材依据引用，属于正文必须完整呈现的内容。");
}
var caseGradingBody = "## 批改结果\n\n" + gradingNarrative.join("\n\n");
var caseGradingState = renderWith({
  schema_version: 1,
  blocks: [
    {
      type: "recap",
      title: "批改结论",
      summary: "本轮得分 8/12",
      bullets: ["整体采分点覆盖不错", "本评分为 AI 阅卷草稿，非正式成绩。"],
    },
  ],
  fallback_text: caseGradingBody,
});
// 正文可能落在 renderableContent 或被解析成 markdown blocks，两者都算可见
var caseGradingVisibleText =
  String(caseGradingState.renderableContent || "") +
  JSON.stringify(caseGradingState.blocks || []);
assert(
  caseGradingVisibleText.indexOf("第40段") >= 0,
  "案例题判分：recap 只是补充结论卡，数千字批改正文必须完整保留，" +
    "不得因为出现 recap 就整篇吞掉（线上「只剩一张处理摘要卡片」的主因）",
);

// 反向对照：结构块确实已复述了正文时，仍应去重，避免同屏重复两遍
var duplicatedState = renderWith({
  schema_version: 1,
  blocks: [
    {
      type: "recap",
      title: "本节课总结",
      summary: "先结构化，再渲染。",
      bullets: ["步骤要稳定", "总结要轻量"],
    },
  ],
  fallback_text: "先结构化，再渲染。",
});
assert.strictEqual(
  String(duplicatedState.renderableContent || "").trim(),
  "",
  "结构块已完整复述正文时应去重，不得同屏重复两遍",
);

// ---------------------------------------------------------------------------
// 4) 空 presentation / 无 presentation 的直通路径不受影响
// ---------------------------------------------------------------------------
[null, { schema_version: 1, blocks: [], fallback_text: ANSWER_BODY }].forEach(function (p) {
  var state = renderWith(p);
  assert(
    visibleSurfaceCount(state) > 0,
    "无结构块时必须直接渲染正文（流式直通路径）",
  );
});

// ---------------------------------------------------------------------------
// 5) 两份小程序副本的渲染权威必须逐字节一致，避免只修一边
// ---------------------------------------------------------------------------
var fs = require("fs");
var primary = fs.readFileSync(path.join(UTILS, "ai-message-state.js"), "utf8");
var legacyPath = path.join(__dirname, "../../wx_miniprogram/utils/ai-message-state.js");
if (fs.existsSync(legacyPath)) {
  assert.strictEqual(
    fs.readFileSync(legacyPath, "utf8"),
    primary,
    "wx_miniprogram/utils/ai-message-state.js 与 yousenwebview 副本已漂移——" +
      "渲染权威必须同步，否则旧包会重犯「答案消失」",
  );
}

console.log("PASS test_presentation_never_drops_answer.js");
