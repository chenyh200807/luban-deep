# 建筑实务 AI 互动课堂架构与实施收口 v1.2

> 状态：**canonical**
>
> 自 2026-04-22 起，本文件是 `docs/openmaic/` 下关于建筑实务 AI 互动课堂的**唯一收口文档**，负责解决 v1.0 / v1.1 文档之间的 authority、transport、状态机、对象命名和 MVP 边界漂移。旧 `doc/openmaic/` 路径只作为历史路径，不再新增内容。
>
> 若本文件与以下文档冲突，以本文件为准：
>
> - [建筑实务AI互动课堂_技术实现蓝图_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_技术实现蓝图_v1.1.md)
> - [建筑实务AI互动课堂_实施任务拆解_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_实施任务拆解_v1.1.md)
> - `建筑实务AI互动课堂_Implementation_Plan_v1.0.docx`
> - `建筑实务AI互动课堂_PRD_v1.0.docx`

> 配套文件：
>
> - [README.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/README.md)
> - [建筑实务AI互动课堂_Implementation_Plan_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)
> - [ADR-001-lesson-ir-authority.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-001-lesson-ir-authority.md)
> - [ADR-002-classroom-turn-transport.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-002-classroom-turn-transport.md)
> - [ADR-003-quality-evaluation-release-gate.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-003-quality-evaluation-release-gate.md)
> - [ADR-004-source-ingestion-provenance.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-004-source-ingestion-provenance.md)
> - [ADR-005-mini-program-surface-renderer-contract.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md)
> - [ADR-006-supabase-knowledge-base-reuse.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md)
> - [banned-v1.1-patterns.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/banned-v1.1-patterns.md)

---

## 0. 这份文档解决什么问题

上一轮文档的主要问题，不是“想法不够多”，而是**系统边界不够单一**：

- 课堂问答被写成了第二套 transport。
- `Lesson IR`、拆分表、导出结构同时被当成 primary truth。
- `classroom / course`、`lesson.json / course.json`、审核状态机在三份文档里并行演化。
- “新增 exam_classroom capability”被当成默认前提，但没有先证明这真的是一个新 capability，而不是一个新产品表面。

本文件的目标是把这些问题一次收口为：

1. 一个业务事实
2. 一个 authority
3. 一套状态机
4. 一套命名
5. 一条 P0 可交付主链路

---

## 1. Root-Cause 结论

### 1.1 One Business Fact

系统真正要稳定维护的唯一业务事实是：

> **存在一份可生成、可播放、可审核、可导出的建筑实务课堂真相，并且这份真相必须与 DeepTutor 现有 turn / capability / learner-state contract 共存，而不能再长第二套 transport、第二套运行时 authority、第二套长期状态。**

### 1.2 One Authority

当前条件下的最小正确 authority 设计为：

- **课程内容真相**：`exam_classrooms.lesson_ir`
- **异步执行真相**：`classroom_jobs`
- **导出任务真相**：`classroom_exports`
- **学员作答真相**：`question_attempts`
- **审核发现真相**：`review_items`
- **课堂问答 transport 真相**：统一 `/api/v1/ws`
- **长期学员进步真相**：沿用 learner-state contract 的 `user_stats` / `learner_memory_events`，由统一 writeback pipeline 写入
- **来源治理真相**：`source_manifest` + source chunk metadata，由 `SourceIngestionService` 写入
- **知识召回真相**：既有 `RAGService` + `construction-exam` 默认知识库绑定；Supabase `kb_chunks / questions_bank` 只能通过 RAG evidence 进入课堂
- **质量评测真相**：`quality_report`，由 `LessonQualityEvaluator` 写入，`review_items` 只做 issue projection
- **学员端主产品表面**：微信小程序 `wx_miniprogram`
- **宿主交付表面**：`yousenwebview/packageDeeptutor`
- **跨端渲染解释真相**：`Scene Runtime Core`，负责解释 scene/action/block/question 语义；各平台 adapter 只做映射

### 1.3 Concepts To Delete Or Demote

本次明确删除、降级或归一化以下概念：

