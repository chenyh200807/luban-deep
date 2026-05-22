"""Batch B Task 4: three-layer learning state projection.

Pins ``project_three_layer_learning_state`` — a focused helper that reads
``learner_memory_events.learning_evidence`` and emits the three projection
arrays (knowledge_state / ability_state / behavior_state) the plan promises.
The module is read-only and lives next to ``learning_synthesis`` so the
synthesis function can compose it without growing past 1000 lines.

Hard rules from the plan:

- No fabrication: states must be backed by ``evidence_refs``.
- Cluster key for recurrence: ``(primary_knowledge_node_id, ability_dimension,
  error_code)``.
- Conversation_synthesis events MAY influence still_confused / explained
  but MUST NOT prove mastery on their own.
- Keyword-only (granularity=keyword_only) rubric items downgrade to a
  lower-confidence observation, never "stable" / "weak".
- Legacy evidence (no rubric, no ability_dimension) is tolerated — it
  still gets projected but with ``legacy=True`` and never produces a
  strong state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from deeptutor.services.learner_state.learning_state_projection import (
    project_three_layer_learning_state,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: float) -> str:
    delta = timedelta(days=days_ago)
    return (datetime.now(_TZ) - delta).isoformat()


def _case_event(
    *,
    event_id: str,
    days_ago: float,
    knowledge_node_id: str = "1A412010",
    ability_dimension: str = "code_application",
    error_code: str = "E02",
    hit: bool = False,
    granularity: str = "scoring_point",
    rubric_mode: str = "curated_rubric",
    score_ratio: float = 0.0,
    learning_signal_type: str = "",
) -> LearnerStateEvent:
    payload = {
        "event_type": "learning_evidence",
        "evidence_source": "construction_grading",
        "question_id": f"q_{event_id}",
        "question_stem": "测试题",
        "user_answer": "A",
        "correct_answer": "B",
        "score_awarded": 1 if score_ratio >= 1 else 0,
        "max_score": 1,
        "rubric": {
            "rubric_mode": rubric_mode,
            "granularity": granularity,
            "scoring_points": [
                {
                    "point_id": f"sp_{event_id}",
                    "label": "测试采分点",
                    "knowledge_node_id": knowledge_node_id,
                    "ability_dimension": ability_dimension,
                }
            ],
            "scoring_point_hits": [
                {
                    "point_id": f"sp_{event_id}",
                    "hit": hit,
                    "awarded_score": 1 if hit else 0,
                    "error_code": error_code,
                }
            ],
        },
        "error_events": [
            {"error_code": error_code, "concept_tag": knowledge_node_id, "diagnosis": "test"}
        ],
        "next_training_signal": {"concept": knowledge_node_id, "focus": "test", "mode": "practice"},
    }
    if learning_signal_type:
        payload["learning_signal_type"] = learning_signal_type
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json=payload,
    )


def _conv_event(
    *,
    event_id: str,
    days_ago: float,
    signal_type: str = "still_confused",
    knowledge_node_id: str = "1A412010",
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="conversation_synthesis",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "conversation_synthesis",
            "learning_signal_type": signal_type,
            "next_training_signal": {"concept": knowledge_node_id},
        },
    )


# ─── Top-level shape ───────────────────────────────────────────────────────


def test_empty_events_produce_empty_projection_with_source_status() -> None:
    """Authority transparency: even when there's no evidence, the read
    surface MUST identify itself as a projection of the ledger so callers
    cannot mistake it for a competing truth source."""
    projection = project_three_layer_learning_state(events=[])

    assert projection["knowledge_state"] == []
    assert projection["ability_state"] == []
    assert projection["behavior_state"] == []
    assert projection["source_status"]["authority"] == "learner_memory_events.learning_evidence"
    assert projection["source_status"]["model"] == "rule_based_v1"


# ─── Knowledge state ───────────────────────────────────────────────────────


def test_single_negative_case_event_is_observed_not_weak() -> None:
    """One miss is an observation, not a verdict. Hard rule: never elevate
    a single piece of evidence to ``weak``."""
    projection = project_three_layer_learning_state(
        events=[_case_event(event_id="e1", days_ago=0)]
    )

    knowledge = projection["knowledge_state"][0]
    assert knowledge["node_id"] == "1A412010"
    assert knowledge["state"] == "observed"
    assert knowledge["evidence_count"] == 1
    assert knowledge["evidence_refs"] == ["e1"]


def test_repeated_negative_case_events_become_weak() -> None:
    """Two negatives on the same (node, ability_dimension, error_code)
    cluster promote to ``weak``."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="e1", days_ago=4),
            _case_event(event_id="e2", days_ago=0),
        ]
    )

    knowledge = projection["knowledge_state"][0]
    assert knowledge["node_id"] == "1A412010"
    assert knowledge["state"] == "weak"
    assert knowledge["evidence_count"] == 2
    assert sorted(knowledge["evidence_refs"]) == ["e1", "e2"]


