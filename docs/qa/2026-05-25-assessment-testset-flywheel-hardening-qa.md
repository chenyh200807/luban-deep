# Assessment TestSet Flywheel Hardening QA

Date: 2026-05-25

Scope:
- Result page CTA must return to the learning report training area, not chat.
- Wrong-item cards expose a "练 3 道同类题" entry with `attempt_ref`, `knowledge_point`, and `error_code`.
- Completing the follow-up training writes `learning_evidence` and makes the next recommendation "再测一次该专题".
- Verify the WeChat mini-program path in DevTools and record real runtime evidence.

## Code Evidence

Changed surfaces:
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.wxml`
  - Both server-result and legacy/fallback-result primary CTAs bind to `goLearningPlan`.
  - No assessment result CTA binds to `goChat`.
  - Wrong-item cards include `练 3 道同类题`.
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
  - `goLearningPlan()` relaunches `/packageDeeptutor/pages/report/report?detail=training`.
  - `onPracticeWrongItem()` writes pending chat intent with `attempt_ref`, `concept_label`, `error_label`, `evidence_refs`, and `question_count=3`.
- `yousenwebview/packageDeeptutor/pages/chat/chat.js`
  - Pending assessment-practice intent is carried into structured MCQ submit.
  - Submitted MCQ payload marks `learning_signal_type=training_completed`.
- `deeptutor/services/learner_state/conversation_learning_evidence.py`
  - Accepts `assessment_wrong_item_practice` and `training_completed`.
  - Persists `attempt_ref`, `evidence_refs`, and `training_question_count` in learning evidence payload.
- `deeptutor/services/learner_state/home_personalization.py`
  - Training-completed projection prepends an assessment retest prompt: `再测一次<concept>`.

## Automated Gate

Node:

```text
PASS test_package_assessment_contract.js (17 assertions)
PASS test_assessment_testset_view_model.js (55 assertions)
PASS test_mistake_book_view_model.js
PASS test_deeptutor_runtime_state.js (47 assertions)
PASS test_route_authority.js (5 assertions)
PASS test_package_chat_surface_layout_contract.js (15 assertions)
```

Pytest:

```text
.........................................                                [100%]
41 passed in 3.77s
```

Contract guard:

```text
contract-guard: passed
[turn] passed
[capability] passed
[learner_state] passed
error-code-guard: passed | codes=E02, E04, M02, M06, M07, unknown_error
node-id-guard: no hard-coded knowledge_node_id literals found
```

## DevTools Evidence

Tool:
- WeChat DevTools Stable v2.01.2510290
- Project path confirmed: `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview`
- Mini-program path observed: `packageDeeptutor/pages/assessment/assessment`

Observed real requests:
- `GET /api/v1/mobile/learning-report?event_limit=100&schema_version=2` returned 200.
- `POST /api/v1/assessment/create` returned 200 with a 20-question diagnostic form.
- Real quiz UI entered answer mode and advanced through questions.
- After completing the run, the previous implementation landed in chat. Root cause was a residual legacy/fallback result CTA in `assessment.wxml`:
  - server-result branch had already used `goLearningPlan`
  - fallback-result branch still used `goChat`
- The fallback branch was fixed and locked by `test_assessment_testset_view_model.js`, which now asserts `bindtap="goChat"` never appears in the assessment result template.

Additional runtime observation:
- The over-clicked DevTools run ended on chat after quiz completion. Code review found a real residual `goChat` binding in the legacy/fallback result branch and that binding was removed.
- The chat view later displayed a review-style MCQ from existing chat state. Because the final click sequence was automated and over-clicked past the result page, this is not sufficient evidence that the wrong-item practice prompt itself failed.
- The writeback contract is covered when structured MCQ submit happens; a clean manual rerun should still explicitly verify the final live chain after hot reload state is reset.

## Status

Passed:
- CTA routing authority is fixed in both result branches.
- Wrong-item practice intent carries assessment context.
- Training-completed writeback projection and retest recommendation are covered by backend tests.
- Assessment create and quiz entry work in real DevTools against `test2.yousenjiaoyu.com`.

Not fully passed:
- Full live "wrong item -> 3 submit-able training questions -> learning_evidence writeback -> report shows retest recommendation" was not proven end-to-end in DevTools. The automated click sequence over-clicked past the result page before the fixed CTA could be manually verified.

Required follow-up:
- Reset DevTools state and rerun the wrong-item practice path manually, without over-click automation past result.
- If the rerun produces a review-only card instead of submit-able MCQs, add a stricter structured training-card contract for the wrong-item practice prompt, or route "练 3 道同类题" into an existing deterministic training generator instead of relying on free-form chat generation.
- Re-run DevTools after that contract is added and verify the final live chain:
  `assessment result -> wrong item practice -> submit 3 questions -> learning_evidence -> report training area -> retest recommendation`.
