# Learner State Contract

## 范围

这一份 contract 管：

- 学员级长期状态的单一权威
- `Summary / Profile / Progress / Goals / Memory Events / Heartbeat`
- Guided Learning / Notebook / Quiz / TutorBot 对长期状态的写回边界
- 学员级状态与 TutorBot runtime sandbox / session cache 的边界
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
7. 会员控制台 / 学员 read-model 访问 token 是身份边界，不是 learner-state truth。签名 token 必须同时满足 HMAC-SHA256 校验、`hmac.compare_digest`、未来 `exp`；缺失、非法或过期 `exp` 必须 fail-closed，不得被解释为“无过期时间”继续访问 learner read model。

### Compact Context 读取边界

- `LearnerStateService.build_compact_context()` 只渲染 learner profile、summary、progress、goals 这类稳定学员事实；它不得读取 `learner_memory_events`，也不得把 recall evidence 当作每轮默认上下文。
- `learner_memory_events` 只在明确 recall-like 路由或 `build_context_candidates()` 判定需要 memory hits 时读取。普通问答的 compact learner context 必须避免额外 memory-event read，以降低每轮上下文构建延迟，同时保持 memory events 作为 durable learner evidence authority。

### Learning Evidence Pipeline

- `LearnerStateService.append_memory_event(memory_kind="learning_evidence")` 是学习证据写入、dedupe 和后续 synthesis 触发的唯一服务入口；API/router/wrapper 不得各自触发第二套长期画像刷新。
- `dedupe_key` 命中时必须返回既有事件，不得再次写入 `MEMORY_EVENTS.jsonl`，也不得再次触发 compiled-truth synthesis；读模型可以按同一 `dedupe_key`/内容 fingerprint 折叠 local+remote replay，但不得折叠 dedupe 不同的真实复练/复测。
- 自动 synthesis 只允许在显式开关 `LUBAN_LEARNING_EVIDENCE_AUTO_SYNTHESIS_ENABLED=1` 下运行；生产环境还必须受既有 `qa_`/`operator_` canonical cohort gate 约束。broad learner canonical truth 仍由 `canonical_truth_promotion_decision()` 决定，不能因为自动 synthesis 而默认打开。
- `learning_evidence.payload_json.canonical_topic` 是 taxonomy resolver 对证据的只读投影。Learning report、Learning Brain 和 synthesis 消费它时，不得在 UI/router 层重新猜 topic；若该字段缺失，旧事件继续按兼容路径读取。
- PGO shadow same-attempt evidence 只能作为 `learning_signal_type="pgo_case_rubric_shadow"` 的
  preview-only `learning_evidence` 写入同一个 `learner_memory_events` ledger。该事件只允许携带
  `artifact_version`、`point_id`、verdict、score coverage 摘要和 read-model 所需字段，不得持久化
  逐字 `official_slice`，不得写 official score，不得促升 mastery，且必须保持
  `claim_promotion_allowed=false` 与 `canonical_truth_written=false`。

### Dream Cycle 夜间巩固与投影缓存（2026-06-12）

- `LearningBrainDreamCycle`（learner_state/dream_cycle.py）是唯一的后台巩固调度器：周期性对有学习证据的用户执行 `synthesize_learning_truth(dry_run=False, event_limit=None)`（全量历史）。它不计算任何新事实，不构成第二合成权威；合成只在 `learning_synthesis` 内，持久化与 canonical 促升门控只在 `canonical_truth_policy` / `write_compiled_learning_truth` 内。
- 默认关：`LUBAN_LEARNING_BRAIN_DREAM_CYCLE_ENABLED`（fail-closed）；间隔由 `LUBAN_LEARNING_BRAIN_DREAM_CYCLE_INTERVAL_HOURS` 控制（默认 24h）。生产环境候选用户限定既有 `qa_`/`operator_` canonical cohort——dream cycle 不得放宽任何授权门。
- `read_compiled_learning_truth` 的产物是**可重建的只读投影缓存**（read model），不是第二记忆权威；任何消费方（TutorBot turn、trajectory 查询）必须实现 cache-miss 回退到 dry-run synthesis，不得因缓存缺失而拒绝服务或自造画像。
- `learning_trajectory.find_learning_trajectory` 是 typed_graph / weak_points / improvement_signals 之上的纯只读多跳组合视图（错因→训练→改善→复测建议）；其 `retest_recommendation` 是建议而非促升，canonical 促升仍只认 teacher-final / real_retest。
- 多 worker 单执行者：dream cycle 的 watermark（`.dream_cycle_last_run`）与互斥锁（`.dream_cycle.lock`）、outbox flush 的互斥锁（`.outbox_flush.lock`）都落在 learner state root 下，经 `worker_file_lock.try_exclusive_file_lock`（fcntl 非阻塞排他）表达"同一时刻只有一个 worker 实际执行"；锁被占=本 tick 跳过，不排队、不重试、不引入第二调度权威；watermark 跨重启生效，重启不再触发重复巩固；删除 `.dream_cycle_last_run` 是运维强制立即重跑的唯一入口。

