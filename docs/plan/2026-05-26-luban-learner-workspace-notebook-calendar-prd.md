# 鲁班学情工作台：个人笔记本 + 计划日历 + 学情看板 PRD

- 状态：Proposed v0.4
- 日期：2026-05-26
- 复审：2026-05-26，基于产品/CEO 视角、移动端交互视角、现有 learner-state/notebook 代码现实做可交付性加固
- 复审：2026-05-27，补入 GBrain / Obsidian Wiki 分层、Learning Brain 后续吸收项与 P0A 边界
- 归属主线：Learner State / Evidence-first Memory / 鲁班智考个性化教学
- 产品表面：鲁班智考微信小程序、佑森融合包、后续教师端
- 相关 contract：[contracts/learner-state.md](../../contracts/learner-state.md)、[docs/contracts/learning-state-inference.md](../contracts/learning-state-inference.md)
- 相关计划：[2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)、[2026-05-21-luban-learning-report-world-class-optimization-plan.md](2026-05-21-luban-learning-report-world-class-optimization-plan.md)、[2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md)、[2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](2026-05-23-luban-learning-history-evidence-closed-loop-plan.md)

## 1. 结论

鲁班智考不应该只做“AI 自动笔记”，也不应该做一个像 Notion 或 Obsidian 的通用笔记产品。

本 PRD 定义的产品是：

> 鲁班学情工作台 = AI 实务教练 + 个人笔记本 + 学习计划日历 + 学情看板。

AI 自动整理负责发现问题、归因、沉淀结构和推荐路径；学员手动收藏负责表达主观关注、掌控感和个人记忆；计划日历负责把笔记、错题和诊断转成每日、每周、每月行动；学情看板负责把“我现在怎么样、为什么这样、下一步做什么”展示清楚。

关键边界：

1. 手动笔记不是第二套 learner memory。
2. 用户说“我会了”不能直接改 mastery，只能触发复测或降低提醒。
3. 日历任务不是第二套 recommendation authority，推荐仍以 `training_intent` / learner-state projection 为准。
4. 任何“学员会什么、不会什么、后来有没有练会”的判断，仍必须回到 `learner_memory_events.memory_kind=learning_evidence` 及其 read model。
5. 手动笔记不仅不能写 `learning_evidence`，也不能通过 summary rewrite 或 recall 注入暗中污染学情判断。

## 1.1 v0.2 复审后的关键加强

v0.1 的方向成立，但 P0 仍然偏满。若同时做完整笔记、AI 待确认箱、今日计划、周/月计划、日历、看板、错因地图和训练转化，首版很容易变成“功能都有，但每个都不够闭环”。

v0.2 采用更稳的切法：

1. P0A 只打穿“保存 -> 复习/训练 -> 证据回流”最小闭环。
2. P0A 不做完整日历，只做“今日 3 任务条 + 即时训练动作”，不做持久化日程。
3. P0A 不做独立 AI 待确认笔记箱，只在答疑/批改后的价值发生点给 1 条高置信卡片；独立待确认箱推到 P0B。
4. P0A 不新增 planner recommendation authority，只把 `training_intent`、现有学情 read model 和已确认笔记的待行动投影组装成前端 view model。
5. P0A 的笔记保存优先复用现有 notebook 能力，但必须补齐 source ref、card type、user decision、evidence badge 等 metadata；若现有 notebook storage 无法满足生产 owner-scope / sync / audit，再进入专门 migration。
6. 用户手动收藏可作为“主观关注信号”，可以影响首页排序和提醒权重，但不能直接推导“掌握”。
7. “我已掌握”不是状态按钮，而是复测入口。复测通过后才能改变学情判断。

一句话：第一版不要证明鲁班能做一切学习管理，而要证明鲁班能把一次答疑/批改变成一次可追踪的下一步训练。

## 1.2 v0.3 代码实证复审修正

v0.3 接受代码实证评审的四个 blocker，并修改 P0A 边界：

1. 当前 notebook 写回不是轻路径。`NotebookManager._writeback_learner_state()` 会先写 `notebook_*` event，再调用 `LearnerStateService.refresh_from_turn()`；`refresh_from_turn()` 会 `record_turn_event()`、`_rewrite_summary()` 并触发 summary refresh。结论：`mastery_effect=none` metadata 挡不住 summary / recall 污染。
2. P0A 必须先把手动收藏改成轻路径：只写 notebook 用户资产和 `notebook_*` / candidate decision 事件，不触发 learner summary LLM 改写，不触发 compiled-truth refresh。需要进入 recall 时必须标注“学员自记/主观关注，不代表已掌握”，并降权。
3. 工作台首页不得新增 `GET /api/v1/learner-workspace/home`。P0A 必须扩展既有 `GET /api/v1/mobile/learning-report` read model，避免学情首页出现第二个 reader。
4. P0A 不做用户自建 planner task，不提供 planner CRUD。今日任务是只读 projection：来自 `training_intent`、learning-report read model、已确认笔记的待行动投影和系统提醒。`换一组`、`今天时间少` 只能做前端过滤/重排，不落库。用户创建任务、延期、完成状态进入 P0B 的 `planner_tasks`。
5. notebook 生产持久化不再是“后续不满足再说”。小程序 + 佑森 + Web 多端写入场景下，file-backed JSON 有 lost update 风险；P0A 上线前必须完成 durable notebook store 方案或明确只做单端内测，不得假装已满足生产。

## 1.3 v0.4 GBrain / Obsidian Wiki 分层修正

v0.4 明确：本工作台同时吸收 Obsidian Wiki 与 GBrain，但两者落在不同层，不能混成一套概念。

| 外部启发 | 在鲁班的产品层 | 在鲁班的系统层 | 边界 |
| --- | --- | --- | --- |
| Obsidian Wiki / LLM Wiki | 笔记、采分点手册、学员可控学习资产 | notebook card / AI candidate / source-linked markdown projection | 给学员掌控感；不作为掌握事实。 |
| GBrain / Learning Brain | 学情、今日任务、个性化答疑、教师提示的底层依据 | evidence ledger、compiled truth、typed graph、brain-first lookup、nightly lint、eval | 给系统理解力；不新增第二套 learner-state / RAG / 聊天入口。 |

因此 P0A 的职责仍然是“用户可控笔记 + 下一步行动”的最小闭环；GBrain 后续增强进入 P0B/P1/P2，作为 Learning Brain 的能力加固，而不是把 P0A 做成复杂学习大脑。

后续要吸收的 GBrain 能力：

1. **Brain-first lookup**：对话、今日任务和学情卡片生成前，优先读取当前学员的 compiled truth、近期 evidence、stale / superseded claim 和 next_training；但只能作为个性化上下文，不能盖过题库、规范、教材和标准答案。
2. **Claim lifecycle**：学习判断不再只有“会/不会”，而要分为 `L0_observed`、`L1_repeated`、`L2_confirmed`、`stale`、`superseded`、`rejected`，并在 UI 中翻译成用户能理解的“观察 / 反复出现 / 已复测确认 / 待复测”。
3. **Typed graph 驱动训练**：用结构化关系连接“学员 -> 知识点 -> 采分点 -> 错因 -> 证据事件 -> 推荐训练 -> 复测结果”，让错因地图、今日任务、AI 互动课堂、笔记转训练共用同一条事实链。
4. **Nightly lint / dream cycle**：夜间检查无证据画像、冲突判断、长期未复测错因、已改善但仍提醒的 stale claim、用户高频收藏但系统未识别的主观关注。
5. **Provenance-aware retrieval**：个性化答疑必须说明“为什么给这个建议”，并能点回 source event / attempt detail；compiled truth 可以参与召回，但不能超过 exact question、规范、教材 authority。
6. **Eval harness**：补 `profile_claim_precision`、`hallucinated_profile_claim_rate`、`stale_claim_rate`、`brain_first_lookup_hit_rate`、`provenance_trace_coverage`、`retest_improvement_rate` 等指标，防止学习大脑自嗨。

