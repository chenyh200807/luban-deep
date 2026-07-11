from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deeptutor.services.config.env_store import get_env_store
from deeptutor.services.learner_state.memory_lifecycle import is_stable_evidence_level
from deeptutor.services.runtime_env import env_flag, is_production_environment

CANONICAL_TRUTH_PRODUCTION_WRITE_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED"
CANONICAL_TRUTH_PRODUCTION_WRITE_COHORT = "LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_COHORT"
CANONICAL_TRUTH_PRODUCTION_WRITE_COHORT_DEFAULT = "qa_,operator_"
CANONICAL_TRUTH_BROAD_TRUSTED_ADJUDICATION_FLAG = (
    "LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED"
)
CANONICAL_TRUTH_BROAD_AI_ADJUDICATION_FLAG = "LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_AI_ADJUDICATION_ENABLED"
CANONICAL_TRUTH_AI_ADJUDICATION_MIN_CONFIDENCE = (
    "LUBAN_CANONICAL_LEARNER_TRUTH_AI_ADJUDICATION_MIN_CONFIDENCE"
)

_AI_ADJUDICATION_SOURCES = frozenset(
    {
        "ai_jury",
        "llm_jury",
        "model_jury",
        "model_jury_teacher_review",
        "model_jury_teacher_final",
        "best_quality_4model",
    }
)
_TRUSTED_NON_AI_SOURCES = frozenset(
    {
        "certified_grading_policy",
        "human_teacher",
        "human_qa_teacher",
        "manual_qa_teacher",
        "teacher_final",
        "operator",
        "operator_soak",
        "operator_smoke",
        "golden_label",
        "signed_variant_server_rescore",
    }
)
_CONFIDENCE_GATED_TRUSTED_SOURCES = _AI_ADJUDICATION_SOURCES | frozenset({"certified_grading_policy"})
_RESOLVED_CONFLICT_STATUSES = frozenset({"", "none", "no_conflict", "resolved", "not_applicable"})


@dataclass(frozen=True)
class CanonicalTruthPromotionDecision:
    allowed: bool
    reason: str
    adjudication_source: str = ""
    requires_human: bool = False
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allowed": self.allowed,
            "reason": self.reason,
            "adjudication_source": self.adjudication_source,
            "requires_human": self.requires_human,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


def canonical_truth_production_write_cohort_allowed(user_id: str) -> bool:
    normalized = _text(user_id)
    raw = get_env_store().get(
        CANONICAL_TRUTH_PRODUCTION_WRITE_COHORT,
        CANONICAL_TRUTH_PRODUCTION_WRITE_COHORT_DEFAULT,
    )
    prefixes = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    return bool(prefixes) and any(normalized.startswith(prefix) for prefix in prefixes)


def canonical_truth_promotion_decision(
    *,
    user_id: str,
    projection: dict[str, Any],
) -> CanonicalTruthPromotionDecision:
    if not is_production_environment():
        return CanonicalTruthPromotionDecision(True, "non_production")

    if not env_flag(CANONICAL_TRUTH_PRODUCTION_WRITE_FLAG, default=False):
        return CanonicalTruthPromotionDecision(False, "production_write_flag_disabled")

    if canonical_truth_production_write_cohort_allowed(user_id):
        return CanonicalTruthPromotionDecision(True, "production_cohort_authorized", "operator_soak")

    if not _broad_trusted_adjudication_enabled():
        return CanonicalTruthPromotionDecision(False, "production_cohort_required")

    trusted = trusted_adjudication_from_projection(projection)
    source = _text(trusted.get("source")).lower()
    if not source:
        return CanonicalTruthPromotionDecision(False, "trusted_adjudication_required")
    if source not in _AI_ADJUDICATION_SOURCES and source not in _TRUSTED_NON_AI_SOURCES:
        return CanonicalTruthPromotionDecision(False, "untrusted_adjudication_source", source)
    if bool(trusted.get("requires_human")):
        return CanonicalTruthPromotionDecision(False, "human_adjudication_required", source, True)

    confidence = _confidence(trusted.get("confidence"))
    if source in _CONFIDENCE_GATED_TRUSTED_SOURCES:
        if confidence is None or confidence < _ai_min_confidence():
            reason = (
                "certified_grading_policy_confidence_too_low"
                if source == "certified_grading_policy"
                else "ai_adjudication_confidence_too_low"
            )
            return CanonicalTruthPromotionDecision(False, reason, source, False, confidence)
        conflict_status = _text(trusted.get("conflict_status")).lower()
        if conflict_status not in _RESOLVED_CONFLICT_STATUSES:
            reason = (
                "certified_grading_policy_conflict_unresolved"
                if source == "certified_grading_policy"
                else "ai_adjudication_conflict_unresolved"
            )
            return CanonicalTruthPromotionDecision(False, reason, source, False, confidence)
        if source == "certified_grading_policy" and not _has_certified_policy_metadata(trusted):
            return CanonicalTruthPromotionDecision(
                False,
                "certified_grading_policy_metadata_required",
                source,
                False,
                confidence,
            )

    if not _has_stable_learner_claim(projection):
        return CanonicalTruthPromotionDecision(False, "stable_learner_claim_required", source, False, confidence)

    return CanonicalTruthPromotionDecision(True, "trusted_adjudication_authorized", source, False, confidence)


