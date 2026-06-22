-- Harden ops-maintained canonical knowledge projection tables.
--
-- Root cause: scripts/export_canonical_knowledge_to_supabase.py creates public
-- projection tables outside normal migrations. The static RLS-on-create gate
-- did not see them, so live production had RLS off and anon/authenticated DML
-- grants on three canonical projection tables. These tables are maintained by
-- ops scripts through direct Postgres only; students must not read or mutate
-- them through Supabase Data API roles.

alter table if exists public.luban_canonical_taxonomy enable row level security;
alter table if exists public.luban_canonical_knowledge_catalog enable row level security;
alter table if exists public.luban_canonical_knowledge_edges enable row level security;

alter table if exists public.luban_canonical_taxonomy force row level security;
alter table if exists public.luban_canonical_knowledge_catalog force row level security;
alter table if exists public.luban_canonical_knowledge_edges force row level security;

revoke all on table public.luban_canonical_taxonomy from anon, authenticated;
revoke all on table public.luban_canonical_knowledge_catalog from anon, authenticated;
revoke all on table public.luban_canonical_knowledge_edges from anon, authenticated;

comment on table public.luban_canonical_taxonomy is
  'Ops-maintained canonical taxonomy projection. RLS service-role-only; anon/authenticated revoked.';
comment on table public.luban_canonical_knowledge_catalog is
  'Ops-maintained canonical knowledge coverage projection. RLS service-role-only; anon/authenticated revoked.';
comment on table public.luban_canonical_knowledge_edges is
  'Ops-maintained canonical knowledge graph projection. RLS service-role-only; anon/authenticated revoked.';