这六件事只增强 Learning Brain 主线，不新增 `gbrain` 运行时、不新增第二套 memory DB、不新增第二套 RAG provider、不新增独立“GBrain”小程序入口。

## 2. Karpathy Gate

### assumptions

本 PRD 采用以下需求解释：

- 用户希望学员拥有自己的“笔记本”和“计划表”，获得掌控感。
- 用户也认可 AI 自动学习档案的价值，但担心纯自动化会让学员不信任、不参与。
- 本次要写产品 PRD，不直接落代码；但 PRD 必须给出可执行 P0、数据边界、交互闭环和验收标准。
- 当前代码已证实 notebook 写回会触发 summary rewrite；P0A 实施前必须先收权写回路径。

仍需后续验证的点：

- 微信小程序当前导航是否能容纳“今日/学情/笔记”入口，还是先嵌入现有学情页。
- notebook 当前 file-backed JSON 适合本地/单端验证，不足以默认承载生产多端并发收藏；P0A 需要 durable store gate。
- `learning_plans` 更像 Guided Learning plan/page 产物，不天然等于日历任务；P0A 不复用它做 planner CRUD。
- `synthesize_learning_truth` 当前严格过滤 `memory_kind="learning_evidence"`，不直接吃 notebook event；但 summary / recall 是更早的污染边界，必须单独收权。

### simplest path

P0A 不做完整日历、不做复杂图谱、不做通用笔记编辑器。

最短路径是：

1. 在 AI 答疑、题目解析、案例批改、作答复盘底部加入轻量操作：收藏、加入采分点、马上训练、生成同类题。
2. 把用户收藏内容转成“智能学习卡片”：原文 + AI 整理 + 知识点 + 错因 + 下一步动作。
3. 答疑/批改完成后只弹 1 条高置信“建议保存”卡片；批量 AI 待确认箱推迟到 P0B。
4. 首页展示最多 3 个“今日最该做”的任务，任务来自 `training_intent`、错因、笔记待行动投影和系统提醒；P0A 不支持用户自建任务。
5. 学情看板只展示今日任务、当前状态、错因/采分点资产和计划进度，不在 P0A 展示复杂知识图谱。

### change boundary

本 PRD 只定义产品和架构边界，后续实施不得顺手改动：

- 统一聊天入口 `/api/v1/ws`。
- `learner_memory_events` 的 canonical authority。
- `training_intent` 作为处方推荐 authority。
- `study_plan` 只读/呈现 canonical 处方的 contract。
- `GET /api/v1/mobile/learning-report` 作为学情首页/工作台 read model 的唯一扩展点。
- notebook 手动收藏写回必须从 summary LLM rewrite / compiled-truth refresh 重路径中收权。
- assessment、grading、RAG、TutorBot 的既有责任边界。

### verification target

P0A 完成标准不是“能写笔记”，而是：

- 学员在一次答疑或批改后，可以一键把关键内容保存成个人学习卡片。
- 学员能从卡片直接进入今日复习或同类题训练；P0A 不承诺持久化日程。
- 系统能解释推荐原因，且原因可点回证据。
- 用户修改、拒绝或收藏 AI 建议，不会篡改 learner-state truth。
- “我已掌握”必须触发复测，不直接写 mastery。
- 新用户没有历史证据时，能看到 starter 任务和手动收藏入口；老用户有证据时，能看到“为什么推荐”。

## 3. 产品目标

### 用户价值

学员打开鲁班时，不只是问问题、看答案，而是进入自己的实务备考工作台：

- 今天该做什么。
- 为什么应该做这件事。
- 哪些点是自己主动收藏的。
- 哪些点是鲁班从错题和对话里发现的。
- 哪些错因反复出现。
- 哪些采分点值得复习。
- 本周、本月目标推进到哪里。

### 商业价值

对学员：

- 从“AI 答疑工具”升级为“我自己的实务备考系统”。
- 手动笔记增强掌控感，AI 整理降低整理成本，计划日历提升行动转化。

对机构：

- 老师不只看到做题数，而能看到学员主观关注、真实薄弱点、错因复发和干预建议。
- 学情看板成为续费、服务交付和教学质量证明的核心资产。

## 4. 非目标

P0A 不做以下事情：

- 不做通用 Obsidian / Notion 替代品。
- 不做复杂文件夹、双链编辑器、Markdown 编辑器或自由排版系统。
- 不把手动笔记作为 mastery truth。
- 不让前端推断掌握度、错因或推荐。
- 不新增聊天 WebSocket。
- 不新增第二套 learner memory 表或 recommendation authority。
- 不做外部 Google/Apple/微信系统日历同步。
- 不在首屏展示全量知识图谱。

## 5. 单一 Authority

| 业务事实 | 唯一 authority | 本 PRD 的处理 |
| --- | --- | --- |
| 学员做过什么、错过什么、系统讲过什么 | `learner_memory_events.memory_kind=learning_evidence` | 只引用，不复制成第二套 truth。 |
| 学员当前掌握、薄弱、趋势 | `learning_synthesis` / learner-state read model | 笔记和看板只展示 projection，不自行推断。 |
| 学习事实 claim 生命周期 | `learning_synthesis` / `summary_structured_json.learning_brain` | 工作台只展示 `L0/L1/L2/stale/superseded/rejected` projection，不让笔记直接改 claim。 |
| 下一步训练处方 | `training_intent` | 日历和今日任务可呈现、排程、完成反馈，但不另算处方。 |
| 学情首页 / 工作台 view model | `GET /api/v1/mobile/learning-report` / `learning_report_read_model` | P0A 只扩展既有 read model，不新增 `learner-workspace/home`。 |
| learner summary / recall context | `LearnerStateService` summary / context candidates | 手动笔记不得触发 summary LLM 改写；进入 recall 必须带“学员自记/主观关注”来源标签并降权。 |
| 个性化召回 / brain-first lookup | `RAGService` + runtime learner context + compiled truth projection | 只作为 source-aware context / source group，不覆盖 exact question、标准、教材事实。 |
| 学员长期目标 | `user_goals` | 月目标/阶段目标应读取或写入既有 goals authority。 |
| 用户手动收藏、手动笔记 | Notebook 用户资产服务 | 代表主观关注和复习资产，不代表掌握事实。 |
| 用户手动计划 | P0B `planner_tasks`，P0A 不做 | P0A 只有只读今日任务 projection；用户自建任务推迟到 P0B。 |
| AI 自动建议保存的笔记 | AI note candidate projection | 进入待确认区；确认后成为用户笔记，拒绝后不影响 evidence。 |

### 禁止模式

