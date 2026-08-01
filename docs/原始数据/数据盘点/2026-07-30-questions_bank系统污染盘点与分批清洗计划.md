# questions_bank 系统污染盘点与分批清洗计划

- **日期**: 2026-07-30
- **状态**: `read_only_investigation + 待审阅执行计划`。调查阶段**未执行任何写操作**；文中所有 SQL 均为草案，**尚未运行**。当日另有三行已删（见 §7），系本次计划之前的独立动作。
- **数据快照**: Supabase `zgupgizexqpwtajvghno` / `public.questions_bank`，REST 只读全量拉取，`total = 4635 行`（`12865` / `9035` / `9037` 三行已确认不在表中，本统计已反映删除后状态）
- **结论一句话**: 2051 行命中至少一个污染信号；**主污染源是一次整批重复入库（449 行 / id 17059–17509），不是散点脏数据**；但真正的风险不是脏字段，而是**删除是无保护动作**（全库无 FK、无软删），已产生 73 个悬挂引用，其中当日删的 `12865` 落在正在服务的 active 试卷里。

---

## 范围与方法

| 项 | 值 |
|---|---|
| 数据面 | Supabase `zgupgizexqpwtajvghno` / `public.questions_bank`，REST 只读全量拉取（4635 行） |
| 消费面 | 代码侧调研：RAG 精确/向量/全文检索、测评组卷、轻练直出、下游快照表 |
| 家族键 | `question_stem` 规范化后完全相等（去空白、去`【题干】`/`【问题】`/`【背景资料】`标记、去中英标点、去首部编号） |
| 逐行产物 | `inventory.json`（2051 行污染清单）、`backup_all_affected.json`（这 2051 行全字段备份，除 `embedding`/`tsv`/`tsv_content` 派生列）、`duplicate_families.json`（530 家族 keep/drop 裁决）、`reference_remap.json`（190 条 drop→keep 映射）、`batches.json`（各批次精确 id 清单） |
| 写操作 | **0**（调查阶段） |

---

## 1. 主污染源：一次整批重复入库（449 行）

`original_id` 形如 `EXAM_<年份>_<node_code>_<hash>` 的 **449 行（id 17059–17509）** 是一次 re-ingest 批次。逐行比对：

| 检查项 | 结果 |
|---|---|
| 有 stem 完全相同的批外孪生行 | **439 / 449** |
| 该批次贡献了任何批外行没有的字段值 | **0 个字段，0 行** |
| 答案比孪生行更长/更完整 | **0 行**（401 行等长、38 行更短或为空） |
| 有 `source_chunk_id` | **0 / 449**（孪生行 365/439 有） |
| 有 `analysis` | 437/449（孪生行 439/439 有） |

即：这批 439 行是**严格劣化的副本**，且同时是 `correct_answer` 污染的主要载体（50 个"答案丢失"行里 **42 个**在这批）。删掉它一次性解决前期审计第 1、4 两类污染的大部分。

---

## 2. 污染分类总账

`inventory.json` 每行带 `pollution[]`（可多重命中）、`downstream_reachable[]`、`disposition[]`。

