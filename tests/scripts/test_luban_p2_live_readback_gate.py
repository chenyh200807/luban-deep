"""P2 live-readback gate tests for grading-to-brain convergence."""
from __future__ import annotations

import json

from scripts.run_luban_p2_live_readback_gate import build_p2_live_readback_package


def test_p2_local_live_readback_can_claim_convergence(tmp_path):
    package = build_p2_live_readback_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_p2_live_readback_gate.v1"
    assert package["p2_live_readback"]["verdict"] == "STRONG-GO"
    assert package["p2_live_readback"]["mode"] == "local_live_readback"
    assert package["p2_live_readback"]["convergence_claim_allowed"] is True
    assert package["p2_live_readback"]["required_readbacks_present"] is True
    assert package["p2_live_readback"]["shadow_writeback_blocked"] is True

    readback = package["p2_live_readback"]["readback_ids"]
    assert readback["learner_memory_event_id"]
    assert readback["weakness_projection_id"]
    assert readback["next_action_id"]
    assert readback["retest_condition_id"]

    chain = package["chain"]
    assert chain["artifact_version"]
    assert chain["point_matches"]
    assert chain["learning_evidence_hash"].startswith("sha256:")
    assert readback["learner_memory_event_id"] in chain["learner_memory_event_ids"]
    assert len(chain["learner_memory_event_ids"]) >= 2
    assert chain["pcp_hash"].startswith("sha256:")
    assert chain["next_action_id"] == readback["next_action_id"]

    assert package["sources"]["memory_events_source"] == "LearnerStateService.MEMORY_EVENTS"
    assert package["sources"]["learning_projection_source"] == "LearnerStateService.synthesize_learning_truth(dry_run=True)"

    for value in package["safety"].values():
        assert value in (False, 0)

    written = tmp_path / "p2_live_readback_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package


def test_p2_missing_required_readback_ids_blocks_convergence(tmp_path):
    package = build_p2_live_readback_package(
        output_dir=tmp_path,
        include_required_readbacks=False,
    )

    assert package["p2_live_readback"]["verdict"] == "NO-GO"
    assert package["p2_live_readback"]["convergence_claim_allowed"] is False
    assert package["p2_live_readback"]["required_readbacks_present"] is False
    assert "live_readback_missing_required_ids" in package["p2_live_readback"]["blockers"]
    assert package["safety"]["canonical_truth_written"] is False
