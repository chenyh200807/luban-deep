# Learning Report Contract

## 范围

这一份 contract 管：

- `learning_report_read_model`：唯一 producer，唯一 schema authority
- `attempt_detail_read_model`：单次 attempt 详情只读视图
- `mistake_book`：错题集写路径与查询接口
- `training_intent`：意图推断与训练目标追踪
- `home_personalization`：home dashboard 个性化 learning projection
- conversation evidence 事件的封闭枚举词汇表

本文件是上述模块的**唯一设计契约**。任何新增字段、重命名、删除字段，必须先更新本文件，并在 PR description 中显式列出 contract diff。

---

## 1. Read Model Authority

### 单一 Producer

| 资源 | 唯一 producer 函数 | 所在文件 |
|---|---|---|
| Learning Report | `build_learning_report_read_model` | `deeptutor/services/learner_state/learning_report_read_model.py` |
| Learning Brain | `build_learning_brain_read_model` | `deeptutor/services/learner_state/learning_brain_read_model.py` |
| Attempt Detail | `build_attempt_detail_read_model`（Task 1 实施） | `deeptutor/services/learner_state/attempt_detail_read_model.py` |

**硬约束：**

1. 任何路由或服务层不得绕过上述 producer 函数，直接读取底层数据并自行组装 learning report 字段。
2. Producer 函数是 pure function（给定相同输入返回相同输出），不得在函数内部执行写操作。
3. Read model 生命周期：按需计算，不做持久化（除非有明确 cache 策略）。

---

## 2. Schema 字段矩阵

### v1 Schema（已上线，稳定）

`build_learning_report_read_model` 的返回结构 v1：

| 字段 | 类型 | 含义 | 状态 |
|---|---|---|---|
| `schema_version` | `int` | 当前 = `1` | stable |
| `generated_at` | `str` (ISO 8601) | 报告生成时间（UTC+8） | stable |
| `user_id` | `str` | 学员标识 | stable |
| `today_progress` | `dict \| None` | 今日练习进度快照 | stable |
| `home_dashboard` | `dict \| None` | 首页 dashboard 汇总 | stable |
| `assessment_profile` | `dict \| None` | 测评画像 | stable |
| `mastery_dashboard` | `dict \| None` | 掌握度 dashboard | stable |
| `mastery` | `dict` | 学情页掌握度 projection；由 read model 统一投影，包含 `knowledge_summary` | stable |
| `quality_signals` | `dict` | 质量指标（dedupe 后，Task 0 已实施） | stable |
| `learning_brain` | `dict \| None` | 学习大脑 projection | stable |
| `training_prescription` | `dict` | `training_intent` 的学员可见训练处方 projection | active |
| `station_journey` | `dict` | v1/v2 共用的 additive 六步只读投影；nested `schema_version=1`，不改变父报告协商版本 | active |
| `source_meta` | `dict` | 各数据源耗时与状态 | stable |
| `error_labels` | `dict[str, str]` | 错误类型枚举映射 | stable |

### v2 Schema（dual-emit，见 plan §7 Stage 1 / Stage 5）

`GET /api/v1/mobile/learning-report` 默认返回 v1；新客户端必须通过
`?schema_version=2` 或 `Accept: application/vnd.deeptutor.learning-report+json;v=2`
显式协商 v2。v2 响应必须保留 v1 顶层字段，并并行输出 v2 顶层字段；不得在
同一个 PR 中删除 v1 字段。

v2 新增字段（Task 1-5 实施后逐步引入）：

