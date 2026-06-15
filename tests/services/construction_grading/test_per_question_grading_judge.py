"""TDD for the deterministic judge-side logic of the per-question grading A/B.

Under test (the KnowQL Phase B mechanism, review-only):
1. controlled student answers carry EXACT ground truth (covered/missing point_ids);
2. the oracle judge HITs covered points and MISSes omitted ones;
3. the candidate coverage score = fraction of atomic official points hit (not minted);
4. the over-credit gate flags a high score with ANY missed official point as invalid.
"""

from __future__ import annotations

from deeptutor.services.construction_grading.per_question_grading_judge import (
    HIT,
    MISS,
    OVER_CREDIT_HIGH_THRESHOLD,
    PARTIAL,
    candidate_coverage_score,
    build_pgo_shadow_payload,
    ground_gate_contract_for_scoring,
    detect_over_credit,
    make_controlled_student_answers,
    oracle_verdicts,
    pgo_contract_from_knowql_rubric_result,
    pgo_point_verdicts_from_luban_case_rubric_payload,
    runtime_points_from_grading_contract,
    verdict_coverage_awarded_score,
)
from deeptutor.services.construction_grading.per_question_grading_object import (
    build_grading_contract,
    compile_per_question_grading_object,
)

# real official answer (权威 A, verbatim) — flaw_correction yields 2 atomic points
FLAW_ANSWER = (
    "① 不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。\n"
    "正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。\n"
    "② 不妥之处：总包项目部按照建设单位要求，每月向检测机构支付当期检测费用。\n"
    "正确做法：建设单位应当在编制工程概预算时合理核算建设工程质量检测费用，"
    "单独列支并按照合同约定及时支付。"
)


def _obj_and_contract():
    obj = compile_per_question_grading_object(
        question_id="Q2023-FLAW",
        stem="见证记录题干",
        correct_answer=FLAW_ANSWER,
        official_total_score=7.0,
        textbook_chunks=[],
    )
    return obj, build_grading_contract(obj)


def test_controlled_answers_carry_exact_ground_truth():
    obj, _contract = _obj_and_contract()
    cases = make_controlled_student_answers(obj)
    labels = {c.label for c in cases}
    assert "complete" in labels
    complete = next(c for c in cases if c.label == "complete")
    assert complete.missing_point_ids == ()
    drop_last = next(c for c in cases if c.label == "drop_last")
    assert len(drop_last.missing_point_ids) == 1
    # covered + missing partition all points, no overlap
    for c in cases:
        assert not (set(c.covered_point_ids) & set(c.missing_point_ids))


def test_oracle_hits_covered_misses_omitted():
    obj, contract = _obj_and_contract()
    drop_last = next(
        c for c in make_controlled_student_answers(obj) if c.label == "drop_last"
    )
    verdicts = oracle_verdicts(contract, drop_last)
    for pid in drop_last.covered_point_ids:
        assert verdicts[pid] == HIT
    for pid in drop_last.missing_point_ids:
        assert verdicts[pid] == MISS


def test_candidate_coverage_score_complete_is_full_partial_is_less():
    obj, contract = _obj_and_contract()
    cases = make_controlled_student_answers(obj)
    complete = next(c for c in cases if c.label == "complete")
    drop_last = next(c for c in cases if c.label == "drop_last")
    assert candidate_coverage_score(oracle_verdicts(contract, complete), contract) == 1.0
    assert candidate_coverage_score(oracle_verdicts(contract, drop_last), contract) < 1.0


def test_over_credit_gate_flags_high_score_with_any_miss():
    obj, contract = _obj_and_contract()
    drop_last = next(
        c for c in make_controlled_student_answers(obj) if c.label == "drop_last"
    )
    verdicts = oracle_verdicts(contract, drop_last)
    # a judge that claims ~full marks despite the missed point is over-credit (invalid)
    result = detect_over_credit(score_pct=0.98, point_verdicts=verdicts, contract=contract)
    assert result["over_credit"] is True
    assert result["invalid"] is True
    assert result["miss_count"] == 1


def test_over_credit_gate_clean_when_score_matches_coverage():
    obj, contract = _obj_and_contract()
    drop_last = next(
        c for c in make_controlled_student_answers(obj) if c.label == "drop_last"
    )
    verdicts = oracle_verdicts(contract, drop_last)
    coverage = candidate_coverage_score(verdicts, contract)
    # a score that honestly reflects coverage (below threshold) is NOT over-credit
    result = detect_over_credit(
        score_pct=coverage, point_verdicts=verdicts, contract=contract
    )
    assert result["over_credit"] is False


