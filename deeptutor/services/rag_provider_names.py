from __future__ import annotations

DEFAULT_PROVIDER = "llamaindex"
LEGACY_PROVIDER_ALIASES = {
    "lightrag": DEFAULT_PROVIDER,
    "raganything": DEFAULT_PROVIDER,
    "raganything_docling": DEFAULT_PROVIDER,
}


def normalize_provider_name(name: str | None) -> str:
    candidate = (name or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    return LEGACY_PROVIDER_ALIASES.get(candidate, candidate)
