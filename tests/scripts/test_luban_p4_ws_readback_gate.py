"""P4 real /api/v1/ws readback gate tests for grading-to-brain convergence."""
from __future__ import annotations

import importlib
import json

from scripts.run_luban_p4_ws_readback_gate import build_p4_ws_readback_package


def test_p4_real_ws_turn_writes_local_memory_and_reads_back_api_surfaces(tmp_path):
    package = build_p4_ws_readback_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_p4_ws_readback_gate.v1"
    assert package["p4_ws_readback"]["verdict"] == "STRONG-GO"
    assert package["p4_ws_readback"]["mode"] == "local_testclient_ws_readback"
    assert package["p4_ws_readback"]["ws_turn_exercised"] is True
    assert package["p4_ws_readback"]["required_readbacks_present"] is True
    assert package["p4_ws_readback"]["projection_hash_match"] is True
    assert package["p4_ws_readback"]["blockers"] == []

    ws = package["ws_turn"]
    assert ws["path"] == "/api/v1/ws"
    assert ws["result_event_seen"] is True
    assert ws["construction_grading_result_present"] is True
    assert ws["learner_memory_event_ids"]

    ids = package["p4_ws_readback"]["readback_ids"]
    assert ids["turn_id"]
    assert ids["learner_memory_event_id"] in ws["learner_memory_event_ids"]
    assert ids["learning_brain_projection_hash"].startswith("sha256:")
    assert ids["mobile_learning_report_hash"].startswith("sha256:")
    assert ids["ws_api_surface_pair_id"].startswith("ws_api_pair_")

    api = package["api_readbacks"]
    assert api["learning_brain_projection"]["status_code"] == 200
    assert api["mobile_learning_report_v2"]["status_code"] == 200
    assert api["learning_brain_projection"]["output_projection_hash"] == api[
        "mobile_learning_report_v2"
    ]["output_projection_hash"]

    assert package["safety"]["canonical_truth_written"] is False
    assert package["safety"]["production_write_count"] == 0
    assert package["safety"]["remote_write_count"] == 0

    written = tmp_path / "p4_ws_readback_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package

    llm_config_module = importlib.import_module("deeptutor.services.llm.config")
    assert hasattr(llm_config_module, "LLMConfig")
    grader_module = importlib.import_module("deeptutor.agents.question.agents.submission_grader_agent")
    assert hasattr(grader_module, "SubmissionGraderAgent")


def test_p4_missing_learner_memory_writeback_blocks_strong_go(tmp_path):
    package = build_p4_ws_readback_package(
        output_dir=tmp_path,
        enable_ws_learner_state_writeback=False,
    )

    assert package["p4_ws_readback"]["verdict"] == "NO-GO"
    assert package["p4_ws_readback"]["required_readbacks_present"] is False
    assert "learner_memory_event_writeback_missing" in package["p4_ws_readback"]["blockers"]
