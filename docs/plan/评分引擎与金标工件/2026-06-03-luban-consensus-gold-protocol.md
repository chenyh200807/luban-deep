# 鲁班案例题 Consensus-Gold Protocol（多模型陪审团 gold,替代大量人工标注）

> Status: directional/shadow 方法论 v1（2026-06-03）。不进生产门、不接 RAG、不碰 `CaseGradingSkillKernel` runtime、不改 golden fixture。
> 代码:`scripts/build_luban_consensus_gold.py`；验证产物:`artifacts/luban_consensus_gold/po_slice_20260601_dev/consensus_gold.json`。

## 1. 要解决的问题

案例题批改要有 gold（标准）才能验证 AI 阅卷器。两条老路都不够:

- **大量真人标注**:贵、慢、单人有噪声、不可放量到新题。
- **单个 LLM 当 gold**:有 **相关性盲区（correlated blind spot）**——若 gold 模型和被测模型共享同一个系统性错误（实测:GPT5.5/Opus4.8 对"大白话/近义词"系统性放水），则"被测 ≈ gold"会让你**自信地认证一个一致地判错的阅卷器**。

**关键前提**:一建案例题不是开放作文,它有**官方标准答案 + 评分细则 + 踩字规则**=客观锚。真人和 LLM 都只是这个标准的近似;真人不是 ground truth。

## 2. 方法

**Gold = 官方标准锚定的多模型对抗陪审团（离线,一次性）。**

1. **学生侧**:LLM 模拟的多样学生答案（archetype 覆盖满分/部分/大白话/算错/方向错…）。已有 5 份/case。
2. **教师/gold 侧**:**异质的 4 个模型各自独立判**——GPT5.5 / Opus4.8 / DeepSeek-V4 / Qwen3.7。异质性是破盲区的关键:不同训练源不易共享同一盲区。
3. **共识分级**（按 hit-label：hit/partial/miss）:
   - **全一致(4/4) → 自动 gold,高置信。**
   - **多数(3/4) → gold,中置信**（实测可靠性较低,建议并入校准队列）。
   - **分裂(无多数) → `needs_human_calibration`**,进人工/官方答案薄校准。
4. **唯一人工螺丝**:只在前沿点（多数+分裂）对照**官方标准答案**拍板,检测陪审团是否集体漂移。不是批全部。

## 3. 已验证结果（dev 切片 131 点,有真人对照）

| basis | 点数 | 对真人一致率 |
|---|---:|---:|
| unanimous_consensus(4/4) | 108 | **0.981** |
| majority_consensus(3/4) | 17 | 0.765 |
| split_frontier_needs_human | 6 | flag |
| **auto-gold 合计(去前 needs_human)** | 125 | **0.952** |

- **82% 的点四模型独立全一致 → 98% 贴真人 → 零人工。**
- 人工成本从 **175 行 → ~23 个前沿点**（17 弱多数 + 6 分裂）,可放量到 held-out / 新题。

## 4. 关键负结果(必须记录,避免重蹈)

**给共识 gold 加"确定性 list_rule k/n 覆盖"会退化:0.952 → 0.913。**
- 初衷:修"模型把近乎答全(6/7)四舍五入成 hit"的盲区。
- 实测:用 `required_terms` 正则计数覆盖 34 个 list_rule 点,**修了 2 个盲区却打坏 7 个**——正则 over/under-count,而**模型语义读学生答案数得对**。
- 这是**第三次**同一教训（前两次:required_terms 全局硬门退化、calc validator label 抽取假阳性):**确定性术语匹配 < LLM 理解**。
- 结论:**纯多模型共识,不加确定性术语覆盖**。`--list-rule-deterministic` 仅留作存档,默认关闭。

## 5. 盲区与前沿的性质(诊断洞察)

- **2 个"四模型全一致≠真人"的盲区**:Q5 列举题近乎答全（6/7、4/6）→ 四模型 hit、真人 partial。属"凑整"边界,**不是踩字语义错**;确定性修反而更糟（见 §4）,接受为 ~2% 残留。
- **6 个分裂点暴露一条轴:GPT/Opus 松 ⟷ DeepSeek/Qwen 严**（踩字边界）。真人 4/6 跟随**严**的一派（DeepSeek/Qwen）。→ 这**再次坐实生产选 qwen3.7-plus**:它踩字严、贴真人、无 GPT/Opus 放水盲区。

## 6. 离线 gold vs 生产 grading（两套,绝不混用）

