# G1 Limited Default Preflight

- Gate: `G1_limited_production_default`
- Verdict: `ready_for_user_authorization`
- Scope: `read_only_pre_authorization_preflight`
- Execution mode: `read_only_no_flip`
- Without authorization: `decision_package_only`
- Required authorization: `explicit_user_authorization_for_limited_default`
- Allowed scope after authorization: `qa_/operator_ cohort only`

This artifact does not flip production default, publish registry, write remote/DB state, or promote canonical learner truth.

## No-Write Invariants

- production_write_count: `0`
- canonical_truth_written: `False`
- remote_write_count: `0`
- published_registry_executed: `False`

## Preconditions

- m19c_limited_default_flip: `GO`
- m19d_soak_verdict: `GO`
- rollback_readiness: `True`
- safety_invariants: `True`
- rollback_works: `True`
- broad_default: `NO-GO`
- canonical_learner_truth_write: `NO-GO`

## Evidence

- `artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/go_no_go_m19c.json`
- `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json`
- `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/rollback_readiness_drill_m19d.json`
- `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/safety_invariants_m19d.json`

## Stop Conditions

- false_positive > 0
- bad_certified > 0
- source_mismatch > 0
- legacy_equal < 1.0
- teacher review backlog exceeds operator capacity
- any canonical learner truth write is requested by this gate