| 类别 | 命中行数 | 含义 |
|---|---:|---|
| `DUP_drop` | 590 | 重复家族里的非正主行 |
| `CA1_empty` | 20 | `correct_answer` 为空 / `[]` / `[""]` |
| `CA2_placeholder` | 30 | 占位指针（`见参考答案`/`见答案解析`/`参考答案见下文`/`见答案页`/`见解析`） |
| `CA3_optfiller_only` | 11 | 答案与解析**双双**只剩伪造的`【选项分析】`ABCD 样板 → 答案完全丢失 |
| `CA4_meta_only` | 7 | 答案是"本题考查…"元评论或生成器套话，不含答案 |
| `CA5_optfiller_leak` | 20 | 答案正文真实，但尾部混入`【选项分析】`样板 |
| `CA6_jieshi_prefix` | 8 | 答案带`【解析】`前缀但正文确实是答案（保守判定：**不算内容污染**，只算格式债） |
| `CA7_ruledump` | 550 | `correct_answer == analysis ==` 机器规则转储（`【参考关键词】`/`【判定逻辑】`/`【系统规则代码】`），全部来自 `TEXTBOOK_ASSESSMENT` |
| `AN1_analysis_lost` | 15 | `analysis` 100% 是伪造`【选项分析】`样板 |
| `AN2_fabricated_optblock` | 161 | `analysis` 正文真实 + 尾部伪造`【选项分析】`（该题**没有选项**） |
| `AN3_analysis_empty` | 633 | `analysis` 为空（629 case_study + 4 single_choice） |
| `CH1_cross_year_chunk` | 111 | 45 个 `source_chunk_id` 被跨年份复用 |
| `CH2_same_year_chunk` | 7 | 3 个 `source_chunk_id` 在同一年份被不同题复用 |
| `SIB1_backfillable` | 254 | 兄弟小问组内 chunk 覆盖不齐 |
| `SIB2_group_all_null` | 50 | 整组兄弟小问 chunk 全 NULL |

**与前期审计口径的对齐（含修正）**：

- "`correct_answer` 污染 ~35 行" → 实测**严重级（答案丢失/无答案）共 68 行**（CA1 20 + CA2 30 + CA3 11 + CA4 7），其中 **44 行会随重复删除自动消失**，净需人工处理 **24 行**。
- "`analysis` 污染 ~443 行" → 实测含`【选项分析】`共 **440 行**，但其中 **264 行是有真实选项的选择题，`【选项分析】`是合法的高质量内容，不是污染**。真正污染的是 **176 行无选项 case_study**（15 行全样板 + 161 行样板尾巴）。
- "跨年 chunk 冲突 46 处" → 现为 **45 处**（当日删除 3 行后）。
- "兄弟小问 chunk 全 NULL" → 去重后收敛为 **21 组 / 75 行覆盖不齐 + 9 组 / 40 行整组全 NULL**。

---

## 3. 显式订正两条旧结论

> 按盘点纪律第 6 条留痕：以下两条**前期审计的判断是错的**，本次逐行比对推翻。

### 3.1 `9502 / 9518 / 8978 / 8979 / 8980` **不是重复家族**

它们是**同一道 2023 案例题的问题 1 / 问题 2 / 问题 3 / 问题 4** —— 共享同一段`【背景资料】`，但设问不同、答案不同。**不可删。**
（旧结论把"背景资料相同"当成了 stem 重复。真正的重复对是 `8744 / 17089`，其中 `17089` 是 re-ingest 副本。）

### 3.2 `9444 / 12617` **不是重复对**

两行题干完全不同：`9444` 问蒸压加气砌块最小龄期，`12617` 问建筑变形测量基准点。它们只是被分配了同一个 `source_chunk_id = EXAM_1A434000_P0022_02`。
**这是 chunk id 分配 bug，不是重复。** 删任何一行都是误删。

> 另有一条方法论级订正（本次调查内部）：家族正主判据**不能**用"`correct_answer` 是 JSON 数组"代替"含官方采分结构"。re-ingest 批次把字符串答案包成了单元素数组，那是序列化差异不是权威信号；本次调查的早期版本用它做判据，**导致 60 个副本错误地当上了正主**。

---

## 4. 可达面与删除风险（两个方向相反的判据）

**读取可达面**（谁会读到脏行，代码侧调研）：

| 通道 | 形态 | 是否有 active-set 闸门 |
|---|---|---|
| RAG 精确题面检索 | `questions_bank?question_stem=ilike.*…*` / `stem=ilike.*…*` | **无** —— 全表可达 |
| RAG 向量检索 | RPC `search_questions_bank_vector`，`filter_question_type=None`、`filter_source_type=None` | **无** |
| RAG 全文检索 | RPC `search_questions_bank_text`，两个 filter 都传 `None` | **无** |
| 测评组卷 | `question_type=in.(…)&source_type=in.(…)&id=not.in.(已用)` | 有 `_candidate_from_row()` 准入闸（缺 stem/options/答案的行被丢弃） |
| 轻练直出 | `coordinator._build_bank_hit_qa_pairs()` 把 bank 行**逐字直出，不过 LLM** | 需 `reference_answer` + ≥2 options |

