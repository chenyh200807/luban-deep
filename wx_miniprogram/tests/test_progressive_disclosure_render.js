// plan §Phase 5 / Batch E Gap 2 — wx 端 progressive_disclosure 接入测试。
// 验证：
//   1. result.metadata.progressive_disclosure → message.progressiveDisclosure
//   2. grading_key / correct_answer / scoring_points / explanation 永远不进 wx state
//   3. action chips 含再练3题/讲透这个点/看记忆口诀 语义

var assert = require("assert");
var renderSchema = require("../utils/render-schema");
var aiMessageState = require("../utils/ai-message-state");

// 1) sanitize 拒绝 hidden authority
var dirty = {
  verdict: "本题答错",
  one_line_diagnosis: "漏掉关键采分点",
  primary_next_action: { slug: "explain_thoroughly", label: "讲透这个点", role: "primary" },
  secondary_actions: [
    { slug: "practice_more_3", label: "再练3题", role: "secondary" },
    { slug: "show_mnemonic", label: "看记忆口诀", role: "secondary" },
    { slug: "extra", label: "should be dropped", role: "secondary" },
  ],
  sections: {
    verdict: "本题答错",
    why_wrong: "漏掉关键采分点",
    grading_key: "DO NOT LEAK",
    correct_answer: "DO NOT LEAK",
    scoring_points: "DO NOT LEAK",
    explanation: "DO NOT LEAK",
  },
  difficulty_pacing: "suggest_consolidation",
  grading_source: "grading_key",
};
var clean = renderSchema.sanitizeProgressiveDisclosure(dirty);
assert(clean, "sanitize returns non-null for valid payload");
assert.strictEqual(clean.primaryNextAction.slug, "explain_thoroughly");
assert.strictEqual(clean.primaryNextAction.label, "讲透这个点");
assert.strictEqual(clean.secondaryActions.length, 2, "max 2 secondary actions");
// gradingSource 合法值是 "grading_key" 字符串标签，所以 leak 检查只看 sections 内容。
assert(!("grading_key" in clean.sections), "sections must drop grading_key key");
assert(!("correct_answer" in clean.sections), "sections must drop correct_answer key");
assert(!("scoring_points" in clean.sections), "sections must drop scoring_points key");
assert(!("explanation" in clean.sections), "sections must drop explanation key");
assert(JSON.stringify(clean.sections).indexOf("DO NOT LEAK") < 0, "sections must not leak hidden values");
assert.strictEqual(clean.difficultyPacing, "suggest_consolidation");
assert.strictEqual(clean.gradingSource, "grading_key");

// 2) ai-message-state 把 input.progressiveDisclosure 透传到 state
var state = aiMessageState.deriveAiMessageRenderState({
  content: "本题答错。详细解释见下。",
  progressiveDisclosure: dirty,
});
assert(state.progressiveDisclosure, "render state must include progressiveDisclosure");
assert.strictEqual(state.progressiveDisclosure.verdict, "本题答错");
var stateSec = state.progressiveDisclosure.sections;
assert(!("grading_key" in stateSec), "state.sections must drop grading_key");
assert(!("correct_answer" in stateSec), "state.sections must drop correct_answer");
assert(!("scoring_points" in stateSec), "state.sections must drop scoring_points");
assert(JSON.stringify(stateSec).indexOf("DO NOT LEAK") < 0, "state.sections must not leak hidden values");

// 3) action chips 必须覆盖 3 个语义 (单独验证 sanitize 不丢标签)
var actionLabels = [clean.primaryNextAction.label].concat(
  clean.secondaryActions.map(function (a) { return a.label; })
);
["再练3题", "讲透这个点", "看记忆口诀"].forEach(function (label) {
  assert(actionLabels.indexOf(label) >= 0, "expected action label: " + label);
});

// 4) 空 payload 返回 null
assert.strictEqual(renderSchema.sanitizeProgressiveDisclosure(null), null);
assert.strictEqual(renderSchema.sanitizeProgressiveDisclosure({}), null);

// 5) verdict / diagnosis 截断
var long = { verdict: "a".repeat(200), one_line_diagnosis: "b".repeat(200) };
var truncated = renderSchema.sanitizeProgressiveDisclosure(long);
assert(truncated.verdict.length <= 120, "verdict <=120 chars");
assert(truncated.oneLineDiagnosis.length <= 80, "diagnosis <=80 chars");

// 6) difficultyPacing 非法值回 hold
var bad = renderSchema.sanitizeProgressiveDisclosure({ verdict: "v", difficulty_pacing: "bogus" });
assert.strictEqual(bad.difficultyPacing, "hold");

console.log("PASS test_progressive_disclosure_render.js (6 assertions groups)");
