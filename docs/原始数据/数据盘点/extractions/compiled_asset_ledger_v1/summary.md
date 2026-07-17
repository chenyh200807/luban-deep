# Compiled Asset Ledger v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: compiled asset inventory only; not runtime install, not official score authority.
- Files indexed: **7,133**
- Total bytes: **1,152,347,822**
- Asset groups: **34**
- Manifest-like refs copied: **623**

## Asset Groups

| Group | Kind | Files | Bytes | Authority |
|---|---|---:|---:|---|
| `artifacts/[root_files]` | `artifact_auxiliary_or_report` | 69 | 3,259,651 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/assessment_flywheel` | `assessment_flywheel` | 2 | 5,764 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/assessment_testset` | `assessment_testset` | 9 | 1,428,036 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/authority_baseline` | `artifact_auxiliary_or_report` | 2 | 21,024 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/automation-runs` | `artifact_auxiliary_or_report` | 224 | 1,735,258 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/bi_reconciliation_20260612` | `artifact_auxiliary_or_report` | 6 | 57,340 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/billing_golive` | `artifact_auxiliary_or_report` | 3 | 36,350 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/cc_student_eval_p04` | `artifact_auxiliary_or_report` | 1 | 4 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/fix_test_log` | `artifact_auxiliary_or_report` | 4 | 16,363 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/knowledge_compiler` | `knowledge_compiler_workbench` | 189 | 50,729,003 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban-posters` | `artifact_auxiliary_or_report` | 16 | 14,547,779 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban-usage-infographic-v1` | `artifact_auxiliary_or_report` | 4 | 9,153,663 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_agentic_grading_harness` | `agentic_grading_harness` | 142 | 5,181,069 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_answer_layer_audit` | `artifact_auxiliary_or_report` | 17 | 57,489 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_case_family_assets` | `case_family_multimedia_assets` | 1,908 | 468,199,612 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_case_grading_three_arms` | `case_grading_ab_workbench` | 32 | 39,561,956 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_consensus_gold` | `consensus_gold_shadow_review` | 496 | 23,704,129 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_governed_gold` | `artifact_auxiliary_or_report` | 8 | 1,131,964 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_grading_artifacts` | `grading_compiler_shadow_workbench` | 3,327 | 367,181,176 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_human_validation_v1` | `artifact_auxiliary_or_report` | 21 | 991,428 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_knowql_nexus_three_arm_ab` | `artifact_auxiliary_or_report` | 17 | 3,649,726 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_no_human_v1_5` | `artifact_auxiliary_or_report` | 101 | 11,864,860 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/luban_typed_policy` | `artifact_auxiliary_or_report` | 5 | 282,668 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/onboarding_motion_qa_20260612` | `artifact_auxiliary_or_report` | 128 | 107,185,692 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/product-research` | `artifact_auxiliary_or_report` | 7 | 1,193,738 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/qa` | `artifact_auxiliary_or_report` | 278 | 14,946,974 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/qa_tmp` | `artifact_auxiliary_or_report` | 1 | 263 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/quality_gate` | `artifact_auxiliary_or_report` | 32 | 279,608 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/security` | `artifact_auxiliary_or_report` | 1 | 18,547 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/student_army_eval` | `artifact_auxiliary_or_report` | 4 | 44,799 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/student_army_tmp` | `artifact_auxiliary_or_report` | 1 | 219 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/tmp` | `artifact_auxiliary_or_report` | 18 | 504,475 | `artifact_workbench_or_candidate_inventory` |
| `artifacts/ui-prototypes` | `artifact_auxiliary_or_report` | 1 | 48,638 | `artifact_workbench_or_candidate_inventory` |
| `runtime_supply` | `runtime_supply_mixed_published_and_candidate` | 59 | 25,328,557 | `runtime_supply_inventory_mixed_publication_status` |

## Guardrails

- Source payloads remain in their original artifact/runtime directories; this ledger copies only indexes and small manifest-like snapshots.
- `artifacts/*` entries are workbench/candidate/shadow unless separately signed and published through runtime supply.
- `runtime_supply` contains mixed published/release-candidate assets; consumers must read each canonical pointer/status before use.
- No record in this ledger may write LearnerState, GBrain, production registry, or official score authority.
