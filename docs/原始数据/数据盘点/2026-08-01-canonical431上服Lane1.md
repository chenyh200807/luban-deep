# canonical-431 采分点上服 Lane 1：编译 + 验证 + 签发候选

- 日期：2026-08-01
- 分支：`chenyh200807/feat-canonical431-bank-lane1`（从 `origin/main@e0b3029e0` 起）
- 阶段：**Lane 1 = 只编译 + 验证 + 签发候选**。**没有切生产**：没注册 slot、没翻 `production_authorized`、没改判分核代码、没碰数据库、没发 turn。
- claim level：**E2（确定性编译 + 17 条可重跑断言全绿 + 与金标 v2 逐点交叉核对）**。**不是**「判得准已改善」——本轮没跑过任何判分器，判分质量一个数都没测。
- 产物：
  - 编译器 [`scripts/build_luban_canonical431_case_rubric_bank.py`](../../../scripts/build_luban_canonical431_case_rubric_bank.py)（确定性、可重跑、`--dry-run` / `--verify` 三态）
  - bank 候选 `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_canonical431/`
    （`case_rubric_scored_canonical431.json` + `canonical_pointer.json` + `validation_report.json`）

---

## 0. 一句话结论

431 采分点已编译成 governed bank 候选 **`canonical431` slot**，键 = `{case_group_id}::E{case_subquestion_index}`，**每条采分点都带 per-小问真实满分**（不是均分）——这正是踩点封顶要的分母权威。

**但三条硬事实必须先看，否则第二波会拿一个 48% 可达的库去宣称 100% 覆盖：**

1. **2022 全年 110 点被隔离**：佑森抽的是**补考卷**，questions_bank 里是**正考卷**，题面实证是两张卷子。挂上去 = 用错卷答案判分。431 里能上服的是 **321 点 / 96 小问**。
2. **可达率 50/96（52%）**：整题行按 C2 契约 `case_subquestion_index` 留空，`::E{n}` 对它们恒不命中。**2024 全年 5 道案例、25 个小问一个都够不着**。
3. **tier-1 今天根本不用这个键**：`_grade_one_case_v1` 只按 `ctx["question_id"]` 平查一个字符串；`case_group_id` 在 RAG 边界就被丢掉了，从没进过判分核。**不接线，这个库装上去也是零命中**（§4）。

---

## 1. 弹药源与编译口径

### 1.1 源

| 项 | 值 |
|---|---|
| 源文件 | `extractions/case_rubric_canonical.json`（`_meta.built_at=2026-06-16`） |
| 规模 | **431 采分点 / 117 小问 / 25 案例 / 5 年**（2021、2022补考、2023、2024、2025） |
| 分值权威 | `training_org_analysis_yousen`，**`NOT_official: true`** — 佑森培训机构解析估分，官方分点口径不公开 |
| 质量背书 | 真题 PDF 视觉核查逐点分值（0.5 粒度）+ 5 份独立专家 agent 复核（仅 2024 漏 1 字已订正） |
| 判分规则 | `小题得分 = min(Σ命中采分点×point_score, sub_q_total_score)` 封顶 |
| 逐点字段 | `seq` / `text` / `score` / `type` / `page`（+ 少量 `_ocr_suspect` 原样保留） |

`type` 分布（431 点全量）：列举 238、判断 61、改错 51、计算步骤 33、计算结果 20、程序 13、措施 12、分类 3。

### 1.2 键的选择与理由

```
qid = "{case_group_id}::E{case_subquestion_index}"     例：2021-case1::E1
```

选它而不选裸 chunk 键，理由是**权威同源**：

- `case_group_id` / `case_subquestion_index` 是 C2（2026-08-01）回填进 `public.questions_bank` 的**题级归属唯一权威键**（`contracts/rag.md §45`），C3 已让 RAG 按 `case_group_id` 取全组、并把 index 投成 `covered_subquestions[].display_index`（`supabase.py:3197-3433`）。
- legacy bank 的 `EXAM_1A413000_P0012_02::E0` 里那个 `E{n}` 是**编译期 0-based `exercises[]` 序数**，与运行时 1-based `display_index` **没有共享权威**。这不是推测：`loop.py:2122-2136` 已构造过 `{exam_year}::{source_chunk_id}::E{display_index}` 复合键，模拟 join 命中 **23/354、语义正确 0 条**，全部错绑到相邻小问的 rubric，因此该键只作为观测 marker 导出、**从不进 `ctx.question_id`**。