- 删除“课堂问答独立 transport”这个想法，不再设计 `/ask` 作为实际流式问答主链路
- 降级“exam_classroom capability”这个说法：P0 默认它是**产品表面与领域模块**，不是自动成立的新 runtime capability
- 删除 `classroom / course` 并行命名：对外领域对象统一叫 `exam_classroom`
- 删除 `lesson.json / course.json` 并行命名：导出包中的 canonical 内容文件统一叫 `lesson.json`
- 删除 `TeachStudio` 作为主决策概念：它只允许作为历史命名或展示别名，不再参与架构 authority
- 删除多套审核生命周期：`ai_checked / source_verified` 只保留为 review evidence，不再作为持久生命周期状态
- 删除 `classroom_scenes / classroom_actions / exam_questions` 作为 P0 primary truth 的设计；如需查询优化，只允许做 read projection

### 1.4 Product North Star

P0 的北极星不是“复刻 OpenMAIC 功能广度”，而是：

> **一键生成高质量建筑实务互动课堂。**

OpenMAIC 只作为体验标杆和 black-box benchmark：

- 可以对标 one-click lesson generation、课堂播放器、白板、测验、导出、互动体验
- 不复制 OpenMAIC 源码、Prompt、Schema、UI、素材或具体生成流程
- P0 只承诺标准课堂生成核心闭环；P0.5/P1 再补课堂临场感和交互广度

---

## 2. 文档权威层级

### 2.1 Canonical

- [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)

职责：

- 定义唯一 authority
- 定义 P0/P1/P2 边界
- 定义 transport / data / lifecycle / release gate
- 解决各版本文档冲突

### 2.2 Supporting

- [建筑实务AI互动课堂_技术实现蓝图_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_技术实现蓝图_v1.1.md)
- [建筑实务AI互动课堂_实施任务拆解_v1.1.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_实施任务拆解_v1.1.md)

职责：

- 作为背景设计说明
- 作为任务拆解素材
- 作为 OpenMAIC 对标分析素材

限制：

- 不再独自定义 authority
- 不再独自定义 API 真相
- 不再独自定义 MVP 和发布门槛

### 2.3 Historical

- `建筑实务AI互动课堂_Implementation_Plan_v1.0.docx`
- `建筑实务AI互动课堂_PRD_v1.0.docx`

职责：

- 仅保留历史上下文
- 不再作为当前实施 authority

---

## 3. 硬约束

### 3.1 Transport

必须遵守：

- 聊天和课堂问答的唯一流式入口仍然是 `/api/v1/ws`
- SSE 只允许用于 job / export / review progress 这类**非聊天**事件流
- HTTP 只允许用于 CRUD、job bootstrap、导出触发、审核动作

明确禁止：

- 新增第二条课堂聊天 WebSocket
- 让 `/api/exam-classrooms/{id}/ask` 承担独立 streaming 协议
- 在播放器内部偷偷维护第二套 pending turn 状态来源

### 3.2 Capability

P0 默认规则：

- `exam_classroom` 是**领域模块 / 产品表面**
- 生成、审核、导出、播放器数据聚合是领域服务，不自动等于新 capability
- 课堂内问答默认复用现有 `chat` capability 和统一 turn contract

只有在以下条件同时满足时，`exam_classroom` 才允许升级为正式 capability：

1. 运行时确实需要独立的 orchestrator 选择逻辑
2. 公开 request config 无法由现有 `chat` capability 表达
3. 已同步更新 `deeptutor/capabilities/request_contracts.py`
4. 已补 capability contract、orchestrator 接入和相关测试

### 3.3 Object Naming

统一命名如下：

- 领域对象：`exam_classroom`
- 课程内容 IR：`Lesson IR`
- 导出包核心内容文件：`lesson.json`
- “course”仅允许用作自然语言描述，不再作为 API/table/file 的 canonical 名称
- `TeachStudio` 仅允许作为历史材料里的背景词，不再进入代码、表名、路由名和 schema 名

### 3.3.1 Product Surface

P0 的学员端主产品表面是微信小程序。

