#!/usr/bin/env bash
# PR-2 SR2 Gate B — every `create table public.X` must enable RLS in the same migration.
#
# Without this gate, the SR2 root cause (PR-0 found 27 RLS-off tables) recurs:
# every new public table is anon-readable by default. Catching it at PR time
# avoids "schema baked, RLS forgotten" footgun.
#
# Exemption: a file may start with a header comment `-- rls-exempt: <reason>`
# to opt out (partition shards, views, ext schema bridges). The reason field
# is for human review, not validated here.

set -euo pipefail

MIG_DIR="${MIG_DIR:-supabase/migrations}"
# STRICT=0 (default): warn on historical violations (PR-2 baseline).
# STRICT=1: hard fail (use in CI for NEW migrations once historical drift is cleaned).
STRICT="${STRICT:-0}"
# FAIL_ON_NEW=1: pass historical migration violations listed in
# scripts/ci/baselines/rls_migrations_baseline.txt, but fail on any NEW migration
# that creates `public.X` without enabling RLS in the same file.
# This is the gate enforced in CI before STRICT=1 rollout.
FAIL_ON_NEW="${FAIL_ON_NEW:-0}"
BASELINE_FILE="${BASELINE_FILE:-scripts/ci/baselines/rls_migrations_baseline.txt}"

if [ "$FAIL_ON_NEW" = "1" ] && [ ! -f "$BASELINE_FILE" ]; then
    echo "[FAIL] FAIL_ON_NEW=1 but baseline file not found: $BASELINE_FILE" >&2
    echo "  → Either regenerate the baseline or unset FAIL_ON_NEW." >&2
    exit 1
fi

fail=0
warn_count=0

if [ ! -d "$MIG_DIR" ]; then
    echo "[SKIP] $MIG_DIR not found"
    exit 0
fi

for f in "$MIG_DIR"/*.sql; do
    [ -e "$f" ] || continue

    # Skip files explicitly opting out.
    if head -1 "$f" | grep -qE '^--[[:space:]]*rls-exempt:'; then
        continue
    fi

    # Capture every `create table [if not exists] public.<name>`.
    tables=$(grep -iEo 'create table( if not exists)? public\.[a-z_][a-z0-9_]*' "$f" \
        | sed -E 's/.*public\.//I' | sort -u || true)
    [ -z "${tables}" ] && continue

    for t in ${tables}; do
        if ! grep -iqE "alter table[[:space:]]+public\.${t}[[:space:]]+enable[[:space:]]+row[[:space:]]+level[[:space:]]+security" "$f"; then
            basename_f=$(basename "$f")
            if [ "$FAIL_ON_NEW" = "1" ]; then
                if ! grep -qxF "$basename_f" "$BASELINE_FILE"; then
                    echo "[FAIL] new migration $basename_f creates public.${t} without RLS enabled in same migration" >&2
                    echo "  → If intentional, regenerate $BASELINE_FILE and reference the approving PR." >&2
                    fail=1
                fi
            elif [ "$STRICT" = "1" ]; then
                echo "[FAIL] $basename_f: table public.${t} created but RLS not enabled in same migration" >&2
                fail=1
            else
                warn_count=$((warn_count + 1))
            fi
        fi
    done
done

if [ "$fail" -eq 0 ]; then
    if [ "$FAIL_ON_NEW" = "1" ]; then
        echo "[OK] check_rls_on_create_table: FAIL_ON_NEW gate passed (baseline: $BASELINE_FILE, $(wc -l < "$BASELINE_FILE" | tr -d ' ') known historical migration files skipped, 0 new)"
    elif [ "$warn_count" -gt 0 ]; then
        echo "[OK-warn] check_rls_on_create_table: $warn_count historical violation(s) (STRICT=0 baseline)" >&2
        echo "  → Re-run with STRICT=1 to see details and fail the gate." >&2
    else
        echo "[OK] check_rls_on_create_table: all new public tables enable RLS"
    fi
fi
exit "$fail"