| 字段 | 类型 | 含义 | 引入阶段 | 状态 |
|---|---|---|---|---|
| `schema_version` | `int` | 切换为 `2` | Stage 1 | active |
| `recent_attempts` | `list[dict]` | v1 字段，等同 `learner_facing.recent_attempts` | Stage 1 | dual-emitted |
| `timeline` | `list[dict]` | v1 字段，等同 `learner_facing.evidence_timeline` | Stage 1 | dual-emitted |
| `training_loop_cards` | `list[dict]` | v1 字段，等同 `learner_facing.training_loops` | Stage 1 | dual-emitted |
| `attempts` | `list[dict]` | v2 单次 attempt 卡片，包含 `attempt_ref`、诊断和操作可用性 | Task 2 | active |
| `hero` | `dict` | 学情页 hero projection；`primary_cta.intent` 必须来自 training intent authority | Task 4 | active |
| `mistake_book` | `dict` | 错题集只读 projection；读 `learner_mistake_book_items`，不得在 read model 写入 | Task 3 | active |
| `next_training` | `list[dict]` | 下一步训练卡片；intent 由 `training_intent.py` / read model projection 生成 | Task 4 | active |
| `training_prescription` | `dict` | `training_intent` v2 的学员可见处方：主题、错因、题目顺序、成功标准 | Task 4 / Batch C | active |
| `home_personalization` | `dict` | 首页个性化 projection；复用 `home_dashboard.today_focus/recommended_prompts` | Task 4.6 | active |
| `mastery.dimensions` | `list[dict]` | 掌握度维度；包含 score/status/confidence，但不得伪装成稳定真相 | Stage 1 | active |
| `mastery.knowledge_summary` | `dict` | taxonomy/textbook-directory 知识地图摘要；只表达教材目录覆盖和证据定位，不等同 mastery truth | Stage 1 | active |
| `i18n_keys` | `dict` | v2 UI copy key，当前 locale=`zh-CN` | Stage 1 | active |
| `pack_lifecycle` | `dict` | 全历史 terminal/evidence 派生的 pack 状态；最近窗口不得截断该状态 | 五模块闭环 | active |
| `pack_review` | `dict` | `pack_lifecycle_projection -> revalidation_queue` 的 pack 级到期切片；学习、复习、学情共用 | 五模块闭环 | active |
| `overview.due_today_count` | `int \| null` | 只镜像 `pack_review.due` 数量；排程不可用时必须为 `null`，不得回退 member-console 旧计数 | 五模块闭环 | active |
| `overview.due_today_state` | `known \| disabled \| unavailable` | 区分真 0、旗标关闭与数据源失败；客户端不得把 unavailable 渲染成全清/稳定 | 五模块闭环 | active |

`freshness.event_count/window_truncated` 只描述最近趋势窗口；不得被解释为 lifecycle
历史完整性。生产 full-history evidence reader 必须分页直到短页。客户端学情缓存只能是
按 canonical `user_id` 分区、带 envelope user 校验的可丢 UI cache；无当前 user、账号切换
或 envelope 不匹配时禁止 hydrate，任何 token invalidation 必须清除当前用户快照；异步响应
落地前还必须复核 request generation 与当前 canonical user，防止账号切换后的迟到响应瞬时串号。

v2 `authority` 必须额外声明以下来源，供前端和 QA 验证 single authority：

| 字段 | 固定含义 |
|---|---|
| `conversation_source` | `learner_memory_events.learning_evidence[evidence_source=conversation_synthesis]` |
| `attempt_detail_source` | `attempt-detail-read-model` |
| `mistake_book_source` | `learner_mistake_book_items` |
| `training_intent_source` | `learning-report-read-model` |
| `home_context_source` | `home_dashboard.today_focus/recommended_prompts` |
| `knowledge_map_source` | `taxonomy_index/textbook_directory + learning-report-read-model evidence/mastery projection` |
| `pack_review_source` | `pack_lifecycle_projection -> revalidation_queue` |
| `station_journey_source` | `station_journey_projection.read_model` |

**v1 Retirement 计划：**

- v1 与 v2 dual-emit 期间（Stage 5），两个版本同时产出，由客户端 `schema_version` 字段区分。
- v1 完全 retire 时间：不早于 v2 灰度覆盖率 >= 95% 且稳定运行 2 周后。
- Retire 决策必须有独立 PR，并更新本文件的 retirement 状态。

---

## 3. 子模块 Owner 与稳定边界

### 3.1 Attempt Detail Read Model

- **Owner 文件**：`deeptutor/services/learner_state/attempt_detail_read_model.py`（Task 1 实施）
- **用途**：以 `attempt_ref`（opaque token）为主键，提供单次作答的只读详情视图
- **公开 endpoint**：`GET /api/v1/mobile/learning-attempts/{attempt_ref}`
- **稳定边界**：
  - 只读，不写；不得在 read model 内修改任何持久化状态
  - `attempt_ref` 是签名 token（HMAC-SHA256），其 secret = `DEEPTUTOR_ATTEMPT_REF_SECRET` 环境变量
  - 解码失败由 read model 返回 `ok=false`，router 只映射为 404，不在 router 里拼装字段
  - `LearnerStateService.read_learning_evidence_event(user_id, event_id)` 是唯一 indexed reader；禁止生产路径 `list_learning_evidence_events(...limit=500)` 后 filter
  - read model 可用 `payload.session_id` / `payload.turn_id` 回查既有会话历史中的 assistant 消息，作为"当时系统解析" raw replay source；这不是新的 learning authority，归一化学习事实仍以 `learner_memory_events.learning_evidence` 为准
  - 当历史 assistant 消息与短 `payload.explanation` 同时存在时，attempt detail 必须优先展示历史 assistant 完整解析；找不到历史消息时才降级到 payload summary
  - 响应不得暴露 raw `event_id`；用户可见引用只使用 `attempt_ref`