**本 bank 的 `E{n}` 一律是 1-based `case_subquestion_index`，与 DB / `display_index` 同权威。** 这条不变量由断言 V6 守住（每条记录的 `qid` 尾部 E 必须逐字等于该记录的 `subquestion_index`，头部必须逐字等于 `case_group_id`）。

### 1.3 逐记录 schema

命名先查了注册表：既有 `SCHEMA_VERSION` 有 `luban_rubric_compiler.v1`（legacy）与 `luban_case_rubric_scored_pgo.v1`（pgo），故本 lane 取 **`luban_case_rubric_canonical431.v1`** / namespace `case_rubric_scored_canonical431`，不与任何既有 namespace 撞名。

```jsonc
{
  "qid": "2021-case1::E1",              // {case_group_id}::E{1-based index}
  "point_id": "2021-case1::E1::p1",
  "text": "不妥之一:要求分包单位与招用的建筑工人签订劳务合同",
  "score": 1.0,                          // 佑森逐点真实分值(0.5 粒度)
  "policy": "boolean_judgment",
  "required_terms": [],
  "case_group_id": "2021-case1",
  "question_no": 1, "subquestion_index": 1, "point_seq": 1,
  "official_total_score": 4.0,           // ★ per-小问真实满分 = 踩点封顶的分母权威
  "official_total_score_authority": "training_org_analysis_yousen",
  "score_authority": "training_org_analysis_yousen",
  "per_point_score_authority": "training_org_analysis_yousen",
  "answer_key_authority": "training_org_analysis_yousen",
  "point_pool_total": 4.0,               // 该小问 Σ点分
  "judging_rule": "min(Σ命中采分点×point_score, sub_q_total_score) 封顶",
  "sub_type": "判断", "factory_point_type": "判断",
  "source_schema": "luban_case_rubric_canonical431.v1",
  "exact_term_required": false,
  "textbook_source_refs": [ /* chunk_id / node_code / provenance_class / quote_snippet / strong */ ],
  "textbook_traced": true, "textbook_traced_strong": false,
  "source_year": 2021, "source_case_no": 1, "source_page": 17,
  "source_authority": "training_org_analysis_yousen", "NOT_official": true
}
```

三条设计取舍值得记：

1. **字段名迁就 `by_q` 白名单，不新造名字。** `rubric_grader_v1` 的 `_rubric_bank()` 只把一张**固定 key 白名单**（`rubric_grader_v1.py:1476-1495`）透传到运行时 point，白名单外的字段**一律丢弃**。因此 per-小问满分复用已在白名单里的 `official_total_score`，而不是新造 `subquestion_nominal_score`（那样会被静默丢掉）。代价是字段名带 "official" 而权威是佑森——用**同条记录上的 `official_total_score_authority` 显式声明 NOT official** 来抵消，不靠字段名承载权威。
2. **零 `exact_required`。** 佑森 `point_text` 是整句解析文本、不是规范术语单点；`exact_required` 是二值无部分分，误判代价是「答对意思判 0 分」。宁可全部 `qualitative`/`list` 起步，也不预埋误杀。断言 V8 守住「裸 exact_required = 0」。
3. **`policy` 映射保守**：判断→`boolean_judgment`；改错→`qualitative`；列举/分类/程序/措施→`list`；计算结果/计算步骤→`calc`。取值域对齐 `rubric_grader_v1._VALID_POLICIES`（断言 V7）。

---

## 2. 覆盖对账

### 2.1 全量守恒

| 项 | 数 |
|---|---|
| 源采分点 | **431** |
| 进 `records`（可上服） | **321** |
| 进 `quarantined`（2022 隔离） | **110** |
| 守恒 | 321 + 110 = **431**，一个不多一个不少（断言 V2） |
| 小问数 | 源 117 → 可上服 **96** |
| 案例组 | 源 25 → 可上服 **20** |
| `point_id` 唯一性 | 321 / 321（断言 V9） |
| `content_hash` | `9ce1e83016cfd1d2…`（`_sha256_hex(records)`，与 manifest、pointer 三方一致，断言 V10） |

