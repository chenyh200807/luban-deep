-- H10: harden public.wallets (the wallet balance / money table).
--
-- BEFORE (audited 2026-05-30 against production): RLS is enabled with two correct
-- policies, but anon AND authenticated still hold the full table-level DML grant
-- (SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER). Today RLS denies anon
-- (no anon policy) and scopes authenticated to its own row, so it is not externally
-- exploitable — but the latent grant means a single future mistake (RLS disabled, or
-- a permissive policy added, or the Data API exposing the public schema) would expose
-- every wallet balance. This migration removes that latent surface, matching the P5
-- pattern (20260525120010 / 20260529000300) for the other PII/wallet tables.
--
-- The application backend connects as service_role over the direct DB_URL (bypasses
-- RLS and keeps its own grants), so revoking anon/authenticated does NOT affect it —
-- same as P5. Idempotent + transaction-safe (re-runnable).

begin;

-- RLS stays on (already enabled; idempotent re-assert).
alter table public.wallets enable row level security;

-- Bring the two out-of-band policies into version control (single authority), matching
-- the exact definitions audited in production. Re-declared idempotently.
drop policy if exists wallets_service_bypass on public.wallets;
create policy wallets_service_bypass on public.wallets
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists wallets_user_isolation on public.wallets;
create policy wallets_user_isolation on public.wallets
  for all
  to authenticated
  using (user_id = (select auth.uid()));

-- Remove the latent full-DML grant from the PostgREST roles. Wallet mutations must go
-- through service_role (apply_wallet_mutation RPC / direct DB_URL), never anon/auth.
revoke all on public.wallets from anon;
revoke all on public.wallets from authenticated;

commit;
