"""Focused TDD for the deterministic per-question grading object compiler.

Hard rules under test (single-authority, source-locked):
1. every atomic point is a verbatim substring of the official ``correct_answer``;
2. textbook anchor misses are honestly marked ``unsourced`` (never fabricated);
3. per-point scores stay ``null`` + pending — never minted as official;
4. the schema/object cannot declare itself official truth;
5. span_hash is verified for every point.
"""

from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.per_question_grading_object import (
    A_OFFICIAL,
    GRADING_CONTRACT_SCHEMA_ID,
    PENDING_SCORE_AUTHORITY,
    SCHEMA_ID,
    build_grading_contract,
    classify_sub_type,
    compile_per_question_grading_object,
    render_markdown,
    split_sub_questions,
    validate_grading_contract,
    validate_per_question_grading_object,
)
from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash

# --- real official answer fragments (权威 A, verbatim from the 2023/2024 exam bank) ---

FLAW_ANSWER = (
    "① 不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。\n"
    "正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。\n"
    "② 不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。\n"
    "正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，"
    "单独列支并按照合同约定及时支付。"
)

EXCEPTIONS_ANSWER = (
    "中标单位应避免的违法分包行为包括：\n"
    "（1）将工程分包给不具备相应资质单位的；\n"
    "（2）将主体结构的施工分包给其他单位的，钢结构工程除外；\n"
    "（3）专业工程中非劳务作业部分再分包的。"
)

CALC_ANSWER = (
    "（1）分部分项工程费：6000+100=6100万元。\n"
    "（2）措施项目费：6100×10%=610万元。\n"
    "（6）结算价：6100+610+480+144+660=7994万元。"
)


def _textbook_chunk(chunk_id: str, content: str) -> dict:
    return {"chunk_id": chunk_id, "content_markdown": content}


# --- 1. atomic point must be verbatim substring of official answer ---


def test_every_atomic_slice_is_verbatim_substring_of_official_answer():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="见证记录题干",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    points = [p for s in obj["sub_questions"] for p in s["scoring_points"]]
    assert points, "expected at least one scoring point"
    for point in points:
        assert point["atomic_official_slice"] in FLAW_ANSWER
        # flaw / correction halves are also verbatim
        if point.get("flaw_span"):
            assert point["flaw_span"] in FLAW_ANSWER
            assert point["correction_span"] in FLAW_ANSWER


def test_flaw_correction_splits_two_paired_points():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    points = [p for s in obj["sub_questions"] for p in s["scoring_points"]]
    assert len(points) == 2
    for point in points:
        assert point["sub_type"] == "flaw_correction"
        assert point["pairing"] == "flaw_AND_correction_both_required"
        assert point["flaw_span"]
        assert point["correction_span"]


# --- 2. unsourced textbook anchor is honestly flagged, not fabricated ---


def test_textbook_anchor_hit_when_term_in_chunk():
    chunk = _textbook_chunk("kb_57", "见证记录应由见证人员填写并制作见证记录")
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[chunk],
    )
    provs = [
        prov
        for s in obj["sub_questions"]
        for p in s["scoring_points"]
        for prov in p["term_provenance"]
    ]
    verified = [prov for prov in provs if prov["anchor_verified"]]
    assert verified, "expected at least one verified textbook anchor"
    for prov in verified:
        assert prov["chunk_id"] == "kb_57"
        assert prov["span_hash"] == source_span_hash(chunk["content_markdown"])


def test_unsourced_term_has_null_chunk_and_is_not_fabricated():
    # no textbook chunks at all -> every term must be unsourced, none invented
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    provs = [
        prov
        for s in obj["sub_questions"]
        for p in s["scoring_points"]
        for prov in p["term_provenance"]
    ]
    assert provs, "expected term provenance entries"
    for prov in provs:
        assert prov["anchor_verified"] is False
        assert prov["chunk_id"] is None
        assert prov["span_hash"] is None
        assert prov["authority_source"] == "unsourced"
    assert obj["textbook_anchor_hit"] == 0
    assert obj["textbook_anchor_hit_rate"] in (0.0, None)


# --- 3. per-point score is never minted as official ---


