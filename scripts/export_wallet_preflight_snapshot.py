from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

try:
    from scripts.wallet_authority_common import (
        WalletAuthorityEnv,
        command_available,
        discover_repo_root,
        ensure_output_dir,
        resolve_wallet_env,
        rest_headers,
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
        rest_headers,
        run_command,
        utc_now_iso,
        write_json,
        write_sql_comment_file,
    )

TARGET_RELATIONS = ("users", "wallets", "v_members")


def _read_rest_sample(client: httpx.Client, env: WalletAuthorityEnv, relation: str, sample_limit: int) -> dict[str, Any]:
    response = client.get(
        f"{env.supabase_url.rstrip('/')}/rest/v1/{relation}",
        headers=rest_headers(env.api_key, prefer_count=True),
        params={"select": "*", "limit": max(int(sample_limit), 1)},
    )
    payload: Any
    error: str | None = None
    count: int | None = None
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = []
    if response.headers.get("content-range"):
        try:
            count = int(str(response.headers["content-range"]).split("/")[-1])
        except ValueError:
            count = None
    if response.is_error:
        error = f"{response.status_code}: {response.text.strip()[:240]}"
    if not isinstance(payload, list):
        payload = []
    return {
        "relation": relation,
        "status_code": response.status_code,
        "count": count,
        "sample": payload,
        "error": error,
    }


def _fetch_rest_samples(env: WalletAuthorityEnv, sample_limit: int) -> list[dict[str, Any]]:
    if not env.rest_enabled:
        return []
    with httpx.Client(timeout=10.0) as client:
        return [_read_rest_sample(client, env, relation, sample_limit) for relation in TARGET_RELATIONS]


def _schema_snapshot_lines(env: WalletAuthorityEnv) -> list[str]:
    if not env.postgres_enabled:
        return [
            "status=blocked",
            "reason=missing SUPABASE_DB_URL or DATABASE_URL",
            "next_action=provide direct postgres url, then rerun this script to export columns and relation metadata",
        ]
    if not command_available("psql"):
        return [
            "status=blocked",
            "reason=psql not found",
            "next_action=install postgres client tools before rerunning",
        ]
    sql = """
select json_agg(row_to_json(t) order by relation_name, ordinal_position)
from (
  select
    table_name as relation_name,
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    coalesce(column_default, '') as column_default
  from information_schema.columns
  where table_schema = 'public'
    and table_name in ('users', 'wallets', 'wallet_ledger', 'v_members')
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
            f"reason=unexpected schema payload: {text[:240]}",
        ]
    lines = ["status=ok", f"relation_column_count={len(rows or [])}"]
    for row in rows or []:
        lines.append(
            "relation={relation_name} column={column_name} type={data_type} nullable={is_nullable} default={column_default}".format(
                **row
            )
        )
    return lines


def generate_preflight_snapshot(
    *,
    output_dir: Path,
    env: WalletAuthorityEnv,
    sample_limit: int = 20,
) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    rest_samples = _fetch_rest_samples(env, sample_limit)
    wallets_sample_path = output_dir / "wallets_sample.json"
    preflight_sql_path = output_dir / "preflight_snapshot.sql"
    schema_sql_path = output_dir / "schema_snapshot.sql"
    status = "ok" if rest_samples else "blocked"
    missing: list[str] = []
    if not env.supabase_url:
        missing.append("SUPABASE_URL")
    if not env.api_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY")
    wallets_payload = {
        "generated_at": utc_now_iso(),
        "status": status,
        "missing": missing,
        "env": env.to_summary(),
        "relations": rest_samples,
    }
    write_json(wallets_sample_path, wallets_payload)
    preflight_lines = [
        f"generated_at={wallets_payload['generated_at']}",
        f"status={status}",
        f"missing={','.join(missing) if missing else '-'}",
    ]
    for relation in rest_samples:
        preflight_lines.append(
            "relation={relation} status_code={status_code} count={count} error={error}".format(
                relation=relation["relation"],
                status_code=relation["status_code"],
                count=relation["count"] if relation["count"] is not None else "unknown",
                error=relation["error"] or "-",
            )
        )
    if not rest_samples:
        preflight_lines.append("next_action=provide SUPABASE_URL plus admin-capable key to export wallets/users/v_members samples")
    write_sql_comment_file(preflight_sql_path, "wallet authority preflight snapshot", preflight_lines)
    write_sql_comment_file(schema_sql_path, "wallet authority schema snapshot", _schema_snapshot_lines(env))
    return {
        "status": status,
        "output_dir": str(output_dir),
        "artifacts": {
            "wallets_sample_json": str(wallets_sample_path),
            "preflight_snapshot_sql": str(preflight_sql_path),
            "schema_snapshot_sql": str(schema_sql_path),
        },
        "relations": [item["relation"] for item in rest_samples],
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export wallet authority preflight artifacts.")
    parser.add_argument("--output-dir", default="", help="Directory for generated artifacts.")
    parser.add_argument("--sample-limit", type=int, default=20, help="Max sample rows per relation.")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "preflight"
    summary = generate_preflight_snapshot(output_dir=output_dir, env=resolve_wallet_env(repo_root=repo_root), sample_limit=args.sample_limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
