begin;

alter table public.learner_summaries enable row level security;
alter table public.learner_memory_events enable row level security;
alter table public.learning_plans enable row level security;
alter table public.learning_plan_pages enable row level security;
alter table public.heartbeat_jobs enable row level security;
alter table public.bot_learner_overlays enable row level security;
alter table public.bot_learner_overlay_events enable row level security;
alter table public.bot_learner_overlay_audit enable row level security;

create policy "learner_summaries_self_access"
on public.learner_summaries
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "learner_memory_events_self_access"
on public.learner_memory_events
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "learning_plans_self_access"
on public.learning_plans
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "learning_plan_pages_self_access"
on public.learning_plan_pages
for all
to authenticated
using (
  exists (
    select 1
    from public.learning_plans lp
    where lp.plan_id = learning_plan_pages.plan_id
      and lp.user_id = auth.uid()::text
  )
)
with check (
  exists (
    select 1
    from public.learning_plans lp
    where lp.plan_id = learning_plan_pages.plan_id
      and lp.user_id = auth.uid()::text
  )
);

create policy "heartbeat_jobs_self_access"
on public.heartbeat_jobs
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "bot_learner_overlays_self_access"
on public.bot_learner_overlays
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "bot_learner_overlay_events_self_access"
on public.bot_learner_overlay_events
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

create policy "bot_learner_overlay_audit_self_access"
on public.bot_learner_overlay_audit
for all
to authenticated
using (auth.uid()::text = user_id)
with check (auth.uid()::text = user_id);

commit;
