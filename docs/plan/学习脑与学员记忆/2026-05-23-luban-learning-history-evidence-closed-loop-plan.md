# Luban Learning History Evidence Closed Loop Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the learning module visibly grounded in the learner's historical conversations, mistake evidence, and test outcomes so the report behaves as a learning-state inference and personalized training engine, not a statistics page or generic mistake book.

**Architecture:** Keep `learner_memory_events.learning_evidence` as the single normalized learning fact ledger. Treat WeChat history/session messages as the raw replay authority for "what the system actually explained at that moment", and let attempt detail, mistake clusters, report cards, home prompts and prescriptions cite that evidence instead of inventing summaries. Do not create a second learner memory, a second recommendation authority, a new chat WebSocket, or frontend-derived diagnosis logic.

**Tech Stack:** Python read models under `deeptutor/services/learner_state`, mobile router under `deeptutor/api/routers/mobile.py`, existing session history store, existing `learning_evidence` ledger, shared WeChat view models under `wx_miniprogram` and `yousenwebview/packageDeeptutor`, pytest, Node snapshot/view-model tests.

---

## Root Cause

The current learning-state engine has the right backend spine but the student-facing surfaces still lose the most valuable evidence:

```text
historical assistant answer exists in session history
  -> learning_evidence keeps only a short explanation summary
  -> attempt_detail_read_model reads the short summary only
  -> mini-program shows "B option does not match the standard answer"
```

That breaks the core product promise. A learner does not need another label; they need to see the original system explanation that made the mistake understandable.

The business fact is:

> A learning conclusion is only useful if the learner can trace it to the concrete historical attempt, the answer they gave, the system explanation they saw, and the next training action that verifies improvement.

## Current Reality vs Target Gap

This plan exists because the product is now in an uncomfortable middle state:

| Layer | Current reality | Target state | Gap severity |
| --- | --- | --- | --- |
| Raw history | WeChat history already stores full assistant answers, including rich grading explanations | Attempt detail and learning report can recover the exact explanation for the same turn | P0 |
| Normalized evidence | `learning_evidence` captures answer, correctness, error events, rubric fields and short explanation payloads | Evidence also carries enough turn/session references for replay and clustering | P0 |
| Attempt detail | Page can show question, answer and generic explanation | Page first answers "where did I go wrong / why / what next" with historical assistant explanation | P0 |
| Learning report | State, prescription and mistake cards exist, but can still feel abstract | Every weak-state claim is backed by concrete historical attempts and can open detail | P1 |
| Home prompts | Backend-driven prompt plumbing exists | Prompt copy visibly cites the learner's recent evidence cluster and starts a verification loop | P1 |
| Mistake book | Cloud authority exists | Mistake book is clearly a read/action projection over evidence, not a separate diagnosis source | P1 |
| Teacher/sales story | Evidence story projection exists from the broader inference plan | Story claims cite evidence and never leak raw chat or PII | P2 |

The immediate gap is not "we need a smarter model". It is that the system already has useful historical explanations but the student-facing read path often downgrades them into generic summaries.

## First Principles Restatement

The learning module is a learning-state inference engine only if it preserves this chain:

```text
historical learning event
  -> normalized learning evidence
  -> diagnosis cluster
  -> prescription
  -> verification attempt
  -> updated learning state
```

If any page displays a conclusion without a reachable historical event, it is not a learning-state engine. It is a report card.

If any page shows an action without a backend `training_intent` and evidence refs, it is not personalized training. It is a prompt shortcut.

If any frontend computes weakness, mastery, diagnosis or recommendation copy, it is not thin wrapper / fat skill. It is a second authority.

## Reinforced Scope

This plan is deliberately narrower than the full 2026-05-22 inference-engine plan. It closes the most damaging product gap first: learners must see the historical explanation behind the learning conclusion.

### In Scope

- Recover the exact assistant explanation for an attempt through existing session history.
- Render the recovered explanation in student-readable sections.
- Ensure mistake evidence cards point to concrete attempt detail.
- Keep report/home prompt actions tied to backend `training_intent`.
- Mark missing links as degraded instead of pretending the diagnosis is complete.

### Out of Scope

- New learner memory tables.
- New public endpoints for story projection.
- Frontend-side weak-point ranking.
- BKT / DKT / GNN model introduction.
- Auto-authoring a full knowledge graph.
- Replacing `learning_evidence` with raw chat scanning.
- Using raw private chat in teacher/sales story output.

## Data Flow Contract

The allowed data flow is:

