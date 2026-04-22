# 建筑实务 AI 互动课堂系统实施任务拆解 v1.1

> 文档状态（2026-04-22）：
>
> - 本文件退居**任务素材**与执行拆解参考。
> - 所有 authority、transport、状态机、MVP 边界、命名收口，以 [建筑实务AI互动课堂_架构与实施收口_v1.2.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md) 为准。
> - `建筑实务AI互动课堂_Implementation_Plan_v1.0.docx` 与 `建筑实务AI互动课堂_PRD_v1.0.docx` 仅保留历史上下文，不再作为实施 authority。

> 本文档不是目标清单，而是研发可执行的实施计划。每个任务都包含：编号、负责人类型、依赖、交付物、验收标准。

---

## 0. 交付策略

项目按“纵向切片”交付，而不是按大模块长期憋大招。

第一条可用切片：

```text
输入考点 → 生成大纲 → 生成 slide/whiteboard/quiz/case → 播放 → 案例批改 → 导出 PPTX/HTML/ZIP
```

这条切片跑通后，再扩展 PBL、交互仿真、视频、班级系统。

---

## 1. 团队分工建议

| 角色 | 人数 | 主要职责 |
|---|---:|---|
| Tech Lead / 架构 | 1 | 架构、接口、Schema、代码质量 |
| AI Backend | 1-2 | 生成器、RAG、Agent、评分、Prompt |
| Backend | 1 | API、DB、任务队列、权限、导出调度 |
| Frontend | 1-2 | 生成页、大纲编辑器、播放器、渲染器 |
| Node Export Engineer | 0.5-1 | PPTX/HTML/ZIP/后期 MP4 |
| 教研专家 | 1 | 一建建筑实务考点、题目、评分 rubric |
| QA | 0.5-1 | 测试用例、回归测试、导出测试 |

最小团队：3 人研发 + 1 个教研兼职也能启动。

---

## 2. 里程碑总览

| 里程碑 | 周期 | 目标 | 是否可演示 |
|---|---:|---|---:|
| M0 技术地基 | 第 1 周 | Schema、DB、API 骨架、Job 框架 | 否 |
| M1 课程生成闭环 | 第 2-3 周 | 输入主题生成大纲和 scene | 是 |
| M2 课堂播放器 | 第 4-5 周 | 播放 slide/whiteboard/quiz/case | 是 |
| M3 考试训练闭环 | 第 6-7 周 | 案例评分、错题本、薄弱点 | 是 |
| M4 导出和审核 | 第 8-9 周 | PPTX/HTML/ZIP、审核流 | 是 |
| M5 OpenMAIC 体验增强 | 第 10-13 周 | 多 Agent、PBL、仿真、TTS 增强 | 是 |
| M6 视频和规模化 | 第 14-18 周 | MP4、批量生成、机构模板 | 是 |

建议：**M0-M4 是 MVP，M5-M6 是增强版。**

---

# M0：技术地基，第 1 周

## M0 目标

让系统具备“可生成、可保存、可追踪、可异步执行”的底座。

## M0.1 建立模块目录

| 字段 | 内容 |
|---|---|
| 编号 | M0.1 |
| 负责人 | Tech Lead + Backend |
| 任务 | 在 DeepTutor 中新增 exam_classroom capability 目录 |
| 交付物 | 后端目录、前端目录、导出服务目录 |
| 依赖 | 现有 DeepTutor 项目结构 |
| 验收 | 项目能启动，新增模块不会影响原有功能 |

建议目录：

```text
deeptutor/exam_classroom/
  __init__.py
  schemas/
  services/
  generators/
  orchestrators/
  graders/
  exporters/
  api/
  prompts/
web/components/exam-classroom/
web/app/exam-classroom/
render-export-service/
```

## M0.2 定义 Lesson IR v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M0.2 |
| 负责人 | AI Backend + Tech Lead |
| 任务 | 用 Pydantic 定义 LessonIR、SceneIR、ActionIR、QuestionIR |
| 交付物 | `schemas/lesson_ir.py`、JSON schema 导出 |
| 依赖 | M0.1 |
| 验收 | 5 个 fixture JSON 能通过校验；非法 JSON 能返回明确错误 |

必须覆盖：

- classroom metadata
- actors
- scenes
- actions
- questions
- citations
- exports
- quality_report

