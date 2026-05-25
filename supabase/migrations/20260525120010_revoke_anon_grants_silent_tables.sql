-- PR-2 SR2 — revoke anon/authenticated grants on 9 critical "silent service-role" tables
--
-- These tables already have RLS enabled but with 0 policies (effectively
-- service-role-only since RLS denies anon/authenticated by default). However,
-- they still have stale anon/authenticated GRANT entries from Supabase's
-- default schema-creation behavior, which:
--   (a) confuses future onboarding ("can client read this?" — no, RLS denies)
--   (b) is a footgun if anyone later writes `create policy ... for select using (true)`
--
-- This migration makes the "service-role only" intent explicit by revoking
-- the grants. Service-role bypasses RLS regardless of grants, so this is
-- functionally a no-op for the backend.
--
-- Scope: only the 9 most critical PII / wallet / auth tables. The remaining
-- ~26 silent tables (kb_chunks, sources, knowledge_*, standard_*, etc.) are
-- knowledge-base content; revoking their grants is lower priority and left
-- to a follow-up cleanup.

begin;

revoke all on public.users from anon;
revoke all on public.users from authenticated;
comment on table public.users is 'User accounts (PII). Service-role only; backend uses service_role bypass.';

revoke all on public.wallet_ledger from anon;
revoke all on public.wallet_ledger from authenticated;
comment on table public.wallet_ledger is 'Wallet ledger (financial). Service-role only.';

revoke all on public.user_identity_aliases from anon;
revoke all on public.user_identity_aliases from authenticated;
comment on table public.user_identity_aliases is 'Cross-platform user identity bindings (PII). Service-role only.';

revoke all on public.user_subscriptions from anon;
revoke all on public.user_subscriptions from authenticated;
comment on table public.user_subscriptions is 'Active subscription state. Service-role only.';

revoke all on public.user_mastery from anon;
revoke all on public.user_mastery from authenticated;
comment on table public.user_mastery is 'Per-user mastery scores. Service-role only.';

revoke all on public.invite_test_applications from anon;
revoke all on public.invite_test_applications from authenticated;
comment on table public.invite_test_applications is 'Invite-test registration form (PII: name / phone / wechat / email). Service-role only.';

revoke all on public.llm_usage_logs from anon;
revoke all on public.llm_usage_logs from authenticated;
comment on table public.llm_usage_logs is 'LLM call usage logs (may include prompt fragments). Service-role only.';

revoke all on public.api_call_logs from anon;
revoke all on public.api_call_logs from authenticated;
comment on table public.api_call_logs is 'API request audit log. Service-role only.';

revoke all on public.error_logs from anon;
revoke all on public.error_logs from authenticated;
comment on table public.error_logs is 'Backend error audit log. Service-role only.';

commit;
