from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage


def test_diagnostic_v1_has_20_units_with_16_scored_and_4_profile() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")

    assert blueprint.version == "diagnostic_v1"
    assert blueprint.requested_count == 20
    assert blueprint.scored_count == 16
    assert blueprint.profile_count == 4
    assert sum(section.count for section in blueprint.sections) == 20
    assert sum(section.count for section in blueprint.sections if section.scored) == 16
    assert sum(section.count for section in blueprint.sections if not section.scored) == 4


def test_calculation_is_optional_and_structured_judgment_is_fallback() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    comprehensive = next(section for section in blueprint.sections if section.id == "comprehensive_application")

    assert comprehensive.count == 2
    assert "case_study" in comprehensive.question_types
    assert "calculation" in comprehensive.question_types
    assert "structured_judgment" in comprehensive.fallback_question_types
    assert comprehensive.hard_require_calculation is False


def test_coverage_passes_when_every_section_has_three_x_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "pass"
    assert report["requested_count"] == 20
    assert report["issues"] == []


def test_coverage_fails_closed_when_a_section_is_missing_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
        if section.id != "planning_schedule"
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "fail"
    assert any(issue["section_id"] == "planning_schedule" for issue in report["issues"])
    assert any(issue["code"] == "insufficient_candidates" for issue in report["issues"])


def test_question_bank_id_is_required_but_source_chunk_id_is_only_warning() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": 0 if section.id == "main_structure" else section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": section.count if "calculation" in section.question_types else 0,
            "structured_judgment_count": section.count,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "fail"
    assert any(issue["code"] == "missing_question_id_provenance" for issue in report["issues"])
    assert any(issue["code"] == "weak_source_chunk_trace" for issue in report["issues"])


def test_sparse_calculation_uses_structured_judgment_warning_not_blocker() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "with_source_chunk_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["status"] == "pass"
    assert any(issue["code"] == "calculation_fallback_used" for issue in report["issues"])
