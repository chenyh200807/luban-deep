"""Tests for the unified canonical grading-object schema (KnowQL Phase A).

Covers: (1) the deterministic ``validate_grading_object`` validator accepts a
hand-built canonical object and rejects each single-authority violation; (2) every
pre-existing grading schema sample maps into ``luban_grading_object.v1`` via its
adapter and passes the validator, with drift field names regularized away.
"""

from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.grading_object_adapters import (
    ADAPTER_REGISTRY,
    map_case_grading_artifact,
    map_compact_scoring_artifact,
    map_gold_panel_row,
    map_objective_answer_key_record,
    map_per_question_grading_object,
    map_rich_leaf_unit,
    map_scoring_point_assets,
)
from deeptutor.services.construction_grading.unified_grading_object import (
    AUTH_OFFICIAL_ANSWER,
    AUTH_PENDING_CALIBRATION,
    AUTH_TEXTBOOK_CITED,
    CORE_POINT_FIELDS,
    PENDING_SCORE_AUTHORITY,
    REQUIRED_POINT_RESULT_FIELDS,
    SCHEMA_ID,
    TYPE_CASE,
    TYPE_OBJECTIVE,
    GradingObject,
    enforce_grading_output_schema,
    span_hash,
    validate_grading_object,
)


# ── canonical fixtures ───────────────────────────────────────────────────────────
def _canonical_point(statement: str, authority: str = AUTH_TEXTBOOK_CITED) -> dict:
    return {
        "point_id": "sp_x",
        "statement": statement,
        "authority_source": authority,
        "span_hash": None if authority == AUTH_PENDING_CALIBRATION else span_hash(statement),
        "max_score": None,
        "score_authority": PENDING_SCORE_AUTHORITY,
        "hit_status": "not_evaluated",
        "required_terms": [],
        "term_provenance": [],
    }


def _canonical_object(points: list[dict] | None = None) -> dict:
    return GradingObject(
        object_id="Q1",
        question_type=TYPE_CASE,
        official_total_score=7.0,
        scoring_points=points if points is not None else [_canonical_point("结构体系")],
        authority_source=AUTH_OFFICIAL_ANSWER,
    ).to_dict()


# ── validator: happy path ────────────────────────────────────────────────────────
def test_valid_canonical_object_passes() -> None:
    assert validate_grading_object(_canonical_object()) == []


def test_pending_point_with_null_span_hash_passes() -> None:
    point = _canonical_point("待标定采分点", authority=AUTH_PENDING_CALIBRATION)
    assert validate_grading_object(_canonical_object([point])) == []


# ── validator: single-authority rejections ───────────────────────────────────────
def test_missing_authority_source_rejected() -> None:
    obj = _canonical_object()
    del obj["authority_source"]
    assert "missing_required:authority_source" in validate_grading_object(obj)


def test_unknown_authority_source_rejected() -> None:
    obj = _canonical_object()
    obj["authority_source"] = "self_declared_truth"
    assert any(b.startswith("unknown_authority_source") for b in validate_grading_object(obj))


def test_official_score_allowed_true_rejected() -> None:
    obj = _canonical_object()
    obj["official_score_allowed"] = True
    assert "official_score_allowed_must_be_false" in validate_grading_object(obj)


@pytest.mark.parametrize("drift", ["weight", "canonical_answer", "answer_key", "label"])
def test_top_level_drift_field_rejected(drift: str) -> None:
    obj = _canonical_object()
    obj[drift] = "x"
    assert f"forbidden_drift_field:{drift}" in validate_grading_object(obj)


@pytest.mark.parametrize("drift", ["weight", "canonical_answer", "answer_key", "label"])
def test_point_drift_field_rejected(drift: str) -> None:
    point = _canonical_point("结构体系")
    point[drift] = "x"
    blockers = validate_grading_object(_canonical_object([point]))
    assert any(b.startswith(f"point_forbidden_drift_field:{drift}") for b in blockers)


def test_span_backed_point_missing_span_hash_rejected() -> None:
    point = _canonical_point("结构体系")
    point["span_hash"] = None
    blockers = validate_grading_object(_canonical_object([point]))
    assert any(b.startswith("point_missing_span_hash") for b in blockers)


def test_span_hash_mismatch_rejected() -> None:
    point = _canonical_point("结构体系")
    point["span_hash"] = "deadbeef"
    blockers = validate_grading_object(_canonical_object([point]))
    assert any(b.startswith("point_span_hash_mismatch") for b in blockers)


