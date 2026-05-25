#!/usr/bin/env bash
# SR6 PR-5 Gate C — main.py must wire up safety primitives.
#
# This is a smoke-gate. Layer A/B (forbidding bare asyncio.create_task across
# the codebase) is deferred to SR6-W1 because 46 historical call-sites need
# triage first. For now, ensure the new file at least gets imported + used by
# the canonical entry.

set -euo pipefail

MAIN="deeptutor/api/main.py"
fail=0

if ! grep -q 'install_exception_handlers' "$MAIN"; then
    echo "[FAIL] $MAIN must call install_exception_handlers(app)" >&2
    fail=1
fi

if ! grep -q 'register_readiness_check' "$MAIN"; then
    echo "[FAIL] $MAIN must call register_readiness_check(...) at least once" >&2
    fail=1
fi

if ! grep -q 'run_readiness_checks' "$MAIN"; then
    echo "[FAIL] $MAIN /readyz must call run_readiness_checks() for active probes" >&2
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "[OK] check_runtime_safety_usage: main.py wires install_exception_handlers + register_readiness_check + run_readiness_checks"
fi
exit "$fail"
