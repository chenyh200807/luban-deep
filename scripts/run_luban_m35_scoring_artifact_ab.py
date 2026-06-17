from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.construction_grading.question_grading_artifacts import (  # noqa: E402
    build_question_grading_artifact,
)
from scripts.audit_luban_m35_label_authority import audit as audit_label_authority  # noqa: E402


DEFAULT_FIXTURE_DIR = ROOT / "tests/fixtures/luban_m35_case_scoring"
DEFAULT_ANSWERS = DEFAULT_FIXTURE_DIR / "student_answers.jsonl"
DEFAULT_MANIFEST = DEFAULT_FIXTURE_DIR / "manifest.json"
PRIOR_POINT_HIT_AGREEMENT = 0.5267
PRIOR_SCORE_MAE = 4.6091
TIERS = {"shape_stub", "cached_judge_replay", "live_provider_sample"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _limited_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return rows
    return rows[:limit]


def _manifest_artifacts(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for question in manifest.get("questions") or []:
        question_id = str(question.get("question_id") or "")
        points = question.get("scoring_points") or []
        if not question_id or not points:
            continue
        verified_points = sum(
            1
            for point in points
            if any(
                ref.get("source_type") == "exam_reference_answer"
                and ref.get("verified") is True
                for ref in (point.get("source_refs") or [])
            )
        )
        artifacts[question_id] = {
            "question_id": question_id,
            "scoring_points": points,
            "artifact_missing": False,
            "verified_source_point_count": verified_points,
            "source_pollution_count": 0,
        }
    return artifacts


def _artifact_summary(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    question_ids = sorted({str(row.get("question_id") or "") for row in rows})
    manifest_artifacts = _manifest_artifacts(manifest)
    artifacts = {
        question_id: manifest_artifacts.get(question_id)
        or build_question_grading_artifact(question_id)
        for question_id in question_ids
        if question_id
    }
    available = [item for item in artifacts.values() if not item.get("artifact_missing")]
    total_points = sum(len(item.get("scoring_points") or []) for item in available)
    verified_points = sum(
        int(item.get("verified_source_point_count"))
        if item.get("verified_source_point_count") is not None
        else sum(
            1
            for point in (item.get("scoring_points") or [])
            if point.get("source_status") == "ok"
        )
        for item in available
    )
    source_pollution = sum(
        int(
            item.get("source_pollution_count")
            if item.get("source_pollution_count") is not None
            else (item.get("quality_gates") or {}).get("source_pollution_count")
            or 0
        )
        for item in available
    )
    return {
        "question_count": len(question_ids),
        "artifact_available_count": len(available),
        "artifact_missing_count": len(question_ids) - len(available),
        "total_scoring_points": total_points,
        "verified_source_point_count": verified_points,
        "source_pollution_count": source_pollution,
        "artifacts": artifacts,
    }


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _metrics(rows: list[dict[str, Any]], artifact_summary: dict[str, Any]) -> dict[str, Any]:
    question_count = artifact_summary["question_count"]
    artifact_available_count = artifact_summary["artifact_available_count"]
    artifact_missing_count = artifact_summary["artifact_missing_count"]
    total_points = artifact_summary["total_scoring_points"]
    verified_points = artifact_summary["verified_source_point_count"]
    source_pollution_count = artifact_summary["source_pollution_count"]

    return {
        "compiled_hit_rate": _ratio(artifact_available_count, question_count),
        "wrong_path_rate": _ratio(artifact_missing_count, question_count),
        "source_validity": _ratio(verified_points, total_points),
        "answer_improvement": None,
        "token_cost": {
            "baseline_total_tokens": 0,
            "rag_only_total_tokens": 0,
            "artifact_first_total_tokens": 0,
            "delta_vs_baseline": 0,
            "basis": "not_exercised_offline_shape_runner",
        },
        "fail_open_rate": 0.0,
        "point_precision": None,
        "point_recall": None,
        "score_mae": None,
        "hallucinated_scoring_points": 0,
        "source_pollution_count": source_pollution_count,
        "metric_basis": "hermetic_shape_metrics_no_quality_claim",
        "quality_metric_status": "not_claimed_without_governed_labels",
        "sampled_answer_count": len(rows),
    }


def _safety() -> dict[str, Any]:
    return {
        "production_write_count": 0,
        "canonical_truth_written": False,
        "rag_chunk_as_answer_key": 0,
        "candidate_used_as_release_truth": 0,
        "client_status_promoted_to_release_truth": 0,
        "shadow_changed_legacy_result": 0,
        "db_write_count": 0,
        "remote_write_count": 0,
        "provider_call_count": 0,
    }


def _arms(tier: str, live_enabled: bool) -> dict[str, Any]:
    live_status = "not_exercised"
    if tier == "live_provider_sample" and not live_enabled:
        live_status = "bounded_sample_disabled"
    elif tier == "live_provider_sample":
        live_status = "not_exercised"

    return {
        "baseline": {
            "status": "not_exercised",
            "reason": "no committed baseline adapter used by this hermetic Task 4 shape runner",
        },
        "rag_only": {
            "status": "not_exercised",
            "reason": "runner never lets RAG chunks become answer-key authority",
        },
        "artifact_first": {
            "status": "shape_evaluated",
            "reason": "question_grading_artifacts loaded for fixture question ids",
        },
        "live_provider_sample": {
            "status": live_status,
            "provider_called": False,
            "reason": (
                "explicit live provider opt-in was not provided"
                if live_status == "bounded_sample_disabled"
                else "provider calls are intentionally absent from this runner"
            ),
        },
    }


def _prior_failure_comparison(quality_claim_allowed: bool) -> dict[str, Any]:
    return {
        "old_human_vs_artifact_first_point_hit_agreement": PRIOR_POINT_HIT_AGREEMENT,
        "old_mean_abs_score_delta": PRIOR_SCORE_MAE,
        "current_point_precision": None,
        "current_score_mae": None,
        "prior_artifact_first_failure_beaten": False,
        "comparison_basis": (
            "governed_quality_metrics_required"
            if quality_claim_allowed
            else "not_claimed_generated_self_label_fixture"
        ),
    }


def build_report(
    *,
    tier: str,
    answers_path: Path,
    manifest_path: Path,
    fixture_limit: int,
    allow_live_provider_sample: bool,
) -> dict[str, Any]:
    rows = _read_jsonl(answers_path)
    sampled_rows = _limited_rows(rows, fixture_limit)
    manifest = _read_json(manifest_path)
    label_audit = audit_label_authority(answers_path)
    artifact_summary = _artifact_summary(sampled_rows, manifest)

    label_quality_allowed = bool(label_audit.get("quality_claim_allowed"))
    metrics = _metrics(sampled_rows, artifact_summary)
    # Quality may only be claimed when governed labels allow it, the tier is not
    # a shape stub, AND the quality metrics were actually computed (never None).
    quality_metrics_computed = (
        metrics.get("point_precision") is not None
        and metrics.get("point_recall") is not None
        and metrics.get("score_mae") is not None
    )
    quality_claim_allowed = (
        label_quality_allowed and tier != "shape_stub" and quality_metrics_computed
    )
    verdict_ceiling = (
        str(label_audit.get("verdict_ceiling") or "NO-GO_LABEL_UNKNOWN")
        if quality_claim_allowed
        else "NO-GO_OR_SHAPE_ONLY"
    )
    live_enabled = allow_live_provider_sample and os.getenv(
        "LUBAN_M35_ENABLE_LIVE_PROVIDER_SAMPLE"
    ) == "1"

    return {
        "schema_version": "luban_m35_scoring_artifact_ab.v1",
        "evaluation_tier": tier,
        "verdict": "NO-GO",
        "quality_claim_allowed": quality_claim_allowed,
        "verdict_ceiling": verdict_ceiling,
        "fixture": {
            "manifest_id": manifest.get("fixture_id"),
            "answers_path": str(answers_path),
            "manifest_path": str(manifest_path),
            "fixture_limit": fixture_limit,
            "sampled_answer_count": len(sampled_rows),
            "total_answer_count": len(rows),
            "answer_label_authority": manifest.get("answer_label_authority"),
        },
        "label_audit": label_audit,
        "metrics": metrics,
        "prior_failure_comparison": _prior_failure_comparison(quality_claim_allowed),
        "safety": _safety(),
        "arms": _arms(tier, live_enabled),
        "artifact_first": {
            "question_count": artifact_summary["question_count"],
            "artifact_available_count": artifact_summary["artifact_available_count"],
            "artifact_missing_count": artifact_summary["artifact_missing_count"],
            "total_scoring_points": artifact_summary["total_scoring_points"],
            "verified_source_point_count": artifact_summary[
                "verified_source_point_count"
            ],
        },
        "notes": [
            "generated_self_label fixtures are shape-only and cannot support quality claims",
            "this runner does not call live providers, write DB state, write remote state, or touch RAG/WS/memory",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--fixture-limit", type=int, default=20)
    parser.add_argument("--tier", choices=sorted(TIERS), default="shape_stub")
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--allow-live-provider-sample", action="store_true")
    args = parser.parse_args()

    report = build_report(
        tier=args.tier,
        answers_path=args.answers,
        manifest_path=args.manifest,
        fixture_limit=args.fixture_limit,
        allow_live_provider_sample=args.allow_live_provider_sample,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
