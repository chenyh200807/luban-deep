from __future__ import annotations

import argparse
import json
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
        write_sql_comment_file,
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
        write_sql_comment_file,
    )

RLS_RELATIONS = ("wallets", "wallet_ledger")


def build_wallet_write_probe(env: WalletAuthorityEnv) -> dict[str, Any]:
    notes: list[str] = []
    recommended_write_path = "postgres_transaction" if env.postgres_enabled else "service_role_rest_only"
    if not env.service_role_enabled:
        notes.append("SUPABASE_SERVICE_ROLE_KEY 缺失，无法安全执行服务端 admin 读写探针。")
    if not env.postgres_enabled:
        notes.append("缺少 DATABASE_URL/SUPABASE_DB_URL，无法验证真正的原子事务写链。")
    if env.postgres_enabled:
        notes.append("生产钱包写链建议走服务端 Postgres 事务，避免多次 REST 请求带来的非原子性。")
    if env.service_role_enabled:
        notes.append("服务端 admin 读链或应急核对可使用 service-role key，但不应让客户端持有。")
    status = "ready" if env.service_role_enabled and env.postgres_enabled else "blocked"
    return {
        "generated_at": utc_now_iso(),
        "status": status,
        "recommended_write_path": recommended_write_path,
        "env": env.to_summary(),
        "notes": notes,
    }


def build_rollback_probe(env: WalletAuthorityEnv) -> dict[str, Any]:
    notes = [
        "rollback probe 的目标是证明 ledger insert 与 wallet update 在同一事务内可整体回滚。",
        "如果只有 REST admin key 而没有 Postgres 连接，则只能做权限探针，不能证明事务性。",
    ]
    return {
        "generated_at": utc_now_iso(),
        "status": "ready" if env.postgres_enabled else "blocked",
        "env": env.to_summary(),
        "notes": notes,
    }


def _dump_rls_lines(env: WalletAuthorityEnv) -> list[str]:
    if not env.postgres_enabled:
        return [
            "status=blocked",
            "reason=missing SUPABASE_DB_URL or DATABASE_URL",
            "next_action=provide direct postgres url, then rerun to inspect pg_policies",
        ]
    if not command_available("psql"):
        return [
            "status=blocked",
            "reason=psql not found",
            "next_action=install postgres client tools before rerunning",
        ]
    sql = """
select json_agg(row_to_json(t) order by relation_name, policy_name nulls first)
from (
  select
    c.relname as relation_name,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced,
    p.policyname as policy_name,
    p.permissive,
    p.roles,
    p.cmd as command,
    coalesce(p.qual, '') as using_expression,
    coalesce(p.with_check, '') as with_check_expression
  from pg_class c
  left join pg_policies p
    on p.schemaname = 'public'
   and p.tablename = c.relname
  where c.relnamespace = 'public'::regnamespace
    and c.relname in ('wallets', 'wallet_ledger')
) t;
""".strip()
    completed = run_command(["psql", env.db_url, "-X", "-A", "-t", "-c", sql], check=False)
    if completed.returncode != 0:
        return [
            "status=blocked",
            f"reason=psql query failed: {completed.stderr.strip()[:240]}",
        ]
    text = completed.stdout.strip() or "[]"
    try:
        rows = json.loads(text)
    except json.JSONDecodeError:
        return [
            "status=blocked",
            f"reason=unexpected RLS payload: {text[:240]}",
        ]
    lines = ["status=ok", f"relation_count={len(RLS_RELATIONS)}", f"policy_rows={len(rows or [])}"]
    for row in rows or []:
        lines.append(
            "relation={relation_name} rls_enabled={rls_enabled} rls_forced={rls_forced} policy={policy_name} command={command}".format(
                **row
            )
        )
    return lines


def generate_wallet_rls_artifacts(*, output_dir: Path, env: WalletAuthorityEnv) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    rls_path = output_dir / "rls_policy_dump.sql"
    wallet_write_probe_path = output_dir / "wallet_write_probe.json"
    rollback_probe_path = output_dir / "rollback_probe.json"
    write_sql_comment_file(rls_path, "wallet authority rls dump", _dump_rls_lines(env))
    wallet_probe = build_wallet_write_probe(env)
    rollback_probe = build_rollback_probe(env)
    write_json(wallet_write_probe_path, wallet_probe)
    write_json(rollback_probe_path, rollback_probe)
    status = "ok" if wallet_probe["status"] == "ready" else "blocked"
    return {
        "status": status,
        "output_dir": str(output_dir),
        "artifacts": {
            "rls_policy_dump_sql": str(rls_path),
            "wallet_write_probe_json": str(wallet_write_probe_path),
            "rollback_probe_json": str(rollback_probe_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump wallet RLS policies and write readiness probes.")
    parser.add_argument("--output-dir", default="", help="Directory for generated artifacts.")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "rls"
    summary = generate_wallet_rls_artifacts(output_dir=output_dir, env=resolve_wallet_env(repo_root=repo_root))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
