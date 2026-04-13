# 鲁班智考适配记录（2026-04-12）

本文记录 2026-04-12 对 DeepTutor 的本地部署与业务化适配过程，目标是为后续 DeepTutor 升级后重新适配提供可复用的操作说明、设计理由和验证方法。

## 1. 本次适配的目标

本次适配有 3 个核心目标：

1. 将 DeepTutor 的默认知识库从原生本地 `llamaindex` 存储切换为 Supabase 中的只读知识库。
2. 保留 DeepTutor 原有聊天、记忆、会话、Co-Writer、Question Generate 等能力，尽量只替换知识库底座。
3. 将产品对外身份从 `DeepTutor` 调整为 `鲁班智考`。

本次适配明确不做的事情：

- 不使用 DeepTutor 原生本地知识库作为主知识库。
- 不让 DeepTutor 负责向 Supabase 写入知识块。
- 不把 Supabase 服务密钥暴露到前端。

## 2. 总体设计原则

### 2.1 只替换知识库底座，不破坏上层能力

核心思路不是删掉 DeepTutor 的知识库能力，而是把 `rag_search` 背后的 provider 从本地 `llamaindex` 扩展为 `supabase`，让上层功能尽可能无感继续工作。

这样做的原因：

- 聊天、Co-Writer、Question Generate 等功能本来就依赖 `rag_search`。
- 记忆、会话历史、用户画像、学习摘要并不依赖本地知识库目录。
- 如果直接砍掉原生知识库模块，会导致大量功能入口失效；如果只替换 provider，则改动面可控。

### 2.2 Supabase 作为主知识库，但保持只读

本次接入的 Supabase 知识库是核心业务资产，因此策略是：

- DeepTutor 只负责查询和召回。
- 知识块写入、清洗、入库仍由外部已有流程负责。
- DeepTutor 内部明确标记该知识库为 `remote_read_only`，拦截创建、上传、同步、删除等本地写操作。

### 2.3 不影响记忆系统

需要特别说明：

- DeepTutor 的 `memory`、`sessions`、`SUMMARY.md`、`PROFILE.md` 不依赖原生本地知识库。
- 因此不使用本地知识库不会影响“记忆”能力本身。
- 真正需要迁移的是所有依赖 `rag_search(..., kb_name=...)` 的检索型功能。

## 3. 运行时配置适配

### 3.1 适配目标

DeepTutor 在容器环境下虽然可以收到 `.env` 或 Docker 环境变量，但其运行时 provider 配置还会受内部 catalog/profile 影响。如果不处理，界面和环境变量写的是 DashScope，实际运行时仍可能回退到旧的 OpenAI 配置。

因此本次做了两类修正：

1. 让环境变量优先覆盖运行时 provider 配置。
2. 为 embedding 侧补齐 `dashscope` 兼容处理。

### 3.2 涉及的环境变量

实际保留的关键配置项如下，仅记录变量名，不在文档中记录真实密钥值：

- `APP_BRAND_NAME`
- `NEXT_PUBLIC_APP_BRAND_NAME`
- `LLM_BINDING`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_HOST`
- `EMBEDDING_BINDING`
- `EMBEDDING_MODEL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_HOST`
- `EMBEDDING_DIMENSION`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_RAG_ENABLED`
- `SUPABASE_RAG_DEFAULT_KB_NAME`
- `SUPABASE_RAG_SOURCES`
- `SUPABASE_RAG_INCLUDE_QUESTIONS`
- `SUPABASE_RAG_TOP_K`
- `SUPABASE_RAG_FETCH_COUNT`
- `SUPABASE_RAG_TIMEOUT_S`
- `SUPABASE_RAG_MATCH_THRESHOLD`
- `SUPABASE_RAG_VECTOR_WEIGHT`
- `SUPABASE_RAG_TEXT_WEIGHT`
- `SUPABASE_RAG_WEIGHT_STANDARD`
- `SUPABASE_RAG_WEIGHT_TEXTBOOK`
- `SUPABASE_RAG_WEIGHT_EXAM`
- `SUPABASE_RAG_WEIGHT_QUESTIONS`
- `SUPABASE_RAG_WEIGHT_STANDARD_PRECISION`
- `SUPABASE_RAG_QUESTION_WEIGHT_EXAM`
- `SUPABASE_RAG_QUESTION_WEIGHT_QUESTIONS`
- `SUPABASE_RAG_MAX_PER_DOCUMENT`

