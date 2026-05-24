# Assessment TestSet P0A Reality Check

**Date:** 2026-05-24  
**Mode:** Phase -1 only; read-only audit plus local test gate.  
**Canonical PRD:** `docs/plan/2026-05-24-luban-assessment-testset-module-prd.md`  
**Execution plan:** `docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md`  
**Decision:** P0A must not enter Phase 1 yet. Phase -1 found real authority blockers that need explicit design resolution.

## Karpathy Gate

**Assumptions**

- P0A means one deferred-feedback topic diagnostic TestSet, not P0B real-exam simulation or Phase 2 deep explanation.
- `questions_bank` remains the question source authority.
- `AssessmentBlueprintService` remains the blueprint/form authority.
- `learner_memory_events` plus the existing learning-report read model remain the learning evidence authority.
- Result-page next action is session-local and must not mutate `training_intent`.

**Simplest Path**

1. Keep existing `/api/v1/mobile/assessment/create` and `/api/v1/mobile/assessment/{quiz_id}/submit` as thin wrappers.
2. Add a P0A-specific blueprint only after coverage and teaching signoff.
3. Move production session authority from member-console JSON to Supabase `assessment_sessions`.
4. Score deterministically from server private session artifacts.
5. Write per-item `learning_evidence` and mistake-book refs idempotently.
6. Render result from a versioned report read model.

**Change Boundary**

- Created Phase -1 audit/test files and worktree-authority docs:
  - `MIGRATION.md`
  - `docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md`
  - `docs/plan/INDEX.md`
  - `scripts/audit_assessment_testset_p0a.py`
  - `tests/api/test_mobile_assessment_payload_redaction.py`
  - this QA report
- No runtime feature code was changed.
- No Supabase writes were performed.
- No migration file was created.
- `docs/plan/INDEX.md` was updated after the worktree authority was moved to the independent clean clone.

**Verification Target**

- Current surface audit recorded.
- Topic coverage audit produced read-only artifacts.
- Payload redaction baseline test added and green.
- Durable session schema design captured for review.
- Authority blockers explicitly named before Phase 0/1.

## Worktree Safety

Command:

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524 && pwd
git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524 rev-parse --show-toplevel
git -C /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524 status --short --branch
```

Observed:

```text
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524
## codex/p0a-assessment-testset-migration-20260524...origin/main
 M docs/plan/INDEX.md
?? MIGRATION.md
?? docs/plan/2026-05-24-luban-assessment-testset-p0a-execution-plan.md
?? docs/qa/2026-05-24-assessment-testset-p0a-reality-check.md
?? scripts/audit_assessment_testset_p0a.py
?? tests/api/test_mobile_assessment_payload_redaction.py
```

**Finding:** Hard Gate #8 is cleared only in the independent clean clone. The old `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor` directory remains disabled for Git commands and must not be used for staging, commit, or deploy.

## Task 1: Current Surface Audit

Command:

```bash
rg -n "assessment/(create|profile|[^/]+/submit)|createAssessment|submitAssessment|assessment_type|quiz_id" \
  deeptutor/api/routers/mobile.py \
  yousenwebview/packageDeeptutor \
  wx_miniprogram
