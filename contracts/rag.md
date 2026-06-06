# RAG Contract

## 范围

这一份 contract 管：

- `RAGService` 作为统一 grounding 入口
- provider / pipeline / strategy 的边界
- exact-question 命中
- authority correction 语义
- retrieval trace 字段
- source-aware retrieval plan、provenance trace、compiled learning truth 的只读召回语义

## 单一控制面

- 单一 RAG 入口：`deeptutor/services/rag/service.py`
- provider / pipeline 可以多实现，但必须挂在统一 RAG 入口之后
- KB v5 只读直连 provider 只能作为 `RAGService` 后面的 provider 实现，
  通过只读事务调用 `public.search_chunks_v2`；不得成为第二套 RAG 入口、
  不得写 Supabase/PG，也不得承担评分 authority。
- exact-question 与 authority metadata 必须以统一字段进入上层 agent
- TutorBot 默认知识链只能由统一 runtime defaults 注入到 `tools/knowledge_bases`
- 本地知识库重建只能通过 `POST /api/v1/knowledge/{kb_name}/reindex`
  触发，后台任务必须复用 `RAGService.initialize` 重建 canonical
  `llamaindex_storage`，不得新增平行 indexing 入口。

## 硬约束

1. agent、router、tool 不得绕过 `RAGService` 私自直连另一个 retrieval 主入口。
2. 如果 exact-question 参与决策，必须稳定输出统一 metadata，而不是入口各写一套字段。
3. authority correction 只能建立在统一 retrieval metadata 之上，不能靠 prompt 猜测。
4. provider 可以替换，但上层消费到的语义契约必须稳定。
5. retrieval trace 命名必须统一，不得为同一语义创造平行字段。
6. 需要默认 grounding 的 TutorBot 业务身份，必须注册进统一 runtime defaults contract，而不是散落在 router 中。
7. 对于注册过默认 grounding 的 TutorBot，当模型本轮放弃工具时，agent 必须执行统一的 server-side RAG fallback，不能把 grounding 是否发生完全交给模型偶然发挥。
7a. 对 `construction-exam-coach` 这类注册过默认 grounding 的 TutorBot，建筑实务概念讲解 / 查漏补缺类短查询即使没有显式 citation flag，也必须先执行统一 server-side RAG；`fast` 与 `deep` 只区别响应密度和 agent loop 深度，不得把 `fast` 降级成无证据直接回答。
8. `exact_question` 不能再默认等同于选择题；案例题必须带 `answer_kind/case_bundle/coverage_state` 这类题型感知字段。
9. 当案例题 exact hit 只覆盖部分小问时，系统必须显式标记 partial coverage，并继续做补充检索；不能因为命中 exact 就直接跳过第二轮检索。
10. 对注册过默认 grounding 的 TutorBot，允许执行 `retrieval-first / exact-first` fast path；但 fast path 仍必须复用统一 `rag` 语义、统一 trace 和统一 `RAGService`。
11. 当案例题 full exact 命中且已完整覆盖全部小问时，`exact_question` 必须作为内容事实拥有高于 `answer_type` 和通用推断的优先级；但不得直接把召回文本短路成最终回答，最终表达必须交给 responding 层组织成用户可读讲解。
12. `answer/content` 只是兼容性的展示文本；结构化 retrieval 真相必须进入统一 `evidence_bundle`，上层不得再把 `content` 当作唯一 authority。
13. source selection 不能只靠 query surface；若上游已有 `intent/question_type/routing_metadata`，必须优先进入统一 source plan。
14. `routing_metadata.exam_track` 可以作为统一 source plan 的 scoped metadata，用来区分一建 / 二建 / 一造 / 二造等考试方向；它不能变成新的知识召回入口，也不能绕过 `RAGService`。
15. provider 出现 typed retrieval failure 时，RAG 工具必须 fail closed：对用户返回可理解的降级语义，对 trace 暴露 `retrieval_degraded / retrieval_status / provider / stage / retryable`，不得泄露 provider raw error 或把异常抹平成无语义失败。
16. Supabase Data API 出现项目级服务限制（例如 HTTP 402 / quota / overdue payment）时，pipeline 必须在检索 fanout 前或 fanout 内按 `RAGSearchError(provider="supabase", retryable=False)` fail closed，不能把项目级不可用降级成某个 source group 的普通 warning。
17. `needs_reindex` 表示当前 canonical 本地 index 不可信；清除该标记的唯一工程路径是从 `raw/` 源文档重新构建成功。不得只靠修改配置或进度状态把它改成 ready。
18. `retrieval_plan` 是可回放的检索计划 trace，只能描述本轮 source group、intent、query expansion 和 authority order；不得成为第二套 RAG 入口、聊天路由或 TutorBot mode。
19. `compiled_learning_truth` 只能由 learner-state / synthesis 层作为只读 projection 传入 `RAGService.search(...)` / provider context；`SupabasePipeline` 只允许 materialize retrieval documents，不允许写 learner-state、更新长期画像或从数据库自行拉取 learner truth。
20. compiled truth 默认只能进入 `ranking_trace.shadow_sources`，不得影响 `answer/content/sources` 或排序。只有显式 enable 且 intent 属于 `weak_point_review` / `next_training` 时，才允许进入最终候选；即便进入候选，也不能压过 exact-question、标准条文、题库标准答案。
21. `ranking_trace.provenance_features` 默认只暴露来源、authority、证据等级、人工确认、支持事件数量等 compact metadata；不得记录完整 compiled projection、原始私密画像、手机号、钱包、会员账户等敏感字段。
22. provenance boost 默认关闭；开启时也只能做 bounded adjustment，且 exact-question pinning 是独立 authority contract，不得依赖 provenance boost 才成立。
23. TutorBot / Chat agent runtime 如果已经持有 caller-passed `compiled_learning_truth`，必须通过现有 `rag` tool top-level kwargs 传入 `RAGService`；`routing_metadata` 只能记录 `compiled_learning_truth_available` 这类 compact marker，不得承载完整 projection，不得在 wrapper 内合成、拉取或改写 learner truth。
24. ChatCapability 只能归一化 mode / config 并委托 `AgenticChatPipeline`；fast mode 的工具裁剪也必须留在 agentic pipeline 内执行。不得在 capability wrapper 内另起一条直接 LLM / 直接 tool 终端路径，否则会绕开统一 RAG fallback、sources/result 组装和 trace authority。
25. graph-aware retrieval 只能作为 compiled truth materialization 的只读上下文，允许表达 `question -> concept -> rubric_item -> error_code -> training_signal -> next_question` 这类 typed edges；它不是第二套 graph DB、第二套 RAG provider，也不得绕过 source-aware ranking。
26. retrieval maintenance workflow 必须是离线 dry-run / job 形态，输出 retrieval miss、citation、stale weak point、rubric coverage、eval case 报告；不得写 Supabase learner-state，也不得进入在线 `/api/v1/ws` 低延迟链路。
27. 当 `compiled_learning_truth` final-source enablement 被显式开启且 intent 属于弱点复习 / 下一题训练时，最终 sources 必须至少保留一条已 materialize 的 compiled truth 证据；该证据只能追加在 exact-question、标准、教材等 authority 后面，不得抢占更高权威来源。
28. Langfuse / ClickHouse 的 canonical `rag.supabase.search` retriever observation 必须能查询到 compact `retrieval_plan` 与 `ranking_trace`。一次 `SupabasePipeline.search()` 只能产生一条 canonical `rag.supabase.search` retriever observation；不得新增同名 sidecar 来承载 trace，否则会污染 RAG 使用次数和 evidence gate。若 observability backend 只支持 string metadata，必须把 `retrieval_plan_json`、`retrieval_plan_intent`、`ranking_trace_json`、`ranking_trace_fusion` 写在这条主 observation 上。
29. `stage_timings_ms` 与 `performance_policy` 只能作为 `evidence_bundle` / metadata 中的 compact retrieval telemetry，用来解释弱点复习 / 下一题训练 fast path 是否跳过 rerank 或 second pass；不得成为新的路由 authority，也不得覆盖 `retrieval_plan` 的 intent / source group 语义。
30. TutorBot `rag` tool 可以在 `weak_point_review` / `next_training` 且 compiled truth final-source 明确启用时返回 learning fact capsule，但 capsule 只是对 `evidence_bundle.sources` 和 compiled truth source 的用户可读摘要；不得从 wrapper 内生成新的学习事实、修改 learner-state、或绕过 `RAGService` / `SupabasePipeline` 的 evidence bundle。
31. `deep_question` 在 `deep` / `smart` 批改讲评中可以先用统一 `rag` 入口检索题库/规范依据，再交给 `SubmissionGraderAgent` 组织教学反馈；RAG 只提供解释依据，不得覆盖 `active_object / questions_bank / construction_grading_result` 已确定的标准答案、分数或正确性。
32. exact-question fast path 必须要求强题目锚点：完整题干/选项、当前 active question、明确题目讲评请求且命中高置信题库来源，或正在批改当前题。低信息考试查询（例如"2025真题"、"历年真题"、"防水真题"、"2025真题有哪些"）只能作为目录/检索/澄清输入，不得由 `prepare_exact_question_probe` 生成 exact candidate，也不得让 TutorBot exact-first path 输出标准答案。若上游 metadata 带 `exact_question_blocked_reason`，RAG / TutorBot fast path 必须 fail closed 跳过 exact authority，并把该 reason 保留到 trace。
32a. exact-question 解析完整 MCQ 且用户当前题面选项顺序或单位表述不同于题库时，当前 query option surface 是本轮公开答案字母 authority。`HistoricalQuestionResolver` 可以在同一题干高置信命中后用稳定 value alias（例如 `25` ↔ `25年`）把题库标准答案 remap 到当前题面；不得继续展示题库旧字母，也不得让普通 RAG/LLM 重写 remap 结果。
33. chat 执行壳（`AgenticChatPipeline`）的 construction-exam skill overlay 必须从 `question_lifecycle_scene` turn metadata 读取由 orchestrator（`resolve_question_lifecycle_scene_decision`）写入的单一 scene authority，再经 `build_question_lifecycle_skill_context` 组织 skill 指令；不得在壳内用 legacy `detect_construction_exam_scene` / `get_construction_exam_skill_instruction` 独立重判 scene。scene 是 turn 级一等事实，两套执行壳（chat / tutorbot）只读不重判，由 `scripts/check_harness_authority.py` 静态保证。
34. `evidence_bundle.sources` must preserve compact public citation identity/location fields when available: `source_id`, `source_table`, `stable_id`, `source_span`, `content_hash`, `quote_hash`, `node_code`, `taxonomy_path`, source type, title, page, and standard/article locators. It must not expose private learner projections or hidden grading authority.
35. 对建筑实务学生端的概念讲解 / 查漏补缺类 `concept_like` 查询，source-aware ranking 必须把 2026 教材类 `textbook` 作为主概念 grounding，避免大体量标准库挤掉教材证据；只有显式规范、标准编号、条文解释等 `standard_like` 查询才允许把标准 / 精确条文权重提升到教材之上。“附依据 / 写出处 / 教材口径 / 答题依据”这类引用格式要求不得单独触发 `standard_like`。该约束只改变同一 `RAGService` 内的排序权重，不得新增第二套 RAG 入口或第二套引用来源 authority。
36. 学生端引用标准 / 规范 / 条文来源时，如果该 source 携带可信 `node_code` 或 `taxonomy_path`，公开 citation locator 必须同时展示“关联教材：第 X 章 / 第 Y 节”这类 2026 教材知识点定位；标准条文本身仍是 evidence source，教材定位是 learner remediation coordinate。缺少可信映射时必须 fail closed，不得凭关键词、标题、`chunk_id`、`source_id`、`stable_id` 硬编或反推教材章节。
37. 学生端 answer citation 的唯一展示 authority 是结构化 `citation_bundle.refs` / `citation_bundle.footer_text`；最终 `response` 正文不得内联 `〔1〕` marker、不得追加“依据”footer，也不得把引用段落混入“采分点 / 易错点 / 判断依据”等教学正文。前端必须在回答末尾用独立引用区域渲染结构化 refs。
38. 学生端开启 answer citation 时，不得压制普通聊天 / TutorBot 正文的 public `content` delta；citation 只负责最终引用组装。对于已经流式展示过的正文，最终组装阶段只能补未展示过的 citation suffix / delta，不能重复发送整段回答。exact-question authority correction、判题、出题、隐藏标准答案等需要先完成权威校验的路径仍允许缓冲到最终结果。
39. `PersonalizationContextPack` 可作为只读 request metadata 进入
    `RAGService.search(...)` 或 RAG tool runtime context。RAG 只能用它设置
    `routing_metadata.personalization_context_available`、解释现有
    `compiled_learning_truth` source group 是否可用，或携带 compact provenance marker；
    不得写 learner-state、不得计算 claim lifecycle、不得把 compiled truth override
    exact question、标准条文、教材或 hidden grading authority。
