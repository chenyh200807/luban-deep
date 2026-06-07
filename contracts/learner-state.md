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
6. `TutorBot workspace memory` 的 consolidation lock 只负责同一 session 内的并发互斥；它不得成为 learner-state 写回 authority，也不得用弱引用等可被 GC 回收的锁破坏同 session consolidation 的串行化。长期学习事实仍只能通过 `learner_memory_events` / learner-state writeback pipeline 进入 durable truth。

## Member Console / BI Audit Boundary

- `deeptutor/services/member_console/*` 可以记录 admin-facing 运营备注和 BI 审计流水，例如
  `ops_action_result`、`feedback_triage`、`bi_export_request`。
- 这些记录不是 learner state writeback，不得修改 `learner_summaries`、
  `learner_memory_events`、profile、progress、goals、heartbeat 或 overlay 真相。
- 如果某个运营动作需要改变 learner state，必须走 learner-state writeback / promotion
  authority，不能通过 member-console audit helper 旁路写入。
- Assessment TestSet session durability belongs to the assessment authority. In production,
  if Supabase `assessment_sessions` is required but not configured, member-console
  initialization and non-assessment auth/admin paths may still load, but assessment
  create/resume/report/explanation/writeback-retry paths must fail closed with
  `assessment_sessions_supabase_not_configured`; they must not silently use JSON or
  in-memory sessions as production authority.

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
- 首页个性化推荐的 durable projection 只能保存在
  `user_stats.knowledge_map.projections.home_personalization`。服务层读回时可暴露为
  `progress.home_personalization` 以便页面消费，但不得把同一 projection 放入平行表、
  本地 JSON 或 member-console cache 作为第二套权威。
- 学情页教材目录进度不得写入 `user_stats.knowledge_map` 作为第二套主真相。它只能由
  `learning-report-read-model` 读取 taxonomy/textbook-directory 与已有 learning evidence 后即时投影，
  用来展示章节覆盖和证据定位，不得反向覆盖 mastery、weak points 或 diagnosis。

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
- 当 Supabase core store 已配置时，nightly synthesis / online read model 读取
  `learner_memory_events` 必须 remote-first；本地 JSONL 只允许作为
  `LearnerStateService` 写入后的 durable write-ahead ledger，不能由 mobile router、
  learning-report read model 或脚本各自实现成第二套 reader。
- remote-first 不等于在生产环境丢弃尚未 flush 的本地写入：`LearnerStateService`
  读取事件列表时必须合并 Supabase 事件与同一 `user_id` 下的本地 write-ahead JSONL，
  按 event_id / dedupe_key 去重并按时间裁剪。这样 assessment submit 后即使 outbox
  尚未完成远端写回，首页、学情和 report 仍能 read-your-writes；本地 JSONL 只能通过
  `LearnerStateService` 参与该合并，不能绕过 Supabase 成为平行长期权威。
- `dedupe_key` 命中已有事件时必须返回原事件，不能重新生成 event_id 或再次写入 outbox。
  重复作答若要形成 L1/L2 证据，dedupe_key 必须包含 turn/session/attempt 级输入边界。
- `dedupe_key` 命中已有本地 JSONL 事件时，`LearnerStateService` 仍必须确保同一事件存在
  durable outbox 行。已有事件不能因为本地去重而跳过 remote writeback；否则生产 remote-first
  reader 会长期读不到这条证据。
- 单条 evidence 详情读取必须走 indexed reader：
  `LearnerStateService.read_learning_evidence_event(user_id, event_id)`。Supabase core store
  必须按 `user_id + event_id + memory_kind=learning_evidence` 直读；只有本地 dev store
  才允许扫描 JSONL，并且必须有小型 LRU 缓存。生产路径不得通过批量 list 再 filter。
- Conversation synthesis 信号也必须写入同一个 `learner_memory_events` ledger：
  `memory_kind="learning_evidence"` 与 `payload.event_type="learning_evidence"` 不变，
  仅通过 `payload.evidence_source="conversation_synthesis"` 和
  `payload.learning_signal_type` 区分。conversation evidence 不得直接提升 mastery，
  只能进入 recent observation / needs confirmation，直到后续 grading evidence 验证。
