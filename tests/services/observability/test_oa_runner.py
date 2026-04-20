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