### 3.3 改动点

#### `deeptutor/services/config/provider_runtime.py`

作用：

- 为 `dashscope` 补齐默认 embedding provider 推断。
- 在 LLM 和 Embedding 配置解析时，优先使用显式环境变量，而不是旧的内部 profile。

为什么要改：

- 否则容器里即使已经配置好 DashScope，运行时仍可能使用旧 provider。

#### `deeptutor/services/config/env_store.py`

作用：

- 读取配置时，将进程环境中的关键项补入配置存储。

为什么要改：

- Docker/Compose 注入的环境变量不一定都落盘到 `.env`，如果只依赖文件，运行时会丢失一部分实际配置。

#### `deeptutor/services/embedding/client.py`

作用：

- 将 `dashscope` 视为 OpenAI-compatible embedding provider 处理。

为什么要改：

- 这样才能复用现有 embedding 客户端逻辑，而不必再写一套独立调用器。

## 4. Supabase 知识库接管方案

### 4.1 为什么不用原生本地知识库

本项目原生知识库链路是：

- 文件上传到本地目录
- 切块
- 生成向量
- 使用 `llamaindex_storage` 持久化

而当前业务上的真实知识资产已经沉淀在 Supabase，因此继续维护两套知识库会带来以下问题：

- 数据源分裂
- 维护成本更高
- 知识更新容易不同步
- Question Generate、题目解析等功能无法直接复用现有业务库

因此本次选择让 Supabase 作为主知识库。

### 4.2 Supabase 接入策略

本次不是把 DeepTutor 改造成“知识入库系统”，而是实现一个只读 `supabase` provider：

- DeepTutor 只负责查询和使用召回结果。
- 上层仍然调用 `rag_search`。
- 下层根据 KB 配置自动转发到 Supabase RPC。

### 4.3 召回策略

最终采用的召回策略不是简单打一条向量检索，而是分源并发检索后再融合：

默认数据源：

- `standard`
- `textbook`
- `exam`
- `questions_bank`（可配置开启）

具体策略：

1. 查询时只生成一次 query embedding。
2. 对 `standard`、`textbook`、`exam` 分别调用 `search_unified`。
3. 对题库单独调用 `search_questions_bank_vector`。
4. 当 query 中命中规范编号或章节编号时，额外调用 `search_kb_chunks` 做精准补召回。
5. 在 DeepTutor 内部做加权 RRF 融合、去重、source diversity 和结果补水。

这样做的原因：

- `standard` 负责权威规范性。
- `textbook` 负责教学化表达。
- `exam` 负责命题表达、考法、陷阱。
- `questions_bank` 负责题目生成、相似题、练题能力。

### 4.4 为什么 `exam` 默认参与

最初的担心是题干会污染普通解释型回答，但结合业务场景后，最终结论是：

- 本系统服务的是一级建造师建筑实务场景。
- `exam` 是业务知识资产的一部分，而不是边缘数据。
- 正确做法不是排除 `exam`，而是让它带权参与，并通过来源配额和加权融合防止它主导普通解释问答。

### 4.5 依赖的 RPC

本次接入主要复用了已有的 Supabase 检索接口：

- `search_unified`
- `search_kb_chunks`
- `search_questions_bank_vector`

注意：

- 文档层面记录接口名和用途，不记录具体密钥或数据库连接串明文。
- 后续如 RPC 参数签名变更，需要优先修改 `SupabasePipeline`。

### 4.6 关键代码改动

#### `deeptutor/services/rag/pipelines/supabase.py`

作用：

- 新增只读 Supabase RAG provider。
- 实现 `search()` 主流程。
- 通过 HTTP RPC 调用 Supabase。
- 执行多源并发、加权融合、题目型补强、精准命中、结果补水。

