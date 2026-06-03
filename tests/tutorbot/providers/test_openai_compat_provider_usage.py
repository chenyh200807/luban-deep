from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

if "loguru" not in sys.modules:
    module = ModuleType("loguru")
    module.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    sys.modules["loguru"] = module
if "json_repair" not in sys.modules:
    module = ModuleType("json_repair")
    module.loads = lambda value: value
    sys.modules["json_repair"] = module

from deeptutor.tutorbot.providers.openai_compat_provider import OpenAICompatProvider
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