## 2026-06-09 Workspace 撤回与正名决策

撤回旧解释：不得再把“每个会员一个独立 workspace”理解成“每个会员或每个 TutorBot 都有一套独立长期学习记忆系统”。该解释会制造第二套 learner truth，已被本 contract 退役。

保留正确目标：每个会员可以拥有独立的学员可见资产空间，用于笔记、附件、收藏、导出、学习页 projection、权限隔离和用户掌控感。但这个空间只是 `owner-scoped learner asset namespace`，不是 learner-state authority。

TutorBot 侧同步正名：

- 退役概念：`TutorBot workspace = 独立学习空间 / 独立长期记忆`。
- 保留能力：`TutorBot RuntimeSandbox = 工具运行隔离 / 临时产物 / channel cache / debug replay`。
- 长期学习事实只允许进入 `LearnerStateService` 和其 durable store。

### 五个一等概念

后续设计只允许围绕以下五个一等概念扩展，禁止再把 workspace 扩张成第六套学习真相：

| 概念 | 职责 | 禁止承担 |
| --- | --- | --- |
| `LearnerState` | 学习证据、画像、弱点、掌握度、复测变化、next action 的长期 truth | bot 局部猜测、手动笔记直接改 mastery |
| `SessionStore` | 所有聊天/session 历史、turn replay、channel conversation continuity | 长期 profile / progress / weak point |
| `BotProfile` | TutorBot 人格、教学风格、技能绑定、channel 绑定 | 学员长期状态 |
| `LearnerWorkspace` | 学员可见资产空间：笔记、附件、收藏、导出、学习页 projection | 学习事实判断、推荐处方、compiled truth |
| `RuntimeSandbox` | 工具执行隔离、临时文件、短期 cache、debug artifact | 任何 durable learner truth |

### 迁移映射

| 旧 TutorBot workspace 内容 | 收敛后的 authority |
| --- | --- |
| persona / soul | `BotProfile` / bot template registry |
| skills | Skill / Capability registry + `bot_id` binding |
| sessions | `SessionStore` |
| channel config | TutorBot channel config service |
| cron / heartbeat | learner heartbeat service + global arbitration |
| memory consolidation | `LearnerStateService` event/synthesis pipeline, or conversation-only session summary |
| media / attachments | owner-scoped attachment store with quota / retention |
| logs / replay | observability / trace / session replay |
| tool scratch files | `RuntimeSandbox` |

### 禁止模式

- `per_user_workspace -> PROFILE/SUMMARY/PROGRESS/COMPILED_TRUTH`
- `TutorBot workspace memory -> LearnerState overwrite`
- `workspace_summary -> learner profile`
- `manual_note -> mastery++`
- `calendar_completed -> mastered`
- `bot overlay -> global weak point`
- `per-user workspace -> copied rubric / KB / runtime_supply`

## P0A NotebookCard / NoteAssets Contract

`NotebookCardService` 是 P0A 学习卡片的唯一写/读/删 authority。它管理的是
owner-scoped 用户资产，不是 learner truth。生产持久化表为
`learner_notebook_cards`，按 `user_id + note_id` 隔离，带 RLS 与 `version` 乐观并发。

卡片写入边界：

