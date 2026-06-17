"""QuestionGradingArtifact Registry v0 (file-based, runtime-readable admission gate).

This is the *publish gate* the runtime consults before auto-certifying a grading:

- ``question_id`` has a **published** artifact -> may enter the auto_certified flow.
- only a **draft** / weak artifact            -> AI-Draft / high_risk only, never auto.
- a **blocked** artifact                       -> never grades automatically (伪源风险 /
  unsupported required_terms, or 0 auto-certifiable points combined with a
  high_risk_review point); a human must repair the source before it can publish.
- **no** artifact for the question            -> ``{"artifact_missing": True}``, no auto.

Thin wrapper, fat skill: every scoring-point / policy / source decision is made once
in ``question_grading_artifacts``. This module only (1) indexes those artifacts by
question_id, (2) refines ``published``/``draft`` into a stricter runtime ``blocked``
status, and (3) exposes the runtime gate functions. It re-uses
``build_question_grading_artifact`` verbatim — it does NOT recompute scoring points,
re-resolve sources, recompile knowledge, run models, touch the DB, or fabricate a
textbook anchor.

Hard invariants (mirror ``question_grading_artifacts``):
- No database. The registry is a list of artifact dicts, built in-memory from the
  golden projection or loaded from a jsonl file. No DB table, no RAG authority,
  no CaseGradingSkillKernel coupling.
- Unknown question_id -> ``{"artifact_missing": True}``. Never auto-certify a miss.
- auto_certification is allowed ONLY for a *published* artifact AND only for that
  artifact's points that are themselves ``auto_certifiable``. draft / blocked /
  missing all forbid it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.question_grading_artifacts import (
    VERSION_ID,
    build_question_grading_artifact,
    list_case_ids,
)

ARTIFACT_MISSING = "artifact_missing"

# Policy types that, by definition, route to a human and can never be auto-certified.
HIGH_RISK_POLICY_TYPES = frozenset({"high_risk_review"})


@dataclass(frozen=True)
class ArtifactLookupResult:
    """Runtime lookup result for a single question_id."""

    found: bool
    status: str  # published | draft | blocked | artifact_missing
    artifact: dict[str, Any] | None
    auto_certification_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "status": self.status,
            "auto_certification_allowed": self.auto_certification_allowed,
            "artifact": self.artifact,
        }


def _has_high_risk_point(artifact: dict[str, Any]) -> bool:
    return any(
        sp.get("policy_type") in HIGH_RISK_POLICY_TYPES
        for sp in artifact.get("scoring_points") or []
    )


def _refine_status(artifact: dict[str, Any]) -> tuple[str, str]:
    """Refine the artifact's published/draft/blocked into the runtime gate status.

    ``question_grading_artifacts`` already marks structurally-broken questions
    ``blocked``. The runtime gate adds two more *blocked* conditions that protect
    Learning Brain authority:

    1. 伪源风险 / unsupported required_terms: an ``exact_required`` point carries
       required_terms but has no verified textbook source -> 伪源 risk -> blocked.
    2. 0 auto-certifiable points AND the question contains a high_risk_review point:
       nothing can be auto-certified and the question is genuinely ambiguous ->
       blocked rather than silently sitting as a draft.

    Returns ``(status, reason)``. Never *upgrades* a status — only blocks harder.
    """
    base_status = artifact.get("status", "blocked")
    base_reason = artifact.get("status_reason", "")
    if base_status == "blocked":
        return base_status, base_reason

    gates = artifact.get("quality_gates") or {}
    unsupported = gates.get("unsupported_required_terms") or []
    if unsupported:
        return "blocked", f"unsupported_required_terms:{unsupported}"

    auto_count = gates.get("auto_certifiable_point_count", 0)
    if auto_count == 0 and _has_high_risk_point(artifact):
        return "blocked", "zero_auto_certifiable_with_high_risk"

    return base_status, base_reason


def _apply_runtime_status(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the artifact with the runtime-refined status (immutable)."""
    status, reason = _refine_status(artifact)
    if status == artifact.get("status") and reason == artifact.get("status_reason"):
        return artifact
    return {**artifact, "status": status, "status_reason": reason}


