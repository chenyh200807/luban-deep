create table if not exists public.invite_test_applications (
  id uuid primary key,
  created_at timestamptz not null default now(),
  source_page text not null default '',
  utm_source text not null default '',
  utm_campaign text not null default '',
  name text not null,
  phone text not null,
  email text not null,
  wechat_id text not null default '',
  exam_type text not null,
  exam_stage text not null,
  pain_point text not null,
  weekly_time text not null,
  current_method text not null default '',
  latest_wrong_question text not null default '',
  is_yousen_member text not null default '',
  exam_date text not null default '',
  accept_interview boolean not null default false,
  consent boolean not null default true check (consent is true),
  status text not null default 'submitted',
  operator_note text not null default '',
  submit_count integer not null default 1,
  raw_payload jsonb not null default '{}'::jsonb
);

alter table public.invite_test_applications enable row level security;

create index if not exists idx_invite_test_applications_phone
  on public.invite_test_applications (phone);

create index if not exists idx_invite_test_applications_email
  on public.invite_test_applications (email);

create index if not exists idx_invite_test_applications_created_at
  on public.invite_test_applications (created_at desc);

create index if not exists idx_invite_test_applications_status
  on public.invite_test_applications (status);