→ **除组卷/轻练外，任何一行只要有 `question_stem` 就在 exact 匹配可达面内。**"污染行没进过试卷所以无害"这个假设**不成立**；修 `correct_answer` 的优先级不能因为"它不在 active set 里"而下调。

**删除风险**恰好相反，取决于是否已被下游快照引用：

| 下游持有者 | 持有形态 | 拟删行命中数 |
|---|---|---:|
| `assessment_forms.items_json`（status=active） | 预生成试卷快照，`source_question_id` | **136** |
| `assessment_sessions.*_questions_*` / `result_report_json` | 已作答会话快照 | **79** |
| `active_questions.question_id` | 在途题目 | **49** |
| `learner_mistake_book_items.question_id` | 用户错题本（纯 text，无 FK） | **48** |
| `knowledge_question_links.question_id` | 派生索引 | **19** |
| `question_intelligence.question_id` | 编译产物 | **5** |

`attempt_ref` 是 HMAC 签名的，里面带 `"q": question_id`；**删行不会让签名失效**，只会让 `attempt_detail_read_model` 解析回一个不存在的 id。

**因此本计划把"拟删行是否被下游引用"作为分批第一判据，而不是污染严重程度。**

---

## 5. 正主裁决判据（重复家族 keep/drop）

得到 **530 个家族 / 1120 行 / 590 个 drop 候选**。家族内按**有序**判据排名，第一名为正主（`duplicate_families.json` 逐家族记录命中判据）：

| # | 判据 | 理由 |
|---|---|---|
| 1 | 有 `source_chunk_id` | 唯一能回溯源文档的锚；tier1 复合键前置条件 |
| 2 | 答案未丢失（非空、非占位、非纯样板） | 无答案的行不能当权威 |
| 3 | 有 ingest 溯源（`source` 或 `source_meta` 非空） | 能追到哪本书/哪年真题 |
| 4 | 答案含官方采分结构（`不妥之处`/`正确做法`/`理由：`/`参考答案`/`判定结果`） | 案例题采分权威 |
| 5 | 答案正文更长 | 内容完整度 |
| 6 | 有真实（非样板）`analysis`，且更长 | |
| 7 | 有 `grading_keywords`/`structured_rules`/`logic_rule` | 判分资产 |
| 8 | id 更小 | 平局兜底，偏向先入库的 |

按 drop/keep 血统统计：

| drop 血统 | keep 血统 | 行数 | 其中被下游引用 |
|---|---|---:|---:|
| `EXAM_YYYY` re-ingest | `EXAM_<node>` | 365 | 120 |
| `EXAM_YYYY` re-ingest | `AUTO_` | 74 | 0 |
| `AUTO_` | `EXAM_<node>` | 38 | 19 |
| `ZL500_` | `QTZ_` | 32 | 5 |
| `XW_` | `ZL500_` | 22 | 21 |
| `QTZ_` | `ZL500_` | 21 | 6 |
| 其余同血统内重复 | | 38 | 19 |

---

## 6. 分批执行计划（B0–B12）

> 批次顺序即执行顺序。**每批之间必须停下来跑 §8 的验证项。** 所有 SQL 仅为草案，需主控逐批审阅后再运行；`$1::int[]` 处填 `batches.json` 对应键的 id 数组。

各批 id 数量（`batches.json` 实测）：

| 批次键 | 行数 |
|---|---:|
| `B1_reingest_delete_safe` | 319 |
| `B2_reingest_delete_reachable` | 120 |
| `B3_intra_exam_dup_safe` | 33 |
| `B4_intra_exam_dup_reachable` | 28 |
| `B5_textbook_edition_dup` | 90（其中 `B5_textbook_edition_dup_reachable` 42） |
| `B6_optfiller_truncate_answer` | 11 |
| `B6_optfiller_truncate_analysis` | 147 |
| `B7_jieshi_prefix_strip` | 8 |
| `B8_reauthor_answer` | 24 |
| `B8_reauthor_analysis` | 11 |
| `B9_chunk_cross_year` | 109 |
| `B9_chunk_same_year` | 7 |
| `B10_sibling_chunk_mixed` | 75 |
| `B10_sibling_chunk_allnull` | 40 |
| `B11_ruledump_shape_debt` | 543 |
| `B12_analysis_empty` | 631 |

