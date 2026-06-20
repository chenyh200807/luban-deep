# FINDING — QuestionGradingArtifact Registry v1 = DATA-BLOCKED (2026-06-04)

> 状态：**data_blocked**。不产出同覆盖 v1。可发布 authority 仍为 20 题 golden。

## 必答 7 问

1. **为什么当前不能发布全题库 v1？**
   20 题之外不存在可批改主观案例题的 rubric authority 数据；62 真题是 MCQ（出范围）；6134 节点资产是
   node-level 知识非题目；唯一非 golden 的 case rubric（mvp-rubric-20q）是 prototype。无新可发布数据 → 无法扩量。

2. **当前可发布 authority 仍只有 20 题 golden / 97 points？** 是。
   published=18 / draft=1（Q20）/ blocked=1（Q15-NA）；97 采分点；auto_certifiable=69 / weak=28。

3. **v0 弱源点为何不能被 6134 节点资产自动富集？**
   对 28 个弱源点在 16 个 textbook-anchor node 上做 label+required_terms **精确匹配 = 0 命中**。
   放宽匹配能凑数但等于用 node 知识 loose-match 伪造题目锚点（红线禁止）。

4. **MCQ 为什么不进 case scoring registry？**
   MCQ 由 `grade_mcq_submission` 判分（选项匹配），不依赖采分点/教材锚；塞进 case 采分点 registry 是 scope 污染。

5. **mvp-rubric-20q 为什么只能 draft/prototype，不可 published？**
   它是 answer-derived rubric extraction，未经教材 verify-on-write + teacher/PO 复核；INDEX 已降级为
   prototype evidence。未验证来源不可 auto_certifiable，故只能 draft。

6. **不做同覆盖 v1 的原因？**
   输出 = v0（18/1/1，97 点）改名 v1 = 假进展。published/auto_certifiable 零增量，只换文件名，违背
   §Less Is More / §不硬造 / First Principles。

7. **解锁 v1 的最小数据条件？**
   新增可批改案例题（≥20–30 道 / ≥100–150 采分点），每题带 official_answer + gold_scoring_points +
   **verified textbook chunk_id+quote** + typed_policy，经 teacher/PO 复核。由数据扩产管线产出
   （`docs/plan/2026-06-04-luban-case-rubric-data-expansion-plan.md`）。

## 红线确认

不产出同覆盖 registry 冒充扩量 / 不把 MCQ 塞进 case registry / 不把 6134 node 资产当 question rubric /
不伪造 source_ref / 不把 official_answer 当 textbook 强锚 / 未接 production runtime / 未改 kernel·RAG / 未新增表。

## 产物

- `input_source_audit.md` — 逐源核验 + 富集探测
- `data_blocker_report.md` — 阻塞链 + 解锁条件
- `quality_gate_failures.json` — 真实门数据（28 弱源点 / 0 富集 / blocked·draft 原因）
- 本 FINDING

## 下一步

不建同覆盖 v1。走数据扩产计划（A 线真正前置）+ runtime 真实化（B 线）。v1 编译器仅留 data_blocked skeleton
（`scripts/build_luban_question_grading_registry_v1.py`：无新源 → 输出 data_blocked，不生成假 registry）。
