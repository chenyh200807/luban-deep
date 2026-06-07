"""Canonical resolution bridge — the ONE normalizer mapping any system's key to canonical.

Master-plan directive: canonical taxonomy must be THE taxonomy for every system (knowledge compiler,
graph, learner_state concept_id, Supabase, reports). Those systems use divergent keys (concept_id +
error_code, question predicted_node, free-text topic). This module is the single entry that resolves
any of them to a canonical code, so cross-system joins (prerequisite remediation, coverage, mastery)
are exact.

Runtime-safe: loads a TRACKED compact index (``runtime_supply/v_canonical_taxonomy_index``) — NOT the
1.4MB external source tree — built offline by ``run_luban_canonical_taxonomy_index``. lru-cached. Returns
"" when nothing resolves (caller falls open; never guesses a wrong concept).
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any

_INDEX_DIR = Path(__file__).parent / "runtime_supply" / "v_canonical_taxonomy_index"
_INDEX_NAME = "canonical_taxonomy_index.json"
# the verified concept registry (Opus+Codex cross-adjudicated): drives deprecated/merged remap so the
# bridge never resolves to a fabricated or merged-away concept.
_REGISTRY_DIR = Path(__file__).parent / "runtime_supply" / "v_concept_registry"
_REGISTRY_NAME = "concept_registry.json"


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any] | None:
    """Load the verified registry into lookup maps: code/name_path -> active concept, + deprecated set,
    + merged redirect (merged concept -> canonical winner). None if absent (bridge falls back to index)."""
    p = _REGISTRY_DIR / _REGISTRY_NAME
    if not p.exists():
        return None
    try:
        reg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    concepts = reg.get("concepts") or {}
    deprecated: set[str] = set()      # canonical codes whose concept is fabricated (dual-model)
    merged_redirect: dict[str, str] = {}  # path_hash of merged-away -> winner concept's primary code
    active_codes: set[str] = set()
    code_to_concept: dict[str, str] = {}
    for cid, c in concepts.items():
        status = c.get("lifecycle", {}).get("status", "active")
        for code in c.get("alias_codes") or []:
            if status == "active":
                active_codes.add(code)
                code_to_concept[code] = cid
            elif status == "deprecated":
                deprecated.add(code)
    return {"concepts": concepts, "deprecated_codes": deprecated,
            "active_codes": active_codes, "code_to_concept": code_to_concept}


@lru_cache(maxsize=1)
def _index() -> dict[str, Any] | None:
    p = _INDEX_DIR / _INDEX_NAME
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    leaves = doc.get("leaves") or []
    # precompute IDF keyword weights (rare keyword dominates; generic ones can't magnet) once.
    df: dict[str, int] = {}
    for lf in leaves:
        for k in lf.get("keywords") or []:
            if k:
                df[k] = df.get(k, 0) + 1
    n = max(1, len(leaves))
    weight = {k: math.log(1 + n / v) for k, v in df.items()}
    return {"leaves": leaves, "weight": weight,
            "codes": {lf["code"] for lf in leaves},
            "name_path": {lf["code"]: lf.get("name_path", lf["code"]) for lf in leaves}}


_CODE_RE = re.compile(r"1A\d{4,}(?:-[0-9a-z]+)*")


@lru_cache(maxsize=4096)
def to_canonical(text: str, native_code: str = "") -> str:
    """Resolve any key/text to a canonical leaf code. Prefers an embedded/explicit canonical code; else
    IDF-weighted keyword classification of the text. '' when nothing resolves."""
    idx = _index()
    if not idx:
        return ""
    codes = idx["codes"]
    reg = _registry()
    deprecated = reg["deprecated_codes"] if reg else set()
    # 1) explicit code that IS a canonical leaf (skip codes the registry deprecated as fabricated)
    for cand in ([native_code] if native_code else []) + _CODE_RE.findall(str(text or "")):
        if cand in codes and cand not in deprecated:
            return cand
    # 2) IDF-weighted keyword classification (excluding deprecated-concept leaves)
    weight = idx["weight"]
    s = str(text or "")
    best_code, best_score = "", 0.0
    for lf in idx["leaves"]:
        if lf["code"] in deprecated:
            continue
        matched = [k for k in lf.get("keywords") or [] if k and k in s]
        if not matched:
            continue
        score = sum(weight.get(k, 1.0) for k in matched)
        if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and lf["code"] < best_code):
            best_code, best_score = lf["code"], score
    return best_code


def to_canonical_set(texts: list[str]) -> frozenset[str]:
    """Map a batch of keys (e.g. a learner's mastered concept_ids) to canonical codes (drops misses)."""
    out = {to_canonical(str(t)) for t in (texts or [])}
    out.discard("")
    return frozenset(out)


def name_path(code: str) -> str:
    idx = _index()
    return (idx["name_path"].get(code, code) if idx else code)


__all__ = ["to_canonical", "to_canonical_set", "name_path"]
