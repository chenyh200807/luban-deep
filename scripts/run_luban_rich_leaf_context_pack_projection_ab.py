#!/usr/bin/env python3
"""Run review-only A/B over candidate-only vs promoted RichLeaf context packs.

This is a projection/protocol A/B, not a semantic runtime A/B. It answers:
after field promotion, do task-specific CompiledContextPacks carry more usable
typed context while preserving question-lane isolation and write-safety?
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import build_compiled_context_pack


REPO = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_artifact_candidates_20260612/rich_leaf_artifact_candidates.json"
)
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_context_pack_projection_ab_20260612/context_pack_projection_ab.json"
)
SCHEMA = "luban_rich_leaf_context_pack_projection_ab.v1"
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


def _pack_metrics(pack: dict[str, Any]) -> dict[str, Any]:
    trace = pack.get("consumption_trace") if isinstance(pack.get("consumption_trace"), dict) else {}
    lanes = sorted({str(ref.get("source_lane")) for ref in pack.get("source_refs") or [] if isinstance(ref, dict)})
    encoded = json.dumps(
        {"fields": pack.get("fields") or [], "source_refs": pack.get("source_refs") or []},
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "field_count": len(pack.get("fields") or []),
        "source_ref_count": len(pack.get("source_refs") or []),
        "source_ref_lanes": lanes,
        "json_char_count": len(encoded),
        "token_proxy": max(1, len(encoded) // 4) if encoded != '{"fields": [], "source_refs": []}' else 0,
        "consumed_field_ids": trace.get("consumed_field_ids") or [],
        "stripped_candidate_field_ids": trace.get("stripped_candidate_field_ids") or [],
        "fail_closed_reasons": trace.get("fail_closed_reasons") or [],
        "canonical_write_allowed": pack.get("canonical_write_allowed"),
        "production_write_count": pack.get("production_write_count"),
        "official_score_allowed": pack.get("official_score_allowed"),
    }


def _build_task_packs(*, artifacts: list[dict[str, Any]], bundle_version: str, manifest_hash: str) -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for task in TASKS:
        packs[task] = build_compiled_context_pack(
            task=task,
            artifacts=artifacts,
            bundle_version=bundle_version,
            manifest_hash=manifest_hash,
        ).to_dict()
    return packs


def _classification_safe(payload: dict[str, Any], name: str, blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{name}_classification_runtime_or_release_allowed:{key}")


def run_context_pack_projection_ab(
    *,
    artifact_candidates: dict[str, Any],
    field_promotion_review: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if artifact_candidates.get("schema") != "luban_rich_leaf_artifact_candidate_batch.v1":
        blockers.append(f"artifact_candidates_schema_mismatch:{artifact_candidates.get('schema')}")
    if artifact_candidates.get("verdict") != "PASS":
        blockers.append(f"artifact_candidates_failed:{artifact_candidates.get('verdict')}")
    if field_promotion_review.get("schema") != "luban_rich_leaf_field_promotion_review.v1":
        blockers.append(f"field_promotion_review_schema_mismatch:{field_promotion_review.get('schema')}")
    if field_promotion_review.get("verdict") != "PASS":
        blockers.append(f"field_promotion_review_failed:{field_promotion_review.get('verdict')}")
    _classification_safe(artifact_candidates, "artifact_candidates", blockers)
    _classification_safe(field_promotion_review, "field_promotion_review", blockers)

    control_artifacts = [
        artifact
        for artifact in artifact_candidates.get("rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    treatment_artifacts = [
        artifact
        for artifact in field_promotion_review.get("promoted_rich_leaf_artifact_candidates") or []
        if isinstance(artifact, dict)
    ]
    control_packs = _build_task_packs(
        artifacts=control_artifacts,
        bundle_version="v_rich_leaf_projection_ab_control_20260612",
        manifest_hash=str(len(control_artifacts)),
    )
    treatment_packs = _build_task_packs(
        artifacts=treatment_artifacts,
        bundle_version="v_rich_leaf_projection_ab_treatment_20260612",
        manifest_hash=str(len(treatment_artifacts)),
    )

    effect_table: list[dict[str, Any]] = []
    improved_task_count = 0
    knowledge_task_leak_count = 0
    for task in TASKS:
        control = _pack_metrics(control_packs[task])
        treatment = _pack_metrics(treatment_packs[task])
        if control["fail_closed_reasons"]:
            blockers.append(f"control_context_pack_fail_closed:{task}:{'|'.join(control['fail_closed_reasons'])}")
        if treatment["fail_closed_reasons"]:
            blockers.append(f"treatment_context_pack_fail_closed:{task}:{'|'.join(treatment['fail_closed_reasons'])}")
        for arm_name, metrics in (("control", control), ("treatment", treatment)):
            if metrics["canonical_write_allowed"] is not False or metrics["official_score_allowed"] is not False:
                blockers.append(f"{arm_name}_context_pack_write_or_score_allowed:{task}")
            if metrics["production_write_count"] not in (0, False):
                blockers.append(f"{arm_name}_context_pack_production_write_count_nonzero:{task}")
        knowledge_leak = task in KNOWLEDGE_TASKS and "question" in treatment["source_ref_lanes"]
        if knowledge_leak:
            knowledge_task_leak_count += 1
            blockers.append(f"treatment_question_lane_source_ref_in_knowledge_task:{task}")
        field_delta = treatment["field_count"] - control["field_count"]
        if field_delta > 0:
            improved_task_count += 1
        effect_table.append(
            {
                "task": task,
                "control_field_count": control["field_count"],
                "treatment_field_count": treatment["field_count"],
                "field_count_delta": field_delta,
                "control_source_ref_count": control["source_ref_count"],
                "treatment_source_ref_count": treatment["source_ref_count"],
                "source_ref_count_delta": treatment["source_ref_count"] - control["source_ref_count"],
                "control_source_ref_lanes": control["source_ref_lanes"],
                "treatment_source_ref_lanes": treatment["source_ref_lanes"],
                "control_token_proxy": control["token_proxy"],
                "treatment_token_proxy": treatment["token_proxy"],
                "token_proxy_delta": treatment["token_proxy"] - control["token_proxy"],
                "knowledge_task_question_lane_leak": knowledge_leak,
            }
        )

    if improved_task_count == 0:
        blockers.append("projection_ab_no_task_field_gain")

    return {
        "schema": SCHEMA,
        "input_schemas": {
            "artifact_candidates": artifact_candidates.get("schema"),
            "field_promotion_review": field_promotion_review.get("schema"),
        },
        "verdict": "FAIL" if blockers else "PASS",
        "verdict_ceiling": "PROJECTION_ONLY",
        "quality_claim_allowed": False,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "context_pack_projection_ab": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "control_artifact_count": len(control_artifacts),
            "treatment_artifact_count": len(treatment_artifacts),
            "task_count": len(effect_table),
            "improved_task_count": improved_task_count,
            "knowledge_task_question_lane_leak_count": knowledge_task_leak_count,
            "blocker_count": len(blockers),
        },
        "effect_table": effect_table,
        "blockers": blockers,
        "not_exercised": [
            "live_runtime_accuracy",
            "live_runtime_latency",
            "live_runtime_token_usage",
            "llm_judge_semantic_quality",
            "learner_outcome_gain",
            "production_default_decision",
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
    parser.add_argument("--artifact-candidates", type=Path, default=DEFAULT_ARTIFACT_CANDIDATES)
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_context_pack_projection_ab(
        artifact_candidates=_read_json(args.artifact_candidates),
        field_promotion_review=_read_json(args.field_promotion_review),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
