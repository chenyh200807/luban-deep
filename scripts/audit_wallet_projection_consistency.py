from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.wallet_authority_common import (
        WalletAuthorityEnv,
        discover_repo_root,
        ensure_output_dir,
        run_command,
        utc_now_iso,
        write_json,
        resolve_wallet_env,
    )
except ModuleNotFoundError:
    from wallet_authority_common import (
        WalletAuthorityEnv,
        discover_repo_root,
        ensure_output_dir,
        run_command,
        utc_now_iso,
        write_json,
        resolve_wallet_env,
    )


def build_wallet_projection_audit_sql(*, limit: int = 100) -> str:
    normalized_limit = max(1, int(limit))
    return f"""
with latest_ledger as (
  select distinct on (user_id)
    user_id,
    balance_after_micros,
    frozen_after_micros,
    created_at
  from public.wallet_ledger
  order by user_id, created_at desc, id desc
),
diff_rows as (
  select
    w.user_id,
    w.balance_micros as wallet_balance_micros,
    l.balance_after_micros as ledger_balance_micros,
    w.frozen_micros as wallet_frozen_micros,
    l.frozen_after_micros as ledger_frozen_micros,
    l.created_at as ledger_created_at
  from public.wallets w
  left join latest_ledger l on l.user_id = w.user_id
  where coalesce(w.balance_micros, 0) <> coalesce(l.balance_after_micros, 0)
     or coalesce(w.frozen_micros, 0) <> coalesce(l.frozen_after_micros, 0)
),
sample_diff as (
  select *
  from diff_rows
  order by user_id
  limit {normalized_limit}
)
select json_build_object(
  'generated_at', now(),
  'limit', {normalized_limit},
  'diff_count', (select count(*) from diff_rows),
  'sample', coalesce(
    json_agg(
      json_build_object(
        'user_id', s.user_id,
        'wallet_balance_micros', s.wallet_balance_micros,
        'ledger_balance_micros', s.ledger_balance_micros,
        'wallet_frozen_micros', s.wallet_frozen_micros,
        'ledger_frozen_micros', s.ledger_frozen_micros,
        'ledger_created_at', s.ledger_created_at
      )
      order by s.user_id
    ),
    '[]'::json
  )
)::text
from sample_diff s;
""".strip()


def audit_wallet_projection_consistency(
    *,
    output_dir: Path,
    env: WalletAuthorityEnv,
    limit: int = 100,
    execute: bool = False,
) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    sql = build_wallet_projection_audit_sql(limit=limit)
    summary_path = output_dir / "wallet_projection_consistency.json"
    summary: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "limit": limit,
        "status": "blocked",
        "sql_preview": sql,
    }
    if not env.postgres_enabled:
        summary["reason"] = "DATABASE_URL or SUPABASE_DB_URL is required"
        write_json(summary_path, summary)
        return summary
    if not execute:
        summary["status"] = "dry_run"
        write_json(summary_path, summary)
        return summary

    completed = run_command(["psql", env.db_url, "-Atqc", sql], check=True)
    payload = json.loads((completed.stdout or "{}").strip() or "{}")
    summary = {
        "generated_at": utc_now_iso(),
        "limit": limit,
        "status": "ok",
        "result": payload,
    }
    write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit wallets projection consistency against wallet_ledger latest entries.")
    parser.add_argument("--output-dir", default="", help="Directory for JSON artifact.")
    parser.add_argument("--limit", type=int, default=100, help="Max diff rows to sample.")
    parser.add_argument("--execute", action="store_true", help="Run the query against the configured database.")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "projection_audit"
    summary = audit_wallet_projection_consistency(
        output_dir=output_dir,
        env=resolve_wallet_env(repo_root=repo_root),
        limit=args.limit,
        execute=args.execute,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
