from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _patch_audit_report() -> dict:
    return {
        "schema": "luban_rich_leaf_patch_evidence_audit.v1",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "audit_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "patch_audits": [
            {
                "patch_id": "patch_good",
                "artifact_id": "A1",
                "leaf_id": "L1",
                "name_path": "建筑设计程序",
                "missing_lane": "textbook",
                "source_lane": "textbook",
                "record_id": "TB1",
                "path": "教材原文/source.json",
                "audit_decision": "machine_precheck_pass",
                "review_status": "machine_precheck_only",
                "reason_codes": [],
                "matched_terms": ["建筑设计程序"],
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "candidate_only": True,
            },
            {
                "patch_id": "patch_bad",
                "artifact_id": "A2",
                "leaf_id": "L2",
                "name_path": "建筑设计程序",
                "missing_lane": "lecture",
                "source_lane": "lecture",
                "record_id": "LEC_BAD",
                "path": "讲义/地下连续墙.md",
                "audit_decision": "machine_reject",
                "review_status": "machine_precheck_only",
                "reason_codes": ["option_marker_only_match", "no_name_path_specific_term_in_span"],
                "matched_terms": ["A.", "B.", "C."],
                "apply_allowed": False,
                "runtime_install_allowed": False,
                "candidate_only": True,
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_rejected_patch_feedback_emits_review_only_work_order_for_rejected_patch() -> None:
    from scripts.run_luban_rich_leaf_rejected_patch_feedback import build_rejected_patch_feedback_report

    report = build_rejected_patch_feedback_report(patch_audit_report=_patch_audit_report())

    assert report["schema"] == "luban_rich_leaf_rejected_patch_feedback.v1"
    assert report["classification"] == {
        "review_only": True,
        "candidate_only": True,
        "work_orders_apply_allowed": False,
        "runtime_install_allowed": False,
    }
    assert report["summary"] == {
        "rejected_patch_count": 1,
        "work_order_count": 1,
        "option_marker_pollution_count": 1,
        "wrong_leaf_source_count": 1,
    }
    assert all(value in (False, 0) for value in report["safety"].values())

    order = report["rejected_patch_work_orders"][0]
    assert order["patch_id"] == "patch_bad"
    assert order["leaf_id"] == "L2"
    assert order["missing_lane"] == "lecture"
    assert order["status"] == "rejected_patch_feedback"
    assert order["source_ref_candidate_reusable"] is False
    assert order["promotion_allowed"] is False
    assert order["runtime_install_allowed"] is False
    assert order["reason_codes"] == ["option_marker_only_match", "no_name_path_specific_term_in_span"]
    assert order["feedback_codes"] == ["option_marker_pollution", "wrong_leaf_source"]
    assert order["next_action"] == "rerun_source_search_with_non_option_specific_leaf_terms"


def test_cli_writes_rejected_patch_feedback(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_rejected_patch_feedback import main

    patch_audit = tmp_path / "patch_evidence_audit.json"
    output_dir = tmp_path / "out"
    _write_json(patch_audit, _patch_audit_report())

    exit_code = main(["--patch-audit", str(patch_audit), "--output-dir", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "rejected_patch_feedback_work_orders.json").read_text("utf-8"))
    assert report["summary"]["work_order_count"] == 1
    assert report["rejected_patch_work_orders"][0]["patch_id"] == "patch_bad"