- 入口复用 `POST /api/v1/notebook/add_record`，以 `metadata.card_type` 作为分流键。
- 命中 `scoring_card / error_pattern_note / review_note / manual_note` 时，必须走
  `NotebookCardService.save_card()`；未命中时 legacy `NotebookManager` 行为保持不变。
- 卡片保存只能调用 `LearnerStateService.record_notebook_writeback()` 追加一条低权重
  `student_note` recall 事件。
- 卡片保存、更新、删除不得调用 `refresh_from_turn()`、`_rewrite_summary()`、
  `patch_overlay()`、compiled-truth refresh 或任何 mastery/profile/progress promotion。
- `mastery_effect` 在 P0A 固定为 `none`；调用方传入其他值必须被忽略。
- 删除语义是 archive 用户资产，`learning_evidence` 不物理删除。

读取投影边界：

- `GET /api/v1/mobile/learning-report` 可以只读投影 `note_assets` 与最多 3 条
  `today_tasks`。
- `note_assets` 的 authority 字段必须指向 `learner_notebook_cards`。
- `today_tasks` 是 read-only projection，只能从 learning-report read model 生成；P0A
  不允许新增 planner CRUD、完成状态落库、延期、周/月日历或第二首页 reader。
- 若卡片缺少 `source_ref`，前端不得展示“可追溯到历史证据/稳定诊断”的判断，只能把它当作
  学员自记资产。

行为埋点边界：

- P0A 事件必须复用 `surface-events -> product_behavior_events`，不得新增 learner-workspace
  专用埋点 endpoint。
- 允许事件名：`note_card_suggested`、`note_card_saved`、`note_card_rejected`、
  `note_action_started`、`probe_requested_from_note`、`today_task_rendered`、
  `today_task_started`。
- 行为事件 metadata 不得包含原始作答、完整聊天文本、手机号、验证码或完整自由文本。

## Member Console / BI Audit Boundary

- `deeptutor/services/member_console/*` 可以记录 admin-facing 运营备注和 BI 审计流水，例如
  `ops_action_result`、`feedback_triage`、`bi_export_request`。
- 这些记录不是 learner state writeback，不得修改 `learner_summaries`、
  `learner_memory_events`、profile、progress、goals、heartbeat 或 overlay 真相。
- BI 会员列表 / 会员经营总量的 eligibility authority 是 Supabase
  `public.user_identity_aliases` 中 `alias_type='phone'` 且来源可信的手机号身份：
  `phone_backfill`、`member_console_backfill`、`phone_verification`。`public_users_backfill`
  是批量迁移 / 测试污染高风险来源，不得计入真实运营会员。`public.v_members` 只负责为这些
  phone-backed identities 补充钱包、画像和聊天汇总 read model。`member_console` 本地 JSON
  只能作为运营备注、审计流水、conversation view audit 和低风险动作记录的 overlay；不得再作为
  生产会员池、注册手机号池、钱包存在性或学习事实的 canonical source。
- `member_console` 可以提供会员套餐展示 read model 和运营包配置投影，但新注册用户的默认权益必须是
  0 点；充值到账、扣费、冻结余额和钱包存在性仍只属于 `WalletService` / wallet ledger
  authority。套餐展示中的原价、现价、点数和可用轮次只是 commerce read model，不得写入 learner
  profile、learner summary 或 learner memory。
- 会员套餐目录可以通过 audited admin endpoint 增删改，并由 `member_console.packages` 作为 BI
  commerce 的套餐目录 authority；这只改变后续可售 / 可人工开通的套餐配置，不回写历史购买流水，
  不改变 wallet ledger 的收入事实，也不得成为 learner-state 或会员余额的第二套 authority。
- BI / member-console 可以提供传统会员管理式的人工开通 / 续费入口，但该入口必须同时满足三条边界：
  权益变更写 `member_console` 审计，点数 / 收入事实写 `WalletService.grant_points()` 产生的
  `wallet_ledger` purchase 流水，前端和 BI commerce 不得自造收入表或把人工开通写成 learner-state
  事实。若 wallet service 不可用，人工付费开通必须 fail-closed，不能只改会员到期时间。