| | 离线/建 gold（一次性,烧 token 没关系） | 生产/服务（每答案,便宜快） |
|---|---|---|
| 谁 | 4 模型对抗陪审团 | **单模 qwen3.7-plus 关思考,一遍** |
| 频率 | 建一次;加新题/月度审漂移才重跑 | 每份答案 1 次 |
| 成本/学生 | ≈ 0（不是 per-user） | ≈ 1 次便宜调用 |

离线陪审团除了出 gold,还产出:**① 难案例 few-shot 范例**（蒸馏进生产单模）；**② 回归门**（改 prompt/模型后用冻结 gold 秒级抓回退）。生产唯一"按需一点对抗":单模**低置信/无 span/命中已知难型**的极少数点才升级第二意见或人审。

## 7. 用法

```bash
python scripts/build_luban_consensus_gold.py \
  --model gpt55_primary=<preds>.json \
  --model opus48_reviewer=<preds>.json \
  --model deepseek_primary=<preds>.json \
  --model qwen_primary=<preds>.json \
  --packet <agentic_grading_packet>.json \
  [--human <po_labels_filled>.csv]  # 可选,验证 auto-gold 对真人吻合度
  --out <consensus_gold>.json
```

## 8. 下一步

1. **held-out 40 样本自动出 gold**:先在 held-out 包上跑齐 4 模型预测（现仅 qwen），再跑本 builder → 免去 175 人工标注,只校准 held-out 的前沿点。
2. 用陪审团 gold（unanimous 部分）当**回归门**,固化到 CI,守住生产单模质量。
3. 前沿点的薄校准对照官方标准答案,沉淀成 few-shot 范例反哺生产 prompt。

## 9. held-out v1 收口（2026-06-03,已跑完）

held-out 40 样本/175 点四模型跑齐(GPT/Opus/DeepSeek/Qwen,span guard unsupported-positive=0)。`scripts/build_luban_frontier_adjudicated_gold.py` 把 39 frontier 确定性收口:

- frontier 39 → resolved 27（with_dissent 14 + score_normalized 13）+ needs_policy_review 12。
- **consensus_gold_v1 = 136 full + 27 resolved = 163 点 = auto-gold 覆盖 93.1%**;policy queue 仅 12。
- 生产候选重评(leave-one-out vs v1):**Qwen3.7 no-think hit_agreement 0.9571、delta 0.0264、exact_required/penalty 重大违规 0、unsupported 0 → 过结论门,remains production shadow candidate**;7 个分歧全为列举题凑整(benign)。DeepSeek LOO 0.9939。
- 证据:`artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/FINDING_consensus_gold_v1_heldout_20260603.md`。

## 10. regression gate（shadow-only,runner 已实现）

2026-06-03 已新增 **`scripts/run_luban_consensus_gold_shadow.py`**，把 `consensus_gold_v1` 冻结成 manifest/hash，并提供一条命令对候选模型 predictions 做离线回归门。该 gate **不进 `pr_gate_core`、不进 production runtime**。

- manifest:`artifacts/luban_consensus_gold/po_slice_20260603_heldout_v1/consensus_gold_v1_manifest.json`
  - `consensus_gold_v1.json` sha256 = `cadc441bedb6613b8b95901fbf417cf2ed43d63525635ddc3acff9d98b0435a9`
  - `frontier_adjudicated_gold.json` sha256 = `b7138948d1f84840bf91309e446b4c5aeddc0e41c0d23ca5c1c926de3cf43701`
  - `frontier_unresolved_queue.csv` sha256 = `32754b3aceeb184ef533f863fe89eca2714f90fe7ea59091db5f21522878e7ed`
- Qwen shadow run:`artifacts/luban_consensus_gold/shadow_runs/qwen37_nothink_heldout_v1_20260603/`
  - pass=`true`;evaluated `163`;missing `0`;hit_agreement `0.9571`;mean_abs_score_delta `0.0227`;unsupported-positive `0`;disagreements `16`;exact_required/penalty major violations `0`。
  - 16 个 disagreement 全属 `list_rule` 口径差异，其中部分是 `partial score=0` vs `miss score=0` 的 hit-label 差异，未构成踩字或罚则重大违规。
- DeepSeek shadow run:`artifacts/luban_consensus_gold/shadow_runs/deepseek_v4_heldout_v1_20260603/`
  - pass=`true`;evaluated `163`;missing `0`;hit_agreement `0.9939`;mean_abs_score_delta `0.0090`;unsupported-positive `0`;disagreements `11`;其中 `exact_required` disagreement `2`、major over-credit `1`，但 DeepSeek reviewer/backup gate 只要求 hit agreement 与 unsupported-positive。
