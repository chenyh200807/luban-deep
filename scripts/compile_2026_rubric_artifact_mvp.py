#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
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
from deeptutor.services.source_compiler.rubric_evidence_aligner import (
    align_candidate_to_evidence,
    build_quality_report,
    build_review_rows,
    iter_evidence_records,
)
from deeptutor.services.source_compiler.source_inventory import classify_source
from deeptutor.services.source_compiler.source_reader import load_source_payload


DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_EVIDENCE_PATHS = [
    "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
    "2026教材/第二次加强/v3_production_enrichment_v2-9-166.json",
    "标准文件/18、GB+50207-2012屋面工程质量验收规范（清晰版）.json",
    "讲义/2025.6.21佑森教育闫力齐授课一建建筑实务《防水&节能&装修工程》专用讲义，版权所有，侵权必究_v8/2025.6.21佑森教育闫力齐授课一建建筑实务《防水&节能&装修工程》专用讲义，版权所有，侵权必究_v8.json",
]


def _source_root(value: str | None) -> Path:
    if value:
        return Path(value)
    env_value = os.environ.get("LUBAN_2026_SOURCE_ROOT")
    if env_value:
        return Path(env_value)
    return DEFAULT_SOURCE_ROOT


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def _markdown_quality(report: dict, rows: list[dict], *, run_id: str) -> str:
    lines = [
        "# Rubric Artifact MVP Quality Report",
        "",
        f"- run_id: `{run_id}`",
        "- writeback: `none; shadow artifacts only`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in report.items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Review Checklist",
            "",
            "| # | candidate | point | score | confidence | evidence | gate | label |",
            "|---:|---|---|---:|---|---:|---|---|",
        ]
    )
    for index, row in enumerate(rows, start=1):
        label = str(row.get("label") or "").replace("|", "\\|")
        lines.append(
            "| {idx} | `{candidate}` | `{point}` | {score} | {confidence} | {evidence} | {gate} | {label} |".format(
                idx=index,
                candidate=row.get("stable_rubric_candidate_id"),
                point=row.get("point_id"),
                score="" if row.get("max_score") is None else row.get("max_score"),
                confidence=row.get("confidence"),
                evidence="yes" if row.get("evidence_aligned") else "no",
                gate=row.get("publish_gate"),
                label=label,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _load_evidence(source_root: Path, evidence_paths: list[str]) -> tuple[list[dict], list[dict]]:
    evidence: list[dict] = []
    skipped: list[dict] = []
    for rel in evidence_paths:
        path = source_root / rel
        if not path.exists():
            skipped.append({"source_path": rel, "reason": "missing"})
            continue
        if detect_dataless(path, platform_name="darwin"):
            skipped.append({"source_path": rel, "reason": "dataless"})
            continue
        loaded = load_source_payload(path, source_root)
        evidence.extend(
            iter_evidence_records(
                loaded["payload"],
                source_path=loaded["source_path"],
                source_class=loaded["source_class"],
            )
        )
    return evidence, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--question-source-path", action="append", required=True)
    parser.add_argument("--evidence-path", action="append", default=[])
    parser.add_argument("--limit-candidates", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        source_root = _source_root(args.source_root).resolve()
        run_dir = _run_dir(args.run_id)
        lock = RunDirectoryLock(run_dir, force=args.force)
        lock.prepare()
        compiled_at = utc_now_iso()
        try:
            evidence, skipped_evidence = _load_evidence(source_root, args.evidence_path or DEFAULT_EVIDENCE_PATHS)

            candidates: list[dict] = []
            for rel_question_path in args.question_source_path:
                question_path = source_root / rel_question_path
                if classify_source(question_path, source_root) != "question":
                    raise ValueError("--question-source-path must point to a question JSON file")
                if detect_dataless(question_path, platform_name="darwin"):
                    raise RuntimeError(f"question source is dataless: {rel_question_path}")
                loaded_questions = load_source_payload(question_path, source_root)
                for record in iter_case_study_answer_records(
                    loaded_questions["payload"],
                    source_path=loaded_questions["source_path"],
                ):
                    candidate = compile_answer_derived_rubric_candidate(
                        record,
                        run_id=args.run_id,
                        source_path=loaded_questions["source_path"],
                        compiled_at=compiled_at,
                    )
                    if candidate:
                        candidates.append(align_candidate_to_evidence(candidate, evidence))
                    if len(candidates) >= args.limit_candidates:
                        break
                if len(candidates) >= args.limit_candidates:
                    break

            review_rows = build_review_rows(candidates)
            report = build_quality_report(candidates, evidence_count=len(evidence))
            report["skipped_evidence_sources"] = len(skipped_evidence)

            write_jsonl(run_dir / "rubric_artifact_candidates.jsonl", candidates)
            write_jsonl(run_dir / "rubric_review_checklist.jsonl", review_rows)
            write_jsonl(run_dir / "rubric_evidence_skipped_sources.jsonl", skipped_evidence)
            (run_dir / "rubric_quality_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (run_dir / "rubric_quality_report.md").write_text(
                _markdown_quality(report, review_rows, run_id=args.run_id),
                encoding="utf-8",
            )
            print(
                " ".join(
                    [
                        f"run_dir={run_dir}",
                        f"candidates={report['candidates']}",
                        f"points={report['points']}",
                        f"alignment_rate={report['point_alignment_rate']}",
                        f"publishable={report['publishable_candidates']}",
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
