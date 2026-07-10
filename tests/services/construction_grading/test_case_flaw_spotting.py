"""AI 错答挑错:泛泛而谈错答漏了哪些采分点(确定性)+ 学员挑错判分。"""
from __future__ import annotations

from deeptutor.services.construction_grading.case_flaw_spotting import (
    compute_expression_gaps,
    grade_flaw_spotting,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
)

_REF = SourceRef("exam_reference_answer", "起鼓割补")


def _point(pid, *terms):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no="起鼓割补", qid="Q::s1", sub_qid="Q::s1", statement=f"s-{pid}",
        authority_source="official_answer", point_type=PointType.PROCEDURE,
        required_terms=tuple(terms), acceptable_variants=(AcceptableVariant("_", _REF),),
        max_score=0.3, textbook_source_refs=(_REF,), answer_key_authority="official_answer",
    )


_POINTS = [_point("a4", "喷灯烘烤"), _point("a5", "分层剥开"), _point("a6", "重新粘贴")]


def test_vague_expression_gaps_are_deterministic():
    # "起鼓了就割开重新粘贴":含"重新粘贴"(a6命中),漏"喷灯烘烤"(a4)、"分层剥开"(a5)。
    gaps = compute_expression_gaps("起鼓了就割开重新粘贴", _POINTS)
    assert gaps == frozenset({"a4", "a5"})


def test_student_spots_exact_missing_set_correct():
    r = grade_flaw_spotting("起鼓了就割开重新粘贴", _POINTS, ["a4", "a5"])
    assert r.correct is True
    assert r.official_score_allowed is False


def test_student_partial_or_wrong_spot_is_incorrect():
    assert grade_flaw_spotting("起鼓了就割开重新粘贴", _POINTS, ["a4"]).correct is False       # 漏挑 a5
    assert grade_flaw_spotting("起鼓了就割开重新粘贴", _POINTS, ["a4", "a5", "a6"]).correct is False  # 多挑 a6(a6没漏)
    assert grade_flaw_spotting("起鼓了就割开重新粘贴", _POINTS, []).correct is False


def test_full_answer_has_no_gaps():
    full = "喷灯烘烤旧卷材槎口,分层剥开,重新粘贴新卷材"
    assert compute_expression_gaps(full, _POINTS) == frozenset()
    assert grade_flaw_spotting(full, _POINTS, []).correct is True  # 无漏点,学员选空=对