- registry 状态:benchmark registry 接入 deferred。原因是接入需要新增 `execution_kind=consensus_gold_shadow` 并扩展 `services/benchmark` runner dispatch；当前已存在 standalone runner，足够作为 shadow gate，不应为登记 suite 扩 scope 或误入 `pr_gate_core`。

## 11. Consensus-Gold 边界（明确）
可用于:离线 gold 生产 / regression 回归门 / 模型 bakeoff / 蒸馏样本。
**不等于**真人 gold（dev 真人锚 0.95–0.98 仅背景）;**不直接进** production grading runtime;**不为覆盖率放松踩字**。

## 12. policy queue → typed policy + Qwen few-shot（2026-06-03,已跑完）

held-out consensus_gold_v1 剩的 12 个 unresolved（**未入 gold**）整理成评分政策资产:`artifacts/luban_consensus_gold/policy_queue_20260603/`。

- **分型**:list_rule_denominator 7 + exact_required_near_synonym 5;按 case Q18=6/Q10=2/Q17=2/Q13=1/Q19=1。**11/12 是"列举项数/术语口径",无踩字崩坏。**
- **Q18 集中 6 个**:11 点最大案、列举点最多、答案最长,口径前沿自然最多(qwen 计列举更严、gpt 对割补法更严)。
- **5 条 typed policy rule**(shadow_only):`list_rule_denominator_v1` / `list_rule_label_vs_score_v1` / `exact_required_near_synonym_v1` / `strict_model_disagreement_v1` / `evidence_span_quality_v1`。诊断:严派不恒对,不机械取严。
- **Qwen disagreement 覆盖(dry-run)**:Qwen 与 v1 gold 的 **16 个 disagreement 100% 被 policy rule 解释,0 unexplained**(12 denominator + 4 label-vs-score);**exact_required/penalty/calc 违规 0**——Qwen 唯一系统性分歧=list_rule 口径。
- **Qwen few-shot**:`qwen_fewshot_policy_examples.json`(12 例全 needs_policy_review,0 伪造 gold)+ `qwen_fewshot_policy_prompt.md`(含 high_risk/needs_policy_review 字段)。`runtime_status: shadow_only`,**不自动接线上**。
- 代码:`scripts/build_luban_policy_queue.py`、`scripts/build_luban_qwen_fewshot.py`;测试:`tests/scripts/test_luban_policy_queue.py`。
- **下一步**:用该 few-shot prompt 重跑 held-out Qwen shadow → 看 list_rule disagreement 是否下降且无踩字回退;12 unresolved 最终入 gold 仍需对官方答案/强模型仲裁,不在本轮。

## 13. Qwen few-shot prompt A/B shadow（2026-06-03,已跑完 → **NO-GO**）

把 §12 的 few-shot policy prompt **抽象化(剥掉所有 held-out 题号/学生/hit-score,0 target leakage)**注入生产候选 qwen3.7-plus no-think,在同一 held-out consensus_gold_v1(163 点)A/B。`artifacts/luban_consensus_gold/qwen_fewshot_ab_20260603/`。

| 指标 | baseline | few-shot | Δ |
|---|---:|---:|---:|
| hit_agreement | 0.9571 | 0.9509 | −0.0062 |
| score_delta | 0.0227 | 0.0404 | +0.0177 |
| unsupported_positive | 0 | 1 | +1 |
| **list_rule 分歧** | 16 | 14 | **−2 ✅** |
| **exact_required 分歧/major** | 0/0 | 2/1 | **+2/+1 ❌** |
| gate pass | True | **False** | — |

**判定 NO-GO**:few-shot 确实降了 list_rule 分歧(目标达成),但把 baseline 本已 0 分歧的 **exact_required 搞乱了**(Q18 S2 P2 过严判 miss、S4 P10 过松判 hit),引入 1 major violation + 1 unsupported,gate FAIL——典型"模型过度套用 few-shot,原本正确点变错"。

**保留/删除**:保留 list_rule 指导(k/n、label-vs-score,有效且无回退);**删除/不注入 exact_required 近义指导 + 全局'吃不准标 review'**(qwen exact_required 本已全对,加了只制造不稳定)。**下一步:list_rule-only 精简 few-shot 再 A/B**,整版 few-shot 不进下一轮、不接线上/runtime。代码 `scripts/build_luban_qwen_fewshot_ab.py`,测试 `tests/scripts/test_luban_qwen_fewshot_ab.py`。

## 13.1 Qwen list_rule-only A/B（2026-06-03,已跑完 → **NO-GO,且比整版还差**）