职责划分：

- `wx_miniprogram`：标准学员端实现，承载一键生成入口、Classroom Player、quiz/case 作答、scene-grounded Q&A 入口。
- `yousenwebview/packageDeeptutor`：佑森宿主内交付包，按既有 selective sync 方式从 `wx_miniprogram` 合入，但必须保留宿主路由、登录、会员、点数和 workspace shell 适配。
- Web/Admin：只作为教研审核、运营管理、导出预览或后续后台，不是 P0 学员端播放器 authority。
- HTML export：是可下载/可离线交付 artifact，不等于 Web 主产品表面。

禁止：

- 先实现 Web player，再把小程序当二期适配
- 在 Web player 与小程序 player 之间维护两套 scene 解释器
- 为小程序新增第二套聊天 transport
- 覆写 `yousenwebview/packageDeeptutor` 的宿主适配

小程序渲染与运行时细则以 [ADR-005-mini-program-surface-renderer-contract.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md) 为准。

### 3.3.2 Lesson IR 的 contract 定位

P0 的 `Lesson IR` 定位为：

- **模块内 canonical schema**
- `exam_classroom` 域内的唯一内容真相
- 前端播放器和导出服务共享的版本化中间表示

P0 暂不把 `Lesson IR` 自动升级成仓库级顶层 contract。

只有在以下条件成立时，才允许把它提升到 `CONTRACT.md` / `contracts/index.yaml` 级别：

1. 存在仓库外或跨产品表面的稳定复用需求
2. 已确认字段需要长期兼容
3. 已补机器可读 schema、validator、tests

### 3.4 Data Authority

P0 唯一课程内容真相：

- `exam_classrooms.lesson_ir`

P0 只允许以下表成为 primary storage：

- `exam_classrooms`
- `classroom_jobs`
- `question_attempts`
- `classroom_exports`
- `review_items`

P0 不允许以下对象成为并行 primary truth：

- `classroom_scenes`
- `classroom_actions`
- `exam_questions`

如果后续为了检索、列表性能、审核筛选需要拆表，只允许：

- 从 `lesson_ir` 做 projection
- 明确标注为 read model / index
- 不允许反向覆盖 `lesson_ir`

### 3.5 Lifecycle

P0 只保留四套状态，各司其职：

1. `classroom_jobs.status`
   - `queued | running | succeeded | failed | cancelled`
2. `exam_classrooms.status`
   - `draft | review_required | approved | published | archived`
3. `classroom_exports.status`
   - `queued | running | succeeded | failed`
4. `review_items.status`
   - `open | resolved`

以下内容不再作为持久生命周期状态：

- `ai_checked`
- `source_verified`
- `needs_review` 作为顶层状态名

它们只能作为 review evidence / quality flags 保存在 `quality_report` 或 `review_items` 中。

### 3.6 Learner-State Boundary

互动课堂模块可以产生结构化学习结果，但不能越权维护第二套 learner truth。

允许：

- 在 `question_attempts` 中保存作答、得分、`weak_tags`
- 通过统一 writeback pipeline 产出 `learner_memory_events`
- 将 mastery / weak points 聚合写回既有 learner-state contract 指定位置

禁止：

- 互动课堂模块直接整份覆盖 `user_stats`
- 在 `lesson_ir` 或导出物中暗藏学员长期真相
- 用播放器本地状态替代长期 learner progress authority

### 3.7 Existing Knowledge Base Boundary

互动课堂必须充分利用现有建筑实务知识库，但不能因此新建第二套知识 authority。

当前扫描结论：

- `construction-exam` 已通过既有 runtime defaults 绑定到 Supabase RAG。
- `kb_chunks` 已包含标准、教材、考试 chunk。
- `questions_bank` 已包含单选、多选、案例题、计算题和评分关键词。

允许：

- generation worker 调用 `RAGService.search(..., kb_name="construction-exam")`
- `SourceIngestionService` 把 `evidence_bundle.sources` 映射成 `source_manifest`
- quiz/case/rubric 生成复用 `questions_bank` evidence

禁止：

