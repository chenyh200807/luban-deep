#!/usr/bin/env python3
"""Audit M35 fixture coverage against the current scoring artifact authority.

This runner is intentionally read-only. It does not compile artifacts, does not
write learner truth, and does not promote compiler work orders to release truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading import compiler_feedback
from deeptutor.services.construction_grading import question_grading_artifacts as qga


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _question_rows(manifest: dict[str, Any], answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(manifest.get("questions") or [])
    if rows:
        return rows

    seen: dict[str, dict[str, Any]] = {}
    for answer in answers:
        question_id = str(answer.get("question_id") or "").strip()
        if question_id and question_id not in seen:
            seen[question_id] = {"question_id": question_id}
    return list(seen.values())


def _answer_counts(answers: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for answer in answers:
        question_id = str(answer.get("question_id") or "").strip()
        if question_id:
            counts[question_id] += 1
    return counts


def _missing_artifact_work_order(
    *,
    fixture_id: str,
    question: dict[str, Any],
    answer_count: int,
) -> dict[str, Any]:
    question_id = str(question.get("question_id") or question.get("id") or "").strip()
    return compiler_feedback.make_candidate(
        kind=compiler_feedback.KIND_WORK_ORDER,
        origin="m35_artifact_coverage_audit",
        payload={
            "work_order_type": "compile_missing_scoring_artifact",
            "fixture_id": fixture_id,
            "question_id": question_id,
            "stem": question.get("stem") or "",
            "source_refs": list(question.get("source_refs") or []),
            "sample_answer_count": answer_count,
            "runtime_usable_as_truth": False,
            "promote_to_release": False,
        },
        reason="artifact_missing",
    )


def audit_fixture_coverage(fixture: Path) -> dict[str, Any]:
    manifest = _read_json(fixture / "manifest.json")
    answers = _read_jsonl(fixture / "student_answers.jsonl")
    fixture_id = str(manifest.get("fixture_id") or fixture.name)
    answer_counts = _answer_counts(answers)

    question_reports: list[dict[str, Any]] = []
    work_orders: list[dict[str, Any]] = []
    compiled_count = 0
    blocked_count = 0
    runtime_consumable_count = 0

    for question in _question_rows(manifest, answers):
        question_id = str(question.get("question_id") or question.get("id") or "").strip()
        if not question_id:
            continue

        artifact = qga.build_question_grading_artifact(question_id)
        sample_count = int(answer_counts.get(question_id, 0))
        if artifact.get("artifact_missing"):
            work_order = _missing_artifact_work_order(
                fixture_id=fixture_id,
                question=question,
                answer_count=sample_count,
            )
            work_orders.append(work_order)
            question_reports.append(
                {
                    "question_id": question_id,
                    "artifact_missing": True,
                    "runtime_consumable": False,
                    "sample_answer_count": sample_count,
                    "compiler_work_order_id": work_order["candidate_id"],
                }
            )
            continue

        compiled_count += 1
        status = str(artifact.get("status") or "")
        quality_gates = dict(artifact.get("quality_gates") or {})
        blocked_reasons = list(quality_gates.get("blocked_reasons") or [])
        runtime_consumable = status == "published" and not blocked_reasons
        if blocked_reasons or status == "blocked":
            blocked_count += 1
        if runtime_consumable:
            runtime_consumable_count += 1
        question_reports.append(
            {
                "question_id": question_id,
                "artifact_missing": False,
                "artifact_version": artifact.get("version_id"),
                "legacy_artifact_status": status,
                "runtime_consumable": runtime_consumable,
                "blocked_reasons": blocked_reasons,
                "sample_answer_count": sample_count,
                "source_validity": quality_gates.get("source_validity", 0.0),
            }
        )

    question_count = len(question_reports)
    missing_count = sum(1 for row in question_reports if row["artifact_missing"])
    coverage_rate = (compiled_count / question_count) if question_count else 0.0
    quality_claim_allowed = missing_count == 0 and blocked_count == 0 and question_count > 0
    verdict = "GO_SHADOW_COVERAGE" if quality_claim_allowed else "NO_GO_ARTIFACT_COVERAGE"

    return {
        "schema_version": "luban_m35_artifact_coverage_audit.v1",
        "fixture": str(fixture),
        "fixture_id": fixture_id,
        "question_count": question_count,
        "answer_count": len(answers),
        "compiled_artifact_count": compiled_count,
        "missing_artifact_count": missing_count,
        "blocked_artifact_count": blocked_count,
        "runtime_consumable_count": runtime_consumable_count,
        "coverage_rate": round(coverage_rate, 4),
        "quality_claim_allowed": quality_claim_allowed,
        "verdict": verdict,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "promote_to_release": False,
        "questions": question_reports,
        "compiler_work_orders": work_orders,
        "compiler_ledger": compiler_feedback.build_ledger(work_orders),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = audit_fixture_coverage(Path(args.fixture))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