```text
WeChat conversation history / answer submission / test set attempt
  -> grading or conversation synthesis
  -> learner_memory_events.learning_evidence
  -> learning_synthesis / read-model projections
  -> attempt detail / report / home prompt / prescription rendering
```

Attempt detail is the only student surface allowed to replay the raw assistant message, and only for the learner's own attempt. Report and home surfaces should summarize with evidence refs and link into attempt detail, not duplicate raw chat.

## Edge Cases To Design For

1. **Existing evidence without `session_id`**
   - Use bounded owner-session lookup by `turn_id`.
   - If still unresolved, show degraded state: "已保留作答事实，完整历史解析暂不可用".

2. **Multiple assistant messages for one turn**
   - Prefer the latest assistant message whose event metadata matches `turn_id`.
   - Do not concatenate unrelated assistant messages.

3. **Payload summary conflicts with historical explanation**
   - Historical assistant content wins for replay.
   - `learning_evidence` remains the normalized source for correctness, answer, error code and attempt identity.

4. **Historical assistant content contains internal context**
   - Use the same trimming/redaction discipline as conversation history.
   - Never show `[History Context]`, internal request snapshots, trace IDs, event IDs or raw private metadata.

5. **Test-set attempts**
   - Treat test-set answers as learning evidence when they pass quality gate.
   - They should be eligible for mistake clusters and state updates, but attempt detail must still show the original question/answer/explanation chain.

6. **Correct follow-up after a previous mistake**
   - Correct attempts should not disappear. They are verification evidence.
   - The state card should be able to say "previously weak, recently verified once" rather than only "weak".

7. **Conversation-only explanation**
   - Can explain why the learner is confused.
   - Cannot independently verify mastery or prescription completion without an attempt or verification probe.

8. **Teacher/sales usage**
   - Use redacted evidence story projection only.
   - Never export raw learner chat, openid, phone, name or user_id.

## Phased Delivery Upgrade

### Phase 1 - Replay Truth

Goal: attempt detail must faithfully recover "what the system explained at that moment".

Deliverables:

- `attempt_detail_read_model` accepts existing session history store.
- `explanation.full_text` prefers matched historical assistant content.
- Frontend renders structured sections before raw transcript.
- Degraded fallback is explicit when history is missing.

Release gate:

- A real trace like "验槽 / 观察法 / 钎探法" shows the complete explanation, not "B 选项不符合标准答案".

### Phase 2 - Evidence Story On Report

Goal: learning report cards should answer "what evidence proves this state?"

Deliverables:

- Mistake history cards show representative attempts with time, question, learner answer, correct answer, error reason and `attempt_ref`.
- State cards cite 1-3 evidence refs or show degraded state.
- No internal enum labels appear in student copy.

Release gate:

- A learner can start at a weak state card, open a historical attempt, and understand the diagnosis without leaving the mini-program.

### Phase 3 - Prescription And Verification Loop

Goal: actions are not static prompts; they are verification loops.

Deliverables:

- Home prompt and report CTA use backend `training_intent`.
- Training launch carries `training_intent_id` and evidence refs.
- Follow-up attempts produce verification outcomes.
- Report can display "not yet verified / verified once / still recurring".

Release gate:

- Clicking a personalized prompt, answering, and returning to report changes or preserves state based on evidence, not frontend assumptions.

### Phase 4 - Teacher/Sales Projection Hardening

Goal: external-facing explanation tells an evidence-backed story without leaking private data.

Deliverables:

- Story projection cites initial pattern, prescription and verification result.
- All claims have evidence refs.
- PII redaction tests pass.
- Sales summary avoids exaggerated claims like "guaranteed score improvement".

Release gate:

- Teacher/sales story can be reviewed independently and every claim traces back to a student-safe evidence reference.

## Quality Bar

For this plan, "done" means:

- Student can answer:
  1. 我是哪道题错了？
  2. 我当时选了什么？
  3. 系统当时为什么说我错？
  4. 这反映了哪个知识 / 能力 / 行为问题？
  5. 下一步训练如何验证我是否改好了？

- Engineer can answer:
  1. 这条 claim 的 writer 是谁？
  2. 它存在哪里？
  3. 它由哪个 read model 读取？
  4. 如果历史解析缺失，如何 degraded？
  5. 哪个测试锁住了这个行为？

## Operational Metrics

Minimum metrics before broad release:

