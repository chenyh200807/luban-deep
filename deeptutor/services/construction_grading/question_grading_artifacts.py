"""题目级 QuestionGradingArtifact 发布层 (runtime-readable, 最小发布层).

This is a *publish* layer, not a recompile: it projects the already-curated
golden fixture (scoring points) + the cached typed-policy packets (policy_type /
required_terms / numeric_spec / penalty_spec / textbook evidence) into a single
runtime-readable artifact per question. It does NOT recompute consensus / QWK,
does NOT touch the DB, does NOT touch CaseGradingSkillKernel, and never lets RAG
into grading authority.

Hard invariants:
- Unknown case_id -> {"artifact_missing": True, ...}; never auto-certify a miss.
- Every scoring point carries policy_type + max_score. policy_type is taken from
  the typed policy; if absent it is inferred from the gold list_rule / penalty
  fields, else falls back to "semantic_allowed". We never fabricate a textbook
  anchor to fill a gap.
- source_refs come only from real fields (textbook evidence quote/chunk, official
  basis, official answer, list rule). When no strong textbook source exists the
  point is marked source_status="missing_or_weak" and auto_certifiable=False.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# Reuse the existing golden->typed_policy resolver (single source of truth) instead
# of re-reading the packets a second way.
from scripts.run_luban_ai_draft_grading import GOLDEN, _golden_typed_policy

VERSION_ID = "qga_v0_20260604"
SCHEMA_VERSION = "question_grading_artifact.v0"
COMPILER_VERSION = "qga_compiler_v0"

# Publish gate threshold (v0): a structurally complete question is *published* only
# if at least this many of its points carry a verified (textbook-strong) source and
# meet their policy minimum, i.e. runtime can auto-certify at least one point. All
# structure ok but zero auto-certifiable -> draft (AI-Draft only). Structure broken
# -> blocked.
MIN_AUTO_CERTIFIABLE_FOR_PUBLISH = 1


@lru_cache(maxsize=1)
def _cases() -> dict[str, dict[str, Any]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in data.get("cases", [])}


def list_case_ids() -> list[str]:
    """Readable question ids, in fixture order."""
    return list(_cases().keys())


def list_question_grading_artifacts() -> list[str]:
    """Alias for list_case_ids (offline listing of publishable questions)."""
    return list_case_ids()


def _infer_policy_type(gold_sp: dict[str, Any]) -> str:
    """Best-effort policy_type when the typed policy is missing one.

    Inference only uses the gold scoring point's own structured fields; it never
    invents a textbook anchor. Falls back to "semantic_allowed".
    """
    if gold_sp.get("penalty_rule"):
        return "penalty_rule"
    if gold_sp.get("list_rule"):
        return "list_rule"
    return "semantic_allowed"


def _source_refs(gold_sp: dict[str, Any], case: dict[str, Any],
                 typed_policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Build source_refs from real fields only. Returns (refs, source_status).

    A textbook evidence ref (with a non-empty quote) makes the source "ok". Otherwise
    only weak/official sources exist and source_status is "missing_or_weak".
    """
    refs: list[dict[str, Any]] = []
    has_strong = False

    evidence = (typed_policy or {}).get("evidence_policy") or {}
    quote = (evidence.get("textbook_quote") or "").strip()
    chunk_id = (evidence.get("chunk_id") or "").strip()
    authority = evidence.get("source_authority")
    if authority == "textbook" and quote:
        # Only a real textbook quote + chunk is verified=True. Everything else is
        # weaker corroboration (verified=False); we never mark a non-textbook ref
        # as a verified textbook anchor.
        refs.append({"source_type": "textbook", "chunk_id": chunk_id,
                     "quote": quote, "verified": True})
        has_strong = True

    # official_basis is a real, curated field on the gold scoring point.
    official_basis = (gold_sp.get("official_basis") or "").strip()
    if official_basis:
        refs.append({"source_type": "official_basis", "chunk_id": "",
                     "quote": official_basis, "verified": False})

    # official_answer / list_rule provide weaker corroboration (no textbook chunk).
    list_rule = (gold_sp.get("list_rule") or "").strip()
    if list_rule:
        refs.append({"source_type": "list_rule", "chunk_id": "",
                     "quote": list_rule, "verified": False})

    official_answer = (case.get("official_answer") or "").strip()
    if official_answer and not refs:
        refs.append({"source_type": "official_answer", "chunk_id": "",
                     "quote": official_answer, "verified": False})

    source_status = "ok" if has_strong else "missing_or_weak"
    return refs, source_status


def _meets_policy_minimum(policy_type: str, *, required_terms: list[str],
                          list_rule: Any, calculation_spec: Any,
                          penalty_rule: Any, official_answer: str) -> bool:
    """v0 per-policy minimum a point must meet to be auto-certifiable.

    Structural only — no fabrication. A point that fails its minimum can still be
    drafted, but is never auto-certified.
    """
    if policy_type == "exact_required":
        return bool(required_terms) or bool(official_answer)
    if policy_type == "list_rule":
        return bool(required_terms) or bool(list_rule)
    if policy_type == "calculation":
        return calculation_spec is not None
    if policy_type == "penalty_rule":
        return bool(penalty_rule)
    if policy_type == "high_risk_review":
        # high_risk_review is, by definition, never auto-certified.
        return False
    # figure_label / semantic_allowed: a verified source is the gate (checked by caller).
    return True


