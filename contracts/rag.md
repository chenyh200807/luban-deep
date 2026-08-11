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
  其 embedding 必须复用统一 `EmbeddingClient` / provider runtime config /
  usage-cost observation authority；其 Postgres 连接必须复用
  `connect_for_fact("kb_v5_chunk_retrieval", readonly=True)` 与
  `contracts/db_registry.yaml`，不得在 pipeline 内再次直读 `KBV5_DB_URL`、
  私建 DashScope HTTP client 或私建 DB 连接 authority。
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
17. LLM SDK 客户端生命周期：高频调用路径（`services/llm/executors.py` 的 `sdk_complete/sdk_stream`、agentic acting loop）必须复用 `get_pooled_openai_client()` 的进程级共享连接池，按 (api_key, base_url) 键控；每调用专属的头（如 `x-session-affinity`）必须走请求级 `extra_headers=`，不得为传 header 退回每调用新建 client（那会泄漏一个永不关闭的 httpx 池）。需要 client 级 header / 自定义 timeout / azure 形态时仍走 `make_openai_client()`，调用方自行管理生命周期。
17. `needs_reindex` 表示当前 canonical 本地 index 不可信；清除该标记的唯一工程路径是从 `raw/` 源文档重新构建成功。不得只靠修改配置或进度状态把它改成 ready。
18. `retrieval_plan` 是可回放的检索计划 trace，只能描述本轮 source group、intent、query expansion 和 authority order；不得成为第二套 RAG 入口、聊天路由或 TutorBot mode。
18a. KB v5 provider 是只读检索 implementation，不是 provider/runtime config authority：查询 embedding 必须先在 async 主链路通过 `EmbeddingClient` 生成并记录 usage/cost，再把 1024 维向量交给只读 DB 检索线程；缺少 `DASHSCOPE_API_KEY`、embedding 维度不为 1024、或 DB fact 无法经 registry 解析时，必须以 typed `RAGSearchError(stage="pipeline.kbv5.search")` fail closed，不得 fallback 到 Supabase、空成功或未计费 raw HTTP。
19. `compiled_learning_truth` 只能由 learner-state / synthesis 层作为只读 projection 传入 `RAGService.search(...)` / provider context；`SupabasePipeline` 只允许 materialize retrieval documents，不允许写 learner-state、更新长期画像或从数据库自行拉取 learner truth。
20. compiled truth 默认只能进入 `ranking_trace.shadow_sources`，不得影响 `answer/content/sources` 或排序。只有显式 enable 且 intent 属于 `weak_point_review` / `next_training` 时，才允许进入最终候选；即便进入候选，也不能压过 exact-question、标准条文、题库标准答案。
21. `ranking_trace.provenance_features` 默认只暴露来源、authority、证据等级、人工确认、支持事件数量等 compact metadata；不得记录完整 compiled projection、原始私密画像、手机号、钱包、会员账户等敏感字段。
22. provenance boost 默认关闭；开启时也只能做 bounded adjustment，且 exact-question pinning 是独立 authority contract，不得依赖 provenance boost 才成立。
23. TutorBot / Chat agent runtime 如果已经持有 caller-passed `compiled_learning_truth`，必须通过现有 `rag` tool top-level kwargs 传入 `RAGService`；`routing_metadata` 只能记录 `compiled_learning_truth_available` 这类 compact marker，不得承载完整 projection，不得在 wrapper 内合成、拉取或改写 learner truth。
24. ChatCapability 只能归一化 mode / config 并委托 `AgenticChatPipeline`；fast mode 的工具裁剪也必须留在 agentic pipeline 内执行。不得在 capability wrapper 内另起一条直接 LLM / 直接 tool 终端路径，否则会绕开统一 RAG fallback、sources/result 组装和 trace authority。
24a. `AgenticChatPipeline` 在解析 end-user enabled tools 时必须复用统一 end-user tool exposure policy，普通聊天 / RAG 链路不得暴露 `code_execution`、`exec` 或其兼容 alias。Native tool-calling 与 ReAct fallback 的执行边界还必须按同一 enabled set 拒绝 provider 未广告工具调用；未广告调用不得进入 registry execution，也不得把拒绝补丁下沉到 RAG provider 或 prompt。该过滤只收紧用户侧工具面，不新增 RAG provider、执行身份或第二套 route authority；内部受信评测/开发代码执行必须走独立控制面。
25. graph-aware retrieval 只能作为 compiled truth materialization 的只读上下文，允许表达 `question -> concept -> rubric_item -> error_code -> training_signal -> next_question` 这类 typed edges；它不是第二套 graph DB、第二套 RAG provider，也不得绕过 source-aware ranking。
26. retrieval maintenance workflow 必须是离线 dry-run / job 形态，输出 retrieval miss、citation、stale weak point、rubric coverage、eval case 报告；不得写 Supabase learner-state，也不得进入在线 `/api/v1/ws` 低延迟链路。
27. 当 `compiled_learning_truth` final-source enablement 被显式开启且 intent 属于弱点复习 / 下一题训练时，最终 sources 必须至少保留一条已 materialize 的 compiled truth 证据；该证据只能追加在 exact-question、标准、教材等 authority 后面，不得抢占更高权威来源。
28. Langfuse / ClickHouse 的 canonical `rag.supabase.search` retriever observation 必须能查询到 compact `retrieval_plan` 与 `ranking_trace`。一次 `SupabasePipeline.search()` 只能产生一条 canonical `rag.supabase.search` retriever observation；不得新增同名 sidecar 来承载 trace，否则会污染 RAG 使用次数和 evidence gate。若 observability backend 只支持 string metadata，必须把 `retrieval_plan_json`、`retrieval_plan_intent`、`ranking_trace_json`、`ranking_trace_fusion` 写在这条主 observation 上。
29. `stage_timings_ms` 与 `performance_policy` 只能作为 `evidence_bundle` / metadata 中的 compact retrieval telemetry，用来解释弱点复习 / 下一题训练 fast path 是否跳过 rerank 或 second pass；不得成为新的路由 authority，也不得覆盖 `retrieval_plan` 的 intent / source group 语义。
30. TutorBot `rag` tool 可以在 `weak_point_review` / `next_training` 且 compiled truth final-source 明确启用时返回 learning fact capsule，但 capsule 只是对 `evidence_bundle.sources` 和 compiled truth source 的用户可读摘要；不得从 wrapper 内生成新的学习事实、修改 learner-state、或绕过 `RAGService` / `SupabasePipeline` 的 evidence bundle。
31. `deep_question` 在 `deep` / `smart` 批改讲评中可以先用统一 `rag` 入口检索题库/规范依据，再交给 `SubmissionGraderAgent` 组织教学反馈；RAG 只提供解释依据，不得覆盖 `active_object / questions_bank / construction_grading_result` 已确定的标准答案、分数或正确性。
32. exact-question fast path 必须要求强题目锚点：完整题干/选项、当前 active question、明确题目讲评请求且命中高置信题库来源，或正在批改当前题。低信息考试查询（例如"2025真题"、"历年真题"、"防水真题"、"2025真题有哪些"）只能作为目录/检索/澄清输入，不得由 `prepare_exact_question_probe` 生成 exact candidate，也不得让 TutorBot exact-first path 输出标准答案。若上游 metadata 带 `exact_question_blocked_reason`，RAG / TutorBot fast path 必须 fail closed 跳过 exact authority，并把该 reason 保留到 trace。
32a. exact-question 解析完整 MCQ 且用户当前题面选项顺序或单位表述不同于题库时，当前 query option surface 是本轮公开答案字母 authority。`HistoricalQuestionResolver` 可以在同一题干高置信命中后用稳定 value alias（例如 `25` ↔ `25年`）把题库标准答案 remap 到当前题面；不得继续展示题库旧字母，也不得让普通 RAG/LLM 重写 remap 结果。
32b. "学员本轮粘贴的题是否=题库某道原题"是 **identity 判断而非 relevance 判断**。`question_exact_text`（direct-ILIKE / 全文 RPC）、`question_exact_vector` 与 option-overlap 促升路径只负责供给候选；候选必须通过单一可证伪 identity adjudicator `exact_question_identity_corresponds` 才能铸成 `question_exact_*` / `question_bank_option_match` authority。判据（归一化后：NFKC 全半角折叠 + 去空白/标点）：题库题干 ⊆ 学员文本 或 学员文本 ⊆ 题库题干（被包含侧须携带足够判别面，≥12 归一化字符），辅以字符级有序覆盖率 ≥ 0.90 的宽容补充（吸收 1-2 处错别字 / OCR 噪声 / 换行漂移；覆盖率路径的判别面须 ≥20 归一化字符——12-19 字符的短模板题干可因单个承载字差异（一级/二级、7天/14天）仍过 0.90,那是不同题;短判别面只能靠逐字包含或选项佐证裁决）。MCQ 的 identity 判别面 = 题干+选项:option-overlap 促升路径把题库选项值作为佐证面传入同一 adjudicator（题干短且带笔误但选项近逐字一致=同一道题）,不新增第二 decider;合并判别面之外题干必须被独立覆盖 ≥0.90——仅粘选项不粘题干不得裁 identity。模糊覆盖路径还须满足数词事实全覆盖:题库题干中每个 数词+单位 token（一级/7天/5000m3…）必须逐字出现在学员文本中,缺任一即拒——字符级容差分不清"错别字"和"变题",数词变题铸出的假标准答案是最恶性的假权威形态。已知残留:非数词类单字变题（做法正确↔错误）字符容差仍不可判,交部署里程碑 live 标定+题库变题家族抽样对抗。bigram 覆盖率、全文 text_score、向量相似度、选项 overlap 等 relevance 信号只能作 cheap pre-filter，**无单独放行权**；禁止对模糊命中人为抬置信（历史上的 `score=max(text_score, 0.98)` floor 已废除——exact 行必须携带真实 text_score / similarity）。adjudicator 不确认 identity 时，该候选必须降级为普通 `questions_bank` 检索行（携带真实分数）、不得进入 exact payload，本轮 fail-open 回主 LLM / 普通 RAG 讲解。仅共享单个高频域词（如"混凝土"）或同域措辞模板的命中不算精确命中——禁止据此输出"命中题库原题 / 标准答案"。计算题、挣值题、造价/工程量/工期等 numeric-heavy 题即使存成 `single_choice`，也必须额外通过正交计算同题不变量：题库题干中的关键数值、兼容单位、数值角色和求解目标必须被当前题面覆盖；同公式不同数字、同数字不同目标、同数字但计划/实际等角色互换只能作为普通 RAG 证据，不得晋升 `exact_question`。`case_study` 命中走 `case_bundle` 覆盖判定（2026-07-12 裁决：case 家族 identity 收权推迟，重评触发条件=case 型假命中 live 证据或案例家族战役开工）；案例中的计算小问若要晋升可见标准答案，也必须满足当前题面/背景的同题身份约束。真原题粘贴（含口语前后缀、带/不带选项、1-2 处笔误、换行差异）必须仍能命中——identity 收权不得过杀真原题。
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
41. `general_knowledge_context` 是 TutorBot / Chat agent runtime 的只读 compiled teaching overlay，只能显式 opt-in 或受控 cohort 启用；执行壳必须复用 `deeptutor.services.compiled_knowledge.general_knowledge` 生成 pack/grounding，不得新建第二套 RAG、KB registry、taxonomy、learner memory 或 context schema。该 overlay 只能作为 LLM 教学上下文和 compact result metadata，不得写 canonical learner truth、不得成为 official grading key、不得覆盖 `RAGService` citations / exact-question / 标准条文 authority；低置信、域外或 active question 场景必须 fail-open 回原 RAG / grading 链路。
42. `lecture_answer_method_context` / `luban_lecture_answer_method_context` 是 TutorBot runtime 的只读讲义答题方法 overlay，默认可对一建建筑实务高命中考试问答启用；执行壳必须复用 `deeptutor.services.compiled_knowledge.lecture_answer_methods` 从 tracked all8 `runtime_supply` manifest 生成 pack/grounding，不得扫散乱 artifacts、不得新建第二套 RAG/KB/taxonomy/learner-memory authority。该 overlay 只能提供采分关键词、陷阱/红线、口诀、公式/适用条件和 source-bounded 联想；不得成为 official answer key、不得给标准分、不得写 canonical learner truth；域外、低置信或 active question / exact-question / grading 场景必须 fail-open 回原 authority。
43. `SupabasePipeline` 的延迟杠杆（Battle2 S1-C）只允许在保持 §4 语义契约不变的前提下裁剪耗时，不得改变检索真相或成为新的路由 authority：(a) `search_unified` 超时预算按实测成功 p95 校准（默认 6.0s，registry 可配），超时必须走既有 typed `RAGSearchError` fail-closed 语义，不得静默空成功；(b) 批量 embedding 与 q0 检索的双 RPC 允许合并为单次 fanout，但逐字段输出必须与拆分路径一致（oracle 一致性门保证）；(c) `rerank` document cap 默认 0（关闭 doc 级 rerank），开启时只做 bounded 截断，不得改变 exact-question / 标准 / 教材的 authority order；(d) source 可用性探测（availability probe）走 SWR memo 出热路径，stale 值只用于避让不可用 source group，绝不据此把项目级不可用（§16 的 402/quota）降级成普通 warning。以上杠杆全部 fail-open / fail-closed 语义保持不变，仅减少每轮检索的时钟耗时。
44. `retrieval_profile` 是**检索深度声明**（L1 瘦身检索，2026-08-01），不是第二条检索入口、不是路由 authority、不是 TutorBot mode：调用方声明「这一轮我消费什么」，统一 pipeline 在**同一条管线内**按 profile 短路，不得为某个 profile 分叉出平行检索函数。命名单一权威 = `deeptutor/services/rag/retrieval_profiles.py`。
    - 缺省（空）= 全量管线，逐字节旧行为。模型自发的 in-loop `rag` 调用永远不带该键。
    - `case_grading_identity`：案例判分直通轮的身份检索。**只允许裁剪产物加工**——全文水合（`_hydrate_sources`）、`_rerank_results`、`_enforce_doc_diversity`、`build_ranking_trace` 的候选面、`content` 拼装、`source_items` 构造、以及 `questions_bank` 以外的 source 检索（textbook/standard/exam 及其派生的 `standard_code_exact` / `standard_precision`）。
    - **不得裁剪身份与分母命脉**：exact 文本探针批（`_search_exact_question_text_batch`）、`questions_bank` 向量检索及由其客户端派生的 `question_exact_vector`、`case_like` 强制 second pass（`covered_subquestions` / `covered_indexes` 的主要来源 = 判分分母，砍它即 P0 兜底满分病复发）、以及 `_extract_exact_question_payload` / `_augment_case_exact_question_with_query` / `_project_mcq_exact_question_to_query_surface` 三件套。同一道题在 lean 与 full 下的 `exact_question` 必须逐字段相同。
    - **空 `content`/`sources` 是该 profile 的正常终态，不是降级**：`retrieval_degraded` / `retrieval_status` 仍只由 `retrieval_warnings` 判定；任何消费方不得因为 sources 为空把该轮标成降级（会点亮降级闸把正常判分回答降成「证据不足」）。
    - 该 profile 的轮次不进 `rag_saturation` 台账（空 sources 会让 `_source_overlap` 恒 `None`，播种它反而毒化下一轮的比较基线）；fell-through 轮的饱和判据回到「首个 in-loop 轮 = round 1」。
    - 观测：`evidence_bundle.performance_policy.retrieval_profile` + 结果顶层 `retrieval_profile`；TutorBot 侧逐轮导出 `case_direct_rag_profile ∈ {lean, full}`。kill switch `LUBAN_CASE_DIRECT_LEAN_RAG`（默认 ON，off 回全量）。
    - `unanchored_exam_query`（2026-08-11，低信息真题查询锁权轮的题面供给收口，live 防冒充钉 3/3 红实证）：本轮 `exact_question_blocked_reason=low_information_exam_query`（学员指代的题无法锚定，exact 题目权威被 lifecycle gate 拒绝武装）时，**题目面材料不得进入模型上下文**。pipeline 整轮不武装两条题目面通道——`questions_bank` 检索族（`search_questions_bank=False` 连锁熄灭 exact 文本探针、bank 向量、`question_exact_vector` 派生、`case_like` second pass 与 `exact_question` payload）与 exam 卷面 chunk（`search_exam_chunks=False`）；textbook/standard 通道**照常**（模型仍有讲解依据，这是供给收权不是拒答降级），降级判据不变（`retrieval_warnings` 单一权威，empty-index 语义照旧）。声明点唯一 = TutorBot `RAGAdapterTool.execute`（prefetch / in-loop / exact-fast-path 三通路共用的供给边界，经 `_set_tool_context` 读锁权 metadata；调用方已显式声明其他 profile 时不覆盖）；调用点与 sink 不得再各自遮蔽/改写题库文本充当第二权威（sink 面 redact 已被 live 证伪：prefetch 先行注入，in-loop sink 永不通电）。域测试：`tests/services/rag/test_unanchored_exam_query_profile.py`（管线）、`tests/tutorbot/test_low_information_bank_disarm.py`（声明点 + loop 注入面）。

