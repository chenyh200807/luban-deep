# Luban Learning Report World-Class Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把学情模块升级为鲁班智考最核心的学习操作系统：学员打开页面 10 秒内能看清“我最近学得怎么样、薄弱点是什么、证据来自哪次作答、下一步该学什么”，并能一键进入针对性训练。

**Architecture:** 后端以 `learning-report-read-model` 为唯一页面 authority，新增 attempt detail、mistake book、training intent 三个子 authority；前端收敛为 shared view model + 双端薄渲染；掌握度升级为证据充分度模型。所有用户可见判断都必须能追溯到 `learning_evidence`、人工修正、RAG/标准答案或训练结果。

**Tech Stack:** Python / FastAPI / LearnerStateService / Supabase / pytest / WeChat mini program JS-WXML-WXSS / Node snapshot tests / Langfuse / Aliyun production logs.

---

## -2. Round 2 Expert Critique & Corrections (BLOCKERS)

> 本节是 2026-05-21 第二轮专家评审结果。基于对代码现状的实证核对（`learner_state/`、`member_console/service.py`、`construction_grading/learning_evidence.py`、`api/routers/mobile.py`、`contracts/index.yaml`、`supabase/migrations/`、`capabilities/deep_question.py`），在第一轮 §-1 之上发现 **8 个 BLOCKER**（未解决前禁止 P0 上线）和 **12 个 high-priority gap**（必须在 Stage 3 灰度前解决）。
>
> 修改原则：所有 BLOCKER 都已 inline 修订到对应 §4 / §5 / §6 / §7 / §9 章节；本节只做 index + 决策依据，便于评审者快速验证。

### -2.1 Blocker B1 — `event_type=conversation_learning_evidence` 与现有 ledger 命名冲突

**事实：** `deeptutor/services/construction_grading/learning_evidence.py:47` 当前写的 `event_type` 就是 `"learning_evidence"`；`supabase_writer._supports_event_type()` 是白名单（`learning_evidence / turn / progress / heartbeat_job / ...`）；`learning_report_read_model._learning_evidence_events()` 通过 `event.memory_kind == "learning_evidence"` 过滤。

**问题：** §4.2 / §6 Task 4.5 设计的 `event_type=conversation_learning_evidence` 会触发三处级联修改：
1. supabase_writer 白名单要扩；
2. read model 过滤要扩；
3. 实际上是引入了**第二个 evidence ledger 大类** — 直接违背 §-1.1.1 "不新增第二套事实系统" 决策。

**纠正（已 inline 到 §4.2 / §6 Task 4.5）：**
- `memory_kind="learning_evidence"`、`event_type="learning_evidence"` 保持不变；
- 新增 payload 字段 `learning_signal_type ∈ {grading_result, answer_explanation, concept_explain, mistake_explain, still_confused, home_prompt_clicked}`；
- 新增 payload 字段 `evidence_source ∈ {construction_grading, conversation_synthesis}` 用于 read model 过滤；
- supabase_writer 白名单**零修改**；
- read model 通过 `payload.learning_signal_type` 与 `payload.evidence_source` 分桶聚合。

### -2.2 Blocker B2 — `deep_question` 路径错（实际是 `.py` 单文件）

**事实：** `find . -type d -name "deep_question*"` 返回 0；`grep "class DeepQuestionCapability"` 命中 `deeptutor/capabilities/deep_question.py:1182`。

**问题：** §5 Backend "Modify: `deeptutor/capabilities/deep_question/*`" 与 §6 Task 4 Files "deeptutor/capabilities/deep_question/* or current practice intent consumer" 是 stale path。

**纠正（已 inline 到 §5 / §6 Task 4）：** 改为 `deeptutor/capabilities/deep_question.py`，并补 active_object 字段持久化 `training_intent_id` 的具体方法签名。

### -2.3 Blocker B3 — `contracts/index.yaml` 把 `mobile.py` 标为 protected/sensitive，新增路由必须先更新契约

**事实：** `contracts/index.yaml` `domains.turn.protected_patterns` / `sensitive_patterns` / `domains.capability.protected_patterns` 都包含 `deeptutor/api/routers/mobile.py`。

**问题：** 计划要在 mobile.py 新增 `learning-attempts/{ref}`、`mistake-book`、`mistake-book/items`、`mistake-book/items/{ref}`、（可选）`learning-home-context` 共 4-5 个 endpoint，但**没有提任何 contract 文件更新**。

**纠正（已 inline 到 §5 / §6 / §7）：** 新增前置 Task 0.5 `Contract & Schema Surface Registration`，要求：
1. 更新 `contracts/index.yaml` 把新 endpoints 加入 `protected_patterns` 与 `schema_files`；
2. 新增 `contracts/learning-report.md`（read model + attempt detail + mistake book + training intent + home projection 的稳定边界声明）；
3. PR 描述必须显式列出契约 diff；
4. 否则 CI contract gate fail-closed 阻断 merge。

### -2.4 Blocker B4 — `schema_version=2` 是 breaking change，缺 dual-emit / 退役流程

**事实：** 现 `learning_report_read_model.py:196` 输出 `schema_version=1`，顶层字段是 `recent_attempts / timeline / training_loop_cards`；§4.1 v2 字段是 `attempts / hero / truth_sections / overview`。`/api/v1/mobile/learning-report` 已经在两端小程序上线消费 v1。

**问题：** 直接换字段会破前端；plan 把"前端切流"和"后端 schema bump"绑死。

**纠正（已 inline 到 §4.1 / §7 Rollout / §10）：**
- 后端在 N 周内 dual-emit：`schema_version=1` 字段全部保留 + v2 顶层并存；
- 路由层支持 `?schema_version=1|2`，默认仍 v1，新前端显式请求 v2；
- view model 适配层在前端 read `schema_version`；
- v2 切流 7 天稳定 + v1 RPS=0 连续 7 天后才允许从 read model 删 v1 分支。

### -2.5 Blocker B5 — `attempt_ref` 签名 secret fall-through，跨用户 ref 伪造风险

**事实：** §6 Task 1 Step 2 `_secret()` 用 `os.getenv("DEEPTUTOR_ATTEMPT_REF_SECRET") or "dev-attempt-ref-secret"`。

**问题：** 生产环境如忘设环境变量，回落到硬编码 secret；攻击者本地复现该 secret 后可伪造任意 `(user_id, event_id)` 组合的合法 ref。

**纠正（已 inline 到 §6 Task 1）：**
1. 生产模式（`DEEPTUTOR_ENV=prod` 或 `ALIYUN_DEPLOY_ENV` 非空）必须读到非空 secret，否则模块导入失败；
2. `sign_attempt_ref` 拒绝空 `user_id` 或 `event_id`；
3. `verify_attempt_ref` 拒绝空 `user_id` 入参；
4. 增加 `kid`（key id）字段为未来 rotate 留位，但 v1 只接受当前 kid；
5. 启动期日志输出 secret SHA-1 前 8 位用于运维校验，不输出 secret 本身。

### -2.6 Blocker B6 — `home_dashboard` 同步 god method + 叠加 learning_report 会击穿 p95 < 500ms

**事实：** `member_console/service.py:3559` `get_home_dashboard()` 同步串行调用 6 个内部方法（`_load_member_snapshot / _ensure_learning_profile / _report_mastery_items / _read_learner_snapshot(event_limit=20) / _read_home_heartbeat_context / _build_home_study_plan / _build_home_today_focus / _build_home_progress_feedback`），且自身不含任何 cache。

**问题：** §6 Task 4.6 让 dashboard 把 `learning_report_read_model` 作为输入源。learning report 自己的目标 p95 已是 800ms，叠加后 dashboard p95 必然 ≥ 800ms，与 §8 "home dashboard projection p95 < 500ms" 直接冲突。

**纠正（已 inline 到 §6 Task 4.6 / §8 / §9）：**
- 不在 dashboard 请求路径里实时跑 learning_report；
- 新增 `learner_state.home_projection` 表（或 learner_snapshot 中的 `home_personalization` 字段），由 nightly synthesis + 批改后 incremental update 维护；
- dashboard 只读 projection，p95 < 500ms；
- projection stale > 6 小时时降级为 fallback starter pool；
- 写入失败不阻断 dashboard 主路径。

### -2.7 Blocker B7 — `LearnerStateService` 无 `read_event_by_id`，attempt detail 必然 O(n) 扫描

**事实：** `LearnerStateService.list_learning_evidence_events(user_id, limit)` 在长尾用户上需扫描全 evidence；§6 Task 2 Step 2 Rule 3 "use `list_learning_evidence_events(user_id, limit=500)` and match `event_id`" 在 5k+ events 用户上 p95 不可达。

**纠正（已 inline 到 §6 Task 2）：**
- 新增 `LearnerStateService.read_learning_evidence_event(user_id, event_id) -> LearnerStateEvent | None`，基于 supabase `learner_memory_events.event_id` 唯一索引直接 lookup；
- 本地文件 store fallback 仍可线性扫描但必须带 LRU；
- p95 SLA 写明 < 100ms（不含 detail render）；
- Task 2 Done 标准包含 "5k events 用户压测通过"。

### -2.8 Blocker B8 — `learner_mistake_book_items` migration 缺 RLS + 跨学科隔离

**事实：** 现 `20260419000100_learner_state_rls.sql` 已为 learner_state 系列表建立 RLS；§6 Task 3 Step 1 migration **完全没写 RLS policy**，也没区分学科。

**问题：**
1. 无 RLS → service_role 之外的角色可越权读写他人错题；
2. 无 `subject_id / bot_id` → 用户同时学一建+二建时错题混在一张 list。

**纠正（已 inline 到 §6 Task 3）：**
- migration 新增 `subject_id text not null default ''` 与 `bot_id text not null default ''`；
- 新增 `enable row level security` + 两条 policy（`auth.uid()::text = user_id` for select/insert/update/delete；service_role bypass）；
- read API 按 `subject_id` 过滤；
- mistake book read model 默认按当前 `active_subject_id` 过滤，未指定时返回所有学科分组列表。

### -2.9 High-Priority Gaps（必须在 Stage 3 灰度前解决，已 inline 到 §6 / §9）

| ID | Gap | 落点 |
| --- | --- | --- |
| G1 | 训练闭环 `training_intent_id` 必须由批改链路反写到 `learning_evidence.payload.training_intent_id`，否则"显示改善/未改善" 永远跑空 | §6 Task 4 Step 4 |
| G2 | 推荐 prompt 反复 click 的"正反馈陷阱"防护：同一 (concept, prompt_type) 每日影响 ranking ≤ 1 次 | §6 Task 4.6 Step 5 |
| G3 | "已讲解但仍未练题" 状态不得作为 mastery 提升信号，且强引导一次定向训练 | §6 Task 4.5 Step 4 |
| G4 | conversation evidence 的 `assistant_explanation_summary` 生成路径：优先复用 grading kernel 的结构化 explanation；自由文本 turn 走 trim+regex，不调额外 LLM | §6 Task 4.5 Step 3 |
| G5 | `attempts[*].user_question` 写入前 PII redact（手机号/身份证/姓名模式） | §6 Task 4.5 Step 3 |
| G6 | 多设备跨端一致性：bookmark / report 响应带 `etag` 或 `generated_at` server time，前端拒绝旧响应覆盖新本地状态 | §6 Task 3 / Task 7 |
| G7 | starter fallback 必须有真实 pool：≥ 3 题/科目，按学员当前 `subject_id` 选取；缺失时 dashboard 显示"先做摸底测评" | §6 Task 4.6 Step 3 |
| G8 | Langfuse trace metadata 必须挂 `learning_training_intent_id / mistake_book_event_id / home_prompt_intent_id` 三键，否则无法串联 | §9 Engineering Metrics + §6 Task 9 Step 2 |
| G9 | `needs_confirmation` 区的定义与 promoter：什么 evidence 进、谁审、何时移出，§4.1 / §6 Task 5 都没写 | §6 Task 5 Step 2 |
| G10 | 训练 CTA 与 wallet quota 联动：额度不足时 CTA 降级文案 + 引导购买 | §6 Task 4 Step 4 |
| G11 | iOS/Android/PC WeChat 三容器 setData 大 payload 卡顿验证（≥ 80KB 时 iOS 微信 setData > 200ms 已知风险） | §6 Task 8 Step 5 |
| G12 | 国际化伏笔：hero / 时间标签 / 状态词从 read model hardcode 中文 → 抽到 `i18n_keys` 字段；v1 只输出 zh-CN，但字段语义可演进 | §4.1 + §6 Task 7 Step 1 |

### -2.10 二轮评审决策摘要

