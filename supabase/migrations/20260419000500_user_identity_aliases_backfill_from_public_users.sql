begin;

insert into public.user_identity_aliases (
  alias_type,
  alias_value,
  user_id,
  source,
  confidence,
  metadata
)
select
  'auth_username',
  u.identifier,
  w.user_id,
  'public_users_backfill',
  0.95,
  jsonb_build_object('public_user_id', u.id)
from public.users u
join public.wallets w on w.user_id::text = u.id
where coalesce(trim(u.identifier), '') <> ''
on conflict (alias_type, alias_value) do update
set user_id = excluded.user_id,
    source = excluded.source,
    confidence = excluded.confidence,
    metadata = excluded.metadata,
    updated_at = now();

insert into public.user_identity_aliases (
  alias_type,
  alias_value,
  user_id,
  source,
  confidence,
  metadata
)
select
  'phone',
  u.phone,
  w.user_id,
  'public_users_backfill',
  0.9,
  jsonb_build_object('public_user_id', u.id)
from public.users u
join public.wallets w on w.user_id::text = u.id
where coalesce(trim(u.phone), '') <> ''
on conflict (alias_type, alias_value) do update
set user_id = excluded.user_id,
    source = excluded.source,
    confidence = excluded.confidence,
    metadata = excluded.metadata,
    updated_at = now();

commit;
