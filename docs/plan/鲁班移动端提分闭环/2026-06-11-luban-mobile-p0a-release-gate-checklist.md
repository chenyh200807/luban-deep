# 鲁班移动端 P0A Release Gate Checklist

> Status: Proposed / Gate checklist
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

> v1.3 对齐（2026-06-15）：新增 **Retention Gate（blocking）**。P0A 的核心假设是「忙碌成年人会连续回来」，所以留存是放行门，不是事后指标。完成率 / 满意度高但用户不回来不得 GO。

## 0. Verdict Rules

Gate verdict:

- `PASS`: evidence exists and no blocker remains.
- `PARTIAL`: useful evidence exists but release risk remains.
- `FAIL`: missing evidence or known blocker.
- `N/A`: not in P0A scope.

P0A cannot enter real-user gray release unless all blocking gates are `PASS`. If WeChat true-entry is `PARTIAL`, verdict cannot be `GO`; at best `WEAK-GO`.

## 1. Gate Matrix

| Gate | Blocking | Verdict | Evidence |
| --- | --- | --- | --- |
| Frontend Source Tree Gate | Yes | TBD | TBD |
| Asset Gate | Yes | TBD | TBD |
| UX Gate | Yes | TBD | TBD |
| Trust Gate | Yes | TBD | TBD |
| Cost/SLA Gate | Yes | TBD | TBD |
| Authority Gate | Yes | TBD | TBD |
| Task Scope Evidence Gate | Yes | TBD | TBD |
| Mistake Tag Schema Gate | Yes | TBD | TBD |
| Authorization Gate | Yes | TBD | TBD |
| WeChat Gate | Yes | TBD | TBD |
| Rollback Gate | Yes | TBD | TBD |
| Observability Gate | Yes | TBD | TBD |
| Privacy Gate | Yes | TBD | TBD |
| Scenario Coverage Gate | Yes | TBD | TBD |
| Decision Sample Gate | Yes | TBD | TBD |
| Retention Gate | Yes | TBD | TBD |

## 1.1 Frontend Source Tree Gate

Required:

- Development source of truth is explicit.
- True-entry validation target is explicit: `devtools_project_root=yousenwebview`, `target_subpackage=packageDeeptutor`.
- If code lands in `wx_miniprogram`, sync manifest / porting proof to `yousenwebview/packageDeeptutor` exists before WeChat Gate.
- Latest mini-program upload source is checked.

Fail if:

- Development and validation happen on different drifting trees.
- OCR/photo code exists only in one tree while P0A evidence is claimed from the other.
- Team cannot answer which tree is release source of truth.

## 2. Asset Gate

Required:

- F16 防水工程 spike package has source_refs before expansion.
- 3-5 expansion `case_family` packages have source_refs only after spike gate passes.
- Each has scoring_point list.
- Each has mistake_tag list.
- Each has question_binding.
- Each has light and semi-write task with task_scope.
- Retest binding prefers same scoring_point and different question.
- Owner and reviewer recorded.
- Rollback by case_family possible.

Fail if:

- Any case_family lacks source evidence.
- Any scoring point cannot be checked against a student answer.
- Any task relies on frontend scoring inference.
- Same original question is the only retest evidence for improvement.

## 3. UX Gate

Required:

- Today page: user can identify main task within 5 seconds.
- Light practice: target completion <= 5 minutes.
- Semi-write: target completion <= 15 minutes.
- Result page: first screen shows score range, confidence, top issues.
- Second attempt / similar question CTA visible.
- Standard answer folded by default.
- All core screens have loading, empty, error, success, high-risk states.

Fail if:

- Homepage looks like function grid, chat box, or marketing page.
- Results page leads to answer consumption only.
- Mobile typing burden blocks case training.

## 4. Trust Gate

Required:

- Score displayed as range unless governed official mode allows exact.
- Confidence visible.
- `uncertain` and `needs_review` states visible.
- High-risk reasons visible.
- User can report grading issue.
- High-risk grading does not promote stable claim.