说明：

- `initialize`、`add_documents`、`delete_documents` 等写操作直接报错，明确只读语义。

#### `deeptutor/services/rag/factory.py`

作用：

- 注册 `supabase` provider。
- 让工厂可以基于 KB 配置创建 `SupabasePipeline`。

#### `deeptutor/services/rag/pipelines/__init__.py`

作用：

- 导出 `SupabasePipeline`，保证懒加载和工厂分发正常工作。

#### `deeptutor/services/config/knowledge_base_config.py`

作用：

- 从环境变量自动注册一个远端知识库。
- 将该 KB 标记为：
  - `rag_provider: supabase`
  - `remote_backend: supabase`
  - `remote_read_only: true`
  - `status: ready`

说明：

- 这一步是“让系统知道有这个 KB”。
- 若后续升级后 KB 列表里不再出现 `supabase-main`，优先检查这里的合并逻辑是否被上游覆盖。

#### `deeptutor/knowledge/manager.py`

作用：

- 让知识库管理层识别远端 KB。
- 在知识库信息里暴露 `remote_backend`、`remote_read_only`。
- 对远端 KB 设置可用状态，避免前端误判为未初始化。

#### `deeptutor/api/routers/knowledge.py`

作用：

- 拦截对远端只读 KB 的创建、上传、同步、删除类写操作。

为什么要改：

- 不做保护的话，前端仍会尝试把它当本地 KB 使用，产生错误行为。

## 5. 品牌替换为“鲁班智考”

### 5.1 目标

让系统在对话、API、页面标题、侧边栏展示、自我介绍中统一使用“鲁班智考”，而不是“DeepTutor”。

### 5.2 实现方法

#### 环境变量

新增并使用：

- `APP_BRAND_NAME`
- `NEXT_PUBLIC_APP_BRAND_NAME`

其中：

- 后端使用 `APP_BRAND_NAME`
- 前端使用 `NEXT_PUBLIC_APP_BRAND_NAME`

#### `deeptutor/services/branding.py`

作用：

- 新增统一品牌工具层。
- 提供 `get_brand_name()`、`get_api_title()`、`get_api_welcome_message()`。

为什么要抽这一层：

- 避免后面再出现散落在不同文件中的硬编码品牌名。

#### `deeptutor/agents/chat/agentic_pipeline.py`

作用：

- 替换聊天主链中的品牌提示词。
- 让模型最终回答阶段不再自称 DeepTutor。

#### `deeptutor/tutorbot/agent/context.py`

作用：

- 替换 TutorBot 身份描述中的品牌名。

#### `deeptutor/api/main.py`

作用：

- 修改 FastAPI title。
- 修改根路径欢迎语。

#### `web/app/layout.tsx`

作用：

- 修改浏览器标签页标题。

#### `web/components/sidebar/SidebarShell.tsx`

作用：

- 修改左侧栏产品名和图标 alt 文案。

### 5.3 验证方式

验证通过以下结果确认：

- `GET /` 返回欢迎语已变为“鲁班智考 API”。
- 前端页面 `<title>` 已变为“鲁班智考”。
- 聊天主链系统提示词已变为“你是 鲁班智考 ...”。
- TutorBot identity 已变为 “powered by 鲁班智考”。

## 6. 本次适配后，哪些能力不受影响

以下能力原则上不受“本地知识库停用”影响：

- 会话历史
- 用户画像
- 学习摘要
- 记忆系统
- Notebook
- Guided Learning 的非知识库部分

需要依赖 Supabase provider 才能继续工作的功能：

- 聊天中的知识检索
- Co-Writer 的 RAG source
- Question Generate
- 题目解析、相似题、跟随问题中的知识引用能力

## 7. 验证清单

本次适配完成后，至少应做以下检查：

1. 容器健康检查通过。
2. `GET /api/v1/knowledge/list` 能看到 `supabase-main`，且状态为 `ready`。
3. 普通知识问答可以从 Supabase 返回 `sources`。
4. 题目型 query 能召回 `exam` 或 `questions_bank` 结果。
5. 远端 KB 的删除、上传、同步操作被正确拦截。
6. 前端标题、侧边栏、根 API 欢迎语、自我介绍均显示“鲁班智考”。

