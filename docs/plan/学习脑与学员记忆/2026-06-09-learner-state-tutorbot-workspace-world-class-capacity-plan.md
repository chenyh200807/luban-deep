# LearnerState / TutorBot Workspace World-Class Capacity Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LearnerState, Learning Brain, TutorBot runtime sandbox/session memory, and Bot-Learner Overlay safe for 50,000+ members without duplicate learner truth, unbounded local files, or runtime capacity collapse.

**Architecture:** `LearnerStateService` remains the single authority for long-term learner truth keyed by `user_id`. The old "TutorBot workspace as independent learning space" interpretation is retired: TutorBot retains only `BotProfile`, `SessionStore`, and `RuntimeSandbox` responsibilities. `bot_id + user_id` overlay is a bounded local-difference layer that can only promote into LearnerState through one promotion pipeline. Supabase/Postgres is the production durable store; local JSONL is write-ahead/dev fallback, never a production reader authority.

**Tech Stack:** Python, FastAPI `/api/v1/ws`, Supabase/Postgres/PostgREST, learner-state services, TutorBot session manager, overlay service, outbox, pytest, contract guards, BI/observability.

---

## 0. Status And Scope

Status: `Proposed / capacity-hardening plan`.

This plan sits under the existing `学员长期状态`, `学习事实编译 / Evidence-first Memory`, and `Bot-Learner Overlay` mainlines. It does not create a fourth learner-memory architecture.

### Non-goals

- Do not create a per-student knowledge compiler workspace.
- Do not copy textbook/rubric/runtime_supply bundles per user.
- Do not make TutorBot workspace memory a learner-state authority.
- Do not create per-member `PROFILE/SUMMARY/PROGRESS/COMPILED_TRUTH` workspace truth.
- Do not preserve `TutorBot workspace` as a first-class business concept; preserve only runtime sandbox capabilities.
- Do not introduce a new chat route or a new learner memory table unless a measured query/capacity gate proves current tables cannot support the workload.
- Do not optimize capacity by skipping grading validators, RAG authority, writeback eligibility, or promotion gates.

## 0.1 2026-06-09 Retraction And Rename

This plan records a deliberate requirement correction:

Retired interpretation:

```text
Every new member gets an independent long-term memory workspace.
Every TutorBot workspace may keep its own learner profile, summary, progress, mastery, or compiled truth.
```

Correct interpretation:

```text
Every member may have an owner-scoped LearnerWorkspace for user assets.
LearnerStateService is the only long-term learner truth authority.
TutorBot keeps BotProfile, SessionStore, and RuntimeSandbox only.
```

Canonical concept map:

| Concept | Owns | Must not own |
|---|---|---|
| `LearnerState` | evidence ledger, profile, summary, progress, weak points, mastery, retest change, next action | free-form bot guesses, raw workspace notes as truth |
| `SessionStore` | session history, channel conversation continuity, replay | learner profile/progress truth |
| `BotProfile` | persona, teaching style, skill binding, channel binding | learner state |
| `LearnerWorkspace` | notes, attachments, bookmarks, exports, visible projections | compiled truth, recommendation authority |
| `RuntimeSandbox` | tool isolation, temporary files, debug artifacts, short cache | durable learner memory |

Migration rule:

```text
TutorBot workspace = retired business concept
TutorBot RuntimeSandbox = allowed technical capability
```

Any future plan or implementation that reintroduces workspace-local learner truth must fail contract review.

## 1. World-Class Bar

The target is not just "storage fits." World-class means:

1. **Single authority:** every learner fact has one writer, one durable store path, and one reader API.
2. **Bounded growth:** raw events can grow, but online reads never scan full history.
3. **Read-your-writes:** a just-written learning evidence event is visible to home/report/context builders even before remote flush completes.
4. **Bot isolation without truth forks:** TutorBot sessions and overlays can personalize behavior but cannot become global mastery/weak-point/profile truth.
5. **Replayable state:** `learner_summaries` and projections can be rebuilt from `learner_memory_events`.
6. **Capacity proven, not assumed:** 50,000-member readiness is demonstrated with synthetic data, indexed queries, load tests, and storage growth reports.
7. **Privacy and retention:** raw events, session logs, and overlay working memory have retention and redaction policies.
8. **Operator visibility:** BI can show learner-state lag, outbox backlog, overlay promotion rate, event growth, read latency, and stale projection risk.