def test_per_point_score_is_null_and_pending_never_official():
    obj = compile_per_question_grading_object(
        question_id="Q2024-CALC",
        stem="x",
        correct_answer=CALC_ANSWER,
        official_total_score=22.0,
        textbook_chunks=[],
    )
    assert obj["official_total_score"] == 22.0
    assert obj["official_total_score_authority"] == A_OFFICIAL
    points = [p for s in obj["sub_questions"] for p in s["scoring_points"]]
    assert points
    for point in points:
        assert point["score"] is None
        assert point["score_authority"] == PENDING_SCORE_AUTHORITY
    # total is NOT distributed across points: sum of (mintable) point scores stays absent
    assert obj["per_point_score_authority"] == PENDING_SCORE_AUTHORITY


def test_calculation_keeps_official_equation_literal_no_recompute_mint():
    obj = compile_per_question_grading_object(
        question_id="Q2024-CALC",
        stem="x",
        correct_answer=CALC_ANSWER,
        official_total_score=22.0,
        textbook_chunks=[],
    )
    calc_points = [
        p
        for s in obj["sub_questions"]
        for p in s["scoring_points"]
        if p["sub_type"] == "calculation"
    ]
    assert calc_points
    for point in calc_points:
        fs = point["formula_step"]
        assert fs["verification_mode"] == "deterministic_recalculation_required"
        # the expected value is the official literal, not a recomputed mint
        assert fs["expected_value_literal"] in CALC_ANSWER


# --- exceptions sub-type ---


def test_exceptions_extracts_base_rule_and_exception_items_verbatim():
    obj = compile_per_question_grading_object(
        question_id="Q2024-EXC",
        stem="x",
        correct_answer=EXCEPTIONS_ANSWER,
        official_total_score=22.0,
        textbook_chunks=[],
    )
    exc_points = [
        p
        for s in obj["sub_questions"]
        for p in s["scoring_points"]
        if p["sub_type"] == "exceptions"
    ]
    assert exc_points, "expected the 钢结构工程除外 point classified as exceptions"
    point = exc_points[0]
    assert point["exception_items"]
    for item in point["exception_items"]:
        assert "除外" in item
        assert item in EXCEPTIONS_ANSWER


# --- 4. schema cannot declare itself official truth ---


def test_object_cannot_declare_official_truth():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    assert obj["schema_id"] == SCHEMA_ID
    assert obj["official_score_allowed"] is False
    assert obj["canonical_write_allowed"] is False
    assert validate_per_question_grading_object(obj) == []


def test_validator_rejects_minted_per_point_score():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    # tamper: mint an official per-point score
    obj["sub_questions"][0]["scoring_points"][0]["score"] = 3.5
    blockers = validate_per_question_grading_object(obj)
    assert any(b.startswith("per_point_score_minted") for b in blockers)


def test_validator_rejects_official_score_allowed_true():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    obj["official_score_allowed"] = True
    blockers = validate_per_question_grading_object(obj)
    assert "official_score_allowed_must_be_false" in blockers


def test_validator_rejects_forbidden_minted_property():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    obj["minted_per_point_score"] = 1.0
    blockers = validate_per_question_grading_object(obj)
    assert "forbidden_property:minted_per_point_score" in blockers


# --- 5. span_hash verification ---


def test_span_hash_matches_official_slice_for_every_point():
    obj = compile_per_question_grading_object(
        question_id="Q2024-CALC",
        stem="x",
        correct_answer=CALC_ANSWER,
        official_total_score=22.0,
        textbook_chunks=[],
    )
    for sub in obj["sub_questions"]:
        for point in sub["scoring_points"]:
            assert point["span_hash"] == source_span_hash(point["atomic_official_slice"])
    assert validate_per_question_grading_object(obj) == []


def test_validator_detects_span_hash_tamper():
    obj = compile_per_question_grading_object(
        question_id="Q2024-CALC",
        stem="x",
        correct_answer=CALC_ANSWER,
        official_total_score=22.0,
        textbook_chunks=[],
    )
    obj["sub_questions"][0]["scoring_points"][0]["span_hash"] = "deadbeef"
    blockers = validate_per_question_grading_object(obj)
    assert any(b.startswith("span_hash_mismatch") for b in blockers)


# --- helper-level units ---


def test_split_sub_questions_uses_answer_own_numbering():
    answer = "1. 第一问答案。\n2. 第二问答案。\n3. 第三问答案。"
    subs = split_sub_questions(answer)
    assert [n for n, _ in subs] == [1, 2, 3]
    for _, body in subs:
        assert body in answer


