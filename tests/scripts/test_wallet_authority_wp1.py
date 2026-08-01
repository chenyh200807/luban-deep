from __future__ import annotations

from pathlib import Path

from scripts.dump_wallet_rls import build_rollback_probe, build_wallet_write_probe, generate_wallet_rls_artifacts
from scripts.export_wallet_preflight_snapshot import generate_preflight_snapshot
from scripts.probe_wallet_transaction import build_failure_probe_sql, build_success_probe_sql, execute_wallet_transaction_probe
from scripts.wallet_authority_common import resolve_wallet_env


def test_resolve_wallet_env_prefers_service_role_and_db_url_from_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "SUPABASE_URL=https://example.supabase.co",
                "SUPABASE_KEY=anon-key",
                "SUPABASE_SERVICE_ROLE_KEY=service-key",
                "SUPABASE_DB_URL=postgresql://postgres:postgres@localhost:5432/postgres",
            ]
        ),
        encoding="utf-8",
    )
    env = resolve_wallet_env(repo_root=tmp_path, environ={})
    assert env.supabase_url == "https://example.supabase.co"
    assert env.api_key == "service-key"
    assert env.service_role_key == "service-key"
    assert env.db_url.startswith("postgresql://")
    assert env.rest_enabled is True
    assert env.postgres_enabled is True


def test_generate_preflight_snapshot_writes_blocked_artifacts_without_env(tmp_path: Path) -> None:
    summary = generate_preflight_snapshot(output_dir=tmp_path, env=resolve_wallet_env(repo_root=tmp_path, environ={}))
    assert summary["status"] == "blocked"
    assert (tmp_path / "wallets_sample.json").exists()
    assert (tmp_path / "preflight_snapshot.sql").exists()
    assert (tmp_path / "schema_snapshot.sql").exists()
    assert "SUPABASE_URL" in (tmp_path / "wallets_sample.json").read_text(encoding="utf-8")


def test_wallet_write_probe_requires_postgres_and_service_role() -> None:
    blocked = build_wallet_write_probe(resolve_wallet_env(repo_root=Path("/tmp"), environ={}))
    assert blocked["status"] == "blocked"
    ready = build_wallet_write_probe(
        resolve_wallet_env(
            repo_root=Path("/tmp"),
            environ={
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-key",
                "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/postgres",
            },
        )
    )
    assert ready["status"] == "ready"
    assert ready["recommended_write_path"] == "postgres_transaction"
    rollback = build_rollback_probe(
        resolve_wallet_env(
            repo_root=Path("/tmp"),
            environ={"DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/postgres"},
        )
    )
    assert rollback["status"] == "ready"


def test_generate_wallet_rls_artifacts_writes_probe_files(tmp_path: Path) -> None:
    summary = generate_wallet_rls_artifacts(output_dir=tmp_path, env=resolve_wallet_env(repo_root=tmp_path, environ={}))
    assert summary["status"] == "blocked"
    assert (tmp_path / "rls_policy_dump.sql").exists()
    assert (tmp_path / "wallet_write_probe.json").exists()
    assert (tmp_path / "rollback_probe.json").exists()


def test_wallet_transaction_probe_sql_contains_atomic_steps() -> None:
    success_sql = build_success_probe_sql(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        entry_id="11111111-1111-4111-8111-111111111111",
        idempotency_key="wallet_probe_success:11111111-1111-4111-8111-111111111111",
        delta_micros=1_000_000,
    )
    failure_sql = build_failure_probe_sql(
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        entry_id="22222222-2222-4222-8222-222222222222",
        idempotency_key="wallet_probe_failure:22222222-2222-4222-8222-222222222222",
        delta_micros=1_000_000,
    )
    assert "insert into public.wallet_ledger" in success_sql
    assert "update public.wallets" in success_sql
    assert success_sql.endswith("rollback;")
    assert "select 1 / 0;" in failure_sql


def test_execute_wallet_transaction_probe_dry_run_writes_artifact(tmp_path: Path) -> None:
    env = resolve_wallet_env(
        repo_root=tmp_path,
        environ={"DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/postgres"},
    )
    summary = execute_wallet_transaction_probe(
        output_dir=tmp_path,
        env=env,
        user_id="2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        delta_micros=1_000_000,
        execute=False,
    )
    assert summary["status"] == "dry_run"
    assert "probe_sql_preview" in summary
    assert (tmp_path / "wallet_transaction_probe.json").exists()


def test_resolve_wallet_env_uses_registered_db_url_when_database_url_is_placeholder(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DB_URL=postgresql://localhost:5432/postgres",
                "DATABASE_URL=${DB_URL}",
            ]
        ),
        encoding="utf-8",
    )

    env = resolve_wallet_env(
        repo_root=tmp_path,
        environ={},
        db_url_keys=("SUPABASE_DB_URL", "DATABASE_URL", "DB_URL"),
    )

    assert env.db_url == "postgresql://localhost:5432/postgres"
    assert env.postgres_enabled is True


def test_resolve_wallet_env_rejects_unexpanded_database_url_placeholder(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("DATABASE_URL=${DB_URL}\n", encoding="utf-8")

    env = resolve_wallet_env(repo_root=tmp_path, environ={})

    assert env.db_url == ""
    assert env.postgres_enabled is False


def test_resolve_wallet_env_does_not_expand_default_writer_authority_to_db_url(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(
        "DB_URL=postgresql://localhost:5432/postgres\n",
        encoding="utf-8",
    )

    env = resolve_wallet_env(repo_root=tmp_path, environ={})

    assert env.db_url == ""
    assert env.postgres_enabled is False
