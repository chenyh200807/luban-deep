from __future__ import annotations

import json
from pathlib import Path

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "runtime_install_allowed": False,
    "production_default": False,
    "release_truth_claimed": False,
}
SAFETY = {
    "canonical_truth_written": False,
    "official_score_allowed": False,
    "installed_runtime_supply": False,
    "production_write_count": 0,
    "release_truth_claimed": False,
}


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "version": "v3.0_frozen_v1_full_compile",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "runtime_token_pack_units": [
            {
                "unit_id": "rtpf1_aaaa",
                "leaf_id": "L1",
                "leaf_name_path": "root > 网络计划",
                "compiled_context": {"concepts": ["与叶无关的内容。"]},
                "source_ref": {"source_path": "2026教材/a.json", "span_hash": "s1"},
            },
            {
                "unit_id": "rtpf1_bbbb",
                "leaf_id": "L2",
                "leaf_name_path": "root > 叶2",
                "compiled_context": {"concepts": ["叶2 概念。"]},
                "source_ref": {"source_path": "2026教材/a.json", "span_hash": "s2"},
            },
        ],
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def _live_ab() -> dict:
    rows = []
    for arm, answerable in (
        ("current_rag_projection_live", True),
        ("legacy_keyword_projection_live", True),
        ("rich_leaf_context_live", False),
        ("artifact_first_guard_live", False),
    ):
        rows.append(
            {
                "arm": arm,
                "case_id": "rtpf1_aaaa",
                "unit_id": "rtpf1_aaaa",
                "leaf_id": "L1",
                "status": "completed",
                "answerable": answerable,
                "expected_answerable": True,
                "matches_expected": answerable,
                "answer_text": "" if answerable else "证据未涉及该知识点",
            }
        )
    for arm in (
        "current_rag_projection_live",
        "legacy_keyword_projection_live",
        "rich_leaf_context_live",
        "artifact_first_guard_live",
    ):
        rows.append(
            {
                "arm": arm,
                "case_id": "rtpf1_bbbb",
                "unit_id": "rtpf1_bbbb",
                "leaf_id": "L2",
                "status": "completed",
                "answerable": True,
                "expected_answerable": True,
                "matches_expected": True,
            }
        )
    rows.append(
        {
            "arm": "rich_leaf_context_live",
            "case_id": "rtpf1_bbbb",
            "unit_id": "rtpf1_bbbb",
            "leaf_id": "L2",
            "status": "failed",
            "error": "timeout",
        }
    )
    return {
        "schema": "luban_rich_leaf_frozen_v1_live_ab.v1",
        "verdict": "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB",
        "summary": {"sample_count": 2},
        "rows": rows,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def test_residual_work_orders_quarantine_failed_context_leaves() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_residual_work_orders import (
        build_frozen_v1_live_residual_work_orders,
    )

    report = build_frozen_v1_live_residual_work_orders(
        live_ab=_live_ab(),
        runtime_token_pack=_runtime_token_pack(),
    )

    assert report["verdict"] == "PASS_FROZEN_V1_LIVE_RESIDUAL_WORK_ORDERS_READY"
    assert report["summary"]["work_order_count"] == 1
    assert report["summary"]["quarantine_candidate_count"] == 1
    assert report["summary"]["provider_error_row_count"] == 1

    order = report["work_orders"][0]
    assert order["work_order_type"] == "compiler_feedback_source_or_leaf_recheck"
    assert order["unit_id"] == "rtpf1_aaaa"
    assert order["candidate_only"] is True
    assert order["failed_arms"] == ["artifact_first_guard_live", "rich_leaf_context_live"]
    assert "live_provider_expected_answerable_but_context_rejected" in order["reason_codes"]
    assert "provider_reported_missing_relevant_evidence" in order["reason_codes"]
    assert "leaf_context_keyword_mismatch" in order["reason_codes"]

    pack = report["annotated_runtime_token_pack"]
    assert pack["version"] == "v3.0.1_frozen_v1_quarantine_annotated"
    assert pack["quarantine"]["quarantine_candidate_unit_ids"] == ["rtpf1_aaaa"]
    by_id = {u["unit_id"]: u for u in pack["runtime_token_pack_units"]}
    assert by_id["rtpf1_aaaa"]["quarantine_candidate"] is True
    assert by_id["rtpf1_aaaa"]["quarantine_work_order_id"] == order["work_order_id"]
    assert "quarantine_candidate" not in by_id["rtpf1_bbbb"]


def test_residual_work_orders_fail_closed_on_non_pass_live_ab() -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_residual_work_orders import (
        build_frozen_v1_live_residual_work_orders,
    )

    live_ab = _live_ab()
    live_ab["verdict"] = "BLOCKED_OR_FAILED"
    report = build_frozen_v1_live_residual_work_orders(
        live_ab=live_ab,
        runtime_token_pack=_runtime_token_pack(),
    )

    assert report["verdict"] == "FAIL"
    assert any(b.startswith("live_ab_not_pass") for b in report["blockers"])
    assert report["annotated_runtime_token_pack"] is None


def test_residual_work_orders_cli_writes_outputs(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_frozen_v1_live_residual_work_orders import main

    live_path = tmp_path / "live.json"
    pack_path = tmp_path / "pack.json"
    out = tmp_path / "orders.json"
    out_pack = tmp_path / "annotated_pack.json"
    live_path.write_text(json.dumps(_live_ab(), ensure_ascii=False), encoding="utf-8")
    pack_path.write_text(json.dumps(_runtime_token_pack(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--live-ab",
            str(live_path),
            "--runtime-token-pack",
            str(pack_path),
            "--output",
            str(out),
            "--output-pack",
            str(out_pack),
        ]
    )

    assert exit_code == 0
    orders = json.loads(out.read_text(encoding="utf-8"))
    assert orders["summary"]["work_order_count"] == 1
    assert orders["annotated_runtime_token_pack_path"] == str(out_pack)
    annotated = json.loads(out_pack.read_text(encoding="utf-8"))
    assert annotated["quarantine"]["quarantine_candidate_count"] == 1
