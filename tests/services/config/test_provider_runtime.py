"""Tests for TutorBot-style runtime config adapter."""

from __future__ import annotations

import json
from pathlib import Path
import re

from deeptutor.services.llm import traffic_control
from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.config.env_store import EnvStore
from deeptutor.services.config.model_catalog import ModelCatalogService
from deeptutor.services.config.provider_runtime import (
    resolve_llm_runtime_config,
    resolve_search_runtime_config,
)


def _build_catalog(
    *,
    llm_profile: dict | None = None,
    llm_model: dict | None = None,
    search_profile: dict | None = None,
) -> dict:
    llm_profile = llm_profile or {
        "id": "llm-p",
        "name": "LLM",
        "binding": "openai",
        "base_url": "",
        "api_key": "",
        "api_version": "",
        "extra_headers": {},
        "models": [{"id": "llm-m", "name": "m", "model": "deepseek-v4-flash"}],
    }
    llm_model = llm_model or llm_profile["models"][0]
    search_profile = search_profile or {
        "id": "search-p",
        "name": "Search",
        "provider": "tavily",
        "base_url": "",
        "api_key": "",
        "proxy": "",
        "models": [],
    }
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": llm_profile["id"],
                "active_model_id": llm_model["id"],
                "profiles": [llm_profile],
            },
            "embedding": {
                "active_profile_id": None,
                "active_model_id": None,
                "profiles": [],
            },
            "search": {
                "active_profile_id": search_profile["id"],
                "profiles": [search_profile],
            },
        },
    }


def _empty_env(tmp_path: Path) -> EnvStore:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_BINDING=",
                "LLM_MODEL=",
                "LLM_API_KEY=",
                "LLM_HOST=",
                "LLM_API_VERSION=",
                "SEARCH_PROVIDER=",
                "SEARCH_API_KEY=",
                "SEARCH_BASE_URL=",
                "SEARCH_PROXY=",
                "BRAVE_API_KEY=",
                "TAVILY_API_KEY=",
                "JINA_API_KEY=",
                "SEARXNG_BASE_URL=",
                "PERPLEXITY_API_KEY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return EnvStore(path=env_path)


def _env_with_lines(tmp_path: Path, lines: list[str]) -> EnvStore:
    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return EnvStore(path=env_path)


def _env_with_llm_defaults(tmp_path: Path) -> EnvStore:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_BINDING=openai",
                "LLM_MODEL=gpt-env-default",
                "LLM_API_KEY=env-key",
                "LLM_HOST=https://env.example/v1",
                "LLM_API_VERSION=",
                "SEARCH_PROVIDER=",
                "SEARCH_API_KEY=",
                "SEARCH_BASE_URL=",
                "SEARCH_PROXY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return EnvStore(path=env_path)


def test_search_without_provider_is_not_configured(tmp_path: Path) -> None:
    catalog = _build_catalog(
        search_profile={
            "id": "search-p",
            "name": "Search",
            "provider": "",
            "base_url": "",
            "api_key": "",
            "proxy": "",
            "models": [],
        }
    )
    resolved = resolve_search_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider == ""
    assert resolved.requested_provider == ""
    assert resolved.status == "not_configured"


def test_llm_explicit_binding_and_headers(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "dashscope",
            "base_url": "",
            "api_key": "dash-key",
            "api_version": "",
            "extra_headers": {"APP-Code": "abc"},
            "models": [{"id": "llm-m", "name": "q", "model": "qwen-max"}],
        }
    )
    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider_name == "dashscope"
    assert resolved.provider_mode == "standard"
    assert resolved.effective_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert resolved.extra_headers == {"APP-Code": "abc"}