### B0 — 前置（必做，无写操作）

1. **落盘备份**：`backup_all_affected.json` 已生成（2051 行全字段）。执行前再跑一次快照对齐，确认 id 集合与内容未漂移：
   ```sql
   -- 只读校验
   select id, md5(coalesce(question_stem,'') || coalesce(correct_answer::text,'') || coalesce(analysis,''))
   from public.questions_bank
   where id = any($1::int[]) order by id;
   ```
2. **建 DB 侧备份表**（比 JSON 更可靠的回滚源）：
   ```sql
   create table if not exists public.questions_bank_cleanup_backup_20260730 as
   select * from public.questions_bank where id = any($1::int[]);
   -- $1 = inventory.json 里全部 2051 个 id
   ```
3. **修当日已造成的悬挂引用**（独立于本计划，优先级最高）：`12865` 被 active 试卷 + 会话 + 错题本 + 在途题四处引用；需先决定恢复该行还是 remap。它已被删，`reference_remap.json` 无法给出 keep，**需人工判定**。

**回滚方式（全计划通用）**：删除批从 `questions_bank_cleanup_backup_20260730` 用 `insert into public.questions_bank select * from … where id = any(…)` 原样回插（若 `id` 是 identity 列需加 `overriding system value`）；UPDATE 批用 `update … set col = b.col from backup b where q.id = b.id` 还原。

### B1 — 删除 re-ingest 重复（无下游引用）· **319 行** · 低风险

- **处置**：DELETE；**对象**：`batches.json → B1_reingest_delete_safe`
- **判据**：`original_id ~ '^EXAM_(19|20)\d{2}_'`；存在批外 stem 孪生行；本行无 `source_chunk_id`；贡献 0 个批外行没有的字段值；答案不比孪生行长；`downstream_reachable = []`
- **风险**：exact 可达面**是**（会被 ilike/向量命中）—— 但删除后同题面由正主行提供，**检索面不减**；下游引用**无**；副作用：总行数 4635 → 4316，`blueprint_service.question_bank_size()` 会变，`deeptutor/services/source_compiler/psql.py` 的 `count(*)` 健康检查阈值需确认不会误报
- **SQL 草案**：
  ```sql
  -- 先看，不删
  select id, original_id, exam_year, question_type, left(question_stem, 40)
  from public.questions_bank where id = any($1::int[]) order by id;
  -- 确认 count = 319 后
  delete from public.questions_bank where id = any($1::int[]);
  ```

### B2 — 删除 re-ingest 重复（**已被下游引用**）· **120 行** · **高风险 · 逐行人审**

- **引用分布**：active 试卷 96 / 会话 58 / 错题本 36 / 在途题 28 / `question_intelligence` 2
- **风险**：`assessment_forms(status=active).items_json` 是**已生成的试卷快照**；删行不会让试卷报错，因为 `_candidate_from_row()` 只在**生成时**跑、服务时不再校验 → **会静默发出指向空 id 的题**。`learner_mistake_book_items` 是用户资产，删对应题会让错题本条目无法回显。`attempt_ref` HMAC 不失效，只是解析不到题。
- **推荐做法（代价从低到高）**：
  1. **不删**，只把这 120 行的 `correct_answer`/`analysis` 按 B6/B8 修好 —— 重复行留着的代价是检索面轻微冗余，不是正确性错误；
  2. 若要删：先在 `assessment_forms`/`assessment_sessions`/`learner_mistake_book_items`/`active_questions`/`question_intelligence` 里把 `drop_id` 改写为 `keep_id`，**且必须确认 keep 行的题面/选项顺序/答案与 drop 行一致** —— 190 条 remap 里 401 处答案等长/等同，但仍需逐行核对**选项顺序**，否则会重演"MCQ 判分锚题库字母倒诬"那类事故；
  3. 逐行人审清单：`reference_remap.json` 中 `holders` 含 `assessment_forms:active` 的 **136 条**必须审到底 —— 这是唯一会直接影响正在服务试卷的集合。

