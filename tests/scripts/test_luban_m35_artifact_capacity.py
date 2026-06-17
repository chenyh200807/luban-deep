from scripts.estimate_luban_m35_artifact_capacity import (
    estimate_m35_capacity,
    estimate_m35_capacity_scenarios,
)


def test_50k_capacity_identifies_attempt_events_not_artifacts_as_growth_driver():
    estimate = estimate_m35_capacity(
        member_count=50_000,
        active_rate=0.20,
        attempts_per_active_member_per_month=10,
        avg_points_per_attempt=8,
        evidence_bytes_per_point=360,
        prompt_trace_bytes_per_attempt=12_000,
        global_artifact_count=500,
        avg_artifact_bytes=14_000,
    )

    assert estimate["monthly_attempts"] == 100_000
    assert estimate["global_artifact_storage_mb"] < 10
    assert estimate["primary_growth_driver"] == "attempt_evidence_and_trace_not_global_artifacts"
    assert estimate["per_user_artifact_copy_allowed"] is False
    assert estimate["requires_partitioning"] is True
    assert estimate["trace_retention_policy"] == "ttl_or_cold_storage"


def test_50k_capacity_matrix_covers_100k_1m_and_3m_attempts():
    report = estimate_m35_capacity_scenarios()

    assert set(report["scenario_results"]) == {"standard_100k", "heavy_1m", "peak_3m"}
    assert report["scenario_results"]["standard_100k"]["monthly_attempts"] == 100_000
    assert report["scenario_results"]["heavy_1m"]["monthly_attempts"] == 1_000_000
    assert report["scenario_results"]["peak_3m"]["monthly_attempts"] == 3_000_000
    assert report["max_monthly_attempts"] == 3_000_000
    assert report["per_user_artifact_copy_allowed"] is False
    assert report["readiness_claim"] == "estimate_only_not_load_test"
    assert report["next_required_gate"] == "load_test_hot_read_models_and_storage"
