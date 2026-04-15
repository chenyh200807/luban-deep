begin;

-- Phase 1 learner-state core tables.
-- These tables extend the existing reused truths:
--   - user_profiles
--   - user_stats
--   - user_goals
-- They must not create parallel profile/progress/goals truths.

create table if not exists public.learner_summaries (
  user_id uuid primary key references public.users(id) on delete cascade,
  summary_md text not null default '',
  summary_structured_json jsonb not null default '{}'::jsonb,
  last_refreshed_from_turn_id text,
  last_refreshed_from_feature text,
  updated_at timestamptz not null default now()
);

comment on table public.learner_summaries is
  'Single summary truth per user_id for long-term learner digest.';

create index if not exists idx_learner_summaries_updated_at
  on public.learner_summaries(updated_at desc);


create table if not exists public.learner_memory_events (
  event_id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  source_feature text not null,
  source_id text not null,
  source_bot_id text,
  memory_kind text not null,
  payload_json jsonb not null,
  dedupe_key text not null,
  created_at timestamptz not null default now()
);

comment on table public.learner_memory_events is
  'Unified long-term learner writeback event stream. Supports replay, audit, summary rebuild, and progress rebuild.';

create unique index if not exists idx_learner_memory_events_dedupe
  on public.learner_memory_events(dedupe_key);

create index if not exists idx_learner_memory_events_user_created
  on public.learner_memory_events(user_id, created_at desc);

create index if not exists idx_learner_memory_events_feature_created
  on public.learner_memory_events(source_feature, created_at desc);


create table if not exists public.learning_plans (
  plan_id text primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  source_bot_id text,
  source_material_refs_json jsonb not null default '[]'::jsonb,
  knowledge_points_json jsonb not null default '[]'::jsonb,
  status text not null,
  current_index integer not null default 0,
  completion_summary_md text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_learning_plans_status
    check (status in ('initialized', 'draft', 'active', 'paused', 'completed', 'cancelled'))
);

comment on table public.learning_plans is
  'Guided Learning plan truth per learner. Stores plan structure, status, and completion summary.';

create index if not exists idx_learning_plans_user_updated
  on public.learning_plans(user_id, updated_at desc);

create index if not exists idx_learning_plans_status_updated
  on public.learning_plans(status, updated_at desc);


create table if not exists public.learning_plan_pages (
  plan_id text not null references public.learning_plans(plan_id) on delete cascade,
  page_index integer not null,
  page_status text not null,
  html_content text,
  error_message text,
  generated_at timestamptz,
  primary key (plan_id, page_index),
  constraint chk_learning_plan_pages_status
    check (page_status in ('pending', 'generating', 'ready', 'failed'))
);

comment on table public.learning_plan_pages is
  'Per-page Guided Learning generation state and rendered HTML content.';


create table if not exists public.heartbeat_jobs (
  job_id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  bot_id text not null,
  channel text not null,
  policy_json jsonb not null default '{}'::jsonb,
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  last_result_json jsonb,
  failure_count integer not null default 0,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_heartbeat_jobs_status
    check (status in ('active', 'paused', 'disabled', 'failed'))
);

comment on table public.heartbeat_jobs is
  'Per-user heartbeat scheduling truth. Phase 1 keeps scheduling keyed by user_id even if bot_id is retained for routing.';

create index if not exists idx_heartbeat_jobs_due
  on public.heartbeat_jobs(status, next_run_at);

create unique index if not exists idx_heartbeat_jobs_user_bot_channel
  on public.heartbeat_jobs(user_id, bot_id, channel);

commit;
