#!/usr/bin/env python3
"""Build task-specific CompiledContextPack smoke reports from promoted RichLeaf candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import build_compiled_context_pack


REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_context_pack_smoke_20260612/context_pack_smoke.json"
)
SCHEMA = "luban_rich_leaf_context_pack_smoke.v1"
TASKS = ("grading", "tutoring", "rag_answer", "next_action", "review")
KNOWLEDGE_TASKS = {"grading", "tutoring", "rag_answer"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    trace = pack.get("consumption_trace") if isinstance(pack.get("consumption_trace"), dict) else {}
    lanes = sorted({str(ref.get("source_lane")) for ref in pack.get("source_refs") or [] if isinstance(ref, dict)})
    return {
        "task": pack.get("task"),
        "field_count": len(pack.get("fields") or []),
        "source_ref_count": len(pack.get("source_refs") or []),
        "source_ref_lanes": lanes,
        "consumed_field_ids": trace.get("consumed_field_ids") or [],
        "review_candidate_field_ids": trace.get("review_candidate_field_ids") or [],
        "review_candidate_field_count": len(trace.get("review_candidate_field_ids") or []),
        "stripped_candidate_field_ids": trace.get("stripped_candidate_field_ids") or [],
        "rejected_field_ids": trace.get("rejected_field_ids") or [],
        "fail_closed_reasons": trace.get("fail_closed_reasons") or [],
        "pack_hash": trace.get("pack_hash"),
        "canonical_write_allowed": pack.get("canonical_write_allowed"),
        "production_write_count": pack.get("production_write_count"),
        "official_score_allowed": pack.get("official_score_allowed"),
    }


def run_context_pack_smoke(*, field_promotion_review: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"input_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"input_field_promotion_review_failed:{field_promotion_review.get('verdict')}")
    classification = field_promotion_review.get("classification") if isinstance(field_promotion_review.get("classification"), dict) else {}
    if classification.get("runtime_install_allowed") is not False or classification.get("release_truth_claimed") is not False:
        blockers.append("input_field_promotion_review_runtime_or_release_allowed")

    artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    packs: list[dict[str, Any]] = []
    manifest_hash = str((field_promotion_review.get("summary") or {}).get("promotion_decision_count") or "unknown")
    for task in TASKS:
        pack = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version="v_rich_leaf_context_pack_smoke_20260612",
            manifest_hash=manifest_hash,
        ).to_dict()
        summary = _pack_summary(pack)
        packs.append(summary)
        if pack.get("canonical_write_allowed") is not False or pack.get("official_score_allowed") is not False:
            blockers.append(f"context_pack_write_or_score_allowed:{task}")
        if pack.get("production_write_count") not in (0, False):
            blockers.append(f"context_pack_production_write_count_nonzero:{task}")
        if summary["fail_closed_reasons"]:
            blockers.append(f"context_pack_fail_closed:{task}:{'|'.join(summary['fail_closed_reasons'])}")
        if task in KNOWLEDGE_TASKS and "question" in summary["source_ref_lanes"]:
            blockers.append(f"question_lane_source_ref_in_knowledge_task:{task}")

    return {
        "schema": SCHEMA,
        "input_schema": field_promotion_review.get("schema"),
        "verdict": "FAIL" if blockers else "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "context_pack_smoke": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "input_promoted_artifact_count": len(artifacts),
            "task_pack_count": len(packs),
            "blocker_count": len(blockers),
            "knowledge_task_question_lane_source_ref_count": sum(
                1 for pack in packs if pack["task"] in KNOWLEDGE_TASKS and "question" in pack["source_ref_lanes"]
            ),
            "review_candidate_field_count": sum(pack["review_candidate_field_count"] for pack in packs),
        },
        "compiled_context_packs": packs,
        "blockers": blockers,
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
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_context_pack_smoke(field_promotion_review=_read_json(args.field_promotion_review))
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
