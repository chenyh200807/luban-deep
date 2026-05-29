"""Tests for wallet ledger serialization correctness.

H2 Gate: frozen_delta_micros must not expose wrong financial data.
Since wallet_ledger has no frozen_before_micros column, the true frozen delta
cannot be computed from a single entry. The field must be absent.
"""
from __future__ import annotations

import pytest
from deeptutor.api.routers.mobile import _serialize_wallet_ledger_entry  # type: ignore[attr-defined]
from deeptutor.services.wallet.service import WalletLedgerEntry


def _make_entry(**overrides) -> WalletLedgerEntry:
    defaults = dict(
        id="test-001",
        user_id="user-001",
        event_type="capture",
        delta_micros=-500_000,
        balance_after_micros=4_500_000,
        frozen_after_micros=0,
        reference_type="session",
        reference_id="session-001",
        idempotency_key="idem-001",
        metadata={},
        created_at="2026-05-29T00:00:00Z",
    )
    defaults.update(overrides)
    return WalletLedgerEntry(**defaults)


def test_serialize_excludes_frozen_delta_micros():
    """frozen_delta_micros cannot be computed (no frozen_before in DB).
    Exposing frozen_after as frozen_delta is wrong financial data — must be absent.
    """
    result = _serialize_wallet_ledger_entry(_make_entry())
    assert "frozen_delta_micros" not in result, (
        "frozen_delta_micros must be absent: wallet_ledger has no frozen_before_micros, "
        "so frozen_after_micros != frozen_delta"
    )


def test_serialize_correct_delta_and_balance_fields():
    """Core financial fields are correctly mapped from the entry."""
    entry = _make_entry(delta_micros=-200_000, balance_after_micros=800_000, frozen_after_micros=50_000)
    result = _serialize_wallet_ledger_entry(entry)

    assert result["delta_micros"] == -200_000
    assert result["balance_after_micros"] == 800_000
    assert result["frozen_after_micros"] == 50_000
    # delta_micros and frozen_after_micros must NOT be the same key's value
    assert result.get("delta_micros") != result.get("frozen_after_micros")
