begin;

create table if not exists public.experience_invites (
  id uuid primary key default gen_random_uuid(),
  code_hash text not null unique check (char_length(code_hash) = 64),
  code_prefix text not null,
  source text not null default 'yousen_paid_student',
  status text not null default 'active' check (status in ('active', 'revoked')),
  max_redemptions integer not null default 1 check (max_redemptions > 0),
  redeemed_count integer not null default 0 check (redeemed_count >= 0),
  valid_until timestamptz,
  created_by text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.experience_access (
  user_id text primary key,
  invite_id uuid not null references public.experience_invites(id),
  source text not null,
  redeemed_at timestamptz not null default now(),
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists public.experience_turn_costs (
  user_id text not null references public.experience_access(user_id),
  turn_key text not null,
  usage_date date not null,
  reservation_micros bigint not null check (reservation_micros >= 0),
  actual_micros bigint check (actual_micros >= 0),
  provenance text,
  status text not null check (status in ('reserved', 'settled', 'released')),
  release_reason text,
  created_at timestamptz not null default now(),
  settled_at timestamptz,
  primary key (user_id, turn_key)
);

create index if not exists experience_turn_costs_user_day_idx
  on public.experience_turn_costs(user_id, usage_date);

comment on table public.experience_invites is
  'Yousen paid-student experience invite definitions. Service-role only; raw codes are never stored.';
comment on table public.experience_access is
  'Canonical 14-day invite experience entitlement per user. Service-role only.';
comment on table public.experience_turn_costs is
  'Canonical per-user invite AI cost reservations and settlements. Service-role only.';

alter table public.experience_invites enable row level security;
alter table public.experience_invites force row level security;
alter table public.experience_access enable row level security;
alter table public.experience_access force row level security;
alter table public.experience_turn_costs enable row level security;
alter table public.experience_turn_costs force row level security;

create or replace function public.redeem_experience_invite(
  p_user_id text,
  p_code_hash text
) returns table(state text, redeemed_at timestamptz, expires_at timestamptz, source text)
language plpgsql security definer set search_path = public
as $$
declare
  v_invite public.experience_invites%rowtype;
  v_access public.experience_access%rowtype;
begin
  if nullif(trim(p_user_id), '') is null then raise exception 'user_id_required'; end if;
  perform pg_advisory_xact_lock(hashtextextended(p_user_id, 0));
  select * into v_access from public.experience_access where user_id = p_user_id for update;
  if found then
    return query select
      case when v_access.expires_at > now() then 'active' else 'expired' end,
      v_access.redeemed_at, v_access.expires_at, v_access.source;
    return;
  end if;

  select * into v_invite from public.experience_invites
   where code_hash = p_code_hash for update;
  if not found or v_invite.status <> 'active' then raise exception 'invite_invalid'; end if;
  if v_invite.valid_until is not null and v_invite.valid_until <= now() then raise exception 'invite_expired'; end if;
  if v_invite.redeemed_count >= v_invite.max_redemptions then raise exception 'invite_exhausted'; end if;

  insert into public.experience_access(user_id, invite_id, source, expires_at)
  values (p_user_id, v_invite.id, v_invite.source, now() + interval '14 days')
  returning * into v_access;
  update public.experience_invites set redeemed_count = redeemed_count + 1 where id = v_invite.id;
  return query select 'active'::text, v_access.redeemed_at, v_access.expires_at, v_access.source;
end;
$$;

create or replace function public.reserve_experience_turn(
  p_user_id text,
  p_turn_key text,
  p_reservation_micros bigint,
  p_daily_limit_micros bigint
) returns jsonb language plpgsql security definer set search_path = public
as $$
declare
  v_access public.experience_access%rowtype;
  v_existing public.experience_turn_costs%rowtype;
  v_existing_found boolean := false;
  v_total bigint;
  v_day date := (now() at time zone 'Asia/Shanghai')::date;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id, 0));
  select * into v_access from public.experience_access where user_id = p_user_id for update;
  if not found then return jsonb_build_object('allowed', false, 'reason', 'not_redeemed'); end if;
  if v_access.expires_at <= now() then return jsonb_build_object('allowed', false, 'reason', 'expired'); end if;
  select * into v_existing
    from public.experience_turn_costs
   where user_id = p_user_id and turn_key = p_turn_key;
  v_existing_found := found;
  if v_existing_found and v_existing.status in ('reserved', 'settled') then
    return jsonb_build_object(
      'allowed', false,
      'reason', case
        when v_existing.status = 'reserved' then 'in_progress'
        else 'already_settled'
      end,
      'turn_key', p_turn_key
    );
  end if;
  select coalesce(sum(case when status = 'settled' then actual_micros else reservation_micros end), 0)
    into v_total from public.experience_turn_costs
   where user_id = p_user_id and usage_date = v_day and status in ('reserved', 'settled');
  if v_total + p_reservation_micros > p_daily_limit_micros then
    return jsonb_build_object('allowed', false, 'reason', 'daily_limit');
  end if;
  if v_existing_found then
    update public.experience_turn_costs
       set usage_date = v_day,
           reservation_micros = p_reservation_micros,
           actual_micros = null,
           provenance = null,
           status = 'reserved',
           release_reason = null,
           created_at = now(),
           settled_at = null
     where user_id = p_user_id and turn_key = p_turn_key;
  else
    insert into public.experience_turn_costs(turn_key, user_id, usage_date, reservation_micros, status)
    values (p_turn_key, p_user_id, v_day, p_reservation_micros, 'reserved');
  end if;
  return jsonb_build_object('allowed', true, 'reason', 'reserved', 'turn_key', p_turn_key);
