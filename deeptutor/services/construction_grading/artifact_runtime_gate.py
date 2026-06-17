"""Artifact runtime gate — enforce the QuestionGradingArtifact Registry on AI-Draft.

This is the fat-skill that turns the Registry from a file asset into a runtime
safety boundary. Both AI-Draft (DeepSeek fast) and Best-Quality (4-model) assemble
their draft through ``build_ai_draft``; this gate is applied to that draft from ONE
place, so the rule is never duplicated into two engines.

First principle: whether a question may be auto-certified is decided by a *published*
QuestionGradingArtifact, NOT by the model output. The gate can only DOWNGRADE a
point (auto_certified -> pending/high_risk); it never upgrades.

Runtime behavior:
  published  -> point-level auto_certified allowed, but only for points whose
                artifact ``auto_certifiable`` is True; weak/source-missing points are
                downgraded with review_reason ``point_not_auto_certifiable``.
  draft      -> draft is fine, but NO point may auto-certify; all points downgraded
                with review_reason ``artifact_not_published``.
  blocked    -> no auto-certification; review_reason ``artifact_blocked``.
  missing    -> fail closed; review_reason ``artifact_missing``.

It does NOT touch CaseGradingSkillKernel, RAG, production runtime, or any DB.
pending_review_score is preserved (never zeroed). unsupported / existing high_risk
guards always take precedence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from deeptutor.services.construction_grading.question_grading_registry import (
    ArtifactLookupResult,
    QuestionGradingRegistry,
    build_default_registry,
)


@lru_cache(maxsize=1)
def _default_registry() -> QuestionGradingRegistry:
    return build_default_registry()

ARTIFACT_MISSING = "artifact_missing"
ARTIFACT_BLOCKED = "artifact_blocked"
ARTIFACT_NOT_PUBLISHED = "artifact_not_published"
POINT_NOT_AUTO_CERTIFIABLE = "point_not_auto_certifiable"


@dataclass(frozen=True)
class ArtifactRuntimeGate:
    """Resolved gate for one question, ready to apply to a draft."""

    artifact_found: bool
    artifact_status: str  # published | draft | blocked | artifact_missing
    artifact_version_id: str | None
    auto_certification_allowed: bool
    blocked_reason: str | None
    point_auto_certification: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_found": self.artifact_found,
            "artifact_status": self.artifact_status,
            "artifact_version_id": self.artifact_version_id,
            "auto_certification_allowed": self.auto_certification_allowed,
            "blocked_reason": self.blocked_reason,
            "point_auto_certification": dict(self.point_auto_certification),
        }


def resolve_runtime_artifact_gate(
    question_id: str | None,
    *,
    registry: QuestionGradingRegistry | None = None,
) -> ArtifactRuntimeGate:
    """Query the Registry for a question and build the runtime gate."""
    reg = registry if registry is not None else _default_registry()
    lookup: ArtifactLookupResult = reg.lookup(question_id or "")
    if not lookup.found or lookup.artifact is None:
        return ArtifactRuntimeGate(
            artifact_found=False,
            artifact_status=ARTIFACT_MISSING,
            artifact_version_id=None,
            auto_certification_allowed=False,
            blocked_reason=ARTIFACT_MISSING,
            point_auto_certification={},
        )

    art = lookup.artifact
    point_map = {
        str(sp.get("point_id")): bool(sp.get("auto_certifiable"))
        for sp in art.get("scoring_points") or []
    }
    status = lookup.status
    blocked_reason: str | None = None
    if status == "blocked":
        blocked_reason = ARTIFACT_BLOCKED
    elif status == "draft":
        blocked_reason = ARTIFACT_NOT_PUBLISHED
    return ArtifactRuntimeGate(
        artifact_found=True,
        artifact_status=status,
        artifact_version_id=art.get("version_id"),
        auto_certification_allowed=lookup.auto_certification_allowed,
        blocked_reason=blocked_reason,
        point_auto_certification=point_map,
    )


def _add_reason(point: dict[str, Any], reason: str) -> None:
    existing = point.get("review_reason")
    if not existing:
        point["review_reason"] = reason
    elif reason not in existing:
        point["review_reason"] = f"{existing};{reason}"


def _display_status(point: dict[str, Any]) -> str:
    if point.get("unsupported"):
        return "unsupported"
    if point.get("high_risk_review"):
        return "pending_review"
    return "auto_certified"


def _gate_point(point: dict[str, Any], gate: ArtifactRuntimeGate) -> dict[str, Any]:
    p = dict(point)
    pid = str(p.get("point_id"))
    if gate.artifact_status != "published":
        # whole question not published -> no point may auto-certify
        p["auto_certified"] = False
        p["high_risk_review"] = True
        _add_reason(p, gate.blocked_reason or gate.artifact_status)
    elif not gate.point_auto_certification.get(pid, False):
        # published, but this point is weak / source-missing -> downgrade
        p["auto_certified"] = False
        p["high_risk_review"] = True
        _add_reason(p, POINT_NOT_AUTO_CERTIFIABLE)
    # published + auto_certifiable point: leave the guard decision untouched
    # (gate only downgrades, never upgrades unsupported/high_risk).
    p["display_status"] = _display_status(p)
    return p


def _score(point: dict[str, Any]) -> float:
    try:
        return float(point.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def apply_runtime_artifact_gate(
    draft: dict[str, Any], gate: ArtifactRuntimeGate
) -> dict[str, Any]:
    """Apply the gate to an assembled draft, returning a new gated draft.

    Recomputes the certified/pending aggregates after downgrades. pending_review_score
    keeps the model's draft score (never zeroed); auto_certified_score only counts
    points still allowed to auto-certify.
    """
    points = [
        _gate_point(p, gate) for p in (draft.get("point_results") or [])
    ]
    auto_certified_score = round(
        sum(_score(p) for p in points if p.get("auto_certified")), 3
    )
    pending_review_score = round(
        sum(
            _score(p)
            for p in points
            if p.get("high_risk_review") or p.get("unsupported")
        ),
        3,
    )
    bad_certified = sum(
        1
        for p in points
        if (p.get("high_risk_review") or p.get("unsupported")) and p.get("auto_certified")
    )

    gated = dict(draft)
    gated["point_results"] = points
    gated["auto_certified_score"] = auto_certified_score
    gated["pending_review_score"] = pending_review_score
    gated["total_score_certified_only"] = auto_certified_score
    gated["bad_certified_count"] = bad_certified
    gated["auto_certified_count"] = sum(1 for p in points if p.get("auto_certified"))
    gated["high_risk_review_count"] = sum(
        1 for p in points if p.get("high_risk_review")
    )
    gated["unsupported_count"] = sum(1 for p in points if p.get("unsupported"))
    gated["artifact_gate"] = gate.to_dict()
    return gated


def gate_draft_for_question(
    draft: dict[str, Any],
    question_id: str | None,
    *,
    registry: QuestionGradingRegistry | None = None,
) -> dict[str, Any]:
    """Convenience: resolve the gate for question_id and apply it to the draft."""
    gate = resolve_runtime_artifact_gate(question_id, registry=registry)
    return apply_runtime_artifact_gate(draft, gate)


__all__ = [
    "ARTIFACT_MISSING",
    "ARTIFACT_BLOCKED",
    "ARTIFACT_NOT_PUBLISHED",
    "POINT_NOT_AUTO_CERTIFIABLE",
    "ArtifactRuntimeGate",
    "resolve_runtime_artifact_gate",
    "apply_runtime_artifact_gate",
    "gate_draft_for_question",
]
