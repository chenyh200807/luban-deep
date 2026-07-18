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

### Summary Maintainer 门控（Battle2 S1）

- 摘要维护器（summary-maintainer）不是学员长期真相的 authority。它的单一权威是 `learner_memory_events` 账本加一个进程内读游标（per-worker cursor），门控只决定"这一轮要不要花一次 LLM 去重写摘要"，绝不改变账本真相。
- 门控的每次跳过（skip）不得丢失事实：每一个实质轮次仍然无条件落入 `learner_memory_events` 账本，摘要在下一次真正运行时按游标一次性消费自上次运行以来的全部增量。因此陈旧上限是 **per-worker N-1 个实质轮次**；多 worker 下全局上限为 `workers × (N-1)`，因为账本共享、跨 worker 的延迟消费永不丢。
- 门控必须 fail-open：未知游标、进程重启、另一 worker、扫描异常都判定为"未读"并立即运行；`guide*` / `notebook*` 等 capability 走直通（不受计数门约束）。
- 读游标只允许在一次**完整跑完**（含 `NO_CHANGE` 结果）之后重置；LLM 异常时不得重置，让陈旧游标下一轮继续触发运行，避免"摘要稳定 ⇒ mtime 不动 ⇒ 门永远打开"的退化。
- 后台摘要维护默认可挂 fast/light tier（`resolve_fast_tier_model` 为唯一 light-model authority）；生产环境未设置该 tier 时为零效果，不得宣称降档收益。
- 单次扫描共享：一个实质轮次的门决策（`_summary_gate_decision`）与摘要 source 构建（`_build_summary_source`）必须复用**同一次** `learner_memory_events` 本地读，由 `refresh_from_turn` 在锁内、当前轮次落账后读取一次并传入两者，杜绝每轮两遍全文件线性扫描。这是纯性能收口——门决策结果与 source 内容逐字节不变；两个消费者的 `events=None` 回退保持独立自读语义。此共享不覆盖 `read_snapshot` 自身的账本读（另一相位的独立读，不在此收口范围）。

### Memory Maintainer 门控（Battle2 S1 同病同修）

- 公开双文件记忆（`MemoryService`：SUMMARY.md + PROFILE.md，bot-side/user_id 为空的共享目录）的 `refresh_from_turn` 每轮无条件顺序两跳 LLM 重写（profile + summary），与 learner_state summary-maintainer 同病（约 57% 输出 NO_CHANGE 白烧）。修法照搬 S1 计数门控，不发明新机制。
- 门控只决定"这一轮要不要花一次 profile+summary 双跳重写"，绝不改变记忆真相；**profile 与 summary 两跳共用同一个门决策（一次判定管两跳），不得做两套门**。
- 门控必须 fail-open：门内部任何异常、以及"从未运行过（冷启动/进程重启）"都判定为立即运行；`guide*` / `notebook*` capability 走直通（不受计数门约束，镜像 S1 never-skip 集）。宁可多跑不可漏跑。
- 计数器只允许在一次**完整跑完两跳**（含 NO_CHANGE）之后重置；LLM 异常时不得重置，让陈旧计数下一轮立即重试。陈旧上限为 **per-worker N-1 个实质轮次**（`_MEMORY_GATE_TURN_THRESHOLD`）。
- 与 S1 的关键结构差异（合理偏离）：`MemoryService` 没有事件账本，门状态是进程内**单实例**计数器（非 per-user 游标），因此没有 S1 的 evidence-scan 分支，也没有 backlog re-feed——被节流跳过的轮次不入账本、不回补。公开记忆是滚动文档、稳定事实会在后续轮次复现，此丢弃可接受；补一套账本属"发明新机制"，不做。
- 门控决策计数走 observe-only Prometheus 计数器 `deeptutor_memory_maintainer_total{decision,outcome}`（`TurnRuntimeMetrics.record_memory_maintainer`），含 UVICORN_WORKERS>1 的多 worker 合并路径；与 `summary_maintainer` 同纪律、同 PR 上线。
- TutorBot workspace memory consolidation 只能消费完整的 provider response；
  `error`、`length`、`max_tokens`、缺失终止原因或其他 non-complete response 即使携带
  partial `save_memory` tool payload，也不得写 PROFILE/SUMMARY/HISTORY。失败仍沿既有
  bounded raw-archive recovery 计数，不得把截断的 LLM 参数提升成 durable memory truth。

