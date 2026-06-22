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
9. `failed` / `cancelled` 也是 terminal state；admission shed / `server_busy` 可在公开 stream 语义上标记 `status=rejected`，但持久 turn status 与 runtime observer 必须收敛为 `failed` + `error=server_busy`，不得新增第二套 terminal enum。若需要向用户历史或 stream 暴露 assistant 内容，只能物化为安全、可展示的 terminal assistant message，禁止把 provider raw error、工具命令、RAG XML、内部 reasoning 或未清洗中间输出直接写入用户可见消息。
10. mobile HTTP adapter 可以返回 convenience read-model 字段（如 `created_at_ms / updated_at_ms`、canonical `presentation`），但这些字段只能是统一 session/message 真相的投影，不得成为新的 turn/session authority，也不得定义第二套 streaming 协议。
11. `messages.metadata.request_snapshot` 只允许保存本轮入口请求的审计 / 回放投影（content、tools、knowledge bases、language、attachments、context references、config overrides）。它不得保存 learner profile、学习进度、memory context、active_object 或任何需要由 learner-state / session runtime 单独负责的 canonical state，避免形成双写真相。
12. mobile learning-brain HTTP read-model 端点只能读取 learner-state / compiled projection 的展示投影；它不得创建 turn、不得写 session、不得定义 streaming 协议，也不得成为 `/api/v1/ws` 之外的聊天入口。
13. `/api/v1/ws` 出库 stream event 必须在公开边界 redact hidden grading authority（plan §Phase 3 Step 3.2 / Batch C Gap 3）：`grading_key`、`scoring_points`、`correct_answer`、`official_answer`、`official_slice`、`answer_key_authority`、`score_authority`、`grading_rubric_provenance`、`minimal_rationale`、`explanation` 不得通过任何 `metadata.question_followup_context`、`metadata.active_object.state_snapshot`、`metadata.scoring_points` 或它们的嵌套 `metadata.metadata` 字段流出到客户端，**且不论嵌套深度（含 `metadata.question.*`、`construction_grading_result.*` 等）都必须 drop**。同时，**evidence-style 子结构**——形如 `{"source":...,"field":"correct_answer","value":"B"}` 或带 `source_field` / `source_key` / `name` 别名的 entry——必须按结构化规则 drop 整个 entry（仅保留 `field` 指向非 hidden 字段的 entry，如 `knowledge_point` / `article` / `trap_type`）；`source_fields: list[str]` 中 hidden 字符串元素被过滤，过滤后空列表整槽 drop。Redaction 只动 dict key / list entry，不重写 string，确保用户可见正文 (`event.content`) 不受影响。服务端内部 turn_runtime、capability、grader、learner_state 仍保留完整 hidden authority；redaction 是公开边界的最后一道保险。详见 `deeptutor/api/routers/unified_ws.py::_redact_event_for_public` 与 `deeptutor/services/question_followup.redact_question_followup_context_for_public`。
14. mobile assessment TestSet HTTP endpoints (`/api/v1/assessment/topics`, `/api/v1/assessment/create`, `/api/v1/assessment/{quiz_id}`, `/api/v1/assessment/{quiz_id}/submit`, `/api/v1/assessment/{quiz_id}/report`, `/api/v1/assessment/{quiz_id}/items/{question_id}/explain`) are non-chat, non-streaming adapters. They must not create a new WebSocket route, must not write turn/session state, and must keep hidden answer/grading artifacts server-side until deferred-feedback submit. `/api/v1/assessment/topics` may return a display-only recommendation, but that recommendation must not create turn state or training-intent authority. `/api/v1/assessment/{quiz_id}/items/{question_id}/explain` is a post-submit explanation projection: it may read the submitted result report plus server-side grading authority and may perform one bounded, non-streaming LLM call to generate richer per-item explanation text with wallet/billing capture. It must not mutate score, mastery, training intent, turn state, assessment session scoring truth, or create any chat/capability turn.
15. `/api/v1/ws` 传输边界设两道内存防护，二者只防资源放大、不改变 turn 状态机或事件 `seq` 语义：(a) 单条入站文本帧硬上限 `unified_ws._MAX_WS_INBOUND_FRAME_CHARS`（128K 字符），超限帧在 `json.loads` 前 fail-fast 拒绝、不进入 turn 链路；(b) 每个 live subscriber 的内存事件队列有界（`turn_runtime._MAX_LIVE_SUBSCRIBER_QUEUE_SIZE`），满载时丢弃**最旧** live 事件以封顶慢消费者内存——SQLite 始终是事件真相，客户端通过 `subscribe_turn` / `resume_from` 的 `after_seq` backlog 重放补齐被丢弃事件，且 terminal `done` / `None` 关闭哨兵始终送达（慢消费者不会因哨兵被丢而挂起）。不得用"放大 live 队列"替代 SQLite replay 作为送达保证。mobile HTTP `/api/v1/chat/start-turn`（turn 的第二个入站边界）等价设 query 128K 硬上限（超限 422）+ 10次/60s 路由限流，与 WS `start_turn` 同治理（H9）。旧小程序包的 `/api/v1/mobile/chat/start-turn` 与 `/api/v1/mobile/chat/start` 只允许作为隐藏 schema 的兼容 bootstrap alias，必须复用同一个 handler、同一限流和同一 `/api/v1/ws` stream bootstrap，不得定义第二套 turn/session/stream truth。
16. `/api/v1/ws` live subscription task 只是 transport fan-out，不是 turn/session truth。旧 subscription task 的失败、取消或迟到 cleanup 不得删除同 key 的新 task；连接退出时必须 best-effort 取消并等待所有当前 task，且单个 failed task 不得跳过后续 cleanup 或 `record_ws_close()`。所有可恢复事件送达仍以 SQLite backlog / resume 为权威，live task 只负责当前连接投递。
17. Public final answers may carry server-side `citation_bundle` metadata (`citation_state`, `refs`, `claims`, `footer_text`). Citation rows are public projections over existing RAG / source / post-submit grading evidence and must not expose hidden grading authority or become a routing, scoring, or learner-state writer. When answer citations are enabled, citations must be assembled before `result.metadata.response` is materialized; if live content deltas differ, `result.metadata.response` remains the canonical displayed answer.
18. Turn resume / mobile background recovery must use the canonical session/message store, not a client-only pending flag. `turn_runtime` must persist stable turn identity on user and terminal assistant messages (`turn_id`, assistant `engine_turn_id`, optional `client_turn_id`, and terminal status) so mobile/web history read models can reconcile a backgrounded or disconnected pending turn with the already-completed assistant message. `client_turn_id` is a request-scoped recovery correlation key only; it must not become capability routing, learner-state, scoring, or session authority.
19. turn / TutorBot trace 可以携带 BI 身份互证字段：`raw_user_id`、`member_user_id`、`identity_resolution_status`、`identity_resolution_source`、`identity_matched`。这些字段只能由会员身份 authority 的只读投影归一，用于 Langfuse / BI 对账；它们不得成为 turn/session/learner-state/wallet authority，不得反写会员资料，不得把手机号写成 Langfuse `user_id` 或新增 PII 扩散。`identity_resolution_status=unmapped` 只表示观测身份待绑定，不能自动创建会员或覆盖 canonical `billing_context.user_id`。
20. end-user chat / turn 工具列表必须在 turn runtime 入口统一过滤，不得把 `code_execution`、`exec` 或其兼容 alias 暴露给非受信用户对话。执行边界还必须按本轮 canonical enabled/advertised tool set 二次校验 provider 返回的 native tool call 或 ReAct action；未广告工具只能产出内部拒绝 trace，不能调用 registry / worker / shell。该过滤只收紧 end-user tool exposure，不新增执行身份、capability route、RAG authority 或 learner-state writer；内部受控评测/开发工具若需要代码执行，必须走独立的受信控制面，不能复用普通 `/api/v1/ws` 用户请求字段自授权。
21. 所有认证后的 mobile LLM / 重计算 HTTP 端点必须挂 `route_rate_limit`（burst；昂贵 LLM 生成端点另加 daily 预算），与 WS `start_turn` 的 10/60s + 500/day 同治理：`/assessment/create`（6/60s + 60/day）、`/assessment/{quiz_id}/items/{question_id}/explain`（10/60s + 200/day）、`/learning-brain/projection`（20/60s）、`/conversations`（20/60s）、`/conversations/batch`（10/60s）。限流只防经济型 DoS / 资源放大，429 不改变 turn/session/assessment 状态机语义。
22. 事件循环线程是 turn streaming 的共享资源：turn 终结化阶段的同步副作用（钱包 capture、usage metering、learning-evidence 写入）必须经 `asyncio.to_thread` 离开事件循环执行，禁止在 `/api/v1/ws` worker 的事件循环线程上做阻塞网络 / bcrypt / LLM 等待（`learning_topic_resolver` 在检测到 running loop 时直接按 LLM miss 降级，不得恢复 thread-join 行为）。post-turn refresh 是 tracked background task 且包含真实挂起点：任何对其副作用的断言必须先等待任务完成，不得假设 turn `done` 事件后这些副作用已同步落地。
23. `turn_runtime` 可以在入口处、question lifecycle / semantic router 裁决前，归一化旧 transport 误包的纯 `{"content": "..."}` JSON envelope，并把解包事实仅作为 `transport_content_unwrapped` / `transport_content_unwrap_depth` trace metadata 记录；该兼容只处理唯一键为 `content` 的 wrapper，最多展开三层，不得把任意 JSON 业务 payload 当作聊天正文重写，也不得定义第二套 streaming 协议或绕过 question lifecycle / semantic router authority。
24. **跨能力上下文连续性（Context-Continuity 不变量 — 反复复发的"切链路丢上下文/失忆/鸡同鸭讲"类的单一根治）**：同一会话内，能力（`tutorbot` / `deep_question` / `chat`）切换**绝不允许丢失对话上下文**。落实为三条结构性规则：
    - **(a) 单一共享历史 authority**：`conversation_context_text` 是"本会话讨论过什么"的唯一共享历史 authority，由 `turn_runtime` 构建并**无条件注入每一个能力执行器**（含主对话 LLM；TutorBot 侧见 `teaching_modes.build_cross_capability_context_instruction`，非空即注入，不得用"继续/接着讲"等字面门控）。任何能力都不得声称"不知道前文"。
    - **(b) 单一 relation authority，禁止各层重判**：一个 turn"与既有会话上下文的关系"（承接当前题 / 回指过去对象 / 新话题 / 作答提交）只由 canonical `turn_semantic_decision`（`semantic_router.build_turn_semantic_decision`）判定一次；orchestrator 路由、capability、各确定性闸只能**读**它，不得用正则/启发式各自重判 relation 或"是不是作答"（见 §硬约束 27 与本文件 active_object 段）。新增任何独立的 submission / relation 判定都视为违约，应改为消费 canonical decision 或并入 `question_followup` 的对称 guard 单一来源。
    - **(c) 依赖上下文的 turn 必须落到上下文连续执行器，禁止 fail-closed 失忆**：当 relation 是"回指一个无法解析成结构化对象的过去对象"（canonical 签名 `semantic_router.is_unresolved_switch_followup`：`relation_to_active_object=switch_to_new_object` + `next_action=route_to_followup_explainer`），orchestrator **必须**把该 turn 路由到持有 `conversation_context_text` 的主对话 LLM（TutorBot），由它从共享历史承接讲解；**不得**送进 `deep_question` 等需要结构化 `active_object` 的解析器后 fail-closed 成"没定位到那道题/请重发题干"（那是失忆，违反本不变量）。`active_object` / `suspended_object_stack` 只对"重新作答/判分"是 authority，对"讲解一道历史讨论过的题"不是。`is_unresolved_switch_followup` 是该签名的唯一定义，capability 内的同名判断只能是 thin wrapper 委托它（禁止第二份拷贝漂移）。回归见 `tests/runtime/test_orchestrator_autoroute.py::test_orchestrator_routes_unresolved_switch_to_context_continuous_main_llm`。
    - **(d) 批量题集对象连续性（object continuity；E8 SEV-1，2026-06-21）**：当 `active_object` 是多题 `question_set`、用户对其中一道按序数作答（"第2题我选B"）时,该轮**必须在整组内判该题并保留其余题**,绝不允许把题组塌成被判那一道单题。塌缩点在 **turn-start 解析层**(`turn_runtime._submission_action_for_user_message`,在 capability 选路与判分之前),`resolve_submission_attempt` 会把 context 窄化成单题——必须经**单一 chokepoint** `question_followup.batch_answer_action_for_numbered_single`(单题+`index`→整组内判该题+`preserve_other_answers` 的 batch action）把它还原成全集,使写库的 `active_object` 仍是题组。一处治 tutorbot 与 deep_question 两条判分路径(两路都过 turn-start);`orchestrator._prepare_question_submission_context` 复用同一 helper 作 deep_question 路径的 defense-in-depth,不得各写一份(承接 (b) 单一权威)。否则后续"第1题"会按塌缩单题集 `items[0]` 解析判错题。回归见 `tests/api/test_unified_ws_turn_runtime.py::test_turn_start_preserves_batch_set_for_numbered_single_answer`。
    - **(e) turn-END 不是第二个 active_object writer（单一权威；E8/E1 真根因，2026-06-22）**：(d) 只收口了 turn-START;但 **turn-END 持久化(`turn_runtime._persist_and_publish` 约6035→6052 `set_active_object`)是第二个独立 writer**,它无条件用判分能力(tutorbot kb_first / deep_question)emit 的**单题** `active_object` 覆盖 turn-START 写入的全集——这才是 E8 SEV-1 的 durable 真凶,也使 E1 成为下游受害者(每个判分轮把 active 覆盖成最近一题,回指"最开始那道"时 canonical 里只剩最近题)。**铁律:`active_object` 的 identity/item 集合只由 turn-START 写一次;turn 内能力与 turn-END 只写"某一项的判分结果",不得改 active identity。** 判分轮在 turn-END 经 `_merge_grading_result_into_active_set` 把被判单题按 `question_id` **merge 回** prior 全集(保 identity+保全部 items),只有"被指对象不属于 prior set"的**真 switch(出新题)**才允许替换。两条判分路径(tutorbot/deep_question)都流经此单点。回归见 `tests/api/test_unified_ws_turn_runtime.py::test_turn_end_merge_preserves_batch_set_through_single_item_grading`。**验证纪律(对结果负责):** 此类 active_object/judging 改动必须 live-faithful 验证(当前 main base + cc_seq2 E1-E9 连跑≥3轮 + 确定性不变量),单测/静态审通过 ≠ live 修好(见 eval-design skill)。
    - **(f) turn-start suspend 守卫不得 demote 被序数回指的批量 set（task#14,2026-06-22）**:turn-start 有一段 suspend 守卫(`turn_runtime` 约 :4783),在"低信息自由文本 follow-up(无 incoming followup_question_context、无 action route)"时把 stored active_object **demote 进 suspended_object_stack** 并清空 active 槽。但当本轮是**对该批量 set 某一道的序数回指**("刚才第3题的答案和考点讲讲")时,demote 把 set 搬走,而 scene 低信息门只读 active_object/question_followup_context(不读 suspended_stack)→ 锚不到"第N题"→ fail-closed。**铁律:被序数回指的批量 set 不得在 turn-start 被 demote**——守卫前置 `_message_references_stored_question_set_item`(单一权威 `question_followup.requested_question_item_index`,序数解析到 stored set 的 item 即保 set 在 active)。set 由此流进 scene metadata,配合 capability.md §硬约束 38 的 Layer 2 序数锚定,"第N题讲讲"落 `question_review`。回归见 `tests/api/test_unified_ws_turn_runtime.py::test_t14_message_references_stored_question_set_item_keeps_set_active`。

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
- 入口请求显式传入 `capability=chat` / `capability=tutorbot` 时，turn runtime 必须先把它降级为 `_entry_capability_hint`，以空 capability 创建待裁决 turn，并在 `_run_turn` 中由 `ChatOrchestrator` / question lifecycle authority 决定最终 canonical capability；不得因为请求 hint 已存在就跳过 lifecycle selector。
- guided plan continuity 也必须进入统一 `active_object`；`active_plan_id / plan_id / guide_session_id / learning_plan_id` 只允许作为入口兼容 alias，在 runtime 入口立即归一化，不得继续作为并行 authority。
- 通用对话连续性也应收敛到 session-scoped 的 `open_chat_topic`；它只是当前 session 的 canonical 投影，不是第二套 topic 抽取器，也不得被误当成 guided plan / active plan anchor。
- `question_followup_context / question_followup_action / active_question_context` 现在只允许作为 question-domain 的兼容 alias 或 result adapter；它们不得再独立决定 capability 路由或覆盖 `turn_semantic_decision`。
- 当 `turn_runtime` 从入口请求、TutorBot mirror session、stored active object 或 interaction hints 中恢复到 question-domain evidence 时，它只能把 `question_followup_context / question_followup_action / entry_capability_hint` 写入 `UnifiedContext.metadata` / `active_capability` 作为 orchestrator 的输入证据；不得根据 action route 自行清空、改写或最终决定 canonical capability。`chat` / `tutorbot` 入口身份只是 hint，最终 capability 必须由 `ChatOrchestrator` / `QuestionLifecycleDecision` 统一裁定并写回 turn 真相。
- `case_grading` 是 question lifecycle 的前置业务事实，不是 TutorBot / deep_question 的自由路由结果。`turn_runtime` 只允许在两类稳定事实上提前盖章：当前消息自带完整案例题题干 + `【问题】` + `回答/作答`，或已恢复的 question-domain context + submission action 明确属于案例题。该盖章只能写 `question_lifecycle_scene=case_grading` 与 `question_lifecycle_skill_names` 等 metadata 供 orchestrator / capability 只读消费；不得在 runtime 中调用 lifecycle derive/attach 重新判 scene，不得决定最终 capability，不得写 score / missed point / deduction reason。
- `turn_runtime` 可以把 question-domain action 适配成 `turn_semantic_decision`，但决策形状必须复用 `semantic_router.build_turn_semantic_decision` 的 canonical schema；不得在 runtime 内维护第二套 relation / next_action / allowed_patch 枚举或结果结构。
- `presentation / fallback_text / response` 是用户可见 read model，不得被 `turn_runtime` 反向解析成新的 `question_followup_context` 或 `active_object`。需要承接批改的 capability 必须显式产出 canonical `question_followup_context` / `active_object`。
- TutorBot 普通文本题目解析只能作为 display-only presentation，用于隐藏答案或改善展示；不得由此生成 canonical `question_followup_context` / `active_object`。能进入后续批改状态的题目必须来自 `deep_question` 或 exact-question 结构化 authority。
- 当已有 question-domain 上下文且用户消息包含可解析作答时，turn runtime 必须优先归一为 `answer_questions` 批改动作；“下一题 / 继续练 / 该练什么”等训练请求只能在本次作答处理之后生效，不能覆盖当前作答批改。
- 当已有多题 question-domain 上下文且用户只给出单个选项、未指明题号时，turn runtime 必须把该输入视为 `ambiguous_question_anchor` 证据并交由 lifecycle clarification 处理；不得把它交给 LLM follow-up interpreter 二次猜测，也不得默认生成 `answer_questions` 或批改第 1 题。
- 当已有多题 question-domain 上下文且用户用稳定编号提交作答（如“第1题我选A，第2题我选BD”）时，turn runtime 必须把每个编号 item 的学员所选选项集合保留为 learner answer 并交由 question authority 判错；不得因为单选题收到了多字母答案就降级成追问或拒答。
- 当用户消息本身包含完整 free-text MCQ 题干、选项和作答 surface 时，本轮完整题面优先于 restored / candidate / explicit / suspended question-domain context。runtime 可以用 deterministic 同题 surface match 保护真实题卡提交；若 surface 不匹配，旧 `question_followup_context` / `active_object` / `suspended_object_stack` 只能作为历史状态保留，不得参与本轮批改或恢复为 grading authority。
- 当用户消息本身包含完整案例题题干 / `【问题】` / `回答|作答` surface 时，本轮完整题面和学员作答优先于 restored / candidate / explicit question-domain context。只有能用严格同题题面证明匹配当前消息的 active-object / followup context 可以继续作为同一题的 hidden authority；不匹配或无法证明同题的旧 `question_id`、`correct_answer`、`user_answer`、`grading_key` 只能作为历史状态保留，不得合并进本轮 case grading，也不得成为 Nexus/V1 的 `on_the_fly_reference` 评分 authority；当前题若未命中 compiled rubric，应由 case grading 主链路基于当前题干降级到 current reference 或 `derived_from_stem`，并在 trace 中标明 provenance。
- 完整 free-text MCQ 的同题判断必须以题干/stem surface 为主，选项值重合只能辅助、不能单独保留旧题 context；带内部逗号/句读的选项仍属于完整题面，不得被 lifecycle 误判成无锚点答案提交并阻断 exact-question authority。
- 稳定格式的选项或数值追问（如 `A错在哪里`、`那1.0m行不行`）属于 active-question follow-up，不是 answer revision。turn runtime 可以将其归一为 canonical `ask_followup` 输入证据；LLM follow-up interpreter 不得把这种 deterministic follow-up 升级为 `revise_answers` / `answer_questions`。
- 当 exact-question 命中携带官方答案 / 解析 authority 时，`turn_runtime` 在持久化和发布 `result` 前必须把缺失的 `correct_answer`、`explanation` 等 hidden authority 同步到服务端内部 `question_followup_context` 与 `active_object.state_snapshot`。这一步只补齐 canonical result state，不得根据 `response` / `presentation` 文本反向猜测答案，也不得在公开 WS 边界绕过 hidden authority redaction。
- 当用户在多题上下文中稳定点名“第 N 题答案 / 解析 / 公布”时，服务端仍以同一个 question-domain context 为 authority，但公开 reference feedback 只投影被点名 item；不得因顶层集合没有公开 `correct_answer` 就拒绝、澄清或改用 TutorBot/RAG 猜答案。
- 练题出题属于 question authority 域。即使入口带有 `bot_id=construction-exam-coach` 或 TutorBot 默认知识库，`practice_generation` 也不得被预先 pin 到 TutorBot；必须交给统一 semantic route / `deep_question` 生成 canonical `active_object`、`question_followup_context`、隐藏标准答案与后续批改依据。TutorBot 可以参与普通讲解、知识问答和已命中精确题目的 grounded answer，但不得成为出题标准答案的第二套 authority。
- 如果最近 assistant turn 明确发出“出同考点题 / 巩固练习 / 继续练题”邀请，下一轮用户的短肯定回复或复述该邀请必须被归一为 question-domain `practice_generation` 候选，由统一 semantic route 决定是否进入 `deep_question`；`bot_id` / TutorBot 默认绑定只能在语义结果为普通聊天时决定执行引擎。
- `exam_track` 只表示同一 `construction-exam-coach` 下的考试方向上下文，如一建 / 二建 / 一造 / 二造；它可以进入 `interaction_hints`、session preferences 和 trace，作为 RAG/source plan 与回答口径的 scoped metadata，但不得成为第二个 TutorBot 身份、第二套 capability route 或第二套 knowledge-chain authority。
- semantic router 的灰度与回滚也必须走统一 turn trace：`semantic_router_mode / semantic_router_mode_reason / semantic_router_scope / semantic_router_scope_match / semantic_router_shadow_decision / semantic_router_shadow_route / semantic_router_selected_capability`。`shadow` 只允许并行比对，不得抢执行 authority。
- semantic-router 决策遥测在 turn 完成时以独立 **internal** turn_event 落 `turn_events`（`type=observation` / `source=turn_runtime` / `stage=semantic_router_telemetry`），字段 `semantic_router_telemetry = {captured_raw_input, semantic_decision, final_executed_capability, drove_route, is_default_template, mode}`：纯 additive 观测，`internal` 可见性——不进公开 / replay 答案、不混入 assistant 消息；`captured_raw_input` 在路由决策点就地捕获（免事后 session+time join），`drove_route` 区分语义决策是否真驱动最终路由（vs lifecycle 覆盖 / 记账）。
- M35 scoring artifact shadow drill 只能作为 `/api/v1/ws` 的 runtime-only config 进入 turn runtime：`grading_engine_m35_artifact_shadow` 必须在 public capability schema 校验前剥离并只写入 `UnifiedContext.config_overrides` / metadata。该 shadow 默认关闭，`LUBAN_M35_ARTIFACT_SHADOW_ENABLED=false` 必须 fail closed；只允许服务端受控的 qa/test/operator cohort 看到 append-only `luban_m35_scoring_artifact_shadow` metadata，客户端 config 不得自授权真实学员进入 shadow。若后续需要真实学员可见，必须由单独 governed gate 注入服务端可信 cohort / 授权，不得复用客户端请求字段。该 block 不得替换 `construction_grading_result`，不得新增 WebSocket route / RAG lookup / learner-memory writer，不得写 DB/remote/published registry/canonical learner truth，且 `official_score_allowed` 必须保持 `false`，直到单独 governed release gate 授权。
- PGO coverage shadow 只能作为 `/api/v1/ws` 的 runtime-only config 进入 turn runtime：`grading_engine_pgo_shadow` 必须在 public capability schema 校验前剥离并只写入 `UnifiedContext.config_overrides` / metadata。该 shadow 默认关闭，`LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED` 未显式开启时必须 fail closed；只允许 qa/test/operator cohort 看到 append-only `luban_case_rubric_pgo_shadow` metadata。该 block 只能消费显式 PGO contract + per-point verdicts，用 `official_total_score × verdict coverage` 生成 shadow score；缺 PGO supply 时必须报告 blocker，不得从 legacy score、response 文本或旧 rubric 分值反推。它不得替换 `construction_grading_result`，不得新增 WebSocket route / RAG lookup / learner-memory writer，不得写 DB/remote/published registry/canonical learner truth，且 `official_score_allowed` / `canonical_write_allowed` / `writeback_performed` 必须保持 `false`。
- TutorBot 默认知识链只能由服务端 runtime 统一解析与注入，adapter 不得各自维护：
  - 默认工具链
  - 默认 knowledge base
  - 相关 trace 字段
- `web_search` 属于可配置联网能力，不是 TutorBot 默认知识链。若 config runtime 判定其关闭或未配置，mobile / web / unified turn adapter 必须过滤请求中的 `web_search`，也不得因时效性意图自动追加。客户端显式请求 `web_search` 只能表示“允许联网能力参与”，不得单独归一为 `interaction_hints.current_info_required=true`；是否需要当前信息必须由服务端 query intent / grounding decision 判定，且是否真正启用工具仍只由 config runtime 决定。
- `mobile` 这类 HTTP bootstrap adapter 可以在服务端把认证态归一为 canonical `user_id` / `billing_context.user_id`，但客户端输入不得成为 learner / billing 身份真相，更不得因此长出第二套 session authority。
- `mobile` 的 `/api/v1/chat/start-turn` 在创建 turn 前可以根据 canonical wallet ledger 做额度 fail-closed；额度耗尽时必须返回 `billing_quota_exceeded`，且不得创建 pending turn、不得写入第二套 session 状态。
- 计费是否真正生效由单一 authority `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED`（helper `deeptutor.services.wallet.is_billing_enforcement_enabled()`，默认开启）控制；只有显式配置 `false` / `0` / `off` / `no` 才进入内测或回滚放行。关闭时 `record_usage_points` 为 no-op（不扣 `balance_micros`、不写 wallet ledger），start-turn 也不做硬余额拦截，钱包保持 pristine。此时微信 turn 完成后可以把同一用量写入非财务 `MemberUsageMeter`，并在 trace 中标记 `billing_capture.status=metered_not_charged`；该状态只表示“已计量但未收费”，不得触发 `mark_usage_scope_billable`，不得写入钱包余额或财务流水。开启后由 wallet authority 扣费与拦截。
- 开启计费后，`mobile` 的 `/api/v1/chat/start-turn` 在创建 turn 前必须基于 canonical wallet snapshot 做硬余额 fail-closed：当 `balance_micros − frozen_micros` 低于本轮最小扣费（`_MINI_PROGRAM_CAPTURE_COST` points 折算 micros）时返回 `billing_quota_exceeded`；当 wallet id 缺失时按 0 余额拒绝；当 wallet service 未配置或不可用时返回 `billing_wallet_unavailable`。这些判断位置严格早于 `turn_runtime.start_turn`，不创建 pending turn、不交付答案。该硬门是上面 ledger 软额度门之外的余额门，二者都不得绕过 canonical wallet authority。
- 显式关闭计费时上述硬余额门不生效（内测/回滚放行），但软额度门与 billing_context 归一化逻辑保持不变。
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
- `turn_runtime` 可以在统一 `/api/v1/ws` 内发送 `progress` + `metadata.status_kind=turn_status` 的 public-safe 进度投影（如 `understanding` / `writing`），用于降低首屏空等感。该事件只能表达“服务端正在处理到哪一段”，不得携带 hidden grading authority、不得成为 capability route / scoring / learner-state / billing authority，也不得替代 terminal `result.metadata.response`。
- `result.metadata.response` 是 canonical final answer；如果某 capability 需要流式增量展示，增量 `content` 只能服务展示，不能替代 canonical final answer 的历史落库权威。若 capability 只产出同源 `assistant_content` / `content` 结果投影，`turn_runtime` 必须在统一 WS 出口清洗后物化为同一份 `result.metadata.response`，并且对 `subscribe_turn` / `resume_from` 回放的历史 public `result` 事件做同样投影，用于旧客户端兼容；该字段仍只是 canonical final answer 的公开投影，不得反向解析成评分、路由、learner-state 或 hidden authority。mobile / wx_miniprogram 回合如果在 terminal `done` 前尚未出现 public `result.metadata.response`，但 runtime 已有同源 final assistant content，必须由 `turn_runtime` 在 `done` 前物化一条 public `result`；传输层和客户端不得把空 `done`、pending flag 或历史补抓状态升级为第二套答案权威。
- `result.metadata.citation_bundle` 是 final answer 的公开引用投影，只允许包含 public-safe `citation_state / refs / claims / footer_text`，不得携带 hidden grading authority。
- `turn_runtime` 的 terminal observer metadata 可以携带 `latency_stages_ms`，用于把单轮耗时拆成 `context_route_preview`、`observability_start`、`context_build`、`capability_selection`、`user_message_persist`、`capability_stream` 等内部阶段，并由 runtime metrics / observer snapshot 聚合。该字段是运维观测投影，不是公开 stream contract、capability route、评分、计费或 learner-state authority；客户端不得依赖它做业务状态判断。
- `context_pack_trace.build_stage_timings_ms` 与 terminal observer metadata 的 `context_build_stage_timings_ms` 可以携带 context build 内部子阶段耗时（如 `route_resolver`、`session_history`、`learner_state`、`source_loader_*`、`context_pack`、`pack_render`），用于定位首屏与上下文构建性能瓶颈。它们只属于 trace/observability projection，不得改变 context route、候选选择、token budget、learner-state truth、评分或计费 authority。
- terminal observer metadata 可以携带 `start_turn_setup_stage_timings_ms`，用于拆解首个 `session` 事件前的准备阶段，如 `payload_normalize`、`active_object_lookup`、`followup_resolution`、`public_config_validation`、`bot_runtime_defaults`、`ensure_session`、`update_session_preferences`、`recover_orphaned_turns`、`cancel_active_turn`、`create_turn`、`register_execution`、`publish_session_event`。该字段只用于定位 first-visible 前置耗时，不得改变 turn 创建、session 偏好、active object、billing 或 follow-up authority。
- terminal observer metadata 可以携带 `capability_stream_stage_timings_ms` 与 `capability_stream_event_counts`，用于拆解 `capability_stream` 黑盒，如 `first_event`、`first_public_event`、`first_content`、`first_tool_call`、`first_tool_result`、`first_result`、`event_persist_total` 以及 capability stream 期间的事件类型计数。它们只用于判断 provider 首 token、工具调用、capability 内部阻塞或事件持久化开销，不得成为客户端展示、capability routing、评分、计费或 learner-state 的业务输入。

- terminal observer metadata、Langfuse turn observation metadata 与 TutorBot provider generation metadata 可以携带 `llm_stream_telemetry` / provider stream 聚合字段，用于继续拆解 `capability_stream` 内部的 TutorBot LLM 调用，例如 `call_site`、`provider_name`、`model`、`stream_chunk_count`、`stream_content_chunk_count`，以及 `provider_stream_create`、`provider_first_chunk`、`provider_first_content_delta`、`provider_stream_read` 等 provider stream 阶段耗时。该字段只能包含 provider 名称、模型名、计数和耗时，不得包含 prompt、用户输入、模型输出、tool 参数、secret 或 endpoint；它只用于运维诊断 provider 建流、首 token、chunk streaming 和 capability 内部阻塞，不得成为公开 stream contract、客户端展示、capability routing、评分、计费或 learner-state authority。
- Grading-to-Brain loop：`turn_runtime` 编排上下文时，除 `compiled_learning_truth` 外，还会把
  `personalization_context`（PersonalizationContextPack，来自 `build_context_candidates` 的同源投影）写入
  runtime `metadata`，供 agent loop / RAGAdapterTool / deep_question 读取，使 learner claim → 个性化下一步动作
  在实时回合可见。它是 learner-state 读模型的**只读投影**，不是第二套推荐 authority；缺 claims 时为空且不进 metadata，
  绝不由前端或回合自行编造推荐。`next_best_action` 在回合内只作 view-layer 呈现，权威仍属 learner-state。

## 必测项

- `tests/api/test_system_router.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
- `tests/services/test_semantic_router.py`
- `tests/runtime/test_orchestrator_semantic_router.py`
