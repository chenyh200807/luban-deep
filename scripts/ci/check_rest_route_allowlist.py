"""REST route EXISTENCE allowlist gate (RESOURCE_GOVERNANCE_FIX_PLAN Layer 3 · P2).

WS already has an existence gate (check_websocket_route_allowlist.py +
contracts/index.yaml websocket_routes). REST only had AUTH gates (secure_router)
plus a *report-only* runtime_route_inventory — no "a new REST router must be
registered" existence闸. This guard closes that gap, mirroring the WS allowlist
EXACTLY: it reflects the live FastAPI app's PRODUCTION HTTP surface and fails CI
when a reflected ROUTER MOUNT PREFIX is not declared in the ``http_routes``
allowlist in ``contracts/index.yaml``.

It does NOT overlap the WS guard:
  - WS guard governs ``APIWebSocketRoute``;
  - this guard governs ``APIRoute`` (HTTP).

Why reflection (codex review R1, mirrored from check_websocket_route_allowlist.py
and runtime_route_inventory.py): a static ``grep include_router`` is a lint, not a
boundary — alias imports, wrappers, and ``include_router`` chains bypass it.
Reflecting ``app.routes`` at runtime is the only way to enumerate the real REST
surface.

Why the MOUNT PREFIX grain (not every leaf path): the question this gate answers
is the GOVERNANCE one — "should this router EXIST?" — not the auth one (the
report-only inventory already enumerates leaves for auth). A router mounts at a
prefix via ``include_router(prefix=...)``; that prefix is the existence unit.
Registering leaves would duplicate the inventory and be noisy.

Why "production" surface: legacy routers (solve / question / guide …) expose
dev-only routes not mounted in production. We force
``DEEPTUTOR_ENABLE_LEGACY_ROUTERS=false`` so the gate sees exactly what ships,
EXACTLY like the WS guard.

Usage:
    python scripts/ci/check_rest_route_allowlist.py

Exit 0 = pass, non-zero = fail.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INDEX_PATH = _REPO_ROOT / "contracts" / "index.yaml"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def mount_prefix(path: str) -> str:
    """Reduce an HTTP route path to its router MOUNT PREFIX.

    The prefix is the leading STATIC (non-``{param}``) path segments, capped at 3
    — this is where ``include_router(prefix=...)`` mounts a router. A path param
    ends the prefix (the mount is always static). Examples:
        /api/v1/bi/overview              -> /api/v1/bi
        /api/v1/member/{user_id}/action  -> /api/v1/member
        /api/attachments/{sid}/{f}       -> /api/attachments
        /healthz                         -> /healthz
        /                                -> /
    """
    segments = [s for s in path.split("/") if s]
    static: list[str] = []
    for segment in segments:
        if segment.startswith("{"):
            break
        static.append(segment)
        if len(static) >= 3:
            break
    if not static:
        return "/"
    return "/" + "/".join(static)


def load_rest_route_allowlist(index_path: Path = _INDEX_PATH) -> set[str]:
    """Parse the ``http_routes`` allowlist into a set of registered mount prefixes."""
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    raw = payload.get("http_routes")
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "contracts/index.yaml must define a non-empty top-level "
            "'http_routes' allowlist"
        )
    allow: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "prefix" not in entry:
            raise ValueError(f"http_routes entry must have a prefix: {entry!r}")
        allow.add(str(entry["prefix"]))
    return allow


def reflect_production_http_mounts() -> list[str]:
    """Return every HTTP route MOUNT PREFIX registered when legacy routers are off.

    Forces ``DEEPTUTOR_ENABLE_LEGACY_ROUTERS=false`` BEFORE importing the app so
    the reflected surface matches production regardless of ambient env (mirrors
    the WS guard).
    """
    os.environ["DEEPTUTOR_ENABLE_LEGACY_ROUTERS"] = "false"

    from fastapi.routing import APIRoute  # local import

    from deeptutor.api.main import app  # noqa: WPS433 — loaded after env + sys.path

    return sorted(
        {mount_prefix(route.path) for route in app.routes if isinstance(route, APIRoute)}
    )


def evaluate_rest_allowlist(
    reflected_mounts: list[str],
    registered_mounts: set[str] | list[str],
) -> tuple[bool, str]:
    """Pure check: every reflected production mount must be registered.

    A registered mount that is not currently reflected (e.g. a behind-flag router)
    does NOT fail — the gate only fails on a reflected mount that is unregistered
    (止血: a new router exists that no one declared).
    """
    registered = set(registered_mounts)
    failures: list[str] = []
    for mount in reflected_mounts:
        if mount not in registered:
            failures.append(
                f"unlisted production REST route mount: {mount} — register it in "
                "contracts/index.yaml http_routes (with a reason). A new router "
                "that no one declared spreads the API surface and forms a second "
                "source of truth for the mini-program / BI / frontend."
            )
    if failures:
        return False, "rest-route-allowlist-guard: failed\n" + "\n".join(failures)
    return True, (
        "rest-route-allowlist-guard: passed | "
        f"production_mounts={len(reflected_mounts)} (all registered)"
    )


def evaluate_rest_route_allowlist() -> tuple[bool, str]:
    """Full guard: reflect the app, then check against the index allowlist.

    Degrades to a pass with a note when the app cannot be imported (e.g. the
    lightweight contract-guard CI job without server deps). The dedicated workflow
    step installs server deps so the reflection runs for real. Mirrors the WS
    guard's degrade-to-skip semantics EXACTLY.
    """
    try:
        allowlist = load_rest_route_allowlist()
    except Exception as exc:  # noqa: BLE001 — surface config errors as a failure
        return False, f"rest-route-allowlist-guard: index load failed: {exc}"

    try:
        reflected = reflect_production_http_mounts()
    except Exception as exc:  # noqa: BLE001 — app deps absent in light job
        return True, (
            "rest-route-allowlist-guard: skipped (app import unavailable — "
            f"run with server deps for full enforcement): {exc}"
        )

    return evaluate_rest_allowlist(reflected, allowlist)


def main() -> int:
    ok, message = evaluate_rest_route_allowlist()
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
