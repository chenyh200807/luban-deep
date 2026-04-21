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
7. 所有 stream event 必须声明统一可见性语义：`visibility=public|internal`。
8. `messages.content`、outer trace `assistant_content`、post-turn learning 只允许由 canonical final answer 物化；禁止再由任意中间 `content` 流片段直接拼接冒充最终答案。

## TutorBot 规则

- TutorBot 是业务身份，不是 transport。
- TutorBot 信息只能通过统一 turn config 传入，例如：
  - `config.bot_id`
  - `interaction_hints`
  - `billing_context`
  - `followup_question_context`
  - `active_object`
- `requested_response_mode` 是 turn runtime 内唯一有效的响应风格字段；历史 `teaching_mode` 只允许作为入口兼容 alias，在 `mobile` / `unified_ws` 等入口归一化后立即删除，不得继续进入 runtime metadata、trace 或 session 写回。
- guided plan continuity 也必须进入统一 `active_object`；`active_plan_id / plan_id / guide_session_id / learning_plan_id` 只允许作为入口兼容 alias，在 runtime 入口立即归一化，不得继续作为并行 authority。
- 通用对话连续性也应收敛到 session-scoped 的 `open_chat_topic`；它只是当前 session 的 canonical 投影，不是第二套 topic 抽取器，也不得被误当成 guided plan / active plan anchor。
- `question_followup_context / question_followup_action / active_question_context` 现在只允许作为 question-domain 的兼容 alias 或 result adapter；它们不得再独立决定 capability 路由或覆盖 `turn_semantic_decision`。
- semantic router 的灰度与回滚也必须走统一 turn trace：`semantic_router_mode / semantic_router_mode_reason / semantic_router_scope / semantic_router_scope_match / semantic_router_shadow_decision / semantic_router_shadow_route / semantic_router_selected_capability`。`shadow` 只允许并行比对，不得抢执行 authority。
- TutorBot 默认知识链只能由服务端 runtime 统一解析与注入，adapter 不得各自维护：
  - 默认工具链
  - 默认 knowledge base
  - 相关 trace 字段
- `mobile` 这类 HTTP bootstrap adapter 可以在服务端把认证态归一为 canonical `user_id` / `billing_context.user_id`，但客户端输入不得成为 learner / billing 身份真相，更不得因此长出第二套 session authority。
- grounded TutorBot 可以在统一 turn runtime 内执行 retrieval-first / exact-first fast path；这只改变内部执行顺序，不改变 `/api/v1/ws` transport contract。
- session `preferences.runtime_state` 只允许作为内部 runtime 恢复态保存；对外 session detail/list payload 不得把它当成公开 preferences contract 暴露出去。

## Schema

- 机器可读 schema：`deeptutor/contracts/unified_turn.py`
- Bot runtime defaults contract：`deeptutor/contracts/bot_runtime_defaults.py`
- 系统导出：`/api/v1/system/turn-contract`
- contract 域索引导出：`/api/v1/system/contracts-index`
- 受控启动自检（如管理面 / SDK / 集成测试）：读取 `/api/v1/system/turn-contract`
- Python SDK 启动自检：读取本地 `contracts/index.yaml` 并校验 turn contract 导出

## 流事件可见性

- `public`：允许进入用户可见链路，如正文 token、presentation、sources、public error。
- `internal`：只允许用于内部 trace、debug、运维或受控调试面板；默认不得进入用户正文、历史正文、outer turn trace 输出。
- `stage_start` / `stage_end` / `thinking` / `observation` / `tool_call` / `tool_result` / `progress` 默认应视为 `internal`，除非调用方显式提升。
- `result.metadata.response` 是 canonical final answer；如果某 capability 需要流式增量展示，增量 `content` 只能服务展示，不能替代 canonical final answer 的历史落库权威。

## 必测项

- `tests/api/test_system_router.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
- `tests/services/test_semantic_router.py`
- `tests/runtime/test_orchestrator_semantic_router.py`
