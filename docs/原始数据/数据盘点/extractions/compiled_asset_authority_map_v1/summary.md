# Compiled Asset Authority Map v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: inventory and consumer policy only; not runtime install, not official score authority.
- Asset groups classified: **34**
- Runtime pointer / manifest rows: **16**
- Published runtime pointers with hash gate: **4**
- Candidate / blocked runtime pointers: **12**

## Group Authority

| Group | Class | Runtime Direct Read | Required Gate |
|---|---|---:|---|
| `artifacts/[root_files]` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/assessment_flywheel` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/assessment_testset` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/authority_baseline` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/automation-runs` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/bi_reconciliation_20260612` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/billing_golive` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/cc_student_eval_p04` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/fix_test_log` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/knowledge_compiler` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban-posters` | `multimedia_or_product_candidate_read_only` | false | visual QA, source provenance, release packaging |
| `artifacts/luban-usage-infographic-v1` | `multimedia_or_product_candidate_read_only` | false | visual QA, source provenance, release packaging |
| `artifacts/luban_agentic_grading_harness` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban_answer_layer_audit` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/luban_case_family_assets` | `multimedia_or_product_candidate_read_only` | false | visual QA, source provenance, release packaging |
| `artifacts/luban_case_grading_three_arms` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban_consensus_gold` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/luban_governed_gold` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/luban_grading_artifacts` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban_human_validation_v1` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/luban_knowql_nexus_three_arm_ab` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban_no_human_v1_5` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/luban_typed_policy` | `candidate_compiler_workbench_read_only` | false | schema validation, source hash, adversarial review, signed release, rollback pointer |
| `artifacts/onboarding_motion_qa_20260612` | `multimedia_or_product_candidate_read_only` | false | visual QA, source provenance, release packaging |
| `artifacts/product-research` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/qa` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/qa_tmp` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/quality_gate` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/security` | `review_or_audit_evidence_read_only` | false | cannot become runtime supply without source validation and release signing |
| `artifacts/student_army_eval` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/student_army_tmp` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/tmp` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `artifacts/ui-prototypes` | `auxiliary_artifact_or_report_read_only` | false | manual owner review before any promotion |
| `runtime_supply` | `runtime_supply_pointer_gated` | false | per canonical pointer: published/status/hash/schema/consumer gate |

## Runtime Pointer Gate

| Pointer | Published | Status | Runtime Read | Hash Gate |
|---|---:|---|---:|---:|
| `deeptutor/services/construction_grading/runtime_supply/v1_limited_default/runtime_supply_manifest.json` | None | `candidate_manifest_no_publish_flag` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v2_objective_real_candidate/runtime_supply_v2_manifest.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v2_objective_release_candidate/runtime_supply_v2_manifest.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v3_objective_records_released_m31/canonical_pointer_m31.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_canonical_knowledge_manifest/canonical_knowledge_manifest.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_pgo/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_kb_v5_chunks_full/canonical_pointer.json` | True | `published_runtime_supply_hash_gated` | true | true |
| `deeptutor/services/construction_grading/runtime_supply/v_lecture_answer_skill_pack_all8/manifest.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_lecture_teaching_cards/canonical_pointer.json` | True | `published_runtime_supply_hash_gated` | true | true |
| `deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_slice_case_rubric/canonical_pointer.json` | True | `published_runtime_supply_hash_gated` | true | true |
| `deeptutor/services/construction_grading/runtime_supply/v_standard_clauses/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_textbook_knowledge_full/canonical_pointer.json` | False | `release_candidate_not_runtime_default` | false | true |
| `deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/canonical_pointer.json` | True | `published_runtime_supply_hash_gated` | true | true |

## Guardrails

- `artifacts/*` stays candidate/workbench/review evidence unless a downstream signed packet promotes it.
- `runtime_supply` is not consumed as a directory; consumers must read a published pointer with content hash and schema gate.
- Published pointer still does not mean official scoring or learner-truth write authority.
- Candidate artifacts and release artifacts must remain separate namespaces.
