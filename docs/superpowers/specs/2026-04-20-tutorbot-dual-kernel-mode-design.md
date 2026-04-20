# TutorBot Dual-Kernel Mode Design

## 背景

当前产品表面存在 `smart / fast / deep` 三种模式，但运行时事实并不干净：

- `fast`、`smart`、`deep` 既像产品模式，又部分映射到不同执行链
- 独立 `agent 4-step` deep runtime 仍然作为顶层可见路径参与执行
- TutorBot runtime、`chat` pipeline、`deep_question` 等模块对模式语义的消费边界不完全一致

真实评测结果已经证明一个核心问题：当前独立 `deep` runtime 并没有稳定换来“最高质量”，却显著抬高了 TTFT、整轮 latency 和失败面。

因此，本设计的目标不是“继续调 deep 4-step”，而是把模式重新收敛成更少概念、更少 authority、更短链路。

## 设计结论

产品表面继续保留三种模式：

- `Fast`
- `Deep`
- `Smart`

但内部只保留两种执行内核：

- `Fast Kernel`
- `TutorBot Kernel`

`Smart` 不再是第三套执行世界，只是 `Fast/Deep` 之间的智能选择策略。

独立 `agent 4-step deep runtime` 退出产品主路径，不再作为顶层模式存在。

## 一等业务事实

系统需要维护的一等业务事实是：

> 同一学员在同一会话里的学习对象、上下文、记忆、工作空间、心跳和交互人格，必须由同一个 TutorBot authority 持续维护；模式只决定本轮回答策略，不决定业务身份切换。

这意味着：

- `TutorBot` 是唯一业务身份
- `Fast / Deep / Smart` 只表达单轮执行策略
- `deep` 不能再被实现成第二套顶层身份或第二条长期 authority

## 模式定义

### Fast

定义：

- 最低时延优先
- 允许回答更短、更保守
- 适合定义解释、短追问、低风险轻任务

运行要求：

- 专门快模型
- 严格工具预算
- 默认短答
- 尽量单次直答
- 最多一次轻量知识召回
- 不默认进入重型多阶段链路

### Deep

定义：

- 最高质量优先
- 允许更慢，但必须“慢得有价值”
- 适合案例题、复杂比较、批改、规划、强连续性任务

运行要求：

- 继续挂在 TutorBot authority 下
- 共享同一 workspace / memory / heartbeat / active object
- 使用更高质量模型与更高预算
- 强化锚点保持、证据组织、答案结构
- 允许更长更严谨的回答
- 不再等于独立 `agent 4-step` runtime

### Smart

定义：

- 自动模式
- 在 `Fast` 与 `Deep` 之间选择

运行要求：

- 不再有第三套执行内核
- 只做单轮路由策略

## 运行时架构

### 顶层原则

- 单一业务 authority：TutorBot
- 双内核：`Fast Kernel` 与 `TutorBot Kernel`
- 单一路由职责：`Smart` 只选择，不执行

### 路由结果

- `Fast` -> `Fast Kernel`
- `Deep` -> `TutorBot Kernel (deep policy)`
- `Smart` -> `AutoSelect(Fast Kernel | TutorBot Kernel deep policy)`

### 独立 4-step runtime 的新位置

独立 `agent 4-step` deep runtime 不再作为用户显式模式存在。

允许的降级位置只有两种：

- 退出产品主路径，仅保留为历史兼容代码路径
- 或降级为 TutorBot 内部极少数 deep turn 的受控子步骤，而不是顶层 capability authority

## Smart 选择规则

`Smart` 默认选 `Fast` 的情形：

- 单一概念解释
- 简短 follow-up
- 用户明确要求“简单说 / 快一点 / 一句话”
- 没有 active object
- 不需要当前信息判断
- 不是高风险任务

`Smart` 默认选 `Deep` 的情形：

- 案例题
- 题目生成、批改、讲评
- 多问并列
- 对比分析
- 学习规划
- 跨轮连续对象已存在
- 当前信息或规则判断风险较高
- 用户明确要求“详细分析 / 深度讲解 / 按考试标准作答”

## 兼容策略

### 外部接口

- 客户端仍可继续发送 `mode/chat_mode`
- `requested_response_mode` 继续作为模式 authority 字段
- `teaching_mode` 继续保留为兼容 alias，但不得再驱动第二套执行语义

### 旧 deep runtime

- 先从产品主路径移除
- 再逐步减少直接入口
- 兼容期内允许保留内部代码，但不得继续扩大调用面

## 观测与指标

所有模式评测默认同时看四类指标：

- TTFT
- full-turn latency
- 语义理解分
- 正确性/稳定性代理

模式收敛后的目标不是单看某一项，而是形成清晰分工：

- `Fast`：TTFT 最优
- `Deep`：语义/正确性最优
- `Smart`：综合体验最优

## 成功标准

### Fast

- TTFT 明显优于 `Deep`
- full-turn latency 不得系统性劣于 `Smart`
- 不得频繁出现 `hard_error` 或 aborted case

### Deep

- 在代表性小样品上，语义与正确性应稳定不低于 `Smart`
- 延迟允许更高，但要显著低于当前独立 4-step 的重链路表现
- 不得继续以大量串行阶段换取并不明显的质量收益

### Smart

- 在小样品与 ARR 中保持综合最优或接近最优
- 不允许退化成第三套重链路

## 非目标

- 本设计不要求一次性删除所有历史 `deep_question/deep_solve` 代码
- 本设计不要求一次性重写所有 capability
- 本设计不把“更多阶段”当作质量提升手段

## 决策

正式采用：

- `Fast: 保留`
- `Deep: 保留，但重定义为 TutorBot deep policy`
- `Smart: 保留，但只做 Fast/Deep 之间的智能选择`
- `独立 agent 4-step deep runtime: 退出产品主路径，不再作为顶层模式存在`
