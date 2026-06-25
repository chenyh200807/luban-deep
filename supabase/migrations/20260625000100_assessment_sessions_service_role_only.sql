-- assessment_sessions contains hidden grading artifacts:
--   session_questions_private, submitted_answer_snapshot, result_report_json.
-- The public mobile API is the only supported user-facing boundary; clients
-- must not read or mutate this base table directly.

alter table public.assessment_sessions enable row level security;
alter table public.assessment_sessions force row level security;

drop policy if exists "assessment_sessions_owner_select" on public.assessment_sessions;
drop policy if exists "assessment_sessions_owner_insert" on public.assessment_sessions;
drop policy if exists "assessment_sessions_owner_update" on public.assessment_sessions;

revoke all on public.assessment_sessions from anon;
revoke all on public.assessment_sessions from authenticated;

comment on table public.assessment_sessions is
  'Durable assessment session authority. Service-role only: contains hidden grading artifacts and submitted answer snapshots.';