- `manual_note -> mastery++`
- `calendar_completed -> mastered`
- `ai_note_candidate -> notebook` 自动强写，无用户确认
- `frontend_tag -> learning_evidence`
- `study_plan` 在 `training_intent` 之外另算推荐
- `notebook_add -> refresh_from_turn -> _rewrite_summary`
- `notebook_* -> compiled_learning_truth`
- `notebook_card -> compiled_truth` 无 evidence 直接升格
- `compiled_truth -> exact_question / standard / textbook authority` 覆盖
- 新增独立 `gbrain` 入口、第二套 RAG 或第二套 learner memory
- `GET /api/v1/learner-workspace/home` 与 `/api/v1/mobile/learning-report` 并行服务同一首页
- P0A 新增 `planner/tasks` CRUD 或把 `learning_plans` 改造成日历任务
- 因为笔记功能新增 `/api/v1/mobile/tutorbot/ws/...`

### 允许模式

- `manual_note -> subjective_focus_signal`
- `manual_note + evidence -> dashboard badge`
- `manual_note -> notebook_* event only`
- `manual_note -> recall_candidate(source_label="student_note", weight=low)`
- `user_says_mastered -> diagnostic_probe`
- `task_completed -> learning_behavior_event`
- `task_completed + retest_result -> learning_evidence`
- `ai_note_candidate accepted -> notebook_card`
- `learning_evidence -> claim lifecycle -> learning-report projection`
- `compiled_learning_truth -> RAG context(source_group)`，并在 provenance 中保留 `supporting_event_ids`
- `typed_graph -> next_training explanation`，题目选择仍由题库 / 出题 authority 完成

## 6. 核心信息架构

微信小程序主框架收敛为 5 个底部 Tab：`学习 / 笔记 / 对话 / 学情 / 我的`。中间 `对话` 是圆形放大的 AI 主入口；`今日` 不再作为独立 Tab，而是放入 `学习` 的首屏处方和计划日历。

| Tab | P0A 展示 | 后续扩展 | 边界 |
| --- | --- | --- | --- |
| 学习 | 今日 3 任务、继续学习、待复习、摸底测试/专项练题入口 | 计划日历、AI 互动课堂、周/月目标、时间压缩模式 | 行动调度入口，不另算 recommendation。 |
| 笔记 | 手动笔记、AI 推荐笔记、采分点卡片 | AI 待确认箱、笔记转训练、导出 | 学员 100% 可控资产，不作为 mastery truth。 |
| 对话 | 问鲁班、拍照识题、案例批改、历史聊天 | 对话后学习档案更新卡、课堂内追问 | 统一 `/api/v1/ws`，不新增聊天路由。 |
| 学情 | 当前状态、测试报告、错因地图、能力图谱、我的成就 | 主观关注 vs 教师关注、证据链、周报/月报 | 只读 learner-state / learning-report projection。 |
| 我的 | 充值、会员、余额、学习设置、反馈、账号 | 教师共享权限、隐私授权、导出管理 | 账户与权益，不承载学习事实判断。 |

P0A 仍可把“今日建议”放在 `学习` 首屏或学情页顶部做灰度，但产品命名上不再把“今日”设为一级 Tab，避免学习、学情、笔记三者边界继续交错。

## 7. 关键体验原则

### 用户主控，AI 副驾

学员只负责学习、作答、收藏、确认和调整计划。AI 负责观察、归因、整理、提醒和推荐。

产品语言要避免：

- “请整理笔记”
- “请维护知识库”
- “请填写标签”

推荐语言：

- “已帮你整理成学习卡片”
- “这条要加入今日复习吗”
- “这是你第 3 次漏写责任主体，建议马上练一道同类题”
- “你觉得这个判断不准确，可以测一下”

### 每次沉淀都能转行动

每条笔记、错因、采分点都必须至少能做一件事：

- 加入今日复习。
- 进入今日任务候选。
- P0B 后加入本周计划。
- 生成同类题。
- 生成案例短答。
- 做复述训练。
- 触发复测。

否则它只是收藏夹，不是学习系统。

### 先判断，再证据，再行动

所有学情反馈采用三段式：

1. 判断：你当前最该处理什么。
2. 证据：为什么这样判断，来自哪次答题/对话/批改。
3. 行动：现在做哪 1-3 件事。

### 移动端控制复杂度

- 今日任务最多 3 个。
- 每个任务只有 1 个主按钮。
- 次级操作收进更多菜单。
- 按钮触控区域不小于 44x44。
- 复杂证据、历史时间线、图谱默认折叠。
- 同一屏不同时展示笔记树、日历、图谱和长报告。

## 7.1 真实使用场景矩阵

| 场景 | 学员状态 | 鲁班应该做 | 不应该做 |
| --- | --- | --- | --- |
| 碎片时间 5 分钟 | 通勤、午休，只想快点做完 | 首页只给 1 个可完成任务，如复习一张采分点卡或做 1 道短题 | 展示周报、长图谱、复杂日历 |
| 晚上深度学习 30 分钟 | 有时间做题和复盘 | 先做推荐题，再复盘错因，再保存 1 条采分点 | 一上来让用户整理笔记树 |
| 刚被案例题打击 | 分数低，情绪挫败 | 先指出“不是完全不会”，再列 1-2 个可补采分点，并给改写入口 | 泛泛鼓励或继续推大量新题 |
| 考前 7 天冲刺 | 时间紧，关注提分 | 优先错因复发、采分点模板、短复测；弱化探索式学习 | 推荐长周期课程和大章节学习 |
| 新用户无证据 | 还没做题，系统不了解 | 展示 starter 任务、手动收藏入口、首个诊断任务 | 装作已经知道薄弱点 |
| 老用户回流 | 有历史证据但间隔久 | 先展示“上次停在这里”和 1 个恢复任务；过期判断标为待复测 | 直接沿用旧 mastery 当最新状态 |
| 用户主动想记笔记 | 对某句话有主观价值 | 一键保存原文，并自动补知识点/采分点/复习动作 | 强迫用户选标签、填分类 |
| 用户不认同系统判断 | 觉得“我其实会” | 给“测一下”作为事实校验入口 | 让用户一键把 weak point 改成 mastered |
| 老师课后辅导 | 老师想知道怎么干预 | 提供聚合证据、错因复发、下一步训练建议 | 默认暴露完整聊天原文 |
| 无网络/弱网 | 小程序加载慢 | 保留最近任务和笔记只读缓存，写操作 pending | 让用户以为保存成功但后台丢失 |

## 7.2 状态机

学习资产必须按状态流转，避免 AI 自动内容和用户确认内容混在一起：

```text
source content
  -> card_draft
  -> user_confirmed | user_edited | user_rejected | dismissed_later
  -> scheduled_for_review
  -> trained_or_retested
  -> evidence_updated
```

关键规则：

- `card_draft` 只能作为建议，不进入“我的笔记本”默认列表。
- `user_confirmed` / `user_edited` 才算用户资产。
- `user_rejected` 不能删除原始 evidence，只能降低同类建议频率。
- `scheduled_for_review` 是计划状态，不是掌握状态。
- `trained_or_retested` 只有经过作答/批改/复测，才能进入 `learning_evidence`。
- 删除笔记只删除用户资产或隐藏关联，不删除原始学习证据。

## 8. P0A 用户流程

### Flow A：答疑后收藏成笔记

