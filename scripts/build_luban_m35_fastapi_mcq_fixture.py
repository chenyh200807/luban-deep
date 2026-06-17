#!/usr/bin/env python3
"""Build an M35 shadow fixture from FastAPI multiple-choice exam JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


YEAR_RE = re.compile(r"V(\d{4})\.json$")


def _correct_set(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return sorted(str(item).strip().upper() for item in raw if str(item).strip())
    return sorted(char for char in str(raw or "").upper() if char.isalpha())


def _wrong_options(options: list[dict[str, Any]], correct: list[str]) -> list[str]:
    correct_set = set(correct)
    return [str(option.get("key") or "").upper() for option in options if str(option.get("key") or "").upper() not in correct_set]


def _score_answer(answer: str, correct: list[str], options: list[dict[str, Any]], max_score: float) -> float:
    selected = sorted(char for char in str(answer or "").upper() if char.isalpha())
    correct_set = set(correct)
    if selected == correct:
        return max_score
    if any(option not in correct_set for option in selected):
        return 0.0
    return min(max_score, 0.5 * len(selected))


def _answer_variants(correct: list[str], options: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    max_score = 2.0
    wrong = _wrong_options(options, correct)
    missing = "".join(correct[:-1] or correct)
    wrong_only = wrong[0] if wrong else ""
    overselect = "".join(sorted(set(correct + wrong[:1])))
    empty = ""
    return [
        ("correct", "".join(correct), max_score),
        ("missing_one", missing, _score_answer(missing, correct, options, max_score)),
        ("wrong_only", wrong_only, 0.0),
        ("overselect", overselect, 0.0 if wrong else max_score),
        ("blank", empty, 0.0),
    ]


def _iter_mcq(source_dir: Path) -> list[dict[str, Any]]:
    items = []
    for path in sorted(source_dir.glob("*年一级建造师《建筑实务》考试真题及答案解析/FINAL_CLEANED_EXAM_V*.json")):
        year_match = YEAR_RE.search(path.name)
        year = year_match.group(1) if year_match else "unknown"
        data = json.loads(path.read_text(encoding="utf-8"))
        ordinal = 0
        for chunk in data.get("chunks", []):
            for exercise in chunk.get("exercises") or []:
                if exercise.get("type") != "multiple_choice":
                    continue
                qd = exercise.get("question_data") or {}
                correct = _correct_set(qd.get("correct_answer"))
                options = qd.get("options") or []
                if len(correct) < 2 or not options:
                    continue
                ordinal += 1
                question_id = f"MCQ-{year}-{chunk.get('chunk_id')}-{ordinal:03d}"
                items.append(
                    {
                        "question_id": question_id,
                        "year": year,
                        "chunk_id": chunk.get("chunk_id"),
                        "stem": str(qd.get("stem") or "").strip(),
                        "options": options,
                        "correct_answer": correct,
                        "analysis": qd.get("analysis"),
                        "total_score": float(qd.get("score") or 2.0),
                        "source_path": str(path),
                    }
                )
    return items


def build_fixture(*, source_dir: Path, output_dir: Path, target_question_count: int) -> dict[str, Any]:
    selected = _iter_mcq(source_dir)[:target_question_count]
    questions = []
    rows = []
    for item in selected:
        content_hash = hashlib.sha256(
            json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        scoring_points = [
            {
                "point_id": f"OPT_{key}",
                "criterion": f"选择正确选项 {key}",
                "max_score": item["total_score"] / max(1, len(item["correct_answer"])),
            }
            for key in item["correct_answer"]
        ]
        questions.append(
            {
                "question_id": item["question_id"],
                "title": f"{item['year']} 多选题 {item['chunk_id']}",
                "stem": item["stem"],
                "total_score": item["total_score"],
                "source_refs": [
                    {
                        "source_type": "fastapi_exam_json",
                        "chunk_id": item["chunk_id"],
                        "verified": False,
                    }
                ],
                "question_authority_ref": {
                    "module": "FastAPI20251222.docs.2026.exam_json",
                    "source_path": item["source_path"],
                    "content_hash": content_hash,
                },
            }
        )
        for variant, answer, score in _answer_variants(item["correct_answer"], item["options"]):
            wrong_options = _wrong_options(item["options"], item["correct_answer"])
            rows.append(
                {
                    "answer_id": f"{item['question_id']}__{variant}",
                    "question_id": item["question_id"],
                    "student_id": f"synthetic_{variant}",
                    "student_answer": answer,
                    "variant": variant,
                    "gold_score": score,
                    "gold_point_matches": scoring_points,
                    "scoring_points": scoring_points,
                    "scoring_protocol": {
                        "question_type": "multiple_choice",
                        "correct_answer": "".join(item["correct_answer"]),
                        "wrong_options": wrong_options,
                        "overselect_policy": "zero_score_if_any_wrong_option_selected",
                        "missing_correct_option_policy": "0.5_per_selected_correct_option_without_wrong_options",
                        "partial_credit_per_selected_correct_option": 0.5,
                    },
                    "label_authority": "generated_from_official_mcq_key",
                    "label_scope": "deterministic_mcq_variant",
                    "directionality_flag": "generated_mcq_answer_variant",
                    "correct_answer": "".join(item["correct_answer"]),
                    "analysis": item["analysis"],
                }
            )

    source_status = "OK" if len(questions) >= target_question_count else "SOURCE_LIMIT"
    manifest = {
        "schema_version": "luban_m35_fastapi_mcq_fixture.v1",
        "source": str(source_dir),
        "source_status": source_status,
        "requested_question_count": target_question_count,
        "requested_answer_count": target_question_count * 5,
        "actual_question_count": len(questions),
        "actual_answer_count": len(rows),
        "label_authority": "generated_from_official_mcq_key",
        "fixture_grain": "multiple_choice_option_set",
        "quality_claim_allowed": False,
        "official_score_allowed": False,
        "questions": questions,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-question-count", type=int, default=20)
    args = parser.parse_args()
    manifest = build_fixture(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        target_question_count=max(0, args.target_question_count),
    )
    print(
        json.dumps(
            {
                "source_status": manifest["source_status"],
                "actual_question_count": manifest["actual_question_count"],
                "actual_answer_count": manifest["actual_answer_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
