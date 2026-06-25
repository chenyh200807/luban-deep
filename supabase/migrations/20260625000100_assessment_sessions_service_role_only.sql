-- Assessment TestSet session hardening.
--
-- public.assessment_sessions stores hidden grading authority
-- (session_questions_private, submitted_answer_snapshot, result_report_json).
-- Client-facing assessment traffic must go through the FastAPI assessment
-- endpoints, which return redacted public payloads before submit.

begin;

alter table public.assessment_sessions enable row level security;
alter table public.assessment_sessions force row level security;

drop policy if exists "assessment_sessions_owner_select" on public.assessment_sessions;
drop policy if exists "assessment_sessions_owner_insert" on public.assessment_sessions;
drop policy if exists "assessment_sessions_owner_update" on public.assessment_sessions;

revoke all on public.assessment_sessions from anon;
revoke all on public.assessment_sessions from authenticated;

comment on table public.assessment_sessions is
  'Durable TestSet session authority. Service-role only; stores redacted client payload and hidden grading artifacts separately.';

commit;