逐年（非隔离）：

| 年 | 小问 | 采分点 | Σper-小问满分 | Σ点池 |
|---|---|---|---|---|
| 2021 | 25 | 85 | 120.0 | 120.0 |
| 2023 | 23 | 89 | 120.0 | 117.0 |
| 2024 | 25 | 67 | 122.0 | 122.0 |
| 2025 | 23 | 80 | 118.5 | 119.0 |
| **合计** | **96** | **321** | **480.5** | **478.0** |

policy 分布（321 点）：`list` 197、`calc` 43、`qualitative` 43、`boolean_judgment` 38、`exact_required` **0**。

### 2.2 2022 为什么整年隔离（这是本轮最重要的一次拦截）

佑森 2022 的抽取源文件名就是答案：`2022bukao_jianzhu_case_rubric.jsonl` — **补考卷**。而 `questions_bank` 的 `2022-caseN` 行是**正考卷**。题面实证：

| | DB（`mapping.jsonl` 的 `q_head`） | 佑森 2022 rubric 首点 |
|---|---|---|
| `2022-case1` E1 | 补充表1-1中A~G处的信息内容。 | `"1"注册建造师,1人` |
| `2022-case1` E2 | 分别写出配套工程1F、2F、3F柱C40混凝土同条件养护试件的等效龄期（d）和日平均气温累计数（℃·d）。 | (1)直径10mm钢筋:重量偏差不合格 |
| `2022-case5` E1 | 施工企业安全生产管理制度内容还有哪些？ | (1)混凝土工程容易发生:①高空坠落 |
| `2022-case5` E3 | 混凝土浇筑过程的安全隐患主要表现形式还有哪些？ | (1)不妥之处:①水管直接埋地穿过临时道路 |

两张卷子，不是抽取误差。`per_question_score_backfill.jsonl` 的 `_meta` 早已因同一理由把 2022 排除（`"years": [2021, 2023, 2024, 2025]`，注 `2022正考≠抽取补考跳过`）。

**订正 C1 的一条结论**：`reconciliation_vs_yousen.json` 把 `2022-case2/3/4/5` 判为「✅覆盖齐」——那只是**小问个数对得上**，不是内容对得上。C1 自己的诚实边界里也写了「未核 DB 2022 是正考还是补考」。本轮核了：**是正考，佑森是补考，不能挂**。

隔离方式：110 点进 `bundle.quarantined`（不进 `records`、不进 `content_hash`），逐点带 `quarantine_reason`。断言 V3 守住「records 内 2022 点数 = 0」。

### 2.3 已知的 2 处缺口（如实标注）

C1 对账登记的两处缺口在本轮原样保留、未编造补齐：

- **`2022-case1` 问3** — 佑森有 E3，DB 只有 index 1、2。**本轮因整年隔离，此缺口暂时无意义**。
- **`2023-case4` 问6** — 佑森有 E6（6.0 分、3 个采分点），DB 的 `case_subquestion_index` 只到 5。bank 里 `2023-case4::E6` **有记录但不可达**（见 §2.4）。

### 2.4 键可达性：50/96（52%）——本轮最该被主控看见的数字

`::E{n}` 只能命中 `case_subquestion_index` 非空的行。按 C2 契约，**整题行（`case_row_granularity='whole_question'`）的 index 必须留空**，所以 `::E{n}` 对整题行**恒不命中**。这不是 bug，是键的适用边界。

| | 小问数 |
|---|---|
| 可上服（非隔离） | 96 |
| **运行时可达** | **50** |
| **不可达** | **46** |

不可达明细：

