#!/usr/bin/env bash
# SR3 PR-3 — single-authority gate: no private rate-limit implementations.
#
# All rate limiting MUST flow through:
#   - deeptutor/api/dependencies/rate_limit.route_rate_limit (HTTP)
#   - deeptutor/api/dependencies/rate_limit.enforce_websocket_rate_limit (WS)
#
# Why: per-process dicts (`_RATE_LIMIT_BUCKETS`, `_extract_ip = ...`) silently
# break across uvicorn workers and trust unverified `X-Forwarded-For` first hop.
# The authoritative limiter uses SQLite/Redis with key extraction normalization.

set -euo pipefail

ALLOWED_FILE="deeptutor/api/dependencies/rate_limit.py"
fail=0

# Rule 1: no `_RATE_LIMIT_BUCKETS` outside the canonical file.
bad=$(grep -RnE '_RATE_LIMIT_BUCKETS' deeptutor/ --include='*.py' 2>/dev/null \
    | grep -v "$ALLOWED_FILE" || true)
if [ -n "$bad" ]; then
    echo "[FAIL] private _RATE_LIMIT_BUCKETS found (use route_rate_limit instead):" >&2
    echo "$bad" >&2
    fail=1
fi

# Rule 2: no `_extract_ip = ...` (or `def _extract_ip`) defined outside the canonical file.
bad=$(grep -RnE '_extract_ip[[:space:]]*[=(]|def _extract_ip' deeptutor/ --include='*.py' 2>/dev/null \
    | grep -v "$ALLOWED_FILE" || true)
if [ -n "$bad" ]; then
    echo "[FAIL] private _extract_ip found (use route_rate_limit key extraction):" >&2
    echo "$bad" >&2
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "[OK] check_rate_limit_single_authority: no private limiters detected"
fi
exit "$fail"
