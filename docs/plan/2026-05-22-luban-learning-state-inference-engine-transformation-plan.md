# Luban Learning State Inference Engine Transformation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the learning module from a "smart mistake book / learning report" into a learning-state inference and personalized training engine.

**Architecture:** Keep `learner_memory_events.learning_evidence` as the single learning fact ledger. Extend existing grading evidence, conversation evidence, compiled learning brain projection, learning report read model, home dashboard projection and training intent contract; do not create a second learner memory, second recommendation authority, or frontend-derived mastery logic.

**Tech Stack:** Python services under `deeptutor/services/learner_state` and `deeptutor/services/construction_grading`, mobile router under `deeptutor/api/routers/mobile.py`, shared mini-program view models under `wx_miniprogram` and `yousenwebview`, existing Supabase-backed learner state ledger and compiled truth projection.

---

## Source Report Absorption

This plan absorbs `/Users/yehongchen/Downloads/deep-research-report (1).md`.

The central product definition is accepted:

> The Luban learning module should not be defined as a smart mistake book or a learning statistics report. It should be a learning-state inference and personalized training engine.

The module must fuse long-term answer history, case-answer evidence, scoring-point hits, mistake labels, time decay, knowledge-graph relations and item difficulty to estimate three state layers:

1. **Knowledge state:** which knowledge points, code provisions, construction processes and management rules are weak.
2. **Ability state:** where the learner breaks down in question reading, code application, calculation, expression, transfer and review.
3. **Behavior state:** whether learning is stable, whether forgetting is likely, and whether similar errors keep recurring.

The report's high-value ideas are absorbed selectively:

- MyLA: student-facing dashboards must answer "where am I / why / what next".
- ASSISTments: diagnosis must be followed by revalidation.
- ALEKS: recommendations should consider "ready to learn next", not only weakest nodes.
- Khan Academy: mastery must expose levels, evidence and trend, not just percentages.
- Duolingo: mistake review and spaced repetition should be low-friction.
- Squirrel AI / MATHia: fine-grained knowledge components and at-risk signals are valuable, but only if they remain explainable.

The report's risky ideas are explicitly deferred:

- Full DKT/GNN/black-box graph recommendation.
- Fully automatic graph construction.
- Decorative whole-book 3D graph UI.
- A second learner-mastery database that competes with `learner_memory_events`.
- Frontend-side weak-point / mastery / prescription derivation.

## Current Baseline

This plan builds on the existing learning-report foundation:

- `learner_memory_events.learning_evidence` is the learning fact ledger.
- `learning_evidence` already captures grading and conversation signals.
- `learning_report_read_model` is the page-level read model.
- `attempt_detail_read_model` supports clickable evidence replay.
- `mistake_book` is cloud authority, not local storage.
- `training_intent` is the structured next-action contract.
- `home_dashboard.today_focus` and `recommended_prompts` feed conversation-home personalization.
- `learning_brain` compiled truth separates stable truth from recent observations.

This plan does **not** supersede `2026-05-21-luban-learning-report-world-class-optimization-plan.md`; it is the next P1/P2 transformation layer after the P0 evidence loop.

## Deep Review V2 - Expert Team Conclusions

This review uses the existing DeepTutor constraints as hard gates, not slogans:

- **Assumptions:** the product goal is not to add a prettier report page. The goal is to make every visible learning conclusion traceable to historical answer records, system explanations, conversation signals and follow-up verification.
- **Simplest path:** keep the current evidence ledger and read-model path, then enrich payloads and projections. Do not start with a new mastery table, graph engine, recommendation service or frontend inference layer.
- **Change boundary:** this plan touches learning evidence, learning synthesis, report read model, training intent, home personalization and mini-program rendering. It does not redesign TutorBot, RAG, billing, membership or the unified WebSocket entry.
- **Verification target:** a learner must be able to open the mini-program learning page and see state, reason, action and evidence; every action must either start training or collect new evidence; backend tests, Node view-model tests, WeChat DevTools and production observation must all agree.

The strongest product interpretation is:

> The learning module is a unified system only when all student-visible state flows from one canonical evidence pipeline. If the page combines several APIs while the frontend still ranks weak points, invents prompts, or stores mistake truth locally, it is not unified.

The plan therefore chooses **selective expansion**:

- Expand into case scoring points, ability/behavior states, prescription loops and conversation-home interaction.
- Do not expand into black-box adaptive learning, large graph recommender, teacher dashboards, sales dashboards or decorative visualizations until the student loop is evidence-backed.
- Treat teacher/sales story output as a read projection after student truth is correct, not as a second business target.

### Review Scorecard After V2 Reinforcement

| Lens | Score | Reason | What makes it ship-ready |
| --- | --- | --- | --- |
| Product clarity | 9/10 | It now defines the learning module as state inference and training action, not a report | Validate learner comprehension in WeChat DevTools and small real-user tests |
| Authority discipline | 9/10 | It reuses the evidence ledger, synthesis and read models | Contract guard must reject new competing tables/event types |
| Engineering feasibility | 8/10 | It is split into evidence, projection, UI and verification batches | Batch A must prove rubric evidence quality before UI promises scoring-point maps |
| UX actionability | 8/10 | The page grammar is state -> reason -> action -> evidence | Snapshot tests and DevTools must prove the first viewport is action-led |
| Risk control | 8/10 | It names degraded states, uncertainty and kill criteria | Production p95, source degradation and deployed SHA must be part of release reports |

The remaining risk is not architectural ambition. The remaining risk is evidence quality: if grading payloads and conversation synthesis do not carry enough specific historical context, the UI will still be forced to show generic diagnosis. This is why Batch A must precede any visual upgrade.

## Deep Review V3 - Codebase Reality Reconciliation

Before V3 supplements anything, it grounds the plan in what already exists. Inventing new constructs where existing ones already cover the need is the most common failure mode of "transformation" plans.

### What Is Already Implemented (Do Not Re-Invent)

- Case rubric authority (4-tier priority) is already encoded in `deeptutor/services/construction_grading/case_kernel.py`:
  1. `grading_key.scoring_points` (active_object hidden authority).
  2. `row.grading_rubric` (curated rubric in `questions_bank`).
  3. `_project_specs_from_existing_fields` (projected rubric fallback).
  4. `_open_skill_specs` (no formal rubric).
- Rubric outputs already include `rubric_items`, `rubric_item_ids`, scoring item results, and per-item error codes (see `audit.py` and `learning_evidence.py`).
- Error codes are already issued from grading:
  - `E02`, `E04`: case-grading error codes in `case_kernel.py`.
  - `M02`, `M06`: MCQ error codes in `mcq.py`.
- `deeptutor/services/learner_state/learning_synthesis.py` already groups by `(concept_id, error_code)` and produces a learner-facing projection.
- `deeptutor/services/learner_state/attempt_detail_read_model.py` already integrates `conversation_synthesis` evidence.
- `deeptutor/services/learner_state/study_plan.py` already builds a study plan from weak points and hotspots.
- `deeptutor/services/learner_state/training_intent.py` v1 exists with four modes: `mcq_discrimination`, `case_repair`, `rubric_recall`, `mixed_review`.
- `deeptutor/services/learner_state/mastery_estimator.py` exists.
- `deeptutor/services/learner_state/mistake_book.py` exists (cloud authority).
- `deeptutor/services/learner_state/home_personalization.py` exists.

### Implications For The Plan

- The plan must **bridge** `training_intent.py` v2 with `study_plan.py`, not let them drift into two authorities. The v2 prescription steps must be the structured spine; `study_plan` becomes a thin presenter that reads from intent, not a competing planner.
- Error codes must be unified, not re-invented. The plan's example `M08 / 规范数字混淆` is consistent with the MCQ `M0X` convention, but case-derived diagnoses must use `E0X` codes. The plan therefore needs a **single error-code registry** that documents `E0X` (case) and `M0X` (MCQ) jointly, with `ability_dimension` mapping.
- Scoring-point map promise depends on the share of case items that actually carry `grading_key.scoring_points` or `grading_rubric`. **Coverage is the gating metric**, not test passage. Batch A must surface coverage telemetry before Batch C UI can show the map.
  - 2026-05-22 Supabase audit: `grading_rubric` is **empty (0%)**, but `grading_keywords` covers ~49% and `structured_rules` covers ~34% of case items with already-structured rubric-equivalent material. The normalization path defined in Phase -1.A.1 turns this into projected scoring points without bank mutation. See Decision 1 and Phase -1.A for the measured numbers and authoring backlog.
- `learning_report_read_model.py` is already large (1814 lines). New projections must be added as composable sub-builders or new sibling modules, not inlined, to prevent a single file from exceeding the project's 800-line guideline.
- `learning_synthesis.py` already iterates event histories. Performance must be benchmarked on realistic histories (e.g. 500-2000 events) before Batch B ships.
- Conversation evidence already flows; the V3 gap is **quality classification**, not new event types. Trivial chat must not pollute synthesis.

### V3 Scorecard Delta

| Lens | V2 | V3 (after this revision) | Reason for delta |
| --- | --- | --- | --- |
| Product clarity | 9/10 | 9/10 | Already strong; V3 adds cold-start/abandonment scenarios |
| Authority discipline | 9/10 | 9/10 | Already strong; V3 unifies error-code registry and `training_intent`/`study_plan` roles |
| Engineering feasibility | 8/10 | 9/10 | V3 adds rubric coverage gate, performance budget, branch/PR strategy, feature flag |
| UX actionability | 8/10 | 9/10 | V3 adds cold-start/abandonment/multi-prescription/concurrent device scenarios |
| Risk control | 8/10 | 9/10 | V3 adds quantitative gates, observability, rollback runbook, A/B comparison |

### V3 Newly Surfaced Gaps (All Closed Below)

1. Rubric coverage is implicit; needs a measured gate.
2. Error code registry is not unified; needs `error_code_registry.md`.
3. `training_intent v2` overlap with `study_plan` is unresolved.
4. No explicit performance budget for synthesis or read model.
5. No data migration / backward compatibility plan for old `learning_evidence` rows missing new fields.
6. No feature flag / cohort rollout / kill switch.
7. No structured observability (rubric coverage rate, evidence completeness, prescription verification rate, p95).
8. No conversation evidence quality bar; chat could pollute synthesis.
9. No SubmissionGraderAgent rubric grounding discipline; LLM may invent scoring-point hits.
10. No mistake clustering algorithm spec (cluster key, dedupe rules, persistence).
11. No ARRS-style scheduled revalidation queue (report mentions revalidation but does not schedule it).
12. No PII redaction policy for teacher/sales story projection.
13. No knowledge graph governance pipeline (versioning, review).
14. No explicit branch/PR strategy under AGENTS §3.6.
15. No rollback runbook per batch.
16. No quantitative A/B comparison plan vs current baseline.
17. No cold-start, abandonment, multi-prescription, multi-device, member-tier scenarios.
18. No test data fixture generator covering all scenarios.

All 18 gaps are closed in the new sections below; tasks 0.A-0.D, observability, rollout, migration, branch, rollback, A/B, and scenario expansion sections are added downstream.

## Existing Module Reuse Matrix

This plan should reuse current modules before adding anything new.

| Product need | Existing module to reuse | Allowed extension | Forbidden shortcut |
| --- | --- | --- | --- |
| Long-term answer history | `learner_memory_events.learning_evidence` | Add evidence payload fields and quality gates | New learner memory table |
| Case-answer grading | `construction_grading` and `SubmissionGraderAgent` path | Preserve rubric/scoring-point hits in payload | Read model fabricates rubric results |
| System explanation and chat history | `conversation_synthesis` evidence under existing learning evidence event | Add `learning_signal_type` and turn refs | New conversation event type or chat WebSocket |
| Attempt replay | `attempt_detail_read_model` | Include full historical question, answer, system explanation and timestamps | Modal-only summaries or frontend reconstruction |
| Mistake collection | Cloud mistake-book authority | Link bookmark state to evidence refs | Local storage as truth |
| Weak point and mastery display | `learning_synthesis`, `learning_brain_read_model`, `learning_report_read_model` | Add knowledge/ability/behavior projections | Frontend-derived mastery or ranking |
| Next training | `training_intent` | Add intent v2 prescription phases and verification criteria | Static prompt cards as recommendation authority |
| Conversation-home personalization | `home_dashboard.today_focus` and `recommended_prompts` | Use report projection to tune prompt payloads | Frontend-generated prompts |
| Knowledge graph | Existing taxonomy/assessment assets plus a minimal expert seed | Small audited graph seed for high-value clusters | Auto-built full graph or 3D graph UI |
| Time decay | `mastery_estimator` / `learning_synthesis` | Rule-based recency confidence and revalidation need | Black-box DKT/BKT before evidence quality is stable |

## Unified Learning System Contract

The learning module is one system with several projections.

Allowed projections:

- Student learning report: `learning_report_read_model`.
- Attempt detail: `attempt_detail_read_model`.
- Home dashboard personalization: `home_dashboard.today_focus` and `recommended_prompts`.
- Training launch payload: `training_intent`.
- Cloud mistake book: mistake-book read model bound to evidence refs.

All projections must obey the same source order:

```text
raw grading / conversation / training action
-> learner_memory_events.learning_evidence
-> synthesis and confidence rules
-> read projection
-> mini-program rendering
```

Forbidden signs that the system is drifting back into split authority:

- A mini-program page computes mastery, weak points, prompt wording or training priority.
- A route reads raw attempts and independently diagnoses errors outside the learning read model.
- A prompt card is shown as personalized without backend evidence refs.
- A mistake-book item exists only in local storage.
- Conversation history affects chat output but never becomes learning evidence.
- A dashboard shows "加载失败" while still claiming stable learning conclusions.

If any of these signs appear, the fix is not another frontend fallback. The fix is to restore the canonical path or mark the projection as degraded.

## Design Gates

