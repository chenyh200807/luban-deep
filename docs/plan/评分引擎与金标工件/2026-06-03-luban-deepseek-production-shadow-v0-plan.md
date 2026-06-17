# 鲁班案例题批改 DeepSeek production-shadow v0 实施计划

> Status: `Proposed v0`（2026-06-03）。**directional/shadow——不进 production runtime、不接 RAG、不碰 `CaseGradingSkillKernel`、不改 consensus gold、不用 Qwen few-shot、不接在线 reviewer。**
> 本计划是从「研究轮」推进到「production-shadow v0 准备」的可执行方案,**不是大平台总纲**。放行前置条件硬绑定 **485 四模型 LOO 复验**。
> 前序证据:`docs/plan/2026-06-03-luban-consensus-gold-protocol.md` §14/§15;`artifacts/luban_consensus_gold/expanded_4model_deepseek_distillation_20260603/`、`.../deepseek_exact_required_fallback_20260603/`。

## 0. 一句话定位

未来生产主模型 = **DeepSeek-V4-flash 单模型批改 + exact_required rationale-based high_risk fallback + span guard + 结构化 JSON**;离线 gold/policy 生产 = **GPT5.5 / Opus4.8 / DeepSeek / Qwen 四模型陪审**。本计划只把这条路线写成可执行 shadow,**不上线正式评分 authority**。

## 1. 已确认事实（前序轮)

- DeepSeek-V4-flash held-out **LOO hit=0.9930 / score_delta=0.0054**,明显优于 Qwen LOO 0.9211;更快(avg 5.0s vs 7.3s、p95 7.8s vs 21.3s)。
- exact_required 极窄 fallback 后 held-out:**exact_required_major_violation 1→0、auto_coverage 98.16%、auto subset hit 1.0、gate=STRONG-GO**。
- dev 切片 fallback 也把 hard violation 2→0,但基础一致率 ~89%(更难+旧 prompt+含 deepseek juror 的 gold)→ **必须做 485 复验**才能宣告生产精度。
- 485 四模型 typed-policy 预测**目前缺失**(只有 held-out 40 样本齐全),**不能伪造**。
- Qwen few-shot / list_rule-only 全部 NO-GO → **收尾**。

## 2. 架构定位(三层)

| 层 | 身份 | 模型/产物 | 边界 |
|---|---|---|---|
| **L1 Offline gold/policy** | 离线真相生产 | GPT5.5+Opus4.8+DeepSeek+Qwen 四模型陪审 → consensus gold / policy casebook | 一次性离线,不在 runtime |
| **L2 Production-shadow grader** | 候选生产批改器 | **DeepSeek-V4-flash 单模型**,结构化 JSON,span guard | shadow-only,不进正式评分 authority |
| **L3 High-risk fallback** | auto-certification gate | exact_required + 模型 rationale 自承认近义/半术语/缺术语 → 转 high_risk_review | **不是评分器,不二次改分**,只决定"该点能否自动认证" |

关键:L3 **不改分**。它只把可疑点从 auto-certified 移到 high_risk_review 队列,等离线陪审/人工裁。

## 3. 单一 authority

- **评分事实 authority = consensus gold / official answer / scoring point policy。** runtime 永远以这套为准。
- runtime **不允许另建第二评分器**;L2 DeepSeek grader 是候选,不是 authority。
- **fallback 不是评分器**,是 auto-certification gate;它的输出只有"auto_certified true/false",不产生分数。
- **high_risk_review ≠ 自动正确,≠ 人工已判**;它是"未自动认证、待离线陪审/人工"的中间态。

## 4. 输入 / 输出 schema（production-shadow v0,离线）

```jsonc
{
  "run_id": "ds-shadow-v0-<date>-<n>",
  "model": "deepseek-v4-flash",
  "model_version": "<provider model id>",
  "question_id": "Q18-1A434000",
  "student_answer_id": "S2",
  "scoring_points": [
    {
      "point_id": "P4",
      "policy_type": "exact_required | list_rule | calculation | penalty_rule | figure_label | high_risk_review",
      "prediction": { "hit": "hit|partial|miss", "score": 0.0 },
      "evidence_span": "<必须逐字来自学生答案>",
      "rationale": "<模型理由>",
      "unsupported": false,            // hit/partial 但无合法 span → true
      "high_risk_review": false,       // L3 触发 → true
      "review_reason": "near_synonym_rationale | exact_required_partial+span_lacks_core_term | ...",
      "auto_certified": true           // = (not unsupported) and (not high_risk_review)
    }
  ]
}
```

