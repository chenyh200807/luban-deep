"""Textbook knowledge runtime consumer (Living LLM Artifact Compiler, increment ① · runtime).

Loads the SIGNED tracked textbook knowledge supply (``runtime_supply/v_textbook_knowledge_full``) and
resolves a node_code into verbatim-sourced teaching / grading context for the runtime surfaces
(TutorBot / deep_question grading). All policy lives here (fat skill); the deep_question wrapper only
reads flag + cohort + node and appends.

Authority discipline: the consumer MINTS nothing. It runs the resolver's four fail-closed gates
(verify_lane_bundle + status + pinned content_hash + namespace), then builds the LubanContextPack via
the F1 seam — release-grade is granted ONLY when a trusted server caller passes ``grant_release``.
A tamper / missing / unknown node falls through to None (caller falls open; refusal rate stays 0).
The signed knowledge is verbatim 2026-textbook content; it is teaching/source context, never an
answer-key authority.
"""
from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading import compiled_registry_resolver as _R

_log = logging.getLogger(__name__)

AUTHORITY = "luban_textbook_knowledge"
_NAMESPACE = "textbook_knowledge_full"
_SUPPLY_DIR = Path(__file__).parent / "runtime_supply" / "v_textbook_knowledge_full"
_BUNDLE_NAME = "textbook_knowledge_release_candidate.json"


@lru_cache(maxsize=1)
def _load_supply() -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """Load + four-gate verify the tracked signed textbook bundle once. Fail-through on any problem."""
    loaded = _R.load_supply(_SUPPLY_DIR, bundle_name=_BUNDLE_NAME)
    if loaded is None:
        return (False, {}, {})
    bundle, pointer = loaded
    ok, reason = _R.verify_bundle(bundle, pointer, namespace=_NAMESPACE)
    if not ok:
        _log.warning("textbook knowledge supply rejected: %s", reason)
        return (False, {}, {})
    return (True, bundle, pointer)


def available_nodes() -> list[str]:
    """The node_codes the signed textbook pack can resolve (empty if the supply is unavailable)."""
    ok, bundle, _pointer = _load_supply()
    if not ok:
        return []
    return sorted((bundle.get("manifest") or {}).get("node_index", {}).keys())


def resolve_textbook_knowledge(
    node_code: str,
    *,
    learner_context: dict[str, Any] | None = None,
    grant_release: bool = False,
) -> dict[str, Any] | None:
    """Resolve a node_code into a verbatim-sourced knowledge payload (or None to fall open).

    ``grant_release`` is the trusted-server F1 decision: True grants controlled official authority;
    False yields teaching/source context with ``official_score_allowed=False``.
    """
    node = str(node_code or "").strip()
    if not node:
        return None
    ok, bundle, pointer = _load_supply()
    if not ok:
        return None
    pack = _R.build_pack_for_node(
        node, bundle=bundle, pointer=pointer, namespace=_NAMESPACE,
        learner_context=learner_context or {}, grant_release=grant_release,
    )
    if pack is None:
        return None
    pack_dict = pack.to_dict()
    cards = pack_dict.get("rubric_context", {}).get("rubric", {}).get("knowledge_cards", [])
    policy = pack_dict.get("diagnostic_policy", {})
    return {
        "authority": AUTHORITY,
        "mode": "textbook_knowledge_node",
        "node_code": node,
        "card_count": len(cards),
        "provenance": "verbatim_2026_textbook_content_markdown",
        "official_score_allowed": bool(policy.get("official_score_allowed")),
        "controlled_official": bool(policy.get("controlled_official")),
        "compiled_context": pack_dict,
        "llm_may_decide_correctness": False,
        "not_production_grade": not grant_release,
        "writeback_performed": False,
    }


__all__ = ["AUTHORITY", "available_nodes", "resolve_textbook_knowledge"]
