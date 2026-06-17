#!/usr/bin/env python3
"""Review-only closure search for RichLeaf needs_external_source records."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_root


DEFAULT_SEMANTIC_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612/semantic_evidence_audit_record.json"
)
DEFAULT_DOCS_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_external_source_closure_20260612"
SCHEMA = "luban_rich_leaf_external_source_closure.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(_normalize_text(value).encode("utf-8")).hexdigest()


def _records(docs_root: Path) -> list[dict[str, Any]]:
    records = []
    for record in load_source_records_from_root(docs_root):
        records.append(
            {
                "source_lane": record.source_lane,
                "source_path": record.source_path,
                "record_id": record.record_id,
                "text": record.text,
                "span": record.span,
                "span_hash": record.span_hash,
                "retrieval_stage": record.retrieval_stage,
                "provenance": record.provenance,
            }
        )
    return records


def _terms(record: dict[str, Any]) -> list[str]:
    terms = [str(term).strip() for term in record.get("terms") or [] if str(term).strip()]
    if terms:
        return terms
    leaf_id = str(record.get("leaf_id") or "").strip()
    return [leaf_id] if leaf_id else []


def _score_record(record: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    text = str(record.get("text") or "")
    matched = [term for term in terms if term and term in text]
    if not matched:
        return 0.0, []
    return round(float(len(matched)) + min(len("".join(matched)) / 100.0, 1.0), 4), matched


def _span(text: str, matched_terms: list[str], max_len: int = 240) -> str:
    first = min((text.find(term) for term in matched_terms if term in text), default=0)
    start = max(first - 80, 0)
    return text[start : start + max_len].strip()


def _candidate(record: dict[str, Any], terms: list[str], *, support_candidate: bool) -> dict[str, Any] | None:
    score, matched_terms = _score_record(record, terms)
    if score <= 0:
        return None
    span = str(record.get("span") or _span(str(record.get("text") or ""), matched_terms))
    return {
        "source_lane": record.get("source_lane"),
        "source_path": record.get("source_path"),
        "record_id": record.get("record_id"),
        "score": score,
        "matched_terms": matched_terms,
        "span": span,
        "span_hash": str(record.get("span_hash") or _hash_text(span)),
        "support_candidate": support_candidate,
        "candidate_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
    }


def _top_candidates(
    records: list[dict[str, Any]], *, terms: list[str], lane: str, support_candidate: bool, top_k: int
) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for record in records
        if record.get("source_lane") == lane
        for candidate in [_candidate(record, terms, support_candidate=support_candidate)]
        if candidate is not None
    ]
    return sorted(candidates, key=lambda item: (-float(item["score"]), str(item["record_id"])))[:top_k]


def _needs_external_source_records(semantic_record: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in semantic_record.get("semantic_evidence_audit_records") or []:
        if isinstance(item, dict) and item.get("decision") == "needs_external_source":
            records.append(item)
    return records


def _closure(record: dict[str, Any], source_records: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    terms = _terms(record)
    missing_lane = str(record.get("missing_lane") or record.get("lane") or "")
    support_candidates = _top_candidates(
        source_records, terms=terms, lane=missing_lane, support_candidate=True, top_k=top_k
    )
    question_context = [] if support_candidates else _top_candidates(
        source_records, terms=terms, lane="question", support_candidate=False, top_k=top_k
    )
    return {
        "audit_item_id": record.get("audit_item_id"),
        "leaf_id": record.get("leaf_id"),
        "artifact_id": record.get("artifact_id"),
        "field": record.get("field"),
        "missing_lane": missing_lane,
        "terms": terms,
        "status": "candidate_sources_found" if support_candidates else "external_source_required",
        "candidate_sources": support_candidates,
        "question_context_candidates": question_context,
        "candidate_only": True,
        "review_only": True,
        "source_truth_claimed": False,
        "promotion_allowed": False,
        "runtime_install_allowed": False,
    }


def build_external_source_closure_report(
    *, semantic_record: dict[str, Any], docs_root: Path, top_k: int = 3
) -> dict[str, Any]:
    source_records = _records(docs_root)
    closures = [_closure(record, source_records, top_k) for record in _needs_external_source_records(semantic_record)]
    lane_counts: dict[str, int] = {}
    for record in source_records:
        lane = str(record.get("source_lane") or "unknown")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    candidate_count = sum(len(row["candidate_sources"]) for row in closures)
    question_context_count = sum(len(row["question_context_candidates"]) for row in closures)
    external_required_count = sum(1 for row in closures if not row["candidate_sources"])
    return {
        "schema": SCHEMA,
        "input_schemas": {
            "semantic_evidence_audit_record": semantic_record.get("schema"),
        },
        "verdict": "PASS",
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "external_source_closure": True,
            "source_truth_claimed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "source_corpus": {
            "docs_root": str(docs_root),
            "record_count": len(source_records),
            "record_count_by_lane": dict(sorted(lane_counts.items())),
        },
        "summary": {
            "needs_external_source_count": len(closures),
            "closures_with_candidates": sum(1 for row in closures if row["candidate_sources"]),
            "external_source_required_count": external_required_count,
            "closure_candidate_count": candidate_count,
            "question_context_candidate_count": question_context_count,
            "source_truth_write_count": 0,
            "runtime_install_count": 0,
            "blocker_count": 0,
        },
        "external_source_closures": closures,
        "not_exercised": [
            "source_truth_promotion",
            "source_ref_mutation",
            "runtime_install",
            "production_default",
            "release_truth_claim",
        ],
        "safety": {
            "canonical_truth_written": False,
            "source_truth_write_count": 0,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-record", type=Path, default=DEFAULT_SEMANTIC_RECORD)
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    report = build_external_source_closure_report(
        semantic_record=_read_json(args.semantic_record),
        docs_root=args.docs_root,
        top_k=args.top_k,
    )
    _write_json(args.output_dir / "external_source_closure.json", report)
    print(
        json.dumps(
            {
                "out": str(args.output_dir / "external_source_closure.json"),
                "summary": report["summary"],
                "verdict": report["verdict"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
