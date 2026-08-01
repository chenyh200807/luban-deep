from __future__ import annotations

from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider
from deeptutor.tutorbot.providers.base import LLMProvider
from deeptutor.tutorbot.providers.registry import find_by_name


def test_openai_compat_provider_builds_charged_provider_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_USAGE_RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("LLM_USAGE_COST_CENTER", "prod_user_chat")
    provider = OpenAICompatProvider(
        api_key="sk-test",
        api_base="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        spec=find_by_name("deepseek"),
        provider_name="deepseek",
    )

    metadata = provider._provider_metadata(streaming=False, model="deepseek-v4-flash")

    assert metadata["provider_name"] == "deepseek"
    assert metadata["charged_provider_name"] == "deepseek"
    assert metadata["requested_provider_name"] == "deepseek"
    assert metadata["api_base"] == "https://api.deepseek.com"
    assert metadata["effective_url"] == "https://api.deepseek.com"
    assert metadata["streaming"] is False
    assert metadata["runtime_environment"] == "production"
    assert metadata["cost_center"] == "prod_user_chat"
    assert metadata["raw_model"] == "deepseek-v4-flash"
    assert metadata["pricing_model"] == "deepseek-v4-flash"
    assert metadata["api_key_fingerprint"]
    assert "sk-test" not in metadata["api_key_fingerprint"]


def test_extract_usage_preserves_deepseek_cache_tokens() -> None:
    response = {
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_cache_hit_tokens": 750,
            "prompt_cache_miss_tokens": 250,
        }
    }

    assert OpenAICompatProvider._extract_usage(response) == {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "total_tokens": 1200,
        "prompt_cache_hit_tokens": 750,
        "prompt_cache_miss_tokens": 250,
    }


def test_normalize_usage_details_preserves_cache_breakdown() -> None:
    assert LLMProvider._normalize_usage_details(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_cache_hit_tokens": 750,
            "prompt_cache_miss_tokens": 250,
        }
    ) == {
        "input": 1000.0,
        "output": 200.0,
        "total": 1200.0,
        "input_cache_hit": 750.0,
        "input_cache_miss": 250.0,
    }
