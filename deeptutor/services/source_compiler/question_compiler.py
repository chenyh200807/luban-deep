from __future__ import annotations

import hashlib
import re
from typing import Any

from .metadata import with_compiler_metadata
from .schema import content_hash, normalize_text, stable_hash
from .standard_compiler import normalize_standard_code


def _coerce_answer_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value if item is not None]
    else:
        items = [str(value)]
    return sorted({item.strip() for item in items if item.strip()})


def _semantic_text(stem: str, options: object) -> str:
    return re.sub(r"\s+", "", normalize_text(stem) + "|" + str(options))


def compile_question_capsule(record: dict, *, run_id: str, source_path: str, compiled_at: str) -> dict[str, Any]:
    source_chunk_id = str(record.get("source_chunk_id") or record.get("chunk_id") or "")
    original_id = str(record.get("original_id") or record.get("id") or source_chunk_id)
    stem = str(record.get("stem") or record.get("question") or record.get("content") or "")
    options = record.get("options") or {}
    correct_answer = _coerce_answer_list(record.get("correct_answer") or record.get("answer"))
    stable_seed = f"{source_path}|{source_chunk_id}|{original_id}"
    semantic_signature = hashlib.sha256(_semantic_text(stem, options).encode("utf-8")).hexdigest()
    standard_refs = [
        normalize_standard_code(value)
        for value in (record.get("candidate_standard_refs") or record.get("cited_standard_codes") or [])
    ]
    payload = {
        "stable_question_source_id": stable_hash(stable_seed, prefix="qsrc_"),
        "source_chunk_id": source_chunk_id,
        "candidate_questions_bank_id": record.get("candidate_questions_bank_id"),
        "original_id": original_id,
        "exam_year": record.get("exam_year") or record.get("year"),
        "question_type": record.get("question_type") or record.get("type") or "unknown",
        "node_code": record.get("node_code") or record.get("predicted_node"),
        "stem": stem,
        "options": options,
        "correct_answer": correct_answer,
        "analysis": record.get("analysis") or record.get("explanation"),
        "option_reasoning": record.get("option_reasoning") or {},
        "pitfalls": record.get("pitfalls") or [],
        "testing_focus": record.get("testing_focus") or [],
        "candidate_standard_refs": standard_refs,
        "content_hash": content_hash({"stem": stem, "options": options, "correct_answer": correct_answer}),
        "semantic_signature": semantic_signature,
        "writeback_policy": record.get("writeback_policy") or "overwrite_only_if_empty",
    }
    return with_compiler_metadata(payload, run_id=run_id, source_path=source_path, compiled_at=compiled_at)

