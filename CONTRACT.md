# DeepTutor Contract Index

本文件是 DeepTutor 的**总纲 contract**。  
它不负责承载所有细节，而是负责规定：

- 哪些系统边界必须单点治理
- 每个边界去看哪一份专项 contract
- AI / 工程师改代码前要先加载什么
- CI guard 应该如何判断“这次改动是否触碰契约边界”

机器可读索引在：

- [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)

## 第一性原则

DeepTutor 必须优先保证：

1. 一致性
2. 可观测性
3. 可持续演进
4. 局部灵活、边界严格

原则上：

- **对外 contract 必须单一**
- **对内实现允许多样**
- **同一业务事实只能有一个一等概念**

也就是：

- transport / schema / 状态来源 / trace 词汇表不能长第二套
- provider / pipeline / strategy / prompt / 内部算法可以演进
- 身份 / 工具 / 知识库绑定 / 表现风格不能混成多套平行概念
- 联网搜索工具必须由 config runtime 统一判定可用性；未配置时关闭，不得由入口、capability 或 provider fallback 各自决定。

## 当前必须单点治理的控制面

### 1. Turn Contract

负责：

- `/api/v1/ws`
- turn / session / stream / replay / resume
- turn trace 词汇表
- TutorBot 作为业务身份接入 turn

专项文档：

- [contracts/turn.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/turn.md)
- [docs/zh/guide/unified-turn-contract.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/unified-turn-contract.md)

### 2. Capability Contract

负责：

- capability 路由
- request config schema
- orchestrator 和 registry 的唯一性

专项文档：

- [contracts/capability.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/capability.md)

### 3. RAG Contract

负责：

- `RAGService` 作为统一 grounding 入口
- retrieval metadata
- exact-question
- authority correction

专项文档：

- [contracts/rag.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/rag.md)

### 4. Config Runtime Contract

负责：

- runtime config 加载
- provider 解析
- env/catalog/settings 优先级

专项文档：

- [contracts/config-runtime.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/config-runtime.md)

### 5. Learner State Contract

负责：

- 学员级长期状态
- Summary / Profile / Progress / Goals / Memory Events
- Guided Learning / Notebook / TutorBot / Heartbeat 对长期状态的写回边界
- 复用 Supabase 学员表与新增表的职责收口

专项文档：

- [contracts/learner-state.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/learner-state.md)

## AI / 工程师工作规则

任何涉及以下边界的改动，不能直接动代码，必须先读 contract：

- `turn / ws / session / stream / replay / resume`
- `capability route / capability config`
- `rag / retrieval / exact-question / authority`
- `tutorbot business identity / default knowledge chain`
- `learner state / summary / profile / guided learning writeback / heartbeat`
- `config runtime / provider resolution / env semantics`

工作顺序固定：

1. 先读本文件
2. 再读 [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
3. 按索引命中的 domain 加载对应专项 contract
4. 确认是否还需要改 schema
5. 再改业务代码
6. 最后补测试

## 概念去重规则

以下属于仓库级硬约束，不是建议：

- `TutorBot` 是唯一业务身份。
- `TutorBot` 只指完整 TutorBot runtime；轻量默认绑定、入口 hint、interaction profile 不得再占用 `TutorBot` 这个名字。
- `bot_runtime_defaults` 只表示 `bot_id -> 默认工具 / 默认知识库` 的绑定契约，不得伪装成完整 TutorBot 执行层。
- `rag` 是唯一知识召回工具。
- 知识库如 `construction-exam` 只能作为工具绑定或数据源，不得再包装成平行“模式身份”。
- `requested_response_mode` 是响应风格的唯一公开权威字段。
- `teaching_mode` 只允许作为历史兼容 alias 存在，并且必须在入口层立即归一化到 `requested_response_mode`；它不得继续参与运行时决策、持久化、trace 或公开 contract。
- `product_surface` / `source` / `entry_role` 只表示入口表面信息，不得演变为第二套业务身份。
- 历史兼容字段允许短期存在，但必须在统一入口层完成归一化，不能继续深入运行时。

如果一个改动引入了第二套：

- Tutor 身份
- Grounding 模式
- 知识链概念
- 入口状态来源

则默认判定为违反 contract，需要先删重再继续实现。

## Schema 规则

不是每个 contract 都必须有 schema，但**只要是对外稳定边界，就应该尽量有机器可读 schema**。

当前已经明确有 schema 的：

- Turn：`deeptutor/contracts/unified_turn.py`
- Capability request config：`deeptutor/capabilities/request_contracts.py`

其他控制面如果后续出现稳定、可复用、可验证的结构边界，也要补 schema，而不是只写自然语言文档。

## CI Guard 规则

CI 不会对全仓库一刀切，只会盯 contract 边界。

当前 guard：

- [scripts/check_contract_guard.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/check_contract_guard.py)

它根据 `contracts/index.yaml` 判断：

- 哪些文件属于哪个 contract domain
- 哪些改动必须补 contract surface
- 哪些改动必须补对应测试

## 禁止事项

- 禁止为同一控制面并行维护两套对外 contract
- 禁止绕过统一入口偷偷接第二套状态来源
- 禁止不更新 contract / tests 就修改边界语义
- 禁止只靠 prompt 或约定俗成承载稳定系统语义
