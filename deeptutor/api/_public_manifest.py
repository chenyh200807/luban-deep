"""Public endpoint manifest — explicit allowlist of unauthenticated paths.

Why this file exists: `_secure_router.py` makes authentication the default;
this manifest is the *audit-friendly* source-of-truth for what is intentionally
public. Any path listed here MUST be served by a `public_router(reason=...)`,
not a bare `APIRouter()`.

Runtime inventory gate (`scripts/ci/runtime_route_inventory.py`) cross-checks
every anonymous endpoint against this manifest. Anonymous endpoint not in the
manifest → fails inventory diff vs baseline.

Format:
    PUBLIC_PATHS: list[tuple[str_method_pattern, str_path_pattern, str_reason]]

Method pattern: regex over HTTP verb (use "*" to match any, including "WS").
Path pattern: exact match (no wildcards yet — keep simple).
"""
from __future__ import annotations

# fmt: off
PUBLIC_PATHS: list[tuple[str, str, str]] = [
    # System / k8s probes
    ("GET",  "/",                                "welcome page (no business data)"),
    ("GET",  "/healthz",                         "k8s liveness probe"),
    ("GET",  "/readyz",                          "k8s readiness probe"),
    ("GET",  "/api/v1/system/public-capabilities", "system public capability advertisement"),

    # Authentication / registration (by-design anonymous; rate-limited body-side)
    ("POST", "/api/v1/auth/login",               "anonymous login (mobile, rate-limited)"),
    ("POST", "/api/v1/auth/register",            "anonymous registration (mobile, rate-limited)"),
    ("POST", "/api/v1/auth/refresh",             "token refresh (presents old refresh token)"),
    ("POST", "/api/v1/auth/send-code",           "anonymous SMS code request (rate-limited)"),
    ("POST", "/api/v1/auth/verify-code",         "anonymous SMS verification (rate-limited)"),
    ("POST", "/api/v1/auth/reset-password",      "anonymous SMS password reset (rate-limited)"),
    ("POST", "/api/v1/wechat/mp/login",          "anonymous wechat mp phone-authorized login (rate-limited)"),
    ("POST", "/api/v1/wechat/mp/bind-phone",     "anonymous wechat mp phone bind (rate-limited)"),

    # Invite test form (PII landing, rate-limited + openid required)
    ("POST", "/api/v1/invite-test/applications", "anonymous invite test form (rate-limited)"),

    # Static UI metadata
    ("GET",  "/api/v1/agent-config/agents",                  "static UI agent registry"),
    ("GET",  "/api/v1/agent-config/agents/{agent_type}",     "static UI agent registry"),
]
# fmt: on


def is_public(method: str, path: str) -> str | None:
    """Returns the reason if (method, path) is in the manifest, None otherwise.

    Used by `runtime_route_inventory.py` to label each anonymous endpoint as
    `is_public_marker=True` + populate `public_reason` field.
    """
    for m, p, reason in PUBLIC_PATHS:
        if (m == "*" or m == method) and p == path:
            return reason
    return None
