# 鲁班智考 RAG 体系评估报告

## 总分：78/100

本报告基于对 `deeptutor/services/rag/`、`deeptutor/services/embedding/`、`deeptutor/agents/chat/`、`deeptutor/services/taxonomy/`、`deeptutor/services/rag/pipelines/supabase_strategy.py` 等核心模块的深度代码审查，评估鲁班智考项目 RAG（检索增强生成）体系的工程质量与技术成熟度。

---

## 各维度评分

| 维度 | 得分 | 满分 |
|---|---|---|
| 文档处理与分块 | 10 | 15 |
| Embedding 与向量存储 | 12 | 15 |
| 检索策略 | 18 | 20 |
| 上下文组装与 Prompt 工程 | 12 | 15 |
| 查询理解与改写 | 9 | 10 |
| 评估与监控 | 8 | 10 |
| GStack 最佳实践应用 | 9 | 15 |
| **合计** | **78** | **100** |

---

## 详细分析

### 1. 文档处理与分块（10/15）

**架构概述**

项目拥有两层分块体系：一层是 LlamaIndex Pipeline 使用的内建 `SentenceSplitter`（通过 `Settings.chunk_size = 512, Settings.chunk_overlap = 50`），另一层是自研的可组合 `RAGPipeline`（`deeptutor/services/rag/pipeline.py`）配合独立 Chunker 组件。

**优点**

- **文件类型路由**：`FileTypeRouter.classify_files()` 将文件自动分为 parser_files（PDF 等复杂格式）、text_files（快速路径直接读取）、unsupported，分类处理合理。路径见 `deeptutor/services/rag/components/routing.py`。
- **PDF 提取**：使用 PyMuPDF（fitz）逐页提取文本，这是 PDF 处理中较可靠的方案（见 `LlamaIndexPipeline._extract_pdf_text()`）。
- **可组合管道**：`RAGPipeline` 提供了 fluent API（`.parser().chunker().embedder().indexer().retriever()`），为未来扩展不同分块策略留出了空间。
- **自研 SemanticChunker 和 FixedSizeChunker** 已经编写完毕，支持可配置的 `chunk_size`、`chunk_overlap` 和分隔符优先级。

**不足**

- **LlamaIndex 管道实际使用的分块参数偏小**：`chunk_size=512, chunk_overlap=50`。对于建筑规范文档（结构化条文、带编号的标准条款），512 字符往往会将一条完整规范条文拆成两个 chunk，导致语义断裂。overlap=50 也偏低（仅约 10%），业界推荐 15-25%。
- **自研 Chunker 组件未在主管道中实际使用**：`SemanticChunker`（默认 chunk_size=1000, overlap=200）和 `FixedSizeChunker` 只在可组合管道中注册，但 `LlamaIndexPipeline`（实际生产管道）直接用 LlamaIndex 内建的 `SentenceSplitter`，两套体系未统一。
- **缺少针对建筑领域的自适应分块**：建筑规范文档有清晰的"条-款-项"层级结构（如 GB50300 的章节编号），没有利用这种结构进行有意义的语义分块。
- **缺少表格/图片处理**：PDF 中的表格（如混凝土强度等级表、钢筋规格表）提取后变成纯文本，结构信息丢失。

---

### 2. Embedding 与向量存储（12/15）

**架构概述**

Embedding 采用统一客户端 `EmbeddingClient`（`deeptutor/services/embedding/client.py`），通过适配器模式支持 OpenAI Compatible / Cohere / Jina / Ollama 四种 binding。向量存储有两条路径：LlamaIndex 的 `VectorStoreIndex`（本地 JSON 持久化）和 Supabase 的 pgvector（远程 PostgREST RPC）。

**优点**

