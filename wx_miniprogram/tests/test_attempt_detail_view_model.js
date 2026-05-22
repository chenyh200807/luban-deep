// Run: node wx_miniprogram/tests/test_attempt_detail_view_model.js
var assert = require("assert");
var path = require("path");

var wxVm = require(path.join(__dirname, "../utils/attempt-detail-view-model.js"));
var yousenVm = require(path.join(
  __dirname,
  "../../yousenwebview/packageDeeptutor/utils/attempt-detail-view-model.js",
));

var detail = {
  ok: true,
  conversation: {
    title: "主体结构验收条件是什么？",
    turns: [
      {
        role: "system",
        label: "系统出题",
        content: "主体结构验收条件是什么？\nA. 先施工后验收\nB. 施工质量验收合格后进入下一步",
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
assert.strictEqual(wxModel.turns[0].content.indexOf("B. 施工质量验收合格后进入下一步") >= 0, true);
assert.strictEqual(wxModel.turns[1].role, "student");
assert.strictEqual(wxModel.turns[2].content.indexOf("错因：多选漏选") >= 0, true);

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
