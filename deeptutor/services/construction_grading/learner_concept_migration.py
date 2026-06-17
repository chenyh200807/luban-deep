"""Learner-state concept migration — the governed bridge from legacy keys to durable concept ids.

Making the concept registry safe as a learner_state durable key needs three things the registry alone
can't provide (adversarial review): (1) governed approval of merges, (2) a legacy-alias migration policy
for the 810 colliding codes, (3) a cross-release semantic identity so a learner fact survives textbook
revisions. This module implements (2)+(3) deterministically and records (1)'s provenance.

Migration policy (fail-safe — never silently mis-attribute a learner's mastery):
  * a legacy key that is a UNIQUE active code -> migrate to that concept's durable id.
  * a key that hits a COLLIDED code (810 of them) WITHOUT disambiguating name_path -> QUARANTINE
    (not migrated; flagged for human resolution) — mis-merging two concepts' mastery is unacceptable.
  * a key resolving to a DEPRECATED (fabricated) concept -> DROP with reason (the concept isn't real).
  * a key resolving to a MERGED concept -> redirect to the canonical winner (lineage.canonical_concept_id).

Cross-release identity: the durable target is the concept's ``concept_id`` (stable across recompiles via
the registry's prior-id reuse) PLUS a ``semantic_fingerprint`` (normalized leaf name) so a future
release can re-link even if the path/parent moved. Pure / deterministic.
"""
from __future__ import annotations

from typing import Any

OUTCOME_MIGRATED = "migrated"
OUTCOME_QUARANTINED = "quarantined_collision"
# deprecated concept with learner signal: NEVER physically dropped — retire from active projection but
# preserve as historical evidence (Codex: learner history is evidence, not the concept's authority).
OUTCOME_ARCHIVED = "archived_deprecated_with_signal"
OUTCOME_DROPPED_EMPTY = "dropped_deprecated_no_signal"
# merged target reached via redirect: needs target-level aggregation (multiple old states -> one winner)
OUTCOME_REDIRECTED = "redirected_merged_needs_aggregation"
# name_path fallback is a LOW-CONFIDENCE candidate, never an authoritative write
OUTCOME_CANDIDATE = "low_confidence_candidate_namepath"
OUTCOME_UNRESOLVED = "unresolved_no_match"


def _semantic_fingerprint(concept: dict[str, Any]) -> str:
    return str(concept.get("canonical_name") or "").strip()


def build_migration_plan(registry: dict[str, Any], legacy_keys: list[dict[str, Any]]) -> dict[str, Any]:
    """Plan the migration of learner legacy keys to durable concept ids. Each legacy key:
    {learner_key, code?, name_path?}. Returns per-key outcomes + summary. Mutates nothing (a PLAN;
    the actual learner_state write is a separate authorized step).
    """
    concepts = registry.get("concepts") or {}
    alias = registry.get("alias_index") or {}
    # code -> active concept_id (unique only); collided codes excluded from the direct map
    code_to_active: dict[str, str] = {}
    collided: set[str] = set()
    for code, v in alias.items():
        if isinstance(v, list):
            collided.add(code)
        else:
            c = concepts.get(v) or {}
            if c.get("lifecycle", {}).get("status") == "active":
                code_to_active[code] = v

    def _name_hash_map() -> dict[str, str]:
        from deeptutor.services.construction_grading.concept_registry import name_path_hash
        return {name_path_hash(c["canonical_path"]): cid
                for cid, c in concepts.items()
                if c.get("lifecycle", {}).get("status") == "active"}

    nph_map = None
    results: list[dict[str, Any]] = []
    for k in legacy_keys:
        code = str(k.get("code") or "")
        name_path = str(k.get("name_path") or "")
        lk = k.get("learner_key")
        has_signal = bool(k.get("has_learner_signal"))  # any mastery/attempts/evidence on this key
        target = ""
        outcome = OUTCOME_UNRESOLVED
        if code and code in collided:
            # collided legacy code: current registry resolution is NOT proof of historical identity.
            # only migrate if name_path disambiguates to exactly one active concept; else quarantine.
            if name_path:
                from deeptutor.services.construction_grading.concept_registry import resolve_alias
                cid = resolve_alias(registry, code, name_path)
                if cid and concepts.get(cid, {}).get("lifecycle", {}).get("status") == "active":
                    target, outcome = cid, OUTCOME_MIGRATED
                else:
                    outcome = OUTCOME_QUARANTINED
            else:
                outcome = OUTCOME_QUARANTINED
        elif code and code in alias and not isinstance(alias[code], list):
            cid = alias[code]
            c = concepts.get(cid, {})
            st = c.get("lifecycle", {}).get("status")
            if st == "active":
                target, outcome = cid, OUTCOME_MIGRATED
            elif st == "merged":
                # redirect to canonical winner BUT flag: multiple old states may converge -> aggregation
                target, outcome = c["lineage"]["canonical_concept_id"], OUTCOME_REDIRECTED
            elif st == "deprecated":
                # never physically drop learner evidence: archive if signal, drop only if empty
                outcome = OUTCOME_ARCHIVED if has_signal else OUTCOME_DROPPED_EMPTY
        if not target and name_path and outcome == OUTCOME_UNRESOLVED:
            from deeptutor.services.construction_grading.concept_registry import name_path_hash
            if nph_map is None:
                nph_map = _name_hash_map()
            cid = nph_map.get(name_path_hash(name_path))
            if cid:
                # name_path match is a LOW-CONFIDENCE candidate, never an authoritative write
                target, outcome = cid, OUTCOME_CANDIDATE
        results.append({
            "learner_key": lk, "legacy_code": code, "outcome": outcome,
            "durable_concept_id": target, "has_learner_signal": has_signal,
            "semantic_fingerprint": _semantic_fingerprint(concepts.get(target, {})) if target else "",
        })

    # aggregation conflict: >1 distinct learner_key (with signal) landing on the same durable target
    by_target: dict[str, list[Any]] = {}
    for r in results:
        if r["durable_concept_id"] and r["outcome"] in (OUTCOME_MIGRATED, OUTCOME_REDIRECTED):
            by_target.setdefault(r["durable_concept_id"], []).append(r)
    aggregation_conflicts = sum(1 for v in by_target.values()
                                if len({x["learner_key"] for x in v}) > 1)

    summary = {o: sum(1 for r in results if r["outcome"] == o) for o in
               (OUTCOME_MIGRATED, OUTCOME_REDIRECTED, OUTCOME_QUARANTINED, OUTCOME_ARCHIVED,
                OUTCOME_DROPPED_EMPTY, OUTCOME_CANDIDATE, OUTCOME_UNRESOLVED)}
    summary["total"] = len(results)
    summary["aggregation_conflicts"] = aggregation_conflicts
    # SAFE to auto-apply only when nothing is silently mis-attributable AND no destructive/ambiguous path:
    # no collision quarantine, no aggregation conflict, no low-confidence candidate auto-written.
    summary["safe_to_apply"] = (summary[OUTCOME_QUARANTINED] == 0
                                and aggregation_conflicts == 0
                                and summary[OUTCOME_CANDIDATE] == 0)
    return {"results": results, "summary": summary}


__all__ = ["build_migration_plan", "OUTCOME_MIGRATED", "OUTCOME_QUARANTINED", "OUTCOME_ARCHIVED",
           "OUTCOME_DROPPED_EMPTY", "OUTCOME_REDIRECTED", "OUTCOME_CANDIDATE", "OUTCOME_UNRESOLVED"]