def test_llm_factory_traffic_controller_uses_runtime_limits(monkeypatch) -> None:
    cfg = LLMConfig(
        model="deepseek-v4-flash",
        api_key="k",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        binding="dashscope",
        provider_name="dashscope",
        provider_mode="standard",
        max_concurrency=7,
        requests_per_minute=123,
    )
    traffic_control._PROVIDER_TRAFFIC_CONTROLLERS.clear()
    monkeypatch.delenv("DEEPTUTOR_LLM_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("DEEPTUTOR_LLM_REQUESTS_PER_MINUTE", raising=False)

    controller = traffic_control.get_provider_traffic_controller(provider_name="dashscope", config=cfg)

    assert controller.max_concurrency == 7
    assert controller.rpm == 123


def test_llm_resolves_dashscope_fallback_model_from_env(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "dashscope",
            "base_url": "",
            "api_key": "",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m", "name": "d", "model": "deepseek-v4-flash"}],
        }
    )
    env = _env_with_lines(
        tmp_path,
        [
            "LLM_BINDING=dashscope",
            "LLM_MODEL=deepseek-v4-flash",
            "LLM_API_KEY=primary-key",
            "LLM_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1",
            "LLM_FALLBACK_BINDING=dashscope",
            "LLM_FALLBACK_MODEL=qwen3.6-flash",
            "LLM_FALLBACK_API_KEY=",
            "LLM_FALLBACK_HOST=",
        ],
    )

    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=env)

    assert resolved.provider_name == "dashscope"
    assert resolved.model == "deepseek-v4-flash"
    assert resolved.fallback_provider_name == "dashscope"
    assert resolved.fallback_model == "qwen3.6-flash"
    assert resolved.fallback_api_key == "primary-key"
    assert resolved.fallback_effective_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_llm_api_key_prefix_gateway(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "",
            "base_url": "",
            "api_key": "sk-or-test-key",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m", "name": "m", "model": "gemini-2.5-pro"}],
        }
    )
    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider_name == "openrouter"
    assert resolved.provider_mode == "gateway"
    assert resolved.effective_url == "https://openrouter.ai/api/v1"


def test_llm_api_base_keyword_gateway(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "",
            "base_url": "https://api.aihubmix.com/v1",
            "api_key": "k",
            "api_version": "",
            "extra_headers": {"APP-Code": "x"},
            "models": [{"id": "llm-m", "name": "m", "model": "claude-3-7-sonnet"}],
        }
    )
    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider_name == "aihubmix"
    assert resolved.provider_mode == "gateway"
    assert resolved.effective_url == "https://api.aihubmix.com/v1"
    assert resolved.extra_headers == {"APP-Code": "x"}


def test_llm_coding_plan_api_base_uses_specific_gateway(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "",
            "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
            "api_key": "k",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m", "name": "m", "model": "volcengine/deepseek-v3"}],
        }
    )

    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))

    assert resolved.provider_name == "volcengine_coding_plan"
    assert resolved.provider_mode == "gateway"


def test_llm_local_fallback(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p",
            "name": "LLM",
            "binding": "",
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m", "name": "m", "model": "llama3.2"}],
        }
    )
    resolved = resolve_llm_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider_name == "ollama"
    assert resolved.provider_mode == "local"
    assert resolved.api_key == "sk-no-key-required"


def test_llm_selection_overrides_active_model_without_mutating_catalog(tmp_path: Path) -> None:
    catalog = _build_catalog(
        llm_profile={
            "id": "llm-p1",
            "name": "LLM A",
            "binding": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "key-a",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m1", "name": "a", "model": "gpt-4o-mini"}],
        }
    )
    catalog["services"]["llm"]["profiles"].append(
        {
            "id": "llm-p2",
            "name": "LLM B",
            "binding": "dashscope",
            "base_url": "",
            "api_key": "key-b",
            "api_version": "",
            "extra_headers": {},
            "models": [{"id": "llm-m2", "name": "b", "model": "qwen-max"}],
        }
    )

    resolved = resolve_llm_runtime_config(
        catalog=catalog,
        env_store=_env_with_llm_defaults(tmp_path),
        llm_selection={"profile_id": "llm-p2", "model_id": "llm-m2"},
    )

    assert resolved.model == "qwen-max"
    assert resolved.provider_name == "dashscope"
    assert resolved.api_key == "key-b"
    assert catalog["services"]["llm"]["active_profile_id"] == "llm-p1"
    assert catalog["services"]["llm"]["active_model_id"] == "llm-m1"