def trusted_adjudication_from_projection(projection: dict[str, Any]) -> dict[str, Any]:
    run = projection.get("synthesis_run") if isinstance(projection.get("synthesis_run"), dict) else {}
    trusted = run.get("trusted_adjudication") if isinstance(run.get("trusted_adjudication"), dict) else {}
    if trusted:
        return dict(trusted)
    trusted = projection.get("trusted_adjudication") if isinstance(projection.get("trusted_adjudication"), dict) else {}
    return dict(trusted)


def trusted_adjudication_from_quality(quality: dict[str, Any], signal: dict[str, Any] | None = None) -> dict[str, Any]:
    trusted = quality.get("trusted_adjudication") if isinstance(quality.get("trusted_adjudication"), dict) else {}
    if trusted:
        return dict(trusted)
    authority = _text(quality.get("teacher_review_authority") or quality.get("authority")).lower()
    if (
        authority == "signed_variant_server_rescore"
        and quality.get("writeback_eligible") is True
        and _text(quality.get("measurement_confidence")).lower() == "high"
        and _text(quality.get("evidence_level")) == "L2_real_retest"
    ):
        return {
            "source": "signed_variant_server_rescore",
            "confidence": 1.0,
            "conflict_status": "resolved",
            "requires_human": False,
        }
    if (
        authority in {"teacher_final_grading_result", "teacher_final", "trusted_adjudication"}
        and quality.get("teacher_reviewed") is True
    ):
        return {
            "source": "teacher_final",
            "confidence": 1.0,
            "conflict_status": "resolved",
            "requires_human": False,
        }
    signal = signal if isinstance(signal, dict) else {}
    audit = signal.get("teacher_review_audit") if isinstance(signal.get("teacher_review_audit"), dict) else {}
    reviewer_type = _text(audit.get("reviewer_type")).lower()
    if reviewer_type:
        return {
            "source": reviewer_type,
            "confidence": _confidence(audit.get("confidence")) or 1.0,
            "conflict_status": _text(audit.get("conflict_status")) or "resolved",
            "requires_human": reviewer_type in {"human_teacher", "human_qa_teacher"},
        }
    return {}


def _broad_trusted_adjudication_enabled() -> bool:
    return env_flag(CANONICAL_TRUTH_BROAD_TRUSTED_ADJUDICATION_FLAG, default=False) or env_flag(
        CANONICAL_TRUTH_BROAD_AI_ADJUDICATION_FLAG,
        default=False,
    )


def _ai_min_confidence() -> float:
    raw = get_env_store().get(CANONICAL_TRUTH_AI_ADJUDICATION_MIN_CONFIDENCE, "0.85")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.85


def _has_stable_learner_claim(projection: dict[str, Any]) -> bool:
    for claim in [
        *list(projection.get("weak_points") or []),
        *list(projection.get("stale_claims") or []),
    ]:
        if not isinstance(claim, dict):
            continue
        stage = _text(claim.get("memory_lifecycle_stage"))
        if stage == "stable_learner_claim":
            return True
        level = _text(claim.get("evidence_level"))
        if is_stable_evidence_level(level):
            return True
    return False


def _has_certified_policy_metadata(trusted: dict[str, Any]) -> bool:
    return bool(
        _text(trusted.get("policy_id"))
        and _text(trusted.get("rubric_hash"))
        and _text(trusted.get("grader_version"))
    )


def _confidence(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()
