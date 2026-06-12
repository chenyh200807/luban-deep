# PRD：统一 `/api/v1/ws` 接入完整 TutorBot，并清理轻量 TutorBot 歧义

## 1. 文档信息

- 文档名称：统一入口接入完整 TutorBot PRD
- 文档路径：`/docs/plan/2026-04-15-unified-ws-full-tutorbot-prd.md`
- 创建日期：2026-04-15
- 适用范围：微信小程序主聊天入口、统一 WebSocket、TutorBot、Turn Runtime、RAG、建筑实务教培主场景
- 状态：Done v1

## 1.1 最终结果

本 PRD 已完成落地，当前系统状态如下：

- 微信小程序主聊天入口已通过统一 `/api/v1/ws` 进入**完整 TutorBot runtime**
- 轻量版 TutorBot 语义已收口为 `bot_runtime_defaults`，不再与完整 TutorBot 混名
- `rag` 是唯一知识工具，`construction-exam` 是默认知识库绑定
- 旧 `/api/v1/tutorbot/{bot_id}/ws` 已退役，不再承担主产品聊天
- 完整 TutorBot 主链已具备 `retrieval-first exact fast path`
- 历史真题完整案例题已在阿里云真实验收中触发 `authority_applied=true`
- 统一 trace contract 中已包含：
  - `execution_engine`
  - `bot_id`
  - `tool_calls`
  - `sources`
  - `authority_applied`
  - `session_id`
  - `turn_id`

## 2. 背景

DeepTutor 项目中当前同时存在两套语义上都被称为 “TutorBot” 的东西：

1. 完整版 TutorBot
   - 具备独立实例、独立 workspace、Soul、Heartbeat、Skills、Subagent、Channels、独立 agent loop。
   - 对应代码主要在 `deeptutor/services/tutorbot/` 与 `deeptutor/tutorbot/`。

2. 轻量版 TutorBot 语义
   - 运行在统一 `/api/v1/ws -> turn_runtime -> orchestrator -> chat/deep_question` 主链上。
   - 本质是 `bot_id + 默认工具 + 默认知识库 + TutorBot 风格判断`。
   - 当前已开始收口到 `deeptutor/contracts/bot_runtime_defaults.py`，兼容壳仍保留在 `deeptutor/contracts/tutorbot_profiles.py`。

这导致系统出现长期混淆：

- 用户以为微信小程序主聊天入口已经进入真正 TutorBot，实际上没有。
- 开发者以为已经统一成单一 TutorBot，实际上完整 TutorBot 与轻量 TutorBot 语义并存。
- 旧的 `tutorbot_profiles.py` 命名会误导开发者，以为其描述的是完整 TutorBot，而实际上只是运行时默认绑定。
- 同一个产品目标被两套实现表达，容易导致 drift、污染、trace 困惑、能力不一致。

## 3. 问题定义

### 3.1 当前核心问题

当前微信小程序 chat 主入口没有直接进入完整 TutorBot，而是进入统一聊天主链，再通过：

- `bot_id=construction-exam-coach`
- 默认 `rag`
- 默认 `construction-exam`
- `chat/deep_question` 自动分流

来模拟一层 “TutorBot 感”。

这带来的问题包括：

1. 名称歧义
   - “TutorBot” 同时指代完整 agent runtime 与轻量默认绑定。

2. 能力不完整
   - 小程序主入口没有天然获得完整 TutorBot 的：
   - 独立 workspace
   - Soul
   - Heartbeat
   - Skill 学习
   - Sub-agent / Team
   - 多通道 presence

3. 执行链路分裂
   - 完整 TutorBot 通过 `/api/v1/tutorbot/{bot_id}/ws`
   - 主产品入口通过 `/api/v1/ws`
   - 两条线并存，不符合单一入口原则

4. 产品语义与实现不一致
   - 产品上希望 “微信小程序聊天入口就是 TutorBot”
   - 实现上却是 “聊天入口只是统一 chat 链挂 TutorBot 默认值”

5. 后续维护风险高
   - 重复概念会持续诱发 patch、污染、trace 断裂、行为不可解释

### 3.2 根因

根因不是能力不够，而是架构收口不彻底：

