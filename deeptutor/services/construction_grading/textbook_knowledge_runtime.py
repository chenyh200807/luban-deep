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
import re
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


# A coarse node_code can hold 100+ cards; focus a turn to this many most-relevant cards by default.
_DEFAULT_CARD_LIMIT = 12


def _canonical_anchors(manifest: dict[str, Any]) -> set[str]:
    """The L4 anchor codes (e.g. 1A411011) derivable from the canonical leaf codes (1A411011-01-a),
    so a question's syllabus code can match a canonical anchor and resolve its subtree."""
    anchors: set[str] = set()
    for leaf in (manifest.get("canonical_index") or {}):
        anchors.add(leaf)                       # the leaf itself
        anchors.add(str(leaf).split("-", 1)[0])  # its L4 anchor (before the first '-')
    return anchors


def available_nodes() -> list[str]:
    """The codes the signed textbook pack resolves. CANONICAL-first: the canonical leaf codes + their L4
    anchors (the single routing spine); falls back to the legacy block node_index for older bundles."""
    ok, bundle, _pointer = _load_supply()
    if not ok:
        return []
    manifest = bundle.get("manifest") or {}
    anchors = _canonical_anchors(manifest)
    if anchors:
        return sorted(anchors)
    return sorted((manifest.get("node_index") or {}).keys())


def available_paths() -> list[str]:
    """The fine taxonomy_path sub-topics the signed pack indexes (197 vs 20 syllabus nodes)."""
    ok, bundle, _pointer = _load_supply()
    if not ok:
        return []
    return sorted((bundle.get("manifest") or {}).get("path_index", {}).keys())


def _relevance_query(learner_context: dict[str, Any] | None) -> str:
    """Build the lexical relevance query for a turn from its question text (+ the learner's answer)."""
    lc = learner_context or {}
    return " ".join(str(lc.get(k) or "") for k in
                    ("question_stem", "stem", "question_text", "question", "user_answer")).strip()


_NODE_IN_ID = re.compile(r"1A\d{4,}")
_MIN_SECTION_PREFIX = 6  # a question node must share >= this many chars with a textbook node


def node_code_for_question(question_id: str) -> tuple[str, str] | None:
    """Map a question_id to a textbook node_code so any in-bank turn can fetch textbook context.

    Returns ``(node_code, match_kind)`` where match_kind is ``exact`` (the question's own node IS a
    textbook node — high confidence) or ``section`` (the question's node shares the longest, UNIQUE
    >= 6-char prefix with one textbook node — section-level teaching match). Returns None when no
    node code is embedded, or when the best prefix is ambiguous (ties across textbook nodes) — the
    caller then falls open (no wrong-chapter attribution). Teaching context only; never grants
    official authority.
    """
    m = _NODE_IN_ID.search(str(question_id or ""))
    if not m:
        return None
    code = m.group(0)
    nodes = available_nodes()
    if not nodes:
        return None
    if code in nodes:
        return (code, "exact")
    best_len = 0
    best: list[str] = []
    for n in nodes:
        p = 0
        for a, b in zip(code, n):
            if a != b:
                break
            p += 1
        if p > best_len:
            best_len, best = p, [n]
        elif p == best_len:
            best.append(n)
    if best_len >= _MIN_SECTION_PREFIX and len(best) == 1:
        return (best[0], "section")
    return None  # ambiguous or too-shallow prefix -> fall open


def resolve_textbook_knowledge(
    node_code: str,
    *,
    learner_context: dict[str, Any] | None = None,
    grant_release: bool = False,
    limit: int = _DEFAULT_CARD_LIMIT,
) -> dict[str, Any] | None:
    """Resolve a node_code into a verbatim-sourced knowledge payload (or None to fall open).

    The node's cards are FOCUSED to the turn: ranked by lexical relevance to the question text in
    ``learner_context`` and capped to ``limit`` (finer effective granularity over the 197 taxonomy_path
    sub-topics within a coarse syllabus node). Pass ``limit<=0`` to get the whole node.

    ``grant_release`` is the trusted-server F1 decision: True grants controlled official authority;
    False yields teaching/source context with ``official_score_allowed=False``.
    """
    node = str(node_code or "").strip()
    if not node:
        return None
    ok, bundle, pointer = _load_supply()
    if not ok:
        return None
    query = _relevance_query(learner_context)
    pack = _R.build_pack_for_node(
        node, bundle=bundle, pointer=pointer, namespace=_NAMESPACE,
        learner_context=learner_context or {}, grant_release=grant_release,
        query=query, limit=limit,
    )
    if pack is None:
        return None
    pack_dict = pack.to_dict()
    rubric = pack_dict.get("rubric_context", {}).get("rubric", {})
    cards = rubric.get("knowledge_cards", [])
    resolution = pack_dict.get("rubric_context", {})
    policy = pack_dict.get("diagnostic_policy", {})
    return {
        "authority": AUTHORITY,
        "mode": "textbook_knowledge_node",
        "node_code": node,
        "card_count": len(cards),
        "node_card_total": resolution.get("node_card_total"),
        "selection_mode": resolution.get("selection_mode"),
        "selected_taxonomy_paths": resolution.get("selected_taxonomy_paths"),
        "provenance": "verbatim_2026_textbook_content_markdown",
        "official_score_allowed": bool(policy.get("official_score_allowed")),
        "controlled_official": bool(policy.get("controlled_official")),
        "compiled_context": pack_dict,
        "llm_may_decide_correctness": False,
        "not_production_grade": not grant_release,
        "writeback_performed": False,
    }


__all__ = ["AUTHORITY", "available_nodes", "node_code_for_question", "resolve_textbook_knowledge"]