def test_pending_point_carrying_score_rejected() -> None:
    point = _canonical_point("待标定", authority=AUTH_PENDING_CALIBRATION)
    point["max_score"] = 2.0  # minted per-point score under pending authority
    blockers = validate_grading_object(_canonical_object([point]))
    assert any(b.startswith("pending_point_must_not_carry_score") for b in blockers)


def test_unsourced_term_with_chunk_id_rejected() -> None:
    point = _canonical_point("结构体系")
    point["term_provenance"] = [{"chunk_id": "c1", "anchor_verified": False}]
    blockers = validate_grading_object(_canonical_object([point]))
    assert any(b.startswith("unsourced_term_must_have_null_chunk") for b in blockers)


def test_non_dict_rejected() -> None:
    assert validate_grading_object(["not", "a", "dict"]) == ["object_not_dict"]


def test_schema_id_present_on_canonical_object() -> None:
    assert _canonical_object()["schema_id"] == SCHEMA_ID


# ── adapter coverage: every existing schema maps in and validates ────────────────
def test_map_case_grading_artifact() -> None:
    artifact = {
        "artifact_schema": "case_grading_artifact.v1",
        "case_id": "Q1",
        "source_chunks": ["c1"],
        "subquestions": [
            {
                "sub_no": "1",
                "max_score": 3.5,  # drift: per-subq weight name
                "scoring_points": [
                    {
                        "point_id": "Q1-1-P1",
                        "weight": 1.75,  # drift name -> dropped/renamed
                        "canonical_answer": "应由见证人员记录",  # drift -> statement
                        "required_terms": ["见证人员"],
                        "provenance": {
                            "sourced": True,
                            "source_ref": "kb:57",
                            "source_authority": "textbook",
                            "textbook_quote": "见证记录应由见证人员填写",
                        },
                    }
                ],
            }
        ],
    }
    obj = map_case_grading_artifact(artifact)
    assert validate_grading_object(obj) == []
    point = obj["scoring_points"][0]
    assert point["statement"] == "应由见证人员记录"  # canonical_answer regularized
    assert "weight" not in point and "canonical_answer" not in point  # drift removed
    assert point["authority_source"] == AUTH_TEXTBOOK_CITED


def test_map_rich_leaf_unit() -> None:
    unit = {
        "leaf_id": "L1",
        "compiled_context": {
            "scoring_points": [
                {
                    "max_score": None,
                    "point_id": "ca:1A411011_002_0005",
                    "policy_type": "semantic_allowed",
                    "required_terms": ["结构体系", "围护体系", "设备体系"],
                    "source": "chunk_assessment",
                    "statement": "建筑物的三大构成体系是什么？",
                    "provenance": {
                        "chunk_id": "1A411011_002_0005",
                        "quote": "建筑物由结构体系、围护体系和设备体系组成。",
                        "quote_verified": True,
                        "source_authority": "textbook",
                    },
                }
            ]
        },
    }
    obj = map_rich_leaf_unit(unit)
    assert validate_grading_object(obj) == []
    assert obj["scoring_points"][0]["statement"] == "建筑物的三大构成体系是什么？"
    assert obj["scoring_points"][0]["authority_source"] == AUTH_TEXTBOOK_CITED


