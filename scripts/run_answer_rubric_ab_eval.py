#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from deeptutor.services.source_compiler.answer_rubric_extractor import (
    compile_answer_derived_rubric_candidate,
    iter_case_study_answer_records,
)
from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.metadata import utc_now_iso
from deeptutor.services.source_compiler.platform import RunDirectoryLock, detect_dataless
from deeptutor.services.source_compiler.rubric_evidence_aligner import align_candidate_to_evidence, iter_evidence_records
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


def _question_paths(source_root: Path, source_paths: list[str] | None, limit_files: int | None) -> list[Path]:
    if source_paths:
        return [source_root / source_path for source_path in source_paths]
    paths: list[Path] = []
    for path in sorted(source_root.rglob("*.json")):
        if classify_source(path, source_root) != "question":
            continue
        paths.append(path)
        if limit_files is not None and len(paths) >= limit_files:
            break
    return paths


def _baseline_points(record: dict[str, Any]) -> list[str]:
    points: list[str] = []
    for key in ("grading_keywords", "testing_focus", "structured_rules"):
        value = record.get(key)
        if isinstance(value, list):
            points.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            points.append(value.strip())
    return sorted(set(points))


def _token_proxy(text: str) -> int:
    # Chinese tokenization varies by model; char/2 is conservative enough for A/B proxy.
    return max(1, round(len(text) / 2))


def _candidate_text(candidate: dict[str, Any]) -> str:
    return "\n".join(str(point.get("label") or "") for point in candidate.get("scoring_points") or [])


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