## M0.3 建立数据库表

| 字段 | 内容 |
|---|---|
| 编号 | M0.3 |
| 负责人 | Backend |
| 任务 | 创建 exam_classrooms、classroom_jobs、classroom_scenes 等表 |
| 交付物 | migration 文件 |
| 依赖 | M0.2 |
| 验收 | 本地 migration 成功；可创建 classroom、scene、job |

## M0.4 Job Queue 骨架

| 字段 | 内容 |
|---|---|
| 编号 | M0.4 |
| 负责人 | Backend |
| 任务 | 接入 Redis + Celery/Dramatiq，支持异步任务和重试 |
| 交付物 | worker 启动脚本、任务状态更新 |
| 依赖 | M0.3 |
| 验收 | 创建一个 dummy job，前端能看到 queued/running/success/failed |

## M0.5 SSE 进度接口

| 字段 | 内容 |
|---|---|
| 编号 | M0.5 |
| 负责人 | Backend + Frontend |
| 任务 | 实现 `/jobs/{id}/events` SSE |
| 交付物 | 后端接口 + 前端进度条 |
| 依赖 | M0.4 |
| 验收 | Worker 更新进度后，前端实时显示 |

## M0.6 Clean-room 规则文档

| 字段 | 内容 |
|---|---|
| 编号 | M0.6 |
| 负责人 | Tech Lead |
| 任务 | 明确不复制 OpenMAIC 代码、Prompt、Schema、UI、素材 |
| 交付物 | `docs/clean-room-openmaic.md` |
| 依赖 | 无 |
| 验收 | 团队确认，PR 模板加入 license checklist |

---

# M1：课程生成闭环，第 2-3 周

## M1 目标

输入一个建筑实务考点，系统能生成课程大纲和 4 类 scene：slide、whiteboard、quiz、case。

## M1.1 课程生成 API

| 字段 | 内容 |
|---|---|
| 编号 | M1.1 |
| 负责人 | Backend |
| 任务 | 实现 `POST /api/exam-classrooms/jobs` |
| 交付物 | API + 请求校验 |
| 依赖 | M0 |
| 验收 | 用户提交 topic 后生成 classroom_id 和 job_id |

## M1.2 Intent Parser

| 字段 | 内容 |
|---|---|
| 编号 | M1.2 |
| 负责人 | AI Backend |
| 任务 | 解析考试类型、科目、课程类型、学员水平、时长 |
| 交付物 | `parse_intent` generator |
| 依赖 | M1.1 |
| 验收 | 20 条自然语言输入中 18 条解析合理 |

测试样例：

```text
“讲一建建筑实务的大体积混凝土，适合冲刺，带案例题”
“我不会网络计划关键线路，给我讲简单点”
“做一节屋面防水的试听课”
```

## M1.3 Source Retriever

| 字段 | 内容 |
|---|---|
| 编号 | M1.3 |
| 负责人 | AI Backend |
| 任务 | 接入 DeepTutor Knowledge Hub 检索资料 |
| 交付物 | `retrieve_sources(topic, kb_ids)` |
| 依赖 | DeepTutor KB |
| 验收 | 输入考点能返回 source chunks；无资料时明确标记资料不足 |

## M1.4 Course Planner

| 字段 | 内容 |
|---|---|
| 编号 | M1.4 |
| 负责人 | AI Backend + 教研 |
| 任务 | 根据 intent + sources 生成课程大纲 |
| 交付物 | outline schema + prompt |
| 依赖 | M1.2、M1.3 |
| 验收 | 10 个建筑实务考点生成的大纲经教研评审 70% 可用 |

大纲必须包含：

- 课程标题
- 学习目标
- 章节/考点标签
- scene 列表
- 每个 scene 类型
- 预计时长
- 来源引用候选

## M1.5 大纲编辑器

| 字段 | 内容 |
|---|---|
| 编号 | M1.5 |
| 负责人 | Frontend |
| 任务 | 前端展示和编辑 outline |
| 交付物 | OutlineEditor 页面 |
| 依赖 | M1.4 |
| 验收 | 可改标题、调整 scene 顺序、删除 scene、保存 |

## M1.6 Slide Scene Generator