class QuestionGradingRegistry:
    """In-memory index over published/draft/blocked artifacts, keyed by question_id.

    Artifacts are stored with their *runtime-refined* status (see ``_refine_status``).
    When two artifacts share a question_id, the one with the greatest ``version_id``
    wins (date-stamped ``qga_vN_YYYYMMDD``), so the registry always returns the latest.
    """

    def __init__(self, artifacts: list[dict[str, Any]] | None = None) -> None:
        self._by_question: dict[str, dict[str, Any]] = {}
        for art in artifacts or []:
            self.add(art)

    def add(self, artifact: dict[str, Any]) -> None:
        qid = artifact.get("question_id")
        if not qid:
            return
        refined = _apply_runtime_status(artifact)
        existing = self._by_question.get(qid)
        if existing is None or _version_key(refined) >= _version_key(existing):
            self._by_question[qid] = refined

    def question_ids(self) -> list[str]:
        return list(self._by_question.keys())

    def get_artifact(self, question_id: str) -> dict[str, Any] | None:
        return self._by_question.get(question_id)

    def lookup(self, question_id: str) -> ArtifactLookupResult:
        art = self._by_question.get(question_id)
        if art is None:
            return ArtifactLookupResult(
                found=False,
                status=ARTIFACT_MISSING,
                artifact=None,
                auto_certification_allowed=False,
            )
        status = art.get("status", "blocked")
        return ArtifactLookupResult(
            found=True,
            status=status,
            artifact=art,
            # Only a published artifact unlocks auto-certification.
            auto_certification_allowed=(status == "published"),
        )

    def publish_summary(self) -> dict[str, int]:
        counts = {"published": 0, "draft": 0, "blocked": 0}
        for art in self._by_question.values():
            status = art.get("status", "blocked")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def to_report(self) -> dict[str, Any]:
        """Spec-shaped registry report: ``{questions: [...], summary: {...}}``."""
        questions = [
            _question_row(self._by_question[qid]) for qid in self._by_question
        ]
        summary = self.publish_summary()
        return {
            "version_id": VERSION_ID,
            "questions": questions,
            "summary": {
                "published_count": summary["published"],
                "draft_count": summary["draft"],
                "blocked_count": summary["blocked"],
            },
        }


def _version_key(artifact: dict[str, Any]) -> str:
    return str(artifact.get("version_id") or "")


def _question_row(artifact: dict[str, Any]) -> dict[str, Any]:
    """Per-question summary row for the registry report (spec shape)."""
    gates = artifact.get("quality_gates") or {}
    scoring_points = artifact.get("scoring_points") or []
    total = len(scoring_points)
    auto_count = gates.get("auto_certifiable_point_count", 0)
    weak_points = [
        sp.get("point_id")
        for sp in scoring_points
        if sp.get("source_status") != "ok"
    ]
    missing_policy_points = [
        sp.get("point_id") for sp in scoring_points if not sp.get("policy_type")
    ]
    return {
        "question_id": artifact.get("question_id"),
        "status": artifact.get("status", "blocked"),
        "reason": artifact.get("status_reason", ""),
        "published_point_count": auto_count,
        "draft_point_count": max(total - auto_count, 0),
        "blocked_point_count": len(gates.get("unsupported_required_terms") or []),
        "total_scoring_points": total,
        "source_weak_points": weak_points,
        "missing_policy_points": missing_policy_points,
    }


def build_default_registry() -> QuestionGradingRegistry:
    """Build the registry in-memory from the golden projection (no file needed).

    Deterministic: reuses ``build_question_grading_artifact`` over the 20 readable
    golden cases. Used by the runtime helpers as the default source of truth and by
    tests without a serialized registry on disk.
    """
    artifacts = [build_question_grading_artifact(cid) for cid in list_case_ids()]
    return QuestionGradingRegistry(artifacts)


def load_registry_from_jsonl(path: str | Path) -> QuestionGradingRegistry:
    """Load a serialized registry (one artifact dict per line)."""
    p = Path(path)
    artifacts: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            artifacts.append(json.loads(line))
    return QuestionGradingRegistry(artifacts)


@lru_cache(maxsize=1)
def _default_registry() -> QuestionGradingRegistry:
    return build_default_registry()


def build_registry(
    *, registry: QuestionGradingRegistry | None = None
) -> dict[str, Any]:
    """Spec entrypoint: build the full registry report over the 20 golden questions.

    Returns ``{version_id, questions: [...], summary: {published_count, draft_count,
    blocked_count}}``. Pure projection over the golden artifacts; no DB, no models.
    """
    reg = registry if registry is not None else build_default_registry()
    return reg.to_report()


def get_question_grading_artifact(
    question_id: str,
    *,
    registry: QuestionGradingRegistry | None = None,
) -> dict[str, Any]:
    """Runtime lookup: return the (runtime-refined) artifact, or fail closed.

    Unknown question_id -> ``{"artifact_missing": True, "question_id": question_id}``.
    Helper only — NOT wired into production runtime.
    """
    reg = registry if registry is not None else _default_registry()
    art = reg.get_artifact(question_id)
    if art is None:
        return {"artifact_missing": True, "question_id": question_id}
    return art


def auto_certification_allowed(
    question_id: str,
    point_id: str | None = None,
    *,
    registry: QuestionGradingRegistry | None = None,
) -> bool:
    """Runtime gate: may this question (or a specific point) be auto-certified?

    True only when:
    - the question has a **published** artifact, AND
    - if ``point_id`` is given, that point is itself ``auto_certifiable``.

    draft / blocked / artifact_missing all return False (fail closed). A weak-source
    point inside a published question is never auto-certified.
    """
    reg = registry if registry is not None else _default_registry()
    result = reg.lookup(question_id)
    if not result.auto_certification_allowed or result.artifact is None:
        return False
    if point_id is None:
        return True
    for sp in result.artifact.get("scoring_points") or []:
        if sp.get("point_id") == point_id:
            return bool(sp.get("auto_certifiable"))
    return False


__all__ = [
    "ARTIFACT_MISSING",
    "VERSION_ID",
    "ArtifactLookupResult",
    "QuestionGradingRegistry",
    "build_default_registry",
    "build_registry",
    "load_registry_from_jsonl",
    "get_question_grading_artifact",
    "auto_certification_allowed",
]
