from __future__ import annotations

import json
from pathlib import Path


def _work_orders_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_shadow_residual_work_orders.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "shadow_residual_work_orders": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "runtime_residual_case_count": 1,
            "runtime_residual_work_order_count": 1,
            "guard_review_work_order_count": 1,
            "non_joinable_residual_count": 1,
            "work_order_count": 2,
            "blocker_count": 0,
        },
        "compiler_work_orders": [
            {
                "work_order_id": "WO_RUNTIME",
                "leaf_id": "L1",
                "trigger_reason": "local_adapter_runtime_residual",
                "priority": "high",
                "action": "review_source_refs_and_pack_guard_for_leaf",
                "artifact_ids": ["A1"],
                "field_ids": ["F1"],
                "families": ["rules"],
                "tasks": ["rag_answer"],
                "residual_case_ids": ["near_live_shadow_0001"],
                "reason_codes": ["fail_open"],
                "guard_evidence_count": 0,
                "source_lanes": ["textbook"],
                "record_ids": ["R1"],
                "candidate_only": True,
                "review_only": True,
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "work_order_id": "WO_GUARD",
                "leaf_id": "L2",
                "trigger_reason": "preventive_negative_evidence_guard_review",
                "priority": "medium",
                "action": "review_source_refs_and_pack_guard_for_leaf",
                "artifact_ids": ["A2"],
                "field_ids": ["N1"],
                "families": [],
                "tasks": [],
                "residual_case_ids": [],
                "reason_codes": ["negative_evidence_guard_review"],
                "guard_evidence_count": 3,
                "source_lanes": ["standard"],
                "record_ids": ["R2"],
                "candidate_only": True,
                "review_only": True,
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
        ],
        "non_joinable_residuals": [
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "near_live_shadow_0002",
                "reason_codes": ["term_miss"],
                "join_blocker": "missing_leaf_id",
            }
        ],
        "blockers": [],
        "not_exercised": [
            "compiler_patch_generation",
            "source_ref_mutation",
            "runtime_guard_enforcement",
            "quality_claim",
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


def test_shadow_residual_review_packets_render_review_only_packets() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_packets import run_shadow_residual_review_packets

    report = run_shadow_residual_review_packets(shadow_residual_work_orders=_work_orders_payload())

    assert report["schema"] == "luban_rich_leaf_shadow_residual_review_packets.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["patch_generation_allowed"] is False
    assert report["classification"]["quality_claim_allowed"] is False
    assert report["summary"]["review_packet_count"] == 2
    assert report["summary"]["non_joinable_residual_count"] == 1
    by_id = {packet["work_order_id"]: packet for packet in report["review_packets"]}
    assert by_id["WO_RUNTIME"]["packet_id"] == "shadow_residual_review_packet:WO_RUNTIME"
    assert by_id["WO_RUNTIME"]["review_scope"] == "runtime_residual_source_ref_review"
    assert "confirm_guard_needed" in by_id["WO_RUNTIME"]["allowed_decisions"]
    assert by_id["WO_RUNTIME"]["decision_recorded"] is False
    assert by_id["WO_GUARD"]["review_scope"] == "preventive_negative_evidence_guard_review"
    assert by_id["WO_GUARD"]["work_order_trace"]["guard_evidence_count"] == 3


def test_shadow_residual_review_packets_fail_closed_on_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_packets import run_shadow_residual_review_packets

    payload = _work_orders_payload()
    payload["compiler_work_orders"][0]["apply_allowed"] = True

    report = run_shadow_residual_review_packets(shadow_residual_work_orders=payload)

    assert report["verdict"] == "FAIL"
    assert "input_work_order_apply_or_runtime_allowed:WO_RUNTIME" in report["blockers"]


def test_shadow_residual_review_packets_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_shadow_residual_review_packets import main

    work_orders = tmp_path / "shadow_residual_work_orders.json"
    output = tmp_path / "shadow_residual_review_packets.json"
    work_orders.write_text(json.dumps(_work_orders_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--shadow-residual-work-orders", str(work_orders), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_shadow_residual_review_packets.v1"
    assert payload["summary"]["review_packet_count"] == 2
