-- Assessment TestSet P0B/P1 Gate 0 hotfix.
--
-- public.assessment_forms stores answer-bearing items_json so it must be
-- service-role only. Client-facing assessment traffic goes through the FastAPI
-- assessment service, which redacts hidden grading authority before submit.
--
-- This migration is intentionally narrow: do not bundle unrelated public table
-- RLS cleanup into the assessment flywheel gate.

begin;

alter table public.assessment_forms enable row level security;
revoke all on public.assessment_forms from anon;
revoke all on public.assessment_forms from authenticated;

comment on table public.assessment_forms is
  'Assessment form bank with answer-bearing items_json. Service-role only; clients must use the API redacted assessment endpoints.';

create or replace view public.assessment_forms_public
with (security_invoker = true)
as
select
  form_id,
  blueprint_version,
  form_index,
  status,
  question_bank_size,
  fallback_used,
  quality_json,
  generated_at,
  updated_at
from public.assessment_forms;

revoke all on public.assessment_forms_public from anon;
revoke all on public.assessment_forms_public from authenticated;

comment on view public.assessment_forms_public is
  'Redacted assessment form metadata view. It deliberately excludes items_json and all hidden answer/grading authority.';

commit;