### B3 — 删除 `AUTO_`/同血统重复（无下游引用）· **33 行** · 低-中风险

- **判据**：家族内正主有 `source_chunk_id` 而本行没有（典型：`8770`（AUTO, chunk=NULL）vs `9150`（`EXAM_1A433000_P0011_01`））；或同血统内两行完全相同（如 `8817`/`8825`）
- **风险**：这批里有 **9 行是 `TEXTBOOK_ASSESSMENT` 自测题**（`7834` `7836` `7837` `7931` `7933` `7938` `7939` `8048` …），是 LLM 对同一教材点的两次生成，答案措辞略有差异 —— 删哪个不影响权威，但**建议单独确认**是否保留两版做多样性

### B4 — 删除 `AUTO_`/同血统重复（**已被下游引用**）· **28 行** · **高风险 · 逐行人审**

与 B2 同处置逻辑，规模小；19 行来自 `AUTO_ → EXAM_<node>` 家族。同样推荐"不删只修"为默认。

### B5 — 教材多版本重复（`ZL500_`/`QTZ_`/`XW_`）· **90 行（42 行被引用）** · **需 owner 拍板，不建议本轮执行**

- **处置**：暂缓。这些不是同一次入库的副本，而是**不同教材版本/不同来源文档**（周立 500 题、其他题源、习题集）录入了同一道题；删除会减少来源多样性，且 `based_on_version`/`source_meta` 不同 —— "同题不同版本"在教材类资产里可能是有意的
- **风险**：`XW_ → ZL500_` 家族里 22 个 drop 有 **21 个被下游引用**（比例异常高），说明这批题是组卷高频命中题，误删杀伤面大
- **建议**：本轮只标注；若要治，应走"同题合并 + `source_meta` 数组化"而不是删行

### B6 — 机械修复：截断伪造的`【选项分析】` · **158 行** · 中风险

- **处置**：UPDATE（纯字符串截断，无内容再创作）
- **判据（保守）**：只处理 **`options` 为空/NULL 的 case_study 行**；有真实选项的 264 行选择题，其`【选项分析】`是合法逐项解析（含 `[概念混淆]` 标注），**绝不能碰**。截断点固定为字符串中第一次出现`【选项分析】`的位置
- **风险**：exact 可达面**是**（`analysis` 会进 `_normalize_question_result` 的`【解析】`段、`QAPair.explanation`、`grading_key["minimal_rationale"]`）；截断后 `analysis` 变短但语义无损；11 行答案截断已核实截断后正文均 ≥20 字，不会截成空串
- **SQL 草案**：
  ```sql
  -- analysis：只处理无选项的 case_study
  update public.questions_bank
  set analysis = btrim(split_part(analysis, '【选项分析】', 1))
  where id = any($1::int[])
    and question_type = 'case_study'
    and (options is null or options::text in ('[]', 'null'))
    and analysis like '%【选项分析】%'
    and length(btrim(split_part(analysis, '【选项分析】', 1))) > 0;   -- 防止截成空串
  ```
  `correct_answer` 同形，但注意它在库里有 `text` 与 JSON 数组两种形态（**4460 / 175**），需按行判形。

### B7 — 剥离 `correct_answer` 的`【解析】`前缀 · **8 行** · 低风险 · **建议跳过**

这 8 行正文**都含采分结构**（`不妥之处`/`理由：` 等），按"`【解析】`开头且无采分结构才算污染"的保守判据，**不算内容污染**，只是格式债。`deep_question._project_correct_answer_to_target_surface` 会对 `correct_answer` 做字母投影，动判分权威字段的收益/风险比不划算 → 整批跳过。

### B8 — 答案/解析重写（**人工，非机械**）· **35 行** · **高风险 · 逐行人审**

