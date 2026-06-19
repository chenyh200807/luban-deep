# Pinecone Nexus 对鲁班智考适配性深度研究报告

> 研究日期：2026-05-31 ｜ 视角：技术合伙人 / 架构审计 ｜ 目标：判断 Nexus 能否真实提高鲁班一建建筑实务 AI 批改准确性、知识可解释性、学情诊断与产品壁垒
> 方法：先审计 luban-deep 仓库代码与 schema（基于证据，引用文件路径），再联网研究 Pinecone Nexus 公开资料（引用 URL，标注可信度与未验证项）。
> 事实/推断/建议已分别标注。涉及二建：本报告不涉及，鲁班当前只做一建建筑实务。

---

## 0. 执行摘要（10 条）

1. **不建议直接接入 Pinecone Nexus。** 它处于 Early Access（2026-05 发布），核心性能数字全部 vendor-reported、无第三方复现，且引入 vendor lock-in、数据出境、artifact 陈旧等真实风险。
2. **不建议自研"通用 Nexus-lite 层"。** 鲁班已在一建建筑实务领域内实现了 Nexus 的核心思想等价物（见 §1），再造一个通用知识编译层属于过度架构，违背项目 Thin-Wrappers / Simplicity 原则。
3. **建议：仅吸收 4 个具体思想，落到已有模块上，不新建大型子系统。**（采分点预编译覆盖率、eval 量化、artifact 版本化、批改结论 provenance 到规范条文。）
4. **最优路径 = 方案 C+（强化现有结构化批改 + eval），非方案 A（接入）、非方案 B（自研通用层）。**
5. **鲁班真正的瓶颈不是架构，是数据**：采分点标注覆盖率 + eval 标注样本规模。Nexus 是通用 agent 检索基础设施，**给不了一建建筑实务的领域评分知识**——它解决不了鲁班的核心瓶颈。
6. 最值得吸收的单一思想是 **Context Compiler**："把采分点提前编译为任务专用 artifact，而非每次临时 RAG"——而鲁班的 `grading_key` / `grading_rubric` authority 优先级**已经是这个思想**，缺的是覆盖率。
7. 最大风险：把"通用基础设施"误当成"领域能力捷径"，付出 lock-in + 跨境 + 早期不稳定的代价，却没提升批改准确率。
8. Nexus 的真正价值对鲁班是**外部验证**：连最早把 RAG 推向主流的 Pinecone 都在转向"artifact-first + 结构化输出 + provenance"，证明鲁班的方向正确。
9. 重新评估 Nexus 的条件：①GA 且有第三方 benchmark 复现；②明确中文 / 数据驻留支持；③出现鲁班无法自建的能力。
10. 第一优先级行动：用**已有的** `services/benchmark/` harness 跑一次"采分点 recall / 分差 / 幻觉率" baseline，把"短板"从推断变成量化事实，再决定投入。

**四层级回答（用户问题一）：**
- ① 是否直接接入？→ **否。**
- ② 是否等成熟再接入？→ **可在 GA + 第三方复现后重评，但即便那时，接入的前提仍是它能解决领域知识缺口——目前看不会。**
- ③ 是否只吸收思想自研？→ **吸收思想是；但"自研通用层"否——落到已有模块强化即可。**
- ④ 优先改造哪些模块？→ `construction_grading/`（采分点覆盖）+ `services/benchmark/`（eval 数据）+ `questions_bank` 的 rubric 版本化。

---

## 1. 当前鲁班智考代码现状（基于仓库证据）

**技术栈（事实）**：Python / FastAPI 后端 + Supabase Postgres + 自建 `EmbeddingClient`（`deeptutor/services/embedding/client.py:88`）+ 多路 RAG + Next.js（`web/`，BI + 小程序）。

**核心发现：鲁班已独立实现了 Nexus 宣传思想的领域专用版。**

