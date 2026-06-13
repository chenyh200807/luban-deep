"""Nexus-like compilation decision package aggregation tests."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_nexus_compilation_decision_package import build_decision_package


def test_decision_package_preserves_shadow_authority_and_release_no_go(tmp_path):
    package = build_decision_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_nexus_compilation_decision.v1"
    assert package["overall"]["phase1_nexus_like_scoring"] == "STRONG-GO"
    assert package["overall"]["phase1_scope"] == "governed_subset"
    assert package["overall"]["phase1_full_set_verdict"] == "WEAK-GO"
    assert package["overall"]["phase2_grading_to_brain_loop"] == "STRONG-GO"
    assert package["overall"]["phase2_scope"] == "local_live_readback"
    assert package["overall"]["phase3_api_readback"] == "STRONG-GO"
    assert package["overall"]["phase3_scope"] == "local_testclient_api_readback"
    assert package["overall"]["phase4_ws_readback"] == "STRONG-GO"
    assert package["overall"]["phase4_scope"] == "local_testclient_ws_readback"
    assert package["overall"]["release_verdict"] == "NO-GO"
    assert package["overall"]["quality_claim_allowed"] is False

    m35 = package["tracks"]["m35_case_scoring"]
    assert m35["status"] == "phase1_shadow_effectiveness_passed"
    assert m35["verdict_ceiling"] == "DIRECTIONAL_SHADOW"
    assert m35["sample_count"] == 162
    assert m35["provider"]["provider_call_count"] > 0
    assert m35["artifact_first_llm_judge"]["score_mae"] < m35["legacy"]["score_mae"]
    assert m35["artifact_first_llm_judge"]["fail_open_rate"] < m35["legacy"]["fail_open_rate"]
    assert m35["not_release_reasons"]

    p1 = package["tracks"]["p1_strong_go"]
    assert p1["verdict"] == "STRONG-GO"
    assert p1["sample_count"] >= 100
    assert p1["quality_claim_allowed"] is True

    m34 = package["tracks"]["m34_general_knowledge"]
    assert m34["system_wide_default"] == "NO-GO"
    assert "online_shadow_or_compiler_repair_pending" in m34["blockers"]

    loop = package["tracks"]["grading_to_brain"]
    assert loop["status"] == "local_live_readback_passed"
    assert loop["phase2_loop_verdict"] == "STRONG-GO"
    assert loop["live_readback_exercised"] is True
    assert loop["required_readbacks_present"] is True
    assert loop["readback_ids"]["learner_memory_event_id"]
    assert loop["release_truth_written"] is False
    assert "production_write_not_authorized" in loop["not_release_reasons"]

    p2 = package["tracks"]["p2_live_readback"]
    assert p2["verdict"] == "STRONG-GO"
    assert p2["mode"] == "local_live_readback"
    assert p2["convergence_claim_allowed"] is True
    assert p2["artifact_path"]

    p3 = package["tracks"]["p3_api_readback"]
    assert p3["verdict"] == "STRONG-GO"
    assert p3["mode"] == "local_testclient_api_readback"
    assert p3["projection_hash_match"] is True
    assert p3["readback_ids"]["api_surface_pair_id"].startswith("api_pair_")
    assert p3["artifact_path"]

    p4 = package["tracks"]["p4_ws_readback"]
    assert p4["verdict"] == "STRONG-GO"
    assert p4["mode"] == "local_testclient_ws_readback"
    assert p4["ws_turn_exercised"] is True
    assert p4["projection_hash_match"] is True
    assert p4["readback_ids"]["ws_api_surface_pair_id"].startswith("ws_api_pair_")
    assert p4["artifact_path"]

    flywheel = package["tracks"]["compiler_feedback_flywheel"]
    assert flywheel["status"] == "partial"
    assert flywheel["open_work_orders"]

    for value in package["safety"].values():
        assert value in (False, 0)

    written = tmp_path / "decision_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_decision_package_can_absorb_p5_real_wechat_readback(tmp_path):
    p5_path = tmp_path / "p5.json"
    p5_payload = {
        "p5_real_wechat_package_readback": {
            "verdict": "STRONG-GO",
            "mode": "devtools_real_package_page_readback",
            "real_wechat_package_readback_exercised": True,
            "page_grading_to_brain_loop_present": True,
            "p4_chain_linked": True,
            "blockers": [],
        },
        "real_wechat_package": {
            "devtools_project_root": "yousenwebview",
            "target_subpackage": "packageDeeptutor",
            "target_page": "/packageDeeptutor/pages/report/report",
            "auth_state": "qa_token",
            "auth_mode": "manual_token",
        },
        "readback_ids": {
            "p4": {
                "turn_id": "turn_p4",
                "learner_memory_event_id": "evt_p4",
                "ws_api_surface_pair_id": "ws_api_pair_p4",
            }
        },
    }
    p5_path.write_text(json.dumps(p5_payload), encoding="utf-8")

    package = build_decision_package(
        output_dir=tmp_path / "decision",
        p5_package_path=p5_path,
    )

    assert package["overall"]["phase5_real_wechat_package_readback"] == "STRONG-GO"
    assert package["overall"]["phase5_scope"] == "devtools_real_package_page_readback"
    assert package["overall"]["release_verdict"] == "NO-GO"
    assert "real_wechat_package_readback" not in package["not_exercised"]
    p5 = package["tracks"]["p5_real_wechat_package_readback"]
    assert p5["verdict"] == "STRONG-GO"
    assert p5["real_wechat_package"]["devtools_project_root"] == "yousenwebview"
