from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts.audit_wallet_projection_consistency import (
    audit_wallet_projection_consistency,
    build_wallet_projection_audit_sql,
)
from scripts.rebuild_wallet_balance_from_ledger import build_rebuild_wallet_projection_sql
from scripts.wallet_authority_common import WalletAuthorityEnv


def test_build_wallet_projection_audit_sql_checks_projection_vs_ledger() -> None:
    sql = build_wallet_projection_audit_sql(limit=25)

    assert "wallet_ledger" in sql
    assert "balance_after_micros" in sql
    assert "public.wallets" in sql
    assert "limit 25" in sql.lower()


def test_audit_wallet_projection_consistency_blocks_without_postgres(tmp_path: Path) -> None:
    summary = audit_wallet_projection_consistency(
        output_dir=tmp_path,
        env=WalletAuthorityEnv(),
        limit=10,
        execute=False,
    )

    assert summary["status"] == "blocked"
    assert (tmp_path / "wallet_projection_consistency.json").exists()


def test_build_rebuild_wallet_projection_sql_targets_single_user() -> None:
    sql = build_rebuild_wallet_projection_sql(user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9")

    assert "wallet_ledger" in sql
    assert "update public.wallets" in sql
    assert "2d9eac15-5d26-4e93-941b-9ec6345ce6d9" in sql


def test_audit_sql_adds_trustworthy_ledger_sum_crosscheck() -> None:
    """H4: the audit must cross-check balance against SUM(delta_micros), independent
    of the polluted balance_after_micros column, and report both checks."""
    sql = build_wallet_projection_audit_sql(limit=25)

    assert "sum(delta_micros)" in sql
    assert "ledger_sum_diff_count" in sql
    assert "expected_balance_micros" in sql
    # Legacy after-image check is kept for continuity (but is the polluted one).
    assert "balance_after_diff_count" in sql
    assert "duplicate_idempotency_count" in sql
    assert "identity_merge_wallet_mutation_count" in sql
    assert "suspicious_positive_delta_count" in sql
    assert "delta_micros > 0" in sql
    assert "delta_micros > 100000000000" not in sql
    assert "operator_type" in sql


@pytest.mark.parametrize(
    ("classification", "required_sql"),
    [
        (
            "verified_manual_purchase",
            (
                "event_type, '')) = 'grant'",
                "reference_type, '')) = 'purchase'",
                "reason, '')) = 'manual_membership_purchase'",
                "operator_type, '')) = 'admin'",
                "metadata->>'source', '')) = 'bi_manual_membership'",
                "metadata->>'channel', '')) = 'manual_membership'",
                "metadata->>'operator_id'",
                "idempotency_key",
            ),
        ),
        (
            "verified_payment_purchase",
            (
                "event_type, '')) = 'grant'",
                "reference_type, '')) in ('order', 'payment', 'wechat_pay')",
                "metadata->>'source', '')) = 'payment_webhook'",
                "metadata->>'payment_status'",
                "metadata->>'provider_transaction_id'",
                "operator_type, '')) = 'system'",
                "idempotency_key",
            ),
        ),
        (
            "verified_manual_reversal",
            (
                "event_type, '')) = 'refund'",
                "reference_type, '')) = 'refund'",
                "reason, '')) = 'manual_membership_reversal'",
                "metadata->>'source', '')) = 'bi_manual_membership_reversal'",
                "metadata->>'reversal_of_purchase_id'",
                "metadata->>'operator_id'",
                "idempotency_key",
            ),
        ),
        (
            "verified_payment_refund",
            (
                "event_type, '')) = 'refund'",
                "metadata->>'source', '')) = 'payment_webhook'",
                "metadata->>'refund_status'",
                "metadata->>'original_payment_id'",
                "operator_type, '')) = 'system'",
                "idempotency_key",
            ),
        ),
        (
            "verified_admin_adjustment",
            (
                "event_type, '')) = 'admin_adjust'",
                "reference_type, '')) = 'ticket'",
                "operator_type, '')) = 'admin'",
                "reason, '')) <> 'admin_adjust'",
                "metadata->>'source'",
                "metadata->>'ticket_id'",
                "metadata->>'operator_id'",
                "idempotency_key",
            ),
        ),
    ],
)
def test_positive_delta_sql_allowlist_behavior_matrix(
    classification: str,
    required_sql: tuple[str, ...],
) -> None:
    """Each allowed positive-delta class must carry its complete provenance proof.

    The generated CASE is the production SQL authority. Extracting each branch
    keeps the matrix coupled to that SQL rather than to a second Python classifier.
    """
    sql = build_wallet_projection_audit_sql(limit=25).lower()
    marker = f"then '{classification}'"
    assert marker in sql
    branch = sql.split(marker, 1)[0].rsplit("when", 1)[1]
    for required in required_sql:
        assert required in branch


def test_positive_delta_sql_is_fail_closed_and_artifacts_are_identifier_safe() -> None:
    sql = build_wallet_projection_audit_sql(limit=25).lower()
    output_sql = sql.split("select json_build_object(", 1)[1]

    assert "else 'unallowlisted_positive_delta'" in sql
    assert "where allowlist_class = 'unallowlisted_positive_delta'" in sql
    assert "row_to_json" not in output_sql
    assert "'user_id'" not in output_sql
    assert "'idempotency_key'" not in output_sql
    assert "'reference_id'" not in output_sql
    assert "'operator_id'" not in output_sql
    assert "'reason'" not in output_sql
    assert "'ledger_hash'" in output_sql
    assert "'user_hash'" in output_sql
    assert "'idempotency_hash'" in output_sql
    assert "'event_type', lower(coalesce" not in output_sql
    assert "'reference_type', lower(coalesce" not in output_sql
    assert "'operator_type', lower(coalesce" not in output_sql
    assert "else 'other'" in output_sql


def test_rebuild_sql_uses_ledger_sum_basis_not_after_image() -> None:
    """H4: rebuild must reconstruct balance from SUM(delta_micros); rebuilding from
    the latest balance_after_micros would fix-in the B1-polluted value."""
    sql = build_rebuild_wallet_projection_sql()

    assert "sum(delta_micros)" in sql
    assert "balance_micros = s.expected_balance_micros" in sql
    # Must NOT seed balance from the polluted after-image column.
    assert "balance_micros = l.balance_after_micros" not in sql


def _consistency_checks_on_fixture() -> tuple[list[str], list[str]]:
    """Run both consistency checks (sqlite-faithful) against a B1-polluted fixture.

    Fixture: a wallet that had a -30 debit recorded in the ledger but whose
    balance_micros was never decremented (still 100), and whose latest ledger
    after-image was snapshotted as the *pre-charge* balance (100) — exactly the
    B1 corruption shape. Returns (ledger_sum_flagged, balance_after_flagged).
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        create table wallets (user_id text primary key, balance_micros integer);
        create table wallet_ledger (id integer primary key, user_id text,
            delta_micros integer, balance_after_micros integer);
        insert into wallets values ('u1', 100);
        -- opening grant (+100, after=100), then a -30 debit that B1 never applied
        -- to wallets.balance_micros and whose after-image is the pre-charge 100.
        insert into wallet_ledger values (1, 'u1', 100, 100);
        insert into wallet_ledger values (2, 'u1', -30, 100);
        """
    )
    # TRUSTWORTHY: wallet.balance vs SUM(delta) -> 100 vs 70 -> drift 30 -> flagged.
    ledger_sum = [
        r[0]
        for r in conn.execute(
            """
            select w.user_id from wallets w
            left join (select user_id, sum(delta_micros) expected
                       from wallet_ledger group by user_id) s on s.user_id = w.user_id
            where coalesce(w.balance_micros,0) <> coalesce(s.expected,0)
            """
        )
    ]
    # LEGACY: wallet.balance vs latest after-image -> 100 vs 100 -> NOT flagged (miss).
    balance_after = [
        r[0]
        for r in conn.execute(
            """
            select w.user_id from wallets w
            left join (select user_id, balance_after_micros from wallet_ledger
                       where id in (select max(id) from wallet_ledger group by user_id)
                      ) l on l.user_id = w.user_id
            where coalesce(w.balance_micros,0) <> coalesce(l.balance_after_micros,0)
            """
        )
    ]
    conn.close()
    return ledger_sum, balance_after


def test_ledger_sum_catches_b1_pollution_that_balance_after_misses() -> None:
    """H4 semantics: on a B1-polluted wallet, the SUM(delta) cross-check flags the
    inconsistency while the balance_after-image check reports a false 'consistent'."""
    ledger_sum_flagged, balance_after_flagged = _consistency_checks_on_fixture()

    assert ledger_sum_flagged == ["u1"]  # trustworthy check CATCHES the corruption
    assert balance_after_flagged == []  # legacy check MISSES it (false-consistent)
