# DeepTutor BI 数据与指标方案

## 1. 目标

本文档回答 4 个问题：

1. DeepTutor 现在已经有哪些可直接拿来做 BI 的数据源。
2. 为了做完整 BI，还需要补哪些事件和事实表。
3. 关键指标应如何统一口径。
4. 后续开发应该如何分阶段落地。

---

## 2. 现有数据基础盘点

DeepTutor 并不是从零开始。当前仓库中已经存在多条可复用的数据链路。

## 2.1 会话与回合数据

来源文件：

- `deeptutor/services/session/sqlite_store.py`
- `deeptutor/api/routers/dashboard.py`

现有能力：

- `sessions` 表：保存会话标题、创建时间、更新时间、summary、preferences
- `messages` 表：保存消息内容、角色、capability、事件、附件
- `turns` 表：保存每个 turn 的 `status`、开始/结束时间、错误信息
- `turn_events` 表：保存 turn 流式事件
- 已支持按 session 聚合 `message_count`、`status`、`active_turns`
- 已支持按 session 聚合 `cost_summary`

这意味着：

- “活跃会话数”“消息数”“会话深度”“回合成功率”“按 capability 的使用量”
  这些指标，已经具备最基本的数据来源。

## 2.2 成本与 token 可观测性

来源文件：

- `deeptutor/services/observability/langfuse_adapter.py`

现有能力：

- `usage_scope()` 已能按 scope/session/turn 汇总 token
- 已能聚合：
  - `total_input_tokens`
  - `total_output_tokens`
  - `total_tokens`
  - `total_calls`
  - `measured_calls`
  - `estimated_calls`
  - `usage_sources`
  - `models`
  - `total_cost_usd`
- 已有 `start_observation()` 与 `update_observation()` 的 trace 更新链路

这意味着：

- “模型成本占比”“能力平均成本”“用户平均 token 消耗”“成本异常”
  这些 BI 模块，不需要从零埋点。

## 2.3 会员、积分与学习画像

来源文件：

- `deeptutor/services/member_console/service.py`
- `deeptutor/api/routers/member.py`

现有能力：

- 会员 dashboard：总人数、活跃人数、到期人数、风险人数、续费覆盖率
- member list：支持 tier、status、segment、risk_level、auto_renew 等筛选
- member 360：钱包、最近账本、最近备注、章节掌握度、学习偏好
- 账本与积分扣减：`capture_points()`
- 聊天学习记录：`record_chat_learning()`
- 学习侧概览：
  - 今日进度
  - 章节进度
  - home dashboard
  - mastery dashboard
  - radar data
  - assessment profile

这意味着：

- 会员运营与 Learner 360 已有一个很好的业务雏形，BI 只需要把这些数据统一到更高层看板即可。

## 2.4 最近活动 Dashboard

来源文件：

- `deeptutor/api/routers/dashboard.py`

现有能力：

- 可列出最近 session
- 能看 capability、title、更新时间、message_count、status
- 能打开单个 activity 详情

这适合作为 BI 中“最近活跃样本”与“异常样本列表”的基础数据源。

---

## 3. 现有数据不足

尽管已有基础数据，但仍有 5 个明显空缺：

1. 缺少统一用户事件表，无法做完整漏斗与留存。
2. 缺少入口来源维度，难以看 Web/CLI/SDK/小程序/TutorBot 的差异。
3. 缺少 tool 级别与知识库级别的稳定事实表，难做 ROI 分析。
4. 缺少学习结果事件，难定义“学会了”“完成了”“复习了”。
5. 缺少按日聚合表，复杂 BI 查询会落在事务表上，性能和维护性都不好。

另外还有一个已经暴露到用户侧、但尚未真正打通的数据缺口：

- 小程序聊天页已经有点赞/点踩与差评标签交互，但当前后端只做了轻量 note 记录，尚未形成结构化反馈事实。
- 这部分不应继续停留在“运营备注”层，而应升级为正式的消息级反馈链路，进入 Supabase，参与 BI、质量评估与后续产品迭代。
- 该链路建议优先复用 `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/` 中已经跑通过的 `ai_feedback` 设计，而不是在 DeepTutor 再造一张同义表。

因此建议新增一层 BI 专用的事件模型和聚合表。

---

## 4. 事件模型设计

建议将 BI 事件按 6 类组织。

## 4.1 用户行为事件

建议事件：

- `app_opened`
- `session_created`
- `session_resumed`
- `message_sent`
- `message_feedback_submitted`
- `turn_completed`
- `session_closed`
- `notebook_saved`
- `kb_selected`

建议公共字段：

- `event_id`
- `occurred_at`
- `user_id`
- `anonymous_id`
- `session_id`
- `turn_id`
- `entrypoint`
- `platform`
- `brand`
- `language`
- `capability`
- `tool_names`
- `kb_names`

