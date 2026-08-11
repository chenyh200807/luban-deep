from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from deeptutor.services.config import get_env_store

_GOVERNED_API_BASE_URLS_KEY = "DEEPTUTOR_OBSERVABILITY_GOVERNED_API_BASE_URLS"


def resolve_governed_metrics_urls() -> tuple[str, ...]:
    env_store = get_env_store()
    raw = str(
        os.getenv(_GOVERNED_API_BASE_URLS_KEY)
        or env_store.get(_GOVERNED_API_BASE_URLS_KEY, "")
        or ""
    )
    urls = {
        f"{base_url.rstrip('/')}/metrics"
        for item in raw.split(",")
        if (base_url := str(item or "").strip())
        and _is_public_https_url(base_url)
    }
    return tuple(sorted(urls))


def _is_public_https_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    if parsed.hostname.lower() == "localhost":
        return False
    try:
        addresses = {
            str(sockaddr[0]).split("%", maxsplit=1)[0]
            for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, ValueError):
        return False
    try:
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False


def resolve_metrics_token(metrics_token: str | None = None) -> str | None:
    candidate = str(
        metrics_token
        or os.getenv("DEEPTUTOR_METRICS_TOKEN")
        or get_env_store().get("DEEPTUTOR_METRICS_TOKEN", "")
        or ""
    ).strip()
    return candidate or None


def metrics_headers(metrics_token: str | None = None) -> dict[str, str] | None:
    token = resolve_metrics_token(metrics_token)
    if not token:
        return None
    return {"X-Metrics-Token": token}


def build_metrics_error_provenance(*, api_base_url: str, exc: Exception) -> dict[str, Any]:
    status_code = None
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status_code = int(exc.response.status_code)
    return {
        "source": "live_metrics_endpoint",
        "url": f"{api_base_url.rstrip('/')}/metrics",
        "fallback_used": False,
        "status_code": status_code,
        "error": f"{type(exc).__name__}: {exc}",
        "error_type": type(exc).__name__,
    }


def load_metrics_snapshot(
    *,
    api_base_url: str,
    metrics_json: str | None = None,
    metrics_token: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    if metrics_json:
        target = Path(metrics_json).expanduser().resolve()
        if not target.exists():
            raise FileNotFoundError(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("Metrics snapshot must be a JSON object")
        payload["observability_metrics_provenance"] = {
            "source": "metrics_json",
            "url": "",
            "fallback_used": False,
            "status_code": None,
            "error": "",
        }
        return payload

    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.get(
            f"{api_base_url.rstrip('/')}/metrics",
            headers=metrics_headers(metrics_token),
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("metrics endpoint must return JSON object")
    payload["observability_metrics_provenance"] = {
        "source": "live_metrics_endpoint",
        "url": f"{api_base_url.rstrip('/')}/metrics",
        "fallback_used": False,
        "status_code": 200,
        "error": "",
    }
    return payload