- 完整 TutorBot 没有成为统一入口下的正式执行引擎
- 轻量版 TutorBot 语义提前占用了 “TutorBot” 这个名字
- 统一传输层和统一执行层没有彻底对齐

## 4. 目标

### 4.1 产品目标

让微信小程序主聊天入口真正进入完整 TutorBot，并保持以下体验：

- 唯一入口：`/api/v1/ws`
- 唯一业务身份：`bot_id=construction-exam-coach`
- 唯一知识工具：`rag`
- 默认知识库绑定：`construction-exam`
- 小程序主入口可直接获得完整 TutorBot 能力
- 出题、批改、追问、知识问答、基础交流都在同一套 TutorBot runtime 内完成

### 4.2 架构目标

1. `/api/v1/ws` 成为唯一对外实时入口
2. 完整 TutorBot 成为该入口下的正式执行引擎之一
3. 轻量版 TutorBot 语义彻底改名，不能再占用 “TutorBot” 名称
4. 保留统一 turn/runtime/trace/鉴权/订阅协议
5. 保留 `rag + construction-exam` 作为默认工具绑定，而不是另一套模式

### 4.3 体验目标

1. 基础交流不被教学策略污染
2. 真题/知识问答可以利用完整 TutorBot 的记忆、技能、工具体系
3. 产品对外表达和内部实现一致
4. trace、日志、事件中能清晰看出本轮是：
   - 统一主链 capability 执行
   - 还是完整 TutorBot 执行

## 5. 非目标

本次不做以下事情：

1. 不重写 TutorBot 核心 agent loop
2. 不删除 `chat` / `deep_question` capability
3. 不取消统一 turn runtime
4. 不一次性重构所有渠道
   - 本次先聚焦微信小程序主聊天入口
5. 不改变 `rag` / Supabase 召回策略的主实现边界

## 6. 第一性原理与设计原则

### 6.1 第一性原理

1. 单一入口优于多入口兼容
2. 单一业务身份优于多套命名包装
3. 证据工具应是工具，不应被包装成平行模式
4. 统一传输层与统一执行层应清晰分层
5. 产品概念必须和系统真实实现保持一致

### 6.2 Less is More

1. 不再新增一个“第三种 TutorBot”
2. 不新增“大而全的 intent gate 平台”
3. 不新增第二套知识链语义
4. 不新增并行 WebSocket 主线
5. 优先删除重复抽象，而不是增加补偿逻辑

## 7. 当前架构现状

### 7.1 当前对外主入口

- `/api/v1/ws`
  - 统一 turn、subscribe、resume、cancel

### 7.2 当前小程序主聊天实际执行

小程序现在大体是：

`mobile.py`
-> start turn
-> `/api/v1/ws`
-> `turn_runtime`
-> `orchestrator`
-> `chat` 或 `deep_question`

同时注入：

- `bot_id=construction-exam-coach`
- 默认工具：`rag`
- 默认知识库：`construction-exam`

这是一种轻量的 “TutorBot 运行时默认值”，不是完整 TutorBot runtime。

### 7.3 当前完整 TutorBot 入口

- `/api/v1/tutorbot/{bot_id}/ws`

这条线才直接进入：

- `TutorBotManager`
- `AgentLoop`
- 独立 workspace
- Heartbeat
- Soul
- Skills
- Channels

### 7.4 当前核心矛盾

当前实际上存在：

1. 统一入口主线
2. 完整 TutorBot 专用入口

这两条线都承载 “TutorBot” 语义，但能力不一致。

## 8. 目标架构

### 8.1 目标结构

未来目标结构应为：

`/api/v1/ws`
-> 统一 auth / turn / subscribe / resume / cancel / trace
-> 根据请求路由到正式执行引擎
-> 当 `bot_id=construction-exam-coach` 时，进入完整 TutorBot runtime

### 8.2 分层职责

#### A. 传输与会话层

负责：

- 统一 WebSocket 协议
- start / subscribe / resume / cancel
- turn_id / session_id / seq
- auth / ownership
- replay / storage / trace envelope

该层继续由：

- `unified_ws.py`
- `turn_runtime`
- session store

