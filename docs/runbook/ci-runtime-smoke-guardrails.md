# CI Runtime Smoke Guardrails

## Scope

This runbook covers failures where GitHub Actions `Smoke Tests (Python 3.11)`
reports missing FastAPI routes even though focused route tests pass locally.

Agents must reach this runbook through
`agent-skills/deeptutor-ci-runtime-fix-gate/SKILL.md` whenever repairing
GitHub Actions, `Tests`, `Smoke Tests`, `Security Scan`, `Deploy Gate`,
contract-guard CI, secret baseline, route smoke, or CI/local runtime mismatch
failures.

This file is the failure catalog. `AGENTS.md` and the skill are the activation
surface.

## Tests Workflow Fast Path

The `Tests` workflow is intentionally split into PR fast paths and push-to-main
full validation:

- PR runs first classify changed paths in `Change Scope`, then run only the
  affected domain jobs. Backend/governance changes run contract/import/smoke;
  `web/`, `wx_miniprogram/`, and `yousenwebview/` changes run their own checks.
- Pushes to `main` or `dev` still run the full job set so Deploy Gate remains a
  main-line release-readiness signal.
- PR secret scanning checks only changed tracked files; push secret scanning
  still checks the full repository.
- Skipped PR jobs are expected when their domain was not touched. Do not treat a
  skipped frontend/WX/Yousen job as a missing test unless the changed paths
  should have selected that domain.
- Repeated pushes to the same PR cancel older in-flight `Tests` runs. Debug the
  newest run for the current head SHA, not a cancelled older SHA.

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
   `SERVICE_ENV`, `DEEPTUTOR_ENV_FILE`, and `DEEPTUTOR_ENV_PATH`.
2. Clear route-feature env keys before each scenario:
   `DEEPTUTOR_ENABLE_API_DOCS`, `DEEPTUTOR_ENABLE_LEGACY_ROUTERS`,
   `DEEPTUTOR_ENABLE_PUBLIC_OUTPUTS`, and
   `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA`.
3. Point `deeptutor.services.config.env_store._env_store` at a test-local
   `EnvStore(path=..., fallback_paths=())`. `runtime_env` and `main.py` read
   through env-store authority; clearing only `os.environ` is not enough when a
   previous test or a developer worktree `.env` has initialized the store.
4. Remove `deeptutor.api.main` from `sys.modules` before importing the app
   again. Do not casually clear every router module: some router schemas rely
   on module-local forward-reference rebuild state, and broad cache eviction can
   create smoke failures unrelated to route mounting.
5. For assertions that define production/local route-mount contracts, prefer a
   fresh Python subprocess probe over an in-process reload. The subprocess must
   set a test-local `DEEPTUTOR_USER_DATA_DIR`, empty env file, and scenario env
   before importing `deeptutor.api.main`. This matches CI cold-start semantics
   and avoids turning pytest module-cache pollution into a product fallback.
6. Collect route paths through a helper that understands both eagerly-expanded
   `APIRoute.path` entries and FastAPI's deferred `_IncludedRouter`
   representation. FastAPI 0.137 can keep included routers as wrapper entries
   with `path=None`; a raw `{route.path for route in app.routes}` check will
   report only base probes even though routers are mounted.
7. Keep production code unchanged unless the same route set fails in a fresh
   process with the same env.

For mobile billing quota tests, patch the imported router binding when the test
needs a deterministic billing-enforcement branch:
`monkeypatch.setattr(mobile_module, "is_billing_enforcement_enabled", ...)`.
The router imports that function at module import time, so setting only
`DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` can leave full-smoke order dependent.
Also freeze `mobile_module.datetime.now()` for quota-window tests: weekly
windows reset at Asia/Shanghai Monday 00:00, so relative timestamps like
`datetime.now() - timedelta(hours=1)` can cross into the previous week during
Sunday/Monday CI runs.
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

### Full Secret Scan Timeout

Push-to-main `Security Scan` runs `scan-secrets-full`. If it spends about five
minutes in `Secret scan full repository (BLOCKING on push)` and ends with
`The operation was canceled`, first classify it as CI runtime timeout, not as a
confirmed secret finding. The fix belongs in
`scripts/ci/tests_workflow_scope.py` scan-input filtering, not in
`.secrets.baseline`.

The scan must still include source, workflow, config, env examples, and
user-authored docs. It may skip known generated payloads, binary/media files,
runtime-supply data, and the baseline file itself. Reproduce locally with:

```bash
python scripts/ci/tests_workflow_scope.py scan-secrets-full
```

Record both the original timeout and the filtered-file count/time in the PR.

## Contract Index Copy Discipline

`contracts/index.yaml` is the repo authority, and
`deeptutor/contracts/index.yaml` is the packaged runtime copy. Any change to the
repo authority must be mirrored into the packaged copy in the same commit. The
smoke suite intentionally fails `tests/services/test_app_facade.py` when these
two files drift, because a packaged install would otherwise load stale contract
metadata.