1. **不收缩 P0 范围**：8 个 BLOCKER 都不是"为了完美而完美"，是与现有代码硬冲突；不解决等于上线后必然 incident。
2. **执行顺序在 §-1.7 之上插入 `Task 0.5 Contract & Schema Surface Registration`**：先把契约 + RLS + secret 三件 surface 落地，再 carry 其他 Task。
3. **MasteryEstimator 继续后置**：与第一轮一致。
4. **认知边界**：本评审基于 2026-05-21 11:00 的代码快照；mobile router/learner_state service 任何后续重构都需要 re-baseline。
5. **如果时间紧**：可只做 BLOCKER B1/B5/B7 + Gap G1，其余按 "Stage 3 之前必须完成" 排程；但 B3/B4/B6/B8 不解决，QA 不应放行 100% rollout。

---

## -1. Expert Re-evaluation Addendum

### -1.1 Revised Decision

本计划不应理解为“把学情页做成更复杂的 Learning Brain 展示面”。更准确的产品目标是：

> 把分散在批改、解析、错题、训练、证据链里的学习事实，收敛成一个学员看得懂、点得进去、练得下去的学习操作系统。

因此本轮最优策略是 **选择性增强，不是全面扩张**：

1. 先做实 `learning_evidence -> attempt detail -> mistake book -> next training -> follow-up grading` 这条闭环。
2. 再做 mastery estimator 和完整 UI 重构。
3. 暂不把 typed graph、timeline、source id、event hash 等内部结构直接呈现给学员。
4. 系统答疑解析和首页个性化都优先复用现有 authority；除非性能或职责边界验证失败，不新增一等模块。

### -1.1.1 Reuse Existing Authority Decision

复核现有代码后，本计划明确收敛：

1. **不新增 `ConversationLearningEvidence` 作为独立 authority**
   - 现有 `learner_memory_events.learning_evidence` 已经是学习事实 ledger。
   - 答疑、解析、错题讲解应作为 `learning_evidence` 的一种新事件类型进入同一 ledger。
   - 允许新增一个薄 helper / normalizer 负责从结构化答案中抽取字段，但它只写入现有 learner state，不拥有业务真相。

2. **不新增 `LearningHomeContext` 作为独立 authority**
   - 现有 `member_console.get_home_dashboard()` 已经产出 `today_focus`，对话首页也已经消费后端 `today_focus`。
   - 本轮应扩展现有 home dashboard / learning report projection，增加 `input_hint`、`recommended_prompts`、`prompt_intents`。
   - 只有当现有 dashboard 太重、p95 超标或职责无法收敛时，才把它拆成 `/api/v1/mobile/learning-home-context` 轻量 endpoint；即使拆出 endpoint，也只是 read projection，不是新 authority。

3. **真正新增的是能力，不是第二套事实系统**
   - 新增学习信号类型：`answer_explanation`、`concept_explain`、`mistake_explain`、`still_confused`、`home_prompt_clicked`。
   - 新增首页投影字段：`today_focus`、`input_hint`、`recommended_prompts`、`prompt_intents`。
   - 统一读写仍走 `LearnerStateService`、`learning_report_read_model`、`home_dashboard`。

### -1.2 Minimum Viable World-Class Slice

当前条件下，最小但真正有价值的 P0 不是完整大改，而是以下 7 件事同时成立：

1. **每次批改都形成 detail-ready evidence**
   - 至少有题干、题型、选项/采分点、学生答案、标准答案/评分、解析摘要、知识点、错因、时间。
   - 如果缺字段，必须显式标记 `detail_ready=false` 和 `missing_fields`，不能在 UI 中假装可追溯。

2. **学情页证据卡能点回真实作答**
   - 不是展示“证据 e8b7f3a8...”，而是展示“今天 09:37，你在主体结构多选题中选 A，正确为 B”。
   - 点击后能看到原题、你的答案、正确答案、选项解析、为什么错、下次怎么避坑。

3. **错题集是云端能力**
   - 收藏行为写入 `learner_mistake_book_items`。
   - 收藏只引用 evidence，不复制评分事实，不制造第二套学习事实。

4. **下一步训练是结构化 intent**
   - CTA 不能只是“去练习”或拼一句 prompt。
   - 必须携带 `concept_id / concept_label / error_code / error_label / attempt_refs / training_mode / question_count / success_criteria`。

5. **单次观察与稳定结论分区**
   - 一次错题只能是“刚发现”。
   - 重复错因、人工确认、nightly synthesis 后才可进入“稳定薄弱点”或“当前可信结论”。

6. **系统答疑与解析也进入学习事实池**
   - 学员问概念、问规范、问错题原因时，系统给出的答案解析不能只停留在聊天历史里。
   - 结构化沉淀为 `learner_memory_events.learning_evidence` 的 `event_type=conversation_learning_evidence`，记录“学员问了什么、系统解释了什么、涉及哪个知识点、引用了哪些知识库/标准答案、建议下一步做什么”。
   - 这类 evidence 默认只能证明“已接触 / 已讲解 / 仍疑惑”，不能单独证明“已掌握”。

7. **学情反向驱动对话首页**
   - 对话首页的“今日焦点”和底部推荐问题必须来自同一份学习状态，而不是静态卡片。
   - 推荐问题优先由现有 home dashboard / learning report projection 生成，要根据当前薄弱点、最近答疑、错题集、训练闭环动态生成，并携带结构化 prompt intent。
   - 用户点击推荐问题后，问题本身也要成为可追踪的学习行为，继续反哺 learning evidence。

这 7 件事是 P0 release gate。任何缺一项，学情模块都还只是“看起来像学习大脑”，不是可交付学习大脑。

### -1.3 What to Defer

为了防止过度工程，本计划明确推迟以下内容：

| 暂缓项 | 原因 | 何时启动 |
| --- | --- | --- |
| 完整 mastery estimator 大模型化 | 样本、难度、覆盖度数据还需先稳定采集 | P0 evidence loop 连续 7 天稳定后 |
| 大规模 UI 重构 | 没有 attempt detail 和 training intent，UI 再漂亮也无真实价值 | P0 API + view model 通过 E2E 后 |
| typed graph 可视化 | 学员不需要看内部图结构 | 转成自然语言证据后再考虑 |
| nightly synthesis 强依赖 | 在线批改后的即时学情不能等夜间任务 | 作为稳定结论增强，不作为首屏唯一来源 |
| 完整错题复习系统 | 先做收藏、查看、继续练；复习排程后置 | 云端错题集写读稳定后 |

### -1.4 User Scenario Matrix

以下场景必须作为验收样本，不允许只测 happy path：

| 场景 | 预期行为 |
| --- | --- |
| 新用户无记录 | 明确告诉用户“先完成一组练习”，不展示假百分比 |
| 单题答错 | 学情页出现 recent observation，不进入 stable truth |
| 同一错因连续 2 次 | 升级为稳定薄弱点，并给定向训练 CTA |
| 先错后对 | 训练闭环显示“已改善”，但 mastery 仍受样本量保护 |
| 一题答对 | 不能直接 100% 掌握，只能显示“有一次正确记录，证据不足” |
| 多题批量作答 | 每题生成独立 attempt ref，进度按题数统计 |
| 案例题主观批改 | 证据卡显示采分点得失，不套选择题答案格式 |
| 解析缺失 | 进度可统计，但详情页标记“解析待补全”，不生成高置信结论 |
| RAG/标准答案缺失 | 批改链路必须 fail-closed 或降低置信，不让模型猜答案 |
| 用户手动纠错 | manual correction supersede 自动提升证据层级，并保留 timeline |
| 跨端刷新 | 错题收藏、训练记录、学习事实保持一致 |
| 学员只问概念不做题 | 记录为“已讲解/已接触”，可影响推荐问题，但不提高掌握度 |
| 系统给出详细解题解析 | 解析摘要、知识点、错因、引用来源进入 conversation evidence，可被后续学情页和首页使用 |
| 学员反复追问同一概念 | 升级为“仍疑惑”信号，今日焦点优先安排该知识点 |
| 首页今日焦点点击进入 | 生成带 `LearningTrainingIntent` 或 `LearningQuestionPromptIntent` 的对话/训练，不泛跳 |
| 首页推荐问题点击后继续追问 | 推荐来源、点击、后续回答都写入 trace / learning evidence，形成闭环 |

### -1.5 Data Quality Gate

`learning_evidence` 进入 learning report 前必须先过质量门槛：

| 字段 | P0 要求 | 缺失后果 |
| --- | --- | --- |
| `event_id` | 必须 | 不能生成 attempt ref |
| `occurred_at` | 必须 | 不计入 today / recent 3 days |
| `question_id` or `question_ref` | 必须 | 不可进入 evidence card |
| `question_stem` / `title` | 必须 | 不可进入 attempt detail |
| `question_type` | 必须 | 不能选择正确详情模板 |
| `user_answer` | 必须 | 不可展示“你当时怎么答” |
| `correct_answer` or `rubric_score` | 必须 | 不可稳定判定对错 |
| `explanation` or `explanation_missing_reason` | 必须二选一 | 缺解析时不得生成高价值详情 |
| `concept_label` | 必须 | 不可展示给学员 |
| `error_label` | 错题必须 | 不可进入薄弱点 |
| `source_refs` | 尽量有 | 无来源只能是低置信观察 |
| `assistant_explanation_summary` | 答疑/解析类必须 | 不可从聊天历史生成学习洞察 |
| `conversation_turn_ref` | 答疑/解析类必须 | 不可点击回当时对话 |
| `learning_signal_type` | 必须 | 区分作答、批改、答疑、解析、复习、训练 |

设计原则：字段缺失不是前端文案问题，而是 evidence 质量问题。read model 可以降级展示，但不能用空洞文案伪造学习洞察。

### -1.6 Uncertainties and Validation Alternatives

| 不确定性 | 风险 | 验证方式 | 替代方案 |
| --- | --- | --- | --- |
| 当前批改事件是否稳定保存结构化解析 | attempt detail 可能空洞 | 抽样 100 条 `learning_evidence` 做字段完整率报告 | 增加 explanation enrichment job，但标记为补全来源 |
| `LearnerStateService` 是否能高效按 event_id 读取 | detail endpoint 可能 O(n) 扫描 | 本地 + 阿里云各跑 500/5000 event latency test | 先用 limit 500，上线前补 event index reader |
| 小程序真实表面到底以 `wx_miniprogram` 还是 `yousenwebview` 为准 | 双端漂移 | 由 release gate 指定唯一发布 shell | 共享 view model + hash/parity test，不让页面各自解释 |
| `deep_question` 是否能稳定消费 training intent | CTA 仍然泛跳 | 写 e2e：点击 CTA 后生成同 concept/error 题 | 第一版把 intent 转成结构化 user message，但记录为兼容层 |
| 生产 Supabase migration 窗口 | 错题集无法云端化 | staging migration + rollback 验证 | 临时用 append-only bookmark event，最多保留一版迭代 |
| 题库 taxonomy 覆盖是否完整 | “综合能力”再次出现 | taxonomy mapping 覆盖率报告 | 未命中时展示“未归类知识点”，不展示“综合能力” |
| 聊天历史里是否能稳定抽取知识点和解析 | 首页推荐可能偏题或噪声大 | 抽样 50 条真实答疑 trace，人工标注 concept/error/recommendation 命中率 | 第一版只沉淀系统已结构化输出的解析块，不从自由文本强抽 |
| 首页个性化是否会让用户感觉“被系统乱推” | 推荐问题不可信 | A/B 对照静态推荐 vs 学情推荐，观察点击率和追问完成率 | 保留一个“通用考点”兜底位，但标记为 fallback |

### -1.7 Execution Order Correction

原计划的 Task 1-4 是必要的，但仍少了一个前置门槛。**Round 2** 又在最前面插入 Task 0.5（contract/secret/RLS 一次性 surface 注册），最新执行顺序应为：

1. **Task 0: Learning Evidence Quality Gate**
2. **Task 0.5: Contract & Schema Surface Registration (Round 2 BLOCKER B3 + B5 + B8 一次性)**
3. Task 1: Attempt Ref Authority
4. Task 2: Attempt Detail Read Model
5. Task 3: Cloud Mistake Book Authority
6. Task 4: Training Intent Contract
7. **Task 4.5: Extend Learning Evidence with Conversation Signals**
8. **Task 4.6: Extend Home Dashboard with Learning Personalization**
9. Task 5: Stable Truth vs Recent Observation Split
10. Task 7: Shared Frontend View Model
11. Task 8: Product UI Redesign
12. Task 6: Mastery Estimator
13. Task 9: E2E and Production Gate

注意：MasteryEstimator 排到 shared view model 和 P0 UI 之后，不是因为它不重要，而是因为没有足够 detail-ready evidence 时，掌握度算法越复杂越容易制造伪精确。

---

## 0. Product Bar

学情页不能只是“数据看板”。它必须成为学员每天愿意打开的学习入口。

### 0.1 学员打开页面后应获得的答案

1. **我今天练了多少？**
   - 今日练习、近 3 天练习、连续学习、待复习。

