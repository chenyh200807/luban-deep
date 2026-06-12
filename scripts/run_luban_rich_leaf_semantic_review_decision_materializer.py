#!/usr/bin/env python3
"""Materialize shadow-only semantic review decisions from RichLeaf suggestions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SUGGESTIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_suggestions_20260612/semantic_review_suggestions.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decisions_20260612/codex_semantic_review_decisions.json"
)
SCHEMA = "luban_rich_leaf_semantic_audit_decisions.v1"
SUGGESTIONS_SCHEMA = "luban_rich_leaf_semantic_review_suggestions.v1"
MATERIALIZABLE_DECISIONS = {
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_confidence(value: Any) -> str:
    return str(value) if value in {"low", "medium", "high"} else "medium"


def _decision_from_suggestion(suggestion: dict[str, Any], reviewer_id: str) -> dict[str, Any] | None:
    suggested_decision = str(suggestion.get("suggested_decision") or "")
    if suggested_decision not in MATERIALIZABLE_DECISIONS:
        return None
    reason_codes = suggestion.get("reason_codes") if isinstance(suggestion.get("reason_codes"), list) else []
    reason_text = ",".join(str(code) for code in reason_codes) or "not_recorded"
    rationale = (
        "Codex semantic shadow reviewer materialized a review-only suggestion; "
        f"audit_source_type={suggestion.get('audit_source_type')}; "
        f"terminal_leaf={suggestion.get('terminal_leaf')}; "
        f"reason_codes={reason_text}."
    )
    return {
        "audit_item_id": suggestion.get("audit_item_id"),
        "decision": suggested_decision,
        "reviewer_role": "codex_semantic_shadow_reviewer",
        "reviewer_id": reviewer_id,
        "rationale": rationale,
        "confidence": _valid_confidence(suggestion.get("suggestion_confidence")),
        "decision_recorded": True,
        "shadow_only": True,
        "candidate_only": True,
        "leaf_id": suggestion.get("leaf_id"),
        "artifact_id": suggestion.get("artifact_id"),
        "missing_lane": suggestion.get("missing_lane"),
        "source_suggestion": {
            "suggestion_confidence": suggestion.get("suggestion_confidence"),
            "reason_codes": list(reason_codes),
        },
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def materialize_semantic_review_decisions(*, suggestions_payload: dict[str, Any], reviewer_id: str) -> dict[str, Any]:
    blockers: list[str] = []
    if not reviewer_id:
        blockers.append("reviewer_id_missing")
    if suggestions_payload.get("schema") != SUGGESTIONS_SCHEMA:
        blockers.append(f"input_suggestions_schema_mismatch:{suggestions_payload.get('schema')}")
    classification = suggestions_payload.get("classification") if isinstance(suggestions_payload.get("classification"), dict) else {}
    if classification.get("suggestion_only") is not True:
        blockers.append("input_suggestions_not_suggestion_only")
    if classification.get("decisions_recorded") is not False:
        blockers.append("input_suggestions_decisions_recorded")
    for key in ("runtime_install_allowed", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"input_suggestions_authority_allowed:{key}")

    decisions: list[dict[str, Any]] = []
    skipped_manual_review_count = 0
    skipped_unmaterializable_count = 0
    if not blockers:
        for suggestion in suggestions_payload.get("suggestions") or []:
            if not isinstance(suggestion, dict):
                blockers.append("suggestion_entry_not_object")
                continue
            if suggestion.get("reviewer_must_confirm") is not True or suggestion.get("decision_recorded") is not False:
                blockers.append(f"suggestion_confirmation_or_record_flag_invalid:{suggestion.get('audit_item_id')}")
                continue
            if suggestion.get("runtime_install_allowed") is True or suggestion.get("release_truth_claimed") is True:
                blockers.append(f"suggestion_authority_allowed:{suggestion.get('audit_item_id')}")
                continue
            if suggestion.get("suggested_decision") == "manual_review_required":
                skipped_manual_review_count += 1
                continue
            decision = _decision_from_suggestion(suggestion, reviewer_id)
            if decision is None:
                skipped_unmaterializable_count += 1
                continue
            decisions.append(decision)

    return {
        "schema": SCHEMA,
        "input_schema": suggestions_payload.get("schema"),
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "semantic_shadow_review_only": True,
            "decisions_recorded": bool(decisions),
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "suggestion_count": len(suggestions_payload.get("suggestions") or []),
            "decision_count": len(decisions),
            "skipped_manual_review_count": skipped_manual_review_count,
            "skipped_unmaterializable_count": skipped_unmaterializable_count,
            "blocker_count": len(blockers),
        },
        "decisions": decisions,
        "blockers": blockers,
        "not_exercised": [
            "human_reviewer_signoff",
            "governance_signoff",
            "runtime_supply_install",
            "production_default",
            "canonical_truth_write",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suggestions", type=Path, default=DEFAULT_SUGGESTIONS)
    parser.add_argument("--reviewer-id", default="codex_semantic_shadow_v1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = materialize_semantic_review_decisions(
        suggestions_payload=_read_json(args.suggestions),
        reviewer_id=args.reviewer_id,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["blocker_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