def _collect_rows(
    source_root: Path,
    paths: list[Path],
    *,
    run_id: str,
    compiled_at: str,
    evidence_records: list[dict],
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    skipped: list[dict] = []
    for path in paths:
        rel = path.relative_to(source_root).as_posix()
        if detect_dataless(path, platform_name="darwin"):
            skipped.append({"source_path": rel, "reason": "dataless"})
            continue
        loaded = load_source_payload(path, source_root)
        for record in iter_case_study_answer_records(loaded["payload"], source_path=loaded["source_path"]):
            baseline_points = _baseline_points(record)
            candidate = compile_answer_derived_rubric_candidate(
                record,
                run_id=run_id,
                source_path=loaded["source_path"],
                compiled_at=compiled_at,
            )
            if not candidate:
                continue
            candidate = align_candidate_to_evidence(candidate, evidence_records)
            publishability = candidate.get("publishability") or {}
            alignment_summary = candidate.get("evidence_alignment_summary") or {}
            raw_context = "\n".join(
                [
                    str(record.get("stem") or ""),
                    str(record.get("correct_answer") or ""),
                    str(record.get("analysis") or ""),
                ]
            )
            artifact_context = _candidate_text(candidate)
            rows.append(
                {
                    "stable_rubric_candidate_id": candidate["stable_rubric_candidate_id"],
                    "source_path": loaded["source_path"],
                    "source_chunk_id": record.get("source_chunk_id"),
                    "source_index": record.get("source_index"),
                    "exam_year": record.get("exam_year"),
                    "node_code": record.get("node_code"),
                    "total_score": candidate.get("total_score"),
                    "baseline_point_count": len(baseline_points),
                    "artifact_point_count": candidate.get("point_count") or 0,
                    "artifact_confidence": candidate.get("overall_confidence"),
                    "artifact_warnings": candidate.get("warnings") or [],
                    "artifact_alignment_rate": alignment_summary.get("alignment_rate") or 0,
                    "artifact_publish_gate": publishability.get("gate"),
                    "baseline_has_usable_rubric": len(baseline_points) >= 2,
                    "artifact_has_usable_rubric": (candidate.get("point_count") or 0) >= 2
                    and publishability.get("gate") in {"publishable_candidate", "review_required"},
                    "baseline_token_proxy": _token_proxy(raw_context),
                    "artifact_token_proxy": _token_proxy(artifact_context),
                    "token_reduction_ratio": 1 - (_token_proxy(artifact_context) / _token_proxy(raw_context)),
                }
            )
    return rows, skipped


def _summary(rows: list[dict], skipped: list[dict]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"cases": 0, "skipped_sources": len(skipped)}
    baseline_usable = sum(1 for row in rows if row["baseline_has_usable_rubric"])
    artifact_usable = sum(1 for row in rows if row["artifact_has_usable_rubric"])
    baseline_tokens = sum(row["baseline_token_proxy"] for row in rows)
    artifact_tokens = sum(row["artifact_token_proxy"] for row in rows)
    return {
        "cases": n,
        "skipped_sources": len(skipped),
        "baseline_usable_cases": baseline_usable,
        "artifact_usable_cases": artifact_usable,
        "baseline_usable_rate": round(baseline_usable / n, 4),
        "artifact_usable_rate": round(artifact_usable / n, 4),
        "baseline_points_total": sum(row["baseline_point_count"] for row in rows),
        "artifact_points_total": sum(row["artifact_point_count"] for row in rows),
        "baseline_token_proxy_total": baseline_tokens,
        "artifact_token_proxy_total": artifact_tokens,
        "token_reduction_proxy": round(1 - (artifact_tokens / baseline_tokens), 4) if baseline_tokens else None,
        "low_confidence_cases": sum(1 for row in rows if str(row["artifact_confidence"]).startswith("C")),
        "publishable_candidates": sum(1 for row in rows if row.get("artifact_publish_gate") == "publishable_candidate"),
        "review_required_candidates": sum(1 for row in rows if row.get("artifact_publish_gate") == "review_required"),
        "blocked_candidates": sum(1 for row in rows if row.get("artifact_publish_gate") == "blocked"),
        "missing_score_cases": sum(
            1
            for row in rows
            if "total_score_missing" in row.get("artifact_warnings", [])
            or "point_score_missing" in row.get("artifact_warnings", [])
        ),
    }


def _markdown(summary: dict[str, Any], rows: list[dict], *, run_id: str) -> str:
    lines = [
        "# Answer Rubric A/B Evaluation",
        "",
        f"- run_id: `{run_id}`",
        "- A: existing source signals (`grading_keywords/testing_focus/structured_rules`)",
        "- B: answer-derived rubric artifacts + evidence alignment + publish gate",
        "- writeback: `none; read-only offline eval`",
        "",
        "## Summary",
        "",
        "| Metric | A Baseline | B Artifact-first |",
        "|---|---:|---:|",
        f"| usable cases | {summary.get('baseline_usable_cases', 0)} | {summary.get('artifact_usable_cases', 0)} |",
        f"| usable rate | {summary.get('baseline_usable_rate', 0):.1%} | {summary.get('artifact_usable_rate', 0):.1%} |",
        f"| total points | {summary.get('baseline_points_total', 0)} | {summary.get('artifact_points_total', 0)} |",
        f"| token proxy total | {summary.get('baseline_token_proxy_total', 0)} | {summary.get('artifact_token_proxy_total', 0)} |",
        f"| token reduction proxy | - | {summary.get('token_reduction_proxy', 0):.1%} |",
        "",
        f"- low_confidence_cases: `{summary.get('low_confidence_cases', 0)}`",
        f"- missing_score_cases: `{summary.get('missing_score_cases', 0)}`",
        f"- publishable_candidates: `{summary.get('publishable_candidates', 0)}`",
        f"- review_required_candidates: `{summary.get('review_required_candidates', 0)}`",
        f"- blocked_candidates: `{summary.get('blocked_candidates', 0)}`",
        "",
        "## Per Case",
        "",
        "| # | year | node | A pts | B pts | B conf | evidence | gate | token reduction | warnings |",
        "|---:|---|---|---:|---:|---|---:|---|---:|---|",
    ]
    for index, row in enumerate(rows, start=1):
        warnings = ", ".join(row.get("artifact_warnings") or [])
        lines.append(
            "| {idx} | {year} | {node} | {a} | {b} | {conf} | {evidence:.1%} | {gate} | {red:.1%} | {warnings} |".format(
                idx=index,
                year=row.get("exam_year") or "",
                node=row.get("node_code") or "",
                a=row.get("baseline_point_count", 0),
                b=row.get("artifact_point_count", 0),
                conf=row.get("artifact_confidence") or "",
                evidence=row.get("artifact_alignment_rate") or 0,
                gate=row.get("artifact_publish_gate") or "",
                red=row.get("token_reduction_ratio") or 0,
                warnings=warnings.replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--source-path", action="append", default=[])
    parser.add_argument("--evidence-path", action="append", default=[])
    parser.add_argument("--limit-files", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        source_root = _source_root(args.source_root).resolve()
        run_dir = _run_dir(args.run_id)
        lock = RunDirectoryLock(run_dir, force=args.force)
        lock.prepare()
        compiled_at = utc_now_iso()
        try:
            evidence_records, skipped_evidence = _load_evidence(source_root, args.evidence_path or DEFAULT_EVIDENCE_PATHS)
            rows, skipped = _collect_rows(
                source_root,
                _question_paths(source_root, args.source_path, args.limit_files),
                run_id=args.run_id,
                compiled_at=compiled_at,
                evidence_records=evidence_records,
            )
            skipped.extend(skipped_evidence)
            summary = _summary(rows, skipped)
            write_jsonl(run_dir / "answer_rubric_ab_eval_rows.jsonl", rows)
            write_jsonl(run_dir / "answer_rubric_ab_eval_skipped.jsonl", skipped)
            (run_dir / "answer_rubric_ab_eval_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (run_dir / "answer_rubric_ab_eval.md").write_text(
                _markdown(summary, rows, run_id=args.run_id),
                encoding="utf-8",
            )
            print(
                " ".join(
                    [
                        f"run_dir={run_dir}",
                        f"cases={summary.get('cases', 0)}",
                        f"baseline_usable={summary.get('baseline_usable_cases', 0)}",
                        f"artifact_usable={summary.get('artifact_usable_cases', 0)}",
                        f"token_reduction_proxy={summary.get('token_reduction_proxy')}",
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
