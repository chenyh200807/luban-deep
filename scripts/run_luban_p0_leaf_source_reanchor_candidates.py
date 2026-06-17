#!/usr/bin/env python3
"""Compile source re-anchor candidates for P0 unified-knowledge leaf gaps.

This is a read-only compiler workbench. It searches source documents for
evidence candidates for leaves that have assessment/question evidence but no
compiled teaching context. It does not mutate canonical_unified_knowledge.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(
    os.getenv(
        "LUBAN_DATA_DIR",
        "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026",
    )
)
DEFAULT_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/unified_knowledge_leaf_coverage_work_orders_20260611/leaf_coverage_work_orders.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/p0_leaf_source_reanchor_candidates_20260611"
KNOWLEDGE_PATTERNS = (
    "2026教材/第二次加强/*fixed.json",
    "标准文件/*.json",
    "讲义/**/*.json",
)
TEXT_KEYS = ("content_markdown", "markdown", "text", "clause_text", "body", "title", "heading")


@dataclass(frozen=True)
class SourceRecord:
    source_lane: str
    source_path: str
    record_id: str
    text: str
    provenance: dict[str, Any]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_lane(path: Path) -> str:
    parts = set(path.parts)
    if "2026教材" in parts:
        return "textbook"
    if "标准文件" in parts:
        return "standard"
    if "讲义" in parts:
        return "lecture"
    return "unknown"


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _record_text(row: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str):
            chunks.append(value)
    meta = row.get("meta_info") or row.get("taxonomy") or {}
    if isinstance(meta, dict):
        for key in ("core_entity", "taxonomy_path", "node_name", "topic"):
            value = meta.get(key)
            if isinstance(value, str):
                chunks.append(value)
    return "\n".join(part.strip() for part in chunks if part and part.strip())


def _record_id(row: dict[str, Any], fallback: str) -> str:
    for key in ("chunk_id", "node_id", "id", "unit_id", "clause_id"):
        value = row.get(key)
        if value:
            return str(value)
    return fallback


def load_source_records(source_root: Path) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for pattern in KNOWLEDGE_PATTERNS:
        for path in sorted(source_root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                payload = _read_json(path)
            except (json.JSONDecodeError, OSError):
                continue
            lane = _source_lane(path)
            rel_path = str(path.relative_to(source_root))
            seen: set[str] = set()
            for idx, row in enumerate(_walk_dicts(payload)):
                text = _record_text(row)
                if len(text) < 20:
                    continue
                record_id = _record_id(row, f"{rel_path}#{idx}")
                dedupe_key = f"{rel_path}:{record_id}:{text[:80]}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                provenance = {}
                for key in ("source_meta", "meta_info", "taxonomy", "document_meta"):
                    value = row.get(key)
                    if isinstance(value, dict):
                        provenance[key] = value
                records.append(
                    SourceRecord(
                        source_lane=lane,
                        source_path=rel_path,
                        record_id=record_id,
                        text=text,
                        provenance=provenance,
                    )
                )
    return records


def _terms_for_order(order: dict[str, Any]) -> list[str]:
    raw_terms: list[str] = []
    raw_terms.extend(str(term) for term in order.get("keywords") or [] if term)
    leaf_path = str(order.get("leaf_path") or order.get("name_path") or "")
    raw_terms.extend(part.strip() for part in re.split(r"[>\s/、，,（）()：:]+", leaf_path) if part.strip())
    code = str(order.get("leaf_id") or order.get("node_code") or "")
    if code:
        raw_terms.append(code.split("-")[0])

    out: list[str] = []
    seen: set[str] = set()
    stop_terms = {"建筑工程技术", "建筑工程", "建筑", "施工", "工程", "技术", "要求", "管理", "应用"}
    for term in raw_terms:
        normalized = term.strip()
        if len(normalized) < 2 or normalized in stop_terms:
            continue
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out[:16]


def _snippet(text: str, matched_terms: list[str], max_len: int = 360) -> str:
    first_hit = min((text.find(term) for term in matched_terms if term in text), default=-1)
    if first_hit < 0:
        start = 0
    else:
        start = max(0, first_hit - 80)
    snippet = text[start : start + max_len].replace("\n", " ").strip()
    return re.sub(r"\s+", " ", snippet)


def _score_record(record: SourceRecord, terms: list[str]) -> tuple[float, list[str]]:
    matched = [term for term in terms if term in record.text]
    if not matched:
        return 0.0, []
    long_bonus = sum(min(len(term), 8) for term in matched) / 24
    lane_bonus = {"textbook": 0.25, "standard": 0.2, "lecture": 0.1}.get(record.source_lane, 0.0)
    return round(len(matched) + long_bonus + lane_bonus, 4), matched


def build_reanchor_candidates(
    *,
    work_order_report: dict[str, Any],
    source_records: list[SourceRecord],
    max_work_orders: int = 57,
    top_k_per_leaf: int = 5,
    strong_candidate_threshold: float = 2.0,
) -> dict[str, Any]:
    p0_orders = [
        order
        for order in work_order_report.get("work_orders") or []
        if order.get("priority") == "P0" and (order.get("gap_type") or order.get("category")) == "question_without_knowledge"
    ][:max_work_orders]

    rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for order in p0_orders:
        terms = _terms_for_order(order)
        scored: list[tuple[float, SourceRecord, list[str]]] = []
        for record in source_records:
            score, matched = _score_record(record, terms)
            if score > 0:
                scored.append((score, record, matched))
        scored.sort(key=lambda item: (-item[0], item[1].source_lane, item[1].source_path, item[1].record_id))
        candidates = [
            {
                "source_lane": record.source_lane,
                "source_path": record.source_path,
                "record_id": record.record_id,
                "score": score,
                "matched_terms": matched,
                "snippet": _snippet(record.text, matched),
                "provenance": record.provenance,
                "candidate_only": True,
            }
            for score, record, matched in scored[:top_k_per_leaf]
        ]
        leaf_id = str(order.get("leaf_id") or order.get("node_code"))
        top_score = float(candidates[0]["score"]) if candidates else 0.0
        review_status = (
            "strong_candidate_sources_found"
            if top_score >= strong_candidate_threshold
            else "weak_candidate_sources_found"
            if candidates
            else "no_candidate_found"
        )
        if not candidates:
            unresolved.append(leaf_id)
        rows.append(
            {
                "work_order_id": order.get("work_order_id"),
                "leaf_id": leaf_id,
                "leaf_path": order.get("leaf_path") or order.get("name_path"),
                "terms": terms,
                "candidate_count": len(candidates),
                "top_score": top_score,
                "strong_candidate_threshold": strong_candidate_threshold,
                "status": review_status,
                "candidates": candidates,
            }
        )

    strong_count = sum(1 for row in rows if row["status"] == "strong_candidate_sources_found")
    weak_count = sum(1 for row in rows if row["status"] == "weak_candidate_sources_found")
    return {
        "schema": "luban_p0_leaf_source_reanchor_candidates.v1",
        "source_work_order_schema": work_order_report.get("schema"),
        "source_bundle_content_hash": work_order_report.get("source_bundle_content_hash"),
        "summary": {
            "p0_work_orders_input": len(p0_orders),
            "source_record_count": len(source_records),
            "leaves_with_candidates": sum(1 for row in rows if row["candidate_count"] > 0),
            "leaves_with_strong_candidates": strong_count,
            "leaves_with_weak_candidates_only": weak_count,
            "leaves_without_candidates": len(unresolved),
            "candidate_total": sum(int(row["candidate_count"]) for row in rows),
            "strong_candidate_threshold": strong_candidate_threshold,
        },
        "unresolved_leaf_ids": unresolved,
        "reanchor_candidates": rows,
        "safety": {
            "candidate_only": True,
            "read_only_source_scan": True,
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--work-orders", type=Path, default=DEFAULT_WORK_ORDERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-work-orders", type=int, default=57)
    parser.add_argument("--top-k-per-leaf", type=int, default=5)
    parser.add_argument("--strong-candidate-threshold", type=float, default=2.0)
    args = parser.parse_args(argv)

    report = build_reanchor_candidates(
        work_order_report=_read_json(args.work_orders),
        source_records=load_source_records(args.source_root),
        max_work_orders=args.max_work_orders,
        top_k_per_leaf=args.top_k_per_leaf,
        strong_candidate_threshold=args.strong_candidate_threshold,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "reanchor_candidates.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
