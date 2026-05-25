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
9. `failed` / `cancelled` 也是 terminal state；如果需要向用户历史或 stream 暴露 assistant 内容，只能物化为安全、可展示的 terminal assistant message，禁止把 provider raw error、工具命令、RAG XML、内部 reasoning 或未清洗中间输出直接写入用户可见消息。
10. mobile HTTP adapter 可以返回 convenience read-model 字段（如 `created_at_ms / updated_at_ms`、canonical `presentation`），但这些字段只能是统一 session/message 真相的投影，不得成为新的 turn/session authority，也不得定义第二套 streaming 协议。
11. `messages.metadata.request_snapshot` 只允许保存本轮入口请求的审计 / 回放投影（content、tools、knowledge bases、language、attachments、context references、config overrides）。它不得保存 learner profile、学习进度、memory context、active_object 或任何需要由 learner-state / session runtime 单独负责的 canonical state，避免形成双写真相。
12. mobile learning-brain HTTP read-model 端点只能读取 learner-state / compiled projection 的展示投影；它不得创建 turn、不得写 session、不得定义 streaming 协议，也不得成为 `/api/v1/ws` 之外的聊天入口。
13. `/api/v1/ws` 出库 stream event 必须在公开边界 redact hidden grading authority（plan §Phase 3 Step 3.2 / Batch C Gap 3）：`grading_key`、`scoring_points`、`correct_answer`、`explanation` 不得通过任何 `metadata.question_followup_context`、`metadata.active_object.state_snapshot`、`metadata.scoring_points` 或它们的嵌套 `metadata.metadata` 字段流出到客户端，**且不论嵌套深度（含 `metadata.question.*`、`construction_grading_result.*` 等）都必须 drop**。同时，**evidence-style 子结构**——形如 `{"source":...,"field":"correct_answer","value":"B"}` 或带 `source_field` / `source_key` / `name` 别名的 entry——必须按结构化规则 drop 整个 entry（仅保留 `field` 指向非 hidden 字段的 entry，如 `knowledge_point` / `article` / `trap_type`）；`source_fields: list[str]` 中 hidden 字符串元素被过滤，过滤后空列表整槽 drop。Redaction 只动 dict key / list entry，不重写 string，确保用户可见正文 (`event.content`) 不受影响。服务端内部 turn_runtime、capability、grader、learner_state 仍保留完整 hidden authority；redaction 是公开边界的最后一道保险。详见 `deeptutor/api/routers/unified_ws.py::_redact_event_for_public` 与 `deeptutor/services/question_followup.redact_question_followup_context_for_public`。
14. mobile assessment TestSet HTTP endpoints (`/api/v1/assessment/topics`, `/api/v1/assessment/create`, `/api/v1/assessment/{quiz_id}`, `/api/v1/assessment/{quiz_id}/submit`, `/api/v1/assessment/{quiz_id}/report`, `/api/v1/assessment/{quiz_id}/items/{question_id}/explain`) are non-chat, non-streaming adapters. They must not create a new WebSocket route, must not write turn/session state, and must keep hidden answer/grading artifacts server-side until deferred-feedback submit. `/api/v1/assessment/topics` may return a display-only recommendation, but that recommendation must not create turn state or training-intent authority. `/api/v1/assessment/{quiz_id}/items/{question_id}/explain` is a post-submit explanation projection: it may read the submitted result report plus server-side grading authority and may perform one bounded, non-streaming LLM call to generate richer per-item explanation text with wallet/billing capture. It must not mutate score, mastery, training intent, turn state, assessment session scoring truth, or create any chat/capability turn.

## TutorBot 规则

- TutorBot 是业务身份，不是 transport。
- TutorBot 信息只能通过统一 turn config 传入，例如：
  - `config.bot_id`
  - `interaction_hints`
  - `billing_context`
  - `followup_question_context`
  - `active_object`