### Thin Wrapper / Fat Skill Split

- Thin wrappers:
  - `deeptutor/api/routers/mobile.py`
  - mini-program page JS/WXML/WXSS
  - shared frontend view models

- Fat skills / authorities:
  - `deeptutor/services/construction_grading/*` writes grading and rubric evidence.
  - `deeptutor/services/learner_state/service.py` stores evidence in the existing ledger.
  - `deeptutor/services/learner_state/learning_synthesis.py` compiles long-term learning state.
  - `deeptutor/services/learner_state/learning_brain_read_model.py` exposes learner-facing compiled truth.
  - `deeptutor/services/learner_state/learning_report_read_model.py` assembles the student report.
  - `deeptutor/services/learner_state/training_intent.py` owns structured prescription intent.
  - `deeptutor/services/learner_state/home_personalization.py` projects conversation-home prompts.

Wrappers may normalize, route and render. They must not infer mastery, weak points, prescriptions or next prompts.

### One Business Fact

The one business fact is:

> For a learner, what is the current evidence-backed learning state, why is that state inferred, and what training action should happen next?

### One Authority

The canonical path is:

```text
grading / conversation / training action
-> learner_memory_events.learning_evidence
-> learning_synthesis compiled projection
-> learning_brain_read_model / learning_report_read_model / home_dashboard projection
-> mobile UI / conversation-home UI
```

Any table, cache or endpoint introduced later must be a bounded projection or asset catalog, not a competing learning-state authority.

### Concepts To Delete Or Demote

- Demote raw correctness rate from "mastery" to one evidence feature.
- Demote one-off wrong answers from "weak point" to "recent observation".
- Demote static prompt cards to fallback copy only.
- Demote local mini-program state from learning truth to UI cache only.
- Do not introduce `learner_mastery` as a new source of truth in this phase.

## Non-Goals

1. No second learner memory system.
2. No second recommendation authority.
3. No dedicated chat WebSocket.
4. No frontend-derived mastery, weak points, next training or prompts.
5. No full GNN, full DKT, automatic graph construction or 3D knowledge map.
6. No teacher/sales dashboard before student evidence and prescription projections are trustworthy.
7. No new database tables unless an existing authority cannot represent the fact and the contract review proves the table is a projection or asset catalog.
8. No new error-code prefix (only `E0X` for case, `M0X` for MCQ) — extending existing codes is allowed; inventing third prefix is forbidden.
9. No new prescription authority; `study_plan.py` must read from `training_intent`, never co-author next-step decisions.
10. No silent LLM rubric invention — if `grading_key.scoring_points` and `grading_rubric` are absent, the system must not let LLM fabricate scoring points; the scoring-point map must show the honest empty state instead.
11. No broad rollout before the feature flag `LEARNING_STATE_INFERENCE_V2` gate is honored.
12. No removal of v1 `training_intent` fields; v2 is additive until v1 consumers migrate.

## Target Learner-Facing Outcome

After this plan, the learning module should show a learner:

- What is currently weak.
- Whether it is a knowledge weakness, ability weakness or behavior pattern.
- Which exact evidence supports the conclusion.
- Whether the conclusion is stable or only a recent observation.
- What to do next.
- How the next action will be verified.

The core UI grammar should be:

```text
状态 -> 原因 -> 动作 -> 证据
```

## WeChat Mini-Program UX Contract

The mini-program is not a statistics dashboard. It is the student-facing control room for the evidence loop.

Primary release surface:

- `yousenwebview/packageDeeptutor` is the current production-facing WeChat/佑森 mini-program surface and must be the primary visual and manual acceptance gate.
- `wx_miniprogram` remains a shadow test / render-contract surface. It should stay in sync for shared view-model tests, but passing `wx_miniprogram` alone does not prove release readiness.
- Shared view-model code should be updated first where possible; page-specific JS/WXML/WXSS changes then land in `yousenwebview/packageDeeptutor`, with `wx_miniprogram` mirroring only the reusable contract.

### First Viewport

The first viewport must answer three things without scrolling deeply:

1. **Today prescription:** one primary action, for example "先完成一次防火门构造采分点验证".
2. **Why this action:** one evidence-backed sentence, for example "最近 2 次都漏掉甲乙丙级耐火极限".
3. **Where the evidence is:** a clickable evidence count, for example "查看 2 条作答证据".

The first viewport may show compact counters, but counters cannot be the hero. The hero is the next learning action and its evidence.

### Page Structure

Use a vertical page with stable sections:

1. `今日处方`: backend-owned `training_intent` with start button.
2. `三层状态`: segmented control for `知识状态 / 能力状态 / 行为状态`.
3. `采分点漏分`: rubric-derived scoring-point map, hidden behind an honest empty state if no case rubric evidence exists.
4. `错因复发`: repeated evidence clusters, deduped by knowledge node + ability dimension + error code.
5. `真实作答证据`: attempt cards with timestamp, question title, learner answer, system explanation, and detail navigation.
6. `复习闭环`: assigned training, completion, verification probe and outcome.

### Required Interactions

- Tap `开始训练`: launch `deep_question` or existing training flow with structured `training_intent`; do not build a new training authority.
- Tap a state chip: filter visible evidence to the matching knowledge node, ability dimension or behavior signal.
- Tap a scoring point: open a scoring-point detail sheet/page with missed attempts and one suggested verification action.
- Tap an attempt card: navigate to the existing attempt detail page, including historical chat/system explanation and exact timestamp.
- Tap `我还不懂`: continue through `/api/v1/ws`; when the assistant explains, emit `conversation_synthesis` learning evidence.
- Tap `收藏错题`: call cloud mistake-book authority; local storage may only cache pending UI state.
- Tap a conversation-home recommended prompt: pass backend `recommended_prompt.intent` into chat and write `home_prompt_clicked` evidence.

### Conversation Home Interaction Contract

The conversation home page and the learning report are two views of the same learning state, not two products.

Home-page focus card:

- Source: `home_dashboard.today_focus`.
- Must cite the same evidence cluster used by `learning_report_read_model`.
- Tap target: opens the learning report filtered to the matching state, or starts the backend-owned `training_intent` if the card is explicitly a training card.

Home-page prompt buttons:

- Source: `home_dashboard.recommended_prompts`.
- Each prompt must include `intent`, `evidence_refs`, `learning_state_ref` and `suggested_mode`.
- Prompt text can change when the learner completes a training step, asks for an explanation, clicks "still confused", or passes/fails verification.
- The mini-program must not rewrite the prompt based on local counters. It only renders the backend prompt and sends its intent into `/api/v1/ws`.

Prompt examples:

```json
{
  "text": "帮我把防火门耐火极限讲透，并出 1 道验证题",
  "intent": {
    "kind": "repair_and_verify",
    "concept_id": "1A421000",
    "concept_label": "防火门耐火极限",
    "ability_dimension": "code_application",
    "training_intent_id": "intent_fire_rating_001"
  },
  "evidence_refs": ["attempt_fire_001", "attempt_fire_002"],
  "learning_state_ref": {
    "layer": "knowledge_state",
    "state_id": "ks_fire_door_rating"
  },
  "suggested_mode": "deep"
}
```

Expected update loop:

```text
home prompt clicked
-> /api/v1/ws conversation
-> conversation_synthesis learning evidence
-> learning_synthesis refresh
-> learning_report_read_model / home_dashboard refresh
-> prompt text and report action change together
```

### Degraded States

The UI must be honest about missing evidence:

- No learning evidence: show "完成一次案例题批改后生成学情".
- No rubric evidence: show "完成案例题批改后生成采分点地图".
- Only conversation evidence: show "已解释但尚未验证", never "已掌握".
- Backend unavailable: show "学情接口暂不可用，已显示基础数据" and hide action claims that depend on missing projections.
- Low confidence: show "需要一次验证题确认", not a strong weakness label.

### Visual Discipline

- Use compact cards and stable section headers; this is an operational student tool, not a landing page.
- Avoid nested cards inside cards.
- Do not let warning banners dominate the page when the report has usable evidence.
- Every visible card needs one primary action or one clear evidence link.
- Every action must round-trip into backend evidence or training intent.

## Data Model Additions Inside Existing Evidence

The following fields are additive payload fields under existing `learning_evidence`. They do not create a new event type.

### Grading / Attempt Evidence

```json
{
  "event_type": "learning_evidence",
  "evidence_source": "construction_grading",
  "question_id": "q_123",
  "question_type": "case_short_answer",
  "item_difficulty": {
    "level": "medium",
    "weight": 0.72,
    "source": "expert_seed"
  },
  "knowledge_refs": [
    {
      "node_id": "1A421000",
      "label": "防火门构造要求",
      "node_type": "knowledge_point",
      "exam_weight": 0.82
    }
  ],
  "rubric": {
    "rubric_id": "fire_door_case_v1",
    "rubric_version": "2026-05-22",
    "scoring_points": [
      {
        "point_id": "fire_door_rating",
        "label": "甲乙丙级防火门耐火极限",
        "max_score": 1,
        "ability_dimension": "code_application",
        "knowledge_node_id": "1A421000",
        "child_concept_label": "防火门耐火极限"
      }
    ],
    "scoring_point_hits": [
      {
        "point_id": "fire_door_rating",
        "hit": false,
        "awarded_score": 0,
        "miss_reason": "把甲级 1.5h 记成 1.0h",
        "evidence_text": "甲级防火门的耐火极限为1.0h"
      }
    ]
  },
  "ability_signals": [
    {
      "dimension": "code_application",
      "polarity": "negative",
      "reason": "规范数值混淆",
      "confidence": 0.8
    }
  ],
  "behavior_signals": [
    {
      "dimension": "recurrence",
      "polarity": "unknown",
      "reason": "首次观察，需要后续验证",
      "confidence": 0.3
    }
  ]
}
```

### Conversation Evidence

Conversation evidence remains:

```json
{
  "event_type": "learning_evidence",
  "memory_kind": "learning_evidence",
  "evidence_source": "conversation_synthesis",
  "learning_signal_type": "answer_explanation",
  "assistant_explanation_summary": "系统解释了防火门甲乙丙级耐火极限和双扇门顺序关闭要求。",
  "conversation_turn_ref": "turn_opaque"
}
```

It can support "exposed / explained / still confused", but cannot by itself prove mastery.

## Scenario Matrix

The implementation must cover these scenarios explicitly, because they are where learning systems usually hallucinate certainty.

| Scenario | Expected system behavior | Acceptance signal |
| --- | --- | --- |
| Brand-new learner | Show entry action and explain that no evidence exists yet | No mastery/weakness label is shown |
| Objective-question only learner | Show attempt evidence and weak observations, but no scoring-point map | Scoring-point section uses honest empty state |
| Case-answer learner | Show rubric scoring-point hits, missed points and next prescription | Attempt detail includes original question, answer and system explanation |
| Conversation-only learner | Show "explained / still confused" signals but require verification | No conversation-only event marks mastery stable |
| Repeated same miss | Cluster by knowledge node + ability dimension + error code | One deduped diagnosis card cites multiple attempts |
| Recent correct after old wrong | Mark as improving or needs follow-up, not permanently weak | Time-aware confidence changes state |
| Old correct with no recent evidence | Mark forgetting risk and request revalidation | `needs_revalidation=true` |
| Contradictory evidence | Prefer recent verified attempt, show confidence and evidence split | UI shows "证据不一致，需验证" |
| Backend degraded | Render only projections that are available | `degraded_sources` names missing surfaces |
| Home prompt clicked | Chat opens with backend intent and writes evidence on interaction | `home_prompt_clicked` evidence exists |
| Student says "I still do not understand" | Chat explains through `/api/v1/ws` and writes `still_confused` evidence | Report behavior state updates without new event type |
| Teacher/sales demo | Read-only story projection cites evidence refs | No raw private chat leak, no uncited claim |
| Cold start, zero evidence | First viewport offers a 1-题 onboarding probe and explains "we will start building your profile after this" | No mastery/weakness/prescription claim; `learning_state.bootstrap=true` |
| First case attempt without curated rubric | System falls back to projected rubric and marks the scoring-point map as "rubric pending" | `rubric_mode=projected_rubric` is honored; no fabricated scoring point hits |
| Prescription abandoned mid-way | Prescription remains `assigned`; system surfaces "继续上次未完成的训练" within 24h, then deprioritizes after 7 days | `prescription_outcomes[*].status` includes `abandoned` |
| Multiple active prescriptions | At most 3 active prescriptions; new ones queued behind | `prescription_outcomes` has `priority` and `queued` states |
| Same learner switches device | Prescription state and report state load identically across mini-program and web view; no local-only progress | View model snapshot test on both `wx_miniprogram` and `yousenwebview` matches backend payload byte-for-byte for the actionable region |
| Free-tier learner exceeds quota | Report still shows state and evidence; prescription start is gated with a tier-aware CTA | No mastery hidden; CTA carries `quota_exceeded` reason and never silently fails |
| Conversation evidence below quality bar | Trivial chat ("ok / 嗯 / 知道了") does not produce learning evidence | `conversation_synthesis` quality classifier filters; `learning_signal_type` is one of allowed enum values only |
| LLM grader disagrees with curated rubric | Curated rubric wins; LLM dissent is logged as `grader_disagreement` audit row | No scoring point hit is changed by LLM after curated rubric ruling |
| Backfill / replay of historical evidence | Historical events without new payload fields render as `legacy_evidence` and do not trigger state regressions | Read model treats missing rubric as projected/legacy, not as failure |
| ARRS spaced revalidation due | Prescription queue inserts a revalidation probe at 1d/3d/7d/14d for prior weak nodes | `prescription_outcomes[*].kind=revalidation_probe` exists |
| Contradiction between curated answer and LLM scoring | System trusts curated `grading_key` first, surfaces `evidence_split` and downgrades confidence | UI shows "证据不一致，需验证" and `confidence < 0.6` |