其中 `message_feedback_submitted` 建议作为明确的一等事件，专门承接点赞/点踩：

- 复用 Supabase `ai_feedback` 作为 ODS 来源，避免再建 `message_feedbacks` 之类的重复概念。
- 主键粒度以“用户对某条 assistant message 的一次反馈动作”为准。
- 第一阶段只做“记录 + 统计 + 下钻”，不做自动回写，不把单次差评直接变成执行逻辑。

建议附加字段：

- `message_id`
- `conversation_id`
- `rating`
- `reason_tags`
- `comment`
- `feedback_source`
- `answer_mode`
- `surface`
- `platform`

## 4.2 Agent 运行事件

建议事件：

- `capability_selected`
- `capability_completed`
- `tool_invoked`
- `tool_succeeded`
- `tool_failed`
- `reasoning_escalated`
- `history_reference_used`
- `notebook_reference_used`

关键字段：

- `capability`
- `tool_name`
- `invoke_count`
- `latency_ms`
- `error_type`
- `model`
- `input_tokens`
- `output_tokens`
- `cost_usd`

## 4.3 学习结果事件

建议事件：

- `learning_goal_set`
- `question_generated`
- `question_answered`
- `answer_reviewed`
- `chapter_mastery_updated`
- `review_due_generated`
- `review_completed`
- `learning_summary_saved`

关键字段：

- `chapter`
- `question_type`
- `score`
- `mastery_before`
- `mastery_after`
- `review_due_count`
- `difficulty`

## 4.4 知识库与内容事件

建议事件：

- `kb_query_executed`
- `kb_query_zero_hit`
- `kb_query_hit`
- `kb_document_cited`
- `kb_document_uploaded`
- `kb_document_deleted`
- `notebook_record_created`

关键字段：

- `kb_name`
- `query`
- `result_count`
- `source_type`
- `document_id`
- `citation_count`
- `retrieval_latency_ms`

## 4.5 会员与商业事件

建议事件：

- `membership_granted`
- `membership_updated`
- `membership_revoked`
- `points_granted`
- `points_captured`
- `package_viewed`
- `package_purchased`
- `renewal_reminder_sent`

关键字段：

- `tier`
- `days`
- `delta_points`
- `balance_after`
- `reason`
- `operator`

## 4.6 可观测性与异常事件

建议事件：

- `turn_failed`
- `api_error`
- `timeout`
- `provider_rate_limited`
- `model_fallback_triggered`
- `cost_spike_detected`

关键字段：

- `error_type`
- `provider`
- `model`
- `status_code`
- `retry_count`
- `latency_ms`

---

## 5. 数仓分层建议

建议采用轻量但清晰的三层结构：

- ODS：原始事件与事务数据
- DWD：标准化明细层
- ADS：面向 BI 页面和报表的聚合层

## 5.1 ODS 层

### `ods_sessions`

来自 `sessions`、`messages`、`turns` 的原始抽取。

字段建议：

- `session_id`
- `user_id`
- `entrypoint`
- `capability_first`
- `created_at`
- `updated_at`
- `status`
- `message_count`
- `cost_summary_json`

### `ods_turns`

字段建议：

- `turn_id`
- `session_id`
- `capability`
- `status`
- `error`
- `created_at`
- `finished_at`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `total_cost_usd`
- `models_json`

### `ods_member_profiles`

来自 member console 存量数据。

字段建议：

- `user_id`
- `tier`
- `status`
- `segment`
- `risk_level`
- `auto_renew`
- `expire_at`
- `points_balance`
- `study_days`
- `review_due`
- `daily_target`

### `ods_member_ledger`

字段建议：

- `ledger_id`
- `user_id`
- `delta`
- `reason`
- `created_at`

### `ods_bi_events`

统一事件落表。

字段建议：

- `event_id`
- `event_name`
- `event_time`
- `user_id`
- `session_id`
- `turn_id`
- `payload_json`

### `ods_ai_feedback`

复用旧项目已存在的 Supabase `ai_feedback` 表，作为消息级用户反馈的原始事实层。

字段建议直接对齐现有表，避免重新抽象：

- `id`
- `created_at`
- `user_id`
- `conversation_id`
- `message_id`
- `rating`
- `reason_tags`
- `comment`
- `metadata`

说明：

- `conversation_id` 在 DeepTutor 小程序语境下可直接对应当前聊天 session / conversation。
- `message_id` 优先绑定本地 `messages.id`；若后续 turn 侧暴露更稳定的 assistant artifact/message id，可在入口层做一次归一，不新增第二套反馈主语。
- `metadata` 用于补充 `turn_id`、`entrypoint`、`capability`、`answer_mode`、`surface=wx_miniprogram` 等上下文。

