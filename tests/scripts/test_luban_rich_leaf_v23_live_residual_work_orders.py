from __future__ import annotations

import json
from pathlib import Path


def _live_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_v23_live_provider_shadow_ab.v1",
        "verdict": "PASS_V23_PROJECTED_LIVE_PROVIDER_SHADOW_AB",
        "summary": {"sample_count": 2, "provider_call_count": 8},
        "rows": [
            {
                "arm": "rich_leaf_v23_context_live",
                "case_id": "case_1",
                "unit_id": "u1",
                "leaf_id": "L1",
                "status": "completed",
                "expected_answerable": True,
                "answerable": False,
                "matches_expected": False,
                "answer_text": "上下文未涉及石材，无法回答。",
            },
            {
                "arm": "current_rag_projection_live",
                "case_id": "case_1",
                "unit_id": "u1",
                "leaf_id": "L1",
                "status": "completed",
                "expected_answerable": False,
                "answerable": False,
                "matches_expected": True,
            },
            {
                "arm": "artifact_first_guard_live",
                "case_id": "case_2",
                "unit_id": "u2",
                "leaf_id": "L2",
                "status": "completed",
                "expected_answerable": True,
                "answerable": True,
                "matches_expected": True,
            },
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
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


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "runtime_token_pack_units": [
            {
                "unit_id": "u1",
                "leaf_id": "L1",
                "leaf_name_path": "结构工程材料 > 石材的性能与应用",
                "review_source": "deterministic_dedup_margin",
                "compiled_context": {"rules": ["地基基础应满足承载力要求"]},
                "source_ref": {"source_path": "标准/a.json", "span_hash": "s1", "source_lane": "textbook"},
            },
            {
                "unit_id": "u2",
                "leaf_id": "L2",
                "leaf_name_path": "装饰装修工程施工 > 绿色施工",
                "review_source": "ai_shadow_review",
                "compiled_context": {"rules": ["绿色施工规则"]},
                "source_ref": {"source_path": "教材/b.json", "span_hash": "s2", "source_lane": "textbook"},
            },
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
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


def test_v23_live_residual_work_orders_materialize_compiler_feedback() -> None:
    from scripts.run_luban_rich_leaf_v23_live_residual_work_orders import build_v23_live_residual_work_orders

    report = build_v23_live_residual_work_orders(
        live_provider_ab=_live_ab(),
        runtime_token_pack=_runtime_token_pack(),
    )

    assert report["schema"] == "luban_rich_leaf_v23_live_residual_work_orders.v1"
    assert report["verdict"] == "PASS_LIVE_RESIDUAL_WORK_ORDERS_READY"
    assert report["summary"]["work_order_count"] == 1
    assert report["quality_claim_allowed"] is False
    order = report["work_orders"][0]
    assert order["candidate_only"] is True
    assert order["runtime_install_allowed"] is False
    assert order["leaf_id"] == "L1"
    assert order["failed_arms"] == ["rich_leaf_v23_context_live"]
    assert "provider_reported_missing_relevant_evidence" in order["reason_codes"]
    assert "deterministic_linker_false_positive_candidate" in order["reason_codes"]
    assert report["safety"]["production_write_count"] == 0


def test_v23_live_residual_work_orders_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_v23_live_residual_work_orders import main

    live = tmp_path / "live.json"
    runtime = tmp_path / "runtime.json"
    output = tmp_path / "work_orders.json"
    live.write_text(json.dumps(_live_ab(), ensure_ascii=False), encoding="utf-8")
    runtime.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--live-provider-ab", str(live), "--runtime-token-pack", str(runtime), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "luban_rich_leaf_v23_live_residual_work_orders.v1"
    assert payload["summary"]["work_order_count"] == 1
