begin;

alter table if exists public.assessment_sessions
  drop constraint if exists assessment_sessions_user_id_fkey;

commit;
