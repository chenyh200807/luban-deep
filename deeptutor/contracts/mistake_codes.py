"""Single authority for grading mistake_type codes (G3 register-before-use).

mistake_type labels carried into learner evidence (why a scoring point was lost)
must come from this controlled registry. This module is the Python mirror of
``contracts/mistake_code_registry.yaml`` and the static authority the CI emit-site
guard cross-checks hard-coded literals against.

LLM-produced mistake_type at runtime must be normalized against this set at the judge
boundary (map-or-review, never silent) — that runtime normalization is a separate
follow-up (audit G3 layer 2); this module covers the static / hard-coded layer.
"""

from __future__ import annotations

# Canonical mistake_type codes (mirror of contracts/mistake_code_registry.yaml).
MISTAKE_CODE_REGISTRY: frozenset[str] = frozenset(
    {
        "omitted",  # MISTAKE_MISS — required point not addressed
        "near_synonym_not_exact",  # MISTAKE_NEAR_SYNONYM — exact_required term not precisely hit
        "list_incomplete",  # MISTAKE_PARTIAL_LIST — enumeration partially covered
        "wrong_content",  # MISTAKE_WRONG — addressed but incorrect
        "shape_stub_no_quality_judgment",  # m35 shadow shape_stub arm — no quality judgment made
    }
)

# An LLM-produced value that maps to no registered code: route to review, never
# silently persist as a real mistake_type.
UNKNOWN_MISTAKE = "unknown_mistake"


def is_known_mistake_code(value: str | None) -> bool:
    """True iff ``value`` is a registered canonical mistake_type code."""
    return str(value or "").strip() in MISTAKE_CODE_REGISTRY


__all__ = ["MISTAKE_CODE_REGISTRY", "UNKNOWN_MISTAKE", "is_known_mistake_code"]
