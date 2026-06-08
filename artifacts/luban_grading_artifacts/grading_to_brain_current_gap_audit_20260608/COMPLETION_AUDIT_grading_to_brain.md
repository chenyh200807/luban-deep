# Grading-to-Brain Completion Audit

- Master plan: `docs/plan/2026-06-04-luban-grading-engine-master-control-plan.md`
- Scope: `explicit_objective_completion_audit`
- This audit maps the objective's seven explicit loop requirements to evidence.

## Single Authority

- Grading truth: grading truth/artifact authority
- Learner truth: Learning Evidence Ledger / Learner Model
- No second mastery/profile/recommendation truth is introduced by this audit.

## Requirement Matrix

| ID | Requirement | Status | Authority | Evidence |
|---|---|---:|---|---|
| R1 | runtime_grading_point_level_result | done | grading truth/artifact authority | `tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py`<br>`tests/services/construction_grading/test_m32_grading_event_learning_evidence.py`<br>`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/grading_packet_schema_m17a.json`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/grading_event_ledger_m32.jsonl` |
| R2 | grading_result_to_standard_learning_evidence_event | done | Learning Evidence Ledger | `tests/services/construction_grading/test_learning_evidence_payload.py`<br>`tests/services/construction_grading/test_m32_grading_event_learning_evidence.py`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/learning_evidence_ledger_m32.jsonl`<br>`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/learning_brain_event_drafts_m17a.jsonl` |
| R3 | learning_evidence_to_learner_claim_profile | done | Learner Model synthesis | `tests/services/learner_state/test_m32_waterproof_learning_synthesis.py`<br>`tests/services/construction_grading/test_learning_brain_synthesis.py`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/learner_claim_projection_m32.jsonl`<br>`artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/claim_gate_decision_matrix_m13e.json` |
| R4 | pcp_feedback_to_tone_diagnosis_next_action_retest | done | PersonalizationContextPack read model | `tests/services/learner_state/test_personalization_context.py`<br>`tests/services/learner_state/test_m32_waterproof_personalization_context.py`<br>`tests/services/learner_state/test_m32_waterproof_next_best_action.py`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/personalization_context_pack_m32.json`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/next_best_action_m32.json` |
| R5 | teacher_final_override_reject_confirm_promotion_arm | done | teacher-final review writeback | `tests/services/construction_grading/test_teacher_review_writeback.py`<br>`tests/api/test_learning_brain_teacher_review_writeback.py`<br>`artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/teacher_review_to_claim_bridge_m13e.jsonl`<br>`artifacts/luban_grading_artifacts/teacher_review_ops_hardening_m13d_20260604/teacher_action_dryrun_m13d.jsonl` |
| R6 | real_retest_improvement_updates_profile | authorization_gated | real retest proof plus learner claim gate | `tests/scripts/test_luban_learning_brain_real_retest_canonical_gate_m18d.py`<br>`tests/services/learner_state/test_m32_waterproof_retest_outcome.py`<br>`artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/real_retest_proofs_m18d.jsonl`<br>`artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/canonical_write_dryrun_candidates_m18d.jsonl`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl` |
| R7 | learning_surfaces_use_same_learning_brain_authority | done | Learning Brain read model | `tests/services/member_console/test_home_dashboard_learning_projection.py`<br>`tests/services/learner_state/test_scoring_point_map_read_model.py`<br>`tests/services/learner_state/test_learning_report_read_model.py`<br>`deeptutor/services/learner_state/learning_report_read_model.py`<br>`deeptutor/services/learner_state/scoring_point_map_read_model.py`<br>`deeptutor/services/taxonomy/textbook_directory.py` |

## Remaining Gate

R6 remains `authorization_gated`: real retest proof and dry-run promotion evidence exist, but production canonical learner-truth write still requires explicit authorization.
