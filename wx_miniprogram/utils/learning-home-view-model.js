function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim();
}

var HOME_PROJECTION_CONTRACT = "canonical_taxonomy_v1";
var HOME_PROJECTION_TOPIC_AUTHORITY =
  "learner_state.home_personalization.canonical_taxonomy";

function homeProjectionSourceStatus(body) {
  return asObject(
    body.source_status ||
      asObject(body.home_projection).source_status ||
      asObject(body.projection).source_status,
  );
}

function hasHomeProjectionSurface(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return false;
  return Boolean(
    body.home_projection ||
      body.projection ||
      body.today_focus ||
      body.recommended_prompts ||
      asObject(body.today).focus,
  );
}

function isTrustedHomeDashboardPayload(dashboard) {
  var body = asObject(dashboard);
  if (!hasHomeProjectionSurface(body)) return true;
  var sourceStatus = homeProjectionSourceStatus(body);
  return (
    sourceStatus.home_projection_contract === HOME_PROJECTION_CONTRACT &&
    sourceStatus.topic_authority === HOME_PROJECTION_TOPIC_AUTHORITY
  );
}

function isStarterFocusTitle(value) {
  var text = compactText(value);
  return /第一份.*学习证据/.test(text) || /给系统.*学习证据/.test(text);
}

function normalizeFocusTitle(value, assessmentAction) {
  var title = compactText(value).replace(/^今日焦点[:：]\s*/, "");
  if (isStarterFocusTitle(title)) return "先做 1 题摸底";
  if (assessmentAction && (!title || title === "今日焦点"))
    return "先做 1 题摸底";
  return title;
}

function normalizeFocusMeta(value, title, assessmentAction) {
  var meta = compactText(value);
  if (meta === "starter" || isStarterFocusTitle(title) || assessmentAction)
    return "生成学情基线";
  if (/learner_state\.home_personalization/.test(meta)) return "来自学情更新";
  return meta;
}

function isAssessmentPrompt(source, text) {
  var payload = asObject(source);
  var kind = compactText(
    payload.prompt_type || payload.type || payload.action_type,
  ).toLowerCase();
  var signal = compactText(
    asObject(payload.intent || payload.prompt_intent).learning_signal_type,
  ).toLowerCase();
  var copy = compactText(
    text || payload.text || payload.title || payload.query || payload.prompt,
  );
  if (
    kind === "discovery_probe" ||
    kind === "assessment" ||
    kind === "diagnostic"
  )
    return true;
  if (signal === "discovery_probe" || signal === "assessment") return true;
  return /^(?:先|立即|开始|去)?\s*(?:做|完成|来)?\s*(?:一次)?\s*(?:摸底测试|摸底测评|起步测评|模拟测评|诊断测试)/.test(
    copy,
  );
}

function getPromptVisual(promptType, index) {
  var key = compactText(promptType).toLowerCase();
  var palette = [
    {
      icon: "▧",
      title: "专项训练",
      bgDark: "rgba(245,158,11,0.16)",
      fgDark: "#fbbf24",
      bgLight: "#fff4e0",
      fgLight: "#c88a2b",
    },
    {
      icon: "○",
      title: "错题复盘",
      bgDark: "rgba(59,130,246,0.16)",
      fgDark: "#93c5fd",
      bgLight: "#e9f1ff",
      fgLight: "#4c72d4",
    },
    {
      icon: "△",
      title: "关键判断",
      bgDark: "rgba(96,165,250,0.12)",
      fgDark: "#7dd3fc",
      bgLight: "#edf4ff",
      fgLight: "#3b82f6",
    },
    {
      icon: "☆",
      title: "真题迁移",
      bgDark: "rgba(59,130,246,0.16)",
      fgDark: "#93c5fd",
      bgLight: "#e9f1ff",
      fgLight: "#4c72d4",
    },
    {
      icon: "▤",
      title: "考点梳理",
      bgDark: "rgba(16,185,129,0.14)",
      fgDark: "#5eead4",
      bgLight: "#e4fbf4",
      fgLight: "#0f9f7a",
    },
    {
      icon: "✓",
      title: "自测验证",
      bgDark: "rgba(168,85,247,0.14)",
      fgDark: "#c4b5fd",
      bgLight: "#f3edff",
      fgLight: "#7c3aed",
    },
  ];
  if (key === "practice_prompt" || key === "learning_prompt") return palette[0];
  if (key === "mistake_review" || key === "wrong_item_review")
    return palette[1];
  if (key === "concept_explain" || key === "concept_review") return palette[2];
  if (key === "exam_transfer") return palette[3];
  if (key === "knowledge_map") return palette[4];
  if (key === "quick_check") return palette[5];
  return palette[(index || 0) % palette.length];
}

