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

也就是：

- transport / schema / 状态来源 / trace 词汇表不能长第二套
- provider / pipeline / strategy / prompt / 内部算法可以演进

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

## AI / 工程师工作规则

任何涉及以下边界的改动，不能直接动代码，必须先读 contract：

- `turn / ws / session / stream / replay / resume`
- `capability route / capability config`
- `rag / retrieval / exact-question / authority`
- `tutorbot business identity / default knowledge chain`
- `config runtime / provider resolution / env semantics`

工作顺序固定：

1. 先读本文件
2. 再读 [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
3. 按索引命中的 domain 加载对应专项 contract
4. 确认是否还需要改 schema
5. 再改业务代码
6. 最后补测试

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
