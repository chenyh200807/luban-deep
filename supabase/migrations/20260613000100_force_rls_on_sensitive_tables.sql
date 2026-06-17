-- Force RLS on the live-regression monitored sensitive tables.
--
-- The earlier hardening migrations enabled RLS and revoked anon/authenticated
-- grants, but the live gate also requires FORCE ROW LEVEL SECURITY so table
-- owners cannot accidentally bypass policies. This migration is intentionally
-- narrow and idempotent: it only asserts the force bit for the tables monitored
-- by scripts/ci/check_live_rls_regression.sh.

begin;

alter table public.user_profiles force row level security;
alter table public.user_stats force row level security;
alter table public.user_goals force row level security;
alter table public.user_logs force row level security;
alter table public.user_emotion_logs force row level security;
alter table public.user_badges force row level security;
alter table public.learner_mistake_book_items force row level security;
alter table public.questions_bank force row level security;
alter table public.mock_exams force row level security;
alter table public.wallets force row level security;

commit;
