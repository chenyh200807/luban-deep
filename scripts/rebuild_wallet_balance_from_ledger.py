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


def build_rebuild_wallet_projection_sql(*, user_id: str = "") -> str:
    predicate = ""
    if str(user_id or "").strip():
        predicate = f"where user_id = '{str(user_id).strip()}'::uuid"
    # Reconstruct balance_micros from SUM(delta_micros) — the trustworthy basis.
    # The opening balance is itself a 'grant' ledger entry (migration 20260419000600),
    # so SUM(delta_micros) == the true balance. The previous basis (latest
    # balance_after_micros) is the SAME application-written column that B1 polluted,
    # so rebuilding from it would FIX-IN the wrong balance — never use it.
    # frozen_micros is a reservation column (not part of delta accounting) and is
    # rebuilt from the latest after-image, which B1 does not touch.
    return f"""
with ledger_sum as (
  select user_id, sum(delta_micros) as expected_balance_micros
  from public.wallet_ledger
  {predicate}
  group by user_id
),
latest_ledger as (
  select distinct on (user_id)
    user_id,
    frozen_after_micros
  from public.wallet_ledger
  {predicate}
  order by user_id, created_at desc, id desc
)
update public.wallets w
   set balance_micros = s.expected_balance_micros,
       frozen_micros = coalesce(l.frozen_after_micros, w.frozen_micros),
       version = greatest(coalesce(w.version, 0), 0) + 1,
       updated_at = now()
  from ledger_sum s
  left join latest_ledger l on l.user_id = s.user_id
 where w.user_id = s.user_id
returning w.user_id::text, w.balance_micros::text, w.frozen_micros::text, w.version::text;
""".strip()


def rebuild_wallet_balance_from_ledger(
    *,
    output_dir: Path,
    env: WalletAuthorityEnv,
    user_id: str = "",
    execute: bool = False,
) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    sql = build_rebuild_wallet_projection_sql(user_id=user_id)
    summary_path = output_dir / "wallet_projection_rebuild.json"
    summary: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "user_id": str(user_id or "").strip(),
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

    completed = run_command(["psql", env.db_url, "-Atq", "-c", sql], check=True)
    rows = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    summary = {
        "generated_at": utc_now_iso(),
        "user_id": str(user_id or "").strip(),
        "status": "ok",
        "updated_rows": rows,
    }
    write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild wallets projection from wallet_ledger latest post-image.")
    parser.add_argument("--output-dir", default="", help="Directory for JSON artifact.")
    parser.add_argument("--user-id", default="", help="Optional single wallet user UUID.")
    parser.add_argument("--execute", action="store_true", help="Run the rebuild query against the configured database.")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "projection_rebuild"
    summary = rebuild_wallet_balance_from_ledger(
        output_dir=output_dir,
        env=resolve_wallet_env(repo_root=repo_root),
        user_id=args.user_id,
        execute=args.execute,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