### Learning Evidence Pipeline

- `LearnerStateService.append_memory_event(memory_kind="learning_evidence")` 是学习证据写入、dedupe 和后续 synthesis 触发的唯一服务入口；API/router/wrapper 不得各自触发第二套长期画像刷新。
- `dedupe_key` 命中时必须返回既有事件，不得再次写入 `MEMORY_EVENTS.jsonl`，也不得再次触发 compiled-truth synthesis；读模型可以按同一 `dedupe_key`/内容 fingerprint 折叠 local+remote replay，但不得折叠 dedupe 不同的真实复练/复测。
- `memory_kind="learning_evidence"` 只是存储分区，不足以让一条事件成为学习证据。local/remote 生命周期 reader 必须共用 `evidence_lifecycle.is_learning_evidence_record`：只读取显式 lifecycle source 集合中 `payload.event_type="learning_evidence"` 的事实 envelope（兼容 construction grading 的既有例外）；synthesis/promotion 再由更窄的 `is_learning_evidence_event` source 白名单与 quality gate 裁决。`luban_lesson` 等 non-promoting 生命周期事实必须可读但不得促升；未注册 rogue source 与 durable completion claim 等非 evidence envelope 控制记录即使同居该分区，也不得进入报告或学情投影。
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
  phone-backed identities 补充钱包和画像 read model；`public.chat_conversations` 是已确认死表
  （真实对话在宿主 SQLite `chat_history.db`），`v_members` 的聊天派生列
  （`first_chat_at`/`last_chat_at`/`total_conversations`/`total_messages`/`has_chat_history`）
  不得再被任何读取方消费，会员对话活跃事实只能从 canonical session store 派生
  （`_merge_session_activity_for_member_list`）。`member_console` 本地 JSON
  只能作为运营备注、审计流水、conversation view audit 和低风险动作记录的 overlay；不得再作为
  生产会员池、注册手机号池、钱包存在性或学习事实的 canonical source。BI 默认会员列表和经营总量
  必须展示真实运营会员：可信手机号身份仍需先排除带有 `account_kind='eval_runner'`、
  `actor_type='machine'`、`created_by='eval_runner'`、`is_internal_test=true` 等显式机器身份的账号；
  QA、eval、release smoke、practice anchor、army 类历史模拟账号和其它 `_looks_like_test_member`
  marker 只能作为旧污染兜底。
- 显式机器身份不得只停留在本地 external auth / member-console overlay。任何会把手机号身份写入
  `public.user_identity_aliases` 的 eval / smoke / QA 路径，必须把上述机器身份同步写入该 alias 的
  `metadata`；Supabase member directory 读取 phone alias 时也必须把这些 metadata 透传到
  member `identity_metadata`，让 BI 在 display name / identifier 已变成 UUID 或学员昵称时仍能排除
  机器账号。
- 注册渠道归因是 phone alias `metadata` 上的两个可选键：`reg_channel`（推广物料 `?ch=xxx`，
  清洗后只含 `[0-9A-Za-z_-]`，≤64 字符）与 `reg_scene`（微信启动场景值，纯数字）。写入方唯一是
  `MemberConsoleService` 的注册 / 微信手机号绑定路径，且只做 first-touch：账号密码注册必然是新会员
  直接写入；微信路径仅当该手机号尚无可信 canonical alias（真·首次注册）时写入，已注册用户复登录
  不得覆盖注册渠道。这两个键是 BI 渠道 ROI read model（会员列表 `channel` 字段与 member-stats
  `channels` 分组）的唯一来源；它们不是 learner state，不得写入 profile、progress、goals、
  learner_summaries 或 learner_memory_events，也不得成为身份判定或计费依据。
- Supabase member directory 读取 trusted phone alias 时，必须优先覆盖最近注册 / 最近验证的手机号身份，
  不能因为历史 backfill alias 数量超过读取上限而漏掉当天新增会员。若 `v_members` 暂无对应行，读取层必须
  hydrate `public.users.identifier`、`createdAt` 和 `metadata`，并把 `public.users.metadata` 与 alias
  `metadata` 合并为 member `identity_metadata`；历史 QA / eval marker 也必须进入
  `_looks_like_test_member` 的 alias / search 兜底，避免 alias-only 机器账号被误计入真实会员。
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
  canonical member `created_at` 计算；“今日新增”按 UTC+8 自然日计算，近 7 天 / 近 30 天
  仍是相对当前时间的滚动窗口。它们是 dashboard read model，不得从前端分页结果、
  行为事件、钱包流水、运营备注或 learner-state projection 反推，也不得写入
  `learner_summaries`、`learner_memory_events`、profile、progress、goals 或 heartbeat。
