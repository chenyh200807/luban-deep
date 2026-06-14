"""PGO runtime-supply builder gates for KnowQL Stage 5.

The builder is deterministic plumbing only: it turns already-validated
``luban_per_question_grading_contract.v1`` records into the separate PGO bank slot
without minting per-point scores or enabling production default.
"""

from __future__ import annotations

from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
from deeptutor.services.construction_grading.per_question_grading_object import (
    A_OFFICIAL,
    GRADING_CONTRACT_SCHEMA_ID,
)


def _contract(question_id: str = "Q-PGO") -> dict:
    return {
        "contract_schema": GRADING_CONTRACT_SCHEMA_ID,
        "source_schema": "luban_per_question_grading_object.v1",
        "question_id": question_id,
        "stem": "案例题",
        "official_total_score": 10.0,
        "official_total_score_authority": A_OFFICIAL,
        "per_point_score_authority": "pending_calibration_not_official",
        "scoring_points": [
            {
                "point_id": "sp_a",
                "sub_no": 1,
                "sub_type": "enumeration",
                "official_slice": "写明项目经理应组织检查",
                "authority_source": A_OFFICIAL,
                "span_hash": "sha256:a",
            },
            {
                "point_id": "sp_b",
                "sub_no": 1,
                "sub_type": "free_text_point",
                "official_slice": "写明应编制专项施工方案",
                "authority_source": A_OFFICIAL,
                "span_hash": "sha256:b",
            },
        ],
        "supporting_citations": [
            {
                "point_id": "sp_b",
                "term": "专项施工方案",
                "chunk_id": "1A420000_001",
                "span_hash": "sha256:cite",
                "official_score_allowed": False,
            }
        ],
        "g2_role": {
            "official_decides_correctness": True,
            "rich_leaf_role": "supporting_only",
        },
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "output_contract": {
            "must_emit_one_verdict_per_point_id": True,
            "verdict_enum": ["hit", "partial", "miss", "contradiction"],
            "score_pct_must_be_consistent_with_verdicts": True,
        },
    }


def test_build_pgo_runtime_supply_keeps_null_scores_and_hash_pins_pointer() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_pgo_runtime_supply,
        build_pgo_runtime_supply_pointer,
        validate_pgo_runtime_supply,
    )

    bundle = build_pgo_runtime_supply([_contract()])
    pointer = build_pgo_runtime_supply_pointer(bundle)

    assert bundle["manifest"]["namespace"] == "case_rubric_scored_pgo"
    assert bundle["manifest"]["status"] == "release_candidate"
    assert bundle["manifest"]["published"] is False
    assert bundle["manifest"]["production_default"] == "off"
    assert bundle["manifest"]["question_count"] == 1
    assert bundle["manifest"]["scoring_point_count"] == 2
    assert bundle["manifest"]["content_hash"] == _sha256_hex(bundle["records"])
    assert pointer["expected_content_hash"] == bundle["manifest"]["content_hash"]
    assert pointer["status"] == "release_candidate"

    records = bundle["records"]
    assert [r["point_id"] for r in records] == ["sp_a", "sp_b"]
    assert records[0]["qid"] == "Q-PGO"
    assert records[0]["text"] == "写明项目经理应组织检查"
    assert records[0]["score"] is None
    assert records[0]["max_score"] is None
    assert records[0]["official_total_score"] == 10.0
    assert records[0]["score_authority"] == "official_total_x_verdict_coverage"
    assert records[0]["per_point_score_authority"] == "pending_calibration_not_official"
    assert records[0]["policy"] == "list"
    assert records[1]["policy"] == "exact_required"
    assert records[1]["required_terms"] == ["专项施工方案"]
    assert validate_pgo_runtime_supply(bundle) == []


def test_build_pgo_runtime_supply_rejects_invalid_contract_without_laundering() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_pgo_runtime_supply,
        validate_pgo_runtime_supply,
    )

    bad = _contract("Q-bad")
    bad["scoring_points"][0]["span_hash"] = ""

    bundle = build_pgo_runtime_supply([bad])

    assert bundle["records"] == []
    assert bundle["rejected"][0]["question_id"] == "Q-bad"
    assert "scoring_point_missing_span_hash:sp_a" in bundle["rejected"][0]["blockers"]
    assert "no_records" in validate_pgo_runtime_supply(bundle)


def test_validate_pgo_runtime_supply_blocks_minted_or_tampered_bundle() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_pgo_runtime_supply,
        validate_pgo_runtime_supply,
    )

    bundle = build_pgo_runtime_supply([_contract()])
    bundle["records"][0]["score"] = 1.0

    blockers = validate_pgo_runtime_supply(bundle)

    assert "record_minted_score:sp_a" in blockers
    assert "content_hash_mismatch" in blockers
