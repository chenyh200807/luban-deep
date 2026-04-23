from __future__ import annotations

from deeptutor.services.observability.oa_runner import build_oa_run


def test_build_oa_run_emits_root_causes_and_blind_spots() -> None:
    payload = build_oa_run(
        mode="pre-release",
        om_payload={
            "run_id": "om-1",
            "release": {"release_id": "rel-1"},
            "health_summary": {"ready": False, "turn_first_render_ratio": None},
        },
        arr_payload={
            "run_id": "arr-1",
            "summary": {"pass_rate": 0.8},
            "baseline_diff": {"regressions": [{"case_key": "semantic-router::c1"}]},
            "suite_summaries": [{"suite": "long-dialog-focus", "skipped": 1}],
        },
        aae_payload={
            "run_id": "aae-1",
            "scorecard": {
                "continuity_score": {"value": 0.6},
                "paid_student_satisfaction_score": {"value": 0.7},
            }
        },
    )

    assert payload["mode"] == "pre-release"
    assert len(payload["root_causes"]) >= 2
    assert any(item["type"] == "long_dialog_skipped" for item in payload["blind_spots"])
    assert payload["repair_playbooks"]


def test_build_oa_run_flags_unified_ws_smoke_failure_as_root_cause() -> None:
    payload = build_oa_run(
        mode="pre-release",
        om_payload={
            "run_id": "om-1",
            "release": {"release_id": "rel-1"},
            "health_summary": {
                "ready": True,
                "unified_ws_smoke_ok": False,
                "unified_ws_smoke_summary": "invalid api key",
            },
            "smoke_checks": [
                {
                    "name": "unified_ws_smoke",
                    "ok": False,
                    "summary": "invalid api key",
                    "evidence": ["Incorrect API key provided"],
                }
            ],
        },
        arr_payload=None,
        aae_payload=None,
    )

    assert any("主聊天链路" in item["hypothesis"] for item in payload["root_causes"])


def test_build_oa_run_consumes_observer_snapshot_blind_spots_and_turn_failures() -> None:
    payload = build_oa_run(
        mode="daily",
        om_payload=None,
        arr_payload=None,
        aae_payload=None,
        observer_payload={
            "run_id": "observer-snapshot-1",
            "release": {"release_id": "rel-1"},
            "data_coverage": {"coverage_ratio": 0.4},
            "blind_spots": [{"type": "missing_surface_coverage", "severity": "medium"}],
            "turn_events": {
                "event_count": 10,
                "error_count": 2,
                "timeout_count": 1,
                "error_ratio": 0.2,
            },
        },
    )

    assert payload["raw_evidence_bundle"]["observer_snapshot_run_id"] == "observer-snapshot-1"
    assert any(item["type"] == "missing_surface_coverage" for item in payload["blind_spots"])
    assert any("真实 turn 失败率偏高" in item["hypothesis"] for item in payload["root_causes"])
    assert any(item["kind"] == "observer_snapshot" for item in payload["signals"])
