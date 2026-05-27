#!/usr/bin/env python3
"""Print the harness hit-rate summary (9+ roadmap C3 — the real world-class judge).

Reads ``eval/harness_hit_ledger.json`` and reports the catch rate. ``real`` is the
figure that matters for 9+ (unintended regressions caught pre-merge); ``injected``
is capability evidence (the gates demonstrably have teeth).

Usage::

    python scripts/harness_hit_rate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.harness_hit_ledger import (  # noqa: E402
    catch_rate_summary,
    load_ledger,
)


def main() -> int:
    hits = load_ledger()
    summary = catch_rate_summary(hits)
    print("== Harness hit-rate (9+ judge: did the net actually catch regressions?) ==")
    print(
        f"REAL incidents:    caught {summary['real_caught']}/{summary['real_total']} "
        f"(rate={summary['real_catch_rate']})"
    )
    print(
        f"INJECTED (teeth):  caught {summary['injected_caught']}/{summary['injected_total']} "
        f"(rate={summary['injected_catch_rate']})"
    )
    print("\nby gate (caught/total):")
    for gate in sorted(summary["by_gate"]):
        slot = summary["by_gate"][gate]
        print(f"  {gate}: {slot['caught']}/{slot['total']}")
    if summary["real_total"] == 0:
        print(
            "\nNote: 0 real incidents recorded yet — gates are capability-proven (injected),"
            " real catch-rate accrues as the harness is used. That accrual IS the path to a"
            " credible 9+."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
