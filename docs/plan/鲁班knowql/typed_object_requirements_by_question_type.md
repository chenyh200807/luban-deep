# 按题型的 Typed Grading Object 需求 Spec（鲁班 KnowQL）

> 角色：题型 typed-object 需求分析师（只读分析，本文件为唯一产物）。
> 题源：`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/` 下 2021–2025 真题及解析 JSON（`FINAL_CLEANED_EXAM_V{year}.json`）+ `近三年案例题_按学生答卷排版.md`。
> 完成日期：2026-06-13。

---

## 0. 贯穿铁律：单一权威 native（must-not-mint hard gate）

本 spec 设计的**每一个 typed object、每一个字段**都必须满足：

1. **有唯一 canonical 权威来源**——三类之一：
   - **A. 官方答案 key**：`exercises[i].question_data.correct_answer`（客观题是 `"D"`；案例题是逐问参考答案 blob）。这是出题方给定的判分真值，鲁班不得改写、不得新造。
   - **B. 教材 chunk + 冻结 taxonomy**：`chunk_id` + `content_markdown` + `taxonomy.node_code`，对照仓库内冻结 taxonomy `FINAL_CLEANED_TAXONOMY2026.json`（canonical，见 MEMORY）。用于把答案术语溯源回教材原文（采分点 provenance 硬约束，见 MEMORY `luban-scoring-points-must-trace-to-textbook`）。
   - **C. owner 字段**：`option_reasoning`（选项级错因，出题方给定）、`analysis`（官方解析）、`logic_chain`（出题方给定判分逻辑）、`process_stage.constraints`（案例工序约束，出题方给定）。
2. **是该权威的投影（projection），不是新权威**——typed object 的每个字段值都能用一条「派生规则」回指到 A/B/C 之一的原文 span；字段只做**结构化 / 切分 / 索引**，不得引入原文中不存在的新事实、新数值、新条文、新得分点。
3. **缺权威即 fail-closed**——找不到 A/B/C 来源的字段 = 第二权威风险，**标红 must-not-mint，不准设计进去**；运行时若某字段的权威解析失败，该字段降级为 `candidate_only` / `not_exercised`，**绝不**用编造值凑判分（对齐 `rich_leaf_artifacts.validate_*` 的 `rejected` / `blockers` 机制与 `release-gate runner attest only what it exercises`）。

> 这条铁律的代码事实依据（已落地，不是设想）：
> - `deeptutor/services/source_compiler/scoring_point_asset_compiler.py::_asset_row` 每个采分点都带 `provenance{chunk_id, content_hash, quote, anchor_verified}`，`anchor_verified` 由 `_valid_textbook_anchor(term, chunk)`（术语必须在 chunk 原文里 `normalized_contains`）决定；anchor 不 verified 的行会被 `score_status="pending_calibration_not_official"` 钉死，不进官方判分。
> - `deeptutor/services/construction_grading/rich_leaf_artifacts.py` 每个 field 携带 `source_ref_ids`，必须解析到 `source_refs[]` 注册表项（`SOURCE_REF_REQUIRED_KEYS` 含 `span` + `span_hash`），`span_hash` 不匹配 → `blockers.append("source_ref_span_hash_mismatch")`，字段被 `rejected`。**span_hash 就是「投影非新权威」的机器证明**。
> - schema `forbidden_properties = ["controlled_default","official_score_allowed","canonical_truth_written"]` + context pack `official_score_allowed const False` / `canonical_write_allowed const False`——typed object 在结构上**被禁止**自称官方真值。

**本 spec 所有新增字段，权威来源列只能填 A/B/C；填不出来的字段一律不设计（已在各表用 🔴 must-not-mint 行显式列出被拒字段）。**

---

## 1. 真实题型分布（归纳自题源）

### 1.1 客观题 + 案例题三分法（来自 `exercises[i].type`）

| `type` | 2023 | 2024 | 2025 | 判分性质 | 权威来源 |
|---|---|---|---|---|---|
| `single_choice` 客观单选 | 20 | 20 | 22 | 单 key 精确匹配 | A：`correct_answer="X"` |
| `multiple_choice` 客观多选 | 10 | 11 | 10 | 多 key 集合匹配（少选/多选规则） | A：`correct_answer="ABD"` |
| `case_study` 案例题 | 31 | 7 | 25 | 逐问采分点判分（free-text blob） | A：`correct_answer` 逐问 blob + B 教材溯源 + C `analysis`/`logic_chain`/`process_stage` |

