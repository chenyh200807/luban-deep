# 鲁班 V1 开放世界评分 — 收敛+加固执行计划（治本，非打补丁）

**日期**：2026-06-07
**目标**：确认并保证 V1 能**全面、稳健**地评判开放题目；同时清除曲折开发中堆积的重复/矛盾/死代码，收敛到**单一 V1 评分权威**。
**三大原则贯穿**：thin wrappers & fat skills（判分逻辑全在 `rubric_grader_v1.py`，`deep_question.py` 只薄接线）、first principles（案例判定=非选择+有参考答案；分数=逐采分点确定性求和）、less is more（先减后强，不新增并行路径/字段）。

## 根因归并（7 问题 → 3 簇）

- **根因①「实验未退役」**：`_emit_grading_result` 挂 6 条 append-only 影子评分 lane（runtime_shadow / v1_beta_shadow / v1_controlled_runtime / v1_llm_adjudication / objective_candidate / textbook_knowledge），运行时多权威竞争 + flag 泛滥。**唯一影响学生 answer 的是 V1（luban_case_rubric_v1）**；其余对真实学生 byte-identical（客户端只读 `response`、默认关、零生产消费者）。
- **根因②「V1 被当查表接线」**：触发受 `_CASE_TYPES` 封闭枚举 + batch 漏判限制。第一性原理：非选择题+有参考答案即主观可判。
- **根因③「确定性脊柱不完整」**：开放世界分值不归一（满分漂移 2.0 vs 6.0）、is_correct/score 与 V1 不同源、concept_id 用 point_id 污染 canonical、错误吞没无日志。

## 关键事实（专家 subagent 核实，file:line 见各 spec）

- `correct_answer` 在 grading turn **可达** `graded_context`（normalize 白名单保留 `question_followup.py:264`）；`analysis` 被 normalize 剥离 → 开放世界抽取实际只能靠 `correct_answer`。
- `_normalize_question_type` 已把多数主观写法压成 `written`（∈ `_CASE_TYPES`）→ live 真缺口主要是 **batch**；枚举仍是脆弱隐式契约，改为显式第一性原理判定。
- V1 的 `to_learning_evidence` 当前是**孤儿**（无生产持久化消费）→ concept_id 修复零现网风险（拆未来炸弹）。
- 客户端 `chat.js` 只读 `d.response` → 退役 append-only lane 对 UI 零影响。
- `is_correct→recent_outcomes→难度步进`（progressive_disclosure）是 V1 不同源唯一能到生产的实际通路。

## 实施（3 批 TDD，每批先红→实现→回归→commit）

### 批1：簇③ 确定性脊柱（fat skill 纯函数）
1. 日志去吞没：`rubric_grader_v1` + `deep_question` 加 `logger`，所有 except `logger.warning(exc_info=True)`，返回值/降级不变。
2. concept_id 不冒充 canonical：`to_learning_evidence` 开放世界 `concept_id=None` + `concept_provenance`；守护 `writeback_performed`/`official_score_allowed` 恒 False。
3. 分值归一：新增 `normalize_points_to_nominal(points, nominal_total)`，**仅**开放世界抽取产物缩放到 `cg["max_score"]`（无则基准 10），compiled rubric 不碰。
4. 同源：新增 `derive_outcome_from_event(event)`，V1 接管时覆盖 `graded_context` 的 is_correct/score/diagnosis（单一来源）。

### 批2：簇② 触发覆盖（adapter + capability 薄接线）
5. `deep_question_adapter`：`_KNOWN_CASE_TYPES` 快路径 + `_has_reference_answer` + `_is_subjective_context`（非选择+有参考答案），**纯增量**（只增不减 case 覆盖）；`_is_choice_context` 不动。
6. batch：`_grade_case_rubric_v1` 顶层 `type=="batch"` 时遍历 items 逐个走同一 V1 链（不复制判分逻辑），渲染聚合。

### 批3：簇① 退役死 lane（less is more，本次只动 live 接线）
7. 删 `_emit_grading_result` 内 6 条 `_maybe_attach_*` 调用 + 其专属 flag/env/cohort helper；保留 V1。
8. 删 8 个直调被删 wrapper 的测试文件。
9. **模块文件 + 里程碑测试 + 重复实现收敛**（采分点拆分 4 份、learning_evidence 投影 3-4 份）→ **独立 PR**，避免 mega-diff。

## 验证
- 每批：相关单测先红后绿 + `pytest tests/core/test_deep_question_*.py tests/services/construction_grading/ -q` 零回归（pre-existing `test_related_generation_anchor` 失败与本工作无关，已 stash 验证）。
- 真实 `/api/v1/ws`：题型矩阵（简答/判断改正/列举/计算/多问/batch/无参考答案/选择题）逐一验 V1 触发与否符合预期、分值同尺度、is_correct 同源。
- 不变量：official_score_allowed/writeback_performed 恒 False、construction_grading_result append-only 不被 mutate、flag-off byte-identical、chat.js 无需改。

## 不确定性与替代
- U1：线上"仅 analysis 无 correct_answer"题占比未知 → 默认不补 analysis 白名单（less is more）；若数据显示占比高，再补 + 评估 redaction。
- U2：batch 多 case 题频率低 → 实现保持最小；多 case 聚合渲染若复杂则降级单 case 处理 + 标 follow-up。
- U3：簇②扩大 case 集会同时影响 V0（有参考答案的非枚举题改为 V0 评分而非不评分）→ 视为更优行为，靠全量回归兜底；若回归翻红则回 Phase 1 重评。