- 为互动课堂新建直连 Supabase 表的检索入口
- 只接 `kb_chunks` 而忽略 `questions_bank`
- 把 Supabase 原始行直接写进 `lesson_ir` 作为内容 truth
- 把“能检索到”推导成“能公开发布”

知识库复用细则以 [ADR-006-supabase-knowledge-base-reuse.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md) 为准。

---

## 4. Canonical 架构

```text
输入主题 / 上传资料
  -> POST /api/exam-classrooms/jobs
  -> classroom_jobs 异步生成
  -> 生成并原子更新 exam_classrooms.lesson_ir
  -> GET /api/exam-classrooms/{id}
  -> 微信小程序 Classroom Player 播放 lesson_ir
  -> 课堂问答统一走 /api/v1/ws
  -> question_attempts 保存结构化结果
  -> writeback pipeline -> learner_memory_events / user_stats
  -> review_items + exam_classrooms.status 控制发布
  -> classroom_exports 从 approved lesson_ir 导出
```

设计原则：

- 生成链路和问答链路分开，但 contract 不重复
- 播放器只消费 `lesson_ir`，不消费多份平行内容真相
- 审核、导出、重生成都围绕同一份 `lesson_ir` 运作

---

## 5. Canonical API 与运行时方案

### 5.1 HTTP / SSE

保留以下接口族：

- `POST /api/exam-classrooms/jobs`
- `GET /api/exam-classrooms/jobs/{job_id}`
- `GET /api/exam-classrooms/jobs/{job_id}/events`
- `GET /api/exam-classrooms/{classroom_id}`
- `POST /api/exam-classrooms/{classroom_id}/scene-regeneration-jobs`
- `POST /api/exam-classrooms/{classroom_id}/exports`
- `GET /api/exam-classrooms/{classroom_id}/reviews`
- `POST /api/exam-classrooms/{classroom_id}/reviews/{review_item_id}/resolve`

说明：

- `scene` 重生成继续走 job，而不是直接同步改课堂
- `events` 只承载生成/导出进度，不承载聊天 token stream

### 5.2 课堂内提问

课堂内提问统一走 `/api/v1/ws`。

功能定位：

- **它不是 P0 launch blocker**
- 如果在 P0 试点里实现，也必须复用统一 turn contract

P0 可选基线方案：

- 不新增 `/ask` 主链路
- 播放器在当前 `classroom_id + scene_key` 上构造 grounded turn context
- 由统一 turn runtime 产出回答和 trace

如果为了兼容 UI 临时保留 `POST /ask`：

- 它只能是 thin adapter
- 只能把请求转回统一 `/api/v1/ws` 链路
- 不得自己写 session
- 不得自己选 capability
- 不得定义第二套返回流协议

P1 增强方案：

- 如果确认需要“课堂对象级连续性”，再通过 turn contract 正式引入新的 active object 语义
- 在那之前，不允许用新路由绕开 contract

### 5.3 关于 `active_object` 的不确定性

当前 `UnifiedTurnActiveObject` 已存在，但现有 `ActiveObjectType` 还没有课堂场景类型。

因此这里给两条路径：

1. 首选路径
   - 先保持课堂问答走统一 `/api/v1/ws`
   - 若确需对象级连续性，再走 contract 变更，把课堂场景作为正式 active object family 引入
2. 保守路径
   - P0 先做“每轮 grounded scene QA”
   - 明确它是 scene-scoped 问答，不承诺新对象级持续状态

两条路径都禁止新增第二套 transport。

---

## 6. Canonical 数据模型

### 6.1 Primary Tables

#### `exam_classrooms`

职责：

- 课堂元数据
- canonical `lesson_ir`
- 顶层 lifecycle status
- source refs / schema version / release version
- `quality_report`
- `source_manifest`

最小字段建议：

- `id`
- `tenant_id`
- `created_by`
- `title`
- `exam_type`
- `subject`
- `status`
- `lesson_ir`
- `source_kb_ids`
- `source_manifest`
- `quality_report`
- `lesson_ir_revision`
- `schema_version`
- `release_version`
- `created_at`
- `updated_at`