- 人工标记的内部/军团账号（`public.bi_internal_accounts` 审计流水中每个 user_id 最新一行
  `is_internal=true`）必须从 BI 全部会员统计口径消失：会员总量、新增窗口、增长漏斗、
  留存 cohort scoping、活跃学习者 scoping、commerce 会员基数。排除逻辑唯一收口在
  `BIService._load_all_members`（按 member identity values 与标记集求交），消费点不得各自
  再实现第二遍；标记表读取唯一走 `BIService._load_internal_account_states`。标记表读失败时
  fail-open（沿用缓存或空集并告警），BI 可短暂回到未清洗口径但不得整体不可用。该标记是
  BI 统计口径事实，不是 learner state，不得写入任何 learner 真相，也不影响会员运营
  工作区（`/member/list`）对内部账号的可见性——运营需要看到并管理这些账号。
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
- 账号密码注册必须在 `MemberConsoleService` 层先校验有效大陆手机号，再创建 external auth
  用户；手机号验证码登录、微信 `getPhoneNumber` 快速登录 / 绑定和账号密码登录必须共同收敛到
  同一个 canonical member identity，一个手机号只能对应一个账号，不得让用户名、openid、设备号或
  未验证手机号获得独立免费试用 / billing / learner-state 身份。
- 生产环境微信手机号快速登录 / 绑定必须使用 `getPhoneNumber` 返回的 `phone_code` 并经微信
  `getuserphonenumber` 换号；直传 11 位手机号只允许作为非生产 eval / legacy QA 兼容路径，且必须
  写入并同步到 external auth 的机器身份元数据：`account_kind='eval_runner'`、
  `actor_type='machine'`、`created_by='eval_runner'`、`is_internal_test=true`。这类账号不得计入
  BI 默认真实会员、今日新增、活跃或行为指标。
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
- 学-evidence（`learning_signal_type="lesson_viewed"`，融合计划 §2.1）：唯一 writer =
  `learner_state/lesson_evidence.record_lesson_view_evidence()`（经 `/api/v1/lesson-progress`
  路由），仍走 `append_memory_event` 唯一 sink。payload 必须带
  `event_type="learning_evidence"`（本 contract 硬要求）+ `evidence_level="exposed"`
  （ladder 外 level，不参与掌握排序）+ `quality.progress_countable=false`（report
  attempt/streak 与 mastery attempts 全部跳过）；`source_feature="luban_lesson"` 必须
  保持在 `learning_synthesis._is_learning_evidence` 白名单**之外**——看动画绝不进
  claim/weak point/mastery（M0）。dedupe_key 按（用户, pack, watched_stage, 业务日）
  折叠。消费边界：只被生命周期投影（「已学·待验证」态）等定向读侧消费；
  `home_personalization` 的最近事件选择器必须过滤 `lesson_viewed`（不顶替
  today_focus）；`learning_state_projection` 以 `lesson_view_count` 显式分类（不计入
  legacy_count）。
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
- `public.users` 已存在时，learner-state mirror writer 只能合并 `metadata`，不得重写
  `createdAt`；注册时间只在首次创建镜像行时写入。否则学情活动会被错误投影成 BI 新增会员。
- learner-state mirror 与手机号 identity writer 必须按 canonical `user_id` 从 external-auth
  identity authority 继承机器身份；任一 machine/eval 信号都必须闭合为
  `account_kind='eval_runner'`、`actor_type='machine'`、`created_by='eval_runner'`、
  `is_internal_test=true` 四字段，并同步到 `public.users.metadata` 与 phone alias `metadata`。
  下游 writer 不得用空 metadata 或仅含 mirror 来源的 metadata 覆盖这些字段。
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

### Home Next-Step Projection（融合计划 §3，2026-07-03 登记）

`home_next_step_projection` 是跨模式「下一步」的**呈现仲裁 read-model authority**
（display arbitration，register-before-use 显式登记——不是第二练习处方）。

