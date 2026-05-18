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
23. TutorBot / Chat agent runtime 如果已经持有 caller-passed `compiled_learning_truth`，必须通过现有 `rag` tool kwargs 传入 `RAGService`；adapter 只能透传和记录 compact availability marker，不得在 wrapper 内合成、拉取或改写 learner truth。
24. graph-aware retrieval 只能作为 compiled truth materialization 的只读上下文，允许表达 `question -> concept -> rubric_item -> error_code -> training_signal -> next_question` 这类 typed edges；它不是第二套 graph DB、第二套 RAG provider，也不得绕过 source-aware ranking。
25. retrieval maintenance workflow 必须是离线 dry-run / job 形态，输出 retrieval miss、citation、stale weak point、rubric coverage、eval case 报告；不得写 Supabase learner-state，也不得进入在线 `/api/v1/ws` 低延迟链路。

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

## 必测项

- `tests/services/rag/test_rag_pipelines.py`
- `tests/services/rag/test_supabase_strategy.py`
- `tests/agents/chat/test_agentic_parallel_tools.py`
