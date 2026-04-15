# Turn Contract

## 范围

这一份 contract 管：

- `/api/v1/ws`
- turn / session / stream / replay / resume
- HTTP bootstrap adapter
- turn 级 trace 字段
- TutorBot 作为业务身份接入 turn 的方式

## 单一控制面

- 单一流式入口：`/api/v1/ws`
- 单一 schema：`deeptutor/contracts/unified_turn.py`
- 单一状态来源：`TurnRuntimeManager + SQLiteSessionStore`
- 单一 trace 词汇表：`UNIFIED_TURN_TRACE_FIELDS`

## 硬约束

1. 禁止新增第二条聊天 WebSocket 路由。
2. 允许存在 HTTP adapter，但只能 bootstrap，不得自定义 streaming 协议。
3. turn 正文字段只能叫 `content`，不能再并行使用 `message` / `text`。
4. `resume_from` 只能重放已有 turn，不能创建新的状态机。
5. mobile / web / tutorbot 不能维护独立的 pending turn 状态来源。
6. 客户端不得假设 turn 一定先经过 `thinking` 再进入 `acting/responding`；在 grounded TutorBot fast path 下，合法顺序可以是 `acting -> responding`。

## TutorBot 规则

- TutorBot 是业务身份，不是 transport。
- TutorBot 信息只能通过统一 turn config 传入，例如：
  - `config.bot_id`
  - `interaction_hints`
  - `billing_context`
  - `followup_question_context`
- TutorBot 默认知识链只能由服务端 runtime 统一解析与注入，adapter 不得各自维护：
  - 默认工具链
  - 默认 knowledge base
  - 相关 trace 字段
- grounded TutorBot 可以在统一 turn runtime 内执行 retrieval-first / exact-first fast path；这只改变内部执行顺序，不改变 `/api/v1/ws` transport contract。

## Schema

- 机器可读 schema：`deeptutor/contracts/unified_turn.py`
- Bot runtime defaults contract：`deeptutor/contracts/bot_runtime_defaults.py`
- 系统导出：`/api/v1/system/turn-contract`
- contract 域索引导出：`/api/v1/system/contracts-index`
- 前端启动自检：读取 `/api/v1/system/turn-contract`
- Python SDK 启动自检：读取本地 `contracts/index.yaml` 并校验 turn contract 导出

## 必测项

- `tests/api/test_system_router.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
