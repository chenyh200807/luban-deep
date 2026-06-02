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
    WriteEndpoint(
        key="feedback.ai.triage",
        method="POST",
        path_template="/api/v1/bi/feedback/{feedback_id}/triage",
        requires_idempotency=True,
        description=(
            "AI feedback triage: admin marks a feedback item open, triaged, "
            "or ignored. Backend updates ai_feedback metadata and appends "
            "feedback_triage to member_console audit_log with idempotency dedup."
        ),
        audit_action="feedback_triage",
    ),
    WriteEndpoint(
        key="feedback.invite_test.update",
        method="PATCH",
        path_template="/api/v1/bi/invite-test/applications/{application_id}",
        requires_idempotency=True,
        description=(
            "Invite-test application edit: growth ops updates applicant "
            "status, contact/profile corrections, callback preference, and "
            "operator note. Backend updates invite_test_applications and "
            "records invite_test_application_update audit with idempotency "
            "dedup."
        ),
        audit_action="invite_test_application_update",
    ),
    WriteEndpoint(
        key="feedback.invite_test.delete",
        method="DELETE",
        path_template="/api/v1/bi/invite-test/applications/{application_id}",
        requires_idempotency=True,
        description=(
            "Invite-test application delete: growth ops soft-deletes an "
            "application by archiving it. Backend hides archived applications "
            "from the default pool and records invite_test_application_delete "
            "audit with idempotency dedup."
        ),
        audit_action="invite_test_application_delete",
    ),
    WriteEndpoint(
        key="member.ops_action.record",
        method="POST",
        path_template="/api/v1/bi/member/{user_id}/ops-action",
        requires_idempotency=True,
        description=(
            "Member low-risk ops action: mark contacted, add an ops note, or "
            "join follow-up queue. Backend writes an ops_action note and "
            "ops_action_result audit with idempotency dedup."
        ),
        audit_action="ops_action_result",
    ),
    WriteEndpoint(
        key="bi.export.request",
        method="POST",
        path_template="/api/v1/bi/export-jobs",
        requires_idempotency=True,
        description=(
            "BI export request: admin asks for a scrubbed export job. "
            "Backend records bi_export_request audit with dataset, filters, "
            "scrubbing, rate-limit metadata, and idempotency dedup before any "
            "export job is shown in the UI. product_behavior_raw is the only "
            "P0 raw_mode=true dataset; all other datasets remain scrubbed. "
            "P0 records the raw export job and audit trail; actual raw CSV "
            "extraction is deferred until the export worker supports behavior "
            "rows."
        ),
        audit_action="bi_export_request",
    ),
)


def write_endpoint_by_key(key: str) -> WriteEndpoint:
    for endpoint in WRITE_ENDPOINTS:
        if endpoint.key == key:
            return endpoint
    raise KeyError(f"Unknown BI v2 write endpoint: {key}")