45. **`case_group_id` 是案例题「题级归属」的唯一权威键，且是不可变 id**（方案 C / C2，2026-08-01 回填上线）。`public.questions_bank` 的四列 `case_group_id` / `case_subquestion_index` / `case_row_granularity` / `case_row_canonical` 构成该 authority，硬约束如下：

    - **(a) id 合同（不可变 + 只追加）**：`case_group_id = {exam_year}-case{N}`。**一经写入即不可变**；同年新增题级组只能取该年当前 `max(N)+1`，**绝不重排既有 N**，即使发现漏题、发现 N 的页序推导有误也不重排（要纠正就新开一个组 id 并把旧组标废，不原地改号）。理由：`{year}-case{N}` 的 N 派生自年内页序排序，一次重排会让所有已消费该 id 的 trace、错题本、评分记录、eval 金标同时指错题——**排序派生的可读 id 只有在冻结后才能当 authority**。`case_group_id` 的年份前缀必须恒等于该行 `exam_year`，一个组不得跨年。
    - **(b) 行粒度分叉**：`case_row_granularity ∈ {subquestion, whole_question}`。`whole_question` 行本身已含该案例全部小问，`case_subquestion_index` 必须为 NULL，消费方命中它时**不得再发兄弟行查询**；`subquestion` 行才走按组取全。粒度是数据事实，不是启发式——不得用题干长度、序号个数在运行时重判。
    - **(c) `case_row_canonical` 三态，NULL ≠ false**：同一 `(case_group_id, case_subquestion_index)` 存在多个入库世代时，`true` = 收权行，`false` = 同格被收权的重复行，**`NULL` = 尚未裁决**（同格答案文本冲突，等人审）。消费方**不得把 NULL 当 false 过滤掉**——那会让存在答案冲突的小问在 bundle 里整个消失，把「有争议」静默变成「没这一问」。正确姿势：`canonical is not false`，并对 NULL 格标记 `case_answer_conflict_unresolved` 进 trace，宁可少给标准答案也不得假装该小问不存在。
    - **(d) 只增不改既有列**：题级归属回填只写这四列，不得借机改写 `stem` / `correct_answer` / `question_type` / `source_chunk_id`。`question_type='case_study'` 今天仍混装真题案例行与教材/讲义自动生成的单问考核题（2026-08-01 实测 1959 行里 1574 行属后者），**`case_group_id IS NULL` 不代表「不是案例」**，只代表题级归属未建；消费方遇 NULL 必须 fail-open 回单行 bundle 并写 `case_bundle_hydration="skipped:null_group_key"`，不得据此反推 `question_type`。
    - **(e) 组边界的可证伪性**：`case_group_id` 的组边界来自背景正文指纹合并，**它是可错的**，因此不得单独充当 identity 裁决。案例行晋升可见官方答案仍须走 §32b 的 `exact_question_identity_corresponds`；`case_group_id` 只负责「取全同组」，不负责「这是不是学员这道题」。
    - 回填执行与证据：`docs/原始数据/数据盘点/2026-08-01-方案C-C2回填执行.md`；DDL：`supabase/migrations/20260801000100_questions_bank_case_group.sql`。

