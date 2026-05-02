from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deeptutor.services.assessment.blueprint import AssessmentBlueprint


@dataclass(frozen=True)
class AssessmentCoverageIssue:
    section_id: str
    severity: str
    code: str
    message: str


def evaluate_blueprint_coverage(
    blueprint: AssessmentBlueprint,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_section = {row["section_id"]: row for row in rows}
    issues: list[AssessmentCoverageIssue] = []
    section_reports: list[dict[str, Any]] = []

    for section in blueprint.sections:
        required_candidates = section.count * section.minimum_multiplier
        row = by_section.get(section.id, {})
        candidate_count = int(row.get("candidate_count") or 0)
        with_question_id = int(row.get("with_question_id") or 0)
        with_source_chunk_id = int(row.get("with_source_chunk_id") or 0)
        renderable_count = int(row.get("renderable_count") or 0)
        calculation_count = int(row.get("calculation_count") or 0)
        structured_judgment_count = int(row.get("structured_judgment_count") or 0)

        if candidate_count < required_candidates:
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="blocker",
                    code="insufficient_candidates",
                    message=f"{section.label} requires {required_candidates} candidates, found {candidate_count}",
                )
            )

        if with_question_id < required_candidates:
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="blocker",
                    code="missing_question_id_provenance",
                    message=f"{section.label} has only {with_question_id} candidates with questions_bank.id",
                )
            )

        if renderable_count < required_candidates:
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="blocker",
                    code="not_renderable",
                    message=f"{section.label} has only {renderable_count} renderable candidates",
                )
            )

        if section.scored and with_source_chunk_id < required_candidates:
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="warning",
                    code="weak_source_chunk_trace",
                    message=f"{section.label} has weak source_chunk_id coverage; use questions_bank.id as P0 provenance",
                )
            )

        if section.hard_require_calculation and calculation_count < section.count:
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="blocker",
                    code="insufficient_calculation",
                    message=f"{section.label} hard-requires calculation items, found {calculation_count}",
                )
            )

        if (
            not section.hard_require_calculation
            and "calculation" in section.question_types
            and calculation_count < section.count
            and structured_judgment_count >= section.count
        ):
            issues.append(
                AssessmentCoverageIssue(
                    section_id=section.id,
                    severity="warning",
                    code="calculation_fallback_used",
                    message=f"{section.label} will use structured judgment/case fallback when calculation items are sparse",
                )
            )

        section_reports.append(
            {
                "section_id": section.id,
                "label": section.label,
                "required_units": section.count,
                "required_candidates": required_candidates,
                "candidate_count": candidate_count,
                "with_question_id": with_question_id,
                "with_source_chunk_id": with_source_chunk_id,
                "renderable_count": renderable_count,
                "calculation_count": calculation_count,
                "structured_judgment_count": structured_judgment_count,
            }
        )

    status = "fail" if any(issue.severity == "blocker" for issue in issues) else "pass"
    return {
        "blueprint_version": blueprint.version,
        "status": status,
        "requested_count": blueprint.requested_count,
        "scored_count": blueprint.scored_count,
        "profile_count": blueprint.profile_count,
        "sections": section_reports,
        "issues": [issue.__dict__ for issue in issues],
    }
