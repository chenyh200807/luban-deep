# Learning Report Flag Changes

## Scope

This runbook records learning-report P0 flags and secret readiness checks. It is not a deployment log and must not contain secret values.

## Flags

| Name | Default | Owner | Notes |
| --- | --- | --- | --- |
| `DEEPTUTOR_MISTAKE_BOOK_ENABLED` | `false` | learner-state | Enables mistake book read projection after RLS verification. |
| `DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED` | `false` | learner-state | Enables mistake book writes after Task 3 API verification. |
| `DEEPTUTOR_HOME_PERSONALIZATION_ENABLED` | `false` | member-console | Enables cached home dashboard learning projection after p95 verification. |

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