承担。

#### B. 业务身份层

负责：

- `bot_id`
- `bot binding defaults`
- 默认工具绑定
- 默认知识库绑定

这里保留：

- `bot_id=construction-exam-coach`
- 默认 `rag`
- 默认 `construction-exam`

但这层不能再叫 “TutorBot profile”。

建议改名：

- `bot_runtime_defaults`
或
- `bot_bindings`

#### C. 执行层

负责真正跑一轮用户消息。

目标是：

- 小程序主聊天入口默认使用完整 TutorBot 执行层
- `chat` / `deep_question` 仍作为平台 capability 存在
- 完整 TutorBot 可在内部调用工具或平台能力

### 8.3 关键原则

1. `/api/v1/ws` 是唯一入口
2. 完整 TutorBot 是正式执行引擎
3. `chat/deep_question` 不再和小程序主入口竞争主线
4. `rag + construction-exam` 是默认工具绑定，不是模式名

## 9. 术语收口

### 9.1 必须保留的术语

- `TutorBot`
  - 只指完整、持久、可多实例、可心跳、可技能扩展的 agent runtime

- `Capability`
  - 指平台内的执行能力，如 `chat`、`deep_question`

- `Tool`
  - 指单功能工具，如 `rag`

### 9.2 必须废弃的歧义用法

以下用法必须退出主概念层：

- 把轻量默认绑定叫作 `TutorBot`
- 把 `rag + construction-exam` 再包成平行 “grounded mode”
- 用 `interaction_profile=tutorbot` 表达完整 TutorBot 执行语义

### 9.3 新命名建议

将当前轻量概念统一改名为：

- `bot_runtime_defaults`
或
- `bot_binding_defaults`

不再使用：

- `tutorbot_profiles`
- `construction_exam_grounded`
- 任何“看起来像完整 TutorBot，实则只是默认值注入”的名称

## 10. 详细需求

### 10.1 产品需求

#### PR-1 小程序主聊天入口接入完整 TutorBot

- 用户从微信小程序 chat 页进入时
- 默认连接 `/api/v1/ws`
- 对应 `bot_id=construction-exam-coach`
- 后端执行引擎应进入完整 TutorBot runtime

#### PR-2 保留建筑实务主场景默认值

完整 TutorBot 在该 bot_id 下默认具备：

- 默认工具：`rag`
- 默认知识库：`construction-exam`

#### PR-3 基础交流体验正常

以下输入应正常由 TutorBot 处理，不被误导为解题或出题：

- 你好
- 在吗
- 谢谢
- 继续
- 重新连接
- 点数还有多少

#### PR-4 教学能力保持

以下输入在完整 TutorBot 下仍能正常完成：

- 真题问答
- 规范知识问答
- 出题
- 批改
- 追问
- 错题复盘

#### PR-5 主动能力保留

完整 TutorBot 的下列能力不能因统一入口而失效：

- Soul
- Heartbeat
- Skills
- Subagent / Team
- 多通道

### 10.2 技术需求

#### TR-1 `/api/v1/ws` 作为唯一入口

完整 TutorBot 不再要求产品主入口必须走：

- `/api/v1/tutorbot/{bot_id}/ws`

该旧入口可保留兼容一段时间，但不再作为主产品线。

#### TR-2 统一 turn runtime 继续保留

无论底层执行进入：

- 平台 capability
或
- 完整 TutorBot

都应保留统一：

- turn_id
- session_id
- subscribe/resume/cancel
- 事件流 contract

#### TR-3 完整 TutorBot 与 turn runtime 的桥接

需要新增或明确一层桥接：

- turn runtime 收到 start_turn
- 判断本轮是否应进入完整 TutorBot
- 将 inbound message 转交给 `TutorBotManager`
- 将 TutorBot 的 thinking/content/proactive/done 等事件桥接回统一 stream event

#### TR-4 统一 trace

需明确区分：

- `execution_engine = tutorbot_runtime`
- `execution_engine = capability`

同时保留：

- `bot_id`
- `default_tools`
- `knowledge_bases`
- `tool_calls`
- `sources`

#### TR-5 统一会话存储

