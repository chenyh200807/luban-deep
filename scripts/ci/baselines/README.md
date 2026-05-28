# CI Gate Baselines

This directory holds frozen snapshots of historical violations for fail-on-new
CI gates. Each file is line-oriented `file:line` (or `filename`) entries that
the gate scripts treat as the known historical debt allowlist.

When `FAIL_ON_NEW=1` is set, a gate script:
- Reads the matching baseline file
- Ignores any violation whose key appears in the baseline
- Fails the PR on any violation whose key does NOT appear in the baseline

**Never edit baseline files by hand to silence a new violation.** If a new
violation is intentional and approved, regenerate the baseline:

    STRICT=1 bash scripts/ci/check_<gate>.sh 2>&1 | <extract keys> > <baseline>

and reference the approving PR in the commit message.

## Files

- `secure_routers_baseline.txt` — `file:line` keys for bare `APIRouter()`,
  `public_router()` missing reason, or `@router.websocket` without
  `secure_ws_endpoint`, as detected by `scripts/ci/check_secure_routers.sh`.
- `rls_migrations_baseline.txt` — migration filenames where
  `create table public.X` lacks same-migration `enable row level security`,
  as detected by `scripts/ci/check_rls_on_create_table.sh`.
