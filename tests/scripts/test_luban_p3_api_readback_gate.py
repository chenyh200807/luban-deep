"""P3 API-surface readback gate tests for grading-to-brain convergence."""
from __future__ import annotations

import json

from scripts.run_luban_p3_api_readback_gate import build_p3_api_readback_package


def test_p3_api_readback_exposes_same_projection_hash_on_brain_and_report(tmp_path):
    package = build_p3_api_readback_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_p3_api_readback_gate.v1"
    assert package["p3_api_readback"]["verdict"] == "STRONG-GO"
    assert package["p3_api_readback"]["mode"] == "local_testclient_api_readback"
    assert package["p3_api_readback"]["api_readback_exercised"] is True
    assert package["p3_api_readback"]["required_readbacks_present"] is True
    assert package["p3_api_readback"]["projection_hash_match"] is True

    readbacks = package["api_readbacks"]
    assert readbacks["learning_brain_projection"]["status_code"] == 200
    assert readbacks["mobile_learning_report_v2"]["status_code"] == 200
    assert readbacks["learning_brain_projection"]["output_projection_hash"].startswith("sha256:")
    assert readbacks["learning_brain_projection"]["output_projection_hash"] == readbacks[
        "mobile_learning_report_v2"
    ]["output_projection_hash"]

    ids = package["p3_api_readback"]["readback_ids"]
    assert ids["learner_memory_event_id"]
    assert ids["learning_brain_projection_hash"].startswith("sha256:")
    assert ids["mobile_learning_report_hash"].startswith("sha256:")
    assert ids["api_surface_pair_id"].startswith("api_pair_")

    assert package["sources"]["api_surfaces"] == [
        "/api/v1/learning-brain/projection",
        "/api/v1/mobile/learning-report?schema_version=2",
    ]
    assert package["safety"]["canonical_truth_written"] is False
    assert package["safety"]["production_write_count"] == 0
    assert package["safety"]["remote_write_count"] == 0

    written = tmp_path / "p3_api_readback_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_p3_missing_report_readback_blocks_strong_go(tmp_path):
    package = build_p3_api_readback_package(
        output_dir=tmp_path,
        include_mobile_report_readback=False,
    )

    assert package["p3_api_readback"]["verdict"] == "NO-GO"
    assert package["p3_api_readback"]["required_readbacks_present"] is False
    assert package["p3_api_readback"]["projection_hash_match"] is False
    assert "mobile_learning_report_readback_missing" in package["p3_api_readback"]["blockers"]
