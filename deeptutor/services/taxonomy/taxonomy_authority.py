from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

_COMPILED_TAXONOMY_PATH = Path(__file__).resolve().parent / "compiled" / "construction_2026_taxonomy.compiled.json"
_BASE_CODE_RE = re.compile(r"^1A\d{6}$", re.IGNORECASE)
_PARENT_CODE_RE = re.compile(r"^1A\d{3}000$", re.IGNORECASE)


def normalize_taxonomy_code(value: Any) -> str:
    # suffix segments keep their case: the 2026 book-derived tree uses uppercase
    # leaf segments (-B103) while legacy codes used lowercase (-02-a); the
    # nodes_by_code index resolves casing via casefolded fallback keys.
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split("-")
    return "-".join([parts[0].upper(), *parts[1:]])


def taxonomy_label(value: Any) -> str:
    code = normalize_taxonomy_code(value)
    if not code:
        return ""
    by_code = _nodes_by_code()
    for candidate in _candidate_codes(code):
        node = by_code.get(candidate) or by_code.get(candidate.casefold())
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


def student_taxonomy_label(value: Any) -> str:
    """SINGLE AUTHORITY for student-facing taxonomy display.

    Returns the canonical Chinese name, or '' when the code cannot be resolved — NEVER the raw code.
    Codes (``1A432000``, ``E02``, ``EXAM_...::Q1-1``, other-track ``1B...``) are meaningless to learners,
    so every learner-facing read model must resolve through HERE instead of ``display_taxonomy_label(x,
    fallback=x)`` (which leaks the code on a miss). The caller decides what to show when this is empty
    (a question topic, an error label, or to omit the row) — but it must never fall back to the code."""
    return taxonomy_label(value)


# Machine-code shapes that must NEVER reach a learner verbatim. Broad on purpose: construction node codes
# of any track/length (1A412000 / 1B.. / 2A.. / 12A4120000 / 7-digit), error codes (E02 / M03), rubric
# refs (Q1-1 / R12 / r3), UUID-ish ids, and compound rubric/exam ids (EXAM_...::E0::Q1-1).
_CODE_SHAPE_RE = re.compile(
    r"^(?:\d{0,2}[A-Za-z]\d{6,}|[EM]\d{2}|[A-Za-z]?\d+(?:-\d+)+|[Rr]\d+)$"
    r"|::|^EXAM_|[0-9a-f]{8}-[0-9a-f]{4}-|_[0-9a-f]{8,}",
    re.IGNORECASE,
)
# Embedded construction code inside free text — NO \b (Python \b fails between a code and an adjacent CJK
# char, e.g. "项目1A412000管理"); use explicit ASCII-alnum lookarounds so CJK-adjacent codes are caught.
_EMBEDDED_CODE_RE = re.compile(r"(?<![A-Za-z0-9])\d{0,2}[A-Za-z]\d{6,}(?![A-Za-z0-9])")
_CJK_RE = re.compile(r"[㐀-鿿]")


def looks_like_taxonomy_code(value: Any) -> bool:
    """True when the string is a machine code (taxonomy / error / rubric / uuid id), not human text."""
    text = str(value or "").strip()
    return bool(text) and bool(_CODE_SHAPE_RE.search(text))


def student_facing_label(value: Any, *, generic: str = "") -> str:
    """SINGLE AUTHORITY for any learner-facing label that MIGHT be a code OR already-human text.

    Heuristic that NEVER leaks a code: a string containing ANY Chinese character is human text and passes
    through; a string with NO Chinese is treated as a machine code/id and is resolved to its canonical
    Chinese name, or ``generic`` — the raw code is never shown. (A Chinese exam app's learner-facing labels
    are Chinese; pure-ASCII learner text is almost always a code/id.) Whole-label values only — embedded
    codes inside free text go through ``scrub_codes_for_student``."""
    text = str(value or "").strip()
    if not text:
        return generic
    if _CJK_RE.search(text):
        return text                              # human Chinese text — pass through
    return taxonomy_label(text) or generic       # no Chinese -> a code/id -> Chinese name or generic, never raw


