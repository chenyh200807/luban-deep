from __future__ import annotations

import json
from pathlib import Path


def _manual_review_packets() -> dict:
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
        "summary": {"manual_review_packet_count": 1, "decision_count": 0},
        "manual_review_packets": [
            {
                "manual_review_packet_id": "rich_leaf_manual_review_packet:audit_queue:patch:MANUAL",
                "audit_item_id": "audit_queue:patch:MANUAL",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "standard",
                "terminal_leaf": "施工缝",
                "source_candidate": {
                    "source_lane": "standard",
                    "source_path": "docs/2026/std.md",
                    "record_id": "std-1",
                    "span": "施工缝的位置应符合设计和施工方案要求。",
                    "span_hash": "abc123",
                    "matched_terms": ["施工缝"],
                },
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "decision_recorded": False,
                "candidate_only": True,
                "review_only": True,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            }
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_ai_council_manual_review_packets_build_shadow_envelopes() -> None:
    from scripts.run_luban_rich_leaf_ai_council_manual_review_packets import build_ai_council_manual_review_packets

    report = build_ai_council_manual_review_packets(manual_review_packets=_manual_review_packets())

    assert report["schema"] == "luban_rich_leaf_ai_council_manual_review_packets.v1"
    assert report["verdict"] == "READY_FOR_AI_COUNCIL_SHADOW_REVIEW"
    assert report["classification"]["ai_council_shadow_only"] is True
    assert report["classification"]["source_ref_mutation_allowed"] is False
    assert report["summary"]["council_review_packet_count"] == 1
    packet = report["council_review_packets"][0]
    assert packet["manual_review_packet_id"] == "rich_leaf_manual_review_packet:audit_queue:patch:MANUAL"
    assert packet["review_scope"] == "semantic_manual_review_shadow"
    assert packet["input_payload_hash"]
    assert packet["source_payload_hash"]
    assert packet["quorum_policy"]["required_member_count"] == 3
    assert packet["planned_council_members"]
    assert packet["evidence_check_schema"]["required_checks"] == [
        "supports_exact_leaf",
        "source_lane_matches_missing_lane",
        "span_support_level",
        "wrong_path_risk",
        "question_pollution_risk",
    ]
    assert packet["allowed_decisions"] == _manual_review_packets()["manual_review_packets"][0]["allowed_decisions"]


def test_ai_council_manual_review_packets_fail_without_source_candidate() -> None:
    from scripts.run_luban_rich_leaf_ai_council_manual_review_packets import build_ai_council_manual_review_packets

    payload = _manual_review_packets()
    payload["manual_review_packets"][0]["source_candidate"]["span_hash"] = None

    report = build_ai_council_manual_review_packets(manual_review_packets=payload)

    assert report["verdict"] == "FAIL"
    assert "manual_packet_missing_source_candidate:audit_queue:patch:MANUAL" in report["blockers"]


def test_ai_council_manual_review_packets_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_ai_council_manual_review_packets import main

    manual = tmp_path / "manual_review_packets.json"
    output = tmp_path / "ai_council_packets.json"
    manual.write_text(json.dumps(_manual_review_packets(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--manual-review-packets", str(manual), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["summary"]["council_review_packet_count"] == 1
