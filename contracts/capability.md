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
27. 题目生命周期场景与 skill 注入的唯一 authority 在 `deeptutor/services/question_lifecycle_skills.py`（详见 `docs/plan/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md` 与 `docs/plan/2026-05-26-deeptutor-question-lifecycle-authority-consolidation-plan.md`）。`SCENE_COMPOSITION` 是 scene → skill stack 的唯一组合表；`resolve_question_lifecycle_scene_decision` 是 orchestrator 可调用的唯一 scene 决策入口：deterministic helper 只能收集稳定事实与安全闸门，LLM scene assistant 只能提出结构化语义候选（`llm_scene_candidate`），最终 scene / route 必须由 `QuestionLifecycleSceneDecision` 的 business gate 裁定。LLM 不得执行出题、批改、讲评或改写答案泄露策略。该 lifecycle decision 必须先于 TutorBot preselected capability / bot_id 默认绑定运行，且即使已有 active question / active object 也必须记录本轮 decision；TutorBot 是业务身份和执行引擎，不得绕过题目生命周期裁判，`chat` / `tutorbot` 请求里的 capability 只能作为入口 hint，必须先降级后交给 orchestrator 决定最终执行 capability。orchestrator 必须把 `question_lifecycle_decision`、`decision_source`、`llm_scene_candidate`、`business_gate_result`、`scene_confidence`、`required_anchor_status`、`exact_question_blocked_reason`、`selected_skill_names` 写入 turn metadata / trace metadata，供下游只读消费。capability / adapter / TutorBot loop 等下游只允许 read `context.metadata["question_lifecycle_scene"]` 和 `context.metadata["question_lifecycle_skill_names"]`，不得自建第二套 scene → skill 映射、不得在 capability 入口外重新判定 scene，也不得把 skill_context 的 scene 写回覆盖 orchestrator decision；trace / skill projection 只能 mirror 已有 decision。`QUESTION_LIFECYCLE_DECISION_AUTHORITY` 是默认开启的生产 emergency kill-switch，关闭时只能作为临时回退旧路由链路使用，正常验收和发布必须在开启状态下完成。明确要求系统出题、练题、测试学员的自然语言（例如"用 3 道题训练项目质量计划管理"）必须归入 `practice_generation`，并绑定 `construction-question-supply`；除非用户显式要求带答案或解析，否则 orchestrator 必须把 `reveal_answers=false` / `reveal_explanations=false` 交给 `deep_question`，避免练题生成泄露答案。无 active question 的自由文本 `question_review`（例如"分析一道验槽方法真题"、"用一道真题场景理解地基与基础"）必须由 orchestrator 路由到 `deep_question` 的题目讲评路径；orchestrator 只能写 scene / skill metadata，不得把该 scene 改写成 practice generation policy。低信息考试查询（例如"2025真题"、"历年真题"、"防水真题"）只能进入 clarification / catalog 语义，必须带 `required_anchor_status=missing_question_anchor`、`business_gate_result=blocked_low_information_exam_query` 与 `exact_question_blocked_reason=low_information_exam_query`；orchestrator 必须把该澄清写成 canonical `question_lifecycle_clarification` / `active_object`，用户下一轮输入"1"、"查看这一类真题目录或考点范围"或带原 topic 复述该选项时，必须由同一个 `resolve_question_lifecycle_scene_decision` 解析为 `exam_catalog_query`，而不是重新触发低信息拒答或被 legacy selector / TutorBot exact path 抢走。`exam_catalog_query` 只能回答目录、范围、可选下一步和不编造具体标准答案的安全提示，不得输出"阅卷结论 / 标准答案 / 命中题库原题"。只含年份/历年/题号但没有题干、选项或明确 topic anchor 的显式讲评请求（例如"分析一道2025真题"、"解析2025真题第15题"）同样属于低信息考试查询，不能让系统自选随机题直接讲评。无 active question 的"我选B"这类作答只能进入 clarification，必须带 `required_anchor_status=missing_active_question`；已有多题 active question 时，未带题号的单选答案（例如"我选B"）必须进入 clarification，带 `required_anchor_status=ambiguous_question_anchor` 与 `exact_question_blocked_reason=ambiguous_multi_question_answer_submission`，不得默认批改第 1 题。上述缺锚点输入不得触发 exact-question authority、不得输出"阅卷结论 / 标准答案 / 命中题库原题"，且不得被 preselected `deep_question` 或 legacy selector 偷走。`deep_question` 只能在 questions_bank / RAG exact-question 高置信命中时物化题干/选项并以 `review_mode=true` 展示答案解析；如果没有命中原题，必须诚实要求用户补充完整题干/选项，不得调用 Idea/Generator 虚构真题或输出可提交练习题卡。已有 active question 的批改/追问回合默认以 active question context 为 authority，TutorBot loop 不得把整张题卡再次送入 RAG 预取或工具循环；只有显式实时资料需求才允许恢复检索。未作答 active question 的直接要答案请求必须 fail-closed，仅在已有作答或用户明确"放弃/跳过这题"时允许展示参考答案/解析。`derive_question_lifecycle_scene` / `select_question_lifecycle_skill_names` 必须保持 import-safe 纯路径，不得在模块加载或 scene 判定时引入 TutorBot skill loader 的可选依赖；`SkillsLoader` 只能在 instruction builder 需要读取 skill 正文时惰性加载。`SkillsLoader` 与 `question_lifecycle_skills` 之外的任何模块**不得**直接读 `construction-*/SKILL.md` 文件（lecture skill 的 `_read_skill_file` 是历史 carve-out，与本条款无关）。
28. 个人学情状态类自由文本（例如"我最近学的怎么样"、"我的学情怎么样"、"我当前薄弱点是什么"、"我今年学习进度怎么样"）必须归入 canonical `learning_evidence_story` scene，并只读取 learner-state read model / `compiled_learning_truth` / `memory_context` 等已存在事实。除非用户显式要求联网或同时命中公共考试政策、报名、教材变化等外部实时信息边界，这类查询不得被升级为 `current_info_required`，也不得由 adapter / TutorBot loop 触发 `web_search`。TutorBot runtime bridge 只能把 `memory_context` 与 `compiled_learning_truth` 作为只读输入转发给主 loop / RAG，不得写 learner state、不得生成第二套学习事实。
29. `mobile` adapter 的 assessment TestSet 目录端点 (`/api/v1/assessment/topics`) 只能暴露 `assessment_forms` / blueprint coverage 派生的 read model，用于选择 topic TestSet。它可以附带 learner-state 派生的 display-only recommendation，但不得触发 capability、不得启动 turn、不得根据 learner state 动态生成题目，也不得把 catalog status 或 recommendation 升级为学习计划或 mastery authority。
30. `mobile` adapter 的 assessment 题目详细解析端点 (`/api/v1/assessment/{quiz_id}/items/{question_id}/explain`) 只能读取已提交 assessment session 的 result report 和服务端隐藏评分 authority，返回 post-submit explanation projection。它可以在该 HTTP 请求内做一次非流式 LLM 解析生成，并按 usage / fallback minimum 通过 wallet authority 捕获点数；扣费结果只是 commerce ledger 事实，不得成为 capability route、assessment score 或 learner-state truth。它不得触发 `ChatOrchestrator`、不得启动 capability、不得调用 `/api/v1/ws` 之外的聊天链路、不得生成新正式题、不得修改分数 / mastery / training_intent。若未来需要流式或交互式追问解析，必须回到统一 `/api/v1/ws`，本端点只能保持 post-submit projection。

## Schema

- 机器可读 schema：`deeptutor/capabilities/request_contracts.py`
- 当前已导出的 schema：`CAPABILITY_REQUEST_SCHEMAS`

## 必测项

- `tests/runtime/test_orchestrator_autoroute.py`
- `tests/api/test_unified_ws_turn_runtime.py`
- `tests/api/test_mobile_router.py`