def test_dual_schema_converges_to_single_canonical_authority() -> None:
    """KnowQL pillar ① convergence proof (single-authority invariant).

    The audit names two divergent grading typed shapes:
      A. ``case_grading_artifact.v1`` (eval-inline) — drift field NAMES ``weight`` / ``canonical_answer``;
      B. ``luban_rich_leaf_scoring_point_compile.v1`` (rich-leaf compile units) — already the
         canonical ``statement`` / ``max_score`` names; its ``runtime_token_pack_unit`` shape is
         exactly what ``map_rich_leaf_unit`` consumes (so it converges through the SAME adapter
         registered for ``luban.rich_leaf_artifact.v0`` — no second adapter, no third schema).

    This pins the invariant that both deterministically map to ONE typed object authority
    (``luban_grading_object.v1``) with the SAME canonical point field set and ZERO drift names.
    KnowQL ②③④ build on this single shape; without this proof they'd have to support two.
    """
    # ── shape A: case_grading_artifact.v1 (weight / canonical_answer drift names) ──
    case_artifact = {
        "artifact_schema": "case_grading_artifact.v1",
        "case_id": "Q1",
        "subquestions": [
            {
                "sub_no": "1",
                "max_score": 2.0,
                "scoring_points": [
                    {
                        "point_id": "Q1-1-P1",
                        "weight": 2.0,  # drift name → max_score
                        "canonical_answer": "见证记录应由见证人员填写",  # drift name → statement
                        "required_terms": ["见证人员"],
                        "provenance": {
                            "sourced": True,
                            "source_ref": "kb:1",
                            "source_authority": "textbook",
                            "textbook_quote": "见证记录应由见证人员填写",
                        },
                    }
                ],
            }
        ],
    }
    # ── shape B: a luban_rich_leaf_scoring_point_compile.v1 runtime_token_pack_unit ──
    # (verbatim shape produced by scripts/run_luban_rich_leaf_scoring_point_compile.py:
    #  compiled_context.scoring_points[] with point_id/statement/max_score/policy_type/
    #  required_terms/provenance — already canonical field names)
    compile_unit = {
        "leaf_id": "1A411011_002",
        "compiled_context": {
            "scoring_points": [
                {
                    "point_id": "ca:1A411011_002_0005",
                    "statement": "建筑物由结构体系、围护体系和设备体系组成",
                    "max_score": None,
                    "policy_type": "semantic_allowed",
                    "required_terms": ["结构体系", "围护体系", "设备体系"],
                    "source": "chunk_assessment",
                    "provenance": {
                        "chunk_id": "1A411011_002_0005",
                        "quote": "建筑物由结构体系、围护体系和设备体系组成。",
                        "quote_verified": True,
                        "source_authority": "textbook",
                    },
                }
            ]
        },
    }

    canonical_a = map_case_grading_artifact(case_artifact)
    canonical_b = map_rich_leaf_unit(compile_unit)

    # 1) both are VALID luban_grading_object.v1 — the one authority covers both divergent shapes
    assert validate_grading_object(canonical_a) == []
    assert validate_grading_object(canonical_b) == []
    assert canonical_a["schema_id"] == SCHEMA_ID == canonical_b["schema_id"]

    point_a = canonical_a["scoring_points"][0]
    point_b = canonical_b["scoring_points"][0]
    # 2) both carry the SAME canonical core field set (convergence to one shape)
    for field in CORE_POINT_FIELDS:
        assert field in point_a, f"shape A missing canonical field {field}"
        assert field in point_b, f"shape B missing canonical field {field}"
    # 3) ZERO drift names survive in EITHER converged object (single canonical vocabulary)
    for drift in ("weight", "canonical_answer", "answer_key", "label"):
        assert drift not in point_a and drift not in point_b
    # 4) the canonical names are identical regardless of which divergent input produced them
    assert point_a["statement"] and point_b["statement"]  # statement (never canonical_answer)
    assert "max_score" in point_a and "max_score" in point_b  # max_score (never weight)


# ── KnowQL ③: the typed object owns its grading-OUTPUT shape contract ──────────────


def _valid_point_result() -> dict:
    return {
        "point_id": "Q1-1-P1",
        "sub_no": "1",
        "max_points": 2.0,
        "required_points": [],
        "accepted_variants": [],
        "student_evidence_quote": "见证记录由见证人员填写",
        "status": "hit",
        "awarded_points": 2.0,
        "deduction_reason": "",
        "misconception_tag": "",
        "next_review_action": "",
        "learning_evidence_event": {},
    }


def test_enforce_grading_output_schema_lifted_to_typed_object_accepts_valid_result() -> None:
    """③: the canonical typed object (not the eval harness) is the single authority for the
    per-point grading-OUTPUT shape. A complete, correctly-typed result passes."""
    assert enforce_grading_output_schema([_valid_point_result()]) == []
    assert len(REQUIRED_POINT_RESULT_FIELDS) == 11


def test_enforce_grading_output_schema_flags_missing_field_type_and_status() -> None:
    # missing a required field
    missing = _valid_point_result()
    del missing["awarded_points"]
    assert any(e.startswith("missing_field:awarded_points") for e in enforce_grading_output_schema([missing]))
    # wrong type (and bool rejected where a number is required — bool is int in Python)
    wrong_type = _valid_point_result()
    wrong_type["awarded_points"] = True
    assert any(e.startswith("type_error:awarded_points") for e in enforce_grading_output_schema([wrong_type]))
    # unknown status (not_evaluated is a rubric state, never a RESULT status)
    bad_status = _valid_point_result()
    bad_status["status"] = "not_evaluated"
    assert any(e.startswith("invalid_status:not_evaluated") for e in enforce_grading_output_schema([bad_status]))
    # missing point identifier
    no_id = _valid_point_result()
    no_id["point_id"] = ""
    assert any("point_id_or_basis_ref" in e for e in enforce_grading_output_schema([no_id]))


