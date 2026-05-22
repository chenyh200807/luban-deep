# Learning Report Flag Changes

## Scope

This runbook records learning-report P0 flags and secret readiness checks. It is not a deployment log and must not contain secret values.

## Flags

| Name | Default | Owner | Notes |
| --- | --- | --- | --- |
| `DEEPTUTOR_MISTAKE_BOOK_ENABLED` | `false` | learner-state | Enables mistake book read projection after RLS verification. |
| `DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED` | `false` | learner-state | Enables mistake book writes after Task 3 API verification. |
| `DEEPTUTOR_HOME_PERSONALIZATION_ENABLED` | `false` | member-console | Enables cached home dashboard learning projection after p95 verification. |
| `LEARNING_STATE_INFERENCE_V2_STAGE` | `off` | learner-state | Master rollout flag for the learning-state inference engine. Valid stages: `off`, `internal`, `cohort_10`, `cohort_50`, `cohort_100`, `sticky_100`. |
| `LEARNING_STATE_INFERENCE_V2_EVIDENCE_STAGE` | `off` | learner-state | Batch A subgate for rubric/evidence payload visibility. |
| `LEARNING_STATE_INFERENCE_V2_STATE_PROJECTION_STAGE` | `off` | learner-state | Batch B subgate for three-layer state projection visibility. |
| `LEARNING_STATE_INFERENCE_V2_ACTION_LOOP_STAGE` | `off` | learner-state | Batch C subgate for prescription v2 and scoring-point map UI visibility. |
| `LEARNING_STATE_INFERENCE_V2_VERIFICATION_STAGE` | `off` | learner-state | Batch D subgate for ARRS revalidation and evidence story projections. |
| `LEARNING_STATE_INFERENCE_V2_INTERNAL_USERS` | empty | learner-state | Comma-separated dogfood allowlist. Never include phone, openid, or raw learner PII in this file. |

## Required Production Secret

`DEEPTUTOR_ATTEMPT_REF_SECRET` is required in production. It must be a random value of at least 32 bytes and must not equal the local development secret.

Validation command:

```bash
python scripts/check_secret_envs.py --env prod
```

Expected production output includes only a fingerprint:

```text
DEEPTUTOR_ATTEMPT_REF_SECRET=set fingerprint=<sha1-prefix>
```

## Change Log

| Date | Change | Evidence |
| --- | --- | --- |
| 2026-05-21 | Registered P0 flags and attempt-ref secret gate. | Local contract tests only; no production deployment in this worktree. |
| 2026-05-22 | Registered learning-state inference master flag and four subgates. | `tests/services/experiments/test_cohort.py`; `python scripts/audit_frontend_inference.py`; no production deployment in this worktree. |

## Learning-State Inference Rollback Drill

Rollback is flag-only and does not delete evidence. For each cohort promotion,
record before / during / after screenshots and the command output in the release
report.

1. Set `LEARNING_STATE_INFERENCE_V2_STAGE=off`.
2. Set all subgates to `off`.
3. Reload the backend env using the existing deployment process.
4. Re-open the mini-program learning page.
5. Confirm the page hides three-layer state, scoring-point map, ARRS probes and
   evidence story surfaces, while the legacy learning report still loads.
6. Restore the prior stage only after the health check is green.

Batch-specific fallback:

- Batch A: `LEARNING_STATE_INFERENCE_V2_EVIDENCE_STAGE=off`.
- Batch B: `LEARNING_STATE_INFERENCE_V2_STATE_PROJECTION_STAGE=off`.
- Batch C: `LEARNING_STATE_INFERENCE_V2_ACTION_LOOP_STAGE=off`.
- Batch D: `LEARNING_STATE_INFERENCE_V2_VERIFICATION_STAGE=off`.