> 客观题结构稳定、已被现有合约覆盖；**真正的 typed-object 需求集中在 `case_study`**，因为它的 `correct_answer` 是一个把多种异质子题型揉在一起的 free-text blob，没有结构化采分点切分。

### 1.2 案例题内部的真实子题型（归纳自 2023–2025 案例 `correct_answer` blob + 案例 MD）

案例题每道含 4–6 个「问题N」，每个小问属于以下子题型之一。这是**本 spec 的核心分析对象**：

| 子题型 code | 真实样例（来自题源原文） | 判分本质 | 现有覆盖 |
|---|---|---|---|
| `flaw_correction` 不妥+改正 | 「不妥之处：试验员…记录见证记录；正确做法：应由见证人员记录…」（2023 质量管理） | 成对判分：识别 flaw + 给出 correction，两半都对才得分 | 🟡 部分（`negative_evidence`，但无成对结构） |
| `enumeration` 列举/补充 | 「见证记录内容还包括：取样、制样、标识、封志、送检、现场检测」（2023） | 集合召回判分，每项独立得分，常带「多答不得分」上限 | 🟢 `scoring_point_assets`（term_exact_match list_rule） |
| `judgment_with_reason` 判断+理由 | 「不妥当。理由：建造阶段的能源总用量宜采用施工工序能耗估算法计算」（2024 绿色施工 Q4） | 判断对（前置门）+ 理由采分点 | 🟡 部分（无 judgment gate 结构） |
| `calculation` 计算+公式步骤 | 「结算价：6100+610+480+144+660=7994万元」分 6 步（2024 招投标 Q5） | 逐步公式判分：基数→中间值→终值，确定性重算 | 🟡 `scoring_point_assets` 有 `calculation{expected_values}`，但无分步 formula_steps |
| `regulation_citation` 规范条文/阈值 | 「灌注桩顶部泛浆高度不应小于500mm」「抗渗混凝土最小受冻临界强度值：20MPa」（2024 进度管理） | 条文主体+数值阈值精确匹配 | 🟢 `scoring_point_assets`（numeric + textbook anchor） |
| `network_diagram` 网络计划计算 | 「关键线路 B→E→I；工作A总时差2周；工期索赔成立」（2024 进度管理 Q1） | 关键线路/时差/索赔结论，确定性图算 | 🔴 未覆盖（新增需求） |
| `figure_labeling` 看图命名/编号 | 「图1-1-麻面；图1-2-裂缝…」「1-基础垫层；2-防水找平层」（2023 质量缺陷） | 图元位置→名称映射，逐项匹配 | 🔴 未覆盖（新增需求；且原图常缺，见 MD 注） |
| `process_sequence` 工艺流程排序/补全 | 「清理表面→支设模板→洒水湿润→涂刷界面剂→浇筑细石混凝土→保温养护≥7天」（2023 孔洞治理） | 有序步骤补全/排序，顺序敏感 | 🟡 `scoring_point_assets` 有 `content_process_step`，但无 ordered/序列约束 |
| `applicability_conditions` 适用条件 | 「低温型灌浆料施工开始24h内灌浆部位温度不低于-5℃」（2024，条件→约束） | 条件触发下的约束判分 | 🔴 未覆盖（USER#13/14 明列，新增需求） |
| `exceptions` 例外/除外 | 「将主体结构施工分包给其他单位的，**钢结构工程除外**」（2024 招投标 Q3） | 主规则 + 除外项，漏掉除外扣分 | 🔴 未覆盖（USER#13/14 明列，新增需求） |
| `responsibility_assignment` 责任主体归属 | 「A—技术；B—商务；C—工程；D—质量；E—质量」（2024 进度管理 Q3） | 项→责任主体映射，逐项匹配 | 🟡 可复用 `figure_labeling`/映射类，但语义独立 |

---

## 2. 各题型 Typed Object 字段表（含唯一权威来源列 + 投影方式 + fail-closed）

> 通用约定：所有 typed object 顶层都**强制**携带 `source_refs[]`（注册表，对齐 `SOURCE_REF_REQUIRED_KEYS`：`source_ref_id / source_dataset_id / source_version / extractor_version / path / record_id / span / span_hash`）；每个字段携带 `source_ref_ids[]` 指向它。下表「唯一权威来源」=该字段值派生自哪个 canonical span；「投影方式」=如何从原文 span 切出该字段而不新增事实；「缺权威 fail-closed」=解析失败时的降级行为。**权威列出现「无 canonical 来源」的字段一律不设计，已用 🔴 must-not-mint 单独列出。**

