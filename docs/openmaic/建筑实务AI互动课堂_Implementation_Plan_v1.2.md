# 建筑实务 AI 互动课堂 Implementation Plan v1.2

> 状态：**live plan**
>
> 本文件是当前唯一可派工的实施计划。v1.1 任务拆解只能作为历史素材，不再作为研发任务表。
>
> 权威来源：
>
> - [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
> - [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
> - [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
> - [ADR-001-lesson-ir-authority.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-001-lesson-ir-authority.md)
> - [ADR-002-classroom-turn-transport.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-002-classroom-turn-transport.md)
> - [ADR-003-quality-evaluation-release-gate.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-003-quality-evaluation-release-gate.md)
> - [ADR-004-source-ingestion-provenance.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-004-source-ingestion-provenance.md)
> - [ADR-005-mini-program-surface-renderer-contract.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-005-mini-program-surface-renderer-contract.md)
> - [ADR-006-supabase-knowledge-base-reuse.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md)

---

## 0. 北极星

唯一北极星指标：

> 一键生成高质量建筑实务互动课堂。

P0 不是完整追平 OpenMAIC。P0 要交付的是：

```text
考点 / 上传资料
-> 生成 lesson_ir
-> 播放 slide / whiteboard / quiz / case
-> 案例题批改
-> weak_tags writeback
-> quality / review gate
-> PPTX / HTML / ZIP 导出
```

OpenMAIC 只作为体验对标和路线图参考，不作为实现资产来源。公开 README / CHANGELOG 可用于 black-box benchmark；禁止复制其源码、Prompt、Schema、UI、素材或具体生成流程。

公开对标资料：

- [OpenMAIC GitHub README](https://github.com/THU-MAIC/OpenMAIC)
- [OpenMAIC CHANGELOG](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md)

---

## 1. P0 Canonical 约束

### 1.1 唯一 authority

- 课程内容真相：`exam_classrooms.lesson_ir`
- 内容写入 authority：`LessonIRService`
- 来源治理 authority：`SourceIngestionService`
- 知识召回 authority：`RAGService` + `construction-exam` 默认知识库绑定
- 质量评测 authority：`LessonQualityEvaluator`
- 学员端主产品表面：微信小程序 `wx_miniprogram`
- 宿主交付表面：`yousenwebview/packageDeeptutor`
- 跨端渲染解释 authority：`Scene Runtime Core`
- 课堂问答流式入口：`/api/v1/ws`
- 长期学员进步 authority：learner-state contract

### 1.2 Frontend surface policy

P0 的学员端主表面是微信小程序，不是 Web。

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

### 1.3 P0 不做

- 课堂内自由问答作为 blocker
- 动态 AI 同学
- 多角色 TTS
- 完整 PBL
- 大规模交互仿真
- MP4
- Script / DOCX
- `exam_classroom` first-class capability

### 1.4 Forbidden shortcuts

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
- 不得为互动课堂新建第二套 Supabase 检索入口
- 不得绕过 `RAGService` 直连 `kb_chunks / questions_bank`
- 没有 `source_manifest`，不得写入 `lesson_ir`
- 没有 `KnowledgeCoverageReport`，不得生成 outline
- 没有 `questions_bank` case/rubric evidence，不得生成正式 `case` scene
- 不得把 `course.json`、`exam_courses`、`TeachStudio` 引回 canonical 设计
- 不得让 `web_unverified / unknown / forbidden` 源进入 `published`
- 不得把 Web-only player 当作 P0 学员端交付完成
- 不得把 React 组件当作跨端共享核心
- 不得在 `lesson_ir` 里嵌入 raw HTML、inline script、iframe、external CSS

---

## 2. One-click Generation Gate

一键生成不是“点一下得到 JSON”，而是用户能得到一堂可用课。

| 指标 | P0 合格线 | P1 优秀线 |
| --- | --- | --- |
| 30 个建筑实务高频考点生成成功率 | >= 90% | >= 97% |
| 首个 outline 可见时间 | <= 30 秒 | <= 15 秒 |
| 10 分钟课程完整生成时间 | <= 4 分钟 | <= 2 分钟 |
| `lesson_ir` schema 通过率 | 100% | 100% |
| 每课 scene 数量 | 5-8 个 | 6-12 个 |
| 必含 scene 类型 | `slide / whiteboard / quiz / case` | + `dialogue / simulation / review` |
| 播放 fatal error | 0 | 0 |
| PPTX / HTML / ZIP 打开成功率 | 100% | 100% |
| 关键知识点 citation 覆盖率 | >= 90% | >= 95% |
| 高频考点知识库覆盖预检通过率 | >= 90% | >= 97% |
| quiz/case 题库 evidence 覆盖率 | >= 90% | >= 95% |
| `source_gap` 未标记静默生成 | 0 容忍 | 0 容忍 |
| 重大事实错误 | 0 容忍 | 0 容忍 |
| 案例题 rubric 完整率 | >= 95% | >= 98% |
| 人工教研评分 >= 4/5 的课程比例 | >= 70% | >= 85% |
| 小程序课堂首屏可交互时间 | <= 3 秒，弱网 <= 6 秒 | <= 2 秒，弱网 <= 4 秒 |
| 课堂 payload 压缩后大小 | 建议 <= 500KB，超出分页/懒加载 | <= 350KB |
| 单 scene 切换耗时 | <= 500ms | <= 300ms |
| 单 scene 降级成功率 | 100% | 100% |
| quiz/case 提交成功率 | >= 98% | >= 99% |
| 音频失败字幕回退成功率 | 100% | 100% |
| hide/show 后恢复成功率 | >= 95% | >= 98% |
| 小程序真机 smoke 覆盖 | iOS + Android | iOS + Android + 弱网 |
| 宿主包 smoke | 100% | 100% |

如果这些指标没有进入验收，研发会自然滑向“功能存在”；进入验收后，目标才会变成“效果可用”。

---

## 3. 阶段路线

### Phase A: Canonical Foundation

目标：

- 文档 authority 冻结
- `Lesson IR` schema 定义
- `render_constraints` 定义
- `LessonIRService` 唯一 writer
- primary tables migration
- `SourceManifest / GenerationTrace / LessonQualityReport` schema
- Supabase RAG evidence 到 `source_manifest` 的映射规则
- `Scene Runtime Core` contract

### Phase B: Fixture-first Playback

目标：

- 第一周禁止接真实 LLM
- 先用 fixture 跑通端到端
- 小程序 Player 通过 `Scene Runtime Core` 消费 `lesson_ir`
- quiz / case / mock grading / mock ZIP 可用
- 微信开发者工具和真机 smoke

### Phase C: One-click Generation Core

目标：

- 异步 job 生成 `lesson_ir`
- SSE 进度只承载非聊天事件
- generation DAG 可追踪
- scene 重生成 CAS
- 小程序 job progress 轮询/增量事件适配
- 生成后自动运行 quality evaluator

Generation DAG：

```text
parse_intent
-> retrieve_sources
-> normalize_source_manifest
-> build_knowledge_coverage_report
-> generate_outline
-> verify_outline
-> generate_scene_plan
-> generate_slide_scene
-> generate_whiteboard_scene
-> generate_quiz_scene
-> generate_case_scene
-> merge_lesson_ir
-> run_quality_evaluator
-> write_lesson_ir
```

原则：LLM 不直接生成完整课堂；LLM 只生成可验证的结构化中间产物。

### Phase D: Exam Training Depth

目标：

- rubric-driven case grading
- hit_points / missing_points / improved_answer
- `weak_tags`
- learner-state writeback
- 后续支持错题重学课

### Phase E: Review + Export

目标：

- `quality_report`
- `review_items`
- approved snapshot export
- `PPTX / HTML / ZIP`
- PPTX golden tests
- 小程序端只看导出状态、分享链接和预览入口

### Phase F: P0.5 OpenMAIC Feel

P0 闭环稳定后启动，不反向污染 P0 blocker。

目标：

- scene-grounded Q&A through `/api/v1/ws`
- single-teacher TTS + subtitle sync
- whiteboard action templates
- one signature construction simulation
- immersive classroom layout polish

---

## 4. P0 任务表

每个任务都必须包含 `Acceptance criteria`、`Forbidden shortcuts`、`Tests`。

### A1 文档纳管与 banned patterns

- ID：`A1`
- Owner：Tech Lead
- Files touched：
  - `docs/openmaic/README.md`
  - `docs/openmaic/banned-v1.1-patterns.md`
  - `docs/plan/INDEX.md`
- Output：
  - 文档层级冻结
  - banned patterns 清单
  - 计划索引能找到 OpenMAIC 主线
- Acceptance criteria：
  - `README` 明确 canonical / supporting / historical 层级
  - banned patterns 可直接作为 PR review 依据
  - `docs/plan/INDEX.md` 不再漏掉本主线
- Forbidden shortcuts：
  - 不得继续以 v1.1 任务表作为 live plan
- Tests：
  - 文档路径检查通过

### A2 Lesson IR schema v0.1

- ID：`A2`
- Owner：Tech Lead + AI Backend
- Files touched：
  - `deeptutor/exam_classroom/schemas/lesson_ir.py`
  - `deeptutor/exam_classroom/schemas/lesson_ir.schema.json`
  - `fixtures/exam_classroom/*.lesson.json`
- Output：
  - `Lesson IR` 机器可读 schema
  - 至少 3 个 fixture：`mass_concrete / network_plan / claim_analysis`
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
- Output：
  - 唯一 writer service
- Acceptance criteria：
  - 具备 `get / create_draft / patch_scene / replace_scene_from_job / approve / publish`
  - 引入 `revision` 或 `etag`
  - 支持 compare-and-swap
- Forbidden shortcuts：
  - 不得让 router / worker / exporter / reviewer 直接改 `lesson_ir`
- Tests：
  - `test_lesson_ir_service_is_only_writer`
  - `test_patch_scene_requires_expected_revision`
  - `test_publish_locks_release_snapshot`

### A4 Primary tables migration

- ID：`A4`
- Owner：Backend
- Files touched：
  - migration 文件
- Output：
  - 5 张 primary tables
- Acceptance criteria：
  - 只建 `exam_classrooms / classroom_jobs / question_attempts / classroom_exports / review_items`
  - 不建 `classroom_scenes / classroom_actions / exam_questions` primary tables
- Forbidden shortcuts：
  - 不得把 projection 表伪装成 primary tables
- Tests：
  - migration apply / rollback 通过
  - schema snapshot review 通过

### A4.1 SourceManifest schema

- ID：`A4.1`
- Owner：AI Backend + Backend
- Files touched：
  - `deeptutor/exam_classroom/schemas/source_manifest.py`
  - `deeptutor/exam_classroom/schemas/source_manifest.schema.json`
- Output：
  - `SourceManifestItem` 与 `SourceChunk` schema
- Acceptance criteria：
  - 字段覆盖 `source_id / source_type / copyright_level / allowed_use / provenance`
  - citation 只能引用已注册 source
  - `web_unverified / unknown / forbidden` 有明确阻断策略
- Forbidden shortcuts：
  - 不得让 generator 临时捏造 citation
- Tests：
  - `test_source_manifest_item_schema_validation`
  - `test_citation_must_reference_source_manifest`

### A4.2 GenerationTrace schema

- ID：`A4.2`
- Owner：AI Backend + Observability
- Files touched：
  - `deeptutor/exam_classroom/schemas/generation_trace.py`
- Output：
  - 可追踪 generation DAG trace
- Acceptance criteria：
  - 每个阶段记录 input hash、model、prompt version、source ids、warnings、cost
  - trace 能回到 `classroom_jobs.trace_id`
- Forbidden shortcuts：
  - 不得只在自然语言日志里记录关键生成决策
- Tests：
  - `test_generation_trace_records_dag_steps`
  - `test_generation_trace_links_to_job_trace_id`

### A4.3 LessonQualityReport schema

- ID：`A4.3`
- Owner：AI Backend + Reviewer tooling
- Files touched：
  - `deeptutor/exam_classroom/schemas/quality_report.py`
- Output：
  - `LessonQualityReport` schema
- Acceptance criteria：
  - 覆盖 `schema_validity / source_grounding / exam_relevance / teaching_flow / interaction_quality / case_rubric_quality / export_readiness`
  - 支持 `blockers / warnings / publishable / score_total`
- Forbidden shortcuts：
  - 不得把质量分散写进多个互相冲突的状态字段
- Tests：
  - `test_quality_report_schema_validation`
  - `test_quality_report_blocker_prevents_publishable`

### A4.4 SupabaseKnowledgeBaseInventory

- ID：`A4.4`
- Owner：AI Backend + Tech Lead
- Files touched：
  - RAG inventory script / report
  - `docs/openmaic/ADR-006-supabase-knowledge-base-reuse.md`
- Output：
  - 现有 Supabase RAG 知识资产清单
  - 30 个黄金考点的知识库覆盖 baseline
- Acceptance criteria：
  - 通过只读方式统计 `kb_chunks` 与 `questions_bank`
  - 分清 `standard / textbook / exam / questions_bank` 四类 evidence
  - 对低覆盖主题生成 `source_gap` 风险清单
  - 不输出密钥和大段私有资料正文
- Forbidden shortcuts：
  - 不得把扫描脚本变成课堂生成运行时依赖
  - 不得为了课堂计划新建第二套 Supabase 表
- Tests：
  - `test_kb_inventory_report_has_no_secret_values`
  - `test_kb_inventory_reports_kb_chunks_and_questions_bank`
  - `test_golden_topic_coverage_baseline_exists`

### A4.5 KB Evidence To SourceManifest Mapper

- ID：`A4.5`
- Owner：AI Backend + Backend
- Files touched：
  - `deeptutor/exam_classroom/services/source_manifest_mapper.py`
  - `deeptutor/exam_classroom/schemas/source_manifest.py`
  - RAG evidence contract tests
- Output：
  - `RAGService` evidence 到 `source_manifest` 的确定性映射
- Acceptance criteria：
  - `kb_chunks.chunk_id` 能映射为 `provenance.chunk_id`
  - `questions_bank.id` 能映射为 `provenance.question_id`
  - evidence 保留 `source_table / source_type / source_doc / node_code / standard_code / exam_year`
  - `questions_bank` 可作为 quiz/case/rubric evidence
  - mapper 只登记来源，不写 `lesson_ir`
- Forbidden shortcuts：
  - 不得让 generator 直接拼 Supabase row
  - 不得丢弃 `questions_bank` provenance
  - 不得把 `source_doc` 当作版权结论
- Tests：
  - `test_generation_uses_rag_service_not_direct_supabase`
  - `test_source_manifest_maps_kb_chunks_and_questions_bank`
  - `test_evidence_bundle_preserves_source_table`
  - `test_questions_bank_case_study_sources_can_be_cited`

### A4.6 RAGEvidenceContractPatch

- ID：`A4.6`
- Owner：AI Backend + Tech Lead
- Files touched：
  - `deeptutor/services/rag/...`
  - `deeptutor/exam_classroom/services/rag_evidence_adapter.py`
  - RAG contract tests
- Output：
  - 课堂生成可消费的稳定 `RAGEvidence` contract
- Acceptance criteria：
  - `source_table` 必填，取值只能是 `kb_chunks / questions_bank`
  - `source_type` 必填
  - `kb_chunks` evidence 必须有 `chunk_id`
  - `questions_bank` evidence 必须有 `question_id`
  - `node_code / standard_code / exam_year / content_hash` 如存在必须保留
  - 无 `source_table` 的 evidence 被拒绝进入 `source_manifest`
- Forbidden shortcuts：
  - 不得让生成器靠 `source_doc` 或自然语言标题猜来源
  - 不得为 OpenMAIC 课堂新建绕过 `RAGService` 的 Supabase client
- Tests：
  - `test_rag_evidence_has_source_table`
  - `test_rag_evidence_has_stable_id`
  - `test_questions_bank_evidence_has_question_id`
  - `test_kb_chunks_evidence_has_chunk_id`
  - `test_evidence_without_source_table_rejected`

### A4.7 KnowledgeCoverageReportService

- ID：`A4.7`
- Owner：AI Backend + 教研专家
- Files touched：
  - `deeptutor/exam_classroom/services/knowledge_coverage_report_service.py`
  - `deeptutor/exam_classroom/schemas/knowledge_coverage_report.py`
- Output：
  - 生成前覆盖预检和 scene eligibility 判断
- Acceptance criteria：
  - 输出 topic coverage、source family coverage、scene eligibility、source gaps、risk level
  - `slide` 至少有 `standard` 或 `textbook` evidence
  - `quiz` 至少有 `questions_bank` 或 `exam` evidence
  - `case` 必须有 `questions_bank.case_study`、`grading_rubric`、`grading_keywords` 或人工 rubric 来源
  - 低覆盖 topic 强制进入 `review_required` 或降级 scene 类型
- Forbidden shortcuts：
  - 不得把 coverage count 当成质量结论
  - 不得在 coverage 不足时让 LLM 静默补写
- Tests：
  - `test_topic_outline_requires_standard_or_textbook`
  - `test_quiz_requires_questions_bank_or_exam_evidence`
  - `test_case_requires_rubric_evidence`
  - `test_low_coverage_topic_forces_review_required`

### A5 Fixture player

- ID：`A5`
- Owner：Frontend + Backend
- Files touched：
  - `GET /api/exam-classrooms/{id}`
  - `wx_miniprogram/pages/exam-classroom/...`
  - `wx_miniprogram/components/exam-classroom/...`
  - `yousenwebview/packageDeeptutor/pages/exam-classroom/...`
  - `yousenwebview/packageDeeptutor/components/exam-classroom/...`
  - fixtures
- Output：
  - 小程序 Player 静态渲染四类 scene
  - 宿主包可同步/适配
- Acceptance criteria：
  - 小程序前端只读取 `lesson_ir`
  - `slide / whiteboard / quiz / case` 能展示
  - 不依赖 projection 表
  - `packageDeeptutor` 保留宿主路由、登录、会员和点数适配
- Forbidden shortcuts：
  - 不得单独从 `scene` 表拼内容
  - 不得先交 Web-only player 作为 P0 完成
- Tests：
  - `test_player_payload_reads_lesson_ir_only`
  - `wx_miniprogram` fixture render smoke
  - `packageDeeptutor` selective-sync smoke
  - 微信开发者工具模拟器 smoke

### A5.1 SceneRuntimeCore

- ID：`A5.1`
- Owner：Mini-program Frontend + Export Engineer + Tech Lead
- Files touched：
  - `packages/exam-classroom-runtime/scene_vm.ts`
  - `packages/exam-classroom-runtime/action_interpreter.ts`
  - `packages/exam-classroom-runtime/block_normalizer.ts`
  - `packages/exam-classroom-runtime/layout_tokens.ts`
  - `packages/exam-classroom-runtime/validation.ts`
  - `packages/exam-classroom-runtime/fallback_policy.ts`
- Output：
  - 平台无关的 scene runtime core
- Acceptance criteria：
  - 不依赖 DOM / React / Window / Document / `wx`
  - 输出平台无关 render model
  - 校验 action timeline 引用存在的 block / actor / question
  - 定义 scene 级降级策略
- Forbidden shortcuts：
  - 不得把 React component 作为跨端共享核心
  - 不得让小程序、HTML、PPTX adapter 各自解释 `lesson_ir`
- Tests：
  - `test_scene_runtime_core_has_no_dom_or_wx_dependency`
  - `test_scene_runtime_validates_action_targets`
  - `test_scene_runtime_outputs_platform_neutral_render_model`

### A5.2 WxRendererAdapter

- ID：`A5.2`
- Owner：Mini-program Frontend
- Files touched：
  - `wx_miniprogram/components/exam-classroom/classroom-player/...`
  - `wx_miniprogram/components/exam-classroom/slide-scene/...`
  - `wx_miniprogram/components/exam-classroom/whiteboard-scene/...`
  - `wx_miniprogram/components/exam-classroom/quiz-scene/...`
  - `wx_miniprogram/components/exam-classroom/case-scene/...`
- Output：
  - WXML / WXSS / Canvas 小程序渲染适配
- Acceptance criteria：
  - `slide / whiteboard / quiz / case` 都消费 runtime core render model
  - `whiteboard` 支持 Canvas / WXML card / static image fallback
  - `case_mode` 长文本输入不丢失
  - 音频失败自动字幕回退
- Forbidden shortcuts：
  - 不得在小程序端运行任意 HTML/CSS/JS
  - 不得用 WebView/iframe 承载 P0 课堂播放器
- Tests：
  - `test_wx_renderer_consumes_scene_runtime_render_model`
  - `test_wx_whiteboard_static_fallback`
  - 微信开发者工具 smoke

### A5.3 WxActionTimelineExecutor

- ID：`A5.3`
- Owner：Mini-program Frontend
- Files touched：
  - `wx_miniprogram/services/exam-classroom/timeline-executor.ts`
  - `yousenwebview/packageDeeptutor/services/exam-classroom/timeline-executor.ts`
- Output：
  - 小程序 action timeline 执行器
- Acceptance criteria：
  - 支持 `play / pause / resume / seek / scene switch`
  - quiz/case 出现时播放自然暂停
  - hide/show 后恢复到正确 scene/action
  - 单 scene 渲染失败只降级当前 scene
- Forbidden shortcuts：
  - 不得把 timeline 状态藏进不可恢复的组件局部变量
- Tests：
  - `test_wx_timeline_pauses_for_quiz_case`
  - `test_wx_background_resume_restores_scene_action`
  - `test_wx_scene_error_degrades_current_scene_only`

### A5.4 WxJobProgressAdapter

- ID：`A5.4`
- Owner：Backend + Mini-program Frontend
- Files touched：
  - `GET /api/exam-classrooms/jobs/{job_id}?include_events_after={seq}`
  - `GET /api/exam-classrooms/jobs/{job_id}/events-lite?after={seq}`
  - `wx_miniprogram/services/exam-classroom/job-progress.ts`
- Output：
  - 小程序 job 进度轮询/增量事件适配
- Acceptance criteria：
  - 小程序端不用浏览器 EventSource
  - 断网/切后台/返回后能恢复 job 状态
  - `outline_ready / scene_ready / quality_check / course_ready` 不丢
  - 重复事件通过 `seq` 去重
  - 最坏情况下轮询也能完成一键生成体验
- Forbidden shortcuts：
  - 不得把微信小程序稳定消费 SSE 作为 P0 依赖
- Tests：
  - `test_wx_job_progress_polling_recovers_after_resume`
  - `test_wx_job_events_deduplicate_by_seq`
  - `test_wx_job_progress_completes_without_sse`

### A5.5 WxTurnSocketManager

- ID：`A5.5`
- Owner：Mini-program Frontend + Backend
- Files touched：
  - `wx_miniprogram/services/exam-classroom/wx-turn-socket-manager.ts`
  - `yousenwebview/packageDeeptutor/services/exam-classroom/wx-turn-socket-manager.ts`
- Output：
  - 小程序统一课堂 turn socket manager
- Acceptance criteria：
  - 统一走 `/api/v1/ws`
  - 支持 connect / reconnect / heartbeat / token refresh / hide-show resume
  - `ClassroomGroundingContext` 作为 metadata 发送
  - `trace_id` 能关联后端 turn trace
  - pending turn 能恢复或明确失败
- Forbidden shortcuts：
  - 不得为 job progress、chat、TTS、review 各自开 turn socket
  - 不得把整段 `lesson_ir` 拼进 `message.content`
  - 不得让小程序端自己选择 capability
- Tests：
  - `test_wx_ws_reconnect_preserves_turn_trace`
  - `test_wx_grounding_context_sent_as_metadata`
  - `test_wx_does_not_append_lesson_ir_to_message_content`
  - `test_wx_background_resume_fetches_latest_turn_state`

### A5.6 WxAssetManifestAndPrefetch

- ID：`A5.6`
- Owner：Mini-program Frontend + Backend
- Files touched：
  - `lesson_ir.asset_manifest`
  - `wx_miniprogram/services/exam-classroom/asset-prefetch.ts`
- Output：
  - 小程序资产清单、懒加载和预取策略
- Acceptance criteria：
  - classroom payload 压缩后建议 <= 500KB，超出分页/懒加载
  - 图片、音频、白板 fallback asset 可按 scene 懒加载
  - 弱网下首屏优先加载当前 scene
  - asset miss 只降级当前 scene
- Forbidden shortcuts：
  - 不得把整堂课所有大资源打进首屏 payload
- Tests：
  - `test_wx_payload_budget_enforced`
  - `test_wx_scene_assets_lazy_loaded`
  - `test_wx_asset_miss_degrades_current_scene`

### A5.7 WxSourceUploadAdapter

- ID：`A5.7`
- Owner：Backend + Mini-program Frontend
- Files touched：
  - `POST /api/sources/upload-sessions`
  - `wx_miniprogram/services/source-upload/...`
  - `yousenwebview/packageDeeptutor/services/source-upload/...`
  - `SourceIngestionService`
- Output：
  - 小程序资料上传到 source ingestion 的闭环
- Acceptance criteria：
  - 生成 job 不直接接收 raw file
  - job 只能接收 `source_manifest_id` / `source_ingestion_id`
  - 小程序上传资料默认 `private_study`
  - 上传失败、解析失败、低置信度进入 `review_required`
  - 机构教研审核后才能升级到 `internal_training / commercial_course`
- Forbidden shortcuts：
  - 不得让前端上传绕过 `SourceIngestionService`
  - 不得在 ingestion 未完成时让 generator 引用资料
- Tests：
  - `test_wx_upload_creates_source_ingestion_before_generation`
  - `test_generation_job_rejects_raw_file_payload`
  - `test_low_confidence_ingestion_requires_review`

### A5.8 PackageDeeptutorSyncManifest

- ID：`A5.8`
- Owner：Host Mini-program Integrator
- Files touched：
  - `docs/openmaic/package-deeptutor-sync-manifest.yaml`
  - sync smoke tests
- Output：
  - `wx_miniprogram -> yousenwebview/packageDeeptutor` selective sync contract
- Acceptance criteria：
  - 明确 include / exclude / host_adapters
  - 保留宿主路由、登录、会员、点数、workspace shell
  - `packageDeeptutor` 不是 raw mirror
- Forbidden shortcuts：
  - 不得整包覆盖 `packageDeeptutor`
- Tests：
  - `test_package_deeptutor_sync_preserves_host_routes`
  - `test_package_deeptutor_sync_preserves_membership_adapter`
  - `test_package_deeptutor_sync_preserves_points_adapter`

### A5.9 MiniProgramReleaseGate

- ID：`A5.9`
- Owner：QA + Mini-program Frontend + Host Mini-program Integrator
- Files touched：
  - mini-program release checklist
  - smoke test scripts
- Output：
  - 小程序 P0 release gate
- Acceptance criteria：
  - 微信开发者工具 smoke 通过
  - iOS 真机 smoke 通过
  - Android 真机 smoke 通过
  - 弱网/断网/恢复后 job 状态可恢复
  - app hide/show 后播放器状态不乱
  - 首屏进入课堂不白屏
  - quiz/case 提交后不会重复扣点
  - `packageDeeptutor` selective sync smoke 通过
- Forbidden shortcuts：
  - 不得只用 Web/Admin 或本地单测替代小程序 smoke
- Tests：
  - `test_mini_program_release_gate_checklist_complete`
  - 微信开发者工具 smoke
  - iOS / Android 真机 smoke

### A6 Generation job

- ID：`A6`
- Owner：AI Backend + Backend
- Files touched：
  - `POST /api/exam-classrooms/jobs`
  - `classroom_jobs`
  - generation worker
- Output：
  - 生成 job 写入 `lesson_ir`
- Acceptance criteria：
  - 生成成功后 `exam_classrooms.lesson_ir` 完整
  - `retrieve_sources` 只通过 `RAGService` 访问 `construction-exam`
  - `kb_chunks / questions_bank` evidence 先进入 `source_manifest` 再被 generator 引用
  - quiz/case/rubric 生成必须优先复用 `questions_bank` evidence
  - evidence 不足的 scene 写入 `source_gap`
  - SSE 显示 `queued / running / succeeded`
  - job 失败不会产生无状态半残课堂
  - `idempotency_key` 相同且 `request_hash` 相同返回同一个 job
- Forbidden shortcuts：
  - 不得先落 `scene` 主表再回填 `lesson_ir`
  - 不得让 SSE 承担聊天 token stream
- Tests：
  - `test_generate_job_writes_lesson_ir_once`
  - `test_generate_job_retrieves_sources_through_rag_service`
  - `test_generate_job_registers_kb_evidence_before_generation`
  - `test_low_kb_coverage_creates_source_gap`
  - `test_job_events_are_non_chat_sse`
  - `test_job_idempotency_returns_same_job`

### A6.1 Evidence-aware Outline Planner

- ID：`A6.1`
- Owner：AI Backend + 教研专家
- Files touched：
  - outline planner
  - generation prompt templates
  - source coverage tests
- Output：
  - 绑定 evidence 的课堂 outline
- Acceptance criteria：
  - 每个 outline item 绑定 candidate `source_id`
  - 没有 source 的 item 只能标记为教学组织语句
  - outline 不得引用未注册 source
  - `KnowledgeCoverageReport` 未通过时不生成正式 outline
- Forbidden shortcuts：
  - 不得让 LLM 先自由列大纲，再事后补 citation
  - 不得把 citation 覆盖率当作 evidence-aware outline 的替代品
- Tests：
  - `test_outline_item_requires_candidate_source_ids`
  - `test_unregistered_source_rejected_in_outline`
  - `test_outline_blocked_without_knowledge_coverage_report`

### A6.2 QuestionsBank-first Quiz/Case Generator

- ID：`A6.2`
- Owner：AI Backend + 教研专家
- Files touched：
  - quiz generator
  - case generator
  - rubric generator
- Output：
  - 题库优先的 quiz/case/rubric 生成
- Acceptance criteria：
  - quiz/case 优先检索 `questions_bank`
  - case scene 必须有 case/rubric evidence，否则降级为非正式训练或不生成
  - LLM 只能做改写、变式、讲解、结构化整理，不得凭空编 rubric
  - 每个评分点可回指 `source_id` 或人工 rubric 来源
- Forbidden shortcuts：
  - 不得凭空生成案例背景和评分点
  - 不得用泛用 short-answer grading 替代建筑实务 rubric
- Tests：
  - `test_quiz_generator_uses_questions_bank_first`
  - `test_case_generator_requires_case_or_rubric_evidence`
  - `test_case_scene_degrades_when_questions_bank_evidence_missing`
  - `test_rubric_points_reference_source_ids`

### A7 Scene regeneration CAS

- ID：`A7`
- Owner：Backend + AI Backend
- Files touched：
  - `POST /api/exam-classrooms/{id}/scene-regeneration-jobs`
  - `LessonIRService.replace_scene_from_job`
- Output：
  - 局部重生成
- Acceptance criteria：
  - 只替换指定 `scene_key`
  - 其他 scene 不变
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
- Output：
  - 得分、命中点、漏点、优化答案、`weak_tags`
- Acceptance criteria：
  - 学员作答后得到结构化 grading 结果
  - `question_attempts` 保存原始作答和评分结果
  - grading 结果包含 hit_points / missing_points / improved_answer
- Forbidden shortcuts：
  - 不得直接把 grading 结果写进 `user_stats`
  - 不得用泛用 LLM 评价替代 rubric-driven grading
- Tests：
  - `test_case_grading_writes_question_attempt`
  - `test_grading_result_contains_weak_tags`
  - `test_case_grading_uses_rubric_points`

### A9 learner writeback

- ID：`A9`
- Owner：Backend
- Files touched：
  - writeback adapter
  - learner-state integration
- Output：
  - `learner_memory_events`
  - learner-state 结构化写回
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
- Output：
  - `draft / review_required / approved / published`
- Acceptance criteria：
  - blocker/high 未解决不能 `approved`
  - `review_items` 只是 issue projection
  - `quality_report` 是审核主输出
  - `score_total < 75` 只能保持 `draft`
  - `75 <= score_total < 85` 必须 `review_required`
- Forbidden shortcuts：
  - 不得把 `review_items.status` 直接当发布状态
- Tests：
  - `test_open_blocker_prevents_approval`
  - `test_quality_score_below_75_keeps_draft`
  - `test_review_items_are_projection_only`

### A11 export snapshot

- ID：`A11`
- Owner：Backend + Export engineer
- Files touched：
  - `classroom_exports`
  - export service adapter
- Output：
  - `PPTX / HTML / ZIP`
- Acceptance criteria：
  - 导出记录 `release_version / lesson_ir_revision / lesson_ir_hash`
  - 导出只来自 `approved` snapshot
  - `lesson.json` 为唯一 canonical 内容文件
  - PPTX 在 PowerPoint / WPS 可打开
  - HTML 能离线或内网打开
- Forbidden shortcuts：
  - 不得导出正在变化的 draft
  - 不得引入 `course.json`
- Tests：
  - `test_export_uses_approved_snapshot_only`
  - `test_export_records_source_revision_and_hash`
  - `test_pptx_has_no_empty_slides`
  - `test_zip_contains_lesson_manifest_assets_citations_questions`

### A12 ACL + provenance + runtime gate

- ID：`A12`
- Owner：Backend + Ops + Tech Lead
- Files touched：
  - ACL policy
  - object storage path policy
  - runtime budget fields
- Output：
  - 最小权限矩阵
  - object storage 授权
  - runtime cost gate
- Acceptance criteria：
  - `tenant_id`、`created_by` 强制存在
  - export 通过 signed URL + tenant check + permission check
  - object storage path 使用 `tenants/{tenant_id}/exam_classrooms/{classroom_id}/exports/{export_id}/...`
  - `classroom_jobs` 含 `idempotency_key / trace_id / max_runtime_seconds / max_llm_tokens / estimated_cost_cents / actual_cost_cents / retry_count`
- Forbidden shortcuts：
  - 不得让公开导出绕过 tenant 和 permission check
  - 不得让成本字段只存在日志里
- Tests：
  - `test_export_requires_tenant_and_permission_check`
  - `test_signed_url_requires_permission`
  - `test_job_budget_blocks_runaway_generation`

### A13 LessonQualityEvaluator

- ID：`A13`
- Owner：AI Backend + 教研专家 + Reviewer tooling
- Files touched：
  - `deeptutor/exam_classroom/services/lesson_quality_evaluator.py`
  - `quality_report` tests
- Output：
  - 结构化质量评测
  - publishability 判断
  - review item projection
- Acceptance criteria：
  - 输出 `score_total / dimensions / blockers / warnings / publishable`
  - 覆盖结构、来源、知识覆盖、教学、考试、移动端播放、交互、案例评分、导出 readiness
  - `source_grounding` 使用 `source_manifest` 和 RAG evidence coverage，而不是只数 citation 文本
  - `questions_bank` evidence 缺失时，case/quiz 质量不能判为满分
  - blocker/high 自动投影成 `review_items`
  - 评测结果进入 One-click Generation Gate
- Forbidden shortcuts：
  - 不得让 evaluator 修改 `lesson_ir` 内容
  - 不得用一个总分掩盖重大事实错误
- Tests：
  - `test_quality_evaluator_writes_quality_report_only`
  - `test_major_factual_error_is_blocker`
  - `test_weak_citation_creates_review_item`
  - `test_source_grounding_uses_kb_coverage_report`
  - `test_case_scene_without_rubric_evidence_cannot_approve`

### A13.1 Domain Superiority Benchmark

- ID：`A13.1`
- Owner：教研专家 + AI Backend + QA
- Files touched：
  - domain benchmark fixtures
  - benchmark scoring scripts
  - benchmark reports
- Output：
  - 建筑实务领域胜出指标，不与 OpenMAIC 做泛功能堆叠竞赛
- Acceptance criteria：
  - 至少 10 个黄金考点
  - 每个考点同时评估考点命中、来源可追溯、题库使用、案例评分、弱点诊断、小程序完成率、导出与审核
  - 输出 `domain_superiority_score`
  - OpenMAIC black-box 只做体验参考，不复制输出、prompt、schema、UI 或素材
- Forbidden shortcuts：
  - 不得用“功能数量”替代建筑实务提分效果
  - 不得把 OpenMAIC 体验对标升级成实现资产参考
- Tests：
  - `test_domain_superiority_benchmark_scores_exam_training_depth`
  - `test_domain_benchmark_requires_source_manifest`
  - `test_domain_benchmark_requires_case_grading_signal`

### A13.2 Regression Harness For Prompt / Model Changes

- ID：`A13.2`
- Owner：AI Backend + QA + Observability
- Files touched：
  - regression harness
  - golden fixtures
  - CI / release gate wiring
- Output：
  - prompt、model、retrieval 改动后的质量回归门禁
- Acceptance criteria：
  - 每次改 prompt / model / retrieval 后跑 30 个黄金考点
  - 跑 50 份案例评分样本
  - 跑 10 个导出样本
  - 跑小程序 fixture smoke
  - 对比上一次 baseline，输出退化项和阻断项
- Forbidden shortcuts：
  - 不得只凭单个 demo 样例判断质量提升
  - 不得把本地 prompt smoke 当成可发布证据
- Tests：
  - `test_regression_harness_detects_source_grounding_regression`
  - `test_regression_harness_detects_case_grading_regression`
  - `test_regression_harness_blocks_export_regression`

---

## 5. 第一周切片

第一周禁止接真实 LLM。

### Slice 1: Canonical Lesson IR Fixture

交付：

- `Lesson IR schema`
- `exam_classrooms` 表
- `mass_concrete.lesson.json`
- `network_plan.lesson.json`
- `claim_analysis.lesson.json`
- `GET /api/exam-classrooms/{id}`
- `Scene Runtime Core`
- 微信小程序 Player 静态渲染
- `packageDeeptutor` selective sync smoke

验收：

1. 没有 `classroom_scenes` primary table
2. 小程序 Player 只通过 runtime core 读取 `lesson_ir`
3. 四类 scene 可显示
4. 微信开发者工具 smoke 通过
5. iOS/Android 真机 smoke 至少完成基础进入课堂

### Slice 2: Mock grading + mock ZIP + job progress

交付：

- case submit
- mock grading
- mock ZIP export
- 小程序 job progress 轮询
- outline_ready / scene_ready / quality_summary / course_ready 状态展示

验收：

1. 证明 authority 干净
2. 证明导出不依赖第二份 truth
3. 证明小程序端不依赖浏览器 EventSource

---

## 6. 七个质量闸门

### Gate 1: Contract Gate

必须检查：

- 没有第二套课堂聊天 WebSocket
- 没有 `/ask` streaming endpoint
- 没有 `classroom_scenes / classroom_actions / exam_questions` primary table
- 没有 router / worker / exporter 直接写 `lesson_ir`
- 没有互动课堂模块直接写 `user_stats`
- 没有 `course.json / TeachStudio / exam_courses` 回流

### Gate 2: Generation Gate

必须检查：

- LLM 输出必须通过 Pydantic / Zod schema
- JSON repair 最多 2 次，失败明确返回
- `retrieve_sources` 只通过 `RAGService`
- `RAGEvidence` 必须具备 `source_table` 和 stable id
- 没有 `KnowledgeCoverageReport` 不得生成 outline
- `source_manifest` 先登记 KB evidence，再进入生成
- 每个 scene 有 `learning_objective`
- 每个 scene 有 `scene_key`
- 每个 question 有 `question_key`
- 每个 case 有 rubric
- 每个关键知识点有 citation 或资料不足提示
- job 失败不会产生半残课堂

### Gate 3: Playback Gate

必须检查：

- 小程序 Player 只消费 `lesson_ir`
- 小程序 Player 通过 `Scene Runtime Core` 解释 scene
- `slide / whiteboard / quiz / case` 四类 scene 都能渲染
- action timeline 不引用不存在的 block / actor / question
- 用户答题时 timeline 能暂停
- scene 重生成后播放器不会崩
- 单个 scene 出错只降级该 scene，不拖垮整堂课
- `yousenwebview/packageDeeptutor` 宿主包 smoke 通过

### Gate 4: Content Gate

必须检查：

- 知识点符合一建建筑实务
- 案例题符合考试表达
- 标准答案有评分点
- 常见扣分点合理
- `weak_tags` 能指导重学
- 无来源内容被标记
- `kb_chunks / questions_bank` 覆盖不足的 topic 被标记为 `source_gap`
- 教研专家对黄金样本打分

### Gate 5: Knowledge Base Coverage Gate

必须检查：

- 30 个黄金考点有知识库覆盖 baseline
- topic outline 至少有 `standard` 或 `textbook` evidence
- quiz/case scene 至少有 `questions_bank` 或 `exam` evidence
- case rubric 有题库、真题、教材评估题或人工 rubric 来源
- 没有 `questions_bank` case/rubric evidence 不得生成正式 `case` scene
- `questions_bank` 不被当作 P1 资产遗漏
- evidence 不足的 scene 进入 `review_required` 或产生 blocker/high review item

### Gate 6: Export / Release Gate

必须检查：

- PPTX 能在 PowerPoint / WPS 打开
- PPTX 无明显文本溢出
- HTML 能离线或内网打开
- ZIP 包含 `lesson.json / manifest / assets / citations / questions`
- 导出来自 approved snapshot
- 导出记录 `release_version / lesson_ir_revision / lesson_ir_hash`
- 未审核或来源不明内容不能 `published`

### Gate 7: Mini-program Release Gate

必须检查：

- 微信开发者工具 smoke 通过
- iOS 真机 smoke 通过
- Android 真机 smoke 通过
- 弱网/断网/恢复后 job 状态可恢复
- app hide/show 后播放器状态不乱
- classroom payload 不超预算
- 首屏进入课堂不白屏
- 单 scene 渲染失败只降级当前 scene
- 音频失败自动字幕回退
- case 长文本输入不丢失
- quiz/case 提交后不会重复扣点
- `packageDeeptutor` selective sync smoke 通过

---

## 7. 三套评测集

### 7.1 30 个建筑实务黄金考点评测集

每个考点固定评估：

1. 大纲是否合理
2. scene 类型是否合适
3. 讲解顺序是否像老师
4. 白板是否帮助理解
5. quiz 是否检查核心点
6. case 是否符合考试题风格
7. rubric 是否能打分
8. `weak_tags` 是否准确
9. `standard / textbook / questions_bank` evidence 是否足够
10. `source_gap` 是否被正确标记
11. 小程序播放是否可用
12. PPTX 是否可用
13. HTML 是否可用

首批建议覆盖：

- 大体积混凝土裂缝控制
- 网络计划关键线路
- 施工索赔
- 屋面防水
- 深基坑安全
- 脚手架
- 模板工程
- 混凝土浇筑
- 质量事故处理
- 竣工验收资料

2026-04-24 知识库扫描显示，`质量事故处理` 在 `kb_chunks / questions_bank` 中的粗略命中相对偏低。进入 P0 试点前，要么补库，要么把该主题标为高风险样本并要求人工教研重点审核。

### 7.2 案例题评分一致性评测集

至少 50 份人工评分样本。

| 指标 | P0 合格线 |
| --- | --- |
| AI 总分与人工总分 MAE | <= 1.5 / 10 分 |
| 关键评分点命中 recall | >= 80% |
| 错误扣分点误报率 | <= 15% |
| `weak_tags` 人工认可率 | >= 75% |
| 优化答案可背诵性评分 | >= 4 / 5 |

### 7.3 OpenMAIC black-box 对标评测集

只做体验对标，不复制输出、prompt、schema、UI 或素材。

建议 10-15 个 prompt：

- Teach me mass concrete crack control.
- Teach me construction claim analysis.
- Teach me critical path method.
- Teach me roof waterproofing quality control.
- Teach me deep foundation pit safety.

评估维度：

| 维度 | 权重 |
| --- | --- |
| 一键生成完整度 | 15% |
| 教学结构 | 15% |
| 交互体验 | 15% |
| 白板 / 可视化 | 10% |
| 测验质量 | 10% |
| 案例训练质量 | 15% |
| 导出质量 | 10% |
| 稳定性 | 10% |

### 7.4 Domain Superiority Benchmark

这套评测不比较谁功能更炫，而是比较谁更能帮助一建建筑实务提分。

| 维度 | 权重 | 胜出标准 |
| --- | ---: | --- |
| 考点命中准确性 | 15% | 覆盖考试高频核心点 |
| 来源可追溯性 | 15% | 关键结论可回指 `source_manifest` |
| 真题/题库使用质量 | 15% | quiz/case 来自 `questions_bank / exam` evidence |
| 案例评分质量 | 20% | rubric 可评分，AI 评分接近人工 |
| 弱点诊断质量 | 10% | `weak_tags` 能指导重学 |
| 移动端学习完成率 | 10% | 小程序端能学完、能提交、不中断 |
| 导出与教研审核 | 10% | PPTX/HTML/ZIP 可用、可审、可追溯 |
| 课堂体验感 | 5% | TTS/白板/互动自然，不牺牲 authority |

目标：

- P0 不要求整体超过 OpenMAIC。
- P1 必须在建筑实务训练深度上超过 OpenMAIC black-box 样本。
- 如果 Domain Superiority Benchmark 下降，即使课堂看起来更炫，也不能作为质量提升。

---

## 8. P0.5 Experience Slice

P0.5 只在 P0 主链路通过后启动。它的目标是提升主观课堂感，不改变 P0 authority。

### F1 Scene-grounded Q&A

- 统一走 `/api/v1/ws`
- 使用 `ClassroomGroundingContext`
- 不新增 `/ask` streaming endpoint
- 不新增 first-class capability
- 小程序端只发送 grounding context，不把整段课堂内容拼进 `message.content`

最低效果：

```text
用户问：为什么保温保湿能减少大体积混凝土裂缝？
系统答：基于当前 scene、教材来源和考试表达，给出短解释、考试答法和引用依据。
```

### F2 Single-teacher TTS + subtitle sync

- P0.5 只做单老师 TTS
- TTS 失败回退字幕
- scene 级音频即可，不做多角色实时合成

### F3 Whiteboard action templates

优先做建筑实务高频模板：

- 原因链：水化热 -> 内外温差 -> 温度应力 -> 约束拉应力 -> 裂缝
- 流程链：事故发生 -> 报告 -> 保护现场 -> 调查 -> 处理 -> 验收
- 索赔链：事件 -> 责任 -> 关键线路 -> 工期 -> 费用 -> 证据
- 网络计划：节点 -> 线路 -> 总时差 -> 自由时差 -> 关键线路

### F4 Signature construction simulation

先做一个招牌仿真：

- 网络计划关键线路识别器

不要 P0.5 就做仿真矩阵。先证明一个建筑实务强相关仿真能稳定提升教学体验。

### F5 Immersive classroom layout polish

目标是让 P0 从“智能课件”接近“AI 互动课堂”：

- AI 老师字幕
- scene timeline
- 白板逐步展开
- 关键点高亮
- quiz/case 自然暂停

小程序优先级：

1. 单老师 TTS + 字幕同步
2. 白板模板
3. scene-grounded Q&A
4. 网络计划关键线路识别器
5. 角色氛围增强

---

## 9. P1 / P2 Backlog

P1：

- 课堂内多轮问答
- 对象级课堂连续性 contract 扩展
- 多角色 TTS
- 动态 AI 同学追问
- PBL lite
- 重点仿真模板
- read projections

P2：

- MP4 / Remotion 视频
- 批量章节生产
- 机构品牌模板
- Script / DOCX 导出
- 完整 PBL 状态机
- 大规模仿真矩阵

P1 启动前必须回答：

1. 为什么现有 `chat` capability 不够？
2. 是否真的需要对象级连续性？
3. 是否需要扩展 turn contract？
4. 新能力是否会制造第二套 transport、content truth 或 review state？

---

## 10. P0 成功标准

P0 完成时，必须同时满足：

1. `Lesson IR` 是唯一课程内容真相
2. `LessonIRService` 是唯一内容 writer
3. 微信小程序 Player 只通过 `Scene Runtime Core` 读取 `lesson_ir`
4. scene 重生成不会覆盖新 revision
5. grading 结果只经统一 pipeline 进入 learner-state
6. `PPTX / HTML / ZIP` 来自 approved snapshot
7. `SourceManifest` 和 citation gate 生效
8. `LessonQualityEvaluator` 生效
9. One-click Generation Gate 达到 P0 合格线
10. 没有任何 `/ask` streaming endpoint
11. 没有任何 scene/action/question primary truth tables
12. `yousenwebview/packageDeeptutor` 宿主包完成 selective sync smoke
13. Mini-program Release Gate 通过

---

## 11. 现实周期与团队假设

如果 DeepTutor 现有 RAG、WebSocket、learner-state、前端框架都可复用：

| 阶段 | 现实周期 |
| --- | --- |
| P0 技术闭环 | 8-12 周 |
| P0 商业可试点质量 | 12-16 周 |
| P0.5 体验增强 | +4-6 周 |
| P1 接近 OpenMAIC 核心体验 | +8-12 周 |
| P2 追 OpenMAIC v0.2.0 当前广度 | 6 个月以上 |

最小团队：

| 角色 | 人数 | 说明 |
| --- | --- | --- |
| Tech Lead | 1 | 守住架构和质量 |
| AI Backend | 1-2 | 生成器、RAG、评分、质量评测 |
| Backend | 1 | API、DB、job、权限、导出调度 |
| Mini-program Frontend | 1-2 | `wx_miniprogram` Player、Renderer、quiz/case、grounded Q&A 入口 |
| Host Mini-program Integrator | 0.5-1 | `yousenwebview/packageDeeptutor` selective sync、宿主路由、登录、会员和点数适配 |
| Web/Admin Frontend | 0-1 | 教研审核、运营管理、导出预览；不是 P0 学员端主表面 |
| Export Engineer | 0.5-1 | PPTX / HTML / ZIP |
| 教研专家 | 1 | 黄金样本和 rubric |
| QA | 0.5-1 | 自动化测试、导出测试、回归 |

---

## 12. 研发执行纪律

任何 PR 如果触发以下任一项，默认打回：

- 引入第二套 transport
- 引入第二套 schema 真相
- 引入第二套状态机
- 让 projection 反写 `lesson_ir`
- 让互动课堂模块绕过 learner-state
- 把 P1/P2 功能混进 P0
- 只交付功能清单，不交付 One-click Generation Gate 证据
- 只靠人工审核兜底，不接入 `LessonQualityEvaluator`
- 只写来源原则，不落 `SourceManifest / citation / copyright_level`