| Nexus 思想 | 鲁班现状（文件证据） | 状态 |
|---|---|---|
| Knowledge Artifact / Scoring Point | `construction_grading/case_kernel.py:26` `grade()` | ✅ |
| **Context Compiler**（预编译知识，非临时 RAG） | `grade()` authority 优先级：`grading_key.scoring_points`(隐藏权威注入) > `grading_rubric`(questions_bank 策展) > projected_rubric > open_skill | ✅ 思想已落地，**覆盖率未知** |
| **Typed Answer**（结构化非 chunk） | `CaseGradingResult`；`rag/retrieval_plan.py:32` `RetrievalPlan` | ✅ |
| **Query Protocol / KnowQL 本土版** | `RetrievalPlan`：`query_shape / intent / authority_order / source_groups / expanded_queries` | ✅ |
| **Provenance / Citation** | `EvidenceRef(source, field, value)`、`grading_source` 写入 `next_training_signal` 供 trace 检测 drift（`case_kernel.py:132`） | ✅ |
| **Eval-driven layer** | `services/benchmark/`：`exam_quality_eval` / `quality_scoring` / `rag_replay` / `tutorbot_turn_replay` / `harness_hit_ledger` / `runner` / `registry` / `trend` / `promotion` | ✅ 框架完整 |
| **Versioned Knowledge** | `RetrievalPlan.schema_version`、`LearnerStateContract.version`（`contracts/learner_state.py:29`） | ◐ 部分（rubric/采分点本身未版本化） |
| 学情 / 错题 / 薄弱点 | migrations `20260415000100_learner_state_core.sql` / `20260521000100_learner_mistake_book_items.sql` / `learning_evidence`；`LearnerStateService` + `structured_writeback_pipeline` | ✅ |

**批改流程（事实，回答用户问题三-4）**：
- **多步骤、artifact-first**，非一次性 prompt：先取 evidence（`_question_evidence_refs` + `_external_evidence_refs`）→ 按 authority 选 rubric → 批改 → 写结构化结果。
- **先取结构化知识再批改**（grading_key/rubric），而非每次临时向量检索。
- **输出结构化** `CaseGradingResult`，写 `grading_source` 可追溯权威来源。
- **provenance 已有**：`EvidenceRef` 记录来自 questions_bank 哪个字段。
- 接入统一 turn：`construction_grading/deep_question_adapter.py:30`。
- 有单测：`tests/services/construction_grading/test_case_grading_kernel.py`、`test_audit_and_writeback.py`。

**审计出的真实短板（这些才该投入，与 Nexus 无关）**：
1. **pgvector / embedding 的 schema 不在版本控制的 migrations 里**：`grep "vector(" supabase/migrations/` **零匹配**；`kb_chunks` 仅 1 处引用。向量表在 Supabase 端直建（与项目记录一致），存在 schema 漂移 / 无版本追溯风险。**（事实）**
2. **采分点结构化覆盖率未知**：`scoring_point` 仅 1 migration，`grading_rubric` 作为 `questions_bank` 字段存在，但**覆盖多少题、质量如何，未发现规模化证据**。**（事实 + 这是批改准确率的真正瓶颈——推断）**
3. **eval 标注样本规模未知**：harness 框架齐全，但人工标注 case 数量未在 migrations 体现。**（未发现证据）**

---

## 2. Pinecone Nexus 是什么（技术解释，去营销化）

**事实（来源见 §3）**：Nexus 是 Pinecone 2026-05 发布的"面向 Agent 的知识引擎"，架在其向量数据库之上，由三部分构成：

- **Context Compiler**：把原始数据**预先编译**成 task-optimized knowledge artifacts（持久化），Agent 直接消费——把"推理"从检索时**前移**到编译时。
- **Composable Retriever**：低延迟服务这些 artifact，提供 **per-field citations** 与 **deterministic conflict resolution**（确定性冲突消解）。
- **KnowQL**：声明式查询语言，6 个 primitive——`intent / filter / provenance / output shape / confidence / budget`，一次调用返回**结构化 typed answer（而非 chunk）**并带来源与延迟预算。

**回答用户问题四的关键判断（推断）**：
- 它返回 **typed answer / structured output**，不是 chunk。
- 它本质是 **③ 知识编译层 +④ Agent 的知识接口协议**的结合（KnowQL = 接口协议），架在 ① 向量库之上；不是单纯"更高级的向量库"，也不止是"RAG 编排框架"。
- **它不是"替代 RAG"，而是把 RAG 演进为"预编译 + 声明式结构化查询"层**。VentureBeat 用了"RAG era is ending"，但这是 Pinecone 的营销叙事；技术实质是 RAG 的**编译型进化**，底层仍是检索。不应被"RAG is dead"带偏。
- 成熟度：**Early Access**，未 GA，无公开 SDK/CLI/GitHub 证据（见 §3）。

---

## 3. 官方宣传与真实可信度

