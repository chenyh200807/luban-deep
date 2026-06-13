# 统一判分对象 Canonical Schema — `luban_grading_object.v1`（KnowQL Phase A）

> Status: `Design + landed (candidate / review-only)` — 2026-06-13
> 角色：统一判分对象 schema 设计师（消除"双 schema 漂移" = 审计 R1 同类的第二权威风险）。
> 本文是 governing spec。代码实现：
> - schema 定义 + 校验器：`deeptutor/services/construction_grading/unified_grading_object.py`
> - 现存 schema → 统一 schema 适配器：`deeptutor/services/construction_grading/grading_object_adapters.py`
> - 测试：`tests/services/construction_grading/test_unified_grading_object.py`
> 权威依据：`AGENTS.md` §0 / §5.6 / §5.7；蓝图 `KNOWQL_BUILDOUT_BLUEPRINT.md` §3 Phase A；审计 `current_state_gap_and_second_authority_audit.md` 任务1 ①（双 schema 待收敛）+ 禁区 D2（禁止第三套 schema）。
> **本文不替代** master plan，也不开新 transport，不授任何 official-score / canonical-write 权。

---

## 0. 一句话结论

判分对象此前散在 **8 套并行 typed shape**，同一概念用不同字段名（`weight`↔`max_score`、`canonical_answer`↔`statement`↔`label`↔`answer_key`），谁 canonical 没在代码固定 = 双（多）schema 第二权威（审计任务1 ①）。本文把它们收敛到 **唯一 canonical schema `luban_grading_object.v1`**：同一概念一个字段名 + 同一套 `span_hash` 投影证明 + 同一套 `authority_source` 权威标注，差异部分用同对象上的可选 typed variant 字段表达（不新建命名，遵守禁区 D2）。全部 8 套现存 shape 都有确定性适配器映射进来，零字段丢失、零语义静默改写；真实数据（M31 客观记录、1612 个 rich-leaf v3.2 单元共 5705 采分点、39 行 gold panel）全部 map-in 且 validator 零 blocker。

---

## 1. 现存判分/采分点/typed object schema 全量盘点（读代码确认真实字段名）

| # | schema 名 | 真实位置 | 分值字段 | 陈述字段 | provenance 机制 | 权威标注字段 | 逐点分 |
|---|---|---|---|---|---|---|---|
| 1 | `case_grading_artifact.v1` | `scripts/run_luban_student_answer_grading_eval.py::build_typed_case_grading_artifact` | 子问 `max_score` + 点 **`weight`** | **`canonical_answer`** | `provenance.{gold_ref,source_ref,sourced,source_authority,textbook_quote}` | `provenance.source_authority`(`textbook`/`unsourced`) | `weight`（编译期摊分，section_score/n） |
| 2 | `luban.rich_leaf_artifact.v0` + v3.2 pack `compiled_context.scoring_points[]` | `deeptutor/services/construction_grading/rich_leaf_artifacts.py` + `artifacts/.../runtime_token_pack_v32_scoring_points.json` | `max_score`(=null) | **`statement`** | `provenance.{chunk_id,quote,quote_verified,source_authority}` + 顶层 `source_refs[]`（`span_hash`） | `source_authority`,`claim_status`,`policy_type` | null（candidate_only） |
| 3 | `luban_scoring_point_assets.v0.1` | `deeptutor/services/source_compiler/scoring_point_asset_compiler.py::_asset_row` | `max_score`(=null) | **`label`** + `required_terms[]` | `provenance.{chunk_id,content_hash,quote,anchor_verified}` | `score_status`(`pending_calibration_not_official`),`anchor_source`(`textbook`/`calculation`) | null（pending） |
| 4 | `luban_m31_governed_objective_pointer.v1` records | `deeptutor/services/construction_grading/runtime_supply/v3_objective_records_released_m31/objective_answer_key_release_candidate_m31.json` | 无逐点（整题） | **`answer_key`** | `answer_key_hash`/`stem_hash`/`content_hash`/`options_hash` | `answer_key_authority`,`official_answer_role`(`seed_corroboration_only_not_authority`) | n/a |
| 5 | `luban_arbitration_gold_panel.v1` rows | `scripts/run_luban_arbitration_gold_panel.py` → `artifacts/.../gold_panel.json` | 无（裁决标签） | `point_id` + verdict | `reference_ledger_label`,`consensus_matches_reference` | `route`,`consensus_verdict`,`panel_unanimous`；`safety.*_write=false` | n/a |
| 6 | `m35_ai_governed_gold.v1` | `deeptutor/services/construction_grading/m35_ai_governed_gold.py::validate_ai_governed_gold_protocol` | 无 | 无 | `source_anchor.{source_ref_count,field_level_citations}` | `label_authority="ai_governed_gold"`,**`official_score_allowed=False`**,`is_release_truth=False` | n/a |
| 7 | `compact_scoring_artifact.v1` | `scripts/run_luban_student_answer_grading_eval.py::build_compact_scoring_artifact` | 子问 `max_score` | **`expected_points[]`** | `source_chunks[]` | 无显式（隐含 official restructure） | `max_score`=official `score` |
| 8 | `luban_per_question_grading_object.v1` | `deeptutor/services/construction_grading/per_question_grading_object.py`（确定性编译器，另一并行 agent 的 demo 后端） | `official_total_score` + 点 `score`(=null) | **`atomic_official_slice`** | `span_hash`(逐点) + `term_provenance[].{chunk_id,span_hash,anchor_verified}` | **`authority_source`**(`official_answer_verbatim`/`textbook_cited`/`owner`/`pending_calibration`),`score_authority` | null（`pending_calibration_not_official`） |