def test_classify_sub_type_is_deterministic():
    assert classify_sub_type("不妥之处：x。正确做法：y。") == "flaw_correction"
    assert classify_sub_type("将主体结构分包，钢结构工程除外。") == "exceptions"
    assert classify_sub_type("措施项目费：6100×10%=610万元。") == "calculation"
    assert classify_sub_type("记录内容还包括：取样、制样、标识。") == "enumeration"


def test_render_markdown_contains_official_total_and_pending_marker():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="见证记录题干",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    md = render_markdown(obj)
    assert "整题总分" in md
    assert "7.0 分" in md
    assert PENDING_SCORE_AUTHORITY in md
    assert "不伪造" in md  # unsourced honesty surfaced in render


@pytest.mark.parametrize("score", [None, 6.0, 22.0])
def test_total_score_passthrough_is_official_only(score):
    obj = compile_per_question_grading_object(
        question_id="Q-X",
        stem="x",
        correct_answer=CALC_ANSWER,
        official_total_score=score,
        textbook_chunks=[],
    )
    assert obj["official_total_score"] == score


# --- G2 wiring on real data: per-question object -> judge-ready grading contract ---


def _flaw_contract_with_textbook():
    chunk = _textbook_chunk("kb_57", "见证记录应由见证人员填写并制作见证记录")
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="见证记录题干",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[chunk],
    )
    return obj, build_grading_contract(obj)


def test_contract_scoring_points_are_official_atomic_checklist():
    obj, contract = _flaw_contract_with_textbook()
    assert contract["contract_schema"] == GRADING_CONTRACT_SCHEMA_ID
    assert contract["official_total_score"] == 7.0
    # every scoring point is an official atomic slice (authority A) with a span_hash
    assert contract["scoring_points"]
    assert len(contract["scoring_points"]) == obj["scoring_point_count"]
    for sp in contract["scoring_points"]:
        assert sp["authority_source"] == A_OFFICIAL
        assert sp["span_hash"]
        assert sp["official_slice"]


def test_contract_g2_routes_textbook_citations_to_supporting_only():
    # G2 on REAL data: verified textbook anchors ride as supporting citations,
    # stamped official_score_allowed=False, never the correctness channel.
    _obj, contract = _flaw_contract_with_textbook()
    assert contract["supporting_citations"], "expected verified textbook citations"
    assert contract["g2_role"]["official_decides_correctness"] is True
    assert contract["g2_role"]["rich_leaf_role"] == "supporting_citation_only"
    for cite in contract["supporting_citations"]:
        assert cite["official_score_allowed"] is False
        assert cite["authority_source"] != A_OFFICIAL
    assert validate_grading_contract(contract) == []


def test_contract_empty_textbook_yields_no_op_supporting_but_keeps_checklist():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="x",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],  # no anchors -> no supporting citations (G2 no-op)
    )
    contract = build_grading_contract(obj)
    assert contract["supporting_citations"] == []
    assert contract["scoring_points"], "official atomic checklist still present"
    assert validate_grading_contract(contract) == []


def test_contract_validator_blocks_supporting_citation_claiming_official():
    # Fail-closed G2 proof: a tampered supporting citation that claims official
    # authority must be rejected (assert_supporting_only raises -> blocker surfaced).
    _obj, contract = _flaw_contract_with_textbook()
    contract["supporting_citations"][0]["official_score_allowed"] = True
    blockers = validate_grading_contract(contract)
    assert any("supporting_citation" in b for b in blockers)


def test_contract_output_contract_forces_per_point_verdict_and_cite():
    _obj, contract = _flaw_contract_with_textbook()
    oc = contract["output_contract"]
    assert oc["must_emit_one_verdict_per_point_id"] is True
    assert oc["must_cite_student_evidence_span_for_hit"] is True
    assert oc["over_credit_invalid_if_high_score_with_any_miss"] is True
    assert "hit" in oc["verdict_enum"] and "miss" in oc["verdict_enum"]


def test_contract_does_not_mint_per_point_scores():
    _obj, contract = _flaw_contract_with_textbook()
    # the contract carries the pending (non-official) per-point authority marker and
    # never assigns a numeric per-point score (per-point scores have no canonical truth).
    assert contract["per_point_score_authority"] == PENDING_SCORE_AUTHORITY
    assert contract["official_score_allowed"] is False
    for sp in contract["scoring_points"]:
        assert "score" not in sp or sp.get("score") is None