- BI 会员运营新增窗口指标（例如今日、近 7 天、近 30 天新增）只能在上述可信会员目录内按
  canonical member `created_at` 计算；它们是 dashboard read model，不得从前端分页结果、
  行为事件、钱包流水、运营备注或 learner-state projection 反推，也不得写入
  `learner_summaries`、`learner_memory_events`、profile、progress、goals 或 heartbeat。
- BI 会员列表的 `last_active_at` 可以用 canonical session store 的真实会话更新时间做
  read-model overlay；当 Supabase 目录暂时缺少一个本地已注册、手机号可信且有 session 活跃
  证据的会员时，`member_console` 可以把该会员作为
  `member_console_session_activity_supplement` 补入列表。这个补入只修正运营读模型可见性和排序，
  不改变 Supabase 会员 eligibility authority，不得写 learner state，也不得作为新增会员窗口指标
  或钱包/学习事实的 canonical source。
- `member_console` 的角色权限矩阵与 per-user 权限覆盖只属于 BI/admin 控制面访问控制。它们可以决定
  管理员能看哪些运营 tab、执行哪些运营动作，但不得改变 learner profile、progress、goals、
  learner_memory_events、wallet ledger、turn/session state 或任何学习事实 authority。
- 如果某个运营动作需要改变 learner state，必须走 learner-state writeback / promotion
  authority，不能通过 member-console audit helper 旁路写入。
- 账号凭证事实与 learner-state 分权：`MemberConsoleService` 可以通过 external auth 管理
  登录密码、手机号验证码和密码找回；这些是账户凭证 authority，不是 learner-state
  writeback。`/api/v1/auth/reset-password` 成功后只能更新 external auth 密码、消费验证码并
  失效旧 auth session，不得写 `learner_summaries`、`learner_memory_events`、profile、
  progress、goals、heartbeat 或 assessment / turn state，也不得返回登录 token。
- 手机号不是 `user_id`；它是可信账户凭证 alias。`MemberConsoleService` 处理手机号验证码登录、
  微信手机号快速登录或注册去重时，必须先通过可信 `phone` alias 解析到 canonical UUID，再绑定或
  合并 member identity。`member_console` 本地 `member.phone` 只能作为兼容读模型和低风险补充，
  不得绕过 `public.user_identity_aliases` 另建第二个手机号账号 authority。
- 微信手机号强制绑定策略上线前签发的 `wechat_mp` token 不得继续作为正式会员态刷新或访问会员
  资源；服务端必须让这类旧会话重新走 `getPhoneNumber phone_code`，避免旧 wx-only session
  长期绕过手机号 canonical identity。
- Assessment TestSet session durability belongs to the assessment authority. In production,
  if Supabase `assessment_sessions` is required but not configured, member-console
  initialization and non-assessment auth/admin paths may still load, but assessment
  create/resume/report/explanation/writeback-retry paths must fail closed with
  `assessment_sessions_supabase_not_configured`; they must not silently use JSON or
  in-memory sessions as production authority.
- 会员身份合并链解析必须对成环安全。`MemberConsoleService._ensure_member` 会沿
  `merged_into` 指针回溯到 canonical 会员（`user_id == external_auth_user_id` 的那条），
  但多跳环（如 `A→B→A`）属于数据损坏，绝不能让解析无限递归 → `RecursionError` →
  `/api/v1/auth/login` 500 →（小程序显示"服务暂时不可用"登不进）。解析器必须跟踪已访问
  `user_id`，重访即停并把当前会员当 canonical 返回；数据层的环要单独修复（清 canonical
  的 `merged_into`），但代码层对任何成环输入都必须终止，登录永不因合并环而崩。

## 第二阶段预留语义：Bot-Learner Overlay

第二阶段允许在 **不改变 `user_id` 全局 learner truth** 的前提下，引入：

- `bot_id + user_id` 级局部 overlay

实现设计见：

