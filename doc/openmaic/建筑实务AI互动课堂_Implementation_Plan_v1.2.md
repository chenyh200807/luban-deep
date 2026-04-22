# 建筑实务 AI 互动课堂 Implementation Plan v1.2

> 状态：**live plan**
>
> 本文件是当前唯一可派工的实施计划。
>
> 权威来源：
>
> - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
> - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
> - [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
> - [ADR-001-lesson-ir-authority.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/ADR-001-lesson-ir-authority.md)
> - [ADR-002-classroom-turn-transport.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/ADR-002-classroom-turn-transport.md)

---

## 0. 目标

P0 只做一条稳健、可交付、可验收的闭环：

```text
fixture / 考点输入
-> 生成 lesson_ir
-> 播放四类 scene
-> 案例题批改
-> weak_tags writeback
-> review gate
-> PPTX / HTML / ZIP 导出
```

不在 P0 里强绑：

- 课堂内自由问答
- 动态 AI 同学
- 多角色 TTS
- PBL
- 交互仿真
- MP4
- Script / DOCX

---

## 1. P0 Canonical 约束

### 1.1 Canonical nouns

- 领域对象：`exam_classroom`
- 唯一内容真相：`lesson_ir`
- 导出核心文件：`lesson.json`

### 1.2 唯一 authority

- 唯一课程内容真相：`exam_classrooms.lesson_ir`
- 唯一聊天/课堂问答流式入口：`/api/v1/ws`
- 唯一长期 learner progress authority：learner-state contract

### 1.3 Forbidden shortcuts

全计划通用禁止项：

- 不得新增 `/ask` streaming endpoint
- 不得新增第二条课堂聊天 WebSocket
- 不得新增 `classroom_scenes` primary table
- 不得新增 `classroom_actions` primary table
- 不得新增 `exam_questions` primary table
- 不得直接 `UPDATE exam_classrooms.lesson_ir`
- 不得让 exporter / reviewer / router 直接写 `lesson_ir`
- 不得让 projection 反写 `lesson_ir`
- 不得让互动课堂模块直接写 `user_stats`
- 不得把 `course.json`、`exam_courses`、`TeachStudio` 引回 canonical 设计

---

## 2. 阶段划分

### Phase A: Canonical Model

目标：

- 文档 authority 冻结
- `Lesson IR` schema 定义
- `LessonIRService` 唯一 writer
- primary tables migration

### Phase B: Generation

目标：

- fixture 优先
- 生成 job 写入 `lesson_ir`
- SSE 进度
- scene 重生成 CAS

### Phase C: Playback

目标：

- Player 只消费 `lesson_ir`
- 四类 scene 可渲染
- 不依赖 projection 才能播放

### Phase D: Grading / Writeback

目标：

- `question_attempts`
- rubric grading
- `weak_tags`
- 统一 learner writeback

### Phase E: Review / Export

目标：

- `quality_report`
- `review_items`
- approved snapshot export
- `PPTX / HTML / ZIP`

### Phase F: P1 Experience

目标：

- 课堂内问答
- 多角色 TTS
- 动态角色互动
- PBL lite / 仿真模板

---

## 3. P0 任务表

以下任务按执行顺序排列，且每个任务都带 `Forbidden shortcuts` 与 `Tests`。

### A1 文档纳管与 banned patterns

- ID：`A1`
- Owner：Tech Lead
- Files touched：
  - `doc/openmaic/README.md`
  - `doc/openmaic/banned-v1.1-patterns.md`
- Input：
  - canonical spec v1.2
- Output：
  - 文档层级冻结
  - banned patterns 清单
- Dependencies：无
- Acceptance criteria：
  - `README` 明确 canonical / supporting / historical 层级
  - banned patterns 清单可直接作为 PR review 依据
- Forbidden shortcuts：
  - 不得继续以 v1.1 任务表作为 live plan
- Tests：
  - 文档 review checklist 通过

### A2 Lesson IR schema v0.1

- ID：`A2`
- Owner：Tech Lead + AI Backend
- Files touched：
  - `deeptutor/exam_classroom/schemas/lesson_ir.py`
  - `deeptutor/exam_classroom/schemas/lesson_ir.schema.json`
  - `fixtures/exam_classroom/*.lesson.json`
- Input：
  - canonical spec v1.2
- Output：
  - `Lesson IR` 机器可读 schema
  - 3 个以上 fixture
- Dependencies：`A1`
- Acceptance criteria：
  - schema 覆盖 `schema_version / exam_classroom_id / exam / audience / source_manifest / actors / scenes / narration / actions / questions / citations / quality_report`
  - fixture 能通过校验
  - schema 暂不把 PBL / MP4 / 多角色实时问答塞进主体
- Forbidden shortcuts：
  - 不得把 `scene` / `question` 拆成第二份 canonical schema
- Tests：
  - `test_lesson_ir_fixture_validation`
  - `test_invalid_lesson_ir_rejected`

### A3 LessonIRService

- ID：`A3`
- Owner：Backend
- Files touched：
  - `deeptutor/exam_classroom/services/lesson_ir_service.py`
  - 对应 tests
- Input：
  - `Lesson IR schema`
- Output：
  - 唯一 writer service
- Dependencies：`A2`
- Acceptance criteria：
  - 具备 `get / create_draft / replace_scene_from_job / approve / publish`
  - 引入 `revision` 或 `etag`
  - 支持 compare-and-swap
- Forbidden shortcuts：
  - 不得让 router / worker / exporter 直接改 `lesson_ir`
- Tests：
  - `test_lesson_ir_service_is_only_writer`
  - `test_patch_scene_requires_expected_revision`
  - `test_publish_locks_release_snapshot`

### A4 Primary tables migration

- ID：`A4`
- Owner：Backend
- Files touched：
  - migration 文件
- Input：
  - `A3` service contract
- Output：
  - 5 张 primary tables
- Dependencies：`A3`
- Acceptance criteria：
  - 只建以下 primary tables：
    - `exam_classrooms`
    - `classroom_jobs`
    - `question_attempts`
    - `classroom_exports`
    - `review_items`
  - 不建 `classroom_scenes / classroom_actions / exam_questions` primary tables
- Forbidden shortcuts：
  - 不得把 projection 表伪装成 primary tables
- Tests：
  - migration apply / rollback 通过
  - schema snapshot review 通过

### A5 Fixture player

- ID：`A5`
- Owner：Frontend + Backend
- Files touched：
  - `GET /api/exam-classrooms/{id}`
  - `web/app/.../exam-classroom/...`
  - fixtures
- Input：
  - 手写 lesson fixture
- Output：
  - Player 静态渲染四类 scene
- Dependencies：`A2`、`A4`
- Acceptance criteria：
  - 前端只读取 `lesson_ir`
  - `slide / whiteboard / quiz / case` 能展示
  - 不依赖 projection 表
- Forbidden shortcuts：
  - 不得单独从 `scene` 表拼内容
- Tests：
  - `test_player_payload_reads_lesson_ir_only`
  - 前端 fixture render smoke

### A6 Generation job

- ID：`A6`
- Owner：AI Backend + Backend
- Files touched：
  - `POST /api/exam-classrooms/jobs`
  - `classroom_jobs`
  - generation worker
- Input：
  - topic / sources / fixture
- Output：
  - 生成 job 写入 `lesson_ir`
- Dependencies：`A3`、`A4`
- Acceptance criteria：
  - 生成成功后 `exam_classrooms.lesson_ir` 完整
  - SSE 显示 `queued / running / succeeded`
  - 失败时课堂仍可解释，不出现无状态半残对象
- Forbidden shortcuts：
  - 不得先落 `scene` 主表再回填 `lesson_ir`
- Tests：
  - `test_generate_job_writes_lesson_ir_once`
  - `test_job_events_are_non_chat_sse`

### A7 Scene regeneration CAS

- ID：`A7`
- Owner：Backend + AI Backend
- Files touched：
  - `POST /api/exam-classrooms/{id}/scene-regeneration-jobs`
  - `LessonIRService.replace_scene_from_job`
- Input：
  - `scene_key`
  - regeneration instruction
- Output：
  - 局部重生成
- Dependencies：`A6`
- Acceptance criteria：
  - 只替换指定 `scene_key`
  - 人工修改后，旧 job 不能覆盖新 revision
  - 失败返回 `stale_revision` 或 `rebase_required`
- Forbidden shortcuts：
  - 不得全量覆盖课堂绕过 revision check
- Tests：
  - `test_scene_regeneration_only_replaces_target_scene`
  - `test_scene_regeneration_cannot_overwrite_newer_revision`

### A8 question_attempts + grading

- ID：`A8`
- Owner：AI Backend + Backend + Frontend
- Files touched：
  - `question_attempts`
  - grading service
  - case renderer
- Input：
  - case answer
  - rubric
- Output：
  - 得分、命中点、漏点、优化答案、`weak_tags`
- Dependencies：`A5`
- Acceptance criteria：
  - 学员作答后能得到结构化 grading 结果
  - `question_attempts` 保存结果
- Forbidden shortcuts：
  - 不得直接把 grading 结果写进 `user_stats`
- Tests：
  - `test_case_grading_writes_question_attempt`
  - `test_grading_result_contains_weak_tags`

### A9 learner writeback

- ID：`A9`
- Owner：Backend
- Files touched：
  - writeback adapter
  - learner-state integration
- Input：
  - `question_attempts`
  - grading result
- Output：
  - `learner_memory_events`
  - learner-state 结构化写回
- Dependencies：`A8`
- Acceptance criteria：
  - `weak_tags` 通过统一 pipeline 写入 learner-state
  - 没有模块直接覆写 `user_stats`
- Forbidden shortcuts：
  - 不得绕过 learner-state contract 私写长期进度
- Tests：
  - `test_writeback_pipeline_consumes_question_attempt`
  - `test_exam_classroom_module_cannot_write_user_stats_directly`

### A10 review gate

- ID：`A10`
- Owner：Backend + Reviewer tooling
- Files touched：
  - `quality_report`
  - `review_items`
  - status computation
- Input：
  - lesson_ir
  - review findings
  - human decision
- Output：
  - `draft / review_required / approved / published`
- Dependencies：`A6`、`A8`
- Acceptance criteria：
  - blocker/high 未解决不能 `approved`
  - `review_items` 只是 issue projection
  - `quality_report` 是审核主输出
- Forbidden shortcuts：
  - 不得把 `review_items.status` 直接当发布状态
- Tests：
  - `test_open_blocker_prevents_approval`
  - `test_review_items_are_projection_only`

### A11 export snapshot

- ID：`A11`
- Owner：Backend + Export engineer
- Files touched：
  - `classroom_exports`
  - export service adapter
- Input：
  - approved snapshot
- Output：
  - `PPTX / HTML / ZIP`
- Dependencies：`A10`
- Acceptance criteria：
  - 导出记录 `release_version / lesson_ir_revision / lesson_ir_hash`
  - 导出只来自 `approved` snapshot
  - `lesson.json` 为唯一 canonical 内容文件
- Forbidden shortcuts：
  - 不得导出正在变化的 draft
  - 不得引入 `course.json`
- Tests：
  - `test_export_uses_approved_snapshot_only`
  - `test_export_records_source_revision_and_hash`

### A12 ACL + provenance + runtime gate

- ID：`A12`
- Owner：Backend + Ops + Tech Lead
- Files touched：
  - ACL policy
  - object storage path policy
  - source manifest schema
  - runtime budget fields
- Input：
  - tenant / role / export / source
- Output：
  - 最小权限矩阵
  - provenance gate
  - runtime cost gate
- Dependencies：`A11`
- Acceptance criteria：
  - `tenant_id`、`created_by` 强制存在
  - export 通过 signed URL + tenant check + permission check
  - `source_manifest` 含 provenance 与 `copyright_level`
  - `classroom_jobs` 含 `idempotency_key / trace_id / max_runtime_seconds / max_llm_tokens / estimated_cost_cents`
- Forbidden shortcuts：
  - 不得让公开导出绕过 tenant 和 permission check
  - 不得让 `web_unverified / unknown / forbidden` 源进入 published
- Tests：
  - `test_export_requires_tenant_and_permission_check`
  - `test_unknown_source_cannot_publish`
  - `test_job_idempotency_returns_same_job`

---

## 4. 第一周切片

第一周禁止接真实 LLM。

### Slice 1: Canonical Lesson IR Fixture

交付：

- `Lesson IR schema`
- `exam_classrooms` 表
- 一个 `mass_concrete.lesson.json` fixture
- `GET /api/exam-classrooms/{id}`
- Player 静态渲染

验收：

1. 没有 `classroom_scenes` primary table
2. 前端只读取 `lesson_ir`
3. 四类 scene 可显示

### Slice 2: Mock grading + mock ZIP

交付：

- case submit
- mock grading
- mock ZIP export

验收：

1. 证明 authority 干净
2. 证明导出不依赖第二份 truth

---

## 5. P1 Backlog

P1 只在 P0 闭环稳定后启动：

- 课堂内问答
- grounded classroom context through `/api/v1/ws`
- 多角色 TTS
- 脚本化 AI 老师/同学增强
- whiteboard 动效
- PBL lite
- 仿真模板

P1 启动前必须回答：

1. 为什么现有 `chat` capability 不够？
2. 是否真的需要对象级连续性？
3. 是否需要扩展 turn contract？

---

## 6. P0 成功标准

P0 完成时，必须同时满足：

1. `Lesson IR` 是唯一课程内容真相
2. Player 只读取 `lesson_ir`
3. scene 重生成不会覆盖新 revision
4. grading 结果只经统一 pipeline 进入 learner-state
5. `PPTX / HTML / ZIP` 来自 approved snapshot
6. 没有任何 `/ask` streaming endpoint
7. 没有任何 scene/action/question primary truth tables

---

## 7. 研发执行纪律

任何 PR 如果触发以下任一项，默认打回：

- 引入第二套 transport
- 引入第二套 schema 真相
- 引入第二套状态机
- 让 projection 反写 `lesson_ir`
- 让互动课堂模块绕过 learner-state
- 把 P1/P2 功能混进 P0
