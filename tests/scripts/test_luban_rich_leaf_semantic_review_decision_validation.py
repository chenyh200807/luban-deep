from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _manifest() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_shards.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
        },
        "summary": {"audit_item_count": 2, "shard_count": 1, "shard_size": 25},
        "shards": [{"shard_id": "semantic_review_shard_000", "path": "semantic_review_shard_000.json", "audit_item_count": 2}],
        "decision_output_schema": {
            "schema": "luban_rich_leaf_semantic_audit_decisions.v1",
            "allowed_decisions": [
                "accept_source_ref_candidate",
                "reject_wrong_leaf_source",
                "needs_external_source",
                "needs_leaf_split_or_retaxonomy",
            ],
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _shard() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_shard.v1",
        "shard_id": "semantic_review_shard_000",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
        },
        "decision_output_schema": _manifest()["decision_output_schema"],
        "summary": {"audit_item_count": 2},
        "audit_items": [
            {"audit_item_id": "audit_queue:patch:P1", "leaf_id": "L1", "missing_lane": "textbook"},
            {"audit_item_id": "audit_queue:source:A2:textbook:0", "leaf_id": "L2", "missing_lane": "textbook"},
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _decision_file() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_audit_decisions.v1",
        "decisions": [
            {
                "audit_item_id": "audit_queue:patch:P1",
                "decision": "accept_source_ref_candidate",
                "reviewer_role": "evidence_auditor",
                "reviewer_id": "ai_shadow_reviewer",
                "rationale": "The span directly supports the leaf.",
                "confidence": "medium",
            }
        ],
    }


def test_decision_validation_reports_missing_items_when_no_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_validation import validate_semantic_review_decisions

    report, merged = validate_semantic_review_decisions(manifest=_manifest(), shard_payloads=[_shard()], decision_payloads=[])

    assert report["schema"] == "luban_rich_leaf_semantic_review_decision_validation.v1"
    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"] == {
        "audit_item_count": 2,
        "decision_count": 0,
        "missing_decision_count": 2,
        "invalid_decision_count": 0,
        "duplicate_decision_count": 0,
        "orphan_decision_count": 0,
        "stale_decision_count": 0,
    }
    assert merged["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert merged["decisions"] == []
    assert report["classification"]["runtime_install_allowed"] is False


def test_decision_validation_merges_valid_decisions_and_keeps_missing_count() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_validation import validate_semantic_review_decisions

    report, merged = validate_semantic_review_decisions(
        manifest=_manifest(),
        shard_payloads=[_shard()],
        decision_payloads=[_decision_file()],
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"]["decision_count"] == 1
    assert report["summary"]["missing_decision_count"] == 1
    assert report["summary"]["invalid_decision_count"] == 0
    assert merged["decisions"][0]["audit_item_id"] == "audit_queue:patch:P1"
    assert merged["classification"] == {
        "review_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def test_decision_validation_ignores_stale_orphan_decisions_without_merging() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_validation import validate_semantic_review_decisions

    stale = _decision_file()
    stale["decisions"].append(
        {
            "audit_item_id": "audit_queue:old-source:stale",
            "decision": "accept_source_ref_candidate",
            "reviewer_role": "evidence_auditor",
            "reviewer_id": "ai_shadow_reviewer",
            "rationale": "This belonged to a previous audit queue build.",
            "confidence": "medium",
        }
    )

    report, merged = validate_semantic_review_decisions(
        manifest=_manifest(),
        shard_payloads=[_shard()],
        decision_payloads=[stale],
    )

    assert report["verdict"] == "INCOMPLETE"
    assert report["summary"]["decision_count"] == 1
    assert report["summary"]["missing_decision_count"] == 1
    assert report["summary"]["orphan_decision_count"] == 0
    assert report["summary"]["stale_decision_count"] == 1
    assert report["stale_decisions_ignored"][0]["audit_item_id"] == "audit_queue:old-source:stale"
    assert [decision["audit_item_id"] for decision in merged["decisions"]] == ["audit_queue:patch:P1"]


def test_decision_validation_rejects_orphan_and_invalid_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_validation import validate_semantic_review_decisions

    invalid = _decision_file()
    invalid["decisions"].append(
        {
            "audit_item_id": "missing_item",
            "decision": "accept_source_ref_candidate",
            "reviewer_role": "evidence_auditor",
            "reviewer_id": "ai_shadow_reviewer",
            "rationale": "No matching audit item.",
            "confidence": "medium",
        }
    )
    invalid["decisions"].append(
        {
            "audit_item_id": "audit_queue:source:A2:textbook:0",
            "decision": "not_allowed",
            "reviewer_role": "evidence_auditor",
            "reviewer_id": "ai_shadow_reviewer",
            "rationale": "Bad decision.",
            "confidence": "medium",
        }
    )

    report, merged = validate_semantic_review_decisions(
        manifest=_manifest(),
        shard_payloads=[_shard()],
        decision_payloads=[invalid],
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["orphan_decision_count"] == 0
    assert report["summary"]["stale_decision_count"] == 1
    assert report["summary"]["invalid_decision_count"] == 1
    assert len(merged["decisions"]) == 1


def test_decision_validation_cli_writes_report_and_merged_decisions(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_validation import main

    shard_dir = tmp_path / "shards"
    decisions_dir = tmp_path / "decisions"
    output_dir = tmp_path / "out"
    _write_json(shard_dir / "semantic_review_shards_manifest.json", _manifest())
    _write_json(shard_dir / "semantic_review_shard_000.json", _shard())
    _write_json(decisions_dir / "decisions_000.json", _decision_file())

    exit_code = main(
        [
            "--review-shards-dir",
            str(shard_dir),
            "--decisions-dir",
            str(decisions_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "semantic_review_decision_validation.json").read_text("utf-8"))
    merged = json.loads((output_dir / "merged_semantic_audit_decisions.json").read_text("utf-8"))
    assert report["summary"]["decision_count"] == 1
    assert merged["decisions"][0]["decision"] == "accept_source_ref_candidate"
