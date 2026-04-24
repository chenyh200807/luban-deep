# Unified Turn Contract 指南

这份文档解释 DeepTutor 当前为什么要把 turn 做成单一控制面。

配套关系：

- [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)：总纲和索引入口
- [contracts/turn.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/turn.md)：turn 专项硬约束
- [deeptutor/contracts/unified_turn.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/contracts/unified_turn.py)：schema as code
- `/api/v1/system/turn-contract`：机器可读导出
- `/api/v1/system/contracts-index`：机器可读 contract 域索引

现在前端会在启动时预热读取 `/api/v1/system/turn-contract` 做自检，Python SDK 会在初始化时读取本地 `contracts/index.yaml` 并校验 turn contract 是否对齐。

## 为什么必须统一

如果同一个 turn 概念被不同入口、不同 ws、不同状态来源、不同字段名同时表达，系统很快就会出现：

- 前后端协议漂移
- trace 不可对齐
- mobile / web / tutorbot 各有一套行为
- 修一个地方，另一个入口继续坏

所以 turn 不能靠“约定俗成”维持，而必须靠 contract 维持。

## 当前统一定义

### 单一入口

- 唯一流式入口：`/api/v1/ws`

允许存在：

- `/api/v1/chat/start-turn`
- `/api/v1/mobile/chat/start-turn`

但它们只能做 bootstrap，不得定义第二套流式协议。

移动端 HTTP adapter 可以返回面向客户端渲染的 read-model，例如：

- `created_at_ms / updated_at_ms`
- canonical `presentation`
- 合并后的用户可见 conversation id

这些字段只是 `TurnRuntimeManager + SQLiteSessionStore` 真相的投影。它们不能成为新的 turn/session authority，也不能参与 capability 路由决策。

### 单一 schema

统一 schema 在：

- [deeptutor/contracts/unified_turn.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/contracts/unified_turn.py)

核心消息：

- `start_turn`
- `subscribe_turn`
- `resume_from`
- `subscribe_session`
- `cancel_turn`
- `unsubscribe`

统一正文字段只有一个：`content`

### 单一状态机

真实状态来源只允许：

- `TurnRuntimeManager`
- `SQLiteSessionStore`

turn 合法状态只允许：

- `idle`
- `running`
- `completed`
- `failed`
- `cancelled`

`failed` / `cancelled` 也是 terminal truth。它们可以产生用户可见的 assistant terminal message，但该内容必须先经过 user-visible output 清洗并落到统一 session/message store；provider raw error、工具命令、RAG XML、内部 reasoning 或未清洗中间输出不能直接进入用户历史、stream error 正文或 outer trace 的 `assistant_content`。

### 单一 trace 字段规范

统一 trace 字段在：

- `UNIFIED_TURN_TRACE_FIELDS`

关键字段包括：

- `session_id`
- `turn_id`
- `release_id`
- `git_sha`
- `git_dirty`
- `deploy_manifest_hash`
- `capability`
- `bot_id`
- `source`
- `interaction_profile`
- `exam_track`
- `exam_track_label`
- `chat_mode`
- `active_object`
- `suspended_object_stack`
- `turn_semantic_decision`
- `question_followup_context`
- `semantic_router_mode`
- `semantic_router_mode_reason`
- `semantic_router_scope`
- `semantic_router_scope_match`
- `semantic_router_shadow_decision`
- `semantic_router_shadow_route`
- `semantic_router_selected_capability`
- `exact_question`
- `authoritative_answer`
- `corrected_from`

## grounded TutorBot 的 fast path

统一 turn contract 只约束 transport、schema、状态来源和 trace 词汇表，不要求所有请求都必须先走 `thinking`。

因此对 grounded TutorBot（例如 `construction-exam-coach`）允许存在这样的合法内部顺序：

- `acting -> responding`

典型场景是：

- 服务端先执行一次统一 `rag` 检索
- 如果 `exact_question` 已完整命中并覆盖全部小问，直接进入 authoritative response
- 不再额外跑通用 `thinking/observing`

这属于**统一 turn contract 之内的优化**，不是第二套链路。客户端只能依赖统一事件协议，不能把 `thinking` 当成必经阶段。

## TutorBot 怎么接进来

TutorBot 现在是业务身份，不是 transport。

也就是说：

- transport 走 `/api/v1/ws`
- TutorBot 通过统一 config 注入身份信息，例如：
  - `config.bot_id`
  - `interaction_hints`
  - `billing_context`
  - `followup_question_context`
  - `active_object`
- `active_object` 不只服务题目域；guided plan continuity 也必须收敛到同一个 canonical object。`active_plan_id / plan_id / guide_session_id / learning_plan_id` 只是兼容输入 alias，进入 runtime 后立即归一，不得继续作为并行权威。
- 通用对话域的 continuity 也允许落到 session-scoped `open_chat_topic`，它复用 session 自身 authority，不新增独立语义 topic runtime。
- `question_followup_context / question_followup_action / active_question_context` 只保留 question-domain 兼容和 presentation/result adapter 角色；真正的主链判断必须落在 `active_object + turn_semantic_decision`，不能让旧字段继续并列抢权。
- semantic router 灰度必须可审计：`semantic_router_mode` 表示 `primary / shadow / disabled`，`semantic_router_mode_reason` 表示当前为何进入该模式，`semantic_router_scope / semantic_router_scope_match` 表示灰度范围是否命中当前对象域，`semantic_router_shadow_*` 只记录并行比较结果，真正执行权威仍以 `semantic_router_selected_capability` 和主链结果为准。
- `exam_track` 是同一 TutorBot 下的考试方向上下文，用来约束 RAG/source plan 与最终回答口径；它不是新的 TutorBot 身份，也不是新的 capability route。入口、session preferences、trace 和 RAG routing metadata 只能复用这一份字段。

## 工作流

改 turn 相关代码前：

1. 先读 [CONTRACT.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/CONTRACT.md)
2. 再读 [contracts/index.yaml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/index.yaml)
3. 再读 [contracts/turn.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/contracts/turn.md)
4. 最后再改 router / runtime / frontend

改完至少验证：

1. `start-turn` 返回的 `stream.url` 是否仍是 `/api/v1/ws`
2. 是否引入了第二套消息字段
3. 是否引入了第二套状态来源
4. 是否新增了平行 trace 字段