### 3.2 Mistake Book

- **Owner 文件**：`deeptutor/services/learner_state/mistake_book.py`（Task 3 实施）
- **数据库表**：`learner_mistake_book_items`（见 §5 Migration）
- **公开 endpoints**：
  - `GET /api/v1/mobile/mistake-book`
  - `POST /api/v1/mobile/mistake-book/items`
  - `DELETE /api/v1/mobile/mistake-book/items/{attempt_ref}`
  - `POST /api/v1/mobile/mistake-book/items/{attempt_ref}/mastered`
  - `POST /api/v1/mobile/mistake-book/items/{attempt_ref}/review`
- **稳定边界**：
  - 写路径受 `DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED` flag 保护
  - 读路径受 `DEEPTUTOR_MISTAKE_BOOK_ENABLED` flag 保护
  - 主键为 `(user_id, event_id)`，防重复写入
  - `mastered_at` 非空表示已掌握；`archived_at` 非空表示已归档；过滤索引已覆盖
  - mutation 必须支持 `If-Match` / `etag` 冲突检测；409 响应携带 latest server state
  - learning report 只能读取 bookmark projection 并输出 `is_bookmarked/bookmark_label`，不得在 read model 中写错题

### 3.3 Training Intent

- **Owner 文件**：`deeptutor/services/learner_state/training_intent.py`（Task 4 实施）
- **用途**：从 conversation evidence 推断学员当前训练意图
- **稳定边界**：
  - 结果为 pure projection，不写入持久化层
  - 推断依赖的输入只能来自已有 learner_state / evidence，不得调用外部 LLM（除非明确 flag 开启）

### 3.4 Home Personalization

- **Owner 文件**：`deeptutor/services/learner_state/home_personalization.py`（Task 4.6 实施）
- **用途**：为 home dashboard 提供基于 learning projection 的个性化内容
- **稳定边界**：
  - 受 `DEEPTUTOR_HOME_PERSONALIZATION_ENABLED` flag 保护
  - 不得替代或覆盖 `home_dashboard` v1 字段；只作为 v2 新增字段 `home_projection` 产出
  - dashboard 请求路径只允许读取既有 learner snapshot / progress / profile 中的 `home_personalization` projection；不得在请求路径里实时调用 `learning_report_read_model` 或用 `weak_nodes` 现场合成个性化推荐
  - projection 缺失或 `generated_at` 超过 6 小时时只能降级为 seed starter fallback；对外 `source_status.learning_report="stale"`，具体原因写入 `source_status.fallback_reason`
  - starter fallback 必须来自 `data/seed/<subject_id>/starter_prompts.json`，不得在代码里维护第二套 `_STARTER_PROMPTS` 静态池
  - `recommended_prompts[].intent` 通过 mobile `prompt_intent` 回传后，只能写入 `learning_evidence` 的 conversation synthesis payload；前端不得自行推导 weak point / mastery / next training。

### 3.5 Truth Sections

- **Owner 文件**：`deeptutor/services/learner_state/learning_report_read_model.py`
- **用途**：把单次观察和稳定结论分开展示
- **稳定边界**：
  - `truth_sections.recent_observations` 承载 L0、conversation exposed、still confused 等低置信信号
  - `truth_sections.stable_truths` 只承载重复出现或已确认的 grading evidence
  - `truth_sections.needs_confirmation` 承载字段缺失、矛盾 evidence、manual correction 冲突
  - UI 不得把 recent observation 文案包装成稳定掌握结论

### 3.6 Training Prescription Projection

- **Owner 文件**：`deeptutor/services/learner_state/learning_report_read_model.py`
- **唯一处方 authority**：`deeptutor/services/learner_state/training_intent.py`
- **用途**：把 `training_intent` v2 的处方流水投影成学员可读的训练主题、错因理由、题目顺序和成功标准。
- **稳定边界**：
  - `training_prescription.source` 固定为 `training_intent`；不得由前端、home dashboard 或 legacy study_plan 另算处方。
  - `display_topic` 必须来自可诊断学习证据；prompt-like 文案（例如“我想练习…出题”“那出5道题”“training_mode=…”）不得展示为训练主题。
  - 证据不足时必须 `status=degraded`，展示起步测评/补证据，不得伪装成专项题。
  - `study_plan` 只能读取 `training_prescription` 或已有安全 projection；不得反向覆盖 `training_intent`。

