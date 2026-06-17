"""Import smoke guardrail against cold-path NameError (F821) recurrence.

A class of NameError bugs reached main because runtime-critical imports were
missing (e.g. ``import os`` in the Anthropic/Cohere provider path, ``from
pathlib import Path`` in solve.py, ``import sys`` in the question_extractor
CLI). These symbols are only referenced on cold paths that the smoke suite did
not exercise, so the modules imported fine while the offending lines stayed one
call away from ``NameError``.

This test imports the affected modules and asserts that each previously-missing
symbol is now bound in the module namespace. It is intentionally cheap: a plain
``import`` already proves the top-level import block is sound, and the symbol
assertions pin the exact names so a future deletion of an import is caught here
rather than in production.

The CI ruff F821/F811 gate (.github/workflows/tests.yml) is the systematic,
single-point defense for the whole class; this test is the belt-and-suspenders
runtime guardrail focused on the concrete instances that shipped.
"""

from __future__ import annotations

import importlib


def test_cloud_provider_imports_os() -> None:
    """Anthropic/Cohere provider paths call ``os.getenv`` for API keys."""
    module = importlib.import_module("deeptutor.services.llm.cloud_provider")
    assert hasattr(module, "os"), "cloud_provider must bind `os` (os.getenv on provider paths)"


def test_solve_router_imports_path() -> None:
    """solve.py constructs ``Path(output_dir_str)`` on the artifact path."""
    module = importlib.import_module("deeptutor.api.routers.solve")
    assert hasattr(module, "Path"), "solve router must bind `Path` (pathlib)"


def test_question_extractor_imports_sys() -> None:
    """question_extractor CLI calls ``sys.exit`` in its __main__ path."""
    module = importlib.import_module("deeptutor.tools.question.question_extractor")
    assert hasattr(module, "sys"), "question_extractor must bind `sys` (sys.exit in CLI)"


def test_release_gate_imports_path() -> None:
    """release_gate annotates ``supply_root: str | Path`` (must resolve)."""
    module = importlib.import_module("deeptutor.services.observability.release_gate")
    assert hasattr(module, "Path"), "release_gate must bind `Path` for its annotations"
