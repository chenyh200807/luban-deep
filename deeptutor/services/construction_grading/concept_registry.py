"""Concept registry — the source-root identity fix for the canonical taxonomy.

The auto-generated canonical tree has identity defects: codes are not globally unique (312 codes bind
different concepts; 490 are duplicate same-name-same-parent subtrees) and ``id = code#ordinal`` is
positional (a recompile silently re-points persisted learner state). This module compiles the dirty
tree into a registry of stable concept identities.

Identity model (hardened after adversarial review — name_path is a FINGERPRINT, never the durable key):
  * ``concept_id`` is a STABLE durable id (``c_<6hex>``). On first compile it is assigned deterministically
    by sorted fingerprint order; on every later compile a ``prior`` registry is matched by fingerprint so
    an existing concept KEEPS its concept_id even if its name/parent/path later changes. A textbook
    revision that renames or re-parents a concept therefore does NOT break persisted learner state.
  * ``name_path_hash`` is a FINGERPRINT (matching/migration only), NOT the primary key.
  * the old ``code`` and positional id become ALIASES; a code colliding across concepts maps to a LIST
    (readers must disambiguate by name_path and MUST NOT single-resolve a collided code).
  * nodes sharing a normalized name_path AND parent merge as ``confirmed_same``; nodes sharing the
    name_path but with DIFFERENT parents are NOT auto-merged — they are kept as separate concepts and
    flagged ``structural_conflict`` for review (avoids silently swallowing a real branch difference).
  * every concept keeps ``source_nodes[]`` (full per-node provenance), not just a keyword union.

Deterministic: same input (+ same prior) -> byte-identical registry.
"""
from __future__ import annotations

import hashlib
from typing import Any

SCHEMA_VERSION = "luban_concept_registry.v3"

STATUS_CONFIRMED = "confirmed_same"
STATUS_STRUCTURAL_CONFLICT = "structural_conflict"
STATUS_SINGLETON = "singleton"

# adjudication lifecycle (B): a structural_conflict moves through these via a governed decision.
ADJ_PENDING = "pending"
ADJ_MERGE = "adjudicated_merge"
ADJ_SPLIT = "adjudicated_split"
ADJ_DEPRECATED = "deprecated_alias"


def _norm_path(name_path: str) -> str:
    segs = [s.strip() for s in str(name_path or "").split(">")]
    return " > ".join(s for s in segs if s)


def name_path_hash(name_path: str) -> str:
    return hashlib.sha256(_norm_path(name_path).encode("utf-8")).hexdigest()[:16]


def _stable_id(seed: str) -> str:
    # 16 hex (64-bit) — birthday-collision-safe for the registry size (vs the v2 6-hex/24-bit risk).
    return "c_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _group_key(name_path: str, parent: str) -> tuple[str, str]:
    """A concept group = (normalized name_path, parent). Same path+parent -> same concept (confirmed).
    Same path but different parent stays a SEPARATE group (structural_conflict, not auto-merged)."""
    return (_norm_path(name_path), str(parent or ""))


