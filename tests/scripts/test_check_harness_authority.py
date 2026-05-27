"""Tests for the AST-based harness authority guard (9+ roadmap H5).

Proves the guard detects legacy scene-detector access *semantically* (actual
import bindings / attribute-access calls, alias-proof) rather than by text —
and does NOT false-positive on docstrings/comments that merely mention a symbol,
which the prior line-regex would have flagged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_guard():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_harness_authority.py"
    spec = importlib.util.spec_from_file_location("check_harness_authority_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # register so @dataclass module lookup resolves
    spec.loader.exec_module(module)
    return module


CHK = _load_guard()


def test_aliased_from_import_is_caught() -> None:
    source = (
        "from deeptutor.tutorbot.teaching_modes import "
        "detect_construction_exam_scene as _d\n"
        "def f(ctx):\n    return _d(ctx.user_message)\n"
    )
    violations = CHK._scan_shell_file_ast("shell.py", source)
    assert violations and "detect_construction_exam_scene" in violations[0]


def test_aliased_module_attribute_call_is_caught() -> None:
    source = (
        "import deeptutor.tutorbot.teaching_modes as tm\n"
        "def f(ctx):\n    return tm.detect_construction_exam_scene(ctx.user_message)\n"
    )
    violations = CHK._scan_shell_file_ast("shell.py", source)
    assert violations and "detect_construction_exam_scene" in violations[0]


def test_dotted_module_attribute_call_is_caught() -> None:
    source = (
        "import deeptutor.tutorbot.teaching_modes\n"
        "def f(ctx):\n"
        "    return deeptutor.tutorbot.teaching_modes."
        "get_construction_exam_skill_instruction('general')\n"
    )
    violations = CHK._scan_shell_file_ast("shell.py", source)
    assert violations and "get_construction_exam_skill_instruction" in violations[0]


def test_docstring_or_comment_mention_is_not_a_false_positive() -> None:
    # The prior line-regex would flag these mentions; the AST guard must not.
    source = (
        '"""Do NOT call detect_construction_exam_scene; read '
        'question_lifecycle_scene instead."""\n'
        "# get_construction_exam_skill_instruction is legacy and forbidden here.\n"
        "def f(ctx):\n    return ctx.metadata.get('question_lifecycle_scene')\n"
    )
    assert CHK._scan_shell_file_ast("shell.py", source) == []


def test_clean_authority_read_passes() -> None:
    source = "def f(ctx):\n    return ctx.metadata.get('question_lifecycle_scene')\n"
    assert CHK._scan_shell_file_ast("shell.py", source) == []


def test_real_execution_shells_pass_the_guard() -> None:
    # Post-P0.2 the shells read the authority and import no legacy detector.
    assert CHK._scan_shell_rejudgement() == []