完整 TutorBot 进入 `/api/v1/ws` 后，需要决定：

1. 继续保留 TutorBot 自己的 per-bot session 存储
2. 或统一写入 turn runtime / sqlite session store

本 PRD 推荐方案：

- 对外统一以 turn/session store 为权威
- TutorBot 内部历史作为实现细节逐步收敛

否则后续会再次出现“两套 session 真相”。

## 11. 候选方案比较

### 方案 A：维持现状

特点：

- 小程序走统一主链
- 完整 TutorBot 继续走专用 ws

问题：

- 概念持续歧义
- 能力持续分裂
- 不符合单一入口

结论：

- 不采用

### 方案 B：让小程序直接切到 `/api/v1/tutorbot/{bot_id}/ws`

优点：

- 能马上用上完整 TutorBot

问题：

- 又长出第二条产品主线
- 破坏单一入口目标
- turn/trace/subscribe 体系分裂

结论：

- 不采用

### 方案 C：统一入口 `/api/v1/ws`，底层切到完整 TutorBot

优点：

- 满足单一入口
- 满足完整 TutorBot 能力
- 满足统一 turn/runtime/trace
- 满足建筑实务默认工具绑定

问题：

- 需要做 bridge
- 需要收口 session/trace 语义

结论：

- 采用

## 12. 推荐方案

采用 **方案 C**：

### 12.1 核心决定

1. `/api/v1/ws` 继续作为唯一入口
2. `TutorBot` 恢复为完整 runtime 的唯一名称
3. 轻量默认绑定概念整体改名
4. `bot_id=construction-exam-coach` 的主聊天请求默认进入完整 TutorBot
5. `rag + construction-exam` 作为该 bot 的默认工具绑定保留
6. `chat/deep_question` 继续存在，但作为平台内部 capability，不再与主产品入口形成语义竞争

### 12.2 执行判断建议

当满足以下条件时，统一入口优先进入完整 TutorBot：

- 存在 `bot_id`
- 且该 `bot_id` 对应已声明为 `runtime_engine=tutorbot`

而不是继续仅靠：

- `interaction_profile=tutorbot`
- `entry_role=tutorbot`

这类软提示决定执行引擎。

## 13. 分阶段实施计划

### 阶段 1：概念清理

目标：

- 消除命名歧义

任务：

1. `tutorbot_profiles.py` 改名为 `bot_runtime_defaults.py` 或等价名称
2. contract 文档更新
3. AGENTS.md / CONTRACT.md 更新
4. trace 字段命名更新

交付物：

- 无 “轻量 TutorBot” 残留命名

### 阶段 2：统一入口桥接完整 TutorBot

目标：

- `/api/v1/ws` 能启动完整 TutorBot 执行

任务：

1. 定义 `execution_engine` 路由规则
2. 在 turn runtime 增加 TutorBot runtime bridge
3. 事件桥接到统一 stream
4. 保持 start/subscribe/resume/cancel

交付物：

- 同一入口下可启动完整 TutorBot

### 阶段 3：小程序主入口切换

目标：

- 微信小程序 chat 主入口改为正式完整 TutorBot

任务：

1. mobile adapter 切换到 runtime-engine based routing
2. 保留 `bot_id=construction-exam-coach`
3. 保留默认 `rag + construction-exam`

交付物：

- 小程序不再依赖轻量 TutorBot 模式

### 阶段 4：会话与 trace 收口

目标：

- 消除双 session、双 trace 真相

任务：

1. 明确统一 session 权威
2. 明确 TutorBot 历史同步策略
3. 统一 Langfuse 观测

交付物：

- 观测与会话语义统一

### 阶段 5：旧入口退役

目标：

- `/api/v1/tutorbot/{bot_id}/ws` 不再作为主产品依赖

任务：

1. 保留兼容期
2. 完成迁移后标记 deprecated
3. 评估最终移除

## 14. 验收标准

### 14.1 结构验收

1. 代码中不存在把轻量默认绑定直接命名为 TutorBot 的新写法
2. 小程序主聊天默认从 `/api/v1/ws` 进入完整 TutorBot runtime
3. `bot_id=construction-exam-coach` 的默认工具和默认 KB 保留

