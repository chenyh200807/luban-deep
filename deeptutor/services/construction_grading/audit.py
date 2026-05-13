from __future__ import annotations

from typing import Any


def evaluate_grading_supabase_audit(raw_report: dict[str, Any]) -> dict[str, Any]:
    questions = raw_report.get("questions_bank") if isinstance(raw_report.get("questions_bank"), dict) else {}
    evidence_tables = (
        raw_report.get("online_evidence_tables")
        if isinstance(raw_report.get("online_evidence_tables"), dict)
        else {}
    )
    mcq = questions.get("field_fill_mcq") if isinstance(questions.get("field_fill_mcq"), dict) else {}
    case = questions.get("field_fill_case") if isinstance(questions.get("field_fill_case"), dict) else {}
    issues: list[dict[str, Any]] = []
    ready_modes: list[str] = []

    if int(mcq.get("total") or 0) >= 100 and int(mcq.get("correct_answer__filled") or 0) >= 100:
        ready_modes.append("mcq_deterministic_ready")
    else:
        issues.append({"severity": "blocker", "code": "mcq_answer_assets_insufficient"})

    if int(case.get("total") or 0) >= 100 and int(case.get("correct_answer__filled") or 0) >= 100:
        if int(case.get("grading_keywords__filled") or 0) > 0 or int(case.get("structured_rules__filled") or 0) > 0:
            ready_modes.append("projected_rubric_ready")
        else:
            issues.append({"severity": "warning", "code": "case_projection_fields_sparse"})
    else:
        issues.append({"severity": "blocker", "code": "case_answer_assets_insufficient"})

    if int(case.get("grading_rubric__filled") or 0) > 0:
        ready_modes.append("curated_rubric_ready")
    else:
        issues.append(
            {
                "severity": "warning",
                "code": "curated_rubric_empty",
                "message": "questions_bank.grading_rubric exists but has no meaningful rows; use projected_rubric/open_skill first.",
            }
        )

    if _table_count(evidence_tables, "kb_chunks") <= 0:
        issues.append({"severity": "blocker", "code": "kb_chunks_missing"})
    if _table_count(evidence_tables, "standard_articles") <= 0:
        issues.append({"severity": "warning", "code": "standard_articles_missing"})
    if _table_count(evidence_tables, "syllabus_tree") <= 0:
        issues.append({"severity": "warning", "code": "syllabus_tree_missing"})
    if "projected_rubric_ready" in ready_modes and _table_count(evidence_tables, "kb_chunks") > 0:
        ready_modes.append("source_grounding_ready")

    status = "fail" if any(issue["severity"] == "blocker" for issue in issues) else "pass"
    return {
        "status": status,
        "ready_modes": ready_modes,
        "issues": issues,
        "summary": {
            "questions_total": int(questions.get("count_total") or 0),
            "mcq_total": int(mcq.get("total") or 0),
            "case_total": int(case.get("total") or 0),
            "case_grading_rubric_filled": int(case.get("grading_rubric__filled") or 0),
            "case_grading_keywords_filled": int(case.get("grading_keywords__filled") or 0),
            "case_structured_rules_filled": int(case.get("structured_rules__filled") or 0),
            "kb_chunks_total": _table_count(evidence_tables, "kb_chunks"),
        },
    }


def _table_count(tables: dict[str, Any], table: str) -> int:
    payload = tables.get(table) if isinstance(tables.get(table), dict) else {}
    if not payload.get("exists"):
        return 0
    return int(payload.get("count_total") or 0)
