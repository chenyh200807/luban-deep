"""Tests for the QTPK import-allowlist guard (QTPK physical extraction, S0).

Strategy mirrors ``tests/scripts/test_check_control_plane_writer_allowlist.py``:
load the guard script as a module and feed synthetic source strings to its
internal ``evaluate_qtpk_imports(source, rel)`` so each case is alias-proof and
free of docstring/comment false-positives. The live QTPK module's actual import
surface is asserted clean via ``main(["--check"])`` returning exit 0.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_guard():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_qtpk_import_allowlist.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_qtpk_import_allowlist_under_test", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHK = _load_guard()

_REL = "deeptutor/services/question_turn_policy.py"


def _msgs(violations) -> str:
    return "\n".join(violations)


# --- Legal imports pass --------------------------------------------------------
def test_canonical_resolver_imports_are_clean() -> None:
    source = (
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from typing import Any\n"
        "from deeptutor.services.semantic_router import resolve_question_semantic_routing\n"
        "from deeptutor.services.semantic_router import apply_active_object_transition\n"
        "from deeptutor.services.question_lifecycle_skills import "
        "resolve_question_lifecycle_scene_decision\n"
        "from deeptutor.services import active_object_builder\n"
        "from deeptutor.services.question_followup import "
        "normalize_question_followup_context\n"
    )
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations == [], _msgs(violations)


def test_active_object_builder_module_import_is_clean() -> None:
    source = "from deeptutor.services.active_object_builder import build_active_object\n"
    assert CHK.evaluate_qtpk_imports(source, _REL) == []


def test_allowed_module_grading_named_imports_are_clean() -> None:
    # Regression for the substring bug: a forbidden substring in the *imported
    # name* (not the module path) of an ALLOWED canonical module must NOT be
    # flagged. The forbidden-substring red line is about the MODULE the import
    # pulls from, not the symbol names that module legitimately exports. These
    # three grading-named predicates are real exports of the allowed
    # ``question_lifecycle_skills`` module that QTPK must be able to forward to.
    source = (
        "from deeptutor.services.question_lifecycle_skills import (\n"
        "    looks_like_free_text_mcq_grading_request,\n"
        "    mcq_grading_context_from_full_submission,\n"
        "    case_grading_context_from_full_submission,\n"
        ")\n"
    )
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations == [], _msgs(violations)


def test_allowed_question_followup_grading_named_import_is_clean() -> None:
    # Same regression on the ``question_followup`` allowed module: an imported
    # name carrying a forbidden substring must not trip the red line when the
    # source module is on the allowlist.
    source = (
        "from deeptutor.services.question_followup import "
        "requested_question_item_index\n"
    )
    assert CHK.evaluate_qtpk_imports(source, _REL) == []


# --- Forbidden imports are rejected (exit-2 substrings) -------------------------
def test_llm_client_import_is_forbidden() -> None:
    source = "from deeptutor.services.llm_client import LLMClient\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations, "LLM client import must be flagged"
    assert "FORBIDDEN" in _msgs(violations)
    assert "llm" in _msgs(violations)


def test_grading_kernel_import_is_forbidden() -> None:
    source = "from deeptutor.services.construction_grading.kernel import grade\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "grading" in _msgs(violations)


def test_rag_import_is_forbidden() -> None:
    source = "from deeptutor.services.rag.pipeline import retrieve\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "FORBIDDEN" in _msgs(violations)


def test_learner_state_import_is_forbidden() -> None:
    source = "from deeptutor.services.learner_state import LearnerState\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "learner" in _msgs(violations)


def test_reveal_import_is_forbidden() -> None:
    source = "from deeptutor.services.reveal_policy import reveal_reference\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "reveal" in _msgs(violations)


def test_terminal_result_assembler_import_is_forbidden() -> None:
    source = "from deeptutor.core.terminal_result_assembler import assemble\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "terminal" in _msgs(violations)


def test_stream_bus_import_is_forbidden() -> None:
    source = "from deeptutor.core.stream_bus import StreamBus\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations


def test_orchestrator_import_is_forbidden() -> None:
    source = "from deeptutor.runtime.orchestrator import Orchestrator\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "orchestrator" in _msgs(violations)


def test_turn_runtime_import_is_forbidden() -> None:
    source = "from deeptutor.services.session.turn_runtime import TurnRuntime\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "turn_runtime" in _msgs(violations)


def test_plain_import_form_of_forbidden_module_is_flagged() -> None:
    # ``import deeptutor.services.session.turn_runtime`` (not from-import).
    source = "import deeptutor.services.session.turn_runtime\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "turn_runtime" in _msgs(violations)


# --- Fail-closed on an unreviewed internal import ------------------------------
def test_unreviewed_deeptutor_import_is_fail_closed() -> None:
    source = "from deeptutor.services.some_new_helper import thing\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations, "unreviewed deeptutor import must be fail-closed"
    assert "UNREVIEWED" in _msgs(violations)


def test_relative_import_is_fail_closed() -> None:
    source = "from . import sibling_module\n"
    violations = CHK.evaluate_qtpk_imports(source, _REL)
    assert violations
    assert "UNREVIEWED" in _msgs(violations)


# --- main(--check) returns exit codes 0 (clean) / 2 (forbidden) ----------------
def test_main_check_on_live_qtpk_module_is_clean() -> None:
    assert CHK.main(["--check"]) == 0


def test_synthetic_forbidden_source_yields_violations_for_exit_2_path() -> None:
    # The live tree is clean (exit 0); a forbidden synthetic source proves the
    # exit-2 path is the one reached when a violation exists.
    forbidden = "from deeptutor.services.llm_client import LLMClient\n"
    assert CHK.evaluate_qtpk_imports(forbidden, _REL) != []
