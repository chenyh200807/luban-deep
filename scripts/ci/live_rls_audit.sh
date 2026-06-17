#!/usr/bin/env bash
# Live RLS audit — PR-0 baseline gate (read-only).
#
# Connects to a Supabase Postgres instance and dumps the RLS / policy / grant
# state of every `public.*` table. Output goes to stdout as JSON for diffing
# against docs/audit/rls_audit.json.
#
# PR-0 is *report-only*: this script does not fail on findings; it captures
# the baseline. SR2 Gate B (check_rls_on_create_table.sh) is the
# fail-on-violation gate; this script is the live ground-truth companion.
#
# Why this exists (codex review R2): static migration scanning misses tables
# that exist in production but not in the migrations directory (e.g.
# `public.users`, `public.wallets`), and misses RLS state drift between
# environments.
#
# Usage:
#   SUPABASE_DB_URL=postgresql://... bash scripts/ci/live_rls_audit.sh > docs/audit/rls_audit.json
#
# Required env:
#   SUPABASE_DB_URL — Postgres connection string with read access to pg_catalog
#                     and information_schema. Service-role pooler URL works.
#
# Exits non-zero only on connection / query failure, never on policy findings.

set -euo pipefail

if [ -z "${SUPABASE_DB_URL:-}" ]; then
    cat >&2 <<'ERR'
ERROR: SUPABASE_DB_URL not set.

To dump live baseline:
  export SUPABASE_DB_URL='postgresql://postgres.<project>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres'
  bash scripts/ci/live_rls_audit.sh > docs/audit/rls_audit.json

You can also pass it inline:
  SUPABASE_DB_URL='...' bash scripts/ci/live_rls_audit.sh
ERR
    exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql not on PATH (install postgresql client)" >&2
    exit 2
fi

# JSON output. Aggregates table-level RLS state + policy count + anon/authenticated grants.
psql "$SUPABASE_DB_URL" -At -v ON_ERROR_STOP=1 <<'SQL'
with table_rls as (
    select n.nspname as schema_name,
           c.relname as table_name,
           c.relrowsecurity as rls_enabled,
           c.relforcerowsecurity as rls_forced
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r'
),
policy_counts as (
    select schemaname, tablename, count(*) as n_policies
    from pg_policies
    group by schemaname, tablename
),
grants_agg as (
    select table_schema, table_name,
           array_agg(distinct grantee || ':' || privilege_type order by grantee || ':' || privilege_type) as grants
    from information_schema.role_table_grants
    where grantee in ('anon', 'authenticated', 'service_role')
    group by table_schema, table_name
)
select json_build_object(
    'generated_at', to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'database', current_database(),
    'tables', coalesce(json_agg(
        json_build_object(
            'schema', t.schema_name,
            'table', t.table_name,
            'rls_enabled', t.rls_enabled,
            'rls_forced', t.rls_forced,
            'n_policies', coalesce(pc.n_policies, 0),
            'grants', coalesce(ga.grants, array[]::text[])
        ) order by t.table_name
    ), '[]'::json)
) as result
from table_rls t
left join policy_counts pc on pc.schemaname = t.schema_name and pc.tablename = t.table_name
left join grants_agg ga on ga.table_schema = t.schema_name and ga.table_name = t.table_name;
SQL
