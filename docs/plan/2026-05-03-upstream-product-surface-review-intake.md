# Upstream Product Surface Review Intake

状态：Proposed

## 目标

把上游 `Book / Space / Co-writer / TutorBot channels` 相关更新从“工程吸收队列”降级为“产品评审队列”，先判断它们是否服务鲁班智考的核心学习闭环，再决定是否进入 PRD 或实施计划。

本 intake 的作用是防止后续 agent 因为上游已有代码而直接搬迁，制造第二套对象、入口或 channel authority。

## 非目标

- 不直接吸收上游 Book / Space / Co-writer / TutorBot channel 代码。
- 不新增聊天 WebSocket、专用 TutorBot transport 或平行 session 状态。
- 不把 `Book`、`Space`、`Co-writer` 当成当前鲁班智考的一等业务概念。
- 不用产品名替代现有 `active_object`、`notebook`、`guide_page`、`study_plan`、`TutorBot` 等已有概念。

## 单一 Authority

- 聊天与 TutorBot 执行：仍由统一 `/api/v1/ws`、`TurnRuntimeManager`、`ChatOrchestrator` 负责。
- 学习对象连续性：仍由 `active_object` / session runtime 负责。
- 学员长期状态：仍由 Learner State / Overlay 负责。
- 文档、笔记、课堂材料：优先复用现有 Notebook / Guide / Lesson IR 主线，不新建 `Book` 或 `Space` 作为并行 truth source。

## 产品评审问题

1. `Book` 是否只是 Notebook / Guide / Lesson IR 的换名？
2. `Space` 是否只是 workspace / session grouping / course 的换名？
3. `Co-writer` 是否属于鲁班智考主学习链，还是泛写作工具？
4. TutorBot channels 是否需要作为产品入口存在，还是只保留统一 TutorBot runtime 后的 adapter？
5. 这些能力是否能提升建筑实务考试的提分、练题、讲解、复盘、测评闭环？

## 分阶段 Gate

### P0: 概念去重

输出一张映射表：

| 上游概念 | 本地已有概念 | 是否重复 | 建议 |
| --- | --- | --- | --- |
| Book | Notebook / Guide / Lesson IR | 待评审 | 默认不吸收 |
| Space | workspace / session / course | 待评审 | 默认不吸收 |
| Co-writer | Co-writer router / writing surface | 待评审 | 先看产品价值 |
| TutorBot channels | TutorBot runtime adapter | 待评审 | 不新增聊天 transport |

### P1: 产品价值判断

每个候选能力必须回答：

- 对建筑实务学习的核心收益是什么？
- 是否能进入已有学习闭环，而不是新增表面？
- 是否有真实用户反馈或运营场景支撑？
- 是否需要线上数据验证？

### P2: PRD 归属

若通过产品评审，必须挂到已有主线：

- TutorBot / 聊天入口：`2026-04-15-unified-ws-full-tutorbot-prd.md`
- 上下文与语义连续性：`2026-04-16-tutorbot-context-orchestration-prd.md`
- Active Object 与语义路由：`2026-04-18-llm-native-active-object-semantic-router-prd.md`
- 建筑实务 AI 互动课堂：`../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md`

只有无法挂入既有主线且产品价值明确时，才允许新增 PRD。

## 验收标准

- 任何 Book / Space / Co-writer / channel 工程改动前，必须先有产品评审结论。
- 评审结论必须写明复用哪个现有 authority，或为什么必须新增一等概念。
- 若新增一等概念，必须同步更新 `CONTRACT.md`、`contracts/index.yaml` 或对应 PRD 主线。
- 不允许因为上游有现成实现就绕过本 intake。

## 相关代码入口

- `deeptutor/api/routers/co_writer.py`
- `deeptutor/services/session/turn_runtime.py`
- `deeptutor/runtime/orchestrator.py`
- `deeptutor/tutorbot/channels/`
- `deeptutor/contracts/unified_turn.py`