## Delivery Sequencing

Do not attempt all ten tasks as one large release. Ship four bounded slices.

### Batch A - Evidence Readiness

Tasks:

- Task 1: Contract addendum.
- Task 2: Case rubric evidence payload.
- Task 3: Minimal expert graph seed.

Release condition:

- Evidence can represent case scoring points, knowledge refs, ability dimensions and difficulty without creating a second authority.

### Batch B - State Projection

Tasks:

- Task 4: Three-layer learning state projection.
- Task 5: Recency-aware confidence and forgetting risk.

Release condition:

- Backend can explain knowledge, ability and behavior state with evidence refs and confidence.

### Batch C - Student Action Loop

Tasks:

- Task 6: Prescription intent v2.
- Task 7: Scoring point map read projection.
- Task 8: Student UI.

Release condition:

- WeChat learning page lets a student start the correct next action from evidence-backed state.

### Batch D - Verification And Story

Tasks:

- Task 9: Prescription completion and revalidation evidence.
- Task 10: Teacher and sales evidence story projection.

Release condition:

- The system can show "missed -> trained -> verified" without uncited claims.

## Uncertainties And Validation Plan

These are current uncertainties, not blockers, as long as each has a validation path.

| Uncertainty | Risk | Validation or fallback |
| --- | --- | --- |
| Rubric extraction quality | Wrong scoring-point diagnosis would damage trust | Start with 20 expert-reviewed case examples; require human agreement before broad rollout |
| Knowledge graph labels | Wrong node labels make advice feel arbitrary | Use only three expert-seeded clusters in Batch A; add graph coverage slowly |
| Item difficulty | Sparse data makes difficulty noisy | Use `expert_seed` difficulty first; later calibrate with exposure/outcome data |
| Time decay threshold | 14-day default may be too strict or loose | Compare 7/14/30-day recurrence and adjust rule in `mastery_estimator` |
| Conversation evidence confidence | Chat explanation may not prove learning | Keep conversation evidence below mastery threshold until verification attempt exists |
| UI comprehension | Students may not understand three-layer terminology | Test with 5-10 learners; success means they can state "why this action" in their own words |
| Production latency | Larger report payload may hurt p95 | Gate with `/api/v1/mobile/learning-report` p95 and degraded-source budget |
| Deployment/worktree drift | Local branch, origin and Aliyun can disagree | Release report must include local HEAD, origin SHA, deployed SHA and WeChat visible result |
| Rubric coverage of case bank | Many case items still lack `grading_key.scoring_points` or `grading_rubric`; scoring-point map will look empty | Phase -1.A measures coverage; promote map UI only when curated+projected coverage ≥ 70% of recent case attempts |
| LLM grader rubric grounding | LLM may invent scoring point hits absent from rubric | Phase -1.A prompt discipline + audit row `grader_disagreement` + curated-rubric-wins policy |
| `training_intent` vs `study_plan` drift | Two prescription authorities could re-emerge | Phase -1.C reconciliation: `study_plan` becomes a read presenter; `training_intent` is the only authority |
| Synthesis performance on long histories | 1000+ events per learner may slow synthesis | Phase -1.D benchmark: synthesis must complete < 200ms p95 on 2000 events; otherwise window to last N events with explicit `truncated=true` |
| Backward compatibility | Existing `learning_evidence` rows lack new payload fields | Read model treats missing fields as `legacy_evidence`; no schema mutation; forward-only enrichment |
| Conversation evidence pollution | Trivial chat could inflate state evidence | `learning_signal_type` enum is closed; classifier in `conversation_learning_evidence.py` rejects below-threshold turns |
| Error code drift | New code added without registry update | Contract guard fails if grading payload emits code outside `error_code_registry.md` |
| Feature flag failure | Bug ships to all users if rollout is uncontrolled | `LEARNING_STATE_INFERENCE_V2` cohort flag gates Batch B/C/D projections; killable in < 5 min |
| Knowledge graph drift | Hand-edited seed nodes diverge from rubric/error codes | Phase -1.B versions the seed and contract guard cross-checks node IDs referenced in evidence |
| Demo PII leakage | Sales/teacher story projection might surface private chat | Mandatory redaction layer in `evidence_story_read_model.py`; unit tests assert no raw chat strings appear |

## Kill Criteria

Do not ship a slice if any of these are true:

- A card claims mastery, weakness or next action without evidence refs.
- A frontend file derives mastery, weak points, training priority or prompt content.
- A scoring-point map is shown without rubric evidence.
- A conversation-only signal marks a learner as mastered.
- A training prescription cannot produce follow-up evidence.
- A cloud mistake-book action falls back to local storage as truth.
- A new endpoint, table or event type appears before contract registration.
- A degraded backend surface still renders strong product claims.
- An error code outside `error_code_registry.md` reaches `learning_evidence`.
- LLM-generated rubric items appear when no curated or projected rubric exists.
- `study_plan.py` independently invents a prescription without reading from `training_intent`.
- Synthesis exceeds the performance budget on a realistic learner history.
- Feature flag `LEARNING_STATE_INFERENCE_V2` is removed before the success criteria are met for the previously rolled-out cohort.
- Sales/teacher story projection ships without an automated PII-redaction test.
- A new payload field is required to render a card; the card must instead show the honest empty state until backfill is done.

## Phased Roadmap

### Phase -1: Foundation Tasks Before Batch A

These four foundation tasks remove the silent assumptions that would otherwise force Batch A to ship on shaky ground. Each is small, scoped, and verifiable.

#### Task 0.A: Rubric Coverage Telemetry And LLM Grounding Discipline

**Why this comes first:** Batch A promises scoring-point evidence. Without coverage telemetry, the project does not know if the case bank has the rubric data needed to keep that promise. Without LLM grounding discipline, the grader may invent hits.

**Reality grounding (2026-05-22, measured directly against production Supabase):**

| Field on `public.questions_bank` | Total rows = 4,638 | case_study rows = 1,961 |
| --- | --- | --- |
| `grading_rubric` populated | 0 / 4,638 | 0 / 1,961 |
| `grading_keywords` non-empty array | — | 960 / 1,961 ≈ 49% |
| `structured_rules` non-empty array | — | 661 / 1,961 ≈ 34% |
| `analysis` non-empty text | — | 1,332 / 1,961 ≈ 68% |
| `correct_answer` non-empty | — | 1,950 / 1,961 ≈ 99% |
| `node_code` populated (knowledge mapping) | — | 1,916 / 1,961 ≈ 98% |
| `cited_standard_codes` non-empty | — | 13 / 1,961 ≈ 0.7% |

| Other tables | Status |
| --- | --- |
| `public.rubrics` (dedicated rubric table) | 1 row total — effectively unused |
| `public.question_intelligence` | 43 / 4,638 rows compiled (~0.9%) — barely started |
| `public.knowledge_question_links` | 709 links covering 432 distinct questions (~9%) |

**Implications that change the plan:**

- `grading_rubric` is **empty across the entire bank**, but case items already carry rich rubric-equivalent data in `grading_keywords` (49%) and `structured_rules` (34%), and almost all carry `correct_answer` (99%).
- Sample inspection of `structured_rules` shows it is already **structured scoring material** (`requirement`, `condition`, `consequence`, `automation_slots`, units, value ranges) — exactly what a scoring point looks like, just stored under a different field name.
- The right move is **NOT** "author rubrics from scratch". The right move is **normalize the existing `grading_keywords` + `structured_rules` + `correct_answer` into the canonical `scoring_points` projection**, then author only the residual ~51% (~ 1,000 case items) that lack any structured rubric signal.
- Knowledge node IDs in production are 7-8 character codes like `1A412010`, `1A422000`, `1A436000` under the `1A4XXXXX` family (一建建筑实务). The plan's earlier hypothetical IDs like `1A421000.fire_door.rating` must be **rewritten to use the real `node_code` namespace**; do not invent dotted sub-codes.
- `question_intelligence` cannot be the source of `common_error_tags` for Batch B; it is empty. Error attribution must come from grading evidence + `mistake_tags` projection, not from this table.
- `cited_standard_codes` is effectively empty; do not promise "规范条文引用错误" diagnosis as a Batch A/B headline. Use `analysis` text and `structured_rules.requirement` as a soft signal only, and target this field for a separate backfill effort.

**Files:**
- Modify: `deeptutor/services/construction_grading/audit.py`
- Modify: `deeptutor/services/construction_grading/case_kernel.py` (only the grounding guardrail)
- Create: `scripts/rubric_coverage_report.py`
- Create: `docs/qa/2026-05-22-rubric-coverage-baseline.md`
- Test: `tests/services/construction_grading/test_rubric_coverage_audit.py`
- Test: `tests/services/construction_grading/test_grader_disagreement_audit.py`

- [ ] Write failing test for coverage classification:

```python
def test_rubric_coverage_classifies_each_attempt_by_authority_tier():
    audit = classify_rubric_coverage(rows=[
        {"question_id": "q1", "grading_key": {"scoring_points": [{"point_id": "p1"}]}},
        {"question_id": "q2", "grading_rubric": [{"point_id": "p2"}]},
        {"question_id": "q3"},
    ])
    assert audit["coverage_counts"] == {
        "grading_key": 1,
        "curated_rubric": 1,
        "projected_or_open": 1,
    }
    assert audit["map_eligible_ratio"] == 2 / 3
```

- [ ] Write failing test for grader-disagreement audit:

```python
def test_llm_scored_hit_outside_curated_rubric_is_flagged_and_overridden():
    audit = reconcile_grader_output(
        rubric_specs=[{"point_id": "fire_rating", "source": "curated_rubric"}],
        llm_output={"scoring_point_hits": [
            {"point_id": "fire_rating", "hit": True},
            {"point_id": "invented_extra_point", "hit": True},
        ]},
    )
    assert audit["accepted_hits"] == [{"point_id": "fire_rating", "hit": True}]
    assert audit["disagreement"] == [{"point_id": "invented_extra_point", "reason": "not_in_rubric"}]
```

- [ ] Implement classification + reconciliation; emit `grader_disagreement` rows into existing audit pipeline.

- [ ] Run coverage report against the latest 30-day case attempts.

```bash
python scripts/rubric_coverage_report.py --window 30d --out docs/qa/2026-05-22-rubric-coverage-baseline.md
```

### Phase -1.A Concrete Path (After 2026-05-22 Supabase Audit)

Phase -1.A is now split into three sub-deliverables, in dependency order:

#### -1.A.1 Rubric Source Normalization (Read-Only Audit + Migration Spec)

- Build `scripts/rubric_coverage_report.py` to compute, per `question_type`:
  - `raw_rubric_coverage` = share with `grading_rubric` populated (baseline today: **0%** for case_study).
  - `legacy_signal_coverage` = share with `grading_keywords` non-empty array OR `structured_rules` non-empty array OR `correct_answer` non-empty (baseline today: **~99%** for case_study).
  - `map_eligible_coverage` = share whose normalized projection produces ≥ 2 distinct scoring points (target ≥ 70% before Batch C map UI promotion).
- Build `scripts/normalize_legacy_rubric.py` that emits a **projected `scoring_points` array** from `grading_keywords` + `structured_rules` + `correct_answer`. This is **read-only** — it does not mutate the bank. It produces an in-memory projection or a clearly derived QA artifact consumed by `case_kernel.py`'s existing `_project_specs_from_existing_fields` path. If a persisted cache is ever needed later, it must be registered as a derived projection with invalidation rules, not as rubric authority.
- The normalization spec must define:
  - How `grading_keywords` entries map to `point_id` (keyword text hash → stable id).
  - How each `structured_rules` entry maps to a `point_id`, `label`, `requirement`, and inferred `ability_dimension` from the rule type (`Mandatory` → `code_application`, `condition_expr` with numeric ranges → `calculation`, etc.).
  - Conflict resolution when keywords and rules overlap (rule wins; keyword becomes evidence_text candidate).
- Output: `docs/qa/2026-05-22-rubric-coverage-baseline.md` with the measured numbers + the available high-signal normalization preview. The 2026-05-22 baseline has only 13 high-signal preview rows under the strict `grading_keywords >= 3 AND structured_rules >= 2` filter; the normalizer must add a keyword-only preview set before asking 教研 to sign off 50 rows.

#### -1.A.2 Authoring Backfill For Residual Gap

- Target the ~51% of case items (≈ 1,000 items) that lack enough `grading_keywords` and `structured_rules` to produce ≥ 2 normalized scoring points.
- 教研 + 数据 双签 authoring queue, prioritized by:
  1. `source_type='REAL_EXAM'` AND `exam_year BETWEEN 2017 AND 2021` (215 items): node classification is already present, so this is rubric authoring only and has the highest leverage.
  2. `source_type='REAL_EXAM'` AND `exam_year IN (2015, 2016)` (45 items): handle as a separate classification-first queue because all 45 miss `node_code`, and 4 of the 2015 items have `[题干缺失]` and require original content recovery before rubric work.
  3. Clusters currently at 32-50% map eligibility (`1A41304`, `1A43400`, `1A41303`, `1A43200`, `1A43300`, about 466 items): light authoring can unlock per-cluster UI.
  4. High aggregate `error_rate` among generated/null-year case items.
- Tooling: a thin admin UI (or a CSV round-trip via 教研 spreadsheet) that writes back into `grading_keywords` + `structured_rules`, **never directly into `grading_rubric`**, so the normalization pipeline remains the single rubric authority.
- 60-day target: top 30% by exam_weight reach map-eligible coverage ≥ 90%.

#### -1.A.3 LLM Grounding Discipline (Already In Spec Above)

Carry forward the curated-rubric-wins reconciliation and `grader_disagreement` audit row exactly as specified.

### Phase -1.A Release Conditions