#### `classroom_jobs`

职责：

- 生成与单 scene 重生成任务
- 进度与错误
- 幂等和重试边界
- trace、成本、runtime budget

关键字段建议：

- `idempotency_key`
- `trace_id`
- `tenant_id`
- `created_by`
- `job_type`
- `status`
- `retry_count`
- `max_retries`
- `max_runtime_seconds`
- `max_llm_tokens`
- `estimated_cost_cents`
- `actual_cost_cents`
- `cancel_requested_at`

#### `question_attempts`

职责：

- 学员作答
- 评分结果
- `weak_tags`

关键字段建议：

- `classroom_id`
- `scene_key`
- `question_key`
- `user_id`
- `answer_payload`
- `score`
- `grade_result`
- `weak_tags`

#### `classroom_exports`

职责：

- 导出任务
- 文件 artifact 引用
- approved snapshot 引用

关键字段建议：

- `classroom_id`
- `release_version`
- `lesson_ir_revision`
- `lesson_ir_hash`
- `export_type`
- `artifact_uri`

#### `review_items`

职责：

- 审核发现
- 风险证据
- 解决状态
- `quality_report` 的 issue projection

关键字段建议：

- `classroom_id`
- `target_type`
- `target_key`
- `severity`
- `status`
- `reason`
- `evidence`
- `resolved_at`

### 6.2 Lesson IR 内部约束

`lesson_ir` 内部保留稳定逻辑主键：

- `scene_key`
- `action_key`
- `question_key`
- `actor_key`

所有播放器、重生成、审核、导出都基于这些逻辑主键，不依赖额外主表。

### 6.3 Read Projections

只有在出现明确查询压力后，才允许新增：

- `classroom_scene_index`
- `classroom_question_index`
- `classroom_action_index`

这些 projection 必须满足：

- 来源唯一是 `lesson_ir`
- 可重建
- 不可反向写回

---

## 7. Canonical 状态机

### 7.1 Classroom

```text
draft
  -> review_required
  -> approved
  -> published
  -> archived
```

规则：

- 新建与生成中的课堂都视为 `draft`
- 只要存在未解决高风险 review item，课堂必须是 `review_required`
- 只有 review gate 通过后才能进入 `approved`
- `published` 只表示对试点/机构可用，不等于再次生成

### 7.2 Review Item

```text
open -> resolved
```

说明：

- `severity` 表示严重度
- `status` 只表示发现是否关闭
- `quality_report` 是课堂内容审核的主输出，`review_items` 只是便于流转和检索的 issue 投影
- `ai_checked / source_verified` 不再做状态机节点

### 7.3 Job

```text
queued -> running -> succeeded | failed | cancelled
```

### 7.4 Export

```text
queued -> running -> succeeded | failed
```

---

## 8. P0 / P1 / P2 重写

### 8.1 P0 必须做

- Canonical `Lesson IR`
- 4 类 scene：`slide / whiteboard / quiz / case`
- 生成 job + SSE 进度
- 微信小程序 Player 消费 `lesson_ir`
- 案例题评分与 `question_attempts`
- `weak_tags` 经统一 writeback pipeline 写回 learner-state
- `PPTX / HTML / ZIP` 导出
- 最小 review workflow
- `SourceManifest` / citation / copyright gate
- 复用现有 Supabase RAG 知识库，`kb_chunks / questions_bank` evidence 映射进 `source_manifest`
- `LessonQualityEvaluator`
- One-click Generation Gate
- 微信小程序学员端 Player
- `yousenwebview/packageDeeptutor` 宿主交付包 smoke
- 文档治理与 clean-room 规则

### 8.2 P0.5 体验增强

P0.5 只在 P0 主链路稳定后启动，不反向污染 P0 blocker：

- scene-grounded Q&A through `/api/v1/ws`
- single-teacher TTS + subtitle sync
- whiteboard action templates
- one signature construction simulation
- immersive classroom layout polish

### 8.3 P1 可增强

