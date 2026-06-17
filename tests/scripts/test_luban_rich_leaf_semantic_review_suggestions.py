from __future__ import annotations

import json
from pathlib import Path


def _shard() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_shard.v1",
        "shard_id": "semantic_review_shard_000",
        "audit_items": [
            {
                "audit_item_id": "audit_queue:patch:P_ACCEPT",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "textbook",
                "name_path": "建筑工程技术 > 建筑设计程序",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "canonical_unified_knowledge:nodes.L1.sources.textbook[0]",
                    "record_id": "TB1",
                    "span": "建筑设计程序一般可分为方案设计、初步设计、施工图设计等阶段。",
                    "span_hash": "hash1",
                    "matched_terms": ["建筑设计程序"],
                    "support_candidate": True,
                },
            },
            {
                "audit_item_id": "audit_queue:patch:P_PARENT",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L2",
                "artifact_id": "A2",
                "missing_lane": "textbook",
                "name_path": "建筑功能材料 > 建筑防水材料的特性与应用 > 高分子防水卷材",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "canonical_unified_knowledge:nodes.L_PARENT.sources.textbook[1]",
                    "record_id": "TB2",
                    "span": "SBS 卷材和 APP 卷材适用于工业与民用建筑的屋面及地下防水工程。",
                    "span_hash": "hash2",
                    "matched_terms": ["建筑功能材料", "建筑防水材料的特性与应用"],
                    "support_candidate": True,
                },
            },
            {
                "audit_item_id": "audit_queue:source:POLLUTED",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L3",
                "artifact_id": "A3",
                "missing_lane": "textbook",
                "name_path": "工程造价 > 工程预付款与起扣点",
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "docs/2026/题库/index_dump.json",
                    "record_id": "IDX1",
                    "span": "unresolved in_corpus 工程预付款与起扣点",
                    "span_hash": "hash3",
                    "matched_terms": ["工程预付款与起扣点"],
                    "support_candidate": True,
                },
            },
        ],
    }


def test_review_suggestions_classify_obvious_accept_reject_and_pollution_without_recording_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_suggestions import build_review_suggestions

    payload = build_review_suggestions(shard_payloads=[_shard()])

    assert payload["schema"] == "luban_rich_leaf_semantic_review_suggestions.v1"
    assert payload["classification"] == {
        "review_only": True,
        "suggestion_only": True,
        "decisions_recorded": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }
    assert payload["summary"] == {
        "audit_item_count": 3,
        "suggestion_count": 3,
        "suggested_accept_count": 1,
        "suggested_reject_count": 2,
        "manual_review_count": 0,
    }
    suggestions = {item["audit_item_id"]: item for item in payload["suggestions"]}
    assert suggestions["audit_queue:patch:P_ACCEPT"]["suggested_decision"] == "accept_source_ref_candidate"
    assert suggestions["audit_queue:patch:P_PARENT"]["suggested_decision"] == "reject_wrong_leaf_source"
    assert suggestions["audit_queue:source:POLLUTED"]["suggested_decision"] == "reject_wrong_leaf_source"
    assert all(item["decision_recorded"] is False for item in payload["suggestions"])
    assert all(item["runtime_install_allowed"] is False for item in payload["suggestions"])


def test_review_suggestions_cli_writes_suggestion_file(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_review_suggestions import main

    shards_dir = tmp_path / "shards"
    output_dir = tmp_path / "out"
    shards_dir.mkdir()
    (shards_dir / "semantic_review_shards_manifest.json").write_text(
        json.dumps(
            {
                "schema": "luban_rich_leaf_semantic_review_shards.v1",
                "shards": [
                    {
                        "shard_id": "semantic_review_shard_000",
                        "path": "semantic_review_shard_000.json",
                        "audit_item_count": 3,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (shards_dir / "semantic_review_shard_000.json").write_text(json.dumps(_shard(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--review-shards-dir", str(shards_dir), "--output-dir", str(output_dir)])

    assert exit_code == 0
    payload = json.loads((output_dir / "semantic_review_suggestions.json").read_text("utf-8"))
    assert payload["summary"]["suggestion_count"] == 3