46. **治理组 bundle 的参考答案必须以 per-问结构进判分核，且每小问独立封顶**（OD-005，2026-08-01 live 实证：整卷 4 问粘贴 + 只答问 1，在 C3 全覆盖参考下三轮两轮 10/10）。

    - **(a) 不得拼接后自由抽取**：`case_bundle_source=group_query` 的 bundle，其 items 自带 `display_index` + `authoritative_answer`。判分 ctx 必须导出 `case_reference_subquestions=[{index, answer}, ...]`（单一产出点 = `AgentLoop._current_case_reference_from_context` 的同一次采纳循环；旧的 `correct_answer` 拼接串保留作非治理路径与向后兼容面，两者同源）。把 N 问答案 `"\n".join` 成一段再做**一次**开放世界抽取，点位分布不受任何约束——抽出的点恰好集中在学生已答的那一问时，命中即满分，而参考全覆盖 ⇒ `scope_ratio=1` ⇒ 整题范围封顶根本不介入。这是**正确性缺陷**，不是效率问题。
    - **(b) 每问独立抽取**：每问的 `extract_rubric_from_reference_async` 只喂该问的 `authoritative_answer`，题面只喂该问（`case_subquestion_stem`，切不出时 fail-open 回整题题面）。点的 `question_no` 由**结构化事实**（答案来自哪一问）确定性盖章，不采信 LLM 自报。多次抽取各自产出 `P1..Pn`，`point_id` 必须加问号前缀 —— 不加则跨问撞键，verdicts 按 point_id 索引会静默错绑判分。
    - **(c) 每问独立封顶**：每问名义满分 = 整题名义满分 ÷ 题面小问数（`questions_bank` 行不带 per-问分值，均分是当前唯一确定性依据）；每问得分 = `min(Σ该问命中, 该问名义满分)`，总分 = Σ 各问 capped，对外分母恒为整题名义满分。**写分者仍只有 `rubric_grader_v1.finalize_case_score` 一个**（codex 不变量审计 §2.1）——逐问封顶作为它的入参 `subquestion_caps`，与整题范围封顶串联，调用方不得自行改分。
    - **(d) 未答的小问自然得零**：没答的问其点位全 miss ⇒ 该问 0 分。**不得**引入「哪几问已答」的第二判定权威（切学生作答、数编号、LLM 判定）——点位分布本身就是判定，多一张名单就多一处会漂的权威。
    - **(e) 抽取失败 = 该问未覆盖，不是零分连坐**：某问抽取失败/空时，该问不进封顶表也不贡献点位，等价于「参考没覆盖这一问」，分母仍是整题名义满分（学生看到诚实的部分覆盖），不得把整轮判分打成 0 或降级拒答。
    - **(f) 非治理路径不变**：`case_reference_subquestions` 少于 2 问（单行兄弟行 / 库外 tier-3 / 学生自带参考）一律回落既有整段抽取 + `scope_ratio` 整题封顶路径，逐字节旧行为。
    - 观测：`case_per_subq_grading`（"有点位的小问数/题面小问数"，空 = 走了旧整段链）、`case_subq_score_caps`（`q1:2.5,...`）、`case_subq_score_capped` / `case_subq_capped_from`（封顶真的咬到时）；判决面 `adjudication_strategy=dynamic_parallel_subquestion_groups`（一组 = 一问，逐组发射即「问 k 判完」）。kill switch `LUBAN_CASE_PER_SUBQ_GRADING`（默认 ON，off 逐字回旧形状）。

