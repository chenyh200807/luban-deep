from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

try:
    from scripts.wallet_authority_common import (
        WalletAuthorityEnv,
        command_available,
        discover_repo_root,
        ensure_output_dir,
        resolve_wallet_env,
        run_command,
        utc_now_iso,
        write_json,
    )
except ModuleNotFoundError:
    from wallet_authority_common import (
        WalletAuthorityEnv,
        command_available,
        discover_repo_root,
        ensure_output_dir,
        resolve_wallet_env,
        run_command,
        utc_now_iso,
        write_json,
    )


def build_success_probe_sql(*, user_id: str, entry_id: str, idempotency_key: str, delta_micros: int) -> str:
    reference_id = f"wallet_probe_success:{entry_id}"
    return f"""
begin;
with locked as (
  select user_id, balance_micros, frozen_micros, version
  from public.wallets
  where user_id = '{user_id}'::uuid
  for update
),
inserted as (
  insert into public.wallet_ledger (
    id,
    user_id,
    event_type,
    delta_micros,
    balance_after_micros,
    frozen_after_micros,
    reference_type,
    reference_id,
    reason,
    idempotency_key,
    operator_type,
    operator_id,
    metadata,
    created_at
  )
  select
    '{entry_id}'::uuid,
    locked.user_id,
    'admin_adjust',
    {int(delta_micros)},
    locked.balance_micros + {int(delta_micros)},
    locked.frozen_micros,
    'wallet_probe',
    '{reference_id}',
    'wallet_authority_probe_success',
    '{idempotency_key}',
    'system',
    'wallet_probe',
    jsonb_build_object('probe', 'success', 'entry_id', '{entry_id}'),
    now()
  from locked
  returning user_id, balance_after_micros, frozen_after_micros
),
updated as (
  update public.wallets w
     set balance_micros = inserted.balance_after_micros,
         frozen_micros = inserted.frozen_after_micros,
         version = coalesce(w.version, 0) + 1,
         updated_at = now()
    from inserted
   where w.user_id = inserted.user_id
  returning w.user_id, w.balance_micros, w.frozen_micros, w.version
)
select json_build_object(
  'mode', 'success_probe',
  'entry_id', '{entry_id}',
  'idempotency_key', '{idempotency_key}',
  'updated_rows', (select count(*) from updated),
  'after_balance_micros', (select balance_micros from updated limit 1),
  'after_frozen_micros', (select frozen_micros from updated limit 1),
  'after_version', (select version from updated limit 1)
)::text;
rollback;
""".strip()


def build_failure_probe_sql(*, user_id: str, entry_id: str, idempotency_key: str, delta_micros: int) -> str:
    reference_id = f"wallet_probe_failure:{entry_id}"
    return f"""
begin;
with locked as (
  select user_id, balance_micros, frozen_micros
  from public.wallets
  where user_id = '{user_id}'::uuid
  for update
),
inserted as (
  insert into public.wallet_ledger (
    id,
    user_id,
    event_type,
    delta_micros,
    balance_after_micros,
    frozen_after_micros,
    reference_type,
    reference_id,
    reason,
    idempotency_key,
    operator_type,
    operator_id,
    metadata,
    created_at
  )
  select
    '{entry_id}'::uuid,
    locked.user_id,
    'admin_adjust',
    {int(delta_micros)},
    locked.balance_micros + {int(delta_micros)},
    locked.frozen_micros,
    'wallet_probe',
    '{reference_id}',
    'wallet_authority_probe_failure',
    '{idempotency_key}',
    'system',
    'wallet_probe',
    jsonb_build_object('probe', 'failure', 'entry_id', '{entry_id}'),
    now()
  from locked
  returning user_id, balance_after_micros, frozen_after_micros
),
updated as (
  update public.wallets w
     set balance_micros = inserted.balance_after_micros,
         frozen_micros = inserted.frozen_after_micros,
         version = coalesce(w.version, 0) + 1,
         updated_at = now()
    from inserted
   where w.user_id = inserted.user_id
  returning w.user_id
)
select count(*) from updated;
select 1 / 0;
rollback;
""".strip()


