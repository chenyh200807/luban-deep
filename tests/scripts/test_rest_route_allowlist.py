"""TDD for scripts/ci/check_rest_route_allowlist.py — the REST existence gate.

WS already has an existence allowlist (check_websocket_route_allowlist.py +
contracts/index.yaml websocket_routes). REST only had auth gates (secure_router)
and a *report-only* runtime_route_inventory — no "a new REST router must be
registered" existence闸. This guard closes that gap, mirroring the WS allowlist
pattern EXACTLY and reflecting the live FastAPI app so include_router chains /
alias imports cannot bypass it.

It does NOT overlap the WS guard: the WS guard reflects ``APIWebSocketRoute``;
this one reflects ``APIRoute`` (HTTP). The grain is the ROUTER MOUNT PREFIX (the
leading static path segments, where ``include_router(prefix=...)`` mounts), so the
gate catches "a NEW router mounted that no one registered" — the existence
question — without re-litigating every leaf path (the report-only inventory
already enumerates those for auth).

These tests pin the pure ``evaluate_*`` check (no app import) so they are
deterministic and touch no parallel WIP source.
"""

from __future__ import annotations

from scripts.ci.check_rest_route_allowlist import (
    evaluate_rest_allowlist,
    load_rest_route_allowlist,
    mount_prefix,
)


# ── mount_prefix: leading STATIC segments only, capped ───────────────────────
def test_mount_prefix_keeps_leading_static_segments() -> None:
    assert mount_prefix("/api/v1/bi/overview") == "/api/v1/bi"
    assert mount_prefix("/api/v1/member/{user_id}/ops-action") == "/api/v1/member"
    # path param at segment 3 → prefix stops before it
    assert mount_prefix("/api/attachments/{session_id}/{f}") == "/api/attachments"
    assert mount_prefix("/healthz") == "/healthz"
    assert mount_prefix("/") == "/"


# ── Registry loads the single canonical allowlist ────────────────────────────
def test_registry_loads_http_route_prefixes() -> None:
    allow = load_rest_route_allowlist()
    # the grandfathered存量 mounts are present
    assert "/api/v1/bi" in allow
    assert "/api/v1/member" in allow
    assert "/api/v1/knowledge" in allow
    assert "/healthz" in allow


# ── FAIL: a NEW unregistered mount prefix (止血 — existence gate) ────────────
def test_fail_new_unregistered_mount() -> None:
    # min repro: a brand-new router mounted at an unlisted prefix.
    registered = ["/api/v1/bi", "/api/v1/member", "/healthz"]
    reflected = ["/api/v1/bi", "/api/v1/member", "/api/v1/shadow_admin", "/healthz"]
    ok, message = evaluate_rest_allowlist(reflected, registered)
    assert ok is False
    assert "unlisted production REST route mount" in message
    assert "/api/v1/shadow_admin" in message


def test_pass_all_mounts_registered() -> None:
    registered = ["/api/v1/bi", "/api/v1/member", "/healthz"]
    reflected = ["/api/v1/bi", "/api/v1/member", "/healthz"]
    ok, message = evaluate_rest_allowlist(reflected, registered)
    assert ok is True
    assert "passed" in message


def test_extra_allowlist_entry_is_allowed() -> None:
    # an allowlist entry not currently reflected (e.g. a behind-flag router) does
    # NOT fail — the gate only fails on a reflected mount that is unregistered.
    registered = ["/api/v1/bi", "/api/v1/member", "/api/v1/legacy_behind_flag"]
    reflected = ["/api/v1/bi", "/api/v1/member"]
    ok, _ = evaluate_rest_allowlist(reflected, registered)
    assert ok is True


# ── load-bearing: the live app's reflected mounts are all registered ─────────
def test_live_app_reflected_mounts_all_registered() -> None:
    # full enforcement: reflect the real production HTTP surface and assert every
    # mount is grandfathered (zero false positives). Skips gracefully if server
    # deps are unavailable (mirrors the WS guard's degrade-to-skip).
    from scripts.ci.check_rest_route_allowlist import (
        evaluate_rest_route_allowlist,
        reflect_production_http_mounts,
    )

    try:
        reflect_production_http_mounts()
    except Exception:  # noqa: BLE001 — server deps absent in light job
        import pytest

        pytest.skip("app import unavailable — full enforcement runs in CI step")
    ok, message = evaluate_rest_route_allowlist()
    assert ok is True, message
    assert "passed" in message