| 组 | 不可达 E | DB 有 index 的行 | 整题行 span |
|---|---|---|---|
| `2021-case2` | [5] | [1,2,3,4] | [[1,5]] |
| `2021-case3` | [1,2,3,4] | — | [[1,4]] |
| `2021-case4` | [1,2,3,4,5,6] | — | [[1,6]] |
| `2021-case5` | [1,2,3,4] | [5] | [[1,5]] |
| `2023-case4` | [6] | [1,2,3,4,5] | — |
| `2024-case1` ~ `2024-case5` | 各 [1,2,3,4,5] | — | 各 [[1,5]] |
| `2025-case2` | [1,2,3,4,5] | — | [[1,5]] |

**2024 全年 25 个小问、67 个采分点，一个都够不着。** 这与 C1 的发现一致：2024 全年 5 道案例在库里都是整题行。

解药是**整题行 bundle 接线**（§4.3），不是改键——改键（比如退回 chunk 键）会把已实测「语义正确 0 条」的错绑病请回来。为此 bank 旁挂了 `whole_case_index`（`{case_group_id}` → 该组全部 qid，升序），给第二波直接用；它**不进 `records`**，所以不参与 `content_hash`，改它不动摇 bank 身份。

---

## 3. 分值账本：每问 nominal 表

### 3.1 这张表是干什么的

`official_total_score` = 该小问的真实满分，是**踩点封顶的分母权威**。它要替换的是今天的均分：`deep_question.py:2583`

```python
per_sub_nominal = round(float(nominal_full_score) / total, 4) if total > 0 else 0.0
```

文档字符串自己写明了：「每问名义满分 = 整题名义满分 / 题面小问数（**均分**——questions_bank 行不带 per-问分值）」。**这个 bank 的存在就是为了让那句话不再成立。**

均分错得有多离谱，看 `2023-case4`：整题 30 分 / 6 问，均分 = 5.0；真实是 `2.0 / 5.0 / 5.0 / 6.0 / 6.0 / 6.0`。E1 的真实满分只有 2 分，均分给它 5 分上限 —— 一个只答对 E1 的学生，最多能被给到 5 分而不是 2 分。

### 3.2 样例（两组全量）

`2023-case3`（全 4 问可达，整题 20 分）：

| qid | nominal | 点池 | 点数 | 池vs满分 | 可达 |
|---|---|---|---|---|---|
| `2023-case3::E1` | 5.0 | 5.0 | 7 | exact | ✅ |
| `2023-case3::E2` | 5.0 | 5.0 | 2 | exact | ✅ |
| `2023-case3::E3` | 5.0 | 5.0 | 5 | exact | ✅ |
| `2023-case3::E4` | 5.0 | 5.0 | 5 | exact | ✅ |

`2024-case1`（整题 20 分，**全 5 问不可达**）：

| qid | nominal | 点池 | 点数 | 池vs满分 | 可达 |
|---|---|---|---|---|---|
| `2024-case1::E1` | 5.0 | 5.0 | 1 | exact | ❌ 整题行 |
| `2024-case1::E2` | 4.0 | 4.0 | 2 | exact | ❌ |
| `2024-case1::E3` | 4.0 | 4.0 | 2 | exact | ❌ |
| `2024-case1::E4` | 3.0 | 3.0 | 2 | exact | ❌ |
| `2024-case1::E5` | 4.0 | 4.0 | 4 | exact | ❌ |

注意 `2024-case1` 的真实分布是 `5/4/4/3/4` —— 均分会给每问 4.0，E1 少 1 分、E4 多 1 分。

全量 96 行在 `validation_report.json` 的 `nominal_table` 与 bank 的 `nominal_table`。

### 3.3 池 vs 满分：**「池>满分是常态」这条前提不成立**

主控给的任务书写「池>满分是常态」。实测**不是**：

| 关系 | 小问数 |
|---|---|
| 点池 **==** 满分 | **91**（94.8%） |
| 点池 > 满分 | 2 |
| 点池 < 满分 | 3 |

佑森的逐点分值绝大多数**正好加成小问满分**。这是源数据质量的一个正面信号，也意味着「封顶」在 95% 的小问上不会真的触发——真正的杠杆是**分母从均分换成真值**，不是封顶本身。

5 处例外（全部登记，`under` 三处提示抽取可能漏点，需人审）：

