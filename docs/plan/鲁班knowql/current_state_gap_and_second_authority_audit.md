# KnowQL 现状审计 + 第二权威风险全扫 + 建设禁区

> Status: `Audit / read-only` — 2026-06-13
> Scope: 只读现状审计。本文件不新增 contract、不改代码、不替代 master plan。任何实现仍以 `CONTRACT.md`、`contracts/index.yaml`、`docs/plan/评分引擎与金标工件/2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md`（含 §4.6 Narrow KnowQL-Inspired Query Contract）为准。
> 审计员身份：KnowQL 现状审计员 + 单一权威风险扫描员。
> 权威依据：`AGENTS.md` §0 Thin Wrappers Fat Skills / §5.6 复发机制+硬门槛 / §5.7 Single Authority Hard Gate / §5.8 Post-QA Root-Cause Gate。

---

## 0. 一句话结论

我们离 "KnowQL（typed object + 按 intent 查询 + artifact 强制 shape + field-level provenance）" 最近的是**支柱①编译成 typed object（约 80%）和支柱④field-level provenance（约 75%）**；最远的是**支柱②按 intent 查询的查询语言（约 25%，目前只有 §4.6 纸面契约 `retrieveRubric`，无实现）**。

最危险的第二权威风险不是 Phase3 AI 面板（它已被 `validate_ai_governed_gold_protocol` 用 `official_score_allowed=False / is_release_truth=False` 关在 quality-label 闸内），而是 **rich leaf v3.2 的 5705 采分点本身**——它是 AI 派生物，体量是官方 key 的 50x+，一旦被 runtime 直读当判分 key，就会无声盖过官方 reference answer。它现在靠 `candidate_only / review_only / quality_claim_allowed=false` 关着，但**没有一个 deterministic 不变量在 runtime 把"采分点 vs 官方 key"的权威序固定下来**，全靠 artifact 自报的 classification flag。这是 KnowQL 建设时最容易越权的点。

---

## 任务1 · 四支柱完成度精确审计

打分口径：**做到了什么 / 缺什么 / 缺口的具体技术形态**。百分比是"对照 KnowQL 该支柱完整形态的成熟度"，不是测试覆盖率。

