from deeptutor.services.observability.provider_reconciliation import (
    BillingScope,
    CostBasis,
    ProviderAccountScope,
    build_reconciliation_delta,
    fingerprint_secret,
)


def test_fingerprint_secret_never_returns_raw_key() -> None:
    fingerprint = fingerprint_secret("sk-real-secret-value")

    assert fingerprint
    assert "sk-real" not in fingerprint
    assert fingerprint != "sk-real-secret-value"


def test_billing_scope_rejects_unknown_margin_scope() -> None:
    scope = BillingScope(
        provider_name="deepseek",
        charged_account_fingerprint="",
        runtime_environment="unknown",
        cost_center="unknown",
        billing_cycle="2026-06",
        raw_model="deepseek-v4-flash",
        pricing_model="deepseek-v4-flash",
        billable_unit="conversation_turn",
    )

    assert scope.margin_confidence == "untrusted"
    assert "unknown_scope" in scope.warnings


def test_cost_basis_defaults_to_list_price_for_margin() -> None:
    basis = CostBasis.for_margin()

    assert basis.primary == "list_price_cost"
    assert "net_charge_cost" in basis.supporting


def test_provider_account_scope_matches_official_key_identity() -> None:
    scope = ProviderAccountScope(
        provider_name="deepseek",
        api_key_fingerprint="sha256:abc12345",
        official_key_id="key_123",
        official_key_label="prod-main",
    )

    assert scope.matches_official_key({"key_id": "key_123"}) is True
    assert scope.matches_official_key({"key_label": "prod-main"}) is True
    assert scope.matches_official_key({"key_id": "other"}) is False


def test_build_reconciliation_delta_flags_large_official_gap() -> None:
    result = build_reconciliation_delta(
        provider_name="deepseek",
        cost_basis="list_price_cost",
        internal={
            "total_tokens": 1200,
            "currency_amounts": {"USD": 0.0001},
            "billable_turns": 1,
            "provider_calls": 1,
            "unattributed_provider_calls": 0,
        },
        official={
            "total_tokens": 1000,
            "currency_amounts": {"USD": 0.0002},
        },
        warn_ratio=0.05,
    )

    assert result["provider_name"] == "deepseek"
    assert result["cost_basis"] == "list_price_cost"
    assert result["token_delta"] == 200
    assert result["amount_delta_by_currency"]["USD"] == -0.0001
    assert result["status"] == "warning"
    assert result["cost_per_billable_turn"]["USD"] == 0.0001


def test_build_reconciliation_delta_refuses_cross_currency_amount_delta() -> None:
    result = build_reconciliation_delta(
        provider_name="deepseek",
        cost_basis="list_price_cost",
        internal={"total_tokens": 1200, "currency_amounts": {"USD": 0.0001}},
        official={"total_tokens": 1200, "currency_amounts": {"CNY": 0.0007}},
        warn_ratio=0.05,
    )

    assert result["status"] == "warning"
    assert result["amount_delta_by_currency"] == {}
    assert "currency_mismatch" in result["warnings"]