| 字段 | 内容 |
|---|---|
| 编号 | M1.6 |
| 负责人 | AI Backend |
| 任务 | 生成 slide_lecture scene_ir |
| 交付物 | slide generator + schema validation |
| 依赖 | M1.4 |
| 验收 | 生成的 slide blocks 可被前端渲染；每页不超过字数限制 |

## M1.7 Whiteboard Scene Generator

| 字段 | 内容 |
|---|---|
| 编号 | M1.7 |
| 负责人 | AI Backend |
| 任务 | 生成 whiteboard steps 和基础 actions |
| 交付物 | whiteboard generator |
| 依赖 | M1.4 |
| 验收 | 能生成流程图/时间轴/答题模板三种白板 |

## M1.8 Quiz Scene Generator

| 字段 | 内容 |
|---|---|
| 编号 | M1.8 |
| 负责人 | AI Backend + 教研 |
| 任务 | 生成单选、多选、判断题 |
| 交付物 | question generator |
| 依赖 | M1.4 |
| 验收 | 每道题有答案、解析、考点、难度、引用 |

## M1.9 Case Scene Generator

| 字段 | 内容 |
|---|---|
| 编号 | M1.9 |
| 负责人 | AI Backend + 教研 |
| 任务 | 生成案例简答题和 rubric |
| 交付物 | case scene generator |
| 依赖 | M1.4 |
| 验收 | 案例题包含题干、标准答案、评分点、常见扣分点 |

## M1.10 Source Verifier v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M1.10 |
| 负责人 | AI Backend |
| 任务 | 检查 scene 中关键知识是否有来源 |
| 交付物 | source verifier |
| 依赖 | M1.6-M1.9 |
| 验收 | 无来源内容标记 `needs_review`，不阻塞草稿生成 |

## M1.11 单 scene 重生成

| 字段 | 内容 |
|---|---|
| 编号 | M1.11 |
| 负责人 | Backend + AI Backend + Frontend |
| 任务 | 支持对某个 scene 局部重生成 |
| 交付物 | API + 前端按钮 |
| 依赖 | M1.6-M1.9 |
| 验收 | 可输入“讲得更简单”，只重生成当前 scene |

---

# M2：互动课堂播放器，第 4-5 周

## M2 目标

生成的课程可以像课堂一样播放，而不是只能看 JSON 或静态页面。

## M2.1 Classroom Payload API

| 字段 | 内容 |
|---|---|
| 编号 | M2.1 |
| 负责人 | Backend |
| 任务 | 实现 `GET /api/exam-classrooms/{id}` |
| 交付物 | 聚合返回 lesson_ir、scenes、actions、questions、assets |
| 依赖 | M1 |
| 验收 | 前端一次请求能拿到播放所需数据 |

## M2.2 ClassroomPlayer 框架

| 字段 | 内容 |
|---|---|
| 编号 | M2.2 |
| 负责人 | Frontend |
| 任务 | 实现播放器基本布局和状态机 |
| 交付物 | ClassroomPlayer component |
| 依赖 | M2.1 |
| 验收 | 支持播放、暂停、上一节、下一节、进度条 |

## M2.3 SlideRenderer

| 字段 | 内容 |
|---|---|
| 编号 | M2.3 |
| 负责人 | Frontend |
| 任务 | 渲染 slide blocks |
| 交付物 | SlideRenderer |
| 依赖 | M1.6、M2.2 |
| 验收 | title、bullet、process、comparison、table 五类 block 可显示 |

## M2.4 WhiteboardRenderer

| 字段 | 内容 |
|---|---|
| 编号 | M2.4 |
| 负责人 | Frontend |
| 任务 | SVG 白板渲染和分步显示 |
| 交付物 | WhiteboardRenderer |
| 依赖 | M1.7、M2.2 |
| 验收 | 流程图、时间轴、树状图可按步骤出现 |

## M2.5 QuizRenderer

| 字段 | 内容 |
|---|---|
| 编号 | M2.5 |
| 负责人 | Frontend + Backend |
| 任务 | 支持选择题作答和即时反馈 |
| 交付物 | QuizRenderer + attempt API |
| 依赖 | M1.8 |
| 验收 | 用户答题后显示正确/错误和解析 |

## M2.6 CasePracticeRenderer