| 支柱 | 完成度 | 做到了什么（带证据） | 缺什么 | 缺口的具体技术形态 |
|---|---|---|---|---|
| **① 编译成 typed object** | **80%** | (1) `build_typed_case_grading_artifact`（`scripts/run_luban_student_answer_grading_eval.py:353`）把官方 reference answer 重构成 `case_grading_artifact.v1`：`subquestions[].scoring_points[].{point_id,sub_no,weight,canonical_answer,required_terms,miss_tags,provenance}`，带 `output_contract`（`must_emit_one_result_per_point_id` 等）。(2) rich leaf v3.2 pack（`runtime_token_pack_v32_scoring_points.json`）已是 typed：1612 个 `runtime_token_pack_units`，每个 unit 的 `compiled_context.scoring_points[]` 是带 `point_id/policy_type/provenance/required_terms/source/statement` 的 typed object，5705 采分点。(3) frozen taxonomy（`taxonomy-frozen-v1.1-20260613`，1612 evidence leaf）做了 leaf 维度的 typed 锚。 | (1) 没有**统一的 typed schema 单一 authority**：`case_grading_artifact.v1`（eval 脚本内联）和 `luban_rich_leaf_scoring_point_compile.v1`（rich leaf pack）是两套并行 typed shape，字段名不同（`weight` vs `max_score`、`canonical_answer` vs `statement`、`miss_tags` vs 无）。(2) typed object 还没有跑成"运行时唯一可读对象"——rich leaf pack 是 `runtime_install_allowed=false` 的 candidate。 | 双 schema 漂移：同一"采分点"概念有两个 typed 定义，谁是 canonical 没在代码里固定，靠人记。要 KnowQL 必须先把这两个 schema 收敛成一个 typed object authority（dataclass / Pydantic / 单一 JSON schema），否则查询语言会被迫同时支持两套形状。 |
| **② 按 intent 查询对象字段（查询语言）** | **25%** | 只有**纸面契约**：Nexus 执行计划 §4.6 定义了窄版 `retrieveRubric(question_id, purpose, shape, citation_required, budget_tier)`，把 KnowQL 的 `ask/where/ground/shape/confidence/budget` 映射到 Luban。这是设计正确的"narrow KnowQL-inspired"。 | **几乎全部**：没有实现、没有 query executor、没有 intent 解析、没有 shape 投影器。当前 runtime 还是 ad-hoc helper 调用 + prompt 拼接（计划自己承认 "Runtime can drift back to ad-hoc helper calls"）。 | 没有"按 intent 查询字段"的语言层。现在要拿某个 question 的 rubric，是直接读 artifact dict 的字段，没有 `purpose=grading/explanation/review_plan` 的 intent 维度，也没有 `shape` 维度去裁剪输出。这是四支柱里**最薄、风险最高**的一根——KnowQL 的精髓就是这根，而我们这根只有 spec。 |
| **③ 输出 shape 被 artifact 强制约束** | **70%** | 这是**最成熟可运行**的一根。`enforce_output_schema`（`scripts/run_luban_student_answer_grading_eval.py:719`）锁死 per-point 输出：`_REQUIRED_POINT_RESULT_FIELDS`（11 个必填字段 + 类型 + `bool` 拒绝）。`validate_grading_output`（:750）做 7 道 hardening：高分冲突、missing/extra point、子问不可坍缩（`subquestion_without_point_results`）、awarded∈[0,max]、Σawarded≤Σmax、miss 必带 deduction、score_pct 自洽（`score_pct_mismatch`）。违规 → `contract_invalid` + `should_regrade`。 | (1) 这套强制只在 **eval 脚本里**，不是 runtime 判分链路的 authority——它约束的是"eval 拿到的模型输出"，不是生产判分。(2) 约束的是 `case_grading_artifact.v1`，rich leaf pack 那套 typed object 没有对应的 output-shape enforcer。 | output 强制和 typed object 定义分属两个文件、两套 schema，没有"artifact 定义 shape → 同一 artifact 强制 shape"的闭环。KnowQL 要求 `shape` 是 query 的一等参数且由 artifact 强制；我们目前是"硬编码 11 字段的 validator"，没法按 intent 切不同 shape。 |
| **④ field-level provenance** | **75%** | (1) `_attach_point_provenance`（`scripts/run_luban_student_answer_grading_eval.py:310`）给每个原子 point 绑 `gold_ref` + 教材 `source_ref`，命不中教材就标 `sourced=False / source_authority="unsourced"`——**绝不伪造、绝不静默丢弃**（符合 memory: 采分点必须教材原文溯源）。(2) rich leaf pack 每个采分点带 `provenance={chunk_id,quote,quote_verified,source_authority:"textbook"}`，编译报告显示 97 个 gold point 里 69 个有教材 provenance、28 个 `skipped_no_textbook_provenance`（缺口被显式记账，不掩盖）。(3) `validate_grading_output` 把 `provenance.sourced is False` 升成 `unsourced_scoring_points` warning。 | (1) provenance **粒度不均**：eval 脚本是 point→教材 ref，rich leaf 是 chunk_id+quote，两者 provenance schema 不同。(2) `quote_verified=true` 的验证逻辑是编译期一次性，runtime 不重验（`live_provider_revalidation` 在 `not_exercised` 列表）。(3) 28/97 缺 provenance 的 point 仍在 pack 里（review_only），它们是"有 statement 无教材锚"的半成品。 | provenance 是"附在字段上的 dict"，不是"查询时可被 `ground` 强制要求的一等约束"。KnowQL 的 `ground` 要求 score-bearing point 必须带 field-level citation 才能判分；我们有数据但**没有 deterministic gate 在判分时拒绝 unsourced point 参与给分**（现在只是 warning）。 |

### 四支柱完成度表（紧凑版）

```
① 编译成 typed object         ████████░░  80%   双 schema 待收敛
② 按 intent 查询（查询语言）   ██▌░░░░░░░  25%   只有 §4.6 纸面契约，零实现 ← 最薄
③ 输出 shape 被 artifact 强制   ███████░░░  70%   强制器只在 eval，未进 runtime authority
④ field-level provenance       ███████▌░░  75%   有数据，缺"判分期强制 ground"的 gate
```

