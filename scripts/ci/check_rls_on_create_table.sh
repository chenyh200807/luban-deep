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
            if [ "$STRICT" = "1" ]; then
                echo "[FAIL] $(basename "$f"): table public.${t} created but RLS not enabled in same migration" >&2
                fail=1
            else
                warn_count=$((warn_count + 1))
            fi
        fi
    done
done

if [ "$fail" -eq 0 ]; then
    if [ "$warn_count" -gt 0 ]; then
        echo "[OK-warn] check_rls_on_create_table: $warn_count historical violation(s) (STRICT=0 baseline)" >&2
        echo "  → Re-run with STRICT=1 to see details and fail the gate." >&2
    else
        echo "[OK] check_rls_on_create_table: all new public tables enable RLS"
    fi
fi
exit "$fail"