- `evidence_span` fail-closed:hit/partial 无 span → `unsupported=true`,不计自动认证。
- `auto_certified` 是唯一对外布尔:`auto_certified = (not unsupported) and (not high_risk_review)`。
- `high_risk_review` 只对 `policy_type==exact_required` 由 L3 置位。

## 5. Gate(v0 放行前置 = 485 四模型 LOO 复验)

> **必须在 485 点上用 leave-one-out(评 DeepSeek 时陪审 = gpt+opus+qwen,排除 deepseek 自己)复验,不能用 held-out 175 直接宣告。**

**Strong GO**:auto_coverage ≥ 90% · exact_required_major_violation = 0 · penalty_rule_major_violation = 0 · unsupported_positive = 0 · auto subset point_hit_agreement ≥ 0.94 · auto subset score_delta ≤ 0.05 · high_risk_review ≤ 10% · parse_failure_rate ≤ 1% · p95 latency 可接受。

**Weak GO**:auto_coverage ≥ 85% · hard violation = 0 · auto subset hit ≥ 0.90 · high_risk_review ≤ 15%。

**NO-GO**:hard violation > 0 · high_risk_review 过高 · DeepSeek 485 明显低于 held-out · parse/latency 不稳定。

## 6. 不做什么(硬边界)

- 不上线正式批改 / 不进 runtime authority。
- 不改 `CaseGradingSkillKernel`。
- 不让 RAG 进评分 authority。
- 不用 Qwen few-shot(已收尾)。
- 不接在线 reviewer 模型(错误集中,规则级 fallback 足够)。
- 不把 high_risk_review 当人工复核完成。
- 不把 175 点结果宣称成生产准确率。

## 7. 执行优先级(Task D)

| Phase | 内容 | 出口判据 |
|---|---|---|
| **Phase 0** 冻结结论 | Qwen few-shot 收尾;held-out fallback STRONG-GO 记为 v0 candidate evidence | 本计划落盘 + INDEX 挂载 ✅ |
| **Phase 1** 485 数据补齐 | 构建 36 缺失样本的 typed-policy packet;补齐 gpt/opus/qwen(60 样本)+ deepseek(36 样本)预测;生成 485 四模型 LOO gold | inventory `ready_for_full_485_loo=true` |
| **Phase 2** 485 fallback gate | DeepSeek before/after、hard violation、high_risk coverage、latency/cost,套 §5 gate | gate = Strong/Weak GO |
| **Phase 3** runtime 设计 | **仅当 Phase 2 过 gate** 才写 runtime 接入方案;否则只保留离线 shadow | Phase 2 GO |

**Phase 2 已执行(2026-06-03)→ WEAK-GO**:`artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/`。485 全量四模型 LOO 复验:packet 100样本/485点齐;LOO gold 422(87.01%,full 327+strong 95,deepseek 自票 0、unsupported 入 gold 0、frontier 63)。DeepSeek + exact_required fallback:**踩字硬违规 7→0**、auto_coverage 97.39%、high_risk 2.61%、auto hit 0.91→0.9246。**WEAK-GO**(未达 Strong:auto hit 0.9246<0.94、score_delta>0.05),残差主因 list_rule 口径(17)。**结论:不进 Phase 3;先做 list_rule 口径修正再 re-gate;不需在线 reviewer(踩字已被 fallback 清零)。** 详见 `FINDING_deepseek_shadow_v0_full_485_20260603.md`。