- `attempt_detail_history_replay_rate`: matched historical assistant explanation / detail opens with `turn_id`.
- `generic_diagnosis_rate`: attempt detail primary explanation equals generic option mismatch text.
- `evidence_card_clickthrough_rate`: report evidence card -> attempt detail open.
- `prompt_to_evidence_rate`: home prompt click -> answered attempt -> learning evidence written.
- `verification_outcome_rate`: prescription launches that reach verified / not_verified.
- `degraded_attempt_detail_rate`: detail opens where full history is unavailable.

Suggested P0 thresholds:

- `generic_diagnosis_rate < 5%` for new attempts.
- `attempt_detail_history_replay_rate >= 80%` for attempts created after this plan ships.
- `prompt_to_evidence_rate >= 70%` for personalized prompt clicks.

## Risks And Mitigations

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Historical messages lack `session_id` | Existing attempts may not replay full explanation | Bounded `turn_id` owner-session lookup, then explicit degraded copy |
| Assistant content contains internal context | Could leak system metadata | Reuse history trimming/redaction; add tests for internal markers |
| Report cards overpromise | Learner loses trust | Require evidence refs or degraded state; no frontend inference |
| More UI text makes page heavy | Learner may not scan it | Put rich explanation in attempt detail; report shows compact evidence story |
| Test-set attempts not normalized | State misses important evidence | Ensure test-set writeback uses same `learning_evidence` quality gate |
| Multiple recommendations compete | System becomes incoherent | `training_intent` remains the only prescription authority |

## Authority Rules

- Raw historical replay authority: existing session history / conversation messages.
- Normalized learning evidence authority: `learner_memory_events.learning_evidence`.
- Student report authority: `learning_report_read_model`.
- Attempt replay authority: `attempt_detail_read_model`.
- Recommendation authority: `training_intent`; frontend only renders it.
- Mistake book authority: cloud mistake-book projection bound to evidence refs.

Forbidden:

- Do not read raw history in the frontend and infer diagnosis there.
- Do not add a second learner-memory table.
- Do not add a public endpoint for teacher/sales story in this plan.
- Do not show raw private chat outside the learner's own attempt detail.
- Do not let fallback prose like "选项不符合标准答案" become the primary diagnosis when rich history exists.

## Implementation Tasks

### Task 1: Attempt Detail Uses Historical System Explanation

**Files:**
- Modify: `deeptutor/services/learner_state/attempt_detail_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Test: `tests/services/learner_state/test_attempt_detail_read_model.py`
- Test: `tests/api/test_mobile_router.py` if router wiring needs coverage

- [x] **Step 1: Write failing test**
  - Create a learning evidence event with generic `payload.explanation`.
  - Create a fake session store whose assistant message for the same `turn_id` contains rich markdown sections: 阅卷结论、正确答案、为什么错、知识点、易错点、记忆口诀、下一步、逐项解析.
  - Assert `build_attempt_detail_read_model(..., session_store=...)` prefers the historical assistant content.

- [x] **Step 2: Verify red**
  - Run: `python -m pytest tests/services/learner_state/test_attempt_detail_read_model.py -q`
  - Expected: FAIL because `session_store` is not accepted or historical assistant content is ignored.

- [x] **Step 3: Minimal backend implementation**
  - Add optional `session_store` to `build_attempt_detail_read_model`.
  - Resolve base `turn_id` from `payload.turn_id`, `event.source_id`, and signed ref context.
  - If `payload.session_id` exists, call existing `session_store.get_session_with_messages(session_id)`.
  - If no `session_id`, use existing owner/session listing only as a bounded read fallback.
  - Match assistant messages by turn metadata and prefer the matched content as `explanation.full_text`.
  - Keep payload summary fallback for legacy evidence.

- [x] **Step 4: Verify green**
  - Run: `python -m pytest tests/services/learner_state/test_attempt_detail_read_model.py -q`
  - Run: `python -m pytest tests/api/test_mobile_router.py -q` if router wiring changed.

- [x] **Step 5: Review**
  - Spec check: no new table, no new event type, no new endpoint.
  - Authority check: history is raw replay source; learning evidence remains normalized fact source.

### Task 2: Attempt Detail Renders Rich Explanation Sections

**Files:**
- Modify: `wx_miniprogram/utils/attempt-detail-view-model.js`
- Modify: `yousenwebview/packageDeeptutor/utils/attempt-detail-view-model.js`
- Modify: `wx_miniprogram/pages/attempt-detail/attempt-detail.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/attempt-detail/attempt-detail.wxml`
- Modify: `wx_miniprogram/pages/attempt-detail/attempt-detail.wxss`
- Modify: `yousenwebview/packageDeeptutor/pages/attempt-detail/attempt-detail.wxss`
- Test: `wx_miniprogram/tests/test_attempt_detail_view_model.js`

- [x] **Step 1: Write failing test**
  - Feed the real "验槽 / 观察法 / 钎探法" rich explanation into the view model.
  - Assert the model exposes ordered sections for 阅卷结论、为什么错、知识点、易错点、记忆口诀、下一步、逐项解析.
  - Assert wx and yousen outputs are deeply equal.

- [x] **Step 2: Verify red**
  - Run: `node wx_miniprogram/tests/test_attempt_detail_view_model.js`
  - Expected: FAIL because `explanationSections` does not exist.

- [x] **Step 3: Minimal frontend implementation**
  - Parse markdown `###` headings from backend `explanation.full_text` or the system turn.
  - Render "系统当时怎么讲清楚的" above the raw conversation transcript.
  - Keep the raw "当时对话" below as evidence replay, not the main explanation.
  - Use student language; do not expose internal enum values.

