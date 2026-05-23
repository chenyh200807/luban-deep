"""Single backend authority for every BI v2 audited write endpoint.

Round 4 S2 closes RC-α (single-sided contract) and RC-β (untyped UI bypass) at
the same time:

  * Backend tests iterate this registry to assert each `requires_idempotency`
    endpoint has both router-level `X-Idempotency-Key` enforcement and a
    service-level dedup path.
  * Frontend `web/lib/bi-v2-write-endpoints.generated.ts` is generated from
    this file (see `scripts/gen_bi_write_endpoints_ts.py`). `useAuditedAction`
    narrows its `endpoint.key` parameter to `keyof typeof WRITE_ENDPOINTS`
    so any TypeScript caller wanting to hit an unregistered URL fails at
    compile time, not just at smoke time.

Adding a new write path:
  1. Append a `WriteEndpoint(...)` entry below.
  2. `python -m scripts.gen_bi_write_endpoints_ts` to regenerate the TS mirror.
  3. Add the router handler + service implementation. Tests
     ``tests/api/test_bi_write_endpoints_registry.py`` iterate the registry
     and fail loudly until both layers exist.

The registry is intentionally tiny (only real, shipped routes) — see
``docs/zh/bi/bi-backoffice-v2-rollout-runbook.md`` for the deferred Stage 2
write paths registered as `xfail` notes rather than placeholder entries.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WriteEndpoint:
    # Stable client-facing key, scoped by domain (member.* / wallet.* / ...).
    # Used as the discriminant in useAuditedAction({ key: ... }).
    key: str
    # HTTP method (POST / PATCH / DELETE).
    method: str
    # FastAPI path template (matches router.add_api_route path).
    path_template: str
    # Whether the route must reject requests missing X-Idempotency-Key.
    requires_idempotency: bool
    # Human-readable description surfaced in the TS registry comments.
    description: str
    # Free-form audit_log `action` string used by the service layer. Pinned in
    # the registry so backend dedup tests + frontend audit ids stay aligned.
    audit_action: str


# Append-only. Removing or renaming an entry is a breaking contract change —
# coordinate with both the frontend codegen and the rollout runbook §7 before
# editing.
WRITE_ENDPOINTS: tuple[WriteEndpoint, ...] = (
    WriteEndpoint(
        key="member.conversation.view_full",
        method="POST",
        path_template="/api/v1/member/{user_id}/conversations/{session_id}/view-audit",
        requires_idempotency=True,
        description=(
            "Privacy audit: admin requests full chat replay for a member. "
            "Body must include reason (≥ 4 chars or one of the 5 whitelisted "
            "reason codes). Backend appends to audit_log + dedupes by "
            "(action, X-Idempotency-Key)."
        ),
        audit_action="conversation_view",
    ),
)


def write_endpoint_by_key(key: str) -> WriteEndpoint:
    for endpoint in WRITE_ENDPOINTS:
        if endpoint.key == key:
            return endpoint
    raise KeyError(f"Unknown BI v2 write endpoint: {key}")
