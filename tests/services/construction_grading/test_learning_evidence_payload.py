"""Batch A Task 2: case rubric evidence payload.

Asserts that ``build_learning_evidence_payload`` preserves case-answer
rubric + scoring_point definitions + scoring_point_hits + rubric_mode +
granularity, after:

1. Reconciling LLM-proposed hits against the curated rubric_specs via
   Phase -1.A ``audit.reconcile_grader_output`` — fabricated point_ids
   are dropped, never written into evidence.
2. Validating each hit's ``error_code`` against the Phase -1.B unified
   registry — unregistered codes are coerced to ``"unknown_error"``.

Hard product rules:

- Detail readiness (``quality.detail_ready``) is NOT blocked by rubric
  presence. It still depends only on question + answer + explanation.
- ``rubric.granularity`` is ``scoring_point`` only for
  ``rubric_mode ∈ {grading_key, curated_rubric}``; ``projected_rubric``
  yields ``keyword_only`` (the UI must render these as "审题要点" rather
  than full "采分点"). ``open_skill`` yields no granularity.
- The normalizer never writes back into ``questions_bank.grading_rubric``.
"""
from __future__ import annotations

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)


def _base_grading_result(**overrides) -> dict:
    payload = {
        "type": "case",
        "question_id": "case_fire_001",
        "question_stem": "下列关于甲级防火门耐火极限的说法，正确的是？",
        "user_answer": "甲级防火门耐火极限 1.0h",
        "correct_answer": "甲级 1.5h，乙级 1.0h，丙级 0.5h",
        "score_awarded": 0,
        "max_score": 2,
        "explanation": {"summary": "甲级耐火极限记错。"},
        "error_events": [
            {"error_code": "E02", "concept_tag": "1A412010", "diagnosis": "采分点遗漏。"}
        ],
        "next_training_signal": {"concept": "1A412010", "focus": "防火门耐火极限", "mode": "case_repair"},
    }
    payload.update(overrides)
    return payload


def test_case_rubric_scoring_points_are_preserved_in_learning_evidence_payload() -> None:
    """Plan's literal failing test (adapted to the actual signature):
    rubric_id, rubric_version, scoring_points, scoring_point_hits
    all survive through build_learning_evidence_payload."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_id": "fire_door_v1",
            "rubric_version": "2026-05-22",
            "rubric_mode": "curated_rubric",
            "scoring_points": [
                {
                    "point_id": "fire_rating",
                    "label": "甲乙丙级耐火极限",
                    "max_score": 1,
                    "ability_dimension": "code_application",
                    "knowledge_node_id": "1A412010",
                }
            ],
            "scoring_point_hits": [
                {
                    "point_id": "fire_rating",
                    "hit": False,
                    "awarded_score": 0,
                    "miss_reason": "把甲级 1.5h 记成 1.0h",
                    "evidence_text": "甲级防火门耐火极限 1.0h",
                    "error_code": "E02",
                }
            ],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    rubric = payload["rubric"]

    assert rubric["rubric_id"] == "fire_door_v1"
    assert rubric["rubric_version"] == "2026-05-22"
    assert rubric["rubric_mode"] == "curated_rubric"
    assert rubric["granularity"] == "scoring_point"
    assert rubric["scoring_points"][0]["point_id"] == "fire_rating"
    assert rubric["scoring_point_hits"][0]["miss_reason"] == "把甲级 1.5h 记成 1.0h"
    assert rubric["scoring_point_hits"][0]["error_code"] == "E02"
    # Detail readiness is independent of rubric presence; the explanation drives it.
    assert payload["quality"]["detail_ready"] is True


def test_grading_key_mode_marks_granularity_as_scoring_point() -> None:
    """grading_key (highest authority tier per case_kernel) is map-eligible
    at scoring_point granularity."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "grading_key",
            "scoring_points": [{"point_id": "p1", "label": "甲乙丙级耐火极限"}],
            "scoring_point_hits": [{"point_id": "p1", "hit": False, "awarded_score": 0}],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    assert payload["rubric"]["rubric_mode"] == "grading_key"
    assert payload["rubric"]["granularity"] == "scoring_point"