### 14.2 行为验收

以下输入必须通过：

- `你好`
- `在吗`
- `谢谢`
- `点数还有多少`
- `出道题`
- `考我一道建筑实务真题`
- 一道完整案例题
- 题后追问
- 原题 exact-question 命中与 authority 修正

### 14.3 能力验收

以下完整 TutorBot 能力必须仍可用：

- Soul
- 独立 workspace
- Skill 加载
- Heartbeat
- Subagent / Team
- 多通道配置

### 14.4 观测验收

trace 中必须可见：

- `execution_engine`
- `bot_id`
- `tool_calls`
- `sources`
- `authority_applied`
- `session_id`
- `turn_id`

### 14.5 实际验收结果

以下结果已在 2026-04-15 通过本地全量测试和阿里云 ECS 真实链路确认：

- 本地全量测试：`460 passed`
- 阿里云统一入口：`/api/v1/ws`
- 旧 TutorBot 专用 ws：
  - `/api/v1/tutorbot/{bot_id}/ws`
  - 已不再作为产品聊天入口
- 输入 `你好`：
  - 走轻响应
  - 不触发 `tool_call`
  - `execution_engine=tutorbot_runtime`
- 输入完整历史案例题全文：
  - 只进行一次主 `rag` 检索
  - `exact_question.coverage_ratio=1.0`
  - `missing_subquestions=[]`
  - `authority_applied=true`
  - 最终答案已确认包含：
    - `10.28`
    - `3335.40`
    - `计划、组织、协调方案`
    - `15日前`
- 阿里云日志已出现：
  - `Fast-path exact authority response`
- Langfuse/trace 收口已确认：
  - 未再出现 `metadata.sources` propagated warning

## 15. 风险与缓解

### 风险 1：统一 turn runtime 与 TutorBot session 模型冲突

缓解：

- 分阶段桥接
- 先统一对外 session，再逐步收口内部 session

### 风险 2：事件语义不一致

缓解：

- 统一 stream event contract
- TutorBot bridge 输出必须转换到统一 schema

### 风险 3：迁移期间行为回归

缓解：

- 建立基础交流、出题、批改、真题、追问五类回归矩阵
- 必须包含阿里云真实验收

### 风险 4：Langfuse 再次断链

缓解：

- execution_engine 和 tool events 作为强制 trace 字段
- 迁移阶段每轮真实验证 Langfuse

## 16. 成功指标

### 产品指标

1. 小程序主聊天入口不再出现概念混淆
2. 用户所有主场景都能在完整 TutorBot 下完成

### 工程指标

1. 统一入口使用率达到 100%
2. 主产品路径不再依赖 `/api/v1/tutorbot/{bot_id}/ws`
3. 轻量 TutorBot 命名从核心路径移除

### 质量指标

1. 基础交流误污染显著下降
2. 真题/知识问答 grounding 稳定
3. trace 工具链完整率恢复

## 17. 当前决定

本 PRD 形成以下正式决定：

1. 微信小程序 chat 主入口目标是 **完整 TutorBot**
2. 完整 TutorBot 必须通过 **统一 `/api/v1/ws`** 接入
3. 当前轻量版 TutorBot 语义必须改名，不能继续叫 TutorBot
4. `bot_id=construction-exam-coach + 默认 rag + 默认 construction-exam` 继续保留
5. `chat/deep_question` 保持为平台 capability，但不再承担“小程序主入口的 TutorBot 替身”角色

## 18. 后续落地顺序建议

建议严格按下面顺序推进：

1. 先完成命名与 contract 清理
2. 再做 `/api/v1/ws -> TutorBot runtime` bridge
3. 再切小程序主入口
4. 再统一 trace/session
5. 最后退役旧专用 ws

---

## 附：一句话版本

DeepTutor 后续必须收口到：

- `TutorBot` 只代表完整 TutorBot runtime
- `/api/v1/ws` 是唯一入口
- 微信小程序主聊天直接进入完整 TutorBot
- `rag + construction-exam` 是该 TutorBot 的默认工具绑定
- `chat/deep_question` 是平台 capability，不再是假扮 TutorBot 的主线
