"""M32 Task 3: the learning_evidence payload must carry the point-level diagnostic
fields the grader already produces (policy_type / mistake_type / evidence_span /
required_terms / high_risk_review), so the Learning Brain can build an explainable
point-level claim ("哪里错、为什么错、证据来自哪段作答").

The grader (rubric_grader_v1) emits these on each scoring point; previously the
learning_evidence normalization layer dropped them. Append-only: payloads without
these fields stay byte-identical and the dedupe key stays stable."""
from __future__ import annotations

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)

# M32 canonical waterproof example (master plan §0.26.15 Task 3 fixture).
WATERPROOF_GRADING_RESULT = {
    "type": "case",
    "question_id": "waterproof_case_001",
    "user_answer": "普通防水砂浆处理",
    "rubric": {
        "rubric_id": "rb_waterproof",
        "rubric_mode": "curated_rubric",
        "scoring_points": [
            {
                "point_id": "waterproof_exact_required_001",
                "label": "防水施工规范术语",
                "max_score": 1,
                "knowledge_node_id": "kn_waterproof_term",
            }
        ],
        "scoring_point_hits": [
            {
                "point_id": "waterproof_exact_required_001",
                "hit": False,
                "awarded_score": 0,
                "policy_type": "exact_required",
                "mistake_type": "near_synonym_not_accepted",
                "evidence_span": "普通防水砂浆处理",
                "required_terms": ["聚合物水泥防水砂浆"],
                "high_risk_review": True,
            }
        ],
    },
    "error_events": [
        {
            "error_code": "near_synonym_not_accepted",
            "evidence_span": "普通防水砂浆处理",
            "policy_type": "exact_required",
            "knowledge_point": "防水施工规范术语",
        }
    ],
}


def _hit(payload: dict) -> dict:
    hits = payload["rubric"]["scoring_point_hits"]
    assert hits, "expected the accepted scoring-point hit to survive normalization"
    return hits[0]


def test_scoring_point_hit_carries_point_level_diagnostic_fields() -> None:
    payload = build_learning_evidence_payload(grading_result=WATERPROOF_GRADING_RESULT)
    hit = _hit(payload)
    assert hit["mistake_type"] == "near_synonym_not_accepted"
    assert hit["evidence_span"] == "普通防水砂浆处理"
    assert hit["policy_type"] == "exact_required"
    assert hit["required_terms"] == ["聚合物水泥防水砂浆"]
    assert hit["high_risk_review"] is True


def test_error_events_preserve_evidence_span_for_learning_brain() -> None:
    payload = build_learning_evidence_payload(grading_result=WATERPROOF_GRADING_RESULT)
    err = payload["error_events"][0]
    assert err["evidence_span"] == "普通防水砂浆处理"
    assert err["policy_type"] == "exact_required"


def test_append_only_dedupe_key_stable_for_payload_without_new_fields() -> None:
    """A legacy-shaped result (no point-level fields) must produce the same dedupe key
    as before — the new fields are diagnostic, not identity."""
    legacy = {
        "type": "case",
        "question_id": "q1",
        "user_answer": "x",
        "error_events": [{"error_code": "omitted"}],
        "score_awarded": 0,
        "max_score": 1,
    }
    payload = build_learning_evidence_payload(grading_result=legacy, turn_id="t1", session_id="s1")
    key = build_learning_evidence_dedupe_key(user_id="u1", payload_json=payload)
    assert key == build_learning_evidence_dedupe_key(user_id="u1", payload_json=payload)
    # the new point-level fields are absent on a legacy hit -> no scoring_point_hits keys leak
    assert payload["rubric"]["scoring_point_hits"] == []


def test_grading_error_event_schema_id_is_registered_as_t2() -> None:
    """The canonical grading error-event (GradingErrorEvent) producer's SCHEMA_ID must be
    registered T2 in the schema registry (no unregistered/competing error-event shape can
    appear). Register-before-use VISIBILITY promotion (schema-governance P2, error_events
    target). The ``evidence`` vs v1-rubric ``evidence_span`` field drift is a separate
    field-canonicalization follow-up (needs_field_canonicalization: true), not this test."""
    from pathlib import Path

    import yaml

    from deeptutor.services.construction_grading.schema import GRADING_ERROR_EVENT_SCHEMA_ID

    assert GRADING_ERROR_EVENT_SCHEMA_ID == "grading_error_event.v1"
    registry = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "contracts" / "schema_registry.yaml").read_text("utf-8")
    )
    t2_names = {e["name"] for e in registry["tier2_canonical_contracts"]}
    assert GRADING_ERROR_EVENT_SCHEMA_ID in t2_names, (
        f"{GRADING_ERROR_EVENT_SCHEMA_ID} must be a registered T2 runtime-canonical contract"
    )
