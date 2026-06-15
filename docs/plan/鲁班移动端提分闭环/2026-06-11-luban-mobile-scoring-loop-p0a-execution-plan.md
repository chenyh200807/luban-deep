# 鲁班移动端提分闭环 P0A 执行计划

> Status: Proposed / Execution plan for P0A vertical slice
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

> v1.3 对齐（2026-06-15）：父 PRD 已收口为「每日提分留存闭环」为前台主菜、案例题 AI 采分点批改为养成习惯后解锁的深度护城河层。本执行计划据此调整重心：P0A 第一个 spike 验证「人会不会连续回来」（留存假设），不是验证案例题批改技术闭环（M32 已证明能跑）；GO 门钉真实 D1/D7 回访留存。下列 WS / 里程碑积木保留，仅重心与验收口径对齐。

## 0. Purpose

本文件把 canonical 产品 PRD 拆成 P0A 可执行计划。它不重新定义产品目标，不替代评分、Learning Brain、OCR、微信入口等专项 contract。

P0A 目标：

先用 1 个 spike 证明「每日提分留存闭环」真实可走（人会连续回来）：今日任务 -> 2 分钟知识点/母题 MCQ 轻练 -> 当场盲点诊断（错选项 -> 采分点 / 教材章节定位）-> learning_evidence -> 「明天复测什么」开环 -> 次日复测 readback。案例题渐进作答 -> AI 采分点批改 -> 错因复练作为留存跑通后第二阶段解锁的深度层。spike 跑通后再扩到 3-5 个高频母题。

## 1. Scope

P0A 做：

- 今日页最小主任务。
- 轻练 5 分钟。
- 半写 15 分钟。
- AI 批改结果页。
- 错因复练入口。
- 复测 readback。
- P0A case_family 资产生产线。
- P0A ViewModel contract。
- P0A release gate 与 decision package。

P0A 不做：

- 完整 30-40 母题。
- 完整章节地图。
- 完整五 Tab 重构。
- 完整人工复核后台。
- 商业化强转化。
- OCR photo path 写长期 learner truth。
- 生产 broad default。

## 2. One Business Fact

P0A 要证明的一等业务事实：

每一次有效训练（知识点 / 母题 MCQ 轻练，或案例题批改），必须转化为可追溯的采分点级 learning_evidence，并驱动盲点诊断、次日复测和明天的今日任务。轻练 MCQ 与案例题批改写同一份 learning_evidence、同一套采分点 / 错因 authority，门槛不同：轻练是低门槛留存入口，案例题批改是深度层。

Authority 分层沿用父 PRD：

- grading truth: `construction_grading` / `CaseGradingSkillKernel` / rubric lane。
- evidence ledger: `learner_memory_events.learning_evidence`。
- long-term learner truth: `Learning Brain` / `LearnerStateService`。
- frontend: read model projection only。

## 3. P0A Data Flow

```text
HomeDashboardViewModel
-> TodayMainTaskCard
-> CaseTrainingSessionViewModel
-> light / semi_write answer
-> GradingResultViewModel
-> grading result
-> learning_evidence
-> mistake_book_read_model
-> next task / retest readback
-> P0A decision package
```

Red lines:

- Frontend never computes `score`, `mastery`, `risk`, or `next_action`.
- OCR raw text never enters grading.
- Behavior events never write learner memory.
- RAG / knowledge map never adjudicates scoring.
- `/wechat-harness` evidence never replaces true `yousenwebview/packageDeeptutor` evidence.
- `priority_score` never replaces `training_intent` / `NextBestAction`; it only ranks or explains backend-authorized candidates.
- Light and semi-write evidence must include `task_scope`; out-of-scope scoring points are `not_evaluated`, never `miss`.
- `mistake_tag` cannot write long-term learner truth until the canonical payload schema and readback contract are frozen.

## 4. Workstreams

### WS0: Reality Inventory

Deliverables:

- Frontend source tree decision: development source of truth, validation tree, sync mechanism, latest mini-program upload source.
- Current page inventory for `packageDeeptutor`.
- Current mobile API / read model inventory.
- Current grading-to-evidence inventory.
- Current mistake book / learning report inventory.
- Concept authority map: `training_task`, `review_schedule`, `learner_mastery`, `priority_score`, `today_tasks`, `mistake_tag`, `task_scope`.
- P0A evidence write policy for full question, semi-write, light practice and preview paths.
- `mistake_tag` schema and protected-contract impact list.
- Reusable component inventory.
- P0A gap list.

Acceptance:

