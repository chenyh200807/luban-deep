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


# ─── Phase -1.A: Rubric Coverage Classification (read-only) ────────────────
#
# Mirrors the 4-tier authority in ``case_kernel.py``:
#   1. ``grading_key.scoring_points`` (highest authority, from active_object)
#   2. ``row.grading_rubric`` (curated rubric)
#   3. projected_rubric (legacy keyword / structured_rules projection)
#   4. open_skill (no formal rubric)
#
# The scoring-point map UI may light up per-cluster once ``map_eligible_ratio``
# crosses 0.70. Items in tier 3/4 stay in ``rubric_pending`` empty state.


def classify_rubric_coverage(*, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify ``questions_bank`` rows into map-eligible vs not, read-only.

    The classifier never mutates input rows; it returns the bucket counts and
    the ratio used by Batch C's UI promotion gate.
    """
    counts = {"grading_key": 0, "curated_rubric": 0, "projected_or_open": 0}
    for row in rows:
        if _has_grading_key_points(row.get("grading_key")):
            counts["grading_key"] += 1
        elif _has_curated_rubric(row.get("grading_rubric")):
            counts["curated_rubric"] += 1
        else:
            counts["projected_or_open"] += 1

    total = sum(counts.values())
    map_eligible = counts["grading_key"] + counts["curated_rubric"]
    ratio = (map_eligible / total) if total else 0.0
    return {"coverage_counts": counts, "map_eligible_ratio": ratio}


def _has_grading_key_points(grading_key: Any) -> bool:
    if not isinstance(grading_key, dict):
        return False
    points = grading_key.get("scoring_points")
    return isinstance(points, list) and len(points) > 0


def _has_curated_rubric(grading_rubric: Any) -> bool:
    if not isinstance(grading_rubric, list):
        return False
    return len(grading_rubric) > 0


# ─── Phase -1.A.3: LLM grounding discipline ────────────────────────────────
#
# Curated rubric wins; LLM dissent is logged as ``grader_disagreement`` so the
# rate can be monitored and Batch A promotion gated at ≤ 5%.


def reconcile_grader_output(
    *,
    rubric_specs: list[dict[str, Any]],
    llm_output: dict[str, Any],
) -> dict[str, Any]:
    """Filter LLM-proposed scoring-point hits against the curated rubric.

    Hits whose ``point_id`` exists in ``rubric_specs`` are accepted (first
    occurrence wins; duplicates silently dropped). Hits referencing unknown
    point ids are dropped from ``accepted_hits`` and recorded in
    ``disagreement`` with ``reason='not_in_rubric'``. When ``rubric_specs``
    is empty, every LLM hit becomes disagreement — the system refuses to
    invent scoring points from thin air.
    """
    allowed_ids = {
        str(spec.get("point_id") or "").strip()
        for spec in rubric_specs
        if isinstance(spec, dict) and str(spec.get("point_id") or "").strip()
    }

    accepted: list[dict[str, Any]] = []
    disagreement: list[dict[str, Any]] = []
    seen_accepted: set[str] = set()

    raw_hits = llm_output.get("scoring_point_hits") if isinstance(llm_output, dict) else None
    if not isinstance(raw_hits, list):
        raw_hits = []

    for hit in raw_hits:
        if not isinstance(hit, dict):
            continue
        point_id = str(hit.get("point_id") or "").strip()
        if not point_id:
            continue
        if point_id not in allowed_ids:
            disagreement.append({"point_id": point_id, "reason": "not_in_rubric"})
            continue
        if point_id in seen_accepted:
            continue
        accepted.append(hit)
        seen_accepted.add(point_id)

    return {"accepted_hits": accepted, "disagreement": disagreement}
