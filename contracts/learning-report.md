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
| `quality_signals` | `dict` | 质量指标（dedupe 后，Task 0 已实施） | stable |
| `learning_brain` | `dict \| None` | 学习大脑 projection | stable |
| `source_meta` | `dict` | 各数据源耗时与状态 | stable |
| `error_labels` | `dict[str, str]` | 错误类型枚举映射 | stable |

### v2 Schema（dual-emit 计划，见 plan §7 Stage 5）

v2 新增字段（Task 1-5 实施后逐步引入）：

| 字段 | 类型 | 含义 | 引入阶段 | 状态 |
|---|---|---|---|---|
| `schema_version` | `int` | 切换为 `2` | Stage 5 | planned |
| `attempt_detail` | `dict \| None` | 单次 attempt 详情视图 | Task 1 | planned |
| `mistake_book_summary` | `dict \| None` | 错题集统计摘要 | Task 3 | planned |
| `training_intent` | `dict \| None` | 当前训练意图推断结果 | Task 2 | planned |
| `home_projection` | `dict \| None` | 个性化 home dashboard projection | Task 4.6 | planned |
| `conversation_evidence` | `list[dict]` | conversation synthesis 产出的学习证据 | Task 4.5 | planned |

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

---

## 4. Conversation Evidence 封闭枚举

### `learning_signal_type`（封闭枚举）

所有 conversation 类学习信号必须继续写入 `learner_memory_events` 的既有大类：

- `event_type="learning_evidence"`
- `memory_kind="learning_evidence"`
- `payload.evidence_source="conversation_synthesis"`

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