### 2.1 `single_choice` 客观单选 —— `ObjectiveSingleChoiceGradingObject`

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `question_id` | str | ✓ | B：`chunk_id`+exercise index | 直接引用 | 无 id → 不可判分，丢弃 |
| `correct_key` | enum[A-D] | ✓ | **A：`question_data.correct_answer`** | 直接引用单字符 | 缺 key → `not_gradeable`，走开放世界裁决（硬约束40，MCQ 兜底），不拒答 |
| `options[]` | list{key,value} | ✓ | A：`question_data.options` | 直接引用 | 缺选项 → 仅做语义判分 |
| `option_diagnostics[]` | list{key,status,error_type,explanation} | ✗ | **C：`option_reasoning`** | 逐选项引用 owner 字段 | 缺 → 不产错因诊断，不影响判分 |
| `score` | float | ✓ | A：`question_data.score`（默认 1.0） | 直接引用 | 缺 → 默认 1.0 |
| `source_refs[]` | registry | ✓ | B | chunk span + span_hash | span_hash 不匹配 → 整对象 `rejected` |
| 🔴 `inferred_difficulty_weight` | — | — | **无 canonical 来源**（`difficulty` 是标签非判分权威，加权会新造判分真值） | — | **must-not-mint：不设计** |

### 2.2 `multiple_choice` 客观多选 —— `ObjectiveMultiChoiceGradingObject`

继承 2.1，差异字段：

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `correct_keys[]` | set[A-E] | ✓ | **A：`correct_answer`** 拆字符 | 字符串切分为集合 | 缺 → 开放世界裁决 |
| `partial_credit_policy` | enum{all_or_nothing, partial_per_official} | ✓ | **A/C：官方解析里若写明「少选得部分分」则取之，否则 all_or_nothing** | 引用 `analysis` 措辞；无措辞→保守默认 | 无措辞证据 → 强制 `all_or_nothing`（保守，不臆造部分分规则） |
| 🔴 `synthetic_partial_score_table` | — | — | **无 canonical 来源**（官方未给少选分值表时自造分档=新权威） | — | **must-not-mint：不设计** |

### 2.3 `flaw_correction` 不妥+改正 —— `FlawCorrectionPoint`（USER#13/14：`flaw_correction_points`）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `point_id` | str | ✓ | 派生：hash(chunk_id+node+term)（同 `_point_id`） | 稳定 hash，非事实 | — |
| `flaw_span` | str | ✓ | **A：`correct_answer` 中「不妥之处：…」原文片段** | 切出 flaw 半句，逐字引用 | 切不出成对结构 → 该点 `candidate_only`，不计官方分 |
| `correction_span` | str | ✓ | **A：`correct_answer` 中「正确做法：…」原文片段** | 切出 correction 半句，逐字引用 | 同上 |
| `pairing` | const "flaw_AND_correction_both_required" | ✓ | 规则（投影自「两半成对」的官方排版语义） | 结构约束 | — |
| `flaw_anchor` | source_ref → 题干被否定句 | ✓ | **B/题干：`stem` 中被判为不妥的原句** | span_hash 锚定题干原句 | 锚不到题干 → flaw 无依据，`rejected` |
| `correction_authority` | source_ref → 教材/规范 chunk | ✓ | **B：教材 chunk 含正确做法条文** | `_valid_textbook_anchor` 验证 correction 术语在 chunk 原文 | anchor 不 verified → `pending_calibration_not_official`（同采分点机制） |
| `max_count` | int \| null | ✗ | **A：题干「本问题N项不妥，多答不得分」** | 引用题干约束数 | 缺 → 不设上限 |
| `score` | float \| null | ✗ | **A：`question_data.score` 摊分（仅当官方给逐点分）** | 摊分；官方未给逐点分则 null | null → `score_status=pending_calibration`，不出官方分 |
| 🔴 `auto_generated_alternative_corrections` | — | — | **无 canonical 来源**（自造「另一种正确做法」=新权威条文） | — | **must-not-mint：不设计**（开放世界裁决在 grader 运行时做近义判定，不在编译期 mint） |

### 2.4 `enumeration` 列举/补充 —— `EnumerationScoringPoint`

