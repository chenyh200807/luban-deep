from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import httpx
import websockets


def _build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


async def load_metrics_snapshot_async(*, api_base_url: str) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/metrics"
    async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
        response = await client.get(url)
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


async def _try_load_metrics_snapshot_async(*, api_base_url: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = f"{api_base_url.rstrip('/')}/metrics"
    try:
        snapshot = await load_metrics_snapshot_async(api_base_url=api_base_url)
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


async def run_unified_ws_smoke(
    *,
    api_base_url: str,
    message: str,
    language: str = "zh",
    capability: str | None = None,
    timeout_seconds: float = 60.0,
    connector_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    ws_url = _build_ws_url(api_base_url)
    connect = connector_factory or (lambda url: websockets.connect(url))
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

    metrics_after, metrics_capture = await _try_load_metrics_snapshot_async(api_base_url=api_base_url)
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
        "passed": passed,
    }
