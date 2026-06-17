#!/usr/bin/env python3
"""Find review-only source evidence candidates for weak RichLeaf work orders."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_luban_rich_leaf_source_gap_candidates import load_source_records_from_root

DEFAULT_WEAK_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_weak_source_refinement_20260611/weak_source_refinement_work_orders.json"
)
DEFAULT_DOCS_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_source_evidence_agent_20260612"
SCHEMA = "luban_rich_leaf_source_evidence_agent.v1"
SUPPORTED_SUFFIXES = {".json", ".md", ".txt"}


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


def _source_lane(path: Path) -> str:
    parts = set(path.parts)
    text = str(path)
    if "2026教材" in parts:
        return "textbook"
    if "标准文件" in parts:
        return "standard"
    if "讲义" in parts:
        return "lecture"
    if "题库" in parts:
        return "question"
    if any(marker in text for marker in ("真题", "答案解析", "章节千题", "考证宝典")):
        return "question"
    return "residual"


def _iter_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_text_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_values(item)


def _record_id(path: Path, item: Any, index: int) -> str:
    if isinstance(item, dict):
        for key in ("record_id", "id", "source_id", "chunk_id", "clause_id", "question_id"):
            value = item.get(key)
            if value:
                return str(value)
    return f"{path.stem}:{index}"


def _records_from_file(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    lane = _source_lane(path)
    if path.suffix == ".json":
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = payload if isinstance(payload, list) else [payload]
        records: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            text = _normalize_text(" ".join(_iter_text_values(item)))
            if text:
                records.append({"source_lane": lane, "path": str(path), "record_id": _record_id(path, item, index), "text": text})
        return records

    text = _normalize_text(raw)
    return [{"source_lane": lane, "path": str(path), "record_id": path.stem, "text": text}] if text else []


def _source_records(docs_root: Path, max_files: int) -> list[dict[str, Any]]:
    records = load_source_records_from_root(docs_root)
    return [
        {
            "source_lane": record.source_lane,
            "path": record.source_path,
            "source_path": record.source_path,
            "record_id": record.record_id,
            "text": record.text,
            "span": record.span,
            "span_hash": record.span_hash,
            "retrieval_stage": record.retrieval_stage,
            "provenance": record.provenance,
        }
        for record in records
    ]


def _score_record(record: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    text = str(record.get("text") or "")
    matched = [term for term in terms if term and term in text]
    if not matched:
        return 0.0, []
    # Prefer exact multi-term support, but keep this deterministic and review-only.
    score = float(len(matched)) + min(len("".join(matched)) / 100.0, 1.0)
    return round(score, 4), matched


def _span(text: str, matched_terms: list[str], max_len: int = 240) -> str:
    first = min((text.find(term) for term in matched_terms if term in text), default=0)
    start = max(first - 80, 0)
    return text[start : start + max_len].strip()


def _candidate(record: dict[str, Any], terms: list[str], *, support_candidate: bool) -> dict[str, Any] | None:
    score, matched_terms = _score_record(record, terms)
    if score <= 0:
        return None
    span = str(record.get("span") or _span(str(record.get("text") or ""), matched_terms))
    span_hash = str(record.get("span_hash") or _hash_text(span))
    return {
        "source_lane": record.get("source_lane"),
        "source_path": record.get("source_path") or record.get("path"),
        "record_id": record.get("record_id"),
        "score": score,
        "matched_terms": matched_terms,
        "span": span,
        "span_hash": span_hash,
        "support_candidate": support_candidate,
        "candidate_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
    }


def _top_candidates(
    records: list[dict[str, Any]],
    *,
    terms: list[str],
    lane: str,
    support_candidate: bool,
    top_k: int,
) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for record in records
        if record.get("source_lane") == lane
        for candidate in [_candidate(record, terms, support_candidate=support_candidate)]
        if candidate is not None
    ]
    return sorted(candidates, key=lambda item: (-float(item["score"]), str(item["record_id"])))[:top_k]


def _lane_orders(weak_work_orders: dict[str, Any]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for leaf in weak_work_orders.get("leaf_work_orders") or []:
        if not isinstance(leaf, dict):
            continue
        for lane_order in leaf.get("lane_work_orders") or []:
            if not isinstance(lane_order, dict):
                continue
            orders.append(
                {
                    "leaf_id": leaf.get("leaf_id"),
                    "artifact_id": leaf.get("artifact_id"),
                    "name_path": leaf.get("name_path"),
                    "missing_lane": lane_order.get("missing_lane"),
                    "source_gap_status": lane_order.get("status"),
                    "terms": list(lane_order.get("terms") or []),
                    "promotion_allowed": False,
                    "runtime_install_allowed": False,
                }
            )
    return orders


def _work_order_result(order: dict[str, Any], records: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    terms = [str(term) for term in order.get("terms") or [] if str(term).strip()]
    missing_lane = str(order.get("missing_lane") or "")
    support_candidates = _top_candidates(records, terms=terms, lane=missing_lane, support_candidate=True, top_k=top_k)
    question_context = []
    if not support_candidates:
        question_context = _top_candidates(records, terms=terms, lane="question", support_candidate=False, top_k=top_k)
    return {
        **order,
        "status": "source_candidates_found" if support_candidates else "no_lane_matched_source_candidate",
        "candidate_sources": support_candidates,
        "question_context_candidates": question_context,
        "review_status": "source_evidence_review_pending",
        "candidate_only": True,
        "review_only": True,
        "promotion_allowed": False,
        "runtime_install_allowed": False,
    }


def build_source_evidence_agent_report(
    *,
    weak_work_orders: dict[str, Any],
    docs_root: Path,
    max_files: int = 5000,
    top_k: int = 3,
) -> dict[str, Any]:
    records = _source_records(docs_root, max_files=max_files)
    results = [_work_order_result(order, records, top_k=top_k) for order in _lane_orders(weak_work_orders)]
    candidate_count = sum(len(row["candidate_sources"]) for row in results)
    question_context_candidate_count = sum(len(row["question_context_candidates"]) for row in results)
    lane_counts: dict[str, int] = {}
    for record in records:
        lane = str(record.get("source_lane") or "unknown")
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
    return {
        "schema": SCHEMA,
        "weak_work_order_schema": weak_work_orders.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "semantic_verdict_recorded": False,
            "runtime_install_allowed": False,
        },
        "source_corpus": {
            "docs_root": str(docs_root),
            "max_files": max_files,
            "record_count": len(records),
            "record_count_by_lane": dict(sorted(lane_counts.items())),
        },
        "summary": {
            "work_order_count": len(results),
            "work_orders_with_candidates": sum(1 for row in results if row["candidate_sources"]),
            "work_orders_without_lane_matched_candidates": sum(1 for row in results if not row["candidate_sources"]),
            "candidate_count": candidate_count,
            "question_context_candidate_count": question_context_candidate_count,
        },
        "source_evidence_work_orders": results,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak-work-orders", type=Path, default=DEFAULT_WEAK_WORK_ORDERS)
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(argv)

    weak_work_orders = _read_json(args.weak_work_orders)
    report = build_source_evidence_agent_report(
        weak_work_orders=weak_work_orders,
        docs_root=args.docs_root,
        max_files=args.max_files,
        top_k=args.top_k,
    )
    output_path = args.output_dir / "source_evidence_agent_candidates.json"
    _write_json(output_path, report)
    print(json.dumps({"out": str(output_path), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
