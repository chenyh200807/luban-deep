create table if not exists public.learner_mistake_book_items (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  subject_id text not null default '',
  bot_id text not null default '',
  event_id text not null,
  question_id text default '',
  attempt_ref text not null,
  title text default '',
  concept_label text default '',
  error_label text default '',
  saved_at timestamptz not null default now(),
  archived_at timestamptz,
  mastered_at timestamptz,
  last_reviewed_at timestamptz,
  review_due_at timestamptz,
  note text default '',
  tags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, event_id)
);

create index if not exists idx_learner_mistake_book_user_saved
  on public.learner_mistake_book_items(user_id, saved_at desc)
  where archived_at is null and mastered_at is null;

create index if not exists idx_learner_mistake_book_user_subject
  on public.learner_mistake_book_items(user_id, subject_id, saved_at desc)
  where archived_at is null;

create index if not exists idx_learner_mistake_book_user_subject_bot
  on public.learner_mistake_book_items(user_id, subject_id, bot_id, saved_at desc)
  where archived_at is null;

create index if not exists idx_learner_mistake_book_review_due
  on public.learner_mistake_book_items(user_id, review_due_at)
  where archived_at is null and mastered_at is null and review_due_at is not null;

alter table public.learner_mistake_book_items enable row level security;

create policy "learner_mistake_book_items_owner_select"
  on public.learner_mistake_book_items
  for select
  using (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_insert"
  on public.learner_mistake_book_items
  for insert
  with check (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_update"
  on public.learner_mistake_book_items
  for update
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_delete"
  on public.learner_mistake_book_items
  for delete
  using (auth.uid()::text = user_id);