1. 组合规则只存在这一份（`learner_state/home_next_step_projection.py`）：
   `到期复（revalidation_queue 有 due probe）> 活跃练（training_intent 有
   active intent 且 target pack 可路由）> 下一学（路线上第一个 未学∧绿灯签发
   的站）> fallback（registry 静态序第一个绿灯站 + 群体理由）`。
   **禁前端/各 tab 再拼一次。** 活跃练的「可路由」= caller 传入的
   `green_lessons` read-model 行上 `绿灯 ∧ retest_available`（现有供给真值，
   禁造第二真值；缺字段与停发同形 fail-closed）。解析不出可路由 target 的
   practice intent **不得胜出**（2026-07-16 QA：F16/X03 停发后空 target 的
   `practice_active` 胜出 → 前端对空 pack fail-closed → 任务卡永久隐藏、
   learn_next 被遮蔽）——跳过落到下一优先级臂，且不静默丢：保留在
   `skipped_intents` diagnostic（仅诊断字段，非第二处方，前端不据此路由）。
   **推荐起点一致性（2026-07-18，A01 冲突包 owner 阻塞治本）**：下一学、
   fallback 两臂在「推荐一个起点」时**必须偏好 `retest_available` 的站**
   （= compiled practice `supply_ready` 单一真值，与活跃练臂同源，禁造第二处方）。
   否则 A01 型冲突包（绿灯可看视频、练习未签发）会被荐为起点，用户看完视频走
   不进练习 → 断链（正是 owner 被 A01 阻塞的现象）。规则：未学站里优先第一个
   supply_ready 的；无一 supply_ready 时**仍回退路线第一个未学站**（视频有价值，
   好过白屏，day-0 不变）；被供给让位的站保留在 `skipped_stations` diagnostic
   （仅诊断，非第二处方，前端不据此路由）。学序（registry+前置边）仍是排序权威，
   本条只在同为未学的候选里按供给真值择优，不改学序 authority、不设前置锁。
2. 输出必须带 `mode / source_authority / source_ref / reason` 四字段——每个
   「下一步」可审计来自哪个权威。
3. 铁律：禁写 ledger、禁生成/修改 `training_intent`、禁改 revalidation 状态。
   它不生成任何「该练什么」的内容判断——练的内容仍完全由 `training_intent`
   说了算，复由 `revalidation_queue`，学序由 registry+前置边。
4. 冷启动兜底：新用户零证据 → 前三臂空 → fallback 必须非空（day-0 不白屏），
   理由文案用群体理由（诚实版，不伪装个性化）。
5. 接入面：home dashboard，受 `DEEPTUTOR_HOME_NEXT_STEP_ENABLED`（默认 off）
   门控；退路（若被证明越权）= learn 只作路线图固有语义。该 flag 是
   「home 生命周期融合面」**总开关**（2026-07-04 owner 拍板）：off = 全走
   旧静态分 + 无 next_step（现状不变）；on = next_step 与 mastery 证据
   blend（首页/雷达/章节盘 `_report_mastery_items` 路径）一起生效——
   不设第二个 blend 专用 flag。内部空态 `mode="unavailable"`
   （`MODE_UNAVAILABLE` / `unavailable_next_step()` 工厂）是投影层哨兵，
   **永不外泄**到 dashboard payload：上层见此 mode 一律不挂 `next_step`。
   范围裁决（2026-07-04，Codex 终审 P2 → 主控裁决）：本条款的「章节盘」=
   `get_mastery_dashboard`（掌握度盘）；`/api/v1/practice/chapter-progress` →
   `get_chapter_progress` 是练习页 legacy 进度列表，**不在本轮融合面内**、
   刻意不受此 flag 门控（其 mastery 字段仍读 member 静态分）。其收口
   （改读单一算子或下线该字段）登记为独立后续工单，不得在无裁决时顺手改。