1. 学员向鲁班提问。
2. AI 正常回答。
3. 回答底部显示轻量操作：
   - 收藏到笔记
   - 加入采分点
   - 设为复习
   - 生成同类题
4. 学员点“收藏到笔记”。
5. 系统生成智能学习卡片：
   - 原始收藏内容
   - 鲁班整理
   - 关联知识点
   - 关联错因
   - 考试采分表达
   - 建议复习时间
6. 学员可选择：
   - 保存
   - 修改后保存
   - 马上练一道
   - 设为重点，进入今日任务候选
   - 生成一道题

验收重点：保存笔记不得直接改变 mastery。

### Flow B：案例批改后进入错因和采分点

1. 学员提交案例题答案。
2. 系统给出得分、漏分点、标准表达。
3. 批改底部显示：
   - 加入错因地图
   - 加入采分点手册
   - 重新作答
   - 练同类题
4. 用户选择“加入采分点手册”。
5. 系统生成个人采分点卡片：
   - 本题可得分表达
   - 用户原答案差距
   - 关联错因
   - 下次作答模板
6. 用户选择“重新作答”或“练同类题”后，进入训练闭环。

验收重点：错因判断必须能点回 `learning_evidence` 或 attempt detail。

### Flow C：AI 待确认笔记箱（P0B）

1. 每日或每次学习结束后，系统展示“鲁班今天为你整理了 3 条学习记录”。
2. 每条候选内容显示：
   - 建议标题
   - 为什么值得保存
   - 来源证据
   - 建议动作
3. 学员可选择：
   - 保存
   - 修改后保存
   - 不准确
   - 以后再说
4. “不准确”不删除原始 evidence，只标记 AI candidate 被拒绝。

验收重点：AI 自动建议默认进入待确认区，不强制写入用户笔记本。

### Flow D：今日任务条

1. 学员打开鲁班。
2. 首屏展示“今天最建议你做 3 件事”：
   - 复习一条笔记
   - 改写一道错题
   - 做一道同类案例题
3. 每个任务显示原因：
   - AI 推荐
   - 笔记待行动
   - 系统提醒
4. 学员可点击：
   - 开始
   - 查看原因
   - 今天时间少，压缩计划
   - 换一组任务
5. P0A 的“今天时间少 / 换一组”只做前端过滤或重排，不落库；完成状态只有在引导到作答、复测、批改后，才通过既有 evidence writer 形成事实。

验收重点：任务完成不是掌握，只是行为；掌握变化必须由复测证据确认。

### Flow E：用户反驳系统判断

1. 系统提示：“根据最近 2 次作答，你在专项施工方案审批流程上表达不稳定。”
2. 学员点击“我其实会”。
3. 系统不直接改 mastery，而是出现：
   - 给我测一下
   - 暂时不提醒
   - 查看判断依据
4. 学员选择“给我测一下”后，生成诊断题。
5. 诊断结果写入 canonical evidence，再刷新学情判断。

验收重点：“我其实会”是复测入口，不是事实写入入口。

## 9. 页面原型要求

### 9.1 学情工作台首页

首屏顺序：

1. 今日建议
2. 当前最该处理的问题
3. 本周目标进度
4. 高频错因
5. 笔记资产

示例文案：

```text
今天最建议你做 3 件事

1. 练 1 道质量问题处理案例题
原因：你最近 3 次都漏写“复查验收”。

2. 复习专项施工方案审批流程
原因：这是高频考点，你上次表达不完整。

3. 整理 1 条个人采分点笔记
原因：你已经理解知识点，但答题语言还不够像标准答案。
```

### 9.2 笔记详情页

每条笔记必须展示来源和可行动作：

```text
笔记：质量问题处理类案例题表达

来源
- 你在 5 月 23 日手动收藏
- 鲁班在 5 月 25 日根据错题自动补充

我的原文
质量问题要写整改和预防。

鲁班整理
案例题不能只写整改，还要写：原因分析、处理措施、复查验收、预防措施。

个人采分点模板
发现问题 -> 分析原因 -> 制定处理方案 -> 整改处理 -> 复查验收 -> 形成记录 -> 预防再发生

下一步
[加入今日复习] [生成同类题] [我已掌握，测一下]
```

### 9.3 简版计划页

P0A 不做独立计划页，只在首页/学情页顶部显示“今日任务条”。P0B 再做简版计划列表，不做完整日历网格：

- 今天
- 本周
- 本月
- 待复习
- 已完成

每个任务卡片字段：

- 标题
- 类型：复习 / 练习 / 改写 / 复测 / 整理
- 来源：AI 推荐 / 笔记待行动 / 系统提醒；`我创建` 和 `老师布置` 推迟到 P0B/P1
- 原因
- 预计时间
- 主按钮

### 9.4 主观关注 vs AI 教练关注

P1 进入学情看板：

```text
你最近主动关注
1. 怎么快速背施工流程
2. 怎么记住模板
3. 哪些知识点会考

鲁班建议你更优先关注
1. 案例题采分点表达
2. 责任主体和验收记录
3. 质量问题处理的答题结构

原因
你最近不是知识点完全不会，而是答案不够像标准答案。

[接受建议，加入本周计划] [我还是想先学我关注的] [生成对比说明]
```

## 10. 功能需求

### P0A：必须先交付的最小闭环

P0A 的目标是证明“学完一次，系统能把关键内容变成下一次行动”，不是证明完整学习管理平台。

P0A 有两个工程前置阻断：

1. notebook 手动收藏写回必须切到轻路径，不再触发 `refresh_from_turn()` 的 summary LLM 改写和 compiled-truth refresh。
2. notebook 卡片必须有 durable store 或明确的单端内测边界；面向小程序 + 佑森 + Web 的真实多端场景时，不能依赖 file-backed JSON records 数组承诺不丢写。

| 编号 | 功能 | 说明 | 验收 |
| --- | --- | --- | --- |
| P0A-1 | 来源绑定的一键收藏 | AI 回答、题目解析、案例批改、作答复盘可收藏 | 收藏后生成 notebook record/card，metadata 保留 `source_ref`、`card_type`、`source_type`、`evidence_event_ids`。 |
| P0A-2 | 智能学习卡片 | 用户保存后自动补“鲁班整理、采分点表达、关联错因、下一步动作” | 用户可保存、编辑、删除；保存不写 `learning_evidence`，不改 mastery。 |
| P0A-3 | 价值发生点建议保存 | 答疑/批改结束后只展示 1 条高置信建议卡片 | 默认不入库；用户确认后才进入笔记本。 |
| P0A-4 | 今日 3 任务条 | 首页或学情页顶部展示最多 3 个任务 | 每个任务有来源、原因、动作、预计时间；来源只允许 AI 推荐、笔记待行动、系统提醒。 |
| P0A-5 | 笔记转训练 | 笔记可生成同类题、改写或复测 | 训练结果经既有 grading/evidence 链路回写。 |
| P0A-6 | 证据抽屉 | 诊断类卡片可展开证据 | 无证据时只能显示“待确认观察”，不能显示稳定结论。 |
| P0A-7 | 用户纠偏入口 | 支持“不准确/我其实会/不再提醒/测一下” | “我其实会”触发 probe，不直接更新 mastery。 |

### P0B：第一版可用后的增强

