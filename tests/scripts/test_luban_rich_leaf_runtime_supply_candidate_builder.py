from __future__ import annotations

import json
from pathlib import Path


def _reviewed_candidates(candidate: dict | None = None) -> dict:
    candidates = [candidate] if candidate else []
    return {
        "schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_record_count": 1 if candidate else 0,
            "accepted_source_ref_count": len(candidates),
            "reviewed_candidate_count": len(candidates),
            "not_accepted_count": 0,
        },
        "reviewed_candidates": candidates,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _candidate() -> dict:
    return {
        "candidate_id": "RC1",
        "candidate_status": "reviewed_candidate",
        "leaf_id": "L1",
        "artifact_id": "A1",
        "missing_lane": "textbook",
        "audit_item_id": "audit_queue:patch:P1",
        "field_patch": {
            "field": "source_refs",
            "operation": "add_source_ref",
            "source_ref": {
                "source_lane": "textbook",
                "source_path": "教材原文/source.json",
                "record_id": "TB1",
                "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                "span_hash": "hash1",
                "support_candidate": True,
            },
        },
        "review_authority": {
            "review_decision_status": "recorded",
            "decision": "accept_source_ref_candidate",
            "reviewer_role": "ai_evidence_auditor",
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "official_score_allowed": False,
    }


def test_runtime_supply_candidate_builder_outputs_empty_candidate_for_no_reviewed_sources() -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_candidate_builder import build_runtime_supply_candidate

    report = build_runtime_supply_candidate(reviewed_candidates=_reviewed_candidates())

    assert report["schema"] == "luban_rich_leaf_runtime_supply_candidate_bundle.v1"
    assert report["status"] == "no_reviewed_candidates"
    assert report["summary"]["reviewed_candidate_count"] == 0
    assert report["summary"]["supply_unit_count"] == 0
    assert report["supply_units"] == []
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["production_default"] is False
    assert report["safety"]["installed_runtime_supply"] is False


def test_runtime_supply_candidate_builder_promotes_only_reviewed_source_refs_to_candidate_units() -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_candidate_builder import build_runtime_supply_candidate

    report = build_runtime_supply_candidate(reviewed_candidates=_reviewed_candidates(_candidate()))

    assert report["status"] == "candidate_ready_for_regression"
    assert report["summary"]["reviewed_candidate_count"] == 1
    assert report["summary"]["supply_unit_count"] == 1
    assert report["summary"]["rejected_candidate_count"] == 0
    assert report["manifest"]["bundle_hash"]
    unit = report["supply_units"][0]
    assert unit["leaf_id"] == "L1"
    assert unit["artifact_id"] == "A1"
    assert unit["source_ref"]["source_lane"] == "textbook"
    assert unit["source_ref"]["record_id"] == "TB1"
    assert unit["provenance"]["candidate_id"] == "RC1"
    assert unit["install_allowed"] is False
    assert unit["runtime_install_allowed"] is False


def test_runtime_supply_candidate_builder_rejects_runtime_installable_reviewed_candidate() -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_candidate_builder import build_runtime_supply_candidate

    candidate = _candidate()
    candidate["runtime_install_allowed"] = True
    report = build_runtime_supply_candidate(reviewed_candidates=_reviewed_candidates(candidate))

    assert report["status"] == "no_valid_supply_units"
    assert report["summary"]["supply_unit_count"] == 0
    assert report["summary"]["rejected_candidate_count"] == 1
    assert report["rejected_candidates"][0]["reason"] == "candidate_runtime_or_release_allowed"


def test_runtime_supply_candidate_builder_cli_writes_candidate_bundle(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_candidate_builder import main

    reviewed = tmp_path / "reviewed_rich_leaf_candidates.json"
    out_dir = tmp_path / "out"
    reviewed.write_text(json.dumps(_reviewed_candidates(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--reviewed-candidates", str(reviewed), "--output-dir", str(out_dir)])

    assert exit_code == 0
    payload = json.loads((out_dir / "rich_leaf_runtime_supply_candidate.json").read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_runtime_supply_candidate_bundle.v1"
    assert payload["summary"]["supply_unit_count"] == 0
