"""RTG1–RTG8 Post-gen gate tests (deterministic).

F16 起鼓割补 flavored fixtures. Every gate's BLOCK / SOFT_FAIL / NEEDS_HUMAN /
NOT_EXERCISED path is exercised. The NOT_EXERCISED assertions are the anti-false-green
guard: an ungiven input must surface as NOT_EXERCISED, never as a silent PASS.
"""
from __future__ import annotations

from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
)
from deeptutor.services.construction_grading.case_light_practice_rtg import (
    GateStatus,
    Verdict,
    normalize,
    run_post_gen_gates,
)

_REF = SourceRef("exam_reference_answer", "2017-一建建筑-案例·起鼓割补")


def _point(pid, statement):
    return LubanCaseScoringPoint(
        point_id=pid,
        sub_no="1",
        qid="EXAM_1A434000_P0011_01::E0::sub1",
        sub_qid="EXAM_1A434000_P0011_01::E0::sub1",
        statement=statement,
        authority_source="official_answer",
        point_type=PointType.PROCEDURE,
        required_terms=(),
        acceptable_variants=(AcceptableVariant("v", _REF),),
        max_score=0.3,
        textbook_source_refs=(_REF,),
        answer_key_authority="official_answer",
    )


_POINTS = [
    _point("a5", "分层剥开旧卷材"),
    _point("a4", "喷灯烘烤旧卷材槎口"),
]


def _valid_item():
    return {
        "stem": "起鼓割补处理旧卷材,正确的关键步骤是?",
        "correct_options": [{"text": "分层剥开旧卷材", "source_scoring_point_id": "a5"}],
        "distractors": [
            {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E06"},
            {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
        ],
    }


def _gate(report, gate_id):
    return next(r for r in report.results if r.gate == gate_id)


def test_valid_item_passes():
    report = run_post_gen_gates(_valid_item(), _POINTS)
    assert report.verdict == Verdict.PASS, [f.detail for f in report.failures()]


def test_rtg1_collision_blocks_even_with_punctuation_and_fullwidth():
    item = _valid_item()
    # distractor equals correct after NFKC + punctuation strip
    item["distractors"][0] = {"text": "分层剥开旧卷材。", "error_code": "E06"}
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG1").status == GateStatus.BLOCK
    assert report.verdict == Verdict.BLOCK


def test_rtg2_duplicate_distractors_block():
    item = _valid_item()
    item["distractors"][1] = {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E01"}
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG2").status == GateStatus.BLOCK


def test_rtg3_bad_error_code_blocks():
    item = _valid_item()
    item["distractors"][0]["error_code"] = "E99"
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG3").status == GateStatus.BLOCK


def test_rtg3_needs_review_routes_to_human():
    item = _valid_item()
    item["distractors"][0]["error_code"] = "NEEDS_REVIEW"
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG3").status == GateStatus.NEEDS_HUMAN
    assert report.verdict == Verdict.NEEDS_HUMAN


def test_rtg5_correct_binding_nonexistent_point_blocks():
    item = _valid_item()
    item["correct_options"][0]["source_scoring_point_id"] = "ZZZ"
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG5").status == GateStatus.BLOCK


def test_rtg5_distractor_binding_point_blocks():
    item = _valid_item()
    item["distractors"][0]["source_scoring_point_id"] = "a5"
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG5").status == GateStatus.BLOCK


def test_rtg8_unfaithful_correct_blocks():
    item = _valid_item()
    item["correct_options"][0]["text"] = "把屋面全部铲除重做防水层"  # not faithful to a5
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG8").status == GateStatus.BLOCK


def test_rtg4_not_exercised_without_candidates_and_soft_fail_with():
    # not provided → NOT_EXERCISED (never silent pass)
    report = run_post_gen_gates(_valid_item(), _POINTS)
    assert _gate(report, "RTG4").status == GateStatus.NOT_EXERCISED
    # provided but code outside subset → SOFT_FAIL
    report2 = run_post_gen_gates(_valid_item(), _POINTS, error_code_candidates={"E03"})
    assert _gate(report2, "RTG4").status == GateStatus.SOFT_FAIL
    assert report2.verdict == Verdict.SOFT_FAIL


def test_rtg6_cheap_negation_soft_fails():
    item = _valid_item()
    item["distractors"][0] = {"text": "不分层剥开旧卷材", "error_code": "E06"}
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG6").status == GateStatus.SOFT_FAIL


def test_rtg7_not_exercised_without_group_and_block_with_outside_point():
    report = run_post_gen_gates(_valid_item(), _POINTS)
    assert _gate(report, "RTG7").status == GateStatus.NOT_EXERCISED
    # referenced point a5 not in the consistent set → BLOCK (欠切分 tell)
    report2 = run_post_gen_gates(_valid_item(), _POINTS, consistent_point_ids={"a4"})
    assert _gate(report2, "RTG7").status == GateStatus.BLOCK
    assert report2.verdict == Verdict.BLOCK


def test_rtg6_near_synonym_of_correct_soft_fails():
    # 2026-07-09 live DeepSeek surfaced this: 干扰项「分层剥离旧卷材」差一字近义正确项
    # 「分层剥开旧卷材(关键区分点)」— 确定性高包含率子集,应软拒→可疑/异源,不放行。
    item = _valid_item()
    item["distractors"][0] = {"text": "分层剥离旧卷材", "error_code": "E12"}
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG6").status == GateStatus.SOFT_FAIL
    assert report.verdict == Verdict.SOFT_FAIL


def test_rtg6_legit_distractor_not_flagged_near_correct():
    # 合法干扰项(整体揭开)包含率低,不被近义门误伤
    item = _valid_item()
    item["distractors"] = [
        {"text": "整体揭开旧卷材", "error_code": "E06"},
        {"text": "用铲刀铲除旧卷材", "error_code": "E07"},
    ]
    report = run_post_gen_gates(item, _POINTS)
    assert _gate(report, "RTG6").status == GateStatus.PASS


def test_normalize_folds_fullwidth_and_symbols():
    assert normalize("分层剥开 。") == normalize("分层剥开")
    assert normalize("100㎡") == normalize("100m2")