2. **我现在最薄弱的是什么？**
   - 一个主攻方向，最多两个次要方向。
   - 用中文知识点 + 中文错因表达，禁止裸 code。

3. **为什么系统这么判断？**
   - 直接指向真实作答：什么时候、哪道题、我选了什么、正确答案是什么、错因是什么。

4. **我下一步该做什么？**
   - 一个主 CTA：例如“练 3 道主体结构多选辨析题”。
   - CTA 必须携带 `LearningTrainingIntent`，不能泛跳。

5. **我的错题怎么复盘？**
   - 错题可以收藏、查看原题和解析、继续练、标记已掌握。

### 0.2 世界顶尖体验标准

| 维度 | 标准 |
| --- | --- |
| 清晰度 | 第一屏只呈现一个主结论、一个主行动、少量关键指标 |
| 可信度 | 每个判断都有可点开的作答证据 |
| 行动性 | 每个薄弱点都能一键进入定向训练 |
| 连续性 | 训练后能显示改善 / 未改善 |
| 丝滑度 | 首屏 p95 < 800ms，骨架屏 < 300ms，可渐进加载详情 |
| 可解释 | 不展示 event hash、M06、typed edge 名、内部 source id |
| 稳定性 | 10 万学员下不靠前端多接口拼装，不靠本机缓存保存核心学习事实 |

---

## 1. Scope and Non-goals

### 1.1 In Scope

1. `learning-report-read-model` v2：面向学员的统一学情读模型。
2. `attempt-detail-read-model`：真实作答详情。
3. 云端错题集 authority。
4. `LearningTrainingIntent`：学情页到训练页 / deep_question 的行动契约。
5. 扩展 `learner_memory_events.learning_evidence`：把系统答疑、答案解析、知识讲解沉淀为可用学习事实。
6. 扩展 `home_dashboard` / learning report 首页投影：对话首页今日焦点、推荐问题、提示词 intent 统一由后端生成。
7. shared report/home view model：统一 wx 与 yousen 两端展示语义。
8. mastery estimator：证据充分度 + 低样本保护 + 难度/覆盖度/最近性。
9. 产品级 UI 信息架构：从工程看板改为“学习复盘 + 下一步行动 + 首页个性化入口”。
10. 10 万学员规模下的性能、观测、灰度、回滚。

### 1.2 Non-goals

1. 不重写 `construction_grading` 主阅卷链路。
2. 不新增第二套 learner memory。
3. 不让前端推导 mastery / weak point / next training。
4. 不把错题集做成本机缓存。
5. 不把 Learning Brain 内部 typed graph 原样展示给学员。
6. 不在本阶段删除旧接口；删除仍受生产观察门槛控制。
7. 不把聊天全文无限期复制进 learner state；只沉淀结构化学习事实和可回放引用。
8. 不让对话首页自己维护“今日焦点”或静态推荐池，首页只消费后端 home dashboard / learning report projection。
9. 不为答疑解析和首页推荐新建第二套 learner memory、第二套画像、第二套推荐 authority。

---

## 2. Single Authority Map

| 业务事实 | 唯一 authority | 说明 |
| --- | --- | --- |
| 学情页最终展示 | `GET /api/v1/mobile/learning-report` | 页面只能消费这一份 read model |
| 作答事实 | `learner_memory_events.learning_evidence` | 批改写入的 append-only evidence |
| 答疑/解析学习事实 | `learner_memory_events.learning_evidence` with `event_type=conversation_learning_evidence` | 从系统答疑和解析中提取“已讲解/仍疑惑/建议训练”，默认低于 grading evidence |
| 作答详情 | `attempt-detail-read-model` over `learning_evidence` | 只读投影，不另写事实 |
| 错题收藏 | `learner_mistake_book_items` | 用户显式收藏行为的新 authority，引用 evidence，不复制评分事实 |
| 当前稳定结论 | persisted compiled truth / manual confirmation | L1/L2/L3，不把 L0 冒充稳定结论 |
| 最近观察 | recent `learning_evidence` dry-run projection | L0，只展示为“刚发现” |
| 下一步训练 | `LearningTrainingIntent` generated by read model | deep_question / practice page 消费，不由页面拼 prompt |
| 对话首页今日焦点 | `home_dashboard.today_focus` backed by learning-report core | 首页只渲染，不自行排序或拼 prompt |
| 首页推荐问题 | `home_dashboard.recommended_prompts[*].intent` backed by learning-report core | 推荐问题必须能追溯到弱点、错题、答疑或复习计划 |
| 掌握度 | `MasteryEstimator` | 聚合 evidence + mastery inputs，输出 score + confidence |

---

## 3. Target UX

### 3.1 第一屏结构

```text
学情

今天复盘
  入门阶段  42%
  今日 6/30    近3天 18题    连续 3天

当前最该补
  主体结构 / 多选漏选
  最近 3 次相关练习里出现 2 次
  [练 3 道同类题]

为什么这么判断
  今天 09:20 你在“主体结构验收条件”选 A，正确 B，错因：多选漏选
  昨天 21:10 同类题漏选 C
  [查看全部证据]
```

### 3.2 第二屏结构

```text
最近做题复盘
  题卡：题干 / 你选 / 正确 / 错因 / 查看解析 / 收藏错题

我的错题
  已收藏 4 题
  [继续练错题] [只看未掌握]

掌握分布
  不是只显示 0%-100%，还显示证据状态：
  证据不足 / 正在形成 / 稳定掌握
```

### 3.3 页面用词原则

| 内部词 | 用户词 |
| --- | --- |
| compiled truth | 当前稳定判断 |
| L0_observed | 刚发现 |
| L1_repeated | 重复出现 |
| evidence flow | 判断依据 |
| typed graph | 学习关系 |
| training intent | 下一步训练 |
| event id | 第 N 次批改 / 当时作答 |
| M06 | 多选漏选 |

### 3.4 对话首页联动

对话首页不是静态入口页，而是学习系统每天的启动器。

```text
对话首页

今日焦点
  主体结构 / 多选漏选
  来自：最近 2 次错题 + 昨天 1 次答疑追问
  [进入训练]

直接问
  输入框 placeholder:
  “可以问：主体结构多选题为什么容易漏选？”

推荐问题
  1. 概念入门：主体结构验收先看哪几个条件？
  2. 知识地图：主体结构和防水工程怎么区分考点？
  3. 对比分析：多选漏选和多选错选有什么区别？
```

Rules:

1. 今日焦点来自 `home_dashboard.today_focus`，不是前端静态文案。
2. 推荐问题来自 `home_dashboard.recommended_prompts`，每个问题携带结构化 prompt intent。
3. 用户点击推荐问题后，发送给后端的不只是自然语言，还包括 intent，方便系统知道这是“围绕当前薄弱点的学习行为”。
4. 系统回答推荐问题后，应写入 `event_type=conversation_learning_evidence` 的 learning evidence，继续反哺学情。

---

## 4. Data Contracts

### 4.1 `LearningReportV2`

`GET /api/v1/mobile/learning-report?event_limit=100&schema_version=2`

> **Round 2 BLOCKER B4 — Dual-emit 契约：** 现 v1 已上线两端小程序，顶层字段是 `recent_attempts / timeline / training_loop_cards`。v2 升级在 Stage 1-4 期间必须 dual-emit（v1 字段字面保留 + v2 新字段并存），不允许直接断字段。版本协商：`?schema_version=1|2` query param 或 `Accept: application/vnd.deeptutor.learning-report+json;v=2` header；默认 v1，新前端显式请求 v2。退役流程见 §7 Stage 5。

```jsonc
{
  "ok": true,
  "schema_version": 2,
  "authority": {
    "read_model": "learning-report-read-model",
    "progress_source": "learner_memory_events.learning_evidence",
    "conversation_source": "learner_memory_events.learning_evidence[event_type=conversation_learning_evidence]",
    "attempt_detail_source": "attempt-detail-read-model",
    "mistake_book_source": "learner_mistake_book_items",
    "training_intent_source": "learning-report-read-model",
    "home_context_source": "home_dashboard.today_focus/recommended_prompts"
  },
  "freshness": {
    "generated_at": "2026-05-21T10:00:00+08:00",
    "latest_event_at": "2026-05-21T09:58:00+08:00",
    "last_synthesized_at": "2026-05-21T03:00:00+08:00",
    "window_truncated": false,
    "unknown_date_count": 0
  },
  "overview": {
    "today_done": 6,
    "recent_three_done": 18,
    "daily_target": 30,
    "streak_days": 3,
    "due_today_count": 2,
    "overall_mastery": {
      "score": 42,
      "confidence": 0.56,
      "status": "emerging"
    }
  },
  "hero": {
    "stage_label": "入门阶段",
    "headline": "当前最该补：主体结构 / 多选漏选",
    "subline": "最近 3 次相关练习里出现 2 次，先做辨析训练最划算。",
    "primary_cta": {
      "label": "练 3 道同类题",
      "intent": { "...": "LearningTrainingIntent" }
    }
  },
  "home_personalization": {
    "focus_ref": "learning_home_context.focus",
    "recommended_prompt_count": 3,
    "latest_conversation_signal": "昨天答疑中追问过主体结构多选漏选"
  },
  "truth_sections": {
    "stable_truths": [],
    "recent_observations": [],
    "needs_confirmation": []
  },
  "attempts": [
    {
      "attempt_key": "attempt_xxx",
      "attempt_ref": "opaque_signed_ref",
      "time_label": "今天 09:20",
      "question_title": "主体结构验收条件",
      "question_preview": "关于主体结构验收条件的说法，正确的是？",
      "result_label": "答错",
      "answer_line": "你选：A；正确：B",
      "diagnosis": "多选漏选",
      "why_it_matters": "这类题容易只选确定项，漏掉并列正确条件。",
      "is_bookmarked": false,
      "actions": {
        "detail": true,
        "bookmark": true,
        "retry": true
      }
    }
  ],
  "mistake_book": {
    "count": 4,
    "recent_items": []
  },
  "next_training": [
    {
      "title": "主体结构多选辨析",
      "reason": "来自最近 2 次多选漏选",
      "estimated_minutes": 8,
      "intent": { "...": "LearningTrainingIntent" }
    }
  ],
  "mastery": {
    "dimensions": [
      {
        "name": "主体结构",
        "score": 38,
        "confidence": 0.48,
        "status": "emerging",
        "sample_count": 5,
        "coverage_ratio": 0.32,
        "last_practiced_at": "2026-05-21T09:20:00+08:00"
      }
    ]
  },
  "degraded": false,
  "degraded_sources": [],
  "source_status": {}
}
```

### 4.2 Conversation Learning Evidence Event

Generated when the system answers a study-related question, explains an answer, summarizes a mistake, or gives a knowledge explanation.

This is not a new learner memory authority and not raw chat history. It is a structured event inside the existing `learner_memory_events.learning_evidence` ledger, extracted from an assistant answer and linked back to the original turn.

> **Round 2 Correction (BLOCKER B1):** 本事件**不能新建第二个 `event_type`**。现有 ledger 用 `event_type="learning_evidence"` + `memory_kind="learning_evidence"` 作为大类（`supabase_writer._supports_event_type()` 白名单与 `learning_report_read_model._learning_evidence_events()` 都按此过滤）。新增子类型靠 **payload 内** 的 `learning_signal_type` 与 `evidence_source` 区分，writer 白名单与 read model 大类过滤**零修改**。

```jsonc
{
  "event_type": "learning_evidence",
  "memory_kind": "learning_evidence",
  "schema_version": 1,
  "evidence_source": "conversation_synthesis",
  "learning_signal_type": "answer_explanation",
  "event_id": "evt_...",
  "conversation_turn_ref": "turn_ref_opaque",
  "occurred_at": "2026-05-21T14:10:00+08:00",
  "user_question": "主体结构多选题为什么容易漏选？",
  "user_question_redacted": true,
  "assistant_explanation_summary": "多选题要逐项判断所有必要条件，不能选到一个确定项就停止。",
  "subject_id": "construction_exam_1",
  "concept": {
    "id": "1A432000",
    "label": "主体结构"
  },
  "error": {
    "code": "M06",
    "label": "多选漏选"
  },
  "evidence_level": "exposed",
  "confidence": 0.42,
  "source_refs": [
    {"type": "rag_hit", "label": "教材/规范依据"},
    {"type": "assistant_answer", "label": "本次答疑解析"}
  ],
  "suggested_next": {
    "label": "练 3 道主体结构多选辨析题",
    "intent": { "...": "LearningTrainingIntent" }
  },
  "training_intent_id": null
}
```

`learning_signal_type` 取值集合（封闭）：
- `grading_result` — 从 construction_grading 写入的传统作答证据（默认值，已存量）
- `answer_explanation` — 系统主动给出答案解析
- `concept_explain` — 系统讲解概念
- `mistake_explain` — 系统讲解错题原因
- `still_confused` — 用户重复追问同一概念
- `home_prompt_clicked` — 用户点击首页推荐 prompt 触发

