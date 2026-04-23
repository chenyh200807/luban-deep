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


def test_build_oa_run_consumes_change_impact_as_causal_evidence() -> None:
    payload = build_oa_run(
        mode="pre-release",
        om_payload=None,
        arr_payload=None,
        aae_payload=None,
        change_impact_payload={
            "run_id": "change-impact-1",
            "risk_level": "high",
            "risk_score": 0.9,
            "first_failing_signal": {
                "type": "arr_regressions",
                "summary": "1 ARR regression after turn changes",
            },
            "changed_domains": [{"domain": "turn", "risk": "high"}],
            "required_gates": [{"gate": "unified_ws_smoke"}],
            "next_commands": [
                "python3.11 scripts/run_unified_ws_smoke.py --api-base-url http://127.0.0.1:8001 --message '请只回复ok。'"
            ],
        },
    )

    assert payload["raw_evidence_bundle"]["change_impact_run_id"] == "change-impact-1"
    assert payload["change_impact"]["run_id"] == "change-impact-1"
    assert any(item["kind"] == "change_impact" for item in payload["signals"])
    assert any("变更影响风险偏高" in item["hypothesis"] for item in payload["root_causes"])


def test_build_oa_run_emits_causal_oa_v1_candidates_from_canonical_change_impact() -> None:
    payload = build_oa_run(
        mode="pre-release",
        om_payload={
            "run_id": "om-1",
            "release": {"release_id": "rel-1", "git_sha": "abc123"},
            "health_summary": {"ready": True, "unified_ws_smoke_ok": True},
        },
        arr_payload={
            "run_id": "arr-1",
            "summary": {"pass_rate": 0.8},
            "baseline_diff": {"regressions": [{"case_key": "long-dialog::ld-001"}]},
        },
        aae_payload={
            "run_id": "aae-1",
            "scorecard": {"continuity_score": {"value": 0.72}},
        },
        observer_payload={
            "run_id": "observer-1",
            "release": {"release_id": "rel-1", "git_sha": "abc123"},
            "turn_events": {"event_count": 10, "error_count": 1, "error_ratio": 0.1},
            "data_sources": {
                "turn_event_log": {"freshness": "fresh", "event_count": 10},
                "surface_event_store": {"freshness": "empty", "event_count": 0},
            },
        },
        change_impact_payload={
            "run_id": "change-impact-1",
            "release": {"release_id": "rel-1", "git_sha": "abc123"},
            "risk_level": "high",
            "risk_score": 0.92,
            "first_failing_signal": {
                "type": "arr_regressions",
                "summary": "1 ARR regression after turn changes",
            },
            "changed_domains": [
                {"domain": "turn", "risk": "high"},
                {"domain": "observability", "risk": "medium"},
            ],
            "required_gates": [{"gate": "arr_full"}],
            "next_commands": ["python3.11 scripts/run_arr_lite.py --mode full"],
        },
    )

    candidates = payload["causal_candidates"]
    assert candidates
    top = candidates[0]
    assert top["schema_version"] == "causal_oa_v1"
    assert top["verdict"] == "regression"
    assert top["confidence_tier"] == "confirmed"
    assert top["changed_domains"] == ["turn", "observability"]
    assert top["first_failing_signal"]["type"] == "arr_regressions"
    assert top["evidence_chain"]["source_run_ids"] == {
        "observer_snapshot": "observer-1",
        "change_impact": "change-impact-1",
        "om": "om-1",
        "arr": "arr-1",
        "aae": "aae-1",
    }
    assert top["repair_playbook"]["validation_cmds"] == [
        "python3.11 scripts/run_arr_lite.py --mode full"
    ]
    assert any(item["kind"] == "causal_oa_v1" for item in payload["signals"])
