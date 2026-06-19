# G3 Published Registry Preflight

- Gate: `G3_published_registry`
- Verdict: `ready_for_user_authorization`
- Scope: `read_only_pre_authorization_preflight`
- Execution mode: `read_only_no_publish`
- Without authorization: `decision_package_only`
- Required authorization: `explicit_registry_publish_authorization`
- Promotion path: `candidate_to_signed_to_published_registry`

This artifact proves staged publish readiness only. It does not publish a registry.

## Artifact Layers

- candidate: `staged_registry_candidate`
- signed_release: `staged_release_candidate`
- published_registry: `not_published`

## No-Write Invariants

- production_write_count: `0`
- canonical_truth_written: `False`
- remote_write_count: `0`
- published_registry_executed: `False`

## Preconditions

- deterministic_signer_pass: `True`
- staged_candidate_generated: `True`
- staged_signature_signed: `True`
- execute_release_decision: `False`
- published_registry_emitted: `False`
- candidate_hash_consistent: `True`
- delta_hash_consistent: `True`
- candidate_entries_count: `69`
- candidate_entries_published_count: `0`
- deterministic_validation_all_pass: `True`
- runtime_default_changed: `False`

## Single Authority

- no_second_grading_truth: `True`
- no_second_learner_truth: `True`
- registry_truth_source: `signed release artifact plus explicit publish gate only`
- runtime_consumption: `manifest/hash/pointer only; never scan artifacts`

## Evidence

- `artifacts/luban_grading_artifacts/llm_artifact_compiler_continuous_factory_m20_20260604/deterministic_signer_report_m20.json`
- `artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_signature_m202.json`
- `artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/release_decision_input_m202.json`
- `artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_candidate_m202.json`

## Stop Conditions

- hash or signature mismatch
- published registry emitted before explicit authorization
- production default changed by registry staging
- candidate entry has published=true before publish gate
- runtime resolver cannot prove rollback pointer