| qid | 点池 | 满分 | |
|---|---|---|---|
| `2023-case1::E4` | 6.0 | 5.0 | over |
| `2025-case5::E4` | 8.0 | 6.0 | over |
| `2023-case4::E5` | 5.0 | 6.0 | **under（疑漏点）** |
| `2023-case5::E4` | 3.0 | 6.0 | **under（疑漏点）** |
| `2025-case5::E5` | 4.5 | 6.0 | **under（疑漏点）** |

### 3.4 分母的外部校验：2 个案例组的满分走样（新发现）

佑森是唯一分值来源，自己校自己等于没校。本轮引入**唯一一条不来自佑森的锚**——一建·建筑实务卷面结构：**案例一~三各 20 分，案例四~五各 30 分，合计 120**。

用它压 20 个案例组的 Σper-小问满分：

| 案例组 | Σnominal | 卷面 | 差 |
|---|---|---|---|
| `2024-case3` | 22.0 | 20.0 | **+2.0** |
| `2025-case5` | 28.5 | 30.0 | **−1.5** |
| 其余 18 组 | — | — | 0（全对上） |

2021 与 2023 逐年 Σ=120.0 完全吻合；2024 因 case3 走样 Σ=122.0，2025 因 case5 走样 Σ=118.5。

**顺带订正 INDEX 的一条待办**：「核案例 sub_q 总分结构（案例四/五 Σ>20——踩点制 or 分值结构）」——答案是**分值结构**：案例四/五官方就是 30 分，不是踩点制溢出。18/20 组精确吻合即为证。

**处置**（不是「发现了就算」）：这 2 组的每条记录都打了 `nominal_authority_disputed: true` + `nominal_dispute_detail`，manifest 里有 `nominal_drift_pending_adjudication`。**任何未来的封顶消费方必须能对这些记录 fail-closed 拒用分母**——拿一个走样的满分去封顶，比不封顶更危险。断言 V16 要求「实测偏离集合 == manifest 声明集合 == 记录打标集合」三者逐字相等，V17 反向守住「没偏离的组不许带争议标」（防止把标当万能免责声明滥用）。

**盘外提醒**：金标 v2 的 `Q2024-03` 正是 `2024-case3`，其 `rubric_total_score` 记的是 **22.0** —— 金标继承了同一处走样。若用它算「满分率」，分母偏大 10%。

---

## 4. tier-1 接线设计（**本轮不实现**，供第二波）

### 4.1 今天的真相：tier-1 在案例判分上事实上是死的

- `_grade_one_case_v1` 在 `deeptutor/capabilities/deep_question.py:2636`（**不在** `rubric_grader_v1.py`）。
- 唯一一次 bank 读取是 `deep_question.py:2660`：`points = _G.load_rubric(qid) if qid else []`，`qid = ctx["question_id"]`。
- `load_rubric` 是**平查一个字符串**：`rubric_grader_v1.py:1508` `return _rubric_bank().get(str(qid), [])`，索引只按 `r["qid"]` 建（`:1500`）。**没有任何 case_group_id / index 参与查表。**
- `case_group_id` 在 RAG 边界就被丢掉：全仓只有 `supabase.py` 用它取全组，`deep_question.py` / `rubric_grader_v1.py` **一次都没引用过**。
- 结果：几乎所有案例轮落 tier-2（`on_the_fly_reference`）或 tier-3（`derived_from_stem`）。

**所以：装上这个 bank ≠ tier-1 生效。不接线，命中率是 0。**

### 4.2 最小接线切片（把 `case_group_id::E{n}` 送进 `ctx.question_id`）

四步，全部在 `loop.py` 的 ctx 构造侧，**不改 `rubric_grader_v1` 判分核**：

