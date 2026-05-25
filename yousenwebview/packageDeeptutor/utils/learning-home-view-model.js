function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

var LEGACY_PROMPT_TYPES = ["practice_prompt", "mistake_review", "concept_explain"];

function copyObject(value) {
  var source = asObject(value);
  var result = {};
  Object.keys(source).forEach(function (key) {
    result[key] = source[key];
  });
  return result;
}

function isAssessmentPrompt(source, text) {
  var payload = asObject(source);
  var kind = compactText(payload.prompt_type || payload.type || payload.action_type).toLowerCase();
  var signal = compactText(asObject(payload.intent || payload.prompt_intent).learning_signal_type).toLowerCase();
  var copy = compactText(text || payload.text || payload.title || payload.query || payload.prompt);
  if (kind === "discovery_probe" || kind === "assessment" || kind === "diagnostic") return true;
  if (signal === "discovery_probe" || signal === "assessment") return true;
  return /^(?:先|立即|开始|去)?\s*(?:做|完成|来)?\s*(?:一次)?\s*(?:摸底测试|摸底测评|起步测评|模拟测评|诊断测试)/.test(copy);
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
  if (key === "mistake_review" || key === "wrong_item_review") return palette[1];
  if (key === "concept_explain" || key === "concept_review") return palette[2];
  if (key === "exam_transfer") return palette[3];
  if (key === "knowledge_map") return palette[4];
  if (key === "quick_check") return palette[5];
  return palette[index % palette.length];
}

function getPromptTopic(source, text) {
  var intent = asObject(source.intent || source.prompt_intent);
  var topic = compactText(
    intent.concept_label ||
      intent.error_label ||
      source.concept_label ||
      source.topic ||
      source.focus_topic,
  );
  if (topic) return topic;
  return compactText(text)
    .replace(/^用\s*\d+\s*道题训练/, "")
    .replace(/^复盘/, "")
    .replace(/^讲清楚/, "")
    .replace(/^用一道真题场景理解/, "")
    .replace(/^梳理/, "")
    .replace(/^用\s*1\s*个小问题验证/, "")
    .replace(/的?(?:关键判断|高频考点|是否真会了)$/, "");
}

function hasLegacyThreePromptSet(items) {
  if (!items || items.length !== 3) return false;
  var seen = {};
  items.forEach(function (item) {
    var source = asObject(item);
    var promptType = compactText(source.prompt_type || source.type).toLowerCase();
    if (promptType) seen[promptType] = true;
  });
  return LEGACY_PROMPT_TYPES.every(function (promptType) {
    return !!seen[promptType];
  });
}

function buildSupplementPrompt(baseItem, promptType, text) {
  var base = asObject(baseItem);
  var intent = copyObject(base.intent || base.prompt_intent);
  intent.prompt_type = promptType;
  return {
    key: "legacy-upgrade-" + promptType,
    prompt_type: promptType,
    text: text,
    evidence_refs: asList(base.evidence_refs || base.evidenceRefs),
    learning_state_ref: compactText(base.learning_state_ref || base.learningStateRef),
    suggested_mode: compactText(base.suggested_mode || base.suggestedMode),
    intent: intent,
  };
}

function upgradeLegacyThreePrompts(items) {
  var rawPrompts = asList(items);
  if (!hasLegacyThreePromptSet(rawPrompts)) return rawPrompts;
  var base = rawPrompts[0] || {};
  var topic = getPromptTopic(base, compactText(base.text || base.title || base.query || base.prompt)) || "当前考点";
  return rawPrompts.concat([
    buildSupplementPrompt(base, "exam_transfer", "用一道真题场景理解" + topic),
    buildSupplementPrompt(base, "knowledge_map", "梳理" + topic + "的高频考点"),
    buildSupplementPrompt(base, "quick_check", "用 1 个小问题验证" + topic + "是否真会了"),
  ]);
}

function normalizePrompt(item, index) {
  var source = asObject(item);
  var text = compactText(source.text || source.title || source.query || source.prompt);
  if (!text) return null;
  if (isAssessmentPrompt(source, text)) return null;
  var promptType = compactText(source.prompt_type || source.type || "learning_prompt");
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
    learningStateRef: compactText(source.learning_state_ref || source.learningStateRef),
    suggestedMode: compactText(source.suggested_mode || source.suggestedMode),
    promptIntent: asObject(source.intent || source.prompt_intent),
  };
}

function buildLearningHomeViewModel(dashboard) {
  var body = asObject(dashboard);
  var review = asObject(body.review);
  var today = asObject(body.today);
  var focus = asObject(body.today_focus || today.focus);
  var rawPrompts = upgradeLegacyThreePrompts(body.recommended_prompts);
  var focusTitle = compactText(focus.title || today.hint || "按当前状态推进建筑实务").replace(
    /^今日焦点[:：]\s*/,
    "",
  );
  var prompts = rawPrompts
    .map(normalizePrompt)
    .filter(Boolean)
    .slice(0, 6);
  var assessmentAction = rawPrompts.some(function (item) {
    return isAssessmentPrompt(item);
  });
  var primaryPrompt = prompts[0] || {};
  var focusQuery = assessmentAction
    ? ""
    : compactText(focus.query || focus.prompt || primaryPrompt.text);
  return {
    reviewCount: Number(review.overdue || 0) + Number(review.due_today || 0),
    focusLabel: compactText(focus.label || "今日焦点"),
    focusTone: compactText(focus.tone || "plan"),
    focusTitle: focusTitle,
    focusMeta: compactText(focus.meta || ""),
    focusText: focusTitle,
    focusQuery: focusQuery,
    focusActionType: assessmentAction ? "assessment" : focusQuery ? "prompt" : "",
    focusPromptIntent: asObject(focus.prompt_intent || focus.intent || primaryPrompt.promptIntent),
    recommendedPrompts: prompts,
  };
}

module.exports = {
  buildLearningHomeViewModel: buildLearningHomeViewModel,
};