| 编号 | 功能 | 说明 | 进入条件 |
| --- | --- | --- | --- |
| P0B-1 | AI 待确认笔记箱 | 聚合每日/本周 AI 候选笔记 | P0A 的 inline 建议接受率达标，且确认疲劳可控。 |
| P0B-2 | 简版计划列表 | 今天/本周/本月/待复习/已完成 | P0A 今日任务完成率达标。 |
| P0B-3 | 采分点手册入口 | 按题型/错因聚合个人采分点 | 至少有 5 条用户确认或批改来源卡片。 |
| P0B-4 | 错因地图入口 | 高频错因、复发次数、最近证据 | 错因 evidence coverage 达标。 |
| P0B-5 | 周复盘 | 本周进步、反复错因、下周建议 | 有足够一周行为数据。 |
| P0B-6 | claim lifecycle 可见标签 | 把 `L0/L1/L2/stale` 翻译成“待确认观察 / 反复出现 / 已复测确认 / 待复测” | `learning_synthesis` 已稳定输出 claim lifecycle projection。 |

### P1：增强个性化

- 周计划、月目标和阶段目标。
- 主观关注 vs AI/教师关注差异卡。
- 个人采分点手册独立入口。
- 错因地图与笔记互链。
- brain-first lookup：对话、今日任务、错因解释先读 compiled truth / recent evidence / next_training。
- 局部 typed graph 链路：只展示“错因 -> 漏分采分点 -> 训练 -> 复测结果”，不展示大而全图谱。
- provenance 抽屉：解释“为什么这样推荐”，并展示 supporting event ids / attempt detail。
- nightly lint dry-run：检查 stale claim、冲突画像、无证据结论、长期未复测错因。
- 教师端提示卡：本周干预建议、证据和建议动作。
- 计划完成后的周报/月报。
- 局部能力链路图，而不是全量知识大网图。

### P2：规模化和协同

- 拖拽式日历排程。
- 外部日历同步。
- 班级/机构维度共性错因看板。
- 教师批量布置计划。
- 笔记/采分点导出。
- 自适应复习频率和间隔复习策略。
- Learning Brain eval harness：画像准确率、无证据画像率、过期画像率、个性化召回命中率、复测改善率。
- maintenance workflow：nightly lint 从 dry-run 进入可回滚修复，输出审计报告。

## 11. 数据模型草案

本节是产品数据草案，不代表必须新增所有表。实施前必须先复核现有 notebook、learning plan、learner-state schema，能复用则复用。

### 11.0 当前代码现实与落地约束

当前仓库已经有可复用基础，但还不能直接等同于本 PRD 的完整产品模型：

1. `deeptutor/services/notebook/service.py` 已有 owner-scoped notebook JSON 存储、record 增删改查和 learner-state writeback，但当前是 file-backed JSON，不足以默认承诺生产多端并发可靠。
2. notebook writeback 当前会写 `notebook_add` / `notebook_update` 等 memory event，并继续调用 `refresh_from_turn` 更新 summary。这是 v0.3 明确要修的 blocker：手动收藏不能走 summary LLM rewrite / compiled-truth refresh 重路径。
3. `RecordType` 当前是通用枚举：`solve`、`question`、`research`、`co_writer`、`chat`、`guided_learning`。P0A 不应为了卡片类型先扩大枚举；更稳的做法是在 `metadata.card_type` 表达 `scoring_card` / `error_pattern_note` / `review_note`。
4. `learning_plans` / `learning_plan_pages` 当前更偏 Guided Learning plan/page，不是通用日历任务。P0A 不应直接把它改成 calendar；P0A 不做用户自建任务 store，P0B 再决定是否新增正式 `planner_tasks`。
5. `study_plan` 当前应继续读取 `training_intent`，不得因为“今日计划”引入第二套 recommendation writer。
6. 若面向生产端多端同步、RLS、教师共享和审计，durable notebook store 是 P0A UI 上线前置阻断；若暂不做 store，只能标为单端/内测实验，不能声称生产可用。

### 11.0.1 metadata 最小扩展

P0A 优先在 notebook record `metadata` 中补齐以下字段，而不是新增大表：

```json
{
  "card_type": "scoring_card",
  "source_type": "grading",
  "source_ref": {
    "kind": "learning_evidence",
    "event_id": "evt_001",
    "attempt_ref": "attempt_001"
  },
  "evidence_event_ids": ["evt_001"],
  "linked_knowledge_points": ["混凝土质量控制"],
  "linked_error_patterns": ["missing_responsible_subject"],
  "user_decision": "confirmed",
  "personalization_weight": "subjective_focus",
  "mastery_effect": "none"
}
```

其中 `mastery_effect` 在 P0A 必须固定为 `none`，但它不是安全边界。真正的安全边界是：保存笔记的 writer 不得调用 `refresh_from_turn()`，recall 注入必须带 `source_label="student_note"` 并降权，learning synthesis 仍只读取 `learning_evidence`。

### notebook_card

```json
{
  "note_id": "note_001",
  "user_id": "user_001",
  "subject_id": "construction_practice",
  "source_type": "manual",
  "source_ref": {
    "kind": "conversation_turn",
    "event_id": "turn_20260526_001"
  },
  "title": "专项施工方案审批流程",
  "raw_user_content": "这个流程我总是记不住，先收藏。",
  "ai_enhanced_content": {
    "summary": "该知识点属于安全管理高频考点。",
    "scoring_expression": "编制 -> 审核 -> 审批 -> 论证 -> 交底 -> 验收",
    "linked_knowledge_points": ["危大工程", "专项施工方案"],
    "linked_error_patterns": ["审批主体混淆"]
  },
  "user_control_status": "confirmed",
  "use_for_personalization": true,
  "created_at": "2026-05-26T10:00:00+08:00",
  "updated_at": "2026-05-26T10:00:00+08:00"
}
```

`source_type` 允许值：

- `manual`
- `ai_suggested`
- `ai_confirmed`
- `grading`
- `conversation_synthesis`
- `teacher_assigned`

### ai_note_candidate

```json
{
  "candidate_id": "cand_001",
  "user_id": "user_001",
  "title": "案例题容易漏写责任主体",
  "reason": "近 3 次案例题中有 2 次漏写责任主体。",
  "evidence_event_ids": ["evt_001", "evt_002"],
  "suggested_note_type": "error_pattern",
  "status": "pending",
  "created_at": "2026-05-26T10:05:00+08:00"
}
```

状态：

- `pending`
- `accepted`
- `edited_and_accepted`
- `rejected_inaccurate`
- `dismissed_later`

### planner_task（P0B，不属于 P0A）

```json
{
  "task_id": "task_001",
  "user_id": "user_001",
  "title": "复习专项施工方案审批流程",
  "task_type": "review",
  "source_type": "ai_recommendation",
  "source_ref": {
    "kind": "training_intent",
    "id": "intent_001"
  },
  "why": "这是高频考点，你上次表达不完整。",
  "scheduled_for": "2026-05-26",
  "estimated_minutes": 8,
  "status": "scheduled",
  "completion_result": null,
  "writes_learning_evidence": false
}
```

`planner_task` 只有进入 P0B 且确认需要用户自建/延期/完成任务时才建立。P0A 的今日任务条不是 planner store，只是 `learning_report_read_model` 的 projection；`writes_learning_evidence=false` 是默认值。只有当任务引导到作答、复测、批改等已有 evidence writer 时，才产生 learning evidence。

