# 学情页 Contract Guide

## 单一 authority

学情页对外稳定边界由 `contracts/learning-report.md` 管理。代码实现必须遵守：

- 学情页主读模型只由 `build_learning_report_read_model` 生产。
- attempt detail 只读详情由 `attempt_detail_read_model` 生产。
- 错题集事实归属云端 `learner_mistake_book_items`，前端不得把本地 storage 当事实源。
- 训练意图和首页个性化只能读取现有 learning evidence / home dashboard projection，不得新增第二套 learner memory 或推荐 authority。

## Conversation evidence

答疑和解析类学习信号继续写入 `learner_memory_events`：

- `event_type="learning_evidence"`
- `memory_kind="learning_evidence"`
- `payload.evidence_source="conversation_synthesis"`
- `payload.learning_signal_type` 只能是 `answer_explanation`、`concept_explain`、`mistake_explain`、`still_confused`、`home_prompt_clicked`

禁止新增 `conversation_learning_evidence` event type。

## 发布纪律

新增字段、枚举、endpoint 或 migration 前，先更新 `contracts/learning-report.md` 和 `contracts/index.yaml`。生产环境缺少 `DEEPTUTOR_ATTEMPT_REF_SECRET` 时必须 fail closed。
