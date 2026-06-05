"""Historical question resolver for canonical exact-question context.

This module is intentionally narrow: it reads configured question-bank JSON
artifacts and returns a structured exact-question payload when the user message
already contains a concrete MCQ stem and options. It does not grade, route, or
generate final prose.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


QUESTION_BANK_DIR_ENV = "DEEPTUTOR_HISTORICAL_QUESTION_BANK_DIR"


def resolve_historical_question(
    query: str,
    *,
    question_bank_dir: str | None = None,
) -> dict[str, Any] | None:
    """Resolve a concrete user question to a canonical exact-question payload."""

    root = _resolve_question_bank_root(question_bank_dir)
    if root is None:
        return None
    query_surface = _normalize_surface(query)
    if not query_surface:
        return None

    best: tuple[int, dict[str, Any]] | None = None
    for candidate in _load_question_bank(str(root)):
        score = _match_score(query_surface, candidate)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is None:
        return None
    return _project_to_query_option_surface(best[1], query)


def build_canonical_question_context(exact_question: dict[str, Any]) -> dict[str, Any]:
    """Project exact-question payload into the canonical question context shape."""

    question_id = str(exact_question.get("id") or "").strip()
    answer_key = str(exact_question.get("correct_answer") or "").strip()
    return {
        "status": "resolved" if question_id and answer_key else "unresolved",
        "question_id": question_id,
        "question_type": str(exact_question.get("question_type") or "").strip(),
        "answer_kind": str(exact_question.get("answer_kind") or "").strip(),
        "stem": str(exact_question.get("stem") or "").strip(),
        "answer_key": answer_key,
        "source_group": str(exact_question.get("source_group") or "").strip(),
        "source_refs": list(exact_question.get("source_refs") or []),
    }


def render_historical_question_context(exact_question: dict[str, Any]) -> str:
    """Render compact retrieval context for downstream responding layers."""

    stem = str(exact_question.get("stem") or "").strip()
    answer = str(exact_question.get("correct_answer") or "").strip()
    analysis = str(exact_question.get("analysis") or "").strip()
    options = _format_options(exact_question.get("options"))
    parts = ["【题库原题】", stem]
    if options:
        parts.append(options)
    if answer:
        parts.append(f"标准答案：{answer}")
    if analysis:
        parts.append(f"解析：{analysis}")
    return "\n".join(part for part in parts if part)


def build_historical_question_source(exact_question: dict[str, Any]) -> dict[str, Any]:
    metadata = exact_question.get("metadata") if isinstance(exact_question.get("metadata"), dict) else {}
    source_file = str(metadata.get("source_file") or "").strip()
    return {
        "title": "题库原题",
        "content": str(exact_question.get("stem") or "")[:200],
        "source": source_file or "historical_question_bank",
        "page": "",
        "chunk_id": str(exact_question.get("id") or ""),
        "score": 1.0,
        "source_type": "question_bank",
        "source_id": str(exact_question.get("id") or ""),
        "source_table": "",
        "stable_id": str(exact_question.get("id") or ""),
        "source_span": {},
        "content_hash": str(metadata.get("content_hash") or ""),
        "quote_hash": "",
        "node_code": str(metadata.get("node_code") or ""),
        "taxonomy_path": str(metadata.get("node_name") or ""),
    }


def _resolve_question_bank_root(question_bank_dir: str | None) -> Path | None:
    raw = str(question_bank_dir or os.getenv(QUESTION_BANK_DIR_ENV, "") or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    if not root.exists() or not root.is_dir():
        return None
    return root.resolve()


@lru_cache(maxsize=8)
def _load_question_bank(root: str) -> tuple[dict[str, Any], ...]:
    root_path = Path(root)
    items: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.extend(_iter_question_items(payload, source_path=path, metadata={}))
    return tuple(items)


def _iter_question_items(
    node: Any,
    *,
    source_path: Path,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(node, list):
        for child in node:
            items.extend(_iter_question_items(child, source_path=source_path, metadata=metadata))
        return items
    if not isinstance(node, dict):
        return items

    next_metadata = dict(metadata)
    taxonomy = node.get("taxonomy")
    if isinstance(taxonomy, dict):
        if taxonomy.get("node_code"):
            next_metadata["node_code"] = str(taxonomy.get("node_code") or "").strip()
        if taxonomy.get("node_name"):
            next_metadata["node_name"] = str(taxonomy.get("node_name") or "").strip()

    question_data = node.get("question_data")
    if isinstance(question_data, dict):
        exact_question = _build_exact_question(
            question_data,
            exercise_type=str(node.get("type") or "").strip(),
            source_path=source_path,
            metadata=next_metadata,
        )
        if exact_question is not None:
            items.append(exact_question)

    for key, child in node.items():
        if key == "question_data":
            continue
        items.extend(_iter_question_items(child, source_path=source_path, metadata=next_metadata))
    return items


def _build_exact_question(
    question_data: dict[str, Any],
    *,
    exercise_type: str,
    source_path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    stem = str(question_data.get("stem") or question_data.get("question") or "").strip()
    correct_answer = _normalize_answer_key(question_data.get("correct_answer"))
    options = _normalize_options(question_data.get("options"))
    if not stem or not correct_answer or not options:
        return None
    question_type = str(question_data.get("type") or exercise_type or "").strip()
    if not _is_mcq_type(question_type, options):
        return None
    content_hash = _question_hash(stem=stem, options=options, answer=correct_answer)
    source_ref = {
        "source_group": "historical_question_bank",
        "source_file": source_path.name,
        "node_code": str(metadata.get("node_code") or ""),
        "node_name": str(metadata.get("node_name") or ""),
    }
    return {
        "id": f"historical:{content_hash[:16]}",
        "chunk_id": f"historical:{content_hash[:16]}",
        "answer_kind": "mcq",
        "question_type": question_type or "mcq",
        "source_group": "historical_question_bank",
        "stem": stem,
        "options": options,
        "correct_answer": correct_answer,
        "analysis": str(question_data.get("analysis") or "").strip(),
        "score": question_data.get("score"),
        "difficulty": str(question_data.get("difficulty") or "").strip(),
        "confidence": 1.0,
        "source_refs": [source_ref],
        "metadata": {
            **source_ref,
            "content_hash": content_hash,
        },
    }


def _match_score(query_surface: str, candidate: dict[str, Any]) -> int:
    stem = _normalize_surface(candidate.get("stem"))
    if not stem or stem not in query_surface:
        return 0
    option_values = [
        _normalize_surface(item.get("value"))
        for item in candidate.get("options") or []
        if isinstance(item, dict)
    ]
    option_values = [value for value in option_values if value]
    if not option_values:
        return 0
    matches = sum(1 for value in option_values if value in query_surface)
    required = 2 if len(option_values) >= 3 else 1
    if matches < required:
        return 0
    return len(stem) * 10 + matches * 100 + len(str(candidate.get("correct_answer") or ""))


def _project_to_query_option_surface(candidate: dict[str, Any], query: str) -> dict[str, Any]:
    projected = dict(candidate)
    query_options = _extract_query_options(query)
    if len(query_options) < 2:
        return projected

    canonical_by_value = _unique_options_by_normalized_value(candidate.get("options"))
    query_by_value = _unique_options_by_normalized_value(query_options)
    if not canonical_by_value or not query_by_value:
        return projected

    mapped_letters: list[str] = []
    for canonical_letter in _normalize_answer_key(candidate.get("correct_answer")):
        canonical_option = next(
            (
                item
                for item in candidate.get("options") or []
                if isinstance(item, dict)
                and str(item.get("key") or "").strip().upper() == canonical_letter
            ),
            None,
        )
        normalized_value = _normalize_surface(
            canonical_option.get("value") if isinstance(canonical_option, dict) else ""
        )
        query_option = query_by_value.get(normalized_value)
        if not isinstance(query_option, dict):
            return projected
        mapped_letters.append(str(query_option.get("key") or "").strip().upper())

    remapped_answer = _normalize_answer_key("".join(mapped_letters))
    if not remapped_answer:
        return projected
    projected["options"] = query_options
    projected["correct_answer"] = remapped_answer
    metadata = dict(projected.get("metadata") or {})
    metadata["canonical_correct_answer"] = str(candidate.get("correct_answer") or "").strip()
    metadata["option_surface"] = "query"
    projected["metadata"] = metadata
    return projected


def _unique_options_by_normalized_value(raw: Any) -> dict[str, dict[str, str]]:
    options = _normalize_options(raw)
    by_value: dict[str, dict[str, str]] = {}
    duplicates: set[str] = set()
    for item in options:
        normalized_value = _normalize_surface(item.get("value"))
        if not normalized_value:
            continue
        if normalized_value in by_value:
            duplicates.add(normalized_value)
            continue
        by_value[normalized_value] = item
    for duplicate in duplicates:
        by_value.pop(duplicate, None)
    return by_value


def _extract_query_options(query: str) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for line in str(query or "").splitlines():
        key, value = _parse_option_string(line, fallback_key="")
        if key and value:
            options.append({"key": key, "value": value})
    return options


def _normalize_options(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, dict):
        return [
            {"key": str(key).strip().upper(), "value": str(value).strip()}
            for key, value in raw.items()
            if str(key).strip() and str(value).strip()
        ]
    if not isinstance(raw, list):
        return []
    options: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            key = str(item.get("key") or chr(ord("A") + index)).strip().upper()
            value = str(item.get("value") or "").strip()
        else:
            key, value = _parse_option_string(str(item or ""), fallback_key=chr(ord("A") + index))
        if key and value:
            options.append({"key": key, "value": value})
    return options


def _parse_option_string(value: str, *, fallback_key: str) -> tuple[str, str]:
    text = str(value or "").strip()
    match = re.match(r"^\s*([A-Ea-e])[\s\.．、:)）-]*(.+?)\s*$", text)
    if match:
        return match.group(1).upper(), match.group(2).strip()
    return fallback_key, text


def _normalize_answer_key(value: Any) -> str:
    return "".join(sorted(set(re.findall(r"[A-E]", str(value or "").upper()))))


def _normalize_surface(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text.replace("的", "")


def _is_mcq_type(question_type: str, options: list[dict[str, str]]) -> bool:
    normalized = str(question_type or "").strip().lower()
    if normalized in {"single", "single_choice", "multi", "multi_choice", "multiple_choice", "mcq", "choice"}:
        return True
    return len(options) >= 2


def _question_hash(*, stem: str, options: list[dict[str, str]], answer: str) -> str:
    payload = json.dumps(
        {
            "stem": _normalize_surface(stem),
            "options": [
                {"key": item.get("key"), "value": _normalize_surface(item.get("value"))}
                for item in options
            ],
            "answer": answer,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _format_options(raw: Any) -> str:
    if not isinstance(raw, list):
        return ""
    lines = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            lines.append(f"{key}. {value}")
    return "\n".join(lines)
