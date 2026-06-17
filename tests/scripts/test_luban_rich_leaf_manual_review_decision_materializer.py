from __future__ import annotations

import json
from pathlib import Path


def _manual_packets_payload() -> dict:
    return {
        "schema": "luban_rich_leaf_manual_review_packets.v1",
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "manual_review_packets": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {"manual_review_packet_count": 3},
        "manual_review_packets": [
            {
                "manual_review_packet_id": "packet:needs_external",
                "audit_item_id": "audit:needs_external",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "textbook",
                "terminal_leaf": "高处作业安全",
                "reason_codes": ["insufficient_deterministic_signal"],
                "source_candidate": {
                    "source_lane": "textbook",
                    "source_path": "教材.md",
                    "record_id": "r1",
                    "span": "高处作业应采取安全防护措施。",
                    "span_hash": "h1",
                    "matched_terms": ["安全防护"],
                },
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "manual_review_packet_id": "packet:lane_mismatch",
                "audit_item_id": "audit:lane_mismatch",
                "leaf_id": "L2",
                "artifact_id": "A2",
                "missing_lane": "standard",
                "terminal_leaf": "模板拆除强度",
                "reason_codes": ["insufficient_deterministic_signal"],
                "source_candidate": {
                    "source_lane": "question",
                    "source_path": "题库.md",
                    "record_id": "q1",
                    "span": "某题解析提到模板拆除。",
                    "span_hash": "h2",
                    "matched_terms": ["模板拆除"],
                },
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "manual_review_packet_id": "packet:no_span",
                "audit_item_id": "audit:no_span",
                "leaf_id": "L3",
                "artifact_id": "A3",
                "missing_lane": "lecture",
                "terminal_leaf": "施工顺序",
                "reason_codes": ["missing_source_candidate"],
                "source_candidate": {
                    "source_lane": None,
                    "source_path": None,
                    "record_id": None,
                    "span": None,
                    "span_hash": None,
                    "matched_terms": [],
                },
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
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


def test_manual_review_decision_materializer_closes_packets_fail_closed() -> None:
    from scripts.run_luban_rich_leaf_manual_review_decision_materializer import (
        materialize_manual_review_shadow_decisions,
    )

    report = materialize_manual_review_shadow_decisions(
        manual_review_packets=_manual_packets_payload(),
        reviewer_id="codex_manual_shadow_v1",
    )

    assert report["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert report["classification"]["manual_shadow_review_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["summary"]["manual_review_packet_count"] == 3
    assert report["summary"]["decision_count"] == 3
    assert report["summary"]["accepted_source_ref_count"] == 0
    assert report["summary"]["blocker_count"] == 0
    decisions = {decision["audit_item_id"]: decision for decision in report["decisions"]}
    assert decisions["audit:needs_external"]["decision"] == "needs_external_source"
    assert decisions["audit:lane_mismatch"]["decision"] == "reject_wrong_leaf_source"
    assert decisions["audit:no_span"]["decision"] == "needs_external_source"
    assert all(decision["shadow_only"] is True for decision in decisions.values())
    assert all(decision["runtime_install_allowed"] is False for decision in decisions.values())
    assert all(decision["release_truth_claimed"] is False for decision in decisions.values())


def test_manual_review_decision_materializer_rejects_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_manual_review_decision_materializer import (
        materialize_manual_review_shadow_decisions,
    )

    payload = _manual_packets_payload()
    payload["classification"]["release_truth_claimed"] = True

    report = materialize_manual_review_shadow_decisions(
        manual_review_packets=payload,
        reviewer_id="codex_manual_shadow_v1",
    )

    assert report["summary"]["decision_count"] == 0
    assert report["summary"]["blocker_count"] == 1
    assert "manual_packets_authority_allowed:release_truth_claimed" in report["blockers"]


def test_manual_review_decision_materializer_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_manual_review_decision_materializer import main

    manual_packets = tmp_path / "manual_review_packets.json"
    output = tmp_path / "manual_shadow_decisions.json"
    manual_packets.write_text(json.dumps(_manual_packets_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--manual-review-packets",
            str(manual_packets),
            "--reviewer-id",
            "codex_manual_shadow_v1",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["decision_count"] == 3
    assert payload["safety"]["production_write_count"] == 0