直接复用现有 `scoring_point_assets` 的 `list_rule{mode:term_exact_match}` 形态，补结构：

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `point_id` | str | ✓ | 派生 hash | — | — |
| `required_terms[]` | list[str] | ✓ | **A：`correct_answer` 列举项逐条** | 按分隔符切条，逐词引用 | 切不出 term → 丢弃该点 |
| `term_provenance[]` | list{term, chunk_id, quote, anchor_verified} | ✓ | **B：每个 term 必在教材 chunk 原文**（`_valid_textbook_anchor`） | per-term span 锚定 | anchor 不 verified → 该 term `pending_calibration_not_official`（MEMORY 硬约束） |
| `recall_mode` | const "set_recall_each_term_independent" | ✓ | 规则 | — | — |
| `over_answer_penalty` | enum{none, multi_answer_zero} | ✗ | **A：题干「多答不得分」** | 引用题干 | 缺 → none |
| `max_score` | float \| null | ✗ | A：官方摊分 | 摊分或 null | null → 不出官方分 |

### 2.5 `judgment_with_reason` 判断+理由 —— `JudgmentWithReasonPoint`

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `verdict` | enum{妥当, 不妥当, 成立, 不成立, 正确, 错误} | ✓ | **A：`correct_answer` 判断词原文** | 引用判断词 | 缺判断词 → `candidate_only` |
| `verdict_is_gate` | const true | ✓ | 规则（判断错则理由不得分，投影自评分惯例） | 结构约束 | — |
| `reason_points[]` | list[EnumerationScoringPoint] | ✓ | **A：「理由：…」原文** + B 教材溯源 | 复用 2.4 切条+锚定 | 同 2.4 |
| `verdict_authority` | source_ref → `analysis`/`logic_chain` | ✓ | **C：`analysis` 或 `logic_chain`** | 引用 owner 字段 | 缺 → verdict `pending_calibration` |

### 2.6 `calculation` 计算+公式步骤 —— `CalculationFormulaSteps`（USER#13/14：`formula_steps`）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `point_id` | str | ✓ | 派生 hash | — | — |
| `formula_steps[]` | list{step_no, expression, expected_value, unit} | ✓ | **A：`correct_answer` 计算式逐行**（如 `6100×10%=610万元`） | 按行切公式，逐式引用；表达式与结果均取自原文 | 切不出等式 → 该步 `candidate_only` |
| `inputs[]` | list{name, value, source} | ✓ | **A：题干给定基数** + 上一步 `expected_value` | 引用题干数 / 链接上一步 | 输入无来源 → `rejected`（禁止臆造基数） |
| `expected_final_value` | {value, unit} | ✓ | **A：`correct_answer` 末步结果** | 引用终值 | 缺 → 不出官方分 |
| `verification_mode` | const "deterministic_recalculation_required" | ✓ | 规则（同现有 `calculation.verification_mode`） | — | 重算与原文不一致 → 标 `provenance_internal_conflict`，不静默取一边 |
| `partial_credit_policy` | enum{per_step, final_only} | ✗ | **A/C：官方是否给步骤分** | 引用官方 | 无证据 → final_only（保守） |
| 🔴 `derived_intermediate_not_in_answer` | — | — | **无 canonical 来源**（补官方没写的中间步=新数值权威） | — | **must-not-mint：不设计** |

### 2.7 `regulation_citation` 规范条文/数值阈值 —— `RegulationThresholdPoint`

复用 `scoring_point_assets` 的 numeric+textbook anchor，补语义：

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `clause_subject` | str | ✓ | **A：`correct_answer` 条文主体**（如「灌注桩顶部泛浆高度」） | 引用主体短语 | — |
| `threshold` | {comparator, value, unit} | ✓ | **A：原文阈值**（`不应小于 500 mm`） | 解析比较符+数值+单位，逐字 | 解析歧义 → `candidate_only`，不猜 |
| `textbook_anchor` | source_ref → 教材/规范 chunk | ✓ | **B：阈值必在教材 chunk 原文**（`_numeric_values` + `normalized_contains`） | numeric anchor + content_hash | anchor 不 verified → `pending_calibration_not_official` |
| `match_mode` | const "subject_and_numeric_both_exact" | ✓ | 规则 | — | — |