- 兼容历史 construction grading 事件：早期 `memory_kind="learning_evidence"` 但缺少
  `payload.event_type` 的 `source_feature="construction_grading"` 事件仍应被 read model
  读取；新写入事件必须带 `payload.event_type="learning_evidence"`。
- Grading-to-Brain loop seam：`build_context_candidates` 除 `compiled_learning_truth` 外，必须再返回
  `personalization_context`（PersonalizationContextPack）。它是**对同一 `compiled_learning_truth` 的投影**
  （单一 authority，不是第二次读取、不是第二套推荐器），由 `build_personalization_context_pack` 生成；
  无 compiled truth 时降级为空 claims（`top_claims=[]`），**绝不**伪造。`personalization_context` 与 claims
  的写入证据仍受 `synthesize_learning_truth` 的 release-eligibility 读过滤约束：shadow/candidate 或
  `quality.writeback_eligible=False` 的事件即使泄漏进 `learner_memory_events`，也不得进入 claim / PCP。
- 手动笔记/卡片来源的召回（recall）注入必须可识别且降权：`build_context_candidates`
  对 `memory_kind` 以 `notebook_` 开头或 `payload.metadata.source_label="student_note"`
  的命中，统一打顶层 `source_label="student_note"`、`weight ≤ 0.4`，并在注入文案前缀
  「（学员自记，不代表已掌握）」。学员主观笔记只作低权重个性化上下文，**不得**被当作
  已掌握证据、不得反向覆盖 learner state（PRD §1.2 / §5）。其余 `memory_hit` 候选行为不变。
- Home dashboard 个性化只能读取 learner-state projection、同一 learner snapshot
  内最近的 canonical `learning_evidence`，或 starter pool。`member_console`
  请求路径不得同步运行完整 learning report，也不得根据 weak point 现场重新推导
  recommended prompts；优先读取 learner snapshot / profile / progress 中的
  `home_personalization` projection。projection 缺失或 stale 时，允许从最近的
  `learner_memory_events.learning_evidence` 恢复一次同形态 projection；若没有有效证据，
  再降级到 `data/seed/<subject_id>/starter_prompts.json`。该 starter pool 是 fallback
  projection，不是第二套推荐 authority。
- 生产 Supabase 写入任何 learner-state 外键表（包括 `learner_memory_events`、
  `learner_summaries`、`learning_plans`、`learning_plan_pages`、`heartbeat_jobs` 和
  overlay 表）前，writeback pipeline 必须先确保同一个 canonical `user_id` 已存在于
  `public.users`，且该镜像行必须满足现有 `users` schema 的必填列（当前线上必填为
  `createdAt`；不得写入 schema 不存在的 `updatedAt`）。移动端生成的 `user_6508` 这类 learner id 不能只停留在本地 JSONL
  或 outbox；否则 remote-first reader 会读不到证据并反复降级到 starter focus。
- Home dashboard、heartbeat context 和 learner-facing projections 如果先经过
  member identity 合并，后续 learner-state reader 必须使用合并后的 canonical
  `member.user_id`。`user_2008` 等 legacy alias 只允许作为入口查询键，不得在
  reconciliation 后继续作为 learner snapshot / heartbeat / personalization 的读键。

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

### Assessment Topic Catalog Read Model

专题测评目录是 TestSet 启动前的可用性 read model，不是 learner-state mastery /
training-intent writer。它必须满足：

1. Catalog authority 来自 `deeptutor.services.assessment.topic_catalog` 定义的 topic
   清单，以及 `assessment_forms` 中每个 `blueprint_version` 的 active form count。
2. 状态只能按 form bank 覆盖与质量校验分类，且达到 3/5 门槛的 topic 必须先通过
   persisted form-bank validator（跨 form `source_question_id` / `semantic_signature`
   去重、每套题量与 section floor）：
   - `stable`: active forms >= 5 且 validator 通过
   - `pilot`: active forms >= 3 and < 5 且 validator 通过
   - `authoring_needed`: active forms < 3，或 validator 不通过