- **处置**：人工回源重写（教材/真题原文），**不可由 LLM 自动补**
- **对象**：
  - `B8_reauthor_answer`（**24 行**）：删重后仍然没有答案的行
    - 家族正主但本身答案丢失：`9170 9171 9303 9304 9342 9446 9447 9575 9663 9680 9698`（11 行）—— 这些家族**整族退化**（如 `8779`/`9171` 两边都只剩样板），**DB 内无源可抄**
    - 孤行（无孪生）：`8303 8923 8924 8925 8926 8927 17285 17317 17370 17381 17421 17463 17533`（13 行）
  - `B8_reauthor_analysis`（**11 行**）：`analysis` 100% 样板
- **风险**：**这是本次调查里唯一"真正的数据损失"**。这 35 行在 exact 可达面内，轻练直出通道要求 `reference_answer` 存在才短路，所以它们会**落到 LLM 现编** —— 对应"编译库干净、泄露在运行时现编"那条病
- **例外**：`17421` 题干只有 `【背景资料】\n\n某`（截断垃圾）、答案空、解析空、无下游引用 → **建议直接删除**，不值得重写
- **优先级**：`8923–8927`（5 行 2021 真题，被 `knowledge_question_links` 引用）与 `17285 / 17317 / 17370 / 17381 / 17463`（5 行 2021–2025 真题孤行，背景资料完整）优先

### B9 — `source_chunk_id` 冲突：**不删行，改键** · 116 行 · 本轮无写操作

- **处置**：NO-OP + 上游 schema 修正
- **对象**：`B9_chunk_cross_year`（**109 行 / 45 个 chunk**）、`B9_chunk_same_year`（**7 行 / 3 个 chunk**）
- **根因**：`source_chunk_id` 形如 `EXAM_<node_code>_P<页码>_<序号>`，是**文档内局部编号**，天然不跨文档唯一。2017 与 2025 两份真题各自的"第 4 页第 4 题"当然会撞。**这不是污染，是把局部 id 当全局键用的设计缺陷。**
- **代码侧证据**：`deeptutor/tutorbot/agent/loop.py:1645-1657` 的 tier1 复合键 `{exam_year}::{source_chunk_id}::E{n}` 只匹配上 **23/354** 且 **0 个语义正确**，"全部错绑到相邻小问 rubric"（详见同日《复合 qid 唯一性与 E 索引权威审计》）
- **正确处置**：① 复合键改为 `(source, exam_year, source_chunk_id, 小问序号)`，或给 chunk id 加文档前缀重新生成；② `scripts/audit_2026_compiler_supabase_coverage.py` 里 `questions_bank q JOIN kb_chunks k ON q.source_chunk_id = k.chunk_id` 这个 JOIN 在 45 个冲突 chunk 上会产生**笛卡尔积**，需同步修
- **`CH2` 的 3 处需单独查（入库管道 bug，改 DB 只是治标）**：
  - `EXAM_1A434000_P0022_02` → `9444`（蒸压加气砌块龄期）+ `12617`（变形测量基准点）：**不同题**
  - `EXAM_1A431022_P0013_01` → `12533` + `12534`：**不同题**
  - `EXAM_1A415041_P0014_02` → `12536` + `12537` + `12538`：**三道不同题**

### B10 — 兄弟小问 `source_chunk_id` 回填 · 115 行 · **不可机械回填**

- **对象**：`B10_sibling_chunk_mixed`（**75 行 / 21 组**）、`B10_sibling_chunk_allnull`（**40 行 / 9 组**，全落在 `13828–13897` 区间）
- **关键更正**：兄弟小问**各自有独立的 chunk id**。例如 2019 年那组：`9236 = EXAM_1A434000_P0019_01`、`9261 = EXAM_1A434000_P0020_02`、`9235 = EXAM_1A432000_P0017_01` —— 页码和序号都不同。**把兄弟的 chunk id 抄给 NULL 行会造成错绑**，正是 `loop.py` 记录的"全部错绑到相邻小问 rubric"那个失败模式
- **正确处置**：① 短期：`questions_bank` 增加显式小问序号列（`subquestion_index`），从题干 `问题N`/`N.` 解析后落列（本次调查已验证该解析在 case_study 上可行）；② 中期：重跑 chunk 归属，用（`source` 文档, 页码, 小问序号）重新派生 `source_chunk_id`；③ **在第 ① 步完成前，tier1 复合键不应上线**
- **更根上的缺口**：`parent_id` 全表 4635 行**全为 NULL**，代码侧只透传不消费 —— **兄弟关系在 DB 里根本没有表达**