## 8. 延迟评估

本次实测中，RAG 的额外耗时主要来自两部分：

- query embedding
- Supabase RPC 网络与检索耗时

经验值：

- 首轮冷启动查询通常更慢。
- 热启动后普通查询通常会快一些。
- 相比本地知识库方案，在 embedding 仍然是远端模型的前提下，新增的主要是 Supabase 网络调用与融合成本。

经验判断：

- 通常额外增加约 `0.8s` 到 `1.8s`
- 网络波动或冷启动时，增加到 `2s+` 也正常

这部分在后续升级后应重新做一次实测，不建议长期使用历史值替代。

## 9. 后续 DeepTutor 升级后的重做顺序

当上游 DeepTutor 升级后，建议按以下顺序重新适配：

1. 先确认 `.env` 中品牌、LLM、Embedding、Supabase 相关变量仍然完整。
2. 检查 `provider_runtime.py` 是否仍然会被内部 profile 覆盖。
3. 检查 `embedding/client.py` 是否仍支持 `dashscope` 兼容路径。
4. 检查 `knowledge_base_config.py` 是否还能自动注册 `supabase-main`。
5. 检查 `knowledge/manager.py` 是否仍正确识别 `remote_read_only`。
6. 检查 `rag/factory.py` 和 `rag/pipelines/__init__.py` 是否仍然注册 `supabase` provider。
7. 检查 `supabase.py` 中 RPC 参数签名是否仍与 Supabase 侧一致。
8. 检查 `api/routers/knowledge.py` 是否仍拦截远端 KB 的写操作。
9. 检查品牌相关文件是否被上游恢复为 `DeepTutor` 硬编码。
10. 最后做一次端到端验证和延迟测量。

## 10. 建议保留的经验

这次适配最重要的经验有 5 条：

1. 不要把“替换知识库”理解成“删除知识库功能”，真正需要替换的是 provider。
2. 不要让前端持有 Supabase 服务级权限，所有检索都应通过后端完成。
3. `exam` 不应被简单排除，而应当作为带权证据源参与融合。
4. 品牌名不要散落硬编码，必须抽成统一配置入口。
5. 升级后先验证 `rag_search` 和品牌提示词，再去看 UI 细节，否则容易误判系统已适配成功。

## 11. 推荐的回归测试顺序

每次升级或重做适配后，按以下顺序回归：

1. 打开首页，确认标题和品牌文案。
2. 访问后端根路径，确认欢迎语。
3. 打开知识库列表，确认 `supabase-main` 存在且只读。
4. 发起一个普通规范问答，确认能返回规范类来源。
5. 发起一个题目型问答，确认能返回题目类来源。
6. 尝试本地上传或删除远端 KB，确认接口会拒绝。
7. 检查系统自我介绍，确认不会再自称 `DeepTutor`。

## 12. 后续可选优化

如果后续继续深化，可考虑以下方向：

- 把知识库页面改成“远端知识库模式”文案，进一步弱化本地上传入口。
- 为不同意图引入更显式的 query routing。
- 将召回权重参数进一步配置化。
- 为 Question Generate 单独补一层基于 Supabase 的题目策略。
- 为 Supabase 检索链增加更细的日志与监控。

## 13. 对话 Prompt 风格迁移（鲁班智考）

### 13.1 迁移目标

在不推倒 DeepTutor 现有 agent 架构的前提下，把旧项目中更适合一级建造师建筑实务教学场景的对话风格迁移进来。

本次迁移不追求一模一样，而是保留 3 个最关键的能力：

- 明确的人格和业务身份
- 稳定的教学路由与收束逻辑
- 面向考试场景的输出护栏

### 13.2 客观取舍结论

评估结果是：

- DeepTutor 的优势在于 agent 架构、工具编排和功能扩展性
- 旧项目的优势在于教学 prompt 的业务贴合度、风格稳定性和学员满意度