## 5.2 DWD 层

### `dwd_learning_turn`

一行代表一个完成的学习 turn。

关键字段：

- `dt`
- `user_id`
- `session_id`
- `turn_id`
- `entrypoint`
- `capability`
- `success_flag`
- `tool_count`
- `kb_count`
- `input_tokens`
- `output_tokens`
- `cost_usd`
- `latency_ms`
- `notebook_saved_flag`
- `followup_flag`

### `dwd_user_day`

一行代表一个用户某天的汇总行为。

关键字段：

- `dt`
- `user_id`
- `is_active`
- `session_count`
- `turn_count`
- `effective_learning_count`
- `deep_capability_count`
- `question_count`
- `notebook_save_count`
- `token_cost_usd`

### `dwd_kb_query`

一行代表一次知识库查询。

关键字段：

- `dt`
- `user_id`
- `session_id`
- `kb_name`
- `query`
- `result_count`
- `zero_hit_flag`
- `latency_ms`
- `source_types`

## 5.3 ADS 层

### `ads_bi_overview_day`

用于经营总览。

指标建议：

- DAU
- WAU
- 新增用户
- 有效学习用户
- 有效学习会话数
- 深度能力使用人数
- 总 token
- 总成本
- 成功回合率
- 错误率
- 活跃会员数

### `ads_capability_day`

用于能力分析。

指标建议：

- capability 使用次数
- 使用人数
- 平均时长
- 成功率
- 平均 token
- 平均成本
- notebook 保存率

### `ads_tool_day`

用于工具效果。

指标建议：

- tool 调用次数
- 调用成功率
- 平均时延
- 平均成本
- tool 后续转化率
- tool 后续 notebook 保存率

### `ads_kb_day`

用于知识库分析。

指标建议：

- KB 查询次数
- 查询用户数
- 零结果率
- 平均命中数
- 被引用次数
- 带动的 deep_question 次数

### `ads_membership_day`

用于会员与积分。

指标建议：

- 活跃会员数
- 到期人数
- 试用转 VIP 数
- 续费数
- 积分发放
- 积分消耗
- 高风险人数

---

## 6. 关键指标口径

下面给出一套建议的统一口径。

## 6.1 活跃类

### DAU

定义：

- 当天至少产生 1 次 `session_created`、`message_sent` 或 `turn_completed` 的去重用户数

### Active Learner

定义：

- 当天至少产生 1 次“有效学习事件”的去重用户数

有效学习事件建议包括：

- `turn_completed` 且成功
- `notebook_saved`
- `question_answered`
- `review_completed`

## 6.2 留存类

### 次日留存

定义：

- 某天新增或激活用户，在次日再次活跃的比例

### 7 日留存

定义：

- 某天新增或激活用户，在第 7 天再次活跃的比例

## 6.3 学习类

### 有效学习会话率

定义：

- 至少包含一次有效学习事件的会话数 / 总会话数

### 平均会话深度

定义：

- 平均每个 session 的消息轮数或 turn 数

### 能力升级转化率

定义：

- 先使用 `chat`，后在同一 session 或 7 日内升级到 `deep_solve`/`deep_question` 的用户比例

## 6.4 Agent 类

### capability 成功率

定义：

- 某 capability 对应 turn 中 `status = completed` 的比例

### tool 成功率

定义：

- `tool_succeeded / tool_invoked`

### tool ROI

定义建议：

- `(使用 tool 的有效学习率 - 不使用 tool 的有效学习率) / 平均成本增量`

这是一个内部分析指标，不必在前台直接暴露复杂公式，但应用于排序。

## 6.5 知识库类

### KB 查询命中率

定义：

- `result_count > 0` 的 KB 查询次数 / 总 KB 查询次数

### 零结果率

定义：

- `result_count = 0` 的 KB 查询次数 / 总 KB 查询次数

### 引用率

定义：

- 至少引用 1 个 KB 文档的成功回合数 / 总成功回合数

## 6.6 成本类

### 单回合成本

定义：

- `turn_cost_usd / turn_count`

### 单有效学习成本

定义：

- 总成本 / 有效学习闭环数

### 模型成本占比

定义：

- 某模型成本 / 全部模型成本

## 6.7 会员类

### 活跃会员率

定义：

- 活跃会员数 / 会员总数

### 自动续费覆盖率

定义：

- `auto_renew = true` 的会员数 / 会员总数

### 到期风险率

定义：

- 7 天内到期会员数 / 会员总数

### 高风险学员率

定义：

- `risk_level = high` 的用户数 / 活跃会员数

---

## 7. 维度设计建议

BI 中建议统一使用以下维度：