1. **透传**：`_hydrate_case_group_bundle` 已把 `case_group_id` 写到 `exact_question` 顶层（`supabase.py:3299`），`covered_subquestions[].display_index` 已是 `case_subquestion_index`（`supabase.py:3240-3268`）。把这两个字段一路带到 `_build_v1_case_ctx`。
2. **构键**：对**每个实际采纳的小问**（`_current_case_reference_from_context` 的 `matched_indexes`，`loop.py:1564-1663`）构 `f"{case_group_id}::E{index}"`。注意是**逐小问一个键**，不是整题一个键 —— 这是本 bank 与 legacy 的形制差别。
3. **fail-closed 前置断言**：只有当 `case_group_id` 非空**且** `display_index` 来自 DB `case_subquestion_index`（不是从题干正则解析的 `_display_index`）时才允许构键。这条是硬的：`loop.py:2122-2136` 的历史教训就是拿正则解析的 index 去对编译期序数，23/354 命中、**语义正确 0 条**。**索引来源必须可证，不可证就不构键。**
4. **发声**：命中/未命中都写 marker（`case_rubric_bank_slot`、`case_rubric_key`、`case_rubric_hit`），进 trace。没有 marker 的降级等于没发生过。

### 4.3 per-问 nominal 怎么进 finalize（把均分换成真值）

今天的封顶链路（`rubric_grader_v1.py:2330-2392`）是两级串联：内层 per-小问 `subquestion_caps`，外层整题 `nominal × scope_ratio`。而 **tier-1 被显式排除在 finalize 之外**（`deep_question.py:2914` `if provenance != "compiled_rubric":`），理由是 `cg.max_score` 来自 V0 文本解析、不够可信。

有了本 bank 之后，那条理由消失了 —— **分母不再需要从题面解析，它在记录里**。建议：

```python
# _grade_one_case_v1，tier-1 分支内（第二波实现，本轮不写）
if provenance == "compiled_rubric":
    # 每个 q{n} 的真实满分直接来自记录，不做除法
    subquestion_caps = {
        f"q{p['subquestion_index']}": float(p["official_total_score"])
        for p in points
        if p.get("official_total_score") and not p.get("nominal_authority_disputed")
    }
    # 整题分母 = 实际采纳小问的真实满分之和（不是「整题满分 × 覆盖比」）
    nominal = sum(set_of_distinct_subq_nominals)
    _G.finalize_case_score(event, nominal_full_score=nominal,
                           scope_ratio=1.0, subquestion_caps=subquestion_caps)
```

四条要点：

- **`subquestion_caps` 的 key 形制必须是 `q{n}`**，且 `n` 与 `_question_group_key` 分出来的组名一致。`_question_group_key`（`rubric_grader_v1.py:1808-1818`）优先读 point 的 `subquestion_index` / `question_no` —— 本 bank 两个都填了 1-based index，所以分组会走显式字段，**不会**掉进那个把 0-based E 序数当 1-based 问号读的 `::E(\d+)` 正则兜底。这是本 bank 相对 legacy 的一个直接修复。
- **`scope_ratio` 应设 1.0**，因为分母已经只算实际采纳的小问了。再乘一次覆盖比 = 双重缩放（这正是 P0 兜底满分那一族的病根形态）。
- **`nominal_authority_disputed` 必须 fail-closed 排除**（`2024-case3` / `2025-case5`）：这些组的分母对不上卷面，宁可退回旧路径也不用走样的满分封顶。
- **`normalize_points_to_nominal` 在 tier-1 上必须不调用**。它把点池缩放到名义满分，是 P0「全中即满分是结构性必然」的直接成因；本 bank 的点分是真值，缩放只会毁掉它。

### 4.4 整题行的 46 个不可达小问怎么办

`whole_case_index` 已备好 `{case_group_id}` → 全组 qid。对 `case_row_granularity='whole_question'` 的命中行，取整组 qid 的全部采分点作为一个 bundle，分母 = 全组 Σnominal（对 `2024-caseN` 就是 20/20/20/30/30）。这条**不建议与 4.2 同批做** —— 先让 50 个可达小问跑出 live 证据，再扩面。

---

## 5. 与判分金标 v2 的交叉验证

三题 `Q2023-03` / `Q2024-03` / `Q2025-03` → `2023-case3` / `2024-case3` / `2025-case3`，逐点比对 `point_text` / `point_score` / `sub_q_total_score`：