6. 输入供给禁断供（2026-07-03，Codex SEV-1 治本；2026-07-18 workflow 收权）：caller 组装输入时**禁止
   硬编码空供给**冒充"该权威无输出"。首页接线口径 = 活跃练从同一份
   snapshot events 纯派生处方 outcomes，并只调用
   `prescription_outcome_read_model.requires_active_practice()`；其活跃集合为
   `assigned/in_progress/needs_followup`。closed canonical forward terminal 必须投影为
   workflow `completed`（原始 measurement `not_verified` 保持不变），不得再次进入
   generic practice；`completed/not_verified/verified` 后续均交 `revalidation_queue`，
   同一份 outcomes 必须同时传入 `revalidation_queue`（已验证抑制，与
   learning-report 路径同口径）；claims 从 `read_compiled_learning_truth`
   的 `weak_points` 读取（miss 时空列表如实降级，**不**跑在线 dry-run
   合成——此为对上文 cache-miss 回退条款在首页在线路径的显式最小偏离）。
7. weak_points 聚合保真（同日）：`learning_synthesis` 的 L2 档聚合按
   evidence rank 判定并保留组内最高 level（`L2_real_retest` 不得被字面
   `L2_confirmed` 比较降档）——真懂信号不在聚合层丢失。
8. 证据生命周期的共享 authority 是 `learner_state/evidence_lifecycle.py`：
   `learning_synthesis`、三层学情投影与 learning report 不得分别按 event row 自判
   “重复出现”。重复阈值必须按 distinct authoritative attempt/completion 计算；同一
   completion 的多个 item 永远只算一次。
9. `claim_promotion_allowed=false` 是全读侧 promotion cap。首次四题、当天 forward
   轻练、preview/simulated/low-confidence 证据只能形成 `L0_observed`；不能生成 weak、
   stable、improvement 或 recurring。一次 signed、服务端重判且到期 probe 匹配的
   `L2_real_retest` 可以确认弱点或让同一 rule-group 的旧弱点 stale，但不直接写 mastery。

### Review Due Projection（双轮 §6 复习模块，2026-07-05 登记，`LUBAN_REVIEW_MODULE_ENABLED` 后）

1. finished 课后练习的题干/选项/答案 authoring authority 是 manifest 显式登记的
   `*.practice.dc.html`；构建时 sidecar 与 public HTML 只是带 source/public SHA 的投影。
   未登记文件、source SHA 漂移、public SHA 漂移或不能唯一重判的题型必须 fail-closed，
   不得回退到 public 解析、客户端答案或 signed variant bank 伪装同一供给。
2. 练习完成事实只认服务端重判且满足严格 mode-authority 矩阵的
   `completion_terminal=true` 事件：forward 可接受 `signed_variant_server_rescore` 或
   `compiled_html_server_rescore`，但必须是 `medium/L0_observed/promotion=false`；review
   接受来自唯一 canonical supply resolver 的服务端重判：compiled Pack 只允许 SHA-pinned
   per-Pack Practice v3 eligible/non-revoked artifact 的 `compiled_html_server_rescore`；仅无
   compiled authority 的 legacy/custom Pack 才允许 `signed_variant_server_rescore`，且必须是
   `high/L2_real_retest/promotion=true`。未通过 v3 eligibility/revocation/SHA gates 的 compiled
   HTML 绝不能冒充 review/L2。item append、
   前端收据、本机 storage 和孤立 `station_completed` 都不得推进生命周期或移动复习时钟。
   `station_completed` 继续作为 completion 后的幂等业务信号，但不是 terminal outcome 的
   mirror，也不得复制分数/状态。相同 `retest_completion_id` replay 只算一次。
3. 到期/间隔语义唯一权威=`revalidation_queue`：新学相 `state="fresh"`
   首跳按 **UTC+8 日历日次日**（§6.1 分相最小实现 + §9-D2「天」=日历日，
   「明天见」承诺的调度载体；满 24h 判定被否——昨晚学的今早即到期）。
   §6.1 地平线参数同居本模块：间隔上限 cap ≤14 天恒生效；`exam_date`
   已设且距考 ≤40 天 → 确定性线性压缩、且间隔永不超过距考天数
   （考前一周结构上不可能出现「21 天后复习」）；考后不压缩（队列语义
   切换归后续阶段）。canonical review 成功后按 `mastery_estimator.DECAY_PROFILES`
   的既有 schedule 索引推进（code_application 早期为 3/7/14，仍受 14 天 cap）；失败
   重置 success streak 并回 weak cadence。该 v1 是确定性规则调度，不得冒充 FSRS。
   `exam_date` 唯一读源 = member profile，读侧透传、不复制。