因此本次方案不是二选一，而是：

- 保留 DeepTutor 的聊天架构
- 把旧体系里最关键的 prompt 哲学迁移到主聊天的最终回答阶段

### 13.3 本次选取的三层

只迁移旧项目里最值得保留的三层：

- identity
- teaching_policy
- guard_rails

原因：

- `identity` 决定老师味和考试味
- `teaching_policy` 决定“先答还是先引导”“如何收束”
- `guard_rails` 决定输出的可信度和稳定性

这三层迁进去之后，学员体感会明显更接近旧项目，但工程改动仍可控。

### 13.4 实现方式

新增一个可切换的聊天风格配置：

- `.env` 中加入 `CHAT_STYLE_PROFILE=luban_zhikao`

新增聊天风格适配模块：

- `deeptutor/agents/chat/style_profile.py`

作用：

- 根据 `CHAT_STYLE_PROFILE` 决定是否启用鲁班智考风格
- 从本地 prompt layer 目录装载三层文本
- 组合成主聊天 `responding` 阶段的系统 prompt

新增本地 prompt layer 文件：

- `deeptutor/agents/chat/prompt_layers/zh/identity.md`
- `deeptutor/agents/chat/prompt_layers/zh/teaching_policy.md`
- `deeptutor/agents/chat/prompt_layers/zh/guard_rails.md`
- `deeptutor/agents/chat/prompt_layers/en/identity.md`
- `deeptutor/agents/chat/prompt_layers/en/teaching_policy.md`
- `deeptutor/agents/chat/prompt_layers/en/guard_rails.md`

### 13.5 为什么只接 responding 阶段

DeepTutor 当前主聊天是四阶段：

- thinking
- acting
- observing
- responding

旧项目的 `general_agent` 类 prompt 本质上更适合“最终面向学员的回答层”，而不适合直接整包塞进工具调用阶段。

如果整包塞进所有阶段，会产生这些问题：

- token 变长
- 延迟更高
- 工具调用逻辑被教学话术干扰
- 多阶段指令互相冲突

因此本次优先把风格迁到 `responding` 阶段，这是收益最大、风险最低的接法。

### 13.6 同步兼容轻量聊天

为了避免旧聊天链路仍保持通用风格，也同步调整：

- `deeptutor/agents/chat/prompts/zh/chat_agent.yaml`

让轻量 `ChatAgent` 在走旧接口时，也尽量保持“建筑实务备考导师”的口吻和规则。

### 13.7 升级后的重做清单补充

DeepTutor 升级后，如果发现聊天风格丢失，按下面顺序检查：

1. `.env` 里的 `CHAT_STYLE_PROFILE` 是否仍存在
2. `style_profile.py` 是否仍被 `agentic_pipeline.py` 引用
3. `responding` 阶段是否仍调用自定义组合 prompt
4. `prompt_layers/zh/*.md` 是否被上游覆盖或遗漏
5. `chat_agent.yaml` 是否被上游恢复为通用助教文案

### 13.8 后续可继续深化的方向

如果未来还要继续接近旧项目风格，可继续做：

- 把 `thinking` 阶段也轻量接入教学策略层
- 增加 fast/deep 两套聊天 recipe
- 增加 slot contract，把学员水平、情绪、练习状态等上下文显式注入
- 把 Prompt layer 做成 registry 组合模式，而不是当前的最小适配版

### 13.9 后续补充实现

在后续一轮优化中，又补了两件事：

1. 把默认运行语言从 `en` 切到 `zh`
2. 把鲁班智考风格轻量接入 `thinking` 阶段

这样做的原因：

- 中文 layer 比英文兜底 layer 更接近原项目的真实教学风格
- 如果只改 `responding`，学员只能在最后的措辞上感受到变化，整体人格不够明显
- 让 `thinking` 也带上“结论先行、判断依据、得分点、问题收敛”的内部规划规则后，最终回答会更像原来的老师风格

升级后若再次出现“风格不明显”，除了检查 `responding`，还应检查：

1. `main.yaml` 和 `interface.json` 是否仍然默认 `zh`
2. `thinking` 阶段是否仍然走 `build_luban_thinking_prompt`

