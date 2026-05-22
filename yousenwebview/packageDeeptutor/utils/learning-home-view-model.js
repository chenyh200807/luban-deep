function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizePrompt(item, index) {
  var source = asObject(item);
  var text = compactText(source.text || source.title || source.query || source.prompt);
  if (!text) return null;
  var promptType = compactText(source.prompt_type || source.type || "learning_prompt");
  return {
    key: compactText(source.key || promptType + "-" + index),
    text: text,
    title: compactText(source.title || text),
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
  var focusTitle = compactText(focus.title || today.hint || "按当前状态推进建筑实务").replace(
    /^今日焦点[:：]\s*/,
    "",
  );
  var prompts = asList(body.recommended_prompts)
    .map(normalizePrompt)
    .filter(Boolean)
    .slice(0, 4);
  var primaryPrompt = prompts[0] || {};
  return {
    reviewCount: Number(review.overdue || 0) + Number(review.due_today || 0),
    focusLabel: compactText(focus.label || "今日焦点"),
    focusTone: compactText(focus.tone || "plan"),
    focusTitle: focusTitle,
    focusMeta: compactText(focus.meta || ""),
    focusText: focusTitle,
    focusQuery: compactText(focus.query || focus.prompt || primaryPrompt.text),
    focusPromptIntent: asObject(focus.prompt_intent || focus.intent || primaryPrompt.promptIntent),
    recommendedPrompts: prompts,
  };
}

module.exports = {
  buildLearningHomeViewModel: buildLearningHomeViewModel,
};
