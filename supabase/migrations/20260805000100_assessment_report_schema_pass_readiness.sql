-- Pass-readiness diagnostic (docs/plan/测评题库与考试模块/2026-08-04-luban-pass-readiness-acquisition-diagnostic-plan.md §11 Phase 2):
-- admit the new report envelope schema version `pass-readiness-v1` in the
-- assessment_sessions report CHECK constraint. The legacy `p0a-v1` version stays
-- admitted unchanged — this migration only widens the allow-list; it creates no
-- new table and rewrites no historical rows.

begin;

alter table public.assessment_sessions
  drop constraint if exists chk_assessment_sessions_report_schema;

alter table public.assessment_sessions
  add constraint chk_assessment_sessions_report_schema
  check (
    result_report_json is null
    or result_report_json->>'schema_version' in ('p0a-v1', 'pass-readiness-v1')
  );

commit;
