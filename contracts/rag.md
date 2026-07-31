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
