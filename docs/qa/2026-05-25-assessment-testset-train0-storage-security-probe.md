# Assessment TestSet Train 0 Storage Security Probe

Date: 2026-05-25

Scope: read-only production storage/security probe for the Assessment TestSet
P0B/P1 production flywheel plan. No migration was applied, no data was written,
and no secret value is recorded in this document.

## Executive Finding

Train 0 currently fails closed on `assessment_forms` storage security.

The application-level create/resume payload redaction remains correct, but the
database table used for persisted assessment forms stores answer-bearing
`items_json` at rest. The table exists in the target database, contains persisted
forms, has RLS disabled, and grants broad privileges to `anon` and
`authenticated`.

Minimum classification: `PREVENTIVE_BLOCKER`.

Escalation condition: if a real client anon/publishable key can select
`public.assessment_forms.items_json` through PostgREST, the finding becomes
`ACTIVE_LEAK`.

## Local Code Evidence

`deeptutor/services/assessment/blueprint_service.py` persists
`assessment_forms.items_json` using `_form_unit_to_json(unit)`.

`_form_unit_to_json()` includes:

```python
"answer": item.answer
```

This is acceptable only if the table is strictly server-side/service-role only.

The migration file
`supabase/migrations/20260503000100_assessment_forms.sql` creates:

```sql
items_json jsonb not null
```

The migration does not enable RLS, does not revoke `anon` /
`authenticated`, and does not define a redacted public view.

## Read-Only Database Probe

Target database probe was executed using the configured server-side database URL.
The URL and credentials were not printed.

Observed table state:

```text
count|assessment_forms|rows=55|answer_rows=55
count|assessment_sessions|rows=8
```

Observed RLS state:

```text
rls|assessment_forms|enabled=false|forced=false
rls|assessment_sessions|enabled=true|forced=false
```

Observed grants include:

```text
grant|assessment_forms|anon|SELECT
grant|assessment_forms|authenticated|SELECT
grant|assessment_forms|anon|INSERT
grant|assessment_forms|authenticated|INSERT
grant|assessment_forms|anon|UPDATE
grant|assessment_forms|authenticated|UPDATE
grant|assessment_forms|anon|DELETE
grant|assessment_forms|authenticated|DELETE
```

`assessment_sessions` also has broad database grants to `anon` and
`authenticated`, but RLS is enabled there. Its policies still require a separate
policy review; the immediate answer-at-rest blocker is `assessment_forms`.

## PostgREST Probe

The available `.env` Supabase API key decodes as `service_role`, not anon.

Service-role PostgREST probe result:

```text
role=service_role
status=200
rows_returned=1
answer_visible=True
```

This is expected for service role and does not prove client/anon exposure. A
client-role probe is still required with a real anon/publishable key.

## Required Remediation Before Train 1

Review and apply a security migration before any P0B Train 1 persisted form-bank
work proceeds.

An existing untracked candidate already covers the immediate table:

```text
supabase/migrations/20260525120000_close_rls_off_business_tables.sql
```

The relevant fragment is:

```sql
begin;

alter table public.assessment_forms enable row level security;

revoke all on table public.assessment_forms from anon;
revoke all on table public.assessment_forms from authenticated;

commit;
```

If future client code needs public form metadata, create a separate redacted
view such as `public.assessment_forms_public` exposing only non-sensitive fields
(`form_id`, `blueprint_version`, `form_index`, `status`, `quality_json`,
timestamps). Never expose `items_json` to client roles.

## Verification Required After Remediation

1. Service role can still read/write persisted forms through the backend.
2. Anon/publishable-key PostgREST request for `assessment_forms.items_json`
   returns permission denied or no rows.
3. `/api/v1/assessment/create` still returns redacted client payload with no
   `answer`, `answer_key`, `correct_answer`, `grading_key`,
   `scoring_points`, `minimal_rationale`, or `option_reasoning`.
4. Existing persisted P0A forms remain replayable through backend service-role
   access.

## Current Decision

Do not proceed to P0B Train 1 form-bank persistence until this storage security
blocker is fixed or a real anon/publishable-key probe proves the table is not
reachable from client roles.
