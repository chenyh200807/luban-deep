begin;

-- Phase 2 reserved schema.
-- These tables must remain subordinate to the user_id-level learner truth.
-- They are local-difference structures only, not parallel profile/progress/summary truths.

create table if not exists public.bot_learner_overlays (
  bot_id text not null,
  user_id uuid not null references public.users(id) on delete cascade,
  local_focus_json jsonb not null default '{}'::jsonb,
  active_plan_id text,
  teaching_policy_override_json jsonb not null default '{}'::jsonb,
  heartbeat_override_json jsonb not null default '{}'::jsonb,
  channel_presence_override_json jsonb not null default '{}'::jsonb,
  local_notebook_scope_refs_json jsonb not null default '[]'::jsonb,
  engagement_state_json jsonb not null default '{}'::jsonb,
  promotion_candidates_json jsonb not null default '[]'::jsonb,
  working_memory_projection_md text not null default '',
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (bot_id, user_id),
  constraint fk_bot_learner_overlays_active_plan
    foreign key (active_plan_id) references public.learning_plans(plan_id) on delete set null
);

comment on table public.bot_learner_overlays is
  'Phase 2 local-difference layer keyed by bot_id + user_id. Must never become a second learner truth.';

create index if not exists idx_bot_learner_overlays_user
  on public.bot_learner_overlays(user_id);

create index if not exists idx_bot_learner_overlays_active_plan
  on public.bot_learner_overlays(active_plan_id)
  where active_plan_id is not null;


create table if not exists public.bot_learner_overlay_events (
  event_id uuid primary key,
  bot_id text not null,
  user_id uuid not null references public.users(id) on delete cascade,
  source_feature text not null,
  source_id text not null,
  patch_kind text not null,
  payload_json jsonb not null,
  dedupe_key text not null,
  created_at timestamptz not null default now()
);

comment on table public.bot_learner_overlay_events is
  'Structured event stream for overlay patching, promotion candidates, and replay/debugging.';

create unique index if not exists idx_bot_learner_overlay_events_dedupe
  on public.bot_learner_overlay_events(dedupe_key);

create index if not exists idx_bot_learner_overlay_events_user_created
  on public.bot_learner_overlay_events(bot_id, user_id, created_at desc);


create table if not exists public.bot_learner_overlay_audit (
  audit_id uuid primary key,
  bot_id text not null,
  user_id uuid not null references public.users(id) on delete cascade,
  actor text,
  action text not null,
  fields_json jsonb not null default '[]'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

comment on table public.bot_learner_overlay_audit is
  'Audit log for critical overlay mutations and manual operations.';

create index if not exists idx_bot_learner_overlay_audit_user_created
  on public.bot_learner_overlay_audit(bot_id, user_id, created_at desc);

commit;