- **多 Provider 适配器**：`OpenAICompatibleEmbeddingAdapter` 覆盖 OpenAI / Azure / DashScope / vLLM 等多种兼容 API，切换成本低。配置从 `resolve_embedding_runtime_config()` 统一解析，支持环境变量和 catalog 配置双通道。
- **Embedding 向量验证**：`validate_embedding_batch()` 在 embedding 返回后、存储前、加载后三个时点做校验，防止空向量或维度不匹配的问题污染索引（见 `deeptutor/services/embedding/validation.py`）。
- **Embedding 签名与索引版本管理**：`EmbeddingSignature` 将 binding + model + dimension + base_url + api_version 组合为签名，`index_versioning.py` 实现了 `resolve_storage_dir_for_read/write/rebuild`，在切换 embedding 模型时能自动识别版本不匹配并警告。
- **Embedding 缓存**：Supabase Pipeline 实现了基于 SHA256 的内存 LRU 缓存（`_EMBEDDING_CACHE`），TTL 可配（默认 600s），避免相同 query 重复调用 embedding API。
- **批量处理**：支持 `batch_size`（默认 10）和 `batch_delay` 配置，有 progress_callback 回调机制。

**不足**

- **LlamaIndex 本地管道使用 JSON 持久化**：`VectorStoreIndex` 默认将向量存为 JSON 文件（`*vector_store.json`），这对于大规模知识库效率很低。虽然也有 FAISS 索引器（`VectorIndexer`），但它只在自研的可组合管道中使用。
- **Supabase pgvector 是只读的**：`SupabasePipeline` 的 `initialize()` / `add_documents()` 直接 raise RuntimeError，说明向量数据由外部流程写入 Supabase，本系统无法自主管理索引的创建和更新。
- **Embedding 模型不匹配检测是被动的**：虽然在搜索时能检测并警告 mismatch，但没有在启动时主动校验或自动触发重建。

---

### 3. 检索策略（18/20）

**架构概述**

这是整个 RAG 体系中最成熟、最精心设计的部分。Supabase Pipeline（`supabase.py`，2831 行）实现了一套完整的多路召回 + 融合排序 + Rerank 的检索架构。

**优点**

- **多路召回（Multi-Source Retrieval）**：`_run_query_plan()` 并行查询多个来源组（`textbook`、`standard`、`exam`、`questions_bank`、`standard_code_exact`、`standard_precision`、`question_exact_text`、`question_exact_vector`、`compiled_learning_truth`），每个组独立检索后融合。
- **智能来源选择（Source Selection）**：`select_sources()` 根据 query_shape（concept_like / mcq_like / case_like / standard_like / calc_like）、intent、question_type 动态裁剪检索源，避免噪声。例如纯概念查询会 prune 掉题库和考试源。
- **Weighted RRF 融合**：`_weighted_rrf_fusion()` 用加权倒数排名融合（k=60）将多路结果合并，权重由 `resolve_group_weights()` 根据 query_shape 动态调整。standard_like 查询给 standard 加权至 1.8，mcq_like 给 questions_bank 加权至 1.8。
- **精确题目匹配（Exact Question Authority）**：支持文本精确匹配和向量精确匹配两条路径，能识别用户输入的完整考题并返回题库原题的标准答案、解析、选项分析。这对考试辅导场景是核心能力。
- **DashScope Rerank**：集成 gte-rerank 模型做二次排序（`rerank_documents()`），带 Langfuse 观测和 timeout 控制。
- **相似度地板机制**：`_apply_similarity_floor()` 对高相似度（≥0.72）的结果做 boost，对超高相似度（≥0.82）的结果做 hard guarantee 插入 top-k 窗口，防止高质量结果被融合排序淹没。
- **二次检索（Second Pass）**：`should_run_second_pass()` 在首轮结果不足或重复率过高时触发二次检索，使用 `build_second_pass_queries()` 生成补充查询。对比类查询和案例题强制触发。
- **来源多样性约束**：`_enforce_doc_diversity()` 限制同一文档最多贡献 2 个结果。
- **Provenance Ranking**：`apply_provenance_ranking()` 在融合排序之上叠加来源权威度调整，exact_question > standard_code_exact > standard > questions_bank > textbook > exam 的优先级清晰。
- **案例题支持**：专门的 `_extract_case_subquestions()`、`_build_case_focus_query()` 从案例题背景材料中提取子问题，分别检索再聚合。

**不足**