只留 list_rule 口径(k/n、label-vs-score)、删掉所有 exact_required/近义/全局 review 指令,leak-safe 注入 qwen no-think,同一 163 点 A/B。`artifacts/luban_consensus_gold/qwen_list_rule_only_ab_20260603/`。结果:hit 0.9571→**0.9264**、**list_rule 分歧 16→20(不降反升)**、exact_required 0→2(含 1 major)、unsupported 0→1。

**结论(两轮一致)**:给 qwen 注入任何评分政策 prompt 都是**负收益**——prompt 在它本已正确处制造的扰动 > 在 list_rule 上偶发的收益。**baseline 裸 prompt(0.9571 / 踩字 0)就是 qwen 这条线的最优态。Qwen few-shot 蒸馏线收尾。** 代码 `scripts/build_luban_qwen_list_rule_only_fewshot.py`,测试 `tests/scripts/test_luban_qwen_list_rule_only_ab.py`。

## 14. 4-model 扩样 + DeepSeek-V4-flash 蒸馏验证（2026-06-03）+ **leave-one-out 公平口径**

`artifacts/luban_consensus_gold/expanded_4model_deepseek_distillation_20260603/`。回答"未来生产用 DeepSeek 单模型还是继续调 Qwen"。

**方法学新增——leave-one-out 反自一致泄漏**:陪审团成员当被测时,**绝不能用包含它自己那一票的 gold 评它**(否则是自己跟自己比,虚高)。DeepSeek 用 {gpt,opus,qwen} 当 gold,Qwen 用 {gpt,opus,deepseek} 当 gold,各自被另外三个异质模型评。

| 模型(LOO) | hit_agreement | score_delta | 分歧 |
|---|---:|---:|---:|
| **DeepSeek-V4-flash**(gpt+opus+qwen 评) | **0.9930** | 0.0054 | 6(全 list_rule:5 四舍五入+1 踩字放水) |
| Qwen3.7-plus no-think(gpt+opus+deepseek 评) | 0.9211 | 0.0362 | 16 |

**DeepSeek 比 Qwen 高 +0.072(干净口径)**,且 avg latency 5.0s vs 7.3s、p95 7.8s vs 21.3s。含 juror 的 gold 上 DeepSeek=0.9939 ≈ LOO 0.9930 → **强是真的,不是自一致刷的。**

**Gate=NO-GO(原则性,仅 1 个踩字点)**:唯一卡点 `exact_required_major_violation>0` = Q10/S2/P4(DeepSeek 给"普通钢筋调直机"partial 0.5,三模一致 miss)。除该点外 6 条 Strong-GO 阈值全过。**最小 fallback**:exact_required 点上"近义/半术语给 partial"→ 路由 `high_risk_review`,即可消该点、提到 Strong-GO,**无需第二 reviewer 模型**(错误极度集中)。

**结论**:离线 gold/policy 继续用 4 模型陪审团;生产 runtime 候选 = **DeepSeek-V4-flash 单模型 + exact_required→high_risk_review 最小 fallback**。代码 `scripts/build_luban_4model_deepseek_distillation.py`,测试 `tests/scripts/test_luban_4model_deepseek_distillation.py`。directional/shadow,不进 runtime。

## 15. DeepSeek 最小 exact_required fallback 验证（2026-06-03 → held-out **STRONG-GO**）

`artifacts/luban_consensus_gold/deepseek_exact_required_fallback_20260603/`。验证 §14 提出的最小 fallback:**exact_required 点上模型 rationale 自承认"近义/半术语/缺术语"却给正分 → 移出 auto-grade、转 high_risk_review(不改判 miss、只对 exact_required)。**

| 切片 | exact_major before→after | auto_coverage | hrr | gate |
|---|---|---:|---:|---|
| held-out 175 | **1→0** | 100%→**98.16%** | 1.84% | **STRONG-GO** |
| dev 131(第二面) | **2→0** | 100%→96.18% | 3.82% | NO-GO* |

*dev NO-GO 非 fallback 失败:DeepSeek 在更难/旧 prompt 的 dev 基础一致率 ~89%<0.94(list_rule/calc 分歧,fallback 不修)。held-out 上 3 个触发点含**唯一硬违规 Q10/S2/P4** ✅ + 2 个模型自承认边界(应送审)。

**关键根因**:任务字面的 "span 不逐字含核心术语 OR 近义" OR 触发 → 21 点误伤(20 个正确 hit)、覆盖率掉 87%;砍掉 span-literal 单独触发、只用 rationale 自承认信号 → 3 点、98.16%。**极窄触发的正确实现 = 用模型自承认,不用 span byte 匹配。**

