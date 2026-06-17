#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from deeptutor.services.source_compiler.answer_rubric_extractor import (
    compile_answer_derived_rubric_candidate,
    iter_case_study_answer_records,
)
from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.metadata import utc_now_iso
from deeptutor.services.source_compiler.platform import RunDirectoryLock, detect_dataless
from deeptutor.services.source_compiler.source_inventory import classify_source
from deeptutor.services.source_compiler.source_reader import load_source_payload


DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")


def _source_root(value: str | None) -> Path:
    if value:
        return Path(value)
    env_value = os.environ.get("LUBAN_2026_SOURCE_ROOT")
    if env_value:
        return Path(env_value)
    return DEFAULT_SOURCE_ROOT


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def _question_paths(source_root: Path, source_path: str | None, limit_files: int | None) -> list[Path]:
    if source_path:
        return [source_root / source_path]
    paths: list[Path] = []
    for path in sorted(source_root.rglob("*.json")):
        if classify_source(path, source_root) != "question":
            continue
        paths.append(path)
        if limit_files is not None and len(paths) >= limit_files:
            break
    return paths


def _preview_markdown(rows: list[dict], *, run_id: str) -> str:
    lines = [
        "# 2026 Answer-Derived Rubric MVP Preview",
        "",
        f"- run_id: `{run_id}`",
        f"- candidates: `{len(rows)}`",
        "- writeback: `none; shadow artifact only`",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## {index}. {row.get('exam_year') or 'unknown'} / {row.get('node_code') or 'unknown'}",
                "",
                f"- rubric_candidate_id: `{row['stable_rubric_candidate_id']}`",
                f"- total_score: `{row.get('total_score')}`",
                f"- point_count: `{row.get('point_count')}`",
                f"- confidence: `{row.get('overall_confidence')}`",
                f"- review_status: `{row.get('review_status')}`",
                "",
                f"题干预览：{row.get('stem_preview')}",
                "",
                "| # | 分值 | 置信度 | 方法 | 采分点 |",
                "|---:|---:|---|---|---|",
            ]
        )
        for point in row.get("scoring_points") or []:
            label = str(point.get("label") or "").replace("|", "\\|")
            lines.append(
                "| {ordinal} | {score} | {confidence} | `{method}` | {label} |".format(
                    ordinal=point.get("ordinal"),
                    score="" if point.get("max_score") is None else point.get("max_score"),
                    confidence=point.get("confidence"),
                    method=point.get("derivation_method"),
                    label=label,
                )
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--source-path", help="Path relative to docs/2026. Recommended for this MVP.")
    parser.add_argument("--limit-files", type=int, default=1)
    parser.add_argument("--limit-candidates", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        source_root = _source_root(args.source_root).resolve()
        run_dir = _run_dir(args.run_id)
        lock = RunDirectoryLock(run_dir, force=args.force)
        lock.prepare()
        compiled_at = utc_now_iso()
        rows: list[dict] = []
        skipped: list[dict] = []
        try:
            for path in _question_paths(source_root, args.source_path, args.limit_files):
                rel = path.relative_to(source_root).as_posix()
                if detect_dataless(path, platform_name="darwin"):
                    skipped.append({"source_path": rel, "reason": "dataless"})
                    continue
                loaded = load_source_payload(path, source_root)
                for record in iter_case_study_answer_records(loaded["payload"], source_path=loaded["source_path"]):
                    candidate = compile_answer_derived_rubric_candidate(
                        record,
                        run_id=args.run_id,
                        source_path=loaded["source_path"],
                        compiled_at=compiled_at,
                    )
                    if candidate:
                        rows.append(candidate)
                    if len(rows) >= args.limit_candidates:
                        break
                if len(rows) >= args.limit_candidates:
                    break

            write_jsonl(run_dir / "answer_rubric_candidates_v2.jsonl", rows)
            write_jsonl(run_dir / "answer_rubric_skipped_sources.jsonl", skipped)
            (run_dir / "answer_rubric_preview.md").write_text(
                _preview_markdown(rows, run_id=args.run_id),
                encoding="utf-8",
            )
            print(
                " ".join(
                    [
                        f"run_dir={run_dir}",
                        f"candidates={len(rows)}",
                        f"skipped={len(skipped)}",
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