- [2026-04-15-bot-learner-overlay-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/学习脑与学员记忆/2026-04-15-bot-learner-overlay-service-design.md)

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
- judge / bot 的判分输出原文，或其中题面未给出的脑补背景数值（如“中标价 1.7 亿”）。`working_memory_projection` 经 `turn_runtime` 当 EVIDENCE 块注入下一轮 judge；若回灌判分输出，会跨会话**自我强化幻觉**——judge 把自己上一轮脑补的数字当“参考证据”抄回。notebook 自动卡 writeback **不得**把判分输出 / 卡片摘要写进 `working_memory_projection`（#23 第二层，2026-06-23，DeepSeek-V4-Pro 异源核坐实）；卡片 summary 仍存卡片本身供展示，不污染 overlay。

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
- 生产环境写 canonical learner-truth 默认 **fail-closed**（M33-ACT G4）：
  `write_compiled_learning_truth` 在 `is_production_environment()` 下默认只返回 preview 投影、
  不落盘，从而保持 `canonical_truth_written=false` 安全不变量。该硬挡只能由
  `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED`（默认 OFF）显式打开；该 flag 的翻转
  本身还受 trusted adjudication / real-retest 权威 + 逐门授权约束，且设回 false / 未设即秒退回 preview。
  即使 flag=true，生产写入仍必须受
  `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_COHORT` 前缀门约束，默认只允许
  `qa_,operator_`；非 cohort 用户继续 preview/fail-closed，不得写入 durable store。
  如果需要 broad real-student canonical write，必须额外显式打开
  `LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_TRUSTED_ADJUDICATION_ENABLED` 或兼容别名
  `LUBAN_CANONICAL_LEARNER_TRUTH_BROAD_AI_ADJUDICATION_ENABLED`，并且 projection 的
  `synthesis_run.trusted_adjudication` 必须证明最终裁决来源可信。对外 contract 与主链路
  统一使用 `trusted_adjudication`；历史 `teacher_final` / `teacher_reviewed` 字段只能作为
  legacy alias 兼容旧读者，不得再作为真人老师终审前置或 UI 主文案。AI 裁决来源（如
  `llm_jury` / `ai_jury`）必须同时满足最低置信度
  `LUBAN_CANONICAL_LEARNER_TRUTH_AI_ADJUDICATION_MIN_CONFIDENCE`（默认 0.85）和
  `conflict_status=resolved`；低置信、冲突未解决、shadow draft、candidate-only 一律不得写
  canonical truth。真人老师只能作为 `human_teacher` / `human_qa_teacher` 等 trusted
  adjudication source 之一，不得成为 broad 默认链路的必需前置。
  生产环境即使 flag=true，也必须写入 Supabase/core-store 的
  `learner_summaries.summary_structured_json.learning_brain` 并从同一 core-store 读回；
  core-store 未配置或 writer 失败时继续 preview/fail-closed，不得退回本地
  `COMPILED_TRUTH.json` 作为 production authority。
  `synthesize_learning_truth(dry_run=False)` 生成的 `summary_refresh` 不得绕过同一 promotion
  policy 写入 `summary_structured_json.learning_brain`；promotion 不允许时只能刷新摘要文本，
  不得把 projection 通过 learner summary 旁路写成 durable canonical-ish truth。
  非生产路径不受此 flag 影响。

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
- `home_personalization` projection 的 canonical marker 必须位于 projection 本体的
  `source_status`：`home_projection_contract="canonical_taxonomy_v1"` 且
  `topic_authority="learner_state.home_personalization.canonical_taxonomy"`。外层
  dashboard 上挂一个空 `home_projection.source_status` 不能授权顶层 legacy
  `today_focus` / `recommended_prompts`。`fallback_used=true`、markerless payload、
  malformed payload、API failure fallback、guest preview、旧缓存和 member-console
  legacy focus 都不得被应用为“今日焦点”或“根据你的学情”自动推荐；它们只能降级为空态 /
  静态示例 / starter fallback，不得伪装成 canonical personalized recommendation。
- `write_home_personalization_projection()` 是 durable home personalization projection
  的写入门；它必须 fail-closed 拒绝 markerless 或非 canonical topic/prompt 的 payload，
  不得因为 shape 看起来合法就自动补 canonical marker。`MemberConsoleService` 与
  mobile / WeChat read model 只能读取并呈现通过同一 canonical validator 的 projection
  本体，不能从顶层 dashboard、旧缓存、`today.hint` 或 prompt 文案二次解释出推荐。