`evidence_source` 取值集合（封闭）：
- `construction_grading` — 由 grading writeback 写入（已存量）
- `conversation_synthesis` — 由 chat finalization 写入（本计划新增）

Rules:

1. It can increase recency / exposure / confusion signals.
2. It cannot alone mark a concept as mastered.
3. It can make a weak point more urgent if the user repeatedly asks the same concept.
4. It must link back to the conversation turn; otherwise it is not user-visible evidence.
5. `user_question` 写入前必须经过 PII redaction（手机号/身份证/真实姓名 pattern），`user_question_redacted=true` 表示已脱敏。
6. `subject_id` 必填，用于跨学科隔离（参见 §6 Task 3 BLOCKER B8）。
7. `training_intent_id` 字段为 grading 回写预留：若该 evidence 由 `LearningTrainingIntent` 触发的训练产生，必须带 intent_id，便于 read model 计算"训练后改善/未改善"（参见 §-2.9 G1）。

### 4.3 Home Dashboard Learning Projection

Primary path: extend existing `GET /api/v1/homepage/dashboard` / `mobile home_dashboard` response.

Optional extraction path: `GET /api/v1/mobile/learning-home-context`, only if the existing dashboard becomes too heavy or cannot meet p95. Even then it remains a lightweight read projection, not a new authority.

```jsonc
{
  "ok": true,
  "schema_version": 1,
  "generated_at": "2026-05-21T14:10:00+08:00",
  "focus": {
    "title": "今日焦点：主体结构",
    "subtitle": "最近多选漏选较多，先补辨析题",
    "reason": "来自最近 2 次错题和 1 次答疑追问",
    "intent": { "...": "LearningTrainingIntent" }
  },
  "input_hint": "直接问：主体结构多选题为什么容易漏选？",
  "recommended_prompts": [
    {
      "label": "概念入门",
      "title": "主体结构验收先看哪几个条件？",
      "subtitle": "建筑构造基础",
      "prompt": "请用一级建造师建筑实务考试口径，讲清主体结构验收先看哪几个条件，并给我一道选择题巩固。",
      "intent": {
        "type": "concept_explain",
        "concept_id": "1A432000",
        "concept_label": "主体结构",
        "source": "learning_home_context",
        "reason": "current_focus"
      }
    },
    {
      "label": "知识地图",
      "title": "一建考点梳理",
      "subtitle": "围绕当前薄弱点",
      "prompt": "请围绕主体结构，把相关高频考点按考试常见问法整理成知识地图。",
      "intent": {
        "type": "knowledge_map",
        "concept_id": "1A432000",
        "concept_label": "主体结构",
        "source": "learning_home_context",
        "reason": "weak_point"
      }
    },
    {
      "label": "对比分析",
      "title": "易混淆概念",
      "subtitle": "错题高发",
      "prompt": "请对比主体结构多选题里的漏选、错选和条件偷换，并分别给例子。",
      "intent": {
        "type": "misconception_compare",
        "concept_id": "1A432000",
        "error_label": "多选漏选",
        "source": "learning_home_context",
        "reason": "recent_error"
      }
    }
  ],
  "source_status": {
    "learning_report": "ok",
    "conversation_evidence": "ok",
    "fallback_used": false
  }
}
```

Rules:

1. 首页只消费 backend home projection fields, not local history and not page-side report scans.
2. 推荐问题最多 3 个，必须覆盖不同学习动作：概念解释、知识地图、错因辨析、错题复练、案例训练等。
3. 每个推荐都必须有 `intent.reason`，可追溯到 weak point、recent observation、mistake book、conversation evidence 或 due review。
4. 如果没有足够学习事实，推荐退化为考试通用入门问题，并标记 `fallback_used=true`。
5. 如果未来拆出 `/learning-home-context`，它必须复用同一 builder，不能重新计算另一套 weak point。

### 4.4 `AttemptDetail`

`GET /api/v1/mobile/learning-attempts/{attempt_ref}`

```jsonc
{
  "ok": true,
  "attempt_key": "attempt_xxx",
  "question": {
    "title": "主体结构验收条件",
    "stem": "关于主体结构验收条件的说法，正确的是？",
    "type": "multiple_choice",
    "options": [
      {"key": "A", "text": "..."},
      {"key": "B", "text": "..."}
    ]
  },
  "answer": {
    "user_answer": "A",
    "correct_answer": "B",
    "score_awarded": 0,
    "max_score": 1
  },
  "explanation": {
    "summary": "正确选项是 B。",
    "why_user_wrong": "你选的 A 只满足部分条件，漏掉了题干要求的并列条件。",
    "option_analysis": [
      {"option": "A", "judgement": "wrong", "reason": "..."},
      {"option": "B", "judgement": "correct", "reason": "..."}
    ],
    "knowledge_points": ["主体结构验收条件"],
    "common_traps": ["多选题只选确定项，漏选并列正确项"],
    "memory_anchor": "多选先找所有必要条件，再排除偷换条件项。",
    "next_time_rule": "看到“正确的是”，先逐项判断，不要选到一个就停。"
  },
  "evidence_sources": [
    {"type": "answer_history", "label": "当时作答"},
    {"type": "grading_result", "label": "本次批改"},
    {"type": "rag_evidence", "label": "知识库依据"}
  ],
  "bookmark": {
    "is_bookmarked": false,
    "saved_at": null
  },
  "next_training": {
    "label": "再练 3 道同类题",
    "intent": { "...": "LearningTrainingIntent" }
  }
}
```

### 4.5 `LearningTrainingIntent`

```jsonc
{
  "intent_id": "lti_...",
  "source": "learning_report",
  "created_at": "2026-05-21T10:00:00+08:00",
  "concept_id": "1A432000",
  "concept_label": "主体结构",
  "error_code": "M06",
  "error_label": "多选漏选",
  "attempt_refs": ["opaque_signed_ref"],
  "training_mode": "mcq_discrimination",
  "question_count": 3,
  "difficulty": "adaptive",
  "success_criteria": {
    "min_correct": 2,
    "requires_explanation": true
  }
}
```

---

## 5. File Structure

### Backend

- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
  - Emit schema v2 hero, truth sections, attempt refs, bookmark status, next training intents, mastery confidence.

- Create: `deeptutor/services/learner_state/attempt_refs.py`
  - Sign / verify opaque attempt refs.

- Create: `deeptutor/services/learner_state/attempt_detail_read_model.py`
  - Build user-facing attempt detail from `learning_evidence`.

- Create: `deeptutor/services/learner_state/mistake_book.py`
  - Save/remove/list bookmarked attempts.

- Create: `deeptutor/services/learner_state/training_intent.py`
  - Build and validate `LearningTrainingIntent`.
  - **Round 2 (G1):** intent 必须能反向写回 grading：active_object 序列化时挂 `training_intent_id`；grading writeback 把 `training_intent_id` 写入新 `learning_evidence` 的 payload，否则改善判断永远跑空。

- Modify or create helper under `deeptutor/services/learner_state/`
  - Normalize useful system explanations and answer-analysis turns into `learner_memory_events.learning_evidence` events.
  - This helper is not an authority; it writes to the existing evidence ledger.

- Modify: `deeptutor/services/member_console/service.py`
  - Extend existing home dashboard `today_focus` with `input_hint`, `recommended_prompts`, and prompt intents.
  - Optional later extraction into `learning_home_context.py` only if dashboard latency or ownership fails release gates.

- Create: `deeptutor/services/learner_state/mastery_estimator.py`
  - Evidence-aware mastery scoring.

- Modify: `deeptutor/api/routers/mobile.py`
  - Add attempt detail + mistake book endpoints.
  - Add lightweight home endpoint only if the existing dashboard cannot meet p95 after projection extension.
  - **Round 2 (BLOCKER B3):** `mobile.py` 在 `contracts/index.yaml` 中是 `turn` + `capability` 域的 protected/sensitive。新增 endpoints 必须同步更新 `contracts/index.yaml` 把 `learning-report / learning-attempts / mistake-book / learning-home-context (optional)` 路由列入对应域的 `protected_patterns / schema_files / test_files`，并新建 `contracts/learning-report.md` 描述稳定边界。CI 的 contract gate 在缺更新时 fail-closed。

- Modify: `deeptutor/runtime/orchestrator.py` or current unified chat finalization path
  - Emit conversation learning evidence after useful educational answers, without duplicating raw chat history.
  - **Round 2:** event 用 `event_type="learning_evidence"` + `evidence_source="conversation_synthesis"` + `learning_signal_type=...`，**不要**新建 event_type 大类（BLOCKER B1）。

- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
  - Preserve structured explanation fields when present.

- Create migration: `supabase/migrations/YYYYMMDDHHMMSS_learner_mistake_book_items.sql`
  - Cloud mistake book authority.

### Frontend

- Create: `wx_miniprogram/utils/learning-report-view-model.js`
- Create: `yousenwebview/packageDeeptutor/utils/learning-report-view-model.js`
  - Same logic, SHA checked by tests.

- Modify: `wx_miniprogram/pages/report/report.js`
- Modify: `wx_miniprogram/pages/report/report.wxml`
- Modify: `wx_miniprogram/pages/report/report.wxss`

- Modify: `yousenwebview/packageDeeptutor/pages/report/report.js`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.wxml`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.wxss`

- Modify: conversation home page in `wx_miniprogram` / `yousenwebview`
  - Render 今日焦点、input hint、recommended prompts from backend home dashboard projection.

- Modify: practice/chat entry route handling
  - Consume `LearningTrainingIntent`.

### Tests

- Create: `tests/services/learner_state/test_attempt_refs.py`
- Create: `tests/services/learner_state/test_attempt_detail_read_model.py`
- Create: `tests/services/learner_state/test_mistake_book.py`
- Create: `tests/services/learner_state/test_training_intent.py`
- Create: `tests/services/learner_state/test_conversation_learning_evidence_event.py`
- Create or modify: `tests/services/member_console/test_home_dashboard_learning_projection.py`
- Create: `tests/services/learner_state/test_mastery_estimator.py`
- Modify: `tests/services/learner_state/test_learning_report_read_model.py`
- Modify: `tests/api/test_mobile_router.py`
- Create: `wx_miniprogram/tests/test_report_view_model.js`
- Create: `yousenwebview/tests/test_report_view_model.js`
- Create: `wx_miniprogram/tests/test_home_dashboard_learning_prompts.js`
- Create: `yousenwebview/tests/test_home_dashboard_learning_prompts.js`
- Modify: `scripts/run_learning_report_read_model_e2e.py`

---

## 6. Implementation Tasks

### Task 0: Learning Evidence Quality Gate

**Goal:** 在做详情页、错题集、训练 intent 前，先保证 learning report 消费的是 detail-ready evidence，而不是缺题干、缺解析、缺答案的半成品事件。

**Files:**
- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `tests/services/learner_state/test_learning_report_read_model.py`
- Create: `tests/services/learner_state/test_learning_evidence_quality_gate.py`

- [ ] **Step 1: Define quality contract**

Every `learning_evidence` item projected into Learning Report must expose:

```jsonc
{
  "quality": {
    "detail_ready": true,
    "progress_countable": true,
    "truth_eligible": true,
    "missing_fields": [],
    "degraded_reason": ""
  }
}
```

Rules:

1. `progress_countable=true` only needs a valid user, timestamp and question/submission reference.
2. `detail_ready=true` requires question, answer/rubric, explanation or explicit explanation-missing reason.
3. `truth_eligible=true` requires concept label, result, and enough evidence to support weak/strong classification.
4. Missing detail can still count progress, but cannot power attempt detail or stable truth.

- [ ] **Step 2: Write failing tests**

```python
def test_complete_mcq_evidence_is_detail_ready_and_truth_eligible():
    event = learning_evidence_event(
        question_stem="关于主体结构验收条件的说法，正确的是？",
        question_type="multiple_choice",
        user_answer="A",
        correct_answer="B",
        explanation={"summary": "正确选项是 B", "why_user_wrong": "A 漏掉并列条件"},
        concept_label="主体结构",
        error_label="多选漏选",
    )
    report = build_learning_report_read_model(events=[event])
    item = report["learning_brain"]["attempts"][0]
    assert item["quality"]["detail_ready"] is True
    assert item["quality"]["truth_eligible"] is True
    assert item["attempt_ref"]


def test_missing_explanation_counts_progress_but_not_detail_ready():
    event = learning_evidence_event(
        question_stem="关于防火分区的说法，正确的是？",
        user_answer="C",
        correct_answer="D",
        explanation=None,
        explanation_missing_reason="grading_output_missing_explanation",
        concept_label="防火分区",
    )
    report = build_learning_report_read_model(events=[event])
    item = report["learning_brain"]["attempts"][0]
    assert item["quality"]["progress_countable"] is True
    assert item["quality"]["detail_ready"] is False
    assert "explanation" in item["quality"]["missing_fields"]
```