- 时间：日、周、月、小时
- 用户：用户 ID、注册时间、会员层级、学习阶段、风险等级
- 入口：Web、CLI、SDK、WS、MiniProgram、TutorBot
- 能力：chat、deep_solve、deep_question、deep_research、visualize、math_animator
- 工具：rag、web_search、reason、brainstorm、paper_search、code_execution、geogebra_analysis
- 知识库：KB 名称、来源类型、是否默认、是否远端
- 模型：provider、model、计费来源、是否估算
- 品牌/租户：若后续支持多品牌，应提前预留

---

## 8. 建议新增接口

参考 `FastAPI20251222` 中 `routers/bi_router.py` 的做法，DeepTutor 可以新增一组独立 BI 接口：

- `GET /api/v1/bi/overview`
- `GET /api/v1/bi/active-trend`
- `GET /api/v1/bi/retention`
- `GET /api/v1/bi/capabilities`
- `GET /api/v1/bi/tools`
- `GET /api/v1/bi/knowledge`
- `GET /api/v1/bi/cost`
- `GET /api/v1/bi/members`
- `GET /api/v1/bi/user/{user_id}`
- `GET /api/v1/bi/tutorbots`
- `GET /api/v1/bi/anomalies`

建议原则：

1. 先读已有 session/member/observability 数据。
2. 再逐步接入统一事件表。
3. 最后将复杂计算迁移到日聚合表。

---

## 9. 页面与数据映射建议

### 9.1 经营总览页

数据来源建议：

- `ads_bi_overview_day`
- member dashboard 聚合
- capability 日聚合
- 异常事件表

### 9.2 用户增长页

数据来源建议：

- `dwd_user_day`
- 用户注册/激活事件

### 9.3 学习漏斗页

数据来源建议：

- `ods_bi_events`
- `dwd_learning_turn`

### 9.4 能力与工具页

数据来源建议：

- `dwd_learning_turn`
- `ads_capability_day`
- `ads_tool_day`

### 9.5 知识库页

数据来源建议：

- `dwd_kb_query`
- `ads_kb_day`

### 9.6 会员页

数据来源建议：

- member console 现有 dashboard/list/360
- `ads_membership_day`

---

## 10. 实施路线图

## Phase 1：2 周内

目标：

- 有最小可用经营 BI

任务：

1. 新增统一 `bi_events` 落表接口/函数
2. 从 session store 抽取 `ods_sessions`、`ods_turns`
3. 从 observability 抽取成本字段
4. 打通小程序 `POST /api/v1/sessions/{session_id}/messages/{message_id}/feedback` -> Supabase `ai_feedback`
   兼容旧别名 `POST /api/v1/chat/feedback`，但只作为历史兼容入口，不再作为主路径。
5. 先把 `rating / reason_tags / comment / answer_mode / conversation_id / message_id` 结构化入库
6. 聚合 `ads_bi_overview_day`
7. 出基础 BI API

交付：

- 总览页
- 活跃趋势
- capability 分布
- 成本总览
- 会员总览
- 基础满意度卡片（点赞数、点踩数、满意度、差评标签 TopN）

## Phase 2：2 到 4 周

目标：

- 学习与 Agent 效果可衡量

任务：

1. 增加学习事件埋点
2. 增加 tool / KB 查询事实表
3. 建立留存与漏斗分析
4. 输出 Learner 360 BI 版视图

交付：

- 学习漏斗页
- 知识库分析页
- 工具效果页
- 用户分层页

## Phase 3：4 到 8 周

目标：

- 面向运营和增长闭环

任务：

1. 增加续费、召回、风险识别规则
2. 增加 TutorBot ROI 视图
3. 增加自动周报、异常告警
4. 增加人群包导出与动作记录

交付：

- TutorBot 运营页
- 风险学员工作台
- 自动周报
- 异常中心

---

## 11. 数据治理要求

### 11.1 指标口径冻结

所有一级指标必须维护在同一个指标字典中，不允许页面自行解释。

### 11.2 用户身份归一

建议建立统一 `actor_id` 体系：

- 登录用户优先用 `user_id`
- 未登录使用 `anonymous_id`
- TutorBot 触发的事件保留 `bot_id` + `owner_user_id`

### 11.3 成本字段统一币种

当前 `langfuse_adapter` 中存在默认 USD 和部分 CNY 定价来源。进入 BI 前建议统一折算到主展示币种。

### 11.4 隐私与权限

Learner 360 必须支持脱敏展示：

- 手机号脱敏
- access token 不落 BI
- 内容级日志按角色控制查看范围

---

## 12. 最后建议

如果只能做一件事，优先把这 3 条打通：

1. `session / turn / cost` 三者统一主键关系
2. `user / membership / learning outcome` 三者统一用户视图
3. `capability / tool / kb` 三者统一事件模型

这样即使第一版 BI 页面很朴素，也已经具备真正可扩展的数据底座。
