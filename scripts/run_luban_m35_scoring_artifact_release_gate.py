#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deeptutor.services.construction_grading.m35_artifact_shadow import (  # noqa: E402
    build_m35_artifact_shadow_payload,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _zero_metrics() -> dict[str, float]:
    return {
        "point_precision": 0.0,
        "point_recall": 0.0,
        "score_mae": 0.0,
        "source_validity": 0.0,
        "wrong_path_rate": 0.0,
        "fail_open_rate": 0.0,
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


def _sample_safety_violations(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    expected = {
        "production_write_count": 0,
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "quality_claim_allowed": False,
        "db_write_count": 0,
        "remote_write_count": 0,
        "rag_lookup_count": 0,
    }
    for index, sample in enumerate(samples):
        for key, expected_value in expected.items():
            if sample.get(key) != expected_value:
                violations.append(
                    {
                        "sample_index": index,
                        "field": key,
                        "expected": expected_value,
                        "actual": sample.get(key),
                    }
                )
    return violations


def build_report(*, fixture: Path) -> dict[str, Any]:
    manifest_path = fixture / "manifest.json"
    answers_path = fixture / "student_answers.jsonl"
    manifest = _read_json(manifest_path)
    rows = _read_jsonl(answers_path)
    samples = [
        build_m35_artifact_shadow_payload(
            question_id=str(row.get("question_id") or ""),
            student_id="qa_m35_release_gate",
            student_answer=str(row.get("student_answer") or ""),
        )
        for row in rows[:3]
    ]
    sample_safety_violations = _sample_safety_violations(samples)
    return {
        "verdict": "NO-GO",
        "evaluation_tier": "shape_stub",
        "quality_claim_allowed": False,
        "verdict_ceiling": "NO-GO_OR_SHAPE_ONLY",
        "metrics": _zero_metrics(),
        "safety": _safety(),
        "fixture": {
            "fixture_id": manifest.get("fixture_id"),
            "answer_label_authority": manifest.get("answer_label_authority"),
            "known_label_gap": bool(manifest.get("known_label_gap")),
            "answer_count": len(rows),
            "manifest_path": str(manifest_path),
            "answers_path": str(answers_path),
        },
        "shadow_sample_count": len(samples),
        "shadow_sample_safety_violation_count": len(sample_safety_violations),
        "shadow_sample_safety_violations": sample_safety_violations,
        "shadow_samples": samples,
        "notes": [
            "shape_stub verifies runtime payload shape only; it is not a quality GO",
            "runner performs no DB, remote, provider, RAG, memory, or WebSocket route writes",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(fixture=args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