def scrub_codes_for_student(text: Any, *, generic: str = "相关考点") -> str:
    """Replace any embedded construction code inside free text with its canonical Chinese name (or
    ``generic`` on a miss) so a learner never sees a code fragment — works even when the code is wedged
    against Chinese characters (``项目1A412000管理`` -> ``项目主要建筑工程材料……管理``)."""
    out = str(text or "")
    return _EMBEDDED_CODE_RE.sub(lambda m: taxonomy_label(m.group(0)) or generic, out)


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


def taxonomy_tree_stats() -> dict[str, int]:
    """Original outline tree statistics, not the deduped lookup index.

    `nodes_by_code` deliberately drops ambiguous duplicate codes for resolver
    safety. Learning-report totals need the full textbook/taxonomy outline
    instead, otherwise the UI undercounts total nodes and wildly overcounts
    leaves.
    """
    return dict(_taxonomy_tree_stats())


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
def _taxonomy_tree_stats() -> dict[str, int]:
    source = _safe_dict(_compiled_taxonomy().get("source"))
    embedded = _coerce_stats(source.get("stats"))
    if embedded:
        return embedded

    path = Path(str(source.get("path") or ""))
    if path.exists():
        stats = _stats_from_source_path(path)
        if stats:
            return stats

    nodes = taxonomy_nodes()
    code_counts = Counter(normalize_taxonomy_code(node.get("code")) for node in nodes if normalize_taxonomy_code(node.get("code")))
    parent_refs = {
        normalize_taxonomy_code(_safe_dict(node).get("parent_code"))
        for node in nodes
        if normalize_taxonomy_code(_safe_dict(node).get("parent_code"))
    }
    leaf_nodes = [
        node
        for node in nodes
        if normalize_taxonomy_code(_safe_dict(node).get("code")) not in parent_refs
    ]
    return {
        "total_nodes": len(nodes),
        "coded_nodes": sum(code_counts.values()),
        "leaf_nodes": len(leaf_nodes),
        "unique_codes": len(code_counts),
        "duplicate_code_rows": sum(count - 1 for count in code_counts.values() if count > 1),
    }


def _stats_from_source_path(path: Path) -> dict[str, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return _stats_from_outline_payload(payload)


def _stats_from_outline_payload(payload: dict[str, Any]) -> dict[str, int]:
    total_nodes = 0
    leaf_nodes = 0
    code_counts: Counter[str] = Counter()

    def walk(items: list[Any]) -> None:
        nonlocal total_nodes, leaf_nodes
        for item in items:
            if not isinstance(item, dict):
                continue
            total_nodes += 1
            code = normalize_taxonomy_code(item.get("code") or item.get("node_code"))
            if code:
                code_counts[code] += 1
            children = list(item.get("children") or [])
            if children:
                walk(children)
            else:
                leaf_nodes += 1

    walk(list(_safe_dict(payload).get("outline_structure") or []))
    if total_nodes <= 0:
        return {}
    return {
        "total_nodes": total_nodes,
        "coded_nodes": sum(code_counts.values()),
        "leaf_nodes": leaf_nodes,
        "unique_codes": len(code_counts),
        "duplicate_code_rows": sum(count - 1 for count in code_counts.values() if count > 1),
    }


def _coerce_stats(value: Any) -> dict[str, int]:
    stats = _safe_dict(value)
    result = {
        "total_nodes": int(stats.get("total_nodes") or 0),
        "coded_nodes": int(stats.get("coded_nodes") or 0),
        "leaf_nodes": int(stats.get("leaf_nodes") or 0),
        "unique_codes": int(stats.get("unique_codes") or 0),
        "duplicate_code_rows": int(stats.get("duplicate_code_rows") or 0),
    }
    return result if result["total_nodes"] > 0 and result["leaf_nodes"] > 0 else {}


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
    # casefolded fallback keys so lowercased refs (e.g. "1a412010-b103" from
    # historical learner payloads) still resolve to the canonical-cased node
    for code, node in list(result.items()):
        folded = code.casefold()
        if folded != code and folded not in result:
            result[folded] = node
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


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


__all__ = [
    "chapter_prefix_labels",
    "display_taxonomy_label",
    "normalize_taxonomy_code",
    "taxonomy_index",
    "taxonomy_label",
    "taxonomy_nodes",
    "taxonomy_source_metadata",
    "taxonomy_tree_stats",
]
