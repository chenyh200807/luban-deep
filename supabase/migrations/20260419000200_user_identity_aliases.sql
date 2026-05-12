begin;

create table if not exists public.user_identity_aliases (
  alias_type text not null,
  alias_value text not null,
  user_id uuid not null,
  source text not null default 'migration',
  confidence numeric(5,4) not null default 1.0,
  metadata jsonb not null default '{}'::jsonb,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (alias_type, alias_value)
);

comment on table public.user_identity_aliases is
  'Canonical alias -> wallet user UUID mapping for wallet identity normalization.';

create index if not exists idx_user_identity_aliases_user_id
  on public.user_identity_aliases(user_id);

create or replace function public.touch_user_identity_aliases_updated_at()
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
    where tgname = 'trg_user_identity_aliases_touch_updated_at'
      and tgrelid = 'public.user_identity_aliases'::regclass
  ) then
    create trigger trg_user_identity_aliases_touch_updated_at
      before update on public.user_identity_aliases
      for each row
      execute function public.touch_user_identity_aliases_updated_at();
  end if;
end $$;

alter table public.user_identity_aliases enable row level security;

commit;
