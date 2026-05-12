begin;

create table if not exists public.wallet_ledger (
  id uuid primary key,
  user_id uuid not null references public.wallets(user_id) on delete cascade,
  event_type text not null,
  delta_micros bigint not null,
  balance_after_micros bigint not null,
  frozen_after_micros bigint not null,
  reference_type text,
  reference_id text,
  reason text not null,
  idempotency_key text not null,
  operator_type text not null,
  operator_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on table public.wallet_ledger is
  'Single source of truth for all wallet balance mutations. Append-only ledger keyed by the canonical wallet user UUID.';

comment on column public.wallet_ledger.delta_micros is
  'Signed delta in micros. Positive for grants/refunds, negative for debits/expirations.';

comment on column public.wallet_ledger.balance_after_micros is
  'Wallet balance projection immediately after this ledger entry is applied.';

comment on column public.wallet_ledger.frozen_after_micros is
  'Frozen micros projection immediately after this ledger entry is applied.';

comment on column public.wallet_ledger.idempotency_key is
  'Global dedupe key for retries. Same business event must never write multiple ledger rows.';

create unique index if not exists idx_wallet_ledger_idempotency_key
  on public.wallet_ledger(idempotency_key);

create index if not exists idx_wallet_ledger_user_created
  on public.wallet_ledger(user_id, created_at desc);

create index if not exists idx_wallet_ledger_reference
  on public.wallet_ledger(reference_type, reference_id, created_at desc)
  where reference_type is not null and reference_id is not null;

create index if not exists idx_wallet_ledger_event_type_created
  on public.wallet_ledger(event_type, created_at desc);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallet_ledger_delta_non_zero'
      and conrelid = 'public.wallet_ledger'::regclass
  ) then
    alter table public.wallet_ledger
      add constraint wallet_ledger_delta_non_zero
      check (delta_micros <> 0);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallet_ledger_balance_after_non_negative'
      and conrelid = 'public.wallet_ledger'::regclass
  ) then
    alter table public.wallet_ledger
      add constraint wallet_ledger_balance_after_non_negative
      check (balance_after_micros >= 0);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallet_ledger_frozen_after_non_negative'
      and conrelid = 'public.wallet_ledger'::regclass
  ) then
    alter table public.wallet_ledger
      add constraint wallet_ledger_frozen_after_non_negative
      check (frozen_after_micros >= 0);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallet_ledger_frozen_le_balance'
      and conrelid = 'public.wallet_ledger'::regclass
  ) then
    alter table public.wallet_ledger
      add constraint wallet_ledger_frozen_le_balance
      check (frozen_after_micros <= balance_after_micros);
  end if;
end $$;

alter table public.wallets
  add column if not exists updated_at timestamptz not null default now();

alter table public.wallets
  alter column balance_micros set default 0;

alter table public.wallets
  alter column frozen_micros set default 0;

alter table public.wallets
  alter column version set default 1;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallets_balance_micros_non_negative'
      and conrelid = 'public.wallets'::regclass
  ) then
    alter table public.wallets
      add constraint wallets_balance_micros_non_negative
      check (balance_micros >= 0) not valid;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallets_frozen_micros_non_negative'
      and conrelid = 'public.wallets'::regclass
  ) then
    alter table public.wallets
      add constraint wallets_frozen_micros_non_negative
      check (frozen_micros >= 0) not valid;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'wallets_frozen_le_balance'
      and conrelid = 'public.wallets'::regclass
  ) then
    alter table public.wallets
      add constraint wallets_frozen_le_balance
      check (frozen_micros <= balance_micros) not valid;
  end if;
end $$;

create or replace function public.touch_wallet_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
begin
  if not exists (
    select 1
    from pg_trigger
    where tgname = 'trg_wallets_touch_updated_at'
      and tgrelid = 'public.wallets'::regclass
  ) then
    create trigger trg_wallets_touch_updated_at
      before update on public.wallets
      for each row
      execute function public.touch_wallet_updated_at();
  end if;
end $$;

alter table public.wallet_ledger enable row level security;

commit;
