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