### 2.8 `network_diagram` 网络计划计算 —— `NetworkDiagramPoint`（新增）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `critical_path` | list[node] | ✓ | **A：`correct_answer`「关键线路 B→E→I」** | 引用线路序列 | 缺 → `candidate_only` |
| `float_values[]` | list{activity, total_float, unit} | ✓ | **A：「工作A总时差2周」原文** | 逐项引用 | — |
| `claim_conclusions[]` | list{event, claim_type, verdict} | ✓ | **A：「工期索赔成立/不成立」** | 引用结论 | — |
| `diagram_authority` | source_ref → 题干网络图描述 | ✓ | **题干 `stem` 双代号网络图文字描述** | span_hash 锚定题干图描述 | 题干无图描述（图缺失）→ 整点 `not_exercised`（不可判，诚实标注，禁止凭空补图算） |
| 🔴 `recomputed_path_from_durations` | — | — | **无 canonical 来源**（题干图常缺，自行重算关键线路=新权威） | — | **must-not-mint：不设计**（仅用官方给的结论判分） |

### 2.9 `figure_labeling` 看图命名/编号 —— `FigureLabelingPoint`（新增）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `label_map[]` | list{position_id, name} | ✓ | **A：`correct_answer`「图1-1-麻面」「1-基础垫层」** | 切位置→名称对，逐对引用 | — |
| `name_provenance[]` | list{name, chunk_id, anchor_verified} | ✓ | **B：缺陷/构造名称在教材 chunk** | per-name anchor | anchor 不 verified → `pending_calibration` |
| `figure_available` | bool | ✓ | **题源元数据**（MD 多处注明「源 JSON 未包含图1原始图片」） | 引用题源注记 | 图缺 → `figure_available=false`，该题按文字参考答案判，标注「无图凭据」 |
| `match_mode` | const "position_to_name_exact" | ✓ | 规则 | — | — |
| 🔴 `vision_inferred_label` | — | — | **无 canonical 来源**（图缺时用视觉模型补标=新权威） | — | **must-not-mint：不设计** |

### 2.10 `process_sequence` 工艺流程排序/补全 —— `ProcessSequencePoint`

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `ordered_steps[]` | list{step_no, step_text} | ✓ | **A：`correct_answer` 工序步骤**（含已给的首尾锚点） | 切步骤，保序引用 | 切不出步骤 → `candidate_only` |
| `step_provenance[]` | list{step_text, chunk_id, anchor_verified} | ✓ | **B：工序在教材 chunk**（`content_process_step`） | per-step anchor | anchor 不 verified → `pending_calibration` |
| `order_sensitivity` | enum{strict_order, set_only} | ✓ | **A：题干是否要求「流程/顺序」** | 引用题干措辞 | 措辞不明 → set_only（保守，不强加顺序扣分） |
| `fixed_anchors[]` | list{step_text, position} | ✗ | **A：题干已给的首/尾步** | 引用题干锚点 | — |

### 2.11 `applicability_conditions` 适用条件 —— `ApplicabilityCondition`（USER#13/14：`applicability_conditions`）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `condition` | str | ✓ | **A：`correct_answer` 条件子句**（「低温型灌浆料施工开始24h内」） | 引用条件短语 | 切不出条件 → `candidate_only` |
| `required_constraint` | {subject, comparator, value, unit} | ✓ | **A：条件下的约束**（「温度不低于-5℃」） | 引用约束 | — |
| `condition_authority` | source_ref → 教材/规范 chunk | ✓ | **B：条件+约束在教材原文** | anchor_verified | 不 verified → `pending_calibration` |
| `scope` | const "constraint_holds_only_when_condition_true" | ✓ | 规则 | — | — |
| 🔴 `generalized_condition` | — | — | **无 canonical 来源**（把特定条件推广到一般情形=新权威） | — | **must-not-mint：不设计** |

### 2.12 `exceptions` 例外/除外 —— `ExceptionClause`（USER#13/14：`exceptions`）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `base_rule` | str | ✓ | **A：`correct_answer` 主规则**（「主体结构施工分包给其他单位的」） | 引用主规则 | — |
| `exception_items[]` | list[str] | ✓ | **A：除外项原文**（「钢结构工程除外」） | 切除外项，逐字引用 | 切不出除外 → 该规则按无例外判（不臆造例外） |
| `exception_authority` | source_ref → 法规/教材 chunk | ✓ | **B：除外项在法规/教材原文** | anchor_verified | 不 verified → `pending_calibration` |
| `scoring_effect` | const "miss_exception_loses_point" | ✓ | 规则（投影自评分惯例：漏除外扣分） | — | — |
| 🔴 `inferred_additional_exceptions` | — | — | **无 canonical 来源**（补官方没列的除外=新权威条文） | — | **must-not-mint：不设计** |