- [x] **Step 4: Verify green**
  - Run: `node wx_miniprogram/tests/test_attempt_detail_view_model.js`
  - Run: `node yousenwebview/tests/test_report_snapshot_dedupe.js` only if shared report files are touched.

- [x] **Step 5: Review**
  - Spec check: no frontend diagnosis inference; only parsing and rendering backend/history content.
  - UX check: learner sees "where I was wrong / why / what next" before raw transcript.

### Task 3: Report Mistake Evidence Cards Link State To Historical Attempts

**Files:**
- Modify: `wx_miniprogram/utils/learning-report-view-model.js`
- Modify: `yousenwebview/packageDeeptutor/utils/learning-report-view-model.js`
- Modify: `wx_miniprogram/pages/report/report.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.wxml`
- Test: `wx_miniprogram/tests/test_report_view_model.js`

- [x] **Step 1: Write failing test**
  - Build a report fixture with repeated mistake cluster, `attempt_ref`, time label, learner answer, correct answer, and explanation snippet.
  - Assert the report model exposes "错题历史怎么证明" cards with concrete attempt evidence and `attempt_ref`.

- [x] **Step 2: Verify red**
  - Run: `node wx_miniprogram/tests/test_report_view_model.js`

- [x] **Step 3: Minimal implementation**
  - Reuse existing report projection fields first: recent attempts, mistake cards, evidence refs, scoring-point map.
  - Show 1-3 representative attempts per cluster.
  - Do not compute weak points or mastery in JS.
  - Make each card enter the existing attempt detail page.

- [x] **Step 4: Verify green**
  - Run: `node wx_miniprogram/tests/test_report_view_model.js`
  - Run: `node yousenwebview/tests/test_report_view_model.js`
  - Run: `node wx_miniprogram/tests/test_report_layout.js`
  - Run: `node yousenwebview/tests/test_report_layout.js`

- [x] **Step 5: Review**
  - Spec check: every card is tied to backend evidence or marked degraded.
  - UX check: the page speaks in learning language, not backend enum language.

### Task 4: Home Prompt And Prescription Feedback Loop Audit

**Files:**
- Read: `deeptutor/services/learner_state/home_personalization.py`
- Read: `deeptutor/services/learner_state/training_intent.py`
- Read: `wx_miniprogram/tests/test_home_dashboard_learning_prompts.js`
- Read: `yousenwebview/tests/test_home_dashboard_learning_prompts.js`
- Modify only if a concrete missing link is found.

- [x] **Step 1: Audit existing prompt payload**
  - Confirmed: `wx_miniprogram/tests/test_home_dashboard_learning_prompts.js` already locks `prompt_intent.source=home_dashboard`, `evidence_refs`, `learning_state_ref`, `suggested_mode`, and asserts `buildFallbackFocusQuery` is absent from the view-model (no frontend invention).

- [x] **Step 2: Add tests only for confirmed gaps**
  - No gap found. Home prompt buttons already carry backend `prompt_intent` + `evidence_refs` end-to-end; `_send` is dispatched with the backend `promptIntent` only and falls back to `showStaticExamples=true` when the dashboard projection is empty rather than synthesizing a prompt.

- [x] **Step 3: Minimal implementation**
  - No code change required. `home_personalization.py` + `training_intent.py` remain the only recommendation authorities; frontend only renders them.

- [x] **Step 4: Verify**
  - Run: `node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js` → PASS.
  - Run: `node yousenwebview/tests/test_home_dashboard_learning_prompts.js` → PASS.

