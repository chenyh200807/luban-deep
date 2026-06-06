from __future__ import annotations

from deeptutor.services.observability.aae_composite import build_aae_composite_run


def test_build_aae_composite_run_uses_arr_and_om_inputs() -> None:
    payload = build_aae_composite_run(
        arr_payload={
            "run_id": "arr-lite-1",
            "release": {"release_id": "rel-1"},
            "summary": {"pass_rate": 0.95, "total_cases": 20},
            "suite_summaries": [
                {"suite": "context-orchestration", "pass_rate": 1.0},
                {"suite": "long-dialog-focus", "pass_rate": 0.8},
            ],
            "case_results": [
                {"status": "PASS", "failure_type": None},
            ],
        },
        om_payload={
            "run_id": "om-1",
            "metrics_snapshot": {
                "surface_events": {
                    "coverage": [
                        {"first_render_coverage_ratio": 0.98},
                    ]
                },
                "turn_runtime": {"turn_avg_latency_ms": 5200.0},
            },
            "slo_summary": {"compliance_ratio": 0.75},
        },
    )

    assert payload["source_arr_run_id"] == "arr-lite-1"
    assert payload["source_om_run_id"] == "om-1"
    assert payload["scorecard"]["correctness_score"]["value"] == 0.95
    assert payload["scorecard"]["continuity_score"]["value"] == 0.9
    assert payload["scorecard"]["surface_render_score"]["value"] == 0.98
    assert payload["scorecard"]["latency_class"]["value"] == "fast"
    assert payload["scorecard"]["om_slo_compliance_score"]["value"] == 0.75
    assert payload["composite"]["input_count"] >= 4


def test_build_aae_composite_run_uses_real_exam_spine_when_present() -> None:
    payload = build_aae_composite_run(
        arr_payload={
            "run_id": "arr-lite-1",
            "release": {"release_id": "rel-1"},
            "summary": {"pass_rate": 0.5, "total_cases": 3},
            "suite_summaries": [
                {"suite": "real_exam_quality_spine", "pass_rate": 1.0},
                {"suite": "context-orchestration", "pass_rate": 0.75},
            ],
            "case_results": [],
        },
    )

    correctness = payload["scorecard"]["correctness_score"]
    assert correctness["value"] == 1.0
    assert correctness["source"] == "arr_real_exam_quality_spine"
    assert payload["scorecard"]["continuity_score"]["value"] == 0.75
    assert "real-exam spine" in payload["review_note"]


def test_build_aae_composite_run_uses_real_feedback_for_paid_satisfaction() -> None:
    payload = build_aae_composite_run(
        arr_payload={
            "run_id": "arr-lite-1",
            "release": {"release_id": "rel-1"},
            "summary": {"pass_rate": 1.0, "total_cases": 3},
            "suite_summaries": [],
            "case_results": [],
        },
        feedback_payload={
            "window_days": 7,
            "storage_status": "ok",
            "summary": {
                "total_feedback": 4,
                "thumbs_up": 2,
                "neutral": 1,
                "thumbs_down": 1,
            },
        },
    )

    score = payload["scorecard"]["paid_student_satisfaction_score"]
    assert score["value"] == 0.625
    assert score["source"] == "supabase_ai_feedback"
    assert score["is_proxy"] is False
    assert payload["coverage_summary"]["feedback_storage_status"] == "ok"
    assert payload["coverage_summary"]["feedback_total"] == 4


def test_build_aae_composite_run_falls_back_to_proxy_when_feedback_is_empty() -> None:
    payload = build_aae_composite_run(
        arr_payload={
            "run_id": "arr-lite-1",
            "release": {"release_id": "rel-1"},
            "summary": {"pass_rate": 1.0, "total_cases": 3},
            "suite_summaries": [],
            "case_results": [],
        },
        feedback_payload={
            "window_days": 7,
            "storage_status": "ok",
            "summary": {
                "total_feedback": 0,
                "thumbs_up": 0,
                "neutral": 0,
                "thumbs_down": 0,
            },
        },
    )

    score = payload["scorecard"]["paid_student_satisfaction_score"]
    assert score["value"] == 1.0
    assert score["source"] == "proxy_composite"
    assert score["is_proxy"] is True
    assert payload["coverage_summary"]["paid_student_satisfaction_available"] is True
    assert "没有真实满意度反馈样本" in payload["review_note"]
    assert "paid_student_satisfaction_score 当前仍是 proxy。" in payload["review_note"]


def test_build_aae_composite_run_falls_back_to_proxy_when_feedback_storage_errors() -> None:
    payload = build_aae_composite_run(
        arr_payload={
            "run_id": "arr-lite-1",
            "release": {"release_id": "rel-1"},
            "summary": {"pass_rate": 0.8, "total_cases": 5},
            "suite_summaries": [],
            "case_results": [],
        },
        feedback_payload={
            "window_days": 7,
            "storage_status": "error",
            "summary": {
                "total_feedback": 0,
                "thumbs_up": 0,
                "neutral": 0,
                "thumbs_down": 0,
            },
        },
    )

    score = payload["scorecard"]["paid_student_satisfaction_score"]
    assert score["value"] == 0.9
    assert score["source"] == "proxy_composite"
    assert score["is_proxy"] is True
    assert payload["coverage_summary"]["feedback_storage_status"] == "error"
    assert "真实满意度反馈存储不可用" in payload["review_note"]
