# Learner State Contract

## 范围

这一份 contract 管：

- 学员级长期状态的单一权威
- `Summary / Profile / Progress / Goals / Memory Events / Heartbeat`
- Guided Learning / Notebook / Quiz / TutorBot 对长期状态的写回边界
- 学员级状态与 TutorBot workspace memory 的边界
- 第一阶段 Supabase 复用表与新增表的职责

## 单一控制面

- 单一长期学员状态主键：**第一阶段为 `user_id`**
- 单一 learner state service：后续实现统一收口到 `LearnerStateService`
- 单一长期写回入口：结构化 writeback pipeline
- 单一 heartbeat 调度主语：`user_id`
- 单一 summary 真相：`learner_summaries`

## 第一阶段硬约束

1. 第一阶段不得把长期 learner state 主真相设计成 `bot_id + user_id`。
2. 第一阶段 TutorBot、Guide、Notebook、Quiz、Review、Heartbeat 必须围绕 **同一个 `user_id` 级 learner state** 协同。
3. 如未来确有需要，可以新增 `bot_id + user_id` overlay，但它只能是后置能力，不能提前成为平行主真相。
4. `TutorBot workspace memory` 不是学员长期真相，不能反向覆盖 learner state。
5. Markdown 文件只能是 projection / cache / 可读视图，不能再承担唯一真相。

## 第二阶段预留语义：Bot-Learner Overlay

第二阶段允许在 **不改变 `user_id` 全局 learner truth** 的前提下，引入：

- `bot_id + user_id` 级局部 overlay

实现设计见：

- [2026-04-15-bot-learner-overlay-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-bot-learner-overlay-service-design.md)

但必须满足以下硬约束：

1. Overlay 只能表达 **局部差异**，不能表达第二份长期主真相。
2. Overlay 不得重建：
   - learner profile
   - learner summary
   - learner progress
   - learner goals
3. Overlay 必须挂在全局 learner core 之后读取，挂在 bot template 之前生效。
4. Overlay 的局部事实若想进入全局 learner core，必须经过统一 promotion pipeline。
5. 多 Bot heartbeat 必须先经过全局仲裁，再决定哪个 Bot 最终触达。

### Overlay 允许承载

- `local_focus`
- `active_plan_binding`
- `teaching_policy_override`
- `heartbeat_override`
- `working_memory_projection`
- `channel_presence_override`
- `local_notebook_scope_refs`
- `engagement_state`
- `promotion_candidates`

### Overlay 明确禁止承载

- 学员显示名
- 时区
- 会员计划
- 学员总目标
- 学员全局 mastery
- 学员全局 weak points
- 学员全局 summary
- 学员全局 consent

### Overlay 晋升规则

Overlay 中的局部候选信息，只有在以下条件成立时才允许晋升为全局事实：

1. 来自结构化结果
2. 或者用户明确确认
3. 或者多次重复出现且未与全局事实冲突

普通单轮聊天推断、Bot 局部猜测、短期 focus 都不允许直接晋升。

### Overlay 生命周期规则

Overlay 必须支持：

1. 局部 focus 衰减
2. active plan 完成后自动解绑
3. working memory 限长
4. promotion candidate 过期
5. engagement state 降级

## 复用与新增表

### 必须复用的现有 Supabase 表

#### `user_profiles`

职责：

- 学员长期 profile 主表
- 存放稳定画像、偏好、目标参数、heartbeat 偏好、来源信息

必须真实接入：

- TutorBot runtime 读取
- onboarding / settings 写入
- Guided Learning / Heartbeat 读取
- 运营后台查看与调整

#### `user_stats`

职责：

- 学员长期 progress 主表
- 承接 mastery、weak points、diagnosis、活跃度信号

必须真实接入：

- 做题/批改/复习结果归并
- Guided Learning completion 进度写回
- Heartbeat 读取
- 学员成长看板读取

#### `user_goals`

职责：

- 学员目标与学习计划目标主表

必须真实接入：

- onboarding 目标设定
- study plan generator
- heartbeat 触达理由
- 目标进度更新

### 第一阶段必须新增的表

#### `learner_summaries`

职责：

- `Summary` 单一真相
- 聚合 session / guide / notebook / quiz 的学习摘要
- 承载学习事实编译层的 `summary_structured_json.learning_brain` projection。该 projection
  可以包含 `compiled_objects`、`typed_graph`、`synthesis_run`，但它仍是
  learner summary 的结构化投影，不是第二套 learner profile / progress 主真相。
- `summary_structured_json.guide_completion` 等其他结构化摘要不得被 Learning Brain
  reader 当作 compiled truth 读取。
- 写入 `summary_structured_json` 时必须按顶层 namespace 做 key-level merge；`learning_brain`、
  `guide_completion` 等合法 namespace 不能通过整列 upsert 互相覆盖。