**KnowQL 建设排序建议（由审计推出，非新计划）**：先把①的双 schema 收敛成单一 typed object authority（这是②③④的共同地基），再把③的 `enforce_output_schema` 从 eval 提升为该 typed object 的方法（shape 由 artifact 自己强制），最后才动②的 `retrieveRubric` 查询语言——②建在漂移的双 schema 上必然返工。

---

## 任务2 · 第二权威风险全扫（AI 派生物 vs 官方权威）

扫描定义（来自 AGENTS §5.7 / §5.8）：任何 AI 派生 artifact、字段、fallback、frontend projection，如果可能被某个 reader 当成"和官方权威竞争的第二真相"来读，就是第二权威风险。每条标：**权威应该是谁 / 当前 artifact 有没有越权 / 怎么降级成投影或评审镜**。

按风险从高到低排序：

### 风险 R1（最高）· rich leaf 5705 采分点 vs 官方 reference key
- **AI 派生物**：`runtime_token_pack_v32_scoring_points.json`，5705 采分点（`chunk_assessment` 1567 + `knowledge_card` 3933 + `m35_artifact` 205），由编译轴从教材/知识卡生成。
- **权威应该是谁**：官方 reference answer / 教材原文是判分 key 的唯一 canonical truth。采分点是它的**投影/弹药**（memory: 编译库是弹药不是门槛），不是替代品。
- **当前有没有越权**：**结构上没越权，但护栏是软的**。pack 自报 `candidate_only=true / review_only=true / runtime_install_allowed=false / quality_claim_allowed=false / canonical_pointer_written=false`，编译报告 `verdict=PASS_SCORING_POINT_COMPILE` 但 `not_exercised` 含 `canonical_truth_write / official_score / runtime_default_install`。**问题：权威序完全靠 artifact 自报的 boolean flag，没有一个 runtime deterministic 不变量在"采分点想参与给分"时强制它退到官方 key 之后。** 体量（50x 官方 key）使得一旦 install，它事实上会主导判分。
- **怎么降级成投影/评审镜**：(a) 建 KnowQL 时，`retrieveRubric` 的 `where` 必须把"官方 key 命中"和"采分点命中"分成两个 confidence 通道，官方 key 永远是 primary，采分点只能 `shape=supporting_evidence`；(b) 把 `runtime_install_allowed=false` 从"自报 flag"升成"由 release gate 派生的 deterministic 闸"；(c) 28 个 `skipped_no_textbook_provenance` 的 point 在任何判分 shape 里都不得出现（`ground` 强制）。

### 风险 R2（高）· Phase3 AI 面板共识当金标权威（已知样本，已部分关好）
- **AI 派生物**：`validate_ai_governed_gold_protocol`（`deeptutor/services/construction_grading/m35_ai_governed_gold.py:11`），`LABEL_AUTHORITY="ai_governed_gold"`，3+ 独立盲投 accept → `quality_claim_allowed=true`。仲裁面板 `scripts/run_luban_arbitration_gold_panel.py` 做盲投+仲裁 reconcile（unanimous/majority_review/arbitration）。
- **权威应该是谁**：官方判分标准 + 人类教师 final 是 release truth 的 canonical authority。AI 面板共识只是**质量标签门（quality-label gate）**，不是 release truth。
- **当前有没有越权**：**已被代码硬关住**。`validate_ai_governed_gold_protocol` 返回值固定 `official_score_allowed=False / is_release_truth=False`，只放开 `quality_claim_allowed`。仲裁面板 footer 固定 `classification=candidate_only / review_status=review_only / production_write_count=0`，且 consensus 与 `reference_ledger_label` 比对（panel 不是孤立真相，要对账官方 ledger）。`m35_artifact_shadow.py` 进一步把 `quality_claim_allowed=False` 钉死在 shadow。**残余风险**：`LABEL_AUTHORITY="ai_governed_gold"` 这个命名 + `quality_claim_allowed=true` 容易被下游 reader 误读成"可当 gold 用"。这是**语义越权风险（命名层）**，不是写权越权。
- **怎么降级成投影/评审镜**：(a) 把 `quality_claim_allowed=true` 的语义在 schema 注释和下游 reader 处显式标成"label-quality only, never score authority"；(b) 任何消费 `ai_governed_gold` 的地方都要再过一次 `is_release_truth` 检查，不能只看 `quality_claim_allowed`；(c) KnowQL 的 `confidence` 维度里，AI 面板共识只能填 `verdict_ceiling`，不能填 `release_status`。

