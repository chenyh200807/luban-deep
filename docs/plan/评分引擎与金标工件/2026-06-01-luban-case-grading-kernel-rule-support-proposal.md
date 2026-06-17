# 鲁班案例题评分 Kernel 规则支持提案

Status: Implemented in v0 directional / shadow on 2026-06-01. Not a production runtime gate.

Related evidence:

- Before full v0 directional report: `artifacts/luban_case_grading_three_arms/full_v0_directional/luban_case_grading_three_arm_full_report_20260601.md`
- After kernel-rule support report: `artifacts/luban_case_grading_three_arms/kernel_rule_support_20260601/kernel_rule_support_lift_report_20260601.md`
- Current authority: `deeptutor/services/construction_grading/case_kernel.py`
- Golden fixture: `deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json`

## 0. Decision

Approved by PO and implemented as a minimal authority change to `CaseGradingSkillKernel`.

This proposal does **not** introduce a second grader, RAG-scoring path, LLM judge, or runner-side score correction. The only allowed implementation location is the existing scoring authority: `deeptutor/services/construction_grading/case_kernel.py`.

## 1. Evidence

The 20-question / 100-sample v0 directional run showed artifact-first is better than baseline/RAG, but remaining errors concentrate in rule expressiveness:

| Category | Count | Meaning |
| --- | ---: | --- |
| `penalty_rule_unsupported` | 1 | Global penalty such as "多答不得分" cannot be expressed by the current kernel. |
| `term_form_normalization_gap` | 8 | Official term is present, but punctuation / parentheses / list punctuation form prevents raw substring match. |
| `keyword_context_false_positive` | 2 | Keyword appears in wrong context; current keyword kernel over-awards. |
| `compiled_term_overmatch` | 3 | Compiled terms were too broad or lacked point context, including fill-blank A/B cross-match. |

This implementation covers `penalty_rule`, official-term form normalization, and narrow compiled-term overmatch fixes. It deliberately does not solve broad semantic context false positives.

## 2. Scope

### 2.1 In Scope

1. `penalty_rule`: support explicit, structured global penalty rules, starting with "多答不得分" cases where a fixed set of point ids must be zeroed if the rule triggers.
2. Official-term normalization: match only punctuation/parentheses/form variants of the same official term.
3. Compiled-term overmatch control: reject overbroad extracted terms, remove full-label fallback when no official term exists, and preserve fill-blank `answer_label` context for `A 处填` / `B 处填` style items.

### 2.2 Out of Scope

- Synonym expansion.
- Near-meaning matching.
- LLM judging inside the kernel.
- RAG evidence directly changing scores.
- New production tables.
- New grading service.
- Runner-side score correction.
- Generic Nexus-like platform work.

## 3. Minimal Diff Boundary

Primary file:

- `deeptutor/services/construction_grading/case_kernel.py`

Likely changes:

1. Add a private normalization helper:

```python
def _normalize_official_term(value: Any) -> str:
    return re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’]+", "", str(value or ""))
```

2. Replace raw keyword check:

```python
matched = [keyword for keyword in keywords if keyword and keyword in answer_text]
```

with official-term normalized check:

```python
answer_norm = _normalize_official_term(answer_text)
matched = [
    keyword
    for keyword in keywords
    if keyword and _normalize_official_term(keyword) in answer_norm
]
```

3. Preserve exact keyword list in output. `evidence_text` may still show original keyword text.

4. Add a narrow `penalty_rule` parser for `grading_key` only. Proposed accepted shape:

```python
grading_key = {
    "scoring_points": [...],
    "penalty_rules": [
        {
            "rule_id": "multi_answer_no_score",
            "type": "multi_answer_no_score",
            "trigger": {"max_answered_items": 2, "pattern": "不妥"},
            "zero_point_ids": ["P1", "P2"],
        }
    ],
}
```

5. To make penalty zeroing possible, `_grading_key_rubric_specs()` should preserve `point_id` from each scoring point if provided. Current `CaseRubricItemResult` has no point_id field, so the lowest-risk implementation is to encode the point id in `criterion` exactly as the current runner does (`P1::见证人员`) and parse the prefix internally. A schema change to `CaseRubricItemResult` is not recommended for this first patch.

6. Actual implemented additional artifact fields:

```python
{
    "criterion": "P1::限制",
    "keywords": ["限制"],
    "score": 1.0,
    "source_point_id": "P1",
    "source_fields": ["golden.gold_scoring_points"],
    "answer_label": "A",           # optional; fill-blank context
    "required_context": "分项工程",  # optional; scoped list-rule context
}
```

7. Actual implemented `penalty_rules` shape:

```python
{
    "rule_id": "multi_answer_no_score",
    "type": "multi_answer_no_score",
    "trigger": {"max_answered_items": 2, "pattern": "不妥"},
    "zero_point_ids": ["P1", "P2"],
    "source_field": "golden.penalty_rule",
}
```

## 4. Tests Required

Add or extend:

- `tests/services/construction_grading/test_case_grading_kernel.py`

Required cases:

1. Official punctuation normalization:

```python
grading_key = {"scoring_points": [{"criterion": "P1::分期(分批)实施工程的开、竣工日期及工期一览表", "keywords": ["分期(分批)实施工程的开、竣工日期及工期一览表"], "score": 1}]}
answer = "分期分批实施工程的开、竣工日期及工期一览表"
```

Expected: full score.

2. No synonym expansion:

```python
grading_key = {"scoring_points": [{"criterion": "P1::诚实信用", "keywords": ["诚实信用"], "score": 1}]}
answer = "诚信经营"
```

Expected: miss.

3. Penalty rule:

Question similar to Q4-S4 with four "不妥" answers and `zero_point_ids=["P1", "P2"]`.

Expected: P1/P2 awarded scores zero; unrelated P3 remains scored.

4. Regression:

Existing tests in `tests/services/construction_grading/test_case_grading_kernel.py` must remain green.

5. Overmatch controls:

- overbroad term `原则` does not score by itself;
- full-label fallback is not emitted when official terms cannot be extracted;
- fill-blank answer labels prevent A/B cross-match.

## 5. Risks

- Over-normalization could accidentally allow near-synonyms. Mitigation: normalization removes only punctuation/space/brackets, not Chinese characters.
- Penalty parsing could become a hidden second policy language. Mitigation: support only one explicit typed rule in this patch; reject free-text penalty interpretation.
- Encoding point ids in `criterion` is not ideal. Mitigation: it is already used by the route-B runner and avoids schema churn; revisit only if more penalty types require point-level metadata.
- `answer_label` / `required_context` are deliberately narrow structured constraints, not a second grader. They must not grow into a free-form policy language.

## 6. Rollback

Rollback is simple:

- Revert changes in `case_kernel.py`.
- Revert route-B runner compiler changes in `scripts/poc_luban_case_grading_three_arms.py`.
- Revert the added tests.
- The route-B runner remains valid and will continue reporting `penalty_rule_unsupported` / `term_form_normalization_gap`.

## 7. Recommendation

Implemented result: mean abs score delta improved from 2.1338 to 1.5778; point precision improved from 0.7890 to 0.8888; hallucination stayed 0.0000. Continue structured scoring-point data investment, but do not approve RAG direct scoring, synonym expansion, production promotion, or generic Nexus-like platform work from this result alone.
