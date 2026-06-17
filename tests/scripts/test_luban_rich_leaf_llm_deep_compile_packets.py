from __future__ import annotations

import json
from pathlib import Path


def _coverage_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_source_corpus_coverage_gate.v1",
        "verdict": "GAP_WORK_ORDERS_READY",
        "quality_claim_allowed": False,
        "summary": {
            "gap_work_order_count": 3,
            "production_write_count": 0,
        },
        "gap_work_orders": [
            {
                "work_order_id": "source_corpus_gap:教材/a.md",
                "relative_path": "教材/a.md",
                "source_lane": "source_truth",
                "sha256": "a" * 64,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "work_order_id": "source_corpus_gap:讲义/b.md",
                "relative_path": "讲义/b.md",
                "source_lane": "teaching_evidence",
                "sha256": "b" * 64,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "work_order_id": "source_corpus_gap:题库/c.md",
                "relative_path": "题库/c.md",
                "source_lane": "assessment_evidence",
                "sha256": "c" * 64,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
        ],
        "classification": {
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
    }


def test_llm_deep_compile_packets_preserve_contract_and_shard_gaps() -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_packets import (
        run_llm_deep_compile_packets,
    )

    report = run_llm_deep_compile_packets(source_corpus_coverage_gate=_coverage_gate(), shard_size=2)

    assert report["schema"] == "luban_rich_leaf_llm_deep_compile_packets.v1"
    assert report["verdict"] == "READY_FOR_LLM_DEEP_COMPILE_SHADOW"
    assert report["summary"]["packet_count"] == 2
    assert report["summary"]["work_order_count"] == 3
    assert report["summary"]["production_write_count"] == 0
    assert report["packets"][0]["packet_id"] == "llm_deep_compile_shard_000"
    assert report["packets"][0]["llm_role"] == "rich_leaf_deep_compiler"
    assert len(report["packets"][0]["work_orders"]) == 2
    assert report["packets"][0]["output_contract"]["required_fields"] == [
        "concepts",
        "definitions",
        "rules",
        "procedures",
        "numeric_constraints",
        "common_mistakes",
        "exam_patterns",
        "source_refs",
        "negative_evidence",
        "teaching_cards",
        "grading_relevance",
        "learner_memory_event_templates",
    ]
    assert report["packets"][0]["forbidden_actions"] == [
        "edit_taxonomy",
        "mint_source_truth",
        "claim_release_truth",
        "write_runtime_default",
        "write_canonical_learner_truth",
        "write_production_db",
    ]
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_llm_deep_compile_packets_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_packets import main

    coverage = tmp_path / "coverage.json"
    output = tmp_path / "packets.json"
    coverage.write_text(json.dumps(_coverage_gate(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--coverage-gate", str(coverage), "--shard-size", "2", "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["packet_count"] == 2
    assert payload["summary"]["work_order_count"] == 3
