begin;

alter table if exists public.assessment_sessions
  drop constraint if exists assessment_sessions_user_id_fkey;

comment on column public.assessment_sessions.user_id is
  'Canonical learner/member identifier from the authenticated session owner. Not foreign-keyed because mobile/member ids are not guaranteed to be mirrored in public.users before assessment start.';

commit;