40. 案例题评分的可见分数、满分、给分/扣分、官方采分点批改，必须来自当前 active case、`questions_bank` / exact case retrieval、结构化 `case_bundle/grading_key/covered_subquestions` 或明确题库证据。普通 RAG 知识、模型常识、相似题经验、用户题面暗示只能支持 `open_skill` 提分诊断，不得生成 `projected_rubric`、标准分或官方阅卷语气；无评分 authority 时学生端必须 fail-open 为“本次不硬估标准分”。

## 当前统一语义

- `exact_question`
- `exact_question.answer_kind`
- `exact_question.case_bundle`
- `exact_question.coverage_state`
- `authoritative_answer`
- `corrected_from`
- `bot_id`
- `knowledge_bases`
- `exact_authority_response`
- `evidence_bundle`
- `evidence_bundle.retrieval_plan`
- `evidence_bundle.ranking_trace`
- `ranking_trace.provenance_features`
- `ranking_trace.shadow_sources`
- `retrieval_degraded`
- `retrieval_status`
- `compiled_learning_truth`
- `compiled_learning_truth.graph_context`
- `routing_metadata.compiled_learning_truth_available`
- `evidence_bundle.stage_timings_ms`
- `evidence_bundle.performance_policy`
- `learning_fact_capsule`
- `routing_metadata.personalization_context_available`
- `PersonalizationContextPack`
- `question_grading_explanation`
- `exact_question_blocked_reason`
- `evidence_bundle.sources[].source_id`
- `evidence_bundle.sources[].source_span`
- `evidence_bundle.sources[].content_hash`
- `evidence_bundle.sources[].quote_hash`
- `content_delta`
- `citation_final_delta`

## 必测项

- `tests/services/rag/test_rag_pipelines.py`
- `tests/services/rag/test_supabase_strategy.py`
- `tests/agents/chat/test_agentic_parallel_tools.py`
- `tests/services/citations/test_normalizer.py`
