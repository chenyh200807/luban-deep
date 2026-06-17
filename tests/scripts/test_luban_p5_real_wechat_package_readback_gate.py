"""P5 real WeChat package readback gate tests."""
from __future__ import annotations

import json

from scripts.run_luban_p5_real_wechat_package_readback_gate import (
    build_p5_real_wechat_package_readback_package,
)


def _p4_package() -> dict:
    return {
        "p4_ws_readback": {
            "verdict": "STRONG-GO",
            "readback_ids": {
                "turn_id": "turn_p4",
                "learner_memory_event_id": "evt_p4",
                "ws_api_surface_pair_id": "ws_api_pair_p4",
            },
        },
        "api_readbacks": {
            "learning_brain_projection": {
                "output_projection_hash": "sha256:p4-projection",
            },
            "mobile_learning_report_v2": {
                "output_projection_hash": "sha256:p4-projection",
            },
        },
    }


def _wechat_pass_payload() -> dict:
    return {
        "ok": True,
        "entry_surface": "real_wechat_package",
        "trace_source": "devtools_cli_auto_page",
        "devtools_project_root": "yousenwebview",
        "target_subpackage": "packageDeeptutor",
        "target_page": "/packageDeeptutor/pages/report/report",
        "entry_flow": "direct_subpackage_page",
        "scenario_evidence_status": "passed",
        "readiness_status": "PASS",
        "readiness_blockers": [],
        "page_automation": {
            "ok": True,
            "current_page": "/packageDeeptutor/pages/report/report",
            "auth_state": "qa_token",
            "auth_mode": "manual_token",
            "grading_to_brain_probe": {
                "has_grading_to_brain_loop": True,
                "status": "active",
                "next_required_action": "practice",
                "evidence_ref_count": 1,
                "stage_count": 3,
                "current_action_title": "练 1 道同类题",
                "latest_outcome_status": "graded",
            },
        },
    }


def test_p5_real_wechat_page_readback_can_close_entry_gap(tmp_path):
    package = build_p5_real_wechat_package_readback_package(
        output_dir=tmp_path,
        p4_package=_p4_package(),
        wechat_smoke_payload=_wechat_pass_payload(),
    )

    assert package["schema_version"] == "luban_p5_real_wechat_package_readback_gate.v1"
    assert package["p5_real_wechat_package_readback"]["verdict"] == "STRONG-GO"
    assert package["p5_real_wechat_package_readback"]["mode"] == "devtools_real_package_page_readback"
    assert package["p5_real_wechat_package_readback"]["real_wechat_package_readback_exercised"] is True
    assert package["p5_real_wechat_package_readback"]["page_grading_to_brain_loop_present"] is True
    assert package["p5_real_wechat_package_readback"]["p4_chain_linked"] is True
    assert package["real_wechat_package"]["devtools_project_root"] == "yousenwebview"
    assert package["real_wechat_package"]["target_subpackage"] == "packageDeeptutor"
    assert package["real_wechat_package"]["target_page"] == "/packageDeeptutor/pages/report/report"
    assert package["real_wechat_package"]["auth_state"] == "qa_token"
    assert package["readback_ids"]["p4"]["ws_api_surface_pair_id"] == "ws_api_pair_p4"
    assert package["safety"]["production_write_count"] == 0
    assert package["safety"]["canonical_truth_written"] is False
    assert package["safety"]["remote_write_count"] == 0

    written = tmp_path / "p5_real_wechat_package_readback_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_p5_project_open_without_page_scenario_stays_no_go(tmp_path):
    payload = _wechat_pass_payload()
    payload["scenario_evidence_status"] = "pending"
    payload["readiness_status"] = "WARN"
    payload["page_automation"] = None

    package = build_p5_real_wechat_package_readback_package(
        output_dir=tmp_path,
        p4_package=_p4_package(),
        wechat_smoke_payload=payload,
    )

    assert package["p5_real_wechat_package_readback"]["verdict"] == "NO-GO"
    assert "devtools_page_scenario_not_passed" in package["p5_real_wechat_package_readback"]["blockers"]
    assert "grading_to_brain_loop_not_visible_in_real_package" in package[
        "p5_real_wechat_package_readback"
    ]["blockers"]
