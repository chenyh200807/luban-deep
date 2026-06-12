# 鲁班案例题阅卷 评分一致性指标治理（QWK + normalized delta）—— protocol-amendment candidate

> Status: `Proposed / candidate_only`（2026-06-04）。**directional/shadow——不进 runtime、不改 CaseGradingSkillKernel、不改 consensus gold、不接 RAG。本文档只影响 shadow/eval gate 的诊断口径，不 retroactively 把历史 WEAK-GO 改成 STRONG-GO。**
> 触发背景：485 全量 Arm2 semantic protocol 已让 DeepSeek-flash `auto_hit 0.9244→0.9493`、`exact_required_major_violation=0`、`unsupported=0`，唯一卡点是 `raw mean_abs_score_delta 0.0756>0.05`，而调研与我们自己的分解都证明 raw MAE 是错口径。

## 1. raw score_delta 的问题（为什么不能单独解释阅卷质量）

- 采分点满分值异质（1 分点 ~ 4+ 分点）。对它们直接做 raw mean absolute error，**4 分点的误差天然压过 1 分点 4 倍**。
- 实测分解（`score_delta_decomposition.json`）：max_score 0-1 桶 raw 0.035，4+ 桶 raw **0.97**；list_rule 整体 raw 0.21 但 **per-question normalized 0.0277**。
- ordinal 评分的类别间距离不可比，未归一化算术平均在统计上不是「阅卷偏差」的有效估计量。
- **决定**：raw score_delta **保留为护栏**（防高分值点单点 blowup 藏在平均里），但**不再单独解释阅卷质量**。

## 2. 新增诊断指标（metric-v2 candidate）

代码 `scripts/luban_grading_metrics.py`（本地 deterministic，无 sklearn/numpy 依赖）+ `build_luban_list_rule_semantic_model_bakeoff.py --qwk`，产物 `qwk_metric_diagnostics.json`：

| 指标 | 定义 | 用途 |
|---|---|---|
| **QWK** | quadratic weighted kappa（hit-label ordinal miss/partial/hit=0/1/2），ASAP/EDM 公认 ordinal 一致性标准 | 主诊断 |
| normalized_per_point_delta | abs_delta / max_score | 诊断 |
| normalized_per_question_delta | abs_delta / question_total_score | 诊断 |
| exact_agreement / adjacent_agreement | 同档 / ±1 档 | 诊断 |
| raw_score_delta | 旧口径 | **护栏（保留）** |

**实测（485 LOO gold，full points）**：

| arm | QWK | exact_agr | adj_agr | raw_delta | norm/pt | norm/q | list_rule QWK |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0.9126 | 0.91 | 0.981 | 0.1286 | 0.0561 | 0.0164 | 0.8549 |
| **semantic_protocol** | **0.9338** | 0.9408 | 0.9834 | 0.0789 | 0.0441 | **0.0117** | 0.8761 |

> semantic_protocol QWK 0.9338（远超 ASAP human-level ~0.75）、norm/q 0.0117 ≤ 0.05。

## 3. 硬门不可替代（零容忍，永不被 QWK 抹平）

QWK/AA 对踩字是 **magnitude-symmetric**：QWK>0.75 可与一次 exact_required 踩字违规共存（被 quadratic weighting + chance correction 抹平），AA 的 ±1 容忍会把 exact_required 近义过分当「相邻可接受」。所以下列硬门**永远并列、永不可被 QWK/normalized 替代**：

- `exact_required_major_violation == 0`
- `unsupported_positive == 0`
- `penalty_rule_major_violation == 0`
- `evidence_span` 必须可追溯（逐字来自学生答案）
- 采分点 + required_terms 必须可溯源教材原文（见 consensus-gold protocol；编译轴硬约束）

## 4. 这不是「为了过门换指标」（治理纪律）

- 本轮 QWK/normalized **只作为 protocol-amendment candidate**，标 `candidate_only`。
- **不 retroactively** 把历史 WEAK-GO 改成 STRONG-GO。
- 新 gate 生效必须写明 `version_id = grading_eval_metric_v2_qwk_candidate`，并：
  1. 经 4 模型 jury rationale 评审；
  2. **冻结定义在先**（在「看到它是否过线之前」就定死阈值），绝不因为新数字恰好过 0.05/0.94 就 retrofit；
  3. 走独立 PR，不与本轮 shadow 实验混。
- `build_luban_list_rule_semantic_model_bakeoff.py` 与 `score_delta_decomposition()` 已写死 `DIAGNOSTIC ONLY`；测试断言 QWK 被报告但 binding 硬门不变。

## 5. 与现有计划的关系

- 不改 runtime（DeepSeek-flash 单模仍是 runtime 候选，离线信号不进 runtime authority）。
- 不改 CaseGradingSkillKernel。
- 不改 consensus gold。
- 只影响 **shadow/eval gate 的诊断口径**。
- 关联：`2026-06-03-luban-deepseek-production-shadow-v0-plan.md`（v0 gate）、`2026-06-03-luban-consensus-gold-protocol.md`（§14-§16）、`FINDING_list_rule_semantic_model_bakeoff_20260603.md`。

## 6. metric-v2 candidate gate 草案（仅 candidate，未生效）

`grading_eval_metric_v2_qwk_candidate`（冻结定义）：
- STRONG-candidate：`QWK ≥ 0.85`（按 policy_type 报告，list_rule 单列）AND `normalized_per_question_delta ≤ 0.05` AND 全部 §3 硬门 AND `auto_hit ≥ 0.94` AND `high_risk_review ≤ 10%`。
- WEAK-candidate：`QWK ≥ 0.75` AND 硬门全过 AND `auto_hit ≥ 0.90`。
- NO-GO：任一硬门破，或 QWK < 0.75。

> 阈值（QWK 0.85/0.75）参照 ASAP/EDM；**在评审通过前不得用于宣称生产准确率**。
