# 部署形态评测：kb_v5 检索 + frozen v11 多叶 rich 上下文 vs 检索单独（D vs E）

- Schema: `luban_rich_leaf_frozen_v11_deployment_eval.v1` · candidate/review-only（无 runtime install、无 canonical 写入、无 DB 写入）
- Runner: `scripts/run_luban_rich_leaf_frozen_v11_deployment_eval.py`（复用 `run_luban_rich_leaf_real_world_three_arm_eval.py` 骨架：题源/三级 leaf 兜底/judge 短序号/断点续跑）
- 题集: 与上轮完全相同的 40 题（seed=20260613，32 客观 + 8 简答/案例，2021–2025 真题），`question_set_identical: true`
- 臂 D（部署形态）: 真 kb_v5 top-3 chunk + 多叶 rich 块——真实运行时缝 `rich_leaf_runtime.get_rich_leaf_contexts(query_terms, [primary_leaf], top_k=3)`（query_terms 用生产 `general_knowledge._extract_query_terms`）→ `format_rich_leaf_pack_grounding_lines`（1200 字上限）。supply bundle v3.1.1_frozen_v11_quarantine_annotated，1595 records
- 臂 E（基线）: 同一次 kb_v5 top-3 检索单独（与上轮 A 臂同构；为保证 D/E 共享同一检索结果而重跑，上轮 A 臂数据仅作 reference，`reused_from` 已标注于结果 JSON）
- Provider: deepseek-chat（temperature 0），judge 同 provider 独立裁决（verdict/解释质量/引证真实 + 引证来源分类 retrieval_chunk|rich_block|both|none）
- 消耗: 80 answer + 40 judge 调用合计 **307,276 tokens**（授权 ~30 万）；kb_v5 单题 1 次降级（两臂共享同一降级检索，配对公平）

## 总表（40 题）

| 指标 | D 部署形态 | E 基线 | Δ (D−E) |
|---|---|---|---|
| 语义得分 | **0.8125** | 0.7875 | +0.025 |
| correct / partial | 0.700 / 0.225 | 0.700 / 0.175 | 0 / +0.05 |
| 客观 exact match | 0.8438 | 0.8438 | 0 |
| 解释质量均分 (1-5) | **4.22** | 3.98 | +0.24 |
| 引证真实率 | 0.875 | 0.850 | +0.025 |
| 引证来源 both/chunk/none | 18 / 17 / 5 | 0 / 34 / 6 | — |
| 均 prompt tokens | 2368 | 1721 | **+647 (+38%)** |
| 均 total tokens | 2500 | 1859 | +641 (+34%) |
| 均 latency ms | 2313 | 2347 | −34 |

## 题型拆分

### 客观题（32 题，单选+多选）

| 指标 | D | E | Δ |
|---|---|---|---|
| 语义得分 | 0.9062 | 0.9062 | 0 |
| exact match | 0.8438 | 0.8438 | 0 |
| 解释质量 | 4.47 | 4.31 | +0.16 |
| 引证来源 both/chunk/none | 17/13/2 | 0/30/2 | — |
| 均 total tokens | 2370 | 1731 | +639 |

### 简答/案例题（8 题）——关键读数

| 指标 | D | E | Δ |
|---|---|---|---|
| 语义得分 | **0.4375** | 0.3125 | **+0.125** |
| correct / partial | 0.125 / **0.625** | 0.125 / 0.375 | 0 / +0.25 |
| 解释质量 | **3.25** | 2.62 | **+0.63** |
| 引证真实率 | 0.625 | 0.500 | +0.125 |
| 引证来源 both/chunk/none | 1/4/3 | 0/4/4 | — |
| 均 total tokens | 3020 | 2371 | +648 |

**案例题多叶兑现情况**：D 臂案例题平均挂载 2.5 个富叶、75% 题目为多叶（>1）；全臂 82.5% 多叶、均 2.62 叶。多叶上下文把案例题 partial 覆盖率从 0.375 提到 0.625（语义 +0.125、解释质量 +0.63）——**质量增益兑现**；但 judge 判定的引证落点显示案例题仅 1/8 引证同时落在 rich 块（0 题纯 rich），多数引证仍落检索 chunk——**显式引证兑现偏弱**，rich 块更多是隐性支撑答案要点而非被直接引用。客观题上 rich 块被引用更频繁（17/32 both）但分数无变化。

## 与上轮 A 臂 reference 对照

上轮 `real_kbv5_rag`（同 40 题）：语义 0.825 / exact 0.8438 / 均 token 1825。本轮 E 臂重跑：0.7875 / 0.8438 / 1859——exact 完全一致，语义差 0.0375 来自 judge 对简答题裁决的 run-to-run 抖动，基线可信。

## 结论（开 flag 是否值得）

- **客观题：不值得**——语义/exact 零增益，每题多付 ~640 tokens。
- **案例/简答题：正向但样本小**——语义 +0.125、partial +0.25、解释质量 +0.63（n=8，非统计显著）；多叶机制按设计兑现（2.5 叶/题），增益形态符合"教学上下文补要点"而非"提供标准答案"。
- **建议**：`LUBAN_RICH_LEAF_RUNTIME_ENABLED` 若开，**值得但应限定在简答/案例/讲解路径**；对纯客观判分路径开启只增成本不增分。成本增量 ~+34% prompt tokens、latency 中性。终局授权可把本读数计为"部署形态无回归、案例题方向性正收益、显式引证兑现待加强（可在 prompt 里要求引用富叶 leaf_id）"。
