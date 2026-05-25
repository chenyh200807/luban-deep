-- PR-2 SR2 — close 25 RLS-off public business tables (v2.1 §3.2)
--
-- Discovered by PR-0 live RLS audit (scripts/ci/live_rls_audit.sh): 27 tables
-- in public schema had RLS=off + anon/authenticated grants. This migration
-- closes 25 of them (excluding 2 system metadata tables alembic_version /
-- schema_migrations which Supabase manages).
--
-- Strategy (codex review R2 alignment): enable RLS + revoke anon/authenticated
-- grants. Service-role bypass keeps backend access intact; no `for select using
-- (...)` policies are added because business logic flows through service_role
-- (verified by grep — clients use API gateway, not PostgREST directly).
--
-- Idempotency: every statement uses `enable row level security` (no-op if
-- already enabled) and `revoke all` (no-op if no grants). Safe to re-run.
--
-- Verification (post-apply):
--   bash scripts/ci/live_rls_audit.sh > /tmp/post.json
--   jq '.tables | map(select(.rls_enabled == false)) | length' /tmp/post.json
--   → should be 2 (only alembic_version + schema_migrations remain)

begin;

-- ============================================================================
-- 25 business tables: enable RLS + revoke anon/authenticated
-- ============================================================================

alter table public.assessment_forms enable row level security;
revoke all on public.assessment_forms from anon;
revoke all on public.assessment_forms from authenticated;
comment on table public.assessment_forms is 'Diagnostic assessment blueprints (answers / scoring_points). Service-role only; clients go through TutorBot/assessment service via API gateway.';

alter table public.compiled_asset_feedback_log enable row level security;
revoke all on public.compiled_asset_feedback_log from anon;
revoke all on public.compiled_asset_feedback_log from authenticated;
comment on table public.compiled_asset_feedback_log is 'Compiled asset feedback events. Service-role only.';

alter table public.daily_paths enable row level security;
revoke all on public.daily_paths from anon;
revoke all on public.daily_paths from authenticated;
comment on table public.daily_paths is 'Daily learning path projections. Service-role only.';

alter table public.heartbeat_jobs enable row level security;
revoke all on public.heartbeat_jobs from anon;
revoke all on public.heartbeat_jobs from authenticated;
comment on table public.heartbeat_jobs is 'Background heartbeat scheduling state. Service-role only.';

alter table public.intents enable row level security;
revoke all on public.intents from anon;
revoke all on public.intents from authenticated;
comment on table public.intents is 'Training intent catalog. Service-role only.';

alter table public.learner_memory_events enable row level security;
revoke all on public.learner_memory_events from anon;
revoke all on public.learner_memory_events from authenticated;
comment on table public.learner_memory_events is 'Learner memory event ledger (evidence-first memory). Service-role only.';

alter table public.learner_summaries enable row level security;
revoke all on public.learner_summaries from anon;
revoke all on public.learner_summaries from authenticated;
comment on table public.learner_summaries is 'Compiled learner truth + projections. Service-role only; surface via API.';

alter table public.learner_wikis enable row level security;
revoke all on public.learner_wikis from anon;
revoke all on public.learner_wikis from authenticated;
comment on table public.learner_wikis is 'Per-learner wiki content. Service-role only.';

alter table public.learning_plan_pages enable row level security;
revoke all on public.learning_plan_pages from anon;
revoke all on public.learning_plan_pages from authenticated;
comment on table public.learning_plan_pages is 'Learning plan child pages. Service-role only.';

alter table public.learning_plans enable row level security;
revoke all on public.learning_plans from anon;
revoke all on public.learning_plans from authenticated;
comment on table public.learning_plans is 'Personalized learning plan documents. Service-role only.';

alter table public.member_audit_log enable row level security;
revoke all on public.member_audit_log from anon;
revoke all on public.member_audit_log from authenticated;
comment on table public.member_audit_log is 'Member-side audit events. Service-role only; never readable by audited subjects.';

alter table public.member_notes enable row level security;
revoke all on public.member_notes from anon;
revoke all on public.member_notes from authenticated;
comment on table public.member_notes is 'Internal member-management notes (PII). Service-role only.';

alter table public.oa_anomalies enable row level security;
revoke all on public.oa_anomalies from anon;
revoke all on public.oa_anomalies from authenticated;
comment on table public.oa_anomalies is 'Observability OA anomaly events. Service-role only.';

alter table public.oa_causal_links enable row level security;
revoke all on public.oa_causal_links from anon;
revoke all on public.oa_causal_links from authenticated;
comment on table public.oa_causal_links is 'Observability OA causal-link graph. Service-role only.';

alter table public.oa_change_events enable row level security;
revoke all on public.oa_change_events from anon;
revoke all on public.oa_change_events from authenticated;
comment on table public.oa_change_events is 'Observability OA system-change events. Service-role only.';

alter table public.oa_playbooks enable row level security;
revoke all on public.oa_playbooks from anon;
revoke all on public.oa_playbooks from authenticated;
comment on table public.oa_playbooks is 'Observability OA incident playbooks. Service-role only.';

alter table public.oa_runs enable row level security;
revoke all on public.oa_runs from anon;
revoke all on public.oa_runs from authenticated;
comment on table public.oa_runs is 'Observability OA runtime runs. Service-role only.';

alter table public.oa_signals enable row level security;
revoke all on public.oa_signals from anon;
revoke all on public.oa_signals from authenticated;
comment on table public.oa_signals is 'Observability OA telemetry signals. Service-role only.';

alter table public.org_members enable row level security;
revoke all on public.org_members from anon;
revoke all on public.org_members from authenticated;
comment on table public.org_members is 'Org-to-user membership join. Service-role only.';

alter table public.organizations enable row level security;
revoke all on public.organizations from anon;
revoke all on public.organizations from authenticated;
comment on table public.organizations is 'Organization records. Service-role only.';

alter table public.platform_user_bindings enable row level security;
revoke all on public.platform_user_bindings from anon;
revoke all on public.platform_user_bindings from authenticated;
comment on table public.platform_user_bindings is 'Platform-specific user identity bindings (PII). Service-role only.';

alter table public.question_intelligence enable row level security;
revoke all on public.question_intelligence from anon;
revoke all on public.question_intelligence from authenticated;
comment on table public.question_intelligence is 'Question-level intelligence projections. Service-role only.';

alter table public.run_evidences enable row level security;
revoke all on public.run_evidences from anon;
revoke all on public.run_evidences from authenticated;
comment on table public.run_evidences is 'Per-run evidence ledger. Service-role only.';

alter table public.teaching_cards enable row level security;
revoke all on public.teaching_cards from anon;
revoke all on public.teaching_cards from authenticated;
comment on table public.teaching_cards is 'Teaching-card catalog (may include answers / rubrics). Service-role only.';

alter table public.user_sessions enable row level security;
revoke all on public.user_sessions from anon;
revoke all on public.user_sessions from authenticated;
comment on table public.user_sessions is 'User session metadata (PII / auth state). Service-role only.';

commit;
