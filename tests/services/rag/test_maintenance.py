from __future__ import annotations

from deeptutor.services.rag.maintenance import (
    audit_learning_fact_retrieval_case,
    build_learning_brain_dream_cycle_maintenance_report,
    build_learning_fact_retrieval_maintenance_report,
)


def test_audit_learning_fact_retrieval_case_requires_plan_and_trace() -> None:
    result = audit_learning_fact_retrieval_case({"id": "case-1", "query": "我老是漏采分点"})

    assert result["ok"] is False
    assert {item["code"] for item in result["issues"]} == {
        "missing_retrieval_plan",
        "missing_ranking_trace",
    }


def test_audit_learning_fact_retrieval_case_detects_compiled_over_exact() -> None:
    result = audit_learning_fact_retrieval_case(
        {
            "id": "case-2",
            "query": "单选题：屋面防水等级",
            "expected_source_types": ["compiled_learning_truth"],
            "expects_exact_question": True,
            "evidence_bundle": {
                "retrieval_plan": {"plan_id": "p1"},
                "ranking_trace": {
                    "provenance_features": [
                        {"source_group": "compiled_learning_truth"},
                        {"source_group": "question_exact_text"},
                    ]
                },
                "exact_question": {"id": "q1"},
                "sources": [{"source_type": "compiled_learning_truth"}],
            },
        }
    )

    assert result["ok"] is False
    assert any(item["code"] == "compiled_truth_over_exact_question" for item in result["issues"])


def test_build_learning_fact_retrieval_maintenance_report_sections() -> None:
    report = build_learning_fact_retrieval_maintenance_report(
        {
            "cases": [
                {
                    "id": "case-3",
                    "query": "我老是案例题丢分怎么办",
                    "expected_source_types": ["compiled_learning_truth"],
                    "evidence_bundle": {
                        "retrieval_plan": {"plan_id": "p1"},
                        "ranking_trace": {"provenance_features": []},
                        "sources": [{"source_type": "compiled_learning_truth"}],
                    },
                }
            ],
            "compiled_learning_truth": {
                "weak_points": [
                    {
                        "concept_id": "waterproof",
                        "error_code": "missing_rubric",
                        "decay_state": "superseded",
                    }
                ],
                "typed_graph": {"edges": [], "readiness_gaps": ["missing next question"]},
            },
        }
    )

    assert report["ok"] is False
    assert report["citation_gap_count"] == 1
    assert report["stale_weak_point_count"] == 1
    assert report["rubric_coverage_gap_count"] == 2
    assert report["sections"]["eval_cases"][0]["case_id"] == "case-3"


def test_build_learning_brain_dream_cycle_maintenance_report_wraps_lint() -> None:
    report = build_learning_brain_dream_cycle_maintenance_report(
        user_id="student_demo",
        dry_run=True,
        projection={
            "weak_points": [
                {
                    "concept_id": "1A432000",
                    "claim": "掌握不稳",
                    "claim_status": "confirmed",
                    "evidence_refs": [],
                }
            ]
        },
    )

    assert report["status"] == "dry_run_ok"
    assert report["maintenance_authority"] == "deeptutor.services.rag.maintenance"
    assert report["issues"][0]["code"] == "unsupported_claim"
