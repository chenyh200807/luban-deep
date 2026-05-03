"""LLM provider adapter that reuses DeepTutor's LLM configuration.

When TutorBot runs in-process inside the DeepTutor server, this provider
reads api_key / model / base_url from DeepTutor's unified config and
delegates to the appropriate provider (OpenAICompat or Anthropic).
"""

from __future__ import annotations

from deeptutor.tutorbot.providers.base import LLMProvider


def _build_provider(
    *,
    api_key: str | None,
    api_base: str | None,
    model: str,
    extra_headers: dict[str, str] | None,
    provider_name: str | None,
) -> LLMProvider:
    from deeptutor.services.provider_registry import find_by_model, find_by_name

    spec = None
    if provider_name:
        spec = find_by_name(provider_name)
    if spec is None and model:
        spec = find_by_model(model)

    backend = spec.backend if spec else "openai_compat"

    if backend == "anthropic":
        from deeptutor.tutorbot.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=api_key,
            api_base=api_base,
            default_model=model,
            extra_headers=extra_headers or {},
        )

    from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider
    return OpenAICompatProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
        extra_headers=extra_headers or {},
        spec=spec,
        provider_name=provider_name,
    )


def create_deeptutor_provider() -> LLMProvider:
    """Build a provider pre-configured from DeepTutor's LLMConfig."""
    from deeptutor.services.config.provider_runtime import resolve_llm_runtime_config
    from deeptutor.services.llm.config import get_llm_config

    cfg = get_llm_config()
    provider = _build_provider(
        api_key=cfg.api_key or None,
        api_base=cfg.effective_url or cfg.base_url or None,
        model=cfg.model,
        extra_headers=cfg.extra_headers or {},
        provider_name=cfg.provider_name or None,
    )

    resolved = resolve_llm_runtime_config()
    if not resolved.fallback_model:
        return provider

    fallback = _build_provider(
        api_key=resolved.fallback_api_key or None,
        api_base=resolved.fallback_effective_url or resolved.fallback_base_url or None,
        model=resolved.fallback_model,
        extra_headers=resolved.fallback_extra_headers or {},
        provider_name=resolved.fallback_provider_name or None,
    )
    from deeptutor.tutorbot.providers.failover import FailoverProvider

    return FailoverProvider(
        primary=provider,
        fallback=fallback,
        fallback_model=resolved.fallback_model,
    )