- 本地 `COMPILED_TRUTH.json` 只能作为本地 / dev / dry-run 的只读缓存，由离线
  synthesis 写入；当 Supabase core store 已配置时，在线 TutorBot / RAG runtime
  只能读取 `learner_summaries.summary_structured_json.learning_brain`，不得让本地缓存
  与 durable store 竞争权威；生产环境即使 Supabase core store 未配置，也不得 fail-open
  读取本地 `COMPILED_TRUTH.json`；在线链路不得为了召回临时重跑 synthesis。

#### `learner_memory_events`

职责：

- 所有长期 writeback 的统一结构化事件流
- 支撑 summary/progress 重建、审计与重放
- 建筑实务阅卷产生的 `learning_evidence` 必须作为
  `memory_kind="learning_evidence"` 写入本事件流；不得新增平行 memory 表。

#### `learning_plans`

职责：

- Guided Learning 计划主表

#### `learning_plan_pages`

职责：

- Guided Learning 页面状态与产物主表

#### `heartbeat_jobs`

职责：

- 学员级 heartbeat 调度主表

## 单一写入职责

### Session State

允许写入：

- `turn_runtime`
- 本轮 capability 执行链
- Notebook 的 owner-scoped runtime 引用（如错题本 entry/category 关联）只能围绕同一个 `user_id -> owner_key` 边界持久化，不能跨学员串用或泄露。

禁止写入：

- Guide completion 直接改 session 真相
- Heartbeat 直接改 session 真相

### Learner Profile

允许写入：

- onboarding / settings
- 受控 profile refinement

禁止写入：

- 任意普通聊天直接覆盖 profile
- TutorBot workspace memory 直接覆盖 profile
- 钱包、会员余额、点数、冻结余额、`wallet` projection 等账户事实写入 learner profile；这些事实只属于 wallet / member authority，learner state 只能在读取时忽略或剥离它们。

### Learner Summary

允许写入：

- session digest aggregator
- guided learning completion aggregator
- notebook summary aggregator
- learning synthesis projection refresh

禁止写入：

- 任何模块直接整份覆盖 summary
- 在线 turn runtime 直接合成或改写 compiled truth projection

### Durable Memory Hygiene

`SUMMARY.md`、`PROFILE.md` 以及后续接入 `learner_summaries` 的长期记忆写入必须先经过
统一清理与形状校验：

1. 模型输出中的 `<think>` / `<thinking>` / provider reasoning scratchpad 不得持久化。
2. 读取旧 memory projection 时，如果发现 reasoning 标签，必须自修复或删除空文件。
3. LLM rewrite 结果必须匹配目标 memory 文档形状；模型随口回答、解释过程、内部草稿不得写入长期记忆。
4. 这条规则适用于手动写入、session refresh、turn refresh 和后续 learner state writeback pipeline。

### Learner Progress

允许写入：

- quiz / review / grading 结构化结果
- guided learning progress writer

禁止写入：

- 普通寒暄对话
- 原始 notebook 富文本直写

### Learner Memory Events

允许写入：

- 统一 writeback pipeline
- 建筑实务批改的结构化错因事件必须通过统一 learner state service 写入
  `source_feature="construction_grading"`、`memory_kind="learning_evidence"` 的
  memory event；payload 只能承载题目 id、题型、得分、rubric、错因事件、证据引用、
  typed edges、用户答案和 next training signal。它可以参与后续召回和相似题训练锚点，
  但不得绕过 `LearnerStateService` 直接改 profile / summary / progress 主真相。
- 摸底测评等结构化测评结果可以通过统一 learner state service 写入
  `source_feature="assessment"` 的 memory event；payload 只能承载测评
  `quiz_id`、blueprint version、知识分、置信度、教学策略 seed 与可审计
  observability 摘要，不能绕过 learner state service 直接改 profile / summary /
  progress 主真相。

禁止写入：

- 各模块私自绕过入口写长期 memory
- 仅凭聊天总结、模型印象、最终 Markdown 文本推断并写入 `learning_evidence`。
- 缺少结构化 grading result / active question / answer history 的学习画像事件。
- 将 `<think>` / provider reasoning / tool scratchpad 写进 `payload_json`。

### Learning Brain Projection

`Learning Brain` 是 learner-state 内部的学习事实编译 projection，不是新的
长期记忆 authority。它必须满足：

1. 原始证据只来自 `learner_memory_events`，尤其是结构化 `learning_evidence`、
   grading events、answer history、RAG evidence refs、trace refs、人工修正事件。
2. `compiled_objects`、`typed_graph`、`weak_points`、`synthesis_run` 只能写入
   `learner_summaries.summary_structured_json.learning_brain` 或本地 dry-run 输出。
