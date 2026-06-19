# Data-blocker report — QuestionGradingArtifact Registry v1 (2026-06-04)

> v1「全题库」**不是工具问题，是数据问题**。本报告固化阻塞事实，作为 v1 的正式状态。

## 一句话

当前可发布 authority 仍只有 **20 题 golden / 97 采分点**（published=18 / draft=1 / blocked=1）。
20 题之外**不存在**可批改主观案例题的 rubric authority 数据，因此**不产出同覆盖 v1 冒充扩量**。

## 阻塞链（逐条事实）

1. **唯一可批改主观题源 = 20 golden**。`luban_case_grading_golden_v1` 与 no-human v1.5、答案派生
   `mvp-rubric-20q`、typed_policy packets、485 consensus 全部是**同一套 20 题**的不同表示，非新题。
2. **62 真题是 MCQ**（`exam_quality_bank.json` 全为 single/multiple_choice）。MCQ 走
   `grade_mcq_submission`，**不进**采分点 artifact registry —— 把它塞进来是 scope 污染，红线禁止。
3. **6134 节点采分点资产是 node-level 知识**（chunk_id + label + required_terms + textbook 锚），
   按 chapter node 组织，**不是 question-level rubric**。一个 node ≠ 一道题。
4. **弱源点自动富集 = 0**：对 v0 的 **28 个弱源点**，在 16 个有 textbook 索引的 node 上做
   label+required_terms **精确匹配 → 0 个可富集**（见 `quality_gate_failures.json`）。
   放宽匹配可凑数，但那是**用 node 知识 loose-match 伪造题目锚点**——红线禁止。
5. **mvp-rubric-20q 是 answer-derived prototype**（INDEX 已降级为 prototype evidence）。
   答案派生 rubric 未经教材 verify-on-write + 人复核，**只能 draft**，不可 published。

## 真实门数据（来自 `quality_gate_failures.json`，无伪造）

- published=18 / draft=1（Q20-1A413000 `no_auto_certifiable_points`）/ blocked=1（Q15-NA `zero_auto_certifiable_with_high_risk`）
- 97 采分点；auto_certifiable=69；non-auto-certifiable=weak=28
- 弱源点教材锚精确富集：0

## 为什么不做同覆盖 v1

做一个输出 = v0（18/1/1）但改名 v1 的 registry，会把「仍是 20 题」包装成「全题库 v1 扩量」——
**假进展**。违背 §Less Is More / §不硬造 / First Principles。registry 行数不变、published 不变、
auto_certifiable 不变，唯一变化是文件名——没有真实能力增量。

## 解锁 v1 的最小数据条件

需要**新的可批改案例题 + 可发布 rubric**，每题至少：

- `question_id` / `question_text` / `official_answer` / `node_code`
- `gold_scoring_points`（每点 policy_type + max_score）
- 每点 `source_refs` 含 **verified textbook `chunk_id` + `textbook_quote`**（verify-on-write）
- exact_required 有 required_terms；list_rule 有 denominator/item set；calculation 有 calculation_spec

第一批最小规模建议：**新增 20–30 道案例题 / ≥100–150 采分点**，published 不强求但必须真实，draft 允许但不 auto-certify。

→ 该数据由「案例题 + rubric 数据扩产管线」产出，见
`docs/plan/2026-06-04-luban-case-rubric-data-expansion-plan.md`。一旦有 ≥N 道带 rubric 的新题，
v1 编译器（源无关投影 + 现有 quality gate + ArtifactRuntimeGate 消费链）即可一次成型。
