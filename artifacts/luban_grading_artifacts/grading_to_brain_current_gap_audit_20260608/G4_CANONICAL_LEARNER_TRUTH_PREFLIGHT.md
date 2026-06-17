# G4 Canonical Learner Truth Preflight

- Gate: `G4_canonical_learner_truth_write`
- Verdict: `not_ready_teacher_final_required`
- Blocking reason: teacher-final live signoff is required before canonical learner truth write
- Scope: `read_only_pre_authorization_preflight`
- Execution mode: `read_only_no_write`
- Without authorization: `decision_package_only`
- Required authorization: `explicit_canonical_learner_truth_write_authorization`
- Promotion path: `teacher_final_plus_real_retest_only`

This artifact proves the gate state only. It does not write canonical learner truth.

## No-Write Invariants

- production_write_count: `0`
- canonical_truth_written: `False`
- remote_write_count: `0`
- published_registry_executed: `False`

## Preconditions

- truth_write_guard_present: `True`
- real_retest_valid_count: `16`
- dryrun_candidate_count: `16`
- teacher_final_live_count: `0`
- teacher_final_simulated_count: `3`
- requires_real_teacher_signoff_count: `3`
- m32_counted_improvement_count: `0`
- shadow_or_simulated_promotion_attempted: `False`
- pcp_unique_contract: `True`
- second_memory_authority: `False`
- second_personalization_authority: `False`

## Single Authority

- no_second_grading_truth: `True`
- no_second_learner_truth: `True`
- learner_truth_source: `Learning Evidence Ledger / Learner Model only`
- write_authority: `LearnerStateService writeback pipeline only`
- pcp_role: `read_only_feedback_context`

## Evidence

- `artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/learning_brain_truth_write_guard_m18d.json`
- `artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/canonical_write_dryrun_candidates_m18d.jsonl`
- `artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/real_retest_proofs_m18d.jsonl`
- `artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl`
- `artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/teacher_review_to_claim_bridge_m13e.jsonl`

## Stop Conditions

- teacher-final live signoff missing
- real retest proof missing or simulated
- shadow/candidate/simulated event attempts canonical mastery
- second learner memory or personalization authority appears
- production/canonical write occurs before authorization