| Claim | 来源 | 是否独立验证 | 评级 |
|---|---|---|---|
| Nexus 存在、三组件 + KnowQL 6 primitives | Pinecone 官方产品页/博客 | 官方一手 | **A**（产品事实成立） |
| task completion >90% | Pinecone KRAFTBench（自建） | 无第三方复现 | **B**（官方 benchmark，未独立验证） |
| 30x faster time-to-completion | Pinecone KRAFTBench | 无第三方复现 | **B** |
| up to 90% less token spend | Pinecone "early results" | 无第三方复现 | **B** |
| 98% token reduction（金融分析单案例） | Pinecone 单测试用例 | techjack 明确："self-reported vendor benchmark from a single test case…Do not use as planning input until third-party evaluation published" | **C**（单案例营销级） |
| KRAFTBench 客观中立 | Pinecone 自建并自评 | "Benchmark Comes From Pinecone"（媒体点名） | **B/C**（裁判即运动员） |
| 可生产、有 SDK/定价 | — | 多源："availability details not confirmed"；无 SDK/CLI/repo 公开证据 | **D/未发现证据** |

**结论（事实）**：所有性能数字均为 **vendor-reported、KRAFTBench 自建、零第三方复现**。多家媒体主动加 vendor-reported caveat。**这些数字不可作为鲁班的决策输入。**

---

## 4. 社区评价

- **正面/叙事**：VentureBeat《RAG era is ending…compilation-stage knowledge layer》、The New Stack《making RAG mainstream is now betting against it》——多为转述 Pinecone 论点。
- **质疑（重要）**：
  1. **benchmark 自报无复现**（techjack：third-party evaluation pending）。
  2. **artifact 陈旧性**：预编译反映"编译时"数据；对频繁变更的数据，刷新频率 / 增量成本"announcement materials don't address"。**——对鲁班直接相关：教材、规范、真题解析、评分标准会改版。**
  3. **KnowQL 标准化存疑**："standards do not get declared into existence by a single vendor"。
  4. **成本质疑**：Pinecone 2.0 较 1.0 涨价 ~300%（serverless read $0.04→$0.12 / 1M units），社区推荐 Chroma（Apache 2.0，无 lock-in）。
  5. **vendor lock-in**：专有模型 vs 开源替代。
- **实际生产采用**：**未发现独立的生产使用证据**（Early Access，发布约 1 个月）。
- **生态/GitHub 活跃度**：**未发现** `nexus-dev` 等公开 repo 的 star/release/issue 证据；无法证实开发者生态成熟。

社区主流：认为它是 **RAG 的演进而非死亡**，且对"单厂商 benchmark + 早期成熟度 + 涨价"普遍保留。

---

## 5. 与鲁班业务场景适配矩阵

| 鲁班场景 | 当前实现 | Nexus 能否提升 | 提升点 | 风险 | 建议 |
|---|---|---|---|---|---|
| 1 案例题批改 | `case_kernel.grade()` artifact+authority | 否（鲁班已是 artifact-first） | 无增量 | lock-in/陈旧 | **自研强化** |
| 2 采分点识别 | `grading_rubric`/`grading_key` | 否（领域知识，非通用检索） | 无 | — | **自建标注** |
| 3 标准答案拆解 | `_question_evidence_refs` | 否 | 无 | — | 自建 |
| 4 错因诊断 | case_kernel 错因类型 | 否（领域规则） | 无 | — | 自建 |
| 5 知识点图谱 | 部分（question 关联） | 部分（图能力） | 关系检索 | 过度复杂 | **自建轻量边表** |
| 6 错题集归因 | `learner_mistake_book_items` | 否 | 无 | — | 自建 |
| 7 长期学情画像 | `LearnerStateService`/`learning_evidence` | 否 | 无 | — | 自建 |
| 8 学习路径推荐 | `next_training_signal` | 否 | 无 | — | 自建 |
| 9 教材/规范/真题知识库问答 | 多路 RAG + `RetrievalPlan` | **轻微**（编译型检索） | 召回质量 | lock-in/跨境 | 思想吸收 |
| 10 AI 老师对话辅导 | 统一 turn + RAG | 轻微 | 同上 | 同上 | 思想吸收 |
| 11 题目相似度推荐 | embedding | 否（pgvector 已够） | 无 | — | 现有够用 |
| 12 主观题表达优化 | 得分表达改写 | 否（领域生成） | 无 | — | 自研 |
| 13 老师后台薄弱点 | BI + learner_state | 否（结构化 DB 够） | 无 | — | 结构化 DB |
| 14 运营内容生成 | LLM | 否 | 无 | — | 直接 LLM |
| 15 增长素材生成 | LLM | 否 | 无 | — | 直接 LLM |