**485 扩样数据缺失,未伪造**(无 20题/100答 四模型 typed-policy 预测;`full_three_arms` 是案例级 rubric 非点级陪审)。下一步:写 production-shadow v0 plan(放行 gate 绑 485 四模型 LOO 复验)+ 补 485 数据。**reviewer 模型不需要**(错误极度集中,规则级 fallback 即可)。**Qwen few-shot 正式收尾。** 代码 `scripts/build_luban_deepseek_exact_required_fallback_eval.py`,测试 `tests/scripts/test_luban_deepseek_exact_required_fallback_eval.py`。

## 16. 485 全量 LOO 复验 + list_rule policy queue（2026-06-03）

`artifacts/luban_consensus_gold/deepseek_shadow_v0_full_485_20260603/`。485 四模型 LOO（DeepSeek excluded，jury=GPT+Opus+Qwen）：gold 422/485（full 327 + strong 95），frontier 63，deepseek 自票入 gold 0、unsupported 入 gold 0。DeepSeek + exact_required fallback：踩字硬违规 **7→0**、auto_coverage 97.4%、auto_hit 0.91→0.9246 → **WEAK-GO**。

**list_rule policy queue（收敛轮结论）**：WEAK-GO 最大残差是 list_rule（17/31）。两条 shadow 政策实测：确定性 recompute = **NO-GO**（净 −12，verbatim 不能复制陪审语义 partial）；fail_closed 隔离 = auto_hit→0.9574 但 high_risk 10.9%>10%、score_delta>0.05 → 仍 WEAK-GO。**根因是 list_rule 的语义阅卷天花板**：陪审 LLM 给近义/大白话 partial credit（天气~气候、省钱~成本低），确定性规则无法复制，语义放宽威胁踩字且 Qwen few-shot 已验证负收益。**这再次印证「确定性术语匹配 < LLM 理解」，但方向是：外挂规则补不了语义阅卷，要靠模型本身。** 16 frontier/list_rule 口径点入 policy queue，不强行入 gold。代码 `scripts/build_luban_485_list_rule_policy.py`，测试 `tests/scripts/test_luban_485_list_rule_policy.py`。directional/shadow，不进 runtime。

## 17. QWK 指标治理 + 选择性弃权(2026-06-04 → STRONG-candidate / legacy 仍 WEAK-GO)

`artifacts/luban_consensus_gold/list_rule_semantic_model_bakeoff_20260603/` + `.../selective_abstention_qwk_20260604/`。两步推进:
- **模型侧语义协议(Arm2,改 prompt 不加规则)**:DeepSeek-flash auto_hit 0.9244→0.9493、exact_required 硬违规 0、unsupported 0;唯一卡点 raw score_delta。证明 list_rule 语义 partial 能由模型协议解决且不伤踩字(Arm3 strict-then-semantic 渗进 exact_required → NO-GO)。
- **QWK 指标治理**:raw mean_abs_score_delta 被高分值采分点结构性放大(4+ 桶 raw 0.97 / 题归一化 0.0277),世界标准 ordinal 口径是 QWK。新增 `scripts/luban_grading_metrics.py`(本地 QWK)+ `qwk_metric_diagnostics.json`。**QWK 仅 candidate_only**,硬门(exact_required/unsupported/penalty 零容忍 + evidence_span 可追溯 + 采分点教材溯源)永不被 QWK 抹平;升 binding gate 须独立治理 PR、冻结定义在先。计划 `docs/plan/2026-06-04-luban-grading-metric-governance-qwk-plan.md`。
- **选择性弃权(risk-coverage)**:用离线陪审分歧 + 模型可观测信号(list_rule-partial / 弱 span / hedge 词)排序,弃权最不确定的正分点(只转 high_risk_review、不改分)。操作点 tau=3.3:high_risk **3.32%**、auto_hit **0.9632**、QWK **0.9618**、踩字/unsupported/penalty **全 0**。
- **三种 gate(防偷换)**:legacy(raw delta)= **WEAK-GO**(0.0589>0.05);metric-v2 QWK candidate = **STRONG-candidate(candidate_only)**;product test = **OK 进 AI-Draft/teacher-review A/B**(不宣称生产准确率)。
- 仍不进 runtime;离线信号不进 runtime 评分权威。代码 `scripts/build_luban_selective_abstention.py`,测试 `tests/scripts/test_luban_grading_metric_qwk.py` + `test_luban_selective_abstention.py`(21 passed)。
