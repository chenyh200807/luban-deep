# 鲁班学情·考点地图（Syllabus Knowledge Map）设计

- 状态：Proposed v0.1
- 日期：2026-05-26
- 归属主线：Learner State / Evidence-first Memory / 学员工作台（本设计是 [2026-05-26-luban-learner-workspace-notebook-calendar-prd.md](2026-05-26-luban-learner-workspace-notebook-calendar-prd.md) 中**故意推迟**的"图谱下钻 / 知识图谱"那块的落地设计，不是新平行主线）
- 产品表面：鲁班智考微信小程序
- 相关 contract：[contracts/learner-state.md](../../contracts/learner-state.md)
- 相关计划：[2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md)、[2026-05-21-luban-learning-report-world-class-optimization-plan.md](2026-05-21-luban-learning-report-world-class-optimization-plan.md)、[2026-05-20-luban-learning-report-read-model-execution-plan.md](2026-05-20-luban-learning-report-read-model-execution-plan.md)

## 1. 结论

考点地图是一张**学员进度概览图**：把官方考纲结构（`syllabus_tree`）与"学员当前掌握/薄弱/趋势"（learner-state 编译真相 read model）**只读叠加**，让学员一眼看清"我在考纲哪、学过多少、掌握多少、薄弱在哪"，并能从任一考点一键转入 TutorBot 练习。

它是**纯呈现层投影**：不新增知识权威、不新增掌握权威、不新增聊天入口、不碰 `rag`。

## 2. Karpathy Gate

### assumptions
- 学员首要诉求是"定位与动机"（进度概览），不是关系探索；关系网/弱点诊断是后续独立功能。
- 掌握度的唯一权威是 learner-state 编译真相 read model（`learning_synthesis`），**不是**原始 `user_stats.knowledge_map` 字段；地图只读 read model 暴露的 projection。
- 真实掌握度记录在**章节级 node_code**（`1A4xxxx`，官方考纲粒度），细叶子级几乎无记录 → 考点单元按章节级。

### simplest path
- 后端：mobile 路由加一个**只读端点**，复用既有 learner-state read model + join `syllabus_tree` 结构，产出"树形 + 双环聚合 + 节点状态"的 view model。不写新表、不建新真相。
- 前端：新增 1 个小程序页面（分层钻取地图）消费该端点；"去练这个"复用现有聊天入口。

### change boundary
- 允许触碰：`deeptutor/api/routers/mobile.py`（加只读端点）、一个新的薄读 service/read-model 函数、1 个新小程序页面、INDEX。
- 不碰：`/api/v1/ws` 协议、`rag`、learner-state 写链路、`syllabus_tree` 写入、其他主线代码。
- 相邻但不在本次：`syllabus_tree` 派生统计列回填、taxonomy 漂移码对齐（只记录，见 §7）。

### verification target
- 单测（聚合/状态/空数据）+ API 契约测 + 微信开发者工具模拟器回归（AGENTS §4 强制）。

## 3. 目标 / 非目标

**目标**
- 学员在小程序看到分层钻取的考点地图，顶部双环（已学覆盖% + 已掌握%）。
- 每个章节级考点显示 4 状态（未学灰 / 薄弱红<0.4 / 巩固中黄0.4–0.7 / 已掌握绿≥0.7）。
- 点考点 → 详情卡（掌握度 / 趋势 / 上次诊断 / 错误类型，均来自 read model）→ "去练这个"转 TutorBot。

**非目标**
- 不做复杂力导向知识图谱 / 3D 图谱（沿用 learning-state-inference 计划的明确 scope-out）。
- 不做备考路径推荐、不做错因回溯（各自独立功能，单独走闭环）。
- 不让前端推断掌握度（前端只渲染 read model projection）。
- 不在本设计回填 `syllabus_tree` 统计列、不解决 taxonomy 漂移（见 §7 风险，单独任务）。

## 4. 单一 Authority

| 业务事实 | 唯一 authority | 本设计角色 |
| --- | --- | --- |
| 考点结构/层级 | `syllabus_tree`（node_code / parent_code / level） | 只读 |
| 学员掌握/薄弱/趋势 | learner-state 编译真相 read model（`learning_synthesis`，经 `LearnerStateService`） | 只读 projection |
| 聊天/练习入口 | `/api/v1/ws`（唯一流式入口，带 `scene`） | 复用，不新增路由 |
| 知识召回 | `rag` | 完全不碰 |

- competing authorities 排查：地图**不得**直接读原始 `user_stats.knowledge_map` 做掌握判断（那会与 read model 争夺 authority）；一律走 read model。
- 地图产出的 view model 是**派生只读**，不回写任何掌握/进度真相。

## 5. 设计