## 2. Authority Model

| Fact | Canonical authority | Durable production store | Runtime use | Forbidden duplicate |
|---|---|---|---|---|
| Stable learner profile | `LearnerStateService` | `user_profiles` | personalization, onboarding, ops view | TutorBot workspace profile copy |
| Long-term progress / weak points | `LearnerStateService` + synthesis | `user_stats` + `learner_summaries` projection | home/report/context | overlay global weak points |
| Raw learning evidence | learner-state writeback pipeline | `learner_memory_events` | evidence ledger, replay, audit | feature-specific memory table |
| Compiled learning truth | synthesis pipeline | `learner_summaries.summary_structured_json.learning_brain` | read-only context | local `COMPILED_TRUTH.json` in production |
| TutorBot session context | `SessionStore` | session JSONL / SQLite adapter / future remote session store | conversation continuity | learner profile/progress truth |
| TutorBot persona / skills / channel | `BotProfile` + Skill / Capability registry | config service / versioned template registry | bot behavior and routing | learner state |
| Tool scratch / execution isolation | `RuntimeSandbox` | bounded temp dirs / artifact store | tool execution safety and debug | durable learner memory |
| Learner visible assets | `LearnerWorkspace` asset services | notebook / attachment / export store | user notes, bookmarks, attachments, projections | mastery, weak points, recommendations |
| Bot-local differences | `BotLearnerOverlayService` | overlay table/file + event audit | local focus, temporary policy, promotion candidates | second learner summary |
| Knowledge/rubric supply | compiler release gate | `runtime_supply` / pinned object storage | shared context pack | per-user copied compiler output |

## 3. Current Baseline

Local checkout observations from 2026-06-09:

- `data/user/learner_state`: about `7.0MB` across `76` top-level local learner-state directories.
- Typical local learner directories are KB-to-low-hundreds-KB; test/demo outliers reach MB scale.
- `deeptutor/services/construction_grading/runtime_supply`: about `22MB`, shared and not user-specific.

These are not production benchmarks. They are enough to show the current risk is not shared compiled bundle size; the risk is unbounded event append, local-file production reads, missing indexes, and overlay/session growth without retention.

## 4. Target Data Shape

### 4.1 Learner Core

Keep production learner core remote-first:

- `user_profiles`: stable profile and preference fields.
- `user_stats`: durable progress projections and home personalization projection.
- `user_goals`: goals and study plan targets.
- `learner_memory_events`: append-only evidence ledger.
- `learner_summaries`: compact learning-brain projection.

Local files may exist only as:

- write-ahead ledger until outbox flush succeeds,
- dev/QA fallback,
- offline dry-run artifact,
- human-readable projection/cache.

### 4.2 Online Read Budget

Online turn context may read:

- latest `learner_summaries.summary_structured_json.learning_brain`,
- latest compact `user_stats` projections,
- bounded recent canonical `learner_memory_events.learning_evidence`,
- bounded effective overlay fields.

Online turn context must not:

- scan all memory events,
- run full synthesis,
- inspect TutorBot session files as learner truth,
- rebuild weak points from free text,
- read local `COMPILED_TRUTH.json` in production.

### 4.3 Storage Budget

Capacity budget for 50,000 members:

| Per-user annual shape | 50,000 users | Interpretation |
|---|---:|---|
| 100KB | 5GB | light usage, trivial |
| 500KB | 25GB | normal active-learning footprint |
| 1MB | 50GB | still manageable with indexed DB |
| 5MB | 250GB/year | heavy users need partitioning, retention, cold archive |

The operational target is not "never exceed X." The target is: online queries remain bounded and raw history can move to cold storage without losing replayability.

## 5. Implementation Phases

### Phase 0: Contract Lock And Inventory

Goal: prove current code does not already have silent competing learner authorities.

Files:

- Read: `contracts/learner-state.md`
- Read: `contracts/index.yaml`
- Read: `deeptutor/services/learner_state/service.py`
- Read: `deeptutor/services/learner_state/supabase_store.py`
- Read: `deeptutor/services/learner_state/overlay_service.py`
- Read: `deeptutor/tutorbot/session/manager.py`
- Read: `deeptutor/services/session/turn_runtime.py`
- Create: `scripts/audit_learner_state_authority.py`
- Test: `tests/scripts/test_audit_learner_state_authority.py`

