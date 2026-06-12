from __future__ import annotations

import json
from pathlib import Path


def _suggestions_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_review_suggestions.v1",
        "classification": {
            "review_only": True,
            "suggestion_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {"suggestion_count": 2, "manual_review_count": 1},
        "suggestions": [
            {
                "audit_item_id": "audit_queue:patch:MANUAL",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "standard",
                "terminal_leaf": "施工缝",
                "suggested_decision": "manual_review_required",
                "suggestion_confidence": "low",
                "reason_codes": ["insufficient_deterministic_signal"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "audit_item_id": "audit_queue:patch:ACCEPT",
                "suggested_decision": "accept_source_ref_candidate",
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


def _semantic_queue_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_audit_queue.v1",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {"audit_item_count": 1},
        "audit_items": [
            {
                "audit_item_id": "audit_queue:patch:MANUAL",
                "leaf_id": "L1",
                "name_path": "root>施工缝",
                "missing_lane": "standard",
                "source_candidate": {
                    "source_lane": "standard",
                    "source_path": "docs/2026/std.md",
                    "record_id": "std-1",
                    "span": "施工缝的位置应符合设计和施工方案要求。",
                    "span_hash": "abc123",
                    "matched_terms": ["施工缝"],
                },
            }
        ],
    }


def test_manual_review_packets_extract_only_manual_items() -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import build_manual_review_packets

    report = build_manual_review_packets(
        suggestions=_suggestions_payload(),
        semantic_queue=_semantic_queue_payload(),
    )

    assert report["schema"] == "luban_rich_leaf_manual_review_packets.v1"
    assert report["verdict"] == "PASS"
    assert report["summary"]["manual_review_packet_count"] == 1
    assert report["summary"]["decision_count"] == 0
    packet = report["manual_review_packets"][0]
    assert packet["audit_item_id"] == "audit_queue:patch:MANUAL"
    assert packet["source_candidate"]["span_hash"] == "abc123"
    assert packet["allowed_decisions"] == [
        "accept_source_ref_candidate",
        "reject_wrong_leaf_source",
        "needs_external_source",
        "needs_leaf_split_or_retaxonomy",
    ]
    assert packet["decision_recorded"] is False
    assert packet["runtime_install_allowed"] is False
    assert packet["release_truth_claimed"] is False


def test_manual_review_packets_fail_on_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import build_manual_review_packets

    suggestions = _suggestions_payload()
    suggestions["classification"]["decisions_recorded"] = True

    report = build_manual_review_packets(
        suggestions=suggestions,
        semantic_queue=_semantic_queue_payload(),
    )

    assert report["verdict"] == "FAIL"
    assert "suggestions_decisions_already_recorded" in report["blockers"]


def test_manual_review_packets_accepts_queue_release_flag_from_safety() -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import build_manual_review_packets

    queue = _semantic_queue_payload()
    del queue["classification"]["release_truth_claimed"]
    queue["safety"] = {"release_truth_claimed": False}

    report = build_manual_review_packets(
        suggestions=_suggestions_payload(),
        semantic_queue=queue,
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["manual_review_packet_count"] == 1


def test_manual_review_packets_reads_current_semantic_audit_queue_field() -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import build_manual_review_packets

    queue = _semantic_queue_payload()
    queue["semantic_audit_queue"] = queue.pop("audit_items")

    report = build_manual_review_packets(
        suggestions=_suggestions_payload(),
        semantic_queue=queue,
    )

    packet = report["manual_review_packets"][0]
    assert report["verdict"] == "PASS"
    assert packet["source_candidate"]["record_id"] == "std-1"
    assert packet["source_candidate"]["span_hash"] == "abc123"


def test_manual_review_packets_fail_on_missing_queue_release_flag() -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import build_manual_review_packets

    queue = _semantic_queue_payload()
    del queue["classification"]["release_truth_claimed"]

    report = build_manual_review_packets(
        suggestions=_suggestions_payload(),
        semantic_queue=queue,
    )

    assert report["verdict"] == "FAIL"
    assert "semantic_queue_release_truth_claimed_not_false" in report["blockers"]


def test_manual_review_packets_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_manual_review_packets import main

    suggestions = tmp_path / "suggestions.json"
    queue = tmp_path / "queue.json"
    output = tmp_path / "manual_review_packets.json"
    suggestions.write_text(json.dumps(_suggestions_payload(), ensure_ascii=False), encoding="utf-8")
    queue.write_text(json.dumps(_semantic_queue_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--suggestions", str(suggestions), "--semantic-queue", str(queue), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["manual_review_packet_count"] == 1