### 5.1 数据流
```
syllabus_tree (结构: node_code/parent_code/level/node_name)        ← 结构权威(只读)
        ⨝  按 node_code 对齐(章节级)
learner-state read model (learning_synthesis projection, 当前学员)  ← 掌握权威(只读)
        ↓  叶子/章节掌握向上聚合(双环 + 节点状态)
考点地图 view model  →  mobile 只读端点  →  小程序分层钻取页
```

### 5.2 视图（方案 A 分层钻取 + 进度环）
- 顶部 hero：**双环**——蓝环"已学(覆盖)% = 有掌握记录的考点 / 总考点"、绿环"已掌握% = mastery≥0.7 / 总考点"。
- 上层大类卡：聚合环 + "已掌握 X/总 Y"，点开逐层钻取。
- 叶子/章节考点：状态色点 + 掌握%。
- 考点单元 = 章节级 node_code；细叶子作为后续下钻详情（P0B）。

### 5.3 交互
- 点考点 → 详情卡：mastery / trend(up/down) / last_diagnosis / last_error_type（全部取自 read model projection）。
- "去练这个"按钮 → 复用 `/api/v1/ws`，`scene=construction-exam` + 携带 node_code/node_name 上下文；不新增聊天路由。

### 5.4 架构落点
| 层 | 落点 | 纪律 |
| --- | --- | --- |
| 后端 | `mobile.py` 加只读端点（如 `GET /api/v1/mobile/knowledge-map`），调用一个薄读 read-model 函数（复用 `LearnerStateService` 编译真相 + join `syllabus_tree`） | thin wrapper；不新增真相 |
| 前端 | 新增 1 个小程序页面（分层钻取地图） | 学员面=小程序 |
| 去练 | 复用 `/api/v1/ws` + `scene`/node 上下文 | 单一流式入口 |

## 6. 实施阶段

- **P0（最小闭环）**：只读端点（章节级 view model：树 + 双环 + 状态）＋ 小程序地图页（钻取 + 双环 + 详情卡 + "去练"跳现有聊天）。
- **P0B（增强）**：叶子级下钻详情；与"错因地图"入口互链（属 workspace 主线 P0B）。
- **P1**：进入学情看板作为一个 tab/入口（与 workspace PRD 的看板对齐）。

## 7. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| **taxonomy 漂移**：部分掌握记录的 node_code 不在 `syllabus_tree`（实测某学员 42 个里 17 个不在） | 地图忽略不崩；单独记一条"taxonomy 对齐"任务（不在本设计范围）；端点返回 `unmatched_count` 供观测 |
| 掌握度粒度不齐（章节级 vs 叶子级） | 考点单元定为章节级；叶子无记录显"未学" |
| 误用原始 `knowledge_map` | 代码评审 gate：掌握度只能来自 read model；`_elo`/`_behavior` 等 `_` 前缀元键排除 |
| 新学员空数据 | 全"未学"，双环 0%/0%，显"开始学习"引导 |
| 首屏过载 | 今日/概览优先，复杂图谱只在下钻；不做力导向全图 |

## 8. 验收标准

- 单测：聚合正确（父进度=子聚合）、4 状态阈值、空 knowledge_map、`_` 前缀元键排除、unmatched node_code 不崩。
- 契约测：端点返回 view model schema 稳定（树 + 双环 + 节点状态 + unmatched_count）。
- 纪律回归：确认未新增聊天路由、未读原始 knowledge_map 做判断、未碰 rag、未写掌握真相。
- 微信开发者工具模拟器/真机回归一次（AGENTS §4）。

## 9. 相关代码入口

- `deeptutor/api/routers/mobile.py`（现有 `/plan/mastery-dashboard`、`/learning-brain/projection` 同款只读端点风格；新端点加在此）
- `deeptutor/services/tutor_state/service.py`（`LearnerStateService`，编译真相 read model）
- `deeptutor/contracts/learner_state.py`（learner_state 契约，`user_stats` = progress truth）
- `build_learning_brain_read_model` / `read_compiled_learning_truth`（read model 组装参考）
- `deeptutor/api/routers/unified_ws.py`（`scene` 参数；"去练"复用入口）
- Supabase（luban / zgupgiz）：`syllabus_tree`、`user_stats`（read model 来源）

## 10. 设计原型证据

- 交互原型（真实考纲 + 某真实学员真实掌握度，方案 A）：`FastAPI20251222/docs/2026/_kmap_prototype.html`
- 布局 3 方案对比草图：`FastAPI20251222/docs/2026/_kmap_mockups.html`
- 全量关系图谱（syllabus_tree + 452 prerequisite 边）：`FastAPI20251222/docs/2026/_syllabus_graph.html`
