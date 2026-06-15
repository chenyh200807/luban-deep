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
    PENDING_SCORE_AUTHORITY,
    SCHEMA_ID,
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


def _pgo_object(question_id: str = "Q-FACTORY") -> dict:
    answer = "施工总进度计划表( 图)\n资源需要量及供应平衡表"
    return {
        "schema_id": SCHEMA_ID,
        "question_id": question_id,
        "stem": "案例题",
        "official_total_score": 8.0,
        "official_total_score_authority": A_OFFICIAL,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
        "sub_questions": [
            {
                "sub_no": 1,
                "sub_type": "free_text_point",
                "official_sub_answer_verbatim": answer,
                "scoring_points": [],
            }
        ],
    }


def _factory_candidate(question_id: str = "Q-FACTORY") -> dict:
    return {
        "summary": {
            "schema": "luban_full_factory_candidate.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "production_gated_by": "migration plan stages",
            },
            "final_must_not_mint_clean": "1/1",
        },
        "cases": [
            {
                "question_id": question_id,
                "case_file": "Q-FACTORY.json",
                "point_type": "list",
                "resolution": "consensus",
                "resolution_lane": "A_consensus",
                "final_mnm_ok": True,
                "segments": [
                    {
                        "text": "施工总进度计划表( 图)",
                        "is_list_item": True,
                        "exact_term_required": True,
                    },
                    {
                        "text": "资源需要量及供应平衡表",
                        "is_list_item": True,
                        "exact_term_required": True,
                    },
                ],
                "list_rule": {"applies": True, "total_items": 2},
                "penalty_rule": {"exists": False, "scope": None, "text": None},
            }
        ],
    }


def _q4_like_pgo_object(question_id: str = "Q4-LIKE") -> dict:
    answer = "\n".join(
        [
            "不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。",
            "正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。",
            "不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。",
            "正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，单独列支并按照合同约定及时支付。",
            "取样",
            "制样",
            "标识",
            "封志",
            "送检",
            "现场检测",
        ]
    )
    return {
        "schema_id": SCHEMA_ID,
        "question_id": question_id,
        "stem": "案例题",
        "official_total_score": 7.0,
        "official_total_score_authority": A_OFFICIAL,
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
        "sub_questions": [
            {
                "sub_no": 1,
                "sub_type": "free_text_point",
                "official_sub_answer_verbatim": answer,
                "scoring_points": [],
            }
        ],
    }


def _q4_like_factory_candidate(question_id: str = "Q4-LIKE") -> dict:
    return {
        "summary": {
            "schema": "luban_full_factory_candidate.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "production_gated_by": "migration plan stages",
            },
            "final_must_not_mint_clean": "1/1",
        },
        "cases": [
            {
                "question_id": question_id,
                "case_file": "Q4-LIKE.json",
                "point_type": "mixed",
                "resolution": "consensus",
                "resolution_lane": "C_opus_arbiter",
                "final_mnm_ok": True,
                "segments": [
                    {"text": "不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。", "is_list_item": False, "exact_term_required": True},
                    {"text": "正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。", "is_list_item": False, "exact_term_required": True},
                    {"text": "不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。", "is_list_item": False, "exact_term_required": True},
                    {"text": "正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，单独列支并按照合同约定及时支付。", "is_list_item": False, "exact_term_required": True},
                    {"text": "取样", "is_list_item": True, "exact_term_required": True},
                    {"text": "制样", "is_list_item": True, "exact_term_required": True},
                    {"text": "标识", "is_list_item": True, "exact_term_required": True},
                    {"text": "封志", "is_list_item": True, "exact_term_required": True},
                    {"text": "送检", "is_list_item": True, "exact_term_required": True},
                    {"text": "现场检测", "is_list_item": True, "exact_term_required": True},
                ],
                "list_rule": {"applies": True, "total_items": 6},
                "penalty_rule": {
                    "exists": True,
                    "scope": "不妥之处部分（2项不妥）",
                    "text": "本问题2项不妥，多答不得分",
                },
                "structural_cap_list_items": 6,
            }
        ],
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
    assert records[0]["authority_source"] == A_OFFICIAL
    assert records[0]["span_hash"] == "sha256:a"
    assert records[0]["policy"] == "list"
    assert records[1]["policy"] == "exact_required"
    assert records[1]["required_terms"] == ["专项施工方案"]
    assert validate_pgo_runtime_supply(bundle) == []


def test_build_grading_contracts_from_factory_candidate_uses_verbatim_segments_only() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_grading_contracts_from_factory_candidate,
        build_pgo_runtime_supply,
        validate_pgo_runtime_supply,
    )

    result = build_grading_contracts_from_factory_candidate(
        _factory_candidate(), [_pgo_object()]
    )

    assert result["rejected"] == []
    contract = result["contracts"][0]
    assert contract["contract_schema"] == GRADING_CONTRACT_SCHEMA_ID
    assert contract["question_id"] == "Q-FACTORY"
    assert contract["official_total_score"] == 8.0
    assert contract["per_point_score_authority"] == PENDING_SCORE_AUTHORITY
    assert contract["official_score_allowed"] is False
    assert contract["canonical_write_allowed"] is False
    assert [p["official_slice"] for p in contract["scoring_points"]] == [
        "施工总进度计划表( 图)",
        "资源需要量及供应平衡表",
    ]
    assert all(p["score"] is None for p in contract["scoring_points"])
    assert all(p["authority_source"] == A_OFFICIAL for p in contract["scoring_points"])
    assert all(str(p["point_id"]).startswith("sp_") for p in contract["scoring_points"])
    assert contract["factory_provenance"]["resolution_lanes"] == ["A_consensus"]

    bundle = build_pgo_runtime_supply(result["contracts"])

    assert validate_pgo_runtime_supply(bundle) == []
    assert bundle["manifest"]["question_count"] == 1
    assert bundle["manifest"]["scoring_point_count"] == 2
    assert bundle["manifest"]["source_schemas"] == [SCHEMA_ID]
    assert bundle["manifest"]["factory_resolution_lanes"] == ["A_consensus"]
    assert bundle["records"][0]["source_schema"] == SCHEMA_ID
    assert bundle["records"][0]["factory_resolution_lane"] == "A_consensus"
    assert bundle["records"][0]["factory_point_type"] == "list"


