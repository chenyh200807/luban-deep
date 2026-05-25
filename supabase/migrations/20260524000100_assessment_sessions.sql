begin;

create extension if not exists pgcrypto;

create table if not exists public.assessment_sessions (
  session_id uuid primary key default gen_random_uuid(),
  quiz_id text not null default ('quiz_' || replace(gen_random_uuid()::text, '-', '')),
  user_id text not null,
  assessment_type text not null,
  subject_id text not null,
  topic_ids text[] not null default array[]::text[],
  blueprint_version text not null,
  form_id text not null,
  status text not null default 'in_progress',
  schema_version text not null default 'assessment_session_v1',
  client_questions_public jsonb not null default '[]'::jsonb,
  session_questions_private jsonb not null default '[]'::jsonb,
  draft_answer_snapshot jsonb,
  submitted_answer_snapshot jsonb,
  submit_idempotency_key text,
  result_report_json jsonb,
  result_report_hash text,
  learning_event_refs jsonb not null default '[]'::jsonb,
  mistake_book_refs jsonb not null default '[]'::jsonb,
  degraded_reason text,
  device_id text not null default '',
  lease_expires_at timestamptz,
  lease_history jsonb not null default '[]'::jsonb,
  created_trace_id text not null default '',
  created_at timestamptz not null default now(),
  submitted_at timestamptz,
  scored_at timestamptz,
  expires_at timestamptz not null default (now() + interval '24 hours'),
  updated_at timestamptz not null default now(),
  constraint uq_assessment_sessions_quiz_id unique (quiz_id),
  constraint chk_assessment_sessions_status
    check (status in ('in_progress', 'submitted', 'scored', 'degraded', 'expired')),
  constraint chk_assessment_sessions_schema_version
    check (schema_version = 'assessment_session_v1'),
  constraint chk_assessment_sessions_report_schema
    check (
      result_report_json is null
      or result_report_json->>'schema_version' = 'p0a-v1'
    ),
  constraint chk_assessment_sessions_private_artifact_array
    check (jsonb_typeof(session_questions_private) = 'array'),
  constraint chk_assessment_sessions_public_artifact_array
    check (jsonb_typeof(client_questions_public) = 'array')
);

comment on table public.assessment_sessions is
  'Durable TestSet session authority. Stores redacted client payload and hidden grading artifacts separately.';

create index if not exists idx_assessment_sessions_user_status_created
  on public.assessment_sessions(user_id, status, created_at desc);

create index if not exists idx_assessment_sessions_user_assessment_blueprint
  on public.assessment_sessions(user_id, assessment_type, blueprint_version);

create index if not exists idx_assessment_sessions_expires_at
  on public.assessment_sessions(expires_at)
  where status = 'in_progress';

create unique index if not exists uq_assessment_sessions_submit_idempotency_key
  on public.assessment_sessions(submit_idempotency_key)
  where submit_idempotency_key is not null;

create unique index if not exists uq_assessment_sessions_active_formal_session
  on public.assessment_sessions(
    user_id,
    assessment_type,
    subject_id,
    blueprint_version,
    topic_ids
  )
  where status = 'in_progress';

alter table public.assessment_sessions enable row level security;

drop policy if exists "assessment_sessions_owner_select" on public.assessment_sessions;
create policy "assessment_sessions_owner_select"
  on public.assessment_sessions
  for select
  to authenticated
  using (auth.uid()::text = user_id);

drop policy if exists "assessment_sessions_owner_insert" on public.assessment_sessions;
create policy "assessment_sessions_owner_insert"
  on public.assessment_sessions
  for insert
  to authenticated
  with check (auth.uid()::text = user_id);

drop policy if exists "assessment_sessions_owner_update" on public.assessment_sessions;
create policy "assessment_sessions_owner_update"
  on public.assessment_sessions
  for update
  to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

grant select, insert, update on public.assessment_sessions to authenticated;

commit;
