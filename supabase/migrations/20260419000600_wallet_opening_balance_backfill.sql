begin;

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
  gen_random_uuid(),
  w.user_id,
  'grant',
  w.balance_micros,
  w.balance_micros,
  w.frozen_micros,
  'migration',
  'opening_balance',
  'migration_opening_balance',
  'migration_opening_balance:' || w.user_id::text,
  'system',
  'wallet_migration',
  jsonb_build_object(
    'migration_batch', '20260419_wallet_opening_balance_v1',
    'source', 'public.wallets',
    'wallet_version_before', w.version
  ),
  coalesce(w.created_at, now())
from public.wallets w
where not exists (
  select 1
  from public.wallet_ledger wl
  where wl.user_id = w.user_id
)
and (coalesce(w.balance_micros, 0) <> 0 or coalesce(w.frozen_micros, 0) <> 0)
on conflict (idempotency_key) do nothing;

commit;
