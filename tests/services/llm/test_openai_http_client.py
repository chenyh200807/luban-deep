from __future__ import annotations

import pytest

from deeptutor.services.llm.exceptions import LLMConfigError


def test_openai_http_client_not_created_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.llm.openai_http_client import openai_client_kwargs

    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)

    assert openai_client_kwargs() == {}


def test_openai_http_client_rejects_disabled_tls_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.llm.openai_http_client import openai_client_kwargs

    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    with pytest.raises(LLMConfigError, match="DISABLE_SSL_VERIFY is not allowed in production"):
        openai_client_kwargs()
