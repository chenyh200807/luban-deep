"""Unified canonical grading-object schema — KnowQL Phase A single authority.

This module is the **one** typed-object authority for Luban grading. It collapses
the pre-existing, drifting grading/scoring/typed-object shapes (eval-inline
``case_grading_artifact.v1``, ``luban.rich_leaf_artifact.v0`` / v3.2 pack scoring
points, ``luban_scoring_point_assets.v0.1``, the M31 governed objective answer key
records, the arbitration ``gold_panel`` labels, ``m35_ai_governed_gold.v1``,
``compact_scoring_artifact.v1`` and the deterministic
``luban_per_question_grading_object.v1``) onto ONE shared core field set so that any
consumer — the grader, a future KnowQL query layer, or the learner brain — reads the
same field contract for an objective / calculation / standard-clause / case point.

Design (governed by ``docs/plan/鲁班knowql/UNIFIED_GRADING_OBJECT_SCHEMA.md``):

* **One name per concept.** ``max_score`` (never ``weight``), ``statement`` (never
  ``canonical_answer`` / ``label`` / ``answer_key``), ``span_hash`` everywhere a
  projection must be proven, ``authority_source`` on every field-bearing object,
  ``hit_status`` for a point's matched state.
* **Single-authority native.** Every grading object and every point carries
  ``authority_source`` ∈ {``official_answer`` | ``textbook_cited`` | ``owner`` |
  ``pending_calibration``}. ``span_hash`` is the machine proof that a field is a
  projection of a cited span, not a new authority. ``official_score_allowed`` is a
  structural ``const False``. Per-point ``max_score`` defaults to ``None`` with
  ``authority_source = pending_calibration`` — the compiler never mints a per-point
  split the official source did not give.
* **Typed variants, not new names.** Objective / calculation / standard_clause / case
  differences live in optional, per-variant fields (``options`` / ``formula_steps`` /
  ``threshold`` / ``flaw_span`` …) on the SAME object — never a parallel schema.

This module is deterministic and pure: no LLM, no network, no DB writes, no release
promotion, no official-score grant. ``validate_grading_object`` is a pure function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any
import unicodedata

SCHEMA_ID = "luban_grading_object.v1"

# ── Canonical authority_source vocabulary (the only allowed values) ──────────────
AUTH_OFFICIAL_ANSWER = "official_answer"
AUTH_TEXTBOOK_CITED = "textbook_cited"
AUTH_OWNER = "owner"
AUTH_PENDING_CALIBRATION = "pending_calibration"
AUTHORITY_SOURCES = frozenset(
    {AUTH_OFFICIAL_ANSWER, AUTH_TEXTBOOK_CITED, AUTH_OWNER, AUTH_PENDING_CALIBRATION}
)

# Authorities that may carry a binding span_hash projection proof.
SPAN_BACKED_AUTHORITIES = frozenset({AUTH_OFFICIAL_ANSWER, AUTH_TEXTBOOK_CITED, AUTH_OWNER})

# ── Canonical question-type family (typed variants share one schema) ─────────────
TYPE_OBJECTIVE = "objective"
TYPE_CALCULATION = "calculation"
TYPE_STANDARD_CLAUSE = "standard_clause"
TYPE_CASE = "case"
QUESTION_TYPE_FAMILY = frozenset(
    {TYPE_OBJECTIVE, TYPE_CALCULATION, TYPE_STANDARD_CLAUSE, TYPE_CASE}
)

# ── Canonical hit_status vocabulary (a point's matched state) ────────────────────
HIT_STATUSES = frozenset({"hit", "partial", "miss", "contradiction", "not_evaluated"})

# Per-point score authority sentinel reused across the codebase.
PENDING_SCORE_AUTHORITY = "pending_calibration_not_official"

# Required core fields every scoring point shares, regardless of variant.
CORE_POINT_FIELDS = (
    "point_id",
    "statement",
    "authority_source",
    "span_hash",
    "max_score",
    "score_authority",
    "hit_status",
)

GRADING_OBJECT_V1_SCHEMA: dict[str, Any] = {
    "schema_id": SCHEMA_ID,
    "type": "object",
    "required": [
        "schema_id",
        "object_id",
        "question_type",
        "official_total_score",
        "official_total_score_authority",
        "authority_source",
        "scoring_points",
    ],
    "properties": {
        "schema_id": {"const": SCHEMA_ID},
        "object_id": {"type": "string"},
        "question_type": {"type": "string", "enum": sorted(QUESTION_TYPE_FAMILY)},
        "official_total_score": {"type": ["number", "null"]},
        "official_total_score_authority": {"const": AUTH_OFFICIAL_ANSWER},
        "authority_source": {"type": "string", "enum": sorted(AUTHORITY_SOURCES)},
        "scoring_points": {"type": "array"},
        # Structural single-authority locks — the object cannot self-declare truth.
        "official_score_allowed": {"const": False},
        "canonical_write_allowed": {"const": False},
    },
    "forbidden_properties": [
        "controlled_default",
        "canonical_truth_written",
        "minted_per_point_score",
        # legacy drift names — must be normalized away, never present on v1.
        "weight",
        "canonical_answer",
        "answer_key",
        "label",
    ],
}


def normalize_span(raw_span: str) -> str:
    """Normalize a source span for stable hashing (matches rich_leaf_artifacts)."""
    normalized = unicodedata.normalize("NFKC", str(raw_span or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\|?\s*:?-{3,}:?\s*(?=\||$)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def span_hash(raw_span: str) -> str:
    """SHA-256 over the normalized span — the projection (not new-authority) proof."""
    return hashlib.sha256(normalize_span(raw_span).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GradingPoint:
    """One canonical scoring point. Variant fields are optional and additive."""

    point_id: str
    statement: str
    authority_source: str
    span_hash: str
    max_score: float | None = None
    score_authority: str = PENDING_SCORE_AUTHORITY
    hit_status: str = "not_evaluated"
    required_terms: list[str] = field(default_factory=list)
    term_provenance: list[dict[str, Any]] = field(default_factory=list)
    # objective variant
    options: dict[str, str] | None = None
    correct_keys: list[str] | None = None
    # calculation variant
    formula_steps: list[dict[str, Any]] | None = None
    expected_final_value: dict[str, Any] | None = None
    # standard_clause variant
    threshold: dict[str, Any] | None = None
    clause_subject: str | None = None
    # case variant (flaw_correction / exceptions / enumeration …)
    sub_type: str | None = None
    flaw_span: str | None = None
    correction_span: str | None = None
    pairing: str | None = None
    base_rule: str | None = None
    exception_items: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "point_id": self.point_id,
            "statement": self.statement,
            "authority_source": self.authority_source,
            "span_hash": self.span_hash,
            "max_score": self.max_score,
            "score_authority": self.score_authority,
            "hit_status": self.hit_status,
            "required_terms": list(self.required_terms),
            "term_provenance": list(self.term_provenance),
        }
        for key in (
            "options",
            "correct_keys",
            "formula_steps",
            "expected_final_value",
            "threshold",
            "clause_subject",
            "sub_type",
            "flaw_span",
            "correction_span",
            "pairing",
            "base_rule",
            "exception_items",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class GradingObject:
    """One canonical grading object for a single question (any type family)."""

    object_id: str
    question_type: str
    official_total_score: float | None
    scoring_points: list[dict[str, Any]]
    authority_source: str = AUTH_OFFICIAL_ANSWER
    official_total_score_authority: str = AUTH_OFFICIAL_ANSWER
    stem: str | None = None
    official_analysis: str | None = None
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    official_score_allowed: bool = False
    canonical_write_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": SCHEMA_ID,
            "object_id": self.object_id,
            "question_type": self.question_type,
            "official_total_score": self.official_total_score,
            "official_total_score_authority": self.official_total_score_authority,
            "authority_source": self.authority_source,
            "stem": self.stem,
            "official_analysis": self.official_analysis,
            "source_refs": list(self.source_refs),
            "scoring_points": list(self.scoring_points),
            "official_score_allowed": self.official_score_allowed,
            "canonical_write_allowed": self.canonical_write_allowed,
        }


def _validate_point(point: Any, *, index: int) -> list[str]:
    """Deterministic per-point checks. Returns blockers (empty = ok)."""
    label = f"point[{index}]"
    if not isinstance(point, dict):
        return [f"point_not_object:{label}"]
    pid = str(point.get("point_id") or "").strip()
    label = pid or label
    blockers: list[str] = []

    for required in CORE_POINT_FIELDS:
        if required not in point:
            blockers.append(f"point_missing_core_field:{required}:{label}")

    for forbidden in GRADING_OBJECT_V1_SCHEMA["forbidden_properties"]:
        if forbidden in point:
            blockers.append(f"point_forbidden_drift_field:{forbidden}:{label}")

    authority = str(point.get("authority_source") or "")
    if authority and authority not in AUTHORITY_SOURCES:
        blockers.append(f"point_unknown_authority_source:{authority}:{label}")
    if not authority:
        blockers.append(f"point_missing_authority_source:{label}")

    # span_hash projection proof: a span-backed authority must carry a span_hash
    # consistent with its own statement; a non-projection authority must not claim one.
    declared_hash = point.get("span_hash")
    statement = str(point.get("statement") or "")
    if authority in SPAN_BACKED_AUTHORITIES:
        if not declared_hash:
            blockers.append(f"point_missing_span_hash:{label}")
        elif declared_hash != span_hash(statement):
            blockers.append(f"point_span_hash_mismatch:{label}")
    elif authority == AUTH_PENDING_CALIBRATION and declared_hash:
        blockers.append(f"pending_point_must_not_claim_span_hash:{label}")

    # must-not-mint: a point may not self-grant a per-point official score.
    score = point.get("max_score")
    score_authority = str(point.get("score_authority") or "")
    if score is not None and score_authority not in {
        PENDING_SCORE_AUTHORITY,
        AUTH_OFFICIAL_ANSWER,
    }:
        blockers.append(f"point_score_without_valid_authority:{label}")
    if score is not None and score_authority == PENDING_SCORE_AUTHORITY:
        blockers.append(f"pending_point_must_not_carry_score:{label}")

    hit_status = str(point.get("hit_status") or "")
    if hit_status and hit_status not in HIT_STATUSES:
        blockers.append(f"point_unknown_hit_status:{hit_status}:{label}")

    # unsourced terms must honestly carry null chunk_id — never a faked anchor.
    for prov in point.get("term_provenance") or []:
        if isinstance(prov, dict):
            if prov.get("anchor_verified") is False and prov.get("chunk_id") is not None:
                blockers.append(f"unsourced_term_must_have_null_chunk:{label}")
    return blockers


def validate_grading_object(obj: Any) -> list[str]:
    """Return blockers for a unified grading object (empty list = valid).

    Deterministic and pure. Rejects any object that: is missing a canonical
    ``authority_source``; carries a forbidden drift field (``weight`` /
    ``canonical_answer`` / ``answer_key`` / ``label`` …); self-declares official
    score authority; or has a point whose span-backed authority is missing or
    inconsistent with its ``span_hash`` projection proof.
    """
    if not isinstance(obj, dict):
        return ["object_not_dict"]

    blockers: list[str] = []

    if obj.get("schema_id") != SCHEMA_ID:
        blockers.append("schema_id_mismatch")

    for required in GRADING_OBJECT_V1_SCHEMA["required"]:
        if required not in obj:
            blockers.append(f"missing_required:{required}")

    for forbidden in GRADING_OBJECT_V1_SCHEMA["forbidden_properties"]:
        if forbidden in obj:
            blockers.append(f"forbidden_drift_field:{forbidden}")

    if obj.get("official_score_allowed") is not False:
        blockers.append("official_score_allowed_must_be_false")
    if obj.get("canonical_write_allowed") not in (False, None):
        blockers.append("canonical_write_allowed_must_be_false")

    question_type = str(obj.get("question_type") or "")
    if question_type and question_type not in QUESTION_TYPE_FAMILY:
        blockers.append(f"unknown_question_type:{question_type}")

    authority = str(obj.get("authority_source") or "")
    if not authority:
        blockers.append("missing_authority_source")
    elif authority not in AUTHORITY_SOURCES:
        blockers.append(f"unknown_authority_source:{authority}")

    if obj.get("official_total_score_authority") != AUTH_OFFICIAL_ANSWER:
        blockers.append("total_score_authority_not_official")

    points = obj.get("scoring_points")
    if not isinstance(points, list):
        blockers.append("scoring_points_not_list")
    else:
        for index, point in enumerate(points):
            blockers.extend(_validate_point(point, index=index))

    return blockers
