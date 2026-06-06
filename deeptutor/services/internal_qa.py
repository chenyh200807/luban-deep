from __future__ import annotations

from deeptutor.services.runtime_env import env_flag, is_production_environment

INTERNAL_QA_BILLING_BYPASS_FLAG = "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS"
INTERNAL_QA_IDENTITY_PREFIXES = ("qa_", "test_", "operator_")


def internal_qa_billing_bypass_enabled() -> bool:
    """Return true only for explicit non-production billing bypass QA runs."""

    return (not is_production_environment()) and env_flag(
        INTERNAL_QA_BILLING_BYPASS_FLAG,
        default=False,
    )


def internal_qa_billing_bypass_allowed(*identity_values: object) -> bool:
    """Return true when the explicit QA billing bypass is scoped to QA identities."""

    if not internal_qa_billing_bypass_enabled():
        return False
    return any(_is_internal_qa_identity(value) for value in identity_values)


def _is_internal_qa_identity(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized) and normalized.startswith(INTERNAL_QA_IDENTITY_PREFIXES)