def test_map_scoring_point_assets() -> None:
    rows = [
        {
            "schema_version": "luban_scoring_point_assets.v0.1",
            "point_id": "sp_abc",
            "point_type": "text_term",
            "label": "见证记录",  # drift -> statement
            "max_score": None,
            "required_terms": ["见证记录"],
            "score_status": "pending_calibration_not_official",
            "provenance": {
                "chunk_id": "1A434000_01",
                "content_hash": "h",
                "quote": "见证记录",
                "anchor_verified": True,
            },
        }
    ]
    obj = map_scoring_point_assets(rows, object_id="Q1")
    assert validate_grading_object(obj) == []
    assert obj["scoring_points"][0]["statement"] == "见证记录"  # label regularized
    assert "label" not in obj["scoring_points"][0]


def test_map_objective_answer_key_record() -> None:
    record = {
        "answer_key": "C",  # drift -> statement
        "answer_key_authority": "governed_questions_bank_official_answer",
        "options": {"A": "仓储建筑", "B": "农机修理站", "C": "医疗建筑", "D": "宿舍建筑"},
        "question_id": "17655",
        "question_type": "single_choice",
    }
    obj = map_objective_answer_key_record(record)
    assert validate_grading_object(obj) == []
    assert obj["question_type"] == TYPE_OBJECTIVE
    point = obj["scoring_points"][0]
    assert point["statement"] == "C"  # answer_key regularized
    assert point["correct_keys"] == ["C"]
    assert "answer_key" not in point


def test_map_gold_panel_row_is_label_quality_only() -> None:
    row = {
        "case_id": "Q2-1A436000-罚则",
        "student_id": "S1",
        "point_id": "P1",
        "consensus_verdict": "hit",
        "reference_ledger_label": "hit",
        "consensus_matches_reference": True,
    }
    obj = map_gold_panel_row(row)
    assert validate_grading_object(obj) == []
    point = obj["scoring_points"][0]
    # panel verdict is a quality label only: never official score authority
    assert point["authority_source"] == AUTH_PENDING_CALIBRATION
    assert point["hit_status"] == "hit"
    assert point["max_score"] is None


def test_map_compact_scoring_artifact() -> None:
    artifact = {
        "artifact_schema": "compact_scoring_artifact.v1",
        "source_chunks": ["c1"],
        "points": [
            {"sub_no": "1", "max_score": 3.0, "expected_points": ["关键判断", "正确做法"]},
        ],
    }
    obj = map_compact_scoring_artifact(artifact)
    assert validate_grading_object(obj) == []
    assert len(obj["scoring_points"]) == 2
    assert obj["scoring_points"][0]["statement"] == "关键判断"


def test_map_per_question_grading_object() -> None:
    pq = {
        "schema_id": "luban_per_question_grading_object.v1",
        "question_id": "EXAM_1A432000_P0015_01",
        "official_total_score": 22.0,
        "stem": "某项目…",
        "sub_questions": [
            {
                "sub_no": 3,
                "sub_type": "exceptions",
                "scoring_points": [
                    {
                        "point_id": "sp_1",
                        "sub_type": "exceptions",
                        "atomic_official_slice": "将主体结构的施工分包给其他单位的，钢结构工程除外",
                        "authority_source": "official_answer_verbatim",
                        "score": None,
                        "score_authority": "pending_calibration_not_official",
                        "base_rule": "将主体结构的施工分包给其他单位的",
                        "exception_items": ["钢结构工程除外"],
                        "term_provenance": [
                            {
                                "term": "钢结构",
                                "chunk_id": "kb1",
                                "anchor_verified": True,
                                "authority_source": "textbook_cited",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    obj = map_per_question_grading_object(pq)
    assert validate_grading_object(obj) == []
    assert obj["official_total_score"] == 22.0
    point = obj["scoring_points"][0]
    # official_answer_verbatim tag regularized to canonical official_answer
    assert point["authority_source"] == AUTH_OFFICIAL_ANSWER
    assert point["statement"] == "将主体结构的施工分包给其他单位的，钢结构工程除外"
    assert point["exception_items"] == ["钢结构工程除外"]


def test_adapter_registry_covers_seven_schemas() -> None:
    assert len(ADAPTER_REGISTRY) == 7