- **缺少 BM25/稀疏检索**：当前只有向量（Dense）检索 + 文本精确匹配，没有 BM25 或其他稀疏检索通道。对于建筑规范中大量的编号（如 GB50300-2019 第 5.3.2 条）和精确术语，稀疏检索往往比向量检索更准确。虽然 `_search_exact_standard()` 和 `_search_precision_standard()` 部分弥补了这一点，但覆盖面有限。
- **LlamaIndex 管道检索策略简单**：`LlamaIndexPipeline.search()` 只是 `index.as_retriever(similarity_top_k=top_k)`，没有融合、rerank、来源选择等高级能力。两条管道的能力差距很大。

---

### 4. 上下文组装与 Prompt 工程（12/15）

**架构概述**

项目采用多阶段 agentic pipeline（Thinking → Acting → Observing → Responding），RAG 结果作为工具调用结果注入 Acting 阶段，由 Observing 阶段整理后供 Responding 阶段使用。

**优点**

- **Teaching Metadata 投影**：`_project_teaching_metadata()` 将检索结果中的结构化教学元数据（记忆口诀、采分点、易错点、思维链、扣分红线、关键参数）自动拼接到 `rag_content` 中，显著丰富了上下文质量。
- **Evidence Bundle 构建**：每次检索都生成完整的 `evidence_bundle`，包含 query、provider、source_plan、retrieval_plan、ranking_trace、content_blocks、sources、exact_question 等全链路信息，为下游消费和审计提供了完整上下文。
- **精确题目权威回复**：`build_exact_authority_response()` 为命中的精确题目生成结构化的权威回复，包含阅卷结论、解析、易错点表格、核心要点、下一步建议，格式精心设计。
- **多阶段 System Prompt**：Thinking/Acting/Observing/Responding 四个阶段各有专门的 system prompt，职责分离清晰。Responding 阶段明确要求"自然融入工具结果中的证据"。
- **考试方向感知**：Responding prompt 能根据 `exam_track` 自动注入考试方向约束。

**不足**

- **上下文窗口管理不够精细**：没有看到显式的 token budget 管理。当多路召回返回大量结果时，拼接后的上下文可能超出模型窗口，但代码中没有按 token 预算截断的逻辑。
- **缺少显式的 citation/attribution 模板**：虽然 sources 信息传递完整，但在 Responding prompt 中没有明确要求模型在回答中标注来源出处（如引用规范编号），citation 需求留给了模型自由发挥。
- **RAG 结果与对话历史的融合方式较粗**：`retrieve_context()` 将 RAG 结果简单拼接为 `[Knowledge Base: {kb_name}]\n{rag_answer}`，没有按 source_type 分层或按 ranking 排序后截断。

---

### 5. 查询理解与改写（9/10）

**架构概述**

`supabase_strategy.py` 实现了一套深度定制的中文建筑考试领域查询理解体系，这是整个 RAG 系统中完成度最高的模块之一。

**优点**

- **Query Shape 分类**：`classify_query_shape()` 将查询分为 5 种形态（concept_like / mcq_like / case_like / standard_like / calc_like），使用正则和关键词匹配，覆盖了建筑考试的主要题型。
- **多层查询归一化**：`normalize_query()` 去除口语化填充词（"请问"、"帮我"等），`normalize_retrieval_query()` 去除 MCQ 选项噪声、考试前缀、来源标注等，提取纯净的检索查询。
- **查询扩展**：`expand_query_variants()` 支持最多 6 个变体，包括：标准规范编号变体（GB50300 → GB 50300 → GB50300-2019）、静态同义词扩展（防水等级 ↔ 一级防水/二级防水）、领域关键词提取、对比实体拆解（"A和B的区别" → 分别查 A 和 B）。
- **精确题目探测**：`prepare_exact_question_probe()` 能从混合输入中提取题干，剥离选项，生成适合精确匹配的查询。支持限定题型（只搜单选/多选/案例题）。
- **案例题子问题提取**：`extract_case_subquestion_items()` 能从"【背景资料】...【问题】1.XXX 2.YYY"格式中精确提取各子问题。
- **标准编号识别**：`extract_standard_codes()` 用正则从查询中提取 GB/JGJ/CJJ 等标准编号。

**不足**

