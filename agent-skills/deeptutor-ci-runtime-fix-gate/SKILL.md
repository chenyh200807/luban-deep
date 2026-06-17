---
name: deeptutor-ci-runtime-fix-gate
description: "Use this when GitHub Actions, Tests, Smoke Tests, Security Scan, Deploy Gate, route smoke, contract guard, detect-secrets, or CI/local runtime mismatch fails. It turns CI failures into reproducible, same-SHA, CI-like repairs instead of patching symptoms."
---

# DeepTutor CI Runtime Fix Gate

Use this skill whenever the task is to repair GitHub Actions or decide whether
`main` is green.

## Activation

Trigger this skill for:

- GitHub Actions links, failed workflow runs, or screenshots of red Actions;
- `Tests`, `Smoke Tests (Python 3.11)`, `Security Scan`, `Contract Guard`,
  `Frontend Checks`, `WX Checks`, `Yousen Checks`, or `Deploy Gate` failures;
- questions like "还有 fail 吗", "继续修", "运行错误", or "为什么 Actions 还是红";
- route smoke failures where FastAPI routes look missing in CI.

Also read `docs/runbook/ci-runtime-smoke-guardrails.md` for the current failure
catalog.

## Start Frame

Before editing, write or keep internally clear:

```text
target run:
target sha:
workflow/job:
blocking failure vs advisory:
local reproduction command:
clean worktree:
files allowed to change:
green definition:
```

`green definition` is not satisfied until the latest `Tests` workflow and the
same-SHA `Deploy Gate` are both successful.

## Workflow

1. Lock the repo state:
   - `git rev-parse --show-toplevel`
   - `git status --short --branch`
   - `git rev-parse HEAD`
   - `git ls-remote origin refs/heads/main`
2. If the shared workspace is dirty, use a clean candidate worktree. Do not
   reset, stash, or sweep unrelated dirty files.
3. Identify the latest run for the target SHA:
   - `gh run list --repo chenyh200807/luban-deep --branch main --limit 12`
   - `gh run view <run_id> --json status,conclusion,headSha,jobs`
4. Separate failure classes:
   - product code or contract bug;
   - test isolation bug;
   - local vs CI dependency drift;
   - root `contracts/index.yaml` vs packaged `deeptutor/contracts/index.yaml`
     drift;
   - `.secrets.baseline` metadata drift;
   - external runner or deprecation advisory.
5. Reproduce with the narrowest local command. If the failure appears only in
   CI, create a CI-like venv from `requirements/server.txt` and run the same
   pytest subset with `PYTHONPATH=$PWD LANGFUSE_ENABLED=false`.
6. Fix the single root cause. Do not make production code compensate for a test
   harness bug, and do not make a test fake a route, contract, or secret state.
7. Run focused verification first, then the local CI smoke subset when the
   change touches smoke, route mounting, contract index, or test isolation.
8. Push only the narrow payload when the user asked for commit/push or when the
   ongoing release workflow already requires it.
9. Watch the new `Tests` run. If it succeeds, check the same-SHA `Deploy Gate`.
   If either fails, fetch that job's logs and continue from step 4.

## CI Runtime Failure Patterns

### FastAPI route smoke

FastAPI may expose included routers as deferred `_IncludedRouter` entries with
`path=None`. Route tests must recursively collect both eager `APIRoute.path`
and deferred `original_router.routes` plus `include_context.prefix`. A raw
`{route.path for route in app.routes}` can falsely report only base probes.

### Import-time app state

`deeptutor.api.main` builds the app at import time. Tests that change runtime
env must clear runtime env keys, point env-store at a test-local store, and
import the app in a fresh process when asserting production/local route
contracts.

### Contract index mirror

`contracts/index.yaml` is the repo authority.
`deeptutor/contracts/index.yaml` is the packaged runtime copy. Any authority
change must mirror to the packaged copy in the same payload.

### Secret scan

`detect-secrets-hook --baseline .secrets.baseline $(git ls-files)` may update
only line numbers for already-audited false positives. Commit that mechanical
baseline update only after inspecting the diff. New high-entropy values in
source, config, docs, or env examples are not baseline updates; remove and
rotate them.

## Reporting

Always report:

- latest `origin/main` SHA;
- latest `Tests` run URL and conclusion;
- same-SHA `Deploy Gate` URL and conclusion;
- local verification commands;
- advisory annotations that remain non-blocking;
- whether the current visible workspace was left on a dirty non-main branch.

## Red Flags

- Saying "fixed" while the latest same-SHA Deploy Gate has not run.
- Relying on global local Python packages when CI installed newer dependencies.
- Treating baseline refresh as safe without inspecting the diff.
- Hiding Node.js action deprecation or frontend i18n annotations as failures.
- Updating production route code to satisfy a route-introspection test bug.

## Verification

- [ ] Failure is tied to one workflow run and one SHA.
- [ ] Blocking failures are separated from advisory annotations.
- [ ] Local reproduction uses focused commands and CI-like dependencies when
      dependency drift is plausible.
- [ ] Root cause is recorded in the runbook if it is a repeatable CI pattern.
- [ ] Latest `Tests` and same-SHA `Deploy Gate` are checked before final PASS.
