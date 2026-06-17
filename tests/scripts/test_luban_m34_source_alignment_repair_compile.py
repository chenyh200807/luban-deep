from __future__ import annotations

import json


def test_build_source_alignment_repairs_merges_only_strong_source_conflicts() -> None:
    from scripts.run_luban_m34_source_alignment_repair_compile import (
        build_source_alignment_repairs,
    )

    bundle = {
        "manifest": {"content_hash": "bundle-hash-1"},
        "nodes": {"1A000002-01": {}, "1A000002-01-a": {}},
    }
    existing = {
        "manifest": {
            "schema": "luban_canonical_unified_knowledge_source_alignment_repairs.v1",
            "namespace": "canonical_unified_knowledge.source_alignment_repairs",
            "status": "release_candidate",
            "tier": "teaching_context_not_answer_key",
            "official_score_allowed": False,
            "llm_may_decide_correctness": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "source_bundle_namespace": "canonical_unified_knowledge",
            "source_bundle_content_hash": "bundle-hash-1",
            "repair_count": 1,
            "generated_from": "previous-shadow",
        },
        "repairs": [
            {
                "node_code": "1A000001-01",
                "name_path": "既有 > 节点",
                "action": "detach_node_from_general_compiled_context",
                "reason": "existing repair",
                "evidence_queries": ["既有问题？"],
                "reanchor_to_node_code": None,
                "runtime_action": "fail_open_to_existing_tutorbot_rag",
            }
        ],
    }
    work_orders = [
        {
            "work_order_type": "source_path_conflict",
            "candidate_node_code": "1A000001-01",
            "candidate_leaf_name_path": "既有 > 节点",
            "question": "新增问题？",
            "negative_evidence": ["primary_path_mismatch", "source_path_conflict"],
            "canonical_truth_written": False,
            "production_write_count": 0,
        },
        {
            "work_order_type": "source_path_conflict",
            "candidate_node_code": "1A000002-01",
            "candidate_leaf_name_path": "父级 > 节点",
            "question": "父级问题？",
            "negative_evidence": ["primary_path_mismatch", "source_path_conflict"],
            "canonical_truth_written": False,
            "production_write_count": 0,
        },
        {
            "work_order_type": "source_path_conflict",
            "candidate_node_code": "1A000004-01",
            "candidate_leaf_name_path": "弱证据 > 节点",
            "question": "弱证据问题？",
            "negative_evidence": ["primary_path_mismatch"],
            "canonical_truth_written": False,
            "production_write_count": 0,
        },
    ]

    overlay, report = build_source_alignment_repairs(
        work_orders,
        bundle=bundle,
        existing_overlay=existing,
        generated_from="unit-test",
        protected_hit_questions={"新增问题？"},
    )

    manifest = overlay["manifest"]
    assert manifest["official_score_allowed"] is False
    assert manifest["llm_may_decide_correctness"] is False
    assert manifest["canonical_truth_written"] is False
    assert manifest["production_write_count"] == 0
    assert manifest["source_bundle_content_hash"] == "bundle-hash-1"
    assert manifest["repair_count"] == 1

    assert len(overlay["repairs"]) == 1
    merged = overlay["repairs"][0]
    assert merged["node_code"] == "1A000001-01"
    assert merged["evidence_queries"] == ["既有问题？"]
    assert merged["runtime_action"] == "fail_open_to_existing_tutorbot_rag"

    assert report["input_work_order_count"] == 3
    assert report["strong_source_conflict_work_order_count"] == 0
    assert report["deferred_review_count"] == 3
    assert report["deferred_broad_parent_count"] == 1
    assert report["deferred_protected_hit_count"] == 1
    assert report["existing_repair_count"] == 1
    assert report["merged_repair_count"] == 1


def test_cli_writes_candidate_overlay_and_report(tmp_path) -> None:
    from scripts.run_luban_m34_source_alignment_repair_compile import main

    bundle_path = tmp_path / "canonical_unified_knowledge.json"
    bundle_path.write_text(
        json.dumps({"manifest": {"content_hash": "bundle-hash-2"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    work_orders_path = tmp_path / "work_orders.jsonl"
    work_orders_path.write_text(
        json.dumps(
            {
                "work_order_type": "source_path_conflict",
                "candidate_node_code": "1A000003-01",
                "candidate_leaf_name_path": "新 > 节点",
                "question": "源路径冲突？",
                "negative_evidence": ["primary_path_mismatch", "source_path_conflict"],
                "canonical_truth_written": False,
                "production_write_count": 0,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--work-orders",
            str(work_orders_path),
            "--bundle",
            str(bundle_path),
            "--output-dir",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    overlay = json.loads((out_dir / "source_alignment_repairs_candidate.json").read_text("utf-8"))
    report = json.loads((out_dir / "compile_report.json").read_text("utf-8"))
    assert overlay["manifest"]["source_bundle_content_hash"] == "bundle-hash-2"
    assert overlay["repairs"][0]["node_code"] == "1A000003-01"
    assert report["safety"]["installed_runtime_supply"] is False


def test_calibration_gate_blocks_case_level_regression_even_when_rates_match() -> None:
    from scripts.run_luban_m34_source_alignment_repair_compile import (
        _calibration_is_non_regressing,
    )

    baseline = {
        "status": "evaluated",
        "teaching_context_hit_rate": 0.875,
        "calibration_pass_rate": 0.9,
        "hit_rate_threshold": 0.8,
        "failed_cases": [{"question": "baseline existing miss", "expected": "hit"}],
    }
    candidate = {
        "status": "evaluated",
        "teaching_context_hit_rate": 0.875,
        "calibration_pass_rate": 0.9,
        "hit_rate_threshold": 0.8,
        "failed_cases": [{"question": "newly regressed case", "expected": "hit"}],
    }

    assert _calibration_is_non_regressing(candidate, baseline) is False


def test_normalize_existing_overlay_drops_invalid_repairs() -> None:
    from scripts.run_luban_m34_source_alignment_repair_compile import (
        normalize_existing_overlay,
    )

    invalid = {
        "manifest": {
            "schema": "luban_canonical_unified_knowledge_source_alignment_repairs.v1",
            "namespace": "canonical_unified_knowledge.source_alignment_repairs",
            "tier": "teaching_context_not_answer_key",
            "official_score_allowed": True,
            "llm_may_decide_correctness": False,
            "canonical_truth_written": False,
            "production_write_count": 0,
            "source_bundle_namespace": "canonical_unified_knowledge",
            "source_bundle_content_hash": "bundle-hash",
        },
        "repairs": [{"node_code": "bad", "action": "detach_node_from_general_compiled_context"}],
    }

    normalized = normalize_existing_overlay(invalid, "bundle-hash")

    assert normalized["repairs"] == []
