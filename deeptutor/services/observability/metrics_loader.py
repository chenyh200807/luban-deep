from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from deeptutor.services.config import get_env_store


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
    return payload
