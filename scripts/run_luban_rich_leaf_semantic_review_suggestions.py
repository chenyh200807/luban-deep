#!/usr/bin/env python3
"""Build non-binding RichLeaf semantic review suggestions for shard reviewers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_SHARDS_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612"
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_suggestions_20260612"
SCHEMA = "luban_rich_leaf_semantic_review_suggestions.v1"
POLLUTION_MARKERS = (
    "题库",
    "真题",
    "答案解析",
    "学生答卷",
    "unresolved in_corpus",
    "index_dump",
    "practice",
    "mcq",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _shard_payloads_from_dir(review_shards_dir: Path) -> list[dict[str, Any]]:
    manifest = _read_json(review_shards_dir / "semantic_review_shards_manifest.json")
    payloads: list[dict[str, Any]] = []
    for shard in manifest.get("shards") or []:
        if isinstance(shard, dict) and shard.get("path"):
            payloads.append(_read_json(review_shards_dir / str(shard["path"])))
    return payloads


def _norm(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _terminal_leaf(name_path: Any) -> str:
    return str(name_path or "").split(">")[-1].strip()


def _polluted(item: dict[str, Any], source_candidate: dict[str, Any]) -> bool:
    blob = json.dumps(
        {
            "source_path": source_candidate.get("source_path"),
            "record_id": source_candidate.get("record_id"),
            "span": source_candidate.get("span"),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).lower()
    return any(marker.lower() in blob for marker in POLLUTION_MARKERS) and item.get("missing_lane") != "question"


def _suggestion_for(item: dict[str, Any]) -> dict[str, Any]:
    source_candidate = item.get("source_candidate") if isinstance(item.get("source_candidate"), dict) else {}
    terminal = _terminal_leaf(item.get("name_path"))
    span = str(source_candidate.get("span") or "")
    matched_terms = [str(term) for term in source_candidate.get("matched_terms") or []]
    source_lane = source_candidate.get("source_lane")
    missing_lane = item.get("missing_lane")
    reasons: list[str] = []

    if not source_candidate:
        suggested = "needs_external_source"
        confidence = "high"
        reasons.append("missing_source_candidate")
    elif _polluted(item, source_candidate):
        suggested = "reject_wrong_leaf_source"
        confidence = "high"
        reasons.append("polluted_or_question_like_support_lane")
    elif source_lane != missing_lane:
        suggested = "reject_wrong_leaf_source"
        confidence = "high"
        reasons.append("source_lane_mismatch")
    elif terminal and (_norm(terminal) in _norm(span) or _norm(terminal) in _norm(" ".join(matched_terms))):
        suggested = "accept_source_ref_candidate"
        confidence = "medium"
        reasons.append("terminal_leaf_text_present")
    elif matched_terms and terminal and all(_norm(term) not in _norm(terminal) for term in matched_terms):
        suggested = "reject_wrong_leaf_source"
        confidence = "low"
        reasons.append("matched_terms_do_not_cover_terminal_leaf")
    else:
        suggested = "manual_review_required"
        confidence = "low"
        reasons.append("insufficient_deterministic_signal")

    return {
        "audit_item_id": item.get("audit_item_id"),
        "audit_source_type": item.get("audit_source_type"),
        "leaf_id": item.get("leaf_id"),
        "artifact_id": item.get("artifact_id"),
        "missing_lane": missing_lane,
        "terminal_leaf": terminal,
        "suggested_decision": suggested,
        "suggestion_confidence": confidence,
        "reason_codes": reasons,
        "reviewer_must_confirm": True,
        "decision_recorded": False,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
    }


def build_review_suggestions(*, shard_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    audit_items = [
        item
        for shard in shard_payloads
        for item in (shard.get("audit_items") or [])
        if isinstance(item, dict)
    ]
    suggestions = [_suggestion_for(item) for item in audit_items]
    suggested_accept_count = sum(1 for item in suggestions if item["suggested_decision"] == "accept_source_ref_candidate")
    suggested_reject_count = sum(1 for item in suggestions if item["suggested_decision"] == "reject_wrong_leaf_source")
    manual_review_count = sum(1 for item in suggestions if item["suggested_decision"] == "manual_review_required")
    return {
        "schema": SCHEMA,
        "classification": {
            "review_only": True,
            "suggestion_only": True,
            "decisions_recorded": False,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "audit_item_count": len(audit_items),
            "suggestion_count": len(suggestions),
            "suggested_accept_count": suggested_accept_count,
            "suggested_reject_count": suggested_reject_count,
            "manual_review_count": manual_review_count,
        },
        "suggestions": suggestions,
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
    parser.add_argument("--review-shards-dir", type=Path, default=DEFAULT_REVIEW_SHARDS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = build_review_suggestions(shard_payloads=_shard_payloads_from_dir(args.review_shards_dir))
    output = args.output_dir / "semantic_review_suggestions.json"
    _write_json(output, report)
    print(json.dumps({"out": str(output), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