4. pack 级到期投影 `luban_lesson/review_due.py`（GET `/api/v1/luban/review-due`）
   只消费 `pack_lifecycle_projection` 的 terminal facts、做粒度桥接与绿灯 join，零调度
   逻辑（禁第二调度器）；`probe_id` 必须包含当前 cycle anchor，避免旧 verified outcome
   永久抑制新周期；`retest_available=false`
   的站客户端必须 fail-closed 隐藏「换皮」承诺句。
5. `mistake_book` 的 `review_due_at` 是**读侧投影**（`derive_review_due_at`，
   错题=lapse 走 weak 相），零落库、零间隔常量在 mistake_book 内——写侧
   `record_review` 继续清空存量 `review_due_at`（防第二调度权威复活）。
6. 「标记掌握」仍是呈现层旗标（见 `mark_mastered` 条款）。`RetestWritebackService`
   是变体练唯一 completion writer：item 事件只承载不可变作答证据，不得自报 pack 终态；
   全部 item 写成后再追加唯一 `completion_terminal=true` 事件，随后由同一服务写一次
   `station_completed`。页面、handoff 与 API wrapper 不得成为并行 writer。
7. review GET 与 completion 必须绑定 `revalidation_queue` 当前到期的 `probe_id + cycle_anchor`；
   客户端只能提交 probe hint，GET 必须从当前 due projection 精确解析 cycle 后才签发
   self-describing `selection_id v3`，缺 probe、非当前 due、无 cycle 或无可发供给均 fail-closed。
   GET 签发与 completion 复核必须向同一 revalidation projection 透传 member profile 的
   `exam_date` 地平线，不能一边压缩 cadence、一边按无地平线重算 due。
   completion 只解码并信任签名内的 pack/day/mode/exact variants/probe/cycle；客户端自报
   mode/day/probe 不得选择执行 authority。客户端只传选择，服务端按 selection 绑定的供给
   identity 经唯一 lesson supply resolver 重判；compiled Pack 不得回退 signed bank，只有无
   compiled authority 的 legacy/custom Pack 才走 signed bank。forward 永远 non-promoting；review 只允许影响
   `pack:{pack_id}:rule:{rule_group}` 的同粒度概念，不得以 pack 粗粒度清除 sibling 错因。
   普通 compiled forward/fresh-review 选卷只能从 `probe_role="anchor"` 的签发题中抽取；
   `immediate_confirm` 与 `d1_probe` 只能由各自既有 probe supply 主链签发，不得混入普通五题。
   review 的 canonical `training_intent_id` 由服务端恢复为该 `probe_id`，忽略客户端自报 intent/mode；
   取题日使用服务端 UTC+8 日历日。
8. 所有 read projection 必须共用 `evidence_lifecycle` 的 terminal closure，而不是只看同一
   `retest_completion_id` 或 `completion_terminal=true`。canonical terminal 必须精确列出唯一
   `item_event_refs`；每条被引用 item 必须匹配同一 request hash、completion、pack、mode，且题数、
   `max_score`、`score_awarded` 与正确数可重算一致。只有 closure 引用的 item 可以进入 weak、
   improvement、typed graph、三层学情、report、pack lifecycle、prescription outcome 或 replay；
   同 completion 的孤儿 item 与 partial append 必须 fail-closed，不得移动复测时钟或形成 verified。
   当前 Luban retest 只允许单选/判断的逐题二元 1 分制：item `max_score=1`、`score_awarded∈{0,1}`
   且必须与 `is_correct` 一致；NaN/Infinity、损坏分数、加权题或部分给分不得静默进入该 closure。
   未来支持加权题必须先升级 scoring contract，不能把容差 fallback 塞进现有 reader。
   `evidence_lifecycle` 还必须用签发的 `cycle_anchor` 区分普通 forward 与
   `immediate_confirm`：空 anchor 只恢复至少含一题 `anchor` 且角色全集属于
   `{anchor, immediate_confirm, d1_probe}` 的历史错误混签闭合；全 `immediate_confirm`
   仍保持 confirm 身份并要求 parent，全 `d1_probe`、空白或未知角色 fail-close；只有普通 forward 能开启新 cycle，确认题不得重置
   `last_completion_at/review_cycle_anchor/successful_review_streak`，也不得单独把
   prescription workflow 关闭为 completed。confirm GET 必须携带上一轮 canonical forward
   terminal receipt；服务端复核其仍是该 pack 最新 forward 且 confirm facts 是该 closure
   错题 facts 的非空子集后，才把 parent terminal 签入 selection `cycle_anchor`。completion
   必须在任何 append 前按同一 evidence authority 复核 parent；旧设备迟交、篡改 parent、
   同 fact 新 episode 覆盖或历史无 parent confirm 均不得完成现代 journey。v3
   review 必须逐次 exact-match 当前 `cycle_anchor`，两个 reader 不得各自按时间猜 episode。
   `LUBAN_REVIEW_MODULE_ENABLED`（以及 forward 的 `LUBAN_LIGHT_PRACTICE_ENABLED`）必须在任何
   append 前 fail closed，禁止“写完 terminal 才撞 rollout flag”。