**范式归属（推断）**：
- **传统 RAG 足够**：场景 9/10/11（教材规范问答、相似题）。
- **结构化 artifact（鲁班已有）**：1/2/3/4/6/7/8/12 —— 这是产品核心，**全部是领域知识，Nexus 给不了**。
- **轻量知识图谱（边表，非 Neo4j）**：5（题-知识点边）。
- **规则 + LLM**：4（错因分类）。
- **纯结构化 DB 足够**：13（老师后台）。
- **直接 LLM**：14/15（运营/增长）。
- **上 Nexus 反而复杂化**：1-8、12（核心评分场景——引入通用检索层无助于领域评分准确率，徒增 lock-in）。

---

## 6. 直接接入 Nexus 可行性（方案 A）

- **技术可行性**：Early Access，无公开 SDK/定价证据，无法评估集成成本。**（未发现证据）**
- **数据出境**：鲁班数据在 Supabase；接入 Pinecone（美国为主，亚太新加坡区）→ 中文教育数据**跨境**，合规与延迟双重成本。
- **与 Supabase/pgvector 关系**：重复建设——鲁班已有 pgvector + 自建 RAG，Nexus 会形成第二套知识基础设施，违背单一权威。
- **领域评分适配**：Nexus 不提供一建采分点知识；仍需鲁班自建采分点 → **接入它不省这块工作**。
- **中文教育场景**：未见官方明确支持声明。**（未发现证据）**
- **citations/structured output**：Nexus 有 per-field citation——但鲁班 `EvidenceRef` 已有等价能力。
- **结论**：**仅适合"观察"，不适合 POC 更不适合生产。**

---

## 7. 自研鲁班 Nexus-lite（方案 B）评估

**判断：不建议作为"新建子系统"，因为鲁班已有等价层。** 若强行新建 14 张 artifact 表 + 通用 Context Compiler 服务，是把已存在的 `case_kernel` + `RetrievalPlan` + `benchmark/` 重新包装，属过度架构。

**正确做法（= 方案 C+，§8 替代评分表中的推荐项）**：在**现有模块**上做最小增强：
- 数据：不新建通用 `knowledge_artifacts` 表；而是给现有 `questions_bank.grading_rubric` 加 **版本字段 + 覆盖率统计**，给 `scoring_point` 补全标注。
- 服务：复用 `case_kernel.grade()`，不新增编译服务；把"采分点编译"做成离线批处理脚本（填充 rubric），而非运行时层。
- eval：复用 `services/benchmark/`，新增一个 20 题 × 100 答案的标注 eval set。

### 7.1 数据库/接口 schema 对照（回答用户问题九——关键是"别重复造已有的"）

对用户提议的 14 张表，逐一对照鲁班现状，**避免过度设计**：

| 提议表 | 鲁班现状（证据） | 判断 |
|---|---|---|
| `knowledge_sources` | `questions_bank.source_meta` / `kb_chunks` 来源 | 已有等价，**不新建** |
| `knowledge_artifacts`（通用） | `questions_bank.grading_rubric` / `structured_rules`（领域化） | 已有等价，**不新建通用大表**（过度设计） |
| `question_rubrics` | `questions_bank.grading_rubric`（字段形式） | 已有；中期**可提取为独立表 + 加版本** |
| `scoring_points` | `scoring_point`(1 migration) + `grading_key.scoring_points` | 已有，**短期：扩覆盖率（数据，非表）** |
| `standard_answer_skeletons` | `questions_bank.correct_answer` / `analysis` | 已有字段，不新建 |
| `common_mistakes` | `case_kernel` 错因类型 + `learner_mistake_book_items` | 部分有；中期可沉淀**题级**常见错因 |
| `knowledge_points` | `questions_bank.node_code` / `testing_focus` | 部分有 |
| `question_knowledge_edges` | **未发现专门边表** | **值得最小新增**（题↔知识点边，支撑薄弱点归因） |
| `student_answer_grading_results` | `CaseGradingResult` 持久化 | 已有 |
| `grading_point_matches` | `grade()` 命中/漏点（结果内） | 已有 |
| `learner_weaknesses` | `learner_state` / `learning_evidence` | 已有 |
| `eval_cases` | `benchmark/fixtures/` | 框架有，**短期：补标注数据（数据，非表）** |
| `eval_runs` | `benchmark/runner.py` / `registry.py` | 已有 |
| `artifact_versions` | **未发现** | **值得最小新增**（`rubric_version` 列即可，教材/规范改版） |