| 金标题 | 映射 | 金标点数 | bank 点数 | 差异 |
|---|---|---|---|---|
| `Q2023-03` | `2023-case3` | 19 | 19 | **0** |
| `Q2024-03` | `2024-case3` | 11 | 11 | **0** |
| `Q2025-03` | `2025-case3` | 13 | 13 | **0** |
| 合计 | | **43** | **43** | **0** |

**诚实边界（这条比结果重要）**：金标 v2 的采分点骨架取自**同一批** `extractions/{year}_jianzhu_case_rubric.jsonl`，所以这是**守恒校验，不是独立信源核对**。它能抓的是「编译器在搬运途中丢点 / 串行 / 分值走样 / per-小问满分错配」；抓不到的是佑森源本身的错。真正独立的那一条外部校验是 §3.4 的卷面结构锚 —— 而它**抓到了 2 处**。

---

## 6. 验证断言（17 条，全绿，可重跑）

```
python scripts/build_luban_canonical431_case_rubric_bank.py --verify
```

| # | 断言 | 结果 |
|---|---|---|
| V1 | 源账 431 点 / 117 小问 / 25 案例 | PASS |
| V2 | 全量守恒 records 321 + quarantined 110 = 431 | PASS |
| V3 | records 内 2022 点数 = 0 | PASS |
| V4 | 池vs满分关系全登记（exact 91 / over 2 / under 3） | PASS |
| V5 | 每条记录都带 >0 的分母 + 分值权威非空 | PASS |
| V6 | 键形制：1-based E，E == `subquestion_index`，头 == `case_group_id` | PASS |
| V7 | policy 合法（对齐 `_VALID_POLICIES`） | PASS |
| V8 | 裸 `exact_required` = 0 | PASS |
| V9 | `point_id` 321/321 唯一 | PASS |
| V10 | `content_hash` 三方一致（records / manifest / pointer） | PASS |
| V11 | **pointer 与 manifest 均 `production_authorized: false`** | PASS |
| V12 | 未污染 legacy / pgo slot | PASS |
| V13 | 教材溯源覆盖登记：119/321（37.1%），strong 49 | PASS |
| V14 | 可达性登记：可达 50 / 不可达 46 / 共 96 | PASS |
| V15 | 金标 v2 逐点交叉 43 条，差异 0 | PASS |
| V16 | 满分走样：实测偏离 == manifest 声明 == 记录打标（三集合逐字相等） | PASS |
| V17 | 未偏离的组不带争议标 | PASS |

编译器 `--dry-run` / 落盘两条路径都跑 **同一套断言**，且**断言不全绿拒绝落盘**（fail-closed）。

---

## 7. 签发候选与切换清单

`canonical_pointer.json`：

```json
{
  "namespace": "case_rubric_scored_canonical431",
  "slot": "canonical431",
  "status": "release_candidate",
  "published": false,
  "expected_content_hash": "9ce1e83016cfd1d2…",
  "production_authorized": false
}
```

**编译器里没有把 `production_authorized` 写成 `true` 的代码路径。** 这是 Lane 1 的硬边界，不是口头承诺。

`rubric_grader_v1._load_bank_slot` 的三道闸（`rubric_grader_v1.py:1384-1438`）现状：

| 闸 | 状态 |
|---|---|
| `manifest.content_hash == _sha256_hex(records)` | ✅ 已满足 |
| `canonical_pointer.expected_content_hash == actual` | ✅ 已满足 |
| `pointer.production_authorized is True` | ❌ **故意为 false** — 装载会被治理闸拒绝并回落 legacy（这是设计的期望行为） |

**关于「签发闸 --kind」**：查过了，仓内 `--kind` 只存在于 `scripts/publish_luban_preview_cards.py:2426` 与 `docs/原始数据/考点原料/promote_variant_bank.py:293`（`_BANK_KINDS` 收敛），那是**考点卡 / variant bank 的签发闸，不覆盖 rubric bank lane**。rubric bank 适用的签发闸就是上表那三道 + `_RUBRIC_BANK_SLOTS` 注册，本报告按后者交付。**不给这个 lane 编造一个不存在的 `--kind`。**

主控切换需要做的（本轮一件都没做）：

