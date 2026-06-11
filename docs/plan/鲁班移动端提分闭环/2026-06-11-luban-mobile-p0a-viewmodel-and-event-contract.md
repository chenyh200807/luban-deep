# 鲁班移动端 P0A ViewModel 与行为事件契约

> Status: Proposed / P0A ViewModel and event authority
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

## 0. Purpose

本文定义 P0A 前后端之间的最小 ViewModel 与行为事件边界，防止移动端实现时把评分、推荐、掌握度、错因和 learner truth 重新做一套。若父 PRD 的字段草案与本文不一致，以本文为准。

本文不是最终 API schema。进入代码前，若字段变成稳定对外边界，必须再落到对应 contract / schema / test fixture 中。

## 1. Boundary Principle

后端负责：

- 今日任务推荐。
- `training_intent` / `NextBestAction` 候选生成。
- `priority_score` 或推荐排序解释。
- 题目、母题、知识点、采分点绑定。
- 批改结果。
- learning_evidence 写入与读回。
- 错因复练和复测 next action。
- OCR provenance 和降级状态。
- 隐私与数据删除/export 的真实执行。

前端负责：

- 展示 ViewModel。
- 收集用户输入。
- 发起提交、复练、复测、上传、删除和导出请求。
- 上报行为事件。
- 展示 loading / empty / degraded / error 状态。

前端不得：

- 自行计算 score、mastery、weakness、priority_score 或 next_action。
- 根据 UI 状态直接写 learner truth。
- 从 OCR 原文直接构造 learning_evidence。
- 从行为事件反推掌握度。
- 暴露 hidden answer key、scoring_point answer 或内部 rubric prompt。

### 1.1 Recommendation Authority

P0A 推荐链的唯一合法形态：

```text
learning_evidence / learner_state
-> training_intent / NextBestAction candidates
-> learning_report_read_model / home personalization projection
-> optional priority_score ranking/explanation
-> HomeDashboardViewModel
```

`priority_score` 不能生成候选、不能关闭弱点、不能替代 `training_intent`。`note_assets today_tasks` 只能作为兼容投影或冷启动输入，不能成为第二套今日任务 writer。

### 1.2 Evidence Scope Authority

轻练和半写不是完整作答。每个可写 evidence 的任务必须带 `task_scope`：

```yaml
task_scope:
  scope_type: "full_question | scoring_point_subset | light_check | preview"
  covered_scoring_point_ids: []
  excluded_scoring_point_policy: "not_evaluated_no_miss"
  evidence_weight: "official | diagnostic | light_signal | none"
```

规则：

- `full_question` 可以按完整 rubric 写 point-level evidence。
- `scoring_point_subset` 只能评价 `covered_scoring_point_ids`；范围外点必须是 `not_evaluated`。
- `light_check` 只能作为 diagnostic / light_signal，不能单独关闭 stable weakness。
- `preview` 不写长期 learner truth。

### 1.3 Mistake Tag Authority

`mistake_tag` 必须是 canonical taxonomy 字段，不得只写自由文本：

```yaml
mistake_tag:
  tag_id: "string"
  label: "string"
  taxonomy_version: "string"
  source: "grading_kernel | reviewer | migration"
  confidence: "high | medium | low"
```

在 `learning_evidence` payload builder、mistake book readback 和 contract tests 冻结前，错因标签只能展示，不得写入长期 learner truth。

## 2. Core ViewModels

### 2.1 HomeDashboardViewModel

用于今日页首屏。

Required fields:

```yaml
schema_version: "mobile_p0a_home_v1"
learner_id_hash: "string"
exam_countdown:
  days_remaining: 0
  label: "string"
today_main_task:
  task_id: "string"
  task_type: "light_practice | semi_write | retest | review"
  case_family_id: "string"
  case_family_name: "string"
  knowledge_node_label: "string"
  title: "string"
  why_recommended: "string"
  estimated_minutes: 0
  priority_bucket: "high | medium | low"
  evidence_refs: []
  recommendation_authority:
    candidate_source: "training_intent | next_best_action | learning_report_read_model | cold_start"
    ranking_source: "priority_score | rule_sort | manual_override"
    generated_by_backend: true
  deep_link: "string"
secondary_actions:
  - action_id: "string"
    label: "string"
    deep_link: "string"
state:
  status: "ready | empty | degraded | unauthenticated | error"
  message: "string"
```

Forbidden fields:

- raw `priority_score` if not intended for display.
- hidden scoring answer.
- client-computable mastery formula.

### 2.2 CaseTrainingSessionViewModel

用于轻练和半写作答页。

```yaml
schema_version: "mobile_p0a_training_v1"
session_id: "string"
task_id: "string"
task_type: "light_practice | semi_write | retest"
case_family_id: "string"
question_ref:
  question_id: "string"
  source_label: "string"
prompt:
  stem: "string"
  materials: []
  user_visible_constraints: []
answer_input:
  mode: "choice | short_text | structured_text | photo_preview"
  min_chars: 0
  max_chars: 0
task_scope:
  scope_type: "full_question | scoring_point_subset | light_check | preview"
  covered_scoring_point_ids: []
  excluded_scoring_point_policy: "not_evaluated_no_miss"
  evidence_weight: "official | diagnostic | light_signal | none"
hints:
  enabled: true
  items: []
state:
  status: "ready | loading | degraded | error"
```

Forbidden:

- hidden scoring_point answer.
- final rubric prompt.
- teacher-only notes.

### 2.3 GradingResultViewModel

用于 AI 批改结果页。

```yaml
schema_version: "mobile_p0a_grading_result_v1"
attempt_id: "string"
session_id: "string"
case_family_id: "string"
score_summary:
  awarded_score: 0
  max_score: 0
  display_level: "string"
task_scope:
  scope_type: "full_question | scoring_point_subset | light_check | preview"
  covered_scoring_point_ids: []
  out_of_scope_policy: "not_evaluated_no_miss"
  evidence_weight: "official | diagnostic | light_signal | none"
point_matches:
  - point_id: "string"
    label: "string"
    max_score: 0
    awarded_score: 0
    outcome: "hit | partial | miss | not_evaluated | high_risk_review"
    evidence_span: "string"
    diagnosis: "string"
    mistake_tags:
      - tag_id: "string"
        label: "string"
        taxonomy_version: "string"
        source: "grading_kernel | reviewer | migration"
        confidence: "high | medium | low"
trust:
  status: "normal | low_confidence | high_risk_review | degraded"
  reason: "string"
next_action:
  action_type: "retest | light_practice | semi_write | review | none"
  task_id: "string"
  label: "string"
  deep_link: "string"
learning_evidence:
  event_id: "string"
  write_status: "written | deferred | skipped | failed"
  readback_status: "readback_ok | pending | failed"
```

Rules:

- `point_matches` comes only from grading authority.
- `learning_evidence.write_status=written` requires backend confirmation.
- Points outside `task_scope.covered_scoring_point_ids` must use `outcome=not_evaluated`; they must not generate miss evidence.
- `mistake_tags` can be written only after canonical schema and readback contract are frozen.
- If `trust.status=high_risk_review`, UI must avoid overconfident wording.

### 2.4 MistakeReviewViewModel

用于错因复练入口。

```yaml
schema_version: "mobile_p0a_mistake_review_v1"
items:
  - mistake_id: "string"
    case_family_id: "string"
    point_id: "string"
    mistake_tag:
      tag_id: "string"
      label: "string"
      taxonomy_version: "string"
    last_seen_at: "string"
    recommended_action:
      action_type: "light_practice | semi_write | retest"
      task_id: "string"
      deep_link: "string"
      retest_policy:
        scoring_point_id: "string"
        prefer_different_question: true
        original_question_reuse_allowed_for_review_only: true
state:
  status: "ready | empty | degraded | error"
```

Forbidden:

- User tapping "掌握了" cannot directly set canonical mastery.
- Local cache cannot become mistake truth.

### 2.5 OcrPreviewViewModel

P0A 默认只作为 preview / diagnostic，不写长期 learner truth。

```yaml
schema_version: "mobile_p0a_ocr_preview_v1"
upload_id: "string"
ocr_status: "pending | succeeded | failed | low_confidence"
recognized_text_preview: "string"
provenance:
  image_hash: "string"
  ocr_engine: "string"
  confidence_bucket: "high | medium | low"
allowed_actions:
  - "edit_text"
  - "submit_as_text"
  - "discard"
```

Rules:

- OCR text must be user-confirmed or edited before grading.
- Raw OCR output must not directly write learning_evidence.

## 3. Behavior Event Catalog

All events use existing product behavior authority. Events are telemetry, not learner truth.

