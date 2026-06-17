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
        "summary": {
            "audit_item_count": 4,
            "suggestion_count": 4,
            "suggested_accept_count": 1,
            "suggested_reject_count": 1,
            "manual_review_count": 1,
        },
        "suggestions": [
            {
                "audit_item_id": "audit_queue:patch:ACCEPT",
                "audit_source_type": "patch_semantic_packet",
                "leaf_id": "L1",
                "artifact_id": "A1",
                "missing_lane": "textbook",
                "terminal_leaf": "建筑设计程序",
                "suggested_decision": "accept_source_ref_candidate",
                "suggestion_confidence": "medium",
                "reason_codes": ["terminal_leaf_text_present"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "audit_item_id": "audit_queue:source:REJECT",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L2",
                "artifact_id": "A2",
                "missing_lane": "standard",
                "terminal_leaf": "模板工程要求",
                "suggested_decision": "reject_wrong_leaf_source",
                "suggestion_confidence": "high",
                "reason_codes": ["source_lane_mismatch"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "audit_item_id": "audit_queue:source:EXTERNAL",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L3",
                "artifact_id": "A3",
                "missing_lane": "lecture",
                "terminal_leaf": "外部依据",
                "suggested_decision": "needs_external_source",
                "suggestion_confidence": "high",
                "reason_codes": ["missing_source_candidate"],
                "reviewer_must_confirm": True,
                "decision_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            {
                "audit_item_id": "audit_queue:source:MANUAL",
                "audit_source_type": "source_evidence_candidate",
                "leaf_id": "L4",
                "artifact_id": "A4",
                "missing_lane": "lecture",
                "terminal_leaf": "人工审核",
                "suggested_decision": "manual_review_required",
                "suggestion_confidence": "low",
                "reason_codes": ["insufficient_deterministic_signal"],
                "reviewer_must_confirm": True,
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


def test_semantic_review_decision_materializer_records_shadow_only_decisions() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_materializer import (
        materialize_semantic_review_decisions,
    )

    report = materialize_semantic_review_decisions(
        suggestions_payload=_suggestions_payload(),
        reviewer_id="codex_semantic_shadow_v1",
    )

    assert report["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert report["classification"]["semantic_shadow_review_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["classification"]["release_truth_claimed"] is False
    assert report["summary"]["suggestion_count"] == 4
    assert report["summary"]["decision_count"] == 3
    assert report["summary"]["skipped_manual_review_count"] == 1
    assert report["summary"]["blocker_count"] == 0
    first = report["decisions"][0]
    assert first["decision"] == "accept_source_ref_candidate"
    assert first["reviewer_role"] == "codex_semantic_shadow_reviewer"
    assert first["reviewer_id"] == "codex_semantic_shadow_v1"
    assert first["shadow_only"] is True
    assert first["candidate_only"] is True
    assert first["runtime_install_allowed"] is False
    assert first["release_truth_claimed"] is False
    assert {decision["decision"] for decision in report["decisions"]} == {
        "accept_source_ref_candidate",
        "reject_wrong_leaf_source",
        "needs_external_source",
    }


def test_semantic_review_decision_materializer_fails_on_suggestion_authority_drift() -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_materializer import (
        materialize_semantic_review_decisions,
    )

    suggestions = _suggestions_payload()
    suggestions["classification"]["decisions_recorded"] = True

    report = materialize_semantic_review_decisions(
        suggestions_payload=suggestions,
        reviewer_id="codex_semantic_shadow_v1",
    )

    assert report["summary"]["decision_count"] == 0
    assert report["summary"]["blocker_count"] == 1
    assert "input_suggestions_decisions_recorded" in report["blockers"]


def test_semantic_review_decision_materializer_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_review_decision_materializer import main

    suggestions = tmp_path / "semantic_review_suggestions.json"
    output = tmp_path / "semantic_review_decisions.json"
    suggestions.write_text(json.dumps(_suggestions_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--suggestions",
            str(suggestions),
            "--reviewer-id",
            "codex_semantic_shadow_v1",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["schema"] == "luban_rich_leaf_semantic_audit_decisions.v1"
    assert payload["summary"]["decision_count"] == 3