| 字段 | 内容 |
|---|---|
| 编号 | M2.6 |
| 负责人 | Frontend |
| 任务 | 案例题作答界面 |
| 交付物 | CasePracticeRenderer |
| 依赖 | M1.9 |
| 验收 | 用户可输入长文本答案并提交 |

## M2.7 Action Timeline Executor

| 字段 | 内容 |
|---|---|
| 编号 | M2.7 |
| 负责人 | Frontend |
| 任务 | 根据 actions 驱动字幕、高亮、白板步骤、测验暂停 |
| 交付物 | action executor |
| 依赖 | M2.2-M2.6 |
| 验收 | speak、highlight、whiteboard_draw、show_quiz、wait_for_answer 可执行 |

## M2.8 Actor Panel

| 字段 | 内容 |
|---|---|
| 编号 | M2.8 |
| 负责人 | Frontend |
| 任务 | 显示 AI 老师、小白同学、阅卷官等角色 |
| 交付物 | ActorPanel |
| 依赖 | M2.2 |
| 验收 | 当前发言角色高亮，字幕区显示角色名 |

## M2.9 TTS v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M2.9 |
| 负责人 | Backend + AI Backend |
| 任务 | 接入一个 TTS provider，按 scene 生成音频 |
| 交付物 | TTS job + audio asset |
| 依赖 | M1 narration |
| 验收 | 老师 narration 可播放；失败回退字幕 |

## M2.10 课堂内提问 v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M2.10 |
| 负责人 | AI Backend + Frontend |
| 任务 | 用户可基于当前 scene 提问 |
| 交付物 | `/ask` API + chat panel |
| 依赖 | M2.1 |
| 验收 | 回答必须引用当前 scene 或知识库，不能跑题 |

---

# M3：考试训练闭环，第 6-7 周

## M3 目标

从“会看课”升级到“能提分”：做题、批改、错题、薄弱点、重学课。

## M3.1 Case Grader v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M3.1 |
| 负责人 | AI Backend + 教研 |
| 任务 | 按 rubric 批改案例题 |
| 交付物 | grade_case_answer generator |
| 依赖 | M1.9、M2.6 |
| 验收 | 输出得分、命中点、漏点、优化答案、weak_tags |

## M3.2 Attempt API

| 字段 | 内容 |
|---|---|
| 编号 | M3.2 |
| 负责人 | Backend |
| 任务 | 保存选择题和案例题作答记录 |
| 交付物 | `question_attempts` API |
| 依赖 | M3.1 |
| 验收 | 作答记录可查询，分数和 weak_tags 可保存 |

## M3.3 错题本

| 字段 | 内容 |
|---|---|
| 编号 | M3.3 |
| 负责人 | Backend + Frontend |
| 任务 | 自动归档错题和低分案例题 |
| 交付物 | WrongBook 页面 |
| 依赖 | M3.2 |
| 验收 | 答错题自动进入错题本，支持按考点筛选 |

## M3.4 薄弱点画像 v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M3.4 |
| 负责人 | Backend + AI Backend |
| 任务 | 根据 weak_tags 聚合用户薄弱点 |
| 交付物 | user_topic_mastery 数据结构 |
| 依赖 | M3.2 |
| 验收 | 能展示用户在 10 个考点上的掌握度 |

## M3.5 错题重学课生成

| 字段 | 内容 |
|---|---|
| 编号 | M3.5 |
| 负责人 | AI Backend |
| 任务 | 根据某道错题或弱点自动生成短课 |
| 交付物 | regenerate_from_wrong_answer |
| 依赖 | M3.3、M3.4 |
| 验收 | 点击错题“生成重学课”，生成 3-5 个 scene |

## M3.6 评分一致性评测集

| 字段 | 内容 |
|---|---|
| 编号 | M3.6 |
| 负责人 | 教研 + QA + AI Backend |
| 任务 | 建立 50 份人工评分样本 |
| 交付物 | grading_eval_dataset |
| 依赖 | M3.1 |
| 验收 | AI 评分与人工评分误差分布可统计 |

---

# M4：导出和审核，第 8-9 周

## M4 目标

让机构能拿走、能改、能发布、能审查。

## M4.1 Render Export Service 骨架