3. 单次 `L0_observed` 只能服务本轮解释，不得进入稳定画像。
4. `L1_repeated` 可以驱动显性诊断 hint。
5. `L2_confirmed` 必须来自人工确认或多次重复且无强冲突，才可进入稳定 Teaching Policy。
6. 人工修正可以 supersede 自动 claim；人工确认可以把有结构化证据支撑的 claim 升级到
   `L2_confirmed`。
7. synthesis 必须可审计、可重跑：至少记录 input event hash、output projection hash、
   created/updated/decayed/conflict/manual override counts。
8. typed graph 是 JSON projection，不是图数据库；P0/P1 不得新增第二套 graph store。
9. `/wechat-harness` 的 Learning Brain QA wrapper 只允许作为 dev/local 可见链路验证入口；
   它不能承载 grading 或 memory truth，生产环境默认关闭。

### Assessment Session Read Model

摸底测评创建出的 session 是 learner-state 的结构化测评 read model，不是新的
profile / progress 主真相。它必须满足：

1. `create_assessment` 返回给客户端的 payload 必须暴露 `form_source`、`form_id`、
   `form_index`、`form_count`，用于判断题组来自 Supabase 持久化 set、生成后持久化
   set，还是本地静态 fallback。
2. assessment session 的持久化记录和 `observability` 摘要必须保存同一个
   `form_source`，日志也必须打印该字段；不能只在内存 payload 中短暂存在。
3. 如果 Supabase 正式题组不可用，服务可以 fail closed 或走明确的 fallback，但必须
   通过 `form_source` 暴露真实来源，不能伪装成 Supabase 持久化题组。
4. 掌握度看板读取时，最近一次真实摸底测评的 `last_assessment.chapter_mastery`
   优先于 provisional / 空 profile 推断；没有真实测评信号时才允许展示保守的
   provisional 视图。不能在任意低分或未答完情况下默认给出 `overall_mastery=100`。
5. `overall_mastery` 必须从实际章节 mastery 聚合得出；0 分章节必须保留为 0，
   不能被展示层过滤成全满分。

## 写回与冲突规则

1. 明确设置优先于模型推断。
2. 结构化结果优先于自由文本。
3. 单字段 merge 优先于整份覆盖。
4. 同一 `user_id` 的并发写回必须串行化。
5. `TutorBot workspace memory` 只能作为运行时辅助，不得反向成为 learner truth。
6. 第二阶段引入 overlay 后，`user_id` 级 learner core 仍然高于 overlay。
7. Overlay 只能影响当前 Bot 的运行时，不得直接影响其他 Bot。
8. 摸底测评生成的 `teaching_policy_override` 属于 Bot 局部教学节奏建议，只能写入
   overlay 的允许字段；它不能成为第二套 learner profile / progress / summary，也不能
   跨 Bot 覆盖全局学习事实。

## 运行时装配顺序

TutorBot / Guide 运行时上下文装配顺序必须固定：

1. 当前输入
2. session state
3. active question / current learning step
4. learner profile
5. learner summary
6. learner progress
7. notebook / guide references
8. overlay（仅第二阶段）
9. bot template

硬规则：

- 当前输入优先级最高
- bot template 不得覆盖 learner 事实
- workspace memory 不得早于 learner state 注入
- overlay 不得覆盖 learner core 的稳定事实字段

## Heartbeat 规则

1. Heartbeat 的主语必须是学员，而不是 bot。
2. Heartbeat 必须有 consent / quiet hours / cooldown / stop / snooze。
3. Heartbeat 不能作为营销广播系统。
4. Heartbeat 必须记录触达原因、结果与负反馈。
5. 第二阶段多 Bot heartbeat 必须引入全局仲裁，不允许每个 Bot 各发各的。

## 可靠性规则

1. 数据库是最终真相。
2. 本地 durable outbox 是异步写回兜底。
3. Markdown projection 不是最终真相。
4. 所有异步写回必须具备幂等键与可重放能力。

## 不允许的设计

1. 再新增一张与 `user_profiles` 同义的 `learner_profiles` 表，只是名字不同。
2. 再新增一张与 `user_stats` 同义的 `learner_progress` 表，只是名字不同。
3. 让 `Guide`、`Notebook`、`TutorBot memory` 各自维护一份长期 summary 真相。
4. 让 `bot_id + user_id` 在第一阶段偷偷成为第二套长期权威。
5. 在第二阶段把 overlay 扩张为第二套 profile/progress/summary 主真相。

## 必测项

- 新注册学员自动建 learner state
- `user_profiles / user_stats / user_goals` 真正进入 TutorBot / Guide / Heartbeat 读写链
- Guided Learning completion 写回 `learner_summaries / user_stats`
- 摸底测评结果写回 learner memory event 与 Bot overlay 时，保持 `user_id`
  learner core 为单一主真相，并具备幂等键
- heartbeat 按 `user_id` 粒度运行
- 同一学员并发写回无覆盖丢失
