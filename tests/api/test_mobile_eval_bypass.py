from __future__ import annotations

from deeptutor.api.routers import mobile
from deeptutor.services.session.turn_runtime import _normalize_billing_context


def _payload(*, eval_bypass_verified: bool, config: dict | None = None) -> dict:
    body = mobile.MobileStartTurnRequest(query="判一道题", config=config)
    return mobile._build_mobile_turn_payload(
        body=body,
        authenticated_user_id="uuid-user-1",
        wallet_user_id="uuid-user-1",
        query="判一道题",
        eval_bypass_verified=eval_bypass_verified,
    )


def test_payload_stamps_marker_only_when_verified() -> None:
    verified = _payload(eval_bypass_verified=True)
    assert verified["config"]["billing_context"]["eval_bypass"] == "verified"

    plain = _payload(eval_bypass_verified=False)
    assert "eval_bypass" not in plain["config"]["billing_context"]


def test_client_cannot_inject_eval_bypass_marker() -> None:
    # SECURITY INVARIANT: billing_context is server-authored. A client that tries
    # to smuggle eval_bypass via body.config must NOT have it honoured.
    injected = _payload(
        eval_bypass_verified=False,
        config={"billing_context": {"eval_bypass": "verified", "source": "wx_miniprogram"}},
    )
    assert "eval_bypass" not in injected["config"]["billing_context"]
    # Server identity is what gets used, not any client-supplied billing_context.
    assert injected["config"]["billing_context"]["user_id"] == "uuid-user-1"


def test_normalize_billing_context_preserves_only_verified_marker() -> None:
    base = {"source": "wx_miniprogram", "user_id": "qa_x"}
    assert _normalize_billing_context({**base, "eval_bypass": "verified"})["eval_bypass"] == "verified"
    # Any non-"verified" value is dropped (no marker leaks through normalization).
    assert "eval_bypass" not in _normalize_billing_context({**base, "eval_bypass": "1"})
    assert "eval_bypass" not in _normalize_billing_context(base)


def test_capture_honours_server_authored_eval_bypass_marker() -> None:
    # The post-turn capture skips the wallet debit (returns before any wallet call)
    # only when the server-authored marker is present.
    from deeptutor.services.session.turn_runtime import TurnRuntimeManager

    mgr = TurnRuntimeManager()
    out = mgr._capture_mobile_points(
        {"source": "wx_miniprogram", "wallet_user_id": "qa_x", "eval_bypass": "verified"},
        "答案内容",
        turn_id="t1",
    )
    assert out is not None
    assert out["status"] == "bypassed"
    assert out["reason"] == "eval_billing_bypass"
