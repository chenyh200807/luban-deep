# Learning State Inference Contract

> Batch A Task 1 — registers the projection surfaces introduced by
> `docs/plan/2026-05-22-luban-learning-state-inference-engine-transformation-plan.md`
> on top of the existing learner-state and learning-report contracts.
>
> This contract is **purely additive**: it does not introduce a new
> authority, table, event type, endpoint, or chat WebSocket. It records
> the agreed projection grammar and the explicit forbidden patterns so
> future agents grep one place to recognize anti-patterns.
>
> Location note: this file lives under `docs/contracts/` rather than the
> historical `contracts/` directory. New contract docs (incl. the Phase −1.B
> [`docs/contracts/error_code_registry.md`](./error_code_registry.md)) follow
> this convention; the older files under `contracts/` (`learner-state.md`,
> `learning-report.md`, etc.) remain authoritative under their existing path.

## 单一 Authority

唯一学习事实 ledger：

```text
grading (case_kernel / mcq) | conversation_synthesis | training action
  → learner_memory_events.learning_evidence  (writer = LearnerStateService.write_learning_evidence)
    → learning_synthesis            (compiles compiled truth + observed candidates)
      → learning_report_read_model  (assembles student-facing learner_facing surface)
      → home_dashboard projection   (home_personalization)
      → attempt_detail_read_model   (attempt-level replay)
```

任何 reader 必须经由 read model；任何 writer 必须先落到 `learning_evidence`。

## 允许的事件类型与来源

- `event_type = "learning_evidence"` 是这条主线唯一允许的 memory event 类型。
- `memory_kind = "learning_evidence"` 同上。
- `payload.evidence_source` 限：
  - `construction_grading` —— 来自 `case_kernel` / `mcq` 的批改事件。
  - `conversation_synthesis` —— 来自 `/api/v1/ws` 答疑解析的语义事实。

不要新增第三种 `evidence_source`。新增加的子分类应走 `payload.learning_signal_type` 子字段。

### 摸底 / 测试集作答证据

摸底测评、测试集和专项训练中的客观题作答，不是第二套 learner memory authority。
它们必须归一化为既有 `construction_grading` 形态的 `learning_evidence`：

- writer 复用 `deeptutor.services.construction_grading.writeback.write_grading_error_events`
  与 `build_learning_evidence_payload`。
- `source_feature` 仍为 `construction_grading`，不得新增 `assessment` evidence source。
- assessment 语义只能作为 payload 内的子字段表达，例如
  `grading_mode = "assessment_blueprint"`、`next_training_signal.source = "assessment"`、
  `evidence_refs[*].source_type = "assessment"`。
- 正确作答可作为 success / improvement evidence 写入；错误作答必须使用已登记错码，或在没有更精确错码时显式降级为 `unknown_error`。
- 缺少题干、用户答案、标准答案或 evidence refs 的作答不能伪装成稳定 mastery truth。
- public API response 不得泄漏内部批量 evidence payload。

`member_console` 可以保留 `last_assessment`、进度统计和 teaching policy seed 作为 UI /
运营投影，但这些字段不能替代 `learning_evidence`，也不能单独驱动
`learning_synthesis`、`learning_report_read_model` 或 `home_dashboard` 的学习状态判断。

## 投影 (Projections)

允许的读侧 projection 名称（Batch A / B / C 全部用同一个 ledger 派生）：

- `knowledge_state` —— 知识层薄弱与稳态。
- `ability_state` —— 能力维度状态（`question_reading / code_application / calculation / expression / transfer / review_execution`）。
- `behavior_state` —— 行为信号（复发 / 遗忘 / 处方执行 / 仍未理解）。
- `prescription` —— `training_intent` v2 处方流水。
- `scoring_point_map` —— 案例题采分点漏分热点（仅当 `payload.rubric.rubric_mode` ∈
  `{grading_key, curated_rubric}` **或** `projected_rubric` 簇已通过 Phase −1.A
  per-cluster ≥ 70% 门槛后才点亮；否则前端 UI 必须使用 `rubric_pending` 空态）。

`prescription` 字段的唯一 authority 是 `training_intent`；`study_plan` 只能读取/呈现，不能另算处方。

## Forbidden 反模式

以下行为视为违反本 contract，应在 PR review 中被阻断：

- 引入 second learner memory 表 / 第二份 truth ledger。
- 引入第二套 recommendation authority（任何不是 `training_intent` 的处方输出）。
- 任何新的专用聊天 WebSocket 路由（聊天入口仍唯一 `/api/v1/ws`）。
- frontend mastery derivation —— 前端推导 mastery / weak point / 推荐 prompt / diagnosis 文本。
- LLM grader 在 `rubric_specs` 之外的 scoring_point_hits 直接写入 `learning_evidence`
  （必须先经过 `audit.reconcile_grader_output`）。
- 在 `payload.rubric.scoring_point_hits[*].error_code` 中使用未注册的错码（由
  [`docs/contracts/error_code_registry.md`](./error_code_registry.md) +
  [`deeptutor/contracts/error_codes.py`](../../deeptutor/contracts/error_codes.py)
  统一登记）。
- keyword-only / projected rubric 在 UI 上冒充完整"采分点"（前端必须按
  `granularity=keyword_only` 显示为"审题要点"，按 `granularity=scoring_point` 才能
  显示为"采分点"）。
- 直接向 `questions_bank.grading_rubric` 写回（normalizer 与 audit pipeline 都是 read-only）。
- 引入 frontend-derived `evidence_refs`（所有 evidence refs 必须由后端 read model 拼装）。

## 与现有 contract 的关系

本 contract 与 `contracts/learner-state.md`、`contracts/learning-report.md` 是
**层叠** 而非 **替代** 关系：

- `learner-state.md` 定义 `LearnerStateService`、`learner_memory_events` 与 writeback 边界。
- `learning-report.md` 定义 `/api/v1/mobile/learning-report` 与 attempt detail /
  mistake book / training intent / home personalization surface。
- 本文档 (`learning-state-inference.md`) 不引入新表 / 新端点 / 新事件类型，只**约束**
  以上两份 contract 在 Phase −1 → Batch D 期间衍生出的 projection 与处方流水如何
  保持单一权威。

如果未来某次改动想破例（例如增加一个新的 evidence_source 或 projection），必须在
本文档增加显式条目并经 contract review，禁止只在代码层添加而不更新本契约。

## 测试 / 守门

- 数据守门：[`scripts/check_contract_guard.py`](../../scripts/check_contract_guard.py)
  扫描 `_ERROR_CODE_EMIT_PATHS` 中的 emit 站，确保所有错码已登记。
- 结构守门：[`tests/contracts/test_index_consistency.py`](../../tests/contracts/test_index_consistency.py)
  确保仓库根与 `deeptutor/contracts/index.yaml` 同步，且本文件已在 learner_state
  domain 的 `contract_files` 中登记。
- 行为守门：Phase −1 已实现的 `audit.reconcile_grader_output` /
  `classify_rubric_coverage` / `validate_error_code` /
  `study_plan(active_training_intent=...)` / `synthesize_learning_truth(event_limit=...)`
  各自有专属测试套。