- `legacy_signal_coverage ≥ 0.49` measured (baseline today, confirmed by 2026-05-22 audit).
- `map_eligible_coverage` measured and published; promotion of the scoring-point map UI requires ≥ 0.70 OR explicit `rubric_pending` empty state in `wx_miniprogram` + `yousenwebview`.
- `grader_disagreement` audit emits less than 5% of all case attempts; higher rate blocks promotion of LLM-generated hits into evidence.
- The first available high-signal preview set is reviewed by 教研 + 数据, then a second 50-row preview including keyword-only items is reviewed before broad normalization rollout.

#### Task 0.B: Unified Error Code Registry

**Why this comes first:** Existing code already uses `E0X` (case) and `M0X` (MCQ), but no single document lists them, defines ability-dimension mapping, or constrains new code emission. Any v2 training intent or three-layer state projection that refers to error codes must reference a single registry, not scattered constants.

**Files:**
- Create: `docs/contracts/error_code_registry.md`
- Modify: `contracts/index.yaml` (register the registry)
- Modify: `deeptutor/services/construction_grading/schema.py` (validate against registry)
- Modify: `scripts/check_contract_guard.py` (cross-check emitted codes)
- Test: `tests/services/construction_grading/test_error_code_registry.py`

Required registry shape:

```markdown
# Error Code Registry

## E series — case / essay grading

| code | label | ability_dimension | typical_cause | example |
| --- | --- | --- | --- | --- |
| E01 | 关键采分点遗漏 | expression | 未写出标准采分点 | 防火门耐火极限漏写丙级 |
| E02 | 规范条文引用错误 | code_application | 引用错条款或数值 | 写成 GB50016 而非 GB50016-2014 |
| E04 | 程序顺序错乱 | transfer | 先后顺序与规范不符 | 先审批后编制 |
| ... | | | | |

## M series — MCQ grading

| code | label | ability_dimension | typical_cause | example |
| --- | --- | --- | --- | --- |
| M02 | 干扰项混淆 | question_reading | 误选高频干扰项 | 选错耐火等级 |
| M06 | 数值记忆错误 | code_application | 数字背错 | 1.5h vs 1.0h |
| M08 | 规范数字混淆 | code_application | 跨条款数字混淆 | 与其他防火条款数值串了 |
| ... | | | | |
```

- [ ] Write failing test for contract guard:

```python
def test_emitting_unregistered_error_code_fails_contract_guard():
    with pytest.raises(ContractGuardError, match="unregistered_error_code"):
        check_emitted_error_codes(["E02", "E04", "X99"])
```

- [ ] Implement registry loader and contract guard cross-check.

- [ ] Verify all current emit sites (`case_kernel.py`, `mcq.py`, `learning_synthesis.py`, `training_intent.py`) reference registered codes.

```bash
python scripts/check_contract_guard.py
python -m pytest tests/services/construction_grading/test_error_code_registry.py -q
```

Release condition: every code emitted in tests and recent production samples exists in the registry; every `ability_dimension` referenced by Task 4's three-layer projection comes from the registry mapping.

#### Task 0.C: `training_intent` / `study_plan` Authority Reconciliation

**Why this comes first:** Two prescription authorities will silently drift. v2 prescription steps must be the spine; `study_plan` can present, never decide.

**Files:**
- Modify: `deeptutor/services/learner_state/study_plan.py` (read from intent only)
- Modify: `deeptutor/services/learner_state/training_intent.py` (expose primary intent for a learner)
- Test: `tests/services/learner_state/test_study_plan_reads_training_intent.py`

- [ ] Write failing test:

```python
def test_study_plan_focus_topic_is_derived_from_active_training_intent():
    plan = build_study_plan(
        focus_hint="auto",
        active_training_intent={"concept_label": "防火门耐火极限"},
        weak_points=["其它"],
    )
    assert plan["focus_topic"] == "防火门耐火极限"
    assert plan["source"] == "training_intent"
```

