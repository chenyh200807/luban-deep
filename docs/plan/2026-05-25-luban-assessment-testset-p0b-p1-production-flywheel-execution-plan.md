# Luban Assessment TestSet P0B/P1 Production Flywheel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for independent backend/frontend/QA tracks, or `superpowers:executing-plans` for inline implementation. Execute task-by-task with checkbox tracking. Do not expand P0A scope while implementing this plan.

**Goal:** Turn the P0A TestSet foundation into a production-grade multi-topic assessment and learning flywheel: topic catalog, 3/5 form-bank gate, persisted `assessment_forms`, personalized recommendation, real-exam mini simulation, wrong-item training loop, and deep explanation as a bounded P1 feature.

**Architecture:** P0A remains the durable assessment foundation: create/submit/report/writeback/session authority stays in `deeptutor/services/assessment/*`, `MemberConsoleService` remains a thin coordinator, and mobile routes stay thin API adapters. This plan adds production read models and bounded P0B/P1 capabilities without creating a second mastery, study-plan, or question lifecycle authority.

**Tech Stack:** Python/FastAPI/Pydantic, Supabase Postgres + RLS, existing `assessment_forms` / `assessment_sessions`, `learning_evidence`, `learner_mistake_book_items`, `yousenwebview/packageDeeptutor`, pytest, Node view-model tests, WeChat DevTools manual gate, Aliyun production smoke.

---

## 0.0 Revision Log

### v1.5 Train 0 Read-Only Storage Probe Evidence - 2026-05-25

Train 0 read-only database probing confirmed that `public.assessment_forms` is not
only a theoretical risk:

- `assessment_forms` exists in the target database with 55 rows.
- 55 / 55 rows contain answer-bearing `items_json`.
- RLS is disabled on `assessment_forms`.
- Database grants include broad `anon` / `authenticated` privileges, including
  `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
- `assessment_sessions` also exists with 8 rows and RLS enabled. Its broad
  `anon` / `authenticated` grants still deserve policy review, but it is not the
  immediate answer-at-rest blocker.
- The only Supabase API key available in local `.env` decodes as
  `service_role`; therefore a true client-role PostgREST probe still requires a
  real anon/publishable key.

Evidence is recorded in
`docs/qa/2026-05-25-assessment-testset-train0-storage-security-probe.md`.

Current classification is at least `PREVENTIVE_BLOCKER`; it escalates to
`ACTIVE_LEAK` if a real anon/publishable key can select
`assessment_forms.items_json` through PostgREST.

An existing untracked candidate migration,
`supabase/migrations/20260525120000_close_rls_off_business_tables.sql`, includes
the required `assessment_forms` RLS enablement and `anon` / `authenticated`
revokes. Review and apply that migration under the normal Supabase release
procedure rather than creating a duplicate migration.

### v1.4 Confirmed Assessment Forms Answer-At-Rest Finding - 2026-05-25

This revision upgrades Gate 0 from "investigate possible leak" to "confirmed answer-at-rest in base table; production exposure unknown". Code inspection proves:

- API create/resume redaction is correct: client payload is built without `answer`, while server-side stored artifacts keep the answer.
- Persisted `assessment_forms.items_json` stores cleartext `answer` through `deeptutor/services/assessment/blueprint_service.py::_form_unit_to_json`.
- `supabase/migrations/20260503000100_assessment_forms.sql` creates `public.assessment_forms` without RLS, policies, or privilege revocation.

Therefore, the vulnerable condition is precise: if `assessment_forms` has been applied and is reachable to `anon` or `authenticated` through Supabase Data API/PostgREST, clients can bypass application-layer redaction and read answers directly. Train 0 must classify this as either `ACTIVE_LEAK` (table exists, has data, and client role can read `items_json.answer`) or `PREVENTIVE_BLOCKER` (table missing/empty/not used yet, but unsafe before any real forms are persisted).

### v1.3 Reality-Verified Hardening - 2026-05-25

Independent code-fact review found one structural false premise and several drift risks. Changes:

1. **CRITICAL — remove migration-apply assumptions.** §0 previously claimed the P0A `assessment_sessions` migration was "applied after explicit approval" without target-database evidence. Later Train 0 probing must be treated as the authority for apply-state. As of the 2026-05-25 read-only probe, `assessment_sessions` exists with RLS enabled; future trains still must verify the target environment they are about to use.
2. **Endpoint prefix corrected to code truth.** Real routes are `/api/v1/assessment/{topics,create,{quiz_id}/submit}` (mobile router mounted at `prefix="/api/v1"`). The `/api/v1/mobile/assessment/*` form used in earlier docs and in this plan's smoke section was wrong. All endpoint references now use the verified prefix; if any doc disagrees with code, code wins (§0.1 rule 4).
3. **Train 0 gains an apply-state gate** for both `assessment_sessions` and `assessment_forms`: a Train cannot start if a table it writes/reads does not exist in the target DB.
4. **Answer-leak audit gains a severity split**: active-leak (P0A already serving persisted forms client-readable) is an emergency stop; preventive (forms not yet enabled) is a normal migration.
5. **wrong-item "3 同类题" generator authority pinned**: questions must come from `questions_bank` by `knowledge_point`/`error_code` (reuse the single question authority) — LLM-generated items may only be labelled `practice` and never enter formal score.
6. **Workspace git instability recorded**: this conductor workspace re-freezes `.git` to `.git.disabled`; all git ops must use explicit `GIT_DIR`/`GIT_WORK_TREE`, and formal push/PR should happen on a stable clone, not here.
7. Added 10-topic catalog id/label table, `semantic_signature` cross-form dedupe, form difficulty-comparability note, `schema_version` bump rule, retired-form replay continuity, and deep-explanation per-user cost cap.

### v1.2 Authority Linkage Fix - 2026-05-25

This revision adds the missing explicit source-of-truth map. This plan extends the Assessment TestSet PRD and the P0A execution plan; it does not replace either document. Future agents must read the PRD and P0A plan before executing this P0B/P1 plan.

### v1.1 Hardening Review - 2026-05-25

This revision tightens the first draft after a fresh PRD/code reality review. The important changes are:

1. Add an `assessment_forms` security gate because current persisted `items_json` stores `answer`; production must prove the table is not client-readable or introduce a server-only storage/redacted-view split before broad release.
2. Split execution into release trains: P0B catalog/form-bank/flywheel first, P1 deep explanation second. P1 must not block P0B pilot.
3. Use the existing `scripts/seed_assessment_topic_catalog_forms.py` as the topic form-bank script surface; do not create a parallel auditor unless the existing script cannot be safely extended.
4. Add explicit old 20-question `diagnostic_v1` continuity checks so comprehensive diagnostic, topic TestSet, and P0B real-exam mini simulation do not overwrite each other.
5. Add source/copyright authority chain for real-exam copy. `REAL_EXAM` provenance alone is not enough to say "官方真题".
6. Add form lifecycle rules: active/draft/retired, replacement, stale standard handling, and form version comparability.
7. Add DevTools failure classification so a 500 create failure, free-form training card, and report writeback miss lead to different fixes.
8. Add authoring backlog contract with owner/date/counts; topics below 3 forms cannot be "temporarily enabled" to satisfy product pressure.

## 0.1 Source Of Truth And Required Reading

This plan is the **next execution layer** for Assessment TestSet after P0A. It is not a standalone PRD.

Read in this order before implementation:

1. [docs/plan/2026-05-24-luban-assessment-testset-module-prd.md](2026-05-24-luban-assessment-testset-module-prd.md)
   - Product authority for assessment types, feedback timing, score interpretation, non-goals, quality gates, and phase boundaries.
   - Defines P0A / P0B / P1 / P2 meaning. This plan cannot redefine those phases.
2. [docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md](2026-05-24-luban-assessment-testset-p0a-execution-plan.md)
   - Engineering authority for durable sessions, deferred feedback, payload redaction, `learning_evidence` writeback, topic catalog seed, and P0A/P0A+ gates.
   - P0B/P1 work must reuse its canonical chain and must not create a second session, scoring, writeback, or recommendation authority.
3. [docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md](../qa/2026-05-24-assessment-testset-p0a-reality-check.md)
   - Reality-check evidence for Phase -1 / Phase 0 decisions, coverage audit, migration approval, and unresolved manual gates.
4. [docs/qa/2026-05-25-assessment-testset-p0a-phase1-dry-run.md](../qa/2026-05-25-assessment-testset-p0a-phase1-dry-run.md)
   - Automated gate evidence and remaining P0A release gaps.
5. [docs/qa/2026-05-25-assessment-testset-flywheel-hardening-qa.md](../qa/2026-05-25-assessment-testset-flywheel-hardening-qa.md)
   - Evidence for result CTA, wrong-item practice, `training_completed`, and the unresolved full DevTools flywheel run.
6. [docs/qa/2026-05-25-assessment-testset-train0-storage-security-probe.md](../qa/2026-05-25-assessment-testset-train0-storage-security-probe.md)
   - Train 0 read-only storage/security evidence for `assessment_forms` RLS, grants, answer-at-rest rows, and the remaining anon-key probe.

Conflict resolution:

| If documents disagree | Winner | Reason |
| --- | --- | --- |
| Product scope, phase boundary, user promise, score interpretation | Assessment TestSet PRD | PRD is the product contract |
| P0A durable session / redaction / writeback / migration gates | P0A execution plan + QA evidence | P0A is already the foundation implementation path |
| P0B/P1 task sequencing after P0A | This plan | This plan is the downstream execution plan |
| Runtime code fact contradicts any document | Code fact + new QA reality check | Do not implement against stale assumptions |
| User explicitly approves a migration/apply/release decision | Milestone QA report must record it | Keeps production-risk decisions auditable |

No implementation task in this plan may bypass the P0A chain:

```text
questions_bank / assessment_forms
  -> assessment_sessions
  -> deterministic scoring
  -> learning_evidence + mistake_book
  -> learning_report_read_model / session-local next action
  -> study_plan consumes evidence later
```

Forbidden shortcuts:

- Directly write `training_intent` from assessment submit.
- Let frontend hard-code topic availability instead of reading catalog.
- Let LLM explanation alter score or mastery.
- Let P0B real-exam copy override PRD copyright/source-policy rules.
- Treat old `last_assessment.score` as long-term mastery.

## 0. Context And Boundary

### Current P0A Status

P0A is the first shippable slice, not the whole assessment product.

Completed or implemented:

- `topic_diagnostic` create / submit / report path.
- Supabase durable `assessment_sessions` exists in the probed target database with 8 rows and RLS enabled. Treat the 2026-05-25 Train 0 probe as the current apply-state evidence, and re-run it for any different target environment before relying on durable sessions.
- Train 0 read-only storage probe confirms `assessment_forms` exists with answer-bearing rows and RLS disabled. Treat P0B Train 1 as blocked until this is remediated or a real anon-key probe proves `NOT_EXPOSED`.
- Deferred feedback and pre-submit payload redaction gates.
- Per-item `learning_evidence`, attempt refs, mistake-book writeback, and result report.
- Yousen assessment run/result view-model gates.
- P0A+ code surface for topic catalog and recommendation endpoint.
- First flywheel hardening: result CTA routes toward report training area, wrong-item cards carry practice context, training-completed evidence can project a retest prompt.

Not complete enough for broad product release:

- WeChat DevTools clean manual run has not fully proven `assessment result -> wrong item practice -> 3 submit-able training questions -> learning_evidence -> report retest recommendation`.
- The 10-topic catalog must be audited against real Supabase persisted form banks, not only local tests.
- P0B real-exam mini simulation is not P0A and needs its own source/copyright/form comparability gates.
- P1 detailed explanation is intentionally absent from P0A and needs cost/cache/score-invariance gates.
- Teacher authoring, QTI, adaptive assessment, full subjective case scoring, and item analytics are still P2+.

### Hard Boundary

This plan does **not** implement:

- CAT / IRT adaptive assessment.
- Teacher-facing authoring or review UI.
- QTI import/export.
- LLM-generated items entering formal forms without validation.
- Full subjective case scoring.
- New chat WebSocket routes.
- A second `training_intent`, `study_plan`, or mastery authority.
- Any migration apply without explicit user approval.

### Single Authority

| Business fact | Canonical authority | Forbidden competing authority |
| --- | --- | --- |
| Which topics are open for formal assessment | `assessment_forms` persisted form bank + topic catalog validator | Frontend hard-coded topic buttons |
| Which TestSet is recommended now | Assessment recommendation read model beside catalog | Mutating `training_intent` from assessment create |
| Current long-term study prescription | Existing `study_plan` / `training_intent` authority | Assessment result page directly rewriting plan |
| Per-item learning fact | `learning_evidence` writeback | `last_assessment` aggregate score as mastery |
| Form score | Deterministic scorer over hidden grading key | LLM explanation or chat output |
| Detailed explanation | P1 explanation cache keyed by submitted result | Pre-submit generation or score mutation |

### Release Principle

P0A is now a baseline. The next release should be called **P0B/P1 Production Flywheel**, not "P0A continued". This avoids silent scope creep and keeps gates honest.

### Release Trains

This document intentionally covers P0B and P1, but implementation order is locked:

| Train | Ships | Must not include | Exit verdict |
| --- | --- | --- | --- |
| Train 0: Reality/security lock | Git authority, schema audit, answer-leak audit, current deployed commit check | Feature changes | `READY_TO_IMPLEMENT` or `BLOCKED_BY_SECURITY` |
| Train 1: Topic catalog productionization | 10-topic catalog, 3/5 form-bank gate, persisted forms, authoring backlog | Deep explanation, adaptive, real-exam score claim | `READY_WITH_AUTHORING_BACKLOG` or `BLOCKED_BY_FORM_BANK` |
| Train 2: Learning flywheel | Result CTA, wrong-item 3-question practice, training_completed evidence, retest recommendation | Free-form chat counted as structured training | `READY_FOR_PILOT` or `BLOCKED_BY_WRITEBACK` |
| Train 3: P0B real-exam mini | 20-question real-exam-style mini simulation with safe copy | Full mock exam, strict timer, official score scale | `READY_FOR_P0B_PILOT` or `BLOCKED_BY_SOURCE_POLICY` |
| Train 4: P1 deep explanation | Post-submit explanation cache and attempt detail | Any score/mastery mutation | `READY_FOR_P1_PILOT` or `BLOCKED_BY_COST_OR_CACHE` |

Train 4 is optional for the next learner-facing pilot. Do not delay Train 1/2/3 because P1 explanation is not ready.

---

## 1. File Map

### Backend Assessment Core

- Modify: `deeptutor/services/assessment/blueprint.py`
  - Add or harden `real_exam_simulation_mini_v1` blueprint.
  - Keep `diagnostic_v1` and topic blueprints backward-compatible.
- Modify: `deeptutor/services/assessment/blueprint_service.py`
  - Use persisted forms first for enabled topics and P0B mini simulation.
  - Keep cold dynamic assembly behind explicit dry-run / dev fallback flags only.
- Modify: `deeptutor/services/assessment/topic_catalog.py`
  - Own topic definitions, status rules, validator result shape, and recommendation read model.
- Modify: `deeptutor/services/assessment/report_read_model.py`
  - Add stable fields needed by report training area and P1 attempt detail links.
- Modify: `deeptutor/services/assessment/writeback.py`
  - Ensure wrong-item practice and training-completed evidence are structured and queryable.
- Modify: `deeptutor/services/member_console/service.py`
  - Thin coordination only: call assessment services, do not add scoring/recommendation policy here.
- Modify: `deeptutor/api/routers/mobile.py`
  - Keep mobile endpoints thin; add only stable request/response contracts if needed.

### Scripts And Data Gates

- Modify: `scripts/seed_assessment_topic_catalog_forms.py`
  - Dry-run all required topics against live Supabase and persisted `assessment_forms`.
  - Add `--out-md` and `--out-json` so the exact reviewed candidate/form-bank result becomes QA evidence.
  - Idempotently persist reviewed forms after dry-run and target DB guard.
  - Do not create a second topic-audit script unless this existing script cannot be safely extended without scope creep.
- Create: `scripts/smoke_assessment_flywheel.py`
  - Authenticated production-like smoke for create/submit/report/recommendation where credentials are available.

### Supabase Schema / Migration

- Review: `supabase/migrations/20260503000100_assessment_forms.sql`
  - Current table stores `items_json`; current service serialization includes `answer`.
  - Before broad release, prove `assessment_forms` is service-role-only or add a redacted public projection.
- Create only if required after schema audit: `supabase/migrations/<timestamp>_assessment_forms_security_or_metadata.sql`
  - Allowed changes: RLS/privilege hardening, metadata columns needed for lifecycle/comparability, or redacted view.
  - Not allowed without explicit approval: destructive rewrite of existing active forms.

### Frontend

- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
  - Show topic catalog, recommended entry, disabled authoring-needed topics, P0B mini simulation entry.
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
  - Keep first screen as usable assessment catalog, not marketing copy.
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`
  - Add compact catalog/status/recommendation styles.
- Modify: `yousenwebview/packageDeeptutor/pages/chat/chat.js`
  - Only if wrong-item training must carry stricter structured submit contract.
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.js`
  - Only if report training area needs a stable anchor for assessment retest prompts.

### Tests

- Modify: `tests/services/assessment/test_topic_catalog.py`
- Modify: `tests/services/assessment/test_blueprint_coverage.py`
- Modify: `tests/services/assessment/test_testset_assembly.py`
- Modify: `tests/services/assessment/test_writeback.py`
- Modify: `tests/api/test_mobile_assessment_payload_redaction.py`
- Modify: `tests/api/test_mobile_router.py`
- Modify: `tests/services/learner_state/test_learning_report_read_model.py`
- Modify: `tests/services/learner_state/test_conversation_learning_evidence_event.py`
- Modify: `yousenwebview/tests/test_assessment_testset_view_model.js`
- Modify: `yousenwebview/tests/test_package_assessment_contract.js`

### QA And Plan Docs

- Create: `docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md`
- Create: `docs/qa/2026-05-25-assessment-testset-p0b-p1-flywheel-dry-run.md`
- Modify: `docs/plan/INDEX.md`

---

## 2. Phase Gates

### Gate 0: Assessment Forms Security And Schema Reality

This gate runs before topic catalog persistence. It exists because current `assessment_forms.items_json` **does contain** hidden answer data when forms are persisted. Application-layer redaction is correct, but database-layer exposure would bypass it.

Confirmed code facts:

- `deeptutor/services/assessment/blueprint_service.py::_build_scored_question` splits client and stored artifacts; client payload omits `answer`.
- `deeptutor/services/assessment/blueprint_service.py::_form_unit_to_json` writes `"answer": item.answer` into persisted `items_json`.
- `supabase/migrations/20260503000100_assessment_forms.sql` creates `public.assessment_forms` without `enable row level security`, policies, or `revoke` statements.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
rg -n "\"answer\"|correct_answer|answer_key|grading_key|scoring_points|option_reasoning" \
  deeptutor/services/assessment/blueprint_service.py \
  supabase/migrations/20260503000100_assessment_forms.sql \
  tests/services/assessment \
  tests/api/test_mobile_assessment_payload_redaction.py
```

Then run a database privilege probe against the target environment:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py --dry-run --json
```

Required evidence in QA:

- Whether `assessment_forms.items_json` stores hidden answer data.
- Whether anon/authenticated clients can read `assessment_forms` directly through PostgREST.
- Whether mobile create/resume payload is redacted even when forms are loaded from persisted rows.
- Whether the finding is `ACTIVE_LEAK`, `PREVENTIVE_BLOCKER`, or `NOT_EXPOSED`.
- Whether a migration is required to make `assessment_forms` service-role-only, add RLS, or create a redacted public view.

Severity classification:

| Classification | Condition | Action |
| --- | --- | --- |
| `ACTIVE_LEAK` | `assessment_forms` exists, contains real answer-bearing rows, and `anon`/`authenticated` can select `items_json` | Emergency stop; immediately revoke/enable RLS before any new feature work |
| `PREVENTIVE_BLOCKER` | Table is missing, empty, or not used by production, but migration lacks RLS | Add security migration before persisting real forms |
| `NOT_EXPOSED` | Table is service-only or Data API cannot read it, verified with client-role probe | Record evidence; still prefer RLS defense-in-depth |

Stop if:

- Client role can read `items_json.answer`.
- Any pre-submit mobile payload contains `answer`, `answer_key`, `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, `rubric`, `official_answer`, or `option_reasoning`.
- A schema migration is needed but has not been reviewed and explicitly approved.

Minimum security migration draft:

```sql
begin;

alter table public.assessment_forms enable row level security;

revoke all on table public.assessment_forms from anon;
revoke all on table public.assessment_forms from authenticated;

-- Intentionally create no anon/authenticated policies.
-- Server code must access this table through the service role.

commit;
```

Verification after apply:

```sql
-- anon/authenticated role probe must fail or return no data:
select items_json from public.assessment_forms limit 1;

-- service role/server path must still load persisted forms:
select form_id, blueprint_version, form_index, status
from public.assessment_forms
where status = 'active'
limit 1;
```

Optional future path:

If a client ever needs public form metadata, create `public.assessment_forms_public` as a redacted view that exposes only non-secret fields such as `form_id`, `blueprint_version`, `status`, `form_index`, and `quality_json`. Do not expose `items_json`. On Postgres 15+, use `security_invoker = true` for views that should obey underlying RLS; otherwise protect the view with explicit privileges and keep the base table denied.

### Gate A: Reality Lock

Before coding, record:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
GIT_DIR=/Users/yehongchen/.gitdirs/deeptutor-documents.git \
GIT_WORK_TREE=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor \
git status --short --branch
```

**Workspace git is unstable.** This conductor workspace re-freezes `.git` into `.git.disabled` without warning (observed multiple times). Therefore:

- Every git command in this plan MUST use explicit `GIT_DIR=/Users/yehongchen/.gitdirs/deeptutor-documents.git GIT_WORK_TREE=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor`. A bare `git` may resolve to a different worktree or fail with `not a git repository`.
- Do NOT treat this workspace as the formal push/PR surface. Code edits here are fine; formal `push`/PR should happen on a stable clone or through the conductor task's own branch flow, recorded in QA.
- If `.git` is missing but `.git.disabled` exists, the pointer can be restored with `echo 'gitdir: /Users/yehongchen/.gitdirs/deeptutor-documents.git' > .git` — but expect it to re-freeze.

Required evidence:

- Current branch.
- Current dirty files grouped into assessment-related and unrelated.
- Production candidate commit currently deployed, if known.
- Whether `origin/main` already contains the P0A/P0A+ commits.

Stop if:

- Git toplevel is not the intended DeepTutor directory.
- The planned diff would touch unrelated dirty files such as BI, report layout, or long-dialog scripts.

### Gate A.5: Production Storage Apply-State (blocks every table-dependent Train)

P0B assumes durable Supabase tables. Verify they actually exist in the target DB before any Train that reads/writes them.

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
# read-only existence probe against the target DB (use the same psql helper / target-db guard as source compiler)
psql -X -v ON_ERROR_STOP=1 "$DB_URL" -c "select to_regclass('public.assessment_sessions'), to_regclass('public.assessment_forms');"
```

Also confirm what storage P0A `create_assessment`/`submit_assessment` actually read/write **right now**:

```bash
rg -n "_data_path|assessment_sessions|assessment_forms|supabase|member_console" \
  deeptutor/services/assessment/session_repository.py \
  deeptutor/services/member_console/service.py
```

Required evidence in QA:

- `assessment_sessions` exists in target DB? (yes/no)
- `assessment_forms` exists in target DB? (yes/no)
- P0A current production storage path: durable Supabase table OR member-console JSON file.

Stop if:

- A Train depends on a table that returns `NULL` from `to_regclass` (table not applied). Apply the P0A migration first, with explicit user approval, before that Train starts.
- P0A is still on member-console JSON file — then P0A is not production-durable yet and P0B's "production flywheel" premise is invalid until the P0A migration is applied.

### Gate B: Topic Catalog Truth

Run dry-run before any persist:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py \
  --dry-run \
  --json \
  --out-json artifacts/assessment/topic-catalog-form-bank-20260525.json \
  --out-md docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

Expected output shape:

```text
topic=waterproof status=stable active_forms=5 delivered_count=12
topic=decoration status=pilot active_forms=3 delivered_count=12
topic=<name> status=authoring_needed active_forms=<0-2> delivered_count=12
out=docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

Stop if:

- Any topic is marked `stable` without validator proof of 5 active forms, 12 items per form, section floor, and cross-form dedupe.
- `authoring_needed` topics are enabled in mobile payload.
- Script attempts to persist before dry-run review.

### Gate C: Persisted Form Bank

Persist only after Gate B review:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py \
  --persist \
  --require-target-main \
  --reviewed-json artifacts/assessment/topic-catalog-form-bank-20260525.json \
  --idempotency-key assessment-topic-catalog-20260525 \
  --out-md docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md
```

Expected:

```text
target_database=deeptutor_main verified=true
persisted_forms=<number>
skipped_existing_forms=<number>
authoring_needed_topics=<comma-separated ids>
```

Stop if:

- Target DB guard cannot prove DeepTutor main.
- Persisted forms use duplicate `source_question_id` across forms for the same topic.
- Form payload contains `answer_key`, `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, or `option_reasoning` in client-visible columns.

### Gate C.5: Form Lifecycle And Drift

Every persisted form must have a lifecycle decision:

| State | Meaning | User-visible? | Can be selected for create? |
| --- | --- | --- | --- |
| `draft` | Built but not reviewed | No | No |
| `active` | Reviewed and eligible | Yes, through catalog | Yes |
| `retired` | Replaced due to source drift, duplication, or quality issue | No | No |

Required rules:

- Do not overwrite an active form in place if item composition changes; create a new `form_id` or increment form metadata and retire the old form.
- A topic can be `stable` only if at least 5 active forms share the same blueprint semantics and pass validator.
- If source standard or taxonomy changes invalidate a form, retire it and recompute catalog status.
- Pilot and stable status must be recomputed after every seed/persist run; never cache topic status in frontend code.
- **Retired-form replay continuity (inherit P0A v1.1):** a session created from a now-retired form must still replay its result report from the stored session snapshot (`result_report_json` + `session_questions_private`), never by re-assembling from the current bank. Retiring a form affects only new `create`, never historical session replay.
- **Form difficulty comparability:** before claiming `stable`, record per-form a difficulty proxy (historical correct-rate of its `source_question_id` set, or section-weighted item difficulty if available). If the 5 forms' difficulty proxy spread exceeds an agreed band, do NOT claim cross-form score comparability — user copy says "同专题不同卷" and full difficulty balancing is deferred to P2 item analytics. Do not silently present non-equivalent forms as an equal-difficulty score.
- **`schema_version` bump:** if P0B adds fields to `result_report_json` beyond P0A `"p0a-v1"`, write `"p0b-v1"` and make the report read model dispatch on version. Never let a P0B reader mis-render a P0A `"p0a-v1"` report or vice versa.

### Gate D: Flywheel Manual Gate

WeChat DevTools manual path:

1. Open DevTools project root `yousenwebview`.
2. Enter `packageDeeptutor/pages/assessment/assessment`.
3. Confirm catalog shows recommended entry plus topic list.
4. Start an enabled topic TestSet.
5. Submit with at least one wrong answer.
6. On result page, confirm CTA goes to report training area, not chat.
7. Tap `练 3 道同类题`.
8. Confirm 3 submit-able MCQs are generated or routed through deterministic training generator.
9. Submit training questions.
10. Reopen report training area and confirm retest recommendation appears.

Record evidence in:

```text
docs/qa/2026-05-25-assessment-testset-p0b-p1-flywheel-dry-run.md
```

Stop if:

- Wrong-item practice produces only free-form review text and no submit-able training card.
- Report cannot show retest recommendation after `training_completed`.
- Result page still routes primary CTA to chat.

### Gate D.5: DevTools Failure Classification

When DevTools fails, classify before patching:

| Failure | Likely broken authority | Fix direction |
| --- | --- | --- |
| `POST /api/v1/assessment/create` 500 | Backend create/form-bank/session | Inspect server log and API response; do not patch UI copy |
| Topic visible but click disabled unexpectedly | Catalog status/read-model | Validate `assessment_forms` count and form-bank validator |
| Result CTA goes to chat | Assessment result template | Fix WXML/view-model contract |
| Wrong-item practice shows free-form explanation only | Training generator/card contract | Route to deterministic structured practice or enforce structured chat card |
| Training submits but report has no retest prompt | `learning_evidence` writeback/read-model | Fix evidence payload or report projection |
| Deep explanation changes score/copy implies mastery | P1 explanation authority violation | Stop; explanation must be projection-only |

Record one classification row in the QA doc for every failed DevTools run.

### Gate E: Old 20-Question Diagnostic Continuity

The old comprehensive diagnostic remains a product entry. P0B must not overwrite it.

Required checks:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_blueprint_coverage.py::test_diagnostic_v1_has_20_units_with_16_scored_and_4_profile -q
```

Add or keep tests proving:

- `diagnostic_v1` remains 20 units.
- `topic_*_v1` remains 12 scored topic questions.
- `real_exam_simulation_mini_v1` is a separate 20-question blueprint.
- The frontend can show both "综合摸底" and "专题测评目录" without treating one as the other.

Stop if:

- The P0B mini simulation reuses `diagnostic_v1` names or mutates old diagnostic semantics.
- The recommendation model sends evidence-insufficient learners directly to a topic instead of `diagnostic_v1`.

---

## 3. Implementation Tasks

### Task 0: Assessment Forms Security And Schema Reality Audit

**Files:**

- Review: `supabase/migrations/20260503000100_assessment_forms.sql`
- Review: `deeptutor/services/assessment/blueprint_service.py`
- Modify if needed: `supabase/migrations/<timestamp>_assessment_forms_security_or_metadata.sql`
- Test: `tests/api/test_mobile_assessment_payload_redaction.py`
- Test: `tests/services/assessment/test_blueprint_coverage.py`

- [ ] **Step 1: Confirm persisted form payload contains hidden answers**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
rg -n "\"answer\"|correct_answer|answer_key|grading_key|scoring_points|option_reasoning" \
  deeptutor/services/assessment/blueprint_service.py \
  supabase/migrations/20260503000100_assessment_forms.sql
```

Expected: QA records whether `items_json` includes `answer` and whether that data is server-only.

- [ ] **Step 2: Write or extend a redaction regression test**

Add a test that creates an assessment from a persisted form row containing `answer` and asserts the pre-submit API response contains no forbidden key:

```python
def test_persisted_form_answers_are_not_serialized_pre_submit(client, monkeypatch):
    response = client.post(
        "/api/v1/assessment/create",
        json={"assessment_type": "topic_diagnostic", "topic_ids": ["waterproof"]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    payload_text = json.dumps(response.json(), ensure_ascii=False)
    for forbidden in ("answer", "answer_key", "correct_answer", "grading_key", "scoring_points", "option_reasoning"):
        assert forbidden not in payload_text
```

- [ ] **Step 3: Probe Supabase table exposure**

Use the target environment's safe read credentials. Do not paste keys into the QA doc.

Record whether anon/authenticated roles can read:

```sql
select items_json from public.assessment_forms limit 1;
```

Expected:

- Service role can read.
- Mobile client roles cannot directly read hidden answer payload.

- [ ] **Step 4: Decide whether a migration is required**

Migration is required unless Train 0 proves `NOT_EXPOSED` with a client-role probe and documents the evidence. If client roles can read hidden answers, stop and draft/apply an emergency migration after explicit user approval.

Acceptable fixes:

1. Enable RLS and service-only policies for `assessment_forms`.
2. Move hidden answers to server-only artifact storage.
3. Create a redacted public view and make all client-facing code read only that view.

Do not apply migration without explicit user approval.

- [ ] **Step 5: Add migration review packet**

Add this section to the QA report before asking for apply approval:

```markdown
## Assessment Forms RLS Review Packet

Classification: ACTIVE_LEAK | PREVENTIVE_BLOCKER | NOT_EXPOSED

Code fact:
- application create/resume payload redacts answers
- assessment_forms.items_json stores answer at rest
- existing migration lacks RLS/revoke

Proposed SQL:
<paste reviewed migration SQL>

Verification plan:
- anon/authenticated select items_json fails
- service role load persisted form succeeds
- mobile create/submit/report still pass
```

### Task 1: Reality Lock And Current-State Report

**Files:**

- Create: `docs/qa/2026-05-25-assessment-testset-p0b-p1-flywheel-dry-run.md`

- [ ] **Step 1: Capture git and deployment authority**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
GIT_DIR=/Users/yehongchen/.gitdirs/deeptutor-documents.git \
GIT_WORK_TREE=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor \
git status --short --branch
```

Expected: output is pasted into the QA report under `## Reality Lock`.

- [ ] **Step 2: Capture current assessment surface**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
rg -n "assessment_topics|assessment/create|assessment/submit|get_assessment_topic_catalog|generate_and_persist_assessment_forms|assessment_wrong_item_practice|training_completed" \
  deeptutor/api/routers/mobile.py \
  deeptutor/services/member_console/service.py \
  deeptutor/services/assessment \
  deeptutor/services/learner_state \
  yousenwebview/packageDeeptutor/pages/assessment \
  yousenwebview/packageDeeptutor/pages/chat
```

Expected: QA report records the current owner for catalog, recommendation, create, submit, writeback, and frontend CTA.

- [ ] **Step 3: Write the report header**

Add this exact structure:

```markdown
# Assessment TestSet P0B/P1 Production Flywheel Dry Run

Date: 2026-05-25

## Reality Lock

## Topic Catalog Audit

## Persisted Form Bank

## Flywheel Manual Gate

## Automated Gates

## Deviations And Decisions

## Release Readiness Verdict
```

- [ ] **Step 4: Commit boundary**

Do not commit yet if the current worktree contains unrelated dirty files. Stage only after the user approves the final grouped commit plan.

### Task 2: Topic Catalog Auditor And Seed Script Hardening

**Files:**

- Modify: `scripts/seed_assessment_topic_catalog_forms.py`
- Test: `tests/services/assessment/test_topic_catalog.py`
- Test: `tests/api/test_mobile_assessment_payload_redaction.py`
- Test: `tests/scripts/test_assessment_topic_catalog_scripts.py`

- [ ] **Step 1: Write failing unit tests for catalog classification**

Add tests covering:

```python
def test_catalog_classifies_less_than_three_forms_as_authoring_needed():
    assert classify_topic_form_count(0) == "authoring_needed"
    assert classify_topic_form_count(2) == "authoring_needed"

def test_catalog_classifies_three_or_four_forms_as_pilot():
    assert classify_topic_form_count(3) == "pilot"
    assert classify_topic_form_count(4) == "pilot"

def test_catalog_classifies_five_forms_as_stable():
    assert classify_topic_form_count(5) == "stable"
```

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_topic_catalog.py -q
```

Expected: tests fail if classification or imports are missing.

- [ ] **Step 2: Add script contract test**

Add a script test that invokes:

```bash
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py --help
```

Expected: help text includes `--dry-run`, `--persist`, `--topic-id`, `--out-json`, `--out-md`, `--reviewed-json`, `--require-target-main`, and `--idempotency-key`.

- [ ] **Step 3: Implement dry-run auditor**

The script must:

- Require explicit topic list. The 10 P0B topics (id + Chinese label) must be defined in **one** authority — `deeptutor/services/assessment/topic_catalog.py` — and derived from existing blueprint/taxonomy, never hard-coded in frontend or invented in this plan. Task 2 Step 0 (do first): read `topic_catalog.py` and `blueprint.py`, list the actual 10 topic ids + labels into the audit QA doc; if fewer than 10 real topics exist, the catalog ships with the real count and the rest go to authoring backlog — do not pad to 10 with empty topics.
- Read form counts through the existing assessment provider or a mockable adapter.
- Validate every enabled topic with persisted form-bank validator.
- Write Markdown and JSON sidecar under `docs/qa/` or `artifacts/assessment/`.
- Never persist data.
- Use `subprocess.run(..., timeout=...)` for every subprocess call.
- On `--persist`, require `--reviewed-json`, `--require-target-main`, and `--idempotency-key`.
- On `--dry-run`, never call the write/upsert path.

Fail-fast messages:

```text
missing_required_topics
topic_catalog_validator_failed: <topic_id>
topic_enabled_without_valid_form_bank: <topic_id>
reviewed_json_required_for_persist
target_database_guard_required
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_topic_catalog.py tests/api/test_mobile_assessment_payload_redaction.py tests/scripts/test_assessment_topic_catalog_scripts.py -q
```

Expected: all tests pass.

### Task 3: Persisted Form Bank Seed Hardening

**Files:**

- Modify: `scripts/seed_assessment_topic_catalog_forms.py`
- Modify: `deeptutor/services/assessment/blueprint_service.py`
- Test: `tests/services/assessment/test_blueprint_coverage.py`
- Test: `tests/services/assessment/test_testset_assembly.py`
- Test: `tests/scripts/test_assessment_topic_catalog_scripts.py`

- [ ] **Step 1: Write failing idempotency test**

Add a test:

```python
def test_seed_forms_is_idempotent_for_same_blueprint_and_form_id(fake_provider):
    first = fake_provider.persist_form("topic_waterproof_v1_form_1", ["q1", "q2"])
    second = fake_provider.persist_form("topic_waterproof_v1_form_1", ["q1", "q2"])
    assert first["status"] == "created"
    assert second["status"] == "skipped_existing"
```

Expected: fail until the provider/seed path exposes idempotent behavior.

- [ ] **Step 2: Write failing duplicate-source test (id AND semantic signature)**

Add tests covering both exact id collision and cross-year semantic duplicates (a topic with 5 forms × 12 items = 60 items must not repeat the same question in different wording across forms):

```python
def test_seed_rejects_cross_form_duplicate_source_question_id(fake_form_bank):
    fake_form_bank.add("topic_waterproof_v1_form_1", source_question_ids=["q1", "q2"])
    with pytest.raises(ValueError, match="duplicate_source_question_id"):
        fake_form_bank.add("topic_waterproof_v1_form_2", source_question_ids=["q2", "q3"])

def test_seed_rejects_cross_form_duplicate_semantic_signature(fake_form_bank):
    # P0A v1.1 introduced semantic_signature to group repeated questions across years.
    fake_form_bank.add("topic_waterproof_v1_form_1", semantic_signatures=["sig_a", "sig_b"])
    with pytest.raises(ValueError, match="duplicate_semantic_signature"):
        fake_form_bank.add("topic_waterproof_v1_form_2", semantic_signatures=["sig_b", "sig_c"])
```

If `questions_bank`/capsules do not yet carry `semantic_signature`, compute it deterministically at seed time as `sha256(normalize(stem)+sorted(options))` and store it in the form metadata so this gate is enforceable now.

- [ ] **Step 3: Implement seed guard**

The seed path must:

- Assert target DB is main before `--persist`.
- Persist only reviewed form candidates.
- Preserve `blueprint_version`, `form_id`, `form_index`, `topic_id`, `subject_id`, `item_count`, `source_question_ids`, `semantic_signatures`, `release_status`, and `reviewed_at`.
- If current `assessment_forms` schema lacks first-class columns for these fields, store them in `quality_json` first; propose a metadata-column migration only if indexed querying or lifecycle management cannot be supported safely from `quality_json`.
- Store hidden grading data server-side only.
- Return `created`, `skipped_existing`, or `rejected`.

- [ ] **Step 4: Run seed tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_blueprint_coverage.py tests/services/assessment/test_testset_assembly.py tests/scripts/test_assessment_topic_catalog_scripts.py -q
```

Expected: all tests pass.

### Task 3.5: Authoring Backlog Handoff

**Files:**

- Create: `docs/qa/2026-05-25-assessment-testset-authoring-backlog.md`
- Modify: `docs/qa/2026-05-25-assessment-testset-topic-catalog-form-bank-audit.md`

- [ ] **Step 1: Generate backlog rows from audit output**

For every topic below the stable target, write a row:

```markdown
| topic_id | status | active_forms | minimum_needed | stable_needed | missing_scored_items | section_gap | owner | target_date | user_visible_state |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| safety | authoring_needed | 1 | 2 | 4 | 48 | temporary_power:16,civilized_incident:20 | teaching-owner-name | 2026-06-03 | disabled |
```

Rules:

- `minimum_needed = max(0, 3 - active_forms)`.
- `stable_needed = max(0, 5 - active_forms)`.
- `missing_scored_items` is computed from `12 × missing_forms` plus section floor gaps.
- `owner` and `target_date` must be real values before a topic can move from `authoring_needed` to `pilot`.

- [ ] **Step 2: Add frontend state contract**

For `authoring_needed` topics, frontend must:

- show the topic in catalog only if product wants demand shaping,
- label it `待补题`,
- disable the formal assessment button,
- never route it to dynamic generic question assembly.

- [ ] **Step 3: Add stop rule**

Stop implementation if a product request asks to enable a topic with fewer than 3 valid active forms. The only allowed alternatives are:

1. Mark the topic `authoring_needed`.
2. Reduce the release topic list.
3. Author and review enough items/forms, then rerun the gate.

### Task 4: Mobile Catalog And Personalized Recommendation

**Files:**

- Modify: `deeptutor/services/assessment/topic_catalog.py`
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Test: `tests/api/test_mobile_router.py`
- Test: `tests/api/test_mobile_assessment_payload_redaction.py`

- [ ] **Step 1: Write recommendation tests**

Required cases:

```python
def test_recommendation_defaults_to_20_question_diagnostic_without_learning_signal():
    recommendation = recommend_assessment_entry([], weak_nodes=[], has_assessment_history=False)
    assert recommendation["recommended_mode"] == "diagnostic"
    assert recommendation["recommended_count"] == 20

def test_recommendation_selects_enabled_weak_topic():
    recommendation = recommend_assessment_entry(
        [{"topic_id": "foundation", "label": "地基基础", "status": "stable", "enabled": True}],
        weak_nodes=[{"name": "地基基础", "mastery": 42}],
        has_assessment_history=True,
    )
    assert recommendation["recommended_mode"] == "topic"
    assert recommendation["recommended_topic_id"] == "foundation"
    assert recommendation["recommended_count"] == 12

def test_recommendation_never_selects_authoring_needed_topic():
    recommendation = recommend_assessment_entry(
        [{"topic_id": "safety", "label": "安全管理", "status": "authoring_needed", "enabled": False}],
        weak_nodes=[{"name": "安全管理", "mastery": 35}],
        has_assessment_history=True,
    )
    assert recommendation["recommended_mode"] == "diagnostic"
```

- [ ] **Step 2: Enforce payload redaction**

Add a response scan asserting `/assessment/topics` and `/assessment/create` never include:

```python
FORBIDDEN_KEYS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "option_reasoning",
}
```

- [ ] **Step 3: Implement minimal changes**

Rules:

- Catalog endpoint reads form-bank status only.
- Recommendation reads learner weak signals but does not write `training_intent`.
- `diagnostic_v1` remains the fallback for insufficient evidence.
- No topic with `authoring_needed` can be returned as `enabled=true`.

- [ ] **Step 4: Run API tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/api/test_mobile_router.py tests/api/test_mobile_assessment_payload_redaction.py -q
```

Expected: all tests pass.

### Task 5: Yousen Topic Catalog UI

**Files:**

- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`
- Test: `yousenwebview/tests/test_assessment_testset_view_model.js`
- Test: `yousenwebview/tests/test_package_assessment_contract.js`

- [ ] **Step 1: Add view-model tests**

Add assertions:

```javascript
assert.equal(model.recommendedMode, "topic");
assert.equal(model.selectedTopicId, "foundation");
assert.equal(model.topicCards.find((item) => item.topicId === "safety").enabled, false);
assert.equal(model.topicCards.find((item) => item.topicId === "safety").statusLabel, "待补题");
```

- [ ] **Step 2: Add template contract tests**

Assert:

```javascript
assert.ok(source.includes("专题测评目录"));
assert.ok(source.includes("综合摸底"));
assert.ok(source.includes("authoring_needed") || source.includes("待补题"));
assert.ok(!source.includes("官方真题"));
```

- [ ] **Step 3: Implement UI**

First viewport must show:

- Recommended entry.
- Comprehensive 20-question diagnostic entry.
- Topic TestSet catalog.
- `stable`, `pilot`, and `authoring_needed` status copy.
- Disabled click state for `authoring_needed`.

Copy invariants:

- Use `本次专题测评`, not `全科能力分`.
- Use `真题样式`, not `官方真题`, unless provenance gate is passed.
- Use `试运行覆盖` for pilot topics.
- Use `待补题` for authoring-needed topics.

- [ ] **Step 4: Run Node tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
node yousenwebview/tests/test_package_assessment_contract.js
node yousenwebview/tests/test_assessment_testset_view_model.js
```

Expected: all assertions pass.

### Task 6: Flywheel Contract Hardening

**Files:**

- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/chat/chat.js`
- Modify: `deeptutor/services/learner_state/conversation_learning_evidence.py`
- Modify: `deeptutor/services/learner_state/home_personalization.py`
- Test: `tests/services/learner_state/test_conversation_learning_evidence_event.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`
- Test: `yousenwebview/tests/test_assessment_testset_view_model.js`

- [ ] **Step 1: Lock result CTA**

Test:

```javascript
assert.ok(!assessmentWxml.includes('bindtap="goChat"'));
assert.ok(assessmentWxml.includes('bindtap="goLearningPlan"'));
```

- [ ] **Step 2: Lock wrong-item practice context**

Test required payload:

```javascript
assert.deepEqual(intent.learning_signal_type, "assessment_wrong_item_practice");
assert.ok(intent.attempt_ref);
assert.ok(intent.knowledge_point);
assert.ok(intent.error_code);
assert.equal(intent.question_count, 3);
```

- [ ] **Step 3: Ensure training completion writes evidence**

Python test:

```python
def test_training_completed_evidence_keeps_assessment_context():
    event = build_training_completed_event(
        user_id="u1",
        attempt_ref="assessment:q1",
        knowledge_point="地下防水等级",
        error_code="M02",
        training_question_count=3,
    )
    assert event["event_type"] == "learning_evidence"
    assert event["payload"]["learning_signal_type"] == "training_completed"
    assert event["payload"]["attempt_ref"] == "assessment:q1"
```

- [ ] **Step 4: Decide generator route**

If DevTools shows wrong-item practice still produces review-only free text, implement one of these two routes:

1. Preferred deterministic route: use existing structured practice generator to return 3 submit-able MCQs with assessment context.
2. Acceptable P1 route: keep chat route but enforce a structured card contract before allowing `training_completed`.

Do not allow free-form chat text to count as completed practice.

**Question-source authority (do not create a second question bank):**

- The 3 same-type questions MUST be sourced from `questions_bank` by `knowledge_point` + `error_code` (and `node_code` if available), reusing the single question authority. Verify first whether `questions_bank` supports filtering by these keys; if it does, this is the only allowed path for items that carry a `source_question_id`.
- If `questions_bank` cannot supply 3 distinct same-type items for that knowledge point, the wrong-item practice may use LLM-generated items **only** when each is labelled `source: "practice_generated"` and `is_formal_score: false`. Practice-generated items never carry a `source_question_id`, never enter formal assessment forms, never affect topic score, and write evidence as `learning_signal_type="practice"` (not a formal attempt).
- Exclude items the learner already saw in the originating assessment session (no immediate repeat of the exact wrong item).
- This route is `practice`, not `assessment`; it does not go through `assessment_sessions` and does not produce a comparable score.

- [ ] **Step 5: Run flywheel tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/learner_state/test_conversation_learning_evidence_event.py tests/services/learner_state/test_learning_report_read_model.py -q
node yousenwebview/tests/test_assessment_testset_view_model.js
```

Expected: all pass.

### Task 7: P0B Real-Exam Mini Simulation

**Files:**

- Modify: `deeptutor/services/assessment/blueprint.py`
- Modify: `deeptutor/services/assessment/coverage.py`
- Modify: `deeptutor/services/assessment/blueprint_service.py`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- Test: `tests/services/assessment/test_blueprint_coverage.py`
- Test: `tests/services/assessment/test_testset_assembly.py`

- [ ] **Step 1: Add blueprint test**

```python
def test_real_exam_simulation_mini_has_20_items():
    blueprint = get_assessment_blueprint("real_exam_simulation_mini_v1")
    assert blueprint.assessment_type == "real_exam_simulation"
    assert blueprint.delivered_count == 20
    assert blueprint.subject_id == "construction_exam"
```

- [ ] **Step 2: Add source policy test**

```python
def test_real_exam_simulation_prefers_real_exam_but_allows_safe_textbook_fallback(fake_provider):
    result = assemble_form("real_exam_simulation_mini_v1", provider=fake_provider)
    assert result["item_count"] == 20
    assert result["source_policy_label"] in {"真题样式测评", "综合模拟测评"}
    assert "官方真题" not in result["user_copy"]

def test_real_exam_copy_downgrades_when_real_exam_share_is_low(fake_provider):
    result = assemble_form("real_exam_simulation_mini_v1", provider=fake_provider.with_real_exam_share(0.2))
    assert result["source_policy_label"] == "综合模拟测评"
    assert "真题样式" not in result["user_copy"]

def test_official_real_exam_label_requires_provenance_and_teaching_signoff(fake_provider):
    result = assemble_form(
        "real_exam_simulation_mini_v1",
        provider=fake_provider.with_real_exam_share(1.0),
        source_policy_review={"provenance_ok": True, "teaching_signoff": False},
    )
    assert "官方真题" not in result["user_copy"]
```

- [ ] **Step 3: Implement P0B mini blueprint**

Rules:

- 20 questions.
- Deferred feedback.
- No strict timer in P0B.
- No equivalent full-exam score claim.
- Uses persisted forms if available.
- Uses copyright-safe copy unless provenance + teaching review both pass.
- Uses `真题样式测评` only if REAL_EXAM/TEXTBOOK_ASSESSMENT share meets the PRD threshold; otherwise uses `综合模拟测评`.
- Keeps `diagnostic_v1` unchanged; P0B has its own `real_exam_simulation_mini_v1` blueprint and form ids.
- Records source mix in report metadata so QA can explain why the label was chosen.

- [ ] **Step 4: Run P0B tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_blueprint_coverage.py tests/services/assessment/test_testset_assembly.py -q
```

Expected: all pass.

### Task 8: P1 Deep Explanation Cache

**Files:**

- Create: `deeptutor/services/assessment/deep_explanation.py`
- Modify: `deeptutor/services/assessment/report_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- Test: `tests/services/assessment/test_deep_explanation.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] **Step 1: Write cache-key test**

```python
def test_deep_explanation_cache_key_includes_result_hash():
    key1 = build_explanation_cache_key("quiz1", "q1", "answer-a", "grade-1", "p1-v1")
    key2 = build_explanation_cache_key("quiz1", "q1", "answer-a", "grade-2", "p1-v1")
    assert key1 != key2
```

- [ ] **Step 2: Write score-invariance test**

```python
def test_deep_explanation_never_changes_score(existing_report):
    before = existing_report["score"]
    explained = attach_deep_explanation(existing_report, question_id="q1", explanation={"summary": "..."})
    assert explained["score"] == before
```

- [ ] **Step 3: Implement bounded service**

Rules:

- Only post-submit.
- Default CTA on wrong/flagged items.
- Correct-item explanation behind cost guard.
- Cache key includes `quiz_id`, `question_id`, `learner_answer_hash`, `grading_result_hash`, and `prompt_version`.
- Explanation writes explanation evidence only; it does not write mastery and does not change score.
- If streaming is needed later, use `/api/v1/ws`; do not add assessment-specific WebSocket.
- **Per-user cost cap (required, not optional):** cache hits are free, but cache misses call an LLM. Without a cap, one learner tapping deep explanation on all 12 items = 12 LLM calls; at 50k members this is a cost incident. Enforce a per-user daily miss budget (default: ≤20 explanation cache-misses/user/day) and a global circuit breaker; over budget returns a graceful "稍后再试" instead of generating. Record the budget value in QA so cost can be projected before broad release.

- [ ] **Step 4: Run deep explanation tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment/test_deep_explanation.py tests/api/test_mobile_router.py -q
```

Expected: all pass.

### Task 9: Observability And Product Metrics

**Files:**

- Modify: `deeptutor/services/assessment/writeback.py`
- Modify: `deeptutor/services/assessment/report_read_model.py`
- Modify: `scripts/run_release_gate.py` only if an existing hook is the right home.
- Create: `docs/qa/2026-05-25-assessment-testset-p0b-p1-flywheel-dry-run.md`

- [ ] **Step 1: Emit minimal metric fields**

Required fields:

```text
assessment_session_started
assessment_session_submitted
assessment_result_viewed
assessment_wrong_item_practice_clicked
assessment_training_completed
assessment_retest_recommended
assessment_topic_status
assessment_form_bank_validation_failed
```

- [ ] **Step 2: Add QA metric table**

Add this table to the QA doc:

```markdown
| Metric | Source | P0B/P1 use |
| --- | --- | --- |
| submit_rate | started/submitted | form difficulty and UX |
| abandon_rate | started without submit | length/time friction |
| wrong_item_practice_ctr | practice clicked/result viewed | flywheel pull |
| training_completion_rate | completed/clicked | training quality |
| retest_rate | retest started/recommended | loop strength |
| topic_authoring_needed_count | catalog validator | content backlog |
```

- [ ] **Step 3: Run existing release tests**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment tests/api/test_mobile_router.py tests/api/test_mobile_assessment_payload_redaction.py -q
python scripts/check_contract_guard.py
```

Expected: all pass.

### Task 10: Production And DevTools Gate

**Files:**

- Modify: `docs/qa/2026-05-25-assessment-testset-p0b-p1-flywheel-dry-run.md`

- [ ] **Step 1: Run automated gates**

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
PYTHONPATH=. pytest tests/services/assessment tests/api/test_mobile_assessment_payload_redaction.py tests/api/test_mobile_router.py tests/services/learner_state/test_learning_report_read_model.py tests/services/learner_state/test_conversation_learning_evidence_event.py -q
node yousenwebview/tests/test_package_assessment_contract.js
node yousenwebview/tests/test_assessment_testset_view_model.js
python scripts/check_contract_guard.py
```

Expected:

```text
pytest: all passed
node: all assertions passed
contract-guard: passed
```

- [ ] **Step 2: Run production API smoke**

Use authenticated credentials only if available in the current secure environment. Do not paste tokens into QA docs.

Required checks (endpoint paths verified against `mobile.py` `@router` + `main.py` `prefix="/api/v1"` — do NOT prepend `/mobile`):

```text
GET  /api/v1/assessment/topics            -> 200
POST /api/v1/assessment/create            -> 200 for enabled topic
POST /api/v1/assessment/{quiz_id}/submit  -> 200
GET  /api/v1/<learning-report path>       -> 200 and includes new evidence or degraded reason
```

The learning-report path must be read from `mobile.py` `@router` declarations at smoke time, not assumed. If any contract doc still says `/api/v1/mobile/assessment/*`, it is stale; code wins per §0.1 rule 4, and the stale doc should be corrected in the same train.

- [ ] **Step 3: Run WeChat DevTools manual gate**

Record:

- Tool version.
- Project path.
- Mini-program page path.
- Screenshots or written observations for catalog, run, result, wrong-item practice, report retest.
- Any 4xx/5xx from Network tab.

- [ ] **Step 4: Verdict**

Use one of:

```text
READY_FOR_PILOT
READY_WITH_AUTHORING_BACKLOG
BLOCKED_BY_FORM_BANK
BLOCKED_BY_DEVTOOLS
BLOCKED_BY_WRITEBACK
```

---

## 4. Commit Plan

Do not use `git add -A`, `git add .`, `git commit -a`, `stash`, `reset --hard`, `checkout -- <file>`, or `clean`.

Recommended commits:

1. `docs: plan assessment p0b p1 production flywheel`
   - `docs/plan/2026-05-25-luban-assessment-testset-p0b-p1-production-flywheel-execution-plan.md`
   - `docs/plan/INDEX.md`
2. `feat: audit and persist assessment topic form banks`
   - topic catalog auditor, seed hardening, backend tests.
3. `feat: expose personalized assessment catalog`
   - catalog/recommendation API and Yousen catalog UI.
4. `feat: close assessment wrong-item training flywheel`
   - CTA, wrong-item practice, training-completed evidence, report retest recommendation.
5. `feat: add real exam mini simulation`
   - P0B 20-question blueprint and safe copy/source policy.
6. `feat: add bounded assessment deep explanations`
   - P1 explanation cache and score-invariance gates.
7. `docs: record assessment production flywheel QA`
   - QA dry-run docs and DevTools evidence.

---

## 5. Open Decisions With Verification

| Decision | Default | Verification | Alternative |
| --- | --- | --- | --- |
| Whether every topic can reach 5 forms | Require audit before claim | Topic catalog auditor over real Supabase | Mark 3-4 as `pilot`; <3 as `authoring_needed` |
| Wrong-item practice generator | Prefer deterministic submit-able MCQ generator | DevTools proves 3 submit-able cards and writeback | Use chat only with strict structured-card contract |
| P0B source label | Use `真题样式测评` | Provenance + teaching review required for stronger label | Use `综合模拟测评` |
| Deep explanation availability | P1 post-submit only | Cache/cost/score-invariance tests | Keep disabled CTA until cache is ready |
| WeChat release readiness | Require DevTools manual gate | Real simulator network + screenshots | Keep as internal pilot only |

---

## 6. Success Criteria

User can:

- See a topic TestSet catalog, not only a single waterproof entry.
- Understand which topics are stable, pilot, or waiting for authoring.
- Start a recommended TestSet based on current evidence.
- Fall back to the 20-question diagnostic when evidence is insufficient.
- Finish a 12-question topic TestSet and see score, wrong items, and simple explanation.
- Tap a wrong item and practice 3 submit-able same-type questions.
- Return to report training area and see a retest recommendation after training.
- Start a 20-question real-exam-style mini simulation after P0B gate passes.
- Request detailed explanation only after submit, with no score mutation.

Engineering can:

- Prove catalog status from persisted `assessment_forms`.
- Prove no pre-submit answer leakage.
- Prove `authoring_needed` topics cannot be started.
- Prove assessment writeback does not mutate `training_intent`.
- Prove deep explanation does not change score or mastery.
- Prove production API smoke and WeChat DevTools manual gate.

Product can:

- Track submit rate, abandon rate, wrong-item practice CTR, training completion, retest rate, and authoring-needed backlog.
- Decide which topics to author next from real form-bank gaps.
- Run a 14-day pilot without confusing topic score, all-subject mastery, and study-plan prescription.