| 字段 | 内容 |
|---|---|
| 编号 | M4.1 |
| 负责人 | Node Export Engineer |
| 任务 | 新建 Node/TypeScript 导出服务 |
| 交付物 | render-export-service |
| 依赖 | M1 LessonIR |
| 验收 | 接收 lesson_ir 返回 artifact_uri |

## M4.2 PPTX Export v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M4.2 |
| 负责人 | Node Export Engineer + Frontend |
| 任务 | 用 PptxGenJS 导出 PPTX |
| 交付物 | PPTX exporter |
| 依赖 | M4.1 |
| 验收 | slide、quiz、case、summary 四类页可导出并在 PowerPoint/WPS 打开 |

## M4.3 PPT 模板系统

| 字段 | 内容 |
|---|---|
| 编号 | M4.3 |
| 负责人 | Frontend + Export Engineer |
| 任务 | 固定标题页、知识点页、流程页、案例页、总结页模板 |
| 交付物 | template definitions |
| 依赖 | M4.2 |
| 验收 | 导出 PPT 风格统一，不出现严重溢出 |

## M4.4 HTML Export v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M4.4 |
| 负责人 | Frontend + Export Engineer |
| 任务 | 导出静态互动课堂 HTML |
| 交付物 | index.html + lesson.json + assets |
| 依赖 | M2 renderers |
| 验收 | 下载后本地可打开，支持基础播放和测验 |

## M4.5 Classroom ZIP Export

| 字段 | 内容 |
|---|---|
| 编号 | M4.5 |
| 负责人 | Backend + Export Engineer |
| 任务 | 打包 classroom.zip |
| 交付物 | ZIP exporter |
| 依赖 | M4.4 |
| 验收 | ZIP 包含 manifest、lesson.json、index.html、assets、questions、citations |

## M4.6 导出任务 API

| 字段 | 内容 |
|---|---|
| 编号 | M4.6 |
| 负责人 | Backend |
| 任务 | 实现 export job 创建、进度、下载 |
| 交付物 | export API |
| 依赖 | M4.1-M4.5 |
| 验收 | 前端点击导出后能看到进度并下载 |

## M4.7 Review Engine v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M4.7 |
| 负责人 | AI Backend + 教研 |
| 任务 | 自动审核内容质量、来源、版权风险、考试相关性 |
| 交付物 | review report |
| 依赖 | M1.10 |
| 验收 | 每个 scene 有 approved/needs_review/rejected 状态 |

## M4.8 审核后台 v0.1

| 字段 | 内容 |
|---|---|
| 编号 | M4.8 |
| 负责人 | Frontend + Backend |
| 任务 | 教研查看风险项、修改、批准发布 |
| 交付物 | Review 页面 |
| 依赖 | M4.7 |
| 验收 | 教研可以 approve/reject scene |

---

# M5：OpenMAIC 体验增强，第 10-13 周

## M5 目标

把 MVP 从“能用”提升到“像互动课堂”，增强多 Agent、PBL、仿真、白板和 TTS。

## M5.1 多 Agent Orchestrator v1

| 字段 | 内容 |
|---|---|
| 编号 | M5.1 |
| 负责人 | AI Backend |
| 任务 | 引入 LangGraph 或自研 state graph，支持 teacher/student/examiner 节点 |
| 交付物 | orchestrator |
| 依赖 | M2.10 |
| 验收 | 用户提问时可由不同角色协作回答 |

## M5.2 AI 同学动态追问

| 字段 | 内容 |
|---|---|
| 编号 | M5.2 |
| 负责人 | AI Backend + Frontend |
| 任务 | AI 同学根据讲解内容动态提出问题 |
| 交付物 | student_interaction node |
| 依赖 | M5.1 |
| 验收 | 每节课至少出现 2 个高质量追问，不打断主线 |

## M5.3 白板增强

| 字段 | 内容 |
|---|---|
| 编号 | M5.3 |
| 负责人 | Frontend |
| 任务 | 增加激光笔、局部高亮、动画绘制 |
| 交付物 | WhiteboardRenderer v1 |
| 依赖 | M2.4、M2.7 |
| 验收 | 网络计划和流程图白板讲解体验明显优于静态页 |

## M5.4 网络计划交互仿真

| 字段 | 内容 |
|---|---|
| 编号 | M5.4 |
| 负责人 | Frontend + 教研 + AI Backend |
| 任务 | 用户识别关键线路、输入时间参数、系统反馈 |
| 交付物 | NetworkPlanSimulation |
| 依赖 | M2 renderers |
| 验收 | 支持至少 5 个网络计划题模板 |

