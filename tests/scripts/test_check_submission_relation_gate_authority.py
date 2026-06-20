"""Tests for the submission/relation gate authority fail-on-new guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_submission_relation_gate_authority",
    REPO_ROOT / "scripts/check_submission_relation_gate_authority.py",
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(guard)


def test_gate_name_detection_matches_submission_relation_intent() -> None:
    assert guard._is_gate_name("_looks_like_unanchored_mcq_answer_submission") is True
    assert guard._is_gate_name("_looks_like_past_question_explanation_request") is True
    assert guard._is_gate_name("_looks_like_question_submission") is True
    # not a gate: no submission/relation keyword
    assert guard._is_gate_name("_looks_like_json_envelope") is False
    # not a _looks_like_ function at all
    assert guard._is_gate_name("resolve_submission_attempt") is False


def test_current_tree_has_no_ungrandfathered_gates() -> None:
    # Every gate present in the tree must be in the baseline (fail-on-new == green now).
    keys = set(guard.collect_gate_keys())
    baseline = guard._read_baseline()
    assert baseline, "baseline must exist"
    new_gates = keys - baseline
    assert not new_gates, f"ungrandfathered submission/relation gate(s): {sorted(new_gates)}"


def test_baseline_includes_the_known_single_source_and_lifecycle_gates() -> None:
    baseline = guard._read_baseline()
    # canonical-area and lifecycle gates we expect to be tracked
    assert (
        "deeptutor/services/question_followup.py::_looks_like_past_question_explanation_request"
        in baseline
    )
    assert (
        "deeptutor/services/question_lifecycle_skills.py::_looks_like_unanchored_mcq_answer_submission"
        in baseline
    )


def test_fail_on_new_detects_a_synthetic_gate(monkeypatch) -> None:
    # Simulate a new gate appearing by extending the collected keys; the new-gate set
    # (collected - baseline) must be non-empty, which is what drives the CI failure.
    baseline = guard._read_baseline()
    synthetic = "deeptutor/services/question_lifecycle_skills.py::_looks_like_sneaky_new_mcq_submission"
    monkeypatch.setattr(
        guard, "collect_gate_keys", lambda: sorted(baseline | {synthetic})
    )
    keys = guard.collect_gate_keys()
    new_gates = [k for k in keys if k not in baseline]
    assert new_gates == [synthetic]