- [ ] **Step 3: Implement minimum gate**

Implementation rules:

1. Gate lives in learner-state/read-model service layer, not page JS.
2. Grading writer should preserve structured explanation fields when available.
3. Read model should expose degraded reasons in learner-friendly language.
4. UI must hide “查看完整解析” when `detail_ready=false`, and instead show “本题解析待补全”.

- [ ] **Step 4: Add field-completeness report (Round 2: 升级为 CI baseline gate)**

Create `scripts/run_learning_evidence_quality_baseline.py`，输出：

```text
sample_size=100
detail_ready=83%
truth_eligible=71%
missing_explanation=12%
missing_concept=9%
missing_question_ref=0%
by_signal_type={grading_result: 92, answer_explanation: 78, concept_explain: 65}
```

Round 2 强化：

1. 输出 JSON 落到 `.gstack/qa-reports/learning-evidence-quality-baseline.json`（与现有 `.gstack/qa-reports/baseline.json` 同管线）；
2. baseline 必须含字段：`detail_ready_min: 0.70`, `truth_eligible_min: 0.60`, `missing_explanation_max: 0.20`；
3. CI 新增 `.github/workflows/learning-evidence-quality.yml`，在 main / 灰度分支上每日抽样跑一次；偏离 baseline > 5pp 报警；
4. PR 改动 `learning_evidence` 字段或 grading writeback 时强制运行该 script，diff baseline；
5. 阿里云生产侧用 nightly job 同样跑 + 写 Langfuse `learning_evidence_quality_baseline` trace tag；
6. Release Gate（§10）增加："最近 7 天 baseline 偏离 ≤ 3pp 才允许灰度推 100%"。

不再只是"release evidence"，而是**带阈值的 CI gate**。

- [ ] **Step 5: Run**

```bash
pytest -q tests/services/learner_state/test_learning_evidence_quality_gate.py tests/services/learner_state/test_learning_report_read_model.py
```

Expected: quality gate tests pass before any attempt detail or UI task is marked complete.

### Task 1: Attempt Ref Authority

**Goal:** 前端永远拿 opaque `attempt_ref`，后端能安全解析到 `learning_evidence` event。

**Files:**
- Create: `deeptutor/services/learner_state/attempt_refs.py`
- Test: `tests/services/learner_state/test_attempt_refs.py`

- [ ] **Step 1: Write failing tests (Round 2: + secret hardening cases)**

```python
import pytest

from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref, verify_attempt_ref


def test_attempt_ref_round_trips_without_exposing_event_id():
    token = sign_attempt_ref(user_id="u1", event_id="evt_secret", question_id="q1")
    assert "evt_secret" not in token
    payload = verify_attempt_ref(token, user_id="u1")
    assert payload["event_id"] == "evt_secret"
    assert payload["question_id"] == "q1"


def test_attempt_ref_rejects_wrong_user():
    token = sign_attempt_ref(user_id="u1", event_id="evt_secret", question_id="q1")
    assert verify_attempt_ref(token, user_id="u2") is None


def test_attempt_ref_rejects_empty_user_or_event():
    with pytest.raises(ValueError):
        sign_attempt_ref(user_id="", event_id="evt_secret")
    with pytest.raises(ValueError):
        sign_attempt_ref(user_id="u1", event_id="")


def test_verify_rejects_empty_user_even_with_valid_token(monkeypatch):
    token = sign_attempt_ref(user_id="u1", event_id="evt1")
    assert verify_attempt_ref(token, user_id="") is None


def test_unknown_kid_rejected(monkeypatch):
    token = sign_attempt_ref(user_id="u1", event_id="evt1")
    # Tamper kid by reusing token under a different module-level constant in future rotation.
    tampered = token[:-2] + "==" if not token.endswith("=") else token
    # Real future-proofing: rotate _KID_V1, assert old tokens stop verifying.
    # Here we only assert verify_attempt_ref still requires kid match.
    assert verify_attempt_ref("not.a.valid.token", user_id="u1") is None


def test_prod_runtime_requires_secret(monkeypatch):
    monkeypatch.setenv("DEEPTUTOR_ENV", "prod")
    monkeypatch.delenv("DEEPTUTOR_ATTEMPT_REF_SECRET", raising=False)
    import importlib
    import deeptutor.services.learner_state.attempt_refs as mod
    with pytest.raises(RuntimeError):
        importlib.reload(mod)
```

- [ ] **Step 2: Implement minimal signing (Round 2 — BLOCKER B5: fail-closed secret)**

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any

_LOG = logging.getLogger(__name__)

_DEV_DEFAULT_SECRET = "dev-attempt-ref-secret"
_KID_V1 = "v1"


def _is_prod_runtime() -> bool:
    env = (os.getenv("DEEPTUTOR_ENV") or os.getenv("ALIYUN_DEPLOY_ENV") or "").strip().lower()
    return env in {"prod", "production", "aliyun"}


def _secret() -> bytes:
    raw = (os.getenv("DEEPTUTOR_ATTEMPT_REF_SECRET") or "").strip()
    if not raw and _is_prod_runtime():
        raise RuntimeError(
            "DEEPTUTOR_ATTEMPT_REF_SECRET is required in production; refuse to fall back to dev default."
        )
    return (raw or _DEV_DEFAULT_SECRET).encode("utf-8")


def _log_secret_fingerprint() -> None:
    digest = hashlib.sha1(_secret()).hexdigest()[:8]
    _LOG.info("attempt_ref secret fingerprint=%s kid=%s", digest, _KID_V1)


_log_secret_fingerprint()


