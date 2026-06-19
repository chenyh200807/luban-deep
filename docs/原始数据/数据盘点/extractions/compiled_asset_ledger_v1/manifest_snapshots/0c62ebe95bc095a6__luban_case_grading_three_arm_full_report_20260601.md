# 鲁班案例题三路批改全量评测报告 v0 directional

Status: v0 directional / shadow. This report is not a production accuracy gate.

Gold source: `ground_truth_ledger`, not `blind_grade`. The ledger is the v0 AI-anchored construction intent recorded when each synthetic answer was created. Therefore this run measures grader-vs-construction-intent consistency, not human IRR.

Raw artifacts:

- JSON rows: `artifacts/luban_case_grading_three_arms/full_v0_directional/full_three_arms_20260601_183231.json`
- Per-sample markdown: `artifacts/luban_case_grading_three_arms/full_v0_directional/full_three_arms_20260601_183231.md`
- Benchmark run: `tmp/benchmark/luban_case_grading_shadow_verify/benchmark_run_20260601_183235.json`

## 1. Executive Result

Artifact-first remains directionally better than baseline and current RAG across the full 20-question / 100-sample v0 fixture.

| Arm | Samples | Mean abs score delta | Point recall | Point precision | Term recall | Term precision | Hallucination | Token proxy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 100 | 2.6305 | 0.4059 | 0.5450 | 0.4630 | 0.6200 | 0.6900 | 812.2 |
| rag | 100 | 2.6305 | 0.4059 | 0.5450 | 0.4630 | 0.6200 | 0.6900 | 1059.2 |
| artifact-first | 100 | 2.1338 | 0.6508 | 0.7890 | 0.7611 | 0.9000 | 0.0000 | 730.5 |

Directional go/no-go: **GO for continued structured scoring-point investment; NO-GO for production runtime promotion without kernel-rule work and v1 human IRR.**

## 2. RAG Finding

RAG evidence is passed into `CaseGradingSkillKernel.grade()` as evidence refs, but it does not enter the scoring decision. Full-run trace:

- `evidence_in_result=true`
- `score_changed_samples=0`
- baseline and RAG metrics are identical
- RAG token proxy is higher than baseline

Interpretation: this is not evidence that "RAG connected but ineffective." It is evidence that current RAG is trace/context only for this grading path. Letting RAG directly alter scores would create a second scoring authority. The acceptable future path is: RAG retrieves sources -> compiler/reviewer creates rubric candidate -> structured validation -> enters `grading_key.scoring_points`.

## 3. Artifact-First Weakness Quantification

Artifact-first has 61 non-zero score-delta samples:

| Category | Count | Meaning |
|---|---:|---|
| compiled_term_recall_gap | 47 | Artifact compiler did not produce enough kernel-matchable terms for gold-positive points. |
| term_form_normalization_gap | 8 | Official term exists but punctuation/parentheses/form prevents raw substring match. |
| compiled_term_overmatch | 3 | Compiled terms are too broad or point granularity overmatches. |
| keyword_context_false_positive | 2 | Keyword appears, but answer context is wrong/vague; current kernel cannot judge context. |
| penalty_rule_unsupported | 1 | Gold penalty triggered, but kernel lacks global penalty-rule execution. |

Top over-scored samples:

| Case | Sample | Delta | Category | Note |
|---|---|---:|---|---|
| Q4-1A434000-罚则 | S4 | +4.0 | penalty_rule_unsupported | 多答不得分清零 P1/P2, kernel still awards raw keyword hits. |
| Q10-1A422000 | S5 | +3.0 | compiled_term_overmatch | Compiled terms overmatch a wrong answer. |
| Q19-1A432000 | S5 | +1.2 | compiled_term_overmatch | Point granularity / term breadth issue. |
| Q4-1A434000-罚则 | S5 | +1.0 | keyword_context_false_positive | Keyword appears in wrong context. |
| Q4-1A434000-罚则 | S3 | +0.5 | keyword_context_false_positive | Vague answer contains a term fragment. |

Top under-scored samples:

| Case | Sample | Delta | Category | Note |
|---|---|---:|---|---|
| Q5-1A432000 | S1 | -16.6667 | compiled_term_recall_gap | Artifact terms insufficient for high-score case. |
| Q5-1A432000 | S4 | -11.6667 | compiled_term_recall_gap | Same source gap. |
| Q3-1A433000 | S1 | -10.2857 | compiled_term_recall_gap | High-score long rubric not fully compiled into kernel terms. |
| Q5-1A432000 | S2 | -10.5 | compiled_term_recall_gap | Same source gap. |
| Q5-1A432000 | S5 | -9.0 | compiled_term_recall_gap | Same source gap. |

## 4. Group Summary

| Group | Arm | Samples | Mean abs score delta | Term recall | Token proxy |
|---|---|---:|---:|---:|---:|
| calculation | baseline | 50 | 3.1659 | 0.4107 | 839.4 |
| calculation | rag | 50 | 3.1659 | 0.4107 | 1097.1 |
| calculation | artifact-first | 50 | 2.8714 | 0.7613 | 746.9 |
| list_rule | baseline | 80 | 2.9144 | 0.4221 | 835.125 |
| list_rule | rag | 80 | 2.9144 | 0.4221 | 1093.8125 |
| list_rule | artifact-first | 80 | 2.2685 | 0.7261 | 787.9375 |
| penalty_rule | baseline | 5 | 2.2 | 0.4 | 721.0 |
| penalty_rule | rag | 5 | 2.2 | 0.4 | 951.0 |
| penalty_rule | artifact-first | 5 | 1.1 | 1.0 | 617.0 |
| specification | baseline | 95 | 2.6648 | 0.4348 | 817.6316 |
| specification | rag | 95 | 2.6648 | 0.4348 | 1065.1579 |
| specification | artifact-first | 95 | 2.0682 | 0.7485 | 726.2632 |

## 5. §0.3 Evolution Gate Reading

The full run satisfies the first directional part of v2.2 §0.3: structured scoring data materially improves grading quality versus baseline/RAG in this code path.

What it proves:

- `grading_key.scoring_points` is the right near-term authority surface.
- Artifact-first reduces hallucination to zero in this v0 fixture.
- Artifact-first reduces token proxy versus both RAG and baseline.
- RAG should not be promoted as a direct grading authority.

What it does not prove:

- It does not prove production readiness.
- It does not prove human-level accuracy.
- It does not justify a generic Nexus-like platform yet.

Next gate:

1. Improve artifact compiler quality for high-score long rubrics.
2. Propose, review, and separately approve minimal kernel support for `penalty_rule` and official-term normalization.
3. Produce v1 human IRR or PO-reviewed validation slices before runtime promotion.

## 6. Final Directional Decision

Decision: **continue Nexus-like data foundation work, do not build platform yet, do not let RAG bypass grading authority, and do not promote to production runtime before kernel rule work + v1 validation.**
