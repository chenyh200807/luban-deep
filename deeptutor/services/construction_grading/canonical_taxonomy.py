"""Canonical 2026 taxonomy — the single authoritative node spine for the Luban knowledge system.

The 2026 exam taxonomy (``FINAL_CLEANED_TAXONOMY2026.json``) is an L1-L6 tree: ~3735 nodes, 2393 L6
leaves, keyword-rich at L5/L6. It is the ONE spine every content source (textbook, standards, lectures,
questions) must pin to — they were each tagged to different, inconsistent code systems and cannot be
joined by their native codes alone.

This module loads the tree and classifies a content unit onto a canonical leaf with a deterministic,
accuracy-first strategy:
  1. ANCHOR by native code — if the unit carries a node_code that IS (or is an ancestor of) canonical
     nodes, restrict the search to that subtree's leaves. This avoids cross-area keyword false
     positives (a card mentioning "水泥" never lands in a 安全 leaf).
  2. REFINE by keyword — within the candidate leaves, pick the one whose keywords best hit the unit's
     text (CJK-substring hits). Deterministic tie-break: more hits, then deeper level, then code.
  3. report method + confidence so a downstream LLM pass handles only the genuinely ambiguous tail.

Pure / hermetic: no I/O beyond reading the taxonomy JSON path it is given.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def node_uuid(name_path: str) -> str:
    """Stable, content-derived node identity (decoupled from the non-unique `code`).

    The canonical source reuses codes across unrelated subtrees (e.g. 1A413061-01 = 15 different
    concepts) and `id = code#ordinal` is positional (a recompile reorders it), so neither is a safe
    persistence key for learner mastery / weak-point anchors. The full name_path is the disambiguating
    identity: same concept (same path) -> same uuid across recompiles (idempotent); same code under a
    different branch -> different path -> different uuid (disambiguated)."""
    return "n_" + hashlib.sha256(str(name_path or "").encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CanonNode:
    code: str
    name: str
    level: int
    name_path: str
    keywords: tuple[str, ...]

    @property
    def uuid(self) -> str:
        return node_uuid(self.name_path)


@dataclass(frozen=True)
class Classification:
    leaf_code: str            # "" if unclassified
    method: str               # "anchor+keyword" | "keyword" | "anchor_only" | "unclassified"
    confidence: float         # 0.0-1.0
    keyword_hits: int


class CanonicalTaxonomy:
    """Loaded canonical tree + the deterministic classifier. Build once, classify many."""

    def __init__(self, nodes: list[CanonNode], children: dict[str, list[str]], by_code: dict[str, CanonNode]):
        self._nodes = nodes
        self._children = children
        self._by_code = by_code
        # leaves that can be classification targets = childless nodes carrying keywords.
        # (structural rule; the legacy "level in (5, 6)" magic numbers broke on the
        # book-derived rebuild, whose evidence leaves sit at depths 2-5)
        self._leaf_codes = [n.code for n in nodes if n.keywords and not children.get(n.code)]
        self._leaf_set = set(self._leaf_codes)
        # keyword specificity weight (IDF): a keyword shared by many leaves (e.g. 结构/管理/要求) is a
        # weak signal and must not turn its leaf into a false-positive magnet; a rare keyword is strong.
        df: dict[str, int] = {}
        for c in self._leaf_codes:
            for k in self._by_code[c].keywords:
                if k:
                    df[k] = df.get(k, 0) + 1
        n_leaves = max(1, len(self._leaf_codes))
        self._kw_weight = {k: math.log(1 + n_leaves / v) for k, v in df.items()}

    # ----- construction -----
    @classmethod
    def load(cls, path: str | Path) -> CanonicalTaxonomy:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        nodes: list[CanonNode] = []
        children: dict[str, list[str]] = {}
        by_code: dict[str, CanonNode] = {}

        def walk(raw: dict[str, Any], trail: list[str]) -> None:
            code = str(raw.get("code") or "")
            name = str(raw.get("name") or "")
            name_path = " > ".join(t for t in (trail + [name]) if t)
            lvl = raw.get("level")
            node = CanonNode(code=code, name=name, level=int(lvl) if isinstance(lvl, int) else 0,
                             name_path=name_path, keywords=tuple(str(k) for k in (raw.get("keywords") or [])))
            if code:
                nodes.append(node)
                by_code[code] = node
            kids = [c for c in (raw.get("children") or []) if isinstance(c, dict)]
            if code:
                children[code] = [str(c.get("code") or "") for c in kids if c.get("code")]
            for c in kids:
                walk(c, trail + [name])

        for root in doc.get("outline_structure", []):
            if isinstance(root, dict):
                walk(root, [])
        return cls(nodes, children, by_code)

    # ----- queries -----
    def node(self, code: str) -> CanonNode | None:
        return self._by_code.get(str(code or ""))

    def leaf_codes(self) -> list[str]:
        return list(self._leaf_codes)

    def name_path(self, code: str) -> str:
        n = self._by_code.get(str(code or ""))
        return n.name_path if n else str(code or "")

    def _subtree_leaves(self, code: str) -> list[str]:
        """All classification leaves at or under ``code`` (the code's own subtree)."""
        if code not in self._by_code:
            return []
        out: list[str] = []
        stack = [code]
        while stack:
            cur = stack.pop()
            if cur in self._leaf_set:
                out.append(cur)
            stack.extend(self._children.get(cur, []))
        return out

    def _best_by_keyword(self, text: str, candidates: list[str]) -> tuple[str, int, float]:
        """The candidate leaf whose keywords best hit ``text``, scored by IDF weight (rare keywords
        dominate, generic ones can't magnet). Tie-break: score, then deeper level, then code. Returns
        (code, raw_hit_count, weighted_score)."""
        best_code, best_score, best_level, best_hits = "", 0.0, -1, 0
        for code in candidates:
            node = self._by_code[code]
            matched = [k for k in node.keywords if k and k in text]
            if not matched:
                continue
            score = sum(self._kw_weight.get(k, 1.0) for k in matched)
            better = (score > best_score + 1e-9
                      or (abs(score - best_score) <= 1e-9 and node.level > best_level)
                      or (abs(score - best_score) <= 1e-9 and node.level == best_level and code < best_code))
            if better:
                best_code, best_score, best_level, best_hits = code, score, node.level, len(matched)
        return best_code, best_hits, best_score

    def classify(self, text: str, *, native_code: str = "") -> Classification:
        """Classify a content unit onto a canonical leaf. ``native_code`` (the source's own node_code,
        possibly from a different code system) anchors the search region when it maps into this tree."""
        text = str(text or "")
        nc = str(native_code or "").strip()
        anchor_leaves = self._subtree_leaves(nc) if nc in self._by_code else []
        # a match resting only on generic (low-IDF) keywords is weak -> lower confidence -> QA/LLM tail.
        weak = 0.7  # weighted-score floor below which even a hit is "low confidence"

        if anchor_leaves:
            code, hits, score = self._best_by_keyword(text, anchor_leaves)
            if code:
                conf = 0.9 if (hits >= 2 and score >= weak) else 0.75 if score >= weak else 0.55
                return Classification(code, "anchor+keyword", conf, hits)
            # native code is valid but keywords didn't refine -> anchor to its first/shallowest leaf.
            return Classification(sorted(anchor_leaves)[0], "anchor_only", 0.5, 0)

        code, hits, score = self._best_by_keyword(text, self._leaf_codes)
        if code:
            conf = 0.7 if (hits >= 2 and score >= weak) else 0.45 if score >= weak else 0.3
            return Classification(code, "keyword", conf, hits)
        return Classification("", "unclassified", 0.0, 0)


__all__ = ["CanonNode", "Classification", "CanonicalTaxonomy"]