### 2.13 `responsibility_assignment` 责任主体归属 —— `ResponsibilityMappingPoint`（新增）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `assignment_map[]` | list{item, responsible_party} | ✓ | **A：`correct_answer`「A—技术；B—商务」** | 切项→主体对，逐对引用 | — |
| `party_provenance[]` | list{responsible_party, chunk_id, anchor_verified} | ✓ | **B：责任主体名在教材/法规 chunk** | per-party anchor | 不 verified → `pending_calibration` |
| `match_mode` | const "item_to_party_exact" | ✓ | 规则 | — | — |

### 2.14 案例题容器 —— `CaseStudyGradingObject`（顶层组合）

| 字段 | 类型 | 必填 | 唯一权威来源 | 投影方式 | 缺权威 fail-closed |
|---|---|---|---|---|---|
| `case_id` | str | ✓ | B：`chunk_id` | 引用 | — |
| `sub_questions[]` | list{sub_no, sub_type, points[]} | ✓ | **A：`correct_answer` 按「问题N」切分** | 切小问，每小问选 §2.3–§2.13 之一 typed | 切不出小问 → 整案 `candidate_only`，走开放世界整卷裁决 |
| `total_score` | float | ✓ | **A：`question_data.score`** | 引用 | — |
| `process_constraints[]` | list[str] | ✗ | **C：`process_stage.constraints`** | 引用 owner | 缺 → 空 |
| `official_analysis` | str | ✗ | **C：`question_data.analysis`** | 引用 owner | 缺 → 空 |
| `source_refs[]` | registry | ✓ | B | chunk span+hash | 任一小问 anchor 失败 → 该小问降级，不污染其他小问 |

---

## 3. 真实题目 Typed Object 填充样例（官方 key 派生，演示「投影非新权威」）

### 样例 1：`flaw_correction` —— 2023 质量管理（`EXAM_1A434000_P0010_02`，官方 score 7.0）

官方 `correct_answer` 原文片段（权威 A）：
> ① 不妥之处：试验员如实记录了其取样、现场检测等情况，制作了见证记录。正确做法：应由见证人员记录其取样、现场检测情况，制作见证记录。

```json
{
  "point_id": "sp_<hash(EXAM_1A434000_P0010_02|1A434000|flaw_correction|试验员记录见证记录)>",
  "sub_type": "flaw_correction",
  "flaw_span": "试验员如实记录了其取样、现场检测等情况，制作了见证记录",
  "correction_span": "应由见证人员记录其取样、现场检测情况，制作见证记录",
  "pairing": "flaw_AND_correction_both_required",
  "flaw_anchor": {"source_ref_id": "sr_stem_01", "path": "...V2023.json", "record_id": "EXAM_1A434000_P0010_02", "span": "试验员如实记录了其取样、现场检测等情况，制作了见证记录", "span_hash": "<sha256(normalized span)>"},
  "correction_authority": {"source_ref_id": "sr_kb_57号令", "record_id": "<教材chunk_id>", "span": "见证记录应由见证人员填写", "span_hash": "<...>", "anchor_verified": true},
  "max_count": 2,
  "score": null,
  "score_status": "pending_calibration_not_official"
}
```
投影证明：`flaw_span`/`correction_span` 都是 `correct_answer` 原文逐字切片；`correction_authority.anchor_verified=true` 表示「应由见证人员记录」这条做法**在教材 chunk 原文里存在**（不是鲁班新造）。`score=null` 因官方未给逐点分 → fail-closed 不出官方分。

### 样例 2：`calculation` formula_steps —— 2024 招投标 Q5（`EXAM_1A432000_P0015_01`，官方 score 22.0）

官方 `correct_answer` 原文（权威 A）：
> 措施项目费：6100×10%=610万元 … 结算价：6100+610+480+144+660=7994万元。

