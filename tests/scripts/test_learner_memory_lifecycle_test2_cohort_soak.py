from __future__ import annotations

import json
from pathlib import Path

import scripts.run_learner_memory_lifecycle_test2_cohort_soak as soak


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_local_core_store_soak_writes_repeatable_artifact_contract(tmp_path: Path) -> None:
    out = tmp_path / "learner_memory_lifecycle_test"

    result = soak.run_soak(out_dir=out)

    assert result["go_no_go"]["status"] == "LOCAL_ARTIFACT_GO"
    assert result["manifest"]["evidence_scope"] == "local_core_store_artifact_contract"
    assert result["manifest"]["remote_write_performed"] is False
    for name in (
        "manifest.json",
        "events.jsonl",
        "projection.json",
        "canonical_readback.json",
        "personalization_context_pack.json",
        "next_best_action.json",
        "learning_brain_readback.json",
        "go_no_go.json",
    ):
        assert (out / name).exists(), name

    manifest = _json(out / "manifest.json")
    go = _json(out / "go_no_go.json")
    events = _jsonl(out / "events.jsonl")
    readback = _json(out / "canonical_readback.json")
    brain = _json(out / "learning_brain_readback.json")

    assert manifest["remote_write_performed"] is False
    assert manifest["remote_write_root_if_authorized"] == "/root/deeptutor"
    assert manifest["cohort_user_id"].startswith("qa_")
    assert manifest["blocked_user_id"].startswith("real_student_")
    assert "local_canonical_readback" in manifest["stage_chain"]
    assert len(events) == 2
    assert {row["memory_lifecycle_stage"] for row in events} == {"stable_learner_claim"}
    assert {row["evidence_level"] for row in events} == {"L2_confirmed"}
    assert all(row["trusted_adjudication"]["source"] == "certified_grading_policy" for row in events)

    assert go["same_projection_hash"] is True
    assert go["canonical_truth_promotion"]["reason"] == "production_cohort_authorized"
    assert go["blocked_non_cohort_decision"]["reason"] == "production_cohort_required"
    assert go["trusted_source"] == "certified_grading_policy"
    assert go["pcp_source"] == "PersonalizationContextPack"
    assert go["next_best_action_id"]
    assert readback["synthesis_run"]["output_projection_hash"] == go["output_projection_hash"]
    assert brain["synthesis_run"]["output_projection_hash"] == go["output_projection_hash"]
