from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import httpx
import websockets

from deeptutor.services.observability.metrics_loader import metrics_headers


_EVAL_USER_PREFIXES = ("qa_eval_", "eval_", "qa_")
_EVAL_IDENTITY = {
    "account_kind": "eval_runner",
    "actor_type": "machine",
    "created_by": "eval_runner",
    "is_internal_test": True,
}


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


async def load_metrics_snapshot_async(*, api_base_url: str, metrics_token: str | None = None) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/metrics"
    async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
        response = await client.get(url, headers=metrics_headers(metrics_token))
        response.raise_for_status()
        return response.json()


def _build_metrics_capture(
    *,
    url: str,
    ok: bool,
    status_code: int | None = None,
    error: str = "",
) -> dict[str, Any]:
    return {
        "url": url,
        "ok": ok,
        "status_code": status_code,
        "error": error,
    }


async def _try_load_metrics_snapshot_async(
    *,
    api_base_url: str,
    metrics_token: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = f"{api_base_url.rstrip('/')}/metrics"
    try:
        kwargs: dict[str, Any] = {"api_base_url": api_base_url}
        if "metrics_token" in inspect.signature(load_metrics_snapshot_async).parameters:
            kwargs["metrics_token"] = metrics_token
        snapshot = await load_metrics_snapshot_async(**kwargs)
    except httpx.HTTPStatusError as exc:
        return None, _build_metrics_capture(
            url=url,
            ok=False,
            status_code=exc.response.status_code if exc.response is not None else None,
            error=f"{exc.__class__.__name__}: {exc}",
        )
    except Exception as exc:
        return None, _build_metrics_capture(
            url=url,
            ok=False,
            error=f"{exc.__class__.__name__}: {exc}",
        )
    return snapshot, _build_metrics_capture(url=url, ok=True, status_code=200)


async def verify_eval_runner_identity(
    *, api_base_url: str, auth_token: str, timeout_seconds: float = 5.0
) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    url = f"{api_base_url.rstrip('/')}/api/v1/auth/profile"
    if not token:
        return {"verified": False, "url": url, "reason": "missing_token", "profile": {}}
    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            profile = response.json()
    except Exception as exc:
        return {
            "verified": False,
            "url": url,
            "reason": "profile_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "profile": {},
        }
    if not isinstance(profile, dict):
        return {"verified": False, "url": url, "reason": "profile_not_object", "profile": {}}
    user_id = str(profile.get("auth_username") or "").strip()
    mismatches = [field for field, expected in _EVAL_IDENTITY.items() if profile.get(field) != expected]
    prefix_ok = user_id.startswith(_EVAL_USER_PREFIXES)
    return {
        "verified": prefix_ok and not mismatches,
        "url": url,
        "reason": "verified" if prefix_ok and not mismatches else "identity_not_eval_runner",
        "user_id": user_id,
        "prefix_ok": prefix_ok,
        "mismatched_fields": mismatches,
        "profile": {field: profile.get(field) for field in _EVAL_IDENTITY},
    }


async def run_unified_ws_smoke(
    *,
    api_base_url: str,
    message: str,
    language: str = "zh",
    capability: str | None = None,
    auth_token: str | None = None,
    metrics_token: str | None = None,
    timeout_seconds: float = 60.0,
    connector_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    ws_url = _build_ws_url(api_base_url)
    token = str(auth_token or "").strip()
    headers = {"Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}"} if token else None
    connect = connector_factory or (lambda url: websockets.connect(url, additional_headers=headers))
    sent_payload = {
        "type": "start_turn",
        "content": message,
        "language": language,
        "capability": capability,
        "tools": [],
        "knowledge_bases": [],
        "attachments": [],
        "config": {},
        "history_references": [],
        "notebook_references": [],
    }
    messages: list[dict[str, Any]] = []
    terminal_event: dict[str, Any] | None = None
    started_at = time.perf_counter()

    async with connect(ws_url) as websocket:
        await websocket.send(json.dumps(sent_payload, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            data = json.loads(raw)
            messages.append(data)
            if str(data.get("type") or "").strip() in {"done", "error"}:
                terminal_event = data
                break

    metrics_after, metrics_capture = await _try_load_metrics_snapshot_async(
        api_base_url=api_base_url,
        metrics_token=metrics_token or os.getenv("DEEPTUTOR_METRICS_TOKEN"),
    )
    duration_ms = (time.perf_counter() - started_at) * 1000.0
    passed = bool(terminal_event) and terminal_event.get("type") == "done"

    return {
        "run_id": f"ws-smoke-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_base_url": api_base_url.rstrip("/"),
        "ws_url": ws_url,
        "sent_payload": sent_payload,
        "messages": messages,
        "terminal_event": terminal_event,
        "duration_ms": round(duration_ms, 1),
        "metrics_after": metrics_after,
        "metrics_capture": metrics_capture,
        "auth_configured": bool(token),
        "passed": passed,
    }
