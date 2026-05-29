-- P5 — eliminate latent Supabase RLS landmine on user_profiles / user_stats (+ 6 sibling tables)
--
-- Root cause (discovered by scripts/ci/live_rls_audit.sh + docs/audit/rls_audit.json):
-- `public.user_profiles` and `public.user_stats` carry an RLS policy literally named
-- "Enable all for service role" that is actually scoped to role=public with USING(true)
-- — i.e. it grants every action to anon + authenticated, not just service_role. On top of
-- that, both tables hold the full anon/authenticated INSERT/SELECT/UPDATE/DELETE grant set
-- (Supabase default schema-creation behavior). These 8 tables were created out-of-band
-- (Supabase dashboard / legacy bootstrap) and have NO `create table` migration in this repo,
-- which is why the static gate (check_rls_on_create_table.sh) never caught them.
--
-- Not currently externally exploitable: the Supabase Data API (PostgREST) does not expose the
-- public schema, and the FastAPI backend talks to Postgres via DB_URL (direct connection,
-- service_role / superuser — RLS is bypassed). But the moment the Data API is enabled for
-- public, a USING(true)/public policy + anon grants = full dump of user PII. This migration
-- closes that latent hole. Because the app bypasses RLS via DB_URL, none of this affects
-- business behavior.
--
-- Strategy (A+B, matching prior SR2 migrations 20260525120000 / 20260525120010):
--   A) DROP the misnamed role=public USING(true) policies and rebuild owner-scoped policies
--      (auth.uid()::text = user_id) for the PII tables. A dedicated service_role ALL policy
--      makes the "full access" intent explicit and correctly role-restricted.
--   B) REVOKE ALL on every table from anon + authenticated. service_role bypasses RLS, so
--      backend access via DB_URL / service_role key is unaffected.
--
-- Per-table disposition (rationale in PR body):
--   PII / user-owned (auth.uid()::text = user_id owner policies + service_role ALL + revoke):
--     user_profiles, user_stats, user_goals, user_logs, user_emotion_logs, user_badges
--   PII / user-owned, already correctly policied by migration 20260521000100 (revoke only):
--     learner_mistake_book_items
--   Content / question bank (revoke anon+authenticated; clients never hit PostgREST directly,
--     backend reads via service_role; no owner policy because rows are not user-scoped):
--     questions_bank, mock_exams
--
-- Idempotency: every statement uses IF EXISTS / DROP-then-CREATE / `revoke all` (no-op when
-- nothing to revoke) / `enable row level security` (no-op when already on). Safe to re-run.
--
-- IMPORTANT (operator action — see PR body): this file only encodes intent. To actually close
-- the live hole, apply it to production Supabase and re-run the audit:
--   SUPABASE_DB_URL='postgresql://postgres.<proj>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres' \
--     bash scripts/ci/live_rls_audit.sh > /tmp/post.json
--   jq -c '.tables[] | select(.table=="user_profiles" or .table=="user_stats")
--          | {table, n_policies, anon: ([.grants[] | select(startswith("anon:"))] | length),
--             auth: ([.grants[] | select(startswith("authenticated:"))] | length)}' /tmp/post.json
--   → both tables must show anon:0 and authenticated:0.

begin;

-- ============================================================================
-- A) Drop the misnamed role=public USING(true) "service role" policies.
--    Named drops first (the known offender), then a defensive catch for the
--    other historical policy names that may exist on these tables across envs.
-- ============================================================================

-- user_profiles
drop policy if exists "Enable all for service role" on public.user_profiles;
drop policy if exists "Enable read access for all users" on public.user_profiles;
drop policy if exists "Enable insert for all users" on public.user_profiles;
drop policy if exists "Enable update for all users" on public.user_profiles;
drop policy if exists "Enable delete for all users" on public.user_profiles;

-- user_stats
drop policy if exists "Enable all for service role" on public.user_stats;
drop policy if exists "Enable read access for all users" on public.user_stats;
drop policy if exists "Enable insert for all users" on public.user_stats;
drop policy if exists "Enable update for all users" on public.user_stats;
drop policy if exists "Enable delete for all users" on public.user_stats;

-- user_goals
drop policy if exists "Enable all for service role" on public.user_goals;
drop policy if exists "Enable read access for all users" on public.user_goals;

-- user_logs
drop policy if exists "Enable all for service role" on public.user_logs;
drop policy if exists "Enable read access for all users" on public.user_logs;

-- user_emotion_logs
drop policy if exists "Enable all for service role" on public.user_emotion_logs;
drop policy if exists "Enable read access for all users" on public.user_emotion_logs;

-- user_badges
drop policy if exists "Enable all for service role" on public.user_badges;
drop policy if exists "Enable read access for all users" on public.user_badges;

-- ============================================================================
-- Ensure RLS is enabled on every target table (no-op when already enabled).
-- ============================================================================

alter table public.user_profiles enable row level security;
alter table public.user_stats enable row level security;
alter table public.user_goals enable row level security;
alter table public.user_logs enable row level security;
alter table public.user_emotion_logs enable row level security;
alter table public.user_badges enable row level security;
alter table public.learner_mistake_book_items enable row level security;
alter table public.questions_bank enable row level security;
alter table public.mock_exams enable row level security;

