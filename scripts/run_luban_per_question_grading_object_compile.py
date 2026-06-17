#!/usr/bin/env python3
"""Compile real case-study exam questions into per-question grading objects (demo).

Thin CLI over the fat skill
``deeptutor.services.construction_grading.per_question_grading_object``. It selects a
few real case-study questions from the 2023/2024 exam bank, compiles each into a typed
``luban_per_question_grading_object.v1`` object (deterministic, no LLM, no network, no DB
write), validates the single-authority hard gates, and writes the typed JSON plus a
human-readable markdown rendering so a person can see what a task-specific typed grading
object actually looks like.

Authority is source-locked: every scoring point is a verbatim slice of the official
``correct_answer`` (A); textbook terms are supporting citations (B) or honestly
``unsourced``; per-point scores are null + pending; the official total is the only score.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.per_question_grading_object import (
    compile_per_question_grading_object,
    render_markdown,
    validate_per_question_grading_object,
)

DEFAULT_EXAM_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库"
)
DEFAULT_BOOK_DIR = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强"
)
DEFAULT_OUT_DIR = Path("artifacts/luban_grading_artifacts/per_question_grading_object_demo_20260613")

# Real, diverse case-study questions (chunk_id, exercise index) selected from the bank.
# Subtypes covered: flaw_correction + enumeration, network/calculation, exceptions + calc.
SELECTED = [
    {"year": 2023, "chunk_id": "EXAM_1A434000_P0010_02", "exercise_index": 0,
     "question_id": "Q2023-1A434000-P0010-02-Q1", "note": "flaw_correction + enumeration (见证记录)"},
    {"year": 2023, "chunk_id": "EXAM_1A433000_P0012_02", "exercise_index": 0,
     "question_id": "Q2023-1A433000-P0012-02-Q1", "note": "calculation (网络计划/成倍节拍)"},
    {"year": 2024, "chunk_id": "EXAM_1A432000_P0015_01", "exercise_index": 0,
     "question_id": "Q2024-1A432000-P0015-01", "note": "enumeration + exceptions + calculation (22分)"},
]


def _load_exam_chunks(exam_root: Path, year: int) -> dict[str, dict[str, Any]]:
    path = (
        exam_root
        / f"{year}年一级建造师《建筑实务》考试真题及答案解析"
        / f"FINAL_CLEANED_EXAM_V{year}.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {c["chunk_id"]: c for c in data.get("chunks", [])}


def _load_textbook_chunks(book_dir: Path) -> list[dict[str, Any]]:
    """Load textbook content blocks for B-authority anchor verification (supporting)."""
    chunks: list[dict[str, Any]] = []
    if not book_dir.exists():
        return chunks
    for path in sorted(book_dir.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = payload.get("content_blocks") if isinstance(payload, dict) else payload
        for block in blocks or []:
            if isinstance(block, dict) and block.get("chunk_id") and block.get("content_markdown"):
                chunks.append(block)
    return chunks


def compile_selected(
    *, exam_root: Path, textbook_chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for sel in SELECTED:
        chunks = _load_exam_chunks(exam_root, sel["year"])
        chunk = chunks.get(sel["chunk_id"])
        if chunk is None:
            raise SystemExit(f"source chunk not found: {sel['chunk_id']} ({sel['year']})")
        exercises = chunk.get("exercises") or []
        if sel["exercise_index"] >= len(exercises):
            raise SystemExit(f"exercise index out of range: {sel['chunk_id']}")
        qd = exercises[sel["exercise_index"]].get("question_data") or {}
        source_path = str(
            exam_root
            / f"{sel['year']}年一级建造师《建筑实务》考试真题及答案解析"
            / f"FINAL_CLEANED_EXAM_V{sel['year']}.json"
        )
        obj = compile_per_question_grading_object(
            question_id=sel["question_id"],
            stem=str(qd.get("stem") or ""),
            correct_answer=str(qd.get("correct_answer") or ""),
            official_total_score=qd.get("score"),
            textbook_chunks=textbook_chunks,
            chunk_id=sel["chunk_id"],
            official_analysis=qd.get("analysis"),
            source_path=source_path,
        )
        obj["selection_note"] = sel["note"]
        blockers = validate_per_question_grading_object(obj)
        if blockers:
            raise SystemExit(f"validation failed for {sel['question_id']}: {blockers}")
        objects.append(obj)
    return objects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument("--book-dir", type=Path, default=DEFAULT_BOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    textbook_chunks = _load_textbook_chunks(args.book_dir)
    objects = compile_selected(exam_root=args.exam_root, textbook_chunks=textbook_chunks)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_id": "luban_per_question_grading_object.v1",
        "compiler": "scripts/run_luban_per_question_grading_object_compile.py",
        "extraction": "deterministic_no_llm",
        "textbook_chunks_loaded": len(textbook_chunks),
        "questions": [],
    }
    for obj in objects:
        qid = obj["question_id"]
        (out_dir / f"{qid}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / f"{qid}.md").write_text(render_markdown(obj), encoding="utf-8")
        summary["questions"].append(
            {
                "question_id": qid,
                "chunk_id": obj["chunk_id"],
                "official_total_score": obj["official_total_score"],
                "scoring_point_count": obj["scoring_point_count"],
                "textbook_anchor_hit": obj["textbook_anchor_hit"],
                "textbook_anchor_total": obj["textbook_anchor_total"],
                "textbook_anchor_hit_rate": obj["textbook_anchor_hit_rate"],
                "selection_note": obj["selection_note"],
            }
        )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