```json
{
  "point_id": "sp_<hash(EXAM_1A432000_P0015_01|1A432000|calculation|结算造价)>",
  "sub_type": "calculation",
  "formula_steps": [
    {"step_no": 1, "expression": "6000+100", "expected_value": 6100, "unit": "万元"},
    {"step_no": 2, "expression": "6100×10%", "expected_value": 610, "unit": "万元"},
    {"step_no": 3, "expression": "268+119+90", "expected_value": 480, "unit": "万元"},
    {"step_no": 4, "expression": "(6100+610+480)×2%", "expected_value": 144, "unit": "万元"},
    {"step_no": 5, "expression": "(6100+610+480+144)×9%", "expected_value": 660, "unit": "万元"},
    {"step_no": 6, "expression": "6100+610+480+144+660", "expected_value": 7994, "unit": "万元"}
  ],
  "inputs": [
    {"name": "分部分项工程费基数", "value": 6000, "source": "stem"},
    {"name": "规费费率", "value": 0.02, "source": "stem"},
    {"name": "税率", "value": 0.09, "source": "stem"}
  ],
  "expected_final_value": {"value": 7994, "unit": "万元"},
  "verification_mode": "deterministic_recalculation_required",
  "partial_credit_policy": "per_step",
  "source_refs": [{"source_ref_id": "sr_ans_q5", "record_id": "EXAM_1A432000_P0015_01", "span": "结算价：6100+610+480+144+660=7994万元", "span_hash": "<...>"}]
}
```
投影证明：每个 `expression`/`expected_value` 都来自 `correct_answer` 同名等式；`inputs[].source="stem"` 锚回题干给定基数；`verification_mode` 要求确定性重算（6100+610+480+144+660=7994 自洽）。无任何「补官方没写的中间步」字段（🔴 已拒）。

### 样例 3：`exceptions` —— 2024 招投标 Q3（`EXAM_1A432000_P0015_01`，官方 score 22.0 内子点）

官方 `correct_answer` 原文（权威 A）：
> （2）将主体结构的施工分包给其他单位的，钢结构工程除外；

```json
{
  "point_id": "sp_<hash(EXAM_1A432000_P0015_01|1A432000|exceptions|主体结构分包)>",
  "sub_type": "exceptions",
  "base_rule": "将主体结构的施工分包给其他单位的",
  "exception_items": ["钢结构工程除外"],
  "exception_authority": {"source_ref_id": "sr_kb_分包", "record_id": "<法规chunk_id>", "span": "主体结构施工不得分包，钢结构工程除外", "span_hash": "<...>", "anchor_verified": true},
  "scoring_effect": "miss_exception_loses_point",
  "source_refs": [{"source_ref_id": "sr_ans_q3", "record_id": "EXAM_1A432000_P0015_01", "span": "将主体结构的施工分包给其他单位的，钢结构工程除外", "span_hash": "<...>"}]
}
```
投影证明：`base_rule` + `exception_items` 都是 `correct_answer` 原句切片；`exception_authority.anchor_verified=true` 表示「钢结构工程除外」这条例外**在法规/教材原文存在**。无 `inferred_additional_exceptions`（🔴 已拒，不补官方没列的除外）。

---

## 4. 现有 v3.2 pack / 判分合约覆盖 vs 新增需求（gap）

> 现有事实依据：`deeptutor/services/source_compiler/scoring_point_asset_compiler.py`（采分点资产，schema `luban_scoring_point_assets.v0.1`）、`deeptutor/services/construction_grading/rich_leaf_artifacts.py`（rich-leaf v0，含 `CORE_FIELD_FAMILIES` / `TASK_FIELD_FAMILIES["grading"]`）、`rubric_grader_v1.py`（确定性求和 + `source_refs` 投影）。

| 题型 / 子题型 | 现有覆盖 | 复用的现有结构 | gap / 新增需求 |
|---|---|---|---|
| `single_choice` | 🟢 已覆盖 | `objective_answer_key_compiler` + `objective_grader` | 无（`correct_key` 已是 A 权威） |
| `multiple_choice` | 🟢 已覆盖 | 同上 | 仅需补 `partial_credit_policy` 保守默认（不臆造少选分档） |
| `enumeration` | 🟢 已覆盖 | `scoring_point_assets.list_rule{term_exact_match}` + `provenance.anchor_verified` | 仅需把「多答不得分」上限结构化 |
| `regulation_citation` | 🟢 已覆盖 | `scoring_point_assets`（numeric + `_valid_textbook_anchor`） | 仅需把 `{comparator,value,unit}` 拆细 |
| `process_sequence` | 🟡 部分 | `scoring_point_assets.content_process_step` | **新增 `order_sensitivity` + `ordered_steps` 序列约束** |
| `calculation` formula_steps | 🟡 部分 | `scoring_point_assets.calculation{expected_values}` | **新增 `formula_steps[]` 分步结构 + `inputs[].source`（USER#14）** |
| `flaw_correction` | 🟡 部分 | rich-leaf `negative_evidence` | **新增成对 `flaw_span/correction_span` + `pairing` gate（USER#13）** |
| `judgment_with_reason` | 🟡 部分 | — | **新增 `verdict_is_gate` 前置门结构** |
| `applicability_conditions` | 🔴 未覆盖 | — | **全新（USER#13/14 明列）：`condition`→`required_constraint`** |
| `exceptions` | 🔴 未覆盖 | — | **全新（USER#13/14 明列）：`base_rule`+`exception_items`** |
| `network_diagram` | 🔴 未覆盖 | — | **全新：`critical_path/float_values/claim_conclusions`，图缺时 `not_exercised`** |
| `figure_labeling` | 🔴 未覆盖 | — | **全新：`label_map`，且 `figure_available` 处理「源 JSON 无原图」** |
| `responsibility_assignment` | 🟡 部分 | 可借映射类 | **新增项→主体映射语义** |
| 案例容器 `CaseStudyGradingObject` | 🔴 未覆盖 | rubric_grader_v1 grade free-text，但**无逐小问 typed 切分** | **全新：把单一 `correct_answer` blob 切成 typed `sub_questions[]`，每小问选对应 typed object** |

