"""D-class: student-visible long-term analytics in the learning report.

Tests the new `long_term_analytics` top-level section of the read model:
  - recurrent_errors: error concepts that appear N>=2 times (derived from
    weak_points.occurrence_timeline — zero new DB reads)
  - progression_summary: trend_direction, active_weak_count, recurrent_error_count

All assertions are read-only projections; no writes occur.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from deeptutor.services.learner_state.learning_report_read_model import _build_long_term_analytics


# ── helpers ──────────────────────────────────────────────────────────────────

def _wp(concept: str, error: str, occurrences: list[dict]) -> dict:
    return {
        "concept_id": concept,
        "error_code": error,
        "occurrence_timeline": occurrences,
    }


def _occ(event_id: str, ts: str, qid: str = "q001") -> dict:
    return {"event_id": event_id, "observed_at": ts, "question_id": qid, "turn_id": f"t_{event_id}"}


# ── D2-A: recurrent_errors lists concepts with N>=2 occurrences ──────────────

def test_recurrent_errors_includes_concepts_appearing_twice_or_more() -> None:
    """Only concepts with 2+ occurrences should appear in recurrent_errors."""
    brain = {
        "weak_points": [
            _wp("waterproof", "missing_term", [
                _occ("e1", "2026-06-01T10:00:00+08:00"),
                _occ("e2", "2026-06-03T10:00:00+08:00"),
            ]),
            _wp("formwork", "wrong_load", [
                _occ("e3", "2026-06-02T10:00:00+08:00"),
            ]),
        ]
    }
    analytics = _build_long_term_analytics(brain)
    recurrent = analytics["recurrent_errors"]
    ids = [(r["concept_id"], r["error_code"]) for r in recurrent]

    assert ("waterproof", "missing_term") in ids, "2-occurrence concept must be in recurrent_errors"
    assert ("formwork", "wrong_load") not in ids, "1-occurrence concept must NOT be in recurrent_errors"


def test_recurrent_error_has_correct_occurrence_count_and_dates() -> None:
    brain = {
        "weak_points": [
            _wp("concrete", "missing_spec", [
                _occ("e1", "2026-05-20T08:00:00+08:00", qid="qA"),
                _occ("e2", "2026-06-01T08:00:00+08:00", qid="qB"),
                _occ("e3", "2026-06-07T08:00:00+08:00", qid="qC"),
            ]),
        ]
    }
    analytics = _build_long_term_analytics(brain)
    recurrent = analytics["recurrent_errors"]
    assert recurrent, "expected non-empty recurrent_errors"

    entry = recurrent[0]
    assert entry["occurrence_count"] == 3
    assert entry["first_seen_at"] == "2026-05-20T08:00:00+08:00"
    assert entry["last_seen_at"] == "2026-06-07T08:00:00+08:00"


# ── D2-B: progression_summary fields ─────────────────────────────────────────

def test_progression_summary_counts_active_weak_and_recurrent() -> None:
    brain = {
        "weak_points": [
            _wp("c1", "err", [_occ("a", "2026-06-01T00:00:00"), _occ("b", "2026-06-02T00:00:00")]),
            _wp("c2", "err", [_occ("c", "2026-06-01T00:00:00")]),
            _wp("c3", "err", [_occ("d", "2026-06-01T00:00:00"), _occ("e", "2026-06-03T00:00:00"),
                               _occ("f", "2026-06-05T00:00:00")]),
        ]
    }
    analytics = _build_long_term_analytics(brain)
    ps = analytics["progression_summary"]
    assert ps["active_weak_count"] == 3
    assert ps["recurrent_error_count"] == 2  # c1 and c3 have >=2 occurrences


def test_progression_summary_trend_direction_is_valid_value() -> None:
    for brain in [
        {"weak_points": []},
        {"weak_points": [_wp("x", "e", [_occ("a", "2026-06-01T00:00:00")])]},
        {"weak_points": [_wp("x", "e", [_occ("a", "2026-06-01T00:00:00"),
                                          _occ("b", "2026-06-03T00:00:00")])]},
    ]:
        analytics = _build_long_term_analytics(brain)
        td = analytics["progression_summary"]["trend_direction"]
        assert td in {"improving", "stable", "declining"}, f"invalid trend_direction: {td}"


# ── D2-C: empty brain produces safe empty results ────────────────────────────

def test_empty_learning_brain_produces_empty_analytics() -> None:
    analytics = _build_long_term_analytics({})
    assert analytics["recurrent_errors"] == []
    assert analytics["progression_summary"]["active_weak_count"] == 0
    assert analytics["progression_summary"]["recurrent_error_count"] == 0
    assert analytics["progression_summary"]["trend_direction"] == "improving"


# ── D2-D: top-level report exposes long_term_analytics key ───────────────────

def test_build_long_term_analytics_is_importable_and_returns_dict() -> None:
    """Smoke test: function is importable and returns correct shape."""
    result = _build_long_term_analytics({"weak_points": []})
    assert "recurrent_errors" in result
    assert "progression_summary" in result
    ps = result["progression_summary"]
    assert "trend_direction" in ps
    assert "active_weak_count" in ps
    assert "recurrent_error_count" in ps