def compile_registry(nodes: list[dict[str, Any]], *, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile dirty taxonomy nodes into a stable concept registry.

    Grouping is by (normalized name_path, parent): same -> one concept; same path/different parent ->
    separate concepts each flagged structural_conflict. ``prior`` (a previous registry) lets existing
    concepts keep their concept_id across a recompile (matched by name_path_hash), so durable ids
    survive textbook revisions.
    """
    # collect groups
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    paths_to_parents: dict[str, set[str]] = {}
    for n in nodes:
        np = _norm_path(n.get("name_path", ""))
        if not np:
            continue
        parent = str(n.get("parent") or "")
        gk = _group_key(np, parent)
        paths_to_parents.setdefault(np, set()).add(parent)
        g = groups.get(gk)
        if g is None:
            g = {"norm_path": np, "parent": parent, "name": n.get("name", ""),
                 "level": n.get("level"), "alias_codes": [], "keywords": [], "source_nodes": []}
            groups[gk] = g
        code = str(n.get("code") or "")
        if code and code not in g["alias_codes"]:
            g["alias_codes"].append(code)
        g["source_nodes"].append({"code": code, "name": n.get("name"), "parent": parent,
                                  "raw_name_path": n.get("name_path"), "level": n.get("level")})
        seen = {k["text"] for k in g["keywords"]}
        for kw in (n.get("keywords") or []):
            if kw and kw not in seen:
                g["keywords"].append({"text": kw, "source_code": code})
                seen.add(kw)

    # prior id reuse: fingerprint (name_path_hash + parent) -> existing concept_id
    prior_by_fp: dict[str, str] = {}
    if prior:
        for cid, c in (prior.get("concepts") or {}).items():
            fp = f"{name_path_hash(c.get('canonical_path', ''))}|{c.get('parent', '')}"
            prior_by_fp[fp] = cid

    concepts: dict[str, Any] = {}
    used_ids: set[str] = set()
    # deterministic order: by norm_path then parent
    for gk in sorted(groups):
        g = groups[gk]
        np, parent = gk
        nph = name_path_hash(np)
        fp = f"{nph}|{parent}"
        # status: structural_conflict if this name_path appears under >1 parent
        status = (STATUS_STRUCTURAL_CONFLICT if len(paths_to_parents.get(np, set())) > 1
                  else (STATUS_CONFIRMED if len(g["source_nodes"]) > 1 else STATUS_SINGLETON))
        cid = prior_by_fp.get(fp)
        if not cid or cid in used_ids:
            cid = _stable_id(fp)
            salt = 0
            while cid in used_ids:  # extremely unlikely; keep ids unique + deterministic
                salt += 1
                cid = _stable_id(f"{fp}#{salt}")
        used_ids.add(cid)
        concepts[cid] = {
            "concept_id": cid,
            "canonical_name": g["name"],
            "canonical_path": np,
            "parent": parent,
            "level": g["level"],
            "name_path_hash": nph,                 # FINGERPRINT, not the key
            "equivalence_status": status,
            "alias_codes": g["alias_codes"],
            "keywords": g["keywords"],
            "source_nodes": g["source_nodes"],     # full provenance, not just keyword union
            # lineage (B): governance over the concept's identity lifecycle. adjudication_status is
            # 'pending' for an unresolved structural_conflict, else 'n/a'. A governed decision later
            # fills supersedes/merged_from/split_from + flips canonical_concept_id.
            "lineage": {
                "adjudication_status": ADJ_PENDING if status == STATUS_STRUCTURAL_CONFLICT else "n/a",
                "canonical_concept_id": cid,        # self until a merge adjudication re-points it
                "supersedes": [], "merged_from": [], "split_from": None,
                "valid_from": None, "valid_to": None,
            },
            "lifecycle": {"status": "active", "replaced_by": None, "split_into": []},
        }

    # alias index: code -> concept_id; a code spanning >1 concept maps to a LIST (no single-resolve)
    alias_index: dict[str, Any] = {}
    for cid, c in concepts.items():
        for code in c["alias_codes"]:
            if code in alias_index:
                prev = alias_index[code]
                alias_index[code] = (prev + [cid]) if isinstance(prev, list) else [prev, cid]
            else:
                alias_index[code] = cid

    structural = sum(1 for c in concepts.values() if c["equivalence_status"] == STATUS_STRUCTURAL_CONFLICT)
    merged = sum(1 for c in concepts.values() if len(c["source_nodes"]) > 1)
    collided = sum(1 for v in alias_index.values() if isinstance(v, list))
    concepts = dict(sorted(concepts.items()))
    content_hash = hashlib.sha256(
        repr([(c["concept_id"], c["canonical_path"], c["parent"], c["equivalence_status"],
               tuple(k["text"] for k in c["keywords"])) for c in concepts.values()]).encode("utf-8")
    ).hexdigest()
    unresolved = sum(1 for c in concepts.values()
                     if c["lineage"]["adjudication_status"] == ADJ_PENDING)
    # PUBLISH GATE: identity is a snapshot of the directory topology, NOT an adjudicated semantic
    # identity. It is safe for retrieval / compilation / coverage indexing, but it MUST NOT be a
    # learner_state durable key while any structural_conflict is unresolved (would transfer future
    # adjudication cost onto learner data). Flips only after governance (B) resolves all conflicts.
    learner_key_safe = unresolved == 0
    manifest = {
        "schema_version": SCHEMA_VERSION, "namespace": "concept_registry",
        "status": "release_candidate", "published": False,
        "input_nodes": len(nodes), "concept_count": len(concepts),
        "merged_confirmed": merged, "structural_conflicts": structural,
        "unresolved_adjudications": unresolved,
        "collided_codes": collided, "reused_prior_ids": sum(1 for c in concepts if c in prior_by_fp.values()),
        "usable_as": ["retrieval", "compilation", "coverage_indexing"],
        "not_usable_as": ([] if learner_key_safe else ["learner_state_durable_key"]),
        "learner_state_durable_key_safe": learner_key_safe,
        "content_hash": content_hash,
    }
    return {"manifest": manifest, "concepts": concepts, "alias_index": alias_index}


def resolve_alias(registry: dict[str, Any], code: str, name_path: str = "") -> str:
    """Map an old code (+ name_path to disambiguate a collision) to a concept_id. A collided code with
    no name_path returns '' — readers MUST NOT single-resolve a collided code (hard block)."""
    hit = (registry.get("alias_index") or {}).get(str(code or ""))
    if hit is None:
        return ""
    if isinstance(hit, list):
        if not name_path:
            return ""
        nph = name_path_hash(name_path)
        for cid in hit:
            if (registry["concepts"].get(cid) or {}).get("name_path_hash") == nph:
                return cid
        return ""
    return hit


def apply_adjudications(registry: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply governed adjudications (B) to resolve structural_conflicts deterministically.

    Each decision: {concept_ids: [...], action: 'adjudicated_merge'|'adjudicated_split'|'deprecated_alias',
    canonical_concept_id?, reviewer, reason}. MERGE: the listed concepts collapse into canonical_concept_id
    (others get lineage.canonical_concept_id -> the winner, status adjudicated_merge, recorded in winner's
    merged_from + a migration edge). KEEP/SPLIT: each stays its own concept, status adjudicated_split.
    Returns a NEW registry dict + migration_edges (old_concept_id -> canonical_concept_id) so learner_state
    can migrate. Pure: same registry + decisions -> same output."""
    import copy
    reg = copy.deepcopy(registry)
    concepts = reg["concepts"]
    migration_edges: list[dict[str, Any]] = []
    for d in decisions:
        ids = [c for c in (d.get("concept_ids") or []) if c in concepts]
        action = str(d.get("action") or "")
        reviewer = str(d.get("reviewer") or "")
        reason = str(d.get("reason") or "")
        if not ids or not reviewer:
            continue
        if action == ADJ_MERGE:
            winner = str(d.get("canonical_concept_id") or ids[0])
            if winner not in concepts:
                continue
            for cid in ids:
                concepts[cid]["lineage"]["adjudication_status"] = ADJ_MERGE
                concepts[cid]["lineage"]["canonical_concept_id"] = winner
                concepts[cid]["lineage"]["reviewer"] = reviewer
                concepts[cid]["lineage"]["reason"] = reason
                if cid != winner:
                    concepts[cid]["lifecycle"]["status"] = "merged"
                    concepts[cid]["lifecycle"]["replaced_by"] = winner
                    if cid not in concepts[winner]["lineage"]["merged_from"]:
                        concepts[winner]["lineage"]["merged_from"].append(cid)
                    migration_edges.append({"from": cid, "to": winner, "action": ADJ_MERGE,
                                            "reviewer": reviewer, "reason": reason})
        elif action in (ADJ_SPLIT, ADJ_DEPRECATED):
            for cid in ids:
                concepts[cid]["lineage"]["adjudication_status"] = action
                concepts[cid]["lineage"]["reviewer"] = reviewer
                concepts[cid]["lineage"]["reason"] = reason
    # recompute the publish gate
    unresolved = sum(1 for c in concepts.values()
                     if c["lineage"]["adjudication_status"] == ADJ_PENDING)
    reg["manifest"]["unresolved_adjudications"] = unresolved
    reg["manifest"]["learner_state_durable_key_safe"] = unresolved == 0
    reg["manifest"]["not_usable_as"] = [] if unresolved == 0 else ["learner_state_durable_key"]
    reg["manifest"]["adjudications_applied"] = len([d for d in decisions if d.get("reviewer")])
    reg["migration_edges"] = migration_edges
    return reg


__all__ = ["SCHEMA_VERSION", "STATUS_CONFIRMED", "STATUS_STRUCTURAL_CONFLICT", "STATUS_SINGLETON",
           "ADJ_PENDING", "ADJ_MERGE", "ADJ_SPLIT", "ADJ_DEPRECATED",
           "name_path_hash", "compile_registry", "resolve_alias", "apply_adjudications"]