- 学情 / 首页展示 topic、Home dashboard 用户可见的 `today_focus` 与 recommended prompt
  topic 必须来自同一 learner-state / taxonomy authority 的 canonical label，并经
  taxonomy canonical resolver 对齐到教材目录 canonical 章/节名称。学情、每日任务、
  assessment evidence、next-best-action、`member_console`、learning report read model
  和微信 view model 只能提供证据与行动信号，不得从题干句子、prompt 文案、泛指词
  （如“本题为”“这题”）、自由文本、旧缓存 topic、frontend 解析结果或未入教材目录的
  短语反推出新的 focus / 推荐；无法映射到 canonical 教材章节或小节时必须丢弃或回退到
  最近有效 `learning_evidence` / starter projection。
- `member_console` 的首页 focus adapter 只能委托
  `learner_state.home_personalization.canonical_home_focus_topic_label()`；该 helper
  对用户可见首页主题先使用教材目录 alias / 章节目 canonical 名，再回退到 taxonomy
  canonical label，避免 `member_console` 形成第二套 topic 归一化 authority。
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
8. 提交一次性必须由 `assessment_sessions` repository 原子维护：正式 TestSet submit
   只能在 `status=in_progress` 且 `submitted_answer_snapshot is null` 的同一条件写中
   落库；并发同 body 重放返回既有 `result_report_json`，并发不同 body 必须返回
   `assessment_submit_body_conflict`。`device_id` 只作为该 durable session 的客户端
   lease token 传递给 repository，不能升级为 learner identity、billing identity 或
   training-intent authority。HTTP adapter 只能做请求体上限、限流、鉴权和错误语义，
   不得把 durable session 故障回落成 legacy JSON session truth。

### Assessment TestSet P0B/P1 Extension Contract

P0B/P1 只能扩展同一条 TestSet authority，不得为模拟卷、错题训练或深解再建第二套
session / evidence truth。

1. `real_exam_simulation` mini 卷必须复用 `assessment_sessions` durable session
   authority，使用 `real_exam_simulation_mini_v1` blueprint，返回 20 题 redacted
   public payload，暴露 `form_source`、`form_id`、`form_index`、`form_count` 作为
   轮换证据，并在 `result_report_json.assessment_type` 中保留 `real_exam_simulation`。
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

7. **Langfuse / BI 身份互证边界**：Langfuse trace 可以记录
   `identity_resolution_status`、`raw_user_id`、`member_user_id` 和
   `identity_matched`，用于把观测 user/session 归一到
   `MemberConsoleService` 输出的 canonical member id。Langfuse 不得成为第二套会员
   authority，不得反写会员资料，不得把手机号作为 trace user id 或额外 PII 扩散；未映射
   trace 只能标记为 `unmapped`，进入待绑定/排查队列。

### 单一权威清单

| 子事实 | 唯一 authority | BI v2 前端职责 |
|---|---|---|
| 会员身份 / Tier / 状态 | Supabase trusted phone aliases + `public.v_members` read model；`member_console` 仅 overlay 运营备注 / 审计 | 只读 + 受控写经 audited endpoint |
| Langfuse trace 身份归一 | Supabase trusted identity projection exposed through `MemberConsoleService` | 只读互证；unmapped 只排查，不创建会员 |
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

- 计划：`docs/plan/会员钱包计费与经营后台/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md`
- 灰度 runbook：`docs/zh/bi/bi-backoffice-v2-rollout-runbook.md`
- 阿里云部署 + 手动测试：`docs/zh/bi/bi-backoffice-v2-aliyun-deploy.md`
- WRITE_ENDPOINTS 注册表：`deeptutor/contracts/bi_v2_write_endpoints.py`

## member display_name 真值（2026-06-24）

`member_console` 投影的 `display_name` **不得回落为 `user_id`**：微信快捷登录曾把 `display_name` 误置为内部 `user_id`（退化态），导致学员台账把内部 uid 当昵称展示。修复后单点约束：当 `display_name` 缺失或等于 `user_id` 时，统一回落为 `微信用户{user_id 后4位}`（`member_console/service.py` 的 directory 投影与绑定路径同口径）。`display_name` 是**展示字段**，不是 learner identity authority——identity 仍按 `canonical_uid` 单点（见上文「单一权威」），display_name 退化不得污染 identity 解析。
