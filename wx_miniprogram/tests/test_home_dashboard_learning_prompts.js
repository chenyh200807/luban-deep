// Run: node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var wxVmPath = path.join(__dirname, "../utils/learning-home-view-model.js");
var yousenVmPath = path.join(
  __dirname,
  "../../yousenwebview/packageDeeptutor/utils/learning-home-view-model.js",
);
var chatSourcePath = path.join(__dirname, "../pages/chat/chat.js");
var chatWxmlPath = path.join(__dirname, "../pages/chat/chat.wxml");
var wsSourcePath = path.join(__dirname, "../utils/ws-stream.js");

var wxVm = require(wxVmPath);
var yousenVm = require(yousenVmPath);
var dashboard = {
  review: { overdue: 1, due_today: 2 },
  today_focus: {
    label: "今日焦点",
    title: "主体结构专项",
    meta: "来自最近批改",
    prompt_intent: { source: "home_dashboard", learning_signal_type: "home_prompt_clicked" },
  },
  recommended_prompts: [
    {
      text: "讲一下主体结构验收",
      prompt_type: "concept_explain",
      intent: { source: "home_dashboard", learning_signal_type: "concept_explain" },
    },
    {
      text: "我还是没懂防水节点",
      prompt_type: "still_confused",
      intent: { source: "home_dashboard", learning_signal_type: "still_confused" },
    },
  ],
};

assert.deepStrictEqual(
  wxVm.buildLearningHomeViewModel(dashboard),
  yousenVm.buildLearningHomeViewModel(dashboard),
);
var model = wxVm.buildLearningHomeViewModel(dashboard);
assert.strictEqual(model.reviewCount, 3);
assert.strictEqual(model.recommendedPrompts.length, 2);
assert.strictEqual(model.recommendedPrompts[0].promptIntent.learning_signal_type, "concept_explain");

var chatSource = fs.readFileSync(chatSourcePath, "utf8");
var chatWxml = fs.readFileSync(chatWxmlPath, "utf8");
var wsSource = fs.readFileSync(wsSourcePath, "utf8");
assert(chatSource.indexOf("learning-home-view-model") >= 0);
assert(chatSource.indexOf("onRecommendedPromptTap") >= 0);
assert(chatWxml.indexOf("recommendedPrompts") >= 0);
assert(wsSource.indexOf("prompt_intent") >= 0);
assert(fs.readFileSync(wxVmPath, "utf8").indexOf("buildFallbackFocusQuery") < 0);
