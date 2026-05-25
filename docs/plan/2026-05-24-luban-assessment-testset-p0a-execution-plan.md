# Luban Assessment TestSet P0A Execution Plan

> Status: Proposed v1.1, review-hardened on 2026-05-24.
>
> Supersedes review history: v1.0 inline draft.
>
> Canonical PRD: `docs/plan/2026-05-24-luban-assessment-testset-module-prd.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship P0A: a durable, deferred-feedback topic diagnostic TestSet for waterproof or the current waterproof/decoration/MEP composite topic, with score report, per-item learning evidence, mistake-book writeback, and no client-side answer leakage.

**Architecture:** Keep `AssessmentBlueprintService` as form/blueprint authority, add focused assessment services for session persistence, scoring, writeback, and report read model, and keep `/api/v1/mobile/assessment/*` as thin API wrappers. The canonical chain is `questions_bank -> assessment form/session -> deterministic scoring -> learning_evidence/mistake_book -> learning_report_read_model`; result-page next action is session-local and does not mutate `training_intent`.

**Tech Stack:** Python/FastAPI/Pydantic, Supabase Postgres + RLS, existing `learner_memory_events` and mistake-book services, `yousenwebview/packageDeeptutor`, pytest, Node view-model tests, WeChat DevTools manual gate.

---

## 0. Source Of Truth

Primary PRD:

- `docs/plan/2026-05-24-luban-assessment-testset-module-prd.md`

Relevant code authorities:

- `deeptutor/services/assessment/blueprint.py`
- `deeptutor/services/assessment/blueprint_service.py`
- `deeptutor/services/assessment/coverage.py`
- `deeptutor/services/member_console/service.py`
- `deeptutor/api/routers/mobile.py`
- `deeptutor/services/learner_state/service.py`
- `deeptutor/services/learner_state/attempt_refs.py`
- `deeptutor/services/learner_state/mistake_book.py`
- `deeptutor/services/learner_state/learning_report_read_model.py`
- `deeptutor/services/learner_state/learning_synthesis.py`
- `deeptutor/contracts/error_codes.py`
- `yousenwebview/packageDeeptutor/pages/assessment/*`
- `yousenwebview/tests/test_package_assessment_contract.js`

Out of scope for this plan:

- Phase 2 deep explanation generation.
- Phase 3 adaptive/CAT/item analytics.
- Phase 4 authoring/QTI/import standards.
- `real_exam_simulation_mini_v1` delivery beyond reserved names.
- `mastery_check_v1` delivery beyond reserved names.
- New assessment-specific WebSocket routes.
- A second question bank, learner-state store, or training prescription writer.

### 0.1 Plan Coverage And Deferred Roadmap

This is a complete execution plan for **P0A only**, not the full Assessment TestSet roadmap. The split is intentional:

| PRD scope | Status in this file | Why |
| --- | --- | --- |
| Phase -1 reality check | Fully planned | Required before any formal TestSet coding |
| Phase 0 design lock / coverage dry-run | Fully planned | Decides topic, count, copy, and teaching signoff |
| Phase 1 P0A topic diagnostic | Fully planned | The first shippable TestSet milestone |
| P0B real-exam mini simulation | Deferred to separate execution plan | Reuses P0A session/writeback/report foundation, but needs separate copyright/provenance and exam-copy gates |
| P1 mastery check | Deferred to separate execution plan | Depends on stable `training_intent`, attempt refs, and study-plan evidence consumption |
| P1/Phase 2 deep explanation | Deferred to separate execution plan | Requires explanation cache, cost controls, and unified question lifecycle wiring |
| P2 subjective case scoring | Deferred to separate execution plan | Requires rubric confidence and `construction_grading` readiness beyond objective/structured P0A |
| P2 adaptive assessment | Deferred to separate execution plan | Requires item analytics, discrimination signals, and score comparability labels |
| Phase 4 standards/authoring/QTI | Deferred to separate execution plan | Authoring/import standards should not block learner-facing P0A |

Do not expand this file to implement all deferred phases. Create follow-up files after P0A gates are green:

- `docs/plan/2026-05-24-luban-assessment-testset-p0b-real-exam-mini-execution-plan.md`
- `docs/plan/2026-05-24-luban-assessment-testset-p1-mastery-and-explanation-execution-plan.md`
- `docs/plan/2026-05-24-luban-assessment-testset-p2-case-adaptive-execution-plan.md`
- `docs/plan/2026-05-24-luban-assessment-testset-authoring-standards-execution-plan.md`

### 0.2 Execution Philosophy

P0A must prove the backbone before expanding the product surface:

```text
redacted form delivery
  -> durable session
  -> one-shot submit
  -> deterministic scoring
  -> idempotent evidence writeback
  -> report read model
  -> yusen visible result
```

Anything that does not strengthen this chain is deferred. In particular, do not add deep explanation, adaptive branching, teacher authoring, official-exam labeling, or full subjective grading to "make the assessment feel complete" before P0A has durable sessions and per-item evidence.

## 1. Hard Gates

Stop and report before continuing if any item below is true:

1. The P0A topic decision cannot be made from coverage evidence.
2. Any Supabase migration apply for `assessment_sessions` is attempted without all five of (a) reviewed schema design captured in the Phase -1 report, (b) RLS owner test, (c) submit-idempotency test, (d) target-database guard probe, and (e) explicit user approval recorded in the milestone report.
3. `last_assessment` downstream audit finds aggregate score or chapter mastery used as long-term mastery authority.
4. `learning_evidence` written with `source_feature="assessment_testset"` is not consumed by the learning-report/synthesis path, and the fix would alter learner-state authority.
5. Client create/resume payload contains `answer`, `answer_key`, `correct_answer`, `grading_key`, `scoring_points`, `minimal_rationale`, `rubric`, `official_answer`, or `option_reasoning` before submit.
6. Duplicate submit can duplicate learner events, attempt refs, or mistake-book rows.
7. Any gate fails twice consecutively.
8. `git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor rev-parse --show-toplevel` does not resolve to `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor` before staging or commit review.
9. Any Supabase write path lacks an explicit target-database guard, reviewed SQL, and rollback/degraded-mode plan.
10. User-facing copy implies "full exam ability", "official real exam", or "long-term mastery updated" before the corresponding authority has produced that fact.
11. P0A authoring backlog is required (approved topic cannot produce at least 3 non-overlapping forms, or cannot reach the signed 5-form stable target) but no signed handoff owner or delivery window has been recorded.
12. A new `error_codes` value is needed before a contract registry PR has landed.
13. P0A `result_report_json` is written without a `schema_version` field; future report readers cannot distinguish P0A and P0B/P1 shapes.

### 1.1 Known Uncertainties And Validation Paths

| Uncertainty | Validation | Default if validation fails |
| --- | --- | --- |
| Whether independent `waterproof` has enough eligible questions | Phase -1/0 read-only coverage audit with exact filters and candidate IDs | Pivot copy to `waterproof_decoration_mep`, reduce to 8-10 items, or block with authoring backlog |
| Whether a topic can support repeated attempts without memorization | Coverage audit must prove at least 3 non-overlapping forms; stable recommendation requires 5 forms with cross-form `source_question_id` / `semantic_signature` dedupe | Mark topic as blocked or minimum pilot; never expose a single-form formal TestSet |
| Whether `assessment_testset` learning evidence is consumed by learning-report/synthesis | `rg` audit plus a focused learner-state test that writes an assessment evidence event and reads the report | Add the narrowest read-model/synthesis support; do not write `training_intent` from submit |
| Whether durable session migration can be applied safely in current environment | Reviewed SQL, local/shadow apply where available, RLS owner tests, target DB guard | Keep P0A blocked for production; allow local demo only with explicit non-production copy |
| Whether simple explanation fields are available for all candidates | Coverage audit checks `analysis`, option reasoning, grading keywords, or source rationale | Show correct answer plus "详细解析下个版本上线"; do not fabricate simple explanation with LLM in P0A |
| Whether yusen current page can be evolved without destabilizing existing diagnostic | JS view-model tests before UI changes | Keep legacy diagnostic path stable and add P0A mode-specific rendering |
| Whether teaching approves 3/4/3/2 distribution | Teaching signoff packet from Phase 0 candidate review | Adjust count/distribution; do not hard-code PRD draft ratio |
| If both topics under-deliver, who owns authoring backlog and when can content land | Task 2.5 handoff packet with named teaching/authoring owner, target candidate count, and delivery window | Block P0A entry until owner+window are signed; no silent generic fallback |
| Whether `submit_idempotency_key` should be client-supplied or server-derived | Repository contract test: same body twice returns same result; different body twice raises 409 with stable error code | Server-derived `sha256(user_id|quiz_id|submitted_answer_snapshot_hash)`; client header optional only as cache hint |
| Default `device_lease_duration` and renewal cadence | Repository test: lease renews on heartbeat, expires after configured idle window; explicit take-over flips owner with audit trail | 30 min idle expiry, 5 min heartbeat; second device read-only until expiry or explicit take-over |
| Whether `create` is rate-limited / dedup'd against in_progress sessions | Service test: second `create` for same `(user_id, blueprint_version, topic_ids)` while one in_progress exists returns existing `quiz_id` instead of creating duplicate | Server returns existing `quiz_id` + `status="in_progress"`; user-visible copy explains "你已有一份未提交的测评" |
| Whether `result_report_json` shape can evolve without breaking P0A reports | Versioned `schema_version: "p0a-v1"` and read-model dispatch on version | Reject unknown versions in report read model; refuse to mis-render |
| Whether questions referenced by P0A form contain figures/tables that need mobile-safe rendering | Phase -1 coverage audit includes `has_figure_ref`, `has_table_ref`, and stem-length percentile | Exclude items lacking mobile-safe rendering from P0A pool until renderer is verified |
| Whether the same `semantic_signature` (cross-year repeat) appears twice in one form | Form assembly test: assert dedupe by `source_question_id` and by `semantic_signature` if the field exists | Skip duplicate semantic signature; log exclusion reason in coverage report |

### 1.2 Worktree And Database Safety

Before implementation or staging:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && pwd
git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor rev-parse --show-toplevel
git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor status --short --branch
```

Expected top-level:

```text
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
```

If the top-level resolves to `/private/tmp/...`, do not stage, commit, or rely on `git diff` until the worktree authority is clarified. File edits may use absolute paths only, and the milestone report must call out that git evidence is unreliable.

Any migration or Supabase write helper must have:

1. read-only dry-run first,
2. explicit main-database assertion,
3. owner/RLS test,
4. idempotency test,
5. rollback or degraded-mode note,
6. user approval before apply.

### 1.3 Migration Ownership Chain

A single owner for `assessment_sessions` migration prevents the design ↔ apply confusion that broke prior plans. Locked sequence:

1. Phase -1 Task 4 writes reviewed schema **inside `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`**. No SQL file yet.
2. Phase 0 Task 8 captures explicit user approval of that schema in the same QA doc (single source of truth, no parallel design notes).
3. Phase 1 Task 10 creates `supabase/migrations/<timestamp>_assessment_sessions.sql` **only after** Phase 0 approval line is filled in.
4. Apply (writing to Supabase) is gated on a separate explicit user message, not on Plan execution. Even after the migration file exists, the implementer must stop and ask before running `supabase db push` or equivalent.
5. If the schema changes after migration file creation, the old file is deleted and a new timestamped file is created. Do not edit applied migrations in place.

If steps 1-4 are out of order or any step lacks signed evidence, halt under Hard Gate #2.

## 2. File Map

Expected new files:

- `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`
  Phase -1 audit report and no-go register.
- `scripts/audit_assessment_testset_p0a.py`
  Read-only coverage, payload shape, topic, and downstream audit helper.
- `deeptutor/services/assessment/session_repository.py`
  Durable session repository interface and Supabase implementation with local/dev adapter.
- `deeptutor/services/assessment/scoring.py`
  Objective scoring and measurement-confidence helpers.
- `deeptutor/services/assessment/writeback.py`
  Aggregate assessment event, per-item learning evidence, attempt refs, and mistake-book writeback.
- `deeptutor/services/assessment/report_read_model.py`
  Submitted session result report for mobile result pages.
- `tests/services/assessment/test_testset_assembly.py`
  P0A blueprint/form/session assembly tests.
- `tests/services/assessment/test_scoring.py`
  Objective scoring and confidence tests.
- `tests/services/assessment/test_writeback.py`
  Per-item evidence, idempotency, attempt refs, and mistake-book tests.
- `tests/services/assessment/test_session_repository.py`
  Repository contract tests for local and Supabase-shaped rows.
- `tests/api/test_mobile_assessment_payload_redaction.py`
  Snapshot/recursive forbidden-key test for pre-submit payloads.
- `yousenwebview/tests/test_assessment_testset_view_model.js`
  Run/result view-model contract for P0A.
- `supabase/migrations/<timestamp>_assessment_sessions.sql`
  Durable session tables and RLS, created only after design review.

Expected modified files:

- `docs/plan/INDEX.md`
  Link this execution plan.
- `deeptutor/services/assessment/blueprint.py`
  Add approved P0A blueprint variant only after coverage/signoff.
- `deeptutor/services/assessment/blueprint_service.py`
  Extend create-session inputs and redacted client payload assembly.
- `deeptutor/services/member_console/service.py`
  Thin compatibility wrapper around new assessment services.
- `deeptutor/api/routers/mobile.py`
  Extend request/response schema while keeping router thin.
- `deeptutor/services/learner_state/learning_synthesis.py`
  Only if audit proves assessment evidence is not consumed by the canonical read path.
- `deeptutor/services/learner_state/learning_report_read_model.py`
  Only if needed to expose assessment evidence through the existing read model.
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`

Do not modify:

- `/api/v1/ws` routing.
- `deeptutor/services/construction_grading/*` unless a Phase 1 rubric gap is proven and explicitly approved.
- RAG runtime.
- Learner-state prescription writer / `training_intent` creation path.
- Source compiler files unless the separate source-compiler taxonomy blocker is cleared and that track is explicitly resumed.

### 2.1 P0A Data Model Decision

Default P0A choice: **one durable `assessment_sessions` table with JSONB item snapshots and result report JSON**. Do not introduce `assessment_attempt_items` in P0A unless Phase 0 proves that report/query/read-model needs cannot be met from session JSON plus per-item `learning_evidence`.

Rationale:

1. P0A has 8-12 delivered items; JSONB replay is simpler and enough for report/idempotency.
2. Long-term per-item learning truth already belongs in `learner_memory_events.learning_evidence`.
3. Adding `assessment_attempt_items` now creates a second query/read authority unless there is a concrete report need.

Minimum `assessment_sessions` shape:

| Column | Type | Purpose |
| --- | --- | --- |
| `session_id` / `quiz_id` | uuid | Stable session identity |
| `user_id` | text/uuid | Owner/RLS boundary |
| `assessment_type` | text | `topic_diagnostic` for P0A |
| `subject_id` | text | `construction_exam` |
| `topic_ids` | text[] | Approved topic/composite |
| `blueprint_version` | text | Reproducible blueprint identity (e.g. `topic_diagnostic_v1`) |
| `form_id` | text | Delivered form identity (e.g. `topic_waterproof_v1_form_03`) |
| `status` | text | `in_progress`, `submitted`, `scored`, `degraded`, `expired` |
| `schema_version` | text | Row schema version, initial `assessment_session_v1` |
| `client_questions_public` | jsonb | Redacted pre-submit payload |
| `session_questions_private` | jsonb | Server-only answers/grading artifacts |
| `draft_answer_snapshot` | jsonb | Optional server draft if P0 adds resume beyond local draft |
| `submitted_answer_snapshot` | jsonb | Immutable submit payload |
| `submit_idempotency_key` | text | Server-derived: `sha256(user_id|quiz_id|submitted_answer_snapshot_hash)`; client header optional only as cache hint |
| `result_report_json` | jsonb | Replayable submitted report; **must contain `schema_version: "p0a-v1"`** so future readers can dispatch by version |
| `result_report_hash` | text | Content hash of `result_report_json` to detect drift |
| `learning_event_refs` | jsonb | Idempotent evidence refs (`learner_memory_events.id` list with kind tags) |
| `mistake_book_refs` | jsonb | Wrong-item writeback refs |
| `degraded_reason` | text | Filled when `status='degraded'`; one of `writeback_failed`, `scoring_partial`, `source_redaction_failed`, `lease_conflict`, `unknown` |
| `device_id` | text | Active device holding lease |
| `lease_expires_at` | timestamptz | Lease expiry, default `created_at + 30min`, renewable on heartbeat |
| `lease_history` | jsonb | Append-only audit trail of lease take-overs `[{device_id, started_at, ended_at, reason}]` |
| `created_at` | timestamptz | Session creation time |
| `submitted_at` | timestamptz | Submit time (null until submitted) |
| `scored_at` | timestamptz | Scoring success time |
| `expires_at` | timestamptz | Default `created_at + 24h` per PRD §4.3 |

Post-submit report may expose `correct_answer` and `simple_explanation` for result review. It must still not expose private fields such as `grading_key`, hidden rubric internals, raw `scoring_points`, or unpublished option reasoning.

#### 2.1.1 Device Lease Semantics (PRD §4.3.1 落地)

| Aspect | P0A behavior |
| --- | --- |
| Default lease duration | 30 minutes from last heartbeat or write |
| Heartbeat cadence | Every 5 minutes during active answering, server-side stored in `lease_expires_at` |
| Second-device view | Read-only render of redacted form; clearly badged "已在另一台设备答题中" |
| Explicit take-over | Second device sends `POST /api/v1/mobile/assessment/{quiz_id}/take-over`; appends to `lease_history`; previous device next write returns 409 with `lease_taken_over` |
| Lease without heartbeat | Idle expiry after 30 min → second device can claim without explicit take-over |
| Submit while lease held by other | Returns 409 `lease_conflict`; client must take over or wait |
| Server-wins draft | Client draft upload only for items where server stored answer is null; otherwise silently dropped + logged |

`POST /take-over` is not strictly required for P0A pilot if there is a UI affordance to refresh and re-claim after expiry. If implementing it is non-trivial, ship P0A without the explicit endpoint but keep `lease_history` and read-only fallback — record the deferral in the milestone report.

#### 2.1.2 Result Report JSON Versioning

```jsonc
{
  "schema_version": "p0a-v1",
  "generated_at": "2026-05-24T12:00:00Z",
  "score_summary": { /* ... */ },
  "knowledge_map": [ /* ... */ ],
  "wrong_items": [ /* ... */ ],
  "attempt_refs": [ /* learner_memory_events.id with kind tags */ ],
  "session_local_next_action": { /* deterministic, no LLM, no training_intent mutation */ },
  "writeback_status": { /* per-target ack/fail */ },
  "degraded_reason": null
}
```

Report read model **must** dispatch on `schema_version` and refuse unknown versions with a clear error rather than rendering a partial mismatched shape.

### 2.2 Service Boundary

`MemberConsoleService` should become a compatibility facade for assessment P0A, not the place where new TestSet policy grows.

Target split:

```text
mobile.py
  -> MemberConsoleService.create_assessment/submit_assessment/report
  -> AssessmentTestSetService
       -> AssessmentBlueprintService
       -> AssessmentSessionRepository
       -> AssessmentScoringService
       -> AssessmentWritebackService
       -> AssessmentReportReadModel
