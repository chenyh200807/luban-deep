# Learning State Inference Release Readiness

Date: 2026-05-22

Scope: local completion review for
`docs/plan/2026-05-22-luban-learning-state-inference-engine-transformation-plan.md`.

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
