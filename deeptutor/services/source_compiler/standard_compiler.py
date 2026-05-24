from __future__ import annotations

import re
from typing import Any

from .metadata import with_compiler_metadata
from .schema import content_hash, stable_hash


def normalize_standard_code(value: object) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("／", "/").replace("＋", "+").replace(" ", "")
    text = text.replace("+", "")
    text = text.replace("GBT", "GB/T")
    text = re.sub(r"GB/T(?=\d)", "GB/T", text)
    return text


def _standard_code(record: dict) -> str:
    source_context = record.get("source_context") if isinstance(record.get("source_context"), dict) else {}
    return normalize_standard_code(
        source_context.get("standard_code")
        or record.get("standard_code")
        or record.get("display_standard_code")
        or record.get("code")
    )


def compile_standard_clause(record: dict, *, run_id: str, source_path: str, compiled_at: str) -> dict[str, Any]:
    normalized = _standard_code(record)
    source_context = record.get("source_context") if isinstance(record.get("source_context"), dict) else {}
    raw_source_record_id = str(
        record.get("source_record_id")
        or record.get("id")
        or record.get("chunk_id")
        or f"row_{record.get('_source_index', 'unknown')}"
    )
    source_record_id = f"{source_path}:{raw_source_record_id}"
    if "_source_index" in record:
        source_record_id = f"{source_record_id}:row_{record['_source_index']}"
    article_code = str(
        record.get("article_code") or source_context.get("article_id") or record.get("article_id") or record.get("clause") or "unknown"
    )
    ref_level = str(record.get("ref_level") or ("chapter" if article_code.count(".") <= 1 else "clause"))
    content = str(record.get("content") or source_context.get("origin_text") or record.get("text") or record.get("title") or "")
    stable_seed = f"{normalized}|{article_code}|{source_record_id}|{ref_level}"
    payload = {
        "stable_clause_id": stable_hash(stable_seed, prefix="std_"),
        "source_record_id": source_record_id,
        "normalized_standard_code": normalized,
        "display_standard_code": record.get("display_standard_code") or record.get("standard_code") or normalized,
        "article_code": article_code,
        "ref_level": ref_level,
        "chapter": record.get("chapter"),
        "chapter_name": record.get("chapter_name"),
        "content": content,
        "content_hash": content_hash(content),
        "taxonomy_node_codes": record.get("taxonomy_node_codes") or [],
        "logic_constraints": record.get("logic_constraints") or [],
        "common_violations": record.get("common_violations") or [],
        "synthetic_qa": record.get("synthetic_qa") or [],
        "graph_relations": record.get("graph_relations") or [],
        "lifecycle_status": record.get("lifecycle_status") or "unknown",
        "superseded_by": record.get("superseded_by"),
        "source_context": record.get("source_context") or {},
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)
