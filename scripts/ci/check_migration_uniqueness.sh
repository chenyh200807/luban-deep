#!/usr/bin/env bash
# PR-2 SR2 Gate A — migration timestamp uniqueness + monotonic order.
#
# Fail if two .sql files in supabase/migrations/ share the same 14-digit
# timestamp prefix, or if the directory listing is not in ascending order.
#
# Why: Supabase CLI applies migrations by filename sort order. Duplicate
# timestamps make application order implementation-defined; non-monotonic
# entries hint that someone hand-edited a file name post-apply (drift risk).

set -euo pipefail

MIG_DIR="${MIG_DIR:-supabase/migrations}"
fail=0
prev=""

if [ ! -d "$MIG_DIR" ]; then
    echo "[SKIP] $MIG_DIR not found"
    exit 0
fi

# Only check `.sql` files with the 14-digit prefix convention.
# (Portable bash 3.2: no `mapfile`.)
files_list=$(ls "$MIG_DIR" 2>/dev/null | grep -E '^[0-9]{14}_.*\.sql$' | sort)
count=$(printf '%s\n' "$files_list" | grep -c . || true)

# Rule 1: no duplicate timestamps.
dupes=$(printf '%s\n' "$files_list" \
    | awk -F'_' '{print $1}' \
    | sort | uniq -d)
if [ -n "${dupes}" ]; then
    echo "[FAIL] duplicate migration timestamps:" >&2
    while IFS= read -r ts; do
        [ -z "$ts" ] && continue
        echo "  ts=${ts}" >&2
        printf '%s\n' "$files_list" | grep -E "^${ts}_" | sed 's/^/    - /' >&2
    done <<< "${dupes}"
    fail=1
fi

# Rule 2: monotonic ascending order (sorted == directory order by ts).
while IFS= read -r f; do
    [ -z "$f" ] && continue
    ts="${f%%_*}"
    if [ -n "${prev}" ] && [ "${ts}" \< "${prev}" ]; then
        echo "[FAIL] non-monotonic: ${f} < previous timestamp ${prev}" >&2
        fail=1
    fi
    prev="${ts}"
done <<< "$files_list"

if [ "$fail" -eq 0 ]; then
    echo "[OK] check_migration_uniqueness: ${count} migrations unique + monotonic"
fi
exit "$fail"