## 14. Langfuse 观测层接入

### 14.1 目标

本轮 Langfuse 的目标不是“把 SDK 深埋到所有业务代码里”，而是：

- 尽量少改稳定入口
- 保留 DeepTutor 快速升级能力
- 先拿到高价值观测：turn、阶段、LLM、Embedding、Tool、Supabase RAG

### 14.2 设计原则

采用“薄适配层”方案：

- 新增 `deeptutor/services/observability/langfuse_adapter.py`
- 所有业务代码只调用 `get_langfuse_observability()`
- 没有配置 Langfuse 时自动 no-op
- Langfuse 初始化失败也不会阻断主业务链

这样做的好处：

- 上游升级时冲突面很小
- Langfuse 逻辑集中维护
- 后续想改 SDK、改脱敏、改成本策略，只动一个适配层

### 14.3 实际接入点

本次只接了 6 个稳定入口：

1. `deeptutor/services/session/turn_runtime.py`

- 每轮 turn 建一个根 observation
- 记录 `session_id / turn_id / capability / language`
- 完成、失败、取消时都会更新状态

2. `deeptutor/agents/chat/agentic_pipeline.py`

- `thinking`
- `acting`
- `observing`
- `responding`
- `answer_now`

这些阶段都作为子 span 进入 Langfuse。

3. `deeptutor/services/llm/factory.py`

- `complete`
- `stream`

这是统一 LLM 入口，所以能覆盖绝大多数模型调用。

4. `deeptutor/services/embedding/client.py`

- 统一 embedding 调用入口
- 记录 text count、batch size、dimensions、model

5. `deeptutor/runtime/registry/tool_registry.py`

- 统一工具执行入口
- 记录工具名、参数摘要、输出摘要、成功失败

6. `deeptutor/services/rag/pipelines/supabase.py`

- 顶层 Supabase RAG 检索 observation
- 每次 RPC 单独一个 observation
- source hydration 的 `select` 也纳入观测

### 14.4 为什么不深埋

原因不是放弃观测，而是避免升级成本失控。

对 DeepTutor 这种上游迭代快的项目，观测最值钱的是：

- 一轮 turn 总耗时
- 四阶段各自耗时
- 每次 LLM 调用
- 每次工具调用
- Supabase RAG 检索耗时和命中
- Embedding 次数和规模

这些都已经能覆盖到。

如果继续把 Langfuse 深埋到更多 agent、更多 prompt 细节、更多内部 helper，虽然会更细，但：

- 升级冲突显著增加
- trace 噪声会快速增多
- 维护价值开始下降

### 14.5 token 与成本策略

当前实现优先保证“usage 可见”，成本采用保守策略：

- `usage_details` 默认记录
- `cost_details` 只有在价格已知时才写

具体做法：

- LLM 与 Embedding 的 token 当前由适配层估算
- 使用 `tiktoken` 的 `cl100k_base` 编码做近似估算
- 如果模型价格是已知安全映射，或者你显式配置了 `LANGFUSE_MODEL_PRICING_JSON`，就写入 `cost_details`
- 如果价格未知，就只记录 usage，不硬猜成本

这比“为了显示成本强行写死错误价格”更稳。

### 14.6 PII 与数据裁剪

适配层内置了最小脱敏与裁剪：

- 手机号
- 邮箱
- 常见 API Key 形态

同时会对：

- 超长文本
- 深层 dict / list
- 大块输入输出

做裁剪，避免把整份上下文原样送进 Langfuse。

### 14.7 环境变量

本次新增到 `.env` 的 Langfuse 相关变量：