> #8（`per_question_grading_object.v1`）已经是 authority-native（它率先用 `official_answer_verbatim`/`textbook_cited`/`owner`/`pending` + 逐点 `span_hash`），所以统一 schema 的 `authority_source` 词表直接采它的方向，只做规范化重命名。本文**不修改** #8 源文件（它是另一并行 agent 的 WIP）。

### 1.1 字段漂移对照表（每处不一致明确点名）

| 概念 | #1 case_artifact | #2 rich_leaf | #3 sp_assets | #4 m31_objective | #5 gold_panel | #7 compact | #8 per_question | **canonical（v1）** |
|---|---|---|---|---|---|---|---|---|
| **分值** | `weight`(点)/`max_score`(子问) | `max_score` | `max_score` | — | — | `max_score` | `score` | **`max_score`** |
| **采分点陈述** | `canonical_answer` | `statement` | `label` | `answer_key` | — | `expected_points[]` | `atomic_official_slice` | **`statement`** |
| **官方答案引用** | `gold_ref` | `source` | （隐含） | `answer_key` | `reference_ledger_label` | `source_chunks` | `atomic_official_slice` | **`authority_source=official_answer`** |
| **教材依据** | `provenance.source_ref` | `provenance.chunk_id` | `provenance.chunk_id` | — | — | — | `term_provenance[].chunk_id` | **`term_provenance[].chunk_id` + `authority_source=textbook_cited`** |
| **投影证明 span_hash** | ✗（仅 sourced bool） | ✓(顶层 source_refs) | ✗（content_hash） | ✗（answer_key_hash） | ✗ | ✗ | ✓（逐点 + 逐 term） | **`span_hash`（逐点强制）** |
| **命中状态** | （runtime `status`） | — | — | — | `consensus_verdict` | — | — | **`hit_status`** |
| **权威来源标注** | `source_authority` | `source_authority`/`claim_status` | `score_status`/`anchor_source` | `answer_key_authority`/`official_answer_role` | `route`/`consensus_matches_reference` | （无） | **`authority_source`** | **`authority_source`（4 值枚举）** |
| **逐点分缺权威默认** | 摊分（有漂移风险） | null | `pending_calibration_not_official` | n/a | n/a | official | `pending_calibration_not_official` | **null + `pending_calibration`（must-not-mint）** |

漂移要害：#1 把"陈述"叫 `canonical_answer`、把"分值"叫 `weight` 还编译期摊分（最容易被读成第二判分权威）；#3 叫 `label`；#4 叫 `answer_key`。同一概念 4 个名字 = reader 必须人记，查询语言被迫同时支持多套形状（审计 ② 的返工源）。

---

## 2. 统一 canonical schema：`luban_grading_object.v1`

### 2.1 核心字段表（题型族共享，含 authority 列）

对象顶层：

| 字段 | 类型 | 必填 | 含义 | authority 列 |
|---|---|---|---|---|
| `schema_id` | const `luban_grading_object.v1` | ✓ | schema 锁 | — |
| `object_id` | str | ✓ | 题/叶 id | — |
| `question_type` | enum{`objective`,`calculation`,`standard_clause`,`case`} | ✓ | 题型族 | — |
| `official_total_score` | number\|null | ✓ | 整题官方总分 | `official_total_score_authority` const `official_answer` |
| `authority_source` | enum（4 值） | ✓ | 对象级权威来源 | 本身即 authority 列 |
| `scoring_points[]` | array<point> | ✓ | 采分点 | 逐点带 authority |
| `official_score_allowed` | const `False` | — | **结构锁：不能自称官方真值** | — |
| `canonical_write_allowed` | const `False` | — | **结构锁：不能自称 canonical 写** | — |