**结论（推断）**：14 张表里约 11 张已有等价物。**真正值得动的只有 3 件**：①`question_knowledge_edges` 轻量边表；②`rubric_version` + provenance 列（版本化，加列不加表）；③补 `eval_cases` 标注**数据**（不是建表）。**绝不新建通用 `knowledge_artifacts` 子系统**。

**6 个 API 对照（多数已存在，缺的是 1 个离线脚本，再次印证"缺数据不缺架构"）**：

| 提议 API | 鲁班现状 | 判断 |
|---|---|---|
| `retrieveRubric(questionId)` | `case_kernel._grading_key_rubric_specs` / `_build_rubric_specs` | 已有 |
| `gradeCaseAnswer(qId, ans, sId)` | `case_kernel.grade()` | 已有 |
| `diagnoseWeakness(studentId)` | `LearnerStateService` | 已有 |
| `recommendReviewPlan(studentId)` | `next_training_signal` | 已有 |
| `compileQuestionArtifact(questionId)` | **未发现** | **新增——但是离线批处理脚本（填充 rubric），不是运行时服务** |
| `runGradingEval(evalSetId)` | `benchmark/runner.py` | 已有 |

---

## 8. 替代方案比较

| 方案 | 成熟度 | 成本 | 工程复杂度 | 可控性 | 适合鲁班程度 | 推荐级别 |
|---|---:|---:|---:|---:|---:|---|
| Pinecone Nexus | 低(EA) | 高(涨价+跨境) | 中 | 低(lock-in) | 低 | ❌ 不推荐 |
| **Supabase pgvector + 结构化 artifacts（现状）** | 高 | 低(已付) | 低 | 高 | **高** | ✅ **首选（强化）** |
| GraphRAG | 中 | 中 | 高 | 中 | 中(仅知识点图) | ◐ 局部 |
| LlamaIndex | 高 | 中 | 中 | 中 | 中 | ◐ 可选组件 |
| LangGraph + 自定义 retriever | 高 | 低 | 中 | 高 | 中(编排) | ◐ 可选 |
| DSPy + eval-driven | 中 | 低 | 中 | 高 | **中高(eval 优化)** | ✅ 思想吸收 |
| Neo4j/Kuzu/Memgraph + 向量 | 高 | 中 | 高 | 中 | 低(重) | ❌ 过重 |
| 纯结构化 DB + LLM | 高 | 低 | 低 | 高 | **高(评分场景)** | ✅ 核心场景 |

**结论（推断）**：对"主观题采分点批改"这类**结构化评分**场景，最合适的范式是 **结构化 DB（采分点/错因/证据）+ LLM 对照 + eval 闭环**——即鲁班现状的强化版，而非任何通用检索框架。

---

## 9. POC 设计（2 周，验证"是否值得在采分点 artifact 上加大投入"）

注意：POC 验证的**不是 Nexus**，而是"artifact-first（结构化采分点）相对 baseline/RAG 是否真能提升批改准确率"——这才是真问题。

1. 选 20 道一建建筑实务案例题（从 `questions_bank` 取，优先已有 `grading_rubric` 的）。
2. 每题标注：题干 / 标准答案 / 采分点+分值 / 常见错误 / 知识点 / 来源（教材章节或真题年份）。
3. 构造 100 份学生答案（含满分/部分/口号化/漏点/跑题各档）。
4. 三臂对比：
   - **Baseline**：当前 prompt 一次批改（关掉 rubric 注入）。
   - **RAG**：检索 `kb_chunks` 相关 chunk 后批改。
   - **Artifact-first**：走 `case_kernel.grade()` 注入 `grading_key.scoring_points`（鲁班现状）。
5. 指标：总分偏差 / 采分点 precision / recall / 错因准确率 / 幻觉率 / token / latency / 可解释性。
6. 成功阈值：平均分差 ≤1 分；采分点 recall ≥90%；幻觉率 ≤3%；token 较 RAG 降 ≥40%；延迟 ≤baseline×1.5。
7. **POC 执行清单（最小侵入）**：
   - 复用 `services/benchmark/runner.py` + `exam_quality_eval.py`，新增 eval set fixture（`deeptutor/services/benchmark/fixtures/`）。
   - 新建脚本 `scripts/poc_grading_three_arms.py`（仿 `scripts/smoke_construction_grading_supabase.py`）。
   - 不建新表（用 fixture JSON）；只读 `questions_bank`。
   - 跑 `pytest tests/services/construction_grading/` 确保不回归。
   - 产出对比表 → 决定是否扩大采分点标注。

