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
assert.strictEqual(model.focusActionType, "prompt");

var assessmentModel = vm.buildLearningHomeViewModel({
  today_focus: { title: "一题，给系统第一份学习证据" },
  recommended_prompts: [
    { text: "先做一次模拟测评", prompt_type: "discovery_probe" },
  ],
});
assert.strictEqual(assessmentModel.focusActionType, "assessment");
assert.strictEqual(assessmentModel.focusTitle, "先做 1 题摸底");
assert.strictEqual(assessmentModel.focusMeta, "生成学情基线");
assert.strictEqual(assessmentModel.focusQuery, "");
assert.strictEqual(assessmentModel.recommendedPrompts.length, 0);

var assessmentLessonModel = vm.buildLearningHomeViewModel({
  recommended_prompts: [
    { text: "讲一下阶段测评后应该怎么复盘", prompt_type: "concept_explain" },
  ],
});
assert.strictEqual(assessmentLessonModel.focusActionType, "prompt");
assert.strictEqual(assessmentLessonModel.recommendedPrompts.length, 1);

var legacyThreePromptModel = vm.buildLearningHomeViewModel({
  recommended_prompts: [
    {
      text: "用 3 道题训练项目质量计划管理",
      prompt_type: "practice_prompt",
      intent: { concept_label: "项目质量计划管理" },
    },
    {
      text: "复盘项目质量计划管理里的错因",
      prompt_type: "mistake_review",
      intent: { concept_label: "项目质量计划管理" },
    },
    {
      text: "讲清楚项目质量计划管理的关键判断",
      prompt_type: "concept_explain",
      intent: { concept_label: "项目质量计划管理" },
    },
  ],
});
assert.deepStrictEqual(
  legacyThreePromptModel.recommendedPrompts.map(function (item) { return item.promptType; }),
  [
    "practice_prompt",
    "mistake_review",
    "concept_explain",
    "exam_transfer",
    "knowledge_map",
    "quick_check",
  ],
);
assert.deepStrictEqual(
  legacyThreePromptModel.recommendedPrompts.map(function (item) { return item.displayTitle; }),
  ["专项训练", "错题复盘", "关键判断", "真题迁移", "考点梳理", "自测验证"],
);

var sixPromptModel = vm.buildLearningHomeViewModel({
  recommended_prompts: [
    { text: "用 3 道题训练项目质量计划管理", prompt_type: "practice_prompt" },
    { text: "复盘项目质量计划管理里的错因", prompt_type: "mistake_review" },
    { text: "讲清楚项目质量计划管理的关键判断", prompt_type: "concept_explain" },
    { text: "用一道真题场景理解项目质量计划管理", prompt_type: "exam_transfer" },
    { text: "梳理项目质量计划管理的高频考点", prompt_type: "knowledge_map" },
    { text: "用 1 个小问题验证项目质量计划管理是否真会了", prompt_type: "quick_check" },
    { text: "第七条不应该展示", prompt_type: "learning_prompt" },
  ],
});
assert.strictEqual(sixPromptModel.recommendedPrompts.length, 6);
assert.deepStrictEqual(
  sixPromptModel.recommendedPrompts.map(function (item) { return item.displayTitle; }),
  ["专项训练", "错题复盘", "关键判断", "真题迁移", "考点梳理", "自测验证"],
);

var chatSource = fs.readFileSync(chatSourcePath, "utf8");
var chatWxml = fs.readFileSync(chatWxmlPath, "utf8");
var wsSource = fs.readFileSync(wsSourcePath, "utf8");
assert(chatSource.indexOf("learning-home-view-model") >= 0);
assert(chatSource.indexOf("onRecommendedPromptTap") >= 0);
assert(chatSource.indexOf("HOME_DASHBOARD_CACHE_KEY") >= 0);
assert(chatSource.indexOf("readCachedHomeDashboard") >= 0);
assert(chatSource.indexOf("writeCachedHomeDashboard") >= 0);
assert(chatSource.indexOf("buildHomeDashboardUpdate") >= 0);
assert(chatSource.indexOf('focusActionType === "assessment"') >= 0);
assert(chatSource.indexOf("route.assessment()") >= 0);
assert(chatWxml.indexOf("recommendedPrompts") >= 0);
assert(chatSource.indexOf("showStaticExamples") >= 0);
assert(chatWxml.indexOf("showStaticExamples") >= 0);
assert(wsSource.indexOf("prompt_intent") >= 0);
assert(fs.readFileSync(yousenVmPath, "utf8").indexOf("buildFallbackFocusQuery") < 0);