每个 `scoring_points[]`（core，所有 variant 共享）：

| 字段 | 类型 | 必填 | 含义 | **authority 列** |
|---|---|---|---|---|
| `point_id` | str | ✓ | 稳定点 id | — |
| `statement` | str | ✓ | **唯一**采分点陈述（消 `canonical_answer`/`label`/`answer_key`/`atomic_official_slice`） | — |
| `authority_source` | enum{`official_answer`,`textbook_cited`,`owner`,`pending_calibration`} | ✓ | 该点权威来源 | **本字段** |
| `span_hash` | str\|null | ✓ | 投影证明：span-backed 权威 = sha256(statement)；`pending_calibration` = null | 绑定 authority |
| `max_score` | number\|null | ✓ | **唯一**分值名（消 `weight`） | 受 `score_authority` 约束 |
| `score_authority` | str | ✓ | 逐点分权威；默认 `pending_calibration_not_official` | **must-not-mint 闸** |
| `hit_status` | enum{`hit`,`partial`,`miss`,`contradiction`,`not_evaluated`} | ✓ | 命中状态（消 `consensus_verdict`） | — |
| `required_terms[]` | list[str] | ✗ | 关键术语 | 逐 term 在 `term_provenance` |
| `term_provenance[]` | list{chunk_id,anchor_verified,authority_source,quote} | ✗ | 教材逐 term 溯源；未命中 = `chunk_id:null`+`unsourced`（不伪造） | 逐 term authority |

variant 可选字段（同对象，按 `question_type`/`sub_type` 出现，不新建命名）：
- objective：`options{key:value}`、`correct_keys[]`
- calculation：`formula_steps[]`、`expected_final_value{value,unit}`
- standard_clause：`threshold{comparator,value,unit}`、`clause_subject`
- case 子型：`sub_type`、`flaw_span`/`correction_span`/`pairing`、`base_rule`/`exception_items[]`

### 2.2 单一权威 native 三条硬不变量（校验器强制）

1. **每字段带 `authority_source`**（4 值枚举之一）；缺/未知 → reject。
2. **`span_hash` = 投影证明**：span-backed 权威（`official_answer`/`textbook_cited`/`owner`）的点必须带 `span_hash == sha256(statement)`，否则 reject（不是投影就别存）；`pending_calibration` 点**禁止**带 span_hash（没在投影任何东西）。
3. **`official_score_allowed const False` + must-not-mint**：对象结构上不能自称官方真值；`pending_calibration` 点**禁止携带 `max_score`**（逐点分默认 pending，不自造分摊）；drift 字段名（`weight`/`canonical_answer`/`answer_key`/`label`）出现即 reject（强制规整）。

---

## 3. 现存 schema → 统一 schema 映射表（迁移/适配，不丢字段、不静默改语义）

| # | 现存 schema | 适配器 | 关键重命名/规整 | authority 推导 | 覆盖验证 |
|---|---|---|---|---|---|
| 1 | `case_grading_artifact.v1` | `map_case_grading_artifact` | `canonical_answer`→`statement`；`weight` 丢弃（逐点分回落 pending） | `provenance.sourced` → `textbook_cited`/`pending_calibration` | ✓ fixture |
| 2 | rich_leaf v3.2 pack | `map_rich_leaf_unit` / `map_rich_leaf_scoring_point` | `statement` 保留；`policy_type`→`sub_type` | `provenance.quote_verified` → `textbook_cited`/`pending` | ✓ **1612 单元 / 5705 点真实数据零 blocker** |
| 3 | `luban_scoring_point_assets.v0.1` | `map_scoring_point_assets` | `label`→`statement`；`calculation.expected_values`→`formula_steps` | `provenance.anchor_verified` → `textbook_cited`/`pending` | ✓ fixture |
| 4 | M31 governed objective record | `map_objective_answer_key_record` | `answer_key`→`statement`；`options`/`correct_keys` 进 objective variant | 官方 key → `official_answer`（不授 score） | ✓ **真实 record 零 blocker** |
| 5 | `luban_arbitration_gold_panel.v1` row | `map_gold_panel_row` | `consensus_verdict`→`hit_status` | **`pending_calibration`**（面板=质量标签，非 release truth） | ✓ **39 行真实数据零 blocker** |
| 6 | `m35_ai_governed_gold.v1` | （非采分点对象；以 `authority_source` const + `official_score_allowed=False` 对齐，不需 point 映射） | — | label-only，永不 score | 语义对齐（见 §4 R2） |
| 7 | `compact_scoring_artifact.v1` | `map_compact_scoring_artifact` | `expected_points[]`→ 逐 `statement` | official restructure → `official_answer` | ✓ fixture |
| 8 | `luban_per_question_grading_object.v1` | `map_per_question_grading_object` | `atomic_official_slice`→`statement`；`official_answer_verbatim`→`official_answer` 等词表规整 | 直接采其 `authority_source` 词表 | ✓ fixture |

