from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess

import pytest

from deeptutor.services.llm.config import LLMConfig
from deeptutor.services.llm.exceptions import LLMConfigError

cloud_provider_module = importlib.import_module("deeptutor.services.llm.cloud_provider")
open_ai_provider_module = importlib.import_module("deeptutor.services.llm.providers.open_ai")


def test_openai_provider_rejects_disable_ssl_verify_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")

    config = LLMConfig(
        model="gpt-test",
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        binding="openai",
    )

    with pytest.raises(LLMConfigError, match="DISABLE_SSL_VERIFY is not allowed in production"):
        open_ai_provider_module.OpenAIProvider(config)


def test_cloud_provider_rejects_disable_ssl_verify_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")

    with pytest.raises(LLMConfigError, match="DISABLE_SSL_VERIFY is not allowed in production"):
        cloud_provider_module._get_aiohttp_connector()


def test_agentic_pipeline_rejects_disable_ssl_verify_in_production() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["DEEPTUTOR_ENV"] = "production"
    env["DISABLE_SSL_VERIFY"] = "1"
    code = """
from types import SimpleNamespace
import deeptutor.agents.chat.agentic_pipeline as module

module.get_llm_config = lambda: SimpleNamespace(
    binding="openai",
    model="gpt-test",
    api_key="sk-test",
    base_url="https://api.example.com/v1",
    api_version=None,
)
module.get_tool_registry = lambda: object()

pipeline = module.AgenticChatPipeline(language="zh")
try:
    pipeline._build_openai_client()
except RuntimeError as exc:
    print(exc)
else:
    raise SystemExit("expected RuntimeError")
"""
    completed = subprocess.run(
        ["./.venv/bin/python", "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "DISABLE_SSL_VERIFY is not allowed in production" in completed.stdout
