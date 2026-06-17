from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# Phase -1.B: opt-in re-export of the unified error-code registry. Callers
# that want hard validation can `from deeptutor.services.construction_grading.schema
# import validate_error_code`; existing GradingErrorEvent construction stays
# behaviorally unchanged so tests fixture-loaded with codes like "" keep
# working. The contract guard enforces the registry at the build layer.
from deeptutor.contracts.error_codes import (
    ContractGuardError as ContractGuardError,
    ERROR_CODE_REGISTRY as ERROR_CODE_REGISTRY,
    validate_error_code as validate_error_code,
)

CaseGradingMode = Literal["curated_rubric", "projected_rubric", "open_skill"]
RubricStatus = Literal["full", "partial", "miss"]


@dataclass(frozen=True)
class EvidenceRef:
    source: str
    field: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical schema id for register-before-use (schema-governance P2: this dataclass is the
# single canonical producer of a grading error event, consumed cross-domain by
# learner_state/learning_synthesis (the error_events → claim projection). Making the schema
# VISIBLE to the schema-registry closure so a competing error-event shape can never appear
# unregistered. Registered as T2 runtime-canonical in contracts/schema_registry.yaml.
# FIELD-CANONICALIZATION TODO (needs_field_canonicalization: true): the canonical span field
# here is ``evidence``; the v1 rubric path still emits a parallel ``evidence_span`` for the
# same fact, and learning_synthesis defensively reads both — that drift is the field-level
# pinning follow-up (P2#9), separate from this visibility registration.
GRADING_ERROR_EVENT_SCHEMA_ID = "grading_error_event.v1"


@dataclass(frozen=True)
class GradingErrorEvent:
    error_code: str
    severity: float
    concept_tag: str
    evidence: str
    diagnosis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCQGradingResult:
    question_id: str
    question_type: str
    user_answer: str
    correct_answer: str
    selected_options: list[str]
    missed_options: list[str]
    extra_options: list[str]
    is_correct: bool
    score_awarded: float
    max_score: float
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    error_events: list[GradingErrorEvent] = field(default_factory=list)
    next_training_signal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [ref.to_dict() for ref in self.evidence_refs]
        payload["error_events"] = [event.to_dict() for event in self.error_events]
        return payload


@dataclass(frozen=True)
class CaseRubricItemResult:
    criterion: str
    max_score: float
    awarded_score: float
    status: RubricStatus
    keywords: list[str]
    evidence_text: str
    source_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseGradingResult:
    question_id: str
    grading_mode: CaseGradingMode
    score_awarded: float
    max_score: float
    rubric_items: list[CaseRubricItemResult]
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    error_events: list[GradingErrorEvent] = field(default_factory=list)
    rewrite_answer: str = ""
    next_training_signal: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rubric_items"] = [item.to_dict() for item in self.rubric_items]
        payload["evidence_refs"] = [ref.to_dict() for ref in self.evidence_refs]
        payload["error_events"] = [event.to_dict() for event in self.error_events]
        return payload