### Task 5: Quality / Privacy / Degraded Hardening

**Files:**
- Modify: `deeptutor/services/learner_state/attempt_detail_read_model.py`
- Test: `tests/services/learner_state/test_attempt_detail_read_model.py::test_attempt_detail_strips_internal_context_and_pii_from_history`

- [x] **Step 1: Write failing test**
  - Feed `[History Context]` block + `trace_id=`/`openid=`/`evt_id=` tokens + phone/email/name PII into the recovered assistant message.
  - Assert the resulting `explanation.full_text` no longer contains the internal block or identifiers and that PII is redacted, while the real student-facing sections (`观察法`, `辅助手段当成主要方法`) survive.

- [x] **Step 2: Verify red**
  - Initial run failed exactly on `[History Context]` retention (recorded in repo via the new test name above).

- [x] **Step 3: Minimal implementation**
  - Added `_sanitize_history_text` in `attempt_detail_read_model` which:
    - Strips `[History Context]…[/History Context]` blocks (case-insensitive, multiline).
    - Strips `trace_id=`, `event_id=`, `evt_id=`, `openid=`, `user_id=`, `session_uid=`, `kid=` tokens.
    - Applies `redact_chat_text` from `learner_state.redaction` for phone/email/openid/name/address PII.
  - Sanitization is only applied to recovered historical assistant content; the structured `payload` summary path is untouched (it never carries raw chat).

- [x] **Step 4: Verify green**
  - `python -m pytest tests/services/learner_state/test_attempt_detail_read_model.py -q` → 7 passed.

- [x] **Step 5: Review**
  - Spec check: reuses existing `redact_chat_text` instead of introducing a second redaction authority.
  - Authority check: history remains the raw replay source; sanitization happens at projection boundary only.

**Other quality/privacy claims confirmed without code change:**
- Teacher/sales story stays redacted: `evidence_story_read_model` already routes through `redact_payload` (see `tests/services/learner_state/test_evidence_story_pii_redaction.py`).
- Conversation-only signal does not verify mastery: `learning_synthesis` + `mastery_estimator` only consume `learning_evidence` events that pass the existing quality gate, and the rule-based mastery does not accept conversation-only events as verified attempts.
- Test-set attempts share the same `learning_evidence` quality gate via `construction_grading/writeback.py` + `learning_evidence.build_learning_evidence_payload`.
- The report view-model test asserts no internal enum text (`weak`/`recurrence`/`question_reading`/`discovery_probe`/`code_application`) reaches student-facing strings.

**Deferred (out of this batch, recorded for the broader inference-engine plan):**
- Operational metric emission for `attempt_detail_history_replay_rate`, `generic_diagnosis_rate`, `degraded_attempt_detail_rate`. The signal can be derived from existing trace/log fields; emitting them as first-class metrics is tracked in `docs/plan/2026-05-22-luban-learning-state-inference-engine-transformation-plan.md` under the release-readiness gates and is not blocked by this batch.

## Completion Gate

Batch is complete only when:

- Attempt detail page shows the rich historical explanation when it exists.
- Report page gives concrete historical attempt cards for learning-state claims.
- Home prompt buttons remain backend-intent driven.
- All changed frontend surfaces are verified in `yousenwebview/packageDeeptutor` and shadow-verified in `wx_miniprogram`.
- No new learning authority, endpoint, database table, or frontend diagnosis logic is introduced.

## Current Status (2026-05-23)

- **Status:** Implemented locally through Task 1-5. All Required Verification commands green at HEAD.
- **Not yet:** No push, no deploy. Operational metric emission is intentionally deferred (see Task 5).
- **Workspace note:** Work landed on branch `codex/fix-attempt-diagnosis-explanation-authority-20260522` in the primary working tree alongside earlier in-flight learning-state-inference changes; only files explicitly listed under Tasks 1-5 above were touched by this batch.

## Required Verification

```bash
python -m pytest tests/services/learner_state/test_attempt_detail_read_model.py -q
python -m pytest tests/api/test_mobile_router.py -q
node wx_miniprogram/tests/test_attempt_detail_view_model.js
node wx_miniprogram/tests/test_report_view_model.js
node wx_miniprogram/tests/test_report_layout.js
node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js
node yousenwebview/tests/test_report_view_model.js
node yousenwebview/tests/test_report_layout.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
node yousenwebview/tests/test_home_dashboard_learning_prompts.js
git diff --check
```
