from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_COMPILED_TAXONOMY_PATH = Path(__file__).resolve().parent / "compiled" / "construction_2026_taxonomy.compiled.json"
_BASE_CODE_RE = re.compile(r"^1A\d{6}$", re.IGNORECASE)
_PARENT_CODE_RE = re.compile(r"^1A\d{3}000$", re.IGNORECASE)


def normalize_taxonomy_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split("-")
    normalized = [parts[0].upper()]
    for part in parts[1:]:
        normalized.append(part.lower() if part.isalpha() else part)
    return "-".join(normalized)


def taxonomy_label(value: Any) -> str:
    code = normalize_taxonomy_code(value)
    if not code:
        return ""
    by_code = _nodes_by_code()
    for candidate in _candidate_codes(code):
        node = by_code.get(candidate)
        if node:
            return str(node.get("name") or "").strip()
    return chapter_prefix_labels().get(code[:5], "") if len(code) >= 5 else ""


def display_taxonomy_label(value: Any, *, with_code: bool = False, fallback: str = "") -> str:
    code = normalize_taxonomy_code(value)
    label = taxonomy_label(code)
    if not label:
        return fallback or code
    if with_code and code:
        return f"{label}（{code}）"
    return label


def chapter_prefix_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    all_by_code = _all_nodes_by_code()
    unique_by_code = _nodes_by_code()
    for code in sorted(all_by_code):
        if not _PARENT_CODE_RE.fullmatch(code):
            continue
        prefix = code[:5]
        node = unique_by_code.get(code) or _preferred_node(all_by_code.get(code) or [])
        label = str((node or {}).get("name") or "").strip()
        if label:
            labels[prefix] = label
    return labels


def taxonomy_source_metadata() -> dict[str, str]:
    source = dict(_compiled_taxonomy().get("source") or {})
    return {
        "path": str(source.get("path") or ""),
        "sha256": str(source.get("sha256") or ""),
    }


def taxonomy_nodes() -> list[dict[str, Any]]:
    return [dict(node) for node in list(_compiled_taxonomy().get("nodes") or []) if isinstance(node, dict)]


def taxonomy_index() -> dict[str, dict[str, dict[str, Any]]]:
    nodes = taxonomy_nodes()
    return {
        "nodes_by_code": _nodes_by_code_from_nodes(nodes),
        "nodes_by_id": {
            str(node.get("id") or "").strip(): node
            for node in nodes
            if str(node.get("id") or "").strip()
        },
        "nodes_by_name": _nodes_by_name_from_nodes(nodes),
    }


@lru_cache(maxsize=1)
def _compiled_taxonomy() -> dict[str, Any]:
    try:
        return json.loads(_COMPILED_TAXONOMY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"source": {}, "nodes": [], "nodes_by_code": {}, "nodes_by_id": {}}


@lru_cache(maxsize=1)
def _nodes_by_code() -> dict[str, dict[str, Any]]:
    compiled = _compiled_taxonomy()
    nodes_by_code = compiled.get("nodes_by_code")
    if isinstance(nodes_by_code, dict) and nodes_by_code:
        return {
            normalize_taxonomy_code(code): dict(node)
            for code, node in nodes_by_code.items()
            if normalize_taxonomy_code(code) and isinstance(node, dict)
        }
    return _nodes_by_code_from_nodes(taxonomy_nodes())


@lru_cache(maxsize=1)
def _all_nodes_by_code() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for node in taxonomy_nodes():
        code = normalize_taxonomy_code(node.get("code"))
        if code:
            grouped.setdefault(code, []).append(node)
    return grouped


def _nodes_by_code_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        code = normalize_taxonomy_code(node.get("code"))
        if code:
            grouped.setdefault(code, []).append(node)
    result: dict[str, dict[str, Any]] = {}
    for code, items in grouped.items():
        labels = {str(item.get("name") or "").strip() for item in items if str(item.get("name") or "").strip()}
        if len(labels) <= 1:
            result[code] = items[-1]
    return result


def _nodes_by_name_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    name_codes: dict[str, set[str]] = {}
    for node in nodes:
        name = _compact(node.get("name"))
        code = normalize_taxonomy_code(node.get("code"))
        if name and code:
            name_codes.setdefault(name, set()).add(code)
    ambiguous_names = {name for name, codes in name_codes.items() if len(codes) > 1}
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        name = _compact(node.get("name"))
        if name and name not in ambiguous_names:
            result.setdefault(name, node)
    return result


def _candidate_codes(code: str) -> list[str]:
    candidates = [code]
    parts = code.split("-")
    while len(parts) > 1:
        parts = parts[:-1]
        parent = "-".join(parts)
        if parent not in candidates:
            candidates.append(parent)
    base = parts[0]
    if _BASE_CODE_RE.fullmatch(base):
        for candidate in (
            f"{base[:7]}0",
            f"{base[:6]}00",
            f"{base[:5]}000",
            base[:5],
        ):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _preferred_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not nodes:
        return None
    return sorted(nodes, key=_node_sort_key)[0]


def _node_sort_key(node: dict[str, Any]) -> tuple[int, int, str]:
    name = str(node.get("name") or "").strip()
    level = int(node.get("level") or 99)
    return (
        1 if name.startswith("第") else 0,
        level,
        str(node.get("id") or node.get("code") or ""),
    )


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


__all__ = [
    "chapter_prefix_labels",
    "display_taxonomy_label",
    "normalize_taxonomy_code",
    "taxonomy_index",
    "taxonomy_label",
    "taxonomy_nodes",
    "taxonomy_source_metadata",
]