---

## 10. 4 周 / 8 周路线（若 POC 通过，强化方向）

- **第 1 周**：标注 20 题 eval set + 跑三臂 baseline。交付：量化对比表。改动：`benchmark/fixtures/`、`scripts/poc_*`。验收：三臂指标出齐。
- **第 2 周**：依据结果给 `questions_bank.grading_rubric` 补标注（覆盖率从 X% → 目标）。交付：采分点覆盖率报告。改动：离线标注脚本 + Supabase 数据。验收：核心高频题 rubric 覆盖 ≥80%。
- **第 3-4 周**：rubric **版本化**（migration 加 `rubric_version` + `source_provenance`）+ eval 纳入 CI。交付：版本化 schema + CI gate。改动：`supabase/migrations/`、`benchmark/registry.py`。验收：rubric 改版可追溯、eval 回归自动跑。
- **第 5-8 周**：扩大 eval set 到 100+ 题、接入趋势监控（`benchmark/trend.py`），把"采分点 recall / 分差"做成生产看板（复用本会话刚做的 BI 思路）。交付：批改质量看板。验收：质量指标可持续观测。

---

## 11. 风险清单

- **vendor lock-in**：Nexus 专有 + KnowQL 未标准化 → 高（接入则锁定）。
- **数据迁移/出境**：中文教育数据跨境 Pinecone → 合规风险。
- **早期不稳定**：Early Access，无 GA/SLA 证据。
- **中文场景适配**：未见官方支持声明。
- **评分标准结构化难度**：真实瓶颈，但属鲁班内部工作，Nexus 不解决。
- **eval 数据不足**：当前最大短板（harness 有、数据缺）。
- **成本不可控**：Pinecone 2.0 涨价 300% 先例。
- **过度架构化**：自研通用 Nexus-lite = 重复造已有的 `case_kernel`/`RetrievalPlan`/`benchmark`。
- **团队维护成本**：第二套知识基础设施长期负担。
- **artifact 陈旧**：教材/规范改版需重编译——鲁班用版本化+离线重跑可控，Nexus 的刷新成本未公开。

---

## 12. 最终建议

**最终结论：**
- **是否直接接入 Pinecone Nexus**：**否**（Early Access、benchmark 不可验证、跨境、lock-in，且解决不了领域评分知识缺口）。
- **是否自研 Nexus-like 知识编译层**：**否（不新建通用层）**；**是（仅在已有 `construction_grading` + `benchmark` 模块上吸收其思想强化）**。
- **当前最优路径**：方案 C+ —— 保持 Supabase pgvector + 现有 artifact-first 批改架构，集中资源做"采分点标注覆盖率 + eval 数据 + rubric 版本化"。
- **未来重新评估 Nexus 条件**：①GA + 第三方 benchmark 复现；②明确中文/数据驻留；③出现鲁班无法自建、且对一建评分有实质增益的能力。
- **第一优先级行动**：用已有 `services/benchmark/` 跑 20 题三臂 POC，把"采分点覆盖率/批改准确率"短板从推断变事实（2 周）。
- **第二优先级行动**：依 POC 结果补全高频题 `grading_rubric` 采分点标注，并加 `rubric_version` + provenance（第 2-4 周）。
- **第三优先级行动**：eval 纳入 CI + 批改质量看板，形成"标注→批改→eval→改进"闭环（第 5-8 周）。

**一句话给技术合伙人**：Nexus 验证了你方向对，但你不需要买它，也不需要重造一个通用版——你已经有了领域版，差的是采分点数据和 eval，把钱和人投在这两件 Nexus 永远替你做不了的事上。

---

### 附：可信度与不确定性声明
- 所有 Nexus 性能数字均"未独立验证"（vendor-reported / KRAFTBench 自建）。
- Nexus SDK/CLI/定价/GitHub 活跃度"未发现公开证据"。
- 鲁班"采分点覆盖率/eval 标注规模"在 migrations 中"未发现规模化证据"，需 POC 量化。
- 本报告区分：事实（代码/官网一手）、推断（架构判断）、建议（行动）。
