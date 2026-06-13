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
    candidate_coverage_score,
    detect_over_credit,
    make_controlled_student_answers,
    oracle_verdicts,
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