def test_build_grading_contracts_from_factory_candidate_preserves_case_shape_constraints() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_grading_contracts_from_factory_candidate,
        build_pgo_runtime_supply,
    )

    factory = _factory_candidate()
    factory["cases"][0]["penalty_rule"] = {
        "exists": True,
        "scope": "不妥之处部分（2项不妥）",
        "text": "本问题2项不妥，多答不得分",
    }

    result = build_grading_contracts_from_factory_candidate(factory, [_pgo_object()])

    assert result["rejected"] == []
    contract = result["contracts"][0]
    assert contract["case_shape_constraints"]["list_rule"] == {
        "applies": True,
        "total_items": 2,
    }
    penalty_rule = contract["case_shape_constraints"]["penalty_rule"]
    assert penalty_rule["exists"] is True
    assert penalty_rule["scope"] == "不妥之处部分（2项不妥）"
    assert penalty_rule["text"] == "本问题2项不妥，多答不得分"
    assert penalty_rule["type"] == "multi_answer_no_score"
    assert penalty_rule["trigger"] == {"max_answered_items": 2, "pattern": "不妥"}

    bundle = build_pgo_runtime_supply(result["contracts"])

    assert bundle["manifest"]["case_shape_constraint_count"] == 1
    assert bundle["records"][0]["case_shape_constraints"]["penalty_rule"]["exists"] is True
    assert bundle["records"][0]["case_shape_constraints"]["list_rule"]["total_items"] == 2


def test_q4_like_factory_candidate_marks_penalty_scope_and_list_shape_units() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_grading_contracts_from_factory_candidate,
        build_pgo_runtime_supply,
    )

    result = build_grading_contracts_from_factory_candidate(
        _q4_like_factory_candidate(), [_q4_like_pgo_object()]
    )

    assert result["rejected"] == []
    contract = result["contracts"][0]
    penalty_rule = contract["case_shape_constraints"]["penalty_rule"]
    assert penalty_rule["type"] == "multi_answer_no_score"
    assert penalty_rule["trigger"] == {"max_answered_items": 2, "pattern": "不妥"}
    assert penalty_rule["applies_to_sub_types"] == ["flaw_correction"]
    assert contract["case_shape_constraints"]["list_rule"]["total_items"] == 6

    points = contract["scoring_points"]
    assert [point["case_shape_role"] for point in points[:4]] == ["flaw_correction"] * 4
    assert [point["penalty_scoped"] for point in points[:4]] == [True] * 4
    assert [point["case_shape_role"] for point in points[4:]] == ["enumeration"] * 6
    assert [point["penalty_scoped"] for point in points[4:]] == [False] * 6

    bundle = build_pgo_runtime_supply(result["contracts"])
    by_text = {record["text"]: record for record in bundle["records"]}
    assert by_text["不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。"]["penalty_scoped"] is True
    assert by_text["取样"]["penalty_scoped"] is False
    assert by_text["取样"]["policy"] == "exact_required"


def test_build_grading_contracts_from_factory_candidate_rejects_minted_segment() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_grading_contracts_from_factory_candidate,
    )

    factory = _factory_candidate()
    factory["cases"][0]["segments"][0]["text"] = "施工总进度计划表和横道图"

    result = build_grading_contracts_from_factory_candidate(factory, [_pgo_object()])

    assert result["contracts"] == []
    assert result["rejected"][0]["question_id"] == "Q-FACTORY"
    assert "segment_not_verbatim:1" in result["rejected"][0]["blockers"]


def test_build_grading_contracts_from_factory_candidate_canonicalizes_to_official_substring() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_grading_contracts_from_factory_candidate,
    )

    obj = _pgo_object()
    obj["sub_questions"][0][
        "official_sub_answer_verbatim"
    ] = "分期( 分批) 实施工程的开、\n竣工日期及工期一览表"
    factory = _factory_candidate()
    factory["cases"][0]["segments"] = [
        {
            "text": "分期( 分批) 实施工程的开、竣工日期及工期一览表",
            "is_list_item": True,
        }
    ]

    result = build_grading_contracts_from_factory_candidate(factory, [obj])

    assert result["rejected"] == []
    assert result["contracts"][0]["scoring_points"][0]["official_slice"] == (
        "分期( 分批) 实施工程的开、\n竣工日期及工期一览表"
    )


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


def test_validate_pgo_runtime_supply_blocks_records_missing_ground() -> None:
    from deeptutor.services.construction_grading.case_rubric_pgo_supply import (
        build_pgo_runtime_supply,
        validate_pgo_runtime_supply,
    )

    bundle = build_pgo_runtime_supply([_contract()])
    bundle["records"][0].pop("authority_source", None)
    bundle["records"][1]["span_hash"] = ""

    blockers = validate_pgo_runtime_supply(bundle)

    assert "record_missing_authority_source:Q-PGO:sp_a" in blockers
    assert "record_missing_span_hash:Q-PGO:sp_b" in blockers