### dashboard_view_model

```json
{
  "today_tasks": [],
  "current_state": {
    "strengths": [],
    "risks": [],
    "trend": []
  },
  "note_assets": {
    "manual_notes": 32,
    "ai_confirmed_notes": 18,
    "scoring_cards": 12,
    "error_patterns": 5
  },
  "subjective_vs_coach_focus": {
    "user_focus": [],
    "coach_focus": [],
    "mismatch_reason": ""
  }
}
```

### 11.1 AI 增强能力归属

智能学习卡片里的“鲁班整理、采分点表达、关联错因、下一步动作”不能新起一个孤立 prompt blob。

P0A 的能力归属：

- 知识点、错因、采分点：优先读取既有 grading / attempt detail / learning-report read model / `training_intent`。
- 案例题采分点表达：复用 construction grading / question lifecycle skill context 和已有 rubric evidence，低置信时降级为“审题要点”。
- 下一步动作：来自 `training_intent` 或当前卡片的 immediate action，不另算处方。
- AI enhanced content 只是用户资产增强，不写 `learning_evidence`，不改 learner summary。

禁止模式：

- 新增一个 notebook enhancer prompt 重新抽取知识点、错因、采分点和推荐。
- 让 AI card enhancer 独立判断 mastery。
- 让 AI card enhancer 绕过 rubric confidence，把低置信文本标成“采分点”。

## 12. API 草案

P0A 不新增第二套首页接口，不新增 planner CRUD，不新增 cards writer。后续实施优先复用现有 notebook router，并扩展 learning-report read model。

| API | 作用 | authority 边界 |
| --- | --- | --- |
| `POST /api/v1/notebook/add_record` | P0A 从答疑/批改来源创建用户笔记卡片 | 复用现有 writer，但必须改为轻 writeback；metadata 带 `source_ref/card_type/evidence_event_ids/mastery_effect=none`。 |
| `PATCH/DELETE notebook record` | 用户编辑、删除、确认笔记 | 只改用户资产；不改 `learning_evidence`，不触发 summary rewrite。 |
| `GET /api/v1/mobile/learning-report` | 学情工作台首页 / 今日任务 / 笔记资产 projection | 唯一首页 read model 扩展点；不得新增 `learner-workspace/home`。 |
| 既有出题/测评/批改入口 | 用户要求“测一下” | 进入既有 `deep_question` / assessment / grading / evidence 链路；不新增 probe writer。 |
| P0B `planner_tasks` | 用户创建、延期、完成任务 | P0B 才允许；P0A 不做 planner CRUD。 |
| P0B AI candidate decision | 批量 AI 待确认笔记箱 | P0B 才允许；P0A 只做 inline 单条建议。 |

禁止新增：

- 专用聊天 WebSocket。
- 前端直接写 learning evidence 的接口。
- 绕过 `training_intent` 的推荐接口。
- `GET /api/v1/learner-workspace/home`。
- P0A 的 `POST /api/v1/planner/tasks` / `PATCH /api/v1/planner/tasks/{id}`。

## 13. 指标

产品采用“沉淀 -> 行动 -> 复测 -> 改善”的指标，而不是只看笔记数量。

| 指标 | 含义 |
| --- | --- |
| `note_save_rate` | 答疑/批改后保存笔记的比例。 |
| `ai_note_acceptance_rate` | AI 待确认笔记被保存或修改保存的比例。 |
| `note_to_action_click_rate` | 笔记保存后点击“马上练一道 / 测一下 / 改写”的比例。 |
| `task_completion_rate` | 今日/本周任务完成率。 |
| `note_to_training_rate` | 笔记触发同类题、改写、复测的比例。 |
| `retest_improvement_rate` | 从笔记/错因触发复测后的改善率。 |
| `false_profile_claim_rate` | 用户标记“不准确”的学情判断比例。 |
| `calendar_return_rate` | 用户因计划/提醒返回学习的比例。 |
| `stale_note_rate` | 长期未复习、未训练、未更新的笔记比例。 |
| `profile_claim_precision` | 抽样审查学情判断与证据是否一致。 |
| `hallucinated_profile_claim_rate` | 没有 source event 支撑的画像 claim 比例。 |
| `stale_claim_rate` | 已过期、已改善但仍在活跃推荐的 claim 比例。 |
| `brain_first_lookup_hit_rate` | 个性化对话/任务生成前成功读取 compiled truth 的比例。 |
| `provenance_trace_coverage` | 个性化建议可展示 supporting event ids 的比例。 |
| `nightly_lint_actionable_rate` | nightly lint 发现的问题中可转成修复/复测动作的比例。 |

## 14. 风险与缓解

| 风险 | 表现 | 缓解 |
| --- | --- | --- |
| 确认疲劳 | 每次学习后都弹很多确认 | 只推 1-3 条高价值候选；低置信内容进汇总箱。 |
| 手动笔记污染 summary / recall | 当前 notebook 保存会触发 summary rewrite，并可能进入后续 recall | P0A 前置修复：手动收藏只走轻路径；recall 标“学员自记/主观关注”并降权。 |
| 日历变负担 | 用户觉得又多一个系统要维护 | P0A 只做今日任务条，支持“今天时间少”前端过滤；周/月列表推到 P0B。 |
| 第二套推荐 authority | planner 自己算下一步训练 | 计划只呈现/排程；推荐来自 `training_intent`。 |
| 第二套首页 read model | 新增 `learner-workspace/home` 与 `mobile/learning-report` 并行 | 禁止新首页接口；只扩展 `GET /api/v1/mobile/learning-report`。 |
| notebook 持久化丢写 | 多端同时写 file-backed JSON records 数组 | P0A 生产前置 durable store + RLS + owner scope + 乐观并发；否则只能单端内测。 |
| P0A planner 半成品 | 没有 store 却承诺用户自建、延期、完成任务 | P0A 只读 projection；用户自建/延期/完成推到 P0B。 |
| AI 自说自话 | 用户不信系统判断 | 每条诊断有证据链和“不准确/测一下”。 |
| 教师端隐私风险 | 老师看到过多原始聊天 | P0A/P0B 教师端只展示聚合事实和证据摘要；原文权限另定。 |
| 首屏过载 | 看板堆满卡片 | 今日行动优先，证据和图谱下钻。 |
| 历史证据不完整 | 老用户有笔记但缺题干/答案/解析 | 可以展示为历史收藏，但不能驱动稳定诊断或下一步训练。 |
| AI 增强内容过度自信 | AI 把用户一句收藏扩展成错误知识点 | AI enhanced content 必须带置信度和“修改/不准确”；低置信只保存原文。 |
| 删除语义混乱 | 用户删笔记后以为系统忘记所有学习事实 | 删除笔记只影响用户资产；原始 learning evidence 仍保留，并在 UI 说明。 |
| 多端冲突 | 手机和 Web 同时编辑笔记 | 生产 P0A 必须有 durable store + 乐观并发；不允许靠 `updated_at` 假装安全。 |
| 考前任务过载 | 系统每天推太多任务 | 考前模式任务更少、更短，以错因复测和采分点模板为主。 |
| 低可信复测假改善 | rubric 覆盖不足时，“测一下”误把弱点刷成已掌握 | probe evidence 必须带 `measurement_confidence`；低于门槛不写 improvement evidence。 |
| 用户编辑错误内容回流 | 用户把 AI 内容改错，后续被 recall 注入 | user-edited 内容进入 recall 时标“学员自记，仅供参考”，不能作为教学事实。 |
| 跨 bot 笔记归属混乱 | 佑森包、鲁班 bot、教师 bot 各自写局部笔记 | 工作台按 learner 聚合，`source_bot_id` 只作来源标签，不形成第二套 learner truth。 |
| GBrain 变第二套 authority | 新增独立 memory / retriever / dashboard reader | 只增强 `LearnerStateService`、`RAGService`、`learning-report` 主链，不新增独立入口。 |
| compiled truth 盖过考试事实 | 个性化判断影响标准答案或 exact question 排序 | authority 顺序固定：exact question / 标准 / 教材 > compiled truth > 普通语义 chunk。 |
| 图谱黑箱化 | 用户看到复杂关系但不知道该做什么 | 只展示局部链路和下一步动作；完整 graph 先留在系统层。 |
| nightly lint 自动作废正确判断 | 后台维护误删仍有效弱点 | P1 只 dry-run + 审计；自动修复必须有回滚和人工抽检。 |