**Phase 2.1 list_rule 收敛轮已执行(2026-06-03)→ 仍 WEAK-GO**:17 个 list_rule 残差分型(label_vs_score 8 / generic_label 5 / denominator 2 / span_insufficient 1 / frontier 1),实测两条 shadow 政策:**确定性 recompute = NO-GO**(净 −12,verbatim 无法复制陪审语义 partial,打破 21 个原本正确点);**fail_closed 隔离** auto_hit 0.9244→0.9574(过 0.94)但 high_risk 升至 10.9%>10% 且 score_delta 0.0748>0.05 → 仍 WEAK-GO。**根因 = list_rule 语义阅卷天花板(陪审 LLM 给近义/大白话 partial,确定性规则不可复制,语义放宽威胁踩字且 Qwen 已验证负收益);score_delta 是大分值 partial 的结构性大差。三臂全程 exact_major/penalty/unsupported=0。** 建议采纳 fail_closed 作 directional guardrail、维持 WEAK-GO、不进 runtime;真正推 Strong 需更强语义阅卷模型本身。代码 `scripts/build_luban_485_list_rule_policy.py`,详见 `FINDING_485_list_rule_residual_20260603.md` + `list_rule_policy_v1_casebook.md`。

**Phase 2.2 模型侧语义协议 + QWK 治理 + 选择性弃权(2026-06-04)→ legacy WEAK-GO / metric-v2 STRONG-candidate**:推翻"必须换更强模型"的悲观结论——**模型侧语义协议(改 prompt 不加规则)即可**:Arm2 让 DeepSeek-flash auto_hit 0.9244→0.9493、踩字 0、unsupported 0(Arm3 strict-then-semantic 渗进 exact_required → NO-GO)。残差 score_delta 经诊断是 raw MAE 错口径(QWK=0.9338、题归一化 0.0117)。**选择性弃权**(离线陪审分歧 + 模型可观测信号排序,只弃权不改分)在 high_risk 3.32% 下达成 auto_hit 0.9632、QWK 0.9618、硬门全 0。**三种 gate**:legacy(raw delta)WEAK-GO、metric-v2 QWK **STRONG-candidate(candidate_only)**、product test **OK 进 AI-Draft/teacher-review A/B**。**结论:不接 runtime;先做 metric-v2 治理 PR + 测试环境 A/B(AI-Draft) + 采分点教材溯源编译放量;不为 legacy 过门改 gate。** 计划 `docs/plan/2026-06-04-luban-grading-metric-governance-qwk-plan.md`,代码 `scripts/luban_grading_metrics.py` + `scripts/build_luban_selective_abstention.py`,详见 `FINDING_selective_abstention_qwk_20260604.md`。

## 8. 485 复验执行准备(指向产物)

- 资产盘点:`artifacts/luban_consensus_gold/deepseek_shadow_v0_485_prep_20260603/485_asset_inventory.json`
  - 现状:target 100 样本/485 点;typed-policy packet 64 present / 36 missing;**four-model ready 40 / missing 60**;per-model preds gpt40 opus40 qwen40 deepseek64。`ready_for_full_485_loo=false`。
- 缺口清单:`.../485_missing_predictions.csv`(60 行)。
- 执行清单:`.../485_execution_plan.md`(逐模型补齐脚本/命令/调用次数/成本)。
- pilot:`.../485_pilot_*`(见执行清单;真实小批验证管线,不伪造)。

## 9. 相关代码入口

- L2 grader / fallback:`scripts/build_luban_deepseek_exact_required_fallback_eval.py`。
- L1 四模型陪审 / LOO:`scripts/build_luban_multimodel_jury_gold.py`、`scripts/build_luban_4model_deepseek_distillation.py`。
- 四模型 runner(qwen/deepseek 自动化):`scripts/run_luban_unified_typed_policy_models.py`;GPT5.5 via Codex CLI、Opus4.8 via subagent。
- 485 prep:`scripts/build_luban_deepseek_shadow_v0_485_prep.py`。
- 测试:`tests/scripts/test_luban_deepseek_shadow_v0_plan_assets.py`、`test_luban_deepseek_exact_required_fallback_eval.py`、`test_luban_4model_deepseek_distillation.py`。

## 10. 验收标准

1. 本计划落盘 + INDEX 挂载(Phase 0)。
2. 485 inventory 能识别缺口、`ready_for_full_485_loo` 在数据不全时为 false。
3. 485 LOO gold 不含被测模型自己的 vote(LOO 纪律)。
4. fallback 只对 exact_required;high_risk_review 不进 auto_certified。
5. Phase 2 gate 在 485 上判定 Strong/Weak/NO-GO,再决定是否进 Phase 3。
