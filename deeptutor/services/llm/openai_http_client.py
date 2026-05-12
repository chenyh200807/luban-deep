"""HTTP client helpers for OpenAI-compatible SDK providers."""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from deeptutor.services.llm.exceptions import LLMConfigError
from deeptutor.services.runtime_env import env_flag, is_production_environment

logger = logging.getLogger(__name__)
_warning_lock = threading.Lock()
_warning_logged = False


def disable_ssl_verify_enabled() -> bool:
    if not env_flag("DISABLE_SSL_VERIFY", default=False):
        return False
    if is_production_environment():
        raise LLMConfigError("DISABLE_SSL_VERIFY is not allowed in production")
    global _warning_logged
    with _warning_lock:
        if not _warning_logged:
            logger.warning(
                "SSL verification is disabled via DISABLE_SSL_VERIFY. This is unsafe "
                "and must not be used in production environments."
            )
            _warning_logged = True
    return True


def build_openai_http_client(**kwargs: Any) -> httpx.AsyncClient | None:
    if not disable_ssl_verify_enabled():
        return None
    return httpx.AsyncClient(verify=False, **kwargs)  # nosec B501


def openai_client_kwargs(**httpx_kwargs: Any) -> dict[str, Any]:
    client = build_openai_http_client(**httpx_kwargs)
    return {"http_client": client} if client is not None else {}
