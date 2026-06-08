"""D-class: occurrence_timeline — error time-series in weak_points.

Each weak_point must carry occurrence_timeline: list[{event_id, observed_at,
question_id, turn_id}] ordered oldest-first. This enables the student-facing
long-term report to show WHEN a mistake recurred, not just that it did.

Invariants:
- occurrence_timeline length == len(supporting_event_ids)
- entries ordered by observed_at asc (chronological)
- single-event candidate also carries a 1-element timeline
- no duplicate event_id in timeline for the same weak_point
"""
from __future__ import annotations

from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth

CONCEPT = "timeline_concept"
ERR = "near_synonym_not_accepted"


def _evt(event_id: str, *, qid: str = "q001", ts: str, turn_id: str | None = None) -> LearnerStateEvent:
    payload = {
        "event_type": "learning_evidence",
        "turn_id": turn_id or f"t_{event_id}",
        "question_id": qid,
        "error_events": [
            {"error_code": ERR, "concept_tag": CONCEPT, "evidence": "answer span", "diagnosis": ""},
        ],
        "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
    }
    return LearnerStateEvent(
        event_id=event_id,
        user_id="qa_timeline",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=ts,
        payload_json=payload,
    )


# ── D1-A: N≥2 events → weak_point must have occurrence_timeline with all entries ──────────────

def test_weak_point_carries_occurrence_timeline_for_repeated_errors() -> None:
    """occurrence_timeline must appear on L1_repeated weak_points with all event entries."""
    e1 = _evt("ev1", ts="2026-06-01T10:00:00+08:00", qid="q001")
    e2 = _evt("ev2", ts="2026-06-03T10:00:00+08:00", qid="q002")
    e3 = _evt("ev3", ts="2026-06-05T10:00:00+08:00", qid="q003")
    result = synthesize_learning_truth(events=[e1, e2, e3])

    weak = result.get("weak_points") or []
    assert weak, "expected at least one weak_point from 3 identical errors"
    found = next((w for w in weak if w["concept_id"] == CONCEPT and w["error_code"] == ERR), None)
    assert found is not None, f"weak_point {CONCEPT}/{ERR} not found"

    timeline = found.get("occurrence_timeline")
    assert isinstance(timeline, list), "occurrence_timeline must be a list"
    assert len(timeline) == 3, f"expected 3 timeline entries, got {len(timeline)}"

    # entries ordered oldest-first (chronological)
    dates = [e["observed_at"] for e in timeline]
    assert dates == sorted(dates), f"occurrence_timeline must be sorted asc: {dates}"

    # each entry has the required fields
    for entry in timeline:
        assert "event_id" in entry
        assert "observed_at" in entry
        assert "question_id" in entry
        assert "turn_id" in entry


def test_occurrence_timeline_maps_question_ids_correctly() -> None:
    """Each timeline entry must map to the correct question_id and turn_id."""
    e1 = _evt("ev-a", ts="2026-06-01T08:00:00+08:00", qid="qA", turn_id="turnA")
    e2 = _evt("ev-b", ts="2026-06-02T08:00:00+08:00", qid="qB", turn_id="turnB")
    result = synthesize_learning_truth(events=[e1, e2])

    weak = result.get("weak_points") or []
    found = next((w for w in weak if w["concept_id"] == CONCEPT), None)
    assert found is not None

    tl = found["occurrence_timeline"]
    by_event = {e["event_id"]: e for e in tl}
    assert by_event["ev-a"]["question_id"] == "qA"
    assert by_event["ev-a"]["turn_id"] == "turnA"
    assert by_event["ev-b"]["question_id"] == "qB"
    assert by_event["ev-b"]["turn_id"] == "turnB"


# ── D1-B: single-event candidate must also carry a 1-element timeline ─────────────────────────

def test_single_event_observed_candidate_carries_one_element_timeline() -> None:
    """observed_candidates (L0) from a single event must also have occurrence_timeline."""
    e1 = _evt("ev-solo", ts="2026-06-01T10:00:00+08:00", qid="qSolo")
    result = synthesize_learning_truth(events=[e1])

    # single event → L0_observed (not a weak_point yet)
    observed = result.get("observed_candidates") or []
    found = next((c for c in observed if c.get("concept_id") == CONCEPT), None)
    assert found is not None, "L0 observed candidate must exist for a single error event"

    timeline = found.get("occurrence_timeline")
    assert isinstance(timeline, list) and len(timeline) == 1, \
        f"single-event candidate must have 1-element occurrence_timeline, got: {timeline}"
    entry = timeline[0]
    assert entry["event_id"] == "ev-solo"
    assert entry["question_id"] == "qSolo"


# ── D1-C: no duplicate event_ids in timeline ─────────────────────────────────────────────────

def test_occurrence_timeline_has_no_duplicate_event_ids() -> None:
    """Event deduplication must not produce duplicate entries in occurrence_timeline."""
    e1 = _evt("uniq-1", ts="2026-06-01T10:00:00+08:00")
    e2 = _evt("uniq-2", ts="2026-06-02T10:00:00+08:00")
    result = synthesize_learning_truth(events=[e1, e2])

    for wp in (result.get("weak_points") or []) + (result.get("observed_candidates") or []):
        tl = wp.get("occurrence_timeline") or []
        ids = [e["event_id"] for e in tl]
        assert len(ids) == len(set(ids)), f"duplicate event_ids in timeline: {ids}"
