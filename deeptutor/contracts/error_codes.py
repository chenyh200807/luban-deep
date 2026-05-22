"""Phase -1.B: Unified error code registry (Python source of truth).

Mirrors ``docs/contracts/error_code_registry.md``. New codes MUST be added
to both files. The contract guard cross-checks emit sites against this
dict; ``learning_synthesis`` and ``learning_brain_read_model`` keep their
local label maps for now, but they cannot reference codes that do not
exist here.

ability_dimension mapping is the canonical lookup driving Task 4's
three-layer learning-state projection in the Phase -1 plan.
"""
from __future__ import annotations

from typing import Iterable, Literal, TypedDict


_ALLOWED_DIMENSIONS = frozenset({
    "question_reading",
    "code_application",
    "calculation",
    "expression",
    "transfer",
    "review_execution",
})


class ErrorCodeSpec(TypedDict):
    """Single-row schema for the registry."""

    label: str
    ability_dimension: str
    series: Literal["E", "M", "FALLBACK"]


class ContractGuardError(Exception):
    """Raised when an emit site references a code not in ERROR_CODE_REGISTRY."""


# ─── E series — case / essay grading ──────────────────────────────────────
# Source: deeptutor/services/learner_state/learning_report_read_model.py
#         deeptutor/services/learner_state/learning_brain_read_model.py
# These dicts already exist locally inside both read models; this registry
# is the single source of truth they must align with going forward.
_E_SERIES: dict[str, ErrorCodeSpec] = {
    "E01": {"label": "知识点缺失", "ability_dimension": "code_application", "series": "E"},
    "E02": {"label": "采分点遗漏", "ability_dimension": "expression", "series": "E"},
    "E03": {"label": "关键词缺失", "ability_dimension": "expression", "series": "E"},
    "E04": {"label": "口号化表达", "ability_dimension": "expression", "series": "E"},
    "E05": {"label": "审题错误", "ability_dimension": "question_reading", "series": "E"},
    "E06": {"label": "程序顺序错误", "ability_dimension": "transfer", "series": "E"},
    "E07": {"label": "概念混淆", "ability_dimension": "code_application", "series": "E"},
    "E08": {"label": "背景信息提取失败", "ability_dimension": "question_reading", "series": "E"},
    "E09": {"label": "计算错误", "ability_dimension": "calculation", "series": "E"},
    "E10": {"label": "规范适用错误", "ability_dimension": "code_application", "series": "E"},
    "E11": {"label": "迁移失败", "ability_dimension": "transfer", "series": "E"},
    "E12": {"label": "表达冗余", "ability_dimension": "expression", "series": "E"},
}

# ─── M series — MCQ grading ───────────────────────────────────────────────
_M_SERIES: dict[str, ErrorCodeSpec] = {
    "M01": {"label": "知识点不熟", "ability_dimension": "code_application", "series": "M"},
    "M02": {"label": "关键词误读", "ability_dimension": "question_reading", "series": "M"},
    "M03": {"label": "概念混淆", "ability_dimension": "code_application", "series": "M"},
    "M04": {"label": "选项陷阱", "ability_dimension": "question_reading", "series": "M"},
    "M05": {"label": "审题方向错误", "ability_dimension": "question_reading", "series": "M"},
    "M06": {"label": "多选漏选", "ability_dimension": "question_reading", "series": "M"},
    "M07": {"label": "多选错选", "ability_dimension": "question_reading", "series": "M"},
    "M08": {"label": "规范数字混淆", "ability_dimension": "code_application", "series": "M"},
    "M09": {"label": "题干条件提取不完整", "ability_dimension": "question_reading", "series": "M"},
    "M10": {"label": "用常识替代规范判断", "ability_dimension": "code_application", "series": "M"},
}

# ─── Fallback — emitted when grader returns no code ───────────────────────
# Used by:
#   deeptutor/services/construction_grading/learning_evidence._typed_edges_from_payload
#   deeptutor/services/learner_state/learning_synthesis._improvement_error_code
_FALLBACK: dict[str, ErrorCodeSpec] = {
    "unknown_error": {
        "label": "未归因错误",
        "ability_dimension": "review_execution",
        "series": "FALLBACK",
    },
}

ERROR_CODE_REGISTRY: dict[str, ErrorCodeSpec] = {
    **_E_SERIES,
    **_M_SERIES,
    **_FALLBACK,
}


# Sanity guard at import time: a registry entry whose ability_dimension is
# outside the canonical set is a bug and the module refuses to load. This
# enforces the plan's hard constraint at the lowest level.
for _code, _spec in ERROR_CODE_REGISTRY.items():
    if _spec["ability_dimension"] not in _ALLOWED_DIMENSIONS:
        raise ContractGuardError(
            f"registry corruption: {_code} ability_dimension={_spec['ability_dimension']!r} "
            f"not in allowed set {sorted(_ALLOWED_DIMENSIONS)}"
        )


def validate_error_code(code: str) -> None:
    """Raise ContractGuardError if ``code`` is not in the registry.

    Single-code helper. Schema and writeback callers can opt into this
    validation without coupling to the bulk ``check_emitted_error_codes``.
    """
    normalized = str(code or "").strip()
    if normalized not in ERROR_CODE_REGISTRY:
        raise ContractGuardError(
            f"unregistered_error_code: {normalized!r} not in error_code_registry.md"
        )


def check_emitted_error_codes(codes: Iterable[str]) -> None:
    """Validate every code in ``codes`` against the registry.

    Raises ``ContractGuardError`` if any are unregistered. The exception
    message lists ALL offending codes in one batch so教研 can fix the
    registry without round-tripping through CI.
    """
    seen_unregistered: list[str] = []
    seen_set: set[str] = set()
    for raw in codes:
        normalized = str(raw or "").strip()
        if not normalized or normalized in ERROR_CODE_REGISTRY:
            continue
        if normalized in seen_set:
            continue
        seen_set.add(normalized)
        seen_unregistered.append(normalized)

    if seen_unregistered:
        raise ContractGuardError(
            "unregistered_error_code(s): "
            + ", ".join(seen_unregistered)
            + " — add to docs/contracts/error_code_registry.md and "
            "deeptutor/contracts/error_codes.py with ability_dimension."
        )


__all__ = [
    "ContractGuardError",
    "ERROR_CODE_REGISTRY",
    "ErrorCodeSpec",
    "check_emitted_error_codes",
    "validate_error_code",
]