Tasks:

- [ ] Add an authority audit script that scans for direct reads of `data/user/learner_state`, `COMPILED_TRUTH.json`, TutorBot session files, and overlay files outside approved services.
- [ ] Fail the audit when mobile router, learning-report read model, TutorBot runtime, or BI code bypasses `LearnerStateService` for learner truth.
- [ ] Add allowed-list entries only for path helpers, migration utilities, tests, and explicit dev-only scripts.
- [ ] Verification: `pytest tests/scripts/test_audit_learner_state_authority.py -q`.

Done when:

- One command can detect new learner-state bypasses.
- The audit distinguishes runtime truth reads from dev/test fixtures.

### Phase 1: Remote-First Learner Store Hardening

Goal: make Supabase/Postgres the production durable learner truth while preserving read-your-writes through local write-ahead.

Files:

- Modify: `deeptutor/services/learner_state/supabase_store.py`
- Modify: `deeptutor/services/learner_state/service.py`
- Modify: `deeptutor/services/learner_state/outbox.py`
- Modify: `contracts/learner-state.md` if the implementation exposes a new stable boundary.
- Test: `tests/services/learner_state/test_supabase_store.py`
- Test: `tests/services/learner_state/test_service.py`
- Test: `tests/services/learner_state/test_outbox.py`

Tasks:

- [ ] Add direct indexed readers for event detail and bounded event list: `user_id + event_id + memory_kind`, `user_id + created_at desc`, and dedupe-key lookup.
- [ ] Ensure `LearnerStateService` merges remote rows and local write-ahead rows by `event_id / dedupe_key`, then applies a bounded limit.
- [ ] Ensure production mode fails closed if Supabase core store is required but not configured.
- [ ] Add outbox health fields: pending count, oldest pending age, last flush error class, retry count.
- [ ] Verification: focused learner-state pytest plus a synthetic read-your-writes test where remote flush is delayed.

Done when:

- A just-written event appears in context candidates before remote flush.
- Production read path cannot silently fall back to local `COMPILED_TRUTH.json`.
- Bounded event list never scans full JSONL in production.

### Phase 2: Event Ledger Compaction And Projection Discipline

Goal: keep `learner_memory_events` replayable while making online reads small and stable.

Files:

- Modify: `deeptutor/services/learner_state/learning_brain_read_model.py`
- Modify: `deeptutor/services/learner_state/personalization_context.py`
- Modify: `deeptutor/services/learner_state/home_personalization.py`
- Create: `deeptutor/services/learner_state/event_compaction.py`
- Test: `tests/services/learner_state/test_event_compaction.py`
- Test: `tests/services/learner_state/test_personalization_context.py`

Tasks:

- [ ] Define event quality tiers: canonical, candidate, shadow, conversation_observation, student_note, rejected.
- [ ] Build a compaction read model that keeps recent canonical evidence hot and older raw events replayable but not online-scanned.
- [ ] Add projection hash fields so `learner_summaries` can prove which event set produced the current learning brain projection.
- [ ] Add stale projection rules: if projection is stale, use last valid projection plus starter fallback, not live synthesis.
- [ ] Verification: tests prove shadow/candidate events never enter claims/PCP, and stale projection does not trigger full synthesis during a turn.

Done when:

- `PersonalizationContextPack` is a projection of compiled truth, not a second recommendation engine.
- Old evidence can be archived without breaking current home/report/context reads.

### Phase 3: TutorBot Workspace Retirement Into RuntimeSandbox

Goal: retire TutorBot workspace as a business concept while keeping its useful runtime capabilities as `BotProfile`, `SessionStore`, and `RuntimeSandbox`.

Files:

- Modify: `deeptutor/tutorbot/session/manager.py`
- Modify: `deeptutor/tutorbot/session/sqlite_adapter.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Create: `deeptutor/services/tutorbot/session_retention.py`
- Create: `deeptutor/services/tutorbot/runtime_sandbox.py`
- Test: `tests/tutorbot/test_session_manager.py`
- Test: `tests/services/session/test_tutorbot_sqlite_adapter.py`
- Test: `tests/services/tutorbot/test_runtime_sandbox_boundary.py`

Tasks:

- [ ] Rename documentation and trace labels from "TutorBot workspace memory" to "TutorBot RuntimeSandbox/session cache" where the code is not referring to a literal directory.
- [ ] Move persona / soul, skills, channel config, heartbeat, session history, media, logs, and temp files into their canonical authorities in design docs before code migration.
- [ ] Add retention policy for TutorBot session logs: max retained messages per session, max byte size, and archival marker.
- [ ] Ensure session consolidation outputs are labeled as conversation summary, not learner summary.
- [ ] Block direct promotion from workspace memory to learner profile/progress/summary.
- [ ] Ensure turn runtime reads LearnerState before overlay/workspace and records trace markers for all three inputs.
- [ ] Verification: tests prove TutorBot session memory cannot override learner core fields and does not grow unbounded in synthetic long-session runs.

Done when:

- TutorBot workspace no longer appears as a first-class business authority.
- RuntimeSandbox remains available for tool isolation and temporary artifacts.
- Learner truth only changes through learner-state writeback or promotion pipeline.

### Phase 4: Bot-Learner Overlay Promotion System

Goal: make `bot_id + user_id` overlay powerful enough for personalization but too narrow to become a second learner core.

Files:

- Modify: `deeptutor/services/learner_state/overlay_service.py`
- Modify: `deeptutor/services/learner_state/service.py`
- Test: `tests/services/learner_state/test_overlay_service.py`
- Test: `tests/services/learner_state/test_overlay_promotion.py`

Tasks:

- [ ] Enforce an allow-list schema for overlay fields: local focus, active plan binding, teaching policy override, heartbeat override, working memory projection, channel presence, notebook scope refs, engagement state, promotion candidates.
- [ ] Reject or drop forbidden fields: global profile, summary, progress, goals, mastery, global weak points, consent, account/member facts.
- [ ] Add TTL/decay to all local focus and working memory fields.
- [ ] Add promotion eligibility checks: structured source, user confirmation, or repeated non-conflicting evidence.
- [ ] Add promotion audit: candidate id, source event ids, decision, reviewer/system actor, applied learner-state patch hash.
- [ ] Verification: tests prove overlay empty values do not override learner core, expired fields are filtered, and promotions cannot bypass LearnerStateService.

Done when:

- Overlay can help a specific TutorBot without owning global truth.
- Every promoted fact is auditable and reversible.

### Phase 5: Capacity Harness For 50,000 Members

Goal: replace intuition with measured capacity gates.

Files:

- Create: `scripts/generate_learner_state_capacity_fixture.py`
- Create: `scripts/run_learner_state_capacity_gate.py`
- Create: `artifacts/learner_state_capacity/.gitkeep`
- Test: `tests/scripts/test_learner_state_capacity_gate.py`

Synthetic profiles:

- `50k_registered`: 50,000 users, light profile/progress only.
- `10k_active`: 10,000 users, 30 evidence events each.
- `2k_heavy`: 2,000 users, 1,000 events each, archived history enabled.
- `peak_turn_context`: 200 concurrent context builds.
- `writeback_burst`: 1,000 learning evidence writes/minute.

Metrics:

- context build p50/p95/p99
- event write p50/p95/p99
- outbox pending age
- remote/local merge cost
- DB query count per turn
- bytes read per turn
- projection stale rate
- overlay size and promotion rate
- storage per 1,000 active users

Initial gates:

- context build p95 below 150ms excluding LLM/RAG.
- learner-state write p95 below 250ms excluding remote transient retries.
- online context reads at most 50 recent events per user unless explicitly debugging.
- zero full-history scan in production mode.
- outbox oldest pending below 5 minutes under normal load.
- projected annual storage report produced for 50k and 100k member cases.

Done when:

- Capacity reports can be regenerated locally and in CI-like environments.
- A regression in full-history scans or unbounded overlay growth fails the gate.

### Phase 6: Observability And BI Control Plane

Goal: make learner-state health visible to operators before users notice degradation.

Files:

- Modify: `deeptutor/services/observability/*`
- Modify: `deeptutor/services/bi_service.py`
- Modify: `web` / BI only in a later frontend task after backend metrics exist.
- Test: `tests/services/observability/test_learner_state_metrics.py`
- Test: `tests/services/test_bi_service.py`

Required metrics:

- `learner_state.event_write.count`
- `learner_state.event_write.latency_ms`
- `learner_state.context_build.latency_ms`
- `learner_state.remote_read.error_count`
- `learner_state.outbox.pending_count`
- `learner_state.outbox.oldest_age_s`
- `learner_state.projection.stale_count`
- `learner_state.compiled_truth.source`
- `bot_overlay.applied_count`
- `bot_overlay.promotion_candidate_count`
- `bot_overlay.promotion_applied_count`
- `tutorbot.workspace.retention_trim_count`

Done when:

- BI can answer: "Are learner facts being written?", "Are projections stale?", "Is overlay growing too fast?", "Are local write-ahead events stuck?", and "Did a TutorBot try to promote global truth?"

### Phase 7: Privacy, Retention, And Cost Governance

Goal: make long-term memory trustworthy enough for real users.

Files:

- Create: `docs/runbook/learner-state-retention-and-privacy.md`
- Modify: retention code from Phase 3/4 as needed.
- Test: retention tests added in Phase 3/4.

Rules:

- Raw TutorBot session logs are not eternal by default.
- Learner evidence events are append-only but can be archived to cold storage after projection and audit windows.
- Student notes are low-authority context and never mastery proof.
- PII and account facts never enter learner memory payloads.
- Deletion/export requests must cover learner core, overlay, TutorBot sessions, and write-ahead files.

Done when:

- There is an operator runbook for storage growth, deletion/export, replay, and archive restore.

## 6. Release Gates

### Local Gate

Run:

```bash
pytest tests/services/learner_state tests/tutorbot tests/services/session/test_tutorbot_sqlite_adapter.py -q
python scripts/audit_learner_state_authority.py
python scripts/run_learner_state_capacity_gate.py --profile 10k_active --mode local
```

Expected:

- all tests pass,
- no authority bypass,
- no full-history production scan,
- capacity report emitted.

### Shadow Gate

Run against a staging Supabase project:

```bash
python scripts/run_learner_state_capacity_gate.py --profile 50k_registered --mode supabase-shadow
python scripts/run_learner_state_capacity_gate.py --profile peak_turn_context --mode supabase-shadow
python scripts/run_learner_state_capacity_gate.py --profile writeback_burst --mode supabase-shadow
```

Expected:

- remote-first reads work,
- local write-ahead merge works,
- indexes hold p95 targets,
- outbox drains,
- no TutorBot workspace reader becomes learner truth.

### Production Limited Gate

Scope:

- `qa_` / `operator_` users only at first.
- No broad real-student default until shadow gate is green for 7 days.

Expected:

- `projection_stale_rate < 1%`
- `outbox_oldest_pending_age_s < 300` during normal operation
- `overlay_forbidden_field_rejected_count = 0` after rollout stabilization
- `context_build_p95 < 150ms` excluding LLM/RAG
- no production local `COMPILED_TRUTH.json` reads

## 7. Failure Modes To Prevent

| Failure | Why it is dangerous | Preventive gate |
|---|---|---|
| TutorBot workspace summary overwrites learner summary | creates second learner truth | authority audit + writeback-only rule |
| Overlay stores global weak points | forks mastery/progress | overlay schema reject |
| Online turn runs synthesis | latency/cost explosion | production full-synthesis guard |
| Local JSONL becomes production reader | slow and inconsistent at 50k | remote-first fail-closed |
| Event ledger becomes garbage pile | no actionable learning brain | quality tiers + compaction |
| Promotion silently applies bot guess | contaminates learner truth | promotion eligibility + audit |
| BI/admin writes learner facts directly | bypasses provenance | member-console boundary guard |
| Session logs grow forever | storage/privacy risk | retention trim + archive policy |

## 8. System Complexity Net Change

This plan intentionally adds only three durable concepts:

1. capacity gate,
2. overlay promotion audit,
3. event compaction/read-model discipline.

It explicitly does not add a second learner memory, second TutorBot learner profile, per-student compiler workspace, or new chat route. The net complexity should go down because every future feature has one answer to "where does this fact live?"

## 9. Recommended Execution Order

1. Phase 0 authority audit.
2. Phase 1 remote-first/read-your-writes hardening.
3. Phase 4 overlay schema + promotion guard, because it blocks truth forks.
4. Phase 5 capacity harness, because every later optimization needs a measurement baseline.
5. Phase 2 event compaction.
6. Phase 3 TutorBot session retention.
7. Phase 6 BI observability.
8. Phase 7 privacy and retention runbook.

Do not start broad production learner-truth writes until Phases 0, 1, 4, and the `10k_active` capacity gate are green.