### 3.7 Knowledge Summary Projection

- **Owner 文件**：`deeptutor/services/learner_state/learning_report_read_model.py`
- **唯一目录 authority**：`deeptutor/services/taxonomy/textbook_directory.py`、`taxonomy_tree_stats()` 与 taxonomy resolver/index
- **用途**：把全局 taxonomy 节点数、叶子节点数、13 章教材目录和已有学习证据定位成学情页可读的知识地图。
- **稳定字段**：

| 字段 | 类型 | 含义 |
|---|---|---|
| `mastery.knowledge_summary.total_nodes` | `int` | taxonomy 总节点数 |
| `mastery.knowledge_summary.coded_nodes` | `int` | 有 code 的原始 taxonomy 节点行数；当前为 3733，不等同唯一 code 数 |
| `mastery.knowledge_summary.leaf_nodes` | `int` | 最细知识点数量 |
| `mastery.knowledge_summary.unique_codes` | `int` | 原始 taxonomy 中唯一 code 数；当前为 1284 |
| `mastery.knowledge_summary.duplicate_code_rows` | `int` | 重复 code 行数；用于解释为什么唯一 code 少于带 code 节点 |
| `mastery.knowledge_summary.total_textbook_chapters` | `int` | 教材章数，当前建筑实务为 13 |
| `mastery.knowledge_summary.evaluated_topics` | `int` | 已被 evidence/mastery 输入定位到的主题数 |
| `mastery.knowledge_summary.evaluated_leaf_points` | `int` | 已定位的叶子知识点数 |
| `mastery.knowledge_summary.mastered_topics` | `int` | 当前 projection 中状态为 strong 的主题数 |
| `mastery.knowledge_summary.developing_topics` | `int` | 当前 projection 中状态为 normal/observed 的主题数 |
| `mastery.knowledge_summary.weak_topics` | `int` | 当前 projection 中状态为 weak 的主题数 |
| `mastery.knowledge_summary.unmeasured_leaf_points` | `int` | 尚未被 evidence 定位的叶子知识点数 |
| `mastery.knowledge_summary.textbook_chapters[]` | `list[dict]` | 按教材目录排序的章级进度 |

`textbook_chapters[]` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `chapter_no` | `int` | 教材章号 |
| `chapter_name` | `str` | 展示章名，形如 `第1章 建筑工程设计技术` |
| `section_count` | `int` | 该章目录小节数 |
| `evaluated_topics` | `int` | 该章已定位主题数 |
| `mastered_topics` | `int` | 该章 strong 主题数 |
| `developing_topics` | `int` | 该章 normal/observed 主题数 |
| `weak_topics` | `int` | 该章 weak 主题数 |
| `top_topics` | `list[str]` | 最多 3 个已定位主题名 |
| `status` | `unseen \| developing \| weak \| strong` | 章级展示状态 |

**硬约束：**

1. `knowledge_summary` 是只读 projection，不写 learner-state，不新增第二套 `knowledge_map_progress` / `textbook_progress` authority。
2. 全量节点统计必须来自原始 taxonomy outline 或 compiled artifact 中固化的 `source.stats`，不得用 `nodes_by_code` / 去歧义检索索引反推总节点或叶子节点。
3. `evaluated_topics` 表示“已定位/有证据”，不得解释成“已掌握”。
4. 教材章节覆盖率不得直接作为全局 mastery；全局 mastery 仍由 `mastery.overall_mastery` 按 evidence sufficiency 产出。
5. 前端只能做 snake_case 到 camelCase 的展示适配，不得自行计算 `textbook_chapters` 或从题数推导 chapter status。

### 3.8 Station Journey Projection