```

Findings:

- Backend assessment surface:
  - `GET /api/v1/mobile/assessment/profile`
  - `POST /api/v1/mobile/assessment/create`
  - `POST /api/v1/mobile/assessment/{quiz_id}/submit`
- `AssessmentCreateRequest` accepts `assessment_type`, but `mobile.py` currently passes only `count` to `MemberConsoleService.create_assessment`.
- `yousenwebview/packageDeeptutor` and `wx_miniprogram` both still use the existing create/submit endpoints.
- Both frontend clients call `createAssessment("diagnostic", 20)` today.
- No duplicate assessment WebSocket or second assessment route surface was found in the audited paths.

Current response gaps:

- Submit result has aggregate score and diagnostic feedback only.
- No durable report endpoint.
- No per-item wrong item list.
- No attempt refs.
- No per-item `learning_evidence` writeback.
- No device lease/resume contract.

## Task 2: Topic Granularity And Coverage Audit

Blueprint facts from `deeptutor/services/assessment/blueprint.py`:

```text
foundation_deep_foundation 地基基础 / 深基坑 2 地基基础,深基坑
main_structure 主体结构 / 混凝土 / 钢筋 3 主体结构,混凝土,钢筋
waterproof_decoration_mep 防水 / 装饰 / 机电 3 防水,装饰,机电
formwork_safety 模板脚手架 / 安全管理 2 模板,脚手架,安全
planning_schedule 施工组织 / 网络计划 2 施工组织,网络计划,进度计划
claim_quality_acceptance 合同索赔 / 质量验收 2 索赔,质量验收,合同
comprehensive_application 综合案例 / 计算 2 综合案例,计算,网络计划,索赔
learning_habits 学习习惯 2 review_rhythm,planning_style,error_review_style
pressure_state 心理/状态 1 pressure_response,frustration_recovery
teaching_preferences 教学偏好 1 explanation_density, hint_style, practice_mode
```

**Finding:** current production blueprint has only the composite section `waterproof_decoration_mep`; it does not have an independent `waterproof` topic-diagnostic blueprint.

Read-only audit commands:

```bash
python scripts/audit_assessment_testset_p0a.py --run-id p0a-phase-minus-1 --topic waterproof --read-only
python scripts/audit_assessment_testset_p0a.py --run-id p0a-phase-minus-1 --topic waterproof_decoration_mep --read-only
```

Stdout:

```text
topic=waterproof candidates=391 eligible=159 recommendation=12 out=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524/artifacts/assessment_testset/p0a/p0a-phase-minus-1
topic=waterproof_decoration_mep candidates=744 eligible=285 recommendation=12 out=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524/artifacts/assessment_testset/p0a/p0a-phase-minus-1
```

Artifacts:

- `artifacts/assessment_testset/p0a/p0a-phase-minus-1/coverage.json`
- `artifacts/assessment_testset/p0a/p0a-phase-minus-1/coverage.md`
- `artifacts/assessment_testset/p0a/p0a-phase-minus-1/candidate_review.csv`
- topic-specific `coverage_<topic>.json`, `coverage_<topic>.md`, `candidate_review_<topic>.csv`

Coverage summary:

| Topic | Candidates | Eligible | Recommendation | Answer key | Options | Knowledge node | Simple explanation | Long stem | Figure ref | Table ref |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `waterproof` | 391 | 159 | 12 | 391 | 185 | 382 | 391 | 43 | 55 | 5 |
| `waterproof_decoration_mep` | 744 | 285 | 12 | 744 | 328 | 733 | 744 | 89 | 79 | 28 |

Recommendation:

- Content coverage is sufficient for an independent `waterproof` P0A pool: 159 eligible candidates is well above the 12-item delivery target and 2x/3x buffer.
- Product should split a P0A `waterproof` topic diagnostic instead of pivoting copy to the existing `waterproof_decoration_mep` composite.
- Phase 0 still needs teaching signoff on exact section distribution and exclusion policy. Current coverage only proves candidate availability.

Task 2.5 authoring backlog:

- Not needed for P0A based on current read-only coverage.
- If teaching later rejects enough candidates that the eligible pool falls below 24, Task 2.5 reactivates.

## Task 3: Payload Redaction Baseline

Created test:

- `tests/api/test_mobile_assessment_payload_redaction.py`

Command:

```bash
PYTHONPATH=. pytest tests/api/test_mobile_assessment_payload_redaction.py -q
```

Stdout:

```text
....                                                                     [100%]
4 passed in 1.40s
```

Finding:

- Current `member_service.create_assessment(...)` payload is already redacted for pre-submit answer/grading fields.
- Current mobile create route response is also redacted.
- The test includes fixed forbidden keys and substring fuzz for `answer`, `grading`, `rubric`, `scoring_point`, and `correct`.

Status:

- `payload_redaction_gate` baseline is green for create payloads.
- Resume/report payloads are not implemented yet and remain Phase 1 gates.

## Task 4: Durable Session Schema Design

Code facts:

- `MemberConsoleService.__init__` sets `self._data_path = self._path_service.get_settings_file("member_console")`.
- `create_assessment` stores sessions under `data.setdefault("assessment_sessions", {})[quiz_id]`.
- `_load_data` / `_save` use local JSON file IO with a process-local lock.
- `is_production_environment()` currently affects the question provider choice, not assessment session persistence.

Conclusion:

- Current `assessment_sessions` are single-instance JSON state.
- This is not durable under multi-worker/container/pod movement.
- P0A production is blocked until Supabase-backed `assessment_sessions` exists and passes owner/RLS/idempotency tests.

Reviewed schema design, no SQL file yet:

| Column | Type | Purpose |
| --- | --- | --- |
| `session_id` | uuid primary key | Stable quiz/session identity |
| `user_id` | text not null | Owner and RLS boundary |
| `assessment_type` | text not null | P0A uses `topic_diagnostic` |
| `subject_id` | text not null | P0A uses `construction_exam` |
| `topic_ids` | text[] not null | e.g. `{waterproof}` |
| `blueprint_version` | text not null | Signed blueprint identity |
| `form_id` | text not null | Reproducible delivered form |
| `status` | text not null | `in_progress`, `submitted`, `scored`, `degraded`, `expired` |
| `schema_version` | text not null | initial `assessment_session_v1` |
| `client_questions_public` | jsonb not null | Redacted pre-submit payload |
| `session_questions_private` | jsonb not null | Server-only answer/grading artifacts |
| `draft_answer_snapshot` | jsonb | Optional server draft |
| `submitted_answer_snapshot` | jsonb | Immutable submitted answers |
| `submit_idempotency_key` | text | Server-derived hash of user/session/submitted snapshot |
| `result_report_json` | jsonb | Replayable report; must include `schema_version: "p0a-v1"` |
| `result_report_hash` | text | Drift detection |
| `learning_event_refs` | jsonb | Per-item evidence refs |
| `mistake_book_refs` | jsonb | Wrong-item writeback refs |
| `degraded_reason` | text | `writeback_failed`, `scoring_partial`, `source_redaction_failed`, `lease_conflict`, `unknown` |
| `device_id` | text | Active lease holder |
| `lease_expires_at` | timestamptz | Default now + 30 minutes, renewed by heartbeat |
| `lease_history` | jsonb not null default `[]` | Append-only take-over audit |
| `created_at` | timestamptz not null default now() | Creation time |
| `submitted_at` | timestamptz | Submit time |
| `scored_at` | timestamptz | Scoring success time |
| `expires_at` | timestamptz not null | Default created + 24h |
| `created_trace_id` | text | Observability stitch field |
| `updated_at` | timestamptz not null default now() | Last mutation time |

Indexes and constraints to include in the reviewed migration:

- Primary key on `session_id`.
- Index on `(user_id, status, created_at desc)`.
- Index on `(user_id, assessment_type, blueprint_version)`.
- Unique partial index for active formal sessions: `(user_id, assessment_type, subject_id, blueprint_version, topic_ids)` where `status='in_progress'`.
- Check constraint for known statuses.
- Check constraint for `result_report_json->>'schema_version' = 'p0a-v1'` when report is present.
- Unique index on `submit_idempotency_key` where not null.

RLS sketch:

- Enable RLS on `assessment_sessions`.
- Owner can select rows where `user_id` equals authenticated user id.
- Owner can insert rows only for self.
- Owner can update only own `in_progress` rows before submit.
- Submitted/scored/degraded writeback fields are updated only by server-side service role or RPC guarded by owner and idempotency checks.
- No client can select `session_questions_private`; production API must project redacted fields, not return raw table rows.

Migration ownership status:

- Phase -1 design captured here.
- `supabase/migrations/*assessment_sessions.sql` not created.
- Apply approval line: **pending user review**.

## Task 5: Last Assessment And Learner-State Authority Audit

Command:

```bash
rg -n "last_assessment" deeptutor/ web/ wx_miniprogram/ yousenwebview/
```

Classification:

| Code area | Classification | Risk |
| --- | --- | --- |
| `member_console/service.py:599` default `last_assessment` | stale compatibility path | low |
| `member_console/service.py:3727-3782` `_last_assessment_mastery_items` and `_report_mastery_items` | profile/report seed | high |
| `member_console/service.py:4403-4476` `get_assessment_profile` reads score/mastery/diagnostic feedback from `last_assessment` | mastery authority risk | high |
| `member_console/service.py:4689` submit updates `member["chapter_mastery"]` from assessment result | long-term mastery authority risk | blocker |
| `member_console/service.py:4707` submit writes aggregate `last_assessment` | aggregate display plus stale compatibility | medium |
| `learning_report_read_model.py:1503` reads `assessment_profile.chapter_mastery` into radar dimensions | downstream mastery projection risk | blocker |

Hard Gate #3 status:

- **Blocked.** Existing diagnostic submit promotes aggregate assessment result into `member["chapter_mastery"]`, and learning report can consume assessment profile chapter mastery as radar/mastery input.
- P0A must not reuse this path as-is.
- Phase 1 must either demote legacy `last_assessment`/`chapter_mastery` to display-only compatibility for P0A or route P0A mastery through per-item `learning_evidence` and the learning-report read model.

Learner-state command:

```bash
rg -n "source_feature == .construction_grading.|memory_kind == .learning_evidence.|assessment_testset|read_learning_evidence" \
  deeptutor/services/learner_state
```

Findings:

- `LearnerStateService.list_learning_evidence_events` can list `memory_kind == "learning_evidence"` when payload `event_type == "learning_evidence"` or source feature is `construction_grading`.
- `learning_synthesis.py` currently defines learning evidence as `source_feature == "construction_grading" and memory_kind == "learning_evidence"`.
- Supabase store has read helpers for learning evidence, but synthesis source filtering would ignore `assessment_testset` unless patched.

Hard Gate #4 status:

- **Blocked for Phase 1 writeback until a minimal authority patch is approved.**
- Recommended fix: accept `source_feature in {"construction_grading", "assessment_testset"}` when `memory_kind == "learning_evidence"` and payload `event_type == "learning_evidence"`, while preserving provenance in the event payload.
- Do not write `training_intent` from submit.

## Task 5.5: Auth, Ownership, And Abuse Audit

Auth facts:

- `assessment_profile`, `assessment_create`, and `assessment_submit` all call `_resolve_authenticated_user_id`.
- Missing/invalid auth should be rejected by mobile router before service call.

Owner-check gap:

- `MemberConsoleService.submit_assessment(user_id, quiz_id, ...)` currently loads by `quiz_id` and does not verify `session["user_id"] == user_id`.
- Current local JSON store therefore permits cross-user submit if a caller knows another `quiz_id`.

Required Phase 1 tests:

- user A cannot resume user B session.
- user A cannot submit user B session.
- missing/invalid auth cannot create formal P0A session.
- duplicate submit with the same body returns the original result.
- duplicate submit with a different body returns 409 with stable error code.
- expired session returns explicit `expired` or `degraded` state.
- second create for the same active P0A returns existing in-progress session instead of creating another.

## Phase -1 Decision Register

| Decision | Status | Evidence |
| --- | --- | --- |
| Topic | Recommend independent `waterproof` | 159 eligible candidates, no authoring backlog needed |
| Count | 12 is feasible by coverage | Teaching signoff still required |
| Existing blueprint | Must add a P0A blueprint after signoff | current only has composite `waterproof_decoration_mep` |
| Session durability | Production blocked until Supabase `assessment_sessions` | current JSON single-instance state |
| Payload redaction | Create payload baseline green | 4 pytest tests passed |
| `last_assessment` authority | Blocker | aggregate/chapter mastery currently feeds downstream profile/report |
| `assessment_testset` evidence | Blocker | synthesis only recognizes `construction_grading` evidence today |
| Migration apply | Not approved | schema design captured, SQL file not created |
| Training intent | Must not be mutated by submit | use session-local next action only |

## Phase 0 Entry Conditions

Phase 0 may start only after:

1. User reviews and accepts this Phase -1 report.
2. Worktree authority is clarified or the user explicitly accepts that git evidence remains unreliable until later.
3. Product/teaching signs the independent `waterproof` topic decision or chooses the composite fallback.
4. Engineering approves the minimal learner-state evidence-source patch strategy.
5. Engineering accepts the `last_assessment` demotion/read-model strategy for P0A.

## Phase 0: Coverage Dry-Run And Signoff Packet

Phase 0 read-only command:

```bash
python scripts/audit_assessment_testset_p0a.py \
  --run-id p0a-phase-0 \
  --topic waterproof \
  --read-only \
  --emit-form-preview
```

Stdout:

```text
topic=waterproof candidates=391 eligible=159 recommendation=12 out=/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524/artifacts/assessment_testset/p0a/p0a-phase-0
```

Artifacts:

- `artifacts/assessment_testset/p0a/p0a-phase-0/coverage_waterproof.json`
- `artifacts/assessment_testset/p0a/p0a-phase-0/coverage_waterproof.md`
- `artifacts/assessment_testset/p0a/p0a-phase-0/candidate_review_waterproof.csv`
- aggregate `coverage.json`, `coverage.md`, and `candidate_review.csv`

Dry-run summary:

| Topic | Candidates | Eligible | Recommendation | Answer key | Options | Knowledge node | Simple explanation | Long stem | Figure ref | Table ref |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `waterproof` | 391 | 159 | 12 | 391 | 185 | 382 | 391 | 43 | 55 | 5 |

Deterministic preview IDs:

| Source question ID | Type | Source type | Node code | Stem chars |
| --- | --- | --- | --- | ---: |
| 12225 | multi_choice | REAL_EXAM | 1A412000 | 108 |
| 12236 | multi_choice | REAL_EXAM | 1A411000 | 47 |
| 12457 | multi_choice | REAL_EXAM | 1A413080 | 111 |
| 12641 | multi_choice | REAL_EXAM | 1A413020 | 76 |
| 12686 | multi_choice | REAL_EXAM | 1A411020 | 134 |
| 12839 | multi_choice | REAL_EXAM | 1A411023 | 90 |
| 12846 | multi_choice | REAL_EXAM | 1A413012 | 49 |
| 12888 | multi_choice | REAL_EXAM | 1A414010 | 45 |
| 13793 | multi_choice | REAL_EXAM | 1A412000 | 54 |
| 13812 | single_choice | REAL_EXAM |  | 19 |
| 13824 | multi_choice | REAL_EXAM |  | 24 |
| 13867 | single_choice | REAL_EXAM |  | 22 |

Important interpretation:

- This preview is a **candidate review packet**, not the final signed form.
- The first deterministic preview is heavily `REAL_EXAM` biased and includes three candidates with blank `node_code`; teaching/product should either approve that source policy or request source mix/knowledge-node balancing before Phase 1.
- Items with figure/table references or long stems were excluded from eligible preview; this keeps P0A mobile-safe until image/table rendering is formally verified.
- `candidate_review_waterproof.csv` contains broader candidate IDs for manual replacement if teaching rejects any preview item.

### Teaching/Product Signoff Packet

| Item | Proposed value | Signoff status |
| --- | --- | --- |
| User-visible topic label | `防水专题测评` | pending |
| Internal topic id | `waterproof` | pending |
| Assessment type | `topic_diagnostic` | pending |
| Subject id | `construction_exam` | pending |
| Delivered count | 12 | pending |
| Source policy label | `专项测评` or `真题样式专项测评` | pending |
| Copyright/provenance copy | Do not call it `官方真题`; use source-safe wording until provenance authority signs | pending |
| Mobile exclusion policy | Exclude figure/table/long-stem candidates from P0A | pending |
| Section distribution | TBD by teaching; dry-run only proves candidate availability | pending |
| Deep explanation | Hidden/disabled in P0A | locked |
| Result score copy | `本次专题测评得分` | pending |
| Training plan copy | Must not say `长期学习计划已更新` | locked |

### Phase 0 Entry Lock

Phase 1 remains blocked until the following are explicitly approved:

1. Teaching/product signoff for the table above.
2. Engineering decision for `last_assessment` demotion: P0A must not update `member["chapter_mastery"]` as long-term mastery authority.
3. Engineering decision for `assessment_testset` evidence consumption: either extend `learning_synthesis.py` to accept canonical assessment evidence or route through an existing canonical writer while preserving provenance.
4. Migration approval for `assessment_sessions` schema design in Task 4.
5. Confirmation that `result_report_json.schema_version` is locked to `p0a-v1`.

## Phase 1 Hard Stop Conditions Still Active

- No Supabase migration apply without explicit approval.
- No P0A feature code should reuse member-console JSON as production session authority.
- No P0A report should claim "全科能力分", "长期学习计划已更新", or "已掌握".
- No deep explanation implementation in P0A.
- No `training_intent` mutation from assessment submit.
- No client payload may include hidden answer/grading artifacts before submit.
