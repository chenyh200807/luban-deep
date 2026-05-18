"""Offline Learning Brain retrieval maintenance helpers."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": str(source.get("chunk_id") or source.get("id") or "").strip(),
        "source_type": str(source.get("source_type") or source.get("source_group") or "").strip(),
        "title": str(source.get("title") or source.get("source") or "").strip(),
    }


def _citation_gaps(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id") or case.get("case_id") or "").strip()
        evidence_bundle = _as_dict(case.get("evidence_bundle"))
        for source in _as_list(evidence_bundle.get("sources")):
            if not isinstance(source, dict):
                continue
            compact = _compact_source(source)
            missing = [
                key
                for key, value in compact.items()
                if key in {"chunk_id", "source_type"} and not value
            ]
            if missing:
                gaps.append({
                    "case_id": case_id,
                    "missing": missing,
                    "source": compact,
                })
    return gaps


def _stale_weak_points(projection: dict[str, Any]) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    for weak_point in _as_list(projection.get("weak_points")):
        if not isinstance(weak_point, dict):
            continue
        decay_state = str(weak_point.get("decay_state") or weak_point.get("status") or "").strip().lower()
        stale_flag = bool(weak_point.get("stale"))
        superseded_by = _as_list(weak_point.get("superseded_by_event_ids"))
        if decay_state not in {"", "active", "confirmed"} or stale_flag or superseded_by:
            stale.append({
                "concept_id": str(weak_point.get("concept_id") or "").strip(),
                "error_code": str(weak_point.get("error_code") or "").strip(),
                "decay_state": decay_state,
                "stale": stale_flag,
                "superseded_by_event_ids": [str(item) for item in superseded_by],
            })
    return stale


def _rubric_coverage_gaps(projection: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    graph = _as_dict(projection.get("typed_graph"))
    for gap in _as_list(graph.get("readiness_gaps")):
        if isinstance(gap, dict):
            gaps.append({
                "code": str(gap.get("code") or "readiness_gap").strip(),
                "message": str(gap.get("message") or "").strip(),
            })
        elif str(gap or "").strip():
            gaps.append({"code": "readiness_gap", "message": str(gap).strip()})

    edges = _as_list(graph.get("edges"))
    rubric_targets = {
        str(edge.get("from") or edge.get("source") or "").strip()
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("type") or edge.get("edge_type") or "").strip() in {
            "concept_to_rubric_item",
            "concept->rubric_item",
        }
    }
    for weak_point in _as_list(projection.get("weak_points")):
        if not isinstance(weak_point, dict):
            continue
        concept_id = str(weak_point.get("concept_id") or "").strip()
        if concept_id and concept_id not in rubric_targets:
            gaps.append({
                "code": "weak_point_without_rubric_edge",
                "message": f"weak point lacks concept -> rubric_item edge: {concept_id}",
            })
    return gaps


def _retrieval_misses(audit: dict[str, Any]) -> list[dict[str, Any]]:
    misses: list[dict[str, Any]] = []
    for result in _as_list(audit.get("results")):
        if not isinstance(result, dict) or result.get("ok"):
            continue
        miss_codes = {
            "missing_expected_source",
            "missing_exact_question",
            "missing_retrieval_plan",
            "missing_ranking_trace",
        }
        issues = [
            issue for issue in _as_list(result.get("issues"))
            if isinstance(issue, dict) and str(issue.get("code") or "") in miss_codes
        ]
        if issues:
            misses.append({
                "case_id": str(result.get("case_id") or "").strip(),
                "issues": issues,
            })
    return misses


def audit_learning_fact_retrieval_case(case: dict[str, Any]) -> dict[str, Any]:
    query = str(case.get("query") or "").strip()
    evidence_bundle = _as_dict(case.get("evidence_bundle"))
    retrieval_plan = _as_dict(evidence_bundle.get("retrieval_plan"))
    ranking_trace = _as_dict(evidence_bundle.get("ranking_trace"))
    exact_question = _as_dict(evidence_bundle.get("exact_question"))
    sources = _as_list(evidence_bundle.get("sources"))
    issues: list[dict[str, str]] = []

    if not query:
        issues.append({"code": "missing_query", "message": "case query is empty"})
    if not retrieval_plan:
        issues.append({"code": "missing_retrieval_plan", "message": "evidence_bundle lacks retrieval_plan"})
    if not ranking_trace:
        issues.append({"code": "missing_ranking_trace", "message": "evidence_bundle lacks ranking_trace"})
    source_types = {str(item.get("source_type") or item.get("source_group") or "") for item in sources if isinstance(item, dict)}
    expected_sources = set(case.get("expected_source_types") or [])
    missing_sources = sorted(item for item in expected_sources if item not in source_types)
    for source_type in missing_sources:
        issues.append({
            "code": "missing_expected_source",
            "message": f"expected source_type not present: {source_type}",
        })
    if case.get("expects_exact_question") and not exact_question:
        issues.append({"code": "missing_exact_question", "message": "exact question was expected but absent"})
    if exact_question and "compiled_learning_truth" in source_types:
        features = _as_list(ranking_trace.get("provenance_features"))
        compiled_before_exact = False
        first_exact_index = None
        first_compiled_index = None
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            group = str(feature.get("source_group") or feature.get("source_type") or "")
            if group in {"question_exact_text", "question_exact_vector", "exact_question"} and first_exact_index is None:
                first_exact_index = index
            if group == "compiled_learning_truth" and first_compiled_index is None:
                first_compiled_index = index
        if first_compiled_index is not None and (first_exact_index is None or first_compiled_index < first_exact_index):
            compiled_before_exact = True
        if compiled_before_exact:
            issues.append({
                "code": "compiled_truth_over_exact_question",
                "message": "compiled truth ranked ahead of exact question authority",
            })
    return {
        "case_id": str(case.get("id") or ""),
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }


def audit_learning_fact_retrieval_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [audit_learning_fact_retrieval_case(case) for case in cases]
    return {
        "ok": all(item["ok"] for item in results),
        "case_count": len(results),
        "failed_count": sum(1 for item in results if not item["ok"]),
        "results": results,
    }


def build_learning_fact_retrieval_maintenance_report(payload: dict[str, Any]) -> dict[str, Any]:
    cases = [
        case for case in _as_list(payload.get("cases") or payload.get("retrieval_cases"))
        if isinstance(case, dict)
    ]
    projection = _as_dict(
        payload.get("compiled_learning_truth")
        or payload.get("compiled_projection")
        or payload.get("projection")
    )
    audit = audit_learning_fact_retrieval_cases(cases)
    retrieval_misses = _retrieval_misses(audit)
    citation_gaps = _citation_gaps(cases)
    stale_weak_points = _stale_weak_points(projection)
    rubric_coverage_gaps = _rubric_coverage_gaps(projection)
    eval_cases = [
        {
            "case_id": str(case.get("id") or case.get("case_id") or "").strip(),
            "query": str(case.get("query") or "").strip(),
            "expected_source_types": list(case.get("expected_source_types") or []),
        }
        for case in cases
    ]
    ok = audit["ok"] and not citation_gaps and not stale_weak_points and not rubric_coverage_gaps
    return {
        "ok": ok,
        "case_count": len(cases),
        "retrieval_miss_count": len(retrieval_misses),
        "citation_gap_count": len(citation_gaps),
        "stale_weak_point_count": len(stale_weak_points),
        "rubric_coverage_gap_count": len(rubric_coverage_gaps),
        "sections": {
            "retrieval_misses": retrieval_misses,
            "citation_gaps": citation_gaps,
            "stale_weak_points": stale_weak_points,
            "rubric_coverage_gaps": rubric_coverage_gaps,
            "eval_cases": eval_cases,
        },
        "case_audit": audit,
    }