3. `authoring_needed` topic 可以在前端展示维护态，但不得开放正式测评。
4. catalog status 不读取、不写入 `training_intent`、`last_assessment` 或 learner
   mastery；学员个人情况只影响独立的 `recommendation` read model 和后续
   result/report/synthesis，不影响 topic 是否有题。
5. 批量预生成/持久化 `assessment_forms` 前必须 dry-run，并通过目标库 guard；不能让首个
   学员点击时承担全专题冷启动成本。
6. `recommendation` 可以读取 learner-state/member-console 已有 projection 来预选
   “综合摸底”或某个 enabled topic，但只能作为展示建议；它不得创建
   `training_intent`，不得覆盖 study-plan 处方 authority，也不得推荐
   `authoring_needed` topic。

### Assessment TestSet P0A Evidence Contract

P0A TestSet 的学情写回只允许走 `assessment_sessions -> AssessmentWritebackService
-> learner_memory_events(memory_kind=learning_evidence)`。它不是第二套
`training_intent` writer，也不能让 `last_assessment.score` 重新成为 mastery truth。

1. `assessment_sessions` 是一次答卷的唯一 session authority：保存 redacted public
   payload、hidden grading artifact、submit idempotency key、versioned
   `result_report_json`、attempt refs、writeback status 与 degraded reason。
2. 提交前客户端 payload 禁止包含 `answer`、`answer_key`、`correct_answer`、
   `grading_key`、`scoring_points`、`minimal_rationale`、`rubric`、
   `official_answer`、`option_reasoning` 及其嵌套变体。
3. P0A deferred feedback：客户端必须一口气提交整卷后才能看到正确答案、简单解析、
   错题和知识点表现。逐题深解属于后续 Phase，不能改变本次正式得分。
4. 每道已评分题写一条 `source_feature=assessment_testset`、
   `memory_kind=learning_evidence` 的 learner event，dedupe key 固定为
   `assessment_item:{user_id}:{quiz_id}:{question_id}`。
5. P0A evidence 可以进入 `learning_synthesis` 的 observed candidates；是否升级为
   stable weak point 仍由 synthesis 的证据等级和重复性规则决定，不能由 result page
   直接声明“已掌握”或“长期学习计划已更新”。
6. Result page 的下一步建议是 session-local deterministic projection；submit 不直接写
   `training_intent`。Study plan 后续只读取 canonical learner-state projection。
7. 错题集写回必须使用云端 mistake-book authority 与 signed attempt ref；写回失败时
   session 进入 `degraded` 并保留可重试状态，不伪装成完整成功。

### Assessment TestSet P0B/P1 Extension Contract

P0B/P1 只能扩展同一条 TestSet authority，不得为模拟卷、错题训练或深解再建第二套
session / evidence truth。

1. `real_exam_simulation` mini 卷必须复用 `assessment_sessions` durable session
   authority，使用 `real_exam_simulation_mini_v1` blueprint，返回 20 题 redacted
   public payload，并在 `result_report_json.assessment_type` 中保留
   `real_exam_simulation`。
2. 真题样式 mini 卷的用户文案默认只能叫“综合模拟测评”或“真题样式测评”；没有
   provenance + 教研签字时不得声明“官方真题”。
3. P1 deep explanation 是基于已提交 report 和 hidden grading artifact 的 projection：
   可以返回 `cache_key`、`cache_status`、题级解析和 wallet/billing capture 摘要。
   解析文本可以由非流式 LLM 生成，但必须 `score_mutation_allowed=false`，不得回写或
   重算正式得分，不得写 learner-state / training_intent / mastery，也不得修改
   `assessment_sessions` 中的评分 truth。
4. 错题卡“练 3 道同类题”必须把 `attempt_ref`、knowledge point 和 error code 带回
   report training surface；它可以触发后续训练入口，但不得绕过 report / learner-state
   authority 直接跳到 chat 生成第二套处方。

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

## BI v2 Admin Audited-Write 契约（2026-05-23 由 BI 会员经营后台 v2 引入）

这一节锁定 BI v2 后台 admin 直接写入 learner state 边界数据（audit log、note、
conversation view-audit 等）必须遵守的横切契约。所有 `member_console`
路径下的 admin write 端点（router 注册在 `deeptutor/api/routers/member.py`）
都必须满足下列条款，未满足者属于契约违反。