**映射表覆盖率：8/8 现存 shape 全部有迁移路径**；其中 7 套有可执行确定性适配器（#6 是 protocol-level 质量门，非逐点对象，靠 const-flag 语义对齐），`ADAPTER_REGISTRY` 登记 7 个。真实数据覆盖：M31 客观 + 全量 1612 rich-leaf 单元（5705 点，正是审计 R1 的第二权威体量）+ 全部 39 gold-panel 行，validator 零 blocker。

---

## 4. 互相可用契约（互用 = 同一份字段契约读任意对象）

任何消费方——grader / 未来 KnowQL 查询层 / learner brain——用**同一份 core 字段契约**读 objective / case / scoring-point 任意一种对象：

- **读分值**：永远 `point.max_score`（不再分 `weight`/`max_score`/`score`）。
- **读陈述**：永远 `point.statement`（不再分 `canonical_answer`/`label`/`answer_key`/`atomic_official_slice`/`expected_points`）。
- **读权威**：永远 `point.authority_source`；只有 `official_answer` 是 primary 判分 key，`textbook_cited` 是 supporting，`pending_calibration` 不参与官方给分（对齐审计 R1 处置：官方 key=primary，采分点=supporting shape）。
- **读命中**：永远 `point.hit_status`。
- **读溯源**：永远 `point.span_hash`（投影证明）+ `point.term_provenance[]`（逐 term 教材锚，未命中诚实标 `unsourced`+`chunk_id:null`）。

### 对齐第二权威风险处置（审计任务2）

- **R1**（rich leaf 5705 采分点 vs 官方 key）：映入后 5705 点的 `authority_source` 全部是 `textbook_cited`/`pending_calibration`，**结构上不可能是 `official_answer`**——官方 key 永远 primary，采分点退为 supporting。校验器拒绝任何 pending 点携带 `max_score`（must-not-mint）。
- **R2**（m35 AI 面板 / gold panel 共识）：`map_gold_panel_row` 把面板 verdict 落成 `hit_status` 但 `authority_source=pending_calibration`、`max_score=null`——**质量标签 only，永不 score**，与 `m35_ai_governed_gold.official_score_allowed=False` 同构。

### KnowQL 建设禁区遵守（审计任务3）

- **D2（禁止第三套 schema）**：本文不是第三套——它**收敛** 8 套为 1 套，并提供把全部 8 套读进来的适配器；扩字段只扩这唯一 schema。
- **D3（采分点不得拿绕过官方 key 的 canonical 写权）**：`official_score_allowed`/`canonical_write_allowed` 结构 const False，pending 点禁带分。
- 校验器只做 deterministic filter + 结构强制，**不做语义判分**（D1）；不开 transport（D7）；不建第二套 learner/mistake registry（D5）。

---

## 5. 验收证据

- schema + 校验器：`deeptutor/services/construction_grading/unified_grading_object.py`
- 适配器（7）：`deeptutor/services/construction_grading/grading_object_adapters.py`
- 测试：`tests/services/construction_grading/test_unified_grading_object.py`（27 passed）—— 含 validator happy path、每条单一权威 reject、7 套现存 schema 样例 map-in + validate
- 真实数据 map-in：M31 客观 record、1612 rich-leaf 单元 / 5705 点、39 gold-panel 行 → validator 零 blocker
- ruff check / format：clean；contract-guard：no protected domains changed（passed）

## 6. 下一步（不在本任务，标衔接点）

- Phase B：把 `enforce_output_schema`（现 eval）提升为本 schema 的 runtime 方法，shape 由对象自己强制。
- `per_question_grading_object.v1` 编译器（#8，并行 agent demo 后端）后续 conform 本 schema：直接 emit `luban_grading_object.v1`，或经 `map_per_question_grading_object` 适配。
- KnowQL 查询层（Phase C）建在本唯一 schema 上，`retrieveRubric` 只读本 schema 字段。
