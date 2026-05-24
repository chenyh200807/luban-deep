from __future__ import annotations

from .metadata import with_compiler_metadata
from .schema import content_hash, stable_hash
from .standard_compiler import normalize_standard_code


def compile_lecture_card(record: dict, *, run_id: str, source_path: str, compiled_at: str) -> dict:
    node_code = str(record.get("node_code") or "")
    title = str(record.get("title") or record.get("page_title") or node_code)
    content = str(record.get("content_markdown") or record.get("rag_content") or record.get("content") or "")
    stable_seed = f"{source_path}|{node_code}|{title}"
    refs = [
        normalize_standard_code(value)
        for value in (record.get("candidate_standard_refs") or record.get("standard_refs") or [])
    ]
    payload = {
        "stable_lecture_card_id": stable_hash(stable_seed, prefix="lect_"),
        "node_code": node_code,
        "title": title,
        "summary": record.get("summary") or content[:240],
        "key_parameters": record.get("key_parameters") or [],
        "structured_rules": record.get("structured_rules") or [],
        "figures": record.get("figures") or [],
        "tables": record.get("tables") or [],
        "candidate_standard_refs": refs,
        "content_hash": content_hash(content),
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)
