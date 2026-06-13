#!/usr/bin/env python3
"""Governance meta-gate: every scanner cataloged + every pr_gate actually wired into CI.

The audit found the "foundation of the foundation" ungoverned — 20+ governance scanners
with no catalog and no check that each runs in CI, which is exactly how
check_harness_authority / check_model_authority and the schema-registry unit tests ran in
ZERO workflows for a long time. This gate closes that, reusing the one-runner pattern (it
adds no second schema/resource authority — it governs the completeness + wiring of the
existing gate set).

Two deterministic checks against contracts/registries.yaml:
  1. register-before-use for the GATES THEMSELVES: every scripts/check_*.py +
     scripts/ci/check_*.{py,sh} governance scanner on disk MUST be cataloged. A new scanner
     cannot be added dead/uncataloged.
  2. no pr_gate goes dark: every cataloged scanner with enforcement == pr_gate MUST appear
     as an executed step in .github/workflows/tests.yml.
Also fails if a cataloged entry points to a script that does not exist on disk.

Exit 0 = clean; 1 = violation. Pure / read-only.
"""

from __future__ import annotations

import glob
from pathlib import Path
import sys

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "contracts" / "registries.yaml"
CI_WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"

# The governance-scanner discovery globs. A script matching these is a "gate" that must be
# cataloged. (Plain scripts/*.py that are not check_* are not gates and are out of scope.)
_DISCOVERY = ("scripts/check_*.py", "scripts/ci/check_*.py", "scripts/ci/check_*.sh")


def _discover_scanners() -> set[str]:
    found: set[str] = set()
    for pat in _DISCOVERY:
        for p in glob.glob(str(REPO / pat)):
            found.add(str(Path(p).relative_to(REPO)))
    return found


def evaluate_registries_meta() -> tuple[bool, list[str]]:
    failures: list[str] = []
    catalog = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    scanners = catalog.get("scanners") or []
    cataloged: dict[str, dict] = {}
    for entry in scanners:
        script = str((entry or {}).get("script") or "")
        if not script:
            failures.append(f"registries.yaml: scanner entry missing 'script': {entry!r}")
            continue
        cataloged[script] = entry

    # (a) every cataloged script must exist on disk
    for script in cataloged:
        if not (REPO / script).exists():
            failures.append(f"cataloged scanner does not exist on disk: {script}")

    # (b) register-before-use for gates: every discovered governance scanner must be cataloged
    discovered = _discover_scanners()
    for script in sorted(discovered):
        if script not in cataloged:
            failures.append(
                f"UNCATALOGED governance scanner: {script} — add it to contracts/registries.yaml "
                f"with an enforcement class before merge (register-before-use applies to the gates too)."
            )

    # (c) no pr_gate goes dark: every pr_gate scanner must be an executed step in tests.yml
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8") if CI_WORKFLOW.exists() else ""
    for script, entry in sorted(cataloged.items()):
        if str(entry.get("enforcement")) != "pr_gate":
            continue
        base = Path(script).name
        if base not in ci_text:
            failures.append(
                f"DARK pr_gate scanner: {script} is classed pr_gate but does not appear as a step "
                f"in .github/workflows/tests.yml — wire it in, or reclassify its enforcement."
            )

    return (not failures), failures


def main(argv: list[str] | None = None) -> int:
    ok, failures = evaluate_registries_meta()
    if ok:
        cat = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
        n = len(cat.get("scanners") or [])
        pr = sum(1 for s in (cat.get("scanners") or []) if s.get("enforcement") == "pr_gate")
        print(f"registries-meta-gate: passed | {n} scanners cataloged, {pr} pr_gate all wired into CI")
        return 0
    print("registries-meta-gate: FAILED", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
