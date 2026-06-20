# Rich-Leaf Frozen v1 真实生产对照三臂评测报告 (2026-06-13)

candidate/review-only。未安装默认、未写 canonical truth、未写任何 DB。
runner: `scripts/run_luban_rich_leaf_real_world_three_arm_eval.py`（tests: `tests/scripts/test_luban_rich_leaf_real_world_three_arm_eval.py`，9 passed）
结果工件: `real_world_three_arm_eval_results.json`（schema `luban_rich_leaf_real_world_three_arm_eval.v1`）

## 设定

- **题源**：2021–2025 一级建造师《建筑实务》真题（FINAL_CLEANED_EXAM_V*.json），seed=20260613 固定抽样 40 题 = 32 客观（单选/多选）+ 8 简答/案例，金标 = 真题 correct_answer + 官方解析。
- **三臂同题同 provider（deepseek-chat, temperature 0, 45s 超时）**：
  - **A real_kbv5_rag**：真实 kb_v5 检索（`public.search_chunks_v2` 直连，dashscope 1024 维 embedding，top-3 整 chunk 注入）。检索通道全程可用，0 次降级。
  - **B rich_leaf_full**：题目 node_code/keyword 定位 frozen v1 leaf，v3.0.1 pack compiled_context 每族 2 条。
  - **C rich_leaf_guard**：同 leaf 每族 1 条 + fail-closed 护栏 prompt（v23 guard 形状）。
- **判分**：独立 judge 调用（同 provider，不同 prompt），按金标给 correct/partial/wrong + 解释质量 1–5 + 引证是否落在该臂真实证据上；judge 用短序号 1..3 防长 ID 错配，非全覆盖即降级（实际 judge 失败 0）。客观题另算确定性字母 exact match。
- **预算**：实际消耗 305,363 tokens（authorized ~400k），answer 调用 120 次 + judge 40 次，fail 率 0。

## 三臂汇总（n=40/臂）

| 指标 | A 真实kb_v5 RAG | B rich_leaf全量 | C guard生产臂 |
|---|---|---|---|
| 语义正确率 (judge correct) | **75.0%** | 60.0% | 55.0% |
| 语义得分 (correct=1, partial=0.5) | **0.825** | 0.663 | 0.600 |
| 客观题 exact match (n=32) | **84.4%** | 78.1% | 75.0% |
| 解释质量均分 (1–5) | **4.25** | 3.38 | 3.23 |
| 引证真实率 | **85.0%** | 27.5% | 25.0% |
| 均 prompt tokens | 1698.9 | 1115.1 | 959.2 |
| 均 total tokens | 1824.7 (基准) | 1223.4 (−33%) | 1067.9 (−41%) |
| 均 latency (answer call) | 2504ms (+检索均4699ms) | 2379ms | 2321ms |
| fail 率 / judge 失败 | 0 / 0 | 0 / 0 | 0 / 0 |

分题型：

| 臂 × 题型 | 语义得分 | 客观exact | 解释质量 | 引证真实率 | 均tok |
|---|---|---|---|---|---|
| A 客观(32) | 0.906 | 0.844 | 4.50 | 0.94 | 1708 |
| A 简答(8) | 0.500 | — | 3.25 | 0.50 | 2292 |
| B 客观(32) | 0.766 | 0.781 | 3.62 | 0.31 | 1111 |
| B 简答(8) | 0.250 | — | 2.38 | 0.12 | 1672 |
| C 客观(32) | 0.688 | 0.750 | 3.47 | 0.31 | 978 |
| C 简答(8) | 0.250 | — | 2.25 | 0.00 | 1425 |

题级胜负（语义得分）：A>B 10 题 vs B>A 1 题；A>C 12 题 vs C>A 1 题；B>C 4 题 vs C>B 1 题。

## 诚实结论

1. **这次 A 是真检索堆料，真实差距比此前投影口径大**：真 kb_v5 top-3 整 chunk 只比 rich_leaf 全量臂多 ~49% prompt tokens（1825 vs 1223），却换来 +16 个百分点语义得分（0.825 vs 0.663）、+0.87 解释质量、引证真实率 85% vs 27.5%。在真实考题分布上，frozen v1 编译包**没有**达到真实 RAG 的语义能力。
2. **根因主要是覆盖/定位，不是编译质量本身**：40 题中只有 18 题 node_code 精确命中 leaf，11 题落到同族（6位前缀），11 题纯 keyword 兜底。frozen v1 pack 只覆盖 43 个 node 前缀，而五年真题分布在 77 个 node。leaf 不对位时，模型只能靠参数化知识答题——客观题还能撑（B 客观 exact 78%），但引证落不到真证据上（引证真实率 27.5% 的主因是供给缺口，不全是幻觉）。
3. **简答/案例题三臂全弱，B/C 尤其差**（A 0.50 / B 0.25 / C 0.25）：案例题需要跨知识点整合 + 规范条文原文，单 leaf 的 compiled_context（哪怕 2 条/族）远不够；真检索也只拿 0.5。该题型不是 rich_leaf 当前形态能解的，需要题型专用编排。
4. **guard 生产臂的性价比**：相对 B 再省 ~13% tokens（1068 vs 1223），但语义得分再降 6 个百分点（0.600 vs 0.663），且简答题引证真实率归零（fail-closed 护栏 + 1条/族供给在证据不足时让模型弃引证）。**结论：在 frozen v1 当前覆盖水平下，guard 臂省下的 token 不足以补偿质量损失，不建议以此形态替代生产 RAG**；guard 形态的价值要等覆盖补齐后重测。
5. **客观题缩差是真实的**：B 客观 exact 78.1% vs A 84.4%，差 2 题；如果只看客观题、且 leaf 精确命中的子集，rich_leaf 以 ~40% 的 token 成本逼近真 RAG——编译轴方向有效，但必须先解决 77→43 的 node 覆盖缺口和 canonical 定位精度。

## 评测局限（如实）

- n=40（简答仅 8），单 seed；结论方向可信但点估计有抽样噪声。
- judge 与作答同为 deepseek-chat（不同 prompt），存在同源偏置；客观题用确定性 exact match 交叉验证（排序与 judge 一致）。
- A 臂检索延迟（均 4.7s，embedding+远端 PG）未计入 answer latency 列。
- 运行中途因误判进程状态 kill 过一次 runner，经 `--resume-from` 无损续跑（11 题断点全部复用，未重复扣费）。