## 14.1 失败救援图

| 失败点 | 用户看到什么 | 系统救援 |
| --- | --- | --- |
| 无证据可解释推荐 | “暂无足够证据，先做一个 5 分钟诊断” | 用 starter task，不生成伪个性化。 |
| 保存笔记失败 | 明确 toast：保存失败，可重试 | 不显示“已加入学习档案”。 |
| AI 建议被拒绝 | “已减少类似提醒” | 标记 candidate decision，不删 evidence。 |
| 今日任务未完成 | 第二天显示“昨天未完成，是否压缩成 1 个任务” | 不惩罚、不刷负面标签。 |
| 复测失败 | “这个点仍不稳定”并给 1 个更小练习 | 不扩大成整章学习计划。 |
| 复测成功 | “这次已通过，降低提醒频率” | 写入 improvement evidence 后刷新 projection。 |
| 复测置信度低 | “这次测试不足以判定，先看 1 个讲解或换一道标准题” | 不写 improvement evidence，不降低提醒频率。 |
| source ref 丢失 | 只显示普通笔记，不显示诊断结论 | 阻断进入错因/掌握判断。 |
| 收藏待同步 | “已暂存，待同步；同步前暂不计入学情” | 回网后补发 notebook record / candidate decision。 |
| 用户编辑内容不可靠 | “这是你的自记内容，鲁班不会把它当作已掌握证据” | recall 低权重注入，不能进入教学事实。 |
| 教师无权限查看原文 | 展示证据摘要和数量 | 原始聊天需单独授权。 |

## 15. 验收清单

### P0A 产品验收

- AI 回答后可一键收藏成笔记。
- 案例批改后可加入错因地图或采分点手册。
- AI 自动整理内容在答疑/批改后以 1 条高置信建议出现，默认不入库。
- 今日计划最多显示 3 个任务。
- 每个任务都有来源、原因、动作。
- 笔记可转为复习、同类题、改写或复测。
- 用户可编辑、删除、拒绝 AI 笔记。
- “我已掌握”走复测，不直接改 mastery。
- 学情判断可点开证据。

### P0A 技术验收

- 新增或修改接口不得新增聊天 WebSocket。
- 前端不得直接计算 mastery、错因置信度或处方推荐。
- 手动笔记保存不写 `learner_memory_events.learning_evidence`。
- 手动笔记允许写 `notebook_*` memory event 或 notebook record，但不得触发 `refresh_from_turn()`、`_rewrite_summary()` 或 compiled-truth refresh。
- `mastery_effect=none` 只能是审计字段，不能作为主要安全边界。
- 任务完成不直接写 mastery。
- 训练、作答、复测结果仍走既有 grading / evidence writer。
- probe / “测一下”写入 improvement evidence 前必须满足 `measurement_confidence` 门槛。
- `training_intent` 仍是处方推荐 authority。
- P0A 今日任务只能扩展 `GET /api/v1/mobile/learning-report` view model，不新增 `learner-workspace/home`。
- P0A 不新增 planner CRUD；`我创建`、延期、完成任务状态推到 P0B。
- notebook 数据必须 owner-scoped；生产 P0A 必须有 durable store + RLS + 乐观并发，或明确标为单端内测。
- 微信小程序和佑森融合包 view model 不漂移。
- source ref 缺失时，不得展示“根据历史证据判断”的文案。

### P0A 量化 gate

这些不是长期 KPI，而是内测判断 P0A 是否值得推进到 P0B 的门槛：

| Gate | 目标 |
| --- | --- |
| 保存成功率 | 点击收藏后服务端成功率 >= 99%。 |
| 收藏后行动转化 | 保存笔记后 24 小时内进入复习/训练的比例 >= 20%。 |
| 今日任务完成率 | 内测用户今日任务完成率 >= 35%。 |
| 不准确率 | AI 建议被标记“不准确”的比例 <= 15%；超过则降低自动建议频率。 |
| 证据覆盖 | 诊断卡中可点回 source ref 的比例 >= 95%。 |
| 首屏负担 | 新用户首屏最多 3 个任务 + 1 个次级入口。 |
| summary 污染 | 保存手动笔记后 learner summary / compiled-truth projection 不应变化。 |
| 首页 reader | 今日任务字段只来自 `/api/v1/mobile/learning-report`，不存在第二个首页接口。 |

### P1 Learning Brain 增强 gate

这些 gate 不阻塞 P0A，但进入 brain-first lookup / typed graph / nightly lint 前必须满足：

| Gate | 目标 |
| --- | --- |
| claim source coverage | 进入 `L1_repeated` / `L2_confirmed` 的 claim 100% 有 supporting event ids。 |
| authority order | exact question / 标准 / 教材检索结果不得被 compiled truth 覆盖。 |
| stale claim lint | nightly dry-run 能识别 stale / superseded / conflict claim，并输出审计报告。 |
| brain-first trace | 个性化对话 trace 中能看到是否读取 compiled truth、读到了什么、为何使用或未使用。 |
| graph explanation | “错因 -> 训练 -> 复测”链路能被翻译成用户可读文案，而不是只展示 JSON/图谱。 |

### 手工回归

微信开发者工具或真机至少验证：

1. 答疑 -> 收藏 -> 生成笔记卡 -> 马上练一道。
2. 案例批改 -> 加入采分点 -> 生成同类题 -> 完成后回到学情。
3. 答疑/批改后 1 条高置信建议 -> 保存 / 修改保存 / 不准确。
4. 今日任务条 -> 今天时间少，前端压缩到 1 个任务。
5. 我其实会 -> 给我测一下 -> 复测结果刷新。
6. 保存手动笔记后，learner summary / compiled-truth projection 不变化。

## 16. 相关代码入口

后续实施前优先审查：

- `deeptutor/services/learner_state/service.py`
- `deeptutor/services/learner_state/learning_synthesis.py`
- `deeptutor/services/learner_state/learning_report_read_model.py`
- `deeptutor/services/learner_state/learning_brain_read_model.py`
- `deeptutor/services/learner_state/conversation_learning_evidence.py`
- `deeptutor/services/learner_state/training_intent.py`
- `deeptutor/services/learner_state/study_plan.py`
- `deeptutor/services/learner_state/attempt_detail_read_model.py`
- `deeptutor/services/learner_state/mistake_book.py`
- `deeptutor/services/notebook/service.py`
- `deeptutor/api/routers/notebook.py`
- `deeptutor/api/routers/mobile.py`
- `yousenwebview/packageDeeptutor/`
- `wx_miniprogram/`

