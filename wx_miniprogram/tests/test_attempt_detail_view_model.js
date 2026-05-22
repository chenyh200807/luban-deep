// Run: node wx_miniprogram/tests/test_attempt_detail_view_model.js
var assert = require("assert");
var path = require("path");

var wxVm = require(
  path.join(__dirname, "../utils/attempt-detail-view-model.js"),
);
var yousenVm = require(
  path.join(
    __dirname,
    "../../yousenwebview/packageDeeptutor/utils/attempt-detail-view-model.js",
  ),
);

var detail = {
  ok: true,
  conversation: {
    title: "主体结构验收条件是什么？",
    turns: [
      {
        role: "system",
        label: "系统出题",
        content:
          "主体结构验收条件是什么？\nA. 先施工后验收\nB. 施工质量验收合格后进入下一步",
      },
      { role: "student", label: "学员作答", content: "A" },
      {
        role: "system",
        label: "系统解析",
        content: "答错。正确答案：B\n先看验收前置条件。\n错因：多选漏选",
      },
    ],
  },
  answer: { result_label: "答错", user_answer: "A", correct_answer: "B" },
  diagnosis: { concept_label: "主体结构", error_label: "多选漏选" },
};
var card = { timeLabel: "05月20日 22:25", resultLabel: "答错" };

var wxModel = wxVm.buildAttemptDetailViewModel(detail, card);
var yousenModel = yousenVm.buildAttemptDetailViewModel(detail, card);
assert.deepStrictEqual(wxModel, yousenModel);
assert.strictEqual(wxModel.title, "主体结构验收条件是什么？");
assert.strictEqual(wxModel.turns.length, 3);
assert.strictEqual(
  wxModel.turns[0].content.indexOf("B. 施工质量验收合格后进入下一步") >= 0,
  true,
);
assert.strictEqual(wxModel.turns[1].role, "student");
assert.strictEqual(
  wxModel.turns[2].content.indexOf("错因：多选漏选") >= 0,
  true,
);

var fallback = wxVm.buildAttemptDetailViewModel(
  {},
  {
    title: "我想练习建筑构造相关的题目",
    answerLine: "你选：C",
    diagnosisDetail: "C 选项不符合标准答案。",
  },
);
assert.strictEqual(fallback.turns.length, 3);
assert.strictEqual(fallback.turns[0].label, "系统出题");
assert.strictEqual(fallback.turns[1].content, "你选：C");

// Rich explanation sections: backend full_text recovered from history must be
// parsed into ordered student-facing sections; raw transcript remains below.
var richExplanationText = [
  "### 阅卷结论",
  "本题你答了 B（钎探法），正确答案是 A（观察法）。诊断类型：概念混淆——你把“辅助手段”当成了“主要方法”。",
  "",
  "### 为什么错",
  "你记住了“钎探法”是验槽的关键环节，但混淆了主次关系。",
  "",
  "### 知识点",
  "1A412020 验槽方法选择",
  "",
  "### 易错点",
  "把辅助手段当成主要方法。",
  "",
  "### 记忆口诀",
  "先看后探，观察为主。",
  "",
  "### 下一步",
  "请用30秒写出：验槽主要方法：观察法；辅助方法：钎探法。",
  "",
  "### 逐项解析",
  "A 观察法：✅ 主要方法。",
  "B 钎探法：❌ 仅作为辅助手段。",
].join("\n");

var richDetail = {
  ok: true,
  question: {
    stem: "验槽通常主要采用什么方法？",
    options: [
      { key: "A", text: "观察法" },
      { key: "B", text: "钎探法" },
      { key: "C", text: "洛阳铲法" },
      { key: "D", text: "钻探法" },
    ],
  },
  answer: { user_answer: "B", correct_answer: "A", result_label: "答错" },
  diagnosis: { concept_label: "1A412020 验槽方法选择" },
  explanation: {
    summary: "B 选项不符合标准答案。",
    full_text: richExplanationText,
    source: "history_assistant",
  },
  conversation: {
    title: "验槽通常主要采用什么方法？",
    turns: [
      {
        role: "system",
        label: "系统出题",
        content: "验槽通常主要采用什么方法？\nA. 观察法\nB. 钎探法",
      },
      { role: "student", label: "学员作答", content: "B" },
      { role: "system", label: "系统解析", content: richExplanationText },
    ],
  },
};
var richCard = { timeLabel: "今天 22:25", resultLabel: "答错" };

var richWx = wxVm.buildAttemptDetailViewModel(richDetail, richCard);
var richYousen = yousenVm.buildAttemptDetailViewModel(richDetail, richCard);
assert.deepStrictEqual(
  richWx,
  richYousen,
  "wx and yousen view models must agree on rich sections",
);

var sectionLabels = richWx.explanationSections.map(function (item) {
  return item.label;
});
assert.deepStrictEqual(
  sectionLabels,
  [
    "阅卷结论",
    "为什么错",
    "知识点",
    "易错点",
    "记忆口诀",
    "下一步",
    "逐项解析",
  ],
  "explanationSections must preserve student-facing order",
);
var sectionContent = richWx.explanationSections.reduce(function (acc, item) {
  acc[item.label] = item.content;
  return acc;
}, {});
assert.ok(
  sectionContent["为什么错"].indexOf("主次关系") >= 0,
  "为什么错 section must carry the diagnosis from the historical explanation",
);
assert.ok(
  sectionContent["记忆口诀"].indexOf("先看后探") >= 0,
  "记忆口诀 section must carry the mnemonic from the historical explanation",
);
assert.ok(
  sectionContent["下一步"].indexOf("观察法") >= 0,
  "下一步 section must point to the verified primary method",
);
// Raw transcript stays below; system 解析 turn carries the rich source.
var lastTurn = richWx.turns[richWx.turns.length - 1];
assert.strictEqual(lastTurn.label, "系统解析");
assert.ok(
  lastTurn.content.indexOf("先看后探") >= 0,
  "system 解析 turn must include the historical assistant content",
);
// No backend enum text should reach the student-facing sections.
richWx.explanationSections.forEach(function (item) {
  assert.ok(
    !/weak|recurrence|question_reading|discovery_probe|code_application/.test(
      item.content,
    ),
    "rich sections must not expose internal enum values: " + item.label,
  );
});

console.log("PASS test_attempt_detail_view_model.js");
