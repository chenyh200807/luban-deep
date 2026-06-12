# 数据 Authority 与现有题库利用

## 运行时 Authority

- 生产题目资产以 Supabase `questions_bank` 为 authority。
- 当前练题上下文以 active question / `question_followup` 为 authority。
- 本地原始题库只用于：
  - 源数据核验
  - golden eval fixture
  - 补录/对账依据
  - 判断 Supabase 是否丢字段

不要把本地 JSON 直接变成第二套线上题库。

## 采分框架 Authority 链（与运行时内核对齐）

运行时案例阅卷内核（`construction_grading/case_kernel.py`）的采分框架优先级，本 Skill 必须与之一致，不另立顺序：

1. `grading_key.scoring_points`：active_object 注入的隐藏采分点，最高 authority → `curated_rubric`（trace `grading_source=grading_key`）。
2. `questions_bank.grading_rubric`：题库人工/结构化 Rubric → `curated_rubric`（trace `grading_source=questions_bank`）。
3. 题库既有字段投影（标准答案/解析/关键词/分值）→ `projected_rubric`。
4. 以上全空 → `open_skill`（trace `grading_source=open_skill_fallback`），开放世界提分诊断，不拒答。

注意线上现状：`questions_bank.grading_rubric` 字段存在但当前非空数为 0，`grading_keywords` 非空 1225 条（case 题 960 条）——所以生产上 `curated_rubric` 主要由 `grading_key` 触达，题库路径大多落在 `projected_rubric`。编译库逐步补全 rubric 是供给侧工作；阅卷侧不得因为 rubric 缺位而拒答或自拼。

## 本地源数据快照

路径：

`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库`

已观察到的清洗后 JSON：

- 2015-2025 年一建建筑实务真题：`FINAL_CLEANED_EXAM_V20xx.json`
- 章节千题斩：`FINAL_CLEANED_QIANTIZAN.json`
- 864 考证宝典：`FINAL_CLEANED_ZL500.json`

真题 case_study 数量快照：

| 年份 | case_study 数量 |
| --- | ---: |
| 2015 | 22 |
| 2016 | 23 |
| 2017 | 13 |
| 2018 | 19 |
| 2019 | 19 |
| 2020 | 26 |
| 2021 | 21 |
| 2022 | 12 |
| 2023 | 31 |
| 2024 | 7 |
| 2025 | 25 |

选择题专项源中暂未观察到 case_study：

- 864/ZL：single_choice 279，multi_choice 124
- 千题斩：single_choice 402，multi_choice 228

## 可用于 Rubric 投影的字段

本地源题库通常包含以下信息，足够支撑 `projected_rubric` 和部分 L2 精修：

- `content_markdown`
- `exercises[].type`
- `question_data.stem` / `stem` / `q`
- `correct_answer` / `answer`
- `analysis`
- `score` / `total_score`
- `logic_chain`
- `taxonomy.node_code` / `taxonomy.node_name`
- `source_meta`
- `pitfalls`
- `related_knowledge`
- `suggested_tool_call`
- `synthetic_queries`
- `_layers.index.rag_content`

## 已观察到的数据风险

- 同一案例可能被拆成多个 chunk 或多个子问。
- 部分记录的 `type` 与内容可能不完全一致。
- 2024、2025 等年份有题干/答案拆分或答案泛化现象。
- 有些 chunk 更像讲解片段，不是可直接判分的完整问答。

因此，Skill 不能假设“源数据字段存在就一定能标准评分”。必须先做 readiness 判断：

1. 题干是否完整。
2. 问法是否明确。
3. 标准答案/解析是否能拆成 2 个以上采分点。
4. 分值是否可用。
5. 来源和考点是否可追溯。

## Supabase 对账口径

实现时需要只读对账：

- Supabase `questions_bank` 是否保留 `case_study` 题。
- 是否保留题干、背景、问法、答案、解析、分值、考点、来源。
- `grading_keywords` / `grading_rubric` 是否存在且结构稳定。
- 是否能从 `source_chunk_id` / `source_meta` 回到本地源数据。

若 Supabase 字段不完整：

1. 不新建线上第二题库。
2. P0 使用本地源数据做 golden fixture。
3. 记录 parity gap。
4. 通过补录或人工覆盖层回填到 `questions_bank`。
