from __future__ import annotations

import json
from pathlib import Path


def _shard() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_shard.v1",
        "shard_id": "semantic_review_shard_000",
        "audit_items": [
            {
                "audit_item_id": "audit_queue:unresolved:A1:standard",
                "audit_source_type": "source_evidence_unresolved",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "standard",
                "source_candidate": None,
                "runtime_install_allowed": False,
            },
            {
                "audit_item_id": "audit_queue:source:A2:textbook:0",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L2",
                "artifact_id": "A2",
                "missing_lane": "textbook",
                "source_candidate": {
                    "source_lane": "textbook",
                    "record_id": "TB1",
                    "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    "span_hash": "hash1",
                },
                "runtime_install_allowed": False,
            },
            {
                "audit_item_id": "audit_queue:source:A3:textbook:0",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L3",
                "artifact_id": "A3",
                "missing_lane": "textbook",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "docs/2026/题库/index_dump.json",
                    "record_id": "IDX1",
                    "span": "unresolved in_corpus 工程预付款与起扣点",
                    "span_hash": "hash3",
                    "support_candidate": True,
                },
                "runtime_install_allowed": False,
            },
        ],
    }


def test_decision_seed_marks_unresolved_items_as_external_source_required() -> None:
    from scripts.run_luban_rich_leaf_semantic_decision_seed import build_decision_seed

    payload = build_decision_seed(shard_payloads=[_shard()], reviewer_id="seed_bot")

    assert payload["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert payload["classification"] == {
        "review_only": True,
        "seed_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }
    assert payload["summary"] == {
        "audit_item_count": 3,
        "seed_decision_count": 2,
        "unseeded_item_count": 1,
    }
    assert len(payload["decisions"]) == 2
    decision = next(item for item in payload["decisions"] if item["audit_item_id"] == "audit_queue:unresolved:A1:standard")
    assert decision["audit_item_id"] == "audit_queue:unresolved:A1:standard"
    assert decision["decision"] == "needs_external_source"
    assert decision["confidence"] == "high"
    assert decision["runtime_install_allowed"] is False
    assert decision["release_truth_claimed"] is False


def test_decision_seed_rejects_polluted_support_lane_candidates() -> None:
    from scripts.run_luban_rich_leaf_semantic_decision_seed import build_decision_seed

    payload = build_decision_seed(shard_payloads=[_shard()], reviewer_id="seed_bot")

    decision = next(item for item in payload["decisions"] if item["audit_item_id"] == "audit_queue:source:A3:textbook:0")
    assert decision["decision"] == "reject_wrong_leaf_source"
    assert decision["confidence"] == "high"
    assert "polluted" in decision["rationale"]


def test_decision_seed_does_not_decide_normal_candidate_source_items() -> None:
    from scripts.run_luban_rich_leaf_semantic_decision_seed import build_decision_seed

    shard = _shard()
    shard["audit_items"] = [shard["audit_items"][1]]

    payload = build_decision_seed(shard_payloads=[shard], reviewer_id="seed_bot")

    assert payload["decisions"] == []
    assert payload["summary"]["seed_decision_count"] == 0
    assert payload["summary"]["unseeded_item_count"] == 1


def test_decision_seed_cli_writes_decision_file(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_decision_seed import main

    shards_dir = tmp_path / "shards"
    output_dir = tmp_path / "decisions"
    shards_dir.mkdir()
    (shards_dir / "semantic_review_shards_manifest.json").write_text(
        json.dumps(
            {
                "schema": "luban_rich_leaf_semantic_review_shards.v1",
                "shards": [
                    {
                        "shard_id": "semantic_review_shard_000",
                        "path": "semantic_review_shard_000.json",
                        "audit_item_count": 2,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (shards_dir / "semantic_review_shard_000.json").write_text(json.dumps(_shard(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--review-shards-dir", str(shards_dir), "--output-dir", str(output_dir), "--reviewer-id", "seed_bot"])

    assert exit_code == 0
    payload = json.loads((output_dir / "semantic_decision_seed_unresolved.json").read_text("utf-8"))
    assert payload["summary"]["seed_decision_count"] == 2