## 17. 分阶段实施建议

### Phase 0：现实校验

- 收权 notebook writeback：手动收藏只写 notebook 用户资产 / `notebook_*` 事件，不调用 `refresh_from_turn()`。
- 审查并落定 notebook durable store：生产 P0A 必须有 Supabase/RLS/owner-scope/乐观并发；否则只能单端内测。
- 确认 P0A 今日任务只扩展 `learning_report_read_model`，不新增首页 read model。
- 明确 P0A 不做用户自建 planner task，`learning_plans` 不承载日历任务。
- 审查小程序现有导航和学情页首屏可用空间。
- 定义 notebook card / today task 最小 view model。
- 验证 notebook writeback 产生的 `notebook_*` event 不会被 learning-state inference、summary、recall 当作 mastery evidence。
- 验证 probe evidence 的 `measurement_confidence` 门槛。

### Phase 1：P0A 最小闭环

- 一键收藏。
- 智能学习卡片。
- 价值发生点建议保存。
- 今日计划 3 任务。
- 笔记转训练。
- 证据链下钻。
- learning-report read model 扩展。

### Phase 2：P0B 可用性增强

- AI 待确认笔记箱。
- 简版计划列表。
- 用户自建 planner task / 延期 / 完成状态。
- 采分点手册入口。
- 错因地图入口。
- 周复盘。

### Phase 3：P1 个性化增强

- 周计划/月目标。
- 主观关注 vs AI 教练关注。
- 个人采分点手册。
- 错因地图和笔记互链。
- brain-first lookup 接入对话、今日任务和学情解释，但只作为个性化上下文。
- claim lifecycle 可见化：`L0/L1/L2/stale/superseded/rejected` 转成用户可理解标签。
- 局部 typed graph：围绕单个错因展示“证据 -> 漏分采分点 -> 训练 -> 复测”。
- provenance 抽屉：个性化建议可点回 supporting event ids 和 attempt detail。
- nightly lint dry-run：只出报告和复测建议，不自动改写稳定画像。
- 周报/月报。

### Phase 4：教师端与机构化

- 教师提示卡。
- 班级共性错因。
- 教师布置任务。
- 学员计划完成和复测改善追踪。

### Phase 5：Learning Brain 评估与维护闭环

- Learning Brain eval harness：画像准确率、无证据画像率、过期画像率、个性化召回命中率、复测改善率。
- maintenance workflow：nightly lint 从 dry-run 进入可回滚修复。
- source-aware retrieval gate：compiled truth 只在 weak-point / next-training 类意图中进入 final source，其余场景先 shadow。
- 教研抽检台：抽样查看 claim、supporting evidence、推荐动作和复测结果是否一致。

## 18. 不确定性与验证方案

| 不确定性 | 当前判断 | 验证方案 | 替代方案 |
| --- | --- | --- | --- |
| notebook 当前 local JSON 是否能承载生产笔记 | 基本判定不能承载多端生产并发 | 双客户端并发 `add_record` 到同一 owner_key，验证 lost update；审查 RLS/backup/restore | 新增 durable notebook store；若不做，只允许单端内测。 |
| notebook 收藏是否触发 summary LLM 改写 | 已证实当前会触发：`_writeback_learner_state -> refresh_from_turn -> _rewrite_summary` | 保存一条笔记，检查 summary mtime、summary refresh outbox、compiled-truth projection hash | P0A 前先切轻路径，只 append notebook event，不改 summary。 |
| `learning_plans` 是否适合日历任务 | 判定不适合 P0A，它是 Guided Learning plan/page | 不再用它承载 P0A 任务；P0B 若需要任务管理再单独设计 | P0A 只用 learning-report projection；P0B 建 `planner_tasks`。 |
| summary / recall 是否会把 notebook event 当学习事实 | 需要回归守门；风险高于 mastery 污染 | 保存笔记后检查 `build_context_candidates` memory_hits 和 final prompt 标签 | recall 候选标 `student_note`、低权重、提示“不代表已掌握”。 |
| AI 待确认笔记箱是否提升留存 | 不确定，可能造成确认疲劳 | 先测 inline 1 条建议的接受率，再开放 inbox | 若接受率低，只保留手动收藏 + 答后学习卡片。 |
| 用户会不会把“删除笔记”理解成“系统忘记我” | 高风险 | 可用性测试中观察删除后反馈理解 | 删除时文案明确“只删除你的笔记，不删除历史作答证据”。 |
| 老师端是否能看原始聊天 | 涉及隐私和机构协议 | 内测前明确授权模型和脱敏策略 | P0/P1 只给聚合证据摘要，不给原文。 |
| 采分点卡片质量是否足够可靠 | 取决于 rubric 覆盖和 grading evidence 质量 | 只对 `grading_key` / curated / 合格 projected rubric 点亮“采分点” | 低置信时展示为“审题要点”或“复习提示”。 |
| probe 是否会制造低可信 improvement | 风险存在，尤其 rubric 覆盖不足时 | 检查 probe writer 是否输出 `measurement_confidence`，低于门槛不得写 improvement | 低置信时只展示讲解或换标准题。 |
| brain-first lookup 会不会干扰标准答案 | 有风险，尤其学员画像与题目标准事实冲突时 | fixture 覆盖 exact question / standard clause / weak-point review / next-training 四类 query | 先 shadow trace；只在 weak-point / next-training 开启 final source。 |
| claim lifecycle 是否会让学员困惑 | L0/L1/L2 对用户不可读 | 可用性测试中只展示“待确认观察 / 反复出现 / 已复测确认 / 待复测” | 专业标签只给教师端和审计日志。 |
| nightly lint 自动维护是否可靠 | 可能误判 stale / conflict | P1 只 dry-run + 人工抽检，不自动修复 | P2 再加可回滚修复和审计。 |

## 19. 最优交付切片

当前条件下最稳的交付切片是：

```text
答疑/批改结果
  -> 一键收藏
  -> source-linked 智能学习卡片
  -> 今日任务条出现“笔记待行动”或立即练一道
  -> 练一道 / 测一下
  -> grading/evidence 回流
  -> 学情页显示是否改善
```

这条链路足够小，可以落地；也足够有价值，能让学员感到“鲁班不是只回答一次，而是在帮我把下一步学清楚”。

GBrain 后续最稳的交付切片是：

```text
learning_evidence
  -> claim lifecycle
  -> compiled truth / typed graph projection
  -> brain-first lookup
  -> 个性化解释 + 今日任务
  -> 复测 / 改善 evidence
  -> nightly lint 检查 stale / conflict / missing evidence
```

这条链路不作为 P0A 阻断，但必须成为 P1 之后学情工作台从“好用的笔记和计划”升级为“真正懂学员的学习事实引擎”的主线。

## 20. 一句话定位

普通题库记录你做错了哪道题；鲁班学情工作台记录你为什么丢分、你自己想记住什么、系统建议你先补什么，并把这些内容安排成今天就能执行的学习计划。
