# Learning State Inference Release Readiness

Date: 2026-05-22

Scope: local completion review for
`docs/plan/学习脑与学员记忆/2026-05-22-luban-learning-state-inference-engine-transformation-plan.md`.

## Local Gates Completed

- Phase -1 through Batch D code paths are present on the current branch.
- `LEARNING_STATE_INFERENCE_V2` env cohort helper exists in
  `deeptutor/services/experiments/cohort.py`.
- ARRS-style revalidation queue exists in
  `deeptutor/services/learner_state/revalidation_queue.py`, reuses
  `training_intent.prioritize_training_intents`, and emits at most one probe
  item per learner per day.
- Frontend inference audit exists at `scripts/audit_frontend_inference.py`.
- Evidence story redaction is centralized in
  `deeptutor/services/learner_state/redaction.py`.
- Scenario matrix fixtures exist in `tests/fixtures/learning_state_scenarios.py`.

## Plan Completion Matrix

This matrix is intentionally split into local implementation status and release
promotion status. Local code completion does not imply broad release readiness.

| Plan item | Local status | Evidence |
| --- | --- | --- |
| Task 0.A Rubric coverage telemetry and LLM grounding | Done | `scripts/rubric_coverage_report.py`, `docs/qa/2026-05-22-rubric-coverage-baseline.md`, `tests/services/construction_grading/test_rubric_coverage_audit.py`, `tests/services/construction_grading/test_grader_disagreement_audit.py` |
| Task 0.B Unified error code registry | Done | `docs/contracts/error_code_registry.md`, `deeptutor/contracts/error_codes.py`, `scripts/check_contract_guard.py`, `tests/services/construction_grading/test_error_code_registry.py` |
| Task 0.C `training_intent` / `study_plan` authority reconciliation | Done | `deeptutor/services/learner_state/study_plan.py`, `tests/services/learner_state/test_study_plan_reads_training_intent.py` |
| Task 0.D Synthesis and read-model performance budget | Done | `scripts/bench_learning_synthesis.py`, `docs/qa/2026-05-22-learning-state-performance-baseline.md`, `tests/services/learner_state/test_learning_synthesis_window.py` |
| Task 1 Contract addendum for learning-state inference | Done | `docs/contracts/learning-state-inference.md`, dual `contracts/index.yaml` registration, `tests/contracts/test_index_consistency.py` |
| Task 2 Case rubric evidence payload | Done | `deeptutor/services/construction_grading/learning_evidence.py`, `tests/services/construction_grading/test_learning_evidence_payload.py` |
| Task 3 Minimal expert graph seed | Done | `deeptutor/services/taxonomy/construction_learning_graph.py`, node-id guard in `scripts/check_contract_guard.py`, `tests/services/taxonomy/test_construction_learning_graph.py` |
| Task 4 Three-layer learning state projection | Done | `deeptutor/services/learner_state/learning_state_projection.py`, synthesis integration, `tests/services/learner_state/test_learning_state_projection.py` |
| Task 5 Recency-aware confidence and forgetting risk | Done | `deeptutor/services/learner_state/mastery_estimator.py`, `tests/services/learner_state/test_mastery_estimator.py` |
| Task 6 Prescription intent v2 | Done | `deeptutor/services/learner_state/training_intent.py`, `tests/services/learner_state/test_training_intent.py` |
| Task 7 Scoring point map read projection | Done | `deeptutor/services/learner_state/scoring_point_map_read_model.py`, `tests/services/learner_state/test_scoring_point_map_read_model.py` |
| Task 8 Student UI state / reason / action / evidence | Done locally | `learning_report_read_model.py`, mirrored `wx_miniprogram` and `yousenwebview/packageDeeptutor` view-model/WXML tests; manual WeChat DevTools acceptance still required before release |
| Task 9 Prescription completion and revalidation evidence | Done | `prescription_outcomes` read projection, `revalidation_queue`, writeback payload tests, `tests/services/learner_state/test_prescription_outcomes_read_model.py`, `tests/services/learner_state/test_revalidation_queue.py` |
| Task 10 Teacher and sales evidence story projection | Done | `deeptutor/services/learner_state/evidence_story_read_model.py`, centralized redaction, `tests/services/learner_state/test_evidence_story_read_model.py`, `tests/services/learner_state/test_evidence_story_pii_redaction.py` |
| Feature flag and rollback gates | Done locally | `deeptutor/services/experiments/cohort.py`, `tests/services/experiments/test_cohort.py`; production kill-switch drill still required |
| Frontend no-inference gate | Done locally | `scripts/audit_frontend_inference.py`; must remain in release gate |
| 20-row scenario matrix | Done locally | `tests/fixtures/learning_state_scenarios.py`, `tests/services/learner_state/test_learning_state_scenario_matrix.py` |

## Deferred Release Promotion Gates

These items are intentionally not marked as complete because they require
human review, WeChat tooling, deployment, or production traffic.

- 教研 normalization preview sign-off.
- 教研 graph seed review.
- WeChat DevTools report / attempt detail / home prompt click-loop regression.
- Cohort rollout evidence for internal, cohort_10 and cohort_50.
- A/B comparison report before promoting from cohort_10 to cohort_50.
- 7-day production metrics for evidence coverage, prescription verification,
  recurrence, degraded sources, p95, and unregistered error-code rate.
- 15-minute kill-switch drill with before / during / after screenshots.
- Merge back to the source worktree, push, Aliyun deploy and deployed-SHA
  verification.

## Release Gates Not Claimable Locally

These remain manual or production gates. They must not be reported as done until
real evidence exists.

- 教研 normalization preview sign-off.
- 教研 graph seed review.
- WeChat DevTools visual regression for report, attempt detail and home prompt
  click loops.
- 7-day production metrics:
  - `evidence_refs_coverage_rate >= 0.90`
  - `home_prompt_click_to_evidence_rate >= 0.70`
  - `prescription_verification_rate >= 0.40`
  - `mistake_recurrence_rate` treatment < control
  - `/api/v1/mobile/learning-report` p95 <= 600ms under cohort traffic
  - `degraded_sources_rate <= 0.05`
  - zero unregistered production error codes
- A/B cohort report for cohort_10 before promotion to cohort_50.
- 15-minute kill-switch drill with before/during/after WeChat DevTools
  screenshots.

## Merge / Release Review Condition

The branch can enter final merge/release review only after local automated gates
pass. It cannot be released to broad traffic until the production gates above
are attached to the release report.