47. **`questions_bank.retired_at` 是题库行生命周期的唯一判据，软删行不可达任何生产读者**（task#31 供给层软删，2026-08-02）。

    - **(a) 单一谓词权威**：应用侧过滤谓词（`retired_at=is.null`）只定义在 `deeptutor/services/questions_bank_liveness.py`；PostgREST 直读 questions_bank 的查询构造必须经 `apply_live_row_filter`（RAG 侧汇聚点 = `SupabasePipeline._select` 按表名注入；组卷侧 = `blueprint_service._query` / `question_bank_size`）。**调用点不得各自手写 WHERE**——那是第 N+1 个 decider。
    - **(b) RPC 通道在 DB 函数体内收权**：`search_questions_bank_text` / `search_questions_bank_vector` 等 RPC 的返回列由函数签名固定、应用侧改不了，谓词落在 `supabase/migrations/20260802000200_questions_bank_reader_soft_delete_filter.sql`（8 函数 + 1 视图穷举，清单常量 = `SOFT_DELETE_FILTERED_DB_READERS`，静态测试逐一核对，漏一个即红）。
    - **(c) 生产读者没有读退役行的权利**：对生命周期列写其他谓词（如 `not.is.null`）必须抛错不静默；治理/审计工具要读全量就不走 `apply_live_row_filter`。这条 fail-closed **与灰度旗标无关，OFF 期间同样生效**——"开关没开"不得变成绕过收权的后门。
    - **(c2) 灰度旗标 `LUBAN_QUESTIONS_BANK_SOFT_DELETE_FILTER`（默认 OFF）解耦部署序**：OFF = 不注入谓词、逐字节现行为，因为本轮无 writer（`retired_at` 全表恒 NULL，过滤与不过滤同结果集）——这是**立法不是疏忽**，让代码可以先于 DDL 安全上线（谓词打在尚未存在的列上 PostgREST 整条返 400 = 题库检索全断）。翻 ON 的正确窗口 = migration Part A 执行之后、首个退役批写入之前。上线四步各自独立可回滚，见 APPROVAL_SHEET。
    - **(d) retire 是状态翻转不是删除**：下游快照（assessment_forms / 会话 / 错题本）与 `user_logs` FK 继续可解析；回滚 = 按 `retired_batch` 一条 UPDATE。破坏性 DELETE 仍受删行三查协议约束。
    - **(e) 退役写操作走 manifest 授权**（canonical431 pointer 模式）：批量 retire 必须有 `production_authorized=true` 的 retirement manifest（完整性链与治理链分离），执行器未见授权必须拒跑并发声。
    - 设计与测绘：`docs/原始数据/数据盘点/2026-08-02-questions_bank软删版本化读者测绘与设计.md`；域测试：`tests/services/rag/test_questions_bank_soft_delete_filter.py`。

