#!/usr/bin/env bash
# Live RLS regression gate — CI wrapper around scripts/ci/live_rls_audit.sh.
#
# Why: live_rls_audit.sh is report-only (it dumps RLS/grant state, never fails).
# This wrapper turns it into a fail-on-new-violation gate so the P5 fix
# (20260529000300_rls_harden_user_tables.sql) cannot silently regress: if any
# PII / sensitive public table regains an anon or authenticated grant, CI goes red.
#
# Graceful degradation (per task requirement): the audit needs SUPABASE_DB_URL
# (service-role pooler connection string). On forks / PRs without the secret,
# live_rls_audit.sh exits 2. This wrapper treats a missing secret as SKIP+WARN
# (exit 0) so a missing credential never blocks CI — only a real, observed
# violation fails the gate.
#
# Configure the repo secret SUPABASE_DB_URL (Settings → Secrets → Actions) to
# activate enforcement.
#
# Exit codes:
#   0  — secret absent (skip+warn), OR audit clean (no monitored table exposed)
#   1  — at least one monitored table still grants anon/authenticated
#   2  — secret present but audit could not run (psql missing / connection error)

set -euo pipefail

AUDIT="${AUDIT:-scripts/ci/live_rls_audit.sh}"

# Tables hardened by 20260529000300 — none may grant anon/authenticated.
MONITORED_TABLES="${MONITORED_TABLES:-user_profiles user_stats user_goals user_logs user_emotion_logs user_badges learner_mistake_book_items questions_bank mock_exams}"

if [ -z "${SUPABASE_DB_URL:-}" ]; then
    echo "[SKIP] check_live_rls_regression: SUPABASE_DB_URL not set."
    echo "  → Configure the repo secret SUPABASE_DB_URL to enable live RLS enforcement."
    echo "  → Gate passes (warn-only) so a missing credential does not block CI."
    exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "[FAIL] jq not on PATH (required to parse audit JSON)" >&2
    exit 2
fi

# Run the read-only audit. live_rls_audit.sh exits 2 on connection/query failure.
audit_json="$(bash "$AUDIT")" || {
    rc=$?
    echo "[FAIL] live_rls_audit.sh failed (exit $rc) — could not fetch live RLS state." >&2
    exit 2
}

violations=0
for t in $MONITORED_TABLES; do
    exposed="$(printf '%s' "$audit_json" \
        | jq -r --arg t "$t" '
            (.tables[] | select(.table == $t) | .grants // [])
            | map(select(startswith("anon:") or startswith("authenticated:")))
            | join(", ")')"
    if [ -n "$exposed" ] && [ "$exposed" != "null" ]; then
        echo "[FAIL] public.$t still grants: $exposed" >&2
        violations=$((violations + 1))
    fi
done

if [ "$violations" -gt 0 ]; then
    echo "[FAIL] check_live_rls_regression: $violations monitored table(s) expose anon/authenticated grants." >&2
    echo "  → Apply supabase/migrations/20260529000300_rls_harden_user_tables.sql to this database." >&2
    exit 1
fi

echo "[OK] check_live_rls_regression: no monitored table grants anon/authenticated."
exit 0
