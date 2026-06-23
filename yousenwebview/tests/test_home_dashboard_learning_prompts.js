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

function trustedHomeProjection(payload) {
  var projection = Object.assign({}, payload);
  delete projection.review;
  return {
    review: payload.review,
    home_projection: Object.assign(
      {
        source_status: {
          home_projection_contract: "canonical_taxonomy_v1",
          topic_authority: "learner_state.home_personalization.canonical_taxonomy",
        },
      },
      projection,
    ),
  };
}

var TOPIC_CODES = {
  主体结构工程施工: "1A413040",
  项目质量计划管理: "1A434",
  防水工程: "1A413000-C24",
  屋面与防水工程施工: "1A413050",
};

function canonicalIntent(topic) {
  return {
    source: "learner_state.home_personalization",
    concept_label: topic,
    taxonomy_code: TOPIC_CODES[topic] || "",
    taxonomy_id: TOPIC_CODES[topic] || "",
    topic_source: TOPIC_CODES[topic] ? "taxonomy_label" : "",
    topic_confidence: TOPIC_CODES[topic] ? "high" : "",
  };
}

function canonicalPrompt(text, promptType, topic) {
  return {
    text: text,
    prompt_type: promptType,
    intent: canonicalIntent(topic),
  };
}

var model = vm.buildLearningHomeViewModel(trustedHomeProjection({
  review: { overdue: 0, due_today: 1 },
  today_focus: {
    title: "今日焦点：主体结构工程施工",
    prompt: "讲清楚主体结构工程施工的关键判断",
    intent: canonicalIntent("主体结构工程施工"),
  },
  recommended_prompts: [
    canonicalPrompt("讲清楚主体结构工程施工的关键判断", "concept_explain", "主体结构工程施工"),
  ],
}));
assert.strictEqual(model.focusTitle, "主体结构工程施工");
assert.strictEqual(model.recommendedPrompts[0].text, "讲清楚主体结构工程施工的关键判断");
assert.strictEqual(model.focusQuery, "讲清楚主体结构工程施工的关键判断");
assert.strictEqual(model.focusActionType, "prompt");

var assessmentModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  today_focus: { title: "一题，给系统第一份学习证据" },
  recommended_prompts: [
    { text: "先做一次模拟测评", prompt_type: "discovery_probe" },
  ],
}));
assert.strictEqual(assessmentModel.focusActionType, "assessment");
assert.strictEqual(assessmentModel.focusTitle, "先做 1 题摸底");
assert.strictEqual(assessmentModel.focusMeta, "生成学情基线");
assert.strictEqual(assessmentModel.focusQuery, "");
assert.strictEqual(assessmentModel.recommendedPrompts.length, 0);

var assessmentLessonModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  recommended_prompts: [
    { text: "讲一下阶段测评后应该怎么复盘", prompt_type: "concept_explain" },
  ],
}));
assert.strictEqual(assessmentLessonModel.focusActionType, "");
assert.strictEqual(assessmentLessonModel.recommendedPrompts.length, 0);

var legacyThreePromptModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  recommended_prompts: [
    {
      text: "用 3 道题训练项目质量计划管理",
      prompt_type: "practice_prompt",
      intent: canonicalIntent("项目质量计划管理"),
    },
    {
      text: "复盘项目质量计划管理里的错因",
      prompt_type: "mistake_review",
      intent: canonicalIntent("项目质量计划管理"),
    },
    {
      text: "讲清楚项目质量计划管理的关键判断",
      prompt_type: "concept_explain",
      intent: canonicalIntent("项目质量计划管理"),
    },
  ],
}));
assert.deepStrictEqual(
  legacyThreePromptModel.recommendedPrompts.map(function (item) { return item.promptType; }),
  [
    "practice_prompt",
    "mistake_review",
    "concept_explain",
  ],
);
assert.deepStrictEqual(
  legacyThreePromptModel.recommendedPrompts.map(function (item) { return item.displayTitle; }),
  ["专项训练", "错题复盘", "关键判断"],
);

var badFocusWithGoodPromptModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  today_focus: {
    title: "今日焦点：直接练题才能把",
    prompt: "用 3 道题训练直接练题才能把",
    intent: canonicalIntent("直接练题才能把"),
  },
  recommended_prompts: [
    canonicalPrompt("用 3 道题训练主体结构工程施工", "practice_prompt", "主体结构工程施工"),
  ],
}));
assert.strictEqual(badFocusWithGoodPromptModel.focusTitle, "");
assert.strictEqual(badFocusWithGoodPromptModel.focusQuery, "");
assert.strictEqual(badFocusWithGoodPromptModel.focusActionType, "");
assert.strictEqual(badFocusWithGoodPromptModel.recommendedPrompts.length, 1);

var markedFreeTextProjectionModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  today_focus: {
    title: "今日焦点：出三道屋面防水的",
    prompt: "用 3 道题训练出三道屋面防水的",
    intent: canonicalIntent("出三道屋面防水的"),
  },
  recommended_prompts: [
    canonicalPrompt("用 3 道题训练出三道屋面防水的", "practice_prompt", "出三道屋面防水的"),
  ],
}));
assert.strictEqual(markedFreeTextProjectionModel.focusTitle, "");
assert.strictEqual(markedFreeTextProjectionModel.focusQuery, "");
assert.strictEqual(markedFreeTextProjectionModel.focusActionType, "");
assert.strictEqual(markedFreeTextProjectionModel.recommendedPrompts.length, 0);
assert.strictEqual(vm.isTrustedHomeDashboardPayload(trustedHomeProjection({
  today_focus: {
    title: "今日焦点：出三道屋面防水的",
    prompt: "用 3 道题训练出三道屋面防水的",
    intent: canonicalIntent("出三道屋面防水的"),
  },
  recommended_prompts: [
    canonicalPrompt("用 3 道题训练出三道屋面防水的", "practice_prompt", "出三道屋面防水的"),
  ],
})), false);

var forgedCodeFreeTextIntent = Object.assign(canonicalIntent("出三道屋面防水的"), {
  taxonomy_code: "1A413050",
  taxonomy_id: "1A413050",
  topic_source: "taxonomy_label",
  topic_confidence: "high",
});
var forgedCodeFreeTextModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  today_focus: {
    title: "今日焦点：出三道屋面防水的",
    prompt: "用 3 道题训练出三道屋面防水的",
    intent: forgedCodeFreeTextIntent,
  },
  recommended_prompts: [
    {
      text: "用 3 道题训练出三道屋面防水的",
      prompt_type: "practice_prompt",
      intent: forgedCodeFreeTextIntent,
    },
  ],
}));
assert.strictEqual(forgedCodeFreeTextModel.focusTitle, "");
assert.strictEqual(forgedCodeFreeTextModel.recommendedPrompts.length, 0);

["今日推进", "直接练题才能把"].forEach(function (badTopic) {
  var badIntent = Object.assign(canonicalIntent(badTopic), {
    taxonomy_code: "1A413050",
    taxonomy_id: "1A413050",
    topic_source: "taxonomy_label",
    topic_confidence: "high",
  });
  var badModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
    today_focus: {
      title: "今日焦点：" + badTopic,
      prompt: "用 3 道题训练" + badTopic,
      intent: badIntent,
    },
    recommended_prompts: [
      {
        text: "用 3 道题训练" + badTopic,
        prompt_type: "practice_prompt",
        intent: badIntent,
      },
    ],
  }));
  assert.strictEqual(badModel.focusTitle, "");
  assert.strictEqual(badModel.recommendedPrompts.length, 0);
});

var stringFallbackModel = vm.buildLearningHomeViewModel({
  home_projection: {
    source_status: {
      home_projection_contract: "canonical_taxonomy_v1",
      topic_authority: "learner_state.home_personalization.canonical_taxonomy",
      fallback_used: "true",
    },
    today_focus: {
      title: "今日焦点：主体结构工程施工",
      prompt: "用 3 道题训练主体结构工程施工",
      intent: canonicalIntent("主体结构工程施工"),
    },
    recommended_prompts: [
      canonicalPrompt("用 3 道题训练主体结构工程施工", "practice_prompt", "主体结构工程施工"),
    ],
  },
});
assert.strictEqual(stringFallbackModel.focusTitle, "");
assert.strictEqual(stringFallbackModel.recommendedPrompts.length, 0);

var sixPromptModel = vm.buildLearningHomeViewModel(trustedHomeProjection({
  recommended_prompts: [
    canonicalPrompt("用 3 道题训练项目质量计划管理", "practice_prompt", "项目质量计划管理"),
    canonicalPrompt("复盘项目质量计划管理里的错因", "mistake_review", "项目质量计划管理"),
    canonicalPrompt("讲清楚项目质量计划管理的关键判断", "concept_explain", "项目质量计划管理"),
    canonicalPrompt("用一道真题场景理解项目质量计划管理", "exam_transfer", "项目质量计划管理"),
    canonicalPrompt("梳理项目质量计划管理的高频考点", "knowledge_map", "项目质量计划管理"),
    canonicalPrompt("用 1 个小问题验证项目质量计划管理是否真会了", "quick_check", "项目质量计划管理"),
    canonicalPrompt("第七条不应该展示", "learning_prompt", "项目质量计划管理"),
  ],
}));
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
assert(chatSource.indexOf('focusTitle: "今日推进"') < 0);
assert(wsSource.indexOf("prompt_intent") >= 0);
assert(fs.readFileSync(yousenVmPath, "utf8").indexOf("buildFallbackFocusQuery") < 0);