9. GET 取题必须签发 `selection_id`，绑定 canonical user、pack、服务端 UTC+8 day、mode 与
   variant ID 集合；review 额外绑定服务端解析的 `probe_id + cycle_anchor`；
   immediate-confirm forward 额外绑定服务端验证的 parent-terminal `cycle_anchor`。POST 必须验证该
   identity 后才按原签发日重建并重判。这样跨午夜/断网
   retry 仍消费同一题组，同时客户端不能改 day、换题或跨用户复用 selection。
10. 最近 8 天窗口只允许用于趋势/timeline。`pack_lifecycle` 与 pack review 必须读取分页后的
   全历史 `learning_evidence` 窄事件流；不得被 8 天、100/200/500 条页面窗口或 PostgREST
   单页 row cap 截断。`learning_report_read_model.v2.pack_review` 是学习/复习/学情共用的
   聚合切片，页面不得再各拉一份 learner-state 到期读模型。
11. 今日进度的单位是题目作答：item event 可以计数，completion terminal 只是提交边界，
    必须带 `quality.progress_countable=false`，读侧也必须识别并排除历史 terminal。五题练习
    只增加 5 题，不能因 terminal 或 `station_completed` 变成 6。
12. review 的并发唯一事实由 PostgreSQL RPC `claim_luban_retest_probe` 在既有
    `learner_memory_events.dedupe_key` 唯一索引上原子 insert-or-read；claim identity 是
    canonical JSON `[user_id, probe_id, cycle_anchor]` 的 SHA-256，不允许冒号拼接歧义，
    不新建平行表。`semantic_request_hash = signed selection identity + normalized answers`，
    明确排除客户端随机 `completion_id`。不同 hash 冲突；同 hash 的 durable winner completion
    可在 claim 后 crash 时以相同 completion ID 幂等 resume；其他 completion 只能读取 winner
    terminal，terminal 尚未 durable 时返回 retryable in-progress，绝不能偷写或把 pending 当成功。
    同 winner completion 的 claim/item/terminal 事件 ID 必须由 dedupe key 稳定派生，保证两个
    worker 的同语义 owner retry 不能让 terminal 引用另一组随机 item IDs、破坏 closure。
    winner terminal 读取必须走 `read_luban_retest_completion_events` 直读 RPC 绕过 20 秒通用缓存。
    未配置/失败的原子 claim 在任何 review item/terminal 写入前返回 unavailable；JSONL 和异步
    outbox 不得充当 claim authority。forward 保持现有 completion 路径，不参与 probe claim。

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
2. 目录页只能读取 `assessment_forms` 的轻量元数据（active form count、
   `fallback_used`、`question_bank_size`），不得串行加载 `items_json` 或在列表页重跑
   persisted form-bank validator。完整 validator（跨 form `source_question_id` /
   `semantic_signature` 去重、每套题量与 section floor）属于预生成 / 持久化和
   `create_assessment` 出卷路径：
   - `stable`: active forms >= 5 且 `fallback_used=false`
   - `pilot`: active forms >= 3 and < 5 且 `fallback_used=false`
   - `authoring_needed`: active forms < 3，或 active forms 来自 fallback form bank
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

### First Run Diagnostic Completion Contract

首次体验是五模块「学习」首页的第一段学习旅程，不是独立 onboarding authority。正式完成
只允许走 `POST /api/v1/first-run/complete -> FirstRunWritebackService ->
learner_memory_events(memory_kind=learning_evidence)`；中途状态只允许保存在按 canonical user
隔离的客户端 checkpoint，不建立第二套服务端 session 或推荐表。

