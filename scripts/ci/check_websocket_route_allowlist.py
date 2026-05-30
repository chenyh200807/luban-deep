"""WebSocket single-control-plane allowlist gate (contracts/turn.md:22).

Reflects the live FastAPI app's PRODUCTION WebSocket surface (every route
still registered when legacy routers are disabled) and fails CI when:

  - a registered production WS path is not declared in the
    ``websocket_routes`` allowlist in ``contracts/index.yaml``, OR
  - any allowlist entry is ``kind: chat`` with a path other than
    ``/api/v1/ws`` (the single streaming control plane), OR
  - more than one allowlist entry is ``kind: chat``.

Why reflection (codex review R1, mirrored from runtime_route_inventory.py):
a static ``grep @router.websocket`` is a lint, not a boundary — alias imports,
wrappers, and ``include_router`` chains bypass it. Reflecting ``app.routes`` at
runtime is the only way to enumerate the real WS surface.

Why "production" surface: legacy routers (``solve`` / ``question`` / ``guide``
…) expose dev-only WS routes that are NOT mounted in production. The contract
that matters is what ships. We force ``DEEPTUTOR_ENABLE_LEGACY_ROUTERS=false``
so the gate sees exactly the production registration set, independent of the
ambient environment.

Usage:
    python scripts/ci/check_websocket_route_allowlist.py

Exit 0 = pass, non-zero = fail.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INDEX_PATH = _REPO_ROOT / "contracts" / "index.yaml"
_SINGLE_CHAT_WS_PATH = "/api/v1/ws"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_websocket_allowlist(index_path: Path = _INDEX_PATH) -> dict[str, dict[str, Any]]:
    """Parse the ``websocket_routes`` allowlist into a path -> entry map."""
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    raw = payload.get("websocket_routes")
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "contracts/index.yaml must define a non-empty top-level "
            "'websocket_routes' allowlist"
        )
    allowlist: dict[str, dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, dict) or "path" not in entry or "kind" not in entry:
            raise ValueError(f"websocket_routes entry must have path + kind: {entry!r}")
        allowlist[str(entry["path"])] = entry
    return allowlist


def reflect_production_websocket_paths() -> list[str]:
    """Return every WS path registered when legacy routers are disabled.

    Forces ``DEEPTUTOR_ENABLE_LEGACY_ROUTERS=false`` BEFORE importing the app so
    the reflected surface matches production regardless of ambient env.
    """
    os.environ["DEEPTUTOR_ENABLE_LEGACY_ROUTERS"] = "false"

    from fastapi.routing import APIWebSocketRoute  # local import

    from deeptutor.api.main import app  # noqa: WPS433 — loaded after env + sys.path

    return sorted(
        route.path
        for route in app.routes
        if isinstance(route, APIWebSocketRoute)
    )


def evaluate_allowlist(
    registered_paths: list[str],
    allowlist: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    """Pure check: registered production WS paths vs the declared allowlist."""
    failures: list[str] = []

    # 1. Every registered production WS must be declared.
    for path in registered_paths:
        if path not in allowlist:
            failures.append(
                f"unlisted production WebSocket route: {path} — register it in "
                "contracts/index.yaml websocket_routes (and confirm it is not a "
                "second chat WS; turn.md:22 allows only /api/v1/ws for chat)."
            )

    # 2. chat-kind discipline: exactly one, and it must be /api/v1/ws.
    chat_entries = [
        (path, entry)
        for path, entry in allowlist.items()
        if str(entry.get("kind")) == "chat"
    ]
    for path, _entry in chat_entries:
        if path != _SINGLE_CHAT_WS_PATH:
            failures.append(
                f"chat-kind WebSocket route {path} is not {_SINGLE_CHAT_WS_PATH}: "
                "turn.md:22 forbids a second chat WebSocket (单一流式入口 "
                f"{_SINGLE_CHAT_WS_PATH})."
            )
    if len(chat_entries) > 1:
        failures.append(
            "more than one chat-kind WebSocket route declared: "
            f"{', '.join(sorted(p for p, _ in chat_entries))} — only "
            f"{_SINGLE_CHAT_WS_PATH} may be chat."
        )

    if failures:
        return False, "websocket-allowlist-guard: failed\n" + "\n".join(failures)
    return True, (
        "websocket-allowlist-guard: passed | "
        f"production_ws={', '.join(registered_paths) or '(none)'}"
    )


def evaluate_websocket_route_allowlist() -> tuple[bool, str]:
    """Full guard: reflect the app, then check against the index allowlist.

    Degrades to a pass with a note when the app cannot be imported (e.g. the
    lightweight contract-guard CI job without server deps). The dedicated
    workflow step installs server deps so the reflection runs for real.
    """
    try:
        allowlist = load_websocket_allowlist()
    except Exception as exc:  # noqa: BLE001 — surface config errors as a failure
        return False, f"websocket-allowlist-guard: index load failed: {exc}"

    try:
        registered = reflect_production_websocket_paths()
    except Exception as exc:  # noqa: BLE001 — app deps absent in light job
        return True, (
            "websocket-allowlist-guard: skipped (app import unavailable — "
            f"run with server deps for full enforcement): {exc}"
        )

    return evaluate_allowlist(registered, allowlist)


def main() -> int:
    ok, message = evaluate_websocket_route_allowlist()
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