- **未使用 LLM 做查询改写**：所有查询理解都基于规则和正则，没有用 LLM 做 query rewriting 或 HyDE（Hypothetical Document Embedding）。虽然 `smart_retrieve()` 中的 `_generate_queries()` 调用了 LLM 生成多查询，但这个路径似乎只在上层 `RAGService` 中可用，Supabase Pipeline 的主检索流程没有使用。对于口语化、模糊、错别字较多的用户查询，纯规则方案有局限。

---

### 6. 评估与监控（8/10）

**架构概述**

项目有相当成熟的 observability 和评估体系。

**优点**

- **Langfuse 全链路追踪**：embedding、retrieval、rerank 三个关键操作都封装在 `observability.start_observation()` 上下文中，记录 input/output/metadata/usage/cost，支持 trace 级别的 DEBUG 到 ERROR。PII 脱敏（手机、邮箱、API Key）内建。
- **Stage Timing**：Supabase Pipeline 的 `search()` 内部对每个阶段（availability_gate、primary_plan、exact_text_probe、primary_fusion、second_pass、rerank）都记录了毫秒级耗时。
- **RAG 专项测试**：`tests/services/rag/` 下有 4 个测试文件覆盖了 retrieval plan、RAG failure contract、learning fact retrieval pipeline、RAG pipelines 基础功能。
- **Eval Gates**：`eval/gates.yaml` 定义了 `rag_retrieval_contract` gate，包含 learning-fact retrieval、retrieval plan、RAG failure contract 三组测试。还有 `learning_fact_retrieval_maintenance` 做 dry-run 维护审计。
- **Maintenance Audit**：`maintenance.py` 实现了完整的检索质量审计，检查 citation gaps、stale weak points、rubric coverage gaps、retrieval misses。
- **Grounding Eval Cases**：`tests/fixtures/rag_grounding_eval_cases.json` 包含精确权威回复的 golden cases。

**不足**

- **缺少端到端 RAG 质量评估**：没有看到 Recall@K、MRR、NDCG 等标准 IR 指标的定量评估框架。现有测试偏合约验证（字段是否存在、类型是否正确），缺少"给定 query 是否检索到正确文档"的 ground truth 评估。
- **缺少用户反馈闭环**：没有看到将用户的 thumbs up/down 反馈与 RAG retrieval trace 关联的机制。

---

### 7. GStack 最佳实践应用（9/15）

**Grounding（基于事实的回答）— 7/10**

项目在 Grounding 方面做得较好：
- **Exact Question Authority**：精确题目命中后直接返回题库标准答案，是最强的 grounding 手段。`exact_authority.py` 有完整的 MCQ/案例题/自由文本三种 authority 处理。
- **Compiled Truth Source**：`compiled_truth_source.py` 将学员的学习事实（弱点、掌握程度）编译为可检索的文档，带有证据等级（L0_observed → L3_mastery_signal）和安全脱敏。
- **Provenance Tracking**：每个检索结果都带有 `_source_group`、`_provenance_features`，从源头到最终排序的全链路可追溯。
- **不足**：没有看到对 LLM 输出的事后 grounding check（即检查 LLM 回复是否与检索到的事实一致）。`exact_authority_response_matches()` 只检查 MCQ 答案字母是否匹配，对于开放式回答没有验证。

**Guardrails（防护栏）— 5/10**

- 项目有 `tutorbot_security_skill.py` 和 `test_tutorbot_guardrails.py`、`test_tutorbot_redteam_matrix.py`，说明对对话安全有投入。
- `compiled_truth_source.py` 中有 `_PROMPT_LIKE_RE` 和 `_PRIVATE_FIELD_RE` 做 prompt injection 防护和 PII 脱敏。
- **不足**：RAG 层面缺少 hallucination guardrail（当检索结果为空时是否拒绝回答或明确告知学生），也没有看到 content filtering 对检索到的内容做安全检查。

**Graph（知识图谱增强）— 4/10**

- `construction_learning_graph.py` 实现了一个小型的专家维护知识图谱种子（≤25 节点），包含 child_concepts 和 typed edges（easy_confuse、prerequisite）。
- `graph_projection.py` 和 `compiled_truth_source.py` 中有基于图谱边的遍历逻辑（`_graph_context_for_weak_point()`），能沿 question → rubric_item → error → training 链追踪。
- **不足**：图谱规模很小（Phase -1 状态），没有自动从文档构建知识图谱的能力。图谱主要服务于学习弱点追踪，没有直接用于 Graph-RAG（如利用图谱关系辅助检索扩展）。