- `wx_miniprogram` and `yousenwebview/packageDeeptutor` ownership is explicit; development and true-entry validation cannot happen on drifting trees.
- Every P0A screen maps to an existing page, a modified page, or a new target page.
- Every P0A ViewModel field has source: existing API, new read model, mock-only, or out-of-scope.
- No implementation task starts until authority map, task-scope rule and mistake-tag schema path are documented.

### WS1: Case Family Assets

Deliverables:

- Single-mother-topic spike package first, default `F16 防水工程`.
- 3-5 P0A expansion case_family packages after spike pass.
- scoring_point list for each package.
- mistake_tag list for each package.
- question_binding list.
- light and semi_write task designs.
- retest binding rule: prefer same scoring_point, different question; original question reuse cannot be counted as clean improvement evidence.
- owner / reviewer / version metadata.

Acceptance:

- Spike package passes Asset Gate before any expansion package is produced in parallel.
- Every P0A expansion case_family passes Asset Gate in [2026-06-11-luban-mobile-case-family-asset-production-plan.md](2026-06-11-luban-mobile-case-family-asset-production-plan.md).

### WS2: ViewModel Contracts

Deliverables:

- `HomeDashboardViewModel`.
- `TodayMainTaskCard`.
- `CaseTrainingSessionViewModel`.
- `GradingResultViewModel`.
- `MistakeBookItem`.
- `task_scope` and `evidence_weight` fields for light, semi-write, full-question and preview paths.
- canonical `mistake_tag` field shape, taxonomy version and readback path.
- mock fixtures for new / normal / interrupted / sprint / error states.

Acceptance:

- Mock can run the full P0A flow without backend.
- Contract tests prevent frontend-only score/mastery/next_action calculation.
- Contract tests prove out-of-scope scoring points are not written as miss evidence.
- If `learning_evidence` protected contract changes, tests are registered in `contracts/index.yaml` before implementation.

### WS3: Today Task And Practice Entry

Deliverables:

- Today page minimum slice.
- Main task card.
- Micro review card.
- Optional task card.
- Quick actions: light practice, semi-write, photo diagnosis preview.

Acceptance:

- New user sees a 3-minute diagnostic or P0A default high-value task.
- Existing user sees one main task with reason.
- Interrupted user sees rescheduled task without debt language.

### WS4: Light And Semi-Write Training

Deliverables:

- Light practice steps for P0A packages; P0A only supports single-choice, multiple-choice and case small-question interactions.
- Semi-write steps for P0A packages.
- Explicit `covered_scoring_point_ids` per step.
- Training session state.
- Draft preservation for network interruption.

Acceptance:

- Light practice can finish in 5 minutes.
- Semi-write can finish in 15 minutes.
- User does not need long mobile typing to produce diagnostic value.
- Sorting, matching and fill-in interactions are marked P0B unless product owner explicitly reopens P0A scope.
- Half-write submission cannot be graded against full rubric without scope clipping or `not_evaluated` semantics.

### WS5: Grading Result And Learning Evidence

Deliverables:

- Grading result page with score range, confidence, top issues, scoring points, evidence blocks, rewrite suggestions.
- Standard answer folded by default.
- Bottom CTA: second attempt and similar question.
- learning_evidence write/readback proof.
- task-scope write/readback proof.
- mistake-tag write/readback proof after canonical schema freeze; before freeze it remains display-only.

Acceptance:

- A completed training produces point-level evidence.
- Evidence can be read back into mistake book or today task.
- High-risk or low-confidence grading does not promote stable claim.
- Light practice evidence is weighted as a diagnostic signal and cannot close a stable weakness by itself.
- Semi-write evidence never records miss for scoring points outside the task scope.

### WS6: Mistake Review And Retest

Deliverables:

- Mistake review entry by mistake_tag / scoring_point / case_family.
- Similar question recommendation.
- Retest readback surface.
- Same-scoring-point / different-question retest selection proof when available.

Acceptance:

- User can enter a retest task from a mistake.
- Retest can show whether the prior mistake improved.
- GO evidence cannot rely only on repeating the original question.

### WS7: True WeChat Evidence

Deliverables:

- DevTools project root evidence: `yousenwebview`.
- Target subpackage evidence: `packageDeeptutor`.
- Target page evidence for today, training, grading result, mistake review.
- auth_state / auth_mode record.

Acceptance:

- At least one P0A core flow has true-entry evidence.
- If true-entry is pending, decision package says `WEAK-GO` or `NO-GO`, not `GO`.

### WS8: Decision Package

Deliverables:

- Completed P0A release gate checklist.
- Completed P0A decision package.
- Authorization gate evidence for QA/operator/test/real-student write paths.
- Sample size report: grey users, valid attempts, mistake review/retest entries.
- GO / WEAK-GO / NO-GO recommendation.

Acceptance:

- P0B cannot start without this package.
- GO requires a pre-registered **D1/D7 retention** threshold (users actually returned on later days without nagging) **plus** the sample threshold, or explicit product-owner override; loop completion / high satisfaction without real return is at most WEAK-GO (this is the exact trap the v1.2 → v1.3 realignment exists to avoid: NPS high, revisit no).

### WS9: Scenario Coverage And Hardening

Deliverables:

- Completed scenario matrix from [2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md](2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md).
- Per-scenario UI state, backend authority, fallback and telemetry mapping.
- Red-team checklist for authority drift, OCR cost creep, trust overclaim and false WeChat pass.

Acceptance:

- Cold start, returning, interrupted, sprint, low-confidence grading, OCR failure, unauthenticated, entitlement-limited, network failure, grading dispute and privacy action scenarios are explicitly covered.
- Any uncovered P0A scenario is either removed from scope or marked as a release blocker.

## 5. Milestones

| Milestone | Output | Gate |
| --- | --- | --- |
| M0 Reality Lock | Source tree decision, current-state inventory, concept authority map, evidence write policy | Frontend Source Tree + Authority Gate |
| M1 Spike Asset | F16 内容下的每日留存闭环 spike 资产（今日任务 + 2 分钟 MCQ 轻练 + 错选项→采分点/教材章节诊断 + 次日复测题） | Asset Gate |
| M2 Contracts | ViewModel + mocks + task_scope + mistake_tag schema path | Authority + Task Scope Evidence Gate |
| M3 Today/Training | Today + light/semi-write | UX Gate |
| M4 Grading/Evidence | Result page + learning_evidence readback | Trust + Authority Gate |
| M5 Mistake/Retest | Mistake review + retest readback | Closure Gate |
| M6 True Entry | WeChat true-entry smoke | WeChat Gate |
| M7 Scenarios | Scenario matrix + hardening review | Scenario Coverage Gate |
| M8 Expansion Assets | 3-5 case_family packages after spike | Asset + Retest Anti-Memorization Gate |
| M9 Decision | Decision package（GO 钉真实 D1/D7 回访留存，不是闭环完成率） | GO / WEAK-GO / NO-GO |

## 6. Minimum Test Matrix

P0A must include:

- ViewModel contract tests.
- State coverage tests: loading, empty, error, partial, success, high-risk.
- Authority tests: no frontend score/mastery/next_action calculation.
- Recommendation authority tests: `priority_score` ranks backend-authorized candidates only.
- Source tree check: development tree, validation tree and sync evidence are present.
- OCR boundary tests: raw_ocr_text does not enter grading.
- Grading-to-evidence tests.
- Task-scope tests: out-of-scope scoring points are `not_evaluated`, not `miss`.
- Mistake-tag schema/readback tests after schema freeze.
- Mistake review readback tests.
- Retest anti-memorization tests: same scoring_point different question preferred.
- Recommendation tests for new / normal / interrupted / sprint states.
- Scenario coverage tests for auth, entitlement, network failure, low-confidence grading, OCR failure, grading dispute and privacy actions.
- Cost/SLA tests: light practice does not trigger OCR; AI grading P50/P95 and per-attempt cost are measured on target model tier.
- Authorization gate tests or evidence: QA/operator/test/real-user write permissions are separated.
- Decision sample checks: grey users, valid attempts, mistake review/retest entries meet or explicitly miss threshold.
- WeChat true-entry smoke or explicit `true-entry pending` risk.

## 7. GStack Review Notes

CEO review stance:

- Hold the product ambition: this is a scoring loop, not UI polish.
- Keep P0A narrow; avoid full platform rewrite.

Engineering review stance:

- Require data flow, tests, failure states, cost visibility, rollback.
- Do not let any wrapper become a second policy engine.

Design review stance:

- Require real screen specs before implementation.
- Reject generic AI-card UI, feature grid homepage, and chat-first entry.

## 8. Dependencies

- Parent product PRD: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
- Asset plan: [2026-06-11-luban-mobile-case-family-asset-production-plan.md](2026-06-11-luban-mobile-case-family-asset-production-plan.md)
- UI/UX screen spec: [2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md](2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md)
- ViewModel/event contract draft: [2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md](2026-06-11-luban-mobile-p0a-viewmodel-and-event-contract.md)
- Scenario/risk hardening review: [2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md](2026-06-11-luban-mobile-p0a-scenario-risk-hardening-review.md)
- Gate checklist: [2026-06-11-luban-mobile-p0a-release-gate-checklist.md](2026-06-11-luban-mobile-p0a-release-gate-checklist.md)
- Decision package template: [2026-06-11-luban-mobile-p0a-decision-package-template.md](2026-06-11-luban-mobile-p0a-decision-package-template.md)