- `LANGFUSE_ENABLED`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL`
- `LANGFUSE_TIMEOUT_S`
- `LANGFUSE_MASK_PII`
- `LANGFUSE_CAPTURE_INPUT`
- `LANGFUSE_CAPTURE_OUTPUT`
- `LANGFUSE_HTTPX_TRUST_ENV`
- `LANGFUSE_FLUSH_AT`
- `LANGFUSE_FLUSH_INTERVAL`
- `LANGFUSE_TRACING_ENVIRONMENT`
- `LANGFUSE_MODEL_PRICING_JSON`

其中：

- `LANGFUSE_ENABLED=false` 时全部旁路
- `LANGFUSE_MODEL_PRICING_JSON` 用于手工补充模型价格

示例：

```json
{
  "deepseek-v3.2": {
    "input_per_1m": 0.0,
    "output_per_1m": 0.0
  },
  "text-embedding-v3": {
    "input_per_1m": 0.0
  }
}
```

上面只是字段格式示例，不代表真实价格。

### 14.8 升级后如何保留 Langfuse

DeepTutor 后续升级时，只需要优先检查这些文件是否仍保持入口作用：

1. `deeptutor/services/session/turn_runtime.py`
2. `deeptutor/agents/chat/agentic_pipeline.py`
3. `deeptutor/services/llm/factory.py`
4. `deeptutor/services/embedding/client.py`
5. `deeptutor/runtime/registry/tool_registry.py`
6. `deeptutor/services/rag/pipelines/supabase.py`
7. `deeptutor/services/observability/langfuse_adapter.py`

只要这些入口还在，你的 Langfuse 能力就基本能重新挂上。

### 14.9 升级后的重做顺序

推荐重做顺序：

1. 先恢复 `langfuse_adapter.py`
2. 再恢复 `llm/factory.py`
3. 再恢复 `turn_runtime.py`
4. 再恢复 `tool_registry.py`
5. 再恢复 `embedding/client.py`
6. 最后恢复 `supabase.py` 和 `agentic_pipeline.py`

原因：

- `llm/factory.py` 和 `turn_runtime.py` 是最高价值入口
- `supabase.py`、`agentic_pipeline.py` 属于增强层，不是最低限度必需项

### 14.10 验证清单

每次升级后至少验证：

1. `python3 -m compileall` 能通过
2. 容器能成功启动
3. 普通聊天一轮后 Langfuse 中能看到 root turn
4. root turn 下能看到 `thinking / acting / observing / responding`
5. 能看到 LLM generation
6. 能看到 generation / embedding observation 的 `cost_details`
7. trace `totalCost` 不再长期固定为 0

### 14.11 当前部署的定价口径

当前这套鲁班智考部署使用的是阿里云百炼：

- `deepseek-v3.2`
- `text-embedding-v3`

为避免 Langfuse 中长期只有 token 没有金额，本次将当前部署的价格直接显式写入了
`.env` 的 `LANGFUSE_MODEL_PRICING_JSON`。

当前约定：

- `deepseek-v3.2`
  - 输入：`2.0 元 / 百万 Token`
  - 输出：`3.0 元 / 百万 Token`
- `text-embedding-v3`
  - 输入：`0.5 元 / 百万 Token`
  - 输出：`0.0 元 / 百万 Token`

说明：

- 这里的金额单位统一按 `CNY` 记录
- Langfuse 里会看到成本数字，但不会自动帮你换币种，所以代码里也会把
  `pricing_currency=CNY` 写进 observation metadata
- 如果后面百炼价格调整，不要改业务代码，优先只改 `.env` 里的
  `LANGFUSE_MODEL_PRICING_JSON`

### 14.12 价格来源与更新策略

2026-04-12 这次接入时，价格是按阿里云百炼官方文档确认后写入的：

- DeepSeek 模型价格页：`deepseek-v3.2` 当前为输入 `2 元 / 百万 Token`、输出
  `3 元 / 百万 Token`
- 向量模型价格页：`text-embedding-v3` 当前为 `0.0005 元 / 千输入 Token`
  即 `0.5 元 / 百万输入 Token`

后续升级或重做时，建议顺序：

1. 先查阿里云百炼最新价格
2. 只更新 `.env` 中的 `LANGFUSE_MODEL_PRICING_JSON`
3. 重启容器
4. 跑一轮真实对话
5. 在 Langfuse 检查新的 trace `totalCost`
6. 开启 RAG 后能看到 `rag.supabase.search`
7. 工具调用时能看到 tool observation

### 14.11 后续可继续增强

如果未来要继续深化 Langfuse，可按这个顺序：

1. 把 stage 级 observation 和 `StreamBus` 事件做更强的联动
2. 为不同 capability 建专门 trace 命名规范
3. 对 Question Generate 单独加更细的出题链路 span
4. 再考虑是否把 prompt 管理迁到 Langfuse

不建议第一阶段就上 prompt 托管，因为当前项目主聊天仍有不少 prompt 是动态拼接的，先把 tracing 稳住更重要。

## 15. 知识讲解风格增强

为了让鲁班智考在“知识讲解”类问题里更像原项目的教学风格，本次又补了一层风格约束：

- 知识点、章节、规范要求、概念辨析、考点归纳类问题
- 默认优先组织成：
  1. 核心结论
  2. 踩分点
  3. 易错点
  4. 记忆口诀或记忆抓手

实现位置：

- `deeptutor/agents/chat/prompt_layers/zh/identity.md`
- `deeptutor/agents/chat/prompt_layers/zh/teaching_policy.md`

设计原则：

- 不强制每条回答都拉成大模板
- 简单问题允许压缩成短要点
- “记忆口诀”只有在自然、准确时才给
- 如果口诀不自然，就退化成“记忆抓手”

这样做的目的：

- 让知识讲解更像考试辅导，而不是普通百科解释
- 让回答里更稳定地出现“答题抓手”
- 增强学员对“哪里拿分、哪里易错、怎么记”的体感

进一步参考原项目 prompt 体系后，又补充了两条适配原则：

- 借用 `teaching_core` 的“四要素教学框架”思路，但不做机械模板化
- 借用 `teaching_concept` 的“开场定位 -> 核心结论 -> 为什么 -> 场景化理解”骨架

本次没有整份照搬旧 prompt，而是把最有产品价值的教学结构抽出来，压进 DeepTutor 当前的回答风格层里。

## 16. 快速与深度模式适配

本次把普通聊天正式拆成两种执行模式：

- `fast`：走轻量 `ChatAgent`，只保留 `rag` 和 `web_search` 两类直达增强，不再经过 `thinking -> acting -> observing -> responding` 四阶段
- `deep`：继续走 `AgenticChatPipeline` 四阶段链路，保留完整工具编排、观察整理和深度回答

设计原因：

- 这更接近原项目 `fast / deep` 的产品思路
- 普通问答默认应该先保证响应速度
- 真正需要复杂工具链、题目分析、多阶段推理时，再切到深度模式

后端接线点：

- `deeptutor/capabilities/request_contracts.py`：新增 `chat_mode` 请求配置，默认读取环境变量
- `deeptutor/capabilities/chat.py`：根据 `chat_mode` 在 `ChatAgent` 和 `AgenticChatPipeline` 之间分流
- `deeptutor/services/session/turn_runtime.py`：把 `chat_mode` 写入 session preferences，保证会话恢复后模式不丢

前端接线点：

- `web/context/UnifiedChatContext.tsx`：新增 `chatMode` 状态、会话恢复、请求透传
- `web/app/(workspace)/page.tsx`：聊天页根据模式限制工具范围
- `web/components/chat/home/ChatComposer.tsx`：新增“快速 / 深度”切换

当前默认值：

- `.env` 中已设置 `CHAT_DEFAULT_MODE=fast`
- 对普通聊天来说，默认打开页面就是快速模式

限制说明：

- 快速模式当前只支持 `rag` 和 `web_search` 两类增强
- 深度模式才保留完整工具集合
- 这样做是有意的，避免“界面上选了快速，后台还在偷偷跑重工具链”

升级时如果要重做，优先检查：

1. `deeptutor/capabilities/chat.py` 里 chat capability 是否仍然是统一入口
2. `web/context/UnifiedChatContext.tsx` 是否还负责会话请求透传
3. `web/app/(workspace)/page.tsx` 的工具过滤逻辑是否仍在
4. `web/components/chat/home/ChatComposer.tsx` 的模式切换 UI 是否仍在
