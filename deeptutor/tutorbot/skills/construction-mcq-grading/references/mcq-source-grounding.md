# 选择题阅卷资料利用手册

选择题不需要主观题那样重的 Rubric 内核，但必须充分利用现有清洗数据，做到比普通题库讲解更准。

## 已核验的选择题资产

本地 2026 资料中观察到：

- `single_choice`: 908
- `multi_choice`: 352
- `multiple_choice`: 110
- 带 `option_reasoning` 的选择题样本：274

导入脚本显示：

- `option_reasoning` 会完整导入或追加到 `analysis`。
- `pitfalls` 会进入 `trap_type`。
- `synthetic_queries` 会提取为 `testing_focus`。

因此，选择题 Skill 应优先消费这些结构化字段，而不是只看标准答案。

## 线上 Supabase 对账结论

2026-05-13 只读 live audit 已确认：

- `questions_bank` 存在 4638 题。
- 选择题合计 2659 条：`single_choice` 1674、`multi_choice` 978、`judgment` 7。
- 选择题 `correct_answer` 非空 2659 条，`analysis` 非空 2655 条，`options` 非空 2655 条。
- 选择题 `option_reasoning` 非空 80 条，覆盖不高但质量高。
- 选择题 `trap_type` 非空 264 条，`testing_focus` 非空 297 条。
- 选择题 `node_code` 非空 2599 条，可用于连到 `kb_chunks` 和 `syllabus_tree`。
- `knowledge_cards` 表在线上不存在；教材/讲义增强字段实际主要落在 `kb_chunks.metadata`。
- `kb_chunks.metadata.exam_matrix` 非空 1192 条，`structured_rules` 非空 884 条，`logic_chains` 非空 1074 条。

因此，选择题运行时证据链应是：

1. `questions_bank.correct_answer / options / analysis / option_reasoning`。
2. `questions_bank.trap_type / testing_focus / grading_keywords`。
3. `kb_chunks` 按 `node_code` 和 `metadata.exam_matrix` 补讲义/教材抓手。
4. `standard_articles.logic_constraints` 补规范和数字边界。

## 字段使用顺序

1. `correct_answer`
   - 判定对错的第一 authority。
   - 没有标准答案时不能正式判分。

2. `option_reasoning`
   - 选择题解释的最高价值字段。
   - 每个选项通常包含：`status / error_type / explanation`。
   - 用户选错时，先解释用户所选项，再解释正确项。

3. `analysis`
   - 如果没有独立 `option_reasoning`，检查是否包含“选项分析”。
   - 用于补足题目解析，但不要覆盖标准答案。

4. `trap_type / pitfalls`
   - 转成错因标签和“下次判断抓手”。
   - 适合识别：概念混淆、事实错误、数字串扰、问法陷阱。

5. `testing_focus / synthetic_queries`
   - 用于同考点下一题推荐。
   - 也可作为 RAG 检索词。

6. `taxonomy.node_code / node_name`
   - 用于稳定挂接知识节点和 mastery。

7. `kb_chunks.metadata / exam_matrix / standard_articles`
   - 涉及规范数字、流程、强制条文时补充。
   - 优先读 `kb_chunks.metadata.exam_matrix.grading_keywords / trap_alert / red_lines`。

## 选项解释策略

| 场景 | 输出重点 |
| --- | --- |
| 单选答错 | 用户所选项为什么错；正确项为什么唯一成立 |
| 多选漏选 | 漏掉的正确项对应哪个关键词或条件 |
| 多选错选 | 错选项偷换了什么主体、条件、数字或程序 |
| 多选部分正确 | 先肯定命中项，再明确漏选/错选，不直接长篇讲课 |
| 判断题 | 先定位题眼，如“必须/不得/宜/不应/超过/不超过” |

## 错因映射建议

- `option_reasoning.error_type = concept_confusion` -> `M03 概念混淆`
- `fact_error` -> `M01 知识点缺失` 或 `M08 数字串扰`
- `trap_alert` 中出现“注意区分” -> `M03` 或 `M04`
- 题干有“不正确/不妥/错误”而用户按正确项选 -> `M05`
- 多选缺少正确项 -> `M06`
- 多选选入错误项 -> `M07`

## 领先体验要求

普通题库只告诉用户“答案是 B”。本 Skill 必须多做三步：

1. 说清用户所选项为什么不能得分。
2. 抽出这个错误背后的错因标签。
3. 给出下一题推荐信号，而不是只结束在解析。