### 风险 R3（中高）· 编译 context vs 教材原文
- **AI 派生物**：rich leaf pack 每个 unit 的 `compiled_context`（concepts / exam_patterns / rules / teaching_cards / scoring_points），是编译轴对教材的重写/结构化。
- **权威应该是谁**：教材逐字原文是 canonical；compiled context 是教学投影（M34 已定性：teaching tier，非官方判分，非 answer key，无 canonical 写）。
- **当前有没有越权**：**有 provenance 但有漂移面**。每个 concept/rule 带 `source_refs`，scoring_point 带 `quote_verified`。但 `compiled_context` 里的 `rules`/`teaching_cards` 是 LLM 重写文本（如 R1 description 是改写句），不是逐字引用——如果它被当判分依据，就用"改写"替了"原文"。M34 master plan 已把 system-wide default 标 NO-GO（compiler pollution repair 未闭环）。
- **怎么降级成投影/评审镜**：(a) 判分链路只允许引用 `quote_verified=true` 的逐字 quote，`rules`/`teaching_cards` 的改写文本只能进 explanation/teaching shape，不能进 grading shape；(b) KnowQL `shape=grading` 与 `shape=explanation` 必须物理隔离可引用的字段集。

### 风险 R4（中）· 错因标签 taxonomy vs canonical
- **AI 派生物**：rich leaf 采分点的 `miss_tags`（如 `["漏列采分点"]`）、`misconception_tag`（per-point 输出字段），以及编译期生成的 mistake 标签。
- **权威应该是谁**：canonical mistake_tag schema（移动端 P0A 四个 P0 门之一，见 `docs/plan/鲁班移动端提分闭环/...viewmodel-and-event-contract.md`）+ 受控 mistake-code registry（Nexus 计划 §4.7：mistake taxonomy 的 runtime authority 是 "controlled mistake-code registry"）应是唯一来源。reference 文件 `error-taxonomy.md` / `mcq-error-taxonomy.md` 是 skill 侧 taxonomy。
- **当前有没有越权**：**有第二套 taxonomy 苗头**。编译轴自造的 `miss_tags`/`misconception_tag` 字符串是自由文本，没有强制对齐到 canonical mistake-code registry。多个 worktree 各有一份 `error-taxonomy.md` 拷贝（source↔runtime 漂移风险，参见 memory: tutorbot-skills 源↔workspace 需手动同步）。这正是 AGENTS §5.7 警告的"错因标签 taxonomy vs canonical"竞争。
- **怎么降级成投影/评审镜**：(a) 编译产出的 mistake 标签只能是 canonical registry 的 `candidate`，runtime 必须映射回 registry code，映不上的进 review queue 不直接给学员；(b) 把散落的 `error-taxonomy.md` 收敛成单一 registry authority，skill 侧引用而非各自拷贝。

### 风险 R5（中）· learner claim vs canonical learner truth
- **AI 派生物**：评分产出的 learning_evidence_event / LearnerClaim / weakness projection。
- **权威应该是谁**：`canonical_truth_policy.py` 已经把它定死——canonical learner truth 的写权由 `canonical_truth_promotion_decision` 派生，production write cohort 限 `qa_,operator_`（`CANONICAL_TRUTH_PRODUCTION_WRITE_COHORT_DEFAULT`），broad 仍需 `_broad_trusted_adjudication_enabled`+human/trusted adjudication。
- **当前有没有越权**：**关得最好的一根**。`write_compiled_learning_truth`（`deeptutor/services/learner_state/service.py:425`）先过 `canonical_truth_promotion_decision`，未授权 cohort 直接返回 projection 不落盘。reader 走 `extract_learning_brain_projection`（投影，非真相覆盖）。残余风险：AI 派生的 learner claim 在未授权 cohort 仍会算出 projection，只是不写——如果某 reader 把 projection 当 canonical 读，就越权（这是 §5.8 的 frontend projection 抢权）。
- **怎么降级成投影/评审镜**：(a) projection 与 canonical truth 在读侧必须带不同 type 标记，reader 不能把 projection 当 truth；(b) KnowQL 若暴露 learner 维度，`where` 不得让 client 指定 release/canonical 状态（§4.6 已规定 "no client-controlled release status"，须落实到 learner 侧）。

