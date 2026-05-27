#!/usr/bin/env python3
"""Static guard + inventory for model-selection authority (harness Deferred D5).

D5's goal is "换模型只改 catalog/config 一处" (single-point model swap). The full
consolidation is gated. What is **true and guardable today** is narrower:

- **Single default authority**: the default LLM model/provider is declared in
  exactly one place — ``deeptutor/config/defaults.py`` (``DEFAULT_LLM_MODEL`` /
  ``DEFAULT_LLM_PROVIDER``). This guard fails if a second default declaration
  appears anywhere, preventing a competing default-config authority from
  creeping in.

Model-id *string literals* are still scattered across provider adapters, pricing
tables and a few business modules. That scatter is the D5 *consolidation debt* —
NOT something this guard pretends is already single-point. ``--inventory`` maps
that debt (deterministic report) so the future gated D5 consolidation has a
ground-truth surface to work from.

Usage::

    python scripts/check_model_authority.py            # guard (gate mode)
    python scripts/check_model_authority.py --inventory # model-id debt map

Guard exits non-zero on a second default authority; ``--inventory`` always
exits 0 (informational).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "deeptutor"

# Single default-selection authority.
DEFAULT_AUTHORITY_FILE = "deeptutor/config/defaults.py"
_DEFAULT_DECL_RE = re.compile(r"^(DEFAULT_LLM_MODEL|DEFAULT_LLM_PROVIDER)\s*=", re.MULTILINE)

# Model-id literal shapes, for the consolidation-debt inventory (informational).
_MODEL_ID_RE = re.compile(
    r"\"("
    r"gpt-[0-9][0-9a-z.\-]*"
    r"|claude-[0-9a-z.\-]+"
    r"|deepseek[0-9a-z.\-/]*"
    r"|qwen[0-9a-z.\-]*"
    r"|gemini-[0-9a-z.\-]+"
    r"|o[0-9]-[a-z0-9\-]+"
    r")\"",
    re.IGNORECASE,
)

# Directories whose model-id literals are *expected* (adapters / pricing / config).
_EXPECTED_LITERAL_PREFIXES = (
    "deeptutor/tutorbot/providers/",
    "deeptutor/services/llm/",
    "deeptutor/config/",
    "deeptutor/services/config/",
    "deeptutor/agents/research/utils/token_tracker.py",  # pricing table
    "deeptutor/logging/",
)


def _iter_python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _check_single_default_authority(files: list[Path]) -> list[str]:
    violations: list[str] = []
    declaring_files: list[str] = []
    for path in files:
        rel = str(path.relative_to(PROJECT_ROOT))
        if _DEFAULT_DECL_RE.search(path.read_text(encoding="utf-8")):
            declaring_files.append(rel)
    if DEFAULT_AUTHORITY_FILE not in declaring_files:
        violations.append(
            f"default LLM model/provider authority not found in {DEFAULT_AUTHORITY_FILE}"
        )
    extra = sorted(set(declaring_files) - {DEFAULT_AUTHORITY_FILE})
    if extra:
        violations.append(
            "default LLM model/provider declared outside the single authority "
            f"{DEFAULT_AUTHORITY_FILE}: {extra} — consolidate to one place"
        )
    return violations


def _is_expected(rel: str) -> bool:
    return any(rel == prefix or rel.startswith(prefix) for prefix in _EXPECTED_LITERAL_PREFIXES)


def _inventory(files: list[Path]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    expected: dict[str, list[str]] = {}
    business: dict[str, list[str]] = {}
    for path in files:
        rel = str(path.relative_to(PROJECT_ROOT))
        hits = sorted({m.group(1) for m in _MODEL_ID_RE.finditer(path.read_text(encoding="utf-8"))})
        if not hits:
            continue
        (expected if _is_expected(rel) else business)[rel] = hits
    return expected, business


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="print the model-id consolidation-debt map (informational, always exits 0)",
    )
    args = parser.parse_args()

    files = _iter_python_files()

    if args.inventory:
        expected, business = _inventory(files)
        print("== model-id literal inventory (D5 consolidation debt) ==")
        print("\n[expected: provider adapters / pricing / config]")
        for rel in sorted(expected):
            print(f"  {rel}: {', '.join(expected[rel])}")
        print("\n[business/other: candidates to route through config/catalog in D5]")
        if business:
            for rel in sorted(business):
                print(f"  {rel}: {', '.join(business[rel])}")
        else:
            print("  (none)")
        return 0

    violations = _check_single_default_authority(files)
    if violations:
        print("model authority guard: FAIL", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    print(f"model authority guard: OK (single default authority in {DEFAULT_AUTHORITY_FILE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