```

If creating `AssessmentTestSetService` adds too much churn for Phase 1, the fallback is still to create the focused lower-level services and keep `MemberConsoleService` as the only thin coordinator. Do not add scoring, writeback, redaction, RLS policy, or report assembly directly into the router.

### 2.3 Test Strategy

P0A relies on three test tiers. Each tier has a clear default mode so contributors do not invent ad-hoc fixtures.

| Tier | Scope | Default fixture | Where it runs |
| --- | --- | --- | --- |
| Unit | Pure functions, schemas, scoring, redaction, view-model | In-memory dataclasses; no IO | Always in PR (`pytest -q`, `node`) |
| Repository contract | `AssessmentSessionRepository` against an in-memory adapter that emulates Supabase semantics (uuid pk, owner-scoped queries, immutable submitted snapshot) | Python dict + per-row dict with same shape as `assessment_sessions`; explicit owner check | Always in PR |
| Supabase integration smoke | Real Supabase shadow project or local Postgres with RLS policy applied | `@pytest.mark.integration` opt-in, gated by env var `LUBAN_INTEGRATION_DB_URL` | Manual + before broad release; never default in PR |

Rules:

1. PR-time tests must not require Supabase credentials. The default in-memory adapter satisfies all PR gates.
2. Integration tier is opt-in only. If the env var is absent, integration tests skip with a clear message; they never silently pass.
3. RLS policy is verified twice: once as a SQL diff under code review, once as an integration smoke that asserts a different `user_id` cannot read the row.
4. Frontend tests (`yousenwebview/tests/*.js`) use Node, run in PR, and must not call backend; they pin against fixture JSON that mirrors the redacted public payload.
5. Manual gates (WeChat DevTools, take-over flow) are evidence-capture, not test substitutes; their absence does not justify skipping unit/contract tiers.

## 3. Phase -1: Reality Check And No-Go Report

**Goal:** Prove the current system can safely host P0A before feature coding.

### Task 1: Current Surface Audit

**Files:**

- Create: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`
- Create: `scripts/audit_assessment_testset_p0a.py`

- [ ] Run current status:

```bash
git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor status --short --branch
```

- [ ] Audit route and client entrypoints:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
rg -n "assessment/(create|profile|[^/]+/submit)|createAssessment|submitAssessment|assessment_type|quiz_id" \
  deeptutor/api/routers/mobile.py \
  yousenwebview/packageDeeptutor \
  wx_miniprogram
```

- [ ] Record whether all clients still use `/api/v1/mobile/assessment/create` and `/api/v1/mobile/assessment/{quiz_id}/submit`.
- [ ] Record current request gaps: `assessment_type` is accepted by `AssessmentCreateRequest` but not passed to `MemberConsoleService.create_assessment`.
- [ ] Record current response gaps: submitted result has no per-item attempts, no attempt refs, no wrong-item details, and no durable report endpoint.

Acceptance:

- Report names all current entrypoints.
- Report identifies any duplicate assessment surface.
- No code path changes in this task.

### Task 2: Topic Granularity Audit

**Files:**

- Modify: `scripts/audit_assessment_testset_p0a.py`
- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Audit current blueprint topics:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
python - <<'PY'
from deeptutor.services.assessment.blueprint import DIAGNOSTIC_V1
for section in DIAGNOSTIC_V1.sections:
    print(section.id, section.label, section.count, ",".join(section.topics))
PY
```

- [ ] Add read-only coverage mode to `scripts/audit_assessment_testset_p0a.py`:
  - `--topic waterproof`
  - `--topic waterproof_decoration_mep`
  - `--run-id <id>`
  - `--out artifacts/assessment_testset/p0a/<run_id>/`
- [ ] The script must query/read only. It must not write Supabase or production files.
- [ ] The script must emit `coverage.json` and `coverage.md` with:
  - candidate count
  - answer-key coverage
  - option coverage
  - knowledge-node coverage
  - source type distribution
  - simple-explanation availability
  - long-stem exclusion count
  - candidate IDs used for manual review
- [ ] Run both topic audits if Supabase credentials are available:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
python scripts/audit_assessment_testset_p0a.py --run-id p0a-phase-minus-1 --topic waterproof --read-only
```

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
python scripts/audit_assessment_testset_p0a.py --run-id p0a-phase-minus-1 --topic waterproof_decoration_mep --read-only
```

Acceptance:

- Report recommends exactly one of:
  - split independent `waterproof`, or
  - pivot P0A copy to `waterproof_decoration_mep`.
- If neither topic can produce at least 3 non-overlapping forms, P0A is blocked and Task 2.5 authoring backlog handoff becomes a Phase -1 exit gate. A 12-item stable P0A target requires 5 forms / 60 unique eligible scored candidates, with section floors satisfied.
- Coverage report records, per candidate, whether the stem contains figure refs, table refs, or exceeds the mobile-safe stem length threshold; items failing mobile rendering are excluded with explicit reason.
- Coverage report deduplicates candidates by `source_question_id` and (if available) by `semantic_signature`; cross-year repeats are surfaced for manual selection rather than auto-included.

### Task 2.5: Authoring Backlog Handoff (only if Task 2 blocks P0A)

**Files:**

- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

Trigger: Task 2 acceptance shows both `waterproof` and `waterproof_decoration_mep` candidate pools below the P0A rotation floor (at least 3 non-overlapping forms) or below the signed stable target (prefer 5 non-overlapping forms).

- [ ] Record in the QA report:
  - exact eligible candidate counts per topic
  - shortfall against P0A delivery target
  - named teaching/authoring owner
  - target candidate count to unblock (`delivered_count × 3` minimum pilot, `delivered_count × 5` stable target; section floors also required)
  - delivery window with explicit calendar date
  - escalation contact if window slips
- [ ] Until the handoff is signed (owner + date + window present), Phase 0 must not start. The plan does **not** auto-degrade to generic construction questions.
- [ ] If the product owner decides to ship a smaller P0A (8 items instead of 12), record the explicit decision here and re-run Phase 0 coverage with the revised target.

Acceptance:

- Either the QA report holds a signed authoring handoff, **or** product has explicitly reduced P0A scope to a count the current pool already supports.
- No generic-fallback path exists in code that could mask the shortage.

### Task 3: Payload Redaction Baseline

**Files:**

- Create: `tests/api/test_mobile_assessment_payload_redaction.py`
- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Write a failing recursive forbidden-key test against current `member_service.create_assessment(...)` and mobile route response.
- [ ] Forbidden pre-submit keys:

```python
FORBIDDEN_PRE_SUBMIT_KEYS = {
    "answer",
    "answer_key",
    "correct_answer",
    "grading_key",
    "scoring_points",
    "minimal_rationale",
    "rubric",
    "official_answer",
    "option_reasoning",
}
```

- [ ] Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest tests/api/test_mobile_assessment_payload_redaction.py -q
```

- [ ] If the test passes before implementation, record the baseline as already redacted and keep the test as a release gate.
- [ ] If it fails, stop and patch redaction before any Phase 1 feature work.

Acceptance:

- Pre-submit payload cannot expose hidden answer/grading fields.
- Test fails if `answer` is accidentally returned from `session_questions`.
- Post-submit report has a separate allowlist: `correct_answer` and `simple_explanation` are allowed for review; `grading_key`, raw rubric internals, hidden scoring points, and unpublished option reasoning remain forbidden.
- Structural fuzz check: in addition to the fixed `FORBIDDEN_PRE_SUBMIT_KEYS` set, the test walks the entire payload and flags any nested key whose name contains `answer`, `grading`, `rubric`, `scoring_point`, or `correct` substring (case-insensitive). A matching key must be allowlisted explicitly with a justification comment in the test file, otherwise the test fails. This catches schema drift like a future field rename to `expectedChoices` or `gradingArtifact`.

### Task 4: Durable Session Schema Design

**Files:**

- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Confirm current JSON storage with code references:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
rg -n "_data_path|assessment_sessions|def create_assessment|def submit_assessment" \
  deeptutor/services/member_console/service.py
```

- [ ] Draft reviewed schema in the report before creating a migration:
  - `assessment_sessions`
  - optional `assessment_attempt_items` if report/query needs indexed items
  - owner fields: `user_id`, `device_id`, `lease_expires_at`
  - state fields: `status`, `created_at`, `submitted_at`, `expires_at`
  - hidden server artifact: `session_questions_private`
  - public artifact: `client_questions_public`
  - idempotency: `submit_idempotency_key`, `result_hash`, `submitted_answer_snapshot`
  - writeback refs: `learning_event_refs`, `mistake_book_refs`
- [ ] Include RLS policy sketch:
  - owner can select own rows
  - owner can insert own rows
  - owner can update own in-progress rows
  - submitted rows are immutable except server-side writeback refs
- [ ] Stop for user review before creating/applying `supabase/migrations/*assessment_sessions.sql`.

Acceptance:

- Design covers owner checks, lease, TTL, hidden answers, submit idempotency, and result replay.
- No production DB write happens in Phase -1.
- P0A default is `assessment_sessions` JSONB replay plus `learning_evidence`; `assessment_attempt_items` is deferred unless a concrete indexed-query need is proven.

### Task 5: Last Assessment And Learner-State Authority Audit

**Files:**

- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
rg -n "last_assessment" deeptutor/ web/ wx_miniprogram/ yousenwebview/
```

- [ ] Classify each hit:
  - aggregate display only
  - profile seed
  - mastery authority risk
  - stale compatibility path
- [ ] Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
rg -n "source_feature == .construction_grading.|memory_kind == .learning_evidence.|assessment_testset|read_learning_evidence" \
  deeptutor/services/learner_state
```

- [ ] Decide whether assessment `learning_evidence` can use `source_feature="assessment_testset"` without being ignored by synthesis/read models.
- [ ] If the read path only consumes `construction_grading`, stop and propose a minimal learner-state authority patch.

Acceptance:

- Report states whether `last_assessment` blocks broad P0A release.
- Report states exact read path for assessment per-item evidence.
- If `learning_synthesis.py` only accepts `source_feature="construction_grading"`, the report must recommend either accepting `assessment_testset` as an evidence source or using an existing canonical writer that preserves assessment provenance.

### Task 5.5: Auth, Ownership, And Abuse Audit

**Files:**

- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Inspect mobile auth boundary:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
rg -n "_resolve_authenticated_user_id|assessment_create|assessment_submit|quiz_id" deeptutor/api/routers/mobile.py
```

- [ ] Record required Phase 1 tests:
  - user A cannot resume user B session
  - user A cannot submit user B session
  - missing/invalid auth cannot create formal P0A session
  - duplicate client submit with different body returns original submitted result, not a rescore
  - expired session returns explicit expired/degraded state

Acceptance:

- Phase -1 report names the exact owner-check point for create/resume/submit/report.

## 4. Phase 0: Design Lock And Coverage Dry Run

**Goal:** Lock topic, count, copy, and durable-session approach before Phase 1 code.

### Task 6: Coverage Dry-Run Script And Artifacts

**Files:**

- Modify: `scripts/audit_assessment_testset_p0a.py`
- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Add deterministic form preview:
  - section target counts
  - selected candidate IDs
  - excluded candidate IDs and reasons
  - source mix
  - knowledge-node distribution
  - answer/simple-explanation coverage
- [ ] Emit:
  - `artifacts/assessment_testset/p0a/<run_id>/coverage.json`
  - `artifacts/assessment_testset/p0a/<run_id>/coverage.md`
  - `artifacts/assessment_testset/p0a/<run_id>/candidate_review.csv`
- [ ] Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
python scripts/audit_assessment_testset_p0a.py \
  --run-id p0a-phase-0 \
  --topic <approved-topic> \
  --read-only \
  --emit-form-preview
```

Acceptance:

- Exact P0A delivered count is recommended as 12, 10, 8, or blocked.
- Exact P0A form rotation status is recommended as blocked, 3-form minimum pilot, or 5-form stable.
- Report has enough candidate detail for teaching review.

### Task 7: Teaching Signoff Packet

**Files:**

- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md`

- [ ] Add signoff section with:
  - topic label shown to users
  - whether copy can say "防水专题" or must say "防水/装饰/机电综合测评"
  - count and section distribution
  - source policy label: "专项测评", "真题样式测评", or other approved copy
  - copyright/provenance caveat
  - long stem/mobile exclusion policy
- [ ] Stop for teaching/product approval.

Acceptance:

- Phase 1 does not start until signoff status is recorded.

### Task 7.5: P0A+ Topic TestSet Catalog And Form Bank

**Files:**

- Create: `deeptutor/services/assessment/topic_catalog.py`
- Create: `scripts/seed_assessment_topic_catalog_forms.py`
- Create: `tests/services/assessment/test_topic_catalog.py`
- Create: `tests/scripts/test_assessment_topic_catalog_scripts.py`
- Modify: `deeptutor/services/assessment/blueprint.py`
- Modify: `deeptutor/services/assessment/blueprint_service.py`
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.{js,wxml,wxss}`
- Modify: `yousenwebview/tests/test_assessment_testset_view_model.js`

Scope: this is a P0A+ closeout task after the waterproof P0A path works. It expands the entry from one topic to a governed catalog; it does not add CAT, teacher authoring UI, P1 deep explanations, or new learner mastery authority.

- [ ] Define the required topic catalog:
  - `waterproof`
  - `decoration`
  - `mep`
  - `foundation`
  - `main_structure`
  - `formwork_scaffold`
  - `safety`
  - `schedule`
  - `contract_claim`
  - `quality_acceptance`
- [ ] Each topic blueprint delivers 12 scored items through 3 section specs × 4 items, with strict topic filters and section-level rotation floors.
- [ ] Run coverage/form-bank gate for every topic:
  - `stable`: at least 5 active persisted forms
  - `pilot`: 3-4 active persisted forms
  - `authoring_needed`: fewer than 3 active persisted forms
- [ ] Runtime catalog status must validate persisted form bank quality before enabling a topic; a topic with 5 active rows but duplicate/bad items is `authoring_needed`, not `stable`.
- [ ] Persist stable/pilot form banks into `assessment_forms` only after dry-run, target-database guard, and reviewed candidate output.
- [ ] Add `GET /api/v1/assessment/topics` as a non-chat, non-streaming HTTP adapter; it reads catalog status only and must not start a turn.
- [ ] Add a separate `recommendation` read model beside the catalog:
  - insufficient learning signal -> recommend `diagnostic_v1` / 20-question comprehensive diagnostic
  - weak enabled topic signal -> recommend that topic TestSet
  - never recommend `authoring_needed`
  - never write `training_intent`
- [ ] Update Yousen assessment page to show a “专题测评目录”; disabled topics show maintenance state and cannot start a formal TestSet.
- [ ] `create_assessment(assessment_type=topic_diagnostic, topic_ids=[...])` must resolve the selected topic blueprint instead of hard-coding waterproof.
- [ ] If a topic is `authoring_needed`, block opening the formal assessment and hand off to Task 2.5 authoring backlog.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest \
  tests/services/assessment/test_topic_catalog.py \
  tests/scripts/test_assessment_topic_catalog_scripts.py \
  tests/api/test_mobile_assessment_payload_redaction.py \
  tests/api/test_mobile_router.py \
  tests/services/member_console/test_service.py \
  -q && \
node yousenwebview/tests/test_assessment_testset_view_model.js
```

Supabase pre-generation:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py --dry-run

cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. python scripts/seed_assessment_topic_catalog_forms.py --persist
```

Acceptance:

- Every catalog topic is classified from persisted form count, not frontend constants.
- Stable topics have 5 forms × 12 items, with 60 scored items and 60 unique scored source IDs.
- Mini-program first screen exposes the catalog, and `开始诊断` sends the selected topic id.
- No single-form topic is exposed as a formal TestSet.

### Task 8: Phase 0 Exit Gate / Phase 1 Entry Lock

**Files:**

- Modify: this plan only if Phase 0 findings change implementation order.
- Modify: `docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md` with Phase 0 sign-line.

- [ ] Map each PRD §13 quality gate to a test command or manual gate.
- [ ] Confirm migration apply decision and capture explicit user approval line in the QA report (single source of truth for §1.3 chain).
- [ ] Confirm whether `assessment_attempt_items` is required in P0A or whether submitted report can replay from `assessment_sessions`.
- [ ] Confirm no Phase 2 deep-explanation implementation will be included.
- [ ] Confirm exact user-facing copy for score interpretation:
  - "本次专题测评得分"
  - not "全科能力分"
  - not "长期学习计划已更新"
- [ ] Confirm exact redaction allowlist before and after submit.
- [ ] Confirm owner-check test cases.
- [ ] Confirm authoring backlog handoff status (Task 2.5) is either "not needed" with coverage evidence or "signed" with owner + date.
- [ ] Confirm `error_codes` registry already covers all P0A error codes; if any new code is needed, halt under Hard Gate #12 and open contract registry PR before Phase 1 starts.
- [ ] Confirm `result_report_json` schema_version string is locked as `"p0a-v1"` and read model dispatches on it.

Acceptance:

- No Phase 1 coding starts with unresolved authority or durability decisions.
- QA report has explicit Phase 0 sign-line with date and reviewer.

## 5. Phase 1: P0A TestSet Foundation

**Goal:** Learner completes one approved P0A TestSet, submits once, sees score/report, and the system writes durable evidence without leaking answers before submit.

### Task 9: Request Schema And Blueprint Variant

**Files:**

- Modify: `deeptutor/api/routers/mobile.py`
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `deeptutor/services/assessment/blueprint.py`
- Modify: `deeptutor/services/assessment/blueprint_service.py`
- Test: `tests/services/assessment/test_testset_assembly.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] Write failing tests:
  - `test_create_accepts_topic_diagnostic_fields_without_breaking_legacy_diagnostic`
  - `test_p0a_blueprint_delivers_exact_signed_off_count`
  - `test_p0a_blueprint_fails_closed_when_topic_candidates_short`
  - `test_p0a_does_not_include_profile_probe_items_in_score`
  - `test_create_returns_existing_in_progress_for_same_user_topic_blueprint` (dedupe path; user double-tap "开始测评" does not spawn a second formal session)
  - `test_create_rate_limit_window_returns_existing_session_with_explanatory_code`
  - `test_legacy_diagnostic_request_without_assessment_type_still_works_with_existing_clients` (backward compatibility against fixture matching the last 30 days of shipped mobile request shapes)
  - `test_blueprint_version_is_returned_to_client_for_form_audit`
- [ ] Extend `AssessmentCreateRequest` with:
  - `assessment_type`
  - `subject_id`
  - `topic_ids`
  - `count`
  - `duration_policy`
- [ ] Keep router as thin wrapper; pass normalized fields into service.
- [ ] Add approved P0A blueprint variant after Phase 0 signoff.
- [ ] Preserve legacy `diagnostic` behavior.
- [ ] `create` is dedupe-aware: when a user has an `in_progress` session for the same `(subject_id, blueprint_version, topic_ids)`, return that existing `quiz_id` with `status="in_progress"` and a clear `reuse_reason="active_session_exists"` field instead of spawning a duplicate. PRD §13.3 "User taps start twice" gate must pass.
- [ ] Apply a soft rate limit per user (e.g. ≤1 new formal P0A `create` per 5 minutes) to prevent `assessment_sessions` flooding. Block extra creates with a clear copy: "你已有一份未提交的测评，先去完成或交卷"; never silently scrap older `in_progress` sessions.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest \
  tests/services/assessment/test_testset_assembly.py \
  tests/api/test_mobile_router.py \
  -q
```

Acceptance:

- Legacy diagnostic clients still work.
- P0A cannot silently fall back to generic questions.

### Task 10: Durable Session Repository

**Files:**

- Create: `deeptutor/services/assessment/session_repository.py`
- Create: `tests/services/assessment/test_session_repository.py`
- Create: `supabase/migrations/<timestamp>_assessment_sessions.sql`
- Modify: `deeptutor/services/member_console/service.py`

- [ ] Write failing tests:
  - `test_session_repository_stores_private_and_public_artifacts_separately`
  - `test_resume_returns_redacted_public_payload`
  - `test_duplicate_submit_returns_existing_result`
  - `test_device_lease_blocks_conflicting_writer`
  - `test_expired_in_progress_session_cannot_be_submitted`
  - `test_lease_renews_on_heartbeat_within_default_window`
  - `test_idle_lease_expires_after_30_minutes_and_second_device_can_claim`
  - `test_explicit_take_over_appends_to_lease_history_and_invalidates_old_device_writes`
  - `test_server_wins_draft_drops_client_value_for_items_with_existing_server_answer`
  - `test_server_draft_patch_does_not_promote_to_submitted_state`
  - `test_owner_check_blocks_user_a_from_reading_user_b_session_via_repository_layer`
  - `test_owner_check_blocks_cross_user_submit_attempt`
  - `test_submit_idempotency_key_is_server_derived_and_stable_across_retries`
  - `test_different_submit_body_with_same_quiz_id_returns_409_with_stable_error_code`
  - `test_degraded_status_records_explicit_reason_and_is_recoverable_via_writeback_retry`
- [ ] Implement repository contract:
  - `create_session`
  - `get_session_for_resume`
  - `mark_submitted_once`
  - `attach_writeback_refs`
  - `expire_stale_sessions` (lazy: invoked from `get_session_for_resume` and `mark_submitted_once`; no cron required for P0A)
  - `renew_lease`
  - `take_over_lease`
  - `record_degraded`
- [ ] Add owner-check behavior:
  - `get_session_for_resume(user_id=A, quiz_id owned by B)` returns not found/forbidden
  - `mark_submitted_once(user_id=A, quiz_id owned by B)` returns not found/forbidden
- [ ] Add status transition behavior:
  - `in_progress -> expired` after TTL
  - `in_progress -> submitted -> scored`
  - `submitted/scored` cannot be mutated by a different answer snapshot
  - any writeback failure marks `degraded` with reason
- [ ] Keep hidden answers only in private server-side fields.
- [ ] Create migration only after user approves schema design.
- [ ] Do not apply migration without explicit approval.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest tests/services/assessment/test_session_repository.py -q
```

Acceptance:

- Durable repository is the production P0A authority.
- Member-console JSON remains local/dev compatibility only.

### Task 11: Scoring And Measurement Confidence

**Files:**

- Create: `deeptutor/services/assessment/scoring.py`
- Create: `tests/services/assessment/test_scoring.py`
- Modify: `deeptutor/services/member_console/service.py`

- [ ] Write failing tests:
  - `test_scores_single_and_multi_answer_items`
  - `test_blank_attempt_is_reported_without_mastery_penalty_flag`
  - `test_completion_rate_affects_measurement_confidence`
  - `test_time_pattern_marks_low_confidence_without_overriding_score`
  - `test_duplicate_source_question_ids_are_rejected`
- [ ] Move scoring out of `MemberConsoleService.submit_assessment`.
- [ ] Score only server-side session questions.
- [ ] Return item-level grading results with:
  - `question_id`
  - `source_question_id`
  - `learner_answer`
  - `correct_answer`
  - `is_correct`
  - `knowledge_points`
  - `simple_explanation`
  - `error_codes`
  - `measurement_confidence`

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest tests/services/assessment/test_scoring.py -q
```

Acceptance:

- Score is deterministic and reproducible from server session artifact.
- Frontend has no correctness inference.

### Task 12: Writeback Service

**Files:**

- Create: `deeptutor/services/assessment/writeback.py`
- Create: `tests/services/assessment/test_writeback.py`
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `deeptutor/services/learner_state/learning_synthesis.py` only if Phase -1 proves the read path ignores assessment evidence.
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py` only if needed for report consumption.

- [ ] Write failing tests:
  - `test_submit_writes_one_learning_evidence_event_per_scored_item`
  - `test_submit_duplicate_does_not_duplicate_learning_events`
  - `test_attempt_ref_is_signed_after_event_id_exists`
  - `test_wrong_item_is_saved_to_mistake_book_projection`
  - `test_error_codes_must_exist_in_error_code_registry`
  - `test_assessment_submit_does_not_mutate_training_intent`
- [ ] Use `deeptutor/contracts/error_codes.py:ERROR_CODE_REGISTRY`.
- [ ] Run `python scripts/check_contract_guard.py` as a release gate.
- [ ] If a P0A error condition does not map to an existing `M01-M10` (MCQ) or `E01-E12` (case) code, halt under Hard Gate #12. Open a separate contract registry PR that lands first; only after merge can the writeback emit the new code. P0A does **not** introduce `unknown_error` as a permanent product taxonomy.
- [ ] Preserve aggregate assessment event for profile/BI, but do not make it mastery authority.
- [ ] Add per-item `learning_evidence` with dedupe key:

```text
assessment_item:{user_id}:{quiz_id}:{question_id}
```

- [ ] Assessment evidence payload must include enough attempt-detail context:
  - `assessment_type`
  - `quiz_id`
  - `form_id`
  - `question_id`
  - `source_question_id`
  - `learner_answer`
  - `correct_answer`
  - `is_correct`
  - `knowledge_points`
  - `error_codes`
  - `measurement_confidence`
  - `simple_explanation`

- [ ] Low-confidence evidence is still written as observation, but report/read-model must not promote it to stable mastery without synthesis confidence.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest tests/services/assessment/test_writeback.py -q
```

Acceptance:

- P0A is not complete unless per-item evidence and attempt refs exist.
- Wrong answered items flow through the cloud mistake-book authority.

### Task 13: Report Read Model And Mobile API

**Files:**

- Create: `deeptutor/services/assessment/report_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Modify: `deeptutor/services/member_console/service.py`
- Test: `tests/api/test_mobile_assessment_payload_redaction.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] Write failing tests:
  - `test_create_payload_is_redacted_before_submit`
  - `test_resume_payload_is_redacted_before_submit`
  - `test_submit_returns_score_wrong_items_knowledge_map_and_attempt_refs`
  - `test_report_endpoint_replays_submitted_report`
  - `test_report_next_action_is_session_local`
  - `test_deep_explanation_endpoint_not_required_for_p0a`
- [ ] Add or wire endpoints:
  - `GET /api/v1/mobile/assessment/{quiz_id}`
  - `GET /api/v1/mobile/assessment/{quiz_id}/report`
- [ ] Keep `POST /api/v1/mobile/assessment/create` and submit stable.
- [ ] Result report sections:
  - score summary
  - knowledge map
  - wrong items
  - simple explanations
  - attempt refs
  - session-local next action
  - writeback status
- [ ] Score interpretation rules:
  - show "本次专题测评得分"
  - show topic/composite label
  - show confidence/degraded reason in learner-safe language
  - do not claim full exam-level ability
  - do not claim long-term training plan has already changed
- [ ] Do not implement working deep explanation in P0A.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest \
  tests/api/test_mobile_assessment_payload_redaction.py \
  tests/api/test_mobile_router.py \
  -q
```

Acceptance:

- Before submit: no answer/grading payload.
- After submit: report can show correct answers and simple explanations.

### Task 14: Yousen Assessment Run/Result Surface

**Files:**

- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxss`
- Modify: `yousenwebview/tests/test_package_assessment_contract.js`
- Create: `yousenwebview/tests/test_assessment_testset_view_model.js`

- [ ] Write failing JS tests:
  - pre-submit question render contains no answer fields
  - local draft restore does not override submitted server result
  - blank and partial submit copy is clear
  - result shows score, wrong items, simple explanation, and knowledge map
  - P0A deep explanation CTA is hidden or disabled
  - frontend does not derive mastery/response profile when backend report is present
  - copy invariants test: result page renders strings drawn from a fixed `i18n_keys` map; the test asserts (a) `assessment.result.score_title` resolves to a literal that starts with "本次"; (b) the page must NOT contain any of `"全科能力分"`, `"长期学习计划已更新"`, `"系统已为你更新"`, `"已掌握"`; (c) deep-explanation CTA copy resolves to `"详细解析下个版本上线"` or is fully absent from the DOM
  - second-device read-only banner shows when API returns `lease_holder_other_device`
  - degraded result renders a clearly badged degraded panel with the `degraded_reason` mapped to a learner-safe copy entry (never raw codes)
- [ ] Maintain copy as an `i18n_keys` mapping in `yousenwebview/packageDeeptutor/pages/assessment/assessment.i18n.json` (or equivalent) so the copy invariants test has a single source of truth.
- [ ] Update page copy to approved topic label.
- [ ] Keep UI as usable assessment surface, not landing page.
- [ ] Use server report as display authority after submit.
- [ ] Keep client draft as draft only; server-wins on conflict.
- [ ] Add a11y baseline:
  - option controls have semantic labels
  - keyboard/screen-reader equivalent labels exist where the platform supports them
  - correctness markers are not color-only
  - long stems do not overlap fixed action controls
  - any image-bearing stem either has alt text or is excluded from P0A pool (linked back to Phase -1 coverage filter)
- [ ] Keep `wx_miniprogram` as shadow/parity only unless routing contract requires a matching update.

Run:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
node yousenwebview/tests/test_package_assessment_contract.js && \
node yousenwebview/tests/test_assessment_testset_view_model.js
```

Acceptance:

- P0A visible flow matches PRD §11.
- No client-side correctness/mastery authority remains in P0A result path.

### Task 15: Full Gate Run

**Files:**

- No new files unless a gate failure requires a narrow fix.

- [ ] Run backend gates:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
PYTHONPATH=. pytest \
  tests/services/assessment/test_blueprint_coverage.py \
  tests/services/assessment/test_testset_assembly.py \
  tests/services/assessment/test_session_repository.py \
  tests/services/assessment/test_scoring.py \
  tests/services/assessment/test_writeback.py \
  tests/api/test_mobile_router.py \
  tests/api/test_mobile_assessment_payload_redaction.py \
  tests/services/learner_state/test_learning_report_read_model.py \
  -q
```

- [ ] Run frontend gates:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
node yousenwebview/tests/test_package_assessment_contract.js && \
node yousenwebview/tests/test_assessment_testset_view_model.js
```

- [ ] Run contract guard:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
python scripts/check_contract_guard.py
```

- [ ] Run artifact safety:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor && \
git ls-files artifacts/
```

- [ ] Run WeChat DevTools manual gate:
  - open `yousenwebview/packageDeeptutor`
  - start approved P0A topic diagnostic
  - answer all questions with at least one wrong answer
  - submit
  - verify no pre-submit answer reveal occurred
  - verify result shows score, wrong items, simple explanation, and knowledge map
  - verify deep explanation is hidden/disabled
  - verify learning report either reflects new evidence or shows a clear degraded reason

Acceptance:

- All PRD §13 gates have concrete evidence.
- Any failed gate is reported with exact command/output and no silent workaround.

### Task 16: Minimal Observability And Degraded Recovery

**Files:**

- Modify: `deeptutor/services/assessment/report_read_model.py`
- Modify: `deeptutor/services/assessment/session_repository.py`
- Modify: `deeptutor/services/assessment/writeback.py`
- Test: narrow additions to `tests/services/assessment/test_session_repository.py` and `tests/services/assessment/test_writeback.py`

- [ ] Emit structured log fields for:
  - `assessment_session_started`
  - `assessment_session_resumed`
  - `assessment_session_submitted`
  - `assessment_session_scored`
  - `assessment_writeback_degraded`
  - `assessment_writeback_retry_succeeded`
  - `assessment_lease_taken_over`
- [ ] Include non-PII fields per event (subset depending on event semantics):
  - `quiz_id`
  - `assessment_type`
  - `blueprint_version`
  - `form_id`
  - `topic_ids`
  - `delivered_count`
  - `answered_count`
  - `scored_count`
  - `measurement_confidence`
  - `writeback_status`
  - `degraded_reason` (when present)
  - `trace_id` (propagated from request context; if absent, generate per-request and log so traces can be stitched even without Langfuse)
- [ ] Do not log learner answers, correct answers, raw stems, or hidden grading artifacts.
- [ ] Provide a `retry_writeback(quiz_id)` admin path (service-level, not exposed to learner clients) that idempotently re-runs the writeback for a `degraded` session and flips status back to `scored` only when all targets ack. Idempotency uses the same `submit_idempotency_key`; learner events are deduped by the existing `dedupe_key`.
- [ ] Surface `degraded_reason` in the result report payload so the result page can render a clear learner-safe message rather than a generic error.

Acceptance:

- Production can debug P0A abandon/submit/writeback failures without exposing answer content.
- A `degraded` session is recoverable: retry succeeds without producing duplicate learner events or duplicate mistake-book rows.
- Logs carry enough fields to compute the PRD §14 metric set (start/submit/abandon/resume/scoring-error/learning-evidence-write/mistake-book/low-confidence rates) **except** `assessment_to_training_intent_rate` and `assessment_deep_explanation_click_rate`, which depend on synthesis/explanation paths deferred from P0A. The deferred metrics must be explicitly listed in the milestone report as "not measured in P0A".

## 6. PRD §13 Gate Mapping

| PRD gate | Evidence |
| --- | --- |
| `deferred_feedback_gate` | `tests/api/test_mobile_assessment_payload_redaction.py` + JS pre-submit fixture |
| `complete_session_gate` | `tests/services/assessment/test_testset_assembly.py` |
| `resume_gate` | `tests/services/assessment/test_session_repository.py` + API resume test |
| `submit_idempotency_gate` | `tests/services/assessment/test_writeback.py` + `test_submit_idempotency_key_is_server_derived_and_stable_across_retries` + `test_different_submit_body_with_same_quiz_id_returns_409_with_stable_error_code` |
| `simple_report_gate` | `tests/api/test_mobile_router.py` + JS result view-model test |
| `deep_explanation_gate` | P0A hidden/disabled CTA test; working endpoint remains Phase 2 |
| `learning_evidence_gate` | `tests/services/assessment/test_writeback.py` |
| `mistake_book_gate` | `tests/services/assessment/test_writeback.py` using `MistakeBookService` boundary |
| `report_read_model_gate` | `tests/services/learner_state/test_learning_report_read_model.py` or a narrow extension |
| `confidence_gate` | `tests/services/assessment/test_scoring.py` |
| `p0a_scope_gate` | Phase 0 signoff packet + JS copy invariants test + Task 8 copy lock |
| `durability_gate` | repository tests + approved Supabase migration/RLS review + §1.3 migration ownership chain evidence |
| `payload_redaction_gate` | recursive forbidden-key snapshot + structural fuzz substring check |
| `copyright_copy_gate` | Phase 0 signoff packet |
| `cost_gate` | no working deep explanation path in P0A |
| `a11y_baseline_gate` | JS/WXML semantic checks plus manual gate notes before broad release |
| `device_lease_gate` | repository lease/heartbeat/take-over tests + JS second-device read-only banner test |
| `dedupe_gate` | `test_create_returns_existing_in_progress_for_same_user_topic_blueprint` + Task 9 rate-limit test |
| `degraded_recovery_gate` | Task 16 retry test + result page degraded panel rendering test |
| `report_schema_version_gate` | Result report read model rejects unknown `schema_version`; current writer pins `"p0a-v1"` |
| `error_code_registry_gate` | All emitted `error_codes` exist in `ERROR_CODE_REGISTRY`; `scripts/check_contract_guard.py` clean |

## 6.1 PRD Requirement Coverage Matrix

| PRD requirement | Covered by this plan | Notes |
| --- | --- | --- |
| P0A topic diagnostic | Yes | Phase -1/0/1 |
| Deferred feedback | Yes | Redaction tests and yusen pre-submit tests |
| Durable active/submitted sessions | Yes | Repository + migration design/apply gate + §1.3 ownership chain |
| Per-item learning evidence | Yes | Writeback service |
| Aggregate assessment event retained | Yes | Writeback service, but demoted from mastery authority |
| Mistake-book writeback | Yes | Writeback service |
| Session-local next action | Yes | Report read model; no `training_intent` mutation |
| Simple report | Yes | Report read model + yusen result |
| Device lease + multi-device policy | Yes | §2.1.1 + Task 10 lease/take-over/heartbeat tests + JS read-only banner |
| Server-wins draft conflict resolution | Yes | Task 10 server-wins draft test |
| Submit idempotency (server-derived key) | Yes | §2.1 schema + Task 10 idempotency tests |
| Create dedupe / rate limit | Yes | Task 9 dedupe + rate-limit tests |
| Degraded mode recovery | Yes | Task 16 retry + result-page degraded panel |
| Result report schema versioning | Yes | §2.1.2 + Task 13 dispatch on `schema_version` |
| Backward compatibility for legacy diagnostic clients | Yes | Task 9 legacy-client fixture test |
| `error_codes` registry discipline | Yes | Task 12 + Hard Gate #12 + Task 8 lock |
| Image/figure-bearing items | Partially | Phase -1 coverage filter excludes items without alt text; Task 14 a11y gate; deep figure renderer remains Phase 2 |
| Cross-year duplicate items | Yes | Coverage audit + assembly test dedupes by `source_question_id` and (when available) `semantic_signature` |
| Deep explanation | No, intentionally deferred | Hidden/disabled CTA only in P0A |
| Real exam mini simulation | No, intentionally deferred | Separate P0B plan |
| Mastery check | No, intentionally deferred | Separate P1 plan |
| Subjective full case scoring | No, intentionally deferred | Separate P2 plan |
| Adaptive assessment | No, intentionally deferred | Separate P2 plan |
| Authoring/QTI/import standards | No, intentionally deferred | Separate authoring/standards plan |
| A11y baseline | Partially | Defined as broad-release gate; minimal P0A semantic/copy checks included |
| Metrics/baseline dashboard | Partially | Task 16 logs cover 8/10 PRD §14 metrics; `assessment_to_training_intent_rate` and `assessment_deep_explanation_click_rate` deferred with explicit milestone-report note |

## 7. Milestone Stop Reports

After each milestone, report:

1. Files created/modified and line counts.
2. Full stdout for targeted pytest/Node commands.
3. PRD §13 gates completed, blocked, or deferred with evidence.
4. `git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor status --short`.
5. Deviations from PRD and reason.
6. Decisions required before next milestone.

No commit is made unless the user explicitly approves exact staged paths.

## 8. Source Compiler Interlock

This Assessment TestSet plan does not depend on source-compiler PR-2/PR-3. If the source taxonomy file becomes readable during this work, pause only at a milestone boundary and resume the source-compiler plan in its own scope:

- `docs/plan/2026-05-24-luban-2026-source-knowledge-compiler-execution-plan-v0-2.md`
- PR-2: Task 2, 3.0, 3, 4, 4.5, 5, 6, 7, 7.5
- PR-3: Task 10, 11, 12; Task 9 remains apply-refusing
- Task 13 remains out of scope

Do not mix compiler implementation files into the Assessment TestSet milestone report.

## 9. Future Execution Plans After P0A

Write these only after P0A Phase 1 gates are green or a product decision explicitly reprioritizes them.

### 9.1 P0B Real Exam Mini Simulation

Entry criteria:

- P0A durable sessions green.
- P0A redaction/idempotency/writeback green.
- Source provenance can distinguish `REAL_EXAM_OFFICIAL`, `REAL_EXAM_STYLE`, and internal practice.

Must cover:

- mini simulation blueprint,
- exam-style copy and copyright authority,
- timer policy,
- score interpretation that avoids official-exam overclaim,
- form rotation and repeat-session rules.

### 9.2 P1 Mastery Check And Deep Explanation

Entry criteria:

- `training_intent` and study-plan projection consume assessment evidence.
- attempt refs and report read model are stable.
- cost model for explanation generation is approved.

Must cover:

- mastery-check blueprint from recent weak evidence,
- deep explanation cache keyed by `assessment_session_id + question_id + result_hash`,
- unified `/api/v1/ws` question lifecycle context,
- no score mutation after explanation,
- retry/cost/rate-limit policy.

### 9.3 P2 Subjective Case And Adaptive Assessment

Entry criteria:

- rubric coverage and grading confidence are measurable.
- item analytics have enough sample size for difficulty/discrimination hooks.
- product agrees on confidence and score-comparability language.

Must cover:

- structured/full subjective case scoring,
- partial-credit policy,
- human-review/degraded flags,
- adaptive routing,
- item exposure and anomaly detection.

### 9.4 Phase 4 Standards And Authoring

Entry criteria:

- learner-facing delivery has proven retention and trust.
- authoring workflow owner is named.
- import/export standards are a business requirement, not speculative architecture.

Must cover:

- teacher/admin authoring,
- QTI-like import/export if needed,
- item lifecycle and review workflow,
- copyright/provenance approval,
- analytics for item quality.