1. 在 `rubric_grader_v1._RUBRIC_BANK_SLOTS` 注册 `"canonical431": ("v_case_rubric_scored_canonical431", "case_rubric_scored_canonical431.json")`。
2. 打通 tier-1 键（§4.2）—— **没有这一步，切了也是零命中**。
3. per-问 nominal 进 finalize（§4.3）。
4. 把 pointer 的 `production_authorized` 翻 `true` 并写授权注记。
5. live 回归 ≥3 轮（单一权威收口 playbook）。

---

## 8. 诚实边界

- **判分质量一个数都没测。** 本轮没跑过任何判分器、没发 turn、没建账号。「采分点吻合 0.44→1.0」是**目标不是结果**。
- **分值权威是佑森培训机构解析，`NOT_official`。** 不是官方评分细则。已逐记录声明。
- **教材溯源只覆盖 119/321（37.1%），strong 49（15.3%）。** 复用 `enrich_rubric_textbook_provenance.py` 的匹配器，`required_terms` 为空所以只有短语通道生效。**没有为了凑覆盖率去放宽阈值** —— 一个弱/假的教材引用比没有引用更危险。202 条无溯源的点 `textbook_traced: false`，可查可补。
- **`2024-case3` / `2025-case3` 的组归属未回 PDF 人工核。** 沿用 C1 的 `case_no` 推导（页序），而 `contracts/rag.md §45(a)` 已把 `case_group_id` 冻成不可变 id —— 若日后发现页序推导有误，只能新开组 id，不能重排。
- **C1 的 14 组「背景互不为子串」静默风险未消解**（C2 报告 §盘外②）。本 bank 直接用了 `case_group_id`，继承这份风险。
- **可达性用的是 C1 的 2026-08-01 只读快照**，不是本轮新查的 live DB（本进程无 DB 凭据）。C2 之后若有人再改过这四列，可达数会变。
- **2022 的 110 点没有丢，只是隔离**。补到正考 rubric 源后可单独立案上服。

---

## 9. 你没问但必须说的

1. **这个库今天装上去命中率是 0**，因为 tier-1 从来不用 `case_group_id` 键。「编译好弹药」和「弹药能上膛」是两件事，第二波（§4.2）才是真正解开三病的那一步。别把 Lane 1 全绿读成「判得准修好了」。
2. **可达率 52% 是天花板，不是执行不力。** 46 个够不着的小问全部卡在「整题行 index 必须留空」这条 C2 契约上，其中 2024 全年整年不可达。要覆盖它们必须做整题行 bundle（§4.4），那是独立一战。
3. **「池>满分是常态」这条任务书前提被实测推翻**（95% 是精确相等）。所以踩点封顶本身不是主要杠杆，**分母从均分换成真值才是**。若第二波只上封顶不换分母，预期收益很小。
4. **发现 2 处满分走样，其中一处已经污染了金标 v2**（`Q2024-03` 的 `rubric_total_score=22.0`，卷面是 20.0）。任何用金标算满分率的地方，`Q2024-03` 的分母偏大 10%。这条建议同步给金标维护方。
5. **`official_total_score` 这个字段名带 "official" 而权威是佑森**，是被 `by_q` 白名单逼出来的妥协（§1.3）。它是一个真实的误读风险面：将来若有人只看字段名不看 `official_total_score_authority`，就会把佑森估分当官方口径。**建议第二波把白名单扩一个 `subquestion_nominal_score` 并迁移**，别让这个妥协长期存在。
6. **共享 worktree 风险（已处置）**：本轮全程在 `gar` 共享 worktree，期间 `rubric_grader_v1.py` / `loop.py` / `langfuse_adapter.py` / `sync_to_aliyun.sh` 有并行 agent 的未提交改动。本次 commit **只 add 自己的三条路径**，未用 `-a`、未用 `add -A`。**本报告所有代码行号已改为对 `git show origin/main:` 的干净副本重新定位**（`deep_question.py` 的 2583/2660/2914 在两侧逐字相同；`rubric_grader_v1.py` 因他人改动有约 44 行偏移，已按 `origin/main` 订正）。这条值得记进方法论：**在共享脏树里写报告，行号必须对 `origin/main` 复位，否则交付出去的引用会指错行。**