def test_over_credit_gate_honest_high_coverage_is_not_flagged():
    # Root-cause-correct semantics: covering 23/24 official points and scoring 0.958 is
    # HONEST proportional credit, NOT over-credit. Over-credit = score exceeds coverage.
    contract = {
        "scoring_points": [{"point_id": f"p{i}"} for i in range(24)],
    }
    verdicts = {f"p{i}": HIT for i in range(23)}
    verdicts["p23"] = MISS  # 23/24 hit -> coverage 0.958
    result = detect_over_credit(score_pct=0.958, point_verdicts=verdicts, contract=contract)
    assert result["over_credit"] is False, "score tracking coverage must not be over-credit"
    # but claiming full marks (1.0) while a sub-point is missed IS over-credit
    inflated = detect_over_credit(score_pct=1.0, point_verdicts=verdicts, contract=contract)
    # gap 1.0 - 0.958 = 0.042 < margin 0.1 -> still honest; need a real coverage shortfall
    assert inflated["over_credit"] is False
    # a genuine missed sub-question: 18/24 covered (0.75) but judge claims 1.0
    short = {f"p{i}": HIT for i in range(18)}
    for i in range(18, 24):
        short[f"p{i}"] = MISS
    flagged = detect_over_credit(score_pct=1.0, point_verdicts=short, contract=contract)
    assert flagged["over_credit"] is True
    assert flagged["score_coverage_gap"] > 0.2


def test_over_credit_gate_complete_high_score_is_fine():
    obj, contract = _obj_and_contract()
    complete = next(
        c for c in make_controlled_student_answers(obj) if c.label == "complete"
    )
    verdicts = oracle_verdicts(contract, complete)
    result = detect_over_credit(
        score_pct=1.0, point_verdicts=verdicts, contract=contract
    )
    # full marks with no missed point is correct, not over-credit
    assert result["over_credit"] is False
    assert result["miss_count"] == 0
    assert OVER_CREDIT_HIGH_THRESHOLD <= 1.0


def _stage2_contract():
    return {
        "contract_schema": "luban_per_question_grading_contract.v1",
        "question_id": "Q-STAGE2",
        "official_total_score": 10.0,
        "official_total_score_authority": "official_answer_verbatim",
        "official_score_allowed": False,
        "canonical_write_allowed": False,
        "scoring_points": [
            {
                "point_id": "sp_flaw",
                "sub_type": "flaw_correction",
                "official_slice": "不妥之处：x。正确做法：y。",
                "authority_source": "official_answer_verbatim",
                "span_hash": "sha256:sp_flaw",
                "score": None,
            },
            {
                "point_id": "sp_exception",
                "sub_type": "exceptions",
                "official_slice": "主体结构不得分包，钢结构工程除外。",
                "authority_source": "official_answer_verbatim",
                "span_hash": "sha256:sp_exception",
                "score": None,
            },
            {
                "point_id": "sp_calc",
                "sub_type": "calculation",
                "official_slice": "措施项目费：6100×10%=610万元。",
                "authority_source": "official_answer_verbatim",
                "span_hash": "sha256:sp_calc",
                "score": None,
            },
            {
                "point_id": "sp_enum",
                "sub_type": "enumeration",
                "official_slice": "记录内容还包括取样、制样、标识。",
                "authority_source": "official_answer_verbatim",
                "span_hash": "sha256:sp_enum",
                "score": None,
            },
            {
                "point_id": "sp_free",
                "sub_type": "free_text_point",
                "official_slice": "建设单位应及时支付检测费用。",
                "authority_source": "official_answer_verbatim",
                "span_hash": "sha256:sp_free",
                "score": None,
            },
        ],
        "supporting_citations": [
            {
                "point_id": "sp_enum",
                "term": "取样",
                "chunk_id": "kb_1",
                "official_score_allowed": False,
            },
            {
                "point_id": "sp_enum",
                "term": "未验证术语",
                "chunk_id": None,
                "anchor_verified": False,
                "official_score_allowed": False,
            },
            {
                "point_id": "sp_enum",
                "term": "越权术语",
                "chunk_id": "kb_2",
                "anchor_verified": True,
                "official_score_allowed": True,
            },
        ],
    }