- `requested_response_mode` 是 turn runtime 内唯一有效的响应风格字段；历史 `teaching_mode` 只允许作为入口兼容 alias，在 `mobile` / `unified_ws` 等入口归一化后立即删除，不得继续进入 runtime metadata、trace 或 session 写回。
- `turn.capability` 表示 runtime 实际选中的 canonical capability，不等于入口请求里传入的 capability hint；请求 hint 只允许作为装配输入，不能再被写回成 turn 真相。
- guided plan continuity 也必须进入统一 `active_object`；`active_plan_id / plan_id / guide_session_id / learning_plan_id` 只允许作为入口兼容 alias，在 runtime 入口立即归一化，不得继续作为并行 authority。
- 通用对话连续性也应收敛到 session-scoped 的 `open_chat_topic`；它只是当前 session 的 canonical 投影，不是第二套 topic 抽取器，也不得被误当成 guided plan / active plan anchor。
- `question_followup_context / question_followup_action / active_question_context` 现在只允许作为 question-domain 的兼容 alias 或 result adapter；它们不得再独立决定 capability 路由或覆盖 `turn_semantic_decision`。
- 当 `turn_runtime` 从入口请求、TutorBot mirror session、stored active object 或 interaction hints 中恢复到 question-domain evidence 时，它只能把 `question_followup_context / question_followup_action / entry_capability_hint` 写入 `UnifiedContext.metadata` / `active_capability` 作为 orchestrator 的输入证据；不得根据 action route 自行清空、改写或最终决定 canonical capability。`chat` / `tutorbot` 入口身份只是 hint，最终 capability 必须由 `ChatOrchestrator` / `QuestionLifecycleDecision` 统一裁定并写回 turn 真相。
- `turn_runtime` 可以把 question-domain action 适配成 `turn_semantic_decision`，但决策形状必须复用 `semantic_router.build_turn_semantic_decision` 的 canonical schema；不得在 runtime 内维护第二套 relation / next_action / allowed_patch 枚举或结果结构。
- `presentation / fallback_text / response` 是用户可见 read model，不得被 `turn_runtime` 反向解析成新的 `question_followup_context` 或 `active_object`。需要承接批改的 capability 必须显式产出 canonical `question_followup_context` / `active_object`。
- TutorBot 普通文本题目解析只能作为 display-only presentation，用于隐藏答案或改善展示；不得由此生成 canonical `question_followup_context` / `active_object`。能进入后续批改状态的题目必须来自 `deep_question` 或 exact-question 结构化 authority。
- 当已有 question-domain 上下文且用户消息包含可解析作答时，turn runtime 必须优先归一为 `answer_questions` 批改动作；“下一题 / 继续练 / 该练什么”等训练请求只能在本次作答处理之后生效，不能覆盖当前作答批改。
- 练题出题属于 question authority 域。即使入口带有 `bot_id=construction-exam-coach` 或 TutorBot 默认知识库，`practice_generation` 也不得被预先 pin 到 TutorBot；必须交给统一 semantic route / `deep_question` 生成 canonical `active_object`、`question_followup_context`、隐藏标准答案与后续批改依据。TutorBot 可以参与普通讲解、知识问答和已命中精确题目的 grounded answer，但不得成为出题标准答案的第二套 authority。
- 如果最近 assistant turn 明确发出“出同考点题 / 巩固练习 / 继续练题”邀请，下一轮用户的短肯定回复或复述该邀请必须被归一为 question-domain `practice_generation` 候选，由统一 semantic route 决定是否进入 `deep_question`；`bot_id` / TutorBot 默认绑定只能在语义结果为普通聊天时决定执行引擎。
- `exam_track` 只表示同一 `construction-exam-coach` 下的考试方向上下文，如一建 / 二建 / 一造 / 二造；它可以进入 `interaction_hints`、session preferences 和 trace，作为 RAG/source plan 与回答口径的 scoped metadata，但不得成为第二个 TutorBot 身份、第二套 capability route 或第二套 knowledge-chain authority。
- semantic router 的灰度与回滚也必须走统一 turn trace：`semantic_router_mode / semantic_router_mode_reason / semantic_router_scope / semantic_router_scope_match / semantic_router_shadow_decision / semantic_router_shadow_route / semantic_router_selected_capability`。`shadow` 只允许并行比对，不得抢执行 authority。
- TutorBot 默认知识链只能由服务端 runtime 统一解析与注入，adapter 不得各自维护：
  - 默认工具链
  - 默认 knowledge base
  - 相关 trace 字段