- 课堂内问答
- 课堂对象级连续性 contract 扩展
- 多角色动态互动
- 多角色 TTS
- read projections
- PBL lite
- 重点仿真模板

### 8.4 P2 才考虑

- MP4 / Remotion 视频
- 批量章节生产
- 机构品牌模板
- Script / DOCX 导出
- 完整 PBL 状态机
- 大规模仿真矩阵

---

## 9. 里程碑重写

### Phase A: Contract And Canonical Model

目标：

- 文档 authority 收口
- `Lesson IR` canonical 化
- 生命周期与命名统一
- clean-room / license gate 写成硬规则
- `SourceManifest / GenerationTrace / LessonQualityReport` schema
- 现有 `construction-exam` RAG evidence 到 `source_manifest` 的映射规则

### Phase B: Fixture-first Playback

目标：

- 第一周禁止接真实 LLM
- 用 fixture 证明微信小程序 Player 只消费 `lesson_ir`
- mock grading / mock ZIP 跑通端到端
- 微信开发者工具模拟器 smoke

### Phase C: One-click Generation Core

目标：

- `POST jobs`
- SSE 进度
- 4 类 scene 生成
- 单 scene 重生成 job
- generation DAG 可追踪
- quality evaluator 自动运行

### Phase D: Exam Training Depth

目标：

- `question_attempts`
- rubric grading
- learner-state writeback pipeline
- 错题重学课的输入基础

### Phase E: Review / Export

目标：

- review console
- `PPTX / HTML / ZIP`
- approved snapshot export

### Phase F: P0.5 Experience Enhancement

目标：

- scene-grounded Q&A
- single-teacher TTS
- whiteboard action templates
- one signature construction simulation

---

## 10. Release Gate 重写

上线前必须同时通过以下门槛。

### 10.1 Contract Gate

- 没有新增第二条聊天 WebSocket
- 没有新增未注册 capability config
- 没有引入第二套课堂问答 transport
- 没有 scene/action/question primary truth tables
- 没有 router / worker / exporter 直接写 `lesson_ir`

### 10.2 Generation Gate

- LLM 输出必须通过机器 schema
- JSON repair 最多 2 次，失败明确返回
- 每个 scene 有 `scene_key` 和 `learning_objective`
- 每个 question 有 `question_key`
- 每个 case 有 rubric
- 生成失败不会产生无状态半残课堂
- `classroom_jobs` 具备 idempotency、trace、成本和 runtime budget

### 10.3 Playback Gate

- 4 类 scene 在播放器里可播放
- 微信小程序 Player 只消费 `lesson_ir`
- action timeline 不引用不存在的 block / actor / question
- scene 重生成后仍能原子回写 `lesson_ir`
- 单 scene 出错只降级该 scene，不拖垮整堂课
- `yousenwebview/packageDeeptutor` 宿主包 smoke 通过

### 10.4 Content Gate

- 30 个高频考点生成任务通过
- `lesson_ir` 全部通过 schema 校验
- 核心知识点具备 citations 或明确资料不足提示
- 案例题符合考试表达，rubric 可评分
- `LessonQualityEvaluator` 输出 `quality_report`
- 重大事实错误为零容忍 blocker

### 10.5 Export / Release Gate

- `PPTX / HTML / ZIP` 全部能打开
- PPTX 在 PowerPoint / WPS 下无明显文本溢出
- ZIP 包含 `lesson.json / manifest / assets / citations / questions`
- 导出均来自 `approved` 的 `lesson_ir`
- 导出记录 `release_version / lesson_ir_revision / lesson_ir_hash`

### 10.6 Learner-State Gate

- `weak_tags` 与 grading result 只经统一 writeback pipeline 进入 learner-state
- 没有模块绕过 learner-state contract 私写长期进度

### 10.7 License / Provenance Gate

- 不复制 OpenMAIC 源码、Prompt、Schema、UI、素材
- 每条 source chunk、外部素材、用户上传资料都带 provenance 与 `copyright_level`
- 每条 citation 只引用 `source_manifest` 中存在的 source
- `web_unverified / unknown / forbidden` 不得 `published`
- 对外发布前存在明确 legal review 结论；未完成 legal review 的课堂不得发布