- [ ] Implement: `study_plan` accepts an `active_training_intent` and uses it as the first source of focus, weak_points only as fallback.

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_study_plan_reads_training_intent.py -q
```

Release condition: `study_plan` never emits a focus topic that disagrees with the active `training_intent` for the same learner.

#### Task 0.D: Synthesis And Read-Model Performance Budget

**Why this comes first:** `learning_synthesis.py` is 907 lines and `learning_report_read_model.py` is 1814 lines. Adding three-layer state, scoring-point map and prescription outcomes without a budget invites a quiet p95 regression.

**Files:**
- Create: `scripts/bench_learning_synthesis.py`
- Create: `docs/qa/2026-05-22-learning-state-performance-baseline.md`
- Modify: `deeptutor/services/learner_state/learning_synthesis.py` (event-window argument with explicit `truncated=true` flag)

Budget targets:

- `synthesize_learning_truth` p95 ≤ 200ms on 2000 events.
- `build_learning_report_read_model` p95 ≤ 350ms cold, ≤ 150ms warm (with read-model cache).
- `/api/v1/mobile/learning-report` p95 ≤ 600ms in production.

- [ ] Implement an event-window argument so the synthesis bounds work for long histories.

- [ ] Run:

```bash
python scripts/bench_learning_synthesis.py --events 2000 --out docs/qa/2026-05-22-learning-state-performance-baseline.md
```

Release condition: baseline numbers are recorded and Batch B is allowed only when synthesis budget is met or a windowing flag explicitly reduces scope with a UI hint.

### Phase 0: Finish Current P0 Release Gate

This phase does not add new product scope. It ensures the existing P0 evidence loop is live and observable before the P1 transformation starts.

**Files:**
- Verify existing: `docs/plan/2026-05-21-luban-learning-report-world-class-optimization-plan.md`
- Verify existing: `scripts/run_learning_report_world_class_e2e.py`
- Verify existing: `tests/services/learner_state/*`
- Verify existing: `tests/api/test_mobile_router.py`

- [ ] Run the existing learning report gate.

```bash
python scripts/check_contract_guard.py
python scripts/run_learning_report_world_class_e2e.py
python -m pytest tests/services/learner_state/test_learning_report_read_model.py \
  tests/services/learner_state/test_attempt_detail_read_model.py \
  tests/services/learner_state/test_conversation_learning_evidence_event.py \
  tests/api/test_mobile_router.py -q
```

Expected:

```text
contract-guard: passed
{"ok": true, "output": ".gstack/qa-reports/learning-report-world-class-gate.json"}
all selected pytest tests pass
```

- [ ] Confirm production has no obvious P0 regression before adding P1 logic.

Acceptance:

- Learning report endpoint responds.
- Attempt detail shows real question, answer, explanation and conversation-derived diagnosis when available.
- Home dashboard prompts come from backend-owned projection.
- `degraded_sources` is below release threshold during observation.

### Task 1: Contract Addendum For Learning-State Inference

**Purpose:** Register the new projection surfaces without adding a second authority.

**Files:**
- Modify: `contracts/index.yaml`
- Modify or create: `contracts/learning-state-inference.md`
- Modify: `docs/plan/INDEX.md`
- Test: `scripts/check_contract_guard.py`

- [ ] Add a contract entry for `learning_state_inference`.

Expected contract surfaces:

```yaml
learning_state_inference:
  authority: learner_memory_events.learning_evidence -> learning_synthesis -> learning_report_read_model
  allowed_event_type: learning_evidence
  allowed_evidence_sources:
    - construction_grading
    - conversation_synthesis
  projections:
    - knowledge_state
    - ability_state
    - behavior_state
    - prescription
    - scoring_point_map
  forbidden:
    - second learner memory table
    - frontend mastery derivation
    - recommendation authority outside training_intent / learning_report_read_model
```

- [ ] Run:

```bash
python scripts/check_contract_guard.py
```

Expected:

```text
contract-guard: passed
```

Commit:

```bash
git add contracts/index.yaml contracts/learning-state-inference.md docs/plan/INDEX.md
git commit -m "contracts: register learning state inference surfaces"
```

### Task 2: Case Rubric Evidence Payload

**Purpose:** Make case-answer scoring points first-class evidence inside the existing ledger.

**Files:**
- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Test: `tests/services/construction_grading/test_learning_evidence_payload.py`
- Test: `tests/services/learner_state/test_learning_evidence_quality_gate.py`

- [ ] Write a failing test proving case rubric hits are preserved.

Test shape:

```python
def test_case_rubric_scoring_points_are_preserved_in_learning_evidence_payload():
    payload = build_learning_evidence_payload(
        user_id="student_demo",
        question_id="case_fire_001",
        question_type="case_short_answer",
        user_answer="甲级防火门耐火极限 1.0h",
        correct_answer="甲级 1.5h，乙级 1.0h，丙级 0.5h",
        score_awarded=0,
        max_score=2,
        explanation={"summary": "甲级耐火极限记错。"},
        rubric={
            "rubric_id": "fire_door_v1",
            "rubric_version": "2026-05-22",
            "scoring_points": [
                {
                    "point_id": "fire_rating",
                    "label": "甲乙丙级耐火极限",
                    "max_score": 1,
                    "ability_dimension": "code_application",
                    "knowledge_node_id": "1A421000",
                    "child_concept_label": "防火门耐火极限",
                }
            ],
            "scoring_point_hits": [
                {
                    "point_id": "fire_rating",
                    "hit": False,
                    "awarded_score": 0,
                    "miss_reason": "把甲级 1.5h 记成 1.0h",
                    "evidence_text": "甲级防火门耐火极限 1.0h",
                }
            ],
        },
    )

    assert payload["rubric"]["rubric_id"] == "fire_door_v1"
    assert payload["rubric"]["scoring_point_hits"][0]["miss_reason"] == "把甲级 1.5h 记成 1.0h"
    assert payload["quality"]["detail_ready"] is True
```

- [ ] Run the test and confirm it fails before implementation.

```bash
python -m pytest tests/services/construction_grading/test_learning_evidence_payload.py::test_case_rubric_scoring_points_are_preserved_in_learning_evidence_payload -q
```

Expected before implementation:

```text
FAIL
```

- [ ] Implement minimal payload pass-through and quality validation.

Rules:

- `rubric.scoring_points[]` is required for scoring-point-map eligibility, not for attempt-detail readiness. Attempt detail remains `detail_ready` when the question, learner answer, standard answer or grading explanation, timestamp and evidence ref are present.
- `rubric.scoring_point_hits[]` must not be fabricated by the read model.
- If rubric is missing for a case answer, evidence remains progress-countable but not scoring-point-map eligible.
- `rubric.scoring_point_hits[*].error_code` (if present) must exist in `docs/contracts/error_code_registry.md` from Phase -1.B; emit `unknown_error` if no registered code matches.
- LLM-generated hits that fall outside the rubric_specs (per Phase -1.A reconciliation) must be dropped and logged as `grader_disagreement`, never written into evidence.
- The payload carries `rubric_mode` from `case_kernel` (`grading_key | curated_rubric | projected_rubric | open_skill`); the read model uses this to decide whether to include the attempt in the scoring-point map (only `grading_key` and `curated_rubric` qualify; `projected_rubric` qualifies after Phase -1.A coverage gate is met).

- [ ] Run:

```bash
python -m pytest tests/services/construction_grading/test_learning_evidence_payload.py \
  tests/services/learner_state/test_learning_evidence_quality_gate.py -q
```

Expected:

```text
all tests pass
```

Commit:

```bash
git add deeptutor/services/construction_grading/learning_evidence.py \
  deeptutor/services/construction_grading/writeback.py \
  tests/services/construction_grading/test_learning_evidence_payload.py \
  tests/services/learner_state/test_learning_evidence_quality_gate.py
git commit -m "feat: preserve case rubric evidence"
```

### Task 3: Minimal Expert Graph Seed

**Purpose:** Add a small expert-owned graph seed for high-value construction-practice diagnosis without attempting full automatic graph construction.

**Files:**
- Create: `deeptutor/services/taxonomy/construction_learning_graph.py`
- Test: `tests/services/taxonomy/test_construction_learning_graph.py`

- [ ] Write a failing test for node lookup and edge filtering.

```python
from deeptutor.services.taxonomy.construction_learning_graph import (
    get_learning_graph_node,
    related_learning_graph_edges,
)


def test_learning_graph_exposes_high_value_fire_door_nodes():
    node = get_learning_graph_node("1A421000")

    assert node["label"]
    assert node["node_type"] == "code_provision"
    assert node["exam_weight"] > 0

    edges = related_learning_graph_edges("1A421000", relation="easy_confuse")
    assert any(edge["to"].startswith("1A4") for edge in edges)
```

- [ ] Run and confirm fail:

```bash
python -m pytest tests/services/taxonomy/test_construction_learning_graph.py -q
```

- [ ] Implement only a small seed.

**Important (2026-05-22 audit):** the production `node_code` namespace uses 7-8 character codes like `1A412010`, `1A422000`, `1A436000` (1A4 = 建筑实务). Do **not** invent dotted sub-codes such as `1A421000.fire_door.rating`. The graph seed must reference the actual `node_code` values found in `public.questions_bank`, plus optional **child concept labels** that are not themselves `node_code`s.

Seed node shape:

```python
{
  "node_id": "1A412010",            # must match an existing questions_bank.node_code
  "label": "<from教研 dictionary>",
  "node_type": "knowledge_point",
  "child_concepts": [
    {"id": "1A412010#fire_door_rating", "label": "防火门耐火极限"},
    {"id": "1A412010#fire_door_closing", "label": "防火门双扇顺序关闭"},
  ],
  "exam_weight": 0.0,
}
```

Required seed clusters (picked because the audit shows each cluster has both high question count and high real-exam frequency):

- 一组（防火与构造类）：选取 1A412010、1A412020、1A411010 三个高频 `node_code`，配 3-5 个 `child_concept` 子节点（耐火极限、易混数值、双扇关闭顺序等）。
- 一组（质量验收类）：选取 1A413020、1A413030、1A413040、1A413050、1A413060 五个 `node_code`（混凝土、钢筋、模板、防水等验收要点）。
- 一组（管理实务类）：选取 1A432000、1A433000、1A434000、1A436000 四个 `node_code`（进度、合同索赔、安全、危大）。

Do not build a full textbook graph. Cross-check each seeded node_id against `SELECT DISTINCT node_code FROM public.questions_bank` before merging.

- [ ] Run:

```bash
python -m pytest tests/services/taxonomy/test_construction_learning_graph.py -q
```

Commit:

```bash
git add deeptutor/services/taxonomy/construction_learning_graph.py \
  tests/services/taxonomy/test_construction_learning_graph.py
git commit -m "feat: add minimal construction learning graph seed"
```

### Task 4: Three-Layer Learning State Projection

**Purpose:** Compile knowledge, ability and behavior states from existing evidence.

**Files:**
- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Modify: `deeptutor/services/learner_state/learning_brain_read_model.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] Write a failing test for three-layer state.

```python
def test_synthesis_projects_knowledge_ability_and_behavior_state():
    projection = synthesize_learning_truth(
        user_id="student_demo",
        events=[
            case_event_with_scoring_point_hit(
                knowledge_node_id="1A421000",
                ability_dimension="code_application",
                miss_reason="把甲级 1.5h 记成 1.0h",
                created_days_ago=0,
            ),
            case_event_with_scoring_point_hit(
                knowledge_node_id="1A421000",
                ability_dimension="code_application",
                miss_reason="把甲级 1.5h 记成 1.0h",
                created_days_ago=4,
            ),
        ],
    )

    knowledge = projection["learning_state"]["knowledge_state"][0]
    ability = projection["learning_state"]["ability_state"][0]
    behavior = projection["learning_state"]["behavior_state"][0]

    assert knowledge["label"] == "防火门耐火极限"
    assert knowledge["state"] in {"unstable", "weak"}
    assert ability["dimension"] == "code_application"
    assert ability["state"] == "weak"
    assert behavior["dimension"] == "recurrence"
    assert behavior["state"] == "recurring"
    assert behavior["evidence_count"] == 2
```

- [ ] Run and confirm fail:

```bash
python -m pytest tests/services/learner_state/test_learning_synthesis.py::test_synthesis_projects_knowledge_ability_and_behavior_state -q
```

- [ ] Implement with simple, explainable rules:

Knowledge state levels:

- `observed`: one evidence item, low confidence.
- `unstable`: mixed evidence or recent miss.
- `weak`: repeated negative evidence.
- `improving`: negative then positive revalidation.
- `stable`: repeated positive evidence with recent verification.

Ability dimensions:

- `question_reading`
- `code_application`
- `calculation`
- `expression`
- `transfer`
- `review_execution`

Behavior dimensions:

- `recurrence`
- `forgetting_risk`
- `prescription_follow_through`
- `still_confused`

- [ ] Expose a compact learner-facing shape:

```json
{
  "learning_state": {
    "knowledge_state": [],
    "ability_state": [],
    "behavior_state": [],
    "source_status": {
      "authority": "learner_memory_events.learning_evidence",
      "model": "rule_based_v1"
    }
  }
}
```

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_learning_report_read_model.py -q
```

Commit:

```bash
git add deeptutor/services/learner_state/learning_synthesis.py \
  deeptutor/services/learner_state/learning_brain_read_model.py \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_learning_report_read_model.py
git commit -m "feat: project three-layer learning state"
```

### Task 5: Recency-Aware Confidence And Forgetting Risk

**Purpose:** Stop treating old correctness as current mastery.

**Files:**
- Modify: `deeptutor/services/learner_state/mastery_estimator.py`
- Test: `tests/services/learner_state/test_mastery_estimator.py`

- [ ] Write failing tests:

```python
from deeptutor.services.learner_state.mastery_estimator import estimate_mastery


def test_old_positive_evidence_has_forgetting_risk():
    estimate = estimate_mastery(
        attempts=[
            {"score_ratio": 1.0, "created_at": "2026-04-01T00:00:00+08:00"},
        ],
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] in {"unstable", "needs_revalidation"}
    assert estimate["forgetting_risk"] > 0.5
    assert estimate["needs_revalidation"] is True


def test_recent_revalidation_lowers_forgetting_risk():
    estimate = estimate_mastery(
        attempts=[
            {"score_ratio": 0.0, "created_at": "2026-05-01T00:00:00+08:00"},
            {"score_ratio": 1.0, "created_at": "2026-05-22T00:00:00+08:00"},
        ],
        now_iso="2026-05-22T00:00:00+08:00",
    )

    assert estimate["level"] in {"improving", "stable"}
    assert estimate["forgetting_risk"] < 0.4
```

- [ ] Implement simple time decay, not BKT yet.

Rules:

- Decay is **per ability_dimension**, not global; the threshold comes from `mastery_estimator.DECAY_PROFILES` (see "Forgetting Decay Profiles" section for the initial tiers).
- Repeated negative evidence increases recurrence and prescription priority.
- Conversation explanation lowers "unknown" but does not mark mastery.
- Below-quality conversation turns are filtered before they reach `estimate_mastery`; only `learning_signal_type` ∈ {`answer_explanation`, `still_confused`, `corrected_misconception`, `verified_understanding`} is allowed to influence behavior state.
- `needs_revalidation=True` must enqueue an ARRS-style revalidation probe into the prescription queue (see "ARRS Scheduled Revalidation" section), using the per-dimension `revalidation_schedule` from the profile.
- No global hard-coded "14 days" anywhere outside `DECAY_PROFILES`; a grep for `14` in `mastery_estimator.py` must yield only references to the profile constants.

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_mastery_estimator.py \
  tests/services/learner_state/test_learning_report_read_model.py -q
```

Commit:

```bash
git add deeptutor/services/learner_state/mastery_estimator.py \
  tests/services/learner_state/test_mastery_estimator.py \
  tests/services/learner_state/test_learning_report_read_model.py
git commit -m "feat: add recency-aware mastery confidence"
```

### Task 6: Prescription Intent V2

**Purpose:** Turn "next training" into an evidence-backed prescription loop.

**Files:**
- Modify: `deeptutor/services/learner_state/training_intent.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `deeptutor/services/learner_state/home_personalization.py`
- Test: `tests/services/learner_state/test_training_intent.py`
- Test: `tests/services/member_console/test_home_dashboard_learning_projection.py`

- [ ] Write failing test for prescription phases.

```python
def test_training_intent_v2_contains_repair_expression_transfer_and_probe():
    intent = build_learning_training_intent(
        user_id="student_demo",
        concept_id="1A421000",
        concept_label="防火门耐火极限",
        error_code="M08",
        error_label="规范数字混淆",
        source="learning_report",
        reason="repeated_code_application_error",
        evidence_refs=["attempt_1", "attempt_2"],
        ability_dimension="code_application",
        behavior_state="recurring",
    )

    assert intent["intent_version"] == 2
    assert [step["phase"] for step in intent["prescription_steps"]] == [
        "repair_root",
        "expression_drill",
        "transfer_case",
        "verification_probe",
    ]
    assert intent["success_criteria"]["requires_revalidation"] is True
```

- [ ] Run and confirm fail:

```bash
python -m pytest tests/services/learner_state/test_training_intent.py::test_training_intent_v2_contains_repair_expression_transfer_and_probe -q
```

- [ ] Implement v2 while preserving v1 fields. v2 is purely additive: every v1 consumer must keep reading the v1 keys until they migrate. Removing v1 keys requires a follow-up cleanup task tracked under "v1 retirement" in `docs/plan/INDEX.md`.

- [ ] Wire `study_plan.py` to read the active `training_intent` (per Phase -1.C), so the home dashboard study card and the report prescription card never disagree about today's focus.

- [ ] Enforce `error_code` validation against `docs/contracts/error_code_registry.md`; reject creation if the code is unregistered.

- [ ] Cap concurrent prescriptions per learner to 3; additional intents go into `queued` state with `priority` derived from `(forgetting_risk × exam_weight × recurrence)`.

Required fields:

```json
{
  "intent_version": 2,
  "source": "learning_report",
  "concept_id": "1A421000",
  "concept_label": "防火门耐火极限",
  "error_code": "M08",
  "error_label": "规范数字混淆",
  "ability_dimension": "code_application",
  "behavior_state": "recurring",
  "evidence_refs": ["attempt_fire_001", "attempt_fire_002"],
  "prescription_steps": [
    {"phase": "repair_root", "question_count": 2},
    {"phase": "expression_drill", "question_count": 1},
    {"phase": "transfer_case", "question_count": 1},
    {"phase": "verification_probe", "question_count": 1}
  ],
  "success_criteria": {
    "requires_revalidation": true,
    "min_correct_probe_count": 1,
    "max_repeat_error_count": 0
  }
}
```

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_training_intent.py \
  tests/services/member_console/test_home_dashboard_learning_projection.py \
  tests/services/learner_state/test_learning_report_read_model.py -q
```

Commit:

```bash
git add deeptutor/services/learner_state/training_intent.py \
  deeptutor/services/learner_state/learning_report_read_model.py \
  deeptutor/services/learner_state/home_personalization.py \
  tests/services/learner_state/test_training_intent.py \
  tests/services/member_console/test_home_dashboard_learning_projection.py \
  tests/services/learner_state/test_learning_report_read_model.py
git commit -m "feat: add prescription training intent v2"
```

### Task 7: Scoring Point Map Read Projection

**Purpose:** Let the student see repeated scoring-point misses, not only generic mistakes.

**Files:**
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `wx_miniprogram/utils/learning-report-view-model.js`
- Modify: `yousenwebview/packageDeeptutor/utils/learning-report-view-model.js`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`
- Test: `wx_miniprogram/tests/test_report_view_model.js`
- Test: `yousenwebview/tests/test_report_snapshot_dedupe.js`

- [ ] Write failing backend test:

```python
def test_learning_report_exposes_scoring_point_map_from_rubric_evidence():
    report = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([
            case_event_with_scoring_point_miss(
                point_id="fire_rating",
                point_label="甲乙丙级耐火极限",
                ability_dimension="code_application",
            )
        ]),
        schema_version=2,
    )

    item = report["scoring_point_map"]["items"][0]
    assert item["point_label"] == "甲乙丙级耐火极限"
    assert item["ability_dimension"] == "code_application"
    assert item["miss_count"] == 1
    assert item["next_action"]["intent"]["intent_version"] == 2
```

- [ ] Implement read projection only.

Rules:

- It reads existing evidence.
- It does not write a new table.
- It only includes evidence with normalized rubric or rubric-equivalent hits. `grading_key` and curated rubric render as `采分点`; projected keyword-only evidence renders as `审题要点` until upgraded.
- It marks empty state clearly when there is no case rubric evidence.
- It promotes scoring-point map rows per `node_code` cluster only when that cluster passes the ≥ 70% map-eligible gate; weaker clusters stay in `rubric_pending`.

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_learning_report_read_model.py -q
node wx_miniprogram/tests/test_report_view_model.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
```

Commit:

```bash
git add deeptutor/services/learner_state/learning_report_read_model.py \
  wx_miniprogram/utils/learning-report-view-model.js \
  yousenwebview/packageDeeptutor/utils/learning-report-view-model.js \
  tests/services/learner_state/test_learning_report_read_model.py \
  wx_miniprogram/tests/test_report_view_model.js \
  yousenwebview/tests/test_report_snapshot_dedupe.js
git commit -m "feat: expose scoring point map projection"
```

### Task 8: Student UI - State / Reason / Action / Evidence

**Purpose:** Reframe the learning report UI around actionable learning state.

**Files:**
- Modify: `wx_miniprogram/pages/report/report.js`
- Modify: `wx_miniprogram/pages/report/report.wxml`
- Modify: `wx_miniprogram/pages/report/report.wxss`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.js`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.wxss`
- Test: `wx_miniprogram/tests/test_report_layout.js`
- Test: `wx_miniprogram/tests/test_report_learning_brain.js`
- Test: `yousenwebview/tests/test_report_layout.js`

- [ ] Write snapshot/view-model assertions before UI edits.

Expected sections:

```text
今日处方
知识状态
能力状态
行为状态
采分点漏分
真实作答证据
```

- [ ] Implement UI from backend projections only.

Rules:

- No frontend mastery calculation.
- No frontend weak-point ranking.
- No frontend prompt generation.
- Empty states must be honest: "完成一次案例题批改后生成采分点地图".
- Cold-start: when `learning_state.bootstrap=true` (no evidence yet), first viewport replaces the prescription hero with an "开始一次起步测评" CTA that launches a 3-题 calibration intent; do not show any state/weakness label.
- Abandonment recovery: if `prescription_outcomes[*].status == "assigned"` and last interaction > 24h, render a "继续上次未完成的训练" banner above the today-prescription card, citing the original evidence refs.
- Multi-prescription: show at most 3 active cards with explicit `priority` order; queued intents collapse into a "稍后的训练" footer.
- Quota / tier: when the backend marks `prescription_cta.gated_by="quota_exceeded"`, render the CTA in a clear paid-tier prompt; never hide the state.
- All Chinese strings in the report page must live in the existing i18n string bag for `wx_miniprogram` and `yousenwebview`; new strings must be added in one place and referenced by key.

- [ ] Run:

```bash
node wx_miniprogram/tests/test_report_layout.js
node wx_miniprogram/tests/test_report_learning_brain.js
node yousenwebview/tests/test_report_layout.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
```

Commit:

```bash
git add wx_miniprogram/pages/report/report.js \
  wx_miniprogram/pages/report/report.wxml \
  wx_miniprogram/pages/report/report.wxss \
  yousenwebview/packageDeeptutor/pages/report/report.js \
  yousenwebview/packageDeeptutor/pages/report/report.wxml \
  yousenwebview/packageDeeptutor/pages/report/report.wxss \
  wx_miniprogram/tests/test_report_layout.js \
  wx_miniprogram/tests/test_report_learning_brain.js \
  yousenwebview/tests/test_report_layout.js \
  yousenwebview/tests/test_report_snapshot_dedupe.js
git commit -m "feat: reframe report as actionable learning state"
```

### Task 9: Prescription Completion And Revalidation Evidence

**Purpose:** Close the loop so prescriptions produce evidence and can be verified.

**Files:**
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `tests/services/construction_grading/test_audit_and_writeback.py`
- Modify: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] Write failing test:

```python
def test_verification_probe_updates_prescription_outcome():
    report = build_learning_report_read_model(
        user_id="student_demo",
        member_service=FakeMemberService(),
        learner_state_service=FakeLearnerStateService([
            prescription_event("intent_fire", status="assigned"),
            verification_probe_event("intent_fire", score_ratio=1.0),
        ]),
        schema_version=2,
    )

    loop = report["prescription_outcomes"][0]
    assert loop["training_intent_id"] == "intent_fire"
    assert loop["status"] == "verified"
    assert loop["evidence_refs"]
```

- [ ] Implement evidence fields:

```json
{
  "training_intent_id": "intent_fire",
  "prescription_phase": "verification_probe",
  "prescription_result": {
    "status": "verified",
    "score_ratio": 1.0
  }
}
```

- [ ] Run:

```bash
python -m pytest tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/learner_state/test_learning_report_read_model.py -q
```

Commit:

```bash
git add deeptutor/services/construction_grading/writeback.py \
  deeptutor/services/learner_state/learning_report_read_model.py \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/learner_state/test_learning_report_read_model.py
git commit -m "feat: track prescription verification outcomes"
```

### Task 10: Teacher And Sales Evidence Story Projection

**Purpose:** Create a read projection for teacher/sales evidence-chain demos without creating a new authority.

**Files:**
- Create: `deeptutor/services/learner_state/evidence_story_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py` only if a stable endpoint is needed after internal validation
- Test: `tests/services/learner_state/test_evidence_story_read_model.py`

- [ ] Write failing test:

```python
def test_evidence_story_links_initial_state_attempt_cluster_prescription_and_revalidation():
    story = build_evidence_story_read_model(
        user_id="student_demo",
        evidence_events=[
            case_event_with_scoring_point_miss(point_id="claim_procedure"),
            case_event_with_scoring_point_miss(point_id="claim_procedure"),
            prescription_event("intent_claim", status="assigned"),
            verification_probe_event("intent_claim", score_ratio=1.0),
        ],
    )

    assert story["headline"]
    assert story["evidence_chain"][0]["type"] == "initial_pattern"
    assert story["evidence_chain"][-1]["type"] == "verified_improvement"
    assert story["sales_summary"]["value_claim"] == "不是多刷题，而是定位丢分机制并验证修复"
```

- [ ] Implement as service-only projection first.

Rules:

- Do not add a public endpoint until the projection has service tests.
- Do not include private raw chat text without redaction.
- Every story claim must cite event refs.
- A dedicated `redact_chat_text(text) -> str` helper masks PII patterns (phone, email, ID number, mention names) before any chat snippet appears in the story; unit tests assert no raw PII string survives.
- The projection emits at most one anonymized sample per evidence cluster; learner identifiers are replaced with stable anonymous handles (`learner_a`, `learner_b`).
- Sales summary uses a closed enum of value claims; freeform marketing copy is forbidden inside the projection.

- [ ] Run:

```bash
python -m pytest tests/services/learner_state/test_evidence_story_read_model.py -q
```

Commit:

```bash
git add deeptutor/services/learner_state/evidence_story_read_model.py \
  tests/services/learner_state/test_evidence_story_read_model.py
git commit -m "feat: add learning evidence story projection"
```

## Observability And Metrics

Every batch must expose these metrics before it can claim "shipped". Metrics live in the existing observability stack; no new dashboards are required, but a `learning_state_inference` panel must exist and be linked from the release report.

### Required Metrics

- `learning_evidence_completeness_rate`: share of recent `learning_evidence` events that carry the new payload fields (`rubric.scoring_points`, `knowledge_refs`, `ability_signals`).
- `rubric_map_eligible_ratio`: share of recent case attempts whose normalized projection yields ≥ 2 distinct scoring points from `grading_key`, curated rubric, `structured_rules`, or `grading_keywords`. Gate ≥ 0.70 globally to promote the full scoring-point map UI.
- `rubric_map_eligible_ratio_by_cluster`: same metric grouped by `node_code` prefix. Gate ≥ 0.70 per cluster to promote that cluster while the global view remains `rubric_pending`.
- `keyword_only_rubric_ratio`: share of map-eligible items whose projection comes only from `grading_keywords`; these render as `审题要点`, not full `采分点`.
- `grader_disagreement_rate`: share of case attempts that triggered a `grader_disagreement` audit row. Alert if > 0.05 over a rolling 7-day window.
- `evidence_refs_coverage_rate`: share of visible diagnosis cards (knowledge state, ability state, behavior state, scoring point map, prescription) that carry non-empty `evidence_refs`. Gate ≥ 0.90.
- `prescription_verification_rate`: share of `assigned` prescriptions that reached `verified` within 7 days. Tracked as the headline learning-outcome metric.
- `prescription_abandon_rate`: share of `assigned` prescriptions that aged past 7 days without verification.
- `home_prompt_click_to_evidence_rate`: share of `home_prompt_clicked` events that produced a follow-up `conversation_synthesis` learning evidence within 30 minutes.
- `learning_report_p95`: production latency of `/api/v1/mobile/learning-report`. Gate ≤ 600ms.
- `learning_synthesis_p95`: server-side synthesis latency. Gate ≤ 200ms on a 2000-event window.
- `degraded_sources_rate`: share of report responses that name any degraded source. Gate ≤ 0.05.
- `legacy_evidence_share`: share of rendered evidence that comes from `legacy_evidence` (no new payload). Used to track backfill / decay progress, not gated.

### Required Logs (Structured, Per-Event)

- `learning_evidence_quality_class`: per-event classification (`full | partial | legacy | rejected`).
- `grader_disagreement`: per case attempt where LLM dissented from curated rubric.
- `prescription_lifecycle`: per intent lifecycle transition with timestamp and source.
- `home_prompt_action`: per home-prompt click and the downstream evidence produced.

### Required Alarms

- `rubric_map_eligible_ratio` or a promoted cluster's `rubric_map_eligible_ratio_by_cluster` drops > 10 pp week-over-week → block Batch C UI promotion until investigated.
- `grader_disagreement_rate` > 0.10 over 24h → page on-call, freeze new LLM grader rollouts.
- `learning_report_p95` > 800ms for 15 minutes → automatic Batch C rollback to baseline rendering (no three-layer state, no scoring-point map).
- `prescription_abandon_rate` > 0.5 for 7 days → product review of prescription wording and difficulty.

## Feature Flag And Progressive Rollout

### Implementation Decision (2026-05-22): Custom Minimal Helper

After surveying the repo (no GrowthBook, no LaunchDarkly, no third-party flag SDK in `deeptutor/`), the right answer for this transformation is **a minimal in-repo cohort helper**, not introducing GrowthBook.

Reasoning:

- This is a single-axis transformation, not a long-term experimentation platform — paying for a flag SDK runtime is overkill.
- AGENTS §0 "Thin Wrappers Fat Skills" prefers a small internal module over a third-party dependency for a one-time control plane.
- The kill-switch budget is < 5 minutes. Env-var-driven flags with a SIGHUP / poll reload satisfy this without depending on an external service that could itself be the failure mode.
- Aliyun SSH write boundary (AGENTS §3.7) is easier to honor with env vars in `/root/deeptutor/.env` than with a SaaS dashboard outside the repo.
- The contract can stay pluggable: the helper exposes a `is_enabled(flag, user_id) -> bool` interface that a future GrowthBook adapter can satisfy without changing call sites.

Implementation outline (kept tiny on purpose, not in this plan's code work — it is the prerequisite that Phase -1 enables):

- File: `deeptutor/services/experiments/cohort.py` (≤ 100 lines).
- API: `is_enabled(flag: str, user_id: str | None = None) -> bool` and `current_stage(flag: str) -> str`.
- Stage source: env var `<FLAG>_STAGE` (e.g. `LEARNING_STATE_INFERENCE_V2_STAGE`).
- Sub-gate source: env vars `<FLAG>_<SUBGATE>_STAGE` (e.g. `LEARNING_STATE_INFERENCE_V2_EVIDENCE_STAGE`).
- Cohort assignment: deterministic `sha256(f"{flag}:{user_id}").digest()[0] % 100 < cohort_percent`.
- Internal allowlist: env var `<FLAG>_INTERNAL_USERS` accepts a comma-separated list (always-on for dogfood).
- Hot reload: helper reads env at call time; no in-memory cache to avoid SIGHUP plumbing. The cost is negligible against the rest of the request.
- Tests: `tests/services/experiments/test_cohort.py` covers determinism, stage progression, sub-gate isolation, internal allowlist, and kill-switch behavior (set `_STAGE=off`, helper returns `False` for everyone within a single env reload).

If, later, GrowthBook is adopted at a higher level, this helper becomes a one-day adapter swap rather than a multi-day refactor.

### Stages

The whole transformation is gated by a single environment-aware flag `LEARNING_STATE_INFERENCE_V2` with these stages.

- `off`: only Phase 0 baseline runs; new payload fields may be written but read model ignores them.
- `internal`: dogfood account list only; full new projections visible.
- `cohort_10`: 10% of opted-in learners (deterministic hash of user_id); production observability fully on.
- `cohort_50`: 50% rollout after 7 days of green cohort_10 metrics.
- `cohort_100`: full rollout after 7 days of green cohort_50 metrics.
- `sticky_100`: flag removed only after success criteria sustained for 14 days.

Kill switch: setting the flag to `off` must restore the prior UI in < 5 minutes without redeploy. This is verified during Phase -1.D bench by toggling the flag and re-running the report read model.

Each batch carries its own sub-gate so partial rollout is possible:

- `LEARNING_STATE_INFERENCE_V2.evidence` — Batch A payload fields.
- `LEARNING_STATE_INFERENCE_V2.state_projection` — Batch B three-layer state.
- `LEARNING_STATE_INFERENCE_V2.action_loop` — Batch C prescription v2 + UI.
- `LEARNING_STATE_INFERENCE_V2.verification` — Batch D revalidation + story.

Promotion of a sub-gate requires the previous sub-gate to be green for at least 72 hours.

## Data Migration And Backward Compatibility

There is no destructive migration. The plan is forward-only.

- Existing `learner_memory_events.learning_evidence` rows without the new payload fields remain valid; the read model treats them as `legacy_evidence`.
- No schema mutation on `learner_memory_events`.
- New payload fields appear inside the JSON payload, gated by Phase -1 readiness.
- A nightly job (`scripts/backfill_legacy_evidence_classification.py`) classifies recent events by quality class so observability reflects ground truth. It must not mutate evidence payloads.
- Read models must treat the absence of `rubric`, `knowledge_refs`, or `ability_signals` as expected, not as an error.
- The contract guard guarantees that a "weak point", "scoring point miss", or "prescription" never claims to cite an evidence ref that the read model could not resolve.

## Branch And PR Strategy

Per AGENTS §3.6, this plan is broken into bounded PRs rather than one branch.

- Branch root: `codex/luban-learning-state-engine-2026-05-22/<batch>-<task>`.
- One PR per task in Phase -1 (4 PRs) and one PR per task in Batches A through D (10 PRs).
- Each PR includes:
  - Code + tests + (if needed) docs and contract changes.
  - Updated `docs/plan/INDEX.md` entry.
  - Release report block listing local HEAD, origin SHA, deployed SHA, WeChat DevTools screenshots when UI is touched.
  - Risk note referencing the matching row in "Uncertainties And Validation Plan".
- No PR merges to `project1` (main) without:
  - Contract guard passing.
  - Required tests passing.
  - At least one human reviewer plus `everything-claude-code:python-review` + (for grading code) `everything-claude-code:security-review`.
- Worktrees are used only when two tasks must run truly in parallel; the default is sequential to keep `learning_synthesis.py` and `learning_report_read_model.py` editable without merge thrash.

## Rollback Runbook

Every batch defines a known-good fallback. Rollback never deletes data; it only stops reading new projections.

- Batch A rollback: set `LEARNING_STATE_INFERENCE_V2.evidence=off`. Grader continues to write minimal payload; new payload fields stay dormant but are ignored.
- Batch B rollback: set `LEARNING_STATE_INFERENCE_V2.state_projection=off`. Report falls back to existing learning brain projection. Three-layer state cards hide.
- Batch C rollback: set `LEARNING_STATE_INFERENCE_V2.action_loop=off`. UI returns to the V1 prescription card and removes the scoring-point map section.
- Batch D rollback: set `LEARNING_STATE_INFERENCE_V2.verification=off`. Verification probes stop being generated; prescription_outcomes remains visible as audit-only.

Rollback drill:

- At the end of cohort_10 and cohort_50, a planned 15-minute kill-switch drill verifies the UI degrades cleanly.
- Drill report attaches WeChat DevTools snapshots before, during, and after rollback.

## Quantitative A/B Comparison

To prove the new system is actually better — not just "more elaborate" — the plan runs a paired comparison with a **sequential gate** that recognizes early-cohort sample size will be small (likely 100-400 learners per arm).

- Cohorts: `control` (V2 off) vs `treatment` (V2 on), deterministic by user_id hash, balanced by member tier and recent activity.
- Primary metric: `weekly_correct_uplift` — change in mean attempt correctness on case items within 14 days of joining the cohort.

### Sequential Promotion Gate

The promotion criteria scale with cohort size to avoid both (a) under-powered cohort_10 forcing a false "not significant" rollback and (b) over-fitting on a tiny sample.

| Stage | Min sample per arm | Primary metric gate | Statistical test | Secondary check |
| --- | --- | --- | --- | --- |
| cohort_10 → cohort_50 | ≥ 100 active learners per arm with ≥ 5 case attempts each in the window | `weekly_correct_uplift` directional positive (>= +3pp) **and** p < 0.10 one-tailed Mann-Whitney | One-tailed because we are testing "treatment ≥ control", not "different" | Directional consistency on at least 2 of 3 secondary metrics |
| cohort_50 → cohort_100 | ≥ 400 active learners per arm | `weekly_correct_uplift` ≥ +5pp **and** p < 0.05 two-tailed Mann-Whitney | Two-tailed because we now have power to claim "different" | All 3 secondary metrics non-regressing; at least 2 of 3 improving |
| cohort_100 → sticky_100 | Full traffic | `weekly_correct_uplift` sustained ≥ +5pp over 14 days **and** `prescription_verification_rate` ≥ 0.40 | Rolling 14-day Mann-Whitney p < 0.05 | All 3 secondary metrics improving |

### Underpowered / Inconclusive Handling

- If cohort_10 fails the minimum sample size after 7 days, **hold at cohort_10 for up to 14 more days** rather than auto-rollback; treat this as an evaluation issue, not a product failure.
- If after 21 days at cohort_10 the sample is still under the minimum, promote to cohort_50 **only if** directional signal is positive on primary + 2 secondary metrics, and document this as an explicit "low-power promotion" in the cohort report.
- If primary metric trends negative (≤ -2pp) for 7 days at any cohort stage, trigger the matching batch rollback (see Rollback Runbook).

### Secondary Metrics (Required, Same Window)

- `prescription_verification_rate` — must be ≥ 0.40 in treatment at cohort_50, ≥ 0.30 at cohort_10.
- `weekly_active_days` — must not regress vs control by > 0.3 days.
- `mistake_recurrence_rate` over 7-day clusters — must decrease in treatment vs control.

### Survey Metric (Required At Every Stage)

5-question understanding survey administered to 5-10 learners per cohort by 销售 / 客户成功:

1. 你的"今日处方"是什么？
2. 系统为什么推荐这个？
3. 这个推荐的依据是哪几次作答？
4. 完成后系统会怎么验证你掌握了？
5. 如果你不同意系统的判断，你会怎么做？

Treatment learners must answer 4 / 5 of these with reference to specific evidence (not vague "因为我错了很多题"). Failure on this metric blocks promotion regardless of statistical significance — comprehension is a kill switch for "elaborate but confusing" outcomes.

### Reports

- `docs/qa/2026-05-22-learning-state-inference-cohort-report.md` — published after each stage.
- Each report must declare which gate type was used (full power vs low-power promotion) and list the exact sample size, p-value, effect size and confidence interval.
- Negative or null results are first-class citizens; do not omit a stage report because it did not pass.

## Mistake Clustering Algorithm

To prevent duplicate diagnosis cards, attempts are clustered. The clustering algorithm is intentionally simple and explainable.

- Cluster key: `(primary_knowledge_node_id, ability_dimension, error_code)`.
- Secondary key for tie-break: same `scoring_point.point_id` (case only).
- Time window: trailing 30 days; older evidence joins as `historical_evidence` with reduced weight.
- Persistence: clusters live as a derived field in `learning_synthesis`; cluster_id is stable across syntheses for the same key.
- Display rules:
  - A cluster with ≥ 2 negative attempts surfaces as a single diagnosis card with all evidence refs.
  - A cluster with a successful verification probe collapses into a "已修复" footnote.
  - Mixed clusters show the current state plus a trend line.
- Test coverage: `tests/services/learner_state/test_mistake_clustering.py` covers cluster creation, deduplication, decay, and verification-driven collapse.

## Forgetting Decay Profiles (Ability-Dimension Tiered)

The original plan default of "14 days for everything" is too coarse. Different ability dimensions decay at materially different rates, and a one-size threshold either over-prompts learners on slow-decaying skills or under-prompts them on fast-decaying memorization. The plan replaces the single number with a tiered profile.

### Initial Tiered Defaults (2026-05-22)

These are starting points informed by spaced-repetition research (Ebbinghaus, Karpicke, Anki/SM-2 intervals) adapted for high-stakes adult exam prep. They are **defaults**, not science — they are explicitly meant to be tuned with real cohort_10 data.

| ability_dimension | decay_half_life_days | first_revalidation_days | rationale |
| --- | --- | --- | --- |
| `code_application` | 10 | 3, 7, 14, 30 | 规范数值类记忆，遗忘最快；高频复测 |
| `calculation` | 14 | 3, 7, 14, 30 | 计算类需多次复现以稳定流程，中速衰减 |
| `question_reading` | 21 | 7, 14, 30 | 审题习惯一旦养成相对稳定，慢衰减 |
| `expression` | 21 | 7, 14, 30 | 得分表达靠刻意练习；学会后保留较好 |
| `transfer` | 28 | 14, 30, 60 | 跨知识点迁移最慢稳定，但稳定后保留最久 |
| `review_execution` | dynamic | 由 prescription 行为驱动 | 不按时间，而按是否完成处方与复盘 |

### Where The Profile Lives

- `deeptutor/services/learner_state/mastery_estimator.py` exposes `DECAY_PROFILES: dict[str, DecayProfile]`.
- Each profile carries `decay_half_life_days`, `revalidation_schedule` (the cadence in days for ARRS probes), and a per-dimension `confidence_floor` (below which the state shows "需要一次验证题确认").
- The profile dictionary is the **only place** to tune decay; no other module hard-codes a forgetting threshold.

### Validation And Tuning Plan

- At cohort_10 close-out, the cohort report includes a **predicted-vs-actual decay table**: for learners whose ARRS probe fired at the scheduled time, how often did they regress vs. retain? A regression rate > 60% on a dimension's first-revalidation point means we waited too long (shorten interval). A regression rate < 20% means we waited too little (lengthen interval).
- Adjust by at most one tier per dimension per cohort cycle to avoid thrashing.
- Document each tuning change in `docs/qa/2026-XX-XX-decay-profile-tuning.md` with the data that drove it.

### Why Not Adopt BKT / DKT Now

Even with tiered profiles, this is a **rule-based estimator**. The plan deliberately defers BKT until:

1. We have at least 12 weeks of per-learner attempt history.
2. Per-question item difficulty is at least loosely calibrated (Phase -1.A coverage + later IRT-lite).
3. Rule-based confidence has stabilized so we can compare BKT against an honest baseline rather than against "anything".

Defaulting to BKT before evidence quality is stable would replace one black box with another. The tiered rule is the smallest move that materially beats the single-threshold default.

## ARRS Scheduled Revalidation

The plan implements ASSISTments-style revalidation as a queued probe, not a real-time decision.

- Trigger: `mastery_estimator.needs_revalidation=True` OR a previously weak cluster crosses 7d / 14d / 30d since last evidence.
- Implementation: `deeptutor/services/learner_state/revalidation_queue.py` (new, ≤ 200 lines) reads recent state and emits a `training_intent` with `kind="revalidation_probe"`.
- Scheduling cadence: 1d, 3d, 7d, 14d after a verified improvement; 3d, 7d after an unverified weak observation.
- Capacity: at most 1 revalidation probe per learner per day.
- UI: probes appear in the prescription queue with a "复习验证" badge; declining a probe pushes it back by 1 day, not forever.
- Test coverage: `tests/services/learner_state/test_revalidation_queue.py` covers cadence, capacity, decline behavior, and verification-driven removal.

## Knowledge Graph Governance

The Phase -1 / Task 3 seed graph must grow safely.

- Source of truth: `deeptutor/services/taxonomy/construction_learning_graph.py`.
- Version: every node carries `version` and `effective_from`; changes are PRs reviewed by 教研 + 数据 + Claude review agent.
- Cross-check: contract guard validates that every `knowledge_node_id` referenced in evidence payloads, rubric specs, and training intents exists in the graph.
- Growth cadence: at most 2 new clusters per week to keep review quality high.
- Retirement: nodes are not deleted; they are marked `deprecated_at` so historical evidence keeps resolving.

## PII Redaction Policy

Sales / teacher story projection is the only path where user-facing conversation could leave the learner boundary. The policy is strict.

- Module: `deeptutor/services/learner_state/redaction.py` (new, ≤ 200 lines).
- Patterns redacted: phone (`\d{11}` formatted), email (`<x>@<y>`), Chinese name lists (configurable list), Chinese ID number (`[0-9Xx]{18}`), address keywords (`市/区/号`), and free-form mention markers (`@xxx`).
- Allowed surface: short paraphrased sentences only; never a raw learner chat quote.
- Test: `tests/services/learner_state/test_evidence_story_pii_redaction.py` asserts no raw PII pattern survives in any field of the story payload.
- The contract guard adds a unit-test enforcement that any new field in `evidence_story_read_model.py` is either an enum or runs through `redact_chat_text()`.

## Test Data Fixture Generator

To make the 20-row scenario matrix verifiable, the plan adds a fixture generator.

- Module: `tests/fixtures/learning_state_scenarios.py` (new).
- Each scenario in the matrix has a named builder that returns a complete `learner_memory_events` event sequence ready for synthesis and read model tests.
- The generator is reused by service tests, view-model tests, and the snapshot suite.

## Release Gate

Before release:

```bash
python scripts/check_contract_guard.py
python scripts/run_learning_report_world_class_e2e.py
python -m pytest tests/services/learner_state/ tests/services/construction_grading/ tests/api/test_mobile_router.py -q
node wx_miniprogram/tests/test_report_view_model.js
node wx_miniprogram/tests/test_report_learning_brain.js
node wx_miniprogram/tests/test_report_layout.js
node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
node yousenwebview/tests/test_report_layout.js
node yousenwebview/tests/test_home_dashboard_learning_prompts.js
```

Manual acceptance:

- WeChat DevTools report page.
- WeChat DevTools attempt detail page.
- Conversation home prompt click -> chat -> conversation evidence -> report/home feedback loop.
- At least one case-rubric example showing scoring-point miss and next prescription.

Production observation:

- `/api/v1/mobile/learning-report` p95 remains within existing release budget (≤ 600ms).
- `learning_synthesis_p95` ≤ 200ms on 2000-event window.
- `degraded_sources_rate` ≤ 0.05.
- `evidence_refs_coverage_rate` ≥ 0.90.
- `rubric_map_eligible_ratio` ≥ 0.70 for global scoring-point map promotion, or per-cluster gates explicitly limit the UI to qualifying `node_code` prefixes while the rest stays in `rubric_pending`.
- `grader_disagreement_rate` ≤ 0.05.
- `prescription_verification_rate` measured and reported (no hard gate before Batch D).
- Feature flag `LEARNING_STATE_INFERENCE_V2` is in the correct cohort stage and a kill-switch drill has been recorded.
- No duplicate learning facts.
- No local-storage-only mistake or prescription state.
- No frontend-derived mastery.
- A/B comparison report attached for cohort_10 and cohort_50 promotions.

Pre-release attestations required in the release PR body:

- Phase -1.A coverage baseline file path + numbers.
- Phase -1.B registry diff (codes added or modified).
- Phase -1.C reconciliation test commit SHA.
- Phase -1.D performance baseline file path + numbers.
- Local HEAD, origin SHA, deployed Aliyun SHA, WeChat DevTools screenshot bundle path.

## Success Criteria

The plan is successful only if the learner can answer these questions within one screen and one click:

1. What is my current weakest learning state?
2. Is it a knowledge problem, ability problem or behavior pattern?
3. What evidence proves it?
4. What should I do next?
5. How will the system verify that I improved?

Measurable acceptance:

- `evidence_refs_coverage_rate` ≥ 0.90 over a 7-day production window.
- 0 mini-program files derive mastery, weak-point rank, training priority or recommended prompt text (verified by a `scripts/audit_frontend_inference.py` grep gate).
- At least one case-rubric scenario in production shows original question, learner answer, system explanation, scoring-point miss and next prescription in one navigation path.
- Conversation-home prompt click produces `home_prompt_clicked` or follow-up conversation evidence in ≥ 70% of clicks (`home_prompt_click_to_evidence_rate ≥ 0.70`).
- A repeated mistake cluster is deduped into one diagnosis card with multiple evidence refs (verified by the test fixture for "repeated same miss").
- A verification probe can move a state from `weak` or `unstable` to `improving` or `stable` (verified by Task 9 fixture + production sample).
- `prescription_verification_rate` ≥ 0.40 in treatment cohort.
- `mistake_recurrence_rate` decreases in treatment cohort vs control over 14 days.
- `weekly_correct_uplift` in treatment beats control by ≥ 5 pp with p < 0.05.
- `/api/v1/mobile/learning-report` p95 ≤ 600ms after the new projection fields (under cohort_50 traffic).
- `learning_synthesis_p95` ≤ 200ms on 2000-event window.
- `rubric_map_eligible_ratio` ≥ 0.70 once the global Batch C UI is promoted; before that, only clusters with `rubric_map_eligible_ratio_by_cluster ≥ 0.70` may show the map, and other clusters must stay in `rubric_pending`.
- `grader_disagreement_rate` ≤ 0.05 over rolling 7 days.
- `degraded_sources_rate` ≤ 0.05.
- WeChat DevTools visible regression confirms no "加载失败" card remains for data that exists in backend projection.
- A documented rollback drill exists for each batch (15-minute kill-switch verified).
- A documented PII redaction test passes for the evidence story projection.
- The error-code registry has zero unregistered codes emitted in production over 7 days.

## Review Checklist

- [ ] All new learning facts enter `learner_memory_events.learning_evidence`.
- [ ] Conversation evidence remains `event_type=learning_evidence` with `evidence_source=conversation_synthesis`.
- [ ] Case rubric evidence remains part of grading evidence, not a second attempt table.
- [ ] Mastery and prescriptions are projections from evidence, not frontend calculations.
- [ ] Recommendation explanations cite evidence refs.
- [ ] Every UI metric has an action.
- [ ] Every action can produce follow-up evidence.
- [ ] Conversation-home prompt buttons use backend intent and evidence refs.
- [ ] Attempt detail exposes historical question, learner answer, timestamp and system explanation.
- [ ] No new stable external endpoint is added before contract registration.
- [ ] No model larger than rule-based/time-decay/Bayesian smoothing is added in this phase.
- [ ] Phase -1.A rubric coverage baseline published and gate honored.
- [ ] Phase -1.B error code registry referenced by all emitting modules; contract guard enforces it.
- [ ] Phase -1.C `study_plan` reads from `training_intent`; no duplicate prescription authority.
- [ ] Phase -1.D performance baseline measured; synthesis windowing flag exists.
- [ ] Feature flag `LEARNING_STATE_INFERENCE_V2` and four sub-gates are wired and verified by a kill-switch drill.
- [ ] Mistake clustering uses `(primary_knowledge_node_id, ability_dimension, error_code)` and is covered by dedicated tests.
- [ ] ARRS revalidation queue exists and is capped at 1 probe per learner per day.
- [ ] Knowledge graph governance: every `knowledge_node_id` in evidence is resolvable in the seed graph.
- [ ] PII redaction passes for evidence story projection; no raw chat quote remains.
- [ ] Cold-start, abandonment, multi-prescription, multi-device, free-tier, low-quality-chat, contradiction, backfill, and revalidation scenarios are all in the scenario matrix and covered by fixtures.
- [ ] A/B cohort comparison report exists for cohort_10 before promoting to cohort_50.
- [ ] Rollback runbook recorded per batch.
- [ ] Worktree/branch strategy honored: one PR per task, no batched mega-PRs.
- [ ] `docs/plan/INDEX.md` updated with this plan and all sub-task PRs.

## Resolved Decisions (2026-05-22)

These four decisions were made at plan-finalization time and supersede the earlier "Open Questions" block. They are the binding answers Phase -1 starts from.

### Decision 1: Rubric Coverage Strategy (Reality-Adjusted After Supabase Audit)

**Measured reality (2026-05-22, queried against production via `scripts/rubric_coverage_report.py`, full table in `docs/qa/2026-05-22-rubric-coverage-baseline.md`):**

- `grading_rubric` on `questions_bank`: **0 / 4,638 rows** populated. The original "some basis exists" assumption was optimistic; the dedicated rubric field is empty.
- `grading_keywords` on case_study items: **49.0% populated** (960 / 1,961).
- `structured_rules` on case_study items: **33.7% populated** (661 / 1,961), and inspection shows these rules are **already scoring-point-shaped** (with `requirement`, `condition`, `consequence`, `automation_slots`).
- `correct_answer` on case_study items: **99.4% populated**.
- `node_code` (knowledge mapping): **97.7% populated**.
- `question_intelligence`: only **43 / 4,638 rows compiled (~0.9%)**.
- `cited_standard_codes`: only **0.7%** — effectively empty.

**Map-eligibility headline (case_study, 1,961 items):**

- `structured_rules >= 2 entries`: **14 (0.7%)** — almost nobody has multiple structured rules.
- `grading_keywords >= 2 entries`: **955 (48.7%)**.
- **Union (map-eligible today): 955 (48.7%)**.
- Intersection (both signals): 14 (0.7%) — virtually no item has both rich keywords and rich rules.
- Implication: the normalization spec **cannot assume both signals are available**. It must fall back gracefully — keyword-only items still produce scoring points, just at lower granularity.

**Year-stratification (the most actionable finding):**

| exam_year | n | map-eligible | share |
| --- | --- | --- | --- |
| 2025 | 311 | 258 | **83.0%** |
| 2024 | 17 | 6 | 35.3% |
| 2023 | 60 | 22 | 36.7% |
| 2022 | 23 | 8 | 34.8% |
| 2021-2015 | 260 | **0** | **0.0%** |
| `<null>` (generated / non-exam) | 1,290 | 661 | 51.2% |

The 2021-2015 REAL_EXAM cohort (~260 items) has **zero rubric signal** — it is the highest-value, lowest-coverage backlog. Authoring priority must shift to these items first, not the already-rich 2025 set.

**Cluster-stratification (enables per-cluster gate promotion):**

| node_code prefix | n | map-eligible | share |
| --- | --- | --- | --- |
| 1A43700 / 1A43800 / 1A41306 / 1A42200 / 1A41302 | sum 273 | ≥ 90% each | strong clusters |
| 1A41101 / 1A43500 / 1A42203 | sum 137 | 78-88% | mid-strong |
| 1A41201 / 1A43600 / 1A41305 | sum 299 | 55-70% | promotable with light backfill |
| 1A41304 / 1A43400 / 1A41303 / 1A43200 / 1A43300 | sum 466 | 32-50% | needs material authoring |
| 1A43102 / 1A43503 | sum 52 | 0% | unauthored clusters |

This unlocks a smarter promotion strategy: ship the scoring-point map UI **per knowledge cluster**, not all-or-nothing. Clusters already at ≥ 70% can light up immediately; weaker clusters stay in `rubric_pending` until authoring catches up.

**`structured_rules.type` taxonomy (informs ability_dimension mapping):**

| rule type | count | suggested ability_dimension |
| --- | --- | --- |
| threshold_check | 224 | calculation |
| forbidden_check | 145 | code_application |
| sequence_check | 73 | transfer |
| Mandatory | 64 | code_application |
| membership_check | 29 | question_reading |
| numeric_check / comparison_check / formula_check | 35 | calculation |
| condition_check / multi_condition_check | 15 | transfer |
| Recommended | 9 | expression |

This is the **canonical mapping** the normalization spec in Phase -1.A.1 must use. New rule types added to the bank without a mapping entry must fail the contract guard.

**Decision:**

- Phase -1.A is **read-only normalization + targeted authoring**, not greenfield rubric writing.
- The first move is `scripts/rubric_coverage_report.py` + `scripts/normalize_legacy_rubric.py`: project the existing `grading_keywords` + `structured_rules` + `correct_answer` into a canonical `scoring_points` array consumed by `case_kernel.py`'s existing projected-rubric path. **No write back into `grading_rubric` until normalization is reviewed.**
- The 70% gate applies to **map-eligible coverage** = share of case items whose normalized projection yields ≥ 2 distinct scoring points. Measured today: **48.7%** (`scripts/rubric_coverage_report.py` on 2026-05-22). Reaching 70% globally requires authoring backfill on ~ 415 case items.
- **Per-cluster promotion** (new strategy after data audit): the scoring-point map UI may be lit up per `node_code` prefix once that prefix exceeds 70%. Today **8 prefixes already qualify** (1A41101, 1A41302, 1A41306, 1A42200, 1A42203, 1A43500, 1A43700, 1A43800), covering ~ 410 case items. These can ship the map immediately while weaker clusters stay in `rubric_pending`.
- Until a global threshold is met, the global empty state remains `rubric_pending`; the UI's per-cluster light-up is a feature flag inside Batch C, gated by per-cluster coverage.
- Authoring queue priority (corrected after audit revealed 2021-2015 REAL_EXAM = 0% coverage):
  1. **REAL_EXAM items with exam_year 2017-2021** (215 items, classification done, only rubric authoring needed). This is the highest-leverage cohort: maximum exam reuse value with the lowest per-item authoring cost.
  2. **REAL_EXAM items with exam_year 2015-2016** (45 items; all 45 are missing `node_code` and 4 of 22 in 2015 have placeholder stems `[题干缺失]`). These require **classification + rubric authoring**, and 4 require **original content recovery** before any rubric work. Treat as a separate sub-task with教研 ownership.
  3. Case items in clusters currently 32-50% map-eligible (1A41304 / 1A43400 / 1A41303 / 1A43200 / 1A43300, ~ 466 items) — small per-item lift produces big cluster lift.
  4. Then the residual generated (exam_year IS NULL) case items not yet covered.
- 60-day target adjusted: **(a)** 2017-2021 REAL_EXAM rubric-authoring queue reaches ≥ 70% map-eligibility, **(b)** 2015-2016 REAL_EXAM classification queue is completed and the 4 `[题干缺失]` stems are recovered or explicitly quarantined, **(c)** at least 12 of the top 20 `node_code` prefixes pass the 70% per-cluster gate, **(d)** global map-eligible coverage reaches ≥ 65% as a stretch.
- The normalization spec must handle keyword-only items (the dominant case — 955 items have keywords-only vs only 14 with both signals). Keyword-only normalization produces lower-granularity scoring points labeled `granularity=keyword_only`, which the UI surfaces as "审题要点" rather than "采分点" until upgraded.
- 教研 + 数据 sign-off required on the first available high-signal preview set and the follow-up 50-row keyword-only preview before broader rollout.
- Output artifact: `docs/qa/2026-05-22-rubric-coverage-baseline.md` with the measured numbers, the normalization preview, and the authoring backlog (item IDs prioritized).

### Decision 2: A/B Sequential Gate (Replaces +5pp Single Gate)

**Decision:** Adopt the sequential promotion gate documented in "Quantitative A/B Comparison" above.

- cohort_10 → cohort_50: +3pp at p < 0.10 one-tailed Mann-Whitney + directional consistency on ≥ 2/3 secondary metrics + ≥ 100 active learners per arm.
- cohort_50 → cohort_100: +5pp at p < 0.05 two-tailed Mann-Whitney + ≥ 400 active learners per arm + all secondary metrics non-regressing.
- cohort_100 → sticky_100: sustained +5pp over 14 days + `prescription_verification_rate` ≥ 0.40.
- Underpowered cohort_10: hold up to 21 days; allow low-power promotion only with positive direction on primary + 2 secondary metrics, documented as such.
- Survey comprehension is a kill switch independent of statistical significance: 4/5 learners must answer the 5 comprehension questions with reference to specific evidence.

This protects against both false negatives at small N and over-fitting on tiny samples.

### Decision 3: Feature Flag Implementation (Custom Minimal Helper)

**Decision:** Add `deeptutor/services/experiments/cohort.py` (≤ 100 lines) as the single source of cohort assignment. Do not introduce GrowthBook or any third-party flag SDK now.

Rationale (see "Feature Flag And Progressive Rollout" → "Implementation Decision" for details):

- No existing flag SDK in repo; one-time transformation does not justify a new runtime dependency.
- Aliyun SSH write boundary is easier to honor with env vars.
- < 5 min kill switch is satisfied by env-var-driven reads with no in-memory cache.
- Pluggable interface (`is_enabled(flag, user_id)`) means a future GrowthBook adapter is a one-day swap.

Stages and sub-gates are defined under "Feature Flag And Progressive Rollout".

### Decision 4: Tiered Forgetting Decay Profiles

**Decision:** Replace the single 14-day default with `DECAY_PROFILES` keyed by `ability_dimension`. Initial tiers (see "Forgetting Decay Profiles"):

| ability_dimension | decay_half_life_days | first_revalidation_days |
| --- | --- | --- |
| code_application | 10 | 3, 7, 14, 30 |
| calculation | 14 | 3, 7, 14, 30 |
| question_reading | 21 | 7, 14, 30 |
| expression | 21 | 7, 14, 30 |
| transfer | 28 | 14, 30, 60 |
| review_execution | dynamic | prescription-driven |

These are starting defaults grounded in spaced-repetition research (Ebbinghaus, Karpicke, SM-2) adapted for adult高 stakes exam prep. They are **explicitly tuneable** with cohort_10 data via a predicted-vs-actual decay table in the cohort report. Adjust at most one tier per dimension per cycle.

BKT / DKT remains deferred until (a) ≥ 12 weeks of per-learner history, (b) item-difficulty calibration, and (c) a stable rule-based baseline to compare against.

### What Is Still Open (Tracked, Not Blocking)

- Whether `review_execution` decay needs its own non-time-based model — to be decided after cohort_10 data on prescription completion patterns.
- Whether the 100-learner cohort_10 floor is reachable from currently active opt-in users — to be confirmed by member service inspection before flipping `cohort_10` on.
- Whether the `question_intelligence` compilation pipeline should be reactivated (only 43/4,638 rows compiled today). The plan does **not** depend on it for Batch A/B; revisit during Batch D if `mistake_clustering` needs richer per-question signals.
- Whether `cited_standard_codes` deserves a dedicated backfill effort. The plan currently treats it as a soft signal mined from `analysis` text and `structured_rules.requirement`; a separate regulation-citation backfill plan should be considered after Batch C ships.

These items are observation-driven, not decision-driven. They will be resolved by data Phase -1 itself produces.

### Audit Trail (2026-05-22)

The Supabase audit that produced the numbers in Decision 1 and Phase -1.A was executed read-only via the credentials in `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env`, using `psql` against `DB_URL` (project `zgupgizexqpwtajvghno` — the legacy KB project; the `KBV5_DB_URL` project is currently empty for `questions_bank`). Audit artifacts:

- Script: `scripts/rubric_coverage_report.py` (read-only, subprocess `psql`, no new dependency).
- Output: `docs/qa/2026-05-22-rubric-coverage-baseline.md` (full numeric tables + top-30 authoring backlog + 20-item normalization preview).
- Date / role: 2026-05-22 / `postgres` role / no writes performed.

To reproduce:

```bash
python scripts/rubric_coverage_report.py \
  --env /Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env \
  --out docs/qa/$(date -u +%F)-rubric-coverage-baseline.md
```

Re-running the report monthly is the simplest way to track Phase -1.A.2 authoring progress and Batch C per-cluster gate eligibility.