- `web_search` 属于可配置联网能力，不是 TutorBot 默认知识链。若 config runtime 判定其关闭或未配置，mobile / web / unified turn adapter 必须过滤请求中的 `web_search`，也不得因时效性意图自动追加。客户端显式请求 `web_search` 只能表示“允许联网能力参与”，不得单独归一为 `interaction_hints.current_info_required=true`；是否需要当前信息必须由服务端 query intent / grounding decision 判定，且是否真正启用工具仍只由 config runtime 决定。
- `mobile` 这类 HTTP bootstrap adapter 可以在服务端把认证态归一为 canonical `user_id` / `billing_context.user_id`，但客户端输入不得成为 learner / billing 身份真相，更不得因此长出第二套 session authority。
- `mobile` 的 `/api/v1/chat/start-turn` 在创建 turn 前可以根据 canonical wallet ledger 做额度 fail-closed；额度耗尽时必须返回 `billing_quota_exceeded`，且不得创建 pending turn、不得写入第二套 session 状态。
- `mobile` 的 `/api/v1/mobile/chat/start-turn` 可以接收 `prompt_intent`：chat 路径只允许归一为 `config.learning_prompt_intent`，deep_question 路径只允许归一为 `config.learning_training_intent`。该 intent 只能作为 post-turn conversation evidence 或 deep_question 训练目标上下文，不得成为新的 session、route、learner-memory 或推荐 authority。
- unified turn finalization 可以在 assistant answer 完成后触发 learner-state conversation evidence 写入；turn wrapper 只传 `turn_ref`、用户文本、canonical assistant 文本、`learning_prompt_intent` 与 source refs，实际是否写入、信号分类、质量门槛、PII redaction、payload schema 必须由 learner-state helper 负责。`learning_prompt_intent` 只能把信号归一为 `home_prompt_clicked`，不得成为唯一写入条件。
- grounded TutorBot 可以在统一 turn runtime 内执行 retrieval-first / exact-first fast path；这只改变内部执行顺序，不改变 `/api/v1/ws` transport contract。
- TutorBot response mode 的公开观测口径必须体现单轮执行策略：
  - `fast` 是 `kb_first + single_shot_with_prefetch`，允许模型 fallback 和已启用的 `web_search` 预取，但不得进入完整 deep agent loop。
  - `deep` 是 `kb_first + full_agent_loop`，保留 TutorBot 原有多轮工具执行能力。
  - 常规 `execution_path` 使用 `tutorbot_kb_first_fast_policy` 或 `tutorbot_kb_first_full_agent_policy`；exact authority shortcut 可继续记录为 `tutorbot_exact_fast_path`。
- `llm_selection` 只允许携带 catalog 内的 `profile_id` / `model_id`，用于本次 turn 的 request-scoped LLM 解析；provider secret、endpoint、binding 仍由服务端 model catalog 唯一持有。它可以进入 request snapshot 和 session preferences 作为审计/恢复提示，但不得改写全局 catalog，也不得成为第二套 LLM authority。
- session `preferences.runtime_state` 只允许作为内部 runtime 恢复态保存；对外 session detail/list payload 不得把它当成公开 preferences contract 暴露出去。
- mobile conversation id 与 TutorBot internal session id 可能同时存在于历史数据中；adapter 只能把它们归一为同一个用户可见 conversation read-model，并在删除/归档等操作中覆盖同一 owner scope 下的 direct 与 mirror variants，不能让 mirror session 成为第二套会话真相。

## Schema

- 机器可读 schema：`deeptutor/contracts/unified_turn.py`
- Bot runtime defaults contract：`deeptutor/contracts/bot_runtime_defaults.py`
- 系统导出：`/api/v1/system/turn-contract`
- contract 域索引导出：`/api/v1/system/contracts-index`
- 公开运行时能力投影：`/api/v1/system/public-capabilities`
- 受控启动自检（如管理面 / SDK / 集成测试）：读取 `/api/v1/system/turn-contract`
- Python SDK 启动自检：读取本地 `contracts/index.yaml` 并校验 turn contract 导出

## 流事件可见性

- `public`：允许进入用户可见链路，如正文 token、presentation、sources、public error。
- `internal`：只允许用于内部 trace、debug、运维或受控调试面板；默认不得进入用户正文、历史正文、outer turn trace 输出。
- `stage_start` / `stage_end` / `thinking` / `observation` / `tool_call` / `tool_result` / `progress` 默认应视为 `internal`，除非调用方显式提升。
- 客户端可以把 `internal` 事件投影成用户可见的安全处理摘要，但普通用户 UI 禁止渲染 raw `content`、raw `metadata`、tool args、tool result 或内部 stage 原文。
- `result.metadata.response` 是 canonical final answer；如果某 capability 需要流式增量展示，增量 `content` 只能服务展示，不能替代 canonical final answer 的历史落库权威。

## 必测项

- `tests/api/test_system_router.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
- `tests/services/test_semantic_router.py`
- `tests/runtime/test_orchestrator_semantic_router.py`
