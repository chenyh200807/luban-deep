#!/usr/bin/env bash
# SR1 Layer A — static grep gate for default-secure router discipline.
#
# Fast pre-commit lint. The real authority is Layer B (runtime_route_inventory.py),
# because alias imports / wrappers / include_router chains can bypass grep.
# See deeptutor/api/_secure_router.py for the factory contract.
#
# Exit 0 = pass, non-zero = fail. CI must run this on every PR.

set -euo pipefail

ROUTERS_DIR="deeptutor/api/routers"
FACTORY="deeptutor/api/_secure_router.py"
MANIFEST="deeptutor/api/_public_manifest.py"
# STRICT=0 (default, post-PR-1a): warn-only baseline; routers still bare APIRouter.
# STRICT=1 (post-PR-1b migration): hard fail on bare APIRouter.
STRICT="${STRICT:-0}"
fail=0
warn_count=0

if [ ! -f "$FACTORY" ] || [ ! -f "$MANIFEST" ]; then
    echo "[FAIL] missing $FACTORY or $MANIFEST" >&2
    exit 1
fi

# Rule 1: no bare APIRouter() in routers/ — must use secure_router or public_router.
bad=$(grep -RnE '^[^#]*APIRouter\(' "$ROUTERS_DIR" 2>/dev/null || true)
if [ -n "$bad" ]; then
    n=$(echo "$bad" | wc -l | tr -d ' ')
    if [ "$STRICT" = "1" ]; then
        echo "[FAIL] bare APIRouter() found in $n places (STRICT=1):" >&2
        echo "$bad" >&2
        fail=1
    else
        echo "[WARN] bare APIRouter() found in $n places (STRICT=0 baseline; will fail when STRICT=1)" >&2
        warn_count=$((warn_count + n))
    fi
fi

# Rule 2: public_router() must include reason= kwarg.
bad=$(grep -RnE 'public_router\(' "$ROUTERS_DIR" 2>/dev/null | grep -vE 'reason\s*=' || true)
if [ -n "$bad" ]; then
    echo "[FAIL] public_router() without reason=:" >&2
    echo "$bad" >&2
    fail=1
fi

# Rule 3: WS endpoints must call secure_ws_endpoint OR be exempted via comment.
ws_violations=0
for f in $(grep -lE '@router\.websocket' "$ROUTERS_DIR"/*.py 2>/dev/null); do
    if ! grep -qE 'secure_ws_endpoint|# secure_ws_endpoint:exempt' "$f"; then
        if [ "$STRICT" = "1" ]; then
            echo "[FAIL] $f has @router.websocket without secure_ws_endpoint:" >&2
            grep -nE '@router\.websocket' "$f" >&2
            fail=1
        else
            ws_violations=$((ws_violations + 1))
        fi
    fi
done
if [ "$ws_violations" -gt 0 ] && [ "$STRICT" != "1" ]; then
    echo "[WARN] $ws_violations WS file(s) without secure_ws_endpoint (STRICT=0 baseline)" >&2
    warn_count=$((warn_count + ws_violations))
fi

if [ "$fail" -eq 0 ]; then
    if [ "$warn_count" -gt 0 ]; then
        echo "[OK-warn] check_secure_routers.sh: $warn_count baseline warnings (STRICT=0 mode)"
    else
        echo "[OK] check_secure_routers.sh: all routers use secure_router/public_router factory"
    fi
fi
exit "$fail"