### B11 — `CA7_ruledump`（543 行）· 本轮不处置

`correct_answer == analysis ==` 机器规则转储，全部来自 `TEXTBOOK_ASSESSMENT` 生成管道。内容**是**存在的（`判定结果: …` 就是答案），只是形态是给机器看的。属于生成管道的输出契约问题，改 DB 是治标 → 列入待办。

### B12 — `AN3_analysis_empty`（631 行）· 本轮不处置

`analysis` 从未被填过（515 行 `textbook_exercise` + 112 行 `TEXTBOOK` + 4 行真题）。这是**缺口不是污染**，但与"答题必有解析＝硬约束"冲突，需单独立项。

---

## 7. 当日已执行的三行删除（不属于本计划）与教训

本计划之前，当日已删除三行（备份在案）：

| id | original_id | 形态 | 备份 |
|---|---|---|---|
| `12865` | `EXAM_1A436000_P0018_02_multiple_choice_709f284f` | `single_choice` / `REAL_EXAM` / 2024 / chunk `EXAM_1A436000_P0018_02` | 全字段快照（含 stem/answer/analysis） |
| `9035` | `AUTO_3d25bd45cf54fca7` | `case_study` / `REAL_EXAM` / 2024 / chunk NULL | 家族级快照（含存活的 `9664`、`17424`） |
| `9037` | `AUTO_f18324ad26afc415` | `case_study` / `REAL_EXAM` / 2024 / chunk NULL | 同上 |

**教训（引用面盲区）**：删除时只核了"是不是重复副本"，**没有核引用面**。事后扫描发现：

- `12865` 被 `assessment_forms(status=active)` + `assessment_sessions` + `learner_mistake_book_items` + `active_questions` **四处引用** —— 已经污染了**正在服务的试卷**；`reference_remap.json` 也给不出 keep（它不是重复家族的 drop），只能人工判定"恢复该行 or remap"。
- `9035`/`9037` 被 `knowledge_question_links` 引用。
- 加上更早删除留下的 70 个（id 区间 8723–9076），**当前共 73 个悬挂引用**。

`questions_bank` **没有任何外键、没有软删标记**（消费面调研确认：全库无 FK，删除被静默接受）。**"删得掉"不等于"删得起"** —— 这正是本计划把引用面设为第一判据的原因。

---

## 8. 建议执行顺序与停等点

| 序 | 批次 | 行数 | 类型 | 需人审 |
|---|---|---:|---|---|
| 1 | B0 备份 + 建备份表 | 2051 | 只读 + 建表 | — |
| 2 | B0.3 修 `12865` 等 73 个已存在的悬挂引用 | 73 | 人工 | 是 |
| 3 | **B1** 删 re-ingest 无引用副本 | 319 | DELETE | 抽检 20 行 |
| 4 | **B6** 截断伪造`【选项分析】` | 158 | UPDATE | 抽检 20 行 |
| 5 | **B3** 删 `AUTO_` 无引用副本 | 33 | DELETE | 全审（9 行自测题单独确认） |
| 6 | **B8** 重写丢失的答案/解析 | 35 | 人工 | 是，全审 |
| 7 | **B2 / B4** 被引用副本 | 148 | remap+DELETE 或只修 | 是，**136 条 active 试卷引用必须逐行** |
| 8 | B9 / B10 | — | schema 变更，另立项 | 是 |
| 9 | B5 / B11 / B12 | — | 待 owner 拍板 | 是 |

**每批之后的验证项（不做完不进下一批）**：