function getPromptTopic(source, text) {
  void text;
  var intent = asObject(source.intent || source.prompt_intent);
  return compactText(intent.concept_label || source.concept_label);
}

function normalizePrompt(item, index) {
  var source = asObject(item);
  var text = compactText(
    source.text || source.title || source.query || source.prompt,
  );
  if (!text) return null;
  if (isAssessmentPrompt(source, text)) return null;
  var promptType = compactText(
    source.prompt_type || source.type || "learning_prompt",
  );
  var visual = getPromptVisual(promptType, index);
  var displayDesc = getPromptTopic(source, text) || "学情推荐";
  return {
    key: compactText(source.key || promptType + "-" + index),
    text: text,
    title: compactText(source.title || text),
    displayTitle: visual.title,
    displayDesc: displayDesc,
    icon: visual.icon,
    bgDark: visual.bgDark,
    fgDark: visual.fgDark,
    bgLight: visual.bgLight,
    fgLight: visual.fgLight,
    promptType: promptType,
    evidenceRefs: asList(source.evidence_refs || source.evidenceRefs),
    learningStateRef: compactText(
      source.learning_state_ref || source.learningStateRef,
    ),
    suggestedMode: compactText(source.suggested_mode || source.suggestedMode),
    promptIntent: asObject(source.intent || source.prompt_intent),
  };
}

function buildLearningHomeViewModel(dashboard) {
  var body = asObject(dashboard);
  if (hasHomeProjectionSurface(body) && !isTrustedHomeDashboardPayload(body)) {
    body = {};
  }
  var review = asObject(body.review);
  var today = asObject(body.today);
  var focus = asObject(body.today_focus || today.focus);
  var rawPrompts = asList(body.recommended_prompts);
  var prompts = rawPrompts.map(normalizePrompt).filter(Boolean).slice(0, 6);
  var assessmentAction = rawPrompts.some(function (item) {
    return isAssessmentPrompt(item);
  });
  var rawFocusTitle = compactText(focus.title || today.hint || "今日推进");
  var focusTitle = normalizeFocusTitle(rawFocusTitle, assessmentAction);
  var focusQuery = assessmentAction
    ? ""
    : compactText(focus.query || focus.prompt);
  return {
    reviewCount: Number(review.overdue || 0) + Number(review.due_today || 0),
    focusLabel: compactText(focus.label || "今日焦点"),
    focusTone: compactText(focus.tone || "plan"),
    focusTitle: focusTitle,
    focusMeta: normalizeFocusMeta(
      focus.meta || "",
      rawFocusTitle,
      assessmentAction,
    ),
    focusText: focusTitle,
    focusQuery: focusQuery,
    focusActionType: assessmentAction
      ? "assessment"
      : focusQuery
        ? "prompt"
        : "",
    focusPromptIntent: asObject(focus.prompt_intent || focus.intent),
    recommendedPrompts: prompts,
  };
}

module.exports = {
  buildLearningHomeViewModel: buildLearningHomeViewModel,
  isTrustedHomeDashboardPayload: isTrustedHomeDashboardPayload,
};
