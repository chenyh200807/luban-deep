"""Compiled Context fat skill (M26): the ONE authority that assembles ``LubanContextPack``.

Master plan §0.26.4 mandates a single Compiled Context Pack builder that every runtime surface
reuses (TutorBot Q&A, case/objective runtime grading, RAG citation, Learning Brain next action).
This module is that builder. It is a PURE organizer over already-resolved upstream authority
outputs — it calls no LLM, performs no network I/O, and makes no grading decision. It only:

  * normalizes the six canonical context blocks (§0.26.4 minimum field set),
  * computes ``diagnostic_policy`` DETERMINISTICALLY from resolution status + signed availability,
  * stamps ``provenance`` hashes so downstream consumers can audit what was compiled.

Authority split (§0.26.3):
  * Upstream resolvers / signed registries decide identity, answer_key, rubric — passed in as
    ``resolution``. This builder never invents an answer_key, never upgrades a candidate to a
    release, never lets retrieval/LLM content become signed truth.
  * The LLM downstream (open-world diagnostic, adjudicator explanation) only ORGANIZES / DIAGNOSES
    over the pack; ``diagnostic_policy`` here is the deterministic gate that says whether an
    official score is even allowed.

Thin wrappers (``/api/v1/ws``, TutorBot, ``deep_question``) only pass request context, flags,
cohort, and append the pack to their packet. No wrapper assembles a second context shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

SCHEMA_VERSION = "luban_context_pack.v1"

# Resolution status vocabulary (from the resolver / registry authority).
STATUS_RESOLVED = "resolved"        # canonical question identity is known
STATUS_CANDIDATE = "candidate"      # identity/answer is a candidate, NOT release truth
STATUS_UNRESOLVED = "unresolved"    # not-in-bank / user-pasted / open-world

# Registry grade vocabulary (signed-availability levels).
RELEASE_GRADES = {"release_candidate", "published"}
CANDIDATE_GRADES = {"candidate", "real_source_candidate", "shadow", "dry_run"}

# Default token budget caps. Efficiency is a CONSTRAINT, never the goal (§0.26.4 budget_policy).
DEFAULT_SOURCE_TOKENS = 1800
DEFAULT_RUBRIC_TOKENS = 900
DEFAULT_LEARNER_TOKENS = 600


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _norm_status(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in {STATUS_RESOLVED, STATUS_CANDIDATE, STATUS_UNRESOLVED}:
        return s
    if s in {"", "open_world", "not_in_bank", "unknown", "none"}:
        return STATUS_UNRESOLVED
    if s in CANDIDATE_GRADES:
        return STATUS_CANDIDATE
    return STATUS_RESOLVED


@dataclass(frozen=True)
class LubanContextPack:
    """Unified, provenance-rich, scoped context reused by every runtime surface (§0.26.4)."""

    question_context: dict[str, Any]
    source_context: dict[str, Any]
    rubric_context: dict[str, Any]
    learner_context: dict[str, Any]
    diagnostic_policy: dict[str, Any]
    budget_policy: dict[str, Any]
    provenance: dict[str, Any]
    schema_version: str = SCHEMA_VERSION
    surfaces_supported: tuple[str, ...] = field(
        default=("tutorbot", "runtime_grading", "rag_citation", "learning_brain")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "question_context": self.question_context,
            "source_context": self.source_context,
            "rubric_context": self.rubric_context,
            "learner_context": self.learner_context,
            "diagnostic_policy": self.diagnostic_policy,
            "budget_policy": self.budget_policy,
            "provenance": self.provenance,
            "surfaces_supported": list(self.surfaces_supported),
        }

    @property
    def official_score_allowed(self) -> bool:
        return bool(self.diagnostic_policy.get("official_score_allowed"))

    @property
    def status(self) -> str:
        return str(self.question_context.get("status") or STATUS_UNRESOLVED)


def _question_context(resolution: dict[str, Any], status: str) -> dict[str, Any]:
    options = resolution.get("options")
    has_answer_key = bool(str(resolution.get("answer_key") or "").strip())
    has_rubric = bool(resolution.get("rubric"))
    return {
        "status": status,
        "question_id": str(resolution.get("question_id") or "").strip(),
        "question_type": str(resolution.get("question_type") or "").strip(),
        "stem": str(resolution.get("stem") or resolution.get("question_text") or "").strip(),
        "options": options if isinstance(options, (dict, list)) else {},
        "registry_status": str(resolution.get("registry_status") or "").strip().lower(),
        "answer_key_available": has_answer_key,
        "rubric_available": has_rubric,
        "is_historical_exam": bool(resolution.get("is_historical_exam")),
    }


def _source_context(
    resolution: dict[str, Any],
    retrieval_sources: list[dict[str, Any]] | None,
    budget_tokens: int,
) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Signed/compiled source refs carried by the resolution (authority side).
    for ref in list(resolution.get("source_refs") or []):
        if not isinstance(ref, dict):
            ref = {"ref": str(ref)}
        key = _sha16(_canonical(ref))
        if key in seen:
            continue
        seen.add(key)
        refs.append({**ref, "provenance_kind": ref.get("provenance_kind") or "compiled_source_ref"})
    # Retrieval-only sources (RAG/KB v5) — NEVER an answer_key, retrieval/context only.
    retrieval_refs: list[dict[str, Any]] = []
    for src in list(retrieval_sources or []):
        if not isinstance(src, dict):
            continue
        retrieval_refs.append({
            "ref": src.get("id") or src.get("chunk_id") or src.get("source_id"),
            "source_table": src.get("source_table"),
            "title": src.get("title"),
            "source_span": src.get("source_span"),
            "content_hash": src.get("content_hash"),
            "score": src.get("score") or src.get("score_final"),
            "provenance_kind": "retrieval_only",
            "is_answer_key": False,
        })
    return {
        "compiled_source_refs": refs,
        "retrieval_refs": retrieval_refs,
        "retrieval_is_grading_authority": False,
        "budget_tokens": budget_tokens,
    }


def _rubric_context(resolution: dict[str, Any], budget_tokens: int) -> dict[str, Any]:
    rubric = resolution.get("rubric")
    return {
        "rubric": rubric if isinstance(rubric, (dict, list)) else None,
        "required_terms": list(resolution.get("required_terms") or []),
        "list_rules": resolution.get("list_rules"),
        "spec": resolution.get("spec"),
        "calc_policy": resolution.get("calc_policy"),
        "risk_flags": list(resolution.get("risk_flags") or []),
        "rubric_signed": str(resolution.get("registry_status") or "").strip().lower() in RELEASE_GRADES
        and bool(rubric),
        # node-resolution focus metadata (textbook lane): how a coarse node was narrowed for this turn.
        "node_card_total": resolution.get("node_card_total"),
        "selected_card_count": resolution.get("selected_card_count"),
        "selection_mode": resolution.get("selection_mode"),
        "selected_taxonomy_paths": resolution.get("selected_taxonomy_paths"),
        "budget_tokens": budget_tokens,
    }


def _learner_context(learner_context: dict[str, Any] | None, budget_tokens: int) -> dict[str, Any]:
    lc = learner_context if isinstance(learner_context, dict) else {}
    return {
        "personalization_context_pack": lc.get("personalization_context_pack") or lc.get("pcp") or {},
        "recent_evidence": list(lc.get("recent_evidence") or [])[:10],
        "active_training_intent": lc.get("active_training_intent") or lc.get("training_intent") or "",
        "is_second_memory_authority": False,  # LB claim lifecycle is the only learner-truth authority
        "budget_tokens": budget_tokens,
    }


def _diagnostic_policy(resolution: dict[str, Any], status: str) -> dict[str, Any]:
    registry_status = str(resolution.get("registry_status") or "").strip().lower()
    has_answer_key = bool(str(resolution.get("answer_key") or "").strip())
    has_rubric = bool(resolution.get("rubric"))
    has_signed_authority = (has_answer_key or has_rubric) and registry_status in RELEASE_GRADES
    is_release_grade = registry_status in RELEASE_GRADES
    is_candidate_grade = registry_status in CANDIDATE_GRADES

    official_score_allowed = (
        status == STATUS_RESOLVED and has_signed_authority and is_release_grade
    )
    # release_candidate => controlled official; published => full official; else no official.
    controlled_official = official_score_allowed and registry_status == "release_candidate"

    if official_score_allowed:
        needs_review_reason = ""
    elif status == STATUS_CANDIDATE or is_candidate_grade:
        needs_review_reason = "candidate_not_release_truth"
    elif status == STATUS_UNRESOLVED:
        needs_review_reason = "not_in_bank_open_world"
    else:
        needs_review_reason = "no_signed_authority"

    work_order_needed = status in {STATUS_UNRESOLVED, STATUS_CANDIDATE} and not official_score_allowed
    return {
        "official_score_allowed": official_score_allowed,
        "controlled_official": controlled_official,
        "unverified_diagnostic_allowed": not official_score_allowed,
        "needs_review_reason": needs_review_reason,
        "answer_key_authority": "signed_registry_only",
        "llm_may_change_answer_key": False,
        "retrieval_may_become_answer_key": False,
        "candidate_work_order": {
            "needed": work_order_needed,
            "kind": "open_world_compiler_candidate"
            if status == STATUS_UNRESOLVED
            else "candidate_promotion_review",
            "promote_to_release": False,
        },
    }


def _budget_policy(budget: dict[str, Any] | None) -> dict[str, Any]:
    b = budget if isinstance(budget, dict) else {}
    return {
        "source_tokens": int(b.get("source_tokens") or DEFAULT_SOURCE_TOKENS),
        "rubric_tokens": int(b.get("rubric_tokens") or DEFAULT_RUBRIC_TOKENS),
        "learner_tokens": int(b.get("learner_tokens") or DEFAULT_LEARNER_TOKENS),
        "efficiency_is_constraint_not_goal": True,
    }


def build_luban_context_pack(
    *,
    resolution: dict[str, Any],
    retrieval_sources: list[dict[str, Any]] | None = None,
    learner_context: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    supply_bundle_hash: str | None = None,
    answer_key_manifest_hash: str | None = None,
) -> LubanContextPack:
    """Assemble the ONE ``LubanContextPack`` from already-resolved authority inputs.

    ``resolution`` is the resolver/registry authority output (status, identity, signed answer_key /
    rubric availability, registry grade, compiled source refs). This builder organizes; it never
    decides correctness or upgrades grade. The same pack shape covers objective, case,
    retrieval-only, and open-world.
    """
    if not isinstance(resolution, dict):
        raise TypeError("resolution must be a dict from the resolver authority")

    status = _norm_status(resolution.get("status"))
    bp = _budget_policy(budget)

    question_block = _question_context(resolution, status)
    source_block = _source_context(resolution, retrieval_sources, bp["source_tokens"])
    rubric_block = _rubric_context(resolution, bp["rubric_tokens"])
    learner_block = _learner_context(learner_context, bp["learner_tokens"])
    policy_block = _diagnostic_policy(resolution, status)

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "resolution_status": status,
        "registry_status": question_block["registry_status"],
        "supply_bundle_hash": supply_bundle_hash or "",
        "answer_key_manifest_hash": answer_key_manifest_hash or "",
        "kb_refs_hash": _sha16(_canonical(source_block["retrieval_refs"])),
        "compiled_source_hash": _sha16(_canonical(source_block["compiled_source_refs"])),
        "learner_pack_hash": _sha16(_canonical(learner_block["personalization_context_pack"])),
        "no_official_answer_leak": not (
            status != STATUS_RESOLVED and question_block["answer_key_available"]
        ),
    }
    provenance["pack_hash"] = _sha16(
        _canonical([question_block, source_block, rubric_block, policy_block])
    )

    return LubanContextPack(
        question_context=question_block,
        source_context=source_block,
        rubric_context=rubric_block,
        learner_context=learner_block,
        diagnostic_policy=policy_block,
        budget_policy=bp,
        provenance=provenance,
    )


def build_pack_from_question_context(
    question_context: dict[str, Any],
    *,
    learner_context: dict[str, Any] | None = None,
    retrieval_sources: list[dict[str, Any]] | None = None,
    governed_registry_status: str = "",
) -> LubanContextPack:
    """Convenience entry shared by runtime surfaces (TutorBot / runtime grading / Learning Brain).

    Maps a runtime ``question_context`` into the resolver-shaped ``resolution`` and delegates to the
    ONE builder, so every surface attaches the SAME pack shape + policy instead of hand-rolling its
    own context. Pure mapping; never decides correctness.

    AUTHORITY HARDENING (F1, master plan §0.26.3): a runtime ``question_context`` is CLIENT-INFLUENCED
    (it can arrive verbatim from the ``/api/v1/ws`` frame). It therefore can NOT carry governed
    release authority. A context-supplied ``registry_status`` is IGNORED here — only a TRUSTED server
    caller may grant release-grade authority by passing ``governed_registry_status`` explicitly (which
    must itself originate from a server-side governed resolver, never from the inbound context). This
    makes ``official_score_allowed`` impossible to flip by injecting ``registry_status`` into the
    question context. Server-resolved authority should call ``build_luban_context_pack`` directly.
    """
    qc = question_context if isinstance(question_context, dict) else {}
    # evidence_refs on a runtime question_context are retrieval-only refs (RAG/KB), never answer keys.
    evidence_refs = retrieval_sources
    if evidence_refs is None:
        evidence_refs = [
            r for r in list(qc.get("evidence_refs") or []) if isinstance(r, dict)
        ]
    status = qc.get("status")
    if status is None:
        status = STATUS_RESOLVED if str(qc.get("question_id") or "").strip() else STATUS_UNRESOLVED
    resolution = {
        "status": status,
        "question_id": qc.get("question_id") or qc.get("id"),
        "question_type": qc.get("question_type") or qc.get("type"),
        "stem": qc.get("stem") or qc.get("question_stem") or qc.get("question_text"),
        "options": qc.get("options"),
        "answer_key": qc.get("answer_key"),
        # Trusted server authority only; context-supplied registry_status is NOT honored (F1 guard).
        "registry_status": str(governed_registry_status or "").strip(),
        "rubric": qc.get("rubric"),
        "required_terms": qc.get("required_terms"),
        "risk_flags": qc.get("risk_flags"),
        "source_refs": qc.get("source_refs"),
        "is_historical_exam": qc.get("is_historical_exam"),
        # node-resolution focus metadata (textbook lane) — carried through so consumers see how a
        # coarse syllabus node was narrowed to the turn's sub-topic.
        "node_card_total": qc.get("node_card_total"),
        "selected_card_count": qc.get("selected_card_count"),
        "selection_mode": qc.get("selection_mode"),
        "selected_taxonomy_paths": qc.get("selected_taxonomy_paths"),
    }
    return build_luban_context_pack(
        resolution=resolution,
        retrieval_sources=evidence_refs,
        learner_context=learner_context,
    )


__all__ = [
    "LubanContextPack",
    "build_luban_context_pack",
    "build_pack_from_question_context",
    "SCHEMA_VERSION",
    "STATUS_RESOLVED",
    "STATUS_CANDIDATE",
    "STATUS_UNRESOLVED",
]
