"""Objective answer-key source classifier + conflict detector (M25-G, fat skill).

Deterministic gate that classifies a source descriptor into a release-authority verdict and
detects cross-source answer_key conflicts. The LLM may organize/explain sources; this module
makes the authority call. Rules (master plan §0.25.3/§0.25.4 red lines):

  * governed production registry (write-owned, versioned, provenance, REAL_EXAM) -> can be release authority
  * eval fixture (provenance but not a governed registry)                        -> real_source_candidate
  * official_answer only / no provenance                                         -> seed_only
  * RAG chunk inferred answer                                                     -> rejected (never scoring authority)
  * model / council vote                                                          -> rejected
  * runtime grading OUTPUT (derivative)                                           -> rejected as source
"""
from __future__ import annotations

from typing import Any

REJECTED_KINDS = {"rag_chunk", "model_vote", "council_vote", "runtime_output", "llm_inferred"}


def classify_source(desc: dict[str, Any]) -> dict[str, Any]:
    """Return {verdict, release_authority, reason} for one source descriptor (deterministic)."""
    kind = str(desc.get("kind") or "").strip()
    has_answer_key = bool(desc.get("has_answer_key"))
    has_provenance = bool(desc.get("has_provenance"))
    governed = bool(desc.get("governed_registry"))  # write-owned, versioned, content_hash lineage
    is_fixture = bool(desc.get("is_eval_fixture"))
    official_only = bool(desc.get("official_answer_only"))

    if kind in REJECTED_KINDS:
        return {"verdict": "rejected", "release_authority": False,
                "reason": f"{kind} can never be objective scoring authority"}
    if not has_answer_key:
        return {"verdict": "rejected", "release_authority": False, "reason": "no answer_key"}
    if governed and has_provenance:
        return {"verdict": "release_authority_candidate", "release_authority": True,
                "reason": "governed production registry with provenance + version lineage"}
    if is_fixture and has_provenance:
        return {"verdict": "real_source_candidate", "release_authority": False,
                "reason": "real-source-backed eval fixture, not a governed registry"}
    if official_only or not has_provenance:
        return {"verdict": "seed_only", "release_authority": False,
                "reason": "official_answer/seed without governed provenance"}
    return {"verdict": "candidate", "release_authority": False, "reason": "unclassified — defaults to candidate"}


def _norm_key(value: Any) -> str:
    return "".join(sorted({c for c in str(value or "").upper() if c.isalpha()}))


def detect_conflicts(rows_by_source: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Cross-source answer_key reconciliation. NEVER averages keys; emits conflict/corroborated queues."""
    by_qid: dict[str, dict[str, str]] = {}
    by_stem: dict[str, dict[str, str]] = {}
    for source, rows in rows_by_source.items():
        for r in rows:
            qid = str(r.get("question_id") or "").strip()
            key = _norm_key(r.get("answer_key") or r.get("correct_answer"))
            stem_hash = str(r.get("stem_hash") or "").strip()
            if qid:
                by_qid.setdefault(qid, {})[source] = key
            if stem_hash:
                by_stem.setdefault(stem_hash, {})[source] = key
    corroborated, conflicts = [], []
    for qid, keys in by_qid.items():
        distinct = set(keys.values())
        if len(keys) >= 2:
            (corroborated if len(distinct) == 1 else conflicts).append(
                {"question_id": qid, "keys_by_source": keys,
                 "status": "corroborated" if len(distinct) == 1 else "conflict"})
    return {"corroborated": corroborated, "conflicts": conflicts,
            "conflict_count": len(conflicts), "corroborated_count": len(corroborated),
            "averaged_any_key": False}
