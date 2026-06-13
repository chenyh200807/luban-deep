# Grading-to-Brain Current Gap Audit

- Master plan: `docs/plan/总控入口与当前作战图/2026-06-04-luban-grading-engine-master-control-plan.md`
- Scope: `read_only_current_gap_audit`
- This audit is read-only: it does not write production state, DB rows, or canonical mastery.

## Single Authority

- Grading truth: signed grading artifacts + runtime packet builder + LLM adjudicator + deterministic validator/gate
- Learner truth: learning evidence ledger + teacher-final/real-retest promotion + learner model synthesis + PersonalizationContextPack
- Shadow/candidate/simulated outputs are evidence candidates only, never canonical mastery.

## Scenario Matrix

| ID | Scenario | Status | Evidence |
|---|---|---:|---|
| S1 | first_case_answer | done | `tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py`<br>`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/grading_packet_schema_m17a.json`<br>`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/learning_brain_event_drafts_m17a.jsonl` |
| S2 | near_synonym_exact_required | done | `tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py`<br>`tests/scripts/test_luban_v0_vs_v1_ab_benchmark_m24.py`<br>`artifacts/luban_grading_artifacts/v0_vs_v1_ab_benchmark_m24_20260605/v0_vs_v1_quality_matrix.json` |
| S3 | calculation_question | done | `tests/scripts/test_luban_calculation_validator_poc.py`<br>`tests/scripts/test_luban_non_textbook_rubric_authority_factory_m10.py`<br>`deeptutor/services/construction_grading/runtime_supply/v1_limited_default/machine_checkable_case_specs_m10.jsonl` |
| S4 | list_rule | done | `tests/scripts/test_luban_485_list_rule_policy.py`<br>`deeptutor/services/construction_grading/runtime_supply/v1_limited_default/list_rule_structured_specs_m10.jsonl`<br>`tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py` |
| S5 | question_stem_fact | done | `tests/scripts/test_luban_full_case_stem_source_acquisition_m14b.py`<br>`tests/services/construction_grading/test_full_knowledge_compiler_m30.py`<br>`artifacts/luban_grading_artifacts/full_knowledge_compiler_release_candidate_m30_20260606/source_context_release_candidate_m30.json` |
| S6 | external_norm | partial | `tests/scripts/test_luban_external_standard_source_rescue_m13c.py`<br>`deeptutor/services/construction_grading/runtime_supply/v1_limited_default/external_source_work_orders_m10.jsonl`<br>`artifacts/luban_grading_artifacts/full_knowledge_compiler_release_candidate_m30_20260606/raw_evidence_inventory_m30.json` |
| S7 | high_risk_review_queue | done | `tests/services/construction_grading/test_teacher_review_writeback.py`<br>`artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/runtime_safety_report_m17a.json`<br>`artifacts/luban_grading_artifacts/teacher_review_ops_hardening_m13d_20260604/review_queue_consolidated_m13d.jsonl` |
| S8 | teacher_review | done | `tests/services/construction_grading/test_teacher_review_writeback.py`<br>`tests/api/test_learning_brain_teacher_review_writeback.py`<br>`artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/teacher_review_to_claim_bridge_m13e.jsonl` |
| S9 | student_retest | done | `tests/scripts/test_luban_learning_brain_real_retest_canonical_gate_m18d.py`<br>`tests/scripts/test_luban_m32_grading_to_brain_waterproof_slice.py`<br>`artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/real_retest_proofs_m18d.jsonl`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl` |
| S10 | provider_fallback | done | `tests/scripts/test_luban_runtime_llm_ai_council_scaleout_m17b_m18.py`<br>`tests/scripts/test_luban_rag_baseline_and_fallback_closure_m22r.py`<br>`artifacts/luban_grading_artifacts/runtime_llm_ai_council_scaleout_m17b_m18_20260604/qwen_fallback_drill_results.jsonl`<br>`artifacts/luban_grading_artifacts/rag_vs_luban_v1_benchmark_closure_m22r_20260605/qwen_fallback_results_m22r.jsonl` |
| S11 | artifact_version_update | partial | `tests/scripts/test_luban_llm_artifact_compiler_continuous_factory_m20.py`<br>`tests/scripts/test_luban_delta_to_registry_candidate_staging_m202.py`<br>`artifacts/luban_grading_artifacts/llm_artifact_compiler_continuous_factory_m20_20260604/deterministic_signer_report_m20.json`<br>`artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_candidate_m202.json` |
| S12 | rollback | done | `tests/scripts/test_luban_limited_default_flip_m19c.py`<br>`tests/scripts/test_luban_limited_default_soak_monitoring_m19d.py`<br>`artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/rollback_drill_transcript_m19c.md`<br>`artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/rollback_readiness_drill_m19d.json` |

## Quality Gates

| Gate | Value |
|---|---:|
| fp | 0 |
| bad_certified | 0 |
| source_mismatch | 0 |
| legacy_equal | 1.0 |
| production_write | 0 |

## Remaining Authorization Gates

| Gate | State |
|---|---|
| production_default | `gated_authorization_required` |
| canonical_learner_truth_write | `gated_authorization_required` |
| published_registry | `gated_authorization_required` |
| remote_or_db_write | `gated_authorization_required` |
| real_wechat_package_page_automation | `not_touched_by_this_read_only_audit` |

## Verdict

The Grading-to-Brain implementation has evidence for all S1-S12 acceptance surfaces, with S6 and S11 still marked partial because external norm publication and published registry promotion remain authorization-gated. This artifact is a decision package, not a production promotion.
