# Grading-to-Brain Authorization Gates

- Master plan: `docs/plan/总控入口与当前作战图/2026-06-04-luban-grading-engine-master-control-plan.md`
- Scope: `read_only_authorization_decision_package`
- This package is read-only and executes no production, registry, learner-truth, remote, or DB write.

## Single Authority

- Grading truth source: signed artifacts + runtime adjudicator + validator
- Learner truth source: Learning Evidence Ledger + Learner Model
- PersonalizationContextPack remains read-only feedback context.

## Recommended Order

- `G1_limited_production_default`
- `G6_real_wechat_package_page_automation`
- `G3_published_registry`
- `G4_canonical_learner_truth_write`
- `G2_broad_production_default`
- `G5_remote_or_db_write`

## Gate Table

| Gate | Current State | Recommended Next | Required Authorization | Without Authorization | Evidence |
|---|---|---:|---|---|---|
| G1_limited_production_default | candidate_ready_not_executed | True | explicit_user_authorization_for_limited_default | `decision_package_only` | `artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/go_no_go_m19c.json`<br>`artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json`<br>`artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/rollback_readiness_drill_m19d.json` |
| G2_broad_production_default | not_recommended | False | separate_broad_default_authorization_after_limited_soak | `decision_package_only` | `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/soak_metrics_m19d.json`<br>`artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/m19c_m19d_evidence_ledger_m19e.json`<br>`docs/plan/总控入口与当前作战图/2026-06-04-luban-grading-engine-master-control-plan.md` |
| G3_published_registry | staged_candidate_only | False | explicit_registry_publish_authorization | `decision_package_only` | `artifacts/luban_grading_artifacts/llm_artifact_compiler_continuous_factory_m20_20260604/deterministic_signer_report_m20.json`<br>`artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_signature_m202.json`<br>`artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/release_decision_input_m202.json` |
| G4_canonical_learner_truth_write | dryrun_candidate_only | False | explicit_canonical_learner_truth_write_authorization | `decision_package_only` | `artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/learning_brain_truth_write_guard_m18d.json`<br>`artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/canonical_write_dryrun_candidates_m18d.jsonl`<br>`artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl`<br>`tests/services/construction_grading/test_teacher_review_writeback.py` |
| G5_remote_or_db_write | not_executed | False | explicit_remote_or_db_write_authorization | `decision_package_only` | `AGENTS.md`<br>`artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/rollback_commands_m19e.md`<br>`artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_r_20260605/m19c_m19d_readiness_rollup_m19e_r.json` |
| G6_real_wechat_package_page_automation | verification_required | False | devtools_or_manual_wechat_qa_window | `decision_package_only` | `AGENTS.md`<br>`scripts/run_wechat_learning_brain_devtools_e2e.py`<br>`tests/services/member_console/test_home_dashboard_learning_projection.py` |

## Non-Negotiables

- Do not promote shadow, candidate, simulated, or test-runner output to canonical mastery.
- Do not publish registry versions without signed hash/version evidence and rollback pointer.
- Do not write remote files outside `/root/deeptutor`.
- Do not count `/wechat-harness` as true `packageDeeptutor` evidence.
