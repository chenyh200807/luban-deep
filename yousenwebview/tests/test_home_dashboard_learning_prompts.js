// Run: node yousenwebview/tests/test_home_dashboard_learning_prompts.js
var assert = require("assert");
var fs = require("fs");
var path = require("path");

var wxVmPath = path.join(
  __dirname,
  "../../wx_miniprogram/utils/learning-home-view-model.js",
);
var yousenVmPath = path.join(
  __dirname,
  "../packageDeeptutor/utils/learning-home-view-model.js",
);
var chatSourcePath = path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js");
var chatWxmlPath = path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml");
var wsSourcePath = path.join(__dirname, "../packageDeeptutor/utils/ws-stream.js");

assert.strictEqual(
  fs.readFileSync(wxVmPath, "utf8"),
  fs.readFileSync(yousenVmPath, "utf8"),
  "wx and yousen home view models must stay byte-identical",
);

var vm = require(yousenVmPath);
var model = vm.buildLearningHomeViewModel({
  review: { overdue: 0, due_today: 1 },
  today: { hint: "按当前状态推进建筑实务" },
  recommended_prompts: [
    {
      text: "练 3 道主体结构题",
      prompt_type: "practice_prompt",
      intent: { source: "home_dashboard", learning_signal_type: "home_prompt_clicked" },
    },
  ],
});
assert.strictEqual(model.focusTitle, "按当前状态推进建筑实务");
assert.strictEqual(model.recommendedPrompts[0].text, "练 3 道主体结构题");

var chatSource = fs.readFileSync(chatSourcePath, "utf8");
var chatWxml = fs.readFileSync(chatWxmlPath, "utf8");
var wsSource = fs.readFileSync(wsSourcePath, "utf8");
assert(chatSource.indexOf("learning-home-view-model") >= 0);
assert(chatSource.indexOf("onRecommendedPromptTap") >= 0);
assert(chatWxml.indexOf("recommendedPrompts") >= 0);
assert(wsSource.indexOf("prompt_intent") >= 0);
assert(fs.readFileSync(yousenVmPath, "utf8").indexOf("buildFallbackFocusQuery") < 0);