Fail if:

- UI claims precise grading without authority.
- Low-confidence OCR or grading is hidden.
- User cannot see why a scoring point was hit / missed.

## 5. Cost/SLA Gate

Required:

- Light practice never calls OCR.
- Semi-write does not call OCR by default.
- OCR limited to controlled photo / real-exam / preview paths.
- Single OCR cost can be counted.
- Single grading cost can be counted.
- AI grading P50 <= 30s and P95 <= 90s on target P0A model tier, or async result fallback is enabled.
- Initial target average grading inference cost <= 0.20 RMB / attempt, pending spike validation.
- Free-user daily high-cost attempt cap is defined before real-user gray.
- Image quality failure stops OCR.
- Entitlement and cost soft cap checked before high-cost path.

Fail if:

- OCR becomes default daily path.
- Bad images still call OCR.
- Costs cannot be attributed by user / task / flow.
- Grading latency has no user-visible pending/degraded state.

## 6. Authority Gate

Required:

- Frontend does not compute score.
- Frontend does not compute mastery.
- Frontend does not compute next_action.
- OCR raw text does not enter grading.
- Behavior events do not write learner memory.
- RAG / knowledge map does not adjudicate scoring.
- Chat still uses `/api/v1/ws`; no new chat WS.
- `priority_score` only ranks/explains backend-authorized `training_intent` / `NextBestAction` candidates.
- Existing `note_assets today_tasks` is not treated as a new recommendation writer.

Fail if:

- Any UI code becomes second policy engine.
- Any transport layer rewrites canonical grading result.
- Any legacy PRD still acts as implementation authority.
- A new today-task engine generates candidates outside the existing authority chain.

## 6.1 Task Scope Evidence Gate

Required:

- Every light/semi-write task has `task_scope.scope_type`, `covered_scoring_point_ids`, `excluded_scoring_point_policy`, and `evidence_weight`.
- Grading result supports `not_evaluated`.
- Evidence builder does not write miss evidence for out-of-scope points.
- Light practice evidence is marked `light_signal` and cannot close stable weakness by itself.

Fail if:

- Semi-write is graded against the full rubric without scope clipping.
- Out-of-scope points become miss evidence.
- UI copy presents partial-scope training as full-question scoring.

## 6.2 Mistake Tag Schema Gate

Required:

- `mistake_tag` has canonical `tag_id`, `label`, `taxonomy_version`, `source`, `confidence`.
- `learning_evidence` payload builder path is defined.
- Mistake book readback path is defined.
- If protected contract changes, `contracts/index.yaml` domain test_files are updated before code implementation.

Fail if:

- Mistake tags are only template strings such as `漏写采分点：XXX`.
- Tags are display-only but release claims they drive recommendation.
- Tags write learner truth without taxonomy version.

## 6.3 Authorization Gate

Required:

- QA/operator/test/real-student cohorts are separated.
- Real-student learning_evidence writes are covered by an existing governed promotion arm or a newly approved gate.
- Decision package states whether P0A writes are QA-only, white-list-only, or broader default.

Fail if:

- Real paid users can write canonical learner truth by default without explicit authorization.
- QA/mock identities are mixed with production learner truth.

## 7. WeChat Gate

Required evidence:

- `devtools_project_root = yousenwebview`.
- `target_subpackage = packageDeeptutor`.
- `target_page = concrete page`.
- `entry_flow = concrete user action chain`.
- `auth_state = logged_in / qa_token / auth_blocked / unknown`.
- `auth_mode = real_wechat / local_dev_wechat / manual_token / none`.

Fail if:

- Only `/wechat-harness` was tested.
- Only DevTools `islogin` or `open` was run.
- Project root is incorrectly set to `yousenwebview/packageDeeptutor`.

## 8. Rollback Gate

Required:

- Feature flags for Today entry, training modes, grading result, OCR preview.
- Cohort control for QA/operator/test users.
- Ability to disable individual case_family.
- Ability to degrade high-risk grading to preview.
- Ability to stop OCR path without breaking light/semi-write.
- No migration that blocks rollback without explicit data plan.

Fail if:

- A bad asset can only be fixed by redeploying all frontend.
- New fields break existing evidence ledger.
- Users see broken task with no fallback.

## 9. Observability Gate

Required events:

- `mobile_p0a_home_viewed`
- `mobile_p0a_main_task_impressed`
- `mobile_p0a_main_task_started`
- `mobile_p0a_training_mode_selected`
- `mobile_p0a_light_step_completed`
- `mobile_p0a_semi_write_step_completed`
- `mobile_p0a_grading_result_viewed`
- `mobile_p0a_scoring_point_expanded`
- `mobile_p0a_second_attempt_started`
- `mobile_p0a_similar_question_started`
- `mobile_p0a_mistake_review_started`
- `mobile_p0a_plan_reordered`
- `mobile_p0a_ai_feedback_submitted`

Required dimensions:

- user cohort.
- entry_flow.
- case_family.
- task_type.
- mode.
- task_scope.
- evidence_weight.
- mistake_tag taxonomy version.
- auth_state.

Fail if:

- Events are not attributable to P0A flow.
- Behavior events can be mistaken for learner truth.

## 10. Privacy Gate

Required:

- Uploaded image deletion path defined.
- Learning record export path defined or explicitly deferred.
- Raw OCR stored as input evidence only.
- Confirmed text and learning evidence boundary clear.
- Feedback path for grading issue exists.

Fail if:

- Uploaded image deletion would delete canonical learning evidence silently.
- Raw OCR appears as student confirmed answer.
- Export is assembled by frontend state.

## 11. Scenario Coverage Gate

Required:

- Scenario matrix is completed with UI state, backend authority, fallback and telemetry for each scenario.
- Cold start, returning, interrupted, sprint, weak foundation, low-confidence grading, grading dispute, OCR failure, bad image, unauthenticated, entitlement-limited, network failure, true WeChat entry and privacy action scenarios are covered.
- Each scenario has a clear PASS/PARTIAL/FAIL verdict.

Fail if:

- Only happy path is tested.
- Any scenario depends on frontend scoring, local mastery or behavior-event truth.
- Uncovered scenario is still included in release scope.

## 11.1 Decision Sample Gate

Required for `GO`:

- At least 20 gray users.
- At least 100 valid attempts.
- At least 30 mistake review or retest entries.
- Sample split reports QA/operator/test/real-student cohorts separately.

Fail if:

- Decision package gives `GO` from only a handful of users or attempts.
- Sample does not include the core scoring loop.
- Cohort identity is ambiguous.

## 11.2 Retention Gate

Required (blocking — this is the P0A core hypothesis):

- A pre-registered D1 / D7 return target is set BEFORE the run (e.g. D1 >= X%, D7 >= Y% of grey users return on a later day without operator nagging).
- Behavior events carry a per-user first-use timestamp / return-day index so D1 / D3 / D7 return is actually computable from telemetry, not estimated.
- Return is measured on the daily retention loop (今日任务 → MCQ 轻练 → 盲点诊断 → 次日复测), not just any app open.
- The decision package reports observed D1 / D3 / D7 retention against the pre-registered target.

Fail if:

- Retention cannot be computed because events lack return-day attribution.
- `GO` is claimed from completion rate or NPS while real return is below target.
- Retention is reported only as a self-report survey number, not behavioral return.

## 12. Final Signoff

| Role | Name | Verdict | Notes |
| --- | --- | --- | --- |
| Product | TBD | TBD | TBD |
| Engineering | TBD | TBD | TBD |
| Design | TBD | TBD | TBD |
| Grading authority | TBD | TBD | TBD |
| Learning Brain authority | TBD | TBD | TBD |
| WeChat QA | TBD | TBD | TBD |
