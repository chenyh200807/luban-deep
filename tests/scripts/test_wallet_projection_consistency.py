from __future__ import annotations

from pathlib import Path

from scripts.audit_wallet_projection_consistency import (
    audit_wallet_projection_consistency,
    build_wallet_projection_audit_sql,
)
from scripts.rebuild_wallet_balance_from_ledger import build_rebuild_wallet_projection_sql
from scripts.wallet_authority_common import resolve_wallet_env


def test_build_wallet_projection_audit_sql_checks_projection_vs_ledger() -> None:
    sql = build_wallet_projection_audit_sql(limit=25)

    assert "wallet_ledger" in sql
    assert "balance_after_micros" in sql
    assert "public.wallets" in sql
    assert "limit 25" in sql.lower()


def test_audit_wallet_projection_consistency_blocks_without_postgres(tmp_path: Path) -> None:
    summary = audit_wallet_projection_consistency(
        output_dir=tmp_path,
        env=resolve_wallet_env(repo_root=tmp_path, environ={}),
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
