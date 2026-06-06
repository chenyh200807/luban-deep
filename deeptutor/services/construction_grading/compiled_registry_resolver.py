"""Compiled registry resolver (Living LLM Artifact Compiler, S6 seam).

Design: docs/plan/2026-06-06-luban-living-llm-artifact-compiler-design.md §6.

The single missing seam between a SIGNED release_candidate bundle and ``build_luban_context_pack``.
It mirrors ``objective_runtime_adapter._governed_index``'s four fail-closed gates, then shapes a
``resolution`` dict the runtime context-pack builder consumes. It MINTS no authority: release-grade
is granted only by the server-side ``governed_registry_status`` kwarg the caller passes downstream
(the F1 seam) — never from anything in the bundle or any client input.

Fail-through, not fail-closed: a tamper / missing / mismatched bundle yields ``None`` and the caller
falls open to open-world diagnostic (refusal rate stays 0).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading import full_knowledge_compiler as _FKC
from deeptutor.services.construction_grading.compiled_context import (
    build_pack_from_question_context,
)

_log = logging.getLogger(__name__)


def verify_bundle(bundle: dict[str, Any], pointer: dict[str, Any], *, namespace: str) -> tuple[bool, str]:
    """Four deterministic gates (mirror _governed_index). Returns (ok, reason)."""
    if not isinstance(bundle, dict) or not isinstance(pointer, dict):
        return (False, "malformed")
    manifest = bundle.get("manifest") or {}
    if not _FKC.verify_lane_bundle(bundle, namespace):
        return (False, "verify_lane_bundle_failed")
    if manifest.get("status") != "release_candidate" or manifest.get("published") is True:
        return (False, "status_gate_failed")
    expected = str(pointer.get("expected_content_hash") or "").strip()
    if not expected or str(manifest.get("content_hash") or "") != expected:
        return (False, "pinned_hash_mismatch")
    if manifest.get("namespace") != namespace:
        return (False, "namespace_mismatch")
    return (True, "ok")


def _point_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index signed point records by point_id."""
    return {
        str(r.get("point_id")): r
        for r in bundle.get("records", [])
        if isinstance(r, dict) and r.get("point_id")
    }


