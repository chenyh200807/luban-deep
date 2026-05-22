"""Batch C Task 7: scoring point map read projection.

Pins a focused sibling read model that emits the采分点 / 审题要点 /
``rubric_pending`` empty state from existing learning_evidence — without
fabricating scoring_point_hits or writing any new table.

Hard rules from the plan:

- Items with ``rubric_mode ∈ {grading_key, curated_rubric}`` surface as
  ``granularity="scoring_point"`` (the canonical 采分点 UI label).
- Items with ``rubric_mode == projected_rubric`` surface as
  ``granularity="keyword_only"`` (UI shows "审题要点").
- ``rubric_mode == open_skill`` items contribute nothing to the map.
- When no map-eligible evidence exists, ``empty_state`` MUST be
  ``rubric_pending`` (or ``no_evidence`` when zero events) so the UI
  shows the honest空态 rather than fabricating采分点.
- Every item must cite ``evidence_refs``; items with empty refs are
  dropped.
- ``next_action.intent.intent_version == 2`` — the v2 prescription is the
  sole recommendation authority on this surface.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deeptutor.services.learner_state.scoring_point_map_read_model import (
    build_scoring_point_map_read_projection,
)
from deeptutor.services.learner_state.service import LearnerStateEvent

_TZ = timezone(timedelta(hours=8))


def _iso(days_ago: float) -> str:
    return (datetime.now(_TZ) - timedelta(days=days_ago)).isoformat()


def _case_event(
    *,
    event_id: str,
    days_ago: float = 0,
    rubric_mode: str = "curated_rubric",
    granularity: str = "scoring_point",
    point_id: str = "p_fire_rating",
    point_label: str = "甲乙丙级耐火极限",
    knowledge_node_id: str = "1A412010",
    ability_dimension: str = "code_application",
    error_code: str = "E02",
    hit: bool = False,
) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=_iso(days_ago),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "construction_grading",
            "question_id": f"q_{event_id}",
            "score_awarded": 1 if hit else 0,
            "max_score": 1,
            "rubric": {
                "rubric_mode": rubric_mode,
                "granularity": granularity,
                "scoring_points": [
                    {
                        "point_id": point_id,
                        "label": point_label,
                        "knowledge_node_id": knowledge_node_id,
                        "ability_dimension": ability_dimension,
                    }
                ],
                "scoring_point_hits": [
                    {
                        "point_id": point_id,
                        "hit": hit,
                        "awarded_score": 1 if hit else 0,
                        "error_code": error_code,
                    }
                ],
            },
        },
    )


# ─── Top-level shape ───────────────────────────────────────────────────────


def test_empty_events_produce_no_evidence_empty_state() -> None:
    projection = build_scoring_point_map_read_projection(events=[], user_id="u1")

    assert projection["items"] == []
    assert projection["empty_state"] == "no_evidence"
    assert projection["source_status"]["authority"] == "learner_memory_events.learning_evidence"


def test_only_open_skill_events_yield_rubric_pending_empty_state() -> None:
    """When evidence exists but no rubric carries scoring points, the
    surface MUST disclose rubric_pending rather than render nothing."""
    projection = build_scoring_point_map_read_projection(
        events=[_case_event(event_id="open1", rubric_mode="open_skill", granularity="")],
        user_id="u1",
    )

    assert projection["items"] == []
    assert projection["empty_state"] == "rubric_pending"


# ─── 采分点 granularity ────────────────────────────────────────────────────


def test_curated_rubric_missed_point_emerges_as_scoring_point_item() -> None:
    projection = build_scoring_point_map_read_projection(
        events=[_case_event(event_id="e1")],
        user_id="student_demo",
    )

    assert projection["empty_state"] == ""
    assert len(projection["items"]) == 1
    item = projection["items"][0]
    assert item["granularity"] == "scoring_point"
    assert item["point_id"] == "p_fire_rating"
    assert item["label"] == "甲乙丙级耐火极限"
    assert item["miss_count"] == 1
    assert item["evidence_refs"] == ["e1"]


def test_grading_key_mode_also_yields_scoring_point_granularity() -> None:
    projection = build_scoring_point_map_read_projection(
        events=[_case_event(event_id="gk1", rubric_mode="grading_key")],
        user_id="student_demo",
    )

    assert projection["items"][0]["granularity"] == "scoring_point"


def test_repeated_misses_on_same_point_aggregate_into_one_item() -> None:
    """Two miss events on the same point_id collapse into a single map
    item with miss_count=2 and both evidence_refs."""
    projection = build_scoring_point_map_read_projection(
        events=[
            _case_event(event_id="e1", days_ago=3),
            _case_event(event_id="e2", days_ago=0),
        ],
        user_id="student_demo",
    )

    assert len(projection["items"]) == 1
    item = projection["items"][0]
    assert item["miss_count"] == 2
    assert sorted(item["evidence_refs"]) == ["e1", "e2"]


def test_hits_do_not_count_as_misses() -> None:
    """A correct attempt on the rubric point is NOT a miss; the item
    only counts misses (``miss_count`` excludes ``hit=True``)."""
    projection = build_scoring_point_map_read_projection(
        events=[
            _case_event(event_id="hit1", hit=True),
            _case_event(event_id="miss1", hit=False),
        ],
        user_id="student_demo",
    )

    items = projection["items"]
    assert len(items) == 1
    assert items[0]["miss_count"] == 1
    assert items[0]["evidence_refs"] == ["miss1"]


# ─── 审题要点 granularity ──────────────────────────────────────────────────


def test_projected_rubric_yields_keyword_only_granularity() -> None:
    """projected_rubric must surface as ``keyword_only`` so the UI shows
    审题要点 rather than 采分点."""
    projection = build_scoring_point_map_read_projection(
        events=[
            _case_event(
                event_id="kw1",
                rubric_mode="projected_rubric",
                granularity="keyword_only",
                point_label="对角线布点",
                knowledge_node_id="1A411010",
            )
        ],
        user_id="student_demo",
    )

    assert len(projection["items"]) == 1
    assert projection["items"][0]["granularity"] == "keyword_only"


def test_projected_rubric_in_unqualified_cluster_stays_rubric_pending() -> None:
    """projected_rubric only promotes for audited >=70% clusters.

    This guards the Batch C per-cluster gate: lower-coverage clusters must not
    render keyword-only map rows as if the map is ready.
    """
    projection = build_scoring_point_map_read_projection(
        events=[
            _case_event(
                event_id="low_cov",
                rubric_mode="projected_rubric",
                granularity="keyword_only",
                knowledge_node_id="1A412010",
            )
        ],
        user_id="student_demo",
    )

    assert projection["items"] == []
    assert projection["empty_state"] == "rubric_pending"
    assert projection["source_status"]["projected_rubric_blocked_event_count"] == 1


def test_projected_rubric_filters_mixed_cluster_points_individually() -> None:
    """A projected rubric event can contain points from multiple clusters.

    The gate is per node_code prefix, so a qualified point must not promote
    a weaker sibling point from the same event.
    """
    event = _case_event(
        event_id="mixed_projected",
        rubric_mode="projected_rubric",
        granularity="keyword_only",
        point_id="eligible_p",
        point_label="合格簇要点",
        knowledge_node_id="1A411010",
    )
    rubric = event.payload_json["rubric"]
    rubric["scoring_points"].append(
        {
            "point_id": "weak_p",
            "label": "弱覆盖簇要点",
            "knowledge_node_id": "1A412010",
            "ability_dimension": "code_application",
        }
    )
    rubric["scoring_point_hits"].append(
        {
            "point_id": "weak_p",
            "hit": False,
            "awarded_score": 0,
            "error_code": "E02",
        }
    )

    projection = build_scoring_point_map_read_projection(
        events=[event],
        user_id="student_demo",
    )

    assert [item["point_id"] for item in projection["items"]] == ["eligible_p"]
    assert projection["items"][0]["granularity"] == "keyword_only"


# ─── next_action ──────────────────────────────────────────────────────────


def test_each_item_carries_next_action_with_training_intent_v2() -> None:
    projection = build_scoring_point_map_read_projection(
        events=[_case_event(event_id="e1")],
        user_id="student_demo",
    )

    item = projection["items"][0]
    assert "next_action" in item
    intent = item["next_action"]["intent"]
    assert intent["intent_version"] == 2
    # Intent must cite the cluster's evidence (the very misses that
    # produced this map item).
    assert intent["evidence_refs"] == ["e1"]
    assert intent["concept_id"] == "1A412010"
    assert intent["ability_dimension"] == "code_application"


def test_map_uses_training_intent_priority_for_active_vs_queued() -> None:
    """The map may surface multiple missed points, but active prescription
    count is governed by training_intent, not by frontend sorting."""
    events = [
        _case_event(
            event_id=f"miss_{index}",
            point_id=f"p_{index}",
            point_label=f"采分点 {index}",
            knowledge_node_id=f"1A4120{index}",
            days_ago=index,
        )
        for index in range(5)
    ]

    projection = build_scoring_point_map_read_projection(
        events=events,
        user_id="student_demo",
    )

    statuses = [
        item["next_action"]["intent"]["status"]
        for item in projection["items"]
    ]
    assert statuses.count("active") == 3
    assert statuses.count("queued") == 2


# ─── Honesty / no-fabrication guards ──────────────────────────────────────


def test_items_with_empty_evidence_refs_are_dropped() -> None:
    """An item that somehow ends up with no evidence_refs (e.g. only hits
    and no misses, or filtered out) must NOT appear. The map projects
    misses, not aspirations."""
    projection = build_scoring_point_map_read_projection(
        events=[_case_event(event_id="hit_only", hit=True)],
        user_id="student_demo",
    )

    # The point is hit, so miss_count=0 and the item is dropped.
    assert projection["items"] == []
    # But the evidence exists, so empty_state is rubric_pending (not no_evidence).
    assert projection["empty_state"] == "rubric_pending"


def test_input_events_are_not_mutated() -> None:
    """Read-only invariant — the projection helper cannot rewrite event
    payloads."""
    event = _case_event(event_id="immut")
    snapshot = (event.event_id, dict(event.payload_json))

    build_scoring_point_map_read_projection(events=[event], user_id="student_demo")

    assert event.event_id == snapshot[0]
    assert event.payload_json == snapshot[1]


def test_conversation_events_do_not_contribute_to_map() -> None:
    """Hard rule: scoring point map reads only from
    construction_grading rubric blocks. Conversation_synthesis events
    are not allowed to seed map items."""
    conv = LearnerStateEvent(
        event_id="conv1",
        user_id="student_demo",
        source_feature="conversation_synthesis",
        source_id="turn:conv1",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key="conv1",
        created_at=_iso(0),
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "conversation_synthesis",
            "learning_signal_type": "still_confused",
        },
    )

    projection = build_scoring_point_map_read_projection(events=[conv], user_id="student_demo")
    assert projection["items"] == []
    assert projection["empty_state"] == "no_evidence"


def test_source_status_discloses_coverage_stats() -> None:
    """source_status MUST surface basic coverage stats so consumers (and
    the per-cluster gate UI) can decide whether to promote keyword_only
    items to采分点 grade."""
    projection = build_scoring_point_map_read_projection(
        events=[
            _case_event(event_id="curated1"),  # scoring_point
            _case_event(
                event_id="proj1",
                rubric_mode="projected_rubric",
                granularity="keyword_only",
                point_id="kw_only_p",
                point_label="提示词",
                knowledge_node_id="1A411010",
            ),
            _case_event(event_id="open1", rubric_mode="open_skill", granularity=""),
        ],
        user_id="student_demo",
    )

    stats = projection["source_status"]
    assert stats["authority"] == "learner_memory_events.learning_evidence"
    assert stats["scoring_point_items"] == 1
    assert stats["keyword_only_items"] == 1
    # 2 of 3 case events carry usable rubric (curated + projected). open_skill drops.
    assert stats["map_eligible_event_count"] == 2
    assert stats["total_case_event_count"] == 3
