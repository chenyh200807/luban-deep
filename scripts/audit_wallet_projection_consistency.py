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
        resolve_wallet_env,
        run_command,
        utc_now_iso,
        write_json,
    )
except ModuleNotFoundError:
    from wallet_authority_common import (
        WalletAuthorityEnv,
        discover_repo_root,
        ensure_output_dir,
        resolve_wallet_env,
        run_command,
        utc_now_iso,
        write_json,
    )


def build_wallet_projection_audit_sql(*, limit: int = 100) -> str:
    normalized_limit = max(1, int(limit))
    # Two independent consistency checks, both reported:
    #  - ledger_sum_diff (TRUSTWORTHY): wallet.balance_micros vs SUM(delta_micros).
    #    The opening balance is itself a 'grant' ledger entry (migration
    #    20260419000600), so SUM(delta_micros) == the true expected balance. This
    #    check never reads balance_after_micros, so B1-style pollution (ledger
    #    written, projection never decremented, after-image snapshotted as the
    #    pre-charge balance) CANNOT hide from it.
    #  - balance_after_diff (LEGACY, may be misled): wallet vs latest ledger
    #    after-image. Kept for continuity, but a 'consistent' result here does NOT
    #    prove correctness — balance_after_micros is the same polluted column.
    return f"""
with ledger_sum as (
  select user_id, sum(delta_micros) as expected_balance_micros
  from public.wallet_ledger wl
  group by user_id
),
latest_ledger as (
  select distinct on (user_id)
    user_id,
    balance_after_micros,
    frozen_after_micros,
    created_at
  from public.wallet_ledger
  order by user_id, created_at desc, id desc
),
ledger_sum_diff as (
  select
    w.user_id,
    w.balance_micros as wallet_balance_micros,
    coalesce(s.expected_balance_micros, 0) as expected_balance_micros,
    w.balance_micros - coalesce(s.expected_balance_micros, 0) as drift_micros
  from public.wallets w
  left join ledger_sum s on s.user_id = w.user_id
  where coalesce(w.balance_micros, 0) <> coalesce(s.expected_balance_micros, 0)
),
balance_after_diff as (
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
duplicate_idempotency as (
  select idempotency_key, count(*) as event_count
  from public.wallet_ledger
  where nullif(trim(coalesce(idempotency_key, '')), '') is not null
  group by idempotency_key
  having count(*) > 1
),
identity_merge_wallet_mutation as (
  select id, user_id, event_type, delta_micros, reference_type, reference_id, reason, created_at
  from public.wallet_ledger
  where created_at >= now() - interval '25 hours'
    and (
      lower(coalesce(reason, '')) like '%member_merge%'
      or lower(coalesce(reason, '')) like '%identity_merge%'
      or lower(coalesce(reference_type, '')) in ('member_merge', 'identity_merge')
      or lower(coalesce(metadata::text, '')) like '%member_merge%'
      or lower(coalesce(metadata::text, '')) like '%identity_merge%'
    )
),
positive_delta_classified as (
  select
    wl.*,
    case
      when lower(coalesce(event_type, '')) = 'grant'
       and lower(coalesce(reference_type, '')) = 'purchase'
       and lower(coalesce(reason, '')) = 'manual_membership_purchase'
       and lower(coalesce(operator_type, '')) = 'admin'
       and nullif(trim(coalesce(operator_id, '')), '') is not null
       and nullif(trim(coalesce(reference_id, '')), '') is not null
       and nullif(trim(coalesce(idempotency_key, '')), '') is not null
       and lower(coalesce(metadata->>'source', '')) = 'bi_manual_membership'
       and lower(coalesce(metadata->>'channel', '')) = 'manual_membership'
       and nullif(trim(coalesce(metadata->>'operator_id', '')), '') =
           nullif(trim(coalesce(operator_id, '')), '')
        then 'verified_manual_purchase'
      when lower(coalesce(event_type, '')) = 'grant'
       and lower(coalesce(reference_type, '')) in ('order', 'payment', 'wechat_pay')
       and lower(coalesce(reason, '')) in ('purchase_grant', 'payment_purchase')
       and lower(coalesce(operator_type, '')) = 'system'
       and nullif(trim(coalesce(reference_id, '')), '') is not null
       and nullif(trim(coalesce(idempotency_key, '')), '') is not null
       and lower(coalesce(metadata->>'source', '')) = 'payment_webhook'
       and lower(coalesce(metadata->>'channel', '')) in ('payment', 'wechat_pay')
       and lower(coalesce(metadata->>'payment_status', '')) in ('paid', 'succeeded', 'verified')
       and nullif(trim(coalesce(metadata->>'provider_transaction_id', '')), '') is not null
        then 'verified_payment_purchase'
      when lower(coalesce(event_type, '')) = 'refund'
       and lower(coalesce(reference_type, '')) = 'refund'
       and lower(coalesce(reason, '')) = 'manual_membership_reversal'
       and lower(coalesce(operator_type, '')) = 'admin'
       and nullif(trim(coalesce(operator_id, '')), '') is not null
       and nullif(trim(coalesce(reference_id, '')), '') is not null
       and nullif(trim(coalesce(idempotency_key, '')), '') is not null
       and lower(coalesce(metadata->>'source', '')) = 'bi_manual_membership_reversal'
       and lower(coalesce(metadata->>'channel', '')) = 'manual_membership_reversal'
       and nullif(trim(coalesce(metadata->>'operator_id', '')), '') =
           nullif(trim(coalesce(operator_id, '')), '')
       and nullif(trim(coalesce(metadata->>'reversal_of_purchase_id', '')), '') =
           nullif(trim(coalesce(reference_id, '')), '')
        then 'verified_manual_reversal'
      when lower(coalesce(event_type, '')) = 'refund'
       and lower(coalesce(reference_type, '')) in ('refund', 'payment', 'wechat_pay')
       and lower(coalesce(reason, '')) in ('payment_refund', 'payment_reversal')
       and lower(coalesce(operator_type, '')) = 'system'
       and nullif(trim(coalesce(reference_id, '')), '') is not null
       and nullif(trim(coalesce(idempotency_key, '')), '') is not null
       and lower(coalesce(metadata->>'source', '')) = 'payment_webhook'
       and lower(coalesce(metadata->>'channel', '')) in ('payment', 'wechat_pay')
       and lower(coalesce(metadata->>'refund_status', '')) in ('succeeded', 'verified')
       and nullif(trim(coalesce(metadata->>'original_payment_id', '')), '') is not null
        then 'verified_payment_refund'
      when lower(coalesce(event_type, '')) = 'admin_adjust'
       and lower(coalesce(reference_type, '')) = 'ticket'
       and lower(coalesce(operator_type, '')) = 'admin'
       and nullif(trim(coalesce(operator_id, '')), '') is not null
       and nullif(trim(coalesce(reference_id, '')), '') is not null
       and nullif(trim(coalesce(idempotency_key, '')), '') is not null
       and nullif(trim(coalesce(reason, '')), '') is not null
       and lower(coalesce(reason, '')) <> 'admin_adjust'
       and lower(coalesce(metadata->>'source', '')) in (
         'member_console_wallet_adjustment',
         'support_wallet_adjustment',
         'finance_wallet_adjustment'
       )
       and nullif(trim(coalesce(metadata->>'operator_id', '')), '') =
           nullif(trim(coalesce(operator_id, '')), '')
       and nullif(trim(coalesce(metadata->>'ticket_id', '')), '') =
           nullif(trim(coalesce(reference_id, '')), '')
        then 'verified_admin_adjustment'
      else 'unallowlisted_positive_delta'
    end as allowlist_class
  from public.wallet_ledger wl
  where delta_micros > 0
    and created_at >= now() - interval '25 hours'
),
suspicious_positive_delta as (
  select *
  from positive_delta_classified
  where allowlist_class = 'unallowlisted_positive_delta'
)
select json_build_object(
  'generated_at', now(),
  'limit', {normalized_limit},
  'audit_window_hours', 25,
  'ledger_sum_diff_count', (select count(*) from ledger_sum_diff),
  'balance_after_diff_count', (select count(*) from balance_after_diff),
  'duplicate_idempotency_count', (select count(*) from duplicate_idempotency),
  'identity_merge_wallet_mutation_count', (select count(*) from identity_merge_wallet_mutation),
  'suspicious_positive_delta_count', (select count(*) from suspicious_positive_delta),
  'ledger_sum_sample', (
    select coalesce(json_agg(json_build_object(
      'user_hash', md5(coalesce(d.user_id::text, '')),
      'wallet_balance_micros', d.wallet_balance_micros,
      'expected_balance_micros', d.expected_balance_micros,
      'drift_micros', d.drift_micros
    )), '[]'::json)
    from (select * from ledger_sum_diff order by abs(drift_micros) desc limit {normalized_limit}) d
  ),
  'balance_after_sample', (
    select coalesce(json_agg(json_build_object(
      'user_hash', md5(coalesce(d.user_id::text, '')),
      'wallet_balance_micros', d.wallet_balance_micros,
      'ledger_balance_micros', d.ledger_balance_micros,
      'wallet_frozen_micros', d.wallet_frozen_micros,
      'ledger_frozen_micros', d.ledger_frozen_micros,
      'ledger_created_at', d.ledger_created_at
    )), '[]'::json)
    from (select * from balance_after_diff order by user_id limit {normalized_limit}) d
  ),
  'duplicate_idempotency_sample', (
    select coalesce(json_agg(json_build_object(
      'idempotency_hash', md5(coalesce(d.idempotency_key, '')),
      'event_count', d.event_count
    )), '[]'::json)
    from (select * from duplicate_idempotency order by event_count desc limit {normalized_limit}) d
  ),
  'identity_merge_wallet_mutation_sample', (
    select coalesce(json_agg(json_build_object(
      'ledger_hash', md5(coalesce(d.id::text, '')),
      'user_hash', md5(coalesce(d.user_id::text, '')),
      'event_type', case
        when lower(coalesce(d.event_type, '')) in ('grant', 'refund', 'admin_adjust', 'debit')
          then lower(d.event_type)
        else 'other'
      end,
      'delta_micros', d.delta_micros,
      'reference_type', case
        when lower(coalesce(d.reference_type, '')) in (
          'member_merge', 'identity_merge', 'purchase', 'order', 'payment',
          'wechat_pay', 'refund', 'ticket', 'ai_usage'
        ) then lower(d.reference_type)
        else 'other'
      end,
      'reference_hash', md5(coalesce(d.reference_id, '')),
      'reason_class', 'identity_merge',
      'created_at', d.created_at
    )), '[]'::json)
    from (select * from identity_merge_wallet_mutation order by created_at desc limit {normalized_limit}) d
  ),
  'suspicious_positive_delta_sample', (
    select coalesce(json_agg(json_build_object(
      'ledger_hash', md5(coalesce(d.id::text, '')),
      'user_hash', md5(coalesce(d.user_id::text, '')),
      'event_type', case
        when lower(coalesce(d.event_type, '')) in ('grant', 'refund', 'admin_adjust', 'debit')
          then lower(d.event_type)
        else 'other'
      end,
      'delta_micros', d.delta_micros,
      'reference_type', case
        when lower(coalesce(d.reference_type, '')) in (
          'member_merge', 'identity_merge', 'purchase', 'order', 'payment',
          'wechat_pay', 'refund', 'ticket', 'ai_usage'
        ) then lower(d.reference_type)
        else 'other'
      end,
      'reference_hash', md5(coalesce(d.reference_id, '')),
      'operator_type', case
        when lower(coalesce(d.operator_type, '')) in ('admin', 'system', 'service')
          then lower(d.operator_type)
        else 'other'
      end,
      'allowlist_class', d.allowlist_class,
      'created_at', d.created_at
    )), '[]'::json)
    from (select * from suspicious_positive_delta order by created_at desc limit {normalized_limit}) d
  )
)::text;
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
