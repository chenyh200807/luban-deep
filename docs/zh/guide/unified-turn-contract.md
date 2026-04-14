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

### 单一 trace 字段规范

统一 trace 字段在：

- `UNIFIED_TURN_TRACE_FIELDS`

关键字段包括：

- `session_id`
- `turn_id`
- `capability`
- `bot_id`
- `source`
- `interaction_profile`
- `chat_mode`
- `question_followup_context`
- `exact_question`
- `authoritative_answer`
- `corrected_from`

## TutorBot 怎么接进来

TutorBot 现在是业务身份，不是 transport。

也就是说：

- transport 走 `/api/v1/ws`
- TutorBot 通过统一 config 注入身份信息，例如：
  - `config.bot_id`
  - `interaction_hints`
  - `billing_context`
  - `followup_question_context`

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