def test_negative_then_positive_marks_improving() -> None:
    """A miss followed by a recent correct attempt is the canonical
    improving signal. Time order matters: the positive must be the more
    recent event."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="old_miss", days_ago=5),
            _case_event(event_id="new_correct", days_ago=0, hit=True, score_ratio=1.0),
        ]
    )

    knowledge = projection["knowledge_state"][0]
    assert knowledge["state"] == "improving"


def test_repeated_positive_recent_is_stable() -> None:
    """Two recent corrects on the same node make ``stable``."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="c1", days_ago=2, hit=True, score_ratio=1.0),
            _case_event(event_id="c2", days_ago=0, hit=True, score_ratio=1.0),
        ]
    )

    knowledge = projection["knowledge_state"][0]
    assert knowledge["state"] == "stable"


def test_knowledge_state_label_resolves_via_graph_seed_when_known() -> None:
    """When the node_id is in the seed graph, label MUST resolve to the
    taxonomy label so the UI does not display raw codes like 1A412010."""
    projection = project_three_layer_learning_state(
        events=[_case_event(event_id="e1", days_ago=0, knowledge_node_id="1A412010")]
    )

    assert projection["knowledge_state"][0]["label"]
    # Real taxonomy label is "结构工程材料"; just assert non-empty + Chinese chars.
    assert any("一" <= ch <= "鿿" for ch in projection["knowledge_state"][0]["label"])


# ─── Ability state ─────────────────────────────────────────────────────────


def test_ability_dimension_aggregates_across_concepts() -> None:
    """Two distinct knowledge nodes that share the same ability_dimension
    must aggregate to a single ability_state entry."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="e1", days_ago=2, knowledge_node_id="1A412010"),
            _case_event(event_id="e2", days_ago=0, knowledge_node_id="1A413040"),
        ]
    )

    ability_entries = [a for a in projection["ability_state"] if a["dimension"] == "code_application"]
    assert len(ability_entries) == 1
    entry = ability_entries[0]
    assert entry["state"] == "weak"
    assert entry["evidence_count"] == 2
    assert sorted(entry["evidence_refs"]) == ["e1", "e2"]


def test_ability_dimension_falls_back_to_error_code_registry_when_rubric_missing() -> None:
    """Legacy evidence with no rubric still drives ability_state via the
    error_code → ability_dimension mapping registered in Phase -1.B."""
    legacy = _case_event(event_id="legacy_e1", days_ago=0, error_code="M02")
    # Strip the rubric to simulate legacy payload.
    legacy.payload_json.pop("rubric", None)

    projection = project_three_layer_learning_state(events=[legacy])

    # M02 maps to question_reading.
    ability = next(a for a in projection["ability_state"] if a["dimension"] == "question_reading")
    assert ability["evidence_count"] == 1


# ─── Behavior state ────────────────────────────────────────────────────────


def test_recurrence_clusters_by_node_ability_and_error_code() -> None:
    """Two events on the same (node, ability_dimension, error_code) key
    drive a behavior state of recurrence=recurring with evidence_count=2."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="e1", days_ago=3),
            _case_event(event_id="e2", days_ago=0),
        ]
    )

    behavior = next(b for b in projection["behavior_state"] if b["dimension"] == "recurrence")
    assert behavior["state"] == "recurring"
    assert behavior["evidence_count"] == 2