### 4.1 横切结构性 gap（最关键）

1. **采分点逐点分缺权威**：题源 `question_data.score` 只有**整题总分**（如案例 7.0 / 22.0），**官方没有逐小问、逐采分点的分值表**。因此所有 typed point 的 `score`/`max_score` 现状只能 `null` + `score_status="pending_calibration_not_official"`。任何「自造逐点分摊」= 🔴 must-not-mint（新判分权威）。逐点分必须走独立的 human/AI-governed 标注通道（仓库已有 `m35_ai_governed_gold` / `scoring_point_recall_calibration`），不在编译期 mint。

2. **图类题 provenance 断链**：案例 MD 多处注明「源 JSON 未包含图1原始图片」。`figure_labeling` / `network_diagram` 的题干图权威**物理缺失**，必须 fail-closed 为 `figure_available=false` / `not_exercised`，按文字参考答案判并诚实标注「无图凭据」，**禁止**用视觉/重算补图（已在各表 🔴 列出）。

3. **rich-leaf v0 的 grading 家族缺这 4 个新族**：现有 `TASK_FIELD_FAMILIES["grading"]=("rubric_link_index","rules","numeric_constraints","negative_evidence","source_refs")` 没有 `flaw_correction_points / applicability_conditions / exceptions / formula_steps`。落地时应作为新 field family 扩进 grading task，**复用现有 `source_ref_ids`+`span_hash` 校验机制**（不新造 provenance 通道），由 `validate_rich_leaf_artifact` 对新族同样跑 `source_ref_span_hash_mismatch` → `rejected` 的 fail-closed。

---

## 5. 落地建议（不在本任务范围，仅标注衔接点，供后续 PRD）

- 新 typed object 必须挂进 `rich_leaf_artifacts.py` 的 `TASK_FIELD_FAMILIES["grading"]` 作为新 field family，**复用** `SOURCE_REF_REQUIRED_KEYS` + `span_hash` 校验，不开新 provenance 通道。
- 案例 blob → `sub_questions[]` 的切分器是新增编译步骤；切分本身是结构化（投影），但**逐小问 typed 归类**需 LLM 辅助 → 必须把归类结果标 `candidate_status="candidate"`，经 review 才 `release_candidate`（对齐现有 candidate 状态机）。
- 逐点分值校准走现有 `scoring_point_recall_calibration` / `m35_ai_governed_gold`，与本 spec 的结构化解耦：本 spec 只负责「采分点是什么 + 从哪来」，分值是另一条独立 authority。

---

## 附录：权威来源代号速查

| 代号 | canonical 来源 | 字段路径 | 含义 |
|---|---|---|---|
| A | 官方答案 key | `exercises[i].question_data.correct_answer` / `correct_answer` 单字符 / `options` / `score` | 出题方给定判分真值 |
| B | 教材 chunk + 冻结 taxonomy | `chunk_id` + `content_markdown` + `taxonomy.node_code`，对照 `FINAL_CLEANED_TAXONOMY2026.json` | 采分点术语溯源（anchor_verified） |
| C | owner 字段 | `option_reasoning` / `analysis` / `logic_chain` / `process_stage.constraints` | 出题方给定的错因/解析/逻辑/约束 |
| 🔴 | must-not-mint | — | 无 A/B/C 来源，第二权威风险，不设计 |