def _scoring_point(case: dict[str, Any], gold_sp: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    point_id = gold_sp["point_id"]
    typed_policy = _golden_typed_policy(case_id, point_id) or {}

    policy_type = typed_policy.get("policy_type") or _infer_policy_type(gold_sp)
    required_terms = list(typed_policy.get("required_terms") or [])

    list_spec = typed_policy.get("list_spec")
    list_rule = gold_sp.get("list_rule") or (
        (list_spec or {}).get("rule_text") if list_spec else None
    )

    penalty_spec = typed_policy.get("penalty_spec")
    penalty_rule = gold_sp.get("penalty_rule") or (
        (penalty_spec or {}).get("rule_text") if penalty_spec else None
    )

    calculation_spec = typed_policy.get("numeric_spec")

    refs, source_status = _source_refs(gold_sp, case, typed_policy)
    # auto_certifiable requires BOTH a strong (textbook) source AND meeting the
    # per-policy minimum. Weak/missing source can still be drafted but never
    # auto-certified.
    meets_minimum = _meets_policy_minimum(
        policy_type,
        required_terms=required_terms,
        list_rule=list_rule,
        calculation_spec=calculation_spec,
        penalty_rule=penalty_rule,
        official_answer=(case.get("official_answer") or "").strip(),
    )
    auto_certifiable = (source_status == "ok") and meets_minimum

    knowledge_point_refs: list[str] = []
    chunk_id = ((typed_policy.get("evidence_policy") or {}).get("chunk_id") or "").strip()
    if chunk_id and source_status == "ok":
        knowledge_point_refs.append(chunk_id)

    return {
        "point_id": point_id,
        "label": gold_sp.get("label"),
        "max_score": gold_sp.get("max_score"),
        "policy_type": policy_type,
        "required_terms": required_terms,
        "list_rule": list_rule,
        "calculation_spec": calculation_spec,
        "penalty_rule": penalty_rule,
        "source_refs": refs,
        "source_status": source_status,
        "meets_policy_minimum": meets_minimum,
        "auto_certifiable": auto_certifiable,
        "knowledge_point_refs": knowledge_point_refs,
    }


def _content_hash(question_id: str, scoring_points: list[dict[str, Any]]) -> str:
    """Stable content hash over the publishable core (no clock / randomness)."""
    core = {
        "question_id": question_id,
        "scoring_points": [
            {
                "point_id": sp.get("point_id"),
                "label": sp.get("label"),
                "max_score": sp.get("max_score"),
                "policy_type": sp.get("policy_type"),
                "required_terms": sp.get("required_terms"),
                "source_refs": sp.get("source_refs"),
                "auto_certifiable": sp.get("auto_certifiable"),
            }
            for sp in scoring_points
        ],
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _quality_gates(scoring_points: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scoring_points)
    verified = sum(1 for sp in scoring_points if sp.get("source_status") == "ok")
    auto_pts = sum(1 for sp in scoring_points if sp.get("auto_certifiable"))
    has_policy = all(sp.get("policy_type") for sp in scoring_points)
    has_max = all(sp.get("max_score") is not None for sp in scoring_points)
    # exact_required points whose required_terms cannot be backed by a verified source.
    unsupported_required = [
        sp.get("point_id")
        for sp in scoring_points
        if sp.get("policy_type") == "exact_required"
        and sp.get("required_terms")
        and sp.get("source_status") != "ok"
    ]
    blocked_reasons: list[str] = []
    if total < 1:
        blocked_reasons.append("no_scoring_points")
    if not has_policy:
        blocked_reasons.append("missing_policy_type")
    if not has_max:
        blocked_reasons.append("missing_max_score")
    return {
        "has_scoring_points": total >= 1,
        "has_policy_type": has_policy,
        "has_max_score": has_max,
        "source_refs_verified_rate": (verified / total) if total else 0.0,
        "auto_certifiable_point_count": auto_pts,
        "unsupported_required_terms": unsupported_required,
        "blocked_reasons": blocked_reasons,
    }


def _resolve_status(gates: dict[str, Any]) -> tuple[str, str]:
    """Map quality gates to (status, status_reason). published|draft|blocked."""
    if gates["blocked_reasons"]:
        return "blocked", ";".join(gates["blocked_reasons"])
    if gates["auto_certifiable_point_count"] >= MIN_AUTO_CERTIFIABLE_FOR_PUBLISH:
        return "published", "has_auto_certifiable_points"
    return "draft", "no_auto_certifiable_points"


def build_question_grading_artifact(case_id: str) -> dict[str, Any]:
    """Project a single question into a runtime-readable grading artifact.

    Unknown case_id -> {"artifact_missing": True, "case_id": case_id}.
    """
    case = _cases().get(case_id)
    if case is None:
        return {"artifact_missing": True, "case_id": case_id}

    scoring_points = [
        _scoring_point(case, gold_sp)
        for gold_sp in (case.get("gold_scoring_points") or [])
    ]
    gates = _quality_gates(scoring_points)
    status, status_reason = _resolve_status(gates)
    content_hash = _content_hash(case_id, scoring_points)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"{case_id}::{VERSION_ID}",
        "question_id": case_id,
        "version_id": VERSION_ID,
        "status": status,
        "status_reason": status_reason,
        "source_profile": {
            "verified_points": sum(
                1 for sp in scoring_points if sp.get("source_status") == "ok"
            ),
            "weak_points": sum(
                1 for sp in scoring_points if sp.get("source_status") != "ok"
            ),
            "verified_rate": gates["source_refs_verified_rate"],
        },
        "stem": case.get("stem", ""),
        "official_answer": case.get("official_answer", ""),
        "scoring_points": scoring_points,
        "quality_gates": gates,
        "provenance": {
            "compiled_from": "luban_case_grading_golden_v1+typed_policy_packets",
            "compiler_version": COMPILER_VERSION,
            "content_hash": content_hash,
        },
    }
