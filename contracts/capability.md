# Capability Contract

## 范围

这一份 contract 管：

- capability 路由决策
- capability request config schema
- orchestrator 选择 capability 的规则
- registry 作为唯一 capability 注册入口

## 单一控制面

- 单一 capability 入口：`ChatOrchestrator`
- 单一 capability schema 源：`deeptutor/capabilities/request_contracts.py`
- 单一 capability 注册入口：`CapabilityRegistry`

## 硬约束

1. capability 选择必须由 orchestrator 主导，router 不得偷偷维持第二套主路由逻辑。
2. capability config 不得在不同入口使用不同字段名表达同一语义。
3. 公开 capability config 必须先过 `request_contracts.py` 校验。
4. 新 capability 如果有公开配置，就必须补 schema 和 request validator。
5. adapter 可以做输入归一化，但不能成为 capability 决策的真实来源。
6. semantic router / rollout mode / shadow decision 也属于 orchestrator 的 capability 控制面；`mobile`、`unified_ws` 这类 adapter 只能传递 hints / auth / transport metadata，不能并行决定 capability。
7. adapter 如果需要把 token claims、wallet identity 或旧字段 alias 归一到 canonical 用户上下文，也只能服务于统一 request config 装配；不能把 capability 选择下沉到 adapter 本身。
8. 响应风格公开字段只能使用 `requested_response_mode`；`teaching_mode` 若仍被旧入口传入，只能在 adapter 层归一化并删除，不能继续作为 capability config 或路由决策字段存在。
9. 请求里的 `capability` 只允许作为 hint；最终写入 turn/session 的 capability 必须是 orchestrator runtime-resolved canonical capability，不能把 request hint 当成持久化真相。
10. adapter 可以做 presentation / timestamp / conversation read-model 装配，但不得在装配层重新决定 capability、改写 canonical final answer、或把 presentation blocks 当作 capability 执行结果的新 authority；adapter 输出必须来自 runtime-resolved turn/session/message 真相。
11. `exam_track` 这类领域上下文只能作为 request config / interaction_hints / metadata 的 scoped input 进入 orchestrator 和 capability；它不得改变 capability 选择权威，也不得被 adapter 用来创建平行 capability。
12. capability 只能看到 runtime 当前可用的工具；`web_search` 关闭或未配置时，registry 必须把它从 schema、prompt hints 和 enabled tools 中过滤掉。入口可以传递用户显式联网意图，但不得绕过 runtime availability authority，也不得把显式工具请求直接升级为 `current_info_required`；当前信息需求必须由 query intent / grounding decision 统一判定。
13. 练题 / 出题类 follow-up 的公开请求配置仍由 orchestrator 归一化：入口可以传入题量、题型、topic 等 hint，但 orchestrator 必须保留显式 config，不得用重新推断覆盖已有非空值。
14. orchestrator 从自然语言推断出的 `num_questions`、`question_type`、`lightweight_generation` 只属于本次 capability request config；它们不得成为 session / learner state 的第二份长期真相。
15. 批量出题请求不能因为上一题已经作答或已批改而退回 grading path；生成更多题目的 intent 必须收敛到 capability routing / request config，而不是 adapter 或 presentation 层重复判定。
16. 当同一用户消息同时包含当前题目的可解析作答和“下一题 / 继续练”类训练请求时，orchestrator 必须先保持 `deep_question` 的 submission/grading 路径；训练生成只能作为后续动作，不能抢在当前作答批改之前改写为 practice generation config。
17. 对上一轮出题 / 巩固邀请的短肯定回复或复述，属于 capability route 的语义承接问题；必须先由 orchestrator 的统一 semantic decision 归一为 `practice_generation` 候选。只有语义结果是普通聊天时，`bot_id` 默认绑定才可以让现有 TutorBot runtime 作为执行引擎。
18. `mobile` adapter 的 billing / wallet 端点只能做认证身份、wallet identity、额度 fail-closed 和展示 read-model 装配；不得把钱包、旧会员流水或展示层状态升级为 capability routing / request config authority。旧会员流水只能通过显式迁移/对账开关参与展示，默认 authority 必须是 wallet ledger。
19. `mobile` adapter 的 learning-brain projection 端点只能暴露 learner-state 已编译投影的 read-model；不得由 adapter 推断 capability、合成 compiled truth、触发 RAG，或把 projection 读取结果作为新的 capability authority。
20. `mobile` adapter 的 learning-report / learning-attempt detail 端点只能暴露 learner-state read model。`/mobile/learning-report` 允许做 `schema_version=1|2` / `Accept ...;v=2` 的 HTTP schema 协商，但不得据此触发 capability 或在 router 中重组学习事实；`/mobile/learning-attempts/{attempt_ref}` 不得触发 capability、不得解析训练意图、不得在 router 中重组学习事实；router 只做 auth、调用 read model、HTTP status 映射。
21. `mobile` adapter 的 mistake-book endpoints 只能把 user auth、`attempt_ref`、subject/bot 参数和 `If-Match` 交给 learner-state mistake-book service；不得从页面 key 推导 event id，不得在 adapter 中缓存 bookmark truth，也不得触发 capability。
22. `lightweight_generation` 是 `deep_question` 的 per-turn execution-strategy 配置项（详见 `docs/plan/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md`）。其唯一规约函数是 `deeptutor/tutorbot/teaching_modes.classify_practice_strategy`：fast/smart 模式下普通"再出 N 题 / 继续练 / 再来几道"默认 lightweight（1 ≤ N ≤ 5），仅当用户消息命中 heavy keyword（详细解析 / 命题依据 / 模拟真题 / 完整案例）、`reveal_preference=True`、`mode=deep` 或 `num_questions` 越界时回退到 heavy。orchestrator 在 `_prepare_practice_request_context` 是唯一调用方；coordinator / generator / 其它下游模块只能读取 `config_overrides["lightweight_generation"]`，不得另行判断。判断结果只属于本次 turn 的 capability request config，禁止写入 session / learner state 作为长期真相。
23. `ChatOrchestrator.handle()` 必须保证 outer cancel（turn timeout、FastAPI client disconnect、`GeneratorExit`）能向内部 capability task 传播：捕获 `CancelledError` / `GeneratorExit` 时取消 task、在 `DEEPTUTOR_CANCEL_GRACE_S`（默认 2 秒）内等待收尾、关闭 stream bus，并将 `turn_cancel_propagated=True` 写入 `context.metadata`；`_publish_completion` 必须在正常完成与取消两条路径都触发（放 `finally`）。禁止内部 capability task 在 parent turn deadline 之后继续调用 LLM。
24. capability 产出的 grading / explanation 结构体（含 `MCQGradingResult.evidence_refs`、`CaseRubricItemResult.source_fields` 等）允许在服务端内部保留完整 hidden authority；但 `/api/v1/ws` 公开出库前必须经统一 redaction（详见 [contracts/turn.md](./turn.md) §硬约束 13）：evidence-style entry 中 `field` / `source_field` / `source_key` / `name` 指向 hidden authority 的整项 drop；`source_fields: list[str]` 中 hidden 元素过滤；不允许 capability 自行另起 transport-side rewriter 绕开统一 redactor。
25. `mobile` / home dashboard 在 capability 尚未 resolved 前可以把点击意图暂存为 `learning_prompt_intent`。一旦 orchestrator 将该 turn 判定为练题生成（例如"先做一次摸底测评"、"小测"、"自测"等 starter / review prompt），必须在 `_prepare_practice_request_context` 边界把该 intent 提升为 `learning_training_intent` 交给 `deep_question`，并优先使用其中的 `question_count`。普通 TutorBot runtime 不得直接生成可提交练题题卡；可提交题卡必须来自 `deep_question` 的 QuestionArtifact / hidden grading authority 主链路。
26. TutorBot runtime 的自由文本不得被 presentation 层抽取并升级为可提交 `mcq` 题卡。TutorBot 只有在命中已有 `exact_question` / questions-bank authority、能构造服务端 `question_followup_context` / `active_object` 时，才允许输出 submit-able MCQ presentation；否则只能作为普通教学文本展示，避免 presentation 成为第二套题目 authority。
27. 题目生命周期场景与 skill 注入的唯一 authority 在 `deeptutor/services/question_lifecycle_skills.py`（详见 `docs/plan/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md`）。`SCENE_COMPOSITION` 是 scene → skill stack 的唯一组合表；`derive_question_lifecycle_scene` 是唯一的 scene 判定函数；`attach_question_lifecycle_scene_to_context` 是唯一的 metadata 写入入口（idempotent —— orchestrator 一旦设值，下游不得覆盖）。capability / adapter / TutorBot loop 等下游只允许 read `context.metadata["question_lifecycle_scene"]` 和 `context.metadata["question_lifecycle_skill_names"]`，不得自建第二套 scene → skill 映射、不得在 capability 入口外重新判定 scene。`SkillsLoader` 与 `question_lifecycle_skills` 之外的任何模块**不得**直接读 `construction-*/SKILL.md` 文件（lecture skill 的 `_read_skill_file` 是历史 carve-out，与本条款无关）。

## Schema

- 机器可读 schema：`deeptutor/capabilities/request_contracts.py`
- 当前已导出的 schema：`CAPABILITY_REQUEST_SCHEMAS`

## 必测项

- `tests/runtime/test_orchestrator_autoroute.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