## M5.5 索赔判断器

| 字段 | 内容 |
|---|---|
| 编号 | M5.5 |
| 负责人 | Frontend + AI Backend |
| 任务 | 用户判断工期/费用索赔，系统给出理由 |
| 交付物 | ClaimDecisionSimulation |
| 依赖 | M3 Case Grader |
| 验收 | 支持事件责任、关键线路、费用三步判断 |

## M5.6 PBL 状态机

| 字段 | 内容 |
|---|---|
| 编号 | M5.6 |
| 负责人 | AI Backend + Frontend |
| 任务 | 实现 intro→事件→决策→挑战→作答→评分→复盘 |
| 交付物 | PBL Engine + PBLRenderer |
| 依赖 | M3、M5.1 |
| 验收 | 可完成一个“深基坑位移异常”PBL 课堂 |

## M5.7 多角色 TTS

| 字段 | 内容 |
|---|---|
| 编号 | M5.7 |
| 负责人 | Backend + AI Backend |
| 任务 | 给老师、同学、阅卷官配置不同音色 |
| 交付物 | actor voice config |
| 依赖 | M2.9 |
| 验收 | 多角色对话能区分音色，字幕同步基本准确 |

---

# M6：视频与规模化，第 14-18 周

## M6 目标

支持内容矩阵和机构规模化生产。

## M6.1 Remotion 视频服务骨架

| 字段 | 内容 |
|---|---|
| 编号 | M6.1 |
| 负责人 | Node Export Engineer |
| 任务 | 建立 Remotion composition，从 LessonIR 渲染视频 |
| 交付物 | video exporter skeleton |
| 依赖 | M4.1、M2 renderers |
| 验收 | 一个 2 分钟课程可导出 MP4 |

## M6.2 字幕和音频合成

| 字段 | 内容 |
|---|---|
| 编号 | M6.2 |
| 负责人 | Export Engineer + AI Backend |
| 任务 | 整合 TTS 音频、字幕、场景切换 |
| 交付物 | subtitle/audio pipeline |
| 依赖 | M6.1、M5.7 |
| 验收 | 视频音画基本同步 |

## M6.3 横屏/竖屏模板

| 字段 | 内容 |
|---|---|
| 编号 | M6.3 |
| 负责人 | Frontend + Export Engineer |
| 任务 | 16:9 课程版、9:16 短视频版 |
| 交付物 | video templates |
| 依赖 | M6.1 |
| 验收 | 同一 LessonIR 可导出两种比例 |

## M6.4 批量生成章节课程

| 字段 | 内容 |
|---|---|
| 编号 | M6.4 |
| 负责人 | Backend + AI Backend |
| 任务 | 按章节批量生成课程草稿 |
| 交付物 | batch generation API |
| 依赖 | M1-M4 |
| 验收 | 可批量生成 10 节草稿，失败可重试 |

## M6.5 机构品牌模板

| 字段 | 内容 |
|---|---|
| 编号 | M6.5 |
| 负责人 | Frontend + Backend |
| 任务 | 支持机构 logo、色板、片头、PPT 模板 |
| 交付物 | tenant branding config |
| 依赖 | M4.3、M6.3 |
| 验收 | 不同机构导出内容有不同品牌样式 |

---

## 3. Sprint 级排期建议

### Sprint 1：地基和第一条假数据链路

目标：不用 LLM，先用 fixture 跑通端到端。

交付：

- LessonIR schema。
- DB migration。
- Job queue。
- 课程详情 API。
- 前端能渲染一个手写 lesson fixture。

验收：

- 打开 `/exam-classroom/demo`，能播放一个假课程。

### Sprint 2：真实生成大纲和 scene

目标：接入 LLM，生成真实大纲和 scene。

交付：

- Intent Parser。
- Source Retriever。
- Course Planner。
- 4 类 scene generator。
- SSE 进度。

验收：

- 输入“网络计划关键线路”，能生成课程草稿。

### Sprint 3：播放器可用

目标：生成的内容能播放和互动。

交付：

- SlideRenderer。
- WhiteboardRenderer。
- QuizRenderer。
- CasePracticeRenderer。
- Action Executor。
- TTS v0.1。

