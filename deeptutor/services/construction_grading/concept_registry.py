"""Concept registry — the source-root identity fix for the canonical taxonomy.

The auto-generated canonical tree has two identity defects: codes are not globally unique (312 codes
bind different concepts; 490 are duplicate same-name-same-parent subtrees) and ``id = code#ordinal`` is
positional (a recompile silently re-points persisted learner state). This module compiles the dirty
tree into a CLEAN registry of frozen concept identities.

Identity design (validated: the textbook chapter structure is 100% stable across the two cleaning
versions, so it is a far better anchor than the auto-gen code):
  * ``concept_id`` is a frozen, content-derived id. Bootstrap = sha256 over the NORMALIZED name_path.
    Once published it is frozen; later name/parent edits are absorbed via the lifecycle map, NOT a
    re-hash (so persisted learner state never silently re-points).
  * the old ``code`` and positional id become ALIASES (lookup compatibility), never the primary key.
  * duplicate same-name-same-parent nodes MERGE into one concept; keywords are unioned WITH provenance
    (which old node each keyword came from) so a later precision regression is auditable/reversible.
  * same-code-different-name stay SEPARATE concepts (their name_paths differ -> different concept_id).

Pure / deterministic: given the same node list, the registry is byte-identical (re-key stability).
"""
from __future__ import annotations

import hashlib
from typing import Any

SCHEMA_VERSION = "luban_concept_registry.v1"


def _norm_path(name_path: str) -> str:
    """Normalize a name_path for identity: collapse whitespace, drop empty segments, unify separators.
    Stable to cosmetic edits; sensitive to real concept/parent changes (those go through lifecycle)."""
    segs = [s.strip() for s in str(name_path or "").split(">")]
    return " > ".join(s for s in segs if s)


def concept_id_for(name_path: str) -> str:
    return "c_" + hashlib.sha256(_norm_path(name_path).encode("utf-8")).hexdigest()[:16]


def compile_registry(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile dirty taxonomy nodes into a clean concept registry.

    Each input node: {code, name, parent, name_path, keywords(list), level}. Nodes sharing a normalized
    name_path MERGE into one concept (same real concept); their codes/keywords/levels are aggregated.
    Returns {manifest, concepts: {concept_id: {...}}, alias_index: {code|old_id -> concept_id}}.
    """
    by_concept: dict[str, dict[str, Any]] = {}
    for n in nodes:
        np = _norm_path(n.get("name_path", ""))
        if not np:
            continue
        cid = concept_id_for(np)
        c = by_concept.get(cid)
        if c is None:
            c = {
                "concept_id": cid,
                "canonical_name": n.get("name", ""),
                "canonical_path": np,
                "level": n.get("level"),
                "alias_codes": [],
                "keywords": [],          # [{text, source_code}] — provenance kept
                "merged_from": [],
                "lifecycle": {"status": "active", "replaced_by": None, "split_into": []},
            }
            by_concept[cid] = c
        code = str(n.get("code") or "")
        if code and code not in c["alias_codes"]:
            c["alias_codes"].append(code)
        c["merged_from"].append({"code": code, "name": n.get("name"), "parent": n.get("parent")})
        seen_kw = {k["text"] for k in c["keywords"]}
        for kw in (n.get("keywords") or []):
            if kw and kw not in seen_kw:
                c["keywords"].append({"text": kw, "source_code": code})
                seen_kw.add(kw)

    # alias index: every old code -> its concept_id (codes that collide across concepts map to MANY;
    # we record the collision so resolution can disambiguate by name_path, never silently pick one).
    alias_index: dict[str, Any] = {}
    for cid, c in by_concept.items():
        for code in c["alias_codes"]:
            if code in alias_index:
                prev = alias_index[code]
                if isinstance(prev, list):
                    prev.append(cid)
                else:
                    alias_index[code] = [prev, cid]
            else:
                alias_index[code] = cid

    merged_count = sum(1 for c in by_concept.values() if len(c["merged_from"]) > 1)
    collided_codes = sum(1 for v in alias_index.values() if isinstance(v, list))
    concepts_sorted = dict(sorted(by_concept.items()))
    content_hash = hashlib.sha256(
        repr([(c["concept_id"], c["canonical_path"], tuple(k["text"] for k in c["keywords"]))
              for c in concepts_sorted.values()]).encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": "concept_registry",
        "status": "release_candidate",
        "published": False,
        "input_nodes": len(nodes),
        "concept_count": len(by_concept),
        "merged_concepts": merged_count,
        "collided_codes": collided_codes,
        "content_hash": content_hash,
    }
    return {"manifest": manifest, "concepts": concepts_sorted, "alias_index": alias_index}


def resolve_alias(registry: dict[str, Any], code: str, name_path: str = "") -> str:
    """Map an old code (+ optional name_path to disambiguate a collision) to a frozen concept_id."""
    hit = (registry.get("alias_index") or {}).get(str(code or ""))
    if hit is None:
        return concept_id_for(name_path) if name_path else ""
    if isinstance(hit, list):  # collided code -> disambiguate by name_path
        want = concept_id_for(name_path) if name_path else ""
        return want if want in hit else ""
    return hit


__all__ = ["SCHEMA_VERSION", "concept_id_for", "compile_registry", "resolve_alias"]
