create table if not exists public.learner_notebook_cards (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  note_id text not null,
  subject_id text not null default '',
  source_bot_id text not null default '',
  card_type text not null default 'manual_note',
  source_type text not null default 'manual',
  source_ref jsonb not null default '{}'::jsonb,
  evidence_event_ids jsonb not null default '[]'::jsonb,
  title text default '',
  raw_user_content text default '',
  ai_enhanced_content jsonb not null default '{}'::jsonb,
  linked_knowledge_points jsonb not null default '[]'::jsonb,
  linked_error_patterns jsonb not null default '[]'::jsonb,
  user_control_status text not null default 'confirmed',
  use_for_personalization boolean not null default true,
  mastery_effect text not null default 'none',
  version integer not null default 1,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, note_id)
);

create index if not exists idx_learner_notebook_cards_user_updated
  on public.learner_notebook_cards(user_id, updated_at desc)
  where archived_at is null;

create index if not exists idx_learner_notebook_cards_user_subject_type
  on public.learner_notebook_cards(user_id, subject_id, card_type, updated_at desc)
  where archived_at is null;

alter table public.learner_notebook_cards enable row level security;

create policy "learner_notebook_cards_owner_select"
  on public.learner_notebook_cards
  for select using (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_insert"
  on public.learner_notebook_cards
  for insert with check (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_update"
  on public.learner_notebook_cards
  for update using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

create policy "learner_notebook_cards_owner_delete"
  on public.learner_notebook_cards
  for delete using (auth.uid()::text = user_id);