### 10.8 Knowledge Base Coverage Gate

- 课堂生成必须复用 `RAGService` 和 `construction-exam` 知识库绑定
- `RAGEvidence` 必须保留 `source_table` 和 stable id
- 没有 `KnowledgeCoverageReport` 不得生成 outline
- topic outline 至少命中 `standard` 或 `textbook` evidence
- quiz/case scene 至少命中 `questions_bank` 或 `exam` evidence
- case rubric 必须有题库、真题、教材评估题或人工 rubric 来源
- 没有 `questions_bank` case/rubric evidence 不得生成正式 `case` scene
- `kb_chunks` 与 `questions_bank` evidence 都能映射为 `source_manifest`
- evidence 不足的 scene 必须写入 `source_gap`，不得静默编造
- 低覆盖主题在补库前只能进入 `review_required`

### 10.9 One-click Generation Gate

- 30 个建筑实务高频考点生成成功率 >= 90%
- 首个 outline 可见时间 <= 30 秒
- 10 分钟课程完整生成时间 <= 4 分钟
- `lesson_ir` schema 通过率 100%
- 播放 fatal error 为 0
- PPTX / HTML / ZIP 打开成功率 100%
- 关键知识点 citation 覆盖率 >= 90%
- 案例题 rubric 完整率 >= 95%
- 人工教研评分 >= 4/5 的课程比例 >= 70%
- 小程序课堂首屏可交互时间 <= 3 秒，弱网 <= 6 秒
- 课堂 payload 压缩后建议 <= 500KB，超出分页/懒加载
- hide/show 后恢复成功率 >= 95%

### 10.10 Mini-program Release Gate

- 微信开发者工具 smoke 通过
- iOS 真机 smoke 通过
- Android 真机 smoke 通过
- 弱网/断网/恢复后 job 状态可恢复
- app hide/show 后播放器状态不乱
- 首屏进入课堂不白屏
- 单 scene 渲染失败只降级当前 scene
- 音频失败自动字幕回退
- case 长文本输入不丢失
- quiz/case 提交后不会重复扣点
- `packageDeeptutor` selective sync smoke 通过

---

## 11. 需要继续验证的不确定性

### 11.1 课堂问答是否必须要“对象级连续性”

不确定点：

- P0 试点是否真的需要跨多轮 scene-bound continuity

验证方式：

- 先用统一 `/api/v1/ws` 做 grounded scene QA 试点
- 若出现显著 continuity 需求，再正式走 turn contract 扩展

### 11.2 是否需要 scene / question projection 表

不确定点：

- 审核后台和运营检索是否会在 P0 就遇到性能瓶颈

验证方式：

- 先用 `lesson_ir` + 后端 projection in memory
- 确认有查询压力后，再增加只读 projection

### 11.3 Script / DOCX 导出是否必须进入近期交付

不确定点：

- 试点机构是否把“可编辑讲稿”列为签约前提

验证方式：

- 先让试点机构基于 `PPTX / HTML / ZIP` 验收
- 如确为 blocker，再把 Script / DOCX 从 P2 提前到独立增量里程碑

### 11.4 复杂资料解析是否必须 P0 全覆盖

不确定点：

- 建筑实务资料可能包含复杂表格、公式、施工图、网络计划图、扫描件和机构私有讲义

验证方式：

- P0 先保证段落、标题、页码、表格和图片 provenance
- OCR、复杂公式、施工图理解先作为 P1/P2 能力增强
- 若解析置信度不足，必须降级为 `review_required`，不能静默发布

---

## 12. 最终执行原则

这次收口之后，后续所有实现都必须服从五条规则：

1. **先判断是不是在长第二套系统，再决定怎么写代码**
2. **先围绕 `lesson_ir` 收权，再考虑 projection**
3. **先复用统一 `/api/v1/ws`，再考虑课堂问答体验增强**
4. **先做可交付的考试闭环，再追求 OpenMAIC 式表现力**
5. **先证明质量与来源可信，再扩大生成和交互能力**
