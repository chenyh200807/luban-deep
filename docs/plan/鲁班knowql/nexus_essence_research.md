# Pinecone Nexus / KnowQL 精髓研究（带出处）

> 研究员：Nexus 原典研究员（Claude Opus 4.8）
> 日期：2026-06-13
> 方法：WebSearch + WebFetch 抓取 Pinecone 一手材料（blog / learn / product 页）+ 一篇独立分析师稿（HyperFRAME）做对照。
> **诚实铁律**：每条结论标注「文档证实 vs 合理推断」。Pinecone 在 2026-05 发布 Nexus / KnowQL，处于**发布稿阶段**——`docs.pinecone.io` 上**尚无 KnowQL 技术参考/语法 BNF**（已核实 docs overview 页无任何 Nexus/KnowQL 内容）。因此 KnowQL 的"语义"我们只有发布博客里的**示例 JSON + 6 个 primitive 的散文定义**，没有正式 grammar。凡涉及内部数据结构的细节，多为推断，已逐条标注。

---

## 出处清单（一手优先）

一手（Pinecone 官方）：
1. [Better Models Won't Save Your Agent — Introducing Nexus](https://www.pinecone.io/blog/introducing-nexus-knowledge-engine/)（含 KRAFTBench 基准表 + KnowQL 示例 query）
2. [Pinecone Nexus: The Knowledge Engine for Agents](https://www.pinecone.io/blog/knowledge-infrastructure-for-agents/)（6 个 primitive 定义 + per-field citation 措辞）
3. [How a Knowledge Engine Works: From Artifacts to Agent-Ready Answers](https://www.pinecone.io/learn/how-knowledge-engines-work/)（compile loop 四阶段 + skill library + 多目标打分 + 另一条 KnowQL 示例）
4. [Pinecone Nexus 产品页](https://www.pinecone.io/product/nexus/)（6 primitive 的 ask/where/ground/shape/confidence/budget 命名 + runtime 数字 0.5K·50ms vs RAG 12K·~4s）

二手（独立/分析师，仅作对照与质疑）：
5. [HyperFRAME Research：Pinecone Expands Beyond Vector Search](https://hyperframeresearch.com/2026/05/05/pinecone-expands-beyond-vector-search-as-agent-constraints-drive-a-new-knowledge-execution-layer/)（独立质疑：vendor-reported、artifact drift、refresh cadence）
6. [ComputerWeekly Developer Network：Nexus offers a knowledge engine for agents](https://www.computerweekly.com/blog/CW-Developer-Network/Pinecone-Nexus-offers-a-knowledge-engine-for-agents)（system of record vs system of knowledge 原话）
7. [VentureBeat：The RAG era is ending for agentic AI](https://venturebeat.com/data/the-rag-era-is-ending-for-agentic-ai-a-new-compilation-stage-knowledge-layer-is-what-comes-next)（**未能抓取**——HTTP 429 / timeout；列出仅供溯源，本文未引用其内容）

> **未找到权威出处的项**：KnowQL 正式 grammar / 类型系统 / artifact 落盘 schema / citation 的具体数据结构 / 去重消歧算法 / canonicalization 规则。这些 Pinecone 都只给了**散文级承诺**，没给规范。下文凡涉及这些，一律标「推断」或「未证实」。

---

## 五个机制的精髓摘要

### 1. typed knowledge object（artifact）到底长什么样

**文档证实：**
- 定义：artifact 是 **"a typed, governed piece of information constructed for a specific task or outcome"**（出处1）／**"the atomic unit: a typed, governed information object"**（出处4）。关键词三个：**typed（带类型）/ governed（带治理：RBAC、版本、PII）/ task-specific（为某个任务塑形，不是通用召回）**。
- **同源不同形**："Same source. Different artifacts. Each shaped for the agent's task, not generic retrieval over the recording."（出处3）——同一份语料，按任务编译出**多个**不同形状的 artifact。
- 已命名的 artifact 形态举例（出处3）：`entity profiles compiled across hundreds of documents`、`dependency graphs`、`semantic layers for analytics (tables, columns, relationships, anti-patterns, worked examples)`、`decision frameworks distilled from policy documents — the rules, not the PDF`。
- 字段级类型：出处1 给了**唯一一个具体 output schema**（10-K 财报查询）：
  ```json
  "properties": {
    "company_name": {"type": "string"},
    "repurchased_usd_millions": {"type": "number"},
    "program_size_usd_millions": {"type": "number"},
    "remaining_usd_millions": {"type": "number"}
  }
  ```
- **字段级溯源（最关键的精髓点）**："**Field-level citations returned by construction, not reconstructed after. Every value carries its source.**"（出处1、3）——citation 是**编译期随对象一起构造**的，**不是**事后再让模型/检索去拼。出处2 进一步：**"Typed fields. Per-field citations with confidence levels."**
- 治理元数据（出处4 / 出处2 / 搜索摘要）：artifact 带 `RBAC scoping`、`version number`、`sources`、`PII tagging`；contract artifact 还继承 `file permission metadata`。
- 响应里还会带**冲突**：出处3 的 diagram caption："Structured response returns **Typed Fields, Citations, Confidence, and Conflicts** so the agent can finish without looping." —— 即 artifact 不仅给值+出处+置信，还把**冲突显式暴露**给 agent，让 agent 一次拿全、不用循环。

**推断（未证实）：**
- citation 在落盘上是「每个字段一个 `{value, source_ref, confidence}` 三元组」——这是从 "every value carries its source" + "per-field citations with confidence levels" **推出来的最自然结构**，但 Pinecone **没给** artifact 的正式 schema，没说 confidence 是连续分数还是 tier。注意出处4 用的词是 **"confidence tiers"**（分档），出处1/2 用 **"confidence levels/scores"**——**两处措辞不一致**，说明对外没定死，**不能当事实断言它是连续分数**。

---

### 2. KnowQL 查询语义

**文档证实：**
- 定性："**a typed declarative query language for agentic knowledge retrieval**"（出处3）／"the first declarative query language designed for **agents rather than humans**"（搜索摘要，多处）。**声明式**、**为 agent 设计**（不是给人读的 SQL）。
- **形态是声明式 JSON，不是类 SQL**。三条官方示例：
  - 出处1（10-K 多实体对比）：
    ```json
    { "ask": "Among NVIDIA, Microsoft, and Walmart, compare fiscal 2022...",
      "ground": true,
      "shape": { "type": "object", "properties": {...} } }
    ```
  - 出处3（合同续约折扣）：
    ```json
    { "ask": "Does Acme qualify for a renewal discount?",
      "shape": { "qualifies": "bool", "discount_pct": "number", "applicable_rules": ["..."] },
      "ground": true }
    ```
- **6 个 primitive**（出处4 给了最干净的字段名映射，出处2/3 给散文定义）：
  | primitive | 字段名(出处4) | 含义(出处4 原话) |
  |---|---|---|
  | Intent | `ask` | "The goal, output schema, and contexts to query" |
  | Filter | `where` | "Deterministic predicates and access-control enforcement" |
  | Provenance | `ground` | "Field-level citations with confidence tiers" |
  | Output Shape | `shape` | "Typed fields returned exactly as the agent specified" |
  | Confidence | (含在 ground) | "Grounded assertions separated from uncertain inferences" |
  | Budget | `budget` | "Depth tier and latency envelope, plus a token budget" |
- **intent 怎么选字段 / 约束 output shape**：靠 `shape` 直接声明返回的 typed schema——"**Output shaped exactly as the agent specified**"（出处2）。即 agent **在 query 里把想要的字段+类型写死**，引擎按这个 schema 返回。出处3 强调 "The full primitive surface (`scope`, `where`, `ground` with **per-field options**, `budget`)"——`ground` 支持**逐字段**指定是否要溯源。
- **cost/latency 声明在结果维度而非 token**："**Cost declared in outcomes, not tokens**"（出处1）——budget 是「深度档 + 延迟目标」，不是让 agent 估 token。

**推断 / 未证实：**
- KnowQL 的**正式语法、类型系统、可组合算子（join / aggregate 跨 artifact）**没有公开规范。出处3 自己写 "the full primitive surface is in the table above" 但**那张表的内容没放出来**。**所以"KnowQL 是 SQL 的声明式表亲"这种说法不能当事实**——目前只能确证它是**带 `ask/where/ground/shape/budget` 的声明式 JSON 调用**。
- "intent 如何把自然语言 `ask` 解析并路由到正确 artifact 的特定字段"——**机制未公开**。合理推断是引擎内部有 planner 把 `ask`+`shape` 编译成对已编译 artifact 的取数计划，但**这是推断**。

---

### 3. compile pipeline（语料 → typed object 的离线编译）

**文档证实——这是 Nexus 最有料、最该学的部分：**
- 编译器叫 **Context Compiler**，本质是**一个自治 coding agent**。它**改两个函数**："the coding agent modifies two functions, **`curate()`** for artifact construction and **`query()`** for knowledge retrieval, runs the eval set, uses the failure signal to refine the code, and repeats until the evals pass."（出处1）
- **输入三件套**（出处1）：
  1. `An eval set you define per domain`（每个领域**自带「代表性任务 + 已知正确答案」的评测集**）+ 对应数据源；
  2. `A library of pre-vetted skills`（**预先审核过的 skill 库**：document processing、entity extraction、chunking、dimensional modeling、symbol-tree generation、**cross-document linking**——出处3）；
  3. task spec（用例 + 上下文需求）。
- **四阶段循环**（出处3 的 diagram）：
  1. Ingest and Parse（structure and entities）
  2. Represent and Derive（task-optimized representations and artifacts）
  3. Evaluate Against Task（precision, coverage, completeness）
  4. Converged? → 否则回到 2 继续迭代
- **多目标联合打分**："It scores candidate strategies against a **multi-objective function (accuracy, tokens, and latency, jointly)**, so that no single objective dominates."（出处3）——编译不是只追准确率，而是**准确/token/延迟三者联合优化**。
- **产出是可审计、可改、可 fork 的代码 artifact**："it commits the **winning code as a versioned, inspectable, forkable strategy**: code the team can read, modify, and override."（出处3）——编译产物**不仅是数据，还是生成数据的代码策略**，团队能 override。
- **去重/消歧/单一权威**：**这里只有间接证据**。出处1 把 RAG/coding-agent 的失败明确归因到**消歧失败**：coding agent **"phrases can appear multiple times in each document and there's no way to determine which mention is the right one"**；RAG **"failed to find the dollar amounts ... since the dollar figure and chunks were not colocated"**。Nexus 的对策是编译期就把这些**消解掉**——产物例子："a table aggregating contract renewal terms across different contracts which allows Nexus to answer ... by fetching a **single artifact** rather than searching across multiple entities."（出处1）+ 搜索摘要给出 composable retriever 带 **"deterministic conflict resolution"（确定性冲突消解）**。

**推断 / 未证实：**
- "单一权威 / canonicalization / 去重"的**具体算法 Pinecone 没写**。出处1/3 **没有**显式出现 "deduplication"、"canonicalization"、"single source of truth" 的算法描述（出处6 的 "system of knowledge vs system of record" 是定位口号，不是机制）。**能确证的是「编译期消解 + 单 artifact 取数 + deterministic conflict resolution 这个结果承诺」，不能确证它内部怎么做的**。这正是我们要警惕的"精髓黑箱"——把结果当机制学会出错。

---

### 4. retrieve vs compile 边界（还用不用向量检索）

**文档证实：**
- **向量检索没有被删，它沉到了底座**。Pinecone 原话："The vector database is the foundation; **vector primitives and their management remain essential**."（出处6）／出处4："Nexus uses vector infrastructure, but it **adds the knowledge layer above storage and retrieval**." 出处2 补充刚加了 **native full-text search + native hybrid retrieval（vector + full-text unified）**。
- **两层职责切干净了**：
  - **compile 层（离线、一次性）**："structures, contextualizes, and composes specialized contexts **before the agent needs them**. The work happens **once at compilation time**."（出处3）
  - **retrieve 层（在线、查询时）**：有个 **composable retriever**，"serves these curated artifacts **at query time**: low-latency, grounded, composable across sources"（出处2）+ 搜索摘要："delivers these artifacts at query time with typed fields, per-field citations ... and **deterministic conflict resolution**."
- **所以边界是**：**典型问答路径 = 在线对「已编译 artifact」做确定性取数（composable retriever），而不是在线对 raw chunks 做向量相似度召回再丢给大模型**。出处1 的对比表里 Nexus **平均 1.69 步**（RAG 7.77 / coding 14.77）就是因为它**取一个 artifact 就答完**，不在线多跳检索。

**关键诚实点（边界的模糊处）：**
- **"typed object 是替代检索，还是检索的对象变成了 typed object？"——两者都对，分层看**：
  - 对 **agent 而言**，artifact **替代**了"在线检索 raw docs"这一步（HyperFRAME 出处5："Agents consume structured context **instead of** assembling it dynamically"）。
  - 但底层 vector/full-text/hybrid **仍在**——**推断**它主要服务于**编译期**（ingest/represent 阶段找候选语料）以及可能的**artifact 选取**。但"查询时是否还用向量相似度来**挑哪个 artifact**"——**出处明确说未公开**（HyperFRAME 出处5 原话："whether vectors are still queried at runtime or only during artifact compilation ... is not detailed"）。
  - **结论**：可证实「artifact 是 agent 在线消费的对象，向量检索退到底座/编译期」；**不可证实**「查询时彻底无向量」。**别把"Nexus 不用向量了"当事实说**。

---

### 5. 什么 regime 赢 RAG、什么 regime 不赢

**文档证实——Pinecone 自报的赢面（KRAFTBench，出处1，150 道难题 / 493 份 SEC 10-K）：**

| 指标 | Nexus | RAG | Coding Agent |
|---|---|---|---|
| Accuracy | **0.680** | 0.413 | 0.585 |
| Latency(avg) | **22.7s** | 37.9s | 84.1s |
| Tokens(avg) | **6,733** | 49,103 | 528,301 |
| Completion | **100%** | 98.7% | 62.7% |
| Steps(avg) | **1.69** | 7.77 | 14.77 |

产品页另给 runtime 口径：Nexus **0.5K token · 50ms** vs RAG **12K · ~4s**（出处4）；以及 "30× faster"、">90% completion"、"up to 90% token reduction"（出处2/3）。

**赢的 regime（文档明确归因）：**
- **多文档/跨实体合成**："Cross-document synthesis fails silently" with RAG；Nexus 用 "deterministic, pre-built artifacts that consolidate cross-document facts at construction time"（出处3）。
- **确定性消歧**（同一事实在多处出现，要选对那一个）——RAG/coding 的核心败因（出处1）。
- **重复查询 / 摊销**："Compile once, read many ... serves cheaply thereafter"（出处3）。
- **治理/审计**："provenance with every field"，RAG "no audit trail back to source"（出处3）。
- **可预测的 token/延迟预算**：budget envelope vs RAG "unbounded retrieval depth"（出处3）。

**不赢 / RAG 仍合适的 regime（文档承认得很少，要诚实）：**
- Pinecone **自己只承认两处**（出处3 对比表）：vanilla RAG "**Works for short single-document lookups against well-formatted text**"；MCP+tool calling "**Useful for prototypes and bounded surfaces**"。
- **Pinecone 没有显式说自己在哪类任务输**（出处1/3 均无 "where Nexus underperforms"）。
- **独立分析师的质疑（出处5，必须保留）**：
  - "Compilation **shifts compute from inference to preparation**, introducing new operational considerations around **refresh cadence, artifact drift, and storage growth**."（编译没消除成本，只是搬到上游，且新增 artifact 漂移/刷新/存储问题）
  - "These performance metrics remain **vendor-reported** and will require validation across diverse enterprise workloads."（基准是 Pinecone 自家出的）
  - "Early deployments will determine whether ... consistently delivers cost and latency advantages **outside controlled scenarios**."
- **推断（标注为推断）**：编译范式天然不擅长**「任务 spec 高度发散、长尾、一次性、无法预先定义 eval set」**的开放问答——因为它的整条 pipeline 依赖 "an eval set you define per domain" + "task spec"。**没有稳定可枚举的任务，就没有东西可编译**。这点 Pinecone 没明说，但**逻辑上是它的结构性边界**。

---

## 我们的精确差距（对照 1-5，逐机制）

> 我们现状："编译材料 → runtime 当 context 塞进 prompt → 模型自由组织答案"。

| # | Nexus 精髓机制（已证实部分） | 我们现在的做法 | **精确差距（差在哪个具体机制）** |
|---|---|---|---|
| 1 | typed object：**字段级 typed schema + 字段级 citation 在编译期随对象构造（"every value carries its source"）+ 显式 Conflicts** | 编译产出的是**给人/模型读的材料文本**，runtime 整块塞进 context | **差在「字段级 provenance 是编译期构造的不变量」**。我们的溯源（若有）是"材料里写了出处，模型可能引用也可能不引用"——**citation 不是结构强制项，是模型自觉**。→ 我们没有 "value 必带 source" 的硬不变量，也**没有把 Conflicts 显式 surface 给消费方**。 |
| 2 | KnowQL：**消费方在 query 里用 `shape` 声明想要的 typed 字段，引擎按 schema 返回；output 被 schema 约束死** | 消费方拿到的是**自由文本 context**，**输出形状由模型即兴决定** | **差在「输出契约」**。我们**没有声明式的 `ask/shape/ground` 调用**，消费端无法说"我只要这 3 个字段、每个都要溯源、预算 X"。→ output shape 不可约束、不可逐字段要溯源、不可声明预算。这是**最大的机制缺口**：我们停在"塞 context"，Nexus 在"声明式取数 + schema 约束输出"。 |
| 3 | compile pipeline：**eval-set 驱动的自治 coding agent，多目标(准确/token/延迟)联合优化，产物是可审计可 override 的 `curate()/query()` 代码 + 编译期消歧→单 artifact + deterministic conflict resolution** | 我们有"编译材料"这步，但**（推断）是规则/模板式产出**，**无 per-domain eval set 闭环**，**无多目标打分**，**消歧/单一权威靠下游/人工** | **差在三点**：(a) **没有 eval-set 收敛闭环**——编译质量不是"跑评测直到过"，而是"写完就用"；(b) **没有把 token/latency 纳入编译目标**——我们编译只关心内容对不对，不联合优化消费成本；(c) **消歧/单一权威没有在编译期固化成 artifact 不变量**——我们靠 runtime 模型或人去消歧，正是 Nexus 归因的 RAG/coding 败因。 |
| 4 | retrieve/compile 边界：**agent 在线消费的是已编译 artifact（取一个就答完，avg 1.69 步），向量检索退到底座/编译期** | 我们 runtime 仍把材料"当 context 塞"，**模型在 context 里在线"翻找+组织"**——本质是把消歧/选取推迟到了**推理时** | **差在「在线 vs 编译期的工作切分」**。我们把"从材料里挑出该用的、消解冲突、组织成答案"留给了**runtime 模型的自由发挥**（= Nexus 说的 "model burns tokens sifting through raw content"）。Nexus 把这步前移到编译期，runtime 只做**确定性取数**。→ 我们的 runtime 步数/token/不确定性都高，且**答案组织过程不可审计**。 |
| 5 | 赢面 regime：**多文档合成 / 确定性消歧 / 重复查询摊销 / 字段级审计 / 可预测预算** | 我们若任务是**可枚举、重复、需跨材料一致结论**的（鲁班判分/采分点正是这种） | **差在没吃到自己最该吃的红利**。我们的判分/采分点场景**恰好落在 Nexus 的赢面**（重复查询、需单一权威、需字段级溯源——见 MEMORY："采分点必须教材原文溯源"、"V1 评分开放世界 Nexus"）。**但我们用的是"塞 context 让模型自由组织"= RAG 那条输的路径**。→ 差距不是场景不对，是**我们在该用编译范式的场景用了 runtime 自由组织范式**。 |

### 一句话总结差距
我们与 Nexus 精髓的差距，**不在"有没有编译材料"，而在四个具体机制全缺**：
1. **字段级 provenance/confidence 不是编译期构造的硬不变量**（机制1）；
2. **没有声明式输出契约（shape/ground/budget），output 形状由模型即兴决定**（机制2）；
3. **编译不是 eval-set 驱动 + 多目标(准确/token/延迟)收敛，消歧/单一权威没在编译期固化**（机制3）；
4. **消歧+答案组织留在 runtime 让模型自由发挥，而非前移到编译期做确定性取数**（机制4）。

这四条合起来，正是为什么"我们一直没学到精髓"：**我们把 Nexus 的"compile-then-deterministic-retrieve"做成了"compile-then-stuff-context-and-let-the-model-freestyle"——后半段塌回了 RAG。**

---

## 诚实声明（哪些是事实、哪些是推断、哪些没找到）

- **文档证实**：artifact 是 typed/governed/task-specific；字段级 citation 编译期构造（"every value carries its source"）；KnowQL 是声明式 JSON，6 primitive = ask/where/ground/shape/confidence/budget，shape 约束输出；Context Compiler = 改 `curate()/query()` 的自治 coding agent，eval-set 驱动，多目标(准确/token/延迟)联合打分，产物可审计可 override；向量检索退到底座、agent 在线消费 artifact；KRAFTBench 数字与 token/latency 赢面归因。
- **合理推断（已逐条标注，非 Nexus 事实）**：citation 落盘为 `{value, source, confidence}` 三元组；confidence 连续 vs tier（措辞不一，存疑）；查询时"挑哪个 artifact"的内部 planner；编译范式不擅长不可枚举的长尾开放问答。
- **未找到权威出处**：KnowQL 正式 grammar / 类型系统 / 跨 artifact join-aggregate 算子；artifact 落盘 schema；去重/消歧/canonicalization 的**具体算法**；Pinecone 自承的失败 regime；VentureBeat 原文（429/timeout 未抓到，未引用）。`docs.pinecone.io` 截至抓取日**无 KnowQL 技术参考**，KnowQL 仍是发布稿阶段的概念+示例，**不是已公开的规范**。
