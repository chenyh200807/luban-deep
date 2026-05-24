#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.lecture_compiler import compile_lecture_card
from deeptutor.services.source_compiler.metadata import utc_now_iso
from deeptutor.services.source_compiler.platform import RunDirectoryLock, detect_dataless
from deeptutor.services.source_compiler.question_compiler import compile_question_capsule
from deeptutor.services.source_compiler.rubric_compiler import compile_option_reasoning_backfill, compile_rubric_candidate
from deeptutor.services.source_compiler.source_inventory import classify_source
from deeptutor.services.source_compiler.source_reader import iter_payload_records, load_source_payload
from deeptutor.services.source_compiler.standard_compiler import compile_standard_clause
from deeptutor.services.source_compiler.taxonomy_loader import build_taxonomy_index


SUPPORTED_CLASSES = {"standard", "question", "lecture_bundle", "book", "taxonomy"}


def _source_root() -> Path:
    value = os.environ.get("LUBAN_2026_SOURCE_ROOT")
    if not value:
        raise RuntimeError("LUBAN_2026_SOURCE_ROOT is required and must point to docs/2026.")
    return Path(value)


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def _paths(source_root: Path, only_class: str | None, limit: int | None) -> list[Path]:
    selected: list[Path] = []
    for path in sorted(source_root.rglob("*.json")):
        source_class = classify_source(path, source_root)
        if source_class not in SUPPORTED_CLASSES:
            continue
        if only_class and source_class != only_class:
            continue
        selected.append(path)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--only-class", choices=sorted(SUPPORTED_CLASSES))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        source_root = _source_root()
        run_dir = _run_dir(args.run_id)
        lock = RunDirectoryLock(run_dir, force=args.force)
        lock.prepare()
        compiled_at = utc_now_iso()
        taxonomy: list[dict] = []
        standards: list[dict] = []
        questions: list[dict] = []
        question_joined: list[dict] = []
        question_unmatched: list[dict] = []
        rubrics: list[dict] = []
        option_reasoning: list[dict] = []
        lectures: list[dict] = []
        try:
            for path in _paths(source_root, args.only_class, args.limit):
                if detect_dataless(path, platform_name="darwin"):
                    continue
                loaded = load_source_payload(path, source_root)
                records = []
                for index, record in enumerate(iter_payload_records(loaded["payload"])):
                    indexed = dict(record)
                    indexed.setdefault("_source_index", index)
                    records.append(indexed)
                source_path = loaded["source_path"]
                if loaded["source_class"] == "taxonomy":
                    taxonomy.extend(
                        build_taxonomy_index(records, run_id=args.run_id, source_path=source_path, compiled_at=compiled_at)
                    )
                elif loaded["source_class"] == "standard":
                    standards.extend(
                        compile_standard_clause(record, run_id=args.run_id, source_path=source_path, compiled_at=compiled_at)
                        for record in records
                    )
                elif loaded["source_class"] == "question":
                    for record in records:
                        capsule = compile_question_capsule(
                            record,
                            run_id=args.run_id,
                            source_path=source_path,
                            compiled_at=compiled_at,
                        )
                        questions.append(capsule)
                        if capsule.get("option_reasoning") and capsule.get("candidate_questions_bank_id") is not None:
                            option_reasoning.append(
                                compile_option_reasoning_backfill(
                                    capsule,
                                    existing_option_reasoning=None,
                                    run_id=args.run_id,
                                    source_path=source_path,
                                    compiled_at=compiled_at,
                                )
                            )
                        rubric = compile_rubric_candidate(capsule, run_id=args.run_id, source_path=source_path, compiled_at=compiled_at)
                        if rubric:
                            rubrics.append(rubric)
                elif loaded["source_class"] == "lecture_bundle":
                    lectures.extend(
                        compile_lecture_card(record, run_id=args.run_id, source_path=source_path, compiled_at=compiled_at)
                        for record in records
                    )

            write_jsonl(run_dir / "taxonomy_index.jsonl", taxonomy)
            write_jsonl(run_dir / "standard_clauses.jsonl", standards)
            write_jsonl(run_dir / "question_capsules.jsonl", questions)
            if questions:
                question_unmatched = [
                    {"stable_question_source_id": row["stable_question_source_id"], "reason": "no_questions_bank_export"}
                    for row in questions
                ]
            write_jsonl(run_dir / "question_capsule_to_questions_bank.jsonl", question_joined)
            write_jsonl(run_dir / "question_capsule_unmatched.jsonl", question_unmatched)
            write_jsonl(run_dir / "rubric_candidates.jsonl", rubrics)
            write_jsonl(run_dir / "option_reasoning_backfill.jsonl", option_reasoning)
            write_jsonl(run_dir / "lecture_teaching_cards.jsonl", lectures)
            print(
                " ".join(
                    [
                        f"taxonomy={len(taxonomy)}",
                        f"standard={len(standards)}",
                        f"question={len(questions)}",
                        f"rubric={len(rubrics)}",
                        f"option_reasoning={len(option_reasoning)}",
                        f"lecture_bundle={len(lectures)}",
                    ]
                )
            )
            return 0
        finally:
            lock.release()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
