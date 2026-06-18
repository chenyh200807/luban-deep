"""Runtime route inventory — PR-0 baseline gate.

Loads the FastAPI app and reflects every HTTP / WebSocket route's dependency
tree (router-level + endpoint-level) to determine whether each endpoint is
actually behind an authentication dependency, a rate-limit dependency, or is
explicitly public.

PR-0 is *report-only*: emit JSON to stdout. Subsequent PRs (PR-1a/PR-1b) will
compare against this baseline and fail CI on any new anonymous endpoint that
isn't on an explicit public manifest.

Why this exists (codex review R1): a static `grep APIRouter(` gate is a lint,
not a security boundary — alias imports, wrappers, `include_router` chains,
and test fixtures can bypass it. Reflecting `app.routes[*].dependant` at runtime
is the only way to enumerate the real authorization surface.

Usage:
    .venv/bin/python scripts/ci/runtime_route_inventory.py > docs/audit/route_inventory.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Ensure repo root is importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Dependency name buckets: anything whose `.__name__` is in these sets counts
# as an auth / rate-limit dep. Update when SR1 lands `secure_router` / `secure_ws_endpoint`.
_AUTH_USER_DEPS = {"get_current_user", "resolve_auth_context"}
_AUTH_ADMIN_DEPS = {"require_admin", "require_metrics_access"}
_AUTH_SELF_DEPS = {"require_self_or_admin"}
_AUTH_BI_DEPS = {"require_bi_access"}
_RATE_LIMIT_DEPS = {"route_rate_limit", "enforce_websocket_rate_limit"}


def _collect_dep_names(dependant: Any) -> list[str]:
    """Recursively walk a fastapi Dependant tree, collecting callable names."""
    names: list[str] = []
    for sub in getattr(dependant, "dependencies", []) or []:
        call = getattr(sub, "call", None)
        if call is not None:
            names.append(getattr(call, "__name__", repr(call)))
        names.extend(_collect_dep_names(sub))
    return names


def _collect_rate_limit_markers(dependant: Any) -> list[str]:
    """Collect dependencies created by the rate-limit authority factories."""
    scopes: list[str] = []
    for sub in getattr(dependant, "dependencies", []) or []:
        call = getattr(sub, "call", None)
        if bool(getattr(call, "__deeptutor_rate_limit__", False)):
            scope = str(getattr(call, "__deeptutor_rate_limit_scope__", "") or "route_rate_limit")
            scopes.append(scope)
        scopes.extend(_collect_rate_limit_markers(sub))
    return scopes


def _classify(has_auth: bool, has_rate: bool, is_public_marker: bool) -> str:
    if has_auth:
        return "secure_authed"
    if is_public_marker:
        return "explicit_public"
    if has_rate:
        return "anonymous_ratelimited_only"
    return "anonymous_no_ratelimit"


def _auth_kind(dep_names: set[str]) -> str | None:
    if dep_names & _AUTH_ADMIN_DEPS:
        return "admin"
    if dep_names & _AUTH_SELF_DEPS:
        return "self_or_admin"
    if dep_names & _AUTH_BI_DEPS:
        return "bi"
    if dep_names & _AUTH_USER_DEPS:
        return "user"
    return None


def build_inventory() -> dict[str, Any]:
    from fastapi.routing import APIRoute, APIWebSocketRoute  # local import

    from deeptutor.api.main import app  # noqa: WPS433 — app must be loaded after sys.path

    # SR1 manifest cross-check (graceful if manifest missing — e.g. baseline pre-PR-1a)
    try:
        from deeptutor.api._public_manifest import is_public as _is_public_path
    except ImportError:
        def _is_public_path(method: str, path: str) -> str | None:  # type: ignore[misc]
            return None

    endpoints: list[dict[str, Any]] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            kind = "http"
            methods = sorted(route.methods or [])
            dependant = route.dependant
            path = route.path
            endpoint_name = f"{route.endpoint.__module__}.{route.endpoint.__name__}"
        elif isinstance(route, APIWebSocketRoute):
            kind = "websocket"
            methods = ["WS"]
            dependant = route.dependant
            path = route.path
            endpoint_name = f"{route.endpoint.__module__}.{route.endpoint.__name__}"
        else:
            continue  # Mount, Route, etc. — not API surface

        dep_names = set(_collect_dep_names(dependant))
        rate_limit_scopes = sorted(set(_collect_rate_limit_markers(dependant)))
        has_auth = bool(
            dep_names
            & (_AUTH_USER_DEPS | _AUTH_ADMIN_DEPS | _AUTH_SELF_DEPS | _AUTH_BI_DEPS)
        )
        has_rate = bool(dep_names & _RATE_LIMIT_DEPS) or bool(rate_limit_scopes)

        for method in methods:
            public_reason = _is_public_path(method, path)
            is_public_marker = public_reason is not None
            endpoints.append(
                {
                    "path": path,
                    "method": method,
                    "kind": kind,
                    "endpoint": endpoint_name,
                    "all_dependency_names": sorted(dep_names),
                    "rate_limit_scopes": rate_limit_scopes,
                    "has_auth_dep": has_auth,
                    "auth_dep_kind": _auth_kind(dep_names),
                    "has_rate_limit_dep": has_rate,
                    "is_public_marker": is_public_marker,
                    "public_reason": public_reason,
                    "classification": _classify(has_auth, has_rate, is_public_marker),
                }
            )

    endpoints.sort(key=lambda e: (e["path"], e["method"]))

    summary: dict[str, Any] = {
        "by_classification": {
            "secure_authed": 0,
            "explicit_public": 0,
            "anonymous_ratelimited_only": 0,
            "anonymous_no_ratelimit": 0,
        },
        "by_kind": {"http": 0, "websocket": 0},
        "anonymous_paths": [],
        "unmarked_anonymous_paths": [],  # anonymous + not in public_manifest (the real risk)
    }
    for ep in endpoints:
        summary["by_classification"][ep["classification"]] += 1
        summary["by_kind"][ep["kind"]] += 1
        if not ep["has_auth_dep"]:
            summary["anonymous_paths"].append(
                f"{ep['method']} {ep['path']} ({ep['classification']})"
            )
            if not ep["is_public_marker"]:
                summary["unmarked_anonymous_paths"].append(
                    f"{ep['method']} {ep['path']}"
                )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fastapi_routes_total": len(app.routes),
        "api_endpoints_total": len(endpoints),
        "summary": summary,
        "endpoints": endpoints,
    }


def main() -> int:
    inventory = build_inventory()
    json.dump(inventory, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