def test_runtime_points_adapter_maps_all_stage2_sub_types_without_minting_score():
    runtime_points = runtime_points_from_grading_contract(_stage2_contract())
    by_id = {p["point_id"]: p for p in runtime_points}

    assert by_id["sp_flaw"]["policy_type"] == "qualitative"
    assert by_id["sp_exception"]["policy_type"] == "qualitative"
    assert by_id["sp_calc"]["policy_type"] == "calculation"
    assert by_id["sp_enum"]["policy_type"] == "list"
    assert by_id["sp_free"]["policy_type"] == "qualitative"
    assert {p["score"] for p in runtime_points} == {None}
    assert {p["max_score"] for p in runtime_points} == {None}


def test_runtime_points_adapter_preserves_case_shape_constraints_and_exact_terms():
    contract = _stage2_contract()
    contract["case_shape_constraints"] = {
        "penalty_rule": {
            "exists": True,
            "type": "multi_answer_no_score",
            "trigger": {"max_answered_items": 2, "pattern": "不妥"},
            "applies_to_sub_types": ["flaw_correction"],
            "text": "本问题2项不妥，多答不得分",
        },
        "list_rule": {"applies": True, "total_items": 6},
    }
    contract["scoring_points"][0]["exact_term_required"] = True
    contract["scoring_points"][0]["case_shape_role"] = "flaw_correction"
    contract["scoring_points"][0]["penalty_scoped"] = True
    contract["scoring_points"][3]["exact_term_required"] = True
    contract["scoring_points"][3]["case_shape_role"] = "enumeration"
    contract["scoring_points"][3]["penalty_scoped"] = False

    runtime_points = runtime_points_from_grading_contract(contract)
    by_id = {p["point_id"]: p for p in runtime_points}

    assert by_id["sp_flaw"]["policy_type"] == "exact_required"
    assert by_id["sp_flaw"]["case_shape_role"] == "flaw_correction"
    assert by_id["sp_flaw"]["penalty_scoped"] is True
    assert by_id["sp_flaw"]["case_shape_constraints"]["penalty_rule"]["type"] == "multi_answer_no_score"
    assert by_id["sp_enum"]["policy_type"] == "exact_required"
    assert by_id["sp_enum"]["case_shape_role"] == "enumeration"
    assert by_id["sp_enum"]["penalty_scoped"] is False


def test_runtime_points_required_terms_only_use_verified_supporting_citations():
    runtime_points = runtime_points_from_grading_contract(_stage2_contract())
    enum_point = next(p for p in runtime_points if p["point_id"] == "sp_enum")

    assert enum_point["required_terms"] == ["取样"]
    assert "未验证术语" not in enum_point["required_terms"]
    assert "越权术语" not in enum_point["required_terms"]
    assert enum_point["term_authority"] == "textbook_cited_supporting_only"


def test_verdict_coverage_score_uses_official_total_not_null_point_scores():
    contract = _stage2_contract()
    verdicts = {
        "sp_flaw": HIT,
        "sp_exception": PARTIAL,
        "sp_calc": MISS,
        "sp_enum": HIT,
        "sp_free": MISS,
    }

    result = verdict_coverage_awarded_score(verdicts, contract)

    # (1 + 0.5 + 0 + 1 + 0) / 5 * official total 10 = 5.
    assert result["coverage"] == 0.5
    assert result["awarded_score"] == 5.0
    assert result["max_score"] == 10.0
    assert result["score_authority"] == "official_total_x_verdict_coverage"
    assert result["official_score_allowed"] is False
    assert result["canonical_write_allowed"] is False


def test_verdict_coverage_score_fails_closed_without_official_total():
    contract = _stage2_contract()
    contract["official_total_score"] = None

    result = verdict_coverage_awarded_score({"sp_flaw": HIT}, contract)

    assert result["awarded_score"] == 0.0
    assert result["max_score"] == 0.0
    assert result["coverage"] == 0.0
    assert result["blockers"] == ["missing_official_total_score"]


def test_pgo_shadow_payload_is_non_authoritative_and_append_only_shape():
    payload = build_pgo_shadow_payload(
        contract=_stage2_contract(),
        point_verdicts={
            "sp_flaw": HIT,
            "sp_exception": PARTIAL,
            "sp_calc": MISS,
            "sp_enum": HIT,
            "sp_free": MISS,
        },
        question_id="Q-STAGE2",
        student_id="qa_pgo",
    )

    assert payload["authority"] == "luban_case_rubric_pgo_shadow"
    assert payload["shadow_status"] == "ok"
    assert payload["score"]["awarded_score"] == 5.0
    assert payload["score"]["score_authority"] == "official_total_x_verdict_coverage"
    assert payload["official_score_allowed"] is False
    assert payload["canonical_write_allowed"] is False
    assert payload["writeback_performed"] is False
    assert payload["runtime_points"][0]["score"] is None


