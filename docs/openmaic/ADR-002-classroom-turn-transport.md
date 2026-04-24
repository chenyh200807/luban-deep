# ADR-002: Classroom Turn Transport

状态：Accepted

日期：2026-04-22

---

## 1. 决策

课堂内所有实时问答都必须复用 DeepTutor 现有统一 turn transport：

- 唯一流式入口：`/api/v1/ws`

SSE 只用于：

- job progress
- export progress
- review progress

HTTP 可以保留，但只允许作为 thin adapter 或 CRUD，不允许成为第二套聊天 transport。

---

## 2. 背景

v1.1 的风险不是“问答体验不够强”，而是把课堂问答写成了另一套系统：

- 一套 `/ask`
- 一套 SSE/WebSocket 组合
- 一套播放器本地语义协议

这会直接复制：

- session authority
- replay / resume
- trace
- auth / billing
- capability selection

---

## 3. P0 决策

P0 不把课堂内问答设为 launch blocker。

如果 P0 里实现课堂问答，必须满足：

1. 复用 `/api/v1/ws`
2. 复用现有 `chat` capability
3. 复用统一 turn trace
4. 不新增 `ActiveObjectType`

P0 的默认课堂问答模式是：

- grounded scene QA

即：

- 每轮问答基于当前课堂上下文提供 grounding
- 但不承诺新的对象级长期连续性

---

## 4. Classroom grounding context

P0 建议引入一个模块级上下文结构，但不提升为顶层 turn contract：

```ts
type ClassroomGroundingContext = {
  exam_classroom_id: string
  lesson_ir_version: number
  scene_key: string
  question_key?: string
  selected_block_key?: string
  mode: 'explain' | 'answer_question' | 'grade_followup'
}
```

用途：

- 让播放器通过统一 `/api/v1/ws` 发起 turn 时，明确告诉后端“当前讲到哪一段”
- 避免前端把大量课堂内容直接拼进用户消息正文

禁止：

- 前端直接拼整段 lesson 内容到 `message.content`
- 前端自己定义第二套 prompt 协议

---

## 5. Thin adapter 规则

如果为了兼容某些 UI 暂时保留：

- `POST /api/exam-classrooms/{id}/ask`

则它只能是 thin adapter，必须同时满足：

1. 不自己写 session
2. 不自己选 capability
3. 不自己定义流协议
4. 不自己维护 pending turn 状态
5. 只把请求转译到统一 `/api/v1/ws` 链路

换句话说：

- 可以是 bootstrap
- 不能是第二条主链路

---

## 6. P1 提升条件

只有在试点证明“grounded scene QA 不够”时，才允许进入 P1 扩展：

1. 需要对象级连续性
2. 需要新 `ActiveObjectType`
3. 需要更强的 classroom-aware routing

进入 P1 前必须回答：

1. 为什么现有 `chat` capability 不够？
2. 为什么 grounding context 不够？
3. 新对象如何进入 trace / replay / resume？
4. 如何保证不新增第二套 transport？

---

## 7. 非目标

本 ADR 不解决：

- 多角色动态互动
- 多角色 TTS
- PBL / 仿真
- capability promotion

这些都在 P1/P2 范围。

---

## 8. 必测项

- `test_classroom_chat_uses_unified_ws_only`
- `test_http_ask_adapter_does_not_define_stream_protocol`
- `test_router_does_not_select_capability_for_classroom_adapter`
- `test_classroom_grounding_context_is_not_serialized_as_user_message_body`
