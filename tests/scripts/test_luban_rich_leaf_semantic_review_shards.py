from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _semantic_queue(count: int = 3) -> dict:
    items = []
    for index in range(count):
        items.append(
            {
                "audit_item_id": f"audit_queue:source:A{index}:textbook:{index}",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": f"L{index}",
                "artifact_id": f"A{index}",
                "name_path": f"知识点 {index}",
                "missing_lane": "textbook",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "教材/book.json",
                    "record_id": f"TB{index}",
                    "span": f"教材原文片段 {index}",
                    "span_hash": f"hash{index}",
                    "support_candidate": True,
                    "candidate_only": True,
                    "install_allowed": False,
                    "runtime_install_allowed": False,
                },
                "question_context_candidates": [],
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "review_status": "semantic_review_pending",
                "semantic_verdict_recorded": False,
                "candidate_only": True,
                "review_only": True,
                "apply_allowed": False,
                "runtime_install_allowed": False,
            }
        )
    return {
        "schema": "luban_rich_leaf_semantic_audit_queue.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "semantic_audit_queue": items,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_semantic_review_shards_split_queue_without_recording_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_shards import build_semantic_review_shards_report

    report, shard_payloads = build_semantic_review_shards_report(semantic_queue=_semantic_queue(3), shard_size=2)

    assert report["schema"] == "luban_rich_leaf_semantic_review_shards.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "decisions_recorded": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {"audit_item_count": 3, "shard_count": 2, "shard_size": 2}
    assert all(value in (False, 0) for value in report["safety"].values())
    assert [shard["summary"]["audit_item_count"] for shard in shard_payloads] == [2, 1]

    first_shard = shard_payloads[0]
    assert first_shard["schema"] == "luban_rich_leaf_semantic_review_shard.v1"
    assert first_shard["classification"]["decisions_recorded"] is False
    assert first_shard["decision_output_schema"]["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert first_shard["decision_output_schema"]["allowed_decisions"] == [
        "accept_source_ref_candidate",
        "reject_wrong_leaf_source",
        "needs_external_source",
        "needs_leaf_split_or_retaxonomy",
    ]
    assert first_shard["audit_items"][0]["audit_item_id"] == "audit_queue:source:A0:textbook:0"
    assert first_shard["audit_items"][0]["source_candidate"]["span"] == "教材原文片段 0"
    assert "decision" not in first_shard["audit_items"][0]
    assert first_shard["audit_items"][0]["runtime_install_allowed"] is False


def test_semantic_review_shards_cli_writes_manifest_and_shard_files(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_review_shards import main

    queue_path = tmp_path / "semantic_audit_queue.json"
    output_dir = tmp_path / "out"
    _write_json(queue_path, _semantic_queue(3))

    exit_code = main(["--semantic-queue", str(queue_path), "--output-dir", str(output_dir), "--shard-size", "2"])

    assert exit_code == 0
    manifest = json.loads((output_dir / "semantic_review_shards_manifest.json").read_text("utf-8"))
    assert manifest["summary"]["shard_count"] == 2
    assert (output_dir / "semantic_review_shard_000.json").exists()
    assert (output_dir / "semantic_review_shard_001.json").exists()