def test_search_missing_key_does_not_fallback_to_duckduckgo(tmp_path: Path) -> None:
    catalog = _build_catalog(
        search_profile={
            "id": "search-p",
            "name": "Search",
            "provider": "brave",
            "base_url": "",
            "api_key": "",
            "proxy": "http://127.0.0.1:7890",
            "models": [],
        }
    )
    resolved = resolve_search_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider == "brave"
    assert resolved.requested_provider == "brave"
    assert resolved.fallback_reason is None
    assert resolved.missing_credentials is True
    assert resolved.status == "missing_credentials"
    assert resolved.proxy == "http://127.0.0.1:7890"


def test_search_marks_deprecated_provider(tmp_path: Path) -> None:
    catalog = _build_catalog(
        search_profile={
            "id": "search-p",
            "name": "Search",
            "provider": "exa",
            "base_url": "",
            "api_key": "k",
            "proxy": "",
            "models": [],
        }
    )
    resolved = resolve_search_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.unsupported_provider is True
    assert resolved.deprecated_provider is True
    assert resolved.provider == "exa"


def test_search_perplexity_missing_credentials(tmp_path: Path) -> None:
    catalog = _build_catalog(
        search_profile={
            "id": "search-p",
            "name": "Search",
            "provider": "perplexity",
            "base_url": "",
            "api_key": "",
            "proxy": "",
            "models": [],
        }
    )
    resolved = resolve_search_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider == "perplexity"
    assert resolved.unsupported_provider is False
    assert resolved.deprecated_provider is False
    assert resolved.missing_credentials is True


def test_search_searxng_without_url_is_missing_config(tmp_path: Path) -> None:
    catalog = _build_catalog(
        search_profile={
            "id": "search-p",
            "name": "Search",
            "provider": "searxng",
            "base_url": "",
            "api_key": "",
            "proxy": "",
            "models": [],
        }
    )
    resolved = resolve_search_runtime_config(catalog=catalog, env_store=_empty_env(tmp_path))
    assert resolved.provider == "searxng"
    assert resolved.fallback_reason is None
    assert resolved.missing_credentials is True
    assert resolved.status == "missing_credentials"


def test_model_catalog_at_rest_redaction_keeps_runtime_api_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_REDACT_MODEL_CATALOG_API_KEYS_AT_REST", "1")
    catalog_path = tmp_path / "model_catalog.json"
    service = ModelCatalogService(path=catalog_path)

    saved = service.save(
        _build_catalog(
            llm_profile={
                "id": "llm-p",
                "name": "LLM",
                "binding": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-runtime-secret-1234567890",
                "api_version": "",
                "extra_headers": {},
                "models": [{"id": "llm-m", "name": "m", "model": "gpt-4o-mini"}],
            },
            search_profile={
                "id": "search-p",
                "name": "Search",
                "provider": "tavily",
                "base_url": "",
                "api_key": "sk-search-secret-1234567890",
                "proxy": "",
                "models": [],
            },
        )
    )

    rendered = catalog_path.read_text(encoding="utf-8")
    persisted = json.loads(rendered)

    assert saved["services"]["llm"]["profiles"][0]["api_key"] == "sk-runtime-secret-1234567890"
    assert saved["services"]["search"]["profiles"][0]["api_key"] == "sk-search-secret-1234567890"
    assert persisted["services"]["llm"]["profiles"][0]["api_key"] == "[REDACTED]"
    assert persisted["services"]["search"]["profiles"][0]["api_key"] == "[REDACTED]"
    assert not re.search(r"sk-[A-Za-z0-9_-]{10,}", rendered)
    assert not re.search(r'api_key"\s*:\s*"(?!\[REDACTED\]|\s*")', rendered)