### 强制约束

1. **X-Idempotency-Key**：每个 admin write 必须接 `X-Idempotency-Key` Header。
   缺失或为空 → router 直接 `400`，service 层不被调用。
   - 格式：`^[A-Za-z0-9_-]{1,128}$`（router 加 regex 守护）。
   - 客户端必须由 `web/app/(workspace)/bi/_v2/useAuditedAction.ts` 注入；
     直接 fetch 绕过的代码被 `tests/web/test_bi_v2_raw_fetch_guard.py` 拦截。

2. **Dedup composite key**：service 层 dedup index 形状为
   `f"{action}:{operator}:{idempotency_key}"`。**必须含 operator 段**，
   否则同一 idempotency_key 跨 admin 会互相 dedup，造成跨用户活动隐匿。

3. **Dedup 索引上限**：`AUDIT_IDEMPOTENCY_INDEX_MAX = 10_000`（FIFO 驱逐）。
   防止 admin token 被滥用做 DoS（无界字典 → JSON 膨胀 → I/O 拖慢）。

4. **Audit log append-only**：写入路径走 `MemberConsoleService._append_audit`，
   原子性由 `_mutate` 的 fcntl 锁保证；TOCTOU 已通过把 lookup 移进
   `_apply` 闭包内闭环（R5 M3）。

5. **Reason 白名单**：`conversation_view` 写入时 `reason` 必须是
   `{"complaint", "ops", "teaching", "engineering", "finance"}` 或
   `"other:<note>"`（note ≥ 4 字符）；router 同步去除 `\n` / `\r` 防 log injection。

6. **Single Authority**：BI v2 前端**不创建**第二套会员/钱包/学习/反馈事实源。
   所有写动作经 `useAuditedAction` → 注册在
   `deeptutor/contracts/bi_v2_write_endpoints.py` 的真实 endpoint。

### 单一权威清单

| 子事实 | 唯一 authority | BI v2 前端职责 |
|---|---|---|
| 会员身份 / Tier / 状态 | `MemberConsoleService` + auth identity | 只读 + 受控写经 audited endpoint |
| 钱包余额 / 流水 | `WalletService` | 只读 + idempotency 兜底（P1 接 etag/undo） |
| 学习事实 / 掌握度 | `learner_state` read model | 只读，禁止前端写 |
| 反馈 | `FeedbackService` (P0) | 列表读，triage 在 useAuditedAction 接入后才启用 |
| 后台操作记录 | `member_console.audit_log` | 必须经 `_append_audit`，禁止前端伪造审计 |

### 不允许的设计

7. **前端 setAuditLog 本地状态自称写入 audit log**（已删除；
   `tests/web/test_bi_v2_banner_fetch_coherence.py` 守护回归）。
8. **mock 数据进生产 bundle**（`web/scripts/check_mock_boundary.mjs` 守护）。
9. **banner 写 "已接真实 service" 但代码无 fetch**（同上 banner-fetch coherence guard）。
10. **绕过 useAuditedAction 直接 fetch admin endpoint**
    （`tests/web/test_bi_v2_raw_fetch_guard.py` 守护）。

### 必测项（BI v2 additional）

- 同 `X-Idempotency-Key` 重复 POST → 后端只写 1 条 audit，第二次返回
  同 `audit_id` + `deduped: true`
- 同 key 不同 operator → 写两条 audit（operator binding 生效）
- 索引超过 `AUDIT_IDEMPOTENCY_INDEX_MAX` 时 FIFO 驱逐生效
- 关闭 `BI_BACKOFFICE_V2_SHELL_ENABLED` flag → `/bi` 完整回滚到旧
  `BiPageClient`（1 秒回滚）

### 关联文档

- 计划：`docs/plan/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md`
- 灰度 runbook：`docs/zh/bi/bi-backoffice-v2-rollout-runbook.md`
- 阿里云部署 + 手动测试：`docs/zh/bi/bi-backoffice-v2-aliyun-deploy.md`
- WRITE_ENDPOINTS 注册表：`deeptutor/contracts/bi_v2_write_endpoints.py`
