begin;

create table if not exists public.assessment_forms (
  form_id text primary key,
  blueprint_version text not null,
  form_index integer not null,
  status text not null default 'active',
  question_bank_size integer not null default 0,
  fallback_used boolean not null default false,
  items_json jsonb not null,
  quality_json jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uniq_assessment_forms_version_index unique (blueprint_version, form_index),
  constraint chk_assessment_forms_status check (status in ('active', 'draft', 'retired')),
  constraint chk_assessment_forms_form_index check (form_index between 1 and 20),
  constraint chk_assessment_forms_items_json check (jsonb_typeof(items_json) = 'array')
);

comment on table public.assessment_forms is
  'Prebuilt diagnostic assessment forms. User requests randomly receive one active form instead of building a paper on the request path.';

create index if not exists idx_assessment_forms_active
  on public.assessment_forms(blueprint_version, status, form_index);

commit;
