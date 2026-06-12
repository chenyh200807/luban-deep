# 案例题阅卷资料利用手册

本 Skill 的领先点不是“模型会说”，而是把 2026 清洗资料变成阅卷动作。

## 已核验的本地资料规模

路径：`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026`

结构快照：

| 类型 | 数量 | 价值 |
| --- | ---: | --- |
| 讲义 JSON | 335 | `exam_matrix / structured_rules / grading_keywords / trap_alert / mnemonics` |
| 2026 教材 JSON | 18 | `knowledge_cards / key_numbers / logic_chain / pitfalls` |
| 题库 JSON | 13 | 真题题干、答案、解析、分值、`option_reasoning`、case 子问 |
| 标准文件 JSON | 8 | `logic_constraints / common_violations / synthetic_qa` |
| taxonomy JSON | 1 | L1-L6 知识节点、关键词、认知类型 |

全量 JSON 观察到的高价值字段：

- `mnemonics`: 12025
- `key_parameters`: 8494
- `rag_content`: 8487
- `structured_rules`: 8467
- `exam_matrix`: 8067
- `logic_chains`: 6835
- `pitfalls`: 4180
- `related_standard`: 2618
- `synthetic_queries`: 1675
- `option_reasoning`: 744

这些字段应优先变成评分线索、错因标签和下一题推荐，不应只作为普通 RAG 背景。

## 线上 Supabase 对账结论

2026-05-13 只读 live audit 已确认：

- `questions_bank` 存在，合计 4638 题。
- `questions_bank` 中 `case_study` 有 1961 条，`single_choice` 1674 条，`multi_choice` 978 条。
- `questions_bank.grading_rubric` 字段存在，但当前非空数为 0。
- `questions_bank.grading_keywords` 非空 1225 条，其中 case 题 960 条。
- `questions_bank.option_reasoning` 非空 80 条，主要在选择题。
- `knowledge_cards` 表在线上不存在；教材/讲义增强字段实际主要落在 `kb_chunks.metadata`。
- `kb_chunks` 存在 15432 条，其中 `source_type=textbook` 1199 条、`source_type=exam` 312 条、`source_type=standard` 13912 条。
- `kb_chunks.metadata` 中可用字段包括：`exam_matrix` 1192 条、`structured_rules` 884 条、`logic_chains` 1074 条、`key_parameters` 677 条、`pitfalls` 240 条。
- `standard_articles` 存在 3319 条，其中 `logic_constraints` 有实际内容 908 条。
- `syllabus_tree` 存在 1284 条，其中 `node_code` 全量、`keywords` 非空 780 条。

因此，线上运行时不能写死 `knowledge_cards` 表名。应按以下顺序查证据：

1. `questions_bank` 当前题目行。
2. `kb_chunks` 按 `node_code / source_type / metadata.exam_matrix / metadata.structured_rules / metadata.logic_chains` 检索。
3. `standard_articles` 按 `standard_code / taxonomy_node_code / logic_constraints` 检索。
4. `syllabus_tree` 按 `node_code / keywords` 挂接知识节点。

## 资料使用优先级

1. **题库真题**
   - 用于绑定题干、问法、标准答案、解析、分值、年份、来源。
   - case 题优先读：`question_data.stem / correct_answer / analysis / score / taxonomy / pitfalls / source_meta`。
   - 观察到 2015-2025 真题中有 218 个 `case_study` exercise，可做 P0 样本池。

2. **教材 knowledge cards**
   - 原始 JSON 里是 `knowledge_cards`；线上主要落在 `kb_chunks.metadata`。
   - 用于补齐标准答案背后的规范性判断、流程链条、关键数字。
   - 重点读：`metadata.exam_matrix / metadata.structured_rules / metadata.logic_chains / metadata.key_parameters / metadata.pitfalls`。
   - 用途：判断用户答案缺的是“知识点、关键词、程序顺序、数字串扰”。

3. **讲义 exam_matrix**
   - 用于提炼老师视角的应试抓手。
   - 线上优先读 `kb_chunks.metadata.exam_matrix` 中的 `grading_keywords / trap_alert / red_lines / mnemonics`。
   - 用途：把“为什么扣分”说成阅卷语言，而不是教材复述。

4. **标准文件 logic_constraints**
   - 用于精确规范、强制性边界、常见违规。
   - 重点读：`logic_constraints / common_violations / synthetic_qa`。
   - 用途：当题目涉及强制条文、验收条件、禁止性规定时补依据。

5. **taxonomy**
   - 用于把错因和下一题挂到稳定知识节点。
   - 重点读：`node_code / node_name / keywords / cognitive_type`。
   - 用途：错因聚合、变式推荐、同考点迁移训练。

## 如何从资料生成采分点投影

`projected_rubric` 不是让模型空想采分点，而是按字段顺序合成：

1. 从 `correct_answer / model_answer_raw` 抽取标准答案句。
2. 从 `analysis` 抽取为什么这么答。
3. 从 `score / total_score` 估算每点分值。
4. 从 `exam_matrix.grading_keywords` 与 `knowledge_cards.key_numbers` 抽取得分关键词。
5. 从 `pitfalls / trap_alert / common_violations` 抽取常见扣分点。
6. 从 `logic_chain / structured_rules / logic_constraints` 抽取流程顺序和禁止条件。
7. 从 `taxonomy` 绑定考点。

没有经过这些字段支撑的采分点，只能作为“可能漏点”，不能作为标准给分项。

## 采分点教材溯源硬规则

编译轴硬约束：**采分点和 required_terms 必须带教材原文溯源（textbook provenance），不可凭模型常识杜撰**。落到阅卷动作上：

1. 每个投影采分点必须记录 `source_fields`（来自题库/教材/讲义/规范的哪些字段），不可为空。
2. 得分关键词（required_terms）必须出现在溯源字段的原文里；模型自己补的同义词只能用于匹配用户答案的含义，不能作为新的得分关键词写进采分框架。
3. 条文号、数字、时限、比例只引检索结果中实际出现的值；检索不到就不写，宁缺勿造。
4. 相似题经验、用户题面暗示、模型记忆都不构成投影 authority——这是 SKILL.md Authority guard 的资料层落地。
5. `open_skill` 档抽出的“可能漏点”也应尽量给出处；完全无出处的诊断要在表述上保持为方向性建议，不写成确定漏分。

## 典型资料到阅卷动作的映射

| 字段 | 阅卷动作 |
| --- | --- |
| `grading_keywords` | 判断用户答案是否写出可得分关键词 |
| `trap_alert` | 生成“你为什么容易错”的诊断 |
| `red_lines` | 判断危险表达、禁止表达、不能给分表达 |
| `mnemonics` | 只在用户需要记忆抓手时输出，不能替代采分点 |
| `logic_chain` / `logic_chains` | 判断程序顺序、因果链、流程漏项 |
| `key_parameters` / `key_numbers` | 判断数字、比例、时限、层数、强度等是否写准 |
| `related_standard` | 生成依据口径，避免伪造条文号 |
| `synthetic_queries` | 扩展同考点检索词和下一题候选 |
| `taxonomy.node_code` | 错因聚合与下一题推荐 |

## 案例题专项注意

- 一道综合案例可能拆成多个子问，不能把整段背景当一个问题判。
- 同一 chunk 的 `pitfalls` 有时覆盖多个子问，不能机械套到每个子问。
- 图表题、网络计划题、索赔计算题应优先找标准解或确定性算法；没有算法时只做过程诊断。
- 如果 Supabase 线上字段缺失，先用本地源数据做 golden eval 和补录依据，不要创建第二套生产题库。