-- ============================================================================
-- Rebuild owner-scoped policies for PII tables (auth.uid()::text = user_id),
-- plus an explicit, correctly role-restricted service_role ALL policy.
-- DROP IF EXISTS before CREATE keeps this re-runnable (Postgres has no
-- `create policy if not exists`).
-- ============================================================================

-- user_profiles -------------------------------------------------------------
drop policy if exists "user_profiles_owner_access" on public.user_profiles;
create policy "user_profiles_owner_access"
  on public.user_profiles
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_profiles_service_role_all" on public.user_profiles;
create policy "user_profiles_service_role_all"
  on public.user_profiles
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_profiles is
  'User profile records (PII). RLS: owner-only for authenticated (auth.uid()=user_id), service_role full. anon/authenticated grants revoked; backend uses DB_URL/service_role bypass.';

-- user_stats ----------------------------------------------------------------
drop policy if exists "user_stats_owner_access" on public.user_stats;
create policy "user_stats_owner_access"
  on public.user_stats
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_stats_service_role_all" on public.user_stats;
create policy "user_stats_service_role_all"
  on public.user_stats
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_stats is
  'Per-user statistics (PII). RLS: owner-only for authenticated, service_role full. anon/authenticated grants revoked.';

-- user_goals ----------------------------------------------------------------
drop policy if exists "user_goals_owner_access" on public.user_goals;
create policy "user_goals_owner_access"
  on public.user_goals
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_goals_service_role_all" on public.user_goals;
create policy "user_goals_service_role_all"
  on public.user_goals
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_goals is
  'Per-user learning goals (PII). RLS: owner-only for authenticated, service_role full. anon/authenticated grants revoked.';

-- user_logs -----------------------------------------------------------------
drop policy if exists "user_logs_owner_access" on public.user_logs;
create policy "user_logs_owner_access"
  on public.user_logs
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_logs_service_role_all" on public.user_logs;
create policy "user_logs_service_role_all"
  on public.user_logs
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_logs is
  'Per-user activity logs (PII). RLS: owner-only for authenticated, service_role full. anon/authenticated grants revoked.';

-- user_emotion_logs ---------------------------------------------------------
drop policy if exists "user_emotion_logs_owner_access" on public.user_emotion_logs;
create policy "user_emotion_logs_owner_access"
  on public.user_emotion_logs
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_emotion_logs_service_role_all" on public.user_emotion_logs;
create policy "user_emotion_logs_service_role_all"
  on public.user_emotion_logs
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_emotion_logs is
  'Per-user emotion/affect logs (sensitive PII). RLS: owner-only for authenticated, service_role full. anon/authenticated grants revoked.';

-- user_badges ---------------------------------------------------------------
drop policy if exists "user_badges_owner_access" on public.user_badges;
create policy "user_badges_owner_access"
  on public.user_badges
  for all
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists "user_badges_service_role_all" on public.user_badges;
create policy "user_badges_service_role_all"
  on public.user_badges
  for all
  to service_role
  using (true)
  with check (true);

comment on table public.user_badges is
  'Per-user earned badges (PII). RLS: owner-only for authenticated, service_role full. anon/authenticated grants revoked.';

-- learner_mistake_book_items ------------------------------------------------
-- Already has correct owner-scoped policies from 20260521000100; only its stale
-- anon/authenticated grants remain. Revoke handled in section B below.
comment on table public.learner_mistake_book_items is
  'Per-user mistake book (PII). RLS: owner-only policies from 20260521000100. anon/authenticated grants revoked.';

-- questions_bank ------------------------------------------------------------
-- Content table (shared question bank, not user-scoped). No owner policy: rows
-- belong to no single user. Backend reads it via service_role (DB_URL bypass and
-- assessment blueprint_service prefers SUPABASE_SERVICE_ROLE_KEY). Clients never
-- hit PostgREST directly (see docs/audit/README.md). Revoke anon/authenticated
-- (incl. read) so a leaked anon key cannot dump the question bank if the Data API
-- is ever enabled. No service_role policy needed — service_role bypasses RLS.
comment on table public.questions_bank is
  'Shared question bank (content, not user-scoped). Service-role only; anon/authenticated grants revoked. Clients go through the API gateway, never PostgREST.';

-- mock_exams ----------------------------------------------------------------
comment on table public.mock_exams is
  'Mock exam definitions (content, not user-scoped). Service-role only; anon/authenticated grants revoked. Clients go through the API gateway, never PostgREST.';

-- ============================================================================
-- B) Revoke all anon/authenticated grants on every target table.
--    service_role retains its grants and bypasses RLS, so the backend is
--    unaffected. `revoke all` is a no-op when no grant exists (idempotent).
-- ============================================================================

revoke all on public.user_profiles from anon;
revoke all on public.user_profiles from authenticated;

revoke all on public.user_stats from anon;
revoke all on public.user_stats from authenticated;

revoke all on public.user_goals from anon;
revoke all on public.user_goals from authenticated;

revoke all on public.user_logs from anon;
revoke all on public.user_logs from authenticated;

revoke all on public.user_emotion_logs from anon;
revoke all on public.user_emotion_logs from authenticated;

revoke all on public.user_badges from anon;
revoke all on public.user_badges from authenticated;

revoke all on public.learner_mistake_book_items from anon;
revoke all on public.learner_mistake_book_items from authenticated;

revoke all on public.questions_bank from anon;
revoke all on public.questions_bank from authenticated;

revoke all on public.mock_exams from anon;
revoke all on public.mock_exams from authenticated;

commit;