验收：

- 10 分钟课程能顺序播放，中途能答题。

### Sprint 4：考试闭环

目标：案例题能批改，薄弱点能沉淀。

交付：

- Case Grader。
- Attempts。
- WrongBook。
- Weakness Tracker。
- 错题重学课。

验收：

- 学员做错题后，系统能生成针对性短课。

### Sprint 5：导出和审核

目标：机构能拿去用。

交付：

- PPTX 导出。
- HTML 导出。
- ZIP 导出。
- 审核流。
- 课程模板。

验收：

- 一节课程能导出 PPTX、HTML、ZIP；教研能批准发布。

---

## 4. MVP 验收清单

MVP 必须全部满足：

- [ ] 输入一个考点可以创建生成任务。
- [ ] 生成进度可见。
- [ ] 先返回大纲，再生成 scene。
- [ ] 支持 slide、whiteboard、quiz、case 四类 scene。
- [ ] 每个 scene 可单独重生成。
- [ ] 课堂可以播放、暂停、切换 scene。
- [ ] AI 老师有字幕和 TTS。
- [ ] AI 同学能提出至少一个相关问题。
- [ ] 用户可以在课堂中提问。
- [ ] 选择题可以作答并即时反馈。
- [ ] 案例题可以提交并按 rubric 批改。
- [ ] 错题自动进入错题本。
- [ ] 用户薄弱点可展示。
- [ ] 可导出 PPTX。
- [ ] 可导出 HTML。
- [ ] 可导出 Classroom ZIP。
- [ ] 内容有引用来源或资料不足提示。
- [ ] 教研可以审核和批准课程。
- [ ] 生成失败不会导致整堂课不可用。
- [ ] 项目不复制 OpenMAIC 源码、Prompt、Schema、UI、素材。

---

## 5. 开发优先级原则

出现资源冲突时，优先级如下：

1. **Lesson IR 和生成稳定性** 高于 UI 炫酷。
2. **案例题批改** 高于泛泛多 Agent 聊天。
3. **PPTX/HTML/ZIP 导出** 高于 MP4 视频。
4. **错题重学闭环** 高于 3D 仿真。
5. **固定模板可控输出** 高于 AI 自由创作。
6. **局部重生成** 高于一次性生成完美。
7. **来源和审核** 高于生成速度。

---

## 6. 研发每日工作方式建议

### 6.1 每个功能必须有 fixture

例如：

```text
fixtures/exam_classroom/
  mass_concrete_lesson.json
  network_plan_lesson.json
  waterproof_case_lesson.json
```

没有 fixture，不允许合并渲染器和导出器。

### 6.2 每个 generator 必须有离线测试

测试内容：

- 输出能否通过 schema。
- 失败后能否 repair。
- 是否有 citations。
- 是否有 topic_tags。
- 是否出现空 scene。

### 6.3 每个导出器必须有黄金样本

黄金样本：

- PPTX 能打开。
- HTML 能打开。
- ZIP 内容完整。

### 6.4 每周演示一条完整链路

不要只演示单个模块。每周必须演示：

```text
输入 → 生成 → 播放 → 做题 → 批改 → 导出
```

哪怕功能粗糙，也要保持端到端闭环。

---

## 7. 第一批推荐测试考点

用于生成评测和演示：

1. 大体积混凝土裂缝控制。
2. 网络计划关键线路。
3. 施工索赔工期与费用判断。
4. 屋面防水施工质量控制。
5. 深基坑支护安全管理。
6. 脚手架工程安全检查。
7. 模板工程施工方案。
8. 混凝土浇筑与养护。
9. 质量事故处理程序。
10. 竣工验收资料管理。

---

## 8. 当前最现实的落地判断

如果目标是“看起来像 OpenMAIC”，容易走偏。真正应该先做到：

```text
建筑实务考点讲得准
案例题批得准
错题能重学
机构能导出课件
课堂有老师感和互动感
```

P0 做到这些，就已经具备商业试点价值。

P1 再追求：

```text
更强多 Agent
更顺滑白板
更强 PBL
更好的 TTS
更丰富交互仿真
```

P2 再做：

```text
MP4 视频
批量课程生产
品牌模板
SCORM/xAPI
多考试拓展
```
