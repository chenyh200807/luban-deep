begin;

create extension if not exists pgcrypto;

create or replace function public.apply_wallet_mutation(
  p_user_id uuid,
  p_event_type text,
  p_delta_micros bigint,
  p_idempotency_key text,
  p_reason text,
  p_reference_type text default null,
  p_reference_id text default null,
  p_operator_type text default 'system',
  p_operator_id text default null,
  p_metadata jsonb default '{}'::jsonb
)
returns table (
  ledger_event_id uuid,
  user_id uuid,
  event_type text,
  delta_micros bigint,
  balance_micros bigint,
  frozen_micros bigint,
  version integer,
  idempotency_key text,
  reference_type text,
  reference_id text,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  wallet_row public.wallets%rowtype;
  ledger_row public.wallet_ledger%rowtype;
  next_balance_micros bigint;
  next_version integer;
begin
  if p_user_id is null then
    raise exception 'user_id is required' using errcode = '22023';
  end if;
  if coalesce(trim(p_event_type), '') = '' then
    raise exception 'event_type is required' using errcode = '22023';
  end if;
  if coalesce(p_delta_micros, 0) = 0 then
    raise exception 'delta_micros must be non-zero' using errcode = '22023';
  end if;
  if coalesce(trim(p_idempotency_key), '') = '' then
    raise exception 'idempotency_key is required' using errcode = '22023';
  end if;

  select *
    into ledger_row
    from public.wallet_ledger wl
   where wl.idempotency_key = p_idempotency_key
   limit 1;

  if found then
    if ledger_row.user_id <> p_user_id then
      raise exception 'Idempotency key already belongs to another user.'
        using errcode = '23505';
    end if;

    select *
      into wallet_row
      from public.wallets w
     where w.user_id = p_user_id
     limit 1;

    return query
    select
      ledger_row.id,
      ledger_row.user_id,
      ledger_row.event_type,
      ledger_row.delta_micros,
      ledger_row.balance_after_micros,
      ledger_row.frozen_after_micros,
      coalesce(wallet_row.version, 0),
      ledger_row.idempotency_key,
      ledger_row.reference_type,
      ledger_row.reference_id,
      ledger_row.created_at;
    return;
  end if;

  insert into public.wallets (
    user_id,
    balance_micros,
    frozen_micros,
    plan_id,
    version
  )
  values (
    p_user_id,
    0,
    0,
    'free',
    0
  )
  on conflict on constraint wallets_pkey do nothing;

  select *
    into wallet_row
    from public.wallets w
   where w.user_id = p_user_id
   for update;

  select *
    into ledger_row
    from public.wallet_ledger wl
   where wl.idempotency_key = p_idempotency_key
   limit 1;

  if found then
    return query
    select
      ledger_row.id,
      ledger_row.user_id,
      ledger_row.event_type,
      ledger_row.delta_micros,
      ledger_row.balance_after_micros,
      ledger_row.frozen_after_micros,
      coalesce(wallet_row.version, 0),
      ledger_row.idempotency_key,
      ledger_row.reference_type,
      ledger_row.reference_id,
      ledger_row.created_at;
    return;
  end if;

  next_balance_micros := coalesce(wallet_row.balance_micros, 0) + p_delta_micros;

  if p_delta_micros < 0
     and next_balance_micros < coalesce(wallet_row.frozen_micros, 0) then
    raise exception 'Insufficient wallet balance.'
      using
        errcode = 'P0001',
        detail = format(
          'available_micros=%s requested_delta_micros=%s',
          greatest(coalesce(wallet_row.balance_micros, 0) - coalesce(wallet_row.frozen_micros, 0), 0),
          p_delta_micros
        );
  end if;

  if next_balance_micros < 0 then
    raise exception 'Wallet balance cannot become negative.'
      using errcode = 'P0001';
  end if;

  next_version := greatest(coalesce(wallet_row.version, 0), 0) + 1;

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
  values (
    gen_random_uuid(),
    p_user_id,
    trim(p_event_type),
    p_delta_micros,
    next_balance_micros,
    coalesce(wallet_row.frozen_micros, 0),
    nullif(trim(p_reference_type), ''),
    nullif(trim(p_reference_id), ''),
    coalesce(nullif(trim(p_reason), ''), trim(p_event_type)),
    trim(p_idempotency_key),
    coalesce(nullif(trim(p_operator_type), ''), 'system'),
    nullif(trim(p_operator_id), ''),
    coalesce(p_metadata, '{}'::jsonb),
    now()
  )
  returning *
    into ledger_row;

  update public.wallets
     set balance_micros = ledger_row.balance_after_micros,
         frozen_micros = ledger_row.frozen_after_micros,
         version = next_version,
         plan_id = coalesce(nullif(trim(wallet_row.plan_id), ''), 'free')
   where wallets.user_id = p_user_id;

  return query
  select
    ledger_row.id,
    ledger_row.user_id,
    ledger_row.event_type,
    ledger_row.delta_micros,
    ledger_row.balance_after_micros,
    ledger_row.frozen_after_micros,
    next_version,
    ledger_row.idempotency_key,
    ledger_row.reference_type,
    ledger_row.reference_id,
    ledger_row.created_at;
exception
  when unique_violation then
    select *
      into ledger_row
      from public.wallet_ledger wl
     where wl.idempotency_key = p_idempotency_key
     limit 1;

    if found then
      if ledger_row.user_id <> p_user_id then
        raise exception 'Idempotency key already belongs to another user.'
          using errcode = '23505';
      end if;

      select *
        into wallet_row
        from public.wallets w
       where w.user_id = p_user_id
       limit 1;

      return query
      select
        ledger_row.id,
        ledger_row.user_id,
        ledger_row.event_type,
        ledger_row.delta_micros,
        ledger_row.balance_after_micros,
        ledger_row.frozen_after_micros,
        coalesce(wallet_row.version, 0),
        ledger_row.idempotency_key,
        ledger_row.reference_type,
        ledger_row.reference_id,
        ledger_row.created_at;
      return;
    end if;

    raise;
end;
$$;

revoke all on function public.apply_wallet_mutation(
  uuid,
  text,
  bigint,
  text,
  text,
  text,
  text,
  text,
  text,
  jsonb
) from public;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public.apply_wallet_mutation(
      uuid,
      text,
      bigint,
      text,
      text,
      text,
      text,
      text,
      text,
      jsonb
    ) to service_role;
  end if;
end $$;

comment on function public.apply_wallet_mutation(
  uuid,
  text,
  bigint,
  text,
  text,
  text,
  text,
  text,
  text,
  jsonb
) is 'Atomic wallet mutation RPC for debit/grant/refund/admin_adjust. Handles wallet bootstrap, idempotency, ledger append, and wallet projection update.';

commit;