end;
$$;

create or replace function public.release_experience_turn(
  p_user_id text, p_turn_key text, p_reason text
) returns void language plpgsql security definer set search_path = public
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id, 0));
  update public.experience_turn_costs set status = 'released', release_reason = left(p_reason, 64)
   where turn_key = p_turn_key and user_id = p_user_id and status = 'reserved';
end;
$$;

create or replace function public.settle_experience_turn(
  p_user_id text,
  p_turn_key text,
  p_actual_micros bigint,
  p_provenance text,
  p_daily_limit_micros bigint
) returns jsonb language plpgsql security definer set search_path = public
as $$
declare
  v_total bigint;
  v_existing_status text;
  v_existing_provenance text;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id, 0));
  update public.experience_turn_costs
     set status = 'settled',
         actual_micros = greatest(0, p_actual_micros),
         provenance = left(p_provenance, 80),
         settled_at = now()
   where turn_key = p_turn_key and user_id = p_user_id and status = 'reserved'
   returning provenance into v_existing_provenance;
  if not found then
    select status, provenance into v_existing_status, v_existing_provenance
      from public.experience_turn_costs
     where turn_key = p_turn_key and user_id = p_user_id;
    if v_existing_status = 'settled' then
      select coalesce(sum(actual_micros), 0) into v_total
        from public.experience_turn_costs
       where user_id = p_user_id
         and usage_date = (now() at time zone 'Asia/Shanghai')::date
         and status = 'settled';
      return jsonb_build_object(
        'status', 'settled',
        'daily_blocked', v_total >= p_daily_limit_micros,
        'provenance', v_existing_provenance
      );
    end if;
    return jsonb_build_object(
      'status', 'missing_reservation',
      'daily_blocked', true,
      'provenance', null
    );
  end if;
  select coalesce(sum(actual_micros), 0) into v_total
    from public.experience_turn_costs
     where user_id = p_user_id
       and usage_date = (now() at time zone 'Asia/Shanghai')::date
       and status = 'settled';
  return jsonb_build_object(
    'status', 'settled',
    'daily_blocked', v_total >= p_daily_limit_micros,
    'provenance', v_existing_provenance
  );
end;
$$;

revoke all on public.experience_invites, public.experience_access, public.experience_turn_costs from anon;
revoke all on public.experience_invites, public.experience_access, public.experience_turn_costs from authenticated;
grant select, insert, update on public.experience_invites to service_role;
grant select, insert, update on public.experience_access to service_role;
grant select, insert, update on public.experience_turn_costs to service_role;
revoke all on function public.redeem_experience_invite(text,text) from public, anon, authenticated;
revoke all on function public.reserve_experience_turn(text,text,bigint,bigint) from public, anon, authenticated;
revoke all on function public.release_experience_turn(text,text,text) from public, anon, authenticated;
revoke all on function public.settle_experience_turn(text,text,bigint,text,bigint) from public, anon, authenticated;
grant execute on function public.redeem_experience_invite(text,text) to service_role;
grant execute on function public.reserve_experience_turn(text,text,bigint,bigint) to service_role;
grant execute on function public.release_experience_turn(text,text,text) to service_role;
grant execute on function public.settle_experience_turn(text,text,bigint,text,bigint) to service_role;

commit;