**多路召回 — 9/10**

如"检索策略"部分所述，这是项目的强项。8+ 个检索通道，Weighted RRF 融合，动态权重调整，二次检索补充。

**评估和监控体系 — 7/10**

如"评估与监控"部分所述，Langfuse 集成完善，有专项测试和 eval gate，但缺少定量 IR 指标评估。

---

## 改进建议

按优先级排列：

### P0：高影响、低成本

1. **引入 BM25 稀疏检索通道**：在 Supabase 中利用 PostgreSQL 的 `tsvector` + `ts_rank` 做全文检索，与现有向量检索并行，在 `_run_query_plan()` 中作为新 source group 加入 RRF 融合。建筑规范的编号和专用术语场景下，BM25 检索效果通常优于纯向量检索。

2. **调大 LlamaIndex 管道的分块参数**：将 `chunk_size` 从 512 调至 800-1024，`chunk_overlap` 从 50 调至 150-200（约 15-20% 重叠率），更适合建筑规范文档的段落长度。

3. **增加显式 token budget 管理**：在上下文组装阶段加入 token 计数，按优先级（exact_question > standard > textbook > exam）截断，防止超出模型窗口。

### P1：高影响、中等成本

4. **建筑规范结构化分块**：开发识别"条-款-项"编号结构（如 `5.3.2`、`第 X.X.X 条`）的分块器，以完整条文为分块单位，保留层级元数据（章 → 节 → 条 → 款）。

5. **LLM 辅助 Query Rewriting**：对规则改写效果不佳的查询（如口语化、省略语、错别字），用 LLM 生成补充改写。可以实现为可选的 "query enrichment" 步骤，只在规则改写的 variant 数量不足时触发。

6. **添加端到端 RAG 评估框架**：构建一个 golden dataset（50-100 条），每条包含 query + 期望命中的 source_type + 期望命中的 chunk_id（或关键词），计算 Recall@5、MRR 等指标，接入 eval gate。

### P2：中等影响、较高成本

7. **Hallucination Detection Guardrail**：在 Responding 阶段之后添加一个轻量验证步骤，检查 LLM 回复中的关键数值/结论是否能在 retrieval context 中找到支撑。对于无法支撑的声明，标注置信度或触发 fallback。

8. **统一两条管道**：目前 LlamaIndex 管道（本地）和 Supabase 管道（远程）能力差距巨大。考虑将 Supabase 管道的高级检索策略（多路召回、RRF、rerank）抽象为可复用模块，让 LlamaIndex 管道也能受益。

9. **扩展知识图谱规模**：将当前 ≤25 节点的种子图谱扩展到覆盖完整考试大纲，利用图谱关系做检索扩展（如查询"混凝土养护"时，自动扩展到 prerequisite 节点"混凝土浇筑"的相关内容）。

10. **用户反馈闭环**：将用户对回答的评价（点赞/点踩）与 Langfuse trace 关联，定期分析低评价回答的 retrieval pattern，指导检索策略优化。

---

## 总结

鲁班智考的 RAG 体系在**检索策略**和**查询理解**两个维度达到了业界领先水平，尤其是 Supabase Pipeline 的多路召回 + Weighted RRF + 精确题目权威匹配 + DashScope Rerank 的组合，展现了对建筑考试辅导场景的深度理解。查询理解模块对中文建筑考试领域的适配（题型识别、标准编号提取、案例题子问题拆解）也非常精细。

主要短板集中在**底层基础设施**层面：分块粒度偏小且未针对建筑规范做结构化适配、缺少 BM25 稀疏检索通道、LlamaIndex 本地管道与 Supabase 远程管道能力差距大、知识图谱处于早期种子阶段。此外，在评估体系上虽有 Langfuse 追踪和合约测试，但缺少定量的端到端检索质量指标。

整体而言，这是一个**工程成熟度较高**的 RAG 系统，核心检索逻辑设计精良，在垂直领域的适配深度远超通用 RAG 框架。78 分的评分反映了"上层检索策略优秀但底层基础设施和评估闭环仍有提升空间"的现状。
