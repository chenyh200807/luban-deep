---
type: "TopicCard"
title: "网络计划"
description: "网络计划时间参数、关键线路、时差、工期调整与索赔联动。"
resource: "docs/原始数据/数据盘点/extractions/topic_okf_v0/topics.jsonl"
tags:
  - "luban"
  - "okf"
  - "topic"
  - "network-planning"
timestamp: "2026-06-20T00:00:00+08:00"
status: "topic_okf_candidate"
runtime_consumable: false
official_score_allowed: false
---

# 网络计划

## What AI Can Answer Better

网络计划时间参数、关键线路、时差、工期调整与索赔联动。

## Evidence Shape

- Raw source hits: 3187
- Source files: 57
- Candidate scoring points: 9
- Candidate cases: 5
- Candidate years: 2021, 2022, 2023, 2024, 2025

## Source Buckets

- `exam_cleaned_json`: 159 hits
- `lecture_cleaned_json`: 1798 hits
- `practice_qiantizan_json`: 25 hits
- `taxonomy_backup_json`: 430 hits
- `taxonomy_cleaned_json`: 69 hits
- `textbook_cleaned_json`: 357 hits
- `textbook_core_json`: 18 hits
- `textbook_enrichment_json`: 331 hits

## Aliases

- 网络计划
- 双代号
- 时标网络
- 关键线路
- 关键工作
- 总时差
- 自由时差
- 最早开始
- 最迟完成
- 工期优化

## Representative Candidate Scoring Points

- `sp_2021_2_q04_01` (case_2021_2, 2021): 绘制从第9月开始到工程结束的双代号网络计划图(图3-2):⑥→⑦、⑥→⑧、⑦→⑧、⑧→⑨,⑥→⑧及⑦前后含波形线虚工作
- `sp_2022_2_q02_03` (case_2022_2, 2022): (3)关键线路:①A-B-D-H;②A-B-E-G-H
- `sp_2022_2_q03_01` (case_2022_2, 2022): (1)关键工作的调整
- `sp_2022_2_q03_04` (case_2022_2, 2022): (4)非关键工作调整
- `sp_2023_2_q01_01` (case_2023_2, 2023): 关键线路:①→②→③→④→⑥→⑦→⑧
- `sp_2024_2_q01_01` (case_2024_2, 2024): (1) 关键线路 B→E→I
- `sp_2024_2_q01_02` (case_2024_2, 2024): (2) 工作A的总时差为2周;工作F的总时差为3周
- `sp_2025_2_q01_01` (case_2025_2, 2025): 调整前关键线路 A→B→E→F→H
- `sp_2025_2_q01_04` (case_2025_2, 2025): 非关键工作调整;剩余工作重新编制进度计划

## Representative Source Hits

- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].content_markdown`: 视为已认可承包人要求。 当发生工期延误事件时，发承包双方计算索赔工期应符合下列规定： ① 延误事件为关键线路上的工作，则延误的时间为索赔的工期； ② 延误事件为非关键线路上的工作，当该工作由于延误超出总时差而成为关键线路上的工作时，其延误时间与总时差的差值为索赔的工期； ③ 工期延误后事件仍为非关键线路上的工作，则不发生工期索赔。 除合同另有约定外，在发承...
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].card_content`: 工期索赔的计算取决于延误是否在关键线路：若为关键线路，则延误时间即为索赔工期；若为非关键线路且超出总时差，则差值为索赔工期；否则不索赔。
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].key_numbers[0]`: 关键线路
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].key_numbers[1]`: 总时差
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].logic_chain`: 延误工作 ∈ 关键线路 → 索赔工期 = 延误时间；延误工作 ∉ 关键线路且超出总时差 → 索赔工期 = 延误时间 - 总时差；否则 → 不索赔
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].pitfalls`: 易错点：非关键线路只要没超过总时差就不索赔，即使有延误也不成立。
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].keywords[1]`: 关键线路
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].knowledge_cards[1].keywords[2]`: 总时差
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[67].synthetic_queries[1]`: 如果延误发生在非关键线路上，是否可以索赔工期？
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[69].content_markdown`: ## （5）索赔的计算 #### ① 工期索赔计算 a. **网络分析法**：通过分析延误前后的施工网络计划，比较两种工期计算结果，计算出工程应顺延的工程工期。 b. **比例分析法**：在实际工程中，干扰事件常常仅影响某些单项工程、单位工程或分部分项工程的工期，分析它们对总工期的影响。 > **工期索赔值 = 原工期 × 新增工程量 / 原工程量** c...
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[69].assessment.grading_keywords[2]`: 关键线路
- `textbook_cleaned_json` `docs/原始数据/2026_副本/2026教材/第一次清洗/FINAL_CLEANED_BOOK2026-222-382.json` at `$[80].related_knowledge[1].reason`: 网络计划技术是进度管理的进阶工具，与流水施工共同构成进度控制体系

## How To Use

- Use this card first when the user asks about this topic across exams, textbooks, standards, lectures, or practice sources.
- Follow source paths for exact wording before making high-stakes claims.
- Treat candidate scoring-point counts as candidate evidence, not official exam-frequency truth.

## Boundary

This Topic OKF card is AI navigation and synthesis support only. It is not runtime supply, not official scoring authority, and not a full source mirror.