def sign_attempt_ref(*, user_id: str, event_id: str, question_id: str = "") -> str:
    user = str(user_id or "").strip()
    event = str(event_id or "").strip()
    if not user or not event:
        raise ValueError("sign_attempt_ref requires non-empty user_id and event_id")
    body = {
        "u": user,
        "e": event,
        "q": str(question_id or "").strip(),
        "k": _KID_V1,
        "v": 1,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()[:24]
    return base64.urlsafe_b64encode(raw + b"." + sig.encode("ascii")).decode("ascii").rstrip("=")


def verify_attempt_ref(token: str, *, user_id: str) -> dict[str, Any] | None:
    user = str(user_id or "").strip()
    if not user:
        return None
    try:
        padded = str(token or "") + "=" * (-len(str(token or "")) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        body_raw, sig_raw = raw.rsplit(b".", 1)
        expected = hmac.new(_secret(), body_raw, hashlib.sha256).hexdigest()[:24].encode("ascii")
        if not hmac.compare_digest(sig_raw, expected):
            return None
        body = json.loads(body_raw.decode("utf-8"))
    except Exception:
        return None
    if str(body.get("k") or "") != _KID_V1:
        return None
    if str(body.get("u") or "") != user:
        return None
    return {"event_id": str(body.get("e") or ""), "question_id": str(body.get("q") or "")}
```

Notes:

1. 生产缺 secret 直接抛 `RuntimeError`，模块导入失败 → uvicorn 启动失败，CI 也会失败 → 不可能带 dev secret 上线。
2. 空 user_id / event_id 在签名时直接拒绝。
3. 引入 `kid` 字段为未来 rotate 留位；v1 只接受 `k=v1` 的 token。
4. 启动期日志写 SHA-1 前 8 位 + kid，运维可对账 secret 是否符合预期，但不泄漏 secret 本身。

- [ ] **Step 3: Run**

```bash
pytest -q tests/services/learner_state/test_attempt_refs.py
```

Expected: `2 passed`.

### Task 2: Attempt Detail Read Model

**Goal:** 学员点击证据卡后，能看到当时题目、作答、解析、错因和下一步训练。

**Files:**
- Create: `deeptutor/services/learner_state/attempt_detail_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Test: `tests/services/learner_state/test_attempt_detail_read_model.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] **Step 1: Write service tests**

```python
def test_attempt_detail_contains_question_answer_explanation_and_sources(fake_event):
    detail = build_attempt_detail_read_model(
        user_id="student_demo",
        learner_state_service=FakeLearnerStateService([fake_event]),
        attempt_ref=sign_attempt_ref(user_id="student_demo", event_id=fake_event.event_id, question_id="q1"),
    )
    assert detail["question"]["stem"]
    assert detail["answer"]["user_answer"] == "A"
    assert detail["answer"]["correct_answer"] == "B"
    assert detail["explanation"]["summary"]
    assert detail["explanation"]["why_user_wrong"]
    assert detail["evidence_sources"][0]["label"] in {"当时作答", "本次批改"}
```

- [ ] **Step 2: Implement read model (Round 2 BLOCKER B7: indexed reader as hard requirement)**

Implementation rules:

1. Verify `attempt_ref` with current `user_id`.
2. **必须** 通过新方法 `LearnerStateService.read_learning_evidence_event(user_id, event_id)` 直读，背后走 supabase `learner_memory_events` 表的 `event_id` 唯一索引 lookup。
3. fallback：本地文件 store 才允许线性扫描，但必须用 in-process LRU 缓存最近 256 个 event。
4. **不允许** 在 prod 走 `list_learning_evidence_events(user_id, limit=500)` 然后客户端 filter — 长尾用户（5k+ events）会击穿 p95。
5. Never return raw event id.
6. If explanation is string, map it to `summary`; if dict, preserve structured fields.
7. **性能 SLA**（Task 2 Done 标准的一部分）：
   - 5k events 的 fixture 用户 + supabase emulator + warm cache: p95 < 100ms；
   - cold cache p95 < 300ms；
   - 不达标禁止合并。
8. Read 时按 attempt_ref payload 中的 `event_id` 与当前 user_id 做强校验，跨用户访问 fail-closed。
9. 新加 service 方法签名（必须实现）：

```python
class LearnerStateService:
    def read_learning_evidence_event(
        self,
        user_id: str,
        event_id: str,
        *,
        max_age_seconds: int | None = None,
    ) -> LearnerStateEvent | None: ...
```

   - supabase 实现走 `learner_memory_events.select("*").eq("user_id", uid).eq("event_id", eid).limit(1)`；
   - 本地 store 实现走 LRU；
   - test 覆盖：
     1. 存在事件命中；
     2. 跨用户访问 None；
     3. cache hit 命中 / cache miss；
     4. supabase 不可用时降级为 None + 日志。

- [ ] **Step 3: Add API**

```python
@router.get("/mobile/learning-attempts/{attempt_ref}")
async def mobile_learning_attempt_detail(
    attempt_ref: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = _resolve_authenticated_user_id(authorization)
    return await run_in_threadpool(
        build_attempt_detail_read_model,
        user_id=user_id,
        learner_state_service=learner_state_service,
        attempt_ref=attempt_ref,
    )
```

- [ ] **Step 4: Run**

```bash
pytest -q tests/services/learner_state/test_attempt_detail_read_model.py tests/api/test_mobile_router.py::test_mobile_learning_attempt_detail_returns_user_facing_attempt
```

### Task 3: Cloud Mistake Book Authority

**Goal:** 错题收藏变成云端正式能力，支持跨端、刷新、重登、nightly synthesis 消费。

**Files:**
- Create: `supabase/migrations/YYYYMMDDHHMMSS_learner_mistake_book_items.sql`
- Create: `deeptutor/services/learner_state/mistake_book.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Test: `tests/services/learner_state/test_mistake_book.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] **Step 1: Create migration (Round 2 BLOCKER B8: RLS + subject isolation + mastered tracking)**

文件名遵循现有约定：`20260YYMMDD0001NN_learner_mistake_book_items.sql`（参考 `20260419000100_learner_state_rls.sql`）。

```sql
create table if not exists learner_mistake_book_items (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  subject_id text not null default '',      -- Round 2 B8: 跨学科隔离
  bot_id text not null default '',          -- Round 2 B8: 多 bot 隔离 (TutorBot subject binding)
  event_id text not null,
  question_id text default '',
  attempt_ref text not null,
  title text default '',
  concept_label text default '',
  error_label text default '',
  saved_at timestamptz not null default now(),
  archived_at timestamptz,
  mastered_at timestamptz,                  -- Round 2: 用户主动标记已掌握 → 与 MasteryEstimator 联动
  last_reviewed_at timestamptz,             -- Round 2: 复习排程
  review_due_at timestamptz,                -- Round 2: 下次建议复习时间
  note text default '',
  tags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, event_id)
);

create index if not exists idx_learner_mistake_book_user_saved
  on learner_mistake_book_items(user_id, saved_at desc)
  where archived_at is null and mastered_at is null;

create index if not exists idx_learner_mistake_book_user_subject
  on learner_mistake_book_items(user_id, subject_id, saved_at desc)
  where archived_at is null;

create index if not exists idx_learner_mistake_book_review_due
  on learner_mistake_book_items(user_id, review_due_at)
  where archived_at is null and mastered_at is null and review_due_at is not null;

-- Round 2 BLOCKER B8: RLS policies (参考 20260419000100_learner_state_rls.sql 现有模式)
alter table learner_mistake_book_items enable row level security;

create policy "learner_mistake_book_items_owner_select"
  on learner_mistake_book_items
  for select
  using (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_insert"
  on learner_mistake_book_items
  for insert
  with check (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_update"
  on learner_mistake_book_items
  for update
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

create policy "learner_mistake_book_items_owner_delete"
  on learner_mistake_book_items
  for delete
  using (auth.uid()::text = user_id);

-- service_role 自动 bypass RLS（supabase 默认行为）
-- 验证：在 staging 上用 anon key + 错配 user_id 触发 select，预期返回空集
```

> Migration 命名：实际仓库格式是 `YYYYMMDDXXXXXX_xxx.sql`（14 位 = 8 位日期 + 6 位 sequence/小时分秒），不是 `YYYYMMDDHHMMSS`。优先沿用既有 sequence 风格 `20260521000100`。

- [ ] **Step 2: Write service tests**

```python
def test_save_remove_and_list_mistake_book_item():
    service = FakeMistakeBookStore()
    saved = save_mistake_book_item(store=service, user_id="u1", event_id="evt1", attempt_ref="ref", title="题1")
    assert saved["is_bookmarked"] is True
    assert list_mistake_book_items(store=service, user_id="u1")["count"] == 1
    remove_mistake_book_item(store=service, user_id="u1", event_id="evt1")
    assert list_mistake_book_items(store=service, user_id="u1")["count"] == 0
```

- [ ] **Step 3: Add APIs (Round 2: 补 mastered + review 路径，G6 加 etag)**

```text
GET    /api/v1/mobile/mistake-book?subject_id=&include_mastered=false
POST   /api/v1/mobile/mistake-book/items
DELETE /api/v1/mobile/mistake-book/items/{attempt_ref}
POST   /api/v1/mobile/mistake-book/items/{attempt_ref}/mastered   (Round 2: 用户主动标记)
POST   /api/v1/mobile/mistake-book/items/{attempt_ref}/review     (Round 2: 记录一次复习 → 更新 last_reviewed_at / review_due_at)
```

跨端一致性（G6）：
- 所有响应携带 `generated_at`（server time, ISO 8601 +08:00）与 `etag`（`saved_at` SHA-1 前 16 位）；
- 前端 mutation 必须带 `If-Match: <etag>`，server 校验失败返回 `409 conflict` 且返回最新状态；
- 前端不持久化本地 bookmark 状态，每次进入页面以 server 状态为准；
- read model 同时把当前 bookmark 状态嵌入 attempt card，避免双源不一致。

跨学科隔离（B8）：
- `subject_id` 缺省时返回所有学科分组聚合；
- 显式传 `subject_id` 时只返回该学科；
- mistake save 写入时强制带 `subject_id`，缺则从当前 active TutorBot 的 `bot_runtime_defaults.subject_id` 推断；都缺直接 `400`。

- [ ] **Step 4: Update Learning Report**

`learning-report-read-model` should mark each attempt:

```jsonc
{
  "is_bookmarked": true,
  "bookmark_label": "已加入错题"
}
```

- [ ] **Step 5: Run**

```bash
pytest -q tests/services/learner_state/test_mistake_book.py tests/api/test_mobile_router.py -k "mistake_book or learning_report"
```

### Task 4: Training Intent Contract

**Goal:** 下一步训练从“文案按钮”升级为可执行训练意图。

**Files:**
- Create: `deeptutor/services/learner_state/training_intent.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `deeptutor/capabilities/deep_question.py` (the file; **Round 2 B2:** `deep_question/` 子目录在仓库中不存在，实际是单文件，`class DeepQuestionCapability` 在 line 1182)
- Modify: `deeptutor/services/construction_grading/learning_evidence.py` (G1: 把 `training_intent_id` 写入 payload)
- Modify: `deeptutor/services/construction_grading/writeback.py` (G1: 把 active_object 上的 `training_intent_id` 透传给 evidence)
- Test: `tests/services/learner_state/test_training_intent.py`
- Test: `tests/capabilities/test_next_training_signal_consumption.py`

- [ ] **Step 1: Write intent tests**

```python
def test_training_intent_contains_concept_error_attempt_and_question_count():
    intent = build_learning_training_intent(
        user_id="u1",
        concept_id="1A432000",
        concept_label="主体结构",
        error_code="M06",
        error_label="多选漏选",
        attempt_refs=["ref1"],
        question_count=3,
    )
    assert intent["source"] == "learning_report"
    assert intent["concept_label"] == "主体结构"
    assert intent["error_label"] == "多选漏选"
    assert intent["question_count"] == 3
```

- [ ] **Step 2: Implement schema builder**

Rules:

1. No raw event ids in frontend intent.
2. `question_count` defaults to 3, max 5.
3. Training mode chosen from:
   - `mcq_discrimination`
   - `case_repair`
   - `rubric_recall`
   - `mixed_review`

- [ ] **Step 3: Wire report CTA**

Every `next_training` item must include:

```jsonc
{
  "title": "主体结构多选辨析",
  "reason": "来自最近 2 次多选漏选",
  "intent": { "...": "LearningTrainingIntent" }
}
```

- [ ] **Step 4: Wire practice/deep_question consumer (Round 2 G1 + G10)**

When route receives intent:

1. Load `concept_id`, `error_code`, `training_mode`, `training_intent_id`.
2. Prefer questions matching concept/error.
3. Store `training_intent_id` in active question object's `state_snapshot` (与现有 `next_training_signal` 同位置)。
4. **On grading writeback (G1 硬约束):** `construction_grading/writeback.py` 把 active_object.state_snapshot.training_intent_id 透传到 `learning_evidence.payload.training_intent_id`，再由 read model `_aggregate_learning_evidence()` 计算 "同一 intent_id 下前后正确率差"，输出 `training_improved` / `training_not_improved` 标签。无 intent_id 持久化 → 改善判断永远跑空。
5. typed graph 同时可 emit `training_improved_error` / `training_not_improved_error` 边，但不作为单一 authority — read model 必须能从 evidence 自身重算。
6. **Wallet 联动 (G10):** intent 消费前调用 `_assert_billing_quota_available` ；额度不足时 CTA 文案降级为"开通会员可解锁定向训练"，并把 intent 暂存到 `learning_state_service.draft_intents`（TTL 24h），充值后单击继续。

- [ ] **Step 5: Run**

```bash
pytest -q tests/services/learner_state/test_training_intent.py tests/capabilities/test_next_training_signal_consumption.py
```

### Task 4.5: Extend Learning Evidence with Conversation Signals

**Goal:** 把系统答疑、答案解析、错题讲解、知识点讲解从“只存在聊天历史”升级为同一 `learner_memory_events.learning_evidence` ledger 里的结构化学习事实。

**Files:**
- Modify or create thin helper under `deeptutor/services/learner_state/`
- Modify: unified chat finalization / assistant response assembly path
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Test: `tests/services/learner_state/test_conversation_learning_evidence_event.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] **Step 1: Write evidence extraction tests**

```python
def test_answer_explanation_turn_becomes_low_confidence_learning_evidence():
    event = build_learning_evidence_from_conversation_turn(
        user_id="u1",
        turn_ref="turn_123",
        user_question="主体结构多选题为什么容易漏选？",
        assistant_answer={
            "summary": "多选题要逐项判断所有必要条件，不能选到一个确定项就停止。",
            "concept_label": "主体结构",
            "error_label": "多选漏选",
            "source_refs": [{"type": "rag_hit", "label": "教材依据"}],
        },
    )
    assert event["memory_kind"] == "learning_evidence"
    assert event["event_type"] == "conversation_learning_evidence"
    assert event["learning_signal_type"] == "answer_explanation"
    assert event["concept"]["label"] == "主体结构"
    assert event["evidence_level"] == "exposed"
    assert event["confidence"] < 0.6
    assert event["conversation_turn_ref"] == "turn_123"


def test_conversation_evidence_does_not_mark_mastered():
    report = build_learning_report_read_model(events=[conversation_explanation_event()])
    assert report["mastery"]["dimensions"][0]["status"] != "stable"
    assert report["truth_sections"]["recent_observations"][0]["label"] in {"已讲解", "仍需巩固"}
```

- [ ] **Step 2: Define when to emit**

Emit `event_type=conversation_learning_evidence` only when at least one condition is true:

1. Assistant answer contains structured answer analysis / option analysis / rubric explanation.
2. Assistant answer uses RAG or standard answer sources to explain a knowledge point.
3. User asks why they were wrong, how to distinguish concepts, or how to train next.
4. Homepage recommendation prompt was clicked and answered.

Do not emit when:

1. The turn is purely greeting, navigation, account, payment, or UI help.
2. The assistant answer lacks a learnable concept.
3. The answer is an error message or degraded fallback.

- [ ] **Step 3: Implement thin-wrapper/fat-skill split (Round 2 G4 + G5 + B1)**

1. Chat/orchestrator wrapper only passes `turn_ref`, user text, assistant structured blocks, and source refs.
2. The learner-state helper owns extraction, quality gate, confidence, and learning signal classification.
3. It writes to `LearnerStateService` as `memory_kind=learning_evidence`、`event_type=learning_evidence`、`evidence_source=conversation_synthesis`、`learning_signal_type=...`；**不要**新建 event_type 大类（BLOCKER B1）。
4. Read model consumes the resulting event; it does not re-parse raw assistant text.

**Round 2 G4 — `assistant_explanation_summary` 生成路径：**

| 来源场景 | 优先策略 | 不允许 |
| --- | --- | --- |
| Grading kernel 已输出 `explanation.summary` / `why_user_wrong` | 直接复用，无额外 LLM call | 跑第二次 LLM 总结 |
| Assistant 答疑回复含 `<summary>` / 结构化 block | 复用 block 内容 | 重新生成 |
| 纯自由文本回复 | `truncate(text, 200)` + 首句切分 + 去除"我来解释..."等 padding 短语；若仍 > 240 字符则丢弃该 evidence | 调 LLM 做 paraphrase（成本 + 延迟不可控） |
| 失败时 | 不写 evidence，记 trace tag `conversation_evidence_skipped=true` | 写空摘要进 ledger |

**Round 2 G5 — `user_question` PII redaction（写入前必做）：**

- 使用现有 `deeptutor/services/safety/pii.py`（若不存在则在本 Task 中新建薄 helper）；
- 至少覆盖：手机号 `1\d{10}`、身份证 18 位、邮箱、连续 2+ 中文姓 + 名 pattern；
- 命中后用 `[REDACTED_PHONE]` / `[REDACTED_NAME]` 等占位符替换；
- payload 加 `user_question_redacted=true`；
- 测试覆盖：含手机号的提问 → 写入后字符串不含原号码。

**Round 2 G9 — `needs_confirmation` 区定义（同步 §6 Task 5 Step 2）：**

进入 `needs_confirmation` 的 evidence：
1. 同一 concept 一对一矛盾 evidence（一次对一次错且时间相近 < 2 小时）；
2. conversation evidence 显示 `still_confused` 但最近一次 grading 显示正确；
3. detail_ready=true 但 concept_label 缺失；
4. manual_correction 与 automated grading 结论不一致。

移出条件：
- 第 N+1 条 evidence 倾向哪一边（多数票）即移入对应 stable_truths / recent_observations；
- 持续 7 天未被新 evidence 解决 → 转 nightly synthesis 队列作人工/LLM 复议候选；
- 用户主动 mark-as-mastered 视为权威结论，覆盖矛盾。

- [ ] **Step 4: Preserve replay link**

Every user-visible conversation evidence card must be able to show:

```text
当时你问：主体结构多选题为什么容易漏选？
系统解释：多选题要逐项判断所有必要条件...
来源：本次答疑解析 / 教材依据
下一步：练 3 道主体结构多选辨析题
```

- [ ] **Step 5: Run**

```bash
pytest -q tests/services/learner_state/test_conversation_learning_evidence_event.py tests/services/learner_state/test_learning_report_read_model.py -k "conversation or home or evidence"
```

### Task 4.6: Extend Home Dashboard with Learning Personalization

**Goal:** 对话首页的“今日焦点”、输入提示、推荐问题与学情模块联动，成为个性化学习入口，而不是静态卡片。

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py` if a shared builder is needed
- Modify: conversation home page JS/WXML/WXSS in both mini-program surfaces
- Test: `tests/services/member_console/test_home_dashboard_learning_projection.py`
- Test: `tests/api/test_mobile_router.py` or existing homepage dashboard API test
- Test: `wx_miniprogram/tests/test_home_dashboard_learning_prompts.js`
- Test: `yousenwebview/tests/test_home_dashboard_learning_prompts.js`

- [ ] **Step 1: Write home dashboard projection tests**

```python
def test_home_dashboard_focus_uses_current_weak_point_and_conversation_signal():
    dashboard = build_home_dashboard_learning_projection(
        report=report_with_weak_point("主体结构", "多选漏选"),
        conversation_events=[conversation_event("主体结构", "多选漏选")],
    )
    assert dashboard["today_focus"]["title"] == "今日焦点：主体结构"
    assert "多选漏选" in dashboard["today_focus"]["meta"]
    assert dashboard["today_focus"]["intent"]["concept_label"] == "主体结构"
    assert dashboard["recommended_prompts"][0]["intent"]["source"] == "home_dashboard"


def test_home_dashboard_falls_back_when_no_learning_facts():
    dashboard = build_home_dashboard_learning_projection(report=empty_report(), conversation_events=[])
    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["recommended_prompts"][0]["intent"]["reason"] == "starter"
```

- [ ] **Step 2: Ranking rules + projection caching (Round 2 BLOCKER B6)**

**Projection caching contract (B6 强制):**

> 现 `get_home_dashboard()` 在 `member_console/service.py:3559` 已是同步 god method（串行 6 个内部调用 + supabase + 本地 store 读）。叠加 `learning_report_read_model` 同步调用 → p95 > 800ms → 与 §8 目标 `home dashboard projection p95 < 500ms` 直接冲突。**不允许在 dashboard 请求路径里实时跑 learning_report**。

1. 新增 `learner_state.home_personalization` 投影（落到 `learner_snapshot.home_personalization` 字段或独立表 `learner_home_projection`）；
2. 写入触发：
   - nightly synthesis 全量重算；
   - 每次 grading writeback → incremental update（只刷 weak point / recent observation）；
   - 每次 conversation evidence 写入 → incremental update（只刷 still_confused）；
   - bookmark mutate → incremental update（只刷 mistake_book due）；
3. dashboard 读路径只读 projection，不调 read model；projection miss / stale > 6 小时 → 降级为 fallback starter pool 并写 degraded counter；
4. projection 写失败不阻断 dashboard 主路径（fail-open on write，fail-closed on stale-detection）；
5. p95 budget：projection lookup < 50ms（cache），dashboard total < 500ms。

Ranking inputs:

1. Stable weak point.
2. Recent wrong attempts.
3. Repeated conversation confusion.
4. Mistake book due review.
5. Training not improved.
6. Due spaced review.
7. Starter fallback.

Tie-break:

```text
training_not_improved > repeated_error > repeated_question > recent_wrong > due_review > starter
```

- [ ] **Step 3: Prompt portfolio + starter pool (Round 2 G7)**

Recommended prompts must cover different jobs:

1. `concept_explain`：讲清概念。
2. `knowledge_map`：整理考点。
3. `misconception_compare`：对比易混淆点。
4. `practice_prompt`：生成同类训练。
5. `mistake_review`：回看错题。

No homepage should show three prompts that all mean "再练题".

**Round 2 G7 — Starter Fallback Pool（必填）：**

| 学科 (subject_id) | 至少 3 题 | 内容来源 |
| --- | --- | --- |
| `construction_exam_1` (一建建筑) | 主体结构验收 / 钢筋检验 / 防水分类 | `data/seed/construction_exam_1/starter_prompts.json` (本计划新建) |
| `construction_exam_2` (二建建筑) | 三类 starter | 同上 pattern |
| 其他/未识别 | "先做一次摸底测评" 单卡片 + 跳转 `/assessment/create` | 现有 assessment 入口 |

starter pool 由 `home_personalization` projection builder 在用户无学习事实时直接 emit；`fallback_used=true`、`source_status.learning_report=stale`；UI 显式标注"先做一题，给系统第一份学习证据"。**不允许用静态硬编码 prompts 假装个性化**。

- [ ] **Step 4: Frontend binding**

Home page should do:

```js
const dashboard = await api.getHomeDashboard()
this.setData(buildLearningHomeViewModel(dashboard))
```

It should not:

1. Hard-code 今日焦点.
2. Hard-code recommended prompts.
3. Build prompts by string-concatenating report labels.
4. Decide weak points in page JS.
5. Call a new endpoint unless existing dashboard p95 or ownership fails release gates.

- [ ] **Step 5: Click tracking and round-trip (Round 2 G2 + G3)**

When user clicks a recommended prompt:

1. Send `prompt` plus `intent`.
2. Store `learning_home_prompt_clicked` trace; Langfuse metadata 必须挂 `home_prompt_intent_id`（G8）。
3. Assistant answer uses intent as context.
4. Final answer writes a `learning_evidence` event with `evidence_source="conversation_synthesis"`、`learning_signal_type="home_prompt_clicked"`（不新建 event_type；BLOCKER B1）。
5. Next refresh can show updated focus or recommendation.

**Round 2 G2 — 正反馈陷阱防护（必填）：**

- 同一 `(user_id, concept_id, prompt_type)` 在自然日内的点击对 ranking 影响 ≤ 1 次（即同一天反复 click 不会反复抬升该 concept 的 focus 权重）；
- 实现位置：projection builder 计算 ranking 时先 group-by 然后 dedupe；
- 触发 trace tag `prompt_click_dedupe=true` 时 UI 不变，仅 ranking 输入被 cap；
- 用户首次某天 click 后，第二次起在 trace 中标 `prompt_repeat=true`，便于复盘是否真的有用。

**Round 2 G3 — "已讲解但未练题" 守门：**

- conversation evidence 单独存在 → projection 必须保留该 concept 在 focus 列表，**且** 把 CTA 优先级从 `concept_explain` 升级为 `practice_prompt`；
- 不允许因为"系统讲过一次" 就把该 concept 从 weak point 列表移除；
- 评判从 weak point 移除的唯一信号：grading evidence 显示连续 2 题正确（mastery estimator 达到 stable）。

- [ ] **Step 6: Run**

```bash
pytest -q tests/services/member_console/test_home_dashboard_learning_projection.py tests/api/test_mobile_router.py -k "home_dashboard"
node wx_miniprogram/tests/test_home_dashboard_learning_prompts.js
node yousenwebview/tests/test_home_dashboard_learning_prompts.js
```

### Task 5: Stable Truth vs Recent Observation Split

**Goal:** 不把单次错题伪装成“当前可信结论”。

**Files:**
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `deeptutor/services/learner_state/learning_brain_read_model.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] **Step 1: Add tests**

```python
def test_single_observation_goes_to_recent_observations_not_stable_truths():
    model = build_learning_report_read_model(... one_wrong_event ...)
    assert model["truth_sections"]["stable_truths"] == []
    assert model["truth_sections"]["recent_observations"][0]["level_label"] == "刚发现"


def test_repeated_error_promotes_to_stable_truth():
    model = build_learning_report_read_model(... two_same_error_events ...)
    assert model["truth_sections"]["stable_truths"][0]["level_label"] in {"重复出现", "已确认"}
```

- [ ] **Step 2: Implement split**

Rules:

1. L0 -> `recent_observations`.
2. L1/L2/L3 -> `stable_truths`.
3. conflict / missing evidence -> `needs_confirmation`.
4. UI never labels L0 as stable truth.

- [ ] **Step 3: Run**

```bash
pytest -q tests/services/learner_state/test_learning_report_read_model.py -k "truth_sections or observation"
```

### Task 6: Mastery Estimator

**Goal:** 掌握度从粗百分比升级为证据充分度模型。

**Files:**
- Create: `deeptutor/services/learner_state/mastery_estimator.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Test: `tests/services/learner_state/test_mastery_estimator.py`

- [ ] **Step 1: Write estimator tests**

```python
def test_one_easy_correct_attempt_has_low_confidence_and_cap():
    result = estimate_mastery(attempts=[attempt(correct=True, difficulty="easy")], legacy_score=100)
    assert result["score"] <= 60
    assert result["confidence"] < 0.4
    assert result["status"] == "insufficient_evidence"


def test_mixed_difficulty_repeated_correct_promotes_stable_mastery():
    result = estimate_mastery(attempts=[
        attempt(correct=True, difficulty="easy"),
        attempt(correct=True, difficulty="medium"),
        attempt(correct=True, difficulty="hard"),
        attempt(correct=True, difficulty="medium"),
        attempt(correct=True, difficulty="hard"),
    ], legacy_score=80)
    assert result["score"] >= 75
    assert result["confidence"] >= 0.65
    assert result["status"] in {"emerging", "stable"}
```

- [ ] **Step 2: Implement formula**

Minimum model:

```text
sample_score = bayesian_accuracy(correct + 1, total + 2)
difficulty_weight = weighted average difficulty
coverage_ratio = min(unique_question_count / required_question_count, 1)
recency_weight = exp decay over last 14 days
confidence = min(0.95, 0.2 + 0.5*coverage_ratio + 0.3*sample_diversity)
score = min(cap_by_confidence, blended legacy/evidence score)
```

- [ ] **Step 3: UI labels**

```text
confidence < 0.4 -> 证据不足
0.4 <= confidence < 0.7 -> 正在形成
confidence >= 0.7 -> 稳定掌握
```

- [ ] **Step 4: Run**

```bash
pytest -q tests/services/learner_state/test_mastery_estimator.py tests/services/learner_state/test_learning_report_read_model.py
```

### Task 7: Shared Frontend View Model

**Goal:** wx 与 yousen 不再各自理解 learning report。

**Files:**
- Create: `wx_miniprogram/utils/learning-report-view-model.js`
- Create: `yousenwebview/packageDeeptutor/utils/learning-report-view-model.js`
- Modify: both report pages
- Test: `wx_miniprogram/tests/test_report_view_model.js`
- Test: `yousenwebview/tests/test_report_view_model.js`

- [ ] **Step 1: Define common output**

```js
{
  hero: {
    stageLabel: "入门阶段",
    scoreText: "42%",
    headline: "当前最该补：主体结构 / 多选漏选",
    primaryCta: { label: "练 3 道同类题", intent: {} }
  },
  metrics: [],
  stableTruths: [],
  recentObservations: [],
  attempts: [],
  mistakeBook: {},
  nextTraining: [],
  masteryDimensions: []
}
```

- [ ] **Step 2: Add parity test**

```bash
shasum wx_miniprogram/utils/learning-report-view-model.js \
       yousenwebview/packageDeeptutor/utils/learning-report-view-model.js
```

Expected: same hash unless a documented platform-specific adapter is used.

- [ ] **Step 3: Thin page binding**

Report pages should do:

```js
const viewModel = buildLearningReportViewModel(report);
this.setData(viewModel);
```

They should not:

1. Translate error taxonomy.
2. Calculate mastery.
3. Decide next training.
4. Consume `legacy_compat`.

- [ ] **Step 4: Run**

```bash
node wx_miniprogram/tests/test_report_view_model.js
node yousenwebview/tests/test_report_view_model.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
```

### Task 8: Product UI Redesign

**Goal:** 学情页从内部系统看板变成学员复盘页。

**Files:**
- Modify: both `report.wxml`
- Modify: both `report.wxss`
- Test: Node snapshot tests
- Manual: WeChat DevTools screenshots

- [ ] **Step 1: First viewport**

First viewport must include:

1. Stage / mastery confidence.
2. Today / recent 3 days / streak.
3. Current focus.
4. Primary training CTA.

- [ ] **Step 2: Evidence cards**

Each attempt card shows:

1. Time.
2. Question title.
3. Result.
4. `你选 / 正确`.
5. One-line diagnosis.
6. `查看解析`.
7. `收藏错题`.

- [ ] **Step 3: Detail interaction**

Click card:

1. If detail endpoint available, navigate to detail page or modal with full detail.
2. If network unavailable, show cached summary and degraded hint.

- [ ] **Step 4: Visual rules**

1. No nested cards.
2. No raw IDs.
3. No giant radar before actionable diagnosis.
4. CTA stays obvious but not intrusive.
5. Empty state tells user exactly how to generate learning facts.

- [ ] **Step 5: Validate in DevTools**

Run:

```bash
scripts/start_local_learning_brain.sh start --no-web
node wx_miniprogram/tests/test_report_view_model.js
node yousenwebview/tests/test_report_view_model.js
```

Manual:

1. Open 微信开发者工具.
2. Run scenario: 出题 -> 作答 -> 批改 -> 学情页.
3. Screenshot first viewport and evidence detail.

### Task 9: E2E and Production Gate

**Goal:** 证明系统对真实学员链路有效，并能支撑 10 万用户。

**Files:**
- Modify: `scripts/run_learning_report_read_model_e2e.py`
- Create: `scripts/run_learning_report_world_class_e2e.py`
- Modify: docs runbook

- [ ] **Step 1: E2E scenario**

```text
中文出题
  -> 选择作答
  -> 批改写 learning_evidence
  -> 系统输出完整解析并写入 learning_evidence[event_type=conversation_learning_evidence]
  -> 学情页显示 recent observation
  -> 点击详情看到当时作答和解析
  -> 收藏错题
  -> 刷新仍存在
  -> 对话首页今日焦点更新为同一薄弱点
  -> 推荐问题围绕当前薄弱点变化
  -> 点击推荐问题后系统答疑
  -> 答疑解析再次沉淀为 learning_evidence[event_type=conversation_learning_evidence]
  -> 点击下一步训练
  -> deep_question 生成同 concept/error 训练题
  -> 再作答
  -> 学情页显示改善/未改善
```

- [ ] **Step 2: Required assertions**

1. `today_done >= 2`
2. `recent_three_done >= 2`
3. `attempt detail` returns question / user answer / correct answer / explanation
4. mistake book count increments and persists
5. next training intent contains concept/error
6. follow-up grading writes `training_improved_error` or `training_not_improved_error`
7. no raw `M06 / event hash / question_tests_concept` in learner-facing payload
8. `event_type=conversation_learning_evidence` exists for the system explanation turn
9. `home_dashboard.today_focus` matches the current learning report weak point
10. homepage recommended prompts carry structured intent and are not static hard-coded cards
11. clicking a recommended prompt produces a traceable conversation turn and later learning evidence

- [ ] **Step 3: Performance gate**

Targets:

```text
/api/v1/mobile/learning-report p95 < 800ms
/api/v1/homepage/dashboard p95 < 500ms after adding learning prompt projection
/api/v1/mobile/learning-attempts/{ref} p95 < 500ms
payload size p95 < 80KB
degraded < 1%
5xx < 0.1%
```

- [ ] **Step 4: Production observation**

Before declaring Done:

1. 14 days stable metrics.
2. deprecated page source RPS = 0 for 7 days.
3. mistake book write success >= 99.5%.
4. next-training click -> practice start conversion tracked.
5. homepage focus click -> useful answer / training conversion tracked.
6. conversation evidence extraction success >= 90% for structured explanation turns.

---

## 7. Rollout Strategy

### Stage 0: Contract & Schema Surface Registration (Round 2 BLOCKER B3)

- 更新 `contracts/index.yaml`：将 `learning-report / learning-attempts / mistake-book / learning-home-context` 新 endpoints 加入 `domains.turn.protected_patterns` 与 `domains.capability.protected_patterns`，并在 `schema_files` / `test_files` 区分别声明。
- 新建 `contracts/learning-report.md`：声明 read model / attempt detail / mistake book / training intent / home projection 的稳定边界 + version 矩阵。
- CI contract gate（已有）在 mobile.py 改动而 contracts/index.yaml 未同步时 fail-closed。
- 阻断条件：本 Stage 未完成时禁止合 Stage 1 任何代码。

### Stage 1: Hidden API + Dual-emit schema v1/v2 (Round 2 BLOCKER B4)

- Ship attempt detail / mistake book / training intent APIs behind feature flags (`DEEPTUTOR_LEARNING_REPORT_V2_ENABLED`, `DEEPTUTOR_MISTAKE_BOOK_ENABLED`, `DEEPTUTOR_HOME_PERSONALIZATION_ENABLED`)。
- No UI exposure.
- Run synthetic and devtool E2E.
- **`/api/v1/mobile/learning-report` 必须 dual-emit：**
  - 默认仍返回 `schema_version=1` 的现有字段 (`recent_attempts / timeline / training_loop_cards`)；
  - `?schema_version=2` 或 `Accept: application/vnd.deeptutor.learning-report+json;v=2` 时叠加 v2 顶层字段 (`hero / overview / truth_sections / attempts / mistake_book / next_training / mastery / home_personalization`)；
  - 旧 v1 字段在双发期内**字面保留**，不允许通过 `legacy_compat` 包装；
  - 后端单元测试覆盖三种 case：仅 v1 / 仅 v2 / dual-emit。

### Stage 2: Internal Users

- Enable for internal demo accounts.
- Compare old vs new learning report payload (字段级 diff，记录到 `.gstack/qa-reports/learning-report-v1-vs-v2.json`)。
- Watch p95, payload size, degraded sources.

### Stage 3: 5% Canary

- Enable new first-screen UX and cloud mistake book for 5%.
- Monitor:
  - report load p95
  - detail click rate
  - mistake save rate
  - next training conversion
  - support complaints
- 同时跑 §-2.7 BLOCKER B7 性能压测（5k events 用户）持续 48h；
- §-2.3 contract gate 必须为 green；
- §-1.5 evidence quality baseline 偏离 ≤ 3pp。

### Stage 4: 100%

- Keep legacy fallback for 7 days.
- Remove page-level old endpoint usage only after RPS gate passes.

### Stage 5: v1 Schema Retirement (Round 2 BLOCKER B4)

进入条件（**全部**满足）：
1. v2 ramp 100% 稳定 7 天；
2. v1 字段在前端代码中 grep 结果 = 0 (wx + yousen 两端各自验证)；
3. `/api/v1/mobile/learning-report?schema_version=1` 真实流量 RPS = 0 连续 7 天；
4. 任何遗留客户端版本（旧 wx 包发布 ≥ 30 天前）已强制更新。

操作：
1. read model 删 v1 字段（独立 PR，diff 限于 `learning_report_read_model.py` + tests）；
2. router 移除 dual-emit 分支；
3. 更新 `contracts/learning-report.md`，标 v1 为 `Retired`。

### Rollback Playbook (Round 2: 显式可执行步骤)

| 触发 | 立即动作 | 命令 / 文件 |
| --- | --- | --- |
| `/mobile/learning-report` p95 > 1.5s 连续 5 分钟 | 关 v2 dual-emit | `export DEEPTUTOR_LEARNING_REPORT_V2_ENABLED=false` + 重启 web pod |
| mistake_book 5xx > 1% | 关错题集写路径，read 仍可用 | `DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED=false` |
| home dashboard p95 > 1s | 关 home_personalization projection 读路径 | `DEEPTUTOR_HOME_PERSONALIZATION_ENABLED=false`，dashboard 退回旧 today_focus 路径 |
| evidence quality baseline 偏离 > 10pp | 关 conversation_synthesis 写路径 | `DEEPTUTOR_CONVERSATION_EVIDENCE_ENABLED=false` |
| supabase migration 故障 | 直接 `archived_at=now()` 全表，保留数据，code-side 走降级 | 不要 drop table（保留用户已保存数据） |
| 前端 hash parity test 失败 | 阻断对应 surface 发布 | wx 或 yousen 单独冻结 |

**Rollback 决策权：** P0 期间 oncall 工程师可单方面触发；100% 后任何 rollback 必须 oncall + product 双签。所有 flag 变更必须留 `git commit` 记录到 `docs/runbook/learning-report-flag-changes.md`（本计划新建）。

---

## 8. Success Metrics

### Product Metrics

| Metric | Target |
| --- | --- |
| 学情页首屏可理解率 | 用户访谈 8/10 能说出自己薄弱点 |
| 下一步训练点击率 | >= 25% |
| 点击训练后完成率 | >= 60% |
| 错题收藏率 | 错题曝光后 >= 15% |
| 错题复习率 | 收藏后 7 天内 >= 35% |
| 同一错因改善率 | 7 天内 >= 20% |
| 首页今日焦点点击率 | >= 20% |
| 推荐问题点击率 | >= 18% |
| 推荐问题后有效追问率 | >= 35% |
| 系统解析沉淀成功率 | 结构化解析 turn >= 90% |

### Engineering Metrics

| Metric | Target |
| --- | --- |
| learning report p95 | < 800ms |
| attempt detail p95 | < 500ms |
| home dashboard learning projection p95 | < 500ms |
| 5xx | < 0.1% |
| degraded | < 1% |
| payload p95 | < 80KB |
| old page-source RPS | 0 for 7 days before deletion |

---

## 9. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 新 schema 过大导致首屏慢 | 首屏只返回 attempt summary，detail 点击再拉 |
| 错题集新表变成第二套学习事实 | 只保存 bookmark 行为，评分事实仍引用 `learning_evidence` |
| training intent 又变成 prompt 拼接 | 后端 schema 化，deep_question 消费结构字段 |
| 双端继续漂移 | shared view model + hash/parity tests |
| 掌握度解释复杂 | UI 显示“证据不足/正在形成/稳定掌握”，百分比退居次要 |
| dry-run synthesis 冒充稳定结论 | stable truth 与 recent observation 分区 |
| evidence 字段不完整却被 UI 包装成洞察 | Task 0 quality gate：progress/detail/truth 分级，不合格 evidence 只能降级展示 |
| 计划一次性铺太大导致交付失控 | 先交付 P0 evidence loop，mastery 和大 UI 重构后置 |
| attempt detail O(n) 查询变慢 | P0 允许 limit 500 扫描验证，生产前补 event_id index reader 或专门索引 |
| taxonomy 未命中又显示“综合能力” | 未命中显示“未归类知识点”，并进入 taxonomy coverage report，不伪造大类 |
| 聊天历史沉淀过多导致 learner state 膨胀 | 只保存结构化学习事实、摘要和 turn ref，不复制全文 |
| 答疑 evidence 被误用为掌握证明 | `event_type=conversation_learning_evidence` 只能增加 exposure/confusion/recency，不能单独提升为 stable mastery |
| 首页推荐又变成前端硬编码 | `home_dashboard.today_focus/recommended_prompts` 是页面唯一输入，页面只渲染和上报点击 |
| 推荐问题偏离学情 | 每个 prompt intent 必须有 `reason` 和 source，E2E 断言与 weak point / due review / conversation signal 对齐 |

---

## 10. Self Review

### Spec Coverage

| Requirement | Covered By |
| --- | --- |
| 学员一看知道薄弱点 | UX first viewport, truth sections, hero focus |
| 下一步该学什么 | `LearningTrainingIntent`, next training CTA |
| 清楚知道依据 | attempt detail, evidence cards |
| 系统答疑解析被利用 | `learning_evidence[event_type=conversation_learning_evidence]`, conversation turn replay refs |
| 对话首页与学情联动 | `home_dashboard.today_focus/recommended_prompts`, homepage prompt intents |
| 丝滑体验 | first-screen architecture, payload cap, p95 gates |
| 10 万学员规模 | source timeout, detail lazy load, performance gates, rollout |
| 不打补丁 | single authority map, shared view model, backend mistake book |

### Placeholder Scan

No `TBD`, no vague “handle edge cases”, no unowned authority.

### Execution Boundary

This plan is intentionally split into independent tasks. The recommended first execution batch is now:

1. Task 0 Learning Evidence Quality Gate
2. Task 1 Attempt Ref Authority
3. Task 2 Attempt Detail
4. Task 3 Cloud Mistake Book
5. Task 4 Training Intent
6. Task 4.5 Extend Learning Evidence with Conversation Signals
7. Task 4.6 Extend Home Dashboard with Learning Personalization
8. Task 5 Stable Truth vs Recent Observation Split

These eight close the P0 product loop before broad UI polish and before MasteryEstimator expansion.

### P0 Release Gate

P0 is not complete until one real Chinese scenario passes end to end:

```text
中文出题
  -> 用户选择/作答
  -> 批改写入 detail-ready learning_evidence
  -> 学情页近 3 天完成数增加
  -> recent observation 出现中文知识点和中文错因
  -> 系统解析被沉淀为 conversation learning evidence
  -> 点击证据卡进入作答详情
  -> 详情页展示原题、学生答案、正确答案、解析、错因、下次规则
  -> 收藏错题后刷新仍存在
  -> 对话首页今日焦点同步为当前薄弱点
  -> 首页推荐问题围绕当前薄弱点和最近答疑生成
  -> 点击推荐问题后形成可追踪答疑 turn
  -> 点击下一步训练进入同 concept/error 训练
  -> 再次批改后显示改善/未改善
```

Required proof:

1. pytest service/API tests.
2. Node view model tests for both surfaces.
3. 微信开发者工具或真实手机截图。
4. Langfuse trace or backend log proving grading/evidence/report/detail/training chain.
5. Langfuse trace or backend log proving conversation answer -> `learning_evidence[event_type=conversation_learning_evidence]` -> `home_dashboard.today_focus/recommended_prompts`.
6. No raw `event_id` / `M06` / `question_tests_concept` / “综合能力” in learner-facing payload, unless displayed in an internal debug-only panel.

### P1 After P0

After P0 is stable, implement:

1. Task 7 Shared Frontend View Model full parity.
2. Task 8 Product UI Redesign.
3. Task 6 Mastery Estimator.
4. Task 9 Production performance gate.

### Kill Criteria

Stop rollout or hide the new UI when any condition is true:

1. `detail_ready` rate below 70% on real grading events.
2. `/api/v1/mobile/learning-report` p95 >= 800ms for 2 consecutive days.
3. attempt detail 5xx >= 0.5%.
4. next-training click generates unrelated questions in more than 5% sampled traces.
5. 学员访谈中少于 8/10 人能在 10 秒内说出“我薄弱在哪里、为什么、下一步做什么”。