| Event | Required properties | Not allowed |
| --- | --- | --- |
| `mobile_p0a_home_viewed` | `visit_id`, `entry_flow`, `task_id`, `case_family_id` | score/mastery write |
| `mobile_p0a_main_task_impressed` | `visit_id`, `task_id`, `case_family_id`, `priority_bucket` | local recommendation mutation |
| `mobile_p0a_main_task_started` | `task_id`, `task_type`, `case_family_id` | next_action mutation |
| `mobile_p0a_quick_action_clicked` | `action_id`, `entry_flow` | learner state mutation |
| `mobile_p0a_training_mode_selected` | `session_id`, `task_type`, `mode` | mode-based mastery write |
| `mobile_p0a_light_step_completed` | `session_id`, `step_id`, `task_scope.scope_type` | stable mastery close |
| `mobile_p0a_semi_write_step_completed` | `session_id`, `step_id`, `covered_scoring_point_ids_count` | miss evidence write |
| `mobile_p0a_answer_submitted` | `session_id`, `task_type`, `answer_input_mode` | raw answer in analytics event |
| `mobile_p0a_grading_result_viewed` | `attempt_id`, `case_family_id`, `trust_status` | point-level private evidence if not redacted |
| `mobile_p0a_scoring_point_expanded` | `attempt_id`, `point_id`, `outcome` | hidden answer key |
| `mobile_p0a_rewrite_suggestion_viewed` | `attempt_id`, `suggestion_id` | raw answer text |
| `mobile_p0a_second_attempt_started` | `attempt_id`, `task_id` | score mutation |
| `mobile_p0a_similar_question_started` | `source_attempt_id`, `task_id`, `retest_policy` | mastery write |
| `mobile_p0a_mistake_added` | `attempt_id`, `mistake_tag.tag_id`, `write_status` | local mistake truth |
| `mobile_p0a_mistake_review_started` | `mistake_id`, `task_id` | mastery write |
| `mobile_p0a_mistake_closed` | `mistake_id`, `close_source` | local close without backend |
| `mobile_p0a_retest_started` | `source_mistake_id`, `task_id` | mastery write |
| `mobile_p0a_retest_completed` | `task_id`, `attempt_id` | local score computation |
| `mobile_p0a_photo_upload_started` | `upload_id`, `entry_flow` | image bytes |
| `mobile_p0a_photo_quality_failed` | `upload_id`, `reason_bucket` | raw image |
| `mobile_p0a_ocr_requested` | `upload_id`, `provider_bucket` | raw image |
| `mobile_p0a_ocr_confirmed` | `upload_id`, `edited` | raw full text in telemetry |
| `mobile_p0a_ai_feedback_submitted` | `attempt_id`, `feedback_type` | raw private answer |
| `mobile_p0a_plan_reordered` | `visit_id`, `reason_bucket` | direct learner truth write |
| `mobile_p0a_privacy_delete_uploads_requested` | `request_id` | deleting evidence silently |
| `mobile_p0a_learning_records_export_requested` | `request_id` | export without auth |

## 4. Versioning

- Every ViewModel includes `schema_version`.
- P0A can tolerate additive optional fields.
- Removing or renaming fields requires a fixture update and compatibility decision.
- Legacy PRD fields do not become valid unless mapped here or in a formal contract.

## 5. Test Fixture Requirement

Before frontend implementation starts, P0A needs frozen fixtures for:

1. Home ready state.
2. Home empty/degraded state.
3. Light practice session.
4. Semi-write session.
5. Semi-write result with scoped points and out-of-scope `not_evaluated`.
6. Light practice result with `evidence_weight=light_signal`.
7. Grading result with hit/partial/miss.
8. High-risk grading result.
9. Mistake review with canonical `mistake_tag` and retest policy.
10. OCR low-confidence preview.
11. Unauthenticated state.
12. Privacy delete/export request states.

## 6. Release Gate

P0A Authority Gate fails if:

- Frontend computes recommendation, score, mastery, weakness or next_action.
- Behavior events write or mutate learner state.
- OCR raw result writes long-term truth without provenance and user confirmation.
- Legacy `PRD/` wording bypasses this contract draft or the canonical PRD.
- Grading result is rewritten by transport or UI projection after canonical assembly.
- `priority_score` generates candidates or overrides `training_intent` / `NextBestAction`.
- Semi-write or light practice writes miss evidence outside `task_scope.covered_scoring_point_ids`.
- `mistake_tag` writes to learner truth as free text or without taxonomy version.
