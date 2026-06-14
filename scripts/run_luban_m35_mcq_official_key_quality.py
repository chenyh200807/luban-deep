#!/usr/bin/env python3
"""R5 MCQ official-answer-key quality line — deterministic, no LLM, no network.

Re-scores every fixture answer against the official MCQ answer key and reports
agreement with the fixture ``gold_score``:

- single choice: exact match earns full score, anything else earns zero;
- multiple choice (official yijian rule): any wrong selection scores zero;
  underselection earns proportional credit per selected correct option;
  blank scores zero.

The official key is the governance authority (``authority_basis =
"official_mcq_answer_key"``), so quality claims are allowed. When the fixture
``gold_score`` disagrees with the official-key recomputation, the runner
reports the mismatch verbatim on both sides — it never silently adopts either.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_m35_mcq_official_key_quality.v1"
SCORE_MATCH_TOLERANCE = 1e-6

# Official yijian MCQ rule, used verbatim when fixture rows do not carry
# explicit scoring_protocol policy fields.
RULE_SOURCE_FIXTURE = "fixture_scoring_protocol"
RULE_SOURCE_BUILTIN = "official_yijian_mcq_rule_builtin"
PROTOCOL_POLICY_FIELDS = ("overselect_policy", "missing_correct_option_policy")

SCORING_RULES = {
    "single_choice": "exact_match_full_score_else_zero",
    "multiple_choice_wrong_selection": "zero_score_if_any_wrong_option_selected",
    "multiple_choice_underselection": "partial_credit_per_selected_correct_option",
    "blank_answer": "zero_score",
}


def _zero_safety() -> dict[str, Any]:
    """Safety block aligned with run_luban_m35_scoring_artifact_release_gate."""
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


def _option_set(raw: Any) -> frozenset[str]:
    return frozenset(char for char in str(raw or "").upper() if char.isalpha())


def _point_scores(row: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for point in row.get("scoring_points") or []:
        point_id = str(point.get("point_id") or "")
        if point_id.startswith("OPT_"):
            scores[point_id[len("OPT_"):]] = float(point.get("max_score") or 0.0)
    return scores


def score_official_mcq(row: dict[str, Any]) -> float:
    """Deterministically score one answer against the official answer key."""
    protocol = row.get("scoring_protocol") or {}
    question_type = protocol.get("question_type")
    if question_type not in ("single_choice", "multiple_choice"):
        raise ValueError(
            f"answer {row.get('answer_id')!r}: unsupported question_type {question_type!r}"
        )
    correct = _option_set(protocol.get("correct_answer"))
    if not correct:
        raise ValueError(f"answer {row.get('answer_id')!r}: empty official correct_answer")

    point_scores = _point_scores(row)
    if point_scores:
        full_score = sum(point_scores.values())
    elif protocol.get("total_score") is not None:
        full_score = float(protocol["total_score"])
    else:
        raise ValueError(
            f"answer {row.get('answer_id')!r}: no scoring_points and no total_score"
        )

    selected = _option_set(row.get("student_answer"))
    if not selected:
        return 0.0
    if question_type == "single_choice":
        return full_score if selected == correct else 0.0
    if selected - correct:
        return 0.0
    if selected == correct:
        return full_score
    if point_scores:
        return sum(point_scores[key] for key in selected)
    return full_score * len(selected) / len(correct)


def _load_rows(answers_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        answers_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        for field in ("answer_id", "question_id", "gold_score", "scoring_protocol"):
            if field not in row:
                raise ValueError(f"{answers_path}:{line_number}: missing field {field!r}")
        rows.append(row)
    return rows


def _rule_source(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        protocol = row.get("scoring_protocol") or {}
        if not all(protocol.get(field) for field in PROTOCOL_POLICY_FIELDS):
            return RULE_SOURCE_BUILTIN
    return RULE_SOURCE_FIXTURE


def build_report(*, fixture_dir: Path) -> dict[str, Any]:
    manifest_path = fixture_dir / "manifest.json"
    answers_path = fixture_dir / "student_answers.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = _load_rows(answers_path)
    if not rows:
        raise ValueError(f"{answers_path}: fixture contains no answers")

    matched_total = 0
    absolute_errors: list[float] = []
    per_question_matched: Counter[str] = Counter()
    per_question_total: Counter[str] = Counter()
    mismatch_details: list[dict[str, Any]] = []

    for row in rows:
        official_score = score_official_mcq(row)
        gold_score = float(row["gold_score"])
        question_id = str(row["question_id"])
        error = abs(official_score - gold_score)
        absolute_errors.append(error)
        per_question_total[question_id] += 1
        if error <= SCORE_MATCH_TOLERANCE:
            matched_total += 1
            per_question_matched[question_id] += 1
        else:
            mismatch_details.append(
                {
                    "answer_id": row["answer_id"],
                    "question_id": question_id,
                    "official_key_score": official_score,
                    "fixture_gold_score": gold_score,
                }
            )

    answer_count = len(rows)
    question_count = len(per_question_total)
    per_question_accuracy = {
        question_id: per_question_matched[question_id] / total
        for question_id, total in sorted(per_question_total.items())
    }
    label_authority_counts = dict(
        Counter(str(row.get("label_authority")) for row in rows)
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "runner": "scripts/run_luban_m35_mcq_official_key_quality.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority_basis": "official_mcq_answer_key",
        "quality_claim_allowed": True,
        "rule_source": _rule_source(rows),
        "scoring_rules": dict(SCORING_RULES),
        "fixture": {
            "manifest_path": str(manifest_path),
            "answers_path": str(answers_path),
            "manifest_label_authority": manifest.get("label_authority"),
            "manifest_question_count": manifest.get("actual_question_count"),
            "manifest_answer_count": manifest.get("actual_answer_count"),
        },
        "metrics": {
            "accuracy": matched_total / answer_count,
            "score_mae": sum(absolute_errors) / answer_count,
            "answer_count": answer_count,
            "question_count": question_count,
            "per_question_accuracy": per_question_accuracy,
        },
        "label_authority_counts": label_authority_counts,
        "gold_score_mismatch": {
            "mismatch_count": len(mismatch_details),
            "mismatched_answer_ids": [
                detail["answer_id"] for detail in mismatch_details
            ],
            "details": mismatch_details,
        },
        "safety": _zero_safety(),
        "notes": [
            "deterministic official-key rescoring; no LLM, DB, RAG, remote, or network calls",
            "official yijian MCQ rule: wrong selection scores zero; underselection earns "
            "proportional credit per selected correct option",
            "gold_score mismatches are reported verbatim on both sides; the runner never "
            "silently adopts either the fixture gold or the recomputed score",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="fixture directory containing manifest.json and student_answers.jsonl",
    )
    parser.add_argument("--output", type=Path, required=True, help="report JSON path")
    args = parser.parse_args()

    report = build_report(fixture_dir=args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "accuracy": report["metrics"]["accuracy"],
                "score_mae": report["metrics"]["score_mae"],
                "answer_count": report["metrics"]["answer_count"],
                "question_count": report["metrics"]["question_count"],
                "mismatch_count": report["gold_score_mismatch"]["mismatch_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
