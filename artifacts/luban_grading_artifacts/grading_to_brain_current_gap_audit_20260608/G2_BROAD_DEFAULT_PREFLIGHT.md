# G2 Broad Default Preflight

- Gate: `G2_broad_production_default`
- Verdict: `not_ready_limited_default_not_executed`
- Blocking reason: G1 limited default must be explicitly authorized/executed and reviewed before broad default
- Scope: `read_only_pre_authorization_preflight`
- Execution mode: `read_only_no_broad_flip`
- Without authorization: `decision_package_only`
- Required authorization: `separate_broad_default_authorization_after_limited_soak`
- Allowed scope after authorization: `explicitly named cohort expansion only`
- Promotion path: `runtime_default_only_no_mastery_write`

This artifact is a broad-default gate report only. It does not flip broad production default, write canonical learner truth, publish registry, or write remote/DB state.

## No-Write Invariants

- production_write_count: `0`
- canonical_truth_written: `False`
- remote_write_count: `0`
- published_registry_executed: `False`

## Preconditions

- g1_ready_for_authorization: `True`
- limited_default_executed_by_this_package: `False`
- limited_default_current_state: `ON`
- m19d_soak_verdict: `GO`
- m19d_broad_default: `NO-GO`
- m19c_production_default_broad: `NO-GO`
- m19c_production_v1_broad_default: `NO-GO`
- soak_false_positive_count: `0`
- soak_source_mismatch_count: `0`
- soak_bad_certified_count: `0`
- m19e_broad_default_remains_no_go: `True`

## Single Authority

- no_second_grading_truth: `True`
- no_second_learner_truth: `True`
- grading_truth_source: `authorized limited-default runtime evidence before any broad flip`
- learner_truth_source: `unchanged Learning Evidence Ledger / Learner Model`
- pcp_role: `read_only_feedback_context`

## Evidence

- `artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G1_LIMITED_DEFAULT_PREFLIGHT.json`
- `artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/go_no_go_m19c.json`
- `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json`
- `artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/soak_metrics_m19d.json`
- `artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/m19c_m19d_evidence_ledger_m19e.json`

## Stop Conditions

- G1 limited default not explicitly authorized/executed/reviewed
- false_positive > 0
- bad_certified > 0
- source_mismatch > 0
- teacher review backlog exceeds operator capacity
- unsupported claim or generic fallback drift appears
- any canonical learner truth write is requested by this gate