def _psql_json(db_url: str, sql: str) -> dict[str, Any]:
    completed = run_command(["psql", db_url, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "psql failed")
    text = completed.stdout.strip()
    if not text:
        return {}
    return json.loads(text)


def _wallet_snapshot(db_url: str, user_id: str) -> dict[str, Any]:
    sql = f"""
select coalesce((
  select json_build_object(
    'exists', true,
    'balance_micros', balance_micros,
    'frozen_micros', frozen_micros,
    'version', version
  )
  from public.wallets
  where user_id = '{user_id}'::uuid
), json_build_object('exists', false))::text;
""".strip()
    return _psql_json(db_url, sql)


def _ledger_count(db_url: str, idempotency_key: str) -> int:
    sql = f"select count(*)::text from public.wallet_ledger where idempotency_key = '{idempotency_key}';"
    completed = run_command(["psql", db_url, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "failed to query wallet_ledger")
    return int((completed.stdout or "0").strip() or 0)


def execute_wallet_transaction_probe(
    *,
    output_dir: Path,
    env: WalletAuthorityEnv,
    user_id: str,
    delta_micros: int,
    execute: bool,
) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    artifact_path = output_dir / "wallet_transaction_probe.json"
    summary: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "status": "blocked",
        "env": env.to_summary(),
        "execute": execute,
        "user_id": user_id,
        "delta_micros": int(delta_micros),
    }
    if not env.postgres_enabled:
        summary["reason"] = "missing SUPABASE_DB_URL or DATABASE_URL"
        write_json(artifact_path, summary)
        return summary
    if not command_available("psql"):
        summary["reason"] = "psql not found"
        write_json(artifact_path, summary)
        return summary
    success_entry_id = str(uuid.uuid4())
    failure_entry_id = str(uuid.uuid4())
    success_idempotency_key = f"wallet_probe_success:{success_entry_id}"
    failure_idempotency_key = f"wallet_probe_failure:{failure_entry_id}"
    summary["probe_sql_preview"] = {
        "success": build_success_probe_sql(
            user_id=user_id,
            entry_id=success_entry_id,
            idempotency_key=success_idempotency_key,
            delta_micros=delta_micros,
        ),
        "failure": build_failure_probe_sql(
            user_id=user_id,
            entry_id=failure_entry_id,
            idempotency_key=failure_idempotency_key,
            delta_micros=delta_micros,
        ),
    }
    if not execute:
        summary["status"] = "dry_run"
        write_json(artifact_path, summary)
        return summary
    before_snapshot = _wallet_snapshot(env.db_url, user_id)
    success_result = _psql_json(
        env.db_url,
        build_success_probe_sql(
            user_id=user_id,
            entry_id=success_entry_id,
            idempotency_key=success_idempotency_key,
            delta_micros=delta_micros,
        ),
    )
    after_success_snapshot = _wallet_snapshot(env.db_url, user_id)
    failure_error = ""
    failure_script = build_failure_probe_sql(
        user_id=user_id,
        entry_id=failure_entry_id,
        idempotency_key=failure_idempotency_key,
        delta_micros=delta_micros,
    )
    failed = run_command(["psql", env.db_url, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", failure_script], check=False)
    if failed.returncode != 0:
        failure_error = failed.stderr.strip() or failed.stdout.strip()
    after_failure_snapshot = _wallet_snapshot(env.db_url, user_id)
    summary["before_snapshot"] = before_snapshot
    summary["success_probe"] = {
        "result": success_result,
        "post_probe_snapshot": after_success_snapshot,
        "post_probe_matches_before": before_snapshot == after_success_snapshot,
        "ledger_rows_after": _ledger_count(env.db_url, success_idempotency_key),
    }
    summary["rollback_probe"] = {
        "error_triggered": bool(failure_error),
        "error": failure_error[:240],
        "post_failure_snapshot": after_failure_snapshot,
        "post_failure_matches_before": before_snapshot == after_failure_snapshot,
        "ledger_rows_after": _ledger_count(env.db_url, failure_idempotency_key),
    }
    summary["status"] = (
        "ok"
        if summary["success_probe"]["result"].get("updated_rows") == 1
        and summary["success_probe"]["post_probe_matches_before"]
        and summary["success_probe"]["ledger_rows_after"] == 0
        and summary["rollback_probe"]["error_triggered"]
        and summary["rollback_probe"]["post_failure_matches_before"]
        and summary["rollback_probe"]["ledger_rows_after"] == 0
        else "failed"
    )
    write_json(artifact_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe wallet transaction atomicity.")
    parser.add_argument("--output-dir", default="", help="Directory for generated artifacts.")
    parser.add_argument("--user-id", default="", help="UUID user id used for the transaction probe.")
    parser.add_argument("--delta-micros", type=int, default=1000000, help="Delta applied during probe.")
    parser.add_argument("--execute", action="store_true", help="Actually execute the transaction probes.")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "probe"
    env = resolve_wallet_env(repo_root=repo_root)
    if args.execute and not args.user_id:
        raise SystemExit("--user-id is required when --execute is set")
    summary = execute_wallet_transaction_probe(
        output_dir=output_dir,
        env=env,
        user_id=args.user_id or "00000000-0000-4000-8000-000000000000",
        delta_micros=args.delta_micros,
        execute=bool(args.execute),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"ok", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
