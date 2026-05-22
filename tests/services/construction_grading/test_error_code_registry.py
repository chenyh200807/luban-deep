"""Phase -1.B: Unified error code registry.

The plan resolves a long-standing duplication where E0X (case grading) and
M0X (MCQ) codes were maintained as separate label dicts in
``learning_report_read_model.py`` AND ``learning_brain_read_model.py``.
This test pins the canonical registry and the contract-guard cross-check
that fails when an unregistered code is emitted.

Hard constraint from the plan: "new rule type without ability_dimension
mapping must fail contract guard".
"""
from __future__ import annotations

import pytest

from deeptutor.contracts.error_codes import (
    ContractGuardError,
    ERROR_CODE_REGISTRY,
    check_emitted_error_codes,
    validate_error_code,
)


def test_existing_e_and_m_codes_are_registered() -> None:
    """All codes currently emitted in production must appear in the registry."""
    # E series (case grading, from learning_report_read_model._ERROR_LABELS)
    for code in ("E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "E12"):
        assert code in ERROR_CODE_REGISTRY, f"existing case-grading code {code} missing from registry"

    # M series (MCQ, from learning_report_read_model._ERROR_LABELS + mcq.py emit sites)
    for code in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10"):
        assert code in ERROR_CODE_REGISTRY, f"existing MCQ code {code} missing from registry"

    # Fallback code emitted by learning_evidence._typed_edges_from_payload + learning_synthesis
    assert "unknown_error" in ERROR_CODE_REGISTRY, (
        "fallback 'unknown_error' must be registered so the current emit sites stay valid"
    )


def test_every_registered_code_has_ability_dimension_mapping() -> None:
    """Hard constraint: a registered code without an ability_dimension cannot
    drive Task 4's three-layer state projection. The contract guard refuses
    such entries at registration time."""
    allowed_dimensions = {
        "question_reading",
        "code_application",
        "calculation",
        "expression",
        "transfer",
        "review_execution",
    }
    for code, spec in ERROR_CODE_REGISTRY.items():
        assert spec["ability_dimension"] in allowed_dimensions, (
            f"{code} ability_dimension={spec['ability_dimension']!r} not in {sorted(allowed_dimensions)}"
        )
        assert spec["label"], f"{code} must have a non-empty label"
        assert spec["series"] in {"E", "M", "FALLBACK"}, f"{code} series must be E/M/FALLBACK"


def test_emitting_unregistered_error_code_fails_contract_guard() -> None:
    """The contract-guard cross-check raises ContractGuardError listing the
    offending code when an emit site references a code not in the registry."""
    with pytest.raises(ContractGuardError, match="unregistered_error_code"):
        check_emitted_error_codes(["E02", "E04", "X99"])


def test_emitting_only_registered_codes_passes() -> None:
    """Happy path: every code is registered → no exception."""
    # Should not raise
    check_emitted_error_codes(["E01", "E02", "M06", "M07", "unknown_error"])


def test_validate_error_code_accepts_registered_codes() -> None:
    """``validate_error_code`` is the single-code helper schema.py can call."""
    validate_error_code("E02")  # no exception
    validate_error_code("M07")
    validate_error_code("unknown_error")


def test_validate_error_code_rejects_unregistered() -> None:
    with pytest.raises(ContractGuardError, match="X99"):
        validate_error_code("X99")


def test_check_emitted_error_codes_reports_all_unregistered_at_once() -> None:
    """When multiple unregistered codes are emitted, the error message must
    list them all so教研 can fix the registry in one batch."""
    with pytest.raises(ContractGuardError) as exc_info:
        check_emitted_error_codes(["E02", "X99", "Y00", "M03"])
    msg = str(exc_info.value)
    assert "X99" in msg
    assert "Y00" in msg
    # Registered codes must NOT appear in the error message
    assert "E02" not in msg
    assert "M03" not in msg