def test_pgo_shadow_payload_blocks_ungrounded_points_from_score_bearing_verdicts():
    contract = _stage2_contract()
    del contract["scoring_points"][0]["authority_source"]
    del contract["scoring_points"][0]["span_hash"]

    payload = build_pgo_shadow_payload(
        contract=contract,
        point_verdicts={
            "sp_flaw": HIT,
            "sp_exception": HIT,
            "sp_calc": HIT,
            "sp_enum": HIT,
            "sp_free": HIT,
        },
        question_id="Q-STAGE2",
        student_id="qa_pgo",
    )

    assert payload["shadow_status"] == "blocked"
    assert payload["score"]["awarded_score"] == 0.0
    assert "scoring_point_missing_authority_source:sp_flaw" in payload["score"]["blockers"]
    assert "scoring_point_missing_span_hash:sp_flaw" in payload["score"]["blockers"]
    blocked = [point for point in payload["runtime_points"] if point["point_id"] == "sp_flaw"][0]
    assert blocked["score_bearing"] is False
    assert blocked["explanation_only"] is True
    assert blocked["ground_status"] == "blocked"


def test_ground_gate_contract_for_scoring_marks_all_points_score_bearing_when_grounded():
    gated = ground_gate_contract_for_scoring(_stage2_contract())

    assert gated["ok"] is True
    assert gated["blockers"] == []
    assert all(point["score_bearing"] is True for point in gated["runtime_points"])
    assert all(point["explanation_only"] is False for point in gated["runtime_points"])


def test_pgo_shadow_payload_missing_contract_does_not_infer_from_legacy_score():
    payload = build_pgo_shadow_payload(
        contract=None,
        point_verdicts={"sp_flaw": HIT},
        question_id="Q-STAGE2",
        student_id="qa_pgo",
    )

    assert payload["shadow_status"] == "pgo_contract_missing"
    assert payload["score"]["awarded_score"] == 0.0
    assert payload["score"]["blockers"] == ["pgo_contract_missing"]
    assert payload["runtime_points"] == []


def test_pgo_contract_from_knowql_rubric_result_adapts_read_only_projection():
    result = {
        "found": True,
        "question_id": "Q-PGO",
        "artifact_version": "case_rubric_scored_pgo",
        "scoring_points": [
            {
                "point_id": "P1",
                "official_slice": "施工总进度计划表",
                "sub_type": "free_text_point",
                "official_total_score": 5.0,
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            },
            {
                "point_id": "P2",
                "official_slice": "资源需要量及供应平衡表",
                "sub_type": "enumeration",
                "official_total_score": 5.0,
                "official_score_allowed": False,
                "canonical_write_allowed": False,
            },
        ],
    }

    contract = pgo_contract_from_knowql_rubric_result(result)

    assert contract is not None
    assert contract["question_id"] == "Q-PGO"
    assert contract["artifact_version"] == "case_rubric_scored_pgo"
    assert contract["official_total_score"] == 5.0
    assert contract["official_score_allowed"] is False
    assert contract["canonical_write_allowed"] is False
    assert [point["point_id"] for point in contract["scoring_points"]] == ["P1", "P2"]
    assert contract["scoring_points"][0]["score"] is None


def test_pgo_contract_from_knowql_rubric_result_keeps_fail_open_blocked():
    contract = pgo_contract_from_knowql_rubric_result(
        {
            "found": False,
            "fail_open": True,
            "reason": "runtime_supply_unavailable",
            "scoring_points": [{"point_id": "P1"}],
        }
    )

    assert contract is None


def test_pgo_point_verdicts_from_luban_case_rubric_payload_reads_same_attempt_hits():
    verdicts = pgo_point_verdicts_from_luban_case_rubric_payload(
        {
            "authority": "luban_case_rubric_v1",
            "status": "ok",
            "learning_evidence": {
                "rubric": {
                    "scoring_point_hits": [
                        {"point_id": "P1", "hit": True, "match_status": "hit"},
                        {"point_id": "P2", "hit": False, "match_status": "miss"},
                        {"point_id": "P3", "match_status": "partial"},
                    ]
                }
            },
        }
    )

    assert verdicts == {"P1": HIT, "P2": MISS, "P3": PARTIAL}