### 第二权威风险排序清单（紧凑版 + 处置摘要）

| # | 风险 | 权威应是谁 | 越权状态 | 处置（降级方向） |
|---|---|---|---|---|
| **R1** | rich leaf 5705 采分点 vs 官方 key | 官方 reference / 教材 = 判分 key | 软护栏（靠自报 flag），体量 50x 易主导 | 官方 key=primary 通道，采分点=supporting shape；install 闸由 release gate 派生 |
| **R2** | Phase3 AI 面板共识当金标 | 官方标准 + 教师 final = release truth | 写权已硬关，残**命名语义**越权 | `quality_claim` 注明 label-only；下游必查 `is_release_truth` |
| **R3** | 编译 context vs 教材原文 | 教材逐字 = canonical | 改写文本可能替原文进判分 | grading shape 只引 `quote_verified` 逐字；改写文本限 explanation shape |
| **R4** | 错因 taxonomy vs canonical | canonical mistake-code registry | 自由文本标签，多份拷贝漂移 | 编译标签=registry candidate，映不上进 review；收敛单一 registry |
| **R5** | learner claim vs canonical learner truth | `canonical_truth_policy` 派生写权 | 写权已关，残 projection 被误读为 truth | projection/truth 读侧带不同 type；client 不控 release 状态 |

---

## 任务3 · thin wrapper / single authority 合规复核（KnowQL 建设禁区）

对照 AGENTS §0 / §5.6 / §5.7，预先列出 KnowQL 建设时会诱发"第二套 authority / state / router"的冲动，每条标为**禁区**并给替代动作。

### 禁区 D1 · 禁止 KnowQL query executor 变成第二套判分 policy engine
- **冲动**：在 `retrieveRubric` 里塞 intent 解析、采分点匹配、给分判断、fallback 兜底。
- **为什么禁**（§0 / §5.7）：wrapper 不能成为第二套 policy engine。判分 policy 的 fat skill 已存在（`rubric_grader_v1.py` / `artifact_first_llm_judge.py`）。query 层一旦开始"理解答案对不对"，就造了第二套判分真相。
- **替代**：query executor 只做 deterministic filter + shape 投影 + provenance 强制，**绝不做语义判分**。判分仍下沉到既有 grader fat skill。

### 禁区 D2 · 禁止新增第二套 typed object schema
- **冲动**：KnowQL 觉得现有 `case_grading_artifact.v1` 和 `luban_rich_leaf_scoring_point_compile.v1` 都不够好，新建一个 `knowql_rubric.v1`。
- **为什么禁**（§5.6 第 4 条 + §5.7 delete-or-demote）：这会变成第三套 typed shape，三套并行漂移。一等业务事实"采分点"只能有一个 typed authority。
- **替代**：先收敛现有两套成一个 typed object authority，KnowQL 直接读它；要扩字段就扩这个唯一 schema，不新建。

### 禁区 D3 · 禁止采分点/编译 context 获得"绕过官方 key"的 canonical 写权
- **冲动**：为了"runtime 更快"，让 KnowQL 直接 install rich leaf pack 当判分 key（把 `runtime_install_allowed` 翻 true）。
- **为什么禁**（R1 + §5.7 competing authorities）：这就是第二权威落地的那一刻——AI 采分点正式和官方 key 竞争判分真相。
- **替代**：install 必须由独立 release gate 授权（非 KnowQL 自己翻 flag），且 install 后官方 key 仍是 primary confidence 通道。

### 禁区 D4 · 禁止 KnowQL 暴露 client 可控的 release/canonical 状态
- **冲动**：query 参数允许 caller 传 `release_status=published` / `canonical=true` 来"拿到更权威的结果"。
- **为什么禁**（§4.6 "no client-controlled release status" + §5.8 competing authorities）：release/canonical 状态是 deterministic 派生的，不是 client 选的。让 client 控 = 把权威决策权交给 wrapper 的调用方。
- **替代**：`where` 只接受 deterministic filter（question_id、cohort flag），release/canonical 由服务端 policy 派生。