1. `first_run_script.v1` 是四道静态题的唯一内容与答案 authority。每题必须有稳定
   `question_id`、source refs、content hash 与两条独立教研 review refs；任一题未 signed 时
   completion 必须 fail closed，前端 `script-data.js` 只能是 hash-pinned 展示镜像。
2. 客户端 completion 只能提交 `completion_id`、`script_version`、`completed_at`、四条
   `question_id/selected_key/duration_ms` 与显式偏好；禁止提交正式 score、correct、mastery、
   error code、training intent 或 home next step。
3. `FirstRunWritebackService` 必须按 signed manifest 重新判定，并为每题写一条
   `source_feature=first_run_diagnostic`、`memory_kind=learning_evidence` 事件；不得让 mobile
   adapter 或页面直接拼 learner event。
4. 幂等键固定包含 canonical `user_id + completion_id + script_version + question_id`。
   同一 completion 同 body 重放返回既有事件；同一 completion 不同 body 在任何额外写入前
   返回 `first_run_idempotency_conflict`。中断后重试允许补齐缺失事件，但不得重复证据。
5. 四题只形成低置信起点证据：所有 event 必须
   `mastery_promotion_allowed=false`、`official_score_allowed=false`；不得宣称稳定掌握、
   完整能力或长期人格。
   错题以 registered `unknown_error` 形成可见 `L0_observed`，正确题只保留 clean baseline；
   四条 item row 仍属于同一个 completion，绝不能因题目数量达到 L1。
6. 学习时段、记忆方式、备考阶段等用户选择只能合并到既有 profile 的显式 preference，
   并标记 `source=explicit_first_run_v1`；“画面派/稳手”等推断画像只允许作为报告解释，
   不能覆盖 profile truth。
7. 训练方向只允许由既有 `build_learning_training_intent()` 生成，首页继续只读消费
   `home_next_step_projection`。first-run wrapper 不得按错题数另写一套正式推荐。
   question→pack 映射必须由 source-backed resolver 与当前 green+signed-retest supply 共同
   验证；映射不写进仅绑定题面 hash 的 manifest。映射表为每题声明**有序候选序列**
   （source-backed 教研映射，可扩），resolver 取第一个 supply-ready
   （`绿灯 ∧ retest_available` read-model 真值）的候选——不硬编码任何 pack 字面
   特权；候选全不可用时诚实返回无 pack 绑定（空 target），不臆造第二真值。
   处方只能引用 focus item evidence，
   `training_intent_id/probe_id` 是来源身份，进入站点必须另读 `target_pack_id`。
8. 本地 DONE 只是 UI cache。只有服务端 writeback 成功才算 canonical 完成；弱网时报告可先
   展示，但必须标为待同步，并使用同一个 `completion_id` 重试。
9. 旧 assessment / chat onboarding 只能作为兼容消费者：它必须从
   `learner_state.learning_preferences.first_run` 只读投影 canonical 完成事实，完成后不得再
   弹第二套摸底入口。禁止为了抑制弹窗新增第二个 completion writer、mirror table 或仅依赖
   跨设备失效的 local flag。
10. canonical first-run completion marker 必须最后提交：item evidence 与 home projection
    成功后才能合并 `learning_preferences.first_run`。home projection 失败时不得留下“已完成但
    没有下一站”的半提交状态；同 completion 重试复用已有 item evidence 后继续收口。

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

## QA/内部账号 allowlist 导出（2026-07-02）

`MemberConsoleService.list_internal_test_user_ids()` 是 QA/内部账号名单的**唯一读权威**（spike D1 度量与 D15 埋点读侧共用）：判据复用 `_looks_like_test_member`，优先识别 `account_kind='eval_runner'`、`actor_type='machine'`、`created_by='eval_runner'`、`is_internal_test=true` 等显式机器身份，再使用旧账号名 marker 兜底；禁止在度量脚本里另建启发式名单（`turns>50` 等只能作对照披露）。实现注意：不得经 `_load_member_directory_members_for_bi` 取数——其 BI 过滤会先剔除测试账号，生产恒为空集；必须遍历本地 store + Supabase directory 原始成员。该导出是只读投影，不是第二 identity authority——identity 仍按 `canonical_uid` 单点。