1. `select count(*) from public.questions_bank` 与预期一致；
2. 重跑悬挂引用扫描：`assessment_forms(active)`/`assessment_sessions`/`learner_mistake_book_items`/`active_questions`/`question_intelligence`/`knowledge_question_links` 里所有 `question_id` ∈ `questions_bank.id`，**新增悬挂 = 0**；
3. `deeptutor/services/source_compiler/psql.py` 的 DB 身份守卫（`to_regclass` + `count(*)`）不报警；
4. 对 B1/B3 删除的每个家族，正主行仍能被 `question_stem=ilike.*<题面>*` 命中（**检索面不缩**）；
5. `blueprint_service.question_bank_size()` 的变化已知且被接受。

---

## 9. 缺口与诚实边界（你没问但必须知道的）

1. **本次最大的发现不是脏字段，是"删除是无保护动作"。** 73 个已存在的悬挂引用（含当日删的 `12865` 落在 active 试卷）说明：在给 `questions_bank` 加软删标记（`deleted_at`）或至少给下游持有表加校验之前，任何批量删除都会继续积累这类债。**建议 B1 之前先加 `deleted_at`，用软删代替物理删** —— 检索面靠 `deleted_at is null` 过滤即可收权，风险从"不可逆"降到"可逆"。
2. **"`analysis` 污染 443 行"这个口径会误伤 264 行高质量内容。** 有选项的选择题的`【选项分析】`是逐项带 `[概念混淆]` 标注的真实解析；若按"含`【选项分析】`就清洗"执行，会删掉库里质量最高的一批解析。本计划已把判据收紧到"`options` 为空"才处理。
3. **`parent_id` 全表 NULL、代码只透传不消费。** 案例题的小问关系在 DB 里完全没有表达，B10 的 chunk 回填只是这个缺口的表症；在补上显式小问序号列之前，任何依赖"同一道案例题的兄弟小问"的能力（复合键、rubric 绑定、跨小问上下文承接）都无法正确落地。
4. **信号计数与落批计数存在小额差异**（`CA7` 550 vs `B11` 543、`AN3` 633 vs `B12` 631、`CH1` 111 vs `B9_chunk_cross_year` 109）：差额是同时命中删除类批次的行在落批时被去重的结果，**未逐行核对差额构成**，记为开口。
5. **未覆盖**：本盘点只做了信号识别与处置设计，**没有对任何一行做内容正确性的教材溯源核验**；B8 的 35 行重写必须回源，不可由本文件的分类推断代替。
6. **执行状态**：截至归档，B0–B12 **一批未跑**；文中所有行数均为快照值，执行前须按 B0.1 重新对齐。

---

## 10. 数据来源路径（可复查）

| 内容 | 路径 |
|---|---|
| 数据面 | Supabase `zgupgizexqpwtajvghno` / `public.questions_bank`（REST 只读） |
| tier1 建键代码 | `deeptutor/tutorbot/agent/loop.py:1645-1657` |
| 组卷准入闸 | `_candidate_from_row()`（测评组卷路径） |
| 轻练直出 | `coordinator._build_bank_hit_qa_pairs()` |
| DB 身份守卫 | `deeptutor/services/source_compiler/psql.py` |
| 受影响的 JOIN | `scripts/audit_2026_compiler_supabase_coverage.py`（`questions_bank q JOIN kb_chunks k ON q.source_chunk_id = k.chunk_id`） |
| 答案字母投影 | `deep_question._project_correct_answer_to_target_surface` |
| 同日姊妹档案 | `docs/原始数据/数据盘点/2026-07-30-复合qid唯一性与E索引权威审计.md` |
| 逐行产物（工作副本） | `inventory.json` / `backup_all_affected.json` / `duplicate_families.json` / `reference_remap.json` / `batches.json` / `backup_row_12865_full.json` / `backup_rows_9035_9037_family.json` |

---

> 产物工作副本（`cleaning_plan.md` 及上表逐行 JSON）曾位于 session scratchpad `qb_cleaning_plan/`，**正式归档以本文档为准**；执行前若逐行 JSON 已消失，须按本文档 §5 判据与 §6 判据重新生成 id 清单，不得凭记忆填 `$1::int[]`。
