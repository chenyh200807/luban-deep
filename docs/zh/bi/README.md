# DeepTutor BI 方案总览

本文档组用于为 DeepTutor 补齐一套可落地的 BI（Business Intelligence）方案。它参考了
`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/` 中已经存在的 BI 思路，
但不会机械照搬，而是围绕 DeepTutor 当前的产品形态重新设计：

- DeepTutor 是 agent-native 学习产品，不只是普通问答应用。
- 它同时存在 Web、WebSocket API、Python SDK、CLI、TutorBot、小程序等多入口。
- 它既有学习行为数据，也有 Agent 路由、工具调用、知识库召回、会话质量、成本与会员数据。

因此，DeepTutor 的 BI 不能只做“用户数 + 充值数 + API 日志”，而应形成一套覆盖
“经营、学习、Agent、知识库、会员、可观测性”的统一数据体系。

## 文档清单

- [DeepTutor BI PRD](./deeptutor-bi-prd.md)
  说明为什么做 BI、给谁看、看什么、页面模块怎么组织、每个模块回答哪些业务问题。
- [DeepTutor BI 数据与指标方案](./deeptutor-bi-data-blueprint.md)
  说明现有数据源、事件模型、事实表/维表设计、指标口径、接口建议和实施路线图。

## 设计原则

### 1. 先面向业务决策，再面向可视化

BI 的目标不是“堆图表”，而是帮助团队回答真实问题：

- 用户从哪里来，什么人会留下来，什么人会流失。
- 哪些 capability、tool、知识库或 TutorBot 真正在提升学习效果。
- 哪些模型组合最贵，哪些最值，哪些会拉低质量。
- 哪些会员应该续费触达，哪些用户应该触发学习干预。

### 2. DeepTutor 的 BI 必须体现 Agent 特性

相比普通教培产品，DeepTutor 还需要回答：

- `chat`、`deep_solve`、`deep_question`、`deep_research`、`visualize` 的使用分布如何。
- 用户会不会从普通聊天升级到深度能力。
- tool 调用是否有效，是否真的提升答案质量、学习完成率、复盘保存率。
- 哪些知识库和 TutorBot 是高 ROI 资产，哪些只是高成本低使用。

### 3. 先复用现有数据，再补埋点与数仓

DeepTutor 当前已经具备一些天然数据源：

- 会话与消息：`deeptutor/services/session/sqlite_store.py`
- 成本与 token 统计：`deeptutor/services/observability/langfuse_adapter.py`
- 会员/积分/学习概览：`deeptutor/services/member_console/service.py`
- 最近活动 Dashboard：`deeptutor/api/routers/dashboard.py`

BI 方案优先把这些数据统一起来，再逐步增加事件埋点、宽表、日报聚合和管理后台接口。

## 推荐看板分层

建议将 BI 拆成 8 个一级模块：

1. 经营总览
2. 用户增长与留存
3. 学习行为与转化漏斗
4. Agent 能力与工具效果
5. 知识库与内容资产
6. 成本、质量与可观测性
7. 会员、积分与营收
8. Learner 360 / TutorBot 360

## 推荐实施节奏

### Phase 1：先把“能看见”做出来

- 汇总现有 session、turn、cost summary、member_console 数据
- 出经营总览、用户活跃、能力分布、成本看板
- 补基础 BI API：`/api/v1/bi/overview`、`/api/v1/bi/usage`、`/api/v1/bi/cost`

### Phase 2：把“学习效果”做出来

- 新增学习事件与评估事件
- 建立学习漏斗、章节掌握度变化、题目生成与作答闭环
- 增加 Learner 360 与人群细分

### Phase 3：把“运营动作”做出来

- 支持风险学员筛选、续费触达、TutorBot ROI、知识库 ROI
- 建立告警、异常面板、日/周报
- 形成产品、运营、教学、模型平台共同使用的统一驾驶舱

## 交付定位

这组文档不是“概念脑暴”，而是面向后续实际开发的蓝图：

- 产品经理可以直接拿来拆 PRD 与页面结构。
- 后端可以据此设计 BI API、事实表和聚合任务。
- 数据侧可以据此补埋点、建宽表、统一指标口径。
- 运营和教学团队可以据此定义日常使用的核心看板。