def test_projected_rubric_mode_marks_granularity_keyword_only() -> None:
    """projected_rubric items must surface as keyword_only so the UI
    renders "审题要点" rather than "采分点". Phase -1.A hard rule."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "projected_rubric",
            "scoring_points": [{"point_id": "kw_1", "label": "对角线布点"}],
            "scoring_point_hits": [{"point_id": "kw_1", "hit": False, "awarded_score": 0}],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    assert payload["rubric"]["rubric_mode"] == "projected_rubric"
    assert payload["rubric"]["granularity"] == "keyword_only"


def test_open_skill_mode_has_no_granularity_no_scoring_points() -> None:
    """open_skill: no formal rubric → granularity absent; scoring_points
    empty; payload still progress-countable."""
    grading_result = _base_grading_result(
        rubric={"rubric_mode": "open_skill"},
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    rubric = payload["rubric"]
    assert rubric["rubric_mode"] == "open_skill"
    assert rubric.get("granularity") in (None, "", "open_skill")  # not scoring_point/keyword_only
    assert rubric["scoring_points"] == []
    assert rubric["scoring_point_hits"] == []


def test_fabricated_scoring_point_hit_is_dropped_and_logged() -> None:
    """LLM-proposed point_id outside rubric_specs must be dropped from
    accepted_hits and recorded under grader_disagreement; never appears in
    evidence."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "curated_rubric",
            "scoring_points": [{"point_id": "real_point", "label": "真实采分点"}],
            "scoring_point_hits": [
                {"point_id": "real_point", "hit": True, "awarded_score": 1},
                {"point_id": "invented_extra_point", "hit": True, "awarded_score": 1},
            ],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    rubric = payload["rubric"]

    hit_ids = [hit["point_id"] for hit in rubric["scoring_point_hits"]]
    assert "real_point" in hit_ids
    assert "invented_extra_point" not in hit_ids, (
        "LLM-fabricated point_id must be dropped from evidence"
    )

    disagreement_ids = [item["point_id"] for item in rubric.get("grader_disagreement") or []]
    assert "invented_extra_point" in disagreement_ids


def test_unregistered_error_code_on_scoring_point_hit_is_coerced_to_unknown_error() -> None:
    """error_code on a hit must exist in error_code_registry; unknowns
    become 'unknown_error' so downstream synthesis doesn't break."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "curated_rubric",
            "scoring_points": [{"point_id": "p1", "label": "x"}],
            "scoring_point_hits": [
                {"point_id": "p1", "hit": False, "awarded_score": 0, "error_code": "X99"}
            ],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    hit = payload["rubric"]["scoring_point_hits"][0]
    assert hit["error_code"] == "unknown_error"


def test_registered_error_code_on_scoring_point_hit_passes_through() -> None:
    """Registered codes (E0X / M0X / unknown_error) survive intact."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "curated_rubric",
            "scoring_points": [{"point_id": "p1", "label": "x"}],
            "scoring_point_hits": [
                {"point_id": "p1", "hit": False, "awarded_score": 0, "error_code": "E04"}
            ],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    assert payload["rubric"]["scoring_point_hits"][0]["error_code"] == "E04"


def test_missing_rubric_block_does_not_break_detail_readiness() -> None:
    """When the grader doesn't supply a rubric, the payload still gets a
    safe rubric block (empty scoring_points + scoring_point_hits) but
    detail readiness stays True because explanation is present."""
    grading_result = _base_grading_result()  # no rubric override
    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")

    rubric = payload["rubric"]
    assert rubric["scoring_points"] == []
    assert rubric["scoring_point_hits"] == []
    # Mode may be derived from grading_result.grading_mode if present, or empty.
    assert "rubric_mode" in rubric
    assert payload["quality"]["detail_ready"] is True


def test_empty_rubric_specs_drop_all_llm_hits() -> None:
    """When rubric_specs is empty (e.g. mode=open_skill), the reconciler
    refuses every LLM-proposed hit so no fabricated scoring points reach
    the evidence ledger."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "open_skill",
            "scoring_points": [],
            "scoring_point_hits": [
                {"point_id": "ghost_a", "hit": True, "awarded_score": 1},
                {"point_id": "ghost_b", "hit": True, "awarded_score": 1},
            ],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    rubric = payload["rubric"]
    assert rubric["scoring_point_hits"] == []
    disagreement_ids = [item["point_id"] for item in rubric.get("grader_disagreement") or []]
    assert sorted(disagreement_ids) == ["ghost_a", "ghost_b"]


def test_rubric_block_does_not_carry_grading_rubric_writeback_marker() -> None:
    """Hard rule: the normalizer is READ-ONLY. The emitted payload must
    not contain any signal that asks downstream code to write back into
    questions_bank.grading_rubric."""
    grading_result = _base_grading_result(
        rubric={
            "rubric_mode": "curated_rubric",
            "scoring_points": [{"point_id": "p1", "label": "x"}],
            "scoring_point_hits": [{"point_id": "p1", "hit": False, "awarded_score": 0}],
        }
    )

    payload = build_learning_evidence_payload(grading_result=grading_result, turn_id="t1")
    rubric = payload["rubric"]

    forbidden_markers = ("writeback", "persist", "write_back", "update_grading_rubric")
    for marker in forbidden_markers:
        assert marker not in rubric, f"{marker!r} must not appear in emitted rubric block"