## 当前统一语义

- `exact_question`
- `exact_question.answer_kind`
- `exact_question.case_bundle`
- `exact_question.coverage_state`
- `exact_question.question_id`（tier1/2 可达性 2026-07-30：payload 顶层显式身份键；
  连同 `source_chunk_id`/`exam_year` 构成 pgo 复合 qid
  `{exam_year}::{source_chunk_id}::E{n}` 的原料——消费方是判分 ctx 组装，
  不得作为路由/relevance 信号）

32c. case 粘贴的 exact 可达性两不变量（1b 2026-07-30，live 实证在库案例恒 miss 的两处根因）：
  ① `classify_query_shape` 中结构性 case 证据（`_looks_like_case_study`：≥80字+背景资料+问题N）
  必须先于弱 MCQ 题干启发（`_MCQ_STEM_RE` 的「不得/应当/可以/不属于」法规语言）裁决——
  案例题干几乎必含这些词；真 MCQ 仍由选项形状与强关键词优先拿走。
  ② exact text-first 探测任务不得被 `exact_probe.query ≤ max_text_len`（MCQ 时代校准的短查询门）
  整体闷死：case 短查询（`case_exact_queries` 小问切片）在场即须放行 text-first 批次，
  长 probe query 交给 `build_exact_question_text_candidates` 的 case_like 切片。
  两处都只放宽**候选供给**；采信权威仍是单一 identity adjudicator
  `exact_question_identity_corresponds`（32b），不新增放行权。
  另：pipeline 未命中时 trace 元数据的 `exact_question: {}` 空壳不得被下游写成
  `_prefetched_exact_question` 冒充命中（非空才写；TutorBot 直批 marker 须落
  `allowed_no_exact_hit`）。直批身份检索只喂题干（作答文本不参与「这是哪道题」的裁决）。
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
- `retrieval_profile`
- `evidence_bundle.performance_policy.retrieval_profile`
- `case_direct_rag_profile`
- `case_reference_subquestions`
- `case_per_subq_grading`
- `case_subq_score_caps`
- `learning_fact_capsule`
- `routing_metadata.personalization_context_available`
- `PersonalizationContextPack`
- `question_grading_explanation`
- `exact_question_blocked_reason`
- `general_knowledge_context`
- `luban_general_knowledge_context`
- `lecture_answer_method_context`
- `luban_lecture_answer_method_context`
- `evidence_bundle.sources[].source_id`
- `evidence_bundle.sources[].source_span`
- `evidence_bundle.sources[].content_hash`
- `evidence_bundle.sources[].quote_hash`
- `content_delta`
- `citation_final_delta`

## 必测项

- `tests/services/rag/test_rag_pipelines.py`
- `tests/services/rag/test_kbv5_pipeline.py`
- `tests/services/db/test_connection_factory.py`
- `tests/scripts/test_db_registry.py`
- `tests/services/rag/test_supabase_strategy.py`
- `tests/agents/chat/test_agentic_parallel_tools.py`
- `tests/services/citations/test_normalizer.py`
- `tests/services/rag/test_questions_bank_soft_delete_filter.py`
