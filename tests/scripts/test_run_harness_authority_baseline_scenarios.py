"""Gate-teeth tests for the control-plane / reveal-terminal scenario sets.

These prove the ``--scenario-set ... --check`` path is a REAL executable gate
(plan §14.A Task 1): it must pass on the tracked fixtures AND fail loudly on a
synthetic drift / leak row, and error (exit 2) on a missing fixture. A gate
that can only return 0 is a no-op closure stand-in — exactly what the plan's
anti-gaming rules forbid.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = PROJECT_ROOT / "scripts" / "run_harness_authority_baseline.py"

_spec = importlib.util.spec_from_file_location("_harness_baseline", _SCRIPT)
assert _spec and _spec.loader
harness = importlib.util.module_from_spec(_spec)
# Register before exec so dataclasses defined in the module can resolve their
# own __module__ during class processing.
sys.modules[_spec.name] = harness
_spec.loader.exec_module(harness)


def test_control_plane_real_fixtures_pass() -> None:
    rows = harness._load_jsonl(
        PROJECT_ROOT / "tests" / "fixtures" / "control_plane_hard_cases.jsonl"
    )
    failures = asyncio.run(harness._run_control_plane_scenarios(rows))
    assert failures == [], failures


def test_control_plane_detects_scene_drift() -> None:
    # Active MCQ submission must resolve to mcq_grading; assert the gate fails
    # when a row claims it should be question_review (synthetic drift).
    bad = [
        {
            "name": "synthetic_drift",
            "user_message": "B",
            "metadata": {
                "question_followup_context": {
                    "question_id": "q1",
                    "question_type": "mcq",
                    "question": "下列哪个选项正确？",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                }
            },
            "expected": {"scene": "question_review"},
        }
    ]
    failures = asyncio.run(harness._run_control_plane_scenarios(bad))
    assert failures, "scene drift must be detected"


def test_reveal_real_fixtures_pass() -> None:
    rows = harness._load_jsonl(
        PROJECT_ROOT / "tests" / "fixtures" / "reveal_terminal_hard_cases.jsonl"
    )
    failures = harness._run_reveal_terminal_scenarios(rows)
    assert failures == [], failures


def test_reveal_gate_fails_if_redactor_regresses(monkeypatch) -> None:
    # End-to-end teeth: drive the real _run_reveal_terminal_scenarios but
    # monkeypatch the redactor to a no-op, simulating a redaction regression.
    # The gate MUST then report the surviving hidden key as a failure.
    from deeptutor.services.question_followup import PUBLIC_HIDDEN_PAYLOAD_KEYS

    hidden_key = PUBLIC_HIDDEN_PAYLOAD_KEYS[0]
    leak_row = [{"name": "synthetic_leak", "metadata": {"nested": {hidden_key: "SECRET"}}}]

    import deeptutor.api.routers.unified_ws as ws

    monkeypatch.setattr(ws, "_redact_metadata_for_public", lambda md: md)
    failures = harness._run_reveal_terminal_scenarios(leak_row)
    assert failures, "a no-op redactor must trip the reveal gate"
    assert "synthetic_leak" in failures[0]


def test_reveal_gate_passes_with_real_redactor() -> None:
    # Same leak row, real redactor -> no failure (the redactor strips it).
    leak_row = [{"name": "synthetic_leak", "metadata": {"nested": {"correct_answer": "B"}}}]
    assert harness._run_reveal_terminal_scenarios(leak_row) == []


def test_missing_fixture_returns_2() -> None:
    rc = asyncio.run(harness._run_scenario_set("control_plane_hard_cases", check=True))
    assert rc == 0
    # Point FIXTURES_DIR at an empty temp location to force the missing-fixture path.
    orig = harness.FIXTURES_DIR
    try:
        harness.FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "__nonexistent__"
        rc_missing = asyncio.run(
            harness._run_scenario_set("control_plane_hard_cases", check=True)
        )
        assert rc_missing == 2
    finally:
        harness.FIXTURES_DIR = orig