def _points_for_question(bundle: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    """Resolve a question's signed points via the manifest's ``question_index`` (qid -> [point_ids]).

    The pipeline augments the manifest with ``question_index`` AFTER signing; this does not affect the
    content_hash/signature (both computed over ``records`` only), so verify_lane_bundle still holds.
    The signer (compile_case_rubric_release_candidate) drops question_id from records, so the index is
    the only safe link from question to its signed points.
    """
    qindex = (bundle.get("manifest") or {}).get("question_index") or {}
    point_ids = qindex.get(qid) or []
    pmap = _point_map(bundle)
    return [pmap[pid] for pid in point_ids if pid in pmap]


def resolve_question(
    question_id: str,
    *,
    bundle: dict[str, Any],
    pointer: dict[str, Any],
    namespace: str = "case_rubric_full",
) -> dict[str, Any] | None:
    """Resolve one case question from a signed case-rubric bundle into a ``resolution`` dict.

    Returns None (caller falls open) on any gate failure or a not-in-bundle question. The resolution
    is shaped for ``build_pack_from_question_context``; it carries NO registry_status — release-grade
    is granted only when the trusted caller passes ``governed_registry_status``.
    """
    qid = str(question_id or "").strip()
    if not qid:
        return None
    ok, reason = verify_bundle(bundle, pointer, namespace=namespace)
    if not ok:
        _log.warning("compiled bundle rejected at resolver: %s", reason)
        return None
    points = _points_for_question(bundle, qid)
    if not points:
        return None
    required_terms: list[str] = []
    for p in points:
        required_terms.extend(p.get("required_terms") or [])
    return {
        "status": "resolved",
        "question_id": qid,
        "question_type": "case",
        # rubric authority comes from the signed points only.
        "rubric": {"points": points, "point_count": len(points)},
        "required_terms": sorted(set(required_terms)),
        "source_refs": [r for p in points for r in (p.get("source_refs") or [])],
    }


def build_pack_for_question(
    question_id: str,
    *,
    bundle: dict[str, Any],
    pointer: dict[str, Any],
    namespace: str = "case_rubric_full",
    learner_context: dict[str, Any] | None = None,
    grant_release: bool = False,
) -> Any | None:
    """Resolve + build the LubanContextPack. ``grant_release`` is the trusted-server F1 decision:
    when True the pack is built with ``governed_registry_status='release_candidate'`` (controlled
    official); when False the same signed rubric yields ``official_score_allowed=False`` (proof the
    authority is granted by the server kwarg, never by the bundle/client)."""
    resolution = resolve_question(question_id, bundle=bundle, pointer=pointer, namespace=namespace)
    if resolution is None:
        return None
    return build_pack_from_question_context(
        resolution,
        learner_context=learner_context or {},
        governed_registry_status="release_candidate" if grant_release else "",
    )


def resolve_node(
    node_code: str,
    *,
    bundle: dict[str, Any],
    pointer: dict[str, Any],
    namespace: str = "textbook_knowledge_full",
) -> dict[str, Any] | None:
    """Resolve a 2026 教材 knowledge node from a signed textbook bundle into a ``resolution`` dict.

    Mirrors ``resolve_question`` but keys on the manifest ``node_index`` (node_code -> [point_ids]).
    Returns None (caller falls open) on any gate failure or a not-in-bundle node. Carries NO
    registry_status — release-grade is granted only by the trusted ``governed_registry_status`` kwarg.
    """
    node = str(node_code or "").strip()
    if not node:
        return None
    ok, reason = verify_bundle(bundle, pointer, namespace=namespace)
    if not ok:
        _log.warning("textbook bundle rejected at resolver: %s", reason)
        return None
    nindex = (bundle.get("manifest") or {}).get("node_index") or {}
    pmap = _point_map(bundle)
    cards = [pmap[pid] for pid in (nindex.get(node) or []) if pid in pmap]
    if not cards:
        return None
    required_terms = sorted({t for c in cards for t in (c.get("required_terms") or [])})
    return {
        "status": "resolved",
        "question_id": node,                 # identity slot reused
        "question_type": "knowledge_node",
        "rubric": {"knowledge_cards": cards, "card_count": len(cards)},
        "required_terms": required_terms,
        "source_refs": [
            {"chunk_id": c.get("chunk_id"), "taxonomy_path": c.get("taxonomy_path"),
             "provenance_kind": c.get("provenance_class"), "textbook_quote": c.get("textbook_quote")}
            for c in cards
        ],
    }


def build_pack_for_node(
    node_code: str,
    *,
    bundle: dict[str, Any],
    pointer: dict[str, Any],
    namespace: str = "textbook_knowledge_full",
    learner_context: dict[str, Any] | None = None,
    grant_release: bool = False,
) -> Any | None:
    """Resolve a textbook node + build the LubanContextPack. ``grant_release`` is the trusted-server F1
    decision (authority is the server kwarg, never the bundle)."""
    resolution = resolve_node(node_code, bundle=bundle, pointer=pointer, namespace=namespace)
    if resolution is None:
        return None
    return build_pack_from_question_context(
        resolution,
        learner_context=learner_context or {},
        governed_registry_status="release_candidate" if grant_release else "",
    )


def load_supply(dir_path: str | Path, *, bundle_name: str, pointer_name: str = "canonical_pointer.json") -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Read a tracked runtime-supply bundle + canonical pointer from disk (read-only). None on error."""
    d = Path(dir_path)
    bundle_path = d / bundle_name
    pointer_path = d / pointer_name
    if not bundle_path.exists() or not pointer_path.exists():
        return None
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — never raise into the runtime
        return None
    return (bundle, pointer)


__all__ = ["verify_bundle", "resolve_question", "build_pack_for_question",
           "resolve_node", "build_pack_for_node", "load_supply"]