def test_different_error_codes_do_not_count_as_recurrence() -> None:
    """Same node + same ability but DIFFERENT error_codes → two separate
    clusters; no recurrence yet."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="e1", days_ago=2, error_code="E02"),
            _case_event(event_id="e2", days_ago=0, error_code="E04"),
        ]
    )

    recurrence = [b for b in projection["behavior_state"] if b["dimension"] == "recurrence"]
    assert recurrence == []


def test_still_confused_from_conversation_alone_does_not_prove_mastery() -> None:
    """Conversation evidence may contribute behavior.still_confused but
    MUST NOT generate a knowledge_state entry or mark mastery."""
    projection = project_three_layer_learning_state(
        events=[
            _conv_event(event_id="conv1", days_ago=0, signal_type="still_confused"),
        ]
    )

    assert projection["knowledge_state"] == []
    assert projection["ability_state"] == []
    behavior = next(b for b in projection["behavior_state"] if b["dimension"] == "still_confused")
    assert behavior["state"] == "active"
    assert behavior["evidence_count"] == 1


# ─── Granularity / legacy / fabrication guards ─────────────────────────────


def test_keyword_only_granularity_downgrades_to_observed_observation() -> None:
    """Hard rule from plan: keyword-only items can be a lower-confidence
    observation; they never escalate to ``weak``, ``stable``, etc."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(
                event_id="kw1",
                days_ago=2,
                granularity="keyword_only",
                rubric_mode="projected_rubric",
            ),
            _case_event(
                event_id="kw2",
                days_ago=0,
                granularity="keyword_only",
                rubric_mode="projected_rubric",
            ),
        ]
    )

    knowledge = projection["knowledge_state"][0]
    # Two negatives would normally promote to "weak", but granularity locks at observed.
    assert knowledge["state"] == "observed"
    assert knowledge["granularity"] == "keyword_only"


def test_legacy_evidence_tolerated_and_marked() -> None:
    """An event without rubric, ability_dimension, or knowledge_node_id
    still projects something safe and gets ``legacy=True`` so consumers
    can dim/hide it. Hard rule: never raise on legacy payload."""
    legacy = LearnerStateEvent(
        event_id="legacy_only",
        user_id="student_demo",
        source_feature="construction_grading",
        source_id="turn:legacy",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="legacy_only",
        created_at=_iso(1),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "construction_grading",
            "question_id": "q_legacy",
            "score_awarded": 0,
            "max_score": 1,
            # no rubric, no error_events, no next_training_signal
        },
    )

    projection = project_three_layer_learning_state(events=[legacy])

    # Doesn't crash. Knowledge/ability arrays may be empty (no usable signal)
    # but a legacy_count is exposed so the consumer can disclose it.
    assert "legacy_count" in projection["source_status"]
    assert projection["source_status"]["legacy_count"] == 1


def test_projection_never_fabricates_evidence_refs() -> None:
    """Every state entry must cite at least one real event_id."""
    projection = project_three_layer_learning_state(
        events=[
            _case_event(event_id="e1", days_ago=2),
            _case_event(event_id="e2", days_ago=0),
        ]
    )

    for layer_name in ("knowledge_state", "ability_state", "behavior_state"):
        for item in projection[layer_name]:
            refs = item.get("evidence_refs") or []
            assert refs, f"{layer_name} item must cite evidence_refs, got {item!r}"
            for ref in refs:
                assert ref in {"e1", "e2"}, f"fabricated ref {ref!r} in {layer_name}"


def test_input_events_are_not_mutated() -> None:
    """Read-only invariant — the projection helper cannot rewrite event
    payloads. Future Phase -1.D windowing relies on this so the synthesis
    can safely truncate without losing data."""
    event = _case_event(event_id="immut", days_ago=0)
    snapshot = (event.event_id, dict(event.payload_json))

    project_three_layer_learning_state(events=[event])

    assert event.event_id == snapshot[0]
    assert event.payload_json == snapshot[1]