- **Owner 文件**：`deeptutor/services/learner_state/station_journey_projection.py`
- **唯一 producer**：`build_learning_report_read_model` 以内嵌 additive 字段 `station_journey` 输出；不新增 endpoint 或平行 report schema。
- **父 schema 归属**：该字段是默认 v1 与显式 v2 的共用 additive 字段；nested `schema_version=1` 只版本化六步结构，不代表客户端协商了 learning-report v2。
- **事实来源**：`lesson_viewed`、`evidence_lifecycle` 验证后的 retest terminal closure、`pack_review` 的 exact due item。
- **稳定边界**：
  - 只读、零持久化、零调度、零 CTA；`home_next_step_projection` 仍是唯一 CTA 仲裁，`revalidation_queue` 仍是唯一到期语义。
  - `practice_mode=forward` 不足以判定新周期；closure items 全为 `probe_role=immediate_confirm` 时只能形成同周期确认事实，不得移动 `review_cycle_anchor`。
  - `evidence_lifecycle.canonical_retest_episode_records` 是唯一 episode binding：confirm facts 必须是本轮错题 facts 的非空子集，且 confirm terminal 的签名 parent `cycle_anchor` 必须等于该 forward terminal；同 fact 的旧设备迟交不得吸附到新 episode。v3 review 的 `cycle_anchor` 必须逐次精确绑定当前 terminal。旧版无 anchor review 只在完整 legacy episode 内兼容，不能挂到 v3 episode。
  - pack `journey_state=active|completed|unavailable`；只有 active 允许非空 `current_step_id`，且该步必须是 `current|scheduled`。排程不可用时不得把 unavailable 步骤称为“当前”。
  - 五题全对时 diagnosis/confirm=`not_applicable`；有错但历史 `fact_id` 或当前安全供给不足时 confirm=`unavailable` 且 non-blocking，禁止按当前题库回填猜测。
  - `completed` 只表示对应 episode 已有 canonical terminal/receipt，不表示 mastered；讲评完成只表示服务端已签发 canonical feedback，不声称用户已阅读。
  - learner events 不可用、authority/schema/pack 不匹配时客户端必须显示 unavailable，不得用 `next_step.mode`、本地点击或缓存零值猜 1/2/5。

---

## 4. Conversation Evidence 封闭枚举

### `learning_signal_type`（封闭枚举）

所有 conversation 类学习信号必须继续写入 `learner_memory_events` 的既有大类：

- `event_type="learning_evidence"`
- `memory_kind="learning_evidence"`
- `payload.evidence_source="conversation_synthesis"`
- `payload.subject_id`：当前学科隔离键，可为空但不得由前端推导后替代 learner-state authority
- `payload.training_intent_id`：可为空；若来自 learning report/home prompt intent，必须原样透传，便于后续 training improvement 对齐
- `payload.user_question_redacted=true|false`：写入前必须完成 PII redaction

不得新增 `conversation_learning_evidence` 之类的第二个 event type 大类。

当且仅当 `payload.evidence_source="conversation_synthesis"` 时，`payload.learning_signal_type`
只能取以下值：

| 值 | 含义 |
|---|---|
| `answer_explanation` | 答后解析或讲评被用户消费 |
| `concept_explain` | 用户请求或获得概念解释 |
| `mistake_explain` | 用户围绕错因继续追问或复盘 |
| `still_confused` | 用户明确仍困惑，不能提升 mastery |
| `home_prompt_clicked` | 用户点击首页学习推荐 prompt |

### `evidence_source`（封闭枚举）

| 值 | 含义 |
|---|---|
| `conversation_synthesis` | 来自 conversation synthesis pipeline |
| `heartbeat_writeback` | 来自 heartbeat writeback |
| `direct_assessment` | 来自直接测评（quiz/exam） |
| `guide_evaluation` | 来自 guide 评估 |
| `construction_grading` | 来自建筑实务批改/作答 writeback |

**硬约束：**

1. 任何新增枚举值必须先更新本文件，并在 PR description 中显式列出。
2. 禁止在业务代码中使用字符串字面量替代枚举值（必须引用枚举类或常量）。
3. Conversation evidence 不得直接提升 mastery；`still_confused` 必须进入 recent observation / needs confirmation，而不是 stable truth。
4. `learning_prompt_intent` 不是 conversation evidence 的唯一触发条件；普通学习答疑、概念讲解、错因追问、仍困惑信号只要通过 learner-state helper 的质量门槛，也必须写入同一个 `learning_evidence` ledger。

---

## 5. Migration 登记

| Migration 文件 | 内容 | 状态 |
|---|---|---|
| `supabase/migrations/20260521000100_learner_mistake_book_items.sql` | `learner_mistake_book_items` 表 + RLS | Task 0.5（本 PR） |

---

## 6. Contract 修改纪律

1. **任何新增字段**：必须更新 §2 字段矩阵，并注明引入阶段与状态。
2. **任何删除字段**：必须先将状态改为 `deprecated`，保留至少一个版本周期，再删除。
3. **任何枚举值变更**（§4）：必须更新枚举表，并在 PR description 中显式列出 contract diff。
4. **任何新增 migration**：必须在 §5 登记。
5. **任何更改 producer 函数签名**：必须更新 §1，并同步更新 `contracts/index.yaml` 的 `schema_files`。
