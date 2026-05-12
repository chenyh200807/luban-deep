begin;

do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conname = 'wallet_ledger_user_id_fkey'
      and conrelid = 'public.wallet_ledger'::regclass
  ) then
    alter table public.wallet_ledger
      drop constraint wallet_ledger_user_id_fkey;
  end if;
end $$;

alter table public.wallet_ledger
  add constraint wallet_ledger_user_id_fkey
  foreign key (user_id)
  references public.wallets(user_id)
  on delete cascade;

do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conname = 'user_identity_aliases_user_id_fkey'
      and conrelid = 'public.user_identity_aliases'::regclass
  ) then
    alter table public.user_identity_aliases
      drop constraint user_identity_aliases_user_id_fkey;
  end if;
end $$;

commit;
