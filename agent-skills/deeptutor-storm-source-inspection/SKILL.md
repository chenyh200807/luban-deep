---
name: deeptutor-storm-source-inspection
description: "Use this for STORM/Co-STORM-like source inspection before DeepTutor knowledge compilation, OKF-like rubric work, data inventory, research synthesis, ADRs, or plan decisions. It turns multi-perspective research into candidate/review-only inspection findings while preserving source spans, provenance, authority boundaries, and preventing runtime, scoring, RAG, citation, or learner-truth authority drift."
---

# DeepTutor STORM Source Inspection

Use this skill to absorb STORM as a DeepTutor workflow, not as a product
runtime system. The output is an inspection report and work orders; it is never
runtime supply, official score authority, answer key, learner truth, or a new
RAG source.

## Start Frame

Before running the workflow, write or keep internally clear:

```text
one business fact:
one authority:
target artifact or decision:
source corpus / source spans:
current authority owner:
candidate output location:
runtime boundary:
verification target:
```

If the authority owner is unclear, stop and use `deeptutor-authority-debugging`
first.

## Hard Boundaries

- STORM output is `candidate_review`, never `truth`.
- Multi-perspective consensus is not evidence. It only creates a hypothesis or
  work order.
- Every factual claim must point to a source span, evidence bundle, or explicit
  `verification_needed`.
- Do not write `runtime_supply`, LearnerState, GBrain, questions bank,
  published registry, canonical truth, official score, or answer key.
- Do not add a STORM RAG provider, STORM chat route, STORM memory, STORM graph,
  STORM scoring layer, or TutorBot runtime persona committee.
- Runtime use requires a separate signed promotion gate and the existing
  consumer authority. This skill does not grant that authorization.

## Workflow

1. **Multi-perspective questions**
   - Use only task-relevant roles. For rubric/scoring work, prefer:
     strict grader, equivalence-expression reviewer, student-error reviewer,
     source/provenance auditor, and retention/economics reviewer.
   - For architecture/product work, use practitioner, academic, skeptic,
     economist, and historian.
   - Each role produces questions and suspected blind spots, not final truth.
2. **Source-grounded claim cards**
   - Convert each useful claim into a card:
     `claim`, `perspective`, `source_ref`, `source_span`, `confidence`,
     `authority_owner`, and `verification_needed`.
   - Claims without source support stay review-only and cannot enter compiler
     output as facts.
3. **Contradiction map**
   - List direct conflicts, shared assumptions, missing evidence, and the one
     question that would resolve the largest uncertainty.
   - Conflicts create `work_order` items. They do not resolve themselves by
     majority vote.
4. **Synthesis**
   - Produce a short brief with ranked findings, weakest link, hidden
     connection, and recommended next action.
   - Include which authority must accept, reject, or defer each finding.
5. **Peer review**
   - Check for source bias, fact misassociation, prompt-only consensus,
     overrepresented perspective, missing stakeholder, and runtime leakage.

## Output Contract

Allowed output:

```text
inspection_findings.md
claim_cards.jsonl
contradiction_map.json
review_work_orders.jsonl
peer_review_ledger.md
```

If writing files, place reusable protocol/ADR material under `docs/plan/` and
specific data-inspection reports under `docs/原始数据/数据盘点/` with index entries.
Do not place workflow rules inside product runtime skill directories.

Each finding should include:

```text
id:
authority_status: candidate_review
runtime_allowed: false
official_score_allowed: false
learner_truth_write_allowed: false
canonical_write_allowed: false
type: source_gap | rubric_ambiguity | provenance_gap | over_credit_risk |
      under_credit_risk | retrieval_bias | product_hypothesis |
      authority_leakage | verification_needed
severity:
source_ref:
source_span:
affected_authority:
recommended_owner:
allowed_next_step:
forbidden_next_step:
```

## Eval Gates

For scoring or learning claims, do not call the work successful unless the
relevant gates are defined:

- `authority_gate`: candidate/review-only unless a signed release gate says
  otherwise.
- `source_gate`: unsupported claims become HOLD / `verification_needed`.
- `rubric_gate`: accepted expressions, counterexamples, and boundary samples
  are explicit.
- `irr_gate`: human inter-rater agreement is measured before production
  scoring claims.
- `anti_over_credit_gate`: high-severity false positives are zero-tolerance.
- `learning_gate`: prove score sentence production, D1/D7 retest, or
  confident-wrong reduction before product claims.
- `retention_economics_gate`: pre-register D1/D7, sample size, cost per
  attempt, review minutes, and appeal upheld rate.
- `appeal_gate`: point-level disagreement and repair feedback path exists
  before claiming trusted grading.

## Stop Conditions

Stop and report a blocker if:

- a STORM artifact is about to be consumed by runtime, RAG, grader, TutorBot,
  LearnerState, GBrain, or published registry;
- an output loses source spans, provenance, confidence, or unresolved-question
  fields;
- a prompt consensus is being treated as source evidence;
- a reviewer proposes a new wrapper/router/fallback instead of restoring the
  existing authority path;
- success is defined as "better report" without a deterministic replay,
  baseline, human adjudication, or product metric.

## Verification

For doc/skill changes, run:

```bash
python agent-skills/scripts/validate_agent_skills.py
git diff --check -- AGENTS.md agent-skills docs/plan
python scripts/check_contract_guard.py AGENTS.md agent-skills docs/plan
```

For OKF-like rubric work, also run the focused generator/tests if touched:

```bash
python3 docs/原始数据/数据盘点/scripts/build_okf_rubric_pilot.py --generated-at 2026-06-19T00:00:00+08:00
python3 -m pytest tests/scripts/test_okf_rubric_pilot.py -q
```
