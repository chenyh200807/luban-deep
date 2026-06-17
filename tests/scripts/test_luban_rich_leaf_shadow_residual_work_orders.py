from __future__ import annotations

import json
from pathlib import Path


def _near_live_shadow_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
        "verdict": "PASS",
        "verdict_ceiling": "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY",
        "quality_claim_allowed": False,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_runtime_near_live_shadow_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "shadow_case_count": 2,
            "blocker_count": 0,
            "provider_call_count": 0,
            "local_adapter_fail_open_rate": 0.5,
            "local_adapter_question_lane_citation_rate": 0.0,
        },
        "sample_rows": [
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "near_live_shadow_0001",
                "answerable": True,
                "fail_open": False,
                "question_lane_citation_count": 1,
            }
        ],
        "local_adapter_rows": [
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": "near_live_shadow_0001",
                "task": "rag_answer",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "field_id": "F1",
                "family": "rules",
                "answerable": True,
                "fail_open": True,
                "question_lane_citation_count": 0,
            },
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": "near_live_shadow_0002",
                "task": "tutoring",
                "artifact_id": "A2",
                "leaf_id": "L2",
                "field_id": "F2",
                "family": "teaching_cards",
                "answerable": True,
                "fail_open": False,
                "question_lane_citation_count": 0,
            },
        ],
        "blockers": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _fail_open_guard_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_fail_open_guard_diagnostic.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "fail_open_guard_diagnostic": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "input_promoted_artifact_count": 2,
            "negative_evidence_candidate_count": 3,
            "review_candidate_field_count": 3,
            "top_leaf_count": 1,
            "blocker_count": 0,
        },
        "leaf_diagnostics": [
            {
                "leaf_id": "L2",
                "artifact_ids": ["A2"],
                "negative_evidence_count": 3,
                "field_ids": ["N1", "N2", "N3"],
                "source_lanes": ["textbook"],
                "record_ids": ["R1"],
                "source_ref_ids": ["S1"],
                "negative_evidence_types": ["wrong_leaf_source"],
                "guard_suggestion": "block_positive_context_until_source_ref_reviewed",
            }
        ],
        "blockers": [],
        "not_exercised": [
            "runtime_fail_open_reduction",
            "production_runtime_enforcement",
            "learner_memory_writeback",
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_shadow_residual_work_orders_join_runtime_residuals_and_guard_diagnostics() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_work_orders import run_shadow_residual_work_orders

    report = run_shadow_residual_work_orders(
        near_live_shadow_ab=_near_live_shadow_payload(),
        fail_open_guard_diagnostic=_fail_open_guard_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_shadow_residual_work_orders.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["runtime_residual_work_order_count"] == 1
    assert report["summary"]["guard_review_work_order_count"] == 1
    assert report["summary"]["non_joinable_residual_count"] == 1
    by_leaf = {order["leaf_id"]: order for order in report["compiler_work_orders"]}
    assert by_leaf["L1"]["trigger_reason"] == "local_adapter_runtime_residual"
    assert by_leaf["L1"]["residual_case_ids"] == ["near_live_shadow_0001"]
    assert by_leaf["L1"]["action"] == "review_source_refs_and_pack_guard_for_leaf"
    assert by_leaf["L2"]["trigger_reason"] == "preventive_negative_evidence_guard_review"
    assert by_leaf["L2"]["guard_evidence_count"] == 3


def test_shadow_residual_work_orders_fail_closed_on_bad_guard_input() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_work_orders import run_shadow_residual_work_orders

    guard = _fail_open_guard_payload()
    guard["classification"]["quality_claim_allowed"] = True

    report = run_shadow_residual_work_orders(
        near_live_shadow_ab=_near_live_shadow_payload(),
        fail_open_guard_diagnostic=guard,
    )

    assert report["verdict"] == "FAIL"
    assert "input_fail_open_guard_quality_claim_allowed" in report["blockers"]


def test_shadow_residual_work_orders_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_work_orders import main

    shadow = tmp_path / "near_live_shadow_ab.json"
    guard = tmp_path / "fail_open_guard_diagnostic.json"
    output = tmp_path / "shadow_residual_work_orders.json"
    shadow.write_text(json.dumps(_near_live_shadow_payload(), ensure_ascii=False), encoding="utf-8")
    guard.write_text(json.dumps(_fail_open_guard_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--near-live-shadow-ab",
            str(shadow),
            "--fail-open-guard-diagnostic",
            str(guard),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_work_orders.v1"
    assert payload["summary"]["work_order_count"] == 2