### 禁区 D5 · 禁止造第二套 learner memory / mistake taxonomy authority
- **冲动**：KnowQL 顺手建一个"knowql learner graph"或"knowql mistake registry"来支撑查询。
- **为什么禁**（Nexus 计划 §177 已明令 + R4/R5 + §5.7）：learner truth 的唯一 authority 是 `canonical_truth_policy` + Learning Brain；mistake 的唯一 authority 是 controlled mistake-code registry。再造一套就是第二套 state。
- **替代**：KnowQL 是 consumer/projection，learner 与 mistake 维度都查既有 authority，映不上的进 review queue，不自建 registry。

### 禁区 D6 · 禁止 query 层做 prompt 拼接 / regex fallback 当主理解
- **冲动**：query 命不中就用 regex 抽字段、拼 prompt 兜底。
- **为什么禁**（§0 / §5.7：regex/fallback 只能在格式稳定+低歧义时辅助，不得承担主理解）。
- **替代**：命不中就 `confidence` 失败开放或 queue review（§4.6 已规定 "uncertain cases fail open or queue review"），不用 regex 硬抽。

### 禁区 D7 · 禁止 KnowQL 引入第二条聊天/检索 transport
- **冲动**：给 KnowQL 配专用 endpoint / WebSocket 做"rubric 查询通道"。
- **为什么禁**（§3 硬约束：`/api/v1/ws` 是唯一聊天流式入口；§5.8 transport 抢权）。
- **替代**：KnowQL 是 service 层函数契约（`retrieveRubric`），被既有 runtime 调用，不开新 transport。

### KnowQL 建设禁区（紧凑版）

| # | 禁区 | 触发原则 | 替代动作 |
|---|---|---|---|
| D1 | query executor 变第二套判分 policy engine | §0 / §5.7 | 只做 filter+shape+provenance，判分留在 grader fat skill |
| D2 | 新增第三套 typed object schema | §5.6.4 / §5.7 | 先收敛现有两套，KnowQL 读唯一 schema |
| D3 | 采分点/编译 context 拿到绕过官方 key 的 canonical 写权 | R1 / §5.7 | install 由独立 release gate 授权，官方 key 永 primary |
| D4 | client 可控 release/canonical 状态 | §4.6 / §5.8 | release 由服务端 policy 派生，`where` 只接 deterministic filter |
| D5 | 自建第二套 learner memory / mistake registry | Nexus §177 / R4 / R5 | 查既有 authority，映不上进 review |
| D6 | query 层 regex/prompt 拼接当主理解 | §0 / §5.7 | 命不中 fail open 或 queue review |
| D7 | 引入第二条聊天/检索 transport | §3 / §5.8 | KnowQL 是 service 函数契约，不开新 endpoint |

---

## 附录 · 审计证据索引（绝对路径）

- 判分合约 / output 强制 / provenance 绑定：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/run_luban_student_answer_grading_eval.py`（`enforce_output_schema`:719 / `validate_grading_output`:750 / `build_typed_case_grading_artifact`:353 / `_attach_point_provenance`:310）
- rich leaf v3.2 pack：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613/`（`runtime_token_pack_v32_scoring_points.json` 5705 点 / `scoring_point_compile_report.json` 编译报告）
- Phase3 AI 面板金标权威：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/m35_ai_governed_gold.py`（`validate_ai_governed_gold_protocol`:11）
- 仲裁金标面板：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/run_luban_arbitration_gold_panel.py`
- m35 shadow（第二判分 policy authority 警告原文）：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/construction_grading/m35_artifact_shadow.py`（:129）
- canonical learner truth 写权 policy：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/deeptutor/services/learner_state/canonical_truth_policy.py` + `service.py`（`write_compiled_learning_truth`:425）
- 已存在的 KnowQL 纸面契约：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/评分引擎与金标工件/2026-06-09-luban-nexus-like-scoring-artifact-engine-execution-plan.md` §4.6 / §4.7
- 权威纪律依据：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/AGENTS.md` §0 / §5.6 / §5.7 / §5.8
