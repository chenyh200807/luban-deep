# CI Runtime Smoke Guardrails

## Scope

This runbook covers failures where GitHub Actions `Smoke Tests (Python 3.11)`
reports missing FastAPI routes even though focused route tests pass locally.

## Failure Signature

- `tests/api/test_main_entrypoints.py` fails inside the full smoke suite.
- The app route set contains only base probes such as `/`, `/healthz`,
  `/readyz`, `/metrics`, and `/metrics/prometheus`.
- Focused `tests/api/test_main_entrypoints.py` can pass when run alone.

## Root Cause Pattern

`deeptutor.api.main` builds the FastAPI app at import time. Tests that exercise
different runtime environments must treat import-time env values and imported
router modules as part of the same authority boundary.

Do not rely on `importlib.reload(deeptutor.api.main)` alone. A prior test can
leave env keys or router modules in `sys.modules`, so a later reload may not
represent the environment it claims to test.

## Required Test Isolation

When testing `deeptutor.api.main` route mounting:

1. Clear all runtime-env authority keys before setting the scenario:
   `DEEPTUTOR_ENV`, `DEEPTUTOR_RUNTIME_ENV`, `APP_ENV`, `ENV`, `ENVIRONMENT`,
   and `SERVICE_ENV`.
2. Clear route-feature env keys before each scenario:
   `DEEPTUTOR_ENABLE_API_DOCS`, `DEEPTUTOR_ENABLE_LEGACY_ROUTERS`,
   `DEEPTUTOR_ENABLE_PUBLIC_OUTPUTS`, and
   `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA`.
3. Remove `deeptutor.api.main` from `sys.modules` before importing the app
   again. Do not casually clear every router module: some router schemas rely
   on module-local forward-reference rebuild state, and broad cache eviction can
   create smoke failures unrelated to route mounting.
4. Keep production code unchanged unless the same route set fails in a fresh
   process with the same env.

## Secret Baseline Discipline

If `detect-secrets-hook --baseline .secrets.baseline $(git ls-files)` reports
only that the baseline file was updated, inspect the diff. Line-number-only
updates for existing false positives may be committed with the related test
change.

Generated runtime-supply manifests may contain deterministic `content_hash`,
`source_aggregate_sha256`, or `signature` fields. Before registering a new
baseline entry for those files, sample the surrounding JSON and confirm the
value is a generated artifact hash, not a credential or token. New high-entropy
strings in application config, source code, env examples, or user-authored docs
still require removal and credential rotation, not baseline registration.
