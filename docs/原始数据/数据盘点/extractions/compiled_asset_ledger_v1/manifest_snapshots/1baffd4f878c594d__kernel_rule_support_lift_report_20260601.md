# 鲁班案例题 Kernel 规则支持后评测报告 v0 directional

Status: v0 directional / shadow. This is not a production accuracy gate.

Gold source: `ground_truth_ledger`, not `blind_grade`.

Raw artifacts:

- Before JSON: `artifacts/luban_case_grading_three_arms/full_v0_directional/full_three_arms_20260601_183231.json`
- After JSON: `artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_185157.json`
- After per-sample markdown: `artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/full_three_arms_20260601_185157.md`
- Benchmark run: `tmp/benchmark/luban_case_grading_shadow_kernel_rule_support_final/benchmark_run_20260601_185528.json`

## 1. Executive Decision

Kernel rule support produced a material directional lift. Artifact-first remains better than baseline/RAG after the authority change.

Decision: **GO for continued structured scoring-point data investment; NO-GO for production runtime promotion; NO-GO for generic Nexus-like platform construction.**

## 2. Before / After Lift

| Metric | Before artifact-first | After artifact-first | Delta | Reading |
|---|---:|---:|---:|---|
| Mean abs score delta | 2.1338 | 1.5778 | -0.5560 | Better; 26.1% relative reduction. |
| Point recall | 0.6508 | 0.7487 | +0.0979 | Better. |
| Point precision | 0.7890 | 0.8888 | +0.0998 | Better; overmatch severity fell. |
| Term recall | 0.7611 | 0.8273 | +0.0662 | Better. |
| Term precision | 0.9000 | 0.9600 | +0.0600 | Better. |
| Hallucination rate | 0.0000 | 0.0000 | 0.0000 | Preserved zero hallucination after removing full-label fallback. |
| Token proxy | 730.5 | 684.5 | -46.0 | Better; narrower artifact context. |

After-run arm comparison:

| Arm | Mean abs score delta | Point recall | Point precision | Term recall | Term precision | Hallucination | Token proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 2.5928 | 0.4376 | 0.6150 | 0.4537 | 0.6500 | 0.7100 | 812.2 |
| rag | 2.5928 | 0.4376 | 0.6150 | 0.4537 | 0.6500 | 0.7100 | 1059.2 |
| artifact-first | 1.5778 | 0.7487 | 0.8888 | 0.8273 | 0.9600 | 0.0000 | 684.5 |

## 3. Targeted Gap Results

| Gap | Before count | After count | Before abs delta sum | After abs delta sum | Reading |
|---|---:|---:|---:|---:|---|
| `penalty_rule_unsupported` | 1 | 0 | 4.0000 | 0.0000 | Fixed. Q4-S4 now aligns with gold. |
| `term_form_normalization_gap` | 8 | 9 | 10.3511 | 7.6249 | Count did not improve, but severity improved. Remaining items are mostly list-rule / data extraction quality, not punctuation-only form gaps. |
| `compiled_term_overmatch` | 3 | 5 | 4.2250 | 1.8583 | Count worsened, severity improved. The severe Q10 A/B cross-match was fixed; remaining overmatches are smaller and require point-specific data review. |
| `keyword_context_false_positive` | 2 | 3 | 1.5000 | 4.0000 | Worse; intentionally not solved by this patch because it needs context semantics or human-reviewed rules. |
| `compiled_term_recall_gap` | 47 | 38 | 193.3023 | 144.2935 | Better as a side effect of cleaner artifacts, but still the main backlog. |

Penalty check:

| Case | Sample | Before pred/gold | After pred/gold | Result |
|---|---|---:|---:|---|
| Q4-1A434000-罚则 | S4 | 7.0 / 3.0 | 3.0 / 3.0 | `multi_answer_no_score` applied to P1/P2 only; P3 preserved. |

## 4. Interaction Between (b) Normalization and (c) Overmatch

They did not cancel each other out at the metric level: net score accuracy, recall, precision, term metrics, hallucination, and token proxy all improved.

However, they did conflict at the failure-mode level. Official-term normalization initially made full-label fallback match too much and raised hallucination. The final fix removed full-label fallback from artifact compilation and added narrow `answer_label` context for fill-blank items. The resulting system is stricter and more data-driven:

- More matching for official punctuation / bracket / slash variants.
- Less matching for overbroad terms such as `原则`.
- No full-label keyword fallback when no official term can be extracted.
- Fill-blank terms can be scoped to answer labels such as `A` / `B`.

## 5. Data Asset Status

Current reusable Nexus-like data assets are:

| Asset | Schema shape | Authority source | Current coverage |
|---|---|---|---|
| `grading_key.scoring_points` | `{criterion, keywords, score, source_point_id, source_fields, required_context?, answer_label?}` | v0 golden `gold_scoring_points`, anchored to official answer / textbook wording | 20 cases, 97 source scoring points, 178 compiled atomic scoring items, 86 source points with extractable terms, 19/20 cases with at least one compiled item. |
| Official term variants | Kernel normalizes punctuation, brackets, slash alternatives, and `或` variants; no synonym expansion | Official terms from textbook / official answer wording | Proven in tests for bracket and slash variants; remaining form gaps require better source term extraction. |
| `penalty_rules` | `{rule_id, type, trigger, zero_point_ids, source_field}` | Golden `penalty_rule` text reviewed in v0 SOP | 1 case currently compiled: Q4 `multi_answer_no_score`. |
| Fill-blank context | `answer_label` on scoring point, e.g. `A`, `B` | Official labels like `A 处填` | Applied to Q10-style fill blanks; prevents cross-match. |

Expansion path:

1. Keep these assets as versioned derived artifacts from the golden fixture / source compiler, not one-off runner state.
2. Extend extraction coverage for list-rule and calculation items without allowing full-label fallback.
3. Add reviewer queues for residual overmatch / false positive cases.
4. Only after v1 human IRR or PO-reviewed slices should runtime promotion be discussed.

## 6. Remaining Backlog

Data problems:

- `compiled_term_recall_gap`: still dominant. Needs better extraction for long rubrics, calculation process points, and list-rule official terms.
- Residual `term_form_normalization_gap`: current category includes list-rule scoring granularity and extraction artifacts, not only punctuation form.
- Some source labels contain scoring instructions mixed with official terms; extraction should keep removing non-answer terms like `每项1分`.

Kernel problems:

- `keyword_context_false_positive`: examples include Q2-S3 and Q4-S3/S5. Requires context-aware rule design or human-reviewed constraints; not solved this round.
- Some small overmatches remain after answer-label scoping, mainly due point-specific context missing.

Explicit non-actions:

- RAG still does not enter scoring authority.
- No runner-side score correction was added.
- No production runtime gate was claimed.
- No generic Nexus-like platform was built.

## 7. §0.3 Evolution Gate Reading

This result strengthens the §0.3 directional gate: structured scoring artifacts are worth continued investment.

It is strong enough to justify moving toward a v1 data-quality plan, but not strong enough to promote production grading. The next decision should be whether to start v1 human/PO-reviewed validation slices and artifact versioning, not whether to build a generic platform.
